# Author: mertaygn, cglrgrkn
import asyncio  # P0 audit 2026-06-28: senkron MQTT publish'i event-loop'tan cikar (to_thread)
import itertools as _itertools  # MQTT yayinci client_id sayaci (bkz. _mqtt_client_id)
import json
import logging
import os
import threading
import time
import uuid as _uuid
from contextlib import asynccontextmanager  # audit B-2.2: on_event yerine lifespan
from datetime import datetime

from fastapi import FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from servers import (
    coil_run_tracker,  # audit B-2.2: coil-run (treatment-DB) tracker ayrı modülde
    live_state,  # audit B-2.2: canlı-durum (WS/live-state) çekirdeği ayrı modülde
    session_state,  # audit B-2.2 (son kademe): aktif-seans state ayrı modülde
)
from servers.ai_router import ai_router
from servers.history_router import router as history_router
from servers.settings_router import router as settings_router
from utils.path_utils import get_app_version, get_build_id  # audit B-8.1: tek versiyon kaynağı

_APP_VERSION = get_app_version()
_BUILD_ID = get_build_id()  # launcher'ın kurduğu paketin sha'sı (yoksa "")

# ── B-2.2: canlı-durum çekirdeği servers/live_state.py'ye taşındı ──────────────────────────────
# Aşağıdaki alias'lar AYNI nesnelere işaret eder (dict/list/lock in-place mutasyon → api_server'ın
# WS/MQTT/session gövdesi DEĞİŞMEDEN çalışır; davranış birebir — tests/test_live_state.py kanıtlar).
# Reassign edilen globaller (_event_loop lifespan'de) live_state.set_event_loop() ile atanır.
_live_state = live_state._live_state
_live_state_lock = live_state._live_state_lock
_ws_clients = live_state._ws_clients
_ws_lock = live_state._ws_lock
STM_COIL_IDS = live_state.STM_COIL_IDS
ESP_COIL_IDS = live_state.ESP_COIL_IDS
_ws_broadcast_sync = live_state._ws_broadcast_sync
_sync_stm_coils_locked = live_state._sync_stm_coils_locked
_push_notification = live_state._push_notification
_build_ws_snapshot = live_state._build_ws_snapshot
update_live_stm_status = live_state.update_live_stm_status
update_live_coil_from_stm = live_state.update_live_coil_from_stm
update_live_session_state = live_state.update_live_session_state
set_live_patient = live_state.set_live_patient

# Headless Core State referansı (Singleton Bridge)
# Bu obje main.py'den enjekte edilebilir veya burada global import edilebilir
try:
    from controllers.hardware_controller import HardwareController
    from database.patient_database import get_patient_database
    from headless_core import HeadlessCore
except ImportError:
    HeadlessCore = None
    HardwareController = None

    def get_patient_database(app_data_dir=None):
        return None


def _app_data_dir():
    """Kanonik app_data dizini — history/settings router'larıyla AYNI kök (split-brain önler).
    Eskiden os.environ APPDATA boş/yokken 'C:/PEMF_GUI'ye düşüp yazıcı/okuyucu ayrışıyordu."""
    try:
        from utils.path_utils import get_app_data_directory

        return get_app_data_directory()
    except Exception:
        from pathlib import Path as _PP

        return _PP(os.environ.get("APPDATA") or (_PP.home() / "AppData" / "Roaming")) / "PEMF_GUI"


# Swagger/OpenAPI görünürlüğü (audit B-1.7): ÜRETİMDE (auth zorunlu VEYA tünel açık = internet'e
# açık yüzey) /docs + /redoc + /openapi.json KAPALI → API şeması tünelden sızmasın. YEREL/dev
# (auth kapalı + tünel kapalı) AÇIK → geliştirici kolaylığı. PEMF_ENABLE_DOCS ile açıkça geçersiz kıl
# (1=aç, 0=kapat). Not: auth.py _EXEMPT_PREFIXES docs'u zaten muaf tutar → açıkken yerelde token'sız açılır.
_docs_env = os.getenv("PEMF_ENABLE_DOCS", "").strip()
if _docs_env in ("0", "1"):
    _docs_enabled = _docs_env == "1"
else:
    _docs_enabled = os.getenv("PEMF_REQUIRE_AUTH", "0") != "1" and os.getenv("PEMF_ENABLE_TUNNEL", "0") != "1"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Uygulama yaşam-döngüsü (audit B-2.2: deprecated @app.on_event yerine + import-zamanı
    thread yan-etkisini kaldırır). Arka-plan thread'leri (safety süre-watchdog dahil) YALNIZ sunucu
    BAŞLARKEN başlatılır — modül import'unda DEĞİL. Fonksiyonlar dosyada sonra tanımlı; runtime'da çözülür."""
    # ── STARTUP ──
    # B-2.2: canlı-durum modülüne event-loop'u ver → thread'lerden (MQTT/STM/sim) gelen WS
    # broadcast'leri bu loop'a planlar (eskiden modül-global _event_loop; davranış aynı).
    live_state.set_event_loop(asyncio.get_event_loop())
    logging.info("FastAPI Bridge: Başlıyor...")
    _register_event_bus_handlers()
    # MQTT canlı veri dinleyicisi + mDNS (aynı Wi-Fi'deki telefonlar keşfetsin)
    threading.Thread(target=_start_mqtt_for_api, daemon=True, name="FastAPIMQTTListener").start()
    threading.Thread(target=_start_mdns_service, daemon=True, name="PEMFmDNSService").start()
    # Arka-plan daemon'ları (süre-watchdog + sensör-persist + günlük-bakım + opsiyonel sim).
    _start_background_threads()
    try:
        yield
    finally:
        # ── SHUTDOWN ──
        logging.info("FastAPI Bridge: Kapanıyor...")
        if _mqtt_client_api:
            try:
                _mqtt_client_api.loop_stop()
                _mqtt_client_api.disconnect()
            except Exception:
                pass
        try:
            from servers.auto_discovery import stop_mdns

            stop_mdns()
        except Exception:
            pass


app = FastAPI(
    title="PEMF React Native API Bridge",
    description="PyQt6 arayüzüne gerek duymayan Headless Donanım API'si",
    version=_APP_VERSION,
    docs_url="/docs" if _docs_enabled else None,
    redoc_url="/redoc" if _docs_enabled else None,
    openapi_url="/openapi.json" if _docs_enabled else None,
    lifespan=lifespan,
)

# CORS configurable: üretimde PEMF_CORS_ORIGINS="https://app1,https://app2" ile daraltın.
# Native uygulamada Origin yok (CORS uygulanmaz); web paneli için anlamlıdır.
# DENETIM P0: VARSAYILAN "*" idi. deploy/device.env bunu daraltiyor ama backend .env dosyalarini
# OTOMATIK YUKLEMEZ (load_dotenv yok) → env yalniz NSSM servis kaydinda uygulanir. Tauri launcher
# ("PEMF Vet Client", canli dagitim yolu) exe'yi DOGRUDAN spawn edip yalniz 2 env verdiginden
# ACAO:* etkin kaliyordu: operatorun actigi HERHANGI bir web sayfasi cihaza fetch atip
# /api/auth/token (kalici cihaz anahtari) ve /api/patients (tum hasta PII) YANITLARINI OKUYABILIYORDU.
# Varsayilan artik loopback + RFC1918 + *.local kokenleriyle sinirli; internetteki bir sayfa
# yanitlari okuyamaz. Acik "*" hala MUMKUN ama artik bilincli bir tercih (PEMF_CORS_ORIGINS=*).
_LAN_ORIGIN_REGEX = (
    r"^https?://("
    r"localhost|127\.\d{1,3}\.\d{1,3}\.\d{1,3}|\[::1\]|"
    r"10\.\d{1,3}\.\d{1,3}\.\d{1,3}|"
    r"192\.168\.\d{1,3}\.\d{1,3}|"
    r"172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}|"
    r"169\.254\.\d{1,3}\.\d{1,3}|"
    r"[A-Za-z0-9-]+\.local"
    r")(:\d+)?$"
)
_cors_env = os.getenv("PEMF_CORS_ORIGINS", "").strip()
if _cors_env == "*":
    _cors_kwargs = {"allow_origins": ["*"]}  # acik opt-in (geriye uyumlu)
elif _cors_env:
    _cors_kwargs = {"allow_origins": [o.strip() for o in _cors_env.split(",") if o.strip()]}
else:
    _cors_kwargs = {"allow_origins": [], "allow_origin_regex": _LAN_ORIGIN_REGEX}
app.add_middleware(
    CORSMiddleware,
    allow_credentials=False,  # API stateless (cookie yok)
    allow_methods=["*"],
    allow_headers=["*"],
    **_cors_kwargs,
)

# Audit P2 + eksik-taraması P2 (2026-08-22): DNS-rebinding'e karşı Host koruması.
#
# TARİHÇE: TrustedHost altyapısı 2026-08-04'ten beri vardı ama varsayılan "*" ve HİÇBİR dağıtım
# profili/launcher ayarlamadığı için koruma hiçbir kurulumda AKTİF DEĞİLDİ. Statik liste de
# çözüm olamıyordu: meşru istemciler kliniğin O ANKİ LAN IP'siyle bağlanır (telefon →
# http://192.168.1.35:8000) ve TrustedHost joker-IP bilmez — liste ya mobili kırar ya "*" kalır.
#
# "auto" MODU: rebinding saldırısının Host başlığı HER ZAMAN saldırganın ALAN ADIdır (tarayıcı
# Host'a çözdüğü adı yazar). Meşru Host'lar sayılabilir bir sınıftır: IP-literal (v4/v6),
# localhost, *.local (mDNS), makinenin kendi adı, tünel alanları. "auto" bu sınıfı serbest
# bırakır, YABANCI DNS ADLARINI 400 ile reddeder. "auto,klinik.sirket.com" ek ad tanımlar
# (kurumsal intranet FQDN'li klinik için çıkış kapısı).
#
# Değer sözlüğü:  "*" (VARSAYILAN) = koruma kapalı (dev/test — sessiz davranış değişikliği yok;
# korumayı deploy/*.env + launcher backend_env "auto" ile açar) · "auto[,ek...]" = yukarıdaki
# sınıflandırma · açık liste = eski TrustedHost davranışı aynen.
# Kilit: tests/test_allowed_hosts_rebinding.py
import ipaddress as _ipaddress
import socket as _socket


def _allowed_hosts_secimi(deger: str):
    """Env değerini (mod, ekstra/liste) çiftine çözer — test edilebilir saf fonksiyon."""
    d = (deger or "*").strip()
    if d == "*" or not d:
        return ("kapali", ())
    parcalar = [p.strip() for p in d.split(",") if p.strip()]
    if parcalar and parcalar[0].lower() == "auto":
        return ("auto", tuple(p.lower() for p in parcalar[1:]))
    return ("liste", tuple(parcalar))


def _host_izinli(host: str, ekstra: tuple) -> bool:
    """'auto' modunun sınıflandırması. Boş Host = izinli (HTTP/1.0 fail-open; rebinding boş
    Host ile YAPILAMAZ — tarayıcı her zaman Host yazar)."""
    h = (host or "").strip().lower()
    if not h:
        return True
    if h.startswith("[") and h.endswith("]"):
        h = h[1:-1]  # IPv6 literal köşeli parantezi
    try:
        _ipaddress.ip_address(h)
        return True  # IP-literal: telefonun LAN erişimi, hotspot, loopback...
    except ValueError:
        pass
    if h == "localhost" or h.endswith(".localhost"):
        return True
    if h.endswith(".local"):
        return True  # mDNS (pemf.local)
    if h == _socket.gethostname().strip().lower():
        return True  # tarayıcıda makine adıyla erişim (http://KLINIK-PC:8000)
    if h.endswith(".trycloudflare.com"):
        return True  # quick tunnel
    if h in ekstra:
        return True
    # Named tunnel hostname'i sırlardan (best-effort; sır altyapısı yoksa sessizce geç).
    try:
        from utils.secrets_manager import get_secret

        tunel = (get_secret("tunnel_hostname", default="", generate=False) or "").strip().lower()
        if tunel and h == tunel:
            return True
    except Exception:
        pass
    return False


class _RebindKorumaMiddleware:
    """Saf ASGI: http+websocket kapsamında Host'u sınıflandırır; yabancı DNS adı → 400.
    Reddedilen host'lar tekrar-log seli üretmesin diye süreç başına bir kez loglanır."""

    def __init__(self, app, ekstra: tuple = ()):
        self.app = app
        self.ekstra = tuple(ekstra)
        self._loglanan: set = set()

    async def __call__(self, scope, receive, send):
        if scope.get("type") not in ("http", "websocket"):
            return await self.app(scope, receive, send)
        host = ""
        for ad, deger in scope.get("headers") or []:
            if ad == b"host":
                host = deger.decode("latin-1")
                break
        # Port'u at ([::1]:8000 dahil): son ':' yalnız rakam taşıyorsa porttur.
        if ":" in host:
            govde, _, kuyruk = host.rpartition(":")
            if kuyruk.isdigit():
                host = govde
        if _host_izinli(host, self.ekstra):
            return await self.app(scope, receive, send)
        if host not in self._loglanan:
            self._loglanan.add(host)
            logging.getLogger(__name__).warning(
                "Host reddedildi (DNS-rebinding korumasi): %r — mesru bir adsa PEMF_ALLOWED_HOSTS='auto,%s' ekleyin",
                host,
                host,
            )
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 4400})
            return
        await send(
            {"type": "http.response.start", "status": 400, "headers": [(b"content-type", b"text/plain; charset=utf-8")]}
        )
        await send({"type": "http.response.body", "body": "Gecersiz Host basligi.".encode("utf-8")})


_ah_mod, _ah_liste = _allowed_hosts_secimi(os.getenv("PEMF_ALLOWED_HOSTS", "*"))
if _ah_mod == "auto":
    app.add_middleware(_RebindKorumaMiddleware, ekstra=_ah_liste)
elif _ah_mod == "liste":
    from starlette.middleware.trustedhost import TrustedHostMiddleware

    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(_ah_liste))


# ── Global exception handler'ları (audit B-4.1) ────────────────────────────────
# Eskiden yakalanmayan istisna → Starlette varsayılan 500 (korelasyon-id'siz, merkezî log'suz);
# doğrulama hataları da tutarsız formattaydı. Artık TEK, tutarlı zarf: yakalanmayan istisnalar
# SUNUCU-TARAFI korelasyon-id ile loglanır ve istemciye ham traceback/str(e) SIZMAZ (bilgi ifşası).
@app.exception_handler(Exception)
async def _unhandled_exception_handler(request: Request, exc: Exception):
    err_id = _uuid.uuid4().hex[:12]
    logging.getLogger("api_server").exception(
        "Yakalanmayan istisna [error_id=%s] %s %s", err_id, request.method, request.url.path
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Sunucu hatası (beklenmeyen).", "error_id": err_id},
    )


@app.exception_handler(RequestValidationError)
async def _validation_exception_handler(request: Request, exc: RequestValidationError):
    # 'input' alanı PII taşıyabilir → istemciye YALNIZ loc/msg/type; ham girdi değeri sızmaz.
    errors = [{"loc": e.get("loc"), "msg": e.get("msg"), "type": e.get("type")} for e in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": "Geçersiz istek verisi.", "errors": errors})


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """
    Expo Web üzerinde SQLite (wa-sqlite) kullanabilmek için 'SharedArrayBuffer' nesnesine ihtiyaç vardır.
    Bu nesnenin tarayıcıda tanımlı olabilmesi için COOP ve COEP header'larının 'same-origin' / 'require-corp' olarak ayarlanması ZORUNLUDUR.
    Aksi halde uygulama beyaz ekranda kalır ve 'SharedArrayBuffer is not defined' hatası fırlatır.
    """
    # O-1: request-correlation-id — istemci X-Request-ID'sini (güvenli-karakter SÜZ → header/log-injection'a
    # karşı) kullan ya da üret; JSON-log + yanıt header'ında izlenir (7/24 saha debug).
    _rid = (
        "".join(c for c in (request.headers.get("X-Request-ID") or "") if c.isalnum() or c in "._-")[:64]
        or _uuid.uuid4().hex[:12]
    )
    from utils.request_context import request_id_var

    request_id_var.set(_rid)
    response = await call_next(request)
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    response.headers["Cross-Origin-Embedder-Policy"] = "require-corp"
    response.headers["Cross-Origin-Resource-Policy"] = "cross-origin"
    response.headers["X-API-Version"] = _APP_VERSION  # istemci/monitoring sürüm görünürlüğü
    # Paket kimliği: aynı sürüm numarası farklı ikiliyi çalıştırabilir (yeniden yayın, yarım
    # güncelleme). Olay kaydında "hangi paket" sorusunu tek başına cevaplar. Launcher'sız
    # çalıştırmada boş → header hiç eklenmez (uydurma değer basmaktansa sessiz kal).
    if _BUILD_ID:
        response.headers["X-Build-Id"] = _BUILD_ID
    # Klasik güvenlik header'ları (audit S-1): MIME-sniff / clickjacking / referrer-sızıntı önle.
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "no-referrer"
    # HSTS YALNIZ TLS-proxy/tünel arkasından (LAN düz-HTTP'de anlamsız; tarayıcı HTTP'de yok sayar).
    _h = request.headers
    if _h.get("cf-connecting-ip") or _h.get("cf-ray") or _h.get("x-forwarded-proto", "").lower() == "https":
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    # CSP (audit P2 #62/#63/#64) — YALNIZ sunulan web (HTML) yanıtlarına. Kilit koruma connect-src:
    # bir XSS/tedarik-zinciri script'i çalışsa bile localStorage'daki X-API-Key + Supabase token'ını
    # DIŞ sunucuya sızdıramaz (self + Supabase + aynı-origin ws dışına ağ isteği bloklanır). script/
    # style/asset yönergeleri Expo-web'i kırmayacak kadar geniş; object/base/frame-ancestors kilitli.
    _ctype = response.headers.get("content-type", "")
    if _ctype.startswith("text/html"):
        _host = _h.get("host", "")
        _connect = "'self' https://*.supabase.co"
        if _host:
            _connect += f" ws://{_host} wss://{_host}"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; "
            "font-src 'self' data:; "
            "worker-src 'self' blob:; "
            f"connect-src {_connect}; "
            "object-src 'none'; base-uri 'none'; frame-ancestors 'self'; form-action 'self'"
        )
    response.headers["X-Request-ID"] = _rid
    return response


@app.middleware("http")
async def _auth_middleware(request: Request, call_next):
    """P0 #1: PEMF_REQUIRE_AUTH=1 iken donanım/hasta/seans endpoint'lerine token zorunlu kılar.
    İstemci: X-API-Key header veya ?token= query. OPTIONS(preflight) + muaf yollar serbesttir
    (emergency_stop/health/discovery/simulator). Auth KAPALIYKEN hiçbir şey değişmez (geriye uyumlu)."""
    # API versiyonlama (audit B-8.1): /api/v1/* yolları /api/* handler'larına yönlendirilir → hem
    # ESKİ istemciler (/api) hem YENİ istemciler (/api/v1) çalışır; route çoğaltmadan.
    # DENETIM P3: bu yeniden-yazim eskiden add_security_headers icindeydi; Starlette'te en SON
    # eklenen middleware EN DISTA calistigindan (kayit sirasi: headers, auth, rate-limit) o
    # middleware auth'tan SONRA kosuyordu → auth, yeniden-YAZILMAMIS yolu goruyordu ve
    # is_exempt("/api/v1/hardware/emergency_stop") tutmuyordu: fail-safe ACIL DURDURMA ucu
    # /api/v1 alias'inda 401 veriyordu. Yeniden-yazim artik auth'tan ONCE.
    _p = request.scope.get("path", "")
    if _p.startswith("/api/v1/"):
        request.scope["path"] = "/api/" + _p[len("/api/v1/") :]
    if request.method == "OPTIONS":
        return await call_next(request)
    # P1 audit 2026-06-28: FAIL-CLOSED. Eskiden auth yolundaki HERHANGI istisna (servers.auth
    # import hatasi, check_token bug) except'e dusup KOSULSUZ call_next ediyordu → TUM enforcement
    # bypass (sessiz fail-open). Artik: auth-katmani yuklenemezse guvenlik-muaf yollar (emergency_stop/
    # health/discovery/simulator) gecer, GERISI 503; token kontrolu patlarsa 401.
    try:
        from servers.auth import check_token, is_exempt, is_local_request, require_auth

        required = bool(require_auth())
        exempt = is_exempt(request.url.path)
        # YEREL/LAN MUAF: masaüstü kısayolu (localhost:8000) + aynı-WiFi istekleri token İSTEMEZ;
        # token YALNIZ tünel/uzak (Cloudflare header'lı) erişimde gerekir → web arayüzü yerelde sorunsuz açılır.
        if not exempt:
            _h = request.headers
            _via_proxy = bool(_h.get("cf-connecting-ip") or _h.get("cf-ray") or _h.get("x-forwarded-for"))
            if is_local_request(request.client.host if request.client else "", _via_proxy):
                exempt = True
    except Exception:
        logging.exception("auth katmani yuklenemedi (FAIL-CLOSED)")
        p = request.url.path
        if any(s in p for s in ("emergency_stop", "/health", "/discovery", "/simulator")):
            return await call_next(request)
        return Response(
            status_code=503, content='{"detail":"Auth katmani kullanilamiyor"}', media_type="application/json"
        )
    if required and not exempt:
        try:
            ok = check_token(request.headers.get("X-API-Key") or request.query_params.get("token") or "")
        except Exception:
            logging.exception("token kontrol hatasi (FAIL-CLOSED)")
            ok = False
        if not ok:
            return Response(
                status_code=401,
                content='{"detail":"Gecersiz veya eksik API anahtari (X-API-Key)"}',
                media_type="application/json",
            )
    return await call_next(request)


# ── Rate limiting (in-process, per-UZAK-IP) — DoS/tarama azaltma (audit B-1.6) ──────────
# YEREL/LAN trafiği (web UI + 8 mobil, güvenli ağ) SINIRLANMAZ — yüksek-frekanslı meşru polling
# (AI Pro capture ~400ms, reconcile 2s) kırılmasın. Yalnız UZAK (Cloudflare tünel / reverse-proxy)
# istekler internet yüzeyi olduğundan pencere-başı sınırlıdır. Token 192-bit → brute-force zaten
# imkânsız; buradaki fayda DoS/otomatik-tarama azaltma. Env: PEMF_RATELIMIT_REMOTE_PER_MIN (vars. 600,
# 0=kapalı). ACİL-DURDURMA + health + discovery DAİMA muaf (fail-safe). _rl_hits yalnız bu async
# middleware'den (event-loop, tek-thread) erişilir → kilit gerekmez.
_RL_WINDOW_SEC = 60.0
try:
    _RL_REMOTE_MAX = int(os.getenv("PEMF_RATELIMIT_REMOTE_PER_MIN", "600"))
except ValueError:
    _RL_REMOTE_MAX = 600
_rl_hits: dict = {}  # client_ip -> [window_start_epoch, count]
_rl_last_purge = [0.0]


def _rl_client_ip(request: Request) -> str:
    """Gerçek istemci IP'si (per-istemci rate-limit anahtarı). GÜVENLİK (audit P3 #5): ham
    X-Forwarded-For SPOOF-EDİLEBİLİR (istemci keyfi XFF gönderip her istekte anahtar-değiştirerek
    rate-limit'i atlar) → ANAHTAR olarak KULLANMA. Yalnız Cloudflare'in DOĞRULADIĞI cf-connecting-ip
    (cloudflared client-supplied değeri ezer) veya doğrudan SOKET IP'si."""
    # DENETIM P3: cf-connecting-ip KOSULSUZ kullaniliyordu — soket-IP'nin gercekten guvenilir bir
    # proxy olup olmadigi hic sorulmuyordu. Cloudflare'siz kurulumda (dogrudan LAN/port-forward)
    # saldirgan her istekte farkli bir cf-connecting-ip uydurup rate-limit anahtarini degistirerek
    # siniri TAMAMEN atlayabiliyordu. Baslik artik YALNIZCA istek beyan edilmis bir ters-proxy'den
    # geliyorsa kullanilir (PEMF_TRUSTED_PROXIES); aksi halde SOKET IP'si esas alinir.
    cf = (request.headers.get("cf-connecting-ip") or "").strip()
    _sock = request.client.host if request.client else "?"
    # Baslik SU IKI durumda guvenilir: (a) istek LOOPBACK'ten geliyor — cloudflared cihazin
    # KENDISINDE kosar ve tunel trafigini 127.0.0.1'den iletir, dolayisiyla gercek tunel
    # istemcilerini birbirinden ayirmak icin baslik ZORUNLUDUR; (b) soket-IP acikca beyan
    # edilmis bir ters-proxy (PEMF_TRUSTED_PROXIES). Diger her durumda (dogrudan LAN/port-forward)
    # baslik saldirgan tarafindan uydurulabilir → SOKET IP'si esas alinir.
    if cf:
        try:
            import ipaddress as _ip

            from servers.auth import _trusted_proxies

            _a = _ip.ip_address(_sock)
            if _a.is_loopback or any(_a in n for n in _trusted_proxies()):
                return cf.split(",")[0].strip()
        except Exception:
            pass
    return _sock


@app.middleware("http")
async def _rate_limit_middleware(request: Request, call_next):
    if _RL_REMOTE_MAX <= 0 or request.method == "OPTIONS":
        return await call_next(request)
    p = request.url.path
    # Fail-safe: acil-durdurma + sağlık/keşif ASLA sınırlanmaz.
    if "emergency_stop" in p or p.startswith("/api/health") or p.startswith("/api/discovery"):
        return await call_next(request)
    _h = request.headers
    _via_proxy = bool(_h.get("cf-connecting-ip") or _h.get("cf-ray") or _h.get("x-forwarded-for"))
    try:
        from servers.auth import is_local_request

        _local = is_local_request(request.client.host if request.client else "", _via_proxy)
    except Exception:
        _local = not _via_proxy
    if _local:
        return await call_next(request)  # LAN/localhost sınırsız (güvenli ağ)
    now = time.time()
    ip = _rl_client_ip(request)
    win = _rl_hits.get(ip)
    if win is None or (now - win[0]) >= _RL_WINDOW_SEC:
        _rl_hits[ip] = [now, 1]
    else:
        win[1] += 1
        if win[1] > _RL_REMOTE_MAX:
            retry = max(1, int(_RL_WINDOW_SEC - (now - win[0])))
            logging.getLogger(__name__).warning("Rate limit: uzak IP %s %s istek/dk aştı (%s)", ip, _RL_REMOTE_MAX, p)
            return Response(
                status_code=429,
                content='{"detail":"Cok fazla istek, biraz bekleyin"}',
                media_type="application/json",
                headers={"Retry-After": str(retry)},
            )
    # Bellek: 5 dk'da bir süresi geçmiş pencereleri temizle (uzak IP birikimi olmasın).
    if now - _rl_last_purge[0] > 300:
        _rl_last_purge[0] = now
        for _k in [k for k, v in _rl_hits.items() if now - v[0] >= _RL_WINDOW_SEC]:
            _rl_hits.pop(_k, None)
    return await call_next(request)


app.include_router(ai_router)
app.include_router(history_router)
app.include_router(settings_router)
# audit B-2.2: cohesive uç grupları ayrı modüler router'lara çıkarıldı (api_server.py küçültüldü).
from servers.auth_router import router as auth_router
from servers.patient_router import router as patient_router
from servers.session_router import router as session_router
from servers.system_router import router as system_router
from servers.update_router import router as update_router

app.include_router(update_router)
app.include_router(patient_router)
app.include_router(system_router)
app.include_router(session_router)
app.include_router(auth_router)


# (audit B-2.2) /api/update/* uçları servers/update_router.py'ye taşındı (modüler ayrım).

# DEMA Simülatörü host etme
import os

from utils.path_utils import packaged_resource_path

# ═══════════════════════════════════════════════════════════════════
# WebSocket + MQTT Canlı Veri Sistemi (port 8000 üzerinden)
# Tek portlu headless backend: REST API + WebSocket canlı veri sistemi.
# ═══════════════════════════════════════════════════════════════════

# ── WebSocket bağlantı havuzu ──────────────────────────────────────
# B-2.2: WS istemci kaydı + gönderim serileştirme + broadcast → servers/live_state.py (üstte alias'landı).


# B-2.2: _live_state + _sync_stm_coils_locked + _push_notification → servers/live_state.py (üstte alias'landı).


# ── MQTT Callbacks ─────────────────────────────────────────────────
_mqtt_client_api = None


def _on_mqtt_connect_api(client, userdata, flags, rc):
    if rc == 0:
        with _live_state_lock:
            _live_state["mqtt"] = "online"
        client.subscribe("pemf/coil/+/sensors")
        client.subscribe("pemf/coil/+/status")
        client.subscribe("pemf/coil/+/events")
        client.subscribe("pemf/coil/+/alarm")
        client.subscribe("pemf/coil/+/ack")  # HG-4 (2026-08-19): ESP komut onayı — E-stop teslimi doğrulanabilsin
        client.subscribe("pemf/gateway/status")
        client.subscribe("pemf/bridge/status")
        _push_notification("Sistem bağlantısı kuruldu", "success")
    else:
        with _live_state_lock:
            _live_state["mqtt"] = "error"


