# -*- coding: utf-8 -*-
"""Y306 (sahip 19-11, OTB [SAHİBE] 2): Türkçe engel / neden metinlerinde ondalık NOKTA vardı ("ortanca sapma 14.40 mm"; aynı ekranda doz
"1,84" virgüllü). SÖZLEŞME: sayıyı metni üreten yer DİLE GÖRE biçimler — TR virgül ("14,40 mm"), EN nokta ("14.40 mm"); tamsayı / metin
yer tutucular AYNEN; 2 basamak AYNI. Tek yardımcı `ceviri.sayi_metni`; ODAK engel metinlerinin hepsi `odak_engel_metni`nden geçer.
GERÇEK: katalog (TR + EN) + `odak_engel_metni` + `plaka_engel_plani`."""

from __future__ import annotations

import re

import pytest


def test_sayi_metni_TR_virgul_EN_nokta_binlik_YOK():
    from utils import ceviri

    assert ceviri.sayi_metni(14.4, 2, dil="tr") == "14,40"
    assert ceviri.sayi_metni(14.4, 2, dil="en") == "14.40"
    assert ceviri.sayi_metni(1234.5, 1, dil="tr") == "1234,5" and ceviri.sayi_metni(1234.5, 1, dil="en") == "1234.5"
    assert ceviri.sayi_metni(3, 0, dil="tr") == "3"


def test_sayi_metni_dil_VERILMEZSE_istek_dili(monkeypatch):
    from utils import ceviri

    monkeypatch.setattr(ceviri, "etkin_dil", lambda: "en")
    assert ceviri.sayi_metni(0.5) == "0.50"
    monkeypatch.setattr(ceviri, "etkin_dil", lambda: "tr")
    assert ceviri.sayi_metni(0.5) == "0,50"


@pytest.mark.parametrize("dil,beklenen,olmayan", [("tr", "14,40 mm", "14.40"), ("en", "14.40 mm", "14,40")])
def test_KRITIK_plaka_KAYDI_engel_metni_ondalik_DILE_gore(dil, beklenen, olmayan):
    from servers import ai_pro_hedef as hedef

    plan = hedef.plaka_engel_plani(
        {"plaka_dogrulanmadi": "plakaKaydi", "plaka_ayrinti": {"gorulen": 20, "sapma": 14.4}}
    )
    metin = hedef.odak_engel_metni(plan, dil=dil)
    assert beklenen in metin and olmayan not in metin, metin
    assert re.search(r"\b20\b", metin) and "20,0" not in metin and "20.0" not in metin, metin  # tamsayı AYNEN


@pytest.mark.parametrize("dil", ["tr", "en"])
def test_eksik_sayi_SORU_isareti_ve_metin_yer_tutucu_AYNEN(dil):
    from servers import ai_pro_hedef as hedef

    plan = hedef.plaka_engel_plani({"plaka_dogrulanmadi": "plakaUyumsuz", "plaka_ayrinti": {"bulunan": 5}})
    metin = hedef.odak_engel_metni(plan, dil=dil)
    assert "?" in metin and re.search(r"\b5\b", metin), metin
