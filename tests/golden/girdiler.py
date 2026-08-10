# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""ALTIN DEĞER GİRDİLERİ — tek kaynak.

Hem `tests/test_ai_golden_values.py` (doğrulama) hem `olc_altin_degerler.py` (yeniden ölçüm)
buradan okur. İkisi ayrı kopya tutarsa "ölçtüğüm girdi ile test ettiğim girdi farklı" sınıfı
sessiz bir yanlış-güvence doğar.
"""

# ── CKD (UCI-CKD, 24 klinik alan) ───────────────────────────────────────────
CKD_HASTA = {
    "age": 48,
    "bp": 80,
    "sg": 1.020,
    "al": 1,
    "su": 0,
    "rbc": "normal",
    "pc": "normal",
    "pcc": "notpresent",
    "ba": "notpresent",
    "bgr": 121,
    "bu": 36,
    "sc": 1.2,
    "sod": 137,
    "pot": 4.4,
    "hemo": 15.4,
    "pcv": 44,
    "wc": 7800,
    "rc": 5.2,
    "htn": "yes",
    "dm": "yes",
    "cad": "no",
    "appet": "good",
    "pe": "no",
    "ane": "no",
}
CKD_SAGLIKLI = {
    "age": 40,
    "bp": 70,
    "sg": 1.025,
    "al": 0,
    "su": 0,
    "rbc": "normal",
    "pc": "normal",
    "pcc": "notpresent",
    "ba": "notpresent",
    "bgr": 95,
    "bu": 25,
    "sc": 0.9,
    "sod": 140,
    "pot": 4.2,
    "hemo": 15.0,
    "pcv": 46,
    "wc": 7000,
    "rc": 5.0,
    "htn": "no",
    "dm": "no",
    "cad": "no",
    "appet": "good",
    "pe": "no",
    "ane": "no",
}
# EKSİK ALAN: SimpleImputer + ColumnTransformer yolunu zorlar — ölçekleme sapmasının en çok
# ısırdığı yer burasıdır (impute edilen değer ölçeklenir).
CKD_EKSIK = dict(CKD_HASTA, sod=None, rc=None, rbc=None)

# ── EM tahmincileri (x, y, z, organ_id, achieved_B, duty_sum) ───────────────
EM_ORTA = dict(x=0.0, y=0.0, z=0.05, organ_id=1, achieved_B=0.001, duty_sum=2.0)
EM_KOSE = dict(x=0.08, y=-0.06, z=0.12, organ_id=0, achieved_B=0.0025, duty_sum=3.5)

# ── RNA ─────────────────────────────────────────────────────────────────────
# Uç nokta `pd.read_csv(..., index_col=0)` kullanır; ölçüm de aynısını kullanmalı.
RNA_CSV = "ai_hub/PEMF_AI_Test_Girdileri/11_BobrekRNA.csv"
