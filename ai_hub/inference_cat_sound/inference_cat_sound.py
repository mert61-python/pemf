#!/usr/bin/env python3
"""
inference_cat_sound.py — Kedi Sesi Siniflandirma (Mel Spectrogram + CNN)
=======================================================================
Tek model: **EfficientNet_Lite0** (en iyi backbone)
    Accuracy = 0.874 | F1_macro = 0.876 | MCC = 0.861
    Params   = 3.7 M | Inference = 3.62 ms (GPU) / ~10 ms (CPU-ONNX)

10 sinif:
    Angry, Defence, Fighting, Happy, HuntingMind,
    Mating, MotherCall, Paining, Resting, Warning

Pipeline:
    Audio (.mp3/.wav/.m4a) → librosa mel spectrogram (3-kanal: mel + delta + delta²)
                          → PIL Image (224×224)
                          → EfficientNet_Lite0
                          → 10 sinif olasilik dagilimi
                          → Top-3 tahmin

Model dosyalari (klasorde bulunur):
    EfficientNet_Lite0.pt      — PyTorch state_dict (varsayilan)
    EfficientNet_Lite0.onnx    — ONNX (opset 17, dynamic batch)

Kullanim:
    # Tek dosya (PyTorch)
    python inference_cat_sound.py --audio kedi.mp3

    # ONNX runtime ile
    python inference_cat_sound.py --audio kedi.mp3 --runtime onnx

    # Klasor batch
    python inference_cat_sound.py --dir sounds/ --output results.csv

    # CSV batch (path sutunlu)
    python inference_cat_sound.py --csv input.csv --output results.csv

    # Python API
    from inference_cat_sound import CatSoundClassifier
    clf = CatSoundClassifier()                     # PT + auto GPU/CPU
    clf = CatSoundClassifier(runtime="onnx")       # ONNX (CPU/CUDA)
    out = clf.predict("kedi.mp3")
    print(out["top_1_class"], out["top_1_prob"])
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np


_DIR = Path(__file__).parent.resolve()
CONFIG_PATH = _DIR / "experiment_config.json"

MODEL_NAME = "EfficientNet_Lite0"
TIMM_BACKBONE = "efficientnet_lite0.ra_in1k"    # training.py ile ayni
DEFAULT_MODEL_PT   = _DIR / f"{MODEL_NAME}.pt"
DEFAULT_MODEL_ONNX = _DIR / f"{MODEL_NAME}.onnx"


# ============================================================
# CONFIG
# ============================================================
def _load_config(path: Path = CONFIG_PATH) -> dict:
    """experiment_config.json'i oku."""
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


_CFG = _load_config()
CLASSES: list[str] = _CFG["classes"]
NUM_CLASSES: int = _CFG["n_classes"]
MEL_PARAMS: dict = _CFG["mel_params"]           # sr, n_mels, n_fft, hop, duration
IMGSZ: int = int(_CFG.get("imgsz", 224))

SR = int(MEL_PARAMS["sr"])
N_MELS = int(MEL_PARAMS["n_mels"])
N_FFT = int(MEL_PARAMS["n_fft"])
HOP_LENGTH = int(MEL_PARAMS["hop_length"])
DURATION = float(MEL_PARAMS["duration"])


