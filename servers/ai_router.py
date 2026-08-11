# Author: mertaygn, cglrgrkn
import asyncio
import base64
import logging
import os
import sys

import cv2
import numpy as np
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from servers.ai_client import (
    ai_service_enabled,
    delegate_infer,
    delegate_infer_sync,  # mikroservis: AI'yı GPU servisine devret (bayraklı; sync=AI Pro loop)
    delegate_json,
    delegate_json_sync,
)
from servers.entitlement import ai_queue_gate, require_research  # tier-enforcement (flag-gated, fail-open)

logger = logging.getLogger("ai_router")

import threading
import time

from utils.model_downloader import download_model_sync
from utils.stm32_protocol_limits import (
    normalize_ai_pro_duty_ratio,
    normalize_phase_deg,
)

# RNA CSV (20531 gen × N hasta) ve ses base64 yüklemeleri, Starlette multipart part-limitini
# (varsayılan 1MB — YALNIZ non-file form alanlarına uygulanır; dosya part'ları diske spool → limitsiz)
# aşabilir. audit B-2.3: eski çözüm Starlette İÇ sınıfı MultiPartParser.__init__'i GLOBAL monkeypatch
# ediyordu → sürüm yükseltmesinde SESSİZCE kırılabilirdi. Artık DESTEKLENEN request.form(max_part_size=)
# API'si + router-düzeyi dependency: yalnız multipart isteklerde limiti yükseltir, JSON gövdeye
# DOKUNMAZ; form'u request._form'a cache'ler → FastAPI'nin File/Form çözümü aynı cache'i kullanır.
_RNA_MAX_PART = 50 * 1024 * 1024  # 50 MB (~350 hasta RNA CSV'si)


async def _allow_large_upload(request: Request) -> None:
    """Büyük multipart yüklemeler için part-limitini yükselt (yalnız multipart; JSON gövdeye dokunmaz)."""
    if request.headers.get("content-type", "").startswith("multipart/form-data"):
        await request.form(max_part_size=_RNA_MAX_PART)


ai_router = APIRouter(dependencies=[Depends(_allow_large_upload), Depends(ai_queue_gate)])


from utils.image_domain import DomainMismatch as _ImgDomainMismatch


def _ai_fail(label: str, e: Exception) -> HTTPException:
    """AI uç hatası (audit B-4.1): gerçek nedeni SUNUCU-TARAFI logla; istemciye ham str(e)/traceback
    SIZDIRMA (bilgi ifşası — bu uçlar auth-muaf/publik). İstemciye yalnız kısa etiket döner.

    2026-08-06: HTTPException AYNEN geçirilir. Tüm görüntü uçları `except Exception → _ai_fail`
    deseni kullanıyor; bu, `_decode_image`'in ürettiği ANLAMLI istemci hatalarını (alan uyuşmazlığı
    422, boyut/çözünürlük sınırı) yutup hepsini "500 <etiket>"e çeviriyordu → kullanıcı "Analiz
    hatası" görüp NEDENİNİ öğrenemiyordu. Tek noktada düzeltildi (10 uçta tekrar gerekmez)."""
    if isinstance(e, HTTPException):
        return e
    logger.exception("%s", label)
    return HTTPException(status_code=500, detail=label)


# ── PETRİ MAKULLİK REDDİ (2026-08-06, sahip bildirimi) ────────────────────────────────────
# Denetimin KENDİSİ ai_hub boru hattındadır (mikroservis yolunda da çalışsın diye — bkz.
# ai_hub/inference_petri_dish/plausibility.py). Burada YALNIZ HTTP çevrimi yapılır.
# Sabit dize bilerek KOPYALANDI: `ai_hub...petri_cv` paketini modül seviyesinde import etmek
# onnxruntime/ultralytics zincirini her açılışta yükletirdi ve mikroservis modunda ai_hub hiç
# gerekmez. Değer bir TEL SÖZLEŞMESİDİR (JSON `error` alanı); tests/test_petri_plausibility.py
# iki tarafın eşitliğini kilitler → sessizce ayrışamaz.
_PETRI_NOT_PLATE = "not_a_petri_plate"
_PETRI_REJECT_FALLBACK = (
    "Bu modül petri kuyucuğu plakası fotoğrafı bekliyor; yüklenen görüntüde petri kuyucuğu "
    "geometrisi bulunamadı. Fantom fotoğrafını 'Fantom Tümör' modülüne, hayvan fotoğrafını "
    "ilgili kedi modülüne yükleyin — yanlış modülde üretilen sonuç yanıltıcıdır."
)


def _petri_reject_message(plausibility) -> str:
    """Boru hattının ürettiği ölçümlü mesajı kullan; yoksa (mikroservis yanıtı `plausibility`
    alanını taşımıyor) ölçümsüz ama aynı yönlendirmeyi veren metne düş."""
    if isinstance(plausibility, dict):
        msg = plausibility.get("message")
        if isinstance(msg, str) and msg.strip():
            return msg
    return _PETRI_REJECT_FALLBACK


# Proje ana dizinini bul
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Thread-safe lazy loading için model önbelleği
_models: dict = {}
_model_lock = threading.Lock()


def _get_or_load_model(key: str, loader_fn):
    """
    Thread-safe model yükleme yardımcısı.
    Model daha önce yüklendiyse direk döner.
    Yükleme sırasında kilidi tutar, hata olursa cache'i temizler.
    """
    if key in _models:
        return _models[key]
    with _model_lock:
        # Double-check after acquiring lock
        if key in _models:
            return _models[key]
        logger.info(f"Model yükleniyor: {key}")
        try:
            model = loader_fn()
            _models[key] = model
            logger.info(f"Model yüklendi ve önbelleğe alındı: {key}")
            return model
        except Exception as e:
            logger.error(f"Model yüklenemedi ({key}): {e}", exc_info=True)
            _models.pop(key, None)  # kırık model kalmasın
            raise


_MAX_IMAGE_BYTES = 25 * 1024 * 1024  # 25 MB — tek görüntü üst sınırı (sınırsız upload = RAM DoS koruması)
_MAX_IMAGE_PIXELS = 50_000_000  # 50 MP — dekompresyon-bombası koruması (küçük dosya → dev BGR ayırma → OOM)


