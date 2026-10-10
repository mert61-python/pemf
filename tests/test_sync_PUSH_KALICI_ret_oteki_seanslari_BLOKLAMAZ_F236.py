# -*- coding: utf-8 -*-
"""F2-3.6 (2-F incelemesi A3 · D2.65) — UYKUDA (A-15) senkron yolu bayrak açılınca bulut BİR seansı KALICI reddederse (kısıt ihlali / RLS)
öteki bekleyen seanslar yine gönderilir, reddedilen seansın PUSH bayrağı KORUNUR (değişiklik kaybolmaz — D2.65), ret seans başına bir kez ERROR.

ÖLÇÜLEN (3 döngü): eskiden ilk hata döngüyü kesiyordu → push=[A, A, A], 3 ERROR, öteki seans (B) HİÇ gönderilmedi; D2.65'in ebeveyni bayrağı
düşürüp B'yi sessizce kaybediyordu. GERÇEK TreatmentHistoryDB (tmp), GERÇEK CloudSyncWorker._sync_sessions; sahte yalnız bulut istemcisi (en
dış sınır). MUTASYON: ret döngüyü keser / her turda ERROR / ret bayrağı düşürür → KIRMIZI."""

from __future__ import annotations

import logging

import pytest


class _Rpc:
    def __init__(self, rows):
        self.data = rows

    def execute(self):
        return self


class _Bulut:
    def __init__(self, red_id, satirlar):
        self.red_id, self.satirlar = red_id, satirlar
        self.push: list = []

    def rpc(self, ad, params=None):
        if ad == "upsert_session":
            sid = params["p_session"]["id"]
            self.push.append(sid)
            if sid == self.red_id:
                raise RuntimeError('{"code":"23514","message":"new row violates check constraint"}')
            return _Rpc([])
        return _Rpc(self.satirlar if ad == "resolve_sessions" else [])


@pytest.fixture
def db(tmp_path, monkeypatch):
    from database.treatment_history_db import TreatmentHistoryDB

    monkeypatch.delenv("PEMF_MASK_HISTORY_PII", raising=False)
    d = TreatmentHistoryDB(tmp_path / "gecmis")
    try:
        yield d
    finally:
        d.close_connections()


def _bayrak(db, sid):
    with db._get_connection() as c:
        c.row_factory = None
        return c.execute("SELECT sync_status FROM treatment_sessions WHERE id=?", (sid,)).fetchone()[0]


def test_KRITIK_KALICI_ret_oteki_seansi_BLOKLAMAZ_bayrak_KORUNUR_gunluk_TEK_ERROR(db, monkeypatch, caplog):
    from servers.sync_worker import CloudSyncWorker

    a = db.start_session("Manual", operator_name="Vet", patient_name="A")
    db.end_session(a, duration_minutes=10, session_status="completed")
    b = db.start_session("Manual", operator_name="Vet", patient_name="B")
    db.end_session(b, duration_minutes=10, session_status="completed")
    assert (_bayrak(db, a), _bayrak(db, b)) == (0, 0), "aparat: iki seans PUSH bekliyor olmalı"
    bulut_satiri = lambda sid: {  # noqa: E731
        "id": sid,
        "session_date": "2026-10-01",
        "start_time": "10:00",
        "end_time": "10:10",
        "duration_minutes": 10,
        "treatment_mode": "Manual",
        "target_condition": None,
        "frequency_hz": None,
        "intensity_mt": None,
        "pulse_duration_ms": None,
        "session_status": "completed",
        "created_at": "2026-10-01T10:00:00",
    }
    bulut = _Bulut(red_id=a, satirlar=[bulut_satiri(a), bulut_satiri(b)])
    monkeypatch.setenv("PEMF_CLOUD_PATIENT_SYNC", "1")
    w = CloudSyncWorker("", "")
    w.client, w.patient_sync_enabled, w.device_id = bulut, True, "test-device"
    w._reg_secret = "s"
    with caplog.at_level(logging.ERROR):
        for _ in range(3):
            w._sync_sessions(db)
    hatalar = [r for r in caplog.records if "Session PUSH hatasi" in r.getMessage()]
    print(
        f"OLCUM push_denemeleri={bulut.push} hata_gunlugu={len(hatalar)} bayrak A={_bayrak(db, a)} B={_bayrak(db, b)}"
    )
    assert b in bulut.push, (
        f"KALICI reddedilen seans ({a}) döngüyü kesiyor: öteki bekleyen seans ({b}) 3 döngüde HİÇ gönderilmedi {bulut.push}"
    )
    assert bulut.push.count(a) <= 1 or len(hatalar) <= 1, (
        f"kalıcı ret her döngüde yeniden deneniyor + günlük: {bulut.push}, {len(hatalar)}"
    )
    assert _bayrak(db, a) == 0, (
        "reddedilen seansın bekleyen değişikliği DÜŞÜRÜLDÜ (bir daha gönderilmez — D2.65'in kapattığı kayıp)"
    )
