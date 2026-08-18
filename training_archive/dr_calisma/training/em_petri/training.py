#!/usr/bin/env python3
"""
training_petri.py — Petri Egitim Seti Benchmark
==============================================================================
145 DL (70 Raw + 70 Normal + 5 diamond) + 6 sklearn + ensembles

Input (6):   x, y, z, target_B (degisken!) + 2 one-hot organ_id (0,1)
Output (15): D1-D7 (BAGIMSIZ!), P1-P7 (0-360), result_E

KEY DIFFERENCES FROM KEDI:
  - 542,494 satir (kedi 51K) — 10x buyuk
  - D1-D7 bagimsiz (kedi'de hepsi ayniydi)
  - target_B degisken (301 farkli deger, kedi'de sabit 0.001)
  - P 0-360 tam daire (kedi 0-278)
  - 2 organ dengeli 50/50 (kedi 6 organ, %98 organ 0)
  - CircularMSE loss for P outputs (MSE for D+E)
  - BS=16384, epoch'lar yarilandi (buyuk veri)
  - Tam blok yapisinda — shuffle zorunlu
"""

import sys
import time
import os
import gc
import math
import json
import warnings
import platform
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import MinMaxScaler
from sklearn.metrics import (r2_score, mean_absolute_error, explained_variance_score,
    median_absolute_error, mean_squared_error, mean_squared_log_error, max_error,
    mean_absolute_percentage_error)
from scipy.stats import spearmanr, pearsonr
from sklearn.tree import DecisionTreeRegressor
from sklearn.svm import SVR as SVRegressor
from sklearn.ensemble import (ExtraTreesRegressor, HistGradientBoostingRegressor,
    RandomForestRegressor, BaggingRegressor, AdaBoostRegressor)
from sklearn.multioutput import MultiOutputRegressor
from sklearn.linear_model import RidgeCV
from xgboost import XGBRegressor
from lightgbm import LGBMRegressor
from catboost import CatBoostRegressor
from tabulate import tabulate
import joblib
from skl2onnx import convert_sklearn
from skl2onnx.common.data_types import FloatTensorType
from scipy import stats

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
MODELS_DIR = "/home/user02/dr/models_petri"
CURVES_DIR = os.path.join(MODELS_DIR, "training_curves")

ORGAN_IDS = [0, 1]   # petri: sadece 2 organ, dengeli 50/50
N_ORGANS = len(ORGAN_IDS)

IN_DIM = 4 + N_ORGANS   # x,y,z,target_B + 2 one-hot = 6
OUT_DIM = 7 + 7 + 1     # D1-7 + P1-7 + result_E = 15
BS = 16384               # buyuk veri icin 2x batch
LR = 0.002
NUM_WORKERS = 4

# Epoch'lar yarilandi (542K satir = epoch basina 10x daha fazla gradient update)
EPOCH_MAP = {
    "Small": 1000, "Medium": 1000,
    "Large": 500, "XL": 250, "XXL": 250,
}

FP32_MODELS = {"TabNet_XL", "TabNet_XXL", "CNN_BiGRU_XXL", "MLP_XXL", "ResNet_XXL"}

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
# 1. Data Loading + SHUFFLE + One-hot + Stratified Split
# ============================================================
print("=" * 80)
print(f"PETRI EGITIM SETI YUKLENIYOR... (Device: {DEVICE})")
print(f"IN_DIM={IN_DIM}, OUT_DIM={OUT_DIM}, BS={BS}, LR={LR}")
print("=" * 80)

CSV_PATH = "/home/user02/dr/dataset/em_petri/petri_egitim_seti_PRO_final.csv"
df = pd.read_csv(CSV_PATH)
print(f"Ham satir sayisi: {len(df):,}")
print(f"organ_id dagilimi (ham):\n{df['organ_id'].value_counts().sort_index()}")

# ---- Step 1: DATASET-LEVEL SHUFFLE (TAM BLOK yapisi: ilk 271K organ 0, sonra 271K organ 1) ----
print("\n[Shuffle] Dataset-level shuffle (frac=1, seed=42) — BLOK YAPISI DAGITILIYOR...")
df = df.sample(frac=1, random_state=SEED).reset_index(drop=True)
print(f"Shuffle sonrasi ilk 10 organ_id: {df['organ_id'].head(10).tolist()}")

# Filtre (guvenlik)
df = df[df["organ_id"].isin(ORGAN_IDS)].reset_index(drop=True)
print(f"Filtre sonrasi satir: {len(df):,}")

d_cols = ["D1", "D2", "D3", "D4", "D5", "D6", "D7"]
p_cols = ["P1", "P2", "P3", "P4", "P5", "P6", "P7"]
e_col = "result_E"
y_cols = d_cols + p_cols + [e_col]   # 15 outputs

# ---- One-hot encode organ_id (2 organ: 0, 1) ----
print(f"\n[One-hot] organ_id -> {N_ORGANS} binary columns")
organ_oh = np.zeros((len(df), N_ORGANS), dtype=np.float32)
for i, oid in enumerate(ORGAN_IDS):
    organ_oh[:, i] = (df["organ_id"].values == oid).astype(np.float32)
print(f"one-hot shape: {organ_oh.shape}, toplam 1 sayisi: {organ_oh.sum():.0f}")

# ---- Build X (6) and y (15) ----
X_raw = np.column_stack([
    df["x"].values, df["y"].values, df["z"].values, df["target_B"].values,
    organ_oh
]).astype(np.float32)
y_raw = df[y_cols].values.astype(np.float32)
print(f"X_raw shape: {X_raw.shape} | y_raw shape: {y_raw.shape}")
print(f"target_B: {df['target_B'].nunique()} farkli deger [{df['target_B'].min():.6f}, {df['target_B'].max():.6f}]")

# Keep original values for metric computation
p_angles_deg = df[p_cols].values          # (N, 7) degrees
y_d_orig = df[d_cols].values              # (N, 7)
y_e_orig = df[e_col].values               # (N,)

print(f"D range: {y_d_orig.min():.4f} - {y_d_orig.max():.4f}")
print(f"P range: {p_angles_deg.min():.2f} - {p_angles_deg.max():.2f} deg")
print(f"E range: {y_e_orig.min():.4f} - {y_e_orig.max():.4f}")

# ---- Step 2: STRATIFIED SPLIT on organ_id (80/10/10) ----
print("\n[Stratified Split] 80/10/10 on organ_id")
idx_all = np.arange(len(df))
stratify_all = df["organ_id"].values

idx_tv, idx_test = train_test_split(
    idx_all, test_size=0.10, random_state=SEED, stratify=stratify_all
)
stratify_tv = df["organ_id"].values[idx_tv]
idx_train, idx_val = train_test_split(
    idx_tv, test_size=1/9, random_state=SEED, stratify=stratify_tv  # 1/9 * 0.9 = 0.1
)

print(f"Train: {len(idx_train):,} | Val: {len(idx_val):,} | Test: {len(idx_test):,}")
print("\nOrgan dagilimi her split'te:")
for split_name, split_idx in [("Train", idx_train), ("Val", idx_val), ("Test", idx_test)]:
    counts = df.iloc[split_idx]["organ_id"].value_counts().sort_index()
    print(f"  {split_name}: {counts.to_dict()}")

X_train_raw = X_raw[idx_train]; X_val_raw = X_raw[idx_val]; X_test_raw = X_raw[idx_test]
y_train_raw = y_raw[idx_train]; y_val_raw = y_raw[idx_val]; y_test_raw = y_raw[idx_test]

# Original-space test targets for metrics
y_d_test = y_d_orig[idx_test]             # (N_test, 7)
yp_test_deg = p_angles_deg[idx_test]      # (N_test, 7)
y_e_test = y_e_orig[idx_test]             # (N_test,)
y_d_val = y_d_orig[idx_val]
yp_val_deg = p_angles_deg[idx_val]
y_e_val = y_e_orig[idx_val]

# ============================================================
# 2. Scaling (MinMaxScaler on BOTH X and y)
# ============================================================
scaler_X = MinMaxScaler()
scaler_y = MinMaxScaler()

X_train_sc = scaler_X.fit_transform(X_train_raw)
X_val_sc = scaler_X.transform(X_val_raw)
X_test_sc = scaler_X.transform(X_test_raw)

y_train_sc = scaler_y.fit_transform(y_train_raw)
y_val_sc = scaler_y.transform(y_val_raw)
y_test_sc = scaler_y.transform(y_test_raw)

joblib.dump(scaler_X, os.path.join(MODELS_DIR, "scaler_X.pkl"))
joblib.dump(scaler_y, os.path.join(MODELS_DIR, "scaler_y.pkl"))
print("\nScaler'lar -> models/models_em_petri/scaler_X.pkl, scaler_y.pkl")

# ============================================================
# 3. DataLoader (train shuffle=True every epoch)
# ============================================================
train_ds = TensorDataset(torch.FloatTensor(X_train_sc), torch.FloatTensor(y_train_sc))
val_ds = TensorDataset(torch.FloatTensor(X_val_sc), torch.FloatTensor(y_val_sc))
test_ds = TensorDataset(torch.FloatTensor(X_test_sc), torch.FloatTensor(y_test_sc))

train_loader = DataLoader(train_ds, batch_size=BS, shuffle=True, num_workers=NUM_WORKERS, pin_memory=True)
val_loader = DataLoader(val_ds, batch_size=BS, shuffle=False, num_workers=NUM_WORKERS, pin_memory=True)
test_loader = DataLoader(test_ds, batch_size=BS, shuffle=False, num_workers=NUM_WORKERS, pin_memory=True)

# Ensemble/Stacking prediction storage
all_val_preds = {}    # model_name -> (N_val, 15) in original space
all_test_preds = {}   # model_name -> (N_test, 15) in original space

# ============================================================
# 4. Model Architectures
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
        mods.append(nn.Linear(in_dim, out_dim))
        self.net = nn.Sequential(*mods)
    def forward(self, x): return self.net(x)

class CNN1DModel(nn.Module):
    def __init__(self, channels, dropout=0.2, out_dim=OUT_DIM, in_dim=IN_DIM):
        super().__init__()
        lays = []
        ic = 1
        for oc in channels:
            lays.append(nn.Conv1d(ic, oc, 3, padding=1))
            if dropout > 0: lays.append(nn.BatchNorm1d(oc))
            lays.append(nn.ReLU())
            if dropout > 0: lays.append(nn.Dropout(dropout))
            ic = oc
        self.conv = nn.Sequential(*lays)
        self.pool = nn.AdaptiveAvgPool1d(1)
        fc_layers = [nn.Linear(channels[-1], 128), nn.ReLU()]
        if dropout > 0: fc_layers.append(nn.Dropout(dropout))
        fc_layers.append(nn.Linear(128, out_dim))
        self.fc = nn.Sequential(*fc_layers)
    def forward(self, x):
        c = self.conv(x.unsqueeze(1))
        p = self.pool(c).squeeze(-1)
        return self.fc(p)

class RNNModel(nn.Module):
    def __init__(self, rnn_type="lstm", hidden_size=128, num_layers=2, dropout=0.2, bidirectional=False, out_dim=OUT_DIM, in_dim=IN_DIM):
        super().__init__()
        self.n_steps = 8
        self.step_dim = 32
        self.proj = nn.Sequential(nn.Linear(in_dim, self.n_steps * self.step_dim), nn.ReLU())
        cls = {"rnn": nn.RNN, "gru": nn.GRU, "lstm": nn.LSTM}[rnn_type]
        self.rnn = cls(self.step_dim, hidden_size, num_layers, batch_first=True,
                       dropout=dropout if num_layers > 1 else 0, bidirectional=bidirectional)
        fc_in = hidden_size * (2 if bidirectional else 1)
        fc_l = [nn.Linear(fc_in, 64), nn.ReLU()]
        if dropout > 0: fc_l.append(nn.Dropout(dropout))
        fc_l.append(nn.Linear(64, out_dim))
        self.fc = nn.Sequential(*fc_l)
    def forward(self, x):
        x = self.proj(x).view(x.size(0), self.n_steps, self.step_dim)
        out, _ = self.rnn(x)
        return self.fc(out[:, -1, :])

