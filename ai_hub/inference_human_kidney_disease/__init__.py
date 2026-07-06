"""ai_hub.inference_human_kidney_disease — UCI-CKD klinik sınıflandırıcı paketi.

predict_one(features_dict): 24 klinik özellik (14 sayısal + 10 kategorik, eksikler
impute) -> preprocessor -> ONNX (default ExtraTrees) -> {prob_ckd, label, model}.
Tüm modeller <5MB, EXE'ye gömülü; CPU; torch gerekmez.
"""
from .inference_human_kidney_disease import predict_one, predict_batch, ALL_FEATURES  # noqa: F401
