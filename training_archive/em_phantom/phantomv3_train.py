# -*- coding: utf-8 -*-
"""
Created on Mon Apr 20 10:12:38 2026

@author: merta
"""

# -*- coding: utf-8 -*-
"""
EĞİTİM — PHANTOM v3 (İyileştirilmiş)
══════════════════════════════════════════════════════════════════════════════
v2 → v3 DEĞİŞİKLİKLER:
  [KRİTİK] 1. Sin/Cos artık StandardScaler dışında — kısıt korunuyor
  [KRİTİK] 2. Model forward'da Phase Normalization — sin²+cos²=1 garanti
  [KRİTİK] 3. Differential E Loss eklendi — E_cancer − E_healthy farkı
               doğrudan öğretiliyor (terapötik pencere bilgisi)
  [KRİTİK] 4. phase_cons loss kaldırıldı — mimari zaten garantiliyor
  [İYİ]    5. LAMBDA_PHASE 0.3→2.5  (RMSE_P=0.121 → hedef <0.05)
  [İYİ]    6. LAMBDA_E 0.5→0.10     (E zaten mükemmel, gereksiz baskı kaldırıldı)
  [İYİ]    7. EPOCHS 600→2000, PATIENCE 80→200 (597/600'de best — hala öğreniyordu!)
  [İYİ]    8. HIDDEN 512→768, N_BLOCKS 8→10, DROPOUT 0.30→0.20
  [İYİ]    9. CosineAnnealingWarmRestarts scheduler
  [İYİ]   10. Early stopping: val_loss → R² bazlı
  [İYİ]   11. Head katmanları derinleştirildi (128→256) + LayerNorm
  [İYİ]   12. Ayrı scaler dosyaları (D: scaler_D, E: scaler_E, X: scaler_X)
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

print("🧠 PHANTOM EĞİTİM v3 — FiLM ResNet Multi-Head [İYİLEŞTİRİLMİŞ]\n")

# ══════════════════════════════════════════════════════════════════════════════
# HİPERPARAMETRELER
# ══════════════════════════════════════════════════════════════════════════════
EPOCHS        = 2000    # v2: 600  → 2000 (597/600'de best, hala öğreniyordu)
BATCH_SIZE    = 512
LR            = 3e-4
PATIENCE      = 200     # v2: 80   → 200
WARMUP_EPOCHS = 50      # v2: 30   → 50
HIDDEN        = 768     # v2: 512  → 768
N_BLOCKS      = 10      # v2: 8    → 10
DROPOUT       = 0.20    # v2: 0.30 → 0.20
NUM_CLASSES   = 2       # 0=sağlıklı (ebos), 1=kanserli (edolu)

# [İYİ FİX] Lambda dengeleri yeniden ayarlandı
LAMBDA_PHASE     = 2.5   # v2: 0.3  → 2.5  (RMSE_P en büyük hata)
LAMBDA_E         = 0.10  # v2: 0.5  → 0.10 (E zaten çok iyi, gereksiz ağırlık azaltıldı)
LAMBDA_E_DIFF    = 0.50  # YENİ: E_cancer − E_healthy farkı (terapötik pencere)
LAMBDA_DUTY_REG  = 0.001
LAMBDA_DUTY_CLIP = 0.01
# LAMBDA_PHASE_CONS kaldırıldı — mimari garantiliyor

# Organ ağırlıkları: kanserli doku daha kritik
ORGAN_LOSS_W = {0: 1.0, 1: 2.0}  # v2: {0:1.0, 1:1.5} → kanser daha önemli

# ══════════════════════════════════════════════════════════════════════════════
# DOSYA YOLLARI
# ══════════════════════════════════════════════════════════════════════════════
BASE_DIR        = os.path.dirname(os.path.abspath(__file__))
DATA_PATH       = os.path.join(BASE_DIR, "training_data_phantom_v7.csv")
MODEL_PTH_PATH  = os.path.join(BASE_DIR, "best_phantom_model_v3.pth")
MODEL_ONNX_PATH = os.path.join(BASE_DIR, "PhantomNet_v3.onnx")
SCALER_X_PATH   = os.path.join(BASE_DIR, "scaler_X_phantom_v3.pkl")
SCALER_D_PATH   = os.path.join(BASE_DIR, "scaler_D_phantom_v3.pkl")
SCALER_E_PATH   = os.path.join(BASE_DIR, "scaler_E_phantom_v3.pkl")
HISTORY_PATH    = os.path.join(BASE_DIR, "training_history_phantom_v3.csv")

# ══════════════════════════════════════════════════════════════════════════════
# VERİ HAZIRLIĞI
# ══════════════════════════════════════════════════════════════════════════════
df = pd.read_csv(DATA_PATH)
print(f"📊 Veri seti   : {len(df):,} satır  |  Organ dağılımı:")
print(df['organ_id'].value_counts().to_string())
print()

X_coords = df[['x', 'y', 'z']].values.astype(np.float32)
X_organs = df['organ_id'].values.astype(np.float32).reshape(-1, 1)

extra_feats = []
for col in ['achieved_B', 'duty_sum']:
    if col in df.columns:
        extra_feats.append(df[col].values.reshape(-1, 1))
        print(f"  ✅ Ek feature: {col}")

D_data     = df[[f'D{i}' for i in range(1, 8)]].values.astype(np.float32)
P_data_rad = np.radians(df[[f'P{i}' for i in range(1, 8)]].values)
sinP_data  = np.sin(P_data_rad).astype(np.float32)   # zaten [-1, 1]
cosP_data  = np.cos(P_data_rad).astype(np.float32)   # zaten [-1, 1]
E_data     = df[['result_E_healthy', 'result_E_cancer']].values.astype(np.float32)

# ── [KRİTİK FİX] Ayrı Ölçekleme Stratejisi ────────────────────────────────
# v2 SORUNU: StandardScaler tüm 23 çıktıya uygulanıyordu.
#   Sin/cos değerleri zaten [-1,1] ve sin²+cos²=1'i sağlıyor.
#   StandardScaler bu değerleri bozuyor → scaled alanda kısıt geçersiz.
# v3 ÇÖZÜM:
#   D (7 sütun) → StandardScaler
#   sinP (7) + cosP (7) → ÖLÇEKLEME YOK (geometrik kısıt korunuyor)
#   E_healthy + E_cancer (2) → StandardScaler

scaler_D = StandardScaler()
scaler_E = StandardScaler()
D_sc     = scaler_D.fit_transform(D_data)   # (N, 7)
E_sc     = scaler_E.fit_transform(E_data)   # (N, 2)

# Eğitim dizisi: [D_sc | sinP | cosP | E_sc]
y_sc   = np.hstack([D_sc, sinP_data, cosP_data, E_sc]).astype(np.float32)
# Orijinal (metrik hesaplama için): [D | sinP | cosP | E]
y_orig = np.hstack([D_data, sinP_data, cosP_data, E_data]).astype(np.float32)

joblib.dump(scaler_D, SCALER_D_PATH)
joblib.dump(scaler_E, SCALER_E_PATH)

# ── Koordinat ölçekleme ────────────────────────────────────────────────────
scaler_X    = StandardScaler()
X_coords_sc = scaler_X.fit_transform(X_coords)
joblib.dump(scaler_X, SCALER_X_PATH)

if extra_feats:
    extra        = np.hstack(extra_feats).astype(np.float32)
    scaler_extra = StandardScaler()
    extra_sc     = scaler_extra.fit_transform(extra)
    X_sc         = np.hstack([X_coords_sc, X_organs, extra_sc])
    INPUT_DIM    = 3 + 1 + extra.shape[1]
    joblib.dump(scaler_extra, os.path.join(BASE_DIR, "scaler_extra_phantom_v3.pkl"))
else:
    X_sc      = np.hstack([X_coords_sc, X_organs])
    INPUT_DIM = 4

print(f"\n  Input dim  : {INPUT_DIM}  |  Output dim : {y_sc.shape[1]}")
print(f"  Scalerlar kaydedildi (D ve E ayrı, sin/cos ölçeklenmedi).\n")

# ── Train / Val Bölme ─────────────────────────────────────────────────────────
(X_tr, X_val, y_tr, y_val, y_tr_orig, y_val_orig,
 org_tr, org_val) = train_test_split(
    X_sc.astype(np.float32), y_sc.astype(np.float32),
    y_orig.astype(np.float32), X_organs,
    test_size=0.15, random_state=42,
    stratify=X_organs.astype(int)
)
print(f"  Eğitim: {len(X_tr):,}  |  Doğrulama: {len(X_val):,}\n")


# ══════════════════════════════════════════════════════════════════════════════
# DATASET
# ══════════════════════════════════════════════════════════════════════════════
class PhantomDataset(Dataset):
    def __init__(self, X, y, y_orig, orgs, augment=False):
        self.X      = torch.tensor(X,      dtype=torch.float32)
        self.y      = torch.tensor(y,      dtype=torch.float32)
        self.y_orig = torch.tensor(y_orig, dtype=torch.float32)
        self.orgs   = torch.tensor(orgs,   dtype=torch.long).squeeze()
        self.augment = augment

    def __len__(self): return len(self.X)

    def __getitem__(self, idx):
        x, y, yo = self.X[idx].clone(), self.y[idx], self.y_orig[idx]
        if self.augment and torch.rand(1).item() < 0.4:
            x[:3] += torch.randn(3) * 0.015
        return x, y, yo, self.orgs[idx]


train_ds = PhantomDataset(X_tr, y_tr, y_tr_orig, org_tr, augment=True)
val_ds   = PhantomDataset(X_val, y_val, y_val_orig, org_val, augment=False)

class_counts   = np.bincount(org_tr.astype(int).flatten(), minlength=NUM_CLASSES)
sample_weights = (1.0 / (class_counts + 1e-5))[org_tr.astype(int).flatten()]
sampler        = WeightedRandomSampler(sample_weights, len(sample_weights), replacement=True)

def collate_fn(batch):
    Xs, ys, yos, orgs = zip(*batch)
    return (torch.stack(Xs), torch.stack(ys),
            torch.stack(yos), torch.stack(orgs))

train_loader = DataLoader(train_ds, batch_size=BATCH_SIZE, sampler=sampler,
                          num_workers=0, pin_memory=True, collate_fn=collate_fn)
val_loader   = DataLoader(val_ds,   batch_size=BATCH_SIZE, shuffle=False,
                          num_workers=0, pin_memory=True, collate_fn=collate_fn)


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
    def __init__(self, hidden: int, num_classes: int, dropout: float = 0.20):
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


def make_head(hidden_in: int, hidden_mid: int, out: int,
              dropout: float = 0.10) -> nn.Sequential:
    """[İYİ FİX] Daha derin head — LayerNorm + Dropout eklendi."""
    return nn.Sequential(
        nn.Linear(hidden_in, hidden_mid),
        nn.LayerNorm(hidden_mid),
        nn.Mish(),
        nn.Dropout(dropout),
        nn.Linear(hidden_mid, hidden_mid // 2),
        nn.Mish(),
        nn.Linear(hidden_mid // 2, out)
    )


class PhantomNet(nn.Module):
    """
    Girdi : [x, y, z, organ_id, (achieved_B, duty_sum)]  → (B, INPUT_DIM)
    Çıktı : [D1..7_sc, sinP1..7, cosP1..7, E_h_sc, E_c_sc] → (B, 23)

    [KRİTİK FİX] Phase Normalization:
      sinP/cosP çıktıları unit vektöre normalize ediliyor → sin²+cos²=1 garanti.
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

        # [İYİ FİX] Daha derin head katmanları (64/128 → 256)
        self.head_D    = make_head(hidden, 256, 7)
        self.head_sinP = make_head(hidden, 256, 7)
        self.head_cosP = make_head(hidden, 256, 7)

        # E_healthy ve E_cancer için ayrı head — terapötik pencereyi öğrenmesi için
        # Paylaşılan gövde → ayrı dallar
        self.head_E_shared = nn.Sequential(
            nn.Linear(hidden, 128),
            nn.LayerNorm(128),
            nn.Mish()
        )
        self.head_E_healthy = nn.Linear(128, 1)
        self.head_E_cancer  = nn.Linear(128, 1)

    def forward(self, x):
        coords = x[:, :3]
        org_id = x[:, 3].long()
        extra  = x[:, 4:] if self.input_dim > 4 else None

        h = self.coord_proj(coords)
        if extra is not None and self.extra_proj is not None:
            h = h + self.extra_proj(extra)

        for blk in self.blocks:
            h = blk(h, org_id)

        # [KRİTİK FİX] Phase Normalization
        sinP_raw   = self.head_sinP(h)
        cosP_raw   = self.head_cosP(h)
        phase_norm = torch.sqrt(sinP_raw ** 2 + cosP_raw ** 2 + 1e-8)
        sinP = sinP_raw / phase_norm
        cosP = cosP_raw / phase_norm

        # Paylaşılan E gövdesinden ayrı tahminler
        e_feat    = self.head_E_shared(h)
        e_healthy = self.head_E_healthy(e_feat)
        e_cancer  = self.head_E_cancer(e_feat)

        return torch.cat([
            self.head_D(h),   # 7: D1..7  (scaled)
            sinP,             # 7: sinP   (normalized, unscaled)
            cosP,             # 7: cosP   (normalized, unscaled)
            e_healthy,        # 1: E_h    (scaled)
            e_cancer          # 1: E_c    (scaled)
        ], dim=1)             # toplam: 23


