"""Kritik yol: treatment DB at-rest şifreleme görünürlük flag'i + retention/maintenance çalışması."""
from database.treatment_history_db import get_treatment_db


def test_at_rest_encryption_flag_visible(temp_app_data):
    db = get_treatment_db(temp_app_data)
    snap = db.get_database_health_snapshot()  # bağlantı kurar → flag'i belirler
    assert "at_rest_encrypted" in snap
    # SQLCipher anahtarı/lib yoksa düz-metin → flag False (sessizce gizlenmemeli).
    assert isinstance(snap["at_rest_encrypted"], bool)
    assert isinstance(getattr(db, "at_rest_encrypted", None), bool)


def test_retention_policy_runs_and_reports(temp_app_data):
    db = get_treatment_db(temp_app_data)
    report = db.apply_data_retention_policy()
    assert isinstance(report, dict)
    for k in ("sensor_samples_removed", "session_events_removed", "sessions_pii_redacted"):
        assert k in report


def test_maintenance_and_backup(temp_app_data, tmp_path):
    db = get_treatment_db(temp_app_data)
    m = db.run_maintenance()
    assert isinstance(m, dict)
    backup = tmp_path / "backup.db"
    assert db.create_backup(str(backup)) is True
    assert backup.exists()


def test_delete_session_with_children_no_fk_error(temp_app_data):
    db = get_treatment_db(temp_app_data)
    sid = db.start_session(treatment_mode="Test", patient_name="X")
    db.add_sensor_samples_batch(sid, [{
        "coil_id": "1", "sample_ts": 1.0, "temperature_c": 30.0, "magnetic_field_mt": 1.0,
        "current_a": 0.5, "pwm_frequency_hz": 50, "pwm_duty_percent": 25, "payload": {},
    }])
    db.record_session_event(sid, "test_event", {"a": 1})
    # Çocuk kayıtlı seansı silmek FK 500 ATMAMALI (sensor_samples/session_events manuel CASCADE).
    db.delete_session(sid)
    db.delete_session(sid)  # idempotent — tekrar silmek de patlamamalı
