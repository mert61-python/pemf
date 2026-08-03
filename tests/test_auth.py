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


def test_trusted_proxy_address_is_never_local(monkeypatch):
    """DENETIM P0 regresyonu: beyan edilmiş ters-proxy adresinden gelen istek LAN sayılmamalı.

    Hata: karar yalnız soket kaynak-IP'si + proxy başlıklarına dayanıyordu. Başlık EKLEMEYEN bir
    ters-proxy (repo'nun kendi docker/nginx'i böyleydi) arkasında proxy'nin konteyner IP'si
    172.16.0.0/12'ye düştüğü için internetten gelen HER istek 'LAN' sayılıp auth-muaf oluyordu —
    PEMF_REQUIRE_AUTH=1 verilse bile (/api/auth/token kalıcı cihaz anahtarını döndürür).
    """
    from servers import auth

    monkeypatch.setattr(auth, "_TRUSTED_PROXIES", None)  # cache'i sıfırla
    monkeypatch.setenv("PEMF_TRUSTED_PROXIES", "172.18.0.0/16")

    # Beyan edilen proxy aralığı → başlık olmasa bile UZAK
    assert auth.is_local_request("172.18.0.7", via_proxy=False) is False
    # Beyan dışındaki gerçek LAN adresleri etkilenmez
    assert auth.is_local_request("192.168.1.50", via_proxy=False) is True
    assert auth.is_local_request("127.0.0.1", via_proxy=False) is True
    # Proxy başlığı varsa zaten uzak
    assert auth.is_local_request("192.168.1.50", via_proxy=True) is False

    monkeypatch.setattr(auth, "_TRUSTED_PROXIES", None)  # sonraki testler için temizle


def test_trusted_proxies_default_empty_keeps_lan_exemption(monkeypatch):
    """Varsayılan BOŞ → mevcut LAN muafiyeti davranışı DEĞİŞMEZ (geriye uyumluluk)."""
    from servers import auth

    monkeypatch.setattr(auth, "_TRUSTED_PROXIES", None)
    monkeypatch.delenv("PEMF_TRUSTED_PROXIES", raising=False)
    assert auth.is_local_request("172.18.0.7", via_proxy=False) is True
    monkeypatch.setattr(auth, "_TRUSTED_PROXIES", None)


def test_auth_endpoints_do_not_block_event_loop(temp_app_data):
    """DENETIM P1 regresyonu: PBKDF2 (200k tur) event-loop'ta çalışmamalı.

    Hata: /register, /login ve /reset async uçlarken auth_db'yi SENKRON çağırıyordu; kimliksiz
    bir istemci arka arkaya istek atarak tek-thread'li loop'u CPU'ya boğup TÜM API'yi (WS
    yayınları + seans uçları dahil) yanıt veremez hale getirebiliyordu.
    """
    import ast
    import inspect

    from servers import auth_router

    src = inspect.getsource(auth_router)
    tree = ast.parse(src)

    # Bloklayan auth_db çağrıları await'li olmalı (to_thread ile sarılı)
    blocking = {"register", "verify", "email_exists", "reset_password"}
    for node in ast.walk(tree):
        if not isinstance(node, ast.AsyncFunctionDef):
            continue
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute) \
                    and sub.func.attr in blocking:
                # Bu çağrı bir Await içinde mi? (to_thread(...) → await)
                parents = [p for p in ast.walk(node)
                           if isinstance(p, ast.Await) and sub in ast.walk(p)]
                assert parents, (
                    f"{node.name} içindeki bloklayan '{sub.func.attr}' çağrısı "
                    f"asyncio.to_thread ile await edilmeli"
                )