# ══════════════════════════════════════════════════════════════════════════════
# OPTİMİZATÖR & KAYIP
# ══════════════════════════════════════════════════════════════════════════════
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
model  = PhantomNet(input_dim=INPUT_DIM).to(device)

total_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
print(f"📦 Model parametresi : {total_params:,}")
print(f"⚡ Cihaz             : {device}\n")

optimizer = optim.AdamW(model.parameters(), lr=LR, weight_decay=3e-4)

# [İYİ FİX] CosineAnnealingWarmRestarts — LambdaLR yerine
# T_0=150: ilk restart, T_mult=2: periyot giderek uzuyor
scheduler = optim.lr_scheduler.CosineAnnealingWarmRestarts(
    optimizer, T_0=150, T_mult=2, eta_min=1e-6
)

organ_w = torch.tensor(
    [ORGAN_LOSS_W[i] for i in range(NUM_CLASSES)],
    device=device, dtype=torch.float32
)


def custom_loss(pred: torch.Tensor, true: torch.Tensor,
                org_ids: torch.Tensor) -> torch.Tensor:
    """
    [KRİTİK DEĞİŞİKLİKLER]:
    1. phase_cons kaldırıldı — mimari garantiliyor
    2. LAMBDA_PHASE artırıldı (0.3→2.5) — RMSE_P ana sorundu
    3. LAMBDA_E azaltıldı (0.5→0.10) — E zaten mükemmeldi
    4. Differential E Loss eklendi — E_cancer − E_healthy farkını öğretir.
       Klinik açıdan: kanserli dokuda enerji sağlıklı dokudan yüksek olmalı.
       Modelin bu farkı doğru tahmin etmesi terapötik etkinlik için kritik.
    """
    w = organ_w[org_ids].unsqueeze(1)

    loss_D   = (F.mse_loss(pred[:, 0:7],   true[:, 0:7],   reduction='none') * w).mean()
    loss_sin = (F.mse_loss(pred[:, 7:14],  true[:, 7:14],  reduction='none') * w).mean()
    loss_cos = (F.mse_loss(pred[:, 14:21], true[:, 14:21], reduction='none') * w).mean()

    loss_E_h = (F.huber_loss(pred[:, 21:22], true[:, 21:22], delta=1.0, reduction='none') * w).mean()
    loss_E_c = (F.huber_loss(pred[:, 22:23], true[:, 22:23], delta=1.0, reduction='none') * w).mean()
    loss_E   = loss_E_h + loss_E_c

    # [YENİ] Differential E Loss — terapötik pencere (E_c − E_h) farkını öğret
    # Not: bu hesaplama scaled alanda yapılıyor
    diff_pred = pred[:, 22:23] - pred[:, 21:22]   # E_cancer_sc - E_healthy_sc
    diff_true = true[:, 22:23] - true[:, 21:22]
    loss_E_diff = (F.mse_loss(diff_pred, diff_true, reduction='none') * w).mean()

    duty_reg  = pred[:, 0:7].mean()
    duty_clip = F.relu(pred[:, 0:7] - 3.0).mean()

    return (loss_D
            + LAMBDA_PHASE * (loss_sin + loss_cos)   # 0.3→2.5
            + LAMBDA_E     * loss_E                   # 0.5→0.10
            + LAMBDA_E_DIFF * loss_E_diff             # YENİ: 0.50
            + LAMBDA_DUTY_REG  * duty_reg
            + LAMBDA_DUTY_CLIP * duty_clip)


