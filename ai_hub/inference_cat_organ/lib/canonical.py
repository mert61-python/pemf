# Author: mertaygn, cglrgrkn
"""canonical.py - Atlas constants + paths."""
from __future__ import annotations
from pathlib import Path
import numpy as np

KEYPOINT_NAMES = [
    "nose", "upper_jaw", "lower_jaw", "mouth_end_right", "mouth_end_left",
    "right_eye", "right_earbase", "right_earend",
    "right_antler_base", "right_antler_end",
    "left_eye", "left_earbase", "left_earend",
    "left_antler_base", "left_antler_end",
    "neck_base", "neck_end", "throat_base", "throat_end",
    "back_base", "back_end", "back_middle",
    "tail_base", "tail_end",
    "front_left_thai", "front_left_knee", "front_left_paw",
    "front_right_thai", "front_right_knee", "front_right_paw",
    "back_left_paw", "back_left_thai", "back_right_thai",
    "back_left_knee", "back_right_knee", "back_right_paw",
    "belly_bottom", "body_middle_right", "body_middle_left",
]
assert len(KEYPOINT_NAMES) == 39

ORGAN_IDS = {
    0: "kutu_butun", 1: "mide", 2: "bobrek", 3: "karaciger",
    4: "mesane", 5: "pankreas", 6: "bagirsak",
    7: "kalp", 8: "dalak", 9: "akciger_sag", 10: "akciger_sol",
}   # CANONICAL_ORGANS_3D (1-10) ile birebir; 7-10 eskiden eksikti (isim/CLI choices)

# Kanonik kedi (sphinx, vücut merkezi origin, cm)
#   +X: cranial (head),  +Y: dorsal (sirt),  +Z: anatomic sag
CAT_BODY_LENGTH_CM = 35.0
CAT_BODY_HEIGHT_CM = 20.0


CANONICAL_CAT_3D = {
    # Kafa
    "nose":              ( 19.0, -1.0,  0.0),
    "upper_jaw":         ( 17.5, -2.5,  0.0),
    "lower_jaw":         ( 16.5, -4.0,  0.0),
    "mouth_end_right":   ( 16.0, -2.5,  1.5),
    "mouth_end_left":    ( 16.0, -2.5, -1.5),
    "right_eye":         ( 15.5,  2.0,  2.5),
    "left_eye":          ( 15.5,  2.0, -2.5),
    "right_earbase":     ( 12.5,  5.5,  3.0),
    "left_earbase":      ( 12.5,  5.5, -3.0),
    "right_earend":      ( 11.0,  9.5,  3.5),
    "left_earend":       ( 11.0,  9.5, -3.5),
    # Antler (DLC quadruped icin var, kedi'de yok - earbase yakini)
    "right_antler_base": ( 12.0,  6.0,  3.0),
    "right_antler_end":  ( 10.5,  8.5,  3.0),
    "left_antler_base":  ( 12.0,  6.0, -3.0),
    "left_antler_end":   ( 10.5,  8.5, -3.0),
    # Boyun / bogaz
    "neck_base":         ( 10.0,  4.0,  0.0),
    "neck_end":          ( 12.5,  4.5,  0.0),
    "throat_base":       ( 11.0, -1.0,  0.0),
    "throat_end":        ( 13.0, -1.5,  0.0),
    # Omurga
    "back_base":         (  6.0,  5.0,  0.0),
    "back_middle":       (  0.0,  5.5,  0.0),
    "back_end":          ( -7.0,  5.0,  0.0),
    # Kuyruk (anatomik: kafa-kuyrukucu ~50 cm, body 30 + tail 18-20)
    "tail_base":         (-10.0,  4.0,  0.0),
    "tail_end":          (-28.0,  2.0,  0.0),
    # On bacaklar (knee bent: hafifce one egik)
    "front_left_thai":   (  5.5,  1.0, -3.5),    # omuz
    "front_left_knee":   (  4.5, -5.0, -3.5),
    "front_left_paw":    (  5.0, -9.0, -3.5),    # ön paw biraz one
    "front_right_thai":  (  5.5,  1.0,  3.5),
    "front_right_knee":  (  4.5, -5.0,  3.5),
    "front_right_paw":   (  5.0, -9.0,  3.5),
    # Arka bacaklar (knee bent: hafifce gerige egik, paw yere uzanir)
    "back_left_thai":    ( -8.0,  2.0, -4.0),    # kalca
    "back_left_knee":    ( -7.0, -4.0, -4.5),
    "back_left_paw":     ( -8.5,-13.0, -4.5),    # arka paw daha derin
    "back_right_thai":   ( -8.0,  2.0,  4.0),
    "back_right_knee":   ( -7.0, -4.0,  4.5),
    "back_right_paw":    ( -8.5,-13.0,  4.5),
    # Govde (belly spine'in 5.5 cm altinda anatomik olarak)
    "belly_bottom":      (  0.0, -5.5,  0.0),
    "body_middle_right": (  0.0,  2.0,  5.0),
    "body_middle_left":  (  0.0,  2.0, -5.0),
}


