# -*- coding: utf-8 -*-
"""AII-1.5 (AI incelemesi, A1) — "iki YAML, bir kabin": petri v2 ile fantom v3 profil YAML'ları AYNI saha kabinini ayrı ayrı
taşıyor; eşitlik kapısı yalnız 7 anahtara bakıyordu (KÖR KAPI).

ÖLÇÜLDÜ (`_inceleme/sonda/k4a_iki_yaml_bir_kabin.py`): iki YAML'da 25 ortak kabin anahtarı var (aruco.*, geometry.*, camera.*,
phantom_plate.*, pnp.*, phantom.*); bugün yalnız nesneye özgü `phantom_plate.width_cm / height_cm` farklı. Mevcut kapı
`tests/test_kabin_config_65x50x50.py::test_uc_pipeline_AYNI_kabini_tanimlar` yalnız `geometry.qr_to_origin_cm / cabin_extent_cm`
ve `camera.*` beşlisini karşılaştırıyor (aruco sözlük / kenar / normal sabite pinli). Mutant: petri v2 YAML'ında karar #6 HEDEF
DÜZLEMİ `-20 → -15 cm` (fantom −20 kalır) ya da fantom v3'te `aruco.plane_offset_cm 0 → 1,5` → kabin / koordinat / Y49 / FIZIKSEL
kümesinin 33 dosyası 499 geçti / 0 kırmızı. Sahibin "saha düzeltmesi için YALNIZ yaml yeter" kuralıyla bir YAML güncellenip öteki
unutulursa fantom ve petri FARKLI kabin çerçevesinde hedef üretir.

Kapı: iki profil YAML'ının ortak kabin anahtarları birebir eşit (nesneye özgü boyutlar hariç); kedi organ YAML'ıyla kesişen
aruco / geometry / camera anahtarları da eşit (`geometry.axes` hasta eksen adlandırması — kediye özgü — hariç).
"""

from __future__ import annotations

from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
PETRI = KOK / "ai_hub" / "inference_petri_dish" / "petri_cv_v2" / "cabin_config_v2.yaml"
FANTOM = KOK / "ai_hub" / "inference_em_fantom" / "phantom_cv_v3" / "cabin_config_v3.yaml"
KEDI = KOK / "ai_hub" / "inference_cat_organ" / "cabin_config_example.yaml"
KABIN_BOLUMLERI = ("aruco.", "geometry.", "camera.", "phantom_plate.", "pnp.", "phantom.")
#: Nesneye özgü (petri plakası ↔ fantom) — kabin değil.
NESNEYE_OZGU = {"phantom_plate.width_cm", "phantom_plate.height_cm"}
#: Kediye özgü eksen ADLANDIRMASI (x=cranial…) — sayısal kabin değil.
KEDIYE_OZGU = {"geometry.axes"}


def _duz(d, on=""):
    out = {}
    if isinstance(d, dict):
        for k, v in d.items():
            out.update(_duz(v, f"{on}{k}."))
    else:
        out[on[:-1]] = d
    return out


def _yukle(p: Path) -> dict:
    yaml = pytest.importorskip("yaml")
    return _duz(yaml.safe_load(p.read_text(encoding="utf-8")))


def test_KRITIK_petri_v2_ve_fantom_v3_AYNI_kabin_alanlarini_tasir():
    pv, fv = _yukle(PETRI), _yukle(FANTOM)
    ortak = sorted(k for k in set(pv) & set(fv) if k.startswith(KABIN_BOLUMLERI) and k not in NESNEYE_OZGU)
    assert len(ortak) >= 20, f"ortak kabin anahtarı çok az ({len(ortak)}) — kapı boş dönüyor olabilir"
    for zorunlu in (
        "phantom_plate.hedef_duzlem_cm",
        "phantom_plate.hedef_duzlem_eksen",
        "aruco.plane_offset_cm",
        "geometry.qr_to_origin_cm",
        "camera.fixed_position_cm",
    ):
        assert zorunlu in ortak, f"{zorunlu} iki YAML'da da olmalı"
    fark = [f"{k}: petri={pv[k]!r} fantom={fv[k]!r}" for k in ortak if pv[k] != fv[k]]
    assert not fark, "iki profil YAML'ı FARKLI kabin tanımlıyor (biri güncellenip öteki unutulmuş):\n  " + "\n  ".join(
        fark
    )
    tek = sorted(k for k in set(pv) ^ set(fv) if k.startswith(KABIN_BOLUMLERI))
    assert not tek, f"kabin anahtarı yalnız bir YAML'da: {tek}"


def test_KRITIK_kedi_organ_YAMLi_ile_kesisen_kabin_alanlari_ESIT():
    pv, kd = _yukle(PETRI), _yukle(KEDI)
    ortak = sorted(
        k for k in set(pv) & set(kd) if k.startswith(("aruco.", "geometry.", "camera.")) and k not in KEDIYE_OZGU
    )
    assert len(ortak) >= 10, f"kedi ile kesişim çok az ({len(ortak)})"
    fark = [f"{k}: petri={pv[k]!r} kedi={kd[k]!r}" for k in ortak if pv[k] != kd[k]]
    assert not fark, "kedi organ kabini petri / fantom kabininden FARKLI:\n  " + "\n  ".join(fark)


def test_KRITIK_yukleyiciler_AYNI_hedef_duzlemini_cozer():
    """YAML metni değil ÜRÜNÜN okuduğu değer: iki profil yükleyicisi aynı hedef düzlemini (karar #6) ve marker pozunu verir."""
    from ai_hub.inference_em_fantom.phantom_cv_v3 import load_cabin_config as fantom_yukle
    from ai_hub.inference_petri_dish.petri_cv_v2 import load_cabin_config as petri_yukle

    p, f = petri_yukle(None), fantom_yukle(None)
    assert (p.phantom_plate.hedef_duzlem_indeksi, p.phantom_plate.hedef_duzlem_mm) == (
        f.phantom_plate.hedef_duzlem_indeksi,
        f.phantom_plate.hedef_duzlem_mm,
    )
    assert (p.aruco.real_cm, p.aruco.plane_offset_cm) == (f.aruco.real_cm, f.aruco.plane_offset_cm)
    assert list(p.geometry.qr_to_origin_cm) == list(f.geometry.qr_to_origin_cm)
