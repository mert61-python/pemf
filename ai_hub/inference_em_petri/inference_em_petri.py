#!/usr/bin/env python3
# Author: mertaygn, cglrgrkn
"""inference_em_petri.py — Petri Inference (Mert pattern + best ONNX).

Best model : BaggingRegressor   (Combined R2 = 0.9849)
Input  (6) : x, y, z, organ_id, achieved_B, duty_sum
        Internal layout (Mert pattern):
            [coords_sc(3), organ_id_raw(1), extras_sc(2)]
Output (15): D1-D7 (clipped [0,1]), P1-P7 (deg, gauge-fixed P1=0),
             result_E_avg (+ ayri olarak result_E_healthy, result_E_cancer)

ONNX model raw cikisi: 23-dim
    [D(7) | sin(P)(7) | cos(P)(7) | E_h | E_c]

Kullanim:
  python inference_em_petri.py --x 78 --y 210 --z -57.85 \
        --organ_id 0 --achieved_B 0.001 --duty_sum 2.4
  python inference_em_petri.py --csv input.csv --output results.csv

  from inference_em_petri import PetriPredictor
  pred = PetriPredictor()
  out = pred.predict(x=78, y=210, z=-57.85, organ_id=0,
                     achieved_B=0.001, duty_sum=2.4)
"""
import argparse
import os

import joblib
import numpy as np
import onnxruntime as ort
import pandas as pd

_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_NAME = "BaggingRegressor"
ONNX_PATH = os.path.join(_DIR, f"{MODEL_NAME}.onnx")
MODEL_DOWNLOAD_ERROR = None
if not os.path.exists(ONNX_PATH):
    try:
        from utils.model_downloader import download_model_sync
        ONNX_PATH = download_model_sync(f"ai_hub/inference_em_petri/{MODEL_NAME}.onnx")
    except Exception as exc:
        MODEL_DOWNLOAD_ERROR = exc
SCALER_X_PATH = os.path.join(_DIR, "scaler_X.pkl")
SCALER_EXTRA_PATH = os.path.join(_DIR, "scaler_extra.pkl")
SCALER_Y_PATH = os.path.join(_DIR, "scaler_y.pkl")

ORGAN_IDS = [0, 1]   # 0=saglikli, 1=kanserli
D_COLS = [f"D{i}" for i in range(1, 8)]
P_COLS = [f"P{i}" for i in range(1, 8)]
IN_DIM = 6


class PetriPredictor:
    def __init__(self, onnx_path=ONNX_PATH, scaler_x=SCALER_X_PATH,
                 scaler_extra=SCALER_EXTRA_PATH, scaler_y=SCALER_Y_PATH,
                 providers=None):
        self.sx = joblib.load(scaler_x)
        self.se = joblib.load(scaler_extra)
        self.sy = joblib.load(scaler_y)
        if providers is None:
            providers = ["CPUExecutionProvider"]
        if not os.path.exists(onnx_path):
            detail = f" İndirme hatası: {MODEL_DOWNLOAD_ERROR}" if MODEL_DOWNLOAD_ERROR else ""
            raise FileNotFoundError(
                f"{MODEL_NAME}.onnx bulunamadı ve otomatik indirilemedi.{detail}")
        self.session = ort.InferenceSession(onnx_path, providers=providers)
        self.input_name = self.session.get_inputs()[0].name
        # Warmup
        warm = np.zeros((1, IN_DIM), dtype=np.float32)
        self.session.run(None, {self.input_name: warm})

    def _build_input(self, x, y, z, organ_id, achieved_B, duty_sum):
        x = np.atleast_1d(np.asarray(x, dtype=np.float64))
        y = np.atleast_1d(np.asarray(y, dtype=np.float64))
        z = np.atleast_1d(np.asarray(z, dtype=np.float64))
        organ_id = np.atleast_1d(np.asarray(organ_id, dtype=np.float32))
        achieved_B = np.atleast_1d(np.asarray(achieved_B, dtype=np.float64))
        duty_sum = np.atleast_1d(np.asarray(duty_sum, dtype=np.float64))

        if not np.all(np.isin(organ_id.astype(int), ORGAN_IDS)):
            raise ValueError(f"organ_id gecersiz; gecerli: {ORGAN_IDS}")

        coords_sc = self.sx.transform(
            np.column_stack([x, y, z]).astype(np.float32)).astype(np.float32)
        extras_sc = self.se.transform(
            np.column_stack([achieved_B, duty_sum]).astype(np.float32)).astype(np.float32)
        organ_raw = organ_id.reshape(-1, 1).astype(np.float32)
        return np.hstack([coords_sc, organ_raw, extras_sc]).astype(np.float32)

    def _unscale(self, y_sc):
        y_orig = self.sy.inverse_transform(y_sc)
        D = np.clip(y_orig[:, :7], 0.0, 1.0)
        sin_p = y_orig[:, 7:14]
        cos_p = y_orig[:, 14:21]
        P_deg = (np.rad2deg(np.arctan2(sin_p, cos_p)) % 360.0).astype(np.float64)
        # Gauge fix: P1 = 0 referans (Mert tarzi)
        P_deg = (P_deg - P_deg[:, 0:1]) % 360.0
        E_h = y_orig[:, 21]
        E_c = y_orig[:, 22]
        return D, P_deg, E_h, E_c

    def _run_onnx(self, X_sc: np.ndarray) -> np.ndarray:
        """Forward + shape repair.

        skl2onnx bazi multi-output regressorler (ornegin BaggingRegressor) icin
        cikisi (N*OUT, 1) seklinde flatten edebilir. Asagidaki reshape hem dogru
        shape'i hem de zaten (N, OUT) gelen ONNX cikislarini etkilemez.
        """
        y_sc = self.session.run(None, {self.input_name: X_sc})[0]
        n = X_sc.shape[0]
        # Eger toplam eleman sayisi (N, 23) ile uyumlu, fakat ilk eksen N degilse reshape:
        if y_sc.size == n * 23 and y_sc.shape != (n, 23):
            y_sc = y_sc.reshape(n, 23)
        return y_sc

    def predict(self, x, y, z, organ_id, achieved_B, duty_sum):
        """Tek nokta -> dict (skalar degerler)."""
        X_sc = self._build_input(x, y, z, organ_id, achieved_B, duty_sum)
        y_sc = self._run_onnx(X_sc)
        D, P_deg, E_h, E_c = self._unscale(y_sc)
        out = {}
        for i, col in enumerate(D_COLS):
            out[col] = float(D[0, i])
        for i, col in enumerate(P_COLS):
            out[col] = float(P_deg[0, i])
        out["result_E_healthy"] = float(E_h[0])
        out["result_E_cancer"] = float(E_c[0])
        out["result_E_avg"] = float(0.5 * (E_h[0] + E_c[0]))
        return out

    def predict_batch(self, df: pd.DataFrame) -> pd.DataFrame:
        """DataFrame batch -> DataFrame (giris kolonlari + tahmin kolonlari)."""
        X_sc = self._build_input(df["x"].values, df["y"].values, df["z"].values,
                                   df["organ_id"].values, df["achieved_B"].values,
                                   df["duty_sum"].values)
        y_sc = self._run_onnx(X_sc)
        D, P_deg, E_h, E_c = self._unscale(y_sc)
        result = df[["x", "y", "z", "organ_id", "achieved_B", "duty_sum"]].copy()
        for i, col in enumerate(D_COLS):
            result[col] = D[:, i]
        for i, col in enumerate(P_COLS):
            result[col] = P_deg[:, i]
        result["result_E_healthy"] = E_h
        result["result_E_cancer"] = E_c
        result["result_E_avg"] = 0.5 * (E_h + E_c)
        return result


