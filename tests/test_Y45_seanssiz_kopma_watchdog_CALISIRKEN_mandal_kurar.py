# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""Y45 (sahip, 1-C §9 S1) — STM kopması ya da firmware watchdog'u anında HERHANGİ bir bobin çalışıyorsa (seans olsun
olmasın, elle başlatılmış dahil) ACİL DURDUR MANDALI KURULUR; boştayken kurulmaz. Mandal STOP'tan ÖNCE, kapısız.

ÖLÇÜLEN KUSUR (1-C inceleme i3-F-7): kopma / watchdog `_emergency_stop_all`'a YALNIZ AKTİF STM SEANSINDA gidiyordu.
Seanssız elle sürüşte kart koptuğunda ya da watchdog düştüğünde HC sıfırlanıyor ve nesil artıyordu ama mandal KURULMUYOR,
yeni START Sıfırla'sız kabul ediliyordu (Y4: "bilinçli sıfırla olmadan hiçbir START").

Kapı: GERÇEK `HeadlessCore._set_stm_connected` / `_handle_stm_line` → GERÇEK olay veriyolu + `_register_event_bus_handlers`
→ GERÇEK `HardwareController` (`kayitci_donanim.gercek_hc`). Sıra kaydı: `estop_mandali.mandalla` ile HC STOP'u
(`on_disconnect` / `stop_all_coils`) aynı listeye yazılır.
"""

from __future__ import annotations

import copy
import logging
import re
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
from topoloji import ESP_BOBIN, TUM_STM

_KOK = Path(__file__).resolve().parents[1]
_MAIN_C = _KOK / "firmware" / "stm32_pemf" / "Core" / "Src" / "main.c"
_B = min(TUM_STM)


def _watchdog_satiri() -> str:
    adaylar = re.findall(r'"([^"\n]*Watchdog Timeout[^"\n]*)"', _MAIN_C.read_text(encoding="utf-8", errors="replace"))
    assert len(adaylar) == 1
    return adaylar[0].replace("\\r", "").replace("\\n", "").strip()


@pytest.fixture
def ortam(monkeypatch):
    import event_bus as eb
    import headless_core as hcm
    from kayitci_donanim import gercek_hc
    from servers import api_server as api
    from servers import live_state as ls
    from utils import estop_mandali
    from utils.simple_signal import SimpleSignal

    sira: list = []
    monkeypatch.setattr(ls, "_ws_broadcast_sync", lambda m: None)
    monkeypatch.setattr(api, "_ws_broadcast_sync", lambda *a, **k: None)
    monkeypatch.setattr(api, "_push_notification", lambda *a, **k: None)
    monkeypatch.setattr(api, "_mqtt_publish", lambda topic, payload: False)
    yeni_bus = eb.EventBus()
    monkeypatch.setattr(eb, "_event_bus_instance", yeni_bus)
    monkeypatch.setattr(api, "_event_bus_registered", False)
    monkeypatch.setitem(api._active_session, "is_active", False)
    orj_mandalla = estop_mandali.mandalla

    def _sayan_mandalla(neden=""):
        sira.append(("mandal", neden))
        return orj_mandalla(neden)

    monkeypatch.setattr(estop_mandali, "mandalla", _sayan_mandalla)
    with ls._live_state_lock:
        eski_stm = ls._live_state["stm"]
        eski_bobinler = copy.deepcopy(ls._live_state["coils"])
    core = hcm.HeadlessCore.__new__(hcm.HeadlessCore)
    core.logger = logging.getLogger("test-y45")
    core.event_bus = yeni_bus
    core._stm_state_lock = threading.RLock()
    core.stm_is_connected = False
    core.stm_kimlik = None
    core.stm_uyumlu = None
    core.stm_uyumsuzluk_sebebi = ""
    core.stm_connected_signal = SimpleSignal()
    core.stm_connected_signal.connect(core._on_stm_connected_slot)
    monkeypatch.setattr(api.state, "core", core)
    try:
        api._register_event_bus_handlers()
        with gercek_hc(stm_cevrimici=False) as hc:
            orj_disc, orj_stop = hc.on_disconnect, hc.stop_all_coils

            def _disc():
                sira.append(("stop", "on_disconnect"))
                return orj_disc()

            def _stop():
                sira.append(("stop", "stop_all_coils"))
                return orj_stop()

            hc.on_disconnect = _disc
            hc.stop_all_coils = _stop
            monkeypatch.setattr(api.state, "hardware", hc)
            core._set_stm_connected(True)
            estop_mandali.sifirla("y45-aparat")
            sira.clear()
            yield SimpleNamespace(api=api, ls=ls, core=core, hc=hc, mandal=estop_mandali, sira=sira)
    finally:
        yeni_bus.shutdown()
        with ls._live_state_lock:
            ls._live_state["stm"] = eski_stm
            ls._live_state["coils"] = eski_bobinler


def _sur(o) -> None:
    assert o.hc.update_coil(_B, 100.0, 40.0, 0.0, 5, start=True) is True, "aparat: bobin baslamadi"
    assert o.hc.coils_state[_B]["is_running"] is True


def _mandal_stoptan_once(sira) -> bool:
    m = next(i for i, (t, _n) in enumerate(sira) if t == "mandal")
    s = next(i for i, (t, _n) in enumerate(sira) if t == "stop")
    return m < s


def test_KRITIK_seanssiz_elle_suruste_STM_kopmasi_mandal_kurar_STOPtan_ONCE(ortam):
    o = ortam
    _sur(o)
    o.core._set_stm_connected(False)
    assert o.mandal.mandalli_mi() is True, "seanssiz surus sirasinda STM koptu ama mandal KURULMADI (Y45)"
    assert _mandal_stoptan_once(o.sira), f"mandal STOP'tan SONRA kuruldu: {o.sira}"
    # Kart geri gelince yeni START Sıfırla'sız GEÇMEZ (Y4).
    o.core._set_stm_connected(True)
    assert o.hc.update_coil(_B, 100.0, 40.0, 0.0, 5, start=True) is False, "mandalliyken START kabul edildi"
    o.mandal.sifirla("operator")
    assert o.hc.update_coil(_B, 100.0, 40.0, 0.0, 5, start=True) is True, "Sifirla sonrasi yeni START reddedildi"


def test_KRITIK_seanssiz_elle_suruste_firmware_watchdog_mandal_kurar_STOPtan_ONCE(ortam):
    o = ortam
    _sur(o)
    o.core._handle_stm_line(_watchdog_satiri(), None)
    assert o.mandal.mandalli_mi() is True, "seanssiz surus sirasinda watchdog dustu ama mandal KURULMADI (Y45)"
    assert _mandal_stoptan_once(o.sira), f"mandal STOP'tan SONRA kuruldu: {o.sira}"
    assert o.hc.update_coil(_B, 100.0, 40.0, 0.0, 5, start=True) is False, "mandalliyken START kabul edildi"


def test_KRITIK_yalniz_ESP_slotu_calisirken_kopma_da_mandal_kurar(ortam):
    """ "HERHANGİ bir bobin": STM bobinleri boşta, ESP slotu canlı durumda çalışıyor."""
    o = ortam
    with o.ls._live_state_lock:
        o.ls._live_state["coils"][ESP_BOBIN - 1]["running"] = True
    o.core._set_stm_connected(False)
    assert o.mandal.mandalli_mi() is True


def test_KARSIT_bostayken_kopma_ve_watchdog_mandal_KURMAZ(ortam):
    o = ortam
    o.core._set_stm_connected(False)
    assert o.mandal.mandalli_mi() is False, "bostayken kartin cikip takilmasi mandal kurdu (Y45: kurmamali)"
    o.core._set_stm_connected(True)
    o.core._handle_stm_line(_watchdog_satiri(), None)
    assert o.mandal.mandalli_mi() is False, "bostayken watchdog mandal kurdu"
    assert o.hc.update_coil(_B, 100.0, 40.0, 0.0, 5, start=True) is True


def test_KRITIK_calisan_bobin_durumu_OKUNAMAZSA_kopmada_mandal_KURULUR(ortam, monkeypatch):
    """1-E incelemesi (i-2.1): `_herhangi_bobin_calisiyor` durumu okuyamazsa ÇALIŞIYOR saymalı (fail-safe: yanlış mandalın
    bedeli bir Sıfırla, kaçan mandal Y4'ü deler). "Okunamazsa çalışmıyor" mutantı mevcut 26 dosyada 295/295 YEŞİL kalıyordu."""

    class _OkunamayanHC:
        @property
        def coils_state(self):
            raise RuntimeError("bobin durumu okunamadi (aparat)")

        def on_disconnect(self):
            return True

        def stop_all_coils(self):
            return True

    o = ortam
    monkeypatch.setattr(o.api.state, "hardware", _OkunamayanHC())
    o.core._set_stm_connected(False)
    assert o.mandal.mandalli_mi() is True, "calisan bobin durumu okunamadi ve mandal KURULMADI (fail-open)"