# ============================================================
# MEL SPECTROGRAM (training.py ile ayni)
# ============================================================
def audio_to_mel_image(audio_path: str | os.PathLike):
    """Audio dosyasini 3-kanal mel spectrogram PIL Image'a cevir.

    Kanal 1: Mel spectrogram (frekans bilgisi)
    Kanal 2: Delta (zamandaki degisim hizi)
    Kanal 3: Delta-delta (degisim ivmesi)

    Returns:
        PIL.Image (IMGSZ × IMGSZ, RGB uint8)
    """
    import librosa
    from PIL import Image

    y, sr = librosa.load(str(audio_path), sr=SR, duration=DURATION, mono=True)

    y_trim, _ = librosa.effects.trim(y, top_db=30)
    if len(y_trim) > SR * 0.3:
        y = y_trim

    mel = librosa.feature.melspectrogram(
        y=y, sr=sr, n_mels=N_MELS, n_fft=N_FFT, hop_length=HOP_LENGTH)
    mel_db = librosa.power_to_db(mel, ref=np.max)
    delta = librosa.feature.delta(mel_db, order=1)
    delta2 = librosa.feature.delta(mel_db, order=2)

    def _norm(ch):
        lo, hi = ch.min(), ch.max()
        if hi - lo < 1e-8:
            return np.zeros_like(ch, dtype=np.uint8)
        return ((ch - lo) / (hi - lo) * 255).astype(np.uint8)

    rgb = np.stack([_norm(mel_db), _norm(delta), _norm(delta2)], axis=2)
    img = Image.fromarray(rgb).resize((IMGSZ, IMGSZ), Image.BILINEAR)
    return img


def _preprocess(img) -> np.ndarray:
    """PIL RGB uint8 -> (1, 3, H, W) float32 tensor, Normalize(0.5, 0.5).

    training.py val_transform ile birebir uyumlu:
        ToTensor()              -> [0,1] float32, (H,W,C) -> (C,H,W)
        Normalize([0.5]*3, [0.5]*3)
    """
    arr = np.asarray(img, dtype=np.float32) / 255.0        # (H, W, 3)
    arr = arr.transpose(2, 0, 1)                            # (3, H, W)
    arr = (arr - 0.5) / 0.5                                 # Normalize
    return arr[None, ...]                                   # (1, 3, H, W)


# ============================================================
# MODEL (training.py SoundClassifier ile ayni mimari)
# ============================================================
def build_sound_model():
    """timm backbone + custom head (256 -> NUM_CLASSES). training.py ile bire bir."""
    import torch
    import torch.nn as nn
    import timm

    class SoundClassifier(nn.Module):
        def __init__(self):
            super().__init__()
            self.backbone = timm.create_model(TIMM_BACKBONE, pretrained=False,
                                              num_classes=0)
            self.backbone.eval()
            with torch.no_grad():
                dummy = torch.randn(1, 3, IMGSZ, IMGSZ)
                feat_dim = self.backbone(dummy).shape[1]
            self.head = nn.Sequential(
                nn.Linear(feat_dim, 256),
                nn.BatchNorm1d(256),
                nn.GELU(),
                nn.Dropout(0.3),
                nn.Linear(256, NUM_CLASSES),
            )

        def forward(self, x):
            feat = self.backbone(x)
            return self.head(feat)

    return SoundClassifier()