class HybridCNNRNN(nn.Module):
    def __init__(self, cnn_ch=[32,64], rnn_type="lstm", hs=128, nl=1, do=0.2, bidir=False, out_dim=OUT_DIM, in_dim=IN_DIM):
        super().__init__()
        cl = []; ic = 1
        for oc in cnn_ch:
            cl.append(nn.Conv1d(ic, oc, 3, padding=1))
            if do > 0: cl.append(nn.BatchNorm1d(oc))
            cl.append(nn.ReLU()); ic = oc
        self.conv = nn.Sequential(*cl)
        self.pool = nn.AdaptiveAvgPool1d(8)
        cls = {"rnn": nn.RNN, "gru": nn.GRU, "lstm": nn.LSTM}[rnn_type]
        self.rnn = cls(cnn_ch[-1], hs, nl, batch_first=True, dropout=do if nl > 1 else 0, bidirectional=bidir)
        hfc = [nn.Linear(hs*(2 if bidir else 1), 64), nn.ReLU()]
        if do > 0: hfc.append(nn.Dropout(do))
        hfc.append(nn.Linear(64, out_dim))
        self.fc = nn.Sequential(*hfc)
    def forward(self, x):
        c = self.pool(self.conv(x.unsqueeze(1)))
        out, _ = self.rnn(c.permute(0, 2, 1))
        return self.fc(out[:, -1, :])

class ResNetMLP(nn.Module):
    def __init__(self, layers, dropout=0.2, out_dim=OUT_DIM, in_dim=IN_DIM):
        super().__init__()
        self.proj = nn.Linear(in_dim, layers[0])
        self.blocks = nn.ModuleList()
        for i in range(len(layers)-1):
            bl = [nn.Linear(layers[i], layers[i+1])]
            if dropout > 0: bl.append(nn.BatchNorm1d(layers[i+1]))
            bl += [nn.ReLU()]
            if dropout > 0: bl.append(nn.Dropout(dropout))
            bl.append(nn.Linear(layers[i+1], layers[i+1]))
            if dropout > 0: bl.append(nn.BatchNorm1d(layers[i+1]))
            b = nn.Sequential(*bl)
            s = nn.Linear(layers[i], layers[i+1]) if layers[i] != layers[i+1] else nn.Identity()
            self.blocks.append(nn.ModuleDict({"b": b, "s": s}))
        self.relu = nn.ReLU()
        self.out = nn.Linear(layers[-1], out_dim)
    def forward(self, x):
        x = self.relu(self.proj(x))
        for blk in self.blocks: x = self.relu(blk["b"](x) + blk["s"](x))
        return self.out(x)

class TabNetBlock(nn.Module):
    def __init__(self, in_dim, hd, out_dim, ns=3, do=0.2):
        super().__init__()
        self.ns = ns
        self.shared = nn.Linear(in_dim, hd)
        self.attns = nn.ModuleList([
            nn.Sequential(nn.Linear(hd, in_dim), nn.BatchNorm1d(in_dim), nn.Sigmoid()) if do > 0
            else nn.Sequential(nn.Linear(hd, in_dim), nn.Sigmoid())
            for _ in range(ns)])
        self.fcs = nn.ModuleList([
            nn.Sequential(nn.Linear(in_dim, hd), nn.BatchNorm1d(hd), nn.ReLU(), nn.Dropout(do)) if do > 0
            else nn.Sequential(nn.Linear(in_dim, hd), nn.ReLU())
            for _ in range(ns)])
        self.out = nn.Linear(hd, out_dim)
    def forward(self, x):
        h = torch.relu(self.shared(x))
        agg = torch.zeros_like(h)
        for i in range(self.ns):
            agg = agg + self.fcs[i](x * self.attns[i](h)); h = agg
        return self.out(agg)
    def get_attention_masks(self, x):
        h = torch.relu(self.shared(x))
        masks = []
        agg = torch.zeros_like(h)
        for i in range(self.ns):
            mask = self.attns[i](h)
            masks.append(mask.detach().cpu().numpy())
            agg = agg + self.fcs[i](x * mask); h = agg
        return masks


def create_model(cfg, out_dim=OUT_DIM, in_dim=IN_DIM):
    t = cfg["type"]
    if t == "mlp": return MLPModel(cfg["layers"], cfg["dropout"], out_dim, in_dim)
    if t == "resnet": return ResNetMLP(cfg["layers"], cfg["dropout"], out_dim, in_dim)
    if t == "tabnet": return TabNetBlock(in_dim, cfg["hidden"], out_dim, cfg["n_steps"], cfg["dropout"])
    if t == "cnn": return CNN1DModel(cfg["channels"], cfg["dropout"], out_dim, in_dim)
    if t == "rnn": return RNNModel(cfg["rnn_type"], cfg["hidden"], cfg["layers"], cfg["dropout"], cfg["bidir"], out_dim, in_dim)
    if t == "hybrid": return HybridCNNRNN(cfg["channels"], cfg["rnn_type"], cfg["hidden"], cfg["layers"], cfg["dropout"], cfg["bidir"], out_dim, in_dim)


# ============================================================
# 5. Circular Metrics
# ============================================================
def circ_diff(yt, yp):
    d = yp - yt; return d - 360.0 * np.round(d / 360.0)

def circ_r2(yt, yp):
    ss_res = np.sum(circ_diff(yt, yp)**2)
    rad = np.deg2rad(yt)
    cm = np.rad2deg(np.arctan2(np.mean(np.sin(rad), 0), np.mean(np.cos(rad), 0))) % 360
    ss_tot = np.sum(circ_diff(yt, np.broadcast_to(cm, yt.shape))**2)
    return 1.0 - ss_res/ss_tot if ss_tot > 0 else 0.0

def circular_mean_ensemble(predictions_list, n_out):
    pred = np.zeros((len(predictions_list[0]), n_out))
    for j in range(n_out):
        cols = np.column_stack([p[:, j] for p in predictions_list])
        rad = np.deg2rad(cols)
        sin_mean = np.mean(np.sin(rad), axis=1)
        cos_mean = np.mean(np.cos(rad), axis=1)
        pred[:, j] = np.rad2deg(np.arctan2(sin_mean, cos_mean)) % 360.0
    return pred

def circular_stacking_features(predictions_list, n_out):
    features = []
    for p in predictions_list:
        for j in range(n_out):
            rad = np.deg2rad(p[:, j])
            features.append(np.sin(rad))
            features.append(np.cos(rad))
    return np.column_stack(features)

def circ_mae(yt, yp): return np.mean(np.abs(circ_diff(yt, yp)))
def circ_rmse(yt, yp): return float(np.sqrt(np.mean(circ_diff(yt, yp)**2)))
def circ_medae(yt, yp): return float(np.median(np.abs(circ_diff(yt, yp))))
def circ_maxae(yt, yp): return float(np.max(np.abs(circ_diff(yt, yp))))
def circ_p95ae(yt, yp): return float(np.percentile(np.abs(circ_diff(yt, yp)), 95))

def per_output_r2(yt, yp, circ=False):
    r2s = []
    for j in range(yt.shape[1]):
        if circ:
            d = circ_diff(yt[:, j], yp[:, j])
            ss_res = np.sum(d**2)
            rad = np.deg2rad(yt[:, j])
            cm = np.rad2deg(np.arctan2(np.mean(np.sin(rad)), np.mean(np.cos(rad)))) % 360
            ss_tot = np.sum(circ_diff(yt[:, j], np.full_like(yt[:, j], cm))**2)
            r2s.append(1.0 - ss_res/ss_tot if ss_tot > 0 else 0.0)
        else:
            r2s.append(r2_score(yt[:, j], yp[:, j]))
    return r2s


# ============================================================
# 6. CSV
# ============================================================
_CSV = os.path.join(MODELS_DIR, "model_petri_karsilastirma.csv")

# ---- Standard regression metric suffixes (per group) ----
_REG_SUFFIX = [
    "MSE", "RMSE", "MAE", "MedAE", "MaxAE", "p95AE", "p99AE",
    "R2", "AdjR2", "ExpVar",
    "MAPE", "sMAPE", "MSLE", "RMSLE",
    "Pearson", "Spearman", "MBE",
    "NRMSE_range", "NRMSE_mean", "NRMSE_std", "CVRMSE",
]

def _group_cols(prefix):
    return [f"{prefix}_{s}" for s in _REG_SUFFIX]

CSV_COLS = (
    ["Model", "Combined_R2"]
    # Scaled-space loss
    + ["Scaled_MSE", "Scaled_RMSE", "Scaled_MAE"]
    # D group (21 standard regression metrics)
    + _group_cols("D")
    # P group LINEAR (21 standard metrics on degree values)
    + _group_cols("P")
    # P group CIRCULAR (6 phase-aware metrics)
    + ["P_cR2", "P_cMAE_deg", "P_cRMSE_deg", "P_cMedAE_deg", "P_cMaxAE_deg", "P_cp95AE_deg"]
    # E group (21 standard regression metrics)
    + _group_cols("E")
    # Training
    + ["Train_Time(s)", "Best_Epoch", "Best_Val_Loss", "Final_Train_Loss",
       "Train_Val_Gap", "GPU_Mem_MB"]
    # Inference
    + ["Inference_Time(s)", "Throughput_samples_s"]
    # Model info
    + ["Params", "ModelSize_MB", "Epochs"]
)

# Mapping from lower-case internal metric key to CSV column name
_METRIC_KEY_MAP = {
    "mse": "MSE", "rmse": "RMSE", "mae": "MAE", "medae": "MedAE",
    "maxae": "MaxAE", "p95ae": "p95AE", "p99ae": "p99AE",
    "r2": "R2", "adj_r2": "AdjR2", "expvar": "ExpVar",
    "mape": "MAPE", "smape": "sMAPE", "msle": "MSLE", "rmsle": "RMSLE",
    "pearson": "Pearson", "spearman": "Spearman", "mbe": "MBE",
    "nrmse_range": "NRMSE_range", "nrmse_mean": "NRMSE_mean",
    "nrmse_std": "NRMSE_std", "cvrmse": "CVRMSE",
}

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
         best_epoch=0, best_val_loss=0.0, final_train_loss=0.0,
         train_val_gap=0.0, gpu_mem_mb=0.0):
    """Build CSV row from a metrics dict m (from compute_metrics) + training info."""
    row = {"Model": name, "Combined_R2": m.get("combined_r2", float("nan"))}

    # Scaled
    row["Scaled_MSE"] = m.get("scaled_mse", float("nan"))
    row["Scaled_RMSE"] = m.get("scaled_rmse", float("nan"))
    row["Scaled_MAE"] = m.get("scaled_mae", float("nan"))

    # D, P (linear), E groups — all 21 standard regression metrics
    for grp_prefix in ["d", "p", "e"]:
        for low_key, col_suf in _METRIC_KEY_MAP.items():
            internal_key = f"{grp_prefix}_{low_key}"
            col_name = f"{grp_prefix.upper()}_{col_suf}"
            row[col_name] = m.get(internal_key, float("nan"))

    # P circular
    row["P_cR2"] = m.get("p_cr2", float("nan"))
    row["P_cMAE_deg"] = m.get("p_cmae_deg", float("nan"))
    row["P_cRMSE_deg"] = m.get("p_crmse_deg", float("nan"))
    row["P_cMedAE_deg"] = m.get("p_cmedae_deg", float("nan"))
    row["P_cMaxAE_deg"] = m.get("p_cmaxae_deg", float("nan"))
    row["P_cp95AE_deg"] = m.get("p_cp95ae_deg", float("nan"))

    # Training + inference + info
    row["Train_Time(s)"] = train_time
    row["Best_Epoch"] = best_epoch
    row["Best_Val_Loss"] = best_val_loss
    row["Final_Train_Loss"] = final_train_loss
    row["Train_Val_Gap"] = train_val_gap
    row["GPU_Mem_MB"] = gpu_mem_mb
    row["Inference_Time(s)"] = inf_time
    row["Throughput_samples_s"] = throughput
    row["Params"] = params
    row["ModelSize_MB"] = model_size_mb
    row["Epochs"] = epochs
    return row


