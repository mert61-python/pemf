# Author: mertaygn, cglrgrkn
"""petri_detector.py — YOLO11m-seg petri kabi detection (ana detector).

Mevcut egitilmis model (ayni klasor):
    inference/inference_petri_dish/yolo11m-seg.pt
        - mAP50    = 0.984
        - mAP50-95 = 0.961
        - 22.3 M parametre

Kullanim:
    from petri_cv.petri_detector import PetriYoloDetector
    det = PetriYoloDetector()
    petris = det.detect(image_bgr)   # list[PetriDetection]
"""
from __future__ import annotations
import os
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


# YOLO model yolu (ayni klasorde - inference_petri_dish/yolo11m-seg.pt)
_THIS_DIR = Path(__file__).parent.resolve()
_DEFAULT_MODEL = _THIS_DIR.parent / "yolo11m-seg.pt"


@dataclass
class PetriDetection:
    """YOLO ile tespit edilen petri kabi."""
    bbox_xyxy: tuple[float, float, float, float]    # x1, y1, x2, y2
    conf: float                                      # YOLO confidence
    mask: np.ndarray                                 # (H, W) uint8 binary
    contour: np.ndarray                              # (N, 1, 2) CV2
    centroid_px: tuple[float, float]
    area_px: int
    radius_px: float                                 # bbox kosegen / 4 (yaklasik)


class PetriYoloDetector:
    """YOLO11m-seg petri dish detector (lazy load).

    Kedi `inference_cat_organ` paterniyle uyumlu:
        - Modeli lazy yukle (ilk detect() cagrisinda)
        - Detection -> PetriDetection list (bbox + mask + contour + centroid)
    """

    def __init__(self, model_path: str | os.PathLike | None = None,
                 *, conf: float = 0.25, iou: float = 0.7,
                 imgsz: int = 640, device: str = "0"):
        self.model_path = Path(model_path) if model_path else _DEFAULT_MODEL
        if not self.model_path.exists():
            raise FileNotFoundError(
                f"YOLO petri modeli bulunamadi: {self.model_path}\n"
                f"Beklenen yol: inference/inference_petri_dish/yolo11m-seg.pt"
            )
        self.conf = conf
        self.iou = iou
        self.imgsz = imgsz
        self.device = device
        self._model = None    # lazy

    def _ensure_model(self):
        if self._model is None:
            try:
                from ultralytics import YOLO
            except ImportError:
                raise SystemExit(
                    "ultralytics yuklenmiyor. Yukle: pip install ultralytics"
                )
            self._model = YOLO(str(self.model_path))
        return self._model

    def detect(self, image_bgr: np.ndarray) -> list[PetriDetection]:
        """Goruntude petri kaplarini tespit et.

        Returns:
            list[PetriDetection] — conf > self.conf olanlar, skora gore sirali
        """
        model = self._ensure_model()
        h, w = image_bgr.shape[:2]
        results = model.predict(
            source=image_bgr, conf=self.conf, iou=self.iou,
            imgsz=self.imgsz, device=self.device,
            verbose=False, save=False, show=False,
        )
        detections: list[PetriDetection] = []
        for r in results:
            if r.boxes is None or len(r.boxes) == 0:
                continue
            masks = r.masks
            for i, box in enumerate(r.boxes):
                conf = float(box.conf[0])
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                bw = max(1.0, x2 - x1)
                bh = max(1.0, y2 - y1)

                # YOLO mask -> binary
                if masks is not None and i < len(masks.data):
                    m_tensor = masks.data[i]
                    m_np = m_tensor.cpu().numpy().astype(np.uint8) * 255
                    if m_np.shape[:2] != (h, w):
                        m_np = cv2.resize(m_np, (w, h),
                                          interpolation=cv2.INTER_NEAREST)
                else:
                    m_np = np.zeros((h, w), dtype=np.uint8)
                    cv2.rectangle(m_np, (int(x1), int(y1)),
                                  (int(x2), int(y2)), 255, -1)

                contours, _ = cv2.findContours(
                    m_np, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                if not contours:
                    continue
                cnt = max(contours, key=cv2.contourArea)
                area = int(cv2.contourArea(cnt))
                if area < 100:
                    continue
                M = cv2.moments(cnt)
                if M["m00"] < 1e-6:
                    continue
                cx = M["m10"] / M["m00"]
                cy = M["m01"] / M["m00"]

                detections.append(PetriDetection(
                    bbox_xyxy=(float(x1), float(y1), float(x2), float(y2)),
                    conf=conf,
                    mask=m_np,
                    contour=cnt,
                    centroid_px=(float(cx), float(cy)),
                    area_px=area,
                    radius_px=float(np.hypot(bw, bh) / 4.0),
                ))
        detections.sort(key=lambda d: d.conf, reverse=True)
        return detections
