# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""ODK9 · Y283 (sahip 13 Kasım 2026: "fantom İPTAL / ERTELENDİ … fantom AI Pro sürüşü fail-closed kapalı (TR + EN neden)").
SÖZLEŞME: fantom AI Pro önerisi / mühürlü sürüşü ODAK katmanında SÜRMEZ — araştırma bayrağı (`PEMF_ARASTIRMA_AIPRO_FANTOM`) AÇIK olsa da;
`/propose` 409 + eylem söyleyen neden (TR + EN), `predict` SIFIR. Petri ve kedi ETKİLENMEZ. Fantoma özel kalanlar istem 45 "F"de.
EN ALT sahte: ODAK modeli (fizikle tutan); alan tablosu + kalibrasyon + ODAK planı GERÇEK (aparat `test_ODK_ai_pro_odak_entegrasyon`)."""

from __future__ import annotations

import pytest
from test_ODK_ai_pro_odak_entegrasyon import M2, _hazirlik, o  # noqa: F401 — aparat


def test_KRITIK_Y283_sabit_VARSAYILAN_kapali():
    from servers import ai_pro_hedef

    assert ai_pro_hedef.FANTOM_ODAK_ERTELENDI is True


@pytest.mark.parametrize(
    "dil,parca", [("tr", "Fantom AI Pro sürüşü şimdilik kapalı"), ("en", "Phantom AI Pro driving is disabled")]
)
def test_KRITIK_Y283_fantom_ONERISI_409_EYLEM_iki_dilde_bayrak_ACIK_olsa_da(o, monkeypatch, dil, parca):
    from servers import ai_pro_hedef

    monkeypatch.setattr(ai_pro_hedef, "FANTOM_ODAK_ERTELENDI", True)  # aparat açmıştı; ürün varsayılanı
    _hazirlik(o)  # aparat araştırma + fantom bayraklarını AÇAR — kapı yine de sürmez
    r = o.c.post(
        "/api/ai/pro/propose",
        json={"organ_id": 0, "duration_minutes": 5, "model": "fantom", "doz_mT": 0.4},
        headers={"X-PEMF-Dil": dil},
    )
    assert r.status_code == 409 and parca in r.json()["detail"], r.text[:300]
    assert {"tr": "Petri", "en": "Well Plate"}[dil] in r.json()[
        "detail"
    ]  # eylem: petri (EN Y168: "Well Plate") / elle seans


def test_KRITIK_Y283_muhurlu_fantom_PREDICT_SIFIR(o, monkeypatch):
    from servers import ai_pro_hedef

    monkeypatch.setattr(ai_pro_hedef, "FANTOM_ODAK_ERTELENDI", True)
    o.tekil.odak_ayari = {"doz_mT": 0.4, "kip": "FANTOM", "hedef_etiket": "", "frek_hz": 100.0}
    assert o.tekil.predict(*M2, 1) == ([0.0] * 7, [0.0] * 7, 0.0)
    plan = ai_pro_hedef.odak_plani(o.tekil, {"x_mm": M2[0], "y_mm": M2[1], "z_mm": M2[2]}, 1, 0.4)
    assert plan["engel"] == "fantomErtelendi" and plan["duty"] == [0.0] * 7


def test_KARSIT_Y283_petri_ve_kedi_ETKILENMEZ():
    from servers import ai_pro_hedef

    class _P:
        ad = "petri"

        def son_lokalizasyon_meta(self):
            return {}

    class _K:
        ad = "kedi"

        def son_lokalizasyon_meta(self):
            return {}

        def odak_kedi_girdisi(self):
            return None

    p = ai_pro_hedef.odak_plani(_P(), {"x_mm": 0.0, "y_mm": 0.0, "z_mm": 0.0, "target_label": ""}, 1, 0.4, "KUYUCUK")
    k = ai_pro_hedef.odak_plani(_K(), {"x_mm": 0.0, "y_mm": 0.0, "z_mm": 0.0}, 0, 0.4)
    assert p["engel"] != "fantomErtelendi" and k["engel"] != "fantomErtelendi", (p["engel"], k["engel"])
