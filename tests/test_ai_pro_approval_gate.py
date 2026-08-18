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
def _kamerasiz(monkeypatch):
    """`_ai_pro_loop`u NO-OP yap — bu dosya ONAY/SAHİPLİK kapısını ölçüyor, kapalı-döngüyü değil.

    ⚠️ CI'DA KIRMIZI OLDU (2026-08-18): gerçek loop `cv2.VideoCapture(0)` açamayınca (başsız
    Linux runner'da kamera YOK) `_ai_loop_active = False` yapıp hemen dönüyor. `/ai/pro/status`
    okumasıyla o thread arasında YARIŞ vardı: Windows'ta kamera açma denemesi yeterince uzun
    sürdüğü için testler geçiyor, Ubuntu'da anında düşüyordu. Yani kırmızılık ÜRÜN HATASI DEĞİL,
    testin ortama bağımlılığıydı — kamerasız makinede loop'un durması DOĞRU davranış.
    Loop'un kendisi `test_kalan_regression_gaps.py`de sahte kamerayla davranışsal olarak sürülüyor."""
    from servers import ai_router

    monkeypatch.setattr(ai_router, "_ai_pro_loop", lambda: None)


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


# ── SAHİPLİK: seansı BAŞLATAN istemci kimliği (denetim 2026-08-17) ────────────


def _onayli_baslat(client, client_id: str = ""):
    rec = ap.create("ai_pro", {"organ_id": 2, "duration_minutes": 20})
    client.post("/api/ai/pro/approve", json={"proposal_id": rec["id"], "operator_email": "dr@k.com"})
    govde = {"proposal_id": rec["id"]}
    if client_id:
        govde["client_id"] = client_id
    return client.post("/api/ai/pro/start", json=govde)


def test_KRITIK_status_seansi_BASLATAN_istemciyi_bildirir(client):
    """`ownerClientId` olmadan istemci "bu seans benim mi" sorusunu yanıtlayamıyordu.

    Kusur: AI Pro panelini yalnızca GÖRÜNTÜLEYEN ikinci istemci, sekmeden çıkınca unmount
    cleanup'ında `/ai/pro/stop` gönderip BAŞKASININ süren otonom seansını (7 bobin) sebep
    söylemeden kesiyordu."""
    assert _onayli_baslat(client, "c1").status_code == 200

    st = client.get("/api/ai/pro/status").json()
    assert st.get("active") is True, st
    assert st.get("ownerClientId") == "c1", f"sahiplik bildirilmiyor: {st}"


def test_stop_SAHIPLIGI_temizler(client):
    assert _onayli_baslat(client, "c1").status_code == 200
    client.post("/api/ai/pro/stop")

    st = client.get("/api/ai/pro/status").json()
    assert st.get("active") is False
    assert st.get("ownerClientId") == "", f"stop sonrasi sahiplik kaldi: {st}"


def test_client_id_GONDERILMEZSE_alan_BOS_ama_VAR(client):
    """⚠️ Alanın VARLIĞI istemci için anlamlı: yoksa (eski backend) panel ESKİ davranışı sürdürür.

    Bu yüzden `client_id` göndermeyen eski bir istemcide alan BOŞ dönmeli ama SİLİNMEMELİ."""
    assert _onayli_baslat(client).status_code == 200

    st = client.get("/api/ai/pro/status").json()
    assert "ownerClientId" in st, f"alan yanittan KAYBOLMUS: {st}"
    assert st["ownerClientId"] == ""


def test_client_id_KIRPILIR_ve_stop_HERKESE_ACIK_kalir(client):
    """⚠️ `client_id` bir YETKİ belirteci DEĞİL: uydurulması kimseye yeni yetki vermez.

    `/ai/pro/stop` gövdesiz ve herkese açık kalmalı — her istemcinin operatörü tedaviyi
    durdurabilmeli. Ayrıca sınırsız uzunlukta bir kimlik saklanmaz (64 karakter kırpma)."""
    assert _onayli_baslat(client, "x" * 200).status_code == 200
    st = client.get("/api/ai/pro/status").json()
    assert len(st["ownerClientId"]) == 64, f"kirpma yok: {len(st['ownerClientId'])}"

    # BAŞKA bir istemci (kimlik göndermeden) durdurabilir.
    assert client.post("/api/ai/pro/stop").status_code == 200
    assert client.get("/api/ai/pro/status").json().get("active") is False
