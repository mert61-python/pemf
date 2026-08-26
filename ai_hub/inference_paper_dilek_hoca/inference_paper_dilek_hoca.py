#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""inference_paper_dilek_hoca.py — CPN hucre segmentasyonu + scratch analizi (PEMF calismasi).

Model: **CPN — Contour Proposal Network** (celldetection paketi)
    Backbone: ResNeXt-101 + UNet decoder
    Agirlik: ginoro_CpnResNeXt101UNet-fbe875f1a3e5ce2c.pt (~872 MB, release_assets tek-kaynak)
    Kaynak: https://github.com/FZJ-INM1-BDA/celldetection (Apache-2.0 — dogrulandi 2026-08-26)

Task: PEMF calismasinin mikroskop hucre goruntulerinde tekil hucre instance
      segmentation + TScratch-benzeri wound-closure metrikleri (primary endpoint:
      closure_pct, mean/max gap um, gap area mm2).

VENDOR NOTU (2026-08-26 — guii sertlestirmeleri, plan: scratch-entegrasyon-plani.md):
  * Gelen kod `torch.load`'u GLOBAL monkey-patch'liyordu (weights_only=False surec
    geneli!) — Audit P3 sinifi regresyon. Patch `_cpn_yukleme_kapsami()`
    contextmanager'ina DARALTILDI: yalniz CPN ckpt yuklemesi sirasinda gecerli,
    finally ile geri alinir. ckpt release_assets tek-kaynagindan gelir.
  * `sys.path.insert(0, parent)` KALDIRILDI — "cell"/"xai_utils" gibi jenerik adlar
    ana servisin import uzayini kirletiyordu. Importlar paket-nitelikli.
  * PT cozumu tek yol: modul dizini -> ai_hub.xai_utils.pt_yolu.pt_coz
    (PEMF_AI_MODELS_DIR mount -> model_downloader -> acik hata).
  * Servis yuzu `scratch_analiz()`: TEK girdiden COKLU gorsel cikti bellek-ici
    base64 (disk yok) + tek-is kilidi (CPN thread-safe degil, 872 MB). OLCULDU:
    ham ornek PNG'ler 3-7 MB -> her cikti gorseli maks ~1280px + JPEG q85
    kucultulur (3-panel 1920px) — 6 gorselli yanit toplami ~<1.5 MB kalir.
  * `torch` importu fonksiyon-ici (modul importu hafif; postproc fonksiyonlari
    yalniz numpy/cv2 ile cell'siz calisir ve CI'da test edilir). Modul top-level'i
    BILEREK yalniz stdlib+numpy+cv2 import eder (bagimlilik-bekcisi ai_hub'i
    taramaz; AST testi tests/test_scratch_postproc.py bunu kilitler).

