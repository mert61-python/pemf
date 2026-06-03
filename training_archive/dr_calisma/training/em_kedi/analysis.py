#!/usr/bin/env python3
"""
analysis_kedi.py — Post-Training Analizleri (SCI Makale)
==========================================================
training_kedi.py'yi calistirdiktan sonra bu script'i calistir.

Veri kaynaklari:
  - models_em_kedi/predictions.npz       (tum tahminler, labellar)
  - models_em_kedi/model_kedi_karsilastirma.csv  (metrikler)
  - models_em_kedi/training_curves/*.csv (loss egrileri)
  - models_em_kedi/pareto_data.csv       (complexity vs performance)
  - models_em_kedi/*.pt, *.pkl           (modeller - noise/perm importance icin)

Uretilen analizler:
  1. Istatistiksel: Friedman, Nemenyi, Wilcoxon, Bonferroni, Cohen's d
  2. Critical Difference diagram (figur)
  3. Residual: Q-Q, histogram, Shapiro-Wilk, Breusch-Pagan, Durbin-Watson
  4. Permutation Importance (top-10)
  5. SHAP (top-1, 500 sample)
  6. Calibration (prediction interval coverage)
  7. Ensemble diversity (pred korelasyon matrisi)
  8. Spatial 3D error heatmap
  9. Per-organ radar chart
 10. Pareto frontier plots
 11. Model comparison bar chart
 12. Family-wise box plot
 13. Per-output R² heatmap
 14. Training curves overlay
 15. Scatter pred vs true
 16. UMAP/TSNE embedding (penultimate layer)
 17. Partial Dependence Plots
 18. Worst-case error analysis
 19. Phase wrapping / Von Mises fit
 20. LaTeX tables
"""

import os, sys, json, time, warnings
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import seaborn as sns
from sklearn.metrics import r2_score, mean_absolute_error
from scipy import stats
from scipy.stats import spearmanr, pearsonr, shapiro, norm
from tabulate import tabulate
import joblib

warnings.filterwarnings("ignore")
plt.rcParams["figure.dpi"] = 100
plt.rcParams["savefig.dpi"] = 200
plt.rcParams["font.size"] = 10
sns.set_style("whitegrid")

# ============================================================
# CONFIG
# ============================================================
MODELS_DIR = "/home/user02/dr/models/models_em_kedi"
FIGURES_DIR = os.path.join(MODELS_DIR, "figures")
ANALYSIS_DIR = os.path.join(MODELS_DIR, "analysis")
LATEX_DIR = os.path.join(MODELS_DIR, "latex")
os.makedirs(FIGURES_DIR, exist_ok=True)
os.makedirs(ANALYSIS_DIR, exist_ok=True)
os.makedirs(LATEX_DIR, exist_ok=True)

DEVICE = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
SEED = 42
ORGAN_IDS = [0, 1, 2, 3, 4, 5, 6]
FEATURE_NAMES = ["x", "y", "z"] + [f"organ_{o}" for o in ORGAN_IDS] + [f"B_coil{i+1}" for i in range(7)]
IN_DIM = 17   # x,y,z + 7 organ one-hot + 7 per-coil B
OUT_DIM = 22  # D1-7 + sin(P1-7) + cos(P1-7) + E

np.random.seed(SEED)

print("=" * 80)
print("ANALYSIS_KEDI.PY — SCI Makale Post-Analizleri")
print("=" * 80)

# ============================================================
# Load predictions + results
# ============================================================
print("\n[LOAD] predictions.npz + model_kedi_karsilastirma.csv ...")
PRED_PATH = os.path.join(MODELS_DIR, "predictions.npz")
CSV_PATH = os.path.join(MODELS_DIR, "model_kedi_karsilastirma.csv")

if not os.path.exists(PRED_PATH):
    print(f"HATA: {PRED_PATH} bulunamadi. Once training_kedi.py'yi calistir.")
    sys.exit(1)

preds_npz = np.load(PRED_PATH)
results_df = pd.read_csv(CSV_PATH)

y_d_test = preds_npz["y_d_test"]
yp_test_deg = preds_npz["yp_test_deg"]
y_e_test = preds_npz["y_e_test"]
y_d_val = preds_npz["y_d_val"]
yp_val_deg = preds_npz["yp_val_deg"]
y_e_val = preds_npz["y_e_val"]
X_test_sc = preds_npz["X_test_sc"]
X_val_sc = preds_npz["X_val_sc"]
X_train_sc = preds_npz["X_train_sc"]
y_train_sc = preds_npz["y_train_sc"]
test_organ_ids = preds_npz["test_organ_ids"]

# Extract per-model predictions
# 22-dim (D7+sinP7+cosP7+E1) -> 15-dim (D7+P_deg7+E1) donusumu
def _convert_22_to_15(pred_22):
    """22-dim sin/cos phase-diff output → 15-dim absolute derece.
    Layout: D(7) + sin(P1,ΔP2-7)(7) + cos(P1,ΔP2-7)(7) + E(1)
    → D(7) + P_absolute_deg(7) + E(1)"""
    if pred_22.shape[1] == 15:
        return pred_22  # zaten eski format
    d = pred_22[:, :7]
    sin_p = pred_22[:, 7:14]
    cos_p = pred_22[:, 14:21]
    # atan2 → P1, ΔP2, ..., ΔP7
    p_angles = np.rad2deg(np.arctan2(sin_p, cos_p))
    # Phase diff → absolute: P_i = P1 + ΔP_i
    p1_ref = p_angles[:, 0:1]
    p_diffs = p_angles[:, 1:]
    p_absolute = np.column_stack([p1_ref, p1_ref + p_diffs])
    p_deg = p_absolute % 360.0
    e = pred_22[:, 21:22]
    return np.column_stack([d, p_deg, e])

all_test_preds = {}
all_val_preds = {}
for k in preds_npz.files:
    if k.endswith("__test"):
        all_test_preds[k[:-6]] = _convert_22_to_15(preds_npz[k])
    elif k.endswith("__val"):
        all_val_preds[k[:-5]] = _convert_22_to_15(preds_npz[k])

print(f"  {len(all_test_preds)} modelin tahminleri yuklendi (22->15 donusumu yapildi)")
print(f"  Test: {len(y_d_test)} satir | Val: {len(y_d_val)} satir")
print(f"  CSV: {len(results_df)} kayit")

# Sort by Combined_R2
results_df["Combined_R2"] = pd.to_numeric(results_df["Combined_R2"], errors="coerce")
results_df = results_df.dropna(subset=["Combined_R2"]).sort_values(
    "Combined_R2", ascending=False).reset_index(drop=True)

TOP_20 = results_df["Model"].head(20).tolist()
TOP_10 = results_df["Model"].head(10).tolist()
TOP_5 = results_df["Model"].head(5).tolist()
TOP_3 = results_df["Model"].head(3).tolist()
BEST = results_df["Model"].iloc[0] if len(results_df) else None
print(f"  Best: {BEST}")
print(f"  Top-5: {TOP_5}")

# ============================================================
# Helpers
# ============================================================
def circ_diff(yt, yp):
    d = yp - yt; return d - 360.0 * np.round(d / 360.0)

def circ_r2(yt, yp):
    ss_res = np.sum(circ_diff(yt, yp)**2)
    rad = np.deg2rad(yt)
    cm = np.rad2deg(np.arctan2(np.mean(np.sin(rad), 0), np.mean(np.cos(rad), 0))) % 360
    ss_tot = np.sum(circ_diff(yt, np.broadcast_to(cm, yt.shape))**2)
    return 1.0 - ss_res/ss_tot if ss_tot > 0 else 0.0

