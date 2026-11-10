# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""SABİT DÜZLEM KALİBRASYONU — ArUco'suz kabin konumu (KD · sahip kararları Y258–Y261, 2026-11-10).

YÖNTEM (Y258): kamera üst kapağa SABİT; petri / fantom tabanda SABİT yükseklikte durur, yalnız kabin X / Z değişir. Bir kez:
24'lük plakanın 4 dış köşesi (ön-sol, ön-sağ, arka-sağ, arka-sol) sol camdan + ön camdan ölçülür ve o anki karede bu köşelere
dokunulur → kameranın KABİN çerçevesindeki duruşu (R, t) çözülür (K / D + 4 eş düzlemli nokta → `solvePnP` IPPE) ve VERİ KÖKÜNE
saklanır (uygulama güncellemesi ezmez). Sonra her karede piksel → ışın → hedef düzlemi → kabin mm; ArUco ARANMAZ (ArUco kodu
SİLİNMEDİ — dosya yoksa bugünkü ArUco kipi aynen çalışır).

Kabin çerçevesi (ürün kuralı, T2B): orijin iç hacmin merkezi, +X = önden bakanın SOLU, +Y yukarı, +Z arkaya. Ölçüm camların İÇ
yüzünden: X = ext_x/2 − sol, Y = −ext_y/2 + taban, Z = −ext_z/2 + ön (ext = `geometry.cabin_extent_cm`; bugün 55,5 × 35 × 40,5).

