# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""1-E inceleme i-15.1 · Y51 — araştırma API'si (`/api/ai/vision/em_fantom`, `/em_petri`) EĞİTİM aralığı dışı `duty_sum`'la
üretilen sonucu Y51 etiketiyle döndürür.

ÖLÇÜLEN KUSUR: uçlar `duty_sum`'u FORM alanı olarak kabul edip doğrudan modele veriyordu; aralık dışı değerde sonuç
"eğitim aralığı dışı — güvenilmez" etiketi OLMADAN dönüyordu (canlı E barı Y51'den beri etiketliyor; arayüz bu yolu
kullanmıyor ama API çağıranı ve özel kabin YAML'ı kullanır). Kural modele genel (Y51).

GERÇEK: uçlar, CV boru hattı, aralık (modelin `xai_ref_stats` referans örnekleminden — canlı barla AYNI yardımcı). Sahte:
vekil tahmini ve YOLO (bu yalıtılmış ortamda ağırlık yok) — `test_em_ongorucu_…` aparatı.
"""

from __future__ import annotations

import pytest

# Aparat (fikstürler) mevcut uç testinden: gerçek uç + gerçek CV hattı, sahte vekil.
from test_em_ongorucu_SONLU_OLMAYAN_girdi_PIKSEL_kipi_ve_TOPLAM_sure import (  # noqa: F401
    _KayitciFantom,
    fantom_hatti,
    fantom_ucu,
    petri_hatti,
    petri_ucu,
)


def _aralik(model):
    from servers import efield_live

    a = efield_live.egitim_duty_araligi(model)
    assert a is not None, f"aparat: {model} eğitim duty aralığı okunamadı"
    return a


@pytest.mark.parametrize("uc", ["em_fantom", "em_petri"])
def test_KRITIK_aralik_DISI_duty_sum_sonucu_Y51_etiketi_tasir(request, uc):
    if uc == "em_fantom":
        c, _ef, kutu, govde = request.getfixturevalue("fantom_ucu")
        kutu["ong"] = _KayitciFantom()
        model = "fantom"
    else:
        c, _kutu, govde, _xai = request.getfixturevalue("petri_ucu")
        model = "petri"
    alt, ust = _aralik(model)
    disarida = round(alt / 2, 3)  # tipik seans (5 bobin × %30 = 1,5) gibi aralığın ALTINDA
    r = c.post(f"/api/ai/vision/{uc}", data={"image_base64": govde, "duty_sum": str(disarida)})
    assert r.status_code == 200, r.text[:200]
    j = r.json()
    assert j.get("dutyEgitimAraligiDisi") is True, (
        f"{uc}: duty_sum={disarida} eğitim aralığı [{alt:.2f}, {ust:.2f}] DIŞINDA ama sonuç Y51 etiketi taşımıyor"
    )
    assert j.get("dutyEgitimAraligi") == [round(alt, 2), round(ust, 2)]


@pytest.mark.parametrize("uc", ["em_fantom", "em_petri"])
def test_KARSIT_aralik_ICI_ve_VARSAYILAN_duty_etiketsiz(request, uc):
    if uc == "em_fantom":
        c, _ef, kutu, govde = request.getfixturevalue("fantom_ucu")
        kutu["ong"] = _KayitciFantom()
        model = "fantom"
    else:
        c, _kutu, govde, _xai = request.getfixturevalue("petri_ucu")
        model = "petri"
    alt, ust = _aralik(model)
    r = c.post(f"/api/ai/vision/{uc}", data={"image_base64": govde, "duty_sum": str(round((alt + ust) / 2, 3))})
    assert r.status_code == 200 and "dutyEgitimAraligiDisi" not in r.json(), r.text[:200]
