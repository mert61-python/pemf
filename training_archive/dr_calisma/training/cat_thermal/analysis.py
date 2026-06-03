#!/usr/bin/env python3
"""
analysis.py — Cat Thermal Classification Post-Analysis
=======================================================
training.py sonrası çalıştır.
"""

import os
import sys
import time
import json
import warnings
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.metrics import confusion_matrix, roc_curve, auc
import joblib

warnings.filterwarnings("ignore")
plt.rcParams["figure.dpi"] = 100
plt.rcParams["savefig.dpi"] = 300
plt.rcParams["font.size"] = 11
plt.rcParams["font.family"] = "serif"
sns.set_style("whitegrid")

MODELS_DIR = "/home/user02/dr/models/models_cat_thermal"
FIGURES_DIR = os.path.join(MODELS_DIR, "figures")
TABLES_DIR = os.path.join(MODELS_DIR, "tables")
os.makedirs(FIGURES_DIR, exist_ok=True)
os.makedirs(TABLES_DIR, exist_ok=True)

CSV_PATH = os.path.join(MODELS_DIR, "model_cat_thermal_karsilastirma.csv")

_STATUS = []


def run_section(sid, name, outputs, func):
    print(f"\n{'='*60}\n[{sid}] {name}\n{'='*60}")
    if outputs and all(os.path.exists(p) for p in outputs):
        print(f"  SKIP (mevcut)")
        _STATUS.append((sid, name, "SKIP"))
        return
    t0 = time.time()
    try:
        func()
        print(f"  OK ({time.time()-t0:.1f}s)")
        _STATUS.append((sid, name, "OK"))
    except Exception as e:
        import traceback
        print(f"  HATA: {str(e)[:200]}")
        traceback.print_exc(limit=3)
        _STATUS.append((sid, name, "FAIL"))


# ============================================================
# LOAD
# ============================================================
if not os.path.exists(CSV_PATH):
    print(f"HATA: {CSV_PATH} yok")
    sys.exit(1)

df = pd.read_csv(CSV_PATH)
df = df.sort_values("AUC_ROC", ascending=False).reset_index(drop=True)
print(f"Loaded: {len(df)} models")
BEST = df.iloc[0]["Model"] if len(df) else None


# ============================================================
# 1. MODEL COMPARISON BAR CHART
# ============================================================
def _s1_comparison():
    fig, ax = plt.subplots(figsize=(12, max(5, len(df) * 0.4)))
    colors = sns.color_palette("viridis", len(df))
    models = df["Model"].tolist()[::-1]
    aucs = df["AUC_ROC"].tolist()[::-1]
    bars = ax.barh(models, aucs, color=colors[::-1], edgecolor="black")
    for bar, val in zip(bars, aucs):
        ax.text(val + 0.005, bar.get_y() + bar.get_height()/2,
                f"{val:.3f}", va="center", fontsize=9)
    ax.set_xlabel("AUC-ROC")
    ax.set_title("Cat Thermal — Model Comparison (AUC-ROC)")
    ax.set_xlim(0, 1)
    plt.tight_layout()
    plt.savefig(os.path.join(FIGURES_DIR, "fig01_model_comparison.png"), bbox_inches="tight")
    plt.savefig(os.path.join(FIGURES_DIR, "fig01_model_comparison.pdf"), bbox_inches="tight")
    plt.close()


# ============================================================
# 2. MULTI-METRIC GROUPED BAR
# ============================================================
def _s2_multi_metric():
    top10 = df.head(min(10, len(df)))
    models = [m[:15] for m in top10["Model"]]
    x = np.arange(len(models))
    w = 0.15

    fig, ax = plt.subplots(figsize=(14, 6))
    metrics = [("Accuracy", "#2196F3"), ("F1", "#4CAF50"), ("AUC_ROC", "#FF9800"),
               ("Sensitivity", "#E91E63"), ("Specificity", "#9C27B0")]
    for i, (m, c) in enumerate(metrics):
        vals = top10[m].tolist()
        ax.bar(x + i * w, vals, w, label=m, color=c, edgecolor="black")

    ax.set_xticks(x + w * 2)
    ax.set_xticklabels(models, rotation=30, ha="right")
    ax.set_ylabel("Score")
    ax.set_ylim(0, 1.1)
    ax.set_title("Top Models — Multi-Metric Comparison")
    ax.legend(loc="upper right", fontsize=9)
    ax.grid(True, alpha=0.3, axis="y")
    plt.tight_layout()
    plt.savefig(os.path.join(FIGURES_DIR, "fig02_multi_metric.png"), bbox_inches="tight")
    plt.savefig(os.path.join(FIGURES_DIR, "fig02_multi_metric.pdf"), bbox_inches="tight")
    plt.close()


