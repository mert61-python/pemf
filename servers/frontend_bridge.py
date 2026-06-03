"""Small HTTP bridge for the Expo frontend.

This server is intentionally dependency-free so it can run inside the
embedded Python build. It exposes a narrow JSON API for the new responsive
frontend while the existing PyQt/backend stack stays intact.
"""

from __future__ import annotations

import json
import mimetypes
import os
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

try:
    import paho.mqtt.client as mqtt
except ImportError:
    mqtt = None

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 5050

_server: ThreadingHTTPServer | None = None
_thread: threading.Thread | None = None
_mqtt_client = None

# --- CANLI DURUM (LIVE STATE) BAZLI YAPI ---
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
    }
}

# --- MQTT CALLBACKLERI ---
def _on_mqtt_connect(client, userdata, flags, rc):
    if rc == 0:
        _live_state["mqtt"] = "online"
        client.subscribe("pemf/coil/+/sensors")
        client.subscribe("pemf/coil/+/status")
        client.subscribe("pemf/gateway/status")
    else:
        _live_state["mqtt"] = "error"

def _on_mqtt_disconnect(client, userdata, rc):
    _live_state["mqtt"] = "error"

def _on_mqtt_message(client, userdata, msg):
    try:
        topic_parts = msg.topic.split('/')
        payload = json.loads(msg.payload.decode('utf-8'))
        
        if len(topic_parts) >= 4 and topic_parts[1] == "coil":
            coil_id_str = topic_parts[2]
            msg_type = topic_parts[3]
            
            if coil_id_str.isdigit():
                coil_index = int(coil_id_str) - 1
                if 0 <= coil_index < 8:
                    if msg_type == "sensors":
                        _live_state["coils"][coil_index]["objectTemp"] = round(payload.get("object_temp", 0.0), 1)
                        _live_state["coils"][coil_index]["ambientTemp"] = round(payload.get("ambient_temp", 0.0), 1)
                        _live_state["coils"][coil_index]["currentA"] = round(payload.get("current", 0.0), 2)
                        _live_state["coils"][coil_index]["magneticMt"] = round(payload.get("magnetic_field", 0.0), 2)
                    elif msg_type == "status":
                        status = payload.get("status", "")
                        _live_state["coils"][coil_index]["connected"] = (status in ["online", "ready", "running"])
                        _live_state["coils"][coil_index]["running"] = (status == "running")
                        
                        # Eğer değerler varsa güncelle
                        if "frequency" in payload:
                            _live_state["coils"][coil_index]["frequencyHz"] = payload["frequency"]
                        if "duty_cycle" in payload:
                            _live_state["coils"][coil_index]["dutyCycle"] = payload["duty_cycle"]
                            
        elif topic_parts[1] == "gateway" and topic_parts[2] == "status":
            _live_state["gateway"] = payload.get("status", "offline")
            
    except Exception:
        pass

def _start_mqtt_listener():
    global _mqtt_client
    if mqtt is None or _mqtt_client is not None:
        return
        
    _mqtt_client = mqtt.Client(client_id="frontend_bridge_listener", clean_session=True)
    _mqtt_client.on_connect = _on_mqtt_connect
    _mqtt_client.on_disconnect = _on_mqtt_disconnect
    _mqtt_client.on_message = _on_mqtt_message
    
    try:
        _mqtt_client.connect("127.0.0.1", 1883, 60)
        _mqtt_client.loop_start()
    except Exception:
        pass

def _stop_mqtt_listener():
    global _mqtt_client
    if _mqtt_client:
        _mqtt_client.loop_stop()
        _mqtt_client.disconnect()
        _mqtt_client = None


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

    # Canlı veri dinleyicisini başlat
    _start_mqtt_listener()

    _thread = threading.Thread(
        target=_server.serve_forever,
        name="PEMFFrontendBridge",
        daemon=True,
    )
    _thread.start()
    return host, resolved_port


def stop_frontend_bridge() -> None:
    """Stop the bridge if this process started it."""
    global _server, _thread

    _stop_mqtt_listener()

    if _server:
        _server.shutdown()
        _server.server_close()
    _server = None
    _thread = None


def _make_handler(project_root: Path):
    class FrontendBridgeHandler(BaseHTTPRequestHandler):
        server_version = "PEMFFrontendBridge/1.0"

        def do_OPTIONS(self) -> None:
            self._send_empty(204)

        def do_GET(self) -> None:
            path = urlparse(self.path).path

            if path == "/api/health":
                self._send_json({"ok": True, "service": "pemf-frontend-bridge", "timestamp": _now_iso()})
                return
            if path == "/api/dashboard-snapshot":
                self._send_json(_dashboard_snapshot(project_root))
                return
            if path == "/api/status":
                self._send_json(_legacy_status())
                return
            if path == "/api/sensor-data":
                self._send_json(_legacy_sensor_data())
                return
            if path == "/api/treatment-history":
                self._send_json({"sessions": _dashboard_snapshot(project_root)["sessions"]})
                return
            if not path.startswith("/api/"):
                self._send_static(path)
                return

            self._send_json({"error": "not_found", "path": path}, status=404)

        def do_POST(self) -> None:
            path = urlparse(self.path).path
            payload = self._read_json_body()

            if path in {"/api/start-treatment", "/api/stop-treatment", "/api/update-parameters"}:
                self._send_json({"ok": True, "path": path, "payload": payload, "timestamp": _now_iso()})
                return

            self._send_json({"error": "not_found", "path": path}, status=404)

        def log_message(self, format: str, *args: Any) -> None:
            return

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
            static_root = project_root / "frontend" / "dist"
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


def _dashboard_snapshot(project_root: Path) -> dict[str, Any]:
    sessions = _load_recent_sessions()
    
    patient_data = {
        "name": sessions[0]["patientName"] if sessions else "Cihaz Hazır",
        "species": "",
        "breed": "",
        "owner": "PEMF Medical",
    }
    
    coils_list = [
        _live_state["coils"][i] for i in range(8)
    ]
    
    return {
        "gateway": _live_state["gateway"],
        "mqtt": _live_state["mqtt"],
        "stm": _live_state["stm"],
        "patient": patient_data,
        "activeTreatment": _live_state["activeTreatment"],
        "coils": coils_list,
        "sessions": sessions,
    }


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
    return {
        "system_status": _live_state["gateway"],
        "treatment_active": _live_state["activeTreatment"]["mode"] != "Sistem Hazır",
        "current_parameters": {
            "frequency": _live_state["activeTreatment"]["frequencyHz"],
            "intensity": _live_state["activeTreatment"]["intensityMt"],
            "duration": _live_state["activeTreatment"]["remainingMin"]
        },
    }


def _legacy_sensor_data() -> dict[str, Any]:
    # Geriye dönük uyumluluk için 1. bobinin verisini döndürür
    coil = _live_state["coils"][0]
    return {
        "object_temp": coil["objectTemp"],
        "ambient_temp": coil["ambientTemp"],
        "magnetic_field": coil["magneticMt"],
        "current": coil["currentA"],
        "esp_id": "backend-bridge",
        "esp_status": "online" if coil["connected"] else "offline",
    }


def _now_iso(timespec: str = "seconds") -> str:
    return datetime.now().isoformat(timespec=timespec)


if __name__ == "__main__":
    address = start_frontend_bridge()
    if not address:
        raise SystemExit(1)
    print(f"PEMF frontend backend running at http://{address[0]}:{address[1]}")
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        stop_frontend_bridge()
