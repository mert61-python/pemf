import asyncio  # P0 audit 2026-06-28: senkron MQTT publish'i event-loop'tan cikar (to_thread)
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
from utils.path_utils import get_app_version  # audit B-8.1: tek versiyon kaynağı

_APP_VERSION = get_app_version()

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
    def get_patient_database(app_data_dir=None): return None

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
    _docs_enabled = (os.getenv("PEMF_REQUIRE_AUTH", "0") != "1"
                     and os.getenv("PEMF_ENABLE_TUNNEL", "0") != "1")

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
    _cors_kwargs = {"allow_origins": ["*"]}                      # acik opt-in (geriye uyumlu)
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

# Audit P2: TrustedHostMiddleware — DNS-rebinding'e karşı Host allowlist. Kötücül bir sayfa,
# kurban tarayıcısını "clinic.local"e rebind edip LAN-muaf API'yi same-origin gibi çağırabiliyordu.
# PEMF_ALLOWED_HOSTS="clinic.local,192.168.1.50,*.trycloudflare.com" ile daraltılır; AYARSIZ = ["*"]
# (tüm host'lar = mevcut davranış, GERİYE-UYUMLU). Deployment kendi host listesini verince rebinding kapanır.
_allowed_hosts_env = os.getenv("PEMF_ALLOWED_HOSTS", "*").strip()
_allowed_hosts = ["*"] if _allowed_hosts_env == "*" else [h.strip() for h in _allowed_hosts_env.split(",") if h.strip()]
if _allowed_hosts != ["*"]:
    from starlette.middleware.trustedhost import TrustedHostMiddleware
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=_allowed_hosts)


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
    # API versiyonlama (audit B-8.1): /api/v1/* yolları /api/* handler'larına yönlendirilir → hem
    # ESKİ istemciler (/api, "v1-uyumlu") hem YENİ istemciler (/api/v1) çalışır; route çoğaltmadan.
    _p = request.scope.get("path", "")
    if _p.startswith("/api/v1/"):
        request.scope["path"] = "/api/" + _p[len("/api/v1/"):]
    # O-1: request-correlation-id — istemci X-Request-ID'sini (güvenli-karakter SÜZ → header/log-injection'a
    # karşı) kullan ya da üret; JSON-log + yanıt header'ında izlenir (7/24 saha debug).
    _rid = "".join(c for c in (request.headers.get("X-Request-ID") or "") if c.isalnum() or c in "._-")[:64] or _uuid.uuid4().hex[:12]
    from utils.request_context import request_id_var
    request_id_var.set(_rid)
    response = await call_next(request)
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    response.headers["Cross-Origin-Embedder-Policy"] = "require-corp"
    response.headers["Cross-Origin-Resource-Policy"] = "cross-origin"
    response.headers["X-API-Version"] = _APP_VERSION  # istemci/monitoring sürüm görünürlüğü
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
        return Response(status_code=503, content='{"detail":"Auth katmani kullanilamiyor"}', media_type="application/json")
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
_rl_hits: dict = {}          # client_ip -> [window_start_epoch, count]
_rl_last_purge = [0.0]