⚠️ `cell/` alt paketi teslimde KIRIK symlink'ti — bkz. __init__.py. Predictor,
paket gelene kadar acik RuntimeError verir; endpoint bunu 503'e cevirir.
"""
from __future__ import annotations

import base64
import contextlib
import logging
import os
import threading
from pathlib import Path

import cv2
import numpy as np

_LOG = logging.getLogger("pemf.scratch")

_DIR = Path(__file__).resolve().parent
_PT_REL = "ai_hub/inference_paper_dilek_hoca/ginoro_CpnResNeXt101UNet-fbe875f1a3e5ce2c.pt"
DEFAULT_MODEL = _DIR / "ginoro_CpnResNeXt101UNet-fbe875f1a3e5ce2c.pt"

# Inference varsayilan parametreleri (v4 script ile birebir)
SCORE_THRESH = 0.3
NMS_THRESH = float(np.round(np.pi / 10, 4))     # 0.3142
SAMPLES = 16
TILE_SIZE = 1664
OVERLAP = 384

# --- Cizim parametreleri (v4 script'ten) ---
FONT = cv2.FONT_HERSHEY_SIMPLEX
FONT_SCALE = 0.6
FONT_THICK = 2
TEXT_COLOR = (0, 0, 255)                          # BGR — kirmizi
LINE_SPACE = 24

# --- ROI kusagi (analysis fonksiyonu icin) ---
HALF_BAND_RATIO = 0.10                            # toplam %20 ROI
BLOB_MAX_DEVIATION = 300                          # sari marker mesafe limiti (px)

# --- Closure analizi (quantitative scratch wound healing) ---
SCRATCH_ROI_RATIO = 0.30                          # ROI genisligi = %30 goruntu genisligi
SMOOTH_KERNEL = np.ones((5, 5), np.uint8)
SMOOTH_ITERS = 3                                   # gap-width olcumu icin morfoloji

# --- Kalibrasyon (mm / pixel) ---
# 4x objektif ~1.6 um/px = 0.0016 mm/px (default) | 10x 0.00065 | 20x 0.00033 | 40x 0.00016
PIXEL_TO_MM_DEFAULT = 0.0016


# ============================================================
# torch.load compat — KAPSAMLI (gelen koddaki GLOBAL patch'in guvenli hali)
# ============================================================
@contextlib.contextmanager
def _cpn_yukleme_kapsami():
    """CPN ckpt yuklemesi SIRASINDA weights_only=False'a izin ver, sonra GERI AL.

    PyTorch >=2.6 default'u weights_only=True; CPN ckpt icinde celldetection'in
    Config sinifi pickle'li -> once add_safe_globals denenir. Gelen kod torch.load'u
    surec-geneli patch'liyordu (Audit P3: ayni surecteki TUM model yuklemeleri
    pickle'a acilirdi) — burada patch bu with-blogu ile sinirli ve finally'de
    kosulsuz geri alinir.
    """
    import torch

    try:
        import celldetection.util.schedule as _sched
        torch.serialization.add_safe_globals([_sched.Config])
    except Exception:
        pass
    _orig = torch.load

    def _wrap(*a, **kw):
        kw.setdefault("weights_only", False)
        return _orig(*a, **kw)

    torch.load = _wrap
    try:
        yield
    finally:
        torch.load = _orig


def _goruntu_oku(image_path) -> np.ndarray:
    """BGR uint8 goruntu (UTF-8/bosluklu yollar icin np.frombuffer ile oku)."""
    with open(str(image_path), "rb") as f:
        buf = np.frombuffer(f.read(), dtype=np.uint8)
    img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    if img is None:
        raise FileNotFoundError(f"Goruntu okunamadi: {image_path}")
    return img


class ModelKurulumEksik(RuntimeError):
    """cell/ paketi ya da 872MB PT bu kurulumda yok — 503'e esler.

    DUSMAN-DOGRULAMA DERSI (2026-08-26): 'except RuntimeError -> 503' cok genisti —
    CUDA OOM ve JPG-encode hatalari da RuntimeError'dir ve kullaniciya YANLIS
    'model paketi gerekli' teshisi gosterirdi. Kurulum eksigi artik BU tip."""


class ScratchMesgul(RuntimeError):
    """Tek-is kilidi zaman asiminda alinamadi — 429'a esler.

    DUSMAN-DOGRULAMA DERSI (YUKSEK): auth-muaf ucta dakikalarca kilit bekleyen
    to_thread thread'leri event-loop'un TEK default executor'unu doldurur; ayni
    executor'u kullanan _emergency_stop_all (E-STOP!) bile kuyruga girerdi.
    Kilit artik KISA timeout'la denenir; mesgulse istek aninda 429 alir."""


_KILIT_BEKLEME_SN = 5.0


def _cell_import():
    """cell paketini paket-nitelikli yoldan getir; yoksa ACIK hata (sessiz degil)."""
    try:
        from ai_hub.inference_paper_dilek_hoca.cell.cpn import CpnInterface
        from ai_hub.inference_paper_dilek_hoca.cell.prep import multi_norm
        return CpnInterface, multi_norm
    except ImportError as e:
        raise ModelKurulumEksik(
            "cell/ paketi eksik: CpnInterface + multi_norm sahibin "
            "training/paper_dilek_hoca/cell paketinden gelmeli (teslimdeki symlink "
            "kirikti). ai_hub/inference_paper_dilek_hoca/cell/ olarak ekleyin."
        ) from e