# ══════════════════════════════════════════════════════════════════════════════
# YARDIMCI FONKSİYONLAR
# ══════════════════════════════════════════════════════════════════════════════
def inv_transform(arr: np.ndarray) -> np.ndarray:
    """Ayrı scaler stratejisine göre orijinal birimlere çevirir."""
    D_orig  = scaler_D.inverse_transform(arr[:, 0:7])
    sinP    = arr[:, 7:14]    # ölçeklenmedi
    cosP    = arr[:, 14:21]   # ölçeklenmedi
    E_orig  = scaler_E.inverse_transform(arr[:, 21:23])
    return np.hstack([D_orig, sinP, cosP, E_orig])


# ══════════════════════════════════════════════════════════════════════════════
# EĞİTİM DÖNGÜSÜ
# ══════════════════════════════════════════════════════════════════════════════
best_r2      = -float('inf')   # [İYİ FİX] R² maksimize (val_loss yerine)
patience_ctr = 0
history      = []

print(f"{'Ep':>5} | {'TrLoss':>8} | {'ValLoss':>8} | {'R²':>7} | "
      f"{'RMSE_D':>8} | {'RMSE_P':>8} | {'RMSE_Eh':>8} | {'RMSE_Ec':>8} | "
      f"{'E_diff_err':>10} | {'LR':>9}")
