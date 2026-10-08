# -*- coding: utf-8 -*-
"""Y114 (S-B2.6 · S-A2.3, 2-B incelemesi) — AI değerlendirmesinin ÖNCEKİ gerekçe ve düzeltilmiş teşhis METİNLERİ AI kaydının
kendi (şifreli) tablosunda GEÇMİŞ olarak saklanır; denetim izi METİNSİZ kalır.

ÖLÇÜLEN KUSUR (2-B incelemesi S-A2.3): `set_ai_review` değerlendirme alanlarını üzerine yazıyor; D2.19 kararın GEÇMİŞİNİ
denetim izine yazdı ama BİLİNÇLİ olarak metinsiz (`gerekce_var`) → hekim ikinci kez değerlendirince önceki red gerekçesi /
düzeltilmiş teşhis METNİ DB'den tümden gidiyordu. Sahip kararı Y114: metin geçmişi `ai_analyses`te (SQLCipher-şifreli
tedavi DB'si) kalır, iz yine metinsiz.
GERÇEK uçlar (`/api/ai/log/review`, `GET /api/ai/log`), GERÇEK `TreatmentHistoryDB`; geçmiş SQL ile okunur; iz `denetim_oku`.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

AYSE = "dr.ayse@klinik.com"
MEHMET = "dr.mehmet@klinik.com"
GEREKCE_1 = "Lezyon sinirlari yanlis-Y114-gizli-gerekce"
TESHIS_2 = "Duzeltilmis teshis: lipom-Y114-gizli"


@pytest.fixture
def o(tmp_path, monkeypatch):
    from database.treatment_history_db import TreatmentHistoryDB
    from servers import api_server as api
    from servers import operator_tokens

    db = TreatmentHistoryDB(tmp_path / "gecmis")
    monkeypatch.setattr(api, "_get_treatment_db", lambda: db)
    yerel = TestClient(api.app, client=("127.0.0.1", 51234))
    lan = TestClient(api.app, client=("192.168.1.50", 51235))

    def _sil():
        for op in yerel.get("/api/operators").json().get("data", []):
            yerel.post("/api/operators/remove", json={"email": op["email"]})

    operator_tokens.temizle_hepsi()
    _sil()
    try:
        yield type("O", (), {"db": db, "yerel": yerel, "lan": lan})
    finally:
        operator_tokens.temizle_hepsi()
        _sil()
        db.close_connections()


def _jetonlar(o):
    j = {}
    for e in (AYSE, MEHMET):
        assert (
            o.yerel.post("/api/operators/enroll", json={"email": e, "display_name": e, "pin": "123456"}).status_code
            == 200
        )
        j[e] = o.yerel.post("/api/operators/verify", json={"email": e, "pin": "123456"}).json()["operator_token"]
    return j


def _degerlendir(o, aid, durum, jeton="", not_="", beyan="", istemci=None):
    return (istemci or o.lan).post(
        "/api/ai/log/review",
        json={"analysis_id": aid, "status": durum, "note": not_, "reviewed_by": beyan},
        headers={"X-PEMF-Operator": jeton} if jeton else {},
    )


def _gecmis_sql(o, aid) -> list:
    with o.db._get_connection() as c:
        ham = c.execute("SELECT COALESCE(review_history, '') FROM ai_analyses WHERE id = ?", (aid,)).fetchone()[0]
    return json.loads(ham) if ham else []


def _iz_ham(o, aid) -> str:
    return json.dumps(
        [s for s in o.db.denetim_oku(200, "ai.review") if s.get("scope") == f"ai_analiz:{aid}"], ensure_ascii=False
    )


def test_KRITIK_ikinci_ve_ucuncu_degerlendirme_ONCEKI_METINLERI_kayitta_SAKLAR(o):
    j = _jetonlar(o)
    aid = o.db.add_ai_analysis(module_id="m", patient_name="P", result_summary="ozet")
    assert _degerlendir(o, aid, "rejected", j[AYSE], GEREKCE_1).status_code == 200
    assert _degerlendir(o, aid, "corrected", j[MEHMET], TESHIS_2).status_code == 200
    assert _degerlendir(o, aid, "approved", j[AYSE]).status_code == 200
    gecmis = _gecmis_sql(o, aid)
    assert [(g.get("status"), g.get("note"), g.get("reviewed_by")) for g in gecmis] == [
        ("rejected", GEREKCE_1, AYSE),
        ("corrected", TESHIS_2, MEHMET),
    ], f"önceki değerlendirme metinleri kayıtta yok: {gecmis}"
    assert all(g.get("reviewed_at") for g in gecmis), "geçmiş girdisi zaman damgasız"
    with o.db._get_connection() as c:
        guncel = c.execute(
            "SELECT review_status, review_note, reviewed_by FROM ai_analyses WHERE id = ?", (aid,)
        ).fetchone()
    assert tuple(guncel) == ("approved", "", AYSE), "güncel değerlendirme alanları değişmemeli"


def test_KARSIT_denetim_izi_METINSIZ_kalir(o):
    j = _jetonlar(o)
    aid = o.db.add_ai_analysis(module_id="m", patient_name="P", result_summary="ozet")
    _degerlendir(o, aid, "rejected", j[AYSE], GEREKCE_1)
    _degerlendir(o, aid, "corrected", j[MEHMET], TESHIS_2)
    iz = _iz_ham(o, aid)
    assert iz.count('"ai.review"') >= 2 or iz.count("ai_analiz:") >= 2, f"ön koşul: iki iz satırı ({iz[:200]})"
    for metin in (GEREKCE_1, TESHIS_2, "gizli"):
        assert metin not in iz and json.dumps(metin)[1:-1] not in iz, f"değerlendirme METNİ denetim izinde: {metin}"


def test_KARSIT_ilk_degerlendirmede_gecmis_BOS_ve_GET_ucu_gecmisi_tasir(o):
    j = _jetonlar(o)
    aid = o.db.add_ai_analysis(module_id="m", patient_name="P", result_summary="ozet")
    assert _degerlendir(o, aid, "rejected", j[AYSE], GEREKCE_1).status_code == 200
    assert _gecmis_sql(o, aid) == [], "ilk değerlendirmede geçmiş boş olmalı"
    assert _degerlendir(o, aid, "approved", j[AYSE]).status_code == 200
    kayit = next(k for k in o.yerel.get("/api/ai/log", params={"limit": 50}).json()["data"] if k["id"] == aid)
    assert [g.get("note") for g in kayit.get("review_history") or []] == [GEREKCE_1], (
        "GET /api/ai/log geçmişi taşımıyor"
    )


def test_KARSIT_Kural2_operatorsuz_klinikte_beyanla_gecmis_yazilir(o):
    aid = o.db.add_ai_analysis(module_id="m", patient_name="P", result_summary="ozet")
    assert _degerlendir(o, aid, "rejected", not_=GEREKCE_1, beyan="tek@klinik.com").status_code == 200
    assert _degerlendir(o, aid, "approved", beyan="tek@klinik.com").status_code == 200
    assert [(g["status"], g["note"]) for g in _gecmis_sql(o, aid)] == [("rejected", GEREKCE_1)]


def test_KARSIT_var_olmayan_kayit_404_ve_gecmis_yazilmaz(o):
    j = _jetonlar(o)
    assert _degerlendir(o, 987654, "approved", j[AYSE]).status_code == 404
