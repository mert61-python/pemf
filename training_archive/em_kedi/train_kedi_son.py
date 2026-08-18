# -*- coding: utf-8 -*-
"""
EĞİTİM — KEDİ v2 (Profesyonel)
══════════════════════════════════════════════════════════════════════════════
Veri dosyası : training_data_kedi_v4.csv
              (veri_kedi_son.py çıktısı — sütunlar: x,y,z, D1-D7, P1-P7,
               achieved_B, result_E, duty_sum, organ_id [0-6])

Mimari       : FiLM ResNet (Multi-head, 7 organ)
Çıktı        : 7×D  +  7×sinP  +  7×cosP  +  1×E  =  22 değer
Fizik kısıtı : sin²+cos² = 1  |  P1 her zaman 0 (veri üretiminde sabitlendi)
Metrikler    : Her epoch → R², MSE, RMSE, MAE (gerçek birim)
ONNX Export  : ResNet_kedi_v2.onnx  (input: [batch, INPUT_DIM])
══════════════════════════════════════════════════════════════════════════════
"""

import os
import pandas as pd
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
import torch.nn.functional as F
from torch.utils.data import Dataset, DataLoader, WeightedRandomSampler
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import r2_score, mean_squared_error, mean_absolute_error
import joblib

print("🧠 KEDİ EĞİTİM v2 — FiLM ResNet Multi-Head (7 Organ)\n")

# ══════════════════════════════════════════════════════════════════════════════
# HİPERPARAMETRELER
# ══════════════════════════════════════════════════════════════════════════════
EPOCHS        = 800
BATCH_SIZE    = 256
LR            = 2e-3
PATIENCE      = 80
WARMUP_EPOCHS = 30
HIDDEN        = 768
N_BLOCKS      = 10
DROPOUT       = 0.25
NUM_CLASSES   = 7   # 0:kutu, 1:mide, 2:böbrek, 3:karaciğer, 4:mesane, 5:pankreas, 6:bağırsak

LAMBDA_PHASE      = 0.5
LAMBDA_E          = 0.1
LAMBDA_DUTY_REG   = 0.001
LAMBDA_DUTY_CLIP  = 0.01
LAMBDA_PHASE_CONS = 0.05

# Küçük/zor organlara daha fazla ağırlık
ORGAN_LOSS_W = {0: 0.5, 1: 1.0, 2: 1.5, 3: 1.0, 4: 2.0, 5: 1.2, 6: 1.2}

# ══════════════════════════════════════════════════════════════════════════════
# DOSYA YOLLARI
# ══════════════════════════════════════════════════════════════════════════════
BASE_DIR        = os.path.dirname(os.path.abspath(__file__))
DATA_PATH       = os.path.join(BASE_DIR, "training_data_kedi_v5.csv")    # DÜZELTİLDİ: v1→v4
MODEL_PTH_PATH  = os.path.join(BASE_DIR, "best_kedi_model.pth")
MODEL_ONNX_PATH = os.path.join(BASE_DIR, "ResNet_kedi_v2.onnx")
SCALER_X_PATH   = os.path.join(BASE_DIR, "scaler_X_kedi_v2.pkl")
SCALER_Y_PATH   = os.path.join(BASE_DIR, "scaler_y_kedi_v2.pkl")
HISTORY_PATH    = os.path.join(BASE_DIR, "training_history_kedi.csv")

# ══════════════════════════════════════════════════════════════════════════════
# VERİ HAZIRLIĞI
# ══════════════════════════════════════════════════════════════════════════════
df = pd.read_csv(DATA_PATH)
print(f"📊 Veri seti   : {len(df):,} satır  |  Organ dağılımı:")
organ_names = {0:'kutu_butun', 1:'mide', 2:'bobrek', 3:'karaciger', 4:'mesane', 5:'pankreas', 6:'bagirsak'}
for oid, cnt in df['organ_id'].value_counts().sort_index().items():
    print(f"    Organ {int(oid):d} ({organ_names.get(int(oid), '?'):>12s}): {cnt:>7,}")
print()

