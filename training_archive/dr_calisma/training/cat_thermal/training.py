#!/usr/bin/env python3
"""
training.py — Cat Thermal Classification (Improved)
================================================================
20 backbones, thermal-only, BCE loss
Sick oversampling (esit dagilim), CutOut aug
Image-based stratified split (70/15/15)
"""

import os
import sys
import time
import json
import gc
import warnings
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.nn.functional as F  # sigmoid icin
from torch.utils.data import Dataset, DataLoader
from torchvision import transforms
from PIL import Image
from sklearn.model_selection import train_test_split
from sklearn.metrics import (accuracy_score, f1_score, roc_auc_score,
    precision_recall_curve, auc, cohen_kappa_score, matthews_corrcoef,
    brier_score_loss, confusion_matrix)
from tabulate import tabulate
import timm

warnings.filterwarnings("ignore")

# ============================================================
# CONFIG
# ============================================================
SEED = 42
DEVICE = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
MODELS_DIR = "/home/user02/dr/models/models_cat_thermal"
RESULTS_CSV = os.path.join(MODELS_DIR, "model_cat_thermal_karsilastirma.csv")
DATA_DIR = "/home/user02/dr/dataset/cat_thermal_224"
IMGSZ = 224
BS = 32
LR = 0.001
EPOCHS = 50
PATIENCE = 15
NUM_WORKERS = 8
THRESHOLD = 0.5

os.makedirs(MODELS_DIR, exist_ok=True)
torch.manual_seed(SEED)
np.random.seed(SEED)
torch.backends.cudnn.deterministic = True

# ============================================================
# 20 Backbones
# ============================================================
BACKBONES = {
    "YOLO26n": {"type": "yolo", "model": "yolo26n-cls"},
    "YOLO26s": {"type": "yolo", "model": "yolo26s-cls"},
    "EfficientViT_B0": {"type": "timm", "model": "efficientvit_b0.r224_in1k"},
    "RepViT_M1": {"type": "timm", "model": "repvit_m1.dist_in1k"},
    "FastViT_T8": {"type": "timm", "model": "fastvit_mci0.apple_mclip"},
    "StarNet_S2": {"type": "timm", "model": "starnet_s2.in1k"},
    "ConvNeXtV2_Atto": {"type": "timm", "model": "convnextv2_atto.fcmae_ft_in1k"},
    "EdgeNeXt_Small": {"type": "timm", "model": "edgenext_small.usi_in1k"},
    "MobileOne_S1": {"type": "timm", "model": "mobileone_s1.apple_in1k"},
    "GhostNetV2": {"type": "timm", "model": "ghostnetv2_100.in1k"},
    "HGNetV2_B0": {"type": "timm", "model": "hgnetv2_b0.ssld_stage2_ft_in1k"},
    # Yeni 4 model
    "MobileViTV2": {"type": "timm", "model": "mobilevitv2_050.cvnets_in1k"},
    "XCiT_Nano": {"type": "timm", "model": "xcit_nano_12_p16_224.fb_in1k"},
    "EfficientFormerV2_S0": {"type": "timm", "model": "efficientformerv2_s0.snap_dist_in1k"},
    "TinyNet_E": {"type": "timm", "model": "tinynet_e.in1k"},
    # Ek 5 lightweight model
    "MobileNetV4_Small": {"type": "timm", "model": "mobilenetv4_conv_small.e2400_r224_in1k"},
    "EfficientNet_Lite0": {"type": "timm", "model": "efficientnet_lite0.ra_in1k"},
    "RegNetY_002": {"type": "timm", "model": "regnety_002.pycls_in1k"},
    "LCNet": {"type": "timm", "model": "lcnet_100.ra2_in1k"},
    "MobileNetV3_Small": {"type": "timm", "model": "mobilenetv3_small_100.lamb_in1k"},
}

CSV_COLS = [
    "Model", "Accuracy", "F1", "AUC_ROC", "AUC_PR",
    "Sensitivity", "Specificity", "PPV", "NPV",
    "Cohen_Kappa", "MCC", "Brier_Score", "Youden_J",
    "Params_M", "Train_Time_s", "Inference_ms", "Epochs_Trained",
]

