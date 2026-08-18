# -*- coding: utf-8 -*-
"""
Created on Tue Apr 14 15:24:25 2026

@author: merta
"""

import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import joblib
import onnxruntime as ort

print("⚡ AI E-Alanı 3D Performans Haritası (V9) Yükleniyor...")

# ─── 1. YOLLAR VE AYARLAR ────────────────────────────────────────────────────
base_dir      = os.path.dirname(os.path.abspath(__file__))
export_path   = os.path.join(base_dir, "CST_Export")

onnx_path     = os.path.join(base_dir, "ResNet_v9.onnx")
scaler_x_path = os.path.join(base_dir, "scaler_X_v9.pkl")
scaler_y_path = os.path.join(base_dir, "scaler_y_v9.pkl")

# HANGİ ORGANI TEST ETMEK İSTİYORSUNUZ?
ORGAN_ID = 0  # 0: kutu_butun, 1: mide, 2: bobrek, 3: karaciger, 4: mesane, 5: pankreas, 6: bagirsak

organ_names = {0: 'kutu_butun', 1: 'mide', 2: 'bobrek', 
               3: 'karaciger', 4: 'mesane', 5: 'pankreas', 6: 'bagirsak'}
organ_name = organ_names[ORGAN_ID]

# ─── 2. YÜKLEMELER ──────────────────────────────────────────────────────────
print("📦 Model ve Scaler'lar yükleniyor...")
scaler_X = joblib.load(scaler_x_path)
scaler_y = joblib.load(scaler_y_path)
ort_session = ort.InferenceSession(onnx_path)
input_name = ort_session.get_inputs()[0].name

print(f"📡 {organ_name.upper()} organı için CST E-Alanı verileri okunuyor...")
all_v = []
coords = None

# Organa ait 7 bobinin E-field txt dosyalarını oku
for i in range(1, 8):
    path = os.path.join(export_path, f"bobin{i}_{organ_name}_efield.txt")
    if not os.path.exists(path):
        print(f"❌ HATA: {path} dosyası bulunamadı! CST_Export klasörünü kontrol edin.")
        exit()
        
    df_e = pd.read_csv(path, sep=r'\s+', skiprows=2, 
                       names=['x', 'y', 'z', 'ExRe', 'ExIm', 'EyRe', 'EyIm', 'EzRe', 'EzIm'])
    
    if coords is None:
        coords = df_e[['x', 'y', 'z']].values.astype(np.float32)
        
    comp = np.stack([
        df_e['ExRe'].values + 1j * df_e['ExIm'].values,
        df_e['EyRe'].values + 1j * df_e['EyIm'].values,
        df_e['EzRe'].values + 1j * df_e['EzIm'].values,
    ], axis=-1)  # Shape: (N, 3)
    all_v.append(comp)

# Shape: (N_voxel, 3_Eksen, 7_Bobin)
E_complex = np.stack(all_v, axis=2)
n_points = len(coords)
print(f"📐 Toplam {n_points:,} voksel bulundu. AI tahminleri başlatılıyor...")

# ─── 3. YAPAY ZEKA TAHMİNLERİ (INFERENCE) ────────────────────────────────────
# Tüm koordinatları tek seferde modele sokarak hızlandırıyoruz
coords_sc = scaler_X.transform(coords).astype(np.float32)
organ_id_arr = np.full((n_points, 1), ORGAN_ID, dtype=np.float32)
inp = np.hstack([coords_sc, organ_id_arr])

out_sc = ort_session.run(None, {input_name: inp})[0]
out    = scaler_y.inverse_transform(out_sc)

# Duty ve Phase değerlerini ayrıştır
D_preds = np.clip(out[:, 0:7], 0.01, 0.50)  # Shape: (N, 7)
sin_P = out[:, 7:14]
cos_P = out[:, 14:21]
P_rad = np.arctan2(sin_P, cos_P)            # Shape: (N, 7)

# ─── 4. FİZİKSEL E-ALANI HESAPLAMA ──────────────────────────────────────────
print("🔬 Tahminlerin fiziksel E-Alanı karşılığı hesaplanıyor...")
# Kompleks fazör hesabı: D * e^(j * P)
phasors = D_preds * np.exp(1j * P_rad)  # Shape: (N, 7)

# Tensör çarpımı ile fiziksel E-Alan vektörünü oluştur (Ex, Ey, Ez)
E_tot = np.einsum('nc,nvc->nv', phasors, E_complex)  # Shape: (N, 3)

# E-Alan genliğini (Magnitude) hesapla
E_mag = np.linalg.norm(E_tot, axis=1)  # Shape: (N,)

# ─── 5. 3D HARİTAYI ÇİZDİRME ────────────────────────────────────────────────
print("🎨 E-Alanı haritası çizdiriliyor...")

X_c = coords[:, 0]
Y_c = coords[:, 1]
Z_c = coords[:, 2]

fig = plt.figure(figsize=(12, 10))
ax = fig.add_subplot(111, projection='3d')

# E-alanı haritası için B-alanından farklı olarak "plasma" renk paletini kullanıyoruz
# Yüksek E-alanı sarı/beyaz, düşük E-alanı mor/siyah görünecek.
sc = ax.scatter(X_c, Y_c, Z_c, c=E_mag, cmap='plasma', s=15, alpha=0.8)

cbar = plt.colorbar(sc, ax=ax, shrink=0.7, pad=0.1)
cbar.set_label('Elde Edilen E-Alanı Şiddeti (V/m)', fontsize=12)

ax.set_title(f"Yapay Zeka E-Alanı Dağılım Haritası (V9)\n(Organ = {organ_name.upper()})", fontsize=14)
ax.set_xlabel("X (mm)", labelpad=10)
ax.set_ylabel("Y (mm)", labelpad=10)
ax.set_zlabel("Z (mm)", labelpad=10)

print("\n📊 E-ALANI İSTATİSTİKLERİ:")
print(f"  Organ              : {organ_name.upper()}")
print(f"  Taranan Nokta      : {n_points:,}")
print(f"  Max E-Alanı        : {np.max(E_mag):.3f} V/m")
print(f"  Min E-Alanı        : {np.min(E_mag):.3f} V/m")
print(f"  Ortalama E-Alanı   : {np.mean(E_mag):.3f} V/m")

plt.show()