ÖLÇÜLEN İKİ KARAR (rapor `DENETIM\\KAMERA-DUZLEM.md` S-KD.1 / S-KD.2):
  * Köşe ölçüleri önce plakanın BİLİNEN dış dikdörtgenine (SBS 127,76 × 85,48 mm) oturtulur (Procrustes: yalnız yer + dönüş).
    Benzetim (gerçek M2 K/D, T2B kamera duruşu, 400 deneme): cetvel ±0,5 cm (σ 2,5 mm) okumasıyla HAM 4 köşede yeniden izdüşüm
    medyanı 5,8 px (%83'ü 3 px eşiğini aşar) ve lens 4,6 cm sapar; oturtunca 0,6 px (%0) ve lens ~5 mm — düzlemdeki hedef hatası
    iki yolda da ~2 mm. 3 px / 2 cm eşikleri ancak böyle anlamlıdır. Ölçümler dikdörtgenden RMS > `OLCUM_UYUM_ESIGI_MM` saparsa
    (bir köşe yanlış yazılmış / köşe sırası karışmış) RET.
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

SURUM = 1
#: Veri kökü altındaki klasör ve dosyalar (uygulama katmanı DEĞİL — güncelleme ezmez).
KLASOR = "kabin_kalibrasyonu"
DOSYA_ADI = "duzlem_kalibrasyonu.json"
REFERANS_ADI = "duzlem_referans.png"

#: Sahip (istem 44 §1a): yeniden izdüşüm hatası bunu aşarsa kalibrasyon REDDEDİLİR.
IZDUSUM_ESIGI_PX = 3.0
#: Sahip (istem 44 §1a): hesaplanan ↔ ölçülen lens farkı bunu aşarsa UYARI (kaydetmeden önce onay ister).
LENS_UYARI_ESIGI_MM = 20.0
#: Ölçülen köşelerin plaka dikdörtgeninden RMS sapması bunu aşarsa RET (cetvel ±0,5 cm → ~3 mm; 1 cm = kaba hata).
OLCUM_UYUM_ESIGI_MM = 10.0
#: Sahip (istem 44 §1c): eşlenen kuyu aralığı 19,3 mm'den bundan fazla saparsa kamera oynamış sayılır.
KUYU_ARALIGI_TOLERANSI = 0.03
#: Sabit sahne kayması (tam çözünürlük pikseli) bunu aşarsa kamera oynamış sayılır.
SAHNE_KAYMA_ESIGI_PX = 12.0
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
#: Sahip (istem 44 §4): doğrulama ölçütü — 2 köşede hedef ≤ 1 cm.
DOGRULAMA_ESIGI_MM = 10.0

#: SBS / ANSI SLAS 1-2004 plaka DIŞ ölçüsü (mm, uzun × kısa) — köşeler bu dikdörtgene oturtulur.
PLAKA_DIS_MM = {12: (127.76, 85.48), 24: (127.76, 85.48), 48: (127.76, 85.48), 96: (127.76, 85.48)}
#: Köşelere dokunulan nokta = plakanın ÜST kenarının dış köşesi (tepeden her köşede görünür; alt flanş uzak kenarda gizlenir).
#: Yükseklik tabandan; 24'lük plaka (kapaksız) ~20 mm — sahip ölçüp ekranda değiştirebilir.
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


def dikdortgene_oturt(olculen_xz_mm: np.ndarray, uzun_mm: float, kisa_mm: float):
    """Ölçülen 4 köşe (X, Z; sıra `KOSE_ADLARI`) → bilinen ölçülü dikdörtgene EN YAKIN yerleşim (yalnız öteleme + dönüş).

    Ön kenar (ön-sol → ön-sağ) ölçümde yan kenardan uzunsa plaka YATAY (uzun kenar sol↔sağ) kabul edilir, değilse DİKEY.
    @return (oturtulmuş (4, 2), köşe başına sapma mm (4,), RMS mm)."""
    P = np.asarray(olculen_xz_mm, dtype=np.float64).reshape(4, 2)
    on = float(np.linalg.norm(P[0] - P[1]))
    yan = float(np.linalg.norm(P[1] - P[2]))
    w, h = (uzun_mm, kisa_mm) if on >= yan else (kisa_mm, uzun_mm)
    # Şablon (X, Z): ön-sol (+X, −Z) · ön-sağ (−X, −Z) · arka-sağ (−X, +Z) · arka-sol (+X, +Z)
    Q = np.array([[w / 2, -h / 2], [-w / 2, -h / 2], [-w / 2, h / 2], [w / 2, h / 2]], dtype=np.float64)
    mp, mq = P.mean(axis=0), Q.mean(axis=0)
    A = (Q - mq).T @ (P - mp)
    U, _S, Vt = np.linalg.svd(A)
    Rm = (U @ Vt).T
    if np.linalg.det(Rm) < 0:  # yansıma YOK — köşe sırası ters dolanıyorsa uyum zaten kötüleşir (RET)
        Vt[-1] *= -1
        Rm = (U @ Vt).T
    fit = (Q - mq) @ Rm.T + mp
    sapma = np.linalg.norm(fit - P, axis=1)
    return fit, sapma, float(np.sqrt(np.mean(sapma**2)))


def _yeni_K(K, D, boyut) -> np.ndarray:
    """`coord_transform.undistort_image` ile AYNI yeni K (alpha 0) — hatlar düzeltilmiş karede çalışır."""
    w, h = (int(v) for v in boyut)
    yeni, _ = cv2.getOptimalNewCameraMatrix(np.asarray(K, np.float64), np.asarray(D, np.float64), (w, h), 0)
    return np.asarray(yeni, dtype=np.float64)


# ── kalibrasyon çözümü ───────────────────────────────────────────────────────────────────────────────────────────────────
def kalibrasyon_hesapla(
    *,
    kose_px,
    kose_olcum_cm,
    K,
    D,
    boyut,
    ext_cm,
    plaka_yuksekligi_mm: float = VARSAYILAN_PLAKA_YUKSEKLIGI_MM,
    plaka_dis_mm=PLAKA_DIS_MM[24],
    lens_cm=None,
) -> dict:
    """4 köşe (HAM kare pikseli, sıra `KOSE_ADLARI`) + köşe başına (sol_cm, on_cm) + K / D → kamera duruşu (KABİN çerçevesinde).

    @return {"gecerli": bool, "nedenler": [kod…], "lens_uyarisi": bool, …ölçümler}. `gecerli` False ise KAYDEDİLMEZ.
    Neden kodları: `girdi_gecersiz`, `olcum_tutarsiz`, `cozum_yok`, `kamera_duzlem_altinda`, `izdusum_yuksek`."""
    sonuc: dict = {"gecerli": False, "nedenler": [], "lens_uyarisi": False}
    try:
        px = np.asarray(kose_px, dtype=np.float64).reshape(4, 2)
        olc = np.asarray(kose_olcum_cm, dtype=np.float64).reshape(4, 2)
        K = np.asarray(K, dtype=np.float64).reshape(3, 3)
        D = np.asarray(D, dtype=np.float64).ravel()
        w, h = (int(v) for v in boyut)
        ext = [float(v) for v in ext_cm]
        ph = float(plaka_yuksekligi_mm)
    except (TypeError, ValueError):
        sonuc["nedenler"].append("girdi_gecersiz")
        return sonuc
    if (
        not np.all(np.isfinite(px))
        or not np.all(np.isfinite(olc))
        or not _sonlu(ph, *ext)
        or w <= 0
        or h <= 0
        or np.any(px < 0)
        or np.any(px[:, 0] > w)
        or np.any(px[:, 1] > h)
        or not (0.0 <= ph <= 100.0)
    ):
        sonuc["nedenler"].append("girdi_gecersiz")
        return sonuc
    duzlem_y = (-ext[1] / 2.0) * 10.0 + ph
    olculen = np.array([kabin_noktasi_mm(s, o, 0.0, ext)[[0, 2]] for s, o in olc])
    fit, sapma, rms = dikdortgene_oturt(olculen, float(plaka_dis_mm[0]), float(plaka_dis_mm[1]))
    sonuc.update(
        {
            "duzlem_y_mm": round(duzlem_y, 3),
            "olcum_uyumu_mm": round(rms, 2),
            "kose_olcum_sapmasi_mm": [round(float(v), 2) for v in sapma],
        }
    )
    if rms > OLCUM_UYUM_ESIGI_MM:
        sonuc["nedenler"].append("olcum_tutarsiz")
        return sonuc
    nesne = np.column_stack([fit[:, 0], np.full(4, duzlem_y), fit[:, 1]]).astype(np.float64)
    try:
        n, rvecs, tvecs, _hatalar = cv2.solvePnPGeneric(
            nesne.reshape(-1, 1, 3), px.reshape(-1, 1, 2), K, D, flags=cv2.SOLVEPNP_IPPE
        )
    except cv2.error:
        n, rvecs, tvecs = 0, [], []
    adaylar = []
    for rv, tv in zip(rvecs[: int(n)], tvecs[: int(n)]):
        try:
            rv, tv = cv2.solvePnPRefineLM(nesne.reshape(-1, 1, 3), px.reshape(-1, 1, 2), K, D, rv.copy(), tv.copy())
        except cv2.error:
            pass
        R, _ = cv2.Rodrigues(rv)
        C = (-R.T @ tv.reshape(3)).astype(np.float64)
        pp, _ = cv2.projectPoints(nesne.reshape(-1, 1, 3), rv, tv, K, D)
        e = np.linalg.norm(pp.reshape(-1, 2) - px, axis=1)
        adaylar.append((float(np.sqrt(np.mean(e**2))), e, rv.reshape(3), tv.reshape(3), R, C))
    if not adaylar:
        sonuc["nedenler"].append("cozum_yok")
        return sonuc
    # IPPE iki çözüm verir; kamera düzlemin ÜSTÜNDE olmalı (kapak) — altındaki çözüm ayna görüntüsüdür.
    ustte = [a for a in adaylar if a[5][1] > duzlem_y]
    if not ustte:
        sonuc["nedenler"].append("kamera_duzlem_altinda")
        return sonuc
    izd, e, rv, tv, R, C = min(ustte, key=lambda a: a[0])
    sonuc.update(
        {
            "izdusum_hatasi_px": round(izd, 3),
            "kose_izdusum_px": [round(float(v), 3) for v in e],
            "R": R.tolist(),
            "rvec": rv.tolist(),
            "t_mm": tv.tolist(),
            "kamera_konumu_mm": [round(float(v), 2) for v in C],
            "kose_kabin_mm": [[round(float(v), 2) for v in p] for p in nesne],
        }
    )
    if lens_cm is not None:
        try:
            L = kabin_noktasi_mm(lens_cm[0], lens_cm[1], lens_cm[2], ext)
        except (TypeError, ValueError, IndexError):
            L = None
        if L is not None and np.all(np.isfinite(L)):
            fark = float(np.linalg.norm(C - L))
            sonuc["olculen_lens_mm"] = [round(float(v), 2) for v in L]
            sonuc["lens_farki_mm"] = round(fark, 2)
            sonuc["lens_uyarisi"] = fark > LENS_UYARI_ESIGI_MM
        else:
            sonuc["nedenler"].append("girdi_gecersiz")
            return sonuc
    if izd > IZDUSUM_ESIGI_PX:
        sonuc["nedenler"].append("izdusum_yuksek")
        return sonuc
    sonuc["gecerli"] = True
    return sonuc


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
        self.K_yeni = _yeni_K(self.K, self.D, self.boyut)
        self._K_yeni_ters = np.linalg.inv(self.K_yeni)

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


def kuyu_araligi(harita: DuzlemHaritasi, H_img_from_plate, satir: int, sutun: int, aralik_mm: float, y_mm: float) -> dict:
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
        "gecti": bool(sapma <= KUYU_ARALIGI_TOLERANSI),
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

ZORUNLU_ALANLAR = ("kamera", "ic_parametre", "R", "t_mm", "kabin_ext_cm", "duzlem_y_mm", "koseler", "izdusum_hatasi_px")


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
            "engeller": [e.split(":", 1)[0] for e in self.engeller],
            "olcum": dict(self.olcum),
        }


def kare_hazirla(durum, *, kare_boyutu, kamera_indeksi=None, npz_sha=None) -> KareDurumu:
    """`yukle()` çıktısı (kal, hata) + karenin boyutu / kamera indeksi / iç parametre SHA'sı → `KareDurumu`.

    Kalibrasyon BOZUK ya da kamera / çözünürlük / iç parametre FARKLI ise harita KURULMAZ (konum üretilmez)."""
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
    ki = kal["kamera"].get("indeks")
    if kamera_indeksi is not None and ki is not None and int(kamera_indeksi) != int(ki):
        kd.engel("kalibrasyon_kamera_farkli", f"secili kamera {kamera_indeksi}, kalibrasyon kamerasi {ki}")
        return kd
    ks = (kal.get("ic_parametre") or {}).get("sha256")
    if npz_sha is not None and ks and npz_sha != ks:
        kd.engel("kalibrasyon_kamera_farkli", "ic parametre dosyasi (K / D) kalibrasyondakinden farkli")
        return kd
    kd.harita = DuzlemHaritasi(kal)
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
