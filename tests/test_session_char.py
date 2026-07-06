"""Characterization: session/notes + session/active — extraction ÖNCESİ davranış dondurma.

`session/notes` mevcut testlerde KAPSANMIYOR → burada karakterize edilir (fallback yolu:
aktif seans yokken start+end → success + session_id + sensor_samples). `session/active`
read-only GÜVENLİK sözleşmesi: yanıtta süre-dolumu göstersе bile GLOBAL state'i MUTATE ETMEZ
(watchdog STOP'u bastırma riski) → art arda iki GET aynı is_active davranışını korur.

Baseline: 2026-07-06 (refactor ÖNCESİ). Client kurulumu test_api_safety ile aynı.
"""
import os

os.environ.pop("PEMF_SIMULATE", None)

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    from servers import api_server

    return TestClient(api_server.app)


def test_session_active_inactive_and_readonly(client):
    """GET /api/session/active (aktif seans YOK): 200 + is_active falsy; read-only → art arda stabil.

    (Not: '== {}' katı invariant değil — test-sırasına göre önceki test global state bırakabilir;
    STABİL invariant: inaktif→is_active falsy + GET global'i MUTATE etmez.)"""
    client.post("/api/session/stop")  # aktif seansı durdur (deterministik)
    r1 = client.get("/api/session/active")
    assert r1.status_code == 200
    b1 = r1.json()
    assert isinstance(b1, dict) and not b1.get("is_active"), f"stop sonrası aktif görünüyor: {b1}"
    # GET salt-okunur → ikinci çağrı is_active'i değiştirmemeli (global mutasyon yok).
    assert client.get("/api/session/active").json().get("is_active") == b1.get("is_active")


def test_session_notes_fallback_response_shape(client):
    """POST /api/session/notes (aktif seans YOK → fallback): 200 + {status, session_id, sensor_samples}."""
    client.post("/api/session/stop")  # aktif seans olmasın → fallback yolu
    payload = {
        "mode": "Manuel", "frequency": 50.0, "intensity": 10.0,
        "notes": "characterization-note", "duration_minutes": 5, "patient_name": "CharTest",
    }
    r = client.post("/api/session/notes", json=payload)
    assert r.status_code == 200, f"beklenmeyen: {r.status_code} {r.text[:120]}"
    body = r.json()
    assert body.get("status") == "success"
    assert "session_id" in body
    assert "sensor_samples" in body
