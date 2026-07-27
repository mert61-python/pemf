"""Audit P1 (test-boşluğu): AI Pro OTONOM tedavi güvenlik kapakları (süre-clamp, organ-doğrulama)
davranışsal test edilmiyordu — yalnız route-varlığı. Uçlar kasıtlı auth-muaf olduğundan bu kapaklar
tek koruma; süre-clamp bir refactorda düşerse {duration_minutes:999999} gözetimsiz sürüş açar.
_ai_pro_loop no-op'lanır → kamera/donanım gerekmez."""
import os

os.environ.pop("PEMF_SIMULATE", None)

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    from servers import api_server
    return TestClient(api_server.app)


def test_ai_pro_duration_capped_to_clinical_max(client, monkeypatch):
    import servers.ai_router as air
    monkeypatch.setattr(air, "_ai_pro_loop", lambda: None)  # loop no-op → kamera/donanım yok
    try:
        r = client.post("/api/ai/pro/start", json={"organ_id": 0, "duration_minutes": 999999})
        assert r.status_code == 200
        # Audit P1: {duration_minutes:999999} klinik üst sınıra (120 dk) KAPANMALI
        assert r.json()["durationMin"] == air._AI_PRO_MAX_DURATION_MIN == 120
    finally:
        client.post("/api/ai/pro/stop")


def test_ai_pro_rejects_unsupported_organ(client):
    # Audit P2: em_kedi yalnız organ 0-6 tedavi eder; 7-10 sessiz-sıfır + yanlış 'aktif' göstergesi
    r = client.post("/api/ai/pro/start", json={"organ_id": 8, "duration_minutes": 20})
    assert r.status_code == 422
    r2 = client.post("/api/ai/pro/organ", json={"organ_id": 9, "duration_minutes": 20})
    assert r2.status_code == 422


def test_ai_pro_double_start_is_idempotent(client, monkeypatch):
    import servers.ai_router as air
    monkeypatch.setattr(air, "_ai_pro_loop", lambda: None)
    try:
        r1 = client.post("/api/ai/pro/start", json={"organ_id": 0, "duration_minutes": 20})
        assert r1.status_code == 200
        r2 = client.post("/api/ai/pro/start", json={"organ_id": 0, "duration_minutes": 20})
        assert r2.status_code == 200
        assert "running" in r2.json().get("message", "").lower()  # ikinci start yeni loop AÇMAZ
    finally:
        client.post("/api/ai/pro/stop")
