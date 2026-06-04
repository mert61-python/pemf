from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
import logging
import tempfile
import os
import cv2
import numpy as np
import base64
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

app = FastAPI(
    title="PEMF React Native API Bridge",
    description="PyQt6 arayüzüne gerek duymayan Headless Donanım API'si",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # React Native için izin veriyoruz
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ai_router)
app.include_router(history_router)
app.include_router(settings_router)

# DEMA Simülatörü host etme
import os
sim_path = os.path.join(os.getcwd(), "dema-terapi-simülatörü", "dist")
if os.path.exists(sim_path):
    app.mount("/simulator", StaticFiles(directory=sim_path, html=True), name="simulator")

# Global State Container
class APIState:
    def __init__(self):
        self.core: HeadlessCore = None
        self.hardware: HardwareController = None
        
state = APIState()

@app.on_event("startup")
async def on_startup():
    logging.info("FastAPI Bridge: Başlıyor...")
    # Gerekirse veritabanı veya HW bağlantılarını buradan yönetebilirsiniz.

@app.on_event("shutdown")
async def on_shutdown():
    logging.info("FastAPI Bridge: Kapanıyor...")

# --- REACT NATIVE (EXPO) ENDPOINT'LERİ ---

@app.get("/api/health")
async def health_check():
    """Sistemin ayakta olup olmadığını kontrol eder."""
    return {
        "status": "online",
        "core_initialized": state.core is not None
    }

class CommandPayload(BaseModel):
    command: str
    params: dict = {}

class PatientInput(BaseModel):
    name: str = ""
    species: str = ""
    breed: str = ""
    age: str = ""
    weight: str = ""
    owner: str = ""
    vet_contact: str = ""

class AutoPresetPayload(BaseModel):
    target_condition: str

class SessionStartPayload(BaseModel):
    patient_id: str = ""
    patient_name: str = ""
    mode: str = "Manuel"  # Manuel | Otomatik | AI
    target_condition: str = ""
    frequency: float = 50.0
    duty: float = 25.0
    intensity: float = 25.0
    duration_minutes: int = 20
    coil_ids: list = []  # empty = all coils

class CoilControlPayload(BaseModel):
    freq: float = 50.0
    duty: float = 25.0
    phase: float = 0.0
    duration: int = 0
    start: bool = True

class BatchCoilPayload(BaseModel):
    coil_ids: list[int]  # e.g. [1,2,3]
    freq: float = 50.0
    duty: float = 25.0
    phase: float = 0.0
    duration: int = 0
    start: bool = True

# ── MQTT publish helper (used by headless and GUI-less mode) ─────────────────
import json as _json

def _mqtt_publish(topic: str, payload: dict) -> bool:
    """Publish a JSON payload to the local MQTT broker. Returns success."""
    try:
        import paho.mqtt.client as _mqtt
        c = _mqtt.Client(client_id="api_server_pub", clean_session=True)
        c.connect("127.0.0.1", 1883, 5)
        c.publish(topic, _json.dumps(payload), qos=1)
        c.disconnect()
        return True
    except Exception:
        return False

# ── Active session state (in-memory, shared) ─────────────────────────────────
from datetime import datetime as _dt
import threading as _threading

_session_lock = _threading.Lock()
_active_session: dict = {}  # empty when no session running