# ============================================================
# 3. SENSITIVITY vs SPECIFICITY SCATTER
# ============================================================
def _s3_sens_spec():
    fig, ax = plt.subplots(figsize=(8, 8))
    colors = sns.color_palette("tab20", len(df))
    for i, (_, r) in enumerate(df.iterrows()):
        ax.scatter(r["Specificity"], r["Sensitivity"], s=100,
                   color=colors[i], edgecolor="black", zorder=5)
        ax.annotate(r["Model"][:12], (r["Specificity"], r["Sensitivity"]),
                    textcoords="offset points", xytext=(5, 5), fontsize=8)
    ax.plot([0, 1], [0, 1], "k--", alpha=0.3)
    ax.set_xlabel("Specificity (Healthy doğru)")
    ax.set_ylabel("Sensitivity (Sick doğru)")
    ax.set_title("Sensitivity vs Specificity Tradeoff")
    ax.set_xlim(0, 1.05)
    ax.set_ylim(0, 1.05)
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(FIGURES_DIR, "fig03_sens_spec.png"), bbox_inches="tight")
    plt.savefig(os.path.join(FIGURES_DIR, "fig03_sens_spec.pdf"), bbox_inches="tight")
    plt.close()


# ============================================================
# 4. PARAMS vs AUC SCATTER
# ============================================================
def _s4_params_auc():
    fig, ax = plt.subplots(figsize=(10, 6))
    colors = sns.color_palette("viridis", len(df))
    for i, (_, r) in enumerate(df.iterrows()):
        ax.scatter(r["Params_M"], r["AUC_ROC"], s=120,
                   color=colors[i], edgecolor="black", zorder=5)
        ax.annotate(r["Model"][:12], (r["Params_M"], r["AUC_ROC"]),
                    textcoords="offset points", xytext=(5, 5), fontsize=8)
    ax.set_xlabel("Parameters (M)")
    ax.set_ylabel("AUC-ROC")
    ax.set_title("Model Size vs Performance")
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(FIGURES_DIR, "fig04_params_auc.png"), bbox_inches="tight")
    plt.savefig(os.path.join(FIGURES_DIR, "fig04_params_auc.pdf"), bbox_inches="tight")
    plt.close()


# ============================================================
# 5. RADAR CHART (top-5)
# ============================================================
def _s5_radar():
    categories = ["Accuracy", "F1", "AUC_ROC", "Sensitivity", "Specificity", "MCC"]
    N = len(categories)
    angles = np.linspace(0, 2 * np.pi, N, endpoint=False).tolist()
    angles += angles[:1]

    fig, ax = plt.subplots(figsize=(8, 8), subplot_kw=dict(polar=True))
    colors = sns.color_palette("Set2", min(5, len(df)))
    top5 = df.head(min(5, len(df)))

    for i, (_, r) in enumerate(top5.iterrows()):
        values = [max(0, r[c]) for c in categories]
        values += values[:1]
        label = r["Model"][:15]
        ax.plot(angles, values, "o-", linewidth=2, label=label, color=colors[i])
        ax.fill(angles, values, alpha=0.1, color=colors[i])

    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(categories, fontsize=10)
    ax.set_ylim(0, 1)
    ax.set_title("Top-5 Models — Performance Radar", pad=20)
    ax.legend(loc="upper right", bbox_to_anchor=(1.3, 1.1), fontsize=9)
    plt.tight_layout()
    plt.savefig(os.path.join(FIGURES_DIR, "fig05_radar.png"), bbox_inches="tight")
    plt.savefig(os.path.join(FIGURES_DIR, "fig05_radar.pdf"), bbox_inches="tight")
    plt.close()


