# -*- coding: utf-8 -*-
"""E2-3.12 (2-E incelemesi A3) — D2.10 kapısının KÖR kolu: kesinti SÜRERKEN açılış hatasının TÜRÜ değişirse (port yok → port VAR ama erişim
reddi / meşgul) yeni durum özet aralığını (600 sn) BEKLEMEDEN hemen bir kez yazılır.

Ürün HEAD'de doğru (imza = port + hata türü + metin). Ama 2-E'nin D2.10 kapısı imzadan tür + metin düşürülünce (`imza = (port,)`, mutant k5a)
YEŞİL kaldı (2-E incelemesi kaydı): "başka bir program portu tutuyor" teşhisi 10 dk'ya dek görünmez olurdu.
Ölçüm: GERÇEK `Stm32SerialTransport.open_and_handshake`, sahte saat (modülün `time`'ı, `headless_core` aralığı ~3 sn), açılış hatası EN ALT
katta (`serial.serialwin32.Serial.open`) gerçek pyserial biçimiyle: önce FileNotFoundError, sonra PermissionError (erişim reddi). Gerçek COM
portu AÇILMAZ.
"""

from __future__ import annotations

import logging
import sys
import threading
import time
import types
import uuid

import pytest

_PORT = "COM239"


@pytest.fixture
def ortam(monkeypatch):
    pytest.importorskip("serial")
    if sys.platform != "win32":
        pytest.skip("serialwin32 yalnız Windows")
    import serial
    from serial import serialwin32
    from serial.tools import list_ports
    from utils import stm32_transport as st

    saat = {"t": 1000.0}
    monkeypatch.setattr(
        st,
        "time",
        types.SimpleNamespace(
            monotonic=lambda: saat["t"], sleep=lambda sn: saat.__setitem__("t", saat["t"] + sn), time=time.time
        ),
    )
    monkeypatch.setattr(st, "FIXED_STM32_PORT", _PORT)
    monkeypatch.setattr(list_ports, "comports", lambda *a, **k: [])
    monkeypatch.setenv("PEMF_STM_PORT", _PORT)
    hata = {"tur": "yok"}

    def _ac(self):  # en alt kat: gerçek pyserial'in Windows açılış hatası biçimi
        if hata["tur"] == "yok":
            raise serial.SerialException(
                f"could not open port '{self.portstr}': FileNotFoundError(2, 'Sistem belirtilen dosyayı bulamıyor.', None, 2)"
            )
        raise serial.SerialException(
            f"could not open port '{self.portstr}': PermissionError(13, 'Erişim engellendi.', None, 5)"
        )

    monkeypatch.setattr(serialwin32.Serial, "open", _ac)
    kayitlar: list[logging.LogRecord] = []

    class _T(logging.Handler):
        def emit(self, record):
            kayitlar.append(record)

    log = logging.getLogger("test.e2312." + uuid.uuid4().hex)
    log.propagate = False
    log.setLevel(logging.DEBUG)
    log.addHandler(_T())
    return types.SimpleNamespace(st=st, saat=saat, log=log, kayitlar=kayitlar, hata=hata)


def _dene(o, t, n):
    for _ in range(n):
        o.saat["t"] += 3.05
        assert t.open_and_handshake(stop_event=threading.Event()) is None


def test_KRITIK_kesinti_surerken_ERISIM_REDDI_hemen_bir_kez_gorunur_E2312(ortam):
    t = ortam.st.Stm32SerialTransport(ortam.log)
    _dene(ortam, t, 10)  # ~30 sn: port yok
    once = len(ortam.kayitlar)
    ortam.hata["tur"] = "erisim_reddi"  # başka bir program portu açtı
    _dene(ortam, t, 10)  # ~30 sn: erişim reddi
    yeni = [r.getMessage() for r in ortam.kayitlar[once:] if r.levelno >= logging.WARNING]
    assert any("PermissionError" in m for m in yeni), (
        "kesinti sürerken hata TÜRÜ değişti (erişim reddi) ama 30 sn'de yazılmadı — özet aralığına (600 sn) kaldı:\n"
        + "\n".join(r.getMessage() for r in ortam.kayitlar)
    )
    assert sum("PermissionError" in m for m in yeni) == 1, f"yeni durum BİR KEZ yazılmalı: {yeni}"
