"""HTTP + WebSocket bridge for the Expo frontend.

This server is intentionally dependency-free so it can run inside the
embedded Python build. It exposes a narrow JSON API for the new responsive
frontend while the existing PyQt/backend stack stays intact.

WebSocket support uses the built-in socket module (no third-party libs).
RFC-6455 handshake + framing implemented manually so it works in the
embedded Python environment without websockets/aiohttp.
"""

from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import os
import struct
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse
from utils.path_utils import packaged_resource_path

try:
    import paho.mqtt.client as mqtt
except ImportError:
    mqtt = None

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 5050

_server: ThreadingHTTPServer | None = None
_thread: threading.Thread | None = None
_mqtt_client = None

# ── WebSocket client registry ──────────────────────────────────────────────
_ws_clients: list[Any] = []          # list of _WSClient instances
_ws_lock = threading.Lock()


class _WSClient:
    """Represents a connected WebSocket peer."""

    def __init__(self, sock, addr):
        self.sock = sock
        self.addr = addr
        self._lock = threading.Lock()
        self.alive = True

    def send(self, data: str) -> bool:
        """Send a text frame. Returns False if the connection is dead."""
        if not self.alive:
            return False
        try:
            payload = data.encode("utf-8")
            length = len(payload)
            with self._lock:
                if length <= 125:
                    header = struct.pack("!BB", 0x81, length)
                elif length <= 65535:
                    header = struct.pack("!BBH", 0x81, 126, length)
                else:
                    header = struct.pack("!BBQ", 0x81, 127, length)
                self.sock.sendall(header + payload)
            return True
        except Exception:
            self.alive = False
            return False

    def close(self):
        self.alive = False
        try:
            self.sock.close()
        except Exception:
            pass


def _broadcast(message: dict) -> None:
    """Send a JSON message to every connected WebSocket client."""
    data = json.dumps(message, ensure_ascii=False)
    dead = []
    with _ws_lock:
        clients = list(_ws_clients)
    for client in clients:
        if not client.send(data):
            dead.append(client)
    if dead:
        with _ws_lock:
            for d in dead:
                try:
                    _ws_clients.remove(d)
                except ValueError:
                    pass


def _ws_handshake(rfile, wfile, headers: dict) -> bool:
    """Perform RFC-6455 upgrade handshake. Returns True on success."""
    key = headers.get("Sec-WebSocket-Key", "").strip()
    if not key:
        return False
    magic = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
    accept = base64.b64encode(
        hashlib.sha1((key + magic).encode()).digest()
    ).decode()
    response = (
        "HTTP/1.1 101 Switching Protocols\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Accept: {accept}\r\n"
        "Access-Control-Allow-Origin: *\r\n"
        "\r\n"
    )
    wfile.write(response.encode())
    wfile.flush()
    return True


def _ws_read_frame(sock) -> tuple[int, bytes] | None:
    """Read one WebSocket frame. Returns (opcode, payload) or None on error."""
    try:
        b1, b2 = struct.unpack("!BB", _recv_exact(sock, 2))
        opcode = b1 & 0x0F
        masked = bool(b2 & 0x80)
        length = b2 & 0x7F
        if length == 126:
            length = struct.unpack("!H", _recv_exact(sock, 2))[0]
        elif length == 127:
            length = struct.unpack("!Q", _recv_exact(sock, 8))[0]
        mask_key = _recv_exact(sock, 4) if masked else b""
        payload = bytearray(_recv_exact(sock, length))
        if masked:
            for i in range(length):
                payload[i] ^= mask_key[i % 4]
        return opcode, bytes(payload)
    except Exception:
        return None


