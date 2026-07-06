"""ai_hub.inference_petri_dish — Petri kuyu görü pipeline paketi.

petri_cv: YOLO11m-seg ile N kuyucuk tespit -> HSV kanser sınıflandırma -> 3B mm
koordinat -> PetriPredictor (ai_hub.inference_em_petri) besleme -> 7-panel görsel.
Klasik CV + YOLO, headless-güvenli (GUI import'u yok).
"""