def nan_metrics():
    """Return a metrics dict filled with NaN (for failed models)."""
    m = {"scaled_mse": float("nan"), "scaled_rmse": float("nan"),
         "scaled_mae": float("nan"), "combined_r2": float("nan"),
         "p_cr2": float("nan"), "p_cmae_deg": float("nan"),
         "p_crmse_deg": float("nan"), "p_cmedae_deg": float("nan"),
         "p_cmaxae_deg": float("nan"), "p_cp95ae_deg": float("nan")}
    for grp in ["d", "p", "e"]:
        for k in _METRIC_KEY_MAP.keys():
            m[f"{grp}_{k}"] = float("nan")
    return m


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

def inverse_transform_predictions(pred_sc):
    """Inverse transform (N,15) scaled to original: (D 7, P 7, E 1)."""
    pred_real = scaler_y.inverse_transform(pred_sc)
    d_pred = pred_real[:, :7]
    p_pred = pred_real[:, 7:14]
    e_pred = pred_real[:, 14]
    return d_pred, p_pred, e_pred

def _regression_metrics(yt, yp, n_features=IN_DIM, prefix=""):
    """Compute comprehensive regression metrics for any (yt, yp) pair.
    Works for 1D or 2D arrays. Returns dict with keys '{prefix}_<metric>'.
    """
    yt_f = np.asarray(yt, dtype=np.float64).flatten()
    yp_f = np.asarray(yp, dtype=np.float64).flatten()
    n = len(yt_f)
    err = yt_f - yp_f
    abs_err = np.abs(err)
    eps = 1e-8

    # --- Core loss metrics ---
    mse = float(np.mean(err**2))
    rmse = float(np.sqrt(mse))
    mae = float(np.mean(abs_err))
    medae = float(np.median(abs_err))
    maxae = float(np.max(abs_err))
    p95ae = float(np.percentile(abs_err, 95))
    p99ae = float(np.percentile(abs_err, 99))

    # --- R-squared family ---
    try:    r2 = float(r2_score(yt_f, yp_f))
    except: r2 = float("nan")
    # Adjusted R² = 1 - (1-R²)(n-1)/(n-p-1)
    if n - n_features - 1 > 0 and not np.isnan(r2):
        adj_r2 = float(1.0 - (1.0 - r2) * (n - 1) / (n - n_features - 1))
    else:
        adj_r2 = float("nan")
    try:    expvar = float(explained_variance_score(yt_f, yp_f))
    except: expvar = float("nan")

    # --- Percentage errors ---
    # MAPE uses sklearn's version (handles small denominators)
    try:
        mape = float(mean_absolute_percentage_error(yt_f, yp_f)) * 100.0
    except:
        mape = float(np.mean(abs_err / np.maximum(np.abs(yt_f), eps))) * 100.0
    # sMAPE: symmetric MAPE (bounded 0-200%)
    smape = float(np.mean(2.0 * abs_err / (np.abs(yt_f) + np.abs(yp_f) + eps))) * 100.0

    # --- Mean Squared Log Error (y >= 0 required) ---
    try:
        yt_pos = np.maximum(yt_f, 0.0)
        yp_pos = np.maximum(yp_f, 0.0)
        msle = float(mean_squared_log_error(yt_pos, yp_pos))
        rmsle = float(np.sqrt(msle))
    except:
        msle = float("nan"); rmsle = float("nan")

    # --- Correlations ---
    try:    pearson_r = float(pearsonr(yt_f, yp_f)[0])
    except: pearson_r = float("nan")
    try:    spearman_r = float(spearmanr(yt_f, yp_f)[0])
    except: spearman_r = float("nan")

    # --- Bias (MBE — Mean Bias Error) ---
    mbe = float(np.mean(yp_f - yt_f))   # positive => over-prediction

    # --- Normalized metrics ---
    yt_range = float(yt_f.max() - yt_f.min())
    yt_mean = float(np.mean(yt_f))
    yt_std = float(np.std(yt_f))
    nrmse_range = rmse / yt_range if yt_range > 0 else float("nan")
    nrmse_mean = rmse / yt_mean if abs(yt_mean) > eps else float("nan")
    nrmse_std = rmse / yt_std if yt_std > 0 else float("nan")
    cvrmse = 100.0 * rmse / yt_mean if abs(yt_mean) > eps else float("nan")  # ASHRAE (%)

    out = {
        "mse": mse, "rmse": rmse, "mae": mae, "medae": medae,
        "maxae": maxae, "p95ae": p95ae, "p99ae": p99ae,
        "r2": r2, "adj_r2": adj_r2, "expvar": expvar,
        "mape": mape, "smape": smape, "msle": msle, "rmsle": rmsle,
        "pearson": pearson_r, "spearman": spearman_r, "mbe": mbe,
        "nrmse_range": nrmse_range, "nrmse_mean": nrmse_mean,
        "nrmse_std": nrmse_std, "cvrmse": cvrmse,
    }
    if prefix:
        out = {f"{prefix}_{k}": v for k, v in out.items()}
    return out


def compute_metrics(d_true, d_pred, p_true_deg, p_pred_deg, e_true, e_pred, y_sc_pred, y_sc_true):
    m = {}

    # ---- Scaled-space loss (all outputs together) ----
    m["scaled_mse"] = float(np.mean((y_sc_pred - y_sc_true)**2))
    m["scaled_rmse"] = float(np.sqrt(m["scaled_mse"]))
    m["scaled_mae"] = float(np.mean(np.abs(y_sc_pred - y_sc_true)))

    # ---- D group (linear, 7 outputs) ----
    m.update(_regression_metrics(d_true, d_pred, n_features=IN_DIM, prefix="d"))

    # ---- P group (LINEAR metrics on degrees) ----
    m.update(_regression_metrics(p_true_deg, p_pred_deg, n_features=IN_DIM, prefix="p"))
    # ---- P group (CIRCULAR metrics) ----
    m["p_cr2"] = float(circ_r2(p_true_deg, p_pred_deg))
    m["p_cmae_deg"] = float(circ_mae(p_true_deg, p_pred_deg))
    m["p_crmse_deg"] = circ_rmse(p_true_deg, p_pred_deg)
    m["p_cmedae_deg"] = circ_medae(p_true_deg, p_pred_deg)
    m["p_cmaxae_deg"] = circ_maxae(p_true_deg, p_pred_deg)
    m["p_cp95ae_deg"] = circ_p95ae(p_true_deg, p_pred_deg)

    # ---- E (scalar) ----
    m.update(_regression_metrics(e_true, e_pred, n_features=IN_DIM, prefix="e"))

    # ---- Combined R² (circular for P) ----
    m["combined_r2"] = (m["d_r2"] + m["p_cr2"] + m["e_r2"]) / 3.0

    return m


# ============================================================
# 8. DL Training
# ============================================================
per_output_metrics_rows = []

def train_dl(cfg, name, epochs):
    use_fp16 = name not in FP32_MODELS
    clip_norm = 0.5 if name in FP32_MODELS else 1.0
    _lr = cfg.get("lr", LR)
    _bs = cfg.get("batch_size", BS)

    pt_path = os.path.join(MODELS_DIR, f"{name}.pt")
    mdl = create_model(cfg, OUT_DIM, IN_DIM).to(DEVICE)
    n_params = count_parameters(mdl)

    if _bs != BS:
        _train_loader = DataLoader(train_ds, batch_size=_bs, shuffle=True, num_workers=NUM_WORKERS, pin_memory=True)
        _val_loader = DataLoader(val_ds, batch_size=_bs, shuffle=False, num_workers=NUM_WORKERS, pin_memory=True)
        _test_loader = DataLoader(test_ds, batch_size=_bs, shuffle=False, num_workers=NUM_WORKERS, pin_memory=True)
    else:
        _train_loader = train_loader
        _val_loader = val_loader
        _test_loader = test_loader

    ckpt_path = os.path.join(MODELS_DIR, f"{name}.ckpt")

    if os.path.exists(pt_path):
        print(f"    Mevcut model yukleniyor (skip)...", flush=True)
        mdl.load_state_dict(torch.load(pt_path, map_location=DEVICE)); mdl.eval()
        _csv_tt = _get_existing_csv_value(_CSV, name, "Train_Time(s)")
        tt = _csv_tt if _csv_tt is not None else 0.0
        bv = _get_existing_csv_value(_CSV, name, "Best_Val_Loss") or 0.0
        best_epoch_ = int(_get_existing_csv_value(_CSV, name, "Best_Epoch") or 0)
        final_tl = _get_existing_csv_value(_CSV, name, "Final_Train_Loss") or 0.0
        train_at_best = final_tl
        gpu_mem = _get_existing_csv_value(_CSV, name, "GPU_Mem_MB") or 0.0
    else:
        scaler_amp = torch.cuda.amp.GradScaler(enabled=use_fp16)
        opt = torch.optim.AdamW(mdl.parameters(), lr=_lr, weight_decay=1e-4)
        crit_mse = nn.MSELoss()

        def crit(pred, target):
            """Hybrid loss: MSE for D(0:7)+E(14), CircularMSE for P(7:14).
            P outputs are MinMaxScaler'd to [0,1], circular diff wraps around 1.0."""
            d_loss = crit_mse(pred[:, :7], target[:, :7])        # D1-D7: MSE
            e_loss = crit_mse(pred[:, 14:], target[:, 14:])      # E: MSE
            # P: circular diff in scaled space (range 0-1, period=1.0)
            p_diff = pred[:, 7:14] - target[:, 7:14]
            p_diff = p_diff - torch.round(p_diff)                # wrap to [-0.5, 0.5]
            p_loss = (p_diff ** 2).mean()
            return (d_loss + p_loss + e_loss) / 3.0              # equal weight

        bv, bs_ = float("inf"), None
        best_epoch_ = 0
        final_tl = 0.0
        train_at_best = 0.0
        curve_data = []
        start_epoch = 1
        elapsed_prev = 0.0  # Time from previous session(s)

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
                train_at_best = ckpt.get("train_at_best", 0.0)
                curve_data = ckpt.get("curve_data", [])
                bs_ = ckpt.get("best_state", None)
                start_epoch = ckpt.get("epoch", 0) + 1
                elapsed_prev = ckpt.get("elapsed_total", 0.0)
                print(f"    >>> CHECKPOINT yuklendi: epoch {start_epoch-1}/{epochs}, "
                      f"bv={bv:.8f}, elapsed={elapsed_prev:.0f}s", flush=True)
            except Exception as e:
                print(f"    Checkpoint HATA ({str(e)[:80]}), bastan basliyor")
                start_epoch = 1
                elapsed_prev = 0.0
                curve_data = []
                bv = float("inf"); bs_ = None; best_epoch_ = 0; train_at_best = 0.0

        print(f"    Egitim (params: {n_params:,}, epochs: {start_epoch}..{epochs}, "
              f"lr: {_lr}, bs: {_bs})"
              f"{' [FP32]' if not use_fp16 else ''}"
              f"{' [RESUMED]' if start_epoch > 1 else ''}...", flush=True)
        reset_gpu_memory_tracking()

        CKPT_EVERY = 100  # Checkpoint her 100 epoch'ta
        t0 = time.time()

        for ep in range(start_epoch, epochs+1):
            mdl.train(); tl_ = 0
            for xb, yb in _train_loader:
                xb, yb = xb.to(DEVICE, non_blocking=True), yb.to(DEVICE, non_blocking=True)
                opt.zero_grad()
                with torch.cuda.amp.autocast(enabled=use_fp16):
                    l = crit(mdl(xb), yb)
                scaler_amp.scale(l).backward()
                scaler_amp.unscale_(opt)
                torch.nn.utils.clip_grad_norm_(mdl.parameters(), max_norm=clip_norm)
                scaler_amp.step(opt); scaler_amp.update()
                tl_ += l.item()*len(xb)
            tl_ /= len(train_ds)

            mdl.eval(); vl_ = 0
            with torch.no_grad(), torch.cuda.amp.autocast(enabled=use_fp16):
                for xb, yb in _val_loader:
                    xb, yb = xb.to(DEVICE, non_blocking=True), yb.to(DEVICE, non_blocking=True)
                    vl_ += crit(mdl(xb), yb).item()*len(xb)
            vl_ /= len(val_ds)

            curve_data.append({"epoch": ep, "train_loss": tl_, "val_loss": vl_})
            final_tl = tl_

            if ep % 100 == 0 or ep == 1 or ep == start_epoch:
                print(f"    Ep {ep:4d}/{epochs} | T: {tl_:.8f} | V: {vl_:.8f}", flush=True)

            if vl_ < bv:
                bv = vl_
                best_epoch_ = ep
                train_at_best = tl_
                bs_ = {k: v.clone() for k, v in mdl.state_dict().items()}

            # Periodic checkpoint (her 100 epoch — son epoch haric, son epoch .pt'ye yazilacak)
            if ep % CKPT_EVERY == 0 and ep < epochs:
                try:
                    elapsed_now = elapsed_prev + (time.time() - t0)
                    torch.save({
                        "epoch": ep,
                        "model_state": mdl.state_dict(),
                        "opt_state": opt.state_dict(),
                        "scaler_state": scaler_amp.state_dict() if use_fp16 else None,
                        "bv": bv, "best_epoch": best_epoch_,
                        "train_at_best": train_at_best,
                        "curve_data": curve_data,
                        "best_state": bs_,
                        "elapsed_total": elapsed_now,
                    }, ckpt_path + ".tmp")
                    os.replace(ckpt_path + ".tmp", ckpt_path)  # Atomic write
                except Exception as e:
                    print(f"    Ckpt save HATA: {str(e)[:80]}")

        tt = elapsed_prev + (time.time() - t0)
        gpu_mem = get_gpu_memory_mb()

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
                         best_epoch=0, best_val_loss=float("nan"),
                         final_train_loss=float("nan"), train_val_gap=float("nan"),
                         gpu_mem_mb=gpu_mem)]

        mdl.load_state_dict(bs_); mdl.eval()
        torch.save(bs_, pt_path)

        try:
            torch.onnx.export(mdl, torch.randn(1, IN_DIM).to(DEVICE),
                os.path.join(MODELS_DIR, f"{name}.onnx"),
                input_names=["input"], output_names=["output"],
                dynamic_axes={"input":{0:"b"},"output":{0:"b"}}, opset_version=13)
        except Exception as e:
            print(f"    ONNX fail: {str(e)[:80]}")

    it, throughput = measure_inference_latency(mdl, _test_loader, DEVICE, len(test_ds))
    model_size_mb = file_size_mb(pt_path)

    test_preds_sc = []
    with torch.no_grad(), torch.cuda.amp.autocast():
        for xb, _ in _test_loader:
            test_preds_sc.append(mdl(xb.to(DEVICE, non_blocking=True)).cpu().numpy())
    test_preds_sc = np.vstack(test_preds_sc)

    val_preds_sc = []
    with torch.no_grad(), torch.cuda.amp.autocast():
        for xb, _ in _val_loader:
            val_preds_sc.append(mdl(xb.to(DEVICE, non_blocking=True)).cpu().numpy())
    val_preds_sc = np.vstack(val_preds_sc)

    d_pred_test, p_pred_test, e_pred_test = inverse_transform_predictions(test_preds_sc)
    d_pred_val, p_pred_val, e_pred_val = inverse_transform_predictions(val_preds_sc)

    # Store for ensemble (15 cols: D1-7 | P1-7 | E)
    all_test_preds[name] = np.column_stack([d_pred_test, p_pred_test, e_pred_test])
    all_val_preds[name] = np.column_stack([d_pred_val, p_pred_val, e_pred_val])

    m = compute_metrics(y_d_test, d_pred_test, yp_test_deg, p_pred_test,
                        y_e_test, e_pred_test, test_preds_sc, y_test_sc)
    print(f"  MSE:{m['scaled_mse']:.6f} | D:{m['d_r2']:.6f} | P:{m['p_cr2']:.6f} "
          f"| E:{m['e_r2']:.6f} | Comb:{m['combined_r2']:.6f} | {tt:.1f}s | {throughput:.0f} s/s")

    d_r2_per = per_output_r2(y_d_test, d_pred_test, circ=False)
    p_r2_per = per_output_r2(yp_test_deg, p_pred_test, circ=True)
    row_po = {"Model": name}
    for j, v in enumerate(d_r2_per): row_po[f"R2_D{j+1}"] = v
    for j, v in enumerate(p_r2_per): row_po[f"R2_P{j+1}"] = v
    row_po["R2_E"] = m["e_r2"]
    per_output_metrics_rows.append(row_po)

    del mdl; torch.cuda.empty_cache()

    train_val_gap = train_at_best - bv if bv != float("inf") else 0.0
    return [mrow(name, m, train_time=tt, inf_time=it, throughput=throughput,
                 params=n_params, model_size_mb=model_size_mb, epochs=epochs,
                 best_epoch=best_epoch_, best_val_loss=bv,
                 final_train_loss=final_tl, train_val_gap=train_val_gap,
                 gpu_mem_mb=gpu_mem)]


