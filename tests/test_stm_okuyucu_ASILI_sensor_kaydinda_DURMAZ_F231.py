# -*- coding: utf-8 -*-
"""F2-3.1 (2-F incelemesi A3, K1 · D2.39) — sensör kaydının ASILI diski STM OKUYUCUSUNU durdurmaz.

D2.39 (`d8a1828`) STM telemetrisini her satırda `_sensor_kaydedici.kaydet` ile diske yazdırır. `hardware.stm.telemetry` olayını STM
okuyucu iş parçacığı (`HeadlessCore._hw_sender_worker.reader` → `_handle_stm_line` → `_publish_event`) yayımlar ve
`api_server._handle_backend_event` EŞZAMANLI abone olduğu için kaydın G/Ç'si OKUYUCU İŞ PARÇACIĞINDA koşar. Kaydedicinin dizini
asılırsa (en alt kat: modülün `open`ı bir `Event` bekler) okuyucu sonraki satırları (kartın tüm-sıfır ACK'i = ACİL DURDUR teyidi,
NACK, STM_EVT) işleyemez; kaydedicinin kilidini tutan asılı okuyucu, yeniden bağlanmanın el sıkışmasını da (el sıkışma satırları aynı
işleyiciden geçer) kilitler.
ÖLÇÜM: GERÇEK `_hw_sender_worker` (okuyucu + gönderici + yeniden bağlanma), GERÇEK `_handle_stm_line`, GERÇEK olay veriyolu + api
işleyicileri, GERÇEK `SensorKaydedici` (dizin testin tmp'si); sahte olan yalnız seri taşıma (en alt kat) ve kaydedicinin `open`ı.
"""

from __future__ import annotations

import asyncio
import copy
import logging
import queue
import socket as _gercek_socket
import threading
import time
import types
from pathlib import Path

import pytest
from topoloji import TUM_STM


def _ack(dutyler) -> str:
    n = len(TUM_STM)
    d = ",".join(str(int(x)) for x in dutyler)
    sifir = ",".join("0" for _ in range(n))
    f = ",".join(("100" if x else "0") for x in dutyler)
    t = ",".join(("5" if x else "0") for x in dutyler)
    return f"-> STM_OK: D={d} P={sifir} F={f} T={t}"


TELE = "-> STM_TELE: C=6,T=34.20,A=27.10,B=1.842,N=412"


def _bekle(kosul, sure=5.0):
    son = time.monotonic() + sure
    while time.monotonic() < son and not kosul():
        time.sleep(0.01)
    return kosul()


