"""Auth uçları (refactor B1: api_server.py'den ayrıldı — modüler router).

Davranış BİREBİR korunur. TEMASSIZ uzaktan-erişim token akışı:
- GET  /api/auth/token    — YEREL/LAN istemcisine cihaz api_token'ı (uzak/tünel → 403).
- POST /api/auth/exchange — 6-haneli pairing kodunu token'la takas (tünelden de erişilir;
                            kod=kimlik, auth-exempt; kaba-kuvvete karşı throttle).

api_server iç durumuna BAĞIMLI DEĞİL: yalnız `servers.auth` + `utils.secrets_manager`
fonksiyonları (fonksiyon-içi import, api_server'daki gibi). `_exchange_throttle` bu uca
özeldi → route ile birlikte taşındı (aliaslama gerekmez). Yollar/yanıtlar/gövde aynen korunur.
"""
import logging
import time as _time

from fastapi import APIRouter, Request
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
            return Response(status_code=403, content='{"detail":"Token yalniz yerel agdan alinabilir"}', media_type="application/json")
        return {"token": get_api_token()}
    except Exception:
        logging.exception("auth token endpoint hatasi")
        return Response(status_code=500, content='{"detail":"token alinamadi"}', media_type="application/json")


# Kod→token takas throttle (tek-cihaz, global; kaba-kuvvete karşı).
_exchange_throttle: dict = {}   # Audit P3: trusted-IP -> {"fails","until"} (eskiden GLOBAL kova → tek saldırgan herkesi kilitliyordu)

# ── SEC-2: login/reset kaba-kuvvet + PBKDF2-CPU-DoS throttle (exchange throttle deseninin eşi).
#    Login E-POSTA-BAŞINA (tarayan saldırgan meşru operatörü kilitlemesin); reset GLOBAL (admin-kod).
#    Not: oturum-token gerçek API-gate DEĞİL (cihaz-token gate'ler) → bu defense-in-depth + her login'in
#    200k-PBKDF2 CPU maliyetine karşı kimliksiz-DoS sınırı. LAN'da da uygulanır (kötücül LAN-sayfası vektörü). ──
_login_throttle: dict = {}                 # email -> {"fails": int, "until": float}
_reset_throttle = {"fails": 0, "until": 0.0}
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
    return Response(status_code=429, content='{"ok":false,"error":"Cok fazla basarisiz deneme. Lutfen biraz bekleyin."}', media_type="application/json")


@router.post("/api/auth/exchange")
async def _exchange_code_for_token(request: Request):
    """TEMASSIZ UZAKTAN PAIRING: 6-haneli eşleştirme kodunu cihaz api_token'ıyla takas eder.
    Hiç LAN'a girmemiş telefon (kod-yolu) uzaktan token alabilsin diye TÜNELDEN de erişilir —
    kodun KENDİSİ kimlik (auth-exempt). Kaba-kuvvete karşı 8 hatada 60sn global kilit. Yanlış→403."""
    import secrets as _sec
    import time as _t
    now = _t.time()
    # Audit P3: throttle per-IP (eskiden GLOBAL kova → 8 yanlış kodla saldırgan TÜM kullanıcıları 429'da
    # tutup uzaktan-pairing'i DoS ediyordu). Güvenilir kaynak IP (tünelde cf-connecting-ip Cloudflare-set).
    _cip = request.headers.get("cf-connecting-ip") or (request.client.host if request.client else "unknown")
    _bkt = _exchange_bucket(_cip)
    if _bkt["until"] > now:
        return Response(status_code=429, content='{"detail":"Cok fazla deneme, biraz bekleyin"}', media_type="application/json")
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
    if not expected or not code or not _sec.compare_digest(code, expected):
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


@router.post("/api/auth/register")
async def _register_user(payload: _AuthCredentials):
    """Yeni operatör hesabı: e-posta + şifre. Şifre kuralı: ≥8 karakter + büyük + küçük + rakam. Anında giriş."""
    from database.auth_db import EMAIL_RE, PASSWORD_RE, get_auth_db
    email = (payload.email or "").strip().lower()
    if not EMAIL_RE.match(email):
        return {"ok": False, "error": "Geçerli bir e-posta adresi girin."}
    if not PASSWORD_RE.match(payload.password or ""):
        return {"ok": False, "error": "Şifre en az 8 karakter olmalı; en az bir büyük harf, bir küçük harf ve bir rakam içermeli."}
    ok, err = get_auth_db().register(email, payload.password)
    if not ok:
        return {"ok": False, "error": err}
    return {"ok": True, "email": email, "token": _issue_session_token(email)}


