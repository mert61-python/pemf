# Author: mertaygn, cglrgrkn
"""pipeline.py - Main organ position estimation (Procrustes-based)."""
from __future__ import annotations
import numpy as np

from .canonical import (KEYPOINT_NAMES, CANONICAL_CAT_3D, CANONICAL_ORGANS_3D,
                                BETA_DIM, BETA_MEAN, BETA_STD, BETA_MIN, BETA_MAX,
                                get_organs_atlas_for_pose)
from .geometry import (weighted_procrustes_fit, project_3d_to_2d,
                                project_3d_with_depth, rotation_to_euler_deg,
                                apply_morphology_to_atlas,
                                apply_morphology_to_canonical_kp)
from .qr import (estimate_organs_qr, beta_to_morphology, detect_aruco_marker)
from .mask_features import (mask_pca_axis, validate_kp_in_mask,
                                       organ_in_mask_flags)
from .priors import (impute_lr_symmetric_kps, bootstrap_organ_uncertainty)
from .camera import (load_intrinsics, approximate_intrinsics,
                              solve_marker_pose, solve_cat_pose_pnp,
                              project_points, transform_points,
                              cat_to_cabin_transform,
                              cat_to_cabin_via_fixed_camera,
                              rvec_to_mat, rotation_to_euler_deg as _rot_euler)
from .cabin_config import (has_perspective_data, is_camera_anchored,
                                       axis_to_vector)


def guven_dokumu_hesapla(pose_confidence: float, depth_factor: float,
                          in_mask: bool, cm_sd: float, cabin_active: bool):
    """Organ reliability + bileşen dökümü — TEK formül kaynağı (sunum-katmanı XAI, 2026-08-26).

    Eskiden ayni formul estimate_organs_pnp icinde inline'di ve bilesenler ATILIYORDU;
    operator "Guven %62"nin nedenini (poz mu, maske-disi mi, kalibrasyonsuzluk mu)
    goremiyordu. Simdi: rel = poz × derinlik × maske × belirsizlik, kalibresizken
    Audit-P2 tavani min(rel, 0.25) — ve her bilesen dokumde raporlanir.

    Doner: (reliability, {"pose_confidence", "depth_factor", "mask_factor",
            "uncertainty_factor", "calibration_cap"}).
    """
    mask_factor = 1.0 if in_mask else 0.6
    uncertainty_factor = float(np.clip(1.0 - cm_sd / 10.0, 0.4, 1.0))
    rel = float(pose_confidence) * float(depth_factor) * mask_factor * uncertainty_factor
    cap = None if cabin_active else 0.25
    if cap is not None:
        rel = min(rel, cap)
    return rel, {
        "pose_confidence": round(float(pose_confidence), 3),
        "depth_factor": round(float(depth_factor), 3),
        "mask_factor": mask_factor,
        "uncertainty_factor": round(uncertainty_factor, 3),
        "calibration_cap": cap,
    }


