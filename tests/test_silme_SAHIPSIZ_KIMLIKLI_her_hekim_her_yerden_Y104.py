# -*- coding: utf-8 -*-
"""Y104 (S-B.1 · D2.72 sonucu — sahip kararı ÖNERİLENDEN FARKLI) — kayıtlı operatörlü klinikte SAHİPSİZ hasta ve seans kayıtları
KİMLİKLİ her hekim tarafından HER YERDEN (cihaz, telefon/LAN, tünel) tekil ve toplu silinebilir; iz o hekimin adına.

ÖLÇÜLEN DURUM (2-B §3.16 sonucu): Y92 "yalnız KENDİ kayıtları" harfiyen uygulanınca kayıtlı operatörlü klinikte SAHİPSİZ kayıtlar
ve operatörler kurulmadan ÖNCE ortak giriş e-postasıyla yazılmış kayıtlar hiçbir hekim tarafından silinemiyordu (403); tek yol
cihaz ekranından "Tümünü Sil" (tüm defter) idi.
SAHİP KARARI Y104: sahipsiz = sahibi boş/NULL YA DA cihazda KAYITLI OLMAYAN bir e-posta (paylaşılan giriş, kayıt dışı adres) —
kimlikli (JETONLU; gövde beyanı sayılmaz — Y109) her hekim her yerden siler, iz onun adına. Başka (kayıtlı) hekimin kaydı 403
KALIR (Y92, atomik). Kimliksiz 428. ⚠️ Risk kaydı (sahip): geri dönüşsüz silme yüzeyi geniş.
Kimlik DB'si okunamazken (arıza öncesi jetonla) yalnız sahibi BOŞ kayıt silinir; sahibinin kayıtlı olup olmadığı BİLİNEMEYEN
kayıt 403 (fail-closed).

GERÇEK: uçlar (TestClient — yerel / LAN 192.168.1.91 / tünel `cf-ray`+`cf-connecting-ip`, saha kimlik kipi + geçerli cihaz
token'ı), `operator_tokens`, `auth_db`, hasta + tedavi DB'leri (geçici). Ölçüt ham `SELECT COUNT(*)` ve iz satırı.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

AYSE = "dr.ayse@klinik.com"
MEHMET = "dr.mehmet@klinik.com"
ORTAK = "klinik@ortak-giris.com"  # operatörler kurulmadan önce paylaşılan giriş — cihazda KAYITLI DEĞİL
TUNEL_BASLIK = {"cf-ray": "8a1b2c3d4e5f-IST", "cf-connecting-ip": "203.0.113.9", "X-API-Key": "DOGRU-TOKEN"}


@pytest.fixture
def o(tmp_path, monkeypatch):
    from database.patient_database import PatientDatabase
    from database.treatment_history_db import TreatmentHistoryDB
    from servers import api_server as api
    from servers import auth, operator_tokens, patient_router
    from servers.history_router import get_db

    hdb = PatientDatabase(str(tmp_path / "patients.db"))
    tdb = TreatmentHistoryDB(tmp_path / "gecmis")
    monkeypatch.setattr(patient_router, "get_patient_database", lambda: hdb)
    monkeypatch.setattr(api, "_get_treatment_db", lambda: tdb)
    monkeypatch.setattr(auth, "check_token", lambda t: t == "DOGRU-TOKEN")
    api.app.dependency_overrides[get_db] = lambda: tdb
    yerel = TestClient(api.app, client=("127.0.0.1", 52634))
    lan = TestClient(api.app, client=("192.168.1.91", 52635))
    tunel = TestClient(api.app, client=("127.0.0.1", 52636))

    def _sil():
        for op in yerel.get("/api/operators").json().get("data", []):
            yerel.post("/api/operators/remove", json={"email": op["email"]})

    operator_tokens.temizle_hepsi()
    _sil()
    try:
        yield type("O", (), {"hdb": hdb, "tdb": tdb, "yerel": yerel, "lan": lan, "tunel": tunel, "tmp": tmp_path})
    finally:
        api.app.dependency_overrides.pop(get_db, None)
        operator_tokens.temizle_hepsi()
        _sil()
        tdb.close_connections()


def _iki_hekim(o):
    j = {}
    for e in (AYSE, MEHMET):
        r = o.yerel.post("/api/operators/enroll", json={"email": e, "display_name": e, "pin": "123456"})
        assert r.status_code == 200, r.text[:200]
        j[e] = o.yerel.post("/api/operators/verify", json={"email": e, "pin": "123456"}).json()["operator_token"]
    return j


def _b(jeton, yer="lan"):
    h = {"X-PEMF-Operator": jeton} if jeton else {}
    return {**h, **TUNEL_BASLIK} if yer == "tunel" else h


class _Hasta:
    ad = "hasta"
    iz_toplu, iz_tekil = "patient.delete_bulk", "patient.delete"

    @staticmethod
    def tohum(o, sahip, n=1):
        return [
            str(o.hdb.add_patient({"name": f"P-{sahip or 'sahipsiz'}-{i}", "species": "Kedi", "operator_email": sahip}))
            for i in range(n)
        ]

    @staticmethod
    def var_olan(o, kimlikler):
        with o.hdb._get_connection() as c:
            yer = ",".join("?" for _ in kimlikler)
            return c.execute(f"SELECT COUNT(*) FROM patients WHERE id IN ({yer})", list(kimlikler)).fetchone()[0]

    @staticmethod
    def toplu(o, istemci, kimlikler, basliklar):
        return istemci.post(
            "/api/patients/delete_bulk",
            json={"patient_ids": kimlikler, "confirm": "DELETE_SELECTED"},
            headers=basliklar,
        )

    @staticmethod
    def tekiller(o, istemci, k1, k2, basliklar):
        return [
            istemci.delete(f"/api/patients/{k1}", headers=basliklar),
            istemci.post(f"/api/patients/{k2}/delete", json={}, headers=basliklar),
        ]


class _Seans:
    ad = "seans"
    iz_toplu, iz_tekil = "history.delete_bulk", "history.delete"

    @staticmethod
    def tohum(o, sahip, n=1):
        return [
            int(o.tdb.start_session(treatment_mode="Manuel", patient_name=f"S-{i}", operator_email=sahip or None))
            for i in range(n)
        ]

    @staticmethod
    def var_olan(o, kimlikler):
        with o.tdb._get_connection() as c:
            yer = ",".join("?" for _ in kimlikler)
            return c.execute(
                f"SELECT COUNT(*) FROM treatment_sessions WHERE id IN ({yer})", list(kimlikler)
            ).fetchone()[0]

    @staticmethod
    def toplu(o, istemci, kimlikler, basliklar):
        return istemci.post(
            "/api/history/delete_bulk", json={"session_ids": kimlikler, "confirm": "DELETE_SELECTED"}, headers=basliklar
        )

    @staticmethod
    def tekiller(o, istemci, k1, k2, basliklar):
        return [
            istemci.delete(f"/api/history/{k1}", headers=basliklar),
            istemci.post("/api/history/delete", json={"session_id": k2}, headers=basliklar),
        ]


TURLER = pytest.mark.parametrize("t", [_Hasta, _Seans], ids=["hasta", "seans"])
YERLER = pytest.mark.parametrize("yer", ["yerel", "lan", "tunel"])


def _iz(o, olay):
    return [(s["operator_email"], s["outcome"], s["item_count"]) for s in o.tdb.denetim_oku(200, olay)]


@TURLER
@YERLER
def test_KRITIK_SAHIPSIZ_ve_ORTAK_GIRIS_kayitlari_KIMLIKLI_hekim_HER_YERDEN_toplu_siler_iz_ONUN(o, monkeypatch, t, yer):
    from servers import auth

    j = _iki_hekim(o)
    if yer == "tunel":
        monkeypatch.setattr(auth, "_require", True)  # saha kimlik kipi: tünel isteği cihaz token'ı ister
    hedef = t.tohum(o, "", 2) + t.tohum(o, ORTAK, 2) + t.tohum(o, AYSE)
    r = t.toplu(o, getattr(o, yer), hedef, _b(j[AYSE], yer))
    assert r.status_code == 200 and r.json().get("silinen") == 5, f"{t.ad}/{yer}: {r.status_code} {r.text[:200]}"
    assert t.var_olan(o, hedef) == 0
    assert _iz(o, t.iz_toplu) == [(AYSE, "ok", 5)], _iz(o, t.iz_toplu)


@TURLER
@YERLER
def test_KRITIK_SAHIPSIZ_ve_ORTAK_GIRIS_kaydi_TEKIL_iki_uctan_silinir_iz_ONUN(o, monkeypatch, t, yer):
    from servers import auth

    j = _iki_hekim(o)
    if yer == "tunel":
        monkeypatch.setattr(auth, "_require", True)
    k1, k2 = t.tohum(o, "")[0], t.tohum(o, ORTAK)[0]
    kodlar = [r.status_code for r in t.tekiller(o, getattr(o, yer), k1, k2, _b(j[MEHMET], yer))]
    assert kodlar == [200, 200] and t.var_olan(o, [k1, k2]) == 0, f"{t.ad}/{yer}: {kodlar}"
    assert {s[0] for s in _iz(o, t.iz_tekil)} == {MEHMET}, _iz(o, t.iz_tekil)


@TURLER
def test_KARSIT_Y92_KAYITLI_baska_hekimin_kaydi_403_KALIR_karisik_secim_ATOMIK(o, t):
    j = _iki_hekim(o)
    sahipsiz, mehmet = t.tohum(o, ""), t.tohum(o, MEHMET)
    r = t.toplu(o, o.lan, sahipsiz + mehmet, _b(j[AYSE]))
    assert r.status_code == 403 and (t.var_olan(o, sahipsiz), t.var_olan(o, mehmet)) == (1, 1), r.text[:200]
    d = r.json().get("detail", "")
    assert "seçimdeki 1 kayıt başka bir hekime ait" in d and "ya da sahipsiz" not in d, d  # yalnız Mehmet'inki yabancı
    kodlar = [x.status_code for x in t.tekiller(o, o.lan, mehmet[0], mehmet[0], _b(j[AYSE]))]
    assert kodlar == [403, 403] and t.var_olan(o, mehmet) == 1, kodlar


@TURLER
def test_KARSIT_KIMLIKSIZ_sahipsiz_silme_428_beyan_SAYILMAZ(o, t):
    _iki_hekim(o)
    sahipsiz = t.tohum(o, "") + t.tohum(o, ORTAK)
    for istemci in (o.lan, o.yerel):
        r = t.toplu(o, istemci, sahipsiz, {})
        assert r.status_code == 428 and t.var_olan(o, sahipsiz) == 2, r.text[:200]


@TURLER
def test_KARSIT_kimlik_DB_OKUNAMAZKEN_jetonla_yalniz_BOS_sahipli_silinir_bilinemeyen_403(o, monkeypatch, t):
    """Fail-closed: sahibinin kayıtlı olup olmadığı BİLİNEMEYEN (dolu e-postalı) kayıt silinmez; sahibi boş kayıt sahipsizdir."""
    from database.auth_db import get_auth_db

    j = _iki_hekim(o)
    bos, ortak = t.tohum(o, ""), t.tohum(o, ORTAK)
    with monkeypatch.context() as m:
        m.setattr(get_auth_db(), "db_path", o.tmp / "yok_dizin" / "auth_users.db")
        r_bos = t.toplu(o, o.lan, bos, _b(j[AYSE]))
        r_ortak = t.toplu(o, o.lan, ortak, _b(j[AYSE]))
    assert (r_bos.status_code, t.var_olan(o, bos)) == (200, 0), r_bos.text[:200]
    assert (r_ortak.status_code, t.var_olan(o, ortak)) == (403, 1), r_ortak.text[:200]


@TURLER
def test_KARSIT_KURAL2_operatorsuz_klinik_kilitlenmez(o, t):
    kayitlar = t.tohum(o, "") + t.tohum(o, ORTAK) + t.tohum(o, "tek@klinik.com")
    r = t.toplu(o, o.lan, kayitlar, {})
    assert r.status_code == 200 and t.var_olan(o, kayitlar) == 0, r.text[:200]


def test_KARSIT_ACIL_DURDUR_ve_STOP_kimlik_kapisindan_GECMEZ(o):
    _iki_hekim(o)
    assert o.lan.post("/api/session/stop", json={}).status_code == 200
    assert o.lan.post("/api/hardware/emergency_stop").status_code == 200
