# -*- coding: utf-8 -*-
"""D2.15 (B-3.23) — kapanmış seansın gözlem notu YAZILAMAZSA `/api/session/notes` "success" DÖNMEZ.

ÖLÇÜLEN KUSUR (DENETIM-03 B-3.23, gerçek 5,7 sn'lik kilitle): `update_session_finalized_extras` DB hatasını
(`except _DB_ERROR: yalnız log`) yutuyordu → uç 200 `success` dönüyor, not ekranı uyarısız kapanıyor, klinik gözlem notu
kalıcılaşmıyordu. Arayüz `!ok` yanıtta notu tutup gerekçeyi zaten gösteriyor — kusur yalnız backend'in başarı demesi.
Kapı GERÇEK kilitle: ikinci bir bağlantı `BEGIN EXCLUSIVE` ile yazma kilidini `busy_timeout`'tan (5 sn) uzun tutar (WAL —
okumalar sürer); GERÇEK `TreatmentHistoryDB`, GERÇEK `POST /api/session/notes`; not SQL ile okunur.
Arayüz yarısı: `apps/ui/src/components/domain/__tests__/ObservationNotesModal.D215.yazilamadi.web.test.tsx` bu dosyanın
ürettiği fikstürü okur (`D215_FIKSTUR_YAZ=1` ile yenilenir; bayatlarsa tazelik kapısı KIRMIZI).
"""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_KOK = Path(__file__).resolve().parents[1]
_FIKSTUR = (
    _KOK / "apps" / "ui" / "src" / "components" / "domain" / "__tests__" / "__fixtures__" / "notYazilamadi.D215.json"
)
NOT = "Sakinleşti — D215 gözlem notu"


@pytest.fixture
def o(tmp_path, monkeypatch):
    from database.treatment_history_db import TreatmentHistoryDB
    from servers import api_server as api

    db = TreatmentHistoryDB(tmp_path / "gecmis")
    monkeypatch.setattr(api, "_get_treatment_db", lambda: db)
    sid = db.start_session(treatment_mode="Manuel", target_condition=None, patient_name="Boncuk")
    db.end_session(sid, duration_minutes=4, session_status="completed")
    try:
        yield type(
            "O",
            (),
            {
                "db": db,
                "sid": sid,
                "yerel": TestClient(api.app, client=("127.0.0.1", 51234)),
                "lan": TestClient(api.app, client=("192.168.1.50", 51235)),
            },
        )
    finally:
        db.close_connections()


@contextmanager
def _yazma_kilidi(o):
    """GERÇEK kilit: başka bir bağlantı yazma kilidini tutar (WAL; okumalar sürer, yazım `busy_timeout` sonunda düşer)."""
    c = sqlite3.connect(str(o.db.db_path), timeout=1.0, isolation_level=None)
    try:
        c.execute("BEGIN EXCLUSIVE")
        yield
    finally:
        c.execute("ROLLBACK")
        c.close()


def _not(o) -> str:
    with o.db._get_connection() as c:
        return c.execute(
            "SELECT COALESCE(patient_notes, '') FROM treatment_sessions WHERE id = ?", (o.sid,)
        ).fetchone()[0]


def _govde(o):
    return {
        "session_id": o.sid,
        "notes": NOT,
        "patient_name": "Boncuk",
        "mode": "Manuel",
        "frequency": 0,
        "intensity": 0,
    }


def kilitli_yanit(o) -> dict:
    with _yazma_kilidi(o):
        r = o.yerel.post("/api/session/notes", json=_govde(o))
    return {"durum": r.status_code, "govde": r.json()}


def test_KRITIK_kilitli_DB_de_not_yazilamazsa_BASARI_DONMEZ(o):
    y = kilitli_yanit(o)
    assert _not(o) == "", "ön koşul: kilit notun yazımını engellemeli"
    assert y["durum"] >= 500 and y["govde"].get("status") != "success", f"yazılamayan not için {y} döndü"
    assert "kaydedilemedi" in str(y["govde"].get("detail") or ""), y


def test_KARSIT_kilit_kalkinca_AYNI_istek_notu_YAZAR_ve_sure_EZILMEZ(o):
    kilitli_yanit(o)
    r = o.yerel.post("/api/session/notes", json=_govde(o))
    assert r.status_code == 200 and r.json().get("status") == "success", r.text[:200]
    assert _not(o) == NOT
    with o.db._get_connection() as c:
        sure, durum = c.execute(
            "SELECT duration_minutes, session_status FROM treatment_sessions WHERE id = ?", (o.sid,)
        ).fetchone()
    assert (sure, durum) == (4, "completed"), "kapanmış seansın gerçek süresi/durumu ezildi (DENETIM P1)"


def test_KARSIT_A01_LAN_istemcisi_kilitsiz_not_yazar(o):
    r = o.lan.post("/api/session/notes", json=_govde(o))
    assert r.status_code == 200 and _not(o) == NOT, r.text[:200]


def test_KRITIK_arayuz_fiksturu_GERCEK_backend_yanitiyla_AYNI(o):
    beklenen = kilitli_yanit(o)
    if os.environ.get("D215_FIKSTUR_YAZ") == "1":
        _FIKSTUR.parent.mkdir(parents=True, exist_ok=True)
        _FIKSTUR.write_text(json.dumps(beklenen, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    assert _FIKSTUR.exists(), "arayüz fikstürü yok (D215_FIKSTUR_YAZ=1 ile üret)"
    assert json.loads(_FIKSTUR.read_text(encoding="utf-8")) == beklenen, (
        "arayüz fikstürü backend'in GERÇEK /api/session/notes hata yanıtından BAYATLADI (D215_FIKSTUR_YAZ=1 ile yenile)"
    )
