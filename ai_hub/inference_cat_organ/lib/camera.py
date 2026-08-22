# Author: mertaygn, cglrgrkn
"""camera.py - Camera intrinsics, perspective projection, solvePnP, transforms.

Level 3 (perspective) icin temel matematik:
  - Intrinsics K (3x3), distortion D (5,)
  - Marker pose -> camera transform (rvec, tvec)
  - Cat pose -> camera transform (rvec, tvec) from kp PnP
  - Compose: cat -> cabin transform
"""
from __future__ import annotations
from pathlib import Path
import numpy as np


def load_intrinsics(npz_path: str, yaml_dir: str | None = None) -> dict | None:
    """Calibrate camera ile uretilmis .npz dosyasini yukle.

    Beklenen alanlar:
      K: (3,3) cameraMatrix
      D: (5,) distortion coeffs
      image_size: (W,H) opsiyonel

    Returns: {"K": np.ndarray, "D": np.ndarray, "image_size": tuple or None}
             None if path yok / okunamiyor.
    """
    if npz_path is None:
        return None
    p = Path(npz_path)
    if not p.is_absolute() and yaml_dir is not None:
        p = Path(yaml_dir) / p
    if not p.exists():
        return None
    data = np.load(str(p), allow_pickle=False)
    K = np.asarray(data["K"], dtype=np.float64).reshape(3, 3)
    D = np.asarray(data["D"], dtype=np.float64).reshape(-1)
    img_size = None
    if "image_size" in data.files:
        img_size = tuple(int(v) for v in data["image_size"])
    return {"K": K, "D": D, "image_size": img_size}


def approximate_intrinsics(image_shape: tuple,
                                       marker_pixel_size: float,
                                       marker_real_cm: float,
                                       camera_to_marker_cm: float) -> dict:
    """Kalibrasyon yoksa: marker mesafesinden focal length tahmin et.

    f_px ~ marker_pixel_size * camera_to_marker_cm / marker_real_cm
    cx, cy = image center
    D = 0 (lens distortion ihmal)

    Bu yaklasik intrinsics — gercek calibrate edilmis K'den 5-15% sapar
    ama marker yakininda projection makul.
    """
    H, W = image_shape[:2]
    f = float(marker_pixel_size * camera_to_marker_cm / max(marker_real_cm, 1e-6))
    K = np.array([
        [f, 0.0, W / 2.0],
        [0.0, f, H / 2.0],
        [0.0, 0.0, 1.0],
    ], dtype=np.float64)
    D = np.zeros(5, dtype=np.float64)
    return {"K": K, "D": D, "image_size": (W, H),
              "source": "approximate", "f_px": f}


def solve_marker_pose(marker_corners_2d: np.ndarray,
                            marker_real_cm: float,
                            K: np.ndarray, D: np.ndarray) -> dict:
    """Marker 4 kose -> marker frame -> camera frame transform.

    ArUco detect kose sirasi: TL, TR, BR, BL (clockwise).
    Marker frame: origin = marker merkez, X sag (TR yonu), Y asagi (BR yonu),
                       Z normal (kameradan disari).
    objectPoints sirasi ArUco corner sirasi ile ayni (TL, TR, BR, BL).
    """
    import cv2
    R = float(marker_real_cm)
    half = R / 2.0
    obj = np.array([
        [-half, -half, 0.0],   # TL
        [+half, -half, 0.0],   # TR
        [+half, +half, 0.0],   # BR
        [-half, +half, 0.0],   # BL
    ], dtype=np.float64)
    img = np.asarray(marker_corners_2d, dtype=np.float64).reshape(-1, 2)
    # IPPE_SQUARE bazi corner ordering'lerde dejene cozum donduruyor;
    # ITERATIVE + initial guess (marker kameradan ~K[0,0]*R/edge_px uzakta) daha kararli.
    edge_px = float(np.linalg.norm(img[1] - img[0]))
    f_avg = float((K[0, 0] + K[1, 1]) / 2.0)
    z_init = f_avg * R / max(edge_px, 1e-6)
    # Marker merkez pixel -> initial t (kabaca)
    cx_img, cy_img = img.mean(0)
    tx_init = (cx_img - K[0, 2]) * z_init / f_avg
    ty_init = (cy_img - K[1, 2]) * z_init / f_avg
    rvec_init = np.zeros((3, 1), dtype=np.float64)
    tvec_init = np.array([[tx_init], [ty_init], [z_init]], dtype=np.float64)
    ok, rvec, tvec = cv2.solvePnP(obj, img, K, D,
                                              rvec=rvec_init, tvec=tvec_init,
                                              useExtrinsicGuess=True,
                                              flags=cv2.SOLVEPNP_ITERATIVE)
    if not ok:
        return {"error": "marker_pnp_fail"}
    return {"rvec": rvec.reshape(3),
              "tvec": tvec.reshape(3),
              "obj_points": obj}


