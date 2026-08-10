# Author: mertaygn, cglrgrkn
"""Auth uçları (refactor B1: api_server.py'den ayrıldı — modüler router).

Davranış BİREBİR korunur. TEMASSIZ uzaktan-erişim token akışı:
- GET  /api/auth/token    — YEREL/LAN istemcisine cihaz api_token'ı (uzak/tünel → 403).
- POST /api/auth/exchange — 6-haneli pairing kodunu token'la takas (tünelden de erişilir;
                            kod=kimlik, auth-exempt; kaba-kuvvete karşı throttle).

2026-08-06 eklendi — MASAÜSTÜ OTURUM DEVRİ (çift giriş yok):
- POST/GET/DELETE /api/auth/desktop-session — Tauri client'ın Supabase oturumunu backend'e
  devretmesi; uygulama onu alıp kendi giriş ekranını atlar. YALNIZ BELLEKTE + SADECE loopback.

api_server iç durumuna BAĞIMLI DEĞİL: yalnız `servers.auth` + `utils.secrets_manager`
fonksiyonları (fonksiyon-içi import, api_server'daki gibi). `_exchange_throttle` bu uca
özeldi → route ile birlikte taşındı (aliaslama gerekmez). Yollar/yanıtlar/gövde aynen korunur.
"""

import asyncio
import logging
import re as _re
import threading
import time as _time

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

router = APIRouter(tags=["auth"])


@router.get("/api/auth/token")
async def _get_auth_token(request: Request):
    """TEMASSIZ uzaktan-erişim: YEREL/LAN istemcisine cihazın api_token'ını verir. Mobil app aynı
    WiFi'deyken token'ı çeker + saklar → farklı ağda tünel üzerinden gönderir (X-API-Key / ?token=).
    UZAK (Cloudflare tünel) istek → 403: token YALNIZ yerel ağdan alınabilir = güvenli (operatör
    token girmez, vet-dostu). Auth alanı kaldırıldığından uzaktan auth aksi halde imkânsızdı."""
    try:
        from servers.auth import get_api_token, is_local_request

        _h = request.headers
        _via_proxy = bool(_h.get("cf-connecting-ip") or _h.get("cf-ray") or _h.get("x-forwarded-for"))
        if not is_local_request(request.client.host if request.client else "", _via_proxy):
            return Response(
                status_code=403,
                content='{"detail":"Token yalniz yerel agdan alinabilir"}',
                media_type="application/json",
            )
        return {"token": get_api_token()}
    except Exception:
        logging.exception("auth token endpoint hatasi")
        return Response(status_code=500, content='{"detail":"token alinamadi"}', media_type="application/json")


# ══════════════════════════════════════════════════════════════════════════════════════════
# MASAÜSTÜ OTURUM DEVRİ (E-özelliği, 2026-08-06) — ÇİFT GİRİŞ YOK
#
# Akış: Tauri client Supabase ile giriş yapar → oturumu buraya POST eder → web/mobil uygulama
# GET ile alır ve KENDİ giriş ekranını ATLAR. DELETE = çıkış.
#
# ⚠️ OTURUM YALNIZ BELLEKTE. Diske YAZILMAZ: `utils/secrets_manager.py` (pemf_secrets.json)
# KULLANILMAZ — o KALICI yazar ve Supabase access/refresh token'ı diske düşürmek, tokeni
# işletim-sistemi korumalı depoda tutan client tarafındaki kalıcılığı anlamsız kılardı.
# SONUÇ (KASITLI): backend yeniden başlarsa oturum KAYBOLUR; client açılışta yeniden devreder.
#
# ⚠️ SADECE 127.0.0.1/::1. `is_local_request` KULLANILMAZ — o LAN'ı da yerel sayar (bkz.
# servers/auth.py::is_loopback_request gerekçesi).
#
# ⚠️ Token'lar HİÇBİR seviyede loglanmaz (ne INFO ne DEBUG); hata yolunda `logging.exception`
# yerine sabit kısa mesaj kullanılır — traceback istek gövdesini taşıyabilir.
#
# NOT: `servers/auth.py::_EXEMPT_PREFIXES`e KASITLI OLARAK EKLENMEDİ. Klinik profilinde
# (PEMF_API_HOST=0.0.0.0) loopback zaten middleware'de auth-muaf → launcher token'sız çalışır;
# sunucu profilinde (loopback-bind + REQUIRE_AUTH=1) cihaz-token istenmesi DOĞRU davranıştır.
# ══════════════════════════════════════════════════════════════════════════════════════════
_desktop_session: dict = {}
_desktop_lock = threading.Lock()

