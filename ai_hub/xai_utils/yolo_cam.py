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


# ============================================================================
# AI1.X2/X3 (hoca XAI v3, 2026-10, `xai_utils/yolo_cam_v2.py`) — TESPIT HEDEFLI CAM
# ============================================================================
# OLCULDU (guii 97908b9b, gercek yolov8s.pt, CPU; DUZELTME-AI1.md X2/X3) — YoloEigenCAM'in uc kusuru:
#   1) on isleme LetterBox(scaleup=False): ultralytics predict scaleup=True kullanir → 300x300 kan yaymasi 640'in
#      ortasinda kucuk kaldi; aciklanan girdi modelin gordugu girdi DEGIL,
#   2) letterbox geri alinmadan 640x640 harita orijinal boyuta gerildi → retikulositte harita enerjisinin %100'u
#      dolgudaydi; BT'de siyah zemin payi %36-86,
#   3) EigenCAM etiket-bagimsiz (PCA): tespit kutularindaki pay %0-27 (tesadufi beklenti %3-6).
# YoloDetCAM: predict ile ayni on isleme (LetterBox auto=False, scaleup=True), dolgu kirpilarak orijinale geri
# olcekleme, hedef = TESPIT SKORU (guveni > conf ankrajlarin sinif skorlari; class_id verilirse yalniz o sinif),
# Detect basinin beslendigi P3/P4/P5 katmanlari birlikte, HiRes-CAM. Hocanin kutu payi olcumu %87,6-99,2.
# guii sertlestirmesi: agirlik yalniz cagiranin verdigi YOLO ornegi (pt_coz ile cozulmus MUTLAK yol; ciplak ad →
# ultralytics indirme denemesi YOK), import'lar fonksiyon icinde (torch'suz ortamda modul yine yuklenir), XAI'nin
# YOLO ornegi predict ile PAYLASILMAZ (predict modeli fuse edip inference tensorune cevirir — autograd kirilir).
class _TespitBasCiktisi:
    """DetectionModel ciktisinin ilk tensoru (B, 4+nc, A)."""

    def __init__(self, m):
        self.m = m

    def __call__(self, x):
        out = self.m(x)
        return out[0] if isinstance(out, (list, tuple)) else out

    def eval(self):
        self.m.eval()
        return self

    def parameters(self):
        return self.m.parameters()

    def zero_grad(self):
        return self.m.zero_grad()


class TespitSkoruHedefi:
    """CAM hedefi = tespit skorlari toplami: guveni > conf ankrajlar; hicbiri yoksa en iyi topk (harita bos kalmaz)."""

    def __init__(self, conf: float, class_id: int | None = None, topk: int = 5):
        self.conf, self.class_id, self.topk = float(conf), class_id, int(topk)

    def __call__(self, out):  # out: (4+nc, A)
        scores = out[4:, :]
        s = scores[self.class_id] if self.class_id is not None else scores.max(0).values
        maske = s.detach() > self.conf
        if int(maske.sum()) == 0:
            idx = s.detach().topk(min(self.topk, s.numel())).indices
            return s[idx].sum()
        return (s * maske).sum()


class YoloDetCAM:
    """Tespit hedefli HiRes-CAM / Grad-CAM — ultralytics YOLO (v8/11) icin.

    Args:
        yolo:   ultralytics.YOLO ornegi (PT; XAI'ye OZEL — predict icin kullanilmamis olmali)
        imgsz:  predict ile ayni girdi boyutu (640)
        conf:   hedefe giren ankraj esigi (predict conf'u ile ayni: 0.25)
        method: "hirescam" (varsayilan) | "gradcam"
    """

    def __init__(self, yolo, imgsz: int = 640, conf: float = 0.25, method: str = "hirescam",
                 device: str | None = None):
        import torch
        from pytorch_grad_cam import GradCAM, HiResCAM

        if method not in ("hirescam", "gradcam"):
            raise ValueError(f"YoloDetCAM yontemi: {method} — mevcut: hirescam, gradcam")
        self.imgsz, self.conf, self.method = int(imgsz), float(conf), method
        if device is None:
            device = "cuda:0" if torch.cuda.is_available() else "cpu"
        dev = str(device)
        if dev.isdigit():
            dev = f"cuda:{dev}"
        self.device = torch.device(dev)
        det = yolo.model.to(self.device).eval()
        for p in det.parameters():
            p.requires_grad_(True)
        bas = det.model[-1]
        katmanlar = [det.model[i] for i in bas.f]  # Detect'in girdileri: P3, P4, P5
        sinif = {"hirescam": HiResCAM, "gradcam": GradCAM}[method]
        self._cam = sinif(model=_TespitBasCiktisi(det), target_layers=katmanlar)

    def _preprocess(self, img_bgr):
        """predict ile BIREBIR ayni letterbox. Doner: (tensor, (top, left, nh, nw, H0, W0))."""
        import torch
        from ultralytics.data.augment import LetterBox

        H0, W0 = img_bgr.shape[:2]
        im = LetterBox(new_shape=(self.imgsz, self.imgsz), auto=False, scaleup=True)(image=img_bgr)
        r = min(self.imgsz / H0, self.imgsz / W0)
        nw, nh = round(W0 * r), round(H0 * r)
        dw, dh = (self.imgsz - nw) / 2, (self.imgsz - nh) / 2
        top, left = int(round(dh - 0.1)), int(round(dw - 0.1))  # LetterBox'in kendi yuvarlamasi
        x = im[..., ::-1].astype(np.float32).transpose(2, 0, 1)[None] / 255.0
        return torch.from_numpy(np.ascontiguousarray(x)).to(self.device), (top, left, nh, nw, H0, W0)

    @staticmethod
    def _unletterbox(heat, geo):
        """Dolguyu kirp, orijinal (H0, W0) boyutuna olcekle."""
        import cv2

        top, left, nh, nw, H0, W0 = geo
        kirpik = heat[top:top + nh, left:left + nw]
        return cv2.resize(kirpik.astype(np.float32), (W0, H0), interpolation=cv2.INTER_LINEAR)

    def explain(self, image, class_id: int | None = None) -> np.ndarray:
        """(H0, W0) [0, 1] isi haritasi — orijinal goruntuye HIZALI."""
        import cv2

        img = cv2.imread(str(image)) if isinstance(image, (str, Path)) else image
        if img is None:
            raise FileNotFoundError(f"resim okunamadi: {image}")
        for p in self._cam.model.parameters():  # guvenlik: grad acik kalsin
            p.requires_grad_(True)
        x, geo = self._preprocess(img)
        heat = self._cam(input_tensor=x, targets=[TespitSkoruHedefi(self.conf, class_id)])[0]
        h = self._unletterbox(heat, geo)
        mx = float(h.max())
        return h / mx if mx > 0 else h
