# -*- coding: utf-8 -*-
"""
Created on Tue Apr 14 16:19:03 2026

@author: merta
"""

import os
import numpy as np
import matplotlib.pyplot as plt
from scipy.spatial import cKDTree

print("🚀 Fiziksel Maksimum B-Alanı Kapasite Haritası Yükleniyor...")

# ─── 1. YOLLAR VE AYARLAR ────────────────────────────────────────────────────
base_dir      = os.path.dirname(os.path.abspath(__file__))
parent_dir    = os.path.dirname(base_dir) 
b_matrix_path = os.path.join(parent_dir, "manyetik_matris.npz")

MAX_DUTY = 0.50  # %50 Maksimum Güç Sınırı

# ─── 2. MANYETİK MATRİS YÜKLEME ──────────────────────────────────────────────
print("🧲 Manyetik Matris yükleniyor...")
b_data       = np.load(b_matrix_path)
b_coords     = b_data['coords']
B_matrix_raw = b_data['B_matrix']

# Her bobinin kendi ürettiği B-Alanını bul (N_Voxel, 7)
B_vec_mag    = np.linalg.norm(B_matrix_raw, axis=-1)
B_max_time   = np.max(B_vec_mag, axis=1) 
B_tensor     = np.transpose(B_max_time, (1, 0))  

b_tree = cKDTree(b_coords)

# ─── 3. 3D IZGARA (GRID) OLUŞTURMA ───────────────────────────────────────────
x_lin = np.linspace(-50, 50, 25)
y_lin = np.linspace(-40, 50, 25)
z_lin = np.linspace(-70, 60, 30)

X, Y, Z = np.meshgrid(x_lin, y_lin, z_lin)
grid_coords = np.c_[X.ravel(), Y.ravel(), Z.ravel()]
n_points    = len(grid_coords)
print(f"📐 {n_points:,} noktalı uzay için limitler hesaplanıyor...")

# ─── 4. FİZİKSEL MAKSİMUM KAPASİTE HESABI ────────────────────────────────────
_, nearest_b_idx = b_tree.query(grid_coords)
B_true_vals = B_tensor[nearest_b_idx]

# Bütün bobinlerin B-Alanları * %50 Güç (0.50) toplanarak Maksimum Kapasite Bulunur
Max_B_Capacity_mT = np.sum(B_true_vals * MAX_DUTY, axis=1) * 1000.0

# ─── 5. 3D HARİTAYI ÇİZDİRME ────────────────────────────────────────────────
print("🎨 Harita çizdiriliyor...")

# İSTERSENİZ FİLTRE UYGULAYABİLİRSİNİZ:
# Sadece "1.0 mT'ye ULAŞAMAYAN" zayıf bölgeleri görmek isterseniz maskeyi şöyle yapın: 
# mask = Max_B_Capacity_mT < 1.0 
mask = Max_B_Capacity_mT > 0.0  # Şu an tüm noktaları gösteriyor

X_filt = grid_coords[mask, 0]
Y_filt = grid_coords[mask, 1]
Z_filt = grid_coords[mask, 2]
B_filt = Max_B_Capacity_mT[mask]

fig = plt.figure(figsize=(12, 10))
ax = fig.add_subplot(111, projection='3d')

# Renk haritası 'Spectral': Kırmızı=Düşük Kapasite, Mavi=Yüksek Kapasite
sc = ax.scatter(X_filt, Y_filt, Z_filt, c=B_filt, cmap='Spectral', 
                s=25, alpha=0.5)

cbar = plt.colorbar(sc, ax=ax, shrink=0.7, pad=0.1)
cbar.set_label('Maksimum Üretilebilecek B-Alanı (mT)', fontsize=12)

ax.set_title(f"Sistem Fiziksel Kapasite Sınırları\n(Şart: Max %50 Duty)", fontsize=14)
ax.set_xlabel("X (mm)", labelpad=10)
ax.set_ylabel("Y (mm)", labelpad=10)
ax.set_zlabel("Z (mm)", labelpad=10)

print("\n📊 KAPASİTE İSTATİSTİKLERİ:")
print(f"  Taranan Nokta        : {n_points:,}")
print(f"  Kutudaki En Yüksek Limit : {np.max(Max_B_Capacity_mT):.3f} mT")
print(f"  Kutudaki En Düşük Limit  : {np.min(Max_B_Capacity_mT):.3f} mT")
print(f"  Hacim Genel Ortalaması   : {np.mean(Max_B_Capacity_mT):.3f} mT")

# %50 duty ile 1.0 mT'ye ulaşamayan ölü bölgelerin yüzdesi
zayif_noktalar = np.sum(Max_B_Capacity_mT < 1.0)
yuzde = (zayif_noktalar / n_points) * 100
print(f"  1.0 mT'ye Ulaşamayan Bölge : {zayif_noktalar:,} nokta (Hacmin %{yuzde:.1f}'i)")

plt.show()