# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""MQTT YAYIN TEYİDİ — `_mqtt_publish` sonucu GERÇEKTEN okunmalı (2026-08-09 denetimi, ENGEL).

ARIZA: `_mqtt_publish` `info.wait_for_publish(timeout=2.0)` çağırıp SONUCU YOK SAYARAK koşulsuz
`True` dönüyordu. Broker TCP bağlantısını kabul edip QoS-1 PUBACK'ini hiç göndermezse (broker
asılı, disk dolu, yetki reddi, ağ yarı-açık) mesaj TESLİM EDİLMEMİŞTİR — ama:

    _estop_one → "success"  →  _esp_ok = True  →  confirmed = True  →  arayüz "bobinler durdu"

Yani acil durdurmanın ESP ayağı sessizce başarısız olurken operatöre BAŞARILI görünüyordu.
Bu dosya zinciri iki uçtan da kilitler: taşıma katmanı yalan söylemesin, ve söylemediğinde
`_emergency_stop_all` bunu doğru şekilde `confirmed=False`'a çevirsin.
"""

import os

os.environ.pop("PEMF_SIMULATE", None)

import pytest


@pytest.fixture
def api():
    from servers import api_server

    return api_server


class _SahteInfo:
    """paho `MQTTMessageInfo` taklidi."""

    def __init__(self, yayinlandi: bool, patlat: Exception | None = None):
        self._yayinlandi = yayinlandi
        self._patlat = patlat
        self.wait_cagrildi = False

    def wait_for_publish(self, timeout=None):
        self.wait_cagrildi = True
        if self._patlat:
            raise self._patlat

    def is_published(self):
        return self._yayinlandi


class _SahteClient:
    son_info = None

    def __init__(self, *a, **k):
        self.baglandi = False

    def username_pw_set(self, *a, **k):
        pass

    def connect(self, *a, **k):
        self.baglandi = True

    def publish(self, topic, payload, qos=0):
        return _SahteClient.son_info

    def loop_start(self):
        pass

    def loop_stop(self):
        pass

    def disconnect(self):
        pass


@pytest.fixture
def mqtt_kur(api, monkeypatch):
    """Broker probe'unu ve paho istemcisini değiştir → gerçek broker gerekmez."""
    import socket as _socket

    class _SahteSocket:
        def close(self):
            pass

    monkeypatch.setattr(_socket, "create_connection", lambda *a, **k: _SahteSocket())

    import paho.mqtt.client as _paho

    monkeypatch.setattr(_paho, "Client", _SahteClient)

    def _ayarla(info):
        _SahteClient.son_info = info
        return info

    return _ayarla


# ── taşıma katmanı ───────────────────────────────────────────────────────────


def test_PUBACK_gelirse_True(api, mqtt_kur):
    info = mqtt_kur(_SahteInfo(yayinlandi=True))
    assert api._mqtt_publish("pemf/coil/6/control", {"command": "stop"}) is True
    assert info.wait_cagrildi, "wait_for_publish cagrilmadi — mesaj disconnect'ten once teslim edilmeyebilir"


def test_KRITIK_PUBACK_GELMEZSE_False(api, mqtt_kur):
    """Zaman aşımı = teslim edilmedi. Eskiden burada koşulsuz True dönüyordu."""
    mqtt_kur(_SahteInfo(yayinlandi=False))
    assert api._mqtt_publish("pemf/coil/6/control", {"command": "stop"}) is False, (
        "PUBACK gelmedigi halde yayin 'basarili' bildirildi"
    )


def test_KRITIK_wait_ISTISNA_atarsa_is_published_belirler(api, mqtt_kur):
    """paho ≥2.0 zaman aşımında istisna atar. İstisna yutulup True dönülmemeli;
    kesin cevabı `is_published()` verir."""
    mqtt_kur(_SahteInfo(yayinlandi=False, patlat=RuntimeError("timeout")))
    assert api._mqtt_publish("pemf/coil/6/control", {"command": "stop"}) is False


