# -*- coding: utf-8 -*-
"""Y112 (S-B2.4 · S-A1.1, 2-B incelemesi) — AI Geçmişi "Tüm Klinik" silmesi Y92 / A-03 ile hizalanır.

ÖLÇÜLEN KUSUR (2-B incelemesi A1): `/api/ai/log/delete_all` `all_operators` ile JETONLU herhangi bir hekim için — cihazdan,
LAN'dan cihaz token'ıyla, tünelden — BAŞKA hekimlerin AI kayıtlarını da siliyordu (deleted 6). Hasta/seans için Y92 "yalnız kendi"
ve A-03 "kliniğin tamamı yalnız cihazın kendi ekranından" kuralları vardı; AI geçmişi ikisinin de dışındaydı.
SAHİP KARARI Y112: her yerden "Tüm Klinik" = yalnız KENDİ + SAHİPSİZ kayıtlar; başkalarınınki dahil TAMAMI yalnız cihazın
kendi ekranından (loopback) ve kimlikli hekimle. "Sahipsiz" Y104 ile aynı: sahibi boş/NULL ya da cihazda KAYITLI OLMAYAN
e-posta (operatörler kurulmadan önceki ortak giriş). Kimliksiz 428 (A-10). Operatörsüz klinik (Kural 2) kilitlenmez.

GERÇEK: uç (TestClient — cihaz 127.0.0.1 / LAN 192.168.1.92 + geçerli cihaz token'ı / tünel başlıkları + saha kimlik kipi),
`operator_tokens`, `auth_db`, tedavi DB'si (geçici). Ölçüt ham `SELECT COUNT(*)` ve iz satırı.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

AYSE = "dr.ayse@klinik.com"
MEHMET = "dr.mehmet@klinik.com"
ORTAK = "klinik@ortak-giris.com"
TEK = "tek@klinik.com"
TOKEN = {"X-API-Key": "DOGRU-TOKEN"}
TUNEL = {"cf-ray": "8a1b2c3d4e5f-IST", "cf-connecting-ip": "203.0.113.9", **TOKEN}
TUM = {"confirm": "DELETE_ALL", "all_operators": True}


@pytest.fixture
def o(tmp_path, monkeypatch):
    from database.treatment_history_db import TreatmentHistoryDB
    from servers import api_server as api
    from servers import auth, operator_tokens

    tdb = TreatmentHistoryDB(tmp_path / "gecmis")
    monkeypatch.setattr(api, "_get_treatment_db", lambda: tdb)
    monkeypatch.setattr(auth, "check_token", lambda t: t == "DOGRU-TOKEN")
    cihaz = TestClient(api.app, client=("127.0.0.1", 52734))
    lan = TestClient(api.app, client=("192.168.1.92", 52735))
    tunel = TestClient(api.app, client=("127.0.0.1", 52736))

    def _sil():
        for op in cihaz.get("/api/operators").json().get("data", []):
            cihaz.post("/api/operators/remove", json={"email": op["email"]})

    operator_tokens.temizle_hepsi()
    _sil()
    try:
        yield type("O", (), {"tdb": tdb, "cihaz": cihaz, "lan": lan, "tunel": tunel})
    finally:
        operator_tokens.temizle_hepsi()
        _sil()
        tdb.close_connections()


def _iki_hekim(o):
    j = {}
    for e in (AYSE, MEHMET):
        r = o.cihaz.post("/api/operators/enroll", json={"email": e, "display_name": e, "pin": "123456"})
        assert r.status_code == 200, r.text[:200]
        j[e] = o.cihaz.post("/api/operators/verify", json={"email": e, "pin": "123456"}).json()["operator_token"]
    return j


def _tohum(o):
    for sahip, n in ((AYSE, 2), (MEHMET, 2), ("", 1), (None, 1), (ORTAK, 1)):
        for i in range(n):
            # benzersiz hasta/özet (tohum: A 2 · M 2 · boş 1 · NULL 1 · ortak 1 = 7)
            aid = o.tdb.add_ai_analysis(
                module_id="m",
                patient_name=f"P-{sahip}-{i}",
                result_summary=f"x-{sahip}-{i}",
                operator_email=sahip or "",
            )
            if sahip is None:
                with o.tdb._get_connection() as c:
                    c.execute("UPDATE ai_analyses SET operator_email = NULL WHERE id = ?", (aid,))
                    c.commit()


def _dagilim(o):
    with o.tdb._get_connection() as c:
        satir = c.execute("SELECT operator_email FROM ai_analyses").fetchall()
    d = {"A": 0, "M": 0, "S": 0, "O": 0}
    for (e,) in satir:
        e = (e or "").strip().lower()
        d["A" if e == AYSE else "M" if e == MEHMET else "O" if e == ORTAK else "S"] += 1
    return d


def _iz(o):
    return [
        (s["operator_email"], s["outcome"], s["item_count"], s["scope"], json.loads(s["detail"] or "{}").get("kapsam"))
        for s in o.tdb.denetim_oku(50, "ai_log.delete_all")
    ]


@pytest.mark.parametrize("yer", ["lan", "tunel"])
def test_KRITIK_cihaz_DISINDAN_tum_klinik_YALNIZ_kendi_ve_sahipsiz_baska_hekiminki_KALIR(o, monkeypatch, yer):
    from servers import auth

    j = _iki_hekim(o)
    _tohum(o)
    if yer == "tunel":
        monkeypatch.setattr(auth, "_require", True)
    r = getattr(o, yer).post(
        "/api/ai/log/delete_all", json=TUM, headers={"X-PEMF-Operator": j[AYSE], **(TUNEL if yer == "tunel" else TOKEN)}
    )
    assert r.status_code == 200 and r.json()["deleted"] == 5, r.text[:200]
    assert _dagilim(o) == {"A": 0, "M": 2, "S": 0, "O": 0}, f"{yer}: Mehmet'in AI kayıtları cihaz dışından silindi"
    assert _iz(o) == [(AYSE, "ok", 5, "KENDI_VE_SAHIPSIZ", "kendi_ve_sahipsiz")], _iz(o)


def test_KARSIT_CIHAZIN_KENDISINDEN_kimlikli_hekimle_TAMAMI_silinir(o):
    j = _iki_hekim(o)
    _tohum(o)
    r = o.cihaz.post("/api/ai/log/delete_all", json=TUM, headers={"X-PEMF-Operator": j[AYSE]})
    assert r.status_code == 200 and r.json()["deleted"] == 7, r.text[:200]
    assert _dagilim(o) == {"A": 0, "M": 0, "S": 0, "O": 0}
    assert _iz(o) == [(AYSE, "ok", 7, "TUM_KLINIK", "tum_klinik")], _iz(o)


@pytest.mark.parametrize("yer", ["cihaz", "lan"])
def test_KARSIT_KIMLIKSIZ_tum_klinik_428_hicbir_sey_silinmez(o, yer):
    _iki_hekim(o)
    _tohum(o)
    r = getattr(o, yer).post("/api/ai/log/delete_all", json=TUM, headers=TOKEN if yer == "lan" else {})
    assert r.status_code == 428 and sum(_dagilim(o).values()) == 7, r.text[:200]


def test_KARSIT_A10_KENDI_kapsami_degismez_sahipsize_dokunmaz(o):
    j = _iki_hekim(o)
    _tohum(o)
    r = o.lan.post(
        "/api/ai/log/delete_all", json={"confirm": "DELETE_ALL"}, headers={"X-PEMF-Operator": j[AYSE], **TOKEN}
    )
    assert r.status_code == 200 and _dagilim(o) == {"A": 0, "M": 2, "S": 2, "O": 1}, (r.text[:200], _dagilim(o))


def test_KARSIT_KURAL2_operatorsuz_klinik_LAN_dan_tum_klinik_kilitlenmez(o):
    for sahip in (TEK, "", ORTAK):
        o.tdb.add_ai_analysis(
            module_id="m", patient_name=f"P-{sahip}", result_summary=f"x-{sahip}", operator_email=sahip
        )
    r = o.lan.post("/api/ai/log/delete_all", json=TUM, headers=TOKEN)
    assert r.status_code == 200 and r.json()["deleted"] == 3, r.text[:200]


def test_KARSIT_ACIL_DURDUR_ve_STOP_kimlik_kapisindan_GECMEZ(o):
    _iki_hekim(o)
    assert o.lan.post("/api/session/stop", json={}).status_code == 200
    assert o.lan.post("/api/hardware/emergency_stop").status_code == 200


def test_KARSIT_kimlik_DB_OKUNAMAZKEN_cihaz_disindan_tum_klinik_yalniz_KENDI_ve_BOS_sahipli(o, monkeypatch, tmp_path):
    """Fail-closed: kimin kayıtlı olduğu bilinmiyorken dolu e-postalı başkasının (ve ortak girişin) kaydı silinmez."""
    from database.auth_db import get_auth_db

    j = _iki_hekim(o)
    _tohum(o)
    with monkeypatch.context() as m:
        m.setattr(get_auth_db(), "db_path", tmp_path / "yok_dizin" / "auth_users.db")
        r = o.lan.post("/api/ai/log/delete_all", json=TUM, headers={"X-PEMF-Operator": j[AYSE], **TOKEN})
    assert r.status_code == 200 and r.json()["deleted"] == 4, r.text[:200]
    assert _dagilim(o) == {"A": 0, "M": 2, "S": 0, "O": 1}, _dagilim(o)