# Bellek hijyeni: yerel de olsa sınırsız gövde kalıcı bir bellek sızıntısı olurdu (backend
# aylarca ayakta kalan bir servis). Supabase JWT'si ~1-2 KB → 8 KB fazlasıyla yeterli.
_DESKTOP_MAX_FIELD = 8 * 1024

# CORS SIZINTISINA KARŞI (savunmanın ikinci katmanı): soket-IP loopback olsa bile istek
# KULLANICININ TARAYICISINDAN gelebilir. api_server.py varsayılan `_LAN_ORIGIN_REGEX`
# 192.168/10/172.16/*.local kökenlerine ACAO veriyor → LAN'daki kötücül bir sayfa
# fetch('http://127.0.0.1:8000/api/auth/desktop-session') ile YANITI OKUYABİLİRDİ.
# Origin YOKSA geç (Tauri/reqwest yerel istemci başlık göndermez); VARSA yalnız loopback kökeni.
_LOOPBACK_ORIGIN_RE = _re.compile(
    r"^https?://(localhost|127\.\d{1,3}\.\d{1,3}\.\d{1,3}|\[::1\])(:\d+)?$", _re.IGNORECASE
)


def _desktop_403() -> Response:
    """HER çağrıda TAZE Response — tek bir modül-düzeyi nesneyi paylaşmak, ara katmanların
    (güvenlik başlıkları/CORS) aynı nesnenin başlıklarını istekler arası mutasyona uğratmasına
    yol açar. `_throttle_429()` ile aynı desen."""
    return Response(
        status_code=403,
        content='{"detail":"Masaustu oturumu yalniz bu bilgisayardan (127.0.0.1) yonetilebilir"}',
        media_type="application/json",
    )


def _desktop_forbidden(request: Request) -> bool:
    """Uç sıkı-loopback + Origin denetimini geçemiyorsa True (403 dönülmeli)."""
    _h = request.headers
    _via_proxy = bool(_h.get("cf-connecting-ip") or _h.get("cf-ray") or _h.get("x-forwarded-for"))
    from servers.auth import is_loopback_request

    if not is_loopback_request(request.client.host if request.client else "", _via_proxy):
        return True
    origin = (_h.get("origin") or "").strip()
    if origin and not _LOOPBACK_ORIGIN_RE.match(origin):
        return True
    return False


@router.post("/api/auth/desktop-session")
async def _set_desktop_session(request: Request):
    """Client → backend: Supabase oturumunu devret. Gövde: {access_token, refresh_token, email, expires_at}.

    Gövde pydantic MODELİYLE ALINMAZ: bir tip uyuşmazlığında (ör. Supabase `expires_at`'i sayı
    gönderir, model `str` beklerdi) FastAPI'nin 422'si GİRDİYİ yanıta geri yansıtır → token
    hem yanıt gövdesine hem de istemci loglarına sızardı. Elle çözülüp str'e zorlanıyor:
    doğrulama HİÇ patlamaz."""
    if _desktop_forbidden(request):
        return _desktop_403()
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}

    def _s(key: str) -> str:
        v = body.get(key)
        return "" if v is None else str(v)

    access = _s("access_token")
    if not access:
        return Response(status_code=422, content='{"detail":"access_token gerekli"}', media_type="application/json")
    exp = body.get("expires_at")
    exp_val = exp if isinstance(exp, (int, float)) and not isinstance(exp, bool) else _s("expires_at")
    oturum = {"access_token": access, "refresh_token": _s("refresh_token"), "email": _s("email"), "expires_at": exp_val}
    if any(isinstance(v, str) and len(v) > _DESKTOP_MAX_FIELD for v in oturum.values()):
        return Response(
            status_code=413, content='{"detail":"Oturum alanlari cok buyuk"}', media_type="application/json"
        )
    with _desktop_lock:
        _desktop_session.clear()
        _desktop_session.update(oturum)
    # Token DEĞİL, yalnız devrin GERÇEKLEŞTİĞİ loglanır (tanı için yeterli, sızıntı yok).
    logging.info("masaustu oturumu devralindi (e-posta var=%s)", bool(oturum["email"]))
    return {"ok": True}


