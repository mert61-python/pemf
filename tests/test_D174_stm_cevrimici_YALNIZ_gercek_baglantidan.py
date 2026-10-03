# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D1.74 · B-1.19 (+ İG-6.1 backend yarısı) — canlı durumda STM "online" YALNIZ gerçek bağlantıdan gelir.

ÖLÇÜLEN KUSUR (plan v-A23, aday doğrulaması İG-6.1): `live_state.update_live_coil_from_stm` her `coil_update`
olayında `_live_state["stm"] = "online"` yazıyor ve `stm_status{online}` yayınlıyordu. Firmware "Watchdog Timeout"
satırının SENTETİK sıfırlama yayını (`HeadlessCore._tum_bobinleri_sifirla_yayinla`) da `coil_update`dir → STM
koptuktan sonra okunan bir watchdog satırı (ya da BAŞARISIZ bir el sıkışmada okunan satır) başlatma kapısını
(`stm_surus_hazir`) yeniden açıyor, `HardwareController.update_coil(start=True)` donanım yokken True dönüyordu.
Aynı sentetik olay "kart komutu kabul etti" sayılıp sistematik-NACK kararını da siliyordu.

Kapı: GERÇEK `HeadlessCore._set_stm_connected` / `_handle_stm_line` → GERÇEK olay veriyolu + `_register_event_bus_handlers`
→ GERÇEK `live_state` → GERÇEK `HardwareController` (`kayitci_donanim.gercek_hc`). STM ACK'i firmware aynasından
(`tools.stm32_simulator`) gönderilen paketin kendisiyle üretilir. Başarısız el sıkışma GERÇEK
`Stm32SerialTransport._wait_for_handshake` ile koşar (`on_line` = ürünün bağladığı `_handle_stm_line`, headless_core).

