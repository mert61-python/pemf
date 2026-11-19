# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""İNCELEME-2 §10 #2 (i3-F-10 genişlemesi) — `/session/start` bobin sürüşü İSTİSNA atarsa başlatma bayrağı ve seans TUTARLI
kapanır; kabul edilen bobin telde KALMAZ; sonraki seans etkilenmez.

ÖLÇÜLEN KUSUR (İNCELEME-2 §8): `_start_stm_coils` istisnasında uç 500'le çıkıyor, `_active_session` `is_active` +
`baslatma_ucusta` kalıyordu; bobin 1 kabul edildiyse TELDE çalışmaya devam ediyordu (yanıt "başlatılamadı" iken) ve
operatörün sonraki normal Durdur'u satırı "İptal Edildi" yazıyordu. Varsayımsal (HC `update_coil` korunaklı) ama tek
kapanış noktası olmadan herhangi bir sürüş hatası yarım seans bırakır.

GERÇEK: `/api/session/start`, `/api/session/stop`, `HardwareController` (kayıtçı kuyruk; firmware aynası), `coil_run_tracker`,
tmp `TreatmentHistoryDB`. Sahte: yalnız ikinci bobinin `update_coil` çağrısı (istisna enjeksiyonu).
"""

from __future__ import annotations

import pytest
from topoloji import TUM_STM

_B1, _B2 = sorted(TUM_STM)[:2]


@pytest.fixture
def ortam(monkeypatch, tmp_path):
    import database.treatment_history_db as thdb
    from database.treatment_history_db import TreatmentHistoryDB
    from fastapi.testclient import TestClient
    from kayitci_donanim import gercek_hc
    from servers import api_server as api
    from servers import coil_run_tracker

    db = TreatmentHistoryDB(tmp_path)
    monkeypatch.setattr(api, "_get_treatment_db", lambda: db)
    monkeypatch.setattr(coil_run_tracker, "_treatment_db_getter", lambda: db)
    monkeypatch.setattr(api, "_mqtt_publish", lambda topic, payload: False)
    monkeypatch.setattr(thdb, "get_treatment_db", lambda *_a, **_k: db)
    with api._session_lock:
        eski = dict(api._active_session)
        api._active_session.clear()
    with gercek_hc() as hc:
        monkeypatch.setattr(api.state, "hardware", hc)
        monkeypatch.setattr(api.state, "core", hc.core)
        c = TestClient(api.app, raise_server_exceptions=False)
        try:
            yield api, hc, db, c, monkeypatch
        finally:
            c.post("/api/session/stop")
            hc.stop_all_coils()
            with api._session_lock:
                api._active_session.clear()
                api._active_session.update(eski)


def _baslat(c, bobinler):
    return c.post(
        "/api/session/start",
        json={
            "mode": "Manuel", "frequency": 100, "duty": 40, "phase": 0, "duration_minutes": 5,
            "coil_ids": bobinler, "patient_name": "Pamuk",
        },
    )  # fmt: skip


def _durumlar(db) -> list[str]:
    with db._get_connection() as conn:
        return [r[0] for r in conn.execute("SELECT session_status FROM treatment_sessions ORDER BY id").fetchall()]


def _ikinci_bobinde_patla(monkeypatch, hc):
    gercek = hc.update_coil

    def _sahte(coil_id, *a, **k):
        if coil_id == _B2 and k.get("start", True):
            raise RuntimeError("inc2-10-2: seri port yazimi patladi")
        return gercek(coil_id, *a, **k)

    monkeypatch.setattr(hc, "update_coil", _sahte)
    return gercek


def test_KRITIK_surus_istisnasi_seansi_IPTAL_eder_kabul_edilen_bobin_DURUR(ortam):
    api, hc, db, c, mp = ortam
    gercek = _ikinci_bobinde_patla(mp, hc)
    r = _baslat(c, [_B1, _B2])
    assert r.status_code == 503, f"surus hatasi durust 503 donmeli (500 degil): {r.status_code} {r.text[:200]}"
    assert "durduruldu" in r.json().get("detail", ""), "teyitli durdurmada yanit durdurmayi soylemiyor (KARSIT)"
    with api._session_lock:
        aktif = bool(api._active_session.get("is_active"))
    assert not aktif, "surus hatasindan sonra seans AKTIF kaldi (yarim seans)"
    assert hc.coils_state[_B1]["is_running"] is False, "kabul edilen bobin 1 TELDE kaldi (yanit 'baslatilmadi' iken)"
    assert _durumlar(db)[-1] == "cancelled", f"satir 'Iptal Edildi' kapanmadi: {_durumlar(db)}"
    mp.setattr(hc, "update_coil", gercek)


def test_KARSIT_sonraki_seans_normal_baslar_ve_normal_Durdur_DURDURULDU_yazar_Y306(ortam):
    api, hc, db, c, mp = ortam
    gercek = _ikinci_bobinde_patla(mp, hc)
    assert _baslat(c, [_B1, _B2]).status_code == 503
    mp.setattr(hc, "update_coil", gercek)
    r = _baslat(c, [_B1])
    assert r.status_code == 200 and r.json().get("status") == "success", r.text[:200]
    with api._session_lock:
        assert api._active_session.get("baslatma_ucusta") is False, "yeni seansin baslatma bayragi inmedi"
    assert c.post("/api/session/stop").status_code == 200
    assert _durumlar(db)[-1] == "stopped", (
        f"normal Durdur satiri yanlis kapandi: {_durumlar(db)}"
    )  # Y306: süre dolmadan elle Durdur = "Durduruldu" (stopped) — iptal / donanım reddi DEĞİL


def test_KRITIK_ic_durdurma_TEYITSIZse_yanit_durduruldu_DEMEZ(ortam):
    """1-E incelemesi (i-18.1): `stop_session` teyitsiz STOP'ta FIRLATMAZ, 409 yanıtı DÖNDÜRÜR; başlatma ucu onu yok sayıp
    "sürülen bobinler durduruldu" diyordu — STOP porta yazılamamışken (ölçüldü). STOP GERÇEKTEN gönderilir (gerçek
    `_stop_session_coils`); yalnız teyit sonucu "porta yazılamadı" olarak döner."""
    api, hc, db, c, mp = ortam
    gercek = _ikinci_bobinde_patla(mp, hc)
    gercek_dur = api._stop_session_coils

    def _teyitsiz_dur(coil_ids, yetkiyi_kes=False):
        gercek_dur(coil_ids, yetkiyi_kes)
        return [_B1]

    mp.setattr(api, "_stop_session_coils", _teyitsiz_dur)
    r = _baslat(c, [_B1, _B2])
    mp.setattr(hc, "update_coil", gercek)
    assert r.status_code == 503, r.text[:200]
    detay = r.json().get("detail", "")
    assert "DOĞRULANAMADI" in detay and "durduruldu" not in detay, (
        f"teyitsiz STOP 'durduruldu' diye bildirildi: {detay}"
    )
    assert hc.coils_state[_B1]["is_running"] is False, "aparat: gercek STOP gitmedi"