# ============================================================
# DATA — Thermal only
# ============================================================
print("=" * 70)
print("CAT THERMAL CLASSIFICATION — THERMAL ONLY + BCE")
print(f"Device: {DEVICE} | BS: {BS} | LR: {LR} | Threshold: {THRESHOLD}")
print("=" * 70)


def load_dataset():
    samples = []
    for root, dirs, files in os.walk(DATA_DIR):
        for f in files:
            if not f.lower().endswith(('.jpg', '.jpeg', '.png')):
                continue
            path = os.path.join(root, f)
            parts = root.split("/")
            modality = label = None
            for p in parts:
                if p == "Thermal": modality = "thermal"
                if p == "Digital": modality = "digital"
                if p == "Healthy": label = 0
                if p == "Sick": label = 1
            # THERMAL ONLY
            if modality == "thermal" and label is not None:
                samples.append({"path": path, "label": label})

    df = pd.DataFrame(samples)
    print(f"\nThermal-only: {len(df)} goruntu")
    print(f"  Healthy: {(df['label']==0).sum()} | Sick: {(df['label']==1).sum()}")
    return df


class ThermalDataset(Dataset):
    def __init__(self, df, transform=None):
        self.df = df.reset_index(drop=True)
        self.transform = transform

    def __len__(self):
        return len(self.df)

    def __getitem__(self, idx):
        row = self.df.iloc[idx]
        img = Image.open(row["path"]).convert("RGB")
        label = row["label"]

        if self.transform:
            img = self.transform(img)

        return img, label


# ============================================================
# MODEL — Thermal only, BCE only (no contrastive)
# ============================================================
class ThermalClassifier(nn.Module):
    def __init__(self, backbone_name, backbone_type="timm"):
        super().__init__()

        if backbone_type == "timm":
            self.backbone = timm.create_model(backbone_name, pretrained=True, num_classes=0)
            self.backbone.eval()  # BN eval mode for dummy forward
            with torch.no_grad():
                dummy = torch.randn(2, 3, IMGSZ, IMGSZ)  # batch=2 (BN icin min 2)
                feat_dim = self.backbone(dummy).shape[1]
            self.backbone.train()
        elif backbone_type == "yolo":
            from ultralytics import YOLO
            yolo_model = YOLO(f"{backbone_name}.pt")
            self.backbone = yolo_model.model.model[:10]
            with torch.no_grad():
                dummy = torch.randn(1, 3, IMGSZ, IMGSZ)
                feat = self.backbone(dummy)
                if isinstance(feat, (list, tuple)):
                    feat = feat[-1]
                feat = nn.AdaptiveAvgPool2d(1)(feat)
                feat_dim = feat.view(1, -1).shape[1]
            self._yolo_pool = nn.AdaptiveAvgPool2d(1)

        self.backbone_type = backbone_type
        self.feat_dim = feat_dim

        # Classification head
        self.classifier = nn.Sequential(
            nn.Linear(feat_dim, 256),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(256, 1),
        )

    def extract_features(self, x):
        if self.backbone_type == "yolo":
            feat = self.backbone(x)
            if isinstance(feat, (list, tuple)):
                feat = feat[-1]
            feat = self._yolo_pool(feat)
            return feat.view(feat.size(0), -1)
        else:
            return self.backbone(x)

    def forward(self, x):
        feat = self.extract_features(x)
        logits = self.classifier(feat).squeeze(1)
        return logits


