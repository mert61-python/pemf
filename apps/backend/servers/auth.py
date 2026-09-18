# Author: mertaygn, cglrgrkn
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
_EXEMPT_PREFIXES = (
    "/api/health",
    "/api/discovery",
    "/api/auth/exchange",
    "/api/auth/register",
    "/api/auth/login",
    "/api/auth/reset",  # operatör kayıt/giriş/şifre-sıfırlama (kullanıcı-katmanı; reset YÖNETİCİ-koduyla self-gate)
    "/api/ai/vision",
    "/api/ai/disease",
    "/api/ai/rna",
    "/api/ai/sound",
    "/api/ai/pro",
    "/api/ai/ai_pro",
    "/favicon",
    "/simulator",
    "/static",
    "/docs",
    "/openapi",
    "/redoc",
)
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
        logger.error(
            "API token BOŞ ama auth zorunlu → erişim REDDEDİLDİ (fail-closed). "
            "SecretsManager / ProgramData izinlerini kontrol edin."
        )
        return False
    return bool(provided) and secrets.compare_digest(str(provided), str(expected))


_TRUSTED_NETS = None


def _trusted_nets():
    global _TRUSTED_NETS
    if _TRUSTED_NETS is None:
        _TRUSTED_NETS = []
        for c in (
            "127.0.0.0/8",
            "::1/128",
            "10.0.0.0/8",
            "172.16.0.0/12",
            "192.168.0.0/16",
            "169.254.0.0/16",
            "fc00::/7",
        ):
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


_LOOPBACK_BIND = None


def _loopback_only_bind() -> bool:
    """Backend YALNIZ loopback'e mi bağlanmış? (PEMF_API_HOST)

    DENETIM P0 (proxy-auth, `server` profili): backend loopback'e bağlıyken makineye
    DIŞARIDAN doğrudan bağlanmak imkânsızdır — 127.0.0.1'den gelen HER istek zorunlu
    olarak önündeki ters-proxy'den (IIS/Nginx/Caddy) gelir. Yani o durumda "loopback =
    yerel/güvenli" çıkarımı GEÇERSİZDİR.
    """
    global _LOOPBACK_BIND
    if _LOOPBACK_BIND is None:
        h = (os.getenv("PEMF_API_HOST", "0.0.0.0") or "").strip().strip("[]")
        if h.lower() == "localhost":
            _LOOPBACK_BIND = True
        else:
            try:
                _LOOPBACK_BIND = ipaddress.ip_address(h).is_loopback
            except Exception:
                _LOOPBACK_BIND = False
    return _LOOPBACK_BIND


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
        # DENETIM P0 (proxy-auth'un ters-proxy yarisi, `server` profili — Docker'a OZEL DEGIL):
        # deploy/server.env PEMF_API_HOST=127.0.0.1 + PEMF_REQUIRE_AUTH=1 ile public sunucu
        # kurar; TLS'i operatorun kendi IIS/Nginx/Caddy'si sonlandirir. Nginx `proxy_pass` ile
        # X-Forwarded-For'u KENDILIGINDEN EKLEMEZ (proxy_set_header gerekir) → via_proxy False
        # kalir, soket kaynak-IP'si 127.0.0.1 olur ve 127.0.0.0/8 _trusted_nets'te oldugu icin
        # INTERNETTEN gelen HER istek "yerel" sayilip auth-MUAF olurdu (PEMF_REQUIRE_AUTH=1
        # olmasina ragmen). Docker'daki esdegeri PEMF_TRUSTED_PROXIES ile kapatilmisti; bu yol
        # operatorun kendi proxy'sine bagli oldugundan env'e GUVENILEMEZ.
        # Loopback'e bagliyken disaridan dogrudan baglanti IMKANSIZ → loopback'ten gelen her
        # istek bir proxy'den gelir → "yerel" cikarimi gecersiz; fail-closed (token iste).
        # PEMF_API_HOST varsayilani 0.0.0.0 → klinik (device.env) ve launcher ETKILENMEZ.
        if ip.is_loopback and _loopback_only_bind() and require_auth():
            return False
        return any(ip in net for net in _trusted_nets())
    except Exception:
        return False


