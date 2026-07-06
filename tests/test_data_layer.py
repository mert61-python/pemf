"""Veri katmanı sağlamlaştırmaları (audit B-7.3, B-6.2, B-6.3, B-7.2): PatientDB FK cascade +
busy_timeout + create_backup; treatment session_parameters composite index."""
import sqlite3

import pytest


@pytest.fixture
def patient_db(temp_app_data, monkeypatch):
    import database.patient_database as pdb
    monkeypatch.setattr(pdb, "import_sqlcipher", lambda: None)
    monkeypatch.setattr(pdb, "get_sqlcipher_key", lambda *a, **k: "")
    monkeypatch.delenv("PEMF_ENCRYPT_AT_REST", raising=False)
    return pdb.PatientDatabase(str(temp_app_data / "patients.db"))


def test_patient_db_foreign_keys_and_busy_timeout_on(patient_db):
    with patient_db._get_connection() as conn:
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1   # B-7.3
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] >= 5000  # B-6.2


def test_patient_db_create_backup(patient_db, tmp_path):
    patient_db.add_patient({"name": "Boncuk", "owner": "Ali", "species": "Kedi"})
    bpath = tmp_path / "patients_backup.db"
    assert patient_db.create_backup(str(bpath)) is True   # B-7.2
    assert bpath.exists()
    # Yedek okunabilir + hasta içerir (düz-metin senaryoda).
    n = sqlite3.connect(str(bpath)).execute("SELECT COUNT(*) FROM patients").fetchone()[0]
    assert n >= 1


def test_treatment_composite_index_exists(temp_app_data):
    from database.treatment_history_db import TreatmentHistoryDB
    db = TreatmentHistoryDB(temp_app_data)
    with db._get_connection() as conn:
        idx = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='session_parameters'"
        ).fetchall()]
    assert "idx_session_params_sid_name" in idx   # B-6.3: (session_id, parameter_name)
