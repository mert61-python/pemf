# Author: mertaygn, cglrgrkn
"""plate_grid.py — Cok kuyucuklu plaka (24/12/48/96) icin izgara tabanli kuyucuk tespiti.

YOLO modeli tekil petri kaplariyla egitildi; 24'luk plakadaki kucuk kuyucuklari
tutarsiz buluyor ve bobin halkalarini da "petri" saniyor. Yeniden egitim yapmadan
cozum: kuyucuklarin yerini plakanin BILINEN geometrisi belirlesin, YOLO sadece ipucu.

Akis:
    1. Pembe besiyeri HSV maskesi -> en buyuk kume = plaka bolgesi
       (bobin, zemin, kabin kosesi gibi her sey burada elenir)
    2. Plaka dortgeni -> ideal ROWS x COLS izgaraya ilk homografi
    3. Aday kuyucuklar: YOLO (plaka kirpilip buyutulerek) + HoughCircles
       -> en yakin izgara noktasina esle -> RANSAC homografi
    4. ECC: sentetik kuyucuk sablonu <-> pembe maske (tum pikseller) ince ayar
    5. Her kuyucuk: homografiden perspektif-dogru daire maske (yaricap %80)

Plaka cercevesi (mm): A1 merkezi = (0, 0), x = sutun yonu (1..COLS),
y = satir yonu (A..). A1'in goruntu kosesi `a1_corner` ile
verilir (auto: yatayda sol-ust, dikeyde sag-ust); aynalama imkansiz kilinir.
"""
from __future__ import annotations
from dataclasses import dataclass, field

import cv2
import numpy as np

from .petri_detector import PetriDetection


@dataclass(frozen=True)
class PlateSpec:
    """SBS/ANSI standart plaka geometrisi (mm)."""
    rows: int
    cols: int
    pitch_mm: float          # kuyucuk merkezleri arasi
    well_diam_mm: float      # kuyucuk ic capi (ust)


PLATE_SPECS: dict[int, PlateSpec] = {
    12: PlateSpec(3, 4, 26.0, 22.1),
    24: PlateSpec(4, 6, 19.3, 15.6),
    48: PlateSpec(6, 8, 13.0, 10.9),
    96: PlateSpec(8, 12, 9.0, 6.9),
}

ROW_LETTERS = "ABCDEFGH"


@dataclass
class PlateGridResult:
    success: bool
    spec: PlateSpec | None = None
    H_img_from_plate: np.ndarray | None = None     # 3x3, plaka mm -> piksel
    well_ids: list[str] = field(default_factory=list)
    wells_plate_mm: list[tuple[float, float]] = field(default_factory=list)
    detections: list[PetriDetection] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)     # yolo / hough / grid
    plate_quad_px: list[list[float]] = field(default_factory=list)
    mm_per_px: float = 0.0
    n_candidates: int = 0
    n_yolo_candidates: int = 0
    n_inliers: int = 0                                   # aday ile dogrulanan kuyucuk
    fit_rms_mm: float = float("nan")
    ecc_ok: bool = False
    well_radius_px: float = 0.0
    chosen: str = ""                                     # secilen hipotez
    orientation: str = ""                                # landscape / portrait
    a1_corner: str = ""                                  # A1'in goruntu kosesi
    fit_score: float = 0.0                               # sivi ici - arasi
    hypotheses: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)    # cekim kalitesi
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "plate_type": (self.spec.rows * self.spec.cols) if self.spec else None,
            "rows": self.spec.rows if self.spec else None,
            "cols": self.spec.cols if self.spec else None,
            "pitch_mm": self.spec.pitch_mm if self.spec else None,
            "H_img_from_plate": (self.H_img_from_plate.tolist()
                                 if self.H_img_from_plate is not None else None),
            "plate_quad_px": self.plate_quad_px,
            "n_candidates": self.n_candidates,
            "n_yolo_candidates": self.n_yolo_candidates,
            "n_inliers": self.n_inliers,
            "fit_rms_mm": self.fit_rms_mm,
            "ecc_ok": self.ecc_ok,
            "well_radius_px": self.well_radius_px,
            "chosen": self.chosen,
            "orientation": self.orientation,
            "a1_corner": self.a1_corner,
            "fit_score": self.fit_score,
            "hypotheses": self.hypotheses,
            "warnings": self.warnings,
            "error": self.error,
        }


