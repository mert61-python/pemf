# -*- coding: utf-8 -*-
"""F2-4.2 = F2-2.1 (2-F incelemesi; orkestratör + A2, iki bağımsız ölçücü) · A-07 · Ö.4-Y8 — günlük bakımın KVKK anonimleştirme turu
tedavi DB'sinin yazma kilidini KISA tutar; tur sürerken eşzamanlı kısa kayıt yazımları (ACİL DURDUR'un kritik olayı, seans kapanışı)
kilitte bekleyip DÜŞMEZ.

ÖLÇÜLEN KUSUR: D2.54 / Y125 turu, `thdb_pii._ai_kayitlarini_anonimlestir`'de HER hasta için tablodaki TÜM kimliksiz AI kayıtlarını
(metinleriyle) çekip Python'da ada göre süzüyordu — O(hasta × kimliksiz kayıt), ilk UPDATE'ten sonra, tek yazma işleminde. 300 hasta /
3000 kimliksiz kayıtta kilit 5,02 sn KESİNTİSİZ; 600 / 3000'de seans sürerken basılan ACİL DURDUR'un `emergency_stop` (critical) olayı
"database is locked" ile DÜŞTÜ (STOP gitti, nedeni kayıtsız); ebeveyn `853cae4`'te kilit görülmedi, olay yazıldı (ölçüldü). Düzeltme
(A2): kimliksiz kayıtlar çağrı başına TEK kez ve yalnız (id, ad) ile okunur — 1000 hastalık tek işlem 0,14 sn (ölçüldü).
Bu dosya HIZLI kol: GERÇEK `kvkk_anonimlestirme.tur`, GERÇEK PatientDatabase + TreatmentHistoryDB; tur sürerken ikinci bağlantıdan 1 sn
`busy_timeout`'lu kısa yazımlar (üründe 5 sn) — biri bile düşerse KIRMIZI. Sonuç kolu (GERÇEK günlük döngü + GERÇEK ACİL DURDUR, kritik olay
ve seans kapanışı): tests/test_kvkk_turu_KILITTE_ACIL_DURDUR_kaydi_DUSMEZ_F2_2_1.py
"""

from __future__ import annotations

import sqlite3
import threading
import time
from datetime import datetime, timedelta

import pytest


def _veri(pdb, tdb, n_hasta, n_kimliksiz):
    eski = (datetime.now() - timedelta(days=2200)).isoformat()
    kimlikler = []
    for i in range(n_hasta):
        ad = f"Hasta F242-{i:04d}"
        kimlikler.append((pdb.add_patient({"name": ad, "owner": f"Sahip-{i:04d}"}), ad))
    with pdb._get_connection() as c:
        c.execute("UPDATE patients SET last_treatment_at=?", (eski,))
        c.commit()
    for pid, ad in kimlikler:
        tp = tdb.upsert_patient({"name": ad, "patient_uuid": pid})
        sid = int(tdb.start_session(treatment_mode="Manuel", patient_name=ad, operator_name="Dr X"))
        tdb.set_session_meta(sid, patient_id=tp)
        tdb.end_session(sid, duration_minutes=1)
        tdb.add_ai_analysis(module_id="m", patient_name=ad, result_summary=f"{ad} bulgu", patient_uuid=pid)
    with tdb._get_connection() as c:
        c.executemany(
            "INSERT INTO ai_analyses (module_id, patient_name, result_summary, patient_uuid) VALUES (?,?,?,'')",
            [("m", f"Baska Kimliksiz-{j:05d}", f"kayit {j}") for j in range(n_kimliksiz)],
        )
        c.commit()


@pytest.fixture
def db(tmp_path, monkeypatch):
    from database.patient_database import PatientDatabase
    from database.treatment_history_db import TreatmentHistoryDB

    monkeypatch.delenv("PEMF_MASK_HISTORY_PII", raising=False)
    pdb = PatientDatabase(str(tmp_path / "patients.db"))
    tdb = TreatmentHistoryDB(tmp_path / "gecmis")
    try:
        yield pdb, tdb
    finally:
        tdb.close_connections()