def _rl_client_ip(request: Request) -> str:
    """Gerçek istemci IP'si (per-istemci rate-limit anahtarı). GÜVENLİK (audit P3 #5): ham
    X-Forwarded-For SPOOF-EDİLEBİLİR (istemci keyfi XFF gönderip her istekte anahtar-değiştirerek
    rate-limit'i atlar) → ANAHTAR olarak KULLANMA. Yalnız Cloudflare'in DOĞRULADIĞI cf-connecting-ip
    (cloudflared client-supplied değeri ezer) veya doğrudan SOKET IP'si."""
    cf = (request.headers.get("cf-connecting-ip") or "").strip()
    if cf:
        return cf.split(",")[0].strip()
    return request.client.host if request.client else "?"


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
            # ESP geri geldiginde retained/yeniden-baglanma ile komutu alir; ulasilamiyorsa
            # zaten yapabilecegimiz bir sey yok (log'a dusulur).
            for cid, snap in changed:
                try:
                    _mqtt_publish(f"pemf/coil/{cid}/control", {
                        "command": "stop",
                        "command_id": f"stale_{cid}_{int(time.time() * 1000)}",
                        "reason": "telemetry_stale",
                    })
                except Exception:
                    logging.getLogger(__name__).warning(
                        "esp watchdog: bobin %s STOP publish edilemedi", cid, exc_info=True)
                _ws_broadcast_sync({"type": "coil_status", "coilId": cid, "data": snap})
                _push_notification(f"⚠️ Bobin {cid} telemetrisi yanıt vermiyor — bağlantı kesildi sayıldı, STOP gönderildi", "warning")
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
                _ws_broadcast_sync({"type": "sensor_data", "coilId": int(coil_id_str),
                                    "data": snapshot, "timestamp": time.time()})

            elif msg_type == "status" and not is_retained:
                with _live_state_lock:
                    coil = _live_state["coils"][coil_index]
                    status = payload.get("status", "")
                    coil["connected"] = status in ("online", "ready", "running")
                    coil["running"] = status == "running"
                    if "frequency" in payload: coil["frequencyHz"] = payload["frequency"]
                    if "duty_cycle" in payload: coil["dutyCycle"] = payload["duty_cycle"]
                    if "pwm_active" in payload: coil["running"] = bool(payload["pwm_active"])
                    if "pwm_frequency" in payload: coil["frequencyHz"] = payload["pwm_frequency"]
                    if "object_temp" in payload: coil["objectTemp"] = round(float(payload["object_temp"]), 1)
                    if "magnetic_field" in payload: coil["magneticMt"] = round(float(payload["magnetic_field"]), 2)
                    snapshot = dict(coil)
                _ws_broadcast_sync({"type": "coil_status", "coilId": int(coil_id_str), "data": snapshot})

            elif msg_type == "events":
                event_type = payload.get("type") or payload.get("event_type", "unknown")
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
                atype = payload.get("type") or payload.get("alarm") or payload.get("reason") or "alarm"
                logging.error("ESP ALARM bobin %s: %s -> tum bobinler durduruluyor", coil_id_str, atype)
                _push_notification(f"🚨 Bobin {coil_id_str} ALARM ({atype}) — tedavi güvenlik için durduruldu", "error")
                try:
                    _emergency_stop_async(reason=f"esp_alarm_{coil_id_str}_{atype}", mode="ESP Güvenlik Alarmı")
                except Exception:
                    logging.exception("ESP alarm STOP failed")

    except Exception as _e:
        # Audit #23: eskiden 'except: pass' ile sessizce yutuluyordu → bozuk/beklenmedik MQTT
        # mesajları (örn. coil status güncellenememesi) görünmezdi. Artık WARN'la (özet, traceback'siz).
        logging.getLogger(__name__).warning(
            "MQTT on_message islenemedi (topic=%s): %s", getattr(msg, "topic", "?"), _e
        )


def _start_mqtt_for_api() -> None:
    global _mqtt_client_api
    try:
        import paho.mqtt.client as _mqtt
        _mqtt_client_api = _mqtt.Client(client_id="api_server_ws_listener", clean_session=True)
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
            _push_notification("⚠️ STM32 bağlantısı koptu — tedavi güvenlik için durduruldu", "error")
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
        _push_notification("⚠️ STM32 watchdog zaman aşımı — tedavi güvenlik için durduruldu", "error")
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
        _ws_broadcast_sync({
            "type": "gateway_status",
            "data": {"gateway": gateway_state, "mqtt": mqtt_state, "network": data},
        })
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
        from servers.auto_discovery import start_mdns
        start_mdns(port=8000, device_name="PEMF-Vet")
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
    # Bağlantı açıldığında anlık durumu gönder
    await websocket.send_text(json.dumps({"type": "snapshot", "data": _build_ws_snapshot()}, ensure_ascii=False))
    try:
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
        ("pemf_active_session", "Aktif tedavi seansi (1/0)", active),
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
    return Response(content="\n".join(lines) + "\n",
                    media_type="text/plain; version=0.0.4; charset=utf-8")


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

