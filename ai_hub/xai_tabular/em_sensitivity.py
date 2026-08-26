"""em_sensitivity.py — em_fantom / em_kedi / em_petri icin XAI helper.

Bu 3 modul ayni yapida (6-dim tabular giris -> cok-hedef regression):
    input:   x, y, z, organ_id, achieved_B, duty_sum
    output:  D(7) coil duty, sin(P)(7)+cos(P)(7) faz, E (2)

Iki tur analiz uretilir:
    1. SHAP KernelExplainer over predict callable (yavas ama tam attribution)
    2. Feature sensitivity table (hizli, +/- delta) — her feature'i +delta kaydirinca
       output'ta ortalama mutlak degisim

Kullanim (her inference_em_*.py icinde):
    from xai_tabular.em_sensitivity import run_em_xai
    run_em_xai(predict_fn, X, feature_names=[...], out_dir=..., target_output_idx=[...])
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Sequence

import numpy as np

EM_FEATURES = ["x", "y", "z", "organ_id", "achieved_B", "duty_sum"]


def sensitivity_analysis(predict_fn: Callable[[np.ndarray], np.ndarray],
                          X: np.ndarray,
                          feature_names: Sequence[str] = EM_FEATURES,
                          delta_frac: float = 0.10,
                          ref_std: np.ndarray | None = None) -> dict:
    """Her feature'i +delta*std ile kaydirinca output mutlak degisimi.

    Args:
        predict_fn: (N, F) -> (N, O) callable (ONNX sess wrapper)
        X:          baseline input (N, F)
        delta_frac: perturbation buyuklugu (input std'sinin %'i olarak)
        ref_std:    (F,) referans std (egitim dagilimi). PEMF sertlestirmesi (2026-08-26):
                    verilirse X.std yerine BU kullanilir — canli seansta N=1 icin sart;
                    N==1 ve ref_std yoksa std=0 oldugundan sonuc sessizce ~0 cikardi
                    (dejenerasyon) -> artik ACIK ValueError.

    Returns:
        {"delta_abs_mean": (F,) — ortalama |Δoutput| feature basi,
         "per_output":     (F, O) — feature x output detay,
         "feature_names":  list}
    """
    N, F = X.shape
    if ref_std is None and N < 2:
        raise ValueError(
            "EM sensitivity N=1'de X.std=0 ile DEJENERE olur (tum degerler ~0). "
            "Canli/tek-ornek aciklama icin egitim-dagilimi ref_std verin "
            "(bkz. xai-entegrasyon-plani.md Faz 1.2).")
    y0 = predict_fn(X)                                     # (N, O)
    O = y0.shape[1] if y0.ndim > 1 else 1
    y0 = y0.reshape(N, O)

    if ref_std is not None:
        std = np.asarray(ref_std, dtype=np.float64).reshape(F) + 1e-9
    else:
        std = X.std(axis=0) + 1e-9
    delta_abs_mean = np.zeros(F, dtype=np.float32)
    per_output = np.zeros((F, O), dtype=np.float32)

    for f in range(F):
        Xp = X.copy()
        Xp[:, f] = X[:, f] + delta_frac * std[f]
        y1 = predict_fn(Xp).reshape(N, O)
        diff = np.abs(y1 - y0)                              # (N, O)
        delta_abs_mean[f] = diff.mean()
        per_output[f] = diff.mean(axis=0)

    return {"delta_abs_mean": delta_abs_mean,
             "per_output":     per_output,
             "feature_names":  list(feature_names)}


def sensitivity_bar_plot(sens: dict, out_png: str | Path,
                          title: str = "Feature sensitivity (EM)"):
    """Sensitivity mean bar plot."""
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    vals = sens["delta_abs_mean"]
    names = sens["feature_names"]
    order = np.argsort(-vals)
    fig, ax = plt.subplots(figsize=(8, max(3, 0.35 * len(names))))
    ax.barh(range(len(order)), vals[order][::-1], color="#1f77b4")
    ax.set_yticks(range(len(order)))
    ax.set_yticklabels([names[i] for i in order][::-1])
    ax.set_xlabel("mean |Δoutput|  (per +10% std perturbation)")
    ax.set_title(title)
    fig.tight_layout()
    out_png = Path(out_png); out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=140); plt.close(fig)
    return out_png


def sensitivity_heatmap(sens: dict, out_png: str | Path,
                         output_labels: Sequence[str] | None = None,
                         title: str = "Feature × Output sensitivity"):
    """Feature × Output heatmap (mean |Δ| per cell)."""
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    M = sens["per_output"]                                 # (F, O)
    names = sens["feature_names"]
    F, O = M.shape
    if output_labels is None:
        output_labels = [f"o{i}" for i in range(O)]

    fig, ax = plt.subplots(figsize=(max(6, 0.3 * O + 2), max(3, 0.35 * F)))
    im = ax.imshow(M, aspect="auto", cmap="viridis")
    ax.set_yticks(range(F)); ax.set_yticklabels(names)
    ax.set_xticks(range(O)); ax.set_xticklabels(output_labels, rotation=90, fontsize=8)
    ax.set_title(title)
    plt.colorbar(im, ax=ax, label="mean |Δ|")
    fig.tight_layout()
    out_png = Path(out_png); out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=140); plt.close(fig)
    return out_png


def shap_kernel_em(predict_fn: Callable[[np.ndarray], np.ndarray],
                    X: np.ndarray,
                    feature_names: Sequence[str] = EM_FEATURES,
                    n_background: int = 40,
                    n_kernel_samples: int = 80,
                    output_agg: str = "mean",
                    background: np.ndarray | None = None,
                    n_duty: int = 7) -> np.ndarray:
    """SHAP KernelExplainer output aggregate (regressor icin).

    Args:
        output_agg: 'mean' -> tum output'lari ortala tek skalar; 'first' -> ilk output;
                    'duty' -> yalniz ILK n_duty kolonun (D1..D7 bobin duty kanallari)
                    ortalamasi (§KALAN A7): faz sin/cos + E kanallari klinik olarak
                    duty'yi surukleyen soruyu sulandiriyordu — "dozu ne belirledi"
                    aciklamasi D-kanallarina odaklanmali (em_runtime.hizli_sensitivity
                    ile ayni hedef).
        n_duty:     'duty' agregasyonunda kullanilacak kolon sayisi (EM cikti
                    yerlesimi D(7)+sinP(7)+cosP(7)+E(2) -> varsayilan 7).
        background: (M, F) referans arka plan (egitim dagilimi). PEMF sertlestirmesi
                    (2026-08-26): verilirse X-dilimi yerine BU kullanilir — N=1'de
                    background=X olunca f(x)-E[f(bg)]=0 ve tum SHAP ~0 cikardi
                    (dejenerasyon) -> tek-ornekte background yoksa ACIK ValueError.
    Returns:
        shap_values (N, F)

    Determinizm: koalisyon orneklemesi np.random kullanir; cagri suresince seed(0)
    uygulanir ve GLOBAL RNG DURUMU GERI YUKLENIR (ayni girdi -> ayni aciklama;
    klinik tekrarlanabilirlik).
    """
    import shap

    if background is None and len(X) < 2:
        raise ValueError(
            "EM kernel-SHAP N=1'de background=X olur ve tum katkilar ~0 cikar "
            "(dejenerasyon). Tek-ornek aciklama icin egitim-dagilimi background verin.")

    if output_agg not in ("mean", "first", "duty"):
        raise ValueError(f"output_agg 'mean'|'first'|'duty' olmali: {output_agg!r}")

    def _agg_pred(x):
        y = predict_fn(x)
        if y.ndim == 1:
            return y
        if output_agg == "mean":
            return y.mean(axis=1)
        if output_agg == "duty":
            return y[:, : min(n_duty, y.shape[1])].mean(axis=1)
        return y[:, 0]

    bg = background if background is not None else X[: min(n_background, len(X))]
    _rng_durum = np.random.get_state()
    try:
        np.random.seed(0)
        expl = shap.KernelExplainer(_agg_pred, bg)
        sv = expl.shap_values(X, nsamples=n_kernel_samples, silent=True)
    finally:
        np.random.set_state(_rng_durum)
    return np.asarray(sv)


def run_em_xai(predict_fn: Callable[[np.ndarray], np.ndarray],
                X: np.ndarray,
                out_dir: str | Path,
                *, feature_names: Sequence[str] = EM_FEATURES,
                output_labels: Sequence[str] | None = None,
                sample_ids: Sequence[str] | None = None,
                run_shap: bool = True,
                sens_delta: float = 0.10,
                shap_background: int = 40,
                shap_nsamples: int = 60,
                top_n: int = 6,
                ref_stats: dict | None = None) -> dict:
    """Tum EM XAI'yi tek çağrida uret: sensitivity + SHAP + CSV + PNG'ler.

    ref_stats (PEMF, 2026-08-26): {"std": (F,), "background": (M, F)} — egitim
    dagilimi referanslari. Canli/tek-ornek (N=1) aciklamada ZORUNLU; verilmezse
    N=1'de sensitivity/SHAP dejenere oldugu icin alt fonksiyonlar ValueError verir.
    """
    import pandas as pd

    from .feature_ranking import bar_plot

    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    N = X.shape[0]
    if sample_ids is None:
        sample_ids = [f"sample_{i}" for i in range(N)]
    ref_std = None if ref_stats is None else ref_stats.get("std")
    ref_bg = None if ref_stats is None else ref_stats.get("background")

    # 1) Sensitivity
    sens = sensitivity_analysis(predict_fn, X, feature_names, delta_frac=sens_delta,
                                 ref_std=ref_std)
    sensitivity_bar_plot(sens, out_dir / "sens_bar.png",
                          title=f"Sensitivity (delta={sens_delta*100:.0f}% std)")
    sensitivity_heatmap(sens, out_dir / "sens_heatmap.png",
                         output_labels=output_labels)
    pd.DataFrame({"feature": feature_names,
                   "mean_abs_delta": sens["delta_abs_mean"]}
                  ).to_csv(out_dir / "sensitivity.csv", index=False)

    # 2) SHAP (opsiyonel)
    shap_vals = None
    if run_shap:
        shap_vals = shap_kernel_em(predict_fn, X, feature_names,
                                     n_background=shap_background,
                                     n_kernel_samples=shap_nsamples,
                                     background=ref_bg)
        pd.DataFrame(shap_vals, columns=list(feature_names),
                      index=sample_ids).to_csv(out_dir / "shap_values.csv")
        # Ortalama |SHAP| bar plot
        mean_abs_shap = np.abs(shap_vals).mean(axis=0)
        bar_plot(mean_abs_shap, feature_names,
                  out_dir / "shap_mean_abs.png",
                  top_n=min(top_n, len(feature_names)),
                  title="Mean |SHAP| — output mean-aggregate", signed=False)
        # Per-sample bar
        for i, pid in enumerate(sample_ids):
            bar_plot(shap_vals[i], feature_names,
                      out_dir / f"bar_shap_{pid}.png",
                      top_n=min(top_n, len(feature_names)),
                      title=f"SHAP — {pid} (output mean)", signed=True)

    return {"sensitivity": sens, "shap_values": shap_vals,
             "out_dir": str(out_dir)}
