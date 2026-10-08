# -*- coding: utf-8 -*-
"""D2.40 (B-1.30 · B-1.31 · B-1.32) — süre hesapları duvar saatinden BAĞIMSIZ (monotonik); aynı saniyedeki iki parametre
değişikliği birbirini EZMEZ; doz kaydı yazılamazsa `kayda_yazildi` False döner.

ÖLÇÜLEN (DENETIM-01 tv-F3_1, tv-F3_2, v-A11):
  (a) `GET /api/session/active` geçen süreyi `time.time() - start_time` ile hesaplıyordu → saat +1 sa atlayınca seans
      (backend aktifken) arayüzde KAPALI, −2 sa atlayınca geçen süre NEGATİF görünüyordu.
  (b) bobin koşusu `duration_seconds` duvar saati farkıydı → koşu sırasında saat −2 sa düzeltilince doz kaydına −7170 sn.
  (c) parametre değişikliği anahtarı `ad@<tamsayı saniye>` → aynı saniyedeki 150 → 200 Hz değişikliğinin İLKİ eziliyordu;
      `set_session_parameter` hatayı yuttuğu için DB yazılamadığında da `kayda_yazildi: True` dönüyordu.
GERÇEK: uçlar (TestClient), `coil_run_tracker`, `TreatmentHistoryDB` (geçici). Saat adımı `time.time` yamasıyla — monotonik
saat gerçek (b'de koşunun süresi monotonik saatin ileri alınmasıyla verilir). Satırlar SQL ile.
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

_GERCEK_SAAT = time.time
_GERCEK_MONO = time.monotonic


@pytest.fixture
def o(tmp_path, monkeypatch):
    from database.treatment_history_db import TreatmentHistoryDB
    from servers import api_server as api

    db = TreatmentHistoryDB(tmp_path / "gecmis")
    monkeypatch.setattr(api, "_get_treatment_db", lambda: db)
    sid = db.start_session(treatment_mode="Manuel", target_condition=None, patient_name="Boncuk")
    with api._active_coil_runs_lock:
        api._active_coil_runs.clear()
    with api._coil_run_stats_lock:
        api._coil_run_stats.clear()
    with api._session_lock:
        eski = dict(api._active_session)
        api._active_session.clear()
        api._active_session.update(
            {
                "is_active": True,
                "session_id": "d240",
                "db_session_id": sid,
                "mode": "Manuel",
                "duration_minutes": 5,
                "start_time": _GERCEK_SAAT(),
                "started_epoch": _GERCEK_SAAT(),
                "start_mono": _GERCEK_MONO(),
                "coil_ids": [1],
            }
        )
    try:
        yield type("O", (), {"api": api, "db": db, "sid": sid, "c": TestClient(api.app, client=("127.0.0.1", 51234))})
    finally:
        with api._active_coil_runs_lock:
            api._active_coil_runs.clear()
        with api._coil_run_stats_lock:
            api._coil_run_stats.clear()
        with api._session_lock:
            api._active_session.clear()
            api._active_session.update(eski)
        db.close_connections()


@pytest.mark.parametrize("adim_s", [3600, -7200])
def test_KRITIK_a_saat_ADIMINDA_aktif_seans_ACIK_ve_gecen_sure_DOGRU(o, monkeypatch, adim_s):
    monkeypatch.setattr(time, "time", lambda: _GERCEK_SAAT() + adim_s)
    j = o.c.get("/api/session/active").json()
    assert j.get("is_active") is True, f"saat {adim_s:+} sn atlayınca seans kapalı göründü: {j}"
    assert 0 <= j.get("elapsed_sec", -1) <= 5, f"geçen süre duvar saatini izledi: {j.get('elapsed_sec')}"
    assert 290 <= j.get("remaining_sec", 0) <= 300, j.get("remaining_sec")


def test_KARSIT_a_saat_SABITken_gecen_ve_kalan_sure_degismez(o):
    j = o.c.get("/api/session/active").json()
    assert j.get("is_active") is True and 0 <= j.get("elapsed_sec") <= 5 and 290 <= j.get("remaining_sec") <= 300, j


def _kosu(o):
    with o.db._get_connection() as c:
        return tuple(c.execute("SELECT duration_seconds, started_epoch, ended_epoch FROM session_coil_runs").fetchone())


def test_KRITIK_b_kosu_sirasinda_saat_GERI_alininca_kosu_suresi_MONOTONIK(o, monkeypatch):
    o.api._begin_coil_run(1, 100.0, 40.0, 0.0, 1.0, "stm")
    monkeypatch.setattr(time, "monotonic", lambda: _GERCEK_MONO() + 30.0)  # koşu 30 sn sürdü
    monkeypatch.setattr(time, "time", lambda: _GERCEK_SAAT() - 7200 + 30.0)  # bu arada saat 2 sa GERİ düzeltildi
    o.api._finish_coil_run(1)
    sure, basla, bitis = _kosu(o)
    assert sure == pytest.approx(30.0, abs=1.0), f"koşu süresi duvar saatini izledi: {sure} sn"
    assert bitis - basla == pytest.approx(sure, abs=0.01), "bitiş damgası süreyle tutarsız"


def test_KARSIT_b_saat_SABITken_kosu_suresi_gercek_sure(o, monkeypatch):
    o.api._begin_coil_run(1, 100.0, 40.0, 0.0, 1.0, "stm")
    monkeypatch.setattr(time, "monotonic", lambda: _GERCEK_MONO() + 12.0)
    monkeypatch.setattr(time, "time", lambda: _GERCEK_SAAT() + 12.0)
    o.api._finish_coil_run(1)
    assert _kosu(o)[0] == pytest.approx(12.0, abs=1.0)


def _degisiklikler(o, on_ek="degisiklik_frekans_hz@"):
    with o.db._get_connection() as c:
        satirlar = c.execute(
            "SELECT parameter_name, parameter_value FROM session_parameters WHERE session_id = ? ORDER BY id", (o.sid,)
        ).fetchall()
    return [float(v) for k, v in satirlar if k.startswith(on_ek)]


def test_KRITIK_c_AYNI_saniyedeki_iki_frekans_degisikligi_IKI_satir(o, monkeypatch):
    sabit = _GERCEK_SAAT()
    monkeypatch.setattr(time, "time", lambda: sabit)  # ikisi de AYNI tamsayı saniyede
    for f in (150, 200):
        r = o.c.post("/api/session/parametre_guncelle", json={"frequency": f})
        assert r.status_code == 200 and r.json().get("kayda_yazildi") is True, r.text[:200]
    assert _degisiklikler(o) == [150.0, 200.0], f"aynı saniyedeki değişiklik ezildi: {_degisiklikler(o)}"


def test_KRITIK_c_doz_kaydi_YAZILAMAZSA_kayda_yazildi_FALSE(o, monkeypatch):
    def _disk_dolu(self):
        raise RuntimeError("Disk free space critical (test)")

    monkeypatch.setattr(type(o.db), "_ensure_write_guardrail", _disk_dolu)
    r = o.c.post("/api/session/parametre_guncelle", json={"frequency": 150})
    assert r.status_code == 200, r.text[:200]
    assert r.json().get("kayda_yazildi") is False, f"yazılamayan değişiklik 'kayda yazıldı' dendi: {r.json()}"


def test_KARSIT_c_tek_degisiklik_YAZILIR_ve_kart_tazelenir(o):
    r = o.c.post("/api/session/parametre_guncelle", json={"frequency": 175})
    assert r.status_code == 200 and r.json().get("kayda_yazildi") is True and r.json().get("frequencyHz") == 175.0
    assert _degisiklikler(o) == [175.0]