def solve_cat_pose_pnp(K3: np.ndarray, K2: np.ndarray,
                              weights: np.ndarray,
                              K: np.ndarray, D: np.ndarray,
                              rvec_init: np.ndarray | None = None,
                              tvec_init: np.ndarray | None = None) -> dict:
    """Kp correspondences ile cat -> camera transform (rvec, tvec).

    Args:
      K3: (N, 3) canonical 3D (cm), per-cat olcekli
      K2: (N, 2) detected 2D (px)
      weights: (N,) confidence — < threshold olanlar atilir
      K: (3,3) intrinsics
      D: (5,) distortion
      rvec_init/tvec_init: opsiyonel baslangic tahmini (extrinsic guess)

    Returns: {"rvec","tvec","inliers","n_used","residual_px"}
    """
    import cv2
    w = np.asarray(weights, dtype=np.float64)
    valid = w > 0.01
    if valid.sum() < 6:
        return {"error": f"yetersiz kp ({int(valid.sum())} < 6)"}
    obj = np.asarray(K3, dtype=np.float64)[valid]
    img = np.asarray(K2, dtype=np.float64)[valid]
    # Confidence > 0.5 inlier seed (RANSAC)
    use_ransac = True
    rvec_arr = None if rvec_init is None else np.asarray(rvec_init,
                                                                       dtype=np.float64).reshape(3, 1)
    tvec_arr = None if tvec_init is None else np.asarray(tvec_init,
                                                                       dtype=np.float64).reshape(3, 1)
    try:
        if use_ransac and len(obj) >= 8:
            ok, rvec, tvec, inliers = cv2.solvePnPRansac(
                obj, img, K, D,
                rvec=rvec_arr, tvec=tvec_arr,
                useExtrinsicGuess=(rvec_arr is not None),
                iterationsCount=200,
                reprojectionError=8.0,
                confidence=0.99,
                flags=cv2.SOLVEPNP_ITERATIVE,
            )
            if not ok or inliers is None or len(inliers) < 6:
                use_ransac = False
        if not use_ransac:
            ok, rvec, tvec = cv2.solvePnP(
                obj, img, K, D,
                rvec=rvec_arr, tvec=tvec_arr,
                useExtrinsicGuess=(rvec_arr is not None),
                flags=cv2.SOLVEPNP_ITERATIVE,
            )
            inliers = None
    except cv2.error as e:
        return {"error": f"opencv_solvepnp: {e}"}
    if not ok:
        return {"error": "cat_pnp_fail"}
    # Reproj error
    proj, _ = cv2.projectPoints(obj, rvec, tvec, K, D)
    proj = proj.reshape(-1, 2)
    residuals = np.linalg.norm(proj - img, axis=1)
    if inliers is not None:
        in_mask = np.zeros(len(obj), dtype=bool)
        in_mask[inliers.flatten()] = True
        n_in = int(in_mask.sum())
        rms = float(np.sqrt((residuals[in_mask] ** 2).mean()))
    else:
        n_in = len(obj)
        rms = float(np.sqrt((residuals ** 2).mean()))
    return {
        "rvec": rvec.reshape(3),
        "tvec": tvec.reshape(3),
        "n_inliers": n_in,
        "n_used": len(obj),
        "residual_px": rms,
    }


