# -*- coding: utf-8 -*-
"""F2-4.3 (2-F incelemesi, orkestratör · A-07 · Ö.4-Y8) — silme sonrası WAL denetim noktası (D2.29 / Y13, F2-2.3'ün yolları) açık bir okuyucu
varken eşzamanlı kayıt yazımlarını (ACİL DURDUR'un kritik olayı) `busy_timeout` boyunca BLOKLAMAZ.

ÖLÇÜLEN KUSUR: `PRAGMA wal_checkpoint(TRUNCATE)` okuyucuyu beklerken (bağlantının `busy_timeout`u = 5 sn) YENİ yazarları da bloklar (SQLite
belgesi; ölçüldü: düz SQLite'ta 2 sn bekleyen yazar "database is locked" ile DÜŞTÜ). D2.29'un tekil AI silmesi sonrası denetim noktası,
uzun bir okuyucu (dışa aktarma, yedek, uzun liste) sürerken eşzamanlı `record_session_event(emergency_stop, critical)`'ı 5,08 sn bekletti
(busy_timeout'un kıyısında; birkaç ms sonra DÜŞERDİ). F2-2.3 aynı denetim noktasını seans silme, olay saklama, PII maskeleme, KVKK
anonimleştirme ve REPLACE_ALL yollarına ekliyor.
DÜZELTME: denetim noktası kısa `busy_timeout` (0,2 sn) ile; tamamlanamazsa kalıcı "VACUUM bekliyor" işareti (F2-2.5) → günlük bakım seans
yokken yeniden dener. GERÇEK TreatmentHistoryDB, okuyucu ikinci bağlantıda açık okuma işlemi.
"""

from __future__ import annotations

import sqlite3
import threading
import time

import pytest


@pytest.fixture
def t(tmp_path, monkeypatch):
    from database.treatment_history_db import TreatmentHistoryDB

    monkeypatch.delenv("PEMF_MASK_HISTORY_PII", raising=False)
    db = TreatmentHistoryDB(tmp_path / "gecmis")
    try:
        yield db
    finally:
        db.close_connections()


def _okuyucu_ac(db):
    c = sqlite3.connect(str(db.db_path), isolation_level=None)
    c.execute("BEGIN")
    c.execute("SELECT COUNT(*) FROM ai_analyses").fetchall()
    return c


def _silme_surerken_olay_yaz(db, sil):
    """`sil()` ayrı iş parçacığında (okuyucu açıkken); 0,3 sn sonra eşzamanlı kritik olay yazımı — süresi ve sonucu."""
    sid = int(db.start_session(treatment_mode="Manuel", patient_name="F243 Hasta", operator_name="Dr"))
    okuyucu = _okuyucu_ac(db)
    sonuc = {}
    try:
        th = threading.Thread(target=lambda: sonuc.__setitem__("sil", sil()), daemon=True)
        th.start()
        time.sleep(0.3)
        t0 = time.monotonic()
        sonuc["olay"] = db.record_session_event(sid, "emergency_stop", {"reason": "f243"}, severity="critical")
        sonuc["olay_sn"] = time.monotonic() - t0
        th.join(15)
    finally:
        okuyucu.execute("COMMIT")
        okuyucu.close()
    return sonuc


def test_KRITIK_F2_4_3_tekil_AI_silme_denetim_noktasi_ACIL_DURDUR_olayini_BEKLETMEZ(t):
    """MUTASYON: denetim noktası bağlantının 5 sn busy_timeout'uyla koşar (HEAD) → olay yazımı ~5 sn bekler → KIRMIZI."""
    aid = t.add_ai_analysis(module_id="m", patient_name="F243 Hasta", result_summary="silinecek F243")
    s = _silme_surerken_olay_yaz(t, lambda: t.delete_ai_analysis(aid))
    assert s.get("sil") is True, s
    assert s["olay"], f"kritik olay YAZILMADI: {s}"
    assert s["olay_sn"] < 1.0, (
        f"silme sonrası denetim noktası okuyucuyu beklerken ACİL DURDUR olay yazımı {s['olay_sn']:.2f} sn BEKLEDİ"
    )


def test_KRITIK_F2_4_3_seans_silme_denetim_noktasi_ACIL_DURDUR_olayini_BEKLETMEZ(t):
    """F2-2.3'ün yeni yolu (seans silme) için aynı ölçüt."""
    eski = int(t.start_session(treatment_mode="Manuel", patient_name="F243 Silinecek", operator_name="Dr"))
    t.end_session(eski, patient_notes="F243 not", duration_minutes=1)
    s = _silme_surerken_olay_yaz(t, lambda: t.delete_session(eski))
    assert s["olay"], f"kritik olay YAZILMADI: {s}"
    assert s["olay_sn"] < 1.0, (
        f"seans silme sonrası denetim noktası ACİL DURDUR olay yazımını {s['olay_sn']:.2f} sn BEKLETTİ"
    )


def test_KARSIT_okuyucu_varken_bekleyen_TRUNCATE_yazari_GERCEKTEN_bloklar(tmp_path):
    """Araç kör değil: düz SQLite'ta okuyucu açıkken 5 sn busy_timeout'lu TRUNCATE sürerken 1 sn bekleyen yazar DÜŞER."""
    yol = str(tmp_path / "x.db")
    a = sqlite3.connect(yol, isolation_level=None)
    a.execute("PRAGMA journal_mode=WAL")
    a.execute("CREATE TABLE t (x)")
    a.execute("INSERT INTO t VALUES (1)")
    ok = sqlite3.connect(yol, isolation_level=None)
    ok.execute("BEGIN")
    ok.execute("SELECT * FROM t").fetchall()
    a.execute("INSERT INTO t VALUES (2)")

    def _cp():
        b = sqlite3.connect(yol, timeout=5, isolation_level=None)
        b.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        b.close()

    th = threading.Thread(target=_cp, daemon=True)
    th.start()
    time.sleep(0.3)
    c = sqlite3.connect(yol, timeout=1, isolation_level=None)
    with pytest.raises(sqlite3.OperationalError):
        c.execute("INSERT INTO t VALUES (3)")
    th.join(10)
    ok.execute("COMMIT")
    for x in (a, ok, c):
        x.close()
