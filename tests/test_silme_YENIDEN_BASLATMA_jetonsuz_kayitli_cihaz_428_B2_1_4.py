# -*- coding: utf-8 -*-
"""B2-1.4 (2-B incelemesi · A1 · KÖR KAPI) — kayıtlı operatörlü cihazda HİÇ geçerli jeton yokken (backend yeniden başladı:
jetonlar yalnız bellekte; ya da herkes "Kilitle"di) jetonsuz silme yine 428.

ÖLÇÜLEN KÖR NOKTA: D2.72 kapısının (tests/test_silme_SAHIPLIK_jetondan_D272_Y92.py) HER kayıtlı-operatör kolu `_iki_hekim` ile
İKİ jeton üretir → "kayıtlı operatör var" ile "etkin jeton var" ayrılmıyor. Mutant a4 (Kural 2 ayrımını `operator_tokens.sayi()`
ile yap — makul bir "sadeleştirme") D2.72 kapısında 18/18 YEŞİL kaldı; oysa sahada her yeniden başlatmadan sonra (jeton yok,
operatörler kayıtlı) jetonsuz LAN isteği herkesin hasta/seans kaydını silerdi. Ürün HEAD'de DOĞRU (bu kollar HEAD'de yeşil);
kapı mutantta kırmızı olmalı. Önerilen yer: tests/test_silme_YENIDEN_BASLATMA_jetonsuz_kayitli_cihaz_428_B2_1_4.py
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

AYSE = "dr.ayse@klinik.com"
MEHMET = "dr.mehmet@klinik.com"


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
        yield type("O", (), {"hdb": hdb, "tdb": tdb, "yerel": yerel, "lan": lan})
    finally:
        api.app.dependency_overrides.pop(get_db, None)
        operator_tokens.temizle_hepsi()
        _sil()
        tdb.close_connections()


def _kayitli_ama_jetonsuz(o):
    from servers import operator_tokens

    for e in (AYSE, MEHMET):
        assert (
            o.yerel.post("/api/operators/enroll", json={"email": e, "display_name": e, "pin": "123456"}).status_code
            == 200
        )
        o.yerel.post("/api/operators/verify", json={"email": e, "pin": "123456"})
    operator_tokens.temizle_hepsi()  # yeniden başlatma: jetonlar bellekteydi
    assert operator_tokens.sayi() == 0


def _say(db, tablo, ids):
    with db._get_connection() as c:
        return c.execute(f"SELECT COUNT(*) FROM {tablo} WHERE id IN ({','.join('?' for _ in ids)})", ids).fetchone()[0]


def test_KRITIK_yeniden_baslatma_sonrasi_jetonsuz_LAN_hasta_ve_seans_silme_428(o):
    _kayitli_ama_jetonsuz(o)
    p = [str(o.hdb.add_patient({"name": "P", "species": "Kedi", "operator_email": MEHMET}))]
    s = [int(o.tdb.start_session(treatment_mode="Manuel", patient_name="S", operator_email=MEHMET))]
    kodlar = [
        o.lan.post("/api/patients/delete_bulk", json={"patient_ids": p, "confirm": "DELETE_SELECTED"}).status_code,
        o.lan.delete(f"/api/patients/{p[0]}").status_code,
        o.lan.post("/api/history/delete_bulk", json={"session_ids": s, "confirm": "DELETE_SELECTED"}).status_code,
        o.lan.delete(f"/api/history/{s[0]}").status_code,
    ]
    assert (_say(o.hdb, "patients", p), _say(o.tdb, "treatment_sessions", s)) == (1, 1), kodlar
    assert kodlar == [428, 428, 428, 428], kodlar


def test_KRITIK_yeniden_baslatma_sonrasi_jetonsuz_AI_Tum_Klinik_428(o):
    _kayitli_ama_jetonsuz(o)
    o.tdb.add_ai_analysis(module_id="m", patient_name="A", result_summary="s", operator_email=MEHMET)
    r = o.yerel.post("/api/ai/log/delete_all", json={"confirm": "DELETE_ALL", "all_operators": True})
    with o.tdb._get_connection() as c:
        n = c.execute("SELECT COUNT(*) FROM ai_analyses").fetchone()[0]
    assert (r.status_code, n) == (428, 1), (r.status_code, r.text[:150])