def project_points(p3d: np.ndarray, rvec: np.ndarray, tvec: np.ndarray,
                       K: np.ndarray, D: np.ndarray) -> np.ndarray:
    """3D nokta (object frame) -> 2D pixel via perspective."""
    import cv2
    p3d = np.atleast_2d(np.asarray(p3d, dtype=np.float64))
    proj, _ = cv2.projectPoints(p3d, rvec, tvec, K, D)
    return proj.reshape(-1, 2)


def rvec_to_mat(rvec: np.ndarray) -> np.ndarray:
    """Rodrigues rvec -> 3x3 rotation matrix."""
    import cv2
    R, _ = cv2.Rodrigues(np.asarray(rvec, dtype=np.float64).reshape(3, 1))
    return R


def mat_to_rvec(R: np.ndarray) -> np.ndarray:
    """3x3 R -> Rodrigues rvec."""
    import cv2
    rvec, _ = cv2.Rodrigues(np.asarray(R, dtype=np.float64))
    return rvec.reshape(3)


def transform_points(p3d: np.ndarray, rvec: np.ndarray,
                          tvec: np.ndarray) -> np.ndarray:
    """3D points (N,3) -> transformed by (R, t)."""
    R = rvec_to_mat(rvec)
    t = np.asarray(tvec, dtype=np.float64).reshape(3)
    p = np.atleast_2d(np.asarray(p3d, dtype=np.float64))
    return (R @ p.T).T + t


def invert_transform(rvec: np.ndarray, tvec: np.ndarray) -> tuple:
    """Inverse of (R|t): R_inv = R.T, t_inv = -R.T @ t."""
    R = rvec_to_mat(rvec)
    t = np.asarray(tvec, dtype=np.float64).reshape(3)
    R_inv = R.T
    t_inv = -R_inv @ t
    rvec_inv = mat_to_rvec(R_inv)
    return rvec_inv, t_inv


def compose_transforms(rvec_a: np.ndarray, tvec_a: np.ndarray,
                              rvec_b: np.ndarray, tvec_b: np.ndarray) -> tuple:
    """T_a o T_b: once T_b (frame B->C), sonra T_a (C->D). Yani:
       p_D = T_a @ T_b @ p_B = R_a @ (R_b @ p + t_b) + t_a.
    """
    R_a = rvec_to_mat(rvec_a)
    R_b = rvec_to_mat(rvec_b)
    t_a = np.asarray(tvec_a, dtype=np.float64).reshape(3)
    t_b = np.asarray(tvec_b, dtype=np.float64).reshape(3)
    R_ab = R_a @ R_b
    t_ab = R_a @ t_b + t_a
    return mat_to_rvec(R_ab), t_ab


def rotation_to_euler_deg(R: np.ndarray) -> tuple:
    """3x3 R -> (yaw, pitch, roll) deg. Z-Y-X convention."""
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
# Camera-anchored mode: fixed_position + look-at
# ============================================================================

