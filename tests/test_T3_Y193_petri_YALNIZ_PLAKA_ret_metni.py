# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""T3 · Y193 (sahip, 2026-10-24: "24'lü ile tekilin farkı ne, sadece 24 kalsın, ai saf çalışsın") — tekil petri kabı kipi ARAYÜZDEN kalktı.

ÖLÇÜLEN (önce, 87d91346): plaka kipinin reddi kullanıcıyı "'Tekil petri kapları' kipini seçin" diye o kipe yönlendiriyordu (kaynak
`plausibility.plate_user_message` + katalog `ai.hata.petriPlakaIzgara`, TR / EN). Kip seçici kalkınca bu, YAPILAMAYAN bir eylem olur
(hata mesajı eylem söylesin kuralı).
KAPI: ret metni tekil kipe yönlendirmez, yapılabilir eylemi söyler (kenarlar kadrajda / doğru modül / denetim nerede kapatılır); katalog
Türkçesi kaynakla BAYT BAYT aynı (`ai_kapi_metni` güvence dalı gizlemesin); İngilizcesi de "Single petri dishes" demez. Eski anahtar
(`petriPlakaIzgara`) yalnız TR taban kapısı için katalogda kalır, kod kullanmaz. Arayüz tarafı: jest `petriYalnizPlaka.T3_Y193.test.tsx`.
"""

from __future__ import annotations

import re
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]


def test_KRITIK_plaka_reddi_TEKIL_kipe_yonlendirmez_yapilabilir_eylem_soyler():
    from ai_hub.inference_petri_dish import plausibility as pl

    m = pl.plate_user_message({"kip": "plaka"})
    assert "Tekil petri kapları" not in m and "tekil" not in m.lower(), m
    assert m.startswith("24 kuyucuklu plaka ızgarası oturmadı.") and "ilgili modüle" in m and "kadrajda" in m, m


def test_KRITIK_katalog_TR_kaynakla_BAYT_BAYT_ayni_EN_tekil_demez():
    from servers import ai_kapi_metni as akm

    from ai_hub.inference_petri_dish import plausibility as pl

    tr = akm.petri_ret_katalog_metni({"kip": "plaka"}, "tr")
    assert tr == pl.plate_user_message({"kip": "plaka"}), (
        "katalog Türkçesi kaynaktan AYRIŞTI (güvence dalı farkı gizler)"
    )
    en = akm.petri_ret_katalog_metni({"kip": "plaka"}, "en")
    assert "Single petri dishes" not in en and "single" not in en.lower() and "24-well plate grid" in en, en


def test_KARSIT_kod_eski_anahtari_KULLANMAZ_eski_anahtar_taban_icin_katalogda():
    import json

    kaynak = (KOK / "apps" / "backend" / "servers" / "ai_kapi_metni.py").read_text(encoding="utf-8")
    assert not re.search(r"\"ai\.hata\.petriPlakaIzgara\"", kaynak), (
        "kod tekil kipe yönlendiren eski anahtarı kullanıyor"
    )
    for dil in ("tr", "en"):
        j = json.loads((KOK / "apps" / "backend" / "i18n" / f"{dil}.json").read_text(encoding="utf-8"))
        assert j["ai"]["hata"]["petriPlakaIzgara"] and j["ai"]["hata"]["petriPlakaIzgaraYalnizPlaka"], dil
