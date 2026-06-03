import os
import json
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import logging

from utils.email_sender import get_email_sender
from database.treatment_history_db import get_treatment_db

router = APIRouter(prefix="/api/settings", tags=["settings"])
logger = logging.getLogger("SettingsRouter")

_app_data_dir = Path.home() / ".pemf_gui"
_app_data_dir.mkdir(parents=True, exist_ok=True)
_settings_file = _app_data_dir / "system_settings.json"

class SettingsModel(BaseModel):
    clinic_name: str = ""
    email_sender: str = ""
    email_password: str = ""
    ble_gateway_mac: str = ""

class EmailPayload(BaseModel):
    recipient_email: str
    patient_name: str
    session_ids: str
    additional_message: str = ""

def load_settings() -> dict:
    if _settings_file.exists():
        try:
            with open(_settings_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"clinic_name": "", "email_sender": "", "email_password": "", "ble_gateway_mac": ""}

def save_settings(data: dict):
    with open(_settings_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

@router.get("/")
def get_settings():
    return load_settings()

@router.post("/")
def update_settings(payload: SettingsModel):
    data = payload.dict()
    save_settings(data)
    return {"status": "success"}

@router.post("/send_email")
def send_email(payload: EmailPayload):
    settings = load_settings()
    sender_email = settings.get("email_sender")
    sender_pwd = settings.get("email_password")
    clinic = settings.get("clinic_name", "Veteriner Kliniği")
    
    if not sender_email or not sender_pwd:
        raise HTTPException(status_code=400, detail="E-posta ayarları yapılmamış.")
        
    try:
        from utils.pdf_report_generator import get_pdf_generator
        pdf_gen = get_pdf_generator(_app_data_dir)
        
        id_list = [int(sid.strip()) for sid in payload.session_ids.split(",")]
        tmp_dir = _app_data_dir / "temp_reports"
        tmp_dir.mkdir(exist_ok=True)
        pdf_path = str(tmp_dir / f"email_report_{id_list[0]}.pdf")
        
        pdf_gen.generate_session_report(session_ids=id_list, output_path=pdf_path)
        
        mailer = get_email_sender()
        success = mailer.send_report_email(
            sender_email=sender_email,
            sender_password=sender_pwd,
            recipient_emails=[payload.recipient_email],
            pdf_file_path=pdf_path,
            patient_name=payload.patient_name,
            clinic_name=clinic,
            additional_message=payload.additional_message
        )
        
        if success:
            return {"status": "success", "message": "E-posta başarıyla gönderildi."}
        else:
            raise HTTPException(status_code=500, detail="E-posta gönderilemedi (Belki şifre veya rate limit).")
    except Exception as e:
        logger.error(f"Email send error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
