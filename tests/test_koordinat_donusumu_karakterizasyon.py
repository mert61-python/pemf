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

    cfg = load_cabin_config(None)  # depoya gömülü kabin geometrisi (65x50x50)
    # ⚠️ GOLDEN DÜZLEMİ SABİTLENİR: bu dosya DÖNÜŞÜMÜ karakterize eder, sahadaki hedef düzlemi
    # seçimini DEĞİL. 2026-09-09'da yaml "Y / -20 cm"e (sahip ölçüsü: tabandan 5 cm) geçti; o
    # düzlemde sentetik ışınlar düzleme neredeyse PARALEL olduğu için sonuç 10^6 mm'ye fırlıyor
    # (aşağıdaki ayrı karakterizasyon bunu ölçer). Dönüşümün kendisi eski düzlemde ölçülmeye
    # devam eder ki gerçek bir regresyon bu gürültünün altında kaybolmasın.
    cfg.phantom_plate.hedef_duzlem_eksen = "Z"
    cfg.phantom_plate.hedef_duzlem_cm = 0.0
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
        # ⚠️ YAML'DAN TÜRETİLİR, elle yazılmaz: marker konumu = -qr_to_origin (cm -> mm).
        # 2026-09-09'da işaret 15 cm'e çıkınca köşe yerleşimi 8/8 -> 11/11 cm taşındı; sabit yazılsaydı
        # golden yaml'dan sessizce ayrışırdı.
        marker_pos_cabin_mm=np.array([-float(v) * 10.0 for v in cfg.geometry.qr_to_origin_cm]),
    )
    return ct, cfg, intr, pose


