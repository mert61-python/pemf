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
try:
    from utils.model_downloader import modul_yani_agirlik as _modul_yani
except Exception:  # utils yolu yoksa (izole kullanim) eski davranis
    def _modul_yani(yerel, _repo):
        return yerel

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
        elif model_path is None:
            # KI G5: modul YANINDAKI ONNX (yalniz kaynaktan kosu; donmusta modul yaninda degil) de butunluk denetiminden gecer —
            # ozet tutmazsa YUKLENMEZ (ModelButunlukHatasi), ozet yoksa acik uyari. Mikroservisin acik `model_path`i DEGISMEZ.
            onnx_path = _modul_yani(onnx_path, f"ai_hub/cat_thermal/{model_name}.onnx")

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


# ============================================================
# XAI — gradient (Grad-CAM++) isi haritasi (Faz 2, 2026-08-26)
# ============================================================
# ⚠️ grad-cam hook'lari + ayni model uzerinde eszamanli explain THREAD-SAFE DEGIL
# (plan §2): tum XAI cagrisi TEK-IS kilidi icinde. XAI kendi PT instance'ini kullanir
# (canli ONNX yoluna dokunmaz); model cache'lenir (istek basina 21MB yukleme olmasin).
import threading as _xai_threading

_XAI_KILIT = _xai_threading.Lock()
_XAI_PT_CACHE: dict = {}


def _build_thermal_model_pt(pt_path: str, backbone_name: str = "ghostnetv2_100.in1k"):
    """training.ThermalClassifier ile birebir mimari + state_dict yukle.

    ⚠️ Audit P3: torch.load weights_only=True — agirlik SAF state_dict (pickle-RCE kapisi
    ACILMAZ; gelen inference(1) kodu False kullaniyordu, tasinirken duzeltildi).
    '_orig_mod.' prefix'i torch.compile artefakti — soyulur.
    """
    import timm
    import torch
    import torch.nn as nn

    class ThermalClassifier(nn.Module):
        def __init__(self, bb_name):
            super().__init__()
            self.backbone = timm.create_model(bb_name, pretrained=False, num_classes=0)
            self.backbone.eval()
            with torch.no_grad():
                dummy = torch.randn(2, 3, IMGSZ, IMGSZ)
                feat_dim = self.backbone(dummy).shape[1]
            self.classifier = nn.Sequential(
                nn.Linear(feat_dim, 256), nn.ReLU(), nn.Dropout(0.3),
                nn.Linear(256, 1),
            )

        def forward(self, x):
            feat = self.backbone(x)
            return self.classifier(feat).squeeze(1)

    model = ThermalClassifier(backbone_name)
    sd = torch.load(pt_path, map_location="cpu", weights_only=True)
    if any(k.startswith("_orig_mod.") for k in sd.keys()):
        sd = {k[len("_orig_mod."):] if k.startswith("_orig_mod.") else k: v for k, v in sd.items()}
    model.load_state_dict(sd)
    return model.eval()


#: Tek lojitli (sigmoid) modelin iki karari. Lojit = Sick kaniti: Sick -> +lojit, Healthy -> -lojit aciklanir.
TERMAL_XAI_SINIFLARI = ("Sick", "Healthy")
#: Tek lojitte iki kararin haritasini AYIRAN yontemler (AII-3.1 olcumu: hirescam = gradcam, rho -0,48...-0,76).
#: gradcam++ sinif-duyarsiz (rho 0,83-0,95), eigencam hedeften BAGIMSIZ (iki harita bayt-ayni) → bunlarda yanit
#: karar IDDIA ETMEZ (hedef None → arayuz genel basligi, toplu CLI karti "aciklanan karar" yazmaz). Izin listesi DEGISMEZ.
TERMAL_SINIF_AYIRAN_YONTEMLER = ("hirescam", "gradcam")


