# xai_utils

**Image-tabanlı XAI ortak kütüphanesi** — projedeki tüm image classifier / detector / segmentation inference modülleri tarafından paylaşılır.

## İçerik

| Modül | Amaç |
|---|---|
| `grad_cam.py` | `GradCAMExplainer` — GradCAM, GradCAM++, HiResCAM, ScoreCAM, EigenCAM, XGradCAM tek wrapper |
| `overlay.py` | `blend_and_save`, `side_by_side` — heatmap + orijinal görüntü blend |
| `disagreement.py` | `ensemble_disagreement_map`, `mean_cam` — ensemble üyeleri arası CAM disagreement |
| `report_html.py` | `build_report` — tek sayfa HTML rapor (embedded görsel + top-K + notlar) |

## Kullanım — Her inference CLI'den

```python
# inference/inference_<X>/inference_<X>.py başında (Faz 0 patterni):
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # inference/ yola ekle

from xai_utils.grad_cam import GradCAMExplainer
from xai_utils.overlay import blend_and_save
from xai_utils.report_html import build_report
```

## Örnek — Tek görüntü açıklama

```python
import torch
from xai_utils import GradCAMExplainer, blend_and_save, build_report

# model: PT nn.Module (eval), img_rgb: (H,W,3) uint8, x: (1,3,H',W') input tensor
explainer = GradCAMExplainer(model, target_layer=model.features[-1],
                              method="hirescam", device="cuda:0")
heatmap = explainer.explain(x, class_idx=predicted_class)   # (H',W') 0-1

blend_and_save(img_rgb, heatmap, "out/cam.png", alpha=0.4)
build_report("out/report.html",
             title="Grad-CAM Explanation",
             input_image="original.jpg",
             prediction={"top_1_class":"grade2","top_1_prob":0.99,"top_k":[...]},
             cam_images={"HiRes-CAM": "out/cam.png"})
```

## Target layer seçimi (mimari başına)

| Backbone | Uygun target_layer |
|---|---|
| VGG-16 / VGG-19 (BN) | `model.features[-1]` |
| ResNet, WideResNet | `model.layer4[-1]` |
| DenseNet | `model.features.denseblock4` |
| EfficientNet (torchvision) | `model.features[-1]` |
| EfficientNet / timm | `model.blocks[-1]` |
| YOLOv8/11 (detect) | `EigenCAM` (`model.model.model[-2]`) |
| Vision Transformer | `model.blocks[-1].norm1` + reshape_transform |

## Bağımlılıklar

```bash
pip install grad-cam matplotlib opencv-python numpy
```

## İkinci Mod — Kardeş `explain_<name>.py`

Her inference klasörüne opsiyonel olarak batch/rapor odaklı ayrı script bırakılır (bkz. `inference_renal_histopath_kmc/explain_renal_histopath_kmc.py`). Aynı `xai_utils` API'yi kullanır ama yalnızca XAI amacına odaklıdır (predict + CAM + HTML rapor tek komutta).

---

Değişiklikler bu kütüphanede yapılırsa **tüm** inference modülleri otomatik iyileşir — kopya-paste yok.
