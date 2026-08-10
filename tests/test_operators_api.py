# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""CİHAZ OPERATÖRLERİ — API kapıları (2026-08-08).

Veri katmanı `test_device_operators.py`'de test edilir. Buradaki asıl risk KAPILAR:
  * kilitli operatörün "PIN hatalı" sanılıp sonsuza dek denenmesi,
  * hangi e-postaların cihazda kayıtlı olduğunun sızması (operatör-enumeration),
  * listenin PIN hash'i sızdırması.
"""

import os

os.environ.pop("PEMF_SIMULATE", None)

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    """⚠️ 2026-08-09: kayıt/çıkarma uçları artık AYRICALIKLI (loopback veya token) — LAN muafiyeti
    yok. TestClient'ın varsayılan `testclient` host'u IP bile değil, fail-closed reddedilir.
    Masaüstü client'ın GERÇEK adresini kullan; LAN reddi `test_privileged_endpoints.py`'de."""
    from servers import api_server

    return TestClient(api_server.app, client=("127.0.0.1", 51234))


@pytest.fixture(autouse=True)
def _temiz_operatorler(client):
    """Her test kendi operatörleriyle başlasın (uçlar süreç-geneli DB'yi paylaşır)."""
    for o in client.get("/api/operators").json().get("data", []):
        client.post("/api/operators/remove", json={"email": o["email"]})
    yield


def _kaydet(client, eposta="a@klinik.com", ad="Dr. A", pin="123456"):
    r = client.post("/api/operators/enroll", json={"email": eposta, "display_name": ad, "pin": pin})
    assert r.status_code == 200, r.text[:200]
    return eposta


def test_kayit_ve_listeleme(client):
    _kaydet(client, "a@klinik.com", "Dr. Ayşe")
    _kaydet(client, "b@klinik.com", "Dr. Mehmet")
    data = client.get("/api/operators").json()["data"]
    assert {o["email"] for o in data} == {"a@klinik.com", "b@klinik.com"}


def test_KRITIK_liste_PIN_HASH_sizdirmaz(client):
    _kaydet(client)
    ham = client.get("/api/operators").text
    assert "pin_hash" not in ham and "pin_salt" not in ham, "PIN sirri istemciye gitti"


def test_gecersiz_pin_400(client):
    r = client.post("/api/operators/enroll", json={"email": "a@klinik.com", "display_name": "A", "pin": "12"})
    assert r.status_code == 400 and "6 haneli" in r.json()["detail"]


def test_gecersiz_eposta_400(client):
    r = client.post("/api/operators/enroll", json={"email": "bozuk", "display_name": "A", "pin": "123456"})
    assert r.status_code == 400


def test_dogru_pin_gecer(client):
    e = _kaydet(client, pin="424242")
    r = client.post("/api/operators/verify", json={"email": e, "pin": "424242"})
    assert r.status_code == 200 and r.json()["email"] == e


def test_yanlis_pin_401(client):
    e = _kaydet(client, pin="424242")
    r = client.post("/api/operators/verify", json={"email": e, "pin": "000000"})
    assert r.status_code == 401


def test_KRITIK_kayitsiz_eposta_ile_yanlis_pin_AYNI_yanit(client):
    """Farklı yanıt verirsek saldırgan hangi veterinerlerin bu cihazda kayıtlı olduğunu öğrenir."""
    e = _kaydet(client, "kayitli@klinik.com", pin="111111")
    r_kayitli = client.post("/api/operators/verify", json={"email": e, "pin": "000000"})
    r_yok = client.post("/api/operators/verify", json={"email": "yok@klinik.com", "pin": "000000"})
    assert r_kayitli.status_code == r_yok.status_code == 401
    assert r_kayitli.json()["detail"] == r_yok.json()["detail"], "operator-enumeration sizintisi"


def test_KRITIK_kilitli_operator_423_doner(client):
    """423 ≠ 401: kullanıcı 'PIN hatalı' sanıp denemeye devam etmemeli, kilidi anlamalı."""
    e = _kaydet(client, pin="777777")
    for _ in range(6):
        client.post("/api/operators/verify", json={"email": e, "pin": "000000"})
    r = client.post("/api/operators/verify", json={"email": e, "pin": "777777"})
    assert r.status_code == 423, f"kilit bildirilmiyor: {r.status_code}"
    assert "kilitlendi" in r.json()["detail"]


def test_kilit_listede_gorunur(client):
    e = _kaydet(client, pin="777777")
    for _ in range(6):
        client.post("/api/operators/verify", json={"email": e, "pin": "000000"})
    o = [x for x in client.get("/api/operators").json()["data"] if x["email"] == e][0]
    assert o["locked"] is True


def test_operator_cikarma(client):
    e = _kaydet(client)
    assert client.post("/api/operators/remove", json={"email": e}).status_code == 200
    assert client.get("/api/operators").json()["data"] == []
    assert client.post("/api/operators/remove", json={"email": e}).status_code == 404


# ───────── KAYIT KAPISI — API katmanı (2026-08-09 denetimi, ENGEL) ─────────


def test_KRITIK_API_mevcut_kaydin_PINi_eski_PIN_olmadan_DEGISTIRILEMEZ(client):
    """Uç, kayıtlı bir hekimin PIN'ini eski PIN olmadan ezerse kimlik devralınır: saldırgan
    kendi bildiği PIN'i koyar, o hekim olarak geçiş yapar ve kayıtlar ONUN adına yazılır."""
    e = _kaydet(client, pin="111111")
    r = client.post("/api/operators/enroll", json={"email": e, "display_name": "Saldirgan", "pin": "999999"})
    assert r.status_code == 401, f"PIN eski-PIN'siz degistirildi ({r.status_code})"
    assert "mevcut PIN" in r.json()["detail"]
    # Orijinal PIN bozulmamış olmalı, saldırganınki geçmemeli.
    assert client.post("/api/operators/verify", json={"email": e, "pin": "111111"}).status_code == 200
    assert client.post("/api/operators/verify", json={"email": e, "pin": "999999"}).status_code == 401


def test_API_dogru_eski_PIN_ile_degistirilebilir(client):
    e = _kaydet(client, pin="111111")
    r = client.post(
        "/api/operators/enroll", json={"email": e, "display_name": "Dr. A", "pin": "222222", "eski_pin": "111111"}
    )
    assert r.status_code == 200, r.text[:200]
    assert client.post("/api/operators/verify", json={"email": e, "pin": "222222"}).status_code == 200


def test_KRITIK_API_kayit_ucu_KILIDI_SIFIRLAYAMAZ(client):
    """Kilit kayıt ucuyla sıfırlanabilseydi 5-deneme sınırı anlamsızdı: saldırgan her 5 yanlış
    denemeden sonra yeniden kaydolup sayacı sıfırlar, PIN'i kaba kuvvetle kırardı."""
    e = _kaydet(client, pin="777777")
    for _ in range(6):
        client.post("/api/operators/verify", json={"email": e, "pin": "000000"})
    assert client.post("/api/operators/verify", json={"email": e, "pin": "777777"}).status_code == 423

    r = client.post(
        "/api/operators/enroll", json={"email": e, "display_name": "X", "pin": "888888", "eski_pin": "777777"}
    )
    assert r.status_code == 423, f"kilit kayit ucuyla sifirlandi ({r.status_code})"
    assert client.post("/api/operators/verify", json={"email": e, "pin": "777777"}).status_code == 423, "kilit kalkti"


def test_ilk_kayit_eski_PIN_ISTEMEZ(client):
    """Geriye uyum kapısı: yeni operatör eklerken eski PIN sorulmamalı (akış kırılır)."""
    r = client.post("/api/operators/enroll", json={"email": "ilk@klinik.com", "display_name": "İlk", "pin": "123456"})
    assert r.status_code == 200, r.text[:200]