# ---------------------------------------------------------------- yardimcilar

def _project(H: np.ndarray, pts: np.ndarray) -> np.ndarray:
    pts = np.asarray(pts, dtype=np.float64).reshape(-1, 1, 2)
    return cv2.perspectiveTransform(pts, H).reshape(-1, 2)


def _ideal_centers(spec: PlateSpec) -> np.ndarray:
    """(rows*cols, 2) plaka mm; sira: A1, A2, ..., B1, ..."""
    return np.array([[c * spec.pitch_mm, r * spec.pitch_mm]
                     for r in range(spec.rows) for c in range(spec.cols)],
                    dtype=np.float64)


def pink_mask(image_bgr: np.ndarray) -> np.ndarray:
    """Pembe/magenta besiyeri (fenol kirmizisi) maskesi."""
    hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
    h, s, v = cv2.split(hsv)
    m = ((h >= 140) | (h <= 6)) & (s >= 35) & (v >= 90)
    return m.astype(np.uint8) * 255


def medium_mask(image_bgr: np.ndarray) -> np.ndarray:
    """Kuyucuktaki sivi: pembe besiyeri VEYA mavi/mor boya.

    Boyali (kanser) kuyucuk pembeligini kaybeder; sadece pembe maske kullanilirsa
    izgara o kuyucuklardan kacar. Yesil bobin (H~60-90) disarida kalir.
    """
    hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
    h, s, v = cv2.split(hsv)
    dye = (h >= 95) & (h < 140) & (s >= 45) & (v >= 40)
    return cv2.bitwise_or(pink_mask(image_bgr), dye.astype(np.uint8) * 255)


def _order_quad(pts: np.ndarray) -> np.ndarray:
    """4 nokta -> TL, TR, BR, BL (saat yonu)."""
    pts = np.asarray(pts, dtype=np.float64).reshape(4, 2)
    c = pts.mean(axis=0)
    ang = np.arctan2(pts[:, 1] - c[1], pts[:, 0] - c[0])
    pts = pts[np.argsort(ang)]                 # saat yonu (y asagi)
    tl = int(np.argmin(pts.sum(axis=1)))
    return np.roll(pts, -tl, axis=0)


def _find_plate_quad(mask: np.ndarray):
    """Pembe maskeden -> (dortgen, plaka bolge maskesi, minAreaRect kosesi) | None."""
    h, w = mask.shape[:2]
    k = max(5, int(round(min(h, w) * 0.02)) | 1)
    m = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE,
                         cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(m)
    if n <= 1:
        return None
    idx = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    if stats[idx, cv2.CC_STAT_AREA] < 0.002 * h * w:
        return None
    region = (lab == idx).astype(np.uint8) * 255
    # 2. gecis: kernel plaka boyutuna gore -> cam yansimasi plakaya yapismasin
    k2 = max(3, int(round(0.025 * np.sqrt(stats[idx, cv2.CC_STAT_AREA]))) | 1)
    if k2 < k:
        m2 = cv2.morphologyEx(cv2.bitwise_and(mask, region), cv2.MORPH_CLOSE,
                              cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k2, k2)))
        n2, lab2, st2, _ = cv2.connectedComponentsWithStats(m2)
        if n2 > 1:
            i2 = 1 + int(np.argmax(st2[1:, cv2.CC_STAT_AREA]))
            region = (lab2 == i2).astype(np.uint8) * 255
    cnts, _ = cv2.findContours(region, cv2.RETR_EXTERNAL,
                               cv2.CHAIN_APPROX_SIMPLE)
    hull = cv2.convexHull(max(cnts, key=cv2.contourArea))
    peri = cv2.arcLength(hull, True)
    quad = None
    for eps in (0.02, 0.03, 0.04, 0.06):
        approx = cv2.approxPolyDP(hull, eps * peri, True)
        if len(approx) == 4:
            quad = approx.reshape(4, 2)
            break
    rect = _order_quad(cv2.boxPoints(cv2.minAreaRect(hull)))
    if quad is None:
        quad = rect
    return _order_quad(quad), region, rect


