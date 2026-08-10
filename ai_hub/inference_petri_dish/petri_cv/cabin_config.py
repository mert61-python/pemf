# Author: mertaygn, cglrgrkn
"""cabin_config.py — Fantom kabin YAML loader.

Kedi (inference_cat_organ/lib/cabin_config.py) paterniyle birebir uyumlu.
TEK ArUco marker + cabin_extent_cm + qr_to_origin_cm + camera fixed_position_cm.

Anatomik eksen:
    +X lateral   +Y dorsal (yukari)   +Z Helmholtz aks (sag/kamera tarafi)
"""
from __future__ import annotations
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import yaml


_DIR = Path(__file__).parent.resolve()
DEFAULT_CONFIG_YAML = _DIR / "cabin_config_example.yaml"


# Cabin frame ekseni string -> 3-vector
_AXIS_MAP: dict[str, list[float]] = {
    "+X": [1.0, 0.0, 0.0], "-X": [-1.0, 0.0, 0.0],
    "+Y": [0.0, 1.0, 0.0], "-Y": [0.0, -1.0, 0.0],
    "+Z": [0.0, 0.0, 1.0], "-Z": [0.0, 0.0, -1.0],
}


def axis_to_vector(axis_str: str) -> list[float]:
    """ '+Y' -> [0, 1, 0]. Bilinmeyen -> [0, 1, 0]. """
    return list(_AXIS_MAP.get(str(axis_str).upper(), [0.0, 1.0, 0.0]))


# -----------------------------------------------------------------------------
# Dataclass tabanli config (kedi-pattern raw dict yerine tip-guvenli)
# -----------------------------------------------------------------------------

@dataclass
class HsvRange:
    h_min: int; h_max: int
    s_min: int; s_max: int
    v_min: int; v_max: int

    def as_lower_upper(self):
        lo = np.array([self.h_min, self.s_min, self.v_min], dtype=np.uint8)
        hi = np.array([self.h_max, self.s_max, self.v_max], dtype=np.uint8)
        return lo, hi


@dataclass
class ArucoCfg:
    dict: str
    real_cm: float                        # marker bir kenar uzunlugu
    plane_offset_cm: float
    normal_axis_in_cabin: str             # "+X/-X/+Y/-Y/+Z/-Z"
    refine_corners: bool = True
    use_apriltag_corners: bool = False

    @property
    def real_mm(self) -> float:
        return self.real_cm * 10.0


@dataclass
class GeometryCfg:
    qr_to_origin_cm: list[float]          # marker -> origin vektoru (cabin frame)
    cabin_extent_cm: list[float]          # [X, Y, Z]
    axes: str                             # "x=...,y=...,z=..."

    @property
    def qr_to_origin_mm(self) -> np.ndarray:
        return np.array(self.qr_to_origin_cm, dtype=np.float64) * 10.0


@dataclass
class CameraCfg:
    fixed_position_cm: list[float] | None
    look_at_cm: list[float]
    up_cabin: list[float]
    to_marker_cm: float | None
    to_origin_cm: float | None
    intrinsics_npz: str | None
    device_index: int = 0
    fps: int = 30
    resolution: tuple[int, int] = (1920, 1080)

    @property
    def fixed_position_mm(self) -> np.ndarray | None:
        if self.fixed_position_cm is None:
            return None
        return np.array(self.fixed_position_cm, dtype=np.float64) * 10.0


@dataclass
class PhantomPlateCfg:
    plate_z_cm: float
    width_cm: float
    height_cm: float

    @property
    def plate_z_mm(self) -> float:
        return self.plate_z_cm * 10.0


@dataclass
class SegmentationCfg:
    cancer_blue: HsvRange
    healthy_white: HsvRange
    open_kernel: int
    close_kernel: int
    iterations: int
    adaptive_enabled: bool
    adaptive_block_size: int
    adaptive_C: int
    min_area_px: int
    max_area_px: int


@dataclass
class PnpCfg:
    method: str                           # ITERATIVE / EPNP / SQPNP
    reprojection_error_px: float
    refine_lm: bool


@dataclass
class PhantomPhysicsCfg:
    achieved_B: float
    duty_sum: float


