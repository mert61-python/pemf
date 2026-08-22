# Author: mertaygn, cglrgrkn
"""mask_features.py - Segmentasyon maskesinden ek anatomik bilgi.

Mevcut YOLOv8m-seg cikti'sini Procrustes oncesi ve sonrasi degerlendirmek icin
kullanir. Yeni model GEREKMEZ — sadece mask poligonu yeniden yorumlanir.

Fonksiyonlar
------------
- mask_pca_axis: PCA ile govde ana ekseni, uzunluk, genislik, merkez
- mask_polygon: poligonu (N,2) numpy array'e cevirir, gerekirse cv2.contour
- point_in_mask: tek noktanin mask icinde olup olmadigi
- validate_kp_in_mask: kp_conf'u mask uyumuna gore yeniden agirlandirir
- clip_organs_to_mask: projekte edilmis organlari mask'a clamp eder + flag
"""
from __future__ import annotations
import numpy as np


def mask_polygon(mask_xy) -> np.ndarray:
    """seg['mask_xy'] -> (N, 2) numpy. Hata durumunda bos array."""
    if mask_xy is None:
        return np.zeros((0, 2), dtype=np.float64)
    arr = np.asarray(mask_xy, dtype=np.float64)
    if arr.ndim == 3:                                        # (1, N, 2) durumu
        arr = arr.reshape(-1, 2)
    if arr.ndim != 2 or arr.shape[1] != 2 or len(arr) < 3:
        return np.zeros((0, 2), dtype=np.float64)
    return arr


def mask_pca_axis(mask_xy) -> dict:
    """Mask noktalarinda PCA -> govde ekseni.

    Returns dict:
      center_px: (2,) mask centroidi
      axis_angle_rad: ana eksenin yatay ile yaptigi aci (image koord)
      body_length_px: ana eksen extent (1. PC uzerinde projekte uzunluk)
      body_width_px:  yan eksen extent
      eigvals: (e1, e2) saralanmis (azalan)
      ok: yeterli nokta var mi
    """
    pts = mask_polygon(mask_xy)
    if len(pts) < 5:
        return {"ok": False, "reason": "az_nokta"}
    c = pts.mean(axis=0)
    cov = ((pts - c).T @ (pts - c)) / max(1, len(pts) - 1)
    eigvals, eigvecs = np.linalg.eigh(cov)
    # azalan sirala
    order = np.argsort(eigvals)[::-1]
    eigvals = eigvals[order]
    eigvecs = eigvecs[:, order]
    pc1 = eigvecs[:, 0]                                       # ana eksen yonu
    pc2 = eigvecs[:, 1]
    # Extent: 5-95 percentile of projection (outlier dayanikli)
    proj1 = (pts - c) @ pc1
    proj2 = (pts - c) @ pc2
    p1_lo, p1_hi = np.percentile(proj1, [5, 95])
    p2_lo, p2_hi = np.percentile(proj2, [5, 95])
    body_length = float(p1_hi - p1_lo)
    body_width = float(p2_hi - p2_lo)
    angle = float(np.arctan2(pc1[1], pc1[0]))                 # image yatay = 0
    return {
        "ok": True,
        "center_px": [float(c[0]), float(c[1])],
        "axis_angle_rad": angle,
        "axis_angle_deg": round(float(np.degrees(angle)), 1),
        "body_length_px": round(body_length, 1),
        "body_width_px": round(body_width, 1),
        "aspect_ratio": round(body_length / max(body_width, 1e-6), 2),
        "eigvals": [float(eigvals[0]), float(eigvals[1])],
        "pc1": [float(pc1[0]), float(pc1[1])],
        "pc2": [float(pc2[0]), float(pc2[1])],
    }


def point_in_mask(px: float, py: float, poly: np.ndarray) -> bool:
    """Ray-casting point-in-polygon. poly: (N, 2)."""
    if len(poly) < 3:
        return True                                           # bilinmiyor -> kabul
    n = len(poly)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if ((yi > py) != (yj > py)) and \
           (px < (xj - xi) * (py - yi) / (yj - yi + 1e-12) + xi):
            inside = not inside
        j = i
    return inside


def validate_kp_in_mask(kp_dict: dict, kp_conf: np.ndarray,
                              kp_names: list, mask_xy,
                              outside_penalty: float = 0.5) -> dict:
    """Mask disindaki keypoint'lerin confidence'ini cezalandir.

    Tum kp'leri tek tek mask icinde mi kontrol et. Disindakilerin
    `kp_conf` degerini outside_penalty ile carp. Imputed/mirrored kp'ler
    burada cezalandirilmaz cunku kp_dict'te degil.

    Returns:
      new_conf: (N,) yeni confidence
      outside_kp: mask disinda kalan kp adlari listesi
    """
    poly = mask_polygon(mask_xy)
    if len(poly) < 3 or kp_conf is None:
        return {"new_conf": kp_conf, "outside_kp": []}
    new_conf = np.asarray(kp_conf, dtype=np.float64).copy()
    outside_kp = []
    # Mask bbox (hizli reddetme icin)
    bb_x0, bb_y0 = poly.min(0)
    bb_x1, bb_y1 = poly.max(0)
    margin = 5.0                                              # px tolerans
    for i, n in enumerate(kp_names):
        if n not in kp_dict:
            continue
        px, py = float(kp_dict[n][0]), float(kp_dict[n][1])
        # Hizli bbox reddi
        if px < bb_x0 - margin or px > bb_x1 + margin or \
           py < bb_y0 - margin or py > bb_y1 + margin:
            new_conf[i] *= outside_penalty
            outside_kp.append(n)
            continue
        if not point_in_mask(px, py, poly):
            new_conf[i] *= outside_penalty
            outside_kp.append(n)
    return {"new_conf": new_conf, "outside_kp": outside_kp}


def organ_in_mask_flags(organ_xy: np.ndarray, mask_xy) -> list[bool]:
    """Her projekte edilmis organ icin mask icinde mi flag."""
    poly = mask_polygon(mask_xy)
    if len(poly) < 3:
        return [True] * len(organ_xy)
    flags = []
    bb_x0, bb_y0 = poly.min(0)
    bb_x1, bb_y1 = poly.max(0)
    for px, py in organ_xy:
        if not (bb_x0 - 5 <= px <= bb_x1 + 5 and bb_y0 - 5 <= py <= bb_y1 + 5):
            flags.append(False)
            continue
        flags.append(point_in_mask(float(px), float(py), poly))
    return flags
