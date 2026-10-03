# Author: mertaygn, cglrgrkn
"""Characterization: session/notes + session/active — extraction ÖNCESİ davranış dondurma.

⚠️ D1.78 (B-3.26): `session/notes` fallback'i (aktif seans yokken start+end → YENİ 'completed' satır) burada
"doğru" diye DONDURULMUŞTU — oysa kusurdu: yeniden başlatma sonrası kurtarılmış satırın yanına koşusuz/kanıtsız ikinci bir
tedavi yazıyordu. Kol artık KUSUR testidir: seansı belirlenemeyen not 409 alır, YENİ satır AÇILMAZ. `session/active`
read-only GÜVENLİK sözleşmesi: yanıtta süre-dolumu göstersе bile GLOBAL state'i MUTATE ETMEZ
(watchdog STOP'u bastırma riski) → art arda iki GET aynı is_active davranışını korur.

Baseline: 2026-07-06 (refactor ÖNCESİ). Client kurulumu test_api_safety ile aynı.
"""

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


def test_KRITIK_D178_seansi_belirlenemeyen_not_YENI_completed_satir_ACMAZ_409(client):
    """POST /api/session/notes (aktif seans YOK, bu hastanın bitmiş seansı YOK): 409 + YENİ seans satırı AÇILMAZ.

    Eskiden 200 + yeni 'completed' satır (istemcinin PLANLANAN süresiyle, koşusuz) — kusur buradaki karakterizasyonla
    donduruluyordu. Davranışlı kapı: tests/test_seans_notu_DOGRU_SEANSA_yazilir_D166_D178.py."""
    from servers import api_server

    client.post("/api/session/stop")  # aktif seans olmasın
    with api_server._session_lock:
        api_server._active_session.clear()  # bellekte (bitmiş) seans da yok — yeniden başlatma
    db = api_server._get_treatment_db()
    assert db is not None, "aparat: tedavi DB'si açılamadı"

    def _sayi():
        with db._get_connection() as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM treatment_sessions WHERE patient_name = ?", ("CharTest-D178",)
            ).fetchone()[0]

    once = _sayi()
    payload = {
        "mode": "Manuel",
        "frequency": 50.0,
        "intensity": 10.0,
        "notes": "characterization-note",
        "duration_minutes": 5,
        "patient_name": "CharTest-D178",
    }
    r = client.post("/api/session/notes", json=payload)
    assert r.status_code == 409, f"seansı belirlenemeyen not kabul edildi: {r.status_code} {r.text[:120]}"
    assert _sayi() == once, "seansı belirlenemeyen not YENİ seans satırı açtı"
