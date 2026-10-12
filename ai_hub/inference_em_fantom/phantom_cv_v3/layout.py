# Author: mertaygn, cglrgrkn
"""layout.py — Fantom tumor yerlesim referansi (v2).

Ayni fantom farkli acilardan cekildiginde tumorler arasi geometri sabittir.
Iyi goruntulerden ortak bir yerlesim (mm) cikarilir ve su islere yarar:

  1. SABIT KIMLIK: her goruntudeki tumorler referansa benzerlik donusumuyle
     (donme + olcek + oteleme, AYNALAMA YOK) eslenir -> T1 her goruntude ayni tumor
  2. DUSUK COZUNURLUK: tumorler ayrilamiyorsa referans sablonu tumor maskesine
     fit edilir (konum + olcek) -> merkezler ve mm olcegi sablondan
  3. QC: kayit hatasi buyukse uyari (yanlis tespit / farkli fantom)

Referans olusturma (bir v2 kosusunun ciktisindan):
  python -m phantom_cv_v3.layout --build phantom_cv/results/<kosu> \
      --out phantom_cv_v3/phantom_layout_<tarih>.json
"""
from __future__ import annotations
import argparse
import itertools
import json
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


@dataclass
class Layout:
    ids: list[str]
    points_mm: np.ndarray            # (n, 2), Y yukari
    tumor_radius_mm: float
    n_images: int = 0
    rms_mm: float = 0.0
    source: str = ""
    # fantom kutusu referans cercevesinde (u = uzun eksen birim vektoru)
    box_center_mm: np.ndarray | None = None
    box_axis_u: np.ndarray | None = None
    box_size_mm: tuple[float, float] | None = None

    def to_uv(self, p_ref: np.ndarray) -> tuple[float, float] | None:
        if self.box_center_mm is None:
            return None
        eu = self.box_axis_u
        ev = np.array([-eu[1], eu[0]])
        d = np.asarray(p_ref, dtype=np.float64) - self.box_center_mm
        return float(d @ eu), float(d @ ev)

    @classmethod
    def load(cls, path) -> "Layout":
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        box = d.get("phantom_box") or {}
        return cls(ids=d["ids"], points_mm=np.asarray(d["points_mm"], dtype=np.float64),
                   tumor_radius_mm=float(d["tumor_radius_mm"]),
                   n_images=int(d.get("n_images", 0)), rms_mm=float(d.get("rms_mm", 0)),
                   source=d.get("source", ""),
                   box_center_mm=(np.asarray(box["center_mm"], dtype=np.float64)
                                  if box else None),
                   box_axis_u=(np.array([np.cos(np.deg2rad(box["long_axis_deg"])),
                                         np.sin(np.deg2rad(box["long_axis_deg"]))])
                               if box else None),
                   box_size_mm=(tuple(box["size_mm"]) if box else None))

    def save(self, path) -> None:
        Path(path).write_text(json.dumps({
            "ids": self.ids, "points_mm": np.round(self.points_mm, 3).tolist(),
            "tumor_radius_mm": round(self.tumor_radius_mm, 2),
            "n_images": self.n_images, "rms_mm": round(self.rms_mm, 3),
            "source": self.source,
            **({"phantom_box": {
                "center_mm": np.round(self.box_center_mm, 3).tolist(),
                "long_axis_deg": round(float(np.degrees(np.arctan2(self.box_axis_u[1],
                                                                   self.box_axis_u[0]))), 2),
                "size_mm": [round(float(v), 1) for v in self.box_size_mm]}}
               if self.box_center_mm is not None else {}),
            "note": "Tumor merkezleri, fantom duzleminde mm (Y yukari). "
                    "Kimlikler bu referanstaki sirayi izler.",
        }, indent=2, ensure_ascii=False), encoding="utf-8")


def similarity_fit(src: np.ndarray, dst: np.ndarray, allow_scale=True):
    """src -> dst en kucuk kareler benzerlik (Umeyama, yansima YOK).
    -> (s, R, t, rms) ; dst ~ s R src + t"""
    mu_s, mu_d = src.mean(0), dst.mean(0)
    A, B = src - mu_s, dst - mu_d
    U, S, Vt = np.linalg.svd(B.T @ A)
    D = np.eye(2)
    D[1, 1] = np.sign(np.linalg.det(U @ Vt))      # aynalamayi engelle
    R = U @ D @ Vt
    s = (S * np.diag(D)).sum() / max((A ** 2).sum(), 1e-12) if allow_scale else 1.0
    t = mu_d - s * R @ mu_s
    res = dst - (s * (R @ src.T).T + t)
    return s, R, t, float(np.sqrt((res ** 2).sum(1).mean()))