def extract_dpe(pred_22):
    """22-dim output'tan D(7), P_deg(7), E(1) cikar.
    Layout: D(0:7) + sin(P)(7:14) + cos(P)(14:21) + E(21)
    """
    d = pred_22[:, :7]
    sin_p = pred_22[:, 7:14]
    cos_p = pred_22[:, 14:21]
    p_deg = np.rad2deg(np.arctan2(sin_p, cos_p)) % 360.0
    e = pred_22[:, 21] if pred_22.shape[1] > 21 else pred_22[:, -1]
    return d, p_deg, e

def get_errors(model_name):
    """Return per-sample combined squared error for a model."""
    p = all_test_preds[model_name]
    d_pred, p_pred_deg, e_pred = extract_dpe(p)
    d_err = np.mean((y_d_test - d_pred)**2, axis=1)
    p_err_raw = circ_diff(yp_test_deg, p_pred_deg)
    p_err = np.mean(p_err_raw**2, axis=1)
    e_err = (y_e_test - e_pred)**2
    d_err_n = d_err / (np.max(d_err) + 1e-12)
    p_err_n = p_err / (np.max(p_err) + 1e-12)
    e_err_n = e_err / (np.max(e_err) + 1e-12)
    return (d_err_n + p_err_n + e_err_n) / 3.0


# ============================================================
# Section runner with skip + try/except
# ============================================================
_SECTION_STATUS = []  # Track outcome of each section

def run_section(sec_id, name, outputs, func):
    """Run an analysis section safely with skip + error handling.

    - sec_id:  integer section number
    - name:    human-readable name
    - outputs: list of output files; if ALL exist, section is skipped
    - func:    callable that runs the analysis
    """
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

# Shared state between sections (populated by _s1)
_shared = {}

def nemenyi_critical_difference(n_models, n_samples, alpha=0.05):
    """CD = q_alpha * sqrt(k(k+1)/(6N))"""
    q_alpha_005 = {2:1.960, 3:2.343, 4:2.569, 5:2.728, 6:2.850, 7:2.949, 8:3.031,
                   9:3.102, 10:3.164, 11:3.219, 12:3.268, 15:3.391, 20:3.532}
    q = q_alpha_005.get(n_models, 3.164)
    return q * np.sqrt(n_models * (n_models + 1) / (6.0 * n_samples))


# ============================================================
# 1. STATISTICAL TESTS
# ============================================================
def _s1_stats():
    n_for_test = 10
    test_models = [m for m in TOP_20[:n_for_test] if m in all_test_preds]
    print(f"  Test modelleri: {test_models}")

    errors_dict = {nm: get_errors(nm) for nm in test_models}
    errs_matrix = np.array([errors_dict[nm] for nm in test_models])

    # --- Friedman ---
    try:
        f_stat, f_p = stats.friedmanchisquare(*[errors_dict[nm] for nm in test_models])
        print(f"  Friedman chi-square: stat={f_stat:.4f}, p={f_p:.2e}")
    except Exception as e:
        f_stat, f_p = float("nan"), float("nan")
        print(f"  Friedman HATA: {e}")

    # --- Nemenyi post-hoc ---
    ranks = np.argsort(np.argsort(errs_matrix, axis=0), axis=0) + 1
    avg_ranks = ranks.mean(axis=1)
    cd = nemenyi_critical_difference(len(test_models), errs_matrix.shape[1])
    print(f"  Nemenyi CD (alpha=0.05): {cd:.4f}")
    rank_rows = sorted(zip(test_models, avg_ranks), key=lambda x: x[1])
    for nm, ar in rank_rows:
        print(f"    {nm:30s}: {ar:.3f}")

    nemenyi_rows = []
    for i in range(len(test_models)):
        for j in range(i+1, len(test_models)):
            diff = abs(avg_ranks[i] - avg_ranks[j])
            nemenyi_rows.append({"Model_1": test_models[i], "Model_2": test_models[j],
                                 "Rank_Diff": diff, "CD": cd,
                                 "Significant": "YES" if diff > cd else "no"})
    pd.DataFrame(nemenyi_rows).to_csv(
        os.path.join(ANALYSIS_DIR, "nemenyi_pairwise.csv"), index=False)

    # --- Wilcoxon + Bonferroni + Cohen's d ---
    wilcox_rows = []
    n_pairs = len(test_models) * (len(test_models) - 1) // 2
    alpha_raw, alpha_bonf = 0.05, 0.05 / n_pairs
    for i in range(len(test_models)):
        for j in range(i+1, len(test_models)):
            n1, n2 = test_models[i], test_models[j]
            try: w_stat, w_p = stats.wilcoxon(errors_dict[n1], errors_dict[n2])
            except: w_stat, w_p = float("nan"), float("nan")
            e1, e2 = errors_dict[n1], errors_dict[n2]
            pooled_std = np.sqrt((np.var(e1) + np.var(e2)) / 2.0)
            cohens_d = (np.mean(e1) - np.mean(e2)) / pooled_std if pooled_std > 0 else 0.0
            wilcox_rows.append({
                "Model_1": n1, "Model_2": n2, "W_stat": w_stat, "p_raw": w_p,
                "p_bonferroni": min(w_p * n_pairs, 1.0) if not np.isnan(w_p) else float("nan"),
                "sig_raw": "YES" if not np.isnan(w_p) and w_p < alpha_raw else "no",
                "sig_bonf": "YES" if not np.isnan(w_p) and w_p < alpha_bonf else "no",
                "Cohens_d": cohens_d,
                "Effect": ("large" if abs(cohens_d) >= 0.8 else
                           "medium" if abs(cohens_d) >= 0.5 else
                           "small" if abs(cohens_d) >= 0.2 else "negligible"),
            })
    pd.DataFrame(wilcox_rows).to_csv(
        os.path.join(ANALYSIS_DIR, "wilcoxon_bonferroni.csv"), index=False)

    with open(os.path.join(ANALYSIS_DIR, "friedman_summary.txt"), "w") as f:
        f.write(f"Friedman chi-square test\n")
        f.write(f"  Statistic: {f_stat}\n  p-value: {f_p}\n")
        f.write(f"  N models: {len(test_models)}\n  N samples: {errs_matrix.shape[1]}\n\n")
        f.write(f"Nemenyi CD (alpha=0.05): {cd:.4f}\n\nAverage ranks:\n")
        for nm, ar in rank_rows:
            f.write(f"  {nm:30s}: {ar:.4f}\n")

    _shared["test_models"] = test_models
    _shared["avg_ranks"] = avg_ranks
    _shared["cd"] = cd


