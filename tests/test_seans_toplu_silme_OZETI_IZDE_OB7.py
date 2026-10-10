# -*- coding: utf-8 -*-
"""O-B.7 (2-B gözlemi → 2-F, D2.50 ile) — TOPLU seans silme izi (`history.delete_bulk`) silinen seansların olay / ACİL DURDUR / doz /
sensör SAYILARINI taşır (tekil silmedeki D2.17 kuralıyla aynı).

ÖLÇÜLEN KUSUR: D2.17 tekil silme izine "bu seansla kaç acil durdurma kaydı ve kaç doz kaydı gitti" sayılarını ekledi; toplu silme
(çok daha geniş bir eylem) izinde yalnız seans sayısı vardı → "bu hastaların acil durdurma kayıtlarını ve dozlarını kim sildi" sorusunun
cevabı toplu yolda yoktu. Sayılar SİLMEDEN ÖNCE ve yalnız gerçekten silinecek (sahipliği denetlenmiş) seanslar için alınır; İÇERİK YOK.
GERÇEK uç (TestClient — yerel istemci), GERÇEK operatör jetonu, GERÇEK tedavi DB'si (olaylar/koşular ürünün yazıcılarıyla).
"""

import json
import time

import pytest
from fastapi.testclient import TestClient

AYSE = "dr.ayse@klinik.com"


@pytest.fixture
def o(tmp_path, monkeypatch):
    from database.treatment_history_db import TreatmentHistoryDB
    from servers import api_server as api
    from servers import operator_tokens
    from servers.history_router import get_db

    tdb = TreatmentHistoryDB(tmp_path / "gecmis")
    monkeypatch.setattr(api, "_get_treatment_db", lambda: tdb)
    api.app.dependency_overrides[get_db] = lambda: tdb
    c = TestClient(api.app, client=("127.0.0.1", 51935))

    def _sil():
        for op in c.get("/api/operators").json().get("data", []):
            c.post("/api/operators/remove", json={"email": op["email"]})

    operator_tokens.temizle_hepsi()
    _sil()
    try:
        assert (
            c.post("/api/operators/enroll", json={"email": AYSE, "display_name": "A", "pin": "123456"}).status_code
            == 200
        )
        j = c.post("/api/operators/verify", json={"email": AYSE, "pin": "123456"}).json()["operator_token"]
        yield type("O", (), {"tdb": tdb, "c": c, "h": {"X-PEMF-Operator": j}})
    finally:
        api.app.dependency_overrides.pop(get_db, None)
        operator_tokens.temizle_hepsi()
        _sil()
        tdb.close_connections()


def _dolu_seans(o, olay, estop, kosu, sensor=0):
    sid = int(o.tdb.start_session(treatment_mode="Manuel", patient_name="Boncuk-GIZLI", operator_email=AYSE))
    for i in range(olay):
        tur = "emergency_stop" if i < estop else "coil_ack"
        o.tdb.record_session_event(
            sid, tur, payload={"reason": "GIZLI-YUK"}, severity="critical" if i < estop else "info"
        )
    t0 = time.time()
    for k in range(kosu):
        o.tdb.start_coil_run(sid, k + 1, frequency_hz=10.0, intensity_mt=2.5, started_epoch=t0 + k)
    if sensor:
        o.tdb.add_sensor_samples_batch(sid, [{"coil_id": "1", "sample_ts": t0, "payload": {}} for _ in range(sensor)])
    return sid


def _toplu_sil(o, kimlikler):
    return o.c.post(
        "/api/history/delete_bulk", json={"session_ids": kimlikler, "confirm": "DELETE_SELECTED"}, headers=o.h
    )


def _iz(o):
    iz = o.tdb.denetim_oku(50, "history.delete_bulk")
    assert iz, "ön koşul: toplu silme izi VAR"
    return iz[0], json.loads(iz[0]["detail"] or "{}")


def test_KRITIK_toplu_silme_izi_ESTOP_DOZ_SENSOR_toplamlarini_tasir(o):
    """MUTASYON: izden özet `detail`i çıkarılır ya da sayılar silmeden SONRA alınır → KIRMIZI."""
    a = _dolu_seans(o, olay=3, estop=1, kosu=2, sensor=2)
    b = _dolu_seans(o, olay=2, estop=2, kosu=1)
    r = _toplu_sil(o, [a, b])
    assert r.status_code == 200 and r.json()["silinen"] == 2, r.text
    iz, ayr = _iz(o)
    assert (iz["operator_email"], iz["item_count"]) == (AYSE, 2), iz
    sayilar = (ayr.get("olay"), ayr.get("acil_durdurma"), ayr.get("bobin_kosusu"), ayr.get("sensor_ornegi"))
    assert sayilar == (5, 3, 3, 2), f"toplu silme izi bağlı kayıt sayılarını taşımıyor: {ayr}"


def test_KRITIK_silinmeyen_seansin_kayitlari_SAYILMAZ(o):
    """Yalnız silinen seanslar: listede olmayan seansın olayları toplama girmez. MUTASYON: seans süzgeci düşer → KIRMIZI."""
    a = _dolu_seans(o, olay=1, estop=1, kosu=1)
    _dolu_seans(o, olay=4, estop=4, kosu=4)  # silinmeyen
    assert _toplu_sil(o, [a]).status_code == 200
    _, ayr = _iz(o)
    assert (ayr.get("olay"), ayr.get("acil_durdurma"), ayr.get("bobin_kosusu")) == (1, 1, 1), ayr


def test_KRITIK_izde_ICERIK_yok(o):
    a = _dolu_seans(o, olay=2, estop=1, kosu=1)
    assert _toplu_sil(o, [a]).status_code == 200
    iz, ayr = _iz(o)
    assert "GIZLI" not in json.dumps(ayr, ensure_ascii=False) and "GIZLI" not in str(iz.get("scope")), iz
