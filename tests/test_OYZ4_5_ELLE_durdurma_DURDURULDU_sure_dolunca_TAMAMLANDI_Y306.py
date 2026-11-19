# -*- coding: utf-8 -*-
"""Y306 (sahip 19-11): ELLE durdurulan seans geçmişte "Tamamlandı" görünüyordu (19-11 18:07 seansı, canlı seans kartının "Durdur"u).
Kök: genel durdurma ucu `/api/session/stop` satırı `"cancelled" if uçuştaki başlatma else "completed"` kapatıyordu; yalnız AI Pro
panelinin "AI Pro'yu Durdur"u `stopped` yazıyordu (ODD B-4).
KURAL (D1.75 / Y90 ilkesi): operatör seansı planlanan süre DOLMADAN durdurursa HER kipte (Manuel / Otomatik / AI Pro, hangi düğmeden
olursa) `stopped` = "Durduruldu"; süre bekçisi bitirirse ya da süre dolduysa `completed`. Ölçüt bekçiyle TEK (`_planlanan_sure_doldu`;
D1.70 kalan süre `bitis_mono` dahil); bekçi saniyede bir baktığı için durdurmada 1 sn pay. Raporlar / PDF / CSV `stopped`u zaten
"Durduruldu" / "Dur./Hata" sayar.
Kapı GERÇEK uçlarla (`/api/session/start` → `/api/session/stop`, onaylı `/api/ai/pro/start`); satır SQL ile okunur (Y90 düzeneği)."""

from __future__ import annotations

import time

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


def _manuel_baslat(o, dk: int = 5) -> int:
    r = o.c.post(
        "/api/session/start",
        json={
            "coil_ids": [1],
            "frequency": 100,
            "duty": 40,
            "phase": 0,
            "duration_minutes": dk,
            "mode": "Manuel",
            "patient_name": "Boncuk",
        },
    )
    assert r.status_code == 200, r.text[:300]
    with o.api._session_lock:
        return o.api._active_session.get("db_session_id")


def _durum(o, sid):
    with o.db._get_connection() as c:
        return c.execute("SELECT session_status FROM treatment_sessions WHERE id = ?", (sid,)).fetchone()[0]


def test_KRITIK_manuel_seans_SURE_DOLMADAN_elle_durdurulunca_DURDURULDU(o):
    sid = _manuel_baslat(o)
    assert o.c.post("/api/session/stop").status_code == 200
    assert _durum(o, sid) == "stopped"


def test_KRITIK_AI_Pro_seansi_CANLI_KARTIN_Durdur_u_ile_DURDURULDU(o):
    import ai_pro_aparati as ap

    _pid, r = ap.onayli_baslat(o, organ=2)
    assert r.status_code == 200, r.text[:300]
    with o.api._session_lock:
        sid = o.api._active_session.get("db_session_id")
    assert sid, "ön koşul: AI Pro seans satırı açmalı"
    assert o.c.post("/api/session/stop").status_code == 200  # canlı kartın Durdur'u = genel durdurma ucu
    assert _durum(o, sid) == "stopped"


def test_KARSIT_planlanan_SURE_DOLDUYSA_durdurma_TAMAMLANDI_bekcinin_1_sn_payi(o):
    """Bekçi henüz tiklemeden (süreye 0,8 sn kala, pay 1 sn) basılan Durdur süreyi tamamlamış sayılır."""
    sid = _manuel_baslat(o, dk=1)
    with o.api._session_lock:
        o.api._active_session["start_mono"] = time.monotonic() - 60 + 0.8
    assert o.c.post("/api/session/stop").status_code == 200
    assert _durum(o, sid) == "completed"


def test_KRITIK_D170_KALAN_sure_bitis_mono_ESAS_alinir(o):
    """Seans ortasında girilen süre (D1.70 · Y5) kesin bitişi yazar: planlanan toplam geçmiş olsa da bitişe 1 dk varken Durdur = stopped."""
    sid = _manuel_baslat(o, dk=1)
    with o.api._session_lock:
        o.api._active_session["start_mono"] = time.monotonic() - 3600  # toplam 1 dk çoktan geçti
        o.api._active_session["bitis_mono"] = time.monotonic() + 60  # ama kalan süre 1 dk
    assert o.c.post("/api/session/stop").status_code == 200
    assert _durum(o, sid) == "stopped"


def test_planlanan_sure_doldu_OLCUTU_bekciyle_TEK():
    from servers import api_server as api

    m = time.monotonic()
    assert api._planlanan_sure_doldu({"duration_minutes": 1, "start_mono": m - 61}) is True
    assert api._planlanan_sure_doldu({"duration_minutes": 1, "start_mono": m - 30}) is False
    assert api._planlanan_sure_doldu({"duration_minutes": 1, "start_mono": m - 59.5}, api.SURE_DOLDU_PAYI_SN) is True
    assert api._planlanan_sure_doldu({"duration_minutes": 1, "start_mono": m - 55}, api.SURE_DOLDU_PAYI_SN) is False
    assert api._planlanan_sure_doldu({"duration_minutes": 0, "start_mono": m - 99999}) is False  # planlanan süre yok
    assert api._planlanan_sure_doldu({"duration_minutes": None, "start_mono": m - 99999}) is False
    assert api._planlanan_sure_doldu({"duration_minutes": 1, "start_mono": m - 3600, "bitis_mono": m + 30}) is False
    assert api._planlanan_sure_doldu({"duration_minutes": 9, "start_mono": m, "bitis_mono": m - 1}) is True
    # kesin bitişe yarım saniye varken: bekçi için dolmadı, durdurma (1 sn pay) için doldu
    assert (
        api._planlanan_sure_doldu({"duration_minutes": 9, "start_mono": m, "bitis_mono": time.monotonic() + 0.5})
        is False
    )
    assert (
        api._planlanan_sure_doldu({"duration_minutes": 9, "bitis_mono": time.monotonic() + 0.5}, api.SURE_DOLDU_PAYI_SN)
        is True
    )
    # monotonik saat yoksa duvar saati
    assert api._planlanan_sure_doldu({"duration_minutes": 1, "start_time": time.time() - 120}) is True
    assert api.SURE_DOLDU_PAYI_SN == 1.0


def test_rapor_PDF_CSV_durum_metni_DURDURULDU():
    from utils import ceviri, seans_durum

    jeton = ceviri.istek_dili_var.set("tr")
    try:
        assert seans_durum.durum_etiketi("stopped") == "Durduruldu"
    finally:
        ceviri.istek_dili_var.reset(jeton)