async def _decode_image(file, image_base64, *, label: str) -> np.ndarray:
    """UploadFile veya base64'ten BGR görüntü çöz. İki yaygın hatayı TEK yerde, tutarlı ele alır:
      (1) girdi yok, (2) 'görüntü yerine HTML geldi' (React fallback index.html gönderdi).
    Böylece görüntü-decode sorunu çıkınca bakılacak tek fonksiyon burasıdır (tekrar kaldırıldı).
    GÜVENLİK: girdi _MAX_IMAGE_BYTES ile sınırlanır → devasa upload ile RAM tüketimi (DoS) engellenir."""
    if image_base64:
        # base64 çözülünce ~%75'ine iner; çözmeden ÖNCE kaba string sınırı (dev RAM allocation'ı önle).
        if len(image_base64) > (_MAX_IMAGE_BYTES * 4) // 3 + 1024:
            raise ValueError(f"Görüntü çok büyük (base64 girdi > {_MAX_IMAGE_BYTES // (1024 * 1024)} MB sınırı).")
        content = base64.b64decode(image_base64)
    elif file:
        # UploadFile.read(N): en fazla N bayt oku → tüm dosyayı RAM'e almadan sınırı aşanı reddet.
        content = await file.read(_MAX_IMAGE_BYTES + 1)
        if len(content) > _MAX_IMAGE_BYTES:
            raise ValueError(f"Görüntü çok büyük (> {_MAX_IMAGE_BYTES // (1024 * 1024)} MB sınırı).")
    else:
        raise ValueError("Görüntü verisi bulunamadı.")
    if len(content) > _MAX_IMAGE_BYTES:
        raise ValueError(f"Görüntü çok büyük (> {_MAX_IMAGE_BYTES // (1024 * 1024)} MB sınırı).")
    # Audit P2: dekompresyon-bombası guard — byte-limit yetmez (küçük PNG → dev BGR ayırma → OOM).
    # Decode ÖNCESİ header'dan boyutu oku (PIL lazy; piksel decode etmez); megapiksel eşiğini aşan reddet.
    try:
        import io as _io

        from PIL import Image as _PILImage

        with _PILImage.open(_io.BytesIO(content)) as _im:
            _w, _h = _im.size
            if _w * _h > _MAX_IMAGE_PIXELS:
                raise ValueError(
                    f"Görüntü çözünürlüğü çok yüksek ({_w}x{_h}px > {_MAX_IMAGE_PIXELS // 1_000_000}MP sınırı)."
                )
    except ValueError:
        raise
    except Exception:
        pass  # PIL header okuyamazsa cv2'ye bırak (bozuk/desteklenmeyen format zaten reddedilir)
    img = cv2.imdecode(np.frombuffer(content, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        stripped = content.strip()
        logger.error("%s: görüntü decode edilemedi (boyut=%d, baş=%r)", label, len(content), content[:40])
        if stripped.startswith(b"<!DOCTYPE html>") or stripped.startswith(b"<html"):
            raise ValueError("Görüntü yerine HTML (index.html) alındı. React paketini kontrol edin.")
        raise ValueError(f"Geçersiz görüntü verisi. Alınan boyut: {len(content)} bytes.")
    # ALAN (modalite) DENETİMİ — 2026-08-06: sınıflandırıcılar eğitim dağılımının DIŞINDAKİ bir
    # girdiye de softmax ile %100 "güvenir" (Böbrek Patoloji'ye CT kesiti → "Grade 4 · %100").
    # Modelin güvenine güvenmek yerine girdinin modalitesini bağımsız ölç; kesin uyuşmazlıkta
    # 422 ile ANLAŞILIR bir mesaj dön (bkz. utils/image_domain.py). Kapatma: PEMF_AI_DOMAIN_GUARD=0
    try:
        from utils import image_domain as _imgdom

        _imgdom.check(img, label)
    except _ImgDomainMismatch as _dm:
        raise HTTPException(status_code=422, detail=_dm.user_message()) from None
    except HTTPException:
        raise
    except Exception:
        logger.debug("alan denetimi çalıştırılamadı (atlandı)", exc_info=True)
    return img


def _encode_jpg_b64(img: np.ndarray, quality: int | None = None) -> str:
    """BGR görüntüyü JPEG'e kodla → base64 string (opsiyonel kalite 0-100)."""
    params = [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)] if quality is not None else []
    _, buffer = cv2.imencode(".jpg", img, params)
    return base64.b64encode(buffer).decode("utf-8")


class DiseaseInput(BaseModel):
    age: float = 0.0
    weight: float = 0.0
    hr: float = 0.0
    temp: float = 0.0
    duration: float = 0.0
    symptom_indices: list[int] = []


@ai_router.post("/api/ai/disease")
async def analyze_disease(data: DiseaseInput):
    """XGBoost Kedi Hastalık Analizi"""
    # ── Girdi validasyonu — sıfır/boş vital ile anlamsız tahmin üretilmesin (audit P1).
    # Canlı bir kedide kilo/nabız/sıcaklık 0 olamaz; eksikse SESSİZ yanlış tahmin yerine
    # 422 dönüp kullanıcıdan geçerli vital iste.
    problems = []
    if not (0 < data.weight <= 30):
        problems.append("kilo (kg) 0-30 aralığında girilmeli")
    if not (0 < data.hr <= 400):
        problems.append("nabız (bpm) girilmeli (makul: ~120-220)")
    if not (0 < data.temp <= 50):
        problems.append("vücut sıcaklığı (°C) girilmeli (makul: ~37-39.5)")
    if data.age < 0:
        problems.append("yaş negatif olamaz")
    if problems:
        raise HTTPException(
            status_code=422,
            detail="Güvenilir hastalık tahmini için geçerli vital veriler gerekli: " + "; ".join(problems),
        )

    try:
        if ai_service_enabled():
            return await delegate_json("disease", data.model_dump())

        def _load():
            from utils.model_downloader import download_model_sync

            download_model_sync("ai_hub/cat_disease/XGBoost.pkl")
            from ai_hub.cat_disease.inference_cat_disease import CatDiseasePredictor

            return CatDiseasePredictor()

        predictor = await asyncio.to_thread(_get_or_load_model, "disease", _load)
        results = predictor.predict(data.age, data.weight, data.hr, data.temp, data.duration, data.symptom_indices)

        # Sonuçlar list of tuples [('Hastalık A', 0.85), ...] formatında geliyor.
        formatted = [{"disease": d, "probability": p} for d, p in results]
        # Güven-eşiği: en yüksek olasılık düşükse FE "düşük güven — veteriner doğrulaması
        # gerekir" uyarısı göstersin (audit: güven-eşiği yoktu).
        top_p = max((float(p) for _, p in results), default=0.0)
        return {
            "status": "success",
            "results": formatted,
            "top_probability": round(top_p, 3),
            "low_confidence": top_p < 0.40,
        }
    except Exception as e:
        logger.error(f"Disease inference error: {e}", exc_info=True)
        raise _ai_fail("Hastalık analizi hatası", e)


@ai_router.post("/api/ai/vision/landmark")
async def analyze_landmark(
    request: Request, file: UploadFile = File(None), image_base64: str = Form(None), auto_adjust: bool = Form(False)
):
    """YOLO Pose + FGS Ağrı Skoru + Otonom Biyogeribildirim"""
    try:
        if ai_service_enabled():
            # NOT: auto_adjust (donanım biofeedback) mikroservis modunda çekirdekte kalır;
            # AI servisi yalnız analiz döner. Sunucu/donanımsız profilde auto_adjust yok.
            return await delegate_infer("landmark", file=file, image_base64=image_base64)
        img = await _decode_image(file, image_base64, label="landmark")

        def _load_landmark():
            from ultralytics import YOLO

            from utils.model_downloader import download_model_sync

            path = download_model_sync("ai_hub/cat_landmark/yolo26m-pose.onnx")
            return YOLO(path, task="pose")

        model = await asyncio.to_thread(_get_or_load_model, "landmark", _load_landmark)

        # Görüntüyü gecici dosyaya kaydet çünkü predict file path istiyor.
        import tempfile

        tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
        tmp.close()
        try:
            cv2.imwrite(tmp.name, img)
            results = await asyncio.to_thread(lambda: model.predict(tmp.name, conf=0.25, device="cpu", verbose=False))
        finally:
            # Hata olsa da geçici dosyayı temizle (disk şişmesini önle).
            try:
                os.unlink(tmp.name)
            except Exception:
                pass

        fgs_result = {}
        detected = False
        if results and len(results) > 0:
            r = results[0]
            if r.keypoints is not None and len(r.keypoints.xy) > 0 and r.boxes is not None and len(r.boxes) > 0:
                kp_xy = r.keypoints.xy[0].cpu().numpy()
                # Keypoint güven skoru (varsa): (0,0)/düşük-güvenli noktalar bozuk geometri -> sahte skor üretir.
                kp_conf = None
                try:
                    if r.keypoints.conf is not None:
                        kp_conf = r.keypoints.conf[0].cpu().numpy()
                except Exception:
                    kp_conf = None
                x1, y1, x2, y2 = r.boxes[0].xyxy[0].cpu().numpy()
                bw = max(x2 - x1, 1.0)
                bh = max(y2 - y1, 1.0)
                kp_norm = kp_xy.copy()
                kp_norm[:, 0] = (kp_norm[:, 0] - x1) / bw
                kp_norm[:, 1] = (kp_norm[:, 1] - y1) / bh

                from ai_hub.cat_landmark.inference_cat_landmark import compute_fgs

                fgs_result = compute_fgs(kp_norm)

                # GEÇERLİ TESPİT: skor >=0 + yeterli görünür keypoint + (varsa) makul güven.
                _ft = fgs_result.get("fgs_total", -1)
                _valid_kp = int(np.count_nonzero((kp_xy[:, 0] > 0) | (kp_xy[:, 1] > 0)))
                _conf_ok = True if kp_conf is None else (float(np.mean(kp_conf)) >= 0.20)
                if _ft is not None and _ft >= 0 and _valid_kp >= 20 and _conf_ok:
                    detected = True
                    for pt in kp_xy:
                        px, py = int(pt[0]), int(pt[1])
                        if px > 0 or py > 0:
                            cv2.circle(img, (px, py), 4, (0, 255, 80), -1)

        b64_image = _encode_jpg_b64(img)

        # KRİTİK: tespit yoksa FGS=0 "Ağrı Yok" YANLIŞ-GÜVENCESİ verme -> null + detected:false.
        if detected:
            total = fgs_result.get("fgs_total")
            pain_level = fgs_result.get("pain_level", "Unknown")
        else:
            total = None
            pain_level = "Kedi yüzü tespit edilemedi"

        # Otonom Biofeedback — YALNIZCA geçerli tespit varsa donanım sür (gürültüde sürme yok).
        hw_status = "idle"
        hw_params = {}
        # Audit P1: auto_adjust DONANIM SÜRÜŞÜ salt-analiz muafiyetini AŞAR → yalnız YEREL/LAN veya
        # geçerli-token'lı istekte sür (tünelden kimliksiz 8-bobin 30dk tedavisini engelle). Analiz muaf kalır.
        _drive_ok = False
        try:
            from servers.auth import check_token, is_local_request

            _h = request.headers
            _via_proxy = bool(_h.get("cf-connecting-ip") or _h.get("cf-ray") or _h.get("x-forwarded-for"))
            _drive_ok = is_local_request(request.client.host if request.client else "", _via_proxy) or check_token(
                _h.get("X-API-Key") or request.query_params.get("token") or ""
            )
        except Exception:
            logger.exception("landmark auto_adjust yetki kontrolü hatası")
            _drive_ok = False
        if auto_adjust and not detected:
            hw_status = "skipped_no_detection"
        elif auto_adjust and detected and not _drive_ok:
            hw_status = "skipped_unauthenticated"  # Audit P1: kimliksiz uzak istekte donanım SÜRÜLMEZ
        elif auto_adjust and detected:
            # Audit P2 #3: bloklayan donanım/MQTT çağrılarını (socket-probe 0.3s + connect 5s +
            # wait_for_publish 2s, 3× ESP) event-loop'tan ÇIKAR → to_thread (ai_pro_frame ile aynı
            # desen). Aksi halde her auto_adjust isteği loop'u saniyelerce kilitler → AI Pro kapalı-
            # döngü sürüş inference'ı ve /health dahil tüm async uçlar gecikir.
            def _drive_landmark_auto():
                try:
                    from servers.api_server import start_ai_session, state, update_live_session_state

                    if not (state and state.hardware):
                        return "idle", {}
                    # DENETIM P2: BASKA bir otonom surucu calisirken donanima DOKUNMA.
                    # Eskiden kosulsuz start_ai_session + start_all_coils cagriliyordu; AI Pro
                    # suruyorken gelen bir landmark auto_adjust istegi (ikinci istemci / dogrudan
                    # API) AI Pro'nun per-bobin duty/fazinin uzerine TEK-TIP degerler yaziyor,
                    # AI Pro'nun surmedigi BOBIN 8'i de enerjilendiriyor ve seans meta-verisini
                    # ("AI (Auto)", 30 dk, coil_ids 1-8) sessizce DEVRALIYORDU — iki otonom surucu
                    # ayni donanimda catisiyor, kayitta yanlis mod gorunuyordu.
                    if _ai_loop_active:
                        logger.info("AI (Auto): AI Pro aktif → donanim SURULMEDI (catisma onlendi).")
                        return "skipped_session_active", {}
                    try:
                        import servers.api_server as _apx3

                        with _apx3._session_lock:
                            _cur_mode = str(_apx3._active_session.get("mode", ""))
                            _cur_active = bool(_apx3._active_session.get("is_active"))
                        # Farkli modda AKTIF bir seans (Manuel/Otomatik/AI Pro) varsa devralma.
                        if _cur_active and _cur_mode != "AI (Auto)":
                            logger.info("AI (Auto): '%s' seansi aktif → donanim SURULMEDI.", _cur_mode)
                            return "skipped_session_active", {}
                    except Exception:
                        logger.warning("AI (Auto): aktif-seans kontrolu basarisiz", exc_info=True)
                    target_freq = min(100.0, 10.0 + (total * 5.0))
                    target_duty = min(50.0, 25.0 + (total * 3.0))
                    # Seansı _active_session'a yaz → süre-watchdog + emergency-stop AI'yı da kapsar.
                    start_ai_session(target_freq, target_duty, 30, range(1, 9), "AI (Auto)")
                    state.hardware.start_all_coils(target_freq, target_duty, 0.0, 30)
                    # ESP 6-8'i de sür (audit #13, kullanıcı onaylı 8-bobin) — tek-atış publish.
                    try:
                        import servers.api_server as _api_esp

                        for _cid in (6, 7, 8):
                            _api_esp._mqtt_publish(
                                f"pemf/coil/{_cid}/control",
                                {
                                    "command": "start",
                                    "command_id": f"aiauto_{_cid}_{int(time.time() * 1000)}",
                                    "freq": round(target_freq, 1),
                                    "duty": round(target_duty, 1),
                                    "phase": 0,
                                    "duration": 30 * 60,
                                },
                            )
                    except Exception as _ee:
                        logger.warning("AI (Auto) ESP 6-8 publish hatasi: %s", _ee)
                    update_live_session_state(
                        is_active=True, mode="AI (Auto)", freq=target_freq, intensity=target_duty, duration_sec=30 * 60
                    )
                    return "updated", {"freq": target_freq, "duty": target_duty}
                except Exception as e:
                    logger.error(f"Otonom biofeedback hatası: {e}")
                    return "idle", {}

            hw_status, hw_params = await asyncio.to_thread(_drive_landmark_auto)

        return JSONResponse(
            content={
                "status": "success",
                "image_base64": b64_image,
                "detected": detected,
                "fgs_total": total,
                "pain_level": pain_level,
                "raw_fgs": fgs_result if detected else None,
                "action_units": fgs_result.get("action_units") if detected else None,
                "hw_status": hw_status,
                "hw_params": hw_params,
            }
        )
    except Exception as e:
        logger.error(f"Landmark inference error: {e}", exc_info=True)
        raise _ai_fail("Landmark model hatası", e)


# ── AI Pro durumu (modül seviyesi) ──
_ai_loop_active = False
import threading as _ai_threading

# TOCTOU koruma: start/stop check-and-set atomik olsun → iki es-zamanli /ai/pro/start ikinci bir
# kamera loop'u acip VideoCapture(0)'i cakistiramasin / bobinleri cift suremesin.
_ai_loop_lock = _ai_threading.Lock()
_ai_thread = None
_ai_organ_id = 0
_ai_duration_min = 20
_ai_started_at = 0.0
# Klinik güvenlik: AI Pro seans süresi üst sınırı (Audit P1). Uzaktan {duration_minutes: 999999}
# ile günlerce/gözetimsiz PEMF sürüşünü engeller. (freq/duty/48°C safety-limit'lerine DOKUNMAZ.)
_AI_PRO_MAX_DURATION_MIN = 120
# AI Pro freq sabit 1 Hz (eski PyQt DDS varsayılanı). Sabit; backend'de limit/clamp EKLEME.
_AI_PRO_FREQ_HZ = 1.0
# em_kedi modelinin sabit ekstra girdileri (eski camera_ai_thread ile birebir).
_AI_ACHIEVED_B = 0.001  # Tesla (1 mT)
_AI_DUTY_SUM = 1.5
_ORGAN_NAMES = {
    0: "Tüm Vücut",
    1: "Mide",
    2: "Böbrek",
    3: "Karaciğer",
    4: "Mesane",
    5: "Pankreas",
    6: "Bağırsak",
    7: "Kalp",
    8: "Dalak",
    9: "Akciğer (sağ)",
    10: "Akciğer (sol)",
}

# ── cat_organ organ-lokalizasyon (el takibi YERİNE; kullanıcı kararı: MediaPipe Hands SÖKÜLDÜ) ──
# cat_organ ~1-4sn/kare (ağır) → loop HER KAREDE çalıştırmaz; periyodik lokalize + cache.
_ORGAN_LOCALIZE_INTERVAL_S = 10.0
_AI_LOST_STOP_STREAK = 3  # DENETIM P2: bu kadar ARDISIK hedef-kaybindan sonra bobinleri durdur
_MIN_RELIABILITY = 0.3  # organ güveni bu eşiğin altında → "bulunamadı" → coil SÜRÜLMEZ
_ai_relocalize = True  # bir sonraki karede zorla yeniden-lokalize (start/organ-değişim/yeniden-konumla)
_ai_organ_cache = {
    "x_mm": 0.0,
    "y_mm": 0.0,
    "z_mm": 0.0,
    "reliability": 0.0,
    "localized": False,
    "overlay_bgr": None,
    "at": 0.0,
    "organ_id": -1,
}
# Audit P2: _ai_organ_cache arkaplan loop (_ai_pro_loop) VE mobil frame ucu (ai_pro_frame) arasinda
# paylasilir. Cok-alanli okuma/.update() kilitsiz interleave olursa yirtik-okuma (bir organin
# reliability'si baska koordinatla) + celiskili bobin komutu. Kisa kritik-bolumler icin tek kilit
# (I/O kilit DISINDA → deadlock yok).
_ai_cache_lock = _ai_threading.Lock()


def _get_or_load_kedi():
    """KediPredictor'ı (em_kedi BiLSTM_XXL_Raw) thread-safe önbellekle."""

    def _load():
        # ONNX dosyasını standart kurulum/release_assets yolundan hazırla (find_installed_model).
        try:
            download_model_sync("ai_hub/em_kedi/BiLSTM_XXL_Raw.onnx")
        except Exception as _de:
            logger.warning("em_kedi ONNX indirme/çözümleme uyarısı: %s", _de)
        from ai_hub.em_kedi.inference_em_kedi import KediPredictor

        return KediPredictor(providers=["CPUExecutionProvider"])

    return _get_or_load_model("em_kedi", _load)


def _get_or_load_catorgan():
    """CatOrganPredictor'ı (kedi organ 3B lokalizasyon, 3 ONNX CPU) thread-safe önbellekle."""

    def _load():
        from ai_hub.inference_cat_organ.catorgan_predictor import CatOrganPredictor

        return CatOrganPredictor(device="cpu")

    return _get_or_load_model("cat_organ", _load)


def _extract_organ_target(organs_by_id, organ_id, overlay):
    """cat_organ sonucundan (CPU dict VEYA GPU-JSON'dan kurulmuş dict) seçili organ hedefini çıkar.
    organs_by_id: {id: {coord_cabin_cm|coord_3d_cm, reliability}}. organ_id 0 (Tüm Vücut) → max-reliability
    güven-geçidi + koordinat (0,0,0). NOT: estimate_organs_pnp INT-anahtarlı ama JSON'da str → ikisi denenir.
    Döner: (localized, x_mm, y_mm, z_mm, reliability, overlay_bgr)."""
    if int(organ_id) == 0:
        # Tüm Vücut: EN AZ BİR organ güvenle lokalize değilse "bulunamadı" → coil SÜRÜLMEZ (max güven-geçidi;
        # eski zorla-1.0 baypası KALDIRILDI — okluzyonlu organlara rağmen gerçek kediyi reddetmez, çöpte sürmez).
        rels = [float(v.get("reliability") or 0.0) for v in organs_by_id.values() if isinstance(v, dict)]
        conf = max(rels) if rels else 0.0
        return (conf >= _MIN_RELIABILITY), 0.0, 0.0, 0.0, conf, overlay
    o = organs_by_id.get(int(organ_id)) or organs_by_id.get(str(int(organ_id)))
    if not o:
        return False, 0.0, 0.0, 0.0, 0.0, overlay
    coord = o.get("coord_cabin_cm") or o.get("coord_3d_cm") or [0.0, 0.0, 0.0]
    rel = float(o.get("reliability") or 0.0)

    def _mm(v):
        return max(-300.0, min(300.0, float(v) * 10.0))  # cm→mm + em_kedi aralığı

    return (rel >= _MIN_RELIABILITY), _mm(coord[0]), _mm(coord[1]), _mm(coord[2]), rel, overlay


def _localize_organ_cpu(frame, organ_id):
    """cat_organ'ı YEREL (in-process, CPU) çalıştır → hedef organ. (tek-EXE klinik + GPU-fallback yolu)."""
    import tempfile

    tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
    tmp.close()
    cv2.imwrite(tmp.name, frame)
    try:
        clf = _get_or_load_catorgan()
        result = clf.predict(tmp.name, render=True, target_oid=(int(organ_id) or None))
    finally:
        try:
            os.unlink(tmp.name)
        except Exception:
            pass
    return _extract_organ_target(result.get("organs") or {}, organ_id, result.get("_overlay_bgr"))


def _localize_organ_gpu(frame, organ_id):
    """cat_organ inference'ını GPU servisine DEVRET (delegate_infer_sync; kare zaten to_thread'de).
    GPU-JSON organs list → {id:organ} dict + overlay base64→BGR → paylaşılan _extract_organ_target.
    (Hoca yönü: AI Pro'nun AĞIR 3B-lokalizasyonu Docker/GPU servisinde koşar.)"""
    ok, buf = cv2.imencode(".jpg", frame)
    if not ok:
        raise RuntimeError("frame JPG encode başarısız")
    resp = delegate_infer_sync(
        "cat_organ", buf.tobytes(), filename="frame.jpg", data={"target_oid": (int(organ_id) or None)}
    )
    organs_by_id = {}
    for o in resp.get("organs") or []:
        if isinstance(o, dict) and "id" in o:
            try:
                organs_by_id[int(o["id"])] = o
            except (TypeError, ValueError):
                pass
    overlay = None
    img_b64 = resp.get("image_base64")
    if img_b64:
        try:
            arr = np.frombuffer(base64.b64decode(img_b64), np.uint8)
            overlay = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        except Exception:
            overlay = None
    return _extract_organ_target(organs_by_id, organ_id, overlay)


def _localize_organ(frame, organ_id):
    """Kareden seçili organı cat_organ ile lokalize et (el takibinin YERİNE).
    cat_organ pipeline (YOLOseg + DLC + RTMPose + PnP, ~1-4sn) → 10 organ 3B. Hedefin
    coord_cabin_cm(ArUco)/coord_3d_cm → cm→mm [-300,300] clamp; organ_id 0 (Tüm Vücut) → (0,0,0).
    ai_service_enabled() ise inference GPU servisine DEVREDİLİR (hata → CPU-yerel fallback, davranış korunur).
    Döner: (localized, x_mm, y_mm, z_mm, reliability, overlay_bgr)."""
    if ai_service_enabled():
        try:
            return _localize_organ_gpu(frame, organ_id)
        except Exception as e:
            logger.warning("AI Pro cat_organ GPU delegasyonu başarısız → CPU-yerel: %s", e)
    return _localize_organ_cpu(frame, organ_id)


def _predict_and_drive_cpu(x_mm, y_mm, z_mm, organ_id):
    """em_kedi'yi YEREL (in-process CPU) çalıştır → D[7]/P[7]/e_field. (tek-EXE + GPU-fallback yolu).
    Eski PyQt davranışı: duty 0..0.50 clip (modelin kendi politikası); EK clamp yok."""
    predictor = _get_or_load_kedi()
    result = predictor.predict(
        x=x_mm,
        y=y_mm,
        z=z_mm,
        organ_id=organ_id,
        achieved_B=_AI_ACHIEVED_B,
        duty_sum=_AI_DUTY_SUM,
    )
    D = np.clip([result.get(f"D{i}", 0.0) for i in range(1, 8)], 0.0, 0.50).tolist()
    P = [float(result.get(f"P{i}", 0.0)) for i in range(1, 8)]  # zaten bobin-1 referanslı
    e_field = float(max(0.0, result.get("result_E", 0.0)))
    return D, P, e_field


def _predict_and_drive_gpu(x_mm, y_mm, z_mm, organ_id):
    """em_kedi sürüş inference'ını GPU servisine DEVRET (delegate_json_sync; zaten to_thread'de) → D/P/E.
    (Hoca yönü: AI Pro'nun bobin-sürüş modeli de Docker/GPU'da.) Aynı duty-clip(0..0.50) + faz-referansı."""
    resp = delegate_json_sync(
        "em_kedi",
        {
            "x": x_mm,
            "y": y_mm,
            "z": z_mm,
            "organ_id": int(organ_id),
            "achieved_B": _AI_ACHIEVED_B,
            "duty_sum": _AI_DUTY_SUM,
        },
    )
    D = np.clip([resp.get(f"D{i}", 0.0) for i in range(1, 8)], 0.0, 0.50).tolist()
    P = [float(resp.get(f"P{i}", 0.0)) for i in range(1, 8)]
    e_field = float(max(0.0, resp.get("result_E", 0.0)))
    return D, P, e_field


def _predict_and_drive(x_mm, y_mm, z_mm, organ_id):
    """em_kedi.predict(x,y,z,organ_id) → D[7]/P[7]/e_field (eski el-pipeline'ının em_kedi kısmı, aynen).
    ai_service_enabled() ise GPU servisine DEVREDİLİR (hata → CPU-yerel fallback). duty-clip+faz DEĞİŞMEDİ;
    TAM başarısızlıkta (0,0,0) döner = coil SÜRÜLMEZ (güvenli). Döner: (D_list[7], P_list[7], e_field)."""
    D = [0.0] * 7
    P = [0.0] * 7
    e_field = 0.0
    try:
        if ai_service_enabled():
            try:
                return _predict_and_drive_gpu(x_mm, y_mm, z_mm, organ_id)
            except Exception as e:
                logger.warning("AI Pro em_kedi GPU delegasyonu başarısız → CPU-yerel: %s", e)
        return _predict_and_drive_cpu(x_mm, y_mm, z_mm, organ_id)
    except Exception as pred_err:
        logger.error("KediPredictor tahmin hatası: %s", pred_err)
    return D, P, e_field


def _drive_coils_ai_pro(D, P):
    """
    em_kedi çıktısı D[7]/P[7] ile bobin 1-7'yi PER-COIL sürer (paylaşımlı tek faz YOK).
      - STM bobin 1-5: hardware_controller.update_coil (duty yüzde olarak, freq=1Hz, per-coil phase)
      - ESP bobin 6-7: _mqtt_publish pemf/coil/{cid}/control (per-coil duty/phase)
      - Bobin 8: SÜRÜLMEZ (kapalı).
    Limit/clamp EKLENMEZ — yalnız mevcut normalize_* yardımcıları (yüzde dönüşümü/0..360 faz).
    """
    from servers.api_server import state

    # STM bobin 1-5 (indeks 0-4)
    if state and state.hardware:
        for idx in range(5):
            cid = idx + 1
            duty_pct = normalize_ai_pro_duty_ratio(D[idx]) * 100.0  # ratio→% (eski 0.50 cap)
            phase_i = normalize_phase_deg(P[idx])
            try:
                state.hardware.update_coil(
                    cid,
                    freq=_AI_PRO_FREQ_HZ,
                    duty=duty_pct,
                    phase=phase_i,
                    duration=_ai_duration_min,
                    start=True,
                )
            except Exception as _he:
                logger.warning("AI Pro STM bobin %d sürüş hatası: %s", cid, _he)

    # ESP bobin 6-7 (indeks 5-6) — per-coil duty/phase (eski paylaşımlı duty + phase:0 DEĞİL).
    try:
        import servers.api_server as _api_esp

        for idx in (5, 6):
            cid = idx + 1
            duty_pct = round(normalize_ai_pro_duty_ratio(D[idx]) * 100.0, 1)
            phase_i = round(normalize_phase_deg(P[idx]), 1)
            _api_esp._mqtt_publish(
                f"pemf/coil/{cid}/control",
                {
                    "command": "start",
                    "command_id": f"aipro_{cid}_{int(time.time() * 1000)}",
                    "freq": round(_AI_PRO_FREQ_HZ, 1),
                    "duty": duty_pct,
                    "phase": phase_i,
                    "duration": int(_ai_duration_min * 60),
                },
            )
    except Exception as _ee:
        logger.warning("AI Pro ESP 6-7 publish hatası: %s", _ee)


def _build_ai_pro_percoil(D, P):
    """7-bobinlik perCoil yükü (gerçek per-coil AI duty/phase, yüzde). Bobin 8 yok (kapalı)."""
    out = []
    for idx in range(7):
        out.append(
            {
                "id": idx + 1,
                "freq": round(_AI_PRO_FREQ_HZ, 1),
                "duty": round(normalize_ai_pro_duty_ratio(D[idx]) * 100.0, 1),
                "phase": round(normalize_phase_deg(P[idx]), 1),
            }
        )
    return out


def _ai_pro_loop():
    global _ai_loop_active, _ai_relocalize
    logger.info("AI Pro Closed-Loop (cat_organ organ-lokalizasyon + em_kedi) arkaplan görevi BAŞLADI.")
    cap = cv2.VideoCapture(0)

    if not cap.isOpened():
        logger.error("Kamera açılamadı (VideoCapture(0)). AI Pro durduruluyor.")
        cap.release()
        _ai_loop_active = False
        return

    # Modeli erkenden yükle — hata fırlarsa kamerayı BIRAK (VideoCapture sızıntısını önle, Audit P1).
    try:
        _get_or_load_kedi()
        _get_or_load_catorgan()
    except Exception as e:
        logger.error("AI Pro em_kedi/cat_organ yüklenemedi, kamera bırakılıyor: %s", e)
        cap.release()
        _ai_loop_active = False
        return

    _lost_streak = 0  # ardisik hedef-kaybi sayaci (bkz. _AI_LOST_STOP_STREAK)
    while _ai_loop_active:
        start_time = time.time()
        # Dış STOP (acil-durdur / süre-watchdog / STM-disconnect / /session/stop) AI loop'u da durdursun.
        try:
            import servers.api_server as _api

            with _api._session_lock:
                _ext_active = bool(_api._active_session.get("is_active"))
            if not _ext_active:
                logger.info("AI Pro: seans dışarıdan durduruldu → loop sonlandırılıyor.")
                # DENETIM P0: bayrak TEMIZLENMEDEN break edilirse asagidaki teardown guard'i
                # (:730 `if _ai_loop_active: return`) bunu "yeni loop basladi" sanip bobin
                # STOP'unu ATLIYORDU. Dis durdurma (E-stop / sure-watchdog / /session/stop)
                # surus penceresine denk geldiginde bobinler keep-alive ile ENERJILI kaliyordu.
                # Sure-bitisi (:679) ve /ai/pro/stop (:813) yollari zaten temizliyor; yalniz bu
                # yol asimetrikti. start_ai_pro atomik check-and-set yaptigindan (:775-778)
                # bayrak True iken ikinci loop zaten baslayamaz → burada temizlemek guvenli;
                # bundan SONRA yeni loop baslarsa teardown guard'i onu dogru korur.
                _ai_loop_active = False
                break
        except Exception:
            logger.debug("AI Pro loop: seans durum kontrolü hatası (yok sayıldı)", exc_info=True)  # B-4.2
        ret, frame = cap.read()
        if not ret:
            time.sleep(0.5)
            continue

        try:
            from servers.api_server import _ws_broadcast_sync, update_live_session_state

            now = time.time()

            # ── cat_organ periyodik organ-lokalizasyon (HER KARE DEĞİL: ~1-4sn → cache) ──
            need_localize = (
                _ai_relocalize
                or _ai_organ_cache["organ_id"] != _ai_organ_id
                or (now - _ai_organ_cache["at"]) >= _ORGAN_LOCALIZE_INTERVAL_S
            )
            if need_localize:
                try:
                    # DENETIM P2 (organ-degisim yarisi): lokalizasyon 1-4 sn surer. Eskiden
                    # cache guncellenirken `_ai_organ_id` GLOBALI YENIDEN okunuyordu → bu sure
                    # icinde klinisyen /api/ai/pro/organ ile organi degistirdiyse ESKI organin
                    # koordinatlari YENI organin etiketiyle damgalaniyordu. Sonraki 10 sn boyunca
                    # need_localize'in uc kosulu da False kaldigindan em_kedi, yeni organ icin
                    # uretilmis duty/faz desenini ESKI organin konumuna odakliyordu; UI ise dogru
                    # organ adini gosteriyordu (enerji yanlis organa). Ayrica `_ai_relocalize`
                    # KOSULSUZ temizlendigi icin, lokalizasyon ucarken basilan "yeniden konumla"
                    # istegi de sessizce yutuluyordu.
                    # Cozum: iterasyon basinda organ kimligini SNAPSHOT al, cache'i onunla damgala;
                    # relocalize bayragini yalnizca ARADA yeni istek GELMEDIYSE temizle.
                    _oid = _ai_organ_id
                    # Bayragi ONCE tuket: bu lokalizasyon zaten mevcut istegi karsiliyor. Boylece
                    # islem SIRASINDA gelen yeni bir istek bayragi tekrar True yapar ve SONRAKI
                    # iterasyonda yeniden lokalize edilir — istek YUTULMAZ. (Sonradan kosulsuz
                    # temizlemek, ayirt edilemedigi icin taze istegi siliyordu.)
                    _ai_relocalize = False
                    lz, lx, ly, lzz, lrel, lov = _localize_organ(frame, _oid)
                    with _ai_cache_lock:
                        _ai_organ_cache.update(
                            {
                                "x_mm": lx,
                                "y_mm": ly,
                                "z_mm": lzz,
                                "reliability": lrel,
                                "localized": lz,
                                "overlay_bgr": lov,
                                "at": now,
                                "organ_id": _oid,  # SNAPSHOT: global yeniden okunmaz
                            }
                        )
                except Exception as le:
                    logger.error("cat_organ lokalizasyon hatası: %s", le)
                    # Audit P2: lokalizasyon HATASINDA cache'i geçersiz kıl — aksi halde ESKİ localized=True
                    # + bayat x/y/z ile bobinler eski (yanlış) hedefe sürülüyordu (kedi kabinden çıkınca /
                    # hareket edince). mobil ai_pro_frame zaten 500 dönüp sürmüyordu → asimetriyi kapatır.
                    with _ai_cache_lock:
                        _ai_organ_cache["localized"] = False

            with _ai_cache_lock:
                localized = _ai_organ_cache["localized"]
                x_mm = _ai_organ_cache["x_mm"]
                y_mm = _ai_organ_cache["y_mm"]
                z_mm = _ai_organ_cache["z_mm"]
                rel = _ai_organ_cache["reliability"]

            # ── em_kedi → per-coil → sür (YALNIZCA organ bulunduysa; el yerine organ-tespiti koşulu) ──
            if localized:
                # Audit P1: E-stop/stop lokalizasyon (~1-4s) sırasında gelmiş olabilir → SÜRMEDEN ÖNCE
                # is_active'i yeniden doğrula (E-stop'un ~1 iterasyon geçersiz kılınmasını engelle).
                import servers.api_server as _apx

                with _apx._session_lock:
                    _still = bool(_apx._active_session.get("is_active"))
                if not _still:
                    _ai_loop_active = False
                    break
                D, P, e_field = _predict_and_drive(x_mm, y_mm, z_mm, _ai_organ_id)
                _drive_coils_ai_pro(D, P)
                _lost_streak = 0  # hedef yeniden bulundu
            else:
                D, P, e_field = [0.0] * 7, [0.0] * 7, 0.0
                # DENETIM P2: bu dalda YALNIZCA yeni komut gonderilmiyordu; halihazirda enerjili
                # bobinlere STOP GITMIYORDU. STM keep-alive son duty paketini saniyede bir
                # tazeledigi ve ESP kendi `duration`i boyunca surdugu icin, hayvan kabinden
                # cikinca/kimildayinca (guven < _MIN_RELIABILITY) HEDEFSIZ tedavi seans sonuna
                # kadar devam ediyordu. Ustelik WS `perCoil` %0 yayinladigi icin operator
                # bobinleri kapali saniyordu. _MIN_RELIABILITY yorumunun NIYETI zaten
                # "coil SURULMEZ"di; artik aktif olarak durduruluyor.
                # Tek kare kaybinda durdurmak tedaviyi kirilgan yapar (tespit anlik sekebilir) →
                # ARDISIK _AI_LOST_STOP_STREAK kayiptan sonra durdur, tekrar bulununca surmeye
                # devam eder (seansi bitirmez; sure-watchdog + teardown kendi isini gorur).
                _lost_streak += 1
                if _lost_streak == _AI_LOST_STOP_STREAK:
                    try:
                        import servers.api_server as _apx2

                        _apx2._stop_session_coils(range(1, 8))
                        logger.warning(
                            "AI Pro: hedef %d ardisik iterasyondur bulunamadi → bobinler DURDURULDU "
                            "(hedef yeniden bulunursa surus devam eder).",
                            _lost_streak,
                        )
                    except Exception:
                        logger.exception("AI Pro: hedef-kayip STOP hatasi")

            remaining = (
                max(0, int(_ai_duration_min * 60 - (time.monotonic() - _ai_started_at))) if _ai_started_at else 0
            )
            if _ai_started_at and remaining <= 0:
                _ai_loop_active = False  # süre doldu → otomatik durdur

            # Canlı seans göstergesi: bobin-1 AI duty'sini temsil değer olarak ver.
            rep_duty = round(normalize_ai_pro_duty_ratio(D[0]) * 100.0, 1) if localized else 0.0
            update_live_session_state(
                is_active=True,
                mode=f"AI Pro · {_ORGAN_NAMES.get(_ai_organ_id, '')}",
                freq=_AI_PRO_FREQ_HZ,
                intensity=rep_duty,
                remaining_min=remaining // 60,
                duration_sec=_ai_duration_min * 60,
            )

            # ── Telemetri yayını: cache'li organ overlay + per-coil (React buradan dinler) ──
            overlay = _ai_organ_cache.get("overlay_bgr")
            if overlay is not None:
                oh, ow = overlay.shape[:2]
                sc = min(1.0, 960.0 / max(oh, ow))
                ov = (
                    cv2.resize(overlay, (int(ow * sc), int(oh * sc)), interpolation=cv2.INTER_AREA)
                    if sc < 1.0
                    else overlay
                )
                _, buffer = cv2.imencode('.jpg', ov, [cv2.IMWRITE_JPEG_QUALITY, 55])
            else:
                _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 50])
            b64_image = base64.b64encode(buffer).decode('utf-8')
            per_coil = _build_ai_pro_percoil(D, P)
            ws_data = {
                "imageBase64": b64_image,
                "detected": localized,
                "reliability": round(rel, 3),
                "target": {"x": round(x_mm, 1), "y": round(y_mm, 1), "z": round(z_mm, 1)},
                "eField": round(e_field, 4),
                "organId": _ai_organ_id,
                "organName": _ORGAN_NAMES.get(_ai_organ_id, ""),
                "perCoil": per_coil,
                "remainingSec": remaining,
                "durationMin": _ai_duration_min,
            }
            try:
                _ws_broadcast_sync({"type": "ai_vision", "data": ws_data})
            except Exception as wse:
                logger.error(f"WS broadcast error in AI loop: {wse}")

        except Exception as e:
            logger.error(f"AI Loop iteration error: {e}")

        elapsed = time.time() - start_time
        sleep_time = max(0.1, 1.0 - elapsed)
        time.sleep(sleep_time)

    cap.release()
    # Audit P2 (teardown-race seal): süre-doldu ile bu teardown arasındaki ~1sn'de yeni bir
    # start_ai_pro başlamış olabilir (_ai_loop_active tekrar True + yeni seans). O durumda YENİ seans
    # bobinlere sahiptir → bu ESKİ thread'in teardown'ı onları DURDURMASIN + is_active'ini EZMESİN.
    if _ai_loop_active:
        logger.info("AI Pro teardown atlandı: yeni loop başlamış (bobinler yeni seansa ait).")
        return
    # Loop bittiğinde (süre doldu / durduruldu / hata) bobinleri DONANIM düzeyinde durdur —
    # keep-alive ile sonsuza sürmesin (AI artık sürmüyor).
    try:
        import servers.api_server as _api2

        if _api2.state and _api2.state.hardware:
            _api2.state.hardware.stop_all_coils()
        # ESP 6-8'i de durdur (AI bunları da sürüyordu — audit #13).
        for _cid in (6, 7, 8):
            try:
                _api2._mqtt_publish(
                    f"pemf/coil/{_cid}/control",
                    {
                        "command": "stop",
                        "command_id": f"ai_stop_{_cid}_{int(time.time() * 1000)}",
                    },
                )
            except Exception:
                logger.warning("AI Pro stop: bobin %s STOP publish hatası", _cid, exc_info=True)  # B-4.2
        with _api2._session_lock:
            if str(_api2._active_session.get("mode", "")).startswith("AI"):
                _api2._active_session["is_active"] = False
        _api2.update_live_session_state(is_active=False, mode="Sistem Hazır")
    except Exception:
        logger.exception("AI Pro loop sonu STOP hatasi")
    logger.info("AI Pro Closed-Loop arkaplan görevi DURDU.")


