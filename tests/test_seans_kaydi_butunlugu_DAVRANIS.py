# Author: mertaygn, cglrgrkn
"""D1.42 · B-10.116 · B-10.120 · B-10.134 — seans kaydı bütünlüğü kapıları DAVRANIŞA bağlı.

ÖLÇÜLEN KÖRLÜK (ürün bugün doğru; kapılar kör):
  * (B-10.116) çökme kurtarması yalnız `not in ('completed', 'active')` ile ölçülüyordu — kurtarılan seans
    `EMERGENCY_STOPPED` diye mühürlense (güvenlik olayı uydurulur) YEŞİL. → `test_cokme_sonrasi_seans_kurtarma`.
  * (B-10.120) `audit_ref` testi değeri KENDİSİ yazıyordu; üretimdeki `/api/session/start` yazımı
    (`set_session_parameter(_sid, "audit_ref", …)`) `pass` yapılsa YEŞİL — denetim izi seansa bağlanamaz.
  * (B-10.134) monotonic süre kapısı metin aramasıydı; `/api/session/stop` duvar saatine dönse ya da süre-watchdog
    finalize'ı `start_mono`'yu geçmese YEŞİL — NTP/DST sıçramasında kayıtlı tedavi süresi YANLIŞ.

Bu dosya GERÇEK `/api/session/start` + `/api/session/stop` (gerçek HC, kayıtçı kuyruk, tmp tedavi DB'si) ve
GERÇEK `_session_duration_watchdog` turunu (yalnız kendi iş parçacığında uyku/saat; `tests/dongu_tek_tur.py`)
koşturur. Duvar saati sıçraması YALNIZ ölçülen yolun iş parçacığında uygulanır.
"""

from __future__ import annotations

import time

import pytest
from dongu_tek_tur import bir_tur_kos
from topoloji import TUM_STM


@pytest.fixture
def ortam(tmp_path, monkeypatch):
    from database.treatment_history_db import TreatmentHistoryDB
    from fastapi.testclient import TestClient
    from kayitci_donanim import gercek_hc
    from servers import api_server as api
    from servers import coil_run_tracker, live_state

    db = TreatmentHistoryDB(tmp_path)
    monkeypatch.setattr(api, "_get_treatment_db", lambda: db)
    monkeypatch.setattr(coil_run_tracker, "_treatment_db_getter", lambda: db)
    monkeypatch.setattr(api, "_ws_broadcast_sync", lambda *a, **k: None)
    monkeypatch.setattr(api, "_push_notification", lambda *a, **k: None)
    live_state.stm_komut_kabulu_bildir()
    with api._session_lock:
        eski = dict(api._active_session)
    istemci = TestClient(api.app, client=("127.0.0.1", 51237))
    with gercek_hc() as hc:
        monkeypatch.setattr(api.state, "hardware", hc)
        try:
            yield api, istemci, db
        finally:
            istemci.post("/api/session/stop", json={})
            with api._session_lock:
                api._active_session.clear()
                api._active_session.update(eski)
            db.close_connections()
            live_state.stm_komut_kabulu_bildir()


def _baslat(istemci, sure_dk=5):
    r = istemci.post(
        "/api/session/start",
        json={
            "mode": "Manuel",
            "frequency": 100,
            "duty": 40,
            "phase": 0,
            "intensity": 0.0,
            "duration_minutes": sure_dk,
            "coil_ids": [min(TUM_STM)],
            "patient_name": "KayitButunlugu",
        },
    )
    assert r.status_code == 200, r.text[:300]


def _seans_satiri(db, sid):
    with db._get_connection() as conn:
        return conn.execute(
            "SELECT session_status, duration_minutes FROM treatment_sessions WHERE id=?", (sid,)
        ).fetchone()