def _recv_exact(sock, n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionResetError("Connection closed")
        buf += chunk
    return buf


def _handle_ws_connection(client: _WSClient) -> None:
    """Loop reading frames from a WebSocket client (runs in its own thread)."""
    # Send initial snapshot immediately on connect
    _broadcast_snapshot_to(client)
    try:
        while client.alive:
            frame = _ws_read_frame(client.sock)
            if frame is None:
                break
            opcode, payload = frame
            if opcode == 0x8:          # close frame
                break
            if opcode == 0x9:          # ping → pong
                try:
                    client.sock.sendall(struct.pack("!BB", 0x8A, 0))
                except Exception:
                    break
            # opcode 1 = text: handle incoming commands from React
            if opcode == 0x1:
                _handle_ws_command(json.loads(payload.decode("utf-8", errors="replace")))
    except Exception:
        pass
    finally:
        client.alive = False
        with _ws_lock:
            try:
                _ws_clients.remove(client)
            except ValueError:
                pass
        client.close()


def _broadcast_snapshot_to(client: _WSClient) -> None:
    """Send the current live snapshot to a single newly-connected client."""
    msg = {
        "type": "snapshot",
        "data": _build_snapshot()
    }
    client.send(json.dumps(msg, ensure_ascii=False))


def _handle_ws_command(msg: dict) -> None:
    """Handle commands sent from React over the WebSocket (e.g. silent mode)."""
    # Currently a no-op placeholder; commands go through REST API
    pass


# ── CANLI DURUM (LIVE STATE) ────────────────────────────────────────────────
_live_state = {
    "gateway": "offline",
    "mqtt": "warning",
    "stm": "warning",
    "coils": {
        i: {
            "id": i + 1,
            "connected": False,
            "running": False,
            "frequencyHz": 0,
            "dutyCycle": 0,
            "magneticMt": 0.0,
            "objectTemp": 0.0,
            "ambientTemp": 0.0,
            "currentA": 0.0,
        }
        for i in range(8)
    },
    "activeTreatment": {
        "mode": "Sistem Hazır",
        "frequencyHz": 0,
        "intensityMt": 0.0,
        "remainingMin": 0,
        "elapsedSec": 0,
        "durationSec": 0,
        "isActive": False,
    },
    "notifications": [],     # last 50 notifications
    "system": {
        "softwareVersion": "1.4",
        "hardwareVersion": "HW-2026.1",
        "deviceId": "PEMF-001",
        "startTime": datetime.now().isoformat(),
        "totalSessions": 0,
    },
}
_live_state_lock = threading.Lock()
_notification_id_counter = 0


def _push_notification(message: str, level: str = "info") -> None:
    """Add a notification to live state and broadcast it."""
    global _notification_id_counter
    _notification_id_counter += 1
    notif = {
        "id": _notification_id_counter,
        "message": message,
        "level": level,
        "timestamp": _now_iso(),
    }
    with _live_state_lock:
        _live_state["notifications"].insert(0, notif)
        if len(_live_state["notifications"]) > 50:
            _live_state["notifications"].pop()
    _broadcast({"type": "notification", "data": notif})


# ── MQTT CALLBACKS ───────────────────────────────────────────────────────────
def _on_mqtt_connect(client, userdata, flags, rc):
    if rc == 0:
        with _live_state_lock:
            _live_state["mqtt"] = "online"
        client.subscribe("pemf/coil/+/sensors")
        client.subscribe("pemf/coil/+/status")
        client.subscribe("pemf/coil/+/events")
        client.subscribe("pemf/coil/+/alarm")
        client.subscribe("pemf/gateway/status")
        client.subscribe("pemf/bridge/status")
        client.subscribe("pemf/system/session/control")
        _push_notification("MQTT broker bağlantısı kuruldu", "success")
    else:
        with _live_state_lock:
            _live_state["mqtt"] = "error"


def _on_mqtt_disconnect(client, userdata, rc):
    with _live_state_lock:
        _live_state["mqtt"] = "error"
    _push_notification("MQTT bağlantısı kesildi", "warning")


def _on_mqtt_message(client, userdata, msg):
    try:
        topic_parts = msg.topic.split("/")
        is_retained = getattr(msg, "retain", False)

        # Bridge status
        if msg.topic == "pemf/bridge/status":
            connected = msg.payload.decode("utf-8", errors="ignore").strip() in ("1", "true", "connected")
            with _live_state_lock:
                _live_state["gateway"] = "online" if connected else "offline"
            _broadcast({"type": "gateway_status", "data": {"gateway": _live_state["gateway"]}})
            return

        # Gateway status
        if len(topic_parts) >= 3 and topic_parts[1] == "gateway":
            payload = json.loads(msg.payload.decode("utf-8"))
            with _live_state_lock:
                _live_state["gateway"] = payload.get("status", "offline")
            _broadcast({"type": "gateway_status", "data": {"gateway": _live_state["gateway"]}})
            return

        # Session control (from Android)
        if msg.topic == "pemf/system/session/control":
            # Just forward to React
            payload = json.loads(msg.payload.decode("utf-8"))
            _broadcast({"type": "session_control", "data": payload})
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

            if msg_type == "sensors":
                if is_retained:
                    return
                with _live_state_lock:
                    coil = _live_state["coils"][coil_index]
                    coil["objectTemp"] = round(float(payload.get("object_temp", 0.0)), 1)
                    coil["ambientTemp"] = round(float(payload.get("ambient_temp", 0.0)), 1)
                    coil["currentA"] = round(float(payload.get("current", 0.0)), 3)
                    coil["magneticMt"] = round(float(payload.get("magnetic_field", 0.0)), 2)
                    coil["connected"] = True
                    snapshot = dict(coil)

                _broadcast({
                    "type": "sensor_data",
                    "coilId": int(coil_id_str),
                    "data": snapshot,
                    "timestamp": time.time(),
                })

            elif msg_type == "status":
                if is_retained:
                    return
                with _live_state_lock:
                    coil = _live_state["coils"][coil_index]
                    status = payload.get("status", "")
                    coil["connected"] = status in ("online", "ready", "running")
                    coil["running"] = status == "running"
                    if "frequency" in payload:
                        coil["frequencyHz"] = payload["frequency"]
                    if "duty_cycle" in payload:
                        coil["dutyCycle"] = payload["duty_cycle"]
                    if "pwm_active" in payload:
                        coil["running"] = bool(payload["pwm_active"])
                    if "pwm_frequency" in payload:
                        coil["frequencyHz"] = payload["pwm_frequency"]
                    if "object_temp" in payload:
                        coil["objectTemp"] = round(float(payload["object_temp"]), 1)
                    if "magnetic_field" in payload:
                        coil["magneticMt"] = round(float(payload["magnetic_field"]), 2)
                    snapshot = dict(coil)

                _broadcast({
                    "type": "coil_status",
                    "coilId": int(coil_id_str),
                    "data": snapshot,
                })

            elif msg_type == "events":
                event_type = payload.get("type") or payload.get("event_type", "unknown")
                if event_type in ("wifi_disconnected", "offline"):
                    with _live_state_lock:
                        _live_state["coils"][coil_index]["connected"] = False
                        _live_state["coils"][coil_index]["running"] = False
                    _push_notification(f"⚠️ Bobin {coil_id_str} bağlantısı kesildi", "warning")
                    _broadcast({"type": "coil_status", "coilId": int(coil_id_str),
                                "data": _live_state["coils"][coil_index]})
                elif event_type == "wifi_connected":
                    with _live_state_lock:
                        _live_state["coils"][coil_index]["connected"] = True
                    _push_notification(f"✅ Bobin {coil_id_str} bağlandı", "success")
                _broadcast({"type": "esp_event", "coilId": int(coil_id_str),
                            "eventType": event_type, "data": payload})

            elif msg_type == "alarm":
                alarm_type = payload.get("alarm_type", "unknown")
                reason = payload.get("reason", "Bilinmeyen sebep")
                level = "error" if alarm_type == "safety_violation" else "warning"
                _push_notification(f"🚨 Bobin {coil_id_str} Alarm ({alarm_type}): {reason}", level)
                _broadcast({"type": "alarm", "coilId": int(coil_id_str), "data": payload})

    except Exception:
        pass


def _start_mqtt_listener() -> None:
    global _mqtt_client
    if mqtt is None or _mqtt_client is not None:
        return

    _mqtt_client = mqtt.Client(client_id="frontend_bridge_listener_v2", clean_session=True)
    _mqtt_client.on_connect = _on_mqtt_connect
    _mqtt_client.on_disconnect = _on_mqtt_disconnect
    _mqtt_client.on_message = _on_mqtt_message

    try:
        _mqtt_client.connect("127.0.0.1", 1883, 60)
        _mqtt_client.loop_start()
    except Exception:
        pass


def _stop_mqtt_listener() -> None:
    global _mqtt_client
    if _mqtt_client:
        _mqtt_client.loop_stop()
        _mqtt_client.disconnect()
        _mqtt_client = None


# ── Helper functions ────────────────────────────────────────────────────────
def _build_snapshot() -> dict[str, Any]:
    sessions = _load_recent_sessions()
    with _live_state_lock:
        coils_list = [_live_state["coils"][i] for i in range(8)]
        patient_data = {
            "name": sessions[0]["patientName"] if sessions else "Cihaz Hazır",
            "species": "",
            "breed": "",
            "owner": "PEMF Medical",
        }
        return {
            "gateway": _live_state["gateway"],
            "mqtt": _live_state["mqtt"],
            "stm": _live_state["stm"],
            "patient": patient_data,
            "activeTreatment": _live_state["activeTreatment"],
            "coils": coils_list,
            "sessions": sessions,
            "notifications": _live_state["notifications"][:10],
            "system": _live_state["system"],
        }


def update_stm_status(connected: bool) -> None:
    """Called from PyQt main window to update STM32 connection state."""
    with _live_state_lock:
        _live_state["stm"] = "online" if connected else "warning"
    _broadcast({"type": "stm_status", "data": {"stm": _live_state["stm"], "connected": connected}})
    try:
        from servers.api_server import update_live_stm_status
        update_live_stm_status(connected)
    except Exception:
        pass


def update_session_state(is_active: bool, mode: str = "", freq: float = 0,
                         intensity: float = 0, remaining_min: int = 0,
                         elapsed_sec: int = 0, duration_sec: int = 0) -> None:
    """Called from PyQt main window to sync active treatment state."""
    with _live_state_lock:
        _live_state["activeTreatment"].update({
            "isActive": is_active,
            "mode": mode,
            "frequencyHz": freq,
            "intensityMt": intensity,
            "remainingMin": remaining_min,
            "elapsedSec": elapsed_sec,
            "durationSec": duration_sec,
        })
    _broadcast({"type": "session_update", "data": _live_state["activeTreatment"]})


# ── STM32 → React Köprüsü ────────────────────────────────────────────────────
def update_coil_from_stm(coil_id: int, duty: float, freq: float,
                          phase: float, duration_min: int, running: bool) -> None:
    """
    STM32 USB CDC'den gelen STM_OK verisi ile _live_state günceller ve
    React'a 'stm_coil_update' mesajı yayınlar.

    Parametreler:
        coil_id       - 1-indexed bobin numarası (1-5)
        duty          - Görev döngüsü (0-100, tam sayı yüzde)
        freq          - Frekans (Hz, tam sayı)
        phase         - Faz açısı (°)
        duration_min  - Seans süresi (dakika, T=XX*dk cinsinden)
        running       - PWM aktif mi (duty > 0)
    """
    coil_index = coil_id - 1
    if not (0 <= coil_index < 8):
        return

    with _live_state_lock:
        coil = _live_state["coils"][coil_index]
        coil["connected"] = True          # STM'den veri geliyorsa bağlı
        coil["running"] = running
        coil["frequencyHz"] = int(freq)
        coil["dutyCycle"] = float(duty)
        coil["phase"] = float(phase)
        coil["durationMin"] = int(duration_min)
        coil["stm32Driven"] = True        # React'a STM kaynağını bildir
        snapshot = dict(coil)

    _broadcast({
        "type": "stm_coil_update",
        "coilId": coil_id,
        "data": snapshot,
    })
    try:
        from servers.api_server import update_live_coil_from_stm
        update_live_coil_from_stm(coil_id, duty, freq, phase, duration_min, running)
    except Exception:
        pass


# ── Session Tick Timer ────────────────────────────────────────────────────────
_session_timer_thread: threading.Thread | None = None
_session_timer_stop = threading.Event()


def _session_tick_loop() -> None:
    """
    Aktif seans varsa her 5 saniyede bir elapsed/remaining değerlerini
    React'a yayınlar. start_frontend_bridge() tarafından başlatılır.
    """
    import time as _t
    _session_start_ts: float | None = None
    _session_duration_sec: int = 0

    while not _session_timer_stop.is_set():
        _session_timer_stop.wait(5)
        if _session_timer_stop.is_set():
            break
        try:
            with _live_state_lock:
                at = _live_state["activeTreatment"]
                is_active = at.get("isActive", False)
                duration_sec = at.get("durationSec", 0)
                elapsed_sec = at.get("elapsedSec", 0)

            if not is_active or duration_sec <= 0:
                continue

            new_elapsed = elapsed_sec + 5
            new_remaining_sec = max(0, duration_sec - new_elapsed)
            new_remaining_min = new_remaining_sec // 60

            with _live_state_lock:
                _live_state["activeTreatment"]["elapsedSec"] = new_elapsed
                _live_state["activeTreatment"]["remainingMin"] = new_remaining_min
                tick_data = dict(_live_state["activeTreatment"])

            _broadcast({"type": "session_tick", "data": tick_data})

            # Süre doldu mu?
            if new_remaining_sec == 0:
                with _live_state_lock:
                    _live_state["activeTreatment"]["isActive"] = False
                    _live_state["activeTreatment"]["mode"] = "Seans Tamamlandı"
                _broadcast({"type": "session_update", "data": _live_state["activeTreatment"]})
        except Exception:
            pass


def get_frontend_backend_port(project_root: Path | None = None) -> int:
    """Return the configured HTTP API port for the frontend bridge."""
    env_port = os.environ.get("PEMF_BACKEND_PORT") or os.environ.get("PEMF_FRONTEND_BACKEND_PORT")
    if env_port:
        try:
            return int(env_port)
        except ValueError:
            pass

    root = project_root or Path(__file__).resolve().parents[1]
    for config_path in (root / "config" / "config.json", root / "data" / "config.json"):
        try:
            with config_path.open("r", encoding="utf-8") as file:
                data = json.load(file)
            port = data.get("http_port") or data.get("frontend_backend_port")
            if port:
                return int(port)
        except Exception:
            continue

    return DEFAULT_PORT


def start_frontend_bridge(
    host: str = DEFAULT_HOST,
    port: int | None = None,
    project_root: Path | None = None,
) -> tuple[str, int] | None:
    """Start the bridge in a daemon thread."""
    global _server, _thread

    if _server:
        return host, _server.server_port

    root = project_root or Path(__file__).resolve().parents[1]
    resolved_port = port or get_frontend_backend_port(root)

    handler = _make_handler(root)
    try:
        _server = ThreadingHTTPServer((host, resolved_port), handler)
    except OSError:
        return host, resolved_port

    _start_mqtt_listener()

    _thread = threading.Thread(
        target=_server.serve_forever,
        name="PEMFFrontendBridge",
        daemon=True,
    )
    _thread.start()

    # Session tick timer başlat
    global _session_timer_thread, _session_timer_stop
    _session_timer_stop.clear()
    _session_timer_thread = threading.Thread(
        target=_session_tick_loop,
        name="PEMFSessionTick",
        daemon=True,
    )
    _session_timer_thread.start()

    return host, resolved_port


def stop_frontend_bridge() -> None:
    """Stop the bridge if this process started it."""
    global _server, _thread, _session_timer_thread

    # Session tick timer durdur
    _session_timer_stop.set()
    if _session_timer_thread and _session_timer_thread.is_alive():
        _session_timer_thread.join(timeout=2)
    _session_timer_thread = None

    _stop_mqtt_listener()

    # Close all WebSocket clients
    with _ws_lock:
        for c in list(_ws_clients):
            c.close()
        _ws_clients.clear()

    if _server:
        _server.shutdown()
        _server.server_close()
    _server = None
    _thread = None


# ── HTTP / WebSocket request handler ────────────────────────────────────────
def _make_handler(project_root: Path):
    class FrontendBridgeHandler(BaseHTTPRequestHandler):
        server_version = "PEMFFrontendBridge/2.0"

        def do_OPTIONS(self) -> None:
            self._send_empty(204)

        def do_GET(self) -> None:
            path = urlparse(self.path).path

            # WebSocket upgrade
            upgrade = self.headers.get("Upgrade", "").lower()
            if upgrade == "websocket" and path == "/ws":
                self._handle_ws_upgrade()
                return

            if path == "/api/health":
                self._send_json({"ok": True, "service": "pemf-frontend-bridge", "timestamp": _now_iso()})
                return
            if path == "/api/dashboard-snapshot":
                self._send_json(_build_snapshot())
                return
            if path == "/api/status":
                self._send_json(_legacy_status())
                return
            if path == "/api/sensor-data":
                self._send_json(_legacy_sensor_data())
                return
            if path == "/api/treatment-history":
                self._send_json({"sessions": _build_snapshot()["sessions"]})
                return
            if path == "/api/gateway/status":
                self._send_json(_gateway_status())
                return
            if path == "/api/system/info":
                self._send_json(_system_info())
                return
            if path == "/api/notifications":
                with _live_state_lock:
                    notifs = list(_live_state["notifications"])
                self._send_json({"notifications": notifs})
                return
            if path == "/api/kpi/summary":
                self._send_json(_kpi_summary())
                return
            if not path.startswith("/api/"):
                self._send_static(path)
                return

            self._send_json({"error": "not_found", "path": path}, status=404)

        def do_POST(self) -> None:
            path = urlparse(self.path).path
            payload = self._read_json_body()

            if path == "/api/start-treatment":
                with _live_state_lock:
                    _live_state["activeTreatment"]["isActive"] = True
                    _live_state["activeTreatment"]["mode"] = payload.get("mode", "Manuel")
                _broadcast({"type": "session_update", "data": _live_state["activeTreatment"]})
                _push_notification("Tedavi başlatıldı", "success")
                self._send_json({"ok": True, "timestamp": _now_iso()})
                return

            if path == "/api/stop-treatment":
                with _live_state_lock:
                    _live_state["activeTreatment"]["isActive"] = False
                    _live_state["activeTreatment"]["mode"] = "Sistem Hazır"
                _broadcast({"type": "session_update", "data": _live_state["activeTreatment"]})
                _push_notification("Tedavi durduruldu", "warning")
                self._send_json({"ok": True, "timestamp": _now_iso()})
                return

            if path == "/api/update-parameters":
                self._send_json({"ok": True, "path": path, "payload": payload, "timestamp": _now_iso()})
                return

            if path == "/api/hardware/emergency_stop":
                # Tüm bobinleri durdur (STM32 ve MQTT/ESP)
                with _live_state_lock:
                    for i in range(8):
                        _live_state["coils"][i]["running"] = False
                    _live_state["activeTreatment"]["isActive"] = False
                    _live_state["activeTreatment"]["mode"] = "Acil Durduruldu"
                _broadcast({"type": "session_update", "data": _live_state["activeTreatment"]})
                _broadcast({"type": "emergency_stop", "data": {"timestamp": _now_iso()}})
                _push_notification("🚨 Tüm bobinler acil olarak durduruldu!", "error")
                # MQTT üzerinden ESP'lere stop komutu gönder
                if _mqtt_client:
                    for i in range(1, 9):
                        try:
                            import json as _json
                            _mqtt_client.publish(
                                f"pemf/coil/{i}/control",
                                _json.dumps({"command": "stop", "command_id": f"emergency_{i}"}),
                                qos=1
                            )
                        except Exception:
                            pass
                # GUI tarafında emergency stop signal'ini tetikle (thread-safe)
                stm_stopped = False
                try:
                    from servers import frontend_bridge as _fb
                    if hasattr(_fb, '_gui_emergency_stop_callback') and callable(_fb._gui_emergency_stop_callback):
                        import threading as _th
                        _th.Thread(target=_fb._gui_emergency_stop_callback, daemon=True).start()
                        stm_stopped = True
                except Exception:
                    pass
                # Audit #22: STM bobinleri (1-5) yalnız GUI callback varsa durur (headless'ta YOK).
                # Eskiden her hâlükârda ok:true dönüyordu → FE durduğunu sanıp operatörü yanıltıyordu.
                # stmStopped'ı DÜRÜST dön ki FE doğrulanamadığında uyarı göstersin.
                resp = {"ok": True, "stmStopped": stm_stopped, "mqttSent": bool(_mqtt_client),
                        "timestamp": _now_iso()}
                if not stm_stopped:
                    resp["warning"] = ("STM bobinleri (1-5) bu legacy köprüden durdurulamadı "
                                       "(GUI callback yok). api_server /hardware/emergency_stop kullanın.")
                self._send_json(resp)
                return

            if path == "/api/notifications/clear":
                with _live_state_lock:
                    _live_state["notifications"].clear()
                self._send_json({"ok": True})
                return

            self._send_json({"error": "not_found", "path": path}, status=404)

        def _handle_ws_upgrade(self) -> None:
            """Perform WebSocket handshake then hand off to a reader thread."""
            headers_dict = {k: v for k, v in self.headers.items()}
            try:
                self.wfile.write(b"")  # flush
                if not _ws_handshake(self.rfile, self.wfile, headers_dict):
                    self.send_error(400, "Bad WebSocket Handshake")
                    return
            except Exception:
                return

            client = _WSClient(self.connection, self.client_address)
            with _ws_lock:
                _ws_clients.append(client)

            t = threading.Thread(
                target=_handle_ws_connection,
                args=(client,),
                daemon=True,
                name=f"WSClient-{self.client_address}",
            )
            t.start()
            # Block this HTTP handler thread until the WS connection closes
            t.join()

        def log_message(self, format: str, *args: Any) -> None:
            return  # Suppress HTTP logs

        def _read_json_body(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0") or "0")
            if length <= 0:
                return {}
            try:
                return json.loads(self.rfile.read(length).decode("utf-8"))
            except Exception:
                return {}

        def _send_empty(self, status: int) -> None:
            self.send_response(status)
            self._send_common_headers()
            self.end_headers()

        def _send_json(self, payload: dict[str, Any], status: int = 200) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self._send_common_headers()
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_common_headers(self) -> None:
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Accept")
            self.send_header("Cache-Control", "no-store")

        def _send_static(self, path: str) -> None:
            app_data_path = Path(os.environ.get("APPDATA", "C:/")) / "PEMF_GUI" / "frontend_dist"
            fallback_root = packaged_resource_path("frontend", "dist")
            static_root = app_data_path if app_data_path.exists() and (app_data_path / "index.html").exists() else fallback_root
            
            if path in {"", "/"}:
                target = static_root / "index.html"
            else:
                relative = unquote(path.lstrip("/")).replace("/", os.sep)
                target = (static_root / relative).resolve()
                try:
                    target.relative_to(static_root.resolve())
                except ValueError:
                    self._send_json({"error": "forbidden"}, status=403)
                    return
                if not target.exists() or target.is_dir():
                    target = static_root / "index.html"

            if not target.exists():
                self._send_json(
                    {
                        "error": "frontend_not_built",
                        "message": "Run `cd frontend && npx expo export --platform web` first.",
                    },
                    status=404,
                )
                return

            body = target.read_bytes()
            content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
            self.send_response(200)
            self._send_common_headers()
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return FrontendBridgeHandler


# ── Data helpers ─────────────────────────────────────────────────────────────
def update_system_info(key: str, value: Any) -> None:
    """Called from PyQt main window to update dynamic system info (like deviceId, version)."""
    with _live_state_lock:
        if key in _live_state["system"]:
            _live_state["system"][key] = value

def _gateway_status() -> dict[str, Any]:
    with _live_state_lock:
        return {
            "gateway": _live_state["gateway"],
            "mqtt": _live_state["mqtt"],
            "stm": _live_state["stm"],
            "networkOnline": True,
            "hotspotActive": False,
        }


def _system_info() -> dict[str, Any]:
    with _live_state_lock:
        sys_data = dict(_live_state["system"])
    # Calculate uptime
    try:
        start = datetime.fromisoformat(sys_data["startTime"])
        uptime_sec = int((datetime.now() - start).total_seconds())
        h = uptime_sec // 3600
        m = (uptime_sec % 3600) // 60
        s = uptime_sec % 60
        sys_data["uptime"] = f"{h:02d}:{m:02d}:{s:02d}"
    except Exception:
        sys_data["uptime"] = "00:00:00"
        
    # Dynamically count total sessions from database
    try:
        app_data = Path(os.environ.get("APPDATA", "C:/")) / "PEMF_GUI"
        db_path = app_data / "pemf_treatment_history.db"
        if db_path.exists():
            import sqlite3
            with sqlite3.connect(str(db_path)) as conn:
                count = conn.execute("SELECT COUNT(*) FROM treatment_sessions").fetchone()[0]
                sys_data["totalSessions"] = count
    except Exception:
        pass
        
    return sys_data


def _load_recent_sessions() -> list[dict[str, Any]]:
    app_data = Path(os.environ.get("APPDATA", "C:/")) / "PEMF_GUI"
    db_path = app_data / "pemf_treatment_history.db"

    if not db_path.exists():
        return []

    try:
        import sqlite3

        with sqlite3.connect(str(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT session_id, session_date, patient_name, frequency_hz,
                       intensity_mt, duration_minutes
                FROM treatment_sessions
                ORDER BY session_date DESC
                LIMIT 10
                """
            ).fetchall()

        if not rows:
            return []

        return [
            {
                "id": str(row["session_id"]),
                "date": str(row["session_date"]),
                "patientName": str(row["patient_name"] or "Bilinmiyor"),
                "mode": "Canlı",
                "target": f"{row['frequency_hz'] or 0} Hz / {row['intensity_mt'] or 0} mT",
                "durationMin": int(row["duration_minutes"] or 0),
                "status": "completed",
            }
            for row in rows
        ]
    except Exception:
        return []


def _legacy_status() -> dict[str, Any]:
    with _live_state_lock:
        return {
            "system_status": _live_state["gateway"],
            "treatment_active": _live_state["activeTreatment"]["isActive"],
            "current_parameters": {
                "frequency": _live_state["activeTreatment"]["frequencyHz"],
                "intensity": _live_state["activeTreatment"]["intensityMt"],
                "duration": _live_state["activeTreatment"]["remainingMin"],
            },
        }


def _legacy_sensor_data() -> dict[str, Any]:
    with _live_state_lock:
        coil = _live_state["coils"][0]
    return {
        "object_temp": coil["objectTemp"],
        "ambient_temp": coil["ambientTemp"],
        "magnetic_field": coil["magneticMt"],
        "current": coil["currentA"],
        "esp_id": "backend-bridge",
        "esp_status": "online" if coil["connected"] else "offline",
    }


def _kpi_summary() -> dict[str, Any]:
    """KPI özeti — DB'den seans istatistikleri."""
    app_data = Path(os.environ.get("APPDATA", "C:/")) / "PEMF_GUI"
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
        import sqlite3
        with sqlite3.connect(str(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT session_id, session_date, mode, duration_minutes, status,
                       active_coils, frequency_hz, intensity_mt
                FROM treatment_sessions
                ORDER BY session_date DESC
                LIMIT 200
                """
            ).fetchall()

        if not rows:
            return result

        total = len(rows)
        completed = sum(1 for r in rows if (r["status"] or "").lower() == "completed")
        stopped = sum(1 for r in rows if (r["status"] or "").lower() in ("stopped", "error"))
        durations = [int(r["duration_minutes"] or 0) for r in rows if r["duration_minutes"]]
        avg_dur = round(sum(durations) / len(durations), 1) if durations else 0.0

        # Mod dağılımı
        modes: dict[str, int] = {}
        for r in rows:
            m = str(r["mode"] or "Manuel")
            modes[m] = modes.get(m, 0) + 1

        # Son 7 gün günlük seans sayısı
        from collections import defaultdict
        daily: dict[str, int] = defaultdict(int)
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


# ── GUI Emergency Stop Callback ───────────────────────────────────────────────
# gui_pyqt_v11.py bu değişkeni set eder, React'tan emergency_stop gelince çağrılır
_gui_emergency_stop_callback = None  # type: ignore


def register_gui_emergency_stop(callback) -> None:
    """PyQt GUI bu fonksiyonla callback'ini kaydeder."""
    global _gui_emergency_stop_callback
    _gui_emergency_stop_callback = callback


def _now_iso(timespec: str = "seconds") -> str:
    return datetime.now().isoformat(timespec=timespec)


if __name__ == "__main__":
    address = start_frontend_bridge()
    if not address:
        raise SystemExit(1)
    print(f"PEMF frontend backend running at http://{address[0]}:{address[1]}")
    print(f"WebSocket: ws://{address[0]}:{address[1]}/ws")
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        stop_frontend_bridge()
