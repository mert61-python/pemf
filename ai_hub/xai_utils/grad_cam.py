"""grad_cam.py — Grad-CAM / Grad-CAM++ / HiRes-CAM / ScoreCAM tek wrapper.

Icerdeki jaycom-kbg/pytorch-grad-cam paketini sarmalayarak proje geneli tek
API sunar. Girdi: PyTorch model + hedef katman + input tensor -> heatmap (H, W).
"""
from __future__ import annotations
from typing import Callable
import numpy as np
import torch

try:
    from pytorch_grad_cam import (
        GradCAM, GradCAMPlusPlus, HiResCAM, ScoreCAM, EigenCAM, XGradCAM,
    )
    from pytorch_grad_cam.utils.model_targets import ClassifierOutputTarget
    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False


_METHODS = {
    "gradcam":     "GradCAM",
    "gradcam++":   "GradCAMPlusPlus",
    "hirescam":    "HiResCAM",
    "scorecam":    "ScoreCAM",
    "eigencam":    "EigenCAM",
    "xgradcam":    "XGradCAM",
}


def list_pytorch_gradcam_methods() -> list[str]:
    return list(_METHODS.keys())


class GradCAMExplainer:
    """Grad-CAM ailesi icin tek girisli wrapper.

    Args:
        model:        eval moddaki PyTorch nn.Module
        target_layer: gradient toplanacak conv katmani (bir nn.Module referansi)
        method:       'gradcam' | 'gradcam++' | 'hirescam' | 'scorecam' | 'eigencam' | 'xgradcam'
        device:       torch.device veya str
    """

    def __init__(self, model, target_layer, method: str = "gradcam",
                 device=None):
        if not _AVAILABLE:
            raise ImportError(
                "pytorch-grad-cam yok. Kur: pip install grad-cam")
        if method not in _METHODS:
            raise ValueError(f"method: {method} — mevcut: {list(_METHODS)}")

        cls = {
            "gradcam":   GradCAM,
            "gradcam++": GradCAMPlusPlus,
            "hirescam":  HiResCAM,
            "scorecam":  ScoreCAM,
            "eigencam":  EigenCAM,
            "xgradcam":  XGradCAM,
        }[method]

        self.method = method
        self.model = model.eval()
        self.device = torch.device(device) if device else next(model.parameters()).device
        # pytorch-grad-cam 1.5+ artik use_cuda parametresini almiyor;
        # model hangi device'ta ise CAM oradan calisir.
        self._cam = cls(model=self.model, target_layers=[target_layer])

    def explain(self, input_tensor: torch.Tensor,
                 class_idx: int | None = None) -> np.ndarray:
        """Girdi tensoru icin (H, W) 0-1 arasi heatmap.

        Args:
            input_tensor: (1, 3, H, W) veya (B, 3, H, W)
            class_idx: hedef sinif index'i. None ise argmax.

        Returns:
            heatmap: (H, W) numpy float32 [0, 1]
        """
        if input_tensor.dim() == 3:
            input_tensor = input_tensor.unsqueeze(0)
        input_tensor = input_tensor.to(self.device)
        targets = None
        if class_idx is not None:
            targets = [ClassifierOutputTarget(int(class_idx))]
        cam_out = self._cam(input_tensor=input_tensor, targets=targets)
        return cam_out[0]

    def explain_batch(self, input_tensor: torch.Tensor,
                       class_indices: list[int] | None = None) -> np.ndarray:
        """Batch icin (B, H, W)."""
        input_tensor = input_tensor.to(self.device)
        targets = None
        if class_indices is not None:
            targets = [ClassifierOutputTarget(int(c)) for c in class_indices]
        return self._cam(input_tensor=input_tensor, targets=targets)