def register(points: np.ndarray, ref: np.ndarray, allow_scale=True,
             scale_bounds=(0.5, 2.0)):
    """Gozlenen noktalar (n <= m) -> referans (m). En iyi atama + benzerlik.

    -> (assign, s, R, t, rms): points[i] <-> ref[assign[i]]; ref ~ s R points + t
    """
    n, m = len(points), len(ref)
    if n < 2 or n > m:
        return None
    best = None
    for subset in itertools.permutations(range(m), n):
        s, R, t, rms = similarity_fit(points, ref[list(subset)], allow_scale)
        if not allow_scale or scale_bounds[0] < s < scale_bounds[1]:
            if best is None or rms < best[4]:
                best = (list(subset), s, R, t, rms)
    return best


def build_layout(point_sets: list[np.ndarray], radii_mm: list[float], source="") -> Layout:
    """Genellestirilmis Procrustes: hepsini ortak cerceveye hizala, ortala."""
    n = len(point_sets[0])
    sets = [p for p in point_sets if len(p) == n]
    ref = sets[0].copy()
    for _ in range(5):
        aligned = []
        for p in sets:
            assign, s, R, t, _ = register(p, ref, allow_scale=True)
            q = np.zeros_like(ref)
            q[assign] = (s * (R @ p.T).T + t)
            aligned.append(q)
        new = np.mean(aligned, axis=0)
        # olcek: gozlenen ortalama mm olcegini koru (Procrustes kuculmesini engelle)
        size_obs = np.mean([np.sqrt(((p - p.mean(0)) ** 2).sum(1).mean()) for p in sets])
        new = (new - new.mean(0)) * size_obs / np.sqrt(((new - new.mean(0)) ** 2).sum(1).mean())
        ref = new
    # kimlik sirasi: yukaridan asagi (Y buyukten kucuge), sonra soldan saga
    order = np.lexsort((ref[:, 0], -np.round(ref[:, 1] / 5.0)))
    ref = ref[order]
    rms = float(np.mean([register(p, ref, True)[4] for p in sets]))
    return Layout(ids=[f"T{i}" for i in range(1, n + 1)], points_mm=ref,
                  tumor_radius_mm=float(np.median(radii_mm)), n_images=len(sets),
                  rms_mm=rms, source=source)


def fit_template(mask: np.ndarray, layout: Layout, init_center_px, init_mm_per_px: float):
    """Referans sablonunu (diskler) tumor maskesine fit et (dusuk cozunurluk).

    Kaba arama: donme (15 derece adim) x olcek; sonra ECC (MOTION_AFFINE) ince ayar.
    -> (centers_px (m,2), mm_per_px, score) ; score = IoU benzeri ortusme
    """
    h, w = mask.shape
    ys, xs = np.nonzero(mask)
    if len(xs) < 20:
        return None
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    pad = int(0.6 * max(x1 - x0, y1 - y0)) + 5
    rx0, ry0 = max(0, x0 - pad), max(0, y0 - pad)
    rx1, ry1 = min(w, x1 + pad), min(h, y1 + pad)
    target = cv2.GaussianBlur(mask[ry0:ry1, rx0:rx1].astype(np.float32) / 255.0, (0, 0), 1.5)
    P = layout.points_mm - layout.points_mm.mean(0)
    P[:, 1] *= -1                                       # mm Y yukari -> piksel Y asagi
    r_mm = layout.tumor_radius_mm
    cx, cy = mask_centroid = (xs.mean() - rx0, ys.mean() - ry0)

    def render(A):
        img = np.zeros(target.shape, np.float32)
        for p in P:
            q = A @ np.array([p[0], p[1], 1.0])
            rad = max(1, int(round(r_mm * np.sqrt(abs(np.linalg.det(A[:, :2]))))))
            cv2.circle(img, (int(round(q[0])), int(round(q[1]))), rad, 1.0, -1)
        return img

    def score(A):
        t = render(A) > 0.5
        m = target > 0.5
        return (t & m).sum() / max((t | m).sum(), 1)

    # olcek: maske alani ~ sablon disk alani toplami
    area = float((target > 0.5).sum())
    s0 = np.sqrt(area / (len(P) * np.pi * r_mm ** 2)) if area > 0 else 1.0 / init_mm_per_px
    best = None
    for ang in np.deg2rad(np.arange(0, 360, 15)):
        for sf in (0.85, 1.0, 1.15):
            s = s0 * sf
            c, si = np.cos(ang), np.sin(ang)
            A = np.array([[s * c, -s * si, cx], [s * si, s * c, cy]])
            sc = score(A)
            if best is None or sc > best[0]:
                best = (sc, A)
    A = best[1].astype(np.float32)
    try:     # ECC: sablon -> hedef afin (egik cekim kisalmasini da karsilar)
        tmpl = cv2.GaussianBlur(render(np.float64(A)), (0, 0), 1.5)
        W = np.array([[1, 0, 0], [0, 1, 0]], np.float32)
        _, W = cv2.findTransformECC(tmpl, target, W, cv2.MOTION_AFFINE,
                                    (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 100, 1e-5),
                                    None, 3)
        A2 = np.vstack([W, [0, 0, 1]]) @ np.vstack([A, [0, 0, 1]])
        if score(A2[:2]) >= best[0]:
            A = A2[:2].astype(np.float32)
    except cv2.error:
        pass
    A = np.float64(A)
    centers = np.array([A @ np.array([p[0], p[1], 1.0]) for p in P]) + [rx0, ry0]
    mm_per_px = 1.0 / np.sqrt(abs(np.linalg.det(A[:, :2])))
    return centers, float(mm_per_px), float(score(A))