@pytest.fixture
def ortam(monkeypatch, tmp_path):
    import builtins

    import event_bus as eb
    import headless_core as hcm
    from servers import api_server as api
    from servers import live_state as ls
    from servers import sensor_kaydedici as sk
    from utils.simple_signal import SimpleSignal

    d = types.SimpleNamespace(acilan=[], kapanan=[], yazilan=[], port_var=True, el_sikisma_satiri=None)
    asili = threading.Event()  # set = disk geri geldi
    d.asili = asili
    d.asili_girdi = threading.Event()
    sensor_dizin = tmp_path / "sensor_log"
    monkeypatch.setenv("PEMF_SENSOR_LOG_DIR", str(sensor_dizin))
    monkeypatch.delenv("PEMF_SENSOR_LOG", raising=False)
    monkeypatch.delenv("PEMF_ESP_ENABLED", raising=False)
    monkeypatch.setattr(sk, "_kaydedici", None)
    _gercek_open = builtins.open

    def _asili_open(yol, mode="r", *a, **k):
        # EN ALT KAT: kaydedicinin dizini asılı (USB/ağ paylaşımı, sürücü takıldı). Yalnız kaydedicinin YAZIM açılışı bekler.
        if "a" in mode and Path(str(yol)).parent == sensor_dizin:
            d.asili_girdi.set()
            asili.wait(30)
        return _gercek_open(yol, mode, *a, **k)

    monkeypatch.setattr(sk, "open", _asili_open, raising=False)

    yayinlar: list = []
    kaydet = lambda m, *a, **k: yayinlar.append(copy.deepcopy(m))  # noqa: E731
    monkeypatch.setattr(ls, "_ws_broadcast_sync", kaydet)
    monkeypatch.setattr(api, "_ws_broadcast_sync", kaydet)
    monkeypatch.setattr(api, "_push_notification", lambda *a, **k: None)
    monkeypatch.setattr(api, "_mqtt_publish", lambda topic, payload: False)
    monkeypatch.setattr(api, "_estop_cloud_mirror", lambda *a, **k: None)
    yeni_bus = eb.EventBus()
    monkeypatch.setattr(eb, "_event_bus_instance", yeni_bus)
    monkeypatch.setattr(api, "_event_bus_registered", False)
    monkeypatch.setattr(api, "_coil_last_telemetry", {})
    with api._session_lock:
        eski_seans = dict(api._active_session)
        api._active_session.clear()
    with ls._live_state_lock:
        eski = {k: copy.deepcopy(ls._live_state.get(k)) for k in ("stm", "coils", "activeTreatment", "estopTeyit")}
        ls._live_state["estopTeyit"] = None

    class _Conn:
        def __init__(self, ad):
            self.ad = ad
            self.port = f"COM_{ad}"
            self.is_open = True
            self.satirlar: queue.Queue = queue.Queue()

        def readline(self):
            try:
                return (self.satirlar.get(timeout=0.02) + "\n").encode()
            except queue.Empty:
                return b""

        def write(self, b):
            d.yazilan.append((time.monotonic(), self.ad, bytes(b)))

        def close(self):
            self.is_open = False

    class _Tasima:
        def __init__(self, *a, **k):
            pass

        def open_and_handshake(self, stop_event=None, on_line=None):
            c = _Conn(f"A{len(d.acilan)}")
            # gerçek taşıma el sıkışmada okunan HER satırı `on_line`a verir (STM_TELE dahil) → aynı işleyici
            if d.el_sikisma_satiri and on_line is not None:
                on_line(d.el_sikisma_satiri)
            d.acilan.append(c)
            return types.SimpleNamespace(serial=c, ready_line="-> STM_OK: hazir")

        def close_serial(self, c):
            d.kapanan.append(c)
            c.close()

        def port_hala_var(self, _port):
            return d.port_var

    def _soket_yok(*_a, **_k):
        raise OSError("test: UDP soketi kurulmaz")

    monkeypatch.setattr(hcm, "Stm32SerialTransport", _Tasima)
    monkeypatch.setattr(
        hcm,
        "socket",
        types.SimpleNamespace(
            socket=_soket_yok,
            AF_INET=_gercek_socket.AF_INET,
            SOCK_DGRAM=_gercek_socket.SOCK_DGRAM,
            SOL_SOCKET=_gercek_socket.SOL_SOCKET,
            SO_BROADCAST=_gercek_socket.SO_BROADCAST,
        ),
    )
    core = hcm.HeadlessCore.__new__(hcm.HeadlessCore)
    core.logger = logging.getLogger("test-F231")
    core.event_bus = yeni_bus
    core._stm_state_lock = threading.RLock()
    core.stm_is_connected = False
    core.stm_kimlik = None
    core.stm_uyumlu = None
    core.stm_uyumsuzluk_sebebi = ""
    core.stm_connected_signal = SimpleSignal()
    core.stm_connected_signal.connect(core._on_stm_connected_slot)
    core._hw_sender_stop = threading.Event()
    core._hw_send_queue = queue.Queue()
    core.mosquitto_supervisor = core.network_status_service = core.udp_discovery_service = None

    class _HC:  # teyitsiz E-stop (D1E04 aparatı): teyit YALNIZ kartın tüm-sıfır ACK'inden gelebilir
        coils_state = {b: {"is_running": False} for b in TUM_STM}

        def stop_all_coils(self):
            return False

        def update_coil(self, *a, **k):
            return True

        def on_disconnect(self):
            return True

    monkeypatch.setattr(api.state, "hardware", _HC())
    monkeypatch.setattr(api.state, "core", core)
    api._register_event_bus_handlers()
    t = threading.Thread(target=core._hw_sender_worker, daemon=True, name="test-F231-HWSender")
    core._hw_sender_thread = t  # üretimde __init__ atar; yoksa E-stop göndericiyi "ölü" sanıp ikincisini başlatır
    t.start()
    assert _bekle(lambda: d.acilan and core.stm_is_connected), f"aparat: STM bağlanmadı {d}"
    try:
        yield types.SimpleNamespace(api=api, ls=ls, sk=sk, core=core, d=d, yayinlar=yayinlar, dizin=sensor_dizin)
    finally:
        asili.set()
        core._hw_sender_stop.set()
        t.join(timeout=5)
        yeni_bus.shutdown()
        if sk._kaydedici is not None:
            sk._kaydedici.kapat()
        with api._session_lock:
            api._active_session.clear()
            api._active_session.update(eski_seans)
        with ls._live_state_lock:
            for k, v in eski.items():
                ls._live_state[k] = v


