"""Kritik yol: tedavi seansı DB kalıcılığı — start→end round-trip, geçmişte görünürlük,
sensör örnek batch yazımı, ve süre hesaplama. DB katmanı doğrudan (SQLCipher-farkında bağlantı)."""


def _db(temp_app_data):
    from database.treatment_history_db import TreatmentHistoryDB
    return TreatmentHistoryDB(temp_app_data)


def test_session_start_end_roundtrip(temp_app_data):
    db = _db(temp_app_data)
    db.at_rest_encrypted = True  # PII intact (round-trip'i doğrulamak için)
    sid = db.start_session("Otomatik", target_condition="artrit", patient_name="Minnos")
    assert isinstance(sid, int) and sid > 0
    db.end_session(sid, parameters={"frequency_hz": 50.0, "intensity_mt": 2.0},
                   patient_notes="tamamlandı", duration_minutes=20)
    hist = db.get_session_history(limit=10)
    row = next((h for h in hist if h["id"] == sid), None)
    assert row is not None
    assert row["session_status"] == "completed"
    assert row["duration_minutes"] == 20
    assert row["patient_name"] == "Minnos"


def test_sensor_samples_batch_persist(temp_app_data):
    db = _db(temp_app_data)
    sid = db.start_session("Manuel", patient_name="Z")
    n = db.add_sensor_samples_batch(sid, [
        {"coil_id": "1", "sample_ts": 1.0, "temperature_c": 30.0, "magnetic_field_mt": 1.0,
         "current_a": 0.5, "pwm_frequency_hz": 50, "pwm_duty_percent": 25, "payload": {}},
        {"coil_id": "2", "sample_ts": 2.0, "temperature_c": 31.0, "magnetic_field_mt": 1.1,
         "current_a": 0.6, "pwm_frequency_hz": 50, "pwm_duty_percent": 25, "payload": {}},
    ])
    assert n == 2
    with db._get_connection() as conn:
        cnt = conn.cursor().execute(
            "SELECT COUNT(*) FROM sensor_samples WHERE session_id=?", (sid,)).fetchone()[0]
    assert cnt == 2


def test_health_snapshot_reports_encryption_flag(temp_app_data):
    db = _db(temp_app_data)
    snap = db.get_database_health_snapshot()
    assert "at_rest_encrypted" in snap
    assert isinstance(snap["at_rest_encrypted"], bool)


def test_end_session_computes_duration_when_absent(temp_app_data):
    """duration_minutes verilmezse başlangıç-bitiş farkından hesaplanır (negatif-clamp korumalı)."""
    db = _db(temp_app_data)
    sid = db.start_session("Manuel", patient_name="Q")
    db.end_session(sid)  # duration override YOK
    hist = db.get_session_history(limit=10)
    row = next((h for h in hist if h["id"] == sid), None)
    assert row is not None
    assert row["duration_minutes"] is not None and row["duration_minutes"] >= 0


def test_notes_do_not_overwrite_real_duration_after_stop(temp_app_data, monkeypatch):
    """DENETIM P1 regresyonu: /api/session/notes, /stop'un yazdığı GERÇEK süreyi EZMEMELİ.

    Hata: notes ucu zaten kapatılmış seansta end_session'ı TEKRAR çağırıyordu; end_session ise
    end_time/duration_minutes/session_status'u koşulsuz yeniden yazıyor. İstemci PLANLANAN süreyi
    (ControlScreen durationSec) gönderdiği için 4 dk'lık seans hasta dosyasında 20 dk PEMF
    maruziyeti olarak görünüyordu. `db_finalized` bayrağı tam bunun için yazılıyordu ama hiç
    okunmuyordu.
    """
    from fastapi.testclient import TestClient

    import database.treatment_history_db as thdb
    from servers import api_server

    db = thdb.TreatmentHistoryDB(temp_app_data)
    db.at_rest_encrypted = True
    monkeypatch.setattr(thdb, "get_treatment_db", lambda *a, **k: db)
    monkeypatch.setattr(api_server, "_app_data_dir", lambda: temp_app_data)

    sid = db.start_session("Manuel", patient_name="Minnos")
    db.end_session(sid, duration_minutes=4)          # /stop GERÇEK süreyi yazdı

    with api_server._session_lock:
        api_server._active_session.clear()
        api_server._active_session.update(
            {"is_active": False, "db_session_id": sid, "db_finalized": True}
        )

    client = TestClient(api_server.app)
    r = client.post("/api/session/notes", json={
        "notes": "iyi tolere etti",
        "duration_minutes": 20,      # istemci PLANLANAN süreyi gönderir
        "frequency": 50.0, "intensity": 2.0,
    })
    assert r.status_code == 200

    # ÖNCE asıl zarar: tıbbi kayıttaki gerçek maruziyet süresi korunmalı.
    row = next(h for h in db.get_session_history(limit=10) if h["id"] == sid)
    assert row["duration_minutes"] == 4, "gerçek tedavi süresi PLANLANAN süreyle ezilmemeli"
    assert row["session_status"] == "completed"
    assert row["frequency_hz"] == 50.0, "parametreler yine de güncellenmeli"
    assert r.json().get("durationPreserved") is True


def test_ai_session_opens_db_row_and_reuses_it(temp_app_data, monkeypatch):
    """DENETIM P1 regresyonu: otonom (AI Pro / AI Auto) tedavi DB'ye YAZILMALI.

    Hata: start_ai_session `_active_session`'ı db_session_id ALANI OLMADAN kuruyordu →
    _flush_sensor_buffer_if_active `if not _db_sid: return` ile tüm dakika-ortalamalarını
    atıyordu ve seansın DB satırı hiç açılmıyordu; canlı hayvana uygulanan dozun ve sıcaklık
    telemetrisinin kalıcı kaydı yoktu. Tekrarlı AI çağrısı (landmark auto_adjust her istekte
    çağırır) ise YENİ satır açmamalı.
    """
    import database.treatment_history_db as thdb
    from servers import api_server

    db = thdb.TreatmentHistoryDB(temp_app_data)
    db.at_rest_encrypted = True
    monkeypatch.setattr(api_server, "_get_treatment_db", lambda *a, **k: db)

    try:
        with api_server._session_lock:
            api_server._active_session.clear()

        api_server.start_ai_session(0.0, 0.0, 20, range(1, 8), "AI Pro")
        with api_server._session_lock:
            sid1 = api_server._active_session.get("db_session_id")
            started1 = api_server._active_session.get("started_epoch")
        assert sid1, "otonom tedavi DB seans satırı açmalı (sensör flush'ı buna bağlı)"
        assert started1, "started_epoch kurulmalı"

        # Aynı AI seansının tekrarlı çağrısı → MEVCUT satırı kullan
        api_server.start_ai_session(0.0, 0.0, 20, range(1, 8), "AI Pro")
        with api_server._session_lock:
            sid2 = api_server._active_session.get("db_session_id")
        assert sid2 == sid1, "tekrarlı AI çağrısı yeni DB satırı AÇMAMALI"

        assert len([h for h in db.get_session_history(limit=20) if h["id"] == sid1]) == 1
    finally:
        with api_server._session_lock:
            api_server._active_session.clear()
