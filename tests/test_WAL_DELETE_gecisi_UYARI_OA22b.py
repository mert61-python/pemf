# -*- coding: utf-8 -*-
"""2-A inceleme O-A2-2.b — havuzda WAL düşüşünde DELETE geçişi düşerse ERROR değil WARNING.

ÖLÇÜLEN (2-A inceleme Kapsam 2 sonda (a)): ana iş parçacığının bağlantısı WAL'de AÇIKKEN bir işçi iş parçacığının yeni
bağlantısında WAL pragması bir kez düşer → tedavi `_create_connection` yeniden açar ve DELETE'e geçmeye çalışır; diğer
bağlantı WAL'de açık olduğu için geçiş düşer ve "Fallback DELETE modu da hataya düştü" ERROR'u basılır. Bağlantı WAL'de
sürer, okuma/yazma çalışır — zararsız; ERROR günlüğü gerçek arızaları gürültüde boğar.
Sahte EN ALT katta: yalnız ilk düz bağlantının `PRAGMA journal_mode`u bir kez OperationalError verir (bağlantı vekili).
"""

from __future__ import annotations

import logging
import sqlite3
import threading

import pytest


@pytest.fixture
def tedavi(monkeypatch, tmp_path):
    from database import sqlcipher_util as su
    from database import treatment_history_db as thdb

    monkeypatch.delenv("PEMF_ENCRYPT_AT_REST", raising=False)
    monkeypatch.setattr(su, "get_sqlcipher_key", lambda *a, **k: "")
    monkeypatch.setattr(thdb.TreatmentHistoryDB, "_get_sqlcipher_key_legacy", lambda self: "")
    t = thdb.TreatmentHistoryDB(tmp_path / "PEMF_GUI")
    t.end_session(t.start_session("AnaBaglanti-OA22b"))
    yield thdb, t
    t.close_connections()


def _ilk_wal_pragmasini_dusur(monkeypatch, thdb) -> dict:
    gercek = thdb.TreatmentHistoryDB._connect_plain_sqlite
    durum = {"dustu": 0}

    class _Vekil:
        def __init__(self, c):
            object.__setattr__(self, "_c", c)

        def execute(self, sql, *a, **k):
            if durum["dustu"] == 0 and str(sql).strip().upper().startswith("PRAGMA JOURNAL_MODE"):
                durum["dustu"] += 1
                raise sqlite3.OperationalError("database is locked (taklit: WAL ayarlanamadi)")
            return self._c.execute(sql, *a, **k)

        def __getattr__(self, ad):
            return getattr(self._c, ad)

        def __setattr__(self, ad, deger):
            setattr(self._c, ad, deger)

    def _sarmal(self):
        c = gercek(self)
        return _Vekil(c) if durum["dustu"] == 0 else c

    monkeypatch.setattr(thdb.TreatmentHistoryDB, "_connect_plain_sqlite", _sarmal)
    return durum


def test_KRITIK_WAL_dususunde_DELETE_gecisi_dusse_ERROR_degil_WARNING_baglanti_calisir(tedavi, monkeypatch, caplog):
    """MUTASYON: seviyeyi yeniden `error`a çevirmek → KIRMIZI; kaydı tamamen yutmak → KIRMIZI (iz kalmaz)."""
    thdb, t = tedavi
    durum = _ilk_wal_pragmasini_dusur(monkeypatch, thdb)
    sonuc = {}

    def _isci():
        try:
            sonuc["gecmis"] = t.get_session_history(limit=5)
        except Exception as e:  # iddia ana iş parçacığında
            sonuc["hata"] = e

    with caplog.at_level(logging.DEBUG, logger="database.treatment_history_db"):
        th = threading.Thread(target=_isci)
        th.start()
        th.join(30)
    assert durum["dustu"] == 1, "ön koşul: işçinin WAL pragması düşürülmeliydi"
    assert "hata" not in sonuc and len(sonuc.get("gecmis", [])) == 1, f"işçi bağlantısı çalışmadı: {sonuc}"
    delete_kayitlari = [r for r in caplog.records if "DELETE" in r.getMessage()]
    assert delete_kayitlari, "ön koşul: DELETE geçişi denenmeli ve DÜŞMELİYDİ (başka bağlantı WAL'de açık)"
    hatalar = [r.getMessage() for r in delete_kayitlari if r.levelno >= logging.ERROR]
    assert hatalar == [], f"zararsız WAL→DELETE düşüşü ERROR basıyor (O-A2-2.b): {hatalar}"
    uyarilar = [r.getMessage() for r in delete_kayitlari if r.levelno == logging.WARNING]
    assert any("suruyor" in m for m in uyarilar), (
        f"DELETE geçişinin düştüğü ve bağlantının mevcut kipte sürdüğü WARNING olarak söylenmiyor: "
        f"{[(r.levelname, r.getMessage()) for r in delete_kayitlari]}"
    )
