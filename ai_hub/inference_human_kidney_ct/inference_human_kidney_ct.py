#!/usr/bin/env python3
"""inference_human_kidney_ct.py — Human Kidney CT tespit (YOLOv8s).

Task: **Object detection** — 3 sinif
    id 0: Kidney Stone   (tas)
    id 1: Kidney         (bobrek dokusu)
    id 2: Kidney Cyst    (kist)

Best model: **yolov8s** (test setinde secildi)
    Val  mAP50    = 0.925
    Val  mAP50-95 = 0.574
    Val  Precision = 0.937
    Val  Recall    = 0.880
    Test mAP50    = 0.842
    Test Precision = 0.912
    Params = 11.1 M, ModelSize = 21.5 MB (PT), 43 MB (ONNX)
    Imgsz = 640, Inference = 3.2 ms (GPU)

Pipeline:
    Image (.jpg/.png/.bmp/.tif...)
      -> letterbox 640x640 (ultralytics)
      -> YOLOv8s (ONNX ya da PT)
      -> NMS (built-in)
      -> N adet detection: (bbox_xyxy, conf, class_id)

Model dosyalari (bu klasorde):
    yolov8s.onnx     ONNX opset 17, dynamic batch (43 MB)  <- varsayilan
    yolov8s.pt       PyTorch state_dict            (22 MB)  <- fallback

Kullanim:
    # Tek dosya
    python inference_human_kidney_ct.py --image ct.jpg

    # Klasor batch
    python inference_human_kidney_ct.py --dir scans/ --output out.csv

    # CSV batch ('path' veya 'image_path' sutunu)
    python inference_human_kidney_ct.py --csv liste.csv --output out.csv

    # PyTorch backend
    python inference_human_kidney_ct.py --image ct.jpg --backend pytorch

    # Overlay uret (annotated jpg)
    python inference_human_kidney_ct.py --image ct.jpg --overlay overlay.jpg
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np


_DIR = Path(__file__).parent.resolve()
DEFAULT_ONNX = _DIR / "yolov8s.onnx"
DEFAULT_PT   = _DIR / "yolov8s.pt"

# 3 sinif (data.yaml ile ayni)
CLASSES = ["Kidney Stone", "Kidney", "Kidney Cyst"]
NUM_CLASSES = len(CLASSES)

# BGR renkler overlay icin
_COLORS = {
    0: (0, 0, 255),      # Kidney Stone   -> kirmizi
    1: (0, 255, 0),      # Kidney         -> yesil
    2: (255, 128, 0),    # Kidney Cyst    -> mavi-turuncu
}


# ============================================================
# DETECTOR
# ============================================================
class KidneyCTDetector:
    """Human Kidney CT detector (YOLOv8s + 3 sinif).

    Args:
        model_path: .onnx / .pt yolu. None -> backend'e gore default.
        backend:    "onnx" (varsayilan) veya "pytorch"
        device:     "cuda:0" / "cpu" / None (auto)
        conf:       min detection conf (default 0.25)
        iou:        NMS IoU threshold  (default 0.5)
        imgsz:      inference img size (default 640)
    """

    def __init__(self,
                 model_path: str | os.PathLike | None = None,
                 backend: str = "onnx",
                 device: str | None = None,
                 conf: float = 0.25,
                 iou: float = 0.5,
                 imgsz: int = 640):
        backend = backend.lower()
        if backend not in ("onnx", "pytorch"):
            raise ValueError(f"backend 'onnx' veya 'pytorch' olmali: {backend}")

        self.backend = backend
        self.conf = float(conf)
        self.iou = float(iou)
        self.imgsz = int(imgsz)
        self.classes = CLASSES

        self.model_path = Path(model_path) if model_path else (
            DEFAULT_ONNX if backend == "onnx" else DEFAULT_PT)
        if not self.model_path.exists():
            raise FileNotFoundError(f"Model bulunamadi: {self.model_path}")

        # ultralytics her iki formati da tek API ile destekler.
        from ultralytics import YOLO
        task = "detect"
        self._model = YOLO(str(self.model_path), task=task)
        # device secimi
        self.device = self._resolve_device(device)
        # Warmup
        self._warmup()

    @staticmethod
    def _resolve_device(dev):
        if dev is not None:
            return dev
        try:
            import torch
            return "0" if torch.cuda.is_available() else "cpu"
        except Exception:
            return "cpu"

    def _warmup(self):
        # tek dummy inference — cold start maliyetini onceden ode
        dummy = np.zeros((self.imgsz, self.imgsz, 3), dtype=np.uint8)
        try:
            self._model.predict(source=dummy, conf=self.conf, iou=self.iou,
                                 imgsz=self.imgsz, device=self.device,
                                 verbose=False)
        except Exception:
            pass

    # ------------------------------------------------------------
    def predict(self, image_path: str | os.PathLike) -> dict:
        """Tek goruntu tespiti.

        Returns:
            {
                "image_path": str,
                "image_shape": [H, W],
                "n_detections": int,
                "detections": [
                    {"class_id": 0..2, "class_name": ...,
                     "conf": 0..1, "bbox_xyxy": [x1,y1,x2,y2],
                     "bbox_xywh": [cx,cy,w,h], "area": float}, ...
                ],
                "class_counts": {"Kidney Stone": ..., "Kidney": ..., "Kidney Cyst": ...}
            }
        """
        r = self._model.predict(source=str(image_path), conf=self.conf,
                                 iou=self.iou, imgsz=self.imgsz,
                                 device=self.device, verbose=False)[0]
        H, W = int(r.orig_shape[0]), int(r.orig_shape[1])
        detections = []
        if r.boxes is not None and len(r.boxes):
            xyxy = r.boxes.xyxy.cpu().numpy() if hasattr(r.boxes.xyxy, "cpu") else np.asarray(r.boxes.xyxy)
            confs = r.boxes.conf.cpu().numpy() if hasattr(r.boxes.conf, "cpu") else np.asarray(r.boxes.conf)
            cls_ids = r.boxes.cls.cpu().numpy() if hasattr(r.boxes.cls, "cpu") else np.asarray(r.boxes.cls)
            for b, c, k in zip(xyxy, confs, cls_ids):
                x1, y1, x2, y2 = [float(v) for v in b]
                w, h = x2 - x1, y2 - y1
                cx, cy = x1 + w / 2, y1 + h / 2
                cid = int(k)
                detections.append({
                    "class_id": cid,
                    "class_name": self.classes[cid],
                    "conf": float(c),
                    "bbox_xyxy": [round(v, 2) for v in (x1, y1, x2, y2)],
                    "bbox_xywh": [round(v, 2) for v in (cx, cy, w, h)],
                    "area": round(w * h, 2),
                })

        cnt = {c: 0 for c in self.classes}
        for d in detections:
            cnt[d["class_name"]] += 1

        return {
            "image_path": str(image_path),
            "image_shape": [H, W],
            "n_detections": len(detections),
            "detections": detections,
            "class_counts": cnt,
        }

    def predict_batch(self, paths: list[str | os.PathLike]):
        """Coklu goruntu — pandas DataFrame (per-detection satirlari)."""
        import pandas as pd
        rows = []
        for p in paths:
            try:
                out = self.predict(p)
            except Exception as e:
                rows.append({"image_path": str(p), "error": str(e)})
                continue
            if out["n_detections"] == 0:
                rows.append({
                    "image_path": out["image_path"],
                    "image_h": out["image_shape"][0],
                    "image_w": out["image_shape"][1],
                    "class_id": None, "class_name": None, "conf": None,
                    "x1": None, "y1": None, "x2": None, "y2": None,
                    "area": None,
                })
            for d in out["detections"]:
                x1, y1, x2, y2 = d["bbox_xyxy"]
                rows.append({
                    "image_path": out["image_path"],
                    "image_h": out["image_shape"][0],
                    "image_w": out["image_shape"][1],
                    "class_id":   d["class_id"],
                    "class_name": d["class_name"],
                    "conf":       d["conf"],
                    "x1": x1, "y1": y1, "x2": x2, "y2": y2,
                    "area":       d["area"],
                })
        return pd.DataFrame(rows)

    # ------------------------------------------------------------
    def draw_overlay(self, image_path: str | os.PathLike,
                       result: dict | None = None,
                       out_path: str | os.PathLike | None = None):
        """Bbox + label ile annotated goruntu uret. cv2 ile kaydeder."""
        import cv2
        if result is None:
            result = self.predict(image_path)
        img = cv2.imread(str(image_path))
        if img is None:
            raise FileNotFoundError(f"resim okunamadi: {image_path}")
        for d in result["detections"]:
            x1, y1, x2, y2 = [int(v) for v in d["bbox_xyxy"]]
            cid = d["class_id"]
            color = _COLORS.get(cid, (255, 255, 255))
            cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)
            label = f"{d['class_name']} {d['conf']:.2f}"
            (tw, th), bl = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 1)
            cv2.rectangle(img, (x1, y1 - th - bl - 4),
                           (x1 + tw + 4, y1), color, -1)
            cv2.putText(img, label, (x1 + 2, y1 - bl - 2),
                         cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 1,
                         cv2.LINE_AA)
        if out_path is not None:
            cv2.imwrite(str(out_path), img)
        return img


# ============================================================
# CLI
# ============================================================
_IMG_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}


def _collect_from_dir(d: Path) -> list[str]:
    return [str(f) for f in sorted(d.rglob("*"))
            if f.is_file() and f.suffix.lower() in _IMG_EXTS]


def main():
    parser = argparse.ArgumentParser(
        prog="inference_human_kidney_ct",
        description="Human Kidney CT tespit (YOLOv8s, 3 sinif)",
    )
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--image", type=str, help="Tek goruntu")
    g.add_argument("--dir",   type=str, help="Klasor (recursive)")
    g.add_argument("--csv",   type=str,
                    help="CSV — 'path' veya 'image_path' sutunlu")
    parser.add_argument("--output", type=str, default="predictions.csv",
                         help="Batch cikti CSV (default: predictions.csv)")
    parser.add_argument("--json", type=str, default=None,
                         help="Tekil --image icin JSON cikti yolu")
    parser.add_argument("--overlay", type=str, default=None,
                         help="Tekil --image icin annotated .jpg yolu")
    parser.add_argument("--overlay-dir", type=str, default=None,
                         help="Batch icin overlay klasoru")
    parser.add_argument("--backend", type=str, default="onnx",
                         choices=["onnx", "pytorch"],
                         help="Runtime (default: onnx)")
    parser.add_argument("--model", type=str, default=None,
                         help=".onnx / .pt yolu (default: klasordeki)")
    parser.add_argument("--conf", type=float, default=0.25,
                         help="Min detection conf (default 0.25)")
    parser.add_argument("--iou", type=float, default=0.5,
                         help="NMS IoU threshold (default 0.5)")
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--device", type=str, default=None,
                         help="cuda:0 / cpu (default: auto)")
    parser.add_argument("--quiet", "-q", action="store_true")
    args = parser.parse_args()

    print(f"[MODEL   ] yolov8s  backend={args.backend}")
    det = KidneyCTDetector(model_path=args.model, backend=args.backend,
                             device=args.device, conf=args.conf, iou=args.iou,
                             imgsz=args.imgsz)
    print(f"[DEVICE  ] {det.device}")
    print(f"[WEIGHTS ] {det.model_path.name}")
    print(f"[CLASSES ] {NUM_CLASSES}: {', '.join(CLASSES)}")
    print(f"[CONF    ] {det.conf}  [IOU] {det.iou}  [IMGSZ] {det.imgsz}")
    print()

    # Tek dosya
    if args.image:
        out = det.predict(args.image)
        print(f"[IMAGE   ] {args.image}  ({out['image_shape'][1]}x{out['image_shape'][0]})")
        print(f"[DETECT  ] {out['n_detections']} kutucuk")
        for i, d in enumerate(out["detections"], 1):
            x1, y1, x2, y2 = d["bbox_xyxy"]
            print(f"    {i}. {d['class_name']:<14s}  conf={d['conf']:.3f}  "
                  f"bbox=({x1:.0f},{y1:.0f})-({x2:.0f},{y2:.0f})  area={d['area']:.0f}")
        print(f"[COUNTS  ] {out['class_counts']}")
        if args.json:
            Path(args.json).write_text(json.dumps(out, indent=2, ensure_ascii=False))
            print(f"[JSON    ] -> {args.json}")
        if args.overlay:
            det.draw_overlay(args.image, out, args.overlay)
            print(f"[OVERLAY ] -> {args.overlay}")
        return

    # Batch
    if args.dir:
        paths = _collect_from_dir(Path(args.dir))
        print(f"[BATCH   ] {len(paths)} goruntu bulundu ({args.dir})")
    else:
        import pandas as pd
        df_in = pd.read_csv(args.csv)
        col = "image_path" if "image_path" in df_in.columns else "path"
        paths = df_in[col].astype(str).tolist()
        print(f"[BATCH   ] {len(paths)} goruntu ({args.csv})")

    if not paths:
        print("HATA: hicbir goruntu bulunamadi", file=sys.stderr)
        sys.exit(2)

    df = det.predict_batch(paths)
    df.to_csv(args.output, index=False)
    print(f"[OUTPUT  ] -> {args.output} ({len(df)} satir)")

    if args.overlay_dir:
        ov = Path(args.overlay_dir); ov.mkdir(parents=True, exist_ok=True)
        for p in paths:
            try:
                res = det.predict(p)
                fn = ov / (Path(p).stem + "_overlay.jpg")
                det.draw_overlay(p, res, fn)
            except Exception as e:
                print(f"  ! overlay hata {p}: {e}")
        print(f"[OVERLAY ] -> {ov}/*.jpg")

    if not args.quiet and "class_name" in df.columns:
        # Ozet — per-class detection sayisi + hicbir sey bulunmayanlar
        sub = df.dropna(subset=["class_name"])
        print(f"\n[DETECT DAGILIMI] toplam {len(sub)} detection")
        print(sub["class_name"].value_counts().to_string())
        empties = df[df["class_name"].isna()]["image_path"].nunique()
        if empties:
            print(f"[BOS      ] {empties} goruntu — detection yok")


if __name__ == "__main__":
    main()
