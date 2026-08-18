#!/usr/bin/env python3
"""
training.py — Cat Sound Classification (Mel Spectrogram + 20 Backbones)
========================================================================
MP3 → Mel Spectrogram (224×224) → 20 pretrained backbones → 10 sinif
Backbones: cat_thermal ile ayni (YOLO26, EfficientViT, MobileNet, etc.)
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
from torch.utils.data import Dataset, DataLoader
from torchvision import transforms
from PIL import Image
from sklearn.model_selection import train_test_split
from sklearn.metrics import (accuracy_score, f1_score, roc_auc_score,
    cohen_kappa_score, matthews_corrcoef, confusion_matrix,
    classification_report, top_k_accuracy_score)
from tabulate import tabulate
import timm
import librosa

warnings.filterwarnings("ignore")

# ============================================================
# CONFIG
# ============================================================
SEED = 42
DEVICE = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
MODELS_DIR = "/home/user02/dr/models/models_cat_sound"
RESULTS_CSV = os.path.join(MODELS_DIR, "model_cat_sound_karsilastirma.csv")
DATA_DIR = "/home/user02/dr/dataset/cat_sound/NAYA_DATA_AUG1X"
MEL_CACHE_DIR = os.path.join(MODELS_DIR, "mel_cache")

IMGSZ = 224         # ImageNet standart
BS = 32             # 224 icin batch arttirildi
LR = 0.001
EPOCHS = 100        # 50 -> 100 (daha uzun egitim)
PATIENCE = 30       # 15 -> 30 (daha sabırli)
NUM_WORKERS = 4

# Mel spectrogram params (optimize edilmis)
SR = 22050          # sample rate
N_MELS = 256        # 128 -> 256 (daha detayli frekans cozunurlugu)
HOP_LENGTH = 256    # 512 -> 256 (daha detayli zaman cozunurlugu)
N_FFT = 2048
DURATION = 5.0      # 5 saniye sabit — kisa sesler pad, uzunlar truncate

CLASSES = sorted(["Angry", "Defence", "Fighting", "Happy", "HuntingMind",
                  "Mating", "MotherCall", "Paining", "Resting", "Warning"])
NUM_CLASSES = len(CLASSES)
CLASS_TO_IDX = {c: i for i, c in enumerate(CLASSES)}

os.makedirs(MODELS_DIR, exist_ok=True)
os.makedirs(MEL_CACHE_DIR, exist_ok=True)
torch.manual_seed(SEED)
np.random.seed(SEED)

# ============================================================
# 20 BACKBONES (cat_thermal ile ayni)
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
    "MobileViTV2": {"type": "timm", "model": "mobilevitv2_050.cvnets_in1k"},
    "XCiT_Nano": {"type": "timm", "model": "xcit_nano_12_p16_224.fb_in1k"},
    "EfficientFormerV2_S0": {"type": "timm", "model": "efficientformerv2_s0.snap_dist_in1k"},
    "TinyNet_E": {"type": "timm", "model": "tinynet_e.in1k"},
    "MobileNetV4_Small": {"type": "timm", "model": "mobilenetv4_conv_small.e2400_r224_in1k"},
    "EfficientNet_Lite0": {"type": "timm", "model": "efficientnet_lite0.ra_in1k"},
    "RegNetY_002": {"type": "timm", "model": "regnety_002.pycls_in1k"},
    "LCNet": {"type": "timm", "model": "lcnet_100.ra2_in1k"},
    "MobileNetV3_Small": {"type": "timm", "model": "mobilenetv3_small_100.lamb_in1k"},
}

CSV_COLS = [
    "Model", "Accuracy", "Top3_Accuracy", "F1_macro", "F1_weighted",
    "AUC_ROC_macro", "Cohen_Kappa", "MCC",
    "Params_M", "Train_Time_s", "Inference_ms", "Epochs_Trained",
]


# ============================================================
# MEL SPECTROGRAM
# ============================================================
def mp3_to_mel_image(mp3_path, cache_dir=None):
    """MP3 → 3-channel mel (mel + delta + delta²) → PIL Image (IMGSZ×IMGSZ).
    Kanal 1: Mel spectrogram (frekans bilgisi)
    Kanal 2: Delta (zamandaki degisim hizi)
    Kanal 3: Delta-delta (degisim ivmesi)
    Full stretch — padding yok.
    """
    # Cache check
    if cache_dir:
        cache_name = os.path.basename(mp3_path).replace(".mp3", ".png")
        cache_path = os.path.join(cache_dir, cache_name)
        if os.path.exists(cache_path):
            return Image.open(cache_path).convert("RGB")

    # Load audio
    y, sr = librosa.load(mp3_path, sr=SR, duration=DURATION, mono=True)

    # Sessiz baslangic/bitis kirp
    y_trimmed, _ = librosa.effects.trim(y, top_db=30)
    if len(y_trimmed) > SR * 0.3:
        y = y_trimmed

    # Mel spectrogram
    mel = librosa.feature.melspectrogram(y=y, sr=sr, n_mels=N_MELS,
                                          n_fft=N_FFT, hop_length=HOP_LENGTH)
    mel_db = librosa.power_to_db(mel, ref=np.max)

    # Delta ve delta-delta (temporal bilgi)
    delta = librosa.feature.delta(mel_db, order=1)
    delta2 = librosa.feature.delta(mel_db, order=2)

    # Normalize her kanal 0-255
    def norm_channel(ch):
        ch_min, ch_max = ch.min(), ch.max()
        if ch_max - ch_min < 1e-8:
            return np.zeros_like(ch, dtype=np.uint8)
        return ((ch - ch_min) / (ch_max - ch_min) * 255).astype(np.uint8)

    ch1 = norm_channel(mel_db)     # R: mel
    ch2 = norm_channel(delta)      # G: delta (degisim hizi)
    ch3 = norm_channel(delta2)     # B: delta-delta (ivme)

    # 3-channel RGB
    mel_rgb = np.stack([ch1, ch2, ch3], axis=2)  # (n_mels, time, 3)

    # Full stretch
    img = Image.fromarray(mel_rgb)
    img = img.resize((IMGSZ, IMGSZ), Image.BILINEAR)

    # Cache
    if cache_dir:
        img.save(cache_path)

    return img


# ============================================================
# DATASET
# ============================================================
print("=" * 70)
print("CAT SOUND CLASSIFICATION — Mel Spectrogram + 20 Backbones")
print(f"Device: {DEVICE} | BS: {BS} | LR: {LR} | Classes: {NUM_CLASSES}")
print("=" * 70)


def load_dataset():
    """Load MP3 files, separate original vs augmented."""
    samples = []
    for cls_name in CLASSES:
        cls_dir = os.path.join(DATA_DIR, cls_name)
        if not os.path.isdir(cls_dir):
            continue
        for f in os.listdir(cls_dir):
            if not f.lower().endswith('.mp3'):
                continue
            path = os.path.join(cls_dir, f)
            is_aug = "aug" in f.lower()
            samples.append({
                "path": path,
                "label": CLASS_TO_IDX[cls_name],
                "class_name": cls_name,
                "is_augmented": is_aug,
                "filename": f,
            })
    return pd.DataFrame(samples)


df = load_dataset()
print(f"\nToplam: {len(df)} dosya ({df['is_augmented'].sum()} augmented)")
print(f"Siniflar:")
for cls in CLASSES:
    n = (df['class_name'] == cls).sum()
    n_orig = ((df['class_name'] == cls) & (~df['is_augmented'])).sum()
    print(f"  {cls:15s}: {n:4d} ({n_orig} orig + {n - n_orig} aug)")

# Split: SADECE original dosyalar uzerinden stratified split
# Augmented dosyalar sadece train'e eklenir
# Base name ile strict split — leakage onleme
df_orig = df[~df['is_augmented']].reset_index(drop=True)
df_aug = df[df['is_augmented']].reset_index(drop=True)

# Her dosyanin base name'ini cikar (aug olsa da olmasa da)
df_orig['base'] = df_orig['filename'].apply(lambda f: os.path.splitext(f)[0])

# UNIQUE base name'ler uzerinden split (ayni base train+val'a dusmesin)
unique_bases = df_orig[['base', 'label']].drop_duplicates(subset='base')
idx_all = np.arange(len(unique_bases))
idx_tv, idx_test = train_test_split(
    idx_all, test_size=0.15, random_state=SEED, stratify=unique_bases['label'].values)
idx_train, idx_val = train_test_split(
    idx_tv, test_size=0.176, random_state=SEED, stratify=unique_bases['label'].values[idx_tv])

train_bases = set(unique_bases.iloc[idx_train]['base'])
val_bases = set(unique_bases.iloc[idx_val]['base'])
test_bases = set(unique_bases.iloc[idx_test]['base'])

# Strict: overlap olmamali
assert len(train_bases & val_bases) == 0, "Train-Val overlap!"
assert len(train_bases & test_bases) == 0, "Train-Test overlap!"

train_df = df_orig[df_orig['base'].isin(train_bases)].reset_index(drop=True)
val_df = df_orig[df_orig['base'].isin(val_bases)].reset_index(drop=True)
test_df = df_orig[df_orig['base'].isin(test_bases)].reset_index(drop=True)

# Augmented dosyalari SADECE train base'lere ekle
aug_for_train = []
for _, row in df_aug.iterrows():
    base = row['filename'].split('_aug')[0]
    if base in train_bases:
        aug_for_train.append(row)

if aug_for_train:
    aug_train_df = pd.DataFrame(aug_for_train)
    train_df = pd.concat([train_df, aug_train_df], ignore_index=True)

print(f"  Leakage check: train∩val={len(train_bases & val_bases)}, train∩test={len(train_bases & test_bases)}")

print(f"\nSplit:")
print(f"  Train: {len(train_df):4d} (incl. {len(aug_for_train)} aug)")
print(f"  Val:   {len(val_df):4d} (original only)")
print(f"  Test:  {len(test_df):4d} (original only)")

# Pre-cache mel spectrograms
# DURATION degistiyse eski cache gecersiz — temizle
_cache_marker = os.path.join(MEL_CACHE_DIR, ".3ch_mel_v2")
if not os.path.exists(_cache_marker):
    import shutil
    if os.path.exists(MEL_CACHE_DIR) and len(os.listdir(MEL_CACHE_DIR)) > 0:
        print(f"\n[Cache] DURATION degisti, eski cache temizleniyor...")
        shutil.rmtree(MEL_CACHE_DIR)
        os.makedirs(MEL_CACHE_DIR, exist_ok=True)
    with open(_cache_marker, 'w') as f:
        f.write(str(DURATION))

print(f"\n[Cache] Mel spectrogram cache olusturuluyor...")
all_paths = set()
for _, row in pd.concat([train_df, val_df, test_df]).iterrows():
    if row['path'] not in all_paths:
        mp3_to_mel_image(row['path'], cache_dir=MEL_CACHE_DIR)
        all_paths.add(row['path'])
    if len(all_paths) % 500 == 0:
        print(f"  {len(all_paths)}/{len(df)}...", flush=True)
print(f"  Cache tamamlandi: {len(os.listdir(MEL_CACHE_DIR))} dosya")


# ============================================================
# AUDIO-LEVEL AUGMENTATION (mel'den ONCE, ses sinyali uzerinde)
# ============================================================
def audio_augment(y, sr):
    """Ses sinyaline fiziksel augmentation uygula."""
    # Pitch shift (±2 semitone)
    if np.random.random() < 0.5:
        n_steps = np.random.uniform(-2, 2)
        y = librosa.effects.pitch_shift(y, sr=sr, n_steps=n_steps)

    # Time stretch (0.85x - 1.15x)
    if np.random.random() < 0.5:
        rate = np.random.uniform(0.85, 1.15)
        y = librosa.effects.time_stretch(y, rate=rate)

    # Gaussian noise
    if np.random.random() < 0.4:
        noise = np.random.randn(len(y)) * 0.005
        y = y + noise

    # Random gain (±6 dB)
    if np.random.random() < 0.4:
        gain_db = np.random.uniform(-6, 6)
        y = y * (10 ** (gain_db / 20))

    return y


# mp3_to_mel_augmented kaldirildi — tek fonksiyon: mp3_to_mel_image


# ============================================================
# SpecAugment (spectrogram uzerinde, audio aug'dan ayri)
# ============================================================
class SpecAugment:
    def __init__(self, freq_mask=30, time_mask=40, n_freq=2, n_time=2):
        self.freq_mask = freq_mask
        self.time_mask = time_mask
        self.n_freq = n_freq
        self.n_time = n_time

    def __call__(self, img):
        arr = np.array(img)
        h, w = arr.shape[:2]
        for _ in range(self.n_freq):
            f = np.random.randint(0, self.freq_mask)
            f0 = np.random.randint(0, max(1, h - f))
            arr[f0:f0+f, :] = 0
        for _ in range(self.n_time):
            t = np.random.randint(0, self.time_mask)
            t0 = np.random.randint(0, max(1, w - t))
            arr[:, t0:t0+t] = 0
        return Image.fromarray(arr)


# ============================================================
# Focal Loss (zor orneklere odaklan)
# ============================================================
class FocalLoss(nn.Module):
    def __init__(self, gamma=2.0, label_smoothing=0.1):
        super().__init__()
        self.gamma = gamma
        self.ce = nn.CrossEntropyLoss(label_smoothing=label_smoothing, reduction='none')

    def forward(self, pred, target):
        ce_loss = self.ce(pred, target)
        pt = torch.exp(-ce_loss)  # p(correct class)
        focal_weight = (1 - pt) ** self.gamma
        return (focal_weight * ce_loss).mean()


# ============================================================
# Dataset
# ============================================================
class SoundDataset(Dataset):
    """Cache'den PNG yukle + spectrogram-level augmentation (hizli)."""
    def __init__(self, df, transform=None, cache_dir=None, mixup_alpha=0.0):
        self.df = df.reset_index(drop=True)
        self.transform = transform
        self.cache_dir = cache_dir
        self.mixup_alpha = mixup_alpha

    def __len__(self):
        return len(self.df)

    def __getitem__(self, idx):
        row = self.df.iloc[idx]
        img = mp3_to_mel_image(row['path'], cache_dir=self.cache_dir)
        label = row['label']

        if self.transform:
            img = self.transform(img)

        # Mixup — label'i da karistir (one-hot soft label)
        if self.mixup_alpha > 0 and np.random.random() < 0.3:
            mix_idx = np.random.randint(len(self.df))
            mix_row = self.df.iloc[mix_idx]
            mix_img = mp3_to_mel_image(mix_row['path'], cache_dir=self.cache_dir)
            if self.transform:
                mix_img = self.transform(mix_img)
            lam = np.random.beta(self.mixup_alpha, self.mixup_alpha)
            img = lam * img + (1 - lam) * mix_img
            # Soft label: lam * one_hot(label) + (1-lam) * one_hot(mix_label)
            soft_label = torch.zeros(NUM_CLASSES)
            soft_label[int(label)] = lam
            soft_label[int(mix_row['label'])] += (1 - lam)
            return img, soft_label

        # Hard label — ayni formatta tensor dondur (collate uyumu)
        hard_label = torch.zeros(NUM_CLASSES)
        hard_label[int(label)] = 1.0
        return img, hard_label


