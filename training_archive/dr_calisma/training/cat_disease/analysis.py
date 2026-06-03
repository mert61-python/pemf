#!/usr/bin/env python3
"""
analysis_cat_disease.py — Post-Training Analizleri (SCI Makale)
================================================================
training_cat_disease.py'yi calistirdiktan sonra bu script'i calistir.

Veri kaynaklari:
  - models_cat_disease/predictions.npz          (tum tahminler, labellar)
  - models_cat_disease/model_cat_disease_karsilastirma.csv (metrikler)
  - models_cat_disease/per_class_metrics.csv     (sinif bazli metrikler)
  - models_cat_disease/confusion_matrix.csv      (18x18 confusion matrix)
  - models_cat_disease/bootstrap_ci.csv          (bootstrap CI)
  - models_cat_disease/training_curves/*.csv     (loss egrileri)
  - models_cat_disease/label_encoder.pkl         (LabelEncoder)
  - models_cat_disease/scaler_X.pkl              (StandardScaler)
  - models_cat_disease/*.pt, *.pkl               (modeller)

Uretilen analizler (15 bolum):
   1. Confusion Matrix Heatmap (top-1 model)
   2. Per-Class Performance Bar Chart
   3. Model Comparison Bar Chart (top-20)
   4. ROC Curves (top-3, one-vs-rest)
   5. Raw vs Normal vs Diamond Comparison
   6. Size Effect (Small->XXL)
   7. Sklearn Model Comparison
   8. Feature Importance (top sklearn)
   9. SHAP (top-1 sklearn, 500 samples)
  10. Training Curves (top-5 DL)
  11. Bootstrap CI (top-10)
  12. Misclassification Analysis
  13. Statistical Tests (Friedman + Wilcoxon)
  14. Calibration (top-3)
  15. LaTeX Tables
"""

import os, sys, json, time, warnings
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import seaborn as sns
from scipy import stats
from sklearn.metrics import (accuracy_score, confusion_matrix, roc_curve, auc,
                             classification_report)
from sklearn.calibration import calibration_curve
import joblib

warnings.filterwarnings("ignore")
plt.rcParams.update({
    "figure.dpi": 150,
    "savefig.dpi": 300,
    "font.size": 10,
    "font.family": "serif",
})
sns.set_style("whitegrid")

# ============================================================
# CONFIG
# ============================================================
MODELS_DIR = "/home/user02/dr/models_cat_disease"
FIGURES_DIR = os.path.join(MODELS_DIR, "figures")
ANALYSIS_DIR = os.path.join(MODELS_DIR, "analysis")
LATEX_DIR = os.path.join(MODELS_DIR, "latex")
CURVES_DIR = os.path.join(MODELS_DIR, "training_curves")
os.makedirs(FIGURES_DIR, exist_ok=True)
os.makedirs(ANALYSIS_DIR, exist_ok=True)
os.makedirs(LATEX_DIR, exist_ok=True)

SEED = 42
np.random.seed(SEED)

print("=" * 80)
print("ANALYSIS_CAT_DISEASE.PY — SCI Makale Post-Analizleri")
print("=" * 80)

# ============================================================
# Load predictions + results
# ============================================================
print("\n[LOAD] predictions.npz + model_cat_disease_karsilastirma.csv ...")
PRED_PATH = os.path.join(MODELS_DIR, "predictions.npz")
CSV_PATH = os.path.join(MODELS_DIR, "model_cat_disease_karsilastirma.csv")
LE_PATH = os.path.join(MODELS_DIR, "label_encoder.pkl")

if not os.path.exists(PRED_PATH):
    print(f"HATA: {PRED_PATH} bulunamadi. Once training_cat_disease.py'yi calistir.")
    sys.exit(1)

preds_npz = np.load(PRED_PATH, allow_pickle=True)
results_df = pd.read_csv(CSV_PATH)
label_encoder = joblib.load(LE_PATH)
disease_names = list(label_encoder.classes_)  # 18 disease names
n_classes = len(disease_names)

# Extract per-model probabilities
all_test_probs = {}
all_val_probs = {}
for k in preds_npz.files:
    if k.endswith("__test_probs"):
        all_test_probs[k.replace("__test_probs", "")] = preds_npz[k]
    elif k.endswith("__val_probs"):
        all_val_probs[k.replace("__val_probs", "")] = preds_npz[k]
y_test = preds_npz["y_test"]
y_val = preds_npz["y_val"]
X_test_sc = preds_npz["X_test_sc"]
X_val_sc = preds_npz["X_val_sc"]

print(f"  {len(all_test_probs)} modelin tahminleri yuklendi")
print(f"  Test: {len(y_test)} satir | Val: {len(y_val)} satir")
print(f"  CSV: {len(results_df)} kayit")
print(f"  Hastalik sayisi: {n_classes}")
print(f"  Hastaliklar: {disease_names}")

# Sort by Accuracy
results_df["Accuracy"] = pd.to_numeric(results_df["Accuracy"], errors="coerce")
results_df = results_df.dropna(subset=["Accuracy"]).sort_values(
    "Accuracy", ascending=False).reset_index(drop=True)

TOP_20 = results_df["Model"].head(20).tolist()
TOP_10 = results_df["Model"].head(10).tolist()
TOP_5 = results_df["Model"].head(5).tolist()
TOP_3 = results_df["Model"].head(3).tolist()
BEST = results_df["Model"].iloc[0] if len(results_df) else None
print(f"  Best: {BEST}")
print(f"  Top-5: {TOP_5}")

# Feature names (from training script)
FEATURE_NAMES = (
    ["Age", "Weight", "Heart_Rate", "Body_Temperature", "Duration_days"]
    + ["Gender_bin"]
    + [c + "_bin" for c in ["Appetite_Loss", "Vomiting", "Diarrhea", "Coughing",
                            "Labored_Breathing", "Lameness", "Skin_Lesions",
                            "Nasal_Discharge", "Eye_Discharge"]]
    + ["has_Lethargy", "has_Weight_Loss", "has_Sneezing", "has_Dehydration", "has_Fever"]
    + [f"Breed_{i}" for i in range(16)]  # breed one-hot
)
# Try loading actual breed columns from scaler or data
_scaler_path = os.path.join(MODELS_DIR, "scaler_X.pkl")
if os.path.exists(_scaler_path):
    try:
        _scaler = joblib.load(_scaler_path)
        if hasattr(_scaler, "feature_names_in_"):
            FEATURE_NAMES = list(_scaler.feature_names_in_)
    except:
        pass
