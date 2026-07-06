# Human Kidney Disease — Inference

Single-sample inference for the UCI-CKD classifier.

## Files

| File | Purpose |
|---|---|
| `inference_human_kidney_disease.py` | load ONNX + scaler, run on a 24-feature dict |
| `<ModelName>.onnx` | exported deep checkpoint (filled in by `training/export_onnx.py`) |
| `<ModelName>.pth` | PyTorch state-dict snapshot (optional, for re-export) |
| `scaler_X.pkl` | fitted StandardScaler used at training time |

## Usage

```python
from inference_human_kidney_disease import predict_one

features = {
    "age": 48, "bp": 80,  "sg": 1.020, "al": 1, "su": 0,
    "rbc": "normal", "pc": "normal", "pcc": "notpresent", "ba": "notpresent",
    "bgr": 121, "bu": 36, "sc": 1.2, "sod": 137, "pot": 4.4,
    "hemo": 15.4, "pcv": 44, "wc": 7800, "rc": 5.2,
    "htn": "no", "dm": "no", "cad": "no",
    "appet": "good", "pe": "no", "ane": "no",
}
out = predict_one(features)
# {'prob_ckd': 0.04, 'label': 'notckd'}
```

Mirrors `inference/inference_em_fantom/`.