print("─" * 125)

for epoch in range(EPOCHS):
    # ── Eğitim ────────────────────────────────────────────────────────────────
    model.train()
    tr_loss = 0.0
    for Xb, yb, _yob, ob in train_loader:
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
    preds_list, trues_orig_list, orgs_list = [], [], []
    with torch.no_grad():
        for Xb, yb, yob, ob in val_loader:
            Xb, yb, ob = Xb.to(device), yb.to(device), ob.to(device)
            p = model(Xb)
            val_loss += custom_loss(p, yb, ob).item()
            preds_list.append(p.cpu().numpy())
            trues_orig_list.append(yob.numpy())
            orgs_list.append(ob.cpu().numpy())

    tr_loss  /= len(train_loader)
    val_loss /= len(val_loader)

    p_sc   = np.vstack(preds_list)
    t_orig = np.vstack(trues_orig_list)
    o_all  = np.concatenate(orgs_list).flatten()

    p_orig = inv_transform(p_sc)

    r2      = r2_score(t_orig, p_orig)
    mse     = mean_squared_error(t_orig, p_orig)
    mae     = mean_absolute_error(t_orig, p_orig)
    rmse_D  = np.sqrt(mean_squared_error(t_orig[:, 0:7],   p_orig[:, 0:7]))
    rmse_P  = np.sqrt(mean_squared_error(t_orig[:, 7:21],  p_orig[:, 7:21]))
    rmse_Eh = np.sqrt(mean_squared_error(t_orig[:, 21:22], p_orig[:, 21:22]))
    rmse_Ec = np.sqrt(mean_squared_error(t_orig[:, 22:23], p_orig[:, 22:23]))

    # Terapötik pencere hatası (E_c − E_h farkının tahmini ne kadar iyi?)
    diff_true_real = t_orig[:, 22:23] - t_orig[:, 21:22]
    diff_pred_real = p_orig[:, 22:23] - p_orig[:, 21:22]
    e_diff_rmse    = np.sqrt(mean_squared_error(diff_true_real, diff_pred_real))

    lr_now = optimizer.param_groups[0]['lr']

    print(f"{epoch:5d} | {tr_loss:8.4f} | {val_loss:8.4f} | {r2:7.4f} | "
          f"{rmse_D:8.6f} | {rmse_P:8.4f} | {rmse_Eh:8.4f} | {rmse_Ec:8.4f} | "
          f"{e_diff_rmse:10.6f} | {lr_now:9.2e}")

    # Per-class R²
    r2_healthy = r2_score(t_orig[o_all == 0], p_orig[o_all == 0]) if (o_all == 0).sum() >= 10 else float('nan')
    r2_cancer  = r2_score(t_orig[o_all == 1], p_orig[o_all == 1]) if (o_all == 1).sum() >= 10 else float('nan')

    history.append({
        "epoch": epoch, "tr_loss": tr_loss, "val_loss": val_loss,
        "r2": r2, "mse": mse, "mae": mae,
        "rmse_D": rmse_D, "rmse_P": rmse_P,
        "rmse_E_healthy": rmse_Eh, "rmse_E_cancer": rmse_Ec,
        "e_diff_rmse": e_diff_rmse,
        "r2_healthy": r2_healthy, "r2_cancer": r2_cancer,
        "lr": lr_now
    })

    # [İYİ FİX] Early stopping: R² maksimize ediliyor
    if r2 > best_r2:
        best_r2      = r2
        patience_ctr = 0
        torch.save(model.state_dict(), MODEL_PTH_PATH)
    else:
        patience_ctr += 1
        if patience_ctr >= PATIENCE:
            print(f"\n🛑 Early stopping @ Ep {epoch}  (best R²: {best_r2:.6f})")
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

