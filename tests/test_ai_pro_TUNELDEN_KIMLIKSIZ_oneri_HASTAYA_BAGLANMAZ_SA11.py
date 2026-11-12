# -*- coding: utf-8 -*-
"""S-A1.1 (a) [ÖNERİLEN UYGULANDI — Y123] (2-C incelemesi, A1 kapsam 1 (v)) — tünelden / ters-proxy'den KİMLİKSİZ gelen AI Pro
önerisi hastaya BAĞLANMAZ; AI Pro tünel ERİŞİMİ değişmez.

ÖLÇÜLEN (A1 `kayit/k1_sonda_v2.txt`, HEAD 1cd770c): saha kimlik kipinde (`auth._require=True`) tünelden (cf-*) jetonsuz `/propose`
(başka hekimin hastasının kimliği) → `/approve` → `/start` 200 → satır `('active','Karabas','dr.x@…',<B'nin uuid'i>,
'sahip.b@ornek.com')`; aynı tünelden ELLE `/api/session/start` 401. D2.E15 öncesi AI Pro satırı sahipsizdi.
KURAL: uzak (cf-connecting-ip / cf-ray / X-Forwarded-For) istek NE geçerli operatör jetonu NE geçerli cihaz token'ı taşıyorsa öneri
mühründe hasta YOK (seans sahipsiz açılır, tedavi engellenmez). Jetonlu ya da cihaz token'lı uzak istek, LAN (A-01) ve cihazın
kendisi DEĞİŞMEZ. Satır SQL ile okunur.
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient
from kd_kalibrasyon_yardimci import (
    odak_tahminci,  # noqa: F401  ODK5: kedi önerisi de ODAK'tan — sahte, eski doz kanıtına bağlar
)

TUNEL = {"cf-ray": "8a1b2c3d4e5f-IST", "cf-connecting-ip": "203.0.113.9"}
LAN = ("192.168.1.85", 52135)
YEREL = ("127.0.0.1", 52134)


@pytest.fixture
def o(monkeypatch, tmp_path):
    import ai_pro_aparati as ap
    from database.patient_database import PatientDatabase
    from kayitci_donanim import gercek_hc
    from servers import operator_tokens

    o = ap.kur(monkeypatch, tmp_path)
    operator_tokens.temizle_hepsi()
    pdb = PatientDatabase(str(tmp_path / "patients.db"))
    monkeypatch.setattr(o.api, "get_patient_database", lambda *a, **k: pdb)
    monkeypatch.setattr("database.patient_database.get_patient_database", lambda *a, **k: pdb)
    o.hasta = pdb.add_patient({"name": "Karabas", "species": "Kedi", "owner_email": "sahip.b@ornek.com"})
    o.yerel = TestClient(o.api.app, client=YEREL)
    try:
        with gercek_hc() as hc:
            monkeypatch.setattr(o.api.state, "hardware", hc)
            o.hc = hc
            yield o
            o.c.post("/api/ai/pro/stop")
    finally:
        o.air._ai_loop_active = False
        operator_tokens.temizle_hepsi()
        for op in (o.yerel.get("/api/operators").json() or {}).get("data", []) or []:
            o.yerel.post("/api/operators/remove", json={"email": op["email"]})
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


def _oner_onayla_baslat(o, c, baslik=None, onay_eposta="dr.x@klinik.com"):
    _taze(o.air)
    r1 = c.post(
        "/api/ai/pro/propose",
        json={"organ_id": 2, "duration_minutes": 5, "patient_id": o.hasta, "patient_name": "Karabas"},
        headers=baslik or {},
    )
    assert r1.status_code == 200, r1.text[:300]
    pid = r1.json()["proposalId"]
    r2 = c.post("/api/ai/pro/approve", json={"proposal_id": pid, "operator_email": onay_eposta}, headers=baslik or {})
    assert r2.status_code == 200, r2.text[:300]
    r3 = c.post("/api/ai/pro/start", json={"proposal_id": pid}, headers=baslik or {})
    assert r3.status_code == 200, r3.text[:300]
    with o.api._session_lock:
        sid = o.api._active_session.get("db_session_id")
    with o.db._get_connection() as conn:
        satir = conn.execute(
            "SELECT p.patient_uuid, s.patient_name FROM treatment_sessions s LEFT JOIN patients p ON p.id = s.patient_id "
            "WHERE s.id = ?",
            (sid,),
        ).fetchone()
        sahip = [
            r[0]
            for r in conn.execute(
                "SELECT parameter_value FROM session_parameters WHERE session_id = ? AND "
                "parameter_name = 'patient_owner_email'",
                (sid,),
            ).fetchall()
        ]
    return r1.json()["specs"], (tuple(satir) if satir else None), sahip


def test_KRITIK_saha_kipinde_TUNELDEN_KIMLIKSIZ_oneri_HASTAYA_baglanmaz_erisim_DEGISMEZ(o, monkeypatch):
    from servers import auth

    monkeypatch.setattr(auth, "_require", True, raising=False)
    specs, satir, sahip = _oner_onayla_baslat(o, o.c, TUNEL)
    assert (specs.get("patient_id"), specs.get("patient_name")) == ("", ""), f"mühürde hasta var: {specs}"
    assert satir is not None and satir[0] is None, f"kimliksiz tünel AI Pro'su hastanın kaydına bağlandı: {satir}"
    assert sahip == [], f"hasta sahibinin e-postası kimliksiz tünel seansına yazıldı: {sahip}"


def test_KARSIT_TUNELDEN_CIHAZ_TOKENLI_oneri_BAGLANIR(o, monkeypatch):
    from servers import auth

    monkeypatch.setattr(auth, "_require", True, raising=False)
    specs, satir, sahip = _oner_onayla_baslat(o, o.c, {**TUNEL, "X-API-Key": auth.get_api_token()})
    assert specs.get("patient_id") == o.hasta
    assert satir is not None and satir[0] == o.hasta and sahip == ["sahip.b@ornek.com"], (satir, sahip)


def test_KARSIT_TUNELDEN_OPERATOR_JETONLU_oneri_BAGLANIR(o):
    r = o.yerel.post("/api/operators/enroll", json={"email": "dr.a@klinik.com", "display_name": "A", "pin": "123456"})
    assert r.status_code == 200, r.text[:200]
    jeton = r.json()["operator_token"]
    specs, satir, _ = _oner_onayla_baslat(o, o.c, {**TUNEL, "X-PEMF-Operator": jeton}, onay_eposta="dr.a@klinik.com")
    assert specs.get("patient_id") == o.hasta and satir is not None and satir[0] == o.hasta, (specs, satir)


def test_KARSIT_A01_LAN_jetonsuz_oneri_BUGUNKU_GIBI_baglanir(o):
    lan = TestClient(o.api.app, client=LAN)
    specs, satir, _ = _oner_onayla_baslat(o, lan)
    assert specs.get("patient_id") == o.hasta and satir is not None and satir[0] == o.hasta, (specs, satir)
