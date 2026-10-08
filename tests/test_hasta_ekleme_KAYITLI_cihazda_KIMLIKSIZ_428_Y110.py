# -*- coding: utf-8 -*-
"""Y110 (S-B2.2 · B2-2.7 · A-61) — kayıtlı operatörlü cihazda KİMLİKSİZ YENİ hasta eklemesi arka uçta 428.

ÖLÇÜLEN KUSUR (2-B incelemesi, A2): A-61 "hasta eklemek KİMLİK ister; kimliksiz eklenen hasta başkalarının 'Benim' listesine
düşmez". 2-B (`f9280c9`) yalnız YENİ arayüzde isteği engelledi; arka uçta (D2.41 + Y109) kimliksiz istek (eski APK, LAN'dan elle
istek, kilit sonrası eski jeton) SAHİPSİZ hasta açıyordu (200) — arayüzün kapsam tek kaynağı (`patientScope.inScope`) sahipsiz
kaydı kliniğin HER hekiminin "Benim" listesinde sayar.
SAHİP KARARI Y110: kayıtlı operatörlü cihazda kimliksiz YENİ hasta → 428 "Operatör seçin" (kimlik DB'si okunamıyorsa Y113 iletisi);
operatörsüz klinik (Kural 2) ve hasta GÜNCELLEME değişmez.

GERÇEK: uçlar (TestClient — LAN 192.168.1.89 / yerel), `operator_tokens`, `auth_db` operatörleri, hasta DB'si (geçici); ölçüt ham
`SELECT COUNT(*)`.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

AYSE = "dr.ayse@klinik.com"
ORTAK = "klinik@ortak-giris.com"
TEK = "tek@klinik.com"
LAN = ("192.168.1.89", 52435)


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
    secenek = dict(apa.ISTEMCI_SECENEKLERI)
    o.tmp = tmp_path
    o.yerel = TestClient(o.api.app, client=("127.0.0.1", 52434), backend_options=secenek)
    o.lan = TestClient(o.api.app, client=LAN, backend_options=secenek)
    operator_tokens.temizle_hepsi()
    _operatorleri_sil(o.yerel)
    try:
        with gercek_hc() as hc:
            monkeypatch.setattr(o.api.state, "hardware", hc)
            yield o
            o.lan.post("/api/session/stop")
    finally:
        operator_tokens.temizle_hepsi()
        _operatorleri_sil(o.yerel)
        o.geri()


def _say(o):
    with o.hdb._get_connection() as c:
        return c.execute("SELECT COUNT(*) FROM patients").fetchone()[0]


def _sahip(o, pid):
    return next((h.get("operator_email") or "") for h in o.hdb.get_all_patients() if str(h["id"]) == str(pid))


def _jeton(o, e=AYSE):
    r = o.yerel.post("/api/operators/enroll", json={"email": e, "display_name": "Dr. Ayşe", "pin": "123456"})
    assert r.status_code == 200, r.text[:200]
    return o.yerel.post("/api/operators/verify", json={"email": e, "pin": "123456"}).json()["operator_token"]


def _ekle(istemci, beyan, jeton=""):
    return istemci.post(
        "/api/patients",
        json={"name": "Boncuk", "species": "Kedi", "operator_email": beyan},
        headers={"X-PEMF-Operator": jeton} if jeton else {},
    )


@pytest.mark.parametrize(
    "beyan",
    ["", AYSE, ORTAK, AYSE + "​"],
    ids=["bos_beyan_eski_apk", "kanitsiz_kayitli_beyan", "kayitsiz_ortak_giris", "gorsel_es"],
)
@pytest.mark.parametrize("istemci", ["lan", "yerel"])
def test_KRITIK_kayitli_cihazda_KIMLIKSIZ_yeni_hasta_428_satir_YOK(o, beyan, istemci):
    _jeton(o)
    once = _say(o)
    r = _ekle(getattr(o, istemci), beyan)
    assert (r.status_code, _say(o)) == (428, once), (
        f"kimliksiz hasta açıldı (kliniğin her hekiminin 'Benim' listesine düşer): {r.status_code} {r.text[:150]}"
    )
    assert r.json().get("detail", "").startswith("Operatör seçin"), r.text[:200]


def test_KRITIK_KILITLE_sonrasi_eski_jetonla_yeni_hasta_428(o):
    j = _jeton(o)
    assert o.lan.post("/api/operators/lock", headers={"X-PEMF-Operator": j}).status_code == 200
    once = _say(o)
    r = _ekle(o.lan, AYSE, j)
    assert (r.status_code, _say(o)) == (428, once), r.text[:200]


def test_KRITIK_kimlik_DB_OKUNAMAZKEN_yeni_hasta_428_ARIZA_iletisi(o, monkeypatch):
    """Y113 ile tutarlı: kimlik DB'si okunamıyorsa da kapı KAPALI; ileti arızayı ve çareyi söyler, "Operatör seçin" demez."""
    from database.auth_db import get_auth_db

    _jeton(o)
    once = _say(o)
    with monkeypatch.context() as m:
        m.setattr(get_auth_db(), "db_path", o.tmp / "yok_dizin" / "auth_users.db")
        r = _ekle(o.lan, "")
    assert (r.status_code, _say(o)) == (428, once), r.text[:200]
    d = r.json().get("detail", "")
    assert d.startswith("Cihazın kimlik veritabanı okunamıyor —") and "Operatör seçin" not in d, d


def test_KARSIT_A01_LAN_jetonlu_ekleme_jeton_SAHIBINE(o):
    j = _jeton(o)
    r = _ekle(o.lan, ORTAK, j)
    assert r.status_code == 200 and r.json()["status"] == "success", r.text[:200]
    assert _sahip(o, r.json()["patient_id"]) == AYSE


@pytest.mark.parametrize("beyan", [TEK, ""], ids=["beyanli", "bos_beyan_eski_istemci"])
def test_KARSIT_KURAL2_operatorsuz_klinikte_eklenir(o, beyan):
    r = _ekle(o.lan, beyan)
    assert r.status_code == 200 and r.json()["status"] == "success", r.text[:200]
    assert _sahip(o, r.json()["patient_id"]) == beyan


def test_KARSIT_GUNCELLEME_yolu_DEGISMEZ_kimliksiz_de_guncellenir_sahip_degismez(o):
    pid = o.hdb.add_patient({"name": "Eski", "species": "Kedi", "operator_email": AYSE})
    _jeton(o)
    r = o.lan.post(
        "/api/patients", json={"id": str(pid), "name": "Eski-Yeni", "species": "Kedi", "operator_email": ORTAK}
    )
    assert r.status_code == 200 and r.json()["status"] == "success", r.text[:200]
    h = next(h for h in o.hdb.get_all_patients() if str(h["id"]) == str(pid))
    assert (h.get("name"), h.get("operator_email")) == ("Eski-Yeni", AYSE)


def test_KARSIT_kimliksiz_durumda_ACIL_DURDUR_ve_STOP_kapisiz(o):
    _jeton(o)
    assert _ekle(o.lan, "").status_code == 428
    assert o.lan.post("/api/session/stop", json={}).status_code == 200
    assert o.lan.post("/api/hardware/emergency_stop").status_code == 200
