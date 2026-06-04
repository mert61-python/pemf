from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel
import cv2
import numpy as np
import base64
import os
import sys
import logging

logger = logging.getLogger("ai_router")

import threading

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

@ai_router.post("/api/ai/vision/landmark")
async def analyze_landmark(file: UploadFile = File(...)):
    """YOLO Pose + FGS Ağrı Skoru"""
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
        
        return {
            "status": "success",
            "fgs_total": total,
            "pain_level": pain_level,
            "raw_fgs": fgs_result,
            "image_base64": b64_image
        }
    except Exception as e:
        logger.error(f"Landmark inference error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Landmark model hatası: {str(e)}")

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