# ============================================================
# Spectrogram-Level Audio Augmentation (hizli, <1ms)
# ============================================================
class SpectrogramAudioAug:
    """Spectrogram uzerinde audio augmentation simulasyonu.
    pitch_shift  → dikey kaydirma (frequency shift)
    time_stretch → yatay resize (tempo degisimi)
    noise        → pixel noise ekleme
    gain         → parlaklik degisimi
    """
    def __call__(self, img):
        arr = np.array(img)  # (H, W, 3)
        h, w = arr.shape[:2]

        # Frequency shift (pitch shift simulasyonu) — dikey kaydir
        if np.random.random() < 0.5:
            shift = np.random.randint(-15, 16)  # ±15 pixel
            if shift > 0:
                arr = np.pad(arr, ((shift,0),(0,0),(0,0)), mode='constant')[:h, :, :]
            elif shift < 0:
                arr = np.pad(arr, ((0,-shift),(0,0),(0,0)), mode='constant')[-shift:h-shift, :, :]

        # Time stretch simulasyonu — yatay resize
        if np.random.random() < 0.5:
            rate = np.random.uniform(0.85, 1.15)
            new_w = int(w * rate)
            stretched = Image.fromarray(arr).resize((new_w, h), Image.BILINEAR)
            stretched = np.array(stretched)
            if new_w > w:
                start = (new_w - w) // 2
                arr = stretched[:, start:start+w, :]
            else:
                pad = w - new_w
                arr = np.pad(stretched, ((0,0),(0,pad),(0,0)), mode='constant')[:, :w, :]

        # Gaussian noise
        if np.random.random() < 0.4:
            noise = np.random.randn(*arr.shape) * 8  # std=8 (0-255 scale)
            arr = np.clip(arr.astype(np.float32) + noise, 0, 255).astype(np.uint8)

        # Random gain (channel-wise)
        if np.random.random() < 0.4:
            gain = np.random.uniform(0.8, 1.2, size=(1, 1, 3))
            arr = np.clip(arr.astype(np.float32) * gain, 0, 255).astype(np.uint8)

        return Image.fromarray(arr)


