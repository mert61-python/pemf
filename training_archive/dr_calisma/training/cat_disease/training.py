#!/usr/bin/env python3
"""
training_cat_disease.py — Cat Disease Multi-Class Classification Benchmark
==============================================================================
15 DL (MLP only: 5 Raw + 5 Normal + 5 Diamond) + 15 sklearn + 6 ensembles = 36

Input (36):  5 numeric + 1 gender + 9 binary symptoms + 5 extracted symptoms + 16 breed one-hot
Output (18): Disease_Prediction (18 balanced classes)

KEY DESIGN:
  - Dataset shuffled BEFORE split
  - Stratified split on Disease_Prediction (80/10/10)
  - DataLoader shuffle=True every epoch
  - StandardScaler on ALL features
  - CrossEntropyLoss, AdamW lr=0.001, batch 512
  - FP16 mixed precision, gradient clipping 1.0
"""

import sys
import time
import os
import gc
import json
import warnings
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.metrics import (accuracy_score, balanced_accuracy_score, f1_score,
    precision_score, recall_score, cohen_kappa_score, matthews_corrcoef,
    log_loss, roc_auc_score, confusion_matrix, classification_report)
from sklearn.tree import DecisionTreeClassifier
from sklearn.svm import SVC
from sklearn.ensemble import (ExtraTreesClassifier, HistGradientBoostingClassifier,
    RandomForestClassifier, BaggingClassifier, AdaBoostClassifier,
    GradientBoostingClassifier)
from sklearn.linear_model import LogisticRegression
from sklearn.neighbors import KNeighborsClassifier
from sklearn.naive_bayes import GaussianNB
from sklearn.neural_network import MLPClassifier
from xgboost import XGBClassifier
from lightgbm import LGBMClassifier
from catboost import CatBoostClassifier
from tabulate import tabulate
import joblib

warnings.filterwarnings("ignore")

# ============================================================
# Deterministic Seed
# ============================================================
SEED = 42
np.random.seed(SEED)
torch.manual_seed(SEED)
torch.cuda.manual_seed_all(SEED)
torch.backends.cudnn.deterministic = True
torch.backends.cudnn.benchmark = False

# ============================================================
# CONFIG
# ============================================================
DEVICE = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
MODELS_DIR = "/home/user02/dr/models_cat_disease"
CURVES_DIR = os.path.join(MODELS_DIR, "training_curves")

IN_DIM = 19   # 5 numeric (age,weight,hr,temp,duration) + 9 binary symptoms + 5 extracted
OUT_DIM = 18  # 18 disease classes
BS = 512
LR = 0.001
NUM_WORKERS = 4

EPOCH_MAP = {
    "Small": 500, "Medium": 500,
    "Large": 300, "XL": 200, "XXL": 200,
}

os.makedirs(MODELS_DIR, exist_ok=True)
os.makedirs(CURVES_DIR, exist_ok=True)


def _get_existing_csv_value(csv_path, model_name, column):
    try:
        if not os.path.exists(csv_path): return None
        import csv as _csv
        with open(csv_path) as f:
            reader = _csv.DictReader(f)
            for row in reader:
                if row.get("Model") == model_name:
                    v = row.get(column, "")
                    return float(v) if v else None
    except: pass
    return None


# ============================================================
# 1. Data Loading + Feature Engineering + Stratified Split
# ============================================================
print("=" * 80)
print(f"CAT DISEASE CLASSIFICATION — YUKLENIYOR... (Device: {DEVICE})")
print(f"IN_DIM={IN_DIM}, OUT_DIM={OUT_DIM}, BS={BS}, LR={LR}")
print("=" * 80)

CSV_PATH = "/home/user02/dr/dataset/cat_disease/synthetic_cat_disease_100000.csv"
df = pd.read_csv(CSV_PATH)
print(f"Ham satir sayisi: {len(df):,}")
print(f"Kolon sayisi: {len(df.columns)}")

# ---- Step 1: DATASET-LEVEL SHUFFLE ----
print("\n[Shuffle] Dataset-level shuffle (frac=1, seed=42)...")
df = df.sample(frac=1, random_state=SEED).reset_index(drop=True)

# ---- Step 2: Feature Engineering ----
print("\n[Feature Engineering]")

# 2a. Numeric features (5: age, weight, heart_rate, body_temp, duration)
df["Body_Temperature"] = df["Body_Temperature"].astype(str).str.replace("°C", "", regex=False).astype(float)

def parse_duration(val):
    val = str(val).strip().lower()
    if "month" in val:
        return int(val.split()[0]) * 30
    elif "week" in val:
        return int(val.split()[0]) * 7
    elif "day" in val:
        return int(val.split()[0])
    try: return int(val)
    except: return 0

df["Duration_days"] = df["Duration"].apply(parse_duration)
numeric_cols = ["Age", "Weight", "Heart_Rate", "Body_Temperature", "Duration_days"]
print(f"  Numeric (5): {numeric_cols}")

# 2b. Binary symptoms (9) — Lameness geri eklendi (Calicivirus %70)
binary_symptom_cols = ["Appetite_Loss", "Vomiting", "Diarrhea", "Coughing",
                       "Labored_Breathing", "Lameness", "Skin_Lesions",
                       "Nasal_Discharge", "Eye_Discharge"]
for col in binary_symptom_cols:
    df[col + "_bin"] = (df[col] == "Yes").astype(int)
binary_symptom_bin_cols = [c + "_bin" for c in binary_symptom_cols]
print(f"  Binary symptoms (8): {binary_symptom_cols}")

# 2c. Extracted symptoms from Symptom_1-4 (5 binary)
extracted_symptoms = ["Lethargy", "Weight Loss", "Sneezing", "Dehydration", "Fever"]
symptom_cols = ["Symptom_1", "Symptom_2", "Symptom_3", "Symptom_4"]
for sym in extracted_symptoms:
    col_name = f"has_{sym.replace(' ', '_')}"
    df[col_name] = 0
    for sc in symptom_cols:
        df[col_name] = df[col_name] | df[sc].astype(str).str.contains(sym, case=False, na=False).astype(int)
