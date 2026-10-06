# -*- coding: utf-8 -*-
"""D2.24 (B-3.81 · Y9) — ŞEMA GÖÇÜ KİLİT / G-Ç HATASINI SESSİZCE YUTMAZ (tedavi + hasta DB'si).

KUSUR. `_safe_add_column` (`thdb_sema.py` ve ikizi `patient_database.py`) `ALTER TABLE … ADD COLUMN`'ın
HER `OperationalError`ını yutuyordu. Amaç "kolon zaten var" (`duplicate column name`) idi — şema göçü her
açılışta koşar ve ikinci koşuda patlamamalıdır. Ama aynı dal kilit (`database is locked`), G-Ç ve disk-dolu
hatalarını da İZ BIRAKMADAN geçiyordu: yeni kolonun ilk açılışında yazma kilidi ≥5 sn sürerse şema KOLONSUZ
kalır, `is_ready` yeşil, seans başlar, kayıt yazımı "no such column" ile düşer → seans kaydı kaybı; günlük
kök nedeni göstermez.

SÖZLEŞME (Y9 · orkestratör notu): yalnız `duplicate column` sessiz geçer. Başka her hata WARNING ile
loglanır ve YÜKSELİR → DB kurucusu düşer → backend DB'siz KISITLI kipte açılır (D1.37 / Y43: ACİL DURDUR ve
STOP çalışır, seans 503, DB arka planda yeniden açılır). Dosyaya dokunulmaz (karantina YOK — kilit anahtar
uyuşmazlığı değildir). Kilit kalkınca AYNI kurucu kolonu ekler (idempotentlik korunur).

ÖLÇÜM GERÇEK KİLİTLE (sahte cursor YOK): başka bir bağlantı `BEGIN IMMEDIATE` ile yazma kilidini tutar. Ölçüldü
(2026-10-06, SQLite 3.35.5): kilit varken VAR OLAN kolona ALTER hemen `duplicate column` verir, YENİ kolona ALTER
busy_timeout (5 sn) sonra `database is locked`; `CREATE … IF NOT EXISTS` ve `SELECT` kilit beklemez. Bu yüzden
yalnız bir kolonu eksik (düşürülmüş) gerçek DB, kusuru tam o ALTER'da üretir. sqlcipher3 GEREKTİRMEZ.
"""

from __future__ import annotations

import contextlib
import logging
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@contextlib.contextmanager
def _yazma_kilidi(db: Path):
    """Başka bir bağlantı YAZMA kilidini (RESERVED) tutar — yedekleyici / ikinci süreç / uzun yazım."""
    tutucu = sqlite3.connect(str(db), isolation_level=None)
    try:
        tutucu.execute("BEGIN IMMEDIATE")
        yield
    finally:
        try:
            tutucu.execute("ROLLBACK")
        finally:
            tutucu.close()


def _kolonlar(db: Path, tablo: str) -> list[str]:
    c = sqlite3.connect(str(db))
    try:
        return [r[1] for r in c.execute(f"PRAGMA table_info({tablo})")]
    finally:
        c.close()


def _kolonu_dusur(db: Path, tablo: str, kolon: str) -> None:
    c = sqlite3.connect(str(db))
    try:
        c.execute(f"ALTER TABLE {tablo} DROP COLUMN {kolon}")
        c.commit()
    finally:
        c.close()
    assert kolon not in _kolonlar(db, tablo), "kurgu bozuk: kolon dusurulemedi"


def _karantina(kok: Path) -> list[str]:
    return sorted(p.name for p in kok.iterdir() if ".acilamadi-" in p.name)


def _sema_uyarilari(caplog, kolon: str) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING and kolon in r.getMessage()]


@pytest.fixture
def duz_kok(tmp_path, monkeypatch):
    """Anahtarsız (düz-metin) kurulum: şifreleme bu kapının konusu değil."""
    monkeypatch.delenv("PEMF_ENCRYPT_AT_REST", raising=False)
    monkeypatch.delenv("PEMF_SQLCIPHER_KEY", raising=False)
    from database import patient_database as pdb
    from database import sqlcipher_util as su

    monkeypatch.setattr(su, "get_sqlcipher_key", lambda *a, **k: "")
    monkeypatch.setattr(pdb, "get_sqlcipher_key", lambda *a, **k: "")
    kok = tmp_path / "PEMF_GUI"
    kok.mkdir(parents=True)
    return kok