# ============================================================
# 2. CRITICAL DIFFERENCE DIAGRAM
# ============================================================
def _plot_cd_diagram(models, ranks, cd, save_path):
    n = len(models)
    sorted_idx = np.argsort(ranks)
    sorted_models = [models[i] for i in sorted_idx]
    sorted_ranks = [ranks[i] for i in sorted_idx]

    fig, ax = plt.subplots(figsize=(12, max(3, n * 0.4 + 1)))
    ax.set_xlim(0.5, n + 0.5)
    ax.set_ylim(-n/2 - 1, 2)
    ax.invert_yaxis()

    for i in range(1, n + 1):
        ax.plot([i, i], [0, -0.2], "k-", linewidth=0.8)
        ax.text(i, -0.35, str(i), ha="center", fontsize=9)
    ax.plot([0.5, n + 0.5], [0, 0], "k-", linewidth=1.5)
    ax.text((n + 1) / 2, -0.8, "Average Rank (lower is better)", ha="center", fontsize=10)

    ax.plot([1, 1 + cd], [0.5, 0.5], "k-", linewidth=2)
    ax.plot([1, 1], [0.4, 0.6], "k-", linewidth=1.5)
    ax.plot([1 + cd, 1 + cd], [0.4, 0.6], "k-", linewidth=1.5)
    ax.text(1 + cd/2, 0.9, f"CD = {cd:.3f}", ha="center", fontsize=9)

    half = (n + 1) // 2
    for i, (mname, r) in enumerate(zip(sorted_models, sorted_ranks)):
        side = "left" if i < half else "right"
        y = -(i + 1) if i < half else -(n - i)
        if side == "left":
            ax.plot([r, 0.7, 0.7], [0, 0, y], "k-", linewidth=0.8)
            ax.text(0.65, y, f"{mname} ({r:.2f})", ha="right", va="center", fontsize=8)
        else:
            ax.plot([r, n + 0.3, n + 0.3], [0, 0, y], "k-", linewidth=0.8)
            ax.text(n + 0.35, y, f"{mname} ({r:.2f})", ha="left", va="center", fontsize=8)

    non_sig_groups = []
    used = set()
    for i in range(n):
        if i in used: continue
        grp = [i]
        for j in range(i+1, n):
            if abs(sorted_ranks[i] - sorted_ranks[j]) <= cd:
                grp.append(j)
        if len(grp) > 1:
            non_sig_groups.append(grp)
            used.update(grp)

    for gi, grp in enumerate(non_sig_groups):
        r_min = min(sorted_ranks[i] for i in grp)
        r_max = max(sorted_ranks[i] for i in grp)
        y_bar = 1.5 + gi * 0.2
        ax.plot([r_min - 0.05, r_max + 0.05], [y_bar, y_bar], "k-", linewidth=3)

    ax.set_axis_off()
    ax.set_title(f"Critical Difference Diagram (Nemenyi, α=0.05)")
    plt.tight_layout()
    plt.savefig(save_path, bbox_inches="tight")
    plt.close()

def _s2_cd_diagram():
    if "test_models" not in _shared:
        # Reconstruct if s1 was skipped
        test_models = [m for m in TOP_20[:10] if m in all_test_preds]
        errs = np.array([get_errors(nm) for nm in test_models])
        ranks = np.argsort(np.argsort(errs, axis=0), axis=0) + 1
        _shared["test_models"] = test_models
        _shared["avg_ranks"] = ranks.mean(axis=1)
        _shared["cd"] = nemenyi_critical_difference(len(test_models), errs.shape[1])
    _plot_cd_diagram(_shared["test_models"], _shared["avg_ranks"], _shared["cd"],
                     os.path.join(FIGURES_DIR, "critical_difference.png"))
    print(f"  -> critical_difference.png")


# ============================================================
# 3. RESIDUAL ANALYSIS (top-5)
# ============================================================
def _s3_residual():
    residual_stats_l = []
    for nm in TOP_5:
        if nm not in all_test_preds: continue
        p = all_test_preds[nm]
        d_res = (y_d_test - p[:, :7]).flatten()
        p_res = circ_diff(yp_test_deg, p[:, 7:14]).flatten()
        e_res = (y_e_test - p[:, 14])
        for grp_name, res in [("D", d_res), ("P_circ", p_res), ("E", e_res)]:
            sample_res = res[:5000] if len(res) > 5000 else res
            try:    sw_stat, sw_p = shapiro(sample_res)
            except: sw_stat, sw_p = float("nan"), float("nan")
            try:    dw = float(np.sum(np.diff(res)**2) / np.sum(res**2))
            except: dw = float("nan")
            try:
                from scipy.stats import linregress
                sq_res = res**2
                _slope, _intc, _rv, bp_p, _ = linregress(np.arange(len(res)), sq_res)
            except: bp_p = float("nan")
            residual_stats_l.append({
                "Model": nm, "Group": grp_name,
                "Mean": float(np.mean(res)), "Std": float(np.std(res)),
                "Skew": float(stats.skew(res)), "Kurtosis": float(stats.kurtosis(res)),
                "Shapiro_W": sw_stat, "Shapiro_p": sw_p,
                "Durbin_Watson": dw, "Breusch_Pagan_p": bp_p,
                "Normal": "YES" if sw_p > 0.05 else "no",
            })
    pd.DataFrame(residual_stats_l).to_csv(
        os.path.join(ANALYSIS_DIR, "residual_stats.csv"), index=False)

    fig, axes = plt.subplots(3, 3, figsize=(12, 10))
    for i, nm in enumerate(TOP_3):
        if nm not in all_test_preds: continue
        p = all_test_preds[nm]
        residuals_list = [
            ("D (duty)", (y_d_test - p[:, :7]).flatten()),
            ("P (phase, circ)", circ_diff(yp_test_deg, p[:, 7:14]).flatten()),
            ("E (result_E)", (y_e_test - p[:, 14])),
        ]
        for j, (lbl, res) in enumerate(residuals_list):
            ax = axes[i, j]
            stats.probplot(res, dist="norm", plot=ax)
            ax.set_title(f"{nm}\n{lbl}", fontsize=9)
            ax.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(FIGURES_DIR, "qq_plots_top3.png"), bbox_inches="tight")
    plt.close()

    fig, axes = plt.subplots(3, 3, figsize=(12, 10))
    for i, nm in enumerate(TOP_3):
        if nm not in all_test_preds: continue
        p = all_test_preds[nm]
        residuals_list = [
            ("D", (y_d_test - p[:, :7]).flatten()),
            ("P (°)", circ_diff(yp_test_deg, p[:, 7:14]).flatten()),
            ("E", (y_e_test - p[:, 14])),
        ]
        for j, (lbl, res) in enumerate(residuals_list):
            ax = axes[i, j]
            ax.hist(res, bins=60, density=True, alpha=0.7, edgecolor="black")
            mu, sigma = np.mean(res), np.std(res)
            xx = np.linspace(res.min(), res.max(), 200)
            ax.plot(xx, norm.pdf(xx, mu, sigma), "r-", linewidth=1.5,
                    label=f"N({mu:.3f},{sigma:.3f})")
            ax.set_title(f"{nm} — {lbl}", fontsize=9)
            ax.legend(fontsize=7)
    plt.tight_layout()
    plt.savefig(os.path.join(FIGURES_DIR, "residual_histograms_top3.png"), bbox_inches="tight")
    plt.close()
    print(f"  -> residual_stats.csv, qq_plots_top3.png, residual_histograms_top3.png")


