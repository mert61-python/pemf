# Author: mertaygn, cglrgrkn
"""phantom_cv_v3 — Sentetik böbrek fantomu CV (Çağlar Hoca v3, 2026-10-02; AI-2 2026-10-12 guii'ye YAMA olarak alındı).

v3: lacivert hale + siyah çekirdekle tümör tespiti (v1 bobin / kablo / etiketi tümör sanıyordu), GrabCut ile fantom
sınırı, yeşil Helmholtz halkasından ölçek (D = 184 mm, VARSAYIM), paralaks düzeltmesi, tümör yerleşim referansıyla
SABİT kimlik (T1–T5) + uzak çekimde şablon fit + QC (`layout_mismatch`), fantom-sabit u/v çerçevesi, ArUco / ölçülmüş
yerleşim yoksa CST eğitim kutusuna PEMF yerleşimi (`pemf_axis_sign_assumed` — eksen işareti VARSAYIM), `reliable`.
Eski dağınık-leke fantomu (2026-06) için v1 HSV algoritmasına otomatik düşer.

guii'de ALINMAYANLAR (plan §3.3): `api.py` (uvicorn 8766), `cli.py`, `manual_select.py` (cv2 penceresi), `mqtt_publish.py`,
`coil_detect.py` (boru hattı kullanmıyor), README, `cabin_config_example.yaml`. Kabin yapılandırması ve koordinat
dönüşümü TEK uygulamadadır (`ai_hub/cv_ortak`, A2).
"""

from .cabin_config import CabinConfig, load_cabin_config  # noqa: F401
from .pipeline import PhantomCvPipeline, PipelineResult  # noqa: F401

# Geriye uyum:
load_config = load_cabin_config

__all__ = [
    "PhantomCvPipeline",
    "PipelineResult",
    "CabinConfig",
    "load_cabin_config",
    "load_config",
]
__version__ = "3.0.0"
