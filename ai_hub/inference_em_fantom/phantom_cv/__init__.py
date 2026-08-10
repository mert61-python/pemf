# Author: mertaygn, cglrgrkn
"""phantom_cv — Sentetik bobrek fantom modeli CV pipeline.

Kedi (inference_cat_organ) cabin paterniyle birebir uyumlu.
Iki kalibrasyon modu:
  (A) ArUco TEK marker + solvePnP -> CabinPose  (kedi paterni)
  (B) Hough Circle ile Helmholtz bobin tespit   (ArUco yoksa FALLBACK)
      Bobinin BILINEN R_c (5.7 cm, paper 7) ile mm/px kalibrasyon.

Akis:
  image  ->  undistort
         ->  ArUco varsa  PnP -> CabinPose
                       yoksa  Hough Circle -> coil-center origin + mm/px
         ->  3-renk HSV segmentasyon (sentetik bobrek):
                MAVI noktalar  -> tumor (organ_id=1)
                KREM/BEYAZ    -> saglikli doku (organ_id=0)
                KAHVERENGI    -> yanik izi (post-PEMF, opsiyonel)
         ->  Her tumor centroid -> cabin-frame mm
         ->  PhantomPredictor (BiLSTM_XXL_Raw, R^2 = 0.9955)
         ->  JSON + kedi tarzi 7-panel TR+EN overlay
         ->  CLI / FastAPI / MQTT

Modules:
  cabin_config      — YAML loader (kedi paterni)
  coord_transform   — ArUco PnP + piksel->cabin mm
  color_segment     — 3-renk HSV (tumor + doku + yanik)
  render            — Kedi tarzi 7-panel TR+EN overlay
  pipeline          — Uctan uca orkestrasyon
  cli               — Komut satiri
  api               — FastAPI REST
  mqtt_publish      — paho-mqtt 3.1.1 (ESP32-S3)
"""
from .pipeline import PhantomCvPipeline, PipelineResult        # noqa: F401
from .cabin_config import CabinConfig, load_cabin_config        # noqa: F401

# Geriye uyum:
load_config = load_cabin_config

__all__ = [
    "PhantomCvPipeline", "PipelineResult",
    "CabinConfig", "load_cabin_config", "load_config",
]
__version__ = "0.2.0"
