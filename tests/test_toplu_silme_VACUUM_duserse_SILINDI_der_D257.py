# -*- coding: utf-8 -*-
"""D2.57 (B-3.87 · B-3.109) — toplu silmede DELETE commit edildikten SONRA VACUUM düşerse sonuç "silindi, VACUUM başarısız"
diye AYRI bildirilir; denetim izi GERÇEK silinen sayıyı yazar.

ÖLÇÜLEN KUSUR (DENETIM-03): `clear_ai_analyses` ve `clear_all_patients` DELETE + commit + VACUUM'u tek `try`'da tutuyordu → VACUUM
(disk dolu / G-Ç) düşünce silme GERÇEKLEŞMİŞ olduğu hâlde `-1` / `False` dönüyor, KVKK denetim izi "hata, 0" yazıyor, arayüz
"başarısız" deyip listeyi yenilemiyordu (operatör verinin durduğunu sanıyor).
  · AI yarısı (B-3.87) D1.58'de (`89cc4b2`) kapandı: VACUUM düşerse silinen sayı döner, VACUUM ertelenir (kalıcı işaret).
    Bu dosyanın AI kolları onu GERÇEK uçla bekçiler (ebeveynde KIRMIZI olduğu ayrıca gösterildi — rapor §3.28).
  · Hasta yarısı (B-3.109) bu maddede.
GERÇEK: `PatientDatabase` / `TreatmentHistoryDB` (geçici), GERÇEK uçlar (`/api/patients/delete_all` cihazın kendisinden — A-03,
`/api/ai/log/delete_all`). VACUUM düşüşü EN ALT katta: SQLite bağlantısının `execute`'u yalnız "VACUUM" ifadesinde
`OperationalError` fırlatır (DELETE ve commit GERÇEK). Satırlar SQL ile, iz `denetim_oku`.
"""

from __future__ import annotations

import json
import sqlite3

import pytest
from fastapi.testclient import TestClient


class _VacuumDuserBaglanti:
    """Gerçek bağlantıyı sarar; yalnız VACUUM'da disk-dolu hatası (diğer her şey gerçek)."""

    def __init__(self, ic):
        object.__setattr__(self, "_ic", ic)

    def __setattr__(self, ad, deger):  # `conn.row_factory = …` gerçek bağlantıya gider
        setattr(self._ic, ad, deger)

    def execute(self, sql, *a, **k):
        if str(sql).strip().upper().startswith("VACUUM"):
            raise sqlite3.OperationalError("database or disk is full")
        return self._ic.execute(sql, *a, **k)

    def cursor(self):
        return _VacuumDuserImlec(self._ic.cursor())

    def __getattr__(self, ad):
        return getattr(self._ic, ad)

    def __enter__(self):
        self._ic.__enter__()
        return self

    def __exit__(self, *a):
        return self._ic.__exit__(*a)


class _VacuumDuserImlec:
    def __init__(self, ic):
        self._ic = ic

    def execute(self, sql, *a, **k):
        if str(sql).strip().upper().startswith("VACUUM"):
            raise sqlite3.OperationalError("database or disk is full")
        return self._ic.execute(sql, *a, **k)

    def __getattr__(self, ad):
        return getattr(self._ic, ad)


class _SarilmisYonetici:
    """`_get_connection` bağlam yöneticisi döndürüyorsa (TreatmentHistoryDB) girişte gerçek bağlantıyı sarar."""

    def __init__(self, ic):
        self._ic = ic

    def __enter__(self):
        return _VacuumDuserBaglanti(self._ic.__enter__())

    def __exit__(self, *a):
        return self._ic.__exit__(*a)


def _vacuum_dusur(monkeypatch, nesne):
    gercek = type(nesne)._get_connection

    def _sarili(self, *a, **k):
        ic = gercek(self, *a, **k)
        return _VacuumDuserBaglanti(ic) if hasattr(ic, "cursor") else _SarilmisYonetici(ic)

    monkeypatch.setattr(type(nesne), "_get_connection", _sarili)


@pytest.fixture
def hdb(temp_app_data, monkeypatch):
    import database.patient_database as pdb

    monkeypatch.setattr(pdb, "import_sqlcipher", lambda: None)
    monkeypatch.setattr(pdb, "get_sqlcipher_key", lambda *a, **k: "")
    monkeypatch.delenv("PEMF_ENCRYPT_AT_REST", raising=False)
    db = pdb.PatientDatabase(str(temp_app_data / "patients.db"))
    for ad in ("Boncuk", "Pamuk", "Tekir"):
        db.add_patient({"name": ad, "owner": "S", "species": "Kedi"})
    return db


def _hasta_sayisi(db) -> int:
    db._reset_thread_conn()
    with db._get_connection() as c:
        return c.execute("SELECT COUNT(*) FROM patients").fetchone()[0]


# ── Hasta yarısı (B-3.109) ─────────────────────────────────────────────────────────────────────────────────────────────


def test_KRITIK_hasta_DELETE_sonrasi_VACUUM_duserse_SILINEN_sayi_ve_vacuum_FALSE(hdb, monkeypatch):
    _vacuum_dusur(monkeypatch, hdb)
    sonuc = hdb.clear_all_patients()
    monkeypatch.undo()
    assert _hasta_sayisi(hdb) == 0, "ön koşul: DELETE gerçekleşmeli"
    assert tuple(sonuc) == (3, False), f"silme gerçekleşti ama sonuç {sonuc!r} (silindi + VACUUM başarısız beklenir)"