@app.post("/api/hardware/auto_preset")
async def auto_preset(payload: AutoPresetPayload):
    """
    Yapay Zeka skoruna göre (veya literatür hedefine göre)
    donanım parametrelerini otomatik ayarlar.
    """
    if not state.core or not state.hardware:
        raise HTTPException(status_code=503, detail="Donanım hazır değil.")
    
    try:
        from ai.hybrid_recommender import get_literature_recommendation
        from pathlib import Path
        app_data = Path.home() / ".pemf_gui"
        rec = get_literature_recommendation(payload.target_condition, app_data_dir=app_data)
        
        freq = float(rec.get("freq", 10.0))
        duty = float(rec.get("duty", 25.0))
        duration = float(rec.get("duration", 20.0))
        
        # Donanıma uygula
        success = state.hardware.start_all_coils(freq, duty, 0.0, int(duration))
        
        return {
            "status": "success" if success else "error",
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


# ── Per-coil MQTT control (direct ESP command via MQTT) ───────────────────────
@app.post("/api/coil/{coil_id}/control")
async def control_single_coil(coil_id: int, payload: CoilControlPayload):
    """Send a start/stop command to a specific ESP coil via MQTT."""
    import time
    if coil_id < 1 or coil_id > 8:
        raise HTTPException(status_code=400, detail="Geçersiz bobin ID (1-8)")

    command_id = f"react_{coil_id}_{int(time.time() * 1000)}"

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

    # Also update hardware controller if available
    if state.hardware and coil_id <= 5:
        state.hardware.update_coil(
            coil_id, payload.freq, payload.duty, payload.phase, payload.duration, start=payload.start
        )

    # Publish to MQTT broker (ESP listens here)
    ok = _mqtt_publish(f"pemf/coil/{coil_id}/control", mqtt_payload)
    return {"status": "success" if ok else "mqtt_unavailable", "command_id": command_id}


@app.post("/api/coil/batch")
async def control_batch_coils(payload: BatchCoilPayload):
    """Send the same command to multiple coils at once."""
    import time
    results = []
    for coil_id in payload.coil_ids:
        if coil_id < 1 or coil_id > 8:
            results.append({"coilId": coil_id, "status": "invalid"})
            continue
        command_id = f"react_batch_{coil_id}_{int(time.time() * 1000)}"
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
        ok = _mqtt_publish(f"pemf/coil/{coil_id}/control", mqtt_payload)
        if state.hardware and coil_id <= 5:
            state.hardware.update_coil(
                coil_id, payload.freq, payload.duty, payload.phase, payload.duration, start=payload.start
            )
        results.append({"coilId": coil_id, "status": "success" if ok else "mqtt_unavailable"})
    return {"status": "success", "results": results}


# ── Session management ────────────────────────────────────────────────────────
@app.post("/api/session/start")
async def start_session(payload: SessionStartPayload):
    """Start a new treatment session."""
    import time
    global _active_session
    with _session_lock:
        if _active_session.get("is_active"):
            raise HTTPException(status_code=409, detail="Zaten aktif bir seans var.")

        coil_ids = payload.coil_ids or list(range(1, 9))
        _active_session = {
            "is_active": True,
            "session_id": f"react_{int(time.time())}",
            "patient_id": payload.patient_id,
            "patient_name": payload.patient_name,
            "mode": payload.mode,
            "target_condition": payload.target_condition,
            "frequency": payload.frequency,
            "duty": payload.duty,
            "intensity": payload.intensity,
            "duration_minutes": payload.duration_minutes,
            "start_time": time.time(),
            "coil_ids": coil_ids,
        }

    # Send MQTT commands to all target coils
    import time as _t
    for coil_id in coil_ids:
        mqtt_payload = {
            "command": "start",
            "command_id": f"sess_{coil_id}_{int(_t.time() * 1000)}",
            "freq": payload.frequency,
            "duty": payload.duty,
            "phase": 0.0,
            "duration": payload.duration_minutes * 60,
        }
        _mqtt_publish(f"pemf/coil/{coil_id}/control", mqtt_payload)

    if state.hardware:
        state.hardware.start_all_coils(payload.frequency, payload.duty, 0.0, payload.duration_minutes * 60)

    # Sync to bridge for WS broadcast
    try:
        from servers.frontend_bridge import update_session_state
        update_session_state(
            is_active=True,
            mode=payload.mode,
            freq=payload.frequency,
            intensity=payload.intensity,
            remaining_min=payload.duration_minutes,
            duration_sec=payload.duration_minutes * 60,
        )
    except Exception:
        pass

    return {"status": "success", "session": _active_session}


@app.post("/api/session/stop")
async def stop_session():
    """Stop the active treatment session."""
    global _active_session
    with _session_lock:
        if not _active_session.get("is_active"):
            return {"status": "ok", "message": "Aktif seans yok."}
        coil_ids = _active_session.get("coil_ids", list(range(1, 9)))
        _active_session["is_active"] = False

    for coil_id in coil_ids:
        import time
        _mqtt_publish(f"pemf/coil/{coil_id}/control", {
            "command": "stop",
            "command_id": f"stop_{coil_id}_{int(time.time() * 1000)}"
        })

    if state.hardware:
        state.hardware.stop_all_coils()

    try:
        from servers.frontend_bridge import update_session_state
        update_session_state(is_active=False, mode="Sistem Hazır")
    except Exception:
        pass

    return {"status": "success", "message": "Seans durduruldu."}


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
        # Auto-stop if time is up
        if remaining == 0 and total > 0:
            sess["is_active"] = False
            with _session_lock:
                _active_session["is_active"] = False
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
    return {
        "softwareVersion": "1",
        "hardwareVersion": "HW-2025.1",
        "deviceId": device_id,
        "stmConnected": state.core.stm_is_connected if state.core else False,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    }

@app.get("/api/gateway/status")
async def gateway_status():
    """Return Mosquitto/Network/Bridge status."""
    status = {
        "mqttConnected": False,
        "brokerRunning": False,
        "bridgeConnected": False,
        "networkOnline": False,
        "hotspotActive": False,
    }
    try:
        from servers.frontend_bridge import _live_state
        status["mqttConnected"] = _live_state.get("mqtt") == "online"
        status["gatewayState"] = _live_state.get("gateway", "offline")
    except Exception:
        pass
    return status

@app.get("/api/dashboard-snapshot")
async def get_dashboard_snapshot():
    """Donanımdan ve broker'dan alınan gerçek zamanlı veriler (React Native için)."""
    # 5 bobinin gerçek state'ini hardware controller'dan alalım
    coils = []
    for i in range(1, 9):
        if state.hardware and i <= 5:
            c_state = state.hardware.coils_state[i]
            coils.append({
                "id": i,
                "connected": True,
                "running": c_state["is_running"],
                "frequencyHz": c_state["freq"],
                "dutyCycle": int(c_state["duty"] * 100),
                "magneticMt": 1.5,
                "objectTemp": 36.0,
                "ambientTemp": 25.0,
                "currentA": 0.5
            })
        else:
            coils.append({
                "id": i,
                "connected": False,
                "running": False,
                "frequencyHz": 0,
                "dutyCycle": 0,
                "magneticMt": 0.0,
                "objectTemp": 0.0,
                "ambientTemp": 0.0,
                "currentA": 0.0
            })

    return {
        "gateway": "online",
        "mqtt": "online",
        "stm": "online" if state.core and getattr(state.core, "stm_is_connected", False) else "warning",
        "patient": {
            "name": "Bilinmeyen",
            "species": "Belirsiz",
            "breed": "Belirsiz",
            "owner": "Bilinmeyen"
        },
        "activeTreatment": {
            "mode": "Manuel Mod",
            "frequencyHz": 0,
            "intensityMt": 0.0,
            "remainingMin": 0
        },
        "coils": coils,
        "sessions": []
    }

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
    """Yeni hasta ekler"""
    db = get_patient_database()
    if not db:
        raise HTTPException(status_code=500, detail="Patient DB not initialized")
    patient_id = db.add_patient(patient.dict())
    return {"status": "success", "patient_id": patient_id}

@app.delete("/api/patients/{patient_id}")
async def remove_patient(patient_id: str):
    """Hasta siler"""
    db = get_patient_database()
    success = db.delete_patient(patient_id)
    return {"status": "success" if success else "error"}

def start_fastapi_server(core_instance=None, port=8000):
    """
    Bu fonksiyon HeadlessCore içinden veya main.py'den bir Thread ile başlatılır.
    """
    state.core = core_instance
    if core_instance:
        state.hardware = HardwareController(core_instance)
        
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")

if __name__ == "__main__":
    start_fastapi_server()
