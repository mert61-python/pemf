# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""CAT_DISEASE SHAP AÇIKLAMASI — Faz 1 kalem 3 (xai-entegrasyon-plani.md §4/1.3).

ÖLÇÜLEN DURUM: /api/ai/disease 18-hastalık tahmini döner ama NEDEN'i dönmez; XGBoost.pkl
guii'de ANA model olduğu için SHAP TreeExplainer ek ağırlık/GPU gerektirmeden ms
mertebesinde özellik-katkısı üretebilir (inference(1) _run_xai bunu diske PNG/CSV yazar —
backend'e JSON alan olarak taşınmalı).

DÜZELTME: ai_hub.cat_disease.xai_top_features TEK-KAYNAK fonksiyonu (predictor'ın kendi
pkl modeli üzerinde TreeExplainer; tahmin edilen sınıfın katmanı; top-N |katkı|);
DiseaseInput.explain=true → yanıtta "xai" alanı; XAI hatası analizi ASLA düşürmez
(xai_error alanına düşer); ai_service /infer/disease AYNI fonksiyonla parite (kapı-paritesi
dersi). Jeton: aynı uç → yeni yol yok (Faz 0 karar #6: analizin parçası).
"""

from types import MethodType, SimpleNamespace

import numpy as np
import pytest
from fastapi.testclient import TestClient


def _sahte_predictor():
    """CI-koşulabilir sahte: sklearn RF (TreeExplainer native destekler) + gerçek _encode.
    Sınıf-0 'Coughing_bin' (idx 8) ile GÜÇLÜ ilişkilendirilir → öksürüklü girdide
    Coughing_bin top-3 katkıda olmalı (anlamlılık ölçülür, varlık değil)."""
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.preprocessing import StandardScaler

    from ai_hub.cat_disease.inference_cat_disease import CatDiseasePredictor

    rng = np.random.default_rng(5)
    n = 240
    X = np.zeros((n, 19), dtype=np.float64)
    X[:, 0] = rng.normal(5, 2, n)  # Age
    X[:, 1] = rng.normal(4, 1, n)  # Weight
    X[:, 2] = rng.normal(160, 20, n)  # Heart_Rate
    X[:, 3] = rng.normal(39, 1, n)  # Body_Temperature
    X[:, 4] = rng.normal(5, 2, n)  # Duration_days
    X[:, 5:] = rng.integers(0, 2, (n, 14))
    y = rng.integers(1, 3, n)  # taban: sınıf 1/2
    y[X[:, 8] == 1] = 0  # Coughing=1 → sınıf 0 (deterministik sinyal)
    sc = StandardScaler().fit(X)
    rf = RandomForestClassifier(n_estimators=30, random_state=0).fit(sc.transform(X), y)

    p = SimpleNamespace(scaler=sc, model=rf, diseases=["Solunum", "Sindirim", "Deri"])
    p._encode = MethodType(CatDiseasePredictor._encode, p)
    p.predict = MethodType(CatDiseasePredictor.predict, p)
    return p


_GIRDI = {"age": 3, "weight": 4.2, "hr": 165, "temp": 39.4, "duration": 5, "symptom_indices": [4]}


# ── 1) Modül fonksiyonu: anlamlılık + determinizm ────────────────────────────
def test_KRITIK_xai_top_features_ANLAMLI_katki_doner():
    from ai_hub.cat_disease.inference_cat_disease import FEATURE_NAMES, xai_top_features

    p = _sahte_predictor()
    res = xai_top_features(p, **_GIRDI, top_n=7)
    assert res["disease"] == "Solunum", f"öksürüklü girdi sınıf-0 değil: {res['disease']}"
    tf = res["top_features"]
    assert len(tf) == 7 and all(t["feature"] in FEATURE_NAMES for t in tf)
    ilk3 = [t["feature"] for t in tf[:3]]
    assert "Coughing_bin" in ilk3, (
        f"mühendislenmiş sinyal (Coughing→sınıf0) top-3 katkıda değil: {ilk3} — açıklama anlamsız"
    )
    assert all(isinstance(t["attribution"], float) for t in tf)


def test_KRITIK_xai_top_features_DETERMINISTIK():
    from ai_hub.cat_disease.inference_cat_disease import xai_top_features

    p = _sahte_predictor()
    a = xai_top_features(p, **_GIRDI)
    b = xai_top_features(p, **_GIRDI)
    assert a == b, "aynı girdiye iki çağrıda farklı açıklama (klinik tekrarlanabilirlik yok)"


# ── 2) Uç: explain=true → xai alanı; yokken sözleşme AYNEN ───────────────────
@pytest.fixture()
def istemci(monkeypatch):
    import servers.ai_router as air
    import servers.api_server as apis

    sahte = _sahte_predictor()
    monkeypatch.setattr(air, "ai_service_enabled", lambda: False)
    monkeypatch.setattr(air, "_get_or_load_model", lambda ad, yukleyici: sahte)
    return TestClient(apis.app), air


def test_KRITIK_endpoint_explain_true_xai_DONER(istemci):
    client, _ = istemci
    r = client.post("/api/ai/disease", json={**_GIRDI, "explain": True})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("status") == "success" and body.get("results"), "analiz sözleşmesi bozuldu"
    xai = body.get("xai")
    assert xai and xai.get("top_features"), "explain=true iken yanıtta xai.top_features yok"
    assert xai["disease"] == body["results"][0]["disease"], "açıklama, gösterilen top-1 tahminle uyuşmuyor"


def test_KARSIT_KANIT_explain_yoksa_sozlesme_AYNEN(istemci):
    client, _ = istemci
    r = client.post("/api/ai/disease", json=_GIRDI)
    assert r.status_code == 200
    body = r.json()
    assert "xai" not in body and "xai_error" not in body, "explain istenmeden xai alanı sızdı"


def test_KRITIK_xai_hatasi_analizi_DUSURMEZ(istemci, monkeypatch):
    """Plan kuralı: açıklama İKİNCİL — hatası ana analizi asla düşürmez (zarif düşüş)."""
    client, air = istemci
    import ai_hub.cat_disease.inference_cat_disease as icd

    def _patla(*a, **k):
        raise RuntimeError("shap patladı (test)")

    monkeypatch.setattr(icd, "xai_top_features", _patla)
    r = client.post("/api/ai/disease", json={**_GIRDI, "explain": True})
    assert r.status_code == 200, f"XAI hatası analizi 500'e düşürdü: {r.text}"
    body = r.json()
    assert body.get("status") == "success" and body.get("results")
    assert "xai" not in body and body.get("xai_error"), "hata durumu xai_error ile işaretlenmedi"


# ── 3) parite: ai_service aynı fonksiyonu çağırır ────────────────────────────
def test_YAPISAL_ai_service_disease_XAI_paritesi():
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "ai_service" / "app.py").read_text(encoding="utf-8")
    i = src.index('post("/infer/disease")')
    govde = src[i : src.index('post("/infer/', i + 10)]
    assert "xai_top_features" in govde and "explain" in govde, (
        "GPU mikroservis /infer/disease XAI paritesi yok — router'da olan açıklama :8100 yolunda kaybolur"
    )
