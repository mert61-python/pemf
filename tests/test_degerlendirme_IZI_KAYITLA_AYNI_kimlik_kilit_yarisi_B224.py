# -*- coding: utf-8 -*-
"""B2-2.4 (2-B bağımsız inceleme · A2) — AI değerlendirmesinin denetim izi, KAYDA yazılan kimliği taşır (kilit yarışı).

ÖLÇÜLEN KUSUR: `review_ai_analysis` kimliği bir kez çözer (`_inceleyen`, `kimlik_kaynagi`), kaydı ona yazar; ama başarı izini
`audit_log.kimlikli_yaz` ile yazar ve o, kimliği İSTEKTEN YENİDEN çözer. Değerlendirme DB'ye yazılırken başka bir sekme aynı
hekimi kilitlerse (`POST /api/operators/lock`, D2.E14 — jeton iptal) kayıt `reviewed_by = Ayşe` olur, iz ise
`operator_email = ''`, `kimlik_kaynagi = 'jeton'`, `kanitsiz_beyan = Ayşe` der: delil kaydın kendisiyle çelişir
(sonda `_inceleme/kapsam2_D219/sonda_D219_iz.py` kol 3). Yarış, `set_ai_review` sırasında jetonu iptal eden kanca ile belirlenimci.
KARŞIT: yarışsız jetonlu değerlendirme ve Kural 2 beyanı izde kayıtla aynı kimlik.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

AYSE = "dr.ayse@klinik.com"
TEK = "tek@klinik.com"


@pytest.fixture
def o(tmp_path, monkeypatch):
    from database.treatment_history_db import TreatmentHistoryDB
    from servers import api_server as api
    from servers import operator_tokens

    db = TreatmentHistoryDB(tmp_path / "gecmis")
    monkeypatch.setattr(api, "_get_treatment_db", lambda: db)
    yerel = TestClient(api.app, client=("127.0.0.1", 51934))
    lan = TestClient(api.app, client=("192.168.1.84", 51935))

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


def _jeton(o, e):
    assert (
        o.yerel.post("/api/operators/enroll", json={"email": e, "display_name": e, "pin": "123456"}).status_code == 200
    )
    return o.yerel.post("/api/operators/verify", json={"email": e, "pin": "123456"}).json()["operator_token"]


def _kayit_ve_iz(o, aid):
    kayit = next(a for a in o.db.get_ai_analyses(limit=50) if a["id"] == aid)
    iz = [
        (s["operator_email"], s["outcome"], json.loads(s["detail"] or "{}"))
        for s in o.db.denetim_oku(200, "ai.review")
        if s.get("scope") == f"ai_analiz:{aid}"
    ]
    return kayit.get("reviewed_by") or "", iz


def test_KRITIK_kilit_YARISINDA_iz_KAYITLA_ayni_hekimi_tasir(o, monkeypatch):
    """MUTASYON: başarı izini kimliği yeniden çözen `kimlikli_yaz` ile yazmak (bugünkü hâl) → KIRMIZI."""
    from servers import operator_tokens

    j = _jeton(o, AYSE)
    aid = o.db.add_ai_analysis(module_id="m", patient_name="P", result_summary="ozet")
    gercek = o.db.set_ai_review

    def _yarisli(*a, **k):
        operator_tokens.iptal(j)  # başka sekme aynı anda "Kilitle" (POST /api/operators/lock)
        return gercek(*a, **k)

    monkeypatch.setattr(o.db, "set_ai_review", _yarisli)
    r = o.lan.post(
        "/api/ai/log/review",
        json={"analysis_id": aid, "status": "approved", "reviewed_by": AYSE},
        headers={"X-PEMF-Operator": j},
    )
    assert r.status_code == 200, r.text[:200]
    kim, iz = _kayit_ve_iz(o, aid)
    assert kim == AYSE, kim
    assert [(e, d.get("kimlik_kaynagi"), d.get("kanitsiz_beyan")) for e, _o, d in iz] == [(AYSE, "jeton", None)], (
        f"iz kayıtla çelişiyor (kayıt {kim!r}): {iz}"
    )


def test_KARSIT_yarissiz_jetonlu_iz_kayitla_ayni(o):
    j = _jeton(o, AYSE)
    aid = o.db.add_ai_analysis(module_id="m", patient_name="P", result_summary="ozet")
    o.lan.post(
        "/api/ai/log/review",
        json={"analysis_id": aid, "status": "approved", "reviewed_by": AYSE},
        headers={"X-PEMF-Operator": j},
    )
    kim, iz = _kayit_ve_iz(o, aid)
    assert (kim, [(e, d.get("kimlik_kaynagi")) for e, _o, d in iz]) == (AYSE, [(AYSE, "jeton")])


def test_KARSIT_KURAL2_beyan_iz_kayitla_ayni(o):
    aid = o.db.add_ai_analysis(module_id="m", patient_name="P", result_summary="ozet")
    o.lan.post("/api/ai/log/review", json={"analysis_id": aid, "status": "approved", "reviewed_by": TEK})
    kim, iz = _kayit_ve_iz(o, aid)
    assert (kim, [(e, d.get("kimlik_kaynagi")) for e, _o, d in iz]) == (TEK, [(TEK, "beyan")])