class AiProStartPayload(BaseModel):
    organ_id: int = 0
    duration_minutes: int = 20
    # SERT KAPI (2026-08-06 sahip kararı): onaylanmış öneri kimliği ZORUNLU.
    # Boş bırakılırsa istek 428 ile reddedilir — otonom tedavi hekim onayı olmadan başlamaz.
    proposal_id: str = ""


class AiProProposePayload(BaseModel):
    organ_id: int = 0
    duration_minutes: int = 20


@ai_router.post("/api/ai/pro/propose")
def propose_ai_pro(payload: AiProProposePayload = AiProProposePayload()):
    """AI'ın önerdiği tedavi parametrelerini ÜRET — DONANIMA DOKUNMADAN.

    SAHİP KARARI (2026-08-06, sert kapı): hekim önce ne uygulanacağını görür, sonra onaylar.
    Bu uç yalnız HESAPLAR: organ konumu (taze lokalizasyon önbelleğinden) → em_kedi → D[7]/P[7].
    Dönen `proposalId` onaylanmadan `/api/ai/pro/start` çalışmaz.

    ⚠️ DÜRÜSTLÜK: AI Pro KAPALI DÖNGÜdür — onay TEDAVİNİN BAŞLAMASINI kapıya bağlar, sonraki
    her döngü adımını DEĞİL. Hayvan hareket ettikçe `_ai_pro_loop` yeniden lokalize edip
    duty/faz'ı günceller; bunları dondurmak kapalı-döngü tasarımını bozardı. Onay = "bu hasta
    için bu organda otonom tedaviyi başlatıyorum" beyanıdır.
    """
    oid = int(payload.organ_id)
    if oid not in (0, 1, 2, 3, 4, 5, 6):
        raise HTTPException(status_code=422, detail=f"organ_id {oid} AI Pro seansı için desteklenmiyor (geçerli 0-6).")
    with _ai_cache_lock:
        c = dict(_ai_organ_cache)
    taze = (
        bool(c.get("localized"))
        and int(c.get("organ_id", -1)) == oid
        and (time.time() - float(c.get("at") or 0)) < 120.0
    )
    if not taze:
        raise HTTPException(
            status_code=409,
            detail="Organ henüz lokalize edilmedi. Kamerayı hedefe doğrultup 'Yeniden konumla' "
            "ile lokalizasyonu tamamlayın, sonra öneri alın.",
        )
    D, P, e_field = _predict_and_drive(c["x_mm"], c["y_mm"], c["z_mm"], oid)
    if not any(float(d) > 0 for d in D):
        raise HTTPException(
            status_code=422,
            detail="Model bu konum için sürülebilir bir parametre üretmedi (tüm duty=0). Lokalizasyonu tekrarlayın.",
        )
    from servers import ai_approval

    sure = max(1, min(_AI_PRO_MAX_DURATION_MIN, int(payload.duration_minutes)))
    rec = ai_approval.create(
        "ai_pro",
        {
            "organ_id": oid,
            "duration_minutes": sure,
            "coil_ids": list(range(1, 8)),
            "D": [round(float(d), 4) for d in D],
            "P": [round(float(p), 2) for p in P],
            "e_field": round(float(e_field), 6),
        },
        meta={
            "x_mm": c["x_mm"],
            "y_mm": c["y_mm"],
            "z_mm": c["z_mm"],
            "reliability": round(float(c.get("reliability") or 0.0), 3),
            "localized_at": c.get("at"),
        },
    )
    return {
        "status": "success",
        "proposalId": rec["id"],
        "specs": rec["specs"],
        "meta": rec["meta"],
        "expiresAt": rec["expires_at"],
    }


