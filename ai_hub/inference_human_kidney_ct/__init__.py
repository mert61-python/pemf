# Author: mertaygn, cglrgrkn
"""ai_hub.inference_human_kidney_ct — Böbrek CT YOLO detektör paketi.

KidneyCTDetector: CT görüntüsü → YOLOv8s ONNX (43MB, staged) → 3 sınıf
(Kidney Stone / Kidney / Kidney Cyst) tespit + draw_overlay (annotated).
ultralytics + cv2; CPU (device="cpu").
"""
from .inference_human_kidney_ct import KidneyCTDetector, xai_ct_isi_haritasi  # noqa: F401
