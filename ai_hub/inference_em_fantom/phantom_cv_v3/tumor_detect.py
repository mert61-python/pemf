# Author: mertaygn, cglrgrkn
"""tumor_detect.py — v2 fantom + tumor tespiti (egitimsiz, renk + geometri).

v1 sorunlari (2026-10-02 goruntuleri):
  - Tumor cekirdekleri neredeyse SIYAH (V 7-14) -> cancer_blue V>=40 disinda kaliyor
  - Mor bobin (H~140, a*+17), mavi kablo, etiketler "tumor" saniliyor
  - Fantom bolgesi yanlis (goruntunun yarisi) veya hic bulunamiyor

v2 akisi:
  1. Lacivert hale maskesi: H 98-130, S>=45, V>=20, Lab a* < +12
     (mor bobin a* ~ +17 -> elenir; cyan/yesil H<98 -> elenir)
  2. Hale bilesenleri -> TUMOR KUMESI adaylari; ince/uzun (kablo) elenir,
     icinde siyah cekirdek olan + kompakt olan secilir
  3. Fantom = GrabCut (kesin on plan: tumor kumesi; olasi on plan: kumenin
     cevresi; kesin arka plan: ROI kenari). Renkleri goruntu basina ogrenir
     (sabit "krem" esigi cam yansimasinda calismadi).
  4. Tumorleri ayir: SIKI siyah cekirdekler (V<35, S<90). Cekirdek az ise
     ya da bir cekirdek birden fazla tumoru kapsiyorsa -> uzaklik-donusumu
     tepeleri. Her tumor pikseli en yakin tohuma atanir (Voronoi).
"""
from __future__ import annotations
from dataclasses import dataclass, field

import cv2
import numpy as np

from .color_segment import PhantomDetection, Region, TUMOR, HEALTHY


@dataclass
class TumorDetectCfg:
    navy_h: tuple[int, int] = (98, 130)
    navy_s_min: int = 45
    navy_v_min: int = 20
    navy_a_max: int = 12           # Lab a* (isaretli); mor bobin ~ +17
    core_v_max: int = 35           # siyah cekirdek
    core_s_max: int = 90
    min_cluster_frac: float = 0.0001   # kume alani / goruntu alani
    peak_rel: float = 0.45         # DT tepe esigi (max'a gore)
    peak_sep: float = 0.9          # tepe ayrimi (tipik tumor yaricapi carpani)


@dataclass
class TumorDetectResult:
    success: bool
    phantom: PhantomDetection | None = None
    tumors: list[Region] = field(default_factory=list)
    healthy: list[Region] = field(default_factory=list)
    tumor_cores_px: list[tuple[float, float]] = field(default_factory=list)
    split_method: str = ""         # cores / distance_peaks / cores+peaks
    cluster_score: float = 0.0
    n_cluster_candidates: int = 0
    tumor_radius_px: float = 0.0
    tumor_mask: np.ndarray | None = None   # tum tumor bolgesi (sablon fit icin)
    warnings: list[str] = field(default_factory=list)
    error: str | None = None


def navy_mask(image_bgr: np.ndarray, cfg: TumorDetectCfg) -> np.ndarray:
    hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
    lab = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2LAB)
    h, s, v = cv2.split(hsv)
    a = lab[..., 1].astype(np.int16) - 128
    m = ((h >= cfg.navy_h[0]) & (h <= cfg.navy_h[1]) & (s >= cfg.navy_s_min)
         & (v >= cfg.navy_v_min) & (a < cfg.navy_a_max))
    return m.astype(np.uint8) * 255


def core_mask(image_bgr: np.ndarray, cfg: TumorDetectCfg) -> np.ndarray:
    hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
    m = (hsv[..., 2] < cfg.core_v_max) & (hsv[..., 1] < cfg.core_s_max)
    return m.astype(np.uint8) * 255


def _fill_holes(mask: np.ndarray) -> np.ndarray:
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    out = np.zeros_like(mask)
    cv2.drawContours(out, cnts, -1, 255, -1)
    return out


def _largest(mask: np.ndarray) -> np.ndarray:
    n, lab, st, _ = cv2.connectedComponentsWithStats(mask)
    if n <= 1:
        return np.zeros_like(mask)
    i = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
    return (lab == i).astype(np.uint8) * 255


def _disk(r: float) -> np.ndarray:
    k = max(3, int(round(2 * r)) | 1)
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))


# ---------------------------------------------------------------- 1-2 kume