# ============================================================
# METRICS
# ============================================================
def compute_metrics(y_true, y_prob, threshold=THRESHOLD):
    y_pred = (y_prob >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()

    acc = accuracy_score(y_true, y_pred)
    f1 = f1_score(y_true, y_pred)
    try: auc_roc = roc_auc_score(y_true, y_prob)
    except: auc_roc = 0.0
    prec_arr, rec_arr, _ = precision_recall_curve(y_true, y_prob)
    auc_pr = auc(rec_arr, prec_arr)

    sensitivity = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    specificity = tn / (tn + fp) if (tn + fp) > 0 else 0.0
    ppv = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    npv = tn / (tn + fn) if (tn + fn) > 0 else 0.0
    kappa = cohen_kappa_score(y_true, y_pred)
    mcc = matthews_corrcoef(y_true, y_pred)
    brier = brier_score_loss(y_true, y_prob)
    youden = sensitivity + specificity - 1.0

    return {
        "Accuracy": acc, "F1": f1, "AUC_ROC": auc_roc, "AUC_PR": auc_pr,
        "Sensitivity": sensitivity, "Specificity": specificity,
        "PPV": ppv, "NPV": npv,
        "Cohen_Kappa": kappa, "MCC": mcc,
        "Brier_Score": brier, "Youden_J": youden,
    }


# ============================================================
# TRAINING
# ============================================================
def train_model(backbone_name, backbone_cfg, train_df, val_df, test_df):

    # Augmentation — renk dokunmaz, geometric + CutOut
    train_transform = transforms.Compose([
        transforms.RandomHorizontalFlip(),
        transforms.RandomVerticalFlip(),
        transforms.RandomRotation(15),
        transforms.RandomResizedCrop(IMGSZ, scale=(0.85, 1.0)),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        transforms.RandomErasing(p=0.3, scale=(0.05, 0.15)),  # CutOut
    ])
    val_transform = transforms.Compose([
        transforms.Resize((IMGSZ, IMGSZ)),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])

    # Oversampling sick → esit dagilim
    healthy_count = (train_df["label"] == 0).sum()
    sick_count = (train_df["label"] == 1).sum()
    sick_train = train_df[train_df["label"] == 1]

    if sick_count > 0:
        repeat = max(1, int(np.ceil(healthy_count / sick_count)) - 1)
        train_df_bal = pd.concat([train_df] + [sick_train] * repeat, ignore_index=True)
        train_df_bal = train_df_bal.sample(frac=1, random_state=SEED).reset_index(drop=True)
    else:
        train_df_bal = train_df

    print(f"    Oversampling: {len(train_df)} -> {len(train_df_bal)} "
          f"(H:{(train_df_bal['label']==0).sum()} S:{(train_df_bal['label']==1).sum()})")

    train_ds = ThermalDataset(train_df_bal, train_transform)
    val_ds = ThermalDataset(val_df, val_transform)
    test_ds = ThermalDataset(test_df, val_transform)

    train_loader = DataLoader(train_ds, batch_size=BS, shuffle=True,
                              num_workers=NUM_WORKERS, pin_memory=True, drop_last=True)
    val_loader = DataLoader(val_ds, batch_size=BS, shuffle=False,
                            num_workers=NUM_WORKERS, pin_memory=True)
    test_loader = DataLoader(test_ds, batch_size=BS, shuffle=False,
                             num_workers=NUM_WORKERS, pin_memory=True)

    # Model
    pt_path = os.path.join(MODELS_DIR, f"{backbone_name}.pt")
    if os.path.exists(pt_path):
        print(f"  Mevcut model yukleniyor...")
        model = ThermalClassifier(backbone_cfg["model"], backbone_cfg["type"]).to(DEVICE)
        model.load_state_dict(torch.load(pt_path, map_location=DEVICE))
        train_time = 0.0
        epochs_trained = 0
    else:
        model = ThermalClassifier(backbone_cfg["model"], backbone_cfg["type"]).to(DEVICE)

        params_m = sum(p.numel() for p in model.parameters()) / 1e6
        print(f"  Params: {params_m:.1f}M")

        # Freeze: epoch 1-3 tum backbone frozen, epoch 4+ tumu acik
        all_backbone_params = list(model.backbone.parameters())
        for param in all_backbone_params:
            param.requires_grad = False
        print(f"    Freeze: tum backbone frozen (epoch 1-3), epoch 4'te acilacak")

        try:
            model = torch.compile(model)
        except:
            pass

        # Loss + differential LR (backbone 0.1x, head 1x)
        bce_criterion = nn.BCEWithLogitsLoss()
        backbone_params = list(model.backbone.parameters()) if hasattr(model, 'backbone') else []
        head_params = list(model.classifier.parameters()) if hasattr(model, 'classifier') else []
        if backbone_params and head_params:
            optimizer = torch.optim.AdamW([
                {"params": backbone_params, "lr": LR * 0.1},
                {"params": head_params, "lr": LR},
            ], weight_decay=1e-4)
        else:
            optimizer = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=1e-4)
        scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
            optimizer, mode='max', factor=0.5, patience=3, min_lr=1e-6)
        scaler = torch.cuda.amp.GradScaler()

        best_val_f1 = 0.0
        best_state = None
        no_improve = 0
        epochs_trained = 0
        t0 = time.time()

        for epoch in range(1, EPOCHS + 1):
            if epoch == 4:
                for param in all_backbone_params:
                    param.requires_grad = True
                no_improve = 0  # Patience reset — backbone yeni acildi
                print(f"    Backbone FULL unfrozen at epoch {epoch} (patience reset)")

            # Train
            model.train()
            train_loss = 0.0
            for imgs, labels in train_loader:
                imgs = imgs.to(DEVICE, non_blocking=True)
                labels_t = labels.float().to(DEVICE, non_blocking=True)

                optimizer.zero_grad()
                with torch.cuda.amp.autocast():
                    logits = model(imgs)
                    loss = bce_criterion(logits, labels_t)

                scaler.scale(loss).backward()
                scaler.unscale_(optimizer)
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                scaler.step(optimizer)
                scaler.update()
                train_loss += loss.item() * len(imgs)

            train_loss /= len(train_ds)

            # Val — F1 ile best model
            model.eval()
            val_probs = []
            val_labels = []
            with torch.no_grad(), torch.cuda.amp.autocast():
                for imgs, labels in val_loader:
                    imgs = imgs.to(DEVICE, non_blocking=True)
                    logits = model(imgs)
                    probs = torch.sigmoid(logits).cpu().numpy()
                    val_probs.extend(probs)
                    val_labels.extend(labels.numpy())

            val_preds = (np.array(val_probs) >= THRESHOLD).astype(int)
            val_f1 = f1_score(np.array(val_labels), val_preds)
            scheduler.step(val_f1)  # ReduceLROnPlateau

            if epoch % 5 == 0 or epoch == 1 or epoch == 4:
                print(f"    Ep {epoch:3d}/{EPOCHS} | TL: {train_loss:.4f} | Val_F1: {val_f1:.4f}")

            if val_f1 > best_val_f1:
                best_val_f1 = val_f1
                best_state = {k: v.clone() for k, v in model.state_dict().items()}
                no_improve = 0
                epochs_trained = epoch
            else:
                no_improve += 1

            if no_improve >= PATIENCE:
                print(f"    Early stop ep {epoch} (best_f1={best_val_f1:.4f}, ep={epochs_trained})")
                break

        train_time = time.time() - t0

        if best_state:
            model.load_state_dict(best_state)
            torch.save(best_state, pt_path)

    # ---- Evaluate on test ----
    model.eval()
    all_probs = []
    all_labels = []
    t_inf = time.time()
    with torch.no_grad(), torch.cuda.amp.autocast():
        for imgs, labels in test_loader:
            imgs = imgs.to(DEVICE, non_blocking=True)
            logits = model(imgs)
            probs = torch.sigmoid(logits).cpu().numpy()
            all_probs.extend(probs)
            all_labels.extend(labels.numpy())
    inference_time = (time.time() - t_inf) / max(len(all_labels), 1) * 1000

    # Optimal threshold from val set (Youden's J)
    val_probs_final = []
    val_labels_final = []
    with torch.no_grad(), torch.cuda.amp.autocast():
        for imgs, labels in val_loader:
            imgs = imgs.to(DEVICE, non_blocking=True)
            logits = model(imgs)
            probs = torch.sigmoid(logits).cpu().numpy()
            val_probs_final.extend(probs)
            val_labels_final.extend(labels.numpy())
    from sklearn.metrics import roc_curve
    try:
        fpr, tpr, thresholds = roc_curve(np.array(val_labels_final), np.array(val_probs_final))
        optimal_idx = np.argmax(tpr - fpr)
        optimal_threshold = float(thresholds[optimal_idx])
        print(f"    Optimal threshold (Youden): {optimal_threshold:.3f}")
    except:
        optimal_threshold = THRESHOLD

    # Test metrics with both thresholds
    metrics = compute_metrics(np.array(all_labels), np.array(all_probs), threshold=optimal_threshold)
    params_m = sum(p.numel() for p in model.parameters()) / 1e6

    row = {"Model": backbone_name, **metrics,
           "Params_M": round(params_m, 1),
           "Train_Time_s": round(train_time, 1),
           "Inference_ms": round(inference_time, 2),
           "Epochs_Trained": epochs_trained}

    del model
    torch.cuda.empty_cache()
    gc.collect()
    return row