# A1'in goruntudeki kosesi -> goruntu koseleri (TL,TR,BR,BL) ile plaka koseleri
# arasindaki dongusel kayma. Plaka USTTEN bakildiginda sadece donebilir, aynalanamaz:
#   yatay plaka : A1 = tl (normal) veya br (180 derece)
#   dikey plaka : A1 = tr (90 saat yonu) veya bl (90 saat tersi)
# (v1 dikey plakada A1'i sol-uste koyuyordu -> etiketler AYNALIYDI.)
A1_SHIFT = {"tl": 0, "bl": 1, "br": 2, "tr": 3}
A1_ALLOWED = {True: ("tl", "br"), False: ("tr", "bl")}     # landscape -> izinli


def quad_is_landscape(quad: np.ndarray) -> bool:
    tl, tr, br, bl = quad
    return bool(np.linalg.norm(tr - tl) + np.linalg.norm(br - bl)
                >= np.linalg.norm(bl - tl) + np.linalg.norm(br - tr))


def resolve_a1_corner(landscape: bool, a1_corner: str = "auto"
                      ) -> tuple[str, str | None]:
    """-> (kullanilacak kose, uyari | None)."""
    allowed = A1_ALLOWED[landscape]
    if a1_corner in (None, "", "auto"):
        return allowed[0], None
    a1_corner = a1_corner.lower()
    if a1_corner in allowed:
        return a1_corner, None
    return allowed[0], (f"a1_corner_invalid: '{a1_corner}' "
                        f"{'yatay' if landscape else 'dikey'} plakada mumkun degil "
                        f"(aynalama); izinli: {'/'.join(allowed)} -> {allowed[0]} kullanildi")


def plate_corners_for_image(spec: PlateSpec, a1: str, pad: float) -> list:
    """Goruntu koseleri TL,TR,BR,BL sirasina karsilik gelen plaka (mm) koseleri.

    pad: kuyucuk merkezlerinden disari pay (0 = kose kuyucuk merkezleri).
    """
    xm = (spec.cols - 1) * spec.pitch_mm + pad
    ym = (spec.rows - 1) * spec.pitch_mm + pad
    P = [(-pad, -pad), (xm, -pad), (xm, ym), (-pad, ym)]   # A1 kosesinden saat yonu
    k = A1_SHIFT[a1]
    return [P[(i + k) % 4] for i in range(4)]


def _initial_homography(quad: np.ndarray, spec: PlateSpec,
                        affine: bool = False, a1: str = "tl") -> np.ndarray:
    """Pembe bolge dortgeni = kuyucuklarin dis zarfi -> ideal izgara."""
    dst = plate_corners_for_image(spec, a1, spec.well_diam_mm / 2.0)
    if affine:
        A = cv2.getAffineTransform(np.float32(dst[:3]), np.float32(quad[:3]))
        return np.vstack([A, [0, 0, 1]]).astype(np.float64)
    H, _ = cv2.findHomography(np.array(dst, np.float64), quad.astype(np.float64))
    return H


def _local_px_per_mm(H: np.ndarray, pt_mm: tuple[float, float]) -> float:
    p = np.array([pt_mm, (pt_mm[0] + 1, pt_mm[1]), (pt_mm[0], pt_mm[1] + 1)])
    q = _project(H, p)
    return float(np.sqrt(abs(np.cross(q[1] - q[0], q[2] - q[0]))))


# ---------------------------------------------------------------- adaylar

def aday_imgsz(yolo, istenen: int = 1280) -> int:
    """YOLO aday kirpintisinin boyutu. AI-2 (guii uyarlamasi, olculdu 2026-10-12):

    guii YALNIZ ONNX sevk eder ve ONNX 640x640 SABIT disa aktarilmistir; hocanin 1280'i ONNX Runtime'da
    `INVALID_ARGUMENT ... Got: 1280 Expected: 640` verir (kahin: 6/6 petri goruntusu COKTU). ONNX modelde aday
    boyutu dedektorun SABIT girisine (`yolo.imgsz`) cekilir. Olculen bedel: YOLO adayi 4-25 -> 0-4 (hocanin PT'si
    @640 ile ayni -> fark BICIMDEN degil boyuttan); kuyucuk sayisi / kimlik / etiket DEGISMEZ, konum <= 1,62 px
    (6/6 x 24, 144/144 < 0,25 aralik). Aday sayisi GIZLENMEZ: `n_yolo_candidates` + kuyucuk basina `source`."""
    yol = str(getattr(yolo, "model_path", "") or "")
    if yol.lower().endswith(".onnx"):
        return int(getattr(yolo, "imgsz", 640) or 640)
    return int(istenen)


