# Author: mertaygn, cglrgrkn
"""KP-1 · apps/backend/servers/history_router.py · sözleşmeler: seans GEÇMİŞİ uçlarının hata ve kenar yolları — liste / PDF /
hasta PDF'i / not / ayrıntı / bobin CSV'si / tek seans: DB ya da PDF üreticisi patlarsa 500 `gecmis.hata.islemBasarisiz`
(ayrıntı ucu KENDİ 404'ünü 500'e çevirmez); CSV: geçersiz kimlik listesi 400 düz metin, geri yükleme sürerken 409; hasta PDF'i
dosyayı gönderir ve gönderim sonrası geçici PII dosyasını siler; tekil silme DB'de düşerse 500 ve iz "ok" YAZILMAZ; toplu
silme özeti okunamazsa silme kısıtlanmaz, iz `ozet_okunamadi` taşır; toplu silme DB'de düşerse 500, kayıt silinmez;
süren seans denetimi api_server yüklenemezse silmeyi engellemez; `_safe_unlink` olmayan dosyada sessiz; `_purge_old_reports`
yalnız 1 saatten eski PDF'leri siler, silinemeyen dosya ve okunamayan dizin işi bozmaz; `_epoch_to_hms` geçersiz epoch'ta "".

Sahte EN ALT katta: tedavi DB'si GERÇEK (`TreatmentHistoryDB`, tmp); arızalar DB yöntemi düzeyinde `sqlite3.OperationalError`,
PDF üreticisi (`get_pdf_gen` bağımlılığı → OSError / tmp'ye yazan kayıtçı), dosya sistemi (`Path.unlink` → PermissionError,
rapor dizini nesnesi → OSError), modül yüklenemezliği (`sys.modules` girdisi None + paket özniteliği — monkeypatch ikisini
birlikte geri koyar).
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

CIHAZ = ("127.0.0.1", 50151)


def _tr(anahtar, **k):
    from utils import ceviri

    return ceviri.t(anahtar, dil="tr", **k)


def _patla(hata):
    def _f(*_a, **_k):
        raise hata

    return _f


def _iz(tdb, olay, sure=2.0):
    son = time.monotonic() + sure
    while True:
        iz = tdb.denetim_oku(event_type=olay)
        if iz or time.monotonic() >= son:
            return iz
        time.sleep(0.05)


@pytest.fixture
def o(tmp_path, monkeypatch):
    from database import sqlcipher_util as su
    from database.treatment_history_db import TreatmentHistoryDB
    from servers import api_server as api
    from servers import history_router as hr

    monkeypatch.delenv("PEMF_ENCRYPT_AT_REST", raising=False)
    monkeypatch.setattr(su, "get_sqlcipher_key", lambda *a, **k: "")
    monkeypatch.setattr(TreatmentHistoryDB, "_get_sqlcipher_key_legacy", lambda self: "")
    monkeypatch.setattr(api, "_RL_REMOTE_MAX", 0)
    monkeypatch.setattr(hr, "_app_data_dir", tmp_path)
    (tmp_path / "gecmis").mkdir()
    tdb = TreatmentHistoryDB(tmp_path / "gecmis")
    monkeypatch.setattr(api, "_get_treatment_db", lambda: tdb)  # denetim izi aynı DB'ye
    pdf: list = []
    api.app.dependency_overrides[hr.get_db] = lambda: tdb
    api.app.dependency_overrides[hr.get_pdf_gen] = lambda: pdf[0]
    try:
        with TestClient(api.app, client=CIHAZ) as c:
            yield SimpleNamespace(api=api, hr=hr, tdb=tdb, c=c, pdf=pdf, tmp=tmp_path)
    finally:
        api.app.dependency_overrides.pop(hr.get_db, None)
        api.app.dependency_overrides.pop(hr.get_pdf_gen, None)
        tdb.close()


def _seans(tdb, ad="Mia") -> int:
    sid = tdb.start_session(treatment_mode="Manuel", patient_name=ad)
    tdb.end_session(sid, duration_minutes=5)
    return sid


# ── liste · PDF · CSV ──────────────────────────────────────────────────────────────────────────────────────────────────────────


def test_LISTE_DB_okumasi_PATLARSA_500(o, monkeypatch):
    """`get_session_history` OperationalError → GET /api/history/ 500 `gecmis.hata.islemBasarisiz`."""
    monkeypatch.setattr(o.tdb, "get_session_history", _patla(sqlite3.OperationalError("database is locked")))
    r = o.c.get("/api/history/")
    assert (r.status_code, r.json()["detail"]) == (500, _tr("gecmis.hata.islemBasarisiz"))


def test_SEANS_PDF_uretici_DISK_hatasi_500_rapor_dizini_olusur(o):
    """PDF üreticisi OSError (disk dolu) → GET /export_pdf?session_ids=1,2 500 `islemBasarisiz`; çıktı `temp_reports` altına
    `report_1_` önekiyle istenmişti."""
    istenen: list = []

    def _uret(session_ids, output_path):
        istenen.append((session_ids, Path(output_path).parent.name, Path(output_path).name.startswith("report_1_")))
        raise OSError(28, "No space left on device")

    o.pdf.append(SimpleNamespace(generate_session_report=_uret))
    r = o.c.get("/api/history/export_pdf", params={"session_ids": "1,2"})
    assert (r.status_code, r.json()["detail"]) == (500, _tr("gecmis.hata.islemBasarisiz"))
    assert istenen == [([1, 2], "temp_reports", True)]


def test_CSV_gecersiz_kimlik_listesi_400_duz_metin(o):
    """`session_ids=1,x` → 400 `text/plain`, gövde `gecmis.hata.gecersizSessionIds`."""
    r = o.c.get("/api/history/export_csv", params={"session_ids": "1,x"})
    assert r.status_code == 400 and r.headers["content-type"].startswith("text/plain")
    assert r.text == _tr("gecmis.hata.gecersizSessionIds")


def test_CSV_geri_yukleme_SURERKEN_409(o):
    """Tedavi DB'sinin geri yükleme nesli TEK (sürüyor) → 409 {"detail": `gecmis.hata.geriYukleme`}; dosya verilmez."""
    _seans(o.tdb)
    o.tdb._geri_yukleme_nesli = 3
    r = o.c.get("/api/history/export_csv", params={"session_ids": "1"})
    assert (r.status_code, r.json()) == (409, {"detail": _tr("gecmis.hata.geriYukleme")})


