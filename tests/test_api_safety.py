"""Kritik yol: emergency_stop her zaman çalışır + aynı anda iki seans engeli (409)."""
import os

os.environ.pop("PEMF_SIMULATE", None)  # testlerde sim loop başlatma

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    from servers import api_server
    return TestClient(api_server.app)


def test_emergency_stop_always_succeeds(client):
    r = client.post("/api/hardware/emergency_stop")
    assert r.status_code == 200
    body = r.json()
    assert body.get("status") == "success"


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