def _on_mqtt_disconnect_api(client, userdata, rc):
    with _live_state_lock:
        _live_state["mqtt"] = "error"
    _push_notification("Sistem bağlantısı kesildi", "warning")


# ── ESP telemetri STALENESS watchdog (reconnect-audit self-heal) ──────────────
# Gap: ESP güç kaybıyla LWT yaymadan (ungraceful) ölürse coil `connected:True` + BAYAT sensör değerleri
# kalıyordu → UI'da "canlı" görünüyordu. ESP bobinleri sıcaklık izleme için PERİYODİK sensör yayınlar;
# GENİŞ eşik (30sn) boyunca HİÇ mesaj gelmezse coil'i disconnected işaretle. Geniş eşik → normal yayın
# aralığında yanlış-alarm yok; sonraki ESP mesajı gelince connected=True'ya KENDİ düzelir. Yalnız ESP
# bobinlerine dokunur (STM 1-5 zaten _sync_stm_coils'ten türer). Timestamp yalnız gerçek MQTT mesajında
# yazılır → PEMF_SIMULATE modda sözlük boş kalır, watchdog no-op (sim coil'lerini bozmaz).
_coil_last_telemetry: dict = {}
ESP_STALE_SEC = 30.0
ESP_WATCHDOG_INTERVAL_SEC = 5.0


def _esp_telemetry_watchdog():
    while True:
        try:
            now = time.monotonic()
            changed = []
            with _live_state_lock:
                for cid in ESP_COIL_IDS:
                    idx = cid - 1
                    if not (0 <= idx < 8):
                        continue
                    last = _coil_last_telemetry.get(idx)
                    coil = _live_state["coils"][idx]
                    # Yalnız: telemetri ALMIŞ (last var) + hâlâ connected + GENİŞ eşik sustu → demote.
                    if last is not None and coil.get("connected") and (now - last) > ESP_STALE_SEC:
                        coil["connected"] = False
                        coil["running"] = False
                        changed.append((cid, dict(coil)))
            # DENETIM P2: bobin YALNIZCA "durdu" ISARETLENIYORDU; gercek bir STOP komutu
            # GONDERILMIYORDU. ESP guc kaybiyla degil de WiFi/broker kopmasiyla sessizlestiyse
            # kendisi hala son `start` komutuyla SURUYOR olabilir (kendi duration'i bitene dek).
            # Bu durumda UI "durdu" gosterirken bobin fiziksel olarak enerjili kalirdi — tam da
            # operatore yanlis guvence veren desen. Broker'a ulasilabiliyorsa STOP yayinla:
            # ESP geri geldiginde retained/yeniden-baglanma ile komutu alir.
            # 2. tur [5.8] (sahip onayi 2026-08-20): publish SONUCU okunur — probe False doner,
            # istisna ATMAZ; eski bildirim broker cokukken de "STOP gonderildi" diyordu (yanlis
            # guvence, 1. turun sahte-"durduruldu" sinifi) ve "log'a dusulur" vaadi bos kaliyordu.
            for cid, snap in changed:
                stop_gitti = False
                try:
                    stop_gitti = bool(
                        _mqtt_publish(
                            f"pemf/coil/{cid}/control",
                            {
                                "command": "stop",
                                "command_id": f"stale_{cid}_{int(time.time() * 1000)}",
                                "reason": "telemetry_stale",
                            },
                        )
                    )
                except Exception:
                    logging.getLogger(__name__).warning(
                        "esp watchdog: bobin %s STOP publish edilemedi", cid, exc_info=True
                    )
                _ws_broadcast_sync({"type": "coil_status", "coilId": cid, "data": snap})
                if stop_gitti:
                    _push_notification(
                        f"⚠️ Bobin {cid} telemetrisi yanıt vermiyor — bağlantı kesildi sayıldı, STOP gönderildi",
                        "warning",
                    )
                else:
                    logging.getLogger(__name__).warning(
                        "esp watchdog: bobin %s STOP publish DOĞRULANAMADI (broker erişilemez olabilir)", cid
                    )
                    _push_notification(
                        f"⚠️ Bobin {cid} telemetrisi yanıt vermiyor — bağlantı kesildi sayıldı; "
                        "STOP GÖNDERİLEMEDİ (broker erişilemiyor) — bobin HÂLÂ ENERJİLİ olabilir, elle kontrol edin",
                        "error",
                    )
        except Exception:
            logging.exception("esp telemetry watchdog error")
        time.sleep(ESP_WATCHDOG_INTERVAL_SEC)


def _on_mqtt_message_api(client, userdata, msg):
    try:
        topic_parts = msg.topic.split("/")
        is_retained = getattr(msg, "retain", False)

        if msg.topic == "pemf/bridge/status":
            connected = msg.payload.decode("utf-8", errors="ignore").strip() in ("1", "true", "connected")
            with _live_state_lock:
                _live_state["gateway"] = "online" if connected else "offline"
            _ws_broadcast_sync({"type": "gateway_status", "data": {"gateway": _live_state["gateway"]}})
            return

        if len(topic_parts) >= 3 and topic_parts[1] == "gateway":
            payload = json.loads(msg.payload.decode("utf-8"))
            with _live_state_lock:
                _live_state["gateway"] = payload.get("status", "offline")
            _ws_broadcast_sync({"type": "gateway_status", "data": {"gateway": _live_state["gateway"]}})
            return

        payload = json.loads(msg.payload.decode("utf-8"))

        if len(topic_parts) >= 4 and topic_parts[1] == "coil":
            coil_id_str = topic_parts[2]
            msg_type = topic_parts[3]
            if not coil_id_str.isdigit():
                return
            coil_index = int(coil_id_str) - 1
            if not (0 <= coil_index < 8):
                return
            # ESP watchdog: bu bobinden HERHANGİ gerçek mesaj = canlı → staleness timestamp'ını tazele.
            # (Explicit wifi_disconnected/offline zaten connected=False yapar → watchdog onu atlar.)
            # ⚠️ `not is_retained` ŞART (2026-08-19, HG-4 denetimi): firmware bazı konuları retain=true
            # yayınlıyor (8266 status:235 + iki ESP'nin ack'i). Broker'da kalmış RETAINED bir mesaj,
            # backend her reconnect'inde teslim edilir; onu "canlı telemetri" sayıp damgayı tazelemek,
            # OFFLINE bir bobinin stale-STOP tespitini ESP_STALE_SEC (30 sn) geciktirir. Yalnız CANLI
            # (retain=0) mesaj bobinin gerçekten yayın yaptığını kanıtlar.
            if not is_retained:
                _coil_last_telemetry[coil_index] = time.monotonic()

            if msg_type == "sensors" and not is_retained:
                with _live_state_lock:
                    coil = _live_state["coils"][coil_index]
                    coil["objectTemp"] = round(float(payload.get("object_temp", 0.0)), 1)
                    coil["ambientTemp"] = round(float(payload.get("ambient_temp", 0.0)), 1)
                    coil["currentA"] = round(float(payload.get("current", 0.0)), 3)
                    coil["magneticMt"] = round(float(payload.get("magnetic_field", 0.0)), 2)
                    coil["connected"] = True
                    snapshot = dict(coil)
                _ws_broadcast_sync(
                    {"type": "sensor_data", "coilId": int(coil_id_str), "data": snapshot, "timestamp": time.time()}
                )

            elif msg_type == "status" and not is_retained:
                with _live_state_lock:
                    coil = _live_state["coils"][coil_index]
                    # DENETIM 2. TUR [1.2] (2026-08-20): `connected` ESKIDEN yalniz
                    # `payload["status"]` DIZESINDEN turetiliyordu — ama depodaki iki firmware'in
                    # publishStatus'u da `status` alani YAYINLAMAZ (S3 NetworkManager.cpp:604-672,
                    # 8266 :210-226; parite kapisi tests/test_esp_status_sozlesmesi.py bunu
                    # kaynakta kilitler). Sonuc: her CANLI status mesaji connected=False yaziyordu;
                    # S3 hic `sensors` yayinlamadigi icin (UYUMSUZ-6) bobin 6-7 KALICI "baglanti
                    # yok" gorunuyor, panel kontrolleri kilitleniyor ve asagidaki
                    # `_esp_telemetry_watchdog` (yalniz connected=True bobini stale-STOP'lar)
                    # S3 icin HIC calismiyordu. CANLI (retain=0; dal kosulu yukarida) status
                    # mesajinin kendisi cihazin yasadiginin kanitidir → varsayilan connected=True.
                    # ESKI firmware'in ACIK dize sinyali ise korunur ve varsayilani EZER
                    # ("offline" diyen cihaza inat canli denmez — karsit-kanit testiyle kilitli).
                    status = payload.get("status")
                    if status is not None:
                        coil["connected"] = status in ("online", "ready", "running")
                        coil["running"] = status == "running"
                    else:
                        coil["connected"] = True
                    if "frequency" in payload:
                        coil["frequencyHz"] = payload["frequency"]
                    # DENETIM 2. TUR [1.2]: duty uc ayri anahtarla geliyor — eski firmware
                    # `duty_cycle`, 8266 `pwm_duty_cycle`, S3 `pwm_duty`. Yalniz ilki okunuyordu →
                    # firmware'in DURUST efektif duty raporu (D-2) live-state'e ve oradan
                    # dakika-akumulatoru uzerinden DOZ KAYDINA (`pwm_duty_percent`) hic ulasmiyor,
                    # ESP bobinlerinin doz satirlarina duty=0 yaziliyordu.
                    # Oncelik EFEKTIF degerlerde (adversaryal review, 2026-08-20): pwm_* anahtarlari
                    # firmware'in D-2 "durust rapor"udur (kirpma/yuvarlama SONRASI gercek cikis);
                    # `duty_cycle` eski filonun/komutlananin adi. Ikisi birden gelirse efektif kazanir.
                    for _duty_anahtari in ("pwm_duty", "pwm_duty_cycle", "duty_cycle"):
                        if _duty_anahtari in payload:
                            coil["dutyCycle"] = payload[_duty_anahtari]
                            break
                    if "pwm_active" in payload:
                        coil["running"] = bool(payload["pwm_active"])
                    if "pwm_frequency" in payload:
                        coil["frequencyHz"] = payload["pwm_frequency"]

                    # TOLERANSLI sayi donusumu (adversaryal review #3): S3 sicaklik sensoru
                    # arizasinda readObjectTempC NaN doner ve ArduinoJson NaN'i `null` yazar —
                    # dogrudan float(None) TypeError'i TUM mesaj islemeyi yarida kesiyordu
                    # (connected/duty uygulanmis, current/ambient + WS + reconcile ATLANMIS).
                    # Bozuk tek alan yalniz KENDINI dusurur; 0-nobetcisi yazilmaz (bkz.
                    # CoilThermalHonesty: 0 "serin" okunur, null bir olcum DEGILDIR).
                    def _sayi(anahtar):
                        try:
                            return float(payload[anahtar])
                        except (KeyError, TypeError, ValueError):
                            return None

                    _ot = _sayi("object_temp")
                    if _ot is not None:
                        coil["objectTemp"] = round(_ot, 1)
                    _mf = _sayi("magnetic_field")
                    if _mf is not None:
                        coil["magneticMt"] = round(_mf, 2)
                    # DENETIM 2. TUR [1.2](c): S3 sensors mesajini kaldirdi ("UYUMSUZ-6") —
                    # current/ambient S3'te YALNIZ status icinde gelir; okunmazsa doz/KPI 0 gorur.
                    # (sensors dalindaki yuvarlama hassasiyetleriyle birebir ayni.)
                    _cur = _sayi("current")
                    if _cur is not None:
                        coil["currentA"] = round(_cur, 3)
                    _amb = _sayi("ambient_temp")
                    if _amb is not None:
                        coil["ambientTemp"] = round(_amb, 1)
                    snapshot = dict(coil)
                _ws_broadcast_sync({"type": "coil_status", "coilId": int(coil_id_str), "data": snapshot})
                # HG-6 (Plan A-3): hedefli reconcile — ESP "çalışıyor" diyor ama backend niyeti/
                # aktif seans kapsamıyor ise arka planda hedefli STOP (NVS/EEPROM resume + kayıp
                # offline-STOP senaryosu). RETAINED status'a asla tepki verme (8266 status'u
                # retain=true yayınlar; bayat "running" sahte reconcile tetiklemesin).
                if not is_retained:
                    _reconcile_esp_calisiyor(int(coil_id_str), snapshot)

            elif msg_type == "ack":
                # HG-4 (2026-08-19): ESP komut onayı → command_id ile bekleyen E-stop'u çöz.
                # ⚠️ RETAINED FİLTRESİ YOK — bilerek. Firmware ack'i retain=true yayınlar (8266:767 /
                # S3:782). MQTT-3.3.1-9: broker, KURULU bir aboneliğe canlı teslimde retain'i 0'lar →
                # yani canlı ack backend'e retain=0 gelir; retain=1 yalnız reconnect'te broker'ın
                # sakladığı BAYAT ack'te görülür. Bayat ack'e karşı koruma is_retained DEĞİL,
                # command_id BENZERSİZLİĞİdir: her E-stop yeni `estop_{coil}_{ms}` üretir; bayat ack
                # eski id taşır → _resolve_ack onu pending'de BULAMAZ → no-op. (Bu dal telemetri
                # damgasını tazelemez — o koruma yukarıda; ack yalnız pending çözer.)
                _cid = payload.get("command_id")
                if _cid:
                    _resolve_ack(str(_cid), bool(payload.get("success", False)))

            elif msg_type == "events":
                # D-4 (2026-08-19): RETAINED events YOK SAY. ESP LWT'si (last-will) retain=true
                # yayınlanıyor (S3 + artık 8266). Bobin ANİ koparsa broker LWT'yi CANLI (retain=0,
                # MQTT-3.3.1-9) yayınlar → işlenir; ama backend RECONNECT'inde broker'ın sakladığı
                # BAYAT offline/online retained gelir ve o an online olan bobini "koptu" sanabilir.
                # Canlı durum yalnız retain=0 events'tir (sensor/status telemetrisi zaten connected=True yapar).
                if is_retained:
                    return
                event_type = payload.get("type") or payload.get("event_type", "unknown")
                # D-1 tamamlayıcısı (review, 2026-08-19 akşam): firmware selftest_ok/fail/skipped
                # event'leri yayınlıyor ama backend İŞLEMİYORDU → selftest endpoint'i koşulsuz
                # "success" döndüğünden ARIZALI bobin operatöre YEŞİL görünüyordu (yanlış tanısal
                # güvence — D-1'in düzelttiği şeyin zincirin öbür ucunda devamı).
                if event_type in ("selftest_ok", "selftest_fail", "selftest_skipped"):
                    _st_msg = str(payload.get("message") or payload.get("detail") or "")[:160]
                    if event_type == "selftest_fail":
                        logging.error("SELFTEST BAŞARISIZ bobin %s: %s", coil_id_str, _st_msg)
                        _push_notification(f"🚨 Bobin {coil_id_str} self-test BAŞARISIZ — {_st_msg}", "error")
                    else:
                        logging.info("selftest bobin %s: %s (%s)", coil_id_str, event_type, _st_msg)
                        _push_notification(
                            f"Bobin {coil_id_str} self-test: "
                            + ("geçti" if event_type == "selftest_ok" else "atlandı (PWM pasif)"),
                            "success" if event_type == "selftest_ok" else "info",
                        )
                    _ws_broadcast_sync(
                        {
                            "type": "selftest_result",
                            "coilId": int(coil_id_str),
                            "data": {"result": event_type, "message": _st_msg},
                        }
                    )
                    return
                # DENETIM 2. TUR [4.2] (2026-08-20): iki firmware de yerel TERMAL korumada event
                # yayinliyor (S3 .ino:80 thermal_stop; 8266 .ino:361/368/493 stop+unlock+lock) ama
                # backend bunlari ISLEMIYORDU → cihazin en onemli yerel guvenlik eylemi operatore
                # gorunmuyordu: bobin "sebepsiz durdu" sanilir, termal kilit surerken start redleri
                # aciklamasiz kalirdi (D-1 selftest duzeltmesinin zincirin obur ucundaki ikizi).
                # RETAINED filtresi yukarida (bayat termal olay reconnect'te alarm uretmez).
                # Ad paritesi firmware kaynagiyla kilitli: tests/test_termal_olay_gorunurlugu.py
                if event_type in ("thermal_stop", "thermal_lock", "thermal_unlock"):
                    _termal_msg = str(payload.get("message") or payload.get("detail") or "")[:160]
                    if event_type == "thermal_stop":
                        logging.error("YEREL TERMAL KESME bobin %s: %s", coil_id_str, _termal_msg)
                        _push_notification(
                            f"🔥 Bobin {coil_id_str} YEREL TERMAL KESME — PWM cihaz tarafından durduruldu"
                            + (f" ({_termal_msg})" if _termal_msg else "")
                            + "; 45°C altına soğuyunca start serbest",
                            "error",
                        )
                    elif event_type == "thermal_lock":
                        _push_notification(
                            f"⚠️ Bobin {coil_id_str} sıcak: start reddedildi — soğuması bekleniyor"
                            + (f" ({_termal_msg})" if _termal_msg else ""),
                            "warning",
                        )
                    else:
                        _push_notification(f"✅ Bobin {coil_id_str} soğudu — start yeniden serbest", "success")
                    _ws_broadcast_sync(
                        {
                            "type": "thermal_event",
                            "coilId": int(coil_id_str),
                            "data": {"event": event_type, "message": _termal_msg},
                        }
                    )
                    return
                # [4.5] NACK YARISI (2026-08-22): iki firmware de komut reddinde `command_error`
                # eventi yayinliyor (8266 .ino:458 rate-limit / :527 validation / :605 unknown;
                # her red ayrica ack success=false gonderir) ama backend bu tipi HIC islemiyordu →
                # ESP'nin acik reddi ve SEBEBI operatore gorunmuyordu. Kosu-kaydi duzeltmesi ack
                # bekcisinde ( _start_ack_watch ) — bu dal yalniz GORUNURLUK: bildirim + WS.
                # RETAINED filtresi yukarida (bayat red reconnect'te alarm uretmez).
                if event_type == "command_error":
                    _ce_msg = str(payload.get("message") or payload.get("detail") or "")[:160]
                    logging.error("Bobin %s KOMUTU REDDETTI (NACK): %s", coil_id_str, _ce_msg)
                    _push_notification(
                        f"⚠️ Bobin {coil_id_str} komutu REDDETTİ — {_ce_msg or 'sebep bildirilmedi'}",
                        "error",
                    )
                    _ws_broadcast_sync(
                        {
                            "type": "command_error",
                            "coilId": int(coil_id_str),
                            "data": {"message": _ce_msg},
                        }
                    )
                    return
                if event_type in ("wifi_disconnected", "offline"):
                    with _live_state_lock:
                        _live_state["coils"][coil_index]["connected"] = False
                        _live_state["coils"][coil_index]["running"] = False
                    _push_notification(f"⚠️ Bobin {coil_id_str} bağlantısı kesildi", "warning")
                elif event_type == "wifi_connected":
                    with _live_state_lock:
                        _live_state["coils"][coil_index]["connected"] = True
                    _push_notification(f"✅ Bobin {coil_id_str} bağlandı", "success")

            elif msg_type == "alarm":
                # ESP firmware'inin KENDİ güvenlik alarmı (overtemp / safety_violation / overcurrent).
                # Backend eşik dayatmaz; donanım "tehlikedeyim" dediğinde TÜM bobinleri durdurur.
                #
                # DENETIM P3: RETAINED filtresi yoktu. Broker'da kalmis ESKI bir retained alarm,
                # her MQTT yeniden-baglanmasinda (broker restart / ag dalgalanmasi) yeniden teslim
                # edilip acil-durdurma tetikliyordu → suren tedavi durdurulur, operator sebebi
                # goremez ("hayalet alarm"). Sensor dalinda (yukarida) `not is_retained` kosulu
                # ZATEN vardi; alarm dali unutulmustu. Retained mesaj GECMISTEKI bir durumdur,
                # CANLI bir tehlike bildirimi degil → yok say ama GORUNUR logla (fail-safe yon
                # kaybi yok: gercek/canli alarm retain'siz gelir).
                if is_retained:
                    logging.warning(
                        "ESP bobin %s icin RETAINED alarm alindi → acil-durdurma TETIKLENMEDI "
                        "(broker'da kalmis eski mesaj; canli alarm retain'siz gelir).",
                        coil_id_str,
                    )
                    return
                atype = payload.get("type") or payload.get("alarm") or payload.get("reason") or "alarm"
                logging.error("ESP ALARM bobin %s: %s -> tum bobinler durduruluyor", coil_id_str, atype)
                _push_notification(f"🚨 Bobin {coil_id_str} ALARM ({atype}) — seans güvenlik için durduruldu", "error")
                try:
                    _emergency_stop_async(reason=f"esp_alarm_{coil_id_str}_{atype}", mode="ESP Güvenlik Alarmı")
                except Exception:
                    logging.exception("ESP alarm STOP failed")

    except Exception as _e:
        # Audit #23: eskiden 'except: pass' ile sessizce yutuluyordu → bozuk/beklenmedik MQTT
        # mesajları (örn. coil status güncellenememesi) görünmezdi. Artık WARN'la (özet, traceback'siz).
        logging.getLogger(__name__).warning("MQTT on_message islenemedi (topic=%s): %s", getattr(msg, "topic", "?"), _e)


# ── MQTT istemci kimligi ─────────────────────────────────────────────────────
# MQTT sozlesmesi geregi AYNI client_id ile yeni bir baglanti gelirse broker ONCEKI oturumu
# DUSURUR. Sabit kimlikler ("api_server_ws_listener" / "api_server_pub") iki gercek arizaya
# yol aciyordu:
#
#   1) DINLEYICI — yeniden baslatma/OTA penceresinde eski surecin oturumu brokerde bir sure
#      yasar: yeni surec baglanir → eski dusurulur → eski otomatik yeniden baglanir → yeni
#      dusurulur... Sonuc: bitmeyen "Sistem baglantisi kesildi/kuruldu" bildirimi ve o sure
#      boyunca ESP telemetrisinde bosluk. (E2E 2026-08-06'da iki backend ile gozlendi.)
#
#   2) YAYINCI — _mqtt_publish HER cagride yeni istemci acar ve _emergency_stop_all, ESP
#      bobinlerine ThreadPoolExecutor ile PARALEL yayin yapar (bobin basina 2 publish).
#      Ucu de ayni kimligi kullandigindan broker sonuncu disindakileri DUSURUR → acil-durdurma
#      STOP komutu KAYBOLABILIR. Bu bir HASTA GUVENLIGI yolu: kimlik cagri basina benzersiz olmali.
#
# Kimlik <=23 karakterde tutulur (MQTT 3.1 doneminden kalma brokerlarin client_id siniri).
_MQTT_PUB_SEQ = _itertools.count(1)


def _mqtt_client_id(role: str) -> str:
    """Surece ozgu (yayinci ve bulut-aynasi icin cagriya da ozgu) MQTT client_id."""
    if role == "pub":
        return f"pemf_pub_{os.getpid()}_{next(_MQTT_PUB_SEQ) % 100000}"
    if role == "estop-cloud":
        # ── [3.3] 2. tur denetimi (duzeltme 2026-08-22) ──────────────────────────────
        # Bu rol eskiden asagidaki genel `pemf_{role}_{pid}` kalibina dusuyordu. Iki ariza:
        #   1) SUREC-SABIT: E-stop cifte tetiginde (panik aninda gercekci) iki ayna oturumu
        #      HiveMQ'ya AYNI kimlikle baglanir → broker ILKINI DUSURUR → ucustaki STOP
        #      publish'leri kaybolabilir. 'pub' rolunde cozulen arizanin birebir aynisi,
        #      yalniz BULUT yolunda.
        #   2) UZUNLUK: "pemf_estop-cloud_" = 17 karakter; Linux pid_max=4194304 (7 hane)
        #      ile kimlik 24'e tasar → eski brokerlarin 23-karakter siniri asilir,
        #      baglanti REDDEDILIR ve ayna SESSIZCE hic calismaz.
        # Kisa rol adi ("esc") + pid%100000 + cagri sayaci: en kotu durumda
        # 9 + 5 + 1 + 5 = 20 <= 23. Sayac 'pub' ile paylasilir — amac benzersizlik,
        # kaynak farki degil. Kilit: tests/test_mqtt_client_id.py [3.3] bolumu.
        return f"pemf_esc_{os.getpid() % 100000}_{next(_MQTT_PUB_SEQ) % 100000}"
    return f"pemf_{role}_{os.getpid()}"


def _start_mqtt_for_api() -> None:
    global _mqtt_client_api
    try:
        import paho.mqtt.client as _mqtt

        # ⚠️ BİLEREK VERSION1 (2026-08-15) — yayıncı istemci V2'ye geçti, bu GEÇMEDİ.
        # Sebep: bu istemcinin ÜÇ geri çağrısı var (`on_connect`/`on_disconnect`/`on_message`) ve
        # V2 imzaları değiştirir (`rc` → `reason_code` + `properties`). Bu geri çağrılar ESP
        # telemetrisi ve ACİL DURDURMA yolundadır ve HİÇBİR TESTLE KAPSANMIYOR. Test kapsamı
        # olmayan bir güvenlik yolunda imza değiştirmek, doğrulanmamış risktir; sessizce
        # bozulursa bunu ancak sahada fark ederiz.
        # Sürümü AÇIKÇA vermek uyarıyı susturur ve davranışı DEĞİŞTİRMEZ.
        # ⚠️ KALICI ÇÖZÜM DEĞİLDİR: paho V1'i eninde sonunda kaldıracak. Geçiş için önce bu üç
        # geri çağrıya test yazılmalı (özellikle `_on_mqtt_message_api` → bobin telemetrisi),
        # sonra imzalar V2'ye çevrilmeli.
        _mqtt_client_api = _mqtt.Client(
            _mqtt.CallbackAPIVersion.VERSION1, client_id=_mqtt_client_id("ws"), clean_session=True
        )
        _u, _pw = _mqtt_credentials()
        if _u:
            _mqtt_client_api.username_pw_set(_u, _pw)  # broker auth açıksa kimlik gönder
        _mqtt_client_api.on_connect = _on_mqtt_connect_api
        _mqtt_client_api.on_disconnect = _on_mqtt_disconnect_api
        _mqtt_client_api.on_message = _on_mqtt_message_api
        # Async connect + loop: broker GEÇ açılırsa da otomatik yeniden dener. Eskiden ilk connect
        # başarısız olunca listener kalıcı ölüydü → ESP telemetrisi WS'e hiç ulaşmazdı.
        _mqtt_client_api.reconnect_delay_set(min_delay=2, max_delay=30)
        _mqtt_client_api.connect_async("127.0.0.1", 1883, 60)
        _mqtt_client_api.loop_start()
    except Exception as e:
        logging.warning(f"MQTT dinleyici başlatılamadı: {e}")


# B-2.2: _build_ws_snapshot + update_live_stm_status/coil_from_stm/session_state → servers/live_state.py (üstte alias'landı).


_event_bus_registered = False


def _handle_backend_event(event) -> None:
    """Route core EventBus events into FastAPI live-state/WebSocket."""
    data = event.data or {}
    if event.event_type == "hardware.stm.connected":
        update_live_stm_status(True)
        return
    if event.event_type == "hardware.stm.disconnected":
        update_live_stm_status(False)
        # GÜVENLİK: STM koptu → bobin durumunu sıfırla (reconnect'te eski freq/duty ile RE-FIRE
        # etmesin) + STM kullanan aktif seansı durdur (kontrolsüz bobin kalmasın).
        try:
            if state.hardware:
                state.hardware.on_disconnect()
        except Exception:
            logging.exception("STM on_disconnect failed")
        with _session_lock:
            _sess_active = bool(_active_session.get("is_active"))
            _sess_coils = _active_session.get("coil_ids") or list(range(1, 9))
        if _sess_active and any(c in STM_COIL_IDS for c in _sess_coils):
            logging.error("STM baglanti kaybi: STM kullanan aktif seans durduruluyor (guvenlik).")
            _push_notification("⚠️ STM32 bağlantısı koptu — seans güvenlik için durduruldu", "error")
            try:
                _emergency_stop_async(reason="stm_disconnected", mode="STM Bağlantı Kaybı")
            except Exception:
                logging.exception("STM disconnect STOP failed")
        return
    if event.event_type == "hardware.stm.coil_update":
        update_live_coil_from_stm(
            coil_id=int(data.get("coil_id", 0)),
            duty=float(data.get("duty", data.get("duty_cycle", 0.0))),
            freq=float(data.get("freq", data.get("frequency", 0.0))),
            phase=float(data.get("phase", 0.0)),
            duration_min=int(data.get("duration_min", data.get("duration", 0))),
            running=bool(data.get("running", data.get("pwm_active", False))),
        )
        return
    if event.event_type == "hardware.stm.watchdog_timeout":
        # STM firmware watchdog'u ateşledi → STM PWM'i BİLİNMEYEN/durmuş durumda (komuta uymuyor). Bu bir
        # donanım-fault EVENT'i (backend EŞİK DAYATMAZ; donanımın kararına tepki verir) → STM kullanan aktif
        # seansı güvenli durdur + state'i eşitle. Aksi halde UI 'çalışıyor' gösterir ama STM durmuştur (desync).
        _push_notification("⚠️ STM32 watchdog zaman aşımı — seans güvenlik için durduruldu", "error")
        with _session_lock:
            _sess_active = bool(_active_session.get("is_active"))
            _sess_coils = _active_session.get("coil_ids") or list(range(1, 9))
        if _sess_active and any(c in STM_COIL_IDS for c in _sess_coils):
            try:
                _emergency_stop_async(reason="stm_watchdog_timeout", mode="STM Watchdog")
            except Exception:
                logging.exception("STM watchdog STOP failed")
        return
    if event.event_type in {"hardware.stm.error", "hardware.stm.nack"}:
        _push_notification(str(data.get("message", event.event_type)), "error")
        return
    if event.event_type == "mqtt.broker.status":
        mqtt_state = "online" if data.get("port_open") or data.get("running") else "warning"
        with _live_state_lock:
            _live_state["mqtt"] = mqtt_state
            gateway_state = _live_state["gateway"]
        _ws_broadcast_sync({"type": "gateway_status", "data": {"gateway": gateway_state, "mqtt": mqtt_state}})
        return
    if event.event_type == "network.status":
        mode = data.get("gateway_mode", "unknown")
        gateway_state = "online" if mode in ("online", "hybrid") else "offline"
        with _live_state_lock:
            _live_state["gateway"] = gateway_state
            if data.get("mqtt_broker_reachable"):
                _live_state["mqtt"] = "online"
            mqtt_state = _live_state["mqtt"]
        _ws_broadcast_sync(
            {
                "type": "gateway_status",
                "data": {"gateway": gateway_state, "mqtt": mqtt_state, "network": data},
            }
        )
        return
    if event.event_type in {"mqtt.broker.error", "discovery.error"}:
        _push_notification(str(data.get("message", event.event_type)), "warning")


