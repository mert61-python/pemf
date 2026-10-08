# -*- coding: utf-8 -*-
"""Y101 (S3 · O-A2-9.b, 2-A incelemesi) — arama indeksi parmak izi dosyası YOK ama indeks DOLUYSA indeks BİR KEZ yeniden kurulur.

KUSUR (2-A incelemesi O-A2-9.b): `_ensure_search_index` parmak izi DOSYASI YOKKEN (`_stored_fp == ""`) dolu indeksi yeniden
KURMUYOR, dosyaya güncel sürümü yazıyordu → parmak izi kaybolmuş (silinmiş / okunamamış / taşımada geride kalmış) bir kurulumda
eski kuralla kurulmuş indeks bir daha tazelenmez, hasta (ör. Türkçe katlamayla) aramada bulunamaz. Bugün `search_patients`'ın
ürün çağıranı yok (arama istemcide) — gizli, ama arama ürün yüzeyine bağlandığı gün sessiz arıza olurdu.
Kurgu: indeks ESKİ kuralla kurulur (D2.05/D2.25 kapılarının deseni), parmak izi dosyası SİLİNİR, gerçek kuralla açılır.
Karşıt: yeniden kurulum TEK seferlik — dosya yazıldıktan sonraki açılış yeniden KURMAZ.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def hasta_db(temp_app_data, monkeypatch):
    import database.patient_database as pdb

    monkeypatch.setattr(pdb, "import_sqlcipher", lambda: None)
    monkeypatch.setattr(pdb, "get_sqlcipher_key", lambda *a, **k: "")
    monkeypatch.delenv("PEMF_ENCRYPT_AT_REST", raising=False)
    return pdb.PatientDatabase(str(temp_app_data / "patients.db"))


def _adlar(sonuc):
    return {p.get("name") for p in (sonuc or [])}


def _eski_kuralla_kur(hasta_db, monkeypatch):
    import database.patient_database as pdb

    gercek_kural = pdb.PatientDatabase._normalize_search_value
    monkeypatch.setattr(pdb.PatientDatabase, "_normalize_search_value", lambda self, v: str(v or "").strip().lower())
    hasta_db.add_patient({"name": "İhsan", "owner": "T", "species": "Kedi"})
    assert "İhsan" not in _adlar(hasta_db.search_patients("ihsan")), "eski kural kurulamadı — kapı kör olurdu"
    hasta_db._reset_thread_conn()
    monkeypatch.setattr(pdb.PatientDatabase, "_normalize_search_value", gercek_kural)
    return hasta_db._key_dir / ".patient_search_keyfp"


def test_KRITIK_parmak_izi_dosyasi_YOK_dolu_ESKI_indeks_acilista_yeniden_KURULUR(hasta_db, temp_app_data, monkeypatch):
    import database.patient_database as pdb

    fp_dosyasi = _eski_kuralla_kur(hasta_db, monkeypatch)
    assert fp_dosyasi.exists(), "ön koşul: parmak izi dosyası yazılmış olmalı"
    fp_dosyasi.unlink()  # dosya kayboldu (silindi / taşımada geride kaldı)
    yeni = pdb.PatientDatabase(str(temp_app_data / "patients.db"))
    assert "İhsan" in _adlar(yeni.search_patients("ihsan")), (
        "parmak izi dosyası yokken dolu (eski kurallı) indeks YENİDEN KURULMADI — hasta aramada bulunamıyor"
    )
    assert fp_dosyasi.exists(), "yeniden kurulumdan sonra parmak izi yazılmadı"


def test_KARSIT_yeniden_kurulum_TEK_seferlik_dosya_yazildiktan_sonra_KURMAZ(hasta_db, temp_app_data, monkeypatch):
    import database.patient_database as pdb

    fp_dosyasi = _eski_kuralla_kur(hasta_db, monkeypatch)
    fp_dosyasi.unlink()
    pdb.PatientDatabase(str(temp_app_data / "patients.db"))._reset_thread_conn()
    sayac = {"n": 0}
    gercek = pdb.PatientDatabase._rebuild_search_index

    def _sayan(self, cursor):
        sayac["n"] += 1
        return gercek(self, cursor)

    monkeypatch.setattr(pdb.PatientDatabase, "_rebuild_search_index", _sayan)
    pdb.PatientDatabase(str(temp_app_data / "patients.db"))
    assert sayac["n"] == 0, "parmak izi güncelken indeks her açılışta yeniden kuruluyor (tek seferlik değil)"
