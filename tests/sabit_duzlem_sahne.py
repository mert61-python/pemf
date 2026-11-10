# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""KD · sabit düzlem testlerinin SENTETİK KABİN çizicisi (test yardımcısı; ürün kodu DEĞİL).

Bilinen K / D (ürünün Pusat 1080p M2 dosyası) ve bilinen kamera duruşuyla HAM (bozulmalı) kare çizer: her piksel için ışın
(`undistortPoints`) → önce plaka ÜST yüzeyi (Y = taban + 20 mm; plaka dikdörtgeni beyaz, 24 kuyu PEMBE disk) → değilse kabin tabanı
(Y = −175 mm; sabit desenli zemin — sahne denetimi buna dayanır). Kuyu merkezleri, köşeler ve lens konumu GERÇEK değer olarak döner.
Kabin çerçevesi ürün kuralı: +X = önden bakanın SOLU, +Y yukarı, +Z arkaya; kabin 55,5 × 35 × 40,5 cm (orijin merkez).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

KOK = Path(__file__).resolve().parents[1]
NPZ = KOK / "ai_hub" / "cv_ortak" / "kalibrasyon" / "pusat_fhd_1920x1080_M2.npz"
EXT_CM = (55.5, 35.0, 40.5)
W, H = 1920, 1080
TABAN_Y = -175.0
PLAKA_YUK = 20.0
PLAKA_UZUN, PLAKA_KISA = 127.76, 85.48
ARALIK = 19.3
#: Görünür pembe disk yarıçapı: kuyu ağzı 15,6 mm ama tepeden besiyeri kuyu duvarı boyunca da görünür (gerçek plakada pembe alan
#: kuyular arasında ~1 mm boşluk bırakır — ızgara dedektörünün plaka bölgesi bunu varsayar). Merkezler DEĞİŞMEZ.
KUYU_R = 9.0
#: T2B kamera: tavan camının üstünde (2,75; 19,5; −12,25) cm, ~15° arkaya eğik — test bu duruşu taban alır.
KAMERA_MM = (27.5, 195.0, -122.5)
EGIM_DEG = 15.0


def ic_parametre():
    d = np.load(NPZ)
    return d["K"].astype(np.float64), d["D"].astype(np.float64).ravel()


def poz(kamera_mm=KAMERA_MM, egim_deg=EGIM_DEG, sapma_deg=0.0, yuvarlanma_deg=0.0):
    """Dünya (kabin) → kamera dönüşü R ve öteleme t (mm). Kamera aşağı bakar; görüntünün ÜSTÜ arka duvar (+Z)."""
    e = np.deg2rad(egim_deg)
    z = np.array([0.0, -np.cos(e), np.sin(e)])
    y = np.array([0.0, -np.sin(e), -np.cos(e)])
    s = np.deg2rad(sapma_deg)
    Ry = np.array([[np.cos(s), 0, np.sin(s)], [0, 1, 0], [-np.sin(s), 0, np.cos(s)]])
    z, y = Ry @ z, Ry @ y
    y = y - z * (y @ z)
    y /= np.linalg.norm(y)
    x = np.cross(y, z)
    r = np.deg2rad(yuvarlanma_deg)
    x, y = np.cos(r) * x + np.sin(r) * y, -np.sin(r) * x + np.cos(r) * y
    R = np.vstack([x, y, z])
    return R, -R @ np.asarray(kamera_mm, dtype=np.float64)


def kuyu_merkezleri(cx, cz, y=TABAN_Y + PLAKA_YUK, yukseltme=0.0):
    """A1…D6 (satır A–D, sütun 1–6) kabin mm. Plaka uzun kenarı sol↔sağ; A1 önden bakınca ARKA-SOL (+X, +Z)."""
    y = y + yukseltme
    out = {}
    for i, harf in enumerate("ABCD"):
        for j in range(6):
            out[f"{harf}{j + 1}"] = np.array([cx + 2.5 * ARALIK - ARALIK * j, y, cz + 1.5 * ARALIK - ARALIK * i])
    return out


def koseler(cx, cz, y=TABAN_Y + PLAKA_YUK, yukseltme=0.0):
    """Plaka üst kenarının dış köşeleri — sıra: ön-sol, ön-sağ, arka-sağ, arka-sol."""
    y = y + yukseltme
    u, k = PLAKA_UZUN / 2.0, PLAKA_KISA / 2.0
    return np.array([[cx + u, y, cz - k], [cx - u, y, cz - k], [cx - u, y, cz + k], [cx + u, y, cz + k]])


def izdusum(R, t, P, K, D):
    import cv2

    rv, _ = cv2.Rodrigues(R)
    p, _ = cv2.projectPoints(np.asarray(P, dtype=np.float64).reshape(-1, 1, 3), rv, t, K, D)
    return p.reshape(-1, 2)


def olcum_cm(P_mm):
    """Kabin mm → (sol cm, ön cm) — sahibin cetvel ölçüsünün tersi."""
    return [(EXT_CM[0] / 2.0 - p[0] / 10.0, p[2] / 10.0 + EXT_CM[2] / 2.0) for p in P_mm]