# ============================================================
# PREDICTOR
# ============================================================
class CellSegmentationPredictor:
    """CPN (ResNeXt-101 UNet) tabanli hucre instance segmentation.

    Args:
        model_path: .pt yolu. None ise modul dizini -> pt_coz sirasiyla cozulur.
        device: "cuda:0" / "cpu" / None (auto).
        score_thresh, nms_thresh, samples: CPN inference parametreleri.
    """

    def __init__(self,
                 model_path: str | os.PathLike | None = None,
                 device: str | None = None,
                 score_thresh: float = SCORE_THRESH,
                 nms_thresh: float = NMS_THRESH,
                 samples: int = SAMPLES):
        CpnInterface, _ = _cell_import()
        import torch

        if model_path is None:
            if DEFAULT_MODEL.exists():
                model_path = DEFAULT_MODEL
            else:
                from ai_hub.xai_utils.pt_yolu import pt_coz

                try:
                    model_path = pt_coz(_PT_REL)
                except FileNotFoundError as e:
                    # Kurulum eksigi (503) — CUDA/inference RuntimeError'lariyla KARISMAZ
                    raise ModelKurulumEksik(str(e)) from e
        self.model_path = Path(model_path)
        if not self.model_path.exists():
            raise ModelKurulumEksik(f"CPN model bulunamadi: {self.model_path}")

        if device is None:
            device = "cuda:0" if torch.cuda.is_available() else "cpu"
        self.device = device

        with _cpn_yukleme_kapsami():
            self.cpn = CpnInterface(
                str(self.model_path),
                device=device,
                score_thresh=score_thresh,
                nms_thresh=nms_thresh,
                samples=samples,
            )
        # tile parametrelerini sabitle
        self.cpn.tile_size = TILE_SIZE
        self.cpn.overlap = OVERLAP
        self.score_thresh = score_thresh
        self.nms_thresh = nms_thresh

    # ------------------------------------------------------------
    def _read_image(self, image_path) -> np.ndarray:
        return _goruntu_oku(image_path)

    # ------------------------------------------------------------
    def predict(self, image_path: str | os.PathLike,
                *, return_contours: bool = False,
                compute_closure: bool = True,
                pixel_mm: float = PIXEL_TO_MM_DEFAULT) -> dict:
        """Tek goruntude hucre segmentasyonu + closure metrikleri (opsiyonel).

        Donen dict'te "_labels" (H,W int) ve "_binary" (0/255) INTERNAL numpy
        alanlari vardir (cizimler icin); JSON'a basmadan once '_' alanlari ayikla.
        """
        _, multi_norm = _cell_import()

        img_bgr = self._read_image(image_path)
        img_norm = multi_norm(img_bgr, "cstm-mix")

        result = self.cpn(img_norm, reduce_labels=True,
                          return_labels=True,
                          return_viewable_contours=False)

        contours = result["contours"]
        labels = result["labels"]                        # (H, W) int
        boxes = result["boxes"]                          # (N, 4)
        scores = result["scores"]                        # (N,)

        n_cells = int(labels.max()) if labels is not None else int(len(contours))

        areas = []
        if labels is not None and n_cells:
            for lid in range(1, n_cells + 1):
                a = int((labels == lid).sum())
                if a > 0:
                    areas.append(a)
        area_mean = float(np.mean(areas)) if areas else 0.0
        area_median = float(np.median(areas)) if areas else 0.0
        coverage = float((labels > 0).mean()) if labels is not None else 0.0

        out = {
            "image_path": str(image_path),
            "image_shape": [int(img_bgr.shape[0]), int(img_bgr.shape[1])],
            "n_cells": n_cells,
            "cell_area_mean": round(area_mean, 2),
            "cell_area_median": round(area_median, 2),
            "coverage_ratio": round(coverage, 4),
            "score_mean": round(float(np.mean(scores)) if len(scores) else 0.0, 4),
            "score_min": round(float(np.min(scores)) if len(scores) else 0.0, 4),
            "boxes": [[int(v) for v in b] for b in boxes],
            "labels_max": n_cells,
        }
        binary = None
        if labels is not None:
            binary = (labels > 0).astype(np.uint8) * 255

        if compute_closure and binary is not None:
            cm = compute_closure_metrics(binary, pixel_mm=pixel_mm)
            cm["pixel_mm"] = pixel_mm
            out["closure"] = cm

        if return_contours:
            out["contours"] = [c.astype(int).tolist() for c in contours]
        out["_labels"] = labels
        out["_binary"] = binary
        return out

    # ------------------------------------------------------------
    def seg_gorselleri(self, image_path, result: dict) -> tuple[np.ndarray, np.ndarray]:
        """(seg_rgb, overlay_rgb) — renkli label haritasi + orijinalle karisimi.

        BELLEK-ICI (disk yok): servis yuzu base64 doner (karar #3 anlik gosterim).
        """
        from celldetection import label_cmap

        labels = result.get("_labels")
        if labels is None:
            raise ValueError("seg_gorselleri icin predict() sonucu gerekli (_labels).")

        vis = label_cmap(labels)
        if vis.dtype != np.uint8:
            vis = (vis * 255).astype(np.uint8) if vis.max() <= 1.0 else vis.astype(np.uint8)
        if vis.ndim == 3 and vis.shape[2] == 4:
            vis = vis[..., :3]

        img_bgr = self._read_image(image_path)
        img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        if vis.shape[:2] != img_rgb.shape[:2]:
            vis = cv2.resize(vis, (img_rgb.shape[1], img_rgb.shape[0]),
                             interpolation=cv2.INTER_NEAREST)
        overlay = np.clip(img_rgb.astype(np.float32) * 0.55
                          + vis.astype(np.float32) * 0.45, 0, 255).astype(np.uint8)
        return vis, overlay


# ============================================================
# POST-PROCESSING (v4 script'ten — SAF numpy/cv2, model/cell GEREKMEZ)
# ============================================================
def to_binary_mask(vis_labels: np.ndarray) -> np.ndarray:
    """Renkli label/segmentation goruntusunden binary mask (0/255)."""
    arr = np.asarray(vis_labels)
    if arr.dtype != np.uint8:
        if arr.max() <= 1.0:
            arr = (arr * 255).astype(np.uint8)
        else:
            arr = arr.astype(np.uint8)
    if arr.ndim == 3:
        if arr.shape[2] == 4:
            gray = cv2.cvtColor(arr, cv2.COLOR_RGBA2GRAY)
        elif arr.shape[2] == 3:
            gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
        else:
            gray = arr[:, :, 0]
    else:
        gray = arr
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY)
    return binary


