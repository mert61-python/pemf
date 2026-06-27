"""Cihaz-yerel API token doğrulama (P0 #1: kimliksiz donanım/hasta API'si).

Token kaynağı: env PEMF_API_TOKEN, yoksa app_data/api_token.txt (yoksa otomatik üretilir).
Zorlama: PEMF_REQUIRE_AUTH=1 ise ZORUNLU; değilse KAPALI (prominent uyarı loglanır → üretimde aç).
İstemci: HTTP 'X-API-Key' header veya '?token=' query; WebSocket '?token=' query.

emergency_stop + health + discovery + statik (simulator) MUAFTIR (fail-safe / keşif).
"""
import logging
import os
import secrets
from pathlib import Path

logger = logging.getLogger(__name__)

_token = None
_require = None
_warned = False

# Auth GEREKMEYEN yollar (acil-durdur fail-safe + keşif + statik + dokümantasyon).
_EXEMPT_PREFIXES = ("/api/health", "/api/discovery", "/favicon", "/simulator", "/static", "/docs", "/openapi", "/redoc")
_EXEMPT_EXACT = ("/api/hardware/emergency_stop",)


def _token_file() -> Path:
    base = Path(os.getenv("APPDATA") or (Path.home() / ".config")) / "PEMF_GUI"
    try:
        base.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return base / "api_token.txt"


def get_api_token() -> str:
    global _token
    if _token:
        return _token
    env = os.getenv("PEMF_API_TOKEN", "").strip()
    if env:
        _token = env
        return _token
    f = _token_file()
    try:
        if f.exists():
            _token = f.read_text(encoding="utf-8").strip()
        if not _token:
            _token = secrets.token_urlsafe(24)
            f.write_text(_token, encoding="utf-8")
            logger.info("Yeni cihaz-yerel API token üretildi: %s", f)
    except Exception:
        _token = _token or secrets.token_urlsafe(24)
    return _token


def require_auth() -> bool:
    global _require, _warned
    if _require is None:
        _require = os.getenv("PEMF_REQUIRE_AUTH", "0") == "1"
    if not _require and not _warned:
        _warned = True
        logger.warning(
            "API AUTH KAPALI: donanım/hasta/seans endpoint'leri KİMLİKSİZ erişilebilir. "
            "Üretimde PEMF_REQUIRE_AUTH=1 ayarlayın ve token'ı istemciye verin. token dosyası: %s",
            _token_file(),
        )
    return _require


def is_exempt(path: str) -> bool:
    if path in _EXEMPT_EXACT:
        return True
    return any(path.startswith(p) for p in _EXEMPT_PREFIXES)


def check_token(provided: str) -> bool:
    expected = get_api_token()
    if not expected:
        return True
    return bool(provided) and secrets.compare_digest(str(provided), str(expected))