class AiApprovalPayload(BaseModel):
    proposal_id: str = ""
    operator_email: str = ""
    reason: str = ""


@ai_router.post("/api/ai/pro/approve")
def approve_ai_pro(payload: AiApprovalPayload):
    """Hekim önerilen parametreleri ONAYLAR. Denetim izi session_events'e yazılır."""
    from servers import ai_approval

    try:
        rec = ai_approval.approve(payload.proposal_id, payload.operator_email)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from None
    _kaydet_onay_izi("ai_proposal_approved", rec)
    return {"status": "success", "proposalId": rec["id"]}


@ai_router.post("/api/ai/pro/reject")
def reject_ai_pro(payload: AiApprovalPayload):
    """Hekim önerilen parametreleri REDDEDER (gerekçesiyle). Tedavi BAŞLAMAZ."""
    from servers import ai_approval

    try:
        rec = ai_approval.reject(payload.proposal_id, payload.operator_email, payload.reason)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from None
    _kaydet_onay_izi("ai_proposal_rejected", rec)
    return {"status": "success", "proposalId": rec["id"]}


def _kaydet_onay_izi(olay: str, rec: dict) -> None:
    """Onay/red kararını KALICI denetim izine yaz (append-only session_events).
    Best-effort: DB hatası klinik akışı DURDURMAZ, ama sessizce de yutulmaz (log'a düşer)."""
    try:
        from servers.api_server import _get_treatment_db

        _get_treatment_db().record_session_event(
            None,
            olay,
            payload={
                "proposal_id": rec.get("id"),
                "operator": rec.get("operator"),
                "reason": rec.get("reason"),
                "specs": rec.get("specs"),
                "meta": rec.get("meta"),
            },
            severity="info",
        )
    except Exception:
        logger.warning("AI onay denetim izi yazılamadı (%s)", olay, exc_info=True)


