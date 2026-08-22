# Author: mertaygn, cglrgrkn
"""cabin_config.py - YAML cabin config loader + CLI argument merge.

Level 3 setup: kabin kurulurken bir kere yapilandirilan dosya.
Klinikte gunluk kullanim: foto + sabit yaml -> tam 3D cabin coords.

YAML semasi (cabin_config_example.yaml gor):

  cabin_id: "klinik_v1"
  aruco:
    dict: DICT_5X5_50
    real_cm: 10.0
    plane_offset_cm: -2.0           # marker plane -> cat plane (Z farki)
  geometry:
    qr_to_origin_cm: [-25.0, 0.0, -15.0]
    cabin_extent_cm: [60, 40, 30]
    axes: "x=cranial,y=dorsal,z=right"
  camera:
    to_marker_cm: 60.0              # kamera lens -> marker merkez (cm)
    to_origin_cm: 65.0              # kamera lens -> kabin origin (cm)
    intrinsics_npz: null            # opsiyonel: "calib_klinik_v1.npz" -> K,D
    fixed_position_cm: null         # opsiyonel: [x,y,z] kabin frame'inde
"""
from __future__ import annotations
from pathlib import Path
from typing import Any
import numpy as np


DEFAULT_CONFIG = {
    "cabin_id": None,
    "aruco": {
        "dict": "DICT_5X5_50",
        "real_cm": 10.0,
        "plane_offset_cm": 0.0,
        # Marker yuzeyinin (face) cabin frame'inde baktigi eksen:
        #   "+X" / "-X" / "+Y" / "-Y" / "+Z" / "-Z"
        # Plane offset bu eksene gore uygulanir.
        # Default "+Y": floor marker, face up (tavan kamera setup).
        "normal_axis_in_cabin": "+Y",
    },
    "geometry": {
        "qr_to_origin_cm": [0.0, 0.0, 0.0],
        "cabin_extent_cm": [0.0, 0.0, 0.0],
        "axes": "x=cranial,y=dorsal,z=right",
    },
    "camera": {
        "to_marker_cm": None,
        "to_origin_cm": None,
        "intrinsics_npz": None,
        # Camera-anchored mode (yan kamera icin onerilen):
        # Verilirse, marker rotation hesabi yerine fixed_position + look_at
        # kullanilir. Daha kararli + interpretable.
        "fixed_position_cm": None,
        "look_at_cm": [0.0, 0.0, 0.0],     # default: cabin origin'e bakar
        "up_cabin": [0.0, 1.0, 0.0],        # default: cabin +Y (dorsal up)
    },
}


# Cabin frame ekseni string -> 3-vector
_AXIS_MAP = {
    "+X": [1.0, 0.0, 0.0], "-X": [-1.0, 0.0, 0.0],
    "+Y": [0.0, 1.0, 0.0], "-Y": [0.0, -1.0, 0.0],
    "+Z": [0.0, 0.0, 1.0], "-Z": [0.0, 0.0, -1.0],
}


def axis_to_vector(axis_str: str):
    """ '+Y' -> [0, 1, 0]. Bilinmeyen -> [0, 1, 0] (default dorsal). """
    return list(_AXIS_MAP.get(str(axis_str).upper(), [0.0, 1.0, 0.0]))


def is_camera_anchored(cfg: dict) -> bool:
    """fixed_position_cm dolu mu? Camera-anchored mod kullanilacak mi?"""
    fp = (cfg.get("camera") or {}).get("fixed_position_cm")
    return fp is not None and len(fp) == 3


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursive dict merge — override base."""
    out = dict(base)
    for k, v in override.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_cabin_config(yaml_path: str | None) -> dict:
    """YAML dosyasini yukle, default'lar ile birlestir.

    yaml_path None ise default config doner (kamera = None -> weak-perspective).
    """
    cfg = dict(DEFAULT_CONFIG)
    # deep copy of defaults
    cfg = _deep_merge({}, DEFAULT_CONFIG)
    if yaml_path is None:
        return cfg
    p = Path(yaml_path).expanduser().resolve()
    if not p.exists():
        raise FileNotFoundError(f"Cabin config bulunamadi: {p}")
    import yaml
    with p.open("r", encoding="utf-8") as f:
        loaded = yaml.safe_load(f) or {}
    merged = _deep_merge(cfg, loaded)
    merged["_yaml_path"] = str(p)
    return merged


def apply_cli_overrides(cfg: dict, args) -> dict:
    """CLI argumanlari yaml'dan oncelikli ise override et.

    Sadece kullanici tarafindan acikca verilen CLI args override etmeli;
    default degerler yaml'i ezmemeli. Bu yuzden args'da `_user_set` kontrol
    edilir (argparse default'tan farklilik).
    """
    # Aruco
    if getattr(args, "aruco_real_cm", None) is not None and \
       args.aruco_real_cm != 10.0:
        cfg["aruco"]["real_cm"] = float(args.aruco_real_cm)
    if getattr(args, "aruco_dict", None) and args.aruco_dict != "DICT_5X5_50":
        cfg["aruco"]["dict"] = str(args.aruco_dict)
    # Geometry
    qr_off = getattr(args, "qr_to_cabin_origin", None)
    if qr_off is not None and qr_off != [0.0, 0.0, 0.0]:
        cfg["geometry"]["qr_to_origin_cm"] = list(qr_off)
    ext = getattr(args, "cabin_extent_cm", None)
    if ext is not None and ext != [0.0, 0.0, 0.0]:
        cfg["geometry"]["cabin_extent_cm"] = list(ext)
    if getattr(args, "cabin_axes", None) and \
       args.cabin_axes != "x=right,y=down,z=depth":
        cfg["geometry"]["axes"] = str(args.cabin_axes)
    # Camera (CLI Seviye 2'den gelirse)
    if getattr(args, "camera_to_marker_cm", None) is not None:
        cfg["camera"]["to_marker_cm"] = float(args.camera_to_marker_cm)
    if getattr(args, "camera_to_origin_cm", None) is not None:
        cfg["camera"]["to_origin_cm"] = float(args.camera_to_origin_cm)
    if getattr(args, "camera_intrinsics_npz", None):
        cfg["camera"]["intrinsics_npz"] = str(args.camera_intrinsics_npz)
    return cfg


def has_perspective_data(cfg: dict) -> bool:
    """Yeterli kamera bilgisi var mi (perspektif moda gec)?

    True: intrinsics_npz mevcut VEYA to_marker_cm verildi.
    """
    cam = cfg.get("camera", {}) or {}
    if cam.get("intrinsics_npz"):
        p = Path(cam["intrinsics_npz"])
        if not p.is_absolute():
            yaml_dir = Path(cfg.get("_yaml_path", "."))
            p = (yaml_dir.parent / p) if yaml_dir.is_file() else p
        if p.exists():
            return True
    if cam.get("to_marker_cm") is not None:
        return True
    return False


def summary(cfg: dict) -> str:
    """Tek satir ozet (log icin)."""
    g = cfg["geometry"]
    a = cfg["aruco"]
    c = cfg["camera"]
    return (
        f"cabin={cfg.get('cabin_id','?')} "
        f"aruco={a['dict']}/{a['real_cm']}cm "
        f"qr_off={g['qr_to_origin_cm']} "
        f"cam_to_mark={c.get('to_marker_cm')}cm "
        f"cam_to_orig={c.get('to_origin_cm')}cm "
        f"K_npz={'yes' if c.get('intrinsics_npz') else 'no'}"
    )
