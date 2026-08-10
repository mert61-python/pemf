# Author: mertaygn, cglrgrkn
"""color_segment.py — Petri kabi ICINDE kanser (mavi) tespit.

NOT: Petri kabi tespiti `petri_detector.py` (YOLO11m-seg) tarafindan yapilir.
     Bu modul SADECE:
       - Mavi kanser noktalari (cancer_blue HSV) → tumor regions
       - YOLO petri mask icinde sinirlandirilir (FP engel)

Kedi (inference_cat_organ) paterniyle uyumlu: YOLO segmentation + HSV
icindeki organ tespiti.
"""
from __future__ import annotations
from dataclasses import dataclass

import cv2
import numpy as np

from .cabin_config import SegmentationCfg


# Bolge tipleri
TUMOR = 1
HEALTHY = 0


@dataclass
class Region:
    organ_id: int
    label: str
    centroid_px: tuple[float, float]
    area_px: int
    bbox_px: tuple[int, int, int, int]
    contour_px: np.ndarray
    mask: np.ndarray


def _morphology(mask, open_k, close_k, iters):
    if open_k > 0:
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (open_k, open_k))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, k, iterations=iters)
    if close_k > 0:
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (close_k, close_k))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k, iterations=iters)
    return mask


def segment_cancer_in_petri(
    image_bgr: np.ndarray,
    cfg: SegmentationCfg,
    petri_mask: np.ndarray,
    *,
    dilate_kernel: int = 15,
) -> list[Region]:
    """YOLO petri mask icinde mavi kanser noktalarini tespit et.

    Args:
        image_bgr: BGR goruntu (H, W, 3)
        cfg: SegmentationCfg (cancer_blue HSV)
        petri_mask: YOLO11m-seg petri mask (H, W) uint8 binary
        dilate_kernel: petri kontur kenarinda olan kanser noktalarini
                       kapsamak icin dilate kernel boyutu

    Returns:
        list[Region] — sadece tumor (organ_id=1) bolgeleri
    """
    hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)

    # Petri mask hafif dilate (kanser noktalari petri kenarinda olabilir)
    if dilate_kernel > 0:
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE,
                                      (dilate_kernel, dilate_kernel))
        roi = cv2.dilate(petri_mask, k, iterations=1)
    else:
        roi = petri_mask.copy()

    # Mavi kanser HSV
    lo, hi = cfg.cancer_blue.as_lower_upper()
    mask_cancer = cv2.inRange(hsv, lo, hi)
    # SADECE petri ROI icinde
    mask_cancer = cv2.bitwise_and(mask_cancer, roi)
    # Open 3 (gurultu) + Close 7 (kenar pikselleri birlestir)
    mask_cancer = _morphology(mask_cancer, 3, 7, 1)

    regions: list[Region] = []
    n, labels, stats, cents = cv2.connectedComponentsWithStats(
        mask_cancer, connectivity=8)
    for i in range(1, n):
        x, y, w, h, a = stats[i]
        if a < 20 or a > 5000:           # min/max kanser nokta boyutu
            continue
        comp = (labels == i).astype(np.uint8) * 255
        contours, _ = cv2.findContours(
            comp, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            continue
        cnt = max(contours, key=cv2.contourArea)
        regions.append(Region(
            organ_id=TUMOR, label="tumor",
            centroid_px=(float(cents[i, 0]), float(cents[i, 1])),
            area_px=int(a),
            bbox_px=(int(x), int(y), int(w), int(h)),
            contour_px=cnt, mask=comp,
        ))
    return regions


def draw_overlay(image_bgr, petri_contour, tumor_regions, *, thickness=2):
    """Petri kontur + kanser kontur cizimi."""
    out = image_bgr.copy()
    if petri_contour is not None:
        cv2.drawContours(out, [petri_contour], -1, (60, 200, 60), thickness)
    for r in tumor_regions:
        cv2.drawContours(out, [r.contour_px], -1, (0, 0, 255), thickness)
        cx, cy = int(r.centroid_px[0]), int(r.centroid_px[1])
        cv2.circle(out, (cx, cy), 4, (0, 0, 255), -1)
        cv2.putText(out, f"T A={r.area_px}", (cx + 8, cy - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1, cv2.LINE_AA)
    return out
