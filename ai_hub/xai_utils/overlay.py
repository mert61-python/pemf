"""overlay.py — heatmap + orijinal goruntu blend + dosyaya kaydet."""
from __future__ import annotations
from pathlib import Path
import numpy as np


def heatmap_to_rgb(heatmap: np.ndarray, colormap: str = "jet") -> np.ndarray:
    """(H, W) 0-1 -> (H, W, 3) uint8 RGB (matplotlib colormap)."""
    # PEMF vendoring (2026-08-26): cm.get_cmap 3.7'de deprecated, 3.11'de KALDIRILIYOR
    # (guii matplotlib 3.10.9'da deprecation olculdu) -> kayit-defteri API'si.
    import matplotlib
    hm = np.clip(heatmap, 0.0, 1.0)
    cmap = matplotlib.colormaps[colormap]
    rgba = cmap(hm)                                  # (H, W, 4) float
    return (rgba[..., :3] * 255).astype(np.uint8)


def blend_to_array(image: np.ndarray, heatmap: np.ndarray,
                    alpha: float = 0.4,
                    colormap: str = "jet") -> np.ndarray:
    """Orijinal (H,W,3) RGB uint8 uzerine heatmap alpha-blend — BELLEK-ICI (disk yok).

    PEMF Faz 2 (2026-08-26): endpoint'ler base64 doner (karar #3 anlik gosterim);
    blend_and_save bu cekirdegi kullanir (davranis birebir).
    """
    import cv2
    H, W = image.shape[:2]
    if heatmap.shape[:2] != (H, W):
        heatmap = cv2.resize(heatmap.astype(np.float32), (W, H),
                              interpolation=cv2.INTER_LINEAR)
    hm_rgb = heatmap_to_rgb(heatmap, colormap=colormap)
    return np.clip(image.astype(np.float32) * (1 - alpha)
                   + hm_rgb.astype(np.float32) * alpha, 0, 255).astype(np.uint8)


def blend_and_save(image: np.ndarray, heatmap: np.ndarray,
                    out_path: str | Path,
                    alpha: float = 0.4,
                    colormap: str = "jet") -> Path:
    """Orijinal goruntu (RGB uint8) uzerine heatmap'i alpha-blend edip PNG olarak kaydet.

    Args:
        image:      (H, W, 3) RGB uint8
        heatmap:    (h, w) veya (H, W) float 0-1  (h != H ise resize edilir)
        out_path:   yazilacak dosya yolu
        alpha:      heatmap opaklik (default 0.4 -> %40 heatmap + %60 goruntu)
        colormap:   matplotlib colormap adi (default 'jet')

    Returns: kaydedilen dosyanin Path'i.
    """
    import cv2
    blended = blend_to_array(image, heatmap, alpha=alpha, colormap=colormap)

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # BGR olarak kaydet (cv2 konvansiyonu)
    cv2.imwrite(str(out_path), cv2.cvtColor(blended, cv2.COLOR_RGB2BGR))
    return out_path


def side_by_side(image: np.ndarray, heatmap: np.ndarray,
                  out_path: str | Path,
                  colormap: str = "jet") -> Path:
    """Orijinal | heatmap | overlay uc panelli PNG."""
    import cv2
    H, W = image.shape[:2]
    if heatmap.shape[:2] != (H, W):
        heatmap = cv2.resize(heatmap.astype(np.float32), (W, H),
                              interpolation=cv2.INTER_LINEAR)
    hm_rgb = heatmap_to_rgb(heatmap, colormap=colormap)
    overlay = np.clip(image.astype(np.float32) * 0.55
                      + hm_rgb.astype(np.float32) * 0.45, 0, 255).astype(np.uint8)
    sep = np.full((H, 8, 3), 255, dtype=np.uint8)
    canvas = np.concatenate([image, sep, hm_rgb, sep, overlay], axis=1)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out_path), cv2.cvtColor(canvas, cv2.COLOR_RGB2BGR))
    return out_path
