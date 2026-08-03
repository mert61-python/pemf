"""Cihaz-yerel API token doğrulama (P0 #1: kimliksiz donanım/hasta API'si).

Token kaynağı: env PEMF_API_TOKEN, yoksa app_data/api_token.txt (yoksa otomatik üretilir).
Zorlama: PEMF_REQUIRE_AUTH=1 ise ZORUNLU; değilse KAPALI (prominent uyarı loglanır → üretimde aç).
İstemci: HTTP 'X-API-Key' header veya '?token=' query; WebSocket '?token=' query.

emergency_stop + health + discovery + statik (simulator) MUAFTIR (fail-safe / keşif).
"""
import ipaddress
import logging
import os
import secrets
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

_token = None
_require = None
_warned = False

# Auth GEREKMEYEN yollar (acil-durdur fail-safe + keşif + statik + dokümantasyon).
# /api/auth/exchange: 6-haneli kod→token takası UZAKTAN (tünel) erişilebilmeli; kodun KENDİSİ
# kimlik olduğundan token-muaf (handler throttle + compare_digest ile korur). [[temassız pairing]]
# /api/ai/vision + /api/ai/disease: FOTO/TEŞHİS analizi HERKESE açık (kimlik istemeden analiz).
# /api/ai/pro + /api/ai/ai_pro: otonom TEDAVİ (bobin sürer). Cihaz SAHİBİNİN AÇIK talebiyle
# (2026-07-01) uzaktan KİMLİKSİZ başlat/durdur için muaf edildi — sahibi riski bilerek kabul etti.
# RİSK: tünel URL'sini bilen HERKES tedavi başlatıp durdurabilir. GERİ ALMAK için bu iki öneki
# ("/api/ai/pro","/api/ai/ai_pro") listeden çıkarın. (Acil-durdur zaten _EXEMPT_EXACT'te fail-safe.)
_EXEMPT_PREFIXES = ("/api/health", "/api/discovery", "/api/auth/exchange",
                    "/api/auth/register", "/api/auth/login", "/api/auth/reset",  # operatör kayıt/giriş/şifre-sıfırlama (kullanıcı-katmanı; reset YÖNETİCİ-koduyla self-gate)
                    "/api/ai/vision", "/api/ai/disease", "/api/ai/rna", "/api/ai/sound",
                    "/api/ai/pro", "/api/ai/ai_pro",
                    "/favicon", "/simulator", "/static", "/docs", "/openapi", "/redoc")
_EXEMPT_EXACT = ("/api/hardware/emergency_stop",)


def _token_file() -> Path:
    # PEMF_DATA_DIR set ise onu kullan → DB + SQLCipher key ile AYNI erişilebilir dizin (ProgramData).
    # Aksi halde LocalSystem servisinde APPDATA = ...\systemprofile\... (operatöre GÖRÜNMEZ) → token
    # bulunamaz, web/mobil "eksik API anahtarı" der. (get_app_data_directory ile tutarlı.)
    # get_app_data_directory'yi ÇAĞIR (elle taklit etme): PEMF_DATA_DIR override'ı + üç
    # platformun kanonik dizinini tek yerde çözer. Eskiden buradaki `APPDATA or ~/.config`
    # dalı yalnız Windows'ta doğruydu; macOS/Linux'ta token ~/.config/PEMF_GUI'ye düşerken
    # DB + SQLCipher anahtarı ~/Library/Application Support (mac) veya ~/.local/share
    # (Linux) altında kalıyordu → yorumun vaat ettiği tutarlılık yeni platformlarda YOKTU.
    # secrets_manager._data_dir() ile birebir aynı desen (import-hatasında yerel yedek).
    try:
        from utils.path_utils import get_app_data_directory
        base = get_app_data_directory()
    except Exception:
        override = os.getenv("PEMF_DATA_DIR", "").strip()
        if override:
            base = Path(override) / "PEMF_GUI"
        elif sys.platform == "win32":
            base = Path(os.getenv("APPDATA") or (Path.home() / "AppData" / "Roaming")) / "PEMF_GUI"
        elif sys.platform == "darwin":
            base = Path.home() / "Library" / "Application Support" / "PEMF_GUI"
        else:
            base = Path.home() / ".local" / "share" / "PEMF_GUI"
    try:
        base.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return base / "api_token.txt"


