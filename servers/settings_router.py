import json
import logging

from fastapi import APIRouter
from pydantic import BaseModel

from utils.path_utils import get_app_data_directory

router = APIRouter(prefix="/api/settings", tags=["settings"])
logger = logging.getLogger("SettingsRouter")

# Canonical veri klasörü — diğer router'larla AYNI olmalı (split-brain önler).
_app_data_dir = get_app_data_directory()
_settings_file = _app_data_dir / "system_settings.json"

from utils.production_config_manager import get_production_config

# NOT: E-posta (Gmail/SMTP) rapor gönderimi KALDIRILDI — raporlar artık mobil "Paylaş"
# butonuyla (expo-sharing) paylaşılıyor. Bu router yalnız klinik adı / BLE MAC / MQTT ayarını tutar.


class SettingsModel(BaseModel):
    clinic_name: str = ""
    ble_gateway_mac: str = ""
    mqtt_broker: str = "localhost"
    mqtt_port: str = "1883"


def load_settings() -> dict:
    data = {"clinic_name": "", "ble_gateway_mac": ""}
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
    # Eski kurulumlardan kalmış olabilecek e-posta sırlarını yanıttan ayıkla (artık kullanılmıyor).
    data.pop("email_sender", None)
    data.pop("email_password", None)
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

    # Save other settings to system_settings.json (e-posta alanları YOK)
    save_data = {
        "clinic_name": data.get("clinic_name", ""),
        "ble_gateway_mac": data.get("ble_gateway_mac", ""),
    }
    with open(_settings_file, "w", encoding="utf-8") as f:
        json.dump(save_data, f, ensure_ascii=False, indent=2)


@router.get("/")
def get_settings():
    """Ayarları döndürür (klinik adı / BLE MAC / MQTT)."""
    return load_settings()


@router.post("/")
def update_settings(payload: SettingsModel):
    data = payload.dict()
    save_settings(data)
    return {"status": "success"}