def _cluster_candidates(navy, dark, cfg):
    """Lacivert bilesenler (+ ici siyah) -> skorlu tumor kumesi adaylari."""
    h, w = navy.shape
    min_area = cfg.min_cluster_frac * h * w
    m = cv2.morphologyEx(navy, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, _disk(0.004 * min(h, w)))
    # halenin cevreledigi siyah cekirdekleri kumeye kat
    m = _fill_holes(m)
    n, lab, st, cen = cv2.connectedComponentsWithStats(m)
    cands = []
    for i in range(1, n):
        a = st[i, cv2.CC_STAT_AREA]
        if a < min_area:
            continue
        comp = (lab == i).astype(np.uint8) * 255
        thick = float(cv2.distanceTransform(comp, cv2.DIST_L2, 5).max())
        rect = cv2.minAreaRect(cv2.findNonZero(comp))
        elong = max(rect[1]) / max(min(rect[1]), 1.0)
        if thick < 2.5 or elong > 6.0:             # kablo / ince serit
            continue
        cnt = max(cv2.findContours(comp, cv2.RETR_EXTERNAL,
                                   cv2.CHAIN_APPROX_SIMPLE)[0], key=cv2.contourArea)
        compact = float(cv2.contourArea(cnt) / max(cv2.contourArea(cv2.convexHull(cnt)), 1))
        core_frac = float((dark[comp > 0] > 0).mean())
        score = a * compact * (1.0 + 4.0 * min(core_frac, 0.4))
        cands.append({"mask": comp, "area": int(a), "thick": thick, "elong": elong,
                      "compact": compact, "core_frac": core_frac,
                      "score": float(score), "centroid": tuple(cen[i])})
    cands.sort(key=lambda c: c["score"], reverse=True)
    return cands


def _merge_cluster(best, cands):
    """En iyi kumeye yakin, cekirdekli diger bilesenleri ekle (ayrik haleler)."""
    mask = best["mask"].copy()
    reach = 0.8 * np.sqrt(best["area"])
    bx, by = best["centroid"]
    for c in cands:
        if c is best or c["core_frac"] < 0.02:
            continue
        cx, cy = c["centroid"]
        if np.hypot(cx - bx, cy - by) < reach + np.sqrt(c["area"]):
            mask |= c["mask"]
    return mask


# ---------------------------------------------------------------- 3 fantom

def _grabcut_phantom(img, cluster):
    h, w = cluster.shape
    ys, xs = np.nonzero(cluster)
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    size = max(x1 - x0, y1 - y0)
    pad = int(1.0 * size)
    rx0, ry0 = max(0, x0 - pad), max(0, y0 - pad)
    rx1, ry1 = min(w, x1 + pad + 1), min(h, y1 + pad + 1)
    roi = img[ry0:ry1, rx0:rx1]
    s = min(1.0, 400.0 / max(roi.shape[:2]))
    roi_s = cv2.resize(roi, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    cl_s = cv2.resize(cluster[ry0:ry1, rx0:rx1], (roi_s.shape[1], roi_s.shape[0]),
                      interpolation=cv2.INTER_NEAREST)
    size_s = size * s
    # Fantom tumor kumesinin disina en fazla ~0.7 x kume boyu tasar (silikon
    # gövde); daha uzagi kesin arka plan -> cam/celik yansimasi fantoma katilmaz.
    gm = np.full(roi_s.shape[:2], cv2.GC_BGD, np.uint8)
    hull = np.zeros_like(cl_s)
    cv2.fillPoly(hull, [cv2.convexHull(cv2.findNonZero(cl_s))], 255)
    gm[cv2.dilate(hull, _disk(0.7 * size_s)) > 0] = cv2.GC_PR_BGD
    gm[cv2.dilate(hull, _disk(0.12 * size_s)) > 0] = cv2.GC_PR_FGD
    gm[cv2.erode(cl_s, np.ones((3, 3), np.uint8)) > 0] = cv2.GC_FGD
    bgd, fgd = np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64)
    try:
        cv2.grabCut(roi_s, gm, None, bgd, fgd, 6, cv2.GC_INIT_WITH_MASK)
    except cv2.error:
        return None
    fg = np.isin(gm, (cv2.GC_FGD, cv2.GC_PR_FGD)).astype(np.uint8) * 255
    fg = cv2.morphologyEx(fg, cv2.MORPH_OPEN, _disk(0.03 * size_s))
    n, lab = cv2.connectedComponents(fg)
    ids = np.unique(lab[(cl_s > 0) & (fg > 0)])
    ids = ids[ids > 0]
    if len(ids) == 0:
        return None
    fg = _fill_holes(np.isin(lab, ids).astype(np.uint8) * 255 | cl_s)
    fg = cv2.morphologyEx(fg, cv2.MORPH_CLOSE, _disk(0.05 * size_s))
    full = np.zeros((h, w), np.uint8)
    full[ry0:ry1, rx0:rx1] = cv2.resize(fg, (rx1 - rx0, ry1 - ry0),
                                        interpolation=cv2.INTER_NEAREST)
    return _largest(full)


