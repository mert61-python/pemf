# -*- coding: utf-8 -*-
"""
VERİ ÜRETİCİ — KEDİ v5 (Profesyonel)
══════════════════════════════════════════════════════════════════════════════
Amaç     : Kedi fantomu içindeki 7 organ bölgesi için 1 mT manyetik alan
           kısıtı altında E-alanı maksimize eden eğitim verisi üretmek.
           P1 = 0 (referans faz, sabitlendi)

organ_id : 0=kutu_butun  1=mide  2=bobrek  3=karaciger
           4=mesane      5=pankreas        6=bagirsak

Çıktı    : training_data_kedi_v5.csv
Sütunlar : x, y, z, D1-D7, P1-P7, achieved_B, result_E, duty_sum, organ_id

Düzeltmeler (v4→v5):
  - Organ aday sayıları / max örnek sayıları denge hataları giderildi
    (mesane: 120k aday → 15k, max_sample tutarlı hale getirildi)
  - Uzamsal stratifikasyon eklendi (MiniBatchKMeans)
  - İstatistik özeti per-organ eklendi
  - Kod yapısı sadeleştirildi
══════════════════════════════════════════════════════════════════════════════
"""

import os
import numpy as np
import pandas as pd
import torch
from scipy.spatial import cKDTree
from sklearn.cluster import MiniBatchKMeans
from tqdm import tqdm

print("🚀 VERİ ÜRETİCİ KEDİ v5 — Max E-Alan & Faz Optimizasyonu\n")

# ══════════════════════════════════════════════════════════════════════════════
# DOSYA YOLLARI
# ══════════════════════════════════════════════════════════════════════════════
EXPORT_PATH   = r"C:\Users\merta\.conda\envs\gui\gui\ealanai\CST_Export_e_field"
B_MATRIX_PATH = r"C:\Users\merta\.conda\envs\gui\gui\ealanai\manyetik_matris.npz"

BASE_DIR       = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE    = os.path.join(BASE_DIR, "training_data_kedi_v5.csv")
MAX_B_LUT_PATH = os.path.join(BASE_DIR, "max_b_lut_kedi_v5.npy")

print(f"📂 CST Yolu    : {EXPORT_PATH}")
print(f"🧲 B-Matris   : {B_MATRIX_PATH}")
print(f"💾 Çıktı      : {OUTPUT_FILE}\n")

# ══════════════════════════════════════════════════════════════════════════════
# HİPERPARAMETRELER
# ══════════════════════════════════════════════════════════════════════════════
TARGET_B   = 0.001
B_TOL      = 0.10    # ±%10
D_MAX      = 0.50
D_MIN      = 0.01
BATCH_SIZE = 256
N_COILS    = 7
N_CLUSTERS = 200     # Uzamsal stratifikasyon küme sayısı

ORGAN_NAMES = {
    0: 'kutu_butun', 1: 'mide',      2: 'bobrek',
    3: 'karaciger',  4: 'mesane',    5: 'pankreas',  6: 'bagirsak'
}

# N_CANDIDATES : Her organ için rastgele arama iterasyonu
# N_SAMPLES    : Uzamsal stratifikasyon ile seçilecek voksel sayısı
# Kural: N_SAMPLES <= N_CANDIDATES (tutarsızlık düzeltildi)
ORGAN_CONFIG = {
    #  organ_id : (N_CANDIDATES, N_SAMPLES)
    0: (15_000,  15_000),   # kutu_butun  — genel referans
    1: (20_000,  15_000),   # mide
    2: (25_000,  20_000),   # bobrek      — klinik öneme sahip
    3: (20_000,  15_000),   # karaciger
    4: (15_000,  10_000),   # mesane      — küçük organ (120k→15k DÜZELTİLDİ)
    5: (20_000,  15_000),   # pankreas
    6: (20_000,  15_000),   # bagirsak
}

# ══════════════════════════════════════════════════════════════════════════════
# YARDIMCI FONKSİYONLAR
# ══════════════════════════════════════════════════════════════════════════════
def read_efield_file(path: str) -> pd.DataFrame:
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        lines = f.readlines()
    skip = next(
        (i for i, line in enumerate(lines)
         if len(line.strip().split()) >= 9
         and line.strip().split()[0].replace('.', '', 1).replace('-', '', 1).isdigit()),
        0
    )
    return pd.read_csv(
        path, sep=r'\s+', skiprows=skip, engine='python', on_bad_lines='skip',
        names=['x', 'y', 'z', 'ExRe', 'ExIm', 'EyRe', 'EyIm', 'EzRe', 'EzIm']
    )


