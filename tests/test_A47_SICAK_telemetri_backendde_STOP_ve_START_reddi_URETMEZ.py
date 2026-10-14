# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""A-47 / Y2 · 1-D inceleme i2-F-1 — BACKEND'de termal kesme/engelleme YOK: sıcak STM telemetrisi (bobin 6-7, 49/63/120 °C)
ne STOP ne acil durdurma ne START reddi üretir.

ÖLÇÜLEN AÇIK: D1.67'nin A-47 kilidi yalnız istemci panelindeydi (jest) ve firmware olayı `STM_EVT` dalındaydı; backend
için kanıt yalnız grep'ti. İşleyiciye "objectTemp > 48 → acil durdurma" ya da "→ bobin STOP" eklenmesi, ya da
`HardwareController.update_coil`'a "ölçülen sıcaklık > 48 → START reddi" eklenmesi ilgili 28 kapı dosyasının (291 test)
tamamında YEŞİL kalıyordu (i2 ölçümü). Hiçbir mevcut test 48 °C üstü STM telemetrisiyle sürüşü/START'ı ölçmüyordu
(`test_stm_sensor_telemetrisi` en çok 41,7 °C besler).

SAHİP KARARI A-47 + Y2: bobin 1–7 için hiçbir katmanda (firmware, backend, istemci) otomatik termal engelleme/kesme
yok; 48 °C yalnız görsel uyarı. (Y40: ESP8266'nın bobin 8 için kendi 100 °C kesmesi firmware'dedir, bu kapının dışında.)