def _phantom_detection(mask, n_tumor, score) -> PhantomDetection:
    cnt = max(cv2.findContours(mask, cv2.RETR_EXTERNAL,
                               cv2.CHAIN_APPROX_SIMPLE)[0], key=cv2.contourArea)
    area = int(cv2.countNonZero(mask))
    M = cv2.moments(cnt)
    cx, cy = M["m10"] / M["m00"], M["m01"] / M["m00"]
    x, y, w, h = cv2.boundingRect(cnt)
    hull = cv2.convexHull(cnt)
    solidity = float(cv2.contourArea(cnt) / max(cv2.contourArea(hull), 1.0))
    return PhantomDetection(centroid_px=(float(cx), float(cy)), area_px=area,
                            bbox_px=(x, y, w, h), contour_px=cnt, mask=mask,
                            solidity=round(solidity, 3),
                            aspect_ratio=round(max(w, h) / max(min(w, h), 1), 3),
                            n_blue_inside=n_tumor, score=round(score, 2))


# ---------------------------------------------------------------- 4 tumorler

def _region(mask, organ_id, label) -> Region | None:
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        return None
    cnt = max(cnts, key=cv2.contourArea)
    M = cv2.moments(mask, binaryImage=True)
    if M["m00"] < 1:
        return None
    x, y, w, h = cv2.boundingRect(cnt)
    return Region(organ_id=organ_id, label=label,
                  centroid_px=(M["m10"] / M["m00"], M["m01"] / M["m00"]),
                  area_px=int(cv2.countNonZero(mask)), bbox_px=(x, y, w, h),
                  contour_px=cnt, mask=mask)


def _dt_peaks(tumor_all, cfg):
    """Uzaklik donusumu yerel maksimumlari -> [(x, y, dt)] + tipik yaricap."""
    dt = cv2.distanceTransform(tumor_all, cv2.DIST_L2, 5)
    dmax = float(dt.max())
    if dmax <= 0:
        return [], 0.0
    dts = cv2.GaussianBlur(dt, (0, 0), max(1.0, 0.15 * dmax))
    r_typ = 0.8 * dmax
    loc = (dts >= cv2.dilate(dts, _disk(0.6 * r_typ))) & (dt >= cfg.peak_rel * dmax)
    ys, xs = np.nonzero(loc)
    pk = sorted(((float(x), float(y), float(dt[y, x])) for x, y in zip(xs, ys)),
                key=lambda t: -t[2])
    kept = []
    for x, y, d in pk:              # yakin tepeleri birlestir (yuksek olan kalir)
        if all(np.hypot(x - kx, y - ky) > cfg.peak_sep * r_typ for kx, ky, _ in kept):
            kept.append((x, y, d))
    return kept, r_typ