def test_wait_istisna_atsa_da_GERCEKTEN_yayinlandiysa_True(api, mqtt_kur):
    """Yarış: PUBACK wait'in istisnasından hemen sonra gelmiş olabilir → False-negatif üretme
    (gereksiz 'DOĞRULANAMADI' uyarısı operatörü alarm-körlüğüne iter)."""
    mqtt_kur(_SahteInfo(yayinlandi=True, patlat=RuntimeError("timeout")))
    assert api._mqtt_publish("pemf/coil/6/control", {"command": "stop"}) is True


def test_broker_erisilemezse_False(api, monkeypatch):
    import socket as _socket

    def _red(*a, **k):
        raise OSError("baglanti reddedildi")

    monkeypatch.setattr(_socket, "create_connection", _red)
    assert api._mqtt_publish("pemf/coil/6/control", {"command": "stop"}) is False


# ── zincir: taşıma yalanı → acil durdurma teyidi ─────────────────────────────


def test_KRITIK_ESP_yayini_dogrulanmazsa_ACIL_DURDURMA_confirmed_FALSE(api, monkeypatch):
    """Uçtan uca kapı: ESP publish'leri teyit edilmezse `confirmed` KESİNLİKLE False olmalı."""
    monkeypatch.setattr(api, "_mqtt_publish", lambda topic, payload: False)

    class _HW:
        def stop_all_coils(self):
            return True  # STM durdu

    monkeypatch.setattr(api.state, "hardware", _HW())

    sonuc = api._emergency_stop_all(reason="test")
    assert sonuc["stmStopped"] is True
    assert sonuc["confirmed"] is False, "ESP dogrulanmadigi halde acil durdurma 'teyitli' bildirildi"
    assert sonuc["status"] == "partial"
    assert all(r["mqtt"] == "mqtt_unavailable" for r in sonuc["mqttResults"])


def test_KRITIK_STM_STOP_dusmusse_confirmed_FALSE(api, monkeypatch):
    """`stop_all_coils()` artık başarısızlıkta False döner → bu da teyidi düşürmeli."""
    monkeypatch.setattr(api, "_mqtt_publish", lambda topic, payload: True)

    class _HW:
        def stop_all_coils(self):
            return False  # paket kuyruğa alınamadı

    monkeypatch.setattr(api.state, "hardware", _HW())

    sonuc = api._emergency_stop_all(reason="test")
    assert sonuc["stmStopped"] is False
    assert sonuc["confirmed"] is False, "STM STOP dusmus ama acil durdurma 'teyitli' bildirildi"


def test_her_iki_transport_da_dogrulanirsa_confirmed_TRUE(api, monkeypatch):
    """Regresyon kapısı: sıkılaştırma SAĞLIKLI kurulumda yanlış alarm ÜRETMEMELİ.
    (Alarm körlüğü de bir hasta-güvenliği riskidir.)"""
    monkeypatch.setattr(api, "_mqtt_publish", lambda topic, payload: True)

    class _HW:
        def stop_all_coils(self):
            return True

    monkeypatch.setattr(api.state, "hardware", _HW())

    sonuc = api._emergency_stop_all(reason="test")
    assert sonuc["confirmed"] is True and sonuc["status"] == "success"


def test_ESP_STOP_daima_TUM_ESP_bobinlerine_gider(api, monkeypatch):
    """Regresyon kapısı (önceki P0): acil durdurma seans kapsamıyla SINIRLANDIRILAMAZ."""
    gidilen = []
    monkeypatch.setattr(api, "_mqtt_publish", lambda topic, payload: gidilen.append(topic) or True)
    monkeypatch.setattr(api.state, "hardware", None)

    with api._session_lock:
        api._active_session["coil_ids"] = [1, 2, 3]  # yalnız STM bobinleri
    sonuc = api._emergency_stop_all(reason="test")

    hedefler = {t.split("/")[2] for t in gidilen if t.startswith("pemf/coil/")}
    assert {"6", "7", "8"} <= hedefler, f"tum ESP bobinlerine STOP gitmedi: {hedefler}"
    assert len(sonuc["mqttResults"]) == 3
