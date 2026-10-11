# Author: mertaygn, cglrgrkn
"""petri_cv_v2 — Petri kuyucuk plakası CV (Çağlar Hoca v2, 2026-10-02; AI-2 2026-10-12 guii'ye YAMA olarak alındı).

v2: 24'lük plaka IZGARA kipi (kuyucuk kimliği A1–D6, YOLO yalnız ipucu: plaka kırpılıp aday üretir + Hough + RANSAC +
ECC), göreli renkle kanser/sağlıklı (+ kontrol kuyucuklarıyla plaka başına eşik kalibrasyonu ve QC uyarıları),
`coord_frame` / `pemf_valid` (kabin konumu yoksa D/P/E fiziksel olarak GEÇERSİZ) / `warnings`. Tekil petri kipi
(`plate_type` 0/None) v1 davranışını korur.

guii'de ALINMAYANLAR (plan §3.3): `api.py` (uvicorn 8765), `cli.py`, `mqtt_publish.py` (paho → ESP), `eval_plate.py`,
`annotate_plate.html`, README (DICT_5X5_100 / 5 cm — saha DICT_5X5_50 / 15 cm, bkz. tests/test_marker_dokuman_tutarliligi.py).
Kabin yapılandırması ve koordinat dönüşümü TEK uygulamadadır (`ai_hub/cv_ortak`, A2); YOLO yalnız ONNX (640 sabit giriş).

Akış: görüntü → (küçültme) → undistort → ArUco PnP (varsa) → plaka ızgarası | YOLO → MAKULLİK → kalibrasyon →
kuyucuk başına kanser sınıfı + kabin/plaka mm → PetriPredictor (D[7], P[7], E) → 7 panel (TR).
"""

from .cabin_config import CabinConfig, load_cabin_config  # noqa: F401
from .petri_detector import PetriDetection, PetriYoloDetector  # noqa: F401
from .pipeline import PetriCvPipeline, PipelineResult  # noqa: F401

# Geriye uyum:
load_config = load_cabin_config

__all__ = [
    "PetriCvPipeline",
    "PipelineResult",
    "CabinConfig",
    "load_cabin_config",
    "load_config",
    "PetriYoloDetector",
    "PetriDetection",
]
__version__ = "2.0.0"
