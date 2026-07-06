"""petri_cv — YOLO11m-seg + Kedi-ArUco kalibrasyon ile petri kabi CV pipeline.

Kedi `inference_cat_organ` paterniyle birebir uyumlu:
    - YOLO11m-seg petri detection (mAP50-95 = 0.961, 22.3M param)
    - ArUco DICT_5X5_100 + solvePnP cabin kalibrasyon
    - HSV ile petri ICINDE mavi kanser tespit
    - PetriPredictor (BaggingRegressor R^2 = 0.9849) PEMF parametre tahmini

Akis:
    image  ->  undistort
           ->  ArUco varsa  PnP -> CabinPose (kedi paterni)
           ->  YOLO11m-seg petri detect -> PetriDetection (mask + bbox)
           ->  Petri mask ICINDE mavi kanser HSV -> tumor regions
           ->  Kalibrasyon mm/px (ArUco / petri_diameter / piksel)
           ->  Her tumor centroid -> cabin-frame mm
           ->  PetriPredictor.predict (organ_id=1)
           ->  JSON + kedi tarzi 7-panel TR+EN overlay
           ->  CLI / FastAPI / MQTT

Modules:
    cabin_config      — YAML loader (kedi paterni)
    coord_transform   — ArUco PnP + piksel->cabin mm
    petri_detector    — YOLO11m-seg petri detection
    color_segment     — Petri mask icinde kanser HSV
    render            — Kedi tarzi 7-panel TR+EN overlay
    pipeline          — Uctan uca orkestrasyon
    cli               — Komut satiri
    api               — FastAPI REST
    mqtt_publish      — paho-mqtt 3.1.1 (ESP32-S3)
"""
from .pipeline import PetriCvPipeline, PipelineResult                # noqa: F401
from .cabin_config import CabinConfig, load_cabin_config              # noqa: F401
from .petri_detector import PetriYoloDetector, PetriDetection         # noqa: F401

# Geriye uyum:
load_config = load_cabin_config

__all__ = [
    "PetriCvPipeline", "PipelineResult",
    "CabinConfig", "load_cabin_config", "load_config",
    "PetriYoloDetector", "PetriDetection",
]
__version__ = "1.0.0"
