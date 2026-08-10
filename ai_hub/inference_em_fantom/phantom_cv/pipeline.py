# Author: mertaygn, cglrgrkn
"""pipeline.py — Sentetik bobrek fantom CV (FANTOM-MERKEZLI).

Direkt FANTOM tespit edip ona odaklan. Bobin/kalibrasyon opsiyonel.

8 adim:
  1. Goruntu (file/camera)
  2. cv2.undistort (kalibrasyon varsa)
  3. FANTOM TESPIT (find_phantom)
     - HSV adaylar -> mavi nokta sayisi + solidity -> en iyi aday = fantom
  4. Tumor (mavi) + yanik (kahverengi) FANTOM ICINDE ara
  5. Kalibrasyon (oncelik sirasi):
     A) ArUco PnP varsa (kedi pattern)
     B) phantom.length_cm verilirse: fantom contour uzunlugundan mm/px
     C) Default: piksel koordinat (kullanici sonra mm cevirir)
  6. Tumor centroid -> fantom merkezi rel piksel veya mm
  7. PhantomPredictor (organ_id=1)
  8. JSON + 7-panel TR+EN
"""
from __future__ import annotations
import json
import os
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .cabin_config import CabinConfig, load_cabin_config
from .coord_transform import (
    CameraIntrinsics, CabinPose, MarkerDetection,
    detect_aruco_marker, solve_cabin_pose, pixel_to_cabin_mm,
    undistort_image, approx_intrinsics_from_marker,
)
from .color_segment import (
    segment_phantom, segment_phantoms_multi, find_phantom, find_phantoms,
    phantom_from_seed, PhantomDetection, Region, TUMOR, HEALTHY,
)
from .manual_select import select_seed_interactive, headless_check
from . import render as rd


_THIS_DIR = Path(__file__).parent.resolve()
_PARENT_DIR = _THIS_DIR.parent
if str(_PARENT_DIR) not in sys.path:
    sys.path.insert(0, str(_PARENT_DIR))

from inference_em_fantom import PhantomPredictor    # noqa: E402


@dataclass
class RegionPrediction:
    organ_id: int
    label: str
    centroid_px: tuple[float, float]
    centroid_cabin_mm: tuple[float, float, float]
    centroid_cabin_cm: tuple[float, float, float]
    area_px: int
    area_mm2: float
    bbox_px: tuple[int, int, int, int]
    D: list[float] = field(default_factory=list)
    P: list[float] = field(default_factory=list)
    E_healthy: float = 0.0
    E_cancer: float = 0.0
    E_avg: float = 0.0


@dataclass
class PipelineResult:
    schema_version: str = "v1.1"
    success: bool = False
    timestamp: float = 0.0
    cabin_id: str = ""
    image_name: str = ""
    n_tumor: int = 0
    n_healthy: int = 0
    method: str = ""                                 # "aruco_pnp" / "phantom_length" / "pixel"
    mm_per_px: float = 1.0                           # 1.0 = piksel mod
    phantom_detection: dict[str, Any] = field(default_factory=dict)
    cabin_pose: dict[str, Any] = field(default_factory=dict)
    camera_calib: dict[str, Any] = field(default_factory=dict)
    tumor_regions: list[RegionPrediction] = field(default_factory=list)
    healthy_regions: list[RegionPrediction] = field(default_factory=list)
    timing_ms: dict[str, float] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict:
        d = {k: v for k, v in self.__dict__.items()
             if k not in ("tumor_regions", "healthy_regions")}
        d["tumor_regions"] = [asdict(r) for r in self.tumor_regions]
        d["healthy_regions"] = [asdict(r) for r in self.healthy_regions]
        return d


