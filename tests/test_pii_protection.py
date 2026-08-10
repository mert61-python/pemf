# Author: mertaygn, cglrgrkn
"""Kritik yol (KVKK/güvenlik): at-rest şifreleme fail-closed (B-1.4) + tedavi-geçmişi PII politikası.

PII maskeleme SAHİP KARARIYLA (2026-07-28) VARSAYILAN KAPALI; PEMF_MASK_HISTORY_PII=1 ile
opt-in açılır. Testler her iki modu da kilitler: varsayılanda gerçek ad yazılır, bayrak
açıkken maskeleme ÇALIŞIR kalır. Bu makinede keyring anahtarı olabileceğinden SQLCipher yolu
MOCK'lanır."""

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
        return (
            conn.cursor()
            .execute(
                "SELECT operator_name, patient_name, patient_notes FROM treatment_sessions WHERE id=?",
                (sid,),
            )
            .fetchone()
        )


def test_treatment_pii_real_by_default_when_plaintext(temp_app_data, monkeypatch):
    """SAHİP KARARI (2026-07-28): maskeleme VARSAYILAN KAPALI → şifresiz DB'de bile GERÇEK ad.

    Gerekçe (bkz. TreatmentHistoryDB._redact_pii): aynı PII zaten patients.db'de düz-metin
    tutuluyor; yalnız tedavi-geçmişinde maskelemek tutarsız bir yarım-önlemdi — klinik
    kullanılabilirliğini bozuyor, gerçek gizlilik eklemiyordu. Doğru üretim çözümü
    PEMF_ENCRYPT_AT_REST=1 + SQLCipher'dır.

    NOT: bu test eskiden maskelemenin AÇIK olduğunu iddia ediyordu ve karar değişince
    kırılmıştı — testin kendisi bayattı, kod doğruydu.
    """
    monkeypatch.delenv("PEMF_MASK_HISTORY_PII", raising=False)
    from database.treatment_history_db import TreatmentHistoryDB

    db = TreatmentHistoryDB(temp_app_data)
    db.at_rest_encrypted = False  # şifresiz senaryo (dev/yanlış-yapılandırma)
    sid = db.start_session("Manuel", operator_name="Dr Mert", patient_name="Boncuk")
    db.end_session(sid, patient_notes="gizli not", duration_minutes=1)
    row = _read_session(db, sid)
    assert row[0] == "Dr Mert"
    assert row[1] == "Boncuk"
    assert row[2] == "gizli not"


def test_treatment_pii_masked_when_opt_in(temp_app_data, monkeypatch):
    """PEMF_MASK_HISTORY_PII=1 → eski maskeleme davranışı geri gelir (opt-in KORUNMALI).

    Karar 'maskeleme kapalı' olsa da mekanizmanın ÇALIŞIR kalması gerekir; bir refactorda
    sessizce ölürse bayrağı açan klinik korumasız kalır.
    """
    monkeypatch.setenv("PEMF_MASK_HISTORY_PII", "1")
    from database.treatment_history_db import TreatmentHistoryDB

    db = TreatmentHistoryDB(temp_app_data)
    db.at_rest_encrypted = False
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


def _read_params(db, sid):
    with db._get_connection() as conn:
        cur = conn.cursor()
        q = "SELECT parameter_value FROM session_parameters WHERE session_id=? AND parameter_name=?"
        return (
            cur.execute(q, (sid, "duration")).fetchone()[0],
            cur.execute(q, (sid, "patient_owner_email")).fetchone()[0],
        )


def test_treatment_nonpii_param_never_masked(temp_app_data, monkeypatch):
    """PII OLMAYAN parametre (duration) hiçbir modda maskelenmez; PII varsayılanda GERÇEK kalır.

    Maskeleme bayrağı kapalıyken (varsayılan) e-posta da gerçek yazılır — sahip kararı.
    Bayrak açıkken YALNIZ PII maskelenir, duration etkilenmez (ayrım korunmalı).
    """
    from database.treatment_history_db import TreatmentHistoryDB

    # Varsayılan (maskeleme KAPALI)
    monkeypatch.delenv("PEMF_MASK_HISTORY_PII", raising=False)
    db = TreatmentHistoryDB(temp_app_data)
    db.at_rest_encrypted = False
    sid = db.start_session("Manuel", patient_name="Y")
    db.set_session_parameter(sid, "duration", "20")
    db.set_session_parameter(sid, "patient_owner_email", "a@b.com")
    dur, oe = _read_params(db, sid)
    assert dur == "20", "non-PII korunmalı"
    assert oe == "a@b.com", "varsayılanda PII de gerçek yazılır (sahip kararı)"

    # Opt-in (maskeleme AÇIK) → yalnız PII maskelenir
    monkeypatch.setenv("PEMF_MASK_HISTORY_PII", "1")
    sid2 = db.start_session("Manuel", patient_name="Z")
    db.set_session_parameter(sid2, "duration", "20")
    db.set_session_parameter(sid2, "patient_owner_email", "a@b.com")
    dur2, oe2 = _read_params(db, sid2)
    assert dur2 == "20", "maskeleme açıkken bile non-PII korunmalı"
    assert oe2 == "[SIFRELENMEMIS-DB]", "opt-in modda PII maskelenmeli"
