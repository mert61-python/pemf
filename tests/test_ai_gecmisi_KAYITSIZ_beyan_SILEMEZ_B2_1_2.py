# -*- coding: utf-8 -*-
"""B2-1.2 (2-B incelemesi · A1) — kayıtlı operatörlü cihazda AI geçmişi silme kapsamı KAYITSIZ bir beyandan ALINMAZ (A-10).

ÖLÇÜLEN KUSUR: D2.20 kimliği `cozumlenmis_operator(request, beyan)` ile alıyor; bu işlevin 2. kuralı yalnız BEYAN EDİLEN
e-postanın kayıtlı olup olmadığına bakar → kayıtlı operatörlü cihazda jetonsuz istek, gövdesine KAYITSIZ bir e-posta
(operatörler kurulmadan önceki paylaşılan giriş e-postası, cihazdan ÇIKARILMIŞ bir hekim, uydurma adres) yazarak o e-postanın
AI geçmişini VACUUM'lu siliyordu (ölçüldü: 200 `deleted: 3`; eski APK cihaz jetonuyla LAN'dan da 200) ve iz silmeyi kanıtsız
beyanın ADINA `ok` yazıyordu. Aynı cihazda D2.72 hasta silmesi aynı istekte 428 der. 2-B raporu (D2.20) "kayıtlı operatörlü
cihazda jetonsuz → ''" diyordu. A-10: "kapsam OTURUM KİMLİĞİNE göre; beyan edilen e-posta dikkate alınmaz".
Kural: kayıtlı operatör VARSA kimlik yalnız jetondan (kimliksiz → 428, hiçbir şey silinmez, iz sahipsiz + `kanitsiz_beyan`);
operatörsüz klinikte (Kural 2) beyan kapsamdır — değişmez.
Önerilen yer: tests/test_ai_gecmisi_KAYITSIZ_beyan_SILEMEZ_B2_1_2.py
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

AYSE = "dr.ayse@klinik.com"
MEHMET = "dr.mehmet@klinik.com"
PAYLASILAN = "klinik.giris@klinik.com"
AYRILAN = "dr.ayrilan@klinik.com"
TEK = "tek@klinik.com"


@pytest.fixture
def o(tmp_path, monkeypatch):
    from database.treatment_history_db import TreatmentHistoryDB
    from servers import api_server as api
    from servers import operator_tokens

    tdb = TreatmentHistoryDB(tmp_path / "gecmis")
    monkeypatch.setattr(api, "_get_treatment_db", lambda: tdb)
    yerel = TestClient(api.app, client=("127.0.0.1", 51434))  # silme uçları ayrıcalıklı: cihazın kendisi
    lan = TestClient(api.app, client=("192.168.1.70", 51435))

    def _sil():
        for op in yerel.get("/api/operators").json().get("data", []):
            yerel.post("/api/operators/remove", json={"email": op["email"]})

    operator_tokens.temizle_hepsi()
    _sil()
    try:
        yield type("O", (), {"tdb": tdb, "yerel": yerel, "lan": lan})
    finally:
        operator_tokens.temizle_hepsi()
        _sil()
        tdb.close_connections()


def _hekimler(o, *epostalar):
    j = {}
    for e in epostalar:
        r = o.yerel.post("/api/operators/enroll", json={"email": e, "display_name": e, "pin": "123456"})
        assert r.status_code == 200, r.text[:200]
        j[e] = o.yerel.post("/api/operators/verify", json={"email": e, "pin": "123456"}).json()["operator_token"]
    return j


def _tohum(o, dagilim):
    return {
        e: [
            o.tdb.add_ai_analysis(module_id="m", patient_name=f"AI-{i}", result_summary="s", operator_email=e)
            for i in range(n)
        ]
        for e, n in dagilim
    }


def _say(o):
    with o.tdb._get_connection() as c:
        return dict(c.execute("SELECT COALESCE(operator_email,''), COUNT(*) FROM ai_analyses GROUP BY 1").fetchall())


def _iz(o):
    return [
        (
            s["event_type"],
            s["operator_email"],
            s["outcome"],
            s["item_count"],
            json.loads(s["detail"] or "{}").get("kanitsiz_beyan"),
        )
        for s in o.tdb.denetim_oku(50)
        if s["event_type"].startswith("ai_log")
    ]


def test_KRITIK_paylasilan_giris_epostasi_beyani_jetonsuz_toplu_silme_428(o):
    _hekimler(o, AYSE, MEHMET)
    _tohum(o, ((PAYLASILAN, 3), (AYSE, 2)))
    r = o.yerel.post("/api/ai/log/delete_all", json={"confirm": "DELETE_ALL", "operator_email": PAYLASILAN})
    assert _say(o).get(PAYLASILAN) == 3, f"jetonsuz kayıtsız beyan AI geçmişini sildi: {r.status_code} {r.text[:150]}"
    assert r.status_code == 428 and "Operatör seçin" in r.json().get("detail", ""), r.text[:200]
    assert _iz(o) == [("ai_log.delete_all", "", "reddedildi", 0, PAYLASILAN)], _iz(o)


def test_KRITIK_cihazdan_CIKARILMIS_hekimin_kaydi_jetonsuz_beyanla_TEKIL_silinmez(o):
    _hekimler(o, AYSE, AYRILAN)
    ids = _tohum(o, ((AYRILAN, 2),))
    assert o.yerel.post("/api/operators/remove", json={"email": AYRILAN}).status_code == 200
    r = o.yerel.post("/api/ai/log/delete", json={"id": ids[AYRILAN][0], "operator_email": AYRILAN})
    assert (r.status_code, _say(o).get(AYRILAN)) == (428, 2), (r.status_code, r.text[:150], _say(o))


def test_KRITIK_eski_APK_cihaz_jetonuyla_LAN_operator_jetonu_YOK_beyanla_silemez(o):
    _hekimler(o, AYSE, AYRILAN)
    _tohum(o, ((AYRILAN, 2),))
    assert o.yerel.post("/api/operators/remove", json={"email": AYRILAN}).status_code == 200
    cihaz = o.lan.get("/api/auth/token").json()["token"]
    r = o.lan.post(
        "/api/ai/log/delete_all",
        json={"confirm": "DELETE_ALL", "operator_email": AYRILAN},
        headers={"X-API-Key": cihaz},
    )
    assert (r.status_code, _say(o).get(AYRILAN)) == (428, 2), (r.status_code, r.text[:150], _say(o))


def test_KARSIT_jetonlu_hekim_kendi_kapsamini_siler_beyan_yok_sayilir(o):
    j = _hekimler(o, AYSE, MEHMET)
    _tohum(o, ((AYSE, 2), (MEHMET, 2), (PAYLASILAN, 1)))
    r = o.yerel.post(
        "/api/ai/log/delete_all",
        json={"confirm": "DELETE_ALL", "operator_email": PAYLASILAN},
        headers={"X-PEMF-Operator": j[AYSE]},
    )
    assert r.status_code == 200 and _say(o) == {MEHMET: 2, PAYLASILAN: 1}, (r.text[:150], _say(o))


def test_KARSIT_KURAL2_operatorsuz_klinikte_beyan_kapsamdir(o):
    ids = _tohum(o, ((TEK, 3), ("", 1)))
    r1 = o.yerel.post("/api/ai/log/delete", json={"id": ids[TEK][0], "operator_email": TEK})
    r2 = o.yerel.post("/api/ai/log/delete_all", json={"confirm": "DELETE_ALL", "operator_email": TEK})
    assert (r1.status_code, r2.status_code) == (200, 200), (r1.text[:120], r2.text[:120])
    # Y105 (2-B2): operatörsüz (tek kullanıcılı) cihazda "kendi" toplu silme sahipsiz eski kaydı da siler (önce A-10 gereği kalıyordu).
    assert _say(o) == {}, _say(o)
