"""gene_ranking.py — RNA-seq attribution icin gen ismi haritalama + top-N gene CSV.

human_kidney_rna gibi omics modullerinde attribution feature-index'ler uzerinde
uretilir. Bu modul index'leri gen sembollerine cevirir ve top-K uretir.
"""
from __future__ import annotations
from pathlib import Path
from typing import Sequence
import numpy as np


def gene_symbols_from_indices(feature_indices: np.ndarray,
                                all_gene_names: Sequence[str]) -> list[str]:
    """SelectKBest indices -> gen sembol listesi."""
    return [all_gene_names[int(i)] for i in feature_indices]


def top_genes_csv(attributions: np.ndarray,
                   gene_names: Sequence[str],
                   out_csv: str | Path,
                   *, top_n: int = 30,
                   sample_ids: Sequence[str] | None = None,
                   direction: str = "signed") -> Path:
    """(N, K_selected) attribution -> top-N gen sıralaması CSV.

    Args:
        direction:
            'signed'  -> pozitif (KIRC'e katki) ve negatif (rest'e katki) ayrik top-N
            'abs'     -> mutlak deger sirasi
    """
    import pandas as pd
    if attributions.ndim == 3:
        attributions = attributions.mean(axis=-1)     # (N, F) — mean over classes
    N, F = attributions.shape
    ids = sample_ids if sample_ids is not None else [str(i) for i in range(N)]
    top_n = min(int(top_n), F)

    rows = []
    for i in range(N):
        if direction == "signed":
            pos = np.argsort(-attributions[i])[:top_n]
            neg = np.argsort(attributions[i])[:top_n]
            for r, j in enumerate(pos, 1):
                rows.append({"sample_id": ids[i], "direction": "pos",
                              "rank": r, "gene": gene_names[j],
                              "attribution": float(attributions[i, j])})
            for r, j in enumerate(neg, 1):
                rows.append({"sample_id": ids[i], "direction": "neg",
                              "rank": r, "gene": gene_names[j],
                              "attribution": float(attributions[i, j])})
        else:  # abs
            order = np.argsort(-np.abs(attributions[i]))[:top_n]
            for r, j in enumerate(order, 1):
                rows.append({"sample_id": ids[i], "direction": "abs",
                              "rank": r, "gene": gene_names[j],
                              "attribution": float(attributions[i, j]),
                              "abs_attribution": float(abs(attributions[i, j]))})

    out_csv = Path(out_csv); out_csv.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(out_csv, index=False)
    return out_csv