IN_DIM = len(FEATURE_NAMES) if len(FEATURE_NAMES) == 36 else 36

# ============================================================
# Model family helpers
# ============================================================
SK_LIST = ["XGBoost", "LightGBM", "CatBoost", "ExtraTrees", "RandomForest",
           "DecisionTree", "AdaBoost", "Bagging", "LogisticRegression",
           "KNeighbors", "GaussianNB", "SVC", "GradientBoosting",
           "HistGradientBoosting", "MLPClassifier"]

def get_family(nm):
    if "diamond" in nm: return "MLP_Diamond"
    if "Raw" in nm: return "MLP_Raw"
    if nm.startswith("MLP_") and "diamond" not in nm and "Raw" not in nm and "Classifier" not in nm:
        return "MLP_Normal"
    if nm in SK_LIST: return "Sklearn"
    if "Ensemble" in nm: return "Ensemble"
    if "Stacking" in nm: return "Stacking"
    return "Other"

def get_model_type_color(nm):
    """Return (type_label, color) for model bar chart coloring."""
    fam = get_family(nm)
    cmap = {
        "MLP_Raw": ("DL Raw", "#e74c3c"),
        "MLP_Normal": ("DL Normal", "#3498db"),
        "MLP_Diamond": ("DL Diamond", "#2ecc71"),
        "Sklearn": ("Sklearn", "#f39c12"),
        "Ensemble": ("Ensemble", "#9b59b6"),
        "Stacking": ("Ensemble", "#9b59b6"),
    }
    return cmap.get(fam, ("Other", "#95a5a6"))

def get_sklearn_type(nm):
    """Return sklearn model sub-type for coloring."""
    tree = {"DecisionTree", "RandomForest", "ExtraTrees", "Bagging"}
    boosting = {"XGBoost", "LightGBM", "CatBoost", "GradientBoosting",
                "HistGradientBoosting", "AdaBoost"}
    linear = {"LogisticRegression", "MLPClassifier"}
    distance = {"KNeighbors", "SVC"}
    probabilistic = {"GaussianNB"}
    if nm in tree: return "Tree-based"
    if nm in boosting: return "Boosting"
    if nm in linear: return "Linear/NN"
    if nm in distance: return "Distance-based"
    if nm in probabilistic: return "Probabilistic"
    return "Other"

def _save_fig(fig, name):
    """Save figure as PNG + PDF."""
    fig.savefig(os.path.join(FIGURES_DIR, f"{name}.png"), bbox_inches="tight")
    fig.savefig(os.path.join(FIGURES_DIR, f"{name}.pdf"), bbox_inches="tight")
    plt.close(fig)


# ============================================================
# Section runner with skip + try/except
# ============================================================
_SECTION_STATUS = []

def run_section(sec_id, name, outputs, func):
    print(f"\n{'='*80}")
    print(f"[{sec_id:2d}] {name}")
    print('=' * 80)

    if outputs and all(os.path.exists(p) for p in outputs):
        print(f"  SKIP: tum ciktilar mevcut ({len(outputs)} dosya)")
        _SECTION_STATUS.append((sec_id, name, "SKIP"))
        return

    t0 = time.time()
    try:
        func()
        dt = time.time() - t0
        print(f"  OK ({dt:.1f}s)")
        _SECTION_STATUS.append((sec_id, name, "OK"))
    except KeyboardInterrupt:
        raise
    except Exception as e:
        import traceback
        print(f"  HATA: {str(e)[:200]}")
        traceback.print_exc(limit=3)
        _SECTION_STATUS.append((sec_id, name, f"FAIL: {str(e)[:80]}"))


# ============================================================
# 1. CONFUSION MATRIX HEATMAP (top-1 model)
# ============================================================
def _s1_confusion_matrix():
    if BEST not in all_test_probs:
        print("  Best model yok"); return
    probs = all_test_probs[BEST]
    preds = probs.argmax(axis=1)

    cm = confusion_matrix(y_test, preds)

    # Raw counts
    fig, ax = plt.subplots(figsize=(14, 12))
    sns.heatmap(cm, annot=True, fmt="d", cmap="Blues",
                xticklabels=disease_names, yticklabels=disease_names, ax=ax)
    ax.set_xlabel("Predicted"); ax.set_ylabel("True")
    ax.set_title(f"Confusion Matrix — {BEST}\n(Raw Counts)")
    plt.xticks(rotation=45, ha="right", fontsize=8)
    plt.yticks(fontsize=8)
    _save_fig(fig, "confusion_matrix_best")

    # Normalized (per-row = recall per class)
    cm_norm = cm.astype(float) / cm.sum(axis=1, keepdims=True)
    fig, ax = plt.subplots(figsize=(14, 12))
    sns.heatmap(cm_norm, annot=True, fmt=".2f", cmap="YlOrRd",
                xticklabels=disease_names, yticklabels=disease_names, ax=ax,
                vmin=0, vmax=1)
    ax.set_xlabel("Predicted"); ax.set_ylabel("True")
    ax.set_title(f"Normalized Confusion Matrix — {BEST}\n(Row = Recall per class)")
    plt.xticks(rotation=45, ha="right", fontsize=8)
    plt.yticks(fontsize=8)
    _save_fig(fig, "confusion_matrix_best_normalized")

    print(f"  -> confusion_matrix_best.png/pdf, confusion_matrix_best_normalized.png/pdf")


