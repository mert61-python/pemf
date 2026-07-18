"""
PEMF AI Servisi — predictor kayıt/yükleme (Faz 2a + 2b).
ai_hub predictor'larını / ultralytics YOLO'ları GPU ile tembel-yükler ve önbelleğe alır.
Ağırlıklar /models (mount) altından explicit model_path ile; kod ai_hub/ (imajda).
  • Saf-ONNX (torch'suz da çalışır): histopath, sound
  • YOLO/ultralytics (torch gerekir, .onnx inference onnxruntime-gpu CUDA): kidney_ct, segmentation, landmark
Yeni model eklemek = REGISTRY'ye bir giriş.

DEVICE: hepsi ai_service.gpu üzerinden (tek nokta). GPU gerçekten çalışıyorsa CUDA, yoksa/başarısızsa
(ör. RTX 5090/Blackwell'de eski torch) OTOMATİK CPU — GPU hatası yerine CPU uyarısı.
"""
import os
import threading

from ai_service import gpu

MODELS_DIR = os.environ.get("PEMF_AI_MODELS_DIR", "/models")

_lock = threading.Lock()
_cache = {}


def _mp(rel: str) -> str:
    return os.path.join(MODELS_DIR, rel)


# ── saf-ONNX predictor'lar (device gpu.torch_device() → CUDA/CPU; torch import ETMEZ) ──
def _load_histopath():
    from ai_hub.inference_renal_histopath_kmc import RenalHistopathClassifier
    return RenalHistopathClassifier(
        model_path=_mp("ai_hub/inference_renal_histopath_kmc/v22_kmc_classictrio_kmc.onnx"),
        backend="onnx", device=gpu.torch_device())


def _load_cat_sound():
    from ai_hub.inference_cat_sound import CatSoundClassifier
    return CatSoundClassifier(
        model_path=_mp("ai_hub/inference_cat_sound/EfficientNet_Lite0.onnx"),
        runtime="onnx", device=gpu.torch_device())


# ── ultralytics YOLO (torch importlu; .onnx inference GPU'da onnxruntime-gpu CUDA) ──
def _yolo(rel: str, task: str):
    from ultralytics import YOLO
    return YOLO(_mp(rel), task=task)


def _load_kidney_ct():
    from ai_hub.inference_human_kidney_ct import KidneyCTDetector
    return KidneyCTDetector(
        model_path=_mp("ai_hub/inference_human_kidney_ct/yolov8s.onnx"),
        backend="onnx", device=gpu.torch_device())


def _load_segmentation():
    return _yolo("ai_hub/cat_segmentation/yolov8m-seg.onnx", "segment")


def _load_landmark():
    return _yolo("ai_hub/cat_landmark/yolo26m-pose.onnx", "pose")


# ── Faz 2c: thermal (edit'li providers), cat_organ (models_dir param), + gömülü CPU modeller ──
def _load_thermal():
    from ai_hub.cat_thermal.inference_cat_thermal import CatThermalPredictor
    return CatThermalPredictor(model_path=_mp("ai_hub/cat_thermal/GhostNetV2.onnx"),
                               providers=gpu.onnx_providers())


def _load_cat_organ():
    from ai_hub.inference_cat_organ.catorgan_predictor import CatOrganPredictor
    return CatOrganPredictor(device=gpu.torch_device(), models_dir=_mp("ai_hub/inference_cat_organ/models"))


def _load_cat_disease():
    from ai_hub.cat_disease.inference_cat_disease import CatDiseasePredictor
    return CatDiseasePredictor()   # XGBoost.pkl gömülü (Dockerfile.ai.dockerignore dahil eder)


def _load_kidney_rna():
    from ai_hub.inference_human_kidney_rna import KidneyRnaPredictor
    return KidneyRnaPredictor()    # mlp onnx gömülü


def _load_reticulocytes():
    return _yolo("ai_hub/feline_reticulocytes/yolov8s.onnx", "detect")