# ============================================================
# 4. PERMUTATION IMPORTANCE (Top-10 sklearn)
# ============================================================
def _s4_permutation():
    sk_models_available = [m for m in TOP_20
                           if os.path.exists(os.path.join(MODELS_DIR, f"{m}.pkl"))
                           and "Ensemble" not in m and "Stacking" not in m]
    print(f"  Sklearn modeller: {sk_models_available[:5]}...")
    if not sk_models_available:
        print("  Sklearn model yok, atlaniyor"); return

    perm_rows = []
    n_repeats = 5
    scaler_y = joblib.load(os.path.join(MODELS_DIR, "scaler_y.pkl"))
    for nm in sk_models_available[:10]:
        try:
            m = joblib.load(os.path.join(MODELS_DIR, f"{nm}.pkl"))
        except: continue
        base_comb = results_df.loc[results_df["Model"] == nm, "Combined_R2"].values
        if len(base_comb) == 0: continue
        base_comb = float(base_comb[0])

        for feat_idx, feat_name in enumerate(FEATURE_NAMES):
            drops = []
            for rep in range(n_repeats):
                rng_p = np.random.RandomState(SEED + rep)
                X_perm = X_test_sc.copy()
                X_perm[:, feat_idx] = rng_p.permutation(X_perm[:, feat_idx])
                y_perm = m.predict(X_perm)
                y_perm_orig = scaler_y.inverse_transform(y_perm)
                y_perm_15 = _convert_22_to_15(y_perm_orig)
                d_p = y_perm_15[:, :7]; p_p = y_perm_15[:, 7:14]; e_p = y_perm_15[:, 14]
                d_r2 = float(r2_score(y_d_test, d_p))
                p_cr2 = float(circ_r2(yp_test_deg, p_p))
                e_r2 = float(r2_score(y_e_test, e_p))
                comb_p = (d_r2 + p_cr2 + e_r2) / 3.0
                drops.append(base_comb - comb_p)
            perm_rows.append({
                "Model": nm, "Feature": feat_name,
                "Importance_mean": float(np.mean(drops)),
                "Importance_std": float(np.std(drops)),
            })
        print(f"  {nm} done")
        del m

    if perm_rows:
        pd.DataFrame(perm_rows).to_csv(
            os.path.join(ANALYSIS_DIR, "permutation_importance.csv"), index=False)
        pdf = pd.DataFrame(perm_rows)
        agg = pdf.groupby("Feature")["Importance_mean"].agg(["mean", "std"]).reset_index()
        agg = agg.sort_values("mean", ascending=True)
        fig, ax = plt.subplots(figsize=(8, 5))
        ax.barh(agg["Feature"], agg["mean"], xerr=agg["std"],
                color="steelblue", edgecolor="black")
        ax.set_xlabel("R² Drop (higher = more important)")
        ax.set_title("Permutation Feature Importance (avg over top sklearn)")
        plt.tight_layout()
        plt.savefig(os.path.join(FIGURES_DIR, "permutation_importance.png"),
                    bbox_inches="tight")
        plt.close()
        print(f"  -> permutation_importance.csv/.png")


# ============================================================
# 5. SHAP (top-1 sklearn, 500 samples)
# ============================================================
def _s5_shap():
    import shap
    sk_best = None
    for nm in TOP_20:
        if (os.path.exists(os.path.join(MODELS_DIR, f"{nm}.pkl"))
                and "Ensemble" not in nm and "Stacking" not in nm):
            sk_best = nm; break
    if sk_best is None:
        print("  Sklearn model yok"); return

    print(f"  SHAP target: {sk_best}")
    mdl_sk = joblib.load(os.path.join(MODELS_DIR, f"{sk_best}.pkl"))
    bg_idx = np.random.RandomState(SEED).choice(len(X_train_sc), 100, replace=False)
    ex_idx = np.random.RandomState(SEED+1).choice(len(X_test_sc), 500, replace=False)
    bg = X_train_sc[bg_idx]
    ex = X_test_sc[ex_idx]

    try:
        explainer = shap.TreeExplainer(mdl_sk)
        shap_values = explainer.shap_values(ex)
        print(f"  TreeExplainer kullanildi")
    except Exception as e:
        print(f"  TreeExplainer basarisiz ({str(e)[:60]}), KernelExplainer...")
        explainer = shap.KernelExplainer(mdl_sk.predict, bg)
        shap_values = explainer.shap_values(ex[:100])

    if isinstance(shap_values, list):
        shap_abs = np.mean([np.abs(sv).mean(axis=0) for sv in shap_values], axis=0)
    else:
        shap_abs = np.abs(shap_values).mean(axis=0)
        if shap_abs.ndim > 1:
            shap_abs = shap_abs.mean(axis=-1)

    shap_df = pd.DataFrame({"Feature": FEATURE_NAMES, "SHAP_abs_mean": shap_abs})
    shap_df = shap_df.sort_values("SHAP_abs_mean", ascending=False)
    shap_df.to_csv(os.path.join(ANALYSIS_DIR, "shap_best.csv"), index=False)

    fig, ax = plt.subplots(figsize=(8, 5))
    shap_df_sorted = shap_df.sort_values("SHAP_abs_mean", ascending=True)
    ax.barh(shap_df_sorted["Feature"], shap_df_sorted["SHAP_abs_mean"],
            color="darkorange", edgecolor="black")
    ax.set_xlabel("Mean |SHAP value|")
    ax.set_title(f"SHAP Feature Importance — {sk_best}")
    plt.tight_layout()
    plt.savefig(os.path.join(FIGURES_DIR, "shap_best.png"), bbox_inches="tight")
    plt.close()
    print(f"  -> shap_best.csv, shap_best.png")


# ============================================================
# 6. ENSEMBLE DIVERSITY (top-20)
# ============================================================
def _s6_ensemble_diversity():
    div_models = [m for m in TOP_20 if m in all_test_preds][:20]
    if len(div_models) < 2:
        print("  Yeterli model yok"); return
    err_matrix = np.array([get_errors(nm) for nm in div_models])
    corr_matrix = np.corrcoef(err_matrix)

    fig, ax = plt.subplots(figsize=(10, 8))
    sns.heatmap(corr_matrix, xticklabels=div_models, yticklabels=div_models,
                cmap="RdYlGn_r", center=0.5, vmin=0, vmax=1, annot=False, ax=ax,
                cbar_kws={"label": "Error Pearson Correlation"})
    ax.set_title("Ensemble Diversity (Error Correlation, Top-20)")
    plt.xticks(rotation=45, ha="right", fontsize=7)
    plt.yticks(fontsize=7)
    plt.tight_layout()
    plt.savefig(os.path.join(FIGURES_DIR, "ensemble_diversity.png"), bbox_inches="tight")
    plt.close()

    div_df = pd.DataFrame(corr_matrix, index=div_models, columns=div_models)
    div_df.to_csv(os.path.join(ANALYSIS_DIR, "ensemble_diversity.csv"))
    off_diag = corr_matrix[np.triu_indices_from(corr_matrix, k=1)]
    print(f"  Mean off-diagonal correlation: {off_diag.mean():.4f}")
    print(f"  -> ensemble_diversity.csv/.png")


# ============================================================
# 7. CALIBRATION (prediction interval coverage)
# ============================================================
def _s7_calibration():
    calib_rows = []
    for nm in TOP_5:
        if nm not in all_test_preds or nm not in all_val_preds: continue
        p_val = all_val_preds[nm]; p_test = all_test_preds[nm]
        d_res_val = (y_d_val - p_val[:, :7]).flatten()
        d_res_test = (y_d_test - p_test[:, :7]).flatten()
        p_res_val = circ_diff(yp_val_deg, p_val[:, 7:14]).flatten()
        p_res_test = circ_diff(yp_test_deg, p_test[:, 7:14]).flatten()
        e_res_val = y_e_val - p_val[:, 14]
        e_res_test = y_e_test - p_test[:, 14]

        for grp_name, res_val, res_test in [("D", d_res_val, d_res_test),
                                             ("P", p_res_val, p_res_test),
                                             ("E", e_res_val, e_res_test)]:
            lo_q, hi_q = np.percentile(res_val, [2.5, 97.5])
            coverage = float(np.mean((res_test >= lo_q) & (res_test <= hi_q)))
            calib_rows.append({
                "Model": nm, "Group": grp_name,
                "PI_lower": float(lo_q), "PI_upper": float(hi_q),
                "Target_Coverage": 0.95, "Actual_Coverage": coverage,
                "Miscoverage": abs(0.95 - coverage),
            })
            print(f"  {nm}/{grp_name}: cov={coverage:.4f}")
    pd.DataFrame(calib_rows).to_csv(
        os.path.join(ANALYSIS_DIR, "calibration.csv"), index=False)