@router.get("/api/auth/desktop-session")
async def _get_desktop_session(request: Request):
    """Uygulama → backend: devredilen oturumu al (yoksa {} + HTTP 200 → 'giriş ekranını göster')."""
    if _desktop_forbidden(request):
        return _desktop_403()
    with _desktop_lock:
        return dict(_desktop_session)


@router.delete("/api/auth/desktop-session")
async def _clear_desktop_session(request: Request):
    """Çıkış — idempotent (oturum yoksa da 200; client tekrar denemek zorunda kalmasın)."""
    if _desktop_forbidden(request):
        return _desktop_403()
    with _desktop_lock:
        _desktop_session.clear()
    return {"ok": True}


# Kod→token takas throttle (tek-cihaz, global; kaba-kuvvete karşı).
_exchange_throttle: dict = {}  # Audit P3: trusted-IP -> {"fails","until"} (eskiden GLOBAL kova → tek saldırgan herkesi kilitliyordu)

# ── SEC-2: login/reset kaba-kuvvet + PBKDF2-CPU-DoS throttle (exchange throttle deseninin eşi).
#    Login E-POSTA-BAŞINA (tarayan saldırgan meşru operatörü kilitlemesin); reset GLOBAL (admin-kod).
#    Not: oturum-token gerçek API-gate DEĞİL (cihaz-token gate'ler) → bu defense-in-depth + her login'in
#    200k-PBKDF2 CPU maliyetine karşı kimliksiz-DoS sınırı. LAN'da da uygulanır (kötücül LAN-sayfası vektörü). ──
_login_throttle: dict = {}  # email -> {"fails": int, "until": float}
# DENETIM P3: reset throttle'i TEK bir surec-geneli kovaydi → kimliksiz UZAK bir saldirgan
# arka arkaya yanlis yonetici kodu gondererek "Sifremi unuttum" akisini TUM operatorler icin
# suresiz kilitleyebiliyordu (hedefli DoS: kimse giris yapamazken kimse sifre de sifirlayamaz).
# Artik IP-BASINA kova birincil kilit; global kova YALNIZCA dagitik kaba-kuvvete karsi cok
# daha genis bir arka-durak olarak kalir (mesru operatoru hemen kilitlemez).
_reset_throttle = {"fails": 0, "until": 0.0}
_reset_throttle_by_ip: dict = {}  # ip -> {"fails": int, "until": float}
_RESET_GLOBAL_MAX_FAILS = 100  # arka-durak (IP-basina kilit birincil korumadir)
_THROTTLE_MAX_FAILS = 10
_THROTTLE_LOCK_SEC = 30.0


def _throttle_locked(bucket: dict) -> bool:
    return bucket.get("until", 0.0) > _time.time()


def _throttle_note_fail(bucket: dict) -> None:
    bucket["fails"] = bucket.get("fails", 0) + 1
    if bucket["fails"] >= _THROTTLE_MAX_FAILS:
        bucket["until"] = _time.time() + _THROTTLE_LOCK_SEC
        bucket["fails"] = 0


def _throttle_clear(bucket: dict) -> None:
    bucket["fails"] = 0
    bucket["until"] = 0.0


