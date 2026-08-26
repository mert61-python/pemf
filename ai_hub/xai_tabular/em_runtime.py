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
- hizli_sensitivity: CANLI yol (öneri-onay ekranı) — 7 ONNX forward, D-KANALLARI (ilk
  n_duty çıktı) üzerinden, PNG/SHAP YOK, JSON döner. SHAP'ın mean-agregasyonu 22/23
  heterojen çıktıyı sulandırdığı için canlı anlatı D-hedeflidir (plan §4/1.2).
- batch_xai: Mod-2 seans-sonrası/batch — run_em_xai (sensitivity+SHAP+CSV+PNG) ref_stats'la.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Sequence

import numpy as np

from .em_sensitivity import EM_FEATURES, run_em_xai, sensitivity_analysis


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
            f"{p} yok — EM tek-örnek XAI referanssız DEJENERE olur. "
            "build_tools/make_em_xai_ref_stats.py ile üretin."
        )
    d = np.load(p, allow_pickle=False)
    return {"std": np.asarray(d["std"], dtype=np.float64),
            "background": np.asarray(d["background"], dtype=np.float64)}


def hizli_sensitivity(predictor, ref_stats: dict,
                       x: float, y: float, z: float, organ_id: float,
                       achieved_B: float, duty_sum: float,
                       *, n_duty: int = 7, top_n: int = 3) -> list[dict]:
    """Canlı yol: tek nokta için hafif duyarlılık (7+1 forward; PNG/SHAP yok).

    D-kanalları (ilk n_duty çıktı = bobin duty'leri) üzerinden ölçer: "önerilen dozu en
    çok hangi girdi belirledi". Döner: [{"feature", "etki"}, ...] |Δ| azalan sırada.
    """
    fn = predict_raw_fn(predictor)
    X = np.array([[x, y, z, organ_id, achieved_B, duty_sum]], dtype=np.float64)
    sens = sensitivity_analysis(lambda A: fn(A)[:, :n_duty], X, ref_std=ref_stats["std"])
    vals = np.asarray(sens["delta_abs_mean"], dtype=np.float64)
    order = np.argsort(-vals)[: int(top_n)]
    return [{"feature": EM_FEATURES[int(i)], "etki": round(float(vals[int(i)]), 4)} for i in order]


def batch_xai(predictor, ref_stats: dict, X: np.ndarray, out_dir,
               *, output_labels: Sequence[str] | None = None,
               sample_ids: Sequence[str] | None = None,
               run_shap: bool = True, shap_nsamples: int = 60) -> dict:
    """Mod-2: seans-sonrası/batch tam paket (sensitivity+SHAP+CSV+PNG+~200KB)."""
    return run_em_xai(
        predict_raw_fn(predictor), np.asarray(X, dtype=np.float64), out_dir,
        output_labels=output_labels, sample_ids=sample_ids,
        run_shap=run_shap, shap_nsamples=shap_nsamples, ref_stats=ref_stats,
    )
