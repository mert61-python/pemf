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
        
        return {"status": "success", "results": formatted}
    except Exception as e:
        logger.error(f"Disease inference error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Hastalık analizi hatası: {str(e)}")

from fastapi import Form

@ai_router.post("/api/ai/vision/landmark")
async def analyze_landmark(file: UploadFile = File(...), auto_adjust: bool = Form(False)):
    """YOLO Pose + FGS Ağrı Skoru + Otonom Biyogeribildirim"""
    try:
        content = await file.read()
        print(f"DEBUG: Received file size: {len(content)} bytes")
        
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
        
        # Görüntüyü gecici dosyaya kaydet çünkü predict file path istiyor
        import tempfile
        tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
        tmp.close()
        cv2.imwrite(tmp.name, img)
        
        results = model.predict(tmp.name, conf=0.25, device="cpu", verbose=False)
        
        fgs_result = {}
        if results and len(results) > 0:
            r = results[0]
            if r.keypoints is not None and len(r.keypoints.xy) > 0 and r.boxes is not None and len(r.boxes) > 0:
                kp_xy = r.keypoints.xy[0].cpu().numpy()
                x1, y1, x2, y2 = r.boxes[0].xyxy[0].cpu().numpy()
                bw = max(x2 - x1, 1.0)
                bh = max(y2 - y1, 1.0)
                kp_norm = kp_xy.copy()
                kp_norm[:, 0] = (kp_norm[:, 0] - x1) / bw
                kp_norm[:, 1] = (kp_norm[:, 1] - y1) / bh
                
                from ai_hub.cat_landmark.inference_cat_landmark import compute_fgs
                fgs_result = compute_fgs(kp_norm)
                
                for pt in kp_xy:
                    px, py = int(pt[0]), int(pt[1])
                    if px > 0 or py > 0:
                        cv2.circle(img, (px, py), 4, (0, 255, 80), -1)

        os.unlink(tmp.name)
        
        _, buffer = cv2.imencode('.jpg', img)
        b64_image = base64.b64encode(buffer).decode('utf-8')
        
        total = fgs_result.get("fgs_total", fgs_result.get("total", 0))
        pain_level = fgs_result.get("pain_level", "Unknown")
        
        # Otonom Biofeedback
        hw_status = "idle"
        hw_params = {}
        if auto_adjust:
            try:
                from servers.api_server import state
                if state and state.hardware:
                    # Basit Algoritma: FGS skoru 0-10 arası, Frekansı 10'dan başlayıp skor başına 5Hz artırıyoruz.
                    target_freq = 10.0 + (total * 5.0)
                    target_duty = 25.0 + (total * 3.0) # Duty de artsın
                    if target_duty > 50.0:
                        target_duty = 50.0
                    if target_freq > 100.0:
                        target_freq = 100.0
                    
                    state.hardware.start_all_coils(target_freq, target_duty, 0.0, 30)
                    update_session_state(True, mode="AI Pro (Auto)", freq=target_freq, duty=target_duty, duration=30)
                    hw_status = "updated"
                    hw_params = {"freq": target_freq, "duty": target_duty}
            except Exception as e:
                logger.error(f"Otonom biofeedback hatası: {e}")

        return JSONResponse(content={
            "status": "success",
            "image_base64": b64_image,
            "fgs_total": total,
            "pain_level": pain_level,
            "hw_status": hw_status,
            "hw_params": hw_params
        })
    except Exception as e:
        logger.error(f"Landmark inference error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Landmark model hatası: {str(e)}")

