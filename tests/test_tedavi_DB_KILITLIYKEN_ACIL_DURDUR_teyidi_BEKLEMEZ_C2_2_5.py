# -*- coding: utf-8 -*-
"""C2-2.5 (2-C inceleme A2 · Ö.4-Y8) — tedavi DB'si YAZMA KİLİDİNDEYKEN (aktif seans) ACİL DURDUR'un yanıtı ve teyidi
(`estop_teyit` yayını) KAYIT KAPANIŞINI beklemez.

ÖLÇÜLEN (HEAD 1cd770c, `_inceleme/kayit/sonda_k4*.txt`, paylaşılan TEK olay döngüsü): ikinci bağlantı tedavi DB'sinde
`BEGIN EXCLUSIVE` + yazma tutarken (WAL; yedekleme/ikinci süreç/uzun bakım işlemi) aktif elle seansta ACİL DURDUR → STM STOP paketi
donanım kuyruğuna 0,000 sn'de GİDİYOR, ama HTTP yanıtı **21,7 sn** (seans STOP'u 16,2 sn) bekliyor: `_emergency_stop_all`
`record_session_event` + `_finalize_session_db` + açık koşuları (her biri `busy_timeout` 5 sn) yanıttan ve teyit yayınından
ÖNCE senkron yazıyor. Arayüz dizisinde (`emergencyStop.ts`: köprü 5 sn → yedek istek → /session/stop) operatör teyidi ~10,5 sn
sonra görüyor (WS `estop_teyit` ilk kez 10,45 sn'de). Gözlem notu istekleri (D2.15) SÜREYİ DEĞİŞTİRMİYOR (yüklü = yüksüz).
Ö.4-Y8: kayıt yazımı ACİL DURDUR'u geciktiremez (2-C E07 ilkesi: kapanış STOP'TAN SONRA ve onu beklemeden).
GERÇEK: uçlar (TestClient + `start_blocking_portal` paylaşılan döngü), `HardwareController` (`gercek_hc`), tedavi DB'si + kilit.
"""

from __future__ import annotations

import sqlite3
import time

import pytest
from fastapi.testclient import TestClient

LAN = ("192.168.1.85", 52135)
SINIR_SN = 3.0


@pytest.fixture
def o(monkeypatch, tmp_path):
    import ai_pro_aparati as apa
    from kayitci_donanim import gercek_hc
    from servers import live_state

    o = apa.kur(monkeypatch, tmp_path)
    o.secenek = dict(apa.ISTEMCI_SECENEKLERI)
    o.teyit: list = []
    o.t0 = [time.monotonic()]

    def _ws(m):
        if isinstance(m, dict) and m.get("type") == "estop_teyit":
            o.teyit.append(time.monotonic() - o.t0[0])

    monkeypatch.setattr(live_state, "_ws_broadcast_sync", _ws)
    try:
        with gercek_hc() as hc:
            monkeypatch.setattr(o.api.state, "hardware", hc)
            o.hc = hc
            yield o
            o.c.post("/api/session/stop")
    finally:
        o.air._ai_loop_active = False
        o.geri()


def _aktif_seans(o):
    r = o.c.post(
        "/api/session/start",
        json={
            "coil_ids": [1, 2],
            "frequency": 100,
            "duty": 40,
            "phase": 0,
            "intensity": 0,
            "duration_minutes": 5,
            "mode": "Manuel",
            "patient_name": "Pamuk",
        },
    )
    assert r.status_code == 200, r.text[:300]
    with o.api._session_lock:
        return o.api._active_session.get("db_session_id")


def _estop_paylasilan(o):
    from anyio.from_thread import start_blocking_portal

    with start_blocking_portal(backend="asyncio", backend_options=o.secenek) as portal:
        c = TestClient(o.api.app, client=LAN)
        c.portal = portal
        once = o.hc.stop_all_cagri
        o.t0[0] = time.monotonic()
        r = c.post("/api/hardware/emergency_stop")
        sn = time.monotonic() - o.t0[0]
    return r, sn, o.hc.stop_all_cagri - once


def test_KRITIK_tedavi_DB_KILITLIYKEN_ACIL_DURDUR_yaniti_ve_TEYIDI_BEKLEMEZ(o):
    _aktif_seans(o)
    kc = sqlite3.connect(str(o.db.db_path), isolation_level=None, timeout=1)
    kc.execute("BEGIN EXCLUSIVE")
    kc.execute("UPDATE treatment_sessions SET updated_at = updated_at")
    try:
        r, sn, stop_all = _estop_paylasilan(o)
    finally:
        kc.execute("ROLLBACK")
        kc.close()
    assert stop_all >= 1, "ön koşul: donanım STOP'u verildi"
    ilk_teyit = o.teyit[0] if o.teyit else None
    print(f"\nC2-2.5: ACİL DURDUR yanıtı {sn:.2f} sn · ilk estop_teyit {ilk_teyit}")
    assert r.status_code == 200 and r.json().get("confirmed") is True, r.text[:200]
    assert ilk_teyit is not None and ilk_teyit < SINIR_SN, (
        f"teyit yayını {ilk_teyit} sn sonra (kayıt kapanışını bekledi)"
    )
    assert sn < SINIR_SN, f"tedavi DB kilitliyken ACİL DURDUR yanıtı {sn:.1f} sn bekledi (kayıt kapanışı yanıttan önce)"


def test_KARSIT_kilit_YOKKEN_seans_ACIL_DURDURMA_muhruyle_kapanir(o):
    sid = _aktif_seans(o)
    r, sn, _ = _estop_paylasilan(o)
    assert r.status_code == 200 and sn < SINIR_SN, (r.status_code, sn)
    son = time.monotonic() + 10
    durum = None
    while time.monotonic() < son:
        with o.db._get_connection() as c:
            durum = c.execute("SELECT session_status FROM treatment_sessions WHERE id = ?", (sid,)).fetchone()[0]
        if durum == "EMERGENCY_STOPPED":
            break
        time.sleep(0.05)
    assert durum == "EMERGENCY_STOPPED", durum