# ── Sınıf bazlı R² (en iyi epoch) ────────────────────────────────────────────
print("\n📊 Sınıf bazlı Val R² (en iyi epoch):")
model.eval()
all_p, all_t, all_o = [], [], []
with torch.no_grad():
    for Xb, yb, yob, ob in val_loader:
        Xb = Xb.to(device)
        all_p.append(model(Xb).cpu().numpy())
        all_t.append(yob.numpy())
        all_o.append(ob.numpy())

p_orig_f = inv_transform(np.vstack(all_p))
t_orig_f = np.vstack(all_t)
o_all    = np.concatenate(all_o).flatten()

labels = {0: 'sağlıklı (ebos)', 1: 'kanserli (edolu)'}
for cls_id in range(NUM_CLASSES):
    mask = o_all == cls_id
    if mask.sum() < 10:
        continue
    r2_c = r2_score(t_orig_f[mask], p_orig_f[mask])
    print(f"  Sınıf {cls_id} ({labels[cls_id]:>16s}): R² = {r2_c:.4f}  (n={mask.sum():,})")

# Terapötik pencere analizi
diff_true_f = t_orig_f[:, 22:23] - t_orig_f[:, 21:22]
diff_pred_f = p_orig_f[:, 22:23] - p_orig_f[:, 21:22]
diff_r2     = r2_score(diff_true_f, diff_pred_f)
diff_rmse   = np.sqrt(mean_squared_error(diff_true_f, diff_pred_f))
print(f"\n  Terapötik pencere (E_cancer − E_healthy):")
print(f"    R²   = {diff_r2:.4f}")
print(f"    RMSE = {diff_rmse:.6f}")

