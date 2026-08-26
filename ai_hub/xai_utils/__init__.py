"""xai_utils — image-tabanli XAI icin paylasilan araclar (Grad-CAM ailesi + overlay).

Kullanim (PEMF vendored kopya, 2026-08-26 — ai_hub paketi icinden):

    ⚠️ Bu paketin import'u KOSULSUZ torch ister (grad_cam.py modul-seviyesi import)
    — frozen client'ta torch 2.1.2+cpu mevcut; yine de tercihen ai_service/PT'li
    yollarda kullanin (xai-entegrasyon-plani.md §2).

    from ai_hub.xai_utils.grad_cam import GradCAMExplainer
    from ai_hub.xai_utils.overlay import blend_and_save
    from ai_hub.xai_utils.report_html import build_report

Ilgili modul icin uygun target_layer secimi sart. Ornekler:
    VGG-19-BN         : model.features[-1]
    ResNet/WideResNet : model.layer4[-1]
    DenseNet-201      : model.features.denseblock4
    EfficientNet      : model.blocks[-1] (timm)  |  model.features[-1] (torchvision)
    YOLO Detect       : eigen_cam.YOLOEigenCAM (Grad-CAM YOLO'da zayif — EigenCAM tercih)
"""
from .grad_cam import GradCAMExplainer, list_pytorch_gradcam_methods
from .overlay import blend_and_save, heatmap_to_rgb
from .disagreement import ensemble_disagreement_map
from .report_html import build_report
from .yolo_cam import YoloEigenCAM

__all__ = [
    "GradCAMExplainer",
    "list_pytorch_gradcam_methods",
    "blend_and_save",
    "heatmap_to_rgb",
    "ensemble_disagreement_map",
    "build_report",
    "YoloEigenCAM",
]