def _telemetri_isleyicide(o):
    """Aparat: telemetri satırı api işleyicisine ULAŞTI (damga kaydet çağrısından ÖNCE atılır — iki kolda da görünür)."""
    assert _bekle(lambda: o.api._coil_last_telemetry.get(5) is not None, 5.0), "aparat: telemetri işleyiciye ulaşmadı"
    print(f"OLCUM kaydedici_asili_open_girildi={o.d.asili_girdi.wait(0.5)}")


def _teyitli(o):
    return bool((o.api._build_ws_snapshot().get("estopTeyit") or {}).get("teyitli"))


def test_SONDA_asili_sensor_kaydi_KARTIN_ACIL_DURDUR_teyidini_BEKLETMEZ(ortam):
    """Kartın tüm-sıfır ACK'i (A-63 teyidi) bir telemetri satırının ARDINDAN gelir; kaydedici asılıyken de ≤1 sn'de işlenir."""
    o = ortam
    o.api._emergency_stop_all("manual")
    assert not _teyitli(o), "aparat: E-stop teyitsiz olmalı"
    conn = o.d.acilan[-1]
    t0 = time.monotonic()
    conn.satirlar.put(TELE)
    conn.satirlar.put(_ack([0] * len(TUM_STM)))
    _telemetri_isleyicide(o)
    islendi = _bekle(lambda: _teyitli(o), 1.0)
    sure = time.monotonic() - t0
    o.d.asili.set()  # disk geri geldi → aparat canlı mı (teyit SONRA geliyor mu)
    sonra = _bekle(lambda: _teyitli(o), 5.0)
    assert sonra, "aparat: disk geri geldikten sonra da teyit gelmedi (araç kör)"
    assert islendi, (
        f"kaydedici asılıyken STM okuyucusu DURDU: kartın tüm-sıfır ACK'i (ACİL DURDUR teyidi) {sure:.2f} sn'de işlenmedi; "
        "teyit ancak disk geri gelince geldi"
    )