# ============================================================
# 9. Model Configurations (141 DL models)
# ============================================================
split_models = {
    # ============================================================
    # RAW variants (NO BatchNorm, NO Dropout) — 70 total
    # ============================================================
    "MLP_Small_Raw":  {"type": "mlp", "layers": [128, 64], "dropout": 0.0},
    "MLP_Medium_Raw": {"type": "mlp", "layers": [256, 128, 64], "dropout": 0.0},
    "MLP_Large_Raw":  {"type": "mlp", "layers": [512, 256, 128, 64], "dropout": 0.0},
    "MLP_XL_Raw":     {"type": "mlp", "layers": [512, 512, 256, 128], "dropout": 0.0},
    "MLP_XXL_Raw":    {"type": "mlp", "layers": [1024, 512, 256, 128], "dropout": 0.0},
    # Diamond variants (narrow->wide->wide->narrow->narrower), no BN/Dropout
    # Original reference: [256, 512, 512, 256, 128] = MLP_diamond_Large
    "MLP_diamond_Small":  {"type": "mlp", "layers": [64, 128, 128, 64, 32],       "dropout": 0.0},
    "MLP_diamond_Medium": {"type": "mlp", "layers": [128, 256, 256, 128, 64],     "dropout": 0.0},
    "MLP_diamond_Large":  {"type": "mlp", "layers": [256, 512, 512, 256, 128],    "dropout": 0.0},
    "MLP_diamond_XL":     {"type": "mlp", "layers": [384, 768, 768, 384, 192],    "dropout": 0.0},
    "MLP_diamond_XXL":    {"type": "mlp", "layers": [512, 1024, 1024, 512, 256],  "dropout": 0.0},
    "CNN1D_Small_Raw":  {"type": "cnn", "channels": [32, 64], "dropout": 0.0},
    "CNN1D_Medium_Raw": {"type": "cnn", "channels": [32, 64, 128], "dropout": 0.0},
    "CNN1D_Large_Raw":  {"type": "cnn", "channels": [64, 128, 256], "dropout": 0.0},
    "CNN1D_XL_Raw":     {"type": "cnn", "channels": [64, 128, 256, 512], "dropout": 0.0},
    "CNN1D_XXL_Raw":    {"type": "cnn", "channels": [128, 256, 512], "dropout": 0.0},
    "SimpleRNN_Small_Raw":  {"type": "rnn", "rnn_type": "rnn", "hidden": 64, "layers": 1, "dropout": 0.0, "bidir": False},
    "SimpleRNN_Medium_Raw": {"type": "rnn", "rnn_type": "rnn", "hidden": 128, "layers": 2, "dropout": 0.0, "bidir": False},
    "SimpleRNN_Large_Raw":  {"type": "rnn", "rnn_type": "rnn", "hidden": 256, "layers": 2, "dropout": 0.0, "bidir": False},
    "SimpleRNN_XL_Raw":     {"type": "rnn", "rnn_type": "rnn", "hidden": 256, "layers": 3, "dropout": 0.0, "bidir": False},
    "SimpleRNN_XXL_Raw":    {"type": "rnn", "rnn_type": "rnn", "hidden": 512, "layers": 3, "dropout": 0.0, "bidir": False},
    "GRU_Small_Raw":  {"type": "rnn", "rnn_type": "gru", "hidden": 64, "layers": 1, "dropout": 0.0, "bidir": False},
    "GRU_Medium_Raw": {"type": "rnn", "rnn_type": "gru", "hidden": 128, "layers": 2, "dropout": 0.0, "bidir": False},
    "GRU_Large_Raw":  {"type": "rnn", "rnn_type": "gru", "hidden": 256, "layers": 2, "dropout": 0.0, "bidir": False},
    "GRU_XL_Raw":     {"type": "rnn", "rnn_type": "gru", "hidden": 256, "layers": 3, "dropout": 0.0, "bidir": False},
    "GRU_XXL_Raw":    {"type": "rnn", "rnn_type": "gru", "hidden": 512, "layers": 3, "dropout": 0.0, "bidir": False},
    "LSTM_Small_Raw":  {"type": "rnn", "rnn_type": "lstm", "hidden": 64, "layers": 1, "dropout": 0.0, "bidir": False},
    "LSTM_Medium_Raw": {"type": "rnn", "rnn_type": "lstm", "hidden": 128, "layers": 2, "dropout": 0.0, "bidir": False},
    "LSTM_Large_Raw":  {"type": "rnn", "rnn_type": "lstm", "hidden": 256, "layers": 2, "dropout": 0.0, "bidir": False},
    "LSTM_XL_Raw":     {"type": "rnn", "rnn_type": "lstm", "hidden": 256, "layers": 3, "dropout": 0.0, "bidir": False},
    "LSTM_XXL_Raw":    {"type": "rnn", "rnn_type": "lstm", "hidden": 512, "layers": 3, "dropout": 0.0, "bidir": False},
    "BiGRU_Small_Raw":  {"type": "rnn", "rnn_type": "gru", "hidden": 64, "layers": 1, "dropout": 0.0, "bidir": True},
    "BiGRU_Medium_Raw": {"type": "rnn", "rnn_type": "gru", "hidden": 128, "layers": 2, "dropout": 0.0, "bidir": True},
    "BiGRU_Large_Raw":  {"type": "rnn", "rnn_type": "gru", "hidden": 256, "layers": 2, "dropout": 0.0, "bidir": True},
    "BiGRU_XL_Raw":     {"type": "rnn", "rnn_type": "gru", "hidden": 256, "layers": 3, "dropout": 0.0, "bidir": True},
    "BiGRU_XXL_Raw":    {"type": "rnn", "rnn_type": "gru", "hidden": 512, "layers": 3, "dropout": 0.0, "bidir": True},
    "BiLSTM_Small_Raw":  {"type": "rnn", "rnn_type": "lstm", "hidden": 64, "layers": 1, "dropout": 0.0, "bidir": True},
    "BiLSTM_Medium_Raw": {"type": "rnn", "rnn_type": "lstm", "hidden": 128, "layers": 2, "dropout": 0.0, "bidir": True},
    "BiLSTM_Large_Raw":  {"type": "rnn", "rnn_type": "lstm", "hidden": 256, "layers": 2, "dropout": 0.0, "bidir": True},
    "BiLSTM_XL_Raw":     {"type": "rnn", "rnn_type": "lstm", "hidden": 256, "layers": 3, "dropout": 0.0, "bidir": True},
    "BiLSTM_XXL_Raw":    {"type": "rnn", "rnn_type": "lstm", "hidden": 512, "layers": 3, "dropout": 0.0, "bidir": True},
    "ResNet_Small_Raw":  {"type": "resnet", "layers": [128, 128, 64], "dropout": 0.0},
    "ResNet_Medium_Raw": {"type": "resnet", "layers": [256, 256, 128, 64], "dropout": 0.0},
    "ResNet_Large_Raw":  {"type": "resnet", "layers": [512, 512, 256, 128], "dropout": 0.0},
    "ResNet_XL_Raw":     {"type": "resnet", "layers": [512, 512, 512, 256], "dropout": 0.0},
    "ResNet_XXL_Raw":    {"type": "resnet", "layers": [1024, 512, 512, 256], "dropout": 0.0},
    "TabNet_Small_Raw":  {"type": "tabnet", "hidden": 128, "n_steps": 3, "dropout": 0.0},
    "TabNet_Medium_Raw": {"type": "tabnet", "hidden": 192, "n_steps": 4, "dropout": 0.0},
    "TabNet_Large_Raw":  {"type": "tabnet", "hidden": 256, "n_steps": 5, "dropout": 0.0},
    "TabNet_XL_Raw":     {"type": "tabnet", "hidden": 384, "n_steps": 6, "dropout": 0.0},
    "TabNet_XXL_Raw":    {"type": "tabnet", "hidden": 512, "n_steps": 3, "dropout": 0.0, "lr": 0.0001, "batch_size": 1024},
    "CNN_RNN_Small_Raw":  {"type": "hybrid", "channels": [16, 32], "rnn_type": "rnn", "hidden": 64, "layers": 1, "dropout": 0.0, "bidir": False},
    "CNN_RNN_Medium_Raw": {"type": "hybrid", "channels": [32, 64], "rnn_type": "rnn", "hidden": 128, "layers": 1, "dropout": 0.0, "bidir": False},
    "CNN_RNN_Large_Raw":  {"type": "hybrid", "channels": [64, 128], "rnn_type": "rnn", "hidden": 256, "layers": 1, "dropout": 0.0, "bidir": False},
    "CNN_RNN_XL_Raw":     {"type": "hybrid", "channels": [64, 128], "rnn_type": "rnn", "hidden": 256, "layers": 2, "dropout": 0.0, "bidir": False},
    "CNN_RNN_XXL_Raw":    {"type": "hybrid", "channels": [128, 256], "rnn_type": "rnn", "hidden": 512, "layers": 2, "dropout": 0.0, "bidir": False},
    "CNN_LSTM_Small_Raw":  {"type": "hybrid", "channels": [16, 32], "rnn_type": "lstm", "hidden": 64, "layers": 1, "dropout": 0.0, "bidir": False},
    "CNN_LSTM_Medium_Raw": {"type": "hybrid", "channels": [32, 64], "rnn_type": "lstm", "hidden": 128, "layers": 1, "dropout": 0.0, "bidir": False},
    "CNN_LSTM_Large_Raw":  {"type": "hybrid", "channels": [64, 128], "rnn_type": "lstm", "hidden": 256, "layers": 1, "dropout": 0.0, "bidir": False},
    "CNN_LSTM_XL_Raw":     {"type": "hybrid", "channels": [64, 128], "rnn_type": "lstm", "hidden": 256, "layers": 2, "dropout": 0.0, "bidir": False},
    "CNN_LSTM_XXL_Raw":    {"type": "hybrid", "channels": [128, 256], "rnn_type": "lstm", "hidden": 512, "layers": 2, "dropout": 0.0, "bidir": False},
    "CNN_GRU_Small_Raw":  {"type": "hybrid", "channels": [16, 32], "rnn_type": "gru", "hidden": 64, "layers": 1, "dropout": 0.0, "bidir": False},
    "CNN_GRU_Medium_Raw": {"type": "hybrid", "channels": [32, 64], "rnn_type": "gru", "hidden": 128, "layers": 1, "dropout": 0.0, "bidir": False},
    "CNN_GRU_Large_Raw":  {"type": "hybrid", "channels": [64, 128], "rnn_type": "gru", "hidden": 256, "layers": 1, "dropout": 0.0, "bidir": False},
    "CNN_GRU_XL_Raw":     {"type": "hybrid", "channels": [64, 128], "rnn_type": "gru", "hidden": 256, "layers": 2, "dropout": 0.0, "bidir": False},
    "CNN_GRU_XXL_Raw":    {"type": "hybrid", "channels": [128, 256], "rnn_type": "gru", "hidden": 512, "layers": 2, "dropout": 0.0, "bidir": False},
    "CNN_BiLSTM_Small_Raw":  {"type": "hybrid", "channels": [16, 32], "rnn_type": "lstm", "hidden": 64, "layers": 1, "dropout": 0.0, "bidir": True},
    "CNN_BiLSTM_Medium_Raw": {"type": "hybrid", "channels": [32, 64], "rnn_type": "lstm", "hidden": 128, "layers": 1, "dropout": 0.0, "bidir": True},
    "CNN_BiLSTM_Large_Raw":  {"type": "hybrid", "channels": [64, 128], "rnn_type": "lstm", "hidden": 256, "layers": 1, "dropout": 0.0, "bidir": True},
    "CNN_BiLSTM_XL_Raw":     {"type": "hybrid", "channels": [64, 128], "rnn_type": "lstm", "hidden": 256, "layers": 2, "dropout": 0.0, "bidir": True},
    "CNN_BiLSTM_XXL_Raw":    {"type": "hybrid", "channels": [128, 256], "rnn_type": "lstm", "hidden": 512, "layers": 2, "dropout": 0.0, "bidir": True},
    "CNN_BiGRU_Small_Raw":  {"type": "hybrid", "channels": [16, 32], "rnn_type": "gru", "hidden": 64, "layers": 1, "dropout": 0.0, "bidir": True},
    "CNN_BiGRU_Medium_Raw": {"type": "hybrid", "channels": [32, 64], "rnn_type": "gru", "hidden": 128, "layers": 1, "dropout": 0.0, "bidir": True},
    "CNN_BiGRU_Large_Raw":  {"type": "hybrid", "channels": [64, 128], "rnn_type": "gru", "hidden": 256, "layers": 1, "dropout": 0.0, "bidir": True},
    "CNN_BiGRU_XL_Raw":     {"type": "hybrid", "channels": [64, 128], "rnn_type": "gru", "hidden": 256, "layers": 2, "dropout": 0.0, "bidir": True},
    "CNN_BiGRU_XXL_Raw":    {"type": "hybrid", "channels": [128, 256], "rnn_type": "gru", "hidden": 512, "layers": 2, "dropout": 0.0, "bidir": True},
    # ============================================================
    # NORMAL variants (BatchNorm + Dropout) (70)
    # ============================================================
    "MLP_Small":  {"type": "mlp", "layers": [128, 64], "dropout": 0.15},
    "MLP_Medium": {"type": "mlp", "layers": [256, 128, 64], "dropout": 0.2},
    "MLP_Large":  {"type": "mlp", "layers": [512, 256, 128, 64], "dropout": 0.2},
    "MLP_XL":     {"type": "mlp", "layers": [512, 512, 256, 128], "dropout": 0.2},
    "MLP_XXL":    {"type": "mlp", "layers": [1024, 512, 256, 128], "dropout": 0.2},
    "CNN1D_Small":  {"type": "cnn", "channels": [32, 64], "dropout": 0.1},
    "CNN1D_Medium": {"type": "cnn", "channels": [32, 64, 128], "dropout": 0.15},
    "CNN1D_Large":  {"type": "cnn", "channels": [64, 128, 256], "dropout": 0.2},
    "CNN1D_XL":     {"type": "cnn", "channels": [64, 128, 256, 512], "dropout": 0.2},
    "CNN1D_XXL":    {"type": "cnn", "channels": [128, 256, 512], "dropout": 0.2},
    "SimpleRNN_Small":  {"type": "rnn", "rnn_type": "rnn",  "hidden": 64,  "layers": 1, "dropout": 0.1, "bidir": False},
    "SimpleRNN_Medium": {"type": "rnn", "rnn_type": "rnn",  "hidden": 128, "layers": 2, "dropout": 0.2, "bidir": False},
    "SimpleRNN_Large":  {"type": "rnn", "rnn_type": "rnn",  "hidden": 256, "layers": 2, "dropout": 0.2, "bidir": False},
    "SimpleRNN_XL":     {"type": "rnn", "rnn_type": "rnn",  "hidden": 256, "layers": 3, "dropout": 0.2, "bidir": False},
    "SimpleRNN_XXL":    {"type": "rnn", "rnn_type": "rnn",  "hidden": 512, "layers": 3, "dropout": 0.2, "bidir": False},
    "GRU_Small":  {"type": "rnn", "rnn_type": "gru",  "hidden": 64,  "layers": 1, "dropout": 0.1, "bidir": False},
    "GRU_Medium": {"type": "rnn", "rnn_type": "gru",  "hidden": 128, "layers": 2, "dropout": 0.2, "bidir": False},
    "GRU_Large":  {"type": "rnn", "rnn_type": "gru",  "hidden": 256, "layers": 2, "dropout": 0.2, "bidir": False},
    "GRU_XL":     {"type": "rnn", "rnn_type": "gru",  "hidden": 256, "layers": 3, "dropout": 0.2, "bidir": False},
    "GRU_XXL":    {"type": "rnn", "rnn_type": "gru",  "hidden": 512, "layers": 3, "dropout": 0.2, "bidir": False},
    "LSTM_Small":  {"type": "rnn", "rnn_type": "lstm", "hidden": 64,  "layers": 1, "dropout": 0.1, "bidir": False},
    "LSTM_Medium": {"type": "rnn", "rnn_type": "lstm", "hidden": 128, "layers": 2, "dropout": 0.2, "bidir": False},
    "LSTM_Large":  {"type": "rnn", "rnn_type": "lstm", "hidden": 256, "layers": 2, "dropout": 0.2, "bidir": False},
    "LSTM_XL":     {"type": "rnn", "rnn_type": "lstm", "hidden": 256, "layers": 3, "dropout": 0.2, "bidir": False},
    "LSTM_XXL":    {"type": "rnn", "rnn_type": "lstm", "hidden": 512, "layers": 3, "dropout": 0.2, "bidir": False},
    "BiGRU_Small":  {"type": "rnn", "rnn_type": "gru",  "hidden": 64,  "layers": 1, "dropout": 0.1, "bidir": True},
    "BiGRU_Medium": {"type": "rnn", "rnn_type": "gru",  "hidden": 128, "layers": 2, "dropout": 0.2, "bidir": True},
    "BiGRU_Large":  {"type": "rnn", "rnn_type": "gru",  "hidden": 256, "layers": 2, "dropout": 0.2, "bidir": True},
    "BiGRU_XL":     {"type": "rnn", "rnn_type": "gru",  "hidden": 256, "layers": 3, "dropout": 0.2, "bidir": True},
    "BiGRU_XXL":    {"type": "rnn", "rnn_type": "gru",  "hidden": 512, "layers": 3, "dropout": 0.2, "bidir": True},
    "BiLSTM_Small":  {"type": "rnn", "rnn_type": "lstm", "hidden": 64,  "layers": 1, "dropout": 0.1, "bidir": True},
    "BiLSTM_Medium": {"type": "rnn", "rnn_type": "lstm", "hidden": 128, "layers": 2, "dropout": 0.2, "bidir": True},
    "BiLSTM_Large":  {"type": "rnn", "rnn_type": "lstm", "hidden": 256, "layers": 2, "dropout": 0.2, "bidir": True},
    "BiLSTM_XL":     {"type": "rnn", "rnn_type": "lstm", "hidden": 256, "layers": 3, "dropout": 0.2, "bidir": True},
    "BiLSTM_XXL":    {"type": "rnn", "rnn_type": "lstm", "hidden": 512, "layers": 3, "dropout": 0.2, "bidir": True},
    "CNN_RNN_Small":  {"type": "hybrid", "channels": [16, 32], "rnn_type": "rnn",  "hidden": 64,  "layers": 1, "dropout": 0.1, "bidir": False},
    "CNN_RNN_Medium": {"type": "hybrid", "channels": [32, 64], "rnn_type": "rnn",  "hidden": 128, "layers": 1, "dropout": 0.2, "bidir": False},
    "CNN_RNN_Large":  {"type": "hybrid", "channels": [64, 128], "rnn_type": "rnn", "hidden": 256, "layers": 1, "dropout": 0.2, "bidir": False},
    "CNN_RNN_XL":     {"type": "hybrid", "channels": [64, 128], "rnn_type": "rnn", "hidden": 256, "layers": 2, "dropout": 0.2, "bidir": False},
    "CNN_RNN_XXL":    {"type": "hybrid", "channels": [128, 256], "rnn_type": "rnn","hidden": 512, "layers": 2, "dropout": 0.2, "bidir": False},
    "CNN_LSTM_Small":  {"type": "hybrid", "channels": [16, 32], "rnn_type": "lstm", "hidden": 64,  "layers": 1, "dropout": 0.1, "bidir": False},
    "CNN_LSTM_Medium": {"type": "hybrid", "channels": [32, 64], "rnn_type": "lstm", "hidden": 128, "layers": 1, "dropout": 0.2, "bidir": False},
    "CNN_LSTM_Large":  {"type": "hybrid", "channels": [64, 128], "rnn_type": "lstm","hidden": 256, "layers": 1, "dropout": 0.2, "bidir": False},
    "CNN_LSTM_XL":     {"type": "hybrid", "channels": [64, 128], "rnn_type": "lstm","hidden": 256, "layers": 2, "dropout": 0.2, "bidir": False},
    "CNN_LSTM_XXL":    {"type": "hybrid", "channels": [128, 256], "rnn_type": "lstm","hidden": 512, "layers": 2, "dropout": 0.2, "bidir": False},
    "CNN_GRU_Small":  {"type": "hybrid", "channels": [16, 32], "rnn_type": "gru",  "hidden": 64,  "layers": 1, "dropout": 0.1, "bidir": False},
    "CNN_GRU_Medium": {"type": "hybrid", "channels": [32, 64], "rnn_type": "gru",  "hidden": 128, "layers": 1, "dropout": 0.2, "bidir": False},
    "CNN_GRU_Large":  {"type": "hybrid", "channels": [64, 128], "rnn_type": "gru", "hidden": 256, "layers": 1, "dropout": 0.2, "bidir": False},
    "CNN_GRU_XL":     {"type": "hybrid", "channels": [64, 128], "rnn_type": "gru", "hidden": 256, "layers": 2, "dropout": 0.2, "bidir": False},
    "CNN_GRU_XXL":    {"type": "hybrid", "channels": [128, 256], "rnn_type": "gru","hidden": 512, "layers": 2, "dropout": 0.2, "bidir": False},
    "CNN_BiLSTM_Small":  {"type": "hybrid", "channels": [16, 32], "rnn_type": "lstm", "hidden": 64,  "layers": 1, "dropout": 0.1, "bidir": True},
    "CNN_BiLSTM_Medium": {"type": "hybrid", "channels": [32, 64], "rnn_type": "lstm", "hidden": 128, "layers": 1, "dropout": 0.2, "bidir": True},
    "CNN_BiLSTM_Large":  {"type": "hybrid", "channels": [64, 128], "rnn_type": "lstm","hidden": 256, "layers": 1, "dropout": 0.2, "bidir": True},
    "CNN_BiLSTM_XL":     {"type": "hybrid", "channels": [64, 128], "rnn_type": "lstm","hidden": 256, "layers": 2, "dropout": 0.2, "bidir": True},
    "CNN_BiLSTM_XXL":    {"type": "hybrid", "channels": [128, 256], "rnn_type": "lstm","hidden": 512, "layers": 2, "dropout": 0.2, "bidir": True},
    "CNN_BiGRU_Small":  {"type": "hybrid", "channels": [16, 32], "rnn_type": "gru",  "hidden": 64,  "layers": 1, "dropout": 0.1, "bidir": True},
    "CNN_BiGRU_Medium": {"type": "hybrid", "channels": [32, 64], "rnn_type": "gru",  "hidden": 128, "layers": 1, "dropout": 0.2, "bidir": True},
    "CNN_BiGRU_Large":  {"type": "hybrid", "channels": [64, 128], "rnn_type": "gru", "hidden": 256, "layers": 1, "dropout": 0.2, "bidir": True},
    "CNN_BiGRU_XL":     {"type": "hybrid", "channels": [64, 128], "rnn_type": "gru", "hidden": 256, "layers": 2, "dropout": 0.2, "bidir": True},
    "CNN_BiGRU_XXL":    {"type": "hybrid", "channels": [128, 256], "rnn_type": "gru","hidden": 512, "layers": 2, "dropout": 0.2, "bidir": True},
    "ResNet_Small":  {"type": "resnet", "layers": [128, 128, 64], "dropout": 0.15},
    "ResNet_Medium": {"type": "resnet", "layers": [256, 256, 128, 64], "dropout": 0.2},
    "ResNet_Large":  {"type": "resnet", "layers": [512, 512, 256, 128], "dropout": 0.2},
    "ResNet_XL":     {"type": "resnet", "layers": [512, 512, 512, 256], "dropout": 0.2},
    "ResNet_XXL":    {"type": "resnet", "layers": [1024, 512, 512, 256], "dropout": 0.2},
    "TabNet_Small":  {"type": "tabnet", "hidden": 128, "n_steps": 3, "dropout": 0.2},
    "TabNet_Medium": {"type": "tabnet", "hidden": 192, "n_steps": 4, "dropout": 0.2},
    "TabNet_Large":  {"type": "tabnet", "hidden": 256, "n_steps": 5, "dropout": 0.2},
    "TabNet_XL":     {"type": "tabnet", "hidden": 384, "n_steps": 6, "dropout": 0.2},
    "TabNet_XXL":    {"type": "tabnet", "hidden": 512, "n_steps": 3, "dropout": 0.2, "lr": 0.0001, "batch_size": 1024},
}


