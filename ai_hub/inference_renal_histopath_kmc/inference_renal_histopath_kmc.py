#!/usr/bin/env python3
# Author: mertaygn, cglrgrkn
"""inference_renal_histopath_kmc.py — Renal histopatoloji grade siniflandirma.

Tek model: **V22-KMC-ClassicTrio** (KMCClassicTrio ensemble)
    Mimari: VGG-19-BN + Wide-ResNet-50-2 + DenseNet-201 (logit ortalamasi)
    CV Balanced Accuracy = 0.958
    CV AUC (macro OvR)   = 0.997
    CV Brier             = 0.062
    CV ECE               = 0.041

5 sinif (grade0, grade1, grade2, grade3, grade4).

Pipeline:
    Image (.jpg/.png/.tif/...)
      -> PIL RGB
      -> Resize 224x224
      -> ToTensor + Normalize(mean=[0.485,0.456,0.406], std=[0.229,0.224,0.225])
      -> KMCClassicTrio (VGG19-BN + WideResNet-50-2 + DenseNet-201)
      -> mean logit -> softmax
      -> Top-K grade + olasilik

Model dosyalari (bu klasorde bulunur):
    v22_kmc_classictrio_kmc.onnx    ONNX (opset 17, dynamic batch)  ~858 MB
    v22_kmc_classictrio_kmc.pt      (opsiyonel PyTorch state_dict fallback)

Kullanim:
    # Tek dosya
    python inference_renal_histopath_kmc.py --image kesit.jpg

    # Klasor batch
    python inference_renal_histopath_kmc.py --dir test_data/ --output out.csv

    # CSV batch ('path' veya 'image_path' sutunu)
    python inference_renal_histopath_kmc.py --csv liste.csv --output out.csv

    # PyTorch backend zorla (varsayilan ONNX)
    python inference_renal_histopath_kmc.py --image k.jpg --backend pytorch
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np


_DIR = Path(__file__).parent.resolve()
META_PATH    = _DIR / "best_model_meta.json"
CLASSES_PATH = _DIR / "classes.json"


# ============================================================
# META + CLASSES
# ============================================================
def _load_meta_and_classes():
    # Audit P3: kütüphane modülünde sys.exit YERİNE RuntimeError — sys.exit SystemExit(BaseException)
    # fırlatır, app.py'nin 'except Exception' bloğu YAKALAMAZ → temiz JSON 500 yerine kirli uvicorn hatası.
    if not META_PATH.exists():
        raise RuntimeError(f"{META_PATH.name} yok — training/renal_histopath_kmc/export_best_real.py calistirilmali")
    if not CLASSES_PATH.exists():
        raise RuntimeError(f"{CLASSES_PATH.name} yok")
    meta = json.loads(META_PATH.read_text(encoding="utf-8"))
    classes = json.loads(CLASSES_PATH.read_text(encoding="utf-8"))
    return meta, classes


_META, CLASSES = _load_meta_and_classes()
NUM_CLASSES: int = len(CLASSES)
IMG_SIZE: int = int(_META.get("image_size", 224))

DEFAULT_ONNX = _DIR / _META["onnx_file"]
DEFAULT_PT   = _DIR / _META["torch_state_dict"]

# ImageNet normalize (training pipeline ile birebir)
_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_STD  = np.array([0.229, 0.224, 0.225], dtype=np.float32)


# ============================================================
# PREPROCESS (training KMCDataset.val_transform ile ayni)
# ============================================================
def image_to_tensor(image_path: str | os.PathLike) -> np.ndarray:
    """Path -> (1, 3, 224, 224) float32 tensor (ImageNet normalized).

    torchvision transforms:
        Resize((224, 224))  (bicubic, PIL default)
        ToTensor()          -> HWC uint8 -> CHW float32 [0,1]
        Normalize(MEAN, STD)
    """
    from PIL import Image
    img = Image.open(str(image_path)).convert("RGB")
    img = img.resize((IMG_SIZE, IMG_SIZE), Image.BILINEAR)
    arr = np.asarray(img, dtype=np.float32) / 255.0        # (H, W, 3) [0,1]
    arr = arr.transpose(2, 0, 1)                            # (3, H, W)
    arr = (arr - _MEAN[:, None, None]) / _STD[:, None, None]
    return arr[None, ...].astype(np.float32)                # (1, 3, H, W)


# ============================================================
# MODEL BUILDER (PyTorch fallback için)
# ============================================================
def build_kmc_classic_trio(n_classes: int = 5, pretrained: bool = False):
    """training/renal_histopath_kmc/arge/flagship_variants.py KMCClassicTrio ile ayni.

    VGG-19-BN + Wide-ResNet-50-2 + DenseNet-201, mean-logit ensemble.
    """
    import torch, torch.nn as nn
    from torchvision import models as tv

    class KMCClassicTrio(nn.Module):
        def __init__(self):
            super().__init__()
            v = tv.vgg19_bn(weights=None)
            v.classifier[-1] = nn.Linear(v.classifier[-1].in_features, n_classes)
            w = tv.wide_resnet50_2(weights=None)
            w.fc = nn.Linear(w.fc.in_features, n_classes)
            d = tv.densenet201(weights=None)
            d.classifier = nn.Linear(d.classifier.in_features, n_classes)
            self.vgg = v; self.wrn = w; self.dense = d

        def forward(self, x):
            return (self.vgg(x) + self.wrn(x) + self.dense(x)) / 3.0

    return KMCClassicTrio()


# ============================================================
# CLASSIFIER
# ============================================================
class RenalHistopathClassifier:
    """Renal histopatoloji grade siniflandirici (KMCClassicTrio ensemble).

    Args:
        model_path: .onnx veya .pt yolu. None ise backend'e gore default.
        backend: "onnx" (default) veya "pytorch"
        device: "cuda:0" / "cpu" (default: auto — ONNX GPU varsa CUDA, PT auto)
    """

    def __init__(self,
                 model_path: str | os.PathLike | None = None,
                 backend: str = "onnx",
                 device: str | None = None):
        backend = backend.lower()
        if backend not in ("onnx", "pytorch"):
            raise ValueError(f"backend 'onnx' veya 'pytorch' olmali, verilen: {backend}")

        self.backend = backend
        self.classes = CLASSES
        self.model_path = Path(model_path) if model_path else (
            DEFAULT_ONNX if backend == "onnx" else DEFAULT_PT)
        if not self.model_path.exists():
            raise FileNotFoundError(f"Model bulunamadi: {self.model_path}")

        if backend == "onnx":
            self._init_onnx(device)
        else:
            self._init_pytorch(device)

        self._warmup()

    def _init_onnx(self, device):
        import onnxruntime as ort
        want_cuda = (device is None and self._cuda_available()) or \
                    (device and str(device).startswith("cuda"))
        providers = []
        if want_cuda and "CUDAExecutionProvider" in ort.get_available_providers():
            providers.append("CUDAExecutionProvider")
        providers.append("CPUExecutionProvider")
        self.session = ort.InferenceSession(str(self.model_path), providers=providers)
        self.input_name  = self.session.get_inputs()[0].name
        self.output_name = self.session.get_outputs()[0].name
        self.device = providers[0].replace("ExecutionProvider", "").lower()

    def _init_pytorch(self, device):
        import torch
        self.device = torch.device(device) if device else torch.device(
            "cuda:0" if torch.cuda.is_available() else "cpu")
        self.model = build_kmc_classic_trio(NUM_CLASSES)
        sd = torch.load(str(self.model_path), map_location=self.device, weights_only=True)
        self.model.load_state_dict(sd)
        self.model = self.model.to(self.device).eval()

    @staticmethod
    def _cuda_available() -> bool:
        try:
            import torch
            return torch.cuda.is_available()
        except Exception:
            return False

    def _warmup(self):
        dummy = np.zeros((1, 3, IMG_SIZE, IMG_SIZE), dtype=np.float32)
        self._forward(dummy)

    def _forward(self, x_np: np.ndarray) -> np.ndarray:
        """(B, 3, 224, 224) float32 -> (B, 5) softmax olasiliklari."""
        if self.backend == "onnx":
            logits = self.session.run([self.output_name], {self.input_name: x_np})[0]
            logits = logits - logits.max(axis=1, keepdims=True)
            e = np.exp(logits)
            return e / e.sum(axis=1, keepdims=True)
        else:
            import torch
            with torch.no_grad():
                t = torch.from_numpy(x_np).to(self.device)
                logits = self.model(t)
                return torch.softmax(logits, dim=1).cpu().numpy()

    # ------------------------------------------------------------
    def predict(self, image_path: str | os.PathLike, *, top_k: int = 3) -> dict:
        """Tek gorutu icin sinif tahmini."""
        x = image_to_tensor(image_path)
        probs = self._forward(x)[0]
        idx = np.argsort(-probs)
        top = [{"class": self.classes[int(i)], "prob": float(probs[i])}
               for i in idx[:top_k]]
        return {
            "image_path": str(image_path),
            "top_1_class": top[0]["class"],
            "top_1_prob":  top[0]["prob"],
            "top_k": top,
            "probabilities": {self.classes[i]: float(probs[i])
                              for i in range(NUM_CLASSES)},
        }

    def predict_batch(self, paths: list[str | os.PathLike],
                       *, top_k: int = 3, batch_size: int = 16):
        """Coklu gorutu — pandas DataFrame."""
        import pandas as pd
        rows = []
        # Batching (ONNX dynamic axes destekliyor)
        for start in range(0, len(paths), batch_size):
            chunk = paths[start:start + batch_size]
            tensors = []
            ok_paths = []
            for p in chunk:
                try:
                    tensors.append(image_to_tensor(p))
                    ok_paths.append(p)
                except Exception as e:
                    rows.append({"image_path": str(p), "error": str(e)})
            if not tensors:
                continue
            x = np.concatenate(tensors, axis=0).astype(np.float32)
            probs = self._forward(x)
            for i, p in enumerate(ok_paths):
                idx = np.argsort(-probs[i])
                top = [{"class": self.classes[int(j)], "prob": float(probs[i, j])}
                       for j in idx[:top_k]]
                row = {
                    "image_path": str(p),
                    "top_1_class": top[0]["class"],
                    "top_1_prob":  top[0]["prob"],
                }
                for k, t in enumerate(top, 1):
                    row[f"top_{k}_class"] = t["class"]
                    row[f"top_{k}_prob"]  = t["prob"]
                for c in self.classes:
                    row[f"prob_{c}"] = float(probs[i, self.classes.index(c)])
                rows.append(row)
        return pd.DataFrame(rows)


# ============================================================
# CLI
# ============================================================
_IMG_EXTS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}


def _collect_from_dir(d: Path) -> list[str]:
    return [str(f) for f in sorted(d.rglob("*"))
            if f.is_file() and f.suffix.lower() in _IMG_EXTS]


# ============================================================
# XAI — HiRes-CAM x3 backbone + ensemble mean + DISAGREEMENT (Faz 4, 2026-08-26)
# ============================================================
# 3 backbone (VGG19-BN / WideResNet50-2 / DenseNet201) ayri ayri HiRes-CAM alir;
# ortalama = konsensus isi haritasi, std = DISAGREEMENT ("uc modelin AYRISTIGI bolgeler"
# — tek skalar guvenin gosteremedigi klinik model-kararsizligi gostergesi).
# ⚠️ 858MB PT + grad-cam hook'lari: TEK-IS kilidi + instance cache (canli ONNX yoluna
# dokunmaz); bellek-ici base64 (karar #3 anlik gosterim). weights_only=True sinif
# icindeki _init_pytorch'tan gelir (Audit P3 korunur).
import threading as _xai_threading

_XAI_KILIT = _xai_threading.Lock()
_XAI_PT_CACHE: dict = {}

# Backbone -> HiRes-CAM hedef katmani (KMCTrio yapisina pinli).
_KMC_TRIO_TARGET_LAYERS = {
    "VGG19-BN": lambda m: m.vgg.features[-1],
    "WideResNet50-2": lambda m: m.wrn.layer4[-1],
    "DenseNet-201": lambda m: m.dense.features.denseblock4,
}


def xai_histopat_isi_haritasi(image_path: str, pt_path: str | None = None,
                                method: str = "hirescam", alpha: float = 0.45) -> dict:
    """Histopat kesiti icin ensemble HiRes-CAM — bellek-ici base64.

    Doner: {"xai_image_base64": ensemble-MEAN overlay (modelin dayandigi bolgeler),
            "xai_disagreement_base64": std overlay 'hot' (modellerin AYRISTIGI bolgeler),
            "method": "hirescam-ensemble"}.
    TEK-KAYNAK: router + ai_service ayni fonksiyon (kapi-paritesi dersi).
    ⚠️ CPU'da 3 backbone backward DAKIKA mertebesine uzayabilir (GPU'da ~sn) — cagiran
    async/thread kullanir; kilit ayni anda tek istegi isler.
    """
    import base64 as _b64

    import cv2
    import torch
    from PIL import Image

    from ai_hub.xai_utils.disagreement import ensemble_disagreement_map, mean_cam
    from ai_hub.xai_utils.grad_cam import GradCAMExplainer
    from ai_hub.xai_utils.overlay import blend_to_array

    if pt_path is None:
        if DEFAULT_PT.exists():
            pt_path = DEFAULT_PT
        else:
            from ai_hub.xai_utils.pt_yolu import pt_coz

            pt_path = pt_coz("ai_hub/inference_renal_histopath_kmc/v22_kmc_classictrio_kmc.pt")

    with _XAI_KILIT:
        clf = _XAI_PT_CACHE.get("kmc")
        if clf is None:
            clf = RenalHistopathClassifier(model_path=pt_path, backend="pytorch")
            _XAI_PT_CACHE["kmc"] = clf

        pred = clf.predict(image_path, top_k=1)
        top1_idx = clf.classes.index(pred["top_1_class"])

        img_pil = Image.open(str(image_path)).convert("RGB").resize(
            (IMG_SIZE, IMG_SIZE), Image.BILINEAR)
        img_np = np.asarray(img_pil)
        x_t = torch.from_numpy(image_to_tensor(image_path)).to(clf.device)

        cams = []
        for _ad, layer_fn in _KMC_TRIO_TARGET_LAYERS.items():
            expl = GradCAMExplainer(clf.model, layer_fn(clf.model),
                                     method=method, device=str(clf.device))
            cams.append(expl.explain(x_t, class_idx=top1_idx))

    avg = mean_cam(cams)
    dis = ensemble_disagreement_map(cams, mode="std")

    def _jpg64(rgb_overlay):
        ok, buf = cv2.imencode(".jpg", cv2.cvtColor(rgb_overlay, cv2.COLOR_RGB2BGR),
                                [cv2.IMWRITE_JPEG_QUALITY, 85])
        if not ok:
            raise RuntimeError("XAI overlay JPG encode basarisiz")
        return _b64.b64encode(buf.tobytes()).decode("ascii")

    return {
        "xai_image_base64": _jpg64(blend_to_array(img_np, avg, alpha=alpha)),
        "xai_disagreement_base64": _jpg64(blend_to_array(img_np, dis, alpha=0.5, colormap="hot")),
        "method": "hirescam-ensemble",
    }


def main():
    parser = argparse.ArgumentParser(
        prog="inference_renal_histopath_kmc",
        description="Renal histopatoloji grade siniflandirma "
                     "(V22-KMC-ClassicTrio ensemble)",
    )
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--image", type=str, help="Tek goruntu dosyasi")
    g.add_argument("--dir",   type=str, help="Klasor (recursive)")
    g.add_argument("--csv",   type=str,
                    help="CSV — 'path' veya 'image_path' sutunu")
    parser.add_argument("--output", type=str, default="predictions.csv",
                         help="Batch cikti CSV (default: predictions.csv)")
    parser.add_argument("--backend", type=str, default="onnx",
                         choices=["onnx", "pytorch"],
                         help="Runtime backend (default: onnx)")
    parser.add_argument("--model", type=str, default=None,
                         help=".onnx / .pt yolu (default: klasordeki)")
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--device", type=str, default=None,
                         help="cuda:0 / cpu (default: auto)")
    parser.add_argument("--quiet", "-q", action="store_true")
    args = parser.parse_args()

    print(f"[MODEL   ] {_META.get('name', '?')}  backend={args.backend}")
    clf = RenalHistopathClassifier(model_path=args.model,
                                     backend=args.backend,
                                     device=args.device)
    print(f"[DEVICE  ] {clf.device}")
    print(f"[WEIGHTS ] {clf.model_path.name}")
    print(f"[CLASSES ] {NUM_CLASSES}: {', '.join(CLASSES)}")
    print()

    if args.image:
        out = clf.predict(args.image, top_k=args.top_k)
        print(f"[IMAGE   ] {args.image}")
        print(f"[TOP-1   ] {out['top_1_class']}  (prob={out['top_1_prob']:.4f})")
        print(f"[TOP-{args.top_k:d}   ]")
        for i, t in enumerate(out["top_k"], 1):
            print(f"    {i}. {t['class']:<8s}  {t['prob']:.4f}")
        return

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

    df = clf.predict_batch(paths, top_k=args.top_k, batch_size=args.batch_size)
    df.to_csv(args.output, index=False)
    print(f"[OUTPUT  ] -> {args.output} ({len(df)} satir)")

    if not args.quiet and "top_1_class" in df.columns:
        print("\n[TOP-1 DAGILIMI]")
        print(df["top_1_class"].value_counts().to_string())


if __name__ == "__main__":
    main()
