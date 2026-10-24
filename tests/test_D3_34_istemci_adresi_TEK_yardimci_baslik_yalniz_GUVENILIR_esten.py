# Author: mertaygn, cglrgrkn
"""D3.34 (B-2.4 · B-2.5 · B-2.12 · B-2.20) + İG-9.51 — istemci adresi TEK yardımcıdan (`servers.auth.istemci_adresi`):
`cf-connecting-ip` yalnız TÜNEL AÇIKKEN (`PEMF_ENABLE_TUNNEL=1`) LOOPBACK eşten (cihazdaki cloudflared), `x-forwarded-for` yalnız
BEYANLI ters-proxy'den (`PEMF_TRUSTED_PROXIES`; son atlama — proxy'nin eklediği) kabul edilir; öteki her durumda soket adresi.

ÖLÇÜLEN KUSURLAR (HEAD): başlık güveni dört yerde dört ayrı biçimde —
(B-2.4) şifre sıfırlama kovası `request.client.host`: tünelden gelen her istemci 127.0.0.1 kovasında → internetten 10 yanlış deneme
cihaz ekranındaki (başlıksız loopback) DOĞRU yönetici kodunu da 429'a düşürür (DoS);
(B-2.5) eşleştirme takası kovası `cf-connecting-ip`'e KOŞULSUZ güvenir → LAN'dan her istekte yeni başlık = yeni kova, 8 deneme kilidi
atlanır (6 haneli koda kaba kuvvet);
(B-2.12) denetim izi `via` alanı her başlığa güvenir → LAN cihazı sahte uzak kaynak yazdırır;
(B-2.20) sunucu profili (beyanlı ters-proxy) XFF'i hiç okumaz → tüm istemciler tek kova;
(İG-9.51) rate-limit anahtarı beyanlı proxy'den gelen `cf-connecting-ip` — nginx istemcinin uydurduğu başlığı AYNEN iletir →
her istekte yeni başlık = yeni kova (20 istek 0×429).
Sahte yalnız EN ALT katta (sır deposu, jeton, auth DB yazımı, beyanlı proxy listesi).
"""

from __future__ import annotations

import ipaddress
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

KOD = "615204"
YONETICI = "D3-34-YONETICI-KODU"


def _istek(host: str, basliklar: dict | None = None):
    return SimpleNamespace(
        client=SimpleNamespace(host=host), headers={k.lower(): v for k, v in (basliklar or {}).items()}
    )


@pytest.fixture
def uygulama(monkeypatch):
    import servers.auth as auth
    import utils.secrets_manager as sm
    from servers import api_server
    from servers import auth_router as ar

    monkeypatch.setattr(sm, "get_secret", lambda ad, *a, **k: KOD if ad == "pairing_code" else "")
    monkeypatch.setattr(auth, "get_api_token", lambda *a, **k: "d3-34-sahte-jeton")
    monkeypatch.setattr(ar, "_admin_reset_code", lambda: YONETICI)
    monkeypatch.setattr(ar, "_exchange_throttle", {})
    monkeypatch.setattr(ar, "_reset_throttle_by_ip", {})
    monkeypatch.setattr(ar, "_reset_throttle", {"fails": 0, "until": 0.0})
    import database.auth_db as adb

    monkeypatch.setattr(adb, "get_auth_db", lambda: SimpleNamespace(reset_password=lambda e, p: (True, "")))
    monkeypatch.setattr(auth, "_TRUSTED_PROXIES", [])
    monkeypatch.setenv(
        "PEMF_ENABLE_TUNNEL", "1"
    )  # cihaz profili (device.env): tünel açık, cloudflared loopback'ten iletir

    def istemci(host: str):
        return TestClient(api_server.app, client=(host, 51334))

    return istemci, ar, auth