def compute_closure_metrics(binary: np.ndarray,
                            pixel_mm: float = PIXEL_TO_MM_DEFAULT) -> dict:
    """Scratch-wound closure metrikleri (goruntu uretmez, hizli).

    ⚠️ DIKEY scratch varsayar: ROI = goruntu ortasinda DIKEY bant (genisligin
    %30'u), gap'ler KOLON bazinda olculur. Yatay scratch'te sonuclar yaklasik
    olur — servis yuzu bu durumda closure_uyari alani doner.
    """
    h, w = binary.shape
    band = max(int(0.10 * w), int(SCRATCH_ROI_RATIO * w))
    cx = w // 2
    left = max(0, cx - band // 2)
    right = min(w, cx + band // 2)
    roi = binary[:, left:right]
    roi_w = roi.shape[1]

    # Smoothing (yalnizca gap-width hesabi icin)
    roi_smooth = cv2.dilate(roi, SMOOTH_KERNEL, iterations=SMOOTH_ITERS)
    roi_smooth = cv2.erode(roi_smooth, SMOOTH_KERNEL, iterations=SMOOTH_ITERS)

    cell_px = int(np.sum(roi > 0))
    total_px = int(roi.size)
    bg_px = total_px - cell_px
    closure_pct = 100.0 * cell_px / total_px if total_px > 0 else 0.0
    gap_area_mm2 = bg_px * (pixel_mm * pixel_mm)

    # Kolon basi en uzun siyah run
    inv = (roi_smooth == 0).astype(np.uint8)
    gap_widths_px = np.zeros(roi_w, dtype=np.int32)
    for col_idx in range(roi_w):
        col = inv[:, col_idx]
        if col.sum() == 0:
            gap_widths_px[col_idx] = 0
            continue
        padded = np.concatenate([[0], col, [0]])
        diff = np.diff(padded)
        starts = np.where(diff == 1)[0]
        ends = np.where(diff == -1)[0]
        runs = ends - starts
        gap_widths_px[col_idx] = int(runs.max()) if runs.size else 0

    mean_gap_um = float(np.mean(gap_widths_px)) * pixel_mm * 1000.0
    max_gap_um = float(np.max(gap_widths_px)) * pixel_mm * 1000.0

    max_col_idx = int(np.argmax(gap_widths_px))
    mean_val = float(np.mean(gap_widths_px))
    mean_col_idx = int(np.argmin(np.abs(gap_widths_px.astype(np.float64) - mean_val)))

    return {
        "closure_pct": round(closure_pct, 2),
        "mean_gap_um": round(mean_gap_um, 1),
        "max_gap_um": round(max_gap_um, 1),
        "gap_area_mm2": round(gap_area_mm2, 4),
        "roi_left": int(left),
        "roi_right": int(right),
        "max_gap_col": int(left + max_col_idx),
        "mean_gap_col": int(left + mean_col_idx),
    }


def draw_closure(binary: np.ndarray,
                 metrics: dict | None = None,
                 pixel_mm: float = PIXEL_TO_MM_DEFAULT) -> np.ndarray:
    """v4.closure() gorsellemesi — RGB uint8 doner (metrics=None ise hesaplar)."""
    if metrics is None:
        metrics = compute_closure_metrics(binary, pixel_mm)
    h, w = binary.shape
    left, right = metrics["roi_left"], metrics["roi_right"]

    result = cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)
    overlay = result.copy()
    cv2.rectangle(overlay, (left, 0), (right, h), (0, 255, 255), -1)
    result = cv2.addWeighted(overlay, 0.08, result, 0.92, 0)
    cv2.line(result, (left, 0), (left, h - 1), (0, 255, 255), 2)
    cv2.line(result, (right - 1, 0), (right - 1, h - 1), (0, 255, 255), 2)

    max_col_x = metrics["max_gap_col"]
    mean_col_x = metrics["mean_gap_col"]
    cv2.line(result, (max_col_x, 0), (max_col_x, h - 1), (0, 0, 255), 3)
    cv2.line(result, (mean_col_x, 0), (mean_col_x, h - 1), (255, 0, 0), 3)

    y = LINE_SPACE
    cv2.putText(result, f"ROI closure: {metrics['closure_pct']:.1f}%",
                (10, y), FONT, FONT_SCALE, TEXT_COLOR, FONT_THICK)
    cv2.putText(result, f"Mean gap width: {metrics['mean_gap_um']:.0f} um (blue line)",
                (10, y + LINE_SPACE), FONT, FONT_SCALE, (255, 0, 0), FONT_THICK)
    cv2.putText(result, f"Max gap width: {metrics['max_gap_um']:.0f} um (red line)",
                (10, y + 2 * LINE_SPACE), FONT, FONT_SCALE, TEXT_COLOR, FONT_THICK)
    cv2.putText(result, f"Gap area: {metrics['gap_area_mm2']:.3f} mm^2",
                (10, y + 3 * LINE_SPACE), FONT, FONT_SCALE, TEXT_COLOR, FONT_THICK)
    return cv2.cvtColor(result, cv2.COLOR_BGR2RGB)


def draw_analysis(binary: np.ndarray, vertical_box: bool = False) -> np.ndarray:
    """v4.analysis() gorsellemesi — RGB uint8 doner.

    vertical_box=False: YATAY ROI kusagi (scratch DIKEY ise; default)
    vertical_box=True : DIKEY ROI kusagi (scratch YATAY ise)
    """
    vis_bgr = cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)
    height, width = binary.shape

    half_band_v = max(50, int(HALF_BAND_RATIO * width))
    half_band_h = max(50, int(HALF_BAND_RATIO * height))

    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL,
                                   cv2.CHAIN_APPROX_SIMPLE)
    white = int(np.sum(binary > 0))
    black = int(binary.size - white)
    overall_ratio = (black // white) if white > 0 else "No cancer"

    if not vertical_box:
        cy = height // 2
        top, bot = max(0, cy - half_band_h), min(height, cy + half_band_h)
        roi = binary[top:bot, :]
        cnts_roi, _ = cv2.findContours(roi, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        roi_count = len(cnts_roi)
        roi_white = int(np.sum(roi > 0))
        roi_black = int(roi.size - roi_white)
        roi_ratio = (roi_black // roi_white) if roi_white > 0 else "No cancer"

        top_y = top_x = bot_y = bot_x = None
        for y in range(top - 1, -1, -1):
            if np.any(binary[y, :] > 0):
                top_y = y
                top_x = int(np.where(binary[y, :] > 0)[0][0])
                break
        for y in range(bot + 1, height):
            if np.any(binary[y, :] > 0):
                bot_y = y
                bot_x = int(np.where(binary[y, :] > 0)[0][0])
                break

        distance = None
        if top_y is not None and bot_y is not None:
            distance = bot_y - top_y
            if (top - top_y) <= BLOB_MAX_DEVIATION:
                cv2.circle(vis_bgr, (top_x, top_y), 10, (0, 255, 255), -1)
            if (bot_y - bot) <= BLOB_MAX_DEVIATION:
                cv2.circle(vis_bgr, (bot_x, bot_y), 10, (0, 255, 255), -1)

        cv2.line(vis_bgr, (0, top), (width - 1, top), (0, 0, 255), 3)
        cv2.line(vis_bgr, (0, bot - 1), (width - 1, bot - 1), (0, 0, 255), 3)
    else:
        cx = width // 2
        left, right = max(0, cx - half_band_v), min(width, cx + half_band_v)
        roi = binary[:, left:right]
        cnts_roi, _ = cv2.findContours(roi, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        roi_count = len(cnts_roi)
        roi_white = int(np.sum(roi > 0))
        roi_black = int(roi.size - roi_white)
        roi_ratio = (roi_black // roi_white) if roi_white > 0 else "No cancer"

        left_x = left_y = right_x = right_y = None
        for x in range(left - 1, -1, -1):
            if np.any(binary[:, x] > 0):
                left_x = x
                left_y = int(np.where(binary[:, x] > 0)[0][0])
                break
        for x in range(right + 1, width):
            if np.any(binary[:, x] > 0):
                right_x = x
                right_y = int(np.where(binary[:, x] > 0)[0][0])
                break

        distance = None
        if left_x is not None and right_x is not None:
            distance = right_x - left_x
            if (left - left_x) <= BLOB_MAX_DEVIATION:
                cv2.circle(vis_bgr, (left_x, left_y), 10, (0, 255, 255), -1)
            if (right_x - right) <= BLOB_MAX_DEVIATION:
                cv2.circle(vis_bgr, (right_x, right_y), 10, (0, 255, 255), -1)

        cv2.line(vis_bgr, (left, 0), (left, height - 1), (0, 0, 255), 3)
        cv2.line(vis_bgr, (right - 1, 0), (right - 1, height - 1), (0, 0, 255), 3)

    y0 = LINE_SPACE
    cv2.putText(vis_bgr, f"Total cells: {len(contours)}",
                (10, y0), FONT, FONT_SCALE, TEXT_COLOR, FONT_THICK)
    cv2.putText(vis_bgr, f"Bg/Cell area ratio: {overall_ratio}",
                (10, y0 + LINE_SPACE), FONT, FONT_SCALE, TEXT_COLOR, FONT_THICK)
    rx = max(width - 360, 10)
    cv2.putText(vis_bgr, f"ROI cells: {roi_count}",
                (rx, y0), FONT, FONT_SCALE, TEXT_COLOR, FONT_THICK)
    cv2.putText(vis_bgr, f"ROI bg/cell ratio: {roi_ratio}",
                (rx, y0 + LINE_SPACE), FONT, FONT_SCALE, TEXT_COLOR, FONT_THICK)
    cv2.putText(vis_bgr, f"Gap distance (px): {distance}",
                (rx, y0 + 2 * LINE_SPACE), FONT, FONT_SCALE, TEXT_COLOR, FONT_THICK)

    return cv2.cvtColor(vis_bgr, cv2.COLOR_BGR2RGB)


# ============================================================
# XAI — Grad-CAM/EigenCAM @ CPN backbone (BELLEK-ICI)
# ============================================================
def _resolve_cpn_backbone_and_target(lit_cpn_model):
    """CPN ResNeXt-101 UNet icinden backbone Module'unu + CAM target katmanini bul.

    Yapi (celldetection 0.4.x): LitCpn -> model -> core -> backbone -> body
    (IntermediateLayerGetter); body'nin son elemani ResNeXt layer4 karsiligi.
    """
    import torch.nn as nn

    for chain in (
        ["model", "model", "core", "backbone", "body"],
        ["model", "core", "backbone", "body"],
        ["model", "backbone", "body"],
    ):
        cur = lit_cpn_model
        try:
            for a in chain:
                cur = getattr(cur, a)
            body = cur
            break
        except AttributeError:
            body = None
    if body is None:
        last_conv = None
        for mod in lit_cpn_model.modules():
            if isinstance(mod, nn.Conv2d):
                last_conv = mod
        if last_conv is None:
            raise RuntimeError("CPN backbone bulunamadi.")
        return lit_cpn_model, last_conv

    children = list(body.children())
    return body, children[-1]


def _xai_cpn_bellekte(predictor: CellSegmentationPredictor,
                      image_path: str,
                      *, method: str = "eigencam") -> dict:
    """CPN backbone uzerinde CAM — overlay + 3-panel side-by-side, base64 (disk yok).

    CPN detection modeli; "target class" yok. _BackboneWrap en derin feature map'i
    GAP'leyip (B, C) dondurur — CAM feature-magnitude proxy'si. Default EigenCAM
    (label-agnostic; CPN icin en stabil). Isi haritasi ~layer4 cozunurlugunde
    KABA bolgesel ilgidir; hucre-duzeyi aciklama VAAT ETMEZ (UI metni de oyle).
    """
    import torch

    from ai_hub.xai_utils.grad_cam import GradCAMExplainer
    from ai_hub.xai_utils.overlay import blend_to_array, heatmap_to_rgb

    _, multi_norm = _cell_import()

    lit_model = predictor.cpn.model
    backbone, target_layer = _resolve_cpn_backbone_and_target(lit_model)

    class _BackboneWrap(torch.nn.Module):
        def __init__(self, b):
            super().__init__()
            self.b = b

        def forward(self, x):
            out = self.b(x)
            if isinstance(out, dict):
                out = list(out.values())[-1]
            if isinstance(out, (list, tuple)):
                out = out[-1]
            return out.mean(dim=(2, 3))

    wrap = _BackboneWrap(backbone).to(predictor.device).eval()
    # DUSMAN-DOGRULAMA DERSI (2026-08-26, hakem-onayli): predictor KALICI cache'te
    # yasar; bayraklar geri alinmazsa ilk explain'den SONRAKI HER normal analiz
    # grad-etkin kosar (1664px tile autograd -> VRAM sismesi) ve backward'in .grad
    # tensorleri (~355MB) cache'li modelde kalici kalirdi. finally ile RESTORE edilir.
    _eski_bayraklar = [(p, p.requires_grad) for p in wrap.parameters()]
    for p, _ in _eski_bayraklar:
        p.requires_grad_(True)

    try:
        img_bgr = predictor._read_image(image_path)
        img_norm = multi_norm(img_bgr, "cstm-mix")
        if img_norm.ndim == 2:
            img_norm = cv2.cvtColor(img_norm, cv2.COLOR_GRAY2RGB)
        H0, W0 = img_norm.shape[:2]
        max_side = 512                                   # GPU bellek korumasi
        if max(H0, W0) > max_side:
            scale = max_side / max(H0, W0)
            img_small = cv2.resize(img_norm, (int(W0 * scale), int(H0 * scale)),
                                   interpolation=cv2.INTER_AREA)
        else:
            img_small = img_norm
        arr = (img_small.astype(np.float32) / 255.0).transpose(2, 0, 1)[None]
        x_t = torch.from_numpy(arr).to(predictor.device)

        expl = GradCAMExplainer(wrap, target_layer=target_layer, method=method,
                                device=predictor.device)
        heatmap = expl.explain(x_t, class_idx=0)
        heatmap_orig = cv2.resize(heatmap.astype(np.float32), (W0, H0),
                                  interpolation=cv2.INTER_LINEAR)

        img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        overlay = blend_to_array(img_rgb, heatmap_orig, alpha=0.5)
        hm_rgb = heatmap_to_rgb(heatmap_orig)
        sep = np.full((img_rgb.shape[0], 8, 3), 255, dtype=np.uint8)
        panel = np.concatenate([img_rgb, sep, hm_rgb, sep, overlay], axis=1)

        return {
            "xai_image_base64": _jpg64(overlay),
            "xai_side_by_side_base64": _jpg64(panel, maks_w=PANEL_MAKS_GENISLIK),
            "xai_method": method,
        }
    finally:
        for p, eski in _eski_bayraklar:
            p.requires_grad_(eski)
            p.grad = None                                # backward artigi VRAM'i birak


# ============================================================
# SERVIS YUZU — tek girdi -> coklu gorsel cikti (base64, disk yok)
# ============================================================
_KILIT = threading.Lock()          # CPN thread-safe degil + 872 MB model: TEK IS
_PREDICTOR_CACHE: dict = {}

GECERLI_SCRATCH_YONLERI = ("dikey", "yatay")

# OLCULDU (plan v2 §2/10): ham ornek ciktilar 3-7 MB PNG; 4-6 gorselli JSON yanit
# ~15-20 MB olurdu (tunel/OOM). Cikti gorselleri kucultulur: standart 1280px,
# 3-panel (uc gorsel yan yana) 1920px. Toplam yanit ~<1.5 MB (bekci testi var).
CIKTI_MAKS_GENISLIK = 1280
PANEL_MAKS_GENISLIK = 1920


def _kucult(rgb: np.ndarray, maks_w: int = CIKTI_MAKS_GENISLIK) -> np.ndarray:
    h, w = rgb.shape[:2]
    if w <= maks_w:
        return rgb
    nh = max(1, int(h * maks_w / w))
    return cv2.resize(rgb, (maks_w, nh), interpolation=cv2.INTER_AREA)


def _jpg64(rgb: np.ndarray, quality: int = 85,
           maks_w: int = CIKTI_MAKS_GENISLIK) -> str:
    rgb = _kucult(rgb, maks_w)
    ok, buf = cv2.imencode(".jpg", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR),
                           [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise RuntimeError("JPG encode basarisiz")
    return base64.b64encode(buf.tobytes()).decode("ascii")


def scratch_analiz(image_path: str,
                   *, scratch_yonu: str = "dikey",
                   pixel_mm: float = PIXEL_TO_MM_DEFAULT,
                   explain: bool = False,
                   xai_method: str = "eigencam") -> dict:
    """TEK mikroskop goruntusunden coklu gorsel AI ciktisi (UI sozlesmesi).

    TEK-KAYNAK: router in-process + ai_service ayni fonksiyonu cagirir (kapi-paritesi).

    Args:
        scratch_yonu: "dikey" (default) | "yatay" — yaranin YONU. Analiz ROI'si
            yaraya DIK secilir (dikey yara -> yatay kusak). Closure metrikleri
            HER ZAMAN dikey-yara varsayimiyla hesaplanir; "yatay"da closure_uyari
            alani doner (metrikler yine verilir, yaklasik oldugu soylenir).
        pixel_mm: objektif kalibrasyonu (4x 0.0016 | 10x 0.00065 | 20x 0.00033 | 40x 0.00016)
        explain: True ise CAM overlay + 3-panel (XAI hatasi analizi DUSURMEZ —
            cagiran zarif dusus uygular).

    Returns: metrikler + seg/overlay/analysis/closure base64 gorselleri
        (+ explain'de xai_image_base64 / xai_side_by_side_base64 / xai_method).
    """
    if scratch_yonu not in GECERLI_SCRATCH_YONLERI:
        raise ValueError(f"scratch_yonu 'dikey' ya da 'yatay' olmali: {scratch_yonu!r}")
    # pixel_mm dogrulamasi TEK-KAYNAK burada (dusman-dogrulama: yalniz router'da
    # sinirlamak :8100'e dogrudan negatif deger + NEGATIF um sonucu birakiyordu)
    if not (0.00001 <= float(pixel_mm) <= 0.01):
        raise ValueError(f"pixel_mm 0.00001-0.01 araliginda olmali (mm/px): {pixel_mm}")

    # Orijinal girdi UI'da yalniz buradan gosterilebilir (TIF taraycida/RN'de
    # render EDILEMEZ — plan v2 §2/11): her yanitta input_image_base64 doner.
    girdi_rgb = cv2.cvtColor(_goruntu_oku(image_path), cv2.COLOR_BGR2RGB)

    # Cok kucuk goruntu: closure ROI'si dejenere olur (w<8'de bos-dizi istisnasi
    # olculdu) — karar 0.3 sozlesmesi geregi jenerik 500 degil yapilandirilmis uyari.
    if min(girdi_rgb.shape[:2]) < 32:
        return {
            "n_cells": 0, "closure": None,
            "uyari": "Goruntu cok kucuk (min 32px) — mikroskop karesini kontrol edin.",
            "scratch_yonu": scratch_yonu, "pixel_mm": pixel_mm,
            "input_image_base64": _jpg64(girdi_rgb),
        }

    # TEK-IS kilidi KISA timeout'la: dakikalarca kilitte bekleyen to_thread
    # thread'leri default executor'u doldurup E-STOP'un to_thread cagrisini bile
    # geciktirebilirdi (hakem-onayli YUKSEK bulgu). Mesgulse aninda ScratchMesgul.
    if not _KILIT.acquire(timeout=_KILIT_BEKLEME_SN):
        raise ScratchMesgul(
            "Su anda baska bir yara-kapanma analizi suruyor — birazdan yeniden deneyin.")
    try:
        pred = _PREDICTOR_CACHE.get("cpn")
        if pred is None:
            pred = CellSegmentationPredictor()
            _PREDICTOR_CACHE["cpn"] = pred

        res = pred.predict(image_path, compute_closure=True, pixel_mm=pixel_mm)

        yanit = {
            "n_cells": res["n_cells"],
            "coverage_ratio": res["coverage_ratio"],
            "cell_area_mean": res["cell_area_mean"],
            "cell_area_median": res["cell_area_median"],
            "score_mean": res["score_mean"],
            "score_min": res["score_min"],
            "image_shape": res["image_shape"],
            "scratch_yonu": scratch_yonu,
            "pixel_mm": pixel_mm,
            "device": str(pred.device),
            "input_image_base64": _jpg64(girdi_rgb),
        }

        # Modalite kapisi YOK (karar 0.3) — bos/yanlis goruntu bu yapilandirilmis
        # uyariyla yakalanir; closure/cizimler dejenere olacagi icin uretilmez.
        if res["n_cells"] == 0:
            yanit["closure"] = None
            yanit["uyari"] = ("Hucre tespit edilemedi — goruntuyu ve objektif "
                              "secimini kontrol edin.")
            return yanit

        seg_rgb, overlay_rgb = pred.seg_gorselleri(image_path, res)
        binary = res["_binary"]

        # ROI yaraya DIK: dikey yara -> yatay kusak (vertical_box=False)
        analysis_rgb = draw_analysis(binary, vertical_box=(scratch_yonu == "yatay"))
        closure_rgb = draw_closure(binary, metrics=res.get("closure"),
                                   pixel_mm=pixel_mm)

        yanit.update({
            "closure": res.get("closure"),
            "seg_image_base64": _jpg64(seg_rgb),
            "overlay_image_base64": _jpg64(overlay_rgb),
            "analysis_image_base64": _jpg64(analysis_rgb),
            "closure_image_base64": _jpg64(closure_rgb),
        })
        if scratch_yonu == "yatay":
            yanit["closure_uyari"] = (
                "Closure metrikleri dikey yara varsayimiyla hesaplanir; "
                "yatay yarada yaklasik degerlerdir.")

        if explain:
            # XAI İKİNCİLDİR (kapi-paritesi: zarif düşüş TEK-KAYNAK burada —
            # router da ai_service de aynı davranışı alır): hata analizi DÜŞÜRMEZ.
            try:
                yanit.update(_xai_cpn_bellekte(pred, image_path, method=xai_method))
            except Exception as e:
                _LOG.warning("Scratch XAI üretilemedi (analiz etkilenmedi): %s",
                             e, exc_info=True)
                yanit["xai_error"] = "Açıklama üretilemedi"
        return yanit
    finally:
        _KILIT.release()


GECERLI_XAI_YONTEMLERI = ("eigencam", "gradcam", "gradcam++")


def isit() -> "str | None":
    """Modeli arka planda önceden yükle (soğuk-başlatma UX'i — plan v2 bulgu 12:
    872 MB'lik ilk yükleme istek anına bırakılırsa diğer uçları da bekletir).

    cell/ paketi ya da PT eksikse None döner ve loglar — servis çalışmaya devam eder.
    """
    try:
        with _KILIT:
            if "cpn" not in _PREDICTOR_CACHE:
                _PREDICTOR_CACHE["cpn"] = CellSegmentationPredictor()
            return str(_PREDICTOR_CACHE["cpn"].device)
    except Exception as e:
        _LOG.info("scratch warmup atlandı (model/cell hazır değil): %s", e)
        return None
