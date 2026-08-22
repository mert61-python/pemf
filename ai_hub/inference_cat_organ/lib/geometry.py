# Author: mertaygn, cglrgrkn
"""geometry.py - Procrustes math + apply_beta + apply_morphology."""
from __future__ import annotations
import numpy as np

from .canonical import CANONICAL_CAT_3D, CANONICAL_ORGANS_3D, KEYPOINT_NAMES




def _procrustes_step(K3d: np.ndarray, K2d: np.ndarray,
                        weights: np.ndarray) -> dict:
    """Tek-pass weighted Procrustes (Horn 1987). IRLS loop bunu cagirir."""
    w = np.asarray(weights, dtype=np.float64)
    valid = w > 0.01
    if valid.sum() < 4:
        return {"error": f"yetersiz keypoint (valid={int(valid.sum())})"}
    K3 = np.asarray(K3d, dtype=np.float64)[valid]
    K2 = np.asarray(K2d, dtype=np.float64)[valid]
    w = w[valid]
    w_sum = float(w.sum())
    if w_sum < 1e-6:
        return {"error": "weight toplami sifir"}
    w = w / w_sum

    c3 = (K3 * w[:, None]).sum(0)
    c2 = (K2 * w[:, None]).sum(0)
    X3 = K3 - c3
    X2 = K2 - c2

    X2_3 = np.column_stack([X2, np.zeros(len(X2))])
    M = (X3 * w[:, None]).T @ X2_3
    U, _, Vt = np.linalg.svd(M)
    D = np.eye(3)
    if np.linalg.det(Vt.T @ U.T) < 0:
        D[2, 2] = -1
    R = Vt.T @ D @ U.T

    K3_rot = (R @ K3.T).T
    X3_rot = K3_rot - (K3_rot * w[:, None]).sum(0)
    num = float((w[:, None] * X2 * X3_rot[:, :2]).sum())
    den = float((w * (X3_rot[:, :2] ** 2).sum(1)).sum())
    s = num / max(den, 1e-9)
    if s < 1e-3:
        s = 1e-3

    t = c2 - s * (R @ c3)[:2]
    K3_proj = s * (R @ K3.T).T[:, :2] + t
    # Ortalama (RMS gibi) hata, normalized weight'ler 1'e toplandigi icin RMS uretir
    res = float(np.sqrt((w * ((K3_proj - K2) ** 2).sum(1)).sum()))
    return {"s": float(s), "R": R, "t": t,
              "residual_px": res, "n_used": int(valid.sum())}