# Transforms
train_transform = transforms.Compose([
    SpectrogramAudioAug(),                              # pitch/stretch/noise/gain simulasyonu
    SpecAugment(freq_mask=30, time_mask=40, n_freq=2, n_time=2),  # freq/time masking
    transforms.RandomAffine(degrees=0, translate=(0.1, 0.05), scale=(0.9, 1.1)),
    transforms.ToTensor(),
    transforms.RandomErasing(p=0.2, scale=(0.02, 0.15)),
    transforms.Normalize([0.5, 0.5, 0.5], [0.5, 0.5, 0.5]),
])

val_transform = transforms.Compose([
    transforms.ToTensor(),
    transforms.Normalize([0.5, 0.5, 0.5], [0.5, 0.5, 0.5]),
])

train_ds = SoundDataset(train_df, train_transform, MEL_CACHE_DIR, mixup_alpha=0.3)
val_ds = SoundDataset(val_df, val_transform, MEL_CACHE_DIR)
test_ds = SoundDataset(test_df, val_transform, MEL_CACHE_DIR)

train_loader = DataLoader(train_ds, batch_size=BS, shuffle=True, num_workers=NUM_WORKERS, pin_memory=True)
val_loader = DataLoader(val_ds, batch_size=BS, shuffle=False, num_workers=NUM_WORKERS, pin_memory=True)
test_loader = DataLoader(test_ds, batch_size=BS, shuffle=False, num_workers=NUM_WORKERS, pin_memory=True)


