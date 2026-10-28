"""disagreement.py — ensemble uyesi CAM'ler arasi anlasmazlik haritasi.

Ensemble modelinin (ornegin KMCClassicTrio: VGG19+WRN50+DenseNet201) her uyesinin
CAM haritasi arasindaki farki gorsel olarak cikartir. Yuksek disagreement bolgeleri
= modelin "emin olmadigi" yerler.

D6.64 (D67, 2026-10-28): harita MUTLAK olcekte doner. Eskiden piksel std'si goruntu basina
min-max ile [0, 1]'e geriliyordu → uc model neredeyse AYNI haritayi verse de (olculdu: ham std
maks ~0,003) en parlak bolge 1,0 cikiyor ve arayuz "parlak bolgelerde uc model AYRISIYOR"
diyordu. ⚠️ pytorch-grad-cam her CAM'i ZATEN kendi icinde min-max ile [0, 1]'e olcekler
(`scale_cam_image`) — CAM'lerin kendi buyuklugu kaybolur; buradaki olcu bu normalize
haritalarin SEKIL ayrismasidir. Mutlak olcek: [0, 1]'deki N degerin alabilecegi EN BUYUK
sapmaya (`sapma_tavani`) bolum → 0 = tam uyum, 1 = kuramsal en buyuk ayrisma.
"""
from __future__ import annotations
import math
import numpy as np


def sapma_tavani(n: int, mode: str = "std") -> float:
    """[0, 1] araligindaki n degerin alabilecegi EN BUYUK ayrisma (n//2 tanesi 0, kalani 1).

    std: sqrt(k*(n-k))/n (n=3 → sqrt(2)/3 ≈ 0,4714) · var: onun karesi · ptp: 1.
    """
    if n < 2:
        return 1.0
    k = n // 2
    s = math.sqrt(k * (n - k)) / n
    return {"std": s, "var": s * s, "ptp": 1.0}[mode]


def ensemble_disagreement_map(cams: list[np.ndarray],
                                mode: str = "std",
                                olcek: str = "mutlak") -> np.ndarray:
    """N adet ayni boyutta (H, W) CAM'den disagreement haritasi.

    Args:
        cams: liste, her biri (H, W) float 0-1
        mode: 'std'  -> pixel bazinda standart sapma  (default)
              'var'  -> varyans
              'ptp'  -> max - min (peak-to-peak)
        olcek: 'mutlak' (default) -> kuramsal tavana bolum (`sapma_tavani`); uyumlu
               CAM'lerde harita KARANLIK kalir, buyuklugu korunur
               'minmax' -> goruntu basina min-max (eski davranis; en parlak bolge HER
               ZAMAN 1 — buyukluk bilgisi ATILIR, urunde kullanilmaz)

    Returns:
        (H, W) float 0-1 disagreement haritasi
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

    if olcek == "mutlak":
        return np.clip(d / sapma_tavani(len(cams), mode), 0.0, 1.0).astype(np.float32)
    if olcek != "minmax":
        raise ValueError(f"olcek: {olcek}")
    lo, hi = float(d.min()), float(d.max())
    if hi - lo < 1e-9:
        return np.zeros_like(d)
    return (d - lo) / (hi - lo)


def mean_cam(cams: list[np.ndarray]) -> np.ndarray:
    """N adet CAM'in aritmetik ortalamasi (ensemble consensus)."""
    return np.stack(cams, axis=0).mean(axis=0)