def test_HASTA_PDF_gonderilir_ve_gecici_PII_dosyasi_SILINIR(o):
    """Üretici `temp_reports/patient_report_*.pdf` yazar → 200 `application/pdf`, gövde aynen, dosya adı "Mia_PEMF_Report.pdf";
    gönderim sonrası geçici dosya SİLİNMİŞ."""
    yazilan: list = []

    def _uret(patient_name, output_path):
        Path(output_path).write_bytes(b"%PDF-1.4 kp " + patient_name.encode())
        yazilan.append(Path(output_path))
        return output_path

    o.pdf.append(SimpleNamespace(generate_patient_report=_uret))
    r = o.c.get("/api/history/export_patient_pdf", params={"patient_name": "Mia"})
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    assert r.content == b"%PDF-1.4 kp Mia"
    assert 'filename="Mia_PEMF_Report.pdf"' in r.headers["content-disposition"]
    assert (
        len(yazilan) == 1
        and yazilan[0].parent == o.tmp / "temp_reports"
        and yazilan[0].name.startswith("patient_report_")
    )
    assert not yazilan[0].exists()


def test_HASTA_PDF_uretici_PATLARSA_500(o):
    """Üretici OSError → 500 `islemBasarisiz`."""
    o.pdf.append(SimpleNamespace(generate_patient_report=_patla(OSError(13, "Erişim engellendi"))))
    r = o.c.get("/api/history/export_patient_pdf", params={"patient_name": "Mia"})
    assert (r.status_code, r.json()["detail"]) == (500, _tr("gecmis.hata.islemBasarisiz"))


# ── silme · not ───────────────────────────────────────────────────────────────────────────────────────────────────────────────


def test_TEKIL_SILME_DB_de_DUSERSE_500_kayit_durur_ok_izi_YOK(o, monkeypatch):
    """Var olan seans + `delete_session` OperationalError → POST /delete 500 `islemBasarisiz`; seans DB'de DURUR; `history.delete`
    izine "ok" yazılmaz."""
    sid = _seans(o.tdb)
    monkeypatch.setattr(o.tdb, "delete_session", _patla(sqlite3.OperationalError("database is locked")))
    r = o.c.post("/api/history/delete", json={"session_id": sid})
    assert (r.status_code, r.json()["detail"]) == (500, _tr("gecmis.hata.islemBasarisiz"))
    assert o.tdb.seans_sahipleri([sid]) != {}
    assert [s for s in o.tdb.denetim_oku(event_type="history.delete") if s["outcome"] == "ok"] == []


