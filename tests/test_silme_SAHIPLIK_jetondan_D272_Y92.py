# -*- coding: utf-8 -*-
"""D2.72 · B-6.26 (+ aday İG-6.4) · Y92 — hasta ve seans SİLME uçları sahipliği JETONDAN denetler.

ÖLÇÜLEN KUSUR (DENETIM-06 B-6.26; ADAY-DOGRULAMA-D2 İG-6.4): `/api/patients/delete_bulk`, `DELETE /api/patients/{id}`,
`POST /api/patients/{id}/delete`, `/api/history/delete_bulk`, `POST /api/history/delete`, `DELETE /api/history/{id}` yalnız
onay dizesine bakıyordu → kimliksiz ev sahibi ya da başka bir hekim (jetonlu da olsa) bir hekimin hasta ve SEANS (tıbbi kayıt)
kayıtlarını geri dönüşsüz silebiliyordu (İG-6.4: 200 `7/7`, başka hekim satırı 4 silindi).

Kural (Y92): cihazda kayıtlı operatör VARKEN silme isteğinin kimliği YALNIZ jetondan; kimliksiz → 428 "Operatör seçin";
hedeflerden biri bile kimliğe ait değilse (başka hekim ya da SAHİPSİZ) → 403 ve HİÇBİR kayıt silinmez (atomik — "kısmen oldu"
yok); red izde `reddedildi`. Karşıt kollar: kendi kayıtları silinir; Kural 2 — kayıtlı operatörü OLMAYAN tek hekimli klinik
bugünkü gibi siler (kilitlenmez); A-01 — LAN'dan jetonlu istek kabul. Kliniğin TAMAMINI silme (`delete_all`) A-03 · D2.11.

GERÇEK: uçlar (TestClient — LAN 192.168.1.70 / yerel), `operator_tokens`, `auth_db` operatörleri, hasta ve tedavi DB'leri
(geçici dizinde). Ölçüt satır VARLIĞI (ham `SELECT COUNT(*)`), yanıt kodu değil yalnız.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

AYSE = "dr.ayse@klinik.com"
MEHMET = "dr.mehmet@klinik.com"
TEK = "tek@klinik.com"


@pytest.fixture
def o(tmp_path, monkeypatch):
    from database.patient_database import PatientDatabase
    from database.treatment_history_db import TreatmentHistoryDB
    from servers import api_server as api
    from servers import operator_tokens, patient_router
    from servers.history_router import get_db

    hdb = PatientDatabase(str(tmp_path / "patients.db"))
    tdb = TreatmentHistoryDB(tmp_path / "gecmis")
    monkeypatch.setattr(patient_router, "get_patient_database", lambda: hdb)
    monkeypatch.setattr(api, "_get_treatment_db", lambda: tdb)  # denetim izi aynı geçici DB'ye
    api.app.dependency_overrides[get_db] = lambda: tdb
    yerel = TestClient(api.app, client=("127.0.0.1", 51434))
    lan = TestClient(api.app, client=("192.168.1.70", 51435))

    def _sil():
        for op in yerel.get("/api/operators").json().get("data", []):
            yerel.post("/api/operators/remove", json={"email": op["email"]})

    operator_tokens.temizle_hepsi()
    _sil()
    try:
        yield type("O", (), {"hdb": hdb, "tdb": tdb, "yerel": yerel, "lan": lan})
    finally:
        api.app.dependency_overrides.pop(get_db, None)
        operator_tokens.temizle_hepsi()
        _sil()
        tdb.close_connections()


def _iki_hekim(o):
    jetonlar = {}
    for e in (AYSE, MEHMET):
        r = o.yerel.post("/api/operators/enroll", json={"email": e, "display_name": e, "pin": "123456"})
        assert r.status_code == 200, r.text[:200]
        jetonlar[e] = o.yerel.post("/api/operators/verify", json={"email": e, "pin": "123456"}).json()["operator_token"]
    return jetonlar


def _b(jeton):
    return {"X-PEMF-Operator": jeton} if jeton else {}


# ─────────────── iki kayıt türü için aynı sözleşme: tohum · ham sayım · toplu uç · iki tekil uç ───────────────


class _Hasta:
    ad = "hasta"
    iz_toplu = "patient.delete_bulk"

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
    def toplu(o, istemci, kimlikler, jeton=""):
        return istemci.post(
            "/api/patients/delete_bulk",
            json={"patient_ids": kimlikler, "confirm": "DELETE_SELECTED"},
            headers=_b(jeton),
        )

    @staticmethod
    def tekiller(o, istemci, kimlik, jeton=""):
        return [
            istemci.delete(f"/api/patients/{kimlik}", headers=_b(jeton)),
            istemci.post(f"/api/patients/{kimlik}/delete", json={}, headers=_b(jeton)),
        ]


class _Seans:
    ad = "seans"
    iz_toplu = "history.delete_bulk"

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
    def toplu(o, istemci, kimlikler, jeton=""):
        return istemci.post(
            "/api/history/delete_bulk", json={"session_ids": kimlikler, "confirm": "DELETE_SELECTED"}, headers=_b(jeton)
        )

    @staticmethod
    def tekiller(o, istemci, kimlik, jeton=""):
        return [
            istemci.delete(f"/api/history/{kimlik}", headers=_b(jeton)),
            istemci.post("/api/history/delete", json={"session_id": kimlik}, headers=_b(jeton)),
        ]


TURLER = pytest.mark.parametrize("t", [_Hasta, _Seans], ids=["hasta", "seans"])


@TURLER
def test_KRITIK_toplu_BASKA_hekimin_kayitlari_403_ve_HICBIRI_silinmez(o, t):
    """MUTASYON: toplu uçtaki sahiplik denetimini kaldırmak → KIRMIZI."""
    j = _iki_hekim(o)
    mehmet = t.tohum(o, MEHMET, 2)
    r = t.toplu(o, o.lan, mehmet, j[AYSE])
    assert r.status_code == 403, f"{t.ad}: başka hekimin kayıtları silinebildi: {r.status_code} {r.text[:200]}"
    assert t.var_olan(o, mehmet) == 2, f"{t.ad}: başka hekimin kaydı silindi"


@TURLER
def test_KRITIK_karisik_secim_ATOMIK_reddedilir_kendi_kaydi_da_silinmez(o, t):
    j = _iki_hekim(o)
    ayse, mehmet = t.tohum(o, AYSE), t.tohum(o, MEHMET)
    r = t.toplu(o, o.lan, ayse + mehmet, j[AYSE])
    assert r.status_code == 403, r.text[:200]
    assert (t.var_olan(o, ayse), t.var_olan(o, mehmet)) == (1, 1), f"{t.ad}: karışık seçim KISMEN silindi"


@TURLER
def test_KRITIK_SAHIPSIZ_kayit_da_kimligin_DEGIL_403(o, t):
    """Y92 'yalnız KENDİ kayıtları': sahipsiz kayıt kimseye ait değildir."""
    j = _iki_hekim(o)
    sahipsiz = t.tohum(o, "")
    r = t.toplu(o, o.lan, sahipsiz, j[AYSE])
    assert r.status_code == 403 and t.var_olan(o, sahipsiz) == 1, (r.status_code, t.var_olan(o, sahipsiz))


@TURLER
def test_KRITIK_kayitli_operatorlu_cihazda_KIMLIKSIZ_silme_428(o, t):
    _iki_hekim(o)
    mehmet = t.tohum(o, MEHMET)
    for istemci in (o.lan, o.yerel):
        r = t.toplu(o, istemci, mehmet)
        assert r.status_code == 428 and "Operatör seçin" in r.json().get("detail", ""), r.text[:200]
    assert t.var_olan(o, mehmet) == 1


@TURLER
def test_KRITIK_TEKIL_uclar_baska_hekim_403_kimliksiz_428(o, t):
    """MUTASYON: tekil uçlardaki sahiplik denetimini kaldırmak → KIRMIZI."""
    j = _iki_hekim(o)
    mehmet = t.tohum(o, MEHMET)[0]
    kodlar = [r.status_code for r in t.tekiller(o, o.lan, mehmet, j[AYSE])]
    kodlar += [r.status_code for r in t.tekiller(o, o.lan, mehmet)]
    assert kodlar == [403, 403, 428, 428], f"{t.ad}: tekil uçlar {kodlar}"
    assert t.var_olan(o, [mehmet]) == 1, f"{t.ad}: tekil uçtan başka hekimin kaydı silindi"


@TURLER
def test_KRITIK_KILITLE_sonrasi_eski_jetonla_silme_428(o, t):
    """İG-6.4 (b) arka uç yarısı: 'Kilitle' (D2.E14) jetonu sunucuda iptal eder → aynı jetonla silme kimliksizdir."""
    j = _iki_hekim(o)
    ayse = t.tohum(o, AYSE)
    o.lan.post("/api/operators/lock", json={}, headers=_b(j[AYSE]))
    r = t.toplu(o, o.lan, ayse, j[AYSE])
    assert r.status_code == 428 and t.var_olan(o, ayse) == 1, (r.status_code, r.text[:200])


@TURLER
def test_KRITIK_red_IZDE_reddedildi_olarak_kalir(o, t):
    j = _iki_hekim(o)
    mehmet = t.tohum(o, MEHMET)
    t.toplu(o, o.lan, mehmet, j[AYSE])
    iz = [s for s in o.tdb.denetim_oku(200, t.iz_toplu)]
    assert [(s["operator_email"], s["outcome"], s["item_count"]) for s in iz] == [(AYSE, "reddedildi", 0)], iz
    assert json.loads(iz[0]["detail"] or "{}").get("yabanci") == 1, iz


@TURLER
def test_KARSIT_kendi_kayitlari_toplu_ve_tekil_SILINIR(o, t):
    j = _iki_hekim(o)
    ayse, mehmet = t.tohum(o, AYSE, 3), t.tohum(o, MEHMET)
    r = t.toplu(o, o.lan, ayse[:2], j[AYSE])
    assert r.status_code == 200 and r.json().get("silinen") == 2, r.text[:200]
    assert all(x.status_code == 200 for x in t.tekiller(o, o.lan, ayse[2], j[AYSE])), f"{t.ad}: kendi tekil silme"
    assert (t.var_olan(o, ayse), t.var_olan(o, mehmet)) == (0, 1)


@TURLER
def test_KARSIT_KURAL2_operatorsuz_klinik_jetonsuz_SILER(o, t):
    """Kural 2: kayıtlı operatörü olmayan tek hekimli klinik kilitlenmez (sahipsiz ve beyanlı kayıtlar dahil)."""
    kayitlar = t.tohum(o, TEK, 2) + t.tohum(o, "") + t.tohum(o, "eski@klinik.com")
    r = t.toplu(o, o.lan, kayitlar[:3], "")
    assert r.status_code == 200 and r.json().get("silinen") == 3, f"Kural 2 kilitlendi: {r.status_code} {r.text[:200]}"
    assert all(x.status_code == 200 for x in t.tekiller(o, o.lan, kayitlar[3], "")), "Kural 2: tekil silme kilitlendi"
    assert t.var_olan(o, kayitlar) == 0
