# Author: mertaygn, cglrgrkn
"""runners.py - YOLO seg + DLC detector + pose ONNX runners (bagimsiz).

Bu modul artik DeepLabCut'a **runtime bagimliligi yok** — sadece 3 ONNX modelini
onnxruntime + numpy + opencv ile calistirir. PyTorch ve DLC sadece bir kereye
mahsus ONNX export'ta gerekiyordu (bkz. export_onnx.py).

Model dosyalari `models/`:
    yolov8m-seg.onnx                                                  (104 MB)
    superanimal_quadruped_fasterrcnn_mobilenet_v3_large_fpn.onnx      ( 72 MB)
    superanimal_quadruped_rtmpose_s.onnx                              ( 23 MB)

Preprocessing/postprocessing DLC 3.0.0rc13 semantiginin birebir kopyasidir:
    - Detector: ImageNet normalize (mean=0.485/0.456/0.406, std=0.229/0.224/0.225)
    - Pose crop: `top_down_crop` (256x256, crop_with_context=True, center_padding=True)
    - Pose input: ayni ImageNet normalize
    - SimCC decode: sigma=5.66, decode_beta=150, apply_softmax=True, simcc_split_ratio=2.0
"""
from __future__ import annotations
from pathlib import Path
import numpy as np
import cv2

from .canonical import KEYPOINT_NAMES, YOLO_SEG_CKPT, MODELS_DIR

# ONNX yollari
POSE_ONNX = MODELS_DIR / "superanimal_quadruped_rtmpose_s.onnx"
DET_ONNX  = MODELS_DIR / "superanimal_quadruped_fasterrcnn_mobilenet_v3_large_fpn.onnx"
YOLO_ONNX = MODELS_DIR / "yolov8m-seg.onnx"

# ImageNet normalize (DLC data.inference.normalize_images: true)
_IN_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_IN_STD  = np.array([0.229, 0.224, 0.225], dtype=np.float32)

# RTMPose SimCC head config (rtmpose_s.yaml)
_SIMCC_INPUT_SIZE  = (256, 256)     # W, H
_SIMCC_SPLIT_RATIO = 2.0
_SIMCC_SIGMA       = 5.66
_SIMCC_DECODE_BETA = 150.0

# Session cache — cold start maliyeti bir kez
_ORT_SESS: dict[str, "any"] = {}


def _ort_session(onnx_path: Path, device: str | None):
    """onnxruntime InferenceSession — GPU varsa CUDA, degilse CPU."""
    key = f"{onnx_path}|{device}"
    if key in _ORT_SESS:
        return _ORT_SESS[key]
    import onnxruntime as ort
    want_cuda = device is None or str(device).startswith(("cuda", "0", "gpu"))
    providers = []
    if want_cuda and "CUDAExecutionProvider" in ort.get_available_providers():
        providers.append("CUDAExecutionProvider")
    providers.append("CPUExecutionProvider")
    sess = ort.InferenceSession(str(onnx_path), providers=providers)
    _ORT_SESS[key] = sess
    return sess


# ============================================================================
# YOLO segmentation (ultralytics ONNX runtime)
# ============================================================================
def run_yolo_segmentation(image_path: str, conf=0.5, iou=0.5, imgsz=640,
                           device=None) -> dict:
    """ultralytics YOLO(.onnx) — API PT ile birebir."""
    onnx_path = YOLO_ONNX if YOLO_ONNX.exists() else YOLO_SEG_CKPT
    if not onnx_path.exists():
        return {"error": f"YOLO model yok: {onnx_path}"}
    from ultralytics import YOLO
    model = YOLO(str(onnx_path), task="segment")
    r = model.predict(source=str(image_path), conf=conf, iou=iou, imgsz=imgsz,
                       device=device if device else "0",
                       verbose=False)[0]
    if r.boxes is None or len(r.boxes) == 0:
        return {"error": "kedi tespit edilemedi"}
    confs = r.boxes.conf.cpu().numpy() if hasattr(r.boxes.conf, "cpu") else np.asarray(r.boxes.conf)
    best = int(np.argmax(confs))
    box = r.boxes.xyxy[best]
    box = box.cpu().numpy() if hasattr(box, "cpu") else np.asarray(box)
    out = {
        "bbox": [float(v) for v in box.tolist()],
        "conf": float(confs[best]),
        "n_detections": int(len(r.boxes)),
    }
    if r.masks is not None and len(r.masks.xy) > best:
        poly = r.masks.xy[best]
        out["mask_xy"] = poly.tolist()
    return out


