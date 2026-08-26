"""disagreement.py — ensemble uyesi CAM'ler arasi anlasmazlik haritasi.

Ensemble modelinin (ornegin KMCClassicTrio: VGG19+WRN50+DenseNet201) her uyesinin
CAM haritasi arasindaki farki gorsel olarak cikartir. Yuksek disagreement bolgeleri
= modelin "emin olmadigi" yerler.
"""
from __future__ import annotations
import numpy as np


def ensemble_disagreement_map(cams: list[np.ndarray],
                                mode: str = "std") -> np.ndarray:
    """N adet ayni boyutta (H, W) CAM'den disagreement haritasi.

    Args:
        cams: liste, her biri (H, W) float 0-1
        mode: 'std'  -> pixel bazinda standart sapma  (default)
              'var'  -> varyans
              'ptp'  -> max - min (peak-to-peak)

    Returns:
        (H, W) float 0-1 disagreement haritasi (min-max normalize)
    """
    if not cams:
        raise ValueError("Bos CAM listesi")
    shapes = {c.shape for c in cams}
    if len(shapes) != 1:
        raise ValueError(f"CAM boyutlari farkli: {shapes}")

    stack = np.stack(cams, axis=0).astype(np.float32)   # (N, H, W)
    if mode == "std":
        d = stack.std(axis=0)
    elif mode == "var":
        d = stack.var(axis=0)
    elif mode == "ptp":
        d = stack.max(axis=0) - stack.min(axis=0)
    else:
        raise ValueError(f"mode: {mode}")

    lo, hi = float(d.min()), float(d.max())
    if hi - lo < 1e-9:
        return np.zeros_like(d)
    return (d - lo) / (hi - lo)


def mean_cam(cams: list[np.ndarray]) -> np.ndarray:
    """N adet CAM'in aritmetik ortalamasi (ensemble consensus)."""
    return np.stack(cams, axis=0).mean(axis=0)