# ============================================================
# CLASSIFIER
# ============================================================
class CatSoundClassifier:
    """Kedi ses siniflandirici — EfficientNet_Lite0 (PT veya ONNX).

    Args:
        model_path: PT veya ONNX yolu. None ise runtime'a gore default:
            runtime="pt"   -> EfficientNet_Lite0.pt
            runtime="onnx" -> EfficientNet_Lite0.onnx
        runtime: "pt" veya "onnx" (default: "pt")
        device: "cuda:0" / "cpu" (default: auto)
    """

    def __init__(self,
                 model_path: str | os.PathLike | None = None,
                 runtime: str = "pt",
                 device: str | None = None):
        runtime = runtime.lower()
        if runtime not in ("pt", "onnx"):
            raise ValueError(f"runtime 'pt' veya 'onnx' olmali, verilen: {runtime}")

        self.runtime = runtime
        self.classes = CLASSES

        if runtime == "pt":
            self._init_pt(model_path, device)
        else:
            self._init_onnx(model_path, device)

        self._warmup()

    # -------- PyTorch backend --------
    def _init_pt(self, model_path, device):
        import torch

        self.model_path = Path(model_path) if model_path else DEFAULT_MODEL_PT
        if not self.model_path.exists():
            raise FileNotFoundError(f"PT bulunamadi: {self.model_path}")

        self.device = torch.device(device) if device else torch.device(
            "cuda:0" if torch.cuda.is_available() else "cpu")

        self.model = build_sound_model()
        state = torch.load(str(self.model_path),
                           map_location=self.device,
                           weights_only=False)
        try:
            self.model.load_state_dict(state)
        except RuntimeError:
            if isinstance(state, dict) and "model" in state:
                self.model.load_state_dict(state["model"])
            else:
                raise
        self.model = self.model.to(self.device).eval()

    # -------- ONNX backend --------
    def _init_onnx(self, model_path, device):
        import onnxruntime as ort

        self.model_path = Path(model_path) if model_path else DEFAULT_MODEL_ONNX
        if not self.model_path.exists():
            raise FileNotFoundError(f"ONNX bulunamadi: {self.model_path}")

        want_cuda = (device is None and self._cuda_available()) or \
                    (device and device.startswith("cuda"))
        providers = []
        if want_cuda and "CUDAExecutionProvider" in ort.get_available_providers():
            providers.append("CUDAExecutionProvider")
        providers.append("CPUExecutionProvider")

        self.session = ort.InferenceSession(str(self.model_path), providers=providers)
        self.input_name  = self.session.get_inputs()[0].name
        self.output_name = self.session.get_outputs()[0].name
        self.device = providers[0].replace("ExecutionProvider", "").lower()

    @staticmethod
    def _cuda_available() -> bool:
        try:
            import torch
            return torch.cuda.is_available()
        except Exception:
            return False

    def _warmup(self):
        dummy = np.zeros((1, 3, IMGSZ, IMGSZ), dtype=np.float32)
        self._forward(dummy)

    def _forward(self, x_np: np.ndarray) -> np.ndarray:
        """(B, 3, H, W) float32 -> (B, NUM_CLASSES) softmax olasiliklari."""
        if self.runtime == "pt":
            import torch
            with torch.no_grad():
                t = torch.from_numpy(x_np).to(self.device)
                logits = self.model(t)
                probs = torch.softmax(logits, dim=1).cpu().numpy()
        else:
            logits = self.session.run([self.output_name], {self.input_name: x_np})[0]
            # softmax (numpy)
            logits = logits - logits.max(axis=1, keepdims=True)
            e = np.exp(logits)
            probs = e / e.sum(axis=1, keepdims=True)
        return probs

    # ------------------------------------------------------------
    # Predict
    # ------------------------------------------------------------
    def predict(self, audio_path: str | os.PathLike,
                *, top_k: int = 3) -> dict:
        """Tek ses dosyasi icin sinif tahmini.

        Returns:
            {
                "audio_path": str,
                "top_1_class": str,
                "top_1_prob":  float,
                "top_k": [{"class": ..., "prob": ...}, ...],
                "probabilities": {"Angry": ..., "Defence": ..., ...},
            }
        """
        img = audio_to_mel_image(audio_path)
        x = _preprocess(img)
        probs = self._forward(x)[0]

        idx_sorted = np.argsort(-probs)
        top = [{"class": self.classes[int(i)], "prob": float(probs[i])}
               for i in idx_sorted[:top_k]]
        return {
            "audio_path": str(audio_path),
            "top_1_class": top[0]["class"],
            "top_1_prob":  top[0]["prob"],
            "top_k": top,
            "probabilities": {self.classes[i]: float(probs[i])
                              for i in range(NUM_CLASSES)},
        }

    def predict_batch(self, paths: list[str | os.PathLike],
                      *, top_k: int = 3):
        """Coklu ses dosyasi — pandas DataFrame."""
        import pandas as pd
        rows = []
        for p in paths:
            try:
                out = self.predict(p, top_k=top_k)
                row = {
                    "audio_path": out["audio_path"],
                    "top_1_class": out["top_1_class"],
                    "top_1_prob": out["top_1_prob"],
                }
                for i, t in enumerate(out["top_k"], 1):
                    row[f"top_{i}_class"] = t["class"]
                    row[f"top_{i}_prob"] = t["prob"]
                for c in self.classes:
                    row[f"prob_{c}"] = out["probabilities"][c]
                rows.append(row)
            except Exception as e:
                rows.append({"audio_path": str(p), "error": str(e)})
        return pd.DataFrame(rows)


