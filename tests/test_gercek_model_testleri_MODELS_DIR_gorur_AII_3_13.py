# -*- coding: utf-8 -*-
"""AII-3.13 — eski gerçek-model XAI testlerinin atlama koşulu ürünün model kökünü (`PEMF_AI_MODELS_DIR`) görür ve 4-A SKIP→FAIL'e uyar.

ÖLÇÜLDÜ (A3, 2026-10-12, `_inceleme/kayit/k5_skip_*.txt`): `test_ckd_xai.py` (8), `test_gradient_xai_ses_termal.py` (3) ve
`test_xai_faz2_kuyruk.py` (4) gerçek-model testleri atlama koşulunu `KOK/release_assets/...` ya da modül dizinine bağlıyor → ağırlık
`PEMF_AI_MODELS_DIR`'dan VERİLDİĞİNDE ve `PEMF_GOLDEN_REQUIRED=1` iken bile 15'i de ATLANIYOR (ağırlıklı + golden: 66 geçti / 15 atlandı;
ağırlıksız + golden: AI-1'in 13 testi HATA, bu 15'i yine atlandı). Klon / CI koşularının hiçbirinde koşmuyorlar (kalıcı kör nokta).
Kapı: model kökü verildiğinde bu dosyaların atlama koşulu "var" der; golden kipte atlamaz.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK / "tests"))


@pytest.fixture()
def agirlik_var():
    from golden.eser import atla, eser_var_mi

    gerekli = (
        "ai_hub/cat_thermal/GhostNetV2.pt",
        "ai_hub/inference_cat_sound/EfficientNet_Lite0.pt",
        "ai_hub/feline_reticulocytes/yolov8s.pt",
        "ai_hub/inference_human_kidney_ct/yolov8s.pt",
    )
    if not eser_var_mi(*gerekli):
        atla(f"ağırlıklar yok ({gerekli})")


def _kosul(modul: str, isaret: str) -> bool:
    m = importlib.import_module(modul)
    return bool(getattr(m, isaret).args[0])


def test_KRITIK_termal_ses_gercek_PT_testleri_MODEL_KOKUNU_gorur(agirlik_var):
    assert _kosul("test_gradient_xai_ses_termal", "gercek_pt_gerekir") is False, (
        "test_gradient_xai_ses_termal: ağırlık PEMF_AI_MODELS_DIR'da VAR ama gerçek-PT testleri ATLANIYOR (KOK/release_assets'e bağlı)"
    )


def test_KRITIK_yolo_gercek_PT_testleri_MODEL_KOKUNU_gorur(agirlik_var):
    assert _kosul("test_xai_faz2_kuyruk", "yolo_pt_gerekir") is False, (
        "test_xai_faz2_kuyruk: YOLO PT'ler PEMF_AI_MODELS_DIR'da VAR ama gerçek DetCAM testleri ATLANIYOR"
    )


def test_KRITIK_ckd_gercek_model_testleri_MODEL_KOKUNU_gorur(agirlik_var):
    from golden.eser import atla, ckd_eserleri, eser_var_mi

    if not eser_var_mi(*ckd_eserleri()):
        atla("CKD eserleri yok")  # D5-F: eski düz pytest.skip — golden zorunlu kipte DÜŞER
    m = importlib.import_module("test_ckd_xai")
    assert m._MODEL_VAR is True, (
        "test_ckd_xai: CKD eserleri PEMF_AI_MODELS_DIR'da VAR ama 8 gerçek-model testi ATLANIYOR"
    )


@pytest.mark.parametrize(
    "modul,isaret",
    [
        ("test_gradient_xai_ses_termal", "gercek_pt_gerekir"),
        ("test_xai_faz2_kuyruk", "yolo_pt_gerekir"),
        ("test_ckd_xai", "gercek_model_gerekir"),
        # D5-F (K5-F P5): eskiden düz `skipif` olan iki gerçek-PT işareti de aynı sözleşmeye bağlandı
        ("test_xai_faz2_kuyruk", "rna_pt_gerekir"),
        ("test_renal_xai", "gercek_pt_gerekir"),
    ],
)
def test_KRITIK_golden_kipte_eser_YOKKEN_ATLAMAZ(monkeypatch, modul, isaret):
    """Orkestratör (AI inceleme): `PEMF_GOLDEN_REQUIRED=1` + eser yok → atlama koşulu YANLIŞ (test koşar ve düşer; 4-A SKIP→FAIL).
    Ajanın kapısı yalnız "eser VARKEN atlamaz" yönünü ölçüyordu; `and not zorunlu_mu()` silinse YEŞİL kalırdı."""
    import importlib.util

    import golden.eser as ge

    monkeypatch.setenv("PEMF_GOLDEN_REQUIRED", "1")
    monkeypatch.setattr(ge, "eser_var_mi", lambda *a, **k: False)
    spec = importlib.util.spec_from_file_location(f"{modul}_aii313_golden", KOK / "tests" / f"{modul}.py")
    m = importlib.util.module_from_spec(spec)
    # D5-F (K5-F P5): ham `Path.exists()` / `is_file()` koşulu da "eser yok" görmeli — yalnız `eser_var_mi` sahtelenirse eser
    # klonda VARKEN eski ham biçime dönen işaret (ör. `_RNA_PT.exists()`) bu kolu YEŞİL geçiyordu (ölçüldü, K5-F m2).
    with monkeypatch.context() as mp:
        mp.setattr(Path, "exists", lambda self, *a, **k: False)
        mp.setattr(Path, "is_file", lambda self, *a, **k: False)
        spec.loader.exec_module(m)
    assert bool(getattr(m, isaret).args[0]) is False, (
        f"{modul}: golden kipte eser yokken {isaret} testleri ATLIYOR (SKIP→FAIL delindi)"
    )