# ============================================================
# 6. BRIER SCORE COMPARISON
# ============================================================
def _s6_brier():
    fig, ax = plt.subplots(figsize=(10, max(4, len(df) * 0.35)))
    sorted_df = df.sort_values("Brier_Score", ascending=True)
    colors = ["#4CAF50" if b < 0.25 else "#FF9800" if b < 0.35 else "#F44336"
              for b in sorted_df["Brier_Score"]]
    ax.barh(sorted_df["Model"], sorted_df["Brier_Score"], color=colors, edgecolor="black")
    ax.axvline(x=0.25, color="green", linestyle="--", alpha=0.5, label="Good (<0.25)")
    ax.set_xlabel("Brier Score (lower = better calibrated)")
    ax.set_title("Model Calibration — Brier Score")
    ax.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(FIGURES_DIR, "fig06_brier.png"), bbox_inches="tight")
    plt.savefig(os.path.join(FIGURES_DIR, "fig06_brier.pdf"), bbox_inches="tight")
    plt.close()


# ============================================================
# 7. TRAINING TIME vs PERFORMANCE
# ============================================================
def _s7_time_perf():
    fig, ax = plt.subplots(figsize=(10, 6))
    colors = sns.color_palette("tab20", len(df))
    for i, (_, r) in enumerate(df.iterrows()):
        ax.scatter(r["Train_Time_s"], r["AUC_ROC"], s=r["Params_M"] * 30,
                   color=colors[i], edgecolor="black", alpha=0.8)
        ax.annotate(r["Model"][:12], (r["Train_Time_s"], r["AUC_ROC"]),
                    textcoords="offset points", xytext=(5, 3), fontsize=8)
    ax.set_xlabel("Training Time (s)")
    ax.set_ylabel("AUC-ROC")
    ax.set_title("Training Efficiency — Time vs Performance (bubble=params)")
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(FIGURES_DIR, "fig07_time_perf.png"), bbox_inches="tight")
    plt.savefig(os.path.join(FIGURES_DIR, "fig07_time_perf.pdf"), bbox_inches="tight")
    plt.close()


# ============================================================
# 8. YOUDEN's J INDEX
# ============================================================
def _s8_youden():
    fig, ax = plt.subplots(figsize=(10, max(4, len(df) * 0.35)))
    sorted_df = df.sort_values("Youden_J", ascending=True)
    colors = ["#4CAF50" if j > 0.3 else "#FF9800" if j > 0.1 else "#F44336"
              for j in sorted_df["Youden_J"]]
    ax.barh(sorted_df["Model"], sorted_df["Youden_J"], color=colors, edgecolor="black")
    ax.axvline(x=0, color="red", linestyle="--", alpha=0.5)
    ax.set_xlabel("Youden's J (Sensitivity + Specificity - 1)")
    ax.set_title("Diagnostic Utility — Youden's J Index")
    plt.tight_layout()
    plt.savefig(os.path.join(FIGURES_DIR, "fig08_youden.png"), bbox_inches="tight")
    plt.savefig(os.path.join(FIGURES_DIR, "fig08_youden.pdf"), bbox_inches="tight")
    plt.close()


# ============================================================
# 9. LATEX TABLE
# ============================================================
def _s9_latex():
    lines = [
        "\\begin{table}[htbp]", "\\centering",
        "\\caption{Cat Thermal Classification — Model Comparison}",
        "\\label{tab:cat_thermal}",
        "\\resizebox{\\textwidth}{!}{%",
        "\\begin{tabular}{lccccccccc}", "\\toprule",
        "Model & Acc & F1 & AUC-ROC & AUC-PR & Sens & Spec & MCC & Brier & Params \\\\",
        "\\midrule",
    ]
    for _, r in df.iterrows():
        nm = r["Model"].replace("_", "\\_")
        lines.append(
            f"{nm} & {r['Accuracy']:.3f} & {r['F1']:.3f} & {r['AUC_ROC']:.3f} & "
            f"{r['AUC_PR']:.3f} & {r['Sensitivity']:.3f} & {r['Specificity']:.3f} & "
            f"{r['MCC']:.3f} & {r['Brier_Score']:.3f} & {r['Params_M']}M \\\\")
    lines += ["\\bottomrule", "\\end{tabular}%", "}", "\\end{table}"]

    with open(os.path.join(TABLES_DIR, "table1_results.tex"), "w") as f:
        f.write("\n".join(lines))
    print(f"  -> table1_results.tex")