def test_SONDA_asili_sensor_kaydi_YENIDEN_BAGLANMAYI_kilitlemez(ortam):
    """Asılı okuyucu kaydedicinin kilidini tutarken kablo çıkıp takılır: el sıkışmanın ilk satırı telemetri → yeni bağlantı ≤6 sn."""
    o = ortam
    conn = o.d.acilan[-1]
    conn.satirlar.put(TELE)
    _telemetri_isleyicide(o)
    # Disk asılı kalırken kablo çıkar: port yoklaması bağlantıyı düşürür; geri takılınca el sıkışma ilk satırı TELE okur.
    o.d.el_sikisma_satiri = TELE
    acilan_once = len(o.d.acilan)
    o.d.port_var = False
    assert _bekle(lambda: not o.core.stm_is_connected, 5.0), "aparat: port kaybı algılanmadı"
    o.d.port_var = True
    yeniden = _bekle(lambda: len(o.d.acilan) > acilan_once and o.core.stm_is_connected, 6.0)
    o.d.asili.set()
    sonra = _bekle(lambda: len(o.d.acilan) > acilan_once and o.core.stm_is_connected, 10.0)
    assert sonra, "aparat: disk geri geldikten sonra da yeniden bağlanılmadı (araç kör)"
    assert yeniden, (
        "kaydedici asılıyken YENİDEN BAĞLANMA kilitlendi: el sıkışma telemetri satırında kaydedicinin kilidini bekledi"
    )


def test_SONDA_asili_sensor_kaydi_ACIL_DURDUR_yanitini_ve_STOP_yazimini_GECIKTIRMEZ(ortam, monkeypatch):
    """Ö.4-Y8: okuyucu asılıyken (3 eşzamanlı istek + ACİL DURDUR, tek döngü) yanıt ve STOP'un porta yazımı ≤1 sn."""
    import httpx
    from controllers.hardware_controller import HardwareController

    o = ortam
    hc = HardwareController(o.core)
    try:
        monkeypatch.setattr(o.api.state, "hardware", hc)
        conn = o.d.acilan[-1]
        conn.satirlar.put(TELE)
        _telemetri_isleyicide(o)

        async def _s():
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=o.api.app, client=("127.0.0.1", 50000)),
                base_url="http://cihaz",
                timeout=30,
            ) as c:
                yazim_once = len(o.d.yazilan)
                t0 = time.monotonic()
                digerleri = [asyncio.create_task(c.get("/api/health")) for _ in range(3)]
                acil = asyncio.create_task(c.post("/api/hardware/emergency_stop"))
                r = await acil
                sure = time.monotonic() - t0
                for x in digerleri:
                    await x
                return r, sure, t0, yazim_once

        r, sure, t0, yazim_once = asyncio.run(_s())
        yazimlar = o.d.yazilan[yazim_once:]
        assert r.status_code == 200, r.text
        assert yazimlar, "STOP porta hiç yazılmadı"
        ilk = yazimlar[0][0] - t0
        print(f"OLCUM estop_yanit={sure:.3f}s stop_porta={ilk:.3f}s yazim={len(yazimlar)}")
        assert sure < 1.0 and ilk < 1.0, f"okuyucu asılıyken ACİL DURDUR {sure:.2f} sn / STOP porta {ilk:.2f} sn"
    finally:
        o.d.asili.set()
        hc.stop()


def test_SONDA_asili_sensor_kaydi_DOLU_kuyrukta_da_okuyucu_BEKLEMEZ(ortam, monkeypatch):
    """Disk asılı kaldıkça kayıt birikir: kuyruk dolunca satır ATILIR (sayılır), okuyucu yine beklemez (teyit ≤2 sn)."""
    o = ortam
    monkeypatch.setattr(o.sk, "_arka_kuyruk", queue.Queue(maxsize=8), raising=False)
    o.api._emergency_stop_all("manual")
    conn = o.d.acilan[-1]
    for _ in range(40):
        conn.satirlar.put(TELE)
    conn.satirlar.put(_ack([0] * len(TUM_STM)))
    islendi = _bekle(lambda: _teyitli(o), 2.0)
    atilan = o.sk.kaydedici().atilan if o.sk._kaydedici is not None else None
    o.d.asili.set()
    assert _bekle(lambda: _teyitli(o), 5.0), "aparat: disk geri gelince de teyit yok"
    print(f"OLCUM dolu_kuyruk_atilan={atilan}")
    assert islendi, "kuyruk dolunca STM okuyucusu BEKLEDİ (ACİL DURDUR teyidi 2 sn'de işlenmedi)"