def _ai_pro_loop():
    global _ai_loop_active
    logger.info("AI Pro Closed-Loop arkaplan görevi BAŞLADI.")
    cap = cv2.VideoCapture(0)
    
    if not cap.isOpened():
        logger.error("Kamera açılamadı (VideoCapture(0)). AI Pro durduruluyor.")
        _ai_loop_active = False
        return

    # Load Model
    from ultralytics import YOLO
    path = download_model_sync("ai_hub/cat_landmark/yolo26m-pose.onnx")
    model = YOLO(path, task="pose")

    while _ai_loop_active:
        start_time = time.time()
        ret, frame = cap.read()
        if not ret:
            time.sleep(0.5)
            continue
            
        try:
            # Predict
            results = model.predict(frame, conf=0.25, device="cpu", verbose=False)
            fgs_result = {}
            total = 0
            
            if results and len(results) > 0:
                r = results[0]
                if r.keypoints is not None and len(r.keypoints.xy) > 0 and r.boxes is not None and len(r.boxes) > 0:
                    kp_xy = r.keypoints.xy[0].cpu().numpy()
                    x1, y1, x2, y2 = r.boxes[0].xyxy[0].cpu().numpy()
                    bw = max(x2 - x1, 1.0)
                    bh = max(y2 - y1, 1.0)
                    kp_norm = kp_xy.copy()
                    kp_norm[:, 0] = (kp_norm[:, 0] - x1) / bw
                    kp_norm[:, 1] = (kp_norm[:, 1] - y1) / bh
                    
                    from ai_hub.cat_landmark.inference_cat_landmark import compute_fgs
                    fgs_result = compute_fgs(kp_norm)
                    total = fgs_result.get("fgs_total", fgs_result.get("total", 0))
                    
                    for pt in kp_xy:
                        px, py = int(pt[0]), int(pt[1])
                        if px > 0 or py > 0:
                            cv2.circle(frame, (px, py), 4, (0, 255, 80), -1)

            # Hardware Control (Biofeedback)
            from servers.api_server import state
            if state and state.hardware:
                target_freq = 10.0 + (total * 5.0)
                target_duty = 25.0 + (total * 3.0)
                target_duty = min(target_duty, 50.0)
                target_freq = min(target_freq, 100.0)
                state.hardware.start_all_coils(target_freq, target_duty, 0.0, 30)
                from servers.frontend_bridge import update_session_state
                update_session_state(True, mode="AI Pro (Auto)", freq=target_freq, duty=target_duty, duration=30)
            
            # Broadcast WS
            _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 50])
            b64_image = base64.b64encode(buffer).decode('utf-8')
            
            ws_data = {
                "imageBase64": b64_image,
                "fgs_total": total,
                "fgs_raw": fgs_result
            }
            try:
                import servers.frontend_bridge as fb
                fb._broadcast({"type": "ai_vision", "data": ws_data})
            except Exception as wse:
                logger.error(f"WS broadcast error in AI loop: {wse}")
            
        except Exception as e:
            logger.error(f"AI Loop iteration error: {e}")
            
        elapsed = time.time() - start_time
        sleep_time = max(0.1, 1.0 - elapsed)
        time.sleep(sleep_time)

    cap.release()
    logger.info("AI Pro Closed-Loop arkaplan görevi DURDU.")

@ai_router.post("/api/ai/pro/start")
def start_ai_pro():
    global _ai_loop_active, _ai_thread
    if _ai_loop_active:
        return {"status": "success", "message": "Already running"}
        
    _ai_loop_active = True
    import threading
    _ai_thread = threading.Thread(target=_ai_pro_loop, daemon=True)
    _ai_thread.start()
    return {"status": "success", "message": "AI Pro Closed-Loop Started"}

@ai_router.post("/api/ai/pro/stop")
def stop_ai_pro():
    global _ai_loop_active
    _ai_loop_active = False
    
    from servers.api_server import state
    if state and state.hardware:
        state.hardware.stop_all_coils()
        from servers.frontend_bridge import update_session_state
        update_session_state(False, mode="Manuel")
        
    return {"status": "success", "message": "AI Pro Closed-Loop Stopped"}


@ai_router.post("/api/ai/vision/segmentation")
async def analyze_segmentation(file: UploadFile = File(...)):
    """YOLO Seg Kedi Segmentasyonu"""
    try:
        content = await file.read()
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

        os.unlink(tmp.name)
        
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
async def analyze_thermal(file: UploadFile = File(...)):
    """GhostNetV2 Termal Analiz"""
    try:
        content = await file.read()
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
        
        result = predictor.predict(tmp.name, threshold=0.5)
        os.unlink(tmp.name)
        
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
async def analyze_reticulocytes(file: UploadFile = File(...)):
    """YOLO Detect Retikülosit Sayımı"""
    try:
        content = await file.read()
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
