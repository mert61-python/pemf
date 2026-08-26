#!/usr/bin/env python3
# Author: mertaygn, cglrgrkn
"""inference_human_kidney_disease.py — single-sample (or batch) inference for
the UCI-CKD classifier.

The training pipeline exports several ONNX checkpoints under this directory
together with a fitted preprocessor and the canonical feature-name list:

    CatBoost.onnx           best by bootstrap LogLoss; CatBoost-native ONNX
    ExtraTrees.onnx         best by aggregate CV LogLoss; skl2onnx export
    RandomForest.onnx       sklearn alternative
    LogisticRegression.onnx tiny baseline
    preprocessor.pkl        fitted ColumnTransformer
    feature_names.json      24 input feature names (numeric + categorical)
    best_model.txt          name of the default model

`predict_one(features)` accepts a raw dict whose keys match UCI CKD column
names (age, bp, sg, al, su, rbc, pc, pcc, ba, bgr, bu, sc, sod, pot, hemo,
pcv, wc, rc, htn, dm, cad, appet, pe, ane) and returns a {prob_ckd, label}
dict. Missing values may be passed as None and are imputed by the
preprocessor.

Use `predict_batch(records)` for batched inference; identical contract but
accepts a list of dicts or a pandas DataFrame.
"""
from __future__ import annotations

import json
import pickle
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import onnxruntime as ort
import pandas as pd

THIS_DIR = Path(__file__).resolve().parent

# UCI CKD column inventory — keep in sync with training/hkd_train_common.py.
NUMERIC = ["age", "bp", "sg", "al", "su",
           "bgr", "bu", "sc", "sod", "pot", "hemo", "pcv", "wc", "rc"]
CATEGORICAL = ["rbc", "pc", "pcc", "ba",
               "htn", "dm", "cad", "appet", "pe", "ane"]
ALL_FEATURES = NUMERIC + CATEGORICAL


# ===========================================================================
# Cached loader
# ===========================================================================
@lru_cache(maxsize=8)
def load_model(model_name: str | None = None):
    """Load preprocessor + ONNX session for `model_name`. If None, falls back
    to `best_model.txt`. Returns a tuple (preprocessor, session, input_name)."""
    if model_name is None:
        try:
            model_name = (THIS_DIR / "best_model.txt").read_text().strip()
        except FileNotFoundError as e:
            raise RuntimeError(
                f"best_model.txt missing at {THIS_DIR}. "
                "Run training/human_kidney_disease/export_onnx.py first."
            ) from e
    onnx_path = THIS_DIR / f"{model_name}.onnx"
    pre_path = THIS_DIR / "preprocessor.pkl"
    if not onnx_path.exists():
        raise FileNotFoundError(f"{onnx_path} missing — run export_onnx.py")
    if not pre_path.exists():
        raise FileNotFoundError(f"{pre_path} missing — run export_onnx.py")
    with open(pre_path, "rb") as f:
        pre = pickle.load(f)
    sess = ort.InferenceSession(str(onnx_path),
                                providers=["CPUExecutionProvider"])
    input_name = sess.get_inputs()[0].name
    return pre, sess, input_name


# ===========================================================================
# Public API
# ===========================================================================
def _normalise_record(rec: dict[str, Any]) -> dict[str, Any]:
    """Lowercase + strip categorical strings; cast numeric to float; pass
    None / '' / '?' through as NaN."""
    out: dict[str, Any] = {}
    for k in ALL_FEATURES:
        v = rec.get(k, None)
        if v is None or (isinstance(v, str) and v.strip() in ("", "?", "NA", "NaN", "nan")):
            out[k] = None
            continue
        if k in NUMERIC:
            try:
                out[k] = float(v)
            except (TypeError, ValueError):
                out[k] = None
        else:
            out[k] = str(v).strip().lower()
    return out


def _predict_onnx(sess: ort.InferenceSession, input_name: str,
                  Xp: np.ndarray) -> np.ndarray:
    outs = sess.run(None, {input_name: Xp.astype(np.float32)})
    probs = outs[-1]
    # Variant 1: list of {label: prob} dicts (CatBoost ONNX).
    if isinstance(probs, list) and probs and isinstance(probs[0], dict):
        return np.asarray([float(d.get(1, list(d.values())[-1])) for d in probs])
    arr = np.asarray(probs)
    if arr.ndim == 2 and arr.shape[1] == 2:
        return arr[:, 1]
    return arr.flatten()


