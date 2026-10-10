# Author: mertaygn, cglrgrkn
"""Cihaz-yerel API token doğrulama (P0 #1: kimliksiz donanım/hasta API'si).

Token kaynağı: env PEMF_API_TOKEN, yoksa app_data/api_token.txt (yoksa otomatik üretilir).
Zorlama: PEMF_REQUIRE_AUTH=1 ise ZORUNLU; değilse KAPALI (prominent uyarı loglanır → üretimde aç).
İstemci: HTTP 'X-API-Key' header veya '?token=' query; WebSocket '?token=' query.

emergency_stop + health + discovery + statik (simulator) MUAFTIR (fail-safe / keşif).
"""

import contextvars
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
            # ⚠️ A-10 (2-E incelemesi): + süreci çalıştıran hesap (`keep_current_user=True`). Eskiden yükseltilmemiş süreç (Kural 2,
            # başlatıcı backend'i) yeniden başlayınca kendi dosyasını OKUYAMIYOR, her açılışta yeni token üretiyordu (ölçüldü). Users yine
            # ERİŞEMEZ. Kapı: tests/test_api_token_YEDEK_yolu_KENDINI_kilitlemez_A10.py
            try:
                from utils.file_acl import lock_down_file

                lock_down_file(f, keep_current_user=True)
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


def cihazin_kendisinden_mi(request) -> bool:
    """İstek cihazın KENDİSİNDEN mi (127.0.0.1 / ::1; tünel ve ters-proxy SAYILMAZ)? Token KABUL EDİLMEZ.

    `is_privileged_request`ten DAHA SIKI (D2.11 · sahip kararı A-03): kliniğin TAMAMINI silmek gibi işlemleri telefon ya
    da ağdaki başka bir cihaz — geçerli cihaz token'ıyla da — yapamaz. Hata halinde FAIL-CLOSED (False)."""
    try:
        h = request.headers
        via_proxy = bool(h.get("cf-connecting-ip") or h.get("cf-ray") or h.get("x-forwarded-for"))
        host = request.client.host if request.client else ""
        return is_loopback_request(host, via_proxy)
    except Exception:
        logger.exception("cihaz-kendisi denetimi hatasi → REDDEDILDI (fail-closed)")
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
#   ⚠️ Y109 (sahip kararı, 2-B incelemesi B2-2.2): (2) HARFİYEN — cihazda kayıtlı operatör VARSA jetonsuz HER beyan
#      (kayıtlı olmayan, paylaşılan giriş e-postası, görünmez karakterle kayıtlı adrese GÖRSEL EŞ) kanıtsızdır → boş.
#      Eskiden yalnız (3) uygulanıyordu: kayıtsız beyan değerlendirmeyi imzalıyor (Y88 baypası), hasta/AI/seans sahibi
#      oluyor, tünelden anonim AI Pro mührü ekranda bir hekimin adresi gibi görünen dizeyle basılıyordu.
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


# ⚠️ Y113 (S-B2.5, 2-B incelemesi): kimlik (auth) veritabanı OKUNAMAZKEN kimlik kapıları KAPALI kalır (B2-1.1) — ama ileti
# "Operatör seçin" DEMEZ: seçilecek operatör listesi de okunamıyor, operatörsüz klinikte seçilecek kimse yok; operatör yanlış
# eyleme yönlendiriliyordu. 428 iletisi, günlük ve arayüz ARIZAYI ve ÇAREYİ söyler. Tek kaynak bu metin (arayüz ikizi:
# apps/ui/src/utils/patientScope.ts `KIMLIK_DB_OKUNAMIYOR`). ACİL DURDUR ve STOP kimlik DB'si okumaz (B2B2-1 ölçümü).
# Kapı: tests/test_kimlik_DB_okunamazken_ileti_ARIZA_ve_CARE_Y113.py
KIMLIK_DB_OKUNAMIYOR = (
    "Cihazın kimlik veritabanı okunamıyor — kayıtların hangi hekime ait olduğu doğrulanamıyor; değerlendirme, silme ve "
    "kimlik isteyen kayıt işlemleri şimdilik yapılamaz. Çare: uygulamayı kapatıp yeniden açın; sorun sürerse veri "
    "klasöründeki auth_users.db dosyasının erişim iznini ve diski teknik desteğe denetletin. ACİL DURDUR ve STOP etkilenmez."
)
# Bu istekte (bağlam) kimlik DB'si okunabildi mi — kimlik kararları yazar, `kimliksiz_detayi` okur (ikinci bir okuma yapılmaz:
# kilitte her okuma döngüyü ~0,8 sn tutar, B2B2-1). İstek görevleri bağlamı kopyalar → istekler arası SIZMAZ.
_KIMLIK_DB_ARIZASI: contextvars.ContextVar = contextvars.ContextVar("kimlik_db_arizasi", default=None)