# ============================================================
# 8. PER-OUTPUT R² HEATMAP
# ============================================================
def _s8_per_output_heatmap():
    per_out_path = os.path.join(MODELS_DIR, "per_output_metrics.csv")
    if not os.path.exists(per_out_path):
        print("  per_output_metrics.csv yok"); return
    per_out_df = pd.read_csv(per_out_path)
    per_out_top = per_out_df[per_out_df["Model"].isin(TOP_20)].set_index("Model")
    per_out_top = per_out_top.reindex(TOP_20).dropna(how="all")
    r2_cols = [c for c in per_out_top.columns if c.startswith("R2_")]
    if not r2_cols:
        print("  R2_ sutunu yok"); return
    fig, ax = plt.subplots(figsize=(11, max(4, 0.35 * len(per_out_top))))
    sns.heatmap(per_out_top[r2_cols], annot=True, fmt=".4f", cmap="RdYlGn",
                vmin=0.9, vmax=1.0, ax=ax, cbar_kws={"label": "R²"})
    ax.set_title("Per-Output R² (D1-D7, P1-P7, E) — Top-20")
    plt.tight_layout()
    plt.savefig(os.path.join(FIGURES_DIR, "per_output_r2_heatmap.png"), bbox_inches="tight")
    plt.close()
    print(f"  -> per_output_r2_heatmap.png")


# ============================================================
# 9. PARETO FRONTIER PLOTS
# ============================================================
def _get_family(name):
    for fam in ["CNN_BiLSTM", "CNN_BiGRU", "CNN_LSTM", "CNN_GRU", "CNN_RNN",
                "BiLSTM", "BiGRU", "LSTM", "GRU", "SimpleRNN", "CNN1D",
                "ResNet", "TabNet", "MLP",
                "XGBoost", "LightGBM", "HistGradientBoosting", "ExtraTrees",
                "DecisionTree", "RandomForest", "BaggingRegressor", "AdaBoost",
                "SVR", "CatBoost", "Baseline"]:
        if name.startswith(fam): return fam
    return "Other"

def _s9_pareto():
    pareto_path = os.path.join(MODELS_DIR, "pareto_data.csv")
    if not os.path.exists(pareto_path):
        print("  pareto_data.csv yok"); return
    pareto_df = pd.read_csv(pareto_path)
    pareto_df = pareto_df[pareto_df["Combined_R2"] > 0]
    pareto_df["Family"] = pareto_df["Model"].apply(_get_family)

    for xcol, xlabel, logx in [
        ("Params", "Parameters", True),
        ("Train_Time_s", "Train Time (s)", True),
        ("Inference_Time_s", "Inference Time (s)", True),
        ("ModelSize_MB", "Model Size (MB)", True),
    ]:
        if xcol not in pareto_df.columns: continue
        fig, ax = plt.subplots(figsize=(10, 7))
        families = pareto_df["Family"].unique()
        palette = sns.color_palette("tab20", len(families))
        for fam, color in zip(families, palette):
            sub = pareto_df[pareto_df["Family"] == fam]
            ax.scatter(sub[xcol].clip(lower=1e-3), sub["Combined_R2"],
                       s=60, alpha=0.7, label=fam, edgecolor="black", color=color)
        ax.set_xlabel(xlabel); ax.set_ylabel("Combined R²")
        if logx: ax.set_xscale("log")
        ax.set_title(f"Pareto Frontier: {xlabel} vs Combined R²")
        ax.legend(loc="lower right", fontsize=7, ncol=2)
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig(os.path.join(FIGURES_DIR, f"pareto_{xcol}.png"), bbox_inches="tight")
        plt.close()
    print(f"  -> pareto_*.png (4 figur)")


# ============================================================
# 10. MODEL COMPARISON BAR CHART (top-20)
# ============================================================
def _s10_top20_bar():
    top20_df = results_df.head(20)
    fig, ax = plt.subplots(figsize=(12, 7))
    colors = sns.color_palette("viridis", len(top20_df))
    bars = ax.barh(top20_df["Model"][::-1], top20_df["Combined_R2"][::-1],
                   color=colors[::-1], edgecolor="black")
    ax.set_xlabel("Combined R²")
    ax.set_title("Top-20 Models by Combined R²")
    for bar, val in zip(bars, top20_df["Combined_R2"][::-1]):
        ax.text(val + 0.0002, bar.get_y() + bar.get_height()/2,
                f"{val:.4f}", va="center", fontsize=8)
    ax.set_xlim(top20_df["Combined_R2"].min() * 0.995,
                top20_df["Combined_R2"].max() * 1.001)
    plt.tight_layout()
    plt.savefig(os.path.join(FIGURES_DIR, "top20_bar.png"), bbox_inches="tight")
    plt.close()
    print(f"  -> top20_bar.png")


# ============================================================
# 11. FAMILY-WISE BOX PLOT
# ============================================================
def _s11_family_boxplot():
    results_df["Family"] = results_df["Model"].apply(_get_family)
    valid_fam = results_df[results_df["Family"] != "Other"]
    valid_fam = valid_fam[~valid_fam["Model"].str.contains("Ensemble|Stacking", regex=True)]
    fig, ax = plt.subplots(figsize=(14, 6))
    sns.boxplot(data=valid_fam, x="Family", y="Combined_R2", ax=ax, palette="tab20")
    ax.set_title("Combined R² Distribution per Model Family")
    plt.xticks(rotation=45, ha="right")
    ax.grid(True, alpha=0.3, axis="y")
    plt.tight_layout()
    plt.savefig(os.path.join(FIGURES_DIR, "family_boxplot.png"), bbox_inches="tight")
    plt.close()
    print(f"  -> family_boxplot.png")


# ============================================================
# 12. SCATTER: PRED vs TRUE (top-3)
# ============================================================
def _s12_scatter():
    fig, axes = plt.subplots(3, 3, figsize=(13, 12))
    for i, nm in enumerate(TOP_3):
        if nm not in all_test_preds: continue
        p = all_test_preds[nm]
        ax = axes[i, 0]
        ax.scatter(y_d_test.flatten(), p[:, :7].flatten(), s=4, alpha=0.3)
        mn, mx = y_d_test.min(), y_d_test.max()
        ax.plot([mn, mx], [mn, mx], "r--", linewidth=1)
        ax.set_title(f"{nm} — D (R²={r2_score(y_d_test, p[:,:7]):.4f})", fontsize=9)
        ax.set_xlabel("True"); ax.set_ylabel("Pred")
        ax = axes[i, 1]
        ax.scatter(yp_test_deg.flatten(), p[:, 7:14].flatten(), s=4, alpha=0.3)
        ax.plot([0, 360], [0, 360], "r--", linewidth=1)
        ax.set_title(f"{nm} — P (cR²={circ_r2(yp_test_deg, p[:,7:14]):.4f})", fontsize=9)
        ax.set_xlabel("True (°)"); ax.set_ylabel("Pred (°)")
        ax = axes[i, 2]
        ax.scatter(y_e_test, p[:, 14], s=4, alpha=0.3)
        mn, mx = y_e_test.min(), y_e_test.max()
        ax.plot([mn, mx], [mn, mx], "r--", linewidth=1)
        ax.set_title(f"{nm} — E (R²={r2_score(y_e_test, p[:,14]):.4f})", fontsize=9)
        ax.set_xlabel("True"); ax.set_ylabel("Pred")
    plt.tight_layout()
    plt.savefig(os.path.join(FIGURES_DIR, "pred_vs_true_top3.png"), bbox_inches="tight")
    plt.close()
    print(f"  -> pred_vs_true_top3.png")


