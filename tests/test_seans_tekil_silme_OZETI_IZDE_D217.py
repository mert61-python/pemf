# -*- coding: utf-8 -*-
"""D2.17 · B-3.27 — tekil seans silme izi silinen seansın E-STOP olayını ve DOZ kayıtlarını SAYILARIYLA taşır.

ÖLÇÜLEN KUSUR (DENETIM-03 B-3.27): karttan tek tek silinen seansta "bu hastanın acil durdurma kaydını ve dozunu kim sildi"
sorusunun cevabı yoktu (toplu silme izlenirken tekil silme izsizdi). D2.43 tekil silmeyi operatörlü ize bağladı; bu kapı
izin İÇERİĞİNİ ölçer: silinen olay sayısı, bunların kaçının acil durdurma (`emergency_stop`) olduğu, kaç bobin koşusu (doz
kaydı: süre + frekans + yoğunluk) ve sensör örneğinin gittiği. Sayılar SİLMEDEN ÖNCE alınır. İÇERİK YAZILMAZ: olay yükü,
hasta adı ya da not ize girmez — yalnız sayılar.
GERÇEK: uçlar (TestClient — yerel istemci), operatör jetonu, tedavi DB'si (geçici; olaylar ve koşular ürünün kendi
yazıcılarıyla). Değişiklik yalnız ekleme: silmeyi kısıtlamaz.
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
    c = TestClient(api.app, client=("127.0.0.1", 51934))

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


def _dolu_seans(o, olay=2, estop=1, kosu=2):
    sid = int(o.tdb.start_session(treatment_mode="Manuel", patient_name="Boncuk-GIZLI", operator_email=AYSE))
    for i in range(olay):
        tur = "emergency_stop" if i < estop else "coil_ack"
        o.tdb.record_session_event(
            sid, tur, payload={"reason": "GIZLI-YUK"}, severity="critical" if i < estop else "info"
        )
    t0 = time.time()
    for k in range(kosu):
        o.tdb.start_coil_run(sid, k + 1, frequency_hz=10.0, intensity_mt=2.5, started_epoch=t0 + k)
    return sid


def _son_iz(o):
    iz = o.tdb.denetim_oku(50, "history.delete")
    assert iz, "ön koşul: tekil silme izi VAR (D2.43)"
    return iz[0], json.loads(iz[0]["detail"] or "{}")


@pytest.mark.parametrize("uc", ["POST /delete", "DELETE /{id}"])
def test_KRITIK_tekil_silme_izi_ESTOP_ve_DOZ_sayilarini_tasir(o, uc):
    """MUTASYON: izden özet `detail`ini çıkarmak ya da sayıları silmeden SONRA almak → KIRMIZI."""
    sid = _dolu_seans(o)
    if uc == "POST /delete":
        r = o.c.post("/api/history/delete", json={"session_id": sid}, headers=o.h)
    else:
        r = o.c.delete(f"/api/history/{sid}", headers=o.h)
    assert r.status_code == 200, r.text[:200]
    satir, d = _son_iz(o)
    assert satir["operator_email"] == AYSE
    assert (d.get("olay"), d.get("acil_durdurma"), d.get("bobin_kosusu")) == (2, 1, 2), d


def test_KRITIK_ozet_YALNIZ_silinen_seansi_sayar(o):
    """MUTASYON: sayımda seans süzgecini kaldırmak → KIRMIZI."""
    _dolu_seans(o, olay=3, estop=2, kosu=3)  # başka seans — sayılmamalı
    sid = _dolu_seans(o, olay=1, estop=1, kosu=1)
    o.c.delete(f"/api/history/{sid}", headers=o.h)
    _, d = _son_iz(o)
    assert (d.get("olay"), d.get("acil_durdurma"), d.get("bobin_kosusu")) == (1, 1, 1), d


def test_KRITIK_izde_ICERIK_yok_yalniz_sayilar(o):
    sid = _dolu_seans(o)
    o.c.delete(f"/api/history/{sid}", headers=o.h)
    satir, d = _son_iz(o)
    degerler = [str(v) for v in list(satir.values()) + list(d.values())]
    assert not any("GIZLI" in v for v in degerler), f"olay yükü / hasta adı ize girdi: {satir}"


def test_KARSIT_olaysiz_seans_sifir_sayilarla_silinir(o):
    sid = _dolu_seans(o, olay=0, estop=0, kosu=0)
    r = o.c.delete(f"/api/history/{sid}", headers=o.h)
    assert r.status_code == 200
    _, d = _son_iz(o)
    assert (d.get("olay"), d.get("acil_durdurma"), d.get("bobin_kosusu")) == (0, 0, 0), d
