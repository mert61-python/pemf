# -*- coding: utf-8 -*-
"""OTB T-14b (kum havuzu EN turu 19-11, kayıtlı gerçek kareler `3a_kayma_once`): kamera OYNAMADAN (sabit sahne kayması 1,6–1,9 px, eşik
12 px) hareketsiz plakada Hough kuyu aralığı karelerin ~1/3'ünde %3,0–5,6 sapıyor (tolerans %3) → hat `kamera_oynamis` engeli → konumlu
aday 0 → T-14 dalı şeride ve seans durma nedenine "Plakanın yeri ve yönü bulunamadı: yalnız 0 kuyu görüldü" yazdı; plaka görüntüde
açıkça duruyordu. SÖZLEŞME: plakanın kuyu merkezleri ÖLÇÜLDÜYSE (kalibrasyon özetinde `olcum.kuyu_araligi` var) neden PLAKA YOK değil,
kapının kendi (fiziksel) nedeni — T-6 ilkesi (gerçek neden). Aralık ölçülmeyen karede (boş kabin) T-14 AYNEN.
GERÇEK: sağlayıcının `localize`i + kapı + şerit / durma metni üreticileri; sahte: CV hattı sonucu ve adaylar (T-6/T-15 düzeneği)."""

from __future__ import annotations

import types
import unittest.mock as um

import numpy as np
import pytest

KARE = np.zeros((8, 8, 3), dtype=np.uint8)
ARALIK_UYARISI = "kamera_oynamis: eslenen kuyu araligi 19.13 / 18.50 mm, beklenen 19.3 mm (sapma %4.1 > %3)"
SAHNE_UYARISI = "kamera_oynamis: sabit sahne kalibrasyon karesiyle eslesmedi (az_eslesme)"
KUYU_ARALIGI = {
    "sutun_mm": 19.128,
    "satir_mm": 18.503,
    "beklenen_mm": 19.3,
    "sapma": 0.0413,
    "tolerans": 0.03,
    "gecti": False,
}


def _saglayici(uyari: str, olcum: dict):
    from servers import ai_pro_hedef as hedef

    class _Hat:
        def process_image(self, frame, **k):
            return types.SimpleNamespace(
                success=True,
                error="",
                method="sabit_duzlem",
                mm_per_px=0.5,
                warnings=[uyari],
                pemf_valid=True,
                reliable=False,
                coord_frame="cabin_plane",
                layout={},
                kalibrasyon={
                    "kip": "sabit_duzlem",
                    "gecerli": False,
                    "engeller": ["kamera_oynamis"],
                    "olcum": dict(olcum),
                },
            ), {}

    class _S(hedef.PetriSaglayici):
        def _onbellek(self):
            return {"cfg": None}

        def _pipeline_kur(self, cache):
            return _Hat()

        def _overlay(self, pl, ctx, result):
            return None

        def _egitim_araligi(self):
            raise RuntimeError("aralık yok")

        def _adaylar(self, result):
            return []

    s = _S()
    s.kosulsuz = True
    return s


def _serit(s, meta):
    from servers import ai_router as air

    with (
        um.patch.object(air, "_saglayici_meta", return_value=meta),
        um.patch.object(air, "_aktif_saglayici", return_value=s),
    ):
        return air._saglayici_cache_alanlari()


def test_KRITIK_T14b_kuyu_araligi_OLCULEN_karede_neden_PLAKA_YOK_degil_KAMERA_nedeni():
    from servers import ai_router as air

    s = _saglayici(ARALIK_UYARISI, {"sahne": {"kayma_px": 1.64, "esik_px": 12.0}, "kuyu_araligi": KUYU_ARALIGI})
    r = s.localize(KARE, 0)
    meta = s.son_lokalizasyon_meta()
    assert r[0] is False, "kapının reddettiği kare lokalize sayıldı"
    assert "plaka_dogrulanmadi" not in meta and "plaka_ayrinti" not in meta, meta
    assert "kamera_oynamis" in meta["pemf_kapisi"]["nedenler"]
    a = _serit(s, meta)  # fiziksel neden şeritte EYLEM alanında (`kapi_eylem`); "plaka yok" uyarısı YOK
    assert "Kamera oynamış" in a["kapi_eylem"] and "bulunamadı" not in a["kapi_uyari"], a
    with um.patch.object(air, "_saglayici_meta", return_value=meta):
        durma = air._sabit_numune_neden_metni(None, dil="tr")
    assert "Kamera oynamış" in durma and "0 kuyu" not in durma and "bulunamadı" not in durma, durma


def test_KARSIT_T14b_aralik_OLCULMEYEN_karede_bos_kabin_PLAKA_YOK_AYNEN():
    s = _saglayici(SAHNE_UYARISI, {"sahne": {"eslesme": 3}})
    assert s.localize(KARE, 0)[0] is False
    meta = s.son_lokalizasyon_meta()
    assert meta["plaka_dogrulanmadi"] == "plakaYok" and meta["plaka_ayrinti"] == {"bulunan": 0, "beklenen": 3}, meta


def test_KARSIT_T14b_kalibrasyon_ozeti_YOK_ya_da_BOZUK_ise_T14_AYNEN():
    from servers import ai_pro_hedef as hedef

    assert hedef._kuyu_araligi_olculdu(types.SimpleNamespace()) is False
    assert hedef._kuyu_araligi_olculdu(types.SimpleNamespace(kalibrasyon=None)) is False
    assert hedef._kuyu_araligi_olculdu(types.SimpleNamespace(kalibrasyon={"olcum": None})) is False
    assert hedef._kuyu_araligi_olculdu(types.SimpleNamespace(kalibrasyon={"olcum": {"sahne": {}}})) is False
    assert (
        hedef._kuyu_araligi_olculdu(types.SimpleNamespace(kalibrasyon={"olcum": {"kuyu_araligi": KUYU_ARALIGI}}))
        is True
    )


@pytest.mark.parametrize("dil", ["tr", "en"])
def test_T14b_serit_metni_iki_dilde_KAMERA_nedeni(dil):
    from utils import ceviri

    s = _saglayici(ARALIK_UYARISI, {"kuyu_araligi": KUYU_ARALIGI})
    jeton = ceviri.istek_dili_var.set(dil)
    try:
        s.localize(KARE, 0)  # kapı mesajı `kapi_cevir` ile localize anında dile çevrilir
        a = _serit(s, s.son_lokalizasyon_meta())
    finally:
        ceviri.istek_dili_var.reset(jeton)
    metin = a["kapi_eylem"]
    assert "plaka" not in a["kapi_uyari"].lower() and "plate" not in a["kapi_uyari"].lower(), a
    assert metin, metin
    if dil == "tr":
        assert "Kamera oynamış" in metin and "bulunamadı" not in metin, metin
    if dil == "en":
        assert not any(c in metin for c in "çğıöşüÇĞİÖŞÜ"), metin
        assert "camera" in metin.lower() and "not found" not in metin.lower(), metin
