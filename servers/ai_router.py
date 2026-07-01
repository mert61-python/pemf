from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import cv2
import numpy as np
import base64
import os
import sys
import logging

logger = logging.getLogger("ai_router")

import threading
import time
from utils.model_downloader import download_model_sync
from utils.stm32_protocol_limits import (
    normalize_ai_pro_duty_ratio,
    normalize_phase_deg,
)

ai_router = APIRouter()

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
        def _load():
            from utils.model_downloader import download_model_sync
            download_model_sync("ai_hub/cat_disease/XGBoost.pkl")
            from ai_hub.cat_disease.inference_cat_disease import CatDiseasePredictor
            return CatDiseasePredictor()

        predictor = _get_or_load_model("disease", _load)
        results = predictor.predict(
            data.age, data.weight, data.hr, data.temp, data.duration, data.symptom_indices
        )

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
        raise HTTPException(status_code=500, detail=f"Hastalık analizi hatası: {str(e)}")

from fastapi import Form

@ai_router.post("/api/ai/vision/landmark")
async def analyze_landmark(file: UploadFile = File(None), image_base64: str = Form(None), auto_adjust: bool = Form(False)):
    """YOLO Pose + FGS Ağrı Skoru + Otonom Biyogeribildirim"""
    try:
        if image_base64:
            content = base64.b64decode(image_base64)
        elif file:
            content = await file.read()
        else:
            raise ValueError("Görüntü verisi bulunamadı.")

        if len(content) > 20 * 1024 * 1024:  # DoS/bellek koruması: 20MB üst sınır
            raise HTTPException(status_code=413, detail="Görüntü çok büyük (en fazla 20MB).")
        logger.debug("Landmark: alinan dosya boyutu %d bytes", len(content))  # P2 audit: print() -> logger.debug
        
        nparr = np.frombuffer(content, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if img is None:
            logger.error(f"Landmark decode failed. Size: {len(content)}. Start: {content[:40]}")
            if content.strip().startswith(b"<!DOCTYPE html>") or content.strip().startswith(b"<html"):
                logger.error("Received HTML instead of image. Frontend might be sending index.html as a fallback!")
                raise ValueError("Görüntü yerine HTML (index.html) alındı. Lütfen React paketini kontrol edin.")
            raise ValueError(f"Geçersiz görüntü verisi. Alınan boyut: {len(content)} bytes.")

        def _load_landmark():
            from ultralytics import YOLO
            from utils.model_downloader import download_model_sync
            path = download_model_sync("ai_hub/cat_landmark/yolo26m-pose.onnx")
            return YOLO(path, task="pose")
        
        model = _get_or_load_model("landmark", _load_landmark)
        
        # Görüntüyü gecici dosyaya kaydet çünkü predict file path istiyor.
        import tempfile
        tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
        tmp.close()
        try:
            cv2.imwrite(tmp.name, img)
            results = model.predict(tmp.name, conf=0.25, device="cpu", verbose=False)
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

        _, buffer = cv2.imencode('.jpg', img)
        b64_image = base64.b64encode(buffer).decode('utf-8')

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
        if auto_adjust and not detected:
            hw_status = "skipped_no_detection"
        elif auto_adjust and detected:
            try:
                from servers.api_server import state, update_live_session_state, start_ai_session
                if state and state.hardware:
                    target_freq = 10.0 + (total * 5.0)
                    target_duty = 25.0 + (total * 3.0)
                    if target_duty > 50.0:
                        target_duty = 50.0
                    if target_freq > 100.0:
                        target_freq = 100.0

                    # Seansı _active_session'a yaz → süre-watchdog + emergency-stop AI'yı da kapsar
                    # (tek-kare auto_adjust artık sonsuza sürmez; süresi dolunca watchdog durdurur).
                    start_ai_session(target_freq, target_duty, 30, range(1, 9), "AI (Auto)")
                    state.hardware.start_all_coils(target_freq, target_duty, 0.0, 30)
                    # ESP 6-8'i de sür (audit #13, kullanıcı onaylı 8-bobin) — tek-atış publish.
                    try:
                        import servers.api_server as _api_esp
                        for _cid in (6, 7, 8):
                            _api_esp._mqtt_publish(f"pemf/coil/{_cid}/control", {
                                "command": "start",
                                "command_id": f"aiauto_{_cid}_{int(time.time() * 1000)}",
                                "freq": round(target_freq, 1),
                                "duty": round(target_duty, 1),
                                "phase": 0,
                                "duration": 30 * 60,
                            })
                    except Exception as _ee:
                        logger.warning("AI (Auto) ESP 6-8 publish hatasi: %s", _ee)
                    update_live_session_state(is_active=True, mode="AI (Auto)", freq=target_freq, intensity=target_duty, duration_sec=30 * 60)
                    hw_status = "updated"
                    hw_params = {"freq": target_freq, "duty": target_duty}
            except Exception as e:
                logger.error(f"Otonom biofeedback hatası: {e}")

        return JSONResponse(content={
            "status": "success",
            "image_base64": b64_image,
            "detected": detected,
            "fgs_total": total,
            "pain_level": pain_level,
            "raw_fgs": fgs_result if detected else None,
            "action_units": fgs_result.get("action_units") if detected else None,
            "hw_status": hw_status,
            "hw_params": hw_params
        })
    except Exception as e:
        logger.error(f"Landmark inference error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Landmark model hatası: {str(e)}")

# ── AI Pro durumu (modül seviyesi) ──
_ai_loop_active = False
_ai_thread = None
_ai_organ_id = 0
_ai_duration_min = 20
_ai_started_at = 0.0
# AI Pro freq sabit 1 Hz (eski PyQt DDS varsayılanı). Sabit; backend'de limit/clamp EKLEME.
_AI_PRO_FREQ_HZ = 1.0
# em_kedi modelinin sabit ekstra girdileri (eski camera_ai_thread ile birebir).
_AI_ACHIEVED_B = 0.001   # Tesla (1 mT)
_AI_DUTY_SUM = 1.5
_Z_SENSITIVITY = 1000.0
# El takibi kalibrasyonu: tetiklenince mevcut avuç genişliğini referans alır (z=0 düzlemi).
_ai_calibration = {
    "z_ref": 0.0,
    "calibrated": False,
    "trigger": False,            # bir sonraki tespit edilen karede referansı yakala
    "ref_palm_width_px": None,   # referans avuç genişliği (piksel)
}
_ORGAN_NAMES = {0: "Tüm Vücut", 1: "Mide", 2: "Böbrek", 3: "Karaciğer", 4: "Mesane", 5: "Pankreas", 6: "Bağırsak"}

# MediaPipe Hands tekil örneği (thread-safe lazy). em_kedi KediPredictor da _models içinde önbelleklenir.
_hands_lock = threading.Lock()
_hands = None


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


def _get_hands():
    """MediaPipe Hands tekil örneği (max_num_hands=1, conf 0.7) — eski PyQt ile birebir."""
    global _hands
    if _hands is not None:
        return _hands
    with _hands_lock:
        if _hands is not None:
            return _hands
        import mediapipe as mp
        _hands = mp.solutions.hands.Hands(
            max_num_hands=1,
            min_detection_confidence=0.7,
            min_tracking_confidence=0.7,
        )
        return _hands


def _track_hand_and_predict(frame):
    """
    Eski PyQt camera_ai_thread.py pipeline'ının birebir portu (PyQt sinyali yerine
    düz değer döndürür):
      - cv2.flip(frame, 1) (ayna)
      - MediaPipe Hands → işaret-parmağı ucu (landmark 8) → x_mm, y_mm
      - avuç genişliği (landmark 5↔17) → z_mm (kalibrasyona göre)
      - KediPredictor.predict(...) → D1..D7 (0..0.50 clip), P1..P7 (deg, bobin-1 referanslı), result_E

    Döner: (annotated_frame_bgr, detected, x_mm, y_mm, z_mm, D_list[7], P_list[7], e_field)
    D/P tespit yoksa sıfır listeleridir.
    """
    import mediapipe as mp

    frame = cv2.flip(frame, 1)
    h, w, _ = frame.shape
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    hands = _get_hands()
    results = hands.process(rgb)

    detected = False
    x_mm, y_mm, z_mm = 0.0, 0.0, 0.0
    D = [0.0] * 7
    P = [0.0] * 7
    e_field = 0.0

    if results.multi_hand_landmarks:
        hand_lms = results.multi_hand_landmarks[0]
        tip = hand_lms.landmark[8]
        p5 = hand_lms.landmark[5]
        p17 = hand_lms.landmark[17]

        p5_pix = (p5.x * w, p5.y * h)
        p17_pix = (p17.x * w, p17.y * h)
        current_palm_width = float(np.sqrt(
            (p5_pix[0] - p17_pix[0]) ** 2 + (p5_pix[1] - p17_pix[1]) ** 2
        ))

        # Kalibrasyon tetiği: mevcut avuç genişliğini z=0 referansı kabul et.
        if _ai_calibration.get("trigger"):
            _ai_calibration["ref_palm_width_px"] = current_palm_width
            _ai_calibration["calibrated"] = True
            _ai_calibration["trigger"] = False

        ref_pw = _ai_calibration.get("ref_palm_width_px")
        if _ai_calibration.get("calibrated") and ref_pw:
            ratio = current_palm_width / ref_pw
            z_raw = (1.0 - ratio) * _Z_SENSITIVITY
            z_mm = max(-300.0, min(300.0, z_raw))
        _ai_calibration["z_ref"] = round(z_mm, 1)

        x_mm = (tip.x * 600.0) - 300.0
        y_mm = ((1.0 - tip.y) * 600.0) - 300.0
        detected = True

        # Çizimler (parmak ucu + el iskeleti) — RGB üstüne çiz, sonra BGR'ye çevirip yayınla.
        cx, cy = int(tip.x * w), int(tip.y * h)
        cv2.circle(rgb, (cx, cy), 15, (255, 0, 0), -1)
        try:
            mp.solutions.drawing_utils.draw_landmarks(
                rgb, hand_lms, mp.solutions.hands.HAND_CONNECTIONS
            )
        except Exception:
            pass

        # ── em_kedi modeli: per-coil duty/phase ──
        try:
            predictor = _get_or_load_kedi()
            result = predictor.predict(
                x=x_mm,
                y=y_mm,
                z=z_mm,
                organ_id=_ai_organ_id,
                achieved_B=_AI_ACHIEVED_B,
                duty_sum=_AI_DUTY_SUM,
            )
            # Eski PyQt davranışı: duty 0..0.50 clip (modelin kendi politikası); EK clamp yok.
            D = np.clip([result.get(f"D{i}", 0.0) for i in range(1, 8)], 0.0, 0.50).tolist()
            P = [float(result.get(f"P{i}", 0.0)) for i in range(1, 8)]  # zaten bobin-1 referanslı
            e_field = float(max(0.0, result.get("result_E", 0.0)))
        except Exception as pred_err:
            logger.error("KediPredictor tahmin hatası: %s", pred_err)

    annotated = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    return annotated, detected, x_mm, y_mm, z_mm, D, P, e_field


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
            _api_esp._mqtt_publish(f"pemf/coil/{cid}/control", {
                "command": "start",
                "command_id": f"aipro_{cid}_{int(time.time() * 1000)}",
                "freq": round(_AI_PRO_FREQ_HZ, 1),
                "duty": duty_pct,
                "phase": phase_i,
                "duration": int(_ai_duration_min * 60),
            })
    except Exception as _ee:
        logger.warning("AI Pro ESP 6-7 publish hatası: %s", _ee)


def _build_ai_pro_percoil(D, P):
    """7-bobinlik perCoil yükü (gerçek per-coil AI duty/phase, yüzde). Bobin 8 yok (kapalı)."""
    out = []
    for idx in range(7):
        out.append({
            "id": idx + 1,
            "freq": round(_AI_PRO_FREQ_HZ, 1),
            "duty": round(normalize_ai_pro_duty_ratio(D[idx]) * 100.0, 1),
            "phase": round(normalize_phase_deg(P[idx]), 1),
        })
    return out


def _ai_pro_loop():
    global _ai_loop_active
    logger.info("AI Pro Closed-Loop (el-takibi + em_kedi) arkaplan görevi BAŞLADI.")
    cap = cv2.VideoCapture(0)

    if not cap.isOpened():
        logger.error("Kamera açılamadı (VideoCapture(0)). AI Pro durduruluyor.")
        cap.release()
        _ai_loop_active = False
        return

    # Modeli erkenden yükle — hata fırlarsa kamerayı BIRAK (VideoCapture sızıntısını önle, Audit P1).
    try:
        _get_or_load_kedi()
        _get_hands()
    except Exception as e:
        logger.error("AI Pro em_kedi/Hands yüklenemedi, kamera bırakılıyor: %s", e)
        cap.release()
        _ai_loop_active = False
        return

    while _ai_loop_active:
        start_time = time.time()
        # Dış STOP (acil-durdur / süre-watchdog / STM-disconnect / /session/stop) AI loop'u da durdursun.
        try:
            import servers.api_server as _api
            with _api._session_lock:
                _ext_active = bool(_api._active_session.get("is_active"))
            if not _ext_active:
                logger.info("AI Pro: seans dışarıdan durduruldu → loop sonlandırılıyor.")
                break
        except Exception:
            pass
        ret, frame = cap.read()
        if not ret:
            time.sleep(0.5)
            continue

        try:
            # ── El takibi + em_kedi (eski PyQt pipeline portu) ──
            annotated, detected, x_mm, y_mm, z_mm, D, P, e_field = _track_hand_and_predict(frame)

            from servers.api_server import state, update_live_session_state, _ws_broadcast_sync
            # YALNIZCA el tespit edilince donanım sür (gürültüde sürme yok). Bobin 1-7 PER-COIL.
            if detected:
                _drive_coils_ai_pro(D, P)

            remaining = max(0, int(_ai_duration_min * 60 - (time.time() - _ai_started_at))) if _ai_started_at else 0
            if _ai_started_at and remaining <= 0:
                _ai_loop_active = False  # süre doldu → otomatik durdur

            # Canlı seans göstergesi: bobin-1 AI duty'sini temsil değer olarak ver.
            rep_duty = round(normalize_ai_pro_duty_ratio(D[0]) * 100.0, 1) if detected else 0.0
            update_live_session_state(
                is_active=True,
                mode=f"AI Pro · {_ORGAN_NAMES.get(_ai_organ_id, '')}",
                freq=_AI_PRO_FREQ_HZ, intensity=rep_duty,
                remaining_min=remaining // 60, duration_sec=_ai_duration_min * 60,
            )

            # ── Telemetri yayını: api_server /ws (React buradan dinler) ──
            _, buffer = cv2.imencode('.jpg', annotated, [cv2.IMWRITE_JPEG_QUALITY, 50])
            b64_image = base64.b64encode(buffer).decode('utf-8')
            per_coil = _build_ai_pro_percoil(D, P)
            ws_data = {
                "imageBase64": b64_image,
                "detected": detected,
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
    # Loop bittiğinde (süre doldu / durduruldu / hata) bobinleri DONANIM düzeyinde durdur —
    # keep-alive ile sonsuza sürmesin (AI artık sürmüyor).
    try:
        import servers.api_server as _api2
        if _api2.state and _api2.state.hardware:
            _api2.state.hardware.stop_all_coils()
        # ESP 6-8'i de durdur (AI bunları da sürüyordu — audit #13).
        for _cid in (6, 7, 8):
            try:
                _api2._mqtt_publish(f"pemf/coil/{_cid}/control", {
                    "command": "stop",
                    "command_id": f"ai_stop_{_cid}_{int(time.time() * 1000)}",
                })
            except Exception:
                pass
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


@ai_router.post("/api/ai/pro/start")
def start_ai_pro(payload: AiProStartPayload = AiProStartPayload()):
    global _ai_loop_active, _ai_thread, _ai_organ_id, _ai_duration_min, _ai_started_at
    if _ai_loop_active:
        return {"status": "success", "message": "Already running"}

    _ai_organ_id = int(payload.organ_id)
    _ai_duration_min = max(1, int(payload.duration_minutes))
    _ai_started_at = time.time()
    _ai_loop_active = True
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
    return {"status": "success", "message": "AI Pro Closed-Loop Started",
            "organId": _ai_organ_id, "durationMin": _ai_duration_min}


@ai_router.post("/api/ai/pro/stop")
def stop_ai_pro():
    global _ai_loop_active
    _ai_loop_active = False

    from servers.api_server import state, update_live_session_state
    if state and state.hardware:
        state.hardware.stop_all_coils()
    update_live_session_state(is_active=False, mode="Sistem Hazır")
    return {"status": "success", "message": "AI Pro Closed-Loop Stopped"}


@ai_router.post("/api/ai/pro/organ")
def set_ai_pro_organ(payload: AiProStartPayload = AiProStartPayload()):
    """Hedef organı değiştir (loop çalışırken de geçerli)."""
    global _ai_organ_id
    _ai_organ_id = int(payload.organ_id)
    return {"status": "success", "organId": _ai_organ_id, "organName": _ORGAN_NAMES.get(_ai_organ_id, "")}


@ai_router.post("/api/ai/pro/calibrate")
def calibrate_ai_pro():
    """Z ekseni referansını kalibre et: bir sonraki el-tespitinde mevcut avuç genişliğini
    z=0 referansı olarak yakala (eski PyQt CameraAIThread.calibrate() ile birebir)."""
    _ai_calibration["trigger"] = True
    return {"status": "success", "calibrated": True}


@ai_router.get("/api/ai/pro/status")
def ai_pro_status():
    remaining = 0
    if _ai_loop_active and _ai_started_at:
        remaining = max(0, int(_ai_duration_min * 60 - (time.time() - _ai_started_at)))
    return {
        "active": _ai_loop_active,
        "organId": _ai_organ_id,
        "organName": _ORGAN_NAMES.get(_ai_organ_id, ""),
        "durationMin": _ai_duration_min,
        "remainingSec": remaining,
        "calibrated": _ai_calibration.get("calibrated", False),
    }


@ai_router.post("/api/ai/ai_pro/frame")
async def ai_pro_frame(file: UploadFile = File(None), image_base64: str = Form(None)):
    """
    MOBİL AI Pro karesi: telefon kamerasından gelen TEK kareyi işler.
    El takibi (MediaPipe Hands) + em_kedi KediPredictor → bobin 1-7 PER-COIL sürüş
    (loop ile AYNI donanım yolu) → annotated görüntü + per-coil/metrikleri döner.

    Organ/süre AKTİF AI Pro seansından okunur (web ile aynı state). FE bu çağrıdan
    ÖNCE /api/ai/pro/start çağırır (loop/coil-drive + süre-watchdog state'i kurulur);
    mobilde kareler bu endpoint'ten gelir, web'de sunucu kamerasından.
    """
    try:
        if image_base64:
            content = base64.b64decode(image_base64)
        elif file:
            content = await file.read()
        else:
            raise ValueError("Görüntü verisi bulunamadı.")

        if len(content) > 20 * 1024 * 1024:  # DoS/bellek koruması: 20MB üst sınır
            raise HTTPException(status_code=413, detail="Görüntü çok büyük (en fazla 20MB).")

        nparr = np.frombuffer(content, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            if content.strip().startswith(b"<!DOCTYPE html>") or content.strip().startswith(b"<html"):
                raise ValueError("Görüntü yerine HTML alındı. React paketini kontrol edin.")
            raise ValueError(f"Geçersiz görüntü verisi. Boyut: {len(content)} bytes.")

        # El takibi + em_kedi (loop ile birebir aynı pipeline).
        annotated, detected, x_mm, y_mm, z_mm, D, P, e_field = _track_hand_and_predict(img)

        # GERÇEK donanımı sür (loop ile aynı yol) — yalnız el tespit edilince. Bobin 1-7.
        if detected:
            _drive_coils_ai_pro(D, P)
            remaining = max(0, int(_ai_duration_min * 60 - (time.time() - _ai_started_at))) if _ai_started_at else 0
            try:
                from servers.api_server import update_live_session_state
                rep_duty = round(normalize_ai_pro_duty_ratio(D[0]) * 100.0, 1)
                update_live_session_state(
                    is_active=True,
                    mode=f"AI Pro · {_ORGAN_NAMES.get(_ai_organ_id, '')}",
                    freq=_AI_PRO_FREQ_HZ, intensity=rep_duty,
                    remaining_min=remaining // 60, duration_sec=_ai_duration_min * 60,
                )
            except Exception:
                logger.exception("AI Pro frame: live state update hatası")

        _, buffer = cv2.imencode('.jpg', annotated, [cv2.IMWRITE_JPEG_QUALITY, 60])
        b64_image = base64.b64encode(buffer).decode('utf-8')

        return JSONResponse(content={
            "status": "success",
            "image_base64": b64_image,
            "detected": detected,
            "perCoil": _build_ai_pro_percoil(D, P),
            "target": {"x": round(x_mm, 1), "y": round(y_mm, 1), "z": round(z_mm, 1)},
            "eField": round(e_field, 4),
            "organId": _ai_organ_id,
            "organName": _ORGAN_NAMES.get(_ai_organ_id, ""),
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"AI Pro frame error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"AI Pro kare hatası: {str(e)}")


@ai_router.post("/api/ai/vision/segmentation")
async def analyze_segmentation(file: UploadFile = File(None), image_base64: str = Form(None)):
    """YOLO Seg Kedi Segmentasyonu"""
    try:
        if image_base64:
            content = base64.b64decode(image_base64)
        elif file:
            content = await file.read()
        else:
            raise ValueError("Görüntü verisi bulunamadı.")
        nparr = np.frombuffer(content, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            logger.error(f"Segmentation decode failed. Size: {len(content)}. Start: {content[:40]}")
            if content.strip().startswith(b"<!DOCTYPE html>") or content.strip().startswith(b"<html"):
                raise ValueError("Görüntü yerine HTML alındı. React frontend'i güncelleyin.")
            raise ValueError(f"Geçersiz görüntü verisi. Boyut: {len(content)} bytes.")

        def _load_seg():
            from ultralytics import YOLO
            from utils.model_downloader import download_model_sync
            path = download_model_sync("ai_hub/cat_segmentation/yolov8m-seg.onnx")
            return YOLO(path, task="segment")
        
        model = _get_or_load_model("seg", _load_seg)
        
        import tempfile
        tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
        tmp.close()
        cv2.imwrite(tmp.name, img)
        # P2 audit 2026-06-28: tmp .jpg'yi HER durumda sil (predict/mask hata yolunda sizmasin → disk
        # dolar → _ensure_write_guardrail sensor/seans yazimini engelleyebilir). landmark deseni.
        try:
            results = model.predict(source=tmp.name, conf=0.25, iou=0.7, imgsz=640, device="cpu", verbose=False)
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
        
        _, buffer = cv2.imencode('.jpg', img)
        b64_image = base64.b64encode(buffer).decode('utf-8')
        
        return {
            "status": "success",
            "cat_count": cat_count,
            "image_base64": b64_image
        }
    except Exception as e:
        logger.error(f"Segmentation inference error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Segmentasyon hatası: {str(e)}")

@ai_router.post("/api/ai/vision/thermal")
async def analyze_thermal(file: UploadFile = File(None), image_base64: str = Form(None)):
    """GhostNetV2 Termal Analiz"""
    try:
        if image_base64:
            content = base64.b64decode(image_base64)
        elif file:
            content = await file.read()
        else:
            raise ValueError("Görüntü verisi bulunamadı.")
        nparr = np.frombuffer(content, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            logger.error(f"Thermal decode failed. Size: {len(content)}. Start: {content[:40]}")
            if content.strip().startswith(b"<!DOCTYPE html>") or content.strip().startswith(b"<html"):
                raise ValueError("Görüntü yerine HTML alındı.")
            raise ValueError(f"Geçersiz görüntü verisi. Boyut: {len(content)} bytes.")

        def _load_thermal():
            from ai_hub.cat_thermal.inference_cat_thermal import CatThermalPredictor
            return CatThermalPredictor(model_name="GhostNetV2")
        
        predictor = _get_or_load_model("thermal", _load_thermal)
        
        import tempfile
        tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
        tmp.close()
        cv2.imwrite(tmp.name, img)
        
        # P2 audit 2026-06-28: tmp .jpg'yi HER durumda sil (predict hata yolunda sizmasin → disk dolar).
        try:
            result = predictor.predict(tmp.name, threshold=0.5)
        finally:
            try:
                os.unlink(tmp.name)
            except Exception:
                pass
        
        _, buffer = cv2.imencode('.jpg', img)
        b64_image = base64.b64encode(buffer).decode('utf-8')
        
        return {
            "status": "success",
            "prediction": result,
            "image_base64": b64_image
        }
    except Exception as e:
        logger.error(f"Thermal inference error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Termal model hatası: {str(e)}")

@ai_router.post("/api/ai/vision/reticulocytes")
async def analyze_reticulocytes(file: UploadFile = File(None), image_base64: str = Form(None)):
    """YOLO Detect Retikülosit Sayımı"""
    try:
        if image_base64:
            content = base64.b64decode(image_base64)
        elif file:
            content = await file.read()
        else:
            raise ValueError("Görüntü verisi bulunamadı.")
        nparr = np.frombuffer(content, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            logger.error(f"Reticulocytes decode failed. Size: {len(content)}. Start: {content[:40]}")
            if content.strip().startswith(b"<!DOCTYPE html>") or content.strip().startswith(b"<html"):
                raise ValueError("Görüntü yerine HTML alındı.")
            raise ValueError(f"Geçersiz görüntü verisi. Boyut: {len(content)} bytes.")

        def _load_retic():
            from ultralytics import YOLO
            from utils.model_downloader import download_model_sync
            path = download_model_sync("ai_hub/feline_reticulocytes/yolov8s.onnx")
            return YOLO(path, task="detect")
        
        model = _get_or_load_model("retic", _load_retic)
        
        import tempfile
        tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
        tmp.close()
        cv2.imwrite(tmp.name, img)
        
        temp_project = os.path.join(tempfile.gettempdir(), "PEMF_API_AI")
        output_dir = os.path.join(temp_project, 'feline_reticulocytes', 'results')
        os.makedirs(output_dir, exist_ok=True)
        
        results = model.predict(
            source=tmp.name, conf=0.25, iou=0.7, imgsz=640, device='cpu', 
            save=True, project=os.path.join(temp_project, 'feline_reticulocytes'),
            name='results', exist_ok=True
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
            _, buffer = cv2.imencode('.jpg', img_res)
            b64_image = base64.b64encode(buffer).decode('utf-8')
        else:
            _, buffer = cv2.imencode('.jpg', img)
            b64_image = base64.b64encode(buffer).decode('utf-8')
            
        os.unlink(tmp.name)
        
        return {
            "status": "success",
            "counts": counts,
            "image_base64": b64_image
        }
    except Exception as e:
        logger.error(f"Reticulocytes inference error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Retikülosit model hatası: {str(e)}")
