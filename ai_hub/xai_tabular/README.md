# xai_tabular

**Tabular/regression XAI ortak kütüphanesi** — tabular classifier ve regression modelleri (sklearn tree ensembles, XGBoost, CatBoost, PyTorch MLP, RNA-seq MLP vb.) için paylaşılan araçlar.

## İçerik

| Modül | Amaç |
|---|---|
| `shap_wrapper.py` | `explain_shap()` — TreeExplainer / DeepExplainer / LinearExplainer / KernelExplainer switcher (auto-detect) |
| `ig_torch.py` | `integrated_gradients()` — Captum tabanlı, PyTorch MLP için |
| `feature_ranking.py` | `top_features_csv`, `bar_plot` — attribution → top-N feature CSV + PNG |
| `gene_ranking.py` | `top_genes_csv` — RNA-seq özel (pos/neg direction ayrık top-N) |

## Kullanım — Her inference CLI'den

```python
# inference/inference_<X>/inference_<X>.py başında:
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # inference/ yola ekle

from xai_tabular.shap_wrapper import explain_shap
from xai_tabular.ig_torch import integrated_gradients   # PyTorch model için
from xai_tabular.feature_ranking import top_features_csv, bar_plot
```

## Örnek — Tree Ensemble (SHAP TreeExplainer)

```python
from xai_tabular import explain_shap, top_features_csv, bar_plot

# clf = ExtraTreesClassifier / XGBClassifier / CatBoostClassifier / ...
res = explain_shap(clf, X_new,
                    feature_names=FEATURE_NAMES,
                    class_names=["not_ckd", "ckd"])
# res.values: (N, F) veya (N, F, C)

top_features_csv(res.values if res.values.ndim == 2 else res.values[..., 1],
                  FEATURE_NAMES, "out/shap_top_ckd.csv", top_n=20)
bar_plot(res.values[0] if res.values.ndim == 2 else res.values[0, :, 1],
         FEATURE_NAMES, "out/shap_bar_ckd.png",
         title="SHAP — CKD attribution", signed=True)
```

## Örnek — PyTorch MLP (Integrated Gradients)

```python
from xai_tabular.ig_torch import integrated_gradients
from xai_tabular.gene_ranking import top_genes_csv

# model = PT nn.Module (eval), X_transformed = (N, K_selected) numpy
attrs = integrated_gradients(model, X_transformed,
                              class_idx=1,     # KIRC
                              baseline=0.0,    # scaled data icin 0 = mean
                              n_steps=50,
                              device="cuda:0")

# RNA-seq: index -> gene symbol
gene_symbols = [ALL_GENES[i] for i in feature_indices]  # (K_selected,)
top_genes_csv(attrs, gene_symbols, "out/top_genes.csv",
              top_n=30, direction="signed")
```

## Auto-detect Kuralları

`explain_shap(model, X, model_type='auto')` şunları tespit eder:

| Model tipi | Explainer | Hız |
|---|---|---|
| `XGBClassifier`, `LGBMClassifier`, `CatBoostClassifier`, `RandomForest*`, `ExtraTrees*`, `GradientBoosting*`, `HistGradientBoosting*`, `Bagging*`, `DecisionTree*` | `TreeExplainer` | Çok hızlı (native) |
| `LogisticRegression`, `LinearRegression`, `Ridge`, `Lasso` | `LinearExplainer` | Hızlı |
| `torch.nn.Module` | `DeepExplainer` (fallback: `GradientExplainer`) | Orta |
| Diğer callable (ONNX runtime, sklearn Pipeline vb.) | `KernelExplainer` | Yavaş |

`model_type` manuel de verilebilir — auto tanımasa da doğru explainer seçilebilsin.

## Bağımlılıklar

```bash
pip install shap captum matplotlib pandas numpy
# opsiyonel: xgboost, lightgbm, catboost (model türüne göre)
```

## İkinci Mod — Kardeş `explain_<name>.py`

Her inference klasörüne opsiyonel batch/rapor odaklı ayrı script (bkz. `inference_human_kidney_rna/explain_human_kidney_rna.py`).

---

Değişiklikler bu kütüphanede yapılırsa tüm tabular inference modülleri otomatik iyileşir.
