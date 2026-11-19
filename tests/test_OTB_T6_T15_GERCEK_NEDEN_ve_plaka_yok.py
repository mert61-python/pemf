# -*- coding: utf-8 -*-
"""OTB T-6 / T-12 / T-14 / T-15 (ODM tezgâhı 19-11, neden metinleri):
  · T-6: seans durunca şerit "Plaka ya da kuyular tanınmadı, plakayı ortaya koyun" dedi — gerçek neden `kamera_oynamis` idi. SÖZLEŞME: kare
    reddedildiyse (plan hiç hesaplanmadı) durma nedeni son lokalizasyonun GERÇEK nedeni: plaka engeli sayılarıyla, yoksa fiziksel kapı
    nedeni; genel "tanınmadı" yalnız son çare.
  · T-12: uyarıdaki "Tümünü gör" yalnız aynı metnin devamını açıyordu → şerit plaka engelinin SAPMASINI (mm) ve GÖRÜLEN kuyu sayısını söyler.
  · T-14: boş kabinde neden "Kamera oynamış olabilir ya da taban yüksekliği yanlış" → plaka görülmüyorsa (< 3 kuyu) "plaka bulunamadı" ÖNCE.
  · T-15: boş kabinde önizlemede hocanın modeli kâğıdı / profili kuyu sandı ("Kuyucuk 3 · Kanser 2 · Sağlıklı 1") → plaka doğrulanmadıkça
    hocanın çizimi (çember + sayaç) GÖNDERİLMEZ, ham kare. Hoca modeli DEĞİŞMEZ.
GERÇEK: sağlayıcının `localize`i + kapı + ODAK ızgarası + şerit / durma metni üreticileri; sahte: CV hattı sonucu ve adaylar (B-5 düzeneği).
"""

from __future__ import annotations

import types

import numpy as np
import pytest
from petri_plaka_aparati import plaka_adaylari

KARE = np.zeros((8, 8, 3), dtype=np.uint8)
CIZIM = object()  # hocanın render paneli (sahte)


def _sonuc(warnings=()):
    return types.SimpleNamespace(
        success=True,
        error="",
        method="sabit_duzlem",
        mm_per_px=0.5,
        warnings=list(warnings),
        pemf_valid=True,
        reliable=False,
        coord_frame="cabin_plane",
        layout={},
    )


def _saglayici(kareler, warnings=()):
    from servers import ai_pro_hedef as hedef

    sira = list(kareler)

    class _Hat:
        def process_image(self, frame, **k):
            return _sonuc(warnings), {}

    class _S(hedef.PetriSaglayici):
        def _onbellek(self):
            return {"cfg": None}

        def _pipeline_kur(self, cache):
            return _Hat()

        def _overlay(self, pl, ctx, result):
            return CIZIM

        def _egitim_araligi(self):
            raise RuntimeError("aralık yok")

        def _adaylar(self, result):
            return [dict(a) for a in sira.pop(0)]

    s = _S()
    s.kosulsuz = True
    return s


def _iki_halka():
    return [
        {
            "px": (3.0, 4.0),
            "bbox": (1, 2, 5, 6),
            "x": -40.0,
            "y": -165.0,
            "z": 0.0,
            "organ_id": 1,
            "reliability": 0.94,
            "oncelik": 1.0,
            "label": "Kuyu B3",
            "id": 0,
        }
    ]


def test_KRITIK_T15_plaka_DOGRULANMAYAN_karede_hocanin_CIZIMI_gonderilmez_dogrulananda_AYNEN():
    dagin = plaka_adaylari()[:6]
    dagin[1] = {**dagin[1], "x": dagin[1]["x"] + 25.0}
    dagin[4] = {**dagin[4], "z": dagin[4]["z"] - 30.0}
    s = _saglayici([[dagin[0], dagin[1], dagin[4], *plaka_adaylari()[6:8]], plaka_adaylari()])
    r = s.localize(KARE, 0)
    assert r[0] is False and r[5] is None, "doğrulanmayan plakada hocanın çember / sayacı önizlemeye gitti"
    r2 = s.localize(KARE, 0)
    assert r2[0] is True and r2[5] is CIZIM


def test_KRITIK_T14_bos_kabinde_FIZIKSEL_kamera_nedeni_yerine_PLAKA_YOK_ve_ham_kare():
    from servers import ai_pro_hedef as hedef
    from servers import ai_router as air

    s = _saglayici([[]], warnings=("kamera_oynamis: sabit sahne kalibrasyon karesiyle eslesmedi (az_eslesme)",))
    r = s.localize(KARE, 0)
    meta = s.son_lokalizasyon_meta()
    assert r[0] is False and r[5] is None
    assert meta["plaka_dogrulanmadi"] == "plakaYok" and meta["plaka_ayrinti"] == {"bulunan": 0, "beklenen": 3}, meta
    plan = hedef.plaka_engel_plani(meta)
    metin = hedef.odak_engel_metni(plan)
    assert "Kamera oynamış" not in metin and "Plaka" in metin and "0" in metin, metin
    # şerit: fiziksel konum nedeni GÖSTERİLMEZ, neden plaka yok
    import unittest.mock as um

    with (
        um.patch.object(air, "_saglayici_meta", return_value=meta),
        um.patch.object(air, "_aktif_saglayici", return_value=s),
    ):
        a = air._saglayici_cache_alanlari()
    assert a["kapi_eylem"] == "" and a["kapi_uyari"] == metin, a


