#!/usr/bin/env python3
"""
analysis_cat_landmark.py — Cat Landmark Detection Post-Analysis
===============================================================
"""

import os, sys, time, json, warnings
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

MODELS_DIR = "/home/user02/dr/models/models_cat_landmark"
FIGURES_DIR = os.path.join(MODELS_DIR, "figures")
TABLES_DIR = os.path.join(MODELS_DIR, "tables")
os.makedirs(FIGURES_DIR, exist_ok=True)
os.makedirs(TABLES_DIR, exist_ok=True)

CSV_PATH = os.path.join(MODELS_DIR, "model_cat_landmark_karsilastirma.csv")

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


if not os.path.exists(CSV_PATH):
    print(f"HATA: {CSV_PATH} yok.")
    sys.exit(1)

df = pd.read_csv(CSV_PATH)
df = df.sort_values("mAP50_95_pose", ascending=False).reset_index(drop=True)
print(f"Loaded: {len(df)} models")
BEST = df.iloc[0]["Model"] if len(df) else None


# ============================================================
# 1. MODEL COMPARISON
# ============================================================
def _s1_model_comparison():
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    models = df["Model"].tolist()
    x = np.arange(len(models))
    w = 0.35

    ax = axes[0]
    ax.bar(x - w/2, df["mAP50_box"], w, label="mAP50", color="#2196F3", edgecolor="black")
    ax.bar(x + w/2, df["mAP50_95_box"], w, label="mAP50-95", color="#FF9800", edgecolor="black")
    ax.set_xticks(x)
    ax.set_xticklabels([m.replace("yolo","Y").replace("-pose","") for m in models], rotation=20, fontsize=8)
    ax.set_ylabel("Score"); ax.set_title("Box Detection"); ax.legend(); ax.set_ylim(0, 1)

    ax = axes[1]
    ax.bar(x - w/2, df["mAP50_pose"], w, label="mAP50", color="#4CAF50", edgecolor="black")
    ax.bar(x + w/2, df["mAP50_95_pose"], w, label="mAP50-95", color="#E91E63", edgecolor="black")
    ax.set_xticks(x)
    ax.set_xticklabels([m.replace("yolo","Y").replace("-pose","") for m in models], rotation=20, fontsize=8)
    ax.set_title("Pose (48 Keypoints)"); ax.legend(); ax.set_ylim(0, 1)

    plt.suptitle("YOLO Cat Landmark Detection — Box vs Pose", fontsize=14, y=1.02)
    plt.tight_layout()
    plt.savefig(os.path.join(FIGURES_DIR, "fig01_model_comparison.png"), bbox_inches="tight")
    plt.savefig(os.path.join(FIGURES_DIR, "fig01_model_comparison.pdf"), bbox_inches="tight")
    plt.close()


# ============================================================
# 2. SPEED vs ACCURACY
# ============================================================
def _s2_speed_accuracy():
    fig, ax = plt.subplots(figsize=(9, 6))
    colors = sns.color_palette("viridis", len(df))
    for i, (_, r) in enumerate(df.iterrows()):
        ax.scatter(r["Inference_ms"], r["mAP50_95_pose"],
                   s=r["Params_M"] * 20, color=colors[i], edgecolor="black", zorder=5, alpha=0.8)
        ax.annotate(r["Model"].replace("yolo","Y").replace("-pose",""),
                     (r["Inference_ms"], r["mAP50_95_pose"]),
                     textcoords="offset points", xytext=(10, 5), fontsize=9)
    ax.set_xlabel("Inference Time (ms)")
    ax.set_ylabel("Pose mAP50-95")
    ax.set_title("Speed vs Accuracy — Cat Landmark Detection")
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(FIGURES_DIR, "fig02_speed_accuracy.png"), bbox_inches="tight")
    plt.savefig(os.path.join(FIGURES_DIR, "fig02_speed_accuracy.pdf"), bbox_inches="tight")
    plt.close()


