# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""CKD SHAP AÇIKLAMASI — Faz 1 kalem 5 (docs/xai-entegrasyon-plani.md §4/1.4).

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

# CKD model agirliklari BILEREK repo disi (.gitignore *.onnx/*.pkl — release_assets tek-kaynak).
# CI checkout'unda YOKLAR (kosu b4d223b dersi): gercek-model testleri ACIK reason'la atlanir
# (sessiz kayip degil); endpoint KABLOLAMA testleri mock'la her ortamda kosar.
_CKD_DIR = KOK / "ai_hub" / "inference_human_kidney_disease"
_MODEL_VAR = (_CKD_DIR / "ExtraTrees.onnx").exists() and (_CKD_DIR / "preprocessor.pkl").exists()
gercek_model_gerekir = pytest.mark.skipif(
    not _MODEL_VAR,
    reason="CKD ONNX/preprocessor yerel degil (gitignore'lu model agirligi) — gercek-model testi yalniz modelli ortamda",
)

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
@gercek_model_gerekir
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


# ── 1b) DENETİM 2026-08-28 #04: açıklama YAKINSAMIŞ ve EKSİKSİZ olmalı ───────
# ⚠️ Yukarıdaki test bu üç kusuru GÖREMİYORDU (ölçüldü): `nsamples` 10'a düşürüldüğünde bile
# yeşil kalıyordu, çünkü toplam-kütle eşiği (1e-4) ve "klinik çekirdek kesişimi" gürültüyle de
# sağlanabiliyor. Ölçülen kusurlar:
#   (1) YAKINSAMA YOK — yalnız seed değişince ilk-5 kümesi TAMAMEN değişiyordu (n=60).
#   (2) l1_reg VARSAYILANI ("num_features(10)") 24 özelliğin 14'ünü TAM SIFIRA zorluyordu —
#       aralarında `sc` (KREATİNİN) vardı: böbrek açıklamasında kreatinin katkısı "0.0"du.
#   (3) BASELINE DEJENERASYONU — sentetik "ortalama hasta" modelce %98,99996 CKD sanılıyordu,
#       açıklanabilir kütle 0,0100'e düşüyordu (en kritik hastada en kötü sinyal).


@gercek_model_gerekir
def test_KRITIK_ckd_aciklamasi_YAKINSAMIS():
    """Aynı hasta, farklı global RNG durumları → ilk-5 AYNI olmalı.

    Fonksiyon kendi içinde `seed(0)` kuruyor; bu test global durumu değiştirerek
    tekrarlanabilirliği DEĞİL yakınsamayı ölçer."""
    import numpy as np

    from ai_hub.inference_human_kidney_disease import xai_top_features

    kumeler = []
    for tohum in (100, 200, 300):
        np.random.seed(tohum)
        r = xai_top_features(_HASTA, top_n=5)
        kumeler.append(frozenset(t["feature"] for t in r["top_features"]))
    assert len(set(kumeler)) == 1, (
        f"ilk-5 kümesi RNG durumuna göre değişiyor → açıklama yakınsamamış: {[sorted(k) for k in kumeler]}"
    )


