#!/usr/bin/env python3
# Author: mertaygn, cglrgrkn
"""
inference_cat_disease.py — Kedi Hastaligi Tahmin (XGBoost ONNX)
================================================================
18 kedi hastaligi siniflandirmasi.
Top-3 tahmin dondurur.

Kullanim:
  # Interaktif mod
  python inference_cat_disease.py

  # Arguman ile
  python inference_cat_disease.py --age 2 --weight 3.0 --hr 155 --temp 40.2 --duration 5 --symptoms 1,3,6,11

  # CSV toplu
  python inference_cat_disease.py --csv input.csv --output results.csv
"""

import os
import sys
import argparse
import numpy as np
import pandas as pd
import joblib
import onnxruntime as ort

# ============================================================
# CONFIG
# ============================================================
_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(_DIR, "XGBoost.pkl")
if not os.path.exists(MODEL_PATH):
    try:
        from utils.model_downloader import download_model_sync
        MODEL_PATH = download_model_sync("ai_hub/cat_disease/XGBoost.pkl")
    except Exception:
        pass
SCALER_PATH = os.path.join(_DIR, "scaler_X.pkl")
ENCODER_PATH = os.path.join(_DIR, "label_encoder.pkl")

SYMPTOM_LIST = [
    "Appetite Loss",       # 1
    "Vomiting",            # 2
    "Diarrhea",            # 3
    "Coughing",            # 4
    "Labored Breathing",   # 5
    "Lameness",            # 6
    "Skin Lesions",        # 7
    "Nasal Discharge",     # 8
    "Eye Discharge",       # 9
    "Lethargy",            # 10
    "Weight Loss",         # 11
    "Sneezing",            # 12
    "Dehydration",         # 13
    "Fever",               # 14
]

# Feature order (must match training)
FEATURE_NAMES = [
    "Age", "Weight", "Heart_Rate", "Body_Temperature", "Duration_days",
    "Appetite_Loss_bin", "Vomiting_bin", "Diarrhea_bin", "Coughing_bin",
    "Labored_Breathing_bin", "Lameness_bin", "Skin_Lesions_bin",
    "Nasal_Discharge_bin", "Eye_Discharge_bin",
    "has_Lethargy", "has_Weight_Loss", "has_Sneezing",
    "has_Dehydration", "has_Fever",
]


# ============================================================
# PREDICTOR
# ============================================================
class CatDiseasePredictor:
    def __init__(self):
        self.scaler = joblib.load(SCALER_PATH)
        self.label_encoder = joblib.load(ENCODER_PATH)
        self.diseases = list(self.label_encoder.classes_)

        self.model = joblib.load(MODEL_PATH)
        self.model.set_params(device='cpu')

        # Warmup
        dummy = np.zeros((1, 19), dtype=np.float32)
        self.model.predict_proba(self.scaler.transform(dummy))

    def _encode(self, age, weight, hr, temp, duration, symptom_indices):
        """Build 19-dim feature vector from raw inputs."""
        features = np.zeros(19, dtype=np.float32)
        features[0] = age
        features[1] = weight
        features[2] = hr
        features[3] = temp
        features[4] = duration

        # Binary symptoms (index 5-13 = 9 binary, 14-18 = 5 extracted)
        symptom_map = {
            1: 5,   # Appetite Loss -> idx 5
            2: 6,   # Vomiting -> idx 6
            3: 7,   # Diarrhea -> idx 7
            4: 8,   # Coughing -> idx 8
            5: 9,   # Labored Breathing -> idx 9
            6: 10,  # Lameness -> idx 10
            7: 11,  # Skin Lesions -> idx 11
            8: 12,  # Nasal Discharge -> idx 12
            9: 13,  # Eye Discharge -> idx 13
            10: 14, # Lethargy -> idx 14
            11: 15, # Weight Loss -> idx 15
            12: 16, # Sneezing -> idx 16
            13: 17, # Dehydration -> idx 17
            14: 18, # Fever -> idx 18
        }
        for s in symptom_indices:
            if s in symptom_map:
                features[symptom_map[s]] = 1.0

        return features.reshape(1, -1)

    def predict(self, age, weight, hr, temp, duration, symptom_indices, top_n=3):
        """Predict disease. Returns list of (disease_name, probability) tuples."""
        X_raw = self._encode(age, weight, hr, temp, duration, symptom_indices)
        X_scaled = self.scaler.transform(X_raw).astype(np.float32)

        probs = self.model.predict_proba(X_scaled)[0]

        top_idx = probs.argsort()[::-1][:top_n]
        results = [(self.diseases[i], float(probs[i])) for i in top_idx]
        return results

    def predict_batch(self, df):
        """Predict from DataFrame. Returns DataFrame with top-3 predictions."""
        X_raw = df[FEATURE_NAMES].values.astype(np.float32)
        X_scaled = self.scaler.transform(X_raw).astype(np.float32)

        all_probs = self.model.predict_proba(X_scaled)

        result_df = df.copy()
        for rank in range(3):
            idx = all_probs.argsort(axis=1)[:, -(rank+1)]
            result_df[f"Pred_{rank+1}"] = [self.diseases[i] for i in idx]
            result_df[f"Prob_{rank+1}"] = [f"{all_probs[row, idx[row]]*100:.1f}%" for row in range(len(idx))]
        return result_df