# ============================================================
# 10. DL Training Loop
# ============================================================
sk_list = ["XGBoost", "ExtraTrees",
    "DecisionTree", "RandomForest", "BaggingRegressor", "AdaBoost"]
# NOT: "LightGBM", "SVR", "CatBoost", "HistGradientBoosting" cikarildi
# — MultiOutputRegressor ile cok yavas (15 output × yuzlerce iter)
results = []

print(f"\n{'='*80}\nEGITIM - {len(split_models)} DL + {len(sk_list)} SK = {len(split_models)+len(sk_list)} MODEL")
print(f"Config: IN_DIM={IN_DIM}, OUT_DIM={OUT_DIM}, BS={BS}, LR={LR}, AdamW, MSE")
print(f"{'='*80}")

for i, (nm, cfg) in enumerate(split_models.items(), 1):
    parts = nm.replace("_Raw","").split("_")
    size = parts[-1] if parts[-1] in EPOCH_MAP else "Medium"
    epochs = EPOCH_MAP.get(size, 1000)
    pt_exists = os.path.exists(os.path.join(MODELS_DIR, f"{nm}.pt"))
    in_csv = _model_in_csv(nm)
    if in_csv and pt_exists:
        # Model tamamlanmis: sadece evaluate (egitim yok, predictions + results icin)
        print(f"\n[{i:3d}/{len(split_models)}] {nm} - mevcut, evaluate...", end=" ", flush=True)
        r = train_dl(cfg, nm, epochs); results.extend(r)
        # save_inc atlanir — CSV'de zaten var
    elif pt_exists and not in_csv:
        # .pt var ama CSV'de yok — evaluate et ve CSV'ye ekle
        print(f"\n[{i:3d}/{len(split_models)}] {nm} - .pt mevcut, evaluate+save\n" + "-"*50); sys.stdout.flush()
        r = train_dl(cfg, nm, epochs); results.extend(r); save_inc(r)
    else:
        # Yeni model — egit
        print(f"\n[{i:3d}/{len(split_models)}] {nm} - {cfg['type']} ({epochs} epochs)\n" + "-"*50); sys.stdout.flush()
        r = train_dl(cfg, nm, epochs); results.extend(r); save_inc(r)


