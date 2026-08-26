"""feature_ranking.py — attribution -> top-N ranking CSV + bar plot."""
from __future__ import annotations
from pathlib import Path
from typing import Sequence
import numpy as np


def top_features_csv(attributions: np.ndarray,
                      feature_names: Sequence[str],
                      out_csv: str | Path,
                      *, top_n: int = 20,
                      sample_ids: Sequence[str] | None = None,
                      abs_rank: bool = True) -> Path:
    """Attribution matrisinden top-N feature CSV.

    Args:
        attributions: (N, F) numpy — SHAP/IG signed values
        feature_names: (F,) sutun isimleri
        out_csv: cikti .csv yolu
        top_n: kaç en yuksek feature listelensin
        sample_ids: (N,) opsiyonel — yoksa 0..N-1
        abs_rank: True -> |attribution| ile sirala (yon ne olursa olsun etki gucu)
                  False -> ham signed value ile sirala

    CSV formati:
        sample_id, rank, feature, attribution
    """
    import pandas as pd
    if attributions.ndim == 3:
        # (N, F, C) -> hedef sinifin katmani (argmax value) ver
        # buraya duserse cagirmadan once sikistir; simdilik mean over classes
        attributions = attributions.mean(axis=-1)

    N, F = attributions.shape
    ids = sample_ids if sample_ids is not None else [str(i) for i in range(N)]
    top_n = min(int(top_n), F)

    rows = []
    key = np.abs(attributions) if abs_rank else attributions
    for i in range(N):
        order = np.argsort(-key[i])[:top_n]
        for rank, j in enumerate(order, 1):
            rows.append({
                "sample_id": ids[i],
                "rank":      rank,
                "feature":   feature_names[j],
                "attribution": float(attributions[i, j]),
                "abs_attribution": float(abs(attributions[i, j])),
            })

    out_csv = Path(out_csv); out_csv.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(out_csv, index=False)
    return out_csv


def bar_plot(attributions_1d: np.ndarray,
              feature_names: Sequence[str],
              out_png: str | Path,
              *, top_n: int = 20,
              title: str = "Feature attribution",
              signed: bool = True) -> Path:
    """Tek sample'in top-N feature'i icin renkli bar plot (matplotlib)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    if attributions_1d.ndim > 1:
        raise ValueError("bar_plot: (F,) tek sample bekler")
    top_n = min(int(top_n), len(attributions_1d))
    order = np.argsort(-np.abs(attributions_1d))[:top_n][::-1]
    vals = attributions_1d[order]
    names = [feature_names[i] for i in order]

    colors = ["#d62728" if v < 0 else "#2ca02c" for v in vals] if signed \
             else ["#1f77b4"] * top_n

    fig, ax = plt.subplots(figsize=(8, max(4, 0.3 * top_n)))
    ax.barh(range(top_n), vals, color=colors)
    ax.set_yticks(range(top_n)); ax.set_yticklabels(names, fontsize=9)
    ax.axvline(0, color="black", lw=0.8)
    ax.set_xlabel("attribution")
    ax.set_title(title)
    fig.tight_layout()
    out_png = Path(out_png); out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=140)
    plt.close(fig)
    return out_png