def test_KRITIK_tedavi_DB_yeni_kolon_KILITTE_eklenemezse_acilis_DURUR_ve_LOGLANIR(duz_kok, caplog):
    """MUTASYON: `thdb_sema._safe_add_column` except dalını yeniden koşulsuz `pass` yapmak → KIRMIZI."""
    from database import treatment_history_db as thdb

    db = duz_kok / "pemf_treatment_history.db"
    ilk = thdb.TreatmentHistoryDB(duz_kok)
    sid = ilk.start_session("KilitliGocSeansi")
    ilk.end_session(sid)
    ilk.close_connections()
    del ilk
    _kolonu_dusur(db, "ai_analyses", "reviewed_at")

    with _yazma_kilidi(db), caplog.at_level(logging.WARNING), pytest.raises(Exception) as hata:
        thdb.TreatmentHistoryDB(duz_kok)

    assert "locked" in str(hata.value).lower(), f"beklenmeyen hata: {hata.value!r}"
    assert _sema_uyarilari(caplog, "reviewed_at"), (
        "yeni kolon KILITTE eklenemedi ama hicbir WARNING yok -> sema KOLONSUZ kalir, kok neden gunlukte gorunmez"
    )
    assert _karantina(duz_kok) == [], "kilit anahtar uyusmazligi DEGIL — DB karantinaya alinmamali"

    # Kilit kalkınca AYNI kurucu kolonu ekler; veri yerinde (idempotent iyileşme).
    yeni = thdb.TreatmentHistoryDB(duz_kok)
    try:
        assert "reviewed_at" in _kolonlar(db, "ai_analyses"), "kilit kalkinca kolon EKLENMEDI"
        assert [s.get("treatment_mode") for s in yeni.get_session_history(limit=10)] == ["KilitliGocSeansi"]
    finally:
        yeni.close_connections()


def test_KRITIK_hasta_DB_yeni_kolon_KILITTE_eklenemezse_acilis_DURUR_ve_LOGLANIR(duz_kok, caplog):
    """İkiz. MUTASYON: `patient_database._safe_add_column` except dalını yeniden koşulsuz `pass` yapmak → KIRMIZI."""
    from database import patient_database as pdb

    db = duz_kok / "patients.db"
    ilk = pdb.PatientDatabase(str(db))
    hid = ilk.add_patient({"name": "KilitliGocHasta", "owner": "T", "species": "Kedi"})
    ilk._reset_thread_conn()
    del ilk
    _kolonu_dusur(db, "patients", "anonymized")

    with _yazma_kilidi(db), caplog.at_level(logging.WARNING), pytest.raises(RuntimeError) as hata:
        pdb.PatientDatabase(str(db))

    assert "locked" in str(hata.value).lower(), f"beklenmeyen hata: {hata.value!r}"
    assert _sema_uyarilari(caplog, "anonymized"), "yeni kolon KILITTE eklenemedi ama hicbir WARNING yok"
    assert _karantina(duz_kok) == [], "kilit anahtar uyusmazligi DEGIL — DB karantinaya alinmamali"

    yeni = pdb.PatientDatabase(str(db))
    try:
        assert "anonymized" in _kolonlar(db, "patients"), "kilit kalkinca kolon EKLENMEDI"
        assert (yeni.get_patient(hid) or {}).get("name") == "KilitliGocHasta", "hasta kaydi kayboldu"
    finally:
        yeni._reset_thread_conn()


def test_KARSIT_kolon_VARKEN_ikinci_acilis_duplicate_column_ile_SESSIZ_gecer(duz_kok, caplog):
    """İdempotentlik korunur (thdb_sema notu: "ikinci koşuda patlamamalı"): her açılışta TÜM ALTER'lar
    `duplicate column` verir — sessiz geçmeli, WARNING basmamalı. MUTASYON: duplicate ayrımını kaldırmak
    (her OperationalError'da yükselt) → KIRMIZI."""
    from database import patient_database as pdb
    from database import treatment_history_db as thdb

    thdb.TreatmentHistoryDB(duz_kok).close_connections()
    pdb.PatientDatabase(str(duz_kok / "patients.db"))._reset_thread_conn()
    with caplog.at_level(logging.WARNING):
        thdb.TreatmentHistoryDB(duz_kok).close_connections()
        pdb.PatientDatabase(str(duz_kok / "patients.db"))._reset_thread_conn()
    gurultu = [
        r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING and "eklenemedi" in r.getMessage()
    ]
    assert gurultu == [], f"kolon VARKEN ikinci acilis sema uyarisi basti (idempotentlik bozuk): {gurultu}"