# ============================================================
# MODEL
# ============================================================
class SoundClassifier(nn.Module):
    def __init__(self, backbone_name, backbone_type="timm"):
        super().__init__()
        if backbone_type == "timm":
            self.backbone = timm.create_model(backbone_name, pretrained=True, num_classes=0)
            self.backbone.eval()
            with torch.no_grad():
                dummy = torch.randn(1, 3, IMGSZ, IMGSZ)
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
                feat_dim = feat.shape[1]
            self.pool = nn.AdaptiveAvgPool2d(1)
        self.backbone_type = backbone_type
        self.head = nn.Sequential(
            nn.Linear(feat_dim, 256),
            nn.BatchNorm1d(256),
            nn.GELU(),
            nn.Dropout(0.3),
            nn.Linear(256, NUM_CLASSES),
        )

    def forward(self, x):
        if self.backbone_type == "yolo":
            feat = self.backbone(x)
            if isinstance(feat, (list, tuple)):
                feat = feat[-1]
            feat = self.pool(feat).flatten(1)
        else:
            feat = self.backbone(x)
        return self.head(feat)


# ============================================================
# TRAINING
# ============================================================
def compute_metrics(y_true, y_pred, y_prob):
    acc = accuracy_score(y_true, y_pred)
    f1_mac = f1_score(y_true, y_pred, average='macro', zero_division=0)
    f1_wt = f1_score(y_true, y_pred, average='weighted', zero_division=0)
    kappa = cohen_kappa_score(y_true, y_pred)
    mcc = matthews_corrcoef(y_true, y_pred)
    try:
        top3 = top_k_accuracy_score(y_true, y_prob, k=3, labels=list(range(NUM_CLASSES)))
    except:
        top3 = 0.0
    try:
        auc_roc = roc_auc_score(y_true, y_prob, multi_class='ovr', average='macro')
    except:
        auc_roc = 0.0
    return {
        "Accuracy": acc, "Top3_Accuracy": top3,
        "F1_macro": f1_mac, "F1_weighted": f1_wt,
        "AUC_ROC_macro": auc_roc, "Cohen_Kappa": kappa, "MCC": mcc,
    }