def _kimlik_db_yolu() -> str:
    try:
        from database.auth_db import _auth_db

        return str(_auth_db.db_path) if _auth_db is not None else "?"
    except Exception:
        return "?"


def _kimlik_db_arizasi_bildir(ne: str) -> None:
    """Kimlik DB arızasını günlüğe ARIZA + ÇARE olarak yazar ve bu isteğin bağlamında işaretler (`kimliksiz_detayi` okur)."""
    _KIMLIK_DB_ARIZASI.set(True)
    logger.exception("%s [%s — FAIL-CLOSED; dosya: %s]", KIMLIK_DB_OKUNAMIYOR, ne, _kimlik_db_yolu())


def kimlik_db_okunamiyor() -> bool:
    """Bu istekte kimlik DB'si okunamadı mı? Bağlamda karar yoksa bir katı okuma dener. ASLA istisna atmaz."""
    d = _KIMLIK_DB_ARIZASI.get()
    if d is not None:
        return d
    try:
        from database.auth_db import get_auth_db

        get_auth_db().list_operators(kati=True)
        return False
    except Exception:
        return True


def kimliksiz_detayi(varsayilan: str) -> str:
    """Kimliksiz istek reddinin (428) iletisi: kimlik DB'si okunamıyorsa ARIZA + ÇARE (Y113), değilse `varsayilan`
    ("Operatör seçin — …")."""
    return KIMLIK_DB_OKUNAMIYOR if kimlik_db_okunamiyor() else varsayilan


def _kayitli_operator_mu(email: str) -> bool:
    """Bu e-posta cihazda kayıtlı bir operatöre mi ait? Hata halinde FAIL-CLOSED (True):
    bilemiyorsak kanıtsız beyanı kabul etmeyiz."""
    e = (email or "").strip().lower()
    if not e:
        return False
    try:
        from database.auth_db import get_auth_db

        # kati=True: AuthDB okuma hatasını YUTMAZ → aşağıdaki fail-closed dalı GERÇEK arızada da koşar (B2-1.1, 2-B incelemesi).
        sonuc = bool(get_auth_db().operator_exists(e, kati=True))
        _KIMLIK_DB_ARIZASI.set(False)
        return sonuc
    except Exception:
        _kimlik_db_arizasi_bildir("kanıtsız beyan REDDEDİLİYOR")
        return True


def kayitli_operator_var() -> bool:
    """Cihazda en az bir operatör KAYITLI mı? (Kural 2 ayrımı: kayıtlı operatörü olmayan tek hekimli klinik kilitlenmez.)
    Hata halinde FAIL-CLOSED (True): bilemiyorsak kimliksiz isteği operatörsüz klinik sanıp kabul etmeyiz. ASLA istisna
    atmaz."""
    try:
        from database.auth_db import get_auth_db

        sonuc = bool(get_auth_db().list_operators(kati=True))  # kati: yutulan hata fail-OPEN oluyordu (B2-1.1)
        _KIMLIK_DB_ARIZASI.set(False)
        return sonuc
    except Exception:
        _kimlik_db_arizasi_bildir("kimliksiz istek REDDEDİLİYOR")
        return True


def kayitli_operator_epostalari():
    """Cihazda kayıtlı operatörlerin e-postaları (küçük harf, kırpılmış) — `frozenset()` = operatörsüz klinik (Kural 2).
    Okunamazsa `None` (çağıran FAIL-CLOSED davranır: kimin kayıtlı olduğu bilinmiyor). ASLA istisna atmaz. (Y104)"""
    try:
        from database.auth_db import get_auth_db

        s = frozenset((o.get("email") or "").strip().lower() for o in get_auth_db().list_operators(kati=True))
        _KIMLIK_DB_ARIZASI.set(False)
        return s
    except Exception:
        _kimlik_db_arizasi_bildir("kayıtlı operatör listesi okunamadı — sahiplik fail-closed")
        return None


