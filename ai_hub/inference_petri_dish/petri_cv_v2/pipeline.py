# Author: mertaygn, cglrgrkn
"""pipeline.py — Petri Kuyucuk CV v2 (hocanin 2026-10-02 surumu; AI-2 2026-10-12 guii'ye YAMA olarak alindi).

v2 (hoca): 24'luk plaka IZGARA kipi (A1..D6, YOLO yalniz ipucu), goreli renk + kontrol kuyucuklu kanser siniflama,
`coord_frame` / `pemf_valid` / `warnings`. guii sertlestirmesi (v1'den 3 yollu birlestirme, taban = ata 2026-08-26):
makullik denetimi (tekil kip v1 kurali + plaka kipi kurali), YOLO oncesi kucultme + K olcekleme, cagri basina YOLO
esikleri, D1.100 gecersiz kesisim -> konum yok, D1.E07 piksel kipinde doz/mm2 yok, ONNX 640 aday uyarlamasi.

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
    detect_aruco_marker, solve_cabin_pose, pixel_to_cabin_mm, KesisimGecersiz,
    undistort_image, approx_intrinsics_from_marker, isaret_ters_mi, olcekli_intrinsics,
)
from ...cv_ortak.pemf_kapisi import ISARET_TERS_METNI
from .petri_detector import PetriYoloDetector, PetriDetection
from .color_segment import (segment_cancer_in_petri, classify_plate_wells,
                            Region, TUMOR, HEALTHY)
from .plate_grid import detect_plate_wells
from . import render as rd
# MAKULLIK DENETIMI (2026-08-06, sahip bildirimi): fantom fotografi bu boru hattinda sessizce
# "2 kuyucuk, 1 kanser" uretiyordu. Denetim ROUTER'da DEGIL burada durmali; cunku
# PEMF_AI_SERVICE_URL tanimliyken istek GPU mikroservisine gider ve apps/backend/servers/ai_router.py hic
# calismaz (bkz. ..plausibility docstring).
from .. import plausibility as _plaus


# PetriPredictor — AI-2: hocanin `../../inference_em_petri` sys.path hilesi (ve guii v1'deki kopyasi) yerine guii PAKET
# yolu. sys.path'e `ai_hub/inference_em_petri` eklemek `inference_em_petri` adini iki modüle bölüyordu (aynı sınıfın
# iki kopyası; bkz. tests/golden/yukleyici.py) — paket yolu tek modül, tek sınıf.
from ...inference_em_petri.inference_em_petri import PetriPredictor


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
class WellPrediction:
    """Tek bir kuyucuk + tahmin sonuclari (kedi'deki organ_pred gibi)."""
    well_id: str                                  # "W1", ... / plaka: "A1".."D6"
    organ_id: int                                 # 0=saglikli, 1=kanserli
    label: str                                    # "healthy" / "cancer"
    conf: float                                   # YOLO conf
    reliability: float                            # solidity * conf (kedi gibi)
    centroid_px: tuple[float, float]
    # D1.100 (B-5.16 · İG-5.72): ArUco kipinde geçersiz kesişim → konum ÜRETİLMEZ (None + `konum_hatasi`), doz yok.
    centroid_cabin_mm: tuple[float, float, float] | None
    centroid_cabin_cm: tuple[float, float, float] | None
    bbox_px: tuple[int, int, int, int]            # x, y, w, h
    area_px: int
    # D1.E07 (İG-5.76): PİKSEL kipinde (ölçek yok) None — eskiden px² "mm²" diye yazılıyordu.
    area_mm2: float | None
    n_cancer_pixels: int = 0                      # HSV mavi piksel sayisi
    # Kontur (simplifie, kedi `segmentation.mask_xy` gibi):
    mask_xy: list[list[float]] = field(default_factory=list)
    D: list[float] = field(default_factory=list)
    P: list[float] = field(default_factory=list)
    # D1.E07: doz hesaplanmadıysa (piksel kipi) None — 0.0 "hesaplandı, sıfır" diye okunur (Y6).
    E_healthy: float | None = None
    E_cancer: float | None = None
    E_avg: float | None = None
    konum_hatasi: str | None = None
    source: str = "yolo"                          # plaka: yolo / hough / grid
    # Plaka modu (goreli renk siniflandirma + plaka cercevesi):
    plate_mm: tuple[float, float] | None = None   # A1 = (0,0), ArUco modunda da dolu
    blue_frac: float | None = None                # maske icinde mavi HSV orani
    lab_b: float | None = None                    # medyan Lab b* (negatif = mavi)
    delta_b: float | None = None                  # lab_b - plaka medyani
    cancer_reasons: list[str] = field(default_factory=list)


@dataclass
class PipelineResult:
    schema_version: str = "v3.3"           # +coord_frame, pemf_valid, classification, warnings
    success: bool = False
    timestamp: float = 0.0
    cabin_id: str = ""
    image_name: str = ""
    n_wells: int = 0
    n_cancer: int = 0
    n_healthy: int = 0
    method: str = ""                       # "aruco_pnp" / "plate_grid" / "petri_diameter" / "pixel"
    mm_per_px: float = 1.0
    cabin_pose: dict[str, Any] = field(default_factory=dict)
    camera_calib: dict[str, Any] = field(default_factory=dict)
    # Kedi paterninden yeni alanlar:
    R_matrix: list[list[float]] = field(default_factory=list)        # cabin <- marker rotation
    pnp_fit: dict[str, Any] = field(default_factory=dict)            # yaw/pitch/roll/residual
    plate: dict[str, Any] = field(default_factory=dict)              # plate_grid ozeti
    # v2: koordinat cercevesi + PEMF gecerliligi + siniflandirma + toplu uyarilar
    coord_frame: str = ""                  # cabin_aruco / cabin_placement / plate / pixel
    pemf_valid: bool = False               # tahmin girdisi gercek kabin koordinati mi
    classification: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    wells: list[WellPrediction] = field(default_factory=list)
    timing_ms: dict[str, float] = field(default_factory=dict)
    error: str | None = None
    # Makullik olcumleri (dairesellik/conf/alan-orani + oy). YENI ALAN, geriye-uyumlu: mevcut
    # JSON tuketicileri (frontend, ai_service) bilmedigi alani yok sayar. Reddedilen istekte
    # ayrica "message" tasir → ai_router bunu 422 govdesinde kullaniciya aynen gosterir.
    plausibility: dict[str, Any] = field(default_factory=dict)
    #: Kucultme uygulandiysa {"from":[w,h],"to":[w,h],"max":N} — uygulanmadiysa BOS.
    resize: dict[str, Any] = field(default_factory=dict)
    #: Bu sonucu ureten ETKIN YOLO ayarlari (arayuzden ayarlanabilir) — denetim izi.
    yolo_ayar: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = {k: v for k, v in self.__dict__.items() if k != "wells"}
        d["wells"] = [asdict(w) for w in self.wells]
        return _json_safe(d)


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
                 yolo_device: str = "auto",
                 cancer_pixel_threshold: int = 30,
                 resize_max: int | None = None,
                 plaus_esikler: dict | None = None,
                 plaus_guard: bool | None = None,
                 plate_type: int | None = None,
                 cancer_frac: float | None = None,
                 cancer_db: float | None = None,
                 a1_corner: str | None = None,
                 control_healthy: list[str] | None = None,
                 control_cancer: list[str] | None = None,
                 a1_cabin_mm: list[float] | None = None):
        """Plaka parametreleri None ise YAML `multiwell:` bolumunden alinir
        (CLI > YAML > varsayilan). plate_type=0 -> plaka modu kapali (tekil petri / YOLO)."""
        if isinstance(cfg, CabinConfig):
            self.cfg = cfg
        else:
            self.cfg = load_cabin_config(cfg)
        mw = self.cfg.multiwell
        self.petri_diameter_cm = petri_diameter_cm
        # Cok kuyucuklu plaka (24/12/48/96): izgara tabanli tespit
        self.plate_type = (mw.plate_type if plate_type is None else plate_type) or None
        self.a1_corner = a1_corner or mw.a1_corner
        # Plaka modu kanser esikleri (goreli; bkz. color_segment.classify_plate_wells)
        self.cancer_frac = mw.cancer_frac if cancer_frac is None else cancer_frac
        self.cancer_db = mw.cancer_db if cancer_db is None else cancer_db
        self.cancer_abs_b = mw.cancer_abs_b
        self.control_healthy = [w.upper() for w in (control_healthy if control_healthy
                                                     is not None else mw.control_healthy)]
        self.control_cancer = [w.upper() for w in (control_cancer if control_cancer
                                                   is not None else mw.control_cancer)]
        # PEMF icin plakanin kabin konumu (ArUco yoksa)
        self.a1_cabin_mm = a1_cabin_mm if a1_cabin_mm is not None else mw.a1_cabin_mm
        self.col_axis = np.asarray(mw.col_axis_cabin, dtype=np.float64)
        self.row_axis = np.asarray(mw.row_axis_cabin, dtype=np.float64)
        # Kuyucuk icinde >= bu kadar mavi piksel varsa kanser
        self.cancer_pixel_threshold = cancer_pixel_threshold
        # ISTEK BASINA ayarlar (arayuzden gelir). Dedektor onbellekte PAYLASILDIGI icin
        # conf/iou nesneye YAZILMAZ, `detect()`e cagri basina gecirilir.
        self._yolo_conf = float(yolo_conf)
        self._yolo_iou = float(yolo_iou)
        #: Uzun kenar bu degeri asarsa goruntu KUCULTULUR (0/None = kapali).
        self.resize_max = int(resize_max) if resize_max else None
        self._plaus_esikler = dict(plaus_esikler) if plaus_esikler else None
        self._plaus_guard = plaus_guard

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

    def _olcekli_intrinsics(self, w: int, h: int) -> None:
        """Yuklenen K matrisini goruntu cozunurlugune OLCEKLE.

        ⚠️ ZORUNLU (2026-09-09): `intrinsics_npz` bir dosyadan gelirse K, KALIBRASYON
        cozunurlugune aittir (fx, fy, cx, cy piksel birimindedir). Goruntu baska bir
        cozunurlukteyse — resize eklendigi icin ARTIK SIK — olceklenmemis K ile solvePnP
        SESSIZCE yanlis 3B koordinat uretir. Yakin-tespit: `approx_intrinsics_from_marker`
        yolu K'yi goruntuden turettigi icin bu sorundan etkilenmez; bu yuzden ariza yalniz
        gercek kalibrasyon dosyasi konuldugunda ortaya cikardi.
        """
        if self.intrinsics is None:
            return
        # TD4: kural ortak işlevde (fantom v3 de kullanır — orada eksikti). T2D-2: kenar oranı farklıysa None → yaklaşık K.
        self.intrinsics = olcekli_intrinsics(self.intrinsics, w, h)

    def _ensure_intrinsics(self, image_bgr: np.ndarray) -> bool:
        if self.intrinsics is not None:
            h, w = image_bgr.shape[:2]
            self._olcekli_intrinsics(w, h)
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

        # 0) RESIZE — YOLO girdisi 640x640'a SABIT export edilmis; 4032 px'lik bir telefon
        # fotografinda kuyucuklar o boyuta inince tespit edilemiyor (olculdu). Kucultme
        # OLCEK-GUVENLIDIR cunku petri olcegi GORUNTUNUN ICINDEN gelir (kuyu capi ya da
        # kabin isareti) ve kalibrasyon K'si `_olcekli_intrinsics` ile birlikte olceklenir.
        if self.resize_max:
            h0, w0 = image_bgr.shape[:2]
            if max(h0, w0) > self.resize_max:
                o = float(self.resize_max) / float(max(h0, w0))
                image_bgr = cv2.resize(image_bgr, (max(1, int(round(w0 * o))), max(1, int(round(h0 * o)))),
                                       interpolation=cv2.INTER_AREA)
                result.resize = {"from": [w0, h0], "to": [image_bgr.shape[1], image_bgr.shape[0]],
                                 "max": int(self.resize_max)}

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
                # TD4: ters takılı işaret (kâğıt 180°) → kabin X / Y aynalanır; uyarı pemf kapısında ENGELLEYİCİ.
                if isaret_ters_mi(cabin_pose, self.cfg):
                    result.warnings.append(f"marker_upside_down: {ISARET_TERS_METNI}")
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
        grid = None
        if self.plate_type:
            # Plaka modu: pembe bolge + YOLO/Hough adaylari + izgara homografisi
            grid = detect_plate_wells(img_und, self.plate_type, yolo=self.yolo,
                                      a1_corner=self.a1_corner)
            result.plate = grid.to_dict()
            dets = grid.detections
            timings["plate_grid"] = (time.perf_counter() - t1) * 1000
        else:
            # ⚠️ conf/iou CAGRI BASINA: paylasilan onbellekli dedektorun alanini yazmak
            # es-zamanli ikinci analizin esigini degistirirdi.
            dets = self.yolo.detect(img_und, conf=self._yolo_conf, iou=self._yolo_iou)
            timings["yolo_detect"] = (time.perf_counter() - t1) * 1000
        if not dets:
            result.error = (grid.error if grid is not None
                            else "yolo_no_well_detected")
            result.timing_ms = timings
            result.timing_ms["total"] = (time.perf_counter() - t0) * 1000
            return result, ctx

        # 3b) MAKULLIK DENETIMI — "tespit VAR" ile "PETRI tespiti var" ayni sey degil.
        # YOLO fantom fotografinda da 2 nesne buluyordu; bu kod olmadan boru hatti onlar icin
        # PetriPredictor'i calistirip E_cancer/D/P uretiyor ve success=True donuyordu. Karar
        # RESIM DUZEYINDE (medyan + 2-of-3 oy); kuyu listesi BUDANMAZ — mesru kuyucuklarin
        # bireysel conf'u 0.42'ye kadar dusebiliyor, tek tek eleme gercek kuyulari sessizce yutar.
        # AI-2: PLAKA kipinde kuyucuklar cizilen izgaradir (dairesellik ~1) -> tekil kipin uc sinyali anlamsiz; ayri kural
        # (ECC + dogrulanmis aday; olculdu, bkz. plausibility.analyze_plate). Tekil kip v1 kuralini aynen kullanir.
        t1 = time.perf_counter()
        h_img, w_img = img_und.shape[:2]
        if grid is not None:
            ok_plaus, plaus_metrics = _plaus.evaluate_plate(result.plate, self._plaus_guard)
        else:
            ok_plaus, plaus_metrics = _plaus.evaluate(
                [d.contour for d in dets], [d.conf for d in dets],
                float(h_img) * float(w_img),
                self._plaus_esikler, self._plaus_guard)
        timings["plausibility"] = (time.perf_counter() - t1) * 1000
        result.plausibility = plaus_metrics
        result.yolo_ayar = {"conf": self._yolo_conf, "iou": self._yolo_iou,
                            "imgsz": int(getattr(self.yolo, "imgsz", 0) or 0),
                            "plate_type": int(self.plate_type or 0)}
        if grid is not None:
            # Plaka kipinde YOLO yalniz IPUCU: aday kirpintisi boyutu ve sayisi (ONNX 640 uyarlamasi GIZLENMEZ).
            from .plate_grid import aday_imgsz as _aday_imgsz

            result.yolo_ayar["aday_imgsz"] = _aday_imgsz(self.yolo)
            result.yolo_ayar["n_yolo_candidates"] = result.plate.get("n_yolo_candidates")
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
        elif grid is not None:
            # Bilinen kuyucuk araligindan (19.3 mm @24'luk) -> perspektif-dogru
            result.method = "plate_grid"
            result.mm_per_px = grid.mm_per_px
        elif self.petri_diameter_cm is not None:
            result.method = "petri_diameter"
            result.mm_per_px = (self.petri_diameter_cm * 10.0) / max(bbox_max, 1.0)
        else:
            result.method = "pixel"
            result.mm_per_px = 1.0

        # Referans nokta (piksel modunda): en buyuk kuyucuk merkezi
        # = "origin" sayilir (cabin frame'de 0,0)
        ref_cx, ref_cy = primary.centroid_px

        H_inv = (np.linalg.inv(grid.H_img_from_plate)
                 if grid is not None and cabin_pose is None else None)
        placement = (np.asarray(self.a1_cabin_mm, dtype=np.float64)
                     if H_inv is not None and self.a1_cabin_mm is not None else None)

        # Koordinat cercevesi: PEMF modeli KABIN cercevesinde egitildi
        # (egitim x,y,z ort ~ (37,-2,-45) mm, std ~ (141,176,111)). Plaka ya da
        # piksel cercevesindeki koordinatla tahmin fiziksel olarak anlamsizdir.
        if cabin_pose is not None:
            result.coord_frame, result.pemf_valid = "cabin_aruco", True
        elif placement is not None:
            result.coord_frame, result.pemf_valid = "cabin_placement", True
        elif H_inv is not None:
            result.coord_frame, result.pemf_valid = "plate", False
        else:
            result.coord_frame, result.pemf_valid = result.method, False
        if not result.pemf_valid:
            result.warnings.append(
                "pemf_frame_unknown: kabin konumu yok (ArUco veya multiwell.placement."
                "a1_cabin_mm) - D/P/E tahminleri fiziksel olarak gecersiz")

        def _to_mm(px: tuple[float, float]) -> tuple[float, float, float]:
            if cabin_pose is not None:
                v = pixel_to_cabin_mm(px, cabin_pose, self.intrinsics, self.cfg)
                return float(v[0]), float(v[1]), float(v[2])
            if H_inv is not None:
                q = cv2.perspectiveTransform(
                    np.array([[px]], dtype=np.float64), H_inv)[0, 0]
                if placement is not None:
                    # Sabit tutucu: A1 kabin konumu + plaka eksenleri (y = satir yonu)
                    v = placement + q[0] * self.col_axis + q[1] * self.row_axis
                    return float(v[0]), float(v[1]), float(v[2])
                # Plaka cercevesi: A1 = origin, x = sutun yonu, y yukari (Y flip)
                return float(q[0]), float(-q[1]), 0.0
            dx = (px[0] - ref_cx) * result.mm_per_px
            dy = (ref_cy - px[1]) * result.mm_per_px        # Y flip
            return float(dx), float(dy), 0.0

        def _contour_area_mm2(contour: np.ndarray) -> float:
            """Contour noktalarini cabin frame'e cevir, mm^2 alan hesapla.

            ArUco modunda: ray-plane intersection ile her nokta dogru cabin mm
            Diger modlarda: area_px * mm_per_px^2 (sabit oran)
            """
            if cabin_pose is None and H_inv is None:
                # Sabit mm/px: hızlı formul
                area_px = float(cv2.contourArea(contour))
                return area_px * (result.mm_per_px ** 2)
            # ArUco / plaka: contour'u alt-orneklemden mm cercevesine cevir
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
        # ⚠️ D1.E07 (İG-5.76): PİKSEL kipinde (ölçek yok) koordinat piksel farkıdır — doz modeline mm diye verilmez,
        # doz/E hesaplanmaz (None) ve alan mm² sayılmaz. ArUco ve petri çapı kipleri fiziksel ölçek taşır.
        _fiziksel_olcek = result.method != "pixel"

        # YOLO sonuclari sol-ust -> sag-alt sirala (well_id atamasi icin)
        if grid is not None:
            dets_sorted = dets          # izgara sirasi: A1, A2, ..., D6
        else:
            dets_sorted = sorted(dets, key=lambda d: (d.centroid_px[1] // 50,
                                                      d.centroid_px[0]))
        ctx["detections"] = dets_sorted   # render icin wells ile ayni sirada

        colors = None
        if grid is not None:
            colors, cls_info = classify_plate_wells(
                img_und, self.cfg.segmentation, [d.mask for d in dets_sorted],
                well_ids=grid.well_ids,
                frac_thr=self.cancer_frac, db_thr=self.cancer_db,
                abs_b_thr=self.cancer_abs_b,
                control_healthy=self.control_healthy,
                control_cancer=self.control_cancer)
            result.classification = cls_info
            result.warnings.extend(cls_info["qc"])

        for i, det in enumerate(dets_sorted, 1):
            well_id = grid.well_ids[i - 1] if grid is not None else f"W{i}"
            # Kanser tespiti: HSV mavi piksel sayisi (plaka modunda goreli renk)
            n_cancer = self._count_cancer_pixels(img_und, det.mask)
            if colors is not None:
                organ_id = TUMOR if colors[i - 1].is_cancer else HEALTHY
            else:
                organ_id = TUMOR if n_cancer >= self.cancer_pixel_threshold else HEALTHY
            label = "cancer" if organ_id == TUMOR else "healthy"

            # D1.100: ArUco kipinde geçersiz kesişim (kameranın arkası / paralel / kabin dışı) → konum ve alan YOK.
            konum_hatasi = None
            try:
                xyz = tuple(round(v, 3) + 0.0 for v in _to_mm(det.centroid_px))
            except KesisimGecersiz as e:
                xyz, konum_hatasi = None, str(e)
            # Alan: ArUco modunda contour cabin-frame integration,
            #       diger modlarda area_px * mm_per_px^2
            try:
                area_mm2 = _contour_area_mm2(det.contour) if (_fiziksel_olcek and xyz is not None) else None
            except KesisimGecersiz:
                area_mm2 = None

            # PetriPredictor
            pr = (
                self.predictor.predict(
                    x=xyz[0], y=xyz[1], z=xyz[2],
                    organ_id=organ_id, achieved_B=B, duty_sum=duty,
                )
                if _fiziksel_olcek and xyz is not None
                else None
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
                centroid_cabin_cm=(xyz[0] / 10, xyz[1] / 10, xyz[2] / 10) if xyz is not None else None,
                konum_hatasi=konum_hatasi,
                bbox_px=(int(x1), int(y1), int(x2 - x1), int(y2 - y1)),
                area_px=det.area_px, area_mm2=area_mm2,
                n_cancer_pixels=n_cancer,
                mask_xy=mask_xy,
                D=[pr[f"D{k}"] for k in range(1, 8)] if pr else [],
                P=[pr[f"P{k}"] for k in range(1, 8)] if pr else [],
                E_healthy=pr["result_E_healthy"] if pr else None,
                E_cancer=pr["result_E_cancer"] if pr else None,
                E_avg=pr["result_E_avg"] if pr else None,
                source=grid.sources[i - 1] if grid is not None else "yolo",
            )
            if grid is not None:
                wp.plate_mm = grid.wells_plate_mm[i - 1]
                c = colors[i - 1]
                wp.blue_frac, wp.lab_b, wp.delta_b = c.blue_frac, c.lab_b, c.delta_b
                wp.cancer_reasons = c.reasons
            result.wells.append(wp)

        timings["predict_all"] = (time.perf_counter() - t1) * 1000
        result.n_wells = len(result.wells)
        result.n_cancer = sum(1 for w in result.wells if w.organ_id == TUMOR)
        result.n_healthy = sum(1 for w in result.wells if w.organ_id == HEALTHY)
        if grid is not None:
            result.warnings = list(grid.warnings) + result.warnings
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
        # imdecode: Unicode yol (orn. 'guncel' -> 'güncel') her platformda okunur
        try:
            img = cv2.imdecode(np.fromfile(str(image_path), dtype=np.uint8),
                               cv2.IMREAD_COLOR)
        except (OSError, ValueError):
            img = None
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