def _register_event_bus_handlers() -> None:
    global _event_bus_registered
    if _event_bus_registered:
        return
    try:
        from event_bus import subscribe

        subscribe("hardware.stm.*", _handle_backend_event, "api_server.hardware_stm")
        subscribe("mqtt.broker.*", _handle_backend_event, "api_server.mqtt_broker")
        subscribe("network.status", _handle_backend_event, "api_server.network_status")
        subscribe("discovery.*", _handle_backend_event, "api_server.discovery")
        _event_bus_registered = True
    except Exception as exc:
        logging.warning("EventBus handler registration failed: %s", exc)


# Global State Container
class APIState:
    def __init__(self):
        self.core: HeadlessCore = None
        self.hardware: HardwareController = None


state = APIState()

# NOT (audit B-2.2): startup/shutdown mantığı yukarıdaki `lifespan` context-manager'ına taşındı
# (deprecated @app.on_event kaldırıldı). Arka-plan thread'leri artık import anında DEĞİL, lifespan
# startup'ta başlar (state.core/hardware backend_service._wire_api_server ile SET EDİLDİKTEN sonra).


def _start_mdns_service() -> None:
    """mDNS (Zeroconf) servisini ayrı thread'de başlatır."""
    try:
        from servers.auto_discovery import get_api_port, start_mdns

        # ⚠️ SABİT 8000 DEĞİL (denetim 2026-08-17): launcher boş port arıyor, staging 8010
        # kullanıyor. 8000 meşgulken mDNS yanlış portu yayınlıyor ve telefon oraya bağlanıyor.
        start_mdns(port=get_api_port(), device_name="PEMF-Vet")
    except Exception as e:
        logging.warning("mDNS başlatılamadı: %s", e)


