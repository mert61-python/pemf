import os
import json
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import logging

from utils.email_sender import get_email_sender
from database.treatment_history_db import get_treatment_db
from utils.path_utils import get_app_data_directory

router = APIRouter(prefix="/api/settings", tags=["settings"])
logger = logging.getLogger("SettingsRouter")

# Canonical veri klasörü — diğer router'larla AYNI olmalı (split-brain önler;
# send_email PDF'i de doğru DB'den üretilsin).
_app_data_dir = get_app_data_directory()
_settings_file = _app_data_dir / "system_settings.json"

from utils.production_config_manager import get_production_config

class SettingsModel(BaseModel):
    clinic_name: str = ""
    email_sender: str = ""
    email_password: str = ""
    ble_gateway_mac: str = ""
    mqtt_broker: str = "localhost"
    mqtt_port: str = "1883"

class EmailPayload(BaseModel):
    recipient_email: str
    patient_name: str
    session_ids: str
    additional_message: str = ""

def load_settings() -> dict:
    data = {"clinic_name": "", "email_sender": "", "email_password": "", "ble_gateway_mac": ""}
    if _settings_file.exists():
        try:
            with open(_settings_file, "r", encoding="utf-8") as f:
                data.update(json.load(f))
        except Exception:
            pass
    # Get MQTT from config.json
    cfg = get_production_config()
    data["mqtt_broker"] = cfg.get("mqtt.broker_url", "localhost")
    data["mqtt_port"] = str(cfg.get("mqtt.broker_port", 1883))
    return data

def save_settings(data: dict):
    # Save MQTT to config.json
    cfg = get_production_config()
    if "mqtt_broker" in data:
        cfg.set("mqtt.broker_url", data["mqtt_broker"], save=False)
    if "mqtt_port" in data:
        try:
            cfg.set("mqtt.broker_port", int(data["mqtt_port"]), save=False)
        except ValueError:
            pass
    cfg.save()

    # E-posta şifresi yazma-amaçlı sır: gelen boşsa mevcut kayıtlı şifreyi KORU
    # (GET şifreyi maskelediği için istemci onu geri göndermez → boş gelir).
    existing = {}
    if _settings_file.exists():
        try:
            with open(_settings_file, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except Exception:
            existing = {}
    incoming_pwd = (data.get("email_password") or "").strip()
    email_password = incoming_pwd or existing.get("email_password", "")

    # Save other settings to system_settings.json
    save_data = {
        "clinic_name": data.get("clinic_name", ""),
        "email_sender": data.get("email_sender", ""),
        "email_password": email_password,
        "ble_gateway_mac": data.get("ble_gateway_mac", "")
    }
    with open(_settings_file, "w", encoding="utf-8") as f:
        json.dump(save_data, f, ensure_ascii=False, indent=2)

@router.get("/")
def get_settings():
    """Ayarları döndürür — GÜVENLİK: e-posta şifresini ASLA döndürmez (yazma-amaçlı sır).
    Sadece şifrenin kayıtlı olup olmadığını bildirir (email_password_set)."""
    data = load_settings()
    has_pwd = bool(data.get("email_password"))
    data["email_password"] = ""            # düz-metin sırrı istemciye gönderme
    data["email_password_set"] = has_pwd   # UI "kayıtlı" göstergesi için
    return data

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
        
    pdf_path = None
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
    finally:
        # P1 audit 2026-06-28: gonderim sonrasi (basari VEYA hata) PII PDF'i diskten sil —
        # at-rest SQLCipher korumasini duz-metin email_report*.pdf ile baypas etmesin.
        try:
            if pdf_path and os.path.exists(pdf_path):
                os.remove(pdf_path)
        except Exception:
            pass
