# Author: mertaygn, cglrgrkn
"""ESP FREKANS TAVANI — donanım-uyum denetimi D-3 (2026-08-19), 8266'ya göre.

NEDEN VAR: STM yolu freq'i normalize_frequency_hz (1-25000) ile clamp'lerken ESP MQTT yolu HAM
gönderiyordu. ESP firmware'i 1000 Hz sınırlı; >1000 komut → 8266 komutu TAMAMEN REDDEDER
(bobin başlamaz), S3 sessizce 1000'e kırpar (komut≠telemetri). Backend'in EN KISITLI ESP olan
8266'nın tavanına (1000) önden normalize etmesi, tüm ESP dizisini tutarlı yapar.
"""

from __future__ import annotations

import pytest

from utils.stm32_protocol_limits import (
    ESP_FREQ_MAX_HZ,
    FREQ_MAX_HZ,
    FREQ_MIN_HZ,
    normalize_esp_frequency_hz,
    normalize_frequency_hz,
)


def test_KRITIK_esp_tavani_8266_firmware_ile_BIREBIR():
    """ESP tavanı 8266 firmware constrain/validation sınırı (1000) ile aynı olmalı."""
    assert ESP_FREQ_MAX_HZ == 1000.0, (
        "ESP freq tavanı 8266 firmware sınırından (1000) sapmış — firmware constrain'leri güncellenmeden değişmez"
    )
    # STM tavanı ESP'den belirgin YÜKSEK (transport-farkındalıklı iki ayrı sınır)
    assert FREQ_MAX_HZ > ESP_FREQ_MAX_HZ, "STM ve ESP aynı tavana düşmüş — transport ayrımı kayboldu"


@pytest.mark.parametrize(
    "girdi,beklenen",
    [
        (1500, 1000.0),  # >1000 → 8266'nın reddedeceği değer, önden 1000'e çekilir
        (25000, 1000.0),  # STM tavanı bile ESP'de 1000'e iner
        (100, 100.0),  # tipik PEMF — dokunulmaz
        (1, 1.0),  # AI Pro 1 Hz — alt sınır
        (0, 1.0),  # alt sınır altı → FREQ_MIN
        (1000, 1000.0),  # tam tavan — geçer
        (1001, 1000.0),  # tavanın 1 üstü — 8266 reddederdi, clamp'lenir
        (-3, 1.0),  # negatif → alt sınıra (review yanlış-yeşil paketi)
        (None, 100.0),  # sayısal-olmayan → güvenli default
    ],
)
def test_KRITIK_esp_normalize_1000e_clampler(girdi, beklenen):
    assert normalize_esp_frequency_hz(girdi) == beklenen


def test_KRITIK_esp_ve_stm_normalize_AYRISIR():
    """Aynı girdi (1500 Hz) STM'de geçer (≤25000) ama ESP'de 1000'e iner — kanıt."""
    assert normalize_frequency_hz(1500) == 1500.0  # STM: 1500 geçerli
    assert normalize_esp_frequency_hz(1500) == 1000.0  # ESP: 1000'e clamp
    # sayısal olmayan girdi ikisinde de güvenli default (100)
    assert normalize_esp_frequency_hz("abc") == 100.0
    assert normalize_esp_frequency_hz(float("inf")) == 100.0


def test_KARSIT_KANIT_manuel_esp_yolu_normalize_KULLANIR():
    """Regresyon: manuel /api/coil control ESP dalı normalize_esp_frequency_hz çağırıyor mu."""
    import inspect

    import servers.api_server as api

    src = inspect.getsource(api)
    assert "normalize_esp_frequency_hz" in src, (
        "manuel ESP yolu ESP freq normalize kullanmıyor → >1000 komut 8266'da reddedilir / S3'te kırpılır"
    )
    assert FREQ_MIN_HZ == 1.0
