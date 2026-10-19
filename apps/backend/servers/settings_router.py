# Author: mertaygn, cglrgrkn
import json
import logging
import os
import tempfile
import threading

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from utils.path_utils import get_app_data_directory

router = APIRouter(prefix="/api/settings", tags=["settings"])
logger = logging.getLogger("SettingsRouter")

# Canonical veri klasörü — diğer router'larla AYNI olmalı (split-brain önler).
_app_data_dir = get_app_data_directory()
_settings_file = _app_data_dir / "system_settings.json"
_settings_lock = threading.Lock()  # Audit P3: eş-zamanlı POST'lar system_settings.json'u bozmasın

from utils.production_config_manager import get_production_config, kayit_reddi_mi

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
    # Audit P3: atomik yaz (temp + os.replace) + kilit — eş-zamanlı POST veya yazma-sırası süreç-kill
    # system_settings.json'u yarım/bozuk bırakmasın (sonraki açılışta sessiz config kaybı).
    with _settings_lock:
        _dir = os.path.dirname(_settings_file) or "."
        _fd, _tmp = tempfile.mkstemp(dir=_dir, suffix=".tmp")
        try:
            with os.fdopen(_fd, "w", encoding="utf-8") as f:
                json.dump(save_data, f, ensure_ascii=False, indent=2)
            os.replace(_tmp, _settings_file)
        except Exception:
            try:
                os.unlink(_tmp)
            except Exception:
                pass
            raise


@router.get("/")
def get_settings():
    """Ayarları döndürür (klinik adı / BLE MAC / MQTT)."""
    return load_settings()


@router.post("/")
def update_settings(payload: SettingsModel):
    # ⚠️ KISMİ GÜNCELLEME (denetim 2026-08-17): yalnız GÖNDERİLEN alanlar değişir; gönderilmeyen
    # alan mevcut değerini KORUR. `payload.dict()` model varsayılanları yüzünden DAİMA 4 anahtar
    # taşıyordu ve iki sonucu vardı:
    #   (a) CANLI KAYIP: `clinic_name`i hiç göndermeyen arayüz (pf `SettingsScreen`in "Kaydet"i)
    #       onu HER kayıtta `system_settings.json`dan siliyordu;
    #   (b) yalnız `clinic_name` gönderen bir istemci MQTT broker ayarını sessizce
    #       `localhost:1883`e döndürüyordu.
    # `save_settings` ZATEN kısmi sözlüğe göre yazılmış (`if "mqtt_broker" in data` gibi kapılar
    # var); eksik olan tek şey ona kısmi sözlüğü VERMEKTİ.
    # ⚠️ Depoda `Optional[X] = None` + sentinel deseni de var ama burada 4 alan tipini değiştirmek
    # ve OpenAPI varsayılanlarını kaybetmek gerekirdi; `exclude_unset` sıfır model değişikliğiyle
    # aynı semantiği veriyor.
    data = {**load_settings(), **payload.dict(exclude_unset=True)}
    try:
        save_settings(data)
    except Exception as e:
        # ⚠️ D2.81 (B-3.41): okunamayan config.json'da kayıt REDDEDİLİR (varsayılanlar klinik ayarlarını ezmesin). Eskiden ret
        # sessizdi ve uç "success" diyordu — operatör ayarın kaydedildiğini sanıyordu. Şimdi eylem söyleyen 503 (hiçbir ayar
        # yazılmadı: config.json system_settings.json'dan ÖNCE yazılır).
        if kayit_reddi_mi(e):
            raise HTTPException(status_code=503, detail=str(e))
        raise
    return {"status": "success"}


# ── ARAYÜZ DİLİ — cihaz düzeyi (I18N · Y161, T5) ────────────────────────────────────────────────────────────────────────────
# Masaüstü arayüz (backend bu makinede) dil seçince buraya bildirir; launcher ve istek DIŞI üretimler (zamanlanmış bildirim, arka plan
# PDF) bu ayarı kullanır (`utils.ceviri.etkin_dil`). Profil / hesap DEĞİLDİR (Y161) — profil seçiminin kalıcı OLMAMASI kuralı ayrı.
# Bayrak (`I18N_EN_ACIK`) arayüzde: kapalıyken arayüz bu ucu hiç çağırmaz (dil kartı gizli).


class ArayuzDiliModel(BaseModel):
    dil: str


@router.get("/arayuz-dili")
def arayuz_dili_al():
    """Cihaz düzeyindeki arayüz dili; hiç seçilmemişse `null` (istek dışı üretimler o zaman Türkçe)."""
    from utils import ceviri

    return {"dil": ceviri.cihaz_dili_ayarli_mi()}


@router.post("/arayuz-dili")
def arayuz_dili_yaz(payload: ArayuzDiliModel):
    from utils import ceviri

    if not ceviri.gecerli_dil(payload.dil):
        raise HTTPException(
            status_code=400, detail=ceviri.t("ayarlar.arayuzDili.gecersiz", dilKodu=str(payload.dil)[:20])
        )
    try:
        dil = ceviri.cihaz_dili_yaz(payload.dil)
    except OSError as e:
        logger.warning("arayuz dili yazilamadi: %r", e)
        raise HTTPException(status_code=503, detail=ceviri.t("ayarlar.arayuzDili.yazilamadi", neden=type(e).__name__))
    return {"status": "success", "dil": dil}
