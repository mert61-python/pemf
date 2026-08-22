# Author: mertaygn, cglrgrkn
"""i18n.py - TR/EN strings, organ colors/descriptions, skeleton edges."""
from __future__ import annotations


ORGAN_COLORS = {
    1: (0, 165, 255),     # mide          turuncu
    2: (0, 0, 255),       # bobrek        kirmizi
    3: (0, 255, 255),     # karaciger     sari
    4: (255, 0, 255),     # mesane        magenta
    5: (255, 255, 0),     # pankreas      cyan
    6: (0, 255, 0),       # bagirsak      yesil
    7: (120, 50, 200),    # kalp          mor-pembe (mediastinum)
    8: (60, 130, 180),    # dalak         steel-blue
    9: (210, 210, 230),   # akciger_sag   acik pembe-gri
   10: (180, 220, 210),   # akciger_sol   acik cyan-gri
}


ORGAN_DESC = {
    1: "mide (cranio-ventral)",
    2: "bobrek (dorsal, mid)",
    3: "karaciger (cranio-ventral)",
    4: "mesane (caudo-ventral)",
    5: "pankreas (orta-ventral)",
    6: "bagirsak (caudo-ventral)",
    7: "kalp (mediastinum)",
    8: "dalak (sol abdomen)",
    9: "sag akciger (toraks)",
   10: "sol akciger (toraks)",
}


STRINGS = {
    "tr": {
        "head": "BAS", "tail": "KUYRUK",
        "head_lc": "bas", "tail_lc": "kuyruk",
        "cranial": "cranial(+X)", "dorsal": "dorsal(+Y)", "right": "sag(+Z)",
        "zone_head": "Bas", "zone_thorax": "Toraks",
        "zone_abdomen": "Karin", "zone_pelvis": "Pelvis/Kuyruk",
        "camera_view": "Kameradaki goruntu",
        "fitted_pose": "Fit poz",
        "scale_unit": "px/cm", "reliability": "Guvenilirlik",
        "organs": "Organlar", "method": "Yontem",
        "pose": "Poz", "kpts": "keypoint",
        "target": "Hedef", "input_image": "girdi",
        "yolo_seg": "YOLO segment", "conf": "guven",
        "dlc_pose": "DLC Quadruped poz tahmini",
        "fit_lbl": "PnP fit (Procrustes)", "scale": "Olcek",
        "reproj_err": "Reproj hata", "inliers": "Inlier KP",
        "mirror_warn": "Sag/sol KP karisikligi",
        "organ_summary": "Organ ozeti",
        "scale_bar": "10 cm",
    },
    "en": {
        "head": "HEAD", "tail": "TAIL",
        "head_lc": "head", "tail_lc": "tail",
        "cranial": "cranial(+X)", "dorsal": "dorsal(+Y)", "right": "right(+Z)",
        "zone_head": "Head", "zone_thorax": "Thorax",
        "zone_abdomen": "Abdomen", "zone_pelvis": "Pelvis/Tail",
        "camera_view": "Camera image",
        "fitted_pose": "Fitted pose",
        "scale_unit": "px/cm", "reliability": "Reliability",
        "organs": "Organs", "method": "Method",
        "pose": "Pose", "kpts": "keypoints",
        "target": "Target", "input_image": "input",
        "yolo_seg": "YOLO segment", "conf": "conf",
        "dlc_pose": "DLC Quadruped pose",
        "fit_lbl": "PnP fit (Procrustes)", "scale": "Scale",
        "reproj_err": "Reproj error", "inliers": "Inlier KP",
        "mirror_warn": "L/R keypoint mismatch",
        "organ_summary": "Organ summary",
        "scale_bar": "10 cm",
    },
}


def _s(lang: str, key: str) -> str:
    return STRINGS.get(lang, STRINGS["tr"]).get(key, key)


ORGAN_NAMES_I18N = {
    "tr": {
        1: "mide", 2: "bobrek", 3: "karaciger", 4: "mesane",
        5: "pankreas", 6: "bagirsak", 7: "kalp", 8: "dalak",
        9: "sag akciger", 10: "sol akciger",
    },
    "en": {
        1: "stomach", 2: "kidney", 3: "liver", 4: "bladder",
        5: "pancreas", 6: "intestine", 7: "heart", 8: "spleen",
        9: "R lung", 10: "L lung",
    },
}


def _organ_name(oid: int, lang: str) -> str:
    """ID'den dile gore organ adi (display)."""
    return ORGAN_NAMES_I18N.get(lang, ORGAN_NAMES_I18N["tr"]).get(oid, str(oid))

# DLC iskelet baglantilari (kafa, omurga, bacaklar)


SKELETON_EDGES = [
    # Kafa
    ("nose", "upper_jaw"), ("nose", "lower_jaw"),
    ("nose", "left_eye"), ("nose", "right_eye"),
    ("left_eye", "left_earbase"), ("right_eye", "right_earbase"),
    ("left_earbase", "left_earend"), ("right_earbase", "right_earend"),
    ("nose", "neck_base"),
    # Omurga
    ("neck_base", "throat_base"), ("throat_base", "throat_end"),
    ("neck_base", "back_base"),
    ("back_base", "back_middle"), ("back_middle", "back_end"),
    ("back_end", "tail_base"), ("tail_base", "tail_end"),
    # On bacaklar
    ("back_base", "front_left_thai"), ("front_left_thai", "front_left_knee"),
    ("front_left_knee", "front_left_paw"),
    ("back_base", "front_right_thai"), ("front_right_thai", "front_right_knee"),
    ("front_right_knee", "front_right_paw"),
    # Arka bacaklar
    ("back_end", "back_left_thai"), ("back_left_thai", "back_left_knee"),
    ("back_left_knee", "back_left_paw"),
    ("back_end", "back_right_thai"), ("back_right_thai", "back_right_knee"),
    ("back_right_knee", "back_right_paw"),
    # Govde yanlari
    ("back_middle", "body_middle_left"), ("back_middle", "body_middle_right"),
    ("back_middle", "belly_bottom"),
]
