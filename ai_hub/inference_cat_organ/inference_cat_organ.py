"""inference_cat_organ.py — Ana giris noktasi (I/O only).

Tum mantik lib/ altinda modüler. Bu dosya sadece:
1. CLI args parse et
2. lib.pipeline.estimate_organs_pnp + lib.render.draw_overlay cagir
3. JSON + overlay'leri kaydet, ozet bas

# ============================================================================
# KULLANIM
# ============================================================================

## 1. En basit kullanim (QR olmadan, canonical default)
   python inference_cat_organ.py --image kedi.jpg

   -> results/<image_stem>/organs.json
   -> results/<image_stem>/tr/01..07.jpg  (Turkce overlay)
   -> results/<image_stem>/en/01..07.jpg  (Ingilizce overlay)

## 2. ArUco marker (kabinin arka duvarinda) + kabin koord sistemi
   python inference_cat_organ.py \
       --image kedi_kabin.jpg \
       --qr-to-cabin-origin "0,50,0" \
       --aruco-real-cm 10.0

   -> Her organa "coord_cabin_cm" alani eklenir
   -> Kabin orijini = QR merkezi + (X,Y,Z) offset (cm)

## 3. EM hipertermi modeline veri besleme (tek organ hedefli)
   python inference_cat_organ.py \
       --image kedi.jpg \
       --to-em --em-organ 2

   -> em-organ secenekleri:
      1=mide, 2=bobrek, 3=karaciger, 4=mesane, 5=pankreas,
      6=bagirsak, 7=kalp, 8=dalak, 9=akciger_sag, 10=akciger_sol

## 4. Tam komut (klinik kullanim, kabin + EM)
   python inference_cat_organ.py \
       --image kedi.jpg \
       --qr-to-cabin-origin "0,50,30" \
       --cabin-extent-cm "60,40,80" \
       --aruco-real-cm 10.0 \
       --aruco-dict DICT_5X5_50 \
       --to-em --em-organ 2 \
       --achieved-b 0.001 --duty-sum 2.0

## 5. CPU'da calistir (GPU yoksa)
   python inference_cat_organ.py --image kedi.jpg --device cpu

## 6. Ozel cikti yolu
   python inference_cat_organ.py --image kedi.jpg \
       --output /tmp/my_result.json

# ============================================================================
# CIKTI SEMASI (organs.json, v2.1)
# ============================================================================

{
  "schema_version": "v2.1",
  "image": "...", "image_name": "kedi.jpg",
  "bbox": [x1, y1, x2, y2],
  "pose_classifier": {"type": "sphinx", "confidence": 0.85},
  "anatomic_consistency": {"passed": true, "score": 1.0, ...},
  "organs": {
    "1": {"name": "mide",      "pixel_xy": [..], "coord_3d_cm": [+3.0,-1.5,-3.5],
            "coord_cabin_cm": [.., .., ..],    # QR varsa
            "reliability": 0.85},
    "2": {"name": "bobrek",    "pixel_xy": [..], "coord_3d_cm": [-2.0,+2.5,+3.0], ...},
    ...
    "10": {"name": "akciger_sol", ...},
  },
  "pnp_fit": {"yaw_deg": .., "pitch_deg": .., "residual_px": .., ...},
  "morphology": {"sx": 1.0, "sy": 1.0, "sz": 1.0, "bcs": 0.0,
                       "method": ["canonical-default"] veya ["QR-canonical"]}
}

# ============================================================================
# ARUCO MARKER HAZIRLIGI (bir kerelik)
# ============================================================================

1. Klasorde hazir: aruco_marker_id0.png  (DICT_5X5_50, id=0)
2. A4 sayfaya tam 10x10 cm boyutta print et
3. Kabinin arka duvarinin sabit yerine yapistir
4. Fiziksel marker boyutu --aruco-real-cm degeriyle uyumlu olsun

# ============================================================================
# KABIN KOORD KONFIGURASYONU (bir kerelik kalibrasyon)
# ============================================================================

Sen marker'i kabine yapistirdiktan sonra:
  - QR merkezinin kabin (0,0,0) noktasina gore ofsetini olc (X,Y,Z cm)
  - Kabin boyutu (genislik, yukseklik, derinlik) cm
  - Bu degerleri --qr-to-cabin-origin ve --cabin-extent-cm ile gir

# ============================================================================
# CIKTI DOSYALARI
# ============================================================================

results/<image_stem>/
├── organs.json                  # Full schema (10 organ + meta)
├── tr/                          # Turkce overlay'ler
│   ├── 01_segmentation.jpg      # YOLO seg sonucu
│   ├── 02_keypoints.jpg         # DLC 39 keypoint + skeleton
│   ├── 03_pnp_3d_mesh.jpg       # 3D mesh fit overlay
│   ├── 04_organs.jpg            # 10 organ pixel pozisyonu
│   ├── 05_deskewed_canonical.jpg # Kediye-spesifik canonical view
│   ├── 06_3d_view.jpg           # 3D yan gorus
│   └── 07_summary.jpg           # 2x2 grid ozet
└── en/                          # Ingilizce overlay'ler (ayni 7 dosya)

# ============================================================================
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np

# Modüler library
from lib.canonical import KEYPOINT_NAMES, ORGAN_IDS, CANONICAL_ORGANS_3D
from lib.pipeline import estimate_organs_pnp
from lib.runners import run_yolo_segmentation, run_pose, _kp_dict
from lib.pose import classify_pose
from lib.validation import anatomic_consistency_check
from lib.render import (
    draw_overlay, render_segmentation, render_keypoints, render_pnp_3d_mesh,
    render_organs_classic, render_deskewed_with_organs, render_3d_view_standalone,
)


def _json_default(o):
    if isinstance(o, np.floating):
        return float(o)
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    raise TypeError(f"Type {type(o)} not serializable")


def main():
    parser = argparse.ArgumentParser(
        description="Kedi organ 3D koordinati (YOLOseg + DLC + canonical atlas + ArUco)")
    parser.add_argument("--image", type=str, required=True)
    parser.add_argument("--output", type=str, default=None,
                          help="JSON cikis (default: results/<name>/organs.json)")
    parser.add_argument("--device", type=str, default=None,
                          help="0/cuda/cpu. Default: GPU varsa 0, yoksa cpu.")
    parser.add_argument("--no-segment", action="store_true")
    parser.add_argument("--to-em", action="store_true",
                          help="EM modele besle + coil ayarlari yazdir")
    parser.add_argument("--em-organ", type=int, default=2,
                          choices=list(ORGAN_IDS),
                          help=f"default=2 (bobrek). {ORGAN_IDS}")
    parser.add_argument("--achieved-b", type=float, default=0.001)
    parser.add_argument("--duty-sum", type=float, default=2.0)

    # Kabin koordinat sistemi (QR merkezi -> kabin origin)
    parser.add_argument("--qr-to-cabin-origin", type=str, default="0,0,0",
                              metavar="X,Y,Z",
                              help="QR merkezi -> kabin origin offset (cm)")
    parser.add_argument("--cabin-axes", type=str,
                              default="x=right,y=down,z=depth",
                              metavar="DEF", help="Kabin eksen tanimi")
    parser.add_argument("--cabin-extent-cm", type=str, default="0,0,0",
                              metavar="W,H,D",
                              help="Kabin boyutu cm (W,H,D)")
    parser.add_argument("--aruco-real-cm", type=float, default=10.0,
                              help="ArUco marker fiziksel kenar (cm)")
    parser.add_argument("--aruco-dict", type=str, default="DICT_5X5_50",
                              help="ArUco dictionary")

    # Level 3: cabin yaml config + opsiyonel kamera mesafeleri
    parser.add_argument("--cabin-config", type=str, default=None,
                              metavar="YAML",
                              help="Kabin YAML config dosyasi (Level 3 perspective)")
    parser.add_argument("--camera-to-marker-cm", type=float, default=None,
                              help="Kamera lens -> ArUco merkez mesafesi (cm)")
    parser.add_argument("--camera-to-origin-cm", type=float, default=None,
                              help="Kamera lens -> kabin origin mesafesi (cm)")
    parser.add_argument("--camera-intrinsics-npz", type=str, default=None,
                              help="Calibrate camera .npz dosyasi (K, D)")
    args = parser.parse_args()

    # Cabin parse
    try:
        args.qr_to_cabin_origin = [float(v) for v in
                                              args.qr_to_cabin_origin.split(",")]
        if len(args.qr_to_cabin_origin) != 3:
            raise ValueError
    except ValueError:
        args.qr_to_cabin_origin = [0.0, 0.0, 0.0]
    try:
        args.cabin_extent_cm = [float(v) for v in args.cabin_extent_cm.split(",")]
        if len(args.cabin_extent_cm) != 3:
            raise ValueError
    except ValueError:
        args.cabin_extent_cm = [0.0, 0.0, 0.0]

    # ArUco runtime overrides (qr.py module-level constants)
    import lib.qr as _qr
    _qr.ARUCO_REAL_CM = args.aruco_real_cm
    _qr.ARUCO_DICT = args.aruco_dict

    # Level 3: Cabin YAML config (varsa) + CLI override
    from lib.cabin_config import (load_cabin_config, apply_cli_overrides,
                                              has_perspective_data, summary as cabin_summary)
    try:
        cabin_cfg = load_cabin_config(args.cabin_config)
        cabin_cfg = apply_cli_overrides(cabin_cfg, args)
        # Aruco runtime const'larini yaml'dan da uygula
        _qr.ARUCO_REAL_CM = cabin_cfg["aruco"]["real_cm"]
        _qr.ARUCO_DICT = cabin_cfg["aruco"]["dict"]
        if has_perspective_data(cabin_cfg):
            print(f"Cabin: [perspective] {cabin_summary(cabin_cfg)}")
        elif args.cabin_config:
            print(f"Cabin: [weak-persp] {cabin_summary(cabin_cfg)}")
    except FileNotFoundError as e:
        print(f"HATA: {e}"); sys.exit(1)

    # Device auto-detect
    if args.device is None:
        try:
            import torch
            args.device = "cuda" if torch.cuda.is_available() else "cpu"
        except ImportError:
            args.device = "cpu"
    print(f"Device: {args.device}")

    img_path = Path(args.image).resolve()
    if not img_path.exists():
        print(f"HATA: {img_path} yok"); sys.exit(1)
    stem = img_path.stem

    out_root = Path(__file__).resolve().parent / "results" / stem
    out_root.mkdir(parents=True, exist_ok=True)
    out_json = Path(args.output) if args.output else out_root / "organs.json"

    # 1. Segmentasyon
    print(f"[1/3] Segmentasyon  {img_path.name}")
    seg = run_yolo_segmentation(str(img_path), device=args.device)
    if "error" in seg:
        print(f"  {seg['error']}"); sys.exit(2)
    bbox = np.array(seg["bbox"])
    print(f"  bbox={seg['bbox']} conf={seg['conf']:.2f}")

    # 2. DLC pose
    print("[2/3] DLC pose")
    pose = run_pose(str(img_path), device=args.device,
                       out_dir=out_root / "dlc")
    if "error" in pose:
        print(f"  {pose['error']}"); sys.exit(3)
    kp = pose["keypoints"]
    kp_d = _kp_dict(kp)
    print(f"  {len(kp_d)}/39 keypoint (>=0.3 conf)")

    # 3. Pose classifier + organ atlas
    print("[3/3] Pose classifier + atlas")
    pose_info = classify_pose(kp_d, seg.get("mask_xy"), bbox)
    print(f"  Pose: {pose_info['type']}  conf={pose_info['confidence']:.2f}")
    for note in pose_info.get("notes", []):
        print(f"    - {note}")

    # Cabin params (legacy CLI + Level 3 yaml)
    cabin_params = {
        "qr_to_origin_cm": args.qr_to_cabin_origin,
        "axes_def": args.cabin_axes,
        "extent_cm": args.cabin_extent_cm,
        "config": cabin_cfg,
    }
    kp_conf = kp[:, 2]
    organs = estimate_organs_pnp(kp_d, kp_conf, bbox, pose_info,
                                          mask_xy=seg.get("mask_xy"),
                                          image_path=str(img_path),
                                          cabin_params=cabin_params)
    if "error" in organs:
        print(f"  PnP fail: {organs['error']}"); sys.exit(4)

    pnp = organs["pnp_fit"]
    print(f"  PnP fit: yaw={pnp['yaw_deg']:+.0f}° "
          f"pitch={pnp['pitch_deg']:+.0f}° roll={pnp['roll_deg']:+.0f}°  "
          f"err={pnp['residual_px']:.1f}px  n_kp={pnp['n_keypoints_used']} "
          f"inliers={pnp.get('n_inliers')} "
          f"iters={pnp.get('robust_iterations', 0)} "
          f"occluded={pnp.get('n_occluded_kp', 0)}")
    persp = pnp.get("perspective")
    if persp and persp.get("enabled"):
        cpos = persp["cat_position_in_cabin_cm"]
        print(f"  Perspective [{persp['intrinsics_source']}]: "
              f"f={persp['f_px']:.0f}px  "
              f"marker_depth={persp['marker_depth_cm']:.1f}cm  "
              f"cat_pnp_err={persp['cat_pnp_residual_px']:.1f}px "
              f"({persp['cat_pnp_inliers']}/{persp['cat_pnp_n_used']} inl)")
        print(f"  Cat in cabin: pos=({cpos[0]:+.1f},{cpos[1]:+.1f},{cpos[2]:+.1f})cm "
              f"yaw={persp['cat_cabin_yaw_deg']:+.0f}° "
              f"pitch={persp['cat_cabin_pitch_deg']:+.0f}° "
              f"roll={persp['cat_cabin_roll_deg']:+.0f}°")
    morph = organs.get("morphology")
    if morph:
        print(f"  Morphology (L1+L2): {morph['summary']}")
        if morph.get("method"):
            print(f"    measures: {', '.join(morph['method'])}")

    # Anatomic check
    try:
        organs_d = organs.get("organs") or {}
        anatomic = anatomic_consistency_check(
            organs_d, morph=organs.get("morphology"), strict=False)
        if not anatomic["passed"] or anatomic["violations"]:
            print(f"  Anatomic check: score={anatomic['score']:.2f} "
                  f"({anatomic['n_organs_passed']}/{anatomic['n_organs_checked']})")
            for oid, name, code, msg in anatomic["violations"][:3]:
                print(f"    ! [{oid}] {name}: {code}")
        else:
            print(f"  Anatomic check: PASSED "
                  f"({anatomic['n_organs_passed']}/{anatomic['n_organs_checked']})")
    except Exception as e:
        anatomic = {"passed": None, "error": str(e)}
        print(f"  Anatomic check failed: {e}")

    # Build full result dict (v2 schema)
    result = {
        "schema_version": "v2.1",
        "image": str(img_path),
        "image_name": img_path.name,
        "bbox": [float(v) for v in seg["bbox"]],
        "segmentation": {"n_detections": seg.get("n_detections"),
                              "mask_xy": seg.get("mask_xy")},
        "pose": {n: [round(float(kp[i, 0]), 2),
                            round(float(kp[i, 1]), 2),
                            round(float(kp[i, 2]), 4)]
                    for i, n in enumerate(KEYPOINT_NAMES)},
        "pose_classifier": pose_info,
        "method": "Procrustes+QR-canonical",
        "morphology_method": morph.get("method") if morph else None,
        "organ_atlas_source": "canonical_atlas_v2",
        "anatomic_consistency": anatomic,
        "organs": organs.get("organs"),
        "axis": organs.get("axis"),
        "pnp_fit": organs.get("pnp_fit"),
        "R_matrix": organs.get("R_matrix"),
        "t_vec": organs.get("t_vec"),
        "fitted_keypoints_2d": organs.get("fitted_keypoints_2d"),
        "morphology": morph,
    }

    with open(out_json, "w") as f:
        json.dump(result, f, indent=2, default=_json_default,
                     ensure_ascii=False)
    print(f"  JSON: {out_json}")

    # Render overlay'ler (TR + EN) — 7 dosya per dil
    target_oid = args.em_organ if args.to_em else None
    try:
        import cv2
        for lang in ("tr", "en"):
            lang_dir = out_root / lang
            lang_dir.mkdir(exist_ok=True)
            renders = [
                ("01_segmentation.jpg",
                 lambda l=lang: render_segmentation(str(img_path), result, lang=l)),
                ("02_keypoints.jpg",
                 lambda l=lang: render_keypoints(str(img_path), result, lang=l)),
                ("03_pnp_3d_mesh.jpg",
                 lambda l=lang: render_pnp_3d_mesh(str(img_path), result, lang=l)),
                ("04_organs.jpg",
                 lambda l=lang: render_organs_classic(str(img_path), result,
                                                            target_oid, lang=l)),
                ("05_deskewed_canonical.jpg",
                 lambda l=lang: render_deskewed_with_organs(str(img_path), result,
                                                                  target_oid,
                                                                  target_h_px=900,
                                                                  lang=l)),
                ("06_3d_view.jpg",
                 lambda l=lang: render_3d_view_standalone(result, 900, 900,
                                                                image_path=str(img_path),
                                                                target_oid=target_oid,
                                                                lang=l)),
                ("07_summary.jpg",
                 lambda l=lang, ld=lang_dir: (draw_overlay(str(img_path), result,
                                                                       str(ld / "07_summary.jpg"),
                                                                       target_oid=target_oid,
                                                                       lang=l)) or None),
            ]
            for fname, fn in renders:
                try:
                    out = fn()
                    if fname == "07_summary.jpg":
                        continue                              # draw_overlay yazdi
                    if out is None:
                        continue
                    cv2.imwrite(str(lang_dir / fname), out)
                except Exception as e:
                    print(f"  ! [{lang}] {fname} render hatasi: {e}")
            print(f"  Overlays [{lang}]: {lang_dir}/  (01..07)")
    except ImportError:
        print("  ! cv2 yok, overlay atlandi")

    # Ozet
    print(f"\n7 organ centroid:")
    for oid, info in sorted((organs.get("organs") or {}).items(),
                                       key=lambda kv: int(kv[0])):
        c = info.get("coord_3d_cm") or [0, 0, 0]
        p = info.get("pixel_xy") or [0, 0]
        rel = info.get("reliability", 0)
        print(f"  [{oid}] {info.get('name', '?'):12s}  "
              f"3D=({c[0]:+5.1f},{c[1]:+5.1f},{c[2]:+5.1f})cm  "
              f"px=({int(p[0]):6d},{int(p[1]):6d})  reliability={rel}")


if __name__ == "__main__":
    main()