# ============================================================
# KNOWLEDGE DISTILLATION — Teacher: BEiT (Microsoft)
# ============================================================
TEACHER_MODEL_NAME = "beit_base_patch16_224.in22k_ft_in22k_in1k"
TEACHER_PT = os.path.join(MODELS_DIR, "teacher_beit.pt")
KD_TEMPERATURE = 4.0    # soft label sicaklik
KD_ALPHA = 0.5          # 0.5 = %50 hard label + %50 teacher soft label

def train_teacher():
    """BEiT teacher model egit (bir kez)."""
    if os.path.exists(TEACHER_PT):
        print(f"\n[Teacher] Mevcut: {TEACHER_PT}")
        teacher = SoundClassifier(TEACHER_MODEL_NAME, "timm").to(DEVICE)
        teacher.load_state_dict(torch.load(TEACHER_PT, map_location=DEVICE))
        teacher.eval()
        return teacher

    print(f"\n{'='*70}")
    print(f"[Teacher] BEiT egitiliyor — simple but effective")
    print(f"{'='*70}")

    teacher = SoundClassifier(TEACHER_MODEL_NAME, "timm").to(DEVICE)
    params_m = sum(p.numel() for p in teacher.parameters()) / 1e6
    print(f"  Teacher params: {params_m:.1f}M")

    TEACHER_EPOCHS = 100
    TEACHER_PATIENCE = 30

    # Basit ama etkili: freeze 5 epoch, sonra full unfreeze
    # Backbone dusuk LR, head yuksek LR
    all_bb = list(teacher.backbone.parameters())
    for p in all_bb:
        p.requires_grad = False

    opt = torch.optim.AdamW([
        {"params": all_bb, "lr": 1e-4},                    # backbone: dusuk ama sifir degil
        {"params": list(teacher.head.parameters()), "lr": 1e-3},  # head: yuksek
    ], weight_decay=1e-4)

    crit = nn.CrossEntropyLoss(label_smoothing=0.1)
    scaler_t = torch.cuda.amp.GradScaler()
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=TEACHER_EPOCHS, eta_min=1e-6)

    best_acc, best_state = 0.0, None
    no_imp = 0

    for ep in range(1, TEACHER_EPOCHS + 1):
        # Epoch 6'da backbone unfreeze
        if ep == 6:
            for p in all_bb:
                p.requires_grad = True
            print(f"    [Epoch {ep}] Backbone unfrozen")

        teacher.train()
        epoch_loss = 0
        for xb, yb in train_loader:
            xb, yb = xb.to(DEVICE), yb.to(DEVICE)
            yb_hard = yb.argmax(dim=1) if yb.dim() == 2 else yb
            opt.zero_grad()
            with torch.cuda.amp.autocast():
                loss = crit(teacher(xb), yb_hard)
            scaler_t.scale(loss).backward()
            scaler_t.unscale_(opt)
            torch.nn.utils.clip_grad_norm_(teacher.parameters(), max_norm=1.0)
            scaler_t.step(opt)
            scaler_t.update()
            epoch_loss += loss.item() * len(xb)
        epoch_loss /= len(train_ds)

        teacher.eval()
        correct, total = 0, 0
        with torch.no_grad():
            for xb, yb in val_loader:
                xb, yb = xb.to(DEVICE), yb.to(DEVICE)
                yb_hard = yb.argmax(dim=1) if yb.dim() == 2 else yb
                pred = teacher(xb).argmax(1)
                correct += (pred == yb_hard).sum().item()
                total += len(yb_hard)
        acc = correct / total
        sched.step()

        if ep % 5 == 0 or ep == 1:
            print(f"    Teacher Ep {ep:3d}/{TEACHER_EPOCHS} | Loss: {epoch_loss:.4f} | VAcc: {acc:.4f}")

        if acc > best_acc:
            best_acc = acc
            best_state = {k: v.clone() for k, v in teacher.state_dict().items()}
            no_imp = 0
        else:
            no_imp += 1

        if no_imp >= TEACHER_PATIENCE:
            print(f"    Teacher early stop ep {ep}, best acc={best_acc:.4f}")
            break

    if best_state:
        teacher.load_state_dict(best_state)
        torch.save(best_state, TEACHER_PT)
    teacher.eval()
    print(f"  Teacher best acc: {best_acc:.4f}")
    return teacher


