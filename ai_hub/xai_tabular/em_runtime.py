# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""em_runtime.py — EM üçlüsü (em_kedi/em_fantom/em_petri) XAI yapıştırıcısı (Faz 1.2).

TEK-KAYNAK: üç modülün ince sarmalayıcıları buradaki fonksiyonları çağırır (çift formül /
kopya-kod yok). Predictor sözleşmesi (üçünde ortak): _build_input(x,y,z,organ_id,B,duty)
-> (N,6) float32; _run_onnx(X_sc) -> (N,O) ölçekli; sy.inverse_transform -> ham çıktı.

- predict_raw_fn: HAM (N,6) girdi -> HAM (N,O) çıktı closure (XAI predict_fn sözleşmesi).
- load_ref_stats: ai_hub/<modül>/xai_ref_stats.npz — eğitim-dağılımı std+background
  (build_tools/make_em_xai_ref_stats.py; scaler.scale_ + eğitim CSV çapraz-kontrollü).
  Tek-örnek (canlı) XAI bu referanslar OLMADAN dejenere olur (em_sensitivity ValueError).
- hizli_sensitivity: CANLI yol (öneri-onay ekranı) — D-KANALLARI (ilk n_duty çıktı) üzerinden, PNG/SHAP YOK, JSON
  döner. SHAP'ın mean-agregasyonu 22/23 heterojen çıktıyı sulandırdığı için canlı anlatı D-hedeflidir (plan §4/1.2).
  AI1.X6 (hoca XAI v3): yöntem eğitim std'li MERKEZİ fark + organ_id kategorik + öğrenilmemiş / eğitim aralığı dışı
  işareti; referans `load_egitim_ref` (xai_train_ref.npz — eğitim CSV'sinin tamamı).
- batch_xai: Mod-2 seans-sonrası/batch — run_em_xai (sensitivity+SHAP+CSV+PNG) ref_stats'la.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Sequence

import numpy as np

from .em_sensitivity import EM_FEATURES, run_em_xai


def predict_raw_fn(predictor) -> Callable[[np.ndarray], np.ndarray]:
    """(N,6) HAM girdi -> (N,O) HAM çıktı. Kolon sırası EM_FEATURES ile aynı."""

    def _fn(X: np.ndarray) -> np.ndarray:
        X = np.asarray(X, dtype=np.float64)
        X_sc = predictor._build_input(X[:, 0], X[:, 1], X[:, 2], X[:, 3], X[:, 4], X[:, 5])
        return np.asarray(predictor.sy.inverse_transform(predictor._run_onnx(X_sc)), dtype=np.float64)

    return _fn


def load_ref_stats(module_dir: str | Path) -> dict:
    """xai_ref_stats.npz -> {"std": (6,), "background": (M,6)}. Yoksa FileNotFoundError
    (sessiz dejenere yerine açık hata — üretim: build_tools/make_em_xai_ref_stats.py)."""
    p = Path(module_dir) / "xai_ref_stats.npz"
    if not p.exists():
        raise FileNotFoundError(
            f"{p} yok — EM tek-örnek XAI referanssız DEJENERE olur. build_tools/make_em_xai_ref_stats.py ile üretin."
        )
    d = np.load(p, allow_pickle=False)
    return {"std": np.asarray(d["std"], dtype=np.float64), "background": np.asarray(d["background"], dtype=np.float64)}


def load_egitim_ref(module_dir: str | Path) -> dict:
    """xai_train_ref.npz -> {"min", "max", "std", "mean"} (6,) — EĞİTİM CSV'sinin TAMAMINDAN (AI1.X6, hoca XAI v3
    `xai_train_ref.npz`; depodaki `training_archive` CSV'leriyle birebir — kapı testi doğrular). Yoksa / bozuksa açık hata."""
    p = Path(module_dir) / "xai_train_ref.npz"
    if not p.exists():
        raise FileNotFoundError(f"{p.name} yok — EM açıklaması eğitim referanssız üretilmez (kurulum eksik)")
    with np.load(p, allow_pickle=False) as d:
        ref = {k: np.asarray(d[k], dtype=np.float64) for k in ("min", "max", "std", "mean")}
    if any(v.shape != (len(EM_FEATURES),) or not np.isfinite(v).all() for v in ref.values()) or (ref["std"] < 0).any() or (
        ref["min"] > ref["max"]
    ).any():
        raise ValueError(f"{p.name} bozuk (beklenen {len(EM_FEATURES)} özellik için sonlu min/max/std/mean)")
    return ref


#: etkisi bundan küçük özellik "dozu belirleyen" sayılmaz (ölçüldü: em_petri x/y/z/organ_id etkisi TAM 0 iken ilk-3'e girip
#: onay ekranında "belirleyen" yazıyordu).
ETKI_ESIGI = 1e-9


def merkezi_duyarlilik(fn: Callable[[np.ndarray], np.ndarray], X: np.ndarray, egitim_ref: dict,
                       *, n_duty: int = 7, delta_frac: float = 0.10) -> np.ndarray:
    """(N, F) yerel duyarlılık — HER SATIR KENDİ BAŞINA (yığından bağımsız; hoca v2 `sensitivity_v2` yöntemi):
    sürekli özellik: |f(x + d) − f(x − d)| / 2, d = delta_frac · EĞİTİM std'si (merkezi fark); organ_id KATEGORİK: komşu geçerli
    değere (±1, eğitim aralığına kırpılır); eğitimde SABİT özellik (std 0) → NaN ("öğrenilmemiş"). Hedef = ilk n_duty çıktının
    (bobin duty'leri) ort. |Δ| — guii'nin klinik sorusu: "önerilen duty'leri en çok ne değiştirir"."""
    X = np.asarray(X, dtype=np.float64)
    N, F = X.shape
    S = np.full((N, F), np.nan)
    for j in range(F):
        s = float(egitim_ref["std"][j])
        if not s > 0.0:
            continue
        Xp, Xm = X.copy(), X.copy()
        if EM_FEATURES[j] == "organ_id":
            lo, hi = float(egitim_ref["min"][j]), float(egitim_ref["max"][j])
            Xp[:, j] = np.clip(np.round(X[:, j]) + 1.0, lo, hi)
            Xm[:, j] = np.clip(np.round(X[:, j]) - 1.0, lo, hi)
        else:
            Xp[:, j] += delta_frac * s
            Xm[:, j] -= delta_frac * s
        fark = np.abs(fn(Xp)[:, :n_duty] - fn(Xm)[:, :n_duty]).mean(axis=1)
        if EM_FEATURES[j] == "organ_id":
            # ⚠️ AII-2.5: UÇ değerde (kedi 0 / 6, fantom 0 / 1) kırpma bir tarafı sıfırlar → kapsanan adım 2 değil 1. Sabit /2 uçta
            # adım etkisini YARIYA indiriyor, onay ekranının ilk-3'ünü değiştiriyordu (ölçüldü). Bölen = kapsanan kategori adımı.
            adim = Xp[:, j] - Xm[:, j]
            S[:, j] = np.where(adim > 0, fark / np.where(adim > 0, adim, 1.0), 0.0)
        else:
            S[:, j] = fark / 2.0
    return S


def hizli_sensitivity(
    predictor,
    egitim_ref: dict,
    x: float,
    y: float,
    z: float,
    organ_id: float,
    achieved_B: float,
    duty_sum: float,
    *,
    n_duty: int = 7,
    top_n: int = 3,
) -> list[dict]:
    """Canlı yol (AI Pro öneri-onay ekranı): tek nokta için hafif duyarlılık (2·5+1 forward; PNG/SHAP yok).

    AI1.X6 (hoca XAI v3 `xai_tabular/em_sensitivity_v2.py`): yöntem `merkezi_duyarlilik` (eğitim std'si, merkezi fark,
    organ_id kategorik, sabit özellik "öğrenilmemiş"). Döner (sıra korunur):
      * dozu belirleyenler: [{"feature", "etki"}] |Δ| azalan, en çok top_n, YALNIZ etki > ETKI_ESIGI;
        değeri EĞİTİM ARALIĞI DIŞINDAYSA "egitim_disi": True (açıklama ekstrapolasyondur),
      * eğitim aralığı dışındaki ama belirleyen olmayan özellik: {"feature", "etki", "egitim_disi": True, "surukleyen": False},
      * öğrenilmemiş özellik: {"feature", "etki": None, "ogrenilmemis": True}.
    """
    fn = predict_raw_fn(predictor)
    X = np.array([[x, y, z, organ_id, achieved_B, duty_sum]], dtype=np.float64)
    S = merkezi_duyarlilik(fn, X, egitim_ref, n_duty=n_duty)[0]
    disi = {EM_FEATURES[j] for j in range(len(EM_FEATURES))
            if not (egitim_ref["min"][j] <= X[0, j] <= egitim_ref["max"][j])}
    ogrenilmemis = [EM_FEATURES[j] for j in range(len(EM_FEATURES)) if np.isnan(S[j])]
    adaylar = [j for j in np.argsort(-np.nan_to_num(S, nan=-1.0)) if not np.isnan(S[j]) and S[j] > ETKI_ESIGI]
    surukleyen = [int(j) for j in adaylar[: int(top_n)]]
    sonuc = []
    for j in surukleyen:
        d = {"feature": EM_FEATURES[j], "etki": round(float(S[j]), 4)}
        if EM_FEATURES[j] in disi:
            d["egitim_disi"] = True
        sonuc.append(d)
    for j in range(len(EM_FEATURES)):
        if EM_FEATURES[j] in disi and j not in surukleyen:
            sonuc.append({"feature": EM_FEATURES[j], "etki": None if np.isnan(S[j]) else round(float(S[j]), 4),
                          "egitim_disi": True, "surukleyen": False})
    sonuc += [{"feature": ad, "etki": None, "ogrenilmemis": True} for ad in ogrenilmemis]
    return sonuc


def batch_xai(
    predictor,
    ref_stats: dict,
    X: np.ndarray,
    out_dir,
    *,
    output_labels: Sequence[str] | None = None,
    sample_ids: Sequence[str] | None = None,
    run_shap: bool = True,
    shap_nsamples: int = 200,
    shap_output_agg: str = "duty",
    egitim_ref: dict | None = None,
) -> dict:
    """Mod-2: seans-sonrası/batch tam paket (sensitivity+SHAP+CSV+PNG+~200KB).

    SHAP varsayılanı 'duty' (§KALAN A7 wiring, 2026-08-27): hizli_sensitivity ile aynı
    klinik soru — "önerilen DOZU ne belirledi". mean-agregasyon 23 heterojen çıktıda
    (D7+faz14+E2) duty sinyalini sulandırıyordu (test: duty-sürücü özellik mean'de top-1
    OLMUYOR, duty'de OLUYOR — mühendislenmiş karşıt-kanıt).

    AI1.X10 (hoca XAI v3): egitim_ref (xai_train_ref.npz) → yığından bağımsız merkezi-fark duyarlılığı + domain_check.csv
    + öğrenilmemiş özellik NaN; shap_nsamples 60 → 200: 6 özellikte ≥ 62 koalisyon TAM sayılır → aynı noktanın SHAP'ı
    tek başına ve yığında AYNI (ölçüldü: 60'ta x katkısı 0,000187 ↔ 0,000059)."""
    return run_em_xai(
        predict_raw_fn(predictor),
        np.asarray(X, dtype=np.float64),
        out_dir,
        output_labels=output_labels,
        sample_ids=sample_ids,
        run_shap=run_shap,
        shap_nsamples=shap_nsamples,
        ref_stats=ref_stats,
        shap_output_agg=shap_output_agg,
        egitim_ref=egitim_ref,
    )
