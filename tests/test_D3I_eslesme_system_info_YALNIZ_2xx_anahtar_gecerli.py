# Author: mertaygn, cglrgrkn
"""D3I-A1.2 (DOĞRULAYICI D) — arayüzün kimlik-yolu anahtar sondası (`discovery.kimlikYoluErisimi`) `/api/system/info`'nun yanıt
koduna bakar. Bu dosya o sondanın DAYANDIĞI backend sözleşmesini ÖLÇER (süreç içi `TestClient`, dinleyici YOK; sahte yalnız EN ALT
katta: `servers.auth` modül durumu — kimlik zorunluluğu / cihaz anahtarı — ve hız sınırı eşiği):

* kimlik zorunluyken UZAK (tünel) istemci: geçerli anahtar → 200; yanlış / eksik anahtar → 401 (bu uç auth-MUAF DEĞİL — muaf
  olsaydı sonda her anahtarı "geçerli" sayardı);
* aynı uzak istemci, YANLIŞ anahtarla — anahtar HİÇ denetlenmeden 401 DIŞI yanıtlar: hız sınırı kovası doluyken 429 (rate-limit
  auth'tan DIŞTA koşar), auth katmanı yüklenemezken 503 (rate-limit kapalı) / 500 (rate-limit açık: kova anahtarı da `servers.auth`'tan);
* kimlik zorunluluğu KAPALI cihaz ve LAN istemcisi (A-01) anahtarsız 200.

Sonuç: arayüz sondası için "anahtar geçerli" = YALNIZ 2xx (`res.ok`); "401 değilse geçerli" kuralı 429 / 5xx'te anahtarı
DOĞRULANMADAN kabul eder. Arayüz kapısı: `apps/ui/src/services/__tests__/pairing.A60.kimlikSondasi.D3I_A1_2.test.ts`.
"""

from __future__ import annotations

import sys

import pytest
from fastapi.testclient import TestClient

DOGRU = "D3I-A12-dogru-anahtar-0123456789abcdef"
YANLIS = "D3I-A12-BASKA-cihazin-anahtari"
TUNEL = {"cf-connecting-ip": "203.0.113.47"}  # cloudflared cihazda koşar, 127.0.0.1'den iletir → UZAK


@pytest.fixture
def ortam(monkeypatch):
    import servers.auth as auth
    from servers import api_server as api

    monkeypatch.setattr(auth, "_require", True)
    monkeypatch.setattr(auth, "_token", DOGRU)
    api._rl_hits.clear()
    yield api, auth, monkeypatch
    api._rl_hits.clear()


def _uzak(api):
    return TestClient(api.app, client=("127.0.0.1", 51347), raise_server_exceptions=False)


def _bilgi(c, anahtar=None, basliklar=TUNEL):
    h = dict(basliklar)
    if anahtar is not None:
        h["X-API-Key"] = anahtar
    return c.get("/api/system/info", headers=h).status_code


def test_SOZLESME_uzak_gecerli_anahtar_200_yanlis_ve_eksik_401(ortam):
    api, _, _ = ortam
    c = _uzak(api)
    assert _bilgi(c, DOGRU) == 200
    assert _bilgi(c, YANLIS) == 401, "uç auth-muaf olduysa arayüz sondası HER anahtarı geçerli sayar"
    assert _bilgi(c) == 401


def test_OLCUM_hiz_siniri_dolu_YANLIS_anahtara_429_anahtar_DENETLENMEZ(ortam):
    api, _, mp = ortam
    mp.setattr(api, "_RL_REMOTE_MAX", 2)
    c = _uzak(api)
    kodlar = [_bilgi(c, YANLIS) for _ in range(4)]
    assert kodlar == [401, 401, 429, 429], kodlar


def test_OLCUM_auth_katmani_yuklenemez_YANLIS_anahtara_401_DISI(ortam):
    api, _, mp = ortam
    mp.setitem(sys.modules, "servers.auth", None)  # `from servers.auth import …` → ImportError (fail-closed dalı)
    c = _uzak(api)
    kod_rl_acik = _bilgi(c, YANLIS)
    mp.setattr(api, "_RL_REMOTE_MAX", 0)
    kod_rl_kapali = _bilgi(c, YANLIS)
    assert kod_rl_kapali == 503, kod_rl_kapali
    assert kod_rl_acik >= 500, kod_rl_acik  # rate-limit kova anahtarı da servers.auth'tan → 500


def test_KARSIT_kimlik_zorunlulugu_KAPALI_ve_LAN_anahtarsiz_200(ortam):
    api, auth, mp = ortam
    lan = TestClient(api.app, client=("192.168.1.20", 51348))
    assert lan.get("/api/system/info").status_code == 200  # A-01: LAN güvenilir ağ
    mp.setattr(auth, "_require", False)
    assert _bilgi(_uzak(api)) == 200
