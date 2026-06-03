"""
Dataset 1 Inference — ONNX Runtime
===================================
Girdi : x, y, z, target_B
Çıkış : p1-p7 (açı, derece), d1-d7 (duty cycle)

Modeller:
  P (açı)  → SimpleRNN_XXL_P  (R²=0.9582)
  D (duty) → SimpleRNN_XL_D   (R²=0.9725)
"""
import os
import numpy as np
import joblib
import onnxruntime as ort

# ============================================================
# Paths
# ============================================================
MODELS_DIR = os.path.dirname(os.path.abspath(__file__))

# Scalers & masks
scaler_Xp = joblib.load(f"{MODELS_DIR}/scaler_Xp.pkl")
scaler_Xd = joblib.load(f"{MODELS_DIR}/scaler_Xd.pkl")
scaler_yd = joblib.load(f"{MODELS_DIR}/scaler_yd.pkl")
mask_P = joblib.load(f"{MODELS_DIR}/feat_mask_P.pkl")
mask_D = joblib.load(f"{MODELS_DIR}/feat_mask_D.pkl")

# ONNX sessions
sess_P = ort.InferenceSession(f"{MODELS_DIR}/SimpleRNN_XXL_P.onnx")
sess_D = ort.InferenceSession(f"{MODELS_DIR}/SimpleRNN_XL_D.onnx")

# ============================================================
# Feature Engineering (training ile aynı)
# ============================================================
def build_features_P(x, y, z, target_B):
    x, y, z, tb = np.atleast_1d(x).astype(np.float64), np.atleast_1d(y).astype(np.float64), np.atleast_1d(z).astype(np.float64), np.atleast_1d(target_B).astype(np.float64)
    r_sq = x**2 + y**2 + z**2
    r = np.sqrt(r_sq)
    r_cyl = np.sqrt(x**2 + y**2)
    theta = np.arctan2(y, x)
    phi = np.arctan2(z, np.maximum(r_cyl, 1e-12))
    return np.column_stack([
        x, y, z, tb, x**2, y**2, z**2, tb**2, x*y, x*z, y*z, x*tb, y*tb, z*tb,
        r, r_cyl, r_sq, np.sin(theta), np.cos(theta), np.sin(phi), np.cos(phi),
        np.sin(2*theta), np.cos(2*theta), np.sin(2*phi), np.cos(2*phi),
        x**3, y**3, z**3, x*y*z, tb*r,
    ])

def build_features_D(x, y, z, target_B):
    x, y, z, tb = np.atleast_1d(x).astype(np.float64), np.atleast_1d(y).astype(np.float64), np.atleast_1d(z).astype(np.float64), np.atleast_1d(target_B).astype(np.float64)
    r = np.sqrt(x**2 + y**2 + z**2)
    r_cyl = np.sqrt(x**2 + y**2)
    theta = np.arctan2(y, x)
    return np.column_stack([
        x, y, z, tb, x**2, y**2, z**2, tb**2, x*y, x*z, y*z, x*tb, y*tb, z*tb,
        r, r_cyl, tb*r, np.sin(theta), np.cos(theta),
    ])

# ============================================================
# Inference
# ============================================================
def predict(x, y, z, target_B):
    """
    Tek veya batch tahmin.

    Args:
        x, y, z: konum (skaler veya array)
        target_B: hedef manyetik alan (skaler veya array)

    Returns:
        dict: {
            'p_degrees': ndarray (N, 7) — açılar (derece, 0-360),
            'd_values':  ndarray (N, 7) — duty cycle değerleri
        }
    """
    x, y, z, target_B = [np.atleast_1d(v).astype(np.float64) for v in [x, y, z, target_B]]

    # Feature engineering + selection + scaling
    Xp = scaler_Xp.transform(build_features_P(x, y, z, target_B)[:, mask_P])
    Xd = scaler_Xd.transform(build_features_D(x, y, z, target_B)[:, mask_D])

    # P tahmini (SimpleRNN_XXL) — çıkış: derece/360 normalize
    inp_name_p = sess_P.get_inputs()[0].name
    p_norm = sess_P.run(None, {inp_name_p: Xp.astype(np.float32)})[0]
    p_degrees = p_norm * 360.0  # 0-360 dereceye dönüştür

    # D tahmini (SimpleRNN_XL) — çıkış: scaled
    inp_name_d = sess_D.get_inputs()[0].name
    d_scaled = sess_D.run(None, {inp_name_d: Xd.astype(np.float32)})[0]
    d_values = scaler_yd.inverse_transform(d_scaled)

    return {
        'p_degrees': p_degrees,  # (N, 7) — p1..p7 açıları (derece)
        'd_values': d_values,    # (N, 7) — d1..d7 duty cycle
    }


# ============================================================
# Kullanım Örneği
# ============================================================
if __name__ == "__main__":
    # Tek nokta tahmini
    result = predict(x=0.05, y=0.02, z=0.01, target_B=0.001)
    print("=" * 60)
    print("Dataset 1 — Tekli Tahmin")
    print("=" * 60)
    print(f"Girdi: x=0.05, y=0.02, z=0.01, target_B=0.001")
    print(f"\nP (açılar, derece):")
    for i, v in enumerate(result['p_degrees'][0]):
        print(f"  p{i+1}: {v:.2f}°")
    print(f"\nD (duty cycle):")
    for i, v in enumerate(result['d_values'][0]):
        print(f"  d{i+1}: {v:.6f}")

    # Batch tahmin
    x_batch = np.array([0.05, 0.10, -0.03])
    y_batch = np.array([0.02, -0.05, 0.04])
    z_batch = np.array([0.01, 0.03, -0.02])
    tB_batch = np.array([0.001, 0.002, 0.0005])

    result_batch = predict(x_batch, y_batch, z_batch, tB_batch)
    print(f"\n{'=' * 60}")
    print(f"Dataset 1 — Batch Tahmin ({len(x_batch)} nokta)")
    print(f"{'=' * 60}")
    for i in range(len(x_batch)):
        print(f"\nNokta {i+1}: x={x_batch[i]}, y={y_batch[i]}, z={z_batch[i]}, tB={tB_batch[i]}")
        print(f"  P: {', '.join(f'{v:.1f}°' for v in result_batch['p_degrees'][i])}")
        print(f"  D: {', '.join(f'{v:.6f}' for v in result_batch['d_values'][i])}")
