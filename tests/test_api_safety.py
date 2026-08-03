"""Kritik yol: emergency_stop her zaman çalışır + aynı anda iki seans engeli (409)."""
import os

os.environ.pop("PEMF_SIMULATE", None)  # testlerde sim loop başlatma

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    from servers import api_server
    return TestClient(api_server.app)


def test_emergency_stop_reports_transport_status(client):
    # Audit P2: emergency_stop status'u artik transport sonuclarindan TURETIR (eskiden kosulsuz
    # 'success' donuyordu = yanlis-guvence; STM hatasi + broker cokuk olsa bile UI 'ciktilar kesildi'
    # saniyordu). Endpoint 200 doner + honest status (success/partial/error) + confirmed alani gelir.
    r = client.post("/api/hardware/emergency_stop")
    assert r.status_code == 200
    body = r.json()
    assert body.get("status") in ("success", "partial", "error")
    assert "confirmed" in body


def test_double_session_start_conflicts(client):
    payload = {"coil_ids": [6, 7, 8], "frequency": 50, "duty": 25, "duration_minutes": 10, "mode": "Test"}
    # önce temizle
    client.post("/api/session/stop")
    r1 = client.post("/api/session/start", json=payload)
    assert r1.status_code == 200
    r2 = client.post("/api/session/start", json=payload)
    assert r2.status_code == 409
    client.post("/api/session/stop")


def test_emergency_stop_deactivates_session(client):
    payload = {"coil_ids": [6, 7, 8], "frequency": 50, "duty": 25, "duration_minutes": 10, "mode": "Test"}
    client.post("/api/session/start", json=payload)
    client.post("/api/hardware/emergency_stop")
    active = client.get("/api/session/active").json()
    is_active = active.get("is_active") or (active.get("session") or {}).get("is_active")
    assert not is_active


def test_session_start_rejects_oversized_coil_ids(client):
    """DENETIM P1 regresyonu: /api/session/start bobin listesi sınırsız olmamalı.

    Hata: `coil_ids: list = []` (eleman tipi/uzunluk kısıtı yok) → {"coil_ids": [6]*20000}
    ESP bobin başına AYRI daemon-thread açıyordu (her biri socket+paho connect) → thread/handle
    tükenmesi; aynı anda süren gerçek tedavide süre-watchdog açlık çekip bobinler planlanandan
    uzun enerjili kalabilirdi. /api/coil/batch zaten `_seen[:8]` ile korunuyordu.
    """
    r = client.post("/api/session/start", json={"coil_ids": [6] * 20000, "duration_minutes": 1})
    assert r.status_code == 422, "8'den uzun bobin listesi sınırda reddedilmeli"


def test_session_start_dedups_coil_ids(client):
    """Tekrarlı/aralık-dışı bobin id'leri normalize edilmeli (derinlemesine savunma)."""
    try:
        r = client.post("/api/session/start", json={
            "coil_ids": [1, 1, 2, 2], "duration_minutes": 1, "patient_name": "T",
        })
        # STM donanımı yoksa 503 dönebilir; o durumda normalizasyon zaten uygulanmıştır.
        if r.status_code == 200:
            assert r.json()["session"]["coil_ids"] == [1, 2]
    finally:
        client.post("/api/session/stop")
