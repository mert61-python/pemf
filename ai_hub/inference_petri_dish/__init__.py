# Author: mertaygn, cglrgrkn
"""ai_hub.inference_petri_dish — Petri kuyu görü pipeline paketi.

petri_cv_v2: Çağlar Hoca'nın petri v2'si (AI-2, 2026-10-12) — 24 kuyucuklu plaka ızgarası (A1–D6; YOLO11m-seg
ONNX yalnız aday ipucu) ya da tekil kap kipi (YOLO) -> Lab b* / mavi oran kanser sınıflandırma -> 3B mm koordinat ->
PetriPredictor (ai_hub.inference_em_petri) besleme -> 7-panel görsel. v1 `petri_cv` emekli (AI-2 C6).
Klasik CV + YOLO, headless-güvenli (GUI import'u yok).
"""
