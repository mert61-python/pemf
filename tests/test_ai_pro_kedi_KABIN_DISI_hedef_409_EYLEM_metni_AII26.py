# -*- coding: utf-8 -*-
"""AII-2.6 (AI incelemesi, A2) — KLİNİK METİN: kedi AI Pro'da organ konumu kabin DIŞINDA ölçülünce `/propose` 409 DOĞRU EYLEMİ söyler.

KUSUR [ÖLÇTÜM K4.kabin_disi_409; AI-1 açık #3]: organ güvenle bulunup (güven 0,7 ≥ 0,3) konumu kabin dışında ölçülünce
(`_extract_organ_target` D1.85 reddi) 409 metni "Hayvan görünüyor ama Böbrek seçilemedi — kamerayı biraz çevirip açıyı değiştirin"
diyor. Gerçek neden ölçülen konumun kabin dışında olması (kabin işareti pozu / kabin yapılandırması) — açıyı değiştirmek çözmez,
veteriner aynı hataya kilitlenir ("hata mesajı EYLEM söylesin"). Sürüş DEĞİŞMEZ (hedef yine reddedilir; plan §3.10).
Sahte EN ALT katta (cat_organ `predict` sonucu); `KediSaglayici.localize` → `_localize_organ_cpu` → `_extract_organ_target` → `/propose` GERÇEK.
Yol: tests/test_ai_pro_kedi_KABIN_DISI_hedef_409_EYLEM_metni_AII26.py"""

from __future__ import annotations

import time

import numpy as np
import pytest


def _sonuc(organs):
    return {
        "organs": organs,
        "_overlay_bgr": None,
        "pose_classifier": {"type": "sphinx"},
        "pnp_fit": {"residual_px": 100.0, "mirror_warning": False},
        "anatomic_consistency": {"passed": True},
        "kabin_yapilandirmasi": {"yuklendi": True, "hata": None},
    }


@pytest.fixture()
def kedi(monkeypatch):
    from servers import ai_approval
    from servers import ai_pro_hedef as aph
    from servers import ai_router as air

    durum = {"sonuc": None}

    class _Clf:
        def predict(self, path, render=True, target_oid=None):
            return durum["sonuc"]

    monkeypatch.setattr(air, "ai_service_enabled", lambda: False)
    monkeypatch.setattr(air, "_get_or_load_catorgan", lambda: _Clf())
    monkeypatch.setattr(air, "_ai_hedef_modeli", "kedi")
    monkeypatch.setattr(air, "_predict_and_drive", lambda x, y, z, oid: ([0.5] * 7, [0.0] * 7, 0.01))
    monkeypatch.setattr(aph.KediSaglayici, "xai_sensitivity", lambda self, *a, **k: None)
    monkeypatch.setattr(ai_approval, "_store", {})
    monkeypatch.setattr(air, "_ai_organ_cache", dict(air._ai_organ_cache))
    sag = aph.saglayici_al("kedi")
    eski = dict(getattr(sag, "_meta", None) or {})
    yield air, sag, durum
    sag._meta = eski
    sag.__dict__.pop("_kabin_disi", None)


def _propose(air, sag, durum, organs, oid=2):
    from fastapi import HTTPException

    durum["sonuc"] = _sonuc(organs)
    r = sag.localize(np.zeros((32, 32, 3), np.uint8), oid)
    air._ai_organ_cache.update(
        {
            "x_mm": r[1],
            "y_mm": r[2],
            "z_mm": r[3],
            "reliability": r[4],
            "localized": r[0],
            "at": time.time(),
            "organ_id": oid,
            "kedi_var": r[6],
            "model": "kedi",
            **air._saglayici_cache_alanlari(),
        }
    )
    try:
        air.propose_ai_pro(None, air.AiProProposePayload(organ_id=oid, model="kedi"))
        return r, 200, ""
    except HTTPException as e:
        return r, e.status_code, str(e.detail)


def test_KRITIK_kabin_disi_hedefte_409_KABIN_ISARETI_eylemini_soyler(kedi):
    air, sag, durum = kedi
    r, kod, metin = _propose(air, sag, durum, {2: {"coord_cabin_cm": [60.0, -45.0, -40.0], "reliability": 0.7}})
    assert r[0] is False and kod == 409, "düzenek: kabin dışı hedef reddedilmeli (sürüş değişmez)"
    assert "kabin" in metin.lower() and "işaret" in metin.lower(), (
        f"409 metni gerçek nedeni / eylemi söylemiyor: {metin}"
    )
    assert "açıyı değiştirin" not in metin, f"409 metni YANLIŞ eylem söylüyor (açı değiştirmek çözmez): {metin}"


def test_KARSIT_organ_GORUNMUYORSA_aci_eylemi_ve_kedi_yoksa_kamera_eylemi_aynen(kedi):
    air, sag, durum = kedi
    _r, kod, metin = _propose(air, sag, durum, {3: {"coord_cabin_cm": [1.0, 1.0, 1.0], "reliability": 0.7}})
    assert kod == 409 and "kamerayı biraz çevirip açıyı değiştirin" in metin, metin
    _r, kod, metin = _propose(air, sag, durum, {2: {"coord_cabin_cm": [1.0, 1.0, 1.0], "reliability": 0.1}})
    assert kod == 409 and "kamerayı biraz çevirip açıyı değiştirin" in metin, f"düşük güven karşıtı: {metin}"
    _r, kod, metin = _propose(air, sag, durum, {})
    assert kod == 409 and "hayvan kadrajda görünmüyor" in metin, metin
    r, kod, _m = _propose(air, sag, durum, {2: {"coord_cabin_cm": [1.0, 1.0, 1.0], "reliability": 0.7}})
    assert r[0] is True and kod == 200, "kabin içi hedef önerilmeli (sürüş değişmez)"
