"""color_segment.py — Tersine Algoritma: Mavi Noktalar → Fantom.

Mantik:
    Silikon bobrek fantomu beyaz/krem renkte; arka plan masa da beyaz olabilir.
    AMA fantom'un BENZERSIZ isareti = mavi tumor noktalari.
    Bu yuzden:
        1. Once MAVI NOKTALARI bul (cancer_blue HSV)
        2. Yogunluk haritasi -> en yogun mavi bolge = FANTOM KONUMU
        3. Fantom konumu etrafinda beyaz/krem HSV -> fantom mask
        4. Fantom mask icinde mavi (tumor) + kahverengi (yanik) filtrele

Bolgeler:
    1 = tumor (mavi nokta)
    0 = healthy (silikon bobrek = beyaz silikon)
   -1 = burn  (kahverengi yanik post-PEMF)
"""
from __future__ import annotations
from dataclasses import dataclass

import cv2
import numpy as np

from .cabin_config import SegmentationCfg


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


@dataclass
class PhantomDetection:
    """Tespit edilen silikon bobrek fantomu."""
    centroid_px: tuple[float, float]
    area_px: int
    bbox_px: tuple[int, int, int, int]
    contour_px: np.ndarray
    mask: np.ndarray
    solidity: float
    aspect_ratio: float
    n_blue_inside: int
    score: float


def _morphology(mask, open_k, close_k, iters):
    if open_k > 0:
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (open_k, open_k))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, k, iterations=iters)
    if close_k > 0:
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (close_k, close_k))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k, iterations=iters)
    return mask


def _find_blue_candidates(image_bgr: np.ndarray,
                          cfg: SegmentationCfg
                          ) -> list[tuple[float, float, int]]:
    """Mavi nokta adaylari (cx, cy, area). Pozisyon + boyut filtre."""
    hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
    blue_lo, blue_hi = cfg.cancer_blue.as_lower_upper()
    mask = cv2.inRange(hsv, blue_lo, blue_hi)
    mask = _morphology(mask, 3, 3, 1)
    n, _, stats, cents = cv2.connectedComponentsWithStats(mask, connectivity=8)
    h, w = image_bgr.shape[:2]
    out = []
    for i in range(1, n):
        x, y, bw, bh, a = stats[i]
        if a < 15 or a > 3000:
            continue
        cx, cy = float(cents[i, 0]), float(cents[i, 1])
        # Position filter YOK — fantom yakın çekimde görüntü tamamını kaplar,
        # tümörler her yerde olabilir. (Önceki: cy/h>0.45 lab fotosu içindi.)
        out.append((cx, cy, int(a)))
    return out


def _density_peak(candidates: list[tuple[float, float, int]],
                  image_shape: tuple[int, int],
                  *, sigma: int = 60
                  ) -> tuple[float, float] | None:
    """Mavi adaylarinin yogunluk haritasinda EN YOGUN noktayi bul.

    Her aday merkezi etrafinda Gaussian kernel; toplam yogunluk.
    """
    if not candidates:
        return None
    h, w = image_shape[:2]
    # Hizli: downscale heatmap, sonra peak
    scale = 0.25
    hd, wd = int(h * scale), int(w * scale)
    heat = np.zeros((hd, wd), dtype=np.float32)
    for cx, cy, a in candidates:
        sx, sy = int(cx * scale), int(cy * scale)
        if 0 <= sy < hd and 0 <= sx < wd:
            heat[sy, sx] += float(a)
    sigma_d = max(int(sigma * scale), 3)
    if sigma_d % 2 == 0:
        sigma_d += 1
    heat = cv2.GaussianBlur(heat, (sigma_d * 2 + 1, sigma_d * 2 + 1),
                             sigma_d)
    py, px = np.unravel_index(np.argmax(heat), heat.shape)
    return (float(px / scale), float(py / scale))