# ── kabin-CV pipeline'ları: predictor'ı explicit /models yoluyla kur → pipeline'a enjekte ──
def _load_em_fantom():
    from ai_hub.inference_em_fantom.phantom_cv import PhantomCvPipeline, load_cabin_config
    from ai_hub.inference_em_fantom.inference_em_fantom import PhantomPredictor
    cfg = load_cabin_config(None)  # gömülü cabin_config_example.yaml (imajda)
    predictor = PhantomPredictor(
        onnx_path=_mp("ai_hub/inference_em_fantom/BiLSTM_XXL_Raw.onnx"), providers=gpu.onnx_providers())
    return {"cfg": cfg, "predictor": predictor, "cls": PhantomCvPipeline}


def _load_em_petri():
    from ai_hub.inference_petri_dish.petri_cv import PetriCvPipeline, load_cabin_config
    from ai_hub.inference_em_petri.inference_em_petri import PetriPredictor
    cfg = load_cabin_config(None)
    predictor = PetriPredictor(
        onnx_path=_mp("ai_hub/inference_em_petri/BaggingRegressor.onnx"), providers=gpu.onnx_providers())
    yolo_path = _mp("ai_hub/inference_petri_dish/yolo11m-seg.onnx")
    warm = PetriCvPipeline(cfg, yolo_model_path=yolo_path, yolo_device=gpu.yolo_device())  # YOLO'yu bir kez kur
    return {"cfg": cfg, "predictor": predictor, "yolo": warm.yolo, "yolo_path": yolo_path,
            "cls": PetriCvPipeline}


def _load_em_kedi():
    # AI Pro bobin-sürüş modeli: em_kedi KediPredictor (BiLSTM_XXL_Raw ONNX, GPU). em_fantom şablonu:
    # ONNX /models'ten explicit yol; scaler_X/extra/y küçük .pkl → imajda gömülü (KediPredictor _DIR default).
    from ai_hub.em_kedi.inference_em_kedi import KediPredictor
    return KediPredictor(onnx_path=_mp("ai_hub/em_kedi/BiLSTM_XXL_Raw.onnx"), providers=gpu.onnx_providers())


REGISTRY = {
    "histopath":    {"loader": _load_histopath,    "kind": "image", "title": "Böbrek Histopatoloji Grade (5 sınıf)"},
    "sound":        {"loader": _load_cat_sound,     "kind": "audio", "title": "Kedi Sesi Sınıflandırma (10 sınıf)"},
    "kidney_ct":    {"loader": _load_kidney_ct,     "kind": "image", "title": "Böbrek CT Tespit (YOLOv8s, taş/kist/normal)"},
    "segmentation": {"loader": _load_segmentation,  "kind": "image", "title": "Kedi Segmentasyon (YOLOv8m-seg)"},
    "landmark":     {"loader": _load_landmark,      "kind": "image", "title": "FGS Ağrı Skoru (YOLO-pose + landmark)"},
    "thermal":      {"loader": _load_thermal,       "kind": "image", "title": "Termal Sağlık Sınıflandırma (GhostNetV2)"},
    "cat_organ":    {"loader": _load_cat_organ,     "kind": "image", "title": "Kedi Organ 3B Lokalizasyon (3 ONNX)"},
    "disease":      {"loader": _load_cat_disease,   "kind": "json",  "title": "Kedi Hastalık (XGBoost)"},
    "kidney_rna":   {"loader": _load_kidney_rna,    "kind": "csv",   "title": "Böbrek RNA-seq KIRC (MLP)"},
    "reticulocytes":{"loader": _load_reticulocytes, "kind": "image", "title": "Retikülosit Sayımı (YOLOv8s detect)"},
    "em_fantom":    {"loader": _load_em_fantom,     "kind": "cv",    "title": "Fantom Tümör (CV + BiLSTM)"},
    "em_petri":     {"loader": _load_em_petri,      "kind": "cv",    "title": "Petri Kuyu (YOLO-seg + CV + Bagging)"},
    "em_kedi":      {"loader": _load_em_kedi,       "kind": "json",  "title": "AI Pro Bobin Sürüş (em_kedi BiLSTM: x/y/z/organ → D/P/E)"},
}


def get(name: str):
    if name not in REGISTRY:
        raise KeyError(name)
    with _lock:
        if name not in _cache:
            _cache[name] = REGISTRY[name]["loader"]()
        return _cache[name]


def loaded():
    return sorted(_cache.keys())
