# -*- coding: utf-8 -*-
"""D2.03 (B-3.92) — `anonymize_patients_by_uuid` (tedavi-DB'deki hasta KOPYASININ anonimleştirmesi) davranışla ölçülür.

ÖLÇÜLEN KÖRLÜK: kanonik hasta DB'sinin anonimleştirmesini `tests/test_kvkk_anonymization.py` uçtan uca kilitliyor; ama 5 yıl inaktif
hastanın TEDAVİ GEÇMİŞİNDEKİ ad kopyalarını silen bu metot hiçbir testte KOŞTURULMUYORDU (yalnız bir docstring'de anılıyordu) →
seans/parametre UPDATE'leri no-op yapılınca süit yeşil kalıyordu; anonimleştirilen hastanın adı seans geçmişinde, PDF'te ve aramada
süresiz kalırdı (KVKK "unutulma hakkı"). `thdb_pii.py` baş yorumu bu metodun kapısını yanlış dosyaya bağlıyordu.

Kapı: tedavi DB'sine hasta ve seans ürünün GERÇEK seans-başlatma zinciriyle yazılır (`api_server._persist_session_start`'ın yaptığı
gibi: `upsert_patient` ayna satırı → `start_session` → `set_session_meta(patient_id)` → `set_session_parameter(patient_owner_email)`);
`anonymize_patients_by_uuid([U])` sonrası hasta kopyası, seans satırı ve seans parametrelerinde eski ad / sahip / e-posta HAM SQL ile
aranır ve `get_session_history` ile de bakılır. KARŞIT: başka kimlikli hastanın kopyası ve seansı DOKUNULMADAN kalır (aşırı silme yok).
⚠️ Hekim atfı (A-27) bu kapının konusu değil — D2.54 kilitler.
"""

from __future__ import annotations

import pytest

ESKI_AD = "Pamuk Benzersiz-7731"
ESKI_SAHIP = "Ayse Sahibi-7731"
ESKI_EPOSTA = "sahip7731@ornek.com"
DIGER_AD = "Boncuk Korunan-5520"


@pytest.fixture
def db(tmp_path, monkeypatch):
    from database.treatment_history_db import TreatmentHistoryDB

    monkeypatch.delenv("PEMF_MASK_HISTORY_PII", raising=False)
    d = TreatmentHistoryDB(tmp_path)
    try:
        yield d
    finally:
        d.close_connections()


def _seans(db, ad: str, kimlik: str, eposta: str, sahip: str) -> int:
    """`api_server._persist_session_start` zinciri: ayna hasta satırı + seans + FK + sahip e-postası parametresi."""
    pid = db.upsert_patient({"name": ad, "patient_uuid": kimlik, "owner_email": eposta, "owner_name": sahip})
    sid = int(db.start_session(treatment_mode="Manuel", patient_name=ad, operator_name="Dr Mehmet"))
    db.set_session_meta(sid, patient_id=pid)
    db.set_session_parameter(sid, "patient_owner_email", eposta, "")
    db.set_session_parameter(sid, "patient_name", ad, "")
    db.end_session(sid, duration_minutes=10)
    return sid


def _ham_metin(db, metin: str) -> list:
    """Hasta kopyası / seans / seans parametrelerinde metnin geçtiği (tablo, kolon) çiftleri — HAM SQL."""
    bulunan = []
    with db._get_connection() as c:
        for tablo in ("patients", "treatment_sessions", "session_parameters"):
            imlec = c.execute(f'SELECT * FROM "{tablo}"')
            kolonlar = [k[0] for k in imlec.description]
            for satir in imlec.fetchall():
                for kol, deger in zip(kolonlar, tuple(satir)):
                    if isinstance(deger, str) and metin in deger:
                        bulunan.append((tablo, kol))
    return sorted(set(bulunan))


def test_KRITIK_anonimlestirilen_hastanin_adi_SEANS_ve_PARAMETRELERDE_kalmaz(db):
    """MUTASYON: seans UPDATE'i ya da parametre UPDATE'i no-op → KIRMIZI."""
    sid = _seans(db, ESKI_AD, "uuid-eski-7731", ESKI_EPOSTA, ESKI_SAHIP)
    assert ("treatment_sessions", "patient_name") in _ham_metin(db, ESKI_AD), "aparat: ad seansa yazılmadı (kapı kör)"
    n = db.anonymize_patients_by_uuid(["uuid-eski-7731"])
    assert n == 1, f"hasta kopyası anonimleştirilmedi (dönüş {n})"
    for metin in (ESKI_AD, ESKI_SAHIP, ESKI_EPOSTA):
        assert _ham_metin(db, metin) == [], (
            f"{metin!r} anonimleştirmeden sonra tedavi DB'sinde duruyor: {_ham_metin(db, metin)}"
        )
    satir = next(h for h in db.get_session_history(limit=50) if h["id"] == sid)
    assert ESKI_AD not in str(satir.get("patient_name")), (
        f"seans geçmişi eski adı gösteriyor: {satir.get('patient_name')!r}"
    )


def test_KRITIK_hasta_KOPYASI_anonim(db):
    """MUTASYON: `patients` kopyasının UPDATE'i no-op → KIRMIZI (seans geçmişi JOIN'i adı oradan da okur)."""
    _seans(db, ESKI_AD, "uuid-eski-7731", ESKI_EPOSTA, ESKI_SAHIP)
    db.anonymize_patients_by_uuid(["uuid-eski-7731"])
    with db._get_connection() as c:
        ad, sahip, eposta = c.execute(
            "SELECT name, owner_name, owner_email FROM patients WHERE patient_uuid=?", ("uuid-eski-7731",)
        ).fetchone()
    assert (ad, sahip, eposta or "") == ("[ANONIM]", "[ANONIM]", ""), (ad, sahip, eposta)


def test_KARSIT_baska_hastanin_kopyasi_ve_seansi_DOKUNULMAZ(db):
    """Aşırı silme yok: yalnız verilen kimliğin hastası ve O hastanın seansları anonimleşir."""
    _seans(db, ESKI_AD, "uuid-eski-7731", ESKI_EPOSTA, ESKI_SAHIP)
    diger = _seans(db, DIGER_AD, "uuid-diger-5520", "diger5520@ornek.com", "Can Sahip-5520")
    db.anonymize_patients_by_uuid(["uuid-eski-7731"])
    assert ("treatment_sessions", "patient_name") in _ham_metin(db, DIGER_AD), "başka hastanın seansı anonimleşti"
    assert ("session_parameters", "parameter_value") in _ham_metin(db, "diger5520@ornek.com")
    assert ("patients", "name") in _ham_metin(db, DIGER_AD)
    satir = next(h for h in db.get_session_history(limit=50) if h["id"] == diger)
    assert satir.get("patient_name") == DIGER_AD


def test_KARSIT_bos_ya_da_bilinmeyen_kimlik_hicbir_seye_dokunmaz(db):
    _seans(db, ESKI_AD, "uuid-eski-7731", ESKI_EPOSTA, ESKI_SAHIP)
    assert db.anonymize_patients_by_uuid([]) == 0
    assert db.anonymize_patients_by_uuid(["", None, "uuid-yok"]) == 0
    assert ("treatment_sessions", "patient_name") in _ham_metin(db, ESKI_AD)
