# -*- coding: utf-8 -*-
"""AI1.X6 — EM ×3 (kedi / fantom / petri) canlı "dozu en çok belirleyen" açıklaması: yığından bağımsız, eğitim std'li merkezi fark,
organ_id kategorik, öğrenilmemiş ve eğitim aralığı dışı İŞARETLİ (hoca XAI v3: `xai_tabular/em_sensitivity_v2.py`,
`inference_em_*/xai_train_ref.npz`).

ÖLÇÜLEN DURUM (2026-10-11, gerçek EM modelleri; `DUZELTME-AI1.md` X6):
  * ata v1 (std = sorgu yığınının std'si): tek noktada açıklama ≈0, aynı nokta farklı yığında ×1,9–3,4 farklı (hocanın E1/E2'si).
    guii'nin canlı yolu bunu Faz 1'de `ref_std` ile kapatmıştı (önceden kapalı).
  * ama guii'de em_petri x/y/z/organ_id etkisi TAM 0 iken "x · y" ilk-3'e girip onay ekranında "dozu belirleyen" yazıyordu; organ_id
    eğitimde SABİT (petri CSV'sinde hep 0) ama guii referansı std'yi 0,5'e zorlayıp "canlandırıyordu" → öğrenilmemiş işaret yok;
    organ_id kesirli (±0,19 organ) kaydırılıyordu; eğitim aralığı dışı değer işaretlenmiyordu (petri hattı organ_id=1 gönderir —
    eğitimde YOK).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

KOK = Path(__file__).resolve().parents[1]
F = ["x", "y", "z", "organ_id", "achieved_B", "duty_sum"]
MODULLER = {
    "em_kedi": ("ai_hub/em_kedi", "training_archive/em_kedi/training_data_kedi_v5.csv"),
    "em_fantom": ("ai_hub/inference_em_fantom", "training_archive/em_phantom/training_data_phantom_v7.csv"),
    "em_petri": ("ai_hub/inference_em_petri", "training_archive/em_petri/training_data_petri_v5.csv"),
}


# ── 1) eğitim referansı: depodaki eğitim CSV'siyle BİREBİR (kaynak kanıtı; hocanın dosyasıyla dizi-aynı) ─────────────
@pytest.mark.parametrize("ad", sorted(MODULLER))
def test_KRITIK_egitim_referansi_DEPODAKI_egitim_CSVsiyle_birebir(ad):
    pd = pytest.importorskip("pandas")
    from ai_hub.xai_tabular.em_runtime import load_egitim_ref

    dizin, csv = MODULLER[ad]
    ref = load_egitim_ref(KOK / dizin)
    X = pd.read_csv(KOK / csv, usecols=F)[F].to_numpy(np.float64)
    for anahtar, beklenen in (("min", X.min(0)), ("max", X.max(0)), ("std", X.std(0)), ("mean", X.mean(0))):
        assert np.allclose(ref[anahtar], beklenen, rtol=1e-9, atol=1e-12), (
            f"{ad} {anahtar}: {ref[anahtar]} ≠ CSV {beklenen}"
        )
    if ad == "em_petri":
        assert ref["std"][3] == 0.0 and ref["min"][3] == ref["max"][3] == 0.0, "petri organ_id eğitimde sabit değil mi?"


# ── 2) yöntem anlamı (ağırlıksız, sahte model) ─────────────────────────────────────────────────────────────────────
def _ref(
    std=(10.0, 10.0, 10.0, 1.0, 1e-4, 0.3), lo=(-100, -100, -100, 0, 0.0009, 1.0), hi=(100, 100, 100, 6, 0.0011, 3.0)
):
    return {"min": np.array(lo, float), "max": np.array(hi, float), "std": np.array(std, float), "mean": np.zeros(6)}


def test_KRITIK_MERKEZI_fark_ve_YIGINDAN_bagimsiz():
    """f = x² + y (D kanallarına): x=0'da merkezi fark 0, ileri fark (eski yöntem) 0,01·std² > 0 verirdi; y'nin etkisi 0,1·std.
    Aynı satır tek başına ve rastgele bir yığının içinde AYNI sonucu verir (std yığından alınmaz)."""
    from ai_hub.xai_tabular.em_runtime import merkezi_duyarlilik

    def fn(X):
        d = (X[:, 0] ** 2 + X[:, 1])[:, None]
        return np.repeat(d, 9, axis=1)

    ref = _ref()
    p = np.array([[0.0, 5.0, 1.0, 2.0, 0.001, 2.0]])
    S1 = merkezi_duyarlilik(fn, p, ref)[0]
    assert S1[0] == pytest.approx(0.0, abs=1e-12), f"x²'nin x=0'daki duyarlılığı {S1[0]} — merkezi fark değil"
    assert S1[1] == pytest.approx(0.1 * 10.0), f"y'nin etkisi {S1[1]} ≠ 0,1·std"
    rng = np.random.default_rng(3)
    for _ in range(3):
        yigin = np.vstack([rng.normal(size=(int(rng.integers(2, 7)), 6)) * 20, p])
        Sy = merkezi_duyarlilik(fn, yigin, ref)[-1]
        assert np.allclose(Sy, S1, equal_nan=True), "aynı nokta farklı yığında farklı açıklama (yığına bağlı std)"


def test_KRITIK_organ_KATEGORIK_komsu_deger_ve_ogrenilmemis():
    from ai_hub.xai_tabular.em_runtime import merkezi_duyarlilik

    goru = []

    def fn(X):
        goru.extend(X[:, 3].tolist())
        return np.repeat(X[:, 3:4] * 0.5, 9, axis=1)

    merkezi_duyarlilik(
        fn, np.array([[0, 0, 0, 0.0, 0.001, 2.0], [0, 0, 0, 6.0, 0.001, 2.0], [0, 0, 0, 3.0, 0.001, 2.0]]), _ref()
    )
    assert set(goru) <= {0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0}, f"organ_id kesirli kaydırıldı: {sorted(set(goru))}"
    assert {1.0, 2.0, 4.0, 5.0} <= set(goru), "organ_id ±1 komşu değere kaydırılmadı"
    S = merkezi_duyarlilik(
        lambda X: np.repeat(X[:, 3:4], 9, axis=1),
        np.array([[0, 0, 0, 0.0, 0.001, 2.0]]),
        _ref(std=(10, 10, 10, 0.0, 1e-4, 0.3), hi=(100, 100, 100, 0, 0.0011, 3.0)),
    )[0]
    assert np.isnan(S[3]), "eğitimde sabit organ_id 'öğrenilmemiş' (NaN) değil"


def _sahte_tahminci(fn):
    p = SimpleNamespace(sy=SimpleNamespace(inverse_transform=lambda y: np.asarray(y, np.float64)))
    p._build_input = lambda x, y, z, o, B, d: np.column_stack([np.atleast_1d(v) for v in (x, y, z, o, B, d)]).astype(
        np.float64
    )
    p._run_onnx = fn
    return p


def test_KRITIK_sifir_etki_BELIRLEYEN_degil_ogrenilmemis_ve_egitim_disi_ISARETLI():
    from ai_hub.xai_tabular.em_runtime import hizli_sensitivity

    ref = _ref(std=(10, 10, 10, 0.0, 1e-4, 0.3), hi=(100, 100, 100, 0, 0.0011, 3.0))  # organ sabit (petri gibi)
    p = _sahte_tahminci(lambda X: np.repeat(X[:, 5:6] * 2.0, 9, axis=1))  # YALNIZ duty_sum etkili
    r = hizli_sensitivity(
        p, ref, 10.0, 20.0, 150.0, 1.0, 0.001, 2.0, top_n=3
    )  # z=150 > 100 ve organ 1 > 0 → eğitim dışı
    belirleyen = [t["feature"] for t in r if not t.get("ogrenilmemis") and t.get("surukleyen", True)]
    assert belirleyen == ["duty_sum"], f"etkisi 0 olan özellik 'belirleyen' gösteriliyor: {r}"
    assert {"feature": "organ_id", "etki": None, "ogrenilmemis": True} in r, f"öğrenilmemiş işareti yok: {r}"
    disi = {t["feature"] for t in r if t.get("egitim_disi")}
    assert disi == {"z", "organ_id"}, f"eğitim aralığı dışı işaretleri {disi}"


# ── 3) gerçek ağırlık ───────────────────────────────────────────────────────────────────────────────────────────────
_NOKTALAR = {  # hocanın test_data/points_in_domain.csv'lerinden
    "em_kedi": [-92.0, -60.0, -187.85, 0.0, 0.0010824567871168, 2.248717784881592],
    "em_petri": [68.0, 140.0, 82.15, 0.0, 0.0009879500139504, 2.68152403831482],
}


@pytest.fixture(scope="module")
def em_modelleri():
    pytest.importorskip("onnxruntime")
    pytest.importorskip("sklearn")
    from golden.eser import atla, eser_var_mi
    from golden.yukleyici import em_tahminci

    if not eser_var_mi("ai_hub/em_kedi/BiLSTM_XXL_Raw.onnx"):
        atla("em_kedi ağırlığı yok")
    try:
        return {"em_kedi": em_tahminci("em_kedi"), "em_petri": em_tahminci("em_petri")}
    except FileNotFoundError as e:
        atla(f"EM ağırlığı yok: {e}")


def test_KRITIK_gercek_kedi_ve_petri_ACIKLAMASI(em_modelleri):
    from ai_hub.xai_tabular.em_runtime import hizli_sensitivity, load_egitim_ref, merkezi_duyarlilik, predict_raw_fn

    for ad, nokta in _NOKTALAR.items():
        ref = load_egitim_ref(KOK / MODULLER[ad][0])
        r1 = hizli_sensitivity(em_modelleri[ad], ref, *nokta)
        assert r1 == hizli_sensitivity(em_modelleri[ad], ref, *nokta), f"{ad}: deterministik değil"
        belirleyen = [t for t in r1 if not t.get("ogrenilmemis") and t.get("surukleyen", True)]
        assert belirleyen and all(t["etki"] > 0 for t in belirleyen), f"{ad}: belirleyen yok / etki 0: {r1}"
        # yığından bağımsız: noktanın satırı, rastgele eğitim-içi noktalarla birlikte de aynı
        fn = predict_raw_fn(em_modelleri[ad])
        rng = np.random.default_rng(1)
        yigin = np.vstack([ref["min"] + rng.random((4, 6)) * (ref["max"] - ref["min"]), np.array([nokta])])
        tek = merkezi_duyarlilik(fn, np.array([nokta]), ref)[0]
        assert np.allclose(merkezi_duyarlilik(fn, yigin, ref)[-1], tek, rtol=1e-6, equal_nan=True), (
            f"{ad}: yığına bağlı"
        )
        if ad == "em_petri":
            assert {"feature": "organ_id", "etki": None, "ogrenilmemis": True} in r1, (
                f"petri organ_id öğrenilmemiş değil: {r1}"
            )
            assert [t["feature"] for t in belirleyen] == ["duty_sum"], f"petri: etkisi 0 olanlar belirleyen: {r1}"
        else:
            assert not any(t.get("ogrenilmemis") for t in r1), f"kedi'de öğrenilmemiş işareti olmamalı: {r1}"


def test_KRITIK_hazirlik_probu_EGITIM_REFERANSI_eksigini_GORUR(monkeypatch, tmp_path):
    """`/api/ai/hazirlik` XAI zinciri: modül dizininde xai_ref_stats.npz VAR ama xai_train_ref.npz YOKSA modül eksik sayılır."""
    import importlib.util as iu

    import servers.ai_router as air

    (tmp_path / "xai_ref_stats.npz").write_bytes(b"x")
    orj = iu.find_spec

    def sahte(ad, *a, **k):
        if ad == "ai_hub.em_kedi":
            return SimpleNamespace(submodule_search_locations=[str(tmp_path)])
        return orj(ad, *a, **k)

    assert "em_kedi" not in air._xai_zinciri_durumu()["em_ref_stats_eksik"], "gerçek modül dizini eksik görünüyor"
    monkeypatch.setattr(iu, "find_spec", sahte)
    d = air._xai_zinciri_durumu()
    assert "em_kedi" in d["em_ref_stats_eksik"] and d["hazir"] is False, d