# ============================================================
# 10. COMPARISON PNG (thermal image)
# ============================================================
def _s10_thermal_comparison():
    """Create comparison image showing model rankings."""
    fig, ax = plt.subplots(figsize=(12, 6))

    models = df["Model"].tolist()
    x = np.arange(len(models))

    ax.bar(x - 0.2, df["Sensitivity"], 0.4, label="Sensitivity (Sick detect)",
           color="#E91E63", edgecolor="black", alpha=0.8)
    ax.bar(x + 0.2, df["Specificity"], 0.4, label="Specificity (Healthy detect)",
           color="#2196F3", edgecolor="black", alpha=0.8)

    ax.set_xticks(x)
    ax.set_xticklabels([m[:12] for m in models], rotation=45, ha="right")
    ax.set_ylabel("Score")
    ax.set_title("Sensitivity vs Specificity per Model")
    ax.legend()
    ax.set_ylim(0, 1.1)
    ax.grid(True, alpha=0.3, axis="y")
    plt.tight_layout()
    plt.savefig(os.path.join(FIGURES_DIR, "fig10_sens_vs_spec_bar.png"), bbox_inches="tight")
    plt.savefig(os.path.join(FIGURES_DIR, "fig10_sens_vs_spec_bar.pdf"), bbox_inches="tight")
    plt.close()


# ============================================================
# MAIN RUNNER
# ============================================================
SECTIONS = [
    (1, "MODEL COMPARISON (AUC-ROC)",
     [os.path.join(FIGURES_DIR, "fig01_model_comparison.png")], _s1_comparison),
    (2, "MULTI-METRIC GROUPED BAR",
     [os.path.join(FIGURES_DIR, "fig02_multi_metric.png")], _s2_multi_metric),
    (3, "SENSITIVITY vs SPECIFICITY",
     [os.path.join(FIGURES_DIR, "fig03_sens_spec.png")], _s3_sens_spec),
    (4, "PARAMS vs AUC",
     [os.path.join(FIGURES_DIR, "fig04_params_auc.png")], _s4_params_auc),
    (5, "RADAR CHART (top-5)",
     [os.path.join(FIGURES_DIR, "fig05_radar.png")], _s5_radar),
    (6, "BRIER SCORE",
     [os.path.join(FIGURES_DIR, "fig06_brier.png")], _s6_brier),
    (7, "TRAINING TIME vs PERFORMANCE",
     [os.path.join(FIGURES_DIR, "fig07_time_perf.png")], _s7_time_perf),
    (8, "YOUDEN's J INDEX",
     [os.path.join(FIGURES_DIR, "fig08_youden.png")], _s8_youden),
    (9, "LATEX TABLE",
     [os.path.join(TABLES_DIR, "table1_results.tex")], _s9_latex),
    (10, "SENSITIVITY vs SPECIFICITY BAR",
     [os.path.join(FIGURES_DIR, "fig10_sens_vs_spec_bar.png")], _s10_thermal_comparison),
]

for sid, name, outputs, func in SECTIONS:
    run_section(sid, name, outputs, func)

print(f"\n{'='*60}")
n_ok = sum(1 for _, _, s in _STATUS if s == "OK")
n_skip = sum(1 for _, _, s in _STATUS if s == "SKIP")
n_fail = sum(1 for _, _, s in _STATUS if s == "FAIL")
print(f"Basarili: {n_ok} | Atlanan: {n_skip} | Basarisiz: {n_fail}")
for sid, nm, st in _STATUS:
    print(f"  [{st:4s}] [{sid:2d}] {nm}")
print(f"\nFigurler: {FIGURES_DIR}")
print(f"Tablolar: {TABLES_DIR}")
print("=" * 60)

sys.exit(0 if n_fail == 0 else 1)