@dataclass
class OutputCfg:
    json_enabled: bool
    json_path: str
    json_pretty: bool
    fastapi_enabled: bool
    fastapi_host: str
    fastapi_port: int
    mqtt_enabled: bool
    mqtt_broker: str
    mqtt_port: int
    mqtt_tls: bool
    mqtt_qos: int
    mqtt_keepalive: int
    mqtt_client_id: str
    mqtt_topic_state: str
    mqtt_topic_cmd: str
    mqtt_username: str | None
    mqtt_password: str | None


@dataclass
class CabinConfig:
    cabin_id: str
    aruco: ArucoCfg
    geometry: GeometryCfg
    camera: CameraCfg
    phantom_plate: PhantomPlateCfg
    segmentation: SegmentationCfg
    pnp: PnpCfg
    phantom: PhantomPhysicsCfg
    output: OutputCfg
    source_path: str = ""

    # ----- yardimcilar -----
    def is_camera_anchored(self) -> bool:
        """fixed_position_cm dolu mu? (kedi paterninden)"""
        return self.camera.fixed_position_cm is not None

    def has_intrinsics(self) -> bool:
        if not self.camera.intrinsics_npz:
            return False
        p = Path(self.camera.intrinsics_npz)
        if not p.is_absolute():
            yaml_dir = Path(self.source_path).parent
            p = yaml_dir / p
        return p.exists()

    def intrinsics_path(self) -> Path:
        """Mutlak yol olarak intrinsics .npz dondur (yoksa exception)."""
        if not self.camera.intrinsics_npz:
            raise FileNotFoundError(
                "camera.intrinsics_npz yapilandirilmamis. "
                "Once calibrate_camera.py calistir.")
        p = Path(self.camera.intrinsics_npz)
        if not p.is_absolute():
            yaml_dir = Path(self.source_path).parent
            p = yaml_dir / p
        if not p.exists():
            raise FileNotFoundError(f"Kalibrasyon .npz yok: {p}")
        return p

    def marker_position_in_cabin_mm(self) -> np.ndarray:
        """Marker merkezinin kabin frame'indeki konumu (mm).

        qr_to_origin_cm: marker -> origin vektoru
        marker_pos     = -qr_to_origin (mm)
        """
        return -self.geometry.qr_to_origin_mm

    def summary(self) -> str:
        g = self.geometry
        a = self.aruco
        c = self.camera
        return (
            f"cabin={self.cabin_id} "
            f"aruco={a.dict}/{a.real_cm}cm "
            f"qr_off={g.qr_to_origin_cm} "
            f"ext={g.cabin_extent_cm} "
            f"cam_fp={c.fixed_position_cm} "
            f"cam_to_orig={c.to_origin_cm}cm "
            f"K_npz={'yes' if self.has_intrinsics() else 'no'}"
        )


# -----------------------------------------------------------------------------
# YAML loader
# -----------------------------------------------------------------------------

def _hsv(d: dict[str, int]) -> HsvRange:
    return HsvRange(
        h_min=int(d["h_min"]), h_max=int(d["h_max"]),
        s_min=int(d["s_min"]), s_max=int(d["s_max"]),
        v_min=int(d["v_min"]), v_max=int(d["v_max"]),
    )