# ============================================================
# 3. TRAINING CURVES
# ============================================================
def _s3_training_curves():
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    cmap = plt.cm.tab10
    for i, (_, r) in enumerate(df.iterrows()):
        name = r["Model"]
        csv_path = os.path.join(MODELS_DIR, name, "results.csv")
        if not os.path.exists(csv_path): continue
        try:
            rdf = pd.read_csv(csv_path)
            rdf.columns = [c.strip() for c in rdf.columns]
            color = cmap(i % 10)
            label = name.replace("yolo", "Y").replace("-pose", "")

            pose_col = [c for c in rdf.columns if 'pose' in c.lower() and 'loss' in c.lower() and 'val' not in c.lower()]
            val_pose_col = [c for c in rdf.columns if 'pose' in c.lower() and 'loss' in c.lower() and 'val' in c.lower()]

            if pose_col:
                axes[0].plot(range(1, len(rdf)+1), rdf[pose_col[0]], color=color, label=label)
            if val_pose_col:
                axes[1].plot(range(1, len(rdf)+1), rdf[val_pose_col[0]], color=color, label=label)
        except: pass

    axes[0].set_title("Train Pose Loss"); axes[0].set_xlabel("Epoch"); axes[0].set_ylabel("Loss")
    axes[1].set_title("Val Pose Loss"); axes[1].set_xlabel("Epoch")
    for ax in axes:
        ax.legend(fontsize=7); ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(FIGURES_DIR, "fig03_training_curves.png"), bbox_inches="tight")
    plt.savefig(os.path.join(FIGURES_DIR, "fig03_training_curves.pdf"), bbox_inches="tight")
    plt.close()


# ============================================================
# 4. VERSION COMPARISON (v8 vs v11 vs v26)
# ============================================================
def _s4_version_comparison():
    fig, ax = plt.subplots(figsize=(10, 6))
    sizes = ["n", "s", "m"]
    versions = {"v8": [], "11": [], "26": []}

    for size in sizes:
        for ver_key, ver_prefix in [("v8", "yolov8"), ("11", "yolo11"), ("26", "yolo26")]:
            model_name = f"{ver_prefix}{size}-pose"
            row = df[df["Model"] == model_name]
            if len(row) > 0:
                versions[ver_key].append(float(row.iloc[0]["mAP50_95_pose"]))
            else:
                versions[ver_key].append(0)

    x = np.arange(len(sizes))
    w = 0.25
    colors = ["#2196F3", "#4CAF50", "#FF9800"]
    for i, (ver, vals) in enumerate(versions.items()):
        bars = ax.bar(x + i*w, vals, w, label=f"YOLO{ver}", color=colors[i], edgecolor="black")
        for bar, val in zip(bars, vals):
            if val > 0:
                ax.text(bar.get_x() + bar.get_width()/2, val + 0.005, f"{val:.3f}",
                        ha="center", fontsize=9)

    ax.set_xticks(x + w)
    ax.set_xticklabels(["Nano", "Small", "Medium"])
    ax.set_ylabel("Pose mAP50-95")
    ax.set_title("YOLO Version Comparison — Landmark Detection")
    ax.legend()
    ax.set_ylim(0, 1)
    ax.grid(True, alpha=0.3, axis="y")
    plt.tight_layout()
    plt.savefig(os.path.join(FIGURES_DIR, "fig04_version_comparison.png"), bbox_inches="tight")
    plt.savefig(os.path.join(FIGURES_DIR, "fig04_version_comparison.pdf"), bbox_inches="tight")
    plt.close()


# ============================================================
# 5. SAMPLE PREDICTIONS
# ============================================================
def _s5_sample_predictions():
    if BEST is None: return
    best_pt = os.path.join(MODELS_DIR, BEST, "weights", "best.pt")
    if not os.path.exists(best_pt):
        print("  best.pt yok"); return

    from ultralytics import YOLO
    model = YOLO(best_pt)

    test_dir = "/home/user02/dr/dataset/cat_landmark/yolo_pose/test/images"
    test_imgs = sorted(glob(os.path.join(test_dir, "*.png")))[:8]
    if not test_imgs:
        print("  Test goruntusu yok"); return

    results = model.predict(test_imgs, imgsz=640, device=0, verbose=False)

    cols = 4
    rows = 2
    fig, axes = plt.subplots(rows, cols, figsize=(16, 8))
    axes = axes.flatten()

    for i, (r, img_path) in enumerate(zip(results, test_imgs)):
        if i >= 8: break
        img = plt.imread(img_path)
        ax = axes[i]
        ax.imshow(img)

        # Draw keypoints
        if r.keypoints is not None and len(r.keypoints.data) > 0:
            kpts = r.keypoints.data[0].cpu().numpy()  # (48, 3) x,y,conf
            for x, y, conf in kpts:
                if conf > 0.3:
                    ax.plot(x, y, 'r.', markersize=3)

        # Draw bbox
        if r.boxes is not None and len(r.boxes) > 0:
            for box in r.boxes:
                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                rect = plt.Rectangle((x1, y1), x2-x1, y2-y1,
                                     linewidth=1.5, edgecolor='lime', facecolor='none')
                ax.add_patch(rect)

        ax.set_title(os.path.basename(img_path)[:20], fontsize=8)
        ax.axis("off")

    for i in range(len(results), 8):
        axes[i].axis("off")

    plt.suptitle(f"Sample Predictions — {BEST} (48 landmarks)", fontsize=13)
    plt.tight_layout()
    plt.savefig(os.path.join(FIGURES_DIR, "fig05_sample_predictions.png"), bbox_inches="tight")
    plt.savefig(os.path.join(FIGURES_DIR, "fig05_sample_predictions.pdf"), bbox_inches="tight")
    plt.close()
    del model
    import torch; torch.cuda.empty_cache()