extracted_bin_cols = [f"has_{s.replace(' ', '_')}" for s in extracted_symptoms]
print(f"  Extracted symptoms (5): {extracted_symptoms}")

# CIKARILAN (MI ≈ 0, bilgi tasimiyor):
# Breed (16 one-hot, Chi-sq p=0.27), Gender (MI=0.003), Age (MI=0.005),
# Weight (MI=0.005), Duration (MI=0.003), Lameness (MI=0.009)
print(f"  CIKARILAN: Breed, Gender (MI=0)")

# 2f. Target: LabelEncoder
le = LabelEncoder()
df["target"] = le.fit_transform(df["Disease_Prediction"])
print(f"  Classes ({len(le.classes_)}): {list(le.classes_)}")
print(f"  Target dagilimi:\n{df['target'].value_counts().sort_index()}")

# Save label encoder
joblib.dump(le, os.path.join(MODELS_DIR, "label_encoder.pkl"))
print(f"  -> label_encoder.pkl")

# ---- Build X and y ----
feature_cols = numeric_cols + binary_symptom_bin_cols + extracted_bin_cols
assert len(feature_cols) == IN_DIM, f"Feature count mismatch: {len(feature_cols)} != {IN_DIM}"

X_raw = df[feature_cols].values.astype(np.float32)
y_raw = df["target"].values.astype(np.int64)
print(f"\nX_raw shape: {X_raw.shape} | y_raw shape: {y_raw.shape}")
print(f"Feature columns ({len(feature_cols)}): {feature_cols}")

# ---- Step 3: STRATIFIED SPLIT on Disease_Prediction (80/10/10) ----
print("\n[Stratified Split] 80/10/10 on Disease_Prediction")
idx_all = np.arange(len(df))

idx_tv, idx_test = train_test_split(
    idx_all, test_size=0.10, random_state=SEED, stratify=y_raw
)
idx_train, idx_val = train_test_split(
    idx_tv, test_size=1/9, random_state=SEED, stratify=y_raw[idx_tv]
)

print(f"Train: {len(idx_train):,} | Val: {len(idx_val):,} | Test: {len(idx_test):,}")

X_train_raw = X_raw[idx_train]; X_val_raw = X_raw[idx_val]; X_test_raw = X_raw[idx_test]
y_train = y_raw[idx_train]; y_val = y_raw[idx_val]; y_test = y_raw[idx_test]

print(f"Train class distribution: {dict(zip(*np.unique(y_train, return_counts=True)))}")

# ============================================================
# 2. Scaling (StandardScaler on ALL features)
# ============================================================
scaler_X = StandardScaler()
X_train_sc = scaler_X.fit_transform(X_train_raw).astype(np.float32)
X_val_sc = scaler_X.transform(X_val_raw).astype(np.float32)
X_test_sc = scaler_X.transform(X_test_raw).astype(np.float32)

joblib.dump(scaler_X, os.path.join(MODELS_DIR, "scaler_X.pkl"))
print(f"\nScaler -> models_cat_disease/scaler_X.pkl")

# ============================================================
# 3. DataLoader
# ============================================================
train_ds = TensorDataset(torch.FloatTensor(X_train_sc), torch.LongTensor(y_train))
val_ds = TensorDataset(torch.FloatTensor(X_val_sc), torch.LongTensor(y_val))
test_ds = TensorDataset(torch.FloatTensor(X_test_sc), torch.LongTensor(y_test))

train_loader = DataLoader(train_ds, batch_size=BS, shuffle=True, num_workers=NUM_WORKERS, pin_memory=True)
val_loader = DataLoader(val_ds, batch_size=BS, shuffle=False, num_workers=NUM_WORKERS, pin_memory=True)
test_loader = DataLoader(test_ds, batch_size=BS, shuffle=False, num_workers=NUM_WORKERS, pin_memory=True)

# Ensemble/Stacking probability storage
all_test_probs = {}   # model_name -> (N_test, 18) probabilities
all_val_probs = {}    # model_name -> (N_val, 18) probabilities

# ============================================================
# 4. Model Architecture — MLP only
# ============================================================
class MLPModel(nn.Module):
    def __init__(self, layers, dropout=0.2, out_dim=OUT_DIM, in_dim=IN_DIM):
        super().__init__()
        mods = []
        for o in layers:
            mods.append(nn.Linear(in_dim, o))
            if dropout > 0: mods.append(nn.BatchNorm1d(o))
            mods.append(nn.ReLU())
            if dropout > 0: mods.append(nn.Dropout(dropout))
            in_dim = o
        mods.append(nn.Linear(in_dim, out_dim))  # logits, NO softmax
        self.net = nn.Sequential(*mods)

    def forward(self, x):
        return self.net(x)