# ============================================================
# 2. PER-CLASS PERFORMANCE BAR CHART
# ============================================================
def _s2_per_class():
    pc_path = os.path.join(MODELS_DIR, "per_class_metrics.csv")
    if not os.path.exists(pc_path):
        print("  per_class_metrics.csv yok, best model'den hesaplaniyor...")
        # Compute from best model
        if BEST not in all_test_probs:
            print("  Best model yok"); return
        probs = all_test_probs[BEST]
        preds = probs.argmax(axis=1)
        report = classification_report(y_test, preds, output_dict=True, zero_division=0)
        rows = []
        for cls_idx in range(n_classes):
            cls_key = str(cls_idx)
            if cls_key in report:
                rows.append({
                    "Model": BEST, "Class_ID": cls_idx,
                    "Class_Name": disease_names[cls_idx],
                    "Precision": report[cls_key]["precision"],
                    "Recall": report[cls_key]["recall"],
                    "F1": report[cls_key]["f1-score"],
                    "Support": report[cls_key]["support"],
                })
        pc_df = pd.DataFrame(rows)
    else:
        pc_df = pd.read_csv(pc_path)

    # Use best model only
    best_pc = pc_df[pc_df["Model"] == BEST].copy()
    if best_pc.empty and len(pc_df) > 0:
        # fallback: use first model
        first_model = pc_df["Model"].iloc[0]
        best_pc = pc_df[pc_df["Model"] == first_model].copy()

    if best_pc.empty:
        print("  Per-class data bos"); return

    best_pc = best_pc.sort_values("F1", ascending=False).reset_index(drop=True)

    fig, ax = plt.subplots(figsize=(16, 8))
    x = np.arange(len(best_pc))
    w = 0.25
    ax.bar(x - w, best_pc["Precision"], w, label="Precision", color="#3498db", edgecolor="black")
    ax.bar(x,     best_pc["Recall"],    w, label="Recall",    color="#2ecc71", edgecolor="black")
    ax.bar(x + w, best_pc["F1"],        w, label="F1-Score",  color="#e74c3c", edgecolor="black")

    ax.set_xticks(x)
    ax.set_xticklabels(best_pc["Class_Name"], rotation=45, ha="right", fontsize=8)
    ax.set_ylabel("Score")
    ax.set_title(f"Per-Class Performance (sorted by F1) — {BEST}")
    ax.legend()
    ax.set_ylim(0, 1.05)
    ax.grid(True, alpha=0.3, axis="y")

    # Highlight worst 3
    worst3 = best_pc.tail(3)
    for _, row in worst3.iterrows():
        idx = best_pc.index.get_loc(row.name) if hasattr(row, 'name') else 0
        ax.axvspan(idx - 0.4, idx + 0.4, alpha=0.15, color="red")

    plt.tight_layout()
    _save_fig(fig, "per_class_performance")
    print(f"  -> per_class_performance.png/pdf")


# ============================================================
# 3. MODEL COMPARISON BAR CHART (top-20)
# ============================================================
def _s3_top20_bar():
    top20_df = results_df.head(20).copy()
    top20_df = top20_df.sort_values("Accuracy", ascending=True).reset_index(drop=True)

    fig, ax = plt.subplots(figsize=(12, 8))
    colors = [get_model_type_color(nm)[1] for nm in top20_df["Model"]]
    bars = ax.barh(top20_df["Model"], top20_df["Accuracy"],
                   color=colors, edgecolor="black", linewidth=0.5)

    for bar, val in zip(bars, top20_df["Accuracy"]):
        ax.text(val + 0.001, bar.get_y() + bar.get_height()/2,
                f"{val:.4f}", va="center", fontsize=8)

    # Legend
    seen = {}
    for nm in top20_df["Model"]:
        lbl, clr = get_model_type_color(nm)
        if lbl not in seen: seen[lbl] = clr
    legend_patches = [Patch(facecolor=c, edgecolor="black", label=l) for l, c in seen.items()]
    ax.legend(handles=legend_patches, loc="lower right", fontsize=9)

    ax.set_xlabel("Accuracy")
    ax.set_title("Top-20 Models by Accuracy")
    xmin = top20_df["Accuracy"].min() * 0.995
    xmax = top20_df["Accuracy"].max() * 1.002
    ax.set_xlim(xmin, xmax)
    plt.tight_layout()
    _save_fig(fig, "top20_bar")
    print(f"  -> top20_bar.png/pdf")


# ============================================================
# 4. ROC CURVES (top-3, one-vs-rest)
# ============================================================
def _s4_roc_curves():
    from sklearn.preprocessing import label_binarize

    y_test_bin = label_binarize(y_test, classes=np.arange(n_classes))

    fig, axes = plt.subplots(1, 3, figsize=(21, 7))
    for ax_idx, nm in enumerate(TOP_3):
        if nm not in all_test_probs: continue
        probs = all_test_probs[nm]
        ax = axes[ax_idx]

        # Per-class ROC
        all_fpr = []; all_tpr = []; all_roc_auc = []
        for i in range(n_classes):
            fpr, tpr, _ = roc_curve(y_test_bin[:, i], probs[:, i])
            roc_auc_i = auc(fpr, tpr)
            all_fpr.append(fpr); all_tpr.append(tpr); all_roc_auc.append(roc_auc_i)
            ax.plot(fpr, tpr, alpha=0.3, linewidth=0.8)

        # Micro-average
        fpr_micro, tpr_micro, _ = roc_curve(y_test_bin.ravel(), probs.ravel())
        auc_micro = auc(fpr_micro, tpr_micro)
        ax.plot(fpr_micro, tpr_micro, "b-", linewidth=2,
                label=f"Micro-avg (AUC={auc_micro:.4f})")

        # Macro-average
        mean_fpr = np.linspace(0, 1, 200)
        mean_tpr = np.zeros_like(mean_fpr)
        for i in range(n_classes):
            mean_tpr += np.interp(mean_fpr, all_fpr[i], all_tpr[i])
        mean_tpr /= n_classes
        auc_macro = auc(mean_fpr, mean_tpr)
        ax.plot(mean_fpr, mean_tpr, "r--", linewidth=2,
                label=f"Macro-avg (AUC={auc_macro:.4f})")

        ax.plot([0, 1], [0, 1], "k:", linewidth=1)
        ax.set_xlabel("False Positive Rate")
        ax.set_ylabel("True Positive Rate")
        ax.set_title(f"ROC — {nm}")
        ax.legend(fontsize=8, loc="lower right")
        ax.grid(True, alpha=0.3)

    plt.tight_layout()
    _save_fig(fig, "roc_curves_top3")
    print(f"  -> roc_curves_top3.png/pdf")


