"""xai_tabular — tabular/regression modeller icin ortak XAI araclari.

Kapsam:
  - shap_wrapper       : Tree / Deep / Linear / Kernel Explainer switcher
  - ig_torch           : Captum Integrated Gradients (PyTorch MLP/tabnet vb.)
  - feature_ranking    : top-N |attribution| CSV + bar plot
  - gene_ranking       : RNA-seq ozel (gene symbol map + top-N gen listesi)

Kullanim (PEMF vendored kopya, 2026-08-26 — ai_hub paketi icinden):

    from ai_hub.xai_tabular.shap_wrapper import explain_shap
    from ai_hub.xai_tabular.feature_ranking import top_features_csv, bar_plot
    from ai_hub.xai_tabular.em_sensitivity import run_em_xai
"""
from .shap_wrapper import explain_shap, ShapResult
from .feature_ranking import top_features_csv, bar_plot
from .em_sensitivity import (
    run_em_xai, sensitivity_analysis, shap_kernel_em, EM_FEATURES,
)

__all__ = [
    "explain_shap",
    "ShapResult",
    "top_features_csv",
    "bar_plot",
    # EM helpers
    "run_em_xai",
    "sensitivity_analysis",
    "shap_kernel_em",
    "EM_FEATURES",
]