def get_api_token() -> str:
    global _token
    if _token:
        return _token
    # DENETIM P3: ACIK ENV OVERRIDE ONCE. Docstring "Token kaynagi: env PEMF_API_TOKEN, yoksa
    # dosya" diyor ama uygulama once SecretsManager'a bakiyordu; SecretsManager env'i yalnizca
    # LEGACY-MIGRATE kaynagi olarak kullanir → anahtar bir kez pemf_secrets.json'a yazildiktan
    # sonra operatorun deploy/device.env ile verdigi PEMF_API_TOKEN SESSIZCE YOK SAYILIYORDU
    # (token dondurmek/istemcilere sabit token dagitmak imkansizlasir). Bu, sir dosyasi
    # kalicilasmadigi surece gorunmuyordu; .tmp tikanmasi duzelince yuzeye cikti.
    _env_tok = os.getenv("PEMF_API_TOKEN", "").strip()
    if _env_tok:
        _token = _env_tok
        return _token
    # TEK-DOSYA: SecretsManager (eski api_token.txt → üret; pemf_secrets.json'da saklar).
    try:
        from utils.secrets_manager import get_secret
        _token = get_secret("api_token")
        if _token:
            return _token
    except Exception as e:
        logger.error("SecretsManager api_token okunamadı, eski yola düşülüyor: %s", e)
    # FALLBACK (SecretsManager yok/hata) — eski davranış, geçiş güvenliği
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
            # NTFS ACL kilidi (audit B-1.2): API token dosyası yalnız SYSTEM + Administrators'a açık.
            try:
                from utils.file_acl import lock_down_file
                lock_down_file(f)
            except Exception:
                pass
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
        # FAIL-CLOSED: auth zorunluyken token BOŞ ise (SecretsManager/ProgramData hatası) herkesi
        # geçirmek = internete KİMLİKSİZ açık. Reddet + yüksek-sesle logla. (Audit P1 fail-OPEN deliği;
        # check_token yalnız 'required' iken çağrılır → boş-token = yanlış-yapılandırma → erişim YOK.)
        logger.error("API token BOŞ ama auth zorunlu → erişim REDDEDİLDİ (fail-closed). "
                     "SecretsManager / ProgramData izinlerini kontrol edin.")
        return False
    return bool(provided) and secrets.compare_digest(str(provided), str(expected))


_TRUSTED_NETS = None


def _trusted_nets():
    global _TRUSTED_NETS
    if _TRUSTED_NETS is None:
        _TRUSTED_NETS = []
        for c in ("127.0.0.0/8", "::1/128", "10.0.0.0/8", "172.16.0.0/12",
                  "192.168.0.0/16", "169.254.0.0/16", "fc00::/7"):
            try:
                _TRUSTED_NETS.append(ipaddress.ip_network(c))
            except Exception:
                pass
    return _TRUSTED_NETS


_TRUSTED_PROXIES = None


def _trusted_proxies():
    """DENETIM P0: BEYAN EDILMIS ters-proxy adresleri (PEMF_TRUSTED_PROXIES, virgullu IP/CIDR).

    Yerel/uzak karari yalnizca soket kaynak-IP'sine + proxy BASLIKLARINA dayaniyordu. Basligi
    EKLEMEYEN bir ters-proxy (repo'nun kendi docker/nginx'i boyleydi) arkasinda proxy'nin
    konteyner IP'si 172.16.0.0/12'ye dustugu icin INTERNETTEN gelen her istek "LAN" sayilip
    auth-muaf oluyordu — PEMF_REQUIRE_AUTH=1 olsa bile. Buraya yazilan adresten gelen istek
    ASLA yerel sayilmaz (fail-closed), basliklar olmasa bile. Varsayilan BOS = davranis degismez.
    """
    global _TRUSTED_PROXIES
    if _TRUSTED_PROXIES is None:
        _TRUSTED_PROXIES = []
        for c in (os.getenv("PEMF_TRUSTED_PROXIES", "") or "").split(","):
            c = c.strip()
            if not c:
                continue
            try:
                _TRUSTED_PROXIES.append(ipaddress.ip_network(c, strict=False))
            except Exception:
                logger.warning("PEMF_TRUSTED_PROXIES gecersiz deger yok sayildi: %s", c)
    return _TRUSTED_PROXIES


def is_local_request(client_host, via_proxy: bool = False) -> bool:
    """Yerel/LAN isteği mi → auth MUAF. Tünel/uzak (Cloudflare) ise token ZORUNLU.

    Masaüstü kısayolu (localhost:8000) ve aynı-WiFi (LAN, 192.168/10/172.16) istekleri
    token GEREKTİRMEZ (güvenli yerel ağ — operatörü 'eksik API anahtarı' ile uğraştırmaz).
    Cloudflare tünelinden gelen istek CF-Connecting-IP / CF-Ray / X-Forwarded-For taşır →
    UZAK kabul edilir → token istenir. cloudflared 127.0.0.1'den bağlandığından yalnız kaynak-IP
    yetmez; proxy-header de kontrol edilir. Belirsizse FAIL-CLOSED (token iste)."""
    try:
        if via_proxy:
            return False
        ip = ipaddress.ip_address(str(client_host or "").strip())
        # Beyan edilmis proxy'den geliyorsa (baslik olmasa bile) UZAK kabul et → token iste.
        if any(ip in net for net in _trusted_proxies()):
            return False
        return any(ip in net for net in _trusted_nets())
    except Exception:
        return False
