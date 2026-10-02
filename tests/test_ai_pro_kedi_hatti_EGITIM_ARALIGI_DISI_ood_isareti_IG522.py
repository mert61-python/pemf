# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""İG-5.22 (D1.85'e ek; Y49) — kedi AI Pro hattı eğitim aralığı DIŞI hedefi `ood` olarak İŞARETLER (sürüş değişmez).

ÖLÇÜLEN KUSUR (D0 İG-5.22): araştırma sağlayıcıları (fantom/petri) hedef konumu modelin referans örnekleminin dışındaysa
`ood` üretiyor; kedi sağlayıcısının meta'sı her zaman `{}` → `/propose` `specs.ood` kedi hattında HEP `false`. D0: 50
rastgele hedefin 36'sı |z| > 2,5 iken hiçbiri işaretlenmedi. Onay ekranının "araştırma amaçlı model tahmini / eğitim aralığı
dışı" uyarısı kedi hattında hiç çıkmıyordu.

DÜZELTME BEKLENTİSİ: kedi hattı da AYNI ölçütü kullanır — konum em_kedi'nin `xai_ref_stats()` referans örnekleminin
(x, y, z) aralığı dışındaysa `ood: true`. ⚠️ Y49 (sahip): yalnız GÖSTERİM/İZ — sürüş değişmez (yeni red ya da kıskaç yok,
Ö.4-Y9). Kare üstü hedef adayı kedi hattında yine üretilmez (veteriner sözleşmesi).
"""

from __future__ import annotations

import pytest


@pytest.fixture
def kedi(monkeypatch):
    from servers import ai_pro_hedef
    from servers import ai_router as air

    from ai_hub.em_kedi import inference_em_kedi as iek

    bg = iek.xai_ref_stats()["background"]
    aralik = [(float(bg[:, i].min()), float(bg[:, i].max())) for i in range(3)]
    ic = tuple((a + b) / 2 for a, b in aralik)
    dis = (aralik[0][1] + 40.0, ic[1], ic[2])  # x eğitim örnekleminin üst sınırının 4 cm ötesinde
    kutu = {"konum": ic}
    monkeypatch.setattr(air, "ai_service_enabled", lambda: False)
    monkeypatch.setattr(air, "_localize_organ_cpu", lambda frame, oid: (True, *kutu["konum"], 0.9, None, True, None))
    sag = ai_pro_hedef.saglayici_al("kedi")
    return sag, kutu, ic, dis, air


def test_KRITIK_IG522_kedi_hedefi_egitim_araligi_DISINDA_ood_True(kedi):
    sag, kutu, ic, dis, _air = kedi
    kutu["konum"] = dis
    sonuc = sag.localize("kare", 2)
    assert sag.son_lokalizasyon_meta().get("ood") is True, (
        f"eğitim aralığı dışındaki kedi hedefi {dis} OOD işaretlenmedi: {sag.son_lokalizasyon_meta()}"
    )
    assert sonuc[0] is True and sonuc[1] == dis[0], f"Y49: işaret sürüşü DEĞİŞTİRMEMELİ (lokalizasyon {sonuc[:4]})"


def test_KARSIT_IG522_aralik_ICINDE_ood_False_ve_aday_URETILMEZ(kedi):
    sag, kutu, ic, dis, _air = kedi
    kutu["konum"] = ic
    sag.localize("kare", 2)
    meta = sag.son_lokalizasyon_meta()
    assert meta.get("ood") is False, f"aralık içindeki hedef OOD işaretlendi: {meta}"
    assert not meta.get("targets"), "kedi hattı kare üstü hedef adayı üretmemeli (veteriner sözleşmesi)"


def test_KRITIK_IG522_ood_ONAY_akisinin_cache_alanlarina_akar(kedi, monkeypatch):
    """Üç lokalizasyon yolu (hazırlık / seans / mobil kare) `_saglayici_cache_alanlari()` yazar; `/propose` `specs.ood`u
    oradan okur (`ai_router` `"ood": bool(c.get("ood"))`)."""
    sag, kutu, ic, dis, air = kedi
    monkeypatch.setattr(air, "_ai_hedef_modeli", "kedi")
    kutu["konum"] = dis
    sag.localize("kare", 2)
    assert air._saglayici_cache_alanlari().get("ood") is True, air._saglayici_cache_alanlari()
    kutu["konum"] = ic
    sag.localize("kare", 2)
    assert air._saglayici_cache_alanlari().get("ood") is False, "önceki karenin OOD işareti BAYAT kaldı"


def test_KARSIT_IG522_lokalize_EDILEMEYEN_karede_ood_YOK(kedi, monkeypatch):
    sag, kutu, ic, dis, air = kedi
    kutu["konum"] = dis
    sag.localize("kare", 2)
    # Lokalize EDİLEMEYEN sonuç, aralık DIŞI kalıntı koordinat taşısa bile işaretlenmez (konum geçersiz).
    monkeypatch.setattr(air, "_localize_organ_cpu", lambda frame, oid: (False, *dis, 0.0, None, True, None))
    sag.localize("kare", 2)
    assert not sag.son_lokalizasyon_meta().get("ood"), "lokalize edilemeyen karede önceki OOD işareti kaldı"
