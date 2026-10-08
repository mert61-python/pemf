# -*- coding: utf-8 -*-
"""C2-3.3 (2-C incelemesi A3 · 2-B2 B5(iii)) — geri dönüşsüz silmenin (Y106 · Y104 · Y112) ve seans notunun (Y107) BAŞARI İZİ,
işlemi yetkilendiren hekimin adına yazılır; işlem SÜRERKEN gelen "Kilitle" izi SAHİPSİZ yapmaz.

ÖLÇÜLEN KUSUR: uçlar kimliği kapıda jetondan çözer (`sahiplik_kapisi` / `cozumlenmis_operator(request)`), DB işlemini yapar
(`clear_all_patients` VACUUM'u, toplu silme, `clear_ai_analyses` VACUUM'u …), sonra başarı izini `audit_log.kimlikli_yaz(request, …)` ile
yazar — o, kimliği İSTEKTEN YENİDEN çözer. İşlem sürerken aynı hekimin jetonu iptal edilirse (`POST /api/operators/lock`, D2.E14
"Kilitle", başka sekme / hareketsizlik kilidi) kayıtlar Ayşe'nin yetkisiyle SİLİNMİŞ olur ama iz `operator_email = ''` der; silinen
kayıt artık yok — iz silmenin TEK kanıtıdır. Sahip kararları Y104 / Y106 / Y107 / Y112: "iz o hekimin adına". Ölçüldü (sonda): altı
uçta da yarışsız iz Ayşe, yarışta iz ''. Aynı sınıfın değerlendirme yarısı B2-2.4'te kapatılmıştı (kayıtla aynı kimlik).

Yarış belirlenimci: DB işlemi sırasında jetonu iptal eden kanca (B2-2.4 deseni; iptal ürünün `operator_tokens.iptal`'i — `/lock`un yaptığı).
KARŞIT: istekten ÖNCE iptal edilmiş jeton 428 alır, hiçbir şey silinmez (önbellek iptali diriltmez) · Kural 2 (operatörsüz) iz değişmez.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

AYSE = "dr.ayse@klinik.com"
MEHMET = "dr.mehmet@klinik.com"
TOKEN = {"X-API-Key": "DOGRU-TOKEN"}


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
    yerel = TestClient(api.app, client=("127.0.0.1", 52954))
    lan = TestClient(api.app, client=("192.168.1.94", 52955))

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
    j = {}
    for e in (AYSE, MEHMET):
        r = o.yerel.post("/api/operators/enroll", json={"email": e, "display_name": e, "pin": "123456"})
        assert r.status_code == 200, r.text[:200]
        j[e] = o.yerel.post("/api/operators/verify", json={"email": e, "pin": "123456"}).json()["operator_token"]
    return j


def _iz(o, olay):
    return [(s["operator_email"], s["outcome"], s["item_count"]) for s in o.tdb.denetim_oku(50, olay)]


def _y106(o, j):
    o.hdb.add_patient({"name": "P1", "species": "Kedi", "operator_email": AYSE})
    return (
        o.hdb,
        "clear_all_patients",
        "patient.delete_all",
        "hasta",
        lambda: o.yerel.post(
            "/api/patients/delete_all", json={"confirm": "DELETE_ALL"}, headers={"X-PEMF-Operator": j}
        ),
    )


def _y104_hasta_toplu(o, j):
    k = [
        str(o.hdb.add_patient({"name": f"Q{i}", "species": "Kedi", "operator_email": s}))
        for i, s in enumerate(("", AYSE))
    ]
    return (
        o.hdb,
        "delete_patients_bulk",
        "patient.delete_bulk",
        "hasta",
        lambda: o.lan.post(
            "/api/patients/delete_bulk",
            json={"patient_ids": k, "confirm": "DELETE_SELECTED"},
            headers={"X-PEMF-Operator": j},
        ),
    )


def _y104_hasta_tekil(o, j):
    k = str(o.hdb.add_patient({"name": "R", "species": "Kedi", "operator_email": ""}))
    return (
        o.hdb,
        "delete_patient",
        "patient.delete",
        "hasta",
        lambda: o.lan.delete(f"/api/patients/{k}", headers={"X-PEMF-Operator": j}),
    )


def _y104_seans_toplu(o, j):
    s = [int(o.tdb.start_session(treatment_mode="Manuel", patient_name=f"S{i}", operator_email=AYSE)) for i in range(2)]
    for sid in s:
        o.tdb.end_session(sid)
    return (
        o.tdb,
        "delete_sessions_bulk",
        "history.delete_bulk",
        "seans",
        lambda: o.lan.post(
            "/api/history/delete_bulk",
            json={"session_ids": s, "confirm": "DELETE_SELECTED"},
            headers={"X-PEMF-Operator": j},
        ),
    )


def _y107_not(o, j):
    sid = int(o.tdb.start_session(treatment_mode="Manuel", patient_name="N", operator_email=MEHMET))
    o.tdb.end_session(sid)
    return (
        o.tdb,
        "update_session_notes",
        "history.notes",
        "not",
        lambda: o.lan.post(
            "/api/history/update_notes", json={"session_id": sid, "notes": "n"}, headers={"X-PEMF-Operator": j}
        ),
    )


def _y112_ai(o, j):
    for sahip in (AYSE, "", MEHMET):
        o.tdb.add_ai_analysis(module_id="m", patient_name="P", result_summary=f"x{sahip}", operator_email=sahip)
    return (
        o.tdb,
        "clear_ai_analyses",
        "ai_log.delete_all",
        "ai",
        lambda: o.lan.post(
            "/api/ai/log/delete_all",
            json={"confirm": "DELETE_ALL", "all_operators": True},
            headers={"X-PEMF-Operator": j, **TOKEN},
        ),
    )


YOLLAR = pytest.mark.parametrize(
    "kur",
    [_y106, _y104_hasta_toplu, _y104_hasta_tekil, _y104_seans_toplu, _y107_not, _y112_ai],
    ids=[
        "Y106_tumunu_sil",
        "Y104_hasta_toplu",
        "Y104_hasta_tekil",
        "Y104_seans_toplu",
        "Y107_seans_notu",
        "Y112_ai_tum_klinik",
    ],
)


@YOLLAR
def test_KRITIK_islem_SURERKEN_Kilitle_basari_izi_YETKILENDIREN_hekimin_adina(o, monkeypatch, kur):
    from servers import operator_tokens

    j = _iki_hekim(o)
    nesne, yontem, olay, _tur, istek = kur(o, j[AYSE])
    gercek = getattr(nesne, yontem)

    def _yarisli(*a, **k):
        operator_tokens.iptal(j[AYSE])  # işlem sürerken "Kilitle" (POST /api/operators/lock'un yaptığı)
        return gercek(*a, **k)

    monkeypatch.setattr(nesne, yontem, _yarisli)
    r = istek()
    assert r.status_code == 200, r.text[:200]
    iz = _iz(o, olay)
    assert iz and iz[0][0] == AYSE and iz[0][1] == "ok", (
        f"{olay}: Ayşe'nin yetkisiyle yapılan işlemin izi kilit yarışında başkasına / sahipsize yazıldı: {iz[:2]}"
    )


@YOLLAR
def test_KARSIT_istekten_ONCE_iptal_edilmis_jeton_428_hicbir_sey_degismez(o, kur):
    from servers import operator_tokens

    j = _iki_hekim(o)
    _nesne, _yontem, olay, _tur, istek = kur(o, j[AYSE])
    operator_tokens.iptal(j[AYSE])
    r = istek()
    assert r.status_code == 428, r.text[:200]
    assert all(s[1] != "ok" for s in _iz(o, olay)), _iz(o, olay)


def test_KARSIT_KURAL2_operatorsuz_klinikte_iz_DEGISMEZ(o):
    o.hdb.add_patient({"name": "P1", "species": "Kedi", "operator_email": ""})
    r = o.yerel.post("/api/patients/delete_all", json={"confirm": "DELETE_ALL"})
    assert r.status_code == 200, r.text[:200]
    assert _iz(o, "patient.delete_all")[:1] == [("", "ok", 1)]
