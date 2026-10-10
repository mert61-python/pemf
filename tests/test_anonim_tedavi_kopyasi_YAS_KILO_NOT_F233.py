# -*- coding: utf-8 -*-
"""F2-3.3 (2-F incelemesi A3, K2 · D2.06 / A-38 / D2.54) — Legal §6 'anonim': "hastanın adı, sahibinin adı, iletişim bilgileri, yaşı ve
kilosu ... anonimleştirilir". Tedavi DB'sindeki hasta KOPYASI (ayna satırı — cihaz taşımasıyla tam gelir, C2-9 kapısının aparatı da böyle
kurar) ve eski seans parametreleri (`patient_age` / `patient_weight` — geçmiş ekranı JOIN'i ve PDF okur) anonimleşiyor mu?
GERÇEK `PatientDatabase` + GERÇEK `TreatmentHistoryDB` (geçici dizin, şifresiz — `PEMF_MASK_HISTORY_PII` tanımsız = değerler gerçek yazılır),
GERÇEK `services.kvkk_anonimlestirme.tur` (onaylı). Ölçüm: ham SQL + ham bayt (.db + -wal + -shm, kaçışlı biçim dahil).
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

AD = "Pamuk Sonda-7731"
SAHIP = "Sahip Sondaoglu-7731"
EPOSTA = "sonda7731@ornek.test"
TEL = "0555 773 1773"
HEKIM = "Dr Hekim Sonda"
NOT = f"Sahibi {SAHIP} ({TEL}) - alerjik"


@pytest.fixture
def o(tmp_path, monkeypatch):
    from database.patient_database import PatientDatabase
    from database.treatment_history_db import TreatmentHistoryDB

    monkeypatch.delenv("PEMF_MASK_HISTORY_PII", raising=False)
    pdb = PatientDatabase(str(tmp_path / "patients.db"))
    tdb = TreatmentHistoryDB(tmp_path / "gecmis")
    try:
        yield type("O", (), {"pdb": pdb, "tdb": tdb, "kok": tmp_path / "gecmis"})
    finally:
        tdb.close_connections()


def _kur(o):
    pid = o.pdb.add_patient(
        {
            "name": AD,
            "owner": SAHIP,
            "owner_email": EPOSTA,
            "vet_contact": TEL,
            "age": "7",
            "weight": "12.5",
            "species": "kedi",
        }
    )
    with o.pdb._get_connection() as c:
        c.execute(
            "UPDATE patients SET last_treatment_at=? WHERE id=?",
            ((datetime.now() - timedelta(days=2200)).isoformat(), pid),
        )
        c.commit()
    t = o.tdb
    # Ayna satırı TAM (cihaz taşıması / eski sürüm) — C2-9 kapısının `TAM` kurulumu ile aynı alanlar.
    tpid = t.upsert_patient(
        {
            "name": AD,
            "patient_uuid": pid,
            "owner_name": SAHIP,
            "owner_email": EPOSTA,
            "species": "kedi",
            "breed": "tekir",
            "age": "7",
            "weight_kg": 12.5,
            "vet_contact": TEL,
            "veteriner": HEKIM,
            "notes": NOT,
        }
    )
    sid = int(
        t.start_session(treatment_mode="Manuel", patient_name=AD, operator_name=HEKIM, operator_email="dr@klinik.test")
    )
    t.set_session_meta(sid, patient_id=tpid)
    for ad, deger in (("patient_age", "7"), ("patient_weight", "12.5"), ("patient_species", "kedi")):
        t.set_session_parameter(sid, ad, deger, "")  # geçmiş JOIN'i + PDF bu adları okur (eski sürüm / taşıma)
    t.end_session(sid, duration_minutes=10)
    return pid, tpid, sid


def _ayna(o, tpid):
    with o.tdb._get_connection() as c:
        r = c.execute(
            "SELECT name, owner_name, age, weight_kg, notes, vet_contact FROM patients WHERE id=?", (tpid,)
        ).fetchone()
    return dict(zip(("name", "owner_name", "age", "weight_kg", "notes", "vet_contact"), tuple(r)))


def _param(o, sid):
    with o.tdb._get_connection() as c:
        return dict(
            tuple(r)
            for r in c.execute(
                "SELECT parameter_name, parameter_value FROM session_parameters WHERE session_id=?", (sid,)
            )
        )


def _bayt_say(o, metin: str) -> int:
    o.tdb.close_connections()
    n = 0
    for p in o.kok.glob("*.db*"):
        b = p.read_bytes()
        for bicim in {metin.encode("utf-8"), json.dumps(metin)[1:-1].encode("utf-8")}:
            n += b.count(bicim)
    return n


def test_SONDA_onayli_anonimlestirmede_TEDAVI_KOPYASI_ve_seans_parametrelerinde_YAS_KILO_SAHIP_KALMAZ(o):
    from services import kvkk_anonimlestirme as kv

    pid, tpid, sid = _kur(o)
    once_ayna, once_param = _ayna(o, tpid), _param(o, sid)
    # pozitif kontrol: okuyucu değerleri GÖRÜYOR
    assert once_ayna["age"] == "7" and SAHIP in (once_ayna["notes"] or ""), f"aparat: ayna kurulmadı {once_ayna}"
    assert once_param.get("patient_age") == "7", f"aparat: parametre yok {once_param}"
    o.tdb.anonim_onayi_yaz(gun=kv.ESIK_GUN, sayi=1, kim="dr@klinik.test")
    sonuc = kv.tur(o.pdb, o.tdb)
    assert sonuc["anonimlestirilen"] == 1 and sonuc["tedavi_bekleyen"] == 0, f"aparat: tur anonimleştirmedi {sonuc}"
    kanonik = o.pdb.get_patient(pid)
    sonra_ayna, sonra_param = _ayna(o, tpid), _param(o, sid)
    gecmis = [s for s in o.tdb.get_session_history(limit=10) if int(s.get("id")) == sid][0]
    sahip_bayt = _bayt_say(o, SAHIP)
    tel_bayt = _bayt_say(o, TEL)
    print(f"OLCUM kanonik age={kanonik.get('age')!r} weight={kanonik.get('weight')!r} name={kanonik.get('name')!r}")
    print(f"OLCUM ayna ONCE={once_ayna}")
    print(f"OLCUM ayna SONRA={sonra_ayna}")
    print(f"OLCUM param ONCE={once_param} SONRA={sonra_param}")
    print(
        f"OLCUM gecmis patient_age={gecmis.get('patient_age')!r} patient_weight={gecmis.get('patient_weight')!r} "
        f"patient_name={gecmis.get('patient_name')!r}"
    )
    print(f"OLCUM ham_bayt SAHIP={sahip_bayt} TEL={tel_bayt}")
    kalan = []
    if sonra_ayna["age"] not in (None, "", "[ANONIM]"):
        kalan.append(f"ayna.age={sonra_ayna['age']!r}")
    if sonra_ayna["weight_kg"] not in (None, ""):
        kalan.append(f"ayna.weight_kg={sonra_ayna['weight_kg']!r}")
    if SAHIP in (sonra_ayna["notes"] or "") or TEL in (sonra_ayna["notes"] or ""):
        kalan.append("ayna.notes sahip adı/telefon")
    for ad in ("patient_age", "patient_weight"):
        if sonra_param.get(ad) not in (None, "", "[ANONIM]"):
            kalan.append(f"param.{ad}={sonra_param.get(ad)!r}")
    if sahip_bayt or tel_bayt:
        kalan.append(f"ham bayt SAHIP={sahip_bayt} TEL={tel_bayt}")
    assert not kalan, (
        f"Legal §6 'yaşı ve kilosu ... sahibinin adı ... anonimleştirilir' — onaylı turdan sonra KALAN: {kalan}"
    )


def test_KRITIK_KIMLIKSIZ_ayna_satiri_da_YAS_KILO_NOT_kaybeder(o):
    """F2-1.4'ün kimliksiz ayna satırı (istemci yalnız ad gönderdi) aynı kuralla: yaş / kilo / serbest not anonimleşir (orkestratör eki).
    MUTASYON: kimliksiz ayna güncellemesi yalnız ad/sahip/iletişim (F2-1.4'ün ilk hâli) → KIRMIZI."""
    from services import kvkk_anonimlestirme as kv

    pid = o.pdb.add_patient({"name": AD, "owner": SAHIP, "owner_email": EPOSTA, "age": "7", "weight": "12.5"})
    with o.pdb._get_connection() as c:
        c.execute(
            "UPDATE patients SET last_treatment_at=? WHERE id=?",
            ((datetime.now() - timedelta(days=2200)).isoformat(), pid),
        )
        c.commit()
    kimliksiz = o.tdb.upsert_patient({"name": AD, "age": "7", "weight_kg": 12.5, "notes": NOT})  # kimlik YOK
    o.tdb.anonim_onayi_yaz(gun=kv.ESIK_GUN, sayi=1, kim="dr@klinik.test")
    assert kv.tur(o.pdb, o.tdb)["anonimlestirilen"] == 1
    sonra = _ayna(o, kimliksiz)
    assert sonra["name"] == "[ANONIM]", f"aparat: kimliksiz ayna anonimleşmedi (F2-1.4) {sonra}"
    assert sonra["age"] in (None, "") and sonra["weight_kg"] is None and SAHIP not in (sonra["notes"] or ""), (
        f"kimliksiz ayna satırında yaş/kilo/not KALDI: {sonra}"
    )
