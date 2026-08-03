"""FAZ 1 güvenlik sertleştirmesi (production-readiness raporu):
- S-1: klasik güvenlik header'ları (nosniff / frame-options / referrer) + koşullu HSTS.
- E-1: hata yanıtlarında ham `str(e)` istemciye SIZMAZ (generic detail) — history_router.
Bu testler regresyon guard'ıdır (header'lar veya sızıntı-fix'i geri gelirse kırılır)."""
from fastapi.testclient import TestClient


def _client():
    from servers.api_server import app
    return app, TestClient(app)


def test_security_headers_present(temp_app_data):
    """S-1: her yanıtta nosniff / SAMEORIGIN / no-referrer bulunmalı."""
    _app, c = _client()
    r = c.get("/api/health")
    assert r.headers.get("X-Content-Type-Options") == "nosniff"
    assert r.headers.get("X-Frame-Options") == "SAMEORIGIN"
    assert r.headers.get("Referrer-Policy") == "no-referrer"


def test_hsts_only_behind_tls_proxy(temp_app_data):
    """S-1: HSTS yalnız TLS-proxy/tünel (x-forwarded-proto=https / CF) arkasından; LAN düz-HTTP'de YOK."""
    _app, c = _client()
    assert c.get("/api/health").headers.get("Strict-Transport-Security") is None
    r = c.get("/api/health", headers={"x-forwarded-proto": "https"})
    assert "max-age=" in (r.headers.get("Strict-Transport-Security") or "")


def test_history_500_does_not_leak_exception_text(temp_app_data):
    """E-1: history_router bir hata verirse istemciye ham exception metni (DB yolu/şema) SIZMAZ."""
    from servers import history_router
    app, c = _client()

    class _BoomDB:
        def get_statistics(self):
            raise RuntimeError("SECRET-DB-PATH C:/gizli/patients.db sema=treatment_sessions")

    app.dependency_overrides[history_router.get_db] = lambda: _BoomDB()
    try:
        r = c.get("/api/history/statistics")
        assert r.status_code == 500
        body = r.json()
        assert "SECRET-DB-PATH" not in str(body), "ham exception metni sızmamalı (bilgi ifşası)"
        assert body.get("detail") == "İşlem başarısız"
    finally:
        app.dependency_overrides.pop(history_router.get_db, None)


def test_request_id_generated_and_echoed(temp_app_data):
    """O-1: her yanıtta X-Request-ID üretilir; istemci gönderirse (güvenli-karakter) yankılanır."""
    _app, c = _client()
    rid = c.get("/api/health").headers.get("X-Request-ID")
    assert rid and len(rid) >= 8, "üretilen id"
    assert c.get("/api/health", headers={"X-Request-ID": "client-req-123"}).headers.get("X-Request-ID") == "client-req-123"
    # header/log-injection: güvensiz karakterler (boşluk/#/slash) SÜZÜLÜR
    got = c.get("/api/health", headers={"X-Request-ID": "a b#c/d"}).headers.get("X-Request-ID")
    assert got == "abcd"


def test_client_error_endpoint_never_5xx(temp_app_data):
    """F-7: ErrorBoundary crash raporu 200 döner (istemci akışını bozmaz); bozuk gövde de tolere edilir."""
    _app, c = _client()
    r = c.post("/api/client/error", json={"message": "boom", "stack": "at X\nat Y", "route": "control"})
    assert r.status_code == 200 and r.json().get("status") == "ok"
    assert c.post("/api/client/error", content=b"not-json").status_code == 200


def test_cors_default_blocks_internet_origin_allows_lan():
    """DENETIM P0 regresyonu: PEMF_CORS_ORIGINS AYARSIZ iken varsayılan '*' OLMAMALI.

    Hata: varsayılan '*' idi ve launcher (canlı dağıtım yolu) backend'i env'siz spawn ettiği için
    ACAO:* etkin kalıyordu → operatörün açtığı herhangi bir web sayfası /api/auth/token (kalıcı
    cihaz anahtarı) ve /api/patients (hasta PII) YANITLARINI okuyabiliyordu.
    """
    import os
    import re

    from servers import api_server

    # Modül-seviyesi yapılandırmayı doğrudan doğrula (importlib.reload kullanmıyoruz:
    # app'i yeniden kurmak test sırasına bağımlı yan etkiler üretir).
    if not os.getenv("PEMF_CORS_ORIGINS", "").strip():
        assert api_server._cors_kwargs.get("allow_origins") != ["*"], \
            "AYARSIZ varsayılan artık '*' olmamalı"
        assert api_server._cors_kwargs.get("allow_origin_regex"), \
            "varsayılan LAN/loopback regex'ine düşmeli"

    rx = re.compile(api_server._LAN_ORIGIN_REGEX)
    for allowed in ("http://localhost:8000", "http://127.0.0.1:8000",
                    "http://192.168.1.50:8000", "http://10.0.0.5:8000",
                    "http://172.16.3.4:8000", "http://pemf.local:8000"):
        assert rx.match(allowed), f"LAN kökeni engellenmemeli: {allowed}"
    for blocked in ("http://evil.example.com", "https://evil.example.com:8000",
                    "http://8.8.8.8:8000", "http://192.168.1.50.evil.com"):
        assert not rx.match(blocked), f"internet kökeni yetkilendirilmemeli: {blocked}"


