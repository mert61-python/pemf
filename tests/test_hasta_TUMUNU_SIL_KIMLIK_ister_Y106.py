# -*- coding: utf-8 -*-
"""Y106 (S-B.3 · D2.11 · A-03) — cihaz ekranındaki "Tümünü Sil" kayıtlı operatörlü klinikte SEÇİLİ operatör ister.

ÖLÇÜLEN KUSUR (2-B §3.18 açık nokta, inceleme A1/A2 ölçtü): `/api/patients/delete_all` yalnız KONUMA (A-03: cihazın kendisi)
bakıyordu; kayıtlı operatörlü klinikte kimse seçili değilken (ya da kilit sonrası) cihaz ekranından kliniğin TÜM hasta defteri
kimliksiz silinebiliyordu, iz sahipsiz (`''`) yazılıyordu — "bütün hastaları kim sildi" sorusu cevapsızdı.
SAHİP KARARI Y106: kayıtlı operatörlü klinikte seçili operatör (jeton) şart — kimliksiz 428 "Operatör seçin"; silme onun adına
kayda geçer. A-03 (yalnız cihazın kendisi) AYNEN; operatörsüz klinik (Kural 2) etkilenmez.

GERÇEK: uç (TestClient soket IP'si — cihaz 127.0.0.1 / LAN / tünel başlıkları), `operator_tokens`, `auth_db`, hasta DB'si ve denetim
izi (geçici). Ölçüt ham `SELECT COUNT(*)` ve iz satırı.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

AYSE = "dr.ayse@klinik.com"
LAN = ("192.168.1.90", 52535)
TUNEL_BASLIK = {"cf-ray": "8a1b2c3d4e5f-IST", "cf-connecting-ip": "203.0.113.9"}
ONAY = {"confirm": "DELETE_ALL"}


def _operatorleri_sil(c):
    for op in c.get("/api/operators").json().get("data", []):
        c.post("/api/operators/remove", json={"email": op["email"]})


@pytest.fixture
def o(monkeypatch, tmp_path):
    import ai_pro_aparati as apa
    from database.patient_database import PatientDatabase
    from kayitci_donanim import gercek_hc
    from servers import operator_tokens, patient_router

    o = apa.kur(monkeypatch, tmp_path)
    o.hdb = PatientDatabase(str(tmp_path / "patients.db"))
    monkeypatch.setattr(patient_router, "get_patient_database", lambda: o.hdb)
    for i in range(2):
        o.hdb.add_patient({"name": f"Hasta{i}", "species": "Kedi", "operator_email": AYSE if i else ""})
    secenek = dict(apa.ISTEMCI_SECENEKLERI)
    o.tmp = tmp_path
    o.cihaz = TestClient(o.api.app, client=("127.0.0.1", 52534), backend_options=secenek)
    o.lan = TestClient(o.api.app, client=LAN, backend_options=secenek)
    o.tunel = TestClient(o.api.app, client=("127.0.0.1", 52536), backend_options=secenek)
    operator_tokens.temizle_hepsi()
    _operatorleri_sil(o.cihaz)
    try:
        with gercek_hc() as hc:
            monkeypatch.setattr(o.api.state, "hardware", hc)
            yield o
            o.lan.post("/api/session/stop")
    finally:
        operator_tokens.temizle_hepsi()
        _operatorleri_sil(o.cihaz)
        o.geri()


def _say(o):
    with o.hdb._get_connection() as c:
        return c.execute("SELECT COUNT(*) FROM patients").fetchone()[0]


def _iz(o):
    return [(s["operator_email"], s["outcome"], s["item_count"]) for s in o.db.denetim_oku(50, "patient.delete_all")]


def _jeton(o, e=AYSE):
    r = o.cihaz.post("/api/operators/enroll", json={"email": e, "display_name": "Dr. Ayşe", "pin": "123456"})
    assert r.status_code == 200, r.text[:200]
    return o.cihaz.post("/api/operators/verify", json={"email": e, "pin": "123456"}).json()["operator_token"]


def _b(j):
    return {"X-PEMF-Operator": j} if j else {}


def test_KRITIK_kayitli_klinikte_cihazdan_KIMLIKSIZ_tumunu_sil_428_hicbiri_silinmez(o):
    _jeton(o)
    r = o.cihaz.post("/api/patients/delete_all", json=ONAY)
    assert (r.status_code, _say(o)) == (428, 2), f"kimliksiz 'Tümünü Sil' kliniği sildi: {r.status_code} {r.text[:150]}"
    assert r.json()["detail"].startswith("Operatör seçin"), r.text[:200]
    assert _iz(o) == [("", "reddedildi", 0)], _iz(o)


def test_KRITIK_KILITLE_sonrasi_eski_jetonla_tumunu_sil_428(o):
    j = _jeton(o)
    assert o.cihaz.post("/api/operators/lock", headers=_b(j)).status_code == 200
    r = o.cihaz.post("/api/patients/delete_all", json=ONAY, headers=_b(j))
    assert (r.status_code, _say(o)) == (428, 2), r.text[:200]


def test_KRITIK_kimlik_DB_OKUNAMAZKEN_tumunu_sil_428_ARIZA_iletisi(o, monkeypatch):
    from database.auth_db import get_auth_db

    _jeton(o)
    with monkeypatch.context() as m:
        m.setattr(get_auth_db(), "db_path", o.tmp / "yok_dizin" / "auth_users.db")
        r = o.cihaz.post("/api/patients/delete_all", json=ONAY)
    assert (r.status_code, _say(o)) == (428, 2), r.text[:200]
    d = r.json()["detail"]
    assert d.startswith("Cihazın kimlik veritabanı okunamıyor —") and "Operatör seçin" not in d, d


def test_KARSIT_SECILI_operatorle_cihazdan_SILER_iz_ONUN_adina(o):
    j = _jeton(o)
    r = o.cihaz.post("/api/patients/delete_all", json=ONAY, headers=_b(j))
    assert r.status_code == 200 and r.json()["deleted"] == 2, r.text[:200]
    assert _say(o) == 0
    assert _iz(o) == [(AYSE, "ok", 2)], _iz(o)


@pytest.mark.parametrize("yer", ["lan", "tunel"])
def test_KARSIT_A03_AYNEN_secili_operatorle_de_cihaz_DISINDAN_silinemez(o, monkeypatch, yer):
    from servers import auth

    j = _jeton(o)
    monkeypatch.setattr(auth, "check_token", lambda t: t == "DOGRU-TOKEN")
    basliklar = {**_b(j), "X-API-Key": "DOGRU-TOKEN", **(TUNEL_BASLIK if yer == "tunel" else {})}
    r = getattr(o, yer).post("/api/patients/delete_all", json=ONAY, headers=basliklar)
    assert r.status_code in (401, 403) and _say(o) == 2, r.text[:200]


def test_KARSIT_KURAL2_operatorsuz_klinikte_cihazdan_kimliksiz_SILER(o):
    r = o.cihaz.post("/api/patients/delete_all", json=ONAY)
    assert r.status_code == 200 and r.json()["deleted"] == 2 and _say(o) == 0, r.text[:200]


def test_KARSIT_onay_dizesi_kapisi_KORUNUR(o):
    j = _jeton(o)
    r = o.cihaz.post("/api/patients/delete_all", json={}, headers=_b(j))
    assert r.status_code == 400 and _say(o) == 2, r.text[:200]


def test_KARSIT_kimliksiz_durumda_ACIL_DURDUR_ve_STOP_kapisiz(o):
    _jeton(o)
    assert o.cihaz.post("/api/patients/delete_all", json=ONAY).status_code == 428
    assert o.cihaz.post("/api/session/stop", json={}).status_code == 200
    assert o.cihaz.post("/api/hardware/emergency_stop").status_code == 200
