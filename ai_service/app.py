"""
PEMF AI Servisi (GPU) — mikroservis.
  • /health          → CUDA/onnxruntime sağlayıcıları + GPU
  • /models          → /models altındaki .onnx dosyaları  |  /infer/models → bağlı uçlar
  • /benchmark       → seçilen modeli CUDA ile yükle, sentetik girdiyle süre ölç
  • /infer/histopath → (görüntü)  Böbrek histopatoloji grade — GPU
  • /infer/sound      → (ses)      Kedi sesi sınıflandırma — GPU (mel-spektrogram CPU)
ai_hub predictor'ları GERÇEK inference; ağırlıklar /models mount. torch YOK (saf-ONNX).
"""

import asyncio
import base64
import glob
import os
import shutil
import subprocess
import tempfile
import time
from typing import Optional

import numpy as np
import onnxruntime as ort
from fastapi import Body, FastAPI, File, Form, Query, UploadFile
from fastapi.responses import JSONResponse

from ai_service import predictors
from ai_service.gpu import gpu_ok as _gpu_ok
from ai_service.gpu import onnx_providers as _providers
from ai_service.gpu import yolo_device as _yolo_device

MODELS_DIR = os.environ.get("PEMF_AI_MODELS_DIR", "/models")
app = FastAPI(title="PEMF AI Service (GPU)", version="0.3.0")

# GPU tespiti (_gpu_ok / _yolo_device / _providers) → ai_service.gpu (tek nokta; üstte import edildi).

# ── Auth-muaf /infer uçları için DoS sertleştirme (upload boyut + eşzamanlılık) ──────────────
# Bu servisin /infer uçları kimlik-muaf (core→GPU dahili çağrı). Sınır yoksa: (1) dev yükler
# belleği/diski doldurur (_save_temp), (2) sınırsız paralel ağır GPU inference GPU/bellek/loop'u
# tüketip AI Pro kapalı-döngü sürüşünü geciktirir. Aşağıdaki middleware her ikisini de kapatır.
MAX_UPLOAD_BYTES = int(os.environ.get("PEMF_AI_MAX_UPLOAD_MB", "100")) * 1024 * 1024
_MAX_CONCURRENT_INFER = max(1, int(os.environ.get("PEMF_AI_MAX_CONCURRENT", "4")))
_infer_sem = asyncio.Semaphore(_MAX_CONCURRENT_INFER)


@app.middleware("http")
async def _guard_infer(request, call_next):
    """Yalnız ağır /infer + /benchmark uçlarını sınırla; /health, /models vb. serbest."""
    path = request.url.path
    if not (path.startswith("/infer/") or path == "/benchmark"):
        return await call_next(request)
    # (1) Boyut kapağı: Content-Length aşarsa gövdeyi OKUMADAN 413 döndür (bellek/disk DoS).
    cl = request.headers.get("content-length")
    if cl:
        try:
            if int(cl) > MAX_UPLOAD_BYTES:
                return JSONResponse(
                    {"error": f"Yük çok büyük (max {MAX_UPLOAD_BYTES // (1024 * 1024)} MB)"},
                    status_code=413,
                )
        except ValueError:
            pass
    # (2) Eşzamanlılık sınırı: asyncio.Semaphore event-loop'u BLOKLAMAZ (await ile bekler),
    # aynı anda en çok _MAX_CONCURRENT_INFER ağır inference koşar → GPU/bellek/loop korunur.
    async with _infer_sem:
        return await call_next(request)


