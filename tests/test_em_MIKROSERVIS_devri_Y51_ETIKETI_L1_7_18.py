# -*- coding: utf-8 -*-
"""L1-7.18 (21'in devri → 22-SON) · i-15.1 açığı — GPU mikroservisine DEVREDİLEN `/api/ai/vision/em_fantom` ve `/em_petri` yanıtı da
eğitim aralığı dışı `duty_sum`'da Y51 etiketini taşır.

ÖLÇÜLEN (D1F §i-15.1 "Açık"): gömülü yol `_y51_duty_etiketi` ile `dutyEgitimAraligiDisi` + `dutyEgitimAraligi` ekliyordu; mikroservis devri
(`ai_service_enabled` → `_kapili_devret`) yanıtı servisten geldiği gibi dönüyordu — aynı istek GPU profilinde etiketsizdi. Artık devir
yanıtı da AYNI yardımcıdan geçer; istek `duty_sum` vermediyse servis kabin YAML'ının değerini kullandığı için aynı YAML burada (model
YÜKLENMEDEN) okunur. Değer gizlenmez / kırpılmaz (Ö.4-Y9).
GERÇEK: uçlar, modalite kapısı (`_kapili_devret`), aralık (modelin `xai_ref_stats`). Sahte EN ALTTA: servise HTTP (`delegate_infer`).
"""

from __future__ import annotations

import pytest

# Aparat: mevcut uç testleri (gerçek uç + gerçek CV hattı).
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


def _devir_kur(request, monkeypatch, uc):
    from servers import ai_router

    if uc == "em_fantom":
        c, _ef, kutu, govde = request.getfixturevalue("fantom_ucu")
        kutu["ong"] = _KayitciFantom()
        model = "fantom"
    else:
        c, _kutu, govde, _xai = request.getfixturevalue("petri_ucu")
        model = "petri"
    giden = []

    async def _sahte_servis(name, **kw):
        giden.append(name)
        return {"status": "success", "success": True, "n_tumor": 1, "paneller": []}

    monkeypatch.setattr(ai_router, "ai_service_enabled", lambda: True)
    monkeypatch.setattr(ai_router, "delegate_infer", _sahte_servis)
    return c, govde, model, giden


@pytest.mark.parametrize("uc", ["em_fantom", "em_petri"])
def test_KRITIK_MIKROSERVIS_devri_aralik_DISI_duty_Y51_etiketi_TASIR(request, monkeypatch, uc):
    c, govde, model, giden = _devir_kur(request, monkeypatch, uc)
    alt, ust = _aralik(model)
    r = c.post(f"/api/ai/vision/{uc}", data={"image_base64": govde, "duty_sum": str(round(alt / 2, 3))})
    assert r.status_code == 200, r.text[:200]
    assert giden == [uc], f"aparat: devir yolu koşmadı: {giden}"
    j = r.json()
    assert j.get("dutyEgitimAraligiDisi") is True, (
        f"{uc}: GPU devri yanıtı aralık dışı duty'de Y51 etiketi taşımıyor: {j}"
    )
    assert j.get("dutyEgitimAraligi") == [round(alt, 2), round(ust, 2)]


@pytest.mark.parametrize("uc", ["em_fantom", "em_petri"])
def test_KARSIT_devirde_aralik_ICI_etiketsiz_VARSAYILAN_kabin_YAML_gomulu_yolla_AYNI(request, monkeypatch, uc):
    from servers import ai_router

    c, govde, model, giden = _devir_kur(request, monkeypatch, uc)
    alt, ust = _aralik(model)
    r = c.post(f"/api/ai/vision/{uc}", data={"image_base64": govde, "duty_sum": str(round((alt + ust) / 2, 3))})
    assert r.status_code == 200 and "dutyEgitimAraligiDisi" not in r.json(), r.text[:200]
    r2 = c.post(f"/api/ai/vision/{uc}", data={"image_base64": govde})
    assert r2.status_code == 200, r2.text[:200]
    beklenen = ai_router._y51_duty_etiketi(model, None, ai_router._kabin_cfg_hafif(model))
    assert {k: r2.json().get(k) for k in ("dutyEgitimAraligiDisi", "dutyEgitimAraligi") if k in r2.json()} == beklenen
    assert giden == [uc, uc]
