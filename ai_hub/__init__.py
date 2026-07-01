# -*- coding: utf-8 -*-
"""
ai_hub — Unified AI Model Registry
====================================
Tüm inference modülleri bu paket altında toplanmıştır.

Yapı:
  em_kedi/          → BiLSTM_XXL_Raw (AI Pro, Combined R²=0.9481)
  em_kedi_legacy/   → ResNet_kedi_v2 (eski model, arşiv)
  em_petri/         → PetriNet_v3
  em_phantom/       → PhantomNet_v3
  cat_disease/      → XGBoost hastalık tahmini
  cat_landmark/     → YOLO-pose (FGS)
  cat_segmentation/ → YOLOv8m-seg
  cat_thermal/      → GhostNetV2 binary sınıflandırma
  cat_sound/        → Ses modeli (hazır slot)
  feline_reticulocytes/ → YOLOv8s
  petri_dish/       → YOLO11m-seg

NOT: ONNX model dosyaları exe'ye dahil edilmez.
     Runtime'da utils.model_downloader üzerinden Hugging Face'den indirilir.
"""
