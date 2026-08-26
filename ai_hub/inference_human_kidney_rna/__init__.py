# Author: mertaygn, cglrgrkn
"""ai_hub.inference_human_kidney_rna — RNA-seq KIRC sınıflandırıcı paketi.

KidneyRnaPredictor: MLP-medium ONNX; girdi 20531-gen CSV (log2→StandardScaler→
SelectKBest top-1000) -> KIRC/other + güven. Tüm dosyalar <5MB, EXE'ye gömülür.
"""
from .inference_human_kidney_rna import KidneyRnaPredictor, xai_top_genler  # noqa: F401