CANONICAL_ORGANS_3D = {
    1: ("mide",         3.0, -1.5, -3.5),   # cranio-ventral SOL
    2: ("bobrek",      -2.0,  2.5,  3.0),   # mid-dorsal SAG (kraniyel)
    3: ("karaciger",    5.5, -1.0,  1.5),   # cranial-merkez, sag'a hafif
    4: ("mesane",      -9.0, -4.0,  0.0),   # caudal-ventral, pelvik giris
    5: ("pankreas",     1.0, -1.5,  1.0),   # midenin caudal'i, sag lob
    6: ("bagirsak",    -3.0, -2.5,  0.0),   # caudo-ventral, abdomen merkezi
    7: ("kalp",         8.5,  0.0,  0.5),   # T4-T6 hizasi, mediastinum
    8: ("dalak",        2.0, -1.0, -4.5),   # sol abdomen, gastrik kurvatura komsu
    9: ("akciger_sag",  7.0,  2.5,  3.0),   # sag toraks, dorsal-lateral
   10: ("akciger_sol",  7.0,  2.5, -3.0),   # sol toraks, dorsal-lateral
}


# ============================================================================
# Pose-Conditional Organ Offsets
# ============================================================================
# CANONICAL_ORGANS_3D base "standing/lateral_recumbent" poz icin tasarlandi.
# Diger poz'larda govde icinde yercekimi/sikisma etkisi ile organlar kayar.
# Her entry: organ_id -> (dx, dy, dz) cm, base pozisyona eklenir.
#
# Notlar (fizyolojik gerekce):
# - sphinx (oturmus, paw'lar altta): omurga dik egim, karaciger-mide hafifce
#   cranio-dorsal'a iter; intestine kompakt; akcigerler standart; mesane
#   ventral'da kalir ama hafif caudal.
# - lateral_recumbent (yan yatmis): yercekimi alttaki tarafa organ kaymasi
#   yaratir, ortalamada hafif ventral kayma; akcigerler ust tarafa.
# - dorsal (sirtustu): organlar dorsal'a (vucut anatomik dorsal'i, yani simdi
#   yere bakan tarafa) kayar; karaciger-mide ventral'dan dorsal'a 1-2 cm.
# - standing (ayakta): mesane/intestine yercekimi ile hafif daha ventral.
# - frontal/oblique: govde 3D pozisyonu belirsiz, default kullan.

