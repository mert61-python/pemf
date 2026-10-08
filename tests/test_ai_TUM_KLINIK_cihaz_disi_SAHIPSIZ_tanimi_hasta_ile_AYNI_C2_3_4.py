# -*- coding: utf-8 -*-
"""C2-3.4 (2-C incelemesi A3 · 2-B2 Y112 / Y104) — AI "Tüm Klinik" cihaz dışı silmesinin "sahipsiz" tanımı, hasta/seans silme
kapısıyla (ve arayüzle) AYNI normalleştirmeyi kullanır: kayıtlı bir hekimin kaydı, sahip dizesindeki boşluk-dışı beyaz karakter ya da
ASCII dışı büyük harf yüzünden "sahipsiz" sayılıp BAŞKA hekimce cihaz dışından SİLİNMEZ.

ÖLÇÜLEN KUSUR: Y104 tanımı iki yerde iki ayrı biçimde uygulanmış — hasta/seans: Python `(sahip or "").strip().lower()`
(`silme_yetkisi._yabanci`); arayüz: JS `.trim().toLowerCase()` (`patientScope.silinebilir`); AI: SQL `LOWER(TRIM(operator_email)) NOT IN
(…)` (`thdb_ai_gecmisi.clear_ai_analyses`). SQLite `LOWER` yalnız ASCII küçültür, `TRIM` yalnız ' ' kırpar. Ölçüldü (sonda): kayıtlı
Mehmet'in `\\t` / `\\n` / NBSP ile, Öz'ün `DR.ÖZ@…` ile yazılmış kaydı: hasta tarafında 403 (başka hekimin) — AI tarafında Ayşe'nin LAN
"Tüm Klinik" isteğiyle SİLİNDİ. Ham sahip dizesi AI tablosunda ham saklanır (`add_ai_analysis`: "filtre için ham saklanır"); bugünkü
yazıcılar normalleştirir (`cozumlenmis_operator`), varyant yalnız eski (2026-08-09 öncesi) / içe aktarılmış kayıtta olur.
KARŞIT: görsel-eş (ZWSP) dize Y104/Y109 gereği sahipsiz KALIR (iki tarafta da) · boş/NULL/kayıtsız silinir · kendi silinir · Mehmet'in
tam/ASCII-büyük/boşluklu kaydı KALIR · Y105 operatörsüz "kendi" dalı değişmez.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

AYSE = "dr.ayse@klinik.com"
MEHMET = "dr.mehmet@klinik.com"
OZ = "Dr.Öz@Klinik.com"  # kayıt normalleştirir → "dr.öz@klinik.com"
ORTAK = "klinik@ortak-giris.com"
TOKEN = {"X-API-Key": "DOGRU-TOKEN"}
TUM = {"confirm": "DELETE_ALL", "all_operators": True}
BASKA_HEKIM_VARYANTI = [
    ("sekme", "dr.mehmet@klinik.com\t"),
    ("satir_sonu", "dr.mehmet@klinik.com\n"),
    ("NBSP", " dr.mehmet@klinik.com"),
    ("Turkce_buyuk", "DR.ÖZ@KLINIK.COM"),
]


@pytest.fixture
def o(tmp_path, monkeypatch):
    from database.patient_database import PatientDatabase
    from database.treatment_history_db import TreatmentHistoryDB
    from servers import api_server as api
    from servers import auth, operator_tokens, patient_router

    hdb = PatientDatabase(str(tmp_path / "patients.db"))
    tdb = TreatmentHistoryDB(tmp_path / "gecmis")
    monkeypatch.setattr(patient_router, "get_patient_database", lambda: hdb)
    monkeypatch.setattr(api, "_get_treatment_db", lambda: tdb)
    monkeypatch.setattr(auth, "check_token", lambda t: t == "DOGRU-TOKEN")
    yerel = TestClient(api.app, client=("127.0.0.1", 52974))
    lan = TestClient(api.app, client=("192.168.1.97", 52975))

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


def _hekimler(o):
    j = {}
    for e in (AYSE, MEHMET, OZ):
        r = o.yerel.post("/api/operators/enroll", json={"email": e, "display_name": e, "pin": "123456"})
        assert r.status_code == 200, r.text[:200]
        j[e] = o.yerel.post("/api/operators/verify", json={"email": e, "pin": "123456"}).json()["operator_token"]
    return j


def _ai(o, sahip):
    aid = o.tdb.add_ai_analysis(
        module_id="m", patient_name="P", result_summary=f"x-{sahip!r}", operator_email=sahip or ""
    )
    if sahip is None:
        with o.tdb._get_connection() as c:
            c.execute("UPDATE ai_analyses SET operator_email = NULL WHERE id = ?", (aid,))
            c.commit()
    return aid


def _var(o, aid) -> bool:
    with o.tdb._get_connection() as c:
        return c.execute("SELECT COUNT(*) FROM ai_analyses WHERE id=?", (aid,)).fetchone()[0] == 1


@pytest.mark.parametrize("ad,sahip", BASKA_HEKIM_VARYANTI, ids=[a for a, _ in BASKA_HEKIM_VARYANTI])
def test_KRITIK_kayitli_hekimin_VARYANT_sahipli_AI_kaydi_cihaz_disi_tum_klinikte_KALIR_hasta_tarafiyla_AYNI(
    o, ad, sahip
):
    j = _hekimler(o)
    aid = _ai(o, sahip)
    with o.tdb._get_connection() as c:
        assert (
            c.execute("SELECT operator_email FROM ai_analyses WHERE id=?", (aid,)).fetchone()[0] == sahip
        )  # ham saklandı
    # referans: AYNI sahip dizesi hasta tarafında "başka hekimin" (403) — Y104 kapısı
    pid = str(o.hdb.add_patient({"name": f"H-{ad}", "species": "Kedi", "operator_email": sahip}))
    rh = o.lan.post(
        "/api/patients/delete_bulk",
        json={"patient_ids": [pid], "confirm": "DELETE_SELECTED"},
        headers={"X-PEMF-Operator": j[AYSE]},
    )
    assert rh.status_code == 403, (
        f"referans değişti: hasta tarafı {ad!r} varyantını başka hekimin saymıyor ({rh.status_code})"
    )
    r = o.lan.post("/api/ai/log/delete_all", json=TUM, headers={"X-PEMF-Operator": j[AYSE], **TOKEN})
    assert r.status_code == 200 and r.json().get("kapsam") == "kendi_ve_sahipsiz", r.text[:200]
    assert _var(o, aid), (
        f"{ad}: kayıtlı hekimin ({sahip!r}) AI kaydı başka hekimin cihaz DIŞI 'Tüm Klinik' isteğiyle SİLİNDİ — hasta tarafı aynı "
        "sahibi 'başka hekimin' sayıyor (403); Y112: başka hekimin kayıtları cihaz dışından KALIR"
    )


def test_KARSIT_sahipsizler_kendi_ve_gorsel_es_SILINIR_baska_hekiminkiler_KALIR(o):
    j = _hekimler(o)
    silinmeli = {
        k: _ai(o, s)
        for k, s in (
            ("kendi", AYSE),
            ("bos", ""),
            ("NULL", None),
            ("ortak", ORTAK),
            ("ZWSP_gorsel_es", "dr.mehmet@klinik.com​"),
        )
    }
    kalmali = {
        k: _ai(o, s)
        for k, s in (
            ("mehmet", MEHMET),
            ("ASCII_buyuk", "DR.MEHMET@KLINIK.COM"),
            ("bosluk", "  dr.mehmet@klinik.com  "),
            ("oz", "dr.öz@klinik.com"),
        )
    }
    r = o.lan.post("/api/ai/log/delete_all", json=TUM, headers={"X-PEMF-Operator": j[AYSE], **TOKEN})
    assert r.status_code == 200 and r.json()["deleted"] == len(silinmeli), r.text[:200]
    assert [k for k, a in silinmeli.items() if _var(o, a)] == [], "sahipsiz / kendi kalmamalı"
    assert [k for k, a in kalmali.items() if not _var(o, a)] == [], "başka hekimin kaydı silindi"


def test_KARSIT_Y105_operatorsuz_kendi_silme_baska_epostaya_DOKUNMAZ(o):
    kendi, bos, baska = _ai(o, "tek@klinik.com"), _ai(o, ""), _ai(o, "eski.hesap@klinik.com\t")
    r = o.lan.post(
        "/api/ai/log/delete_all", json={"confirm": "DELETE_ALL", "operator_email": "tek@klinik.com"}, headers=TOKEN
    )
    assert r.status_code == 200 and r.json().get("kapsam") == "kendi_ve_sahipsiz", r.text[:200]
    assert (_var(o, kendi), _var(o, bos), _var(o, baska)) == (False, False, True)
