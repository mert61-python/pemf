# Human Kidney Disease — Inference

Single-sample inference for the UCI-CKD classifier.

## Files

The training pipeline exports an **ONNX zoo** (several checkpoints) into this directory
alongside a fitted preprocessor and metadata:

| File | Purpose |
|---|---|
| `inference_human_kidney_disease.py` | load preprocessor + ONNX session, run on a 24-feature dict |
| `CatBoost.onnx` | CatBoost-native ONNX export |
| `ExtraTrees.onnx` | skl2onnx export (current `best_model.txt` default) |
| `RandomForest.onnx` | sklearn alternative |
| `LogisticRegression.onnx` | tiny baseline |
| `preprocessor.pkl` | fitted `ColumnTransformer` (imputes missing → scale/encode) |
| `feature_names.json` | 24 input feature names (numeric + categorical) |
| `best_model.txt` | name of the default model (used when `model_name=None`) |
| `onnx_meta.json` | export metadata |

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
out = predict_one(features)           # default model from best_model.txt
# {'prob_ckd': 0.04, 'label': 'notckd', 'model': 'ExtraTrees'}
```

Missing values may be passed as `None` / `""` / `"?"` — the preprocessor imputes them.
Override the checkpoint with `predict_one(features, model_name="CatBoost")`.

Companion API:
- `predict_batch(records, model_name=None)` → `DataFrame` (accepts a list of dicts or a DataFrame).
- `available_models()` → list of ONNX stems in this directory.

Mirrors `inference/inference_em_fantom/`.
