# Author: mertaygn, cglrgrkn
"""ai_hub.inference_human_kidney_disease — UCI-CKD klinik sınıflandırıcı paketi.

predict_one(features_dict): 24 klinik özellik (14 sayısal + 10 kategorik, eksikler
impute) -> preprocessor -> ONNX (default ExtraTrees) -> {prob_ckd, label, model}.
Tüm modeller <5MB, EXE'ye gömülü; CPU; torch gerekmez.
"""
from .inference_human_kidney_disease import (  # noqa: F401
    ALL_FEATURES,
    _preprocessor_feature_names,
    _referans_background,
    load_model,
    predict_batch,
    predict_one,
    xai_top_features,
)