def camera_rotation_from_lookat(cam_pos_cabin: np.ndarray,
                                            target_cabin: np.ndarray,
                                            up_cabin: np.ndarray) -> np.ndarray:
    """R_cam_cabin: kamera frame'inden cabin frame'ine rotation.

    cam_pos_cabin: kamera lens'i cabin frame'inde (cm)
    target_cabin:  kameranin baktigi nokta (cabin'de)
    up_cabin:      cabin'deki "up" yonu (genelde [0,1,0])

    OpenCV camera convention: +Z out (looking direction), +X right, +Y down.
    """
    cam = np.asarray(cam_pos_cabin, dtype=np.float64).reshape(3)
    tgt = np.asarray(target_cabin, dtype=np.float64).reshape(3)
    up = np.asarray(up_cabin, dtype=np.float64).reshape(3)
    z = tgt - cam
    nz = float(np.linalg.norm(z))
    if nz < 1e-6:
        raise ValueError("Camera position cabin origin'e cok yakin")
    z = z / nz
    # X = z cross up (camera right). Up parallel ise alternatif sec.
    x = np.cross(z, up)
    nx = float(np.linalg.norm(x))
    if nx < 1e-6:
        # up Z ile parallel — alternatif up
        up2 = np.array([1.0, 0.0, 0.0]) if abs(up[0]) < 0.5 \
                else np.array([0.0, 0.0, 1.0])
        x = np.cross(z, up2)
        nx = float(np.linalg.norm(x))
    x = x / nx
    y = np.cross(z, x)
    return np.column_stack([x, y, z])


def cat_to_cabin_via_fixed_camera(rvec_cat_cam: np.ndarray,
                                                tvec_cat_cam: np.ndarray,
                                                cam_pos_cabin: np.ndarray,
                                                target_cabin: np.ndarray,
                                                up_cabin: np.ndarray) -> tuple:
    """Camera-anchored cat -> cabin: fixed kamera pozisyonu + look-at kullan.

    R_cam_cabin = lookat(cam_pos, target, up)
    T_cat_cabin = T_cam_cabin o T_cat_cam
      R_cat_cabin = R_cam_cabin @ R_cat_cam
      t_cat_cabin = R_cam_cabin @ t_cat_cam + cam_pos_cabin
    """
    R_cam_cabin = camera_rotation_from_lookat(cam_pos_cabin, target_cabin,
                                                              up_cabin)
    rvec_cam_cabin = mat_to_rvec(R_cam_cabin)
    tvec_cam_cabin = np.asarray(cam_pos_cabin, dtype=np.float64).reshape(3)
    return compose_transforms(rvec_cam_cabin, tvec_cam_cabin,
                                       rvec_cat_cam, tvec_cat_cam)


def cat_to_cabin_transform(rvec_cat_cam: np.ndarray, tvec_cat_cam: np.ndarray,
                                     rvec_mark_cam: np.ndarray, tvec_mark_cam: np.ndarray,
                                     qr_to_origin_cm: np.ndarray) -> tuple:
    """Compose: cat -> camera, marker -> camera, qr_offset (marker->cabin origin).

    Returns: (rvec_cat_cabin, tvec_cat_cabin) — cat frame'inde nokta verirsen
    cabin frame'ine cevirir. p_cabin = R_cc @ p_cat + t_cc.

    Mantik:
      T_cat_cam: cat -> camera (kp PnP'den)
      T_mark_cam: marker -> camera (marker PnP'den)
      T_cam_mark = inv(T_mark_cam): camera -> marker
      T_mark_cabin: marker origin -> cabin origin = sadece translation qr_to_origin
        (rotation = identity, marker eksenleri kabin eksenleri ile aligned varsayim)
      T_cat_cabin = T_mark_cabin o T_cam_mark o T_cat_cam
    """
    # cat -> cam -> marker
    rvec_cam_mark, tvec_cam_mark = invert_transform(rvec_mark_cam, tvec_mark_cam)
    # cat -> marker = (cam->marker) o (cat->cam)
    rvec_cat_mark, tvec_cat_mark = compose_transforms(
        rvec_cam_mark, tvec_cam_mark,
        rvec_cat_cam, tvec_cat_cam,
    )
    # marker -> cabin: rotation identity, translation = qr_to_origin
    q = np.asarray(qr_to_origin_cm, dtype=np.float64).reshape(3)
    rvec_mark_cabin = np.zeros(3, dtype=np.float64)
    tvec_mark_cabin = q
    # cat -> cabin = (marker->cabin) o (cat->marker)
    return compose_transforms(rvec_mark_cabin, tvec_mark_cabin,
                                       rvec_cat_mark, tvec_cat_mark)
