# Author: mertaygn, cglrgrkn
"""TD7 (tezgâh Oturum 13, madde 7) — `STM_TELE` DEBUG günlüğü ÖRNEKLENİR; telemetri olayı HER satırda yayınlanır.

ÖLÇÜLEN (tezgâh, kurulu ürün günlüğü DEBUG): ilk ~1 dakikada 9 646 `STM_TELE` satırı (~4 000 satır/dk) — günlük boğuluyor, NACK / watchdog / E-stop satırları
gözden kaçıyor. Koddaki gerekçe "1 Hz × 2 bobin" varsayıyordu; kart bobin başına çok daha sık basıyor.
SÖZLEŞME: bobin başına `_STM_TELE_GUNLUK_ARALIGI_S` (60 sn) içinde BİR DEBUG satırı; atlananların sayısı bir sonraki örnekte söylenir; ayrıştırma ve
`hardware.stm.telemetry` yayını HER satırda (veri kaybı yok); INFO'da hiç yazılmaz (eskisi gibi). Aparat: GERÇEK `_handle_stm_line`; saat sahte.
"""

from __future__ import annotations

import logging
import time

import pytest


class _Saat:
    def __init__(self):
        self.t = 1000.0

    def monotonic(self):
        return self.t

    def __getattr__(self, ad):
        return getattr(time, ad)


@pytest.fixture
def cekirdek(monkeypatch):
    import headless_core as hcm

    saat = _Saat()
    monkeypatch.setattr(hcm, "time", saat)
    core = hcm.HeadlessCore.__new__(hcm.HeadlessCore)
    core.logger = logging.getLogger("test-td7")
    core.olaylar = []
    core._publish_event = lambda tur, veri=None, **k: core.olaylar.append((tur, veri))
    return core, saat, hcm


def _satir(c: int) -> str:
    return f"-> STM_TELE: C={c},T=34.20,A=27.10,B=1.842"


def _tele_kayitlari(caplog):
    return [r for r in caplog.records if r.name == "test-td7" and "STM_TELE" in r.getMessage()]


def test_KRITIK_STM_TELE_gunlugu_bobin_basina_ORNEKLENIR_olay_HER_satirda(cekirdek, caplog):
    core, saat, _ = cekirdek
    with caplog.at_level(logging.DEBUG, logger="test-td7"):
        for _ in range(600):
            for c in (1, 6):
                core._handle_stm_line(_satir(c), None)
    tele = _tele_kayitlari(caplog)
    assert len(tele) == 2, f"aynı dakika içinde {len(tele)} STM_TELE günlük satırı (bobin başına 1 beklenir)"
    assert len([o for o in core.olaylar if o[0] == "hardware.stm.telemetry"]) == 1200, (
        "telemetri olayı örneklemeye takıldı (veri kaybı)"
    )


def test_KRITIK_aralik_dolunca_yeni_ornek_ATLANAN_sayisini_soyler(cekirdek, caplog):
    core, saat, hcm = cekirdek
    with caplog.at_level(logging.DEBUG, logger="test-td7"):
        for _ in range(10):
            core._handle_stm_line(_satir(1), None)
        saat.t += hcm._STM_TELE_GUNLUK_ARALIGI_S + 1.0
        core._handle_stm_line(_satir(1), None)
    tele = _tele_kayitlari(caplog)
    assert len(tele) == 2, [r.getMessage() for r in tele]
    assert "önceki 9 satır günlüğe yazılmadı" in tele[1].getMessage(), tele[1].getMessage()


def test_KARSIT_INFO_seviyesinde_STM_TELE_HIC_yazilmaz_olay_yine_yayinlanir(cekirdek, caplog):
    core, _, _ = cekirdek
    with caplog.at_level(logging.INFO, logger="test-td7"):
        for _ in range(5):
            core._handle_stm_line(_satir(2), None)
    assert _tele_kayitlari(caplog) == []
    assert len(core.olaylar) == 5