def find_cst_file(bobin_no: int, efield_type: str):
    p = os.path.join(EXPORT_PATH, f"bobin{bobin_no}_{efield_type}.txt")
    return p if os.path.exists(p) else None


def spatial_stratified_sample(coords: np.ndarray, n_samples: int,
                               n_clusters: int = N_CLUSTERS) -> np.ndarray:
    """Koordinat uzayında dengeli örnekleme (kümelere göre)."""
    nc      = min(n_clusters, len(coords), n_samples)
    km      = MiniBatchKMeans(n_clusters=nc, random_state=42,
                              batch_size=4096, n_init=3)
    labels  = km.fit_predict(coords)
    per_c   = max(1, n_samples // nc)
    indices = []
    for c in range(nc):
        mask = np.where(labels == c)[0]
        if len(mask) == 0:
            continue
        indices.extend(
            np.random.choice(mask, min(per_c, len(mask)), replace=False).tolist()
        )
    indices = np.array(indices)
    if len(indices) < n_samples:
        extra   = np.random.choice(len(coords), n_samples - len(indices), replace=False)
        indices = np.concatenate([indices, extra])
    return indices[:n_samples]


def get_organ_masks(coords: np.ndarray) -> dict[int, np.ndarray]:
    """
    Kedi fantomu için anatomik organ bölge maskeleri.
    Koordinatlar normalize edilmiş (merkez & yarıçap) eşiklerle karşılaştırılır.
    """
    cx, cy, cz = coords[:, 0], coords[:, 1], coords[:, 2]
    mx  = (cx.max() + cx.min()) / 2
    my  = (cy.max() + cy.min()) / 2
    mz  = (cz.max() + cz.min()) / 2
    xr  = (cx.max() - cx.min()) / 2
    yr  = (cy.max() - cy.min()) / 2
    zr  = (cz.max() - cz.min()) / 2

    # Normalize mesafe yardımcısı
    def nd(axis, center, radius, tol):
        return np.abs(axis - center) < radius * tol

    return {
        0: np.ones(len(coords), dtype=bool),                              # kutu_butun
        1: nd(cx, mx, xr, 0.50) & nd(cy, my, yr, 0.55)                   # mide
           & (cz > mz - zr * 0.30) & (cz < mz + zr * 0.70),
        2: nd(cx, mx, xr, 0.65) & nd(cy, my, yr, 0.40)                   # bobrek
           & nd(cz, mz, zr, 0.45),
        3: nd(cx, mx, xr, 0.70) & nd(cy, my, yr, 0.65)                   # karaciger
           & nd(cz, mz, zr, 0.60),
        4: nd(cx, mx, xr, 0.30)                                           # mesane
           & (cy > my - yr * 0.20) & (cy < my + yr * 0.80)
           & (cz > mz - zr * 0.55) & (cz < mz + zr * 0.15),
        5: nd(cx, mx, xr, 0.45) & nd(cy, my, yr, 0.70)                   # pankreas
           & nd(cz, mz, zr, 0.70),
        6: nd(cx, mx, xr, 0.60) & nd(cy, my, yr, 0.70)                   # bagirsak
           & nd(cz, mz, zr, 0.80),
    }

# ══════════════════════════════════════════════════════════════════════════════
# B-ALANI YÜKLEME
# ══════════════════════════════════════════════════════════════════════════════
print("📡 B-matris yükleniyor...")
b_data   = np.load(B_MATRIX_PATH)
b_coords = b_data['coords']
B_tensor = np.transpose(
    np.max(np.linalg.norm(b_data['B_matrix'], axis=-1), axis=1), (1, 0)
)
b_tree = cKDTree(b_coords)
print(f"   B vokseli : {len(b_coords):,}\n")

# ══════════════════════════════════════════════════════════════════════════════
# CST E-ALANI YÜKLEME
# ══════════════════════════════════════════════════════════════════════════════
chosen_etype = next(
    (et for et in ['ekutu', 'edolu', 'ebos'] if find_cst_file(1, et)),
    None
)
if not chosen_etype:
    raise FileNotFoundError(
        f"'{EXPORT_PATH}' içinde bobin1_ekutu/edolu/ebos bulunamadı!"
    )
print(f"📡 CST E-alan tipi : {chosen_etype}")

df_base    = read_efield_file(find_cst_file(1, chosen_etype))
cst_coords = df_base[['x', 'y', 'z']].values
cst_tree   = cKDTree(cst_coords)
n_pts      = len(cst_coords)
print(f"   CST nokta sayısı : {n_pts:,}\n")

E_cst = np.zeros((N_COILS, n_pts, 3), dtype=np.complex64)
for i in range(1, N_COILS + 1):
    p = find_cst_file(i, chosen_etype)
    if p is None:
        print(f"   ⚠️  bobin{i}_{chosen_etype}.txt bulunamadı, sıfır kullanılıyor.")
        continue
    df_e  = read_efield_file(p)
    vals  = np.stack([
        df_e['ExRe'] + 1j * df_e['ExIm'],
        df_e['EyRe'] + 1j * df_e['EyIm'],
        df_e['EzRe'] + 1j * df_e['EzIm']
    ], axis=-1).astype(np.complex64)
    _, idx = cst_tree.query(df_e[['x', 'y', 'z']].values)
    valid  = idx < n_pts
    E_cst[i - 1, idx[valid]] = vals[valid]
    print(f"   ✅ bobin{i}_{chosen_etype} yüklendi.")

# ══════════════════════════════════════════════════════════════════════════════
# GPU'YA TRANSFER — B koordinatlarına göre E-alan eşleştirme
# ══════════════════════════════════════════════════════════════════════════════
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
print(f"\n⚡ Hesaplama cihazı : {device}")

B_tensor_gpu = torch.tensor(B_tensor, dtype=torch.float32, device=device)

_, b_to_cst = cst_tree.query(b_coords)
valid_b     = b_to_cst < n_pts

# (N_b, 3, N_coils)
E_tensor_cpu          = np.zeros((len(b_coords), 3, N_COILS), dtype=np.complex64)
E_tensor_cpu[valid_b] = np.transpose(E_cst[:, b_to_cst[valid_b], :], (1, 2, 0))

# Organ maskelerini B koordinatlarında hesapla
organ_masks = get_organ_masks(b_coords)

# ══════════════════════════════════════════════════════════════════════════════
# ANA DÖNGÜ — Her organ için E-alan optimizasyonu
# ══════════════════════════════════════════════════════════════════════════════
B_lo     = TARGET_B * (1 - B_TOL)
B_hi     = TARGET_B * (1 + B_TOL)
all_rows = []
lut_rows = []   # max_achB lookup table (GUI'de B ulaşılabilirlik kontrolü için)

np.random.seed(42)

for oid in range(N_COILS):   # organ 0-6
    mask = organ_masks[oid]
    if mask.sum() == 0:
        print(f"\n⚠️  Organ {oid} ({ORGAN_NAMES[oid]}): hiç voksel yok, atlanıyor.")
        continue

    n_cand, n_samp = ORGAN_CONFIG[oid]
    n_batches      = max(1, n_cand // BATCH_SIZE)

    # Organ voksellerini al
    organ_b_idx = np.where(mask)[0]
    print(f"\n{'='*65}")
    print(f"  Organ {oid}: {ORGAN_NAMES[oid]}")
    print(f"  Toplam voksel : {len(organ_b_idx):,}  "
          f"→ Stratified sample : {n_samp:,}  "
          f"→ Batch: {n_batches:,}")
    print(f"{'='*65}")

    # Uzamsal stratifikasyon
    local_idx    = spatial_stratified_sample(b_coords[organ_b_idx], n_samp)
    sel_idx      = organ_b_idx[local_idx]   # B koordinat uzayındaki global indeks
    n_vox        = len(sel_idx)
    sel_idx_gpu  = torch.tensor(sel_idx, dtype=torch.long, device=device)

    E_org = torch.tensor(E_tensor_cpu[sel_idx], dtype=torch.complex64, device=device)
    B_org = B_tensor_gpu[sel_idx_gpu]

    # En iyi değerleri izle
    topk_E    = torch.full((n_vox,), -float('inf'), device=device)
    topk_D    = torch.zeros((n_vox, N_COILS), dtype=torch.float32, device=device)
    topk_P    = torch.zeros((n_vox, N_COILS), dtype=torch.float32, device=device)
    topk_achB = torch.zeros(n_vox, dtype=torch.float32, device=device)
    max_achB  = torch.zeros(n_vox, dtype=torch.float32, device=device)

    for _ in tqdm(range(n_batches), desc=f"  🔍 Organ {oid} Arama"):
        D_rand       = torch.rand((BATCH_SIZE, N_COILS), device=device) * (D_MAX - D_MIN) + D_MIN
        P_rand       = torch.rand((BATCH_SIZE, N_COILS), device=device) * 360.0
        P_rand[:, 0] = 0.0   # P1 = 0 sabiti

        phasors  = D_rand * torch.exp(1j * torch.deg2rad(P_rand))
        E_tot    = torch.einsum('bc,nvc->bnv', phasors, E_org)   # (BATCH, N_vox, 3)
        E_mag    = torch.linalg.norm(E_tot, dim=2)               # (BATCH, N_vox)
        ach_B    = torch.einsum('bc,nc->bn', D_rand, B_org)      # (BATCH, N_vox)

        # Maksimum ulaşılabilir B'yi takip et (LUT için)
        max_achB = torch.maximum(max_achB, ach_B.max(dim=0)[0])

        in_band    = (ach_B >= B_lo) & (ach_B <= B_hi)
        E_masked   = torch.where(in_band, E_mag, torch.tensor(-float('inf'), device=device))
        best_b_idx = E_masked.argmax(dim=0)
        best_E_val = E_masked[best_b_idx, torch.arange(n_vox)]

        improve = best_E_val > topk_E
        imp_vox = torch.where(improve)[0]

        if len(imp_vox) > 0:
            imp_batch          = best_b_idx[imp_vox]
            topk_E[imp_vox]    = best_E_val[imp_vox]
            topk_D[imp_vox]    = D_rand[imp_batch]
            topk_P[imp_vox]    = P_rand[imp_batch]
            topk_achB[imp_vox] = ach_B[imp_batch, imp_vox]

    # CPU'ya al
    sel_idx_cpu   = sel_idx
    topk_D_np     = topk_D.cpu().numpy()
    topk_P_np     = topk_P.cpu().numpy()
    topk_achB_np  = topk_achB.cpu().numpy()
    topk_E_np     = topk_E.cpu().numpy()
    max_achB_np   = max_achB.cpu().numpy()
    valid_mask    = np.isfinite(topk_E_np)

    print(f"  Geçerli voksel : {valid_mask.sum():,} / {n_vox:,} "
          f"({100 * valid_mask.mean():.1f}%)")

    for k in range(n_vox):
        cx, cy, cz = b_coords[sel_idx_cpu[k]]
        lut_rows.append([cx, cy, cz, float(max_achB_np[k])])

        if not valid_mask[k]:
            continue

        all_rows.append(np.concatenate([
            [cx, cy, cz],
            topk_D_np[k],
            topk_P_np[k],
            [topk_achB_np[k],
             topk_E_np[k],
             topk_D_np[k].sum(),   # duty_sum
             float(oid)]
        ]))

# ══════════════════════════════════════════════════════════════════════════════
# SONUÇLARI KAYDET
# ══════════════════════════════════════════════════════════════════════════════
cols = (
    ['x', 'y', 'z']
    + [f'D{i}' for i in range(1, 8)]
    + [f'P{i}' for i in range(1, 8)]
    + ['achieved_B', 'result_E', 'duty_sum', 'organ_id']
)
df_out = pd.DataFrame(all_rows, columns=cols)
df_out.to_csv(OUTPUT_FILE, index=False)

np.save(MAX_B_LUT_PATH, np.array(lut_rows, dtype=np.float32))

# ── İstatistik özeti ──────────────────────────────────────────────────────────
print(f"\n✅ Kedi eğitim verisi kaydedildi: {OUTPUT_FILE}")
print(f"   Toplam satır : {len(df_out):,}")
print(f"\n{'─'*65}")
print(f"  {'Organ':<6} {'İsim':<14} {'Satır':>7}  "
      f"{'E_ort':>8}  {'E_max':>8}  {'achB_ort':>9}  {'duty_ort':>9}")
print(f"{'─'*65}")
for oid in sorted(df_out['organ_id'].unique()):
    sub = df_out[df_out['organ_id'] == oid]
    print(f"  {int(oid):<6} {ORGAN_NAMES.get(int(oid), '?'):<14} {len(sub):>7,}  "
          f"{sub['result_E'].mean():>8.2f}  "
          f"{sub['result_E'].max():>8.2f}  "
          f"{sub['achieved_B'].mean():>9.5f}  "
          f"{sub['duty_sum'].mean():>9.4f}")
print(f"{'─'*65}")
print(f"\n🗺️  Max-B LUT kaydedildi: {MAX_B_LUT_PATH}")