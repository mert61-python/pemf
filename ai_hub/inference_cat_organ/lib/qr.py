# Author: mertaygn, cglrgrkn
"""qr.py - ArUco detection + QR-canonical morphology."""
from __future__ import annotations
import numpy as np

from .canonical import CANONICAL_CAT_3D, CANONICAL_ORGANS_3D, KEYPOINT_NAMES


ARUCO_DICT = "DICT_5X5_50"                                       # OpenCV preset


ARUCO_REAL_CM = 10.0                                              # marker bir kenar uzunlugu (cm)


def detect_aruco_marker(image_path: str) -> dict:
    """Foto'da ArUco marker bul -> pixel/cm orani + marker corners.

    Returns: {"cm_per_px": float, "corners_px": (4,2), "center_px": (2,),
                  "error": str or None}
    """
    import cv2
    img = cv2.imread(image_path)
    if img is None:
        return {"error": "image_read_fail"}
    try:
        aruco_dict = cv2.aruco.getPredefinedDictionary(
            getattr(cv2.aruco, ARUCO_DICT))
    except AttributeError:
        return {"error": f"aruco_dict_invalid: {ARUCO_DICT}"}
    detector = cv2.aruco.ArucoDetector(aruco_dict)
    corners_all, ids, _ = detector.detectMarkers(img)
    if ids is None or len(ids) == 0:
        return {"error": "no_aruco_detected"}
    # Birden cok marker varsa ilki (id en kucuk)
    idx = int(np.argmin(ids.flatten()))
    c = corners_all[idx][0]                                        # (4, 2)
    # Marker kenar uzunlugu pixelde (ortalama 4 kenar)
    edges = [np.linalg.norm(c[i] - c[(i+1) % 4]) for i in range(4)]
    edge_px_mean = float(np.mean(edges))
    cm_per_px = ARUCO_REAL_CM / max(edge_px_mean, 1e-6)
    center_px = c.mean(axis=0)
    return {
        "cm_per_px": cm_per_px,
        "corners_px": c.tolist(),
        "center_px": center_px.tolist(),
        "edge_px": edge_px_mean,
        "marker_id": int(ids.flatten()[idx]),
        "error": None,
    }




def estimate_cat_axis_from_kp(kp_dict: dict, kp_conf: np.ndarray):
    """39 DLC kp'den kedi cranio-caudal eksenini (2D pixel) cikar.

    nose / upper_jaw / neck_base -> ON
    back_end / tail_base / tail_end -> ARKA
    Vector: arka -> on (kedi yuruyus yonu).
    """
    front_kps = ["nose", "upper_jaw", "neck_base", "throat_end"]
    back_kps = ["tail_base", "back_end", "back_middle"]
    front_pts, back_pts = [], []
    for name in front_kps:
        if name in kp_dict:
            front_pts.append(np.array(kp_dict[name]))
    for name in back_kps:
        if name in kp_dict:
            back_pts.append(np.array(kp_dict[name]))
    if len(front_pts) == 0 or len(back_pts) == 0:
        return None
    front_centroid = np.mean(front_pts, axis=0)
    back_centroid = np.mean(back_pts, axis=0)
    axis = front_centroid - back_centroid                          # (2,)
    norm = np.linalg.norm(axis)
    if norm < 1e-3:
        return None
    return {
        "axis_unit": (axis / norm).tolist(),
        "front_centroid_px": front_centroid.tolist(),
        "back_centroid_px": back_centroid.tolist(),
        "length_px": float(norm),
        "cat_centroid_px": ((front_centroid + back_centroid) / 2).tolist(),
    }




