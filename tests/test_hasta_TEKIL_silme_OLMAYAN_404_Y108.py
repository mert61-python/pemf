# -*- coding: utf-8 -*-
"""Y108 (S-B.5 · O-B.8) — var olmayan hastanın tekil silinmesi 404 döner (seans uçlarıyla aynı — D2.43).

ÖLÇÜLEN DURUM (2-B §6 O-B.8): `DELETE /api/patients/{id}` ve `POST /api/patients/{id}/delete` olmayan kimlikte `200 {"status":
"error"}` dönüyordu; arayüz bunu genel "Hasta silinemedi." hatası sayıyordu (başka sekmede / telefonda zaten silinmiş hasta için
operatör "silme çalışmıyor" sanıyordu). Seans uçları D2.43'ten beri 404 "zaten silinmiş olabilir; listeyi yenileyin".
SAHİP KARARI Y108: olmayan hasta → 404; arayüz "zaten silinmiş" der ve listeyi yeniler. Kimliksize varlık bilgisi verilmez
(D2.43 sırası: önce kimlik 428, sonra varlık 404). Var olan kaydın silinememesi 404 DEĞİL (500 — gerçek arıza gizlenmez).

GERÇEK: uçlar (TestClient — LAN / yerel), `operator_tokens`, `auth_db`, hasta DB'si ve denetim izi (geçici). Ölçüt ham satır sayısı.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

AYSE = "dr.ayse@klinik.com"
OLMAYAN = "00000000-0000-0000-0000-000000000000"


@pytest.fixture
def o(tmp_path, monkeypatch):
    from database.patient_database import PatientDatabase
    from database.treatment_history_db import TreatmentHistoryDB
    from servers import api_server as api
    from servers import operator_tokens, patient_router

    hdb = PatientDatabase(str(tmp_path / "patients.db"))
    tdb = TreatmentHistoryDB(tmp_path / "gecmis")
    monkeypatch.setattr(patient_router, "get_patient_database", lambda: hdb)
    monkeypatch.setattr(api, "_get_treatment_db", lambda: tdb)
    yerel = TestClient(api.app, client=("127.0.0.1", 53134))
    lan = TestClient(api.app, client=("192.168.1.96", 53135))

    def _sil():
        for op in yerel.get("/api/operators").json().get("data", []):
            yerel.post("/api/operators/remove", json={"email": op["email"]})

    operator_tokens.temizle_hepsi()
    _sil()
    try:
        yield type("O", (), {"hdb": hdb, "tdb": tdb, "yerel": yerel, "lan": lan})
    finally:
        operator_tokens.temizle_hepsi()
        _sil()
        tdb.close_connections()


def _say(o):
    with o.hdb._get_connection() as c:
        return c.execute("SELECT COUNT(*) FROM patients").fetchone()[0]


def _iz(o):
    return [(s["operator_email"], s["outcome"]) for s in o.tdb.denetim_oku(50, "patient.delete")]


def _jeton(o):
    r = o.yerel.post("/api/operators/enroll", json={"email": AYSE, "display_name": "A", "pin": "123456"})
    assert r.status_code == 200, r.text[:200]
    return o.yerel.post("/api/operators/verify", json={"email": AYSE, "pin": "123456"}).json()["operator_token"]


def _sil_iki_uc(istemci, pid, h):
    return [
        istemci.delete(f"/api/patients/{pid}", headers=h),
        istemci.post(f"/api/patients/{pid}/delete", json={}, headers=h),
    ]


@pytest.mark.parametrize("kip", ["kayitli_jetonlu", "kural2"])
def test_KRITIK_OLMAYAN_hasta_iki_uctan_404_zaten_silinmis_baska_hasta_DURUR(o, kip):
    h = {"X-PEMF-Operator": _jeton(o)} if kip == "kayitli_jetonlu" else {}
    o.hdb.add_patient({"name": "Kalan", "species": "Kedi", "operator_email": AYSE if h else ""})
    for r in _sil_iki_uc(o.lan, OLMAYAN, h):
        assert r.status_code == 404, f"{kip}: olmayan hasta {r.status_code} {r.text[:150]}"
        assert "zaten silinmiş" in r.json().get("detail", ""), r.text[:200]
    assert _say(o) == 1
    assert [s for _e, s in _iz(o)] == ["bulunamadi", "bulunamadi"], _iz(o)


def test_KARSIT_KIMLIKSIZE_varlik_bilgisi_VERILMEZ_once_428(o):
    _jeton(o)
    for r in _sil_iki_uc(o.lan, OLMAYAN, {}):
        assert r.status_code == 428, r.text[:200]


def test_KARSIT_VAR_OLAN_kendi_hastasi_200_silinir(o):
    h = {"X-PEMF-Operator": _jeton(o)}
    p1 = o.hdb.add_patient({"name": "A1", "species": "Kedi", "operator_email": AYSE})
    p2 = o.hdb.add_patient({"name": "A2", "species": "Kedi", "operator_email": AYSE})
    r1 = o.lan.delete(f"/api/patients/{p1}", headers=h)
    r2 = o.lan.post(f"/api/patients/{p2}/delete", json={}, headers=h)
    assert [r1.status_code, r2.status_code] == [200, 200] and _say(o) == 0, (r1.text[:120], r2.text[:120])
    assert r1.json()["status"] == "success"


def test_KARSIT_VAR_OLAN_kayit_silinemezse_404_DEGIL_500(o, monkeypatch):
    """Gerçek arıza 'zaten silinmiş' diye gizlenmez (kayıt DURUYOR — liste yenilense yine görünür)."""
    p = o.hdb.add_patient({"name": "Inatci", "species": "Kedi", "operator_email": ""})
    monkeypatch.setattr(o.hdb, "delete_patient", lambda _pid: False)
    r = o.lan.delete(f"/api/patients/{p}")
    assert r.status_code == 500 and "zaten silinmiş" not in r.text and _say(o) == 1, r.text[:200]


def test_KARSIT_ACIL_DURDUR_ve_STOP_kapisiz(o):
    assert o.lan.post("/api/session/stop", json={}).status_code == 200
    assert o.lan.post("/api/hardware/emergency_stop").status_code == 200