def _safe_compare(a: str, b: str) -> bool:
    """Sabit-zamanli karsilastirma — ASCII-DISI girdide COKMEZ.

    DENETIM P3: `secrets.compare_digest` STR argumanlarda yalnizca ASCII kabul eder; kullanici
    kontrolundeki kod/parola alanina Turkce harf ya da emoji konursa TypeError firlatiyordu.
    Istisna handler'in DISINDA kaldigi icin iki sonuc doguyordu: (1) 403 yerine 500, (2) basarisiz
    deneme throttle'a HIC yazilmiyor → saldirgan ASCII-disi bayt ekleyerek kaba-kuvvet sayacini
    tamamen atlayabiliyordu. Bayta cevirerek karsilastirmak ikisini de koker.
    """
    import hmac as _h  # modul-duzeyinde _sec YOK (fonksiyon-ici import ediliyor) → yerel al

    try:
        return _h.compare_digest(str(a).encode("utf-8", "surrogatepass"), str(b).encode("utf-8", "surrogatepass"))
    except Exception:
        return False


def _reset_bucket(ip: str) -> dict:
    """Sifre-sifirlama icin IP-basina throttle kovasi (bellek korumali)."""
    if len(_reset_throttle_by_ip) > 1000:
        now = _time.time()
        for k in [k for k, v in _reset_throttle_by_ip.items() if v.get("until", 0.0) < now]:
            _reset_throttle_by_ip.pop(k, None)
    return _reset_throttle_by_ip.setdefault(ip or "?", {"fails": 0, "until": 0.0})


def _login_bucket(email: str) -> dict:
    # Bellek koruması: çok e-posta birikirse (enumeration taraması) süresi-geçmiş kayıtları temizle.
    if len(_login_throttle) > 1000:
        now = _time.time()
        for k in [k for k, v in _login_throttle.items() if v.get("until", 0.0) < now]:
            _login_throttle.pop(k, None)
    return _login_throttle.setdefault(email, {"fails": 0, "until": 0.0})


def _exchange_bucket(ip: str) -> dict:
    # Audit P3: exchange throttle per-IP → tek saldırgan tüm kullanıcıları kilitleyemesin.
    if len(_exchange_throttle) > 1000:
        now = _time.time()
        for k in [k for k, v in _exchange_throttle.items() if v.get("until", 0.0) < now]:
            _exchange_throttle.pop(k, None)
    return _exchange_throttle.setdefault(ip or "unknown", {"fails": 0, "until": 0.0})


def _throttle_429() -> Response:
    return Response(
        status_code=429,
        content='{"ok":false,"error":"Cok fazla basarisiz deneme. Lutfen biraz bekleyin."}',
        media_type="application/json",
    )


@router.post("/api/auth/exchange")
async def _exchange_code_for_token(request: Request):
    """TEMASSIZ UZAKTAN PAIRING: 6-haneli eşleştirme kodunu cihaz api_token'ıyla takas eder.
    Hiç LAN'a girmemiş telefon (kod-yolu) uzaktan token alabilsin diye TÜNELDEN de erişilir —
    kodun KENDİSİ kimlik (auth-exempt). Kaba-kuvvete karşı 8 hatada 60sn global kilit. Yanlış→403."""
    import time as _t

    now = _t.time()
    # Audit P3: throttle per-IP (eskiden GLOBAL kova → 8 yanlış kodla saldırgan TÜM kullanıcıları 429'da
    # tutup uzaktan-pairing'i DoS ediyordu). Güvenilir kaynak IP (tünelde cf-connecting-ip Cloudflare-set).
    _cip = request.headers.get("cf-connecting-ip") or (request.client.host if request.client else "unknown")
    _bkt = _exchange_bucket(_cip)
    if _bkt["until"] > now:
        return Response(
            status_code=429, content='{"detail":"Cok fazla deneme, biraz bekleyin"}', media_type="application/json"
        )
    try:
        body = await request.json()
    except Exception:
        body = {}
    code = str((body or {}).get("code") or "").strip().upper()
    try:
        from utils.secrets_manager import get_secret

        expected = (get_secret("pairing_code") or "").strip().upper()
    except Exception:
        expected = ""
    if not _safe_compare(code, expected) or not expected or not code:
        _bkt["fails"] += 1
        if _bkt["fails"] >= 8:
            _bkt["until"] = now + 60.0
            _bkt["fails"] = 0
        return Response(status_code=403, content='{"detail":"Eslestirme kodu hatali"}', media_type="application/json")
    _bkt["fails"] = 0
    try:
        from servers.auth import get_api_token

        return {"token": get_api_token()}
    except Exception:
        logging.exception("exchange token alinamadi")
        return Response(status_code=500, content='{"detail":"token alinamadi"}', media_type="application/json")


