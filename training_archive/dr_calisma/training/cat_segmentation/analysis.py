#!/usr/bin/env python3
"""
analysis_cat_segmentation.py — YOLO26 Segmentation Post-Analysis
================================================================
Figures + tables for SCI paper.
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
from glob import glob

warnings.filterwarnings("ignore")
plt.rcParams["figure.dpi"] = 100
plt.rcParams["savefig.dpi"] = 300
plt.rcParams["font.size"] = 11
plt.rcParams["font.family"] = "serif"
sns.set_style("whitegrid")

MODELS_DIR = "/home/user02/dr/models_cat_segmentation"
FIGURES_DIR = os.path.join(MODELS_DIR, "figures")
TABLES_DIR = os.path.join(MODELS_DIR, "tables")
os.makedirs(FIGURES_DIR, exist_ok=True)
os.makedirs(TABLES_DIR, exist_ok=True)

CSV_PATH = os.path.join(MODELS_DIR, "model_cat_seg_karsilastirma.csv")

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
        _STATUS.append((sid, name, f"FAIL"))


# ============================================================
# LOAD DATA
# ============================================================
if not os.path.exists(CSV_PATH):
    print(f"HATA: {CSV_PATH} yok. Once training calistir.")
    sys.exit(1)

df = pd.read_csv(CSV_PATH)
df = df.sort_values("mAP50_95_mask", ascending=False).reset_index(drop=True)
print(f"Loaded: {len(df)} models")
BEST = df.iloc[0]["Model"] if len(df) else None


# ============================================================
# SECTIONS
# ============================================================

def _s1_model_comparison():
    """Bar chart: 5 models, mAP50 and mAP50-95 for box and mask."""
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    models = df["Model"].tolist()
    x = np.arange(len(models))
    w = 0.35

    # Box
    ax = axes[0]
    ax.bar(x - w/2, df["mAP50_box"], w, label="mAP50", color="#2196F3", edgecolor="black")
    ax.bar(x + w/2, df["mAP50_95_box"], w, label="mAP50-95", color="#FF9800", edgecolor="black")
    ax.set_xticks(x)
    ax.set_xticklabels([m.replace("yolo26","Y26-").replace("-seg","") for m in models], rotation=15)
    ax.set_ylabel("Score")
    ax.set_title("Box Detection")
    ax.legend()
    ax.set_ylim(0, 1)
    for i, v in enumerate(df["mAP50_95_box"]):
        ax.text(i + w/2, v + 0.02, f"{v:.3f}", ha="center", fontsize=9)

    # Mask
    ax = axes[1]
    ax.bar(x - w/2, df["mAP50_mask"], w, label="mAP50", color="#4CAF50", edgecolor="black")
    ax.bar(x + w/2, df["mAP50_95_mask"], w, label="mAP50-95", color="#E91E63", edgecolor="black")
    ax.set_xticks(x)
    ax.set_xticklabels([m.replace("yolo26","Y26-").replace("-seg","") for m in models], rotation=15)
    ax.set_title("Mask Segmentation")
    ax.legend()
    ax.set_ylim(0, 1)
    for i, v in enumerate(df["mAP50_95_mask"]):
        ax.text(i + w/2, v + 0.02, f"{v:.3f}", ha="center", fontsize=9)

    plt.suptitle("YOLO26 Model Comparison — Box vs Mask Performance", fontsize=14, y=1.02)
    plt.tight_layout()
    plt.savefig(os.path.join(FIGURES_DIR, "fig01_model_comparison.png"), bbox_inches="tight")
    plt.savefig(os.path.join(FIGURES_DIR, "fig01_model_comparison.pdf"), bbox_inches="tight")
    plt.close()


def _s2_speed_accuracy():
    """Scatter: inference time vs mAP50-95 mask, bubble size = params."""
    fig, ax = plt.subplots(figsize=(9, 6))
    colors = sns.color_palette("viridis", len(df))
    for i, (_, r) in enumerate(df.iterrows()):
        ax.scatter(r["Inference_ms"], r["mAP50_95_mask"],
                   s=r["Params_M"] * 20, color=colors[i], edgecolor="black",
                   zorder=5, alpha=0.8)
        ax.annotate(r["Model"].replace("yolo26","Y26-").replace("-seg",""),
                     (r["Inference_ms"], r["mAP50_95_mask"]),
                     textcoords="offset points", xytext=(10, 5), fontsize=10)
    ax.set_xlabel("Inference Time (ms)")
    ax.set_ylabel("Mask mAP50-95")
    ax.set_title("Speed vs Accuracy Tradeoff — YOLO26 Segmentation")
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(FIGURES_DIR, "fig02_speed_accuracy.png"), bbox_inches="tight")
    plt.savefig(os.path.join(FIGURES_DIR, "fig02_speed_accuracy.pdf"), bbox_inches="tight")
    plt.close()


def _s3_training_curves():
    """Training curves from YOLO results.csv files."""
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    cmap = plt.cm.tab10

    for i, (_, r) in enumerate(df.iterrows()):
        name = r["Model"]
        csv_path = os.path.join(MODELS_DIR, name, "results.csv")
        if not os.path.exists(csv_path):
            continue
        try:
            rdf = pd.read_csv(csv_path)
            rdf.columns = [c.strip() for c in rdf.columns]
            color = cmap(i)
            label = name.replace("yolo26", "Y26-").replace("-seg", "")

            # Find columns
            cols = rdf.columns.tolist()
            box_loss = [c for c in cols if 'box_loss' in c.lower() or 'train/box_loss' in c.lower()]
            seg_loss = [c for c in cols if 'seg_loss' in c.lower() or 'train/seg_loss' in c.lower()]
            val_box = [c for c in cols if 'val/box_loss' in c.lower()]
            val_seg = [c for c in cols if 'val/seg_loss' in c.lower()]
            mask_map = [c for c in cols if 'mask' in c.lower() and 'map50' in c.lower() and '95' not in c.lower()]
            mask_map95 = [c for c in cols if 'mask' in c.lower() and ('map50-95' in c.lower() or 'map' in c.lower()) and '50(' not in c.lower()]

            epochs = range(1, len(rdf) + 1)

            if box_loss:
                axes[0, 0].plot(epochs, rdf[box_loss[0]], color=color, label=label)
            if seg_loss:
                axes[0, 1].plot(epochs, rdf[seg_loss[0]], color=color, label=label)
            if val_box:
                axes[1, 0].plot(epochs, rdf[val_box[0]], color=color, label=label)
            if val_seg:
                axes[1, 1].plot(epochs, rdf[val_seg[0]], color=color, label=label)
        except Exception as e:
            print(f"    {name} curve HATA: {e}")

    for ax, title in zip(axes.flat, ["Train Box Loss", "Train Seg Loss",
                                      "Val Box Loss", "Val Seg Loss"]):
        ax.set_title(title)
        ax.set_xlabel("Epoch")
        ax.set_ylabel("Loss")
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)

    plt.suptitle("Training Dynamics — YOLO26 Segmentation", fontsize=14, y=1.02)
    plt.tight_layout()
    plt.savefig(os.path.join(FIGURES_DIR, "fig03_training_curves.png"), bbox_inches="tight")
    plt.savefig(os.path.join(FIGURES_DIR, "fig03_training_curves.pdf"), bbox_inches="tight")
    plt.close()


def _s4_params_vs_performance():
    """Bar + line: params vs mAP."""
    fig, ax1 = plt.subplots(figsize=(10, 6))
    models = [m.replace("yolo26","Y26-").replace("-seg","") for m in df["Model"]]
    x = np.arange(len(models))

    bars = ax1.bar(x, df["Params_M"], color="#90CAF9", edgecolor="black", alpha=0.8, label="Params (M)")
    ax1.set_ylabel("Parameters (M)", color="#1976D2")
    ax1.set_xticks(x)
    ax1.set_xticklabels(models)

    ax2 = ax1.twinx()
    ax2.plot(x, df["mAP50_95_mask"], "o-", color="#E91E63", linewidth=2, markersize=8, label="Mask mAP50-95")
    ax2.plot(x, df["mAP50_mask"], "s--", color="#4CAF50", linewidth=2, markersize=8, label="Mask mAP50")
    ax2.set_ylabel("mAP Score")
    ax2.set_ylim(0, 1)

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left")

    ax1.set_title("Model Size vs Segmentation Performance")
    plt.tight_layout()
    plt.savefig(os.path.join(FIGURES_DIR, "fig04_params_vs_performance.png"), bbox_inches="tight")
    plt.savefig(os.path.join(FIGURES_DIR, "fig04_params_vs_performance.pdf"), bbox_inches="tight")
    plt.close()


def _s5_comprehensive_radar():
    """Radar chart: 5 models, 6 metrics."""
    categories = ["mAP50\nBox", "mAP50-95\nBox", "mAP50\nMask", "mAP50-95\nMask", "F1\nBox", "F1\nMask"]
    N = len(categories)
    angles = np.linspace(0, 2 * np.pi, N, endpoint=False).tolist()
    angles += angles[:1]

    fig, ax = plt.subplots(figsize=(8, 8), subplot_kw=dict(polar=True))
    colors = sns.color_palette("Set2", len(df))

    for i, (_, r) in enumerate(df.iterrows()):
        values = [r["mAP50_box"], r["mAP50_95_box"], r["mAP50_mask"],
                  r["mAP50_95_mask"], r["F1_box"], r["F1_mask"]]
        values += values[:1]
        label = r["Model"].replace("yolo26", "Y26-").replace("-seg", "")
        ax.plot(angles, values, "o-", linewidth=2, label=label, color=colors[i])
        ax.fill(angles, values, alpha=0.1, color=colors[i])

    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(categories, fontsize=10)
    ax.set_ylim(0, 1)
    ax.set_title("Comprehensive Performance Radar — YOLO26", pad=20, fontsize=13)
    ax.legend(loc="upper right", bbox_to_anchor=(1.3, 1.1), fontsize=9)
    plt.tight_layout()
    plt.savefig(os.path.join(FIGURES_DIR, "fig05_radar.png"), bbox_inches="tight")
    plt.savefig(os.path.join(FIGURES_DIR, "fig05_radar.pdf"), bbox_inches="tight")
    plt.close()


def _s6_sample_predictions():
    """Show sample prediction images if available."""
    pred_dir = os.path.join(MODELS_DIR, "test_predictions")
    if not os.path.exists(pred_dir):
        print("  test_predictions yok"); return
    images = sorted(glob(os.path.join(pred_dir, "*.jpg")))[:12]
    if not images:
        print("  Tahmin goruntusu yok"); return

    n = min(12, len(images))
    cols = 4
    rows = (n + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(16, 4 * rows))
    axes = axes.flatten() if n > 1 else [axes]

    for i, img_path in enumerate(images[:n]):
        img = plt.imread(img_path)
        axes[i].imshow(img)
        axes[i].set_title(os.path.basename(img_path)[:25], fontsize=8)
        axes[i].axis("off")
    for i in range(n, len(axes)):
        axes[i].axis("off")

    plt.suptitle(f"Sample Predictions — {BEST}", fontsize=13)
    plt.tight_layout()
    plt.savefig(os.path.join(FIGURES_DIR, "fig06_sample_predictions.png"), bbox_inches="tight")
    plt.savefig(os.path.join(FIGURES_DIR, "fig06_sample_predictions.pdf"), bbox_inches="tight")
    plt.close()


def _s7_latex_tables():
    """LaTeX table."""
    lines = [
        "\\begin{table}[htbp]",
        "\\centering",
        "\\caption{YOLO26 Cat Segmentation Benchmark Results}",
        "\\label{tab:yolo26_seg}",
        "\\resizebox{\\textwidth}{!}{%",
        "\\begin{tabular}{lcccccccccc}",
        "\\toprule",
        "Model & mAP50\\textsubscript{box} & mAP50-95\\textsubscript{box} & "
        "mAP50\\textsubscript{mask} & mAP50-95\\textsubscript{mask} & "
        "F1\\textsubscript{box} & F1\\textsubscript{mask} & "
        "Params & Size & Infer & FPS \\\\",
        "\\midrule",
    ]
    for _, r in df.iterrows():
        nm = r["Model"].replace("_", "\\_")
        lines.append(
            f"{nm} & {r['mAP50_box']:.4f} & {r['mAP50_95_box']:.4f} & "
            f"{r['mAP50_mask']:.4f} & {r['mAP50_95_mask']:.4f} & "
            f"{r['F1_box']:.4f} & {r['F1_mask']:.4f} & "
            f"{r['Params_M']}M & {r['ModelSize_MB']:.1f}MB & "
            f"{r['Inference_ms']:.1f}ms & {r['FPS']:.0f} \\\\"
        )
    lines += ["\\bottomrule", "\\end{tabular}%", "}", "\\end{table}"]

    with open(os.path.join(TABLES_DIR, "table1_results.tex"), "w") as f:
        f.write("\n".join(lines))
    print(f"  -> table1_results.tex")


# ============================================================
# MAIN RUNNER
# ============================================================
SECTIONS = [
    (1, "MODEL COMPARISON BAR CHART",
     [os.path.join(FIGURES_DIR, "fig01_model_comparison.png")], _s1_model_comparison),
    (2, "SPEED vs ACCURACY SCATTER",
     [os.path.join(FIGURES_DIR, "fig02_speed_accuracy.png")], _s2_speed_accuracy),
    (3, "TRAINING CURVES",
     [os.path.join(FIGURES_DIR, "fig03_training_curves.png")], _s3_training_curves),
    (4, "PARAMS vs PERFORMANCE",
     [os.path.join(FIGURES_DIR, "fig04_params_vs_performance.png")], _s4_params_vs_performance),
    (5, "RADAR CHART",
     [os.path.join(FIGURES_DIR, "fig05_radar.png")], _s5_comprehensive_radar),
    (6, "SAMPLE PREDICTIONS",
     [os.path.join(FIGURES_DIR, "fig06_sample_predictions.png")], _s6_sample_predictions),
    (7, "LATEX TABLE",
     [os.path.join(TABLES_DIR, "table1_results.tex")], _s7_latex_tables),
]

for sid, name, outputs, func in SECTIONS:
    run_section(sid, name, outputs, func)

# Summary
print(f"\n\n{'='*60}")
n_ok = sum(1 for _, _, s in _STATUS if s == "OK")
n_skip = sum(1 for _, _, s in _STATUS if s == "SKIP")
n_fail = sum(1 for _, _, s in _STATUS if s == "FAIL")
print(f"Basarili: {n_ok} | Atlanan: {n_skip} | Basarisiz: {n_fail}")
for sid, nm, st in _STATUS:
    print(f"  [{st:4s}] [{sid}] {nm}")
print(f"\nFigurler: {FIGURES_DIR}")
print(f"Tablolar: {TABLES_DIR}")
print("=" * 60)

sys.exit(0 if n_fail == 0 else 1)