# Train teacher ONCE
teacher_model = train_teacher()

# Teacher'i test set'te evaluate edip CSV'ye yaz
print(f"\n[Teacher] Test set evaluate...")
teacher_model.eval()
_t_preds, _t_probs, _t_true = [], [], []
_t_inf = time.time()
with torch.no_grad(), torch.cuda.amp.autocast():
    for xb, yb in test_loader:
        xb, yb = xb.to(DEVICE), yb.to(DEVICE)
        yb_hard = yb.argmax(dim=1) if yb.dim() == 2 else yb
        out = teacher_model(xb)
        probs = torch.softmax(out, dim=1).cpu().numpy()
        _t_probs.append(probs)
        _t_preds.extend(probs.argmax(axis=1))
        _t_true.extend(yb_hard.cpu().numpy())
_t_inf_ms = (time.time() - _t_inf) / len(test_ds) * 1000
_t_probs = np.vstack(_t_probs)
_t_metrics = compute_metrics(_t_true, _t_preds, _t_probs)
_t_params = sum(p.numel() for p in teacher_model.parameters()) / 1e6
_t_metrics["Params_M"] = round(_t_params, 1)
_t_metrics["Train_Time_s"] = 0.0
_t_metrics["Inference_ms"] = round(_t_inf_ms, 2)
_t_metrics["Epochs_Trained"] = 0
_t_metrics["Model"] = "Teacher_BEiT"
print(f"  Teacher test Acc: {_t_metrics['Accuracy']:.4f} | F1: {_t_metrics['F1_macro']:.4f}")

# Teacher sonucunu CSV'ye kaydet
_t_df = pd.DataFrame([_t_metrics])
if os.path.exists(RESULTS_CSV):
    _old = pd.read_csv(RESULTS_CSV)
    _keep = _old[_old['Model'] != 'Teacher_BEiT']
    pd.concat([_keep, _t_df], ignore_index=True).to_csv(RESULTS_CSV, index=False)