# ── Operatör hesapları: e-posta/şifre KAYIT + GİRİŞ (yerel; PBKDF2). AUTH-EXEMPT (kullanıcı-katmanı cihaz-
# token'dan bağımsız; cihaz-token tüm GERÇEK API aksiyonlarını yine de gate'ler). Kayıt = ANINDA giriş. ──
from pydantic import BaseModel


class _AuthCredentials(BaseModel):
    email: str = ""
    password: str = ""


def _issue_session_token(email: str) -> str:
    """Cihaz-yerel sırla imzalı oturum token'ı (frontend saklar → oturum bütünlüğü; kolayca taklit edilemez).
    Gerçek API erişimini cihaz-token ayrıca gate'lediğinden bu, UI-oturum kanıtı içindir."""
    import base64
    import hashlib as _hl
    import hmac as _hmac
    import time as _t

    try:
        from utils.secrets_manager import get_secret

        secret = (get_secret("api_token") or "pemf").encode("utf-8")
    except Exception:
        secret = b"pemf-fallback"
    payload = f"{email}|{int(_t.time())}"
    sig = _hmac.new(secret, payload.encode("utf-8"), _hl.sha256).hexdigest()
    return base64.urlsafe_b64encode(f"{payload}|{sig}".encode("utf-8")).decode("utf-8")


# ─────────────── CİHAZ OPERATÖRLERİ: tek makine, çoklu veteriner (2026-08-08) ───────────────
# Bir kliniği 3-4 veteriner paylaşıyor ama uygulamaya TEK e-postayla giriliyordu → her kayda
# AYNI `operator_email` yazılıyor, "Benim Hastalarım / Tüm Klinik" ayrımı anlamsız kalıyordu.
# Kimlik bir kez Supabase ile doğrulanır (client girişi), sonraki geçişler yerel PIN ile
# ÇEVRİMDIŞI yapılır — internetsiz klinikte de operatör değişebilmeli.


def _yetki_iste(request: Request) -> None:
    """Operatör kaydı/çıkarma kapısı — LAN muafiyeti YOK (bkz. servers/auth.enforce_privileged)."""
    from servers.auth import enforce_privileged

    enforce_privileged(request)


class _OperatorEnroll(BaseModel):
    email: str = ""
    display_name: str = ""
    pin: str = ""
    # ⚠️ 2026-08-09: MEVCUT bir kaydın PIN'ini değiştirmek ESKİ PIN ister (bkz. auth_db).
    # Yeni kayıtta boş bırakılır.
    eski_pin: str = ""


class _OperatorPin(BaseModel):
    email: str = ""
    pin: str = ""


class _OperatorRemove(BaseModel):
    email: str = ""


@router.get("/api/operators")
async def _operators_list():
    """Bu cihazda kayıtlı operatörler (hızlı geçiş listesi). SIR İÇERMEZ."""
    from database.auth_db import get_auth_db

    return {"ok": True, "data": await asyncio.to_thread(get_auth_db().list_operators)}


