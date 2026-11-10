# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""SABİT DÜZLEM KALİBRASYONU — ArUco'suz kabin konumu (KD · sahip kararları Y258–Y261, 2026-11-10).

YÖNTEM (Y258; KD-2 ile ÇOK KONUMLU): kamera üst kapağa SABİT; petri / fantom tabanda SABİT yükseklikte durur, yalnız kabin X / Z
değişir. Bir kez: 24'lük plaka kabinin İKİ YANINA (≥ 2 konum, merkezler arası ≥ `KONUM_YAYILIM_ESIGI_MM`) sırayla konur; her konumda
kuyular OTOMATİK bulunur (dokunma yok) ve görüntüde numaralanan dış köşelerden en az ikisi (çapraz) sol camdan + ön camdan ölçülür →
kamera duruşu (R, t) + her konumun kabin içi yeri ORTAK en küçük kareler çözümüyle bulunur (`kalibrasyon_coz`) ve VERİ KÖKÜNE
saklanır (uygulama güncellemesi ezmez). Sonra her karede piksel → ışın → hedef düzlemi → kabin mm; ArUco ARANMAZ (ArUco kodu
SİLİNMEDİ — dosya yoksa bugünkü ArUco kipi aynen çalışır).

KD-2 ÖLÇÜMÜ (kayıtlı tezgâh kareleri, rapor S-KD.4): sahibin cetvel ölçüleri köşe başına σ ≈ 5–8 mm; tek konumlu 4 köşe çözümü
başka konumda 0,8–2,5 cm (eğim tek küçük plakadan ±4° oynar, dönüş 128 mm'lik kenardan ~3°) → ≤ 1 cm TUTMAZ. İki yana yayılmış
iki konumla dışarıda bırakılan plakalarda MERKEZ farkı 0,33–0,91 cm; aynı yanda iki konum (14,5 cm) karşı yanda 1,9 cm → yayılım şartı.

Kabin çerçevesi (ürün kuralı, T2B): orijin iç hacmin merkezi, +X = önden bakanın SOLU, +Y yukarı, +Z arkaya. Ölçüm camların İÇ
yüzünden: X = ext_x/2 − sol, Y = −ext_y/2 + taban, Z = −ext_z/2 + ön (ext = `geometry.cabin_extent_cm`; bugün 55,5 × 35 × 40,5).

ÖLÇÜLEN İKİ KARAR (rapor `DENETIM\\KAMERA-DUZLEM.md` S-KD.1 / S-KD.2):
  * Plaka geometrisi ÖLÇÜLMEZ, bilinir: kuyu ızgarası (19,3 mm) + SBS dış ölçüsü (127,76 × 85,48 mm, ızgara ortada). Cetvel yalnız
    plakanın kabindeki YERİNİ söyler; ölçüler ortak çözümden RMS > `OLCUM_UYUM_ESIGI_MM` ya da tek köşe > `OLCUM_TEK_KOSE_ESIGI_MM`
    saparsa (köşe yanlış yazılmış / sıra karışmış) RET. 3 px eşiği kuyu merkezlerinin izdüşümüne uygulanır.
  * Kuyu aralığı denetimi (19,3 mm, %3) yalnız kameranın YÜKSEKLİK / büyük eğim değişimini görür: yatay 2 cm kayma aralığı HİÇ
    değiştirmez, 2° dönüş kadraj ortasında ~%0,1 değiştirir (plaka kaymasından ayırt edilemez). Bu yüzden kalibrasyon karesi
    (plaka maskelenmiş) REFERANS olarak saklanır ve her karede SABİT SAHNE kayması ölçülür (ORB + RANSAC) — 2 cm / 2° ≈ 45–70 px,
    eşik `SAHNE_KAYMA_ESIGI_PX` (≈ 3–4 mm hedef hatası).

Bu modül saf geometri + dosya G/Ç'dir: backend'i içe AKTARMAZ (ai_hub kuralı); veri kökünü çağıran verir. Konum geçersizse
`KesisimGecersiz` (D1.100 ile aynı sınıf) — konum ÜRETİLMEZ. Bu bir HEDEF GEÇERLİLİK denetimidir; tedavi doz kıskacı değil
(Ö.4-Y9) ve ACİL DURDUR'a dokunmaz (Ö.4-Y8).
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
import threading
import time
from pathlib import Path

import cv2
import numpy as np

from .coord_transform import KesisimGecersiz

SURUM = 2
#: Veri kökü altındaki klasör ve dosyalar (uygulama katmanı DEĞİL — güncelleme ezmez).
KLASOR = "kabin_kalibrasyonu"
DOSYA_ADI = "duzlem_kalibrasyonu.json"
REFERANS_ADI = "duzlem_referans.png"

#: Sahip (istem 44 §1a): yeniden izdüşüm hatası bunu aşarsa kalibrasyon REDDEDİLİR (çok konumlu çözümde: kuyu merkezleri RMS).
IZDUSUM_ESIGI_PX = 3.0
#: Sahip (istem 44 §1a): hesaplanan ↔ ölçülen lens farkı bunu aşarsa UYARI (kaydetmeden önce onay ister) — YATAY (sol / ön).
LENS_UYARI_ESIGI_MM = 20.0
#: Lens YÜKSEKLİĞİ ayrı eşik: ölçü "tavan camının üstünden, cam kalınlığı hariç" alınır ve optik merkez merceğin birkaç mm İÇİNDEDİR
#: → hesaplanan yükseklik ölçüden sistematik ~1,5–2,5 cm fazla çıkar (KD-2 kayıtlı karelerde 38,2–38,5 cm ↔ ölçü 36,5).
LENS_DIKEY_UYARI_ESIGI_MM = 30.0
#: Ölçülen köşelerin çözümden RMS sapması bunu aşarsa RET (cetvel σ ≈ 5–8 mm ölçüldü; 1 cm RMS = kaba hata).
OLCUM_UYUM_ESIGI_MM = 10.0
#: Tek bir köşe çözümden bunu aşarsa RET (RMS'i çok köşede seyrelen yanlış yazılmış köşe).
OLCUM_TEK_KOSE_ESIGI_MM = 20.0
#: Çok konumlu çözüm: en az konum sayısı ve konum merkezleri arası en büyük uzaklık (aynı yandaki iki konum karşı yanı 1,9 cm kaçırdı).
KONUM_ASGARI = 2
KONUM_YAYILIM_ESIGI_MM = 200.0
#: Ortak çözümde artık ağırlıkları: kuyu merkezi pikseli ve cetvel ölçüsü (ölçülen gürültüler).
KUYU_PIKSEL_SIGMA = 0.7
OLCU_SIGMA_MM = 6.0
#: Sahip (istem 44 §1c): eşlenen kuyu aralığı 19,3 mm'den bundan fazla saparsa kamera oynamış sayılır.
KUYU_ARALIGI_TOLERANSI = 0.03
#: Sabit sahne kayması (tam çözünürlük pikseli) bunu aşarsa kamera oynamış sayılır.
SAHNE_KAYMA_ESIGI_PX = 12.0
#: Sahip kararı (KD-1, "kalibre etmeden devam"): kamera oynamışsa kullanıcı yeniden kalibre etmeden SÜRDÜREBİLİR — yalnız kayma ~≤ 2 cm
#: ise (sahne ≤ 70 px ≈ 2 cm / 2°; kuyu aralığı ≤ %10). O andaki kare yeni sahne referansı olur, kuyu aralığı toleransı %10'a çıkar ve
#: her karede "kalibrasyon eski (~1–2 cm)" uyarısı kalır. Daha büyük kayma → yalnız yeniden kalibrasyon.
SAHNE_YENILEME_ESIGI_PX = 70.0
KUYU_ARALIGI_TOLERANSI_ESKI = 0.10
#: Sahip kararı (KD-1): numune tabanı yükseltmesi (kutu / altlık) 0–20 cm.
TABAN_YUKSELTME_AZAMI_MM = 200.0
#: Sahne ölçümünün çalıştığı genişlik (ORB hızı); sonuç tam çözünürlüğe ölçeklenir.
SAHNE_GENISLIK = 960
#: Referans karede bu kadar öznitelik yoksa sahne denetimi YAPILAMAZ (kalibrasyon bunu söyler, kare denetimi uyarı verir).
SAHNE_ASGARI_OZNITELIK = 150
SAHNE_ASGARI_ESLESME = 25
#: Sahip (istem 44 §1c): fantom boyu ayardakinden bu oranda farklıysa hedef YOK.
FANTOM_BOY_TOLERANSI = 0.20
#: KD (istem 44 §1d — boş / fantomsuz karede 0 hedef): fantom tümörleri gövdeden KOYU olmalı (lacivert hale + siyah çekirdek).
#: ÖLÇÜLDÜ (göreli — aydınlatmadan bağımsız): tümör ortanca V / gövde ortanca V hocanın 9 fantom fotoğrafında 0,36–0,71; T2B boş kabin
#: karelerindeki mavi IŞIK YANSIMASI "fantomu" 1,01–1,28 (boyu ayara %17 yakın çıkabildiği için boy denetimi tek başına yetmedi).
FANTOM_KOYULUK_ORANI = 0.85
#: Sahip (istem 44 §4): doğrulama ölçütü — hedef ≤ 1 cm. Ölçüt plaka MERKEZİ (ölçülen köşelerin ortalaması ↔ hesaplanan): köşe başına
#: cetvel gürültüsü σ ≈ 5–8 mm olduğundan tek köşe kusursuz kalibrasyonda da 1 cm'yi aşabilir (köşe farkları bilgi olarak gösterilir).
DOGRULAMA_ESIGI_MM = 10.0

#: SBS / ANSI SLAS 1-2004 plaka DIŞ ölçüsü (mm, uzun × kısa) — kuyu ızgarası bu dikdörtgenin ortasındadır.
PLAKA_DIS_MM = {12: (127.76, 85.48), 24: (127.76, 85.48), 48: (127.76, 85.48), 96: (127.76, 85.48)}
#: Kuyu ızgarasının görüldüğü düzlem = plaka ÜST yüzü (analiz de aynı düzlemi kullanır → kalibrasyonla tutarlı). Tabandan; 24'lük
#: plaka (kapaksız) ~20 mm — sahip ölçüp ekranda değiştirebilir.
VARSAYILAN_PLAKA_YUKSEKLIGI_MM = 20.0
#: Fantom ayarı yoksa referans yerleşimin kutu ölçüsü (`phantom_layout_2026-10-02.json` → `phantom_box.size_mm`).
VARSAYILAN_FANTOM_BOY_MM = (104.1, 65.0)

#: Köşe adları — ekran ve API bu sırayı kullanır.
KOSE_ADLARI = ("on_sol", "on_sag", "arka_sag", "arka_sol")


# ── yardımcılar ──────────────────────────────────────────────────────────────────────────────────────────────────────────
def _sonlu(*degerler) -> bool:
    try:
        return all(math.isfinite(float(v)) for v in degerler)
    except (TypeError, ValueError):
        return False


def dosya_sha256(yol) -> str:
    h = hashlib.sha256()
    with open(yol, "rb") as f:
        for parca in iter(lambda: f.read(1 << 20), b""):
            h.update(parca)
    return h.hexdigest()


def kabin_noktasi_mm(sol_cm: float, on_cm: float, taban_cm: float, ext_cm) -> np.ndarray:
    """Cam iç yüzünden ölçü (cm) → kabin çerçevesi (mm). +X = önden bakanın SOLU, +Z arkaya, +Y yukarı."""
    ex, ey, ez = (float(v) for v in ext_cm)
    return np.array(
        [(ex / 2.0 - float(sol_cm)) * 10.0, (-ey / 2.0 + float(taban_cm)) * 10.0, (-ez / 2.0 + float(on_cm)) * 10.0],
        dtype=np.float64,
    )


def kabin_icinde_mi(p_mm, ext_cm) -> bool:
    yari = [float(v) * 10.0 / 2.0 for v in ext_cm]
    return all(abs(float(a)) <= h for a, h in zip(p_mm, yari))


def _yeni_K(K, D, boyut) -> np.ndarray:
    """`coord_transform.undistort_image` ile AYNI yeni K (alpha 0) — hatlar düzeltilmiş karede çalışır."""
    w, h = (int(v) for v in boyut)
    yeni, _ = cv2.getOptimalNewCameraMatrix(np.asarray(K, np.float64), np.asarray(D, np.float64), (w, h), 0)
    return np.asarray(yeni, dtype=np.float64)


# ── kalibrasyon çözümü (çok konumlu) ───────────────────────────────────────────────────────────────────────────────────────
def konum_hazirla(H_img_from_plate, kuyu_plaka_mm, plaka_dis_mm=PLAKA_DIS_MM[24]) -> dict:
    """Kuyu ızgarası (homografi: plaka mm → DÜZELTİLMİŞ kare pikseli) → kuyu pikselleri + plakanın 4 DIŞ köşesi (plaka mm + piksel).

    Dış dikdörtgen kuyu ızgarasının ortasındadır (SBS; ızgaranın uzun ekseni = 127,76 mm). Köşeler GÖRÜNTÜYE göre adlanır (alttaki iki
    köşe ön, soldaki sol — görüntünün üstü ARKA cam; ters takılı kamerada adlar yer değiştirir ama kullanıcı görüntüde İŞARETLİ köşeyi
    ölçtüğü için eşleşme yine doğrudur). Sıra `KOSE_ADLARI`."""
    H = np.asarray(H_img_from_plate, dtype=np.float64).reshape(3, 3)
    W = np.asarray(kuyu_plaka_mm, dtype=np.float64).reshape(-1, 2)
    kuyu_px = cv2.perspectiveTransform(W.reshape(-1, 1, 2), H).reshape(-1, 2)
    orta = (W.min(axis=0) + W.max(axis=0)) / 2.0
    yay = W.max(axis=0) - W.min(axis=0)
    uzun, kisa = float(plaka_dis_mm[0]) / 2.0, float(plaka_dis_mm[1]) / 2.0
    dx, dy = (uzun, kisa) if yay[0] >= yay[1] else (kisa, uzun)
    kose_pl = orta + np.array([[-dx, -dy], [dx, -dy], [dx, dy], [-dx, dy]], dtype=np.float64)
    kose_px = cv2.perspectiveTransform(kose_pl.reshape(-1, 1, 2), H).reshape(-1, 2)
    sira = np.argsort(kose_px[:, 1])
    arka = sorted(sira[:2].tolist(), key=lambda i: kose_px[i, 0])
    on = sorted(sira[2:].tolist(), key=lambda i: kose_px[i, 0])
    idx = [on[0], on[1], arka[1], arka[0]]
    return {"kuyu_px": kuyu_px, "kuyu_plaka_mm": W, "kose_plaka_mm": kose_pl[idx], "kose_px": kose_px[idx]}


def _lm(f, x0, adim, *, azami: int = 200):
    """Küçük Levenberg–Marquardt (sayısal Jacobian). scipy.optimize dondurulmuş EXE'de AÇIKÇA toplanmadığı için bağımlılıksız."""
    x = np.asarray(x0, dtype=np.float64).copy()
    r = f(x)
    c = float(r @ r)
    lam = 1e-3
    for _ in range(azami):
        J = np.empty((r.size, x.size))
        for j in range(x.size):
            d = np.zeros_like(x)
            d[j] = adim[j]
            J[:, j] = (f(x + d) - r) / adim[j]
        A = J.T @ J
        g = J.T @ r
        ilerledi = False
        while lam < 1e10:
            try:
                dx = -np.linalg.solve(A + lam * np.diag(np.diag(A) + 1e-12), g)
            except np.linalg.LinAlgError:
                lam *= 10.0
                continue
            xn = x + dx
            rn = f(xn)
            cn = float(rn @ rn)
            if np.isfinite(cn) and cn < c:
                ilerledi = (c - cn) > 1e-12 * max(c, 1.0)
                x, r, c = xn, rn, cn
                lam = max(lam / 10.0, 1e-12)
                break
            lam *= 10.0
        if not ilerledi:
            break
    return x, r


def _yon_isareti(kose_pl, kose_px) -> float:
    """Plaka mm → görüntü yönelimi (+1 / −1). Aşağı bakan kamerada görüntü (x, y) → kabin (X, Z) yönelimi KORUR (X̂ × Ẑ = −Ŷ)."""
    a = np.asarray(kose_pl, np.float64)
    b = np.asarray(kose_px, np.float64)
    d_pl = np.cross(a[1] - a[0], a[3] - a[0])
    d_px = np.cross(b[1] - b[0], b[3] - b[0])
    return 1.0 if d_pl * d_px > 0 else -1.0


def _plaka_kabin(c, th, sgn, merkez_pl, pl) -> np.ndarray:
    """Plaka mm → kabin (X, Z): yansıma işareti `sgn` (görüntü yönelimi) + düzlem içi dönüş `th` + öteleme `c`."""
    d = np.asarray(pl, np.float64).reshape(-1, 2) - merkez_pl
    d = np.column_stack([d[:, 0], sgn * d[:, 1]])
    co, si = math.cos(th), math.sin(th)
    return np.column_stack([c[0] + co * d[:, 0] - si * d[:, 1], c[1] + si * d[:, 0] + co * d[:, 1]])


def _olculen(konum, ext) -> list[tuple[int, np.ndarray]]:
    out = []
    for i, o in enumerate(konum["olcum_cm"]):
        if o is not None:
            out.append((i, kabin_noktasi_mm(o[0], o[1], 0.0, ext)[[0, 2]]))
    return out


def _ortak_coz(konumlar, K_yeni, duzlem_y, ext):
    """Kamera duruşu (6) + konum başına (X, Z, θ) → kuyu izdüşümü / σp + ölçülen köşe / σm en küçük kareler. → (rv, tv, yerler) | None."""
    hazir = []
    for k in konumlar:
        merkez = (k["kose_plaka_mm"].min(axis=0) + k["kose_plaka_mm"].max(axis=0)) / 2.0
        sgn = _yon_isareti(k["kose_plaka_mm"], k["kose_px"])
        olc = _olculen(k, ext)
        idx = [i for i, _ in olc]
        M = np.array([m for _, m in olc])
        P = _plaka_kabin((0.0, 0.0), 0.0, sgn, merkez, k["kose_plaka_mm"][idx])
        pc, mc = P.mean(axis=0), M.mean(axis=0)
        Hm = (P - pc).T @ (M - mc)
        th = math.atan2(Hm[0, 1] - Hm[1, 0], Hm[0, 0] + Hm[1, 1])
        co, si = math.cos(th), math.sin(th)
        c0 = mc - np.array([[co, -si], [si, co]]) @ pc
        hazir.append({"merkez": merkez, "sgn": sgn, "olc": olc, "x0": [c0[0], c0[1], th], **k})
    # Başlangıç duruşu: ölçüyle yerleştirilmiş BÜTÜN kuyular (eş düzlemli) → IPPE (iki çözüm; kamera düzlemin ÜSTÜNDE olan).
    nesne, img = [], []
    for h in hazir:
        XZ = _plaka_kabin(h["x0"][:2], h["x0"][2], h["sgn"], h["merkez"], h["kuyu_plaka_mm"])
        nesne.append(np.column_stack([XZ[:, 0], np.full(len(XZ), duzlem_y), XZ[:, 1]]))
        img.append(h["kuyu_px"])
    nesne = np.vstack(nesne).astype(np.float64)
    img = np.vstack(img).astype(np.float64)
    try:
        n, rvs, tvs, _e = cv2.solvePnPGeneric(nesne.reshape(-1, 1, 3), img.reshape(-1, 1, 2), K_yeni, None, flags=cv2.SOLVEPNP_IPPE)
    except cv2.error:
        n, rvs, tvs = 0, [], []
    bas = []
    for rv, tv in zip(rvs[: int(n)], tvs[: int(n)]):
        R, _ = cv2.Rodrigues(rv)
        if float((-R.T @ tv.reshape(3))[1]) > duzlem_y:
            bas.append((rv.reshape(3), tv.reshape(3)))
    if not bas:
        return None, ("kamera_duzlem_altinda" if int(n) else "cozum_yok")

    def artik(x):
        rv, tv = x[:3], x[3:6]
        r = []
        for j, h in enumerate(hazir):
            c, th = x[6 + 3 * j: 8 + 3 * j], x[8 + 3 * j]
            XZ = _plaka_kabin(c, th, h["sgn"], h["merkez"], h["kuyu_plaka_mm"])
            P3 = np.column_stack([XZ[:, 0], np.full(len(XZ), duzlem_y), XZ[:, 1]])
            pp, _ = cv2.projectPoints(P3.reshape(-1, 1, 3), rv, tv, K_yeni, None)
            r.append(((pp.reshape(-1, 2) - h["kuyu_px"]) / KUYU_PIKSEL_SIGMA).ravel())
            KZ = _plaka_kabin(c, th, h["sgn"], h["merkez"], h["kose_plaka_mm"])
            for i, m in h["olc"]:
                r.append((KZ[i] - m) / OLCU_SIGMA_MM)
        return np.concatenate(r)

    adim = np.array([1e-6] * 3 + [1e-3] * 3 + [1e-3, 1e-3, 1e-6] * len(hazir))
    en_iyi = None
    for rv0, tv0 in bas:
        x0 = np.concatenate([rv0, tv0] + [np.asarray(h["x0"], np.float64) for h in hazir])
        x, r = _lm(artik, x0, adim)
        maliyet = float(r @ r)
        if np.all(np.isfinite(x)) and (en_iyi is None or maliyet < en_iyi[0]):
            en_iyi = (maliyet, x)
    if en_iyi is None:
        return None, "cozum_yok"
    x = en_iyi[1]
    R, _ = cv2.Rodrigues(x[:3])
    if float((-R.T @ x[3:6])[1]) <= duzlem_y:
        return None, "kamera_duzlem_altinda"
    yerler = []
    for j, h in enumerate(hazir):
        c, th = x[6 + 3 * j: 8 + 3 * j], x[8 + 3 * j]
        XZ = _plaka_kabin(c, th, h["sgn"], h["merkez"], h["kuyu_plaka_mm"])
        P3 = np.column_stack([XZ[:, 0], np.full(len(XZ), duzlem_y), XZ[:, 1]])
        pp, _ = cv2.projectPoints(P3.reshape(-1, 1, 3), x[:3], x[3:6], K_yeni, None)
        e_px = np.linalg.norm(pp.reshape(-1, 2) - h["kuyu_px"], axis=1)
        KZ = _plaka_kabin(c, th, h["sgn"], h["merkez"], h["kose_plaka_mm"])
        sap = [None] * 4
        for i, m in h["olc"]:
            sap[i] = float(np.linalg.norm(KZ[i] - m))
        yerler.append({"merkez_xz": np.asarray(c, np.float64), "kose_xz": KZ, "kuyu_px_hata": e_px, "kose_sapmasi_mm": sap})
    return (x[:3].copy(), x[3:6].copy(), yerler), None


def kalibrasyon_coz(
    *,
    konumlar,
    K,
    D,
    boyut,
    ext_cm,
    plaka_yuksekligi_mm: float = VARSAYILAN_PLAKA_YUKSEKLIGI_MM,
    lens_cm=None,
    capraz: bool = True,
) -> dict:
    """ÇOK KONUMLU kalibrasyon. `konumlar`: her biri `konum_hazirla()` çıktısı + `olcum_cm` (4 öğe, sıra `KOSE_ADLARI`; ölçülmeyen
    köşe None; konum başına ≥ 2 köşe). Pikseller DÜZELTİLMİŞ karede (`undistort_image` / `_yeni_K`).

    @return {"gecerli", "nedenler", "lens_uyarisi", …ölçümler}. Neden kodları: `girdi_gecersiz`, `konum_az`, `olcum_eksik`,
    `cozum_yok`, `kamera_duzlem_altinda`, `olcum_tutarsiz`, `izdusum_yuksek`, `konum_yayilimi_az`. `gecerli` False ise KAYDEDİLMEZ.
    `capraz` (≥ 3 konum): her konum dışarıda bırakılıp kalanlarla çözülür → o plakanın MERKEZ farkı (çapraz doğrulama, bilgi)."""
    sonuc: dict = {"gecerli": False, "nedenler": [], "lens_uyarisi": False}
    try:
        K = np.asarray(K, dtype=np.float64).reshape(3, 3)
        D = np.asarray(D, dtype=np.float64).ravel()
        w, h = (int(v) for v in boyut)
        ext = [float(v) for v in ext_cm]
        ph = float(plaka_yuksekligi_mm)
        kl = []
        for k in konumlar:
            olc = list(k["olcum_cm"])
            if len(olc) != 4:
                raise ValueError("olcum_cm")
            kl.append(
                {
                    "kuyu_px": np.asarray(k["kuyu_px"], np.float64).reshape(-1, 2),
                    "kuyu_plaka_mm": np.asarray(k["kuyu_plaka_mm"], np.float64).reshape(-1, 2),
                    "kose_plaka_mm": np.asarray(k["kose_plaka_mm"], np.float64).reshape(4, 2),
                    "kose_px": np.asarray(k["kose_px"], np.float64).reshape(4, 2),
                    "olcum_cm": [None if o is None else (float(o[0]), float(o[1])) for o in olc],
                }
            )
    except (TypeError, ValueError, KeyError, IndexError):
        sonuc["nedenler"].append("girdi_gecersiz")
        return sonuc
    sayisal = all(
        np.all(np.isfinite(k["kuyu_px"])) and np.all(np.isfinite(k["kose_px"])) and len(k["kuyu_px"]) == len(k["kuyu_plaka_mm"]) >= 4
        and all(o is None or _sonlu(*o) for o in k["olcum_cm"])
        for k in kl
    )
    if not sayisal or not _sonlu(ph, *ext) or w <= 0 or h <= 0 or not (0.0 <= ph <= 100.0):
        sonuc["nedenler"].append("girdi_gecersiz")
        return sonuc
    if len(kl) < KONUM_ASGARI:
        sonuc["nedenler"].append("konum_az")
        return sonuc
    if any(sum(o is not None for o in k["olcum_cm"]) < 2 for k in kl):
        sonuc["nedenler"].append("olcum_eksik")
        return sonuc
    K_yeni = _yeni_K(K, D, (w, h))
    duzlem_y = (-ext[1] / 2.0) * 10.0 + ph
    sonuc["duzlem_y_mm"] = round(duzlem_y, 3)
    cozum, neden = _ortak_coz(kl, K_yeni, duzlem_y, ext)
    if cozum is None:
        sonuc["nedenler"].append(neden)
        return sonuc
    rv, tv, yerler = cozum
    R, _ = cv2.Rodrigues(rv)
    C = (-R.T @ tv).astype(np.float64)
    kuyu_hata = np.concatenate([y["kuyu_px_hata"] for y in yerler])
    sapmalar = [s for y in yerler for s in y["kose_sapmasi_mm"] if s is not None]
    izd = float(np.sqrt(np.mean(kuyu_hata**2)))
    rms = float(np.sqrt(np.mean(np.square(sapmalar))))
    merkezler = np.array([y["merkez_xz"] for y in yerler])
    yayilim = max(float(np.linalg.norm(a - b)) for i, a in enumerate(merkezler) for b in merkezler[i + 1:])
    sonuc.update(
        {
            "izdusum_hatasi_px": round(izd, 3),
            "olcum_uyumu_mm": round(rms, 2),
            "yayilim_mm": round(yayilim, 1),
            "R": R.tolist(),
            "rvec": rv.tolist(),
            "t_mm": tv.tolist(),
            "kamera_konumu_mm": [round(float(v), 2) for v in C],
            "konumlar": [
                {
                    "merkez_kabin_mm": [round(float(y["merkez_xz"][0]), 2), round(duzlem_y, 2), round(float(y["merkez_xz"][1]), 2)],
                    "kose_kabin_mm": [[round(float(p[0]), 2), round(duzlem_y, 2), round(float(p[1]), 2)] for p in y["kose_xz"]],
                    "kose_sapmasi_mm": [None if s is None else round(s, 2) for s in y["kose_sapmasi_mm"]],
                    "kuyu_izdusum_px": round(float(np.sqrt(np.mean(y["kuyu_px_hata"] ** 2))), 3),
                }
                for y in yerler
            ],
        }
    )
    if lens_cm is not None:
        try:
            L = kabin_noktasi_mm(lens_cm[0], lens_cm[1], lens_cm[2], ext)
        except (TypeError, ValueError, IndexError):
            L = None
        if L is None or not np.all(np.isfinite(L)):
            sonuc["nedenler"].append("girdi_gecersiz")
            return sonuc
        yatay = float(np.hypot(C[0] - L[0], C[2] - L[2]))
        dikey = float(C[1] - L[1])
        sonuc.update(
            {
                "olculen_lens_mm": [round(float(v), 2) for v in L],
                "lens_farki_mm": round(float(np.linalg.norm(C - L)), 2),
                "lens_yatay_farki_mm": round(yatay, 2),
                "lens_dikey_farki_mm": round(dikey, 2),
                "lens_uyarisi": bool(yatay > LENS_UYARI_ESIGI_MM or abs(dikey) > LENS_DIKEY_UYARI_ESIGI_MM),
            }
        )
    if capraz and len(kl) >= 3:
        cd = []
        for i in range(len(kl)):
            kalan = kl[:i] + kl[i + 1:]
            c2, _n = _ortak_coz(kalan, K_yeni, duzlem_y, ext)
            if c2 is None:
                cd.append(None)
                continue
            R2, _ = cv2.Rodrigues(c2[0])
            hm = DuzlemHaritasi.durustan(K, D, (w, h), R2, c2[1], ext, duzlem_y)
            olc = _olculen(kl[i], ext)
            try:
                tah = np.array([hm.kabin_noktasi(kl[i]["kose_px"][j], duzlem_y, kabin_siniri=False)[[0, 2]] for j, _ in olc])
            except KesisimGecersiz:
                cd.append(None)
                continue
            cd.append(round(float(np.linalg.norm(tah.mean(axis=0) - np.mean([m for _, m in olc], axis=0))), 2))
        sonuc["capraz_dogrulama_mm"] = cd
    if rms > OLCUM_UYUM_ESIGI_MM or (sapmalar and max(sapmalar) > OLCUM_TEK_KOSE_ESIGI_MM):
        sonuc["nedenler"].append("olcum_tutarsiz")
    if izd > IZDUSUM_ESIGI_PX:
        sonuc["nedenler"].append("izdusum_yuksek")
    if yayilim < KONUM_YAYILIM_ESIGI_MM:
        sonuc["nedenler"].append("konum_yayilimi_az")
    sonuc["gecerli"] = not sonuc["nedenler"]
    return sonuc


def a1_kosesi(harita: "DuzlemHaritasi", y_mm: float) -> str | None:
    """Kabinin ARKA-SOL yönü görüntüde hangi köşede (`plate_grid` adı: tl / tr / br / bl) — plaka A1 arka-solda konur (kılavuz).

    Kalibrasyondan: karenin ortasındaki düzlem noktası P → P + 50 mm (+X sol, +Z arka) → düzeltilmiş piksel farkının işaretleri. Kamera
    ters (180°) ya da yan (90°) takılsa da A1 doğru adlanır (sabit "tl" varsayımı o durumda kuyu kimliklerini aynalardı). Kesişim yoksa None."""
    w, h = harita.boyut
    try:
        P = harita.kabin_noktasi((w / 2.0, h / 2.0), y_mm, kabin_siniri=False)
    except KesisimGecersiz:
        return None
    p0 = harita.piksel(P)
    p1 = harita.piksel(P + np.array([50.0, 0.0, 50.0]))
    dx, dy = float(p1[0] - p0[0]), float(p1[1] - p0[1])
    return ("t" if dy < 0 else "b") + ("l" if dx < 0 else "r")


def gorus_alani(harita: "DuzlemHaritasi", y_mm: float) -> dict:
    """Kör bölge (sahip, KD-1): DÜZELTİLMİŞ karenin kenarları `y_mm` düzlemine → camdan itibaren görünmeyen şerit (cm, 0,5'e yuvarlı).

    `on_cm`: ön camdan ilk N cm görünmez (karenin ALT kenarı, kabin genişliği içinde en kötü nokta); `arka_cm` / `sol_cm` / `sag_cm`
    benzer (0 = o cama kadar görünür). Görüntünün üstü ARKA cam varsayımıyla; kenar ışını düzlemi kesmiyorsa o yön None."""
    w, h = harita.boyut
    ex, _ey, ez = (float(v) * 10.0 for v in harita.ext_cm)
    t = np.linspace(0.0, 1.0, 41)
    kenarlar = {
        "on": np.column_stack([t * (w - 1), np.full_like(t, h - 1)]),
        "arka": np.column_stack([t * (w - 1), np.zeros_like(t)]),
        "sol": np.column_stack([np.zeros_like(t), t * (h - 1)]),
        "sag": np.column_stack([np.full_like(t, w - 1), t * (h - 1)]),
    }
    out = {}
    for ad, pts in kenarlar.items():
        q = []
        for p in pts:
            try:
                q.append(harita.kabin_noktasi(p, y_mm, kabin_siniri=False))
            except KesisimGecersiz:
                continue
        if not q:
            out[ad] = None
            continue
        q = np.array(q)
        if ad in ("on", "arka"):
            q = q[np.abs(q[:, 0]) <= ex / 2.0]
            seri = (q[:, 2] + ez / 2.0) if ad == "on" else (ez / 2.0 - q[:, 2])
        else:
            q = q[np.abs(q[:, 2]) <= ez / 2.0]
            seri = (ex / 2.0 - q[:, 0]) if ad == "sol" else (q[:, 0] + ex / 2.0)
        if len(seri) == 0:
            out[ad] = None
            continue
        out[ad] = round(max(0.0, float(seri.max())) / 10.0 * 2.0) / 2.0
    return out


# ── çalışma anı: piksel → kabin ─────────────────────────────────────────────────────────────────────────────────────────
class DuzlemHaritasi:
    """Saklanan duruşla piksel → ışın → yatay düzlem (Y = sabit) → kabin mm.

    `duzeltilmis=True`: piksel `undistort_image` çıktısındadır (yeni K, bozulma YOK — T2B B2 "çift bozulma" bu yolda OLMAZ);
    `False`: ham kare pikseli (K + D ile `undistortPoints`)."""

    def __init__(self, kal: dict):
        ip = kal["ic_parametre"]
        self.K = np.asarray(ip["K"], dtype=np.float64).reshape(3, 3)
        self.D = np.asarray(ip["D"], dtype=np.float64).ravel()
        self.boyut = (int(kal["kamera"]["genislik"]), int(kal["kamera"]["yukseklik"]))
        self.R = np.asarray(kal["R"], dtype=np.float64).reshape(3, 3)
        self.t = np.asarray(kal["t_mm"], dtype=np.float64).reshape(3)
        self.C = (-self.R.T @ self.t).astype(np.float64)
        self.ext_cm = [float(v) for v in kal["kabin_ext_cm"]]
        self.duzlem_y_mm = float(kal["duzlem_y_mm"])
        #: Sahip kararı (KD-1): numune tabanı yükseltmesi (altlık / kutu) — petri ızgara düzlemi + hedef ve fantom tabanı bu kadar yukarı.
        self.yukseltme_mm = taban_yukseltmesi_mm(kal)
        self.K_yeni = _yeni_K(self.K, self.D, self.boyut)
        self._K_yeni_ters = np.linalg.inv(self.K_yeni)

    @classmethod
    def durustan(cls, K, D, boyut, R, t_mm, ext_cm, duzlem_y_mm) -> "DuzlemHaritasi":
        return cls(
            {
                "ic_parametre": {"K": np.asarray(K).tolist(), "D": np.asarray(D).ravel().tolist()},
                "kamera": {"genislik": int(boyut[0]), "yukseklik": int(boyut[1])},
                "R": np.asarray(R).tolist(),
                "t_mm": np.asarray(t_mm).ravel().tolist(),
                "kabin_ext_cm": list(ext_cm),
                "duzlem_y_mm": float(duzlem_y_mm),
            }
        )

    @property
    def numune_y_mm(self) -> float:
        """Petri ızgara düzlemi (plaka üstü) — kalibrasyon düzlemi + taban yükseltmesi."""
        return self.duzlem_y_mm + self.yukseltme_mm

    @property
    def taban_y_mm(self) -> float:
        """Numunenin oturduğu taban (fantom alt yüzü) — kabin tabanı + yükseltme."""
        return -self.ext_cm[1] * 10.0 / 2.0 + self.yukseltme_mm

    def isin(self, px, *, duzeltilmis: bool = True) -> np.ndarray:
        u, v = float(px[0]), float(px[1])
        if duzeltilmis:
            r = self._K_yeni_ters @ np.array([u, v, 1.0])
        else:
            n = cv2.undistortPoints(np.array([[[u, v]]], dtype=np.float64), self.K, self.D).reshape(2)
            r = np.array([n[0], n[1], 1.0])
        r = self.R.T @ r
        return r / np.linalg.norm(r)

    def kabin_noktasi(self, px, y_mm: float, *, duzeltilmis: bool = True, kabin_siniri: bool = True) -> np.ndarray:
        r = self.isin(px, duzeltilmis=duzeltilmis)
        if abs(float(r[1])) < 1e-9:
            raise KesisimGecersiz("isin hedef duzlemine paralel — kesisim yok")
        s = (float(y_mm) - float(self.C[1])) / float(r[1])
        if s <= 0:
            raise KesisimGecersiz(f"isin hedef duzlemini kameranin ARKASINDA kesiyor (s={s:.1f} mm)")
        p = self.C + s * r
        if kabin_siniri and not kabin_icinde_mi(p, self.ext_cm):
            raise KesisimGecersiz(f"kesisim kabin DISINDA {tuple(round(float(a), 1) for a in p)} mm")
        return p.astype(np.float64)

    def piksel(self, p_mm, *, duzeltilmis: bool = True) -> np.ndarray:
        """Kabin noktası → piksel (doğrulama / çizim)."""
        rv, _ = cv2.Rodrigues(self.R)
        if duzeltilmis:
            pp, _ = cv2.projectPoints(np.asarray(p_mm, np.float64).reshape(1, 1, 3), rv, self.t, self.K_yeni, None)
        else:
            pp, _ = cv2.projectPoints(np.asarray(p_mm, np.float64).reshape(1, 1, 3), rv, self.t, self.K, self.D)
        return pp.reshape(2)


def kuyu_araligi(
    harita: DuzlemHaritasi,
    H_img_from_plate,
    satir: int,
    sutun: int,
    aralik_mm: float,
    y_mm: float,
    tolerans: float = KUYU_ARALIGI_TOLERANSI,
) -> dict:
    """Plaka ızgarasının (homografi, DÜZELTİLMİŞ kare) İDEAL kuyu merkezlerini düzleme eşle → komşu aralıkları 19,3 mm ile karşılaştır.

    Kuyu SKORU eşiğinde elenen hücreler ölçüyü bozmasın diye merkezler homografiden üretilir (ızgaranın kendisi). Ölçüt: sütun ve satır
    yönündeki ORTANCA aralığın orana sapması; büyük olanı `sapma`."""
    H = np.asarray(H_img_from_plate, dtype=np.float64).reshape(3, 3)
    ideal = np.array([[c * aralik_mm, r * aralik_mm] for r in range(satir) for c in range(sutun)], dtype=np.float64)
    pix = cv2.perspectiveTransform(ideal.reshape(-1, 1, 2), H).reshape(-1, 2)
    pts = np.array([harita.kabin_noktasi(p, y_mm, kabin_siniri=False) for p in pix]).reshape(satir, sutun, 3)
    sut = np.linalg.norm(pts[:, 1:] - pts[:, :-1], axis=2).ravel() if sutun > 1 else np.array([aralik_mm])
    sat = np.linalg.norm(pts[1:] - pts[:-1], axis=2).ravel() if satir > 1 else np.array([aralik_mm])
    o_sut = float(np.median(sut)) / aralik_mm
    o_sat = float(np.median(sat)) / aralik_mm
    sapma = max(abs(o_sut - 1.0), abs(o_sat - 1.0))
    return {
        "sutun_mm": round(float(np.median(sut)), 3),
        "satir_mm": round(float(np.median(sat)), 3),
        "beklenen_mm": aralik_mm,
        "sapma": round(sapma, 4),
        "tolerans": tolerans,
        "gecti": bool(sapma <= tolerans),
    }


def komsu_kuyu_araligi(harita: DuzlemHaritasi, konum: dict, aralik_mm: float, y_mm: float, tolerans: float) -> dict:
    """`konum_hazirla` sözlüğünden (yönelimden bağımsız): plaka mm'de aralığı ≈ `aralik_mm` olan KOMŞU kuyu çiftlerinin düzlemdeki
    uzaklığı → ortanca oran. Sonuç `kuyu_araligi` ile aynı biçim (satır / sütun ayrımı yok → ikisi de ortanca)."""
    W = np.asarray(konum["kuyu_plaka_mm"], np.float64).reshape(-1, 2)
    P = np.array([harita.kabin_noktasi(p, y_mm, kabin_siniri=False) for p in np.asarray(konum["kuyu_px"]).reshape(-1, 2)])
    d = []
    for i in range(len(W)):
        for j in range(i + 1, len(W)):
            if abs(float(np.linalg.norm(W[i] - W[j])) - aralik_mm) < 0.25 * aralik_mm:
                d.append(float(np.linalg.norm(P[i] - P[j])))
    if not d:
        raise ValueError("komsu kuyu yok")
    m = float(np.median(d))
    sapma = abs(m / aralik_mm - 1.0)
    return {
        "sutun_mm": round(m, 3),
        "satir_mm": round(m, 3),
        "beklenen_mm": aralik_mm,
        "sapma": round(sapma, 4),
        "tolerans": tolerans,
        "gecti": bool(sapma <= tolerans),
    }


def _gri_kucuk(goruntu, maske=None):
    """Gri + TAM `SAHNE_GENISLIK` genişliğe (küçültülmüş analiz karesi de aynı boyuta gelir — referansla karşılaştırılabilir)."""
    g = goruntu if goruntu.ndim == 2 else cv2.cvtColor(goruntu, cv2.COLOR_BGR2GRAY)
    olcek = SAHNE_GENISLIK / float(g.shape[1])
    if g.shape[1] != SAHNE_GENISLIK:
        g = cv2.resize(
            g,
            (SAHNE_GENISLIK, max(1, int(round(g.shape[0] * olcek)))),
            interpolation=cv2.INTER_AREA if olcek < 1 else cv2.INTER_LINEAR,
        )
        if maske is not None:
            maske = cv2.resize(maske, (g.shape[1], g.shape[0]), interpolation=cv2.INTER_NEAREST)
    return g, maske, olcek


def sahne_ozniteligi_say(goruntu, maske=None) -> int:
    """Referans karede (maske DIŞINDA) kaç ORB özniteliği var — sahne denetimi yapılabilir mi."""
    g, m, _ = _gri_kucuk(goruntu, maske)
    kp = cv2.ORB_create(3000).detect(g, m)
    return len(kp)


def sahne_kaymasi(referans, kare, referans_maske=None, kare_maske=None, *, tam_genislik: int | None = None) -> dict:
    """Sabit sahnenin (plaka / fantom MASKELİ) referansa göre kayması — kameranın oynayıp oynamadığı.

    Maske: 255 = KULLAN, 0 = dışla. ORB + çapraz denetimli eşleme + RANSAC benzerlik dönüşümü; kayma = dönüşümün kare üzerindeki
    ızgara noktalarını taşıdığı ORTANCA mesafe, `tam_genislik` (kalibrasyon karesi genişliği; yoksa karenin kendi genişliği)
    pikseline ölçekli. Ölçülemezse `olculdu: False` (+ neden)."""
    g1, m1, _o1 = _gri_kucuk(referans, referans_maske)
    g2, m2, o2 = _gri_kucuk(kare, kare_maske)
    if tam_genislik:
        o2 = SAHNE_GENISLIK / float(tam_genislik)
    if g1.shape != g2.shape:
        return {"olculdu": False, "neden": "boyut_farkli"}
    orb = cv2.ORB_create(3000)
    k1, d1 = orb.detectAndCompute(g1, m1)
    k2, d2 = orb.detectAndCompute(g2, m2)
    if d1 is None or d2 is None or len(k1) < SAHNE_ASGARI_ESLESME or len(k2) < SAHNE_ASGARI_ESLESME:
        return {"olculdu": False, "neden": "az_oznitelik", "oznitelik": [len(k1 or []), len(k2 or [])]}
    es = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True).match(d1, d2)
    if len(es) < SAHNE_ASGARI_ESLESME:
        return {"olculdu": False, "neden": "az_eslesme", "eslesme": len(es)}
    src = np.float32([k1[m.queryIdx].pt for m in es]).reshape(-1, 1, 2)
    dst = np.float32([k2[m.trainIdx].pt for m in es]).reshape(-1, 1, 2)
    M, inl = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC, ransacReprojThreshold=3.0, maxIters=4000)
    n_inl = int(inl.sum()) if inl is not None else 0
    if M is None or n_inl < SAHNE_ASGARI_ESLESME:
        return {"olculdu": False, "neden": "az_eslesme", "eslesme": n_inl}
    hh, ww = g1.shape[:2]
    xs, ys = np.meshgrid(np.linspace(0, ww - 1, 9), np.linspace(0, hh - 1, 6))
    P = np.stack([xs.ravel(), ys.ravel(), np.ones(xs.size)], axis=1)
    Q = P @ M.T
    # Tam çözünürlük pikseline: KARENİN küçültme oranı (referans diske zaten küçük yazılır → onun oranı 1'dir).
    d = np.linalg.norm(Q - P[:, :2], axis=1) / o2
    return {
        "olculdu": True,
        "kayma_px": round(float(np.median(d)), 2),
        "en_buyuk_px": round(float(d.max()), 2),
        "eslesme": n_inl,
        "esik_px": SAHNE_KAYMA_ESIGI_PX,
        "gecti": bool(float(np.median(d)) <= SAHNE_KAYMA_ESIGI_PX),
    }


