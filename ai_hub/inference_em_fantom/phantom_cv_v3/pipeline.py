# Author: mertaygn, cglrgrkn
"""pipeline.py — Sentetik bobrek fantom CV v3 (hocanin 2026-10-02 surumu; AI-2 2026-10-12 guii'ye YAMA olarak alindi).

guii sertlestirmesi (v1'deki ata -> guii farki, elle ve ACIK uygulandi): D1.100 gecersiz ArUco kesisimi -> konum / doz
YOK (`konum_hatasi`); D1.E07 piksel kipinde doz yok, fiziksel alan bilinmiyorsa (piksel / ArUco perspektifi) None;
manuel tiklama (cv2 penceresi, `manual_select`) ALINMADI (headless — plan 3.3); PhantomPredictor guii PAKET yolundan.

v3: paralaks duzeltmesi, tumor yerlesim referansi (sabit kimlik, dusuk cozunurlukte
sablon fit, QC), fantom-sabit u/v cercevesi + CST egitim kutusuna PEMF yerlesimi.


v1 -> v2 (2026-10-02 goruntuleri ile):
  - Tespit: lacivert hale + siyah cekirdek (tumor_detect.py). v1 HSV mavi
    esigi (V>=40) siyah cekirdekleri kaciriyor, mor bobin/kablolari tumor
    sayiyordu; 2/9 goruntude fantom hic bulunamiyordu.
  - Tumor ayirma: halenin icindeki delikler = cekirdekler (her tumor ayri).
  - Kalibrasyon: ArUco > yesil bobin halkasi (ring_calib.py) > fantom boyu > piksel.
  - PEMF: cerceve kabin konumu bilinmiyorsa pemf_valid=False + uyari.

Adimlar:
  1. undistort   2. ArUco (varsa)   3. fantom + tumorler (v2)
  4. olcek/cerceve   5. piksel -> mm   6. PhantomPredictor   7. JSON + 7 panel
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
    CameraIntrinsics, detect_aruco_marker, solve_cabin_pose, pixel_to_cabin_mm, KesisimGecersiz,
    undistort_image, approx_intrinsics_from_marker, isaret_ters_mi, olcekli_intrinsics,
)
from ...cv_ortak.pemf_kapisi import ISARET_TERS_METNI
from .color_segment import segment_phantom, find_phantoms, Region, TUMOR, HEALTHY
from .tumor_detect import TumorDetectCfg, detect_phantom_tumors
from .ring_calib import detect_ring
from .layout import Layout, register, fit_template
from . import render as rd


# PhantomPredictor — AI-2: hocanin `..` sys.path hilesi (ve guii v1'deki kopyasi) yerine guii PAKET yolu: modul adi tek,
# sinif tek (petri v2'de ayni hile PetriPredictor'i iki ayri sinifa boluyordu — olculdu).
from ..inference_em_fantom import PhantomPredictor


def _json_safe(o):
    """JSON-uyumlu: NaN/inf -> None, numpy -> Python (FastAPI/strict JSON icin)."""
    import math
    if isinstance(o, dict):
        return {str(k): _json_safe(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_json_safe(v) for v in o]
    if isinstance(o, np.ndarray):
        return _json_safe(o.tolist())
    if isinstance(o, (np.floating, float)):
        f = float(o)
        return None if (math.isnan(f) or math.isinf(f)) else f
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, np.bool_):
        return bool(o)
    return o


@dataclass
class RegionPrediction:
    organ_id: int
    label: str
    centroid_px: tuple[float, float]
    # D1.100 (B-5.16 · İG-5.72): ArUco kipinde ışın hedef düzlemi geçerli noktada kesmiyorsa (kameranın arkası,
    # paralel, kabin dışı) konum ÜRETİLMEZ → None (+ `konum_hatasi`); doz da hesaplanmaz.
    centroid_cabin_mm: tuple[float, float, float] | None
    centroid_cabin_cm: tuple[float, float, float] | None
    area_px: int
    # D1.E07 (İG-5.76): fiziksel alan BİLİNMİYORSA (piksel kipi: ölçek yok; ArUco kipi: perspektif alanı
    # hesaplanmıyor) None — eskiden piksel kipinde px² "mm²" diye, ArUco kipinde 0.0 ("ölçüldü, sıfır") yazılıyordu.
    area_mm2: float | None
    bbox_px: tuple[int, int, int, int]
    tumor_id: str = ""                               # T1..Tn (yukaridan asagi)
    frame_mm: tuple[float, float] | None = None      # cerceve (halka/fantom) mm
    phantom_uv_mm: tuple[float, float] | None = None # fantom-sabit (u=uzun, v=kisa eksen)
    D: list[float] = field(default_factory=list)
    P: list[float] = field(default_factory=list)
    # D1.E07: doz hesaplanmadıysa (piksel kipi / konum yok) None — 0.0 "hesaplandı, sıfır" diye okunur (Y6).
    E_healthy: float | None = None
    E_cancer: float | None = None
    E_avg: float | None = None
    konum_hatasi: str | None = None


@dataclass
class PipelineResult:
    schema_version: str = "v3.0"
    success: bool = False
    timestamp: float = 0.0
    cabin_id: str = ""
    image_name: str = ""
    n_tumor: int = 0
    n_healthy: int = 0
    method: str = ""              # aruco_pnp / coil_ring / phantom_length / pixel
    mm_per_px: float = 1.0
    coord_frame: str = ""         # cabin_aruco / cabin_placement / coil / phantom / pixel
    frame_origin: str = ""        # coil_center / phantom_center / marker
    pemf_valid: bool = False
    reliable: bool = True         # dusuk guvenli tespit -> False
    layout: dict[str, Any] = field(default_factory=dict)   # referans kaydi / sablon fit
    phantom_frame: dict[str, Any] = field(default_factory=dict)  # fantom-sabit u/v cercevesi
    pemf_source: str = ""         # aruco / placement / cst_phantom_box / ""
    phantom_detection: dict[str, Any] = field(default_factory=dict)
    ring: dict[str, Any] = field(default_factory=dict)
    cabin_pose: dict[str, Any] = field(default_factory=dict)
    camera_calib: dict[str, Any] = field(default_factory=dict)
    tumor_regions: list[RegionPrediction] = field(default_factory=list)
    healthy_regions: list[RegionPrediction] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    timing_ms: dict[str, float] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict:
        d = {k: v for k, v in self.__dict__.items()
             if k not in ("tumor_regions", "healthy_regions")}
        d["tumor_regions"] = [asdict(r) for r in self.tumor_regions]
        d["healthy_regions"] = [asdict(r) for r in self.healthy_regions]
        return _json_safe(d)


class PhantomCvPipeline:
    """Fantom-merkezli sentetik bobrek CV pipeline (v2)."""

    def __init__(self, cfg: CabinConfig | str | os.PathLike | None = None,
                 *, phantom_length_cm: float | None = None,
                 manual_fallback: bool = False,
                 ring_diameter_mm: float | None = None,
                 use_ring: bool | None = None,
                 origin_cabin_mm: list[float] | None = None):
        """Parametreler None ise YAML `phantom_v2:` bolumunden (CLI > YAML)."""
        if isinstance(cfg, CabinConfig):
            self.cfg = cfg
        else:
            self.cfg = load_cabin_config(cfg)
        v2 = self.cfg.phantom_v2
        self.phantom_length_cm = phantom_length_cm
        # AI-2: guii headless — manuel tiklama (cv2 penceresi) ALINMADI; parametre geriye uyum icin kabul edilir, YOK SAYILIR.
        self.manual_fallback = False
        self.use_ring = v2.ring_enabled if use_ring is None else use_ring
        self.ring_diameter_mm = ring_diameter_mm or v2.ring_diameter_mm
        self.origin_cabin_mm = (origin_cabin_mm if origin_cabin_mm is not None
                                else v2.origin_cabin_mm)
        self.x_axis = np.asarray(v2.x_axis_cabin, dtype=np.float64)
        self.y_axis = np.asarray(v2.y_axis_cabin, dtype=np.float64)
        self.layout: Layout | None = None
        if v2.layout_file:
            lp = Path(v2.layout_file)
            if not lp.is_absolute():
                lp = Path(self.cfg.source_path).parent / lp
            if lp.exists():
                self.layout = Layout.load(lp)
        self.tumor_cfg = TumorDetectCfg(navy_s_min=v2.navy_s_min, navy_v_min=v2.navy_v_min,
                                        navy_a_max=v2.navy_a_max, core_v_max=v2.core_v_max)

        self.intrinsics: CameraIntrinsics | None = None
        self._approx_intrinsics = False
        if self.cfg.has_intrinsics():
            self.intrinsics = CameraIntrinsics.from_npz(str(self.cfg.intrinsics_path()))
        self._predictor: PhantomPredictor | None = None

    @property
    def predictor(self) -> PhantomPredictor:
        if self._predictor is None:
            try:                        # CUDA saglayici yoksa CPU'ya duser; gurultulu logu kapat
                import onnxruntime as ort
                ort.set_default_logger_severity(4)
            except Exception:
                pass
            self._predictor = PhantomPredictor()
        return self._predictor

    def _ensure_intrinsics(self, image_bgr: np.ndarray) -> None:
        if self.intrinsics is not None:
            # ⚠️ TD4: kalibrasyon (`intrinsics_npz`) / ilk karenin yaklaşık K'sı başka çözünürlükteyse kareye ÖLÇEKLE
            # (petri v2 kuralı; ölçüldü: ölçeksiz K ile işaret mesafesi çözünürlük oranı kadar yanlış).
            h, w = image_bgr.shape[:2]
            self.intrinsics = olcekli_intrinsics(self.intrinsics, w, h)
            return
        approx = approx_intrinsics_from_marker(image_bgr, self.cfg)
        if approx is None:
            h, w = image_bgr.shape[:2]
            f = float(max(h, w))
            K = np.array([[f, 0, w / 2.0], [0, f, h / 2.0], [0, 0, 1.0]])
            approx = CameraIntrinsics(K, np.zeros(5), (w, h), float("nan"))
        self.intrinsics = approx
        self._approx_intrinsics = True

    # ------------------------------------------------------------------ ana
    def process_image(self, image_bgr: np.ndarray, *, image_name: str = "",
                      achieved_B: float | None = None,
                      duty_sum: float | None = None) -> tuple[PipelineResult, dict]:
        t0 = time.perf_counter()
        result = PipelineResult(timestamp=time.time(), cabin_id=self.cfg.cabin_id,
                                image_name=image_name)
        timings: dict[str, float] = {}
        ctx: dict = {"img_und": None, "regions": None, "phantoms": [],
                     "cabin_pose": None, "marker": None}

        def _done():
            timings["total"] = (time.perf_counter() - t0) * 1000
            result.timing_ms = timings
            return result, ctx

        self._ensure_intrinsics(image_bgr)
        result.camera_calib = {
            "K": self.intrinsics.K.tolist(), "D": self.intrinsics.D.tolist(),
            "image_size": list(self.intrinsics.image_size),
            "rms": self.intrinsics.rms, "approx": self._approx_intrinsics,
        }

        # 1) undistort
        t1 = time.perf_counter()
        img = undistort_image(image_bgr, self.intrinsics)
        ctx["img_und"] = img
        timings["undistort"] = (time.perf_counter() - t1) * 1000

        # 2) ArUco
        t1 = time.perf_counter()
        cabin_pose = None
        marker_det = detect_aruco_marker(img, self.cfg.aruco)
        if marker_det is not None:
            cabin_pose = solve_cabin_pose(img, self.intrinsics, self.cfg.aruco,
                                          self.cfg.geometry, self.cfg.pnp)
            if cabin_pose is not None:
                result.cabin_pose = {"marker_id": cabin_pose.marker_id,
                                     "tvec_mm": cabin_pose.tvec.flatten().tolist(),
                                     "reproj_error_px": cabin_pose.reproj_error_px}
                ctx["cabin_pose"] = cabin_pose
                ctx["marker"] = {"marker_id": cabin_pose.marker_id,
                                 "corners_px": marker_det.corners_px.tolist()}
                # TD4: ters takılı işaret (kâğıt 180°) → kabin X / Y aynalanır; uyarı pemf kapısında ENGELLEYİCİ.
                if isaret_ters_mi(cabin_pose, self.cfg):
                    result.warnings.append(f"marker_upside_down: {ISARET_TERS_METNI}")
        timings["aruco"] = (time.perf_counter() - t1) * 1000

        # 3) fantom + tumorler
        t1 = time.perf_counter()
        det = detect_phantom_tumors(img, self.tumor_cfg)
        detect_method = "v2_navy_halo"
        tumors, healthy = det.tumors, det.healthy
        phantom = det.phantom
        # Siyah cekirdeksiz DAGINIK mavi leke fantomu (orn. 2026-06 test_img):
        # v2 hale/cekirdek yapisi yok -> v1 HSV algoritmasi (o fantomda dogrulanmis)
        structured = det.success and any(k in det.split_method
                                          for k in ("hole", "core", "log"))
        if not structured:
            v1 = find_phantoms(img, self.cfg.segmentation, max_phantoms=1)
            if v1:
                segs = segment_phantom(img, self.cfg.segmentation, phantom=v1[0])
                if segs["tumor"]:
                    phantom, tumors, healthy = v1[0], segs["tumor"], segs["healthy"]
                    detect_method = "v1_hsv_diffuse"
                    # v2 denemesinin uyarilari (dusuk kontrast vb.) artik gecerli degil
                    det.warnings = ["diffuse_tumor_mode: cekirdeksiz daginik mavi leke "
                                    "-> v1 HSV algoritmasi (tek fantom) kullanildi"]
        timings["phantom_detect"] = (time.perf_counter() - t1) * 1000
        if phantom is None or not tumors:
            result.error = det.error or "phantom_not_detected"
            result.warnings.extend(det.warnings)
            return _done()
        result.warnings.extend(det.warnings)
        if any(w.startswith(("low_contrast_fallback", "low_resolution", "phantom_grabcut"))
               for w in det.warnings):
            result.reliable = False
        ctx["phantoms"] = [phantom]
        ctx["phantom"] = phantom
        ctx["regions"] = {"phantoms": [phantom], "tumor": tumors, "healthy": healthy}
        result.phantom_detection = {
            "n_phantoms": 1,
            "primary": {"centroid_px": list(phantom.centroid_px),
                        "area_px": phantom.area_px, "bbox_px": list(phantom.bbox_px),
                        "solidity": phantom.solidity,
                        "n_blue_inside": phantom.n_blue_inside, "score": phantom.score},
            "detect_method": detect_method,
            "split_method": (det.split_method if detect_method == "v2_navy_halo"
                             else detect_method),
            "tumor_radius_px": det.tumor_radius_px,
        }

        # 3b) Dusuk cozunurluk + yerlesim referansi: sablonu tumor maskesine fit et
        layout_mmpx = None
        if (self.layout is not None and detect_method == "v2_navy_halo"
                and not result.reliable and det.tumor_mask is not None):
            fit = fit_template(det.tumor_mask, self.layout, phantom.centroid_px,
                               max(det.tumor_radius_px, 1.0))
            if fit is not None:
                centers, mmpx, sc = fit
                result.layout = {"mode": "template_fit", "score": round(sc, 3),
                                 "mm_per_px": round(mmpx, 4)}
                if sc >= 0.45:
                    r_px = max(2, int(round(self.layout.tumor_radius_mm / mmpx)))
                    new = []
                    for tid, (cx, cy) in zip(self.layout.ids, centers):
                        m = np.zeros(img.shape[:2], np.uint8)
                        cv2.circle(m, (int(round(cx)), int(round(cy))), r_px, 255, -1)
                        m &= phantom.mask
                        cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL,
                                                   cv2.CHAIN_APPROX_SIMPLE)
                        if not cnts:
                            continue
                        x, y, w_, h_ = cv2.boundingRect(max(cnts, key=cv2.contourArea))
                        new.append(Region(organ_id=TUMOR, label="tumor",
                                          centroid_px=(float(cx), float(cy)),
                                          area_px=int(cv2.countNonZero(m)),
                                          bbox_px=(x, y, w_, h_),
                                          contour_px=max(cnts, key=cv2.contourArea), mask=m))
                    if len(new) == len(self.layout.ids):
                        tumors = new
                        ctx["regions"]["tumor"] = tumors
                        layout_mmpx = mmpx
                        result.phantom_detection["split_method"] = "layout_template_fit"
                        result.warnings.append(
                            f"layout_fit_used: tumorler ayrilamadi, referans yerlesim "
                            f"sablonu fit edildi (ortusme {sc:.2f})")
                        result.reliable = sc >= 0.6

        # 4) olcek + cerceve
        t1 = time.perf_counter()
        ring = None
        if cabin_pose is None and self.use_ring:
            bx, by, bw, bh = phantom.bbox_px
            ring = detect_ring(img, phantom.centroid_px, max(bw, bh),
                               diameter_mm=self.ring_diameter_mm)
            result.ring = ring.to_dict()
            if ring.success:
                result.warnings.extend(ring.warnings)
            else:
                result.warnings.append(f"ring_unavailable: {ring.error}")
                ring = None
        timings["ring"] = (time.perf_counter() - t1) * 1000

        ph_cx, ph_cy = phantom.centroid_px
        if cabin_pose is not None:
            result.method, result.mm_per_px = "aruco_pnp", 0.0
            result.coord_frame, result.frame_origin = "cabin_aruco", "marker"
        elif ring is not None:
            result.method, result.mm_per_px = "coil_ring", ring.mm_per_px
            result.coord_frame, result.frame_origin = "coil", "coil_center"
        elif layout_mmpx is not None:
            result.method, result.mm_per_px = "phantom_layout", layout_mmpx
            result.coord_frame, result.frame_origin = "phantom", "phantom_center"
        elif self.phantom_length_cm is not None:
            bx, by, bw, bh = phantom.bbox_px
            result.method = "phantom_length"
            result.mm_per_px = self.phantom_length_cm * 10.0 / float(max(bw, bh))
            result.coord_frame, result.frame_origin = "phantom", "phantom_center"
        else:
            result.method, result.mm_per_px = "pixel", 1.0
            result.coord_frame, result.frame_origin = "pixel", "phantom_center"
            result.warnings.append("no_scale: halka/ArUco/fantom boyu yok - koordinatlar PIKSEL")

        # Paralaks: fantom ust yuzeyi (tumorler) halka duzleminden h mm yukarida ->
        # kameraya yakin, Z/(Z-h) kat buyuk ve nadirden disari kaymis gorunur.
        # Nadir ~ goruntu merkezi (ustten cekim). Duzleme indirgemek icin olcekle.
        par = 1.0
        nadir = np.array([img.shape[1] / 2.0, img.shape[0] / 2.0])
        if ring is not None:
            v2c = self.cfg.phantom_v2
            f_px = v2c.focal_equiv_mm / 43.27 * float(np.hypot(*img.shape[:2]))
            par = ring.parallax_factor(v2c.parallax_height_mm, f_px)
            result.ring["parallax_factor"] = round(par, 4)
            result.ring["parallax_height_mm"] = v2c.parallax_height_mm

        def _frame(px) -> tuple[float, float]:
            if ring is not None:
                q = nadir + (np.asarray(px, dtype=np.float64) - nadir) * par
                return ring.px_to_mm(q)
            return ((px[0] - ph_cx) * result.mm_per_px, (ph_cy - px[1]) * result.mm_per_px)

        # Yerlesim referansina kayit: sabit kimlik + QC (+ olcek yoksa olcek)
        id_map = None
        reg_T = None
        if (self.layout is not None and detect_method == "v2_navy_halo"
                and 3 <= len(tumors) <= len(self.layout.ids)):
            pts = np.array([_frame(t.centroid_px) for t in tumors], dtype=np.float64)
            reg = register(pts, self.layout.points_mm, allow_scale=True,
                           scale_bounds=((0.5, 2.0) if result.method != "pixel"
                                         else (1e-3, 1e3)))   # piksel: s = mm/px
            if reg is not None:
                assign, s_reg, _, _, rms = reg
                rms_mm = rms                       # referans birimi mm
                tol = max(3.0, 0.3 * self.layout.tumor_radius_mm)
                result.layout.update({"mode": result.layout.get("mode", "register"),
                                      "rms_mm": round(rms_mm, 2),
                                      "scale_vs_ref": round(1.0 / s_reg if s_reg else 0, 4)})
                if rms_mm <= tol:
                    id_map = [self.layout.ids[k] for k in assign]
                    reg_T = (s_reg, reg[2], reg[3])
                    if result.method == "pixel":
                        # olcek yok: referansa gore mm/px
                        result.method, result.mm_per_px = "phantom_layout", float(s_reg)
                        result.coord_frame = "phantom"
                        result.warnings = [w for w in result.warnings
                                           if not w.startswith("no_scale")]
                    elif abs(1.0 / s_reg - 1.0) > 0.08:
                        result.warnings.append(
                            f"scale_check: referansa gore olcek x{1.0 / s_reg:.3f} "
                            "(halka capi / paralaks kontrol)")
                else:
                    result.warnings.append(
                        f"layout_mismatch: referans yerlesime kayit hatasi {rms_mm:.1f} mm "
                        f"(> {tol:.1f}) - yanlis tespit veya farkli fantom; konum sirali kimlik")
        # ⚠️ AI-2 (guii, olculdu 2026-10-12): kayit HIC yapilamadiginda kimlikler SESSIZCE konum sirali kaliyordu. ArUco
        # kipinde `_frame` olcegi 0 (mm_per_px = 0) -> tum tumorler (0, 0) -> `register` None -> uyari YOK, T1..T5 gorunur ama
        # referans tumorleri DEGIL (sentetik ArUco + hocanin 19.40.11 fotografi: layout bos, uyari bos). Sabit kimlik
        # iddiasi bozuldugunda bunu SOYLE: tuketiciler (AI Pro saglayicisi, AI Hub) kimligi yalniz kayitli sonucta sabit sayar.
        if (self.layout is not None and detect_method == "v2_navy_halo" and id_map is None
                and not any(str(w).startswith("layout_mismatch") for w in result.warnings)):
            neden = ("ArUco kipinde cerceve olcegi yok" if result.method == "aruco_pnp"
                     else f"{len(tumors)} tumor, referansta {len(self.layout.ids)}")
            result.warnings.append(
                f"layout_unregistered: tumorler yerlesim referansina kaydedilemedi ({neden}) - kimlikler KONUM "
                "SIRALI, goruntuden goruntuye ayni tumoru garanti etmez")

        # Fantom-sabit cerceve (u = uzun eksen, v = kisa eksen, origin = fantom kutu
        # merkezi). Fotograf yonunden bagimsiz. u isareti: referanstaki SON kimlikli
        # tumor (+u) tarafinda -> her goruntude ayni yon (kimlikler tutarli oldugu icin).
        uv = None
        if id_map is not None and result.method != "pixel":
            par_pts = np.array([_frame(p) for p in phantom.contour_px.reshape(-1, 2)],
                               dtype=np.float32)
            (bc, (ba, bb), bang) = cv2.minAreaRect(par_pts)
            th = np.deg2rad(bang if ba >= bb else bang + 90.0)
            e_u = np.array([np.cos(th), np.sin(th)])
            tum_f = {tid: np.array(_frame(t.centroid_px)) for tid, t in zip(id_map, tumors)}
            last = max(tum_f, key=lambda k: int(k[1:]))
            if (tum_f[last] - np.asarray(bc)) @ e_u < 0:
                e_u = -e_u
            e_v = np.array([-e_u[1], e_u[0]])            # sag-el (aynalama yok)
            uv = (np.asarray(bc, dtype=np.float64), e_u, e_v)
            result.phantom_frame = {
                "center_frame_mm": [round(float(v), 2) for v in bc],
                "long_axis_deg_in_frame": round(float(np.degrees(np.arctan2(e_u[1], e_u[0]))), 1),
                "size_mm": [round(float(max(ba, bb)), 1), round(float(min(ba, bb)), 1)],
                "u_sign_rule": f"{last} +u tarafinda",
            }

        placement = (np.asarray(self.origin_cabin_mm, dtype=np.float64)
                     if self.origin_cabin_mm is not None and cabin_pose is None
                     and result.method != "pixel" else None)
        v2c = self.cfg.phantom_v2
        use_cst = (cabin_pose is None and placement is None and uv is not None
                   and v2c.cst_box_enabled)
        if cabin_pose is not None:
            result.pemf_valid, result.pemf_source = True, "aruco"
        elif placement is not None:
            result.coord_frame, result.pemf_valid = "cabin_placement", True
            result.pemf_source = "placement"
        elif use_cst:
            result.coord_frame, result.pemf_valid = "cabin_cst_phantom_box", True
            result.pemf_source = "cst_phantom_box"
            result.warnings.append(
                "pemf_axis_sign_assumed: fantom merkezi/eksenleri CST egitim kutusuna "
                "eslendi; u->+y, v->+z ISARETI fotograftan dogrulanamaz "
                "(phantom_v2.cst_box.axis_u/axis_v ile degistir)")
        else:
            result.warnings.append(
                "pemf_frame_unknown: kabin konumu yok (ArUco, placement veya referansa "
                "kayitli fantom) - D/P/E tahminleri fiziksel olarak gecersiz")
        cst_c = np.asarray(v2c.cst_box_center_mm, dtype=np.float64)
        cst_u = np.asarray(v2c.cst_axis_u, dtype=np.float64)
        cst_v = np.asarray(v2c.cst_axis_v, dtype=np.float64)

        lay_uv = {}
        if (id_map is not None and self.layout is not None
                and self.layout.box_center_mm is not None):
            # Fantom rijit: tumorun fantom-sabit konumu = referans (N goruntu ortalamasi)
            for tid in id_map:
                k = self.layout.ids.index(tid)
                lay_uv[tid] = self.layout.to_uv(self.layout.points_mm[k])
            result.phantom_frame["uv_source"] = (
                f"referans yerlesim ({self.layout.n_images} goruntu ortalamasi)")
            s_r, R_r, t_r = reg_T
            result.layout["transform"] = {"s": round(float(s_r), 5),
                                          "rot_deg": round(float(np.degrees(
                                              np.arctan2(R_r[1, 0], R_r[0, 0]))), 2),
                                          "t": [round(float(v), 3) for v in t_r]}
        elif reg_T is not None:
            s_r, R_r, t_r = reg_T
            result.layout["transform"] = {"s": round(float(s_r), 5),
                                          "rot_deg": round(float(np.degrees(
                                              np.arctan2(R_r[1, 0], R_r[0, 0]))), 2),
                                          "t": [round(float(v), 3) for v in t_r]}

        def _uv(fr, tid=None):
            if tid in lay_uv:
                return lay_uv[tid]
            if uv is None or fr is None:
                return None
            c, eu, ev = uv
            d = np.asarray(fr) - c
            return float(d @ eu), float(d @ ev)

        def _to_mm(px, tid=None) -> tuple[tuple[float, float, float], tuple[float, float] | None]:
            if cabin_pose is not None:
                v = pixel_to_cabin_mm(px, cabin_pose, self.intrinsics, self.cfg)
                return (float(v[0]), float(v[1]), float(v[2])), None
            fx, fy = _frame(px)
            if use_cst:
                u, v_ = _uv((fx, fy), tid)
                q = cst_c + u * cst_u + v_ * cst_v
                return (float(q[0]), float(q[1]), float(q[2])), (fx, fy)
            if placement is not None:
                v = placement + fx * self.x_axis + fy * self.y_axis
                return (float(v[0]), float(v[1]), float(v[2])), (fx, fy)
            return (fx, fy, 0.0), (fx, fy)

        # 5-6) mm + PhantomPredictor
        t1 = time.perf_counter()
        B = self.cfg.phantom.achieved_B if achieved_B is None else achieved_B
        duty = self.cfg.phantom.duty_sum if duty_sum is None else duty_sum

        # ⚠️ D1.E07 (İG-5.76): PİKSEL kipinde (ölçek yok) koordinat piksel farkıdır — doz modeline mm diye verilmez
        # (ölçüldü: x=9,32 "mm" → eğitim dağılımının +6,8σ dışı) ve alan mm² sayılmaz. ArUco kipinde perspektif alanı
        # hesaplanmaz (mm_per_px 0) → alan None (eskiden 0.0 "ölçüldü, sıfır").
        _doz_hesaplanir = result.method != "pixel"
        _olcekli_alan = result.method in ("phantom_length", "phantom_layout") and bool(result.mm_per_px)

        def _make(r: Region, tid: str) -> RegionPrediction:
            konum_hatasi = None
            try:
                xyz, fr = _to_mm(r.centroid_px, tid)
                xyz = tuple(round(v, 3) + 0.0 for v in xyz)
            except KesisimGecersiz as e:  # D1.100: geçersiz kesişim → konum yok, doz yok
                xyz, fr, konum_hatasi = None, None, str(e)
            if xyz is None:
                area_mm2 = None
            elif ring is not None:
                area_mm2 = round(ring.area_px_to_mm2(r.area_px) * par ** 2, 2)
            elif _olcekli_alan:
                area_mm2 = round(r.area_px * (result.mm_per_px ** 2), 2)
            else:
                area_mm2 = None
            uvv = _uv(fr, tid) if fr is not None else None
            rp = RegionPrediction(
                organ_id=r.organ_id, label=r.label, centroid_px=r.centroid_px,
                centroid_cabin_mm=xyz,
                centroid_cabin_cm=tuple(v / 10 for v in xyz) if xyz is not None else None,
                area_px=r.area_px, area_mm2=area_mm2, bbox_px=r.bbox_px,
                tumor_id=tid,
                frame_mm=(tuple(round(v, 3) + 0.0 for v in fr) if fr else None),
                phantom_uv_mm=(tuple(round(v, 3) + 0.0 for v in uvv) if uvv is not None else None),
                konum_hatasi=konum_hatasi)
            if _doz_hesaplanir and xyz is not None and r.organ_id in (0, 1):
                pr = self.predictor.predict(x=xyz[0], y=xyz[1], z=xyz[2],
                                            organ_id=r.organ_id, achieved_B=B, duty_sum=duty)
                rp.D = [pr[f"D{i}"] for i in range(1, 8)]
                rp.P = [pr[f"P{i}"] for i in range(1, 8)]
                rp.E_healthy, rp.E_cancer = pr["result_E_healthy"], pr["result_E_cancer"]
                rp.E_avg = pr["result_E_avg"]
            return rp

        ids = id_map or [f"T{i}" for i in range(1, len(tumors) + 1)]
        for tid, r in sorted(zip(ids, tumors), key=lambda t: int(t[0][1:])):
            result.tumor_regions.append(_make(r, tid))
        if id_map is not None:      # panel sirasi da kimlikle ayni olsun
            ctx["regions"]["tumor"] = [r for _, r in sorted(zip(ids, tumors),
                                                            key=lambda t: int(t[0][1:]))]
        for r in healthy:
            result.healthy_regions.append(_make(r, "H"))
        timings["predictor"] = (time.perf_counter() - t1) * 1000
        result.n_tumor = len(result.tumor_regions)
        result.n_healthy = len(result.healthy_regions)
        result.success = True
        return _done()

    # ------------------------------------------------------------------ cikti
    def render_panels(self, ctx: dict, result: PipelineResult, *, lang: str = "tr"):
        return rd.render_all_panels(
            ctx["img_und"], phantoms=ctx.get("phantoms") or [],
            marker=ctx.get("marker"),
            regions=ctx.get("regions") or {"tumor": [], "healthy": []},
            regions_pred=result.tumor_regions + result.healthy_regions,
            method=result.method, mm_per_px=result.mm_per_px, lang=lang,
            origin_px=(result.ring.get("center_px") if result.method == "coil_ring" else None),
            ring=(result.ring if result.method == "coil_ring" else None))

    def process_file(self, image_path, **kwargs):
        # imdecode: Unicode yol ('güncel') her platformda okunur
        try:
            img = cv2.imdecode(np.fromfile(str(image_path), dtype=np.uint8),
                               cv2.IMREAD_COLOR)
        except (OSError, ValueError):
            img = None
        if img is None:
            return PipelineResult(success=False, timestamp=time.time(),
                                  cabin_id=self.cfg.cabin_id,
                                  image_name=Path(image_path).name,
                                  error=f"image_read_fail: {image_path}"), {}
        kwargs.setdefault("image_name", Path(image_path).name)
        return self.process_image(img, **kwargs)

    def write_results(self, image_path, result: PipelineResult, ctx: dict,
                      out_root: str | os.PathLike = "results") -> Path:
        out_dir = Path(out_root) / Path(image_path).stem
        out_dir.mkdir(parents=True, exist_ok=True)
        with open(out_dir / "result.json", "w", encoding="utf-8") as fh:
            json.dump(result.to_dict(), fh, indent=2, default=str, ensure_ascii=False)
        if result.success and ctx.get("img_und") is not None:
            for lang in ("tr", "en"):
                rd.save_all_panels(self.render_panels(ctx, result, lang=lang),
                                   out_dir / lang, fmt="jpg", quality=88)
        return out_dir