def find_phantom(image_bgr: np.ndarray,
                 cfg: SegmentationCfg,
                 *,
                 roi_size_px: int | None = None,
                 ) -> PhantomDetection | None:
    """Sentetik bobrek fantomunu bul (Tersine Algoritma).

    1. Mavi nokta adaylari bul
    2. Yogunluk pik = fantom merkez
    3. Merkez etrafinda 2*roi_size kutu = arama bolgesi
    4. Bu bolgede beyaz/krem HSV ile fantom mask
    5. En buyuk bagli bilesen + convex hull
    """
    h, w = image_bgr.shape[:2]
    # Adaptif: ROI = goruntunun cogu (yakin cekim icin fantom buyuk)
    if roi_size_px is None:
        roi_size_px = max(200, int(min(h, w) * 0.75))
    candidates = _find_blue_candidates(image_bgr, cfg)
    if not candidates:
        return None

    sigma_d = max(20, int(min(h, w) * 0.05))
    peak = _density_peak(candidates, image_bgr.shape, sigma=sigma_d)
    if peak is None:
        return None
    px, py = peak

    # Peak etrafinda ROI kutusu - mavi adaylar siniri ile genislet
    # Adaylarin bbox'i = fantom potansiyel alani
    cs_in_peak = [(cx, cy, a) for (cx, cy, a) in candidates
                  if abs(cx - px) < roi_size_px * 1.5
                  and abs(cy - py) < roi_size_px * 1.5]
    if cs_in_peak:
        xs = [c[0] for c in cs_in_peak]
        ys = [c[1] for c in cs_in_peak]
        margin = 100
        x0 = max(0, int(min(xs) - margin))
        x1 = min(w, int(max(xs) + margin))
        y0 = max(0, int(min(ys) - margin))
        y1 = min(h, int(max(ys) + margin))
    else:
        x0 = max(0, int(px - roi_size_px))
        x1 = min(w, int(px + roi_size_px))
        y0 = max(0, int(py - roi_size_px))
        y1 = min(h, int(py + roi_size_px))

    # ROI icinde beyaz HSV + opening (fantom-masa baglarini kopar)
    roi = image_bgr[y0:y1, x0:x1]
    hsv_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    healthy_lo, healthy_hi = cfg.healthy_white.as_lower_upper()
    roi_mask = cv2.inRange(hsv_roi, healthy_lo, healthy_hi)
    # 5x5 opening: kucuk gurultu temizler, fantom korunur
    k_open = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    roi_mask = cv2.morphologyEx(roi_mask, cv2.MORPH_OPEN, k_open,
                                iterations=1)
    # Closing: fantom icinde mavi nokta delikleri doldur
    k_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
    roi_mask = cv2.morphologyEx(roi_mask, cv2.MORPH_CLOSE, k_close,
                                iterations=2)

    # ROI'de SEED konum (peak ROI'ye gore)
    py_roi = int(py) - y0
    px_roi = int(px) - x0

    # SEED'in bagli oldugu komponent
    n, lbl, stats, cents = cv2.connectedComponentsWithStats(roi_mask,
                                                            connectivity=8)
    if n <= 1:
        return None
    seed_label = lbl[py_roi, px_roi] if (0 <= py_roi < roi_mask.shape[0]
                                          and 0 <= px_roi < roi_mask.shape[1]) else 0
    if seed_label == 0:
        # En yakin beyaz piksel
        ys_w, xs_w = np.where(roi_mask > 0)
        if len(ys_w) == 0:
            return None
        d2 = (ys_w - py_roi) ** 2 + (xs_w - px_roi) ** 2
        idx = int(np.argmin(d2))
        seed_label = int(lbl[ys_w[idx], xs_w[idx]])
        if seed_label == 0:
            return None

    area = int(stats[seed_label, cv2.CC_STAT_AREA])
    # Adaptif min: goruntunun %0.5'i (300x300 icin 450 px, 1200x1600 icin 9600)
    min_area = max(500, int(h * w * 0.005))
    if area < min_area:
        return None
    # Ust sinir: ROI'nin %90'indan buyukse fantom-masa birlesik
    roi_area = roi_mask.shape[0] * roi_mask.shape[1]
    if area > roi_area * 0.90:
        return None

    biggest = int(seed_label)
    comp_roi = (lbl == biggest).astype(np.uint8) * 255

    # Tam goruntu koordinatina cevir + centroid offset
    comp = np.zeros((h, w), dtype=np.uint8)
    comp[y0:y1, x0:x1] = comp_roi
    area = int((comp > 0).sum())
    # Centroid offset (ROI koordinati -> tam goruntu)
    centroid_full = (float(cents[biggest, 0] + x0),
                     float(cents[biggest, 1] + y0))
    contours, _ = cv2.findContours(comp, cv2.RETR_EXTERNAL,
                                    cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    cnt = max(contours, key=cv2.contourArea)
    hull = cv2.convexHull(cnt)
    hull_area = max(cv2.contourArea(hull), 1.0)
    solidity = float(cv2.contourArea(cnt) / hull_area)
    x, y, bw, bh = cv2.boundingRect(cnt)
    aspect = bh / max(bw, 1)

    # Kac mavi nokta fantom icinde
    cnt_blue = sum(1 for (bcx, bcy, _) in candidates
                   if cv2.pointPolygonTest(hull, (bcx, bcy), False) >= 0)

    return PhantomDetection(
        centroid_px=centroid_full,
        area_px=area, bbox_px=(int(x), int(y), int(bw), int(bh)),
        contour_px=cnt, mask=comp,
        solidity=solidity, aspect_ratio=float(aspect),
        n_blue_inside=cnt_blue,
        score=float(cnt_blue * 10 + solidity * 5),
    )


def phantom_from_seed(image_bgr: np.ndarray,
                      cfg: SegmentationCfg,
                      seed_xy: tuple[int, int],
                      *,
                      roi_size_px: int = 250,
                      ) -> PhantomDetection | None:
    """Kullanici tikladi seed -> etrafindaki beyaz fantom mask.

    Algoritma:
        1. Seed konumu etrafinda ROI kutusu
        2. ROI'de beyaz HSV + opening
        3. Seed konumdaki komponent veya en yakin beyaz piksel
        4. Convex hull
    """
    h, w = image_bgr.shape[:2]
    sx, sy = seed_xy

    x0 = max(0, int(sx - roi_size_px))
    x1 = min(w, int(sx + roi_size_px))
    y0 = max(0, int(sy - roi_size_px))
    y1 = min(h, int(sy + roi_size_px))

    roi = image_bgr[y0:y1, x0:x1]
    hsv_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    healthy_lo, healthy_hi = cfg.healthy_white.as_lower_upper()
    roi_mask = cv2.inRange(hsv_roi, healthy_lo, healthy_hi)
    k_open = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    roi_mask = cv2.morphologyEx(roi_mask, cv2.MORPH_OPEN, k_open,
                                iterations=1)
    k_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
    roi_mask = cv2.morphologyEx(roi_mask, cv2.MORPH_CLOSE, k_close,
                                iterations=2)

    sy_roi = sy - y0
    sx_roi = sx - x0
    n, lbl, stats, cents = cv2.connectedComponentsWithStats(roi_mask,
                                                            connectivity=8)
    if n <= 1:
        return None
    seed_label = (lbl[sy_roi, sx_roi]
                  if 0 <= sy_roi < roi_mask.shape[0]
                  and 0 <= sx_roi < roi_mask.shape[1] else 0)
    if seed_label == 0:
        ys_w, xs_w = np.where(roi_mask > 0)
        if len(ys_w) == 0:
            return None
        d2 = (ys_w - sy_roi) ** 2 + (xs_w - sx_roi) ** 2
        idx = int(np.argmin(d2))
        seed_label = int(lbl[ys_w[idx], xs_w[idx]])
        if seed_label == 0:
            return None

    area = int(stats[seed_label, cv2.CC_STAT_AREA])
    if area < 1000:
        return None

    comp_roi = (lbl == seed_label).astype(np.uint8) * 255
    comp = np.zeros((h, w), dtype=np.uint8)
    comp[y0:y1, x0:x1] = comp_roi
    area = int((comp > 0).sum())

    contours, _ = cv2.findContours(comp, cv2.RETR_EXTERNAL,
                                    cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    cnt = max(contours, key=cv2.contourArea)
    hull = cv2.convexHull(cnt)
    hull_area = max(cv2.contourArea(hull), 1.0)
    solidity = float(cv2.contourArea(cnt) / hull_area)
    x, y, bw, bh = cv2.boundingRect(cnt)
    aspect = bh / max(bw, 1)

    # Mavi nokta sayisi fantom icinde
    hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
    blue_lo, blue_hi = cfg.cancer_blue.as_lower_upper()
    blue_mask = cv2.inRange(hsv, blue_lo, blue_hi)
    blue_mask = _morphology(blue_mask, 3, 3, 1)
    inside = cv2.bitwise_and(blue_mask, comp)
    nbc, _, bs, _ = cv2.connectedComponentsWithStats(inside, connectivity=8)
    n_blue = sum(1 for i in range(1, nbc) if bs[i, cv2.CC_STAT_AREA] >= 15)

    cx_full = float(cents[seed_label, 0] + x0)
    cy_full = float(cents[seed_label, 1] + y0)

    return PhantomDetection(
        centroid_px=(cx_full, cy_full),
        area_px=area, bbox_px=(int(x), int(y), int(bw), int(bh)),
        contour_px=cnt, mask=comp,
        solidity=solidity, aspect_ratio=float(aspect),
        n_blue_inside=n_blue,
        score=float(n_blue * 10 + solidity * 5 + 100),    # +100 manuel bonus
    )


def _white_mask_global(image_bgr: np.ndarray,
                       cfg: SegmentationCfg) -> np.ndarray:
    """Tum goruntu uzerinde beyaz HSV mask + temizlik."""
    hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
    lo, hi = cfg.healthy_white.as_lower_upper()
    mask = cv2.inRange(hsv, lo, hi)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, k, iterations=1)
    k2 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k2, iterations=2)
    return mask


