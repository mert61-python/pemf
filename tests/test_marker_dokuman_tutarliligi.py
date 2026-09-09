# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""KABİN İŞARETİ DOKÜMAN TUTARLILIĞI (Faz 4, 2026-09-09).

ÖLÇÜLEN SAPMA: `phantom_cv/README.md` ve `petri_cv/README.md` kullanıcıya **DICT_5X5_100** sözlüğünü
ve **5 cm** kenar bas diyordu; basılı sayfa `PEMF_ArUco_Marker_5X5_50_ID0_10cm_A4.pdf`
(DICT_5X5_50 · 10,0 cm) ve üç kabin yaml'ı da `dict: DICT_5X5_50` + `real_cm: 10.0` okuyor.

NEDEN KAPI (iki ayrı sessiz arıza):
  · YANLIŞ SÖZLÜK → işaret HİÇ tespit edilmez; yöntem `aruco_pnp` olmaz, araştırma AI Pro hedefi
    reddeder ve kullanıcı işareti asmış olduğu hâlde "kabin işareti görünmüyor" okur.
  · DOĞRU sözlük + YANLIŞ KENAR (5 cm yerine 10 cm) → tespit ÇALIŞIR, ölçek 2 kat yanlış olur ve
    3B koordinat sessizce iki katına çıkar. Hiçbir ekran hata göstermez; bobinler yanlış noktaya
    odaklanır. Bu, "ölçüm doğru görünüyor ama yanlış" sınıfının tam örneğidir.

⚠️ Kapı DOKÜMANI koda pinler: yaml'daki değer değişirse (ör. daha büyük bir sayfaya geçilirse)
dokümanların da değişmesi ZORUNLU olur.
"""

import pathlib
import re

import pytest

_KOK = pathlib.Path(__file__).resolve().parents[1]
_AI_HUB = _KOK / "ai_hub"

#: Basılı sayfanın adı, gerçeğin tek kaynağı (dosya adı sözlük ve kenarı taşır).
_BASILI = "PEMF_ArUco_Marker_5X5_50_ID0_10cm_A4.pdf"

#: Kabin yaml'ları — hepsi AYNI işareti okumak zorunda (tek kabin, tek işaret).
_YAMLLAR = (
    "inference_cat_organ/cabin_config_example.yaml",
    "inference_em_fantom/phantom_cv/cabin_config_example.yaml",
    "inference_petri_dish/petri_cv/cabin_config_example.yaml",
)

#: Kullanıcıyı işaret basmaya yönlendiren dokümanlar.
_DOKUMANLAR = (
    "inference_em_fantom/phantom_cv/README.md",
    "inference_petri_dish/petri_cv/README.md",
    "KABIN_KURULUM_KILAVUZU.md",
)

pytestmark = pytest.mark.skipif(not (_AI_HUB / _YAMLLAR[0]).exists(), reason="ai_hub kaynak ağacı yok")


def _yaml_isaret(gorece: str) -> "tuple[str, float]":
    src = (_AI_HUB / gorece).read_text(encoding="utf-8")
    d = re.search(r"^\s*dict:\s*(\S+)", src, re.M)
    r = re.search(r"^\s*real_cm:\s*([\d.]+)", src, re.M)
    assert d and r, f"{gorece}: aruco.dict / aruco.real_cm okunamadı"
    return d.group(1), float(r.group(1))


def test_KRITIK_basili_sayfa_DOSYASI_var():
    """Dokümanların yönlendirdiği sayfa gerçekten depoda olmalı (ölü yönlendirme yok)."""
    assert (_AI_HUB / _BASILI).exists(), f"basılı işaret sayfası yok: ai_hub/{_BASILI}"


def test_KRITIK_UC_kabin_yamli_AYNI_isareti_okur():
    """Tek kabin, tek işaret: modüller ayrışırsa biri işareti hiç bulamaz."""
    okunan = {y: _yaml_isaret(y) for y in _YAMLLAR}
    tekil = set(okunan.values())
    assert len(tekil) == 1, f"kabin yaml'ları farklı işaret okuyor: {okunan}"
    sozluk, kenar = tekil.pop()
    # Basılı sayfanın ADI gerçeğin kaynağı: 5X5_50 ve 10cm onun içinde yazılı.
    assert sozluk.replace("DICT_", "") in _BASILI, f"yaml sözlüğü ({sozluk}) basılı sayfayla uyuşmuyor"
    assert f"{int(kenar)}cm" in _BASILI, f"yaml kenar uzunluğu ({kenar} cm) basılı sayfayla uyuşmuyor"


def test_KRITIK_DOKUMANLAR_yanlis_SOZLUK_onermez():
    """MUTASYON: bir README'ye `DICT_5X5_100` yazın → KIRMIZI (işaret hiç tespit edilmez)."""
    sozluk, _ = _yaml_isaret(_YAMLLAR[0])
    for gorece in _DOKUMANLAR:
        yol = _AI_HUB / gorece
        if not yol.exists():
            continue
        src = yol.read_text(encoding="utf-8")
        yanlis = {m for m in re.findall(r"DICT_\w+", src) if m != sozluk}
        assert not yanlis, f"{gorece} yanlış ArUco sözlüğü öneriyor: {sorted(yanlis)} (doğrusu {sozluk})"


def test_KRITIK_DOKUMANLAR_yanlis_KENAR_uzunlugu_onermez():
    """Doğru sözlük + yanlış kenar = SESSİZ ölçek hatası (3B koordinat kat kat yanlış).

    MUTASYON: bir README'de "5 cm × 5 cm yazdır" satırını geri koyun → KIRMIZI."""
    _, kenar = _yaml_isaret(_YAMLLAR[0])
    # "N cm × N cm yazdır" / "N cm kenar" gibi BASIM TALİMATI kalıpları.
    kalip = re.compile(r"([\d.,]+)\s*cm\s*(?:×|x)\s*([\d.,]+)\s*cm\s*(?:yazdır|bas)|([\d.,]+)\s*cm\s*kenar")
    for gorece in _DOKUMANLAR:
        yol = _AI_HUB / gorece
        if not yol.exists():
            continue
        for satir in yol.read_text(encoding="utf-8").splitlines():
            m = kalip.search(satir)
            if not m:
                continue
            sayilar = [float(g.replace(",", ".")) for g in m.groups() if g]
            assert all(abs(s - kenar) < 0.01 for s in sayilar), (
                f"{gorece} işareti {sayilar} cm basmayı söylüyor, kabin {kenar} cm okuyor "
                f"→ ölçek {max(sayilar) / kenar:.1f}× yanlış olurdu: {satir.strip()[:90]}"
            )


def test_KAPI_gercekten_olcuyor():
    """MUTASYON ÖZ-TESTİ: tarayıcı yanlış kenar talimatını sentetik metinde görüyor mu?"""
    _, kenar = _yaml_isaret(_YAMLLAR[0])
    kalip = re.compile(r"([\d.,]+)\s*cm\s*(?:×|x)\s*([\d.,]+)\s*cm\s*(?:yazdır|bas)|([\d.,]+)\s*cm\s*kenar")
    m = kalip.search("5 cm × 5 cm yazdır, kabinin sol duvarına yapıştır.")
    assert m, "tarayıcı basım talimatını görmüyor"
    sayilar = [float(g.replace(",", ".")) for g in m.groups() if g]
    assert not all(abs(s - kenar) < 0.01 for s in sayilar), "kapı yanlış kenarı doğru sayıyor"