@router.post("/api/operators/enroll")
async def _operators_enroll(payload: _OperatorEnroll, request: Request):
    """Operatörü bu cihaza kaydet / PIN'ini güncelle.

    ⚠️ Bu uç KİMLİK DOĞRULAMAZ: çağıran (client) Supabase girişini ZATEN yapmış olmalıdır.
    Amaç kimlik kanıtlamak değil, doğrulanmış kimliğe hızlı-geçiş PIN'i bağlamaktır.
    """
    _yetki_iste(request)
    from database.auth_db import get_auth_db

    # PBKDF2 200k tur → event-loop'u bloklama (register ucundaki P1 dersinin aynısı).
    ok, err = await asyncio.to_thread(
        get_auth_db().enroll_operator, payload.email, payload.display_name, payload.pin, payload.eski_pin
    )
    if not ok:
        if err == "locked":
            raise HTTPException(
                status_code=423, detail="Çok fazla hatalı deneme — bu operatör geçici olarak kilitlendi."
            )
        if err == "wrong_old_pin":
            # 401: kimlik kanıtlanamadı. Mevcut bir kaydın PIN'i sahibi olmadan değiştirilemez.
            raise HTTPException(
                status_code=401, detail="Bu e-posta zaten kayıtlı. PIN'i değiştirmek için mevcut PIN'i girin."
            )
        mesaj = {
            "invalid_email": "Geçerli bir e-posta adresi girin.",
            "invalid_pin": "PIN 6 haneli bir sayı olmalı.",
        }.get(err, "Operatör kaydedilemedi.")
        raise HTTPException(status_code=400, detail=mesaj)
    _e = (payload.email or "").strip().lower()
    # ⚠️ 2026-08-09 (Tier 1): kaydolan kişi ANINDA aktif olur (PIN yeniden sorulmaz) — dolayısıyla
    # jetonu da burada almalı. Almazsa şu tuzağa düşerdi: kayıttan sonra artık "kayıtlı operatör"
    # olduğu için jetonsuz yazmaları `cozumlenmis_operator` tarafından REDDEDİLİR ve İLK
    # operatörün tüm kayıtları sessizce SAHİPSİZ yazılırdı.
    # Denetim izi (2026-08-09, Tier 3): kimin bu cihaza operatör olarak eklendiği/PIN'inin
    # değiştirildiği, tıbbi kaydın ATFI açısından belirleyicidir. Sonradan "bu kaydı ben
    # yazmadım" denildiğinde kimliğin ne zaman ve nereden bağlandığı görülebilmelidir.
    from servers import audit_log as _iz
    from servers import operator_tokens

    _iz.yaz(
        request, "operator.enroll", operator_email=_e, scope="cihaz", detail={"pin_guncelleme": bool(payload.eski_pin)}
    )
    return {
        "ok": True,
        "email": _e,
        "operator_token": operator_tokens.uret(_e),
        "expires_in": operator_tokens.TTL_SANIYE,
    }


@router.post("/api/operators/verify")
async def _operators_verify(payload: _OperatorPin):
    """PIN doğrula → aktif operatör değişimi için izin. Hatalarda kilitlenme uygulanır."""
    from database.auth_db import get_auth_db

    ok, err = await asyncio.to_thread(get_auth_db().verify_pin, payload.email, payload.pin)
    if ok:
        _e = (payload.email or "").strip().lower()
        # ⚠️ DENETİM 2026-08-09 (Tier 1): doğrulama artık BİR ŞEYE YARIYOR. Eskiden yalnız
        # `{ok, email}` dönüyordu; doğrulama ile sonraki yazmalar arasında hiçbir bağ yoktu ve
        # `operator_email` her uçta istemci beyanıydı → cihaza erişen herkes başka bir hekimin
        # adıyla seans/AI/hasta kaydı yazabiliyordu. Artık kısa ömürlü bir jeton veriliyor ve
        # yazma yollarında e-posta JETONDAN türetiliyor (bkz. servers.auth.cozumlenmis_operator).
        from servers import operator_tokens

        return {
            "ok": True,
            "email": _e,
            "operator_token": operator_tokens.uret(_e),
            "expires_in": operator_tokens.TTL_SANIYE,
        }
    if err == "locked":
        # 423 Locked: istemci "PIN yanlış" değil "kilitli" demeli (kullanıcı boşuna denemesin).
        raise HTTPException(status_code=423, detail="Çok fazla hatalı deneme — bu operatör geçici olarak kilitlendi.")
    # ⚠️ 'no_operator' ile 'bad_pin' AYNI mesaj: hangi e-postaların kayıtlı olduğunu sızdırma.
    raise HTTPException(status_code=401, detail="PIN hatalı.")


