# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""AP-13 (istem 48 · B10): öneri 409'unun ipucu kapının fiziksel OLMAYAN nedeninde canlı, istek dilinde metin verir — hocanın AI Hub
tek-foto metni ("… yeniden çekin", yalnız Türkçe) EN arayüzde Türkçe çıkıyordu. Fiziksel neden zaten dile çevrili (`kapi_cevir`)."""


def test_KRITIK_ipucu_kalite_nedeninde_CANLI_metin_iki_dilde():
    from servers import ai_pro_hedef as h
    from utils import ceviri

    s = h.PetriSaglayici()
    s._meta = {
        "method": "sabit_duzlem",
        "pemf_kapisi": {"surulebilir": False, "nedenler": ["few_candidates"], "eylem": "x yeniden çekin"},
    }
    j = ceviri.istek_dili_var.set("en")
    try:
        en = s.ipucu(True, "Well C6")
    finally:
        ceviri.istek_dili_var.reset(j)
    assert en.startswith("The well grid could not be verified")
    assert "yeniden çekin" not in s.ipucu(True, "Kuyu C6")


def test_fiziksel_nedende_kapi_eylemi_AYNEN():
    from servers import ai_pro_hedef as h

    s = h.PetriSaglayici()
    s._meta = {
        "method": "sabit_duzlem",
        "pemf_kapisi": {"surulebilir": False, "nedenler": ["kamera_oynamis"], "eylem": "KAMERA EYLEMI"},
    }
    assert s.ipucu(True, "Kuyu C6") == "KAMERA EYLEMI"
