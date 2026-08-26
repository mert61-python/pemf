#!/usr/bin/env python3
"""calibrate_camera.py - Sahmat tahtasi kamera kalibrasyonu.

Kullanim:
  1. Yazici ciktisi sahmat tahtasi (orn. 9x6 ic kose, kare boyu olculmus)
  2. Tahtayi 20-30 farkli aci/mesafede foto cek (kabinde, ayni kamera ile)
  3. Bu script'i fotograflarin klasoru ile calistir:

     python calibrate_camera.py \
       --images calib_photos/ \
       --pattern 9x6 \
       --square-cm 2.5 \
       --output calib_klinik_v1.npz

Cikti: .npz dosyasi -> cabin_config.yaml -> camera.intrinsics_npz
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--images", required=True, help="Sahmat foto klasoru")
    p.add_argument("--pattern", default="9x6",
                       help="Ic kose sayisi WxH (default 9x6)")
    p.add_argument("--square-cm", type=float, required=True,
                       help="Bir karenin kenar uzunlugu (cm)")
    p.add_argument("--output", default="calib.npz",
                       help="Cikti .npz dosyasi")
    p.add_argument("--max-images", type=int, default=50)
    p.add_argument("--show-progress", action="store_true")
    args = p.parse_args()

    import cv2
    cols, rows = (int(v) for v in args.pattern.split("x"))
    sq = float(args.square_cm)

    # Object points (her foto icin ayni): (rows*cols, 3) - z=0
    objp = np.zeros((rows * cols, 3), dtype=np.float32)
    objp[:, :2] = np.mgrid[0:cols, 0:rows].T.reshape(-1, 2) * sq

    folder = Path(args.images).expanduser().resolve()
    if not folder.exists():
        print(f"HATA: {folder} yok"); sys.exit(1)
    paths = sorted([p for p in folder.iterdir()
                       if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".bmp")])
    if len(paths) == 0:
        print(f"HATA: {folder} icinde foto yok"); sys.exit(1)
    paths = paths[:args.max_images]
    print(f"{len(paths)} foto bulundu. Pattern: {cols}x{rows} kose, "
          f"square={sq}cm")

    obj_points = []
    img_points = []
    image_size = None
    n_ok = 0
    n_fail = 0
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)

    for i, pth in enumerate(paths):
        img = cv2.imread(str(pth))
        if img is None:
            n_fail += 1
            continue
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        if image_size is None:
            image_size = gray.shape[::-1]      # (W, H)
        flags = (cv2.CALIB_CB_ADAPTIVE_THRESH +
                  cv2.CALIB_CB_NORMALIZE_IMAGE +
                  cv2.CALIB_CB_FAST_CHECK)
        ok, corners = cv2.findChessboardCorners(gray, (cols, rows), flags)
        if not ok:
            n_fail += 1
            if args.show_progress:
                print(f"  [{i+1}/{len(paths)}] {pth.name}: FAIL")
            continue
        corners2 = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1),
                                                criteria)
        obj_points.append(objp)
        img_points.append(corners2)
        n_ok += 1
        if args.show_progress:
            print(f"  [{i+1}/{len(paths)}] {pth.name}: OK")

    print(f"\nBasarili: {n_ok}  Basarisiz: {n_fail}")
    if n_ok < 8:
        print("HATA: en az 8 basarili foto gerek. Pattern dogru mu?")
        sys.exit(2)

    print("\ncalibrateCamera calisiyor...")
    ret, K, D, rvecs, tvecs = cv2.calibrateCamera(
        obj_points, img_points, image_size, None, None)
    print(f"  RMS reproj error: {ret:.3f} px")
    print(f"  K (intrinsics):\n{K}")
    print(f"  D (distortion): {D.flatten()}")

    # Per-image reproj error
    err_total = 0.0
    for i in range(len(obj_points)):
        proj, _ = cv2.projectPoints(obj_points[i], rvecs[i], tvecs[i], K, D)
        err = cv2.norm(img_points[i], proj, cv2.NORM_L2) / len(proj)
        err_total += err
    print(f"  Mean per-image reproj: {err_total / len(obj_points):.3f} px")

    out_path = Path(args.output).resolve()
    np.savez(str(out_path),
                K=K, D=D,
                image_size=np.array(image_size, dtype=np.int32),
                rms=float(ret),
                n_images=int(n_ok))
    print(f"\nKaydedildi: {out_path}")
    print(f"YAML'de kullan:\n  camera:\n    intrinsics_npz: {out_path.name}")


if __name__ == "__main__":
    main()