X_coords = df[['x', 'y', 'z']].values.astype(np.float32)
X_organs = df['organ_id'].values.astype(np.float32).reshape(-1, 1)

# Ek fiziksel özellikler
extra_feats = []
for col in ['achieved_B', 'duty_sum']:
    if col in df.columns:
        extra_feats.append(df[col].values.reshape(-1, 1))
        print(f"  ✅ Ek feature: {col}")

D_data     = df[[f'D{i}' for i in range(1, 8)]].values
P_data_rad = np.radians(df[[f'P{i}' for i in range(1, 8)]].values)
E_data     = df[['result_E']].values

y_data = np.hstack([D_data, np.sin(P_data_rad), np.cos(P_data_rad), E_data]).astype(np.float32)
# Çıktı: [D1..D7 | sinP1..sinP7 | cosP1..cosP7 | E] = 22

# ── Ölçekleme ─────────────────────────────────────────────────────────────────
scaler_X    = StandardScaler()
X_coords_sc = scaler_X.fit_transform(X_coords)

if extra_feats:
    extra        = np.hstack(extra_feats).astype(np.float32)
    scaler_extra = StandardScaler()
    extra_sc     = scaler_extra.fit_transform(extra)
    X_sc         = np.hstack([X_coords_sc, X_organs, extra_sc])
    INPUT_DIM    = 3 + 1 + extra.shape[1]
    joblib.dump(scaler_extra, os.path.join(BASE_DIR, "scaler_extra_kedi.pkl"))
else:
    X_sc      = np.hstack([X_coords_sc, X_organs])
    INPUT_DIM = 4

scaler_y = StandardScaler()
y_sc     = scaler_y.fit_transform(y_data)

joblib.dump(scaler_X, SCALER_X_PATH)
joblib.dump(scaler_y, SCALER_Y_PATH)
print(f"\n  Input dim  : {INPUT_DIM}  |  Output dim : {y_data.shape[1]}")
print(f"  Scalerlar kaydedildi.\n")

# ── Train / Val Bölme ─────────────────────────────────────────────────────────
X_tr, X_val, y_tr, y_val, org_tr, org_val = train_test_split(
    X_sc.astype(np.float32), y_sc.astype(np.float32),
    X_organs,
    test_size=0.15, random_state=42,
    stratify=X_organs.astype(int)
)
print(f"  Eğitim: {len(X_tr):,}  |  Doğrulama: {len(X_val):,}\n")

# ══════════════════════════════════════════════════════════════════════════════
# DATASET
# ══════════════════════════════════════════════════════════════════════════════
class EMDataset(Dataset):
    def __init__(self, X, y, orgs, augment=False):
        self.X       = torch.tensor(X,    dtype=torch.float32)
        self.y       = torch.tensor(y,    dtype=torch.float32)
        self.orgs    = torch.tensor(orgs, dtype=torch.long).squeeze()
        self.augment = augment

    def __len__(self): return len(self.X)

    def __getitem__(self, idx):
        x, y = self.X[idx].clone(), self.y[idx]
        if self.augment and torch.rand(1).item() < 0.4:
            x[:3] += torch.randn(3) * 0.015   # Koordinat augmentasyonu
        return x, y, self.orgs[idx]

train_ds = EMDataset(X_tr, y_tr, org_tr, augment=True)
val_ds   = EMDataset(X_val, y_val, org_val, augment=False)

class_counts   = np.bincount(org_tr.astype(int).flatten(), minlength=NUM_CLASSES)
sample_weights = (1.0 / (class_counts + 1e-5))[org_tr.astype(int).flatten()]
sampler        = WeightedRandomSampler(sample_weights, len(sample_weights), replacement=True)

train_loader = DataLoader(train_ds, batch_size=BATCH_SIZE, sampler=sampler,  num_workers=0, pin_memory=True)
val_loader   = DataLoader(val_ds,   batch_size=BATCH_SIZE, shuffle=False,    num_workers=0, pin_memory=True)