# ── Final özet ────────────────────────────────────────────────────────────────
best_row = max(history, key=lambda r: r['r2'])
print("\n" + "═" * 60)
print("✅ EN İYİ MODEL (Val seti, gerçek birim):")
print("═" * 60)
print(f"  Epoch             : {int(best_row['epoch'])}")
print(f"  R²                : {best_row['r2']:.6f}")
print(f"  MSE               : {best_row['mse']:.8f}")
print(f"  RMSE (genel)      : {best_row['rmse']:.6f}" if 'rmse' in best_row else "")
print(f"  MAE  (genel)      : {best_row['mae']:.6f}")
print(f"  RMSE Duty         : {best_row['rmse_D']:.6f}")
print(f"  RMSE Faz          : {best_row['rmse_P']:.6f}")
print(f"  RMSE E_Healthy    : {best_row['rmse_E_healthy']:.6f}")
print(f"  RMSE E_Cancer     : {best_row['rmse_E_cancer']:.6f}")
print(f"  RMSE E_diff (ther): {best_row['e_diff_rmse']:.6f}")
print(f"  R² (sağlıklı)     : {best_row['r2_healthy']:.4f}")
print(f"  R² (kanserli)     : {best_row['r2_cancer']:.4f}")
print("═" * 60)
print(f"\n  GUI bağlantısı için : {MODEL_ONNX_PATH}")
print(f"\n  ⚠️  INFERENCE NOT: v3'te scaler değişti!")
print(f"    X      : scaler_X_phantom_v3.pkl")
print(f"    D çık. : scaler_D_phantom_v3.pkl  (cols 0-6)")
print(f"    E çık. : scaler_E_phantom_v3.pkl  (cols 21-22)")
print(f"    sinP/cosP (cols 7-20): ölçeksiz, doğrudan kullan")