def _cli():
    ap = argparse.ArgumentParser(prog="phantom_cv_v3.layout")
    ap.add_argument("--build", required=True, help="v2 kosu klasoru (result.json'lar)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--min-n", type=int, default=3)
    a = ap.parse_args()
    sets, radii, names, boxes = [], [], [], []
    for p in sorted(Path(a.build).glob("*/result.json")):
        r = json.loads(p.read_text(encoding="utf-8"))
        if not (r.get("success") and r.get("reliable") and r.get("method") == "coil_ring"):
            continue
        T = r["tumor_regions"]
        if len(T) < a.min_n or any(t.get("frame_mm") is None for t in T):
            continue
        sets.append(np.array([t["frame_mm"] for t in T], dtype=np.float64))
        boxes.append(r.get("phantom_frame") or None)
        radii.append(float(np.median([np.sqrt(t["area_mm2"] / np.pi) for t in T])))
        names.append(p.parent.name)
    if not sets:
        raise SystemExit("HATA: uygun (reliable, coil_ring) sonuc yok")
    n = max(set(len(s) for s in sets), key=lambda k: sum(len(s) == k for s in sets))
    keep = [i for i, s_ in enumerate(sets) if len(s_) == n]
    lay = build_layout([sets[i] for i in keep], radii,
                       source=f"{Path(a.build).name}: " + ", ".join(names))
    # Fantom kutusunu referans cercevesine tasi ve ortala (eksen: eksenel ortalama)
    cs, us, sz = [], [], []
    for i in keep:
        b = boxes[i]
        if not b:
            continue
        assign, s_, R, t, _ = register(sets[i], lay.points_mm, True)
        th = np.deg2rad(b["long_axis_deg_in_frame"])
        cs.append(s_ * R @ np.asarray(b["center_frame_mm"]) + t)
        us.append(R @ np.array([np.cos(th), np.sin(th)]))
        sz.append(b["size_mm"])
    if cs:
        u = np.mean(us, axis=0)
        lay.box_center_mm = np.mean(cs, axis=0)
        lay.box_axis_u = u / np.linalg.norm(u)
        lay.box_size_mm = tuple(np.median(np.array(sz), axis=0))
        spread = np.degrees(np.std([np.arctan2(v[1], v[0]) for v in us]))
        print(f"fantom kutusu: {lay.box_size_mm[0]:.0f} x {lay.box_size_mm[1]:.0f} mm, "
              f"{len(cs)} goruntu, eksen sapmasi {spread:.1f} derece")
    lay.save(a.out)
    if lay.box_center_mm is not None:
        for i, p in zip(lay.ids, lay.points_mm):
            print(f"  {i}: u,v = {lay.to_uv(p)[0]:+7.2f}, {lay.to_uv(p)[1]:+7.2f} mm")
    print(f"referans: {n} tumor, {lay.n_images} goruntu, kayit rms {lay.rms_mm:.2f} mm, "
          f"tumor yaricapi {lay.tumor_radius_mm:.1f} mm -> {a.out}")
    for i, p in zip(lay.ids, lay.points_mm):
        print(f"  {i}: ({p[0]:+7.2f}, {p[1]:+7.2f}) mm")


if __name__ == "__main__":
    _cli()
