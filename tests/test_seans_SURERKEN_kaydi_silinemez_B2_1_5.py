# -*- coding: utf-8 -*-
"""B2-1.5 (2-B incelemesi · A1) — SÜREN (aktif) seansın tedavi kaydı silinemez; silinmeye çalışılması ACİL DURDUR kaydını
ve doz kaydını yok etmez.

ÖLÇÜLEN KUSUR: tekil (`DELETE /api/history/{id}`, `POST /api/history/delete`) ve toplu (`/api/history/delete_bulk`) silme uçları
seansın o an SÜRDÜĞÜNE bakmıyor. Aktif seansın satırı silinince (ölçüldü, Kural 2 jetonsuz LAN ve kendi jetonuyla aynı): tedavi
donanımda sürer, sonraki bobin koşusu (doz) satırı EBEVEYNSİZ yazılır (session_coil_runs FK'sız), ACİL DURDUR donanımı durdurur
ama `emergency_stop` olayı YAZILAMAZ (session_events FK → `record_session_event` None) — o tedavinin ne kaydı ne acil durdurma
izi kalır; D2.17 silme izi `acil_durdurma: 0` der. Kontrol (silmeden): aynı ACİL DURDUR olayı yazılır.
Kural: süren seansın kaydı silinmez → 409 "Seans sürüyor", hiçbir satır silinmez (toplu: atomik), red izde; ACİL DURDUR'a
dokunulmaz (Ö.4-Y8: kapı `_session_lock` ALMAZ). Biten seans bugünkü gibi silinir.
Önerilen yer: tests/test_seans_SURERKEN_kaydi_silinemez_B2_1_5.py
"""

from __future__ import annotations

import copy
import time

import pytest
from fastapi.testclient import TestClient

AYSE = "dr.ayse@klinik.com"


class _KaydediciDonanim:
    def __init__(self):
        self.stop_all = 0

    def on_disconnect(self):
        return True

    def stop_all_coils(self):
        self.stop_all += 1
        return True


@pytest.fixture
def ortam(tmp_path, monkeypatch):
    from database.treatment_history_db import TreatmentHistoryDB
    from servers import api_server as api
    from servers import live_state as ls
    from servers import operator_tokens
    from servers.history_router import get_db

    db = TreatmentHistoryDB(tmp_path)
    hw = _KaydediciDonanim()
    monkeypatch.setattr(api, "_get_treatment_db", lambda: db)
    monkeypatch.setattr(api.state, "hardware", hw)
    monkeypatch.setattr(api, "_ws_broadcast_sync", lambda *a, **k: None)
    monkeypatch.setattr(api, "_push_notification", lambda m, t="info": None)
    api.app.dependency_overrides[get_db] = lambda: db
    yerel = TestClient(api.app, client=("127.0.0.1", 51434))
    lan = TestClient(api.app, client=("192.168.1.70", 51435))

    def _sil():
        for op in yerel.get("/api/operators").json().get("data", []):
            yerel.post("/api/operators/remove", json={"email": op["email"]})

    operator_tokens.temizle_hepsi()
    _sil()
    with api._session_lock:
        eski_seans = dict(api._active_session)
    with ls._live_state_lock:
        eski_canli = copy.deepcopy(ls._live_state)
    try:
        yield type("O", (), {"api": api, "db": db, "hw": hw, "yerel": yerel, "lan": lan})
    finally:
        api.app.dependency_overrides.pop(get_db, None)
        with api._session_lock:
            api._active_session.clear()
            api._active_session.update(eski_seans)
        with ls._live_state_lock:
            ls._live_state.clear()
            ls._live_state.update(eski_canli)
        operator_tokens.temizle_hepsi()
        _sil()
        db.close_connections()


def _aktif_seans(o, sahip):
    sid = int(
        o.db.start_session(treatment_mode="Manuel", target_condition="t", patient_name="Pamuk", operator_email=sahip)
    )
    with o.api._session_lock:
        o.api._active_session.clear()
        o.api._active_session.update(
            {
                "is_active": True,
                "session_id": "b215",
                "coil_ids": [1, 2],
                "db_session_id": sid,
                "started_epoch": time.time() - 60,
                "start_mono": time.monotonic() - 60,
            }
        )
    o.db.start_coil_run(sid, 1, frequency_hz=10, duty_percent=20, intensity_mt=2.0, started_epoch=time.time() - 50)
    return sid


def _say(o, sid):
    with o.db._get_connection() as c:
        return (
            c.execute("SELECT COUNT(*) FROM treatment_sessions WHERE id=?", (sid,)).fetchone()[0],
            c.execute(
                "SELECT COUNT(*) FROM session_events WHERE session_id=? AND event_type='emergency_stop'", (sid,)
            ).fetchone()[0],
        )


def _sil_istegi(o, uc, sid, jeton=""):
    h = {"X-PEMF-Operator": jeton} if jeton else {}
    if uc == "tekil_DELETE":
        return o.lan.delete(f"/api/history/{sid}", headers=h)
    if uc == "tekil_POST":
        return o.lan.post("/api/history/delete", json={"session_id": sid}, headers=h)
    return o.lan.post("/api/history/delete_bulk", json={"session_ids": [sid], "confirm": "DELETE_SELECTED"}, headers=h)


UCLAR = pytest.mark.parametrize("uc", ["tekil_DELETE", "tekil_POST", "toplu"])


@UCLAR
def test_KRITIK_SUREN_seansin_kaydi_silinmez_ve_ACIL_DURDUR_kaydi_yazilir_KURAL2(ortam, uc):
    o = ortam
    sid = _aktif_seans(o, "tek@klinik.com")
    r = _sil_istegi(o, uc, sid)
    o.api._emergency_stop_all("manual")
    assert o.hw.stop_all == 1, "ACİL DURDUR donanıma gitmedi"
    assert _say(o, sid) == (1, 1), (
        f"süren seansın kaydı silindi ({r.status_code} {r.text[:80]}) → ACİL DURDUR olayı yazılamadı: (seans, estop)={_say(o, sid)}"
    )
    assert r.status_code == 409 and "sürüyor" in r.json().get("detail", ""), r.text[:200]


@UCLAR
def test_KRITIK_kendi_jetonuyla_da_SUREN_seans_silinmez(ortam, uc):
    o = ortam
    assert (
        o.yerel.post("/api/operators/enroll", json={"email": AYSE, "display_name": "A", "pin": "123456"}).status_code
        == 200
    )
    j = o.yerel.post("/api/operators/verify", json={"email": AYSE, "pin": "123456"}).json()["operator_token"]
    sid = _aktif_seans(o, AYSE)
    r = _sil_istegi(o, uc, sid, j)
    assert (r.status_code, _say(o, sid)[0]) == (409, 1), (r.status_code, r.text[:150])


@UCLAR
def test_KARSIT_BITEN_seans_bugunku_gibi_silinir(ortam, uc):
    o = ortam
    sid = _aktif_seans(o, "tek@klinik.com")
    with o.api._session_lock:
        o.api._active_session["is_active"] = False
    r = _sil_istegi(o, uc, sid)
    assert r.status_code == 200 and _say(o, sid)[0] == 0, r.text[:200]