def test_corrupt_secrets_file_is_not_silently_regenerated(tmp_path, monkeypatch):
    """DENETİM P0 regresyonu: bozuk pemf_secrets.json SESSİZCE yeni anahtarla değiştirilmemeli.

    Hata: _load() parse hatasında boş doküman dönüyordu; get_secret ardından eksik sqlcipher_key /
    patient_fernet_key'i ÜRETİP _save() ile dosyayı eziyordu → patients.db, tedavi geçmişi ve TÜM
    yedekler sonsuza dek çözülemez hale geliyordu. get_secret'teki brick-koruması yalnız
    "saklanmış ama çözülemiyor" halini kapsıyor, "dosya parse edilemiyor" hali korumayı atlıyordu.
    """
    import pytest

    from utils import secrets_manager as sm

    secrets_file = tmp_path / "pemf_secrets.json"
    secrets_file.write_text("{bozuk-json", encoding="utf-8")
    monkeypatch.setattr(sm, "secrets_path", lambda: secrets_file)
    monkeypatch.setattr(sm, "_cache", None)

    with pytest.raises(RuntimeError):
        sm._load()

    # Bozuk dosya EZİLMEMELİ; kanıt olarak saklanmalı.
    assert not secrets_file.exists(), "bozuk dosya .corrupt.<zaman> olarak taşınmalı"
    corrupt = list(tmp_path.glob("pemf_secrets.json.corrupt.*"))
    assert len(corrupt) == 1, "bozuk kopya kanıt olarak saklanmalı"
    assert corrupt[0].read_text(encoding="utf-8") == "{bozuk-json", "içerik korunmalı"
    monkeypatch.setattr(sm, "_cache", None)


def test_secrets_save_writes_file_when_not_admin(tmp_path, monkeypatch):
    """DENETİM P1 regresyonu: ACL kilidi os.replace'ten SONRA uygulanmalı.

    Hata: lock_down_file .tmp'ye ÖNCE uygulanıyordu; erişimi SYSTEM+Administrators'a kısıtladığı
    için yönetici OLMAYAN süreç (launcher kullanıcı-başına kurulum) kendi .tmp'si üzerindeki
    DELETE hakkını kaybedip os.replace'te PermissionError alıyordu → sırlar hiç kalıcılaşmıyor,
    geride okunamaz bir .tmp kalıyordu (sahada doğrulandı).
    """
    import utils.file_acl as facl
    from utils import secrets_manager as sm

    secrets_file = tmp_path / "pemf_secrets.json"
    monkeypatch.setattr(sm, "secrets_path", lambda: secrets_file)

    # GERÇEK arızayı taklit et: ACL kilidi BAŞARIYLA uygulanır (erişimi SYSTEM+Administrators'a
    # kısıtlar) ve BUNDAN SONRA yönetici olmayan süreç o dosyayı taşıyamaz hale gelir.
    locked = {"tmp": False}

    def _fake_lock(path):
        if str(path).endswith(".tmp"):
            locked["tmp"] = True
        return True

    _real_replace = sm.os.replace

    def _fake_replace(src, dst):
        if locked["tmp"]:
            raise PermissionError("kilitlenmiş .tmp taşınamaz (yönetici olmayan süreç)")
        return _real_replace(src, dst)

    monkeypatch.setattr(facl, "lock_down_file", _fake_lock)
    monkeypatch.setattr(sm.os, "replace", _fake_replace)

    sm._save({"auto": {"x": "1"}, "operator": {}, "embedded": {}})

    assert secrets_file.exists(), "sırlar kalıcılaşmalı (replace ACL'den ÖNCE olmalı)"
    assert not list(tmp_path.glob("*.tmp")), "yetim .tmp bırakılmamalı"
