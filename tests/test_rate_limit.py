# Author: mertaygn, cglrgrkn
"""Kritik yol (güvenlik B-1.6): uzak (tünel) istekler IP-başı sınırlı; LAN sınırsız;
acil-durdurma/health muaf (fail-safe). Limit modül-globali monkeypatch ile düşürülür."""

import os

os.environ.pop("PEMF_SIMULATE", None)

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def api():
    from servers import api_server

    return api_server


@pytest.fixture(scope="module")
def client(api):
    # DENETIM P3: cf-connecting-ip artik YALNIZCA soket LOOPBACK ise ya da soket beyan edilmis
    # bir ters-proxy ise (PEMF_TRUSTED_PROXIES) rate-limit anahtari olarak kabul edilir —
    # aksi halde saldirgan her istekte farkli bir deger uydurup siniri tamamen atlardi.
    # Gercek dagitimda cloudflared cihazin KENDISINDE kosar ve 127.0.0.1'den iletir; testin de
    # o yolu temsil etmesi icin istemci loopback'ten baglanir (TestClient varsayilani
    # "testclient"tir, gecerli bir IP degildir).
    return TestClient(api.app, client=("127.0.0.1", 45678))


def test_remote_rate_limited_after_threshold(client, api, monkeypatch):
    monkeypatch.setattr(api, "_RL_REMOTE_MAX", 5)
    api._rl_hits.clear()
    h = {"cf-connecting-ip": "203.0.113.10"}  # uzak istemci (proxy header → remote)
    codes = [client.get("/api/system/info", headers=h).status_code for _ in range(7)]
    assert codes[:5] == [200] * 5
    assert codes[5] == 429 and codes[6] == 429


def test_separate_ip_separate_bucket(client, api, monkeypatch):
    monkeypatch.setattr(api, "_RL_REMOTE_MAX", 3)
    api._rl_hits.clear()
    a = {"cf-connecting-ip": "203.0.113.20"}
    b = {"cf-connecting-ip": "203.0.113.21"}
    for _ in range(4):
        client.get("/api/system/info", headers=a)
    assert client.get("/api/system/info", headers=a).status_code == 429  # A limitli
    assert client.get("/api/system/info", headers=b).status_code == 200  # B ayrı kova


def test_emergency_stop_exempt_from_rate_limit(client, api, monkeypatch):
    monkeypatch.setattr(api, "_RL_REMOTE_MAX", 2)
    api._rl_hits.clear()
    h = {"cf-connecting-ip": "203.0.113.30"}
    codes = [client.post("/api/hardware/emergency_stop", headers=h).status_code for _ in range(5)]
    assert 429 not in codes  # acil-durdurma ASLA sınırlanmaz (fail-safe)


def test_health_exempt_from_rate_limit(client, api, monkeypatch):
    monkeypatch.setattr(api, "_RL_REMOTE_MAX", 2)
    api._rl_hits.clear()
    h = {"cf-connecting-ip": "203.0.113.40"}
    codes = [client.get("/api/health", headers=h).status_code for _ in range(5)]
    assert 429 not in codes


def test_unresolvable_client_counted_failclosed(api, monkeypatch):
    """Belirsiz/çözülemeyen istemci (host IP DEĞİL, proxy header YOK) UZAK sayılır
    → fail-closed olarak sınırlanır.

    NOT: paylaşılan `client` fixture'ı artık loopback'ten bağlanıyor (cf-başlığı güven kapısı
    için) ve loopback LAN-muaf olduğundan sınırlanmaz → bu test KENDİ istemcisini kurar ve
    TestClient'ın çözülemeyen varsayılan host'unu ("testclient") kullanır."""
    monkeypatch.setattr(api, "_RL_REMOTE_MAX", 2)
    api._rl_hits.clear()
    c = TestClient(api.app)  # varsayilan host: "testclient" (IP degil → cozulemez)
    codes = [c.get("/api/system/info").status_code for _ in range(3)]
    assert codes[2] == 429  # header yoksa da fail-closed sayım (remote kabul)


def test_cf_header_ignored_from_untrusted_source(api, monkeypatch):
    """DENETIM P3 regresyonu: cf-connecting-ip GUVENILMEYEN kaynaktan gelirse anahtar OLMAMALI.

    Hata: baslik kosulsuz kullaniliyordu → Cloudflare'siz kurulumda (dogrudan LAN / port-forward)
    saldirgan her istekte farkli bir cf-connecting-ip uydurarak rate-limit kovasini degistirip
    siniri TAMAMEN atlayabiliyordu.
    """
    monkeypatch.setattr(api, "_RL_REMOTE_MAX", 3)
    api._rl_hits.clear()
    # LAN'dan (loopback DEGIL, beyan edilmis proxy DEGIL) gelen istemci: baslik yok sayilmali
    c = TestClient(api.app, client=("203.0.113.99", 40000))
    h1 = {"cf-connecting-ip": "198.51.100.1"}
    h2 = {"cf-connecting-ip": "198.51.100.2"}  # her istekte farkli "IP" uydur
    codes = [c.get("/api/system/info", headers=(h1 if i % 2 else h2)).status_code for i in range(6)]
    assert 429 in codes, "uydurma cf-connecting-ip ile rate-limit ATLANMAMALI (tek kova = soket IP)"
