# Author: mertaygn, cglrgrkn
"""priors.py - L/R simetri imputation + bootstrap uncertainty.

L/R imputation: bir cift kp'den birini gozlemleyince digerini ayna ile
tahmin et (azaltilmis agirlikla). Spine ortalamasini cizgi alarak yansit.

Bootstrap uncertainty: Procrustes fit'ini N kez kp subset'leriyle tekrarla,
her organ icin 3D ve 2D pozisyon std hesapla.
"""
from __future__ import annotations
import numpy as np

from .canonical import KEYPOINT_NAMES
from .geometry import weighted_procrustes_fit, project_3d_with_depth


LR_PAIRS = [
    ("right_eye",          "left_eye"),
    ("right_earbase",      "left_earbase"),
    ("right_earend",       "left_earend"),
    ("mouth_end_right",    "mouth_end_left"),
    ("front_right_thai",   "front_left_thai"),
    ("front_right_knee",   "front_left_knee"),
    ("front_right_paw",    "front_left_paw"),
    ("back_right_thai",    "back_left_thai"),
    ("back_right_knee",    "back_left_knee"),
    ("back_right_paw",     "back_left_paw"),
    ("body_middle_right",  "body_middle_left"),
]

# Govde midline tahmini icin (sirayla onem)
SPINE_KP = ["nose", "neck_base", "back_base", "back_middle",
                "back_end", "tail_base"]


def _fit_midline(kp_dict: dict) -> dict | None:
    """Spine kp'lerinden cizgi fit eder (least squares). Donen:
      origin: (2,) cizgi uzerinde bir nokta (centroid)
      dir:    (2,) birim teget vektor
      normal: (2,) birime dik (yansima icin)
    """
    pts = [kp_dict[n] for n in SPINE_KP if n in kp_dict]
    if len(pts) < 2:
        return None
    P = np.asarray(pts, dtype=np.float64)
    c = P.mean(axis=0)
    X = P - c
    # PCA: ana eksen = spine yonu
    cov = X.T @ X / max(1, len(X) - 1)
    eigvals, eigvecs = np.linalg.eigh(cov)
    order = np.argsort(eigvals)[::-1]
    eigvecs = eigvecs[:, order]
    direction = eigvecs[:, 0]
    direction = direction / max(np.linalg.norm(direction), 1e-9)
    normal = np.array([-direction[1], direction[0]])
    return {"origin": c, "dir": direction, "normal": normal}


def _reflect_point(p: np.ndarray, origin: np.ndarray,
                       normal: np.ndarray) -> np.ndarray:
    """Cizgiye gore yansima: p' = p - 2 * <p-o, n> * n."""
    d = float(np.dot(p - origin, normal))
    return p - 2.0 * d * normal


def impute_lr_symmetric_kps(kp_dict: dict, kp_conf: np.ndarray,
                                  kp_names: list[str] | None = None,
                                  conf_threshold: float = 0.30,
                                  imputed_weight: float = 0.30) -> dict:
    """L/R cift kp'leri ayna ile tamamla.

    Spine kp'lerinden midline fit edilir, gozlemlenen taraf yansitilir.

    Args:
      kp_dict: {kp_name: [x, y]} gozlemlenen (conf >= threshold)
      kp_conf: (N,) tum kp'lerin conf'u (KEYPOINT_NAMES sirasinda)
      kp_names: KEYPOINT_NAMES (default)
      conf_threshold: bu altinda eksik kabul
      imputed_weight: imputed kp'nin agirligi (oran)

    Returns:
      kp_dict_aug: {name: [x,y]} yansitilanlar dahil
      kp_conf_aug: (N,) yeni conf vektoru
      imputed_kp:  imputed kp ad listesi
    """
    if kp_names is None:
        kp_names = KEYPOINT_NAMES
    kp_dict_aug = dict(kp_dict)
    conf_aug = np.asarray(kp_conf, dtype=np.float64).copy()
    imputed = []
    midline = _fit_midline(kp_dict)
    if midline is None:
        return {"kp_dict": kp_dict_aug, "kp_conf": conf_aug, "imputed_kp": []}

    origin = midline["origin"]
    normal = midline["normal"]
    for a, b in LR_PAIRS:
        # a varsa b yok / dusuk -> b'yi yansit
        i_a = kp_names.index(a) if a in kp_names else -1
        i_b = kp_names.index(b) if b in kp_names else -1
        if i_a < 0 or i_b < 0:
            continue
        ca = float(conf_aug[i_a]) if i_a >= 0 else 0.0
        cb = float(conf_aug[i_b]) if i_b >= 0 else 0.0
        if ca >= conf_threshold and cb < conf_threshold and a in kp_dict_aug:
            p_a = np.asarray(kp_dict_aug[a], dtype=np.float64)
            p_b_imp = _reflect_point(p_a, origin, normal)
            kp_dict_aug[b] = [float(p_b_imp[0]), float(p_b_imp[1])]
            conf_aug[i_b] = max(cb, ca * imputed_weight)
            imputed.append(b)
        elif cb >= conf_threshold and ca < conf_threshold and b in kp_dict_aug:
            p_b = np.asarray(kp_dict_aug[b], dtype=np.float64)
            p_a_imp = _reflect_point(p_b, origin, normal)
            kp_dict_aug[a] = [float(p_a_imp[0]), float(p_a_imp[1])]
            conf_aug[i_a] = max(ca, cb * imputed_weight)
            imputed.append(a)
    return {"kp_dict": kp_dict_aug, "kp_conf": conf_aug,
              "imputed_kp": imputed}