# ============================================================
# MAIN
# ============================================================
df = load_dataset()

# IMAGE-BASED STRATIFIED SPLIT (70/15/15)
# Thermal goruntulerde arka plan/pozisyon her karede farkli
# → kedi kimligi ogrenilemiyor → image-based split uygun

idx_all = np.arange(len(df))
labels_all = df["label"].values

idx_tv, idx_test = train_test_split(idx_all, test_size=0.15, random_state=SEED, stratify=labels_all)
idx_train, idx_val = train_test_split(idx_tv, test_size=0.176, random_state=SEED, stratify=labels_all[idx_tv])

train_df = df.iloc[idx_train].reset_index(drop=True)
val_df = df.iloc[idx_val].reset_index(drop=True)
test_df = df.iloc[idx_test].reset_index(drop=True)

print(f"\n=== IMAGE-BASED STRATIFIED SPLIT ===")
print(f"Train: {len(train_df)} imgs (H:{(train_df['label']==0).sum()} S:{(train_df['label']==1).sum()})")
print(f"Val:   {len(val_df)} imgs (H:{(val_df['label']==0).sum()} S:{(val_df['label']==1).sum()})")
print(f"Test:  {len(test_df)} imgs "
      f"(H:{(test_df['label']==0).sum()} S:{(test_df['label']==1).sum()})")

