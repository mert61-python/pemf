# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""Tahminci yükleyici — `sys.path`i KİRLETMEDEN.

⚠️ NEDEN importlib: `ai_hub/` dizinini `sys.path`e eklemek `inference_em_petri` adını
**pakete** çözer (`ai_hub/inference_em_petri/__init__.py`, `PetriPredictor` YOK). Oysa üretim
yolu — `ai_hub/inference_petri_dish/petri_cv/pipeline.py` — aynı adın **modül dosyasına**
çözülmesine dayanır ve kendi `sys.path` girdisini ekler. Testte `ai_hub`i öne almak bu ad
çakışmasını tersine çevirir ve `test_petri_plausibility.py`nin 11 testini kırar (ölçüldü,
2026-08-10). Bu yüzden burada dosyadan BENZERSİZ adla yüklenir; `sys.modules`taki gerçek adlar
hiç dokunulmaz.
"""

import importlib.util
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parents[2]
AI_HUB = KOK / "ai_hub"

# ad -> (modül dosyası, sınıf)
EM_TAHMINCILER = {
    "em_fantom": ("inference_em_fantom/inference_em_fantom.py", "PhantomPredictor"),
    "em_petri": ("inference_em_petri/inference_em_petri.py", "PetriPredictor"),
    "em_kedi": ("em_kedi/inference_em_kedi.py", "KediPredictor"),
}


def _dosyadan_yukle(ad: str, yol: Path):
    """Benzersiz modül adıyla dosyadan yükle — gerçek adı gölgeleme."""
    spec = importlib.util.spec_from_file_location(ad, yol)
    if spec is None or spec.loader is None:
        raise ImportError(f"{yol} yuklenemedi")
    m = importlib.util.module_from_spec(spec)
    sys.modules[ad] = m  # dataclass/pickle için gerekli, ad ÖN EKLİ
    spec.loader.exec_module(m)
    return m


def em_tahminci(ad: str):
    """`em_fantom` / `em_petri` / `em_kedi` örneği döndür."""
    dosya, sinif = EM_TAHMINCILER[ad]
    yol = AI_HUB / dosya
    if not yol.exists():
        raise FileNotFoundError(f"{yol} yok")
    m = _dosyadan_yukle(f"_altin_{ad}", yol)
    return getattr(m, sinif)()


def ckd_modulu():
    """CKD paketi `__init__.py`den `predict_one` ihraç eder → normal import yeterli."""
    from ai_hub.inference_human_kidney_disease import inference_human_kidney_disease as m

    return m


def rna_tahminci():
    """RNA paketi `__init__.py`den `KidneyRnaPredictor` ihraç eder → normal import yeterli."""
    from ai_hub.inference_human_kidney_rna import KidneyRnaPredictor

    return KidneyRnaPredictor()
