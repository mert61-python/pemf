# -*- coding: utf-8 -*-
"""T-d (Tezgâh-2 #9, Y195) — seans CSV'sinde bobinleri SÜREN parametre (duty %) kendi sütununda; "Ayarlanan(mT)" yalnız reçete (mT); eski
CSV okuyucusu kırılmaz.

ÖLÇÜLEN KUSUR (Tezgâh-2, 2026-10-23, `DENETIM/t2/kanit/D_pdf/csv_*.csv`): `ID,Hasta,…,Ayarlanan(mT),…` satırında 50,0 — seansın %50'lik
parametresi mT gibi okundu. Seans CSV'sinde duty HİÇ yoktu (yalnız bobin koşusu CSV'sinde); `/api/session/start` yoğunluk verilmezse
reçeteye "25 mT" UYDURUYORDU (varsayılan 25.0).
SÖZLEŞME: ilk 11 sütun (sıra + başlık) DEĞİŞMEZ; SONA `Duty(%)` (bobin koşularından komut edilen; birden çoksa "25.0/50.0"; koşusuz boş);
başlatma isteğinde yoğunluk yoksa reçete NULL. APARAT: gerçek `TreatmentHistoryDB` (ürünün yazıcıları), gerçek uç (TestClient, cihaz).
"""

from __future__ import annotations

import csv
import io

import pytest
from fastapi.testclient import TestClient

ESKI_TR = [
    "ID",
    "Hasta",
    "Hedef",
    "Mod",
    "Sure(dk)",
    "Frekans(Hz)",
    "Ayarlanan(mT)",
    "Tarih",
    "Baslangic",
    "Durum",
    "Notlar",
]
ESKI_EN = [
    "ID",
    "Patient",
    "Target",
    "Mode",
    "Duration(min)",
    "Frequency(Hz)",
    "Set(mT)",
    "Date",
    "Start",
    "Status",
    "Notes",
]


@pytest.fixture
def o(tmp_path, monkeypatch):
    from database import sqlcipher_util as su
    from database.treatment_history_db import TreatmentHistoryDB
    from servers import api_server as api
    from servers import history_router as hr

    monkeypatch.delenv("PEMF_ENCRYPT_AT_REST", raising=False)
    monkeypatch.setattr(su, "get_sqlcipher_key", lambda *a, **k: "")
    monkeypatch.setattr(TreatmentHistoryDB, "_get_sqlcipher_key_legacy", lambda self: "")
    tdb = TreatmentHistoryDB(tmp_path / "gecmis")
    with tdb._get_connection() as c:
        c.executemany(
            "INSERT INTO treatment_sessions (id, session_date, start_time, treatment_mode, patient_name, frequency_hz, intensity_mt, "
            "session_status) VALUES (?, '2026-10-23', '14:55:43', 'Manuel', ?, 100.0, ?, 'completed')",
            [(5, "T2 Test", None), (6, "Iki Bobin", 2.5), (7, "Kosusuz", None)],
        )
        c.commit()
    tdb.start_coil_run(5, 1, frequency_hz=100.0, duty_percent=50.0, started_epoch=1_792_800_000.0)
    tdb.start_coil_run(6, 1, frequency_hz=100.0, duty_percent=25.0, started_epoch=1_792_800_010.0)
    tdb.start_coil_run(6, 2, frequency_hz=100.0, duty_percent=50.0, started_epoch=1_792_800_011.0)
    tdb.start_coil_run(6, 3, frequency_hz=100.0, duty_percent=25.0, started_epoch=1_792_800_012.0)
    api.app.dependency_overrides[hr.get_db] = lambda: tdb
    try:
        yield type("O", (), {"tdb": tdb, "c": TestClient(api.app, client=("127.0.0.1", 53217))})
    finally:
        api.app.dependency_overrides.pop(hr.get_db, None)
        tdb.close()


def _tablo(r) -> list[list[str]]:
    assert r.status_code == 200, r.text[:200]
    return list(csv.reader(io.StringIO(r.content.decode("utf-8-sig"))))


def test_KRITIK_seans_csv_DUTY_sutunu_SONDA_eski_11_sutun_AYNI(o):
    t = _tablo(o.c.get("/api/history/export_csv"))
    assert t[0][:11] == ESKI_TR, f"eski sütunların sırası / başlığı değişti (eski okuyucu kırılır): {t[0]}"
    assert t[0][11:] == ["Duty(%)"], t[0]
    satir = {r[0]: r for r in t[1:]}
    assert satir["5"][6] == "" and satir["5"][11] == "50.0", (
        f"reçetesiz elle seansta duty mT sütununda / eksik: {satir['5']}"
    )
    assert satir["6"][6] == "2.5" and satir["6"][11] == "25.0/50.0", satir["6"]
    assert satir["7"][11] == "", "koşusuz seansa duty uyduruldu"
    assert all(len(r) == 12 for r in t), "satır / başlık sütun sayısı tutmuyor"


def test_KRITIK_EN_baslik_eski_11_sutun_AYNI_ve_Duty_sonda(o):
    t = _tablo(o.c.get("/api/history/export_csv", headers={"X-PEMF-Dil": "en"}))
    assert t[0][:11] == ESKI_EN and t[0][11] == "Duty(%)", t[0]


def test_KRITIK_ESKI_okuyucu_bildigi_sutunlari_AYNI_degerle_okur(o):
    """Eski okuyucu (başlık adıyla `DictReader`, bildiği 11 sütun) yeni dosyada aynı değerleri bulur; fazladan sütun onu bozmaz."""
    r = o.c.get("/api/history/export_csv")
    okunan = list(csv.DictReader(io.StringIO(r.content.decode("utf-8-sig"))))
    s6 = next(x for x in okunan if x["ID"] == "6")
    assert {k: s6[k] for k in ("Hasta", "Mod", "Frekans(Hz)", "Ayarlanan(mT)", "Durum")} == {
        "Hasta": "Iki Bobin",
        "Mod": "Manuel",
        "Frekans(Hz)": "100.0",
        "Ayarlanan(mT)": "2.5",
        "Durum": "Tamamlandı",
    }


def test_KRITIK_duty_ozeti_DB_hatasini_YUTMAZ(o, monkeypatch):
    """Duty okunamazsa dosya "duty yok" diye boş hücreyle VERİLMEZ (500)."""
    import sqlite3

    def _bozuk(_ids):
        raise sqlite3.OperationalError("disk I/O error (sahte)")

    monkeypatch.setattr(o.tdb, "get_session_duty_ozeti", _bozuk)
    assert o.c.get("/api/history/export_csv").status_code == 500


def test_KRITIK_baslatmada_yogunluk_YOKSA_recete_UYDURULMAZ():
    """`/api/session/start` gövdesinde `intensity` yoksa kayda "25 mT" yazılmaz (`intensity_mt = payload.intensity or None`)."""
    from servers import api_server as api

    p = api.SessionStartPayload(patient_name="T2 Test", mode="Manuel", frequency=100, duty=50, duration_minutes=1)
    assert (p.intensity or None) is None, f"yoğunluk verilmediği hâlde reçete {p.intensity} mT yazılır"
