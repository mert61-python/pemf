# -*- coding: utf-8 -*-
"""Y204 (S-D5.10) — anonimleştirmesi ONAYLANMIŞ hastanın kartı silinirse tedavi geçmişindeki ad / sahip / e-posta da `[ANONIM]` olur;
kalıcı bekleyen girdi ancak tedavi adımı UYGULANDIKTAN sonra düşer (adım düşerse girdi KALIR, sonraki turda yeniden denenir).

ÖLÇÜLEN (D5 C63 `2e5b62d4`, yardımcı E): kartı silinen hastanın girdisi listeden düşüyordu ama "tedavi geçmişine DOKUNULMAZ" kuralıyla
seans / ayna satırlarındaki ad, sahip ve e-posta SÜRESİZ kalıyordu ([SAHİBE] S-D5.10). SAHİP KARARI Y204: girdi düşmeden önce tedavi
adımı uygulanır. Girdi yalnız onaylı turda (ya da kanonik tarafı zaten anonim — `_uzlastir`) yazılır → anonimleştirme sahip / operatör
onaylıdır. A-27: hekim atfı (seansın `operator_name` / `operator_email`) KALIR.

Kurulum EN ALT katta: tedavi / kanonik adımın düşmesi GERÇEK SQLite tetikleyicisiyle (`RAISE(ABORT)`), kart silmesi GERÇEK
`PatientDatabase.delete_patient`. GERÇEK `services.kvkk_anonimlestirme.tur`.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta

import pytest

HEKIM = "dr.y204@klinik.vet"
IZ = "kvkk.bekleyen_silinen_hasta"


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
    pid = pdb.add_patient({"name": ad, "owner": f"Sahip {ad}", "owner_email": "y204@ornek.com"})
    with pdb._get_connection() as c:
        c.execute(
            "UPDATE patients SET last_treatment_at=? WHERE id=?",
            ((datetime.now() - timedelta(days=gun)).isoformat(), pid),
        )
        c.commit()
    return pid


def _seans(tdb, ad, pid):
    tpid = tdb.upsert_patient(
        {"name": ad, "patient_uuid": pid, "owner_name": f"Sahip {ad}", "owner_email": "y204@ornek.com"}
    )
    sid = int(
        tdb.start_session(treatment_mode="Manuel", patient_name=ad, operator_name="Dr Y204", operator_email=HEKIM)
    )
    tdb.set_session_meta(sid, started_epoch=time.time(), patient_id=tpid)
    tdb.end_session(sid, patient_notes=f"{ad} sakin", duration_minutes=5)
    return sid


def _onay(tdb):
    from services import kvkk_anonimlestirme as kv

    tdb.anonim_onayi_yaz(gun=kv.ESIK_GUN, sayi=2, kim=HEKIM)


def _tetik(db, ad):
    with db._get_connection() as c:
        c.execute(f"CREATE TRIGGER {ad} BEFORE UPDATE ON patients BEGIN SELECT RAISE(ABORT, 'Y204 benzetim'); END")
        c.commit()


def _tetik_kaldir(db, ad):
    with db._get_connection() as c:
        c.execute(f"DROP TRIGGER {ad}")
        c.commit()


def _dosyada(yol, metin: str) -> dict:
    """F2-1.5 deseni: ad DB DOSYASINDA (.db + -wal) kaldı mı — SQL'de 0 olsa da eski sayfa / WAL çerçevesi adı taşıyabilir."""
    from pathlib import Path

    p, igne, out = Path(yol), metin.encode("utf-8"), {}
    for ek in ("", "-wal"):
        f = p.with_name(p.name + ek)
        out[ek or ".db"] = (f.read_bytes() if f.exists() else b"").count(igne)
    return out


def _tedavi_metni(tdb) -> str:
    """Tedavi DB'sinin hasta ayna + seans satırlarındaki bütün kimlik / not metni (tek dize)."""
    with tdb._get_connection() as c:
        ayna = c.execute("SELECT name, owner_name, owner_email FROM patients").fetchall()
        seans = c.execute(
            "SELECT patient_name, patient_notes, operator_name, operator_email FROM treatment_sessions"
        ).fetchall()
    return json.dumps([list(r) for r in ayna] + [list(r) for r in seans], ensure_ascii=False)


