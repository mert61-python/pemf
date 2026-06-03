# -*- coding: utf-8 -*-
"""
VERİ ÜRETİCİ — PHANTOM v7 (Profesyonel)
══════════════════════════════════════════════════════════════════════════════
Amaç     : Phantom (vücut modeli) için hem sağlıklı (ebos) hem kanserli (edolu)
           doku konfigürasyonunda eğitim verisi üretmek.
           P1 = 0 (referans faz, sabitlendi)

organ_id : 0 = Sağlıklı doku (ebos), hedef → E_healthy max
           1 = Kanserli doku (edolu), hedef → E_cancer max

Çıktı    : training_data_phantom_v7.csv
Sütunlar : x, y, z, D1-D7, P1-P7, achieved_B,
           result_E_healthy, result_E_cancer, duty_sum, organ_id

Düzeltmeler (v6→v7):
  - N_SEARCH 30k→80k (çok düşük arama sayısı artırıldı)
  - Progress bar her organ için detaylı
  - Geçersiz satır filtreleme güçlendirildi
  - İstatistik özeti eklendi
══════════════════════════════════════════════════════════════════════════════
"""

import os
import numpy as np
import pandas as pd
import torch
from scipy.spatial import cKDTree
from sklearn.cluster import MiniBatchKMeans
from tqdm import tqdm

print("🚀 PHANTOM VERİ ÜRETİCİ v7 — Kompleks E-Alan + P1=0 Faz Optimizasyonu\n")

# ══════════════════════════════════════════════════════════════════════════════
# DOSYA YOLLARI
# ══════════════════════════════════════════════════════════════════════════════
EXPORT_PATH   = r"C:\Users\merta\.conda\envs\gui\gui\ealanai\petri\CST_Export"
B_MATRIX_PATH = r"C:\Users\merta\.conda\envs\gui\gui\ealanai\manyetik_matris.npz"

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = os.path.join(BASE_DIR, "training_data_phantom_v7.csv")

print(f"📂 CST Yolu    : {EXPORT_PATH}")
print(f"🧲 B-Matris   : {B_MATRIX_PATH}")
print(f"💾 Çıktı      : {OUTPUT_FILE}\n")

# ══════════════════════════════════════════════════════════════════════════════
# HİPERPARAMETRELER
# ══════════════════════════════════════════════════════════════════════════════
TARGET_B   = 0.001    # 1 mT
B_TOL      = 0.03     # ±%3 (petri'den daha sıkı)
D_MAX      = 0.50
D_MIN      = 0.01
BATCH_SIZE = 256
N_SEARCH   = 80_000   # DÜZELTİLDİ: 30k → 80k (çok düşükti)
N_SAMPLES  = 60_000   # Her organ tipi için örneklenecek voksel
N_COILS    = 7
N_CLUSTERS = 300      # Uzamsal stratifikasyon için küme sayısı

# ══════════════════════════════════════════════════════════════════════════════
# YARDIMCI FONKSİYONLAR
# ══════════════════════════════════════════════════════════════════════════════
def read_efield_file(path: str) -> pd.DataFrame:
    """CST Studio Suite E-alan txt dosyasını okur."""
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


def spatial_stratified_sample(coords: np.ndarray, n_samples: int,
                               n_clusters: int = N_CLUSTERS) -> np.ndarray:
    """
    Uzamsal olarak dengeli örnekleme: koordinat uzayını kümelere böler,
    her kümeden eşit sayıda örnek alır. Yoğun bölgelerin aşırı temsili önlenir.
    """
    nc      = min(n_clusters, len(coords))
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
    # Yeterli örnek yoksa rastgele tamamla
    if len(indices) < n_samples:
        extra   = np.random.choice(len(coords), n_samples - len(indices), replace=False)
        indices = np.concatenate([indices, extra])
    return indices[:n_samples]

# ══════════════════════════════════════════════════════════════════════════════
# CST E-ALANI YÜKLEME
# ══════════════════════════════════════════════════════════════════════════════
# Temel koordinat dosyasını bul (edolu veya ebos)
p_base = None
for suffix in ['edolu', 'ebos']:
    candidate = os.path.join(EXPORT_PATH, f"bobin1_{suffix}.txt")
    if os.path.exists(candidate):
        p_base = candidate
        print(f"📡 Temel dosya : bobin1_{suffix}.txt")
        break
if p_base is None:
    raise FileNotFoundError(
        f"'{EXPORT_PATH}' klasöründe bobin1_edolu.txt veya bobin1_ebos.txt bulunamadı!"
    )

base_df  = read_efield_file(p_base)
e_coords = base_df[['x', 'y', 'z']].values.astype(np.float32)
e_tree   = cKDTree(e_coords)
n_pts    = len(e_coords)
print(f"   CST nokta sayısı : {n_pts:,}\n")

