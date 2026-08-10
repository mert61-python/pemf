# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""AI PRO SERT KAPISI — UÇ SEVİYESİ (2026-08-06, sahip kararı).

`/api/ai/pro/start` artık ONAYLANMIŞ bir öneri kimliği olmadan otonom tedavi başlatamaz.
Ayrıca uygulanacak organ/süre, istemcinin gövdesinden DEĞİL onaylanan MÜHÜRDEN okunur —
"organ 2'yi onaylat, organ 5'i başlat" saldırısı/kazası yapısal olarak imkânsız olmalı.
"""

import os

os.environ.pop("PEMF_SIMULATE", None)

import pytest
from fastapi.testclient import TestClient

from servers import ai_approval as ap


@pytest.fixture(scope="module")
def client():
    from servers import api_server

    return TestClient(api_server.app)


@pytest.fixture(autouse=True)
def _temiz(client):
    ap.clear()
    client.post("/api/ai/pro/stop")
    yield
    client.post("/api/ai/pro/stop")
    ap.clear()


# ── SERT KAPI ───────────────────────────────────────────────────────────────
def test_proposal_id_YOKKEN_start_428_doner(client):
    r = client.post("/api/ai/pro/start", json={"organ_id": 2, "duration_minutes": 20})
    assert r.status_code == 428, f"onaysız başlatma ENGELLENMEDİ: {r.status_code} {r.text[:200]}"


def test_UYDURMA_proposal_id_ile_start_reddedilir(client):
    r = client.post("/api/ai/pro/start", json={"organ_id": 2, "duration_minutes": 20, "proposal_id": "sahte"})
    assert r.status_code == 428


def test_ONAYLANMAMIS_oneri_ile_start_reddedilir(client):
    rec = ap.create("ai_pro", {"organ_id": 2, "duration_minutes": 20})
    r = client.post("/api/ai/pro/start", json={"proposal_id": rec["id"]})
    assert r.status_code == 428
    assert "onaylanmadı" in r.json().get("detail", "")


def test_REDDEDILMIS_oneri_ile_start_reddedilir(client):
    rec = ap.create("ai_pro", {"organ_id": 2, "duration_minutes": 20})
    client.post(
        "/api/ai/pro/reject", json={"proposal_id": rec["id"], "operator_email": "dr@k.com", "reason": "duty yüksek"}
    )
    r = client.post("/api/ai/pro/start", json={"proposal_id": rec["id"]})
    assert r.status_code == 428
    assert "REDDEDİLDİ" in r.json().get("detail", "")


def test_onay_TEK_KULLANIMLIK_ikinci_start_reddedilir(client):
    rec = ap.create("ai_pro", {"organ_id": 2, "duration_minutes": 20})
    client.post("/api/ai/pro/approve", json={"proposal_id": rec["id"], "operator_email": "dr@k.com"})
    r1 = client.post("/api/ai/pro/start", json={"proposal_id": rec["id"]})
    assert r1.status_code == 200, r1.text[:200]
    client.post("/api/ai/pro/stop")
    r2 = client.post("/api/ai/pro/start", json={"proposal_id": rec["id"]})
    assert r2.status_code == 428
    assert "zaten kullanıldı" in r2.json().get("detail", "")


# ── MÜHÜR: gövdedeki değer onaylananı EZEMEZ ────────────────────────────────
def test_organ_MUHURDEN_okunur_govdedeki_deger_YOK_SAYILIR(client):
    """Onay organ 2 için verildiyse, gövdede organ 5 gönderilse bile organ 2 uygulanmalı."""
    rec = ap.create("ai_pro", {"organ_id": 2, "duration_minutes": 20})
    client.post("/api/ai/pro/approve", json={"proposal_id": rec["id"]})
    r = client.post("/api/ai/pro/start", json={"proposal_id": rec["id"], "organ_id": 5, "duration_minutes": 180})
    assert r.status_code == 200, r.text[:200]
    assert r.json().get("organId") == 2, "gövdedeki organ mührü EZDİ — enerji yanlış organa giderdi"


def test_sure_MUHURDEN_okunur(client):
    rec = ap.create("ai_pro", {"organ_id": 1, "duration_minutes": 5})
    client.post("/api/ai/pro/approve", json={"proposal_id": rec["id"]})
    r = client.post("/api/ai/pro/start", json={"proposal_id": rec["id"], "organ_id": 1, "duration_minutes": 240})
    assert r.status_code == 200
    assert r.json().get("durationMin") == 5, "gövdedeki süre mührü EZDİ (maruziyet uzardı)"


# ── öneri ucu ───────────────────────────────────────────────────────────────
def test_propose_desteklenmeyen_organ_422(client):
    r = client.post("/api/ai/pro/propose", json={"organ_id": 9})
    assert r.status_code == 422


def test_propose_lokalizasyon_YOKKEN_409_ve_ANLASILIR_mesaj(client):
    """Lokalizasyon olmadan öneri üretmek = uydurma parametre. Net mesajla reddedilmeli."""
    r = client.post("/api/ai/pro/propose", json={"organ_id": 2})
    assert r.status_code == 409
    assert "lokalize" in r.json().get("detail", "").lower()


# ── karar uçları ────────────────────────────────────────────────────────────
def test_bilinmeyen_oneri_onaylanamaz_404(client):
    r = client.post("/api/ai/pro/approve", json={"proposal_id": "yok"})
    assert r.status_code == 404


def test_ayni_oneri_iki_kez_karara_baglanamaz_409(client):
    rec = ap.create("ai_pro", {"organ_id": 2, "duration_minutes": 20})
    assert client.post("/api/ai/pro/approve", json={"proposal_id": rec["id"]}).status_code == 200
    r = client.post("/api/ai/pro/reject", json={"proposal_id": rec["id"], "reason": "vazgeçtim"})
    assert r.status_code == 409


def test_red_gerekcesi_kayda_gecer(client):
    rec = ap.create("ai_pro", {"organ_id": 3, "duration_minutes": 10})
    client.post(
        "/api/ai/pro/reject",
        json={"proposal_id": rec["id"], "operator_email": "dr@k.com", "reason": "Lokalizasyon güvenilirliği düşük"},
    )
    kayit = ap.get(rec["id"])
    assert kayit["status"] == ap.REJECTED
    assert kayit["reason"] == "Lokalizasyon güvenilirliği düşük"
    assert kayit["operator"] == "dr@k.com"
