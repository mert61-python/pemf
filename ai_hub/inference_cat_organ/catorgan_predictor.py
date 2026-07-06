"""catorgan_predictor.py — CatOrganPredictor: inference_cat_organ.main() sadık wrapper.

Hazır predictor sınıfı olmadığı için main() (I/O-only CLI) çekirdek akışını
sarmalıyoruz:  YOLOv8m-seg → SuperAnimal FasterRCNN + RTMPose-S → classify_pose →
estimate_organs_pnp (canonical atlas + PnP, ArUco opsiyonel) → 10 organ 3B (cm).

- **ONNX-only, CPU** (device="cpu"). torch/DeepLabCut/mmpose GEREKMEZ.
- Model yolları: 3 ONNX ProgramData'dan (download_model_sync) çözülür ve
  `lib.runners` modül sabitleri (POSE/DET/YOLO_ONNX) monkeypatch edilir — böylece
  frozen EXE'de staged modeller kullanılır (bundle EDİLMEZ, >5MB).
- lib/ relative-import alt-paketi olarak import edilir (sys.path kirletmeden).
"""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np

# lib alt-paketi (içinde relative importlar `.canonical` vb. → doğru çözülür)
from .lib import runners as _runners
from .lib import qr as _qr
from .lib.pipeline import estimate_organs_pnp
from .lib.pose import classify_pose
from .lib.validation import anatomic_consistency_check
from .lib.canonical import KEYPOINT_NAMES, ORGAN_IDS
from .lib.cabin_config import load_cabin_config

# organ_id → TR ad (canonical ORGAN_IDS ile birebir)
ORGAN_NAMES = dict(ORGAN_IDS)  # {1:"mide", 2:"bobrek", ...}

_MODEL_FILES = {
    "yolo": "yolov8m-seg.onnx",
    "det":  "superanimal_quadruped_fasterrcnn_mobilenet_v3_large_fpn.onnx",
    "pose": "superanimal_quadruped_rtmpose_s.onnx",
}


class CatOrganPredictor:
    """Kedi organ 3B lokalizasyon — tek görüntü → organs dict (+ opsiyonel overlay).

    Args:
        device: "cpu" (headless varsayılan) / "0"/"cuda" (GPU).
        models_dir: ONNX'lerin bulunduğu dizin (None → download_model_sync/ProgramData).
    """

    def __init__(self, device: str = "cpu", models_dir: str | os.PathLike | None = None):
        self.device = device
        self._resolve_models(models_dir)
        # ArUco/cabin varsayılanları (main() ile aynı; CLI verilmediğinde)
        _qr.ARUCO_REAL_CM = 10.0
        _qr.ARUCO_DICT = "DICT_5X5_50"
        self.cabin_cfg = load_cabin_config(None)
        # cold-start: ilk çağrı ONNX session'ları yükler (runners cache)

    def _resolve_models(self, models_dir):
        base_local = Path(models_dir) if models_dir else (Path(__file__).parent / "models")

        def resolve(fname):
            try:
                from utils.model_downloader import download_model_sync
                return Path(download_model_sync(f"ai_hub/inference_cat_organ/models/{fname}"))
            except Exception:
                return base_local / fname

        # runners.py modül-sabitlerini staged yollara yönlendir (frozen-safe)
        _runners.YOLO_ONNX = resolve(_MODEL_FILES["yolo"])
        _runners.DET_ONNX = resolve(_MODEL_FILES["det"])
        _runners.POSE_ONNX = resolve(_MODEL_FILES["pose"])

    def predict(self, image_path: str | os.PathLike, *, render: bool = False,
                target_oid: int | None = None, lang: str = "tr") -> dict:
        """Tek görüntü → organs.json v2.1 dict. render=True ise `_overlay_bgr` ekler."""
        image_path = str(image_path)

        # 1. Segmentasyon (YOLOv8m-seg ONNX)
        seg = _runners.run_yolo_segmentation(image_path, device=self.device)
        if "error" in seg:
            raise RuntimeError(f"segmentasyon: {seg['error']}")
        bbox = np.array(seg["bbox"])

        # 2. DLC pose (FasterRCNN + RTMPose-S ONNX)
        pose = _runners.run_pose(image_path, device=self.device)
        if "error" in pose:
            raise RuntimeError(f"pose: {pose['error']}")
        kp = pose["keypoints"]
        kp_d = _runners._kp_dict(kp)

        # 3. Pose sınıflandırma + organ atlası (Procrustes + PnP)
        pose_info = classify_pose(kp_d, seg.get("mask_xy"), bbox)
        cabin_params = {
            "qr_to_origin_cm": [0.0, 0.0, 0.0],
            "axes_def": "x=right,y=down,z=depth",
            "extent_cm": [0.0, 0.0, 0.0],
            "config": self.cabin_cfg,
        }
        organs = estimate_organs_pnp(kp_d, kp[:, 2], bbox, pose_info,
                                     mask_xy=seg.get("mask_xy"),
                                     image_path=image_path,
                                     cabin_params=cabin_params)
        if "error" in organs:
            raise RuntimeError(f"PnP: {organs['error']}")

        morph = organs.get("morphology")
        try:
            anatomic = anatomic_consistency_check(organs.get("organs") or {},
                                                  morph=morph, strict=False)
        except Exception as e:  # noqa: BLE001
            anatomic = {"passed": None, "error": str(e)}

        # main() ile aynı v2.1 sonuç sözlüğü (render fonksiyonları bu şemayı bekler)
        result = {
            "schema_version": "v2.1",
            "image": image_path,
            "image_name": os.path.basename(image_path),
            "bbox": [float(v) for v in seg["bbox"]],
            "segmentation": {"n_detections": seg.get("n_detections"),
                             "mask_xy": seg.get("mask_xy")},
            "pose": {n: [round(float(kp[i, 0]), 2), round(float(kp[i, 1]), 2),
                         round(float(kp[i, 2]), 4)]
                     for i, n in enumerate(KEYPOINT_NAMES)},
            "pose_classifier": pose_info,
            "method": "Procrustes+QR-canonical",
            "morphology_method": morph.get("method") if morph else None,
            "organ_atlas_source": "canonical_atlas_v2",
            "anatomic_consistency": anatomic,
            "organs": organs.get("organs"),
            "axis": organs.get("axis"),
            "pnp_fit": organs.get("pnp_fit"),
            "R_matrix": organs.get("R_matrix"),
            "t_vec": organs.get("t_vec"),
            "fitted_keypoints_2d": organs.get("fitted_keypoints_2d"),
            "morphology": morph,
        }

        if render:
            result["_overlay_bgr"] = self._render_organs(image_path, result, target_oid, lang)
        return result

    @staticmethod
    def _render_organs(image_path, result, target_oid, lang):
        """04_organs benzeri organ-overlay (cv2 BGR img) — render hatası None döner."""
        try:
            from .lib.render import render_organs_classic
            return render_organs_classic(image_path, result, target_oid, lang=lang)
        except Exception:  # noqa: BLE001
            return None
