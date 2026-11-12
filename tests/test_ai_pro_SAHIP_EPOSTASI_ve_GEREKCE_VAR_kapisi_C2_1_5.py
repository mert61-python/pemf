# -*- coding: utf-8 -*-
"""C2-1.5 (2-C inceleme, A1) — KÖR KAPI: D2.E15'in "elle seans yoluyla AYNI bağ" iddiasının `patient_owner_email` kolu ve
O-A2.2'nin `gerekce_var` DEĞERİ hiçbir kapıda ölçülmüyor.

Ölçülen (A1 mutantları, `_inceleme/kayit/k1_mutasyon.txt`): k1m2 `start_ai_session`'da sahip e-postası araması kaldırılır
(`_sahip_epostasi = ""`) → E15/E07 + O-A2.2 + E06 kapıları 15/15 YEŞİL; k1m5 red izinde `gerekce_var` gerekçeden değil
operatör alanından hesaplanır → 15/15 YEŞİL. Bu kapı ikisini GERÇEK uçlarla (`/propose` → `/approve` → `/start`; `/reject`)
ve SQL ile ölçer. HEAD'de YEŞİL (ürün doğru); iki mutantta KIRMIZI olmalı.
"""

from __future__ import annotations

import json
import time

import pytest
from kd_kalibrasyon_yardimci import (
    odak_tahminci,  # noqa: F401  ODK5: kedi önerisi de ODAK'tan — sahte, eski doz kanıtına bağlar
)


@pytest.fixture
def o(monkeypatch, tmp_path):
    import ai_pro_aparati as ap
    from database.patient_database import PatientDatabase
    from kayitci_donanim import gercek_hc
    from servers import operator_tokens

    o = ap.kur(monkeypatch, tmp_path)
    o.pdb = PatientDatabase(str(tmp_path / "patients.db"))
    monkeypatch.setattr(o.api, "get_patient_database", lambda *a, **k: o.pdb)
    monkeypatch.setattr("database.patient_database.get_patient_database", lambda *a, **k: o.pdb)
    operator_tokens.temizle_hepsi()
    try:
        with gercek_hc() as hc:
            monkeypatch.setattr(o.api.state, "hardware", hc)
            o.hc = hc
            yield o
            o.c.post("/api/ai/pro/stop")
    finally:
        o.air._ai_loop_active = False
        o.geri()


def _taze(air, organ=2):
    air._ai_organ_id = organ
    with air._ai_cache_lock:
        air._ai_organ_cache.update(
            {
                "x_mm": 1.0,
                "y_mm": 2.0,
                "z_mm": 3.0,
                "reliability": 0.9,
                "localized": True,
                "overlay_bgr": None,
                "at": time.time(),
                "organ_id": organ,
                "kedi_var": True,
                "guven_dokumu": None,
                "model": "kedi",
            }
        )


def _oner(o, ek):
    _taze(o.air)
    r = o.c.post("/api/ai/pro/propose", json={"organ_id": 2, "duration_minutes": 5, **ek})
    assert r.status_code == 200, r.text[:200]
    return r.json()["proposalId"]


def test_KRITIK_C2_1_5_AI_Pro_seansi_HASTA_SAHIBININ_epostasini_tasir(o):
    hid = o.pdb.add_patient({"name": "Boncuk", "species": "Kedi", "owner_email": "sahip@ornek.com"})
    pid = _oner(o, {"patient_id": hid, "patient_name": "Boncuk"})
    assert o.c.post("/api/ai/pro/approve", json={"proposal_id": pid, "operator_email": "h@k.com"}).status_code == 200
    assert o.c.post("/api/ai/pro/start", json={"proposal_id": pid}).status_code == 200
    with o.api._session_lock:
        sid = o.api._active_session.get("db_session_id")
    with o.db._get_connection() as c:
        par = [
            r[0]
            for r in c.execute(
                "SELECT parameter_value FROM session_parameters WHERE session_id=? AND parameter_name='patient_owner_email'",
                (sid,),
            ).fetchall()
        ]
    assert par == ["sahip@ornek.com"], f"AI Pro seansı hasta sahibinin e-postasını taşımıyor: {par}"


def test_KRITIK_C2_1_5_gerekcesiz_red_izinde_gerekce_var_YANLIS(o):
    pid = _oner(o, {})
    assert (
        o.c.post(
            "/api/ai/pro/reject", json={"proposal_id": pid, "operator_email": "h@k.com", "reason": "   "}
        ).status_code
        == 200
    )
    with o.db._get_connection() as c:
        yuk = c.execute(
            "SELECT payload FROM session_events WHERE event_type='ai_proposal_rejected' ORDER BY id DESC LIMIT 1"
        ).fetchone()[0]
    assert json.loads(yuk).get("gerekce_var") is False, f"gerekçesiz red 'gerekce_var' True yazıldı: {yuk}"