POSE_ORGAN_OFFSETS_CM = {
    "standing": {
        # Yercekimi: ventral organlar 1cm daha asagi (ayakta)
        1: (0.0, -0.5, 0.0),    # mide
        4: (0.0, -1.0, 0.0),    # mesane (pelvik tabana yakin)
        6: (0.0, -1.0, 0.0),    # bagirsak
    },
    "sphinx": {
        # Oturmus: ventral organlar hafif kraniyel sikisma
        1: (+0.8, +0.5, 0.0),   # mide cranio-dorsal kayma
        3: (+0.5, +0.3, 0.0),   # karaciger cranio
        5: (+0.3, +0.2, 0.0),   # pankreas
        6: (-0.3, +0.5, 0.0),   # bagirsak hafif kompakt
        4: (-0.3, -0.3, 0.0),   # mesane caudal
    },
    "lateral_recumbent": {
        # Yan yatmis: ventral kayma minimal (vucut yana donmus)
        1: (0.0, -0.3, 0.0),
        6: (0.0, -0.5, 0.0),
        4: (0.0, -0.5, 0.0),
    },
    "lateral": {
        # 'lateral' classify_pose ciktisi (yan profil ayakta/yatmis ortak)
        1: (0.0, -0.3, 0.0),
        4: (0.0, -0.5, 0.0),
        6: (0.0, -0.5, 0.0),
    },
    "dorsal": {
        # Sirtustu: organlar +Y yonune (anatomik dorsal'a) kayar
        1: (0.0, +1.2, 0.0),
        3: (0.0, +0.8, 0.0),
        4: (0.0, +0.8, 0.0),
        6: (0.0, +1.0, 0.0),
    },
    "frontal": {},   # govde 3D belirsiz, no shift
    "oblique": {},
    "unknown": {},
}


def get_organs_atlas_for_pose(pose_type: str) -> dict:
    """CANONICAL_ORGANS_3D'ye pose-spesifik offset'leri uygula.

    Returns: yeni atlas dict, ayni format (oid -> (name, x, y, z)).
    """
    offsets = POSE_ORGAN_OFFSETS_CM.get(pose_type, {})
    out = {}
    for oid, (name, x, y, z) in CANONICAL_ORGANS_3D.items():
        dx, dy, dz = offsets.get(oid, (0.0, 0.0, 0.0))
        out[oid] = (name, round(x + dx, 2), round(y + dy, 2), round(z + dz, 2))
    return out


KEYPOINT_DRIVEN_ATLAS = {
    # organ_id: (name, primary_anchor, fallback_anchors, offset_dir, offset_frac)
    # Her organ TEK bir primary anchor'a baglandi -> sphinx pose'da bile ayrim garantili
    3: ("karaciger",  "neck_base",
        ["throat_base", "back_base"],   "ventral", 0.30),
    1: ("mide",       "back_base",
        ["throat_end", "back_middle"], "ventral", 0.25),
    5: ("pankreas",   "back_middle",
        ["back_base", "back_end"],     "ventral", 0.15),
    2: ("bobrek",     "back_middle",
        ["back_base", "back_end"],     "dorsal",  0.20),    # SIRTA yakin
    6: ("bagirsak",   "back_end",
        ["belly_bottom", "back_middle"], "ventral", 0.20),
    4: ("mesane",     "tail_base",
        ["back_end", "back_left_thai", "back_right_thai"],
        "ventral", 0.20),
    0: ("kutu_butun", "back_middle",
        ["belly_bottom"], None, 0.0),
}
# ============================================================================


BETA_DIM = 4  # sx, sy, sz, BCS
BETA_MEAN = np.array([1.00, 1.00, 1.00, 0.00])
BETA_STD  = np.array([0.15, 0.15, 0.10, 0.35])
BETA_MIN  = np.array([0.70, 0.65, 0.75, -1.0])
BETA_MAX  = np.array([1.40, 1.45, 1.30, +1.0])



# Paths
_DIR = Path(__file__).resolve().parents[1]
MODELS_DIR = _DIR / "models"
# ONNX modelleri (aynı klasörde bulunur, DLC/PyTorch bağımlılığı yok)
POSE_ONNX = MODELS_DIR / "superanimal_quadruped_rtmpose_s.onnx"
DET_ONNX  = MODELS_DIR / "superanimal_quadruped_fasterrcnn_mobilenet_v3_large_fpn.onnx"
YOLO_SEG_CKPT = MODELS_DIR / "yolov8m-seg.onnx"
# Legacy PT yolları (backward-compat için görünmez; runners.py artık ONNX kullanır)
POSE_CKPT = MODELS_DIR / "superanimal_quadruped_rtmpose_s.pt"
DET_CKPT  = MODELS_DIR / "superanimal_quadruped_fasterrcnn_mobilenet_v3_large_fpn.pt"
SUPERANIMAL = "superanimal_quadruped"
POSE_MODEL = "rtmpose_s"
DETECTOR = "fasterrcnn_mobilenet_v3_large_fpn"
N_KP = len(KEYPOINT_NAMES)
