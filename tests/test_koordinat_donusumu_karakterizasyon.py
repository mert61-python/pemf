# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""FANTOM/PETRİ KOORDİNAT DÖNÜŞÜMÜ — KARAKTERİZASYON GOLDEN'I (2026-09-08).

BU DOSYA DOĞRULUK İDDİA ETMEZ. `phantom_cv`/`petri_cv` `pixel_to_cabin_mm`in BUGÜN ne
ürettiğini sabitler ki dönüşüm değiştiğinde bu SESSİZ olmasın.

NEDEN GEREKLİ (docs/arastirma-ai-pro-fantom-petri-plani.md, karar #6 — hoca):
  · `coord_transform.py` ArUco modunda marker→kabin ROTASYONUNU uygulamıyor (`ray_cabin =
    ray_marker`; kodun kendi yorumu bunu kısıt olarak itiraf ediyor) ve kesişimi kabin
    Z=`plate_z` düzleminde alıyor.
  · Kedi hattı (cat_organ) kabin-merkezli PnP kullanıyor. İki hattın AYNI 3B çerçeveyi ürettiği
    KANITLANMADI → araştırma AI Pro'da fantom/petri sürüşü tezgâh doğrulaması geçene kadar
    bayrak arkasında kalır.
  · Dönüşüm YAMALANIRSA yalnız AI Pro değil, BUGÜN KULLANILAN AI Hub tek-foto analizleri
    (`/api/ai/vision/em_fantom`, `/api/ai/vision/em_petri`) ve Docker `ai_service` de kayar —
    aynı fonksiyon. Değişim CHANGELOG'a "araştırma fotoğraf analizi koordinatları değişti"
    olarak yazılmalı ve bu golden bilinçli güncellenmelidir.

Girdiler SENTETİKTİR (ağırlık/fotoğraf gerekmez) → bu kapı CI'da da koşar.
"""

import numpy as np
import pytest

_TOL_MM = 1e-6


@pytest.fixture()
def donusum():
    from ai_hub.inference_em_fantom.phantom_cv import coord_transform as ct
    from ai_hub.inference_em_fantom.phantom_cv.cabin_config import load_cabin_config

    cfg = load_cabin_config(None)  # depoya gömülü 2026-09-08 kabin geometrisi (65x50x50)
    intr = ct.CameraIntrinsics(
        K=np.array([[900.0, 0.0, 640.0], [0.0, 900.0, 360.0], [0.0, 0.0, 1.0]]),
        D=np.zeros((1, 5)),
        image_size=(1280, 720),
        rms=0.0,
    )
    pose = ct.CabinPose(
        marker_id=0,
        rvec=np.zeros((3, 1)),
        tvec=np.array([[0.0], [0.0], [500.0]]),  # kamera markerdan 500 mm uzakta
        R=np.eye(3),  # marker kameraya paralel
        reproj_error_px=0.0,
        marker_pos_cabin_mm=np.array([245.0, -170.0, -250.0]),  # yaml qr_to_origin (24,5/-17/-25 cm)
    )
    return ct, cfg, intr, pose


# (piksel, bugün üretilen kabin mm) — 2026-09-08'de ölçüldü.
_GOLDEN = [
    ((640.0, 360.0), (245.000000, -170.000000, 0.0)),  # görüntü merkezi
    ((740.0, 360.0), (328.333333, -170.000000, 0.0)),  # +100 px sağ
    ((640.0, 460.0), (245.000000, -86.666667, 0.0)),  # +100 px aşağı
    ((300.0, 200.0), (-38.333333, -303.333333, 0.0)),  # sol üst
]


@pytest.mark.parametrize("px,beklenen", _GOLDEN)
def test_KARAKTERIZASYON_pixel_to_cabin_mm_bugunku_davranis(donusum, px, beklenen):
    """Golden değişirse KIRMIZI. Değişim bilinçliyse: bu tabloyu güncelleyin, iki kopyayı
    (phantom_cv + petri_cv) birlikte yamalayın ve CHANGELOG'a analiz etkisini yazın."""
    ct, cfg, intr, pose = donusum
    p = ct.pixel_to_cabin_mm(px, pose, intr, cfg)
    assert np.allclose(p, np.array(beklenen), atol=_TOL_MM), (
        f"koordinat dönüşümü değişti: {px} -> {p.tolist()} (golden {list(beklenen)}). "
        "Bu fonksiyon AI Hub fantom/petri FOTOĞRAF analizinde de kullanılıyor — mevcut sonuçlar "
        "kayar. Bilinçliyse golden'ı güncelleyin ve CHANGELOG'a yazın."
    )


def test_KARAKTERIZASYON_marker_rotasyonu_UYGULANMIYOR(donusum):
    """Kısıtın kendisi, açıkça ölçülür: marker'ın kabin içindeki YÖNELİMİ (R) değişse bile
    ray kabin eksenine döndürülmediği için sonuç yalnız kamera-ışını + öteleme ile belirlenir.

    Bu bir HATA RAPORU değil, mevcut sözleşmenin kaydıdır: `ray_cabin = ray_marker`. Rotasyon
    eklenirse (karar #6) bu test KIRMIZI olur — tam da o zaman görülmesi istenen şey budur.
    """
    ct, cfg, intr, pose = donusum
    merkez = ct.pixel_to_cabin_mm((640.0, 360.0), pose, intr, cfg)

    # Marker'ı kendi normali etrafında 90 derece çevir: kabin çerçevesinde ışın DÖNMELİYDİ.
    aci = np.pi / 2
    R90 = np.array([[np.cos(aci), -np.sin(aci), 0.0], [np.sin(aci), np.cos(aci), 0.0], [0.0, 0.0, 1.0]])
    pose_dondurulmus = ct.CabinPose(
        marker_id=pose.marker_id,
        rvec=pose.rvec,
        tvec=pose.tvec,
        R=R90,
        reproj_error_px=0.0,
        marker_pos_cabin_mm=pose.marker_pos_cabin_mm,
    )
    dondurulmus = ct.pixel_to_cabin_mm((740.0, 360.0), pose_dondurulmus, intr, cfg)
    duz = ct.pixel_to_cabin_mm((740.0, 360.0), pose, intr, cfg)

    assert not np.allclose(dondurulmus, duz, atol=1e-3), (
        "marker yönelimi sonucu hiç etkilemiyor — beklenmedik; kapıyı gözden geçirin"
    )
    assert abs(merkez[2] - cfg.phantom_plate.plate_z_mm) < _TOL_MM, (
        "kesişim düzlemi artık plate_z değil — hedef düzlemi yapılandırılabilir yapıldıysa "
        "(karar #6) bu kapıyı ve yaml'ı birlikte güncelleyin"
    )


def test_KRITIK_iki_kopya_BIREBIR_ayni(donusum):
    """`phantom_cv/coord_transform.py` ile `petri_cv/coord_transform.py` birebir aynı dosyadır.
    Ayrışırlarsa fantom ve petri AYNI kabinde FARKLI koordinat üretir ve bunu kimse fark etmez;
    plan da "iki kopyaya AYNI yama" diyor. MUTASYON: bir kopyaya satır ekleyin → KIRMIZI."""
    import filecmp
    from pathlib import Path

    kok = Path(__file__).resolve().parents[1]
    a = kok / "ai_hub" / "inference_em_fantom" / "phantom_cv" / "coord_transform.py"
    b = kok / "ai_hub" / "inference_petri_dish" / "petri_cv" / "coord_transform.py"
    assert a.exists() and b.exists(), f"koordinat dönüşümü kopyaları bulunamadı: {a}, {b}"
    assert filecmp.cmp(a, b, shallow=False), (
        "fantom ve petri koordinat dönüşümleri AYRIŞTI — aynı kabinde farklı 3B koordinat "
        "üretirler. Yamayı iki kopyaya da uygulayın (tek kaynak yapılana kadar)."
    )