# ============================================================
# 5. RAW vs NORMAL vs DIAMOND COMPARISON
# ============================================================
def _s5_variant_comparison():
    groups = {"Raw": [], "Normal": [], "Diamond": []}
    for _, row in results_df.iterrows():
        nm = row["Model"]
        acc = row["Accuracy"]
        if "diamond" in nm: groups["Diamond"].append(acc)
        elif "Raw" in nm and nm.startswith("MLP_"): groups["Raw"].append(acc)
        elif nm.startswith("MLP_") and "diamond" not in nm and "Raw" not in nm and "Classifier" not in nm:
            groups["Normal"].append(acc)

    # Check we have data
    non_empty = {k: v for k, v in groups.items() if len(v) > 0}
    if len(non_empty) < 2:
        print("  Yeterli MLP varyant yok"); return

    fig, ax = plt.subplots(figsize=(8, 6))
    data = [groups[g] for g in ["Raw", "Normal", "Diamond"] if groups[g]]
    labels = [g for g in ["Raw", "Normal", "Diamond"] if groups[g]]
    colors = ["#e74c3c", "#3498db", "#2ecc71"][:len(labels)]

    parts = ax.violinplot(data, positions=range(len(labels)), showmeans=True,
                          showmedians=True, showextrema=True)
    for i, pc in enumerate(parts["bodies"]):
        pc.set_facecolor(colors[i])
        pc.set_alpha(0.6)

    # Scatter individual points
    for i, vals in enumerate(data):
        jitter = np.random.RandomState(SEED).uniform(-0.1, 0.1, len(vals))
        ax.scatter(np.full(len(vals), i) + jitter, vals, s=40, alpha=0.8,
                   color=colors[i], edgecolor="black", zorder=5)

    # Annotate mean/median
    for i, vals in enumerate(data):
        mn = np.mean(vals); md = np.median(vals)
        ax.text(i + 0.15, mn, f"mean={mn:.4f}", fontsize=8, va="center")
        ax.text(i + 0.15, md, f"med={md:.4f}", fontsize=8, va="center", color="gray")

    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, fontsize=11)
    ax.set_ylabel("Accuracy")
    ax.set_title("MLP Variant Comparison: Raw vs Normal vs Diamond")
    ax.grid(True, alpha=0.3, axis="y")
    plt.tight_layout()
    _save_fig(fig, "variant_comparison")
    print(f"  -> variant_comparison.png/pdf")


# ============================================================
# 6. SIZE EFFECT (Small -> XXL)
# ============================================================
def _s6_size_effect():
    sizes = ["Small", "Medium", "Large", "XL", "XXL"]
    groups = {"Raw": {}, "Normal": {}, "Diamond": {}}

    for _, row in results_df.iterrows():
        nm = row["Model"]; acc = row["Accuracy"]
        for sz in sizes:
            if sz not in nm: continue
            if "diamond" in nm:
                groups["Diamond"][sz] = acc
            elif "Raw" in nm:
                groups["Raw"][sz] = acc
            elif nm.startswith("MLP_") and "Classifier" not in nm:
                groups["Normal"][sz] = acc
            break

    fig, ax = plt.subplots(figsize=(10, 6))
    markers = {"Raw": "o", "Normal": "s", "Diamond": "D"}
    colors = {"Raw": "#e74c3c", "Normal": "#3498db", "Diamond": "#2ecc71"}

    for grp_name in ["Raw", "Normal", "Diamond"]:
        x_vals = []; y_vals = []; x_labels = []
        for i, sz in enumerate(sizes):
            if sz in groups[grp_name]:
                x_vals.append(i)
                y_vals.append(groups[grp_name][sz])
                x_labels.append(sz)
        if x_vals:
            ax.plot(x_vals, y_vals, f"-{markers[grp_name]}", color=colors[grp_name],
                    label=grp_name, linewidth=2, markersize=8)

    ax.set_xticks(range(len(sizes)))
    ax.set_xticklabels(sizes, fontsize=11)
    ax.set_xlabel("Model Size")
    ax.set_ylabel("Accuracy")
    ax.set_title("Size Effect on Accuracy (MLP variants)")
    ax.legend(fontsize=10)
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    _save_fig(fig, "size_effect")
    print(f"  -> size_effect.png/pdf")


# ============================================================
# 7. SKLEARN MODEL COMPARISON
# ============================================================
def _s7_sklearn_comparison():
    sk_df = results_df[results_df["Model"].isin(SK_LIST)].copy()
    if sk_df.empty:
        print("  Sklearn model yok"); return

    sk_df = sk_df.sort_values("Accuracy", ascending=True).reset_index(drop=True)
    sk_type_colors = {
        "Tree-based": "#27ae60", "Boosting": "#e67e22",
        "Linear/NN": "#3498db", "Distance-based": "#e74c3c",
        "Probabilistic": "#9b59b6", "Other": "#95a5a6",
    }
    colors = [sk_type_colors.get(get_sklearn_type(nm), "#95a5a6") for nm in sk_df["Model"]]

    fig, ax = plt.subplots(figsize=(12, 8))
    bars = ax.barh(sk_df["Model"], sk_df["Accuracy"],
                   color=colors, edgecolor="black", linewidth=0.5)

    for bar, val in zip(bars, sk_df["Accuracy"]):
        ax.text(val + 0.001, bar.get_y() + bar.get_height()/2,
                f"{val:.4f}", va="center", fontsize=8)

    # Legend
    seen = {}
    for nm in sk_df["Model"]:
        t = get_sklearn_type(nm)
        if t not in seen: seen[t] = sk_type_colors.get(t, "#95a5a6")
    legend_patches = [Patch(facecolor=c, edgecolor="black", label=l) for l, c in seen.items()]
    ax.legend(handles=legend_patches, loc="lower right", fontsize=9)

    ax.set_xlabel("Accuracy")
    ax.set_title("Sklearn Model Comparison (15 models)")
    xmin = max(0, sk_df["Accuracy"].min() - 0.02)
    ax.set_xlim(xmin, sk_df["Accuracy"].max() * 1.002)
    plt.tight_layout()
    _save_fig(fig, "sklearn_comparison")
    print(f"  -> sklearn_comparison.png/pdf")


# ============================================================
# 8. FEATURE IMPORTANCE (top sklearn model)
# ============================================================
def _s8_feature_importance():
    # Find best sklearn model that has feature_importances_
    sk_best = None
    sk_model = None
    for nm in TOP_20:
        pkl_path = os.path.join(MODELS_DIR, f"{nm}.pkl")
        if not os.path.exists(pkl_path): continue
        if nm not in SK_LIST: continue
        try:
            m = joblib.load(pkl_path)
            if hasattr(m, "feature_importances_"):
                sk_best = nm; sk_model = m; break
        except:
            continue

    if sk_best is None:
        # Fallback: try any sklearn model with feature_importances_
        for nm in SK_LIST:
            pkl_path = os.path.join(MODELS_DIR, f"{nm}.pkl")
            if not os.path.exists(pkl_path): continue
            try:
                m = joblib.load(pkl_path)
                if hasattr(m, "feature_importances_"):
                    sk_best = nm; sk_model = m; break
            except:
                continue

    if sk_best is None:
        print("  Feature importances destekleyen sklearn model yok"); return

    print(f"  Feature importance target: {sk_best}")
    fi = sk_model.feature_importances_
    feat_names = FEATURE_NAMES[:len(fi)] if len(FEATURE_NAMES) >= len(fi) else \
                 [f"feat_{i}" for i in range(len(fi))]

    fi_df = pd.DataFrame({"Feature": feat_names, "Importance": fi})
    fi_df = fi_df.sort_values("Importance", ascending=True)
    fi_df.to_csv(os.path.join(ANALYSIS_DIR, "feature_importance.csv"), index=False)

    fig, ax = plt.subplots(figsize=(10, max(8, len(fi_df) * 0.3)))
    ax.barh(fi_df["Feature"], fi_df["Importance"],
            color="steelblue", edgecolor="black")
    ax.set_xlabel("Feature Importance")
    ax.set_title(f"Feature Importance — {sk_best}")
    ax.grid(True, alpha=0.3, axis="x")
    plt.tight_layout()
    _save_fig(fig, "feature_importance")
    print(f"  -> feature_importance.csv, feature_importance.png/pdf")
    del sk_model


