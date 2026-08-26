"""xai_utils — image-tabanli XAI icin paylasilan araclar (Grad-CAM ailesi + overlay).

Kullanim (PEMF vendored kopya, 2026-08-26 — ai_hub paketi icinden):

    ⚠️ grad_cam/yolo_cam torch ister ve KOSULLU yuklenir (asagida) — torch'suz ortamda
    (CI test seti, agir-AI'siz kurulum) overlay/report_html/disagreement YINE calisir;
    GradCAMExplainer/YoloEigenCAM None kalir (TORCH_XAI_AVAILABLE bayragi). Gradient-XAI
    tercihen ai_service/PT'li yollarda (xai-entegrasyon-plani.md §2).

    from ai_hub.xai_utils.overlay import blend_and_save
    from ai_hub.xai_utils.report_html import build_report
    from ai_hub.xai_utils import GradCAMExplainer, TORCH_XAI_AVAILABLE  # torch'luysa

Ilgili modul icin uygun target_layer secimi sart. Ornekler:
    VGG-19-BN         : model.features[-1]
    ResNet/WideResNet : model.layer4[-1]
    DenseNet-201      : model.features.denseblock4
    EfficientNet      : model.blocks[-1] (timm)  |  model.features[-1] (torchvision)
    YOLO Detect       : eigen_cam.YOLOEigenCAM (Grad-CAM YOLO'da zayif — EigenCAM tercih)
"""

# PEMF sertlestirmesi (2026-08-26, CI kosusu dersi): grad_cam.py modul-seviyesinde torch
# import eder; kosulsuz paket-import'u torch'suz ortamda TUM xai_utils'i kilitliyordu
# (overlay/report_html testleri CI'da ModuleNotFoundError). torch-gerektirenler KOSULLU.
try:
    from .grad_cam import GradCAMExplainer, list_pytorch_gradcam_methods
    from .yolo_cam import YoloEigenCAM

    TORCH_XAI_AVAILABLE = True
except ImportError:  # torch yok → gradient-XAI kapali; geri kalan paket calisir
    GradCAMExplainer = None  # type: ignore[assignment]
    list_pytorch_gradcam_methods = None  # type: ignore[assignment]
    YoloEigenCAM = None  # type: ignore[assignment]
    TORCH_XAI_AVAILABLE = False
from .disagreement import ensemble_disagreement_map
from .overlay import blend_and_save, heatmap_to_rgb
from .report_html import build_report

__all__ = [
    "GradCAMExplainer",
    "list_pytorch_gradcam_methods",
    "blend_and_save",
    "heatmap_to_rgb",
    "ensemble_disagreement_map",
    "build_report",
    "YoloEigenCAM",
    "TORCH_XAI_AVAILABLE",
]
