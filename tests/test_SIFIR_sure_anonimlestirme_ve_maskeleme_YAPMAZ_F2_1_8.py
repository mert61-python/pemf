# -*- coding: utf-8 -*-
"""F2-1.8 (2-F incelemesi · A1) — D2.49 kuralı ("süre 0/negatif → HİÇBİR ŞEY") geri dönüşsüz ANONİMLEŞTİRME ve MASKELEME işlevlerinde de geçerli.

ÖLÇÜLEN KUSUR: D2.49 `max(1, …)` kalıbını yalnız dört `purge_old_*` işlevinden kaldırdı. Aynı kalıp `patient_database.anonymize_inactive_patients`
(`:951`), `thdb_pii.redact_old_session_pii` (`:176`) ve `redaksiyon_bekleyen_sayisi` (`:66`) içinde KALDI: süre 0 ya da negatif gelirse 1 GÜNLÜK
kesime düşer → dünden önce tedavi görmüş TÜM hastalar geri dönüşsüz anonimleşir / tüm seanslar maskelenir. Bugün çağıranlar 0'ı dışarıda
eliyor (`tur` sabit 1825 + `anonimlestirilecek_hastalar` 0'da boş; `apply_data_retention_policy` `> 0`) — D2.49'un gerekçesiyle AYNI gizli
risk ("çağıran '0 = kapalı' kuralını bir kez unutursa"; 2026-08-17 doz olayı ve B2-1.6'da iki kez oldu).
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest


@pytest.fixture
def o(tmp_path, monkeypatch):
    from database.patient_database import PatientDatabase
    from database.treatment_history_db import TreatmentHistoryDB

    monkeypatch.delenv("PEMF_MASK_HISTORY_PII", raising=False)
    pdb = PatientDatabase(str(tmp_path / "patients.db"))
    tdb = TreatmentHistoryDB(tmp_path / "gecmis")
    try:
        yield pdb, tdb
    finally:
        tdb.close_connections()


@pytest.mark.parametrize("gun", [0, -5])
def test_KRITIK_anonymize_inactive_patients_SIFIR_ve_negatifte_HICBIR_hastaya_dokunmaz(o, gun):
    pdb, _ = o
    pid = pdb.add_patient({"name": "Pamuk Sifir-F218", "owner": "Sahip", "owner_email": "s@ornek.com"})
    with pdb._get_connection() as c:
        c.execute(
            "UPDATE patients SET last_treatment_at=? WHERE id=?",
            ((datetime.now() - timedelta(days=30)).isoformat(), pid),
        )
        c.commit()
    assert pdb.anonymize_inactive_patients(gun) == []
    assert pdb.get_patient(pid)["name"] == "Pamuk Sifir-F218", (
        f"süre {gun} iken 30 gün önce tedavi gören hasta ANONİMLEŞTİ"
    )


@pytest.mark.parametrize("gun", [0, -5])
def test_KRITIK_redact_old_session_pii_SIFIR_ve_negatifte_HICBIR_seansi_maskelemez(o, gun):
    _, tdb = o
    sid = int(tdb.start_session(treatment_mode="Manuel", patient_name="Boncuk Sifir-F218", operator_name="Dr"))
    tdb.end_session(sid, duration_minutes=5)
    with tdb._get_connection() as c:
        c.execute(
            "UPDATE treatment_sessions SET session_date=? WHERE id=?",
            ((datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d"), sid),
        )
        c.commit()
    assert tdb.redaksiyon_bekleyen_sayisi(gun) == 0, "süre 0/negatif (kapalı) iken bekleyen sayıldı"
    # SON (Y208): rapor olay sayacını da taşır (`events_redacted`) — sıfır / negatif sürede o da 0.
    assert tdb.redact_old_session_pii(gun) == {"sessions_redacted": 0, "parameters_redacted": 0, "events_redacted": 0}
    with tdb._get_connection() as c:
        assert (
            c.execute("SELECT patient_name FROM treatment_sessions WHERE id=?", (sid,)).fetchone()[0]
            == "Boncuk Sifir-F218"
        )


def test_KARSIT_pozitif_sure_yine_CALISIR(o):
    pdb, tdb = o
    pid = pdb.add_patient({"name": "Eski F218", "owner": "S", "owner_email": "e@ornek.com"})
    with pdb._get_connection() as c:
        c.execute(
            "UPDATE patients SET last_treatment_at=? WHERE id=?",
            ((datetime.now() - timedelta(days=30)).isoformat(), pid),
        )
        c.commit()
    assert pdb.anonymize_inactive_patients(7) == [pid]
