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


# ---------------------------------------------------------------- plaka modu
# Cok kuyucuklu plakada mutlak piksel sayisi cozunurluge bagli (30 px yakin
# cekimde %0.3, uzak cekimde %6). Bunun yerine her kuyucuk icin:
#   blue_frac : maske icinde mavi HSV piksel ORANI
#   lab_b     : maske icinde medyan Lab b* (negatif = mavi)
#   delta_b   : lab_b - plaka medyani  (isik degisimine dayanikli, goreli)
# Mavi boya pembe besiyerine karisinca mor gorunebilir -> HSV mavi araligina
# girmez ama b* belirgin duser; o yuzden iki isaret birlikte kullanilir.

@dataclass
class WellColor:
    blue_frac: float
    lab_b: float
    delta_b: float
    is_cancer: bool
    reasons: list


def classify_plate_wells(image_bgr: np.ndarray, cfg: SegmentationCfg,
                         masks: list[np.ndarray], *,
                         well_ids: list[str] | None = None,
                         frac_thr: float = 0.02,
                         db_thr: float = 8.0,
                         db_mad_k: float = 4.0,
                         abs_b_thr: float = -5.0,
                         control_healthy: list[str] | None = None,
                         control_cancer: list[str] | None = None,
                         ) -> tuple[list[WellColor], dict]:
    """Plakadaki her kuyucugu goreli renk olcutleriyle siniflandir.

    Kanser = asagidakilerden HERHANGI biri:
        blue_frac >= frac_thr                       (belirgin mavi leke)
        delta_b   <= -db_lim                        (plakaya gore maviye kayma)
        lab_b     <= abs_b_thr                      (tum plaka boyaliysa da yakala)
    db_lim = max(db_thr, db_mad_k * MAD).

    Kontrol kuyucuklari (v2):
        control_healthy -> b* referansi plaka medyani yerine BU kuyucuklar
                           (plakanin yarisindan fazlasi kanserliyse de dogru kalir)
        control_cancer  -> esikler saglikli ile kanser kontrolun ORTASINA cekilir
                           (her iki yone; sinirli), bu plakanin boya/isigina uyar
        Kontrol yanlis siniflanirsa info["qc"] uyari listesi dolar.

    Returns: (list[WellColor], info)  info = kullanilan esikler + QC
    """
    hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
    b_ch = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2LAB)[..., 2]
    lo, hi = cfg.cancer_blue.as_lower_upper()
    blue = _morphology(cv2.inRange(hsv, lo, hi), 3, 0, 1)
    ids = list(well_ids) if well_ids else [str(i) for i in range(len(masks))]
    ctrl_h = [w for w in (control_healthy or []) if w in ids]
    ctrl_c = [w for w in (control_cancer or []) if w in ids]
    qc = [f"control_unknown_well: {w}" for w in
          (control_healthy or []) + (control_cancer or []) if w not in ids]

    fracs, bs = [], []
    for m in masks:
        sel = m > 0
        n = int(sel.sum())
        if n == 0:
            fracs.append(0.0)
            bs.append(0.0)
            continue
        fracs.append(float((blue[sel] > 0).sum()) / n)
        bs.append(float(np.median(b_ch[sel])) - 128.0)
    F = dict(zip(ids, fracs))
    B = dict(zip(ids, bs))

    ref_ids = ctrl_h if ctrl_h else ids
    ref_b = np.array([B[w] for w in ref_ids], dtype=np.float64)
    med = float(np.median(ref_b)) if len(ref_b) else 0.0
    mad = 1.4826 * float(np.median(np.abs(ref_b - med))) if len(ref_b) else 0.0
    db_lim = max(db_thr, db_mad_k * max(mad, 1.5))

    if ctrl_c:
        # saglikli referans ust siniri vs kanser kontrol alt siniri -> orta nokta
        h_frac = max(F[w] for w in ref_ids) if ctrl_h else float(np.median(fracs))
        c_frac = min(F[w] for w in ctrl_c)
        if c_frac > h_frac:
            frac_thr = float(np.clip((h_frac + c_frac) / 2.0, 0.005, 0.2))
        h_db = min(B[w] - med for w in ref_ids) if ctrl_h else 0.0
        c_db = max(B[w] - med for w in ctrl_c)
        if c_db < h_db:
            db_lim = float(np.clip(-(h_db + c_db) / 2.0, 3.0, 30.0))

    out = []
    for w, f, b in zip(ids, fracs, bs):
        d = b - med
        reasons = []
        if f >= frac_thr:
            reasons.append("blue_frac")
        if d <= -db_lim:
            reasons.append("delta_b")
        if b <= abs_b_thr:
            reasons.append("abs_b")
        out.append(WellColor(blue_frac=round(f, 4), lab_b=round(b, 2),
                             delta_b=round(d, 2), is_cancer=bool(reasons),
                             reasons=reasons))
    res = dict(zip(ids, out))
    for w in ctrl_c:
        if not res[w].is_cancer:
            qc.append(f"control_cancer_missed: {w} (blue={res[w].blue_frac:.3f}, "
                      f"db={res[w].delta_b:+.1f}) - boya cok soluk veya kuyucuk yanlis")
    for w in ctrl_h:
        if res[w].is_cancer:
            qc.append(f"control_healthy_flagged: {w} ({'+'.join(res[w].reasons)})")
    info = {
        "frac_thr": round(frac_thr, 4),
        "delta_b_limit": round(-db_lim, 2),
        "abs_b_thr": abs_b_thr,
        "b_reference": "control_healthy" if ctrl_h else "plate_median",
        "b_median": round(med, 2),
        "b_mad": round(mad, 2),
        "control_healthy": ctrl_h,
        "control_cancer": ctrl_c,
        "calibrated_by_controls": bool(ctrl_c),
        "qc": qc,
    }
    return out, info