else:
    _t_df.to_csv(RESULTS_CSV, index=False)


def kd_loss(student_logits, teacher_logits, hard_labels, T=KD_TEMPERATURE, alpha=KD_ALPHA):
    """Knowledge Distillation loss: hard label + soft teacher."""
    # Hard label loss (focal)
    hard_loss = FocalLoss(gamma=2.0, label_smoothing=0.1)(student_logits, hard_labels)
    # Soft label loss (KL divergence with temperature)
    soft_student = nn.functional.log_softmax(student_logits / T, dim=1)
    soft_teacher = nn.functional.softmax(teacher_logits / T, dim=1)
    kl_loss = nn.functional.kl_div(soft_student, soft_teacher, reduction='batchmean') * (T * T)
    return alpha * hard_loss + (1 - alpha) * kl_loss


def train_model(backbone_name, backbone_cfg):
    pt_path = os.path.join(MODELS_DIR, f"{backbone_name}.pt")

    # Skip if exists
    if os.path.exists(pt_path):
        print(f"  Mevcut: {pt_path}, evaluate...")
        model = SoundClassifier(backbone_cfg["model"], backbone_cfg["type"]).to(DEVICE)
        model.load_state_dict(torch.load(pt_path, map_location=DEVICE))
        model.eval()
        train_time = 0.0
        epochs_trained = 0
    else:
        model = SoundClassifier(backbone_cfg["model"], backbone_cfg["type"]).to(DEVICE)
        params_m = sum(p.numel() for p in model.parameters()) / 1e6
        print(f"  Params: {params_m:.1f}M (+ KD from BEiT teacher)")

        # Freeze backbone (epoch 1-3)
        all_backbone_params = list(model.backbone.parameters())
        for param in all_backbone_params:
            param.requires_grad = False

        # Differential LR
        backbone_params = list(model.backbone.parameters())
        head_params = list(model.head.parameters())
        optimizer = torch.optim.AdamW([
            {"params": backbone_params, "lr": LR * 0.1},
            {"params": head_params, "lr": LR},
        ], weight_decay=1e-4)

        scaler = torch.cuda.amp.GradScaler()
        scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=EPOCHS, eta_min=1e-6)

        best_val_acc = 0.0
        best_state = None
        no_improve = 0
        epochs_trained = 0

        t0 = time.time()
        for epoch in range(1, EPOCHS + 1):
            if epoch == 4:
                for param in all_backbone_params:
                    param.requires_grad = True
                no_improve = 0

            # Train with KD
            model.train()
            train_loss = 0
            for xb, yb in train_loader:
                xb, yb = xb.to(DEVICE), yb.to(DEVICE)
                # Mixup soft label: yb tensor ise (soft), int ise (hard)
                if yb.dim() == 2:
                    # Soft label (mixup) — hard_labels = argmax
                    hard_labels = yb.argmax(dim=1)
                else:
                    hard_labels = yb
                optimizer.zero_grad()
                with torch.cuda.amp.autocast():
                    student_out = model(xb)
                    with torch.no_grad():
                        teacher_out = teacher_model(xb)
                    loss = kd_loss(student_out, teacher_out, hard_labels)
                scaler.scale(loss).backward()
                scaler.step(optimizer)
                scaler.update()
                train_loss += loss.item() * len(xb)
            train_loss /= len(train_ds)

            # Val
            model.eval()
            val_loss = 0
            val_preds, val_probs, val_true = [], [], []
            with torch.no_grad(), torch.cuda.amp.autocast():
                for xb, yb in val_loader:
                    xb, yb = xb.to(DEVICE), yb.to(DEVICE)
                    yb_hard = yb.argmax(dim=1) if yb.dim() == 2 else yb
                    out = model(xb)
                    val_loss += nn.functional.cross_entropy(out, yb_hard).item() * len(xb)
                    probs = torch.softmax(out, dim=1).cpu().numpy()
                    val_probs.append(probs)
                    val_preds.extend(probs.argmax(axis=1))
                    val_true.extend(yb_hard.cpu().numpy())
            val_loss /= len(val_ds)
            val_acc = accuracy_score(val_true, val_preds)

            if epoch % 5 == 0 or epoch == 1:
                print(f"    Ep {epoch:3d}/{EPOCHS} | TL: {train_loss:.4f} | VL: {val_loss:.4f} | VAcc: {val_acc:.4f}")

            if val_acc > best_val_acc:
                best_val_acc = val_acc
                best_state = {k: v.clone() for k, v in model.state_dict().items()}
                no_improve = 0
                epochs_trained = epoch
            else:
                no_improve += 1

            # Cosine LR step
            scheduler.step()

            if no_improve >= PATIENCE:
                print(f"    Early stop at epoch {epoch} (best={epochs_trained})")
                break

        train_time = time.time() - t0

        if best_state:
            model.load_state_dict(best_state)
            torch.save(best_state, pt_path)

    # Evaluate on test
    model.eval()
    test_preds, test_probs, test_true = [], [], []
    t_inf = time.time()
    with torch.no_grad(), torch.cuda.amp.autocast():
        for xb, yb in test_loader:
            xb, yb = xb.to(DEVICE), yb.to(DEVICE)
            yb_hard = yb.argmax(dim=1) if yb.dim() == 2 else yb
            out = model(xb)
            probs = torch.softmax(out, dim=1).cpu().numpy()
            test_probs.append(probs)
            test_preds.extend(probs.argmax(axis=1))
            test_true.extend(yb_hard.cpu().numpy())
    inf_time = (time.time() - t_inf) / len(test_ds) * 1000  # ms per sample
    test_probs = np.vstack(test_probs)

    metrics = compute_metrics(test_true, test_preds, test_probs)
    params_m = sum(p.numel() for p in model.parameters()) / 1e6

    metrics["Params_M"] = round(params_m, 1)
    metrics["Train_Time_s"] = round(train_time, 1)
    metrics["Inference_ms"] = round(inf_time, 2)
    metrics["Epochs_Trained"] = epochs_trained
    metrics["Model"] = backbone_name

    del model
    torch.cuda.empty_cache()
    gc.collect()

    return metrics