@ai_router.post("/api/ai/pro/start")
def start_ai_pro(payload: AiProStartPayload = AiProStartPayload()):
    global _ai_loop_active, _ai_thread, _ai_organ_id, _ai_duration_min, _ai_started_at, _ai_relocalize
    # Güncelleme uygulanıyorken otonom AI Pro tedavisi BAŞLATMA: installer servisi durdurup
    # EXE'yi değiştirebilir → bobinler kontrolcüsüz kalır (update TOCTOU guard'ının ters yönü).
    try:
        from servers import update_manager as _um

        if _um.is_update_in_progress():
            raise HTTPException(
                status_code=409, detail="Güncelleme uygulanıyor; işlem bitene kadar AI Pro başlatılamaz."
            )
    except HTTPException:
        raise
    except Exception:
        pass
    # ── SERT KAPI (2026-08-06 sahip kararı): ONAYSIZ OTONOM TEDAVİ BAŞLAMAZ ────────────
    # Onay TÜKETİLİR (tek kullanımlık + süreli) ve uygulanacak parametreler onaylananın
    # MÜHÜRLÜ kopyasından okunur → "onayı al, başka parametreyle sür" yapısal olarak imkânsız.
    # Kilit ALINMADAN ÖNCE doğrulanır: reddedilen istek `_ai_loop_active`'i kirletmemeli.
    from servers import ai_approval

    try:
        _onay = ai_approval.consume(payload.proposal_id)
    except ValueError as e:
        raise HTTPException(status_code=428, detail=str(e)) from None
    _spec = _onay.get("specs") or {}

    # ATOMIK check-and-set: iki es-zamanli start ikinci loop'u ACMASIN (TOCTOU).
    with _ai_loop_lock:
        if _ai_loop_active:
            return {"status": "success", "message": "Already running"}
        _ai_loop_active = True

    # Audit P2: em_kedi yalnız organ 0-6'yı TEDAVİ eder; 7-10 (Kalp/Dalak/Akciğer) cat_organ ile
    # lokalize olur ama _build_input ValueError→D=P=0 (sessiz sıfır-tedavi) YİNE 'aktif+lokalize·Kalp'
    # gösterir → klinisyeni 'kalp tedavi ediliyor' diye yanıltır. Desteklenmeyeni reddet + loop'u geri al.
    # Organ ve süre ONAYLANAN mühürden okunur; istemcinin gövdede gönderdiği değer YOK SAYILIR
    # (aksi halde "organ 2'yi onaylat, organ 5'i başlat" mümkün olurdu — enerji YANLIŞ ORGANA).
    _organ_req = int(_spec.get("organ_id", payload.organ_id))
    if _organ_req not in (0, 1, 2, 3, 4, 5, 6):
        with _ai_loop_lock:
            _ai_loop_active = False
        raise HTTPException(
            status_code=422, detail=f"organ_id {_organ_req} AI Pro seansı için desteklenmiyor (geçerli 0-6)."
        )
    _ai_organ_id = _organ_req
    # Süreyi klinik üst sınıra kapla (Audit P1) — aksi halde {duration_minutes: 999999} uzaktan
    # kabul ediliyordu. Bu değer hem STM/watchdog'a hem ESP MQTT yüküne (_ai_duration_min*60) gider.
    # Süre de MÜHÜRDEN okunur (organ ile aynı gerekçe: "20 dk onayla, 180 dk başlat" olmasın).
    _ai_duration_min = max(
        1, min(_AI_PRO_MAX_DURATION_MIN, int(_spec.get("duration_minutes", payload.duration_minutes)))
    )
    # DENETIM P2: DUVAR SAATI idi. AI Pro sure siniri gecen-sure farkiyla hesaplandigindan
    # NTP duzeltmesi/DST/elle saat degisimi GERI giderse maruziyet UZAR (donanim deadline'i
    # keep-alive ile her saniye tazelendigi icin onu da kesmez). Dort kullanimin hepsi delta
    # oldugundan monotonic'e gecildi (epoch olarak hicbir yerde gosterilmiyor).
    _ai_started_at = time.monotonic()
    _ai_relocalize = True  # başlangıçta hemen cat_organ lokalizasyonu yap
    _ai_organ_cache["localized"] = False
    # Seansı baştan _active_session'a yaz → süre-watchdog + emergency-stop AI Pro'yu da kapsar.
    # 1-7: STM 1-5 + ESP 6-7 (bobin 8 KAPALI; em_kedi 7 bobinlik per-coil duty/phase üretir).
    try:
        from servers.api_server import start_ai_session

        start_ai_session(0.0, 0.0, _ai_duration_min, range(1, 8), "AI Pro")
    except Exception:
        logger.exception("start_ai_session failed")
    import threading

    _ai_thread = threading.Thread(target=_ai_pro_loop, daemon=True)
    _ai_thread.start()
    return {
        "status": "success",
        "message": "AI Pro Closed-Loop Started",
        "organId": _ai_organ_id,
        "durationMin": _ai_duration_min,
    }


@ai_router.post("/api/ai/pro/stop")
def stop_ai_pro():
    global _ai_loop_active
    with _ai_loop_lock:
        _ai_loop_active = False

    # Bobinleri TÜM transport'larda durdur: STM 1-5 + ESP 6-8 (Audit P1 #3). Eskiden yalnız
    # stop_all_coils (STM) çağrılıyordu; kamerasız/mobil yolda loop-cleanup çalışmadığı için
    # ESP 6-7 STOP almadan enerjili kalıyordu. _stop_session_coils ikisini de durdurur + coil-run kapatır.
    # DENETIM P1: kapsam range(1,8) idi = bobin 8 ATLANIYORDU. "AI (Auto)" landmark yolu
    # (_drive_landmark_auto) 8 BOBINLI seans acar (start_ai_session(..., range(1,9)) + ESP 6,7,8'e
    # duration=1800 publish) ve /ai/pro/start'i HIC cagirmaz → _ai_pro_loop teardown'u da yok.
    # Boylece acik STOP komutundan sonra bobin 8, ESP'de 30 dk enerjili kaliyordu; onu durduracak
    # baska yazilim katmani da yok (sure-watchdog ve /session/stop 'aktif seans yok' diye erken doner).
    # Calismayan bobine STOP gondermek zararsiz/idempotenttir → kapsami TUM 8 bobine cikar.
    import servers.api_server as _api

    try:
        _api._stop_session_coils(range(1, 9))
    except Exception:
        logger.exception("stop_ai_pro: _stop_session_coils hatası")
    # AI seansını da kapat → süre-watchdog ve frame-geçidi 'seans aktif değil' görsün.
    try:
        with _api._session_lock:
            if str(_api._active_session.get("mode", "")).startswith("AI"):
                _api._active_session["is_active"] = False
    except Exception:
        logger.exception("stop_ai_pro: _active_session reset hatası")
    _api.update_live_session_state(is_active=False, mode="Sistem Hazır")
    return {"status": "success", "message": "AI Pro Closed-Loop Stopped"}


@ai_router.post("/api/ai/pro/organ")
def set_ai_pro_organ(payload: AiProStartPayload = AiProStartPayload()):
    """Hedef organı değiştir (loop çalışırken de geçerli) + hemen yeniden-lokalize et."""
    global _ai_organ_id, _ai_relocalize
    _organ_req = int(payload.organ_id)
    if _organ_req not in (0, 1, 2, 3, 4, 5, 6):  # Audit P2: em_kedi yalnız 0-6 TEDAVİ eder (7-10 sessiz-sıfır)
        raise HTTPException(status_code=422, detail=f"organ_id {_organ_req} desteklenmiyor (geçerli 0-6).")
    _ai_organ_id = _organ_req
    _ai_relocalize = True  # yeni organ için cat_organ'ı hemen yeniden çalıştır
    return {"status": "success", "organId": _ai_organ_id, "organName": _ORGAN_NAMES.get(_ai_organ_id, "")}


@ai_router.post("/api/ai/pro/calibrate")
def calibrate_ai_pro():
    """Yeniden konumla: bir sonraki karede cat_organ organ-lokalizasyonunu zorla tazele.
    (Eski avuç-tabanlı Z kalibrasyonu KALDIRILDI — el takibi söküldü.)"""
    global _ai_relocalize
    _ai_relocalize = True
    return {"status": "success", "relocalize": True}


@ai_router.get("/api/ai/pro/status")
def ai_pro_status():
    remaining = 0
    if _ai_loop_active and _ai_started_at:
        remaining = max(0, int(_ai_duration_min * 60 - (time.monotonic() - _ai_started_at)))
    return {
        "active": _ai_loop_active,
        "organId": _ai_organ_id,
        "organName": _ORGAN_NAMES.get(_ai_organ_id, ""),
        "durationMin": _ai_duration_min,
        "remainingSec": remaining,
        "localized": bool(_ai_organ_cache.get("localized")),
        "reliability": round(float(_ai_organ_cache.get("reliability", 0.0)), 3),
    }


