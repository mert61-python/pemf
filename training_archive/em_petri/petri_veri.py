# -*- coding: utf-8 -*-
"""
VERİ ÜRETİCİ — PETRİ KABI v5 (Profesyonel)
══════════════════════════════════════════════════════════════════════════════
Amaç     : 7 bobinin D (duty) ve P (faz) değerlerini optimize ederek
           1 mT manyetik alan kısıtı altında kanserli dokuda E-alanı
           maksimize eden eğitim verisi üretmek.
           P1 = 0 (referans faz, sabitlendi)

Çıktı    : training_data_petri_v5.csv
Sütunlar : x, y, z, D1-D7, P1-P7, achieved_B,
           result_E_healthy, result_E_cancer, duty_sum, organ_id

Düzeltmeler (v4→v5):
  - duty_sum = 0.0 hardcode hatası düzeltildi
  - Çıktı istatistikleri eklendi
  - Geçersiz satır filtreleme güçlendirildi
  - Kod yapısı sadeleştirildi
══════════════════════════════════════════════════════════════════════════════
"""

import os
import numpy as np
import pandas as pd
import torch
from scipy.spatial import cKDTree
from tqdm import tqdm

print("🚀 VERİ ÜRETİCİ PETRİ v5 — Kanserli/Sağlıklı Çift Doku Optimizasyonu\n")

# ══════════════════════════════════════════════════════════════════════════════
# DOSYA YOLLARI
# ══════════════════════════════════════════════════════════════════════════════
EXPORT_PATH   = r"C:\Users\merta\.conda\envs\gui\gui\ealanai\petri\CST_Export"
B_MATRIX_PATH = r"C:\Users\merta\.conda\envs\gui\gui\ealanai\manyetik_matris.npz"

BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE  = os.path.join(BASE_DIR, "training_data_petri_v5.csv")

print(f"📂 CST Yolu    : {EXPORT_PATH}")
print(f"🧲 B-Matris   : {B_MATRIX_PATH}")
print(f"💾 Çıktı      : {OUTPUT_FILE}\n")

# ══════════════════════════════════════════════════════════════════════════════
# HİPERPARAMETRELER
# ══════════════════════════════════════════════════════════════════════════════
TARGET_B   = 0.001   # 1 mT hedef manyetik alan
B_TOL      = 0.10    # ±%10 tolerans
D_MAX      = 0.50    # Maksimum duty cycle
D_MIN      = 0.01    # Minimum duty cycle
BATCH_SIZE = 256     # Her iterasyondaki rastgele aday sayısı
N_SEARCH   = 200_000 # Toplam arama iterasyonu (artırıldı: 150k→200k)
N_COILS    = 7

# ══════════════════════════════════════════════════════════════════════════════
# YARDIMCI FONKSİYON — CST E-Alan Dosyası Okuma
# ══════════════════════════════════════════════════════════════════════════════
def read_efield_file(path: str) -> pd.DataFrame:
    """CST Studio Suite E-alan txt dosyasını okur, başlık satırlarını atlar."""
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        lines = f.readlines()

    # İlk sayısal satırı bul (başlık satırlarını atla)
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

# ══════════════════════════════════════════════════════════════════════════════
# B-ALANI YÜKLEME
# ══════════════════════════════════════════════════════════════════════════════
print("📡 B-matris yükleniyor...")
b_data   = np.load(B_MATRIX_PATH)
b_coords = b_data['coords']                                             # (N_b, 3)
B_tensor = np.transpose(
    np.max(np.linalg.norm(b_data['B_matrix'], axis=-1), axis=1), (1, 0)
)                                                                       # (N_b, N_coils)
b_tree   = cKDTree(b_coords)
print(f"   B vokseli : {len(b_coords):,}\n")

# ══════════════════════════════════════════════════════════════════════════════
# CST E-ALANI YÜKLEME (Dolu=Kanserli / Boş=Sağlıklı)
# ══════════════════════════════════════════════════════════════════════════════
p_base = os.path.join(EXPORT_PATH, "bobin1_edolu.txt")
if not os.path.exists(p_base):
    raise FileNotFoundError(
        f"Temel dosya bulunamadı: {p_base}\n"
        f"'{EXPORT_PATH}' klasöründe bobin1_edolu.txt bekleniyor."
    )

print("📡 CST E-alan dosyaları yükleniyor...")
df_base    = read_efield_file(p_base)
cst_coords = df_base[['x', 'y', 'z']].values
cst_tree   = cKDTree(cst_coords)
n_pts      = len(cst_coords)
print(f"   CST nokta sayısı : {n_pts:,}")

