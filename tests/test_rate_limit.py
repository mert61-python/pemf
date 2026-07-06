"""Kritik yol (güvenlik B-1.6): uzak (tünel) istekler IP-başı sınırlı; LAN sınırsız;
acil-durdurma/health muaf (fail-safe). Limit modül-globali monkeypatch ile düşürülür."""
import os

os.environ.pop("PEMF_SIMULATE", None)

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def api():
    from servers import api_server
    return api_server


@pytest.fixture(scope="module")
def client(api):
    return TestClient(api.app)


def test_remote_rate_limited_after_threshold(client, api, monkeypatch):
    monkeypatch.setattr(api, "_RL_REMOTE_MAX", 5)
    api._rl_hits.clear()
    h = {"cf-connecting-ip": "203.0.113.10"}  # uzak istemci (proxy header → remote)
    codes = [client.get("/api/system/info", headers=h).status_code for _ in range(7)]
    assert codes[:5] == [200] * 5
    assert codes[5] == 429 and codes[6] == 429


def test_separate_ip_separate_bucket(client, api, monkeypatch):
    monkeypatch.setattr(api, "_RL_REMOTE_MAX", 3)
    api._rl_hits.clear()
    a = {"cf-connecting-ip": "203.0.113.20"}
    b = {"cf-connecting-ip": "203.0.113.21"}
    for _ in range(4):
        client.get("/api/system/info", headers=a)
    assert client.get("/api/system/info", headers=a).status_code == 429  # A limitli
    assert client.get("/api/system/info", headers=b).status_code == 200  # B ayrı kova


def test_emergency_stop_exempt_from_rate_limit(client, api, monkeypatch):
    monkeypatch.setattr(api, "_RL_REMOTE_MAX", 2)
    api._rl_hits.clear()
    h = {"cf-connecting-ip": "203.0.113.30"}
    codes = [client.post("/api/hardware/emergency_stop", headers=h).status_code for _ in range(5)]
    assert 429 not in codes  # acil-durdurma ASLA sınırlanmaz (fail-safe)


def test_health_exempt_from_rate_limit(client, api, monkeypatch):
    monkeypatch.setattr(api, "_RL_REMOTE_MAX", 2)
    api._rl_hits.clear()
    h = {"cf-connecting-ip": "203.0.113.40"}
    codes = [client.get("/api/health", headers=h).status_code for _ in range(5)]
    assert 429 not in codes


def test_unresolvable_client_counted_failclosed(client, api, monkeypatch):
    """Belirsiz/çözülemeyen istemci (TestClient host'u IP değil, proxy header YOK) UZAK sayılır
    → fail-closed olarak sınırlanır. (Gerçek LAN muafiyeti is_local_request ile; TestClient bunu
    header'sız simüle edemez — LAN muafiyeti izole birim testinde doğrulandı.)"""
    monkeypatch.setattr(api, "_RL_REMOTE_MAX", 2)
    api._rl_hits.clear()
    codes = [client.get("/api/system/info").status_code for _ in range(3)]
    assert codes[2] == 429  # header yoksa da fail-closed sayım (remote kabul)
