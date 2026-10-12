# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""AI-2 C1 — hocanın petri v2 `multiwell:` ve fantom v3 `phantom_v2:` bölümleri TEK UYGULAMADA (A2, plan §3.4).

NE GELDİ (Çağlar Hoca, `degisenler.zip` SHA-256 0285b1d969f8…, 2026-10-02): `petri_cv_v2/cabin_config.py` ve
`phantom_cv_v3/cabin_config.py` kendi KOPYALARINI getiriyordu. Ata (2026-08-26 teslimi) → v2/v3 farkı ÖLÇÜLDÜ:
yalnız EK — `MultiwellCfg` + `_multiwell` (46 satır) ve `PhantomV2Cfg` + `_phantom_v2` (66 satır); `coord_transform.py`
v2 = v3 = ata (değişmemiş). guii'de iki profil zaten `ai_hub/cv_ortak` kabuğu (A2) → kopya ALINMADI, iki bölüm
`cv_ortak/cabin_config.py`ye taşındı.

KAPI:
  · hocanın YAML bölümleri (metin aynen aşağıda) cv_ortak ile hocanın yükleyicisinin verdiği değerlere BİREBİR çözülür
    (beklenen değerler BURADA sabit — yükleyiciden OKUNMAZ; hocanın kendi yükleyicisiyle kâhin ağacında ölçüldü);
  · bölümü OLMAYAN eski profil YAML'ları aynen yüklenir (plate_type None = tekil petri kipi);
  · yeni sayısal alanlar D1.E07 kuralına tabidir: `.nan` / `.inf` YÜKLEMEDE reddedilir ve hata BOZUK ANAHTARI söyler.
"""

from __future__ import annotations

from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
PETRI_V2_YAML = KOK / "ai_hub" / "inference_petri_dish" / "petri_cv_v2" / "cabin_config_v2.yaml"
FANTOM_V3_YAML = KOK / "ai_hub" / "inference_em_fantom" / "phantom_cv_v3" / "cabin_config_v3.yaml"


def _bolumsuz(yol: Path, bolum: str) -> str:
    """Profil YAML'ının hocanın bölümü ÇIKARILMIŞ hâli = saha kabin çekirdeği (eski profil YAML'ı). AI-2 C6: v1 örnek
    YAML'ları (`petri_cv/`, `phantom_cv/cabin_config_example.yaml`) emekli; v2 / v3 YAML'ı = o çekirdek + hocanın bölümü."""
    satirlar = yol.read_text(encoding="utf-8").splitlines(keepends=True)
    i = next(n for n, x in enumerate(satirlar) if x.startswith(f"{bolum}:"))
    j = next((n for n in range(i + 1, len(satirlar)) if satirlar[n][:1].isalpha()), len(satirlar))
    metin = "".join(satirlar[:i] + satirlar[j:])
    assert f"\n{bolum}:" not in "\n" + metin, f"aparat: {bolum} bölümü çıkarılamadı"
    return metin


def _petri_taban() -> str:
    return _bolumsuz(PETRI_V2_YAML, "multiwell")


def _fantom_taban() -> str:
    return _bolumsuz(FANTOM_V3_YAML, "phantom_v2")


#: Hocanın `petri_cv_v2/cabin_config_v2.yaml` `multiwell:` bölümü (yorumlar atıldı); iki değer testte değiştirildi:
#: a1_cabin_mm (null → ölçülmüş örnek) ve kontrol kuyucukları (küçük harf → büyütülmeli).
HOCA_MULTIWELL = """
multiwell:
  plate_type: 24
  a1_corner: auto
  placement:
    a1_cabin_mm: [-48.25, 28.95, 0.0]
    col_axis_cabin: [1.0, 0.0, 0.0]
    row_axis_cabin: [0.0, -1.0, 0.0]
  cancer:
    frac: 0.02
    delta_b: 8.0
    abs_b: -5.0
    control_healthy: [a1, D6]
    control_cancer: [b2]
"""

#: Hocanın `phantom_cv_v3/cabin_config_v3.yaml` `phantom_v2:` bölümü (yorumlar atıldı); `axis_u` testte [0,-1,0].
HOCA_PHANTOM_V2 = """
phantom_v2:
  coil_ring:
    enabled: true
    diameter_mm: 184.0
  parallax:
    height_mm: 31.3
    focal_equiv_mm: 26.0
  layout_file: phantom_layout_2026-10-02.json
  placement:
    origin_cabin_mm: null
    x_axis_cabin: [0.0, 1.0, 0.0]
    y_axis_cabin: [0.0, 0.0, 1.0]
  cst_box:
    enabled: true
    center_mm: [-43.645, 0.215, 3.335]
    axis_u: [0.0, -1.0, 0.0]
    axis_v: [0.0, 0.0, 1.0]
  tumor:
    navy_s_min: 45
    navy_v_min: 20
    navy_a_max: 12
    core_v_max: 35
