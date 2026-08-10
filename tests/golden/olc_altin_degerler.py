# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""ALTIN DEĞERLERİ YENİDEN ÖLÇ (yalnız BİLİNÇLİ model değişikliğinde çalıştırın).

    python tests/golden/olc_altin_degerler.py > tests/golden/ai_golden_values.json

⚠️ Bu script'i "test kırıldı, kolay yoldan geçireyim" diye çalıştırmak, testin var oluş
amacını yok eder: dosya, sayıların KAYMADIĞININ kanıtıdır. Kırılma önce AÇIKLANMALIDIR.
"""

import json
import os
import platform
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(KOK / "tests"))
os.chdir(KOK)

import numpy as np  # noqa: E402

from golden import girdiler as G  # noqa: E402
from golden import yukleyici as Y  # noqa: E402


def _sadelestir(o):
    if isinstance(o, dict):
        return {k: _sadelestir(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_sadelestir(v) for v in o]
    if isinstance(o, np.ndarray):
        return _sadelestir(o.tolist())
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, (np.floating, float)):
        return round(float(o), 10)
    return o


def olc() -> dict:
    import sklearn
    import xgboost

    sonuc = {
        "_aciklama": "ALTIN DEGERLER — sabit girdi -> beklenen cikti. 2026-08-09 denetimi Tier 3.",
        "_neden": (
            "Uretim on-isleyicileri sklearn 1.8.0 ile serilestirilmis, runtime 1.7.2 sabitli. "
            "sklearn her yuklemede 'may lead to INVALID RESULTS' diyor. Bu dosya, sayilarin "
            "gercekten kaymadiginin tek kaniti."
        ),
        "_yeniden_olcum": (
            "python tests/golden/olc_altin_degerler.py > tests/golden/ai_golden_values.json  "
            "(SADECE bilincli model degisikliginde)"
        ),
        "_olcum_ortami": {
            "sklearn": sklearn.__version__,
            "xgboost": xgboost.__version__,
            "numpy": np.__version__,
            "python": platform.python_version(),
            "platform": sys.platform,
        },
    }

    ckd = Y.ckd_modulu()
    sonuc["ckd"] = {
        "hasta": ckd.predict_one(G.CKD_HASTA),
        "saglikli": ckd.predict_one(G.CKD_SAGLIKLI),
        "eksik": ckd.predict_one(G.CKD_EKSIK),
    }

    for ad in sorted(Y.EM_TAHMINCILER):
        p = Y.em_tahminci(ad)
        sonuc[ad] = {"orta": p.predict(**G.EM_ORTA), "kose": p.predict(**G.EM_KOSE)}

    import pandas as pd

    df = pd.read_csv(KOK / G.RNA_CSV, index_col=0)
    sonuc["rna"] = {"csv": Y.rna_tahminci().predict(df)}

    return sonuc


if __name__ == "__main__":
    print(json.dumps(_sadelestir(olc()), indent=2, ensure_ascii=False, default=str))