Arayüz yarısı (İG-6.1): `apps/ui/src/context/__tests__/__fixtures__/stmKopusuManuelBobin.ws.json` bu dosyadaki
`ws_dizisi_uret()` ile GERÇEK backend'den üretilir; `test_arayuz_fiksturu_GERCEK_backend_dizisiyle_AYNI` bayatlamayı yakalar.
"""

from __future__ import annotations

import copy
import json
import logging
import re
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from topoloji import TUM_STM

_KOK = Path(__file__).resolve().parents[1]
_MAIN_C = _KOK / "firmware" / "stm32_pemf" / "Core" / "Src" / "main.c"
_FIKSTUR = _KOK / "apps" / "ui" / "src" / "context" / "__tests__" / "__fixtures__" / "stmKopusuManuelBobin.ws.json"
_B = min(TUM_STM)
# Sahadaki kartın banner'ı (SAHIP-CEVAPLARI Y7, salt-okur ölçüm 2026-09-30).
_SAHA_BANNER = "-> STM_READY: DDS v2.3 (7-ch KARMA uni=0x60 + HW_SYNC@PB1)"


def _firmware_satiri(desen: str) -> str:
    adaylar = re.findall(r'"([^"\n]*' + desen + r'[^"\n]*)"', _MAIN_C.read_text(encoding="utf-8", errors="replace"))
    assert len(adaylar) == 1, f"firmware satiri tekil bulunamadi ({desen}): {adaylar}"
    return adaylar[0].replace("\\r", "").replace("\\n", "").strip()


def _ack_satiri(paket: bytes) -> str:
    """Firmware aynası: gönderilen paketin STM_OK satırı (tools/stm32_simulator `_send_ack`)."""
    import tools.stm32_simulator as sim

    cozum, sebep = sim.decode_packet(paket)
    assert cozum is not None, f"paket firmware'ce NACK'lenir: {sebep!r}"
    duty, faz, freq, sure, _ref, kip = cozum
    giden: list[str] = []

    class _Soket:
        def sendall(self, b):
            giden.append(b.decode("utf-8"))

    sim.Stm32SimClient(_Soket(), ("test", 0))._send_ack(duty, faz, freq, sure, kip)
    return giden[-1].strip()


def _cekirdek(bus):
    import headless_core as hcm
    from utils.simple_signal import SimpleSignal

    core = hcm.HeadlessCore.__new__(hcm.HeadlessCore)
    core.logger = logging.getLogger("test-d174")
    core.event_bus = bus
    core._stm_state_lock = threading.RLock()
    core.stm_is_connected = False
    core.stm_kimlik = None
    core.stm_uyumlu = None
    core.stm_uyumsuzluk_sebebi = ""
    core.stm_connected_signal = SimpleSignal()
    core.stm_connected_signal.connect(core._on_stm_connected_slot)
    return core


@pytest.fixture
def ortam(monkeypatch):
    import event_bus as eb
    from kayitci_donanim import gercek_hc
    from servers import api_server as api
    from servers import live_state as ls

    yayinlar: list = []
    monkeypatch.setattr(ls, "_ws_broadcast_sync", lambda m: yayinlar.append(copy.deepcopy(m)))
    monkeypatch.setattr(api, "_ws_broadcast_sync", lambda *a, **k: None)
    monkeypatch.setattr(api, "_push_notification", lambda *a, **k: None)
    monkeypatch.setattr(api, "_mqtt_publish", lambda topic, payload: False)
    yeni_bus = eb.EventBus()
    monkeypatch.setattr(eb, "_event_bus_instance", yeni_bus)
    monkeypatch.setattr(api, "_event_bus_registered", False)
    monkeypatch.setitem(api._active_session, "is_active", False)
    with ls._live_state_lock:
        eski_stm = ls._live_state["stm"]
        eski_bobinler = copy.deepcopy(ls._live_state["coils"])
        eski_tedavi = copy.deepcopy(ls._live_state["activeTreatment"])
        # Bilinen zemin: önceki testlerin bıraktığı bobin / tedavi durumu fikstür dizisine SIZMASIN (toplu koşuda ölçüldü:
        # slot 8 ya da tedavi kipi başka testten kalınca bayatlık kapısı yalancı kırmızı veriyordu).
        for _c in ls._live_state["coils"].values():
            _c.update({"connected": False, "running": False})
        ls._live_state["activeTreatment"].update({"isActive": False, "mode": "Sistem Hazır"})
    with ls._stm_red_lock:
        eski_red = dict(ls._stm_red)
    core = _cekirdek(yeni_bus)
    monkeypatch.setattr(api.state, "core", core)
    try:
        api._register_event_bus_handlers()
        with gercek_hc(stm_cevrimici=False) as hc:
            monkeypatch.setattr(api.state, "hardware", hc)
            ls.stm_komut_kabulu_bildir()
            ls.update_live_stm_status(False)  # temiz başlangıç: kart yok
            yayinlar.clear()
            yield SimpleNamespace(api=api, ls=ls, core=core, hc=hc, yayinlar=yayinlar)
    finally:
        yeni_bus.shutdown()
        with ls._live_state_lock:
            ls._live_state["stm"] = eski_stm
            ls._live_state["coils"] = eski_bobinler
            ls._live_state["activeTreatment"] = eski_tedavi
        with ls._stm_red_lock:
            ls._stm_red.clear()
            ls._stm_red.update(eski_red)


def _surus_paketi_var(paketler) -> bool:
    from kayitci_donanim import paket_coz

    return any(any(d > 0 for d in paket_coz(p)[0]) for p in paketler)


def _bagla_ve_bobini_sur(o) -> None:
    o.core._set_stm_connected(True)
    assert o.ls.stm_surus_hazir() is True, "aparat: gercek baglanti STM'i cevrimici yapmadi"
    assert o.hc.update_coil(_B, 100.0, 40.0, 0.0, 5, start=True) is True, "aparat: bobin baslamadi"
    o.core._handle_stm_line(_ack_satiri(o.hc.core._hw_send_queue.paketler[-1]), None)
    calisan = [m for m in o.yayinlar if m.get("type") == "stm_coil_update" and m["data"].get("running")]
    assert calisan, "aparat: STM ACK'i bobini 'calisiyor' yayinlamadi"


def test_KRITIK_kopus_sonrasi_watchdog_satiri_baslatma_kapisini_ACMAZ(ortam):
    o = ortam
    _bagla_ve_bobini_sur(o)
    o.core._set_stm_connected(False)
    assert o.ls.stm_surus_hazir() is False, "aparat: kopus STM'i cevrimdisi yapmadi"
    kopus = len(o.yayinlar)
    once = len(o.hc.core._hw_send_queue.paketler)

    o.core._handle_stm_line(_firmware_satiri("Watchdog Timeout"), None)

    assert o.ls.stm_surus_hazir() is False, "kopustan sonra sentetik watchdog yayini STM'i 'online' yapti (B-1.19)"
    assert o.api._build_ws_snapshot()["stm"] == "warning", "anlik goruntu kopuk STM'i 'online' gosteriyor"
    online = [m for m in o.yayinlar[kopus:] if m.get("type") == "stm_status" and m["data"].get("stm") == "online"]
    assert not online, f"kopustan sonra istemcilere 'stm online' yayinlandi: {online}"
    assert o.hc.update_coil(_B, 100.0, 40.0, 0.0, 5, start=True) is False, (
        "kart yokken START kabul edildi (sentetik coil_update baslatma kapisini acti)"
    )
    assert not _surus_paketi_var(o.hc.core._hw_send_queue.paketler[once:]), "kart yokken surus paketi kuyruga girdi"


def test_KRITIK_basarisiz_el_sikismada_okunan_satir_kapiyi_ACMAZ(ortam):
    from utils.stm32_transport import Stm32PortCandidate, Stm32SerialTransport

    o = ortam
    satirlar = [(_firmware_satiri("Watchdog Timeout") + "\r\n").encode("utf-8")]

    class _SahteSeri:
        def readline(self):
            if satirlar:
                return satirlar.pop(0)
            time.sleep(0.01)
            return b""

        def write(self, _b):
            return len(_b)

    tasima = Stm32SerialTransport(logging.getLogger("test-d174-el"), handshake_timeout_sec=0.3)
    sonuc = tasima._wait_for_handshake(
        _SahteSeri(),
        Stm32PortCandidate(device="socket://d174", description="test"),
        None,
        lambda satir: o.core._handle_stm_line(satir, None),
    )
    assert sonuc == "", "aparat: el sikisma BASARISIZ olmali (STM_READY/STM_OK yok)"
    assert not satirlar, "aparat: watchdog satiri el sikismada okunmadi"
    assert o.ls.stm_surus_hazir() is False, "basarisiz el sikismada okunan satir STM'i 'online' yapti (B-1.19)"
    assert o.hc.update_coil(_B, 100.0, 40.0, 0.0, 5, start=True) is False, "basarisiz el sikismadan sonra START"


def test_KRITIK_sistematik_NACK_karari_sentetik_sifirlama_yayiniyla_SILINMEZ(ortam):
    o = ortam
    o.core._set_stm_connected(True)
    for _ in range(o.ls.STM_RED_ESIGI):
        o.core._handle_stm_line("-> STM_NACK: CRC", None)
    assert o.ls.stm_komutlari_reddediyor() is True, "aparat: sistematik red karari olusmadi"

    o.core._handle_stm_line(_firmware_satiri("Watchdog Timeout"), None)

    assert o.ls.stm_komutlari_reddediyor() is True, (
        "firmware watchdog'unun SENTETIK sifirlama yayini 'kart komutu kabul etti' sayildi, red karari silindi"
    )
    assert o.hc.update_coil(_B, 100.0, 40.0, 0.0, 5, start=True) is False, (
        "kart paketleri reddederken START kabul edildi"
    )


def test_KARSIT_gercek_el_sikisma_ve_gercek_STM_OK_kapiyi_ACAR(ortam):
    """Karşıt: gerçek banner (sahadaki kart, Y7) ve gerçek ACK STM'i çevrimiçi yapar — düzeltme fail-closed'a kaymaz."""
    o = ortam
    o.core._handle_stm_line(_SAHA_BANNER, None)
    assert o.ls.stm_surus_hazir() is True, "gercek STM_READY STM'i cevrimici yapmadi"
    assert o.hc.update_coil(_B, 100.0, 40.0, 0.0, 5, start=True) is True, "gercek el sikismadan sonra START reddedildi"


def test_KARSIT_kacirilan_baglanti_olayi_GERCEK_ACK_ile_iyilesir(ortam):
    """Açılış yarışı: çekirdek kartla el sıkıştı (`stm_is_connected=True`) ama `hardware.stm.connected` olayı api
    işleyicileri kaydolmadan yayınlandı (kaçtı). Eskiden her STM_OK canlı durumu 'online' yapıp bunu örtüyordu;
    düzeltmeden sonra GERÇEK ACK, çekirdeğin bağlantı gerçeğinden iyileştirmeli — yoksa çalışan kart kalıcı 'warning'de
    kalır ve her START reddedilir."""
    from utils.stm32_transport import build_stm32_zero_duty_packet

    o = ortam
    with o.core._stm_state_lock:
        o.core.stm_is_connected = True  # olay yayınlanmadan (kaçırılan olay)
    assert o.ls.stm_surus_hazir() is False, "aparat: canli durum 'warning' olmali"
    o.core._handle_stm_line(_ack_satiri(build_stm32_zero_duty_packet()), None)
    assert o.ls.stm_surus_hazir() is True, "gercek STM_OK, bagli cekirdekte canli durumu iyilestirmedi"


# ── Arayüz fikstürü (İG-6.1): GERÇEK backend'in seanssız manuel bobin + STM kopuşu WS dizisi ────────────────────────
_ALANLAR = ("stm", "connected", "running")


def ws_dizisi_uret(o) -> list[dict]:
    """İlk anlık görüntü → bağlan → bobin START + ACK → kopuş. İstemcinin okuduğu alanlar (tip, bobin,
    stm/connected/running; anlık görüntüde bobinler ve aktif tedavi bayrağı)."""
    ilk = o.api._build_ws_snapshot()
    anlik = {
        "type": "snapshot",
        "data": {
            "stm": ilk["stm"],
            "activeTreatment": {"isActive": ilk["activeTreatment"]["isActive"], "mode": ilk["activeTreatment"]["mode"]},
            "coils": [{"id": c["id"], "connected": c["connected"], "running": c["running"]} for c in ilk["coils"]],
            "notifications": [],
        },
    }
    o.yayinlar.clear()
    o.core._set_stm_connected(True)
    assert o.hc.update_coil(_B, 100.0, 40.0, 0.0, 5, start=True) is True
    o.core._handle_stm_line(_ack_satiri(o.hc.core._hw_send_queue.paketler[-1]), None)
    o.core._set_stm_connected(False)
    dizi = [anlik]
    for m in o.yayinlar:
        if m.get("type") not in ("stm_status", "stm_coil_update"):
            continue
        g = {"type": m["type"]}
        if "coilId" in m:
            g["coilId"] = m["coilId"]
        g["data"] = {k: m["data"][k] for k in _ALANLAR if k in m["data"]}
        dizi.append(g)
    return dizi


def test_arayuz_fiksturu_GERCEK_backend_dizisiyle_AYNI(ortam):
    beklenen = ws_dizisi_uret(ortam)
    assert _FIKSTUR.is_file(), f"arayuz fiksturu yok: {_FIKSTUR}"
    kayitli = json.loads(_FIKSTUR.read_text(encoding="utf-8"))
    assert kayitli == beklenen, "arayuz fiksturu backend'in GERCEK WS dizisinden BAYATLADI (ws_dizisi_uret ile yenile)"
    # Dizinin kendisi kusuru taşımalı: çalışan bobin → kopuş → bobin güncellemeleri (istemci override'ı bunlarla açılır).
    tipler = [m["type"] for m in kayitli]
    assert kayitli[0]["type"] == "snapshot" and kayitli[0]["data"]["stm"] == "warning"
    assert not any(c["running"] for c in kayitli[0]["data"]["coils"]), "aparat: ilk anlik goruntude calisan bobin var"
    kopus = next(i for i, m in enumerate(kayitli) if m["type"] == "stm_status" and m["data"]["stm"] == "warning")
    assert any(m["type"] == "stm_coil_update" and m["data"].get("running") for m in kayitli[:kopus])
    assert tipler[kopus + 1 :].count("stm_coil_update") == len(TUM_STM)