class CoilControlPayload(BaseModel):
    freq: float = 50.0
    duty: float = 25.0
    phase: float = 0.0
    duration: int = 0  # seconds for ESP/MQTT payloads
    start: bool = True

class BatchCoilPayload(BaseModel):
    coil_ids: list[int]  # e.g. [1,2,3]
    freq: float = 50.0
    duty: float = 25.0
    phase: float = 0.0
    duration: int = 0  # seconds for ESP/MQTT payloads
    start: bool = True


def _duration_seconds_to_stm_minutes(duration_seconds: int) -> int:
    """Convert web/API ESP duration seconds to STM firmware duration minutes."""
    try:
        seconds = int(duration_seconds)
    except (TypeError, ValueError):
        return 0
    if seconds <= 0:
        return 0
    return max(1, (seconds + 59) // 60)

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
    try:
        import socket as _socket
        try:
            _probe = _socket.create_connection(("127.0.0.1", 1883), timeout=0.3)
            _probe.close()
        except OSError:
            return False  # broker erişilemez → hızlı başarısız
        import paho.mqtt.client as _mqtt
        c = _mqtt.Client(client_id="api_server_pub", clean_session=True)
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
            info.wait_for_publish(timeout=2.0)
        finally:
            c.loop_stop()
        c.disconnect()
        return True
    except Exception:
        return False


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
            "parameters": {
                "freq": freq,
                "duty": duty,
                "duration": duration,
                "source": rec.get("source", "unknown")
            }
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
    import time, threading
    if not state.hardware:
        raise HTTPException(status_code=503, detail="Donanım hazır değil.")
    # 8× _mqtt_publish (her biri connect-publish-disconnect) SANİYELER sürebilir → HTTP yanıtını
    # BEKLETME (eskiden await → istemci timeout'u "gönderilemedi" gösteriyordu, HTTP 000). Arka-plan
    # daemon thread'de best-effort gönder, yanıtı hemen dön ("komut gönderildi" semantiği).
    def _selftest_all():
        for i in range(1, 9):
            try:
                _mqtt_publish(f"pemf/esp32_{i}/command", {
                    "command": "SELFTEST",
                    "command_id": f"selftest_{i}_{int(time.time()*1000)}",
                    "timestamp": time.time()
                })
            except Exception:
                logging.getLogger(__name__).debug("selftest publish %d hatasi", i, exc_info=True)
    threading.Thread(target=_selftest_all, name="hw-selftest", daemon=True).start()
    return {"status": "success", "message": "Self-test commands sent."}

@app.post("/api/hardware/reset_pwm")
async def reset_all_pwms():
    """Tüm bobinleri durdurur ve duty 0 olarak reset atar (fire-and-forget)."""
    if not state.hardware:
        raise HTTPException(status_code=503, detail="Donanım hazır değil.")
    import time, threading
    # stop_all_coils (STM seri I/O; STM yoksa retry→saniyeler) + 8× _mqtt_publish (connect-publish) →
    # HTTP yanıtını BEKLETME (eskiden await → timeout / HTTP 000). Arka-plan thread'de yürüt, hemen dön.
    # Birincil güvenlik yolu /hardware/emergency_stop'tur; bu yalnız bakım-reset'idir.
    def _reset_all():
        try:
            state.hardware.stop_all_coils()
        except Exception:
            logging.getLogger(__name__).debug("reset_pwm stop_all_coils hatasi", exc_info=True)
        for i in range(1, 9):
            try:
                _mqtt_publish(f"pemf/esp32_{i}/command", {
                    "command": "start",
                    "command_id": f"reset_{i}_{int(time.time()*1000)}",
                    "freq": 10.0, "duty": 0.0, "phase": 0.0, "duration": 0
                })
            except Exception:
                logging.getLogger(__name__).debug("reset_pwm publish %d hatasi", i, exc_info=True)
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
        state.hardware.update_coil(
            coil_id, payload.freq, payload.duty, payload.phase, stm_duration_min, start=payload.start
        )
        # Asama-2: per-bobin run logging (best-effort, seansi bozmaz).
        if payload.start:
            _begin_coil_run(coil_id, payload.freq, payload.duty, payload.phase, None, "stm")
        else:
            _finish_coil_run(coil_id)
        return {"status": "success", "command_id": command_id, "transport": "stm32"}

    if payload.start:
        mqtt_payload = {
            "command": "start",
            "command_id": command_id,
            "freq": payload.freq,
            "duty": payload.duty,
            "phase": payload.phase,
            "duration": payload.duration,
        }
    else:
        mqtt_payload = {"command": "stop", "command_id": command_id}

    # P0 audit 2026-06-28: senkron _mqtt_publish (~7sn worst-case) event-loop'u bloklamasin → to_thread.
    ok = await asyncio.to_thread(_mqtt_publish, f"pemf/coil/{coil_id}/control", mqtt_payload)
    # Asama-2: per-bobin run logging (ESP/MQTT dali).
    if payload.start:
        _begin_coil_run(coil_id, payload.freq, payload.duty, payload.phase, None, "esp")
    else:
        _finish_coil_run(coil_id)
    return {"status": "success" if ok else "mqtt_unavailable", "command_id": command_id, "transport": "mqtt"}


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
            state.hardware.update_coil(
                coil_id, payload.freq, payload.duty, payload.phase, stm_duration_min, start=payload.start
            )
            # Asama-2: per-bobin run logging.
            if payload.start:
                _begin_coil_run(coil_id, payload.freq, payload.duty, payload.phase, None, "stm")
            else:
                _finish_coil_run(coil_id)
            results.append({"coilId": coil_id, "status": "success", "transport": "stm32"})
            continue
        if payload.start:
            mqtt_payload = {
                "command": "start",
                "command_id": command_id,
                "freq": payload.freq,
                "duty": payload.duty,
                "phase": payload.phase,
                "duration": payload.duration,
            }
        else:
            mqtt_payload = {"command": "stop", "command_id": command_id}
        # P0 audit 2026-06-28: senkron _mqtt_publish event-loop'u bloklamasin → to_thread.
        ok = await asyncio.to_thread(_mqtt_publish, f"pemf/coil/{coil_id}/control", mqtt_payload)
        # Asama-2: per-bobin run logging (ESP/MQTT dali).
        if payload.start:
            _begin_coil_run(coil_id, payload.freq, payload.duty, payload.phase, None, "esp")
        else:
            _finish_coil_run(coil_id)
        results.append({"coilId": coil_id, "status": "success" if ok else "mqtt_unavailable", "transport": "mqtt"})
    return {"status": "success", "results": results}


# ── Session management ────────────────────────────────────────────────────────
@app.post("/api/session/start")
async def start_session(payload: SessionStartPayload):
    """Start a new treatment session."""
    import time
    # Derinlemesine savunma (Pydantic max_length=8 sinirda zaten reddeder): tekrarlari at ve
    # gecerli bobin araligina (1-8) filtrele → /api/coil/batch'teki `_seen[:8]` deseniyle ayni.
    _seen_coils = []
    for _c in (payload.coil_ids or []):
        if 1 <= _c <= 8 and _c not in _seen_coils:
            _seen_coils.append(_c)
    coil_ids = _seen_coils or list(range(1, 9))
    stm_coils = [coil_id for coil_id in coil_ids if coil_id in STM_COIL_IDS]
    esp_coils = [coil_id for coil_id in coil_ids if coil_id in ESP_COIL_IDS]
    if stm_coils and not state.hardware:
        raise HTTPException(status_code=503, detail="STM32 donanım kontrolcüsü hazır değil.")

    # Güncelleme uygulanıyorken YENİ seans başlatma: installer servisi durdurup EXE'yi
    # değiştirebilir → başlayan tedavi bobinleri kontrolcüsüz bırakabilir. (update_manager
    # TOCTOU guard'ının TERS yönü — apply, başlamış tedaviyi zaten _has_active_treatment ile
    # reddeder; bu da apply penceresinde yeni tedaviyi reddeder.)
    try:
        from servers import update_manager as _um
        if _um.is_update_in_progress():
            raise HTTPException(status_code=409, detail="Güncelleme uygulanıyor; işlem bitene kadar yeni seans başlatılamaz.")
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
        _active_session.update({
            "is_active": True,
            "session_id": f"react_{int(time.time())}",
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
            "db_session_id": None,   # Asama-2: seans BASINDA olusan gercek int DB session_id
            "db_patient_id": None,
        })

    # Denetim izi (audit P1) — seansı HEMEN kalıcılaştır: kim (operatör) + ne zaman + hangi
    # parametreler. Eskiden seans yalnız SONDA DB'ye yazılıyordu → backend seans ortasında
    # çökerse hiçbir kayıt kalmıyordu ve operatör kimliği hiç tutulmuyordu. session_events
    # append-only olduğundan bu, ana seans satırı sonradan yazılsa da bağımsız kanıt sağlar.
    try:
        # P1 audit 2026-06-28: get_treatment_db() ARGUMANSIZ cagriliyordu (imza app_data_dir
        # zorunlu) → TypeError → except yutuyordu → session_started AUDIT IZI HIC yazilmazdi.
        # _get_treatment_db() sarmalayicisi app_data_dir gecer (dosyadaki diger cagrilarla tutarli).
        _get_treatment_db().record_session_event(
            None, "session_started",
            payload={
                "ref": _active_session["session_id"],
                "operator_name": payload.operator_name,
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
                _pid = db.upsert_patient({
                    "name": payload.patient_name,
                    "patient_uuid": (payload.patient_id or None),
                    "owner_email": (owner_email or None),
                })
            except Exception:
                logging.getLogger(__name__).debug("upsert_patient hatasi", exc_info=True)
        _sid = db.start_session(
            treatment_mode=payload.mode,
            target_condition=payload.target_condition or None,
            operator_name=payload.operator_name or None,
            patient_name=payload.patient_name or None,
            operator_email=payload.operator_email or None,
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
        logging.getLogger(__name__).warning("Seans başlatma İPTAL: enerjilemeden önce durdurma algılandı (bobinler açılmadı).")
        return {"status": "cancelled", "message": "Seans başlatma sırasında durduruldu (bobinler açılmadı)."}

    # Session API accepts minutes; ESP/MQTT duration remains seconds.
    import time as _t
    mqtt_duration_seconds = payload.duration_minutes * 60
    for coil_id in esp_coils:
        mqtt_payload = {
            "command": "start",
            "command_id": f"sess_{coil_id}_{int(_t.time() * 1000)}",
            "freq": payload.frequency,
            "duty": payload.duty,
            "phase": payload.phase,
            "duration": mqtt_duration_seconds,
        }
        # ESP publish arka planda → broker yavaş/erişilemezse seans başlatmayı bekletme (snappy start).
        _threading.Thread(target=_mqtt_publish, args=(f"pemf/coil/{coil_id}/control", mqtt_payload), daemon=True).start()
        # Asama-2: seans-baslangic bobini icin per-bobin run kaydi. /session/start bobinleri
        # KENDI dongusuyle baslattigindan control_single/batch hook'u buraya ULASMAZ → burada ac.
        _begin_coil_run(coil_id, payload.frequency, payload.duty, payload.phase, payload.intensity, "esp")

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
    resp = {"status": "success", "session": _active_session}
    if esp_coils and not _broker_reachable():
        msg = f"Sistem bağlantısı yok — ESP bobinleri {esp_coils} aktif OLMAYABİLİR (STM bobinleri çalışıyor)."
        logging.getLogger(__name__).warning("Seans başladı ama %s", msg)
        resp["warning"] = msg
        resp["esp_unreachable"] = True
    return resp


def _stop_session_coils(coil_ids):
    """Verilen bobinlere donanım STOP gönderir (ESP→MQTT, STM→update_coil start=False).
    is_running=False yapar → HWKeepAlive tazelemeyi keser → bobinler fiziksel olarak durur."""
    import time as _t
    for coil_id in [cid for cid in coil_ids if cid in ESP_COIL_IDS]:
        _mqtt_publish(f"pemf/coil/{coil_id}/control", {
            "command": "stop",
            "command_id": f"stop_{coil_id}_{int(_t.time() * 1000)}",
        })
    if state.hardware:
        for coil_id in [cid for cid in coil_ids if cid in STM_COIL_IDS]:
            state.hardware.update_coil(coil_id, 0.0, 0.0, 0.0, 0, start=False)
    # Asama-2: durdurulan tum bobinlerin acik run'larini kapat (acik kalmasin).
    for coil_id in coil_ids:
        try:
            _finish_coil_run(coil_id)
        except Exception:
            logging.getLogger(__name__).debug("_stop_session_coils _finish_coil_run hatasi", exc_info=True)


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
        _active_session.update({
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
        })
        _started_epoch_ai = _active_session["started_epoch"]
    # P1 audit 2026-06-28: AKTIF MANUEL (non-AI) seans varken AI baslayinca _active_session KOSULSUZ
    # eziliyordu → manuel db_session_id/coil_ids kayboluyor, acik coil-run'lar kapanmiyor, DB satiri
    # kalici 'active' kaliyor (KPI/history sisiyor + STM keep-alive surer ama UI 'AI' gosterir).
    # Yeni AI seansini kurduktan SONRA eski manuel seansi DUZGUN kapat (orphan onle). Hizli: coil-run
    # in-memory + ~ms DB write; AI coil komutlari start_ai_session DONDUKTEN sonra → race yok.
    if not cont and prev.get("is_active"):
        try:
            for cid in (prev.get("coil_ids") or []):
                try:
                    _finish_coil_run(cid)
                except Exception:
                    pass
            prev_db_id = prev.get("db_session_id")
            if prev_db_id:
                st = prev.get("start_time")
                dur_min = max(1, round((_t.time() - st) / 60.0)) if st else None
                _get_treatment_db().end_session(prev_db_id, duration_minutes=dur_min)
            logging.getLogger(__name__).warning(
                "AI seansi (%s) aktif MANUEL seansi devraldi → eski seans (db_id=%s) duzgun kapatildi (orphan onlendi).",
                mode, prev.get("db_session_id"))
        except Exception:
            logging.getLogger(__name__).exception("AI gecisinde eski manuel seans kapatma hatasi")

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
                    if (_active_session.get("is_active")
                            and _active_session.get("session_id") == _new_session_id):
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
    for _cid in (coil_ids or []):
        try:
            _finish_coil_run(_cid)
        except Exception:
            logging.getLogger(__name__).debug("finalize: _finish_coil_run(%s) hatasi", _cid, exc_info=True)
    flushed = 0
    try:
        _emit_minute_averages()   # birikmis KISMI dakikayi da buffer'a dok (yoksa kaybolur)
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
            try:
                _now = time.time()
                dur_min = int((_now - float(started_epoch)) / 60) if started_epoch else None
                db.end_session(db_session_id, duration_minutes=dur_min)
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
                _elapsed = ((_t.monotonic() - _sm) if _sm is not None
                            else (_t.time() - sess.get("start_time", _t.time())))
                if total > 0 and _elapsed >= total:
                    # Audit P2 (TOCTOU seal): fiziksel STOP'tan HEMEN önce seansın HÂLÂ aynı olduğunu
                    # doğrula — aksi halde operatör A'yı durdurup B'yi aynı bobinlerde başlattıysa bayat
                    # snapshot B'nin TAZE bobinlerini durdurur + coil-run'larını bozar (pencere ~µs'e iner).
                    with _session_lock:
                        _still_same = (bool(_active_session.get("is_active"))
                                       and _active_session.get("session_id") == sess.get("session_id"))
                    if not _still_same:
                        continue  # seans devralındı/durduruldu → bayat watchdog turu dokunmasın
                    _stop_session_coils(sess.get("coil_ids", list(range(1, 9))))
                    with _session_lock:
                        if _active_session.get("session_id") == sess.get("session_id"):
                            _active_session["is_active"] = False
                    # DENETIM P2: seansi DB'de de KAPAT. Frontend timer bitiminde /stop
                    # cagirmadigindan NORMAL tam-sure bitisi buradan gecer; eskiden satir
                    # kalici 'active' kaliyor ve son dakikanin sensor verisi kayboluyordu.
                    _finalize_session_db(sess.get("db_session_id"), sess.get("started_epoch"),
                                         reason="sure-doldu")
                    try:
                        update_live_session_state(is_active=False, mode="Sistem Hazır")
                        _ws_broadcast_sync({"type": "session_completed", "data": {"session_id": sess.get("session_id")}})
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
                        coil["magneticMt"] = round(d / 25.0 * 2.0 + 0.25 * math.sin(el * 2 + idx) + random.uniform(-0.04, 0.04), 3)
                        coil["currentA"] = round(0.35 + d / 100.0 * 0.6 + random.uniform(-0.02, 0.02), 3)
                        coil["objectTemp"] = round(26.0 + min(el / 25.0, 14.0) + 0.4 * math.sin(el * 0.5 + idx) + random.uniform(-0.2, 0.2), 1)
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
                _ws_broadcast_sync({"type": "sensor_data", "coilId": coil["id"], "timestamp": now,
                                    "data": {"magneticMt": coil["magneticMt"], "objectTemp": coil["objectTemp"],
                                             "ambientTemp": coil["ambientTemp"], "currentA": coil["currentA"]}})
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
        _tn = acc.get("t_n", 0); _in = acc.get("i_n", 0)
        _bn = acc.get("b_n", 0); _an = acc.get("amb_n", 0)
        # Metrik o dakika HIC okunmadiysa 0.0 — ESKI davranisla birebir ayni (t_sum/n zaten
        # 0.0 verirdi); asagi-akista (grafik/rapor) yeni None/NULL riski OLUSTURMAZ.
        amb_avg = (acc["amb_sum"] / _an) if _an else 0.0
        rows.append({
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
        })
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
                del _sensor_sample_buffer[:len(_sensor_sample_buffer) - 20000]


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
                            acc = {"t_sum": 0.0, "t_min": None, "t_max": None,
                                   "i_sum": 0.0, "b_sum": 0.0, "amb_sum": 0.0, "n": 0,
                                   "t_n": 0, "i_n": 0, "b_n": 0, "amb_n": 0,
                                   "freq": coil.get("frequencyHz"), "duty": coil.get("dutyCycle"),
                                   "phase": coil.get("phase")}
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
                    removed_c = db.purge_old_coil_runs(retain_days)  # P2 audit: per-bobin run retention
                    log.info("Retention: %s sensor + %s event + %s coil_run silindi.", removed_s, removed_e, removed_c)
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
                if run_count % 7 == 0:
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
        _active_session["is_active"] = False

    # (a) Bekleyen kismi dakikayi emit et — acik run-ozetine de katki saglar (finish'ten ONCE).
    try:
        _emit_minute_averages(time.time())
    except Exception:
        logging.getLogger(__name__).debug("stop: minute emit hatasi", exc_info=True)

    # Donanim STOP (ESP→MQTT, STM→update_coil). _stop_session_coils ayrica acik coil-run'lari kapatir.
    # P-1b: senkron _mqtt_publish (~2s/ESP-bobin) event-loop'u DONDURMASIN → to_thread (emergency_stop
    # deseniyle birebir; bobinler yine durur, sadece threadpool'da). Watchdog'dan (1327) cagri sync kalir.
    await asyncio.to_thread(_stop_session_coils, coil_ids)
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
                if (not _active_session.get("is_active")
                        and _active_session.get("db_session_id") == db_session_id):
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
            logging.warning("stop: db_session_id YOK → %d sensor satiri KALICI DEGIL (kayip). Seans DB'ye baglanmamis.", _lost)

    return {"status": "success", "message": "Seans durduruldu.", "sensor_samples": flushed}


class AiLogPayload(BaseModel):
    # Geriye-uyumlu alanlar (eski istemci yalnız bunları gönderir):
    patient_name: str = ""
    module: str = ""              # modül etiketi → module_label
    summary: str = ""            # sonuç özeti → result_summary
    # 2026-07 profesyonel DETAYLI kayıt — yeni istemci ayrıca gönderir:
    mode: str = ""               # profil (pet_owner/veterinarian/researcher)
    module_id: str = ""          # AiModule id (em_fantom, kidney_ct, ...)
    input_type: str = ""         # image / clinical / audio / csv ...
    result_detail: dict = {}     # tam sonuç JSON (heterojen)
    confidence: float | None = None
    operator_email: str = ""     # klinik-içi sahiplik — analizi yapan hekim ("Benim/Tüm Klinik")


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
                    db.add_ai_analysis(module_label=r.get("module", ""),
                                       patient_name=r.get("patient_name", ""),
                                       result_summary=r.get("summary", ""),
                                       result_detail={"legacy": True, "timestamp": r.get("timestamp", "")})
                except Exception:
                    pass
            p.rename(p.with_name("ai_diagnoses.jsonl.migrated"))
    except Exception:
        logging.exception("ai jsonl migrate failed")


@app.post("/api/ai/log")
async def log_ai_result(payload: AiLogPayload):
    """AI analiz sonucunu ŞİFRELİ (SQLCipher) geçmişe profesyonel+detaylı kaydeder (ai_analyses tablosu).
    Eski düz-metin JSONL + isim-maskeleme KALDIRILDI — şifreli olduğundan hasta adı TAM (KVKK-güvenli)."""
    try:
        db = _get_treatment_db()
        if db is None:
            return {"status": "error", "detail": "Kayıt DB yok"}
        await asyncio.to_thread(_migrate_ai_jsonl_once, db)
        rid = await asyncio.to_thread(
            db.add_ai_analysis,
            payload.mode, payload.module_id, payload.module,
            str(payload.patient_name or "").strip(), payload.input_type,
            payload.summary, payload.result_detail or {}, payload.confidence,
            payload.operator_email or "",
        )
        return {"status": "success", "id": rid}
    except Exception:
        logging.exception("log_ai_result failed")
        return {"status": "error", "detail": "Kayıt başarısız"}


@app.get("/api/ai/log")
async def get_ai_log(limit: int = 50, module_id: str = "", patient_name: str = "", before_id: int = 0):
    """AI analiz geçmişini döndürür (yeni önce). Filtre: modül / hasta / keyset-pagination (before_id)."""
    try:
        db = _get_treatment_db()
        if db is None:
            return {"status": "success", "data": []}
        data = await asyncio.to_thread(
            db.get_ai_analyses, int(limit),
            module_id or None, patient_name or None, (int(before_id) or None),
        )
        return {"status": "success", "data": data}
    except Exception:
        logging.exception("get_ai_log failed")
        return {"status": "error", "detail": "Log okunamadı", "data": []}


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
        command_id = f"estop_{coil_id}_{int(_t.time() * 1000)}"
        ok = _mqtt_publish(f"pemf/coil/{coil_id}/control", {"command": "stop", "command_id": command_id, "emergency": True, "timestamp": _t.time()})
        legacy_ok = _mqtt_publish(f"pemf/esp32_{coil_id}/command", {"command": "stop", "command_id": command_id, "emergency": True, "timestamp": _t.time()})
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
                _db_sid, "emergency_stop",
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
    return {"status": _status, "confirmed": bool(_stm_ok and _esp_ok),
            "stmStopped": stm_stopped, "mqttResults": mqtt_results, "reason": reason,
            # Denetim izi: acil-durdurma ANINDAKI seans kapsami (STOP kapsamini ARTIK belirlemez).
            "sessionCoilIds": list(coil_ids)}


def _emergency_stop_async(reason: str = "manual", mode: str = "Acil Durdurma"):
    """Audit P2: _emergency_stop_all'i AYRI daemon-thread'de tetikle. STM seri-okuyucu ve MQTT paho
    callback thread'leri (senkron event/mesaj dispatch) bloklanan MQTT publish'iyle ~sn'lerce
    takilmasin — stop bagimsizca yurur, cagiran guvenlik-kritik thread hemen doner (ag-I/O'da
    bloklanmaz; ayrica paho callback'i icinden publish deadlock'u onlenir)."""
    import threading as _th
    _th.Thread(target=_emergency_stop_all, kwargs={"reason": reason, "mode": mode},
               name=f"estop-{reason}"[:24], daemon=True).start()


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
