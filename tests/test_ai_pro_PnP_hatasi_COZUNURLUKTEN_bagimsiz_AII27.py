# -*- coding: utf-8 -*-
"""AII-2.7 (AI incelemesi, A2 · S-AII [ÖNERİLEN UYGULANDI]) — AI Pro güven dökümünde PnP uyum hatası ÇÖZÜNÜRLÜKTEN BAĞIMSIZ (≈ cm).

KUSUR [ÖLÇTÜM A2 `K4_pnp_cozunurluk.json`]: döküm "PnP uyum hatası N px" gösteriyordu; aynı kedi karesi 4032 / 2016 / 1008 px'te
231 / 114 / 49 px — sayı kameranın çözünürlüğünü ölçüyor, hattın uyumunu değil; eşik ve eylem yok. Hattın kendi ölçeği
(`pnp_fit.scale_px_per_cm`) da çözünürlükle doğrusal → `residual_px / scale_px_per_cm` kedi gövdesi biriminde (cm) aynı kalır.
DÜZELTME (yalnız gösterim; güven, konum, sürüş DEĞİŞMEZ): `_hat_dokumu` dökümün kopyasına `pnp_hata_cm` ekler; iki cat_organ ucu
(gömülü + GPU servisi) `pnp_scale_px_per_cm` taşır (parite); panel "≈ X cm" der, ölçek yoksa (eski servis) sayı GÖSTERİLMEZ.
Yol: tests/test_ai_pro_PnP_hatasi_COZUNURLUKTEN_bagimsiz_AII27.py"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK / "tests"))
from test_ai_gomulu_gpu_paritesi import ROUTER, SERVIS, _fonksiyonlar, _yanit_alanlari  # noqa: E402

DOK = {
    "pose_confidence": 0.7,
    "depth_factor": 0.95,
    "mask_factor": 1.0,
    "uncertainty_factor": 0.93,
    "calibration_cap": None,
}


@pytest.fixture
def air(monkeypatch):
    from servers import ai_router

    monkeypatch.setattr(ai_router, "ai_service_enabled", lambda: False)
    return ai_router


def _organlar():
    return {2: {"coord_cabin_cm": [5.0, -3.0, 2.0], "reliability": 0.62, "reliability_components": dict(DOK)}}


def _cpu(air, monkeypatch, pnp_fit):
    sonuc = {
        "organs": _organlar(),
        "pose_classifier": {"type": "lateral", "confidence": 0.7},
        "pnp_fit": pnp_fit,
        "anatomic_consistency": {"passed": True, "score": 1.0},
        "kabin_yapilandirmasi": {"yuklendi": True, "hata": None},
        "_overlay_bgr": None,
    }

    class _Clf:
        def predict(self, yol, render=False, target_oid=None):
            return sonuc

    monkeypatch.setattr(air, "_get_or_load_catorgan", lambda: _Clf())
    return air._localize_organ_cpu(np.zeros((8, 8, 3), np.uint8), 2)


def test_KRITIK_ayni_kedi_FARKLI_cozunurlukte_AYNI_cm(air, monkeypatch):
    """Aynı kare 4032 / 1008 px: residual 231,2 / 57,8 px, ölçek 46,24 / 11,56 px/cm → ikisi de ≈ 5,0 cm (px 4 kat farklı)."""
    buyuk = _cpu(air, monkeypatch, {"residual_px": 231.2, "scale_px_per_cm": 46.24, "mirror_warning": False})[7]
    kucuk = _cpu(air, monkeypatch, {"residual_px": 57.8, "scale_px_per_cm": 11.56, "mirror_warning": False})[7]
    assert buyuk["pnp_hata_cm"] == pytest.approx(5.0) and kucuk["pnp_hata_cm"] == pytest.approx(5.0), (
        f"PnP uyum hatası çözünürlüğe bağlı: 4032 px {buyuk.get('pnp_hata_cm')} cm ↔ 1008 px {kucuk.get('pnp_hata_cm')} cm"
    )
    assert buyuk["pnp_hata_px"] != kucuk["pnp_hata_px"], "senaryo: px değerleri çözünürlükle FARKLI olmalı"


def test_KRITIK_GPU_yolu_olcegi_tasir_CPU_ile_PARITE(air, monkeypatch):
    cpu = _cpu(air, monkeypatch, {"residual_px": 231.2, "scale_px_per_cm": 46.24, "mirror_warning": False})
    monkeypatch.setattr(
        air,
        "delegate_infer_sync",
        lambda *a, **k: {
            "organs": [{"id": 2, **_organlar()[2]}],
            "pose_type": "lateral",
            "pnp_residual_px": 231.2,
            "pnp_scale_px_per_cm": 46.24,
            "mirror_warning": False,
            "anatomic_consistency": {"passed": True, "score": 1.0},
            "kabin_uyarisi": None,
            "image_base64": None,
        },
    )
    gpu = air._localize_organ_gpu(np.zeros((8, 8, 3), np.uint8), 2)
    assert gpu[7] == cpu[7] and gpu[7]["pnp_hata_cm"] == pytest.approx(5.0), f"GPU ↔ CPU döküm: {gpu[7]} ↔ {cpu[7]}"


def test_KRITIK_iki_cat_organ_ucu_OLCEGI_tasir():
    """Gömülü uç ve GPU servisi `pnp_scale_px_per_cm` taşır — biri taşımazsa o dağıtımda cm hesaplanamaz (parite)."""
    gomulu = _yanit_alanlari(_fonksiyonlar(ROUTER)["analyze_cat_organ"])
    gpu = _yanit_alanlari(_fonksiyonlar(SERVIS)["infer_cat_organ"])
    assert "pnp_scale_px_per_cm" in gomulu, "gömülü cat_organ ucu PnP ölçeğini TAŞIMIYOR"
    assert "pnp_scale_px_per_cm" in gpu, "GPU cat_organ ucu PnP ölçeğini TAŞIMIYOR → GPU dağıtımında cm hesaplanamaz"


@pytest.mark.parametrize("olcek", [None, 0.0, -3.0, float("nan"), float("inf"), "bozuk"])
def test_KARSIT_olcek_YOK_ya_da_BOZUKSA_cm_yok_ve_dusmez(air, monkeypatch, olcek):
    pnp = {"residual_px": 119.2, "mirror_warning": False}
    if olcek is not None:
        pnp["scale_px_per_cm"] = olcek
    r = _cpu(air, monkeypatch, pnp)
    assert r[7]["pnp_hata_cm"] is None and r[7]["pnp_hata_px"] == pytest.approx(119.2)
    taban = air._extract_organ_target(_organlar(), 2, None)
    assert r[:5] == taban[:5], "PnP gösterimi güven / konum / sürüşü DEĞİŞTİRDİ"