def test_TOPLU_SILME_ozet_OKUNAMAZSA_silme_KISITLANMAZ_iz_ozetsiz(o, monkeypatch):
    """İki seans + `seans_silme_ozeti_toplu` OperationalError → 200 {istenen 2, silinen 2}; seanslar silinir; `history.delete_bulk`
    izi "ok", 2 kalem, ayrıntı {"ozet_okunamadi": true}."""
    a, b = _seans(o.tdb, "Mia"), _seans(o.tdb, "Pamuk")
    monkeypatch.setattr(o.tdb, "seans_silme_ozeti_toplu", _patla(sqlite3.OperationalError("database is locked")))
    r = o.c.post("/api/history/delete_bulk", json={"session_ids": [a, b], "confirm": "DELETE_SELECTED"})
    assert (r.status_code, r.json()) == (200, {"status": "success", "istenen": 2, "silinen": 2})
    assert o.tdb.seans_sahipleri([a, b]) == {}
    iz = _iz(o.tdb, "history.delete_bulk")
    assert [(s["outcome"], s["item_count"], json.loads(s["detail"])) for s in iz] == [
        ("ok", 2, {"ozet_okunamadi": True})
    ]


def test_TOPLU_SILME_DB_de_DUSERSE_500_kayitlar_DURUR(o, monkeypatch):
    """`delete_sessions_bulk` OperationalError → 500 `islemBasarisiz`; iki seans da DB'de durur."""
    a, b = _seans(o.tdb, "Mia"), _seans(o.tdb, "Pamuk")
    monkeypatch.setattr(o.tdb, "delete_sessions_bulk", _patla(sqlite3.OperationalError("disk I/O error")))
    r = o.c.post("/api/history/delete_bulk", json={"session_ids": [a, b], "confirm": "DELETE_SELECTED"})
    assert (r.status_code, r.json()["detail"]) == (500, _tr("gecmis.hata.islemBasarisiz"))
    assert sorted(o.tdb.seans_sahipleri([a, b])) == sorted([a, b])


def test_SUREN_SEANS_denetimi_api_server_YUKLENEMEZSE_silmeyi_engellemez(monkeypatch):
    """`servers.api_server` içe aktarılamıyor (girdi None, paket özniteliği yok) → `_suren_seans_reddi` istisnasız döner (süren
    seans bilinemez; bu süreçte seans durumu da yoktur)."""
    import servers
    from servers import api_server as _api  # noqa: F401 — geri koyma için yüklü olsun
    from servers import history_router as hr

    monkeypatch.delattr(servers, "api_server")
    monkeypatch.setitem(sys.modules, "servers.api_server", None)
    with pytest.raises(ImportError):
        from servers import api_server  # noqa: F401
    assert hr._suren_seans_reddi(None, [5], "history.delete", "id=5") is None


def test_NOT_guncelleme_DB_de_DUSERSE_500(o, monkeypatch):
    """`update_session_notes` OperationalError → POST /update_notes 500 `islemBasarisiz`."""
    sid = _seans(o.tdb)
    monkeypatch.setattr(o.tdb, "update_session_notes", _patla(sqlite3.OperationalError("database is locked")))
    r = o.c.post("/api/history/update_notes", json={"session_id": sid, "notes": "kontrol"})
    assert (r.status_code, r.json()["detail"]) == (500, _tr("gecmis.hata.islemBasarisiz"))


# ── ayrıntı · bobin CSV'si · tek seans ────────────────────────────────────────────────────────────────────────────────────────


def test_AYRINTI_olmayan_seans_404_DB_hatasi_500(o, monkeypatch):
    """Olmayan seans → GET /{id}/details 404 "Session not found" (500'e çevrilmez); `get_session_details` OperationalError → 500."""
    r = o.c.get("/api/history/987654/details")
    assert (r.status_code, r.json()["detail"]) == (404, "Session not found")
    monkeypatch.setattr(o.tdb, "get_session_details", _patla(sqlite3.OperationalError("database is locked")))
    r = o.c.get("/api/history/1/details")
    assert (r.status_code, r.json()["detail"]) == (500, _tr("gecmis.hata.islemBasarisiz"))


