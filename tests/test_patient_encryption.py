"""Kritik yol: hasta PII alan-şifrelemesi round-trip + cross-tenant (yabancı anahtar) maskeleme."""
import base64

from cryptography.fernet import Fernet

from database.patient_database import PatientDatabase


def _db(temp_app_data):
    return PatientDatabase(str(temp_app_data / "patients.db"))


def test_patient_roundtrip_encrypted_at_rest(temp_app_data, monkeypatch):
    # Bu test ALAN-düzeyi Fernet şifrelemesini doğrular (ham DB'de 'enc:' + düz-metin YOK).
    # Whole-DB SQLCipher'ı KAPAT: aksi halde makinenin keyring anahtarı varsa DB tümden şifreli
    # açılır → plain sqlite3.connect okuyamaz ve test makine-durumuna bağlı hale gelir (kararsız).
    import database.patient_database as _pdb
    monkeypatch.setattr(_pdb, "import_sqlcipher", lambda: None)
    monkeypatch.setattr(_pdb, "get_sqlcipher_key", lambda *a, **k: "")
    monkeypatch.delenv("PEMF_ENCRYPT_AT_REST", raising=False)
    db = _db(temp_app_data)
    pid = db.add_patient({"name": "TestMia", "species": "Kedi", "owner": "Ahmet"})
    assert pid

    # Ham DB değeri ŞİFRELİ olmalı (düz-metin 'TestMia' DİSKTE durmamalı).
    import sqlite3
    raw = sqlite3.connect(str(temp_app_data / "patients.db")).execute(
        "SELECT name FROM patients WHERE id=?", (pid,)
    ).fetchone()[0]
    assert raw != "TestMia"
    assert str(raw).startswith("enc:")

    # API görünümü doğru çözmeli.
    names = [p.get("name") for p in db.get_all_patients()]
    assert "TestMia" in names


def test_foreign_key_record_is_masked_not_leaked(temp_app_data):
    """Başka makinenin/kliniğin anahtarıyla şifreli kayıt çözülemez → ham ciphertext SIZMAMALI."""
    db = _db(temp_app_data)
    foreign_token = Fernet(Fernet.generate_key()).encrypt(b"SomeOtherClinicPatient")
    foreign_value = "enc:" + base64.urlsafe_b64encode(foreign_token).decode()

    decoded = db._decrypt_field(foreign_value)
    assert decoded == "[okunamayan kayıt]"
    assert "gAAAA" not in decoded and "Z0FBQ" not in decoded