# ============================================================
# 11. Sklearn (joint 15-output)
# ============================================================
def mk_sk(nm):
    f = {
        "XGBoost": lambda: XGBRegressor(n_estimators=500, max_depth=10, learning_rate=0.05, tree_method="hist", device="cuda:0", random_state=SEED, n_jobs=-1),
        "LightGBM": lambda: LGBMRegressor(n_estimators=500, max_depth=10, learning_rate=0.05, num_leaves=128, random_state=SEED, n_jobs=-1, verbose=-1),
        "HistGradientBoosting": lambda: HistGradientBoostingRegressor(max_iter=1500, max_depth=12, learning_rate=0.05, max_leaf_nodes=128, random_state=SEED),
        "ExtraTrees": lambda: ExtraTreesRegressor(n_estimators=200, max_depth=20, min_samples_leaf=5, random_state=SEED, n_jobs=-1),
        "DecisionTree": lambda: DecisionTreeRegressor(max_depth=25, min_samples_leaf=5, random_state=SEED),
        "RandomForest": lambda: RandomForestRegressor(n_estimators=200, max_depth=20, min_samples_leaf=5, random_state=SEED, n_jobs=-1),
        "BaggingRegressor": lambda: BaggingRegressor(estimator=DecisionTreeRegressor(max_depth=20), n_estimators=100, max_samples=0.8, random_state=SEED, n_jobs=4),
        "AdaBoost": lambda: AdaBoostRegressor(n_estimators=50, learning_rate=0.05, estimator=DecisionTreeRegressor(max_depth=10), random_state=SEED),
        "SVR": lambda: BaggingRegressor(estimator=SVRegressor(kernel="rbf", C=1.0, epsilon=0.1), n_estimators=5, max_samples=0.05, random_state=SEED, n_jobs=4),
        "CatBoost": lambda: CatBoostRegressor(task_type="CPU", iterations=500, depth=10, learning_rate=0.05, random_seed=SEED, verbose=0),
    }
    return f[nm]()

MULTI_OUTPUT_WRAP = {"LightGBM", "HistGradientBoosting", "AdaBoost", "CatBoost", "SVR"}

print(f"\n{'='*80}\nSKLEARN - {len(sk_list)} MODEL (joint 15-output, MinMaxScaler X+y)\n{'='*80}")

for i, nm in enumerate(sk_list, 1):
    print(f"\n[{i:2d}/{len(sk_list)}] {nm}\n" + "-"*50); sys.stdout.flush()
    pkl_path = os.path.join(MODELS_DIR, f"{nm}.pkl")

    if os.path.exists(pkl_path):
        print(f"    Mevcut model yukleniyor (skip training)...", flush=True)
        m = joblib.load(pkl_path); tt = _get_existing_csv_value(_CSV, nm, "Train_Time(s)") or 0.0
    else:
        print(f"    Egitim (15-output joint)...", flush=True)
        m = mk_sk(nm)
        if nm in MULTI_OUTPUT_WRAP:
            m = MultiOutputRegressor(m)
        try:
            t0 = time.time()
            m.fit(X_train_sc, y_train_sc)
            tt = time.time()-t0
            joblib.dump(m, pkl_path)
        except Exception as e:
            print(f"    HATA: {str(e)[:80]} - model atlaniyor", flush=True)
            continue

        try:
            om = convert_sklearn(m, initial_types=[("input", FloatTensorType([None, IN_DIM]))])
            with open(os.path.join(MODELS_DIR, f"{nm}.onnx"), "wb") as f:
                f.write(om.SerializeToString())
        except Exception as e:
            print(f"    ONNX fail: {str(e)[:60]}")

    _ = m.predict(X_test_sc[:100])
    _ = m.predict(X_test_sc[:100])
    _ = m.predict(X_test_sc[:100])
    times_sk = []
    for _ in range(10):
        t1 = time.time(); _ = m.predict(X_test_sc); times_sk.append(time.time()-t1)
    it = float(np.mean(times_sk))
    throughput_sk = len(X_test_sc) / it if it > 0 else 0.0
    sk_size_mb = file_size_mb(pkl_path)

    # Param count approx: sum of all numpy arrays in model
    try:
        n_params_sk = int(sum(getattr(v, 'size', 0) for v in m.__dict__.values() if hasattr(v, 'size')))
    except: n_params_sk = 0

    test_preds_sc = m.predict(X_test_sc)
    val_preds_sc = m.predict(X_val_sc)

    d_pred_test, p_pred_test, e_pred_test = inverse_transform_predictions(test_preds_sc)
    d_pred_val, p_pred_val, e_pred_val = inverse_transform_predictions(val_preds_sc)

    all_test_preds[nm] = np.column_stack([d_pred_test, p_pred_test, e_pred_test])
    all_val_preds[nm] = np.column_stack([d_pred_val, p_pred_val, e_pred_val])

    met = compute_metrics(y_d_test, d_pred_test, yp_test_deg, p_pred_test,
                          y_e_test, e_pred_test, test_preds_sc, y_test_sc)
    print(f"  MSE:{met['scaled_mse']:.6f} | D:{met['d_r2']:.6f} | P:{met['p_cr2']:.6f} "
          f"| E:{met['e_r2']:.6f} | Comb:{met['combined_r2']:.6f} | {tt:.1f}s | {throughput_sk:.0f} s/s")

    d_r2_per = per_output_r2(y_d_test, d_pred_test, circ=False)
    p_r2_per = per_output_r2(yp_test_deg, p_pred_test, circ=True)
    row_po = {"Model": nm}
    for j, v in enumerate(d_r2_per): row_po[f"R2_D{j+1}"] = v
    for j, v in enumerate(p_r2_per): row_po[f"R2_P{j+1}"] = v
    row_po["R2_E"] = met["e_r2"]
    per_output_metrics_rows.append(row_po)

    row = mrow(nm, met, train_time=tt, inf_time=it, throughput=throughput_sk,
               params=n_params_sk, model_size_mb=sk_size_mb, epochs=0)
    results.append(row); save_inc([row])
    print(f"    OK ({tt:.1f}s)", flush=True); del m; gc.collect()


