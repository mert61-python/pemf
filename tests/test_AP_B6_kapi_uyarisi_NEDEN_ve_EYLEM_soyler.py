# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""AP · B6 (istem 48 · S-AP.6, sahip 14 Kasım 2026 "neden + eylem"): canlı hazırlıkta kare tüketim kapısı fiziksel OLMAYAN nedenle
(`few_candidates`, `ecc_failed`, …) ya da plaka makullik reddiyle keserse arayüz NEDEN + EYLEM görür (`/ai/pro/status` `kapiUyari`,
istek dilinde). 13-11 tezgâhında koşullu kipte her kare böyle kesildi; şerit "kuyu aranıyor" deyip 120 sn sonra kedi + telefon iletisi
veriyordu. Fiziksel neden kendi metniyle (`kapiEylem`) gider → burada boş. Koşulsuz kip ÖNERİLMEZ. Yalnız gösterim (kapı kararı aynı)."""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def dil():
    from utils import ceviri

    jetonlar = []

    def _ayarla(d):
        jetonlar.append(ceviri.istek_dili_var.set(d))

    yield _ayarla
    for j in reversed(jetonlar):
        ceviri.istek_dili_var.reset(j)


def test_KRITIK_izgara_dogrulanamadi_NEDEN_ve_EYLEM_iki_dilde(dil):
    from servers import ai_pro_hedef as h

    kapi = {"surulebilir": False, "nedenler": ["few_candidates", "ecc_failed"]}
    dil("tr")
    tr = h.kapi_uyari_metni(kapi)
    assert tr.startswith("Kuyu ızgarası doğrulanamadı") and "kabin ışığı" in tr
    assert "Koşulsuz" not in tr and "yeniden çekin" not in tr
    dil("en")
    en = h.kapi_uyari_metni(kapi)
    assert en.startswith("The well grid could not be verified") and "petri" not in en.lower()


def test_KRITIK_makullik_reddi_de_NEDEN_soyler(dil):
    from servers import ai_pro_hedef as h

    from ai_hub.inference_petri_dish import plausibility as pl

    dil("tr")
    assert h.kapi_uyari_metni(None, pl.PETRI_REJECT).startswith("Kuyu ızgarası doğrulanamadı")


@pytest.mark.parametrize(
    "kapi",
    [
        {"surulebilir": True, "nedenler": []},
        {"surulebilir": False, "nedenler": ["kamera_oynamis", "few_candidates"]},  # fiziksel → kendi metni (kapiEylem)
        None,
    ],
)
def test_suruleblir_ya_da_FIZIKSEL_nedende_BOS(kapi):
    from servers import ai_pro_hedef as h

    assert h.kapi_uyari_metni(kapi) == ""


def test_durum_ucu_kapiUyari_verir():
    import servers.ai_router as air
    import servers.api_server as apis

    eski = air._ai_organ_cache.get("kapi_uyari")
    try:
        air._ai_organ_cache["kapi_uyari"] = "Kuyu ızgarası doğrulanamadı — x"
        assert TestClient(apis.app).get("/api/ai/pro/status").json()["kapiUyari"] == "Kuyu ızgarası doğrulanamadı — x"
    finally:
        air._ai_organ_cache["kapi_uyari"] = eski