# ============================================================
# 5. Metrics
# ============================================================
def compute_metrics(y_true, y_pred, y_prob):
    """
    y_true: (N,) int labels
    y_pred: (N,) int predicted labels
    y_prob: (N, 18) predicted probabilities
    """
    acc = accuracy_score(y_true, y_pred)
    bal_acc = balanced_accuracy_score(y_true, y_pred)
    f1_mac = f1_score(y_true, y_pred, average='macro')
    f1_wt = f1_score(y_true, y_pred, average='weighted')
    prec_mac = precision_score(y_true, y_pred, average='macro')
    prec_wt = precision_score(y_true, y_pred, average='weighted')
    rec_mac = recall_score(y_true, y_pred, average='macro')
    rec_wt = recall_score(y_true, y_pred, average='weighted')
    kappa = cohen_kappa_score(y_true, y_pred)
    mcc = matthews_corrcoef(y_true, y_pred)
    ll = log_loss(y_true, y_prob)

    # Top-2 and Top-3 accuracy
    top2 = np.mean([y_true[i] in np.argsort(y_prob[i])[-2:] for i in range(len(y_true))])
    top3 = np.mean([y_true[i] in np.argsort(y_prob[i])[-3:] for i in range(len(y_true))])

    # ROC AUC (one-vs-rest)
    try:
        roc_mac = roc_auc_score(y_true, y_prob, multi_class='ovr', average='macro')
        roc_wt = roc_auc_score(y_true, y_prob, multi_class='ovr', average='weighted')
    except:
        roc_mac = roc_wt = float('nan')

    # Specificity (macro) = mean of TNR per class
    cm = confusion_matrix(y_true, y_pred)
    specs = []
    for i in range(cm.shape[0]):
        tn = cm.sum() - cm[i, :].sum() - cm[:, i].sum() + cm[i, i]
        fp = cm[:, i].sum() - cm[i, i]
        specs.append(tn / (tn + fp) if (tn + fp) > 0 else 0)
    spec_mac = np.mean(specs)

    return {
        "Accuracy": acc,
        "Balanced_Accuracy": bal_acc,
        "F1_macro": f1_mac,
        "F1_weighted": f1_wt,
        "Precision_macro": prec_mac,
        "Precision_weighted": prec_wt,
        "Recall_macro": rec_mac,
        "Recall_weighted": rec_wt,
        "Specificity_macro": spec_mac,
        "Cohen_Kappa": kappa,
        "MCC": mcc,
        "Log_Loss": ll,
        "Top2_Accuracy": top2,
        "Top3_Accuracy": top3,
        "ROC_AUC_macro": roc_mac,
        "ROC_AUC_weighted": roc_wt,
    }


# ============================================================
# 6. CSV
# ============================================================
_CSV = os.path.join(MODELS_DIR, "model_cat_disease_karsilastirma.csv")

CSV_COLS = ["Model", "Accuracy", "Balanced_Accuracy", "F1_macro", "F1_weighted",
            "Precision_macro", "Precision_weighted", "Recall_macro", "Recall_weighted",
            "Specificity_macro", "Cohen_Kappa", "MCC", "Log_Loss", "Top2_Accuracy", "Top3_Accuracy",
            "ROC_AUC_macro", "ROC_AUC_weighted",
            "Train_Time(s)", "Best_Epoch", "Best_Val_Loss",
            "Inference_Time(s)", "Throughput_samples_s", "Params", "ModelSize_MB", "Epochs"]

def _load_existing_csv():
    if os.path.exists(_CSV):
        try: return pd.read_csv(_CSV)
        except: return pd.DataFrame()
    return pd.DataFrame()

def _model_in_csv(model_name):
    existing = _load_existing_csv()
    if existing.empty: return False
    return model_name in existing["Model"].values

_hdr_written = os.path.exists(_CSV) and os.path.getsize(_CSV) > 0

def save_inc(rows):
    global _hdr_written
    d = pd.DataFrame(rows)
    for c in CSV_COLS:
        if c not in d.columns: d[c] = 0
    d = d[CSV_COLS]
    if not _hdr_written:
        d.to_csv(_CSV, index=False, mode="w"); _hdr_written = True
    else:
        existing = _load_existing_csv()
        if not existing.empty:
            d = d[~d["Model"].isin(existing["Model"].values)]
        if not d.empty:
            d.to_csv(_CSV, index=False, mode="a", header=False)


def mrow(name, m, train_time=0.0, inf_time=0.0, throughput=0.0,
         params=0, model_size_mb=0.0, epochs=0,
         best_epoch=0, best_val_loss=0.0):
    """Build CSV row from a metrics dict + training info."""
    row = {"Model": name}
    for k in ["Accuracy", "Balanced_Accuracy", "F1_macro", "F1_weighted",
              "Precision_macro", "Precision_weighted", "Recall_macro", "Recall_weighted",
              "Specificity_macro", "Cohen_Kappa", "MCC", "Log_Loss", "Top2_Accuracy", "Top3_Accuracy",
              "ROC_AUC_macro", "ROC_AUC_weighted"]:
        row[k] = m.get(k, float("nan"))
    row["Train_Time(s)"] = train_time
    row["Best_Epoch"] = best_epoch
    row["Best_Val_Loss"] = best_val_loss
    row["Inference_Time(s)"] = inf_time
    row["Throughput_samples_s"] = throughput
    row["Params"] = params
    row["ModelSize_MB"] = model_size_mb
    row["Epochs"] = epochs
    return row


def nan_metrics():
    """Return a metrics dict filled with NaN (for failed models)."""
    return {k: float("nan") for k in [
        "Accuracy", "Balanced_Accuracy", "F1_macro", "F1_weighted",
        "Precision_macro", "Precision_weighted", "Recall_macro", "Recall_weighted",
        "Specificity_macro", "Cohen_Kappa", "MCC", "Log_Loss", "Top2_Accuracy", "Top3_Accuracy",
        "ROC_AUC_macro", "ROC_AUC_weighted"]}


# ============================================================
# 7. Utility functions
# ============================================================
def count_parameters(model):
    return sum(p.numel() for p in model.parameters() if p.requires_grad)

def reset_gpu_memory_tracking():
    if torch.cuda.is_available():
        torch.cuda.reset_peak_memory_stats(DEVICE)

def get_gpu_memory_mb():
    if torch.cuda.is_available():
        return torch.cuda.max_memory_allocated(DEVICE) / (1024 * 1024)
    return 0.0

def file_size_mb(path):
    try:
        return os.path.getsize(path) / (1024 * 1024)
    except: return 0.0