# ============================================================
# 11b. BASELINES (Linear, Mean, kNN — reviewer neyle karsilastirdin?)
# ============================================================
from sklearn.linear_model import LinearRegression
from sklearn.dummy import DummyRegressor
from sklearn.neighbors import KNeighborsRegressor

print(f"\n{'='*80}\nBASELINE MODELLER (makale referansi)\n{'='*80}")

baseline_list = [
    ("Baseline_Mean", lambda: DummyRegressor(strategy="mean")),
    ("Baseline_Linear", lambda: LinearRegression(n_jobs=-1)),
    ("Baseline_kNN5", lambda: KNeighborsRegressor(n_neighbors=5, n_jobs=-1)),
]

for nm, mk in baseline_list:
    print(f"\n  {nm}\n" + "-"*50); sys.stdout.flush()
    pkl_path = os.path.join(MODELS_DIR, f"{nm}.pkl")
    if os.path.exists(pkl_path):
        print(f"    Mevcut model yukleniyor (skip training)...", flush=True)
        m = joblib.load(pkl_path); tt = _get_existing_csv_value(_CSV, nm, "Train_Time(s)") or 0.0
    else:
        m = mk()
        t0 = time.time(); m.fit(X_train_sc, y_train_sc); tt = time.time()-t0
        joblib.dump(m, pkl_path)
    times_bl = []
    for _ in range(5):
        t1 = time.time(); _ = m.predict(X_test_sc); times_bl.append(time.time()-t1)
    it = float(np.mean(times_bl))
    throughput_bl = len(X_test_sc) / it if it > 0 else 0.0
    bl_size_mb = file_size_mb(pkl_path)

    test_preds_sc = m.predict(X_test_sc)
    val_preds_sc = m.predict(X_val_sc)
    d_pred_test, p_pred_test, e_pred_test = inverse_transform_predictions(test_preds_sc)
    d_pred_val, p_pred_val, e_pred_val = inverse_transform_predictions(val_preds_sc)

    all_test_preds[nm] = np.column_stack([d_pred_test, p_pred_test, e_pred_test])
    all_val_preds[nm] = np.column_stack([d_pred_val, p_pred_val, e_pred_val])

    met = compute_metrics(y_d_test, d_pred_test, yp_test_deg, p_pred_test,
                          y_e_test, e_pred_test, test_preds_sc, y_test_sc)
    print(f"  D:{met['d_r2']:.4f} | P:{met['p_cr2']:.4f} | E:{met['e_r2']:.4f} "
          f"| Comb:{met['combined_r2']:.4f}")
    row = mrow(nm, met, train_time=tt, inf_time=it, throughput=throughput_bl,
               params=0, model_size_mb=bl_size_mb, epochs=0)
    results.append(row); save_inc([row])
    del m; gc.collect()


# ============================================================
# 12. Ensemble & Stacking
# ============================================================
print(f"\n{'='*80}\nENSEMBLE & STACKING\n{'='*80}")

all_model_results = sorted(results, key=lambda x: x.get("Combined_R2", 0) if not np.isnan(x.get("Combined_R2", 0)) else -1, reverse=True)

# SK Top 5
sk_results = [r for r in all_model_results if r["Model"] in sk_list]
top5_sk_names = [r["Model"] for r in sk_results[:5]]

# DL Top 5 (sadece deep learning — sklearn ve baseline haric)
dl_exclude = set(sk_list) | {"Baseline_Mean", "Baseline_Linear", "Baseline_kNN5"}
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
for group_name, top_names in [("SK_Top5", top5_sk_names), ("DL_Top5", top5_dl_names), ("All_Top5", top5_all_names)]:
    for method, label in [("mean", f"Ensemble_{group_name}"), ("stacking", f"Stacking_{group_name}")]:
        avail = [n for n in top_names if n in all_test_preds]
        if len(avail) < 2:
            print(f"  {label}: yeterli tahmin yok ({len(avail)})"); continue

        if method == "mean":
            d_preds_list = [all_test_preds[n][:, :7] for n in avail]
            p_preds_list = [all_test_preds[n][:, 7:14] for n in avail]
            e_preds_list = [all_test_preds[n][:, 14] for n in avail]
            d_ens = np.mean(np.stack(d_preds_list), axis=0)
            p_ens = circular_mean_ensemble(p_preds_list, 7)
            e_ens = np.mean(np.stack(e_preds_list), axis=0)
        else:
            d_ens = np.zeros((len(y_d_test), 7))
            p_ens = np.zeros((len(yp_test_deg), 7))
            e_ens = np.zeros(len(y_e_test))
            avail_v = [n for n in avail if n in all_val_preds]
            if len(avail_v) < 2:
                print(f"  {label}: yeterli val tahmin yok"); continue
            # D stacking
            for j in range(7):
                tr_j = np.column_stack([all_val_preds[n][:, j] for n in avail_v])
                te_j = np.column_stack([all_test_preds[n][:, j] for n in avail_v])
                meta = RidgeCV(alphas=[0.001, 0.01, 0.1, 1.0, 10.0])
                meta.fit(tr_j, y_d_val[:, j])
                d_ens[:, j] = meta.predict(te_j)
            # P stacking (circular features)
            tr_feat_p = circular_stacking_features([all_val_preds[n][:, 7:14] for n in avail_v], 7)
            te_feat_p = circular_stacking_features([all_test_preds[n][:, 7:14] for n in avail_v], 7)
            for j in range(7):
                meta = RidgeCV(alphas=[0.001, 0.01, 0.1, 1.0, 10.0])
                meta.fit(tr_feat_p, yp_val_deg[:, j])
                p_ens[:, j] = meta.predict(te_feat_p)
            # E stacking
            tr_e = np.column_stack([all_val_preds[n][:, 14] for n in avail_v])
            te_e = np.column_stack([all_test_preds[n][:, 14] for n in avail_v])
            meta = RidgeCV(alphas=[0.001, 0.01, 0.1, 1.0, 10.0])
            meta.fit(tr_e, y_e_val)
            e_ens = meta.predict(te_e)

        # Build scaled predictions for ensemble (for scaled_mse metric)
        ens_pred_orig = np.column_stack([d_ens, p_ens, e_ens.reshape(-1, 1)])
        ens_pred_sc = scaler_y.transform(ens_pred_orig)

        ens_met = compute_metrics(y_d_test, d_ens, yp_test_deg, p_ens,
                                   y_e_test, e_ens, ens_pred_sc, y_test_sc)
        print(f"  {label}: D={ens_met['d_r2']:.6f} | P={ens_met['p_cr2']:.6f} "
              f"| E={ens_met['e_r2']:.6f} | Comb={ens_met['combined_r2']:.6f}")
        ens_rl.append(mrow(label, ens_met, train_time=0, inf_time=0,
                           throughput=0, params=0, model_size_mb=0, epochs=0))

results.extend(ens_rl); save_inc(ens_rl)
print("Ensemble & Stacking tamamlandi")


# ============================================================
# 13. Final Results Table
# ============================================================
print(f"\n\n{'='*80}\nSONUC TABLOSU\n{'='*80}")
rs = sorted(results, key=lambda x: x.get("Combined_R2", 0) if not np.isnan(x.get("Combined_R2", 0)) else -1, reverse=True)

td = [[r["Model"], f"{r.get('Combined_R2', 0):.6f}",
       f"{r.get('D_R2', 0):.6f}", f"{r.get('P_cR2', 0):.6f}", f"{r.get('E_R2', 0):.6f}",
       f"{r.get('D_MAE', 0):.4f}", f"{r.get('P_cMAE_deg', 0):.4f}", f"{r.get('E_MAE', 0):.6f}",
       f"{r.get('D_MaxAE', 0):.4f}", f"{r.get('P_cMaxAE_deg', 0):.2f}",
       f"{r.get('Train_Time(s)', 0):.1f}", f"{r.get('Throughput_samples_s', 0):.0f}",
       f"{r.get('ModelSize_MB', 0):.2f}", f"{r.get('Params', 0)}"]
      for r in rs if not np.isnan(r.get("Combined_R2", 0))]

if rs:
    print(tabulate(td[:30], headers=["Model", "Comb", "D_R2", "P_cR2", "E_R2",
                                      "D_MAE", "P_cMAE", "E_MAE", "D_Max", "P_Max",
                                      "Train(s)", "Thr(s/s)", "Size(MB)", "Params"],
                   tablefmt="simple_grid", stralign="right"))
    b = rs[0]
    print(f"\nEN IYI -> {b['Model']} | Combined_R2: {b.get('Combined_R2', 0):.6f}")

# Merge: mevcut CSV ile results birlestir (overwrite degil!)
_new_df = pd.DataFrame(rs)
_existing_csv = _load_existing_csv()
if not _existing_csv.empty:
    _keep = _existing_csv[~_existing_csv['Model'].isin(_new_df['Model'].values)]
    _final = pd.concat([_keep, _new_df], ignore_index=True)
    for c in CSV_COLS:
        if c not in _final.columns: _final[c] = 0
    _final = _final.sort_values('Combined_R2', ascending=False).reset_index(drop=True)
    _final[CSV_COLS].to_csv(_CSV, index=False)
else:
    _new_df.to_csv(_CSV, index=False)

if per_output_metrics_rows:
    pd.DataFrame(per_output_metrics_rows).to_csv(
        os.path.join(MODELS_DIR, "per_output_metrics.csv"), index=False)


# ============================================================
# 14. Post-Training Analyses
# ============================================================
print(f"\n\n{'='*80}\nPOST-TRAINING ANALIZLERI\n{'='*80}")

all_valid = [r for r in rs if not np.isnan(r.get("Combined_R2", 0))]
if not all_valid:
    print("UYARI: Hic sonuc yok")
    sys.exit(0)

indiv_results = [r for r in all_valid if "Ensemble" not in r["Model"] and "Stacking" not in r["Model"]]
best_name = indiv_results[0]["Model"] if indiv_results else all_valid[0]["Model"]
best_result = all_valid[0]
print(f"En iyi model: {best_name}")

# --- Convergence speed ---
print("\n--- Convergence Speed (90% of final) ---")
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

# --- Family summary ---
print("\n--- Family Summary ---")
family_map = {
    "MLP": "MLP", "CNN1D": "CNN", "SimpleRNN": "RNN", "GRU": "GRU", "LSTM": "LSTM",
    "BiGRU": "BiGRU", "BiLSTM": "BiLSTM", "CNN_RNN": "CNN-RNN", "CNN_LSTM": "CNN-LSTM",
    "CNN_GRU": "CNN-GRU", "CNN_BiLSTM": "CNN-BiLSTM", "CNN_BiGRU": "CNN-BiGRU",
    "ResNet": "ResNet", "TabNet": "TabNet",
    "XGBoost": "XGBoost", "LightGBM": "LightGBM", "HistGradientBoosting": "HistGB",
    "ExtraTrees": "ExtraTrees", "DecisionTree": "DecisionTree", "RandomForest": "RandomForest",
    "BaggingRegressor": "Bagging", "AdaBoost": "AdaBoost", "CatBoost": "CatBoost",
}
family_data = {}
for r in all_valid:
    nm = r["Model"]
    if "Ensemble" in nm or "Stacking" in nm: continue
    if np.isnan(r.get("Combined_R2", 0)): continue
    fam = None
    for prefix, family in sorted(family_map.items(), key=lambda x: -len(x[0])):
        if nm.startswith(prefix): fam = family; break
    if fam is None: continue
    if fam not in family_data: family_data[fam] = []
    family_data[fam].append(r)

