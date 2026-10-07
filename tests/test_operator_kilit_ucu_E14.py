# -*- coding: utf-8 -*-
"""D2.E14 · İG-6.63 — "Kilitle" operatör jetonunu SUNUCUDA da iptal eder (`POST /api/operators/lock`).

ÖLÇÜLEN KUSUR (aday doğrulaması İG-6.63, jest kaydı ayrı süreç backend'e uygulandı): "Kilitle" jetonu yalnız istemciden
siliyordu; sunucuda iptal ucu YOKTU (`operator_tokens.iptal(` üründe çağıranı 0). Kilitlenen hekimin jetonunu elinde tutan
HER kopya (ikinci sekme, eski mobil) onun adına AI kaydı ve tedavi seansı yazmayı sürdürüyordu; kayan 12 sa TTL ile jeton
47,9 sa geçerli kaldı (ölçüldü).
SAHİP KARARI Y89: kayan TTL'e mutlak üst ömür ŞİMDİLİK EKLENMEZ — kilit ucu pencereyi kapatır ("seans sürerken jeton ölmesin").

Kural: yetki = jetonun KENDİSİ (yalnız istekteki `X-PEMF-Operator` düşer; başka hekim kilitlenemez). Uç ACİL DURDUR/STOP'a
dokunmaz. Gerçek uçlar (TestClient), gerçek `operator_tokens`, gerçek tedavi DB'si (geçici dizinde).
"""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def api():
    from servers import api_server

    return api_server


@pytest.fixture(scope="module")
def client(api):
    return TestClient(api.app, client=("127.0.0.1", 51234))


@pytest.fixture(autouse=True)
def _temiz(client):
    from servers import operator_tokens

    operator_tokens.temizle_hepsi()
    for o in client.get("/api/operators").json().get("data", []):
        client.post("/api/operators/remove", json={"email": o["email"]})
    yield
    operator_tokens.temizle_hepsi()
    for o in client.get("/api/operators").json().get("data", []):
        client.post("/api/operators/remove", json={"email": o["email"]})


@pytest.fixture
def db(api, tmp_path, monkeypatch):
    from database.treatment_history_db import TreatmentHistoryDB

    d = TreatmentHistoryDB(tmp_path)
    monkeypatch.setattr(api, "_get_treatment_db", lambda: d)
    yield d
    d.close_connections()


def _kaydet_ve_jeton(client, eposta, pin="123456"):
    r = client.post("/api/operators/enroll", json={"email": eposta, "display_name": eposta, "pin": pin})
    assert r.status_code == 200, r.text[:200]
    r = client.post("/api/operators/verify", json={"email": eposta, "pin": pin})
    assert r.status_code == 200, r.text[:200]
    return r.json()["operator_token"]


def _ai_kaydi(client, jeton, beyan, ozet):
    r = client.post(
        "/api/ai/log",
        json={"module_id": "m", "summary": ozet, "operator_email": beyan},
        headers={"X-PEMF-Operator": jeton} if jeton else {},
    )
    assert r.json().get("status") == "success", r.text[:200]


def _sahip(db, ozet):
    return [a.get("operator_email") or "" for a in db.get_ai_analyses(limit=50) if a["result_summary"] == ozet][0]


def test_KRITIK_kilit_ucu_jetonu_IPTAL_eder_ayni_jetonla_kayit_SAHIPSIZ(client, db):
    """MUTASYON: uçtaki `iptal` çağrısını silmek → KIRMIZI (aynı jetonla kayıt yine A'ya yazılır)."""
    ja = _kaydet_ve_jeton(client, "a@klinik.com")
    _ai_kaydi(client, ja, "a@klinik.com", "kilit-oncesi")
    assert _sahip(db, "kilit-oncesi") == "a@klinik.com", "ön koşul: jeton A'ya atfetmeli"

    r = client.post("/api/operators/lock", headers={"X-PEMF-Operator": ja})
    assert r.status_code == 200, f"sunucu kilit ucu yok/çalışmıyor: {r.status_code} {r.text[:200]}"
    assert r.json().get("iptal") is True

    _ai_kaydi(client, ja, "a@klinik.com", "kilit-sonrasi")
    assert _sahip(db, "kilit-sonrasi") == "", (
        "KİLİTLENEN hekimin jetonu sunucuda hâlâ geçerli — ikinci sekme/eski mobil onun adına yazıyor (İG-6.63)"
    )


def test_KARSIT_kilit_YALNIZ_kendi_jetonunu_dusurur_baska_hekim_etkilenmez(client, db):
    """Yetki = jetonun kendisi. MUTASYON: uçta tüm jetonları düşürmek → KIRMIZI."""
    ja = _kaydet_ve_jeton(client, "a@klinik.com")
    jb = _kaydet_ve_jeton(client, "b@klinik.com")
    assert client.post("/api/operators/lock", headers={"X-PEMF-Operator": ja}).status_code == 200
    _ai_kaydi(client, jb, "b@klinik.com", "b-kaydi")
    assert _sahip(db, "b-kaydi") == "b@klinik.com", "A'nın kilidi B'nin jetonunu da düşürdü"


def test_KARSIT_jetonsuz_kilit_hicbir_seyi_dusurmez(client, db):
    ja = _kaydet_ve_jeton(client, "a@klinik.com")
    r = client.post("/api/operators/lock")
    assert r.status_code == 200 and r.json().get("iptal") is False, r.text[:200]
    _ai_kaydi(client, ja, "a@klinik.com", "jetonsuz-kilit-sonrasi")
    assert _sahip(db, "jetonsuz-kilit-sonrasi") == "a@klinik.com"