def measure_inference_latency(model, loader, device, n_samples):
    model.eval()
    sample_batch = next(iter(loader))[0].to(device)
    with torch.no_grad(), torch.cuda.amp.autocast():
        for _ in range(3): _ = model(sample_batch)
        if torch.cuda.is_available(): torch.cuda.synchronize()
        times = []
        for _ in range(10):
            t0 = time.time()
            for xb, _ in loader:
                _ = model(xb.to(device, non_blocking=True))
            if torch.cuda.is_available(): torch.cuda.synchronize()
            times.append(time.time() - t0)
    mean_t = float(np.mean(times))
    throughput = n_samples / mean_t if mean_t > 0 else 0.0
    return mean_t, throughput


# ============================================================
# 8. DL Training
# ============================================================
per_class_metrics_rows = []

def train_dl(cfg, name, epochs):
    pt_path = os.path.join(MODELS_DIR, f"{name}.pt")
    mdl = MLPModel(cfg["layers"], cfg["dropout"], OUT_DIM, IN_DIM).to(DEVICE)
    n_params = count_parameters(mdl)

    ckpt_path = os.path.join(MODELS_DIR, f"{name}.ckpt")

    if os.path.exists(pt_path):
        print(f"    Mevcut model yukleniyor (skip)...", flush=True)
        mdl.load_state_dict(torch.load(pt_path, map_location=DEVICE)); mdl.eval()
        _csv_tt = _get_existing_csv_value(_CSV, name, "Train_Time(s)")
        tt = _csv_tt if _csv_tt is not None else 0.0
        bv = _get_existing_csv_value(_CSV, name, "Best_Val_Loss") or 0.0
        best_epoch_ = int(_get_existing_csv_value(_CSV, name, "Best_Epoch") or 0)
    else:
        scaler_amp = torch.cuda.amp.GradScaler(enabled=True)
        opt = torch.optim.AdamW(mdl.parameters(), lr=LR, weight_decay=1e-4)
        crit = nn.CrossEntropyLoss()

        bv, bs_ = float("inf"), None
        best_epoch_ = 0
        no_improve_count = 0
        curve_data = []
        start_epoch = 1
        elapsed_prev = 0.0

        # --- Epoch-level checkpoint resume ---
        if os.path.exists(ckpt_path):
            try:
                ckpt = torch.load(ckpt_path, map_location=DEVICE)
                mdl.load_state_dict(ckpt["model_state"])
                opt.load_state_dict(ckpt["opt_state"])
                if "scaler_state" in ckpt and ckpt["scaler_state"] is not None:
                    try: scaler_amp.load_state_dict(ckpt["scaler_state"])
                    except: pass
                bv = ckpt.get("bv", float("inf"))
                best_epoch_ = ckpt.get("best_epoch", 0)
                curve_data = ckpt.get("curve_data", [])
                bs_ = ckpt.get("best_state", None)
                start_epoch = ckpt.get("epoch", 0) + 1
                elapsed_prev = ckpt.get("elapsed_total", 0.0)
                print(f"    >>> CHECKPOINT yuklendi: epoch {start_epoch-1}/{epochs}, "
                      f"bv={bv:.8f}, elapsed={elapsed_prev:.0f}s", flush=True)
            except Exception as e:
                print(f"    Checkpoint HATA ({str(e)[:80]}), bastan basliyor")
                start_epoch = 1; elapsed_prev = 0.0; curve_data = []
                bv = float("inf"); bs_ = None; best_epoch_ = 0; no_improve_count = 0

        print(f"    Egitim (params: {n_params:,}, epochs: {start_epoch}..{epochs}, "
              f"lr: {LR}, bs: {BS})"
              f"{' [RESUMED]' if start_epoch > 1 else ''}...", flush=True)
        reset_gpu_memory_tracking()

        CKPT_EVERY = 50
        t0 = time.time()

        for ep in range(start_epoch, epochs + 1):
            mdl.train(); tl_ = 0
            for xb, yb in train_loader:
                xb = xb.to(DEVICE, non_blocking=True)
                yb = yb.to(DEVICE, non_blocking=True)
                opt.zero_grad()
                with torch.cuda.amp.autocast(enabled=True):
                    logits = mdl(xb)
                    l = crit(logits, yb)
                scaler_amp.scale(l).backward()
                scaler_amp.unscale_(opt)
                torch.nn.utils.clip_grad_norm_(mdl.parameters(), max_norm=1.0)
                scaler_amp.step(opt); scaler_amp.update()
                tl_ += l.item() * len(xb)
            tl_ /= len(train_ds)

            mdl.eval(); vl_ = 0
            with torch.no_grad(), torch.cuda.amp.autocast(enabled=True):
                for xb, yb in val_loader:
                    xb = xb.to(DEVICE, non_blocking=True)
                    yb = yb.to(DEVICE, non_blocking=True)
                    vl_ += crit(mdl(xb), yb).item() * len(xb)
            vl_ /= len(val_ds)

            curve_data.append({"epoch": ep, "train_loss": tl_, "val_loss": vl_})

            if ep % 50 == 0 or ep == 1 or ep == start_epoch:
                print(f"    Ep {ep:4d}/{epochs} | T: {tl_:.6f} | V: {vl_:.6f}", flush=True)

            if vl_ < bv:
                bv = vl_
                best_epoch_ = ep
                no_improve_count = 0
                bs_ = {k: v.clone() for k, v in mdl.state_dict().items()}
            else:
                no_improve_count += 1

            # Early stopping (patience=50)
            if no_improve_count >= 50:
                print(f"    Early stopping at ep {ep} (no improve for 50 epochs, best={best_epoch_})")
                break

            # Periodic checkpoint
            if ep % CKPT_EVERY == 0 and ep < epochs:
                try:
                    elapsed_now = elapsed_prev + (time.time() - t0)
                    torch.save({
                        "epoch": ep,
                        "model_state": mdl.state_dict(),
                        "opt_state": opt.state_dict(),
                        "scaler_state": scaler_amp.state_dict(),
                        "bv": bv, "best_epoch": best_epoch_,
                        "curve_data": curve_data,
                        "best_state": bs_,
                        "elapsed_total": elapsed_now,
                    }, ckpt_path + ".tmp")
                    os.replace(ckpt_path + ".tmp", ckpt_path)
                except Exception as e:
                    print(f"    Ckpt save HATA: {str(e)[:80]}")

        tt = elapsed_prev + (time.time() - t0)

        # Tamamlandi — checkpoint'i sil
        if os.path.exists(ckpt_path):
            try: os.remove(ckpt_path)
            except: pass

        if curve_data:
            pd.DataFrame(curve_data).to_csv(
                os.path.join(CURVES_DIR, f"{name}.csv"), index=False)

        if bs_ is None:
            print(f"    UYARI: Model ogrenemedi (NaN)")
            del mdl; torch.cuda.empty_cache()
            return [mrow(name, nan_metrics(), train_time=tt, inf_time=0, throughput=0,
                         params=n_params, model_size_mb=0, epochs=epochs,
                         best_epoch=0, best_val_loss=float("nan"))]

        mdl.load_state_dict(bs_); mdl.eval()
        torch.save(bs_, pt_path)

    # --- Evaluation ---
    it, throughput = measure_inference_latency(mdl, test_loader, DEVICE, len(test_ds))
    model_size_mb = file_size_mb(pt_path)

    # Test predictions
    test_logits_list = []
    with torch.no_grad(), torch.cuda.amp.autocast():
        for xb, _ in test_loader:
            test_logits_list.append(mdl(xb.to(DEVICE, non_blocking=True)).cpu())
    test_logits = torch.cat(test_logits_list, dim=0)
    test_probs = torch.softmax(test_logits, dim=1).numpy()
    test_preds = test_probs.argmax(axis=1)

    # Val predictions
    val_logits_list = []
    with torch.no_grad(), torch.cuda.amp.autocast():
        for xb, _ in val_loader:
            val_logits_list.append(mdl(xb.to(DEVICE, non_blocking=True)).cpu())
    val_logits = torch.cat(val_logits_list, dim=0)
    val_probs = torch.softmax(val_logits, dim=1).numpy()

    # Store for ensemble
    all_test_probs[name] = test_probs
    all_val_probs[name] = val_probs

    m = compute_metrics(y_test, test_preds, test_probs)
    print(f"  Acc:{m['Accuracy']:.4f} | BalAcc:{m['Balanced_Accuracy']:.4f} | "
          f"F1m:{m['F1_macro']:.4f} | Kappa:{m['Cohen_Kappa']:.4f} | "
          f"LogLoss:{m['Log_Loss']:.4f} | {tt:.1f}s")

    del mdl; torch.cuda.empty_cache()

    return [mrow(name, m, train_time=tt, inf_time=it, throughput=throughput,
                 params=n_params, model_size_mb=model_size_mb, epochs=epochs,
                 best_epoch=best_epoch_, best_val_loss=bv)]


