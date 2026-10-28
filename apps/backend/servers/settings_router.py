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
#
# ⚠️ D6.16 (B-3.97 · sahip kararı Y15): `mqtt_broker` / `mqtt_port` (`config.json` → `mqtt.broker_url` / `broker_port`)
# BAĞLANTIYA ETKİSİZDİR — yerel broker istemcisi sabit adrese bağlanır (`api_server._YEREL_BROKER` = 127.0.0.1:1883,
# `headless_core` `mqtt_port=1883`), ESP yolu kapalı (Y7). Eskiden uç değeri yazıp yalnız "success" diyordu; operatör
# bağlantının değiştiğini sanıyordu. Değerler aynen okunur / yazılır (fail-closed kayıt DEĞİŞMEZ, kod SİLİNMEZ); GET ve
# MQTT alanı gönderilen POST yanıtı `mqtt_etkisiz: true` + istek dilinde `mqtt_notu` taşır.
# Kapı: tests/test_ayar_MQTT_broker_ETKISIZ_D6_16.py (ayarı bağlantıya bağlayan kod eklenirse ölçüm kolu KIRMIZI olur).
_MQTT_ALANLARI = frozenset({"mqtt_broker", "mqtt_port"})


def _mqtt_etkisiz_notu() -> dict:
    from utils import ceviri

    return {"mqtt_etkisiz": True, "mqtt_notu": ceviri.t("ayarlar.mqtt.etkisiz")}


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
    """Ayarları döndürür (klinik adı / BLE MAC / MQTT — MQTT bağlantıya ETKİSİZ, D6.16)."""
    return {**load_settings(), **_mqtt_etkisiz_notu()}


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
    gonderilen = payload.dict(exclude_unset=True)
    data = {**load_settings(), **gonderilen}
    try:
        save_settings(data)
    except Exception as e:
        # ⚠️ D2.81 (B-3.41): okunamayan config.json'da kayıt REDDEDİLİR (varsayılanlar klinik ayarlarını ezmesin). Eskiden ret
        # sessizdi ve uç "success" diyordu — operatör ayarın kaydedildiğini sanıyordu. Şimdi eylem söyleyen 503 (hiçbir ayar
        # yazılmadı: config.json system_settings.json'dan ÖNCE yazılır).
        if kayit_reddi_mi(e):
            raise HTTPException(status_code=503, detail=str(e))
        raise
    # D6.16 (Y15): MQTT alanı gönderildiyse değer YAZILDI ama bağlantıya etkisiz — yanıt bunu söyler.
    if _MQTT_ALANLARI & gonderilen.keys():
        return {"status": "success", **_mqtt_etkisiz_notu()}
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


# ── Kabin kamerası (T2D-2 · Tezgâh-2 #3) ─────────────────────────────────────────────────────────────────────────────────
# AI Pro'nun sunucu kamerası CİHAZ düzeyinde seçilir (`utils.kabin_kamerasi`); seçim yoksa kamera açılmaz (dahili kameraya
# sessiz düşüş yok). Tarama yalnız kullanıcı eylemiyle ve AI Pro kamerayı tutmuyorken.


class KabinKamerasiModel(BaseModel):
    indeks: int


def _ai_kamerasi_mesgul() -> bool:
    try:
        from servers import ai_router as _ai

        return bool(getattr(_ai, "_ai_hazirlik_active", False) or getattr(_ai, "_ai_loop_active", False))
    except Exception:
        return False


@router.get("/kabin-kamerasi")
def kabin_kamerasi_al():
    """Seçili kabin kamerası (`null` = seçilmedi → AI Pro kamerası açılmaz) ve istenen çözünürlük."""
    from utils import kabin_kamerasi as kk

    return {"secili": kk.secili_kamera(), "istenenCozunurluk": list(kk.ISTENEN_COZUNURLUK)}


@router.post("/kabin-kamerasi")
def kabin_kamerasi_yaz(payload: KabinKamerasiModel):
    from utils import ceviri
    from utils import kabin_kamerasi as kk

    try:
        secim = kk.kamera_sec(payload.indeks)
    except ValueError:
        raise HTTPException(
            status_code=400, detail=ceviri.t("ayarlar.kabinKamerasi.gecersiz", indeks=str(payload.indeks)[:12])
        )
    except OSError as e:
        logger.warning("kabin kamerasi secimi yazilamadi: %r", e)
        raise HTTPException(
            status_code=503, detail=ceviri.t("ayarlar.kabinKamerasi.yazilamadi", neden=type(e).__name__)
        )
    if kk.canli_acik():
        # Y190: canlı oturum ESKİ kamerayı tutuyor — seçim değişince bırakılır (sonraki canlı / tek kare YENİ kameradan).
        kk.canli_durdur()
    return {"status": "success", "secili": secim}