def _split_by_watershed(
    image_bgr: np.ndarray,
    white_mask: np.ndarray,
    *, peak_thresh_ratio: float = 0.4,
) -> list[np.ndarray]:
    """Watershed ile birlesik beyaz mask'i ayrik fantomlara bol.

    Algoritma:
        1. Distance transform on white_mask
        2. Peak threshold (dist > ratio * max_dist) -> sure_fg
        3. Mask dilate -> sure_bg
        4. unknown = bg - fg
        5. cv2.watershed -> segmentler

    Returns:
        list of binary masks, her biri ayri fantom
    """
    # Beyaz pikseller yetersizse hicbir sey yapma
    if cv2.countNonZero(white_mask) < 500:
        return []
    # Distance transform
    dist = cv2.distanceTransform(white_mask, cv2.DIST_L2, 5)
    max_d = float(dist.max())
    if max_d < 5:
        # Mask cok ince/dagilmis
        return [white_mask] if cv2.countNonZero(white_mask) > 500 else []
    _, sure_fg = cv2.threshold(dist, peak_thresh_ratio * max_d, 255, 0)
    sure_fg = sure_fg.astype(np.uint8)
    # Sure background (mask kendisi yeterli; biraz dilate)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    sure_bg = cv2.dilate(white_mask, k, iterations=2)
    unknown = cv2.subtract(sure_bg, sure_fg)
    # Marker labelling
    n_marks, markers = cv2.connectedComponents(sure_fg)
    markers = markers + 1                          # background=1
    markers[unknown == 255] = 0                    # unknown=0
    # Watershed
    markers_ws = cv2.watershed(image_bgr, markers.copy())
    # markers_ws: -1 boundary, 1 background, 2+ segmentler
    segments: list[np.ndarray] = []
    for lbl in np.unique(markers_ws):
        if lbl <= 1:
            continue
        seg = (markers_ws == lbl).astype(np.uint8) * 255
        # Hafif dilate (boundary kayıp)
        seg = cv2.dilate(seg, k, iterations=1)
        # Beyaz mask ile AND (sadece beyaz pikseller)
        seg = cv2.bitwise_and(seg, white_mask)
        if cv2.countNonZero(seg) > 500:
            segments.append(seg)
    return segments


