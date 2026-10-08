# -*- coding: utf-8 -*-
"""Y107 (S-B.4 · O-B.9) — seans notu (Geçmiş ekranı düzenlemesi `/api/history/update_notes`) kayıtlı operatörlü klinikte KİMLİK
ister (kimliksiz 428); kimlikli HER hekim düzenleyebilir (klinik içi paylaşım); iz kimin yaptığını yazar.

ÖLÇÜLEN DURUM (2-B incelemesi A1): `update_notes` kimlik ve sahiplik denetlemiyordu — jetonsuz LAN isteği bir seansın (tıbbi kayıt)
notunu değiştiriyor, iz sahipsiz (`''`) kalıyordu; kim yazdığı bilinemiyordu.
SAHİP KARARI Y107: kayıtlı operatörlü klinikte kimlik şart (428 "Operatör seçin"; kimlik DB'si okunamıyorsa Y113 iletisi); kimlikli
her hekim (başka hekimin seansı dahil) düzenler; iz düzenleyenin adına; not METNİ ize girmez (D2.43). Operatörsüz klinik (Kural 2)
değişmez.

GERÇEK: uç (TestClient — LAN 192.168.1.94 / yerel), `operator_tokens`, `auth_db`, tedavi DB'si (geçici). Ölçüt seans satırının notu
(ürün okuyucusu) ve iz satırı.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

AYSE = "dr.ayse@klinik.com"
MEHMET = "dr.mehmet@klinik.com"
ESKI_NOT = "eski gozlem"


@pytest.fixture
def o(tmp_path, monkeypatch):
    from database.treatment_history_db import TreatmentHistoryDB
    from servers import api_server as api
    from servers import operator_tokens
    from servers.history_router import get_db

    tdb = TreatmentHistoryDB(tmp_path / "gecmis")
    monkeypatch.setattr(api, "_get_treatment_db", lambda: tdb)
    api.app.dependency_overrides[get_db] = lambda: tdb
    yerel = TestClient(api.app, client=("127.0.0.1", 52934))
    lan = TestClient(api.app, client=("192.168.1.94", 52935))

    def _sil():
        for op in yerel.get("/api/operators").json().get("data", []):
            yerel.post("/api/operators/remove", json={"email": op["email"]})

    operator_tokens.temizle_hepsi()
    _sil()
    try:
        yield type("O", (), {"tdb": tdb, "yerel": yerel, "lan": lan, "tmp": tmp_path})
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


def _seans(o, sahip=AYSE):
    sid = int(o.tdb.start_session(treatment_mode="Manuel", patient_name="Pamuk", operator_email=sahip))
    o.tdb.update_session_notes(sid, ESKI_NOT)
    return sid


def _not(o, sid):
    with o.tdb._get_connection() as c:
        return c.execute("SELECT patient_notes FROM treatment_sessions WHERE id = ?", (sid,)).fetchone()[0]


def _iz(o):
    return [
        (s["operator_email"], s["outcome"], s["scope"], json.loads(s["detail"] or "{}"))
        for s in o.tdb.denetim_oku(50, "history.notes")
    ]


def _yaz(istemci, sid, metin, jeton=""):
    return istemci.post(
        "/api/history/update_notes",
        json={"session_id": sid, "notes": metin},
        headers={"X-PEMF-Operator": jeton} if jeton else {},
    )


@pytest.mark.parametrize("yer", ["lan", "yerel"])
def test_KRITIK_kayitli_klinikte_KIMLIKSIZ_not_duzenleme_428_not_DEGISMEZ(o, yer):
    _iki_hekim(o)
    sid = _seans(o)
    r = _yaz(getattr(o, yer), sid, "kimliksiz yazildi")
    assert (r.status_code, _not(o, sid)) == (428, ESKI_NOT), f"kimliksiz not yazıldı: {r.status_code} {r.text[:150]}"
    assert r.json()["detail"].startswith("Operatör seçin"), r.text[:200]
    assert [(e, s) for e, s, _sc, _d in _iz(o)] == [("", "reddedildi")], _iz(o)


def test_KRITIK_KILITLE_sonrasi_eski_jetonla_not_428(o):
    j = _iki_hekim(o)
    sid = _seans(o)
    assert o.lan.post("/api/operators/lock", headers={"X-PEMF-Operator": j[AYSE]}).status_code == 200
    r = _yaz(o.lan, sid, "kilit sonrasi", j[AYSE])
    assert (r.status_code, _not(o, sid)) == (428, ESKI_NOT), r.text[:200]


def test_KRITIK_kimlik_DB_OKUNAMAZKEN_not_428_ARIZA_iletisi(o, monkeypatch):
    from database.auth_db import get_auth_db

    _iki_hekim(o)
    sid = _seans(o)
    with monkeypatch.context() as m:
        m.setattr(get_auth_db(), "db_path", o.tmp / "yok_dizin" / "auth_users.db")
        r = _yaz(o.lan, sid, "arizada")
    assert (r.status_code, _not(o, sid)) == (428, ESKI_NOT), r.text[:200]
    d = r.json()["detail"]
    assert d.startswith("Cihazın kimlik veritabanı okunamıyor —") and "Operatör seçin" not in d, d


def test_KARSIT_KIMLIKLI_BASKA_hekim_duzenler_iz_DUZENLEYENIN_adina_metin_ize_GIRMEZ(o):
    """Klinik içi paylaşım: Mehmet, Ayşe'nin seansının notunu düzenleyebilir; iz Mehmet'in adına; not METNİ izde yok."""
    j = _iki_hekim(o)
    sid = _seans(o, AYSE)
    r = _yaz(o.lan, sid, "GIZLI-Mehmet-notu", j[MEHMET])
    assert r.status_code == 200 and _not(o, sid) == "GIZLI-Mehmet-notu", r.text[:200]
    iz = _iz(o)
    assert [(e, s, sc) for e, s, sc, _d in iz] == [(MEHMET, "ok", f"id={sid}")], iz
    assert "GIZLI" not in json.dumps([d for *_x, d in iz], ensure_ascii=False)


def test_KARSIT_KURAL2_operatorsuz_klinik_jetonsuz_duzenler(o):
    sid = _seans(o, "")
    r = _yaz(o.lan, sid, "tek hekim notu")
    assert r.status_code == 200 and _not(o, sid) == "tek hekim notu", r.text[:200]


def test_KARSIT_kimliksiz_durumda_ACIL_DURDUR_ve_STOP_kapisiz(o):
    _iki_hekim(o)
    assert _yaz(o.lan, _seans(o), "x").status_code == 428
    assert o.lan.post("/api/session/stop", json={}).status_code == 200
    assert o.lan.post("/api/hardware/emergency_stop").status_code == 200