def weighted_procrustes_fit(K3d: np.ndarray, K2d: np.ndarray,
                                weights: np.ndarray, robust: bool = True,
                                n_iters: int = 5,
                                huber_min_delta_px: float = 8.0) -> dict:
    """Weak-perspective Procrustes fit (Horn 1987) + IRLS Huber refinement.

    Initial: weighted single-pass Procrustes.
    Refinement: iteratively reweighted least squares (Huber kernel).
      - Her iterasyonda her keypoint icin reproj error hesaplanir.
      - Huber weight: 1 (error<delta), delta/error (error>=delta)
      - delta = 2 * MAD (robust outlier threshold), min huber_min_delta_px
      - Yeni weight = original_conf * huber_weight

    Args:
        K3d: (N, 3) canonical 3D (cm)
        K2d: (N, 2) detected 2D (px)
        weights: (N,) DLC confidence
        robust: True -> IRLS Huber, False -> tek-pass
        n_iters: IRLS iterasyon sayisi
        huber_min_delta_px: minimum outlier threshold (px)
    """
    fit = _procrustes_step(K3d, K2d, weights)
    if "error" in fit or not robust:
        if "error" not in fit:
            fit["robust_iterations"] = 0
            fit["huber_delta_px"] = None
        return fit

    cur_w = np.asarray(weights, dtype=np.float64).copy()
    K3_arr = np.asarray(K3d, dtype=np.float64)
    K2_arr = np.asarray(K2d, dtype=np.float64)
    iters_done = 0
    delta = huber_min_delta_px

    for it in range(n_iters):
        s, R, t = fit["s"], fit["R"], fit["t"]
        K3_proj = s * (R @ K3_arr.T).T[:, :2] + t
        residuals = np.linalg.norm(K3_proj - K2_arr, axis=1)   # (N,)

        # Adaptive Huber delta: 2 * MAD on valid keypoints
        valid_mask = cur_w > 0.01
        if valid_mask.sum() > 0:
            r_valid = residuals[valid_mask]
            med = float(np.median(r_valid))
            mad = float(np.median(np.abs(r_valid - med)))
            delta = max(huber_min_delta_px, 1.4826 * mad * 2.0)

        huber_w = np.where(residuals < delta, 1.0,
                              delta / np.maximum(residuals, 1e-6))
        new_w = cur_w * huber_w
        new_fit = _procrustes_step(K3_arr, K2_arr, new_w)
        if "error" in new_fit:
            break
        iters_done = it + 1
        delta_res = abs(new_fit["residual_px"] - fit["residual_px"])
        fit = new_fit
        cur_w = new_w
        if delta_res < 0.05:                                    # convergence
            break

    fit["robust_iterations"] = iters_done
    fit["huber_delta_px"] = round(delta, 2)
    # Inlier sayisi (huber_w yakin 1)
    s, R, t = fit["s"], fit["R"], fit["t"]
    K3_proj = s * (R @ K3_arr.T).T[:, :2] + t
    residuals = np.linalg.norm(K3_proj - K2_arr, axis=1)
    inlier_mask = (cur_w > 0.01) & (residuals < delta)
    fit["n_inliers"] = int(inlier_mask.sum())
    return fit




def project_3d_to_2d(p3d: np.ndarray, s: float, R: np.ndarray,
                       t: np.ndarray) -> np.ndarray:
    """3D nokta (cm) -> 2D pixel projeksiyonu (weak-perspective)."""
    p3d = np.atleast_2d(np.asarray(p3d, dtype=np.float64))
    rotated = (R @ p3d.T).T                                  # (N, 3)
    return s * rotated[:, :2] + t




def project_3d_with_depth(p3d: np.ndarray, s: float, R: np.ndarray,
                             t: np.ndarray) -> tuple:
    """3D -> 2D + depth (z after rotation). depth: artan = uzak."""
    p3d = np.atleast_2d(np.asarray(p3d, dtype=np.float64))
    rotated = (R @ p3d.T).T
    xy = s * rotated[:, :2] + t
    z = rotated[:, 2]
    return xy, z




def rotation_to_euler_deg(R: np.ndarray) -> tuple:
    """R -> (yaw, pitch, roll) derece. Z-Y-X euler convention."""
    sy = float(np.sqrt(R[0, 0] ** 2 + R[1, 0] ** 2))
    singular = sy < 1e-6
    if not singular:
        roll = float(np.degrees(np.arctan2(R[2, 1], R[2, 2])))
        pitch = float(np.degrees(np.arctan2(-R[2, 0], sy)))
        yaw = float(np.degrees(np.arctan2(R[1, 0], R[0, 0])))
    else:
        roll = float(np.degrees(np.arctan2(-R[1, 2], R[1, 1])))
        pitch = float(np.degrees(np.arctan2(-R[2, 0], sy)))
        yaw = 0.0
    return yaw, pitch, roll


# ============================================================================
# Pose Classifier
# ============================================================================


def apply_beta_to_canonical(beta: np.ndarray) -> dict:
    """Beta -> deforme atlas (kp_name -> (x, y, z) cm)."""
    sx, sy, sz, bcs = beta
    bcs_shift = bcs * -1.5                                       # ventral kayma cm
    out = {}
    for name, (x, y, z) in CANONICAL_CAT_3D.items():
        x_s = x * sx
        y_s = y * sy
        z_s = z * sz
        if y < -0.5:                                              # ventral
            y_s += bcs_shift
        elif y > 1.0:                                             # dorsal
            y_s += -bcs_shift * 0.3
        out[name] = (x_s, y_s, z_s)
    return out




