# -*- coding: utf-8 -*-
"""SON-A1.3 (22-SON A1a · C112 / C122 / C132 J kapı gücü) — hasta sahibine giden PDF'te ayarlanan mT BAŞKA BİRİMLE (µT / T) ya da
"doz / dose" etiketiyle de görünmez.

ÖLÇÜLEN ZAYIFLIK (uç 8b002fc0): `tests/test_mt_dose_honesty.py` (D5.59 tur 1-3b) ayarlanan değeri yalnız ondalık biçimiyle
(`(?<!\\d)7[.,]3`) ve kapalı bir etiket kümesiyle (şiddet / yoğunluk / intensity / strength / ölçülen / alan / field / (mT) / mT / tesla /
gauss) arar. Seans bilgi tablosuna `["Doz (µT)", "7300"]` ekleyen mutant 18 düğümün HEPSİNDE YEŞİL kaldı (aynı doz, başka birim +
kümede olmayan etiket). Bu sonda aynı GERÇEK üretim yolunu (`_rapor_ogeleri` — gerçek DB + gerçek `generate_*_report`, story
yakalanır) kullanır; birim dönüşümlü değer ve doz etiketi de yasak.
"""

from __future__ import annotations

import re

import pytest
from test_mt_dose_honesty import _APARATLAR, _rapor_ogeleri

#: Ayarlanan değerin başka birimle yazımı: µT (×1000, tam sayı) ve T (÷1000). Biçim rastlantısı: tarih / saat / süre / sayaç hücrelerinde
#: 7300 / 5100 / 0.0073 / 0.0051 oluşmaz (aparat değerleri belirgin).
_DOZ_ETIKETI = re.compile(r"(?i)\bdoz|\bdose|dosage|dozaj|[µμ]\s*t\b|mikrotesla|microtesla|militesla|millitesla")


def _birim_deseni(degerler) -> re.Pattern:
    parcalar = set()
    for v in degerler:
        parcalar.add(re.escape(f"{float(v) * 1000:.0f}"))  # µT
        parcalar.add(r"0[.,]00" + "".join(f"{float(v):.1f}".split(".")))  # T (7.3 mT → 0.0073)
    return re.compile(r"(?<![\d.,])(?:" + "|".join(sorted(parcalar)) + r")(?!\d)")


@pytest.mark.parametrize("rapor", ["seans", "hasta"])
@pytest.mark.parametrize("aparat", sorted(_APARATLAR))
@pytest.mark.parametrize("dil", ["tr", "en"])
def test_KRITIK_rapor_ayarlanan_mT_yi_BASKA_BIRIMLE_ya_da_DOZ_etiketiyle_TASIMAZ(
    temp_app_data, tmp_path, monkeypatch, dil, aparat, rapor
):
    degerler = _APARATLAR[aparat]
    desen = _birim_deseni(degerler)
    tablolar, paragraflar = _rapor_ogeleri(tmp_path, monkeypatch, dil, rapor, degerler)
    hucreler = [h for t in tablolar for satir in t for h in satir]
    assert hucreler and paragraflar, "aparat: rapor öğeleri okunmadı"
    ihlal = [m for m in hucreler + paragraflar if _DOZ_ETIKETI.search(m) or desen.search(m)]
    assert not ihlal, (
        f"hasta sahibine giden {rapor} raporunda ayarlanan mT başka birimle ya da doz etiketiyle var ({dil}, {aparat}): {ihlal}"
    )
