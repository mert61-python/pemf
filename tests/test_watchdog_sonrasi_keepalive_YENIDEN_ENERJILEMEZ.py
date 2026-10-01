# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D1.73 · B-1.18 — firmware "Watchdog Timeout" sonrası HardwareController durumu SIFIRLANIR; keep-alive eski duty ile
bobini YENİDEN ENERJİLEMEZ; seans yokken bildirim "seans durduruldu" DEMEZ.

ÖLÇÜLEN KUSUR (plan v-A18): seanssız sürüşte host 1,5 sn takılınca firmware ölü-adam devresi çıkışları sıfırlayıp
"-> STM_ERR: Watchdog Timeout!" basıyordu; api_server yalnız AKTİF STM seansında E-stop yapıyordu → seans yokken HC
durumu "çalışıyor" kalıyor, bir sonraki `_tick` paketi duty 0,4 ile bobini yeniden enerjiliyordu (RE-FIRE). Bildirim
koşulsuz "seans güvenlik için durduruldu" diyordu.

A-47 (sahip): termal kesme YOK — `STM_EVT` (termal) dalının davranışı DEĞİŞMEZ; karşıt kol pinler.

Kapı: satır FIRMWARE KAYNAĞINDAN okunur (main.c) → GERÇEK `HeadlessCore._handle_stm_line` → GERÇEK olay veriyolu +
`_register_event_bus_handlers` → GERÇEK `HardwareController` (`kayitci_donanim.gercek_hc`) → GERÇEK `_tick`.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import pytest
from topoloji import TUM_STM

_KOK = Path(__file__).resolve().parents[1]
_MAIN_C = _KOK / "firmware" / "stm32_pemf" / "Core" / "Src" / "main.c"
_B = min(TUM_STM)


def _firmware_watchdog_satiri() -> str:
    adaylar = re.findall(r'"([^"\n]*Watchdog Timeout[^"\n]*)"', _MAIN_C.read_text(encoding="utf-8", errors="replace"))
    assert len(adaylar) == 1, f"firmware watchdog satiri tekil bulunamadi: {adaylar}"
    return adaylar[0].replace("\\r", "").replace("\\n", "").strip()


@pytest.fixture
def ortam(monkeypatch):
    import event_bus as eb
    import headless_core as hcm
    from kayitci_donanim import gercek_hc
    from servers import api_server as api

    bildirimler: list = []
    monkeypatch.setattr(api, "_push_notification", lambda m, t="info": bildirimler.append((m, t)))
    monkeypatch.setattr(api, "_ws_broadcast_sync", lambda *a, **k: None)
    monkeypatch.setattr(api, "_mqtt_publish", lambda topic, payload: False)
    yeni_bus = eb.EventBus()
    monkeypatch.setattr(eb, "_event_bus_instance", yeni_bus)
    monkeypatch.setattr(api, "_event_bus_registered", False)
    monkeypatch.setitem(api._active_session, "is_active", False)
    core = hcm.HeadlessCore.__new__(hcm.HeadlessCore)
    core.logger = logging.getLogger("test-d173")
    core.event_bus = yeni_bus
    try:
        api._register_event_bus_handlers()
        with gercek_hc() as hc:
            monkeypatch.setattr(api.state, "hardware", hc)
            yield api, core, hc, bildirimler
    finally:
        yeni_bus.shutdown()


def _duty(p):
    from kayitci_donanim import paket_coz

    return paket_coz(p)[0]


def test_KRITIK_seanssiz_suruste_watchdog_sonrasi_keepalive_YENIDEN_ENERJILEMEZ(ortam):
    api, core, hc, bildirimler = ortam
    assert hc.update_coil(_B, 100.0, 40.0, 0.0, 5, start=True) is True
    assert _duty(hc.core._hw_send_queue.paketler[-1])[_B - 1] == pytest.approx(0.40), "aparat: bobin surulmuyor"
    once = len(hc.core._hw_send_queue.paketler)

    core._handle_stm_line(_firmware_watchdog_satiri(), None)
    for _ in range(3):
        hc._tick()  # GERÇEK keep-alive turu

    sonra = hc.core._hw_send_queue.paketler[once:]
    surus = [p for p in sonra if any(d > 0 for d in _duty(p))]
    assert not surus, (
        f"watchdog sonrasi keep-alive bobini ESKI duty ile yeniden enerjiledi: {[_duty(p) for p in surus]}"
    )
    assert hc.coils_state[_B]["is_running"] is False, "watchdog sonrasi HC durumu 'calisiyor' kaldi"
    metinler = [m for m, _t in bildirimler if "atchdog" in m]
    assert metinler, "watchdog operatore bildirilmedi"
    # "seans … durduruldu" CÜMLESİ aranır (seansın durdurulduğunu iddia eden): "çıkışlar durduruldu (aktif seans
    # yoktu)" gibi doğru bir metin kelimeleri ayrı bağlamlarda içerebilir.
    assert not any(re.search(r"seans[^()—]*durduruldu", m.lower()) for m in metinler), (
        f"seans YOKKEN bildirim 'seans durduruldu' dedi: {metinler}"
    )


def test_KARSIT_termal_STM_EVT_dalinin_davranisi_DEGISMEDI_A47(ortam):
    """A-47: termal kesme YOK. Termal satır HC durumunu sıfırlamaz ve donanıma STOP göndermez (bugünkü davranış)."""
    api, core, hc, bildirimler = ortam
    assert hc.update_coil(_B, 100.0, 40.0, 0.0, 5, start=True) is True
    once = len(hc.core._hw_send_queue.paketler)
    core._handle_stm_line("-> STM_EVT: TERMAL kesme (>=48C) bobin 6", None)
    assert hc.coils_state[_B]["is_running"] is True, "termal satir HC durumunu SIFIRLADI (A-47: termal kesme YOK)"
    assert len(hc.core._hw_send_queue.paketler) == once, "termal satir donanima paket gonderdi (A-47)"