# ============================================================
# CLI
# ============================================================
def print_symptom_menu():
    print("\n  Semptom listesi:")
    for i, s in enumerate(SYMPTOM_LIST, 1):
        print(f"    {i:2d}. {s}")


def main():
    parser = argparse.ArgumentParser(
        description="Kedi Hastaligi Tahmin — XGBoost (Acc=%92.3)",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--age", type=int, help="Yas (1-15)")
    parser.add_argument("--weight", type=float, help="Kilo (kg)")
    parser.add_argument("--hr", type=int, help="Nabiz (bpm)")
    parser.add_argument("--temp", type=float, help="Ates (°C)")
    parser.add_argument("--duration", type=int, help="Sure (gun)")
    parser.add_argument("--symptoms", type=str, help="Semptom numaralari (virgülle: 1,3,10)")
    parser.add_argument("--csv", type=str, help="Input CSV")
    parser.add_argument("--output", type=str, default="predictions.csv")
    args = parser.parse_args()

    print("=" * 60)
    print("Kedi Hastaligi Tahmin Sistemi")
    print("XGBoost — 18 hastalik, %92.3 accuracy")
    print("=" * 60)

    predictor = CatDiseasePredictor()

    if args.csv:
        # Toplu tahmin
        df = pd.read_csv(args.csv)
        result = predictor.predict_batch(df)
        result.to_csv(args.output, index=False)
        print(f"\nSonuclar: {args.output}")
        print(result[["Pred_1", "Prob_1", "Pred_2", "Prob_2", "Pred_3", "Prob_3"]].head())

    elif args.age is not None:
        # Arguman ile
        sym_idx = [int(x) for x in args.symptoms.split(",")] if args.symptoms else []
        results = predictor.predict(args.age, args.weight, args.hr, args.temp, args.duration, sym_idx)
        print(f"\nTahmin:")
        for rank, (disease, prob) in enumerate(results, 1):
            bar = "█" * int(prob * 50)
            print(f"  {rank}. {disease:35s} %{prob*100:.1f}  {bar}")

    else:
        # Interaktif mod
        print_symptom_menu()
        print("\n  Interaktif mod (cikmak icin 'q')")
        print("-" * 60)

        while True:
            try:
                print()
                age = input("  Yas (1-15): ").strip()
                if age.lower() in ('q', 'quit', 'exit', ''):
                    break
                age = int(age)

                weight = float(input("  Kilo (kg): ").strip())
                hr = int(input("  Nabiz (bpm): ").strip())
                temp = float(input("  Ates (°C): ").strip())
                duration = int(input("  Sure (gun): ").strip())

                print_symptom_menu()
                sym_str = input("  Semptom numaralari (virgülle, ornek: 1,3,10): ").strip()
                sym_idx = [int(x.strip()) for x in sym_str.split(",") if x.strip()] if sym_str else []

                results = predictor.predict(age, weight, hr, temp, duration, sym_idx)

                print(f"\n  {'='*50}")
                print(f"  TAHMIN:")
                print(f"  {'='*50}")
                for rank, (disease, prob) in enumerate(results, 1):
                    bar = "█" * int(prob * 40)
                    print(f"  {rank}. {disease:35s} %{prob*100:.1f}  {bar}")

            except KeyboardInterrupt:
                print("\n  Cikis.")
                break
            except Exception as e:
                print(f"  Hata: {e}")


if __name__ == "__main__":
    main()