# ============================================================
# 9. SHAP (top-1 sklearn, 500 samples)
# ============================================================
def _s9_shap():
    import shap

    sk_best = None
    for nm in TOP_20:
        pkl_path = os.path.join(MODELS_DIR, f"{nm}.pkl")
        if os.path.exists(pkl_path) and nm in SK_LIST:
            sk_best = nm; break
    if sk_best is None:
        for nm in SK_LIST:
            if os.path.exists(os.path.join(MODELS_DIR, f"{nm}.pkl")):
                sk_best = nm; break

    if sk_best is None:
        print("  Sklearn model yok"); return

    print(f"  SHAP target: {sk_best}")
    mdl_sk = joblib.load(os.path.join(MODELS_DIR, f"{sk_best}.pkl"))

    rng = np.random.RandomState(SEED)
    bg_idx = rng.choice(len(X_test_sc), min(100, len(X_test_sc)), replace=False)
    ex_idx = rng.choice(len(X_test_sc), min(500, len(X_test_sc)), replace=False)
    bg = X_test_sc[bg_idx]
    ex = X_test_sc[ex_idx]

    try:
        explainer = shap.TreeExplainer(mdl_sk)
        shap_values = explainer.shap_values(ex)
        print(f"  TreeExplainer kullanildi")
    except Exception as e:
        print(f"  TreeExplainer basarisiz ({str(e)[:60]}), KernelExplainer...")
        def predict_proba_fn(X):
            return mdl_sk.predict_proba(X)
        explainer = shap.KernelExplainer(predict_proba_fn, bg)
        shap_values = explainer.shap_values(ex[:100])

    # Aggregate SHAP across classes
    if isinstance(shap_values, list):
        shap_abs = np.mean([np.abs(sv).mean(axis=0) for sv in shap_values], axis=0)
    else:
        shap_abs = np.abs(shap_values).mean(axis=0)
        if shap_abs.ndim > 1:
            shap_abs = shap_abs.mean(axis=-1)

    feat_names = FEATURE_NAMES[:len(shap_abs)] if len(FEATURE_NAMES) >= len(shap_abs) else \
                 [f"feat_{i}" for i in range(len(shap_abs))]
    shap_df = pd.DataFrame({"Feature": feat_names, "SHAP_abs_mean": shap_abs})
    shap_df = shap_df.sort_values("SHAP_abs_mean", ascending=False)
    shap_df.to_csv(os.path.join(ANALYSIS_DIR, "shap_best.csv"), index=False)

    fig, ax = plt.subplots(figsize=(10, max(8, len(shap_df) * 0.3)))
    shap_sorted = shap_df.sort_values("SHAP_abs_mean", ascending=True)
    ax.barh(shap_sorted["Feature"], shap_sorted["SHAP_abs_mean"],
            color="darkorange", edgecolor="black")
    ax.set_xlabel("Mean |SHAP value|")
    ax.set_title(f"SHAP Feature Importance — {sk_best}")
    ax.grid(True, alpha=0.3, axis="x")
    plt.tight_layout()
    _save_fig(fig, "shap_best")
    print(f"  -> shap_best.csv, shap_best.png/pdf")
    del mdl_sk


# ============================================================
# 10. TRAINING CURVES (top-5 DL)
# ============================================================
def _s10_training_curves():
    # Select top-5 DL models
    dl_models = [nm for nm in TOP_20
                 if nm.startswith("MLP_") and "Classifier" not in nm
                 and os.path.exists(os.path.join(CURVES_DIR, f"{nm}.csv"))][:5]
    if not dl_models:
        print("  DL training curves yok"); return

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    cmap = plt.cm.tab10
    for i, nm in enumerate(dl_models):
        cp = os.path.join(CURVES_DIR, f"{nm}.csv")
        try:
            c = pd.read_csv(cp)
            color = cmap(i % 10)
            axes[0].plot(c["epoch"], c["train_loss"], color=color, alpha=0.8,
                         label=nm[:25], linewidth=1.5)
            axes[1].plot(c["epoch"], c["val_loss"], color=color, alpha=0.8,
                         label=nm[:25], linewidth=1.5)
        except:
            pass

    axes[0].set_title("Training Loss (Top-5 DL)"); axes[0].set_xlabel("Epoch")
    axes[0].set_ylabel("Loss"); axes[0].set_yscale("log")
    axes[1].set_title("Validation Loss (Top-5 DL)"); axes[1].set_xlabel("Epoch")
    axes[1].set_ylabel("Loss"); axes[1].set_yscale("log")
    axes[0].legend(fontsize=7); axes[1].legend(fontsize=7)
    axes[0].grid(True, alpha=0.3); axes[1].grid(True, alpha=0.3)
    plt.tight_layout()
    _save_fig(fig, "training_curves")
    print(f"  -> training_curves.png/pdf")