@router.post("/api/auth/login")
async def _login_user(payload: _AuthCredentials):
    """E-posta + şifre ile giriş → {ok, email, token}. E-posta '.edu' içeriyorsa frontend araştırma-modunu açar.
    'kullanıcı yok' ile 'şifre yanlış' AYRI mesajlanır (net UX): kayıtsız e-postada kullanıcı Kayıt Ol'a yönlenir."""
    from database.auth_db import get_auth_db
    email = (payload.email or "").strip().lower()
    bucket = _login_bucket(email)                       # SEC-2: e-posta-başına kaba-kuvvet/PBKDF2-DoS throttle
    if _throttle_locked(bucket):
        return _throttle_429()
    db = get_auth_db()
    # Audit P3: PEMF_GENERIC_LOGIN_ERRORS=1 → no_user/bad_password'ü TEK jenerik mesaja indir (kullanıcı-
    # enumeration engelle) + non-existent'te dummy-verify (timing-eşitle). VARSAYILAN KAPALI: frontend
    # 'no_user' kodunu kayıt-yönlendirmesi için kullanıyor → açmak frontend koordinasyonu ister.
    import os as _os
    _generic = _os.getenv("PEMF_GENERIC_LOGIN_ERRORS", "0") == "1"
    if not db.email_exists(email):
        _throttle_note_fail(bucket)
        if _generic:
            try:
                db.verify(email, payload.password or "")   # dummy: no_user'ı bad_password ile eşitle (timing)
            except Exception:
                pass
            return {"ok": False, "code": "invalid", "error": "E-posta veya şifre hatalı."}
        return {"ok": False, "code": "no_user", "error": "Bu e-posta ile kayıtlı bir hesap yok. Yeni hesap için Kayıt Ol'u kullanın."}
    if not db.verify(email, payload.password or ""):
        _throttle_note_fail(bucket)
        if _generic:
            return {"ok": False, "code": "invalid", "error": "E-posta veya şifre hatalı."}
        return {"ok": False, "code": "bad_password", "error": "Şifre hatalı. Lütfen tekrar deneyin."}
    _throttle_clear(bucket)                             # başarılı giriş → sayaç sıfırla
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
async def _reset_password(payload: _ResetPayload):
    """'Şifremi unuttum' — YÖNETİCİ koduyla operatör şifresini sıfırlar (login ekranından, oturumsuz).
    admin_code = cihaz yönetici kodu (Ayarlar'da görünür) VEYA cihaz api_token'ı (break-glass:
    ProgramData'daki api_token.txt — kimse giriş yapamıyorsa bile yönetici sıfırlayabilir)."""
    import hmac

    from database.auth_db import EMAIL_RE, PASSWORD_RE, get_auth_db
    if _throttle_locked(_reset_throttle):               # SEC-2: admin-kod kaba-kuvvetine karşı global throttle
        return _throttle_429()
    email = (payload.email or "").strip().lower()
    supplied = (payload.admin_code or "").strip()
    valid = bool(supplied) and hmac.compare_digest(supplied, _admin_reset_code())
    if not valid and supplied:  # break-glass: api_token da geçerli (ProgramData'dan okunabilir)
        try:
            from utils.secrets_manager import get_secret
            api_tok = (get_secret("api_token") or "").strip()
            if api_tok:
                valid = hmac.compare_digest(supplied, api_tok)
        except Exception:
            pass
    if not valid:
        _throttle_note_fail(_reset_throttle)
        return {"ok": False, "error": "Yönetici kodu hatalı. Kodu cihaz Ayarlar'ında veya ProgramData'daki api_token.txt'de bulabilirsiniz."}
    _throttle_clear(_reset_throttle)                    # doğru admin-kod → sayaç sıfırla
    if not EMAIL_RE.match(email):
        return {"ok": False, "error": "Geçerli bir e-posta adresi girin."}
    if not PASSWORD_RE.match(payload.new_password or ""):
        return {"ok": False, "error": "Yeni şifre en az 8 karakter olmalı; bir büyük harf, bir küçük harf ve bir rakam içermeli."}
    ok, err = get_auth_db().reset_password(email, payload.new_password)
    return {"ok": True} if ok else {"ok": False, "error": err}


@router.get("/api/auth/admin-code")
async def _get_admin_code():
    """Yönetici şifre-sıfırlama kodunu döndürür (Ayarlar'da gösterilir). X-API-Key ile KORUNUR —
    yalnız cihaza eşleşmiş app (cihaz-token'lı) okuyabilir; auth-exempt DEĞİL."""
    return {"code": _admin_reset_code()}
