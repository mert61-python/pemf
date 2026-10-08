# -*- coding: utf-8 -*-
"""C2-2.8 (2-C inceleme A2 · D2.15 1a9fe6a) — KÖR KAPI: `/api/session/notes`'un İKİNCİ yazım dalı ("seans bellekte bitti ama DB'de
açık" → `end_session(...)`) yazılamazsa da "success" DÖNMEZ.

D2.15 kapısı (`test_gozlem_notu_YAZILAMAZSA_basari_DONMEZ_D215.py`) yalnız kapanmış-seans dalını (`update_session_finalized_extras`)
ölçüyor. `end_session`'ın hatayı YUTTUĞU mutant (`thdb_seans.py` `Seans sonlandırma hatası` → `return`) not ucu kümesinde
(D215, D166/D178, Y116, treatment_persistence, session_char, D189) **38/38 YEŞİL** kaldı (`_inceleme/kayit/d215_mutasyon.txt`):
bu dalda kilitli DB'de not ve kapanış kaybolup uç 200 "success" dönse hiçbir kapı görmez (D2.15'in düzelttiği kusurun ikizi).
Ürün bugün DOĞRU (`end_session` yükseltiyor → 500 + gerekçe) — kapı körlüğü maddesi; önce-kırmızı mutant tabanlı.
GERÇEK kilit: ikinci bağlantı `BEGIN EXCLUSIVE` + yazma (WAL), GERÇEK uç ve `TreatmentHistoryDB`; satır SQL ile.
"""

from __future__ import annotations

import sqlite3
import time
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def o(tmp_path, monkeypatch):
    from database.treatment_history_db import TreatmentHistoryDB
    from servers import api_server as api

    db = TreatmentHistoryDB(tmp_path / "gecmis")
    monkeypatch.setattr(api, "_get_treatment_db", lambda: db)
    sid = db.start_session(treatment_mode="Manuel", target_condition=None, patient_name="Boncuk")  # DB'de AÇIK
    with api._session_lock:
        eski = dict(api._active_session)
        api._active_session.clear()
        api._active_session.update(
            {
                "is_active": False,
                "db_session_id": sid,
                "patient_name": "Boncuk",
                "session_id": "c228",
                "start_time": time.time() - 240,
            }
        )
    try:
        yield type("O", (), {"db": db, "sid": sid, "c": TestClient(api.app, client=("127.0.0.1", 51236))})
    finally:
        with api._session_lock:
            api._active_session.clear()
            api._active_session.update(eski)
        db.close_connections()


@contextmanager
def _yazma_kilidi(o):
    k = sqlite3.connect(str(o.db.db_path), timeout=1.0, isolation_level=None)
    try:
        k.execute("BEGIN EXCLUSIVE")
        k.execute("UPDATE treatment_sessions SET updated_at = updated_at")
        yield
    finally:
        k.execute("ROLLBACK")
        k.close()


def _satir(o):
    with o.db._get_connection() as c:
        c.row_factory = None
        return c.execute(
            "SELECT COALESCE(patient_notes,''), session_status FROM treatment_sessions WHERE id = ?", (o.sid,)
        ).fetchone()


def test_KRITIK_bellek_kapanis_dalinda_kilitli_DB_BASARI_DONMEZ_gerekce_EYLEM_soyler(o):
    with _yazma_kilidi(o):
        r = o.c.post("/api/session/notes", json={"session_id": o.sid, "notes": "kilitte not", "duration_minutes": 4})
    assert r.status_code >= 400 and r.json().get("status") != "success", (
        f"kilitte yazılamayan not {r.status_code} {r.text[:200]}"
    )
    assert "kaydedilemedi" in r.json().get("detail", ""), r.text[:200]
    assert _satir(o) == ("", "active"), _satir(o)


def test_KARSIT_bellek_kapanis_dali_kilitsiz_notu_yazar_ve_kapatir(o):
    r = o.c.post("/api/session/notes", json={"session_id": o.sid, "notes": "kilitsiz not", "duration_minutes": 4})
    assert r.status_code == 200 and r.json().get("status") == "success", r.text[:200]
    assert _satir(o) == ("kilitsiz not", "completed")
