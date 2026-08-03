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


def test_non_ascii_code_does_not_500_and_counts_against_throttle():
    """DENETIM P3 regresyonu: ASCII-dışı kod 500 vermemeli ve throttle'ı ATLAMAMALI.

    Hata: secrets.compare_digest STR argümanlarda yalnız ASCII kabul eder; kullanıcı
    kontrolündeki kod alanına Türkçe harf/emoji konunca TypeError fırlıyor, istisna handler'ın
    DIŞINDA kaldığı için (1) 403 yerine 500 dönüyor, (2) başarısız deneme throttle'a hiç
    yazılmıyordu → saldırgan ASCII-dışı bayt ekleyerek kaba-kuvvet sayacını tamamen atlıyordu.
    """
    from fastapi.testclient import TestClient

    from servers import api_server, auth_router

    # Yardımcının kendisi: ASCII-dışı girdide çökmemeli, False dönmeli
    assert auth_router._safe_compare("ŞİFRE-Ğ", "ŞİFRE-Ğ") is True, "eşit değerler eşleşmeli"
    assert auth_router._safe_compare("ŞİFRE-Ğ", "başka") is False
    assert auth_router._safe_compare("kod", None) is False

    c = TestClient(api_server.app)
    r = c.post("/api/auth/exchange", json={"code": "ĞÜŞİÖÇ"})
    assert r.status_code != 500, "ASCII-dışı kod 500 üretmemeli"
    assert r.status_code in (403, 429), f"beklenen 403/429, gelen {r.status_code}"


def test_reset_throttle_is_per_ip_not_global():
    """DENETIM P3 regresyonu: şifre-sıfırlama throttle'ı GLOBAL olmamalı.

    Hata: tek bir süreç-geneli kova → kimliksiz uzak bir saldırgan arka arkaya yanlış yönetici
    kodu göndererek 'Şifremi unuttum' akışını TÜM operatörler için süresiz kilitleyebiliyordu
    (kimse giriş yapamazken kimse şifre de sıfırlayamaz).
    """
    from servers import auth_router as ar

    assert isinstance(ar._reset_throttle_by_ip, dict), "IP-başına kova olmalı"
    b1 = ar._reset_bucket("10.0.0.1")
    b2 = ar._reset_bucket("10.0.0.2")
    assert b1 is not b2, "farklı IP'ler ayrı kova almalı"
    # Global kova yalnız ARKA-DURAK: eşiği IP-başına eşikten çok daha geniş olmalı
    assert ar._RESET_GLOBAL_MAX_FAILS > ar._THROTTLE_MAX_FAILS * 5