# ============================================================
# 11. BOOTSTRAP CI (top-10)
# ============================================================
def _s11_bootstrap_ci():
    ci_path = os.path.join(MODELS_DIR, "bootstrap_ci.csv")
    if os.path.exists(ci_path):
        ci_df = pd.read_csv(ci_path)
    else:
        # Compute bootstrap CI
        print("  bootstrap_ci.csv yok, hesaplaniyor...")
        n_boot = 1000
        ci_rows = []
        for nm in TOP_10:
            if nm not in all_test_probs: continue
            probs = all_test_probs[nm]
            preds = probs.argmax(axis=1)
            n_samples = len(y_test)
            boot_accs = []
            rng = np.random.RandomState(SEED)
            for _ in range(n_boot):
                idx_b = rng.choice(n_samples, n_samples, replace=True)
                boot_accs.append(accuracy_score(y_test[idx_b], preds[idx_b]))
            boot_accs = np.array(boot_accs)
            ci_rows.append({
                "Model": nm,
                "Accuracy_mean": np.mean(boot_accs),
                "Accuracy_std": np.std(boot_accs),
                "CI_lower_2.5": np.percentile(boot_accs, 2.5),
                "CI_upper_97.5": np.percentile(boot_accs, 97.5),
            })
        ci_df = pd.DataFrame(ci_rows)

    if ci_df.empty:
        print("  Bootstrap CI bos"); return

    ci_df = ci_df.head(10).sort_values("Accuracy_mean", ascending=True).reset_index(drop=True)

    fig, ax = plt.subplots(figsize=(10, 6))
    y_pos = np.arange(len(ci_df))
    means = ci_df["Accuracy_mean"].values
    lo = means - ci_df["CI_lower_2.5"].values
    hi = ci_df["CI_upper_97.5"].values - means

    ax.barh(y_pos, means, xerr=[lo, hi], color="steelblue", edgecolor="black",
            capsize=4, ecolor="black")
    ax.set_yticks(y_pos)
    ax.set_yticklabels(ci_df["Model"], fontsize=9)
    ax.set_xlabel("Accuracy")
    ax.set_title("Bootstrap 95% CI — Top-10 Models")
    ax.grid(True, alpha=0.3, axis="x")

    for i, (m, lo_v, hi_v) in enumerate(zip(means, ci_df["CI_lower_2.5"], ci_df["CI_upper_97.5"])):
        ax.text(hi_v + 0.002, i, f"{m:.4f} [{lo_v:.4f}, {hi_v:.4f}]",
                va="center", fontsize=7)

    plt.tight_layout()
    _save_fig(fig, "bootstrap_ci")
    print(f"  -> bootstrap_ci.png/pdf")


# ============================================================
# 12. MISCLASSIFICATION ANALYSIS
# ============================================================
def _s12_misclassification():
    if BEST not in all_test_probs:
        print("  Best model yok"); return

    probs = all_test_probs[BEST]
    preds = probs.argmax(axis=1)
    cm = confusion_matrix(y_test, preds)

    # Extract top confused pairs (off-diagonal)
    pairs = []
    for i in range(n_classes):
        for j in range(n_classes):
            if i == j: continue
            if cm[i, j] > 0:
                pairs.append({
                    "True_Class": disease_names[i],
                    "Predicted_Class": disease_names[j],
                    "Count": int(cm[i, j]),
                    "True_Total": int(cm[i, :].sum()),
                    "Error_Rate": float(cm[i, j] / cm[i, :].sum()),
                })
    pairs_df = pd.DataFrame(pairs).sort_values("Count", ascending=False)
    top10_pairs = pairs_df.head(10)
    pairs_df.to_csv(os.path.join(ANALYSIS_DIR, "misclassification_pairs.csv"), index=False)

    # Bar chart of top-10 confused pairs
    fig, ax = plt.subplots(figsize=(12, 6))
    pair_labels = [f"{r['True_Class']}\n-> {r['Predicted_Class']}"
                   for _, r in top10_pairs.iterrows()]
    bars = ax.bar(range(len(top10_pairs)), top10_pairs["Count"],
                  color="crimson", edgecolor="black")
    ax.set_xticks(range(len(top10_pairs)))
    ax.set_xticklabels(pair_labels, rotation=45, ha="right", fontsize=8)
    ax.set_ylabel("Misclassification Count")
    ax.set_title(f"Top-10 Most Confused Disease Pairs — {BEST}")
    ax.grid(True, alpha=0.3, axis="y")

    for bar, val in zip(bars, top10_pairs["Count"]):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.3,
                str(val), ha="center", fontsize=9)

    plt.tight_layout()
    _save_fig(fig, "misclassification_pairs")
    print(f"  -> misclassification_pairs.csv, misclassification_pairs.png/pdf")


# ============================================================
# 13. STATISTICAL TESTS (Friedman + Wilcoxon)
# ============================================================
def _s13_statistical_tests():
    # Per-sample correctness (1/0) for each model
    test_models = [m for m in TOP_10 if m in all_test_probs]
    if len(test_models) < 3:
        print("  Yeterli model yok (<3)"); return

    correct_dict = {}
    for nm in test_models:
        probs = all_test_probs[nm]
        preds = probs.argmax(axis=1)
        correct_dict[nm] = (preds == y_test).astype(int)

    correct_matrix = np.array([correct_dict[nm] for nm in test_models])

    # --- Friedman test ---
    try:
        f_stat, f_p = stats.friedmanchisquare(*[correct_dict[nm] for nm in test_models])
        print(f"  Friedman chi-square: stat={f_stat:.4f}, p={f_p:.2e}")
    except Exception as e:
        f_stat, f_p = float("nan"), float("nan")
        print(f"  Friedman HATA: {e}")

    with open(os.path.join(ANALYSIS_DIR, "friedman_summary.txt"), "w") as f:
        f.write(f"Friedman chi-square test (per-sample correctness)\n")
        f.write(f"  Statistic: {f_stat}\n  p-value: {f_p}\n")
        f.write(f"  N models: {len(test_models)}\n  N samples: {len(y_test)}\n\n")
        f.write(f"Models tested:\n")
        for nm in test_models:
            acc = correct_dict[nm].mean()
            f.write(f"  {nm:35s}: acc={acc:.4f}\n")

    # --- Pairwise Wilcoxon + Bonferroni (top-5) ---
    top5_models = [m for m in TOP_5 if m in correct_dict]
    wilcox_rows = []
    n_pairs = len(top5_models) * (len(top5_models) - 1) // 2
    alpha_bonf = 0.05 / max(n_pairs, 1)

    for i in range(len(top5_models)):
        for j in range(i + 1, len(top5_models)):
            n1, n2 = top5_models[i], top5_models[j]
            try:
                w_stat, w_p = stats.wilcoxon(correct_dict[n1], correct_dict[n2])
            except:
                w_stat, w_p = float("nan"), float("nan")

            e1, e2 = correct_dict[n1].astype(float), correct_dict[n2].astype(float)
            pooled_std = np.sqrt((np.var(e1) + np.var(e2)) / 2.0)
            cohens_d = (np.mean(e1) - np.mean(e2)) / pooled_std if pooled_std > 0 else 0.0

            wilcox_rows.append({
                "Model_1": n1, "Model_2": n2,
                "W_stat": w_stat, "p_raw": w_p,
                "p_bonferroni": min(w_p * n_pairs, 1.0) if not np.isnan(w_p) else float("nan"),
                "sig_raw": "YES" if not np.isnan(w_p) and w_p < 0.05 else "no",
                "sig_bonf": "YES" if not np.isnan(w_p) and w_p < alpha_bonf else "no",
                "Cohens_d": cohens_d,
                "Effect": ("large" if abs(cohens_d) >= 0.8 else
                           "medium" if abs(cohens_d) >= 0.5 else
                           "small" if abs(cohens_d) >= 0.2 else "negligible"),
            })

    pd.DataFrame(wilcox_rows).to_csv(
        os.path.join(ANALYSIS_DIR, "wilcoxon_pairwise.csv"), index=False)
    print(f"  -> friedman_summary.txt, wilcoxon_pairwise.csv")


