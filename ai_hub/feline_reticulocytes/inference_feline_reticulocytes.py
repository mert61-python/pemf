#!/usr/bin/env python3
# Author: mertaygn, cglrgrkn
"""
inference_feline_reticulocytes.py — Kan Hucresi Tespiti (YOLOv8s)
================================================================
3 sinif: erythrocyte, punctate reticulocyte, aggregate reticulocyte

Kullanim:
  python inference_feline_reticulocytes.py --image kan_ornek.jpg --save
  python inference_feline_reticulocytes.py --source images/ --save
  python inference_feline_reticulocytes.py  # interaktif mod
"""

import os
import sys
import argparse

_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(_DIR, "yolov8s.pt")

CLASS_NAMES = ["erythrocyte", "punctate reticulocyte", "aggregate reticulocyte"]


# ============================================================
# XAI — EigenCAM isi haritasi (Faz 2 kuyrugu, 2026-08-26)
# ============================================================
# EigenCAM label-agnostik PCA — GRADIENT'SIZ (YOLO'da Grad-CAM gurultulu, doc §10.1).
# ⚠️ grad-cam hook'lari + paylasilan model thread-safe DEGIL → TEK-IS kilidi; XAI kendi
# PT-YOLO instance'ini cache'ler (canli ONNX tespit yoluna dokunmaz); bellek-ici base64.
import threading as _xai_threading

_XAI_KILIT = _xai_threading.Lock()
_XAI_PT_CACHE: dict = {}


def xai_retikulosit_isi_haritasi(image_path: str, pt_path: str | None = None,
                                   alpha: float = 0.5) -> dict:
    """Kan yaymasi goruntusu icin EigenCAM — modelin tespitte dayandigi hucre bolgeleri.

    TEK-KAYNAK: router in-process + ai_service ayni fonksiyonu cagirir (kapi-paritesi).
    Doner: {"xai_image_base64": <jpg b64 overlay>, "method": "eigencam"}
    """
    import base64 as _b64

    import cv2

    from ai_hub.xai_utils.overlay import blend_to_array
    from ai_hub.xai_utils.yolo_cam import YoloEigenCAM

    if pt_path is None:
        from utils.model_downloader import download_model_sync

        pt_path = download_model_sync("ai_hub/feline_reticulocytes/yolov8s.pt")

    with _XAI_KILIT:
        expl = _XAI_PT_CACHE.get("retic")
        if expl is None:
            from ultralytics import YOLO

            expl = YoloEigenCAM(YOLO(str(pt_path)), layer_idx=-2, imgsz=640, device="cpu")
            _XAI_PT_CACHE["retic"] = expl
        heatmap = expl.explain(image_path)  # (H, W) 0-1, orijinal cozunurluk

    bgr = cv2.imread(str(image_path))
    if bgr is None:
        raise RuntimeError(f"XAI icin goruntu okunamadi: {image_path}")
    overlay = blend_to_array(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB), heatmap, alpha=alpha)
    ok, buf = cv2.imencode(".jpg", cv2.cvtColor(overlay, cv2.COLOR_RGB2BGR),
                            [cv2.IMWRITE_JPEG_QUALITY, 85])
    if not ok:
        raise RuntimeError("XAI overlay JPG encode basarisiz")
    return {"xai_image_base64": _b64.b64encode(buf.tobytes()).decode("ascii"), "method": "eigencam"}


def main():
    parser = argparse.ArgumentParser(
        description="Feline Reticulocytes Detection — YOLOv8s (mAP50=0.943)")
    parser.add_argument("--image", type=str, help="Tek goruntu yolu")
    parser.add_argument("--source", type=str, help="Kaynak: klasor, video, webcam (0)")
    parser.add_argument("--conf", type=float, default=0.25, help="Confidence threshold")
    parser.add_argument("--iou", type=float, default=0.7, help="IoU threshold")
    parser.add_argument("--imgsz", type=int, default=640, help="Goruntu boyutu")
    parser.add_argument("--device", type=str, default="0", help="Device: 0, cpu")
    parser.add_argument("--save", action="store_true", help="Sonuclari kaydet")
    parser.add_argument("--show", action="store_true", help="Sonuclari goster")
    parser.add_argument("--output", type=str, default="results", help="Cikti klasoru")
    args = parser.parse_args()

    from ultralytics import YOLO

    print("=" * 60)
    print("Feline Reticulocytes Detection — YOLOv8s")
    print("3 sinif: erythrocyte | punctate ret. | aggregate ret.")
    print(f"mAP50: 0.943 | mAP50-95: 0.848 | 11.1M params")
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
                    source=path, conf=args.conf, iou=args.iou,
                    imgsz=args.imgsz, device=args.device,
                    save=True, project=_DIR, name=args.output, exist_ok=True,
                )

                for r in results:
                    if r.boxes is not None:
                        counts = {c: 0 for c in CLASS_NAMES}
                        for box in r.boxes:
                            cls_id = int(box.cls[0])
                            conf = float(box.conf[0])
                            counts[CLASS_NAMES[cls_id]] += 1
                        print(f"\n  Tespit ({sum(counts.values())} hucre):")
                        for name, cnt in counts.items():
                            if cnt > 0:
                                print(f"    {name:30s} {cnt}")
                    print(f"  Kaydedildi: {_DIR}/{args.output}/")

            except KeyboardInterrupt:
                print("\n  Cikis.")
                break
            except Exception as e:
                print(f"  Hata: {e}")
    else:
        # Direkt tahmin
        print(f"\nKaynak: {source}")
        results = model.predict(
            source=source, conf=args.conf, iou=args.iou,
            imgsz=args.imgsz, device=args.device,
            save=args.save, show=args.show,
            project=_DIR, name=args.output, exist_ok=True,
        )

        total_counts = {c: 0 for c in CLASS_NAMES}
        for r in results:
            if r.boxes is not None:
                for box in r.boxes:
                    cls_id = int(box.cls[0])
                    total_counts[CLASS_NAMES[cls_id]] += 1

        print(f"\nSonuc: {len(results)} goruntu islendi")
        for name, cnt in total_counts.items():
            print(f"  {name:30s} {cnt}")
        if args.save:
            print(f"Kaydedildi: {_DIR}/{args.output}/")


if __name__ == "__main__":
    main()