def apply_beta_to_3d_array(beta: np.ndarray) -> np.ndarray:
    """Beta -> deforme (N_KP, 3) numpy array (KEYPOINT_NAMES sirasinda)."""
    deformed = apply_beta_to_canonical(beta)
    return np.array([deformed[n] for n in KEYPOINT_NAMES], dtype=np.float32)


# ============================================================================
# QR (ArUco) + canonical atlas: ML-free organ position estimation
# ============================================================================
# Klinik kabin kullanim: kabinin arka duvarinda 1 ArUco marker (bilinen boyut)
# Foto: kedi + marker -> pixel/cm calibration + cabin coordinate system
# Cat: canonical atlas (sx=sy=sz=1, BCS=0) ile default organ pozisyonlari
# Output: organ pozisyonlari kabin koordinatlarinda (cm)

# ArUco marker konfigurasyonu (sen kalibre edersin)


_CANON_SPINE_CM = 29.0        # nose -> tail_base mesafesi (kanonik)
_CANON_DV_CM = 11.0           # back_middle -> belly_bottom (dorso-ventral)
_CANON_LAT_CM = 10.0          # body_middle_R -> body_middle_L (lateral)
_CANON_PLUMPNESS = 0.55       # ortalama mask_area / bbox_area
_BCS_VENTRAL_SHIFT_CM = 1.5   # bcs=+1 (sisman) ventral organ kaymasi (cm)


def apply_morphology_to_atlas(atlas_dict: dict, morph: dict) -> dict:
    """Canonical 3D dict'i (oid -> (name, x, y, z)) per-cat scale uygula."""
    out = {}
    bcs_shift = morph["bcs"] * (-_BCS_VENTRAL_SHIFT_CM)        # +bcs -> ventral asagi
    for oid, val in atlas_dict.items():
        if isinstance(val, tuple) and len(val) == 4:
            name, x, y, z = val
            x_s = x * morph["sx"]
            y_s = y * morph["sy"]
            z_s = z * morph["sz"]
            if y < -0.5:                                          # ventral organlar
                y_s += bcs_shift
            elif y > 1.0:                                         # dorsal organlar
                y_s += -bcs_shift * 0.3                           # az etki
            out[oid] = (name, round(x_s, 2), round(y_s, 2), round(z_s, 2))
        else:                                                    # canonical kp atlas
            x, y, z = val
            x_s = x * morph["sx"]
            y_s = y * morph["sy"]
            z_s = z * morph["sz"]
            if y < -0.5:
                y_s += bcs_shift
            out[oid] = (round(x_s, 2), round(y_s, 2), round(z_s, 2))
    return out




def apply_morphology_to_canonical_kp(morph: dict) -> dict:
    """CANONICAL_CAT_3D dict'i (name -> (x, y, z)) per-cat scale uygula."""
    out = {}
    bcs_shift = morph["bcs"] * (-_BCS_VENTRAL_SHIFT_CM)
    for name, (x, y, z) in CANONICAL_CAT_3D.items():
        x_s = x * morph["sx"]
        y_s = y * morph["sy"]
        z_s = z * morph["sz"]
        if y < -0.5:
            y_s += bcs_shift
        out[name] = (x_s, y_s, z_s)
    return out




def apply_morphology_to_mesh(canonical_mesh: dict, morph: dict) -> dict:
    """Mesh vertex'lerini anisotropic scale + BCS."""
    V = canonical_mesh["vertices"].copy()
    V[:, 0] *= morph["sx"]
    V[:, 1] *= morph["sy"]
    V[:, 2] *= morph["sz"]
    bcs_shift = morph["bcs"] * (-_BCS_VENTRAL_SHIFT_CM)
    # Sadece ventral kism (y<0) BCS'den etkilensin
    V[V[:, 1] < 0, 1] += bcs_shift
    return {"vertices": V, "faces": canonical_mesh["faces"],
              "groups": canonical_mesh.get("groups", {})}


# ============================================================================
# Method C: 3D PnP fit (weighted Procrustes)
# ============================================================================