def load_cabin_config(yaml_path: str | os.PathLike | None = None) -> CabinConfig:
    """YAML cabin config dosyasini oku, CabinConfig dataclass'a doldur.

    yaml_path None ise default `cabin_config_example.yaml` kullanilir.
    """
    p = Path(yaml_path) if yaml_path else DEFAULT_CONFIG_YAML
    if not p.exists():
        raise FileNotFoundError(f"Cabin config bulunamadi: {p}")
    with open(p, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)

    ar_r = raw["aruco"]
    geo_r = raw["geometry"]
    cam_r = raw["camera"]
    plate_r = raw["phantom_plate"]
    seg_r = raw["segmentation"]
    morph = seg_r["morphology"]
    adap = seg_r["adaptive"]
    pnp_r = raw["pnp"]
    ph_r = raw["phantom"]
    out_r = raw["output"]
    mq = out_r["mqtt"]

    aruco = ArucoCfg(
        dict=ar_r["dict"],
        real_cm=float(ar_r["real_cm"]),
        plane_offset_cm=float(ar_r.get("plane_offset_cm", 0.0)),
        normal_axis_in_cabin=str(ar_r.get("normal_axis_in_cabin", "+Z")),
        refine_corners=bool(ar_r.get("refine_corners", True)),
        use_apriltag_corners=bool(ar_r.get("use_apriltag_corners", False)),
    )

    geom = GeometryCfg(
        qr_to_origin_cm=list(geo_r["qr_to_origin_cm"]),
        cabin_extent_cm=list(geo_r["cabin_extent_cm"]),
        axes=str(geo_r.get("axes", "x=lateral,y=dorsal,z=axial")),
    )

    cam = CameraCfg(
        fixed_position_cm=(
            list(cam_r["fixed_position_cm"])
            if cam_r.get("fixed_position_cm") is not None else None
        ),
        look_at_cm=list(cam_r.get("look_at_cm", [0.0, 0.0, 0.0])),
        up_cabin=list(cam_r.get("up_cabin", [0.0, 1.0, 0.0])),
        to_marker_cm=(float(cam_r["to_marker_cm"])
                      if cam_r.get("to_marker_cm") is not None else None),
        to_origin_cm=(float(cam_r["to_origin_cm"])
                      if cam_r.get("to_origin_cm") is not None else None),
        intrinsics_npz=cam_r.get("intrinsics_npz"),
        device_index=int(cam_r.get("device_index", 0)),
        fps=int(cam_r.get("fps", 30)),
        resolution=tuple(cam_r.get("resolution", [1920, 1080])),
    )

    plate = PhantomPlateCfg(
        plate_z_cm=float(plate_r.get("plate_z_cm", 0.0)),
        width_cm=float(plate_r.get("width_cm", 8.5)),
        height_cm=float(plate_r.get("height_cm", 13.0)),
    )

    seg = SegmentationCfg(
        cancer_blue=_hsv(seg_r["cancer_blue"]),
        healthy_white=_hsv(seg_r["healthy_white"]),
        open_kernel=int(morph["open_kernel"]),
        close_kernel=int(morph["close_kernel"]),
        iterations=int(morph["iterations"]),
        adaptive_enabled=bool(adap["enabled"]),
        adaptive_block_size=int(adap["block_size"]),
        adaptive_C=int(adap["C"]),
        min_area_px=int(seg_r["min_area_px"]),
        max_area_px=int(seg_r["max_area_px"]),
    )

    pnp = PnpCfg(
        method=str(pnp_r.get("method", "ITERATIVE")),
        reprojection_error_px=float(pnp_r.get("reprojection_error_px", 3.0)),
        refine_lm=bool(pnp_r.get("refine_lm", True)),
    )

    ph = PhantomPhysicsCfg(
        achieved_B=float(ph_r["achieved_B"]),
        duty_sum=float(ph_r["duty_sum"]),
    )

    out = OutputCfg(
        json_enabled=bool(out_r["json"]["enabled"]),
        json_path=out_r["json"]["path"],
        json_pretty=bool(out_r["json"].get("pretty", True)),
        fastapi_enabled=bool(out_r["fastapi"]["enabled"]),
        fastapi_host=out_r["fastapi"]["host"],
        fastapi_port=int(out_r["fastapi"]["port"]),
        mqtt_enabled=bool(mq["enabled"]),
        mqtt_broker=mq["broker"],
        mqtt_port=int(mq["port"]),
        mqtt_tls=bool(mq.get("tls", False)),
        mqtt_qos=int(mq.get("qos", 1)),
        mqtt_keepalive=int(mq.get("keepalive", 60)),
        mqtt_client_id=mq.get("client_id", "petri_cv_pipeline"),
        mqtt_topic_state=mq["topic_state"],
        mqtt_topic_cmd=mq["topic_cmd"],
        mqtt_username=mq.get("username"),
        mqtt_password=mq.get("password"),
    )

    return CabinConfig(
        cabin_id=str(raw["cabin_id"]),
        aruco=aruco, geometry=geom, camera=cam,
        phantom_plate=plate, segmentation=seg, pnp=pnp,
        phantom=ph, output=out, source_path=str(p),
    )


# Geriye uyum: eski API
load_config = load_cabin_config
