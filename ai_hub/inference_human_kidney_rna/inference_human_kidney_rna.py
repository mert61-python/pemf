#!/usr/bin/env python3
# Author: mertaygn, cglrgrkn
"""inference_human_kidney_rna.py - ONNX inference for the RCC RNA-seq classifier.

Loads the calibration-best ONNX model (selected on cross-validated mean Brier
score during training) and predicts KIRC vs rest for one or more patient
RNA-seq vectors. The model filename is read from ``best_model_meta.json`` so
the on-disk artifact name always matches the actual deployed model
(e.g. ``mlp_medium_kirc.onnx``), not a generic ``best_model.onnx`` placeholder.

Usage:
  python3 inference_human_kidney_rna.py --csv path/to/sample.csv
  python3 inference_human_kidney_rna.py --csv path/to/sample.csv --pytorch  # use the .pt fallback

The CSV must have the same gene columns as the training data. The first
column is the patient ID and is preserved verbatim in the output.

Expected files (written by training.py / export_best_real.py into this dir):
    <model_slug>_kirc.onnx     ONNX-converted classifier (deployed inference)
    <model_slug>_kirc.pt       PyTorch state_dict fallback (deep backbones)
    best_model_meta.json       {name, in_dim, onnx_file, torch_state_dict, ...}
    scaler.pkl                 StandardScaler fit on the full data
    feature_indices.npy        SelectKBest indices (post-scaling)
    classes.json               ordered class labels
    onnx_parity.json           max |delta proba| against the PyTorch model
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
META_PATH = HERE / "best_model_meta.json"
SCALER_PATH = HERE / "scaler.pkl"
FEATURE_IDX_PATH = HERE / "feature_indices.npy"
CLASSES_PATH = HERE / "classes.json"


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--csv", required=True,
                   help="Patient RNA-seq CSV (rows = patients, cols = genes).")
    p.add_argument("--out", default=None,
                   help="Output CSV path (default: predictions.csv next to script).")
    p.add_argument("--pytorch", action="store_true",
                   help="Force the PyTorch state_dict path even when an ONNX file exists.")
    return p.parse_args()


def _require(path: Path, label: str):
    if not path.exists():
        sys.exit(f"⚠  {label} not found at {path}\n"
                  f"   Run training.py + export_best_real.py to produce it.")


def _load_meta_and_aux():
    _require(META_PATH, "best_model_meta.json")
    _require(SCALER_PATH, "scaler.pkl")
    _require(FEATURE_IDX_PATH, "feature_indices.npy")
    _require(CLASSES_PATH, "classes.json")
    import joblib
    meta = json.loads(META_PATH.read_text(encoding="utf-8"))
    scaler = joblib.load(SCALER_PATH)
    fs_idx = np.load(FEATURE_IDX_PATH)
    classes = json.loads(CLASSES_PATH.read_text(encoding="utf-8"))
    return meta, scaler, fs_idx, classes


def _validate_columns(df: pd.DataFrame, expected_n_cols: int):
    if expected_n_cols and df.shape[1] != expected_n_cols:
        sys.exit(
            f"⚠  Input CSV column count mismatch:\n"
            f"   expected {expected_n_cols} gene columns "
            f"(from training data),\n"
            f"   got {df.shape[1]}.\n"
            f"   The gene-column order must match the training file exactly."
        )


def _softmax(z: np.ndarray) -> np.ndarray:
    z = z - z.max(axis=1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=1, keepdims=True)


def _outs_to_proba(outs) -> np.ndarray:
    """ONNX çıktı listesinden olasılık tensörünü çıkar (PyTorch logits / skl2onnx zipmap)."""
    # PyTorch export: a single 2-D logits tensor → softmax here.
    # skl2onnx export: [labels, probabilities_zipmap] → return the proba tensor.
    if len(outs) == 1 and isinstance(outs[0], np.ndarray) and outs[0].ndim == 2:
        return _softmax(outs[0])
    for arr in outs:
        if isinstance(arr, np.ndarray) and arr.ndim == 2 and arr.shape[1] >= 2:
            # Heuristic: probabilities sum to ~1.
            row_sum = arr.sum(axis=1)
            if np.allclose(row_sum, 1.0, atol=1e-3):
                return arr
    for arr in outs:
        if isinstance(arr, list):
            keys = sorted(arr[0].keys())
            return np.array([[row[k] for k in keys] for row in arr])
    # Fallback: first 2-D tensor through softmax.
    for arr in outs:
        if isinstance(arr, np.ndarray) and arr.ndim == 2:
            return _softmax(arr)
    raise RuntimeError("No probability tensor in ONNX outputs")


def _predict_proba_onnx(onnx_path: Path, X: np.ndarray) -> np.ndarray:
    import onnxruntime as ort
    sess = ort.InferenceSession(str(onnx_path),
                                  providers=["CPUExecutionProvider"])
    in_name = sess.get_inputs()[0].name
    out_names = [o.name for o in sess.get_outputs()]
    outs = sess.run(out_names, {in_name: X.astype(np.float32)})
    return _outs_to_proba(outs)


class KidneyRnaPredictor:
    """RNA-seq → KIRC/other (ONNX). Meta/scaler/ONNX'i bir kez yükler; cache'lenebilir.

    predict(df): df satır=hasta, sütun=20531 gen (eğitim sırası), index=hasta ID.
    -> [{patient_id, prediction, confidence, prob_<class>...}, ...]
    """

    def __init__(self):
        self.meta, self.scaler, self.fs_idx, self.classes = _load_meta_and_aux()
        onnx_path = HERE / self.meta.get("onnx_file", "")
        if not onnx_path.exists():
            raise FileNotFoundError(f"{onnx_path.name} bulunamadı: {onnx_path}")
        import onnxruntime as ort
        self._sess = ort.InferenceSession(str(onnx_path),
                                          providers=["CPUExecutionProvider"])
        self._in = self._sess.get_inputs()[0].name
        self._out_names = [o.name for o in self._sess.get_outputs()]
        self.expected_cols = int(getattr(self.scaler, "n_features_in_", 0))

    def predict(self, df: "pd.DataFrame") -> list:
        if self.expected_cols and df.shape[1] != self.expected_cols:
            raise ValueError(
                f"gen sütun sayısı uyuşmuyor: beklenen {self.expected_cols}, "
                f"gelen {df.shape[1]}")
        X = np.log2(df.values.astype(np.float32) + 1.0)
        X = self.scaler.transform(X)[:, self.fs_idx]
        probs = _outs_to_proba(
            self._sess.run(self._out_names, {self._in: X.astype(np.float32)}))
        classes = self.classes if probs.shape[1] == len(self.classes) \
            else [f"class_{i}" for i in range(probs.shape[1])]
        pred_idx = probs.argmax(axis=1)
        rows = []
        for i, pid in enumerate(df.index):
            row = {"patient_id": str(pid),
                   "prediction": classes[int(pred_idx[i])],
                   "confidence": float(probs[i].max())}
            for j, c in enumerate(classes):
                row[f"prob_{c}"] = float(probs[i, j])
            rows.append(row)
        return rows


def _predict_proba_pytorch(pt_path: Path, X: np.ndarray, in_dim: int,
                            n_classes: int) -> np.ndarray:
    import torch
    import torch.nn as nn

    # Reconstruct MLP-medium architecture (must match export_best_real.py).
    model = nn.Sequential(
        nn.Linear(in_dim, 256), nn.BatchNorm1d(256), nn.ReLU(), nn.Dropout(0.3),
        nn.Linear(256, 128), nn.BatchNorm1d(128), nn.ReLU(), nn.Dropout(0.3),
        nn.Linear(128, 64), nn.BatchNorm1d(64), nn.ReLU(),
        nn.Linear(64, 32), nn.ReLU(),
        nn.Linear(32, n_classes),
    )
    sd = torch.load(pt_path, map_location="cpu", weights_only=True)
    model.load_state_dict(sd)
    model.eval()
    with torch.no_grad():
        logits = model(torch.from_numpy(X.astype(np.float32)))
        probs = torch.softmax(logits, dim=1).numpy()
    return probs


def main():
    args = parse_args()

    csv_path = Path(args.csv)
    if not csv_path.exists():
        sys.exit(f"⚠  Input CSV not found: {csv_path}")

    meta, scaler, fs_idx, classes = _load_meta_and_aux()

    onnx_path = HERE / meta.get("onnx_file", "")
    pt_path = HERE / meta.get("torch_state_dict", "")

    use_onnx = onnx_path.exists() and not args.pytorch
    if not use_onnx and not pt_path.exists():
        sys.exit(f"⚠  Neither {onnx_path.name} nor {pt_path.name} is available. "
                  "Re-run training.py + export_best_real.py.")

    df = pd.read_csv(csv_path, index_col=0)

    expected_cols = int(getattr(scaler, "n_features_in_", df.shape[1]))
    _validate_columns(df, expected_cols)

    X = np.log2(df.values.astype(np.float32) + 1.0)
    X = scaler.transform(X)
    X = X[:, fs_idx]

    if use_onnx:
        probs = _predict_proba_onnx(onnx_path, X)
        backend = f"onnx:{onnx_path.name}"
    else:
        probs = _predict_proba_pytorch(pt_path, X, int(meta["in_dim"]),
                                         len(classes))
        backend = f"pytorch:{pt_path.name}"

    if probs.shape[1] != len(classes):
        classes = [f"class_{i}" for i in range(probs.shape[1])]

    pred_idx = probs.argmax(axis=1)
    out = pd.DataFrame({
        "patient_id": df.index,
        "prediction": [classes[i] for i in pred_idx],
        "confidence": probs.max(axis=1),
    })
    for i, c in enumerate(classes):
        out[f"prob_{c}"] = probs[:, i]

    out_path = Path(args.out) if args.out else (HERE / "predictions.csv")
    out.to_csv(out_path, index=False)
    print(f"[{backend}] model = {meta.get('name', '?')}  "
          f"input_dim = {X.shape[1]}  patients = {len(out)}")
    print(f"wrote {out_path}  ({len(out)} rows)")


if __name__ == "__main__":
    main()