def termal_cam_haritasi(image_path: str, hedef_sinif: str | None = None, pt_path: str | None = None,
                        method: str = "hirescam"):
    """CAM isi haritasi — TAHMIN EDILEN sinifin kaniti (AI1.X1, hoca XAI v3 `xai_thermal_v2.py`).

    ⚠️ Eskiden hedef HEP `class_idx=0` = +Sick lojitiydi ("Saglikli" tahmininde "Hasta" aciklaniyordu). Grad-CAM++
    tek lojitte sinif-duyarsiz (Sick<->Healthy rho 0,83-0,95); HiRes-CAM tamamlayici (-0,45...-0,76) → varsayilan.
    hedef_sinif: cagiranin GOSTERDIGI tahmin; None ise PT lojiti karar verir (lojit >= 0 <=> predict esigi 0.5).
    Doner: (img_rgb (224, 224, 3) uint8, heatmap (H, W) 0-1, aciklanan_sinif)
    """
    if hedef_sinif is not None and hedef_sinif not in TERMAL_XAI_SINIFLARI:
        raise ValueError(f"Termal XAI hedefi gecersiz: {hedef_sinif!r} (beklenen: {TERMAL_XAI_SINIFLARI})")
    import torch

    from ai_hub.xai_utils.grad_cam import GradCAMExplainer

    if pt_path is None:
        from ai_hub.xai_utils.pt_yolu import pt_coz

        pt_path = pt_coz("ai_hub/cat_thermal/GhostNetV2.pt")

    class _NoSqueeze(torch.nn.Module):
        def __init__(self, m):
            super().__init__()
            self.m = m

        def forward(self, x):
            return self.m.classifier(self.m.backbone(x))  # (B, 1) — squeeze YOK

    with _XAI_KILIT:
        model_raw = _XAI_PT_CACHE.get("thermal")
        if model_raw is None:
            model_raw = _build_thermal_model_pt(str(pt_path))
            _XAI_PT_CACHE["thermal"] = model_raw
        device = "cuda:0" if torch.cuda.is_available() else "cpu"
        model_raw = model_raw.to(device)
        model = _NoSqueeze(model_raw).to(device).eval()

        img = Image.open(image_path).convert("RGB").resize((IMGSZ, IMGSZ), Image.BILINEAR)
        img_rgb = np.array(img)
        arr = (img_rgb.astype(np.float32) / 255.0 - MEAN) / STD
        x_t = torch.from_numpy(arr.transpose(2, 0, 1)[None]).to(device)

        if hedef_sinif is None:
            with torch.no_grad():
                hedef_sinif = "Sick" if float(model(x_t).reshape(-1)[0]) >= 0.0 else "Healthy"
        isaret = 1.0 if hedef_sinif == "Sick" else -1.0
        expl = GradCAMExplainer(model, target_layer=model_raw.backbone.blocks[-1],
                                 method=method, device=device)
        # isaretli hedef: Sick -> +lojit, Healthy -> -lojit (cikti (B, 1))
        heatmap = expl.explain(x_t, target=lambda cikti, s=isaret: s * cikti[..., 0])
    return img_rgb, heatmap, hedef_sinif


def xai_termal_isi_haritasi(image_path: str, pt_path: str | None = None,
                             method: str = "hirescam", alpha: float = 0.5,
                             hedef_sinif: str | None = None) -> dict:
    """Termal goruntu icin CAM isi haritasi — BELLEK-ICI base64 (disk yok, karar #3).

    Binary sigmoid model squeeze sorunu _NoSqueeze ile cozulur (bkz. XAI_INTEGRATION §9.5); harita TAHMIN EDILEN
    sinifin kanitini gosterir (`termal_cam_haritasi`). TEK-KAYNAK: router in-process + ai_service ayni fonksiyonu
    cagirir ve gosterdigi tahmini `hedef_sinif` ile gecirir (kapi-paritesi dersi).

    Doner: {"xai_image_base64": <jpg b64 overlay>, "method": ..., "hedef": "Sick" | "Healthy"}
    """
    import cv2

    from ai_hub.xai_utils.overlay import blend_to_array

    img_rgb, heatmap, hedef = termal_cam_haritasi(image_path, hedef_sinif=hedef_sinif, pt_path=pt_path, method=method)
    overlay = blend_to_array(img_rgb, heatmap, alpha=alpha)
    ok, buf = cv2.imencode(".jpg", cv2.cvtColor(overlay, cv2.COLOR_RGB2BGR),
                            [cv2.IMWRITE_JPEG_QUALITY, 85])
    if not ok:
        raise RuntimeError("XAI overlay JPG encode basarisiz")
    import base64 as _b64

    iddia = hedef if method in TERMAL_SINIF_AYIRAN_YONTEMLER else None
    return {"xai_image_base64": _b64.b64encode(buf.tobytes()).decode("ascii"), "method": method, "hedef": iddia}


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