class PhantomCvPipeline:
    """Fantom-merkezli sentetik bobrek CV pipeline."""

    def __init__(self, cfg: CabinConfig | str | os.PathLike | None = None,
                 *, phantom_length_cm: float | None = None,
                 manual_fallback: bool = True):
        if isinstance(cfg, CabinConfig):
            self.cfg = cfg
        else:
            self.cfg = load_cabin_config(cfg)
        # Bilinen fantom uzunlugu (cm) — calibrate icin (orn. 10 cm tipik bobrek)
        self.phantom_length_cm = phantom_length_cm
        self.manual_fallback = manual_fallback

        self.intrinsics: CameraIntrinsics | None = None
        self._approx_intrinsics = False
        if self.cfg.has_intrinsics():
            self.intrinsics = CameraIntrinsics.from_npz(
                str(self.cfg.intrinsics_path()))

        self._predictor: PhantomPredictor | None = None

    @property
    def predictor(self) -> PhantomPredictor:
        if self._predictor is None:
            self._predictor = PhantomPredictor()
        return self._predictor

    def _ensure_intrinsics(self, image_bgr: np.ndarray) -> bool:
        if self.intrinsics is not None:
            return True
        approx = approx_intrinsics_from_marker(image_bgr, self.cfg)
        if approx is None:
            h, w = image_bgr.shape[:2]
            f = float(max(h, w))
            K = np.array([[f, 0, w / 2.0], [0, f, h / 2.0], [0, 0, 1.0]],
                         dtype=np.float64)
            D = np.zeros(5, dtype=np.float64)
            self.intrinsics = CameraIntrinsics(K, D, (w, h), float("nan"))
            self._approx_intrinsics = True
            return True
        self.intrinsics = approx
        self._approx_intrinsics = True
        return True

    def process_image(self, image_bgr: np.ndarray,
                      *,
                      image_name: str = "",
                      achieved_B: float | None = None,
                      duty_sum: float | None = None,
                      ) -> tuple[PipelineResult, dict]:
        t0 = time.perf_counter()
        result = PipelineResult(success=False, timestamp=time.time(),
                                cabin_id=self.cfg.cabin_id,
                                image_name=image_name)
        timings: dict[str, float] = {}
        ctx: dict = {"img_und": None, "regions": None,
                     "phantom": None, "cabin_pose": None, "marker": None}

        self._ensure_intrinsics(image_bgr)
        result.camera_calib = {
            "K": self.intrinsics.K.tolist(),
            "D": self.intrinsics.D.tolist(),
            "image_size": list(self.intrinsics.image_size),
            "rms": self.intrinsics.rms,
            "approx": self._approx_intrinsics,
        }

        # 1) Undistort
        t1 = time.perf_counter()
        img_und = undistort_image(image_bgr, self.intrinsics)
        timings["undistort"] = (time.perf_counter() - t1) * 1000
        ctx["img_und"] = img_und

        # 2) ArUco varsa kalibrasyon (kedi pattern)
        t1 = time.perf_counter()
        marker_det = detect_aruco_marker(img_und, self.cfg.aruco)
        cabin_pose = None
        if marker_det is not None:
            cabin_pose = solve_cabin_pose(
                img_und, self.intrinsics,
                self.cfg.aruco, self.cfg.geometry, self.cfg.pnp,
            )
            if cabin_pose is not None:
                result.cabin_pose = {
                    "marker_id": cabin_pose.marker_id,
                    "tvec_mm": cabin_pose.tvec.flatten().tolist(),
                    "reproj_error_px": cabin_pose.reproj_error_px,
                }
                ctx["cabin_pose"] = cabin_pose
                ctx["marker"] = {
                    "marker_id": cabin_pose.marker_id,
                    "corners_px": marker_det.corners_px.tolist(),
                }
        timings["aruco"] = (time.perf_counter() - t1) * 1000

        # 3) FANTOM TESPIT — TEK fantom (FP riskini azaltir)
        t1 = time.perf_counter()
        phantoms = find_phantoms(img_und, self.cfg.segmentation,
                                 max_phantoms=1)
        detect_method = "auto_hsv"
        h_img, w_img = img_und.shape[:2]
        img_area = h_img * w_img
        auto_quality_ok = bool(phantoms) and any(
            (img_area * 0.005 < p.area_px < img_area * 0.90
             and p.n_blue_inside >= 1)
            for p in phantoms
        )
        if not auto_quality_ok and self.manual_fallback:
            if not headless_check():
                title = f"Fantom MERKEZINI tikla ({image_name or 'image'})"
                seed = select_seed_interactive(
                    img_und, window_title=title,
                    instruction=("HSV otomatik basarisiz. Silikon bobrek "
                                 "fantom MERKEZINI tikla, ENTER=onayla "
                                 "(ESC=atla)"),
                )
                if seed is not None:
                    p_man = phantom_from_seed(
                        img_und, self.cfg.segmentation, seed)
                    if p_man is not None:
                        phantoms = [p_man]
                        detect_method = "manual_click"
        if not phantoms:
            result.error = "phantom_not_detected"
            result.timing_ms = timings
            result.timing_ms["total"] = (time.perf_counter() - t0) * 1000
            return result, ctx
        ctx["phantoms"] = phantoms
        ctx["phantom"] = phantoms[0]    # geriye uyum
        result.phantom_detection = {
            "n_phantoms": len(phantoms),
            "primary": {
                "centroid_px": list(phantoms[0].centroid_px),
                "area_px": phantoms[0].area_px,
                "bbox_px": list(phantoms[0].bbox_px),
                "solidity": phantoms[0].solidity,
                "n_blue_inside": phantoms[0].n_blue_inside,
                "score": phantoms[0].score,
            },
            "all_centroids_px": [list(p.centroid_px) for p in phantoms],
            "all_areas_px": [p.area_px for p in phantoms],
            "detect_method": detect_method,
        }
        timings["phantom_detect"] = (time.perf_counter() - t1) * 1000

        # 4) Kalibrasyon mm/px (en buyuk fantoma gore)
        primary = max(phantoms, key=lambda p: p.area_px)
        if cabin_pose is not None:
            result.method = "aruco_pnp"
            result.mm_per_px = 0.0
        elif self.phantom_length_cm is not None:
            bx, by, bw, bh = primary.bbox_px
            length_px = float(max(bw, bh))
            result.method = "phantom_length"
            result.mm_per_px = (self.phantom_length_cm * 10.0) / length_px
        else:
            result.method = "pixel"
            result.mm_per_px = 1.0

        # 5) Tumor segmentasyon HER FANTOM icin ayri + duplicate engelle
        t1 = time.perf_counter()
        all_tumors: list[Region] = []
        all_healthy: list[Region] = []
        seen_centroids: list[tuple[float, float]] = []
        for p in phantoms:
            segs_i = segment_phantom(img_und, self.cfg.segmentation,
                                     phantom=p)
            for r in segs_i["tumor"]:
                cx, cy = r.centroid_px
                # 15 px mesafe duplikasyon
                if any(abs(cx - sx) < 15 and abs(cy - sy) < 15
                       for sx, sy in seen_centroids):
                    continue
                seen_centroids.append((cx, cy))
                all_tumors.append(r)
            all_healthy.extend(segs_i["healthy"])
        segs = {"phantoms": phantoms, "tumor": all_tumors,
                "healthy": all_healthy}
        timings["segmentation"] = (time.perf_counter() - t1) * 1000
        ctx["regions"] = segs

        # 6) Piksel -> mm donusum (primary fantom merkez ref)
        t1 = time.perf_counter()
        B = self.cfg.phantom.achieved_B if achieved_B is None else achieved_B
        duty = self.cfg.phantom.duty_sum if duty_sum is None else duty_sum
        ph_cx, ph_cy = primary.centroid_px

        def _to_mm(px: tuple[float, float]) -> tuple[float, float, float]:
            if cabin_pose is not None:
                v = pixel_to_cabin_mm(px, cabin_pose, self.intrinsics, self.cfg)
                return float(v[0]), float(v[1]), float(v[2])
            dx_mm = (px[0] - ph_cx) * result.mm_per_px
            dy_mm = (ph_cy - px[1]) * result.mm_per_px
            return float(dx_mm), float(dy_mm), 0.0

        def _make(r: Region, predict: bool) -> RegionPrediction:
            xyz_mm = _to_mm(r.centroid_px)
            area_mm2 = r.area_px * (result.mm_per_px ** 2) if result.mm_per_px else 0.0
            rp = RegionPrediction(
                organ_id=r.organ_id, label=r.label,
                centroid_px=r.centroid_px,
                centroid_cabin_mm=xyz_mm,
                centroid_cabin_cm=(xyz_mm[0]/10, xyz_mm[1]/10, xyz_mm[2]/10),
                area_px=r.area_px, area_mm2=area_mm2, bbox_px=r.bbox_px,
            )
            if predict and r.organ_id in (0, 1):
                pr = self.predictor.predict(
                    x=xyz_mm[0], y=xyz_mm[1], z=xyz_mm[2],
                    organ_id=r.organ_id, achieved_B=B, duty_sum=duty,
                )
                rp.D = [pr[f"D{i}"] for i in range(1, 8)]
                rp.P = [pr[f"P{i}"] for i in range(1, 8)]
                rp.E_healthy = pr["result_E_healthy"]
                rp.E_cancer = pr["result_E_cancer"]
                rp.E_avg = pr["result_E_avg"]
            return rp

        for r in segs["tumor"]:
            result.tumor_regions.append(_make(r, predict=True))
        for r in segs["healthy"]:
            result.healthy_regions.append(_make(r, predict=True))

        timings["predictor"] = (time.perf_counter() - t1) * 1000
        result.n_tumor = len(result.tumor_regions)
        result.n_healthy = len(result.healthy_regions)
        result.success = True
        timings["total"] = (time.perf_counter() - t0) * 1000
        result.timing_ms = timings
        return result, ctx

    def render_panels(self, ctx: dict, result: PipelineResult,
                      *, lang: str = "tr") -> dict[str, np.ndarray]:
        regions_pred = result.tumor_regions + result.healthy_regions
        return rd.render_all_panels(
            ctx["img_und"],
            phantoms=ctx.get("phantoms") or ([ctx["phantom"]]
                                              if ctx.get("phantom")
                                              else []),
            marker=ctx.get("marker"),
            regions=ctx.get("regions") or {"tumor": [], "healthy": []},
            regions_pred=regions_pred,
            method=result.method,
            mm_per_px=result.mm_per_px,
            lang=lang,
        )

    def process_file(self, image_path, **kwargs):
        img = cv2.imread(str(image_path))
        if img is None:
            return PipelineResult(success=False, timestamp=time.time(),
                                  cabin_id=self.cfg.cabin_id,
                                  error=f"image_read_fail: {image_path}"), {}
        kwargs.setdefault("image_name", Path(image_path).name)
        return self.process_image(img, **kwargs)

    def write_results(self, image_path, result: PipelineResult, ctx: dict,
                      out_root: str | os.PathLike = "results") -> Path:
        stem = Path(image_path).stem
        out_dir = Path(out_root) / stem
        out_dir.mkdir(parents=True, exist_ok=True)
        with open(out_dir / "result.json", "w", encoding="utf-8") as fh:
            json.dump(result.to_dict(), fh, indent=2, default=str,
                      ensure_ascii=False)
        if result.success and ctx.get("img_und") is not None:
            for lang in ("tr", "en"):
                panels = self.render_panels(ctx, result, lang=lang)
                rd.save_all_panels(panels, out_dir / lang, fmt="jpg",
                                   quality=88)
        return out_dir