def _yolo_candidates(image_bgr, roi, yolo, exp_r_px, *, conf=0.15,
                     imgsz=1280) -> list[tuple[float, float, float, float]]:
    """Plaka bolgesini kirp + buyut + YOLO. -> [(cx, cy, r, conf)] piksel."""
    if yolo is None:
        return []
    imgsz = aday_imgsz(yolo, imgsz)
    x0, y0, x1, y1 = roi
    crop = image_bgr[y0:y1, x0:x1]
    if crop.size == 0:
        return []
    s = imgsz / max(crop.shape[:2])
    crop_s = cv2.resize(crop, None, fx=s, fy=s,
                        interpolation=cv2.INTER_CUBIC if s > 1 else cv2.INTER_AREA)
    model = yolo._ensure_model()
    res = model.predict(source=crop_s, conf=conf, iou=yolo.iou, imgsz=imgsz,
                        device=yolo.device, verbose=False)
    out = []
    for r in res:
        if r.boxes is None:
            continue
        for b in r.boxes:
            bx1, by1, bx2, by2 = (v / s for v in b.xyxy[0].tolist())
            rad = (bx2 - bx1 + by2 - by1) / 4.0
            if not (0.55 * exp_r_px <= rad <= 1.6 * exp_r_px):
                continue
            out.append((x0 + (bx1 + bx2) / 2, y0 + (by1 + by2) / 2, rad,
                        float(b.conf[0])))
    return out


