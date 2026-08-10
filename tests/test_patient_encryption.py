# Author: mertaygn, cglrgrkn
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

    raw = (
        sqlite3.connect(str(temp_app_data / "patients.db"))
        .execute("SELECT name FROM patients WHERE id=?", (pid,))
        .fetchone()[0]
    )
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


def test_get_all_patients_paginates_in_sql(temp_app_data, monkeypatch):
    """DENETIM P2 regresyonu: sayfalama SQL'de yapılmalı, tüm tablo deşifre EDİLMEMELİ.

    Hata: get_all_patients her çağrıda TÜM hastaları çekip TÜMÜNÜN alan-başı Fernet deşifresini
    yapıyor ve bunu self.lock TUTARAK sonuçlandırıyordu; sayfalama yalnız çağıranda (Python
    dilimi) vardı → /api/patients?limit=20 bile binlerce kayıtlık klinikte tüm tabloyu deşifre
    ediyor, o süre boyunca hasta-DB'sine erişen her işlem blokleniyordu.
    """
    import database.patient_database as pdb

    monkeypatch.delenv("PEMF_ENCRYPT_AT_REST", raising=False)
    monkeypatch.setattr(pdb, "import_sqlcipher", lambda: None)
    monkeypatch.setattr(pdb, "get_sqlcipher_key", lambda *a, **k: "")
    db = pdb.PatientDatabase(str(temp_app_data / "patients.db"))

    for i in range(7):
        assert db.add_patient({"name": f"Hasta{i}", "species": "Kedi"})

    assert db.count_patients() == 7, "toplam sayım deşifre gerektirmeden doğru olmalı"

    # Deşifre edilen kayıt sayısını say → sayfa boyutuyla sınırlı olmalı
    calls = {"n": 0}
    _orig = pdb.PatientDatabase._decrypt_patient_fields

    def _counting(self, p):
        calls["n"] += 1
        return _orig(self, p)

    monkeypatch.setattr(pdb.PatientDatabase, "_decrypt_patient_fields", _counting)

    page = db.get_all_patients(limit=3, offset=0)
    assert len(page) == 3
    assert calls["n"] == 3, f"yalnız istenen sayfa deşifre edilmeli, edilen: {calls['n']}"

    calls["n"] = 0
    page2 = db.get_all_patients(limit=3, offset=3)
    assert len(page2) == 3 and calls["n"] == 3
    assert {p["name"] for p in page}.isdisjoint({p["name"] for p in page2}), "sayfalar örtüşmemeli"

    # limit=0 → hepsi (geriye uyumlu)
    calls["n"] = 0
    assert len(db.get_all_patients()) == 7 and calls["n"] == 7


def test_unreadable_placeholder_never_overwrites_ciphertext(temp_app_data, monkeypatch):
    """DENETIM P3 regresyonu: '[okunamayan kayıt]' yer-tutucusu GERİ YAZILMAMALI.

    Çözülemeyen (farklı anahtar/eski sürüm) şifreli alan UI'ya yer-tutucu olarak gider. Operatör
    BAŞKA bir alanı düzenleyip kaydettiğinde form bu metni aynen geri gönderiyordu → orijinal
    (doğru anahtarla belki hâlâ kurtarılabilir) ciphertext, sabit metnin şifrelenmiş hâliyle
    EZİLİYOR ve hasta verisi KALICI kayboluyordu.
    """
    import database.patient_database as pdb

    monkeypatch.delenv("PEMF_ENCRYPT_AT_REST", raising=False)
    monkeypatch.setattr(pdb, "import_sqlcipher", lambda: None)
    monkeypatch.setattr(pdb, "get_sqlcipher_key", lambda *a, **k: "")
    db = pdb.PatientDatabase(str(temp_app_data / "patients.db"))

    pid = db.add_patient({"name": "Boncuk", "owner": "Ayşe", "species": "Kedi"})
    assert pid

    # Operatör yalnız 'species' değiştiriyor; 'name' alanı çözülemediği için form
    # yer-tutucuyu aynen geri gönderiyor.
    ok = db.update_patient(pid, {"name": pdb._UNREADABLE_PLACEHOLDER, "species": "Köpek"})
    assert ok, "diğer alanların güncellenmesi başarılı olmalı"

    row = next(p for p in db.get_all_patients() if p["id"] == pid)
    assert row["species"] == "Köpek", "gerçek düzenleme uygulanmalı"
    assert row["name"] == "Boncuk", "yer-tutucu orijinal değeri EZMEMELİ"
    assert row["name"] != pdb._UNREADABLE_PLACEHOLDER