def lens_cm(kamera_mm=KAMERA_MM):
    x, y, z = (float(v) for v in kamera_mm)
    return (EXT_CM[0] / 2.0 - x / 10.0, z / 10.0 + EXT_CM[2] / 2.0, y / 10.0 + EXT_CM[1] / 2.0)


def _zemin(X, Z):
    """Sabit, desenli kabin tabanı (ORB köşeleri bol) — 14 mm hücreli, tohumlu gri tonlar + ince çizgiler."""
    rng = np.random.default_rng(20261110)
    tablo = rng.integers(40, 215, size=(64, 64)).astype(np.float64)
    i = np.floor(X / 14.0).astype(np.int64) % 64
    j = np.floor(Z / 14.0).astype(np.int64) % 64
    g = tablo[i, j]
    cizgi = (np.abs(((X + 3.0 * Z) % 37.0) - 18.5) < 0.8) | (np.abs(((Z - 2.0 * X) % 53.0) - 26.5) < 0.8)
    g = np.where(cizgi, 20.0, g)
    return g


def ciz(R, t, K, D, *, plaka=(115.0, -32.5), plaka_var=True, yukseltme=0.0):
    """Ham (bozulmalı) BGR kare. `plaka` = (cx, cz) mm, plaka üst yüzeyi Y = taban + 20 mm (+ `yukseltme`: altlık; zemin aynı)."""
    import cv2

    uu, vv = np.meshgrid(np.arange(W, dtype=np.float64), np.arange(H, dtype=np.float64))
    pts = np.stack([uu.ravel(), vv.ravel()], axis=1).reshape(-1, 1, 2)
    n = cv2.undistortPoints(pts, K, D).reshape(-1, 2)
    r = np.column_stack([n, np.ones(len(n))]) @ R  # = (R^T r_cam)^T
    C = -R.T @ t
    img = np.empty((len(n), 3), dtype=np.float64)
    # zemin
    s = (TABAN_Y - C[1]) / r[:, 1]
    X = C[0] + s * r[:, 0]
    Z = C[2] + s * r[:, 2]
    g = _zemin(X, Z)
    img[:] = np.column_stack([g * 0.95, g, g * 1.05])
    if plaka_var:
        cx, cz = plaka
        yp = TABAN_Y + PLAKA_YUK + yukseltme
        s2 = (yp - C[1]) / r[:, 1]
        X2 = C[0] + s2 * r[:, 0]
        Z2 = C[2] + s2 * r[:, 2]
        icinde = (np.abs(X2 - cx) <= PLAKA_UZUN / 2.0) & (np.abs(Z2 - cz) <= PLAKA_KISA / 2.0)
        img[icinde] = (236.0, 238.0, 240.0)
        kuyu = np.zeros(len(n), dtype=bool)
        for P in kuyu_merkezleri(cx, cz, yukseltme=yukseltme).values():
            kuyu |= (X2 - P[0]) ** 2 + (Z2 - P[2]) ** 2 <= KUYU_R**2
        img[icinde & kuyu] = (180.0, 105.0, 255.0)  # BGR pembe besiyeri (HSV h≈165, s≈150, v=255)
    out = np.clip(img, 0, 255).reshape(H, W, 3).astype(np.uint8)
    return cv2.GaussianBlur(out, (0, 0), 0.7)


def konum(R, t, K, D, cx, cz, *, yukseltme=0.0, piksel_gurultu=None):
    """KD-2 çok konumlu kalibrasyon girdisi — ÇİZMEDEN (izdüşümle): plakanın kuyu merkezleri → DÜZELTİLMİŞ piksel (ürünün `_yeni_K`'si),
    ızgara homografisi (plaka mm → piksel; A1 = (0, 0), x → A6, y → D) → `sabit_duzlem.konum_hazirla`. Köşelerin GERÇEK cetvel ölçüsü
    (sol, ön cm) `olcum_cm` olarak döner (görüntü adlandırmasından BAĞIMSIZ — plaka mm → kabin dönüşümüyle)."""
    import cv2

    from ai_hub.cv_ortak import sabit_duzlem as sd

    gercek = kuyu_merkezleri(cx, cz, yukseltme=yukseltme)
    P = np.array(list(gercek.values()))
    pl = np.array([[j * ARALIK, i * ARALIK] for i in range(4) for j in range(6)], dtype=np.float64)
    Kn = sd._yeni_K(K, D, (W, H))
    ham = izdusum(R, t, P, K, D)
    duz = cv2.undistortPoints(ham.reshape(-1, 1, 2), K, D, P=Kn).reshape(-1, 2)
    if piksel_gurultu is not None:
        duz = duz + piksel_gurultu(duz.shape)
    Hm, _ = cv2.findHomography(pl.reshape(-1, 1, 2), duz.reshape(-1, 1, 2))
    k = sd.konum_hazirla(Hm, pl, (PLAKA_UZUN, PLAKA_KISA))
    a1x, a1z = cx + 2.5 * ARALIK, cz + 1.5 * ARALIK
    kabin = [(a1x - u, TABAN_Y, a1z - v) for u, v in k["kose_plaka_mm"]]
    k["olcum_cm"] = olcum_cm(kabin)
    return k