# ============================================================
# 9. Model Configurations (15 MLP)
# ============================================================
split_models = {
    # Normal (dropout=0.2) — 5
    "MLP_Small":  {"layers": [128, 64], "dropout": 0.2},
    "MLP_Medium": {"layers": [256, 128, 64], "dropout": 0.2},
    "MLP_Large":  {"layers": [512, 256, 128, 64], "dropout": 0.2},
    "MLP_XL":     {"layers": [512, 512, 256, 128], "dropout": 0.2},
    "MLP_XXL":    {"layers": [1024, 512, 256, 128], "dropout": 0.2},
    # Diamond (dropout=0.0) — 5
    "MLP_diamond_Small":  {"layers": [64, 128, 128, 64, 32], "dropout": 0.0},
    "MLP_diamond_Medium": {"layers": [128, 256, 256, 128, 64], "dropout": 0.0},
    "MLP_diamond_Large":  {"layers": [256, 512, 512, 256, 128], "dropout": 0.0},
    "MLP_diamond_XL":     {"layers": [384, 768, 768, 384, 192], "dropout": 0.0},
    "MLP_diamond_XXL":    {"layers": [512, 1024, 1024, 512, 256], "dropout": 0.0},
}


# ============================================================
# 10. DL Training Loop
# ============================================================
results = []

print(f"\n{'='*80}\nEGITIM - {len(split_models)} DL MODELS")
print(f"Config: IN_DIM={IN_DIM}, OUT_DIM={OUT_DIM}, BS={BS}, LR={LR}, AdamW, CrossEntropyLoss")
print(f"{'='*80}")

for i, (nm, cfg) in enumerate(split_models.items(), 1):
    parts = nm.replace("_Raw", "").replace("diamond_", "").split("_")
    size = parts[-1] if parts[-1] in EPOCH_MAP else "Medium"
    epochs = EPOCH_MAP.get(size, 500)
    pt_exists = os.path.exists(os.path.join(MODELS_DIR, f"{nm}.pt"))
    in_csv = _model_in_csv(nm)
    if in_csv and pt_exists:
        print(f"\n[{i:3d}/{len(split_models)}] {nm} - mevcut, evaluate...", end=" ", flush=True)
        r = train_dl(cfg, nm, epochs); results.extend(r)
    elif pt_exists and not in_csv:
        print(f"\n[{i:3d}/{len(split_models)}] {nm} - .pt mevcut, evaluate+save\n" + "-" * 50)
        sys.stdout.flush()
        r = train_dl(cfg, nm, epochs); results.extend(r); save_inc(r)
    else:
        print(f"\n[{i:3d}/{len(split_models)}] {nm} - MLP ({epochs} epochs)\n" + "-" * 50)
        sys.stdout.flush()
        r = train_dl(cfg, nm, epochs); results.extend(r); save_inc(r)


