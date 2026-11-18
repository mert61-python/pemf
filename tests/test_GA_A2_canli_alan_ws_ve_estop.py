# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""GA (istem 53) A2 — canlı alanın `/ws` bağlantısı + ACİL DURDUR'dan bağımsızlığı.

SÖZLEŞME:
  - İstemci `{"type": "alan_abone", "acik": true|false}` ile abone olur / çıkar; bağlantı koparsa abonelik SİLİNİR.
  - `alan_haritasi` YALNIZ abonelere gider (`_ws_broadcast_sync(..., alicilar=[...])`); alıcısız yayın bütün istemcilere (DEĞİŞMEDİ).
    `alan_haritasi` periyodik tür → geri basınçta ilk o düşer (tek seferlik geçişler — E-stop vb. — düşmez, D1.71).
  - Hesap ACİL DURDUR'u / bobin durdurmayı BEKLETMEZ: hesap iş parçacığı TAKILI iken `POST /api/hardware/emergency_stop` ve
    `HardwareController.stop_all_coils()` döner (ortak kilit YOK; bobin durumu anlık görüntüyle okunur, hesap kilit DIŞINDA).
"""

from __future__ import annotations

import asyncio
import json
import threading
import time

import pytest


class _Istemci:
    def __init__(self):
        self.alinan: list[dict] = []

    async def send_text(self, data):
        self.alinan.append(json.loads(data))

    async def close(self, code=None):
        pass


@pytest.fixture
def ws_ortami(monkeypatch):
    from servers import live_state as ls

    dongu = asyncio.new_event_loop()
    a, b = _Istemci(), _Istemci()
    monkeypatch.setattr(ls, "_event_loop", dongu)
    monkeypatch.setattr(ls, "_ws_clients", [a, b])
    monkeypatch.setattr(ls, "_ws_send_lock", None)
    monkeypatch.setattr(ls, "_ws_pending", 0)
    monkeypatch.setattr(ls, "_ws_bekleyenler", __import__("collections").deque())
    try:
        yield ls, dongu, a, b
    finally:
        for _ in range(50):
            dongu.run_until_complete(asyncio.sleep(0.002))
        dongu.close()


def _adim(dongu, n=5):
    for _ in range(n):
        dongu.run_until_complete(asyncio.sleep(0.002))


def test_KRITIK_GA_A2_yayin_ALICISIZ_herkese_ALICILI_yalniz_abonelere(ws_ortami):
    ls, dongu, a, b = ws_ortami
    ls._ws_broadcast_sync({"type": "estop_mandali", "data": {"x": 1}})  # alıcısız: DEĞİŞMEDİ
    _adim(dongu)
    assert [m["type"] for m in a.alinan] == ["estop_mandali"] == [m["type"] for m in b.alinan]
    ls._ws_broadcast_sync({"type": "alan_haritasi", "data": {"durum": "sifir"}}, alicilar=[b])
    _adim(dongu)
    assert [m["type"] for m in a.alinan] == ["estop_mandali"]
    assert [m["type"] for m in b.alinan] == ["estop_mandali", "alan_haritasi"]
    ls._ws_broadcast_sync({"type": "alan_haritasi", "data": {}}, alicilar=[])  # abone yok → kimseye
    _adim(dongu)
    assert len(a.alinan) == 1 and len(b.alinan) == 2
    assert "alan_haritasi" in ls._WS_PERIYODIK_TURLER


@pytest.fixture
def api(monkeypatch):
    from servers import api_server as _api

    class _HW:
        def __init__(self):
            self.durum = {1: {"freq": 100.0, "duty": 0.5, "phase": 0.0}}
            self.durduruldu = 0

        def calisan_bobin_durumu(self):
            return dict(self.durum)

        def stop_all_coils(self):
            self.durduruldu += 1
            return True

    hw = _HW()
    monkeypatch.setattr(_api.state, "hardware", hw)
    yield _api, hw


def test_KRITIK_GA_A2_ws_ABONE_ol_cik_KOPUNCA_silinir(api, monkeypatch):
    from fastapi.testclient import TestClient

    _api, _ = api
    olaylar = []
    monkeypatch.setattr(_api._canli_alan, "abone", lambda ws, acik: olaylar.append((id(ws), bool(acik))))
    c = TestClient(_api.app)
    with c.websocket_connect("/ws") as ws:
        assert ws.receive_json()["type"] == "snapshot"
        ws.send_text(json.dumps({"type": "alan_abone", "acik": True}))
        ws.send_text(json.dumps({"type": "ping"}))
        assert ws.receive_json()["type"] == "pong"  # sıra: abonelik işlendi
        ws.send_text(json.dumps({"type": "alan_abone", "acik": False}))
        ws.send_text(json.dumps({"type": "alan_abone"}))  # acik yok → çıkış
        ws.send_text(json.dumps({"type": "ping"}))
        assert ws.receive_json()["type"] == "pong"
    t0 = time.monotonic()
    while len(olaylar) < 4 and time.monotonic() - t0 < 5:
        time.sleep(0.01)
    kim = {k for k, _ in olaylar}
    assert len(kim) == 1  # hep aynı bağlantı
    assert [a for _, a in olaylar] == [True, False, False, False]  # son: kopunca (finally) silinir


def test_KRITIK_GA_A2_api_bobin_durumu_DONANIMDAN_donanim_yoksa_bos(api, monkeypatch):
    _api, hw = api
    assert _api._canli_alan_bobinleri() == {1: {"freq": 100.0, "duty": 0.5, "phase": 0.0}}
    monkeypatch.setattr(_api.state, "hardware", None)
    assert _api._canli_alan_bobinleri() == {}


def test_KRITIK_GA_A2_api_gonderim_YALNIZ_abonelere(api, monkeypatch):
    _api, _ = api
    giden = []
    monkeypatch.setattr(_api, "_ws_broadcast_sync", lambda ileti, alicilar=None: giden.append((ileti, alicilar)))
    w = object()
    _api._canli_alan._gonder({"type": "alan_haritasi", "data": {}}, [w])
    assert giden == [({"type": "alan_haritasi", "data": {}}, [w])]


def test_KRITIK_GA_A2_hesap_TAKILIYKEN_ACIL_DURDUR_ve_bobin_durdurma_DONER(api, monkeypatch):
    """Hesap (alt süreç yanıtı beklenirken) TAKILI → GERÇEK `HardwareController.stop_all_coils()`
    (durum kilidi) ve ACİL DURDUR ucu beklemeden döner; hesap hâlâ takılıdır (ACİL DURDUR onu beklemedi)."""
    from ai_pro_aparati import istemci, mandali_sifirla
    from kayitci_donanim import gercek_hc
    from servers import canli_alan

    _api, hw = api
    basladi, birak = threading.Event(), threading.Event()

    def takili_hesap(bobinler):
        basladi.set()
        birak.wait(30)
        return {"durum": "tamam"}

    with gercek_hc() as hc:
        hc.coils_state[2].update(is_running=True, duty=0.4, phase=90.0, freq=100.0)
        servis = canli_alan.CanliAlan(hc.calisan_bobin_durumu, lambda *a: None, hesap=takili_hesap, aralik_s=0.01)
        monkeypatch.setattr(_api, "_canli_alan", servis)
        ws = object()
        servis.abone(ws, True)
        c = istemci(_api.app)
        try:
            assert basladi.wait(10)
            t0 = time.monotonic()
            hc.stop_all_coils()
            assert time.monotonic() - t0 < 1.0
            assert hc.calisan_bobin_durumu() == {}
            t0 = time.monotonic()
            r = c.post("/api/hardware/emergency_stop")
            sure = time.monotonic() - t0
            assert r.status_code == 200
            assert sure < 5.0, sure
            assert hw.durduruldu >= 1
            assert servis._is is not None and servis._is.is_alive()  # hesap HÂLÂ takılı
        finally:
            birak.set()
            servis.abone(ws, False)
            mandali_sifirla(c)
