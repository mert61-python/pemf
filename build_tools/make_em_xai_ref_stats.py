# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""make_em_xai_ref_stats.py — EM XAI referans istatistik varliklari (Faz 1.2, 2026-08-26).

NEDEN: EM sensitivity/SHAP tek-ornekte (canli AI Pro) DEJENERE — std ve background verilen
X'ten turetilirse N=1'de her sey ~0 cikar (ai_hub/xai_tabular/em_sensitivity.py bunu artik
ACIK ValueError ile reddediyor). Cozum: EGITIM DAGILIMI referanslari modul varligi olarak
paketlenir (xai_ref_stats.npz: std (6,) + background (M,6)).

KAYNAK DOGRULAMASI (2026-08-26 kesif ajani + bu betikteki capraz-kontrol): deployed
scaler_X.pkl / scaler_extra.pkl StandardScaler'lari egitim CSV'lerinin populasyon
istatistikleriyle birebir eslesti (mean/scale ~1e-3 tolerans; n_samples_seen ~= 0.8*satir).
ref_std dogrudan scaler.scale_'den gelir (x,y,z + achieved_B,duty_sum); organ_id HAM gecer
(hicbir scaler'da yok) -> CSV'den olculur. ⚠️ PETRI TUZAGI: training CSV'sinde organ_id
SABIT 0 (kanser bilgisi ayri kolonda tasinmis) -> std=0 dejenerasyonu; ORGAN_IDS={0,1}
Bernoulli(0.5) std'si (0.5) ELLE gecilir ve background organ_id {0,1} yeniden ornekleme.

CALISTIRMA (yalniz bu makinede; training_archive gerekir):
    python build_tools/make_em_xai_ref_stats.py
Cikti: ai_hub/<modul>/xai_ref_stats.npz (kucuk, deterministik seed=0) — repo'ya commit'lenir,
frozen build'e ai_hub datas'iyla otomatik girer.
"""

from __future__ import annotations

import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

KOK = Path(__file__).resolve().parents[1]
ARSIV = KOK / "training_archive"
KOLONLAR = ["x", "y", "z", "organ_id", "achieved_B", "duty_sum"]
M_BACKGROUND = 64

MODELLER = [
    {
        "ad": "em_kedi",
        "ai_hub": KOK / "ai_hub" / "em_kedi",
        "csv": ARSIV / "em_kedi" / "training_data_kedi_v5.csv",
        "organ_std_override": None,  # CSV'den (0-6, 7 organ)
        "organ_degerleri": None,
    },
    {
        "ad": "em_fantom",
        "ai_hub": KOK / "ai_hub" / "inference_em_fantom",
        "csv": ARSIV / "em_phantom" / "training_data_phantom_v7.csv",
        "organ_std_override": None,  # CSV'den (0/1 dengeli -> ~0.5)
        "organ_degerleri": None,
    },
    {
        "ad": "em_petri",
        "ai_hub": KOK / "ai_hub" / "inference_em_petri",
        "csv": ARSIV / "em_petri" / "training_data_petri_v5.csv",
        # ⚠️ CSV'de organ_id sabit 0 (std=0 dejenerasyonu) — deploy ORGAN_IDS=[0,1]:
        "organ_std_override": 0.5,
        "organ_degerleri": np.array([0.0, 1.0]),
    },
]


def uret(m: dict) -> Path:
    sx = joblib.load(m["ai_hub"] / "scaler_X.pkl")
    se = joblib.load(m["ai_hub"] / "scaler_extra.pkl")
    df = pd.read_csv(m["csv"], usecols=KOLONLAR)[KOLONLAR]
    X = df.to_numpy(dtype=np.float64)

    # Capraz-kontrol: CSV populasyonu ile deployed scaler ayni dagilimdan mi?
    # (yanlis CSV eslesmesi sessizce sacma referans uretmesin — %2 tolerans)
    csv_std_xyz = X[:, :3].std(axis=0)
    csv_std_ext = X[:, 4:6].std(axis=0)
    if not (np.allclose(csv_std_xyz, sx.scale_, rtol=0.02) and np.allclose(csv_std_ext, se.scale_, rtol=0.02)):
        raise SystemExit(
            f"{m['ad']}: CSV std ile scaler.scale_ UYUSMUYOR — yanlis egitim CSV'si?\n"
            f"  xyz csv={csv_std_xyz} scaler={sx.scale_}\n  ext csv={csv_std_ext} scaler={se.scale_}"
        )

    organ_std = float(X[:, 3].std()) if m["organ_std_override"] is None else float(m["organ_std_override"])
    if organ_std <= 0:
        raise SystemExit(f"{m['ad']}: organ_id std=0 (dejenerasyon) — override gerekli")
    std = np.array(
        [sx.scale_[0], sx.scale_[1], sx.scale_[2], organ_std, se.scale_[0], se.scale_[1]],
        dtype=np.float64,
    )

    rng = np.random.default_rng(0)  # deterministik varlik (yeniden uretim ayni npz)
    idx = rng.choice(len(X), size=M_BACKGROUND, replace=False)
    bg = X[idx].astype(np.float64)
    if m["organ_degerleri"] is not None:  # petri: sabit-0 kolonu {0,1} ile canlandir
        bg[:, 3] = rng.choice(m["organ_degerleri"], size=M_BACKGROUND)

    hedef = m["ai_hub"] / "xai_ref_stats.npz"
    np.savez_compressed(
        hedef,
        std=std,
        background=bg,
        feature_names=np.array(KOLONLAR),
        source=np.array([m["csv"].name]),
        n_source_rows=np.array([len(X)]),
        created=np.array(["2026-08-26"]),
    )
    print(f"  {m['ad']:10s} -> {hedef.name}  std={np.array2string(std, precision=4)}  bg={bg.shape}")
    return hedef


def main() -> int:
    print("EM XAI referans istatistikleri uretiliyor (seed=0, deterministik):")
    for m in MODELLER:
        uret(m)
    print("TAMAM — ai_hub/<modul>/xai_ref_stats.npz dosyalarini commit'leyin.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
