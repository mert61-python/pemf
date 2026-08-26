"""shap_wrapper.py — Tek fonksiyon icinde tum SHAP Explainer'lari yonlendir.

    explain_shap(model, X, feature_names=..., model_type='auto', ...)

model_type:
    'tree'    -> XGBoost / LightGBM / CatBoost / sklearn Tree / RandomForest / ExtraTrees
    'linear'  -> LogisticRegression / LinearRegression
    'deep'    -> PyTorch nn.Module  (DeepExplainer, background gerekli)
    'kernel'  -> generic sklearn/onnxruntime callable
    'auto'    -> otomatik tespit
"""
from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import Any
import numpy as np

_log = logging.getLogger(__name__)


@dataclass
class ShapResult:
    values: np.ndarray            # (N, F) veya (N, F, C) — sinif basina
    base_values: np.ndarray        # (N,) veya (N, C)
    feature_names: list[str]
    model_type: str
    class_names: list[str] | None = None


def _detect_type(model) -> str:
    name = type(model).__name__.lower()
    mod  = type(model).__module__.lower()
    if any(k in name for k in ("xgb", "lgbm", "catboost", "randomforest",
                                 "extratrees", "gradientboost", "histgradient",
                                 "decisiontree", "extratree", "bagging")):
        return "tree"
    if "xgboost" in mod or "lightgbm" in mod or "catboost" in mod:
        return "tree"
    if any(k in name for k in ("logistic", "linear", "ridge", "lasso")):
        return "linear"
    try:
        import torch
        if isinstance(model, torch.nn.Module):
            return "deep"
    except ImportError:
        pass
    return "kernel"


def explain_shap(model, X: np.ndarray,
                  *, feature_names: list[str] | None = None,
                  model_type: str = "auto",
                  background: np.ndarray | None = None,
                  class_names: list[str] | None = None,
                  n_background: int = 100,
                  n_kernel_samples: int = 100) -> ShapResult:
    """SHAP degerlerini hesapla.

    Args:
        model:        sklearn / torch / xgboost / ... model
        X:            (N, F) numpy — aciklanacak ornekler
        feature_names: sutun isimleri (None ise 'f0'..'fN')
        model_type:   'auto' | 'tree' | 'linear' | 'deep' | 'kernel'
        background:   DeepExplainer / KernelExplainer icin arka plan set (n, F)
        class_names:  sinif isimleri (multiclass icin)
        n_background: background verilmezse X'ten kaç ornek se-cilsin (default 100)
        n_kernel_samples: KernelExplainer icin nsamples

    Returns:
        ShapResult(values, base_values, feature_names, model_type, class_names)
    """
    import shap
    if X.ndim == 1:
        X = X[None, :]
    N, F = X.shape
    if feature_names is None:
        feature_names = [f"f{i}" for i in range(F)]

    mtype = model_type if model_type != "auto" else _detect_type(model)

    if mtype == "tree":
        expl = shap.TreeExplainer(model)
        sv = expl.shap_values(X)
        # sklearn RF multiclass -> list of (N,F) her sinif icin
        if isinstance(sv, list):
            values = np.stack(sv, axis=-1)                # (N, F, C)
            base   = np.asarray(expl.expected_value)      # (C,)
            base_values = np.tile(base, (N, 1))
        else:
            values = np.asarray(sv)                        # (N, F) veya (N, F, C)
            base   = np.asarray(expl.expected_value)
            base_values = np.full(N, float(base)) if base.ndim == 0 else np.tile(base, (N, 1))
        return ShapResult(values, base_values, feature_names, "tree", class_names)

    if mtype == "linear":
        expl = shap.LinearExplainer(model, background if background is not None else X[:n_background])
        sv = expl.shap_values(X)
        return ShapResult(np.asarray(sv),
                           np.asarray(expl.expected_value),
                           feature_names, "linear", class_names)

    if mtype == "deep":
        import torch
        if background is None:
            # PEMF sertlestirmesi (2026-08-26): seed'siz np.random.choice ayni girdiye
            # farkli aciklama uretiyordu (klinik tekrarlanabilirlik) -> sabit tohum.
            idx = np.random.default_rng(0).choice(N, size=min(n_background, N), replace=False)
            background = X[idx]
        model.eval()
        # PEMF sertlestirmesi: deep yolu tensorleri CPU'da kurar; CUDA'daki modelle
        # device-mismatch SESSIZCE GradientExplainer'a dusuyordu -> acik hata.
        _dev = next(model.parameters()).device
        if _dev.type != "cpu":
            raise ValueError(
                f"shap deep yolu CPU-model varsayar; model {_dev} uzerinde. "
                "model.cpu() kopyasi verin veya model_type='kernel' kullanin.")
        bg_t = torch.from_numpy(background.astype(np.float32))
        X_t  = torch.from_numpy(X.astype(np.float32))
        try:
            expl = shap.DeepExplainer(model, bg_t)
        except Exception:
            # DeepExplainer bazi mimarilerde patlar -> GradientExplainer
            # PEMF sertlestirmesi: dusus artik SESSIZ DEGIL (hangi aciklayicinin
            # kullanildigi log'dan izlenebilir).
            _log.warning("shap DeepExplainer kurulamadi, GradientExplainer'a dusuluyor",
                         exc_info=True)
            expl = shap.GradientExplainer(model, bg_t)
        sv = expl.shap_values(X_t)
        if isinstance(sv, list):
            values = np.stack(sv, axis=-1)                 # (N, F, C)
            base = np.asarray(getattr(expl, "expected_value", 0.0))
            base_values = np.tile(base, (N, 1)) if base.ndim else np.zeros((N,))
        else:
            values = np.asarray(sv)
            base = np.asarray(getattr(expl, "expected_value", 0.0))
            base_values = np.full(N, float(base)) if base.ndim == 0 else np.tile(base, (N, 1))
        return ShapResult(values, base_values, feature_names, "deep", class_names)

    # kernel fallback
    def _predict(Xi):
        try:
            return model.predict_proba(Xi)
        except Exception:
            # PEMF sertlestirmesi (2026-08-26): dusus artik sessiz degil — gercek
            # hata (or. bozuk girdi) predict_proba yoklugu sanilip maskelenmesin.
            _log.debug("predict_proba kullanilamadi, predict'e dusuluyor", exc_info=True)
            return model.predict(Xi)
    # Determinizm: shap.sample + koalisyon orneklemesi global np.random kullanir;
    # cagri suresince seed(0), sonra DURUM GERI YUKLENIR.
    _rng_durum = np.random.get_state()
    try:
        np.random.seed(0)
        bg = background if background is not None else shap.sample(X, min(n_background, N))
        expl = shap.KernelExplainer(_predict, bg)
        sv = expl.shap_values(X, nsamples=n_kernel_samples)
    finally:
        np.random.set_state(_rng_durum)
    if isinstance(sv, list):
        values = np.stack(sv, axis=-1)
    else:
        values = np.asarray(sv)
    base_values = np.asarray(expl.expected_value)
    return ShapResult(values, base_values, feature_names, "kernel", class_names)