@ai_router.post("/api/ai/ai_pro/frame")
async def ai_pro_frame(file: UploadFile = File(None), image_base64: str = Form(None)):
    """
    MOBİL AI Pro karesi: telefon kamerasından gelen TEK kareyi işler.
    cat_organ organ-lokalizasyon + em_kedi KediPredictor → bobin 1-7 PER-COIL sürüş
    (loop ile AYNI donanım yolu; el takibi SÖKÜLDÜ) → organ overlay + per-coil/metrik döner.
    cat_organ ağır (~1-4sn) → periyodik lokalize + cache (mobil akıcı kalsın).

    Organ/süre AKTİF AI Pro seansından okunur (web ile aynı state). FE bu çağrıdan
    ÖNCE /api/ai/pro/start çağırır; mobilde kareler bu endpoint'ten, web'de sunucu kamerasından.
    """
    try:
        img = await _decode_image(file, image_base64, label="ai_pro_frame")

        # cat_organ organ-lokalizasyon (el takibi söküldü). Ağır (~1-4sn) → periyodik + cache;
        # inference'i thread'e AL → event-loop'u (WS telemetri + diğer istekler) bloklamasın.
        global _ai_relocalize
        now = time.time()
        need_localize = (
            _ai_relocalize
            or _ai_organ_cache["organ_id"] != _ai_organ_id
            or (now - _ai_organ_cache["at"]) >= _ORGAN_LOCALIZE_INTERVAL_S
        )
        if need_localize:
            # DENETIM P2 (mobil yolda AYNI organ-degisim yarisi — loop tarafiyla simetrik):
            # organ kimligini SNAPSHOT al (await sonrasi global yeniden okunmasin, yoksa ESKI
            # organin koordinatlari YENI organin etiketiyle 10 sn cache'lenir) ve relocalize
            # bayragini ONCE tuket (islem sirasinda gelen yeni istek yutulmasin).
            _oid = _ai_organ_id
            _ai_relocalize = False
            lz, lx, ly, lzz, lrel, lov = await asyncio.to_thread(_localize_organ, img, _oid)
            with _ai_cache_lock:
                _ai_organ_cache.update(
                    {
                        "x_mm": lx,
                        "y_mm": ly,
                        "z_mm": lzz,
                        "reliability": lrel,
                        "localized": lz,
                        "overlay_bgr": lov,
                        "at": now,
                        "organ_id": _oid,
                    }
                )

        with _ai_cache_lock:
            localized = _ai_organ_cache["localized"]
            x_mm = _ai_organ_cache["x_mm"]
            y_mm = _ai_organ_cache["y_mm"]
            z_mm = _ai_organ_cache["z_mm"]
            rel = _ai_organ_cache["reliability"]

        # GÜVENLİK (Audit P0): bobin YALNIZCA süre-watchdog kapsamındaki AKTİF AI Pro seansı
        # varken sürülür. /start çağrılmadan (veya süre dolduktan / durdurulduktan sonra) gelen
        # kare bobin SÜRMEZ → watchdog'un izlemediği gözetimsiz/uzayan PEMF maruziyetini engeller.
        session_active = False
        try:
            import servers.api_server as _api

            with _api._session_lock:
                _sess = _api._active_session
                session_active = bool(_sess.get("is_active")) and str(_sess.get("mode", "")).startswith("AI")
            if session_active and _ai_started_at and (time.monotonic() - _ai_started_at) >= _ai_duration_min * 60:
                session_active = False  # süre dolmuş (watchdog henüz kapatmamış olsa da) → sürme
        except Exception:
            logger.exception("ai_pro_frame: aktif-seans kontrolü hatası")
            session_active = False

        D, P, e_field = [0.0] * 7, [0.0] * 7, 0.0
        # GERÇEK donanımı sür (loop ile aynı yol) — organ bulundu VE aktif AI Pro seansı varsa. Bobin 1-7.
        if localized and session_active:
            D, P, e_field = await asyncio.to_thread(_predict_and_drive, x_mm, y_mm, z_mm, _ai_organ_id)
            # Audit P2: _drive_coils_ai_pro senkron MQTT publish yapar (ESP probe/connect/wait ~sn) →
            # event-loop'u bloklardi (es-zamanli /emergency_stop yaniti gecikir). to_thread'e al.
            await asyncio.to_thread(_drive_coils_ai_pro, D, P)
            remaining = (
                max(0, int(_ai_duration_min * 60 - (time.monotonic() - _ai_started_at))) if _ai_started_at else 0
            )
            try:
                from servers.api_server import update_live_session_state

                rep_duty = round(normalize_ai_pro_duty_ratio(D[0]) * 100.0, 1)
                update_live_session_state(
                    is_active=True,
                    mode=f"AI Pro · {_ORGAN_NAMES.get(_ai_organ_id, '')}",
                    freq=_AI_PRO_FREQ_HZ,
                    intensity=rep_duty,
                    remaining_min=remaining // 60,
                    duration_sec=_ai_duration_min * 60,
                )
            except Exception:
                logger.exception("AI Pro frame: live state update hatası")

        # Organ overlay (yoksa ham kare) — mobil için küçült
        overlay = _ai_organ_cache.get("overlay_bgr")
        img_out = overlay if overlay is not None else img
        oh, ow = img_out.shape[:2]
        sc = min(1.0, 960.0 / max(oh, ow))
        if sc < 1.0:
            img_out = cv2.resize(img_out, (int(ow * sc), int(oh * sc)), interpolation=cv2.INTER_AREA)
        b64_image = _encode_jpg_b64(img_out, quality=70)

        return JSONResponse(
            content={
                "status": "success",
                "image_base64": b64_image,
                "detected": localized,
                "driven": bool(localized and session_active),
                "sessionActive": session_active,
                "reliability": round(rel, 3),
                "perCoil": _build_ai_pro_percoil(D, P),
                "target": {"x": round(x_mm, 1), "y": round(y_mm, 1), "z": round(z_mm, 1)},
                "eField": round(e_field, 4),
                "organId": _ai_organ_id,
                "organName": _ORGAN_NAMES.get(_ai_organ_id, ""),
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"AI Pro frame error: {e}", exc_info=True)
        raise _ai_fail("AI Pro kare hatası", e)


@ai_router.post("/api/ai/vision/segmentation")
async def analyze_segmentation(file: UploadFile = File(None), image_base64: str = Form(None)):
    """YOLO Seg Kedi Segmentasyonu"""
    try:
        if ai_service_enabled():
            return await delegate_infer("segmentation", file=file, image_base64=image_base64)
        img = await _decode_image(file, image_base64, label="segmentation")

        def _load_seg():
            from ultralytics import YOLO

            from utils.model_downloader import download_model_sync

            path = download_model_sync("ai_hub/cat_segmentation/yolov8m-seg.onnx")
            return YOLO(path, task="segment")

        model = await asyncio.to_thread(_get_or_load_model, "seg", _load_seg)

        import tempfile

        tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
        tmp.close()
        cv2.imwrite(tmp.name, img)
        # P2 audit 2026-06-28: tmp .jpg'yi HER durumda sil (predict/mask hata yolunda sizmasin → disk
        # dolar → _ensure_write_guardrail sensor/seans yazimini engelleyebilir). landmark deseni.
        try:
            results = await asyncio.to_thread(
                lambda: model.predict(source=tmp.name, conf=0.25, iou=0.7, imgsz=640, device="cpu", verbose=False)
            )
            r = results[0]
            cat_count = len(r.boxes) if r.boxes else 0
            if r.masks is not None and len(r.masks) > 0:
                for mask_data in r.masks.data:
                    mask_np = mask_data.cpu().numpy()
                    mask_resized = cv2.resize(mask_np, (img.shape[1], img.shape[0]), interpolation=cv2.INTER_NEAREST)
                    colored = np.zeros_like(img)
                    colored[:, :, 1] = 160
                    blend = cv2.addWeighted(img, 0.55, colored, 0.45, 0)
                    img = np.where(mask_resized[:, :, None] > 0.5, blend, img).astype(np.uint8)
        finally:
            try:
                os.unlink(tmp.name)
            except Exception:
                pass

        b64_image = _encode_jpg_b64(img)

        return {"status": "success", "cat_count": cat_count, "image_base64": b64_image}
    except Exception as e:
        logger.error(f"Segmentation inference error: {e}", exc_info=True)
        raise _ai_fail("Segmentasyon hatası", e)


@ai_router.post("/api/ai/vision/thermal")
async def analyze_thermal(file: UploadFile = File(None), image_base64: str = Form(None)):
    """GhostNetV2 Termal Analiz"""
    try:
        if ai_service_enabled():
            return await delegate_infer("thermal", file=file, image_base64=image_base64)
        img = await _decode_image(file, image_base64, label="thermal")

        def _load_thermal():
            from ai_hub.cat_thermal.inference_cat_thermal import CatThermalPredictor

            return CatThermalPredictor(model_name="GhostNetV2")

        predictor = await asyncio.to_thread(_get_or_load_model, "thermal", _load_thermal)

        import tempfile

        tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
        tmp.close()
        cv2.imwrite(tmp.name, img)

        # P2 audit 2026-06-28: tmp .jpg'yi HER durumda sil (predict hata yolunda sizmasin → disk dolar).
        try:
            result = await asyncio.to_thread(lambda: predictor.predict(tmp.name, threshold=0.5))
        finally:
            try:
                os.unlink(tmp.name)
            except Exception:
                pass

        b64_image = _encode_jpg_b64(img)

        return {"status": "success", "prediction": result, "image_base64": b64_image}
    except Exception as e:
        logger.error(f"Thermal inference error: {e}", exc_info=True)
        raise _ai_fail("Termal model hatası", e)


@ai_router.post("/api/ai/vision/reticulocytes")
async def analyze_reticulocytes(file: UploadFile = File(None), image_base64: str = Form(None)):
    """YOLO Detect Retikülosit Sayımı"""
    tmp = None  # finally'de temizlenecek temp görüntü (hata olsa da sızmasın)
    try:
        if ai_service_enabled():
            return await delegate_infer("reticulocytes", file=file, image_base64=image_base64)
        img = await _decode_image(file, image_base64, label="reticulocytes")

        def _load_retic():
            from ultralytics import YOLO

            from utils.model_downloader import download_model_sync

            path = download_model_sync("ai_hub/feline_reticulocytes/yolov8s.onnx")
            return YOLO(path, task="detect")

        # model-load-thread: ilk-yükleme (indir+ONNX) event-loop'u bloklamasın → thread-safe cache'i offload et.
        model = await asyncio.to_thread(_get_or_load_model, "retic", _load_retic)

        import tempfile

        tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
        tmp.close()
        cv2.imwrite(tmp.name, img)

        temp_project = os.path.join(tempfile.gettempdir(), "PEMF_API_AI")
        output_dir = os.path.join(temp_project, 'feline_reticulocytes', 'results')
        os.makedirs(output_dir, exist_ok=True)

        results = await asyncio.to_thread(
            lambda: model.predict(
                source=tmp.name,
                conf=0.25,
                iou=0.7,
                imgsz=640,
                device='cpu',
                save=True,
                project=os.path.join(temp_project, 'feline_reticulocytes'),
                name='results',
                exist_ok=True,
            )
        )

        CLASS_NAMES = ['erythrocyte', 'punctate reticulocyte', 'aggregate reticulocyte']
        counts = {c: 0 for c in CLASS_NAMES}

        for r in results:
            if r.boxes is not None:
                for box in r.boxes:
                    cls_id = int(box.cls[0])
                    counts[CLASS_NAMES[cls_id]] += 1

        saved_image_path = os.path.join(output_dir, os.path.basename(tmp.name))

        if os.path.exists(saved_image_path):
            img_res = cv2.imread(saved_image_path)
            b64_image = _encode_jpg_b64(img_res)
        else:
            b64_image = _encode_jpg_b64(img)

        os.unlink(tmp.name)

        return {"status": "success", "counts": counts, "image_base64": b64_image}
    except Exception as e:
        logger.error(f"Reticulocytes inference error: {e}", exc_info=True)
        raise _ai_fail("Retikülosit model hatası", e)
    finally:
        # reticulocytes-finally fix: temp dosyayı hata olsa da MUTLAKA sil (diğer uçlarla tutarlı).
        # Eski kod os.unlink'i finally DIŞINDA çağırıyordu → predict/imwrite hata verirse temp sızardı.
        if tmp is not None:
            try:
                os.unlink(tmp.name)
            except Exception:
                pass


@ai_router.post("/api/ai/vision/em_fantom")
async def analyze_em_fantom(
    _res=Depends(require_research),
    file: UploadFile = File(None),
    image_base64: str = Form(None),
    phantom_length_cm: float = Form(None),
    achieved_B: float = Form(None),
    duty_sum: float = Form(None),
):
    """Fantom Tümör Analizi (phantom_cv + BiLSTM_XXL_Raw ONNX).

    Sentetik böbrek fantomu fotoğrafından: fantomu tespit et → mavi tümör
    odaklarını bul → 3B mm koordinatı (phantom_length_cm verilirse gerçek mm,
    yoksa piksel) → PhantomPredictor ile her tümör için D1-7/P1-7 + E_cancer.
    Klasik CV (headless-güvenli), 6-panel annotated görsel döner.
    """
    try:
        if ai_service_enabled():
            return await delegate_infer(
                "em_fantom",
                file=file,
                image_base64=image_base64,
                data={"phantom_length_cm": phantom_length_cm, "achieved_B": achieved_B, "duty_sum": duty_sum},
            )
        img = await _decode_image(file, image_base64, label="em_fantom")

        def _load_em_fantom():
            # Büyük ONNX runtime'da indirilir (ProgramData/HF); yerel dev'de mevcut.
            try:
                download_model_sync("ai_hub/inference_em_fantom/BiLSTM_XXL_Raw.onnx")
            except Exception as _de:
                logger.warning("em_fantom ONNX indirme/çözümleme uyarısı: %s", _de)
            from ai_hub.inference_em_fantom.phantom_cv import (
                PhantomCvPipeline,
                load_cabin_config,
            )

            cfg = load_cabin_config(None)  # gömülü cabin_config_example.yaml
            warm = PhantomCvPipeline(cfg, manual_fallback=False)
            _ = warm.predictor  # ONNX + scaler'ları bir kez yükle
            return {"cfg": cfg, "predictor": warm._predictor, "cls": PhantomCvPipeline}

        cache = await asyncio.to_thread(_get_or_load_model, "em_fantom_cv", _load_em_fantom)
        # Her istekte hafif pipeline (taze intrinsics), önbellekli predictor enjekte.
        # manual_fallback=False ŞART — headless serviste GUI açmamalı.
        pl = cache["cls"](cache["cfg"], phantom_length_cm=phantom_length_cm, manual_fallback=False)
        pl._predictor = cache["predictor"]

        result, ctx = await asyncio.to_thread(lambda: pl.process_image(img, achieved_B=achieved_B, duty_sum=duty_sum))

        if result.success:
            panels = await asyncio.to_thread(lambda: pl.render_panels(ctx, result, lang="tr"))
            _, buffer = cv2.imencode('.jpg', panels["07_combined"])
            status = "success"
        else:
            _, buffer = cv2.imencode('.jpg', img)  # tespit yok → orijinali dön
            status = "no_detection"
        b64_image = base64.b64encode(buffer).decode('utf-8')

        payload = result.to_dict()
        # CANLI E-ALANI bağlamı (2026-08-06): tümör konumu + organ seans boyunca DEĞİŞMEZ.
        # Bunu saklarsak tedavi sürerken E'yi AYNI vekil modelle canlı B/duty'den türetebiliriz
        # → bar'daki değer bu paneldeki E ile aynı kaynaktan gelir (bkz. servers/efield_live.py).
        try:
            from servers import efield_live as _ef

            _ef.set_context(payload.get("tumor_regions") or [])
        except Exception:
            logger.debug("canlı E-alanı bağlamı kurulamadı", exc_info=True)
        return {
            "status": status,
            "image_base64": b64_image,
            "success": result.success,
            "error": result.error,
            "n_tumor": result.n_tumor,
            "n_healthy": result.n_healthy,
            "method": result.method,
            "mm_per_px": round(result.mm_per_px, 4),
            "tumor_regions": payload["tumor_regions"],
            "healthy_regions": payload["healthy_regions"],
            "timing_ms": result.timing_ms,
        }
    except Exception as e:
        logger.error(f"em_fantom inference error: {e}", exc_info=True)
        raise _ai_fail("Fantom analiz hatası", e)


@ai_router.post("/api/ai/vision/em_petri")
async def analyze_em_petri(
    _res=Depends(require_research),
    file: UploadFile = File(None),
    image_base64: str = Form(None),
    petri_diameter_cm: float = Form(None),
    achieved_B: float = Form(None),
    duty_sum: float = Form(None),
):
    """Petri Kuyu Analizi (petri_cv YOLO11m-seg + BaggingRegressor ONNX).

    Petri fotoğrafından: YOLO ile N kuyucuk tespit → her kuyuda HSV kanser
    sınıflandırma → 3B mm koordinat (petri_diameter_cm verilirse gerçek mm) →
    PetriPredictor ile D1-7/P1-7 + E_cancer. Klasik CV + YOLO (headless-güvenli),
    7-panel annotated görsel döner.
    """
    try:
        if ai_service_enabled():
            _remote = await delegate_infer(
                "em_petri",
                file=file,
                image_base64=image_base64,
                data={"petri_diameter_cm": petri_diameter_cm, "achieved_B": achieved_B, "duty_sum": duty_sum},
            )
            # MİKROSERVİS YOLU: makullik reddi ai_hub boru hattında verilir (ai_service o kodu
            # aynen çalıştırır) ve JSON `error` alanıyla telden geçer. Burada da 422'ye çevrilmeli;
            # aksi halde GPU dağıtımında kullanıcı yine sessiz bir "no_detection" görürdü.
            if isinstance(_remote, dict) and _remote.get("error") == _PETRI_NOT_PLATE:
                raise HTTPException(status_code=422, detail=_petri_reject_message(_remote.get("plausibility")))
            return _remote
        img = await _decode_image(file, image_base64, label="em_petri")

        def _load_em_petri():
            from ai_hub.inference_petri_dish.petri_cv import (
                PetriCvPipeline,
                load_cabin_config,
            )

            # YOLO ONNX yolu (ProgramData/HF'den indir; yoksa yerel dev).
            try:
                yolo_path = download_model_sync("ai_hub/inference_petri_dish/yolo11m-seg.onnx")
            except Exception as _de:
                logger.warning("em_petri YOLO ONNX indirme/çözümleme uyarısı: %s", _de)
                yolo_path = os.path.join(project_root, "ai_hub", "inference_petri_dish", "yolo11m-seg.onnx")
            cfg = load_cabin_config(None)  # gömülü cabin_config_example.yaml
            # yolo_device="cpu" ŞART (headless — CUDA yok).
            warm = PetriCvPipeline(cfg, yolo_model_path=yolo_path, yolo_device="cpu")
            _ = warm.predictor  # BaggingRegressor ONNX (kendi fallback'i)
            try:
                warm.process_image(np.zeros((640, 640, 3), dtype=np.uint8))  # YOLO modelini ısıt
            except Exception:
                pass
            return {
                "cfg": cfg,
                "cls": PetriCvPipeline,
                "yolo": warm.yolo,
                "predictor": warm._predictor,
                "yolo_path": yolo_path,
            }

        cache = await asyncio.to_thread(_get_or_load_model, "em_petri_cv", _load_em_petri)
        # Her istekte hafif pipeline (taze intrinsics); önbellekli YOLO + predictor enjekte
        # (ağır modeller yeniden yüklenmez, yarış yok). yolo_device="cpu" ŞART.
        pl = cache["cls"](
            cache["cfg"], petri_diameter_cm=petri_diameter_cm, yolo_model_path=cache["yolo_path"], yolo_device="cpu"
        )
        pl.yolo = cache["yolo"]
        pl._predictor = cache["predictor"]

        result, ctx = await asyncio.to_thread(lambda: pl.process_image(img, achieved_B=achieved_B, duty_sum=duty_sum))

        # MAKULLİK REDDİ ≠ "tespit yok". `success=False` dalı 200 + status="no_detection" döner;
        # yanlış modülün fotoğrafı için bu SESSİZ bir başarısızlıktır (kullanıcı neden sonuç
        # alamadığını anlamaz, tekrar dener). 422 + NE yapması gerektiğini söyleyen Türkçe mesaj.
        # `_ai_fail` HTTPException'ı aynen geçirir → aşağıdaki except bunu 500'e çevirmez.
        if result.error == _PETRI_NOT_PLATE:
            raise HTTPException(status_code=422, detail=_petri_reject_message(result.plausibility))

        if result.success:
            panels = await asyncio.to_thread(lambda: pl.render_panels(ctx, result, lang="tr"))
            _, buffer = cv2.imencode('.jpg', panels["07_combined"])
            status = "success"
        else:
            _, buffer = cv2.imencode('.jpg', img)  # tespit yok → orijinali dön
            status = "no_detection"
        b64_image = base64.b64encode(buffer).decode('utf-8')

        from dataclasses import asdict

        wells = [asdict(w) for w in result.wells]
        return {
            "status": status,
            "image_base64": b64_image,
            "success": result.success,
            "error": result.error,
            "n_wells": result.n_wells,
            "n_cancer": result.n_cancer,
            "n_healthy": result.n_healthy,
            "method": result.method,
            "mm_per_px": round(result.mm_per_px, 4),
            "wells": wells,
            "timing_ms": result.timing_ms,
        }
    except Exception as e:
        logger.error(f"em_petri inference error: {e}", exc_info=True)
        raise _ai_fail("Petri analiz hatası", e)


@ai_router.post("/api/ai/rna/kidney")
async def analyze_kidney_rna(
    file: UploadFile = File(None), csv_base64: str = Form(None), _res=Depends(require_research)
):
    """Böbrek RNA-seq → KIRC sınıflandırma (MLP-medium ONNX).

    Girdi: CSV — satır=hasta, sütun=20531 gen (eğitim/TCGA sırasında), 1. sütun hasta ID.
    log2(x+1) → StandardScaler → SelectKBest top-1000 → MLP → KIRC/other + güven.
    Foto DEĞİL — bir sekans laboratuvarı çıktısı. Tümü <5MB → model EXE'ye gömülü.
    """
    try:
        if ai_service_enabled():
            return await delegate_infer("rna", file=file, csv_base64=csv_base64)
        if csv_base64:
            content = base64.b64decode(csv_base64)
        elif file:
            # Audit P2: sınırsız file.read() → GB dosya OOM/temp-disk dolumu (Starlette max_part_size
            # yalnız non-file form alanlarını sınırlar; file part sınır-kontrolsüz spool edilir). RNA CSV ~60MB.
            content = await file.read(60 * 1024 * 1024 + 1)
            if len(content) > 60 * 1024 * 1024:
                raise ValueError("CSV çok büyük (> 60 MB sınırı).")
        else:
            raise ValueError("CSV verisi bulunamadı.")

        import io as _io

        import pandas as _pd

        # event-loop-blok fix: 50MB'a kadar CSV × 20531 sütun pandas parse'ı CPU-yoğun → thread'e offload.
        def _parse_csv():
            return _pd.read_csv(_io.BytesIO(content), index_col=0)

        try:
            df = await asyncio.to_thread(_parse_csv)
        except Exception as pe:
            raise ValueError(f"CSV okunamadı ({pe}). Beklenen: satır=hasta, sütun=gen, 1. sütun hasta ID.")
        if df.shape[0] == 0:
            raise ValueError("CSV boş — hasta satırı yok.")

        def _load_kidney_rna():
            from ai_hub.inference_human_kidney_rna import KidneyRnaPredictor

            return KidneyRnaPredictor()

        predictor = await asyncio.to_thread(_get_or_load_model, "kidney_rna", _load_kidney_rna)

        if predictor.expected_cols and df.shape[1] != predictor.expected_cols:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Gen sütun sayısı uyuşmuyor: beklenen {predictor.expected_cols} "
                    f"(eğitim/TCGA sırası), gelen {df.shape[1]}. 1. sütun hasta ID olmalı."
                ),
            )

        predictions = await asyncio.to_thread(lambda: predictor.predict(df))
        return {
            "status": "success",
            "n_patients": len(predictions),
            "classes": predictor.classes,
            "predictions": predictions,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"kidney_rna inference error: {e}", exc_info=True)
        raise _ai_fail("RNA analiz hatası", e)