# ============================================================
# TRAINING LOOP
# ============================================================
results_list = []
print(f"\n{'='*70}\nEGITIM — {len(BACKBONES)} BACKBONE (thermal-only + BCE)\n{'='*70}")

for i, (name, cfg) in enumerate(BACKBONES.items(), 1):
    print(f"\n[{i}/{len(BACKBONES)}] {name} ({cfg['type']}: {cfg['model']})")
    print("-" * 50)
    try:
        row = train_model(name, cfg, train_df, val_df, test_df)
        results_list.append(row)
        print(f"  Acc:{row['Accuracy']:.4f} F1:{row['F1']:.4f} AUC:{row['AUC_ROC']:.4f} "
              f"Sens:{row['Sensitivity']:.4f} Spec:{row['Specificity']:.4f}")

        _new = pd.DataFrame(results_list)
        if os.path.exists(RESULTS_CSV):
            _old = pd.read_csv(RESULTS_CSV)
            _keep = _old[~_old['Model'].isin(_new['Model'].values)]
            _merged = pd.concat([_keep, _new], ignore_index=True)
            _merged.to_csv(RESULTS_CSV, index=False)
        else:
            _new.to_csv(RESULTS_CSV, index=False)
    except Exception as e:
        import traceback
        print(f"  HATA: {str(e)[:200]}")
        traceback.print_exc(limit=3)
        torch.cuda.empty_cache()
        gc.collect()

# ============================================================
# FINAL TABLE
# ============================================================
print(f"\n\n{'='*70}\nSONUC TABLOSU\n{'='*70}")
if os.path.exists(RESULTS_CSV):
    df_res = pd.read_csv(RESULTS_CSV).sort_values("AUC_ROC", ascending=False)
    df_res.to_csv(RESULTS_CSV, index=False)
    td = [[r["Model"], f"{r['Accuracy']:.4f}", f"{r['F1']:.4f}",
           f"{r['AUC_ROC']:.4f}", f"{r['Sensitivity']:.4f}",
           f"{r['Specificity']:.4f}", f"{r['MCC']:.4f}"]
          for _, r in df_res.iterrows()]
    print(tabulate(td, headers=["Model", "Acc", "F1", "AUC", "Sens", "Spec", "MCC"],
                   tablefmt="simple_grid", stralign="right"))
    print(f"\nEN IYI -> {df_res.iloc[0]['Model']} | AUC: {df_res.iloc[0]['AUC_ROC']:.4f}")

config = {
    "approach": "thermal-only + BCE + CutOut + oversampling",
    "split": "image-based stratified (70/15/15)",
    "threshold": THRESHOLD,
    "backbones": list(BACKBONES.keys()),
    "loss": "BCE only",
    "augmentation": "HFlip, VFlip, Rotate15, RandomCrop, CutOut (no color)",
}
with open(os.path.join(MODELS_DIR, "experiment_config.json"), "w") as f:
    json.dump(config, f, indent=2)

print(f"\n{'='*70}\nTAMAMLANDI -> {RESULTS_CSV}\n{'='*70}")
