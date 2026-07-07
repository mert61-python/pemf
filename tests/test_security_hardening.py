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