# ══════════════════════════════════════════════════════════════════════════════
# MODEL MİMARİSİ
# ══════════════════════════════════════════════════════════════════════════════
class FiLMLayer(nn.Module):
    def __init__(self, num_classes: int, num_features: int):
        super().__init__()
        self.gamma = nn.Embedding(num_classes, num_features)
        self.beta  = nn.Embedding(num_classes, num_features)
        nn.init.ones_(self.gamma.weight)
        nn.init.zeros_(self.beta.weight)

    def forward(self, x, cls_id):
        return x * self.gamma(cls_id) + self.beta(cls_id)


class ResBlock(nn.Module):
    def __init__(self, hidden: int, num_classes: int, dropout: float = 0.25):
        super().__init__()
        self.ln1   = nn.LayerNorm(hidden)
        self.lin1  = nn.Linear(hidden, hidden)
        self.film1 = FiLMLayer(num_classes, hidden)
        self.act1  = nn.Mish()
        self.drop1 = nn.Dropout(dropout)

        self.ln2   = nn.LayerNorm(hidden)
        self.lin2  = nn.Linear(hidden, hidden)
        self.film2 = FiLMLayer(num_classes, hidden)
        self.act2  = nn.Mish()
        self.drop2 = nn.Dropout(dropout)

    def forward(self, x, org_id):
        h = self.drop1(self.act1(self.film1(self.lin1(self.ln1(x)), org_id)))
        h = self.drop2(self.act2(self.film2(self.lin2(self.ln2(h)), org_id)))
        return x + h


class EAlanAI(nn.Module):
    """
    Girdi : [x, y, z, organ_id, (achieved_B, duty_sum)]  → (B, INPUT_DIM)
    Çıktı : [D1..D7, sinP1..sinP7, cosP1..cosP7, E] → (B, 22)
    """
    def __init__(self, input_dim: int = 4, hidden: int = HIDDEN,
                 num_classes: int = NUM_CLASSES, blocks: int = N_BLOCKS,
                 dropout: float = DROPOUT):
        super().__init__()
        self.input_dim = input_dim
        extra_dim      = input_dim - 4

        self.coord_proj = nn.Sequential(
            nn.Linear(3, hidden),
            nn.LayerNorm(hidden),
            nn.Mish()
        )
        self.extra_proj = nn.Linear(extra_dim, hidden) if extra_dim > 0 else None

        self.blocks = nn.ModuleList(
            [ResBlock(hidden, num_classes, dropout) for _ in range(blocks)]
        )

        self.head_D    = nn.Sequential(nn.Linear(hidden, 128), nn.Mish(), nn.Linear(128, 7))
        self.head_sinP = nn.Sequential(nn.Linear(hidden, 128), nn.Mish(), nn.Linear(128, 7))
        self.head_cosP = nn.Sequential(nn.Linear(hidden, 128), nn.Mish(), nn.Linear(128, 7))
        self.head_E    = nn.Sequential(nn.Linear(hidden,  64), nn.Mish(), nn.Linear(64,  1))

    def forward(self, x):
        coords = x[:, :3]
        org_id = x[:, 3].long()
        extra  = x[:, 4:] if self.input_dim > 4 else None

        h = self.coord_proj(coords)
        if extra is not None and self.extra_proj is not None:
            h = h + self.extra_proj(extra)

        for blk in self.blocks:
            h = blk(h, org_id)

        return torch.cat([
            self.head_D(h),
            self.head_sinP(h),
            self.head_cosP(h),
            self.head_E(h)
        ], dim=1)


# ══════════════════════════════════════════════════════════════════════════════
# OPTİMİZATÖR & KAYIP
# ══════════════════════════════════════════════════════════════════════════════
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
model  = EAlanAI(input_dim=INPUT_DIM).to(device)

total_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
print(f"📦 Model parametresi : {total_params:,}")
print(f"⚡ Cihaz             : {device}\n")

optimizer = optim.AdamW(model.parameters(), lr=1e-5, weight_decay=5e-4)

