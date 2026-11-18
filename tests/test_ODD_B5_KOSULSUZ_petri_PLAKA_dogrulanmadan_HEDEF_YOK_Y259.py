# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""ODD B-5 (ODK-B keşfi 18-11, sahip 12–14.png) — KOŞULSUZ kipte BOŞ kabinde sahte kuyu.

ÖLÇÜLEN: koşulsuz kipte hocanın tüketim kapısı kesmediği için iki bobin halkasının ortası 2 "kuyu" (%92–94) sayıldı: "Kuyu ✓ Bulundu",
"Konumlandı ✓", "3B konum ölçüldü ✓", sayaç "Kanser: 2"; öneri ODAK kapısında durdu ("Öneri alınamadı — konumlandırma sürüyor"), 2 dk sonra
"Konumlandırma tamamlanamadı" (aynı ekranda "Konumlandı ✓" ile çelişki). Koşullu kip boş kabinde 0 kuyu (doğru).
SÖZLEŞME (Y259 ilkesi — boş kabinde 0 hedef): koşulsuz kipte plaka ODAK ızgara oturtmasıyla (`petri_izgarasi`, sürüşün de tek kaynağı)
doğrulanır; oturmayan karede hedef YOK, kare lokalize SAYILMAZ, şerit / öneri ipucu NEDENİ ("Plaka doğrulanmadı …") söyler. Gerçek plaka
(≥ 3 kuyu, iki satır + iki sütun, sapma sınır içinde) AYNEN lokalize olur. Koşullu kip DEĞİŞMEZ (oturtma çağrılmaz).
GERÇEK: sağlayıcının `localize`i + hocanın tüketim kapısı + ODAK ızgarası; sahte: CV hattı sonucu ve adaylar.
"""

from __future__ import annotations

import types

import numpy as np
import pytest
from petri_plaka_aparati import plaka_adaylari

KARE = np.zeros((8, 8, 3), dtype=np.uint8)
PLAKA_TR = (
    "Plaka doğrulanmadı: görülen kuyular 24'lük plaka düzenine oturmadı (boş kabinde ya da plaka eğikken hedef gösterilmez). "
    "Plakayı kabinin ortasına düz yerleştirin ve tüm kuyuların kamerada göründüğünden emin olun."
)


def _sonuc(warnings=("layout_mismatch",)):
    return types.SimpleNamespace(
        success=True,
        error="",
        method="sabit_duzlem",
        mm_per_px=0.5,
        warnings=list(warnings),
        pemf_valid=True,
        reliable=False,  # bu kabin: sabit düzlem
        coord_frame="cabin_aruco",
        layout={},
    )


def _saglayici(adaylar, kosulsuz=True, warnings=("layout_mismatch",)):
    from servers import ai_pro_hedef as hedef

    class _Hat:
        def process_image(self, frame, **k):
            return _sonuc(warnings), {}

    class _S(hedef.PetriSaglayici):
        def _onbellek(self):
            return {"cfg": None}

        def _pipeline_kur(self, cache):
            return _Hat()

        def _overlay(self, pl, ctx, result):
            return None

        def _egitim_araligi(self):
            raise RuntimeError("sonda: aralık yok")

        def _adaylar(self, result):
            return [dict(a) for a in adaylar]

    s = _S()
    s.kosulsuz = kosulsuz
    return s


def _iki_halka():
    """Boş kabin: iki bobin halkasının ortası — iki komşu "kuyu" (tek satır, ızgara kurulamaz)."""
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
        },
        {
            "px": (6.0, 4.0),
            "bbox": (4, 2, 8, 6),
            "x": 40.0,
            "y": -165.0,
            "z": 0.0,
            "organ_id": 1,
            "reliability": 0.92,
            "oncelik": 0.9,
            "label": "Kuyu B4",
            "id": 0,
        },
    ]


def test_KRITIK_B5_bos_kabin_iki_halka_HEDEF_YOK_lokalize_DEGIL_ve_NEDEN(monkeypatch):
    from servers import ai_pro_hedef as hedef

    s = _saglayici(_iki_halka())
    sonuc = s.localize(KARE, 0)
    meta = s.son_lokalizasyon_meta()
    assert sonuc[0] is False, f"boş kabinde (plaka doğrulanmadan) hedef lokalize SAYILDI: {sonuc[:5]}"
    assert meta["targets"] == [] and meta["odak_adaylar"] == [], f"boş kabinde hedef gösterildi: {meta['targets']}"
    assert meta.get("plaka_dogrulanmadi") == "plakaYok", meta.get("plaka_dogrulanmadi")
    assert hedef.kapi_uyari_metni(meta["pemf_kapisi"]) == PLAKA_TR
    assert s.ipucu(True, "Kuyu (otomatik)") == PLAKA_TR, "öneri ipucu (409) nedeni söylemiyor"


def test_KRITIK_B5_izgaraya_OTURMAYAN_uc_kuyu_plakaUyumsuz_HEDEF_YOK():
    dagin = plaka_adaylari()[:6]
    dagin[1] = {**dagin[1], "x": dagin[1]["x"] + 25.0}  # A2 ızgaradan 25 mm sapık
    dagin[4] = {**dagin[4], "z": dagin[4]["z"] - 30.0}
    s = _saglayici([dagin[0], dagin[1], dagin[4], *plaka_adaylari()[6:8]])
    assert s.localize(KARE, 0)[0] is False
    assert s.son_lokalizasyon_meta().get("plaka_dogrulanmadi") in ("plakaUyumsuz", "plakaYok")


def test_KARSIT_B5_gercek_plaka_KOSULSUZ_kipte_AYNEN_lokalize(monkeypatch):
    s = _saglayici(plaka_adaylari())
    sonuc = s.localize(KARE, 0)
    meta = s.son_lokalizasyon_meta()
    assert sonuc[0] is True and len(meta["targets"]) == 24 and "plaka_dogrulanmadi" not in meta, (
        sonuc[:5],
        meta.get("plaka_dogrulanmadi"),
    )


def test_KARSIT_B5_yari_dolu_plaka_KOSULSUZ_lokalize_ODK11():
    s = _saglayici(plaka_adaylari(eksik=("A6", "B5", "C1", "D3", "D6")))
    assert s.localize(KARE, 0)[0] is True


def test_KARSIT_B5_KOSULLU_kipte_oturtma_CAGRILMAZ(monkeypatch):
    s = _saglayici(_iki_halka(), kosulsuz=False)

    def _cagrilmamali(_adaylar):
        raise AssertionError("koşullu kipte ODAK oturtması çağrıldı")

    monkeypatch.setattr(s, "_plaka_engeli", _cagrilmamali)
    s.localize(KARE, 0)  # hocanın kapısı (layout_mismatch) keser — B-5 değil
    assert "plaka_dogrulanmadi" not in s.son_lokalizasyon_meta()
    # hocanın kapısı GEÇERKEN de (uyarısız sonuç) koşullu kipte oturtma YOK — koşullu kip davranışı AYNEN
    s2 = _saglayici(_iki_halka(), kosulsuz=False, warnings=())
    monkeypatch.setattr(s2, "_plaka_engeli", _cagrilmamali)
    s2.localize(KARE, 0)
    assert "plaka_dogrulanmadi" not in s2.son_lokalizasyon_meta() and s2.son_lokalizasyon_meta()["targets"], (
        s2.son_lokalizasyon_meta()
    )


def test_B5_oturtma_HESAPLANAMAZSA_fail_closed(monkeypatch):
    from ai_hub.odak import oneri

    def _patla(_k):
        raise FileNotFoundError("numune.json (test)")

    monkeypatch.setattr(oneri, "petri_izgarasi", _patla)
    s = _saglayici(plaka_adaylari())
    assert s.localize(KARE, 0)[0] is False and s.son_lokalizasyon_meta()["plaka_dogrulanmadi"] == "plakaYok"


@pytest.mark.parametrize(
    "dil,beklenen",
    [("en", "Plate not verified: the visible wells do not fit the 24-well plate layout")],
)
def test_B5_neden_INGILIZCE(dil, beklenen):
    from servers import ai_pro_hedef as hedef
    from utils import ceviri

    jeton = ceviri.istek_dili_var.set(dil)
    try:
        m = hedef.kapi_uyari_metni({"surulebilir": False, "nedenler": ["plaka_dogrulanmadi"]})
    finally:
        ceviri.istek_dili_var.reset(jeton)
    assert m.startswith(beklenen), m
