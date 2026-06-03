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