# ============================================================
# MAIN LOOP
# ============================================================
results = []

print(f"\n{'='*70}")
print(f"EGITIM BASLIYOR — {len(BACKBONES)} backbone")
print(f"{'='*70}")

for i, (name, cfg) in enumerate(BACKBONES.items(), 1):
    print(f"\n[{i}/{len(BACKBONES)}] {name}")
    print(f"  Type: {cfg['type']} | Model: {cfg['model']}")

    try:
        m = train_model(name, cfg)
        results.append(m)
        print(f"  Acc: {m['Accuracy']:.4f} | F1: {m['F1_macro']:.4f} | "
              f"Top3: {m['Top3_Accuracy']:.4f} | {m['Inference_ms']:.1f}ms")

        # Incremental CSV save (merge)
        new_df = pd.DataFrame(results)
        if os.path.exists(RESULTS_CSV):
            old_df = pd.read_csv(RESULTS_CSV)
            keep = old_df[~old_df['Model'].isin(new_df['Model'].values)]
            merged = pd.concat([keep, new_df], ignore_index=True)
            merged.to_csv(RESULTS_CSV, index=False)
        else:
            new_df.to_csv(RESULTS_CSV, index=False)

    except Exception as e:
        import traceback
        print(f"  HATA: {str(e)[:200]}")
        traceback.print_exc(limit=2)


# ============================================================
# FINAL TABLE
# ============================================================
print(f"\n\n{'='*70}")
print("SONUC TABLOSU")
print(f"{'='*70}")

df_res = pd.DataFrame(results)
if os.path.exists(RESULTS_CSV):
    old = pd.read_csv(RESULTS_CSV)
    keep = old[~old['Model'].isin(df_res['Model'].values)]
    df_res = pd.concat([keep, df_res], ignore_index=True)

df_res = df_res.sort_values("Accuracy", ascending=False).reset_index(drop=True)
df_res.to_csv(RESULTS_CSV, index=False)

for _, r in df_res.head(20).iterrows():
    print(f"  {r['Model']:25s} Acc={r['Accuracy']:.4f} F1={r['F1_macro']:.4f} "
          f"Top3={r['Top3_Accuracy']:.4f} {r['Inference_ms']:.1f}ms")

best = df_res.iloc[0]
print(f"\nEN IYI: {best['Model']} — Acc={best['Accuracy']:.4f}")

# Config
config = {
    "task": "audio_classification",
    "dataset": DATA_DIR,
    "classes": CLASSES,
    "n_classes": NUM_CLASSES,
    "mel_params": {"sr": SR, "n_mels": N_MELS, "n_fft": N_FFT,
                   "hop_length": HOP_LENGTH, "duration": DURATION},
    "imgsz": IMGSZ,
    "backbones": list(BACKBONES.keys()),
}
with open(os.path.join(MODELS_DIR, "experiment_config.json"), "w") as f:
    json.dump(config, f, indent=2)

print(f"\n{'='*70}")
print(f"TAMAMLANDI -> {RESULTS_CSV}")
print(f"{'='*70}")