def _sifirla(c, kod: str, basliklar: dict | None = None):
    return c.post(
        "/api/auth/reset",
        json={"email": "hekim@klinik.test", "admin_code": kod, "new_password": "Yeni1Sifre"},
        headers=basliklar or {},
    )


def test_KRITIK_B_2_4_tunelden_yanlis_denemeler_CIHAZ_EKRANINDAKI_dogru_sifirlamayi_KILITLEMEZ(uygulama):
    istemci, ar, auth = uygulama
    tunel = {"cf-connecting-ip": "203.0.113.50", "cf-ray": "8b2c3d4e5f60-FRA"}
    c = istemci("127.0.0.1")
    for _ in range(10):
        assert _sifirla(c, "YANLIS", tunel).json().get("ok") is False
    assert _sifirla(c, "YANLIS", tunel).status_code == 429, "tünel istemcisi kendi kovasında kilitlenmedi"
    r = _sifirla(c, YONETICI)  # başlıksız loopback = cihazın kendi ekranı
    assert r.status_code == 200 and r.json().get("ok") is True, (
        f"internetten 10 deneme yerel sıfırlamayı kilitledi: {r.status_code}"
    )


def test_KRITIK_B_2_5_LANdan_her_istekte_YENI_cf_basligi_takas_kilidini_ATLATAMAZ(uygulama):
    istemci, ar, auth = uygulama
    c = istemci("192.168.1.30")
    for i in range(8):
        r = c.post("/api/auth/exchange", json={"code": "000000"}, headers={"cf-connecting-ip": f"198.51.100.{i + 1}"})
        assert r.status_code == 403
    r = c.post("/api/auth/exchange", json={"code": KOD}, headers={"cf-connecting-ip": "198.51.100.99"})
    assert r.status_code == 429, f"uydurma cf başlığıyla kilit atlandı ({r.status_code}) — 6 haneli koda kaba kuvvet"


def test_KARSIT_B_2_5_tunel_istemcileri_AYRI_kovalarda(uygulama):
    istemci, ar, auth = uygulama
    c = istemci("127.0.0.1")
    for _ in range(8):
        c.post("/api/auth/exchange", json={"code": "000000"}, headers={"cf-connecting-ip": "203.0.113.7"})
    r = c.post("/api/auth/exchange", json={"code": KOD}, headers={"cf-connecting-ip": "203.0.113.8"})
    assert r.json().get("token") == "d3-34-sahte-jeton", (
        "bir tünel istemcisi ötekini kilitledi (cloudflared loopback'ten iletir)"
    )


@pytest.mark.parametrize(
    ("host", "basliklar", "beklenen"),
    [
        pytest.param("192.168.1.50", {"x-forwarded-for": "8.8.8.8"}, "192.168.1.50", id="LAN-XFF-uydurma"),
        pytest.param("192.168.1.50", {"cf-connecting-ip": "8.8.8.8"}, "192.168.1.50", id="LAN-cf-uydurma"),
        pytest.param("127.0.0.1", {"cf-connecting-ip": "203.0.113.9"}, "127.0.0.1 (via 203.0.113.9)", id="tunel"),
        pytest.param("127.0.0.1", {"x-forwarded-for": "203.0.113.9"}, "127.0.0.1", id="beyansiz-loopback-XFF"),
        pytest.param("192.168.1.50", {}, "192.168.1.50", id="basliksiz"),
    ],
)
def test_KRITIK_B_2_12_denetim_izi_via_yalniz_GUVENILIR_esten(uygulama, host, basliklar, beklenen):
    from servers.audit_log import istemci_ip

    assert istemci_ip(_istek(host, basliklar)) == beklenen


