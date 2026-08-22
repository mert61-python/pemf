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


# ── 2. TUR DENETİMİ [4.4] (2026-08-20): SEANS YOLU DA CLAMP'LENİR ────────────────────────────
# D-3 düzeltmesi (ffd4406) üç ham yayın sitesinden yalnız İKİSİNİ (tek-bobin + batch) kapatmıştı;
# `/api/session/start`ın ESP dalı ham `payload.frequency` göndermeye devam ediyordu ve doküman
# yine de D-3'ü "✅ düzeltildi" işaretliyordu — bu deponun bir kez yandığı "kısmi düzeltme"
# deseninin ta kendisi. Aşağıdaki testler DAVRANIŞSAL: gerçek endpoint koşar, ESP'ye GİDEN
# MQTT payload'u ölçülür (eski KARSIT_KANIT yalnız kaynakta substring arıyordu — üç siteden
# HERHANGİ biri normalize kullansa geçiyordu; bu boşluğu yapısal olarak göremezdi).


def _seans_baslat_ve_esp_payloadini_yakala(monkeypatch, frequency: float):
    import time as _t

    from fastapi.testclient import TestClient

    import servers.api_server as api

    yayinlar: list = []
    monkeypatch.setattr(api, "_mqtt_publish", lambda t, p=None, *a, **k: yayinlar.append((t, dict(p or {}))) or True)
    monkeypatch.setattr(api, "_ws_broadcast_sync", lambda *a, **k: None)
    monkeypatch.setattr(api, "_push_notification", lambda *a, **k: None)
    monkeypatch.setattr(api.state, "hardware", None)

    with api._session_lock:
        eski_sess = dict(api._active_session)
    try:
        r = TestClient(api.app).post(
            "/api/session/start",
            json={
                "mode": "Manuel",
                "frequency": frequency,
                "duty": 25,
                "intensity": 0,
                "duration_minutes": 5,
                "coil_ids": [6],
            },
        )
        assert r.status_code == 200, f"seans başlatılamadı: {r.status_code} {r.text}"
        # ESP publish'leri ARKA PLAN thread'inde gider (bilinçli: broker yavaşsa start bekletilmez)
        # → yayını kısa bir pencerede bekle.
        for _ in range(100):
            eslesen = [p for t, p in yayinlar if t == "pemf/coil/6/control" and p.get("command") == "start"]
            if eslesen:
                return eslesen[0]
            _t.sleep(0.02)
        raise AssertionError(f"seans ESP start yayını görülmedi: {yayinlar!r}")
    finally:
        with api._session_lock:
            api._active_session.clear()
            api._active_session.update(eski_sess)
        # start'ın açtığı per-bobin run kaydını kapat (modül durumu sonraki testlere sızmasın)
        try:
            api._finish_coil_run(6)
        except Exception:
            pass


def test_KRITIK_seans_yolu_esp_freqini_1000e_clampler(monkeypatch):
    payload = _seans_baslat_ve_esp_payloadini_yakala(monkeypatch, frequency=5000)
    assert payload.get("freq") == 1000.0, (
        f"seans yolu ESP'ye HAM freq gönderdi: {payload!r} — STM bobinleri 5000 Hz'de, ESP'ler "
        "sessizce 1000'de → karma dizide tutarsız doz (D-3'ün üçüncü yolu, bulgu [4.4])"
    )


def test_KARSIT_KANIT_seans_yolu_tipik_frekansa_DOKUNMAZ(monkeypatch):
    payload = _seans_baslat_ve_esp_payloadini_yakala(monkeypatch, frequency=100)
    assert payload.get("freq") == 100.0, f"tipik 100 Hz değişti: {payload!r}"


def test_KARSIT_KANIT_manuel_esp_yolu_normalize_KULLANIR():
    """Regresyon: manuel /api/coil control ESP dalı normalize_esp_frequency_hz çağırıyor mu."""
    import inspect

    import servers.api_server as api

    src = inspect.getsource(api)
    assert "normalize_esp_frequency_hz" in src, (
        "manuel ESP yolu ESP freq normalize kullanmıyor → >1000 komut 8266'da reddedilir / S3'te kırpılır"
    )
    assert FREQ_MIN_HZ == 1.0
