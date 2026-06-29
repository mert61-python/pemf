from fastapi import FastAPI, HTTPException, UploadFile, File, WebSocket, WebSocketDisconnect, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
import logging
import tempfile
import os
import shutil
import cv2
import numpy as np
import base64
import json
import threading
import time
import asyncio  # P0 audit 2026-06-28: senkron MQTT publish'i event-loop'tan cikar (to_thread)
from datetime import datetime
from servers.ai_router import ai_router
from servers.history_router import router as history_router
from servers.settings_router import router as settings_router

# Headless Core State referansı (Singleton Bridge)
# Bu obje main.py'den enjekte edilebilir veya burada global import edilebilir
try:
    from headless_core import HeadlessCore
    from controllers.hardware_controller import HardwareController
    from database.patient_database import get_patient_database
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


app = FastAPI(
    title="PEMF React Native API Bridge",
    description="PyQt6 arayüzüne gerek duymayan Headless Donanım API'si",
    version="1.0.0"
)

# CORS configurable: üretimde PEMF_CORS_ORIGINS="https://app1,https://app2" ile daraltın.
# Native uygulamada Origin yok (CORS uygulanmaz); web paneli için anlamlıdır.
_cors_env = os.getenv("PEMF_CORS_ORIGINS", "*").strip()
_cors_origins = ["*"] if _cors_env == "*" else [o.strip() for o in _cors_env.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=False,  # API stateless (cookie yok)
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """
    Expo Web üzerinde SQLite (wa-sqlite) kullanabilmek için 'SharedArrayBuffer' nesnesine ihtiyaç vardır.
    Bu nesnenin tarayıcıda tanımlı olabilmesi için COOP ve COEP header'larının 'same-origin' / 'require-corp' olarak ayarlanması ZORUNLUDUR.
    Aksi halde uygulama beyaz ekranda kalır ve 'SharedArrayBuffer is not defined' hatası fırlatır.
    """
    response = await call_next(request)
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    response.headers["Cross-Origin-Embedder-Policy"] = "require-corp"
    response.headers["Cross-Origin-Resource-Policy"] = "cross-origin"
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
        from servers.auth import require_auth, is_exempt, check_token
        required = bool(require_auth())
        exempt = is_exempt(request.url.path)
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

app.include_router(ai_router)
app.include_router(history_router)
app.include_router(settings_router)

# DEMA Simülatörü host etme
import os
from utils.path_utils import packaged_resource_path

# ═══════════════════════════════════════════════════════════════════
# WebSocket + MQTT Canlı Veri Sistemi (port 8000 üzerinden)
# Tek portlu headless backend: REST API + WebSocket canlı veri sistemi.
# ═══════════════════════════════════════════════════════════════════

# ── WebSocket bağlantı havuzu ──────────────────────────────────────
_ws_clients: list[WebSocket] = []
_ws_lock = threading.Lock()
_event_loop = None  # startup'ta set edilir


async def _ws_broadcast(message: dict) -> None:
    """Tüm bağlı WebSocket istemcilerine JSON mesajı gönderir."""
    data = json.dumps(message, ensure_ascii=False)
    dead: list[WebSocket] = []
    with _ws_lock:
        clients = list(_ws_clients)
    for ws in clients:
        try:
            await ws.send_text(data)
        except Exception:
            dead.append(ws)
    if dead:
        with _ws_lock:
            for d in dead:
                try:
                    _ws_clients.remove(d)
                except ValueError:
                    pass


def _ws_broadcast_sync(message: dict) -> None:
    """Thread-safe senkron broadcast (MQTT callback'lerinden çağrılır)."""
    global _event_loop
    import asyncio
    if not _event_loop or not _ws_clients:
        return
    data = json.dumps(message, ensure_ascii=False)
    with _ws_lock:
        clients = list(_ws_clients)

    async def _send_all():
        dead = []
        for ws in clients:
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(ws)
        if dead:
            with _ws_lock:
                for d in dead:
                    try:
                        _ws_clients.remove(d)
                    except ValueError:
                        pass

    try:
        _event_loop.call_soon_threadsafe(lambda: asyncio.ensure_future(_send_all(), loop=_event_loop))
    except Exception:
        pass


# ── Canlı Durum (Live State) ───────────────────────────────────────
_live_state = {
    "gateway": "offline",
    "mqtt": "warning",
    "stm": "warning",
    "coils": {
        i: {
            "id": i + 1, "connected": False, "running": False,
            "frequencyHz": 0, "dutyCycle": 0, "magneticMt": 0.0,
            "objectTemp": 0.0, "ambientTemp": 0.0, "currentA": 0.0,
            "stm32Driven": i < 5,
        } for i in range(8)
    },
    "activeTreatment": {
        "mode": "Sistem Hazır", "frequencyHz": 0, "intensityMt": 0.0,
        "remainingMin": 0, "elapsedSec": 0, "durationSec": 0, "isActive": False,
    },
    "notifications": [],
    "system": {
        "softwareVersion": "1.5",
        "hardwareVersion": "HW-2026.1",
        "deviceId": "PEMF-001",
        "startTime": datetime.now().isoformat(),
        "totalSessions": 0,
    },
}
_live_state_lock = threading.Lock()
_notif_counter = 0
STM_COIL_IDS = set(range(1, 6))
ESP_COIL_IDS = set(range(6, 9))


def _sync_stm_coils_locked() -> list[dict]:
    """Keep coils 1-5 derived from the live STM connection state."""
    stm_online = _live_state["stm"] == "online"
    snapshots = []
    for idx in range(5):
        coil = _live_state["coils"][idx]
        coil["stm32Driven"] = True
        coil["connected"] = stm_online
        if not stm_online:
            coil["running"] = False
        snapshots.append(dict(coil))
    return snapshots


def _push_notification(message: str, level: str = "info") -> None:
    global _notif_counter
    _notif_counter += 1
    notif = {"id": _notif_counter, "message": message, "level": level,
             "timestamp": datetime.now().isoformat()}
    with _live_state_lock:
        _live_state["notifications"].insert(0, notif)
        if len(_live_state["notifications"]) > 50:
            _live_state["notifications"].pop()
    _ws_broadcast_sync({"type": "notification", "data": notif})


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
        _push_notification("MQTT broker bağlantısı kuruldu", "success")
    else:
        with _live_state_lock:
            _live_state["mqtt"] = "error"


def _on_mqtt_disconnect_api(client, userdata, rc):
    with _live_state_lock:
        _live_state["mqtt"] = "error"
    _push_notification("MQTT bağlantısı kesildi", "warning")


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
                    _emergency_stop_all(reason=f"esp_alarm_{coil_id_str}_{atype}", mode="ESP Güvenlik Alarmı")
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


def _build_ws_snapshot() -> dict:
    """Anlık durum özeti (WebSocket'e ilk bağlanıldığında gönderilir)."""
    with _live_state_lock:
        _sync_stm_coils_locked()
        coils_list = [dict(_live_state["coils"][i]) for i in range(8)]
        return {
            "gateway": _live_state["gateway"],
            "mqtt": _live_state["mqtt"],
            "stm": _live_state["stm"],
            "activeTreatment": _live_state["activeTreatment"],
            "coils": coils_list,
            "notifications": _live_state["notifications"][:10],
            "system": _live_state["system"],
        }


def update_live_stm_status(connected: bool) -> None:
    """STM32 bağlantı durumunu günceller."""
    with _live_state_lock:
        _live_state["stm"] = "online" if connected else "warning"
        stm_state = _live_state["stm"]
        coil_snapshots = _sync_stm_coils_locked()
    _ws_broadcast_sync({"type": "stm_status", "data": {"stm": stm_state, "connected": connected}})
    for coil in coil_snapshots:
        _ws_broadcast_sync({"type": "stm_coil_update", "coilId": coil["id"], "data": coil})


def update_live_coil_from_stm(coil_id: int, duty: float, freq: float,
                               phase: float, duration_min: int, running: bool) -> None:
    """STM32 USB verisiyle bobin durumunu günceller."""
    coil_index = coil_id - 1
    if not (0 <= coil_index < 8):
        return
    with _live_state_lock:
        _live_state["stm"] = "online"
        coil = _live_state["coils"][coil_index]
        coil.update({"connected": True, "running": running, "frequencyHz": int(freq),
                     "dutyCycle": float(duty), "phase": float(phase),
                     "durationMin": int(duration_min), "stm32Driven": True})
        snapshot = dict(coil)
    _ws_broadcast_sync({"type": "stm_status", "data": {"stm": "online", "connected": True}})
    _ws_broadcast_sync({"type": "stm_coil_update", "coilId": coil_id, "data": snapshot})


def update_live_session_state(is_active: bool, mode: str = "Sistem Hazır", freq: float = 0,
                              intensity: float = 0, remaining_min: int = 0,
                              elapsed_sec: int = 0, duration_sec: int = 0) -> None:
    """React/WebSocket tarafındaki aktif tedavi özetini günceller."""
    with _live_state_lock:
        _live_state["activeTreatment"].update({
            "isActive": bool(is_active),
            "mode": mode,
            "frequencyHz": freq,
            "intensityMt": intensity,
            "remainingMin": remaining_min,
            "elapsedSec": elapsed_sec,
            "durationSec": duration_sec,
        })
        snapshot = dict(_live_state["activeTreatment"])
    _ws_broadcast_sync({"type": "session_update", "data": snapshot})


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
                _emergency_stop_all(reason="stm_disconnected", mode="STM Bağlantı Kaybı")
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
    if event.event_type in {"hardware.stm.error", "hardware.stm.nack", "hardware.stm.watchdog_timeout"}:
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

@app.on_event("startup")
async def on_startup():
    global _event_loop
    import asyncio
    _event_loop = asyncio.get_event_loop()
    logging.info("FastAPI Bridge: Başlıyor...")
    _register_event_bus_handlers()
    # MQTT Canlı Veri dinleyicisini başlat
    threading.Thread(target=_start_mqtt_for_api, daemon=True, name="FastAPIMQTTListener").start()
    # mDNS servisini başlat (aynı Wi-Fi'deki telefonlar otomatik keşfedecek)
    threading.Thread(target=_start_mdns_service, daemon=True, name="PEMFmDNSService").start()

@app.on_event("shutdown")
async def on_shutdown():
    logging.info("FastAPI Bridge: Kapanıyor...")
    global _mqtt_client_api
    if _mqtt_client_api:
        _mqtt_client_api.loop_stop()
        _mqtt_client_api.disconnect()
    # mDNS durdur
    try:
        from servers.auto_discovery import stop_mdns
        stop_mdns()
    except Exception:
        pass


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
        from servers.auth import require_auth, check_token
        required = bool(require_auth())
    except Exception:
        logging.exception("WS auth katmani yuklenemedi (FAIL-CLOSED)")
        await websocket.close(code=1011)  # internal error
        return
    if required:
        try:
            tok = websocket.query_params.get("token") or websocket.headers.get("X-API-Key") or ""
            ok = check_token(tok)
        except Exception:
            logging.exception("WS token kontrol hatasi (FAIL-CLOSED)")
            ok = False
        if not ok:
            await websocket.close(code=1008)  # policy violation
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

@app.get("/api/health")
async def health_check():
    """Sistemin ayakta olup olmadığını kontrol eder. Otomatik keşf için de kullanılır."""
    from servers.auto_discovery import _get_local_ip
    from servers.tunnel_manager import get_tunnel_url
    local_ip = _get_local_ip()
    tunnel_url = get_tunnel_url()
    try:
        from utils.path_utils import get_unique_device_id
        device_id = get_unique_device_id()
    except Exception:
        device_id = "PEMF-001"
    # Eşleştirme kodu — FE bu cihazın kodunu kullanıcıya gösterir.
    try:
        from utils.path_utils import get_pairing_code
        pairing_code = get_pairing_code()
    except Exception:
        pairing_code = None
    service_status = state.core.get_service_status() if state.core and hasattr(state.core, "get_service_status") else {}
    # At-rest şifreleme durumu (görünürlük — düz-metin fallback'i sessizce gizleme).
    at_rest_encrypted = None
    try:
        from pathlib import Path as _P
        from database.treatment_history_db import get_treatment_db
        _tdb = get_treatment_db(_app_data_dir())
        at_rest_encrypted = bool(getattr(_tdb, "at_rest_encrypted", False))
    except Exception:
        pass
    return {
        "status": "online",
        "service": "PEMF-Vet",
        "deviceId": device_id,
        "pairingCode": pairing_code,
        "localIp": local_ip,
        "tunnelUrl": tunnel_url or None,
        "core_initialized": state.core is not None,
        "stmConnected": bool(getattr(state.core, "stm_is_connected", False)) if state.core else False,
        "atRestEncrypted": at_rest_encrypted,
        "services": service_status,
    }


@app.get("/favicon.ico")
async def favicon():
    return Response(status_code=204)


@app.get("/api/discovery")
async def discovery_info():
    """Otomatik keşf endpoint'i. Telefon uygulaması bu endpoint'i sorgular."""
    from servers.auto_discovery import _get_local_ip
    from servers.tunnel_manager import get_tunnel_url
    return {
        "service": "PEMF-Vet",
        "version": "1.5",
        "localIp": _get_local_ip(),
        "port": 8000,
        "tunnelUrl": get_tunnel_url() or None,
        "capabilities": ["rest", "websocket", "mqtt", "ai", "database"],
    }


@app.get("/api/qr")
async def get_qr_code():
    """
    Aktif bağlantı adresi için QR kod PNG görüntüsü döndürür.
    Tünel URL'si varsa onu, yoksa yerel IP'yi kullanır.
    Mobil uygulama bu endpoint'i göstererek kullanıcıya kolayca tarama imkânı sunar.
    """
    from fastapi.responses import Response
    from servers.auto_discovery import generate_qr_image_bytes, _get_local_ip
    from servers.tunnel_manager import get_tunnel_url

    tunnel_url = get_tunnel_url()
    local_ip = _get_local_ip()
    # QR kod içeriği: Tünel URL varsa onu kullan, yoksa yerel IP
    target = tunnel_url if tunnel_url else f"http://{local_ip}:8000"
    png = generate_qr_image_bytes(target)
    if png:
        return Response(content=png, media_type="image/png")
    return {"error": "QR kod üretilemedi"}


class CommandPayload(BaseModel):
    command: str
    params: dict = {}

class PatientInput(BaseModel):
    id: str = ""
    name: str = ""
    species: str = ""
    breed: str = ""
    age: str = ""
    weight: str = ""
    owner: str = ""
    vet_contact: str = ""
    owner_email: str = ""  # hasta sahibinin e-postasi (rapor gonderimi icin)

class AutoPresetPayload(BaseModel):
    target_condition: str

class SessionStartPayload(BaseModel):
    patient_id: str = ""
    patient_name: str = ""
    operator_name: str = ""  # denetim izi — seansı başlatan operatör (audit P1)
    mode: str = "Manuel"  # Manuel | Otomatik | AI
    target_condition: str = ""
    frequency: float = 50.0
    duty: float = 25.0
    intensity: float = 25.0
    phase: float = 0.0
    duration_minutes: int = 20
    coil_ids: list = []  # empty = all coils

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
from datetime import datetime as _dt
import threading as _threading

_session_lock = _threading.Lock()
_active_session: dict = {}  # empty when no session running
# Sensör örnekleri aktif seans boyunca burada toplanır; /api/session/notes ve /api/session/stop ile
# gerçek session_id'ye (db_session_id) flush edilir.
_sensor_sample_buffer: list = []
_sensor_sample_buffer_lock = _threading.Lock()

# ── Asama-2: per-bobin run logging + dakika-ortalama aggregator state ──────────
# Aktif (acik) bobin calismalari: coil_id(int) -> run_id(int). _begin/_finish_coil_run yonetir.
_active_coil_runs: dict = {}
_active_coil_runs_lock = _threading.Lock()
# Per-RUN sensor istatistik akumulatoru (run summary icin): run_id -> {n,t_min,t_max,t_sum,i_sum,b_sum}
_coil_run_stats: dict = {}
_coil_run_stats_lock = _threading.Lock()
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


def _coil_hw_type(coil_id):
    """coil_id<=5 -> 'stm', >=6 -> 'esp' (STM_COIL_IDS/ESP_COIL_IDS uyumlu)."""
    return "stm" if int(coil_id) in STM_COIL_IDS else "esp"


def _begin_coil_run(coil_id, freq, duty, phase, intensity, hw_type):
    """Aktif seans (db_session_id) varsa bir bobin calismasini DB'de baslat ve run-map'e koy.
    Ayni coil zaten acik run'daysa once eskisini _finish_coil_run ile kapatir. Hepsi best-effort."""
    try:
        coil_id = int(coil_id)
    except Exception:
        return
    try:
        with _session_lock:
            sid = _active_session.get("db_session_id")
        if not sid:
            return
        # Ayni coil zaten acik run'daysa once kapat (cift-acik kalmasin).
        with _active_coil_runs_lock:
            already_open = coil_id in _active_coil_runs
        if already_open:
            _finish_coil_run(coil_id)
        db = _get_treatment_db()
        if db is None:
            return
        run_id = db.start_coil_run(
            sid, coil_id,
            frequency_hz=freq, duty_percent=duty, phase=phase,
            intensity_mt=intensity, hw_type=hw_type, started_epoch=time.time(),
        )
        if run_id is not None:
            with _active_coil_runs_lock:
                _active_coil_runs[coil_id] = run_id
            with _coil_run_stats_lock:
                _coil_run_stats[run_id] = {"n": 0, "t_min": None, "t_max": None,
                                           "t_sum": 0.0, "i_sum": 0.0, "b_sum": 0.0}
    except Exception:
        logging.getLogger(__name__).debug("_begin_coil_run hatasi (coil=%s)", coil_id, exc_info=True)


def _finish_coil_run(coil_id):
    """Acik bobin calismasini kapat: end_coil_run + run-ozetini (add_sensor_run_summary) yaz.
    Run-map ve istatistik akumulatorundan siler. Best-effort (hata seansi durdurmaz)."""
    try:
        coil_id = int(coil_id)
    except Exception:
        return
    try:
        with _active_coil_runs_lock:
            run_id = _active_coil_runs.pop(coil_id, None)
        if run_id is None:
            return
        db = _get_treatment_db()
        if db is not None:
            try:
                db.end_coil_run(run_id, time.time())
            except Exception:
                logging.getLogger(__name__).debug("end_coil_run hatasi", exc_info=True)
        with _coil_run_stats_lock:
            st = _coil_run_stats.pop(run_id, None)
        if db is not None and st and st.get("n", 0) > 0:
            n = st["n"]
            try:
                db.add_sensor_run_summary(
                    run_id,
                    sample_count=n,
                    temp_min=st.get("t_min"),
                    temp_max=st.get("t_max"),
                    temp_avg=(st["t_sum"] / n),
                    current_avg=(st["i_sum"] / n),
                    field_avg=(st["b_sum"] / n),
                )
            except Exception:
                logging.getLogger(__name__).debug("add_sensor_run_summary hatasi", exc_info=True)
    except Exception:
        logging.getLogger(__name__).debug("_finish_coil_run hatasi (coil=%s)", coil_id, exc_info=True)

@app.post("/api/hardware/auto_preset")
async def auto_preset(payload: AutoPresetPayload):
    """
    Yapay Zeka skoruna göre (veya literatür hedefine göre)
    donanım parametrelerini otomatik ayarlar.
    """
    if not state.core:
        raise HTTPException(status_code=503, detail="Çekirdek hazır değil.")

    try:
        from ai.hybrid_recommender import get_literature_recommendation
        from pathlib import Path
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/hardware/selftest")
async def trigger_hardware_selftest():
    """Tüm bobinlere SELFTEST komutu gönderir."""
    import time
    if not state.hardware:
        raise HTTPException(status_code=503, detail="Donanım hazır değil.")
    for i in range(1, 9):
        command_id = f"selftest_{i}_{int(time.time()*1000)}"
        _mqtt_publish(f"pemf/esp32_{i}/command", {
            "command": "SELFTEST",
            "command_id": command_id,
            "timestamp": time.time()
        })
    return {"status": "success", "message": "Self-test commands sent."}

@app.post("/api/hardware/reset_pwm")
async def reset_all_pwms():
    """Tüm bobinleri durdurur ve duty 0 olarak reset atar."""
    if not state.hardware:
        raise HTTPException(status_code=503, detail="Donanım hazır değil.")
    state.hardware.stop_all_coils()
    import time
    for i in range(1, 9):
        command_id = f"reset_{i}_{int(time.time()*1000)}"
        _mqtt_publish(f"pemf/esp32_{i}/command", {
            "command": "start",
            "command_id": command_id,
            "freq": 10.0,
            "duty": 0.0,
            "phase": 0.0,
            "duration": 0
        })
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
    for coil_id in payload.coil_ids:
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
    global _active_session
    coil_ids = payload.coil_ids or list(range(1, 9))
    stm_coils = [coil_id for coil_id in coil_ids if coil_id in STM_COIL_IDS]
    esp_coils = [coil_id for coil_id in coil_ids if coil_id in ESP_COIL_IDS]
    if stm_coils and not state.hardware:
        raise HTTPException(status_code=503, detail="STM32 donanım kontrolcüsü hazır değil.")

    with _session_lock:
        if _active_session.get("is_active"):
            raise HTTPException(status_code=409, detail="Zaten aktif bir seans var.")

        _active_session = {
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
            "started_epoch": time.time(),
            "coil_ids": coil_ids,
            "db_session_id": None,   # Asama-2: seans BASINDA olusan gercek int DB session_id
            "db_patient_id": None,
        }

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

    # Best-effort: DB hatasi seansi/donanimi DURDURMASIN → db_session_id=None kalir (eski davranis).
    try:
        db = _get_treatment_db()
        if db is not None:
            patient_id = None
            if payload.patient_name:
                try:
                    patient_id = db.upsert_patient({
                        "name": payload.patient_name,
                        "patient_uuid": (payload.patient_id or None),
                        "owner_email": (owner_email or None),
                    })
                except Exception:
                    logging.getLogger(__name__).debug("upsert_patient hatasi", exc_info=True)
            sid = db.start_session(
                treatment_mode=payload.mode,
                target_condition=payload.target_condition or None,
                operator_name=payload.operator_name or None,
                patient_name=payload.patient_name or None,
            )
            with _session_lock:
                # Yalniz hala bu seans aktifse yaz (arada /stop gelmis olabilir).
                if _active_session.get("is_active"):
                    _active_session["db_session_id"] = sid
                    _active_session["db_patient_id"] = patient_id
            # Yeni kolonlar (start_session bunlari yazmaz): gercek baslangic epoch + patient_id FK.
            try:
                db.set_session_meta(sid, started_epoch=_active_session.get("started_epoch"), patient_id=patient_id)
            except Exception:
                logging.getLogger(__name__).debug("set_session_meta(start) hatasi", exc_info=True)
            # Sahip e-postasini seans-parametresi olarak yaz (history JOIN'i bunu okur).
            if owner_email:
                try:
                    db.set_session_parameter(sid, "patient_owner_email", owner_email, "")
                except Exception:
                    logging.getLogger(__name__).debug("set_session_parameter(owner_email) hatasi", exc_info=True)
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

    for coil_id in stm_coils:
        state.hardware.update_coil(
            coil_id, payload.frequency, payload.duty, payload.phase, payload.duration_minutes, start=True
        )
        _begin_coil_run(coil_id, payload.frequency, payload.duty, payload.phase, payload.intensity, "stm")

    update_live_session_state(
        is_active=True,
        mode=payload.mode,
        freq=payload.frequency,
        intensity=payload.intensity,
        remaining_min=payload.duration_minutes,
        duration_sec=payload.duration_minutes * 60,
    )

    # ESP fail-safe (audit #4): broker erişilemezse ESP bobinleri (6-8) sessizce başlamaz →
    # operatöre WARN dön. Eskiden seans her hâlükârda 'success' dönüp ESP'ler ölü kalıyordu
    # ve kimse fark etmiyordu (STM bobinleri çalışsa da ESP yolu sessizce başarısızdı).
    resp = {"status": "success", "session": _active_session}
    if esp_coils and not _broker_reachable():
        msg = f"MQTT broker erişilemez — ESP bobinleri {esp_coils} aktif OLMAYABİLİR (STM bobinleri çalışıyor)."
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
    global _active_session
    import time as _t
    with _session_lock:
        prev = dict(_active_session)
        cont = bool(prev.get("is_active")) and str(prev.get("mode", "")).startswith("AI")
        _active_session = {
            "is_active": True,
            "session_id": prev.get("session_id") if cont else f"ai_{int(_t.time())}",
            "mode": mode,
            "frequency": freq,
            "duty": duty,
            "phase": 0.0,
            "duration_minutes": int(duration_minutes),
            "start_time": prev.get("start_time") if cont else _t.time(),
            "coil_ids": list(coil_ids),
        }
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
                if total > 0 and (_t.time() - sess.get("start_time", _t.time())) >= total:
                    _stop_session_coils(sess.get("coil_ids", list(range(1, 9))))
                    with _session_lock:
                        if _active_session.get("session_id") == sess.get("session_id"):
                            _active_session["is_active"] = False
                    try:
                        update_live_session_state(is_active=False, mode="Sistem Hazır")
                        _ws_broadcast_sync({"type": "session_completed", "data": {"session_id": sess.get("session_id")}})
                    except Exception:
                        pass
                    logging.info("Süre doldu → seans otomatik durduruldu (watchdog): %s", sess.get("session_id"))
        except Exception:
            logging.exception("session_duration_watchdog hata")
        _t.sleep(1)


_threading.Thread(target=_session_duration_watchdog, daemon=True, name="session-watchdog").start()


def _hardware_simulation_loop():
    """PEMF_SIMULATE=1: gerçek donanım yokken sanal STM+ESP bobin + sensör verisi üretip
    WS ile yayınlar (Dashboard/Sensör/Kontrol/KPI testleri için). Seans aktifken bobinler
    seansın freq/duty'siyle 'çalışıyor' görünür; aksi halde boşta + ortam sıcaklığı."""
    import time as _t, math, random
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
        amb_avg = (acc["amb_sum"] / n) if n else None
        rows.append({
            "coil_id": str(coil_id),
            "sample_ts": now,
            "temperature_c": acc["t_sum"] / n,
            "ambient_temp_c": amb_avg,
            "current_a": acc["i_sum"] / n,
            "magnetic_field_mt": acc["b_sum"] / n,
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
                        temp = coil.get("objectTemp")
                        cur = coil.get("currentA")
                        fld = coil.get("magneticMt")
                        amb = coil.get("ambientTemp")
                        acc = _minute_acc.get(cid)
                        if acc is None:
                            acc = {"t_sum": 0.0, "t_min": None, "t_max": None,
                                   "i_sum": 0.0, "b_sum": 0.0, "amb_sum": 0.0, "n": 0,
                                   "freq": coil.get("frequencyHz"), "duty": coil.get("dutyCycle"),
                                   "phase": coil.get("phase")}
                            _minute_acc[cid] = acc
                        if temp is not None:
                            tv = float(temp)
                            acc["t_sum"] += tv
                            acc["t_min"] = tv if acc["t_min"] is None else min(acc["t_min"], tv)
                            acc["t_max"] = tv if acc["t_max"] is None else max(acc["t_max"], tv)
                        if cur is not None:
                            acc["i_sum"] += float(cur)
                        if fld is not None:
                            acc["b_sum"] += float(fld)
                        if amb is not None:
                            acc["amb_sum"] += float(amb)
                        acc["n"] += 1
                        # En guncel parametreleri sakla (dakika boyunca degisebilir).
                        acc["freq"] = coil.get("frequencyHz")
                        acc["duty"] = coil.get("dutyCycle")
                        if coil.get("phase") is not None:
                            acc["phase"] = coil.get("phase")
                # Dakika siniri: ortalama satirlarini emit et (akumulatoru sifirlar).
                if (_t.time() - minute_start) >= 60.0:
                    _emit_minute_averages(_t.time())
                    minute_start = _t.time()
            else:
                minute_start = _t.time()
        except Exception:
            logging.exception("sensor persistence loop error")
        _t.sleep(2.0)


_threading.Thread(target=_sensor_persistence_loop, daemon=True, name="sensor-persist").start()


def _daily_maintenance_loop():
    """Asama-2 (4): GUNLUK arka-plan bakim — retention temizligi + .db yedek.
    - Retention: sensor_samples (PEMF_SENSOR_RETAIN_DAYS, vars. 90) + session_events (365).
      Run-ozetleri run bitiminde yazildigindan ham silinince ozet kalir.
    - Haftada bir wal_checkpoint(TRUNCATE) + VACUUM (run_maintenance helper'i + VACUUM).
    - Gunluk .db yedek: once wal_checkpoint, sonra pemf_treatment_history.db ->
      app_data/backups/pemf_treatment_history_YYYYMMDD.db (shutil.copy2). Son 14 yedek tutulur.
    Hata olursa loglanir, cokmez. Ilk calisma acilistan ~60sn sonra (acilisi yavaslatmamak icin)."""
    import time as _t
    from pathlib import Path as _Path
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
                    log.info("Retention: %s sensor_samples + %s session_events silindi.", removed_s, removed_e)
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


_threading.Thread(target=_daily_maintenance_loop, daemon=True, name="daily-maintenance").start()


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
    global _active_session
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
    _stop_session_coils(coil_ids)
    update_live_session_state(is_active=False, mode="Sistem Hazır")

    # (b) Sensor buffer'i gercek db_session_id ile FLUSH et + (c) end_session (gercek wall-clock sure).
    flushed = 0
    if db_session_id:
        try:
            with _sensor_sample_buffer_lock:
                pending = list(_sensor_sample_buffer)
                _sensor_sample_buffer.clear()
            db = _get_treatment_db()
            if db is not None:
                if pending:
                    try:
                        flushed = db.add_sensor_samples_batch(db_session_id, pending)
                        logging.info("stop: sensor flush %d satir (session_id=%s)", flushed, db_session_id)
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
            # Bu seansin DB satiri kapandi → notes endpoint cift-kayit yapmasin.
            with _session_lock:
                _active_session["db_finalized"] = True
        except Exception:
            logging.exception("stop: kalici kayit genel hatasi")

    return {"status": "success", "message": "Seans durduruldu.", "sensor_samples": flushed}


class SessionNotesPayload(BaseModel):
    notes: str = ""
    patient_name: str = ""
    mode: str = "Manuel"
    target_condition: str = ""
    frequency: float = 0.0
    intensity: float = 0.0
    duration_minutes: int = 0


@app.post("/api/session/notes")
async def save_session_notes(payload: SessionNotesPayload):
    """Seans-sonrası gözlem notu + seansı history'ye yaz (PyQt observation_notes karşılığı).

    Asama-2 (1c): seans BASINDA gercek db_session_id olustuysa ARTIK YENI satir ACMAZ →
    o satiri GUNCELLER (notlar + parametreler). Sensor buffer zaten /api/session/stop'ta
    flush edildiginden burada tekrar flush ETMEZ (cift-kayit onlenir). db_session_id yoksa
    eski start_session+end_session fallback'i korunur (geriye uyumlu)."""
    try:
        from database.treatment_history_db import get_treatment_db

        app_data = _app_data_dir()
        db = get_treatment_db(app_data)

        # Aktif seansin DB durumunu al (varsa).
        with _session_lock:
            existing_sid = _active_session.get("db_session_id")

        if existing_sid:
            # Var olan seans satirini GUNCELLE (yeni satir acma → cift-kayit yok).
            db.end_session(
                existing_sid,
                parameters={"frequency_hz": payload.frequency, "intensity_mt": payload.intensity},
                patient_notes=payload.notes or None,
                duration_minutes=(int(payload.duration_minutes) if payload.duration_minutes else None),
            )
            # Buffer zaten /stop'ta flush edildi; tekrar flush etme (idempotent).
            return {"status": "success", "session_id": existing_sid, "sensor_samples": 0, "updated": True}

        # Eski yol (db_session_id yok): tek-seferlik start+end fallback'i.
        sid = db.start_session(
            treatment_mode=payload.mode,
            target_condition=payload.target_condition or None,
            patient_name=payload.patient_name or None,
        )
        db.end_session(
            sid,
            parameters={"frequency_hz": payload.frequency, "intensity_mt": payload.intensity},
            patient_notes=payload.notes or None,
            duration_minutes=int(payload.duration_minutes),
        )
        # Seans boyunca toplanan sensör örneklerini gerçek session_id ile kalıcı kaydet.
        pending_count = 0
        try:
            with _sensor_sample_buffer_lock:
                pending = list(_sensor_sample_buffer)
                _sensor_sample_buffer.clear()
            if pending:
                pending_count = db.add_sensor_samples_batch(sid, pending)
                logging.info("Sensör örnekleri kaydedildi: %d satır (session_id=%s)", pending_count, sid)
        except Exception:
            logging.exception("Sensör örnekleri kaydedilemedi")
        return {"status": "success", "session_id": sid, "sensor_samples": pending_count}
    except Exception as e:
        logging.exception("save_session_notes failed")
        raise HTTPException(status_code=500, detail=str(e))


class AiLogPayload(BaseModel):
    patient_name: str = ""
    module: str = ""
    summary: str = ""


@app.post("/api/ai/log")
async def log_ai_result(payload: AiLogPayload):
    """AI teşhis sonucunu kalıcı denetim (audit) loguna ekler (hasta + modül + özet)."""
    try:
        from pathlib import Path

        app_data = _app_data_dir()
        app_data.mkdir(parents=True, exist_ok=True)
        rec = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "patient_name": payload.patient_name,
            "module": payload.module,
            "summary": payload.summary,
        }
        with open(app_data / "ai_diagnoses.jsonl", "a", encoding="utf-8") as f:
            f.write(_json.dumps(rec, ensure_ascii=False) + "\n")
        return {"status": "success"}
    except Exception as e:
        logging.exception("log_ai_result failed")
        return {"status": "error", "detail": str(e)}


@app.get("/api/ai/log")
async def get_ai_log(limit: int = 50):
    """Son AI teşhislerini döndürür (gelecekte bir geçmiş ekranı için)."""
    try:
        from pathlib import Path

        p = _app_data_dir() / "ai_diagnoses.jsonl"
        if not p.exists():
            return {"status": "success", "data": []}
        lines = p.read_text(encoding="utf-8").splitlines()[-int(limit):]
        data = []
        for ln in lines:
            try:
                data.append(_json.loads(ln))
            except Exception:
                pass
        return {"status": "success", "data": list(reversed(data))}
    except Exception as e:
        return {"status": "error", "detail": str(e), "data": []}


def _emergency_stop_all(reason: str = "manual", mode: str = "Acil Durdurma"):
    """Tüm transport'lardan (STM 1-5 + ESP 6-8) DONANIM STOP + seans kapat + WS bildir.
    Manuel acil-durdurma + ESP firmware ALARM'ı + STM bağlantı kaybı ortak bunu çağırır.
    NOT: backend bir sıcaklık/parametre EŞİĞİ dayatmaz; donanımın/operatörün kararına tepki verir."""
    import time as _t
    global _active_session
    with _session_lock:
        coil_ids = _active_session.get("coil_ids") or list(range(1, 9))
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
    _estop_coils = [cid for cid in coil_ids if cid in ESP_COIL_IDS]
    if _estop_coils:
        import concurrent.futures as _cf
        with _cf.ThreadPoolExecutor(max_workers=len(_estop_coils)) as _ex:
            mqtt_results = list(_ex.map(_estop_one, _estop_coils))
    else:
        mqtt_results = []
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
    return {"status": "success", "stmStopped": stm_stopped, "mqttResults": mqtt_results, "reason": reason}


@app.post("/api/hardware/emergency_stop")
async def emergency_stop():
    """Stop all outputs through every available transport and notify clients."""
    # P0 audit 2026-06-28: _emergency_stop_all senkron MQTT publish yapar (~7sn worst-case) →
    # event-loop'u BLOKLARDI (acil-durdurma yaniti gecikir + tum WS/istemci donardi). to_thread
    # ile thread'e al — loop responsive kalir; fonksiyon icindeki ESP publish'leri de paralel.
    result = await asyncio.to_thread(_emergency_stop_all, "manual")
    _push_notification("Acil durdurma uygulandı", "error")
    return result


@app.get("/api/session/active")
async def get_active_session():
    """Return current active session state."""
    import time
    with _session_lock:
        sess = dict(_active_session)
    if sess.get("is_active"):
        elapsed = int(time.time() - sess.get("start_time", time.time()))
        total = sess.get("duration_minutes", 0) * 60
        remaining = max(0, total - elapsed)
        sess["elapsed_sec"] = elapsed
        sess["remaining_sec"] = remaining
        sess["remaining_min"] = remaining // 60
        # Süre dolduysa yalnız YANITTA göster — GLOBAL _active_session'ı MUTATE ETME. GET salt-okunur
        # olmalı; aksi halde watchdog STOP'unu bastırıp bobinler fiziksel açık kalabilir (gerçek
        # durdurma _session_duration_watchdog'un işi).
        if remaining == 0 and total > 0:
            sess["is_active"] = False
    return sess


# ── System info & gateway status ──────────────────────────────────────────────
@app.get("/api/system/info")
async def system_info():
    """Return software/hardware version, device ID, uptime."""
    from datetime import datetime
    try:
        from utils.path_utils import get_unique_device_id
        device_id = get_unique_device_id()
    except Exception:
        device_id = "PEMF-001"
    # Eşleştirme kodu — FE bu cihazın kodunu kullanıcıya gösterir.
    try:
        from utils.path_utils import get_pairing_code
        pairing_code = get_pairing_code()
    except Exception:
        pairing_code = None
    try:
        from servers.tunnel_manager import get_tunnel_url
        tunnel_url = get_tunnel_url() or None
    except Exception:
        tunnel_url = None
    return {
        "softwareVersion": "1",
        "hardwareVersion": "HW-2025.1",
        "deviceId": device_id,
        "pairingCode": pairing_code,
        "tunnelUrl": tunnel_url,
        "stmConnected": state.core.stm_is_connected if state.core else False,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    }

@app.get("/api/kpi/summary")
async def get_kpi_summary():
    """KPI Özeti — DB'den seans istatistikleri."""
    import sqlite3
    import os
    from pathlib import Path
    
    app_data = _app_data_dir()
    db_path = app_data / "pemf_treatment_history.db"
    result = {
        "totalSessions": 0,
        "completedSessions": 0,
        "stoppedSessions": 0,
        "avgDurationMin": 0.0,
        "coilUsage": {str(i): 0 for i in range(1, 9)},
        "modeDistribution": {},
        "last7Days": [],
    }
    if not db_path.exists():
        return result
    try:
        with sqlite3.connect(str(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT session_date, treatment_mode, duration_minutes, session_status
                FROM treatment_sessions
                ORDER BY session_date DESC
                LIMIT 200
                """
            ).fetchall()

        if not rows:
            return result

        total = len(rows)
        completed = sum(1 for r in rows if (r["session_status"] or "").lower() == "completed")
        stopped = sum(
            1 for r in rows
            if (r["session_status"] or "").lower() in ("stopped", "error", "interrupted")
            or "abort" in (r["session_status"] or "").lower()
        )
        durations = [int(r["duration_minutes"] or 0) for r in rows if r["duration_minutes"]]
        avg_dur = round(sum(durations) / len(durations), 1) if durations else 0.0

        # Mod dağılımı
        modes = {}
        for r in rows:
            m = str(r["treatment_mode"] or "Manuel")
            modes[m] = modes.get(m, 0) + 1

        # Son 7 gün günlük seans sayısı
        from collections import defaultdict
        daily = defaultdict(int)
        for r in rows:
            dt = str(r["session_date"] or "")[:10]
            if dt:
                daily[dt] += 1
        sorted_days = sorted(daily.items(), reverse=True)[:7]
        last7 = [{"date": d, "count": c} for d, c in sorted_days]

        result.update({
            "totalSessions": total,
            "completedSessions": completed,
            "stoppedSessions": stopped,
            "avgDurationMin": avg_dur,
            "modeDistribution": modes,
            "last7Days": last7,
        })
    except Exception:
        pass
    return result


@app.get("/api/gateway/status")
async def gateway_status():
    """Return Mosquitto/Network/Bridge status."""
    with _live_state_lock:
        mqtt_state = _live_state.get("mqtt", "warning")
        gateway_state = _live_state.get("gateway", "offline")
        stm_state = _live_state.get("stm", "warning")
    service_status = state.core.get_service_status() if state.core and hasattr(state.core, "get_service_status") else {}
    mosquitto_status = service_status.get("mosquitto", {})
    network_status = service_status.get("network", {})
    return {
        "mqttConnected": mqtt_state == "online" or bool(mosquitto_status.get("port_open")),
        "brokerRunning": bool(mosquitto_status.get("running") or mosquitto_status.get("port_open")),
        "bridgeConnected": gateway_state == "online",
        "gatewayState": gateway_state,
        "stmConnected": stm_state == "online",
        "networkOnline": bool(network_status.get("internet_connected")) or gateway_state == "online" or mqtt_state == "online",
        "hotspotActive": bool(network_status.get("hotspot_active")),
        "mosquitto": mosquitto_status,
        "network": network_status,
    }

@app.get("/api/dashboard-snapshot")
async def get_dashboard_snapshot():
    """Donanımdan ve broker'dan alınan gerçek zamanlı veriler (React Native için)."""
    snapshot = _build_ws_snapshot()
    
    # Eksik olan 'patient' ve 'sessions' alanlarını React hata vermesin diye ekliyoruz
    snapshot["patient"] = {
        "name": "Bilinmeyen",
        "species": "Belirsiz",
        "breed": "Belirsiz",
        "owner": "Bilinmeyen"
    }
    snapshot["sessions"] = []
    
    return snapshot


@app.post("/api/notifications/clear")
async def clear_notifications():
    """Clear in-memory notifications shown in React clients."""
    with _live_state_lock:
        _live_state["notifications"].clear()
    _ws_broadcast_sync({"type": "notifications_cleared", "data": {"timestamp": time.time()}})
    return {"status": "success"}

# --- PATIENT DATABASE ENDPOINTS ---

@app.get("/api/patients")
async def get_all_patients():
    """Tüm hastaları döndürür"""
    db = get_patient_database()
    if not db:
        raise HTTPException(status_code=500, detail="Patient DB not initialized")
    return {"status": "success", "data": db.get_all_patients()}

@app.post("/api/patients")
async def add_new_patient(patient: PatientInput):
    """Yeni hasta ekler veya id verilirse mevcut hastayı günceller."""
    db = get_patient_database()
    if not db:
        raise HTTPException(status_code=500, detail="Patient DB not initialized")
    payload = patient.dict()
    patient_id = payload.pop("id", "") or ""
    if patient_id:
        success = db.update_patient(patient_id, payload)
        return {"status": "success" if success else "error", "patient_id": patient_id}
    patient_id = db.add_patient(payload)
    return {"status": "success", "patient_id": patient_id}

@app.delete("/api/patients/{patient_id}")
async def remove_patient(patient_id: str):
    """Hasta siler"""
    db = get_patient_database()
    success = db.delete_patient(patient_id)
    return {"status": "success" if success else "error"}


@app.post("/api/patients/{patient_id}/delete")
async def remove_patient_compat(patient_id: str):
    """Backward-compatible delete route used by the current Expo app."""
    return await remove_patient(patient_id)

@app.post("/api/patients/delete_all")
async def remove_all_patients():
    """Tüm hastaları siler"""
    db = get_patient_database()
    if not db:
         raise HTTPException(status_code=500, detail="Patient DB not initialized")
    
    patients = db.get_all_patients()
    for p in patients:
        db.delete_patient(p.get("id"))
    return {"status": "success"}

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

def start_fastapi_server(core_instance=None, port=8000):
    """
    Bu fonksiyon HeadlessCore içinden veya main.py'den bir Thread ile başlatılır.
    Tüm sistem tek port (8000) üzerinden çalışır: REST API + WebSocket + Simülatör.
    """
    state.core = core_instance
    if core_instance:
        state.hardware = HardwareController(core_instance)
    _register_event_bus_handlers()

    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")

if __name__ == "__main__":
    start_fastapi_server()