# ============================================================
# 11. Sklearn (15 models)
# ============================================================
sk_models = {
    "XGBoost": XGBClassifier(n_estimators=500, max_depth=10, learning_rate=0.05,
                              tree_method="hist", device="cuda:0", random_state=42,
                              n_jobs=-1, eval_metric="mlogloss"),
    "ExtraTrees": ExtraTreesClassifier(n_estimators=200, max_depth=20,
                                        random_state=42, n_jobs=-1),
    "RandomForest": RandomForestClassifier(n_estimators=200, max_depth=20,
                                            random_state=42, n_jobs=-1),
    "DecisionTree": DecisionTreeClassifier(max_depth=25, random_state=42),
    "Bagging": BaggingClassifier(n_estimators=100, max_samples=0.8,
                                  random_state=42, n_jobs=-1),
    "LogisticRegression": LogisticRegression(max_iter=2000, random_state=42,
                                              n_jobs=-1, multi_class="multinomial"),
    "KNeighbors": KNeighborsClassifier(n_neighbors=5, n_jobs=-1),
    "GaussianNB": GaussianNB(),
    "HistGradientBoosting": HistGradientBoostingClassifier(max_iter=500, max_depth=12,
                                                            learning_rate=0.05, random_state=42),
}
# NOT: LightGBM, CatBoost, GradientBoosting, SVC, MLPClassifier cikarildi (yavas)

sk_list = list(sk_models.keys())

print(f"\n{'='*80}\nSKLEARN - {len(sk_list)} MODEL\n{'='*80}")

for i, nm in enumerate(sk_list, 1):
    print(f"\n[{i:2d}/{len(sk_list)}] {nm}\n" + "-" * 50); sys.stdout.flush()
    pkl_path = os.path.join(MODELS_DIR, f"{nm}.pkl")

    if os.path.exists(pkl_path):
        print(f"    Mevcut model yukleniyor (skip training)...", flush=True)
        m = joblib.load(pkl_path)
        tt = _get_existing_csv_value(_CSV, nm, "Train_Time(s)") or 0.0
    else:
        print(f"    Egitim...", flush=True)
        m = sk_models[nm]
        try:
            t0 = time.time()
            m.fit(X_train_sc, y_train)
            tt = time.time() - t0
            joblib.dump(m, pkl_path)
        except Exception as e:
            print(f"    HATA: {str(e)[:120]} - model atlaniyor", flush=True)
            continue

    # Warmup
    _ = m.predict(X_test_sc[:100])
    _ = m.predict(X_test_sc[:100])
    _ = m.predict(X_test_sc[:100])

    # Inference timing
    times_sk = []
    for _ in range(10):
        t1 = time.time(); _ = m.predict(X_test_sc); times_sk.append(time.time() - t1)
    it = float(np.mean(times_sk))
    throughput_sk = len(X_test_sc) / it if it > 0 else 0.0
    sk_size_mb = file_size_mb(pkl_path)

    # Param count approx
    try:
        n_params_sk = int(sum(getattr(v, 'size', 0) for v in m.__dict__.values()
                              if hasattr(v, 'size')))
    except: n_params_sk = 0

    # Predictions
    test_preds_sk = m.predict(X_test_sc)
    test_probs_sk = m.predict_proba(X_test_sc)
    val_probs_sk = m.predict_proba(X_val_sc)

    # Store for ensemble
    all_test_probs[nm] = test_probs_sk
    all_val_probs[nm] = val_probs_sk

    met = compute_metrics(y_test, test_preds_sk, test_probs_sk)
    print(f"  Acc:{met['Accuracy']:.4f} | BalAcc:{met['Balanced_Accuracy']:.4f} | "
          f"F1m:{met['F1_macro']:.4f} | Kappa:{met['Cohen_Kappa']:.4f} | "
          f"LogLoss:{met['Log_Loss']:.4f} | {tt:.1f}s | {throughput_sk:.0f} s/s")

    row = mrow(nm, met, train_time=tt, inf_time=it, throughput=throughput_sk,
               params=n_params_sk, model_size_mb=sk_size_mb, epochs=0)
    results.append(row); save_inc([row])
    print(f"    OK ({tt:.1f}s)", flush=True)
    del m; gc.collect()


# ============================================================
# 12. Ensemble & Stacking
# ============================================================
print(f"\n{'='*80}\nENSEMBLE & STACKING\n{'='*80}")

all_model_results = sorted(results,
    key=lambda x: x.get("Accuracy", 0) if not np.isnan(x.get("Accuracy", 0)) else -1,
    reverse=True)

# SK Top 5
sk_results = [r for r in all_model_results if r["Model"] in sk_list]
top5_sk_names = [r["Model"] for r in sk_results[:5]]

# DL Top 5
dl_exclude = set(sk_list)
dl_results = [r for r in all_model_results
              if r["Model"] not in dl_exclude
              and "Ensemble" not in r["Model"] and "Stacking" not in r["Model"]]
top5_dl_names = [r["Model"] for r in dl_results[:5]]

# All Top 5
top5_all_names = [r["Model"] for r in all_model_results[:5]]

print(f"SK  Top 5: {top5_sk_names}")
print(f"DL  Top 5: {top5_dl_names}")
print(f"All Top 5: {top5_all_names}")

ens_rl = []
for group_name, top_names in [("SK_Top5", top5_sk_names),
                               ("DL_Top5", top5_dl_names),
                               ("All_Top5", top5_all_names)]:
    for method, label in [("mean", f"Ensemble_{group_name}"),
                          ("stacking", f"Stacking_{group_name}")]:
        avail = [n for n in top_names if n in all_test_probs]
        if len(avail) < 2:
            print(f"  {label}: yeterli tahmin yok ({len(avail)})"); continue

        if method == "mean":
            # Probability averaging -> argmax
            ens_probs = np.mean(np.stack([all_test_probs[n] for n in avail]), axis=0)
            ens_preds = ens_probs.argmax(axis=1)
        else:
            # Stacking: LogisticRegression meta-learner on val predictions
            avail_v = [n for n in avail if n in all_val_probs]
            if len(avail_v) < 2:
                print(f"  {label}: yeterli val tahmin yok"); continue
            # Stack val probabilities as features
            val_feats = np.hstack([all_val_probs[n] for n in avail_v])
            test_feats = np.hstack([all_test_probs[n] for n in avail_v])
            meta = LogisticRegression(max_iter=2000, random_state=SEED,
                                       multi_class="multinomial", n_jobs=-1)
            meta.fit(val_feats, y_val)
            ens_probs = meta.predict_proba(test_feats)
            ens_preds = meta.predict(test_feats)

        ens_met = compute_metrics(y_test, ens_preds, ens_probs)
        print(f"  {label}: Acc={ens_met['Accuracy']:.4f} | F1m={ens_met['F1_macro']:.4f} | "
              f"Kappa={ens_met['Cohen_Kappa']:.4f}")
        ens_rl.append(mrow(label, ens_met, train_time=0, inf_time=0,
                           throughput=0, params=0, model_size_mb=0, epochs=0))