def test_KRITIK_B_2_20_beyanli_proxy_arkasinda_XFF_SON_atlamasi_istemcidir(uygulama, monkeypatch):
    istemci, ar, auth = uygulama
    from servers.api_server import _rl_client_ip

    monkeypatch.setattr(auth, "_TRUSTED_PROXIES", [ipaddress.ip_network("127.0.0.1/32")])
    anahtarlar = {_rl_client_ip(_istek("127.0.0.1", {"x-forwarded-for": f"9.9.9.9, 203.0.113.{i}"})) for i in range(5)}
    assert anahtarlar == {f"203.0.113.{i}" for i in range(5)}, (
        f"beyanlı proxy arkasında tek kova / ilk (uydurulabilir) atlama: {anahtarlar}"
    )
    monkeypatch.setattr(auth, "_TRUSTED_PROXIES", [])
    assert _rl_client_ip(_istek("127.0.0.1", {"x-forwarded-for": "203.0.113.1"})) == "127.0.0.1", (
        "beyansız XFF'e güvenildi"
    )
    assert _rl_client_ip(_istek("192.168.1.9", {"cf-connecting-ip": "203.0.113.1"})) == "192.168.1.9"


def test_KRITIK_IG_9_51_sunucu_profilinde_proxynin_ILETTIGI_uydurma_cf_basligi_anahtar_DEGIL(uygulama, monkeypatch):
    """deploy/server.env: PEMF_ENABLE_TUNNEL=0, PEMF_TRUSTED_PROXIES=127.0.0.1,::1 (nginx). İstemcinin gönderdiği cf-connecting-ip
    nginx'ten AYNEN geçer — her istekte yeni değer = yeni kova olmamalı; anahtar XFF'in son atlaması (nginx'in eklediği)."""
    istemci, ar, auth = uygulama
    from servers.api_server import _rl_client_ip

    monkeypatch.setenv("PEMF_ENABLE_TUNNEL", "0")
    monkeypatch.setattr(auth, "_TRUSTED_PROXIES", [ipaddress.ip_network("127.0.0.1/32")])
    anahtarlar = {
        _rl_client_ip(_istek("127.0.0.1", {"cf-connecting-ip": f"198.51.100.{i}", "x-forwarded-for": "203.0.113.77"}))
        for i in range(20)
    }
    assert anahtarlar == {"203.0.113.77"}, (
        f"uydurma cf başlığı rate-limit kovasını değiştiriyor: {sorted(anahtarlar)[:5]}"
    )
    assert _rl_client_ip(_istek("127.0.0.1", {"cf-connecting-ip": "198.51.100.1"})) == "127.0.0.1"


def test_KARSIT_tunel_KAPALI_cihazda_loopback_cf_basligi_yok_sayilir(uygulama, monkeypatch):
    istemci, ar, auth = uygulama
    monkeypatch.setenv("PEMF_ENABLE_TUNNEL", "0")
    assert auth.istemci_adresi(_istek("127.0.0.1", {"cf-connecting-ip": "203.0.113.9"})) == "127.0.0.1"
    monkeypatch.setenv("PEMF_ENABLE_TUNNEL", "1")
    assert auth.istemci_adresi(_istek("127.0.0.1", {"cf-connecting-ip": "203.0.113.9, 10.0.0.1"})) == "203.0.113.9"


def test_YAPISAL_D3_34_dort_yer_TEK_yardimciyi_kullanir():
    import inspect

    from servers import api_server, audit_log, auth_router

    kaynak = inspect.getsource(auth_router)
    for uc in ("async def _exchange_code_for_token(", "async def _reset_password("):
        govde = kaynak[kaynak.index(uc) :]
        govde = govde[: govde.index("\n@router") if "\n@router" in govde else len(govde)]
        assert "istemci_adresi(request)" in govde and "request.client.host" not in govde, (
            f"{uc} kendi adres kuralını kuruyor"
        )
        assert 'headers.get("cf-connecting-ip")' not in govde, f"{uc} başlığa doğrudan güveniyor"
    assert "istemci_adresi(request)" in inspect.getsource(api_server._rl_client_ip)
    assert "istemci_adresi(request)" in inspect.getsource(audit_log.istemci_ip)
