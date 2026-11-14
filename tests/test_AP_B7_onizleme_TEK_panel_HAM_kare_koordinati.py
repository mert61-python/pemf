# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""AP · B7 (istem 48 · S-AP.3 "tek kamera görüntüsü", tezgâh 13 Kasım 2026): AI Pro önizlemesindeki numaralı hedef halkaları plakanın
üstüne değil 6 panelli özetin (`07_combined`) ORTASINA çiziliyordu — halkanın `pxn`'i HAM kareye göre, gösterilen görüntü ise 3×2 ızgara
+ başlık bantlarıydı. Artık önizleme TEK panel (petri `04_classify`, fantom `04_tumors`) ve başlık bandı kırpılmış: panel ham kareyle
aynı piksel ızgarasında → `pxn × boyut` = kuyu merkezi."""

import numpy as np
import pytest


def _hat(paneller):
    class _Hat:
        def render_panels(self, ctx, result, lang=None):
            return paneller

    return _Hat()


@pytest.mark.parametrize("ad,panel_adi", [("petri", "04_classify"), ("fantom", "04_tumors")])
def test_KRITIK_onizleme_TEK_panel_bandi_KIRPILMIS_ham_kare_boyutunda(ad, panel_adi):
    from servers import ai_pro_hedef as h

    kare = np.zeros((60, 80, 3), np.uint8)
    kare[30, 40] = (1, 2, 3)  # kuyu merkezi işareti (ham kare koordinatı)
    bant = np.full((12, 80, 3), 200, np.uint8)
    panel = np.vstack([bant, kare])
    ozet = np.zeros((300, 400, 3), np.uint8)
    ov = h.SAGLAYICILAR[ad]._overlay(_hat({"07_combined": ozet, panel_adi: panel}), {"img_und": kare}, None)
    assert ov is not None and ov.shape == kare.shape, "önizleme ham kare boyutunda olmalı (halkalar pxn × boyut)"
    assert tuple(ov[30, 40]) == (1, 2, 3), "kuyu merkezi önizlemede ham karedeki yerinde değil"


def test_boyut_uymazsa_ON_IZLEME_ham_kareye_duser():
    from servers import ai_pro_hedef as h

    kare = np.zeros((60, 80, 3), np.uint8)
    ov = h.SAGLAYICILAR["petri"]._overlay(
        _hat({"04_classify": np.zeros((70, 90, 3), np.uint8)}), {"img_und": kare}, None
    )
    assert ov is None  # döngü ham kareyi yayınlar


def test_kedi_saglayicisi_etkilenmez():
    from servers import ai_pro_hedef as h

    assert not hasattr(h.SAGLAYICILAR["kedi"], "onizleme_paneli") or not h.SAGLAYICILAR["kedi"].onizleme_paneli