@router.post("/kabin-kamerasi/tara")
def kabin_kamerasi_tara():
    """Bu makinedeki kameraları kısa açıp küçük önizlemeyle listeler (kullanıcı kabin kamerasını görüntüden tanır)."""
    from utils import ceviri
    from utils import kabin_kamerasi as kk

    if _ai_kamerasi_mesgul():
        raise HTTPException(status_code=409, detail=ceviri.t("ayarlar.kabinKamerasi.taramaMesgul"))
    if kk.canli_acik():
        # Y190: canlı oturum seçili kamerayı tutuyor — tarama o indeksi açamaz ve yanlış "kamera yok" derdi.
        raise HTTPException(status_code=409, detail=ceviri.t("ayarlar.kabinKamerasi.taramaCanliAcik"))
    return {"kameralar": kk.kameralari_tara(), "secili": kk.secili_kamera()}


@router.post("/kabin-kamerasi/kare")
def kabin_kamerasi_kare():
    """T3 · Y189 (sahip): petri / fantom analizine SEÇİLİ kabin kamerasından tam çözünürlüklü TEK kare (1920×1080 isteği —
    kalibrasyonla aynı). AI Pro kamerayı tutuyorsa 409; seçim yoksa 409 (dahili kameraya düşüş YOK); kare alınamazsa 503."""
    from utils import ceviri
    from utils import kabin_kamerasi as kk

    if _ai_kamerasi_mesgul():
        raise HTTPException(status_code=409, detail=ceviri.t("ayarlar.kabinKamerasi.kareMesgul"))
    try:
        kare = kk.kare_al()
    except kk.KameraSecilmedi:
        raise HTTPException(status_code=409, detail=ceviri.t("ai.pro.hazirlik.kameraSecilmedi")) from None
    if kare is None:
        secim = kk.secili_kamera() or {}
        raise HTTPException(
            status_code=503,
            detail=ceviri.t("ayarlar.kabinKamerasi.kareAlinamadi", indeks=str(secim.get("indeks", "?"))),
        )
    return {"status": "success", **kare}


# ── CANLI kabin kamerası (T3 · Y190): petri / fantom canlı önizleme + otomatik analiz ────────────────────────────────────────
@router.post("/kabin-kamerasi/canli/baslat")
def kabin_kamerasi_canli_baslat():
    """Seçili kabin kamerasını AÇIK tutan canlı oturumu başlatır (açıksa aynısı). AI Pro kamerayı tutuyorsa 409; seçim yoksa 409;
    açılamazsa 503. Kare istenmedikçe oturum kendiliğinden kapanır (`kabin_kamerasi.CANLI_ZAMAN_ASIMI_SN`)."""
    from utils import ceviri
    from utils import kabin_kamerasi as kk

    if _ai_kamerasi_mesgul():
        raise HTTPException(status_code=409, detail=ceviri.t("ayarlar.kabinKamerasi.canliMesgul"))
    try:
        d = kk.canli_baslat(mesgul=_ai_kamerasi_mesgul)
    except kk.KameraSecilmedi:
        raise HTTPException(status_code=409, detail=ceviri.t("ai.pro.hazirlik.kameraSecilmedi")) from None
    except kk.KameraMesgul:
        raise HTTPException(status_code=409, detail=ceviri.t("ayarlar.kabinKamerasi.canliMesgul")) from None
    if d is None:
        secim = kk.secili_kamera() or {}
        raise HTTPException(
            status_code=503,
            detail=ceviri.t("ayarlar.kabinKamerasi.kareAlinamadi", indeks=str(secim.get("indeks", "?"))),
        )
    return {"status": "success", **d}


@router.get("/kabin-kamerasi/canli/kare")
def kabin_kamerasi_canli_kare(tam: bool = False):
    """Canlı oturumun son karesi (`tam=true`: kalibrasyon boyutunda, analiz için; değilse küçük önizleme). Oturum yoksa 409.
    T3 · Y192: oturum açık ama ilk kare henüz yoksa kısa süre beklenir, gelmezse 200 `status: "bekliyor"` (`hazir: false`) —
    "kapalı" (409) DEĞİL; arayüz bekleyip yeniden ister."""
    from utils import ceviri
    from utils import kabin_kamerasi as kk

    k = kk.canli_kare(tam=tam is True, bekle_sn=kk.CANLI_ILK_KARE_BEKLE_SN)
    if k is None:
        raise HTTPException(status_code=409, detail=ceviri.t("ayarlar.kabinKamerasi.canliKapali"))
    if not k.get("hazir"):
        return {"status": "bekliyor", **k}
    return {"status": "success", **k}


@router.post("/kabin-kamerasi/canli/durdur")
def kabin_kamerasi_canli_durdur():
    """Canlı oturumu kapatır, kamera bırakılır (açık değilse de başarı)."""
    from utils import kabin_kamerasi as kk

    kk.canli_durdur()
    return {"status": "success"}
