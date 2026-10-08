# -*- coding: utf-8 -*-
"""D2.E06 (YA-2) · SAHİP KARARI Y90 — AI Pro'nun devraldığı MANUEL seans geçmişte `interrupted` ("Kesintiye Uğradı") yazılır.

ÖLÇÜLEN (ADAY-DOĞRULAMA-D2 YA-2, İG-5.13 yan gözlemi): manuel seans sürerken AI Pro başlatılınca `start_ai_session` eski
manuel seansı `_finalize_session_db(reason="ai-devralma")` ile kapatıyor; bu sebep `completed`a düşüyordu → planlanan süresi
dolmadan devralınan tedavi "Tamamlandı" görünüyordu. D1.75 ile aynı ilke (seans ortasında kapanış = Kesintiye Uğradı).
Kapı GERÇEK uçlarla (`/api/session/start` → onaylı `/api/ai/pro/start`); satır SQL ile okunur.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def o(monkeypatch, tmp_path):
    import ai_pro_aparati as ap
    from kayitci_donanim import gercek_hc

    o = ap.kur(monkeypatch, tmp_path)
    try:
        with gercek_hc() as hc:
            monkeypatch.setattr(o.api.state, "hardware", hc)
            o.hc = hc
            yield o
            o.c.post("/api/ai/pro/stop")
            o.c.post("/api/session/stop")
    finally:
        o.air._ai_loop_active = False
        o.geri()


def _manuel_baslat(o) -> int:
    r = o.c.post(
        "/api/session/start",
        json={
            "coil_ids": [1],
            "frequency": 100,
            "duty": 40,
            "phase": 0,
            "duration_minutes": 5,
            "mode": "Manuel",
            "patient_name": "Boncuk",
        },
    )
    assert r.status_code == 200, r.text[:300]
    with o.api._session_lock:
        return o.api._active_session.get("db_session_id")


def _durum(o, sid):
    with o.db._get_connection() as c:
        return tuple(
            c.execute("SELECT session_status, end_time FROM treatment_sessions WHERE id = ?", (sid,)).fetchone()
        )


def test_KRITIK_Y90_AI_Pro_devraldigi_manuel_seans_KESINTIYE_UGRADI(o):
    import ai_pro_aparati as ap

    manuel = _manuel_baslat(o)
    _pid, r = ap.onayli_baslat(o, organ=2)
    assert r.status_code == 200, r.text[:300]
    with o.api._session_lock:
        assert o.api._active_session.get("db_session_id") != manuel, "ön koşul: AI Pro yeni satır açmalı"
    durum, bitis = _durum(o, manuel)
    assert (durum, bool(bitis)) == ("interrupted", True), (
        f"devralınan manuel seans '{durum}' yazıldı (Y90: interrupted)"
    )


def test_KARSIT_Y90_manuel_seans_operatorce_durdurulunca_TAMAMLANDI_kalir(o):
    manuel = _manuel_baslat(o)
    assert o.c.post("/api/session/stop").status_code == 200
    assert _durum(o, manuel)[0] == "completed"