# ============================================================
# 14. CALIBRATION (top-3)
# ============================================================
def _s14_calibration():
    fig, ax = plt.subplots(figsize=(8, 8))
    ax.plot([0, 1], [0, 1], "k:", linewidth=1, label="Perfectly calibrated")

    colors = ["#e74c3c", "#3498db", "#2ecc71"]
    for idx, nm in enumerate(TOP_3):
        if nm not in all_test_probs: continue
        probs = all_test_probs[nm]
        preds = probs.argmax(axis=1)

        # For multiclass: use max probability as confidence
        confidences = probs.max(axis=1)
        correctness = (preds == y_test).astype(int)

        try:
            prob_true, prob_pred = calibration_curve(correctness, confidences,
                                                     n_bins=15, strategy="uniform")
            ax.plot(prob_pred, prob_true, f"-o", color=colors[idx],
                    label=f"{nm[:30]}", linewidth=1.5, markersize=4)
        except Exception as e:
            print(f"  {nm} calibration HATA: {str(e)[:60]}")

    ax.set_xlabel("Mean Predicted Confidence")
    ax.set_ylabel("Fraction of Correct Predictions")
    ax.set_title("Calibration (Reliability Diagram) — Top-3 Models")
    ax.legend(fontsize=8, loc="lower right")
    ax.grid(True, alpha=0.3)
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    plt.tight_layout()
    _save_fig(fig, "calibration")
    print(f"  -> calibration.png/pdf")


# ============================================================
# 15. LATEX TABLES
# ============================================================
def _df_to_latex(df_in, caption, label, cols=None, fmt=None):
    if cols is None: cols = df_in.columns.tolist()
    sub = df_in[cols].copy()
    if fmt:
        for c, f in fmt.items():
            if c in sub.columns:
                sub[c] = sub[c].apply(lambda x: f.format(x) if pd.notnull(x) else "-")
    lines = [
        "\\begin{table}[htbp]", "\\centering",
        f"\\caption{{{caption}}}", f"\\label{{{label}}}",
        "\\resizebox{\\textwidth}{!}{%",
        "\\begin{tabular}{l" + "c" * (len(cols) - 1) + "}",
        "\\toprule",
        " & ".join(c.replace("_", "\\_") for c in cols) + " \\\\",
        "\\midrule",
    ]
    for _, row in sub.iterrows():
        lines.append(" & ".join(str(row[c]).replace("_", "\\_") for c in cols) + " \\\\")
    lines += ["\\bottomrule", "\\end{tabular}%", "}", "\\end{table}"]
    return "\n".join(lines)


def _s15_latex():
    # Table 1: Top-20 model comparison
    tbl1_cols = ["Model", "Accuracy", "F1_macro", "ROC_AUC_macro", "Balanced_Accuracy",
                 "Precision_macro", "Recall_macro", "Cohen_Kappa", "MCC",
                 "Log_Loss", "Train_Time(s)", "Params"]
    tbl1_fmt = {"Accuracy": "{:.4f}", "F1_macro": "{:.4f}", "ROC_AUC_macro": "{:.4f}",
                "Balanced_Accuracy": "{:.4f}", "Precision_macro": "{:.4f}",
                "Recall_macro": "{:.4f}", "Cohen_Kappa": "{:.4f}", "MCC": "{:.4f}",
                "Log_Loss": "{:.4f}", "Train_Time(s)": "{:.1f}", "Params": "{:,.0f}"}
    top20_tbl = results_df.head(20)[[c for c in tbl1_cols if c in results_df.columns]]
    with open(os.path.join(LATEX_DIR, "table1_main.tex"), "w") as f:
        f.write(_df_to_latex(top20_tbl,
                             "Top-20 models by Accuracy for cat disease classification",
                             "tab:top20", top20_tbl.columns.tolist(), tbl1_fmt))

    # Table 2: Per-class F1 for best model
    pc_path = os.path.join(MODELS_DIR, "per_class_metrics.csv")
    if os.path.exists(pc_path):
        pc_df = pd.read_csv(pc_path)
        best_pc = pc_df[pc_df["Model"] == BEST].copy()
        if not best_pc.empty:
            tbl2_cols = ["Class_Name", "Precision", "Recall", "F1", "Support"]
            tbl2_fmt = {"Precision": "{:.4f}", "Recall": "{:.4f}", "F1": "{:.4f}",
                        "Support": "{:.0f}"}
            with open(os.path.join(LATEX_DIR, "table2_perclass.tex"), "w") as f:
                f.write(_df_to_latex(best_pc,
                                     f"Per-class metrics for best model ({BEST})",
                                     "tab:perclass", tbl2_cols, tbl2_fmt))

    # Table 3: Sklearn comparison
    sk_df = results_df[results_df["Model"].isin(SK_LIST)].copy()
    if not sk_df.empty:
        tbl3_cols = ["Model", "Accuracy", "F1_macro", "Balanced_Accuracy",
                     "Cohen_Kappa", "MCC", "Log_Loss", "Train_Time(s)"]
        tbl3_fmt = {"Accuracy": "{:.4f}", "F1_macro": "{:.4f}",
                    "Balanced_Accuracy": "{:.4f}", "Cohen_Kappa": "{:.4f}",
                    "MCC": "{:.4f}", "Log_Loss": "{:.4f}", "Train_Time(s)": "{:.1f}"}
        sk_tbl = sk_df[[c for c in tbl3_cols if c in sk_df.columns]]
        with open(os.path.join(LATEX_DIR, "table3_sklearn.tex"), "w") as f:
            f.write(_df_to_latex(sk_tbl,
                                 "Sklearn model comparison for cat disease classification",
                                 "tab:sklearn", sk_tbl.columns.tolist(), tbl3_fmt))

    # Table 4: Statistical tests summary
    wilc_path = os.path.join(ANALYSIS_DIR, "wilcoxon_pairwise.csv")
    if os.path.exists(wilc_path) and os.path.getsize(wilc_path) > 10:
        wilc = pd.read_csv(wilc_path)
        w_cols = ["Model_1", "Model_2", "p_raw", "p_bonferroni",
                  "sig_bonf", "Cohens_d", "Effect"]
        w_fmt = {"p_raw": "{:.3e}", "p_bonferroni": "{:.3e}", "Cohens_d": "{:.3f}"}
        w_tbl = wilc[[c for c in w_cols if c in wilc.columns]]
        with open(os.path.join(LATEX_DIR, "table4_stats.tex"), "w") as f:
            f.write(_df_to_latex(w_tbl,
                                 "Pairwise Wilcoxon signed-rank test with Bonferroni correction",
                                 "tab:wilcoxon", w_tbl.columns.tolist(), w_fmt))

    # Also include Friedman summary if available
    friedman_path = os.path.join(ANALYSIS_DIR, "friedman_summary.txt")
    if os.path.exists(friedman_path):
        with open(friedman_path) as f:
            friedman_text = f.read()
        # Append to table4
        tex_path = os.path.join(LATEX_DIR, "table4_stats.tex")
        with open(tex_path, "a") as f:
            f.write("\n\n% Friedman test summary:\n")
            for line in friedman_text.strip().split("\n"):
                f.write(f"% {line}\n")

    print(f"  -> {LATEX_DIR}/table1_main.tex through table4_stats.tex")


