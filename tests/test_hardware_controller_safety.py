"""Audit P1 (test-boşluğu #6): GERÇEK HardwareController güvenlik davranışları.

Mevcut testler yalnız FakeHW kullanıyordu → gerçek kontrolcünün donanım-tarafı süre-limiti
(_tick deadline auto-stop), duration<=0 DURATION_MAX üst-kapağı, on_disconnect re-fire
engelleme ve düşen-STOP telafisi regrese olsa YAKALANMAZDI (bobin süresiz enerjili / bağlantı
dönünce kendiliğinden yeniden ateşleme). Donanımsız: sahte core (_hw_send_queue) +
monotonic monkeypatch ile deterministik.
"""
import queue
import struct
import zlib

import pytest

from controllers import hardware_controller
from controllers.hardware_controller import HardwareController
from utils.stm32_protocol_limits import DURATION_MAX_MINUTES


class _FakeCore:
    def __init__(self):
        self._hw_send_queue = queue.Queue(maxsize=100)


@pytest.fixture
def hw():
    c = HardwareController(_FakeCore())
    # keep-alive thread'ini durdur → testler _tick'i DETERMİNİSTİK sürsün (arka-plan yarışı yok).
    c._keep_alive_stop.set()
    c._keep_alive_thread.join(timeout=2)
    yield c
    c.stop()


def _fake_clock(monkeypatch, holder):
    monkeypatch.setattr(hardware_controller.time, "monotonic", lambda: holder[0])


def test_deadline_auto_stop(hw, monkeypatch):
    clk = [1000.0]
    _fake_clock(monkeypatch, clk)
    assert hw.update_coil(1, 100.0, 25.0, 0.0, duration=1) is True  # deadline = 1000 + 1*60
    assert hw.coils_state[1]["is_running"] is True
    assert hw._coil_deadline[1] == pytest.approx(1060.0)
    # süre dolmadan: _tick DURDURMAZ
    clk[0] = 1059.0
    hw._tick()
    assert hw.coils_state[1]["is_running"] is True
    # süre dolunca: donanım-tarafı OTOMATİK durdurma (yazılım-watchdog'suz yolda son savunma)
    clk[0] = 1061.0
    hw._tick()
    assert hw.coils_state[1]["is_running"] is False
    assert hw.coils_state[1]["duty"] == 0.0
    assert hw._coil_deadline[1] is None
    # _tick expired'da 3 set eder, AYNI tick'te 1 azaltır → 2 kalır; sonraki tick'lerde STOP tekrar
    assert hw._force_send_left == 2  # STOP paketi birkaç döngü tekrar gönderilir (telafi)


def test_duration_zero_is_capped_not_unlimited(hw, monkeypatch):
    clk = [500.0]
    _fake_clock(monkeypatch, clk)
    hw.update_coil(2, 100.0, 25.0, 0.0, duration=0)  # duration<=0 → SINIRSIZ DEĞİL
    assert hw._coil_deadline[2] is not None
    assert hw._coil_deadline[2] == pytest.approx(500.0 + DURATION_MAX_MINUTES * 60)
    # DURATION_MAX dolunca yine durur (keep-alive'a rağmen)
    clk[0] = 500.0 + DURATION_MAX_MINUTES * 60 + 1
    hw._tick()
    assert hw.coils_state[2]["is_running"] is False


def test_start_all_duration_zero_capped(hw, monkeypatch):
    clk = [0.0]
    _fake_clock(monkeypatch, clk)
    hw.start_all_coils(duration=0)
    for i in range(1, 6):
        assert hw._coil_deadline[i] == pytest.approx(DURATION_MAX_MINUTES * 60)
        assert hw.coils_state[i]["is_running"] is True


def test_on_disconnect_resets_and_prevents_refire(hw):
    hw.start_all_coils(freq=100.0, duty=40.0, duration=30)
    assert any(hw.coils_state[i]["is_running"] for i in range(1, 6))
    hw.on_disconnect()
    for i in range(1, 6):
        assert hw.coils_state[i]["is_running"] is False
        assert hw.coils_state[i]["duty"] == 0.0
        assert hw.coils_state[i]["duration"] == 0
        assert hw._coil_deadline[i] is None
    # bağlantı kopuk → gönderim anlamsız (re-fire paketi ÜRETME)
    assert hw._force_send_left == 0


def test_stop_all_sets_force_send(hw):
    hw.start_all_coils(duration=30)
    hw.stop_all_coils()
    for i in range(1, 6):
        assert hw.coils_state[i]["is_running"] is False
        assert hw.coils_state[i]["duty"] == 0.0
        assert hw._coil_deadline[i] is None
    assert hw._force_send_left == 3  # düşen STOP telafisi


def test_invalid_coil_id_rejected(hw):
    assert hw.update_coil(0, 100.0, 25.0, 0.0, 30) is False
    assert hw.update_coil(6, 100.0, 25.0, 0.0, 30) is False


def test_stm_packet_crc_roundtrip(hw, monkeypatch):
    clk = [10.0]
    _fake_clock(monkeypatch, clk)
    while not hw.core._hw_send_queue.empty():
        hw.core._hw_send_queue.get_nowait()
    hw.update_coil(1, 100.0, 50.0, 0.0, duration=5)  # bir paket kuyruğa gider
    stm_msg, _udp, _ip, _port = hw.core._hw_send_queue.get_nowait()
    # header 0xAA,0x55 + crc32 gövde ile tutarlı olmalı (struct/crc round-trip)
    assert stm_msg[0] == 0xAA and stm_msg[1] == 0x55
    body, crc = stm_msg[:-4], struct.unpack("<I", stm_msg[-4:])[0]
    assert zlib.crc32(body) & 0xFFFFFFFF == crc
