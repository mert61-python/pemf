# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""CKD SHAP AÇIKLAMASI — Faz 1 kalem 5 (xai-entegrasyon-plani.md §4/1.4).

ÖLÇÜLEN DURUM: /api/ai/disease/kidney prob_ckd + imputed/low_evidence şeffaflığı döner ama
hangi klinik özelliğin kararı sürüklediğini dönmez. Model ONNX-only → SHAP KernelExplainer
tek yol (PT'siz XAI kanıtı). ⚠️ Gelen kodda TEK-HASTA DEJENERASYONU: background=kaydın
kendisi → f(x)−E[f(bg)]=0 → tüm katkılar ~0 (EM'dekiyle aynı sınıf hata).

DÜZELTME: ai_hub.inference_human_kidney_disease.xai_top_features — 'ortalama-hasta'
referans background'u (post-uzayda numeric=0 [standardize ortalama], one-hot=0.5
[bilgisiz]) ile tek-hasta katkıları "ortalamaya göre" okunur; seed save/restore ile
deterministik; 24 ham klinik özelliğe agrege. explain=true → yanıtta 'xai'; hatası
analizi ASLA düşürmez; mevcut sözleşme (total_fields=24 dahil) AYNEN korunur;
ai_service /infer/kidney_disease paritesi.
"""

from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

KOK = Path(__file__).resolve().parents[1]

# Belirgin CKD tablosu (doc-doğrulanmış klinik sıralama: htn > hemo > ane > pc > rbc > sc > bp)
_HASTA = {
    "age": 62,
    "bp": 90,
    "sg": 1.01,
    "al": 3,
    "su": 0,
    "bgr": 140,
    "bu": 55,
    "sc": 2.8,
    "sod": 132,
    "pot": 4.9,
    "hemo": 9.1,
    "pcv": 29,
    "wc": 9800,
    "rc": 3.9,
    "rbc": "abnormal",
    "pc": "abnormal",
    "pcc": "present",
    "ba": "notpresent",
    "htn": "yes",
    "dm": "yes",
    "cad": "no",
    "appet": "poor",
    "pe": "yes",
    "ane": "yes",
}


# ── 1) Modül fonksiyonu ──────────────────────────────────────────────────────
def test_KRITIK_ckd_xai_tek_hasta_DEJENERE_DEGIL_ve_klinik_cekirdek():
    from ai_hub.inference_human_kidney_disease import ALL_FEATURES, xai_top_features

    res = xai_top_features(_HASTA, top_n=7)
    tf = res["top_features"]
    assert len(tf) == 7 and all(t["feature"] in ALL_FEATURES for t in tf)
    toplam = sum(abs(t["attribution"]) for t in tf)
    assert toplam > 1e-4, f"tek-hasta SHAP ~0 (toplam |katkı|={toplam:.2e}) — background=kayıt dejenerasyonu sürüyor"
    ilk5 = {t["feature"] for t in tf[:5]}
    assert ilk5 & {"htn", "hemo", "sc", "dm", "ane"}, (
        f"klinik çekirdek (htn/hemo/sc/dm/ane) top-5'te yok: {ilk5} — agregasyon/katman seçimi şüpheli"
    )
    assert 0.0 <= res["prob_ckd"] <= 1.0


def test_KRITIK_ckd_xai_DETERMINISTIK():
    from ai_hub.inference_human_kidney_disease import xai_top_features

    a = xai_top_features(_HASTA, top_n=5)
    b = xai_top_features(_HASTA, top_n=5)
    assert a == b, "aynı hastaya iki çağrıda farklı açıklama (kernel örneklemesi seed'siz)"


def test_KARSIT_KANIT_referans_background_ortalama_hasta():
    """Baseline 'ortalama-hasta': post-uzayda numeric=0, one-hot=0.5 — tek satır, deterministik."""
    from ai_hub.inference_human_kidney_disease import _preprocessor_feature_names, _referans_background, load_model

    pre, _s, _i = load_model(None)
    adlar = _preprocessor_feature_names(pre)
    bg = _referans_background(adlar)
    assert bg.shape == (1, len(adlar))
    for j, ad in enumerate(adlar):
        beklenen = 0.0 if ad.startswith("num__") else 0.5
        assert bg[0, j] == pytest.approx(beklenen), f"{ad}: {bg[0, j]} != {beklenen}"


# ── 2) Uç sözleşmesi ─────────────────────────────────────────────────────────
@pytest.fixture()
def istemci():
    import servers.api_server as apis

    return TestClient(apis.app)


def test_KRITIK_endpoint_explain_true_xai_DONER(istemci, monkeypatch):
    import servers.ai_router as air

    monkeypatch.setattr(air, "ai_service_enabled", lambda: False)
    r = istemci.post("/api/ai/disease/kidney", json={**_HASTA, "explain": True})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("status") == "success" and "prob_ckd" in body
    assert body.get("total_fields") == 24, (
        f"explain bayrağı alan sayımına SIZDI (total_fields={body.get('total_fields')}) — mevcut şeffaflık sözleşmesi bozuldu"
    )
    xai = body.get("xai")
    assert xai and xai.get("top_features"), "explain=true iken xai.top_features yok"


def test_KARSIT_KANIT_explain_yoksa_sozlesme_AYNEN(istemci, monkeypatch):
    import servers.ai_router as air

    monkeypatch.setattr(air, "ai_service_enabled", lambda: False)
    r = istemci.post("/api/ai/disease/kidney", json=_HASTA)
    assert r.status_code == 200
    body = r.json()
    assert "xai" not in body and "xai_error" not in body
    assert body.get("total_fields") == 24


def test_KRITIK_xai_hatasi_analizi_DUSURMEZ(istemci, monkeypatch):
    import ai_hub.inference_human_kidney_disease as ihd
    import servers.ai_router as air

    monkeypatch.setattr(air, "ai_service_enabled", lambda: False)

    def _patla(*a, **k):
        raise RuntimeError("shap patladı (test)")

    monkeypatch.setattr(ihd, "xai_top_features", _patla)
    r = istemci.post("/api/ai/disease/kidney", json={**_HASTA, "explain": True})
    assert r.status_code == 200, f"XAI hatası analizi düşürdü: {r.text}"
    body = r.json()
    assert body.get("status") == "success" and body.get("xai_error") and "xai" not in body


# ── 3) parite ────────────────────────────────────────────────────────────────
def test_YAPISAL_ai_service_kidney_disease_XAI_paritesi():
    src = (KOK / "ai_service" / "app.py").read_text(encoding="utf-8")
    i = src.index('post("/infer/kidney_disease")')
    govde = src[i : src.index('post("/infer/', i + 10)]
    assert "xai_top_features" in govde and "explain" in govde, (
        ":8100 kidney_disease XAI paritesi yok — kapı-paritesi dersi"
    )
