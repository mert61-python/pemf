# -*- coding: utf-8 -*-
"""I18NI-A1.2 — kart duty TAVANI reddi (KRİTİK bildirim + 409 eylemi) İngilizcede yüzdeyi İngilizce biçimle yazmalı ("50%"), Türkçe biçimle
DEĞİL ("%50"). Arayüz EN kataloğu aynı değeri `{{duty}}%` yazar (`kontrol.ekran.uygulandiGovde`, `ai.pro.tablo.surulmediPlan`); sunucu
`bildirim.dutyReddi.*` EN değerleri `%{{tavan}}` / `%{{istenen}}` taşıyor. TR değerleri (`%{{tavan}}`) bayt bayt AYNI kalmalı.

GERÇEK: `live_state.stm_duty_reddi_metni` + sunucu kataloğu. Bugün KIRMIZI; EN değerleri düzelince YEŞİL.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

TR_BICIM = re.compile(r"%\s?\d")  # "%50" — Türkçe yüzde biçimi
EN_BICIM = re.compile(r"\d%")


def _nack(bobin, istenen, tavan, kip):
    return f"-> STM_NACK: RANGE coil={bobin} field=duty value_milli={istenen} max_milli={tavan} kip={kip}"


@pytest.mark.parametrize("sifirla", [False, True])
@pytest.mark.parametrize(
    "nack", [_nack(1, 800, 500, "bipolar"), _nack(6, 1255, 1000, "unipolar")], ids=["bipolar", "unipolar"]
)
def test_duty_reddi_EN_yuzde_ingilizce_bicimde(nack, sifirla):
    from servers import live_state as ls

    en = ls.stm_duty_reddi_metni(nack, "the session was STOPPED", sifirla=sifirla, dil="en")
    assert en, "duty reddi metni üretilmedi"
    assert not TR_BICIM.search(en), f"EN metinde Türkçe yüzde biçimi: {en!r}"
    assert len(EN_BICIM.findall(en)) >= 3, (
        f"EN metinde tavan / istenen / eylem yüzdeleri İngilizce biçimde değil: {en!r}"
    )


def test_duty_reddi_TR_bayt_bayt_ayni():
    from servers import live_state as ls

    assert ls.stm_duty_reddi_metni(_nack(1, 800, 500, "bipolar"), "seans DURDURULDU", sifirla=True, dil="tr") == (
        "Bobin 1 çift yönlü kipte en fazla %50 çalışabilir; %80 kabul edilmedi; seans DURDURULDU. "
        "Duty'yi %50 veya altına indirin (ya da ⚡ Sürüş Kipi'nden bu bobini Unipolar yapın), sonra 'Sıfırla'ya basın ve yeniden başlatın."
    )


def test_sunucu_EN_katalogunda_turkce_yuzde_bicimi_yok():
    def duz(d, o=""):
        r = {}
        for k, v in d.items():
            t = f"{o}.{k}" if o else k
            r.update(duz(v, t)) if isinstance(v, dict) else r.__setitem__(t, v)
        return r

    en = duz(json.loads((KOK / "apps/backend/i18n/en.json").read_text(encoding="utf-8")))
    kotu = {k: v for k, v in en.items() if re.search(r"%(\{\{|\d)", str(v))}
    assert not kotu, f"EN değerde Türkçe yüzde biçimi (%önce): {kotu}"
