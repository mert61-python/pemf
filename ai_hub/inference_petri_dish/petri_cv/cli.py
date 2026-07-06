"""cli.py — Petri CV komut satiri (kedi inference_cat_organ tarzi).

Kullanim:
  # Tek goruntu (YOLO + petri capi kalibrasyon):
  python -m petri_cv.cli \
      --config petri_cv/cabin_config.yaml \
      --image test_img/foto.jpg \
      --out results \
      --petri-diameter-cm 5.0

  # Klasor batch:
  python -m petri_cv.cli --config ... --batch test_img/ --out results \
      --petri-diameter-cm 5.0

  # Canli kamera tek frame:
  python -m petri_cv.cli --config ... --camera 0 --out results

  # MQTT publish:
  python -m petri_cv.cli --config ... --image test.jpg --mqtt

Cikti yapisi (kedi paterni):
  results/<image_stem>/
    ├── result.json
    ├── tr/01_input.jpg .. 07_combined.jpg
    └── en/01_input.jpg .. 07_combined.jpg
"""
from __future__ import annotations
import argparse
import sys
import time
from pathlib import Path

import cv2

from .pipeline import PetriCvPipeline
from .mqtt_publish import publish_result


def _summary_line(label: str, value: str, width: int = 22) -> str:
    return f"  {label:<{width}}: {value}"


