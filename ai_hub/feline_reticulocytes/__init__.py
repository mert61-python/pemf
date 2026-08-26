# Author: mertaygn, cglrgrkn
"""ai_hub.feline_reticulocytes — kan yaymasinda retikulosit sayimi (YOLOv8s).

Tespit: router dogrudan ultralytics YOLO(onnx) ile kosar (bkz. servers/ai_router.py).
Bu paket XAI icin import edilir: xai_retikulosit_isi_haritasi (EigenCAM, Faz 2).
"""
from .inference_feline_reticulocytes import xai_retikulosit_isi_haritasi  # noqa: F401