@gercek_model_gerekir
def test_KARSIT_KANIT_eski_yapilandirma_gercekten_KARARSIZDI():
    """⚠️ BU TEST DÜZELTMEYİ DEĞİL, GEREKÇESİNİ KİLİTLER.

    Ölçüldü (mutasyon turunda): yukarıdaki yakınsama testi tek bir ayarı geri almakla kırmızı
    OLMUYOR — düzeltilmiş baseline + `l1_reg=False` ile n=60'ta, hatta n=4'te bile ilk-5
    kararlı (shap alt sınır uyguluyor). Yani kararsızlığın asıl sebebi örnek sayısı değil,
    ESKİ BASELINE ile SEYREKLEŞTİRMENİN BİRLİKTE etkisiydi. O kombinasyonu burada doğrudan
    kurup kararsız olduğunu gösteriyoruz; aksi hâlde "yakınsama" kapısı hiçbir şey kanıtlamaz.

    Kırmızıya dönerse: eski yapılandırma artık kararsız DEĞİL demektir (shap sürümü değişmiş
    olabilir) — o zaman düzeltmenin gerekçesi gözden geçirilmeli.
    """
    import numpy as np
    import pandas as pd
    import shap

    from ai_hub.inference_human_kidney_disease.inference_human_kidney_disease import (
        ALL_FEATURES,
        _aggregate_to_raw,
        _normalise_record,
        _predict_onnx,
        _preprocessor_feature_names,
        _referans_background,
        load_model,
    )

    pre, sess, giris = load_model(None)
    Xp = pre.transform(pd.DataFrame([_normalise_record(_HASTA)], columns=ALL_FEATURES)).astype("float32")
    post = _preprocessor_feature_names(pre)
    eski_bg = _referans_background(post)  # ESKİ dejenere baseline

    def _proba(x):
        p = _predict_onnx(sess, giris, x)
        return np.stack([1 - p, p], axis=1)

    kumeler = []
    durum = np.random.get_state()
    try:
        for tohum in (0, 1, 2):
            np.random.seed(tohum)
            expl = shap.KernelExplainer(_proba, eski_bg)
            sv = expl.shap_values(Xp, nsamples=60, silent=True)  # ESKİ n, ESKİ l1_reg varsayılanı
            sv = np.asarray(sv[1]) if isinstance(sv, list) else np.asarray(sv)
            sv_ckd = sv[..., 1] if sv.ndim == 3 else sv
            ham = _aggregate_to_raw(sv_ckd[0], post)
            ilk5 = sorted(ham.items(), key=lambda kv: -abs(kv[1]))[:5]
            kumeler.append(frozenset(f for f, _ in ilk5))
    finally:
        np.random.set_state(durum)

    assert len(set(kumeler)) > 1, (
        "eski yapılandırma (dejenere baseline + varsayılan l1_reg + n=60) KARARLI çıktı — "
        f"düzeltmenin gerekçesi doğrulanamıyor: {[sorted(k) for k in kumeler]}"
    )


@gercek_model_gerekir
def test_KRITIK_kreatinin_SIFIRA_zorlanmiyor():
    """`l1_reg` seyrekleştirmesi klinik çekirdek özellikleri susturmamalı.

    Ölçüldü: varsayılan `num_features(10)` ile bu hastada `sc` (kreatinin) katkısı TAM 0.0
    dönüyordu — böbrek hastalığı açıklamasında kabul edilemez. `l1_reg=False` ile 0.02+."""
    from ai_hub.inference_human_kidney_disease import xai_top_features

    r = xai_top_features(_HASTA, top_n=24)
    katki = {t["feature"]: t["attribution"] for t in r["top_features"]}
    assert katki.get("sc", 0.0) != 0.0, "kreatinin (sc) katkısı TAM SIFIR — l1_reg özelliği susturuyor"
    sifirlar = [f for f, v in katki.items() if v == 0.0]
    assert len(sifirlar) <= 6, (
        f"{len(sifirlar)}/24 özellik tam sıfır ({sifirlar}) — seyrekleştirme açıklamayı buduyor "
        f"(ölçülen bozuk hâl 14/24 idi)"
    )


@gercek_model_gerekir
def test_KRITIK_baseline_DEJENERE_DEGIL():
    """Açıklanabilir kütle f(x)−f(bg) anlamlı olmalı.

    Eski sentetik baseline'da bu kütle 0,0100'dü (model baseline'ı da %99 CKD sanıyordu);
    klinik-normal referansla ~0,99. Kütle küçükse tüm katkılar gürültüye gömülür."""
    from ai_hub.inference_human_kidney_disease import xai_top_features

    r = xai_top_features(_HASTA, top_n=24)
    kutle = sum(abs(t["attribution"]) for t in r["top_features"])
    assert kutle > 0.2, (
        f"açıklanabilir toplam kütle {kutle:.4f} — baseline hastaya çok yakın, katkılar gürültüde "
        f"(ölçülen bozuk hâl 0,0100)"
    )
    assert r["baseline"] == "klinik_normal_referans", f"baseline etiketi beklenmedik: {r['baseline']}"