def _hough_candidates(image_bgr, roi, exp_r_px, pitch_px):
    x0, y0, x1, y1 = roi
    gray = cv2.cvtColor(image_bgr[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY)
    if gray.size == 0:
        return []
    # Hough kucuk kuyucukta zayif -> en az ~40 px yaricapa buyut
    s = max(1.0, 40.0 / max(exp_r_px, 1.0))
    if s > 1:
        gray = cv2.resize(gray, None, fx=s, fy=s, interpolation=cv2.INTER_CUBIC)
    gray = cv2.medianBlur(gray, 5)
    circles = cv2.HoughCircles(
        gray, cv2.HOUGH_GRADIENT, dp=1.2, minDist=0.7 * pitch_px * s,
        param1=100, param2=30,
        minRadius=int(0.75 * exp_r_px * s), maxRadius=int(1.35 * exp_r_px * s))
    if circles is None:
        return []
    return [(x0 + c[0] / s, y0 + c[1] / s, c[2] / s, 0.0) for c in circles[0]]


def _ransac_refine(H, spec, cands, pitch_px):
    """Adaylari izgara noktalarina esle, RANSAC homografi. -> H, n_inl, rms_mm, src"""
    ideal = _ideal_centers(spec)
    best = (H, 0, float("nan"), {})
    if len(cands) < 4:
        return best
    C = np.array([c[:2] for c in cands], dtype=np.float64)
    for gate in (0.5, 0.35, 0.25):
        pred = _project(H, ideal)
        d = np.linalg.norm(C[:, None, :] - pred[None, :, :], axis=2)
        # her izgara noktasi icin en yakin aday (tekil eslesme)
        pairs = []
        for j in range(len(ideal)):
            i = int(np.argmin(d[:, j]))
            if d[i, j] < gate * pitch_px and int(np.argmin(d[i, :])) == j:
                pairs.append((j, i))
        if len(pairs) < 6:
            break
        src = ideal[[j for j, _ in pairs]]
        dst = C[[i for _, i in pairs]]
        Hn, inl = cv2.findHomography(src, dst, cv2.RANSAC,
                                     0.15 * pitch_px, maxIters=2000)
        if Hn is None:
            break
        inl = inl.ravel().astype(bool)
        if inl.sum() < 6:
            break
        # rms (mm): inlier tahmini - aday, plaka cercevesinde
        back = _project(np.linalg.inv(Hn), dst[inl])
        rms = float(np.sqrt(np.mean(np.sum((back - src[inl]) ** 2, axis=1))))
        H = Hn
        pitch_px = spec.pitch_mm * _local_px_per_mm(H, tuple(ideal.mean(axis=0)))
        srcmap = {}
        for (j, i), ok in zip(pairs, inl):
            if ok:
                srcmap[j] = cands[i]
        best = (H, int(inl.sum()), rms, srcmap)
    return best


def _ecc_refine(H, spec, region_mask, pink, roi) -> tuple[np.ndarray, bool]:
    """Sentetik kuyucuk sablonu ile pembe maskeyi hizala (MOTION_HOMOGRAPHY)."""
    x0, y0, x1, y1 = roi
    target = pink[y0:y1, x0:x1].astype(np.float32) / 255.0
    if target.size == 0:
        return H, False
    a = min(1.0, 700.0 / max(target.shape))
    if a < 1:
        target = cv2.resize(target, None, fx=a, fy=a, interpolation=cv2.INTER_AREA)
    A = np.array([[a, 0, -a * x0], [0, a, -a * y0], [0, 0, 1]], np.float64)

    ppm = _local_px_per_mm(A @ H, (0.0, 0.0))     # sablon ~ hedef olcek
    ppm = float(np.clip(ppm, 1.0, 8.0))
    margin = spec.pitch_mm * 0.75
    Tm = np.array([[ppm, 0, ppm * margin], [0, ppm, ppm * margin], [0, 0, 1]])
    tw = int(ppm * ((spec.cols - 1) * spec.pitch_mm + 2 * margin))
    th = int(ppm * ((spec.rows - 1) * spec.pitch_mm + 2 * margin))
    templ = np.zeros((th, tw), np.float32)
    rad = int(round(ppm * spec.well_diam_mm / 2.0 * 0.9))
    for cx, cy in _ideal_centers(spec):
        cv2.circle(templ, (int(round(ppm * (cx + margin))),
                           int(round(ppm * (cy + margin)))), rad, 1.0, -1)
    sig = max(1.0, 0.12 * rad)
    templ = cv2.GaussianBlur(templ, (0, 0), sig)
    target = cv2.GaussianBlur(target, (0, 0), sig)

    W = A @ H @ np.linalg.inv(Tm)
    W = (W / W[2, 2]).astype(np.float32)
    crit = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 200, 1e-6)
    try:
        if abs(W[2, 0]) < 1e-9 and abs(W[2, 1]) < 1e-9:     # affine baslangic
            _, Wa = cv2.findTransformECC(templ, target, W[:2].copy(),
                                         cv2.MOTION_AFFINE, crit, None, 5)
            W = np.vstack([Wa, [0, 0, 1]]).astype(np.float32)
        _, W = cv2.findTransformECC(templ, target, W, cv2.MOTION_HOMOGRAPHY,
                                    crit, None, 5)
    except cv2.error:
        return H, False
    Hn = np.linalg.inv(A) @ W.astype(np.float64) @ Tm
    Hn /= Hn[2, 2]
    # akil kontrolu: izgara merkezi ve olcek cok kaymamali
    c = _ideal_centers(spec).mean(axis=0)
    s0, s1 = _local_px_per_mm(H, tuple(c)), _local_px_per_mm(Hn, tuple(c))
    shift = np.linalg.norm(_project(Hn, c[None]) - _project(H, c[None]))
    if not (0.8 < s1 / s0 < 1.25) or shift > 0.5 * spec.pitch_mm * s0:
        return H, False
    return Hn, True


