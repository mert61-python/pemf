"""ig_torch.py — Captum Integrated Gradients (PyTorch MLP/tabular icin)."""
from __future__ import annotations
from typing import Callable
import numpy as np


def integrated_gradients(model, X: np.ndarray,
                          *, class_idx: int | list[int] | None = None,
                          baseline: np.ndarray | float = 0.0,
                          n_steps: int = 50,
                          internal_batch_size: int | None = 64,
                          device=None) -> np.ndarray:
    """PyTorch modelin (N, F) girdisine gore IG attribution'i.

    Args:
        model:      eval moddaki PyTorch nn.Module (logit doner)
        X:          (N, F) float32 numpy
        class_idx:  int (tum ornekler icin ayni) | list[int] (per-sample) | None (argmax)
        baseline:   float (X'in tumune uygulanacak sabit) veya (F,) veya (N, F)
        n_steps:    IG entegrasyon adim sayisi
        internal_batch_size: Captum ic-batch (PEMF sertlestirmesi 2026-08-26: verilmezse
                    Captum N*n_steps genislemesini TEK seferde isler — RNA-seq gibi genis
                    F'te GPU/RAM OOM; varsayilan 64 bellek zarfini sinirlar)
        device:     torch.device / str

    Returns:
        attributions: (N, F) numpy float32 — signed (pozitif -> tahmine katki)
    """
    import torch
    from captum.attr import IntegratedGradients

    if X.ndim == 1:
        X = X[None, :]
    N, F = X.shape

    model.eval()
    dev = torch.device(device) if device else next(model.parameters()).device
    X_t = torch.from_numpy(X.astype(np.float32)).to(dev)

    if isinstance(baseline, (int, float)):
        bl = torch.full_like(X_t, float(baseline))
    else:
        bl = torch.from_numpy(np.asarray(baseline, dtype=np.float32)).to(dev)
        if bl.dim() == 1:
            bl = bl.unsqueeze(0).expand_as(X_t)

    # target'i belirle
    with torch.no_grad():
        logits = model(X_t)
    if class_idx is None:
        target = logits.argmax(dim=1)
    elif isinstance(class_idx, int):
        target = torch.full((N,), int(class_idx), device=dev, dtype=torch.long)
    else:
        target = torch.tensor(class_idx, device=dev, dtype=torch.long)

    ig = IntegratedGradients(model)
    attr = ig.attribute(X_t, baselines=bl, target=target, n_steps=n_steps,
                        internal_batch_size=internal_batch_size)
    return attr.detach().cpu().numpy()
