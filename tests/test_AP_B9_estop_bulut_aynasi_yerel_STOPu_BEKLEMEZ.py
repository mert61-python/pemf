# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""AP · B9 (istem 48, tezgâh 13 Kasım 2026 15:26:49): ACİL DURDUR'un BULUT AYNASI zaman aşımına düştü ("E-stop bulut aynasi
basarisiz (yerel yol etkilenmez): timed out" × 2) — yerel yol etkilenmedi (kart < 1 sn'de D=0). Bu dosya bulut çağrısının YEREL
STOP'u HİÇBİR koşulda beklemediğini kanıtlar (Ö.4-Y8):
  1) ayna SÜRESİZ asılı kalsa da `_emergency_stop_all` saniyeler içinde döner; STM STOP aynadan ÖNCE gider, yerel ESP STOP'ları gider;
  2) ayna iş parçacığı AÇILAMAZSA (iş parçacığı tükenmesi) yerel yol yine SÜRER;
  3) bulut bağlantısı zaman aşımına düşerse yalnız günlüğe yazılır (kullanıcıya bildirim / istisna YOK).
Ağa çıkılmaz: ayna sahtelenir ya da paho istemcisi sahte (bağlantı denemesi ağa gitmez).
"""

from __future__ import annotations

import logging
import socket
import threading
import time

import pytest


@pytest.fixture
def api(monkeypatch):
    from servers import api_server as _api

    olaylar: list[str] = []
    yayinlar: list[str] = []

    class _HW:
        def stop_all_coils(self):
            olaylar.append("stm_stop")
            return True

    monkeypatch.setattr(_api.state, "hardware", _HW())
    monkeypatch.setenv("PEMF_ESP_ENABLED", "1")

    def _yayin(topic, payload):
        yayinlar.append(topic)
        return True

    monkeypatch.setattr(_api, "_mqtt_publish", _yayin)
    _api._ap_b9 = {"olaylar": olaylar, "yayinlar": yayinlar}
    yield _api
    del _api._ap_b9


def test_KRITIK_ASILI_bulut_aynasi_yerel_STOPu_GECIKTIRMEZ(api, monkeypatch):
    basladi, birak = threading.Event(), threading.Event()
    olaylar = api._ap_b9["olaylar"]

    def _asili_ayna(coil_ids, reason):
        olaylar.append("ayna_basladi")
        basladi.set()
        birak.wait(30)  # 13-11'deki ~15 sn bağlantı denemesinden uzun

    monkeypatch.setattr(api, "_estop_cloud_mirror", _asili_ayna)
    try:
        t0 = time.monotonic()
        api._emergency_stop_all(reason="ap-b9", kalici=False)
        sure = time.monotonic() - t0
        assert basladi.wait(5), "bulut aynası hiç başlamadı — senaryo kurulamadı (test kör)"
        assert sure < 5.0, f"_emergency_stop_all asılı bulut aynasını BEKLEDİ ({sure:.1f} sn)"
        assert not birak.is_set()
        assert olaylar[0] == "stm_stop", f"STM STOP bulut aynasından ÖNCE gitmeli: {olaylar}"
        assert any(t.startswith("pemf/coil/") for t in api._ap_b9["yayinlar"]), "yerel ESP STOP yayını gitmedi"
    finally:
        birak.set()


def test_KRITIK_ayna_is_parcacigi_ACILAMAZSA_yerel_yol_SURER(api, monkeypatch):
    gercek = threading.Thread
    denendi = []

    class _Thread(gercek):
        def __init__(self, *a, **k):
            if k.get("name") == "estop-cloud-mirror":
                denendi.append(True)
                raise RuntimeError("can't start new thread (AP-B9 sahte tükenme)")
            super().__init__(*a, **k)

    monkeypatch.setattr(threading, "Thread", _Thread)
    sonuc = api._emergency_stop_all(reason="ap-b9-thread", kalici=False)
    assert denendi, "ayna iş parçacığı denenmedi — senaryo kurulamadı (test kör)"
    assert "stm_stop" in api._ap_b9["olaylar"]
    assert any(t.startswith("pemf/coil/") for t in api._ap_b9["yayinlar"]), "yerel ESP STOP yayını gitmedi"
    assert sonuc is not None


def test_bulut_ZAMAN_ASIMI_yalniz_GUNLUGE_kullaniciya_bildirim_YOK(api, monkeypatch, caplog):
    import paho.mqtt.client as pm
    from utils import secrets_manager

    degerler = {
        "mqtt_cloud_host": "bulut.ornek",
        "mqtt_cloud_user": "u",
        "mqtt_cloud_pass": "p",
        "mqtt_cloud_port": "8883",
    }
    monkeypatch.setattr(secrets_manager, "get_secret", lambda ad, default="", generate=False: degerler.get(ad, default))
    baglanti = []

    class _Istemci:
        def __init__(self, *a, **k):
            pass

        def username_pw_set(self, *a, **k):
            pass

        def tls_set(self, *a, **k):
            pass

        def connect(self, host, port, keepalive=60):
            baglanti.append((host, port))
            raise socket.timeout("timed out")

    monkeypatch.setattr(pm, "Client", _Istemci)
    bildirimler = []
    monkeypatch.setattr(api, "_bildir", lambda *a, **k: bildirimler.append(a))
    with caplog.at_level(logging.WARNING):
        api._estop_cloud_mirror([6, 7, 8], "ap-b9-zaman-asimi")  # istisna YÜKSELMEZ
    assert baglanti == [("bulut.ornek", 8883)], "sahte bulut bağlantısı denenmedi — senaryo kurulamadı (test kör)"
    assert any("yerel yol etkilenmez" in r.getMessage() and "timed out" in r.getMessage() for r in caplog.records)
    assert bildirimler == [], (
        "bulut aynası hatası kullanıcıya bildirim olarak GİTMEMELİ (yerel ACİL DURDUR teyidi ayrı yoldan)"
    )
