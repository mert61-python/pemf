# -*- coding: utf-8 -*-
"""S-A1.3 (a) [ÖNERİLEN UYGULANDI — Y123] (2-C incelemesi, A1 kapsam 8) — kayıtlı operatörlü cihazda JETONSUZ LAN isteği
`/api/ai/log`'da hasta KİMLİĞİNDEN ADI öğrenemez.

ÖLÇÜLEN (A1 `kayit/k8_sonda.txt`, HEAD 1cd770c): kayıtlı operatörlü cihazda kimliksiz LAN istemcisi Dr. B'nin hastasının kimliğiyle
`patient_name: ""` gönderince D2.69 ad doldurması satıra `Karabas` yazıyor; `GET /api/ai/log` (A-02, jetonsuz LAN) adı geri veriyor —
Y103 ile aynı istemciye kapalı olan hasta listesinin vermediği ad kimlikten öğreniliyordu (kimlik→ad kâhini).
KURAL: jetonlu hekim, operatörsüz klinik (Kural 2) ve cihazın kendi ekranı DEĞİŞMEZ (ad doldurulur); kayıtlı operatörlü cihazda
jetonsuz LAN isteğinde ad DOLDURULMAZ — kayıt yine kimlikle yazılır (D2.56: kayıt düşmez). Kimlik DB'si okunamazsa doldurulmaz.
Satır SQL ile okunur.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

KARABAS = "u-karabas-0001"
LAN = ("192.168.1.85", 52135)
YEREL = ("127.0.0.1", 52134)
AYSE = "dr.ayse@klinik.com"


@pytest.fixture
def o(tmp_path, monkeypatch):
    from database.patient_database import PatientDatabase
    from database.treatment_history_db import TreatmentHistoryDB
    from servers import api_server, operator_tokens

    class O:
        pass

    o = O()
    kok = tmp_path / "gecmis"
    kok.mkdir()
    o.d = TreatmentHistoryDB(kok)
    hdb = PatientDatabase(str(tmp_path / "patients.db"))
    monkeypatch.setattr(api_server, "_get_treatment_db", lambda: o.d)
    monkeypatch.setattr(api_server, "_app_data_dir", lambda: kok)
    monkeypatch.setattr("database.patient_database.get_patient_database", lambda: hdb)
    monkeypatch.setattr(api_server, "_ai_kimlik_tasindi", True)  # tek seferlik taşıma bu kapının konusu değil
    o.pid = hdb.add_patient({"name": "Karabas", "species": "Kedi", "id": KARABAS})
    o.lan = TestClient(api_server.app, client=LAN)
    o.yerel = TestClient(api_server.app, client=YEREL)
    operator_tokens.temizle_hepsi()
    o.jeton = None
    yield o
    operator_tokens.temizle_hepsi()
    for op in (o.yerel.get("/api/operators").json() or {}).get("data", []) or []:
        o.yerel.post("/api/operators/remove", json={"email": op["email"]})


def _kayitli_yap(o):
    r = o.yerel.post("/api/operators/enroll", json={"email": AYSE, "display_name": "Ayşe", "pin": "123456"})
    assert r.status_code == 200, r.text[:200]
    o.jeton = r.json()["operator_token"]


def _yaz(o, c, baslik=None):
    r = c.post(
        "/api/ai/log",
        json={"patient_name": "", "patient_id": o.pid, "module": "FGS", "summary": "s", "module_id": "landmark"},
        headers=baslik or {},
    )
    assert r.status_code == 200 and r.json().get("status") == "success", r.text[:200]
    with o.d._get_connection() as conn:
        return tuple(conn.execute("SELECT patient_uuid, patient_name FROM ai_analyses ORDER BY id DESC").fetchone())


def test_KRITIK_kayitli_klinikte_JETONSUZ_LAN_istegi_ADI_kimlikten_OGRENEMEZ_kayit_DUSMEZ(o):
    _kayitli_yap(o)
    assert _yaz(o, o.lan) == (o.pid, ""), (
        "jetonsuz LAN isteği kayıtlı klinikte hasta adını kimlikten öğrendi (Y103 kâhini)"
    )


def test_KARSIT_kayitli_klinikte_JETONLU_hekimin_kaydi_ADLANIR(o):
    _kayitli_yap(o)
    assert _yaz(o, o.lan, {"X-PEMF-Operator": o.jeton}) == (o.pid, "Karabas")


def test_KARSIT_kayitli_klinikte_CIHAZIN_KENDI_ekrani_ADLANIR(o):
    _kayitli_yap(o)
    assert _yaz(o, o.yerel) == (o.pid, "Karabas")


def test_KARSIT_operatorsuz_klinikte_Kural2_LAN_istegi_ADLANIR(o):
    assert _yaz(o, o.lan) == (o.pid, "Karabas")


def test_KARSIT_kimlik_DB_okunamazsa_DOLDURULMAZ_fail_closed(o, monkeypatch):
    from servers import auth

    monkeypatch.setattr(auth, "kayitli_operator_var", lambda: (_ for _ in ()).throw(RuntimeError("okunamadı")))
    assert _yaz(o, o.lan) == (o.pid, "")