def _grid_score(H, spec, liquid, roi) -> float:
    """Izgara uyumu: kuyucuk ici sivi orani - kuyucuklar arasi sivi orani."""
    x0, y0, x1, y1 = roi
    a = min(1.0, 500.0 / max(x1 - x0, y1 - y0, 1))
    A = np.array([[a, 0, -a * x0], [0, a, -a * y0], [0, 0, 1]], np.float64)
    Hs = A @ H
    sh = (int((y1 - y0) * a) + 1, int((x1 - x0) * a) + 1)
    liq = cv2.resize(liquid[y0:y1, x0:x1], (sh[1], sh[0]),
                     interpolation=cv2.INTER_AREA) > 127
    ang = np.linspace(0, 2 * np.pi, 32, endpoint=False)
    r = spec.well_diam_mm / 2.0
    inside = np.zeros(sh, np.uint8)
    outer = np.zeros(sh, np.uint8)
    for cx, cy in _ideal_centers(spec):
        for rad, img in ((0.8 * r, inside), (1.05 * r, outer)):
            ring = np.stack([cx + rad * np.cos(ang), cy + rad * np.sin(ang)], 1)
            cv2.fillPoly(img, [_project(Hs, ring).astype(np.int32)], 1)
    # kuyucuklar arasi bant: izgara zarfi icinde, hicbir kuyucuga ait degil
    hull = np.zeros(sh, np.uint8)
    corners = np.array([[-r, -r], [(spec.cols - 1) * spec.pitch_mm + r, -r],
                        [(spec.cols - 1) * spec.pitch_mm + r,
                         (spec.rows - 1) * spec.pitch_mm + r],
                        [-r, (spec.rows - 1) * spec.pitch_mm + r]])
    cv2.fillPoly(hull, [_project(Hs, corners).astype(np.int32)], 1)
    gap = (hull > 0) & (outer == 0)
    ins = inside > 0
    if ins.sum() == 0:
        return -1.0
    return float(liq[ins].mean() - (liq[gap].mean() if gap.any() else 0.0))