def warmup_cosine(epoch: int) -> float:
    if epoch < WARMUP_EPOCHS:
        return LR * (epoch + 1) / WARMUP_EPOCHS / 1e-5
    progress = (epoch - WARMUP_EPOCHS) / max(1, EPOCHS - WARMUP_EPOCHS)
    return (1e-5 + 0.5 * (LR - 1e-5) * (1 + np.cos(np.pi * progress))) / 1e-5

scheduler = optim.lr_scheduler.LambdaLR(optimizer, lr_lambda=warmup_cosine)

organ_w = torch.tensor(
    [ORGAN_LOSS_W[i] for i in range(NUM_CLASSES)],
    device=device, dtype=torch.float32
)

def custom_loss(pred: torch.Tensor, true: torch.Tensor,
                org_ids: torch.Tensor) -> torch.Tensor:
    w = organ_w[org_ids].unsqueeze(1)

    loss_D   = (F.mse_loss(pred[:, 0:7],   true[:, 0:7],   reduction='none') * w).mean()
    loss_sin = (F.mse_loss(pred[:, 7:14],  true[:, 7:14],  reduction='none') * w).mean()
    loss_cos = (F.mse_loss(pred[:, 14:21], true[:, 14:21], reduction='none') * w).mean()
    loss_E   = (F.huber_loss(pred[:, 21:22], true[:, 21:22],
                              delta=1.0, reduction='none') * w).mean()

    sinP, cosP     = pred[:, 7:14], pred[:, 14:21]
    phase_cons     = F.mse_loss(sinP**2 + cosP**2, torch.ones_like(sinP))

    duty_reg  = pred[:, 0:7].mean()
    duty_clip = F.relu(pred[:, 0:7] - 3.0).mean()

    loss_main = (loss_D
                 + LAMBDA_PHASE * (loss_sin + loss_cos)
                 + LAMBDA_E * loss_E
                 + LAMBDA_PHASE_CONS * phase_cons)

    return loss_main + LAMBDA_DUTY_REG * duty_reg + LAMBDA_DUTY_CLIP * duty_clip


# ══════════════════════════════════════════════════════════════════════════════
# EĞİTİM DÖNGÜSÜ
# ══════════════════════════════════════════════════════════════════════════════
best_val     = float('inf')
patience_ctr = 0
history      = []

print(f"{'Ep':>4} | {'TrLoss':>8} | {'ValLoss':>8} | {'R²':>7} | "
      f"{'MSE':>10} | {'RMSE':>9} | {'MAE':>9} | "
      f"{'RMSE_D':>8} | {'RMSE_P':>8} | {'RMSE_E':>8} | {'LR':>9}")
print("─" * 110)

for epoch in range(EPOCHS):
    # ── Eğitim ────────────────────────────────────────────────────────────────
    model.train()
    tr_loss = 0.0
    for Xb, yb, ob in train_loader:
        Xb, yb, ob = Xb.to(device), yb.to(device), ob.to(device)
        optimizer.zero_grad()
        loss = custom_loss(model(Xb), yb, ob)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
        optimizer.step()
        tr_loss += loss.item()
    scheduler.step()

    # ── Doğrulama ─────────────────────────────────────────────────────────────
    model.eval()
    val_loss   = 0.0
    preds_list, trues_list = [], []
    with torch.no_grad():
        for Xb, yb, ob in val_loader:
            Xb, yb, ob = Xb.to(device), yb.to(device), ob.to(device)
            p = model(Xb)
            val_loss += custom_loss(p, yb, ob).item()
            preds_list.append(p.cpu().numpy())
            trues_list.append(yb.cpu().numpy())

    tr_loss  /= len(train_loader)
    val_loss /= len(val_loader)

    p_orig = scaler_y.inverse_transform(np.vstack(preds_list))
    t_orig = scaler_y.inverse_transform(np.vstack(trues_list))

    r2     = r2_score(t_orig, p_orig)
    mse    = mean_squared_error(t_orig, p_orig)
    rmse   = np.sqrt(mse)
    mae    = mean_absolute_error(t_orig, p_orig)
    rmse_D = np.sqrt(mean_squared_error(t_orig[:, 0:7],   p_orig[:, 0:7]))
    rmse_P = np.sqrt(mean_squared_error(t_orig[:, 7:21],  p_orig[:, 7:21]))
    rmse_E = np.sqrt(mean_squared_error(t_orig[:, 21:22], p_orig[:, 21:22]))
    lr_now = optimizer.param_groups[0]['lr']

    print(f"{epoch:4d} | {tr_loss:8.4f} | {val_loss:8.4f} | {r2:7.4f} | "
          f"{mse:10.6f} | {rmse:9.6f} | {mae:9.6f} | "
          f"{rmse_D:8.6f} | {rmse_P:8.4f} | {rmse_E:8.4f} | {lr_now:9.2e}")

    history.append({
        "epoch": epoch, "tr_loss": tr_loss, "val_loss": val_loss,
        "r2": r2, "mse": mse, "rmse": rmse, "mae": mae,
        "rmse_D": rmse_D, "rmse_P": rmse_P, "rmse_E": rmse_E, "lr": lr_now
    })

    if val_loss < best_val:
        best_val     = val_loss
        patience_ctr = 0
        torch.save(model.state_dict(), MODEL_PTH_PATH)
    else:
        patience_ctr += 1
        if patience_ctr >= PATIENCE:
            print(f"\n🛑 Early stopping @ Ep {epoch}  (best val: {best_val:.6f})")
            break