# ── XAI (Faz 1.2, 2026-08-26) — TEK-KAYNAK ai_hub.xai_tabular.em_runtime ─────
# ⚠️ ref-stats organ_id std'si 0.5 OVERRIDE'lı: eğitim CSV'sinde organ_id sabit 0
# (kanser bilgisi ayrı kolonda) — CSV'den ölçülseydi std=0 dejenerasyonu olurdu.
XAI_OUTPUT_LABELS = (D_COLS + [f"sinP{i}" for i in range(1, 8)]
                     + [f"cosP{i}" for i in range(1, 8)] + ["E_healthy", "E_cancer"])


def xai_ref_stats():
    """Eğitim-dağılımı referansları (std+background) — tek-örnek XAI için ZORUNLU."""
    from ai_hub.xai_tabular.em_runtime import load_ref_stats

    return load_ref_stats(_DIR)


def xai_hizli_sensitivity(predictor, x_mm: float, y_mm: float, z_mm: float,
                          organ_id: float, achieved_B: float = 0.0,
                          duty_sum: float = 0.0, top_n: int = 3) -> list[dict]:
    """Canli hafif duyarlilik (7+1 forward; PNG/SHAP yok) — em_kedi paritesi
    (xai plani §KALAN A5). Girdi semasi EM_FEATURES ile birebir (olculdu:
    predict(x, y, z, organ_id, achieved_B, duty_sum) ayni 6'li).
    Doner: [{"feature", "etki"}...] |delta| azalan; hata cagiranin zarif dususune."""
    from ai_hub.xai_tabular.em_runtime import hizli_sensitivity

    return hizli_sensitivity(predictor, xai_ref_stats(), float(x_mm), float(y_mm),
                             float(z_mm), float(organ_id), float(achieved_B or 0.0),
                             float(duty_sum or 0.0), top_n=top_n)


def _run_xai_em(predictor, X, out_dir, **kw):
    """Mod-2 batch XAI paketi (sensitivity+SHAP+CSV+PNG) — ref_stats'la dejenerasyonsuz."""
    from ai_hub.xai_tabular.em_runtime import batch_xai

    kw.setdefault("output_labels", XAI_OUTPUT_LABELS)
    return batch_xai(predictor, xai_ref_stats(), X, out_dir, **kw)


def main():
    parser = argparse.ArgumentParser(description=f"Petri Inference ({MODEL_NAME})")
    parser.add_argument("--x", type=float)
    parser.add_argument("--y", type=float)
    parser.add_argument("--z", type=float)
    parser.add_argument("--organ_id", type=int, default=0, choices=ORGAN_IDS)
    parser.add_argument("--achieved_B", type=float, default=0.001)
    parser.add_argument("--duty_sum", type=float, default=2.0)
    parser.add_argument("--csv", type=str, help="Input CSV (x,y,z,organ_id,achieved_B,duty_sum)")
    parser.add_argument("--output", type=str, default="predictions.csv")
    args = parser.parse_args()

    print(f"\nPetriPredictor ({MODEL_NAME}, Combined_R2=0.9849)")
    pred = PetriPredictor()

    if args.csv:
        df = pd.read_csv(args.csv)
        out_df = pred.predict_batch(df)
        out_df.to_csv(args.output, index=False)
        print(f"  -> {args.output} ({len(out_df)} satir)")
    else:
        if None in (args.x, args.y, args.z):
            parser.error("--x, --y, --z gerekli (veya --csv).")
        out = pred.predict(args.x, args.y, args.z, args.organ_id,
                            args.achieved_B, args.duty_sum)
        for k, v in out.items():
            print(f"  {k:24s} = {v:.6f}")


if __name__ == "__main__":
    main()