# ============================================================================
# DLC top-down crop (data/image.py'den birebir kopyalanmis)
# ============================================================================
def _top_down_crop(image: np.ndarray, bbox_xywh: tuple,
                    output_size: tuple = (256, 256),
                    margin: int = 0, crop_with_context: bool = True,
                    center_padding: bool = True):
    """DLC top_down_crop: bbox merkezine gore aspect-ratio korunmus kirp+padle.

    Args:
        image: (H, W, C) numpy — RGB
        bbox_xywh: (x, y, w, h) — sol-ust koseden genislik/yukseklik
        output_size: (out_w, out_h)
    Returns:
        cropped_image (out_h, out_w, C), offset=(ox, oy), scale=(sx, sy)
    """
    image_h, image_w, c = image.shape
    out_w, out_h = output_size
    x, y, w, h = bbox_xywh

    cx = x + w / 2
    cy = y + h / 2
    w += 2 * margin
    h += 2 * margin

    if crop_with_context:
        input_ratio = w / h
        output_ratio = out_w / out_h
        if input_ratio > output_ratio:
            h = w / output_ratio
        elif input_ratio < output_ratio:
            w = h * output_ratio

    x1, y1 = int(round(cx - (w / 2))), int(round(cy - (h / 2)))
    x2, y2 = int(round(cx + (w / 2))), int(round(cy + (h / 2)))

    pad_left = pad_right = pad_top = pad_bottom = 0
    if x1 < 0:
        pad_left = -x1; x1 = 0
    if x2 > image_w:
        pad_right = x2 - image_w; x2 = image_w
    if y1 < 0:
        pad_top = -y1; y1 = 0
    if y2 > image_h:
        pad_bottom = y2 - image_h; y2 = image_h

    w, h = x2 - x1, y2 - y1
    pad_x = pad_left + pad_right
    pad_y = pad_top + pad_bottom
    if center_padding:
        pad_left = pad_x // 2
        pad_top = pad_y // 2

    image_crop = np.zeros((h + pad_y, w + pad_x, c), dtype=image.dtype)
    image_crop[pad_top:pad_top + h, pad_left:pad_left + w] = image[y1:y2, x1:x2]
    image_out = cv2.resize(image_crop, (out_w, out_h), interpolation=cv2.INTER_LINEAR)

    offset = (x1 - pad_left, y1 - pad_top)
    scale = ((w + pad_x) / out_w, (h + pad_y) / out_h)
    return image_out, offset, scale


# ============================================================================
# SimCC decode (DLC predictors/sim_cc.py'den birebir kopyalanmis)
# ============================================================================
def _simcc_decode(simcc_x: np.ndarray, simcc_y: np.ndarray,
                   sigma: float = _SIMCC_SIGMA,
                   decode_beta: float = _SIMCC_DECODE_BETA,
                   split_ratio: float = _SIMCC_SPLIT_RATIO,
                   apply_softmax: bool = True):
    """SimCC (x/y ekseni 1D-classification) -> keypoint locs + scores.

    Args:
        simcc_x: (N, K, Wx)  — muhtemelen (1, 39, 512)
        simcc_y: (N, K, Wy)
    Returns:
        locs: (N, K, 2) float32 — crop pixel koordinatlari (0..256)
        vals: (N, K) float32     — score [0,1]
    """
    x = simcc_x * (sigma * decode_beta)
    y = simcc_y * (sigma * decode_beta)

    if x.ndim == 3:
        N, K, Wx = x.shape
        x_flat = x.reshape(N * K, -1)
        y_flat = y.reshape(N * K, -1)
    else:
        N = None
        x_flat, y_flat = x, y

    if apply_softmax:
        x_flat = x_flat - np.max(x_flat, axis=1, keepdims=True)
        y_flat = y_flat - np.max(y_flat, axis=1, keepdims=True)
        ex = np.exp(x_flat); ey = np.exp(y_flat)
        x_flat = ex / np.sum(ex, axis=1, keepdims=True)
        y_flat = ey / np.sum(ey, axis=1, keepdims=True)

    x_locs = np.argmax(x_flat, axis=1)
    y_locs = np.argmax(y_flat, axis=1)
    locs = np.stack((x_locs, y_locs), axis=-1).astype(np.float32)
    max_val_x = np.amax(x_flat, axis=1)
    max_val_y = np.amax(y_flat, axis=1)
    mask = max_val_x > max_val_y
    max_val_x[mask] = max_val_y[mask]
    vals = max_val_x.astype(np.float32)
    locs[vals <= 0.0] = -1

    if N:
        locs = locs.reshape(N, K, 2)
        vals = vals.reshape(N, K)

    locs = locs / split_ratio
    return locs, vals