def estimate_organs_pnp(kp_dict: dict, kp_conf: np.ndarray,
                            bbox: np.ndarray, pose_info: dict,
                            mask_xy: list | None = None,
                            image_path: str | None = None,
                            cabin_params: dict | None = None) -> dict:
    """Canonical 3D cat model'i 2D DLC keypoint'lere fit eder.

    Sonra organlarin canonical 3D pozisyonlarini ayni transform ile 2D'ye
    projekte eder. Tum poslar icin tek matematik (Procrustes).

    Args:
        kp_dict: {kp_name: np.array([u, v])} guvenilir keypoint'ler
        kp_conf: (39,) confidence vektoru (KEYPOINT_NAMES sirasinda)
        bbox: [x1, y1, x2, y2]
        pose_info: classify_pose ciktisi
    """
    # QR-canonical: ArUco marker + canonical atlas (deterministik, ML-free).
    # ArUco yoksa: yine canonical default β=(1,1,1,0) — fallback YOK.
    qr_result = None
    kp_conf_full = (kp_conf if kp_conf is not None
                          else np.ones(len(KEYPOINT_NAMES)))
    try:
        if image_path is not None:
            qr_result = estimate_organs_qr(image_path, kp_dict, kp_conf_full,
                                                       bbox)
    except Exception as e:
        print(f"  ! QR pipeline error: {e}")
        qr_result = None
    if qr_result and qr_result.get("success"):
        morph = qr_result["morphology"]
        morph["bcs_source"] = "QR-canonical"
    else:
        # ArUco yok -> canonical default (sx=sy=sz=1, BCS=0)
        err = qr_result.get("error") if qr_result else "no_image_path"
        print(f"  ! ArUco/QR yok ({err}) -> canonical default")
        morph = {
            "sx": 1.0, "sy": 1.0, "sz": 1.0, "bcs": 0.0,
            "method": ["canonical-default"],
            "raw": {"qr_error": err},
            "summary": "sx=1.00 sy=1.00 sz=1.00 BCS=+0.00 (canonical-default)",
            "bcs_source": "canonical-default",
        }
    morph["pose_type"] = pose_info.get("type", "unknown")
    arch_label = "QR" if (qr_result and qr_result.get("success")) else "DEFAULT"
    morph["summary"] = f"[{arch_label}] " + morph["summary"] + \
                              f"  (poz={morph['pose_type']})"
    # ------------------------------------------------------------------
    # [1] MASK PCA + KP validation
    # ------------------------------------------------------------------
    mask_pca = mask_pca_axis(mask_xy) if mask_xy is not None else {"ok": False}
    if mask_pca.get("ok") and kp_conf is not None:
        val = validate_kp_in_mask(kp_dict, kp_conf_full, KEYPOINT_NAMES,
                                              mask_xy, outside_penalty=0.5)
        kp_conf_validated = val["new_conf"]
        outside_kp = val["outside_kp"]
    else:
        kp_conf_validated = kp_conf_full
        outside_kp = []

    # ------------------------------------------------------------------
    # [3] L/R simetri imputation (Procrustes'ten ONCE)
    # ------------------------------------------------------------------
    imp = impute_lr_symmetric_kps(kp_dict, kp_conf_validated,
                                              KEYPOINT_NAMES,
                                              conf_threshold=0.30,
                                              imputed_weight=0.30)
    kp_dict_aug = imp["kp_dict"]
    kp_conf_aug = imp["kp_conf"]
    imputed_kp = imp["imputed_kp"]

    # ------------------------------------------------------------------
    # [4] Pose-conditional organ atlas
    # ------------------------------------------------------------------
    pose_type = pose_info.get("type", "unknown")
    organs_canonical = get_organs_atlas_for_pose(pose_type)

    # Per-cat scaled atlas (canonical kp ve pose-conditional organ)
    kp_atlas_scaled = apply_morphology_to_canonical_kp(morph)
    organs_atlas_scaled = apply_morphology_to_atlas(organs_canonical, morph)

    # K3 ve K2 dizilerini KEYPOINT_NAMES sirasinda hazirla (per-cat olcekli)
    K3 = np.array([kp_atlas_scaled[n] for n in KEYPOINT_NAMES],
                    dtype=np.float64)                              # (39, 3) per-cat
    K2 = np.zeros((len(KEYPOINT_NAMES), 2), dtype=np.float64)
    w = np.zeros(len(KEYPOINT_NAMES), dtype=np.float64)
    for i, n in enumerate(KEYPOINT_NAMES):
        if n in kp_dict_aug:
            K2[i] = kp_dict_aug[n]
            w[i] = float(kp_conf_aug[i]) if kp_conf_aug is not None else 1.0

    # Occlusion handling: cok dusuk confidence keypoint'leri sifirla
    OCCLUSION_THR = 0.3
    n_occluded = (int((kp_conf_aug < OCCLUSION_THR).sum())
                       if kp_conf_aug is not None else 0)
    if kp_conf_aug is not None:
        w[kp_conf_aug < OCCLUSION_THR] = 0.0

    fit = weighted_procrustes_fit(K3, K2, w)
    if "error" in fit:
        return {"error": fit["error"]}

    # Mirror flip check: sag/sol keypoint'lerin Z bilesenleri tutarli mi?
    # Right kp'ler canonical olarak Z>0, left kp'ler Z<0.
    # Fitted R uygulandiktan sonra image x ekseninde sag/sol konum mantikli mi?
    mirror_warning = None
    R_init = fit["R"]
    s_init = fit["s"]
    t_init = fit["t"]
    pairs = [("right_eye", "left_eye"),
                ("right_earbase", "left_earbase"),
                ("front_right_paw", "front_left_paw")]
    mirror_votes = []
    for r_name, l_name in pairs:
        if r_name in kp_dict and l_name in kp_dict:
            # Canonical 3D: right_eye Z=+2.5, left_eye Z=-2.5
            # Fitted projection of right - left in 2D X (image u):
            i_r = KEYPOINT_NAMES.index(r_name)
            i_l = KEYPOINT_NAMES.index(l_name)
            proj_r = s_init * (R_init @ K3[i_r])[:2] + t_init
            proj_l = s_init * (R_init @ K3[i_l])[:2] + t_init
            expected_du = proj_r[0] - proj_l[0]
            actual_du = kp_dict[r_name][0] - kp_dict[l_name][0]
            # Eger isaretler ayni -> dogru; aksi -> mirror flip suphesi
            if expected_du * actual_du < 0:
                mirror_votes.append(1)
            else:
                mirror_votes.append(0)
    if mirror_votes and sum(mirror_votes) > len(mirror_votes) / 2:
        mirror_warning = (f"Olasi sag/sol keypoint karisikligi "
                            f"({sum(mirror_votes)}/{len(mirror_votes)} cift uyusmadi)")

    s, R, t = fit["s"], fit["R"], fit["t"]
    yaw, pitch, roll = rotation_to_euler_deg(R)

    # Organlari per-cat scaled atlas'tan projekte et
    organs_out = {}
    org_3d_coords = []
    org_items = list(organs_atlas_scaled.items())
    for oid, (name, x3, y3, z3) in org_items:
        org_3d_coords.append([x3, y3, z3])
    org_3d = np.array(org_3d_coords, dtype=np.float64)
    org_xy, org_z = project_3d_with_depth(org_3d, s, R, t)

    # ------------------------------------------------------------------
    # [2] Bootstrap uncertainty — organ pozisyon std'si
    # ------------------------------------------------------------------
    boot = bootstrap_organ_uncertainty(K3, K2, w, org_3d,
                                                 n_iter=30,
                                                 subsample_frac=0.80,
                                                 rng_seed=42)
    organ_xy_std = boot["organ_xy_std"]
    organ_3d_std = boot["organ_3d_std"]

    # ------------------------------------------------------------------
    # [1b] Organ-in-mask flags
    # ------------------------------------------------------------------
    organ_in_mask = (organ_in_mask_flags(org_xy, mask_xy)
                          if mask_xy is not None else [True] * len(org_xy))

    # ------------------------------------------------------------------
    # [LEVEL 3] Perspektif projeksiyon (cabin_config varsa)
    # ------------------------------------------------------------------
    perspective = None
    cabin_config = cabin_params.get("config") if cabin_params else None
    if cabin_config is not None and has_perspective_data(cabin_config) \
       and image_path is not None:
        try:
            perspective = _run_perspective_pipeline(
                image_path=image_path,
                cabin_config=cabin_config,
                K3=K3, K2=K2, w=w,
                organs_3d=org_3d,
                init_rvec=None, init_tvec=None,
            )
        except Exception as e:
            print(f"  ! Perspektif pipeline hatasi: {e}")
            perspective = {"error": str(e)}

    # Kabin koord donusumu (QR varken)
    cabin_active = False
    cm_per_px = None
    qr_center_px = None
    qr_origin_offset = [0.0, 0.0, 0.0]
    if cabin_params is not None and image_path is not None:
        try:
            qr_inf = detect_aruco_marker(image_path)
            if not qr_inf.get("error"):
                cm_per_px = qr_inf["cm_per_px"]
                qr_center_px = qr_inf["center_px"]
                qr_origin_offset = cabin_params.get("qr_to_origin_cm",
                                                                [0.0, 0.0, 0.0])
                cabin_active = True
        except Exception:
            pass

    z_mid = float(np.mean(org_z))
    for i, (oid, (name, x3, y3, z3)) in enumerate(org_items):
        rel_z = float(org_z[i] - z_mid)
        depth_factor = 1.0 - 0.3 * (rel_z / max(abs(rel_z) + 5.0, 5.0))
        depth_factor = float(np.clip(depth_factor, 0.5, 1.0))
        # Canonical (kullanici reference icin) ve scaled (per-cat) 3D koord
        canon = CANONICAL_ORGANS_3D[oid]                          # (name, x, y, z)
        # Bootstrap uncertainty
        px_sd = float(np.linalg.norm(organ_xy_std[i]))      # px (skalar)
        cm_sd = float(np.linalg.norm(organ_3d_std[i]))      # cm (skalar)
        # Mask flag (organ vucut silueti icinde mi)
        in_mask = bool(organ_in_mask[i]) if i < len(organ_in_mask) else True
        # Reliability = poz × derinlik × maske × belirsizlik (+ Audit-P2 kalibresiz 0.25 tavani).
        # Formul TEK kaynakta (guven_dokumu_hesapla) — bilesenler entry'ye de yazilir ki
        # operator dusuk guvenin NEDENINI gorebilsin (sunum-katmani XAI, 2026-08-26).
        rel_unc, guven_dokumu = guven_dokumu_hesapla(
            pose_info["confidence"], depth_factor, in_mask, cm_sd, cabin_active
        )
        entry = {
            "name": name,
            "pixel_xy": [round(float(org_xy[i, 0]), 1),
                           round(float(org_xy[i, 1]), 1)],
            "coord_3d_cm": [round(x3, 2), round(y3, 2), round(z3, 2)],
            "coord_3d_canonical_cm": [round(canon[1], 2),
                                            round(canon[2], 2),
                                            round(canon[3], 2)],
            "depth_z_rel": round(rel_z, 2),
            "position_std_px": round(px_sd, 2),
            "position_std_cm": round(cm_sd, 2),
            "position_std_3d_cm": [round(float(organ_3d_std[i, 0]), 2),
                                          round(float(organ_3d_std[i, 1]), 2),
                                          round(float(organ_3d_std[i, 2]), 2)],
            "in_body_mask": in_mask,
            "reliability": round(rel_unc, 3),
            "reliability_components": guven_dokumu,  # sunum-katmani XAI: guvenin NEDENI (2026-08-26)
            "calibrated": bool(cabin_active),  # Audit P2: ArUco/kabin kalibrasyonu var mi (coord olculmus mu)
        }
        # Level 3: perspektif sonuc varsa cabin mutlak 3D koord ekle
        if perspective is not None and "organs_cabin_cm" in perspective:
            cabin_xyz = perspective["organs_cabin_cm"][i]
            entry["coord_cabin_cm"] = [round(float(cabin_xyz[0]), 2),
                                                round(float(cabin_xyz[1]), 2),
                                                round(float(cabin_xyz[2]), 2)]
            entry["pixel_xy_perspective"] = [
                round(float(perspective["organs_pixel"][i, 0]), 1),
                round(float(perspective["organs_pixel"][i, 1]), 1)]
            entry["cabin_origin"] = "perspective_solvePnP"
        # Cabin koord (QR varken, weak-perspective fallback):
        # Perspektif yoksa veya basarisizsa pixel -> cm -> cabin offset
        if cabin_active and "coord_cabin_cm" not in entry:
            dx_cm = (float(org_xy[i, 0]) - qr_center_px[0]) * cm_per_px
            dy_cm = (float(org_xy[i, 1]) - qr_center_px[1]) * cm_per_px
            cabin_x = dx_cm + qr_origin_offset[0]
            cabin_y = dy_cm + qr_origin_offset[1]
            cabin_z = rel_z + qr_origin_offset[2]                 # depth proxy
            entry["coord_cabin_cm"] = [round(cabin_x, 2),
                                                round(cabin_y, 2),
                                                round(cabin_z, 2)]
            entry["cabin_origin"] = "QR_marker_center + qr_to_origin_cm"
        organs_out[oid] = entry

    # Head/tail axis (canonical -> projected)
    head_2d = project_3d_to_2d(np.array([19.0, -1.0, 0.0]),
                                   s, R, t)[0]                # nose
    tail_2d = project_3d_to_2d(np.array([-20.0, 2.0, 0.0]),
                                   s, R, t)[0]                # tail_end

    # Tum keypoint'leri fitted modelden tahmin et (gorsel icin)
    K3_proj = s * (R @ K3.T).T[:, :2] + t                       # (39, 2)
    fitted_keypoints_2d = {n: [round(float(K3_proj[i, 0]), 1),
                                  round(float(K3_proj[i, 1]), 1)]
                              for i, n in enumerate(KEYPOINT_NAMES)}

    return {
        "organs": organs_out,
        "axis": {
            "head_pixel": [round(float(head_2d[0]), 1),
                              round(float(head_2d[1]), 1)],
            "tail_pixel": [round(float(tail_2d[0]), 1),
                              round(float(tail_2d[1]), 1)],
        },
        "method": "pnp_procrustes_3d",
        "pnp_fit": {
            "scale_px_per_cm": round(s, 3),
            "yaw_deg": round(yaw, 1),
            "pitch_deg": round(pitch, 1),
            "roll_deg": round(roll, 1),
            "residual_px": round(fit["residual_px"], 2),
            "n_keypoints_used": fit["n_used"],
            "n_inliers": fit.get("n_inliers"),
            "huber_delta_px": fit.get("huber_delta_px"),
            "robust_iterations": fit.get("robust_iterations", 0),
            "n_occluded_kp": n_occluded,
            "mirror_warning": mirror_warning,
            "n_imputed_kp": len(imputed_kp),
            "imputed_kp": imputed_kp,
            "n_outside_mask_kp": len(outside_kp),
            "outside_mask_kp": outside_kp,
            "bootstrap_iters": boot.get("n_succ", 0),
            "bootstrap_scale_std": round(boot.get("scale_std", 0.0), 3),
            "pose_atlas_used": pose_type,
            "mask_pca": (mask_pca if mask_pca.get("ok") else None),
            "perspective": (perspective.get("info") if perspective else None),
        },
        "R_matrix": R.tolist(),
        "t_vec": t.tolist(),
        "fitted_keypoints_2d": fitted_keypoints_2d,
        "morphology": morph,                                      # L1+L2 per-cat
    }