# ============================================================
# 13. SPATIAL 3D ERROR HEATMAP (top-1)
# ============================================================
def _s13_spatial():
    if BEST not in all_test_preds:
        print("  Best model yok"); return
    p = all_test_preds[BEST]
    d_err = np.mean(np.abs(y_d_test - p[:, :7]), axis=1)
    p_err = np.mean(np.abs(circ_diff(yp_test_deg, p[:, 7:14])), axis=1)
    e_err = np.abs(y_e_test - p[:, 14])
    combined_err = (d_err / max(d_err.max(), 1e-12)
                    + p_err / max(p_err.max(), 1e-12)
                    + e_err / max(e_err.max(), 1e-12)) / 3.0
    x_sc = X_test_sc[:, 0]; y_sc = X_test_sc[:, 1]; z_sc = X_test_sc[:, 2]

    fig = plt.figure(figsize=(18, 5))
    for i, (xx, yy, lbl) in enumerate([
        (x_sc, y_sc, "XY plane (top view)"),
        (x_sc, z_sc, "XZ plane (side view)"),
        (y_sc, z_sc, "YZ plane (front view)"),
    ]):
        ax = fig.add_subplot(1, 3, i+1)
        sc = ax.scatter(xx, yy, c=combined_err, s=4, cmap="YlOrRd", alpha=0.8)
        plt.colorbar(sc, ax=ax, label="Normalized error")
        ax.set_title(f"{BEST} — {lbl}")
    plt.tight_layout()
    plt.savefig(os.path.join(FIGURES_DIR, "spatial_error_heatmap.png"), bbox_inches="tight")
    plt.close()
    print(f"  -> spatial_error_heatmap.png")


# ============================================================
# 14. PER-ORGAN RADAR CHART (top-5)
# ============================================================
def _s14_radar():
    organ_path = os.path.join(MODELS_DIR, "per_organ_metrics.csv")
    if not os.path.exists(organ_path):
        print("  per_organ_metrics.csv yok"); return
    org_df = pd.read_csv(organ_path)
    fig = plt.figure(figsize=(12, 10))
    org_labels = [f"organ {o}" for o in ORGAN_IDS]
    angles = np.linspace(0, 2*np.pi, len(ORGAN_IDS), endpoint=False).tolist()
    angles += angles[:1]
    ax = fig.add_subplot(111, polar=True)
    for nm in TOP_5:
        sub = org_df[org_df["Model"] == nm]
        if len(sub) == 0: continue
        vals = []
        for oid in ORGAN_IDS:
            v = sub[sub["organ_id"] == oid]["Combined"].values
            vals.append(float(v[0]) if len(v) else 0.0)
        vals += vals[:1]
        ax.plot(angles, vals, linewidth=1.5, label=nm[:25])
        ax.fill(angles, vals, alpha=0.1)
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(org_labels)
    ax.set_ylim(0, 1)
    ax.set_title("Per-Organ Combined R² (Top-5)", pad=20)
    ax.legend(loc="upper right", bbox_to_anchor=(1.3, 1.1), fontsize=8)
    plt.tight_layout()
    plt.savefig(os.path.join(FIGURES_DIR, "per_organ_radar.png"), bbox_inches="tight")
    plt.close()
    print(f"  -> per_organ_radar.png")


# ============================================================
# 15. TRAINING CURVES OVERLAY (top-10)
# ============================================================
def _s15_curves():
    curves_dir = os.path.join(MODELS_DIR, "training_curves")
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    cmap = plt.cm.tab10
    for i, nm in enumerate(TOP_10):
        cp = os.path.join(curves_dir, f"{nm}.csv")
        if not os.path.exists(cp): continue
        try:
            c = pd.read_csv(cp)
            color = cmap(i % 10)
            axes[0].plot(c["epoch"], c["train_loss"], color=color, alpha=0.8, label=nm[:20])
            axes[1].plot(c["epoch"], c["val_loss"], color=color, alpha=0.8, label=nm[:20])
        except: pass
    axes[0].set_title("Training Loss (Top-10)"); axes[0].set_xlabel("Epoch"); axes[0].set_ylabel("Loss")
    axes[1].set_title("Validation Loss (Top-10)"); axes[1].set_xlabel("Epoch")
    axes[0].set_yscale("log"); axes[1].set_yscale("log")
    axes[0].legend(fontsize=6, ncol=2); axes[1].legend(fontsize=6, ncol=2)
    axes[0].grid(True, alpha=0.3); axes[1].grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(FIGURES_DIR, "training_curves_top10.png"), bbox_inches="tight")
    plt.close()
    print(f"  -> training_curves_top10.png")


