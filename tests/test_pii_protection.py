"""Kritik yol (KVKK/güvenlik): at-rest şifreleme fail-closed (B-1.4) + şifresiz DB'de PII
maskeleme (B-1.3). Bu makinede keyring anahtarı olabileceğinden SQLCipher yolu MOCK'lanır."""
import pytest


# ── B-1.4: PatientDatabase fail-closed (TreatmentHistoryDB ile tutarlı) ──────────────
def test_patient_db_fail_closed_when_encryption_requested(temp_app_data, monkeypatch):
    """PEMF_ENCRYPT_AT_REST=1 ama SQLCipher yok → düz-metin yazmaktansa RuntimeError."""
    monkeypatch.setenv("PEMF_ENCRYPT_AT_REST", "1")
    import database.patient_database as pdb
    monkeypatch.setattr(pdb, "import_sqlcipher", lambda: None)
    monkeypatch.setattr(pdb, "get_sqlcipher_key", lambda *a, **k: "")
    with pytest.raises(RuntimeError):
        pdb.PatientDatabase(str(temp_app_data / "patients.db"))


def test_patient_db_plaintext_ok_when_encryption_off(temp_app_data, monkeypatch):
    """Şifreleme İSTENMEDİYSE (bayrak yok) düz-metin açılır — geriye uyumlu."""
    monkeypatch.delenv("PEMF_ENCRYPT_AT_REST", raising=False)
    import database.patient_database as pdb
    monkeypatch.setattr(pdb, "import_sqlcipher", lambda: None)
    monkeypatch.setattr(pdb, "get_sqlcipher_key", lambda *a, **k: "")
    db = pdb.PatientDatabase(str(temp_app_data / "patients.db"))
    assert db.add_patient({"name": "X", "species": "Kedi"})


# ── B-1.3: TreatmentHistoryDB PII maskeleme (şifresiz DB'de gerçek PII yazılmaz) ──────
def _read_session(db, sid):
    with db._get_connection() as conn:
        return conn.cursor().execute(
            "SELECT operator_name, patient_name, patient_notes FROM treatment_sessions WHERE id=?",
            (sid,),
        ).fetchone()


def test_treatment_pii_masked_when_plaintext(temp_app_data):
    from database.treatment_history_db import TreatmentHistoryDB
    db = TreatmentHistoryDB(temp_app_data)
    db.at_rest_encrypted = False  # şifresiz senaryo (dev/yanlış-yapılandırma)
    sid = db.start_session("Manuel", operator_name="Dr Mert", patient_name="Boncuk")
    db.end_session(sid, patient_notes="gizli not", duration_minutes=1)
    row = _read_session(db, sid)
    assert row[0] == "[SIFRELENMEMIS-DB]"  # operator_name maskeli
    assert row[1] == "[SIFRELENMEMIS-DB]"  # patient_name maskeli
    assert row[2] == "[SIFRELENMEMIS-DB]"  # patient_notes maskeli


def test_treatment_pii_intact_when_encrypted(temp_app_data):
    from database.treatment_history_db import TreatmentHistoryDB
    db = TreatmentHistoryDB(temp_app_data)
    db.at_rest_encrypted = True  # SQLCipher açık (üretim) → değerler AYNEN
    sid = db.start_session("Manuel", operator_name="Dr Mert", patient_name="Boncuk")
    row = _read_session(db, sid)
    assert row[0] == "Dr Mert"
    assert row[1] == "Boncuk"


def test_treatment_nonpii_param_not_masked(temp_app_data):
    """PII olmayan parametre (duration) şifresiz DB'de bile maskelenmez."""
    from database.treatment_history_db import TreatmentHistoryDB
    db = TreatmentHistoryDB(temp_app_data)
    db.at_rest_encrypted = False
    sid = db.start_session("Manuel", patient_name="Y")
    db.set_session_parameter(sid, "duration", "20")
    db.set_session_parameter(sid, "patient_owner_email", "a@b.com")
    with db._get_connection() as conn:
        cur = conn.cursor()
        dur = cur.execute("SELECT parameter_value FROM session_parameters WHERE session_id=? AND parameter_name='duration'", (sid,)).fetchone()
        oe = cur.execute("SELECT parameter_value FROM session_parameters WHERE session_id=? AND parameter_name='patient_owner_email'", (sid,)).fetchone()
    assert dur[0] == "20"                       # non-PII korundu
    assert oe[0] == "[SIFRELENMEMIS-DB]"        # PII maskelendi
