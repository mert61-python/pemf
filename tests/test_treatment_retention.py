# Author: mertaygn, cglrgrkn
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
    db.add_sensor_samples_batch(
        sid,
        [
            {
                "coil_id": "1",
                "sample_ts": 1.0,
                "temperature_c": 30.0,
                "magnetic_field_mt": 1.0,
                "current_a": 0.5,
                "pwm_frequency_hz": 50,
                "pwm_duty_percent": 25,
                "payload": {},
            }
        ],
    )
    db.record_session_event(sid, "test_event", {"a": 1})
    # Çocuk kayıtlı seansı silmek FK 500 ATMAMALI (sensor_samples/session_events manuel CASCADE).
    db.delete_session(sid)
    db.delete_session(sid)  # idempotent — tekrar silmek de patlamamalı


def test_retention_steps_can_be_disabled(temp_app_data):
    """DENETIM P2 regresyonu: retention adımları kapatılabilmeli (0 = kapalı).

    Hata: apply_data_retention_policy() parametresiz çağrılıyordu → sabit 90/365/30/365 gün
    zorlanıyor, bobin-çalışma kayıtları + seans olayları GERİ DÖNÜŞSÜZ siliniyor ve hasta/operatör
    adları maskeleniyordu; opt-out yoktu. Tıbbi-hukuki saklama süresi ülkeye/kliniğe göre değişir.
    """
    from database.treatment_history_db import TreatmentHistoryDB

    db = TreatmentHistoryDB(temp_app_data)
    db.at_rest_encrypted = True
    sid = db.start_session("Manuel", patient_name="Minnos", operator_name="Dr Mert")
    db.end_session(sid, patient_notes="klinik gözlem", duration_minutes=20)

    # Hepsi kapalı → hiçbir şey silinmemeli/maskelenmemeli
    rep = db.apply_data_retention_policy(
        sensor_retain_days=0, event_retain_days=0, dead_outbox_retain_days=0, pii_retain_days=0
    )
    assert all(v == 0 for v in rep.values()), f"tüm adımlar kapalıyken hiçbir şey silinmemeli: {rep}"

    row = next(h for h in db.get_session_history(limit=10) if h["id"] == sid)
    assert row["patient_name"] == "Minnos", "PII maskeleme kapalıyken isim korunmalı"


def test_retention_env_overrides_are_read(monkeypatch):
    """Bakım thread'i sabit süre yerine PEMF_RETAIN_* env'lerini okumalı."""
    from services.headless_db_maintenance import HeadlessDBMaintenance as M

    monkeypatch.setenv("PEMF_RETAIN_SENSOR_DAYS", "0")
    assert M._retain_days("PEMF_RETAIN_SENSOR_DAYS", 90) == 0, "0 = kapalı olarak okunmalı"
    monkeypatch.setenv("PEMF_RETAIN_SENSOR_DAYS", "bozuk")
    assert M._retain_days("PEMF_RETAIN_SENSOR_DAYS", 90) == 90, "geçersiz değer varsayılana düşmeli"
    monkeypatch.delenv("PEMF_RETAIN_SENSOR_DAYS", raising=False)
    assert M._retain_days("PEMF_RETAIN_SENSOR_DAYS", 90) == 90


def test_startup_backup_skipped_when_recent_one_exists(tmp_path, monkeypatch):
    """DENETIM P2 regresyonu: restart döngüsü yedek geçmişini imha etmemeli.

    Hata: döngü koşulu `first or ...` idi → servis HER açılışta yedek alıyordu. Rotasyon yalnız
    son N yedeği tuttuğundan crash-loop / art arda restart, N açılışta TÜM yedek geçmişini aynı
    günün kopyalarıyla değiştiriyordu (felaket-kurtarma penceresi yok olur).
    """
    import time

    from services.headless_db_maintenance import HeadlessDBMaintenance as M

    obj = M.__new__(M)  # __init__'i atla (DB/thread gerekmesin)
    obj.app_data_dir = tmp_path
    obj.backup_interval = 24 * 3600.0

    bdir = tmp_path / "backups"
    bdir.mkdir()
    assert obj._recent_backup_exists() is False, "yedek yokken açılışta yedek ALINMALI"

    taze = bdir / "pemf_treatment_history_20260803_120000.db"
    taze.write_bytes(b"x")
    assert obj._recent_backup_exists() is True, "taze yedek varken açılış yedeği ATLANMALI"

    # Bayat yedek → tekrar yedeklenmeli (servis uzun süre kapalı kaldıysa)
    eski = time.time() - (25 * 3600)
    import os

    os.utime(taze, (eski, eski))
    assert obj._recent_backup_exists() is False, "bayat yedek varken yeniden yedeklenmeli"