# ============================================================
# 16. WORST-CASE ERROR ANALYSIS (top-1)
# ============================================================
def _s16_worst_case():
    if BEST not in all_test_preds:
        print("  Best yok"); return
    p = all_test_preds[BEST]
    d_err = np.mean(np.abs(y_d_test - p[:, :7]), axis=1)
    p_err = np.mean(np.abs(circ_diff(yp_test_deg, p[:, 7:14])), axis=1)
    e_err = np.abs(y_e_test - p[:, 14])
    n_worst = max(10, len(d_err) // 100)

    worst_rows = []
    for grp, err_arr in [("D", d_err), ("P", p_err), ("E", e_err)]:
        idx_arr = np.argsort(err_arr)[-n_worst:]
        for i in idx_arr[::-1]:
            worst_rows.append({
                "Model": BEST, "Group": grp,
                "Test_Index": int(i), "Error": float(err_arr[i]),
                "Organ": int(test_organ_ids[i]),
                "x_sc": float(X_test_sc[i, 0]),
                "y_sc": float(X_test_sc[i, 1]),
                "z_sc": float(X_test_sc[i, 2]),
            })
    pd.DataFrame(worst_rows).to_csv(
        os.path.join(ANALYSIS_DIR, "worst_cases.csv"), index=False)

    fig, axes = plt.subplots(1, 3, figsize=(14, 4))
    for ax, (grp, err_arr) in zip(axes, [("D", d_err), ("P", p_err), ("E", e_err)]):
        n_w = max(10, len(err_arr) // 100)
        w_idx = np.argsort(err_arr)[-n_w:]
        w_organs = test_organ_ids[w_idx]
        counts = pd.Series(w_organs).value_counts().sort_index()
        ax.bar(counts.index.astype(str), counts.values, color="crimson", edgecolor="black")
        ax.set_title(f"Worst {n_w} ({grp}) — organ distribution")
        ax.set_xlabel("Organ ID"); ax.set_ylabel("Count")
    plt.tight_layout()
    plt.savefig(os.path.join(FIGURES_DIR, "worst_case_organs.png"), bbox_inches="tight")
    plt.close()
    print(f"  -> worst_cases.csv, worst_case_organs.png")


# ============================================================
# 17. ONNX QUANTIZATION (INT8 vs FP32)
# ============================================================
def _s17_quantization():
    import onnxruntime as ort
    from onnxruntime.quantization import quantize_dynamic, QuantType

    quant_rows = []
    onnx_candidates = [m for m in TOP_5
                       if os.path.exists(os.path.join(MODELS_DIR, f"{m}.onnx"))]
    print(f"  ONNX mevcut: {onnx_candidates[:3]}")

    scaler_y_q = joblib.load(os.path.join(MODELS_DIR, "scaler_y.pkl"))
    for nm in onnx_candidates[:3]:
        onnx_path = os.path.join(MODELS_DIR, f"{nm}.onnx")
        int8_path = os.path.join(MODELS_DIR, f"{nm}_int8.onnx")
        try:
            quantize_dynamic(onnx_path, int8_path, weight_type=QuantType.QUInt8)
            fp32_size = os.path.getsize(onnx_path) / (1024*1024)
            int8_size = os.path.getsize(int8_path) / (1024*1024)

            for variant, path in [("FP32", onnx_path), ("INT8", int8_path)]:
                try:
                    sess = ort.InferenceSession(path, providers=["CPUExecutionProvider"])
                    inp_name = sess.get_inputs()[0].name
                    for _ in range(3):
                        _ = sess.run(None, {inp_name: X_test_sc[:100].astype(np.float32)})
                    t_times = []
                    for _ in range(5):
                        t0 = time.time()
                        preds = sess.run(None, {inp_name: X_test_sc.astype(np.float32)})[0]
                        t_times.append(time.time() - t0)
                    mean_t = float(np.mean(t_times))
                    y_orig = scaler_y_q.inverse_transform(preds)
                    y_15 = _convert_22_to_15(y_orig)
                    d_p = y_15[:, :7]; p_p = y_15[:, 7:14]; e_p = y_15[:, 14]
                    d_r2 = float(r2_score(y_d_test, d_p))
                    p_cr2 = float(circ_r2(yp_test_deg, p_p))
                    e_r2 = float(r2_score(y_e_test, e_p))
                    comb = (d_r2 + p_cr2 + e_r2) / 3.0
                    size_mb = fp32_size if variant == "FP32" else int8_size
                    quant_rows.append({
                        "Model": nm, "Variant": variant,
                        "Size_MB": size_mb, "Inference_Time_s": mean_t,
                        "D_R2": d_r2, "P_cR2": p_cr2, "E_R2": e_r2,
                        "Combined_R2": comb,
                    })
                    print(f"  {nm} [{variant}]: {size_mb:.2f}MB | {mean_t*1000:.1f}ms | R²={comb:.4f}")
                except Exception as e:
                    print(f"    {variant} HATA: {str(e)[:80]}")
        except Exception as e:
            print(f"  {nm} quantize HATA: {str(e)[:80]}")

    if quant_rows:
        pd.DataFrame(quant_rows).to_csv(
            os.path.join(ANALYSIS_DIR, "quantization.csv"), index=False)


# ============================================================
# 18. UMAP + TSNE EMBEDDING
# ============================================================
def _s18_embedding():
    try:
        import umap
        reducer = umap.UMAP(n_neighbors=30, min_dist=0.1,
                            random_state=SEED, n_components=2)
        emb = reducer.fit_transform(X_test_sc[:5000])
        fig, ax = plt.subplots(figsize=(9, 7))
        organs = test_organ_ids[:5000]
        for oid in ORGAN_IDS:
            mask = organs == oid
            if mask.sum() > 0:
                ax.scatter(emb[mask, 0], emb[mask, 1], s=8, alpha=0.6, label=f"organ {oid}")
        ax.set_title("UMAP of X_test_sc (10 features, 5000 samples)")
        ax.legend()
        plt.tight_layout()
        plt.savefig(os.path.join(FIGURES_DIR, "umap_input.png"), bbox_inches="tight")
        plt.close()
        print(f"  -> umap_input.png")
    except Exception as e:
        print(f"  UMAP HATA: {str(e)[:120]}")

    try:
        from sklearn.manifold import TSNE
        emb_t = TSNE(n_components=2, random_state=SEED, perplexity=30,
                     n_iter=1000).fit_transform(X_test_sc[:3000])
        fig, ax = plt.subplots(figsize=(9, 7))
        organs = test_organ_ids[:3000]
        for oid in ORGAN_IDS:
            mask = organs == oid
            if mask.sum() > 0:
                ax.scatter(emb_t[mask, 0], emb_t[mask, 1], s=8, alpha=0.6, label=f"organ {oid}")
        ax.set_title("TSNE of X_test_sc (10 features, 3000 samples)")
        ax.legend()
        plt.tight_layout()
        plt.savefig(os.path.join(FIGURES_DIR, "tsne_input.png"), bbox_inches="tight")
        plt.close()
        print(f"  -> tsne_input.png")
    except Exception as e:
        print(f"  TSNE HATA: {str(e)[:120]}")


# ============================================================
# 19. VON MISES FIT (P residuals, top-1)
# ============================================================
def _s19_vonmises():
    if BEST not in all_test_preds:
        print("  Best yok"); return
    p = all_test_preds[BEST]
    p_res_deg = circ_diff(yp_test_deg, p[:, 7:14]).flatten()
    p_res_rad = np.deg2rad(p_res_deg)

    from scipy.stats import vonmises
    kappa, loc, scale = vonmises.fit(p_res_rad, fscale=1)
    print(f"  Von Mises kappa={kappa:.4f}, loc={np.rad2deg(loc):.4f} deg")

    fig, ax = plt.subplots(figsize=(9, 5))
    ax.hist(p_res_deg, bins=80, density=True, alpha=0.7,
            label="Residuals", edgecolor="black")
    xx = np.linspace(-180, 180, 500)
    vm_pdf = vonmises.pdf(np.deg2rad(xx), kappa, loc, scale) * (np.pi/180)
    ax.plot(xx, vm_pdf, "r-", linewidth=2, label=f"Von Mises (κ={kappa:.2f})")
    ax.set_xlabel("Phase residual (°)")
    ax.set_ylabel("Density")
    ax.set_title(f"{BEST} — P residual Von Mises fit")
    ax.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(FIGURES_DIR, "p_residual_vonmises.png"), bbox_inches="tight")
    plt.close()

    with open(os.path.join(ANALYSIS_DIR, "vonmises_fit.txt"), "w") as f:
        f.write(f"Model: {BEST}\n")
        f.write(f"Von Mises kappa: {kappa:.6f}\n")
        f.write(f"Location (deg): {np.rad2deg(loc):.6f}\n")
        f.write(f"Scale: {scale:.6f}\n")
    print(f"  -> p_residual_vonmises.png, vonmises_fit.txt")


# ============================================================
# 20. LATEX TABLES
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
        "\\begin{tabular}{l" + "c" * (len(cols)-1) + "}",
        "\\toprule",
        " & ".join(c.replace("_", "\\_") for c in cols) + " \\\\",
        "\\midrule",
    ]
    for _, row in sub.iterrows():
        lines.append(" & ".join(str(row[c]).replace("_", "\\_") for c in cols) + " \\\\")
    lines += ["\\bottomrule", "\\end{tabular}%", "}", "\\end{table}"]
    return "\n".join(lines)

