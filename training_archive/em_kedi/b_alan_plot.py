# -*- coding: utf-8 -*-
"""
Created on Tue Apr 14 15:50:29 2026

@author: merta
"""

import os
import numpy as np
import matplotlib.pyplot as plt
import joblib
import onnxruntime as ort
from scipy.spatial import cKDTree

print("🌌 AI B-Alanı 3D Performans Haritası (V9) Yükleniyor...")

# ─── 1. YOLLAR VE AYARLAR ────────────────────────────────────────────────────
base_dir      = os.path.dirname(os.path.abspath(__file__))
parent_dir    = os.path.dirname(base_dir) 

# V9 Dosyaları
onnx_path     = os.path.join(base_dir, "ResNet_v9.onnx")
scaler_x_path = os.path.join(base_dir, "scaler_X_v9.pkl")
scaler_y_path = os.path.join(base_dir, "scaler_y_v9.pkl")
b_matrix_path = os.path.join(parent_dir, "manyetik_matris.npz")

# HANGİ ORGANI TEST ETMEK İSTİYORSUNUZ?
ORGAN_ID = 0  # 0 = kutu_butun, 4 = mesane, 1 = mide

# ─── 2. YÜKLEMELER ──────────────────────────────────────────────────────────
print("📦 Model ve Scaler'lar yükleniyor...")
scaler_X = joblib.load(scaler_x_path)
scaler_y = joblib.load(scaler_y_path)
ort_session = ort.InferenceSession(onnx_path)
input_name = ort_session.get_inputs()[0].name

print("🧲 Manyetik Matris yükleniyor (Fiziksel doğrulama için)...")
b_data       = np.load(b_matrix_path)
b_coords     = b_data['coords']
B_matrix_raw = b_data['B_matrix']

# (N_Voxel, 7) formuna getiriyoruz
B_vec_mag    = np.linalg.norm(B_matrix_raw, axis=-1)
B_max_time   = np.max(B_vec_mag, axis=1) 
B_tensor     = np.transpose(B_max_time, (1, 0))  

b_tree = cKDTree(b_coords)

# ─── 3. 3D IZGARA (GRID) OLUŞTURMA ───────────────────────────────────────────
# X, Y ve Z için tüm hacmi tarayacak 3 boyutlu noktalar
x_lin = np.linspace(-50, 50, 25)
y_lin = np.linspace(-40, 50, 25)
z_lin = np.linspace(-70, 60, 30)

X, Y, Z = np.meshgrid(x_lin, y_lin, z_lin)
grid_coords = np.c_[X.ravel(), Y.ravel(), Z.ravel()]
n_points    = len(grid_coords)
print(f"📐 {n_points:,} nokta için 3 Boyutlu AI tahmini yapılacak...")

# ─── 4. YAPAY ZEKA TAHMİNLERİ (INFERENCE) ────────────────────────────────────
coords_sc = scaler_X.transform(grid_coords).astype(np.float32)
organ_id_arr = np.full((n_points, 1), ORGAN_ID, dtype=np.float32)
inp = np.hstack([coords_sc, organ_id_arr])

out_sc = ort_session.run(None, {input_name: inp})[0]
out    = scaler_y.inverse_transform(out_sc)
# Duty değerlerini kırp (0.01 - 0.50 arası)
D_preds = np.clip(out[:, 0:7], 0.01, 0.50)

# ─── 5. FİZİKSEL HESAPLAMA ──────────────────────────────────────────────────
print("🔬 Tahminlerin fiziksel manyetik karşılığı hesaplanıyor...")
_, nearest_b_idx = b_tree.query(grid_coords)
B_true_vals = B_tensor[nearest_b_idx]

Achieved_B_mT = np.sum(D_preds * B_true_vals, axis=1) * 1000.0

# ─── 6. 3D HARİTAYI ÇİZDİRME ────────────────────────────────────────────────
print("🎨 3D Harita çizdiriliyor...")

# Filtre: Sadece 0.8 mT ile 1.2 mT arasındaki noktaları al
mask = (Achieved_B_mT >= 0.8) & (Achieved_B_mT <= 1.2)
X_filt = grid_coords[mask, 0]
Y_filt = grid_coords[mask, 1]
Z_filt = grid_coords[mask, 2]
B_filt = Achieved_B_mT[mask]

fig = plt.figure(figsize=(12, 10))
ax = fig.add_subplot(111, projection='3d')

# Renk haritası: 1.0 hedefi ortada olacak şekilde renklenir.
sc = ax.scatter(X_filt, Y_filt, Z_filt, c=B_filt, cmap='RdYlBu_r', 
                s=25, alpha=0.7, vmin=0.8, vmax=1.2)

cbar = plt.colorbar(sc, ax=ax, shrink=0.7, pad=0.1)
cbar.set_label('Elde Edilen B-Alanı (mT)', fontsize=12)

organ_isim = {0: 'kutu_butun', 1: 'mide', 2: 'bobrek', 3: 'karaciger', 4: 'mesane', 5: 'pankreas', 6: 'bagirsak'}
ax.set_title(f"Yapay Zeka B-Alanı Başarı Bulutu (V9)\n(Organ = {organ_isim[ORGAN_ID]} | Filtre: 0.8 - 1.2 mT)", fontsize=14)
ax.set_xlabel("X (mm)", labelpad=10)
ax.set_ylabel("Y (mm)", labelpad=10)
ax.set_zlabel("Z (mm)", labelpad=10)

print("\n📊 3D İSTATİSTİKLER:")
print(f"  Taranan Toplam Nokta : {n_points:,}")
print(f"  0.8 - 1.2 mT Arası   : {np.sum(mask):,} nokta")
print(f"  Hacim Geneli Max B   : {np.max(Achieved_B_mT):.3f} mT")
print(f"  Hacim Geneli Min B   : {np.min(Achieved_B_mT):.3f} mT")
print(f"  Hacim Geneli Ort B   : {np.mean(Achieved_B_mT):.3f} mT")

plt.show()