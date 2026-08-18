# -*- coding: utf-8 -*-
"""
Created on Sun Apr 19 23:49:58 2026

@author: merta
"""

# -*- coding: utf-8 -*-
import os
import numpy as np
import joblib
import onnxruntime as ort

# =====================================================================
# AYARLAR VE YÜKLEMELER
# =====================================================================
BASE_DIR = r"C:\Users\merta\.conda\envs\gui\gui\ealanai" # KENDİ YOLUNUZLA DEĞİŞTİRİN

SESSION = ort.InferenceSession(os.path.join(BASE_DIR, "ResNet_kedi_v2.onnx"), providers=['CPUExecutionProvider'])
SCALER_X = joblib.load(os.path.join(BASE_DIR, "scaler_X_kedi_v2.pkl"))
SCALER_EXTRA = joblib.load(os.path.join(BASE_DIR, "scaler_extra_kedi.pkl"))
SCALER_Y = joblib.load(os.path.join(BASE_DIR, "scaler_y_kedi_v2.pkl"))

# =====================================================================
# INFERENCE FONKSİYONU
# =====================================================================
def infer_kedi(x: float, y: float, z: float, organ_id: float, achieved_B: float, duty_sum: float) -> dict:
    coords = np.array([[x, y, z]], dtype=np.float32)
    extras = np.array([[achieved_B, duty_sum]], dtype=np.float32)
    
    coords_sc = SCALER_X.transform(coords)
    extras_sc = SCALER_EXTRA.transform(extras)
    organ_arr = np.array([[organ_id]], dtype=np.float32) # Organ ID: 0'dan 6'ya kadar
    
    input_tensor = np.hstack([coords_sc, organ_arr, extras_sc]).astype(np.float32)
    
    input_name = SESSION.get_inputs()[0].name
    raw_out = SESSION.run(None, {input_name: input_tensor})[0]
    
    pred = SCALER_Y.inverse_transform(raw_out)[0]
    
    D = np.clip(pred[0:7], 0.0, 1.0)
    
    sinP, cosP = pred[7:14], pred[14:21]
    P_deg = np.degrees(np.arctan2(sinP, cosP)) % 360.0
    P_deg[0] = 0.0 
    
    # Kedi modelinde 22. indeks (index 21) tek E-Alan değeridir
    return {
        "Duty_Cycles": D.tolist(),
        "Phases_Deg": P_deg.tolist(),
        "E_Field": float(pred[21]) 
    }

# --- Test İçin ---
if __name__ == "__main__":
    sonuc = infer_kedi(x=0.01, y=-0.02, z=0.05, organ_id=2.0, achieved_B=0.001, duty_sum=2.3)
    print("KEDİ SONUÇLARI:")
    for k, v in sonuc.items():
        print(f"{k}: {np.round(v, 4) if isinstance(v, list) else round(v, 4)}")