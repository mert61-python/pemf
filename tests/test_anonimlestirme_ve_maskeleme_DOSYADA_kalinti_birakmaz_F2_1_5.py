# -*- coding: utf-8 -*-
"""F2-1.5 (2-F incelemesi · A1) — anonimleştirme ve PII maskeleme UPDATE'lerinden sonra eski ad / sahip / e-posta DB DOSYASINDA (.db + -wal)
okunabilir kalmaz (Y13 · KVKK: anonimleştirme geri döndürülemez olmalı).

ÖLÇÜLEN KUSUR: `secure_delete=ON` yeni sayfa sürümünü sıfırlar ama WAL kipinde ESKİ sayfa sürümü bir sonraki denetim noktasına dek ANA dosyada,
önceki yazımların çerçeveleri (ör. kalıcı bekleyen listesinin düz ad/sahip/e-posta JSON'u) -wal dosyasında durur. D2.29 tekil silmeden sonra
`wal_checkpoint(TRUNCATE)` ekledi; anonimleştirme turu ve maskeleme eklemedi. Ölçüldü (`_inceleme\\K1\\sonda_wal_kalinti.py`): onaylı turdan
sonra SQL'de ad 0 iken tedavi DB'sinin `.db`'sinde 14, `-wal`'ında 4 eşleşme; hasta DB'sinin `.db`'sinde eski ŞİFRELİ ad/sahip/e-posta
(cihaz anahtarıyla `_decrypt_field` → 'Kalinti Pamuk-9917', 'Kalinti Sahip-9917', 'kalinti9917@ornek.com'); maskelemeden sonra `.db`'de 3.
Hasta DB'sinde dönemsel TRUNCATE denetim noktası YOK (yalnız silme sonrası) → kalıntı oto denetim noktasına (1000 sayfa) dek haftalarca durabilir.
Gerçekçi durum: veriler önce denetim noktasıyla ana dosyaya yazılır (uzun ömürlü DB), sonra GERÇEK tur.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

AD = "Kalinti Pamuk-F215"
SAHIP = "Kalinti Sahip-F215"
EPOSTA = "kalintif215@ornek.com"


def _say(yol, igneler) -> dict:
    p = Path(yol)
    out = {}
    for ek in ("", "-wal"):
        f = p.with_name(p.name + ek)
        b = f.read_bytes() if f.exists() else b""
        out[ek or ".db"] = sum(b.count(i) for i in igneler)
    return out


@pytest.fixture
def o(tmp_path, monkeypatch):
    from database.patient_database import PatientDatabase
    from database.treatment_history_db import TreatmentHistoryDB

    monkeypatch.delenv("PEMF_MASK_HISTORY_PII", raising=False)
    monkeypatch.delenv("PEMF_ENCRYPT_AT_REST", raising=False)
    pdb = PatientDatabase(str(tmp_path / "patients.db"))
    tdb = TreatmentHistoryDB(tmp_path / "gecmis")
    assert tdb.at_rest_encrypted is False, "aparat: kapı ŞİFRESİZ kurulumu ölçer (Y13)"
    try:
        yield pdb, tdb
    finally:
        tdb.close_connections()


def _denetim_noktasi(*dbs):
    for db in dbs:
        with db._get_connection() as c:
            c.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()


def test_KRITIK_anonimlestirme_sonrasi_ad_tedavi_ve_hasta_DB_DOSYASINDA_yok(o):
    """MUTASYON: tur sonundaki denetim noktası kaldırılır → KIRMIZI."""
    from services import kvkk_anonimlestirme as kv

    pdb, tdb = o
    pid = pdb.add_patient({"name": AD, "owner": SAHIP, "owner_email": EPOSTA})
    with pdb._get_connection() as c:
        c.execute(
            "UPDATE patients SET last_treatment_at=? WHERE id=?",
            ((datetime.now() - timedelta(days=2200)).isoformat(), pid),
        )
        c.commit()
        saklanan = [
            v for v in c.execute("SELECT name, owner, owner_email FROM patients WHERE id=?", (pid,)).fetchone() if v
        ]
    tpid = tdb.upsert_patient({"name": AD, "patient_uuid": pid, "owner_email": EPOSTA})
    sid = int(tdb.start_session(treatment_mode="Manuel", patient_name=AD, operator_name="Dr F215"))
    tdb.set_session_meta(sid, started_epoch=time.time(), patient_id=tpid)
    tdb.set_session_parameter(sid, "patient_owner_email", EPOSTA, "")
    tdb.end_session(sid, patient_notes=f"{AD} not " + "x" * 300, duration_minutes=5)
    tdb.add_ai_analysis(module_id="m", patient_name=AD, result_summary=f"{AD} bulgu " + "y" * 300, patient_uuid=pid)
    _denetim_noktasi(tdb, pdb)  # uzun ömürlü DB: veriler ana dosyada
    for i in range(5):
        tdb.record_session_event(sid, "seans_notu", {"i": i})
    ig_t = [AD.encode(), SAHIP.encode(), EPOSTA.encode(), json.dumps(AD)[1:-1].encode()]
    ig_p = [str(s).encode() for s in saklanan]
    assert sum(_say(tdb.db_path, ig_t).values()) and sum(_say(pdb.db_file, ig_p).values()), (
        "aparat KÖR: önce dosyada yok"
    )
    tdb.anonim_onayi_yaz(gun=kv.ESIK_GUN, sayi=1, kim="dr@k.vet")
    assert kv.tur(pdb, tdb)["anonimlestirilen"] == 1
    with tdb._get_connection() as c:
        assert c.execute("SELECT COUNT(*) FROM treatment_sessions WHERE patient_name=?", (AD,)).fetchone()[0] == 0
    assert _say(tdb.db_path, ig_t) == {".db": 0, "-wal": 0}, (
        f"anonim hastanın adı tedavi DB DOSYASINDA: {_say(tdb.db_path, ig_t)}"
    )
    assert _say(pdb.db_file, ig_p) == {".db": 0, "-wal": 0}, (
        f"anonim hastanın ŞİFRELİ kimliği (cihaz anahtarıyla çözülür) hasta DB DOSYASINDA: {_say(pdb.db_file, ig_p)}"
    )


def test_KRITIK_PII_maskeleme_sonrasi_ad_DOSYADA_yok(o):
    """MUTASYON: maskeleme sonrası denetim noktası kaldırılır → KIRMIZI."""
    _, tdb = o
    ad = "Maske Boncuk-F215"
    sid = int(tdb.start_session(treatment_mode="Manuel", patient_name=ad, operator_name="Dr Maske-F215"))
    tdb.end_session(sid, patient_notes=f"{ad} not " + "z" * 300, duration_minutes=5)
    with tdb._get_connection() as c:
        c.execute(
            "UPDATE treatment_sessions SET session_date=? WHERE id=?",
            ((datetime.now() - timedelta(days=400)).strftime("%Y-%m-%d"), sid),
        )
        c.commit()
    _denetim_noktasi(tdb)
    ig = [ad.encode(), b"Dr Maske-F215"]
    assert sum(_say(tdb.db_path, ig).values()), "aparat KÖR"
    tdb.pii_onayla(gun=365, sayi=1, kim="dr@k.vet")
    r = tdb.apply_data_retention_policy(
        sensor_retain_days=0, event_retain_days=0, dead_outbox_retain_days=0, pii_retain_days=365, dose_retain_days=0
    )
    assert r["sessions_pii_redacted"] == 1, r
    assert _say(tdb.db_path, ig) == {".db": 0, "-wal": 0}, f"maskelenen ad DOSYADA okunabilir: {_say(tdb.db_path, ig)}"