# ── WebSocket Endpoint (/ws) ───────────────────────────────────────
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Tek port (8000) üzerinden canlı sensör verisi WebSocket bağlantısı."""
    # P1 audit 2026-06-28: FAIL-CLOSED. Eskiden auth istisnasi except'e dusup KOSULSUZ accept()
    # ediyordu (kimliksiz WS kabul). Artik istisnada baglanti KAPATILIR (sessiz bypass YOK).
    try:
        from servers.auth import check_token, is_local_request, require_auth

        required = bool(require_auth())
    except Exception:
        logging.exception("WS auth katmani yuklenemedi (FAIL-CLOSED)")
        await websocket.close(code=1011)  # internal error
        return
    # YEREL/LAN WS de auth MUAF (token yalniz tunel/uzak — Cloudflare header'li)
    _wh = websocket.headers
    _ws_via_proxy = bool(_wh.get("cf-connecting-ip") or _wh.get("cf-ray") or _wh.get("x-forwarded-for"))
    # Cross-origin CSRF (audit P2 #1): tarayıcı WS'inde Origin GELİR. DOĞRUDAN (proxy'siz) LAN'da
    # Origin host'u Host ile eşleşmezse, başka-origin bir kötücül web sayfası cihaza WS açıyordur →
    # reddet. Native mobil Origin GÖNDERMEZ → serbest. Proxy/tünelde Host/Origin güvenilmez +
    # token-auth zaten zorunlu → orada uygulanmaz (yanlış-pozitif tünel erişimini kırmasın).
    _ws_origin = _wh.get("origin")
    if _ws_origin and not _ws_via_proxy:
        try:
            from urllib.parse import urlparse as _urlparse

            _o_host = (_urlparse(_ws_origin).hostname or "").lower()
            _h_host = (_wh.get("host") or "").rsplit(":", 1)[0].lower()
            if _o_host and _h_host and _o_host != _h_host:
                await websocket.close(code=1008)  # policy violation (cross-origin)
                return
        except Exception:
            pass
    if required and is_local_request(websocket.client.host if websocket.client else "", _ws_via_proxy):
        required = False
    if required:
        try:
            tok = websocket.query_params.get("token") or websocket.headers.get("X-API-Key") or ""
            ok = check_token(tok)
        except Exception:
            logging.exception("WS token kontrol hatasi (FAIL-CLOSED)")
            ok = False
        if not ok:
            # accept() ÖNCE → close(1008) SONRA: aksi halde client handshake hatası (1006) görür ve
            # 1008'i (auth) ağ-kopmasından AYIRAMAZ → wsClient hot-loop'a girerdi (audit P0).
            try:
                await websocket.accept()
            except Exception:
                pass
            await websocket.close(code=1008)  # policy violation (auth)
            return
    await websocket.accept()
    with _ws_lock:
        _ws_clients.append(websocket)
    # DENETIM P3: ilk snapshot gonderimi try/finally'nin DISINDA idi. Istemci accept ile ilk
    # send_text arasinda koparsa (mobilde ekran-kilidi/ag gecisi siradan) send_text firlatir,
    # `finally: _ws_clients.remove(...)` HIC calismaz ve OLU soket yayin listesinde KALIR →
    # her broadcast onun icin 5 sn timeout bekler (tum filoyu yavaslatir) ve ancak o zaman
    # dusurulur. try bloguna ALINDI: hata olsa da temizlik garanti.
    try:
        # Bağlantı açıldığında anlık durumu gönder
        await websocket.send_text(json.dumps({"type": "snapshot", "data": _build_ws_snapshot()}, ensure_ascii=False))
        while True:
            data = await websocket.receive_text()
            # İstemciden gelen komutları işle (şimdilik ping/pong)
            try:
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
            except Exception:
                pass
    except WebSocketDisconnect:
        pass
    finally:
        with _ws_lock:
            try:
                _ws_clients.remove(websocket)
            except ValueError:
                pass


# --- REACT NATIVE (EXPO) ENDPOINT'LERİ ---


@app.get("/metrics")
async def metrics():
    """Prometheus-uyumlu metrikler (audit B-5.2) — sayısal zaman-serisi gözlemlenebilirliği.
    Harici bağımlılık YOK (elle text format → frozen EXE'yi şişirmez). YEREL/LAN scrape auth-muaf
    (Prometheus localhost'tan çeker), uzak scrape token ister (auth middleware). Ölçütler in-memory
    canlı durumdan türetilir (ek sayaç enstrümantasyonu gerektirmez)."""
    with _live_state_lock:
        coils = _live_state["coils"]
        connected = sum(1 for i in range(8) if coils[i].get("connected"))
        running = sum(1 for i in range(8) if coils[i].get("running"))
        mqtt_up = 1 if _live_state.get("mqtt") == "online" else 0
        stm_up = 1 if _live_state.get("stm") == "online" else 0
        gateway_up = 1 if _live_state.get("gateway") == "online" else 0
        notif = len(_live_state.get("notifications", []))
    with _session_lock:
        active = 1 if _active_session.get("is_active") else 0
    with _ws_lock:
        ws_clients = len(_ws_clients)
    m = [
        ("pemf_ws_clients", "Bagli WebSocket istemci sayisi", ws_clients),
        ("pemf_active_session", "Aktif seans (1/0)", active),
        ("pemf_coils_connected", "Bagli bobin sayisi", connected),
        ("pemf_coils_running", "Calisan bobin sayisi", running),
        ("pemf_mqtt_up", "MQTT broker baglantisi (1/0)", mqtt_up),
        ("pemf_stm_up", "STM32 baglantisi (1/0)", stm_up),
        ("pemf_gateway_up", "Gateway/ag baglantisi (1/0)", gateway_up),
        ("pemf_notifications", "Bekleyen bildirim sayisi", notif),
    ]
    lines = []
    for name, help_text, val in m:
        lines.append(f"# HELP {name} {help_text}")
        lines.append(f"# TYPE {name} gauge")
        lines.append(f"{name} {val}")
    return Response(content="\n".join(lines) + "\n", media_type="text/plain; version=0.0.4; charset=utf-8")


class CommandPayload(BaseModel):
    command: str
    params: dict = {}


# (audit B-2.2) PatientInput modeli servers/patient_router.py'ye taşındı (hasta uçlarıyla birlikte).


class AutoPresetPayload(BaseModel):
    target_condition: str


class SessionStartPayload(BaseModel):
    patient_id: str = ""
    patient_name: str = ""
    operator_name: str = ""  # denetim izi — seansı başlatan operatör (audit P1)
    operator_email: str = ""  # klinik-içi sahiplik — seansı başlatan hekim e-postası ("Benim/Tüm Klinik")
    mode: str = "Manuel"  # Manuel | Otomatik | AI
    target_condition: str = ""
    frequency: float = 50.0
    duty: float = 25.0
    intensity: float = 25.0
    phase: float = 0.0
    # ge=1: süre 0/negatif olursa auto-end mantığı (total>0) hiç tetiklenmez → seans SONSUZ sürerdi.
    # Bu bir SÜRE (seans-uzunluğu) doğrulaması; frekans/duty/intensity TEDAVİ parametrelerine DOKUNULMADI.
    duration_minutes: int = Field(default=20, ge=1)
    # DENETIM P1 (thread-bombasi): tip `list` idi (eleman tipi/uzunluk kisiti YOK) →
    # {"coil_ids": [6]*20000} ESP bobin basina AYRI daemon-thread aciyordu (her biri socket
    # connect + paho connect) → 'can't start new thread' / handle tukenmesi; ayni anda suren
    # gercek tedavide sure-watchdog aclik cekip bobinler planlanandan uzun enerjili kalabilirdi.
    # /api/coil/batch zaten `_seen[:8]` ile sertlestirilmisti, start yolu unutulmustu.
    # Cihazda toplam 8 bobin var → 8'den uzun liste MESRU DEGIL, sinirda 422 ile reddedilir.
    # list[int]: tip-disi eleman artik sessizce "tedavi yok"a dusmek yerine 422 verir.
    coil_ids: list[int] = Field(default_factory=list, max_length=8)  # empty = all coils


# ⚠️ `duration` NEGATIF OLAMAZ (kampanya bulgusu S03, 2026-08-14). Eskiden dogrulama YOKTU:
# `duration=-60` sessizce kabul ediliyor, `_duration_seconds_to_stm_minutes(-60)` 0 donduruyor ve
# komut "sure verilmemis" gibi davraniyordu → bir YAZIM HATASI bobini gozetimsiz varsayilan sure
# boyunca enerjili birakiyordu. `0` GECERLIDIR ("sure belirtme") ve reddedilmez; negatif deger
# anlamsizdir ve 422 ile geri cevrilir. (Seans modeli zaten `Field(ge=1)` ile dogruluyordu; bobin
# yolu bu korumadan yoksundu.)
class CoilControlPayload(BaseModel):
    freq: float = 50.0
    duty: float = 25.0
    phase: float = 0.0
    duration: int = Field(default=0, ge=0)  # seconds for ESP/MQTT payloads
    start: bool = True


class BatchCoilPayload(BaseModel):
    coil_ids: list[int]  # e.g. [1,2,3]
    freq: float = 50.0
    duty: float = 25.0
    phase: float = 0.0
    duration: int = Field(default=0, ge=0)  # seconds for ESP/MQTT payloads
    start: bool = True


_seans_muhru_kilit = threading.Lock()
_seans_muhru_sayac = 0


def _yeni_seans_muhru() -> str:
    """API seans mührü — `react_<epoch_ms>_<sayac>`.

    ⚠️ ESKİDEN `react_<epoch SANİYE>` idi ve AYNI SANİYEDE başlatılan iki farklı seans AYNI
    mührü alıyordu (kampanya bulgusu S11, ölçüldü). `session_events` kayıtlarındaki
    `payload.ref` bu mühürdür; çakışınca "bu denetim kaydı hangi seansa ait?" sorusu CEVAPSIZ
    kalır — bir istismar incelemesinde atfedilebilirlik yoksa iz işe yaramaz.

    Milisaniye TEK BAŞINA yetmez (hızlı durdur/başlat aynı ms'e düşebilir) → süreç-içi artan
    sayaç eklenir. Mühür artandır: denetimde olaylar kronolojik sıralanabilir.

    ⚠️ `react_` ÖN-EKİ KORUNUR — mevcut testler ve tüketiciler `startswith` ile bakar.
    """
    global _seans_muhru_sayac
    with _seans_muhru_kilit:
        _seans_muhru_sayac += 1
        return f"react_{int(time.time() * 1000)}_{_seans_muhru_sayac}"


def _duration_seconds_to_stm_minutes(duration_seconds: int) -> int:
    """Convert web/API ESP duration seconds to STM firmware duration minutes."""
    try:
        seconds = int(duration_seconds)
    except (TypeError, ValueError):
        return 0
    if seconds <= 0:
        return 0
    return max(1, (seconds + 59) // 60)


def _esp_duration_seconds(duration_seconds: int) -> int:
    """ESP (bobin 6-8) MQTT `duration` alanini SANIYE olarak cozer; gozetimsiz kapagi uygular.

    ⚠️ DENETIM BULGUSU 2026-08-17 — KISMI DUZELTME TAMAMLANDI. `duration = 0` bu projenin KENDI
    protokol sozlesmesinde **SURESIZ** demektir (`firmware/stm32_pemf/Core/Src/main.c`: "Süre (dakika): 0 = süresiz";
    `controllers/hardware_controller` ayni notu tasir). STM yolu bu nobetciyi 1.9.14'ten beri
    `GOZETIMSIZ_VARSAYILAN_DAKIKA`ya cevirir — ama ESP yolu onu HAM iletiyordu. Sonuc: 1.9.14'te
    BILINCLI eklenen klinik kapak 8 bobinin yalniz 5'ini kapsiyordu.

    ESP tarafinda sunucu-yanli hicbir son-tarih YOKTUR: `_coil_deadline` yalniz `range(1, 6)`,
    seans acilmadigi icin `_session_duration_watchdog` kapsam disi, `_esp_telemetry_watchdog`
    (bkz. asagi) yalniz telemetri SUSARSA devreye girer — saglikli yayin yapan bir ESP bobini
    kapaksiz kalirdi. Ustelik arayuz operatore "bobin donanim ust-sinirina kadar calisir" diye
    guvence veriyordu; ESP firmware'i o tarihte bu depoda DEGILDI, yani o guvencenin dayanagi
    yoktu. GUNCELLEME 2026-08-19: firmware artik depoda (firmware/esps3_pemf_coil +
    esp8266_pemf_coil) VE Plan A-1 ile cihazin KENDISI de suresiz modda 7200 sn KUMULATIF
    tavan uygular (SURESIZ_TAVAN_SEC — ayni 120 dk'dan turer). Bu fonksiyon backend-yanli
    ILK katman olarak DURUR (derinlemesine savunma; kaldirma).

    ⚠️ Sabit BURADA TANIMLANMAZ. Klinik sinir TEK KAYNAKTAN (`hardware_controller`) okunur ki iki
    transport bir gun ayrisamasin — bu bulgunun kok nedeni tam olarak o ayrisma idi.
    ⚠️ Yeni bir UST-SINIR DEGILDIR: acikca verilen sureye DOKUNULMAZ. `duration=0` de REDDEDILMEZ
    (Kontrol Paneli'ni bozardi); yalnizca sonsuz surmez.
    ⚠️ freq/duty/48°C safety-limit'leriyle ILGISI YOKTUR; onlar sahip karariyla kaldirildi ve GERI
    EKLENMEZ. Buradaki sinir yalniz SUREdir.

    Kilit: `tests/test_esp_gozetimsiz_sure_kapagi.py` (karsit-kanit testleri dahil).
    """
    from controllers.hardware_controller import GOZETIMSIZ_VARSAYILAN_DAKIKA

    try:
        seconds = int(duration_seconds)
    except (TypeError, ValueError):
        seconds = 0
    if seconds > 0:
        return seconds
    return GOZETIMSIZ_VARSAYILAN_DAKIKA * 60


# ── MQTT publish helper (used by headless and GUI-less mode) ─────────────────
import json as _json


def _mqtt_credentials():
    """Broker auth (allow_anonymous false) açıkken kullanılacak (kullanıcı, şifre) — env'den.
    Yapılandırılmamışsa (None, None) → anonim (geriye uyumlu). Üretimde PEMF_MQTT_USER/PASS ayarla."""
    try:
        from utils.secrets_manager import get_secret

        u = get_secret("mqtt_user")
        p = get_secret("mqtt_pass")
    except Exception:
        u = os.environ.get("PEMF_MQTT_USER", "").strip()
        p = os.environ.get("PEMF_MQTT_PASS", "")
    return (u or None, p or None)


def _mqtt_publish(topic: str, payload: dict) -> bool:
    """Publish a JSON payload to the local MQTT broker. Returns success.

    Broker kapalıyken paho.connect Windows'ta ~2sn bloke oluyordu (3 ESP bobin →
    seans başlatma ~8sn kilitleniyordu). Önce 0.3sn'lik hızlı socket probe ile
    broker erişilebilir mi bak; değilse anında çık (seansı kilitleme)."""
    # HG-6 (Plan A-3): backend'in ESP'ye komutladığı NİYET tek boğaz noktasında kaydedilir.
    # ASİMETRİK (review F4): STOP burada HEMEN (başarısız STOP'ta bile niyet False olmalı ki
    # ESP görününce reconcile denesin); START ise yalnız publish DOĞRULANINCA (aşağıda) —
    # başarısız start niyeti True bıraksaydı NVS-resume hayaleti reconcile'dan süresiz muaf
    # kalırdı. Tüm çağıranlar (manuel, AI, seans, E-stop, reset) buradan geçer.
    _kaydet_esp_komut_niyeti(topic, payload, basarili=False)
    try:
        import socket as _socket

        try:
            _probe = _socket.create_connection(("127.0.0.1", 1883), timeout=0.3)
            _probe.close()
        except OSError:
            return False  # broker erişilemez → hızlı başarısız
        import paho.mqtt.client as _mqtt

        # Cagri basina BENZERSIZ kimlik — acil-durdurma ESP bobinlerine paralel yayin yapar;
        # sabit kimlikte broker es-zamanli baglantilardan yalniz birini tutar (bkz. _mqtt_client_id).
        # ⚠️ CALLBACK API SÜRÜMÜ AÇIKÇA VERİLİR (2026-08-15). paho 2.x, sürüm verilmeyen her
        # istemci için "Callback API version 1 is deprecated" uyarısı basıyordu ve bu tek satır
        # test çıktısında ~156 uyarı üretiyordu. Gürültü zararsız değildir: bugün tam bu yüzden
        # sklearn'ün "geçersiz sonuç üretebilir" uyarısı 171 satırlık tekrarın içinde
        # kayboluyordu. Bu istemcinin HİÇ geri çağrısı yok (yalnız connect/publish) → V2'ye
        # geçmek davranışı değiştirmez.
        c = _mqtt.Client(_mqtt.CallbackAPIVersion.VERSION2, client_id=_mqtt_client_id("pub"), clean_session=True)
        _u, _pw = _mqtt_credentials()
        if _u:
            c.username_pw_set(_u, _pw)  # broker auth açıksa (allow_anonymous false) kimlik gönder
        c.connect("127.0.0.1", 1883, 5)
        info = c.publish(topic, _json.dumps(payload), qos=1)
        # wait_for_publish: qos=1 mesajı disconnect'ten ÖNCE broker'a teslim edilsin (audit #4).
        # Eskiden publish hemen disconnect ediliyordu → ağ döngüsü çalışmadan mesaj ara sıra
        # gönderilmeden düşebiliyordu (bobin komutu kaybı).
        c.loop_start()
        try:
            # ⚠️ DENETİM 2026-08-09 (ENGEL) — SONUÇ ARTIK GERÇEKTEN OKUNUYOR.
            # Eski hâli `wait_for_publish(timeout=2.0)` çağırıp SONUCU YOK SAYARAK koşulsuz True
            # dönüyordu. Broker TCP'yi kabul edip QoS-1 PUBACK'i hiç göndermezse (broker asılı,
            # disk dolu, yetki reddi) zaman aşımı dolar ve mesaj TESLİM EDİLMEMİŞTİR — ama
            # `_estop_one` bunu "success" sayar, `_esp_ok` True olur, arayüz "bobinler durdu" der.
            # Yani acil durdurmanın ESP ayağı sessizce başarısız olurken operatöre BAŞARILI görünür.
            # `wait_for_publish` zaman aşımında (paho ≥2.0) WouldBlockError atar → yakala.
            try:
                info.wait_for_publish(timeout=2.0)
            except (ValueError, RuntimeError, OSError):
                pass  # aşağıdaki is_published() kesin cevabı verir
            except Exception:
                pass
            yayinlandi = bool(info.is_published())
        finally:
            c.loop_stop()
        c.disconnect()
        if not yayinlandi:
            logging.getLogger(__name__).error(
                "MQTT yayin DOGRULANAMADI (PUBACK yok) — konu=%s. Bobin komutu TESLIM EDILMEMIS olabilir.", topic
            )
        else:
            # F4: START niyeti yalnız DOĞRULANMIŞ publish'te kaydedilir (yukarıdaki asimetri notu).
            _kaydet_esp_komut_niyeti(topic, payload, basarili=True)
        return yayinlandi
    except Exception:
        return False


# ── ESP KOMUT ONAYI (ACK ROUND-TRIP) — donanım-uyum denetimi HG-4 (2026-08-19) ────────────────
# SORUN: ESP bobinleri (6-8) her komuta `pemf/coil/{id}/ack` konusuna {command_id, success}
# yayınlar (firmware sendCommandAck), ama backend bu konuyu HİÇ dinlemiyordu. `_mqtt_publish`
# yalnız broker QoS-1 PUBACK'ini okur → "broker mesajı kabul etti" demek, "ESP mesajı ALDI"
# demek DEĞİL. WiFi'siz bir ESP'ye E-stop yayınlanınca broker PUBACK döner, çağıran "success"
# sayar, operatöre "durduruldu" gösterir — ama ESP mesajı hiç almaz (STOP retain=False). Bobin
# fiziksel enerjili kalırken UI "durdu" der.
#
# ÇÖZÜM: kalıcı dinleyici client `.../ack`e abone olur; komut ONAYINI command_id ile eşler.
# ⚠️ E-stop'u BLOKLAMAZ: publish hemen gider (hız kritik), onay ARKA PLANDA izlenir; gelmezse
# operatöre AÇIK uyarı gider. Onay yokluğu artık SESSİZ değil.
_pending_acks: dict = {}
_pending_acks_lock = threading.Lock()

# DENETIM 2. TUR [3.2] (2026-08-20): command_id YALNIZ ms çözünürlüklüydü — aynı bobine aynı
# milisaniyede iki E-stop tetiği (manuel buton + ESP alarmı; alarm dalında debounce yok) AYNI
# id'yi üretiyordu. _register_ack üzerine yazar + _wait_ack pop'lar → ikinci bekçi ack GELMİŞKEN
# timeout görüp acil-durdurma anında SAHTE "ONAYI GELMEDİ" kırmızı alarmı basıyordu (ölçüldü,
# iki advers interleaving). Süreç-ömürlü sıra numarası aynı ms'de bile benzersizlik verir.
# (itertools.count C-uygulamalıdır; next() GIL altında atomiktir — ayrıca kilit gerekmez.)
# ⚠️ id UZUNLUĞU (17. parti düzeltmesi — adversaryal inceleme): S3 firmware ≥36 karakterlik
# command_id'yi KIRPMAZ, TÜMDEN REDDEDER (esps3 NetworkManager.cpp: strlen<36 değilse id boş
# bırakılır → HİÇ ACK GİTMEZ). Yani id biçimi büyürse arıza modu "kırpılmış eşleşme" değil
# "onay hiç gelmez" olur. Biçim `estop_{coil}_{13 haneli ms}_{sıra}` ~25 karakterdir ve testle kilitlidir.
import itertools as _itertools

_estop_sira = _itertools.count(1)


def _register_ack(command_id: str) -> None:
    """Publish'ten ÖNCE çağrılır (ack yarışı kaybolmasın): command_id için bekleme kaydı aç."""
    with _pending_acks_lock:
        _pending_acks[command_id] = {"success": None, "event": threading.Event()}


def _resolve_ack(command_id: str, success: bool) -> None:
    """ESP ack'i gelince: kayıtlıysa sonucu yaz + bekleyeni uyandır. Bilinmeyen id → no-op
    (retained/bayat ack veya STM seri yolu; zararsız)."""
    with _pending_acks_lock:
        entry = _pending_acks.get(command_id)
    if entry is not None:
        entry["success"] = bool(success)
        entry["event"].set()


def _wait_ack(command_id: str, timeout: float):
    """True=ESP onayladı, False=ESP başarısız bildirdi, None=onay GELMEDİ (timeout)."""
    with _pending_acks_lock:
        entry = _pending_acks.get(command_id)
    if entry is None:
        return None
    got = entry["event"].wait(timeout)
    with _pending_acks_lock:
        _pending_acks.pop(command_id, None)
    return entry["success"] if got else None


# ── [4.5] NACK yarisi (2026-08-22): manuel ESP start'i da ack-mimarisine baglanir ────────────
# "Dogrulanmis publish" yalniz BROKER kabuludur; ESP komutu ayrica REDDEDEBILIR (rate-limit /
# validation / unknown → sendCommandAck(id, false)). Eskiden bu NACK yalniz E-stop bekcisinde
# okunuyordu → manuel start reddedilse bile tedavi gecmisindeki kosu kaydi "kostu" olarak acik
# kaliyordu (hayalet kayit). Bekci E-stop deseninin aynisi: publish BLOKLANMAZ, onay arka planda.
#
# ⚠️ ASIMETRI KASITLI:
#   · NACK (success=false) → kosu kaydi KAPANIR (bobin hic baslamadi — kesin bilgi) + error.
#   · TIMEOUT (onay yok)   → kayit KALIR + yalniz uyari. Ack QoS-0'dir ve kaybolabilir;
#     onaysizlikta kaydi kapatmak, GERCEKTEN calisan bobinin dozunu kayittan silmek olurdu
#     (yanlis yonde hata). Fiziksel-calismiyor-olabilir uyarisi [1.1]'in isidir.
# ⚠️ Bu is GUVENLIK LIMITI isi DEGILDIR: backend'e freq/duty clamp'i EKLENMEZ (sahip karari,
# pemf-production-readiness). Kilit: tests/test_nack_gorunurlugu.py
_START_ACK_TIMEOUT = 2.0  # sn — E-stop bekcisiyle ayni sozlesme (testle kilitli)


def _start_ack_watch(coil_id: int, command_id: str, run_id=None) -> None:
    """Manuel ESP start onayini ARKA PLANDA izle (bkz. ustteki blok yorumu).

    ⚠️ run_id (denetim 2026-08-24, D2): bekci baslatildigi andaki kosu kaydinin id'si. NACK'te
    kosu YALNIZ hala BU run ise kapatilir — ayni bobine hizli ikinci bir start (KABUL edilmis) run'i
    devraldiysa, bu (bayat) NACK araya giren CALISAN kosuyu DUSURMEMELI."""
    confirmed = _wait_ack(command_id, timeout=_START_ACK_TIMEOUT)
    if confirmed is True:
        logging.getLogger(__name__).debug("start bobin %s: ESP onayladi (ack)", coil_id)
        return
    if confirmed is False:
        # Kesin red: kosu kaydi hayalet — kapat. Sebep metni command_error eventiyle ayrica gelir.
        logging.getLogger(__name__).error(
            "start bobin %s: ESP komutu REDDETTI (NACK) — kosu kaydi kapatiliyor (hic kosmamis bobin)",
            coil_id,
        )
        try:
            # D2: yalniz BU start'in run'ini kapat (araya giren yeni start run'i devraldiysa dokunma).
            _finish_coil_run(coil_id, only_run_id=run_id)
        except Exception:
            logging.getLogger(__name__).debug("NACK sonrasi run kapatma hatasi", exc_info=True)
        try:
            _push_notification(
                f"⚠️ Bobin {coil_id}: start komutu cihaz tarafından REDDEDİLDİ — bobin ÇALIŞMIYOR; "
                "koşu kaydı düzeltildi",
                "error",
            )
        except Exception:
            pass
        return
    logging.getLogger(__name__).warning(
        "start bobin %s: ESP onayi %.1f sn'de GELMEDI — bobin komutu almamis olabilir (kayit korunuyor)",
        coil_id,
        _START_ACK_TIMEOUT,
    )
    try:
        _push_notification(
            f"⚠️ Bobin {coil_id}: start onayı gelmedi — bobinin gerçekten çalıştığını panelden kontrol edin",
            "warning",
        )
    except Exception:
        pass


def _start_ack_izle_arka_planda(coil_id: int, command_id: str, publish_ok: bool, run_id=None) -> None:
    """Publish sonucu belliyken bekciyi baglar. Kayit publish'ten ONCE acilmis olmali (hizli ESP
    ack yarisi kaybolmasin — HG-4 deseni); publish dusmusse bekleyecek sey yok → kaydi temizle.

    run_id (D2): bekciye bu start'in kosu kaydi id'sini gecir → NACK yalniz KENDI run'ini kapatir."""
    if not publish_ok:
        with _pending_acks_lock:
            _pending_acks.pop(command_id, None)
        return
    try:
        threading.Thread(
            target=_start_ack_watch, args=(coil_id, command_id, run_id), daemon=True, name=f"start-ack-{coil_id}"
        ).start()
    except Exception:
        # Thread acilamazsa (kaynak tukenmesi) start akisi BOZULMAZ — yalniz izleme kaybolur.
        logging.getLogger(__name__).warning("start-ack bekcisi baslatilamadi (bobin %s)", coil_id, exc_info=True)
        with _pending_acks_lock:
            _pending_acks.pop(command_id, None)


def _esp_control_broadcast(command: str, id_prefix: str, extra: dict | None = None) -> None:
    """ESP bobinlerine (6-8) `pemf/coil/{id}/control`'e komut yayınlar.

    ⚠️ D-1 (donanım-uyum denetimi, 2026-08-19): selftest + reset_pwm eskiden ÖLÜ bir topiğe
    (`pemf/esp32_{id}/command`) yayınlıyordu — S3/8266 firmware'i `pemf/coil/{id}/control`'e abone,
    o topiğe DEĞİL. Sonuç: selftest ESP 6-8'de HİÇ çalışmıyor (arızalı ESP sessizce geçer = yanlış
    tanısal güvence); reset sonrası seans-dışı ESP bobini enerjili kalıyordu. STM (1-5) MQTT
    dinlemez (seri protokol) → kapsam yalnız ESP_COIL_IDS. E-stop yolu ayrıdır (kendi çift-yayını)."""
    for i in sorted(ESP_COIL_IDS):
        payload = {"command": command, "command_id": f"{id_prefix}_{i}_{int(time.time() * 1000)}"}
        if extra:
            payload.update(extra)
        try:
            _mqtt_publish(f"pemf/coil/{i}/control", payload)
        except Exception:
            logging.getLogger(__name__).debug("%s publish %d hatasi", id_prefix, i, exc_info=True)


def _estop_ack_watch(coil_id: int, command_id: str) -> None:
    """E-stop onayını ARKA PLANDA izle (publish'i bloklamadan). Onay 2 sn'de gelmezse operatörü
    AÇIKÇA uyar — bobin fiziksel durmamış olabilir (WiFi partition / cloud-failover senaryosu)."""
    confirmed = _wait_ack(command_id, timeout=2.0)
    if confirmed is True:
        logging.getLogger(__name__).info("E-stop bobin %s: ESP ONAYLADI (ack)", coil_id)
        return
    if confirmed is False:
        # [3.2]: ESP komutu AÇIKÇA REDDETTİ (success=false NACK) — eskiden bu dal da "(2s) ONAYI
        # GELMEDİ" diyordu: hem teşhis hem süre ibaresi yanlıştı (NACK anında döner). Operatör
        # doğru şeye bakmalı: sorun ağ/teslim değil, cihazın reddi.
        logging.getLogger(__name__).error(
            "E-stop bobin %s: ESP komutu REDDETTİ (NACK) — bobin fiziksel DURMAMIS olabilir, MANUEL KONTROL et.",
            coil_id,
        )
        try:
            _push_notification(
                f"⚠️ Bobin {coil_id}: acil durdurma komutu ESP tarafından REDDEDİLDİ — bobini elle kontrol edin",
                "error",
            )
        except Exception:
            pass
        return
    logging.getLogger(__name__).error(
        "E-stop bobin %s: ESP ONAYI GELMEDI (2s) — bobin fiziksel DURMAMIS olabilir, MANUEL KONTROL et.",
        coil_id,
    )
    try:
        _push_notification(
            f"⚠️ Bobin {coil_id}: acil durdurma ESP onayı GELMEDİ — bobini elle kontrol edin",
            "error",
        )
    except Exception:
        pass


# ── ESP KOMUT NİYETİ + HEDEFLİ RECONCILE (HG-6, Plan A-3, 2026-08-19) ─────────────────────────
# SORUN: ESP reboot'ta NVS/EEPROM'dan OTONOM devam eder; backend'in offline pencerede yayınladığı
# STOP retained olmadığından KAYBOLUR ve backend yalnız "bağlandı" der → bobin, backend'in haberi
# olmadan enerjili. ÇÖZÜM: backend'in her ESP'ye KOMUTLADIĞI son durum tek boğaz noktasında
# (_mqtt_publish) kaydedilir; ESP status'unda "çalışıyor" görülüp backend niyeti "çalışmıyor" ise
# (ve aktif seans o bobini kapsamıyorsa) HEDEFLİ STOP gönderilir. Retained-STOP YERİNE bu tercih
# edildi: retained STOP, yeniden bağlanan ESP'nin MEŞRU seansını da öldürürdü.
# Backend restart'ında kayıt boş (=hiçbirine start komutlanmadı) → NVS'den devam eden bobin
# yakalanır; backend_service açılış-reconcile'ı ile çift katman.
_esp_commanded_running: dict = {}
_esp_intent_lock = threading.Lock()
_reconcile_last_stop: dict = {}
_reconcile_last_notify: dict = {}  # coil_id -> monotonic (bildirim katlama: 5 dk'da bir)
_esp_stop_zamani: dict = {}  # coil_id -> monotonic (son STOP niyeti anı; F5 grace penceresi)
_RECONCILE_MIN_ARALIK_SN = 30.0
_RECONCILE_STOP_GRACE_SN = 10.0  # STOP sonrası uçuştaki 'running' status'ları sahte tetik sayma


def _kaydet_esp_komut_niyeti(topic: str, payload: dict, basarili: bool = False) -> None:
    """`pemf/coil/{id}/control`e giden start/stop = backend NİYETİ. ASİMETRİK kayıt (review F4):
    · STOP: publish SONUCUNDAN BAĞIMSIZ, HEMEN kaydedilir (basarili=False çağrısında) — başarısız
      STOP'ta niyet False kalmalı ki ESP yeniden görününce reconcile DENESİN. Anı damgalanır
      (F5 grace penceresi: stop'tan hemen sonra gelen uçuştaki 'running' status sahte tetiklemesin).
    · START: yalnız publish DOĞRULANINCA (basarili=True çağrısında) kaydedilir — başarısız start
      niyeti True bırakırsa, o bobinin NVS-resume hayaleti reconcile'dan süresiz muaf kalırdı
      (güvenlik ağının kendisini delen delik)."""
    try:
        parts = topic.split("/")
        if len(parts) != 4 or parts[0] != "pemf" or parts[1] != "coil" or parts[3] != "control":
            return
        cmd = str(payload.get("command", "")).lower()
        cid = int(parts[2])
        if cmd == "stop" and not basarili:
            with _esp_intent_lock:
                _esp_commanded_running[cid] = False
                _esp_stop_zamani[cid] = time.monotonic()
        elif cmd == "start" and basarili:
            with _esp_intent_lock:
                _esp_commanded_running[cid] = True
    except Exception:
        pass


def _reconcile_esp_calisiyor(coil_id: int, snapshot: dict) -> None:
    """ESP status'u 'çalışıyor' dedi; backend niyeti/seansı bunu KAPSAMIYORSA hedefli STOP.
    MQTT callback'inden çağrılır → publish ARKA PLANDA (callback'i ~7sn bloklamasın)."""
    if coil_id not in ESP_COIL_IDS or not snapshot.get("running"):
        return
    simdi = time.monotonic()
    with _esp_intent_lock:
        if _esp_commanded_running.get(coil_id, False):
            return  # backend zaten start komutladı — meşru çalışma
        # F5 (review): normal STOP'tan hemen sonra broker sırasında bekleyen 'running' status'lar
        # işlenir — bunlar hayalet değil, uçuştaki bayat rapor. Grace penceresinde tetikleme
        # (sahte "güvenlik durdurması" bildirimi = tıbbi cihazda alarm yorgunluğu).
        if simdi - _esp_stop_zamani.get(coil_id, -1e9) < _RECONCILE_STOP_GRACE_SN:
            return
    with _session_lock:
        sess_aktif = bool(_active_session.get("is_active"))
        sess_coils = _active_session.get("coil_ids") or list(range(1, 9))
    if sess_aktif and coil_id in sess_coils:
        return  # aktif seans kapsıyor (niyet kaydı seans yolunda da dolar ama çifte emniyet)
    with _esp_intent_lock:
        if simdi - _reconcile_last_stop.get(coil_id, 0.0) < _RECONCILE_MIN_ARALIK_SN:
            return  # hız sınırı: aynı bobine 30 sn'de en çok bir reconcile-STOP
        _reconcile_last_stop[coil_id] = simdi

    def _stop_gonder():
        # F3 (review): karar ile publish arası pencerede meşru bir start gelmiş olabilir —
        # publish'ten HEMEN önce niyeti ve seans kapsamını YENİDEN doğrula; yoksa reconcile-STOP
        # yeni başlamış meşru tedaviyi sessizce durdururdu (üstelik stop niyeti start'ı ezerdi).
        with _esp_intent_lock:
            if _esp_commanded_running.get(coil_id, False):
                return
        with _session_lock:
            s_aktif = bool(_active_session.get("is_active"))
            s_coils = _active_session.get("coil_ids") or list(range(1, 9))
        if s_aktif and coil_id in s_coils:
            return
        cid = f"reconcile_{coil_id}_{int(time.time() * 1000)}"
        ok = _mqtt_publish(
            f"pemf/coil/{coil_id}/control",
            {"command": "stop", "command_id": cid, "timestamp": time.time()},
        )
        logging.getLogger(__name__).warning(
            "RECONCILE: bobin %s beklenmedik 'calisiyor' raporladi (backend niyeti: durmus) -> hedefli STOP %s.",
            coil_id,
            "gonderildi" if ok else "GONDERILEMEDI (broker?)",
        )
        # Bildirim katlama (review 'sonraya' maddesi — alarm yorgunluğu): STOP'a rağmen ısrarla
        # "çalışıyor" diyen kalıcı hayalet 30 sn'de bir DEĞİL, 5 dk'da bir bildirilir (log hep yazar).
        simdi_n = time.monotonic()
        with _esp_intent_lock:
            bildir = simdi_n - _reconcile_last_notify.get(coil_id, -1e9) >= 300.0
            if bildir:
                _reconcile_last_notify[coil_id] = simdi_n
        if bildir:
            try:
                _push_notification(
                    f"⚠️ Bobin {coil_id} beklenmedik şekilde çalışıyordu — güvenlik durdurması gönderildi",
                    "warning",
                )
            except Exception:
                pass

    threading.Thread(target=_stop_gonder, name=f"reconcile-stop-{coil_id}", daemon=True).start()


def _estop_cloud_mirror(coil_ids, reason: str) -> None:
    """HG-5 (Plan A-2, 2026-08-19): E-stop'u BULUT broker'ına AYNALA — best-effort, arka plan.

    ESP'ler yerel broker 3 kez başarısız olunca HiveMQ cloud'a failover eder; backend ise yalnız
    127.0.0.1'e yayınlıyordu → buluta göçmüş ESP'ye E-stop HİÇ ulaşmıyordu. Bu ayna, aynı STOP'u
    buluta da yayınlar. Kimlik bilgileri SecretsManager'dan (mqtt_cloud_host/port/user/pass;
    generate=False — yoksa dosyaya rastgele değer YAZILMAZ, ayna sessizce devre dışı kalır ve
    bir kez loglanır). ESP davranışına dokunmaz; yerel E-stop yolunu BLOKLAMAZ (ayrı thread)."""
    try:
        from utils.secrets_manager import get_secret

        host = (get_secret("mqtt_cloud_host", default="", generate=False) or "").strip()
        user = (get_secret("mqtt_cloud_user", default="", generate=False) or "").strip()
        parola = get_secret("mqtt_cloud_pass", default="", generate=False)
        port_s = (get_secret("mqtt_cloud_port", default="8883", generate=False) or "8883").strip()
        if not host or not user or not parola:
            logging.getLogger(__name__).info(
                "E-stop bulut aynasi ATLANDI: mqtt_cloud_* sirlari tanimli degil (yalniz yerel yol)."
            )
            return
        import paho.mqtt.client as _pm

        c = _pm.Client(
            _pm.CallbackAPIVersion.VERSION2,
            client_id=_mqtt_client_id("estop-cloud"),
            clean_session=True,
        )
        c.username_pw_set(user, parola)
        c.tls_set()  # sistem CA deposu (HiveMQ cloud sertifikası genel CA'lıdır)
        c.connect(host, int(port_s), keepalive=10)
        c.loop_start()
        try:
            infolar = []
            for cid in coil_ids:
                komut_id = f"estopcloud_{cid}_{int(time.time() * 1000)}"
                for topic in (f"pemf/coil/{cid}/control", f"pemf/esp32_{cid}/command"):
                    infolar.append(
                        c.publish(
                            topic,
                            _json.dumps(
                                {"command": "stop", "command_id": komut_id, "emergency": True, "timestamp": time.time()}
                            ),
                            qos=1,
                        )
                    )
            # Toplam süre bütçesi (review 'sonraya' maddesi): 6 yayın × 3sn ayrı ayrı beklemek
            # ~20sn'e uzayabilirdi. Tek 8sn'lik bütçe — dolunca kalanlar beklenmeden sayılır.
            teslim = 0
            son_tarih = time.monotonic() + 8.0
            for info in infolar:
                kalan = son_tarih - time.monotonic()
                if kalan > 0:
                    try:
                        info.wait_for_publish(timeout=min(3.0, kalan))
                    except Exception:
                        pass
                if info.is_published():
                    teslim += 1
            logging.getLogger(__name__).warning(
                "E-stop BULUT aynasi (%s): %d/%d yayin teslim edildi (butce 8sn).", reason, teslim, len(infolar)
            )
        finally:
            c.loop_stop()
            c.disconnect()
    except Exception as e:
        logging.getLogger(__name__).warning("E-stop bulut aynasi basarisiz (yerel yol etkilenmez): %s", e)


def _broker_reachable(timeout: float = 0.3) -> bool:
    """MQTT broker (127.0.0.1:1883) hızlı erişilebilirlik sağlaması — ESP bobin yolunun
    broker kapalıyken sessizce 'success' dönmesini önlemek için (audit #4)."""
    import socket as _socket

    try:
        _c = _socket.create_connection(("127.0.0.1", 1883), timeout=timeout)
        _c.close()
        return True
    except Exception:
        return False


# ── Active session state (in-memory, shared) ─────────────────────────────────
import threading as _threading

# B-2.2 (son kademe): session state → servers/session_state.py. Alias'lar AYNI nesnelere işaret eder
# (dict/lock in-place; rebind normalize edildiğinden endpoint/watchdog/emergency gövdesi değişmedi).
_session_lock = session_state._session_lock
_active_session = session_state._active_session
# Sensör örnekleri aktif seans boyunca burada toplanır; /api/session/notes ve /api/session/stop ile
# gerçek session_id'ye (db_session_id) flush edilir.
_sensor_sample_buffer: list = []
_sensor_sample_buffer_lock = _threading.Lock()

# ── Asama-2: per-bobin run logging + dakika-ortalama aggregator state ──────────
# B-2.2: coil-run state + _begin/_finish_coil_run → servers/coil_run_tracker.py. Alias'lar AYNI
# nesnelere işaret eder (yalnız in-place mutasyon: start_session `.clear()` + sensör-loop akümülasyon).
_active_coil_runs = coil_run_tracker._active_coil_runs
_active_coil_runs_lock = coil_run_tracker._active_coil_runs_lock
_coil_run_stats = coil_run_tracker._coil_run_stats
_coil_run_stats_lock = coil_run_tracker._coil_run_stats_lock
# Per-coil dakika-akumulatoru (dakika-ortalama aggregator). Modul-duzeyi → /api/session/stop
# bekleyen kismi dakikayi flush'tan ONCE emit edebilsin. {coil_id: {t_sum,t_min,t_max,i_sum,b_sum,amb_sum,n,freq,duty,phase}}
_minute_acc: dict = {}
_minute_acc_lock = _threading.Lock()


def _get_treatment_db():
    """Asama-2 yardimci: kanonik app_data ile TreatmentHistoryDB singleton'ini getir.
    Hata halinde None (cagiranlar try/except ile sarmali; DB hatasi seansi/donanimi DURDURMAZ)."""
    try:
        from database.treatment_history_db import get_treatment_db

        return get_treatment_db(_app_data_dir())
    except Exception:
        logging.getLogger(__name__).debug("Treatment DB erisilemedi", exc_info=True)
        return None


def _kayit_db_hazir():
    """Tıbbi kayıt DB'si yazmaya hazır mı → (hazir: bool, sebep: str). ASLA istisna atmaz.

    ⚠️ DENETİM 2026-08-09 (ENGEL) — bu, `/api/health`'in `dbReady` alanının ve seans-başlatma
    kapısının TEK KAYNAĞIDIR. İkisinin ayrı hesaplaması, "sağlık yeşil ama seans reddediliyor"
    (ya da tersi) gibi teşhis edilemez bir tutarsızlık üretirdi.
    """
    try:
        db = _get_treatment_db()
        if db is None:
            return False, "veritabani acilamadi"
        return db.is_ready()
    except Exception as e:
        logging.getLogger(__name__).error("DB hazirlik kontrolu basarisiz: %s", e, exc_info=True)
        return False, str(e)[:200]


def _lookup_owner_email(patient_uuid: str) -> str:
    """Hasta sahibinin e-postasini PatientDatabase'ten (UUID ile) getir. Bulunamazsa ''.
    Best-effort: hata seansi DURDURMAZ. ('raporu sahibe e-posta gonder' icin owner_email zinciri.)"""
    if not patient_uuid:
        return ""
    try:
        pdb = get_patient_database()
        if not pdb:
            return ""
        p = pdb.get_patient(patient_uuid)
        if not p:
            return ""
        return (p.get("owner_email") or "").strip()
    except Exception:
        logging.getLogger(__name__).debug("_lookup_owner_email hatasi", exc_info=True)
        return ""


# ── B-2.2: coil-run tracker (servers/coil_run_tracker.py) — bağımlılık injection + fonksiyon alias ──
# coil_run_tracker'a aktif-seans DB-id getter'ını enjekte et (session_state sahibi; kilitli okuma).
coil_run_tracker.set_db_session_id_getter(session_state.current_db_session_id)
# lambda (fonksiyon-referansı DEĞİL) → _get_treatment_db monkeypatch'i/yeniden-bağlaması çağrı-anında görülür.
coil_run_tracker.set_treatment_db_getter(lambda: _get_treatment_db())
_begin_coil_run = coil_run_tracker._begin_coil_run
_finish_coil_run = coil_run_tracker._finish_coil_run


@app.post("/api/hardware/auto_preset")
async def auto_preset(payload: AutoPresetPayload):
    """
    Yapay Zeka skoruna göre (veya literatür hedefine göre)
    donanım parametrelerini otomatik ayarlar.
    """
    if not state.core:
        raise HTTPException(status_code=503, detail="Çekirdek hazır değil.")

    try:
        from pathlib import Path

        from ai.hybrid_recommender import get_literature_recommendation

        app_data = Path.home() / ".pemf_gui"
        rec = get_literature_recommendation(payload.target_condition, app_data_dir=app_data)

        freq = float(rec.get("freq", 10.0))
        duty = float(rec.get("duty", 25.0))
        duration = float(rec.get("duration", 20.0))

        # GÜVENLİK: auto_preset SADECE parametre ÖNERİSİ döndürür — donanımı BAŞLATMAZ.
        # Fiziksel başlatma yalnız /api/session/start üzerinden (clamp + seans + interlock).
        # (Eskiden burada start_all_coils yan-etkisi vardı → chip'e dokununca bobinler ateşleniyordu.)
        return {
            "status": "success",
            "parameters": {"freq": freq, "duty": duty, "duration": duration, "source": rec.get("source", "unknown")},
        }
    except ImportError:
        raise HTTPException(status_code=501, detail="AI recommender bulunamadı.")
    except Exception:
        # B3 güvenlik-fix: ham str(e) istemciye SIZMAZ (bilgi ifşası) — sunucuda logla, generic dön.
        logging.getLogger(__name__).exception("AI öneri hesaplanamadı")
        raise HTTPException(status_code=500, detail="AI öneri hatası")


@app.post("/api/hardware/command")
async def hardware_command(payload: CommandPayload):
    """
    Eskiden bir PyQt6 butonuna tıklandığında yapılan işlemi buraya aktarır.
    Örn: MainWindow.start_treatment() -> /api/hardware/command {command: 'start_treatment'}
    """
    if not state.core or not state.hardware:
        raise HTTPException(status_code=503, detail="Headless Core veya HardwareController hazır değil.")

    try:
        cmd = payload.command.lower()
        p = payload.params

        if cmd == "start_coil":
            coil_id = p.get("coil_id", 1)
            freq = p.get("freq", 100.0)
            duty = p.get("duty", 25.0)
            phase = p.get("phase", 0.0)
            duration = p.get("duration", 0)
            success = state.hardware.update_coil(coil_id, freq, duty, phase, duration, start=True)
            return {"status": "success" if success else "error", "command": cmd, "coil_id": coil_id}

        elif cmd == "stop_coil":
            coil_id = p.get("coil_id", 1)
            success = state.hardware.update_coil(coil_id, 0, 0, 0, 0, start=False)
            return {"status": "success" if success else "error", "command": cmd, "coil_id": coil_id}

        elif cmd == "stop_all_coils":
            success = state.hardware.stop_all_coils()
            return {"status": "success" if success else "error", "command": cmd}

        elif cmd == "start_all_coils":
            freq = p.get("freq", 100.0)
            duty = p.get("duty", 25.0)
            phase = p.get("phase", 0.0)
            duration = p.get("duration", 30)
            success = state.hardware.start_all_coils(freq, duty, phase, duration)
            return {"status": "success" if success else "error", "command": cmd}

        else:
            return {"status": "error", "message": f"Bilinmeyen komut: {cmd}"}

    except Exception:
        # B3 güvenlik-fix: ham str(e) SIZMAZ — sunucuda logla, generic dön.
        logging.getLogger(__name__).exception("Donanım komutu başarısız")
        raise HTTPException(status_code=500, detail="Donanım komutu başarısız")


@app.post("/api/hardware/selftest")
async def trigger_hardware_selftest():
    """Tüm bobinlere SELFTEST komutu gönderir (fire-and-forget)."""
    import threading

    if not state.hardware:
        raise HTTPException(status_code=503, detail="Donanım hazır değil.")

    # 8× _mqtt_publish (her biri connect-publish-disconnect) SANİYELER sürebilir → HTTP yanıtını
    # BEKLETME (eskiden await → istemci timeout'u "gönderilemedi" gösteriyordu, HTTP 000). Arka-plan
    # daemon thread'de best-effort gönder, yanıtı hemen dön ("komut gönderildi" semantiği).
    # D-1 (2026-08-19): ESP'nin GERÇEKTEN dinlediği topiğe (`pemf/coil/{id}/control`) yayınla.
    # STM (1-5) MQTT selftest'i dinlemez → kapsam ESP_COIL_IDS. (8266'da SELFTEST handler'ı ayrı
    # bir eksik — tezgah maddesi; backend artık en azından doğru kapıya çalıyor.)
    threading.Thread(
        target=lambda: _esp_control_broadcast("SELFTEST", "selftest"),
        name="hw-selftest",
        daemon=True,
    ).start()
    return {"status": "success", "message": "Self-test commands sent."}


@app.post("/api/hardware/reset_pwm")
async def reset_all_pwms():
    """Tüm bobinleri durdurur ve duty 0 olarak reset atar (fire-and-forget)."""
    if not state.hardware:
        raise HTTPException(status_code=503, detail="Donanım hazır değil.")
    import threading

    # stop_all_coils (STM seri I/O; STM yoksa retry→saniyeler) + 8× _mqtt_publish (connect-publish) →
    # HTTP yanıtını BEKLETME (eskiden await → timeout / HTTP 000). Arka-plan thread'de yürüt, hemen dön.
    # Birincil güvenlik yolu /hardware/emergency_stop'tur; bu yalnız bakım-reset'idir.
    def _reset_all():
        try:
            state.hardware.stop_all_coils()  # STM 1-5 (seri)
        except Exception:
            logging.getLogger(__name__).debug("reset_pwm stop_all_coils hatasi", exc_info=True)
        # D-1 (2026-08-19): ESP 6-8'e ESP'nin dinlediği topiğe AÇIK "stop" (eskiden ölü esp32_
        # topiğine "start duty:0" gidiyordu → seans-dışı ESP bobini enerjili kalıyordu).
        _esp_control_broadcast("stop", "reset")

    threading.Thread(target=_reset_all, name="hw-reset-pwm", daemon=True).start()
    return {"status": "success", "message": "All PWM signals reset."}


@app.post("/api/hardware/cleanup_esp")
async def cleanup_stale_esp():
    """Zaman aşımına uğramış ESP cihazlarını temizler."""
    with _live_state_lock:
        for idx in range(5, 8):
            coil = _live_state["coils"][idx]
            if not coil.get("connected"):
                coil["running"] = False
    return {"status": "success", "message": "Stale ESP state cleaned."}


# ── Per-coil MQTT control (direct ESP command via MQTT) ───────────────────────
@app.post("/api/coil/{coil_id}/control")
async def control_single_coil(coil_id: int, payload: CoilControlPayload):
    """Send a start/stop command to a coil.

    Duration convention:
    - API/MQTT payload duration is seconds (ESP-compatible).
    - STM32 firmware duration is minutes, converted only for HardwareController.
    """
    import time

    if coil_id < 1 or coil_id > 8:
        raise HTTPException(status_code=400, detail="Geçersiz bobin ID (1-8)")

    command_id = f"react_{coil_id}_{int(time.time() * 1000)}"

    if coil_id in STM_COIL_IDS:
        if not state.hardware:
            raise HTTPException(status_code=503, detail="STM32 donanım kontrolcüsü hazır değil.")
        stm_duration_min = _duration_seconds_to_stm_minutes(payload.duration)
        _stm_sonuc = state.hardware.update_coil(
            coil_id,
            payload.freq,
            payload.duty,
            payload.phase,
            stm_duration_min,
            start=payload.start,
            # DENETIM P3: STM firmware suresi DAKIKA granulerliginde oldugundan saniye→dakika
            # donusumu YUKARI yuvarlanir (30 sn → 1 dk = 2x fazla tedavi). Firmware icin bu dogru
            # (yarida kesmez); ama yazilim deadline'i monotonik SANIYE tuttugundan gercek sureyi
            # tam uygulayabilir → hassas saniyeyi de gecir. Firmware 1 dk'lik yedek kapak kalir.
            duration_seconds=payload.duration,
        )
        # DENETIM 2. TUR [4.5] (2026-08-20): update_coil'in donusu ESKIDEN yok sayiliyordu —
        # parametre reddinde (state DEGISMEDI, bobin surulmedi) hem tedavi gecmisine "kostu"
        # yaziliyor hem istemciye "success" donuyordu. Kosu kaydi yalniz KABUL edilen start'ta;
        # STOP'ta finish HER halde calisir (acik kaydi kapatmak guvenli taraftir).
        _stm_kabul = bool(_stm_sonuc)
        if payload.start:
            if _stm_kabul:
                _begin_coil_run(coil_id, payload.freq, payload.duty, payload.phase, None, "stm")
        else:
            _finish_coil_run(coil_id)
        return {
            "status": "success" if _stm_kabul else "error",
            "command_id": command_id,
            "transport": "stm32",
        }

    if payload.start:
        # D-3 (2026-08-19): ESP DDS 1000 Hz üstünü süremez (firmware constrain) → önden normalize.
        # STM yolu (yukarıda) update_coil içinde normalize_frequency_hz uygular; ESP yolu HAM
        # gönderiyordu → >1000 komut ESP'de SESSİZCE kırpılıp komut≠telemetri sapması yaratıyordu.
        from utils.stm32_protocol_limits import normalize_esp_frequency_hz

        esp_freq = normalize_esp_frequency_hz(payload.freq)
        # HG-3 üçüncü katman (2026-08-19): STM referans bobini (1) çalışırken frekansı, istenen
        # ESP frekansının ≳50 katıysa PB1 senkron darbeleri ESP periyot-başı penceresine düşer →
        # DC-yapışma rejimi (S3 latch'i ~8 darbede keser ama o pencerede DC akar; firmware PB1
        # artık duty=0'da susturuldu — bu uyarı ÇALIŞAN coil1 senaryosunu kapatır). REDDETMEZ
        # (operatör bilinçli olabilir), operatörü AÇIKÇA uyarır + yanıtında taşır.
        _sync_uyari = None
        try:
            with _live_state_lock:
                _c1 = dict(_live_state["coils"][0])
            if _c1.get("running") and float(_c1.get("frequencyHz") or 0) >= 50.0 * max(esp_freq, 1.0):
                _sync_uyari = (
                    f"STM bobin-1 {_c1.get('frequencyHz')} Hz çalışırken bobin {coil_id} için "
                    f"{esp_freq} Hz istendi (≥50× ayrışma) — faz senkronu kilitlenmez, S3 DC-koruma "
                    f"latch'i devreye girebilir. Faz gerekmiyorsa sorun değil; gerekiyorsa frekansları yaklaştırın."
                )
                _push_notification(f"⚠️ {_sync_uyari}", "warning")
        except Exception:
            _sync_uyari = None
        mqtt_payload = {
            "command": "start",
            "command_id": command_id,
            "freq": esp_freq,
            "duty": payload.duty,
            "phase": payload.phase,
            # Gozetimsiz kapak (bkz. _esp_duration_seconds): `0` = "sure belirtilmedi" nobetcisi
            # SURESIZ demektir ve ESP tarafinda hicbir sunucu-yanli watchdog yok.
            "duration": _esp_duration_seconds(payload.duration),
        }
    else:
        esp_freq = payload.freq
        _sync_uyari = None
        mqtt_payload = {"command": "stop", "command_id": command_id}

    # [4.5] NACK yarisi (2026-08-22): onay kaydi publish'ten ONCE acilir (hizli ESP ack yarisi
    # kaybolmasin — HG-4 deseni). Bekci publish sonucuna gore asagida baglanir.
    if payload.start:
        _register_ack(command_id)
    # P0 audit 2026-06-28: senkron _mqtt_publish (~7sn worst-case) event-loop'u bloklamasin → to_thread.
    ok = await asyncio.to_thread(_mqtt_publish, f"pemf/coil/{coil_id}/control", mqtt_payload)
    # Asama-2: per-bobin run logging (ESP/MQTT dali). Loglanan freq = ESP'ye GİDEN (normalize) değer.
    # [4.5]: kosu kaydi yalniz DOGRULANMIS publish'te — broker oluyken komut KESIN gitmedi;
    # "kostu" yazmak hic kosmamis bobini tedavi gecmisine sokar. STOP'ta finish her halde.
    if payload.start:
        _esp_run_id = None
        if ok:
            _begin_coil_run(coil_id, esp_freq, payload.duty, payload.phase, None, "esp")
            _esp_run_id = _active_coil_runs.get(coil_id)  # D2: bekçiye BU start'ın run'ını taşı
        # NACK gelirse bekci bu kaydi kapatir; timeout'ta kayit korunur (bkz. _start_ack_watch).
        _start_ack_izle_arka_planda(coil_id, command_id, ok, _esp_run_id)
    else:
        _finish_coil_run(coil_id)
    _yanit = {"status": "success" if ok else "mqtt_unavailable", "command_id": command_id, "transport": "mqtt"}
    if _sync_uyari:
        _yanit["sync_warning"] = _sync_uyari
    return _yanit


@app.post("/api/coil/batch")
async def control_batch_coils(payload: BatchCoilPayload):
    """Send the same command to multiple coils at once.

    Duration convention:
    - API/MQTT payload duration is seconds (ESP-compatible).
    - STM32 firmware duration is minutes, converted only for HardwareController.
    """
    import time

    results = []
    # Audit P3: coil_ids'i max 8 BENZERSİZE sınırla — {coil_ids:[6]*5000} her ID için sıralı
    # to_thread(_mqtt_publish ~2sn) + DB yazımıyla broker/threadpool'u bombalayıp gerçek coil-kontrolünü
    # geciktiriyordu (uzunluk/dedup kısıtı yoktu).
    _seen = []
    for _c in payload.coil_ids:
        if _c not in _seen:
            _seen.append(_c)
    for coil_id in _seen[:8]:
        if coil_id < 1 or coil_id > 8:
            results.append({"coilId": coil_id, "status": "invalid"})
            continue
        command_id = f"react_batch_{coil_id}_{int(time.time() * 1000)}"
        if coil_id in STM_COIL_IDS:
            if not state.hardware:
                results.append({"coilId": coil_id, "status": "stm_unavailable"})
                continue
            stm_duration_min = _duration_seconds_to_stm_minutes(payload.duration)
            _b_stm_sonuc = state.hardware.update_coil(
                coil_id,
                payload.freq,
                payload.duty,
                payload.phase,
                stm_duration_min,
                start=payload.start,
                # DENETIM P3: STM firmware suresi DAKIKA granulerliginde oldugundan saniye→dakika
                # donusumu YUKARI yuvarlanir (30 sn → 1 dk = 2x fazla tedavi). Firmware icin bu dogru
                # (yarida kesmez); ama yazilim deadline'i monotonik SANIYE tuttugundan gercek sureyi
                # tam uygulayabilir → hassas saniyeyi de gecir. Firmware 1 dk'lik yedek kapak kalir.
                duration_seconds=payload.duration,
            )
            # Asama-2: per-bobin run logging.
            # [4.5]: kosu kaydi + satir durumu update_coil'in donusune bagli (tekil yolla ayni) —
            # reddedilen start batch satirinda "success" gorunmesin, gecmise "kostu" yazilmasin.
            _b_stm_kabul = bool(_b_stm_sonuc)
            if payload.start:
                if _b_stm_kabul:
                    _begin_coil_run(coil_id, payload.freq, payload.duty, payload.phase, None, "stm")
            else:
                _finish_coil_run(coil_id)
            results.append(
                {"coilId": coil_id, "status": "success" if _b_stm_kabul else "invalid", "transport": "stm32"}
            )
            continue
        if payload.start:
            # D-3 batch tamamlayıcısı (review, 2026-08-19 akşam): tek-bobin yolu normalize
            # ederken batch HAM freq gönderiyordu — "kısmi düzeltme" deseninin ta kendisi.
            # Tek-bobin yoluyla AYNI normalize + AYNI ≳50× sync uyarısı.
            from utils.stm32_protocol_limits import normalize_esp_frequency_hz as _nesp

            _b_esp_freq = _nesp(payload.freq)
            _b_uyari = None
            try:
                with _live_state_lock:
                    _bc1 = dict(_live_state["coils"][0])
                if _bc1.get("running") and float(_bc1.get("frequencyHz") or 0) >= 50.0 * max(_b_esp_freq, 1.0):
                    _b_uyari = (
                        f"STM bobin-1 {_bc1.get('frequencyHz')} Hz çalışırken bobin {coil_id} için "
                        f"{_b_esp_freq} Hz istendi (≥50× ayrışma) — faz senkronu kilitlenmez."
                    )
                    _push_notification(f"⚠️ {_b_uyari}", "warning")
            except Exception:
                _b_uyari = None
            mqtt_payload = {
                "command": "start",
                "command_id": command_id,
                "freq": _b_esp_freq,
                "duty": payload.duty,
                "phase": payload.phase,
                # Tek-bobin yoluyla AYNI kapak (bkz. _esp_duration_seconds). Batch'i atlamak, bu
                # deponun bir kez yandigi "kismi duzeltme" desenini tekrarlamak olurdu.
                "duration": _esp_duration_seconds(payload.duration),
            }
        else:
            _b_esp_freq = payload.freq
            _b_uyari = None
            mqtt_payload = {"command": "stop", "command_id": command_id}
        # [4.5] NACK yarisi: tekil yolla AYNI bekci — batch'i atlamak deponun bir kez yandigi
        # "kismi duzeltme" desenini tekrarlamak olurdu.
        if payload.start:
            _register_ack(command_id)
        # P0 audit 2026-06-28: senkron _mqtt_publish event-loop'u bloklamasin → to_thread.
        ok = await asyncio.to_thread(_mqtt_publish, f"pemf/coil/{coil_id}/control", mqtt_payload)
        # Asama-2: per-bobin run logging (ESP/MQTT dali) — loglanan freq = ESP'ye GIDEN (normalize).
        # [4.5]: kosu kaydi yalniz DOGRULANMIS publish'te (tekil yolla ayni gerekce).
        if payload.start:
            _b_run_id = None
            if ok:
                _begin_coil_run(coil_id, _b_esp_freq, payload.duty, payload.phase, None, "esp")
                _b_run_id = _active_coil_runs.get(coil_id)  # D2: bekçiye BU start'ın run'ını taşı
            _start_ack_izle_arka_planda(coil_id, command_id, ok, _b_run_id)
        else:
            _finish_coil_run(coil_id)
        _satir = {"coilId": coil_id, "status": "success" if ok else "mqtt_unavailable", "transport": "mqtt"}
        if _b_uyari:
            _satir["sync_warning"] = _b_uyari
        results.append(_satir)
    return {"status": "success", "results": results}


# ── Session management ────────────────────────────────────────────────────────
@app.post("/api/session/start")
async def start_session(payload: SessionStartPayload, request: Request):
    """Start a new treatment session."""
    import time

    # ⚠️ 2026-08-09 (Tier 1): kaydın SAHİBİNE sunucu karar verir (bkz. auth.cozumlenmis_operator).
    # Beyanı doğrudan yazmak, cihaza erişen herkesin başka bir hekim adına seans açmasına izin
    # veriyordu; seansın denetim izi (`session_started` olayı) de o adla imzalanıyordu.
    from servers.auth import cozumlenmis_operator

    _operator_kimligi = cozumlenmis_operator(request, payload.operator_email)
    # Derinlemesine savunma (Pydantic max_length=8 sinirda zaten reddeder): tekrarlari at ve
    # gecerli bobin araligina (1-8) filtrele → /api/coil/batch'teki `_seen[:8]` deseniyle ayni.
    _seen_coils = []
    for _c in payload.coil_ids or []:
        if 1 <= _c <= 8 and _c not in _seen_coils:
            _seen_coils.append(_c)
    coil_ids = _seen_coils or list(range(1, 9))
    stm_coils = [coil_id for coil_id in coil_ids if coil_id in STM_COIL_IDS]
    esp_coils = [coil_id for coil_id in coil_ids if coil_id in ESP_COIL_IDS]
    if stm_coils and not state.hardware:
        raise HTTPException(status_code=503, detail="STM32 donanım kontrolcüsü hazır değil.")

    # ⚠️ DENETİM 2026-08-09 (ENGEL) — KAYITSIZ TEDAVİ ARTIK BAŞLAMAZ.
    # Aşağıdaki DB yazımları bilinçli olarak "best-effort"tur (DB hatası bobinleri durdurmasın).
    # Ama BAŞLANGIÇTA bunun sonucu şuydu: DB hiç açılamıyorken bile seans başlıyor, bobinler
    # enerjileniyor, tedavi uygulanıyor ve db_session_id=None kaldığı için seans satırı,
    # coil-run'lar ve sensör telemetrisinin HİÇBİRİ yazılmıyordu — operatöre tek bir uyarı
    # bile çıkmadan. Hastanın aldığı doz geriye dönük OLARAK BİLİNEMEZ hâle geliyordu.
    # Kapı YALNIZ BAŞLATMADADIR: /session/stop, /hardware/emergency_stop ve bobin durdurma
    # yolları BU KONTROLDEN GEÇMEZ — DB çökükken tedaviyi durduramamak asıl tehlike olurdu.
    # Ayrıca seans ORTASINDA DB düşerse tedavi kesilmez (eski best-effort davranışı korunur).
    _db_ok, _db_sebep = _kayit_db_hazir()
    if not _db_ok:
        logging.getLogger(__name__).error("Seans REDDEDILDI — tibbi kayit DB'si hazir degil: %s", _db_sebep)
        raise HTTPException(
            status_code=503,
            detail=(
                "Tıbbi kayıt veritabanı açılamadı; seans başlatılamaz. Tedavi kaydı "
                "tutulamayacağı için işlem güvenli değildir. Cihazı yeniden başlatın, "
                "sorun sürerse teknik desteğe başvurun."
            ),
        )

    # Güncelleme uygulanıyorken YENİ seans başlatma: installer servisi durdurup EXE'yi
    # değiştirebilir → başlayan tedavi bobinleri kontrolcüsüz bırakabilir. (update_manager
    # TOCTOU guard'ının TERS yönü — apply, başlamış tedaviyi zaten _has_active_treatment ile
    # reddeder; bu da apply penceresinde yeni tedaviyi reddeder.)
    try:
        from servers import update_manager as _um

        if _um.is_update_in_progress():
            raise HTTPException(
                status_code=409, detail="Güncelleme uygulanıyor; işlem bitene kadar yeni seans başlatılamaz."
            )
    except HTTPException:
        raise
    except Exception:
        pass

    with _session_lock:
        if _active_session.get("is_active"):
            raise HTTPException(status_code=409, detail="Zaten aktif bir seans var.")

        # B-2.2: REBIND (`_active_session = {...}`) yerine IN-PLACE (clear+update) → dict kimliği
        # sabit kalır (session_state alias'lanabilir); davranış aynı (kilit altında atomik).
        _active_session.clear()
        _active_session.update(
            {
                "is_active": True,
                "session_id": _yeni_seans_muhru(),
                "patient_id": payload.patient_id,
                "patient_name": payload.patient_name,
                "operator_name": payload.operator_name,
                "mode": payload.mode,
                "target_condition": payload.target_condition,
                "frequency": payload.frequency,
                "duty": payload.duty,
                "intensity": payload.intensity,
                "phase": payload.phase,
                "duration_minutes": payload.duration_minutes,
                "start_time": time.time(),
                # DENETIM P2: sure-watchdog DUVAR SAATI farkiyla calisiyordu. NTP duzeltmesi/DST/
                # elle saat degisimi ILERI giderse seans ERKEN kesilir, GERI giderse planlanandan
                # UZUN surer (maruziyet artar). start_time istemciye/gosterime gittigi icin epoch
                # olarak KORUNDU; guvenlik karari icin AYRI monotonic isaret kullanilir.
                "start_mono": time.monotonic(),
                "started_epoch": time.time(),
                "coil_ids": coil_ids,
                "db_session_id": None,  # Asama-2: seans BASINDA olusan gercek int DB session_id
                "db_patient_id": None,
            }
        )

    # Denetim izi (audit P1) — seansı HEMEN kalıcılaştır: kim (operatör) + ne zaman + hangi
    # parametreler. Eskiden seans yalnız SONDA DB'ye yazılıyordu → backend seans ortasında
    # çökerse hiçbir kayıt kalmıyordu ve operatör kimliği hiç tutulmuyordu. session_events
    # append-only olduğundan bu, ana seans satırı sonradan yazılsa da bağımsız kanıt sağlar.
    try:
        # P1 audit 2026-06-28: get_treatment_db() ARGUMANSIZ cagriliyordu (imza app_data_dir
        # zorunlu) → TypeError → except yutuyordu → session_started AUDIT IZI HIC yazilmazdi.
        # _get_treatment_db() sarmalayicisi app_data_dir gecer (dosyadaki diger cagrilarla tutarli).
        _get_treatment_db().record_session_event(
            None,
            "session_started",
            payload={
                "ref": _active_session["session_id"],
                "operator_name": payload.operator_name,
                "operator_email": _operator_kimligi,
                "patient_id": payload.patient_id,
                "mode": payload.mode,
                "frequency": payload.frequency,
                "duty": payload.duty,
                "intensity": payload.intensity,
                "phase": payload.phase,
                "duration_minutes": payload.duration_minutes,
                "coil_ids": coil_ids,
            },
            severity="info",
        )
    except Exception:
        logging.getLogger(__name__).warning("Seans başlangıç audit kaydı yapılamadı.", exc_info=True)

    # Asama-2 (1a): seans BASINDA gercek DB satirini ac (coil-run + sensor ona baglanir).
    # Sahip e-postasini hasta kayittan (patient_id=UUID) cek — "raporu sahibe e-posta gonder"
    # icin history'de session.owner_email dolu gelsin. Best-effort (yoksa bos string).
    owner_email = _lookup_owner_email(payload.patient_id)
    # KVKK retention (2026-06-28): bu tedavi icin hastanin last_treatment_at'ini guncelle
    # (inaktiflik sayaci → 5 yil sonra anonimlestirme bunu baz alir).
    if payload.patient_id:
        try:
            _pdb = get_patient_database()
            if _pdb is not None:
                _pdb.touch_last_treatment(payload.patient_id)
        except Exception:
            logging.getLogger(__name__).debug("touch_last_treatment hatasi", exc_info=True)

    # Best-effort: DB hatasi seansi/donanimi DURDURMASIN → db_session_id=None kalir (eski davranis).
    # P-1 fix: senkron SQLCipher yazimlari (upsert_patient/start_session/set_meta/set_param) event-loop'u
    # BLOKLAMASIN → tumu tek to_thread'de; hizli lock-update (db_session_id) async'te sonrasinda yapilir.
    _started_epoch_snap = _active_session.get("started_epoch")

    def _persist_session_start():
        db = _get_treatment_db()
        if db is None:
            return None, None
        _pid = None
        if payload.patient_name:
            try:
                _pid = db.upsert_patient(
                    {
                        "name": payload.patient_name,
                        "patient_uuid": (payload.patient_id or None),
                        "owner_email": (owner_email or None),
                    }
                )
            except Exception:
                logging.getLogger(__name__).debug("upsert_patient hatasi", exc_info=True)
        _sid = db.start_session(
            treatment_mode=payload.mode,
            target_condition=payload.target_condition or None,
            operator_name=payload.operator_name or None,
            patient_name=payload.patient_name or None,
            # ⚠️ 2026-08-09 (Tier 1): e-posta İSTEMCİ BEYANINDAN değil, doğrulanmış operatör
            # jetonundan gelir. Beyan yalnız cihazda kayıtlı operatör YOKKEN kabul edilir.
            operator_email=_operator_kimligi or None,
        )
        # Yeni kolonlar (start_session bunlari yazmaz): gercek baslangic epoch + patient_id FK.
        try:
            db.set_session_meta(_sid, started_epoch=_started_epoch_snap, patient_id=_pid)
        except Exception:
            logging.getLogger(__name__).debug("set_session_meta(start) hatasi", exc_info=True)
        # Sahip e-postasini seans-parametresi olarak yaz (history JOIN'i bunu okur).
        if owner_email:
            try:
                db.set_session_parameter(_sid, "patient_owner_email", owner_email, "")
            except Exception:
                logging.getLogger(__name__).debug("set_session_parameter(owner_email) hatasi", exc_info=True)
        # ⚠️ DENETİM İZİNİ SEANSA BAĞLA (kampanya bulgusu S11, 2026-08-15).
        # `session_started` olaylarında `session_events.session_id` NULL'dur ve bu KASITLIDIR:
        # olay, DB seans satırı OLUŞMADAN ÖNCE yazılır (önce-iz-sonra-satır). Ama bağlantı
        # hiçbir yerde kurulmuyordu → "bu denetim kaydı hangi seansa ait?" cevapsız kalıyordu.
        #
        # ⚠️ BAĞLANTI TERS YÖNDE KURULUR: `session_events`e SONRADAN UPDATE ATILMAZ — o tablo
        # append-only'dir ve sıralama bilinçlidir. Bunun yerine mühür seans satırına yazılır.
        # Böylece yeni DB metodu, denetim tablosuna UPDATE ve `delete_session` semantiğinde
        # değişiklik GEREKMEZ. Join: session_parameters.parameter_value ==
        # json_extract(session_events.payload,'$.ref').
        #
        # ⚠️ DÜRÜST SINIR: bu, silinen bir seansın `session_events` payload'unda kalan
        # patient_id/operator_email artığını (KVKK) ÇÖZMEZ — "iz seansla birlikte silinsin mi?"
        # ayrı bir sahip kararıdır ve bu düzeltme onu cevaplamadan uygulanabilir.
        try:
            _ref = (_active_session or {}).get("session_id")
            if _ref:
                db.set_session_parameter(_sid, "audit_ref", str(_ref), "")
        except Exception:
            logging.getLogger(__name__).debug("set_session_parameter(audit_ref) hatasi", exc_info=True)
        return _sid, _pid

    try:
        sid, patient_id = await asyncio.to_thread(_persist_session_start)
        if sid is not None:
            with _session_lock:
                # Yalniz hala bu seans aktifse yaz (arada /stop gelmis olabilir).
                if _active_session.get("is_active"):
                    _active_session["db_session_id"] = sid
                    _active_session["db_patient_id"] = patient_id
    except Exception:
        logging.getLogger(__name__).warning("Seans DB satiri olusturulamadi (db_session_id=None).", exc_info=True)

    # Yeni seans → önceki (kaydedilmemiş) sensör buffer'ını temizle.
    with _sensor_sample_buffer_lock:
        _sensor_sample_buffer.clear()
    # Asama-2: onceki seanstan artmis acik coil-run / istatistik kalmasin.
    with _active_coil_runs_lock:
        _active_coil_runs.clear()
    with _coil_run_stats_lock:
        _coil_run_stats.clear()
    # DENETIM P2 (hasta-verisi karismasi): _minute_acc bu temizlikte YOKTU. Tek temizleme
    # noktasi _emit_minute_averages'ti; onu ise SADECE dakika-loop'u ve /api/session/stop
    # cagiriyor. Sure-watchdog otomatik bitisi ve acil-durdurma is_active=False yaptigindan
    # /stop "Aktif seans yok" ile erken doner → birikmis kismi dakika HIC bosaltilmaz ve
    # SONRAKI hastanin ilk dakika-ortalamasina karisirdi (tibbi kayit kirlenmesi).
    with _minute_acc_lock:
        _minute_acc.clear()

    # Audit P1 (TOCTOU): DB-persist await'i sırasında eşzamanlı /stop is_active=False yapmış olabilir.
    # Bobinleri ENERJİLEMEDEN ÖNCE yeniden doğrula — aksi halde bobinler fiziksel açılır ama
    # _active_session.is_active=False kalır → süre-watchdog ASLA durdurmaz (gözetimsiz sürüş; setin en
    # zararlısı). Henüz hiç bobin enerjilenmediği için burada iptal güvenli (yarım-açık kalmaz).
    with _session_lock:
        _still_active = bool(_active_session.get("is_active"))
    if not _still_active:
        logging.getLogger(__name__).warning(
            "Seans başlatma İPTAL: enerjilemeden önce durdurma algılandı (bobinler açılmadı)."
        )
        return {"status": "cancelled", "message": "Seans başlatma sırasında durduruldu (bobinler açılmadı)."}

    # Session API accepts minutes; ESP/MQTT duration remains seconds.
    import time as _t

    # DENETIM 2. TUR [4.4] (2026-08-20): D-3 duzeltmesi (ffd4406) uc ham yayin sitesinden yalniz
    # IKISINI (tek-bobin + batch) kapatmisti; SEANS yolu ESP'ye HAM freq gondermeye devam ediyordu
    # → >1000 Hz'lik seansta STM bobinleri istenen frekansta, ESP'ler sessizce 1000'de: karma
    # dizide tutarsiz doz ("kismi duzeltme, duzeltilmemis demektir"). Tek-bobin/batch ile AYNI
    # normalize; run-log da ESP'ye GIDEN degeri yazar (o iki yolun kuraliyla birebir).
    from utils.stm32_protocol_limits import normalize_esp_frequency_hz as _sess_nesp

    _esp_sess_freq = _sess_nesp(payload.frequency)
    mqtt_duration_seconds = payload.duration_minutes * 60
    # [E1] (denetim 2026-08-24): NACK bekcisi yalniz broker CANLIYKEN baglanir. Broker oluyken NACK
    # gelemez (publish gitmedi) ve `esp_unreachable` (asagida) zaten uyarir; bekci timeout'u cift
    # uyari uretmesin (8. parti bilincli karari: broker-olu yarisi snappy-start + esp_unreachable).
    _esp_broker_ok = bool(esp_coils) and _broker_reachable()
    for coil_id in esp_coils:
        command_id = f"sess_{coil_id}_{int(_t.time() * 1000)}"
        mqtt_payload = {
            "command": "start",
            "command_id": command_id,
            "freq": _esp_sess_freq,
            "duty": payload.duty,
            "phase": payload.phase,
            "duration": mqtt_duration_seconds,
        }
        # [E1]: 18. parti ack-mimarisi tekil+batch yollarina baglandi ama SEANS yolu DISARIDA
        # kalmisti — termal-kilitli 8266 seans-start'i NACK'lerse (command_error) hayalet kosu kaydi
        # seans boyu acik kalir, kapanista TAM SURELI muhurlenir. Onay kaydi publish'ten ONCE acilir
        # (hizli ack yarisi kaybolmasin — HG-4 deseni; bekci publish sonucundan BAGIMSIZ, NACK ESP'nin
        # command_error event'iyle gelir). Tekil/batch yoluyla ayni sozlesme.
        if _esp_broker_ok:
            _register_ack(command_id)
        # ESP publish arka planda → broker yavaş/erişilemezse seans başlatmayı bekletme (snappy start).
        _threading.Thread(
            target=_mqtt_publish, args=(f"pemf/coil/{coil_id}/control", mqtt_payload), daemon=True
        ).start()
        # Asama-2: seans-baslangic bobini icin per-bobin run kaydi. /session/start bobinleri
        # KENDI dongusuyle baslattigindan control_single/batch hook'u buraya ULASMAZ → burada ac.
        # ⚠️ KOSULSUZ (8. parti bilincli karari: fire-and-forget publish → sonuc bilinemez; broker-olu
        # seans zaten esp_unreachable tasir). [4.4]: loglanan freq = ESP'ye GIDEN (normalize) deger.
        _begin_coil_run(coil_id, _esp_sess_freq, payload.duty, payload.phase, payload.intensity, "esp")
        _sess_run_id = _active_coil_runs.get(coil_id)  # D2: bekçiye BU start'ın run'ını taşı
        # NACK gelirse bekci bu kaydi kapatir (hayalet kayit) + operatore bildirir; ack TIMEOUT'unda
        # kayit KORUNUR (ack QoS-0, kayip ack gercek kosunun dozunu silmemeli). Tekil yolla ayni.
        if _esp_broker_ok:
            _start_ack_izle_arka_planda(coil_id, command_id, True, _sess_run_id)

    # event-loop-blok fix: update_coil = STM32'ye SENKRON seri-port yazımı (bobin başına ~onlarca ms) →
    # async-uçta doğrudan çalışınca event-loop'u bloklar; STM bobin döngüsünü thread'e offload et.
    def _start_stm_coils():
        for coil_id in stm_coils:
            state.hardware.update_coil(
                coil_id, payload.frequency, payload.duty, payload.phase, payload.duration_minutes, start=True
            )
            _begin_coil_run(coil_id, payload.frequency, payload.duty, payload.phase, payload.intensity, "stm")

    if stm_coils:
        await asyncio.to_thread(_start_stm_coils)

    update_live_session_state(
        is_active=True,
        mode=payload.mode,
        freq=payload.frequency,
        intensity=payload.intensity,
        remaining_min=payload.duration_minutes,
        duration_sec=payload.duration_minutes * 60,
    )

    # Dashboard 'Hasta Özeti' kartı için aktif hastayı canlı-duruma yaz (aktif seansın GERÇEK hastası).
    # İsim in-memory payload'dan (maskesiz); tür/ırk/sahip patient_id ile hasta-DB'den (düz-metin, maskesiz)
    # zenginleştirilir. Hasta yoksa None → kart "Aktif hasta yok" gösterir. set_live_patient tam snapshot yayınlar.
    _patient_snap = None
    _pname = (payload.patient_name or "").strip()
    if _pname or payload.patient_id:
        _patient_snap = {"name": _pname or "İsimsiz", "species": "", "breed": "", "owner": ""}
        if payload.patient_id:
            try:
                _pdb = get_patient_database()
                _rec = _pdb.get_patient(payload.patient_id) if _pdb else None
                if _rec:
                    _patient_snap = {
                        "name": (_rec.get("name") or _pname or "İsimsiz"),
                        "species": _rec.get("species") or "",
                        "breed": _rec.get("breed") or "",
                        "owner": _rec.get("owner") or "",
                    }
            except Exception:
                logging.getLogger(__name__).debug("Hasta Özeti snapshot lookup hatasi", exc_info=True)
    set_live_patient(_patient_snap)

    # ESP fail-safe (audit #4): broker erişilemezse ESP bobinleri (6-8) sessizce başlamaz →
    # operatöre WARN dön. Eskiden seans her hâlükârda 'success' dönüp ESP'ler ölü kalıyordu
    # ve kimse fark etmiyordu (STM bobinleri çalışsa da ESP yolu sessizce başarısızdı).
    # DENETIM P3: canli global `_active_session` REFERANSLA donuyordu. FastAPI yaniti bu
    # fonksiyon dondukten SONRA serilestirir; arada bir arka-plan thread'i (sure-watchdog,
    # AI loop, /stop) sozlugu mutate ederse serilestirme sirasinda "dictionary changed size
    # during iteration" → 500, ya da yanit yari-eski/yari-yeni alanlar tasir. Kilit altinda
    # SNAPSHOT dondur (istemci sozlesmesi ayni; yalniz yasam suresi guvenli).
    with _session_lock:
        _sess_snapshot = dict(_active_session)
    resp = {"status": "success", "session": _sess_snapshot}
    # `_esp_broker_ok` yukarida bir kez olculdu (esp_coils VE broker canli); ayni degeri kullan.
    if esp_coils and not _esp_broker_ok:
        msg = f"Sistem bağlantısı yok — ESP bobinleri {esp_coils} aktif OLMAYABİLİR (STM bobinleri çalışıyor)."
        logging.getLogger(__name__).warning("Seans başladı ama %s", msg)
        resp["warning"] = msg
        resp["esp_unreachable"] = True
    return resp


def _stop_session_coils(coil_ids):
    """Verilen bobinlere donanım STOP gönderir (ESP→MQTT, STM→update_coil start=False).
    is_running=False yapar → HWKeepAlive tazelemeyi keser → bobinler fiziksel olarak durur.

    DENETIM 2. TUR [1.1] (2026-08-20): DOĞRULANAMAYAN bobinlerin listesini DÖNER.
    Eskiden publish/update_coil sonuçları YOK SAYILIYORDU → broker ölüyken /api/session/stop
    koşulsuz "success" dönüyor, istemcinin "Durdurma onaylanamadı — ACİL DURDUR'a basın"
    uyarısı hiç tetiklenmiyordu (STOP hiçbir bobine ulaşmamışken UI "durdu" der).
    "Teyitsiz" üç durumu kapsar: ESP publish PUBACK'siz düştü · STM update_coil False döndü ·
    STM kontrolcüsü hiç yok (STOP denen(e)medi — sessiz atlama da teyitsizliktir).
    Dönüş listesi bilgidir; durdurma denemeleri her hâlükârda yapılır (best-effort korunur)."""
    import time as _t

    teyitsiz: list = []
    for coil_id in [cid for cid in coil_ids if cid in ESP_COIL_IDS]:
        ok = _mqtt_publish(
            f"pemf/coil/{coil_id}/control",
            {
                "command": "stop",
                "command_id": f"stop_{coil_id}_{int(_t.time() * 1000)}",
            },
        )
        if not ok:
            teyitsiz.append(coil_id)
    _stm_hedef = [cid for cid in coil_ids if cid in STM_COIL_IDS]
    if state.hardware:
        for coil_id in _stm_hedef:
            try:
                ok = bool(state.hardware.update_coil(coil_id, 0.0, 0.0, 0.0, 0, start=False))
            except Exception:
                logging.getLogger(__name__).warning(
                    "_stop_session_coils: STM stop hatasi (bobin %s)", coil_id, exc_info=True
                )
                ok = False
            if not ok:
                teyitsiz.append(coil_id)
    else:
        teyitsiz.extend(_stm_hedef)
    # Asama-2: durdurulan tum bobinlerin acik run'larini kapat (acik kalmasin).
    for coil_id in coil_ids:
        try:
            _finish_coil_run(coil_id)
        except Exception:
            logging.getLogger(__name__).debug("_stop_session_coils _finish_coil_run hatasi", exc_info=True)
    if teyitsiz:
        logging.getLogger(__name__).warning(
            "_stop_session_coils: donanim STOP'u DOGRULANAMAYAN bobinler: %s (broker/STM erisilemez olabilir)",
            sorted(teyitsiz),
        )
    return sorted(teyitsiz)


def _bildir_teyitsiz_stop(teyitsiz, kaynak: str) -> None:
    """DENETIM 2. TUR [1.1] tamamlamasi (adversaryal review #2): /session/stop yaniti teyitsizligi
    tasirken sure-watchdog / AI durdurma / sahipsiz-bobin yollari onu YUTUYORDU — broker oluyken
    seans "sure doldu" ile bitince operatore hicbir uyari gitmiyordu (bobinler ESP'de kendi suresi
    bitene dek enerjili kalabilir). Bu yardimci, HTTP yaniti OLMAYAN durdurma yollarinin ortak
    uyari kanali. Bos listede SESSIZ (alarm yorgunlugu uretme); bildirim hatasi durdurmayi bozmaz."""
    if not teyitsiz:
        return
    try:
        _push_notification(
            f"⚠️ {kaynak}: bobin(ler) {sorted(teyitsiz)} için donanım STOP'u DOĞRULANAMADI — "
            "HÂLÂ ÇALIŞIYOR olabilirler. ACİL DURDUR'a basın ya da bobinleri elle kontrol edin.",
            "error",
        )
    except Exception:
        logging.getLogger(__name__).warning("teyitsiz-stop bildirimi gonderilemedi (%s)", kaynak, exc_info=True)


def start_ai_session(freq, duty, duration_minutes, coil_ids, mode="AI"):
    """AI biofeedback donanım sürerken seansı _active_session'a YAZAR → süre-watchdog onu da
    izler ve süresi dolunca DURDURUR; emergency_stop/STM-disconnect de AI'yı kapsar. Parametre
    CLAMP'i YOK (sadece seans takibi). Tekrarlı AI çağrılarında ilk start_time/session_id korunur."""
    import time as _t

    with _session_lock:
        prev = dict(_active_session)  # devralma kararı için ESKİ seansın snapshot'ı (clear'dan ÖNCE)
        cont = bool(prev.get("is_active")) and str(prev.get("mode", "")).startswith("AI")
        # B-2.2: REBIND yerine IN-PLACE (clear+update) → dict kimliği sabit; davranış aynı.
        _active_session.clear()
        _new_session_id = prev.get("session_id") if cont else f"ai_{int(_t.time())}"
        _active_session.update(
            {
                "is_active": True,
                "session_id": _new_session_id,
                "mode": mode,
                "frequency": freq,
                "duty": duty,
                "phase": 0.0,
                "duration_minutes": int(duration_minutes),
                "start_time": prev.get("start_time") if cont else _t.time(),
                "start_mono": prev.get("start_mono") if cont else _t.monotonic(),
                "coil_ids": list(coil_ids),
                # DENETIM P1: bu iki alan HIC kurulmuyordu → _flush_sensor_buffer_if_active
                # `if not _db_sid: return` ile TUM dakika-ortalamalarini atiyordu ve otonom
                # tedavinin DB'de seans satiri OLUSMUYORDU (doz/sicaklik kaydi kalici kayip).
                # cont=True (ayni AI seansinin tekrarli cagrisi, or. landmark auto_adjust her
                # istekte cagirir) → MEVCUT satiri koru, YENI satir acma.
                "db_session_id": prev.get("db_session_id") if cont else None,
                "db_patient_id": prev.get("db_patient_id") if cont else None,
                "started_epoch": prev.get("started_epoch") if cont else _t.time(),
            }
        )
        _started_epoch_ai = _active_session["started_epoch"]
        # DENETIM (2026-08-05, dogrulama turunda bulundu): yukarida `coil_ids` KOSULSUZ
        # yeniden yaziliyor (satir "coil_ids": list(coil_ids)). Yeni seans ONCEKINDEN DAR bir
        # kume sahiplenirse aradaki bobinler SESSIZCE sahipsiz kalir — donanima STOP gitmez.
        #   Somut yol: `AI (Auto)` landmark surusu bobin 1-8'i 30 dk enerjiler → operator
        #   `AI Pro` baslatir (yalniz 1-7). Bobin 8'i artik ne AI Pro dongusunun hedef-kayip
        #   STOP'u (range(1,8)) ne sure-watchdog (sess["coil_ids"]=1-7) ne de teardown kapsar;
        #   ESP kendi 30 dk suresi dolana kadar CANLI HAYVAN uzerinde surer.
        # Hem cont=True (AI→AI devam) hem cont=False (devralma) yolunda gecerli → kilit
        # BLOGUNUN DISINDA, tek yerde hesapla. STOP kilit birakildiktan SONRA gonderilir.
        _orphan_coils = [
            int(c)
            for c in (prev.get("coil_ids") or [])
            if prev.get("is_active") and int(c) not in set(int(x) for x in coil_ids)
        ]
    if _orphan_coils:
        try:
            _bildir_teyitsiz_stop(_stop_session_coils(_orphan_coils), "Sahipsiz bobin durdurması")
            logging.getLogger(__name__).warning(
                "AI seansi daha DAR bir bobin kumesi sahiplendi → sahipsiz kalan bobinler "
                "durduruldu %s (aksi halde enerjili kalirlardi).",
                _orphan_coils,
            )
        except Exception:
            logging.getLogger(__name__).exception("Sahipsiz bobin STOP hatasi: %s", _orphan_coils)
    # P1 audit 2026-06-28: AKTIF MANUEL (non-AI) seans varken AI baslayinca _active_session KOSULSUZ
    # eziliyordu → manuel db_session_id/coil_ids kayboluyor, acik coil-run'lar kapanmiyor, DB satiri
    # kalici 'active' kaliyor (KPI/history sisiyor + STM keep-alive surer ama UI 'AI' gosterir).
    # Yeni AI seansini kurduktan SONRA eski manuel seansi DUZGUN kapat (orphan onle). Hizli: coil-run
    # in-memory + ~ms DB write; AI coil komutlari start_ai_session DONDUKTEN sonra → race yok.
    if not cont and prev.get("is_active"):
        try:
            # DENETIM 2026-08-17: burada coil-run kapatma + end_session ELLE yapiliyordu; iki eksigi
            # vardi. (1) `_emit_minute_averages()` CAGRILMIYORDU → devralinan seansin birikmis KISMI
            # dakikasi `_minute_acc`te KALIYOR ve bir sonraki dakika-loop turunda YENI (AI) seansin
            # db_session_id'si ile yaziliyordu: onceki hastanin sicaklik/akim ornekleri BASKA bir
            # seansin tibbi kaydina karisiyordu. (2) `ended_epoch` yazilmiyordu. Ikisi de
            # `_finalize_session_db`de zaten dogru: coil-run'lari kapatir, kismi dakikayi DOGRU
            # (eski) db_session_id'ye doker, buffer'i flush eder, end_session + ended_epoch yazar.
            # ⚠️ SENKRON DB isi: `start_ai_session`in iki cagricisi da event-loop DISINDA
            # (`asyncio.to_thread(_drive_landmark_auto)` ve senkron `def start_ai_pro` → FastAPI
            # threadpool'u) → `_finalize_session_db`in "yalniz thread'lerden" sozlesmesi korunur.
            # ⚠️ Coil-run kapatma BURADA kalir, `_finalize_session_db`e devredilmez: finalize
            # `if not db_session_id: return 0` ile ilk satirda doner, yani DB satiri hic acilmamis
            # bir seansta acik coil-run'lar kapatilmadan kalirdi (eski davranis kapatiyordu).
            for _cid in prev.get("coil_ids") or []:
                try:
                    _finish_coil_run(_cid)
                except Exception:
                    pass
            _finalize_session_db(
                prev.get("db_session_id"),
                prev.get("started_epoch") or prev.get("start_time"),
                reason="ai-devralma",
            )
            logging.getLogger(__name__).warning(
                "AI seansi (%s) aktif MANUEL seansi devraldi → eski seans (db_id=%s) duzgun kapatildi (orphan onlendi).",
                mode,
                prev.get("db_session_id"),
            )
        except Exception:
            logging.getLogger(__name__).exception("AI gecisinde eski manuel seans kapatma hatasi")

    # DENETIM 2026-08-17 (hasta-verisi karismasi, `/api/session/start` ile SIMETRI): manuel yol
    # yeni seansta `_minute_acc` + `_sensor_sample_buffer`i temizliyordu (bkz. `start_session`),
    # AI yolu TEMIZLEMIYORDU. Sonuc: onceki seanstan kalan kismi-dakika ve flush edilmemis sensor
    # ornekleri, `_flush_sensor_buffer_if_active` GUNCEL `db_session_id`yi kullandigi icin YENI AI
    # seansinin satirina yaziliyordu → yanlis seansa/hastaya ait tibbi kayit.
    # ⚠️ Yukaridaki finalize onceki seansin verisini KENDI satirina zaten dokuyor; buradaki temizlik
    # (a) DB satiri hic acilmamis seans (finalize ilk satirda doner) ve (b) hic aktif seans olmayan
    # ama buffer'da artik kalan durum icin. Finalize yazimi basarisiz olup ornekleri buffer'a GERI
    # koyduysa da temizlenirler: veri kaybi, YANLIS HASTAYA yazmaktan iyidir (manuel yolun karari).
    # ⚠️ `cont=True` (ayni AI seansinin tekrarli cagrisi — landmark auto_adjust her istekte cagirir)
    # yolunda TEMIZLENMEZ; aksi halde suren seansin kendi telemetrisi her istekte silinirdi.
    if not cont:
        with _minute_acc_lock:
            _minute_acc.clear()
        with _sensor_sample_buffer_lock:
            _sensor_sample_buffer.clear()

    # DENETIM P1: otonom (AI Pro / AI Auto) tedavinin DB seans satirini AC. Eskiden hic
    # acilmadigi icin canli hayvana uygulanan dozun, dakika-ortalamali sensor/sicaklik
    # telemetrisinin ve seansin kendisinin KALICI KAYDI YOKTU (buffer 20k tavaninda kirpilip
    # atiliyordu). Yalniz YENI seansta (cont=False) acilir; tekrarli AI cagrilari mevcut
    # satiri kullanir. Best-effort: DB hatasi otonom tedaviyi DURDURMAZ (eski davranis).
    if not cont:
        try:
            _db = _get_treatment_db()
            if _db is not None:
                _ai_sid = _db.start_session(treatment_mode=mode, target_condition=None)
                try:
                    _db.set_session_meta(_ai_sid, started_epoch=_started_epoch_ai)
                except Exception:
                    logging.getLogger(__name__).debug("AI set_session_meta hatasi", exc_info=True)
                # YARIS MUHRU: DB yazimi sirasinda seans durdurulmus/devralinmis olabilir →
                # db_session_id'yi YALNIZ hala AYNI seans aktifse damgala (yanlis seansa
                # sensor satiri baglama).
                with _session_lock:
                    if _active_session.get("is_active") and _active_session.get("session_id") == _new_session_id:
                        _active_session["db_session_id"] = _ai_sid
        except Exception:
            logging.getLogger(__name__).exception("AI seansi DB satiri acilamadi (tedavi surer).")


def _finalize_session_db(db_session_id, started_epoch, coil_ids=None, reason: str = "auto") -> int:
    """Seansi DB'de KAPAT: kismi dakika-ortalamasi + sensor buffer flush + end_session/ended_epoch.

    DENETIM P2: /api/session/stop DISINDAKI bitis yollari DB'ye HIC dokunmuyordu:
      - sure-watchdog otomatik tamamlanmasi (frontend timer bitiminde /stop CAGIRMAZ → NORMAL
        tam-sure bitisi de bu yoldan gecer),
      - acil durdurma (_emergency_stop_all).
    Sonuc: treatment_sessions satiri kalici 'active' kalir (KPI/gecmis sisir), son dakikanin
    sensor/sicaklik verisi ve acik coil-run'lar KAYBOLUR — acil durdurmada guvenlik olayinin
    telemetri kaniti da yok olur. SENKRONDUR: yalniz thread'lerden cagrilir (watchdog / e-stop
    thread'i), event-loop'tan DEGIL.
    """
    if not db_session_id:
        return 0
    # Acik coil-run'lari kapat (watchdog yolunda _stop_session_coils zaten yapar; e-stop yapmaz).
    for _cid in coil_ids or []:
        try:
            _finish_coil_run(_cid)
        except Exception:
            logging.getLogger(__name__).debug("finalize: _finish_coil_run(%s) hatasi", _cid, exc_info=True)
    flushed = 0
    try:
        _emit_minute_averages()  # birikmis KISMI dakikayi da buffer'a dok (yoksa kaybolur)
    except Exception:
        logging.exception("finalize: dakika-ortalamasi hatasi")
    try:
        with _sensor_sample_buffer_lock:
            pending = list(_sensor_sample_buffer)
            _sensor_sample_buffer.clear()
        db = _get_treatment_db()
        if db is not None:
            if pending:
                try:
                    flushed = db.add_sensor_samples_batch(db_session_id, pending)
                except Exception:
                    logging.exception("finalize: sensor flush hatasi")
                # DENETIM P2: yazim BASARISIZSA (istisna ya da sessiz 0) ornekleri KAYBETME —
                # buffer'a geri koy ki bir sonraki flush (dakika-loop / sonraki finalize)
                # yeniden denesin. Buffer'in kendi 20k tavani sinirsiz buyumeyi zaten onler.
                if not flushed:
                    with _sensor_sample_buffer_lock:
                        _sensor_sample_buffer[:0] = pending
                    logging.warning("finalize: %d sensor ornegi yazilamadi → buffer'a geri konuldu.", len(pending))
            try:
                _now = time.time()
                dur_min = int((_now - float(started_epoch)) / 60) if started_epoch else None
                # ⚠️ SEBEP ARTIK KAYDA DA GECER (kampanya bulgusu S09). `reason` buraya zaten
                # tasiniyordu ama YALNIZ loglaniyordu → acil durdurma ile biten seans gecmiste
                # normal bitenden ayirt EDILEMIYORDU ("bu hastada e-stop yasandi mi?" cevapsiz).
                from database.treatment_history_db import SEANS_DURUMU_ACIL_DURDURMA

                _durum = SEANS_DURUMU_ACIL_DURDURMA if str(reason or "").startswith("acil-durdurma") else "completed"
                db.end_session(db_session_id, duration_minutes=dur_min, session_status=_durum)
                db.set_session_meta(db_session_id, ended_epoch=_now)
            except Exception:
                logging.exception("finalize: end_session hatasi")
        # notes ucu cift-kayit yapmasin (bkz. session_router db_finalized kontrolu).
        with _session_lock:
            if _active_session.get("db_session_id") == db_session_id:
                _active_session["db_finalized"] = True
        logging.info("Seans DB'de kapatildi (%s): db_id=%s, %d sensor satiri", reason, db_session_id, flushed)
    except Exception:
        logging.exception("finalize: kalici kayit hatasi")
    return flushed


def _session_duration_watchdog():
    """KRİTİK GÜVENLİK: seans süresi dolunca bobinleri DONANIM düzeyinde durdurur.
    Firmware keep-alive süreyi her sn tazelediğinden tek başına auto-stop OLMAZ; bu watchdog
    süre dolunca açık STOP üretir (planlanandan uzun PEMF maruziyetini önler)."""
    import time as _t

    while True:
        try:
            with _session_lock:
                sess = dict(_active_session)
            if sess.get("is_active"):
                total = int(sess.get("duration_minutes", 0)) * 60
                _sm = sess.get("start_mono")
                _elapsed = (
                    (_t.monotonic() - _sm) if _sm is not None else (_t.time() - sess.get("start_time", _t.time()))
                )
                if total > 0 and _elapsed >= total:
                    # Audit P2 (TOCTOU seal): fiziksel STOP'tan HEMEN önce seansın HÂLÂ aynı olduğunu
                    # doğrula — aksi halde operatör A'yı durdurup B'yi aynı bobinlerde başlattıysa bayat
                    # snapshot B'nin TAZE bobinlerini durdurur + coil-run'larını bozar (pencere ~µs'e iner).
                    with _session_lock:
                        _still_same = bool(_active_session.get("is_active")) and _active_session.get(
                            "session_id"
                        ) == sess.get("session_id")
                    if not _still_same:
                        continue  # seans devralındı/durduruldu → bayat watchdog turu dokunmasın
                    _bildir_teyitsiz_stop(
                        _stop_session_coils(sess.get("coil_ids", list(range(1, 9)))),
                        "Süre doldu — otomatik durdurma",
                    )
                    with _session_lock:
                        if _active_session.get("session_id") == sess.get("session_id"):
                            _active_session["is_active"] = False
                    # DENETIM P2: seansi DB'de de KAPAT. Frontend timer bitiminde /stop
                    # cagirmadigindan NORMAL tam-sure bitisi buradan gecer; eskiden satir
                    # kalici 'active' kaliyor ve son dakikanin sensor verisi kayboluyordu.
                    _finalize_session_db(sess.get("db_session_id"), sess.get("started_epoch"), reason="sure-doldu")
                    try:
                        update_live_session_state(is_active=False, mode="Sistem Hazır")
                        _ws_broadcast_sync(
                            {"type": "session_completed", "data": {"session_id": sess.get("session_id")}}
                        )
                    except Exception:
                        pass
                    logging.info("Süre doldu → seans otomatik durduruldu (watchdog): %s", sess.get("session_id"))
        except Exception:
            logging.exception("session_duration_watchdog hata")
        _t.sleep(1)


# (audit B-2.2) session-watchdog başlatma _start_background_threads()'e taşındı (lifespan startup).


def _hardware_simulation_loop():
    """PEMF_SIMULATE=1: gerçek donanım yokken sanal STM+ESP bobin + sensör verisi üretip
    WS ile yayınlar (Dashboard/Sensör/Kontrol/KPI testleri için). Seans aktifken bobinler
    seansın freq/duty'siyle 'çalışıyor' görünür; aksi halde boşta + ortam sıcaklığı."""
    import math
    import random
    import time as _t

    t0 = _t.time()
    while True:
        try:
            now = _t.time()
            el = now - t0
            with _session_lock:
                sess = dict(_active_session)
            active = bool(sess.get("is_active"))
            sfreq = float(sess.get("frequency") or 0)
            sduty = float(sess.get("duty") or 0)
            scoils = set(sess.get("coil_ids") or [])
            snaps = []
            with _live_state_lock:
                _live_state["gateway"] = "online"
                _live_state["mqtt"] = "online"
                _live_state["stm"] = "online"
                for idx in range(8):
                    coil = _live_state["coils"][idx]
                    cid = idx + 1
                    coil["connected"] = True
                    running = active and ((cid in scoils) if scoils else True)
                    coil["running"] = running
                    if running:
                        d = sduty or 25.0
                        coil["frequencyHz"] = round(sfreq or 50.0, 1)
                        coil["dutyCycle"] = round(d, 1)
                        coil["magneticMt"] = round(
                            d / 25.0 * 2.0 + 0.25 * math.sin(el * 2 + idx) + random.uniform(-0.04, 0.04), 3
                        )
                        coil["currentA"] = round(0.35 + d / 100.0 * 0.6 + random.uniform(-0.02, 0.02), 3)
                        coil["objectTemp"] = round(
                            26.0 + min(el / 25.0, 14.0) + 0.4 * math.sin(el * 0.5 + idx) + random.uniform(-0.2, 0.2), 1
                        )
                    else:
                        coil["frequencyHz"] = 0
                        coil["dutyCycle"] = 0
                        coil["magneticMt"] = round(abs(random.uniform(0, 0.05)), 3)
                        coil["currentA"] = round(abs(random.uniform(0, 0.02)), 3)
                        coil["objectTemp"] = round(24.0 + 0.3 * math.sin(el * 0.3 + idx) + random.uniform(-0.2, 0.2), 1)
                    coil["ambientTemp"] = round(23.0 + random.uniform(-0.3, 0.3), 1)
                    snaps.append(dict(coil))
            _ws_broadcast_sync({"type": "gateway_status", "data": {"gateway": "online", "mqtt": "online"}})
            _ws_broadcast_sync({"type": "stm_status", "data": {"stm": "online"}})
            for coil in snaps:
                _ws_broadcast_sync({"type": "coil_status", "coilId": coil["id"], "data": coil})
                _ws_broadcast_sync(
                    {
                        "type": "sensor_data",
                        "coilId": coil["id"],
                        "timestamp": now,
                        "data": {
                            "magneticMt": coil["magneticMt"],
                            "objectTemp": coil["objectTemp"],
                            "ambientTemp": coil["ambientTemp"],
                            "currentA": coil["currentA"],
                        },
                    }
                )
        except Exception:
            logging.exception("hardware sim loop error")
        _t.sleep(0.5)


def _emit_minute_averages(now=None):
    """Modul-duzeyi _minute_acc icindeki n>0 her bobin icin DAKIKA-ortalamasi satirini
    _sensor_sample_buffer'a ekler ve akumulatoru SIFIRLAR. Ayrica per-RUN istatistigini
    (_coil_run_stats) gunceller. Ham veri YERINE dakika-ortalamasi → 20dk seans ≈ bobin basina ~20 satir.
    Hem dakika-loop hem /api/session/stop (kismi dakika) cagirir; thread-safe."""
    if now is None:
        now = time.time()
    rows = []
    with _minute_acc_lock:
        snapshot = list(_minute_acc.items())
        _minute_acc.clear()
    for coil_id, acc in snapshot:
        n = acc.get("n", 0)
        if n <= 0:
            continue
        with _active_coil_runs_lock:
            run_id = _active_coil_runs.get(coil_id)
        _tn = acc.get("t_n", 0)
        _in = acc.get("i_n", 0)
        _bn = acc.get("b_n", 0)
        _an = acc.get("amb_n", 0)
        # Metrik o dakika HIC okunmadiysa 0.0 — ESKI davranisla birebir ayni (t_sum/n zaten
        # 0.0 verirdi); asagi-akista (grafik/rapor) yeni None/NULL riski OLUSTURMAZ.
        amb_avg = (acc["amb_sum"] / _an) if _an else 0.0
        rows.append(
            {
                "coil_id": str(coil_id),
                "sample_ts": now,
                "temperature_c": (acc["t_sum"] / _tn) if _tn else 0.0,
                "ambient_temp_c": amb_avg,
                "current_a": (acc["i_sum"] / _in) if _in else 0.0,
                "magnetic_field_mt": (acc["b_sum"] / _bn) if _bn else 0.0,
                "pwm_frequency_hz": acc.get("freq"),
                "pwm_duty_percent": acc.get("duty"),
                "phase": acc.get("phase"),
                "sample_count": n,
                "coil_run_id": run_id,
                "payload": {"aggregated": True, "minute": True},
            }
        )
        # Per-RUN ozet akumulatoru: dakika-ortalamasi run istatistigine de katki saglar.
        if run_id is not None:
            with _coil_run_stats_lock:
                st = _coil_run_stats.get(run_id)
                if st is not None:
                    st["n"] += n
                    st["t_sum"] += acc["t_sum"]
                    st["i_sum"] += acc["i_sum"]
                    st["b_sum"] += acc["b_sum"]
                    st["t_n"] = st.get("t_n", 0) + acc.get("t_n", 0)
                    st["i_n"] = st.get("i_n", 0) + acc.get("i_n", 0)
                    st["b_n"] = st.get("b_n", 0) + acc.get("b_n", 0)
                    tmn, tmx = acc.get("t_min"), acc.get("t_max")
                    if tmn is not None:
                        st["t_min"] = tmn if st["t_min"] is None else min(st["t_min"], tmn)
                    if tmx is not None:
                        st["t_max"] = tmx if st["t_max"] is None else max(st["t_max"], tmx)
    if rows:
        with _sensor_sample_buffer_lock:
            _sensor_sample_buffer.extend(rows)
            if len(_sensor_sample_buffer) > 20000:
                del _sensor_sample_buffer[: len(_sensor_sample_buffer) - 20000]


def _flush_sensor_buffer_if_active():
    """P2 audit 2026-06-28: aktif seansin db_session_id'si varsa _sensor_sample_buffer'i DB'ye yaz
    (periyodik kalicilastirma → cokmede/20k-cap'te telemetri kaybini onler). Basarisizsa GERI koyar.
    Yalniz arka-plan _sensor_persistence_loop thread'inden cagrilir → event-loop'u bloklamaz."""
    with _session_lock:
        _db_sid = _active_session.get("db_session_id")
    if not _db_sid:
        return
    with _sensor_sample_buffer_lock:
        pending = list(_sensor_sample_buffer)
        _sensor_sample_buffer.clear()
    if not pending:
        return
    try:
        _get_treatment_db().add_sensor_samples_batch(_db_sid, pending)
    except Exception:
        with _sensor_sample_buffer_lock:
            _sensor_sample_buffer[:0] = pending  # geri koy (sonraki flush/stop yazar)
        logging.getLogger(__name__).debug("periyodik sensor flush hatasi", exc_info=True)


def _sensor_persistence_loop():
    """Aktif seans boyunca her ~2sn _live_state'ten ÇALIŞAN bobinlerin sensör değerlerini
    DAKIKA-ortalama akumulatorunde toplar (canli WS yayini KORUNUR; yayin sim/HW kendi
    looplarinda). Her 60sn'de per-bobin dakika-ortalamasi _sensor_sample_buffer'a yazilir.
    Buffer /api/session/notes + /api/session/stop ile gercek db_session_id ile flush edilir.
    Boylece HAM yazma YERINE dakika-ortalamasi (20dk seans ≈ bobin basina ~20 satir)."""
    import time as _t

    minute_start = _t.time()
    while True:
        try:
            with _session_lock:
                active = bool(_active_session.get("is_active"))
            if active:
                with _live_state_lock:
                    coils = [dict(_live_state["coils"][i]) for i in range(8)]
                with _minute_acc_lock:
                    for coil in coils:
                        if not coil.get("running"):
                            continue
                        try:
                            cid = int(coil.get("id"))
                        except Exception:
                            continue
                        # DENETIM P2 (sahte olcum): STM bobinlerinde (1-5) sicaklik/akim/alan
                        # telemetrisi YOKTUR — seri protokol yalniz duty/phase/freq/duration
                        # dondurur ve update_live_coil_from_stm bu alanlara hic dokunmaz. Ama
                        # _live_state baslangic degeri 0.0 oldugu icin "is not None" kontrolu
                        # onu GERCEK olcum sayip DB'ye "temperature_c=0.0, sample_count=30"
                        # yaziyordu → gecmis/PDF raporunda "olculmedi" yerine "0.0 °C olculdu"
                        # gorunuyor, asiri-isinma analizi ve hasta sahibine giden rapor yanlis
                        # veriyle uretiliyordu. Olcum KAYNAGI (gercek MQTT telemetrisi) yoksa
                        # hic biriktirme → _emit_minute_averages n<=0 satirini zaten atlar.
                        # NOT: 0.0-yerine-NULL yolu BILEREK secilmedi; asagi-akis (PDF/KPI/grafik)
                        # 0.0 bekliyor (onceki denetimin bilincli karari) — sahte satiri hic
                        # uretmemek ayni sonucu downstream riski OLMADAN verir.
                        if _coil_last_telemetry.get(cid - 1) is None:
                            continue
                        temp = coil.get("objectTemp")
                        cur = coil.get("currentA")
                        fld = coil.get("magneticMt")
                        amb = coil.get("ambientTemp")
                        acc = _minute_acc.get(cid)
                        if acc is None:
                            acc = {
                                "t_sum": 0.0,
                                "t_min": None,
                                "t_max": None,
                                "i_sum": 0.0,
                                "b_sum": 0.0,
                                "amb_sum": 0.0,
                                "n": 0,
                                "t_n": 0,
                                "i_n": 0,
                                "b_n": 0,
                                "amb_n": 0,
                                "freq": coil.get("frequencyHz"),
                                "duty": coil.get("dutyCycle"),
                                "phase": coil.get("phase"),
                            }
                            _minute_acc[cid] = acc
                        if temp is not None:
                            tv = float(temp)
                            acc["t_sum"] += tv
                            acc["t_n"] += 1
                            acc["t_min"] = tv if acc["t_min"] is None else min(acc["t_min"], tv)
                            acc["t_max"] = tv if acc["t_max"] is None else max(acc["t_max"], tv)
                        if cur is not None:
                            acc["i_sum"] += float(cur)
                            acc["i_n"] += 1
                        if fld is not None:
                            acc["b_sum"] += float(fld)
                            acc["b_n"] += 1
                        if amb is not None:
                            acc["amb_sum"] += float(amb)
                            acc["amb_n"] += 1
                        acc["n"] += 1
                        # En guncel parametreleri sakla (dakika boyunca degisebilir).
                        acc["freq"] = coil.get("frequencyHz")
                        acc["duty"] = coil.get("dutyCycle")
                        if coil.get("phase") is not None:
                            acc["phase"] = coil.get("phase")
                # Dakika siniri: ortalama satirlarini emit et (akumulatoru sifirlar).
                if (_t.time() - minute_start) >= 60.0:
                    _emit_minute_averages(_t.time())
                    _flush_sensor_buffer_if_active()  # P2 audit: periyodik DB flush (cokme/cap kaybi onle)
                    minute_start = _t.time()
            else:
                minute_start = _t.time()
        except Exception:
            logging.exception("sensor persistence loop error")
        _t.sleep(2.0)


# (audit B-2.2) sensor-persist başlatma _start_background_threads()'e taşındı (lifespan startup).


def _daily_maintenance_loop():
    """Asama-2 (4): GUNLUK arka-plan bakim — retention temizligi + .db yedek.
    - Retention: sensor_samples (PEMF_SENSOR_RETAIN_DAYS, vars. 90) + session_events (365).
      Run-ozetleri run bitiminde yazildigindan ham silinince ozet kalir.
    - Haftada bir wal_checkpoint(TRUNCATE) + VACUUM (run_maintenance helper'i + VACUUM).
    - Gunluk .db yedek: once wal_checkpoint, sonra pemf_treatment_history.db ->
      app_data/backups/pemf_treatment_history_YYYYMMDD.db (shutil.copy2). Son 14 yedek tutulur.
    Hata olursa loglanir, cokmez. Ilk calisma acilistan ~60sn sonra (acilisi yavaslatmamak icin)."""
    import time as _t

    log = logging.getLogger(__name__)
    _t.sleep(60)  # acilisi yavaslatma
    run_count = 0
    while True:
        try:
            retain_days = int(os.getenv("PEMF_SENSOR_RETAIN_DAYS", "90"))
        except Exception:
            retain_days = 90
        try:
            db = _get_treatment_db()
            if db is not None:
                # 1) Retention temizligi.
                try:
                    removed_s = db.purge_old_sensor_samples(retain_days)
                    removed_e = db.purge_old_session_events(365)
                    # ⚠️ DOZ SİLME BU DÖNGÜDEN KALDIRILDI (denetim 2026-08-17). Burası
                    # `PEMF_SENSOR_RETAIN_DAYS` okuyordu — headless bakımın kullandığı
                    # `PEMF_RETAIN_SENSOR_DAYS`ten FARKLI, hiçbir yerde belgelenmemiş bir ad.
                    # Sonuç: operatör `PEMF_RETAIN_SENSOR_DAYS=0` yazıp "silme kapalı" sansa bile
                    # uygulanan doz 90 günde BURADAN silinmeye devam ediyordu. Üstelik bu yolda
                    # `0` = kapalı DEĞİLDİ: `purge_old_coil_runs` içindeki `max(1, ...)` yüzünden
                    # `0` → 1 GÜNLÜK saklama, yani neredeyse tüm doz geçmişi.
                    # Silme yeteneği kaybolmuyor: `services/headless_db_maintenance` üretimde her
                    # zaman koşuyor ve aynı işi `apply_data_retention_policy` üzerinden
                    # YAPILANDIRILABİLİR biçimde (`PEMF_RETAIN_DOSE_DAYS`) yapıyor.
                    log.info("Retention: %s sensor + %s event silindi.", removed_s, removed_e)
                    # KVKK retention (2026-06-28): 5 YIL inaktif hastalari ANONIMLESTIR (canonical
                    # patient_database + treatment-history kopyasi). Muafiyet yok.
                    try:
                        _pdb = get_patient_database()
                        if _pdb is not None:
                            _anon = _pdb.anonymize_inactive_patients(1825)
                            if _anon:
                                db.anonymize_patients_by_uuid(_anon)
                                log.warning("KVKK: %d inaktif hasta anonimlestirildi.", len(_anon))
                    except Exception:
                        log.warning("Hasta retention (anonimlestirme) hatasi", exc_info=True)
                except Exception:
                    log.warning("Retention temizleme hatasi", exc_info=True)

                # 2) Haftada bir checkpoint + VACUUM.
                # DENETIM P3: kosul `run_count % 7 == 0` idi ve run_count 0'dan basladigi icin
                # VACUUM "haftada bir" DEGIL, HER BACKEND ACILISINDAN ~60 sn SONRA calisiyordu.
                # VACUUM tum DB'yi yeniden yazar ve OZEL kilit tutar; busy_timeout 5 sn oldugundan
                # o pencerede baslayan bir seansin sensor/coil-run yazimlari "database is locked"
                # ile dusebiliyordu (sessiz telemetri kaybi). Iki kapak: (a) ilk turda ATLA →
                # restart dongusu her seferinde VACUUM tetiklemesin; (b) AKTIF SEANS varken ATLA →
                # tedavi sirasinda DB'yi kilitleme (bir sonraki turda yapilir).
                _sess_active = False
                try:
                    with _session_lock:
                        _sess_active = bool(_active_session.get("is_active"))
                except Exception:
                    _sess_active = True  # emin degilsek VACUUM YAPMA (fail-safe)
                if run_count > 0 and run_count % 7 == 0 and not _sess_active:
                    try:
                        if hasattr(db, "run_maintenance"):
                            db.run_maintenance()  # wal_checkpoint(TRUNCATE) + optimize
                        conn_fn = getattr(db, "_get_connection", None)
                        if conn_fn is not None:
                            with conn_fn() as conn:
                                cur = conn.cursor()
                                try:
                                    cur.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                                except Exception:
                                    pass
                                try:
                                    # VACUUM islem (transaction) icinde calismaz → autocommit'e gec.
                                    conn.isolation_level = None
                                    cur.execute("VACUUM")
                                except Exception:
                                    pass
                    except Exception:
                        log.warning("Haftalik VACUUM/checkpoint hatasi", exc_info=True)

                # 3) GUNLUK YEDEK: BURADA YAPILMIYOR (P1 cift-yazici cakismasi giderildi).
                # Yedegi services/headless_db_maintenance.py (HeadlessDBMaintenance) aliyor:
                # KEYED create_backup() → SIFRELI + atomik (sifreli DB'de duz-metin sizmaz).
                # Eskiden burada shutil.copy2 (duz-metin) ile AYNI backups/ dizinine + AYNI glob'a
                # (pemf_treatment_history_*.db, son-14) yaziliyordu → iki zamanlayici birbirinin
                # yedegini SILIYORDU ve PII duz-metin yedekleniyordu. Yedek tek noktada toplandi.
        except Exception:
            log.warning("daily maintenance loop genel hatasi", exc_info=True)
        run_count += 1
        _t.sleep(86400)  # gunde bir kez


_bg_threads_started = False


def _start_background_threads() -> None:
    """Arka-plan daemon thread'lerini başlat: safety süre-watchdog + sensör-persist + günlük-bakım
    (+ PEMF_SIMULATE ile sanal donanım). Idempotent — lifespan startup'tan BİR KEZ çağrılır (audit
    B-2.2: eskiden modül-import anında başlıyordu → import yan-etkisi; test/araç import'u gerçek
    thread açıyor, state.core set edilmeden). Fonksiyonlar bu noktada tanımlı."""
    global _bg_threads_started
    if _bg_threads_started:
        return
    _bg_threads_started = True
    _threading.Thread(target=_session_duration_watchdog, daemon=True, name="session-watchdog").start()
    _threading.Thread(target=_sensor_persistence_loop, daemon=True, name="sensor-persist").start()
    _threading.Thread(target=_daily_maintenance_loop, daemon=True, name="daily-maintenance").start()
    # ESP sessiz-ölüm (ungraceful) tespiti: 30sn telemetri sustuysa coil'i disconnected işaretle
    # (self-heal reconnect-audit). Sim modda no-op (timestamp sözlüğü boş).
    _threading.Thread(target=_esp_telemetry_watchdog, daemon=True, name="esp-telemetry-watchdog").start()
    # CANLI E-ALANI (2026-08-06): 2 Hz'de vekil modeli canlı B/duty ile çalıştırıp önbelleğe yazar.
    # AYRI thread olmasının sebebi: ONNX çağrısı dashboard-snapshot/WS istek yolunda ÇALIŞMASIN.
    # Yalnız aktif seansta + analiz bağlamı varken hesaplar (bkz. servers/efield_live.py).
    try:
        from servers import efield_live as _ef

        _ef.start_loop(
            read_coils=lambda: _build_ws_snapshot().get("coils", []),
            is_session_active=lambda: bool(_active_session.get("is_active")),
        )
    except Exception:
        logging.getLogger(__name__).warning("Canlı E-alanı döngüsü başlatılamadı", exc_info=True)
    if os.environ.get("PEMF_SIMULATE") == "1":
        _threading.Thread(target=_hardware_simulation_loop, daemon=True, name="hw-sim").start()
        logging.info("HARDWARE SIMULATION aktif (sanal STM+ESP+sensor) - PEMF_SIMULATE=1")


@app.post("/api/session/stop")
async def stop_session():
    """Stop the active treatment session.

    Asama-2: donanim durdurulduktan sonra seans+sensor KALICI yazilir (not beklenmez):
    bekleyen kismi dakika emit edilir, acik coil-run'lar kapatilir (run ozeti yazilir),
    sensor buffer'i gercek db_session_id ile flush edilir ve end_session ile GERCEK
    wall-clock sure yazilir. Hepsi best-effort (DB hatasi donanim durdurmayi engellemez)."""
    with _session_lock:
        if not _active_session.get("is_active"):
            return {"status": "ok", "message": "Aktif seans yok."}
        coil_ids = _active_session.get("coil_ids", list(range(1, 9)))
        db_session_id = _active_session.get("db_session_id")
        started_epoch = _active_session.get("started_epoch") or _active_session.get("start_time")
        _stopping_session_id = _active_session.get("session_id")  # TOCTOU muhru (asagi bkz.)
        _active_session["is_active"] = False

    # (a) Bekleyen kismi dakikayi emit et — acik run-ozetine de katki saglar (finish'ten ONCE).
    try:
        _emit_minute_averages(time.time())
    except Exception:
        logging.getLogger(__name__).debug("stop: minute emit hatasi", exc_info=True)

    # Donanim STOP (ESP→MQTT, STM→update_coil). _stop_session_coils ayrica acik coil-run'lari kapatir.
    # P-1b: senkron _mqtt_publish (~2s/ESP-bobin) event-loop'u DONDURMASIN → to_thread (emergency_stop
    # deseniyle birebir; bobinler yine durur, sadece threadpool'da). Watchdog'dan (1327) cagri sync kalir.
    # DENETIM P2 (TOCTOU): yukarida is_active=False yapilip KILIT BIRAKILIYOR. Bu await
    # penceresinde (saglikli broker'da ~10-100 ms, cokuk broker'da saniyeler) BASKA bir istemci
    # /api/session/start atabilir → yeni seans bobinleri ENERJILER, hemen ardindan buradaki
    # _stop_session_coils AYNI fiziksel bobinleri durdurur: yeni seans sessizce olur (UI 'suruyor'
    # sanir, coil-run/sensor kayitlari bozulur). Sure-watchdog'da bu muhur (1600-1604 `_still_same`)
    # ZATEN vardi; /stop yolunda YOKTU. Donanima dokunmadan hemen once ayni seansta miyiz diye bak.
    with _session_lock:
        _takeover = bool(_active_session.get("is_active")) and _active_session.get("session_id") != _stopping_session_id
    # DENETIM 2. TUR [1.1]: donanim STOP'u dogrulanamayan bobinler yanita tasinir (asagida).
    _stop_teyitsiz: list = []
    if _takeover:
        logging.getLogger(__name__).warning(
            "stop: bu seans (%s) durdurulurken YENI seans (%s) baslamis → donanim STOP'u ATLANDI "
            "(bobinler yeni seansa ait).",
            _stopping_session_id,
            _active_session.get("session_id"),
        )
    else:
        _stop_teyitsiz = await asyncio.to_thread(_stop_session_coils, coil_ids) or []
        update_live_session_state(is_active=False, mode="Sistem Hazır")

    # (b) Sensor buffer'i gercek db_session_id ile FLUSH et + (c) end_session (gercek wall-clock sure).
    # P-2 fix: senkron SQLCipher yazimlari (add_sensor_samples_batch/end_session/set_meta) event-loop'u
    # BLOKLAMASIN → to_thread; buffer-grab + db_finalized-isaret hizli/async kalir.
    flushed = 0
    if db_session_id:
        try:
            with _sensor_sample_buffer_lock:
                pending = list(_sensor_sample_buffer)
                _sensor_sample_buffer.clear()

            def _persist_session_stop():
                _flushed = 0
                db = _get_treatment_db()
                if db is not None:
                    if pending:
                        try:
                            _flushed = db.add_sensor_samples_batch(db_session_id, pending)
                            logging.info("stop: sensor flush %d satir (session_id=%s)", _flushed, db_session_id)
                        except Exception:
                            logging.exception("stop: sensor flush hatasi")
                    try:
                        _now = time.time()
                        dur_min = int((_now - float(started_epoch)) / 60) if started_epoch else None
                        db.end_session(db_session_id, duration_minutes=dur_min)
                        # Yeni kolon: gercek wall-clock bitis epoch'u (end_session bunu yazmaz).
                        db.set_session_meta(db_session_id, ended_epoch=_now)
                    except Exception:
                        logging.exception("stop: end_session hatasi")
                return _flushed

            flushed = await asyncio.to_thread(_persist_session_stop)
            # Bu seansin DB satiri kapandi → notes endpoint cift-kayit yapmasin.
            # YARIS FIX: kilit birakilip yeniden alindi; ARADA yeni bir seans BASLAMIS olabilir
            # (_active_session yeni dict ile degismis). db_finalized'i YENI seansa damgalama →
            # yalniz AYNI (bu) seans hala yerindeyse (is_active False + ayni db_session_id) isaretle.
            with _session_lock:
                if not _active_session.get("is_active") and _active_session.get("db_session_id") == db_session_id:
                    _active_session["db_finalized"] = True
        except Exception:
            logging.exception("stop: kalici kayit genel hatasi")
    else:
        # P2 audit 2026-06-28: db_session_id YOK → bu seansin sensor verisi DB'ye yazilamaz; eskiden
        # SESSIZCE kayboluyordu (sonraki seans start'inda buffer temizlenir). UYAR + buffer'i simdi
        # temizle (sonraki seansa sizmasin).
        with _sensor_sample_buffer_lock:
            _lost = len(_sensor_sample_buffer)
            _sensor_sample_buffer.clear()
        if _lost:
            logging.warning(
                "stop: db_session_id YOK → %d sensor satiri KALICI DEGIL (kayip). Seans DB'ye baglanmamis.", _lost
            )

    # DENETIM 2. TUR [1.1] (2026-08-20): ust-seviye status "success" KALIR (seans kaydi gercekten
    # kapatildi; mevcut cagiranlarin sozlesmesi bozulmaz) ama donanim STOP'u DOGRULANAMAYAN
    # bobinler ACIKCA listelenir. Eskiden broker oluyken bile kosulsuz "success" donuyordu →
    # istemcinin "Durdurma onaylanamadi — ACIL DURDUR'a basin" uyarisi HIC tetiklenmiyordu
    # (STOP hicbir bobine ulasmamisken UI seansi "durdu" gosterir). Alan yalniz teyitsizlik
    # VARSA eklenir — mutlu yolda yanit sekli birebir ayni (alarm yorgunlugu uretme).
    _yanit = {"status": "success", "message": "Seans durduruldu.", "sensor_samples": flushed}
    if not _stop_teyitsiz:
        return _yanit

    # ─────────────────────────────────────────────────────────────────────────────────────────
    # ⚠️ GÜVENLİK SİNYALİ SÖZLEŞMESİ — "BİLİNMİYORSA KÖTÜMSER" (sahip kararı 2026-08-22)
    #
    # [1.1]'in ilk hâli üst-seviye `status`u "success" bırakıp uyarıyı YENİ bir alana koyuyordu
    # (`hardware_stop_unconfirmed`). Sürüm kayması senaryosu ölçüldü: telefon eski sürümde
    # kalabilir (Android'de kurulumu İŞLETİM SİSTEMİ sorar; güncelleme zorunlu kılınamaz — bkz.
    # MobileUpdateGate). Eski istemcide o alanı okuyan kod YOKTUR ve kontrolü
    # `res.status === "error"` biçimindedir → tanımadığı her değeri BAŞARI sayar. Sonuç:
    # bobinler hâlâ çalışıyorken operatör düz "seans durduruldu" görüyordu. Yani düzeltme,
    # düzeltmeyi en çok gereken istemciye HİÇ ulaşmıyordu.
    #
    # ÇÖZÜM: uyarıyı yeni bir alana DEĞİL, eski istemcinin de anladığı KANALA koy → 2xx DIŞI
    # yanıt. Ölçülen davranış (pf/src/services/apiClient.ts):
    #   · `!response.ok` → gövde `detail` alanı okunur ve `showError("Sunucu Hatası", detail)`
    #     ile EKRANA BASILIR → eski istemci uyarının METNİNİ görür,
    #   · çağrıya `null` döner → `useSessionControl` "Durdurma onaylanamadı … ACİL DURDUR'a
    #     basın" uyarısını gösterir → eylem TAVSİYESİ de doğru olur.
    # Yeni istemci `onHttpError` ile 409'u ayırt eder, seansı kapatır ve SPESİFİK bobin
    # listesini gösterir (aşağıdaki alanlar korunur).
    #
    # ⚠️ 2xx SEÇİLEMEZ: 207 Multi-Status da `response.ok`tur → eski istemci yine sessizce
    # başarı sayardı. Fail-safe olması için yanıt 2xx DIŞI olmalıdır. 409 Conflict seçildi:
    # istek işlendi (seans kaydı GERÇEKTEN kapandı) ama donanım durumu çelişkili.
    #
    # ⚠️ SEANS KAYDI KAPANDI — bu bir "işlem başarısız" durumu DEĞİLDİR. `session_closed: true`
    # alanı bunu açıkça söyler ki yeni istemci UI'da seansı yeniden "açık" göstermesin.
    # ─────────────────────────────────────────────────────────────────────────────────────────
    _uyari = (
        f"Bobin {', '.join(str(c) for c in _stop_teyitsiz)} için donanım STOP'u DOĞRULANAMADI — "
        "HÂLÂ ÇALIŞIYOR olabilirler. ACİL DURDUR'a basın ya da cihazın fiziksel güç düğmesini kullanın."
    )

    # ⚠️ UYARI KAYBOLMAYACAK BİR YERE DE DÜŞER (sahip kararı 2026-08-22, 3. madde): telefon eski
    # sürümdeyse ya da ekranı kimse görmüyorsa uyarı yok olmasın. Bildirim akışı klinik
    # bilgisayarındaki arayüzde görünür (masaüstü arayüzü paketle birlikte GÜNCELDİR) ve günlüğe
    # yazılır — böylece uyarı en azından BİRİNE ulaşır ve destek sonradan izini sürebilir.
    try:
        _push_notification(f"🚨 {_uyari}", "error")
    except Exception:  # noqa: BLE001 — bildirim yolu çökse bile yanıt DÖNMELİ
        logging.exception("stop: teyitsiz-durdurma bildirimi gonderilemedi")
    logging.error("stop: donanim STOP DOGRULANAMADI — bobinler=%s", _stop_teyitsiz)

    _yanit["status"] = "hardware_stop_unconfirmed"
    _yanit["message"] = _uyari
    _yanit["detail"] = _uyari  # eski istemci YALNIZ bunu görebiliyor (apiClient showError)
    _yanit["hardware_stop_unconfirmed"] = _stop_teyitsiz
    _yanit["session_closed"] = True
    return JSONResponse(status_code=409, content=_yanit)


class AiLogPayload(BaseModel):
    # Geriye-uyumlu alanlar (eski istemci yalnız bunları gönderir):
    patient_name: str = ""
    module: str = ""  # modül etiketi → module_label
    summary: str = ""  # sonuç özeti → result_summary
    # 2026-07 profesyonel DETAYLI kayıt — yeni istemci ayrıca gönderir:
    mode: str = ""  # profil (pet_owner/veterinarian/researcher)
    module_id: str = ""  # AiModule id (em_fantom, kidney_ct, ...)
    input_type: str = ""  # image / clinical / audio / csv ...
    result_detail: dict = {}  # tam sonuç JSON (heterojen)
    confidence: float | None = None
    operator_email: str = ""  # klinik-içi sahiplik — analizi yapan hekim ("Benim/Tüm Klinik")


_ai_migrate_lock = _threading.Lock()


def _migrate_ai_jsonl_once(db) -> None:
    """Eski düz-metin ai_diagnoses.jsonl → şifreli ai_analyses (TEK SEFERLİK, best-effort, THREAD-SAFE).
    Çift-kontrollü kilit: iki eşzamanlı istek DUPLICATE kayıt üretemez. Yalnız POST yolunda çağrılır
    (GET read-only kalsın); başarılı taşımada dosya .migrated'a taşınır → sonraki çağrılarda no-op."""
    try:
        p = _app_data_dir() / "ai_diagnoses.jsonl"
        if db is None or not p.exists():
            return  # hızlı yol — kilit gerektirmez
        with _ai_migrate_lock:
            if not p.exists():
                return  # başka thread taşımış (kilit altında yeniden-kontrol → duplicate yok)
            for ln in p.read_text(encoding="utf-8").splitlines():
                try:
                    r = _json.loads(ln)
                    db.add_ai_analysis(
                        module_label=r.get("module", ""),
                        patient_name=r.get("patient_name", ""),
                        result_summary=r.get("summary", ""),
                        result_detail={"legacy": True, "timestamp": r.get("timestamp", "")},
                    )
                except Exception:
                    pass
            p.rename(p.with_name("ai_diagnoses.jsonl.migrated"))
    except Exception:
        logging.exception("ai jsonl migrate failed")


@app.post("/api/ai/log")
async def log_ai_result(payload: AiLogPayload, request: Request):
    """AI analiz sonucunu ŞİFRELİ (SQLCipher) geçmişe profesyonel+detaylı kaydeder (ai_analyses tablosu).
    Eski düz-metin JSONL + isim-maskeleme KALDIRILDI — şifreli olduğundan hasta adı TAM (KVKK-güvenli)."""
    try:
        db = _get_treatment_db()
        if db is None:
            return {"status": "error", "detail": "Kayıt DB yok"}
        await asyncio.to_thread(_migrate_ai_jsonl_once, db)
        from servers.auth import cozumlenmis_operator

        rid = await asyncio.to_thread(
            db.add_ai_analysis,
            payload.mode,
            payload.module_id,
            payload.module,
            str(payload.patient_name or "").strip(),
            payload.input_type,
            payload.summary,
            payload.result_detail or {},
            payload.confidence,
            # ⚠️ 2026-08-09 (Tier 1): AI analizinin sahibi de jetondan türetilir — aksi hâlde
            # "bu teşhisi kim yaptı" sorusunun cevabı doğrulanmamış bir dizeydi.
            cozumlenmis_operator(request, payload.operator_email),
        )
        return {"status": "success", "id": rid}
    except Exception:
        logging.exception("log_ai_result failed")
        return {"status": "error", "detail": "Kayıt başarısız"}


class AiReviewPayload(BaseModel):
    analysis_id: int
    status: str = ""  # approved | rejected | corrected
    note: str = ""  # red gerekçesi ya da hekimin düzeltilmiş teşhisi
    reviewed_by: str = ""  # karar veren hekimin e-postası


@app.post("/api/ai/log/review")
async def review_ai_analysis(payload: AiReviewPayload):
    """AI analizine HEKİM DEĞERLENDİRMESİ ekle (2026-08-06, sahip isteği).

    AI çıktısı bir ÖNERİdir; klinik karar hekimindir. Onay/red/düzeltme kaydın YANINA yazılır —
    AI'ın ne dediği ile hekimin ne dediği ayrı ayrı görünür kalır (sonradan "model ne demişti?"
    sorusu cevaplanabilsin). Kayıt silinmez, AI sonucu değiştirilmez.
    """
    if payload.status not in ("approved", "rejected", "corrected"):
        raise HTTPException(status_code=422, detail="status 'approved', 'rejected' veya 'corrected' olmalı.")
    # Red ve düzeltme GEREKÇESİZ olamaz: boş bir "reddedildi" denetim izinde işe yaramaz ve
    # modeli iyileştirmek için de veri taşımaz. Onay için not opsiyonel.
    if payload.status in ("rejected", "corrected") and not (payload.note or "").strip():
        raise HTTPException(status_code=422, detail="Red ve düzeltme için gerekçe/açıklama zorunludur.")
    db = _get_treatment_db()
    if db is None:
        raise HTTPException(status_code=503, detail="Kayıt veritabanı kullanılamıyor.")
    ok = await asyncio.to_thread(
        db.set_ai_review, int(payload.analysis_id), payload.status, payload.note, payload.reviewed_by
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Analiz kaydı bulunamadı.")
    return {"status": "success", "analysisId": payload.analysis_id, "review": payload.status}


@app.get("/api/ai/log")
async def get_ai_log(limit: int = 50, module_id: str = "", patient_name: str = "", before_id: int = 0):
    """AI analiz geçmişini döndürür (yeni önce). Filtre: modül / hasta / keyset-pagination (before_id)."""
    try:
        db = _get_treatment_db()
        if db is None:
            return {"status": "success", "data": []}
        data = await asyncio.to_thread(
            db.get_ai_analyses,
            int(limit),
            module_id or None,
            patient_name or None,
            (int(before_id) or None),
        )
        return {"status": "success", "data": data}
    except Exception:
        logging.exception("get_ai_log failed")
        return {"status": "error", "detail": "Log okunamadı", "data": []}


def _enforce_privileged(request: Request) -> None:
    """Yıkıcı/PII ucu kapısı — LAN muafiyeti YOK (bkz. servers/auth.enforce_privileged).

    2026-08-09 denetimi (ENGEL): bu uçlar tüm hasta geçmişini dışarı verebiliyor ya da geri
    dönülemez silebiliyordu ve `is_local_request` LAN'ı auth-muaf saydığı için klinik WiFi'sindeki
    HERHANGİ bir cihaz kimliksiz çağırabiliyordu.
    """
    from servers.auth import enforce_privileged

    enforce_privileged(request)


class AiLogDeletePayload(BaseModel):
    """Tekil silme. `operator_email` doluysa yalnız O KİŞİYE ait kayıt silinebilir."""

    id: int
    operator_email: str = ""


class AiLogDeleteAllPayload(BaseModel):
    """Toplu silme. `confirm` ZORUNLU (yanlış-tık/otomatik-istek koruması — hasta silmedeki kural).

    `operator_email` doluysa yalnız o kişinin (ve sahipsiz) kayıtları silinir.

    ⚠️ DENETİM 2026-08-09 (Tier 1) — BOŞ `operator_email` ARTIK "HEPSİNİ SİL" DEMEK DEĞİL.
    Eski kural "boşsa TÜM klinik geçmişi gider" idi ve bu, kimliğin kaybolduğu HER durumu
    sessizce klinik-geneli silmeye çeviriyordu: çoklu-operatör kipinde kimse seçilmemişse
    istemcinin `operatorEmail`i bilerek "" döner → "kendi kayıtlarımı sil" isteği kliniğin
    TÜM AI geçmişini silerdi. Kimlik yokluğu ile "hepsini sil" NİYETİ artık ayrı:
    klinik-geneli silme `all_operators: true` ile AÇIKÇA istenmelidir.
    """

    confirm: str = ""
    operator_email: str = ""
    #: Klinik-geneli silme NİYETİ. Kimliksiz + bayraksız istek REDDEDİLİR (fail-closed).
    all_operators: bool = False


@app.post("/api/ai/log/delete")
async def delete_ai_log_entry(payload: AiLogDeletePayload, request: Request):
    """Tek bir AI analiz kaydını sil (KVKK silme hakkı)."""
    _enforce_privileged(request)
    db = _get_treatment_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Geçmiş veritabanı hazır değil")
    ok = await asyncio.to_thread(db.delete_ai_analysis, int(payload.id), (payload.operator_email or "").strip() or None)
    from servers import audit_log as _iz

    if not ok:
        # Kayıt yok VEYA başkasına ait → ikisini AYIRMA (varlık sızdırmayalım).
        # ⚠️ BAŞARISIZ deneme de yazılır: bir hesabın başkasının kaydını silmeye çalışması,
        # başarılı silme kadar önemli bir sinyaldir.
        _iz.kimlikli_yaz(
            request,
            "ai_log.delete",
            beyan=payload.operator_email or "",
            scope=f"id={payload.id}",
            item_count=0,
            outcome="reddedildi",
        )
        raise HTTPException(status_code=404, detail="Kayıt bulunamadı veya silme yetkiniz yok.")
    logging.getLogger(__name__).warning("KVKK: AI analiz kaydı silindi (id=%s).", payload.id)
    _iz.kimlikli_yaz(
        request, "ai_log.delete", beyan=payload.operator_email or "", scope=f"id={payload.id}", item_count=1
    )
    return {"status": "success", "deleted": 1}


@app.post("/api/ai/log/delete_all")
async def delete_ai_log_all(payload: AiLogDeleteAllPayload, request: Request):
    """AI analiz geçmişini TOPLU sil — `{"confirm":"DELETE_ALL"}` ZORUNLU.

    Hasta toplu-silmesiyle AYNI kapı (bkz. patient_router.remove_all_patients): boş bir POST'un
    geri-dönülemez biçimde tüm geçmişi silmesini engeller.
    """
    _enforce_privileged(request)
    if payload.confirm != "DELETE_ALL":
        raise HTTPException(
            status_code=400, detail="Toplu silme için onay gerekli: gövdede {\"confirm\":\"DELETE_ALL\"} gönderin."
        )
    db = _get_treatment_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Geçmiş veritabanı hazır değil")
    op = (payload.operator_email or "").strip() or None
    # ⚠️ FAIL-CLOSED (2026-08-09): kimlik yok VE klinik-geneli silme AÇIKÇA istenmediyse reddet.
    # Aksi hâlde istemcideki bir kimlik kaybı (operatör seçilmemiş, oturum düşmüş, alan boş
    # gönderilmiş) sessizce "kliniğin tüm AI geçmişini sil"e dönüşürdü — geri dönüşü olmayan bir
    # işlem için kabul edilemez bir varsayılan.
    if op is None and not payload.all_operators:
        raise HTTPException(
            status_code=400,
            detail="Silme kapsamı belirsiz. Kendi kayıtlarınız için operatör seçin; kliniğin "
            "tamamını silmek için isteğe {\"all_operators\": true} ekleyin.",
        )
    n = await asyncio.to_thread(db.clear_ai_analyses, op)
    from servers import audit_log as _iz

    if n < 0:
        _iz.kimlikli_yaz(
            request,
            "ai_log.delete_all",
            beyan=payload.operator_email or "",
            scope=(op or "TUM_KLINIK"),
            item_count=0,
            outcome="hata",
        )
        raise HTTPException(status_code=500, detail="Geçmiş temizlenemedi")
    # KVKK "sildim" kanıtı: kapsam + sayı loglanır (kayıt İÇERİĞİ loglanmaz).
    logging.getLogger(__name__).warning(
        "KVKK: AI analiz geçmişi TOPLU silindi (kapsam=%s, %d kayıt, VACUUM uygulandı).", op or "TÜM KLİNİK", n
    )
    # ⚠️ Denetim izi SİLİNMEZ (ekleme-only mühür): "hepsini sil" bu satırı da silseydi, silmenin
    # olduğunu gösteren tek kanıt kaybolurdu.
    _iz.kimlikli_yaz(
        request,
        "ai_log.delete_all",
        beyan=payload.operator_email or "",
        scope=(op or "TUM_KLINIK"),
        item_count=n,
        detail={"all_operators": bool(payload.all_operators), "vacuum": True},
    )
    return {"status": "success", "deleted": n}


# ─────────────────── CİHAZ TAŞIMA: şifreli dışa/içe aktarma (2026-08-08) ───────────────────
# Kayıtlar bilerek MAKİNEDE tutuluyor (bulut senkronu YOK). Tek gerçek dezavantajı cihaz
# değişimiydi; çözümü bulut değil, kliniğin kendi kontrolündeki şifreli dosya.


class DataExportPayload(BaseModel):
    passphrase: str = ""


class DataImportPayload(BaseModel):
    passphrase: str = ""
    blob_b64: str = ""
    confirm: str = ""  # hedef DOLU ise "REPLACE_ALL" ZORUNLU


@app.post("/api/data/export")
async def export_clinic_data(payload: DataExportPayload, request: Request):
    """Hasta + seans + AI analiz kayıtlarını TEK şifreli dosyaya çıkarır (base64 döner)."""
    _enforce_privileged(request)
    import base64 as _base64

    from utils.data_export import BUNDLE_VERSION, ExportError, encrypt_bundle

    try:
        thdb = _get_treatment_db()
        pdb = get_patient_database()
        if thdb is None or pdb is None:
            raise HTTPException(status_code=500, detail="Veritabanı hazır değil")
        rows = await asyncio.to_thread(thdb.export_rows)
        # ⚠️ İKİ AYRI HASTA DEPOSU VAR ve ikisi de taşınmalı:
        #   rows["patients"]  → tedavi DB'sindeki hasta satırları; `treatment_sessions.patient_id`
        #                       BUNLARA bakar, dolayısıyla ilişkiyi kurmak için ŞART.
        #   pdb.get_all_patients → ayrı hasta veritabanı (arayüzün hasta listesi).
        # Eskiden yalnız ikincisi taşınıyor ve `rows`daki `patients` anahtarını EZİYORDU.
        paket = {
            "bundle_version": BUNDLE_VERSION,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            **rows,
            "patient_db": await asyncio.to_thread(pdb.get_all_patients),
        }
        blob = await asyncio.to_thread(encrypt_bundle, paket, payload.passphrase)
        # ⚠️ DENETİM 2026-08-09 (Tier 1) — ÜRETİLEN DOSYA GERÇEKTEN AÇILIYOR MU?
        # Yedeğin bozuk olduğu, ancak KULLANILMASI gereken gün (eski makine ölmüş, geri dönüş yok)
        # anlaşılırdı. Round-trip doğrulama, aynı parolayla çözüp kayıt sayılarını karşılaştırır;
        # maliyeti tek bir PBKDF2 + gzip açma, karşılığı "bu dosya açılabilir" güvencesi.
        from utils.data_export import decrypt_bundle as _coz

        _geri = await asyncio.to_thread(_coz, blob, payload.passphrase)
        for _t in ("treatment_sessions", "session_coil_runs", "ai_analyses"):
            if len(_geri.get(_t) or []) != len(paket.get(_t) or []):
                logging.getLogger(__name__).error(
                    "VERİ TAŞIMA: round-trip doğrulaması BAŞARISIZ (%s: %d != %d)",
                    _t,
                    len(_geri.get(_t) or []),
                    len(paket.get(_t) or []),
                )
                raise HTTPException(
                    status_code=500,
                    detail="Yedek dosyası doğrulanamadı; oluşturulan dosya açılamıyor. "
                    "İşlem iptal edildi — lütfen tekrar deneyin.",
                )
    except ExportError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception:
        logging.exception("data export failed")
        raise HTTPException(status_code=500, detail="Dışa aktarma başarısız")
    logging.getLogger(__name__).warning(
        "VERİ TAŞIMA: dışa aktarıldı (%d hasta, %d seans, %d bobin-koşusu, %d sensör, %d analiz).",
        len(paket["patient_db"]),
        len(paket["treatment_sessions"]),
        len(paket["session_coil_runs"]),
        len(paket["sensor_samples"]),
        len(paket["ai_analyses"]),
    )
    # ⚠️ Dışa aktarma, at-rest şifrelemesinin dışına ÇIKAN tek meşru yoldur: klinik verisinin
    # tamamı, çağıranın SEÇTİĞİ bir parolayla tek dosyaya iner. Kim, ne zaman, nereden ve kaç
    # kayıt çıkardı — bu kayıt olmadan bir veri sızıntısı geriye dönük hiç görünmez.
    from servers import audit_log as _iz

    _iz.yaz(
        request,
        "data.export",
        scope="klinik",
        item_count=len(paket["treatment_sessions"]),
        detail={
            k: len(paket.get(k) or [])
            for k in (
                "patient_db",
                "treatment_sessions",
                "session_coil_runs",
                "sensor_samples",
                "session_events",
                "ai_analyses",
            )
        },
    )
    return {
        "status": "success",
        "filename": f"pemf-vet-yedek-{datetime.now():%Y%m%d-%H%M}.pemfbak",
        "data_b64": _base64.b64encode(blob).decode("ascii"),
        # Sayımlar kullanıcıya gösterilir: "ne taşındığını" görebilmeli. Doz kaydı (bobin
        # koşuları) ayrı kalem — eskiden hiç taşınmadığı için hiç görünmüyordu da.
        "counts": {
            k: len(paket.get(k) or [])
            for k in (
                "patient_db",
                "treatment_sessions",
                "session_coil_runs",
                "sensor_samples",
                "session_events",
                "ai_analyses",
            )
        },
    }


@app.post("/api/data/import")
async def import_clinic_data(payload: DataImportPayload, request: Request):
    """Şifreli yedeği geri yükler.

    ⚠️ HEDEF BOŞ DEĞİLSE `{"confirm":"REPLACE_ALL"}` ZORUNLU ve mevcut TIBBİ KAYITLARIN TAMAMI
    SİLİNİR. Sessiz birleştirme YAPMIYORUZ: seans ve analiz append-only günlüklerdir, aynı dosyayı
    iki kez almak kayıtları ÇOĞALTIR ve klinik geçmişini sessizce bozar.

    ⚠️ 2026-08-09: silme kapsamı GENİŞLEDİ. Paket artık bağlı tabloların tamamını taşıdığı için
    (bobin koşuları = uygulanan doz, sensör telemetrisi, seans olayları/parametreleri ve tedavi
    DB'sinin hasta satırları) `replace` bunların HEPSİNİ siler. Yalnız seans+analiz silinip
    çocuk satırlar bırakılsaydı, eski telemetri yeni seanslara bağlanır ve kayıtlar karışırdı.
    """
    import base64 as _base64

    _enforce_privileged(request)
    from utils.data_export import ExportError, decrypt_bundle

    thdb = _get_treatment_db()
    pdb = get_patient_database()
    if thdb is None or pdb is None:
        raise HTTPException(status_code=500, detail="Veritabanı hazır değil")
    try:
        blob = _base64.b64decode(payload.blob_b64 or "", validate=True)
    except Exception:
        raise HTTPException(status_code=400, detail="Dosya okunamadı (geçersiz kodlama).")
    try:
        paket = await asyncio.to_thread(decrypt_bundle, blob, payload.passphrase)
    except ExportError as e:
        raise HTTPException(status_code=400, detail=str(e))

    mevcut = await asyncio.to_thread(thdb.export_rows)
    dolu = bool(
        mevcut["treatment_sessions"] or mevcut["ai_analyses"] or (await asyncio.to_thread(pdb.get_all_patients))
    )
    if dolu and payload.confirm != "REPLACE_ALL":
        raise HTTPException(
            status_code=409,
            detail="Bu cihazda zaten kayıt var. Geri yükleme bu cihazdaki TÜM tıbbi kayıtları "
            "(seanslar, bobin koşuları, sensör verisi, AI analizleri ve hasta kayıtları) "
            "SİLER ve yedektekilerle değiştirir. Onaylamak için "
            "{\"confirm\":\"REPLACE_ALL\"} gönderin.",
        )

    n = await asyncio.to_thread(thdb.import_rows, paket, bool(dolu))
    eklenen_hasta = 0
    # v2'de ayrı hasta veritabanı `patient_db` anahtarındadır; v1 yedeklerinde `patients` idi
    # (o sürümde tedavi DB'sinin hasta tablosu hiç taşınmıyordu, çakışma yok).
    _hastalar = paket.get("patient_db")
    if _hastalar is None and int(paket.get("bundle_version") or 1) < 2:
        _hastalar = paket.get("patients")
    # ⚠️ ÜÇ SONUÇ AYRI SAYILIR — "zaten vardı" ile "İÇE AKTARILAMADI" AYNI KOVAYA KONMAZ.
    # İlk yazımda her istisna tek bir "zaten vardı/atlandı" sayacını artırıyordu; o hâlde
    # operatör "0 hasta [+50 zaten vardı]" görüp "sorun yok" diye okuyabilirdi — oysa 50 satır da
    # GERÇEKTEN başarısız olmuş olabilirdi. Tıbbi kayıt taşımada bu kabul edilemez bir belirsizlik.
    # Ayrım hata METNİNDEN değil, ÖNCE varlık sorgusundan türetilir (metin kırılgan olurdu).
    _zaten_var, _basarisiz = 0, 0
    for h in _hastalar or []:
        _hid = h.get("id") if isinstance(h, dict) else None
        try:
            # ⚠️ DENETİM 2026-08-17 — UUID ZİNCİRİ: paketteki `id` AYNEN korunmalı. Eskiden
            # `add_patient` gelen id'yi yok sayıp yeni uuid4 üretiyordu ve `patients.db` ↔ tedavi-DB
            # (`patients.patient_uuid`) bağı HER içe aktarımda kopuyordu → 5 yıl inaktif hastada
            # tedavi geçmişindeki ad kopyası `[REDACTED]` olmuyordu (sessiz KVKK boşluğu).
            # Bkz. `patient_database.add_patient` docstring'i + tests/test_ice_aktarma_hasta_uuid_zinciri.py
            if _hid and await asyncio.to_thread(pdb.get_patient, _hid):
                # Aynı paketin ikinci kez alınması: `id` korunduğu için satır ZATEN burada.
                # Sessiz çoğaltma YOK — bu İSTENEN sonuç, hata değil.
                _zaten_var += 1
                continue
            if await asyncio.to_thread(pdb.add_patient, h, _hid):
                eklenen_hasta += 1
        except Exception as _e:
            _basarisiz += 1
            logging.getLogger(__name__).warning("Hasta İÇE AKTARILAMADI (id=%s): %s", _hid, _e)
    logging.getLogger(__name__).warning(
        "VERİ TAŞIMA: içe aktarıldı (%d hasta eklendi, %d zaten vardı, %d BAŞARISIZ, %d seans, "
        "%d bobin-koşusu, %d analiz; replace=%s).",
        eklenen_hasta,
        _zaten_var,
        _basarisiz,
        n["treatment_sessions"],
        n["session_coil_runs"],
        n["ai_analyses"],
        dolu,
    )
    # ⚠️ `replace=True` ise bu işlem cihazdaki TÜM tıbbi kayıtları SİLDİ. Denetim izi (ekleme-only)
    # silinmediği için "hangi yedek, ne zaman, kaç kaydın üzerine yazıldı" sorusu cevaplanabilir
    # kalır — aksi hâlde yanlış yedeği geri yükleyen bir işlem geriye dönük görünmez olurdu.
    from servers import audit_log as _iz

    _iz.yaz(
        request,
        "data.import",
        scope=("replace_all" if dolu else "bos_cihaz"),
        item_count=n.get("treatment_sessions", 0),
        detail={"replace": bool(dolu), "hasta": eklenen_hasta, "bundle_version": paket.get("bundle_version"), **n},
    )
    # ⚠️ ÜÇ SONUÇ YANITTA DA RAPORLANIR (yalnız logda değil). Operatör geri yüklemenin gerçekten
    # ne yaptığını görmeli: "0 hasta" tek başına "hepsi zaten vardı" mı yoksa "hepsi BAŞARISIZ" mı
    # olduğunu söylemez — tıbbi kayıt taşımada bu ayrım kritiktir. EKLEMELİ alanlar: mevcut
    # istemciler (`SettingsScreen` yalnız `patients`/`treatment_sessions`/`ai_analyses` okur)
    # etkilenmez.
    return {
        "status": "success",
        "counts": {
            "patient_db": eklenen_hasta,
            "patient_db_zaten_vardi": _zaten_var,
            "patient_db_basarisiz": _basarisiz,
            **n,
        },
    }


def _emergency_stop_all(reason: str = "manual", mode: str = "Acil Durdurma"):
    """Tüm transport'lardan (STM 1-5 + ESP 6-8) DONANIM STOP + seans kapat + WS bildir.
    Manuel acil-durdurma + ESP firmware ALARM'ı + STM bağlantı kaybı ortak bunu çağırır.
    NOT: backend bir sıcaklık/parametre EŞİĞİ dayatmaz; donanımın/operatörün kararına tepki verir."""
    import time as _t

    with _session_lock:
        coil_ids = _active_session.get("coil_ids") or list(range(1, 9))
        _was_active = bool(_active_session.get("is_active"))
        _db_sid = _active_session.get("db_session_id")
        _started_ep = _active_session.get("started_epoch")
        _active_session["is_active"] = False
    stm_stopped = False
    if state.hardware:
        try:
            stm_stopped = bool(state.hardware.stop_all_coils())
        except Exception:
            logging.exception("STM emergency stop failed")

    # P0 audit 2026-06-28: ESP stop publish'lerini PARALEL gonder (eskiden bobin basina 2 senkron
    # publish sirayla → acil-durdurma N-bobin x ~7sn gecikiyordu). _emergency_stop_all DAIMA bir
    # thread'de calisir (async endpoint asyncio.to_thread; ESP-alarm/STM-disconnect zaten thread),
    # dolayisiyla burada ThreadPoolExecutor guvenli + event-loop'u etkilemez.
    def _estop_one(coil_id):
        # [3.2]: `_{next(_estop_sira)}` eki ŞART — ms tek başına çakışabilir (üstteki blok yorumu).
        command_id = f"estop_{coil_id}_{int(_t.time() * 1000)}_{next(_estop_sira)}"
        # HG-4 (2026-08-19): onay kaydını publish'ten ÖNCE aç (hızlı ESP ack yarışı kaybolmasın).
        _register_ack(command_id)
        ok = _mqtt_publish(
            f"pemf/coil/{coil_id}/control",
            {"command": "stop", "command_id": command_id, "emergency": True, "timestamp": _t.time()},
        )
        legacy_ok = _mqtt_publish(
            f"pemf/esp32_{coil_id}/command",
            {"command": "stop", "command_id": command_id, "emergency": True, "timestamp": _t.time()},
        )
        # ⚠️ E-stop'u BLOKLAMA: publish gitti, onayı ARKA PLANDA izle. Gelmezse operatör uyarılır.
        # PUBACK bile yoksa bekleme anlamsız → pending kaydını temizle (bekçi thread açma).
        if ok or legacy_ok:
            # ⚠️ Thread start'ı try/except'te (2026-08-19 denetimi): thread tükenirse
            # (`RuntimeError: can't start new thread`) istisna _ex.map üzerinden yayılıp E-stop'un
            # POST-güvenlik işini (live_state sıfırlama, WS yayını, DB finalize) atlardı — oysa
            # fiziksel STOP publish'i ZATEN gitti (yukarıda). Ack izlemenin açılmaması yalnız onay
            # gözlemini kaçırır; E-stop'u düşürmemeli.
            try:
                threading.Thread(
                    target=_estop_ack_watch,
                    args=(int(coil_id), command_id),
                    name=f"estop-ack-{coil_id}",
                    daemon=True,
                ).start()
            except RuntimeError:
                with _pending_acks_lock:
                    _pending_acks.pop(command_id, None)
                logging.getLogger(__name__).error(
                    "E-stop bobin %s: ack-izleme thread'i açılamadı (STOP publish'i gitti, onay izlenmeyecek).",
                    coil_id,
                )
        else:
            with _pending_acks_lock:
                _pending_acks.pop(command_id, None)
        return {"coilId": coil_id, "mqtt": "success" if ok or legacy_ok else "mqtt_unavailable"}

    # DENETIM P0: kapsam `[cid for cid in coil_ids if cid in ESP_COIL_IDS]` idi → ESP STOP'lari
    # AKTIF SEANSIN bobin listesiyle sinirlaniyordu. STM tarafi ise kosulsuz stop_all_coils()
    # cagiriyor; bu asimetri hatanin kasitsiz oldugunu gosteriyor. Somut ariza: seans coil_ids=[1,2,3]
    # (yalniz STM) iken bobin 7 seans-disi surulmusse (/api/coil/7/control veya onceki seans),
    # _estop_coils BOS kaliyor → bobin 7'ye HIC stop yayinlanmiyor, ustelik asagida mqtt_results
    # bos oldugu icin _esp_ok=True → yanit "success"/confirmed=True ve canli-durum 8 bobini de
    # "durdu" gosteriyor: operatore YANLIS guvence. Acil durdurma ASLA seans kapsamiyla
    # sinirlandirilmaz → DAIMA tum ESP bobinleri. Calismayan bobine STOP zararsiz/idempotenttir.
    _estop_coils = sorted(ESP_COIL_IDS)
    # HG-5 (Plan A-2): E-stop'u BULUT broker'ına da aynala — buluta failover etmiş ESP'ye
    # yerel yayın ulaşmaz. Ayrı daemon thread: yerel yolu (aşağıda, öncelikli) BLOKLAMAZ.
    # ⚠️ try/except ŞART (review F2): thread tükenmesinde istisna buradan yükselirse aşağıdaki
    # YEREL ESP STOP havuzu + live_state sıfırlama + DB finalize ATLANIR — ayna best-effort,
    # E-stop'un esas yolunu asla düşüremez (_estop_ack_watch spawn'ındaki korumanın simetriği).
    try:
        threading.Thread(
            target=_estop_cloud_mirror,
            args=(list(_estop_coils), reason),
            name="estop-cloud-mirror",
            daemon=True,
        ).start()
    except Exception:
        logging.getLogger(__name__).error("E-stop bulut-ayna thread'i açılamadı (yerel yol sürüyor).")
    import concurrent.futures as _cf

    with _cf.ThreadPoolExecutor(max_workers=max(1, len(_estop_coils))) as _ex:
        mqtt_results = list(_ex.map(_estop_one, _estop_coils))
    with _live_state_lock:
        for idx in range(8):
            coil = _live_state["coils"][idx]
            coil["running"] = False
            coil["dutyCycle"] = 0.0
        snapshots = [dict(_live_state["coils"][i]) for i in range(8)]
    update_live_session_state(is_active=False, mode=mode)
    for coil in snapshots:
        _ws_broadcast_sync({"type": "coil_status", "coilId": coil["id"], "data": coil})
    _ws_broadcast_sync({"type": "emergency_stop", "data": {"timestamp": _t.time(), "reason": reason}})
    # DENETIM P2: acil durdurma seansi DB'de KAPATMIYOR, acik coil-run'lari ve son dakikanin
    # sensor verisini kaybediyordu → guvenlik olayinin telemetri KANITI yok oluyordu. Bobinler
    # ZATEN durduruldu (yukarida); bu blok yalnizca kaydi tamamlar, durdurmayi geciktirmez.
    # Denetim izi olarak ayrica session_events'e emergency_stop olayi yazilir.
    if _was_active and _db_sid:
        try:
            _get_treatment_db().record_session_event(
                _db_sid,
                "emergency_stop",
                payload={"reason": reason, "mode": mode, "coil_ids": list(coil_ids)},
                severity="critical",
            )
        except Exception:
            logging.getLogger(__name__).warning("estop: session_event yazilamadi", exc_info=True)
        _finalize_session_db(_db_sid, _started_ep, coil_ids=coil_ids, reason=f"acil-durdurma:{reason}")
    # Audit P2: ust-seviye status'u transport sonuclarindan TURET — eskiden kosulsuz 'success'
    # donuyordu (STM hatasi + broker cokuk olsa bile UI 'ciktilar kesildi' saniyordu). Bir transport
    # dogrulanamadiysa 'partial'/'error' don + confirmed=False (keep-alive/firmware fiziksel-telafi P2).
    # DENETIM P0 (yukaridaki kapsam fix'inin ikinci yarisi): mqtt_results BOS iken _esp_ok=True
    # varsayimi "dogrulanmadi"yi "basarili" sayiyordu. Kapsam artik daima tum ESP bobinleri
    # oldugundan liste bos olamaz; yine de bos-liste FAIL-CLOSED yorumlanir (bos = dogrulanmadi).
    _esp_ok = bool(mqtt_results) and all(r.get("mqtt") == "success" for r in mqtt_results)
    _stm_ok = stm_stopped or state.hardware is None  # STM yoksa STM-basarisizligi sayma
    _status = "success" if (_stm_ok and _esp_ok) else ("error" if (not _stm_ok and not _esp_ok) else "partial")
    return {
        "status": _status,
        "confirmed": bool(_stm_ok and _esp_ok),
        "stmStopped": stm_stopped,
        "mqttResults": mqtt_results,
        "reason": reason,
        # Denetim izi: acil-durdurma ANINDAKI seans kapsami (STOP kapsamini ARTIK belirlemez).
        "sessionCoilIds": list(coil_ids),
    }


def _emergency_stop_async(reason: str = "manual", mode: str = "Acil Durdurma"):
    """Audit P2: _emergency_stop_all'i AYRI daemon-thread'de tetikle. STM seri-okuyucu ve MQTT paho
    callback thread'leri (senkron event/mesaj dispatch) bloklanan MQTT publish'iyle ~sn'lerce
    takilmasin — stop bagimsizca yurur, cagiran guvenlik-kritik thread hemen doner (ag-I/O'da
    bloklanmaz; ayrica paho callback'i icinden publish deadlock'u onlenir)."""
    import threading as _th

    _th.Thread(
        target=_emergency_stop_all, kwargs={"reason": reason, "mode": mode}, name=f"estop-{reason}"[:24], daemon=True
    ).start()


@app.post("/api/hardware/emergency_stop")
async def emergency_stop():
    """Stop all outputs through every available transport and notify clients."""
    # P0 audit 2026-06-28: _emergency_stop_all senkron MQTT publish yapar (~7sn worst-case) →
    # event-loop'u BLOKLARDI (acil-durdurma yaniti gecikir + tum WS/istemci donardi). to_thread
    # ile thread'e al — loop responsive kalir; fonksiyon icindeki ESP publish'leri de paralel.
    result = await asyncio.to_thread(_emergency_stop_all, "manual")
    _push_notification("Acil durdurma uygulandı", "error")
    return result


# --- PATIENT DATABASE ENDPOINTS ---
# (audit B-2.2) Hasta CRUD uçları servers/patient_router.py'ye taşındı (modüler ayrım; yollar aynı).

# 2. DEMA Simülatörü host etme
sim_path = str(packaged_resource_path("dema-terapi-simülatörü", "dist"))
if os.path.exists(sim_path):
    app.mount("/simulator", StaticFiles(directory=sim_path, html=True), name="simulator")

# 1. Ana React Arayüzünü host etme (frontend/dist)
frontend_candidates = [
    packaged_resource_path("frontend", "dist"),
    packaged_resource_path("frontend_temp"),
]
frontend_path = next((str(path) for path in frontend_candidates if (path / "index.html").exists()), None)
if frontend_path:
    # DİKKAT: / endpoint'i diğer tüm API rotalarından (örn: /api) SONRA tanımlanmalıdır.
    # Bu yüzden mount işlemini en alta (API router'larından sonra) ekliyoruz.
    app.mount("/", StaticFiles(directory=frontend_path, html=True), name="frontend")
else:
    import logging

    logging.getLogger(__name__).warning("Frontend derlemesi bulunamadı! Tarayıcıda boş sayfa çıkabilir.")

# P2 audit 2026-06-28: start_fastapi_server() + __main__ KALDIRILDI — main.py silindi, HeadlessCore
# cagirmiyordu, backend_service.py kullanmiyordu (olu). Bu alt-giris uvicorn.run'i backend_service.py'nin
# guvenlik/reconcile setup'i (PEMF_REQUIRE_AUTH zorlama, stale-session reconcile, named-tunnel) OLMADAN
# yapiyordu → kaza-guvensiz. TEK gercek giris noktasi: backend_service.py.