@gercek_model_gerekir
def test_KARSIT_KANIT_eski_baseline_gercekten_dejenereydi():
    """Bulgunun kendisini kanıtla: eski sentetik baseline modelce ~CKD sayılıyor.

    Bu test düzeltmeyi değil, DÜZELTME GEREKÇESİNİ kilitler — biri "eski baseline de iyiydi"
    diye geri almak isterse ölçüm burada duruyor."""
    import numpy as np
    import pandas as pd

    from ai_hub.inference_human_kidney_disease.inference_human_kidney_disease import (
        _predict_onnx,
        _preprocessor_feature_names,
        _referans_background,
        load_model,
    )

    pre, sess, giris = load_model(None)
    post = _preprocessor_feature_names(pre)
    eski_bg = _referans_background(post)
    p_eski = float(_predict_onnx(sess, giris, np.asarray(eski_bg, dtype=np.float32))[0])
    assert p_eski > 0.9, (
        f"eski sentetik baseline'ın prob_ckd'si {p_eski:.4f} — bulgunun gerekçesi (baseline'ın "
        f"kendisinin hasta sayılması) artık geçerli değil, düzeltmeyi gözden geçirin"
    )

    from ai_hub.inference_human_kidney_disease.inference_human_kidney_disease import (
        ALL_FEATURES,
        NORMAL_REFERANS,
        _normalise_record,
    )

    yeni_bg = pre.transform(pd.DataFrame([_normalise_record(NORMAL_REFERANS)], columns=ALL_FEATURES))
    p_yeni = float(_predict_onnx(sess, giris, np.asarray(yeni_bg, dtype=np.float32))[0])
    assert p_yeni < 0.2, f"yeni referans hasta da CKD sayılıyor (prob={p_yeni:.4f}) — referans klinik değil"


@gercek_model_gerekir
def test_KRITIK_ckd_xai_DETERMINISTIK():
    from ai_hub.inference_human_kidney_disease import xai_top_features

    a = xai_top_features(_HASTA, top_n=5)
    b = xai_top_features(_HASTA, top_n=5)
    assert a == b, "aynı hastaya iki çağrıda farklı açıklama (kernel örneklemesi seed'siz)"


@gercek_model_gerekir
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


# ── 2) Uç sözleşmesi (KABLOLAMA — model gerektirmez, CI'da da koşar) ─────────
_XAI_SENTINEL = {
    "prob_ckd": 0.91,
    "baseline": "ortalama_hasta",
    "top_features": [{"feature": "htn", "attribution": 0.12}],
}


@pytest.fixture()
def istemci(monkeypatch):
    """Model ağırlıkları gitignore'lu (CI'da yok) → predict_one mock'lanır; ölçülen şey
    UÇ KABLOLAMASI: explain pop'u, total_fields=24, xai alanı, zarif düşüş."""
    import ai_hub.inference_human_kidney_disease as ihd
    import servers.ai_router as air
    import servers.api_server as apis

    monkeypatch.setattr(air, "ai_service_enabled", lambda: False)
    monkeypatch.setattr(
        ihd, "predict_one", lambda features, **k: {"prob_ckd": 0.91, "label": "ckd", "model": "ExtraTrees"}
    )
    return TestClient(apis.app), ihd


def test_KRITIK_endpoint_explain_true_xai_DONER(istemci, monkeypatch):
    client, ihd = istemci
    monkeypatch.setattr(ihd, "xai_top_features", lambda features, **k: _XAI_SENTINEL)
    r = client.post("/api/ai/disease/kidney", json={**_HASTA, "explain": True})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("status") == "success" and "prob_ckd" in body
    assert body.get("total_fields") == 24, (
        f"explain bayrağı alan sayımına SIZDI (total_fields={body.get('total_fields')}) — mevcut şeffaflık sözleşmesi bozuldu"
    )
    assert body.get("xai") == _XAI_SENTINEL, "explain=true iken xai alanı modül fonksiyonundan taşınmadı"


def test_KARSIT_KANIT_explain_yoksa_sozlesme_AYNEN(istemci):
    client, _ihd = istemci
    r = client.post("/api/ai/disease/kidney", json=_HASTA)
    assert r.status_code == 200
    body = r.json()
    assert "xai" not in body and "xai_error" not in body
    assert body.get("total_fields") == 24


def test_KRITIK_xai_hatasi_analizi_DUSURMEZ(istemci, monkeypatch):
    client, ihd = istemci

    def _patla(*a, **k):
        raise RuntimeError("shap patladı (test)")

    monkeypatch.setattr(ihd, "xai_top_features", _patla)
    r = client.post("/api/ai/disease/kidney", json={**_HASTA, "explain": True})
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