def estimate_organs_qr(image_path: str, kp_dict: dict, kp_conf: np.ndarray,
                              bbox: np.ndarray) -> dict:
    """QR + canonical atlas ile organ pozisyonu tahmin et.

    Returns: {
        "organs": {oid: {"name", "coord_cm_cabin", "coord_px"}},
        "morphology": {sx=sy=sz=1, bcs=0, method=[QR-canonical]},
        "qr": {cm_per_px, center_px, ...},
        "cat": {axis_unit, centroid_px, length_px}
    }
    """
    qr = detect_aruco_marker(image_path)
    if qr.get("error"):
        return {"success": False, "error": qr["error"], "qr": qr}
    cm_per_px = qr["cm_per_px"]

    cat = estimate_cat_axis_from_kp(kp_dict, kp_conf)
    if cat is None:
        return {"success": False, "error": "cat_axis_fail", "qr": qr}

    # Kedi 2D pixel ekseninden 2D rotation acisini bul
    ax, ay = cat["axis_unit"]
    theta = float(np.arctan2(ay, ax))                              # radians
    cos_t, sin_t = float(np.cos(theta)), float(np.sin(theta))

    # 10 canonical organ -> 2D pixel + cabin cm
    organs_out = {}
    cat_cx, cat_cy = cat["cat_centroid_px"]
    # Canonical kedi boy: 47 cm (nose -> tail_end). Image'da kedi boyunu olc
    cat_len_cm_img = cat["length_px"] * cm_per_px                  # gercek kedi cm boyu (axis uzunlugu)
    canon_len_cm = 19.0 - (-28.0)                                   # 47 cm (canonical nose to tail_end)
    scale = cat_len_cm_img / canon_len_cm                          # canonical -> image scale

    for oid, val in CANONICAL_ORGANS_3D.items():
        name, x_canon, y_canon, z_canon = val
        # Canonical organ pozisyonu (cat-local cm): x = cranio-caudal,
        # y = dorso-ventral (z-orto: image y'de gozukur), z = lateral (perspektif drop)
        # 2D image: x = kedi ekseni boyu, y = dik dorsal-ventral
        x_img_local = x_canon * scale                              # px (kedi ekseni)
        y_img_local = -y_canon * scale                             # px (dik, dorsal+yukari)
        # Kedi ekseni 2D rotasyonuyla cevir
        x_img_rot = cos_t * x_img_local - sin_t * y_img_local
        y_img_rot = sin_t * x_img_local + cos_t * y_img_local
        # Cabin coords: cat centroid'den ofset
        px_x = cat_cx + x_img_rot
        px_y = cat_cy + y_img_rot
        # Cabin cm (origin = ArUco merkezi, x = saga +, y = asagi +)
        qr_cx, qr_cy = qr["center_px"]
        cabin_x_cm = (px_x - qr_cx) * cm_per_px
        cabin_y_cm = (px_y - qr_cy) * cm_per_px
        organs_out[oid] = {
            "name": name,
            "coord_cm_cabin": [round(cabin_x_cm, 2), round(cabin_y_cm, 2),
                                       round(z_canon * scale * cm_per_px, 2)],
            "coord_px": [int(round(px_x)), int(round(px_y))],
            "coord_canon_cm": [round(x_canon, 2), round(y_canon, 2),
                                       round(z_canon, 2)],
        }

    morph = {
        "sx": 1.0, "sy": 1.0, "sz": 1.0, "bcs": 0.0,
        "method": ["QR-canonical"],
        "raw": {"cat_length_cm": round(cat_len_cm_img, 2),
                  "scale_cat_to_canon": round(scale, 3),
                  "cm_per_px": round(cm_per_px, 4)},
        "summary": (f"sx=1.00 sy=1.00 sz=1.00 BCS=+0.00  "
                       f"(QR-canonical, cat_len={cat_len_cm_img:.1f}cm)"),
    }
    return {
        "success": True,
        "organs": organs_out,
        "morphology": morph,
        "qr": qr,
        "cat": cat,
        "cat_axis_theta_deg": float(np.degrees(theta)),
    }




def beta_to_morphology(beta_named: dict) -> dict:
    """Backward-compat shim — QR-canonical kullaniyoruz, hep default."""
    return {
        "sx": 1.0, "sy": 1.0, "sz": 1.0, "bcs": 0.0,
        "method": ["QR-canonical"],
        "raw": {},
        "summary": "sx=1.00 sy=1.00 sz=1.00 BCS=+0.00 (QR-canonical)",
    }

# ============================================================================
# Anatomic consistency check (validation gate) + cross-photo consistency
# ============================================================================
# Her organ icin "anatomik kabul edilebilir bolge" — kanonik (cm) koordinatlar
