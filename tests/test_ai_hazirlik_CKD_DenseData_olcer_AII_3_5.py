# -*- coding: utf-8 -*-
"""AII-3.5 — `/api/ai/hazirlik` CKD XAI zinciri, açıklamanın kurulduğu shap ÖZEL API'sini (`shap.utils._legacy.DenseData`) de ölçer.

ÖLÇÜLEN (A3, 2026-10-12, `_inceleme/kayit/k3_x4_ckd.json`): `xai_top_features` arka planı `shap.utils._legacy.DenseData(merkez, adlar,
None, ağırlık)` ile kurar (shap 0.49.1'de özel modül; ağırlık 4. konumsal argüman). Bu ad yoksa (shap yükseltmesi) her CKD açıklaması
`ImportError` → "Açıklama üretilemedi"; ama `_xai_zinciri_durumu()` yalnız npz'yi yüklediği için `ckd_xai_referansi: "ok"`, `hazir: true`
diyor → hazırlık ekranı yeşil, özellik ölü (AI-1'in "spec'te yok → üretimde sessiz ölü" sınıfı). Ağırlıksız.
"""

from __future__ import annotations

import capraz
import pytest


@pytest.fixture()
def durum_fn():
    capraz.paket_yoksa_atla("shap")
    import servers.ai_router as air

    return air._xai_zinciri_durumu


def test_KRITIK_DenseData_YOKSA_hazirlik_CKD_referansini_EKSIK_der(durum_fn, monkeypatch):
    import shap.utils._legacy as leg

    monkeypatch.delattr(leg, "DenseData")
    d = durum_fn()
    assert d.get("ckd_xai_referansi") == "eksik", (
        f"shap DenseData yokken (her CKD açıklaması ImportError) hazırlık 'ckd_xai_referansi'={d.get('ckd_xai_referansi')!r} diyor"
    )
    assert d.get("hazir") is False


def test_KRITIK_DenseData_IMZASI_degisirse_hazirlik_EKSIK_der(durum_fn, monkeypatch):
    import shap.utils._legacy as leg

    class _YeniImza:  # ör. ağırlığı anahtar sözcükle isteyen bir sürüm
        def __init__(self, data, group_names, *, weights=None):
            raise TypeError("imza değişti")

    monkeypatch.setattr(leg, "DenseData", _YeniImza)
    assert durum_fn().get("ckd_xai_referansi") == "eksik"


def test_KARSIT_DenseData_varken_hazirlik_OK(durum_fn):
    assert durum_fn().get("ckd_xai_referansi") == "ok"