@router.post("/api/operators/remove")
async def _operators_remove(payload: _OperatorRemove, request: Request):
    """Operatörü cihazdan çıkar. ⚠️ Tıbbi KAYITLARI SİLMEZ (yasal saklama + klinik sürekliliği)."""
    _yetki_iste(request)
    from database.auth_db import get_auth_db

    ok = await asyncio.to_thread(get_auth_db().remove_operator, payload.email)
    if not ok:
        raise HTTPException(status_code=404, detail="Operatör bulunamadı.")
    # ⚠️ Jetonları da düşür: aksi hâlde cihazdan ÇIKARILMIŞ bir hekim, elindeki jeton süresi
    # dolana kadar (12 saat) onun adına kayıt yazmaya devam ederdi.
    from servers import operator_tokens

    operator_tokens.iptal_email(payload.email)
    from servers import audit_log as _iz

    _iz.yaz(request, "operator.remove", operator_email=(payload.email or "").strip().lower(), scope="cihaz")
    return {"ok": True}


@router.post("/api/auth/register")
async def _register_user(payload: _AuthCredentials):
    """Yeni operatör hesabı: e-posta + şifre. Şifre kuralı: ≥8 karakter + büyük + küçük + rakam. Anında giriş."""
    from database.auth_db import EMAIL_RE, PASSWORD_RE, get_auth_db

    email = (payload.email or "").strip().lower()
    if not EMAIL_RE.match(email):
        return {"ok": False, "error": "Geçerli bir e-posta adresi girin."}
    if not PASSWORD_RE.match(payload.password or ""):
        return {
            "ok": False,
            "error": "Şifre en az 8 karakter olmalı; en az bir büyük harf, bir küçük harf ve bir rakam içermeli.",
        }
    # DENETIM P1: PBKDF2 (200k tur) EVENT-LOOP'ta calisiyordu → kimliksiz istemci arka arkaya
    # /register atarak tek-thread'li loop'u CPU'ya bogup TUM API'yi (WS yayinlari + seans
    # uclari dahil) yanit veremez hale getirebiliyordu. Bloklayan hash'i thread'e al.
    ok, err = await asyncio.to_thread(get_auth_db().register, email, payload.password)
    if not ok:
        return {"ok": False, "error": err}
    return {"ok": True, "email": email, "token": _issue_session_token(email)}


@router.post("/api/auth/login")
async def _login_user(payload: _AuthCredentials):
    """E-posta + şifre ile giriş → {ok, email, token}. E-posta '.edu' içeriyorsa frontend araştırma-modunu açar.
    'kullanıcı yok' ile 'şifre yanlış' AYRI mesajlanır (net UX): kayıtsız e-postada kullanıcı Kayıt Ol'a yönlenir."""
    from database.auth_db import get_auth_db

    email = (payload.email or "").strip().lower()
    bucket = _login_bucket(email)  # SEC-2: e-posta-başına kaba-kuvvet/PBKDF2-DoS throttle
    if _throttle_locked(bucket):
        return _throttle_429()
    db = get_auth_db()
    # Audit P3: PEMF_GENERIC_LOGIN_ERRORS=1 → no_user/bad_password'ü TEK jenerik mesaja indir (kullanıcı-
    # enumeration engelle) + non-existent'te dummy-verify (timing-eşitle). VARSAYILAN KAPALI: frontend
    # 'no_user' kodunu kayıt-yönlendirmesi için kullanıyor → açmak frontend koordinasyonu ister.
    import os as _os

    _generic = _os.getenv("PEMF_GENERIC_LOGIN_ERRORS", "0") == "1"
    if not await asyncio.to_thread(db.email_exists, email):
        _throttle_note_fail(bucket)
        if _generic:
            try:
                await asyncio.to_thread(
                    db.verify, email, payload.password or ""
                )  # dummy: no_user'ı bad_password ile eşitle (timing)
            except Exception:
                pass
            return {"ok": False, "code": "invalid", "error": "E-posta veya şifre hatalı."}
        return {
            "ok": False,
            "code": "no_user",
            "error": "Bu e-posta ile kayıtlı bir hesap yok. Yeni hesap için Kayıt Ol'u kullanın.",
        }
    if not await asyncio.to_thread(db.verify, email, payload.password or ""):
        _throttle_note_fail(bucket)
        if _generic:
            return {"ok": False, "code": "invalid", "error": "E-posta veya şifre hatalı."}
        return {"ok": False, "code": "bad_password", "error": "Şifre hatalı. Lütfen tekrar deneyin."}
    _throttle_clear(bucket)  # başarılı giriş → sayaç sıfırla
    return {"ok": True, "email": email, "token": _issue_session_token(email)}