def test_KARSIT_T14_plaka_VARKEN_fiziksel_neden_AYNEN():
    s = _saglayici([plaka_adaylari()], warnings=("kamera_oynamis: sabit sahne 30 px kaymis (esik 12)",))
    r = s.localize(KARE, 0)
    meta = s.son_lokalizasyon_meta()
    assert r[0] is False and "plaka_dogrulanmadi" not in meta and "kamera_oynamis" in meta["pemf_kapisi"]["nedenler"]


@pytest.mark.parametrize("dil", ["tr", "en"])
def test_KRITIK_T12_serit_SAPMA_ve_GORULEN_kuyu_sayisini_SOYLER(dil):
    from servers import ai_pro_hedef as hedef
    from utils import ceviri

    dagin = plaka_adaylari()[:6]
    dagin[1] = {**dagin[1], "x": dagin[1]["x"] + 25.0}
    dagin[4] = {**dagin[4], "z": dagin[4]["z"] - 30.0}
    s = _saglayici([[dagin[0], dagin[1], dagin[4], *plaka_adaylari()[6:8]]])
    s.localize(KARE, 0)
    meta = s.son_lokalizasyon_meta()
    jeton = ceviri.istek_dili_var.set(dil)
    try:
        metin = hedef.kapi_uyari_metni(meta["pemf_kapisi"], "", meta)
    finally:
        ceviri.istek_dili_var.reset(jeton)
    ek = meta["plaka_ayrinti"]
    assert meta["plaka_dogrulanmadi"] == "plakaUyumsuz" and ek["bulunan"] == 5 and ek["sapma"] > 5, ek
    sapma = f"{float(ek['sapma']):.2f}"
    assert "5" in metin and (sapma if dil == "en" else sapma.replace(".", ",")) in metin, (
        metin
    )  # Y306: TR ondalık virgül
    if dil == "en":
        assert not any(c in metin for c in "çğıöşüÇĞİÖŞÜ"), metin


def test_KRITIK_T6_seans_DURMA_nedeni_GERCEK_neden_plakaKaydi_sayilariyla():
    from servers import ai_pro_hedef as hedef
    from servers import ai_router as air

    ref = plaka_adaylari()
    kaymis = [{**a, "x": a["x"] + 19.3} for a in ref]
    s = _saglayici([ref, kaymis])
    hedef.odak_ayarla(s, {"doz_mT": 1.4, "kip": "TUM_PETRI"}, "Tüm petri")
    s.localize(KARE, 0)
    assert s.localize(KARE, 0)[0] is False
    meta = s.son_lokalizasyon_meta()
    import unittest.mock as um

    with um.patch.object(air, "_saglayici_meta", return_value=meta):
        metin = air._sabit_numune_neden_metni(None, dil="tr")
    assert "kaydı" in metin and "24" in metin, metin
    assert "tanınmadı" not in metin


def test_KRITIK_T6_seans_DURMA_nedeni_FIZIKSEL_kapi_nedeni_ve_SON_CARE_genel():
    from servers import ai_router as air

    fiziksel = {
        "pemf_kapisi": {
            "surulebilir": False,
            "nedenler": ["kamera_oynamis"],
            "mesajlar": [{"kod": "kamera_oynamis", "metin": "x"}],
        }
    }
    import unittest.mock as um

    with um.patch.object(air, "_saglayici_meta", return_value=fiziksel):
        m1 = air._sabit_numune_neden_metni(None, dil="tr")
    assert "Kamera oynamış" in m1 and "tanınmadı" not in m1, m1
    with um.patch.object(air, "_saglayici_meta", return_value={}):
        m2 = air._sabit_numune_neden_metni(None, dil="tr")
    assert "tanınmadı" in m2  # son çare AYNEN


def test_KARSIT_T14_KOSULLU_kipte_neden_AYNEN():
    s = _saglayici([[]], warnings=("kamera_oynamis: sabit sahne kalibrasyon karesiyle eslesmedi (az_eslesme)",))
    s.kosulsuz = False
    assert s.localize(KARE, 0)[0] is False
    assert (
        "plaka_dogrulanmadi" not in s.son_lokalizasyon_meta()
    )  # koşullu kip hocanın kapısıyla (B-5 kuralı) — DEĞİŞMEZ
