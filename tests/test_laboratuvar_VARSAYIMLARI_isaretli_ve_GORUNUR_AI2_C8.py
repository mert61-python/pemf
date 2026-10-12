# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""AI-2 C8 — hocanın laboratuvar maddeleri (ENTEGRASYON §4; plan §6 #1–#5) YAPILANDIRMADA işaretli ve SONUÇTA görünür (2026-10-12).

NEDEN: hocanın v2 / v3'ü beş ölçülmemiş fiziksel değere dayanıyor (plakanın kabin konumu, fantom eksen işareti, yeşil halka çapı,
kanser eşiklerinin yalnız yapay boyayla doğrulanması, A1 köşesi). Değer YAML'da sessizce dururken bir sonraki kişi onu "ölçülmüş"
sanar; sonuç ekranında da söylenmezse operatör D / P / E'nin bir varsayıma dayandığını bilemez.

KAPI (beklenenler BURADA sabit — kaynaktan OKUNMAZ):
  · her madde profil YAML'ında, değerin bulunduğu bölümde `⚠️ LABORATUVAR` işaretiyle ve hocanın madde numarasıyla duruyor;
  · her madde, koşulu oluşan GERÇEK v2 / v3 sonuç sözlüğünde (`pemf_kapisi.degerlendir`) operatöre giden metne dönüşüyor
    (#1 → eylem "plakanın kabindeki konumu bilinmiyor"; #2–#5 → VARSAYIM satırları); koşul yokken o satır ÇIKMIYOR (karşıt).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
PETRI_YAML = KOK / "ai_hub" / "inference_petri_dish" / "petri_cv_v2" / "cabin_config_v2.yaml"
FANTOM_YAML = KOK / "ai_hub" / "inference_em_fantom" / "phantom_cv_v3" / "cabin_config_v3.yaml"

#: (madde, YAML, bölüm, işaretin altında görünmesi gereken anahtar)
MADDELER = [
    ("#1", PETRI_YAML, "multiwell", "a1_cabin_mm"),
    ("#2", FANTOM_YAML, "phantom_v2", "axis_u"),
    ("#3", FANTOM_YAML, "phantom_v2", "diameter_mm"),
    ("#4", PETRI_YAML, "multiwell", "frac"),
    ("#5", PETRI_YAML, "multiwell", "a1_corner"),
]


def _bolum(yol: Path, bolum: str) -> list[str]:
    satirlar = yol.read_text(encoding="utf-8").splitlines()
    i = next(n for n, s in enumerate(satirlar) if s.startswith(f"{bolum}:"))
    j = next((n for n in range(i + 1, len(satirlar)) if satirlar[n][:1].isalpha()), len(satirlar))
    return satirlar[i:j]


@pytest.mark.parametrize("madde,yol,bolum,anahtar", MADDELER, ids=[m[0] for m in MADDELER])
def test_KRITIK_laboratuvar_maddesi_YAMLda_ISARETLI(madde, yol, bolum, anahtar):
    satirlar = _bolum(yol, bolum)
    isaret = [n for n, s in enumerate(satirlar) if "LABORATUVAR" in s and f"§4 {madde}" in s]
    assert isaret, f"{yol.name} `{bolum}:` bölümünde hoca §4 {madde} için ⚠️ LABORATUVAR işareti YOK"
    sonra = "\n".join(satirlar[isaret[0] : isaret[0] + 25])
    assert re.search(rf"^\s*{anahtar}:", sonra, re.M), (
        f"§4 {madde} işareti `{anahtar}` değerinin yanında değil (işaret ile değer ayrışmış: biri taşınırsa öteki yalnız kalır)"
    )


def _kapi(sonuc: dict, model: str) -> dict:
    from ai_hub.cv_ortak import pemf_kapisi

    return pemf_kapisi.degerlendir(sonuc, model=model)


def _kodlar(k: dict) -> set[str]:
    return {v["kod"] for v in k["varsayimlar"]}


#: v2 / v3 `to_dict()` biçiminde en küçük sonuçlar (alan adları hocanın sözleşmesi).
PETRI_PLAKA = {
    "success": True,
    "pemf_valid": False,
    "coord_frame": "plate",
    "method": "plate_grid",
    "warnings": ["pemf_frame_unknown: kabin konumu yok (ArUco veya multiwell.placement.a1_cabin_mm) - D/P/E gecersiz"],
    "plate": {"plate_type": 24, "a1_corner": "tl"},
    "classification": {"control_healthy": [], "control_cancer": []},
}
FANTOM_HALKA_CST = {
    "success": True,
    "pemf_valid": True,
    "reliable": True,
    "method": "coil_ring",
    "pemf_source": "cst_phantom_box",
    "coord_frame": "cabin_cst_phantom_box",
    "warnings": ["pemf_axis_sign_assumed: fantom merkezi/eksenleri CST egitim kutusuna eslendi; u->+y, v->+z ISARETI"],
}


def test_KRITIK_madde1_petri_KABIN_KONUMU_yoksa_EYLEM_soyler():
    k = _kapi(PETRI_PLAKA, "petri")
    assert not k["surulebilir"] and "pemf_gecersiz" in k["nedenler"]
    assert "plakanın kabindeki konumu bilinmiyor" in k["eylem"], k["eylem"]


def test_KRITIK_madde4_5_PLAKA_kipinde_A1_ve_KANSER_ESIGI_varsayimi_GORUNUR():
    assert {"a1_kosesi", "kanser_esikleri"} <= _kodlar(_kapi(PETRI_PLAKA, "petri"))


def test_KARSIT_madde4_KONTROL_kuyucugu_VERILINCE_esik_varsayimi_CIKMAZ():
    s = dict(PETRI_PLAKA, classification={"control_healthy": ["A1"], "control_cancer": ["B2"]})
    assert "kanser_esikleri" not in _kodlar(_kapi(s, "petri"))
    assert "a1_kosesi" in _kodlar(_kapi(s, "petri")), "A1 köşesi kontrol kuyucuğundan bağımsız bir varsayım"


def test_KARSIT_TEKIL_kipte_plaka_varsayimlari_CIKMAZ():
    s = dict(PETRI_PLAKA, plate={}, method="aruco_pnp", pemf_valid=True, coord_frame="cabin_aruco", warnings=[])
    assert not ({"a1_kosesi", "kanser_esikleri"} & _kodlar(_kapi(s, "petri")))


def test_KRITIK_madde2_3_fantom_HALKA_ve_EKSEN_ISARETI_varsayimi_GORUNUR():
    k = _kapi(FANTOM_HALKA_CST, "fantom")
    assert k["surulebilir"], "aparat: geçerli fantom sonucu sürülebilir olmalı (varsayım SÜRÜŞÜ engellemez, gösterilir)"
    assert {"pemf_axis_sign_assumed", "halka_capi"} <= _kodlar(k)
    metin = " ".join(v["metin"] for v in k["varsayimlar"])
    assert "184 mm" in metin and "u→+y" in metin, metin


def test_KARSIT_ArUco_fantomda_halka_ve_eksen_varsayimi_CIKMAZ():
    s = dict(FANTOM_HALKA_CST, method="aruco_pnp", pemf_source="aruco", coord_frame="cabin_aruco", warnings=[])
    assert not ({"pemf_axis_sign_assumed", "halka_capi"} & _kodlar(_kapi(s, "fantom")))