E_ebos_mat  = np.zeros((N_COILS, n_pts, 3), dtype=np.complex64)   # Sağlıklı doku
E_edolu_mat = np.zeros((N_COILS, n_pts, 3), dtype=np.complex64)   # Kanserli doku

for i in range(1, N_COILS + 1):
    for suffix, mat in [('ebos', E_ebos_mat), ('edolu', E_edolu_mat)]:
        p = os.path.join(EXPORT_PATH, f"bobin{i}_{suffix}.txt")
        if not os.path.exists(p):
            print(f"   ⚠️  Bulunamadı (atlanıyor): bobin{i}_{suffix}.txt")
            continue
        df_e  = read_efield_file(p)
        vals  = np.stack([
            df_e['ExRe'] + 1j * df_e['ExIm'],
            df_e['EyRe'] + 1j * df_e['EyIm'],
            df_e['EzRe'] + 1j * df_e['EzIm']
        ], axis=-1).astype(np.complex64)
        _, idx  = cst_tree.query(df_e[['x', 'y', 'z']].values)
        valid   = idx < n_pts
        mat[i - 1, idx[valid]] = vals[valid]
    print(f"   ✅ Bobin {i} yüklendi.")

# ══════════════════════════════════════════════════════════════════════════════
# GPU'YA TRANSFER — B koordinatlarına göre E-alan eşleştirme
# ══════════════════════════════════════════════════════════════════════════════
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
print(f"\n⚡ Hesaplama cihazı : {device}")

_, b_to_cst = cst_tree.query(b_coords)
valid_b     = b_to_cst < n_pts

# E-alan tensörleri: (N_b, 3, N_coils)
E_ebos_cpu  = np.zeros((len(b_coords), 3, N_COILS), dtype=np.complex64)
E_edolu_cpu = np.zeros((len(b_coords), 3, N_COILS), dtype=np.complex64)
E_ebos_cpu[valid_b]  = np.transpose(E_ebos_mat[:, b_to_cst[valid_b], :],  (1, 2, 0))
E_edolu_cpu[valid_b] = np.transpose(E_edolu_mat[:, b_to_cst[valid_b], :], (1, 2, 0))

B_gpu       = torch.tensor(B_tensor,    dtype=torch.float32,  device=device)
E_ebos_gpu  = torch.tensor(E_ebos_cpu,  dtype=torch.complex64, device=device)
E_edolu_gpu = torch.tensor(E_edolu_cpu, dtype=torch.complex64, device=device)

n_vox    = len(b_coords)
n_batch  = N_SEARCH // BATCH_SIZE
B_lo     = TARGET_B * (1 - B_TOL)
B_hi     = TARGET_B * (1 + B_TOL)

print(f"   B bant : [{B_lo:.5f}, {B_hi:.5f}] T")
print(f"   Voksel : {n_vox:,}  |  Batch : {n_batch:,}  |  Toplam aday : {N_SEARCH:,}\n")

# ══════════════════════════════════════════════════════════════════════════════
# OPTİMİZASYON — Kanserli dokuda E-alanı maksimize et
# ══════════════════════════════════════════════════════════════════════════════
# Her voksel için en iyi (D, P) konfigürasyonunu tut
topk_E_cancer  = torch.full((n_vox,), -float('inf'), device=device)
topk_E_healthy = torch.zeros(n_vox,  dtype=torch.float32, device=device)
topk_D         = torch.zeros((n_vox, N_COILS), dtype=torch.float32, device=device)
topk_P         = torch.zeros((n_vox, N_COILS), dtype=torch.float32, device=device)
topk_achB      = torch.zeros(n_vox,  dtype=torch.float32, device=device)

