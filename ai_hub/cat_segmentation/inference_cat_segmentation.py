#!/usr/bin/env python3
# Author: mertaygn, cglrgrkn
"""
inference_cat_segmentation.py — Kedi Segmentasyonu (YOLOv8m-seg)
================================================================
Goruntudeki kedileri tespit edip segmente eder.

Kullanim:
  # Tek goruntu
  python inference_cat_segmentation.py --image kedi.jpg

  # Klasor
  python inference_cat_segmentation.py --source images_folder/

  # Webcam
  python inference_cat_segmentation.py --source 0

  # Ayarlar
  python inference_cat_segmentation.py --image kedi.jpg --conf 0.5 --save --show
"""

import os
import sys
import argparse
import numpy as np

_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(_DIR, "yolov8m-seg.pt")


def main():
    parser = argparse.ArgumentParser(
        description="Kedi Segmentasyonu — YOLOv8m-seg (mAP50=0.872)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ornekler:
  python inference_cat_segmentation.py --image kedi.jpg
  python inference_cat_segmentation.py --image kedi.jpg --conf 0.5 --save
  python inference_cat_segmentation.py --source images_folder/ --save
  python inference_cat_segmentation.py --source 0  # webcam
""")
    parser.add_argument("--image", type=str, help="Tek goruntu yolu")
    parser.add_argument("--source", type=str, help="Kaynak: klasor, video, webcam (0)")
    parser.add_argument("--conf", type=float, default=0.5, help="Confidence threshold (default: 0.5)")
    parser.add_argument("--iou", type=float, default=0.5, help="IoU threshold (default: 0.5)")
    parser.add_argument("--imgsz", type=int, default=640, help="Goruntu boyutu (default: 640)")
    parser.add_argument("--device", type=str, default="0", help="Device: 0, cpu")
    parser.add_argument("--save", action="store_true", help="Sonuclari kaydet")
    parser.add_argument("--show", action="store_true", help="Sonuclari goster")
    parser.add_argument("--save-txt", action="store_true", help="Label txt kaydet")
    parser.add_argument("--save-crop", action="store_true", help="Crop'lari kaydet")
    parser.add_argument("--output", type=str, default="results", help="Cikti klasoru")

    args = parser.parse_args()

    from ultralytics import YOLO

    print("=" * 60)
    print("Kedi Segmentasyonu — YOLOv8m-seg")
    print(f"Model: {MODEL_PATH}")
    print(f"mAP50: 0.872 | mAP50-95: 0.671 | 27.2M params")
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
                    n_cats = len(r.boxes) if r.boxes is not None else 0
                    print(f"\n  Tespit: {n_cats} kedi")
                    if r.boxes is not None:
                        for i, box in enumerate(r.boxes):
                            conf = float(box.conf[0])
                            x1, y1, x2, y2 = box.xyxy[0].tolist()
                            w, h = x2 - x1, y2 - y1
                            print(f"    Kedi {i+1}: conf={conf:.2f} bbox=[{x1:.0f},{y1:.0f},{x2:.0f},{y2:.0f}] size={w:.0f}x{h:.0f}")
                    if r.masks is not None:
                        print(f"  Mask: {r.masks.data.shape[0]} segment")
                    print(f"  Kaydedildi: {_DIR}/{args.output}/")

            except KeyboardInterrupt:
                print("\n  Cikis.")
                break
            except Exception as e:
                print(f"  Hata: {e}")
    else:
        # Direkt tahmin
        print(f"\nKaynak: {source}")
        print(f"Conf: {args.conf} | IoU: {args.iou} | Imgsz: {args.imgsz}")

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

        total_cats = 0
        for r in results:
            n = len(r.boxes) if r.boxes is not None else 0
            total_cats += n

        print(f"\nSonuc: {len(results)} goruntu islendi, toplam {total_cats} kedi tespit edildi")
        if args.save:
            print(f"Kaydedildi: {_DIR}/{args.output}/")


if __name__ == "__main__":
    main()