results.extend(ens_rl); save_inc(ens_rl)
print("Ensemble & Stacking tamamlandi")


# ============================================================
# 13. Final Results Table
# ============================================================
print(f"\n\n{'='*80}\nSONUC TABLOSU\n{'='*80}")
rs = sorted(results,
    key=lambda x: x.get("Accuracy", 0) if not np.isnan(x.get("Accuracy", 0)) else -1,
    reverse=True)

td = [[r["Model"],
       f"{r.get('Accuracy', 0):.4f}",
       f"{r.get('Balanced_Accuracy', 0):.4f}",
       f"{r.get('F1_macro', 0):.4f}",
       f"{r.get('Precision_macro', 0):.4f}",
       f"{r.get('Recall_macro', 0):.4f}",
       f"{r.get('Cohen_Kappa', 0):.4f}",
       f"{r.get('MCC', 0):.4f}",
       f"{r.get('Log_Loss', 0):.4f}",
       f"{r.get('Top2_Accuracy', 0):.4f}",
       f"{r.get('Top3_Accuracy', 0):.4f}",
       f"{r.get('Train_Time(s)', 0):.1f}",
       f"{r.get('Params', 0)}"]
      for r in rs if not np.isnan(r.get("Accuracy", 0))]

if rs:
    print(tabulate(td[:30], headers=["Model", "Acc", "BalAcc", "F1_mac", "Prec_mac",
                                      "Rec_mac", "Kappa", "MCC", "LogLoss", "Top2", "Top3",
                                      "Train(s)", "Params"],
                   tablefmt="simple_grid", stralign="right"))
    b = rs[0]
    print(f"\nEN IYI -> {b['Model']} | Accuracy: {b.get('Accuracy', 0):.4f}")

# Merge: mevcut CSV ile results birlestir (overwrite degil!)
_new_df = pd.DataFrame(rs)
_existing_csv = _load_existing_csv()
if not _existing_csv.empty:
    _keep = _existing_csv[~_existing_csv['Model'].isin(_new_df['Model'].values)]
    _final = pd.concat([_keep, _new_df], ignore_index=True)
    for c in CSV_COLS:
        if c not in _final.columns: _final[c] = 0
    _final = _final.sort_values('Accuracy', ascending=False).reset_index(drop=True)
    _final[CSV_COLS].to_csv(_CSV, index=False)
else:
    for c in CSV_COLS:
        if c not in _new_df.columns: _new_df[c] = 0
    _new_df[CSV_COLS].to_csv(_CSV, index=False)


# ============================================================
# 14. Post-Training Analyses
# ============================================================
print(f"\n\n{'='*80}\nPOST-TRAINING ANALIZLERI\n{'='*80}")

all_valid = [r for r in rs if not np.isnan(r.get("Accuracy", 0))]
if not all_valid:
    print("UYARI: Hic sonuc yok")
    sys.exit(0)

# --- Per-class metrics CSV (18 classes x precision/recall/f1) ---
print("\n--- Per-Class Metrics ---")
per_class_rows = []
for r in all_valid:
    nm = r["Model"]
    if nm not in all_test_probs: continue
    probs = all_test_probs[nm]
    preds = probs.argmax(axis=1)
    report = classification_report(y_test, preds, output_dict=True, zero_division=0)
    for cls_idx in range(OUT_DIM):
        cls_name = le.classes_[cls_idx]
        cls_key = str(cls_idx)
        if cls_key in report:
            per_class_rows.append({
                "Model": nm, "Class_ID": cls_idx, "Class_Name": cls_name,
                "Precision": report[cls_key]["precision"],
                "Recall": report[cls_key]["recall"],
                "F1": report[cls_key]["f1-score"],
                "Support": report[cls_key]["support"],
            })
if per_class_rows:
    pd.DataFrame(per_class_rows).to_csv(
        os.path.join(MODELS_DIR, "per_class_metrics.csv"), index=False)
    print(f"  -> per_class_metrics.csv ({len(per_class_rows)} rows)")

# --- Confusion matrix CSV (best model, 18x18) ---
print("\n--- Confusion Matrix (Best Model) ---")
best_name = all_valid[0]["Model"]
if best_name in all_test_probs:
    best_preds = all_test_probs[best_name].argmax(axis=1)
    cm = confusion_matrix(y_test, best_preds)
    cm_df = pd.DataFrame(cm, index=le.classes_, columns=le.classes_)
    cm_df.to_csv(os.path.join(MODELS_DIR, "confusion_matrix.csv"))
    print(f"  -> confusion_matrix.csv ({best_name})")

# --- Family summary CSV ---
print("\n--- Family Summary ---")
family_map = {
    "MLP_diamond": "MLP_Diamond",
    "MLP_Small_Raw": "MLP_Raw", "MLP_Medium_Raw": "MLP_Raw",
    "MLP_Large_Raw": "MLP_Raw", "MLP_XL_Raw": "MLP_Raw", "MLP_XXL_Raw": "MLP_Raw",
}
# Build family from prefix
def get_family(nm):
    if "diamond" in nm: return "MLP_Diamond"
    if "Raw" in nm: return "MLP_Raw"
    if nm.startswith("MLP_") and "diamond" not in nm and "Raw" not in nm and "Classifier" not in nm:
        return "MLP_Normal"
    if nm in sk_list: return "Sklearn"
    if "Ensemble" in nm: return "Ensemble"
    if "Stacking" in nm: return "Stacking"
    return "Other"

