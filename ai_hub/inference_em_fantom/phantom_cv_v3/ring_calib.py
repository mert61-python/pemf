# Author: mertaygn, cglrgrkn
"""ring_calib.py — Yesil Helmholtz bobin halkasindan olcek + bobin merkezi (v2).

ArUco bu kurulumda kullanilamiyor (marker kabin disinda, kadraj disi / bobin
arkasinda). Fantomu cevreleyen yesil bobin halkasi ise HER goruntude var:

    1. Yesil maske (H 60-95, S>=60, V>=35) -> bilesenler
    2. Her bilesene elips (cv2.fitEllipse; bant piksellerinin merkez cizgisi)
    3. Fantom merkezini ICEREN ve fantomdan belirgin buyuk elips = bobin halkasi
       (ust bobin / komsu halka elenir); ayni elipse oturan diger parcalar
       (kablo/kol ile bolunmus) eklenip yeniden fit
    4. Elips -> daire afin duzeltme: buyuk eksen boyunca olcek D / (2a),
       kucuk eksen boyunca D / (2b) (egiklik kisaltmasi geri alinir)

Bobin cercevesi (mm): origin = halka merkezi, X = goruntu saga, Y = goruntu
yukari (duzeltilmis duzlemde). Halka capi D varsayilan 184 mm: petri
goruntulerindeki 24'luk plakadan (bilinen 19.3 mm kuyucuk araligi) capraz
kalibrasyonla OLCULDU (3 goruntu 183.5-185.8 mm). Serit metreyle dogrula.
"""
from __future__ import annotations
from dataclasses import dataclass, field

import cv2
import numpy as np


@dataclass
class RingCalib:
    success: bool
    center_px: tuple[float, float] = (0.0, 0.0)
    axes_px: tuple[float, float] = (0.0, 0.0)     # yari eksenler (a >= b)
    angle_deg: float = 0.0                         # buyuk eksen acisi (goruntu)
    diameter_mm: float = 0.0
    mm_per_px: float = 0.0                         # buyuk eksen boyunca
    tilt_deg: float = 0.0                          # arccos(b/a)
    coverage: float = 0.0                          # cevrenin gorunen orani
    residual: float = 0.0                          # |r_norm - 1| medyani
    warnings: list[str] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict:
        return {k: (list(v) if isinstance(v, tuple) else v)
                for k, v in self.__dict__.items()}

    # ---- piksel <-> bobin mm
    def _basis(self):
        t = np.deg2rad(self.angle_deg)
        return np.array([np.cos(t), np.sin(t)]), np.array([-np.sin(t), np.cos(t)])

    def px_to_mm(self, px) -> tuple[float, float]:
        """Piksel -> bobin cercevesi mm (X saga, Y yukari)."""
        e1, e2 = self._basis()
        d = np.asarray(px, dtype=np.float64) - np.asarray(self.center_px)
        R = self.diameter_mm / 2.0
        u = d @ e1 * R / self.axes_px[0]
        v = d @ e2 * R / self.axes_px[1]
        q = u * e1 + v * e2                       # duzeltilmis, goruntu yonunde
        return float(q[0]), float(-q[1])

    def parallax_factor(self, height_mm: float, focal_px: float) -> float:
        """Duzlemin h mm ustundeki nokta Z/(Z-h) kat buyuk gorunur -> (Z-h)/Z.

        Z (kamera-halka duzlemi) = f * R / a ; buyuk eksen kisalmaz.
        """
        if height_mm <= 0 or self.axes_px[0] <= 0:
            return 1.0
        Z = focal_px * (self.diameter_mm / 2.0) / self.axes_px[0]
        return float(max(0.5, (Z - height_mm) / Z))

    def area_px_to_mm2(self, area_px: float) -> float:
        R = self.diameter_mm / 2.0
        return float(area_px * (R / self.axes_px[0]) * (R / self.axes_px[1]))


def green_mask(image_bgr: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
    h, s, v = cv2.split(hsv)
    m = ((h >= 60) & (h <= 95) & (s >= 60) & (v >= 35)).astype(np.uint8) * 255
    return cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))


def _rnorm(pts, ell):
    (cx, cy), (MA, ma), ang = ell
    t = np.deg2rad(ang)
    d = pts - np.array([cx, cy])
    x = d[:, 0] * np.cos(t) + d[:, 1] * np.sin(t)
    y = -d[:, 0] * np.sin(t) + d[:, 1] * np.cos(t)
    return np.sqrt((x / (MA / 2)) ** 2 + (y / (ma / 2)) ** 2), np.arctan2(y / (ma / 2), x / (MA / 2))