def predict_one(features: dict[str, Any],
                model_name: str | None = None,
                threshold: float = 0.5) -> dict[str, Any]:
    """Single-patient inference.

    Parameters
    ----------
    features
        Mapping with keys among ALL_FEATURES. Missing keys are imputed by the
        training preprocessor.
    model_name
        ONNX checkpoint stem to use; defaults to best_model.txt.
    threshold
        Probability cut-off for the binary label.

    Returns
    -------
    dict
        {"prob_ckd": float, "label": "ckd"|"notckd", "model": str}
    """
    pre, sess, input_name = load_model(model_name)
    rec = _normalise_record(features)
    df = pd.DataFrame([rec], columns=ALL_FEATURES)
    Xp = pre.transform(df).astype(np.float32)
    prob = float(_predict_onnx(sess, input_name, Xp)[0])
    return {
        "prob_ckd": prob,
        "label": "ckd" if prob >= threshold else "notckd",
        "model": model_name or (THIS_DIR / "best_model.txt").read_text().strip(),
    }


def predict_batch(records: Iterable[dict[str, Any]] | pd.DataFrame,
                  model_name: str | None = None,
                  threshold: float = 0.5) -> pd.DataFrame:
    pre, sess, input_name = load_model(model_name)
    if isinstance(records, pd.DataFrame):
        recs = records[ALL_FEATURES].to_dict(orient="records")
    else:
        recs = list(records)
    df = pd.DataFrame([_normalise_record(r) for r in recs], columns=ALL_FEATURES)
    Xp = pre.transform(df).astype(np.float32)
    probs = _predict_onnx(sess, input_name, Xp)
    out = pd.DataFrame({"prob_ckd": probs})
    out["label"] = np.where(probs >= threshold, "ckd", "notckd")
    return out


def available_models() -> list[str]:
    return sorted(p.stem for p in THIS_DIR.glob("*.onnx"))


# ===========================================================================
# CLI smoke test
# ===========================================================================
# ===========================================================================
# XAI — sunum-katmani (Faz 1.4, 2026-08-26)
# ===========================================================================
def _preprocessor_feature_names(pre) -> list[str]:
    """ColumnTransformer'dan post-transform feature isimlerini cikart."""
    try:
        return list(pre.get_feature_names_out())
    except Exception:
        return [f"f{i}" for i in range(pre.transform(
            pd.DataFrame([{k: (0 if k in NUMERIC else "normal") for k in ALL_FEATURES}],
                          columns=ALL_FEATURES)).shape[1])]


def _aggregate_to_raw(shap_row: np.ndarray, post_names: list[str]) -> dict[str, float]:
    """Post-transform katkilari 24 HAM klinik ozellige topla.

    ColumnTransformer isim formati: numeric 'num__<col>', categorical 'cat__<col>_<val>'.
    """
    raw = {f: 0.0 for f in ALL_FEATURES}
    for name, val in zip(post_names, shap_row):
        if name.startswith("num__"):
            base = name[len("num__"):]
            if base in raw:
                raw[base] += float(val)
        elif name.startswith("cat__"):
            rest = name[len("cat__"):]
            for cand in ALL_FEATURES:
                if rest.startswith(cand + "_") or rest == cand:
                    raw[cand] += float(val)
                    break
        else:  # bilinmeyen format — kaba eslesme
            for cand in ALL_FEATURES:
                if cand in name:
                    raw[cand] += float(val)
                    break
    return raw


def _referans_background(post_names: list[str]) -> np.ndarray:
    """(1, F_post) 'ORTALAMA-HASTA' baseline'i.

    ⚠️ Gelen kodda tek-hasta DEJENERASYONU vardi (EM'dekiyle ayni sinif): background=
    kaydin KENDISI -> f(x)-E[f(bg)]=0 -> tum SHAP ~0. Burada referans egitim-oncesi
    donusum uzayindan turetilir: numeric kolonlar standardize (num__* -> 0.0 = egitim
    ortalamasi), one-hot kolonlar bilgisiz 0.5. Katkilar 'ortalama hastaya gore' okunur;
    deterministik, ek veri dosyasi gerektirmez.
    """
    return np.array([[0.0 if ad.startswith("num__") else 0.5 for ad in post_names]],
                     dtype=np.float32)


