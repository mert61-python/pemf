import os
import numpy as np
import matplotlib.pyplot as plt
import joblib
import onnxruntime as ort

print("⚡ PETRİ-BOT EVRENSEL: 3D E-Alanı Stres Haritası ve İstatistikler...")

# ─── 1. YOLLAR VE YÜKLEME ────────────────────────────────────────────────────
base_dir      = os.path.dirname(os.path.abspath(__file__))
onnx_path     = os.path.join(base_dir, "PetriNet_Evrensel.onnx")
scaler_x_path = os.path.join(base_dir, "scaler_X_evrensel.pkl")
scaler_y_path = os.path.join(base_dir, "scaler_y_evrensel.pkl")
b_matrix_path = os.path.join(base_dir, "manyetik_matris.npz")

scaler_X = joblib.load(scaler_x_path)
scaler_y = joblib.load(scaler_y_path)
ort_session = ort.InferenceSession(onnx_path)

b_data = np.load(b_matrix_path)
B_coords = b_data['coords'].astype(np.float32)

# 15.000 rastgele nokta seçimi
np.random.seed(42)
sample_size = 15000
sampled_idx = np.random.choice(B_coords.shape[0], sample_size, replace=False)
test_coords = B_coords[sampled_idx]

# ─── 2. YAPAY ZEKA TAHMİNİ ───────────────────────────────────────────────────
print("🤖 Yapay Zeka fiziksel E-Alanlarını hesaplıyor...")
X_scaled = scaler_X.transform(test_coords).astype(np.float32)

all_outs = []
for i in range(X_scaled.shape[0]):
    ort_inputs = {ort_session.get_inputs()[0].name: X_scaled[i:i+1]}
    out = ort_session.run(None, ort_inputs)[0]
    all_outs.append(out)

ort_outs = np.vstack(all_outs)
y_pred_real = scaler_y.inverse_transform(ort_outs)

# Kanserli Hücre E-Alanını Çek (21. İndeks)
E_kanserli_Vm = np.maximum(y_pred_real[:, 21], 0) 

# ─── 3. 3D ÇİZİM ─────────────────────────────────────────────────────────────
X_c, Y_c, Z_c = test_coords[:, 0], test_coords[:, 1], test_coords[:, 2]
fig = plt.figure(figsize=(10, 8))
ax = fig.add_subplot(111, projection='3d')
sc = ax.scatter(X_c, Y_c, Z_c, c=E_kanserli_Vm, cmap='plasma', s=15, alpha=0.7)
plt.colorbar(sc, ax=ax, shrink=0.6, pad=0.1).set_label('E-Alanı (V/m)')
ax.set_title("⚡ Kutu İçi E-Alanı Isı Haritası")
plt.show()

# ─── 4. 📊 TALEP ETTİĞİN İSTATİSTİK PANELİ ───────────────────────────────────
print("\n" + "="*40)
print("📊 E-ALANI İSTATİSTİKLERİ:")
print(f"  Bölge              : TÜM PETRİ KABI")
print(f"  Taranan Nokta      : {len(E_kanserli_Vm):,}")
print(f"  Max E-Alanı        : {np.max(E_kanserli_Vm):.3f} V/m")
print(f"  Min E-Alanı        : {np.min(E_kanserli_Vm):.3f} V/m")
print(f"  Ortalama E-Alanı   : {np.mean(E_kanserli_Vm):.3f} V/m")
print("="*40 + "\n")