# ============================================================================
# Pose: FasterRCNN (detector) + RTMPose-S (top-down) — hepsi ONNX
# ============================================================================
def run_pose(image_path: str, device=None, out_dir=None, plot=False,
              bbox_threshold: float = 0.5) -> dict:
    """DLC SuperAnimal-Quadruped pipeline'inin ONNX-native karsiligi.

    1. FasterRCNN ONNX -> bbox_xyxy
    2. top_down_crop (256x256, crop_with_context, center_padding)
    3. ImageNet normalize -> RTMPose ONNX -> (simcc_x, simcc_y)
    4. SimCC decode -> 39 keypoint (crop koord)
    5. Unwarp -> orijinal goruntu koord
    """
    if not DET_ONNX.exists():
        return {"error": f"detector ONNX yok: {DET_ONNX}"}
    if not POSE_ONNX.exists():
        return {"error": f"pose ONNX yok: {POSE_ONNX}"}

    # Load image
    img_bgr = cv2.imread(str(image_path))
    if img_bgr is None:
        return {"error": f"resim okunamadi: {image_path}"}
    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)

    # -- (1) Detector --
    det_input = ((img_rgb.astype(np.float32) / 255.0 - _IN_MEAN) / _IN_STD
                  ).transpose(2, 0, 1)[None].astype(np.float32)
    det_sess = _ort_session(DET_ONNX, device)
    det_out = det_sess.run(None, {"images": det_input})
    boxes, labels, scores = det_out
    if len(boxes) == 0:
        return {"error": "DLC kedi bulamadi (detector)"}
    keep = scores >= bbox_threshold
    if not np.any(keep):
        return {"error": f"detector conf < {bbox_threshold}"}
    boxes = boxes[keep]; scores = scores[keep]
    best = int(np.argmax(scores))
    box_xyxy = boxes[best].astype(np.float32)
    box_xywh = (float(box_xyxy[0]), float(box_xyxy[1]),
                 float(box_xyxy[2] - box_xyxy[0]),
                 float(box_xyxy[3] - box_xyxy[1]))

    # -- (2) Top-down crop --
    crop, offset, scale = _top_down_crop(img_rgb, box_xywh, _SIMCC_INPUT_SIZE,
                                          margin=0, crop_with_context=True,
                                          center_padding=True)

    # -- (3) Pose forward --
    pose_input = ((crop.astype(np.float32) / 255.0 - _IN_MEAN) / _IN_STD
                   ).transpose(2, 0, 1)[None].astype(np.float32)
    pose_sess = _ort_session(POSE_ONNX, device)
    simcc_x, simcc_y = pose_sess.run(None, {"input": pose_input})

    # -- (4) SimCC decode --
    locs, vals = _simcc_decode(simcc_x, simcc_y)

    # -- (5) Unwarp --
    kp = np.zeros((len(KEYPOINT_NAMES), 3), dtype=np.float32)
    kp[:, 0] = locs[0, :, 0] * scale[0] + offset[0]
    kp[:, 1] = locs[0, :, 1] * scale[1] + offset[1]
    kp[:, 2] = vals[0]

    return {"keypoints": kp, "bbox": box_xyxy}


def _kp_dict(keypoints: np.ndarray, thr: float = 0.3) -> dict:
    out = {}
    for i, name in enumerate(KEYPOINT_NAMES):
        x, y, c = keypoints[i]
        if float(c) >= thr:
            out[name] = np.array([float(x), float(y)], dtype=np.float64)
    return out
