# -*- coding: utf-8 -*-
"""Y306 (sahip 19-11 tezgâh denemesi 4c): "Canlı E-Alanı" kutusu "Tüm petri" hedefinde de "Hedef kuyu" diyordu — oysa o kipte hedef
satırı TÜM kuyuların ortalamasıdır (`oneri._e_degerleri`: T = bütün kuyular). Arayüz hedef türünü bilmiyordu. SÖZLEŞME: sağlayıcı
sürdüğü planın ODAK KİPİNİ canlı E'ye yazar (`son_odak_e["kip"]`), `efield_live` onu (yalnız metin) taşır — bobinler dururken de.
GERÇEK: PetriSaglayici.predict (plan sahte) + efield_live.odak_guncelle / compute."""

from __future__ import annotations


def test_KRITIK_saglayici_TUM_PETRI_kipini_canli_E_ye_yazar(monkeypatch):
    from servers import ai_pro_hedef as hedef

    p = hedef.PetriSaglayici()
    hedef.odak_ayarla(p, {"doz_mT": 1.4, "kip": "TUM_PETRI"}, "Tüm petri")
    plan = {
        "engel": None,
        "duty": [0.2] * 7,
        "faz": [0.0] * 7,
        "e_hedef_Vm": 0.0027,
        "e_cevre_Vm": None,
        "e_ortam": "kuyu",
    }
    monkeypatch.setattr(hedef, "odak_plani", lambda *a, **k: dict(plan))
    p.predict(0.0, -160.0, 0.0, 1)
    assert p.son_odak_e == {"cancer": 0.0027, "healthy": None, "ortam": "kuyu", "kip": "TUM_PETRI"}


def test_KRITIK_efield_live_KIP_tasinir_bobinler_DURURKEN_de_gecersiz_None():
    from servers import efield_live as ef

    ef.set_context([{"centroid_cabin_mm": [0.0, 0.0, 0.0]}], 1, "petri")
    try:
        calisan = [{"running": True, "dutyCycle": 30.0, "magneticMt": 0.8, "measuredFields": ["magneticMt"]}]
        ef.odak_guncelle({"cancer": 0.0027, "healthy": None, "ortam": "kuyu", "kip": "TUM_PETRI"})
        assert ef.odak_degeri()["kip"] == "TUM_PETRI"
        assert ef.compute(calisan)["kip"] == "TUM_PETRI"
        assert ef.compute([{"running": False}])["kip"] == "TUM_PETRI"
        ef.odak_guncelle({"cancer": 0.0027, "healthy": 0.001, "ortam": "kuyu", "kip": 5})
        assert ef.compute(calisan)["kip"] is None
        ef.odak_guncelle({"cancer": 0.0027, "healthy": 0.001, "ortam": "kuyu"})  # eski çağıran (kipsiz) → None
        assert ef.compute(calisan)["kip"] is None
    finally:
        ef.odak_guncelle(None)
        ef.set_context([])