class KidneyDiseaseInput(BaseModel):
    # 14 sayısal klinik değer (eksik → None → preprocessor impute eder)
    age: float | None = None
    bp: float | None = None
    sg: float | None = None
    al: float | None = None
    su: float | None = None
    bgr: float | None = None
    bu: float | None = None
    sc: float | None = None
    sod: float | None = None
    pot: float | None = None
    hemo: float | None = None
    pcv: float | None = None
    wc: float | None = None
    rc: float | None = None
    # 10 kategorik (rbc/pc: normal/abnormal · pcc/ba: present/notpresent ·
    # htn/dm/cad/pe/ane: yes/no · appet: good/poor)
    rbc: str | None = None
    pc: str | None = None
    pcc: str | None = None
    ba: str | None = None
    htn: str | None = None
    dm: str | None = None
    cad: str | None = None
    appet: str | None = None
    pe: str | None = None
    ane: str | None = None


# CKD için ASGARİ girdi kuralı (2026-08-07, sahip bildirimi: "hiçbir veri girmeden analiz
# yaptığımda %78 çıkıyor"). Tüm alanlar opsiyonel olduğundan BOŞ istek de preprocessor'ün
# impute ettiği değerlerle modele gidiyor ve model eğitim setinin ÖN-OLASILIĞINI döndürüyor.
# Kullanıcı bunu "%78 hasta" diye okuyor — hastalık analizi ucunda (`/api/ai/disease`) aynı
# hata daha önce kapatılmıştı, bu uç atlanmıştı.
#
# KURAL (muhafazakâr, uydurma klinik eşik YOK):
#   1) En az `_CKD_MIN_ALAN` alan DOLU olmalı → "hiç veri girmeden sonuç" imkânsız.
#   2) Böbrek işleviyle DOĞRUDAN ilgili en az bir belirteç olmalı → aksi halde tahminde
#      renal sinyal yoktur, sayı yalnız demografiden türer.
_CKD_MIN_ALAN = 6
_CKD_CEKIRDEK = ("sc", "bu", "sg", "al", "hemo")  # kreatinin, üre, dansite, albümin, hemoglobin
_CKD_ETIKET = {
    "sc": "serum kreatinin",
    "bu": "kan üresi",
    "sg": "idrar dansitesi",
    "al": "albümin",
    "hemo": "hemoglobin",
}