def _plausible(H, spec, region, pitch_px) -> bool:
    """Fiziksel akil kontrolu: izgara plaka bolgesinde ve katlanmamis olmali."""
    ideal = _ideal_centers(spec)
    pts = _project(H, ideal)
    h, w = region.shape[:2]
    # plaka alani = sivi bolgesinin dis bukey zarfi (karanlik/boyali kuyucuk bosluk birakmasin)
    cnts, _ = cv2.findContours(region, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    reg = np.zeros_like(region)
    cv2.fillPoly(reg, [cv2.convexHull(np.vstack(cnts))], 255)
    k = max(3, int(0.3 * pitch_px) | 1)
    reg = cv2.dilate(reg, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    inside = sum(1 for x, y in pts if 0 <= int(y) < h and 0 <= int(x) < w
                 and reg[int(y), int(x)] > 0)
    if inside < 0.9 * len(pts):
        return False
    # katlanma / asiri perspektif: kose Jacobian determinant isareti + olcek orani
    corners = ideal[[0, spec.cols - 1, -spec.cols, -1]]
    dets = []
    for c in corners:
        q = _project(H, np.array([c, c + (1, 0), c + (0, 1)]))
        dets.append(np.cross(q[1] - q[0], q[2] - q[0]))
    dets = np.array(dets)
    if not (np.all(dets > 0) or np.all(dets < 0)):
        return False
    return float(np.abs(dets).max() / np.abs(dets).min()) < 2.5


def _match_sources(H, spec, cands, pitch_px) -> dict:
    """Son H'ye gore her kuyucugu destekleyen aday (yolo/hough) -> {j: cand}."""
    if not cands:
        return {}
    pred = _project(H, _ideal_centers(spec))
    C = np.array([c[:2] for c in cands], dtype=np.float64)
    out = {}
    for j, p in enumerate(pred):
        d = np.linalg.norm(C - p, axis=1)
        close = np.nonzero(d < 0.25 * pitch_px)[0]
        if len(close):
            # YOLO adayi varsa onu tercih et
            yo = [i for i in close if cands[i][3] > 0]
            i = yo[0] if yo else int(close[np.argmin(d[close])])
            out[j] = cands[i]
    return out


# ---------------------------------------------------------------- ana fonksiyon

def detect_plate_wells(image_bgr: np.ndarray, plate_type: int = 24, *,
                       yolo=None, mask_frac: float = 0.8,
                       use_ecc: bool = True,
                       a1_corner: str = "auto") -> PlateGridResult:
    """Goruntudeki cok kuyucuklu plakanin TUM kuyucuklarini dondur.

    Args:
        yolo: PetriYoloDetector (opsiyonel; aday kaynagi olarak kullanilir)
        mask_frac: kuyucuk maskesi yaricapi / kuyucuk yaricapi (kenar yansimasi disarida)
    """
    if plate_type not in PLATE_SPECS:
        return PlateGridResult(False, error=f"unknown_plate_type:{plate_type}")
    spec = PLATE_SPECS[plate_type]
    h, w = image_bgr.shape[:2]

    pink = medium_mask(image_bgr)          # pembe besiyeri + mavi/mor boya
    found = _find_plate_quad(pink)
    if found is None:
        return PlateGridResult(False, spec=spec, error="plate_not_found")
    quad, region, rect = found
    landscape = quad_is_landscape(rect)
    a1, a1_warn = resolve_a1_corner(landscape, a1_corner)
    H = _initial_homography(rect, spec, affine=True, a1=a1)

    # ROI: plaka dortgeni + %15 pay
    qx0, qy0 = quad.min(axis=0)
    qx1, qy1 = quad.max(axis=0)
    mx, my = 0.15 * (qx1 - qx0), 0.15 * (qy1 - qy0)
    roi = (int(max(0, qx0 - mx)), int(max(0, qy0 - my)),
           int(min(w, qx1 + mx)), int(min(h, qy1 + my)))

    center_mm = tuple(_ideal_centers(spec).mean(axis=0))
    ppm = _local_px_per_mm(H, center_mm)
    exp_r = ppm * spec.well_diam_mm / 2.0
    pitch_px = ppm * spec.pitch_mm

    # AI-2: YOLO yalniz IPUCU (hoca). Aday cagrisi duserse (bozuk/uyumsuz model) izgara Hough + ECC ile surer ama
    # SESSIZ kalmaz: `yolo_candidates_failed` uyarisi + `n_yolo_candidates = 0` (makullik kapisi dogrulanmis aday ister).
    yolo_hata = None
    try:
        cands = _yolo_candidates(image_bgr, roi, yolo, exp_r)
    except Exception as e:  # noqa: BLE001 — ipucu kaynagi; neden uyariya yazilir
        cands, yolo_hata = [], f"{type(e).__name__}: {str(e)[:160]}"
    yolo_n = len(cands)
    cands += _hough_candidates(image_bgr, roi, exp_r, pitch_px)
    # sadece plaka bolgesine yakin adaylar
    region_d = cv2.dilate(region, np.ones((int(pitch_px * 0.5) | 1,) * 2, np.uint8))
    cands = [c for i, c in enumerate(cands)
             if 0 <= int(c[1]) < h and 0 <= int(c[0]) < w
             and region_d[int(c[1]), int(c[0])] > 0]

    H0 = H
    H1, n_inl, rms, _ = _ransac_refine(H0, spec, cands, pitch_px)

    # Aday hipotezler; sivi maskesiyle en iyi uyusani sec. Egik uzak cekimde
    # Hough kuyucuk AGZINI da bulur -> RANSAC yanlis satira kayabilir; ECC de
    # kotu baslangictan kotu yere gidebilir. Hicbir ince ayar koru korune kabul edilmez.
    hyps = [("init", H0, False)]
    if n_inl:
        hyps.append(("ransac", H1, False))
    if use_ecc:
        for name, Hb in list((n, Hh) for n, Hh, _ in hyps):
            He, ok = _ecc_refine(Hb, spec, region, pink, roi)
            if ok:
                hyps.append((name + "+ecc", He, True))
    scored = [(_grid_score(Hh, spec, pink, roi), n, Hh, e) for n, Hh, e in hyps
              if n == "init" or _plausible(Hh, spec, region, pitch_px)]
    best_score, chosen, H, ecc_ok = max(scored, key=lambda t: t[0])
    if not chosen.startswith("ransac"):
        rms = float("nan")              # rms sadece RANSAC tabanli hipotezde anlamli
    srcmap = _match_sources(H, spec, cands, pitch_px)

    res = PlateGridResult(True, spec=spec, H_img_from_plate=H,
                          plate_quad_px=quad.tolist(),
                          n_candidates=len(cands), n_inliers=len(srcmap),
                          fit_rms_mm=rms, ecc_ok=ecc_ok)
    res.chosen = chosen
    res.orientation = "landscape" if landscape else "portrait"
    res.a1_corner = a1
    res.fit_score = round(best_score, 3)
    res.hypotheses = {n: round(sc, 3) for sc, n, _, _ in scored}
    res.mm_per_px = 1.0 / _local_px_per_mm(H, center_mm)

    ang = np.linspace(0, 2 * np.pi, 48, endpoint=False)
    rr = spec.well_diam_mm / 2.0 * mask_frac
    ideal = _ideal_centers(spec)
    for j, (cx, cy) in enumerate(ideal):
        r_idx, c_idx = divmod(j, spec.cols)
        ring = np.stack([cx + rr * np.cos(ang), cy + rr * np.sin(ang)], axis=1)
        poly = _project(H, ring).astype(np.int32)
        mask = np.zeros((h, w), np.uint8)
        cv2.fillPoly(mask, [poly], 255)
        area = int(cv2.countNonZero(mask))
        ctr = _project(H, np.array([[cx, cy]]))[0]
        x1, y1 = poly.min(axis=0)
        x2, y2 = poly.max(axis=0)
        # destek skoru: maske icinde sivi orani (pembe besiyeri veya boya)
        support = float(cv2.countNonZero(cv2.bitwise_and(pink, mask))) / max(area, 1)
        if j in srcmap:
            src = "yolo" if srcmap[j][3] > 0 else "hough"
        else:
            src = "grid"
        res.detections.append(PetriDetection(
            bbox_xyxy=(float(x1), float(y1), float(x2), float(y2)),
            conf=round(support, 3),
            mask=mask,
            contour=poly.reshape(-1, 1, 2),
            centroid_px=(float(ctr[0]), float(ctr[1])),
            area_px=area,
            radius_px=float((x2 - x1 + y2 - y1) / 4.0),
        ))
        res.well_ids.append(f"{ROW_LETTERS[r_idx]}{c_idx + 1}")
        res.wells_plate_mm.append((float(cx), float(cy)))
        res.sources.append(src)
    res.n_candidates = len(cands)
    res.n_yolo_candidates = yolo_n
    res.well_radius_px = round(spec.well_diam_mm / 2.0 / res.mm_per_px, 1)
    res.warnings = _quality_warnings(res, spec, (h, w))
    if a1_warn:
        res.warnings.append(a1_warn)
    if yolo_hata:
        res.warnings.append(f"yolo_candidates_failed: YOLO aday cagrisi dustu ({yolo_hata}) - izgara Hough + ECC ile kuruldu")
    return res


def _quality_warnings(res: PlateGridResult, spec: PlateSpec,
                      shape: tuple[int, int]) -> list[str]:
    """Cekim protokolu kontrolu (README 'Cekim Protokolu')."""
    warn = []
    h, w = shape
    if res.well_radius_px < 25:
        warn.append(f"low_resolution: kuyucuk yaricapi {res.well_radius_px:.0f}px "
                    f"(<25) - plakaya daha yakin cek")
    if res.n_inliers < 6:
        warn.append(f"few_candidates: {res.n_inliers} aday dogrulandi - konum "
                    f"agirlikla geometri+ECC'den")
    if not res.ecc_ok:
        warn.append("ecc_failed: pembe maske ile ince hizalama yapilamadi")
    ideal = _ideal_centers(spec)
    H = res.H_img_from_plate
    s = [_local_px_per_mm(H, tuple(p)) for p in (ideal[0], ideal[-1],
                                                  ideal[spec.cols - 1],
                                                  ideal[-spec.cols])]
    # egiklik: (1) olcek plaka boyunca degisiyor (yakin perspektif)
    #         (2) bir eksen digerine gore basik (uzak egik cekim)
    c = ideal.mean(axis=0)
    q3 = _project(H, np.array([c, c + (1, 0), c + (0, 1)]))
    sv = np.linalg.svd(np.stack([q3[1] - q3[0], q3[2] - q3[0]], axis=1),
                       compute_uv=False)
    aniso = float(sv[0] / max(sv[1], 1e-9))
    if max(s) / min(s) > 1.25 or aniso > 1.3:
        warn.append(f"oblique_view: olcek degisimi x{max(s) / min(s):.2f}, "
                    f"eksen basikligi x{aniso:.2f} - kamerayi plakaya dik tut")
    q = np.array(res.plate_quad_px)
    if (q[:, 0].min() < 3 or q[:, 1].min() < 3 or q[:, 0].max() > w - 4
            or q[:, 1].max() > h - 4):
        warn.append("plate_cropped: plaka goruntu kenarina degiyor")
    return warn