def test_KRITIK_A_onayli_anonim_hastanin_KARTI_SILINIRSE_tedavi_gecmisi_ANONIMLESIR_ve_girdi_DUSER(o):
    from services import kvkk_anonimlestirme as kv

    pdb, tdb = o
    p1 = _hasta(pdb, "Pamuk Silinen-Y204")
    _seans(tdb, "Pamuk Silinen-Y204", p1)
    _onay(tdb)
    _tetik(tdb, "y204_tedavi_dus")
    s = kv.tur(pdb, tdb)
    assert s["anonimlestirilen"] == 1 and p1 in tdb.anonim_bekleyen_oku(), (
        f"aparat: kanonik adım / bekleyen kurulamadı: {s}"
    )
    assert "Pamuk Silinen-Y204" in _tedavi_metni(tdb), "aparat: tedavi adımı zaten uygulanmış (tetikleyici etkisiz)"
    assert pdb.delete_patient(p1) is True
    # Tedavi adımı HÂLÂ düşüyorken kart silindi: girdi DÜŞMEZ (adım uygulanmadan düşerse ad süresiz kalır), iz YOK.
    kv.tur(pdb, tdb)
    assert p1 in tdb.anonim_bekleyen_oku(), (
        "kartı silinen hastanın girdisi tedavi adımı UYGULANMADAN düştü — tedavi geçmişindeki ad SÜRESİZ kalır (Y204 / S-D5.10)"
    )
    assert tdb.denetim_oku(50, IZ) == [], "tedavi adımı uygulanmadığı hâlde 'silinen hasta' izi yazıldı"
    _tetik_kaldir(tdb, "y204_tedavi_dus")
    kv.tur(pdb, tdb)
    metin = _tedavi_metni(tdb)
    assert p1 not in tdb.anonim_bekleyen_oku(), "tedavi adımı uygulandığı hâlde girdi listeden düşmedi"
    for parca in ("Pamuk Silinen-Y204", "Sahip Pamuk Silinen-Y204", "y204@ornek.com"):
        assert parca not in metin, (
            f"kartı silinen, anonimleştirmesi ONAYLI hastanın tedavi geçmişinde '{parca}' KALDI (Y204 / S-D5.10)"
        )
    assert "Dr Y204" in metin and HEKIM in metin, "A-27: seansın hekim atfı (operator_name / operator_email) KALMALI"
    izler = tdb.denetim_oku(50, IZ)
    assert len(izler) == 1 and int(izler[0]["item_count"]) == 1, izler
    assert json.loads(izler[0]["detail"]).get("tedavi_adimi") == "uygulandi", izler[0]["detail"]
    assert "Pamuk" not in json.dumps(izler, ensure_ascii=False, default=str), "denetim izi hasta adını taşıyor"
    # F2-1.5: tur yalnız silinen kartı işlediğinde de denetim noktası koşar — ad DOSYADA (.db + -wal) da kalmaz.
    assert _dosyada(tdb.db_path, "Pamuk Silinen-Y204") == {".db": 0, "-wal": 0}, (
        f"silinen kartın adı tedavi DB DOSYASINDA okunabilir: {_dosyada(tdb.db_path, 'Pamuk Silinen-Y204')}"
    )


def test_KRITIK_B_kanonik_adimi_dusen_adayin_KARTI_SILINIRSE_tedavi_gecmisi_ANONIMLESIR(o):
    from services import kvkk_anonimlestirme as kv

    pdb, tdb = o
    p1 = _hasta(pdb, "Zeytin Aday-Y204")
    _seans(tdb, "Zeytin Aday-Y204", p1)
    _onay(tdb)
    _tetik(pdb, "y204_kanonik_dus")
    s = kv.tur(pdb, tdb)
    assert s["anonimlestirilen"] == 0 and p1 in tdb.anonim_bekleyen_oku(), f"aparat: {s}"
    _tetik_kaldir(pdb, "y204_kanonik_dus")
    assert pdb.delete_patient(p1) is True
    kv.tur(pdb, tdb)
    assert p1 not in tdb.anonim_bekleyen_oku()
    assert "Zeytin Aday-Y204" not in _tedavi_metni(tdb), (
        "onaylı turda adayı olan (kanonik adımı düşen) hastanın kartı silindi; tedavi geçmişindeki adı KALDI (Y204 / S-D5.10)"
    )


def test_KARSIT_karti_DURAN_ve_ONAYSIZ_hastanin_tedavi_gecmisine_DOKUNULMAZ(o):
    """Onay yokken bekleyen girdi yazılmaz → kart silinse de tedavi geçmişi (bugünkü hasta silme kuralı) aynen kalır."""
    from services import kvkk_anonimlestirme as kv

    pdb, tdb = o
    p1 = _hasta(pdb, "Mavi Onaysiz-Y204")
    _seans(tdb, "Mavi Onaysiz-Y204", p1)
    kv.tur(pdb, tdb)  # onay YOK
    assert not tdb.anonim_bekleyen_oku()
    assert pdb.delete_patient(p1) is True
    kv.tur(pdb, tdb)
    assert "Mavi Onaysiz-Y204" in _tedavi_metni(tdb), (
        "onaysız (girdisi olmayan) hastanın tedavi geçmişi anonimleştirildi"
    )
    assert tdb.denetim_oku(50, IZ) == []
