# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""Yara Kapanma (Scratch) — GERÇEK 872MB CPN modeliyle uçtan-uca doğrulama.

Plan §6 "gerçek model" satırı: cell/ teslimi (2026-08-26 23:12, cell.zip) +
release_assets PT + celldetection==0.4.9 kuruluysa koşar; CI'da (hiçbiri yok)
sessizce atlanır. Referanslar sahibin paketinden (Linux/GPU ortamı) — bu yüzden
TOLERANSLI: hücre ±%2, kapanma ±0.5 puan, ort. gap ±%5 (plan v2 bulgu 18:
birebir-eşitlik farklı donanımda kırılgandır).

⚠️ CPU'da model yüklemesi ~30 sn + görüntü başına dakikalar sürebilir — bu dosya
yalnız model+cell mevcut makinelerde (geliştirme/GPU) koşar.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

pytest.importorskip("torch", reason="torch yok (CI) — gerçek-model testi atlanır")
pytest.importorskip("celldetection", reason="celldetection kurulu değil — gerçek-model testi atlanır")
cv2 = pytest.importorskip("cv2")

KOK = Path(__file__).resolve().parents[1]
GIRDI = KOK / "ai_hub" / "PEMF_AI_Test_Girdileri"

if importlib.util.find_spec("ai_hub.inference_paper_dilek_hoca.cell.cpn") is None:
    pytest.skip("cell/cpn.py teslim edilmemiş — gerçek-model testi atlanır", allow_module_level=True)

import ai_hub.inference_paper_dilek_hoca.inference_paper_dilek_hoca as m  # noqa: E402

# PT: modül dizini → pt_coz (release_assets) — yoksa atla (sessiz değil, sebepli)
try:
    if not m.DEFAULT_MODEL.exists():
        from ai_hub.xai_utils.pt_yolu import pt_coz

        pt_coz(m._PT_REL)
except Exception as _e:  # pragma: no cover - ortam koşulu
    pytest.skip(f"CPN PT bulunamadı ({_e}) — gerçek-model testi atlanır", allow_module_level=True)

# Sahibin referansları (4× objektif, pixel_mm=0.0016)
REFERANSLAR = {
    "12a_YaraKapanma_0H.tif": {"n_cells": 1494, "closure_pct": 4.3, "mean_gap_um": 1053.0},
    "12b_YaraKapanma_24H.tif": {"n_cells": 2085, "closure_pct": 29.3, "mean_gap_um": 428.0},
}


@pytest.fixture(scope="module")
def sonuclar():
    """Model BİR KEZ yüklenir (isit → modül cache'i); iki görüntü tam yoldan geçer."""
    cihaz = m.isit()
    assert cihaz is not None, "warmup model yükleyemedi (cell/PT mevcutken)"
    cikti = {}
    for ad in REFERANSLAR:
        yol = GIRDI / ad
        assert yol.exists(), f"test girdisi eksik: {yol}"
        cikti[ad] = m.scratch_analiz(str(yol), scratch_yonu="dikey", pixel_mm=0.0016)
    return cikti


def test_KRITIK_gercek_model_referans_TOLERANSLI(sonuclar):
    for ad, ref in REFERANSLAR.items():
        y = sonuclar[ad]
        assert "uyari" not in y, f"{ad}: gerçek görüntüde 'hücre yok' uyarısı: {y.get('uyari')}"
        n, cp, mg = y["n_cells"], y["closure"]["closure_pct"], y["closure"]["mean_gap_um"]
        assert abs(n - ref["n_cells"]) <= ref["n_cells"] * 0.02, (
            f"{ad}: hücre {n} — referans {ref['n_cells']} ±%2 dışında"
        )
        assert abs(cp - ref["closure_pct"]) <= 0.5, (
            f"{ad}: kapanma %{cp} — referans %{ref['closure_pct']} ±0.5 puan dışında"
        )
        assert abs(mg - ref["mean_gap_um"]) <= ref["mean_gap_um"] * 0.05, (
            f"{ad}: ort. gap {mg}µm — referans {ref['mean_gap_um']}µm ±%5 dışında"
        )


def test_KRITIK_gercek_model_24h_daha_kapali(sonuclar):
    """Çalışmanın asıl sorusu ölçülür: 24H kapanması 0H'den BELİRGİN yüksek (+25 puan ref)."""
    d0 = sonuclar["12a_YaraKapanma_0H.tif"]["closure"]["closure_pct"]
    d24 = sonuclar["12b_YaraKapanma_24H.tif"]["closure"]["closure_pct"]
    assert d24 - d0 > 20, f"Δkapanma {d24 - d0:.1f} puan — referans +25, yön/etki kaybolmuş"


def test_KRITIK_gercek_yol_gorselleri_ve_kucultme(sonuclar):
    """Uçtan-uca sözleşme GERÇEK yolda: 5 görsel + 1280px küçültme + input önizleme."""
    import base64

    import numpy as np

    y = sonuclar["12b_YaraKapanma_24H.tif"]
    for alan in (
        "input_image_base64",
        "seg_image_base64",
        "overlay_image_base64",
        "analysis_image_base64",
        "closure_image_base64",
    ):
        assert y.get(alan), f"gerçek yolda eksik görsel: {alan}"
        img = cv2.imdecode(np.frombuffer(base64.b64decode(y[alan]), np.uint8), cv2.IMREAD_COLOR)
        assert img is not None and img.shape[1] <= 1280, f"{alan}: küçültme kaçmış ({img.shape})"
    assert y["device"] in ("cpu", "cuda:0")