def is_loopback_request(client_host, via_proxy: bool = False) -> bool:
    """SIKI loopback denetimi: YALNIZ 127.0.0.1 / ::1 — LAN DEĞİL.

    NEDEN AYRI BİR FONKSİYON (2026-08-06, masaüstü oturum devri): `is_local_request` LAN'ı da
    "yerel" sayar (`_trusted_nets` 10/8, 172.16/12, 192.168/16, 169.254/16, fc00::/7 içerir).
    Masaüstü oturum ucu gövdesinde SUPABASE ACCESS TOKEN taşır; oradaki gevşeklik "kliniğin
    WiFi'sindeki HERHANGİ bir cihaz operatörün oturum token'ını okuyabilir" demek olurdu.
    E-özelliği sözleşmesi açıkça "SADECE 127.0.0.1/::1" diyor.

    `is_local_request`'e DOKUNULMADI (10+ çağıranı var: middleware, WS, ai_router, system_router,
    auth_router) — davranış değişikliği regresyon riski taşır; bu sıkı kural yalnız yeni uçlarda.

    Formül `servers/system_router.py`'deki launcher-nonce denetiminin aynısı: `_trusted_proxies()`
    ELEMESİ ŞART, çünkü cloudflared 127.0.0.1'DEN bağlanır → başlıksız bir tünel isteği aksi
    halde "loopback" görünürdü.
    """
    try:
        if via_proxy:
            return False
        ip = ipaddress.ip_address(str(client_host or "").strip())
        if any(ip in net for net in _trusted_proxies()):
            return False
        # DENETIM 2026-08-06: `is_local_request`'teki ters-proxy fail-closed'unun AYNISI, burada
        # DAHA DA gerekli — bu yardimci Supabase access/refresh token TASIYAN uclari korur.
        # deploy/server.env = PEMF_API_HOST=127.0.0.1 + PEMF_REQUIRE_AUTH=1: backend yalniz
        # loopback dinler, TLS'i operatorun IIS/Nginx'i sonlandirir ve `proxy_pass` XFF'i
        # KENDILIGINDEN EKLEMEZ → INTERNETTEN gelen istek soket-IP 127.0.0.1 + basliksiz gelir
        # ve bu fonksiyon onu "ayni bilgisayar" sayardi. Cihaz-token'i olan UZAK biri (ornegin
        # eslesmis bir telefon) masaustu oturumunu OKUYABILIR ya da KENDI oturumunu YERLESTIREBILIR
        # (oturum sabitleme). Loopback'e bagliyken disaridan dogrudan baglanmak IMKANSIZ oldugu
        # icin oradan gelen her istek bir proxy'dendir → "ayni bilgisayar" cikarimi GECERSIZ.
        # Klinik profili (device.env PEMF_API_HOST=0.0.0.0) ve launcher ETKILENMEZ.
        if ip.is_loopback and _loopback_only_bind() and require_auth():
            return False
        # Çift-yığın soket ::ffff:127.0.0.1 verebilir (aynı makine, meşru) → IPv4'e indir.
        mapped = getattr(ip, "ipv4_mapped", None)
        if mapped is not None:
            ip = mapped
        return str(ip) in ("127.0.0.1", "::1")
    except Exception:
        return False


# ════════════════════════════════════════════════════════════════════════════════════════
# AYRICALIKLI UÇLAR — LAN MUAFİYETİ YOK (2026-08-09 üretim-hazırlık denetimi, ENGEL)
#
# ARIZA: `is_local_request` LAN'ı (10/8, 172.16/12, 192.168/16) auth-MUAF sayar ve middleware
# bunu tüm uçlara uygular. Bu, "operatör yerel ağda token'la uğraşmasın" kolaylığı için bilinçli
# bir gevşemeydi ve sıradan uçlar (telemetri, kontrol) için savunulabilir. AMA 2026-08-08'de
# eklenen uçlar niteliksel olarak farklı: `/api/data/export` TÜM hasta + seans + AI geçmişini
# ÇAĞIRANIN SEÇTİĞİ parolayla tek dosyada dışarı verir; `/api/ai/log/delete_all` VACUUM'lu ve
# geri dönülemez siler; `/api/operators/enroll` bir hekimin kimliğini devralmaya izin verir.
# Bunlar LAN'a kimliksiz açıkken at-rest şifreleme HİÇBİR ŞEY korumaz — veriyi uygulamanın
# kendisi çözüp teslim eder. Klinik hotspot parolası da her makinede aynıdır (`pemf1234`) ve
# pakette dağıtılır → "güvenli yerel ağ" varsayımı bu uçlar için geçerli DEĞİLDİR.
#
# KURAL: loopback (cihazın KENDİSİ — fiziksel erişim zaten tam yetki demektir) VEYA geçerli
# cihaz token'ı. Mobil uygulama LAN'dayken token'ı `/api/auth/token`'dan zaten alıp saklar →
# meşru kullanım kırılmaz; token'sız rastgele bir LAN cihazı REDDEDİLİR.
# ════════════════════════════════════════════════════════════════════════════════════════


def _istek_tokeni(request) -> str:
    """İstekten cihaz token'ını çıkar — middleware ile AYNI kaynaklar (X-API-Key / ?token=)
    artı `Authorization: Bearer` (mobil istemci bazı yollarda onu kullanır)."""
    try:
        h = request.headers
        t = (h.get("X-API-Key") or "").strip()
        if not t:
            t = (request.query_params.get("token") or "").strip()
        if not t:
            auth = (h.get("authorization") or "").strip()
            if auth[:7].lower() == "bearer ":
                t = auth[7:].strip()
        return t
    except Exception:
        return ""


