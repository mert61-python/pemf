#!/usr/bin/env python3
"""
analysis.py — Cat Sound Classification Post-Analysis
"""

import os, sys, time, warnings, json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns

warnings.filterwarnings("ignore")
plt.rcParams["figure.dpi"] = 100
plt.rcParams["savefig.dpi"] = 300
plt.rcParams["font.size"] = 11
plt.rcParams["font.family"] = "serif"
sns.set_style("whitegrid")

MODELS_DIR = "/home/user02/dr/models/models_cat_sound"
FIGURES_DIR = os.path.join(MODELS_DIR, "figures")
TABLES_DIR = os.path.join(MODELS_DIR, "tables")
os.makedirs(FIGURES_DIR, exist_ok=True)
os.makedirs(TABLES_DIR, exist_ok=True)

CSV_PATH = os.path.join(MODELS_DIR, "model_cat_sound_karsilastirma.csv")
_STATUS = []

def run_section(sid, name, outputs, func):
    print(f"\n{'='*60}\n[{sid}] {name}\n{'='*60}")
    if outputs and all(os.path.exists(p) for p in outputs):
        print(f"  SKIP"); _STATUS.append((sid, name, "SKIP")); return
    t0 = time.time()
    try:
        func(); print(f"  OK ({time.time()-t0:.1f}s)")
        _STATUS.append((sid, name, "OK"))
    except Exception as e:
        import traceback; print(f"  HATA: {str(e)[:200]}")
        traceback.print_exc(limit=3); _STATUS.append((sid, name, "FAIL"))

if not os.path.exists(CSV_PATH):
    print(f"HATA: {CSV_PATH} yok"); sys.exit(1)

df = pd.read_csv(CSV_PATH).sort_values("Accuracy", ascending=False).reset_index(drop=True)
print(f"Loaded: {len(df)} models")


def _s1_model_comparison():
    fig, ax = plt.subplots(figsize=(12, 7))
    colors = sns.color_palette("viridis", len(df))
    bars = ax.barh(df["Model"][::-1], df["Accuracy"][::-1], color=colors[::-1], edgecolor="black")
    ax.set_xlabel("Accuracy"); ax.set_title("Cat Sound — Model Comparison")
    for bar, val in zip(bars, df["Accuracy"][::-1]):
        ax.text(val + 0.002, bar.get_y() + bar.get_height()/2, f"{val:.3f}", va="center", fontsize=8)
    plt.tight_layout()
    plt.savefig(os.path.join(FIGURES_DIR, "fig01_model_comparison.png"), bbox_inches="tight")
    plt.savefig(os.path.join(FIGURES_DIR, "fig01_model_comparison.pdf"), bbox_inches="tight")
    plt.close()


def _s2_speed_accuracy():
    fig, ax = plt.subplots(figsize=(9, 6))
    colors = sns.color_palette("tab10", len(df))
    for i, (_, r) in enumerate(df.iterrows()):
        ax.scatter(r["Inference_ms"], r["Accuracy"], s=r["Params_M"]*30+50,
                   color=colors[i], edgecolor="black", zorder=5)
        ax.annotate(r["Model"], (r["Inference_ms"], r["Accuracy"]),
                    textcoords="offset points", xytext=(8, 4), fontsize=7)
    ax.set_xlabel("Inference (ms)"); ax.set_ylabel("Accuracy")
    ax.set_title("Speed vs Accuracy — Cat Sound"); ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(FIGURES_DIR, "fig02_speed_accuracy.png"), bbox_inches="tight")
    plt.savefig(os.path.join(FIGURES_DIR, "fig02_speed_accuracy.pdf"), bbox_inches="tight")
    plt.close()


def _s3_metrics_heatmap():
    metric_cols = [c for c in ["Accuracy", "Top3_Accuracy", "F1_macro", "AUC_ROC_macro",
                                "Cohen_Kappa", "MCC"] if c in df.columns]
    data = df.set_index("Model")[metric_cols].head(20)
    fig, ax = plt.subplots(figsize=(10, max(4, len(data)*0.35)))
    sns.heatmap(data, annot=True, fmt=".3f", cmap="RdYlGn", ax=ax, vmin=0, vmax=1)
    ax.set_title("Metrics Heatmap — Top-20"); plt.tight_layout()
    plt.savefig(os.path.join(FIGURES_DIR, "fig03_metrics_heatmap.png"), bbox_inches="tight")
    plt.savefig(os.path.join(FIGURES_DIR, "fig03_metrics_heatmap.pdf"), bbox_inches="tight")
    plt.close()