def test_BOBIN_CSV_DB_hatasi_500(o, monkeypatch):
    """`get_session_coil_runs` OperationalError → GET /{id}/coil_runs.csv 500 `islemBasarisiz`."""
    monkeypatch.setattr(o.tdb, "get_session_coil_runs", _patla(sqlite3.OperationalError("database is locked")))
    r = o.c.get("/api/history/1/coil_runs.csv")
    assert (r.status_code, r.json()["detail"]) == (500, _tr("gecmis.hata.islemBasarisiz"))


def test_TEK_SEANS_var_200_yok_404_DB_hatasi_500(o, monkeypatch):
    """GET /api/history/{id}: var olan seans → 200 ve gövde DB'nin ayrıntısıyla aynı kimlik/hasta; olmayan → 404 "Session not
    found" (500'e çevrilmez); DB OperationalError → 500 `islemBasarisiz`."""
    sid = _seans(o.tdb, "Boncuk")
    r = o.c.get(f"/api/history/{sid}")
    assert r.status_code == 200
    assert (r.json()["id"], r.json()["patient_name"]) == (sid, "Boncuk")
    r = o.c.get("/api/history/987654")
    assert (r.status_code, r.json()["detail"]) == (404, "Session not found")
    monkeypatch.setattr(o.tdb, "get_session_details", _patla(sqlite3.OperationalError("database is locked")))
    r = o.c.get(f"/api/history/{sid}")
    assert (r.status_code, r.json()["detail"]) == (500, _tr("gecmis.hata.islemBasarisiz"))


# ── yardımcılar ───────────────────────────────────────────────────────────────────────────────────────────────────────────────


def test_SAFE_UNLINK_olmayan_dosyada_sessiz_olani_siler(tmp_path):
    """Olmayan yol → istisna YOK; var olan dosya → silinir."""
    from servers import history_router as hr

    hr._safe_unlink(str(tmp_path / "yok.pdf"))
    f = tmp_path / "var.pdf"
    f.write_bytes(b"x")
    hr._safe_unlink(str(f))
    assert not f.exists()


def test_PURGE_yalniz_ESKI_pdf_silinir_silinemeyen_isi_bozmaz(tmp_path, monkeypatch):
    """2 saatlik `eski.pdf` silinir; 2 saatlik `kilitli.pdf` PermissionError → durur, iş sürer; yeni `taze.pdf` ve `eski.txt`
    durur."""
    from servers import history_router as hr

    d = tmp_path / "temp_reports"
    d.mkdir()
    eski, kilitli, taze, metin = (d / "eski.pdf"), (d / "kilitli.pdf"), (d / "taze.pdf"), (d / "eski.txt")
    for f in (eski, kilitli, taze, metin):
        f.write_bytes(b"x")
    iki_saat_once = time.time() - 7200
    for f in (eski, kilitli, metin):
        os.utime(f, (iki_saat_once, iki_saat_once))
    gercek = Path.unlink

    def _unlink(self, *a, **k):
        if self.name == "kilitli.pdf":
            raise PermissionError(13, "dosya başka süreçte açık")
        return gercek(self, *a, **k)

    monkeypatch.setattr(Path, "unlink", _unlink)
    monkeypatch.setattr(hr, "_REPORTS_DIR", d)
    hr._purge_old_reports()
    assert (eski.exists(), kilitli.exists(), taze.exists(), metin.exists()) == (False, True, True, True)


def test_PURGE_dizin_LISTELENEMEZSE_istisna_sizmaz(monkeypatch):
    """Rapor dizini var ama listeleme OSError → `_purge_old_reports` istisnasız döner."""
    from servers import history_router as hr

    listelenen: list = []

    class _Dizin:
        def exists(self):
            return True

        def glob(self, desen):
            listelenen.append(desen)
            raise OSError(5, "Erişim engellendi")

    monkeypatch.setattr(hr, "_REPORTS_DIR", _Dizin())
    assert hr._purge_old_reports() is None
    assert listelenen == ["*.pdf"]


@pytest.mark.parametrize("epoch", ["abc", 1e20, float("nan")])
def test_EPOCH_HMS_gecersiz_epoch_bos(epoch):
    """Sayıya çevrilemeyen / taşan / NaN epoch → "" (rapor satırı bozulmaz); geçerli epoch → HH:MM:SS."""
    from datetime import datetime

    from servers import history_router as hr

    assert hr._epoch_to_hms(epoch) == ""
    assert hr._epoch_to_hms(0) == datetime.fromtimestamp(0).strftime("%H:%M:%S")