def is_privileged_request(request) -> bool:
    """Yıkıcı/PII ucu için yetki var mı? loopback VEYA geçerli token. LAN TEK BAŞINA YETMEZ."""
    try:
        h = request.headers
        via_proxy = bool(h.get("cf-connecting-ip") or h.get("cf-ray") or h.get("x-forwarded-for"))
        host = request.client.host if request.client else ""
        if is_loopback_request(host, via_proxy):
            return True
        t = _istek_tokeni(request)
        return bool(t) and check_token(t)
    except Exception:
        # FAIL-CLOSED: kararı veremiyorsak yetki YOK (bu uçlar tüm hasta verisine dokunur).
        logger.exception("ayricalikli istek denetimi hatasi → REDDEDILDI (fail-closed)")
        return False


def enforce_privileged(request) -> None:
    """`is_privileged_request` değilse 403 fırlatır. Yıkıcı/PII uçlarında İLK satır olmalı."""
    if is_privileged_request(request):
        return
    from fastapi import HTTPException

    raise HTTPException(
        status_code=403,
        detail="Bu işlem cihazın kendisinden ya da eşleştirilmiş bir istemciden yapılabilir. "
        "Yerel ağda olmak yeterli değildir.",
    )


# ══════════════════════════════════════════════════════════════════════════════════════════
# OPERATÖR KİMLİĞİ — kayıt kime yazılacak (2026-08-09 denetimi, Tier 1)
#
# `operator_email` her uçta İSTEMCİ BEYANIYDI: PIN doğrulaması (`/api/operators/verify`) ile
# sonraki yazmalar arasında hiçbir bağ yoktu. Cihaza erişebilen herkes başka bir hekimin adıyla
# seans başlatabilir, AI analizi ve hasta kaydı yazabilirdi — PBKDF2 + kilitlenme + PIN'in
# tamamı doğrulanmayan bir dize yüzünden anlamsız kalıyordu.
#
# YENİ KURAL:
#   1) İstek `X-PEMF-Operator` jetonu taşıyorsa → e-posta JETONDAN gelir (beyan YOK SAYILIR).
#   2) Jeton yoksa ve cihazda KAYITLI OPERATÖR YOKSA → beyan kabul edilir. Tek veterinerli
#      klinik ve eski istemciler bozulmaz; ortada taklit edilecek bir kimlik de yoktur.
#   3) Jeton yoksa ama beyan edilen e-posta KAYITLI BİR OPERATÖRE aitse → REDDEDİLİR (boş döner).
#      Kanıtsız olarak kayıtlı bir hekimin adına yazmak, korumanın delindiği tek durumdu.
#
# ⚠️ İşlemi DURDURMAZ, yalnız atfı düşürür. Seans başlatmayı 403'e çevirmek, hasta masadayken
# eski bir istemci yüzünden tedaviyi engellerdi; kaydın "sahipsiz" yazılması bundan iyidir.
# ══════════════════════════════════════════════════════════════════════════════════════════
OPERATOR_HEADER = "X-PEMF-Operator"


def _operator_jetonu(request) -> str:
    """İstekten operatör jetonunu çıkar (header ya da ?operator_token=)."""
    try:
        t = (request.headers.get(OPERATOR_HEADER) or "").strip()
        if t:
            return t
        return (request.query_params.get("operator_token") or "").strip()
    except Exception:
        return ""


def _kayitli_operator_mu(email: str) -> bool:
    """Bu e-posta cihazda kayıtlı bir operatöre mi ait? Hata halinde FAIL-CLOSED (True):
    bilemiyorsak kanıtsız beyanı kabul etmeyiz."""
    e = (email or "").strip().lower()
    if not e:
        return False
    try:
        from database.auth_db import get_auth_db

        return bool(get_auth_db().operator_exists(e))
    except Exception:
        logger.exception("operator varlik kontrolu basarisiz → beyan REDDEDILIYOR (fail-closed)")
        return True


def cozumlenmis_operator(request, beyan: str = "") -> str:
    """Kaydın yazılacağı operatör e-postası. Yukarıdaki üç kurala göre; ASLA istisna atmaz."""
    try:
        from servers import operator_tokens

        jetonlu = operator_tokens.cozumle(_operator_jetonu(request))
        if jetonlu:
            return jetonlu
        e = (beyan or "").strip().lower()
        if not e:
            return ""
        if _kayitli_operator_mu(e):
            logger.warning(
                "Operatör beyanı KANITSIZ (jeton yok) ve e-posta cihazda kayıtlı → kayıt "
                "SAHİPSİZ yazılıyor. İstemcinin PIN doğrulaması yapması gerekir."
            )
            return ""
        return e
    except Exception:
        logger.exception("operator cozumleme hatasi → SAHIPSIZ")
        return ""