family_data = {}
for r in all_valid:
    nm = r["Model"]
    fam = get_family(nm)
    if fam not in family_data: family_data[fam] = []
    family_data[fam].append(r)

fam_rows = []
for fam, recs in family_data.items():
    fam_rows.append({
        "Family": fam, "N_Models": len(recs),
        "Accuracy_mean": np.mean([r.get("Accuracy", 0) for r in recs]),
        "Accuracy_best": max(r.get("Accuracy", 0) for r in recs),
        "F1_macro_mean": np.mean([r.get("F1_macro", 0) for r in recs]),
        "Cohen_Kappa_mean": np.mean([r.get("Cohen_Kappa", 0) for r in recs]),
        "Train_Time_mean": np.mean([r.get("Train_Time(s)", 0) for r in recs]),
    })
if fam_rows:
    pd.DataFrame(fam_rows).to_csv(os.path.join(MODELS_DIR, "family_summary.csv"), index=False)
    print(f"  -> family_summary.csv")

# --- Bootstrap 95% CI on accuracy (top-10, 1000 bootstrap) ---
print("\n--- Bootstrap 95% CI (Top-10) ---")
n_boot = 1000
ci_rows = []
for r in all_valid[:10]:
    nm = r["Model"]
    if nm not in all_test_probs: continue
    probs = all_test_probs[nm]
    preds = probs.argmax(axis=1)
    n_samples = len(y_test)
    boot_accs = []
    rng = np.random.RandomState(SEED)
    for _ in range(n_boot):
        idx_b = rng.choice(n_samples, n_samples, replace=True)
        boot_accs.append(accuracy_score(y_test[idx_b], preds[idx_b]))
    boot_accs = np.array(boot_accs)
    ci_rows.append({
        "Model": nm, "Accuracy_mean": np.mean(boot_accs), "Accuracy_std": np.std(boot_accs),
        "CI_lower_2.5": np.percentile(boot_accs, 2.5),
        "CI_upper_97.5": np.percentile(boot_accs, 97.5)
    })
    print(f"  {nm}: {np.mean(boot_accs):.4f} "
          f"[{np.percentile(boot_accs, 2.5):.4f}, {np.percentile(boot_accs, 97.5):.4f}]")
if ci_rows:
    pd.DataFrame(ci_rows).to_csv(os.path.join(MODELS_DIR, "bootstrap_ci.csv"), index=False)
    print(f"  -> bootstrap_ci.csv")

# --- Predictions dump ---
print("\n--- Predictions dump (npz) ---")
pred_save = {}
for nm, p in all_test_probs.items():
    pred_save[f"{nm}__test_probs"] = p.astype(np.float32)
for nm, p in all_val_probs.items():
    pred_save[f"{nm}__val_probs"] = p.astype(np.float32)
pred_save["y_test"] = y_test.astype(np.int64)
pred_save["y_val"] = y_val.astype(np.int64)
pred_save["X_test_sc"] = X_test_sc.astype(np.float32)
pred_save["X_val_sc"] = X_val_sc.astype(np.float32)
np.savez_compressed(os.path.join(MODELS_DIR, "predictions.npz"), **pred_save)
print(f"  -> predictions.npz ({len(all_test_probs)} models)")


# --- Convergence speed ---
print("\n--- Convergence Speed (90% of best) ---")
conv_rows = []
for nm in split_models.keys():
    curve_path = os.path.join(CURVES_DIR, f"{nm}.csv")
    if not os.path.exists(curve_path): continue
    try:
        cdf = pd.read_csv(curve_path)
        best_val = cdf["val_loss"].min()
        threshold = best_val * 1.1
        reached = cdf[cdf["val_loss"] <= threshold]
        ep_90 = int(reached.iloc[0]["epoch"]) if len(reached) > 0 else -1
        conv_rows.append({"Model": nm, "Best_Val_Loss": best_val,
                          "Epoch_90pct": ep_90, "Total_Epochs": len(cdf)})
    except: pass
if conv_rows:
    pd.DataFrame(conv_rows).to_csv(os.path.join(MODELS_DIR, "convergence_speed.csv"), index=False)
    print(f"  -> convergence_speed.csv")


# --- Experiment config JSON ---
config = {
    "seed": SEED,
    "approach": "cat disease multi-class classification",
    "in_dim": IN_DIM,
    "out_dim": OUT_DIM,
    "epoch_map": EPOCH_MAP,
    "batch_size": BS,
    "learning_rate": LR,
    "optimizer": "AdamW",
    "loss": "CrossEntropyLoss",
    "dataset": {
        "path": CSV_PATH,
        "total_rows": len(df),
        "train_size": len(idx_train),
        "val_size": len(idx_val),
        "test_size": len(idx_test),
        "split_ratio": "80/10/10",
        "stratified_on": "Disease_Prediction",
        "n_classes": OUT_DIM,
        "classes": list(le.classes_),
        "feature_columns": feature_cols,
    },
    "preprocessing": {
        "dataset_shuffle": True,
        "X_scaler": "StandardScaler",
        "target_encoding": "LabelEncoder",
    },
    "models": {
        "dl_models": len(split_models),
        "sklearn_models": len(sk_list),
        "ensemble_models": 6,
        "total": len(split_models) + len(sk_list) + 6,
    },
}
with open(os.path.join(MODELS_DIR, "experiment_config.json"), "w") as f:
    json.dump(config, f, indent=2, default=str)

print(f"\n{'='*80}\nTUM EGITIM TAMAMLANDI -> {_CSV}\n{'='*80}")