def _s4_params_vs_accuracy():
    fig, ax1 = plt.subplots(figsize=(12, 5))
    models = df["Model"].tolist()
    x = np.arange(len(models))
    ax1.bar(x, df["Params_M"], color="#90CAF9", edgecolor="black", alpha=0.8)
    ax1.set_ylabel("Params (M)"); ax1.set_xticks(x)
    ax1.set_xticklabels(models, rotation=45, ha="right", fontsize=8)
    ax2 = ax1.twinx()
    ax2.plot(x, df["Accuracy"], "o-", color="#E91E63", linewidth=2, markersize=6)
    ax2.set_ylabel("Accuracy"); ax2.set_ylim(0, 1)
    ax1.set_title("Params vs Accuracy"); plt.tight_layout()
    plt.savefig(os.path.join(FIGURES_DIR, "fig04_params_accuracy.png"), bbox_inches="tight")
    plt.savefig(os.path.join(FIGURES_DIR, "fig04_params_accuracy.pdf"), bbox_inches="tight")
    plt.close()


def _s5_latex():
    cols = [c for c in CSV_COLS if c in df.columns]
    lines = ["\\begin{table}[htbp]", "\\centering",
             "\\caption{Cat Sound Classification Results}",
             "\\label{tab:cat_sound}", "\\resizebox{\\textwidth}{!}{%",
             "\\begin{tabular}{l" + "c"*(len(cols)-1) + "}", "\\toprule",
             " & ".join(c.replace("_","\\_") for c in cols) + " \\\\", "\\midrule"]
    for _, r in df.iterrows():
        vals = []
        for c in cols:
            v = r.get(c, "")
            if isinstance(v, float): vals.append(f"{v:.4f}")
            else: vals.append(str(v).replace("_","\\_"))
        lines.append(" & ".join(vals) + " \\\\")
    lines += ["\\bottomrule", "\\end{tabular}%}", "\\end{table}"]
    with open(os.path.join(TABLES_DIR, "table1_results.tex"), "w") as f:
        f.write("\n".join(lines))

CSV_COLS = ["Model", "Accuracy", "Top3_Accuracy", "F1_macro", "AUC_ROC_macro",
            "Cohen_Kappa", "MCC", "Params_M", "Inference_ms"]

SECTIONS = [
    (1, "MODEL COMPARISON", [os.path.join(FIGURES_DIR, "fig01_model_comparison.png")], _s1_model_comparison),
    (2, "SPEED vs ACCURACY", [os.path.join(FIGURES_DIR, "fig02_speed_accuracy.png")], _s2_speed_accuracy),
    (3, "METRICS HEATMAP", [os.path.join(FIGURES_DIR, "fig03_metrics_heatmap.png")], _s3_metrics_heatmap),
    (4, "PARAMS vs ACCURACY", [os.path.join(FIGURES_DIR, "fig04_params_accuracy.png")], _s4_params_vs_accuracy),
    (5, "LATEX TABLE", [os.path.join(TABLES_DIR, "table1_results.tex")], _s5_latex),
]

for sid, name, outputs, func in SECTIONS:
    run_section(sid, name, outputs, func)

print(f"\n{'='*60}")
n_ok = sum(1 for _,_,s in _STATUS if s=="OK")
n_skip = sum(1 for _,_,s in _STATUS if s=="SKIP")
n_fail = sum(1 for _,_,s in _STATUS if s=="FAIL")
print(f"OK: {n_ok} | SKIP: {n_skip} | FAIL: {n_fail}")
for s in _STATUS: print(f"  [{s[2]:4s}] [{s[0]}] {s[1]}")
print(f"\nFigures: {FIGURES_DIR}\nTables: {TABLES_DIR}")
sys.exit(0 if n_fail == 0 else 1)
