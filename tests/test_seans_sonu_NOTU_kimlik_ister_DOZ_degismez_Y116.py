# -*- coding: utf-8 -*-
"""Y116 (S-B2B2.1 · B2B2-2) — seans sonu gözlem notu (`/api/session/notes`, `session_id` ile) kayıtlı operatörlü klinikte KİMLİK
ister; güncelleme İZ yazar; BİTMİŞ seansın doz parametreleri istekle DEĞİŞMEZ.

ÖLÇÜLEN (2-B2 B2B2-2, `kayit/b2b22_sonda.txt`): cihazda Ayşe kayıtlı; Ayşe'nin bitmiş seansı (50 Hz, 2 mT); LAN'dan JETONSUZ
`POST /api/session/notes {"session_id": 1, "notes": "LAN-kimliksiz", "frequency": 999, "intensity": 9}` → 200; satır
`('LAN-kimliksiz', 999.0, 9.0)`; denetim izinde satır YOK.
SAHİP KARARI Y116: kayıtlı operatörlü klinikte `session_id` ile güncelleme kimlik ister (428 "Operatör seçin"; kimlik DB'si
okunamıyorsa Y113 iletisi); iz yazar (kim, hangi seans, hangi alanlar — not METNİ ize girmez, D2.43); BİTMİŞ seansın frekans /
şiddeti DEĞİŞTİRİLMEZ, yalnız not; kimlikli her hekim not ekler (Y107); operatörsüz klinik (Kural 2) değişmez.
GERÇEK: uç (TestClient — LAN 192.168.1.95 / yerel), `operator_tokens`, `auth_db`, tedavi DB'si (geçici). Satır SQL ile, iz
`denetim_oku`.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

AYSE = "dr.ayse@klinik.com"
MEHMET = "dr.mehmet@klinik.com"
NOT = "Uyudu — Y116 gizli gozlem"


@pytest.fixture
def o(tmp_path, monkeypatch):
    from database.treatment_history_db import TreatmentHistoryDB
    from servers import api_server as api
    from servers import operator_tokens

    tdb = TreatmentHistoryDB(tmp_path / "gecmis")
    monkeypatch.setattr(api, "_get_treatment_db", lambda: tdb)
    yerel = TestClient(api.app, client=("127.0.0.1", 52944))
    lan = TestClient(api.app, client=("192.168.1.95", 52945))

    def _sil():
        for op in yerel.get("/api/operators").json().get("data", []):
            yerel.post("/api/operators/remove", json={"email": op["email"]})

    operator_tokens.temizle_hepsi()
    _sil()
    try:
        yield type("O", (), {"tdb": tdb, "yerel": yerel, "lan": lan, "tmp": tmp_path})
    finally:
        operator_tokens.temizle_hepsi()
        _sil()
        tdb.close_connections()


def _hekimler(o):
    j = {}
    for e in (AYSE, MEHMET):
        r = o.yerel.post("/api/operators/enroll", json={"email": e, "display_name": e, "pin": "123456"})
        assert r.status_code == 200, r.text[:200]
        j[e] = o.yerel.post("/api/operators/verify", json={"email": e, "pin": "123456"}).json()["operator_token"]
    return j


def _bitmis_seans(o, sahip=AYSE) -> int:
    import time

    sid = int(o.tdb.start_session(treatment_mode="Manuel", patient_name="Pamuk", operator_email=sahip))
    o.tdb.set_session_meta(sid, started_epoch=time.time() - 300)  # eski istemci dalı son 12 sa'te BAŞLAYANI arar
    o.tdb.end_session(sid, parameters={"frequency_hz": 50.0, "intensity_mt": 2.0}, duration_minutes=4)
    return sid


def _satir(o, sid):
    with o.tdb._get_connection() as c:
        return tuple(
            c.execute(
                "SELECT COALESCE(patient_notes,''), frequency_hz, intensity_mt, duration_minutes, session_status "
                "FROM treatment_sessions WHERE id = ?",
                (sid,),
            ).fetchone()
        )


def _iz(o):
    return [
        (s["operator_email"], s["outcome"], s["scope"], json.loads(s["detail"] or "{}"))
        for s in o.tdb.denetim_oku(50, "session.notes")
    ]


def _not_yaz(istemci, sid, jeton="", **ek):
    govde = {"session_id": sid, "notes": NOT, "patient_name": "Pamuk", "frequency": 999, "intensity": 9, **ek}
    return istemci.post("/api/session/notes", json=govde, headers={"X-PEMF-Operator": jeton} if jeton else {})


@pytest.mark.parametrize("yer", ["lan", "yerel"])
def test_KRITIK_kayitli_klinikte_KIMLIKSIZ_seans_notu_428_satir_DEGISMEZ_iz_REDDEDILDI(o, yer):
    _hekimler(o)
    sid = _bitmis_seans(o)
    once = _satir(o, sid)
    r = _not_yaz(getattr(o, yer), sid)
    assert r.status_code == 428, f"kimliksiz seans notu {r.status_code} {r.text[:200]} (Y116: 428)"
    assert "Operatör seçin" in r.json().get("detail", "")
    assert _satir(o, sid) == once, "kimliksiz istek seans satırını değiştirdi"
    assert [(e, s) for e, s, _sc, _d in _iz(o)] == [("", "reddedildi")], _iz(o)


def test_KRITIK_kimlik_DB_OKUNAMAZKEN_seans_notu_428_ARIZA_iletisi(o, monkeypatch):
    from database.auth_db import get_auth_db

    _hekimler(o)
    sid = _bitmis_seans(o)
    once = _satir(o, sid)
    with monkeypatch.context() as m:
        m.setattr(get_auth_db(), "db_path", o.tmp / "yok_dizin" / "auth_users.db")
        r = _not_yaz(o.lan, sid)
    assert (r.status_code, _satir(o, sid)) == (428, once), r.text[:200]
    d = r.json()["detail"]
    assert d.startswith("Cihazın kimlik veritabanı okunamıyor —") and "Operatör seçin" not in d, d


def test_KRITIK_KILITLE_sonrasi_eski_jetonla_seans_notu_428(o):
    j = _hekimler(o)
    sid = _bitmis_seans(o)
    once = _satir(o, sid)
    assert o.lan.post("/api/operators/lock", headers={"X-PEMF-Operator": j[AYSE]}).status_code == 200
    r = _not_yaz(o.lan, sid, jeton=j[AYSE])
    assert (r.status_code, _satir(o, sid)) == (428, once), r.text[:200]


def test_KRITIK_BITMIS_seansin_DOZU_istekle_DEGISMEZ_yalniz_not_eklenir_iz_ALANLARI_yazar(o):
    j = _hekimler(o)
    sid = _bitmis_seans(o, sahip=AYSE)
    r = _not_yaz(o.lan, sid, jeton=j[MEHMET])  # başka hekim (Y107: kimlikli her hekim not ekler)
    assert r.status_code == 200, r.text[:200]
    assert _satir(o, sid) == (NOT, 50.0, 2.0, 4, "completed"), "bitmiş seansın doz kaydı/süresi istekle değişti"
    iz = _iz(o)
    assert [(e, s, sc) for e, s, sc, _d in iz] == [(MEHMET, "ok", f"id={sid}")], iz
    assert iz[0][3].get("alanlar") == ["notes"] and iz[0][3].get("not_var") is True
    assert NOT not in json.dumps(iz, ensure_ascii=False) and "gizli" not in json.dumps(iz, ensure_ascii=False)


def test_KARSIT_KURAL2_operatorsuz_klinikte_jetonsuz_not_YAZILIR_doz_yine_DEGISMEZ(o):
    sid = _bitmis_seans(o, sahip="")
    r = _not_yaz(o.lan, sid)
    assert r.status_code == 200, r.text[:200]
    assert _satir(o, sid) == (NOT, 50.0, 2.0, 4, "completed")
    assert [(s, sc) for _e, s, sc, _d in _iz(o)] == [("ok", f"id={sid}")]


def test_KARSIT_kimliksiz_durumda_ACIL_DURDUR_ve_STOP_kapisiz(o):
    _hekimler(o)
    assert _not_yaz(o.lan, _bitmis_seans(o)).status_code == 428
    assert o.lan.post("/api/session/stop", json={}).status_code == 200
    assert o.lan.post("/api/hardware/emergency_stop").status_code == 200


# (Eski `test_KARSIT_A01_eski_istemci_SESSION_ID_siz_not_yolu_DEGISMEZ` kaldırıldı: Y120 (S-C.2) sahip kararıyla `session_id`'siz eski
# istemci dalı da kayıtlı klinikte KİMLİK ister — davranış ve karşıtları tests/test_eski_istemci_notu_KAYITLI_klinikte_KIMLIK_ister_Y120.py.)


def test_KRITIK_arayuz_fiksturu_GERCEK_428_yanitiyla_AYNI(o):
    """Arayüz yarısı (`ObservationNotesModal.Y116.operatorSectirir.web.test.tsx`) bu GERÇEK 428 yanıtını okur (jest Python
    koşturamaz). Bayatlarsa KIRMIZI; yenilemek: `Y116_FIKSTUR_YAZ=1`."""
    import os
    from pathlib import Path

    _hekimler(o)
    r = _not_yaz(o.lan, _bitmis_seans(o))
    beklenen = {"durum": r.status_code, "govde": r.json()}
    f = (
        Path(__file__).resolve().parents[1]
        / "apps"
        / "ui"
        / "src"
        / "components"
        / "domain"
        / "__tests__"
        / "__fixtures__"
        / "notKimliksiz.Y116.json"
    )
    if os.environ.get("Y116_FIKSTUR_YAZ") == "1":
        f.write_text(json.dumps(beklenen, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    assert f.exists(), "arayüz fikstürü yok (Y116_FIKSTUR_YAZ=1 ile üret)"
    assert json.loads(f.read_text(encoding="utf-8")) == beklenen, "arayüz fikstürü GERÇEK 428 yanıtından BAYATLADI"