E_ebos_mat  = np.zeros((N_COILS, n_pts, 3), dtype=np.complex64)   # Sağlıklı
E_edolu_mat = np.zeros((N_COILS, n_pts, 3), dtype=np.complex64)   # Kanserli

print("📡 CST dosyaları yükleniyor...")
for i in range(1, N_COILS + 1):
    for suffix, mat in [('ebos', E_ebos_mat), ('edolu', E_edolu_mat)]:
        p = os.path.join(EXPORT_PATH, f"bobin{i}_{suffix}.txt")
        if not os.path.exists(p):
            print(f"   ⚠️  Bulunamadı: bobin{i}_{suffix}.txt")
            continue
        df_e  = read_efield_file(p)
        vals  = np.stack([
            df_e['ExRe'] + 1j * df_e['ExIm'],
            df_e['EyRe'] + 1j * df_e['EyIm'],
            df_e['EzRe'] + 1j * df_e['EzIm']
        ], axis=-1).astype(np.complex64)
        _, idx = e_tree.query(df_e[['x', 'y', 'z']].values)
        valid  = idx < n_pts
        mat[i - 1, idx[valid]] = vals[valid]
    print(f"   ✅ Bobin {i} yüklendi.")

# ══════════════════════════════════════════════════════════════════════════════
# B-ALANI YÜKLEME VE EŞLEŞTİRME
# ══════════════════════════════════════════════════════════════════════════════
print("\n📡 B-matris yükleniyor...")
b_data   = np.load(B_MATRIX_PATH)
b_coords = b_data['coords']
B_tensor = np.transpose(
    np.max(np.linalg.norm(b_data['B_matrix'], axis=-1), axis=1), (1, 0)
)
b_tree       = cKDTree(b_coords)
_, B_idx_all = b_tree.query(e_coords)
B_all        = B_tensor[B_idx_all]   # Her CST noktası için B değerleri
print(f"   B vokseli : {len(b_coords):,}\n")

# ══════════════════════════════════════════════════════════════════════════════
# GPU'YA TRANSFER
# ══════════════════════════════════════════════════════════════════════════════
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
print(f"⚡ Hesaplama cihazı : {device}")

B_all_gpu   = torch.tensor(B_all,       dtype=torch.float32,  device=device)
E_ebos_gpu  = torch.tensor(E_ebos_mat,  dtype=torch.complex64, device=device)
E_edolu_gpu = torch.tensor(E_edolu_mat, dtype=torch.complex64, device=device)

B_lo      = TARGET_B * (1 - B_TOL)
B_hi      = TARGET_B * (1 + B_TOL)
N_BATCHES = N_SEARCH // BATCH_SIZE

print(f"   B bant    : [{B_lo:.5f}, {B_hi:.5f}] T")
print(f"   N_SEARCH  : {N_SEARCH:,}  |  Batch: {N_BATCHES:,}\n")

# ══════════════════════════════════════════════════════════════════════════════
# ORGAN KONFİGÜRASYONLARI
# organ_id 0: Sağlıklı doku → E_primary = ebos, E_secondary = edolu
# organ_id 1: Kanserli doku → E_primary = edolu, E_secondary = ebos
# ══════════════════════════════════════════════════════════════════════════════
organ_configs = {
    0: {"name": "Sağlıklı (ebos)",   "E_primary": E_ebos_gpu,  "E_secondary": E_edolu_gpu},
    1: {"name": "Kanserli (edolu)",  "E_primary": E_edolu_gpu, "E_secondary": E_ebos_gpu},
}

all_rows = []
np.random.seed(42)