def test_KARSIT_hasta_VACUUM_basarili_ise_SILINEN_sayi_ve_vacuum_TRUE(hdb):
    assert tuple(hdb.clear_all_patients()) == (3, True)
    assert _hasta_sayisi(hdb) == 0


@pytest.fixture
def uc(hdb, monkeypatch):
    from servers import api_server as api
    from servers import patient_router

    monkeypatch.setattr(patient_router, "get_patient_database", lambda: hdb)
    return TestClient(api.app, client=("127.0.0.1", 51234))


def _iz(denetim_db, eylem):
    return [(s["outcome"], s["item_count"], json.loads(s["detail"] or "{}")) for s in denetim_db.denetim_oku(20, eylem)]


def test_KRITIK_hasta_ucu_VACUUM_duserse_SILINDI_der_iz_GERCEK_sayi(uc, hdb, monkeypatch, tmp_path):
    from database.treatment_history_db import TreatmentHistoryDB
    from servers import api_server as api

    tdb = TreatmentHistoryDB(tmp_path / "gecmis")
    monkeypatch.setattr(api, "_get_treatment_db", lambda: tdb)
    _vacuum_dusur(monkeypatch, hdb)
    r = uc.post("/api/patients/delete_all", json={"confirm": "DELETE_ALL"})
    assert r.status_code == 200, r.text[:200]
    j = r.json()
    assert (j.get("status"), j.get("deleted"), j.get("vacuum_ok")) == ("success", 3, False), j
    assert _iz(tdb, "patient.delete_all") == [("ok", 3, {"vacuum": False})], _iz(tdb, "patient.delete_all")


# ── AI yarısı (B-3.87 — D1.58'de kapandı; bekçi) ────────────────────────────────────────────────────────────────────────


@pytest.fixture
def tdb(tmp_path, monkeypatch):
    from database.treatment_history_db import TreatmentHistoryDB
    from servers import api_server as api

    db = TreatmentHistoryDB(tmp_path / "gecmis2")
    monkeypatch.setattr(api, "_get_treatment_db", lambda: db)
    for i in range(3):
        db.add_ai_analysis(module_id="m", patient_name=f"P{i}", result_summary="o")
    return db


def test_KRITIK_AI_DELETE_sonrasi_VACUUM_duserse_SILINEN_sayi_ve_VACUUM_ERTELENIR(tdb, monkeypatch):
    _vacuum_dusur(monkeypatch, tdb)
    n = tdb.clear_ai_analyses(None)
    monkeypatch.undo()
    assert n == 3, f"silme gerçekleşti ama sonuç {n}"
    assert tdb.vacuum_bekliyor_mu() is True, "düşen VACUUM ertelenmedi (KVKK — silinen veri dosyada kalır)"


def test_KRITIK_AI_ucu_VACUUM_duserse_iz_OK_ve_GERCEK_sayi(tdb, monkeypatch):
    from servers import api_server as api

    c = TestClient(api.app, client=("127.0.0.1", 51234))
    _vacuum_dusur(monkeypatch, tdb)
    r = c.post("/api/ai/log/delete_all", json={"confirm": "DELETE_ALL", "all_operators": True})
    assert r.status_code == 200, r.text[:200]
    iz = [(o, n) for o, n, _d in _iz(tdb, "ai_log.delete_all")]
    assert iz == [("ok", 3)], iz


def test_KRITIK_arayuz_fiksturu_GERCEK_hasta_ucu_yanitiyla_AYNI(uc, hdb, monkeypatch, tmp_path):
    """Arayüz yarısı (`screens/__tests__/tumunuSil.D257.vacuum.web.test.tsx`) bu GERÇEK yanıtı okur (jest Python koşturamaz).
    Bayatlarsa KIRMIZI; yenilemek: `D257_FIKSTUR_YAZ=1`."""
    import os
    from pathlib import Path

    from database.treatment_history_db import TreatmentHistoryDB
    from servers import api_server as api

    tdb = TreatmentHistoryDB(tmp_path / "gecmis3")
    monkeypatch.setattr(api, "_get_treatment_db", lambda: tdb)
    _vacuum_dusur(monkeypatch, hdb)
    r = uc.post("/api/patients/delete_all", json={"confirm": "DELETE_ALL"})
    beklenen = {"durum": r.status_code, "govde": r.json()}
    f = (
        Path(__file__).resolve().parents[1]
        / "apps"
        / "ui"
        / "src"
        / "screens"
        / "__tests__"
        / "__fixtures__"
        / "hastaTumunuSil.D257.json"
    )
    if os.environ.get("D257_FIKSTUR_YAZ") == "1":
        f.write_text(json.dumps(beklenen, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    assert f.exists(), "arayüz fikstürü yok (D257_FIKSTUR_YAZ=1 ile üret)"
    assert json.loads(f.read_text(encoding="utf-8")) == beklenen, "arayüz fikstürü GERÇEK yanıttan BAYATLADI"