# ══════════════════════════════════════════════════════════════════════════════
# ONNX EXPORT
# ══════════════════════════════════════════════════════════════════════════════
model.load_state_dict(torch.load(MODEL_PTH_PATH, weights_only=True))
model.eval()

dummy = torch.randn(1, INPUT_DIM).to(device)
torch.onnx.export(
    model, dummy, MODEL_ONNX_PATH,
    export_params=True, opset_version=14, do_constant_folding=True,
    input_names=['input_coords'], output_names=['outputs'],
    dynamic_axes={'input_coords': {0: 'batch_size'}, 'outputs': {0: 'batch_size'}}
)
print(f"\n🎉 ONNX export tamam : {MODEL_ONNX_PATH}")

pd.DataFrame(history).to_csv(HISTORY_PATH, index=False)
print(f"📊 Eğitim geçmişi    : {HISTORY_PATH}")

# ── Per-organ R² ──────────────────────────────────────────────────────────────
print("\n📊 Organ bazlı Val R² (en iyi epoch):")
model.eval()
all_p, all_t, all_o = [], [], []
with torch.no_grad():
    for Xb, yb, ob in val_loader:
        Xb, yb = Xb.to(device), yb.to(device)
        all_p.append(model(Xb).cpu().numpy())
        all_t.append(yb.cpu().numpy())
        all_o.append(ob.numpy())

p_orig_f = scaler_y.inverse_transform(np.vstack(all_p))
t_orig_f = scaler_y.inverse_transform(np.vstack(all_t))
o_all    = np.concatenate(all_o).flatten()

for oid in range(NUM_CLASSES):
    mask = o_all == oid
    if mask.sum() < 10: continue
    r2_o = r2_score(t_orig_f[mask], p_orig_f[mask])
    print(f"  Organ {oid} ({organ_names.get(oid,'?'):>12s}): R² = {r2_o:.4f}  (n={mask.sum():,})")

# ── Final özet ────────────────────────────────────────────────────────────────
best_row = min(history, key=lambda r: r['val_loss'])
print("\n" + "═" * 60)
print("✅ EN İYİ MODEL (Val seti, gerçek birim):")
print("═" * 60)
print(f"  Epoch        : {int(best_row['epoch'])}")
print(f"  R²           : {best_row['r2']:.6f}")
print(f"  MSE          : {best_row['mse']:.8f}")
print(f"  RMSE (genel) : {best_row['rmse']:.6f}")
print(f"  MAE  (genel) : {best_row['mae']:.6f}")
print(f"  RMSE Duty    : {best_row['rmse_D']:.6f}")
print(f"  RMSE Faz     : {best_row['rmse_P']:.6f}")
print(f"  RMSE E-alan  : {best_row['rmse_E']:.6f}")
print("═" * 60)