# ============================================================
# 6. PARAMS vs PERFORMANCE
# ============================================================
def _s6_params_performance():
    fig, ax1 = plt.subplots(figsize=(10, 6))
    models = [m.replace("yolo","Y").replace("-pose","") for m in df["Model"]]
    x = np.arange(len(models))

    bars = ax1.bar(x, df["Params_M"], color="#90CAF9", edgecolor="black", alpha=0.8, label="Params (M)")
    ax1.set_ylabel("Parameters (M)", color="#1976D2")
    ax1.set_xticks(x)
    ax1.set_xticklabels(models, rotation=20, fontsize=8)

    ax2 = ax1.twinx()
    ax2.plot(x, df["mAP50_95_pose"], "o-", color="#E91E63", linewidth=2, markersize=8, label="Pose mAP50-95")
    ax2.set_ylabel("mAP Score")
    ax2.set_ylim(0, 1)

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left")
    ax1.set_title("Model Size vs Landmark Detection Performance")
    plt.tight_layout()
    plt.savefig(os.path.join(FIGURES_DIR, "fig06_params_performance.png"), bbox_inches="tight")
    plt.savefig(os.path.join(FIGURES_DIR, "fig06_params_performance.pdf"), bbox_inches="tight")
    plt.close()


# ============================================================
# 7. LATEX TABLE
# ============================================================
def _s7_latex():
    lines = [
        "\\begin{table}[htbp]", "\\centering",
        "\\caption{YOLO Cat Facial Landmark Detection (48 keypoints)}",
        "\\label{tab:cat_landmark}",
        "\\resizebox{\\textwidth}{!}{%",
        "\\begin{tabular}{lccccccc}", "\\toprule",
        "Model & mAP50\\textsubscript{box} & mAP50-95\\textsubscript{box} & "
        "mAP50\\textsubscript{pose} & mAP50-95\\textsubscript{pose} & "
        "Params & Infer & FPS \\\\", "\\midrule",
    ]
    for _, r in df.iterrows():
        nm = r["Model"].replace("_", "\\_")
        lines.append(
            f"{nm} & {r['mAP50_box']:.4f} & {r['mAP50_95_box']:.4f} & "
            f"{r['mAP50_pose']:.4f} & {r['mAP50_95_pose']:.4f} & "
            f"{r['Params_M']}M & {r['Inference_ms']:.1f}ms & {r['FPS']:.0f} \\\\"
        )
    lines += ["\\bottomrule", "\\end{tabular}%", "}", "\\end{table}"]
    with open(os.path.join(TABLES_DIR, "table1_results.tex"), "w") as f:
        f.write("\n".join(lines))
    print(f"  -> table1_results.tex")


# ============================================================
# MAIN RUNNER
# ============================================================
SECTIONS = [
    (1, "MODEL COMPARISON",
     [os.path.join(FIGURES_DIR, "fig01_model_comparison.png")], _s1_model_comparison),
    (2, "SPEED vs ACCURACY",
     [os.path.join(FIGURES_DIR, "fig02_speed_accuracy.png")], _s2_speed_accuracy),
    (3, "TRAINING CURVES",
     [os.path.join(FIGURES_DIR, "fig03_training_curves.png")], _s3_training_curves),
    (4, "VERSION COMPARISON (v8 vs v11 vs v26)",
     [os.path.join(FIGURES_DIR, "fig04_version_comparison.png")], _s4_version_comparison),
    (5, "SAMPLE PREDICTIONS",
     [os.path.join(FIGURES_DIR, "fig05_sample_predictions.png")], _s5_sample_predictions),
    (6, "PARAMS vs PERFORMANCE",
     [os.path.join(FIGURES_DIR, "fig06_params_performance.png")], _s6_params_performance),
    (7, "LATEX TABLE",
     [os.path.join(TABLES_DIR, "table1_results.tex")], _s7_latex),
]

for sid, name, outputs, func in SECTIONS:
    run_section(sid, name, outputs, func)

print(f"\n{'='*60}")
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