# ── Şifre sıfırlama (yönetici koduyla; e-posta altyapısı olmayan yerel cihaz için "Şifremi unuttum") ──
class _ResetPayload(BaseModel):
    email: str = ""
    admin_code: str = ""
    new_password: str = ""


def _admin_reset_code() -> str:
    """Cihaz yönetici şifre-sıfırlama kodu (yoksa secrets_manager üretip kalıcı yazar)."""
    try:
        from utils.secrets_manager import get_secret

        return (get_secret("admin_reset_code") or "").strip()
    except Exception:
        logging.exception("admin_reset_code okunamadı")
        return ""


@router.post("/api/auth/reset")
async def _reset_password(payload: _ResetPayload, request: Request):
    """'Şifremi unuttum' — YÖNETİCİ koduyla operatör şifresini sıfırlar (login ekranından, oturumsuz).
    admin_code = cihaz yönetici kodu (Ayarlar'da görünür) VEYA cihaz api_token'ı (break-glass:
    ProgramData'daki api_token.txt — kimse giriş yapamıyorsa bile yönetici sıfırlayabilir)."""

    from database.auth_db import EMAIL_RE, PASSWORD_RE, get_auth_db

    # SEC-2 + DENETIM P3: birincil kilit IP-BASINA (bir saldirgan tum operatorleri kilitlemesin);
    # global kova cok genis esikle dagitik kaba-kuvvete karsi arka-durak olarak korunur.
    _ip = request.client.host if request.client else "?"
    _rbkt = _reset_bucket(_ip)
    if _throttle_locked(_rbkt) or _throttle_locked(_reset_throttle):
        return _throttle_429()
    email = (payload.email or "").strip().lower()
    supplied = (payload.admin_code or "").strip()
    valid = bool(supplied) and _safe_compare(supplied, _admin_reset_code())
    if not valid and supplied:  # break-glass: api_token da geçerli (ProgramData'dan okunabilir)
        try:
            from utils.secrets_manager import get_secret

            api_tok = (get_secret("api_token") or "").strip()
            if api_tok:
                valid = _safe_compare(supplied, api_tok)
        except Exception:
            pass
    if not valid:
        _throttle_note_fail(_rbkt)
        # Global kova yalniz ARKA-DURAK: cok daha genis esikle say.
        _reset_throttle["fails"] = _reset_throttle.get("fails", 0) + 1
        if _reset_throttle["fails"] >= _RESET_GLOBAL_MAX_FAILS:
            _reset_throttle["until"] = _time.time() + _THROTTLE_LOCK_SEC
            _reset_throttle["fails"] = 0
        return {
            "ok": False,
            "error": "Yönetici kodu hatalı. Kodu cihaz Ayarlar'ında veya ProgramData'daki api_token.txt'de bulabilirsiniz.",
        }
    _throttle_clear(_rbkt)  # doğru admin-kod → sayaç sıfırla
    _throttle_clear(_reset_throttle)
    if not EMAIL_RE.match(email):
        return {"ok": False, "error": "Geçerli bir e-posta adresi girin."}
    if not PASSWORD_RE.match(payload.new_password or ""):
        return {
            "ok": False,
            "error": "Yeni şifre en az 8 karakter olmalı; bir büyük harf, bir küçük harf ve bir rakam içermeli.",
        }
    ok, err = await asyncio.to_thread(get_auth_db().reset_password, email, payload.new_password)
    return {"ok": True} if ok else {"ok": False, "error": err}


@router.get("/api/auth/admin-code")
async def _get_admin_code():
    """Yönetici şifre-sıfırlama kodunu döndürür (Ayarlar'da gösterilir). X-API-Key ile KORUNUR —
    yalnız cihaza eşleşmiş app (cihaz-token'lı) okuyabilir; auth-exempt DEĞİL."""
    return {"code": _admin_reset_code()}
