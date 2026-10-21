# -*- coding: utf-8 -*-
"""I18NI-A2.8 sondası: AI Pro hedef sağlayıcılarının (fantom / petri / genel) ARAYÜZE giden hedef adı Türkçe ön ekle KURULUYOR:
aday çipi (`HedefSecici.tsx` `h.label` → "Tümör T1", "Kuyu B3") ve canlı WS `organName` / `targetName` (`AiHubScreen` "Hedef organ: …",
`AiSpecApprovalModal`) → `hedef_adi()` "Tümör (otomatik)" / "Kuyu (otomatik)". `kapsam.json` bunları "`mode` verisinin parçası" diye MUAF
saymış ([İNCELE] notuyla). TR görünüm doğru; İngilizcede ekranda Türkçe kalır.
Sonda GÖSTERİLENİ ölçer: aday için `etiketGosterim` (varsa) yoksa `label`; ad için `ai_pro_hedef.hedef_gosterim_adi()` (yönlendiricinin
kullanması gereken yardımcı) VE yönlendiricinin WS yükünde `organName` / `targetName` için onu kullanması. VERİ (`label`, `hedef_adi`,
`mode`) Türkçe KALMALI (onay mührü / DB kaydı).
Koşum: bash $SP/aj.sh b pytest _inceleme/I18NI-A2.8/test_ai_pro_hedef_etiketi_istek_dilinde.py -q -rfE
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


def _kok() -> Path:
    p = Path(__file__).resolve().parent
    while not (p / "i18n" / "kapsam.json").exists():
        p = p.parent
    return p


KOK = _kok()
for _p in (KOK, KOK / "apps" / "backend"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from servers import ai_pro_hedef as aph  # noqa: E402
from utils import ceviri  # noqa: E402

TURKCE = re.compile(r"[çğıöşüÇĞİÖŞÜ]|\b(Tümör|Kuyu|Hedef|otomatik)\b")


@pytest.fixture
def ingilizce_istek():
    jeton = ceviri.istek_dili_var.set("en")
    try:
        yield
    finally:
        ceviri.istek_dili_var.reset(jeton)


def _fantom_sonucu():
    bolge = SimpleNamespace(
        centroid_cabin_mm=(1.0, 2.0, 3.0),
        tumor_id="T1",
        centroid_px=(10.0, 20.0),
        bbox_px=(0, 0, 5, 5),
        organ_id=1,
        area_px=50.0,
        E_cancer=None,
        E_healthy=None,
    )
    return SimpleNamespace(
        phantom_detection={"primary": {"solidity": 0.9, "n_blue_inside": 2}},
        warnings=[],
        layout={"rms_mm": 0.5},
        tumor_regions=[bolge],
    )


def _gosterilen_aday(s):
    a = s._kimlik_ata(s._adaylar(_fantom_sonucu()))[0]
    return a.get("etiketGosterim", a["label"]), a["label"]


def test_TR_gosterim_ve_VERI_gocten_onceki_gibi_TURKCE():
    s = aph.FantomSaglayici()
    gosterim, veri = _gosterilen_aday(s)
    assert gosterim == "Tümör T1" and veri == "Tümör T1"
    assert aph.hedef_gosterim_adi(s, 0) == "Tümör (otomatik)" and s.hedef_adi(0) == "Tümör (otomatik)"


def test_EN_istekte_aday_cipi_TURKCE_KALMAZ_veri_TURKCE_kalir(ingilizce_istek):
    gosterim, veri = _gosterilen_aday(aph.FantomSaglayici())
    assert veri == "Tümör T1", "VERİ (onay mührü etiketi) dile göre DEĞİŞMEMELİ"
    assert not TURKCE.search(gosterim), f"EN istekte aday çipinde Türkçe: {gosterim!r} (HedefSecici çizer)"


@pytest.mark.parametrize("sinif", ["FantomSaglayici", "PetriSaglayici"])
def test_EN_istekte_hedef_gosterim_adi_TURKCE_KALMAZ(sinif, ingilizce_istek):
    s = getattr(aph, sinif)()
    assert TURKCE.search(s.hedef_adi(0)), "VERİ adı (mode kaydı) Türkçe kalmalı"
    ad = aph.hedef_gosterim_adi(s, 0)
    assert not TURKCE.search(ad), f"EN istekte gösterilen hedef adı Türkçe: {ad!r}"


def test_yonlendirici_WS_yukunde_organName_targetName_GOSTERIM_adini_kullanir():
    src = (KOK / "apps/backend/servers/ai_router.py").read_text(encoding="utf-8")
    ham = re.findall(r'"(?:organName|targetName)":\s*_(?:aktif_saglayici\(\)|saglayici)\.hedef_adi\(', src)
    assert not ham, f"ai_router WS / yanıt yükünde {len(ham)} organName / targetName VERİ adıyla (Türkçe) dolduruluyor"
