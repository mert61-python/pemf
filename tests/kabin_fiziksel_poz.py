# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""Test aparatı (D1.100): ÜRÜN kabin YAML'ından FİZİKSEL TUTARLI ArUco pozu ve izdüşüm.

Kamera `camera.fixed_position_cm`de, `look_at_cm`e bakar, `up_cabin` yukarı; marker `-qr_to_origin`da (arka duvar,
normal `aruco.normal_axis_in_cabin`). OpenCV sözleşmesi: P_kam = R · P_marker + t. Eski karakterizasyon pozu (R = I,
t = (0, 0, 500)) kamerayı marker'ın ARKASINA koyuyordu — fiziksel değil; dönüşüm hatasını (B-5.16) gizledi.
"""

from __future__ import annotations

import numpy as np


def genis_aci_ic_parametre(ct):
    """Sentetik geniş açı (yatay ~104°): köşedeki kamera kabinin çoğunu görsün."""
    return ct.CameraIntrinsics(
        K=np.array([[500.0, 0.0, 640.0], [0.0, 500.0, 360.0], [0.0, 0.0, 1.0]]),
        D=np.zeros((1, 5)),
        image_size=(1280, 720),
        rms=0.0,
    )


def fiziksel_poz(ct, cfg):
    """→ (CabinPose, R_kabin→kamera, kamera merkezi C [mm])."""
    from ai_hub.cv_ortak.coord_transform import _axis_vec, _marker_to_cabin_R

    C = np.array(cfg.camera.fixed_position_cm, dtype=float) * 10.0
    hedef = np.array(cfg.camera.look_at_cm, dtype=float) * 10.0
    yukari = np.array(cfg.camera.up_cabin, dtype=float)
    z = hedef - C
    z /= np.linalg.norm(z)
    y = -(yukari - z * float(np.dot(yukari, z)))  # OpenCV: y AŞAĞI
    y /= np.linalg.norm(y)
    x = np.cross(y, z)
    R_kk = np.vstack([x, y, z])  # kabin → kamera
    M = np.array([-float(v) * 10.0 for v in cfg.geometry.qr_to_origin_cm])
    ofset = np.array(_axis_vec(cfg.aruco.normal_axis_in_cabin), dtype=float) * (cfg.aruco.plane_offset_cm * 10.0)
    R = R_kk @ _marker_to_cabin_R(cfg)
    t = R_kk @ (M + ofset - C)
    poz = ct.CabinPose(
        marker_id=0, rvec=np.zeros((3, 1)), tvec=t.reshape(3, 1), R=R, reproj_error_px=0.0, marker_pos_cabin_mm=M
    )
    return poz, R_kk, C


def izdusur(K, R_kk, C, P):
    """Kabin noktası → piksel (kameranın önünde değilse None)."""
    pk = R_kk @ (np.asarray(P, float) - C)
    if pk[2] <= 0:
        return None
    u, v, w = K @ pk
    return (float(u / w), float(v / w))
