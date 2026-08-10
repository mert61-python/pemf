# Author: mertaygn, cglrgrkn
"""Operasyonel doğrulama #8: KVKK inaktif-hasta anonimleştirme UÇTAN-UCA (local, sentetik veri).

Rapor 'canlı doğrulayamadım' diyordu → burada 5-yıl-inaktif sentetik hastayla uçtan-uca kanıtlanır:
inaktif hastanın PII'si [ANONIM] olur + `anonymized=1` + arama-indeksi temizlenir (eski adla bulunamaz);
aktif hasta KORUNUR; işlem idempotenttir (zaten-anonim tekrar işlenmez)."""

from datetime import datetime, timedelta


def _pdb(temp_app_data):
    from database.patient_database import PatientDatabase

    return PatientDatabase(str(temp_app_data / "patients.db"))


def _set_last_treatment(db, pid, dt):
    """last_treatment_at'i geçmişe/bugüne çek (anonymize COALESCE(last_treatment_at, created_at)'e bakar)."""
    with db._get_connection() as conn:
        conn.execute("UPDATE patients SET last_treatment_at=? WHERE id=?", (dt.isoformat(), pid))
        conn.commit()


def test_anonymize_inactive_end_to_end(temp_app_data):
    db = _pdb(temp_app_data)
    old = db.add_patient(
        {"name": "Eski Hasta", "owner": "Ali Veli", "owner_email": "ali@x.com", "vet_contact": "5551112233"}
    )
    new = db.add_patient({"name": "Yeni Hasta", "owner": "Ayşe Yılmaz", "owner_email": "ayse@x.com"})
    _set_last_treatment(db, old, datetime.now() - timedelta(days=2200))  # ~6 yıl inaktif
    _set_last_treatment(db, new, datetime.now() - timedelta(days=10))  # aktif

    anon = db.anonymize_inactive_patients(inactive_days=1825)  # 5 yıl eşiği

    assert old in anon, "6-yıl-inaktif hasta anonimleştirilmeliydi"
    assert new not in anon, "aktif hasta anonimleştirilMEmeli (muafiyet doğru)"

    op = db.get_patient(old)
    assert op["name"] == "[ANONIM]", "ad anonimleştirilmedi"
    assert op["owner"] == "[ANONIM]", "sahip anonimleştirilmedi"
    assert (op.get("owner_email") or "") == "", "e-posta temizlenmedi"
    assert (op.get("vet_contact") or "") == "", "vet iletişim temizlenmedi"
    assert op.get("anonymized") in (1, True), "anonymized bayrağı set edilmedi"

    npat = db.get_patient(new)
    assert npat["name"] == "Yeni Hasta", "aktif hastanın PII'si korunmalı"
    assert npat.get("anonymized") in (0, None, False)

    # Arama indeksi: eski ad/sahip token'ları silinmeli → eski adla BULUNAMAZ (KVKK gereği)
    hits = db.search_patients("Eski Hasta")
    assert all(p["id"] != old for p in hits), "anonimleştirilen hasta eski adıyla hâlâ aranabiliyor (KVKK ihlali)"
    # Aktif hasta hâlâ aranabilir
    hits2 = db.search_patients("Yeni Hasta")
    assert any(p["id"] == new for p in hits2), "aktif hasta aranamıyor (indeks bozuldu)"


def test_anonymize_is_idempotent(temp_app_data):
    """İkinci çağrı zaten-anonim hastayı TEKRAR işlemez (COALESCE(anonymized,0)=0 filtresi)."""
    db = _pdb(temp_app_data)
    pid = db.add_patient({"name": "X Hasta", "owner": "Y Sahip"})
    _set_last_treatment(db, pid, datetime.now() - timedelta(days=2200))
    first = db.anonymize_inactive_patients(1825)
    assert pid in first
    second = db.anonymize_inactive_patients(1825)
    assert pid not in second, "zaten-anonim hasta ikinci kez işlenmemeli (idempotent)"


def test_recent_patient_never_anonymized(temp_app_data):
    """Muafiyet-yok ama EŞİK var: yeni kayıt (created_at=now, last_treatment yok) anonimleştirilMEZ."""
    db = _pdb(temp_app_data)
    pid = db.add_patient({"name": "Taze", "owner": "Kayit"})  # last_treatment_at yok → created_at=now
    anon = db.anonymize_inactive_patients(1825)
    assert pid not in anon
    assert db.get_patient(pid)["name"] == "Taze"
