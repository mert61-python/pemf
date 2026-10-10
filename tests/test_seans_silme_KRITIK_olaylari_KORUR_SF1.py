# -*- coding: utf-8 -*-
"""S-F.1 [ÖNERİLEN UYGULANDI] (2-F · A-07 "kritik tıbbi olaylar SÜRESİZ") — operatörün seans silmesi (tekil ve toplu) seansın KRİTİK
olaylarını SİLMEZ: seans bağı kopar (`session_id` NULL), yüke silinen seansın kimliği yazılır; kritik olmayan olaylar seansla gider.

ÖLÇÜLEN DURUM: `delete_session` / `delete_sessions_bulk` seansın TÜM `session_events` satırlarını siliyordu — ACİL DURDUR (ve nedeni:
aşırı akım, NACK, STM kopması, bekçi) ile seansı kesen servis kapanışı dahil. D2.17 / O-B.7 izi kaç acil durdurmanın gittiğini yazıyor ama
kaydın kendisi yok oluyordu. A-07 ve bu oturumun kuralı ("kritik olaylar hiçbir yoldan silinmez") ile çelişiyordu. Kritik olay yükünde
PII YOK (neden, kip, bobin listesi) → seansla birlikte hasta kaydı silinse de KVKK açısından ad/kimlik taşımaz.
GERÇEK uçlar (TestClient — yerel istemci), GERÇEK operatör jetonu, GERÇEK tedavi DB'si.
"""

import json
import time

import pytest
from fastapi.testclient import TestClient

AYSE = "dr.ayse@klinik.com"


@pytest.fixture
def o(tmp_path, monkeypatch):
    from database.treatment_history_db import TreatmentHistoryDB
    from servers import api_server as api
    from servers import operator_tokens
    from servers.history_router import get_db

    tdb = TreatmentHistoryDB(tmp_path / "gecmis")
    monkeypatch.setattr(api, "_get_treatment_db", lambda: tdb)
    api.app.dependency_overrides[get_db] = lambda: tdb
    c = TestClient(api.app, client=("127.0.0.1", 51936))

    def _sil():
        for op in c.get("/api/operators").json().get("data", []):
            c.post("/api/operators/remove", json={"email": op["email"]})

    operator_tokens.temizle_hepsi()
    _sil()
    try:
        assert (
            c.post("/api/operators/enroll", json={"email": AYSE, "display_name": "A", "pin": "123456"}).status_code
            == 200
        )
        j = c.post("/api/operators/verify", json={"email": AYSE, "pin": "123456"}).json()["operator_token"]
        yield type("O", (), {"tdb": tdb, "c": c, "h": {"X-PEMF-Operator": j}})
    finally:
        api.app.dependency_overrides.pop(get_db, None)
        operator_tokens.temizle_hepsi()
        _sil()
        tdb.close_connections()


def _seans(o) -> dict:
    sid = int(o.tdb.start_session(treatment_mode="Manuel", patient_name="Boncuk SF1", operator_email=AYSE))
    k = {
        "sid": sid,
        "estop": o.tdb.record_session_event(
            sid, "emergency_stop", {"reason": "overcurrent", "coil_ids": [2]}, severity="critical"
        ),
        "kapanis": o.tdb.record_session_event(sid, "service_shutdown", {"mode": "Manuel"}),
        "not": o.tdb.record_session_event(sid, "coil_ack", {"a": 1}),
    }
    o.tdb.start_coil_run(sid, 1, frequency_hz=10.0, started_epoch=time.time())
    return k


def _olay(o, eid):
    with o.tdb._get_connection() as c:
        r = c.execute("SELECT session_id, payload FROM session_events WHERE id=?", (eid,)).fetchone()
    return None if r is None else (r[0], json.loads(r[1] or "{}"))


@pytest.mark.parametrize("yol", ["POST /delete", "DELETE /{id}", "POST /delete_bulk"])
def test_KRITIK_seans_silinince_KRITIK_olaylar_KALIR_bagi_kopar_kritik_olmayan_gider(o, yol):
    """MUTASYON: silmede kritik olaylar da silinir (eski davranış) → KIRMIZI."""
    k = _seans(o)
    sid = k["sid"]
    if yol == "POST /delete":
        r = o.c.post("/api/history/delete", json={"session_id": sid}, headers=o.h)
    elif yol == "DELETE /{id}":
        r = o.c.delete(f"/api/history/{sid}", headers=o.h)
    else:
        r = o.c.post("/api/history/delete_bulk", json={"session_ids": [sid], "confirm": "DELETE_SELECTED"}, headers=o.h)
    assert r.status_code == 200, r.text
    assert o.tdb.get_session_details(sid) is None, "aparat: seans silinmedi"
    for ad in ("estop", "kapanis"):
        kalan = _olay(o, k[ad])
        assert kalan is not None, f"{yol}: kritik olay ({ad}) seansla SİLİNDİ (A-07: süresiz)"
        assert kalan[0] is None and kalan[1].get("silinen_seans_id") == sid, f"{yol}: {ad} bağı/izi yanlış: {kalan}"
    assert _olay(o, k["not"]) is None, f"{yol}: kritik OLMAYAN olay seansla gitmedi"


@pytest.mark.parametrize("yol", ["POST /delete", "POST /delete_bulk"])
def test_KRITIK_iz_KORUNAN_kritik_sayisini_soyler(o, yol):
    """MUTASYON: iz `kritik_korunan` taşımaz → KIRMIZI (iz "kaç acil durdurma gitti" diye yanlış okunmasın)."""
    k = _seans(o)
    if yol == "POST /delete":
        o.c.post("/api/history/delete", json={"session_id": k["sid"]}, headers=o.h)
        olay_turu = "history.delete"
    else:
        o.c.post(
            "/api/history/delete_bulk", json={"session_ids": [k["sid"]], "confirm": "DELETE_SELECTED"}, headers=o.h
        )
        olay_turu = "history.delete_bulk"
    iz = json.loads(o.tdb.denetim_oku(10, olay_turu)[0]["detail"] or "{}")
    assert iz.get("kritik_korunan") == 2 and iz.get("acil_durdurma") == 1, iz


def test_KARSIT_korunan_kritik_olay_saklama_silmesinde_de_KALIR(o):
    """Bağı kopan kritik olay (session_id NULL) süre dolsa da saklama silmesinden geçer (A-07 süresiz)."""
    k = _seans(o)
    o.c.post("/api/history/delete", json={"session_id": k["sid"]}, headers=o.h)
    with o.tdb._get_connection() as c:
        c.execute("UPDATE session_events SET created_at=? WHERE id=?", (time.time() - 4000 * 86400, k["estop"]))
        c.commit()
    o.tdb.purge_old_session_events(365)
    assert _olay(o, k["estop"]) is not None