# ============================================================================
# LEVEL 3: Perspektif projeksiyon pipeline
# ============================================================================

def _detect_marker_corners(image_path: str, aruco_dict_name: str) -> dict:
    """ArUco markeri tespit et, 4 kose pixel koord doner.

    Returns: {"corners_px": (4,2), "id": int, "edge_px": float, "center_px":(2,),
                  "image_shape": (H,W,3)} veya {"error": str}.
    """
    import cv2
    img = cv2.imread(image_path)
    if img is None:
        return {"error": "image_read_fail"}
    try:
        aruco_dict = cv2.aruco.getPredefinedDictionary(
            getattr(cv2.aruco, aruco_dict_name))
    except AttributeError:
        return {"error": f"aruco_dict_invalid: {aruco_dict_name}"}
    detector = cv2.aruco.ArucoDetector(aruco_dict)
    corners_all, ids, _ = detector.detectMarkers(img)
    if ids is None or len(ids) == 0:
        return {"error": "no_aruco_detected"}
    idx = int(np.argmin(ids.flatten()))
    c = corners_all[idx][0]                                     # (4,2)
    edges = [float(np.linalg.norm(c[i] - c[(i + 1) % 4])) for i in range(4)]
    edge_mean = float(np.mean(edges))
    center = c.mean(axis=0)
    return {
        "corners_px": np.asarray(c, dtype=np.float64),
        "id": int(ids.flatten()[idx]),
        "edge_px": edge_mean,
        "center_px": center.tolist(),
        "image_shape": img.shape,
    }


