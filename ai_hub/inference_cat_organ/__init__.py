# Author: mertaygn, cglrgrkn
"""ai_hub.inference_cat_organ — Kedi organ 3B lokalizasyon pipeline paketi.

CatOrganPredictor (catorgan_predictor.py): kedi görüntüsü → YOLOv8m-seg + SuperAnimal
FasterRCNN + RTMPose-S (3 ONNX, staged) → canonical atlas + PnP → 10 organ 3B (cm).
ONNX-only, CPU (device="cpu"); ArUco opsiyonel. torch/DLC/mmpose GEREKMEZ (sadece export).
"""