@ai_router.post("/api/ai/disease/kidney")
async def analyze_kidney_disease(data: KidneyDiseaseInput, _res=Depends(require_research)):
    """İnsan Kronik Böbrek Hastalığı (UCI-CKD) sınıflandırma (ExtraTrees ONNX).

    24 klinik özellik (14 sayısal + 10 kategorik; eksikler impute) → preprocessor →
    ONNX → {prob_ckd, label(ckd/notckd)}. `/api/ai/disease` prefix'iyle auth-muaf.
    Model EXE'ye gömülü (<5MB); CPU. Foto/CSV DEĞİL — form girişi.

    ⚠️ ASGARİ GİRDİ ZORUNLU (2026-08-07): boş/yetersiz istek 422 ile reddedilir; bkz. _CKD_MIN_ALAN.
    """
    features = data.model_dump() if hasattr(data, "model_dump") else data.dict()
    dolu = [k for k, v in features.items() if v is not None and not (isinstance(v, str) and not v.strip())]
    cekirdek_dolu = [k for k in _CKD_CEKIRDEK if k in dolu]
    if len(dolu) < _CKD_MIN_ALAN or not cekirdek_dolu:
        eksik = ", ".join(_CKD_ETIKET[k] for k in _CKD_CEKIRDEK if k not in dolu)
        raise HTTPException(
            status_code=422,
            detail=(
                f"Güvenilir bir tahmin için yeterli klinik veri yok "
                f"({len(dolu)}/{len(features)} alan dolu; en az {_CKD_MIN_ALAN} gerekli). "
                f"Ayrıca böbrek işlevine dair en az bir değer girilmeli — eksik olanlar: {eksik}. "
                f"Boş formla üretilen sonuç, hastanın verisini değil modelin genel "
                f"ortalamasını yansıtır ve yanıltıcıdır."
            ),
        )
    try:
        if ai_service_enabled():
            return await delegate_json("kidney_disease", features)
        from ai_hub.inference_human_kidney_disease import predict_one

        result = await asyncio.to_thread(lambda: predict_one(features))
        return {
            "status": "success",
            "prob_ckd": result["prob_ckd"],
            "prob_pct": round(result["prob_ckd"] * 100, 1),
            "label": result["label"],
            "model": result.get("model"),
            # ŞEFFAFLIK: kaç alanın impute edildiğini klinisyen GÖRMELİ — 6/24 alanla üretilen
            # tahminle 22/24 alanla üretilen aynı güvenle sunulmamalı.
            "filled_fields": len(dolu),
            "total_fields": len(features),
            "imputed_fields": len(features) - len(dolu),
            "low_evidence": len(dolu) < 12,
        }
    except Exception as e:
        logger.error(f"kidney_disease inference error: {e}", exc_info=True)
        raise _ai_fail("Böbrek hastalığı analiz hatası", e)


@ai_router.post("/api/ai/sound/cat")
async def analyze_cat_sound(file: UploadFile = File(None), audio_base64: str = Form(None)):
    """Kedi Sesi Sınıflandırma (EfficientNet_Lite0 mel-spektrogram ONNX).

    Ses (mp3/wav/m4a/…) → ffmpeg 22050Hz mono WAV → librosa mel-spektrogram (mel+delta+
    delta²) → EfficientNet_Lite0 ONNX → 10 sınıf (Angry..Warning) + top-3. Foto/CSV/form
    DEĞİL — SES. `/api/ai/sound` prefix'iyle auth-muaf.
    """
    import tempfile

    tmp_in = None
    tmp_wav = None
    try:
        if ai_service_enabled():
            return await delegate_infer("sound", file=file, audio_base64=audio_base64)
        if audio_base64:
            content = base64.b64decode(audio_base64)
        elif file:
            # Audit P2: sınırsız file.read() → GB ses OOM/temp-disk dolumu; ffmpeg tüm girdiyi transcode
            # eder. Ses üst-sınırı ~25MB.
            content = await file.read(25 * 1024 * 1024 + 1)
            if len(content) > 25 * 1024 * 1024:
                raise ValueError("Ses dosyası çok büyük (> 25 MB sınırı).")
        else:
            raise ValueError("Ses verisi bulunamadı.")
        if len(content) < 200:
            raise ValueError(f"Ses verisi boş/çok küçük ({len(content)} bytes).")

        def _load_cat_sound():
            try:
                onnx = download_model_sync("ai_hub/inference_cat_sound/EfficientNet_Lite0.onnx")
            except Exception as _de:
                logger.warning("cat_sound ONNX indirme/çözümleme uyarısı: %s", _de)
                onnx = os.path.join(project_root, "ai_hub", "inference_cat_sound", "EfficientNet_Lite0.onnx")
            from ai_hub.inference_cat_sound import CatSoundClassifier

            # device="cpu" ŞART (headless); runtime onnx (torch YOK).
            return CatSoundClassifier(model_path=onnx, runtime="onnx", device="cpu")

        clf = await asyncio.to_thread(_get_or_load_model, "cat_sound", _load_cat_sound)

        # Ham sesi temp'e yaz → ffmpeg ile 22050Hz mono WAV'a çevir (herhangi format:
        # mp3/wav/m4a/aac/ogg... — kayıt Android m4a olabilir; librosa/soundfile m4a decode
        # etmez, ffmpeg üniversal). Sonra classifier librosa ile WAV'ı işler.
        tf = tempfile.NamedTemporaryFile(suffix=".bin", delete=False)
        tf.write(content)
        tf.close()
        tmp_in = tf.name
        tmp_wav = tmp_in + ".wav"
        import imageio_ffmpeg

        ff = imageio_ffmpeg.get_ffmpeg_exe()
        # Audit P2: ffmpeg sertleştir — -protocol_whitelist file (HLS/concat SSRF engelle), -nostdin,
        # -t 30 (girdi okuma süresi cap), -fs (çıktı WAV boyut cap) → uzun/kötücül medya disk-dolumu+SSRF keser.
        proc = await asyncio.to_thread(
            lambda: __import__('utils.gizli_surec', fromlist=['calistir']).calistir(
                [
                    ff,
                    "-nostdin",
                    "-protocol_whitelist",
                    "file",
                    "-t",
                    "30",
                    "-y",
                    "-i",
                    tmp_in,
                    "-ar",
                    "22050",
                    "-ac",
                    "1",
                    "-fs",
                    "30000000",
                    tmp_wav,
                ],
                capture_output=True,
                timeout=30,
            )
        )
        if proc.returncode != 0 or not os.path.exists(tmp_wav):
            raise ValueError("Ses çözümlenemedi (desteklenmeyen format?).")

        result = await asyncio.to_thread(lambda: clf.predict(tmp_wav, top_k=3))
        return {
            "status": "success",
            "top_1_class": result["top_1_class"],
            "top_1_prob": result["top_1_prob"],
            "top_k": result["top_k"],
            "probabilities": result["probabilities"],
        }
    except Exception as e:
        logger.error(f"cat_sound inference error: {e}", exc_info=True)
        raise _ai_fail("Ses analiz hatası", e)
    finally:
        for _p in (tmp_in, tmp_wav):
            if _p and os.path.exists(_p):
                try:
                    os.unlink(_p)
                except Exception:
                    pass


@ai_router.post("/api/ai/vision/kidney_ct")
async def analyze_kidney_ct(
    file: UploadFile = File(None), image_base64: str = Form(None), _res=Depends(require_research)
):
    """Böbrek CT Tespit (YOLOv8s ONNX, 3 sınıf: Kidney Stone / Kidney / Kidney Cyst).

    CT görüntüsü → YOLO detect → annotated görsel + tespit sayıları. `/vision/` auth-muaf.
    """
    try:
        if ai_service_enabled():
            return await delegate_infer("kidney_ct", file=file, image_base64=image_base64)
        img = await _decode_image(file, image_base64, label="kidney_ct")

        def _load_kidney_ct():
            try:
                onnx = download_model_sync("ai_hub/inference_human_kidney_ct/yolov8s.onnx")
            except Exception as _de:
                logger.warning("kidney_ct ONNX indirme/çözümleme uyarısı: %s", _de)
                onnx = os.path.join(project_root, "ai_hub", "inference_human_kidney_ct", "yolov8s.onnx")
            from ai_hub.inference_human_kidney_ct import KidneyCTDetector

            return KidneyCTDetector(model_path=onnx, backend="onnx", device="cpu")

        det = await asyncio.to_thread(_get_or_load_model, "kidney_ct", _load_kidney_ct)

        import tempfile

        tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
        tmp.close()
        cv2.imwrite(tmp.name, img)
        try:
            result = await asyncio.to_thread(lambda: det.predict(tmp.name))
            overlay = await asyncio.to_thread(lambda: det.draw_overlay(tmp.name, result))
        finally:
            try:
                os.unlink(tmp.name)
            except Exception:
                pass

        b64_image = _encode_jpg_b64(overlay)
        return {
            "status": "success",
            "image_base64": b64_image,
            "n_detections": result["n_detections"],
            "class_counts": result["class_counts"],
            "detections": result["detections"],
        }
    except Exception as e:
        logger.error(f"kidney_ct inference error: {e}", exc_info=True)
        raise _ai_fail("Böbrek CT analiz hatası", e)


@ai_router.post("/api/ai/vision/histopath")
async def analyze_histopath(
    file: UploadFile = File(None), image_base64: str = Form(None), _res=Depends(require_research)
):
    """Böbrek Histopatoloji Grade (V22-KMC-ClassicTrio ONNX, 5 sınıf grade0-4).

    Histoloji doku görüntüsü → 3-backbone ensemble → grade + olasılıklar (sınıflandırıcı,
    detektör değil → overlay yok). `/vision/` auth-muaf.
    """
    try:
        if ai_service_enabled():
            return await delegate_infer("histopath", file=file, image_base64=image_base64)
        img = await _decode_image(file, image_base64, label="histopath")

        def _load_histopath():
            try:
                onnx = download_model_sync("ai_hub/inference_renal_histopath_kmc/v22_kmc_classictrio_kmc.onnx")
            except Exception as _de:
                logger.warning("histopath ONNX indirme/çözümleme uyarısı: %s", _de)
                onnx = os.path.join(
                    project_root, "ai_hub", "inference_renal_histopath_kmc", "v22_kmc_classictrio_kmc.onnx"
                )
            from ai_hub.inference_renal_histopath_kmc import RenalHistopathClassifier

            return RenalHistopathClassifier(model_path=onnx, backend="onnx", device="cpu")

        clf = await asyncio.to_thread(_get_or_load_model, "histopath", _load_histopath)

        import tempfile

        tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
        tmp.close()
        cv2.imwrite(tmp.name, img)
        try:
            result = await asyncio.to_thread(lambda: clf.predict(tmp.name, top_k=5))
        finally:
            try:
                os.unlink(tmp.name)
            except Exception:
                pass

        return {
            "status": "success",
            "top_1_class": result["top_1_class"],
            "top_1_prob": result["top_1_prob"],
            "top_k": result["top_k"],
            "probabilities": result["probabilities"],
        }
    except Exception as e:
        logger.error(f"histopath inference error: {e}", exc_info=True)
        raise _ai_fail("Histopatoloji analiz hatası", e)


@ai_router.post("/api/ai/vision/cat_organ")
async def analyze_cat_organ(file: UploadFile = File(None), image_base64: str = Form(None)):
    """Kedi Organ 3B Lokalizasyon (YOLOv8m-seg + SuperAnimal FasterRCNN + RTMPose ONNX).

    Kedi görüntüsü → 10 organ 3B konumu (cm) + organ overlay. Sınıflandırıcı/detektör
    değil, lokalizasyon pipeline'ı. `/vision/` auth-muaf.
    """
    try:
        if ai_service_enabled():
            return await delegate_infer("cat_organ", file=file, image_base64=image_base64)
        img = await _decode_image(file, image_base64, label="cat_organ")

        def _load_cat_organ():
            from ai_hub.inference_cat_organ.catorgan_predictor import CatOrganPredictor

            return CatOrganPredictor(device="cpu")

        clf = await asyncio.to_thread(_get_or_load_model, "cat_organ", _load_cat_organ)

        import tempfile

        tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
        tmp.close()
        cv2.imwrite(tmp.name, img)
        try:
            result = await asyncio.to_thread(lambda: clf.predict(tmp.name, render=True))
        finally:
            try:
                os.unlink(tmp.name)
            except Exception:
                pass

        overlay = result.get("_overlay_bgr")
        image_b64 = None
        if overlay is not None:
            # Overlay orijinal çözünürlükte (ör. 4032px) → mobil için max 1280px'e küçült
            oh, ow = overlay.shape[:2]
            scale = min(1.0, 1280.0 / max(oh, ow))
            if scale < 1.0:
                overlay = cv2.resize(overlay, (int(ow * scale), int(oh * scale)), interpolation=cv2.INTER_AREA)
            _, buf = cv2.imencode('.jpg', overlay, [cv2.IMWRITE_JPEG_QUALITY, 85])
            image_b64 = base64.b64encode(buf).decode('utf-8')

        organs_dict = result.get("organs") or {}
        organs_list = [
            {
                "id": int(oid),
                "name": o.get("name"),
                "coord_3d_cm": o.get("coord_3d_cm"),
                "coord_cabin_cm": o.get("coord_cabin_cm"),
                "reliability": o.get("reliability"),
                # #49: kalibrasyon durumunu İLET → istemci/UI ölçülmüş (ArUco kalibreli) vs kanonik
                # şablon koordinatını ayırt edebilsin (aksi halde şablonu ölçülmüş sanabilir).
                "calibrated": o.get("calibrated"),
            }
            for oid, o in sorted(organs_dict.items(), key=lambda kv: int(kv[0]))
        ]

        return {
            "status": "success",
            "image_base64": image_b64,
            "n_organs": len(organs_list),
            "organs": organs_list,
            "pose_type": (result.get("pose_classifier") or {}).get("type"),
            "pnp_residual_px": round(float((result.get("pnp_fit") or {}).get("residual_px", 0.0)), 1),
        }
    except Exception as e:
        logger.error(f"cat_organ inference error: {e}", exc_info=True)
        raise _ai_fail("Kedi organ analiz hatası", e)