def _inside(pt, ell, margin=1.0):
    r, _ = _rnorm(np.asarray([pt], dtype=np.float64), ell)
    return r[0] < margin


def detect_ring(image_bgr: np.ndarray, phantom_center_px, phantom_size_px: float,
                *, diameter_mm: float = 184.0) -> RingCalib:
    h, w = image_bgr.shape[:2]
    gm = green_mask(image_bgr)
    n, lab, st, _ = cv2.connectedComponentsWithStats(gm)
    comps = []
    for i in range(1, n):
        if st[i, cv2.CC_STAT_AREA] < 0.0008 * h * w:
            continue
        ys, xs = np.nonzero(lab == i)
        pts = np.c_[xs, ys].astype(np.float64)
        if len(pts) > 6000:
            pts = pts[np.random.default_rng(0).choice(len(pts), 6000, replace=False)]
        comps.append(pts)
    if not comps:
        return RingCalib(False, diameter_mm=diameter_mm, error="ring_not_found")

    # Halka kablo/kol/fantomla parcalanir; tek parcaya fit kisa yayda yanlis
    # elips verir. Tekil + ikili parca birlesimlerine fit et, TUM yesil
    # piksellerden en cok destek alan (|r-1| < 0.06) makul elipsi sec.
    import itertools
    comps = sorted(comps, key=len, reverse=True)[:7]
    allp = np.vstack(comps)
    trials = [[i] for i in range(len(comps))] + \
             [list(c) for c in itertools.combinations(range(len(comps)), 2)]
    # destek toleransi PIKSEL cinsinden (goreli tolerans buyuk elipsi odullendirir:
    # iki ayri halkaya teget gecen dev elips "destekli" gorunur)
    tol_px = max(5.0, 0.008 * max(h, w))
    best = None
    for idx in trials:
        pts = np.vstack([comps[i] for i in idx])
        if len(pts) < 20:
            continue
        ell = cv2.fitEllipse(pts.astype(np.float32))
        (cx, cy), (MA, ma), ang = ell
        a, b = max(MA, ma) / 2, min(MA, ma) / 2
        if b < 0.4 * phantom_size_px or a > 3.0 * max(h, w):
            continue
        if not _inside(phantom_center_px, ell, 0.9):
            continue
        r, _ = _rnorm(allp, ell)
        support = int((np.abs(r - 1) * b < tol_px).sum())
        if best is None or support > best[0]:
            best = (support, ell)
    if best is None:
        return RingCalib(False, diameter_mm=diameter_mm,
                         error="ring_around_phantom_not_found")

    ell = best[1]
    for _ in range(2):                  # destekleyen parcalarla yeniden fit
        r, _ = _rnorm(allp, ell)
        P = allp[np.abs(r - 1) * min(ell[1]) / 2 < tol_px]
        if len(P) < 20:
            break
        ell = cv2.fitEllipse(P.astype(np.float32))
    (cx, cy), (MA, ma), ang = ell
    r, th = _rnorm(P, ell)
    res = float(np.median(np.abs(r - 1)))
    bins = np.unique(((th + np.pi) / (2 * np.pi) * 36).astype(int) % 36)
    coverage = len(bins) / 36.0

    if MA >= ma:
        a, b, angle = MA / 2, ma / 2, ang
    else:
        a, b, angle = ma / 2, MA / 2, ang + 90.0
    out = RingCalib(True, center_px=(float(cx), float(cy)), axes_px=(float(a), float(b)),
                    angle_deg=float(angle), diameter_mm=diameter_mm,
                    mm_per_px=float(diameter_mm / (2 * a)),
                    tilt_deg=float(np.degrees(np.arccos(np.clip(b / a, 0, 1)))),
                    coverage=round(coverage, 3), residual=round(res, 4))
    if coverage < 0.35:
        # yanlis olcek hic olcekten kotu -> kullanma
        return RingCalib(False, diameter_mm=diameter_mm,
                         coverage=round(coverage, 3), residual=round(res, 4),
                         error=f"ring_partial: halkanin %{coverage * 100:.0f}'i "
                               "gorunur (<%35) - olcek kullanilmadi")
    if coverage < 0.6:
        out.warnings.append(f"ring_partial: halkanin %{coverage * 100:.0f}'i gorunur "
                            "- olcek/merkez belirsizligi artar")
    if out.tilt_deg > 35:
        out.warnings.append(f"ring_oblique: egiklik {out.tilt_deg:.0f} derece - afin "
                            "yaklasim hatasi artar, kamerayi diklestir")
    return out
