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
_exchange_throttle = {"fails": 0, "until": 0.0}


@router.post("/api/auth/exchange")
async def _exchange_code_for_token(request: Request):
    """TEMASSIZ UZAKTAN PAIRING: 6-haneli eşleştirme kodunu cihaz api_token'ıyla takas eder.
    Hiç LAN'a girmemiş telefon (kod-yolu) uzaktan token alabilsin diye TÜNELDEN de erişilir —
    kodun KENDİSİ kimlik (auth-exempt). Kaba-kuvvete karşı 8 hatada 60sn global kilit. Yanlış→403."""
    import secrets as _sec
    import time as _t
    now = _t.time()
    if _exchange_throttle["until"] > now:
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
        _exchange_throttle["fails"] += 1
        if _exchange_throttle["fails"] >= 8:
            _exchange_throttle["until"] = now + 60.0
            _exchange_throttle["fails"] = 0
        return Response(status_code=403, content='{"detail":"Eslestirme kodu hatali"}', media_type="application/json")
    _exchange_throttle["fails"] = 0
    try:
        from servers.auth import get_api_token
        return {"token": get_api_token()}
    except Exception:
        logging.exception("exchange token alinamadi")
        return Response(status_code=500, content='{"detail":"token alinamadi"}', media_type="application/json")