for oid, cfg in organ_configs.items():
    print(f"\n{'='*65}")
    print(f"  Organ {oid}: {cfg['name']}  |  Örneklenecek: {N_SAMPLES:,}")
    print(f"{'='*65}")

    # Uzamsal stratifikasyon ile voksel seçimi
    vox_idx_np  = spatial_stratified_sample(e_coords, N_SAMPLES)
    n_vox       = len(vox_idx_np)
    vox_idx_gpu = torch.tensor(vox_idx_np, dtype=torch.long, device=device)

    B_org       = B_all_gpu[vox_idx_gpu]
    E_primary   = cfg['E_primary'][:, vox_idx_gpu, :].permute(1, 2, 0)    # (N_vox, 3, N_coils)
    E_secondary = cfg['E_secondary'][:, vox_idx_gpu, :].permute(1, 2, 0)  # (N_vox, 3, N_coils)

    # En iyi değerleri izle
    topk_E_primary   = torch.full((n_vox,), -float('inf'), device=device)
    topk_E_secondary = torch.zeros(n_vox,  dtype=torch.float32, device=device)
    topk_D           = torch.zeros((n_vox, N_COILS), dtype=torch.float32, device=device)
    topk_P           = torch.zeros((n_vox, N_COILS), dtype=torch.float32, device=device)
    topk_achB        = torch.zeros(n_vox,  dtype=torch.float32, device=device)

    for _ in tqdm(range(N_BATCHES), desc=f"  🔍 Organ {oid} Arama"):
        D_rand       = torch.rand((BATCH_SIZE, N_COILS), device=device) * (D_MAX - D_MIN) + D_MIN
        P_rand       = torch.rand((BATCH_SIZE, N_COILS), device=device) * 360.0
        P_rand[:, 0] = 0.0   # P1 = 0 sabiti

        phasors = D_rand * torch.exp(1j * torch.deg2rad(P_rand))

        # Birincil doku E-alanı
        E_tot_p  = torch.einsum('bc,nvc->bnv', phasors, E_primary)
        E_mag_p  = torch.linalg.norm(E_tot_p, dim=2)

        # Manyetik alan kısıtı
        ach_B   = torch.einsum('bc,nc->bn', D_rand, B_org)
        in_band = (ach_B >= B_lo) & (ach_B <= B_hi)

        E_masked   = torch.where(in_band, E_mag_p, torch.tensor(-float('inf'), device=device))
        best_b_idx = E_masked.argmax(dim=0)
        best_E_val = E_masked[best_b_idx, torch.arange(n_vox)]

        improve = best_E_val > topk_E_primary
        imp_vox = torch.where(improve)[0]

        if len(imp_vox) > 0:
            imp_batch = best_b_idx[imp_vox]
            topk_E_primary[imp_vox] = best_E_val[imp_vox]
            topk_D[imp_vox]         = D_rand[imp_batch]
            topk_P[imp_vox]         = P_rand[imp_batch]
            topk_achB[imp_vox]      = ach_B[imp_batch, imp_vox]

            # İkincil doku E-alanını aynı fazörlerle hesapla
            E_tot_s = torch.einsum('nc,nvc->nv', phasors[imp_batch], E_secondary[imp_vox])
            topk_E_secondary[imp_vox] = torch.linalg.norm(E_tot_s, dim=1)

    # Sonuçları CPU'ya al
    topk_D_cpu   = topk_D.cpu().numpy()
    topk_P_cpu   = topk_P.cpu().numpy()
    topk_achB_cpu = topk_achB.cpu().numpy()
    topk_Ep_cpu  = topk_E_primary.cpu().numpy()
    topk_Es_cpu  = topk_E_secondary.cpu().numpy()
    valid_mask   = np.isfinite(topk_Ep_cpu)

    print(f"  Geçerli voksel : {valid_mask.sum():,} / {n_vox:,} "
          f"({100 * valid_mask.mean():.1f}%)")

    for k in range(n_vox):
        if not valid_mask[k]:
            continue
        cx, cy, cz = e_coords[vox_idx_np[k]]

        # organ_id'ye göre E_healthy / E_cancer ataması
        E_healthy = float(topk_Ep_cpu[k]) if oid == 0 else float(topk_Es_cpu[k])
        E_cancer  = float(topk_Es_cpu[k]) if oid == 0 else float(topk_Ep_cpu[k])

        all_rows.append(np.concatenate([
            [cx, cy, cz],
            topk_D_cpu[k],
            topk_P_cpu[k],
            [topk_achB_cpu[k],
             E_healthy,
             E_cancer,
             topk_D_cpu[k].sum(),   # duty_sum (gerçek hesaplama)
             float(oid)]
        ]))

# ══════════════════════════════════════════════════════════════════════════════
# SONUÇLARI KAYDET
# ══════════════════════════════════════════════════════════════════════════════
cols = (
    ['x', 'y', 'z']
    + [f'D{i}' for i in range(1, 8)]
    + [f'P{i}' for i in range(1, 8)]
    + ['achieved_B', 'result_E_healthy', 'result_E_cancer', 'duty_sum', 'organ_id']
)
df_out = pd.DataFrame(all_rows, columns=cols)
df_out.to_csv(OUTPUT_FILE, index=False)

# ── İstatistik özeti ──────────────────────────────────────────────────────────
print(f"\n✅ Phantom eğitim verisi kaydedildi: {OUTPUT_FILE}")
print(f"   Toplam satır : {len(df_out):,}")
for oid in sorted(df_out['organ_id'].unique()):
    subset = df_out[df_out['organ_id'] == oid]
    name   = "Sağlıklı" if oid == 0 else "Kanserli"
    print(f"\n   Organ {int(oid)} ({name}) — {len(subset):,} satır:")
    print(f"     achieved_B  : ort={subset['achieved_B'].mean():.5f}  "
          f"std={subset['achieved_B'].std():.5f}")
    print(f"     E_healthy   : ort={subset['result_E_healthy'].mean():.2f}  "
          f"max={subset['result_E_healthy'].max():.2f}")
    print(f"     E_cancer    : ort={subset['result_E_cancer'].mean():.2f}  "
          f"max={subset['result_E_cancer'].max():.2f}")
    print(f"     duty_sum    : ort={subset['duty_sum'].mean():.4f}  "
          f"std={subset['duty_sum'].std():.4f}")