def _jeton_kimligi(request) -> str:
    """İsteğin JETON kimliği — istek başına BİR KEZ çözülür ve istek boyunca AYNI kalır (ASGI `scope`'ta; istekler arası SIZMAZ).

    ⚠️ C2-3.3 (2-C incelemesi A3): uçlar kimliği kapıda çözüp DB işlemine girer, başarı izini `audit_log.kimlikli_yaz` ile yazar —
    o kimliği YENİDEN çözüyordu; işlem sürerken (VACUUM'lu toplu silme) gelen "Kilitle" jetonu düşürünce Ayşe'nin yetkisiyle
    silinen kayıtların izi SAHİPSİZ kalıyordu (silinen kaydın tek kanıtı). İstekten ÖNCE iptal edilmiş jeton yine boş çözülür.
    Kapı: tests/test_silme_ve_not_BASARI_IZI_kilit_yarisinda_YETKILENDIREN_hekim_C2_3_3.py"""
    from servers import operator_tokens

    kapsam = getattr(request, "scope", None)
    if isinstance(kapsam, dict) and "pemf_jeton_kimligi" in kapsam:
        return kapsam["pemf_jeton_kimligi"]
    e = operator_tokens.cozumle(_operator_jetonu(request)) or ""
    if isinstance(kapsam, dict):
        kapsam["pemf_jeton_kimligi"] = e
    return e


def cozumlenmis_operator(request, beyan: str = "") -> str:
    """Kaydın yazılacağı operatör e-postası. Yukarıdaki üç kurala göre; ASLA istisna atmaz."""
    try:
        jetonlu = _jeton_kimligi(request)
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
        # Y109: kural (2) harfiyen — kayıtlı operatörlü cihazda KAYITSIZ beyan (paylaşılan giriş, uydurma, görsel eş adres)
        # da kanıtsızdır. Kapı: tests/test_kayitli_cihazda_JETONSUZ_KAYITSIZ_beyan_SAHIPSIZ_Y109.py
        if kayitli_operator_var():
            logger.warning(
                "Operatör beyanı KANITSIZ (jeton yok) ve cihazda kayıtlı operatör var → kayıt SAHİPSİZ yazılıyor "
                "(beyan yalnız operatörsüz klinikte kabul edilir). İstemcinin PIN doğrulaması yapması gerekir."
            )
            return ""
        return e
    except Exception:
        logger.exception("operator cozumleme hatasi → SAHIPSIZ")
        return ""


def cozumlenmis_operator_adi(cozulen_email: str, beyan_ad: str = "") -> str:
    """Kayda yazılacak operatör ADI — e-postayla AYNI kurala bağlı (D2.41 · B-2.19).

    * E-posta cihazda KAYITLI bir operatöre aitse ad onun KAYITLI görünen adıdır (beyan yok sayılır).
    * E-posta çözüldü ama kayıtlı değilse beyan edilen ad YALNIZ cihazda kayıtlı operatör YOKSA (Kural 2) kabul edilir.
    * E-posta ÇÖZÜLMEDİYSE: cihazda kayıtlı operatör VARSA ad da YOK (kanıtsız beyan bir hekimin adını taşıyamaz — seans
      satırı ve `session_started` izi); kayıtlı operatör YOKSA (Kural 2: tek hekimli klinik, yalnız ad gönderen eski
      istemci) beyan edilen ad kabul edilir.
    Hata halinde FAIL-CLOSED: ad yazılmaz. ASLA istisna atmaz."""
    e = (cozulen_email or "").strip().lower()
    try:
        from database.auth_db import get_auth_db

        operatorler = get_auth_db().list_operators(kati=True)  # B2-1.1: arızada ad YAZILMAZ (aşağıdaki dal)
        _KIMLIK_DB_ARIZASI.set(False)
    except Exception:
        _kimlik_db_arizasi_bildir("operatör adı YAZILMIYOR")
        return ""
    if not e:
        return (beyan_ad or "").strip() if not operatorler else ""
    for op in operatorler:
        if (op.get("email") or "").strip().lower() == e:
            return (op.get("display_name") or "").strip() or e
    # ⚠️ B2-2.3: kayıtlı operatörlü cihazda kayıtsız (doğrulanmamış) e-postanın yanındaki ad da kanıtsızdır — kayıtlı bir hekimin
    # görünen adını ("Dr. Ayşe") seans satırına / `session_started` izine / CSV'ye taşıyamaz. Kural 2 (operatör yok) değişmez.
    return (beyan_ad or "").strip() if not operatorler else ""
