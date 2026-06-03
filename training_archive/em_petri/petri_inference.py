# -*- coding: utf-8 -*-
"""
Created on Sun Apr 19 23:49:21 2026

@author: merta
"""

# -*- coding: utf-8 -*-
import os
import numpy as np
import joblib
import onnxruntime as ort

# =====================================================================
# AYARLAR VE YÜKLEMELER (GUI donmaması için sadece 1 kez çalışır)
# =====================================================================
BASE_DIR = r"C:\Users\merta\.conda\envs\gui\gui\ealanai\petri" # KENDİ YOLUNUZLA DEĞİŞTİRİN

# Modeli ve Scaler'ları hafızaya al
SESSION = ort.InferenceSession(os.path.join(BASE_DIR, "PetriNet_v2.onnx"), providers=['CPUExecutionProvider'])
SCALER_X = joblib.load(os.path.join(BASE_DIR, "scaler_X_petri.pkl"))
SCALER_EXTRA = joblib.load(os.path.join(BASE_DIR, "scaler_extra_petri.pkl"))
SCALER_Y = joblib.load(os.path.join(BASE_DIR, "scaler_y_petri.pkl"))

# =====================================================================
# INFERENCE FONKSİYONU
# =====================================================================
def infer_petri(x: float, y: float, z: float, organ_id: float, achieved_B: float, duty_sum: float) -> dict:
    # 1. Girdileri Numpy dizisine çevir ve ölçekle
    coords = np.array([[x, y, z]], dtype=np.float32)
    extras = np.array([[achieved_B, duty_sum]], dtype=np.float32)
    
    coords_sc = SCALER_X.transform(coords)
    extras_sc = SCALER_EXTRA.transform(extras)
    organ_arr = np.array([[organ_id]], dtype=np.float32)
    
    # 2. [x_sc, y_sc, z_sc, organ_id, achieved_B_sc, duty_sum_sc] birleştir
    input_tensor = np.hstack([coords_sc, organ_arr, extras_sc]).astype(np.float32)
    
    # 3. ONNX Modelinden geçir
    input_name = SESSION.get_inputs()[0].name
    raw_out = SESSION.run(None, {input_name: input_tensor})[0]
    
    # 4. Çıktıyı ters ölçekle (Gerçek değerlere dönüştür)
    pred = SCALER_Y.inverse_transform(raw_out)[0]
    
    # 5. Duty Cycle ve Faz açılarını hesapla
    D = np.clip(pred[0:7], 0.0, 1.0) # 0 ile 1 arasına sıkıştır
    
    sinP, cosP = pred[7:14], pred[14:21]
    P_deg = np.degrees(np.arctan2(sinP, cosP)) % 360.0
    P_deg[0] = 0.0 # P1 her zaman 0 referans
    
    # 6. Sonuçları döndür
    return {
        "Duty_Cycles": D.tolist(),
        "Phases_Deg": P_deg.tolist(),
        "E_Healthy": float(pred[21]),
        "E_Cancer": float(pred[22])
    }

# --- Test İçin ---
if __name__ == "__main__":
    sonuc = infer_petri(x=0.01, y=-0.02, z=0.05, organ_id=0.0, achieved_B=0.001, duty_sum=2.4)
    print("PETRİ SONUÇLARI:")
    for k, v in sonuc.items():
        print(f"{k}: {np.round(v, 4) if isinstance(v, list) else round(v, 4)}")