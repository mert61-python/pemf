"""yolo_cam.py — YOLOv8/11/26 (ultralytics) icin EigenCAM/Grad-CAM helper.

Ultralytics YOLO forward'i (torch tensor + list feature maps) pytorch-grad-cam
ile direkt uyumlu degil — bu modul yalnizca "primary prediction tensor"u
donduren bir sarmalayici uygular ve EigenCAM'i C2f/CSP katmani uzerinde
calistirir.

Kullanim:
    from ultralytics import YOLO
    from xai_utils.yolo_cam import YoloEigenCAM

    yolo = YOLO("yolov8s.pt")
    cam = YoloEigenCAM(yolo, layer_idx=-2)   # son C2f (Detect'ten onceki)
    heatmap = cam.explain("image.jpg")       # (H, W) 0-1 heatmap (orijinal boyuta)
"""
from __future__ import annotations
from pathlib import Path
from typing import Union
import numpy as np


class _YoloForwardWrapper:
    """YOLO's DetectionModel forward'inda ilk tensoru don."""
    def __init__(self, det_model):
        self._m = det_model
    def __call__(self, x):
        out = self._m(x)
        # out = (predictions_tensor, feature_maps_list) — sadece 1. tensoru al
        if isinstance(out, (list, tuple)):
            out = out[0]
        # (B, 4 + nc, num_anchors) veya benzeri; EigenCAM bunun PCA'sini alacak
        return out
    def eval(self):
        self._m.eval(); return self
    def parameters(self):
        return self._m.parameters()
    def zero_grad(self):
        return self._m.zero_grad()
    def to(self, device):
        self._m.to(device); return self


class YoloEigenCAM:
    """EigenCAM YOLO uzerine — label-agnostic (PCA tabanli).

    Args:
        yolo:      ultralytics.YOLO nesnesi (PT ile yuklenmis)
        layer_idx: hedef katman indeksi (default -2 -> son C2f/CSP, Detect oncesi)
        imgsz:     inference boyut (default 640)
        device:    "cuda:0" / "cpu" / None (auto)
    """

    def __init__(self, yolo, layer_idx: int = -2, imgsz: int = 640,
                 device: str | None = None):
        try:
            from pytorch_grad_cam import EigenCAM
        except ImportError:
            raise ImportError("pytorch-grad-cam yok. Kur: pip install grad-cam")
        import torch

        self.yolo = yolo
        self.imgsz = int(imgsz)
        # Ultralytics '0'/'gpu' gibi string'leri normalize et
        if device is None:
            self.device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
        else:
            dev_str = str(device).lower()
            if dev_str.isdigit() or dev_str in ("gpu",):
                dev_str = f"cuda:{dev_str}" if dev_str.isdigit() else "cuda:0"
            self.device = torch.device(dev_str)

        # DetectionModel torch nn.Module
        det_model = yolo.model.to(self.device).eval()
        # Hedef katman — model.model (Sequential), -2 son C2f
        target_layer = det_model.model[layer_idx]
        # Wrapper: forward'da ilk tensoru don
        self._wrapped = _YoloForwardWrapper(det_model)
        self._cam = EigenCAM(model=self._wrapped, target_layers=[target_layer])

    def _preprocess(self, img_path_or_bgr) -> tuple:
        """Letterbox 640 + normalize [0,1] + tensor. Return: (tensor, (H,W))."""
        import cv2
        import torch
        if isinstance(img_path_or_bgr, (str, Path)):
            img_bgr = cv2.imread(str(img_path_or_bgr))
            if img_bgr is None:
                raise FileNotFoundError(f"resim okunamadi: {img_path_or_bgr}")
        else:
            img_bgr = img_path_or_bgr
        H0, W0 = img_bgr.shape[:2]
        # Ultralytics LetterBox (proje icinde var)
        from ultralytics.data.augment import LetterBox
        lb = LetterBox(new_shape=(self.imgsz, self.imgsz), auto=False, scaleup=False)
        img_lb = lb(image=img_bgr)                            # (imgsz, imgsz, 3) BGR uint8
        img_rgb = img_lb[..., ::-1].copy()                     # BGR -> RGB
        x = img_rgb.astype(np.float32) / 255.0
        x = x.transpose(2, 0, 1)[None]                         # (1, 3, H, W)
        return torch.from_numpy(x).to(self.device), (H0, W0), img_bgr

    def explain(self, image, resize_to_original: bool = True) -> np.ndarray:
        """(H, W) 0-1 heatmap. resize_to_original=True -> orijinal goruntu boyutu."""
        import cv2
        x, (H0, W0), _ = self._preprocess(image)
        heatmap = self._cam(input_tensor=x, targets=None)[0]   # (imgsz, imgsz) 0-1
        if resize_to_original:
            heatmap = cv2.resize(heatmap.astype(np.float32), (W0, H0),
                                   interpolation=cv2.INTER_LINEAR)
        return heatmap
