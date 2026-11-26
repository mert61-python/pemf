# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""KEDİ HEDEF DÜZLEMİ (istem 58 FK · K1 — KD-3b'nin kedi karşılığı): ArUco'suz kabinde organın kabin konumu SABİT DÜZLEM kalibrasyonundan.

Neden: kabin kamerası üst kapakta, kabinde ArUco işareti YOK (KD · Y258 — petri / fantom konumu `cv_ortak.sabit_duzlem`den). Kedi hattının
kabin koordinatı ise yalnız ArUco + perspektif çözümünden geliyordu → sabit düzlem kalibrasyonlu kabinde organlar HEP kalibrasyonsuz kaldı
(güven tavanı 0,25 < AI Pro eşiği 0,3): AI Pro kediyi bulsa da hedefi hiç lokalize edemiyordu (K1 çevrimdışı ölçümü, K0 peluş kaydı).

Yöntem: organ pikseli (ham kare) → ışın → yatay HEDEF DÜZLEMİ (Y = numune tabanı + organ yüksekliği) → kabin mm. Organ yüksekliği:
kedi tabanda YÜZÜSTÜ yatar varsayımı (karın alt yüzü yerde) → kanonik atlasta organın karın alt yüzünden yüksekliği × ölçek k.
Ölçek ÖLÇÜLÜR (yanlış ölçek SESSİZ kayar: üstten kamerada yükseklik hatası yatay kaymaya döner): k = Procrustes ölçeği (piksel / kanonik
cm) ÷ düzlemin gövde merkezindeki piksel / cm'si (gövde orta yüksekliğinde, iki tur). `classify_pose` YAN kamera fotoğrafı içindir — üstten
kabin karesinde duruşu söylemez, burada KULLANILMAZ. k kedi aralığı dışındaysa (`OLCEK_ARALIGI`) konum ÜRETİLMEZ (fail-closed).

Saf geometri: `harita` `cv_ortak.sabit_duzlem.DuzlemHaritasi` arayüzüdür (`kabin_noktasi`, `piksel`, `taban_y_mm`); bu modül onu içe AKTARMAZ
(CLI `lib`i tek başına da yükler). Bir HEDEF GEÇERLİLİK hesabıdır — doz kıskacı değil (Ö.4-Y9), ACİL DURDUR'a dokunmaz (Ö.4-Y8).
"""
from __future__ import annotations

import math

import numpy as np

#: Kanonik kedide karın alt yüzü (`CANONICAL_CAT_3D["belly_bottom"]` y) — yüzüstü yatışta zemine değen yüz (cm).
KARIN_Y_CM = -5.5
#: Gövde orta yüksekliği (karından sırta 11 cm'nin yarısı) — ölçek bu yükseklikteki düzlemde ölçülür (cm, kanonik).
GOVDE_ORTA_CM = 5.5
#: Ölçülen ölçeğin kabul aralığı (kanonik = 29 cm burun → kuyruk kökü yetişkin kedi). Dışında konum üretilmez.
OLCEK_ARALIGI = (0.25, 2.0)
#: Ölçek ölçümünde düzlemde atılan adım (mm) — X ve Z yönünde.
_ADIM_MM = 10.0


def duzlem_piksel_cm(harita, px, y_mm: float) -> float:
    """Ham karedeki `px` noktasının `y_mm` yüksekliğindeki yatay düzlemde 1 cm'nin piksel boyu (X ve Z yönü ortalaması)."""
    P = np.asarray(harita.kabin_noktasi(px, y_mm, duzeltilmis=False, kabin_siniri=False), dtype=np.float64)
    p0 = np.asarray(harita.piksel(P, duzeltilmis=False), dtype=np.float64)
    d = []
    for e in (np.array([_ADIM_MM, 0.0, 0.0]), np.array([0.0, 0.0, _ADIM_MM])):
        d.append(float(np.linalg.norm(np.asarray(harita.piksel(P + e, duzeltilmis=False), dtype=np.float64) - p0)))
    return float(np.mean(d)) * (10.0 / _ADIM_MM)


def organ_kabin_konumlari(harita, organ_px, organ_y_cm, olcek_px_cm: float, merkez_px) -> dict:
    """Organ pikselleri (N, 2) + kanonik organ y'leri (N,) + Procrustes ölçeği → {"olcek", "duzlem_px_cm", "konumlar_mm" (N; kabin mm
    ya da None), "yukseklik_mm" (N; tabandan ya da None), "neden" (None | "olcek_disi" | "kesisim_yok")}.

    Organ ışını düzlemi geçerli bir yerde kesmezse (kabin dışı, kameranın arkası) o organın konumu None (çağıran kalibrasyonsuz sayar)."""
    n = len(organ_y_cm)
    bos = {"olcek": None, "duzlem_px_cm": None, "konumlar_mm": [None] * n, "yukseklik_mm": [None] * n}
    taban = float(harita.taban_y_mm)
    try:
        s = float(olcek_px_cm)
        y0 = taban + GOVDE_ORTA_CM * 10.0
        k = pxcm = None
        for _ in range(2):
            pxcm = duzlem_piksel_cm(harita, merkez_px, y0)
            k = s / pxcm
            y0 = taban + k * GOVDE_ORTA_CM * 10.0
    except (ValueError, ZeroDivisionError, TypeError):
        return {**bos, "neden": "kesisim_yok"}
    if not (math.isfinite(k) and OLCEK_ARALIGI[0] <= k <= OLCEK_ARALIGI[1]):
        return {**bos, "olcek": k if math.isfinite(k) else None, "duzlem_px_cm": pxcm, "neden": "olcek_disi"}
    konumlar, yukseklik = [], []
    for px, y in zip(organ_px, organ_y_cm):
        h = max(0.0, float(y) - KARIN_Y_CM) * k * 10.0
        try:
            P = harita.kabin_noktasi((float(px[0]), float(px[1])), taban + h, duzeltilmis=False)
        except ValueError:  # `KesisimGecersiz` (kabin dışı / kameranın arkası / paralel)
            konumlar.append(None)
            yukseklik.append(None)
            continue
        konumlar.append(np.asarray(P, dtype=np.float64))
        yukseklik.append(h)
    neden = None if any(p is not None for p in konumlar) else "kesisim_yok"
    return {"olcek": k, "duzlem_px_cm": pxcm, "konumlar_mm": konumlar, "yukseklik_mm": yukseklik, "neden": neden}
