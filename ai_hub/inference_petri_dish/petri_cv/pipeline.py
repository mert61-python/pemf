# Author: mertaygn, cglrgrkn
"""pipeline.py — Petri Kuyucuk CV (YOLO + Kedi-ArUco kalibrasyon).

Kedi `inference_cat_organ` paterniyle birebir:
    - Kedi: YOLO + RTMPose -> 10 organ x,y,z cabin frame
    - Petri: YOLO11m-seg -> N kuyucuk x,y,z cabin frame (her biri!)

7 adim:
    1. cv2.undistort (kalibrasyon varsa)
    2. ArUco PnP -> CabinPose (varsa)
    3. YOLO11m-seg -> list[PetriDetection] (N kuyucuk)
    4. Kalibrasyon mm/px:
         A) ArUco varsa -> ray-plane intersection
         B) --petri-diameter-cm verilirse -> cap * 10 / bbox_max
         C) Default -> piksel mod (referans: en buyuk kuyucuk merkezi)
    5. Her kuyucuk icin organ_id (HSV mavi varsa kanser, yoksa saglikli)
    6. Her kuyucuga PetriPredictor.predict -> D[7], P[7], E
    7. JSON + 7-panel TR/EN overlay (her kuyucuk numarali: W1, W2, ...)
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
    CameraIntrinsics, CabinPose,
    detect_aruco_marker, solve_cabin_pose, pixel_to_cabin_mm,
    undistort_image, approx_intrinsics_from_marker,
)
from .petri_detector import PetriYoloDetector, PetriDetection
from .color_segment import segment_cancer_in_petri, Region, TUMOR, HEALTHY
from . import render as rd
# MAKULLIK DENETIMI (2026-08-06, sahip bildirimi): fantom fotografi bu boru hattinda sessizce
# "2 kuyucuk, 1 kanser" uretiyordu. Denetim ROUTER'da DEGIL burada durmali; cunku
# PEMF_AI_SERVICE_URL tanimliyken istek GPU mikroservisine gider ve servers/ai_router.py hic
# calismaz (bkz. ..plausibility docstring).
from .. import plausibility as _plaus


# PetriPredictor
_THIS_DIR = Path(__file__).parent.resolve()
_EM_PETRI = _THIS_DIR.parent.parent / "inference_em_petri"
if str(_EM_PETRI) not in sys.path:
    sys.path.insert(0, str(_EM_PETRI))

from inference_em_petri import PetriPredictor    # noqa: E402


@dataclass
class WellPrediction:
    """Tek bir kuyucuk + tahmin sonuclari (kedi'deki organ_pred gibi)."""
    well_id: str                                  # "W1", "W2", ...
    organ_id: int                                 # 0=saglikli, 1=kanserli
    label: str                                    # "healthy" / "cancer"
    conf: float                                   # YOLO conf
    reliability: float                            # solidity * conf (kedi gibi)
    centroid_px: tuple[float, float]
    centroid_cabin_mm: tuple[float, float, float]
    centroid_cabin_cm: tuple[float, float, float]
    bbox_px: tuple[int, int, int, int]            # x, y, w, h
    area_px: int
    area_mm2: float
    n_cancer_pixels: int = 0                      # HSV mavi piksel sayisi
    # Kontur (simplifie, kedi `segmentation.mask_xy` gibi):
    mask_xy: list[list[float]] = field(default_factory=list)
    D: list[float] = field(default_factory=list)
    P: list[float] = field(default_factory=list)
    E_healthy: float = 0.0
    E_cancer: float = 0.0
    E_avg: float = 0.0


@dataclass
class PipelineResult:
    schema_version: str = "v3.1"           # +R_matrix, pnp_fit, mask_xy, reliability
    success: bool = False
    timestamp: float = 0.0
    cabin_id: str = ""
    image_name: str = ""
    n_wells: int = 0
    n_cancer: int = 0
    n_healthy: int = 0
    method: str = ""                       # "aruco_pnp" / "petri_diameter" / "pixel"
    mm_per_px: float = 1.0
    cabin_pose: dict[str, Any] = field(default_factory=dict)
    camera_calib: dict[str, Any] = field(default_factory=dict)
    # Kedi paterninden yeni alanlar:
    R_matrix: list[list[float]] = field(default_factory=list)        # cabin <- marker rotation
    pnp_fit: dict[str, Any] = field(default_factory=dict)            # yaw/pitch/roll/residual
    wells: list[WellPrediction] = field(default_factory=list)
    timing_ms: dict[str, float] = field(default_factory=dict)
    error: str | None = None
    # Makullik olcumleri (dairesellik/conf/alan-orani + oy). YENI ALAN, geriye-uyumlu: mevcut
    # JSON tuketicileri (frontend, ai_service) bilmedigi alani yok sayar. Reddedilen istekte
    # ayrica "message" tasir → ai_router bunu 422 govdesinde kullaniciya aynen gosterir.
    plausibility: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = {k: v for k, v in self.__dict__.items() if k != "wells"}
        d["wells"] = [asdict(w) for w in self.wells]
        return d


class PetriCvPipeline:
    """YOLO11m-seg ile N kuyucuk + cabin-frame x,y,z (kedi paterni).

    Kedi organ tahminine paralel: her organa x,y,z, her kuyucuga x,y,z.
    """

    def __init__(self, cfg: CabinConfig | str | os.PathLike | None = None,
                 *, petri_diameter_cm: float | None = None,
                 yolo_model_path: str | os.PathLike | None = None,
                 yolo_conf: float = 0.25,
                 yolo_iou: float = 0.7,
                 yolo_imgsz: int = 640,
                 yolo_device: str = "0",
                 cancer_pixel_threshold: int = 30):
        if isinstance(cfg, CabinConfig):
            self.cfg = cfg
        else:
            self.cfg = load_cabin_config(cfg)
        self.petri_diameter_cm = petri_diameter_cm
        # Kuyucuk icinde >= bu kadar mavi piksel varsa kanser
        self.cancer_pixel_threshold = cancer_pixel_threshold

        self.intrinsics: CameraIntrinsics | None = None
        self._approx_intrinsics = False
        if self.cfg.has_intrinsics():
            self.intrinsics = CameraIntrinsics.from_npz(
                str(self.cfg.intrinsics_path()))

        # YOLO detector (ZORUNLU, kedi paterni)
        self.yolo = PetriYoloDetector(
            model_path=yolo_model_path,
            conf=yolo_conf, iou=yolo_iou,
            imgsz=yolo_imgsz, device=yolo_device,
        )

        self._predictor: PetriPredictor | None = None

    @property
    def predictor(self) -> PetriPredictor:
        if self._predictor is None:
            self._predictor = PetriPredictor()
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

    def _count_cancer_pixels(self, image_bgr: np.ndarray,
                             mask: np.ndarray) -> int:
        """Kuyucuk mask icinde mavi piksel sayisi (HSV cancer_blue)."""
        hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
        lo, hi = self.cfg.segmentation.cancer_blue.as_lower_upper()
        m_blue = cv2.inRange(hsv, lo, hi)
        m_blue = cv2.bitwise_and(m_blue, mask)
        return int((m_blue > 0).sum())

    @staticmethod
    def _rvec_to_euler_deg(rvec: np.ndarray) -> tuple[float, float, float]:
        """Rodrigues rvec -> yaw, pitch, roll (deg). Kedi pnp_fit gibi."""
        R, _ = cv2.Rodrigues(rvec)
        # ZYX intrinsic (yaw=Z, pitch=Y, roll=X)
        sy = float(np.sqrt(R[0, 0] ** 2 + R[1, 0] ** 2))
        if sy > 1e-6:
            yaw = float(np.degrees(np.arctan2(R[1, 0], R[0, 0])))
            pitch = float(np.degrees(np.arctan2(-R[2, 0], sy)))
            roll = float(np.degrees(np.arctan2(R[2, 1], R[2, 2])))
        else:
            yaw = float(np.degrees(np.arctan2(-R[1, 2], R[1, 1])))
            pitch = float(np.degrees(np.arctan2(-R[2, 0], sy)))
            roll = 0.0
        return yaw, pitch, roll

    @staticmethod
    def _contour_simplify(contour: np.ndarray, *,
                          max_pts: int = 80,
                          epsilon_frac: float = 0.003,
                          ) -> list[list[float]]:
        """Contour'u kedi `mask_xy` formati gibi sade nokta listesine cevir.

        approxPolyDP ile dusur; sonra hala fazlaysa downsample.
        """
        if len(contour) == 0:
            return []
        peri = float(cv2.arcLength(contour, True))
        if peri <= 0:
            return []
        approx = cv2.approxPolyDP(contour, epsilon_frac * peri, True)
        pts = approx.reshape(-1, 2)
        if len(pts) > max_pts:
            step = max(1, len(pts) // max_pts)
            pts = pts[::step]
        return [[float(p[0]), float(p[1])] for p in pts]

    def process_image(self, image_bgr: np.ndarray,
                      *, image_name: str = "",
                      achieved_B: float | None = None,
                      duty_sum: float | None = None,
                      ) -> tuple[PipelineResult, dict]:
        t0 = time.perf_counter()
        result = PipelineResult(success=False, timestamp=time.time(),
                                cabin_id=self.cfg.cabin_id,
                                image_name=image_name)
        timings: dict[str, float] = {}
        ctx: dict = {"img_und": None, "detections": None,
                     "cabin_pose": None, "marker": None}

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

        # 2) ArUco PnP
        t1 = time.perf_counter()
        marker_det = detect_aruco_marker(img_und, self.cfg.aruco)
        cabin_pose = None
        if marker_det is not None:
            cabin_pose = solve_cabin_pose(
                img_und, self.intrinsics,
                self.cfg.aruco, self.cfg.geometry, self.cfg.pnp,
            )
            if cabin_pose is not None:
                # Kedi paterni: tvec + R_matrix + Euler aci + reproj
                yaw, pitch, roll = self._rvec_to_euler_deg(cabin_pose.rvec)
                result.cabin_pose = {
                    "marker_id": cabin_pose.marker_id,
                    "tvec_mm": cabin_pose.tvec.flatten().tolist(),
                    "reproj_error_px": cabin_pose.reproj_error_px,
                }
                # Kedi `R_matrix` + `pnp_fit` alanlari
                result.R_matrix = cabin_pose.R.tolist()
                result.pnp_fit = {
                    "yaw_deg": yaw,
                    "pitch_deg": pitch,
                    "roll_deg": roll,
                    "residual_px": cabin_pose.reproj_error_px,
                    "marker_id": cabin_pose.marker_id,
                    "marker_pos_cabin_mm": cabin_pose.marker_pos_cabin_mm.tolist(),
                    "rvec": cabin_pose.rvec.flatten().tolist(),
                }
                ctx["cabin_pose"] = cabin_pose
                ctx["marker"] = {
                    "marker_id": cabin_pose.marker_id,
                    "corners_px": marker_det.corners_px.tolist(),
                }
        timings["aruco"] = (time.perf_counter() - t1) * 1000

        # 3) YOLO11m-seg — TUM kuyucuklar
        t1 = time.perf_counter()
        dets = self.yolo.detect(img_und)
        timings["yolo_detect"] = (time.perf_counter() - t1) * 1000
        if not dets:
            result.error = "yolo_no_well_detected"
            result.timing_ms = timings
            result.timing_ms["total"] = (time.perf_counter() - t0) * 1000
            return result, ctx

        # 3b) MAKULLIK DENETIMI — "tespit VAR" ile "PETRI tespiti var" ayni sey degil.
        # YOLO fantom fotografinda da 2 nesne buluyordu; bu kod olmadan boru hatti onlar icin
        # PetriPredictor'i calistirip E_cancer/D/P uretiyor ve success=True donuyordu. Karar
        # RESIM DUZEYINDE (medyan + 2-of-3 oy); kuyu listesi BUDANMAZ — mesru kuyucuklarin
        # bireysel conf'u 0.42'ye kadar dusebiliyor, tek tek eleme gercek kuyulari sessizce yutar.
        t1 = time.perf_counter()
        h_img, w_img = img_und.shape[:2]
        ok_plaus, plaus_metrics = _plaus.evaluate(
            [d.contour for d in dets], [d.conf for d in dets],
            float(h_img) * float(w_img))
        timings["plausibility"] = (time.perf_counter() - t1) * 1000
        result.plausibility = plaus_metrics
        if not ok_plaus:
            # Mevcut erken-cikis deseni (yolo_no_well_detected gibi); ai_router bu hatayi
            # 200/"no_detection" YERINE 422 + anlasilir Turkce mesaja cevirir.
            result.error = _plaus.PETRI_REJECT
            result.timing_ms = timings
            result.timing_ms["total"] = (time.perf_counter() - t0) * 1000
            return result, ctx
        # Sirali kopyayi ctx'e ekle (render sirasinda wells ile esle)
        # Not: sirali alti _sorted, asagida atanir

        # 4) Kalibrasyon mm/px (en buyuk kuyucuk referans)
        primary = max(dets, key=lambda d: d.area_px)
        x1, y1, x2, y2 = primary.bbox_xyxy
        bbox_max = max(x2 - x1, y2 - y1)
        if cabin_pose is not None:
            result.method = "aruco_pnp"
            result.mm_per_px = 0.0
        elif self.petri_diameter_cm is not None:
            result.method = "petri_diameter"
            result.mm_per_px = (self.petri_diameter_cm * 10.0) / max(bbox_max, 1.0)
        else:
            result.method = "pixel"
            result.mm_per_px = 1.0

        # Referans nokta (piksel modunda): en buyuk kuyucuk merkezi
        # = "origin" sayilir (cabin frame'de 0,0)
        ref_cx, ref_cy = primary.centroid_px

        def _to_mm(px: tuple[float, float]) -> tuple[float, float, float]:
            if cabin_pose is not None:
                v = pixel_to_cabin_mm(px, cabin_pose, self.intrinsics, self.cfg)
                return float(v[0]), float(v[1]), float(v[2])
            dx = (px[0] - ref_cx) * result.mm_per_px
            dy = (ref_cy - px[1]) * result.mm_per_px        # Y flip
            return float(dx), float(dy), 0.0

        def _contour_area_mm2(contour: np.ndarray) -> float:
            """Contour noktalarini cabin frame'e cevir, mm^2 alan hesapla.

            ArUco modunda: ray-plane intersection ile her nokta dogru cabin mm
            Diger modlarda: area_px * mm_per_px^2 (sabit oran)
            """
            if cabin_pose is None:
                # Sabit mm/px: hızlı formul
                area_px = float(cv2.contourArea(contour))
                return area_px * (result.mm_per_px ** 2)
            # ArUco: contour'u alt-orneklemden cabin'e cevir
            n_pts = len(contour)
            step = max(1, n_pts // 40)        # ~40 nokta yeter
            pts_cabin = []
            for i in range(0, n_pts, step):
                p = contour[i][0]
                x_mm, y_mm, _ = _to_mm((float(p[0]), float(p[1])))
                pts_cabin.append([x_mm, y_mm])
            if len(pts_cabin) < 3:
                return 0.0
            arr = np.array(pts_cabin, dtype=np.float32)
            return float(abs(cv2.contourArea(arr)))

        # 5+6) HER KUYUCUK icin: HSV kanser kontrol + PetriPredictor
        t1 = time.perf_counter()
        B = self.cfg.phantom.achieved_B if achieved_B is None else achieved_B
        duty = self.cfg.phantom.duty_sum if duty_sum is None else duty_sum

        # YOLO sonuclari sol-ust -> sag-alt sirala (well_id atamasi icin)
        dets_sorted = sorted(dets, key=lambda d: (d.centroid_px[1] // 50,
                                                  d.centroid_px[0]))
        ctx["detections"] = dets_sorted   # render icin wells ile ayni sirada

        for i, det in enumerate(dets_sorted, 1):
            well_id = f"W{i}"
            # Kanser tespiti: HSV mavi piksel sayisi
            n_cancer = self._count_cancer_pixels(img_und, det.mask)
            organ_id = TUMOR if n_cancer >= self.cancer_pixel_threshold else HEALTHY
            label = "cancer" if organ_id == TUMOR else "healthy"

            xyz = _to_mm(det.centroid_px)
            # Alan: ArUco modunda contour cabin-frame integration,
            #       diger modlarda area_px * mm_per_px^2
            area_mm2 = _contour_area_mm2(det.contour)

            # PetriPredictor
            pr = self.predictor.predict(
                x=xyz[0], y=xyz[1], z=xyz[2],
                organ_id=organ_id, achieved_B=B, duty_sum=duty,
            )

            x1, y1, x2, y2 = det.bbox_xyxy
            # Reliability: kedi `reliability` analoji — solidity (mask kalitesi) * YOLO conf
            hull = cv2.convexHull(det.contour)
            hull_area = max(cv2.contourArea(hull), 1.0)
            solidity = float(cv2.contourArea(det.contour) / hull_area)
            reliability = float(det.conf * solidity)
            # Kontur (kedi `mask_xy` formati)
            mask_xy = self._contour_simplify(det.contour)

            wp = WellPrediction(
                well_id=well_id,
                organ_id=organ_id, label=label,
                conf=det.conf,
                reliability=reliability,
                centroid_px=det.centroid_px,
                centroid_cabin_mm=xyz,
                centroid_cabin_cm=(xyz[0] / 10, xyz[1] / 10, xyz[2] / 10),
                bbox_px=(int(x1), int(y1), int(x2 - x1), int(y2 - y1)),
                area_px=det.area_px, area_mm2=area_mm2,
                n_cancer_pixels=n_cancer,
                mask_xy=mask_xy,
                D=[pr[f"D{k}"] for k in range(1, 8)],
                P=[pr[f"P{k}"] for k in range(1, 8)],
                E_healthy=pr["result_E_healthy"],
                E_cancer=pr["result_E_cancer"],
                E_avg=pr["result_E_avg"],
            )
            result.wells.append(wp)

        timings["predict_all"] = (time.perf_counter() - t1) * 1000
        result.n_wells = len(result.wells)
        result.n_cancer = sum(1 for w in result.wells if w.organ_id == TUMOR)
        result.n_healthy = sum(1 for w in result.wells if w.organ_id == HEALTHY)
        result.success = True
        timings["total"] = (time.perf_counter() - t0) * 1000
        result.timing_ms = timings
        return result, ctx

    def render_panels(self, ctx: dict, result: PipelineResult,
                      *, lang: str = "tr") -> dict[str, np.ndarray]:
        return rd.render_all_panels(
            ctx["img_und"],
            detections=ctx.get("detections") or [],
            marker=ctx.get("marker"),
            wells=result.wells,
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