# ============================================================
# MAIN RUNNER — all sections with skip + try/except
# ============================================================
SECTIONS = [
    (1, "CONFUSION MATRIX HEATMAP (top-1 model)",
     [os.path.join(FIGURES_DIR, "confusion_matrix_best.png"),
      os.path.join(FIGURES_DIR, "confusion_matrix_best_normalized.png")],
     _s1_confusion_matrix),

    (2, "PER-CLASS PERFORMANCE BAR CHART",
     [os.path.join(FIGURES_DIR, "per_class_performance.png")],
     _s2_per_class),

    (3, "MODEL COMPARISON BAR CHART (top-20)",
     [os.path.join(FIGURES_DIR, "top20_bar.png")],
     _s3_top20_bar),

    (4, "ROC CURVES (top-3, one-vs-rest)",
     [os.path.join(FIGURES_DIR, "roc_curves_top3.png")],
     _s4_roc_curves),

    (5, "RAW vs NORMAL vs DIAMOND COMPARISON",
     [os.path.join(FIGURES_DIR, "variant_comparison.png")],
     _s5_variant_comparison),

    (6, "SIZE EFFECT (Small -> XXL)",
     [os.path.join(FIGURES_DIR, "size_effect.png")],
     _s6_size_effect),

    (7, "SKLEARN MODEL COMPARISON",
     [os.path.join(FIGURES_DIR, "sklearn_comparison.png")],
     _s7_sklearn_comparison),

    (8, "FEATURE IMPORTANCE (top sklearn)",
     [os.path.join(ANALYSIS_DIR, "feature_importance.csv"),
      os.path.join(FIGURES_DIR, "feature_importance.png")],
     _s8_feature_importance),

    (9, "SHAP (top-1 sklearn, 500 samples)",
     [os.path.join(ANALYSIS_DIR, "shap_best.csv"),
      os.path.join(FIGURES_DIR, "shap_best.png")],
     _s9_shap),

    (10, "TRAINING CURVES (top-5 DL)",
     [os.path.join(FIGURES_DIR, "training_curves.png")],
     _s10_training_curves),

    (11, "BOOTSTRAP CI (top-10)",
     [os.path.join(FIGURES_DIR, "bootstrap_ci.png")],
     _s11_bootstrap_ci),

    (12, "MISCLASSIFICATION ANALYSIS",
     [os.path.join(ANALYSIS_DIR, "misclassification_pairs.csv"),
      os.path.join(FIGURES_DIR, "misclassification_pairs.png")],
     _s12_misclassification),

    (13, "STATISTICAL TESTS (Friedman + Wilcoxon)",
     [os.path.join(ANALYSIS_DIR, "friedman_summary.txt"),
      os.path.join(ANALYSIS_DIR, "wilcoxon_pairwise.csv")],
     _s13_statistical_tests),

    (14, "CALIBRATION (top-3)",
     [os.path.join(FIGURES_DIR, "calibration.png")],
     _s14_calibration),

    (15, "LATEX TABLES (4 tablo)",
     [os.path.join(LATEX_DIR, "table1_main.tex"),
      os.path.join(LATEX_DIR, "table3_sklearn.tex"),
      os.path.join(LATEX_DIR, "table4_stats.tex")],
     _s15_latex),
]

for sec_id, name, outputs, func in SECTIONS:
    run_section(sec_id, name, outputs, func)


# ============================================================
# FINAL SUMMARY
# ============================================================
print(f"\n\n{'='*80}\nTUM ANALIZ OZETI\n{'='*80}")
n_ok = sum(1 for _, _, s in _SECTION_STATUS if s == "OK")
n_skip = sum(1 for _, _, s in _SECTION_STATUS if s == "SKIP")
n_fail = sum(1 for _, _, s in _SECTION_STATUS if s.startswith("FAIL"))
print(f"  Basarili: {n_ok} | Atlanan: {n_skip} | Basarisiz: {n_fail}")
print()
for sid, nm, st in _SECTION_STATUS:
    icon = "OK  " if st == "OK" else ("SKIP" if st == "SKIP" else "FAIL")
    print(f"  [{icon}] [{sid:2d}] {nm}")
print()
print(f"Figurler:    {FIGURES_DIR}")
print(f"CSV/TXT:     {ANALYSIS_DIR}")
print(f"LaTeX:       {LATEX_DIR}")
print("=" * 80)

# Save status as JSON
status_path = os.path.join(ANALYSIS_DIR, "section_status.json")
with open(status_path, "w") as f:
    json.dump({"ok": n_ok, "skip": n_skip, "fail": n_fail,
               "sections": [{"id": s[0], "name": s[1], "status": s[2]}
                            for s in _SECTION_STATUS]}, f, indent=2)

# Exit code: 0 if all OK or SKIP, 1 if any FAIL
sys.exit(0 if n_fail == 0 else 1)