def _read_bgr(data: bytes):
    import cv2

    arr = np.frombuffer(data, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("görüntü çözülemedi")
    return img


def _jpg_b64(bgr) -> str:
    import cv2

    ok, buf = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return base64.b64encode(buf).decode("utf-8")


def _err500(exc, code: int = 500):
    """Audit P3: ham istisna metni (sunucu dosya yolları/iç detay) istemciye SIZMASIN — jenerik mesaj
    + correlation-id döndür, tam istisnayı yalnız sunucu log'una yaz (keşif/bilgi-ifşası engellenir)."""
    import logging as _lg
    import uuid as _uuid

    eid = _uuid.uuid4().hex[:12]
    _lg.getLogger("ai_service").error("infer hata [%s]: %s: %s", eid, type(exc).__name__, exc)
    return JSONResponse({"error": "Sunucu hatasi (loglandi)", "error_id": eid}, status_code=code)


# ── yardımcılar ──────────────────────────────────────────────────────────────
def _list_onnx():
    out = []
    for p in glob.glob(os.path.join(MODELS_DIR, "**", "*.onnx"), recursive=True):
        try:
            out.append({"path": os.path.relpath(p, MODELS_DIR), "mb": round(os.path.getsize(p) / 1048576, 1)})
        except OSError:
            pass
    return sorted(out, key=lambda x: x["mb"])


def _synthetic_input(sess):
    inp = sess.get_inputs()[0]
    shape = [d if isinstance(d, int) and d > 0 else (1 if i == 0 else 224) for i, d in enumerate(inp.shape)]
    tmap = {
        "tensor(float)": np.float32,
        "tensor(float16)": np.float16,
        "tensor(int64)": np.int64,
        "tensor(int32)": np.int32,
        "tensor(uint8)": np.uint8,
        "tensor(double)": np.float64,
    }
    dt = tmap.get(inp.type, np.float32)
    arr = np.random.rand(*shape).astype(dt) if np.issubdtype(dt, np.floating) else np.zeros(shape, dtype=dt)
    return inp.name, arr


def _save_temp(data: bytes, suffix: str) -> str:
    # İkincil boyut-kapağı: Content-Length'siz (chunked) istekte middleware'in header-kontrolü
    # devreye girmez → burada da diske yazmadan reddet (disk-dolumu DoS savunma-derinliği).
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError(f"yük çok büyük (max {MAX_UPLOAD_BYTES // (1024 * 1024)} MB)")
    tf = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    tf.write(data)
    tf.close()
    return tf.name


# ── sağlık / keşif ───────────────────────────────────────────────────────────
@app.get("/health")
def health():
    avail = ort.get_available_providers()
    gpu = _gpu_ok()
    info = {
        "status": "online",
        "service": "pemf-ai",
        "onnxruntime": ort.__version__,
        "onnx_providers": avail,
        "cuda": "CUDAExecutionProvider" in avail,
        "gpu_usable": gpu,
        "device": "gpu" if gpu else "cpu",
        "models_dir": MODELS_DIR,
        "onnx_count": len(_list_onnx()),
        "infer_endpoints": sorted(predictors.REGISTRY.keys()),
        "loaded": predictors.loaded(),
    }
    try:
        import torch

        info["torch"] = torch.__version__
        info["torch_cuda"] = torch.cuda.is_available()
    except Exception as e:
        info["torch"] = f"yok ({type(e).__name__})"
    return info


@app.get("/models")
def models():
    return {"models_dir": MODELS_DIR, "onnx": _list_onnx()}


@app.get("/infer/models")
def infer_models():
    return {k: {"kind": v["kind"], "title": v["title"], "onnx": v["onnx"]} for k, v in predictors.REGISTRY.items()}


@app.get("/benchmark")
def benchmark(model: Optional[str] = Query(None), runs: int = Query(20, ge=1, le=200)):
    lst = _list_onnx()
    if not lst:
        return JSONResponse({"error": f"{MODELS_DIR} altında .onnx yok"}, status_code=404)
    rel = model or lst[0]["path"]
    # Audit P3: path-traversal engelle — rel MODELS_DIR ALTINDA olmalı ('../..' / mutlak yol reddet).
    full = os.path.realpath(os.path.join(MODELS_DIR, rel))
    _root = os.path.realpath(MODELS_DIR)
    if not (full == _root or full.startswith(_root + os.sep)) or not os.path.exists(full):
        return JSONResponse({"error": "model yok"}, status_code=404)
    provs = _providers(True)
    try:
        t0 = time.time()
        sess = ort.InferenceSession(full, providers=provs)
        load_ms = (time.time() - t0) * 1000
    except Exception:
        return JSONResponse({"error": "model yuklenemedi"}, status_code=400)
    used = sess.get_providers()
    name, arr = _synthetic_input(sess)
    sess.run(None, {name: arr})
    t1 = time.time()
    for _ in range(runs):
        sess.run(None, {name: arr})
    return {
        "model": rel,
        "active_providers": used,
        "ran_on_gpu": bool(used) and used[0] == "CUDAExecutionProvider",
        "load_ms": round(load_ms, 1),
        "inference_ms_avg": round((time.time() - t1) / runs * 1000, 2),
        "runs": runs,
    }


# ── GERÇEK inference uçları ──────────────────────────────────────────────────
@app.post("/infer/histopath")
def infer_histopath(file: UploadFile = File(...)):
    """Böbrek histopatoloji doku görüntüsü → grade0-4 + olasılıklar (GPU)."""
    tmp = None
    try:
        data = file.file.read()
        if len(data) < 200:
            return JSONResponse({"error": "görüntü boş/çok küçük"}, status_code=400)
        clf = predictors.get("histopath")
        tmp = _save_temp(data, ".jpg")
        t0 = time.time()
        result = clf.predict(tmp, top_k=5)
        return {
            "status": "success",
            "device": getattr(clf, "device", "?"),
            "inference_ms": round((time.time() - t0) * 1000, 1),
            "top_1_class": result["top_1_class"],
            "top_1_prob": result["top_1_prob"],
            "top_k": result["top_k"],
            "probabilities": result.get("probabilities"),
        }
    except Exception as e:
        return _err500(e)
    finally:
        if tmp and os.path.exists(tmp):
            os.unlink(tmp)


@app.post("/infer/sound")
def infer_sound(file: UploadFile = File(...)):
    """Kedi sesi (mp3/wav/m4a) → ffmpeg 22050 mono WAV → 10 sınıf + top-3 (ONNX GPU)."""
    tmp_in = tmp_wav = None
    try:
        data = file.file.read()
        if len(data) < 200:
            return JSONResponse({"error": "ses boş/çok küçük"}, status_code=400)
        clf = predictors.get("sound")
        tmp_in = _save_temp(data, ".bin")
        tmp_wav = tmp_in + ".wav"
        ff = shutil.which("ffmpeg") or "ffmpeg"
        # Audit P2: ffmpeg sertleştir (SSRF/disk-dolumu) — -protocol_whitelist file, -nostdin, -t 30, -fs cap.
        proc = subprocess.run(
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
        if proc.returncode != 0 or not os.path.exists(tmp_wav):
            return JSONResponse({"error": "ses çözümlenemedi (ffmpeg)"}, status_code=400)
        t0 = time.time()
        result = clf.predict(tmp_wav, top_k=3)
        return {
            "status": "success",
            "device": getattr(clf, "device", "?"),
            "inference_ms": round((time.time() - t0) * 1000, 1),
            "top_1_class": result["top_1_class"],
            "top_1_prob": result["top_1_prob"],
            "top_k": result["top_k"],
            "probabilities": result.get("probabilities"),
        }
    except Exception as e:
        return _err500(e)
    finally:
        for p in (tmp_in, tmp_wav):
            if p and os.path.exists(p):
                os.unlink(p)


# ── YOLO/görüntü uçları (Faz 2b — GPU via ultralytics device=0 → onnxruntime CUDA) ──
@app.post("/infer/kidney_ct")
def infer_kidney_ct(file: UploadFile = File(...)):
    """Böbrek CT → YOLOv8s tespit (taş/kist/normal) + annotated görsel (GPU)."""
    tmp = None
    try:
        data = file.file.read()
        if len(data) < 200:
            return JSONResponse({"error": "görüntü boş/çok küçük"}, status_code=400)
        det = predictors.get("kidney_ct")
        tmp = _save_temp(data, ".jpg")
        t0 = time.time()
        result = det.predict(tmp)
        overlay = det.draw_overlay(tmp, result)
        return {
            "status": "success",
            "device": _yolo_device(),
            "inference_ms": round((time.time() - t0) * 1000, 1),
            "n_detections": result.get("n_detections"),
            "class_counts": result.get("class_counts"),
            "detections": result.get("detections"),
            "image_base64": _jpg_b64(overlay),
        }
    except Exception as e:
        return _err500(e)
    finally:
        if tmp and os.path.exists(tmp):
            os.unlink(tmp)


@app.post("/infer/segmentation")
def infer_segmentation(file: UploadFile = File(...)):
    """Kedi segmentasyon → YOLOv8m-seg maske overlay + kedi sayısı (GPU)."""
    import cv2

    tmp = None
    try:
        data = file.file.read()
        if len(data) < 200:
            return JSONResponse({"error": "görüntü boş/çok küçük"}, status_code=400)
        img = _read_bgr(data)
        model = predictors.get("segmentation")
        tmp = _save_temp(data, ".jpg")
        t0 = time.time()
        results = model.predict(source=tmp, conf=0.25, iou=0.7, imgsz=640, device=_yolo_device(), verbose=False)
        r = results[0]
        cat_count = len(r.boxes) if r.boxes is not None else 0
        if r.masks is not None and len(r.masks) > 0:
            for mask_data in r.masks.data:
                mask_np = mask_data.cpu().numpy()
                mask_rs = cv2.resize(mask_np, (img.shape[1], img.shape[0]), interpolation=cv2.INTER_NEAREST)
                colored = np.zeros_like(img)
                colored[:, :, 1] = 160
                blend = cv2.addWeighted(img, 0.55, colored, 0.45, 0)
                img = np.where(mask_rs[:, :, None] > 0.5, blend, img).astype(np.uint8)
        return {
            "status": "success",
            "device": _yolo_device(),
            "inference_ms": round((time.time() - t0) * 1000, 1),
            "cat_count": int(cat_count),
            "image_base64": _jpg_b64(img),
        }
    except Exception as e:
        return _err500(e)
    finally:
        if tmp and os.path.exists(tmp):
            os.unlink(tmp)


@app.post("/infer/landmark")
def infer_landmark(file: UploadFile = File(...)):
    """Kedi yüzü → YOLO-pose keypoint → FGS ağrı skoru + keypoint overlay (GPU).

    Tespit yoksa yanlış-güvence verme: fgs_total=null, detected=false.
    """
    import cv2

    tmp = None
    try:
        data = file.file.read()
        if len(data) < 200:
            return JSONResponse({"error": "görüntü boş/çok küçük"}, status_code=400)
        img = _read_bgr(data)
        model = predictors.get("landmark")
        tmp = _save_temp(data, ".jpg")
        t0 = time.time()
        results = model.predict(tmp, conf=0.25, device=_yolo_device(), verbose=False)
        infer_ms = round((time.time() - t0) * 1000, 1)

        fgs, detected = {}, False
        if results and len(results) > 0:
            r = results[0]
            if r.keypoints is not None and len(r.keypoints.xy) > 0 and r.boxes is not None and len(r.boxes) > 0:
                kp_xy = r.keypoints.xy[0].cpu().numpy()
                kp_conf = None
                try:
                    if r.keypoints.conf is not None:
                        kp_conf = r.keypoints.conf[0].cpu().numpy()
                except Exception:
                    kp_conf = None
                x1, y1, x2, y2 = r.boxes[0].xyxy[0].cpu().numpy()
                bw, bh = max(x2 - x1, 1.0), max(y2 - y1, 1.0)
                kp_norm = kp_xy.copy()
                kp_norm[:, 0] = (kp_norm[:, 0] - x1) / bw
                kp_norm[:, 1] = (kp_norm[:, 1] - y1) / bh
                from ai_hub.cat_landmark.inference_cat_landmark import compute_fgs

                fgs = compute_fgs(kp_norm)
                _ft = fgs.get("fgs_total", -1)
                _valid = int(np.count_nonzero((kp_xy[:, 0] > 0) | (kp_xy[:, 1] > 0)))
                _conf_ok = True if kp_conf is None else (float(np.mean(kp_conf)) >= 0.20)
                if _ft is not None and _ft >= 0 and _valid >= 20 and _conf_ok:
                    detected = True
                    for pt in kp_xy:
                        px, py = int(pt[0]), int(pt[1])
                        if px > 0 or py > 0:
                            cv2.circle(img, (px, py), 4, (0, 255, 80), -1)

        return {
            "status": "success",
            "device": _yolo_device(),
            "inference_ms": infer_ms,
            "detected": detected,
            "fgs_total": (fgs.get("fgs_total") if detected else None),
            "pain_level": (fgs.get("pain_level", "Unknown") if detected else "Kedi yüzü tespit edilemedi"),
            "image_base64": _jpg_b64(img),
        }
    except Exception as e:
        return _err500(e)
    finally:
        if tmp and os.path.exists(tmp):
            os.unlink(tmp)


# ── Faz 2c: termal (görüntü, GPU), cat_organ (görüntü 3B, GPU) ──
@app.post("/infer/thermal")
def infer_thermal(file: UploadFile = File(...)):
    """Termal görüntü → sağlık sınıflandırma (GhostNetV2 ONNX, GPU)."""
    tmp = None
    try:
        data = file.file.read()
        if len(data) < 200:
            return JSONResponse({"error": "görüntü boş/çok küçük"}, status_code=400)
        clf = predictors.get("thermal")
        tmp = _save_temp(data, ".jpg")
        t0 = time.time()
        result = clf.predict(tmp, threshold=0.5)
        dev = clf.session.get_providers()[0].replace("ExecutionProvider", "").lower()
        return {"status": "success", "device": dev, "inference_ms": round((time.time() - t0) * 1000, 1), **result}
    except Exception as e:
        return _err500(e)
    finally:
        if tmp and os.path.exists(tmp):
            os.unlink(tmp)


@app.post("/infer/cat_organ")
def infer_cat_organ(file: UploadFile = File(...), target_oid: int = Form(None)):
    """Kedi görüntüsü → 10 organ 3B lokalizasyon (3 ONNX) + overlay (GPU).
    target_oid (ops): AI Pro seçili organı → overlay o organa odaklanır (CPU-parite; 0/None=Tüm Vücut)."""
    import cv2

    tmp = None
    try:
        data = file.file.read()
        if len(data) < 200:
            return JSONResponse({"error": "görüntü boş/çok küçük"}, status_code=400)
        clf = predictors.get("cat_organ")
        tmp = _save_temp(data, ".jpg")
        t0 = time.time()
        _toid = (int(target_oid) or None) if target_oid is not None else None
        result = clf.predict(tmp, render=True, target_oid=_toid)
        infer_ms = round((time.time() - t0) * 1000, 1)
        overlay = result.get("_overlay_bgr")
        image_b64 = None
        if overlay is not None:
            oh, ow = overlay.shape[:2]
            scale = min(1.0, 1280.0 / max(oh, ow))
            if scale < 1.0:
                overlay = cv2.resize(overlay, (int(ow * scale), int(oh * scale)), interpolation=cv2.INTER_AREA)
            image_b64 = _jpg_b64(overlay)
        organs = result.get("organs") or {}
        organs_list = [
            {
                "id": int(oid),
                "name": o.get("name"),
                "coord_3d_cm": o.get("coord_3d_cm"),
                "coord_cabin_cm": o.get("coord_cabin_cm"),
                "reliability": o.get("reliability"),
            }
            for oid, o in sorted(organs.items(), key=lambda kv: int(kv[0]))
        ]
        return {
            "status": "success",
            "device": getattr(clf, "device", "?"),
            "inference_ms": infer_ms,
            "n_organs": len(organs_list),
            "organs": organs_list,
            "pose_type": (result.get("pose_classifier") or {}).get("type"),
            "image_base64": image_b64,
        }
    except Exception as e:
        return _err500(e)
    finally:
        if tmp and os.path.exists(tmp):
            os.unlink(tmp)


# ── Faz 2c: JSON girdili uçlar (küçük/CPU modeller) ──
@app.post("/infer/disease")
def infer_disease(payload: dict = Body(...)):
    """Kedi hastalık (XGBoost) — JSON: age,weight,hr,temp,duration,symptom_indices."""
    try:
        clf = predictors.get("disease")
        t0 = time.time()
        results = clf.predict(
            payload.get("age", 0.0),
            payload.get("weight", 0.0),
            payload.get("hr", 0.0),
            payload.get("temp", 0.0),
            payload.get("duration", 0.0),
            payload.get("symptom_indices", []),
        )
        formatted = [{"disease": d, "probability": p} for d, p in results]
        top_p = max((float(p) for _, p in results), default=0.0)
        return {
            "status": "success",
            "device": "cpu",
            "inference_ms": round((time.time() - t0) * 1000, 1),
            "results": formatted,
            "top_probability": round(top_p, 3),
            "low_confidence": top_p < 0.40,
        }
    except Exception as e:
        return _err500(e)


@app.post("/infer/kidney_disease")
def infer_kidney_disease(payload: dict = Body(...)):
    """İnsan KBH (ExtraTrees ONNX) — JSON: 24 klinik özellik."""
    try:
        from ai_hub.inference_human_kidney_disease import predict_one

        t0 = time.time()
        r = predict_one(payload)
        return {
            "status": "success",
            "device": "cpu",
            "inference_ms": round((time.time() - t0) * 1000, 1),
            "prob_ckd": r["prob_ckd"],
            "prob_pct": round(r["prob_ckd"] * 100, 1),
            "label": r["label"],
            "model": r.get("model"),
        }
    except Exception as e:
        return _err500(e)


@app.post("/infer/rna")
def infer_rna(file: UploadFile = File(...)):
    """Böbrek RNA-seq CSV (satır=hasta, sütun=gen) → KIRC sınıflandırma (MLP ONNX)."""
    try:
        import io as _io

        import pandas as pd

        data = file.file.read()
        if len(data) < 50:
            return JSONResponse({"error": "CSV boş/çok küçük"}, status_code=400)
        df = pd.read_csv(_io.BytesIO(data), index_col=0)
        if df.shape[0] == 0:
            return JSONResponse({"error": "CSV boş — hasta satırı yok"}, status_code=400)
        pred = predictors.get("kidney_rna")
        if getattr(pred, "expected_cols", None) and df.shape[1] != pred.expected_cols:
            return JSONResponse(
                {"error": f"gen sütun sayısı uyuşmuyor: beklenen {pred.expected_cols}, gelen {df.shape[1]}"},
                status_code=400,
            )
        t0 = time.time()
        predictions = pred.predict(df)
        return {
            "status": "success",
            "device": "cpu",
            "inference_ms": round((time.time() - t0) * 1000, 1),
            "n_patients": len(predictions),
            "classes": pred.classes,
            "predictions": predictions,
        }
    except Exception as e:
        return _err500(e)


# ── Faz kalan: reticulocytes (YOLO detect) + em_fantom/em_petri (kabin-CV pipeline) ──
@app.post("/infer/reticulocytes")
def infer_reticulocytes(file: UploadFile = File(...)):
    """Kan mikroskop görüntüsü → YOLOv8s retikülosit tespiti + sayım + overlay (GPU)."""
    tmp = None
    try:
        data = file.file.read()
        if len(data) < 200:
            return JSONResponse({"error": "görüntü boş/çok küçük"}, status_code=400)
        model = predictors.get("reticulocytes")
        tmp = _save_temp(data, ".jpg")
        t0 = time.time()
        results = model.predict(source=tmp, conf=0.25, iou=0.7, imgsz=640, device=_yolo_device(), verbose=False)
        r = results[0]
        n = len(r.boxes) if r.boxes is not None else 0
        return {
            "status": "success",
            "device": _yolo_device(),
            "inference_ms": round((time.time() - t0) * 1000, 1),
            "n_detections": int(n),
            "image_base64": _jpg_b64(r.plot()),
        }
    except Exception as e:
        return _err500(e)
    finally:
        if tmp and os.path.exists(tmp):
            os.unlink(tmp)


def _prov_dev(session):
    try:
        return session.get_providers()[0].replace("ExecutionProvider", "").lower()
    except Exception:
        return "?"


@app.post("/infer/em_fantom")
def infer_em_fantom(
    file: UploadFile = File(...),
    phantom_length_cm: float = Form(None),
    achieved_B: float = Form(None),
    duty_sum: float = Form(None),
):
    """Fantom tümör: klasik CV + BiLSTM (D/P/E). phantom_length_cm ile gerçek-mm ölçek."""
    try:
        data = file.file.read()
        img = _read_bgr(data)
        c = predictors.get("em_fantom")
        pl = c["cls"](c["cfg"], phantom_length_cm=phantom_length_cm, manual_fallback=False)
        pl._predictor = c["predictor"]  # önbellekli predictor enjekte (router deseni)
        t0 = time.time()
        result, ctx = pl.process_image(img, achieved_B=achieved_B, duty_sum=duty_sum)
        infer_ms = round((time.time() - t0) * 1000, 1)
        overlay = pl.render_panels(ctx, result, lang="tr")["07_combined"] if result.success else img
        payload = result.to_dict()
        return {
            "status": "success" if result.success else "no_detection",
            "device": _prov_dev(c["predictor"].session),
            "inference_ms": infer_ms,
            "success": result.success,
            "error": result.error,
            "n_tumor": result.n_tumor,
            "n_healthy": result.n_healthy,
            "method": result.method,
            "mm_per_px": round(result.mm_per_px, 4),
            "tumor_regions": payload["tumor_regions"],
            "healthy_regions": payload["healthy_regions"],
            "timing_ms": result.timing_ms,
            "image_base64": _jpg_b64(overlay),
        }
    except Exception as e:
        return _err500(e)


@app.post("/infer/em_petri")
def infer_em_petri(
    file: UploadFile = File(...),
    petri_diameter_cm: float = Form(None),
    achieved_B: float = Form(None),
    duty_sum: float = Form(None),
):
    """Petri kuyu: YOLO-seg + klasik CV + BaggingRegressor. petri_diameter_cm ile gerçek-mm."""
    from dataclasses import asdict

    try:
        data = file.file.read()
        img = _read_bgr(data)
        c = predictors.get("em_petri")
        pl = c["cls"](
            c["cfg"], petri_diameter_cm=petri_diameter_cm, yolo_model_path=c["yolo_path"], yolo_device=_yolo_device()
        )
        pl.yolo = c["yolo"]
        pl._predictor = c["predictor"]
        t0 = time.time()
        result, ctx = pl.process_image(img, achieved_B=achieved_B, duty_sum=duty_sum)
        infer_ms = round((time.time() - t0) * 1000, 1)
        overlay = pl.render_panels(ctx, result, lang="tr")["07_combined"] if result.success else img
        return {
            "status": "success" if result.success else "no_detection",
            "device": _prov_dev(c["predictor"].session),
            "inference_ms": infer_ms,
            "success": result.success,
            "error": result.error,
            "n_wells": result.n_wells,
            "n_cancer": result.n_cancer,
            "n_healthy": result.n_healthy,
            "method": result.method,
            "mm_per_px": round(result.mm_per_px, 4),
            "wells": [asdict(w) for w in result.wells],
            "timing_ms": result.timing_ms,
            "image_base64": _jpg_b64(overlay),
        }
    except Exception as e:
        return _err500(e)


@app.post("/infer/em_kedi")
def infer_em_kedi(payload: dict = Body(...)):
    """AI Pro bobin-sürüş: em_kedi (BiLSTM_XXL_Raw ONNX, GPU) → D1-7/P1-7/result_E.
    JSON: x,y,z (mm) + organ_id + achieved_B(ops) + duty_sum(ops). AI Pro loop/frame'in AĞIR
    sürüş-inference'ını GPU'ya devreder (çekirdek _predict_and_drive ai_service_enabled'da çağırır)."""
    try:
        pred = predictors.get("em_kedi")
        t0 = time.time()
        result = pred.predict(
            x=float(payload.get("x", 0.0)),
            y=float(payload.get("y", 0.0)),
            z=float(payload.get("z", 0.0)),
            organ_id=int(payload.get("organ_id", 0)),
            achieved_B=float(payload.get("achieved_B", 0.001)),
            duty_sum=float(payload.get("duty_sum", 2.0)),
        )
        # numpy skalerlerini JSON-serileştirilebilir float'a çevir (aksi halde json.dumps patlar).
        out = {}
        for k, v in result.items():
            try:
                out[k] = float(v)
            except (TypeError, ValueError):
                out[k] = v
        return {
            "status": "success",
            "device": _prov_dev(pred.session),
            "inference_ms": round((time.time() - t0) * 1000, 1),
            **out,
        }
    except Exception as e:
        return _err500(e)
