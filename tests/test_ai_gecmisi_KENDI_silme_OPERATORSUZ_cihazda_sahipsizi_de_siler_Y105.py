# -*- coding: utf-8 -*-
"""Y105 (S-B.2 · D2.20 / A-10 sonucu) — kayıtlı operatörü OLMAYAN (tek kullanıcılı) cihazda "kendi AI geçmişimi sil" SAHİPSİZ eski
AI kayıtlarını da siler; çok hekimli klinikte A-10 aynen.

ÖLÇÜLEN DURUM (2-B §3.17 sonucu): A-10 genel uygulandığından operatörsüz cihazda da "kendi geçmişimi sil" sahipsiz (`NULL`/`''`)
eski AI kayıtlarına dokunmuyordu; ev sahibi profili "Tüm Klinik"e çıkamadığı için kendi cihazındaki sahipsiz eski kayıtları HİÇ
silemiyordu (KVKK silme hakkı).
SAHİP KARARI Y105: operatörsüz cihazda "kendi" = kimliğin kayıtları + SAHİPSİZ (boş/NULL) kayıtlar — tek kullanıcılı cihazda sahipsiz
kayıt o kullanıcınındır. Başka bir e-postayla yazılmış kayıt (eski hesap) "kendi" DEĞİLDİR. Kayıtlı operatörlü klinikte A-10 aynen
(sahipsizlere dokunulmaz). Tekil "Kaydı sil" sahipsizi silmez (Y83 aynen).

GERÇEK: uç (TestClient — cihaz 127.0.0.1 / LAN 192.168.1.93 + geçerli cihaz token'ı), `auth_db`, `operator_tokens`, tedavi DB'si
(geçici). Ölçüt ham `SELECT`.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

TEK = "tek@klinik.com"
ESKI = "eski.hesap@klinik.com"
AYSE = "dr.ayse@klinik.com"
TOKEN = {"X-API-Key": "DOGRU-TOKEN"}


@pytest.fixture
def o(tmp_path, monkeypatch):
    from database.treatment_history_db import TreatmentHistoryDB
    from servers import api_server as api
    from servers import auth, operator_tokens

    tdb = TreatmentHistoryDB(tmp_path / "gecmis")
    monkeypatch.setattr(api, "_get_treatment_db", lambda: tdb)
    monkeypatch.setattr(auth, "check_token", lambda t: t == "DOGRU-TOKEN")
    cihaz = TestClient(api.app, client=("127.0.0.1", 52834))
    lan = TestClient(api.app, client=("192.168.1.93", 52835))

    def _sil():
        for op in cihaz.get("/api/operators").json().get("data", []):
            cihaz.post("/api/operators/remove", json={"email": op["email"]})

    operator_tokens.temizle_hepsi()
    _sil()
    try:
        yield type("O", (), {"tdb": tdb, "cihaz": cihaz, "lan": lan})
    finally:
        operator_tokens.temizle_hepsi()
        _sil()
        tdb.close_connections()


def _tohum(o, kendi):
    ids = {}
    for etiket, sahip in (("K1", kendi), ("K2", kendi), ("BOS", ""), ("NULL", None), ("ESKI", ESKI)):
        aid = o.tdb.add_ai_analysis(
            module_id="m", patient_name=f"P-{etiket}", result_summary=f"ozet-{etiket}", operator_email=sahip or ""
        )
        if sahip is None:
            with o.tdb._get_connection() as c:
                c.execute("UPDATE ai_analyses SET operator_email = NULL WHERE id = ?", (aid,))
                c.commit()
        ids[etiket] = aid
    return ids


def _kalan(o):
    with o.tdb._get_connection() as c:
        return sorted(r[0].replace("ozet-", "") for r in c.execute("SELECT result_summary FROM ai_analyses"))


@pytest.mark.parametrize("yer", ["cihaz", "lan"])
def test_KRITIK_OPERATORSUZ_cihazda_kendi_silme_SAHIPSIZ_eski_kayitlari_da_siler(o, yer):
    _tohum(o, TEK)
    r = getattr(o, yer).post(
        "/api/ai/log/delete_all",
        json={"confirm": "DELETE_ALL", "operator_email": TEK},
        headers=TOKEN if yer == "lan" else {},
    )
    assert r.status_code == 200 and r.json()["deleted"] == 4, r.text[:200]
    assert _kalan(o) == ["ESKI"], f"{yer}: sahipsiz eski kayıtlar kaldı ya da başka hesabınki gitti: {_kalan(o)}"


def test_KARSIT_COK_HEKIMLI_klinikte_A10_AYNEN_sahipsize_dokunmaz(o):
    r = o.cihaz.post("/api/operators/enroll", json={"email": AYSE, "display_name": "Dr. Ayşe", "pin": "123456"})
    assert r.status_code == 200, r.text[:200]
    j = o.cihaz.post("/api/operators/verify", json={"email": AYSE, "pin": "123456"}).json()["operator_token"]
    _tohum(o, AYSE)
    r = o.cihaz.post("/api/ai/log/delete_all", json={"confirm": "DELETE_ALL"}, headers={"X-PEMF-Operator": j})
    assert r.status_code == 200 and r.json()["deleted"] == 2, r.text[:200]
    assert _kalan(o) == ["BOS", "ESKI", "NULL"], _kalan(o)


def test_KARSIT_Y83_OPERATORSUZ_cihazda_da_TEKIL_silme_sahipsizi_SILMEZ(o):
    ids = _tohum(o, TEK)
    for etiket in ("BOS", "NULL"):
        r = o.cihaz.post("/api/ai/log/delete", json={"id": ids[etiket], "operator_email": TEK})
        assert r.status_code == 404, (etiket, r.text[:200])
    assert "BOS" in _kalan(o) and "NULL" in _kalan(o)


def test_KARSIT_OPERATORSUZ_kimliksiz_kendi_silme_400_kapsam_belirsiz(o):
    _tohum(o, TEK)
    r = o.cihaz.post("/api/ai/log/delete_all", json={"confirm": "DELETE_ALL"})
    assert r.status_code == 400 and len(_kalan(o)) == 5, r.text[:200]


def test_KARSIT_ACIL_DURDUR_ve_STOP_kapisiz(o):
    assert o.lan.post("/api/session/stop", json={}).status_code == 200
    assert o.lan.post("/api/hardware/emergency_stop").status_code == 200