def _hole_seeds(img, navy_in, tumor_all, r_typ):
    """Lacivert halenin ICINDEKI delikler = tumor cekirdekleri.

    Her tumor: siyah/koyu cekirdek + cevresinde lacivert hale. Hale maskesi
    cekirdegin etrafinda halka cizer; halkanin deligi cekirdektir. Mutlak
    karanliktan bagimsiz (egik/parlak cekimde cekirdek V 60'a cikabiliyor).
    Parlama (glare) deligi: hale'den daha PARLAK -> elenir.
    """
    v = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)[..., 2]
    nc = cv2.morphologyEx(navy_in, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    holes = _fill_holes(nc) & ~nc & tumor_all
    holes = cv2.morphologyEx(holes, cv2.MORPH_OPEN, _disk(max(1.5, 0.08 * r_typ)))
    halo_v = float(np.median(v[navy_in > 0])) if navy_in.any() else 80.0
    min_a = max(9.0, np.pi * (0.2 * r_typ) ** 2)
    n, lab, st, cen = cv2.connectedComponentsWithStats(holes)
    good = []
    for i in range(1, n):
        if st[i, cv2.CC_STAT_AREA] < min_a:
            continue
        hv = float(np.median(v[lab == i]))
        if hv > max(70.0, halo_v + 15.0):           # parlama, cekirdek degil
            continue
        good.append(i)
    if not good:
        return []
    areas = np.array([st[i, cv2.CC_STAT_AREA] for i in good], dtype=np.float64)
    med = float(np.median(areas)) if len(areas) >= 3 else float(areas.min())
    seeds = []
    for i, a in zip(good, areas):
        m = lab == i
        k = 1
        if len(areas) >= 2 and a / med >= 1.8:
            # buyuk delik tek basina yetmez (bazi tumorlerin cekirdegi gercekten
            # buyuk); birlesik iki cekirdek UZUN veya ICBUKEY olur
            cnt = max(cv2.findContours(m.astype(np.uint8), cv2.RETR_EXTERNAL,
                                       cv2.CHAIN_APPROX_SIMPLE)[0], key=cv2.contourArea)
            (_, (rw, rh), _) = cv2.minAreaRect(cnt)
            aspect = max(rw, rh) / max(min(rw, rh), 1.0)
            solidity = cv2.contourArea(cnt) / max(cv2.contourArea(cv2.convexHull(cnt)), 1.0)
            if aspect >= 1.6 or solidity < 0.85:
                k = 3 if a / med >= 2.6 else 2
        if k >= 2:
            # aradaki hale kirik -> iki/uc cekirdek tek delik olmus: k-means ile bol
            k = min(k, 3)
            ys, xs = np.nonzero(m)
            pts = np.float32(np.c_[xs, ys])
            _, lbl, ctr = cv2.kmeans(pts, k, None,
                                     (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_MAX_ITER, 50, 0.5),
                                     5, cv2.KMEANS_PP_CENTERS)
            for j in range(k):
                sub = np.zeros_like(m)
                sel = lbl.ravel() == j
                sub[ys[sel], xs[sel]] = True
                seeds.append((float(ctr[j][0]), float(ctr[j][1]), sub))
        else:
            seeds.append((float(cen[i][0]), float(cen[i][1]), m))
    return seeds


def _relative_blue(img, region, navy):
    """Dusuk cozunurluk: cevresine gore DAHA MAVI ve DAHA KOYU pikseller.

    Uzak/sikistirilmis cekimde tumor ici gri-mavi (S~50, V~60) olur ve sabit
    lacivert esigi sadece kenarlari yakalar. Referans = bolge cevresindeki
    kutunun PARLAK pikselleri (silikon + zemin) -> isik/beyaz dengesinden
    bagimsiz. (Fantom maskesi bu durumda guvenilir degil, referans olamaz.)
    """
    h, w = region.shape
    ys, xs = np.nonzero(region)
    if len(xs) == 0:
        return np.zeros_like(region)
    size = max(xs.max() - xs.min(), ys.max() - ys.min())
    x0, x1 = max(0, xs.min() - size), min(w, xs.max() + size + 1)
    y0, y1 = max(0, ys.min() - size), min(h, ys.max() + size + 1)
    lab = cv2.cvtColor(img[y0:y1, x0:x1], cv2.COLOR_BGR2LAB)
    b = lab[..., 2].astype(np.float32) - 128
    L = lab[..., 0].astype(np.float32)
    bright = L >= np.percentile(L, 60)
    b0, L0 = float(np.median(b[bright])), float(np.median(L[bright]))
    sub = ((b <= b0 - 8) & (L <= 0.75 * L0)).astype(np.uint8) * 255
    sub = cv2.morphologyEx(sub, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    sub = cv2.morphologyEx(sub, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    m = np.zeros_like(region)
    m[y0:y1, x0:x1] = sub
    # sadece mevcut kumeye bagli parca(lar)
    n, lab_ = cv2.connectedComponents(m)
    ids = np.unique(lab_[(cv2.dilate(region, np.ones((5, 5), np.uint8)) > 0) & (m > 0)])
    ids = ids[ids > 0]
    return (np.isin(lab_, ids).astype(np.uint8) * 255) if len(ids) else np.zeros_like(m)


def _log_blob_seeds(img, region, max_n=12):
    """Olcek-normalize LoG ile KOYU lekeler (dusuk cozunurluk tumor merkezleri).

    Tumor cekirdegi uzak cekimde bile halesinden biraz koyudur. Olcek, en guclu
    yanita gore secilir -> fantoma ozgu boyut onbilgisi gerekmez.
    """
    ys, xs = np.nonzero(region)
    if len(xs) < 30:
        return [], 0.0
    size = max(xs.max() - xs.min(), ys.max() - ys.min())
    L = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)[..., 0].astype(np.float32)
    best = None
    for sig in np.geomspace(2.0, max(2.5, size / 5.0), 8):
        g = cv2.GaussianBlur(L, (0, 0), sig)
        resp = (sig ** 2) * cv2.Laplacian(g, cv2.CV_32F, ksize=3)   # koyu leke -> +
        resp[region == 0] = 0
        score = float(np.sort(resp[region > 0])[-max(5, len(xs) // 50):].mean())
        if best is None or score > best[0]:
            best = (score, sig, resp)
    _, sig, resp = best
    r = sig * np.sqrt(2.0)
    loc = (resp >= cv2.dilate(resp, _disk(r))) & (resp > 0.25 * resp.max())
    pts = sorted(((float(x), float(y), float(resp[y, x]))
                  for y, x in zip(*np.nonzero(loc))), key=lambda t: -t[2])
    kept = []
    for x, y, v in pts:
        if all(np.hypot(x - kx, y - ky) > 1.6 * r for kx, ky, _ in kept):
            kept.append((x, y, v))
        if len(kept) >= max_n:
            break
    return kept, r


def _split_tumors(img, phantom, navy, dark, cfg, low_res=False):
    navy_in = navy & phantom
    tumor_all = _fill_holes(cv2.morphologyEx(navy_in, cv2.MORPH_CLOSE,
                                             np.ones((5, 5), np.uint8))) & phantom
    tumor_all = _fill_holes(tumor_all | (dark & cv2.dilate(tumor_all, _disk(3))))
    peaks, r_typ = _dt_peaks(tumor_all, cfg)
    if not peaks:
        return [], [], "none", tumor_all, 0.0
    holes = sorted(_hole_seeds(img, navy_in, tumor_all, r_typ),
                   key=lambda t: -int(t[2].sum()))
    # Tumor yaricapi: >=3 delik varsa komsu delik araliginin yarisi (bitisik
    # tumorler); DT tabanli tahmin birlesik kumede sisiyor.
    if len(holes) >= 3:
        P = np.array([(x, y) for x, y, _ in holes])
        d = np.linalg.norm(P[:, None] - P[None], axis=2)
        np.fill_diagonal(d, np.inf)
        r_typ = float(0.5 * np.median(d.min(axis=1)))

    marker = np.zeros(tumor_all.shape, np.int32)
    seeds_xy, kinds = [], []

    def _add(x, y, mask=None, kind=""):
        # delikler birbirinden zaten ayrik (sadece parlamayla bolunmus cekirdek
        # birlesir); cekirdek/tepe ancak tum tohumlardan ~1 tumor capi uzaktaysa
        # YENI tumordur (kacan tumor)
        sep = 0.5 * r_typ if kind == "hole" else 1.5 * r_typ
        for j, (sx, sy) in enumerate(seeds_xy, 1):
            if np.hypot(x - sx, y - sy) <= sep:          # ayni tumor -> birlestir
                if mask is not None:
                    marker[mask & (marker == 0)] = j
                return
        seeds_xy.append((x, y))
        kinds.append(kind)
        j = len(seeds_xy)
        if mask is not None:
            marker[mask] = j
        else:
            cv2.circle(marker, (int(x), int(y)), max(2, int(0.3 * r_typ)), j, -1)

    # 1) hale delikleri (en guvenilir), buyukten kucuge
    for x, y, m in holes:
        _add(x, y, m, "hole")
    # 2) delik olarak kapanmamis siyah cekirdekler (kenardaki tumor)
    core = cv2.morphologyEx(dark & tumor_all, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n, lab, st, cen = cv2.connectedComponentsWithStats(core)
    min_core = max(9.0, np.pi * (0.25 * r_typ) ** 2)
    for i in sorted(range(1, n), key=lambda i: -st[i, cv2.CC_STAT_AREA]):
        if st[i, cv2.CC_STAT_AREA] >= min_core:
            _add(float(cen[i][0]), float(cen[i][1]), lab == i, "core")
    # 3) cekirdeksiz soluk tumor: DT tepeleri (dusuk cozunurlukte LoG koyu leke)
    if low_res and not holes:
        blobs, r_log = _log_blob_seeds(img, tumor_all)
        if len(blobs) >= 2:
            r_typ = r_log
            for x, y, _ in blobs:
                _add(x, y, None, "log")
    for x, y, _ in peaks:
        _add(x, y, None, "peak")
    used = sorted(set(kinds))
    method = "+".join(used)

    # Voronoi: her tumor pikseli en yakin tohuma
    inv = (marker == 0).astype(np.uint8)
    _, near = cv2.distanceTransformWithLabels(inv, cv2.DIST_L2, 5,
                                              labelType=cv2.DIST_LABEL_PIXEL)
    seed_pix = marker > 0
    lut = np.zeros(int(near.max()) + 1, np.int32)
    lut[near[seed_pix]] = marker[seed_pix]
    owner = lut[near]
    tumors, centers = [], []
    for j in range(1, len(seeds_xy) + 1):
        m = ((owner == j) & (tumor_all > 0)).astype(np.uint8) * 255
        r = _region(m, TUMOR, "tumor")
        if r is None or r.area_px < 0.15 * np.pi * r_typ ** 2:
            continue
        sx, sy = seeds_xy[j - 1]
        r.centroid_px = (float(sx), float(sy))     # tumor merkezi = cekirdek
        tumors.append(r)
        centers.append((float(sx), float(sy)))
    order = np.lexsort(([c[0] for c in centers],
                        [round(c[1] / max(r_typ, 1)) for c in centers]))
    return ([tumors[i] for i in order], [centers[i] for i in order], method,
            tumor_all, r_typ)


def detect_phantom_tumors(image_bgr: np.ndarray,
                          cfg: TumorDetectCfg | None = None) -> TumorDetectResult:
    cfg = cfg or TumorDetectCfg()
    navy = navy_mask(image_bgr, cfg)
    dark = core_mask(image_bgr, cfg)
    cands = _cluster_candidates(navy, dark, cfg)
    if not cands:
        return TumorDetectResult(False, error="tumor_cluster_not_found")
    best = cands[0]
    cluster = _merge_cluster(best, cands)
    warnings = []
    phantom = _grabcut_phantom(image_bgr, cluster)
    if phantom is None or cv2.countNonZero(phantom) < cv2.countNonZero(cluster):
        phantom = _fill_holes(cv2.dilate(cluster, np.ones((9, 9), np.uint8)))
        warnings.append("phantom_grabcut_failed: fantom = tumor kumesi zarfi")
    tumors, centers, method, tumor_all, r_typ = _split_tumors(
        image_bgr, phantom, navy, dark, cfg)
    if r_typ < 8 or "hole" not in method:
        # dusuk cozunurluk: goreli mavi-koyu maske ile kumeyi/fantomu genislet
        rel = _relative_blue(image_bgr, cluster, navy)
        if cv2.countNonZero(rel) > cv2.countNonZero(navy & phantom):
            cluster2 = _largest(cv2.morphologyEx(rel | cluster, cv2.MORPH_CLOSE,
                                                 np.ones((5, 5), np.uint8)))
            ph2 = _grabcut_phantom(image_bgr, cluster2)
            if ph2 is not None:
                phantom = ph2 | cluster2
            navy2 = navy | rel
            tumors, centers, method, tumor_all, r_typ = _split_tumors(
                image_bgr, phantom, navy2, dark, cfg, low_res=True)
            method = "relative_" + method
            warnings.append("low_contrast_fallback: goreli mavi maske kullanildi "
                            "(tumor sayisi/sinirlari dusuk guvenli)")
    if not tumors:
        return TumorDetectResult(False, n_cluster_candidates=len(cands),
                                 error="no_tumor_in_phantom", warnings=warnings)
    ratio = cv2.countNonZero(phantom) / max(cv2.countNonZero(tumor_all), 1)
    if ratio > 6:
        warnings.append(f"phantom_too_large: fantom/tumor alani = {ratio:.1f}")
    if r_typ < 6:
        warnings.append(f"low_resolution: tumor yaricapi ~{r_typ:.0f}px - yaklas")
    healthy_mask = phantom & ~cv2.dilate(tumor_all, np.ones((5, 5), np.uint8))
    healthy = [r for r in [_region(_largest(healthy_mask), HEALTHY, "healthy")] if r]
    ph = _phantom_detection(phantom, len(tumors), best["score"])
    return TumorDetectResult(True, phantom=ph, tumors=tumors, healthy=healthy,
                             tumor_cores_px=centers, split_method=method,
                             cluster_score=best["score"],
                             n_cluster_candidates=len(cands),
                             tumor_radius_px=round(r_typ, 1), tumor_mask=tumor_all,
                             warnings=warnings)
