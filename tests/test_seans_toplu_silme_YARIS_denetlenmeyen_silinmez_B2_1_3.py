# -*- coding: utf-8 -*-
"""B2-1.3 (2-B incelemesi · A1) — toplu seans silme YALNIZ sahipliği denetlenen kimlikleri siler (D2.72 atomikliği yarışta).

ÖLÇÜLEN KUSUR: `delete_sessions_bulk` ucu sahipliği `seans_sahipleri(istenen)` ile okur (var olmayan kimlik "sahiplik sorusuna
girmez"), sonra DELETE'i `istenen` listesinin TAMAMINA koşar. Seans kimlikleri AUTOINCREMENT → kimlikli bir hekim sıradaki
kimlik aralığını silme isteğine koyarsa, denetim ile DELETE arasında açılan BAŞKA hekimin seansı sahiplik sorulmadan silinir.
Gerçek iş parçacıklarıyla ölçüldü (kanca yok): Dr. Ayşe'nin döngüdeki toplu silmesi Dr. Mehmet'in o sırada açılan 35 seansından
2'sini (2. koşu 1'ini) sildi, iz Ayşe'ye `ok`. Bu kapı yarışı BELİRLENİMCİ kurar: ürünün kendi `seans_sahipleri` okuması
döndükten HEMEN SONRA (gerçek pencere) Mehmet'in seansı ürünün kendi yazıcısıyla açılır.
Kural: DELETE yalnız denetimde VAR OLAN kimliklere koşar; üst sınır (TOPLU_SILME_AZAMI) sözleşmesi aynen kalır.
Önerilen yer: tests/test_seans_toplu_silme_YARIS_denetlenmeyen_silinmez_B2_1_3.py
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

AYSE = "dr.ayse@klinik.com"
MEHMET = "dr.mehmet@klinik.com"


@pytest.fixture
def o(tmp_path, monkeypatch):
    from database.treatment_history_db import TreatmentHistoryDB
    from servers import api_server as api
    from servers import operator_tokens
    from servers.history_router import get_db

    tdb = TreatmentHistoryDB(tmp_path / "gecmis")
    monkeypatch.setattr(api, "_get_treatment_db", lambda: tdb)
    api.app.dependency_overrides[get_db] = lambda: tdb
    yerel = TestClient(api.app, client=("127.0.0.1", 51434))
    lan = TestClient(api.app, client=("192.168.1.70", 51435))

    def _sil():
        for op in yerel.get("/api/operators").json().get("data", []):
            yerel.post("/api/operators/remove", json={"email": op["email"]})

    operator_tokens.temizle_hepsi()
    _sil()
    try:
        yield type("O", (), {"tdb": tdb, "yerel": yerel, "lan": lan})
    finally:
        api.app.dependency_overrides.pop(get_db, None)
        operator_tokens.temizle_hepsi()
        _sil()
        tdb.close_connections()


def _hekimler(o):
    j = {}
    for e in (AYSE, MEHMET):
        assert (
            o.yerel.post("/api/operators/enroll", json={"email": e, "display_name": e, "pin": "123456"}).status_code
            == 200
        )
        j[e] = o.yerel.post("/api/operators/verify", json={"email": e, "pin": "123456"}).json()["operator_token"]
    return j


def _var_mi(o, sid):
    with o.tdb._get_connection() as c:
        return c.execute("SELECT COUNT(*) FROM treatment_sessions WHERE id = ?", (sid,)).fetchone()[0]


def _pencerede_ac(o, monkeypatch, sahip):
    """`seans_sahipleri` döner dönmez (denetim bitti, DELETE henüz koşmadı) `sahip` adına seans açar."""
    gercek = o.tdb.seans_sahipleri
    acilan = []

    def _sarili(ids):
        sonuc = gercek(ids)
        if not acilan:
            acilan.append(int(o.tdb.start_session(treatment_mode="Manuel", patient_name="yaris", operator_email=sahip)))
        return sonuc

    monkeypatch.setattr(o.tdb, "seans_sahipleri", _sarili)
    return acilan


def test_KRITIK_denetimden_sonra_acilan_BASKA_hekimin_seansi_toplu_silmede_GITMEZ(o, monkeypatch):
    j = _hekimler(o)
    kendi = int(o.tdb.start_session(treatment_mode="Manuel", patient_name="A", operator_email=AYSE))
    acilan = _pencerede_ac(o, monkeypatch, MEHMET)
    r = o.lan.post(
        "/api/history/delete_bulk",
        json={"session_ids": [kendi, kendi + 1, kendi + 2], "confirm": "DELETE_SELECTED"},
        headers={"X-PEMF-Operator": j[AYSE]},
    )
    assert acilan and acilan[0] == kendi + 1, f"yarış kurulamadı (ölçüm aracı): {acilan}"
    assert _var_mi(o, acilan[0]) == 1, (
        f"Dr. Mehmet'in seansı sahiplik SORULMADAN silindi (denetim penceresinde açıldı): {r.status_code} {r.text[:150]}"
    )
    assert r.status_code == 200 and _var_mi(o, kendi) == 0 and r.json().get("silinen") == 1, r.text[:200]


def test_KARSIT_KURAL2_operatorsuz_klinikte_toplu_silme_aynen(o):
    ids = [
        int(o.tdb.start_session(treatment_mode="Manuel", patient_name=f"T{i}", operator_email="tek@klinik.com"))
        for i in range(3)
    ]
    r = o.lan.post("/api/history/delete_bulk", json={"session_ids": ids + [ids[-1] + 50], "confirm": "DELETE_SELECTED"})
    assert r.status_code == 200 and r.json() == {"status": "success", "istenen": 4, "silinen": 3}, r.text[:200]
    assert sum(_var_mi(o, s) for s in ids) == 0


def test_KARSIT_UST_SINIR_sozlesmesi_aynen_400(o):
    _hekimler(o)
    kendi = int(o.tdb.start_session(treatment_mode="Manuel", patient_name="A", operator_email=AYSE))
    from database.treatment_history_db import TreatmentHistoryDB

    fazla = [kendi] + list(range(kendi + 1000, kendi + 1000 + TreatmentHistoryDB.TOPLU_SILME_AZAMI + 1))
    j = o.yerel.post("/api/operators/verify", json={"email": AYSE, "pin": "123456"}).json()["operator_token"]
    r = o.lan.post(
        "/api/history/delete_bulk",
        json={"session_ids": fazla, "confirm": "DELETE_SELECTED"},
        headers={"X-PEMF-Operator": j},
    )
    assert r.status_code == 400 and _var_mi(o, kendi) == 1, r.text[:200]