"""


def _yukle(tmp_path: Path, taban: str, ek: str, ad: str = "kabin.yaml"):
    from ai_hub.cv_ortak.cabin_config import load_cabin_config

    yol = tmp_path / ad
    yol.write_text(taban + "\n" + ek, encoding="utf-8")
    return load_cabin_config(yol)


def test_KRITIK_hoca_petri_v2_multiwell_bolumu_BIREBIR(tmp_path):
    c = _yukle(tmp_path, _petri_taban(), HOCA_MULTIWELL)
    m = c.multiwell
    assert m.plate_type == 24
    assert m.a1_corner == "auto"
    assert m.a1_cabin_mm == [-48.25, 28.95, 0.0]
    assert m.col_axis_cabin == [1.0, 0.0, 0.0] and m.row_axis_cabin == [0.0, -1.0, 0.0]
    assert (m.cancer_frac, m.cancer_db, m.cancer_abs_b) == (0.02, 8.0, -5.0)
    assert m.control_healthy == ["A1", "D6"] and m.control_cancer == ["B2"], (
        "kontrol kuyucukları büyük harfe çevrilmeli"
    )
    # Bölüm eklenince kabin çekirdeği (saha ölçüsü) DEĞİŞMEZ: aynı YAML'ın bölümsüz hâliyle aynı.
    t = _yukle(tmp_path, _petri_taban(), "", ad="taban.yaml")
    assert (c.aruco, c.geometry, c.phantom_plate, c.phantom) == (t.aruco, t.geometry, t.phantom_plate, t.phantom)


def test_KRITIK_hoca_fantom_v3_phantom_v2_bolumu_BIREBIR(tmp_path):
    c = _yukle(tmp_path, _fantom_taban(), HOCA_PHANTOM_V2)
    v = c.phantom_v2
    assert v.ring_enabled is True and v.ring_diameter_mm == 184.0
    assert (v.parallax_height_mm, v.focal_equiv_mm) == (31.3, 26.0)
    assert v.layout_file == "phantom_layout_2026-10-02.json"
    assert v.origin_cabin_mm is None
    assert v.x_axis_cabin == [0.0, 1.0, 0.0] and v.y_axis_cabin == [0.0, 0.0, 1.0]
    assert v.cst_box_enabled is True
    assert v.cst_box_center_mm == [-43.645, 0.215, 3.335]
    assert v.cst_axis_u == [0.0, -1.0, 0.0], "eksen işareti (laboratuvar maddesi #2) YAML'dan okunmalı"
    assert v.cst_axis_v == [0.0, 0.0, 1.0]
    assert (v.navy_s_min, v.navy_v_min, v.navy_a_max, v.core_v_max) == (45, 20, 12, 35)


def test_bolum_YOKSA_varsayilan_eski_profil_YAMLlari_aynen_yuklenir(tmp_path):
    """Bölümü olmayan YAML (v1 profilleri) KeyError VERMEZ; plaka kipi KAPALI (None) — tekil petri / YOLO."""
    for ad, taban in (("petri.yaml", _petri_taban()), ("fantom.yaml", _fantom_taban())):
        c = _yukle(tmp_path, taban, "", ad=ad)
        assert c.multiwell.plate_type is None and c.multiwell.a1_cabin_mm is None
        assert c.multiwell.a1_corner == "auto" and c.multiwell.control_healthy == []
        assert c.phantom_v2.ring_diameter_mm == 184.0 and c.phantom_v2.origin_cabin_mm is None
        assert c.phantom_v2.cst_box_center_mm == [-43.645, 0.215, 3.335]
        assert c.phantom_v2.layout_file == "phantom_layout_2026-10-02.json"


@pytest.mark.parametrize(
    "eski,yeni,anahtar",
    [
        ("a1_cabin_mm: [-48.25, 28.95, 0.0]", "a1_cabin_mm: [-48.25, .nan, 0.0]", "multiwell.placement.a1_cabin_mm"),
        ("row_axis_cabin: [0.0, -1.0, 0.0]", "row_axis_cabin: [0.0, -.inf, 0.0]", "multiwell.placement.row_axis_cabin"),
        ("frac: 0.02", "frac: .nan", "multiwell.cancer.frac"),
    ],
    ids=["a1_kabin_nan", "satir_ekseni_inf", "kanser_orani_nan"],
)
def test_KRITIK_multiwell_SONLU_OLMAYAN_alan_yuklemede_REDDEDILIR(tmp_path, eski, yeni, anahtar):
    with pytest.raises(ValueError, match=anahtar.replace(".", r"\.")):
        _yukle(tmp_path, _petri_taban(), HOCA_MULTIWELL.replace(eski, yeni))


@pytest.mark.parametrize(
    "eski,yeni,anahtar",
    [
        ("diameter_mm: 184.0", "diameter_mm: .nan", "phantom_v2.coil_ring.diameter_mm"),
        ("center_mm: [-43.645, 0.215, 3.335]", "center_mm: [-43.645, .inf, 3.335]", "phantom_v2.cst_box.center_mm"),
        ("origin_cabin_mm: null", "origin_cabin_mm: [.nan, 0.0, 0.0]", "phantom_v2.placement.origin_cabin_mm"),
        ("height_mm: 31.3", "height_mm: .nan", "phantom_v2.parallax.height_mm"),
    ],
    ids=["halka_capi_nan", "cst_merkez_inf", "yerlesim_nan", "paralaks_nan"],
)
def test_KRITIK_phantom_v2_SONLU_OLMAYAN_alan_yuklemede_REDDEDILIR(tmp_path, eski, yeni, anahtar):
    with pytest.raises(ValueError, match=anahtar.replace(".", r"\.")):
        _yukle(tmp_path, _fantom_taban(), HOCA_PHANTOM_V2.replace(eski, yeni))
