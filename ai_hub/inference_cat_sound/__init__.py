# Author: mertaygn, cglrgrkn
"""ai_hub.inference_cat_sound — Kedi sesi sınıflandırıcı paketi.

CatSoundClassifier: ses (mp3/wav) → librosa mel-spektrogram (mel+delta+delta²) →
EfficientNet_Lite0 ONNX (14.7MB, staged) → 10 sınıf (Angry..Warning) + top-3.
ONNX runtime (torch YOK). Ses decode: librosa/soundfile + ffmpeg (imageio-ffmpeg).
"""
from .inference_cat_sound import CatSoundClassifier  # noqa: F401