def test_KRITIK_audit_ref_GERCEK_seans_baslatmada_muhurle_YAZILIR(ortam):
    api, istemci, db = ortam
    _baslat(istemci)
    with api._session_lock:
        muhur, sid = api._active_session.get("session_id"), api._active_session.get("db_session_id")
    assert muhur and sid, f"aparat: seans mührü/DB satırı yok ({muhur}, {sid})"
    with db._get_connection() as conn:
        satir = conn.execute(
            "SELECT parameter_value FROM session_parameters WHERE session_id=? AND parameter_name='audit_ref'", (sid,)
        ).fetchone()
    assert satir is not None, "üretim /api/session/start audit_ref YAZMADI → denetim izi seansa JOIN edilemez"
    assert satir[0] == muhur, f"audit_ref {satir[0]!r} ≠ seans mührü {muhur!r}"


@pytest.mark.parametrize(("mono_geri_sn", "beklenen_dk"), [(0, 0), (120, 2)], ids=["sifir_dk", "pozitif_2dk"])
def test_KRITIK_session_stop_suresi_MONOTONIC_duvar_saati_sicramasi_YAZILMAZ(
    ortam, monkeypatch, mono_geri_sn, beklenen_dk
):
    """Kayıtlı süre MONOTONIC başlangıçtan. 1-B bağımsız inceleme (i4): kapı eskiden yalnız `time.time`'ı +1 saat
    kaydırıyordu — süre `datetime.now().timestamp()` (yine duvar saati) ile hesaplanınca YEŞİLDİ. Artık duvar-saati
    başlangıcı 1 saat GERİDE kurulur (HER duvar-saati hesabı ≥ 60 dk verir), monotonic başlangıç `mono_geri_sn`
    geride: kayıt TAM beklenen dakika olmalı (pozitif kontrol 120 sn → 2 dk: monotonic GERÇEKTEN kullanılıyor)."""
    api, istemci, db = ortam
    _baslat(istemci)
    with api._session_lock:
        sid = api._active_session.get("db_session_id")
        api._active_session["started_epoch"] = float(api._active_session["started_epoch"]) - 3600.0
        api._active_session["start_time"] = float(api._active_session.get("start_time") or time.time()) - 3600.0
        api._active_session["start_mono"] = time.monotonic() - mono_geri_sn
    r = istemci.post("/api/session/stop", json={})
    assert r.status_code == 200, r.text[:200]
    _durum, sure = _seans_satiri(db, sid)
    assert sure is not None and int(sure) == beklenen_dk, (
        f"kayıtlı süre {sure} dk (beklenen {beklenen_dk}) — süre duvar saatinden hesaplanıyor (monotonic olmalı)"
    )


def test_KRITIK_sure_watchdog_finalize_suresi_MONOTONIC(ortam):
    """Süre dolmuş seans (monotonic 61 sn önce başladı) watchdog turunda kapanır; o turda duvar saati +1 saat
    sıçramış. Kayıt 1 dk olmalı (duvar saatiyle 61 dk)."""
    api, _istemci, db = ortam
    sid = db.start_session(treatment_mode="Manuel", target_condition="test", patient_name="Watchdog")
    simdi_m, simdi_e = time.monotonic(), time.time()
    with api._session_lock:
        api._active_session.clear()
        api._active_session.update(
            {
                "is_active": True,
                "session_id": "d142-watchdog",
                "coil_ids": [min(TUM_STM)],
                "duration_minutes": 1,
                "db_session_id": sid,
                "start_mono": simdi_m - 61,
                # 1-B inceleme (i4): duvar-saati başlangıcı 1 saat DAHA geride — her duvar-saati hesabı ≥ 61 dk verir
                "started_epoch": simdi_e - 3661,
                "start_time": simdi_e - 3661,
            }
        )
    uyku, hatalar = bir_tur_kos(api._session_duration_watchdog, zaman_kaydir=3600.0)
    assert (uyku, hatalar) == (1, []), f"watchdog turu: uyku={uyku} hata={hatalar}"
    with api._session_lock:
        assert api._active_session.get("is_active") is False, "aparat: süresi dolan seans kapanmadı"
    durum, sure = _seans_satiri(db, sid)
    assert durum == "completed", f"aparat: watchdog finalize kaydı kapatmadı ({durum})"
    assert sure == 1, f"kayıtlı süre {sure} dk — finalize duvar saatini kullandı (monotonic 61 sn = 1 dk)"
