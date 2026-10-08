# -*- coding: utf-8 -*-
"""D2.43 · B-2.7 · B-2.10 — tekil seans silme (iki uç), not güncelleme ve dışa/içe aktarma denetim izine OPERATÖRLÜ satır
yazar; var olmayan seansın silinmesi 'success' yerine 404 döner.

ÖLÇÜLEN KUSUR (DENETIM-02 B-2.7 / B-2.10 + 02-2): tedavi kaydının (uygulanan doz dahil) geri dönüşsüz tekil silinmesi izsizdi
(`POST /api/history/delete`, `DELETE /api/history/{id}`: iz 0); not güncelleme izsizdi; kliniğin TÜM verisinin makineden
çıkışı (`data.export`) ve geri yüklemesi (`data.import`) izde OPERATÖRSÜZ (`yaz`, jetonlu istekte de ''); olmayan seansı
silmek 'success' dönüyordu. Desen hazırdı: `delete_bulk` ve hasta silme `kimlikli_yaz` kullanıyor.

KURAL: her tekil silme / not güncelleme / dışa-içe aktarma `kimlikli_yaz` ile (kimlik sunucuda çözülür: jeton; Kural 2'de
beyan yok → ''). İÇERİK YAZILMAZ: not METNİ ize girmez. Olmayan seans → 404 (iz `bulunamadi`).
GERÇEK: uçlar (TestClient — yerel istemci: dışa/içe aktarma ayrıcalıklı), `operator_tokens`, `auth_db`, hasta + tedavi DB'leri
(geçici). Ölçüt `audit_events` satırları ve ham satır sayısı.
"""

import base64
import json

import pytest
from fastapi.testclient import TestClient

AYSE = "dr.ayse@klinik.com"
MEHMET = "dr.mehmet@klinik.com"
PAROLA = "klinik-yedek-2026-D243"
GIZLI_NOT = "GIZLI-NOT-METNI-D243"


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
    monkeypatch.setattr(api, "get_patient_database", lambda: hdb)
    monkeypatch.setattr(api, "_get_treatment_db", lambda: tdb)
    api.app.dependency_overrides[get_db] = lambda: tdb
    yerel = TestClient(api.app, client=("127.0.0.1", 51834))

    def _sil():
        for op in yerel.get("/api/operators").json().get("data", []):
            yerel.post("/api/operators/remove", json={"email": op["email"]})

    operator_tokens.temizle_hepsi()
    _sil()
    try:
        yield type("O", (), {"hdb": hdb, "tdb": tdb, "c": yerel})
    finally:
        api.app.dependency_overrides.pop(get_db, None)
        operator_tokens.temizle_hepsi()
        _sil()
        tdb.close_connections()


def _jeton(o, e=AYSE):
    assert o.c.post("/api/operators/enroll", json={"email": e, "display_name": e, "pin": "123456"}).status_code == 200
    return o.c.post("/api/operators/verify", json={"email": e, "pin": "123456"}).json()["operator_token"]


def _h(j):
    return {"X-PEMF-Operator": j} if j else {}


def _seans(o, sahip=AYSE):
    return int(o.tdb.start_session(treatment_mode="Manuel", patient_name="Boncuk", operator_email=sahip or None))


def _iz(o, olay):
    return [dict(s, detail=json.loads(s["detail"] or "{}")) for s in o.tdb.denetim_oku(200, olay)]


def _var(o, sid):
    with o.tdb._get_connection() as c:
        return c.execute("SELECT COUNT(*) FROM treatment_sessions WHERE id = ?", (sid,)).fetchone()[0]


@pytest.mark.parametrize("uc", ["POST /delete", "DELETE /{id}"])
def test_KRITIK_tekil_silme_IZE_operatorlu_yazilir(o, uc):
    """MUTASYON: tekil silmedeki `kimlikli_yaz` çağrısını silmek → KIRMIZI."""
    j = _jeton(o)
    sid = _seans(o)
    if uc == "POST /delete":
        r = o.c.post("/api/history/delete", json={"session_id": sid}, headers=_h(j))
    else:
        r = o.c.delete(f"/api/history/{sid}", headers=_h(j))
    assert r.status_code == 200 and _var(o, sid) == 0, r.text[:200]
    iz = _iz(o, "history.delete")
    assert [(s["operator_email"], s["scope"], s["item_count"], s["outcome"]) for s in iz] == [
        (AYSE, f"id={sid}", 1, "ok")
    ], iz


@pytest.mark.parametrize("uc", ["POST /delete", "DELETE /{id}"])
def test_KRITIK_OLMAYAN_seans_404_ve_izde_bulunamadi(o, uc):
    j = _jeton(o)
    baska = _seans(o)
    if uc == "POST /delete":
        r = o.c.post("/api/history/delete", json={"session_id": 987654}, headers=_h(j))
    else:
        r = o.c.delete("/api/history/987654", headers=_h(j))
    assert r.status_code == 404, f"olmayan seans silmesi {r.status_code} {r.text[:200]}"
    assert _var(o, baska) == 1
    assert [(s["operator_email"], s["outcome"]) for s in _iz(o, "history.delete")] == [(AYSE, "bulunamadi")]


def test_KRITIK_not_guncelleme_IZE_yazilir_METIN_yazilmaz(o):
    j = _jeton(o)
    sid = _seans(o)
    r = o.c.post("/api/history/update_notes", json={"session_id": sid, "notes": GIZLI_NOT}, headers=_h(j))
    assert r.status_code == 200, r.text[:200]
    iz = _iz(o, "history.notes")
    assert [(s["operator_email"], s["scope"]) for s in iz] == [(AYSE, f"id={sid}")], iz
    assert iz[0]["detail"].get("not_var") is True
    # Sızıntı: DEĞERLER üzerinde (json.dumps metni değil).
    for s in o.tdb.denetim_oku(200):
        for v in list(s.values()) + list(json.loads(s.get("detail") or "{}").values()):
            assert GIZLI_NOT not in str(v), f"not METNİ ize girdi: {s}"


def test_KRITIK_disa_ve_ice_aktarma_IZDE_OPERATORLU(o):
    """MUTASYON: dışa aktarmada `kimlikli_yaz` → `yaz` → KIRMIZI."""
    j = _jeton(o)
    _seans(o)
    r = o.c.post("/api/data/export", json={"passphrase": PAROLA}, headers=_h(j))
    assert r.status_code == 200, r.text[:200]
    blob = r.json()["data_b64"]
    r = o.c.post(
        "/api/data/import", json={"passphrase": PAROLA, "blob_b64": blob, "confirm": "REPLACE_ALL"}, headers=_h(j)
    )
    assert r.status_code == 200, r.text[:300]
    assert [s["operator_email"] for s in _iz(o, "data.export")] == [AYSE]
    assert [s["operator_email"] for s in _iz(o, "data.import")] == [AYSE]


def test_KARSIT_KURAL2_operatorsuz_klinik_siler_iz_SAHIPSIZ(o):
    sid = _seans(o, "")
    r = o.c.delete(f"/api/history/{sid}")
    assert r.status_code == 200 and _var(o, sid) == 0, r.text[:200]
    assert [(s["operator_email"], s["outcome"]) for s in _iz(o, "history.delete")] == [("", "ok")]


def test_KARSIT_tek_silme_baska_seanslara_DOKUNMAZ(o):
    j = _jeton(o)
    a, b = _seans(o), _seans(o)
    o.c.delete(f"/api/history/{a}", headers=_h(j))
    assert (_var(o, a), _var(o, b)) == (0, 1)
