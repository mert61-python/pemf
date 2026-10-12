# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""AIK K4 · AI incelemesi §8 #8 — petri makullik reddi (422) kullanıcıya ORTAM DEĞİŞKENİ adını göstermez; EYLEMİ söyler.

ÖLÇÜLEN (AI incelemesi A3; AIK önce-kırmızı): tekil kap kipinin (`user_message`) ve plaka kipinin (`plate_user_message`) ret metni
"… kapatılabilir (sunucu tarafında PEMF_AI_PLAUSIBILITY_GUARD=0)." ile bitiyordu. Metin AI Hub'da 422 ayrıntısı olarak operatöre
gösterilir (`ai_router._petri_reject_message`); operatör ortam değişkenini değiştiremez (sunucu yapılandırması) ve "hata mesajı
eylem söylesin" ilkesine aykırı ham teknik ad görür. Eylem ZATEN metinde: "Petri modülündeki 'Gelişmiş (araştırma) ayarları'
bölümünden … kapatılabilir". Kaçış kapağının KENDİSİ (`PEMF_AI_PLAUSIBILITY_GUARD`) DEĞİŞMEZ — yalnız kullanıcı metninden çıkar.
"""

from __future__ import annotations

import pytest


def _metinler():
    from ai_hub.inference_petri_dish import plausibility as pl

    tekil = pl.user_message({"circularity_med": 0.31, "conf_med": 0.42, "max_area_frac": 0.61})
    plaka = pl.plate_user_message({"n_inliers": 0, "ecc_ok": False})
    _ok, olc = pl.evaluate_plate(None, guard=True)  # ölçülemeyen plaka → fail-closed ret, mesaj ÜRÜNÜN kendi yolundan
    assert not _ok and olc.get("message"), "aparat: plaka kipi reddi mesaj üretmedi"
    return {"tekil": tekil, "plaka": plaka, "plaka_degerlendir": olc["message"]}


@pytest.mark.parametrize("ad", ["tekil", "plaka", "plaka_degerlendir"])
def test_KRITIK_AIK_K4_makullik_iletisi_ORTAM_DEGISKENI_adini_gostermez(ad):
    metin = _metinler()[ad]
    assert "PEMF_" not in metin and "=0" not in metin, (
        f"{ad}: kullanıcı metninde ortam değişkeni / yapılandırma ayarı: {metin!r}"
    )


@pytest.mark.parametrize("ad", ["tekil", "plaka", "plaka_degerlendir"])
def test_KARSIT_AIK_K4_iletide_EYLEM_kalir(ad):
    """Metinden çıkarılan yalnız teknik ad — operatörün yapabileceği eylem (Gelişmiş ayarlar) AYNEN kalır."""
    metin = _metinler()[ad]
    assert "Gelişmiş (araştırma) ayarları" in metin and "kapatılabilir" in metin, metin


def test_KRITIK_AIK_K4_422_ayrintisi_URUN_yolundan_ortam_degiskeni_tasimaz():
    """Router'ın 422 çevirisi boru hattının mesajını AYNEN geçirir — kullanıcıya giden ayrıntı da temiz olmalı."""
    from servers import ai_router as air

    from ai_hub.inference_petri_dish import plausibility as pl

    _ok, olc = pl.evaluate_plate(None, guard=True)
    ayrinti = air._petri_reject_message(olc)
    assert ayrinti == olc["message"] and "PEMF_" not in ayrinti, ayrinti


def test_KARSIT_AIK_K4_kacis_kapagi_DEGISMEDI(monkeypatch):
    """Ortam değişkeni sunucu tarafında AYNEN çalışır (yalnız kullanıcı metninden çıktı)."""
    from ai_hub.inference_petri_dish import plausibility as pl

    monkeypatch.setenv("PEMF_AI_PLAUSIBILITY_GUARD", "0")
    assert pl.guard_enabled() is False
    monkeypatch.delenv("PEMF_AI_PLAUSIBILITY_GUARD", raising=False)
    assert pl.guard_enabled() is True
