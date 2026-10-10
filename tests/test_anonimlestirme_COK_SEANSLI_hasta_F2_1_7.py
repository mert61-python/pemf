# -*- coding: utf-8 -*-
"""F2-1.7 (2-F incelemesi · A1) — anonimleştirme kapıları ÇOK SEANSLI hastayı ölçmeli (KÖR KAPI).

ÖLÇÜLEN KÖRLÜK: D2.03 / D2.54 / D2.59 / Y119 / test_kvkk_anonymization kapılarının HEPSİNDE hasta başına TEK seans var. `anonymize_patients_by_uuid`
seans UPDATE'i ya da parametre UPDATE'i yalnız İLK seansa uygulanınca (`WHERE id IN (SELECT MIN(id) …)`) beş dosyanın 28 testi YEŞİL kaldı
(ölçüldü: `_inceleme\\kayit\\K3_mutasyon.txt`). Sahada inaktif hastanın onlarca seansı olur; ikinci seansından itibaren ad kalırdı.
Bu kapı GERÇEK zincirle (`_persist_session_start` sırası: ayna `upsert_patient(ad, uuid, owner_email)` → `start_session` →
`set_session_meta(patient_id)` → `set_session_parameter(patient_owner_email)`) ve uykudaki SessionManager'la (olay + outbox yükü) hasta başına
ÜÇ seans yazar, onaylı GERÇEK tur sonrası HER seansı ölçer.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta

import pytest

AD = "Pamuk Coklu-F217"
EPOSTA = "coklu217@ornek.com"


@pytest.fixture
def o(tmp_path, monkeypatch):
    from database import session_manager as smod
    from database.patient_database import PatientDatabase
    from database.treatment_history_db import TreatmentHistoryDB

    monkeypatch.delenv("PEMF_MASK_HISTORY_PII", raising=False)
    monkeypatch.delenv("PEMF_ENCRYPT_AT_REST", raising=False)
    pdb = PatientDatabase(str(tmp_path / "patients.db"))
    tdb = TreatmentHistoryDB(tmp_path / "gecmis")
    monkeypatch.setattr(smod, "get_treatment_db", lambda *_a, **_k: tdb)
    try:
        yield pdb, tdb, smod.SessionManager(tmp_path / "gecmis")
    finally:
        tdb.close_connections()


def test_KRITIK_hastanin_TUM_seanslari_parametreleri_ve_yukleri_anonimlesir(o):
    """MUTASYON: seans / parametre / yük temizliği yalnız ilk seansa → KIRMIZI."""
    from services import kvkk_anonimlestirme as kv

    pdb, tdb, sm = o
    pid = pdb.add_patient({"name": AD, "owner": "Sahip F217", "owner_email": EPOSTA})
    with pdb._get_connection() as c:
        c.execute(
            "UPDATE patients SET last_treatment_at=? WHERE id=?",
            ((datetime.now() - timedelta(days=2200)).isoformat(), pid),
        )
        c.commit()
    sidler = []
    for i in range(3):
        tpid = tdb.upsert_patient({"name": AD, "patient_uuid": pid, "owner_email": EPOSTA})
        sid = int(tdb.start_session(treatment_mode="Manuel", patient_name=AD, operator_name="Dr F217"))
        tdb.set_session_meta(sid, started_epoch=time.time(), patient_id=tpid)
        tdb.set_session_parameter(sid, "patient_owner_email", EPOSTA, "")
        tdb.end_session(sid, patient_notes=f"{AD} kontrol {i}", duration_minutes=5)
        sidler.append(sid)
    for _ in range(2):  # SessionManager: olay + outbox yükünde ad (D2.59)
        assert sm.start_session("Manuel", operator_name="Dr F217", patient_name=AD, patient_uuid=pid)
        assert sm.end_session(actual_duration=5.0)
    tdb.anonim_onayi_yaz(gun=kv.ESIK_GUN, sayi=1, kim="dr@k.vet")
    assert kv.tur(pdb, tdb)["anonimlestirilen"] == 1
    kac = json.dumps(AD)[1:-1]
    with tdb._get_connection() as c:
        seanslar = c.execute("SELECT id, patient_name, patient_notes FROM treatment_sessions ORDER BY id").fetchall()
        param = c.execute(
            "SELECT session_id, parameter_value FROM session_parameters WHERE parameter_name='patient_owner_email'"
        ).fetchall()
        yukler = [r[0] for r in c.execute("SELECT payload FROM session_events").fetchall()]
        yukler += [r[0] for r in c.execute("SELECT payload FROM outbox_messages").fetchall()]
    assert len(seanslar) == 5 and len(yukler) >= 8, f"aparat: {len(seanslar)} seans, {len(yukler)} yük"
    kalan = [tuple(s) for s in seanslar if AD in str(s[1]) + str(s[2])]
    assert not kalan, f"anonimleştirilen hastanın şu seanslarında ad KALDI: {kalan}"
    assert all(v == "[ANONIM]" for _, v in param) and len(param) == 3, (
        f"sahip e-postası kalan seans parametresi: {param}"
    )
    assert not [y for y in yukler if AD in y or kac in y], "olay / outbox yükünde ad kaldı"
