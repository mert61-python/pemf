# -*- coding: utf-8 -*-
"""F2-1.4 (2-F incelemesi · A1) — hastaya KİMLİKLE bağlanmamış (yalnız adla açılmış) seans ve ayna satırı da anonimleşir (Y125 kuralıyla).

ÖLÇÜLEN KUSUR: `/api/session/start` istemci hasta kimliği GÖNDERMEDEN ad gönderdiğinde (arayüz: `ControlScreen` `patientName =
selectedPatient?.name || snapshot.patient?.name` — seçili hasta yokken anlık görüntüdeki ad; eski / LAN istemcisi; Aşama-2 öncesi seanslar)
`_persist_session_start` → `upsert_patient({"name": ad, "patient_uuid": None})` KİMLİKSİZ bir ayna satırı açar ve seans ona bağlanır.
`anonymize_patients_by_uuid` yalnız `patient_uuid` ile eşleşen ayna satırının seanslarına ulaşır → 5 yıl inaktif hasta onayla anonimleşince
bu seansın `patient_name` / `patient_notes`'u ve kimliksiz ayna satırının adı SÜRESİZ kalıyordu (ölçüldü: `_inceleme\\K1\\sonda_k1_zincir.py`).
Aynı DB'de kimliksiz ESKİ AI kayıtları (Y125) ad TEK hastaya çözülüyorsa anonimleşiyor — seanslar için bu kural yoktu (asimetri).
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta

import pytest

HEKIM = "dr.f214@klinik.vet"


@pytest.fixture
def o(tmp_path, monkeypatch):
    from database.patient_database import PatientDatabase
    from database.treatment_history_db import TreatmentHistoryDB

    monkeypatch.delenv("PEMF_MASK_HISTORY_PII", raising=False)
    monkeypatch.delenv("PEMF_ENCRYPT_AT_REST", raising=False)
    pdb = PatientDatabase(str(tmp_path / "patients.db"))
    tdb = TreatmentHistoryDB(tmp_path / "gecmis")
    try:
        yield pdb, tdb
    finally:
        tdb.close_connections()


def _hasta(pdb, ad, gun=2200):
    pid = pdb.add_patient({"name": ad, "owner": f"Sahip {ad}", "owner_email": "f214@ornek.com"})
    with pdb._get_connection() as c:
        c.execute(
            "UPDATE patients SET last_treatment_at=? WHERE id=?",
            ((datetime.now() - timedelta(days=gun)).isoformat(), pid),
        )
        c.commit()
    return pid


def _seans(tdb, ad, pid):
    """`_persist_session_start` sırası; `pid` boşsa istemci kimlik göndermedi (yalnız ad)."""
    tpid = tdb.upsert_patient({"name": ad, "patient_uuid": pid or None, "owner_email": None})
    sid = int(
        tdb.start_session(treatment_mode="Manuel", patient_name=ad, operator_name="Dr F214", operator_email=HEKIM)
    )
    tdb.set_session_meta(sid, started_epoch=time.time(), patient_id=tpid)
    tdb.set_session_parameter(sid, "patient_veteriner", "Dr F214", "")
    tdb.end_session(sid, patient_notes=f"{ad} kontrol", duration_minutes=5)
    return sid


def _adli(tdb, ad) -> dict:
    kac = json.dumps(ad)[1:-1]
    n: dict = {}
    with tdb._get_connection() as c:
        for (t,) in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
            im = c.execute(f'SELECT * FROM "{t}"')
            kol = [k[0] for k in im.description]
            for s in im.fetchall():
                for k, d in zip(kol, tuple(s)):
                    if isinstance(d, str) and (ad in d or kac in d):
                        n[f"{t}.{k}"] = n.get(f"{t}.{k}", 0) + 1
    return n


def test_KRITIK_yalniz_ADLA_acilmis_seans_ve_kimliksiz_ayna_ANONIMLESIR_hekim_KALIR(o):
    """MUTASYON: kimliksiz ayna / seans kolu silinir → KIRMIZI."""
    from services import kvkk_anonimlestirme as kv

    pdb, tdb = o
    ad = "Işıl Kimliksiz-F214"
    pid = _hasta(pdb, ad)
    _seans(tdb, ad, pid)  # kimlikli seans
    sid_k = _seans(tdb, ad, "")  # istemci yalnız ad gönderdi
    with tdb._get_connection() as c:
        assert c.execute("SELECT patient_id FROM treatment_sessions WHERE id=?", (sid_k,)).fetchone()[0] is not None
    tdb.anonim_onayi_yaz(gun=kv.ESIK_GUN, sayi=1, kim=HEKIM)
    assert kv.tur(pdb, tdb)["anonimlestirilen"] == 1
    assert not _adli(tdb, ad), f"yalnız adla açılmış seans / kimliksiz ayna adı SÜRESİZ kaldı: {_adli(tdb, ad)}"
    with tdb._get_connection() as c:
        hekim = c.execute(
            "SELECT operator_name, operator_email FROM treatment_sessions WHERE id=?", (sid_k,)
        ).fetchone()
        vet = c.execute(
            "SELECT parameter_value FROM session_parameters WHERE session_id=? AND parameter_name='patient_veteriner'",
            (sid_k,),
        ).fetchone()
    assert tuple(hekim) == ("Dr F214", HEKIM) and vet[0] == "Dr F214", "A-27: hekim atfı silindi"


def test_KRITIK_hastaya_HIC_baglanmamis_seans_ANONIMLESIR(o):
    """`upsert_patient` düşerse (`_pid=None`) seans `patient_id` NULL kalır, `patient_name` adı taşır."""
    from services import kvkk_anonimlestirme as kv

    pdb, tdb = o
    ad = "Boncuk Bagsiz-F214"
    pid = _hasta(pdb, ad)
    _seans(tdb, ad, pid)
    sid = int(
        tdb.start_session(treatment_mode="Manuel", patient_name=ad, operator_name="Dr F214", operator_email=HEKIM)
    )
    tdb.end_session(sid, patient_notes="not", duration_minutes=5)
    tdb.anonim_onayi_yaz(gun=kv.ESIK_GUN, sayi=1, kim=HEKIM)
    kv.tur(pdb, tdb)
    assert not _adli(tdb, ad), f"hastaya bağlanmamış seansın adı SÜRESİZ kaldı: {_adli(tdb, ad)}"


def test_KARSIT_ayni_adli_AKTIF_hasta_varken_kimliksiz_seans_DOKUNULMAZ(o):
    """Ad belirsiz (aynı adlı AKTİF hasta var) → kimliksiz seans kimin olduğu bilinemez, dokunulmaz (Y125 kuralı)."""
    from services import kvkk_anonimlestirme as kv

    pdb, tdb = o
    ad = "Pamuk Belirsiz-F214"
    pid = _hasta(pdb, ad)
    _hasta(pdb, ad, gun=10)  # aynı adlı aktif hasta
    _seans(tdb, ad, pid)
    sid_k = _seans(tdb, ad, "")
    tdb.anonim_onayi_yaz(gun=kv.ESIK_GUN, sayi=1, kim=HEKIM)
    assert kv.tur(pdb, tdb)["anonimlestirilen"] == 1
    with tdb._get_connection() as c:
        assert c.execute("SELECT patient_name FROM treatment_sessions WHERE id=?", (sid_k,)).fetchone()[0] == ad