# ============================================================================
# Bootstrap uncertainty
# ============================================================================

def bootstrap_organ_uncertainty(K3: np.ndarray, K2: np.ndarray,
                                          weights: np.ndarray,
                                          organs_3d: np.ndarray,
                                          n_iter: int = 30,
                                          subsample_frac: float = 0.80,
                                          rng_seed: int = 42) -> dict:
    """Procrustes fit'ini kp subset'leri ile tekrarla, organ std hesapla.

    Args:
      K3: (N_KP, 3) canonical 3D atlas (per-cat scaled)
      K2: (N_KP, 2) detected 2D (px)
      weights: (N_KP,) confidence
      organs_3d: (N_ORG, 3) per-cat scaled organ atlas
      n_iter: bootstrap iterasyon sayisi
      subsample_frac: her iterasyonda valid kp'nin orani
      rng_seed: reproducibility

    Returns:
      organ_xy_std: (N_ORG, 2) px std
      organ_3d_std: (N_ORG, 3) cm std (rotated 3D space)
      scale_std:    s degerinin std'si
      n_succ:       basarili iterasyon sayisi
    """
    rng = np.random.default_rng(rng_seed)
    valid = np.where(weights > 0.01)[0]
    n_valid = len(valid)
    if n_valid < 6:
        return {"organ_xy_std": np.zeros_like(organs_3d[:, :2]),
                  "organ_3d_std": np.zeros_like(organs_3d),
                  "scale_std": 0.0,
                  "n_succ": 0,
                  "reason": "az_kp"}

    n_sub = max(6, int(round(n_valid * subsample_frac)))
    organ_xys = []
    organ_3ds = []
    scales = []
    for _ in range(n_iter):
        idx = rng.choice(valid, size=n_sub, replace=True)
        w_sub = np.zeros_like(weights)
        # Sampling frekansi -> weight (bootstrap replicate)
        for k in idx:
            w_sub[k] += float(weights[k])
        try:
            fit = weighted_procrustes_fit(K3, K2, w_sub,
                                                    robust=True, n_iters=3)
            if "error" in fit:
                continue
            s, R, t = fit["s"], fit["R"], fit["t"]
            xy, z = project_3d_with_depth(organs_3d, s, R, t)
            # 3D rotated coord: (R @ p3d.T).T  -> tam 3D (px degil cm)
            xyz_rot = (R @ organs_3d.T).T
            organ_xys.append(xy)
            organ_3ds.append(xyz_rot)
            scales.append(s)
        except Exception:
            continue
    n_succ = len(organ_xys)
    if n_succ < 3:
        return {"organ_xy_std": np.zeros_like(organs_3d[:, :2]),
                  "organ_3d_std": np.zeros_like(organs_3d),
                  "scale_std": 0.0,
                  "n_succ": n_succ,
                  "reason": "az_basarili_iter"}
    A_xy = np.stack(organ_xys, axis=0)          # (n_succ, N_ORG, 2)
    A_3d = np.stack(organ_3ds, axis=0)          # (n_succ, N_ORG, 3)
    organ_xy_std = A_xy.std(axis=0, ddof=1)
    organ_3d_std = A_3d.std(axis=0, ddof=1)
    scale_std = float(np.std(scales, ddof=1))
    return {"organ_xy_std": organ_xy_std,
              "organ_3d_std": organ_3d_std,
              "scale_std": scale_std,
              "n_succ": n_succ}
