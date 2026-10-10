# -*- coding: utf-8 -*-
"""2-C incelemesi §9 #9 — `upsert_patient` tedavi DB'sindeki hasta ayna satırının GÖNDERİLMEYEN alanlarını NULL'lamaz.

ÖLÇÜLEN KUSUR (A1, 2-C öncesi; 2-F'de yeniden ölçüldü): UPDATE dalı `species/breed/age/weight_kg/owner_name/vet_contact/veteriner/notes`
alanlarını gelen değerle KOŞULSUZ yazıyordu. Üretimdeki ÜÇ çağıranın üçü de (seans başlangıcı `api_server`, AI Pro seansı, uykudaki
`SessionManager`) yalnız `name` / `patient_uuid` / `owner_email` gönderir → her seans başlangıcı (cihaz taşımasıyla tam gelmiş) ayna
satırının tür, ırk, yaş, kilo, sahip adı, veteriner ve notunu siliyordu. Kural: `None` = "gönderilmedi" → mevcut değer KALIR.
GERÇEK: TreatmentHistoryDB (sentetik, tmp, şifresiz — PII alanları `_redact_pii` ile maskeli yazılır; ölçüm DEĞER korunuyor mu).
"""

from __future__ import annotations

import pytest

ALANLAR = ("species", "breed", "age", "weight_kg", "owner_name", "vet_contact", "veteriner", "notes")


@pytest.fixture
def db(tmp_path, monkeypatch):
    from database.treatment_history_db import TreatmentHistoryDB

    monkeypatch.delenv("PEMF_MASK_HISTORY_PII", raising=False)
    d = TreatmentHistoryDB(tmp_path / "gecmis")
    try:
        yield d
    finally:
        d.close_connections()


def _satir(db, pid):
    # ⚠️ havuz bağlantısının row_factory'si DEĞİŞTİRİLMEZ (ürün `row['id']` okur — havuz kirlenmesi sahte kırmızı üretir).
    with db._get_connection() as c:
        return dict(
            zip(ALANLAR, tuple(c.execute(f"SELECT {', '.join(ALANLAR)} FROM patients WHERE id=?", (pid,)).fetchone()))
        )


TAM = {
    "species": "kedi",
    "breed": "tekir",
    "age": "4",
    "weight_kg": 4.2,
    "vet_contact": "0555",
    "veteriner": "Dr. Ayse",
    "notes": "alerjik",
}


def test_KRITIK_kimliksiz_ayna_satiri_KISMI_upsertte_alanlarini_KORUR(db):
    """Seans başlangıcının gönderdiği kısmi kayıt (yalnız ad) kimliksiz ayna satırına bağlanır — alanlar KALIR.
    MUTASYON: UPDATE'te bir alanın COALESCE'i kaldırılır → KIRMIZI."""
    pid = db.upsert_patient({"name": "Mia", **TAM})
    once = _satir(db, pid)
    assert once["species"] == "kedi" and once["breed"] == "tekir", f"aparat: tam kayıt yazılmadı {once}"
    assert db.upsert_patient({"name": "Mia", "patient_uuid": None, "owner_email": None}) == pid
    sonra = _satir(db, pid)
    silinen = [a for a in ALANLAR if once[a] is not None and sonra[a] is None]
    assert not silinen, f"kısmi upsert gönderilmeyen alanları NULL'ladı: {silinen}"


def test_KRITIK_kimlikli_ayna_satiri_seans_baslangicinda_alanlarini_KORUR(db):
    pid = db.upsert_patient({"name": "Pamuk", "patient_uuid": "uuid-c29", "owner_name": "Ali", **TAM})
    once = _satir(db, pid)
    assert db.upsert_patient({"name": "Pamuk", "patient_uuid": "uuid-c29", "owner_email": "a@b.com"}) == pid
    sonra = _satir(db, pid)
    silinen = [a for a in ALANLAR if once[a] is not None and sonra[a] is None]
    assert not silinen, f"kimlikli ayna satırında gönderilmeyen alanlar NULL'landı: {silinen}"


def test_KARSIT_GONDERILEN_alan_GUNCELLENIR(db):
    pid = db.upsert_patient({"name": "Boncuk", "patient_uuid": "uuid-k", **TAM})
    db.upsert_patient({"name": "Boncuk", "patient_uuid": "uuid-k", "species": "kopek", "breed": "golden"})
    s = _satir(db, pid)
    assert (s["species"], s["breed"], s["age"]) == ("kopek", "golden", "4"), s
