# -*- coding: utf-8 -*-
"""DALGA-1 §7 "Dalga 2 (veri)" (1-C §9 #11 — D3 devri → D5): 1.9.50 sahada tekil bobin ucuna ham `Infinity` / `NaN` geldiğinde 200
dönüp koşu kaydına SONLU OLMAYAN frekans / duty yazabiliyordu (D1.99 yeni satırı engelledi; ESKİ satırlar sahada durur). Bu satırlı seansın
ayrıntı ucu (`/api/history/{id}/details`) yanıtı JSON'a çevirirken (`allow_nan=False`) patlayıp 500 veriyordu → hekim o seansın kaydını
HİÇ göremiyordu. Sonlu olmayan sayı yanıtta `null` olur (değer "ölçüm yok" gibi gösterilir), diğer alanlar ve seans görünür.

Eski satır EN ALT katta kurulur: koşu satırı doğrudan SQL ile `inf` / `-inf` değerle yazılır (1.9.50'nin bıraktığı biçim). `NaN`
SQLite'ta NULL saklanır (ölçüldü) — diskten gelebilecek sonlu olmayan değer yalnız ±inf."""

from __future__ import annotations

import math
import time

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def ortam(temp_app_data, monkeypatch):
    from database import sqlcipher_util as su
    from database import treatment_history_db as thdb
    from servers import api_server, history_router

    monkeypatch.delenv("PEMF_ENCRYPT_AT_REST", raising=False)
    monkeypatch.setattr(su, "get_sqlcipher_key", lambda *a, **k: "")
    monkeypatch.setattr(thdb.TreatmentHistoryDB, "_get_sqlcipher_key_legacy", lambda self: "")
    db = thdb.TreatmentHistoryDB(temp_app_data / "gecmis")
    api_server.app.dependency_overrides[history_router.get_db] = lambda: db
    try:
        yield db, TestClient(api_server.app, client=("127.0.0.1", 50000), raise_server_exceptions=False)
    finally:
        api_server.app.dependency_overrides.pop(history_router.get_db, None)
        db.close()


def _eski_inf_satiri(db):
    sid = db.start_session(treatment_mode="Manuel", patient_name="INF-test")
    simdi = time.time()
    with db._get_connection() as c:
        c.execute(
            "INSERT INTO session_coil_runs (session_id, coil_id, started_epoch, ended_epoch, duration_seconds, frequency_hz, "
            "duty_percent, phase, intensity_mt, hw_type, created_at) VALUES (?, 1, ?, ?, 60, ?, ?, 0, 1.5, 'stm32', ?)",
            (sid, simdi - 60, simdi, float("inf"), float("-inf"), simdi),
        )
        c.execute(
            "INSERT INTO session_coil_runs (session_id, coil_id, started_epoch, ended_epoch, duration_seconds, frequency_hz, "
            "duty_percent, phase, intensity_mt, hw_type, created_at) VALUES (?, 2, ?, ?, 60, 100, 25, 0, 1.2, 'stm32', ?)",
            (sid, simdi - 60, simdi, simdi),
        )
        c.commit()
        assert math.isinf(c.execute("SELECT frequency_hz FROM session_coil_runs WHERE coil_id=1").fetchone()[0])
    return sid


def test_KRITIK_inf_kosu_satirli_seansin_AYRINTISI_acilir(ortam):
    db, istemci = ortam
    sid = _eski_inf_satiri(db)
    r = istemci.get(f"/api/history/{sid}/details")
    assert r.status_code == 200, f"1.9.50'nin inf koşu satırı ayrıntı ucunu {r.status_code}'de tutuyor: {r.text[:200]}"
    kosular = {k["coil_id"]: k for k in r.json()["coil_runs"]}
    assert kosular[1]["frequency_hz"] is None and kosular[1]["duty_percent"] is None, kosular[1]
    assert kosular[1]["intensity_mt"] == 1.5, "sonlu alanlar korunmalı"
    assert kosular[2]["frequency_hz"] == 100 and kosular[2]["duty_percent"] == 25, "sağlam satır değişmemeli"
