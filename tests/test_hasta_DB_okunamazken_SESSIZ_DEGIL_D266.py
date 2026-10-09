# -*- coding: utf-8 -*-
"""D2.66 (B-3.110) — hasta DB'si okunamazken: dokuz `except _DB_ERROR` dalı SESSİZ DEĞİL; cihaz taşıma "hasta yok" diye başarı DEMEZ.

ÖLÇÜLEN KUSUR (DENETIM-03 B-3.110, 2-D'de yeniden ölçüldü): `PatientDatabase`'in okuma/yazma yöntemleri DB hatasını günlüksüz yutup
boş liste / None / False / 0 dönüyordu. Operatör "hasta yok" görüyor, günlükte iz yok. Asıl uç: arıza sırasında alınan cihaz-taşıma yedeği
hasta listesiz "Yedek oluşturuldu" diyordu (yeni cihaza yüklenirse 0 hasta — veri kaybı zinciri); aynı yutma geri yüklemenin "hedef dolu
mu" denetiminde DOLU cihazı BOŞ gösterip onay (REPLACE_ALL) ve Y111 kapısını atlatıyordu.
ARIZA EN ALT KATTA, GERÇEK BİÇİMİYLE: hasta DB dosyasının SQLite başlığı bozulur (disk/antivirüs hasarı) → SQLite'ın kendisi "file is not a
database" verir.
"""

from __future__ import annotations

import logging

import pytest
from veri_tasima_aparati import PAROLA, cihaz_kur, disa_aktar, doldur, istekler, kapat, uclari_bagla


def _bozuk(hdb) -> None:
    hdb._reset_thread_conn()
    with open(hdb.db_file, "r+b") as f:
        f.write(b"BOZUK-BASLIK-D266" * 6)


@pytest.mark.parametrize(
    "ad, cagri",
    [
        ("get_patient", lambda h, pid: h.get_patient(pid)),
        ("count_patients", lambda h, pid: h.count_patients()),
        ("get_all_patients", lambda h, pid: h.get_all_patients()),
        ("update_patient", lambda h, pid: h.update_patient(pid, {"name": "Yeni"})),
        ("delete_patient", lambda h, pid: h.delete_patient(pid)),
        ("delete_patients_bulk", lambda h, pid: h.delete_patients_bulk([pid])),
        ("clear_all_patients", lambda h, pid: h.clear_all_patients()),
        ("search_patients", lambda h, pid: h.search_patients("Mia")),
        ("get_patient_count", lambda h, pid: h.get_patient_count()),
    ],
)
def test_KRITIK_D266_hasta_DB_okunamazken_her_dal_WARNING_ve_istisna_izi_yazar(
    tmp_path, monkeypatch, caplog, ad, cagri
):
    tdb, hdb = cihaz_kur(monkeypatch, tmp_path / "A")
    try:
        pid = hdb.add_patient({"name": "Mia", "species": "Kedi"})
        _bozuk(hdb)
        with caplog.at_level(logging.WARNING, logger="PatientDatabase"):
            caplog.clear()
            cagri(hdb, pid)
        uyarilar = [r for r in caplog.records if r.name == "PatientDatabase" and r.levelno >= logging.WARNING]
        assert uyarilar, (
            f"{ad}: hasta DB'si okunamazken HİÇBİR uyarı yazılmadı (sessiz yutma — operatör 'hasta yok' görür)"
        )
        assert any(r.exc_info for r in uyarilar), (
            f"{ad}: uyarı istisna izini (exc_info) taşımıyor — kök neden günlükte yok"
        )
    finally:
        kapat(tdb, hdb)


def test_KRITIK_D266_hasta_okumasi_DUSERSE_cihaz_tasima_yedegi_BASARI_demez(tmp_path, monkeypatch):
    from servers import api_server as api

    tdb, hdb = cihaz_kur(monkeypatch, tmp_path / "A")
    uclari_bagla(monkeypatch, tdb, hdb)
    try:
        doldur(tdb, hdb, ["Mia", "Pamuk"], seans_basi=1)
        _bozuk(hdb)
        (r,) = istekler(api.app, [("POST", "/api/data/export", {"passphrase": PAROLA}, None)])
        assert r.status_code != 200, (
            f"hasta DB'si okunamazken yedek 'başarılı' döndü — hasta listesiz yedek: {r.text[:200]}"
        )
        assert "OLUŞTURULMADI" in r.json().get("detail", ""), r.text[:300]
    finally:
        kapat(tdb, hdb)


def test_KRITIK_D266_hasta_okumasi_DUSERSE_geri_yukleme_DOLU_cihazi_BOS_saymaz(tmp_path, monkeypatch):
    """Tedavi DB'si boş (yeni seans yok) ama hasta kartları var — hasta DB'si okunamazken cihaz BOŞ sanılıp onaysız içe aktarma
    yapılmaz."""
    from servers import api_server as api

    ta, ha = cihaz_kur(monkeypatch, tmp_path / "A")
    uclari_bagla(monkeypatch, ta, ha)
    doldur(ta, ha, ["Mia"], seans_basi=1)
    paket = disa_aktar(api.app)
    tb, hb = cihaz_kur(monkeypatch, tmp_path / "B")
    uclari_bagla(monkeypatch, tb, hb)
    try:
        hb.add_patient({"name": "SadeceKart", "species": "Kopek"})  # hedefte yalnız hasta kartı
        _bozuk(hb)
        (r,) = istekler(
            api.app, [("POST", "/api/data/import", {"passphrase": PAROLA, "blob_b64": paket["data_b64"]}, None)]
        )
        assert r.status_code >= 500, (
            f"hasta DB'si okunamazken geri yükleme cihazı BOŞ sayıp sürdü: {r.status_code} {r.text[:200]}"
        )
        with tb._get_connection() as c:
            assert c.execute("SELECT count(*) FROM treatment_sessions").fetchone()[0] == 0, "tedavi DB'sine yazıldı"
    finally:
        kapat(ta, ha, tb, hb)


def test_KARSIT_D266_saglikli_hasta_DB_bugunku_gibi_sessiz_ve_dogru(tmp_path, monkeypatch, caplog):
    tdb, hdb = cihaz_kur(monkeypatch, tmp_path / "A")
    try:
        pid = hdb.add_patient({"name": "Mia", "species": "Kedi"})
        with caplog.at_level(logging.WARNING, logger="PatientDatabase"):
            caplog.clear()
            assert hdb.get_patient(pid)["name"] == "Mia" and len(hdb.get_all_patients()) == 1
        assert [r for r in caplog.records if r.name == "PatientDatabase" and r.levelno >= logging.WARNING] == []
    finally:
        kapat(tdb, hdb)