for _ in tqdm(range(n_batch), desc="🔍 Petri Arama (Max E_cancer @ 1mT)"):
    # Rastgele aday konfigürasyonlar
    D_rand       = torch.rand((BATCH_SIZE, N_COILS), device=device) * (D_MAX - D_MIN) + D_MIN
    P_rand       = torch.rand((BATCH_SIZE, N_COILS), device=device) * 360.0
    P_rand[:, 0] = 0.0   # P1 = 0 (referans faz sabiti)

    phasors = D_rand * torch.exp(1j * torch.deg2rad(P_rand))   # (BATCH, N_COILS)

    # Kanserli doku E-alanı
    E_tot_c  = torch.einsum('bc,nvc->bnv', phasors, E_edolu_gpu)   # (BATCH, N_vox, 3)
    E_mag_c  = torch.linalg.norm(E_tot_c, dim=2)                   # (BATCH, N_vox)

    # Manyetik alan kontrolü
    ach_B    = torch.einsum('bc,nc->bn', D_rand, B_gpu)            # (BATCH, N_vox)
    in_band  = (ach_B >= B_lo) & (ach_B <= B_hi)

    # Bant dışındakileri elendir
    E_masked    = torch.where(in_band, E_mag_c, torch.tensor(-float('inf'), device=device))
    best_b_idx  = E_masked.argmax(dim=0)                           # (N_vox,)
    best_E_val  = E_masked[best_b_idx, torch.arange(n_vox)]

    # Gelişme olan vokselleri güncelle
    improve = best_E_val > topk_E_cancer
    imp_vox = torch.where(improve)[0]

    if len(imp_vox) > 0:
        imp_batch = best_b_idx[imp_vox]

        topk_E_cancer[imp_vox] = best_E_val[imp_vox]
        topk_D[imp_vox]        = D_rand[imp_batch]
        topk_P[imp_vox]        = P_rand[imp_batch]
        topk_achB[imp_vox]     = ach_B[imp_batch, imp_vox]

        # Aynı fazörlerle sağlıklı doku E-alanını hesapla
        phasors_imp     = phasors[imp_batch]                       # (|imp|, N_COILS)
        E_tot_h         = torch.einsum('nc,nvc->nv', phasors_imp, E_ebos_gpu[imp_vox])
        topk_E_healthy[imp_vox] = torch.linalg.norm(E_tot_h, dim=1)

# ══════════════════════════════════════════════════════════════════════════════
# SONUÇLARI KAYDET
# ══════════════════════════════════════════════════════════════════════════════
topk_D_np  = topk_D.cpu().numpy()
topk_P_np  = topk_P.cpu().numpy()
topk_achB_np = topk_achB.cpu().numpy()
topk_Ec_np = topk_E_cancer.cpu().numpy()
topk_Eh_np = topk_E_healthy.cpu().numpy()
valid_mask = np.isfinite(topk_Ec_np)

print(f"\n📊 Geçerli voksel : {valid_mask.sum():,} / {n_vox:,} "
      f"({100 * valid_mask.mean():.1f}%)")

all_rows = []
for i in range(n_vox):
    if not valid_mask[i]:
        continue
    cx, cy, cz = b_coords[i]
    all_rows.append(np.concatenate([
        [cx, cy, cz],
        topk_D_np[i],
        topk_P_np[i],
        [topk_achB_np[i],
         topk_Eh_np[i],   # result_E_healthy
         topk_Ec_np[i],   # result_E_cancer
         topk_D_np[i].sum(),   # duty_sum — DÜZELTİLDİ (0.0 değildi!)
         0.0]             # organ_id (petri = 0)
    ]))

cols = (
    ['x', 'y', 'z']
    + [f'D{i}' for i in range(1, 8)]
    + [f'P{i}' for i in range(1, 8)]
    + ['achieved_B', 'result_E_healthy', 'result_E_cancer', 'duty_sum', 'organ_id']
)
df_out = pd.DataFrame(all_rows, columns=cols)
df_out.to_csv(OUTPUT_FILE, index=False)

# ── İstatistik özeti ──────────────────────────────────────────────────────────
print(f"\n✅ Petri eğitim verisi kaydedildi: {OUTPUT_FILE}")
print(f"   Toplam satır     : {len(df_out):,}")
print(f"   achieved_B  → min: {df_out['achieved_B'].min():.5f}  "
      f"max: {df_out['achieved_B'].max():.5f}  "
      f"ort: {df_out['achieved_B'].mean():.5f}")
print(f"   E_cancer    → min: {df_out['result_E_cancer'].min():.2f}  "
      f"max: {df_out['result_E_cancer'].max():.2f}  "
      f"ort: {df_out['result_E_cancer'].mean():.2f}")
print(f"   E_healthy   → min: {df_out['result_E_healthy'].min():.2f}  "
      f"max: {df_out['result_E_healthy'].max():.2f}  "
      f"ort: {df_out['result_E_healthy'].mean():.2f}")
print(f"   duty_sum    → min: {df_out['duty_sum'].min():.4f}  "
      f"max: {df_out['duty_sum'].max():.4f}  "
      f"ort: {df_out['duty_sum'].mean():.4f}")