# -*- coding: utf-8 -*-
"""C2-2.3 (2-C inceleme A2) — KÖR KAPI: D2.40'ın −7200 kolu SÜREN (yaşı > 0) seansta geri saat adımını ölçmez.

`test_sure_hesaplari_MONOTONIK_…_D240::test_KRITIK_a_saat_ADIMINDA…[-7200]` seansı TAM o an başlatıp `0 <= elapsed <= 5` ister:
gerçek geçen süre ≈ 0 olduğu için duvar-saati yedeği (`max(0, time.time() - start_time)` → 0'da kırpılı) ile monotonik hesap AYIRT
EDİLEMEZ. 2-C raporu bunu "−7200 kolu yeşil (duvar-saati yedeği 0'da kırpılı)" diye not etti (§3.27 m1). Gizlenen yanlış: geri
saat adımından sonra SÜREN seansın geçen süresi 0'da DONAR, kalan süre TAM görünür (bekçi monotonik — seans yine zamanında biter;
arayüz yanlış kalan süre gösterir). Bu kapı seansı 120 sn önce başlamış kurar (iki saatte de), sonra saati geri alır.
ÖNCE-KIRMIZI (mutant tabanlı — ürün bugün doğru, kapı körlüğü maddesi; O-A2-7.a deseni): 2-C'nin m1'i (duvar saatine dönüş)
D2.40'ın −7200 kolunda YEŞİL, bu kapıda KIRMIZI. GERÇEK: `GET /api/session/active` (TestClient), oturum sözlüğü ürünün alanlarıyla.
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

_GERCEK_SAAT = time.time
_GERCEK_MONO = time.monotonic
YAS_S = 120


@pytest.fixture
def o(monkeypatch):
    from servers import api_server as api

    with api._session_lock:
        eski = dict(api._active_session)
        api._active_session.clear()
        api._active_session.update(
            {
                "is_active": True,
                "session_id": "c223",
                "db_session_id": None,
                "mode": "Manuel",
                "duration_minutes": 5,
                "start_time": _GERCEK_SAAT() - YAS_S,
                "started_epoch": _GERCEK_SAAT() - YAS_S,
                "start_mono": _GERCEK_MONO() - YAS_S,
                "coil_ids": [1],
            }
        )
    try:
        yield type("O", (), {"c": TestClient(api.app, client=("127.0.0.1", 51235))})
    finally:
        with api._session_lock:
            api._active_session.clear()
            api._active_session.update(eski)


@pytest.mark.parametrize("adim_s", [-7200, -30])
def test_KRITIK_geri_saat_adiminda_SUREN_seansin_gecen_suresi_DONMAZ_kalan_sure_DOGRU(o, monkeypatch, adim_s):
    monkeypatch.setattr(time, "time", lambda: _GERCEK_SAAT() + adim_s)
    j = o.c.get("/api/session/active").json()
    assert j.get("is_active") is True, j
    assert YAS_S - 2 <= j.get("elapsed_sec", -1) <= YAS_S + 5, (
        f"saat {adim_s:+} sn geri alınınca süren seansın geçen süresi {j.get('elapsed_sec')} (gerçek ≈ {YAS_S})"
    )
    assert 300 - YAS_S - 5 <= j.get("remaining_sec", 0) <= 300 - YAS_S + 2, j.get("remaining_sec")


def test_KARSIT_saat_SABITken_suren_seansin_gecen_suresi_yasina_esit(o):
    j = o.c.get("/api/session/active").json()
    assert j.get("is_active") is True and YAS_S - 2 <= j.get("elapsed_sec") <= YAS_S + 5, j
