# -*- coding: utf-8 -*-
"""2-F incelemesi §10 #4 yan bulgusu (D5 · yardımcı E, E-4b) — tur başındaki UZLAŞTIRMA (`_uzlastir`, F2-1.3) kalıcı BEKLEYEN listesindeki
girdiyi ayna satırının eksik metinleriyle EZMEZ; sahibin adı tedavi adımı düzelince serbest metinden de silinir.

ÖLÇÜLEN KUSUR (HEAD 9c6d4505): kanonik adım olur, tedavi adımı düşer (-1) → girdi `[ad, sahip, e-posta]` (kanonik karttan) listede kalır.
Sonraki turun başında `_uzlastir` aynı hastayı "ayna satırı hâlâ ad taşıyor + kanonik anonim" diye bulur ve girdiyi ayna satırının KENDİ
metinleriyle `anonim_bekleyen_ekle` (dict.update) ile EZER. Üretimde ayna satırına sahip adı hiç yazılmaz (`_persist_session_start` ve AI
seansı `upsert_patient`'a yalnız ad + e-posta verir) → girdi `[ad, "", e-posta]` olur; tedavi adımı düzelince AI özetinde / gerekçesinde
geçen SAHİP ADI `[ANONIM]` olmaz, SÜRESİZ kalır (sonda: `'Fatma Sahipova-E4y aradi, [ANONIM] iyi'`).

Düzeltme: uzlaştırma var olan girdiyi KORUR, ayna satırının girdide olmayan metinlerini SONA ekler (ad başta kalır).
Kurulum EN ALT katta: tedavi adımının düşmesi GERÇEK SQLite tetikleyicisiyle (`RAISE(ABORT)`). GERÇEK `services.kvkk_anonimlestirme.tur`.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta

import pytest

HEKIM = "dr.e4b@klinik.vet"
AD = "Pamuk Uzlas-E4b"
SAHIP = "Fatma Sahipova-E4b"
EPOSTA = "e4b@ornek.com"


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


def _kur(pdb, tdb, ayna_ad=AD):
    """Kanonik kart (ad + SAHİP + e-posta) · ayna satırı üretimdeki gibi yalnız ad + e-posta · seans · sahibi anan AI kaydı · onay."""
    from services import kvkk_anonimlestirme as kv

    pid = pdb.add_patient({"name": AD, "owner": SAHIP, "owner_email": EPOSTA})
    with pdb._get_connection() as c:
        c.execute(
            "UPDATE patients SET last_treatment_at=? WHERE id=?",
            ((datetime.now() - timedelta(days=2200)).isoformat(), pid),
        )
        c.commit()
    tpid = tdb.upsert_patient({"name": ayna_ad, "patient_uuid": pid, "owner_email": EPOSTA})
    sid = int(tdb.start_session(treatment_mode="Manuel", patient_name=AD, operator_name="Dr E4b", operator_email=HEKIM))
    tdb.set_session_meta(sid, started_epoch=time.time(), patient_id=tpid)
    tdb.end_session(sid, patient_notes="sakin", duration_minutes=5)
    tdb.add_ai_analysis(
        module_id="m",
        patient_name=AD,
        result_summary=f"{SAHIP} telefonla aradi; {ayna_ad} iyi",
        patient_uuid=pid,
        operator_email=HEKIM,
    )
    tdb.anonim_onayi_yaz(gun=kv.ESIK_GUN, sayi=1, kim=HEKIM)
    with tdb._get_connection() as c:
        c.execute("CREATE TRIGGER e4b_dus BEFORE UPDATE ON patients BEGIN SELECT RAISE(ABORT, 'E4b benzetim'); END")
        c.commit()
    return pid


def _tetik_kaldir(tdb):
    with tdb._get_connection() as c:
        c.execute("DROP TRIGGER e4b_dus")
        c.commit()


def _ozet(tdb) -> str:
    with tdb._get_connection() as c:
        return c.execute("SELECT result_summary FROM ai_analyses").fetchone()[0]


def test_KRITIK_tedavi_adimi_dusen_girdiyi_uzlastirma_EZMEZ_sahip_adi_sonunda_SILINIR(o):
    """MUTASYON: uzlaştırma girdiyi ayna metinleriyle ezer (HEAD) → KIRMIZI."""
    from services import kvkk_anonimlestirme as kv

    pdb, tdb = o
    pid = _kur(pdb, tdb)
    s = kv.tur(pdb, tdb)
    assert s["anonimlestirilen"] == 1, f"aparat: kanonik adım olmadı: {s}"
    ilk = tdb.anonim_bekleyen_oku().get(pid)
    assert ilk and SAHIP in ilk, f"aparat: girdi kanonik karttan sahip adıyla yazılmadı: {ilk}"
    kv.tur(pdb, tdb)  # tedavi adımı yine düşer; tur başında uzlaştırma koşar
    ikinci = tdb.anonim_bekleyen_oku().get(pid)
    assert ikinci and ikinci[0] == AD and SAHIP in ikinci, (
        f"uzlaştırma bekleyen girdiyi ayna satırının eksik metinleriyle EZDİ (sahip adı kayboldu): {ilk} → {ikinci}"
    )
    _tetik_kaldir(tdb)
    kv.tur(pdb, tdb)
    assert not tdb.anonim_bekleyen_oku(), "aparat: tedavi adımı düzeldiği hâlde girdi işlenmedi"
    ozet = _ozet(tdb)
    assert SAHIP not in ozet and AD not in ozet, f"anonimleştirmeden sonra AI özetinde kimlik metni kaldı: {ozet!r}"


def test_KRITIK_ayna_satirindaki_FARKLI_eski_ad_da_girdiye_EKLENIR(o):
    """Ayna satırı kanonik addan FARKLI (eski) bir ad taşıyorsa uzlaştırma onu da girdiye EKLER (eskiden yalnız ezerek ekliyordu) —
    hem kanonik ad hem ayna adı serbest metinden silinir; ad başta kalır."""
    from services import kvkk_anonimlestirme as kv

    pdb, tdb = o
    eski = "Minnos Eskiad-E4b"
    pid = _kur(pdb, tdb, ayna_ad=eski)
    kv.tur(pdb, tdb)
    kv.tur(pdb, tdb)
    girdi = tdb.anonim_bekleyen_oku().get(pid)
    assert girdi and girdi[0] == AD, f"girdinin başındaki ad değişti: {girdi}"
    assert eski in girdi and SAHIP in girdi, f"uzlaştırma ayna adını eklemedi / sahip adını kaybetti: {girdi}"
    _tetik_kaldir(tdb)
    kv.tur(pdb, tdb)
    ozet = _ozet(tdb)
    assert SAHIP not in ozet and eski not in ozet, f"AI özetinde kimlik metni kaldı: {ozet!r}"