def _es_yazar(yol, bitti: threading.Event, sonuc: dict, bekleme_sn: float):
    """Tur sürerken eşzamanlı KISA yazımlar (ürünün kayıt yazımları gibi): her biri `bekleme_sn` busy_timeout'la; düşenler sayılır."""
    c = sqlite3.connect(yol, timeout=bekleme_sn, isolation_level=None)
    deneme = dusen = 0
    en_uzun = 0.0
    try:
        while not bitti.is_set():
            t0 = time.monotonic()
            deneme += 1
            try:
                c.execute(
                    "INSERT OR REPLACE INTO system_settings (setting_key, setting_value) VALUES ('f242_yazar', ?)",
                    (str(deneme),),
                )
            except sqlite3.OperationalError:
                dusen += 1
            en_uzun = max(en_uzun, time.monotonic() - t0)
            time.sleep(0.05)
    finally:
        c.close()
    sonuc.update(deneme=deneme, dusen=dusen, en_uzun=en_uzun)


def test_KRITIK_F2_4_2_tur_suresince_esazamanli_yazim_DUSMEZ(db):
    """300 hasta + 3000 kimliksiz AI kaydı: eski tur kilidi ~5 sn KESİNTİSİZ tutuyordu → 1 sn bekleyen eşzamanlı yazım düşüyordu.
    MUTASYON: kimliksiz kayıtlar hasta başına yeniden taranır (HEAD) → KIRMIZI."""
    from services import kvkk_anonimlestirme as kv

    pdb, tdb = db
    _veri(pdb, tdb, 300, 3000)
    tdb.anonim_onayi_yaz(gun=kv.ESIK_GUN, sayi=300, kim="")
    bitti, yazar = threading.Event(), {}
    th = threading.Thread(target=_es_yazar, args=(str(tdb.db_path), bitti, yazar, 1.0), daemon=True)
    th.start()
    time.sleep(0.2)
    t0 = time.monotonic()
    sonuc = kv.tur(pdb, tdb)
    sure = time.monotonic() - t0
    time.sleep(0.2)
    bitti.set()
    th.join(10)
    assert sonuc["anonimlestirilen"] == 300 and sonuc["tedavi_bekleyen"] == 0, sonuc
    with tdb._get_connection() as c:
        kalan = c.execute("SELECT COUNT(*) FROM ai_analyses WHERE patient_name LIKE 'Hasta F242-%'").fetchone()[0]
        kimliksiz = c.execute(
            "SELECT COUNT(*) FROM ai_analyses WHERE patient_name LIKE 'Baska Kimliksiz-%'"
        ).fetchone()[0]
    assert kalan == 0, f"anonimleştirme eksik kaldı: {kalan} AI kaydı adı taşıyor"
    assert kimliksiz == 3000, f"başka adlı kimliksiz kayıtlara DOKUNULDU: {kimliksiz}/3000"
    assert yazar["deneme"] >= 3, f"aparat: yazar koşmadı ({yazar}, tur {sure:.2f} sn)"
    assert yazar["dusen"] == 0, (
        f"KVKK turu sürerken eşzamanlı kısa yazımların {yazar['dusen']}/{yazar['deneme']}'i 1 sn bekleyip DÜŞTÜ (en uzun bekleme "
        f"{yazar['en_uzun']:.2f} sn, tur {sure:.2f} sn) — üründe busy_timeout 5 sn: ilk onayda daha büyük veriyle ACİL DURDUR / seans "
        "kaydı düşer (A-07)"
    )


def test_KARSIT_esazamanli_yazar_KOR_DEGIL(db):
    """Araç kör değil: ikinci bağlantı 1,5 sn EXCLUSIVE tutarken 1 sn bekleyen yazar en az bir kez DÜŞER."""
    _, tdb = db
    bitti, yazar = threading.Event(), {}
    th = threading.Thread(target=_es_yazar, args=(str(tdb.db_path), bitti, yazar, 1.0), daemon=True)
    c = sqlite3.connect(str(tdb.db_path), timeout=5, isolation_level=None)
    try:
        c.execute("BEGIN EXCLUSIVE")
        c.execute("INSERT OR REPLACE INTO system_settings (setting_key, setting_value) VALUES ('f242_kilit', '1')")
        th.start()
        time.sleep(1.5)
        c.execute("ROLLBACK")
    finally:
        c.close()
    time.sleep(0.3)
    bitti.set()
    th.join(10)
    assert yazar["dusen"] >= 1, yazar
