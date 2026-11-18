# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""ODD K-9 / K-10 / K-11 (ODK-B keşfi 18-11):
  K-9  döngü günlüğü petri seansında "AI Pro Closed-Loop (cat_organ organ-lokalizasyon + em_kedi)" diyordu (yanıltıcı tanı) → MODELE göre.
  K-10 canlı seans kartı hedefi iç numarayla ("Kuyu 12") gösteriyordu → o karede görülmeyen (kaybolan) kimliğin de plaka etiketi ("Kuyu C6").
  K-11 canlı kart "DUTY (AI planı, bobin 1) %36" — 7 bobinlik planın yalnız bobin 1'i → canlı durum seçilen ODAK dozunu (mühür) ve planın
       sürdüğü bobin sayısını taşır (`odakDozMt` / `odakBobinSayisi`; yalnız-ek). D1.89: duty mT alanına YİNE yazılmaz.
GERÇEK: döngü (`ai-pro-dongu`) + HC; lokalizasyon / doz planı sahte (ODD B-1 düzeneği)."""

from __future__ import annotations

import logging

import ai_pro_aparati as ap
from test_ODD_B1_petri_SABIT_NUMUNE_son_plan_tolerans_Y300 import D_PLAN, _baslat_ve_sur, _calistir


def test_KRITIK_K9_K11_petri_seansi_gunluk_MODELE_gore_canli_durum_ODAK_dozu_ve_bobin_sayisi(
    monkeypatch, tmp_path, caplog
):
    from servers import ai_pro_hedef, live_state

    caplog.set_level(logging.INFO)
    with _calistir(monkeypatch, tmp_path, pencere_s=30.0) as (ns, durum):
        petri = ai_pro_hedef.saglayici_al("petri")
        monkeypatch.setattr(
            petri, "odak_ayari", {"doz_mT": 0.6, "kip": "KUYUCUK", "hedef_etiket": "Kuyu C6", "frek_hz": 100.0}
        )
        orig = ai_pro_hedef.odak_ayarla
        monkeypatch.setattr(
            ai_pro_hedef, "odak_ayarla", lambda s, o, e="": None
        )  # mühürsüz test önerisi ayarı SİLMESİN
        _baslat_ve_sur(ns)
        assert ap.bekle(lambda: live_state._live_state["activeTreatment"].get("odakDozMt") == 0.6, 4), (
            live_state._live_state["activeTreatment"]
        )
        at = dict(live_state._live_state["activeTreatment"])
        monkeypatch.setattr(ai_pro_hedef, "odak_ayarla", orig)
    satirlar = [r.getMessage() for r in caplog.records if "BAŞLADI" in r.getMessage()]
    assert any("model: petri" in m and "kabin CV" in m for m in satirlar), satirlar
    assert not any("em_kedi" in m for m in satirlar), satirlar
    assert at["odakBobinSayisi"] == sum(1 for d in D_PLAN if d > 0) and not at.get("intensityMt"), at


def test_KARSIT_K11_ODAK_ayari_yoksa_alanlar_BOS_kedi_gunlugu_cat_organ(monkeypatch, tmp_path, caplog):
    from servers import live_state

    caplog.set_level(logging.INFO)
    with _calistir(monkeypatch, tmp_path, pencere_s=30.0) as (ns, durum):
        monkeypatch.setattr(ns.air, "_ORGAN_LOCALIZE_INTERVAL_S", 0.0)
        _baslat_ve_sur(ns, model="kedi", organ=2)
        assert ap.bekle(lambda: live_state._live_state["activeTreatment"].get("isActive") is True, 3)
        at = dict(live_state._live_state["activeTreatment"])
    assert at.get("odakDozMt") is None and at.get("odakBobinSayisi") == 7, at
    assert any("model: kedi" in r.getMessage() and "cat_organ" in r.getMessage() for r in caplog.records)


def test_KRITIK_K10_kaybolan_kimligin_adi_PLAKA_etiketi_ic_numara_DEGIL():
    from servers import ai_pro_hedef

    p = ai_pro_hedef.PetriSaglayici()
    p._kimlikler = [{"id": 3, "ad": "Kuyu A1", "px": (1, 1)}]
    p._kayip_kimlikler = {12: {"id": 12, "ad": "Kuyu C6", "px": (5, 5)}}
    assert p.hedef_adi(12) == "Kuyu C6"
    assert p.hedef_adi(3) == "Kuyu A1"
    assert p.hedef_adi(99) == "Kuyu 99"  # hiç görülmemiş kimlik — eski davranış
