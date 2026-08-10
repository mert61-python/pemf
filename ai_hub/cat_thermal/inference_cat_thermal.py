#!/usr/bin/env python3
# Author: mertaygn, cglrgrkn
"""
inference_cat_thermal.py — Kedi Thermal Saglik Tahmini (ONNX)
==============================================================
Thermal goruntuden kedi sağlık durumu: Healthy / Sick

Modeller:
  GhostNetV2  — AUC=0.999, Acc=98.9%, 20MB (default)
  FastViT_T8  — AUC=0.999, Acc=98.6%, 43MB

Kullanim:
  # Tek goruntu
  python inference_cat_thermal.py --image kedi_thermal.jpg

  # Klasor
  python inference_cat_thermal.py --source thermal_images/

  # Model secimi
  python inference_cat_thermal.py --image kedi.jpg --model FastViT_T8

  # Interaktif
  python inference_cat_thermal.py
"""

import os
import sys
import argparse
import numpy as np
from PIL import Image

_DIR = os.path.dirname(os.path.abspath(__file__))

AVAILABLE_MODELS = {
    "GhostNetV2": os.path.join(_DIR, "GhostNetV2.onnx"),
}
DEFAULT_MODEL = "GhostNetV2"

IMGSZ = 224
# ImageNet normalization
MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


class CatThermalPredictor:
    def __init__(self, model_name=DEFAULT_MODEL, model_path=None, providers=None):
        import onnxruntime as ort

        # mikroservis: explicit model_path (/models mount) + providers (CUDA) — geriye uyumlu.
        onnx_path = model_path or AVAILABLE_MODELS.get(model_name)
        if onnx_path is None or not os.path.exists(onnx_path):
            try:
                from utils.model_downloader import download_model_sync
                repo_path = f"ai_hub/cat_thermal/{model_name}.onnx"
                onnx_path = download_model_sync(repo_path)
            except Exception as e:
                raise FileNotFoundError(f"Model bulunamadi ve indirilemedi ({model_name}): {e}")

        if providers is None:
            providers = ["CPUExecutionProvider"]
        self.session = ort.InferenceSession(onnx_path, providers=providers)
        self.input_name = self.session.get_inputs()[0].name
        self.model_name = model_name

        # Warmup
        dummy = np.random.randn(1, 3, IMGSZ, IMGSZ).astype(np.float32)
        self.session.run(None, {self.input_name: dummy})

    def preprocess(self, image_path):
        """Load and preprocess thermal image."""
        img = Image.open(image_path).convert("RGB")
        img = img.resize((IMGSZ, IMGSZ), Image.BILINEAR)
        arr = np.array(img, dtype=np.float32) / 255.0
        arr = (arr - MEAN) / STD
        arr = arr.transpose(2, 0, 1)  # HWC → CHW
        return arr[np.newaxis, ...]   # add batch dim

    def predict(self, image_path, threshold=0.5):
        """Predict health status from thermal image.

        Returns:
            dict with keys: label, probability, confidence
        """
        x = self.preprocess(image_path)
        logits = self.session.run(None, {self.input_name: x})[0]

        # Sigmoid
        prob = 1.0 / (1.0 + np.exp(-float(logits[0])))

        if prob >= threshold:
            label = "Sick"
            confidence = prob
        else:
            label = "Healthy"
            confidence = 1.0 - prob

        return {
            "label": label,
            "probability_sick": round(float(prob), 4),
            "confidence": round(float(confidence), 4),
        }

    def predict_batch(self, image_paths, threshold=0.5):
        """Predict for multiple images."""
        results = []
        for path in image_paths:
            try:
                result = self.predict(path, threshold)
                result["image"] = os.path.basename(path)
                results.append(result)
            except Exception as e:
                results.append({
                    "image": os.path.basename(path),
                    "label": "ERROR",
                    "probability_sick": 0.0,
                    "confidence": 0.0,
                    "error": str(e)[:100],
                })
        return results


def main():
    parser = argparse.ArgumentParser(
        description="Kedi Thermal Saglik Tahmini (ONNX)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ornekler:
  python inference_cat_thermal.py --image kedi_thermal.jpg
  python inference_cat_thermal.py --source thermal_images/ --threshold 0.4
  python inference_cat_thermal.py --model FastViT_T8 --image kedi.jpg
""")
    parser.add_argument("--image", type=str, help="Tek goruntu yolu")
    parser.add_argument("--source", type=str, help="Klasor yolu")
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL,
                        choices=list(AVAILABLE_MODELS.keys()),
                        help=f"Model (default: {DEFAULT_MODEL})")
    parser.add_argument("--threshold", type=float, default=0.5,
                        help="Sick threshold (default: 0.5)")

    args = parser.parse_args()

    print("=" * 60)
    print("Kedi Thermal Saglik Tahmini")
    print(f"Model: {args.model} | Threshold: {args.threshold}")
    print("=" * 60)

    predictor = CatThermalPredictor(args.model)

    if args.image:
        # Tek goruntu
        if not os.path.exists(args.image):
            print(f"Dosya bulunamadi: {args.image}")
            sys.exit(1)

        result = predictor.predict(args.image, args.threshold)
        icon = "🟢" if result["label"] == "Healthy" else "🔴"
        print(f"\n  Goruntu: {args.image}")
        print(f"  Sonuc:   {icon} {result['label']}")
        print(f"  Sick olasılığı: %{result['probability_sick']*100:.1f}")
        print(f"  Guven:   %{result['confidence']*100:.1f}")

    elif args.source:
        # Klasor
        import glob
        images = sorted(glob.glob(os.path.join(args.source, "*.jpg")) +
                        glob.glob(os.path.join(args.source, "*.jpeg")) +
                        glob.glob(os.path.join(args.source, "*.png")))
        if not images:
            print(f"Goruntu bulunamadi: {args.source}")
            sys.exit(1)

        print(f"\n{len(images)} goruntu isleniyor...")
        results = predictor.predict_batch(images, args.threshold)

        healthy = sum(1 for r in results if r["label"] == "Healthy")
        sick = sum(1 for r in results if r["label"] == "Sick")

        print(f"\nSonuc: {healthy} Healthy, {sick} Sick")
        print(f"\n{'Goruntu':40s} {'Sonuc':10s} {'Sick%':>8s} {'Guven':>8s}")
        print("-" * 70)
        for r in results:
            icon = "🟢" if r["label"] == "Healthy" else "🔴"
            print(f"  {r['image']:38s} {icon} {r['label']:8s} "
                  f"{r['probability_sick']*100:7.1f}% {r['confidence']*100:7.1f}%")

    else:
        # Interaktif
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

                result = predictor.predict(path, args.threshold)
                icon = "🟢" if result["label"] == "Healthy" else "🔴"
                print(f"  {icon} {result['label']} | Sick: %{result['probability_sick']*100:.1f} | Guven: %{result['confidence']*100:.1f}")

            except KeyboardInterrupt:
                print("\n  Cikis.")
                break
            except Exception as e:
                print(f"  Hata: {e}")


if __name__ == "__main__":
    main()
