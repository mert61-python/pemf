"""ai_hub.inference_renal_histopath_kmc — Böbrek histopatoloji grade sınıflandırıcı paketi.

RenalHistopathClassifier: histoloji tile → V22-KMC-ClassicTrio ONNX (899MB, staged,
3-backbone ensemble VGG19-BN+WideResNet50-2+DenseNet201) → 5 grade (grade0..grade4)
softmax + top-k. onnxruntime + PIL; CPU (device="cpu"). .pt fallback bundle EDİLMEZ.
"""
from .inference_renal_histopath_kmc import RenalHistopathClassifier  # noqa: F401