def cokgen_maskesi(boyut, cokgenler, *, genislet_px: int = 0) -> np.ndarray:
    """`boyut` (w, h) karede verilen çokgenlerin İÇİ 0, dışı 255 (sahne denetimi maskesi)."""
    w, h = (int(v) for v in boyut)
    m = np.full((h, w), 255, np.uint8)
    for c in cokgenler:
        cc = np.asarray(c, dtype=np.float64).reshape(-1, 2)
        if cc.size == 0:
            continue
        cv2.fillPoly(m, [np.round(cc).astype(np.int32)], 0)
    if genislet_px > 0:
        m = cv2.erode(m, np.ones((2 * genislet_px + 1,) * 2, np.uint8))
    return m


def fantom_boyu(harita: DuzlemHaritasi, kontur_px, y_mm: float) -> tuple[float, float] | None:
    """Fantom konturunu (DÜZELTİLMİŞ kare) üst yüzey düzlemine eşle → en küçük çevreleyen dikdörtgen (uzun, kısa) mm."""
    pts = np.asarray(kontur_px, dtype=np.float64).reshape(-1, 2)
    if len(pts) < 3:
        return None
    adim = max(1, len(pts) // 200)
    mm = []
    for p in pts[::adim]:
        try:
            q = harita.kabin_noktasi(p, y_mm, kabin_siniri=False)
        except KesisimGecersiz:
            return None
        mm.append([q[0], q[2]])
    (_c, (a, b), _ang) = cv2.minAreaRect(np.asarray(mm, dtype=np.float32))
    return (float(max(a, b)), float(min(a, b)))


# ── dosya ───────────────────────────────────────────────────────────────────────────────────────────────────────────────
def klasor(veri_koku) -> Path:
    return Path(veri_koku) / KLASOR


def _kanonik(d: dict) -> bytes:
    return json.dumps({k: v for k, v in d.items() if k != "butunluk"}, sort_keys=True, ensure_ascii=False).encode("utf-8")


def butunluk(d: dict) -> str:
    return hashlib.sha256(_kanonik(d)).hexdigest()


def _atomik_yaz(yol: Path, veri: bytes) -> None:
    yol.parent.mkdir(parents=True, exist_ok=True)
    fd, gecici = tempfile.mkstemp(dir=str(yol.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(veri)
            f.flush()
            os.fsync(f.fileno())
        os.replace(gecici, yol)
    except BaseException:
        try:
            os.unlink(gecici)
        except OSError:
            pass
        raise


def kaydet(veri_koku, kal: dict, referans_bgr=None, referans_maske=None) -> dict:
    """Kalibrasyonu (ve referans kareyi) VERİ KÖKÜNE atomik yaz. Referans önce yazılır, JSON onun SHA'sını taşır.

    `referans_bgr` BOZULMASI GİDERİLMİŞ karedir (`undistort_image`) — hatlar sahneyi düzeltilmiş karede karşılaştırır."""
    k = klasor(veri_koku)
    kal = dict(kal)
    if referans_bgr is not None:
        g, m, _ = _gri_kucuk(referans_bgr, referans_maske)
        if m is not None:
            g = g.copy()
            g[m == 0] = 0  # plaka bölgesi saklanmaz (her karede maskelenir); sıfır = "dışla" işareti
        ok, tampon = cv2.imencode(".png", g)
        if not ok:
            raise OSError("referans kare kodlanamadi")
        _atomik_yaz(k / REFERANS_ADI, tampon.tobytes())
        kal["referans"] = dict(kal.get("referans") or {})
        kal["referans"].update({"dosya": REFERANS_ADI, "sha256": hashlib.sha256(tampon.tobytes()).hexdigest()})
    kal["surum"] = SURUM
    kal["butunluk"] = butunluk(kal)
    _atomik_yaz(k / DOSYA_ADI, json.dumps(kal, ensure_ascii=False, indent=1).encode("utf-8"))
    _onbellek.clear()
    return kal


#: (yol, mtime_ns, boyut) → (kal | None, hata | None). Her karede diskten okumamak için.
_onbellek: dict = {}
_onbellek_kilit = threading.Lock()

ZORUNLU_ALANLAR = ("kamera", "ic_parametre", "R", "t_mm", "kabin_ext_cm", "duzlem_y_mm", "konumlar", "izdusum_hatasi_px")


def _dogrula_icerik(d) -> str | None:
    if not isinstance(d, dict):
        return "bicim"
    if d.get("surum") != SURUM:
        return "surum"
    if any(a not in d for a in ZORUNLU_ALANLAR):
        return "eksik_alan"
    if d.get("butunluk") != butunluk(d):
        return "butunluk"
    try:
        R = np.asarray(d["R"], dtype=np.float64).reshape(3, 3)
        t = np.asarray(d["t_mm"], dtype=np.float64).reshape(3)
        K = np.asarray(d["ic_parametre"]["K"], dtype=np.float64).reshape(3, 3)
        D = np.asarray(d["ic_parametre"]["D"], dtype=np.float64).ravel()
        w, h = int(d["kamera"]["genislik"]), int(d["kamera"]["yukseklik"])
        ext = [float(v) for v in d["kabin_ext_cm"]]
        y = float(d["duzlem_y_mm"])
        izd = float(d["izdusum_hatasi_px"])
    except (TypeError, ValueError, KeyError):
        return "bicim"
    if not (np.all(np.isfinite(R)) and np.all(np.isfinite(t)) and np.all(np.isfinite(K)) and np.all(np.isfinite(D))):
        return "sonlu_degil"
    if not _sonlu(y, izd, *ext) or w <= 0 or h <= 0 or len(ext) != 3:
        return "sonlu_degil"
    if abs(float(np.linalg.det(R)) - 1.0) > 1e-3 or float(np.abs(R @ R.T - np.eye(3)).max()) > 1e-3:
        return "donus_gecersiz"
    if izd > IZDUSUM_ESIGI_PX:
        return "izdusum_yuksek"
    return None


def yukle(veri_koku) -> tuple[dict | None, str | None]:
    """→ (kalibrasyon, None) · (None, None) = dosya YOK (ArUco kipi) · (None, hata kodu) = BOZUK (fail-closed: konum yok).

    Referans kare de denetlenir (SHA); okunursa `kal["_referans_gri"]` (bellekte, diske yazılmaz)."""
    yol = klasor(veri_koku) / DOSYA_ADI
    try:
        st = yol.stat()
    except FileNotFoundError:
        return None, None
    except OSError:
        return None, "okunamadi"
    try:
        rst = (klasor(veri_koku) / REFERANS_ADI).stat()
        ref_damga = (rst.st_mtime_ns, rst.st_size)
    except OSError:
        ref_damga = None  # referans silinmiş / yok — önbellek bunu da ayırt eder (bozuk referans GEÇERLİ sayılmasın)
    anahtar = (str(yol), st.st_mtime_ns, st.st_size, ref_damga)
    with _onbellek_kilit:
        if anahtar in _onbellek:
            return _onbellek[anahtar]
    try:
        d = json.loads(yol.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        sonuc = (None, "okunamadi")
    else:
        hata = _dogrula_icerik(d)
        if hata is None:
            ref = d.get("referans") or {}
            if ref.get("dosya"):
                rp = klasor(veri_koku) / str(ref["dosya"])
                try:
                    ham = rp.read_bytes()
                except OSError:
                    hata = "referans_yok"
                else:
                    if hashlib.sha256(ham).hexdigest() != ref.get("sha256"):
                        hata = "referans_butunluk"
                    else:
                        g = cv2.imdecode(np.frombuffer(ham, np.uint8), cv2.IMREAD_GRAYSCALE)
                        if g is None:
                            hata = "referans_okunamadi"
                        else:
                            d["_referans_gri"] = g
        sonuc = (d, None) if hata is None else (None, hata)
    with _onbellek_kilit:
        _onbellek.clear()
        _onbellek[anahtar] = sonuc
    return sonuc


def dogrulama_ekle(veri_koku, kayit: dict) -> dict | None:
    """Doğrulama sonucunu kalibrasyon dosyasına ekle (son 20). Dosya yok / bozuksa None."""
    kal, hata = yukle(veri_koku)
    if kal is None or hata:
        return None
    kal = {k: v for k, v in kal.items() if not k.startswith("_")}
    kal["dogrulamalar"] = (list(kal.get("dogrulamalar") or []) + [kayit])[-20:]
    return kaydet(veri_koku, kal)


def fantom_ayari_yaz(veri_koku, ayar: dict) -> dict | None:
    kal, hata = yukle(veri_koku)
    if kal is None or hata:
        return None
    kal = {k: v for k, v in kal.items() if not k.startswith("_")}
    kal["fantom"] = dict(ayar)
    return kaydet(veri_koku, kal)


def taban_yukseltmesi_mm(kal) -> float:
    """Kalibrasyondaki numune tabanı yükseltmesi (mm); yok → 0 (dosya bütünlük özetli — değer yazılırken sınırlandı)."""
    try:
        v = float(((kal or {}).get("numune_tabani") or {}).get("yukseltme_mm", 0.0))
    except (TypeError, ValueError, AttributeError):
        return 0.0
    return v if math.isfinite(v) and 0.0 <= v <= TABAN_YUKSELTME_AZAMI_MM else 0.0


def numune_tabani_yaz(veri_koku, ayar: dict) -> dict | None:
    kal, hata = yukle(veri_koku)
    if kal is None or hata:
        return None
    kal = {k: v for k, v in kal.items() if not k.startswith("_")}
    kal["numune_tabani"] = dict(ayar)
    return kaydet(veri_koku, kal)


def sahne_yenile(veri_koku, referans_bgr, referans_maske, kayit: dict) -> dict | None:
    """Sahip (KD-1) "kalibre etmeden devam": o anki kare YENİ sahne referansı olur; kayıt (`sahne_yenileme`) kuyu aralığı toleransını
    %10'a çıkarır ve her karede "kalibrasyon eski" uyarısı verdirir. Yeniden kalibrasyon bu alanı SİLER (yeni dosya)."""
    kal, hata = yukle(veri_koku)
    if kal is None or hata:
        return None
    kal = {k: v for k, v in kal.items() if not k.startswith("_")}
    oz = sahne_ozniteligi_say(referans_bgr, referans_maske)
    kal["referans"] = dict(kal.get("referans") or {})
    kal["referans"].update({"sahne_denetimi": bool(oz >= SAHNE_ASGARI_OZNITELIK), "oznitelik": int(oz)})
    kal["sahne_yenileme"] = dict(kayit)
    kal["sahne_yenilemeleri"] = (list(kal.get("sahne_yenilemeleri") or []) + [dict(kayit)])[-20:]
    return kaydet(veri_koku, kal, referans_bgr=referans_bgr, referans_maske=referans_maske)


def zaman_damgasi() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


_npz_sha_onbellek: dict = {}


def npz_sha256(yol) -> str | None:
    """İç parametre dosyasının SHA-256'sı (yol + mtime önbellekli). Okunamazsa None."""
    try:
        p = Path(yol)
        st = p.stat()
    except (OSError, TypeError):
        return None
    anahtar = (str(p), st.st_mtime_ns, st.st_size)
    if anahtar not in _npz_sha_onbellek:
        try:
            _npz_sha_onbellek[anahtar] = dosya_sha256(p)
        except OSError:
            return None
    return _npz_sha_onbellek[anahtar]


# ── kare başına denetim (petri v2 / fantom v3 hatları AYNI kuralı kullanır) ────────────────────────────────────────────────
#: Bu kodlardan biri sonuçta varsa konum KABİN çerçevesinde GEÇERSİZDİR (`pemf_valid` False, konum yok) — PEMF kapısı bunları
#: koşulsuz kipte de keser (`pemf_kapisi.FIZIKSEL`). Biçim hocanın uyarılarıyla aynı: `kod: açıklama`.
ENGEL_KODLARI = (
    "kalibrasyon_bozuk",
    "kalibrasyon_kamera_farkli",
    "kamera_oynamis",
    "fantom_ayari_yok",
    "fantom_boyu_farkli",
    "fantom_degil",
    "kor_bolge_on",
    "kor_bolge_arka",
    "kor_bolge_sol",
    "kor_bolge_sag",
)


def fantom_koyuluk_orani(kare_bgr, govde_maske, tumor_maskeleri) -> float | None:
    """Tümör bölgelerinin ortanca parlaklığı (HSV V) / gövdenin (tümörler hariç) ortanca parlaklığı. Ölçülemezse None."""
    hsv_v = cv2.cvtColor(kare_bgr, cv2.COLOR_BGR2HSV)[..., 2]
    tum = np.zeros(hsv_v.shape, dtype=bool)
    for m in tumor_maskeleri:
        if m is not None and getattr(m, "shape", None) == hsv_v.shape:
            tum |= m > 0
    if govde_maske is None or getattr(govde_maske, "shape", None) != hsv_v.shape or not tum.any():
        return None
    halka = cv2.dilate(tum.astype(np.uint8), np.ones((9, 9), np.uint8)) > 0
    govde = (govde_maske > 0) & ~halka
    if govde.sum() < 50:
        return None
    gv = float(np.median(hsv_v[govde]))
    return float(np.median(hsv_v[tum])) / gv if gv > 0 else None


class KareDurumu:
    """Bir karenin sabit düzlem kipindeki durumu: harita (geçerliyse) + ENGEL (fail-closed) + bilgi uyarıları + ölçümler."""

    def __init__(self, kal: dict | None):
        self.kal = kal
        self.harita: DuzlemHaritasi | None = None
        self.engeller: list[str] = []
        self.uyarilar: list[str] = []
        self.olcum: dict = {}

    @property
    def gecerli(self) -> bool:
        return self.harita is not None and not self.engeller

    @property
    def eski(self) -> bool:
        """Sahip (KD-1) "kalibre etmeden devam" edildi mi (sahne yenilendi; konum ~1–2 cm sapabilir)."""
        return bool((self.kal or {}).get("sahne_yenileme"))

    @property
    def kuyu_araligi_toleransi(self) -> float:
        return KUYU_ARALIGI_TOLERANSI_ESKI if self.eski else KUYU_ARALIGI_TOLERANSI

    def engel(self, kod: str, aciklama: str) -> None:
        self.engeller.append(f"{kod}: {aciklama}")

    def ozet(self) -> dict:
        kal = self.kal or {}
        return {
            "kip": "sabit_duzlem",
            "gecerli": self.gecerli,
            "tarih": kal.get("tarih"),
            "izdusum_hatasi_px": kal.get("izdusum_hatasi_px"),
            "lens_farki_mm": kal.get("lens_farki_mm"),
            "eski": self.eski,
            "taban_yukseltmesi_mm": taban_yukseltmesi_mm(kal),
            "engeller": [e.split(":", 1)[0] for e in self.engeller],
            "olcum": dict(self.olcum),
        }


def _kimlik_metni(k: dict) -> str:
    return f"{k.get('ad') or '?'} ({k.get('vidpid') or '?'})"


def kimlik_ayni(a: dict | None, b: dict | None) -> bool | None:
    """Kamera kimliği (ad + VID/PID) aynı mı; ikisinden biri bilinmiyorsa None (karşılaştırılamaz). Aygıt YOLU (USB girişi) burada
    karşılaştırılmaz: aynı kamera başka girişe takılınca kalibrasyon geçerli kalır (kamera açılırken yol önceliklidir — `kabin_kamerasi`)."""
    if not a or not b or not a.get("vidpid") or not b.get("vidpid"):
        return None
    return str(a.get("ad") or "").strip().lower() == str(b.get("ad") or "").strip().lower() and str(
        a["vidpid"]
    ).upper() == str(b["vidpid"]).upper()


def kare_hazirla(durum, *, kare_boyutu, kamera_indeksi=None, npz_sha=None, kamera_kimligi=None) -> KareDurumu:
    """`yukle()` çıktısı (kal, hata) + karenin boyutu / kamera kimliği (yoksa indeksi) / iç parametre SHA'sı → `KareDurumu`.

    Kalibrasyon BOZUK ya da kamera / çözünürlük / iç parametre FARKLI ise harita KURULMAZ (konum üretilmez). Kimlik (ad + VID/PID)
    iki tarafta da biliniyorsa İNDEKS karşılaştırılmaz (MSMF sırası değişebilir — KD-1'de Pusat 1 → 0 oldu)."""
    kal, hata = durum if durum else (None, None)
    kd = KareDurumu(kal)
    if hata:
        kd.engel("kalibrasyon_bozuk", f"kalibrasyon dosyasi okunamadi ya da bozuk ({hata})")
        return kd
    if kal is None:
        kd.engel("kalibrasyon_bozuk", "kalibrasyon yok")
        return kd
    w, h = (int(v) for v in kare_boyutu)
    kw, kh = int(kal["kamera"]["genislik"]), int(kal["kamera"]["yukseklik"])
    if (w, h) != (kw, kh):
        kd.engel("kalibrasyon_kamera_farkli", f"kare {w}x{h}, kalibrasyon {kw}x{kh}")
        return kd
    kk = kal["kamera"].get("kimlik")
    ayni = kimlik_ayni(kamera_kimligi, kk)
    if ayni is False:
        kd.engel(
            "kalibrasyon_kamera_farkli",
            f"secili kamera {_kimlik_metni(kamera_kimligi)}, kalibrasyon kamerasi {_kimlik_metni(kk)}",
        )
        return kd
    ki = kal["kamera"].get("indeks")
    if ayni is None and kamera_indeksi is not None and ki is not None and int(kamera_indeksi) != int(ki):
        kd.engel("kalibrasyon_kamera_farkli", f"secili kamera {kamera_indeksi}, kalibrasyon kamerasi {ki}")
        return kd
    ks = (kal.get("ic_parametre") or {}).get("sha256")
    if npz_sha is not None and ks and npz_sha != ks:
        kd.engel("kalibrasyon_kamera_farkli", "ic parametre dosyasi (K / D) kalibrasyondakinden farkli")
        return kd
    kd.harita = DuzlemHaritasi(kal)
    if kd.eski:
        y = kal.get("sahne_yenileme") or {}
        kd.uyarilar.append(
            f"kalibrasyon_eski: kamera oynadiktan sonra kalibre etmeden devam edildi ({y.get('tarih', '?')}, sahne "
            f"{y.get('kayma_px', '?')} px) - konum ~1-2 cm sapabilir; yeniden kalibre edin"
        )
    return kd


def sahne_denetle(kd: KareDurumu, kare_duzeltilmis_bgr, dislanan_cokgenler=(), *, genislet_px: int = 60) -> None:
    """Sabit sahne kayması (kamera oynadı mı). Referans yoksa / referansta öznitelik azsa yalnız UYARI; referans ölçülebilirken
    karede eşleşme yoksa ya da kayma eşiği aşıyorsa ENGEL (`kamera_oynamis`)."""
    if kd.harita is None or kd.kal is None:
        return
    ref = kd.kal.get("_referans_gri")
    ref_bilgi = kd.kal.get("referans") or {}
    if ref is None or not ref_bilgi.get("sahne_denetimi", False):
        kd.uyarilar.append("sahne_denetimi_yok: kalibrasyon karesinde sabit sahne yeterli degil - kamera kaymasi yalniz kuyu araligindan")
        return
    h, w = kare_duzeltilmis_bgr.shape[:2]
    kare_maske = cokgen_maskesi((w, h), dislanan_cokgenler, genislet_px=genislet_px)
    ref_maske = (ref > 0).astype(np.uint8) * 255
    ref_maske = cv2.erode(ref_maske, np.ones((7, 7), np.uint8))
    s = sahne_kaymasi(
        ref, kare_duzeltilmis_bgr, referans_maske=ref_maske, kare_maske=kare_maske, tam_genislik=int(kd.kal["kamera"]["genislik"])
    )
    kd.olcum["sahne"] = s
    if not s.get("olculdu"):
        kd.engel("kamera_oynamis", f"sabit sahne kalibrasyon karesiyle eslesmedi ({s.get('neden')})")
    elif not s.get("gecti"):
        kd.engel("kamera_oynamis", f"sabit sahne {s['kayma_px']} px kaymis (esik {SAHNE_KAYMA_ESIGI_PX:g})")
