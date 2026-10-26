# Author: mertaygn, cglrgrkn
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
from .lib.cabin_config import load_cabin_config, varsayilan_kabin_yaml

# organ_id → TR ad (canonical ORGAN_IDS ile birebir)
ORGAN_NAMES = dict(ORGAN_IDS)  # {1:"mide", 2:"bobrek", ...}

#: D1.E08 (İG-5.27): kabin yapılandırması yüklenemediğinde operatöre giden TEK metin (gömülü uç + GPU servisi aynı).
KABIN_UYARISI = (
    "Kabin yapılandırması yüklenemedi — organ konumları KALİBRASYONSUZ (kabin koordinatı yok, güven sınırlı). "
    "Kabin yapılandırma dosyasını (kurulum) kontrol edin ya da teknik desteğe başvurun."
)


def kabin_uyarisi(result: dict) -> str | None:
    """Sonuç kalibrasyonsuzsa (kabin yapılandırması yüklenemedi) operatör metni, değilse None."""
    return KABIN_UYARISI if ((result or {}).get("kabin_yapilandirmasi") or {}).get("yuklendi") is False else None


# SG.G5 (2026-10-14, sahip gözlemi — canlı kip): "kedi / organ BULUNAMADI" BİLGİDİR, hata değil. `predict` bunları RuntimeError ile
# bildiriyor ve AI Hub ucu hepsini 500 "Kedi organ analiz hatası"na çeviriyordu → canlı kipte kedisiz her kare sessizce düşüyor,
# elle analizde operatör "hata" görüyordu (FGS / segmentasyon "bulunamadı"yı başarılı yanıtla söyler). Yalnız aşağıdaki BİLGİ
# iletileri eşlenir; gerçek arızalar (model dosyası yok, resim okunamadı, solvePnP istisnası) hata olarak KALIR. Gömülü uç ve GPU
# servisi AYNI işlevi kullanır (parite).
BULUNAMADI_KEDI = "kedi_bulunamadi"
BULUNAMADI_ORGAN = "organ_cikarilamadi"
BULUNAMADI_METNI = {
    BULUNAMADI_KEDI: "Görüntüde kedi bulunamadı. Kedinin tümü kadraja girsin; ışık iyi ve görüntü net olsun.",
    BULUNAMADI_ORGAN: (
        "Kedi bulundu ama organ konumları çıkarılamadı (vücut noktaları yetersiz). Kediyi yandan ya da üstten, tümü görünecek "
        "şekilde çekin."
    ),
}
_BULUNAMADI_ONEKLERI = (
    ("segmentasyon: kedi tespit edilemedi", BULUNAMADI_KEDI),
    ("pose: DLC kedi bulamadi", BULUNAMADI_KEDI),
    ("pose: detector conf <", BULUNAMADI_KEDI),
    ("PnP: yetersiz keypoint", BULUNAMADI_ORGAN),
    ("PnP: yetersiz kp", BULUNAMADI_ORGAN),
    ("PnP: weight toplami sifir", BULUNAMADI_ORGAN),
    ("PnP: cat_pnp_fail", BULUNAMADI_ORGAN),
)


