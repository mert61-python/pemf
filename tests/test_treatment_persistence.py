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
