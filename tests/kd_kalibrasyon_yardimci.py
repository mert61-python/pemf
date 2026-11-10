# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""KD · Y259 test yardımcısı — araştırma (petri / fantom) AI Pro önerisi / başlatması / sürüşü artık GEÇERLİ sabit düzlem kalibrasyonu
ister (`ai_router._duzlem_kalibrasyonu_kapisi` → `ai_pro_hedef.duzlem_surus_engeli`). KD öncesi yazılmış kapı testleri (bayrak, mühür,
koşulsuz kip, otomatik hedef …) BAŞKA bir kuralı ölçer; kalibrasyon ön koşulunu bu aparatla "sağlanmış" kabul eder. Kalibrasyon
kapısının kendisi `test_KD_kalibrasyon_uclari_ve_surus_kapisi.py`'de (yokluk / bozukluk / kamera farkı / fantom ayarı → 409).

Kullanım (modül düzeyinde): `from kd_kalibrasyon_yardimci import kd_gecerli_kalibrasyon  # noqa: F401`.
⚠️ `monkeypatch` İSTEMEZ (hafıza: autouse fikstürü monkeypatch isterse yıkım sırası nöbet fikstürlerini bozar) — elle kaydet / geri yükle.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def kd_gecerli_kalibrasyon():
    from servers import ai_pro_hedef

    eski = ai_pro_hedef.duzlem_surus_engeli
    ai_pro_hedef.duzlem_surus_engeli = lambda _saglayici: None
    try:
        yield
    finally:
        ai_pro_hedef.duzlem_surus_engeli = eski
