# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""HEKİM DEĞERLENDİRMESİ — AI analiz sonuçlarında onay/red/düzeltme (2026-08-06, sahip isteği).

Klinik sözleşme: AI çıktısı bir ÖNERİdir. Hekimin kararı kaydın YANINA yazılır; AI'ın ne dediği
KAYBOLMAZ. Değerlendirilmemiş kayıt "onaylı" GİBİ görünmez.
"""

import os

os.environ.pop("PEMF_SIMULATE", None)

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    from servers import api_server

    return TestClient(api_server.app)


def _kayit_ekle(client, summary="Test sonucu") -> int:
    r = client.post(
        "/api/ai/log",
        json={
            "patient_name": "Minnos",
            "module": "Hastalık",
            "module_id": "disease",
            "summary": summary,
            "mode": "veterinarian",
            "input_type": "clinical",
            "result_detail": {"top": "Test"},
            "confidence": 0.8,
        },
    )
    assert r.status_code == 200, r.text[:200]
    return int(r.json()["id"])


# ── varsayılan: DEĞERLENDİRİLMEMİŞ ───────────────────────────────────────────
def test_yeni_kayit_DEGERLENDIRILMEMIS_baslar(client):
    """Değerlendirilmemiş bir AI çıktısını 'onaylı' saymak yanlış güvence olurdu."""
    aid = _kayit_ekle(client)
    kayit = _bul(client, aid)
    assert kayit["review_status"] == ""
    assert kayit["reviewed_by"] == ""


def _bul(client, aid):
    r = client.get("/api/ai/log?limit=50")
    assert r.status_code == 200
    for k in r.json().get("data", []):
        if int(k["id"]) == aid:
            return k
    raise AssertionError(f"kayıt bulunamadı: {aid}")


# ── onay / red / düzeltme ───────────────────────────────────────────────────
def test_onaylama_kaydi_isler(client):
    aid = _kayit_ekle(client)
    r = client.post("/api/ai/log/review", json={"analysis_id": aid, "status": "approved", "reviewed_by": "dr@k.com"})
    assert r.status_code == 200
    k = _bul(client, aid)
    assert k["review_status"] == "approved"
    assert k["reviewed_by"] == "dr@k.com"
    assert k["reviewed_at"]


def test_red_gerekce_ile_islenir(client):
    aid = _kayit_ekle(client)
    r = client.post(
        "/api/ai/log/review",
        json={
            "analysis_id": aid,
            "status": "rejected",
            "note": "Klinik bulgularla uyuşmuyor",
            "reviewed_by": "dr@k.com",
        },
    )
    assert r.status_code == 200
    k = _bul(client, aid)
    assert k["review_status"] == "rejected"
    assert k["review_note"] == "Klinik bulgularla uyuşmuyor"


def test_duzeltme_hekimin_teshisini_saklar(client):
    aid = _kayit_ekle(client)
    r = client.post(
        "/api/ai/log/review",
        json={
            "analysis_id": aid,
            "status": "corrected",
            "note": "Gerçek teşhis: idiyopatik sistit",
            "reviewed_by": "dr@k.com",
        },
    )
    assert r.status_code == 200
    assert _bul(client, aid)["review_note"] == "Gerçek teşhis: idiyopatik sistit"


def test_AI_CIKTISI_degismez_hekim_karari_YANINA_yazilir(client):
    """Sonradan 'model ne demişti?' sorusu cevaplanabilmeli."""
    aid = _kayit_ekle(client, summary="AI: Böbrek yetmezliği %85")
    client.post(
        "/api/ai/log/review",
        json={"analysis_id": aid, "status": "rejected", "note": "Yanlış", "reviewed_by": "dr@k.com"},
    )
    k = _bul(client, aid)
    assert k["result_summary"] == "AI: Böbrek yetmezliği %85", "AI çıktısı EZİLDİ"
    assert k["review_status"] == "rejected"


# ── doğrulama ───────────────────────────────────────────────────────────────
def test_gecersiz_durum_422(client):
    aid = _kayit_ekle(client)
    r = client.post("/api/ai/log/review", json={"analysis_id": aid, "status": "belki"})
    assert r.status_code == 422


def test_RED_gerekcesiz_olamaz(client):
    """Boş bir 'reddedildi' denetim izinde işe yaramaz."""
    aid = _kayit_ekle(client)
    r = client.post("/api/ai/log/review", json={"analysis_id": aid, "status": "rejected"})
    assert r.status_code == 422
    assert "gerekçe" in r.json().get("detail", "").lower()


def test_DUZELTME_aciklamasiz_olamaz(client):
    aid = _kayit_ekle(client)
    r = client.post("/api/ai/log/review", json={"analysis_id": aid, "status": "corrected", "note": "   "})
    assert r.status_code == 422


def test_ONAY_notsuz_olabilir(client):
    """Onaylarken hekimin ayrıca yazacak bir şeyi olmayabilir — zorlamak sürtünme yaratır."""
    aid = _kayit_ekle(client)
    r = client.post("/api/ai/log/review", json={"analysis_id": aid, "status": "approved"})
    assert r.status_code == 200


def test_olmayan_kayit_404(client):
    r = client.post("/api/ai/log/review", json={"analysis_id": 999999999, "status": "approved"})
    assert r.status_code == 404