# (piksel, bugün üretilen kabin mm) — kesişim düzlemi "Z"/0 cm'de SABİTLENMİŞ fixture ile.
# ⚠️ YENİDEN TEMELLENDİ 2026-09-09 (sahip ölçüsü): kabin işareti 10 -> 15 cm büyüdü ve köşe
# yerleşimi 8/8 -> 11/11 cm taşındı (15 cm'lik işaretin sessiz bölgesi 8 cm'lik merkezde duvardan
# taşıyordu). Marker konumu (-21,5 / +14 / +25 cm) değiştiği için TÜM golden değerleri kaydı —
# dönüşüm mantığı DEĞİŞMEDİ. Önceki temel: marker (-24,5 / +17 / +25) cm.
# ⚠️ Sahip notu (2026-09-09): kamera ile fantom/petri konumları SAHADA tekrar düzeltilecek →
# bu tablo o ölçümden sonra bir kez daha yeniden temellenecektir.
_GOLDEN = [
    ((640.0, 360.0), (-215.000000, 140.000000, 0.0)),  # görüntü merkezi = marker merkezi hizası
    ((740.0, 360.0), (-187.222222, 140.000000, 0.0)),  # +100 px sağ
    ((640.0, 460.0), (-215.000000, 112.222222, 0.0)),  # +100 px aşağı
    ((300.0, 200.0), (-309.444444, 184.444444, 0.0)),  # sol üst
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


def test_KRITIK_marker_KABIN_rotasyonu_UYGULANIR(donusum):
    """Karar #6 sonrası: marker çerçevesinden kabin çerçevesine İŞARET/PERMUTASYON dönüşümü
    uygulanır. Marker arka duvarda (normal −Z) ve "üst" oku tavana baktığında beklenen matris
    diag(−1, +1, −1)'dir: eksenler hizalı, X ve Z İŞARETLERİ ters.

    Eskiden `ray_cabin = ray_marker` (birim matris) yazılıydı → ışın ters yöne gidiyor ve kesişim
    yanlış noktada bulunuyordu. MUTASYON: `R_axis`i birim matrise döndürün → KIRMIZI."""
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
    # ⚠️ KULLANIMI ölç, varlığı değil: matrisi doğrulamak yetmiyordu — `pixel_to_cabin_mm` içindeki
    # çağrıyı birim matrise çeviren mutasyon bu kapıdan GEÇİYORDU (ölçüldü). Marker normalini
    # değiştirmek sonucu DEĞİŞTİRMELİ; değişmiyorsa dönüşüm ışına uygulanmıyor demektir.
    eski_normal = cfg.aruco.normal_axis_in_cabin
    try:
        cfg.aruco.normal_axis_in_cabin = "+X"
        farkli_normal = ct.pixel_to_cabin_mm((740.0, 360.0), pose, intr, cfg)
    finally:
        cfg.aruco.normal_axis_in_cabin = eski_normal
    assert not np.allclose(farkli_normal, duz, atol=1e-3), (
        "marker normali değiştiği hâlde sonuç aynı — marker→kabin dönüşümü ışına UYGULANMIYOR "
        "(eski `ray_cabin = ray_marker` davranışı geri gelmiş olabilir)"
    )

    beklenen_R = np.diag([-1.0, 1.0, -1.0])
    assert np.allclose(ct._marker_to_cabin_R(cfg), beklenen_R, atol=1e-9), (
        f"marker→kabin dönüşümü beklenen diag(-1,1,-1) değil: {ct._marker_to_cabin_R(cfg).tolist()} "
        "— marker arka duvarda (normal -Z) ve üst oku tavana bakıyor varsayımı bozulduysa "
        "KABIN_KURULUM_KILAVUZU ile birlikte gözden geçirin"
    )
    assert abs(merkez[cfg.phantom_plate.hedef_duzlem_indeksi] - cfg.phantom_plate.hedef_duzlem_mm) < _TOL_MM, (
        "kesişim yapılandırılan hedef düzleminde değil — yaml `hedef_duzlem_eksen`/`hedef_duzlem_cm` "
        "ile kod ayrışmış olabilir"
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


def test_KRITIK_hedef_duzlemi_YAPILANDIRILABILIR(donusum):
    """Karar #6: fantom/petri kabinde YATAY duruyorsa doğru kesişim düzlemi "Y = taban + kalınlık"
    olmalı; eski kod her zaman kabin Z=0 (DİKEY orta düzlem) ile kesişiyordu.

    Bu kapı yaml'ın DEĞERİNİ değil, kodun o değeri GERÇEKTEN kullandığını ölçer (yaml şu an eski
    davranışta bırakıldı: yatay düzlem mevcut kamera konumuyla sayısal olarak dayanıksız).
    MUTASYON: kesişimi sabit `plate_z`/eksen 2'ye döndürün → KIRMIZI."""
    ct, cfg, intr, pose = donusum

    cfg.phantom_plate.hedef_duzlem_eksen = "Y"
    cfg.phantom_plate.hedef_duzlem_cm = -24.0
    yatay = ct.pixel_to_cabin_mm((640.0, 460.0), pose, intr, cfg)
    assert abs(yatay[1] - (-240.0)) < 1e-6, (
        f"yatay düzlem yapılandırması uygulanmadı: Y={yatay[1]} (beklenen -240 mm) — yatay yerleşimde "
        "hedef kabin ortasındaki dikey perdeye yansıtılır ve konum yanlış çıkar"
    )

    cfg.phantom_plate.hedef_duzlem_eksen = "Z"
    cfg.phantom_plate.hedef_duzlem_cm = 0.0
    dikey = ct.pixel_to_cabin_mm((640.0, 460.0), pose, intr, cfg)
    assert abs(dikey[2] - 0.0) < 1e-6, "eksen 'Z' seçilince eski davranış (dikey orta düzlem) dönmüyor"
    assert not np.allclose(yatay, dikey), "iki düzlem aynı sonucu veriyor — yapılandırma etkisiz"


def test_KRITIK_yaml_ve_parser_hedef_duzlemini_TASIYOR():
    """Yaml'a alan eklemek yetmez: `cabin_config.py` ayrıştırıcısı onu OKUMALI (bilinmeyen anahtar
    sessizce yok sayılır). İki kopya da taşımalı. MUTASYON: parser satırını silin → KIRMIZI."""
    from pathlib import Path

    kok = Path(__file__).resolve().parents[1]
    for kok_dizin in ("inference_em_fantom/phantom_cv", "inference_petri_dish/petri_cv"):
        cfg_src = (kok / "ai_hub" / kok_dizin / "cabin_config.py").read_text(encoding="utf-8")
        yaml_src = (kok / "ai_hub" / kok_dizin / "cabin_config_example.yaml").read_text(encoding="utf-8")
        assert "hedef_duzlem_eksen" in yaml_src, f"{kok_dizin}: yaml hedef düzlemi taşımıyor"
        assert 'plate_r.get("hedef_duzlem_eksen"' in cfg_src, (
            f"{kok_dizin}: ayrıştırıcı yaml'daki hedef düzlemini OKUMUYOR — alan sessizce yok sayılır"
        )
        assert "hedef_duzlem_mm" in cfg_src and "hedef_duzlem_indeksi" in cfg_src, (
            f"{kok_dizin}: yapılandırma sınıfı düzlem yardımcılarını sunmuyor"
        )


def test_KARAKTERIZASYON_SAHADAKI_yatay_duzlem_KOTU_KOSULLANMIS(donusum):
    """ÖLÇÜM KAYDI (2026-09-09): sahaya yazılan hedef düzlemi (tabandan 5 cm = kabin `Y = -20` cm)
    mevcut kamera konumuyla SAYISAL OLARAK DAYANIKSIZ.

    Kamera lensi taban hizasında (Y = -25 cm); hedef düzlemi onun yalnız 5 cm üstünde. Işın düzlemi
    çok sığ bir açıyla keser → küçük piksel hatası metrelere döner. Sentetik ışınlarda kesişim
    10^6 mm'ye fırlıyor, gerçek ArUco'lu fotoğrafta kuyu (-48,3 · -20,0 · +445,4) cm = KABİN DIŞI.

    ⚠️ BU KAPI BİLİNÇLİDİR ve bir HEDEFİ değil bir DURUMU sabitler: `PEMF_ARASTIRMA_AIPRO`ın neden
    0 kaldığının ölçülmüş gerekçesidir. Sahada kamera/hedef konumu düzeltilince (sahip notu) bu
    test KIRMIZI olacak — o zaman düzeltmenin İŞE YARADIĞI anlaşılır ve kapı yenilenir.
    Ayrıntı: ai_hub/KABIN_KURULUM_KILAVUZU.md §0.5 · docs/VERIFICATION.md §15.
    """
    ct, cfg, intr, pose = donusum
    cfg.phantom_plate.hedef_duzlem_eksen = "Y"
    cfg.phantom_plate.hedef_duzlem_cm = -20.0

    p = ct.pixel_to_cabin_mm((740.0, 360.0), pose, intr, cfg)

    kabin_yarim = [float(v) * 10.0 / 2 for v in cfg.geometry.cabin_extent_cm]
    disarida = any(abs(float(p[i])) > kabin_yarim[i] for i in range(3))
    assert disarida, (
        f"yatay düzlem artık kabin İÇİNDE sonuç veriyor: {p.tolist()} — kamera/hedef konumu "
        "düzeltilmiş olabilir. Ölçümü tekrarlayıp bu kapıyı ve KABIN_KURULUM_KILAVUZU §0.5'i "
        "güncelleyin; bayrak açılabilir hâle gelmiş olabilir."
    )
