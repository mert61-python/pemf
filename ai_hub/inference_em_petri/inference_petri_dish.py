#!/usr/bin/env python3
"""
inference_petri_dish.py — Petri Dish Segmentasyonu (YOLO11m-seg)
================================================================
Goruntudeki petri kaplarini tespit edip segmente eder.

Kullanim:
  # Tek goruntu
  python inference_petri_dish.py --image petri.jpg

  # Klasor
  python inference_petri_dish.py --source images_folder/ --save

  # Interaktif
  python inference_petri_dish.py
"""

import os
import sys
import argparse

_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(_DIR, "yolo11m-seg.pt")


def main():
    parser = argparse.ArgumentParser(
        description="Petri Dish Segmentasyonu — YOLO11m-seg (mAP50-95=0.961)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ornekler:
  python inference_petri_dish.py --image petri.jpg
  python inference_petri_dish.py --image petri.jpg --conf 0.5 --save
  python inference_petri_dish.py --source images_folder/ --save
""")
    parser.add_argument("--image", type=str, help="Tek goruntu yolu")
    parser.add_argument("--source", type=str, help="Kaynak: klasor, video, webcam (0)")
    parser.add_argument("--conf", type=float, default=0.25, help="Confidence threshold")
    parser.add_argument("--iou", type=float, default=0.7, help="IoU threshold")
    parser.add_argument("--imgsz", type=int, default=640, help="Goruntu boyutu")
    parser.add_argument("--device", type=str, default="0", help="Device: 0, cpu")
    parser.add_argument("--save", action="store_true", help="Sonuclari kaydet")
    parser.add_argument("--show", action="store_true", help="Sonuclari goster")
    parser.add_argument("--save-txt", action="store_true", help="Label txt kaydet")
    parser.add_argument("--save-crop", action="store_true", help="Crop'lari kaydet")
    parser.add_argument("--output", type=str, default="results", help="Cikti klasoru")

    args = parser.parse_args()

    from ultralytics import YOLO

    print("=" * 60)
    print("Petri Dish Segmentasyonu — YOLO11m-seg")
    print(f"Model: {MODEL_PATH}")
    print(f"mAP50: 0.984 | mAP50-95: 0.961 | 22.3M params")
    print("=" * 60)

    model = YOLO(MODEL_PATH)
    source = args.image or args.source

    if source is None:
        # Interaktif mod
        print("\nInteraktif mod (cikmak icin 'q')")
        print("-" * 60)
        while True:
            try:
                path = input("\nGoruntu yolu: ").strip()
                if path.lower() in ('q', 'quit', 'exit', ''):
                    break
                if not os.path.exists(path):
                    print(f"  Dosya bulunamadi: {path}")
                    continue

                results = model.predict(
                    source=path,
                    conf=args.conf,
                    iou=args.iou,
                    imgsz=args.imgsz,
                    device=args.device,
                    save=True,
                    project=_DIR,
                    name=args.output,
                    exist_ok=True,
                )

                for r in results:
                    n = len(r.boxes) if r.boxes is not None else 0
                    print(f"\n  Tespit: {n} petri dish")
                    if r.boxes is not None:
                        for i, box in enumerate(r.boxes):
                            conf = float(box.conf[0])
                            x1, y1, x2, y2 = box.xyxy[0].tolist()
                            print(f"    Petri {i+1}: conf={conf:.2f} bbox=[{x1:.0f},{y1:.0f},{x2:.0f},{y2:.0f}]")
                    print(f"  Kaydedildi: {_DIR}/{args.output}/")

            except KeyboardInterrupt:
                print("\n  Cikis.")
                break
            except Exception as e:
                print(f"  Hata: {e}")
    else:
        print(f"\nKaynak: {source}")
        results = model.predict(
            source=source,
            conf=args.conf,
            iou=args.iou,
            imgsz=args.imgsz,
            device=args.device,
            save=args.save,
            save_txt=args.save_txt,
            save_crop=args.save_crop,
            show=args.show,
            project=_DIR,
            name=args.output,
            exist_ok=True,
        )

        total = sum(len(r.boxes) for r in results if r.boxes is not None)
        print(f"\nSonuc: {len(results)} goruntu, {total} petri dish tespit edildi")
        if args.save:
            print(f"Kaydedildi: {_DIR}/{args.output}/")


if __name__ == "__main__":
    main()