fam_rows = []
for fam, recs in family_data.items():
    fam_rows.append({
        "Family": fam, "N_Models": len(recs),
        "Combined_R2_mean": np.mean([r.get("Combined_R2", 0) for r in recs]),
        "Combined_R2_best": max(r.get("Combined_R2", 0) for r in recs),
        "D_MAE_mean": np.mean([r.get("D_MAE", 0) for r in recs]),
        "P_cMAE_deg_mean": np.mean([r.get("P_cMAE_deg", 0) for r in recs]),
        "E_MAE_mean": np.mean([r.get("E_MAE", 0) for r in recs]),
        "Train_Time_mean": np.mean([r.get("Train_Time(s)", 0) for r in recs]),
    })
if fam_rows:
    pd.DataFrame(fam_rows).to_csv(os.path.join(MODELS_DIR, "family_summary.csv"), index=False)
    print(f"  -> family_summary.csv")

# --- Per-organ evaluation (organ bazinda performance) ---
print("\n--- Per-Organ Evaluation (Top-5) ---")
organ_rows = []
test_organ_ids = df.iloc[idx_test]["organ_id"].values
for r in all_valid[:5]:
    nm = r["Model"]
    if nm not in all_test_preds: continue
    preds = all_test_preds[nm]
    d_pred = preds[:, :7]; p_pred = preds[:, 7:14]; e_pred = preds[:, 14]
    for oid in ORGAN_IDS:
        mask = test_organ_ids == oid
        if mask.sum() < 2: continue
        d_r2 = float(r2_score(y_d_test[mask], d_pred[mask]))
        p_cr2 = float(circ_r2(yp_test_deg[mask], p_pred[mask]))
        try:
            e_r2 = float(r2_score(y_e_test[mask], e_pred[mask]))
        except: e_r2 = float("nan")
        organ_rows.append({"Model": nm, "organ_id": oid, "N": int(mask.sum()),
                           "D_R2": d_r2, "P_cR2": p_cr2, "E_R2": e_r2,
                           "Combined": (d_r2 + p_cr2 + e_r2) / 3.0})
if organ_rows:
    pd.DataFrame(organ_rows).to_csv(os.path.join(MODELS_DIR, "per_organ_metrics.csv"), index=False)
    print(f"  -> per_organ_metrics.csv")

# --- Bootstrap 95% CI (Top-10) ---
print("\n--- Bootstrap 95% CI (Top-10) ---")
n_boot = 1000
ci_rows = []
for r in all_valid[:10]:
    nm = r["Model"]
    if nm not in all_test_preds: continue
    preds = all_test_preds[nm]
    d_pred = preds[:, :7]; p_pred = preds[:, 7:14]; e_pred = preds[:, 14]
    n_samples = len(y_d_test)
    boot_r2s = []
    rng = np.random.RandomState(SEED)
    for _ in range(n_boot):
        idx_b = rng.choice(n_samples, n_samples, replace=True)
        r2_d = r2_score(y_d_test[idx_b], d_pred[idx_b])
        r2_p = circ_r2(yp_test_deg[idx_b], p_pred[idx_b])
        r2_e = r2_score(y_e_test[idx_b], e_pred[idx_b])
        boot_r2s.append((r2_d + r2_p + r2_e) / 3.0)
    boot_r2s = np.array(boot_r2s)
    ci_rows.append({
        "Model": nm, "R2_mean": np.mean(boot_r2s), "R2_std": np.std(boot_r2s),
        "CI_lower_2.5": np.percentile(boot_r2s, 2.5),
        "CI_upper_97.5": np.percentile(boot_r2s, 97.5)
    })
    print(f"  {nm}: {np.mean(boot_r2s):.6f} [{np.percentile(boot_r2s,2.5):.6f}, {np.percentile(boot_r2s,97.5):.6f}]")
if ci_rows:
    pd.DataFrame(ci_rows).to_csv(os.path.join(MODELS_DIR, "bootstrap_ci.csv"), index=False)


# --- Noise Robustness (Top-5, noise 1%/5%/10%) ---
print("\n--- Noise Robustness (Top-5) ---")
noise_rows = []
noise_levels = [0.01, 0.05, 0.10]
rng_noise = np.random.RandomState(SEED)

for r in all_valid[:5]:
    nm = r["Model"]
    if "Ensemble" in nm or "Stacking" in nm: continue
    base_r2 = r.get("Combined_R2", 0)
    cfg = split_models.get(nm)
    pt_path = os.path.join(MODELS_DIR, f"{nm}.pt")
    pkl_path = os.path.join(MODELS_DIR, f"{nm}.pkl")

    for noise_pct in noise_levels:
        noise_std = noise_pct * np.std(X_test_sc, axis=0)
        Xte_noisy = X_test_sc + rng_noise.randn(*X_test_sc.shape) * noise_std

        if cfg is not None and os.path.exists(pt_path):
            mdl = create_model(cfg, OUT_DIM, IN_DIM).to(DEVICE)
            mdl.load_state_dict(torch.load(pt_path, map_location=DEVICE)); mdl.eval()
            with torch.no_grad(), torch.cuda.amp.autocast():
                yps = mdl(torch.FloatTensor(Xte_noisy.astype(np.float32)).to(DEVICE)).cpu().numpy()
            del mdl; torch.cuda.empty_cache()
        elif os.path.exists(pkl_path):
            mdl_sk = joblib.load(pkl_path)
            yps = mdl_sk.predict(Xte_noisy.astype(np.float32))
            del mdl_sk
        else:
            continue

        d_p, p_p, e_p = inverse_transform_predictions(yps)
        d_r2 = float(r2_score(y_d_test, d_p))
        p_cr2 = float(circ_r2(yp_test_deg, p_p))
        e_r2 = float(r2_score(y_e_test, e_p))
        comb = (d_r2 + p_cr2 + e_r2) / 3.0
        noise_rows.append({
            "Model": nm, "Noise_Level": f"{noise_pct*100:.0f}%",
            "D_R2": d_r2, "P_cR2": p_cr2, "E_R2": e_r2,
            "Combined_R2": comb, "R2_Drop": base_r2 - comb
        })
        print(f"  {nm} @ {noise_pct*100:.0f}%: Comb={comb:.4f} (drop={base_r2-comb:+.4f})")
if noise_rows:
    pd.DataFrame(noise_rows).to_csv(os.path.join(MODELS_DIR, "noise_robustness.csv"), index=False)


# --- TabNet attention masks (en iyi TabNet) ---
print("\n--- TabNet Attention Masks ---")
tabnet_models = [r for r in all_valid if "TabNet" in r["Model"]
                 and "Ensemble" not in r["Model"] and "Stacking" not in r["Model"]]
if tabnet_models:
    best_tn = tabnet_models[0]["Model"]
    pt_path = os.path.join(MODELS_DIR, f"{best_tn}.pt")
    cfg_tn = split_models.get(best_tn)
    if cfg_tn is not None and os.path.exists(pt_path):
        mdl = create_model(cfg_tn, OUT_DIM, IN_DIM).to(DEVICE)
        mdl.load_state_dict(torch.load(pt_path, map_location=DEVICE)); mdl.eval()
        sample = torch.FloatTensor(X_test_sc[:1000]).to(DEVICE)
        with torch.no_grad():
            masks = mdl.get_attention_masks(sample)
        np.save(os.path.join(MODELS_DIR, "tabnet_attention.npy"), np.array(masks))
        # Per-feature average attention
        feat_names = ["x", "y", "z", "target_B"] + [f"organ_{o}" for o in ORGAN_IDS]
        avg_mask = np.mean([m.mean(axis=0) for m in masks], axis=0)
        att_df = pd.DataFrame({"Feature": feat_names, "MeanAttention": avg_mask})
        att_df.to_csv(os.path.join(MODELS_DIR, "tabnet_attention_summary.csv"), index=False)
        print(f"  {best_tn}: {dict(zip(feat_names, avg_mask.round(4)))}")
        del mdl; torch.cuda.empty_cache()
else:
    print("  TabNet modeli bulunamadi")


# --- Pareto Frontier Data ---
print("\n--- Pareto Data (params/time/size vs R²) ---")
pareto_rows = []
for r in all_valid:
    if "Ensemble" in r["Model"] or "Stacking" in r["Model"]: continue
    pareto_rows.append({
        "Model": r["Model"],
        "Combined_R2": r.get("Combined_R2", 0),
        "D_R2": r.get("D_R2", 0),
        "P_cR2": r.get("P_cR2", 0),
        "E_R2": r.get("E_R2", 0),
        "Params": r.get("Params", 0),
        "ModelSize_MB": r.get("ModelSize_MB", 0),
        "Train_Time_s": r.get("Train_Time(s)", 0),
        "Inference_Time_s": r.get("Inference_Time(s)", 0),
        "Throughput": r.get("Throughput_samples_s", 0),
    })
if pareto_rows:
    pd.DataFrame(pareto_rows).to_csv(os.path.join(MODELS_DIR, "pareto_data.csv"), index=False)
    print(f"  -> pareto_data.csv ({len(pareto_rows)} models)")


# --- Predictions dump (analysis_kedi.py icin) ---
print("\n--- Predictions dump (npz) ---")
pred_save = {}
for nm, p in all_test_preds.items():
    pred_save[f"{nm}__test"] = p.astype(np.float32)
for nm, p in all_val_preds.items():
    pred_save[f"{nm}__val"] = p.astype(np.float32)
pred_save["y_d_test"] = y_d_test.astype(np.float32)
pred_save["yp_test_deg"] = yp_test_deg.astype(np.float32)
pred_save["y_e_test"] = y_e_test.astype(np.float32)
pred_save["y_d_val"] = y_d_val.astype(np.float32)
pred_save["yp_val_deg"] = yp_val_deg.astype(np.float32)
pred_save["y_e_val"] = y_e_val.astype(np.float32)
pred_save["X_test_sc"] = X_test_sc.astype(np.float32)
pred_save["X_val_sc"] = X_val_sc.astype(np.float32)
pred_save["X_train_sc"] = X_train_sc.astype(np.float32)
pred_save["y_train_sc"] = y_train_sc.astype(np.float32)
pred_save["test_organ_ids"] = df.iloc[idx_test]["organ_id"].values.astype(np.int32)
pred_save["val_organ_ids"] = df.iloc[idx_val]["organ_id"].values.astype(np.int32)
pred_save["train_organ_ids"] = df.iloc[idx_train]["organ_id"].values.astype(np.int32)
np.savez_compressed(os.path.join(MODELS_DIR, "predictions.npz"), **pred_save)
print(f"  -> predictions.npz ({len(all_test_preds)} models)")


# --- Experiment config JSON ---
config = {
    "seed": SEED,
    "approach": "petri — CircularMSE for P, shuffle + stratified, BS=16384",
    "in_dim": IN_DIM,
    "out_dim": OUT_DIM,
    "epoch_map": EPOCH_MAP,
    "batch_size": BS,
    "learning_rate": LR,
    "optimizer": "AdamW",
    "loss": "MSE",
    "dataset": {
        "path": CSV_PATH,
        "total_rows": len(df),
        "train_size": len(idx_train),
        "val_size": len(idx_val),
        "test_size": len(idx_test),
        "split_ratio": "80/10/10",
        "stratified_on": "organ_id",
        "organ_ids": ORGAN_IDS,
        "input_columns": ["x", "y", "z", "target_B"] + [f"organ_{o}" for o in ORGAN_IDS],
        "output_columns": d_cols + p_cols + [e_col],
    },
    "preprocessing": {
        "dataset_shuffle": True,
        "X_scaler": "MinMaxScaler",
        "y_scaler": "MinMaxScaler (joint D+P+E)",
        "organ_encoding": "one-hot",
    },
    "models": {
        "dl_models": len(split_models),
        "sklearn_models": len(sk_list),
    },
}
with open(os.path.join(MODELS_DIR, "experiment_config.json"), "w") as f:
    json.dump(config, f, indent=2, default=str)

print(f"\n{'='*80}\nTUM EGITIM TAMAMLANDI -> {_CSV}\n{'='*80}")