def _phantom_from_mask(
    image_bgr: np.ndarray,
    mask: np.ndarray,
    cfg: SegmentationCfg,
    all_blue_candidates: list[tuple[float, float, int]],
) -> PhantomDetection | None:
    """Tek bir bitmap mask'tan PhantomDetection olustur."""
    n, lbl, stats, cents = cv2.connectedComponentsWithStats(mask,
                                                            connectivity=8)
    if n <= 1:
        return None
    biggest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    area = int(stats[biggest, cv2.CC_STAT_AREA])
    if area < 500:
        return None
    comp = (lbl == biggest).astype(np.uint8) * 255
    contours, _ = cv2.findContours(comp, cv2.RETR_EXTERNAL,
                                    cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    cnt = max(contours, key=cv2.contourArea)
    hull = cv2.convexHull(cnt)
    hull_area = max(cv2.contourArea(hull), 1.0)
    solidity = float(cv2.contourArea(cnt) / hull_area)
    x, y, bw, bh = cv2.boundingRect(cnt)
    aspect = bh / max(bw, 1)
    cx, cy = cents[biggest]

    # Mavi nokta sayisi (convex hull icinde)
    n_blue = sum(1 for (bcx, bcy, _) in all_blue_candidates
                 if cv2.pointPolygonTest(hull, (bcx, bcy), False) >= 0)
    return PhantomDetection(
        centroid_px=(float(cx), float(cy)),
        area_px=area, bbox_px=(int(x), int(y), int(bw), int(bh)),
        contour_px=cnt, mask=comp,
        solidity=solidity, aspect_ratio=float(aspect),
        n_blue_inside=n_blue,
        score=float(n_blue * 10 + solidity * 5 + np.log10(max(area, 1)) * 1.5),
    )


def find_phantoms(image_bgr: np.ndarray,
                  cfg: SegmentationCfg,
                  *,
                  max_phantoms: int = 1,
                  ) -> list[PhantomDetection]:
    """Multi-fantom: watershed ile birlesik beyaz mask'i ayrik fantomlara bol.

    Algoritma:
        1. Beyaz HSV mask (global)
        2. Watershed ile ayri segmentlere bol
        3. Her segment icin PhantomDetection olustur
        4. Filtre: en az 1 mavi nokta icermeli (yoksa arka plan)
        5. Skora gore sirala, en iyi max_phantoms al
    """
    candidates = _find_blue_candidates(image_bgr, cfg)
    if not candidates:
        return []

    white_mask = _white_mask_global(image_bgr, cfg)

    # Once watershed dene; eger segment yoksa fallback CC
    segments = _split_by_watershed(image_bgr, white_mask,
                                    peak_thresh_ratio=0.30)
    if not segments:
        # Watershed FAIL -> connectedComponents
        n, lbl, stats, _ = cv2.connectedComponentsWithStats(
            white_mask, connectivity=8)
        segments = []
        for i in range(1, n):
            if stats[i, cv2.CC_STAT_AREA] >= 500:
                segments.append((lbl == i).astype(np.uint8) * 255)

    h, w = image_bgr.shape[:2]
    img_area = h * w
    phantoms: list[PhantomDetection] = []
    for seg in segments:
        ph = _phantom_from_mask(image_bgr, seg, cfg, candidates)
        if ph is None:
            continue
        # SIKI kabul kriteri (FP engelle):
        # mavi nokta SART (yoksa fantom degil — arka plan)
        # + minimum area + solidity
        if ph.n_blue_inside < 1:
            continue
        if ph.area_px < img_area * 0.01:    # %1'den kucuk = gurultu
            continue
        if ph.solidity < 0.40:               # parcali sekiller = arka plan
            continue
        phantoms.append(ph)

    # En yuksek skorlu segment = tek fantom
    phantoms.sort(key=lambda p: p.score, reverse=True)
    return phantoms[:max_phantoms]


def segment_phantom(image_bgr: np.ndarray,
                    cfg: SegmentationCfg,
                    *,
                    phantom: PhantomDetection | None = None
                    ) -> dict:
    """Fantom mask icinde 3-renk segmentasyon."""
    if phantom is None:
        phantom = find_phantom(image_bgr, cfg)
    if phantom is None:
        return {"phantom": None, "tumor": [], "healthy": [], "burn": []}

    hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)

    # ROI = convex hull (mavi delikler dolu) + ORTA dilate
    # Tumor SADECE fantom icinde — disinda olamaz (kullanici talebi)
    hull = cv2.convexHull(phantom.contour_px)
    phantom_roi = np.zeros_like(phantom.mask)
    cv2.drawContours(phantom_roi, [hull], -1, 255, cv2.FILLED)
    # Hafif dilate: fantom kenarinda olan tumor noktalarini kapsa (cok degil)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
    phantom_roi = cv2.dilate(phantom_roi, k, iterations=1)

    # Tumor (sadece fantom ROI icinde) — opening + closing (FP engelle)
    tumor_lo, tumor_hi = cfg.cancer_blue.as_lower_upper()
    mask_tumor = cv2.inRange(hsv, tumor_lo, tumor_hi)
    mask_tumor = cv2.bitwise_and(mask_tumor, phantom_roi)
    # Opening 3x3 kucuk gurultu temizler
    # Closing 7x7 kenarda kopuk parcalari birlestirir (S sinirinda)
    mask_tumor = _morphology(mask_tumor, 3, 7, 1)

    def comps(m, oid, lbl, min_a, max_a):
        out = []
        nn, ll, st, ct = cv2.connectedComponentsWithStats(m, connectivity=8)
        for i in range(1, nn):
            x, y, w, h, a = st[i]
            if a < min_a or a > max_a:
                continue
            cm = (ll == i).astype(np.uint8) * 255
            cnts, _ = cv2.findContours(cm, cv2.RETR_EXTERNAL,
                                        cv2.CHAIN_APPROX_SIMPLE)
            if not cnts:
                continue
            c = max(cnts, key=cv2.contourArea)
            out.append(Region(
                organ_id=oid, label=lbl,
                centroid_px=(float(ct[i, 0]), float(ct[i, 1])),
                area_px=int(a),
                bbox_px=(int(x), int(y), int(w), int(h)),
                contour_px=c, mask=cm,
            ))
        return out

    tumors = comps(mask_tumor, TUMOR, "tumor", 20, 5000)
    healthys = [Region(
        organ_id=HEALTHY, label="healthy",
        centroid_px=phantom.centroid_px,
        area_px=phantom.area_px,
        bbox_px=phantom.bbox_px,
        contour_px=phantom.contour_px,
        mask=phantom.mask,
    )]
    return {"phantom": phantom, "tumor": tumors, "healthy": healthys}