def bulunamadi_nedeni(exc: BaseException) -> str | None:
    """`predict`in fırlattığı istisna bir "bulunamadı" BİLGİSİ ise kodu (`BULUNAMADI_*`), gerçek arızaysa None."""
    if not isinstance(exc, RuntimeError):
        return None
    metin = str(exc)
    for onek, kod in _BULUNAMADI_ONEKLERI:
        if metin.startswith(onek):
            return kod
    return None

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
        # Kabin yapılandırması = paketli cabin_config_example.yaml (kabin kurulumunda doldurulan dosya).
        # 2026-09-08'e kadar burada `load_cabin_config(None)` → DEFAULT geliyordu: fixed_position/
        # to_marker YOK → `has_perspective_data` False → ArUco/perspektif yolu uygulamada HİÇ
        # çalışmıyordu (yaml güncellemeleri etkisizdi). Dosya yok/bozuksa eski davranış (DEFAULT,
        # kalibrasyonsuz kanonik) korunur — analiz düşmez. Kapı: tests/test_kabin_config_65x50x50.py
        # ⚠️ D1.E08 (İG-5.27): DEFAULT'a düşüş artık SESSİZ ve "kalibre" DEĞİL. Eskiden `cabin_active` yalnız ArUco'ya
        # bağlıydı → YAML yok/bozukken sonuç `calibrated=True`, güven tavansız ve kabin koordinatı DEFAULT geometriden
        # ~84 cm kayık çıkıyordu (ölçüldü). Artık `kabin_yuklendi=False` → pipeline kabini KALİBRE SAYMAZ (calibrated
        # False, kalibrasyonsuz güven tavanı, DEFAULT geometriden kabin koordinatı yok) ve sonuç bunu `kabin_yapilandirmasi`
        # ile bildirir (AI Pro: hedef doğrulanamaz → sürülmez + operatöre eylem; AI Hub: yanıtta uyarı).
        self.kabin_yuklendi = True
        self.kabin_hatasi = None
        try:
            _kabin_yolu = varsayilan_kabin_yaml()
            if _kabin_yolu is None:
                # ⚠️ İNCELEME-2 i5-F-1: paketli dosya YOKSA `varsayilan_kabin_yaml()` None döner ve
                # `load_cabin_config(None)` istisnasız DEFAULT verir → "yüklendi" sanılıyor, operatöre hiçbir şey
                # söylenmiyordu (ölçüldü: `kabin_yapilandirmasi.yuklendi` True, AI Hub `kabin_uyarisi` yok).
                raise FileNotFoundError("paketli kabin yapılandırması (cabin_config_example.yaml) bulunamadı")
            self.cabin_cfg = load_cabin_config(_kabin_yolu)
        except Exception as e:  # noqa: BLE001 — bozuk yaml analizi düşürmesin
            import logging

            logging.getLogger(__name__).warning(
                "Kabin yapılandırması yüklenemedi (%s) — kedi-organ sonuçları KALİBRASYONSUZ (kabin koordinatı yok)", e
            )
            self.cabin_cfg = load_cabin_config(None)
            self.kabin_yuklendi = False
            self.kabin_hatasi = f"{type(e).__name__}: {e}"[:200]
        # ArUco sabitleri TEK kaynaktan (yaml) — basılı marker sayfasıyla aynı: DICT_5X5_50 / 10 cm
        _qr.ARUCO_REAL_CM = float((self.cabin_cfg.get("aruco") or {}).get("real_cm", 10.0))
        _qr.ARUCO_DICT = str((self.cabin_cfg.get("aruco") or {}).get("dict", "DICT_5X5_50"))
        # cold-start: ilk çağrı ONNX session'ları yükler (runners cache)

    def _resolve_models(self, models_dir):
        base_local = Path(models_dir) if models_dir else (Path(__file__).parent / "models")

        def resolve(fname):
            try:
                from utils.model_downloader import download_model_sync
                return Path(download_model_sync(f"ai_hub/inference_cat_organ/models/{fname}"))
            except Exception as e:
                if type(e).__name__ == "ModelButunlukHatasi":  # D3I-A2.4 · Y18: bütünlük reddi yutulmaz (503 + açık uyarı)
                    raise
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
        _geo = self.cabin_cfg.get("geometry") or {}
        cabin_params = {
            # marker→origin vektörü ve kabin boyutu yaml'dan (eskiden sabit 0 → QR bulununca
            # koordinatlar origin'e değil marker'a göre çıkıyordu)
            "qr_to_origin_cm": list(_geo.get("qr_to_origin_cm") or [0.0, 0.0, 0.0]),
            "axes_def": "x=right,y=down,z=depth",
            "extent_cm": list(_geo.get("cabin_extent_cm") or [0.0, 0.0, 0.0]),
            "config": self.cabin_cfg,
            # D1.E08: yapılandırma YÜKLENMEDİYSE ArUco bulunsa da kabin kalibre SAYILMAZ (DEFAULT geometri gerçek değil).
            "kabin_yuklendi": bool(getattr(self, "kabin_yuklendi", True)),
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
            # D1.E08 (İG-5.27): kabin yapılandırmasının durumu — tüketiciler (AI Pro, AI Hub) operatöre SÖYLER.
            "kabin_yapilandirmasi": {
                "yuklendi": bool(getattr(self, "kabin_yuklendi", True)),
                "hata": getattr(self, "kabin_hatasi", None),
            },
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
