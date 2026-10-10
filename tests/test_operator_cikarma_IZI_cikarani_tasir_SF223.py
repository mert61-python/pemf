# -*- coding: utf-8 -*-
"""S-F2-2.3 (2-F incelemesi A2 · Y123 önerilen) — `POST /api/operators/remove` izi kimin ÇIKARDIĞINI da taşır.

ÖLÇÜLEN: iz yalnız ÇIKARILAN hekimi (`operator_email`) taşıyordu; istekte operatör jetonu olsa da "kim çıkardı" sorusunun cevabı izde
yoktu (yalnız istemci IP). Önerilen: istekte operatör jetonu varsa izin `detail`ine `cikaran` — jeton çıkarmadan ÖNCE çözülür (hekim
kendini çıkarırsa jetonu uçta düşer). `operator_email` alanının anlamı DEĞİŞMEZ. Jetonsuz istek (Kural 2 / yerel yönetim) `cikaran`
yazmaz — kanıtsız kimlik ize girmez.
GERÇEK: uç, operatör kaydı / PIN doğrulaması / jeton, `TreatmentHistoryDB` (tmp) denetim izi.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

AYSE = "dr.ayse.sf223@klinik.com"
MEHMET = "dr.mehmet.sf223@klinik.com"


@pytest.fixture
def o(tmp_path, monkeypatch):
    from database.treatment_history_db import TreatmentHistoryDB
    from servers import api_server as api
    from servers import operator_tokens

    kok = tmp_path / "veri"
    kok.mkdir()
    db = TreatmentHistoryDB(kok)
    monkeypatch.setattr(api, "_get_treatment_db", lambda: db)
    monkeypatch.setattr(api, "_app_data_dir", lambda: kok)
    yerel = TestClient(api.app, client=("127.0.0.1", 51437))

    def _sil():
        for op in yerel.get("/api/operators").json().get("data", []):
            yerel.post("/api/operators/remove", json={"email": op["email"]})

    operator_tokens.temizle_hepsi()
    _sil()
    try:
        yield type("O", (), {"db": db, "yerel": yerel})
    finally:
        operator_tokens.temizle_hepsi()
        _sil()
        db.close_connections()


def _kaydet(o, email, pin):
    r = o.yerel.post("/api/operators/enroll", json={"email": email, "display_name": email.split("@")[0], "pin": pin})
    assert r.status_code == 200, r.text[:300]


def _jeton(o, email, pin):
    return o.yerel.post("/api/operators/verify", json={"email": email, "pin": pin}).json()["operator_token"]


def _iz(o):
    izler = o.db.denetim_oku(20, "operator.remove")
    assert izler, "aparat: operator.remove izi yok"
    son = izler[0]
    return son["operator_email"], json.loads(son["detail"]) if son.get("detail") else {}


def test_KRITIK_jetonlu_hekim_BASKASINI_cikarinca_iz_CIKARANI_tasir(o):
    """MUTASYON: `cikaran` yazılmaz → KIRMIZI."""
    _kaydet(o, AYSE, "123456")
    _kaydet(o, MEHMET, "654321")
    j = _jeton(o, AYSE, "123456")
    r = o.yerel.post("/api/operators/remove", json={"email": MEHMET}, headers={"X-PEMF-Operator": j})
    assert r.status_code == 200, r.text[:300]
    cikarilan, detay = _iz(o)
    assert cikarilan == MEHMET, f"izin operator_email anlamı değişti: {cikarilan!r}"
    assert detay.get("cikaran") == AYSE, f"iz kimin çıkardığını taşımıyor: {detay}"


def test_KRITIK_hekim_KENDINI_cikarinca_cikaran_jeton_dusmeden_COZULUR(o):
    """MUTASYON: kimlik çıkarmadan SONRA çözülür (jeton `iptal_email` ile düşmüş) → `cikaran` boş → KIRMIZI."""
    _kaydet(o, AYSE, "123456")
    _kaydet(o, MEHMET, "654321")
    j = _jeton(o, AYSE, "123456")
    r = o.yerel.post("/api/operators/remove", json={"email": AYSE}, headers={"X-PEMF-Operator": j})
    assert r.status_code == 200, r.text[:300]
    cikarilan, detay = _iz(o)
    assert (cikarilan, detay.get("cikaran")) == (AYSE, AYSE), (cikarilan, detay)


def test_KARSIT_jetonsuz_istek_cikaran_YAZMAZ(o):
    _kaydet(o, MEHMET, "654321")
    r = o.yerel.post("/api/operators/remove", json={"email": MEHMET})
    assert r.status_code == 200, r.text[:300]
    cikarilan, detay = _iz(o)
    assert cikarilan == MEHMET and "cikaran" not in detay, (cikarilan, detay)