def xai_top_features(features: dict, top_n: int = 7,
                      model_name: str | None = None,
                      n_kernel_samples: int = 60) -> dict:
    """Tek hasta icin SHAP KernelExplainer top-N klinik ozellik katkisi (ONNX uzerinde).

    PT'siz XAI yolu: KernelExplainer model-agnostik predict-callable sarar (GPU gerekmez).
    Determinizm: koalisyon orneklemesi np.random kullanir -> cagri suresince seed(0),
    sonra GLOBAL DURUM GERI YUKLENIR. TEK-KAYNAK: router in-process + ai_service ayni
    fonksiyonu cagirir (kapi-paritesi dersi).

    Doner: {"prob_ckd", "top_features": [{"feature","attribution"}...], "baseline"}.
    """
    import shap

    pre, sess, input_name = load_model(model_name)
    df = pd.DataFrame([_normalise_record(features)], columns=ALL_FEATURES)
    Xp = pre.transform(df).astype(np.float32)

    def _proba(x):
        p = _predict_onnx(sess, input_name, x)
        return np.stack([1 - p, p], axis=1)

    post_names = _preprocessor_feature_names(pre)
    bg = _referans_background(post_names)

    _rng_durum = np.random.get_state()
    try:
        np.random.seed(0)
        expl = shap.KernelExplainer(_proba, bg)
        sv = expl.shap_values(Xp, nsamples=n_kernel_samples, silent=True)
    finally:
        np.random.set_state(_rng_durum)

    # ckd sinifinin katmani: List[(N,F)x2] (eski shap) veya (N,F,2) (yeni shap)
    if isinstance(sv, list):
        sv_ckd = np.asarray(sv[1])
    else:
        sv = np.asarray(sv)
        sv_ckd = sv[..., 1] if sv.ndim == 3 else sv

    raw = _aggregate_to_raw(sv_ckd[0], post_names)
    sirali = sorted(raw.items(), key=lambda kv: -abs(kv[1]))[: int(top_n)]
    return {
        "prob_ckd": float(_predict_onnx(sess, input_name, Xp)[0]),
        "top_features": [{"feature": f, "attribution": round(v, 4)} for f, v in sirali],
        "baseline": "ortalama_hasta",
    }


def _smoke() -> None:
    """Sanity check: pull 5 rows from the cleaned dataset, run inference on
    each available ONNX, compare to the ground truth."""
    DATA = (THIS_DIR.parent.parent
            / "dataset/human_kidney_disease/processed/ckd_clean.csv")
    if not DATA.exists():
        print(f"[skip] {DATA} missing"); return
    df = pd.read_csv(DATA).dropna(subset=["class"]).reset_index(drop=True)
    rng = np.random.default_rng(0)
    idx = rng.choice(len(df), size=5, replace=False)
    print(f"[info] available ONNX models: {available_models()}")
    for model_name in available_models():
        sub = df.iloc[idx].copy()
        out = predict_batch(sub[ALL_FEATURES], model_name=model_name)
        out["true"] = sub["class"].values
        print(f"\n--- {model_name} ---")
        print(out.to_string(index=False))


if __name__ == "__main__":
    print("[demo] Single patient")
    sample = {
        "age": 48, "bp": 80, "sg": 1.020, "al": 1, "su": 0,
        "rbc": "normal", "pc": "normal", "pcc": "notpresent", "ba": "notpresent",
        "bgr": 121, "bu": 36, "sc": 1.2, "sod": None, "pot": None,
        "hemo": 15.4, "pcv": 44, "wc": 7800, "rc": 5.2,
        "htn": "yes", "dm": "yes", "cad": "no",
        "appet": "good", "pe": "no", "ane": "no",
    }
    print(predict_one(sample))
    print("\n[demo] Batch + cross-model smoke test")
    _smoke()