# ============================================================
# CLI
# ============================================================
_AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".flac", ".ogg", ".aac"}


def _collect_audio_from_dir(d: Path) -> list[str]:
    out = []
    for f in sorted(d.rglob("*")):
        if f.is_file() and f.suffix.lower() in _AUDIO_EXTS:
            out.append(str(f))
    return out


def main():
    parser = argparse.ArgumentParser(
        prog="inference_cat_sound",
        description="Kedi Sesi Siniflandirma (EfficientNet_Lite0 + Mel)",
    )
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--audio", type=str, help="Tek ses dosyasi")
    g.add_argument("--dir",   type=str, help="Klasor (recursive)")
    g.add_argument("--csv",   type=str,
                   help="CSV — 'path' veya 'audio_path' sutunlu")
    parser.add_argument("--output", type=str, default="predictions.csv",
                        help="Batch cikti CSV (default: predictions.csv)")
    parser.add_argument("--runtime", type=str, default="pt", choices=["pt", "onnx"],
                        help="Runtime backend (default: pt)")
    parser.add_argument("--model", type=str, default=None,
                        help=".pt / .onnx yolu (default: klasordeki EfficientNet_Lite0.<runtime>)")
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--device", type=str, default=None,
                        help="cuda:0 / cpu (default: auto)")
    parser.add_argument("--quiet", "-q", action="store_true")
    args = parser.parse_args()

    print(f"[MODEL   ] EfficientNet_Lite0  runtime={args.runtime}")
    clf = CatSoundClassifier(model_path=args.model,
                             runtime=args.runtime,
                             device=args.device)
    print(f"[DEVICE  ] {clf.device}")
    print(f"[WEIGHTS ] {clf.model_path}")
    print(f"[CLASSES ] {NUM_CLASSES}: {', '.join(CLASSES)}")
    print()

    # Tek dosya
    if args.audio:
        out = clf.predict(args.audio, top_k=args.top_k)
        print(f"[AUDIO   ] {args.audio}")
        print(f"[TOP-1   ] {out['top_1_class']}  (prob={out['top_1_prob']:.4f})")
        print(f"[TOP-{args.top_k:d}   ]")
        for i, t in enumerate(out["top_k"], 1):
            print(f"    {i}. {t['class']:<12s}  {t['prob']:.4f}")
        return

    # Batch
    if args.dir:
        paths = _collect_audio_from_dir(Path(args.dir))
        print(f"[BATCH   ] {len(paths)} dosya bulundu ({args.dir})")
    else:  # csv
        import pandas as pd
        df_in = pd.read_csv(args.csv)
        col = "audio_path" if "audio_path" in df_in.columns else "path"
        paths = df_in[col].astype(str).tolist()
        print(f"[BATCH   ] {len(paths)} dosya ({args.csv})")

    if not paths:
        print("HATA: hicbir dosya bulunamadi", file=sys.stderr)
        sys.exit(2)

    df = clf.predict_batch(paths, top_k=args.top_k)
    df.to_csv(args.output, index=False)
    print(f"[OUTPUT  ] -> {args.output} ({len(df)} satir)")

    if not args.quiet and "top_1_class" in df.columns:
        print("\n[TOP-1 DAGILIMI]")
        print(df["top_1_class"].value_counts().to_string())


if __name__ == "__main__":
    main()