KAPI: GERÇEK satır yolu (`HeadlessCore._handle_stm_line` → yayın → `api._handle_backend_event`) + GERÇEK
`HardwareController` (kayıtçı kuyruk, firmware aynası) + GERÇEK sensör döngüsü turu. Ölçüt TEL: kuyruğa giden paket,
`stop_all_coils` ve acil durdurma çağrısı, START kabulü. Zaman yalnız `api_server.time` vekiliyle ilerler.
"""

from __future__ import annotations

import sys
import time as _gercek_zaman
import types
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(KOK / "tests"))

from dongu_tek_tur import bir_tur_kos  # noqa: E402


class _ModulSaati:
    """`api_server.time` vekili: `monotonic` = gerçek + `ek`; diğer her şey gerçek modül."""

    def __init__(self):
        self.ek = 0.0

    def monotonic(self):
        return _gercek_zaman.monotonic() + self.ek

    def __getattr__(self, ad):
        return getattr(_gercek_zaman, ad)


class _Olay:
    def __init__(self, tip: str, govde: dict):
        self.event_type = tip
        self.data = govde


class _SahteAlanKaydi:
    def seans_basladi(self, *a, **k):
        return None

    def seans_bitti(self, *a, **k):
        return None

    def olcum(self, *a, **k):
        return None

    def son_deger(self):
        return None

    def zirve(self):
        return None


_ALANLAR = ("objectTemp", "ambientTemp", "magneticMt", "currentA")


def _temizle(api):
    with api._live_state_lock:
        for i in range(8):
            c = api._live_state["coils"][i]
            for a in _ALANLAR:
                c[a] = 0.0
            c["measuredFields"] = []
            c["running"] = False
    for i in range(8):
        api._coil_olculen_alanlar.pop(i, None)
        api._coil_last_telemetry.pop(i, None)
    with api._minute_acc_lock:
        api._minute_acc.clear()
    with api._sensor_sample_buffer_lock:
        api._sensor_sample_buffer.clear()


@pytest.fixture
def o(monkeypatch, tmp_path):
    from ai_pro_aparati import istemci
    from database.treatment_history_db import TreatmentHistoryDB
    from headless_core import HeadlessCore
    from kayitci_donanim import gercek_hc
    from servers import api_server as api
    from servers import coil_run_tracker as crt
    from servers import live_state
    from utils import estop_mandali

    kok = tmp_path / "gecmis"
    kok.mkdir()
    db = TreatmentHistoryDB(kok)
    monkeypatch.setattr(api, "_get_treatment_db", lambda: db)
    monkeypatch.setattr(crt, "_treatment_db_getter", lambda: db)
    monkeypatch.setattr(api, "_kayit_db_hazir", lambda: (True, ""))
    bildirim: list = []
    monkeypatch.setattr(api, "_push_notification", lambda m, t="info", *a, **k: bildirim.append((m, t)))
    ws: list = []
    monkeypatch.setattr(api, "_ws_broadcast_sync", ws.append)
    monkeypatch.setattr(live_state, "_ws_broadcast_sync", ws.append)
    monkeypatch.setattr(api, "_mqtt_publish", lambda topic, payload: True)
    monkeypatch.setattr(api, "_estop_cloud_mirror", lambda *a, **k: None)
    monkeypatch.setattr(api, "_estop_ack_watch", lambda *a, **k: None)
    monkeypatch.setattr(api, "_start_ack_izle_arka_planda", lambda *a, **k: None)
    monkeypatch.setattr(api, "_broker_reachable", lambda timeout=0.3: True)
    monkeypatch.setattr(api, "_seans_alan", _SahteAlanKaydi())
    monkeypatch.setattr(api.state, "core", types.SimpleNamespace(stm_uyumlu=None))
    monkeypatch.setattr(api, "_RL_REMOTE_MAX", 0)
    saat = _ModulSaati()
    monkeypatch.setattr(api, "time", saat)
    # Acil durdurma çağrıları KAYDEDİLİR (gerçek yol yine koşar): sıcak telemetri onu tetiklememeli.
    acil: list = []
    _orj_async = api._emergency_stop_async
    _orj_all = api._emergency_stop_all

    def _kayitli_async(*a, **k):
        acil.append(("async", a, k))
        return _orj_async(*a, **k)

    def _kayitli_all(*a, **k):
        acil.append(("all", a, k))
        return _orj_all(*a, **k)

    monkeypatch.setattr(api, "_emergency_stop_async", _kayitli_async)
    monkeypatch.setattr(api, "_emergency_stop_all", _kayitli_all)
    live_state.stm_komut_kabulu_bildir()
    estop_mandali.sifirla("test-izolasyon")
    _temizle(api)
    with api._session_lock:
        eski_seans = dict(api._active_session)
        api._active_session["is_active"] = False

    # GERÇEK satır yolu: HeadlessCore._handle_stm_line → (yayın) → api._handle_backend_event
    def _yayinla(tip, govde, priority=None):
        api._handle_backend_event(_Olay(tip, govde))

    hc_kopru = types.SimpleNamespace(
        logger=__import__("logging").getLogger("a47.sicak"),
        _TELE_DESENI=HeadlessCore._TELE_DESENI,
        _publish_event=_yayinla,
    )
    hc_kopru._parse_stm_tele = lambda s: HeadlessCore._parse_stm_tele(hc_kopru, s)

    def satir(s: str):
        HeadlessCore._handle_stm_line(hc_kopru, s)

    try:
        with gercek_hc() as hc:
            monkeypatch.setattr(api.state, "hardware", hc)
            yield types.SimpleNamespace(api=api, hc=hc, c=istemci(api.app), saat=saat, acil=acil, satir=satir)
    finally:
        estop_mandali.sifirla("test-izolasyon")
        with api._session_lock:
            api._active_session.clear()
            api._active_session.update(eski_seans)
        _temizle(api)
        live_state.stm_komut_kabulu_bildir()


def _paketler(o, once=0) -> list:
    from kayitci_donanim import paket_coz

    return [[round(float(x), 4) for x in paket_coz(p)[0]] for p in o.hc.core._hw_send_queue.paketler[once:]]


def _calisan(o) -> list:
    return sorted(i for i, s in o.hc.coils_state.items() if s["is_running"])


def _tur(api, n=1):
    for _ in range(n):
        uyku, hatalar = bir_tur_kos(api._sensor_persistence_loop)
        assert (uyku, hatalar) == (1, []), (uyku, hatalar)


def _mf(api, cid):
    with api._live_state_lock:
        c = api._live_state["coils"][cid - 1]
        return list(c.get("measuredFields") or []), c.get("objectTemp")


def test_KRITIK_A47_tekil_surus_sirasinda_49_63_120C_STOP_YOK_ve_sicakken_START_KABUL(o):
    api = o.api
    r = o.c.post("/api/coil/6/control", json={"start": True, "freq": 100, "duty": 40, "phase": 0, "duration": 60})
    assert r.status_code == 200, r.text[:300]
    once = len(o.hc.core._hw_send_queue.paketler)
    for t in (49.0, 63.0, 120.0):
        o.satir(f"-> STM_TELE: C=6,T={t:.2f},A=27.10,B=1.842,N=412,GS=0,RS=0")
        o.satir(f"-> STM_TELE: C=7,T={t:.2f},A=27.10")
        o.saat.ek += 1.0
        _tur(api)
    mf6, t6 = _mf(api, 6)
    assert "objectTemp" in mf6 and t6 == 120.0, (mf6, t6)  # ARA DOĞRULAMA: 120 °C gerçekten ÖLÇÜLDÜ
    assert _paketler(o, once) == [], f"sıcak telemetri donanıma paket gönderdi (termal STOP?): {_paketler(o, once)}"
    assert o.hc.stop_all_cagri == 0 and o.acil == [], f"sıcak telemetri durdurma tetikledi: {o.acil}"
    assert 6 in _calisan(o), "sıcak telemetriyle bobin 6 durdu (A-47: termal kesme yok)"
    # Bobin 7 120 °C ÖLÇÜLÜYKEN START kabul edilir ve tele gider.
    once2 = len(o.hc.core._hw_send_queue.paketler)
    r7 = o.c.post("/api/coil/7/control", json={"start": True, "freq": 100, "duty": 30, "phase": 0, "duration": 60})
    assert r7.status_code == 200 and any(p[6] > 0 for p in _paketler(o, once2)), (r7.status_code, r7.text[:200])


def test_KRITIK_A47_SEANS_sicakken_baslar_ve_sicaklik_artinca_DURMAZ(o):
    api = o.api
    for cid in (6, 7):
        o.satir(f"-> STM_TELE: C={cid},T=63.00,A=27.10,B=1.842,N=412,GS=0,RS=0")
    once = len(o.hc.core._hw_send_queue.paketler)
    r = o.c.post(
        "/api/session/start",
        json={"coil_ids": [6, 7], "frequency": 100, "duty": 40, "phase": 0, "duration_minutes": 5, "mode": "Manuel"},
    )
    assert r.status_code == 200, r.text[:300]
    assert any(p[5] > 0 and p[6] > 0 for p in _paketler(o, once)), "63 °C ölçülüyken seans tele gitmedi"
    once2 = len(o.hc.core._hw_send_queue.paketler)
    for k in range(6):
        o.saat.ek += 1.0
        for cid in (6, 7):
            o.satir(f"-> STM_TELE: C={cid},T={70.0 + k:.2f},A=27.10,B=1.842,N=412,GS=0,RS=0")
        _tur(api)
    with api._session_lock:
        aktif = bool(api._active_session.get("is_active"))
    assert aktif and o.acil == [] and _paketler(o, once2) == [], (aktif, o.acil, _paketler(o, once2))
    assert _calisan(o) == [6, 7], _calisan(o)
