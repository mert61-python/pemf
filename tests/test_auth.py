"""Kritik yol: PEMF_REQUIRE_AUTH=1 iken token zorunlu; emergency_stop/health MUAF (fail-safe)."""
from fastapi.testclient import TestClient


def _reset_auth_cache():
    import servers.auth as auth
    auth._require = None
    auth._token = None
    auth._warned = False


def test_auth_enforced(monkeypatch):
    monkeypatch.setenv("PEMF_REQUIRE_AUTH", "1")
    monkeypatch.setenv("PEMF_API_TOKEN", "secret-test-token")
    _reset_auth_cache()
    from servers import api_server
    client = TestClient(api_server.app)
    try:
        # MUAF (fail-safe / keşif) — token'sız erişilebilir
        assert client.get("/api/health").status_code == 200
        assert client.post("/api/hardware/emergency_stop").status_code == 200
        # KORUMALI — token'sız 401
        assert client.get("/api/patients").status_code == 401
        # Doğru token ile 401 DEĞİL
        r = client.get("/api/patients", headers={"X-API-Key": "secret-test-token"})
        assert r.status_code != 401
        # Yanlış token → 401
        assert client.get("/api/patients", headers={"X-API-Key": "wrong"}).status_code == 401
    finally:
        _reset_auth_cache()  # diğer testleri etkileme


def test_auth_disabled_by_default(monkeypatch):
    monkeypatch.delenv("PEMF_REQUIRE_AUTH", raising=False)
    _reset_auth_cache()
    from servers import api_server
    client = TestClient(api_server.app)
    try:
        # Auth kapalı → korumalı endpoint token'sız erişilebilir (geriye uyumlu)
        assert client.get("/api/patients").status_code != 401
    finally:
        _reset_auth_cache()