def main():
    p = argparse.ArgumentParser(
        prog="petri_cv",
        description="Petri Kabi CV — YOLO11m-seg + ArUco kalibrasyon",
    )
    p.add_argument("--config", "-c", default=None,
                   help="YAML config (default: cabin_config_example.yaml)")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--image", "-i", help="Tek goruntu (.jpg/.png)")
    g.add_argument("--camera", type=int, metavar="IDX",
                   help="/dev/video<IDX> canli kamera (tek frame)")
    g.add_argument("--batch", help="Klasor — icindeki tum .jpg/.png isle")
    p.add_argument("--out", "-o", default="results",
                   help="Cikti kok klasoru (default: results)")
    p.add_argument("--lang", default="both", choices=["tr", "en", "both"],
                   help="Overlay dil(ler)i")
    p.add_argument("--achieved-B", type=float, default=None)
    p.add_argument("--duty-sum", type=float, default=None)
    p.add_argument("--petri-diameter-cm", type=float, default=None,
                   help="Petri kabi capi (cm). "
                        "Verilirse mm/px kalibrasyon icin kullanilir "
                        "(standart petri: 5/6/9/10 cm).")
    # YOLO params
    p.add_argument("--yolo-conf", type=float, default=0.25,
                   help="YOLO confidence esiki (default 0.25).")
    p.add_argument("--yolo-iou", type=float, default=0.7,
                   help="YOLO IoU esiki (default 0.7).")
    p.add_argument("--yolo-imgsz", type=int, default=640,
                   help="YOLO inference goruntu boyutu (default 640).")
    p.add_argument("--yolo-device", type=str, default="0",
                   help="YOLO device: '0', 'cpu' (default '0').")
    p.add_argument("--yolo-model", type=str, default=None,
                   help="YOLO model yolu "
                        "(default: ../yolo11m-seg.pt).")
    p.add_argument("--cancer-pixel-threshold", type=int, default=30,
                   help="Kuyucukta >=N mavi HSV piksel varsa kanser "
                        "(default 30).")
    p.add_argument("--mqtt", action="store_true")
    p.add_argument("--quiet", "-q", action="store_true")
    args = p.parse_args()

    pipeline = PetriCvPipeline(args.config,
                               petri_diameter_cm=args.petri_diameter_cm,
                               yolo_model_path=args.yolo_model,
                               yolo_conf=args.yolo_conf,
                               yolo_iou=args.yolo_iou,
                               yolo_imgsz=args.yolo_imgsz,
                               yolo_device=args.yolo_device,
                               cancer_pixel_threshold=args.cancer_pixel_threshold)
    print(f"[CABIN  ] {pipeline.cfg.summary()}")
    print(f"[PETRI  ] diameter = {args.petri_diameter_cm} cm "
          f"(None=piksel mod)")
    print(f"[YOLO   ] {pipeline.yolo.model_path.name} "
          f"conf={args.yolo_conf} imgsz={args.yolo_imgsz}")

    # Goruntu kaynagi
    image_paths: list[str] = []
    if args.image:
        image_paths = [args.image]
    elif args.batch:
        batch_dir = Path(args.batch)
        for ext in ("*.jpg", "*.jpeg", "*.png", "*.JPG", "*.JPEG", "*.PNG"):
            image_paths.extend(str(p) for p in batch_dir.glob(ext))
        image_paths.sort()
        if not image_paths:
            print(f"HATA: {batch_dir} icinde goruntu yok", file=sys.stderr)
            sys.exit(2)
        print(f"[BATCH ] {len(image_paths)} goruntu islenecek")
    else:    # camera
        cap = cv2.VideoCapture(args.camera)
        if not cap.isOpened():
            print(f"HATA: kamera {args.camera} acilmadi", file=sys.stderr)
            sys.exit(2)
        for _ in range(5):
            cap.read(); time.sleep(0.05)
        ok, captured_img = cap.read()
        cap.release()
        if not ok:
            print("HATA: kamera frame okumadi", file=sys.stderr)
            sys.exit(2)
        captured_path = Path(args.out) / "_camera_capture.jpg"
        captured_path.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(captured_path), captured_img)
        image_paths = [str(captured_path)]

    langs = ["tr", "en"] if args.lang == "both" else [args.lang]

    summary_rows = []
    for idx, img_path in enumerate(image_paths, 1):
        result, ctx = pipeline.process_file(
            img_path,
            achieved_B=args.achieved_B,
            duty_sum=args.duty_sum,
        )
        out_dir = Path(args.out) / Path(img_path).stem
        out_dir.mkdir(parents=True, exist_ok=True)

        import json as _json
        with open(out_dir / "result.json", "w", encoding="utf-8") as fh:
            _json.dump(result.to_dict(), fh, indent=2, default=str,
                       ensure_ascii=False)

        if result.success and ctx.get("img_und") is not None:
            for lang in langs:
                panels = pipeline.render_panels(ctx, result, lang=lang)
                from . import render as rd
                rd.save_all_panels(panels, out_dir / lang,
                                   fmt="jpg", quality=88)

        if not args.quiet:
            print(f"\n[{idx}/{len(image_paths)}] {Path(img_path).name}")
            print(_summary_line("success",       str(result.success)))
            print(_summary_line("method",        result.method or "-"))
            if result.error:
                print(_summary_line("error",     result.error))
            print(_summary_line("n_wells",       str(result.n_wells)))
            print(_summary_line("n_cancer",      str(result.n_cancer)))
            print(_summary_line("n_healthy",     str(result.n_healthy)))
            print(_summary_line("mm_per_px",
                  f"{result.mm_per_px:.4f}"))
            if result.cabin_pose:
                print(_summary_line("marker_id",
                      str(result.cabin_pose.get("marker_id"))))
            print(_summary_line("total_ms",
                  f"{result.timing_ms.get('total', 0):.1f}"))
            for w in result.wells[:10]:
                x, y, z = w.centroid_cabin_mm
                lbl = "C" if w.organ_id == 1 else "H"   # Cancer/Healthy
                print(f"    {w.well_id:<4s} [{lbl}] ({x:+6.1f}, {y:+6.1f}, "
                      f"{z:+5.1f})mm  conf={w.conf:.2f}  "
                      f"E_c={w.E_cancer:.4f}  area={w.area_px}px")
            if len(result.wells) > 10:
                print(f"    ... +{len(result.wells) - 10} more wells")
            print(f"  -> {out_dir}/")

        summary_rows.append({
            "image": Path(img_path).name,
            "success": result.success,
            "method": result.method,
            "n_wells": result.n_wells,
            "n_cancer": result.n_cancer,
            "n_healthy": result.n_healthy,
            "total_ms": result.timing_ms.get("total", 0),
        })

        if args.mqtt or pipeline.cfg.output.mqtt_enabled:
            publish_result(pipeline.cfg.output, result.to_dict(),
                           quiet=args.quiet)

    if len(image_paths) > 1 and not args.quiet:
        print("\n=== BATCH OZET ===")
        print(f"  Toplam: {len(image_paths)}, "
              f"basarili: {sum(1 for r in summary_rows if r['success'])}")
        for r in summary_rows:
            mark = "OK" if r["success"] else "!!"
            print(f"  [{mark}] {r['image']:<50s} method={r['method']:<14s} "
                  f"W={r['n_wells']} C={r['n_cancer']} H={r['n_healthy']} "
                  f"{r['total_ms']:>6.1f}ms")


if __name__ == "__main__":
    main()
