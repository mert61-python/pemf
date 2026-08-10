# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""AYRICALIKLI UÇLAR — LAN MUAFİYETİ YOK (2026-08-09 üretim-hazırlık denetimi, ENGEL).

ARIZA: `servers/auth.is_local_request` LAN'ı (10/8, 172.16/12, 192.168/16) auth-MUAF sayar ve
middleware bunu TÜM uçlara uygular. 2026-08-08'de eklenen uçlar niteliksel olarak farklıydı:
  • /api/data/export      → TÜM hasta+seans+AI geçmişini ÇAĞIRANIN parolasıyla tek dosyada verir
  • /api/ai/log/delete_all → VACUUM'lu, geri dönülemez siler
  • /api/operators/enroll  → bir hekimin kimliğini devralmaya izin verir
Bunlar LAN'a kimliksiz açıkken at-rest şifreleme HİÇBİR ŞEY korumaz — veriyi uygulamanın kendisi
çözüp teslim eder. Klinik hotspot parolası da her makinede aynıdır (pemf1234) ve pakette dağıtılır.

KURAL: loopback (cihazın kendisi) VEYA geçerli cihaz token'ı. LAN TEK BAŞINA YETMEZ.
"""

import os

os.environ.pop("PEMF_SIMULATE", None)

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def app():
    from servers import api_server

    return api_server.app


# LAN istemcisi taklidi: TestClient varsayılan 'testclient' host'u yerine GERÇEK bir LAN IP'si.
def _lan(app, **kw):
    return TestClient(app, client=("192.168.1.77", 51234), **kw)


def _loopback(app, **kw):
    return TestClient(app, client=("127.0.0.1", 51234), **kw)


AYRICALIKLI = [
    ("/api/data/export", {"passphrase": "p"}),
    ("/api/data/import", {"passphrase": "p", "blob_b64": "", "confirm": "REPLACE_ALL"}),
    ("/api/ai/log/delete", {"id": 1}),
    ("/api/ai/log/delete_all", {"confirm": "DELETE_ALL"}),
    ("/api/operators/enroll", {"email": "a@x.com", "display_name": "A", "pin": "123456"}),
    ("/api/operators/remove", {"email": "a@x.com"}),
]


@pytest.mark.parametrize("yol,govde", AYRICALIKLI)
def test_KRITIK_LAN_token_olmadan_REDDEDILIR(app, yol, govde):
    """Klinik WiFi'sindeki rastgele bir cihaz bu uçlara ERİŞEMEMELİ."""
    r = _lan(app).post(yol, json=govde)
    assert r.status_code == 403, f"{yol} LAN'dan kimliksiz gecti ({r.status_code})"
    assert "Yerel ağda olmak yeterli değildir" in r.json()["detail"]


@pytest.mark.parametrize("yol,govde", AYRICALIKLI)
def test_loopback_gecer(app, yol, govde):
    """Cihazın KENDİSİ (masaüstü client) engellenmemeli — fiziksel erişim zaten tam yetkidir."""
    r = _loopback(app).post(yol, json=govde)
    assert r.status_code != 403, f"{yol} loopback'ten 403 verdi — masaustu client kirilir"


@pytest.mark.parametrize("yol,govde", AYRICALIKLI)
def test_LAN_gecerli_token_ile_gecer(app, yol, govde, monkeypatch):
    """Eşleştirilmiş mobil uygulama LAN'da token taşır → meşru kullanım KIRILMAMALI."""
    from servers import auth

    monkeypatch.setattr(auth, "check_token", lambda t: t == "DOGRU-TOKEN")
    r = _lan(app).post(yol, json=govde, headers={"X-API-Key": "DOGRU-TOKEN"})
    assert r.status_code != 403, f"{yol} gecerli token'la 403 verdi"


@pytest.mark.parametrize("yol,govde", AYRICALIKLI)
def test_LAN_yanlis_token_REDDEDILIR(app, yol, govde, monkeypatch):
    from servers import auth

    monkeypatch.setattr(auth, "check_token", lambda t: t == "DOGRU-TOKEN")
    r = _lan(app).post(yol, json=govde, headers={"X-API-Key": "YANLIS"})
    assert r.status_code == 403


def test_KRITIK_tunel_istegi_loopback_SAYILMAZ(app):
    """cloudflared 127.0.0.1'DEN bağlanır → proxy başlığı varsa UZAK sayılmalı, yoksa internetten
    gelen bir istek 'cihazın kendisi' gibi görünürdü."""
    r = _loopback(app).post("/api/data/export", json={"passphrase": "p"}, headers={"CF-Connecting-IP": "8.8.8.8"})
    assert r.status_code == 403, "tunelden gelen istek loopback sayildi"


def test_bearer_basligi_da_kabul_edilir(app, monkeypatch):
    """Mobil istemci bazı yollarda Authorization: Bearer kullanır."""
    from servers import auth

    monkeypatch.setattr(auth, "check_token", lambda t: t == "T")
    r = _lan(app).post("/api/ai/log/delete", json={"id": 1}, headers={"Authorization": "Bearer T"})
    assert r.status_code != 403


def test_sorgu_parametresi_token_da_kabul_edilir(app, monkeypatch):
    from servers import auth

    monkeypatch.setattr(auth, "check_token", lambda t: t == "T")
    r = _lan(app).post("/api/ai/log/delete?token=T", json={"id": 1})
    assert r.status_code != 403


def test_SIRADAN_uclar_LAN_muafiyetini_KORUR(app):
    """⚠️ REGRESYON KAPISI: bu düzeltme YALNIZ yıkıcı/PII uçlarını kapsamalı. Telemetri/okuma
    uçları LAN'da token istemeye başlarsa mobil uygulama ve web arayüzü kırılır."""
    for yol in ("/api/health", "/api/ai/log?limit=1", "/api/patients", "/api/operators"):
        r = _lan(app).get(yol)
        assert r.status_code != 403, f"{yol} yanlislikla kapatildi — mesru kullanim kirilir"
