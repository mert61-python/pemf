# Author: mertaygn, cglrgrkn
"""cli.py — Komut satiri arabirimi (kedi inference_cat_organ tarzi).

Kullanim:
  # Tek goruntu (ArUco yoksa Hough fallback):
  python -m phantom_cv.cli \
      --config phantom_cv/cabin_config.yaml \
      --image test_img/foto.jpg \
      --out results

  # Canli kamera tek frame:
  python -m phantom_cv.cli --config ... --camera 0 --out results

  # MQTT publish:
  python -m phantom_cv.cli --config ... --image test.jpg --mqtt

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

from .pipeline import PhantomCvPipeline
from .mqtt_publish import publish_result


def _summary_line(label: str, value: str, width: int = 22) -> str:
    return f"  {label:<{width}}: {value}"


def main():
    p = argparse.ArgumentParser(
        prog="phantom_cv",
        description="Sentetik bobrek fantom CV — tumor tespit + cabin koord",
    )
    p.add_argument("--config", "-c", default=None,
                   help="YAML config (default: cabin_config_example.yaml)")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--image", "-i", help="Tek goruntu (.jpg/.png)")
    g.add_argument("--camera", type=int, metavar="IDX",
                   help="/dev/video<IDX> canli kamera (tek frame yakala)")
    g.add_argument("--batch", help="Klasor — icindeki tum .jpg/.png isle")
    p.add_argument("--out", "-o", default="results",
                   help="Cikti kok klasoru (default: results)")
    p.add_argument("--lang", default="both", choices=["tr", "en", "both"],
                   help="Overlay dil(ler)i")
    p.add_argument("--achieved-B", type=float, default=None)
    p.add_argument("--duty-sum", type=float, default=None)
    p.add_argument("--phantom-length-cm", type=float, default=None,
                   help="Silikon bobrek fantom uzun kenari (cm). "
                        "Verilirse mm/px kalibrasyon icin kullanilir "
                        "(tipik insan bobregi ~10-12 cm).")
    p.add_argument("--no-manual", action="store_true",
                   help="HSV basarisiz olursa manuel tikla fallback'i kapat.")
    p.add_argument("--mqtt", action="store_true")
    p.add_argument("--quiet", "-q", action="store_true")
    args = p.parse_args()

    pipeline = PhantomCvPipeline(args.config,
                                 phantom_length_cm=args.phantom_length_cm,
                                 manual_fallback=not args.no_manual)
    print(f"[CABIN  ] {pipeline.cfg.summary()}")
    print(f"[PHANTOM] length = {args.phantom_length_cm} cm (None=piksel mod)")
    print(f"[MANUAL ] fallback = {'ON' if not args.no_manual else 'OFF'}")

    # Goruntu kaynagi
    image_paths: list[str] = []
    captured_img = None
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
        print(f"[BATCH] {len(image_paths)} goruntu islenecek")
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
        # Geçici dosya — write_results stem'i kullaniyor
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

        # JSON yaz
        import json as _json
        with open(out_dir / "result.json", "w", encoding="utf-8") as fh:
            _json.dump(result.to_dict(), fh, indent=2, default=str,
                       ensure_ascii=False)

        # Paneller
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
            print(_summary_line("n_tumor",       str(result.n_tumor)))
            print(_summary_line("n_healthy",     str(result.n_healthy)))
            if result.phantom_detection:
                pd = result.phantom_detection
                cx, cy = pd["centroid_px"]
                print(_summary_line("phantom_center_px",
                      f"({cx:.0f}, {cy:.0f})"))
                print(_summary_line("phantom_area_px",
                      str(pd["area_px"])))
                print(_summary_line("phantom_solidity",
                      f"{pd['solidity']:.3f}"))
                print(_summary_line("phantom_score",
                      f"{pd['score']:.2f}"))
                print(_summary_line("mm_per_px",
                      f"{result.mm_per_px:.4f}"))
            if result.cabin_pose:
                print(_summary_line("marker_id",
                      str(result.cabin_pose.get("marker_id"))))
            print(_summary_line("total_ms",
                  f"{result.timing_ms.get('total', 0):.1f}"))
            for r in result.tumor_regions[:5]:
                x, y, z = r.centroid_cabin_mm
                print(f"    TUMOR  ({x:+6.1f}, {y:+6.1f}, {z:+5.1f})mm  "
                      f"E_c={r.E_cancer:.4f}  area={r.area_px}")
            print(f"  -> {out_dir}/")

        summary_rows.append({
            "image": Path(img_path).name,
            "success": result.success,
            "method": result.method,
            "n_tumor": result.n_tumor,
            "n_healthy": result.n_healthy,
            "total_ms": result.timing_ms.get("total", 0),
        })

        if args.mqtt or pipeline.cfg.output.mqtt_enabled:
            publish_result(pipeline.cfg.output, result.to_dict(),
                           quiet=args.quiet)

    # Batch ozet
    if len(image_paths) > 1 and not args.quiet:
        print("\n=== BATCH OZET ===")
        print(f"  Toplam: {len(image_paths)}, "
              f"basarili: {sum(1 for r in summary_rows if r['success'])}")
        for r in summary_rows:
            mark = "OK" if r["success"] else "!!"
            print(f"  [{mark}] {r['image']:<50s} method={r['method']:<12s} "
                  f"T={r['n_tumor']} H={r['n_healthy']} "
                  f"{r['total_ms']:>6.1f}ms")


if __name__ == "__main__":
    main()