def _s20_latex():
    tbl_cols = ["Model", "Combined_R2", "D_R2", "P_cR2", "E_R2",
                "D_MAE", "P_cMAE_deg", "E_MAE", "Train_Time(s)", "Params"]
    tbl_fmt = {"Combined_R2": "{:.4f}", "D_R2": "{:.4f}", "P_cR2": "{:.4f}",
               "E_R2": "{:.4f}", "D_MAE": "{:.4f}", "P_cMAE_deg": "{:.2f}",
               "E_MAE": "{:.5f}", "Train_Time(s)": "{:.0f}", "Params": "{:,.0f}"}
    top20_tbl = results_df.head(20)[[c for c in tbl_cols if c in results_df.columns]]
    with open(os.path.join(LATEX_DIR, "table_top20.tex"), "w") as f:
        f.write(_df_to_latex(top20_tbl, "Top-20 models by Combined $R^2$",
                             "tab:top20", top20_tbl.columns.tolist(), tbl_fmt))

    if os.path.exists(os.path.join(MODELS_DIR, "family_summary.csv")):
        fam_df = pd.read_csv(os.path.join(MODELS_DIR, "family_summary.csv"))
        fam_cols = ["Family", "N_Models", "Combined_R2_best", "Combined_R2_mean",
                    "D_MAE_mean", "P_cMAE_deg_mean", "E_MAE_mean"]
        fam_fmt = {"Combined_R2_best": "{:.4f}", "Combined_R2_mean": "{:.4f}",
                   "D_MAE_mean": "{:.4f}", "P_cMAE_deg_mean": "{:.2f}",
                   "E_MAE_mean": "{:.5f}"}
        fam_df_sub = fam_df[[c for c in fam_cols if c in fam_df.columns]]
        with open(os.path.join(LATEX_DIR, "table_family.tex"), "w") as f:
            f.write(_df_to_latex(fam_df_sub, "Family-wise performance summary",
                                 "tab:family", fam_df_sub.columns.tolist(), fam_fmt))

    wilc_path = os.path.join(ANALYSIS_DIR, "wilcoxon_bonferroni.csv")
    if os.path.exists(wilc_path):
        wilc = pd.read_csv(wilc_path).head(15)
        w_cols = ["Model_1", "Model_2", "p_raw", "p_bonferroni", "sig_bonf", "Cohens_d", "Effect"]
        w_fmt = {"p_raw": "{:.3e}", "p_bonferroni": "{:.3e}", "Cohens_d": "{:.3f}"}
        with open(os.path.join(LATEX_DIR, "table_wilcoxon.tex"), "w") as f:
            f.write(_df_to_latex(wilc, "Pairwise Wilcoxon + Bonferroni + Cohen's d",
                                 "tab:wilcoxon", w_cols, w_fmt))

    ci_path = os.path.join(MODELS_DIR, "bootstrap_ci.csv")
    if os.path.exists(ci_path):
        ci = pd.read_csv(ci_path)
        ci_cols = ["Model", "R2_mean", "R2_std", "CI_lower_2.5", "CI_upper_97.5"]
        ci_fmt = {"R2_mean": "{:.5f}", "R2_std": "{:.5f}",
                  "CI_lower_2.5": "{:.5f}", "CI_upper_97.5": "{:.5f}"}
        with open(os.path.join(LATEX_DIR, "table_bootstrap.tex"), "w") as f:
            f.write(_df_to_latex(ci, "Bootstrap 95\\% confidence intervals (top-10)",
                                 "tab:bootstrap", ci_cols, ci_fmt))
    print(f"  -> {LATEX_DIR}/*.tex")


# ============================================================
# MAIN RUNNER — all sections with skip + try/except
# ============================================================
SECTIONS = [
    (1, "STATISTICAL TESTS (Friedman, Nemenyi, Wilcoxon, Bonferroni, Cohen's d)",
     [os.path.join(ANALYSIS_DIR, "wilcoxon_bonferroni.csv"),
      os.path.join(ANALYSIS_DIR, "nemenyi_pairwise.csv"),
      os.path.join(ANALYSIS_DIR, "friedman_summary.txt")], _s1_stats),
    (2, "CRITICAL DIFFERENCE DIAGRAM",
     [os.path.join(FIGURES_DIR, "critical_difference.png")], _s2_cd_diagram),
    (3, "RESIDUAL ANALYSIS (Q-Q, histogram, normality tests)",
     [os.path.join(ANALYSIS_DIR, "residual_stats.csv"),
      os.path.join(FIGURES_DIR, "qq_plots_top3.png"),
      os.path.join(FIGURES_DIR, "residual_histograms_top3.png")], _s3_residual),
    (4, "PERMUTATION IMPORTANCE (top-10 sklearn)",
     [os.path.join(ANALYSIS_DIR, "permutation_importance.csv"),
      os.path.join(FIGURES_DIR, "permutation_importance.png")], _s4_permutation),
    (5, "SHAP (top-1 sklearn, 500 samples)",
     [os.path.join(ANALYSIS_DIR, "shap_best.csv"),
      os.path.join(FIGURES_DIR, "shap_best.png")], _s5_shap),
    (6, "ENSEMBLE DIVERSITY MATRIX (top-20)",
     [os.path.join(ANALYSIS_DIR, "ensemble_diversity.csv"),
      os.path.join(FIGURES_DIR, "ensemble_diversity.png")], _s6_ensemble_diversity),
    (7, "CALIBRATION (prediction interval coverage)",
     [os.path.join(ANALYSIS_DIR, "calibration.csv")], _s7_calibration),
    (8, "PER-OUTPUT R² HEATMAP",
     [os.path.join(FIGURES_DIR, "per_output_r2_heatmap.png")], _s8_per_output_heatmap),
    (9, "PARETO FRONTIER PLOTS (4 varyant)",
     [os.path.join(FIGURES_DIR, "pareto_Params.png"),
      os.path.join(FIGURES_DIR, "pareto_Train_Time_s.png"),
      os.path.join(FIGURES_DIR, "pareto_Inference_Time_s.png"),
      os.path.join(FIGURES_DIR, "pareto_ModelSize_MB.png")], _s9_pareto),
    (10, "MODEL COMPARISON BAR CHART (top-20)",
     [os.path.join(FIGURES_DIR, "top20_bar.png")], _s10_top20_bar),
    (11, "FAMILY-WISE BOX PLOT",
     [os.path.join(FIGURES_DIR, "family_boxplot.png")], _s11_family_boxplot),
    (12, "SCATTER PRED vs TRUE (top-3)",
     [os.path.join(FIGURES_DIR, "pred_vs_true_top3.png")], _s12_scatter),
    (13, "SPATIAL 3D ERROR HEATMAP (top-1)",
     [os.path.join(FIGURES_DIR, "spatial_error_heatmap.png")], _s13_spatial),
    (14, "PER-ORGAN RADAR CHART (top-5)",
     [os.path.join(FIGURES_DIR, "per_organ_radar.png")], _s14_radar),
    (15, "TRAINING CURVES OVERLAY (top-10)",
     [os.path.join(FIGURES_DIR, "training_curves_top10.png")], _s15_curves),
    (16, "WORST-CASE ERROR ANALYSIS",
     [os.path.join(ANALYSIS_DIR, "worst_cases.csv"),
      os.path.join(FIGURES_DIR, "worst_case_organs.png")], _s16_worst_case),
    (17, "ONNX QUANTIZATION (INT8 vs FP32)",
     [os.path.join(ANALYSIS_DIR, "quantization.csv")], _s17_quantization),
    (18, "UMAP + TSNE EMBEDDING",
     [os.path.join(FIGURES_DIR, "umap_input.png"),
      os.path.join(FIGURES_DIR, "tsne_input.png")], _s18_embedding),
    (19, "VON MISES FIT (P residuals)",
     [os.path.join(FIGURES_DIR, "p_residual_vonmises.png"),
      os.path.join(ANALYSIS_DIR, "vonmises_fit.txt")], _s19_vonmises),
    (20, "LATEX TABLES (4 tablo)",
     [os.path.join(LATEX_DIR, "table_top20.tex"),
      os.path.join(LATEX_DIR, "table_family.tex"),
      os.path.join(LATEX_DIR, "table_wilcoxon.tex"),
      os.path.join(LATEX_DIR, "table_bootstrap.tex")], _s20_latex),
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
print(f"Figürler:    {FIGURES_DIR}")
print(f"CSV/TXT:     {ANALYSIS_DIR}")
print(f"LaTeX:       {LATEX_DIR}")
print("=" * 80)

# Save status as JSON for run_kedi.sh to check
status_path = os.path.join(ANALYSIS_DIR, "section_status.json")
with open(status_path, "w") as f:
    json.dump({"ok": n_ok, "skip": n_skip, "fail": n_fail,
               "sections": [{"id": s[0], "name": s[1], "status": s[2]}
                            for s in _SECTION_STATUS]}, f, indent=2)

# Exit code: 0 if all OK or SKIP, 1 if any FAIL
sys.exit(0 if n_fail == 0 else 1)
