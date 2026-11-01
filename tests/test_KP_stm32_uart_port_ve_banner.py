# -*- coding: utf-8 -*-
"""KP-1 · `utils/stm32_uart.py` · sözleşmeler: ST-Link sanal COM portu adaylarda ÖNCE (backend `stm32_transport` ile aynı öncelik), açık
port isteği aynen · pyserial yoksa port listesi boş (çağıran karar verir) · açılış banner'ı dinlenirken boş / gürültü satırları atlanır,
ilgi satırları toplanır, banner gelince kanal sayısıyla HEMEN döner, gelmezse süre dolunca None · kart doğrulaması boş okuma ve boşluk
satırını banner saymaz, banner'dan sonra doğrulama yoklamasına geçer.

Gerçek COM / kart YOK: işletim sistemi port numaralandırması (`serial.tools.list_ports.comports`) ve seri port (`serial.Serial`) EN ALT
katta sahte; kart doğrulamasında depodaki bayt düzeyi kart öykünmesi (`_Kart`, T-a testi) kullanılır.
"""

from __future__ import annotations

import sys
import time
from types import SimpleNamespace

import pytest
import serial
import serial.tools.list_ports as lp
from test_Ta_stm_yak_GERI_DONUS_ve_NACK_ESIGI_TEZGAH2 import _Kart
from utils import stm32_uart as su

BANNER = "-> STM_READY: DDS v2.5 (7-ch KARMA uni=0x60 + HW_SYNC@PB1) proto=3 pkt=121 Waiting for commands..."


def test_KRITIK_ST_Link_portu_ONCE_aciklamasiz_port_da_listede_acik_istek_AYNEN(monkeypatch):
    monkeypatch.setattr(
        lp,
        "comports",
        lambda: [
            SimpleNamespace(device="COM3", description="USB Serial Device"),
            SimpleNamespace(device="COM7", description="STMicroelectronics STLink Virtual COM Port"),
            SimpleNamespace(device="COM9", description=None),
        ],
    )
    assert su.portlari_listele() == [
        su.PortBilgisi("COM3", "USB Serial Device"),
        su.PortBilgisi("COM7", "STMicroelectronics STLink Virtual COM Port"),
        su.PortBilgisi("COM9", ""),
    ]
    assert su.port_adaylari() == ["COM7", "COM3", "COM9"], (
        "ST-Link portu önce denenmiyor (backend ile farklı kart okunur)"
    )
    assert su.port_adaylari("COM5") == ["COM5"]


def test_pyserial_araclari_YOKSA_port_listesi_bos(monkeypatch):
    monkeypatch.setitem(sys.modules, "serial.tools", None)
    assert su.portlari_listele() == [] and su.port_adaylari() == []


class _Port:
    """`serial.Serial` sahtesi: `read` sırayla verilen parçaları döner, bitince boş bayt."""

    def __init__(self, parcalar):
        self.parcalar = list(parcalar)
        self.kapandi = False

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        self.kapandi = True
        return False

    def read(self, _n):
        return self.parcalar.pop(0) if self.parcalar else b""


def test_KRITIK_banner_gelince_kanal_sayisiyla_HEMEN_doner_gurultu_ve_bos_satir_atlanir(monkeypatch):
    acilan = []

    def _ac(port, baud, timeout=None):
        acilan.append((port, baud))
        return _Port(
            [b"\x00gurultu\r\n\r\n-> STM_TELE: C=1\r\n", (BANNER + "\r\n").encode(), b"-> STM_ERR: sonradan\r\n"]
        )

    monkeypatch.setattr(serial, "Serial", _ac)
    t0 = time.monotonic()
    kanal, satirlar = su.banner_dinle("COM7", sure=5.0)
    assert time.monotonic() - t0 < 2.0, "banner geldiği halde süre sonuna kadar beklendi"
    assert kanal == 7 and acilan == [("COM7", su.BAUD)]
    assert satirlar == ["-> STM_TELE: C=1", BANNER], "ilgi satırları toplanmadı ya da gürültü satırı eklendi"


def test_banner_GELMEZSE_sure_dolunca_None_ve_toplananlar(monkeypatch):
    monkeypatch.setattr(serial, "Serial", lambda port, baud, timeout=None: _Port([b"-> STM_NACK: CRC\r\n"]))
    kanal, satirlar = su.banner_dinle("COM3", sure=0.05)
    assert kanal is None and satirlar == ["-> STM_NACK: CRC"]


def test_kart_dogrulamasi_BOS_okuma_ve_BOSLUK_satirini_banner_saymaz(monkeypatch):
    class _BoslukluKart(_Kart):
        def __init__(self):
            super().__init__("yeni")
            self._once = [b"", b"   \r\n"]  # zaman aşımı (boş okuma) + yalnız boşluk satırı, SONRA banner

        def readline(self):
            return self._once.pop(0) if self._once else super().readline()

    kart = _BoslukluKart()
    monkeypatch.setattr(serial, "Serial", lambda port, baud=115200, timeout=None, **_k: kart)
    satirlar, ozet = su.kart_dogrula("COM7", 2.0)
    assert any("STM_READY" in s for s in satirlar) and not any(not s.strip() for s in satirlar)
    assert ozet["kabul"] and ozet["kimlik"], ozet