def segment_phantoms_multi(image_bgr: np.ndarray,
                           cfg: SegmentationCfg,
                           *,
                           max_phantoms: int = 3,
                           ) -> dict:
    """Multi-fantom: 1-N fantom + her birinde tumor ara."""
    phantoms = find_phantoms(image_bgr, cfg, max_phantoms=max_phantoms)
    if not phantoms:
        return {"phantoms": [], "tumor": [], "healthy": []}
    all_tumors: list[Region] = []
    all_healthy: list[Region] = []
    for ph in phantoms:
        segs = segment_phantom(image_bgr, cfg, phantom=ph)
        all_tumors.extend(segs["tumor"])
        all_healthy.extend(segs["healthy"])
    return {"phantoms": phantoms, "tumor": all_tumors, "healthy": all_healthy}


def draw_overlay(image_bgr, result, *, thickness=2):
    out = image_bgr.copy()
    colors = {TUMOR: (0, 0, 255), HEALTHY: (0, 255, 0)}
    labels = {TUMOR: "TUMOR", HEALTHY: "FANTOM"}
    regs = (result.get("tumor", []) + result.get("healthy", [])
            ) if isinstance(result, dict) else result
    for r in regs:
        col = colors.get(r.organ_id, (200, 200, 200))
        cv2.drawContours(out, [r.contour_px], -1, col, thickness)
        cx, cy = int(r.centroid_px[0]), int(r.centroid_px[1])
        cv2.circle(out, (cx, cy), 4, col, -1)
        cv2.putText(out, f"{labels.get(r.organ_id, '?')} A={r.area_px}",
                    (cx + 8, cy - 8), cv2.FONT_HERSHEY_SIMPLEX,
                    0.5, col, 1, cv2.LINE_AA)
    return out