def _run_perspective_pipeline(image_path: str, cabin_config: dict,
                                          K3: np.ndarray, K2: np.ndarray,
                                          w: np.ndarray,
                                          organs_3d: np.ndarray,
                                          init_rvec=None, init_tvec=None) -> dict:
    """Level 3 perspective: marker pose + cat PnP + cat->cabin compose.

    Adimlari:
      1. ArUco marker detect (kose pixel)
      2. Intrinsics: .npz veya marker mesafesinden yaklasik
      3. solvePnP: marker -> camera (4 kose)
      4. solvePnP: cat canonical 3D -> 2D kp correspondences
      5. Compose: cat -> cabin transform
      6. Organlari cabin frame'e + pixel'e projekte et

    Returns: {
      "info": dict (loga gore),
      "organs_cabin_cm": (N,3),
      "organs_pixel": (N,2),
      "K": (3,3), "rvec_cat_cam":(3,), "tvec_cat_cam":(3,),
      "rvec_mark_cam":(3,), "tvec_mark_cam":(3,),
    }
    """
    aruco_dict = cabin_config["aruco"]["dict"]
    marker_real_cm = float(cabin_config["aruco"]["real_cm"])
    plane_offset_cm = float(cabin_config["aruco"].get("plane_offset_cm", 0.0))
    normal_axis_str = cabin_config["aruco"].get("normal_axis_in_cabin", "+Y")
    qr_to_origin = np.asarray(
        cabin_config["geometry"]["qr_to_origin_cm"], dtype=np.float64)
    cam_to_marker = cabin_config["camera"].get("to_marker_cm")
    intrinsics_npz = cabin_config["camera"].get("intrinsics_npz")
    # Camera-anchored mod parametreleri (yan kamera icin onerilen)
    cam_anchored = is_camera_anchored(cabin_config)
    fixed_pos = cabin_config["camera"].get("fixed_position_cm")
    look_at = cabin_config["camera"].get("look_at_cm", [0.0, 0.0, 0.0])
    up_cabin = cabin_config["camera"].get("up_cabin", [0.0, 1.0, 0.0])

    # 1. Marker detect
    mk = _detect_marker_corners(image_path, aruco_dict)
    if "error" in mk:
        return {"error": f"marker_detect: {mk['error']}"}
    corners = mk["corners_px"]
    img_shape = mk["image_shape"]

    # 2. Intrinsics
    intr = None
    yaml_dir = cabin_config.get("_yaml_path")
    if intrinsics_npz:
        intr = load_intrinsics(intrinsics_npz,
                                       yaml_dir=str(yaml_dir) if yaml_dir else None)
    if intr is None and cam_to_marker is not None:
        intr = approximate_intrinsics(img_shape, mk["edge_px"],
                                                  marker_real_cm,
                                                  float(cam_to_marker))
    if intr is None:
        return {"error": "no_intrinsics_no_distance"}
    K = intr["K"]
    D = intr["D"]

    # 3. Marker pose
    mp = solve_marker_pose(corners, marker_real_cm, K, D)
    if "error" in mp:
        return {"error": f"marker_pose: {mp['error']}"}
    rvec_mark_cam = mp["rvec"]
    tvec_mark_cam = mp["tvec"]

    # 4. Cat pose via PnP
    cp = solve_cat_pose_pnp(K3, K2, w, K, D,
                                       rvec_init=init_rvec, tvec_init=init_tvec)
    if "error" in cp:
        return {"error": f"cat_pose: {cp['error']}"}
    rvec_cat_cam = cp["rvec"]
    tvec_cat_cam = cp["tvec"]

    # 5. Compose cat -> cabin
    if cam_anchored:
        # --- Camera-anchored mod (yan kamera icin onerilen) ---
        # Marker rotation kullanilmaz, fixed_position + look-at ile cabin frame
        # direkt belirlenir. Marker sadece scale (ve opsiyonel validation) icin.
        try:
            rvec_cat_cabin, tvec_cat_cabin = cat_to_cabin_via_fixed_camera(
                rvec_cat_cam, tvec_cat_cam,
                np.asarray(fixed_pos, dtype=np.float64),
                np.asarray(look_at, dtype=np.float64),
                np.asarray(up_cabin, dtype=np.float64),
            )
            anchor_mode = "camera_anchored"
        except Exception as e:
            return {"error": f"camera_anchored_fail: {e}"}
    else:
        # --- Marker-anchored mod (tavan kamera, marker yere yapisik) ---
        # plane_offset_cm marker normaline gore uygulanir (axis-aware).
        # Marker rotation cabin frame'inde identity varsayilir.
        normal_vec = np.asarray(axis_to_vector(normal_axis_str), dtype=np.float64)
        plane_offset_vec = plane_offset_cm * normal_vec
        qr_off_eff = qr_to_origin + plane_offset_vec
        rvec_cat_cabin, tvec_cat_cabin = cat_to_cabin_transform(
            rvec_cat_cam, tvec_cat_cam,
            rvec_mark_cam, tvec_mark_cam,
            qr_off_eff,
        )
        anchor_mode = "marker_anchored"

    # 6. Organlari projekte et + cabin frame'e
    organs_pixel = project_points(organs_3d, rvec_cat_cam, tvec_cat_cam, K, D)
    organs_cabin = transform_points(organs_3d, rvec_cat_cabin, tvec_cat_cabin)

    # Cat orientation in cabin frame (Euler)
    R_cat_cabin = rvec_to_mat(rvec_cat_cabin)
    yaw_c, pitch_c, roll_c = _rot_euler(R_cat_cabin)
    # Marker depth (camera Z) — bilgi
    marker_depth_cm = float(np.linalg.norm(tvec_mark_cam))

    info = {
        "enabled": True,
        "anchor_mode": anchor_mode,
        "intrinsics_source": intr.get("source", "npz") if "source" in intr else "npz",
        "f_px": float(K[0, 0]),
        "cx_px": float(K[0, 2]),
        "cy_px": float(K[1, 2]),
        "image_shape": [int(img_shape[0]), int(img_shape[1])],
        "marker_id": mk["id"],
        "marker_edge_px": round(mk["edge_px"], 1),
        "marker_depth_cm": round(marker_depth_cm, 2),
        "cat_pnp_residual_px": round(cp["residual_px"], 2),
        "cat_pnp_inliers": cp["n_inliers"],
        "cat_pnp_n_used": cp["n_used"],
        "cat_cabin_yaw_deg": round(yaw_c, 1),
        "cat_cabin_pitch_deg": round(pitch_c, 1),
        "cat_cabin_roll_deg": round(roll_c, 1),
        "cat_position_in_cabin_cm": [round(float(tvec_cat_cabin[0]), 2),
                                              round(float(tvec_cat_cabin[1]), 2),
                                              round(float(tvec_cat_cabin[2]), 2)],
        "plane_offset_cm": plane_offset_cm,
    }
    return {
        "info": info,
        "organs_cabin_cm": organs_cabin,
        "organs_pixel": organs_pixel,
        "K": K,
        "rvec_cat_cam": rvec_cat_cam,
        "tvec_cat_cam": tvec_cat_cam,
        "rvec_mark_cam": rvec_mark_cam,
        "tvec_mark_cam": tvec_mark_cam,
        "rvec_cat_cabin": rvec_cat_cabin,
        "tvec_cat_cabin": tvec_cat_cabin,
    }


# ============================================================================
# 3D Cat Body Mesh (canonical primitives)
# ============================================================================
