# Author: mertaygn, cglrgrkn
"""Faz-1 (B-2.2 session-state ayrımı — refactor-ÖNCESİ DAVRANIŞ KİLİDİ).

`_active_session` + `start_session` / `stop_session` / `start_ai_session` — seansın in-memory
yaşam-döngüsü. B-2.2 son kademesinde `_active_session` `servers/session_state.py`'ye taşınacak;
bunun ÖN KOŞULU `start_session`/`start_ai_session`'daki REBIND'i (`_active_session = {...}`) in-place
mutasyona (`.clear()+.update()`) normalize etmek (aksi halde alias kopar). Bu testler MEVCUT gözlenen
davranışı kilitler → normalizasyon + taşıma sonrası AYNI testler yeşil kalmalı = davranış birebir.

ESP-only bobinler (6-8) → STM donanımı gerekmez; MQTT/DB/broker mock'lanır. `asyncio.run` ile
doğrudan çağrı (TestClient YOK → watchdog thread'i kurulan seansı bozmaz, deterministik)."""

import asyncio
import os

os.environ.pop("PEMF_SIMULATE", None)
import pytest


class _SahteIstek:
    """`start_session` 2026-08-09'da `request` almaya başladı: kaydın SAHİBİNİ artık sunucu
    belirliyor (bkz. servers.auth.cozumlenmis_operator) — `operator_email` istemci beyanı
    olmaktan çıktı. Bu dosya HTTP katmanını atlayıp fonksiyonu doğrudan çağırdığı için asgari
    bir istek nesnesi gerekiyor. Jeton yok → beyan yolu (cihazda kayıtlı operatör olmadığından
    beyan kabul edilir; kimlik kapısı tests/test_operator_identity_server_side.py'de test edilir).
    """

    headers: dict = {}
    query_params: dict = {}


@pytest.fixture()
def api(monkeypatch):
    """İzole api_server: MQTT/DB/broker mock + tüm seans state'i temiz."""
    from servers import api_server

    monkeypatch.setattr(api_server, "_mqtt_publish", lambda *a, **k: True)
    monkeypatch.setattr(api_server, "_get_treatment_db", lambda: None)  # DB best-effort → atla
    # ⚠️ 2026-08-09: `_get_treatment_db → None` artık "DB hazır değil" demek ve seans 503 ile
    # reddediliyor (kayıtsız tedavi kapısı). Bu dosyanın konusu BELLEK-İÇİ yaşam döngüsü, DB
    # değil → kapıyı da devre dışı bırak. Kapının KENDİSİ `test_db_ready_gate.py`'de test edilir.
    monkeypatch.setattr(api_server, "_kayit_db_hazir", lambda: (True, ""))
    monkeypatch.setattr(api_server, "_broker_reachable", lambda: True)
    with api_server._session_lock:
        api_server._active_session.clear()
    with api_server._active_coil_runs_lock:
        api_server._active_coil_runs.clear()
    with api_server._coil_run_stats_lock:
        api_server._coil_run_stats.clear()
    with api_server._sensor_sample_buffer_lock:
        api_server._sensor_sample_buffer.clear()
    return api_server


def _payload(api, **kw):
    base = dict(
        coil_ids=[6, 7, 8],
        mode="Manuel",
        operator_name="op",
        frequency=50,
        duty=25,
        intensity=2.0,
        phase=0,
        duration_minutes=20,
    )
    base.update(kw)
    return api.SessionStartPayload(**base)


# ── start_session: _active_session doğru doldurulur ──────────────────────────
def test_start_session_populates_active_session(api):
    resp = asyncio.run(api.start_session(_payload(api), _SahteIstek()))
    assert resp["status"] == "success"
    with api._session_lock:
        s = dict(api._active_session)
    assert s["is_active"] is True
    assert s["coil_ids"] == [6, 7, 8]
    assert s["mode"] == "Manuel"
    assert s["operator_name"] == "op"
    assert s["session_id"].startswith("react_")
    assert s["db_session_id"] is None  # DB mock None → best-effort atlandı, seans yine de aktif


def test_start_session_rejects_double_start(api):
    asyncio.run(api.start_session(_payload(api), _SahteIstek()))
    with pytest.raises(Exception) as ei:  # HTTPException 409
        asyncio.run(api.start_session(_payload(api), _SahteIstek()))
    assert getattr(ei.value, "status_code", None) == 409


# ── stop_session: aktif→pasif + boş→ok ───────────────────────────────────────
def test_stop_session_no_active_returns_ok(api):
    resp = asyncio.run(api.stop_session())
    assert resp["status"] == "ok"
    assert "Aktif seans yok" in resp["message"]


def test_stop_session_marks_inactive(api):
    asyncio.run(api.start_session(_payload(api), _SahteIstek()))
    asyncio.run(api.stop_session())
    with api._session_lock:
        assert api._active_session.get("is_active") is False


# ── start_ai_session: AI modu + manuel seansı devralma ───────────────────────
def test_start_ai_session_sets_ai_mode(api):
    api.start_ai_session(freq=10, duty=25, duration_minutes=15, coil_ids=[6, 7], mode="AI")
    with api._session_lock:
        s = dict(api._active_session)
    assert s["is_active"] is True
    assert s["mode"] == "AI"
    assert s["session_id"].startswith("ai_")
    assert s["coil_ids"] == [6, 7]


# ── B-2.2 extraction invariantı: _active_session kimliği SABİT (rebind YOK) → alias çalışır ─────
def test_active_session_identity_stable_across_start(api):
    """start_session artık `_active_session`'ı REBIND etmez (in-place clear+update) → dict kimliği
    korunur. session_state alias'ının doğruluğu buna bağlı (rebind olsaydı alias eski dict'e kalırdı)."""
    before = api._active_session
    asyncio.run(api.start_session(_payload(api), _SahteIstek()))
    assert api._active_session is before, "start_session _active_session'ı rebind etti (alias kopardı)"


def test_active_session_identity_stable_across_ai_start(api):
    before = api._active_session
    api.start_ai_session(freq=10, duty=25, duration_minutes=10, coil_ids=[6], mode="AI")
    assert api._active_session is before, "start_ai_session _active_session'ı rebind etti (alias kopardı)"


def test_active_session_shared_with_session_state_module(api):
    """State gerçekten `servers/session_state.py`'ye taşındı + api_server aynı nesneye alias'lı."""
    from servers import session_state

    assert api._active_session is session_state._active_session
    assert api._session_lock is session_state._session_lock
    # coil_run_tracker'a enjekte edilen getter da session_state üzerinden okur
    with api._session_lock:
        api._active_session["db_session_id"] = 99
    assert session_state.current_db_session_id() == 99


def test_start_ai_session_takes_over_active_manual(api):
    # Aktif MANUEL seans (db_session_id'li) kur → AI başlayınca düzgün devralmalı (orphan önle)
    with api._session_lock:
        api._active_session.clear()
        api._active_session.update(
            {
                "is_active": True,
                "session_id": "react_x",
                "mode": "Manuel",
                "coil_ids": [6, 7, 8],
                "db_session_id": None,
                "start_time": 1.0,
            }
        )
    api.start_ai_session(freq=10, duty=25, duration_minutes=15, coil_ids=[6], mode="AI")
    with api._session_lock:
        s = dict(api._active_session)
    # Yeni AI seansı manueli devraldı (mode AI, yeni session_id, yeni coil kapsamı)
    assert s["mode"] == "AI"
    assert s["session_id"].startswith("ai_")
    assert s["coil_ids"] == [6]
    assert s["is_active"] is True
