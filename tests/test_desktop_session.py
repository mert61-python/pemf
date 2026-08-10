# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""MASAÜSTÜ OTURUM DEVRİ (E-özelliği, 2026-08-06) — POST/GET/DELETE /api/auth/desktop-session.

Sözleşme: Tauri client Supabase ile giriş yapar, oturumu backend'e devreder, uygulama onu alıp
kendi giriş ekranını ATLAR (çift giriş yok). Bu testler sözleşmenin GÜVENLİK maddelerini kilitler:
  * SADECE 127.0.0.1/::1 — LAN'dan (192.168.x) erişim 403. `is_local_request` LAN'ı da "yerel"
    saydığı için burada KULLANILAMAZ; regresyon olursa kliniğin WiFi'sindeki her cihaz operatörün
    Supabase access_token'ını okuyabilir.
  * Origin denetimi — soket-IP loopback olsa bile istek kullanıcının TARAYICISINDAN gelebilir;
    varsayılan CORS regex'i LAN kökenlerine ACAO verdiği için yanıt okunabilirdi.
  * Token'lar loglanmaz, diske YAZILMAZ (yalnız bellekte; süreç yeniden başlarsa kaybolur).

TUZAK: Starlette TestClient'ın varsayılan istemci host'u 'testclient' (IP değil) → sıkı-loopback
denetimi 403 verir ve testler YANLIŞ nedenle kırmızı olur. `client=("127.0.0.1", 1234)` ŞART.
"""

import logging

import pytest
from fastapi.testclient import TestClient

TOKEN = "eyJhbGciOiJIUzI1NiJ9.SAHTE-ACCESS-TOKEN-lTMLnkQ.imza"
YENILEME = "SAHTE-REFRESH-TOKEN-v1-9c2f"


@pytest.fixture(autouse=True)
def _temiz_oturum():
    """Modül-düzeyi bellek deposu testler arası SIZMASIN."""
    from servers import auth_router

    auth_router._desktop_session.clear()
    yield
    auth_router._desktop_session.clear()


def _yerel() -> TestClient:
    from servers import api_server

    return TestClient(api_server.app, client=("127.0.0.1", 1234))


def _lan() -> TestClient:
    from servers import api_server

    return TestClient(api_server.app, client=("192.168.1.50", 1234))


# ── YUVARLAK YOL: devret → al → çıkış ────────────────────────────────────────
def test_yuvarlak_yol_post_get_delete():
    c = _yerel()
    r = c.post(
        "/api/auth/desktop-session",
        json={"access_token": TOKEN, "refresh_token": YENILEME, "email": "vet@klinik.com", "expires_at": 1893456000},
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True}

    r = c.get("/api/auth/desktop-session")
    assert r.status_code == 200
    veri = r.json()
    assert veri["access_token"] == TOKEN
    assert veri["refresh_token"] == YENILEME
    assert veri["email"] == "vet@klinik.com"
    assert veri["expires_at"] == 1893456000  # sayı olarak KORUNMALI (Supabase int gönderir)

    assert c.delete("/api/auth/desktop-session").json() == {"ok": True}
    assert c.get("/api/auth/desktop-session").json() == {}


def test_oturum_yokken_GET_bos_sozluk_200():
    """'Oturum yok' bir HATA değil — uygulama giriş ekranını gösterir."""
    r = _yerel().get("/api/auth/desktop-session")
    assert r.status_code == 200
    assert r.json() == {}


def test_DELETE_idempotent():
    c = _yerel()
    assert c.delete("/api/auth/desktop-session").status_code == 200
    assert c.delete("/api/auth/desktop-session").status_code == 200


def test_ikinci_POST_oncekini_DEGISTIRIR():
    c = _yerel()
    c.post("/api/auth/desktop-session", json={"access_token": "eski", "email": "a@b.com"})
    c.post("/api/auth/desktop-session", json={"access_token": "yeni", "email": "c@d.com"})
    veri = c.get("/api/auth/desktop-session").json()
    assert veri["access_token"] == "yeni"
    assert veri["email"] == "c@d.com"


# ── SÖZLEŞMENİN ASIL MADDESİ: yalnız loopback ────────────────────────────────
@pytest.mark.parametrize("metod", ["post", "get", "delete"])
def test_LAN_istegi_403(metod):
    c = _lan()
    kw = {"json": {"access_token": TOKEN}} if metod == "post" else {}
    r = getattr(c, metod)("/api/auth/desktop-session", **kw)
    assert r.status_code == 403, f"{metod.upper()} LAN'dan geçti (HTTP {r.status_code})"


def test_LAN_oturumu_OKUYAMAZ():
    """Regresyon kilidi: yerelden devredilen token LAN'daki bir cihaza SIZMAMALI."""
    _yerel().post("/api/auth/desktop-session", json={"access_token": TOKEN})
    r = _lan().get("/api/auth/desktop-session")
    assert r.status_code == 403
    assert TOKEN not in r.text


def test_yardimci_LAN_i_yerel_SAYMAZ():
    """`is_local_request` LAN'ı yerel sayar (bu doğru, DEĞİŞTİRİLMEDİ); yeni sıkı yardımcı saymaz."""
    from servers import auth

    assert auth.is_local_request("192.168.1.50") is True  # mevcut davranış korunuyor
    assert auth.is_loopback_request("192.168.1.50") is False
    assert auth.is_loopback_request("10.0.0.5") is False
    assert auth.is_loopback_request("127.0.0.1") is True
    assert auth.is_loopback_request("::1") is True
    assert auth.is_loopback_request("::ffff:127.0.0.1") is True  # çift-yığın soket
    assert auth.is_loopback_request("127.0.0.1", via_proxy=True) is False
    assert auth.is_loopback_request("") is False


def test_tunel_istegi_403():
    """cloudflared 127.0.0.1'DEN bağlanır → yalnız soket-IP'ye bakmak yetmez; proxy başlığı elenmeli."""
    c = _yerel()
    r = c.get("/api/auth/desktop-session", headers={"CF-Connecting-IP": "203.0.113.9"})
    assert r.status_code == 403


def test_sunucu_profilinde_loopback_GUVENILMEZ(monkeypatch):
    """DENETİM 2026-08-06: `deploy/server.env` = PEMF_API_HOST=127.0.0.1 + PEMF_REQUIRE_AUTH=1.
    Orada backend'e DIŞARIDAN doğrudan bağlanmak imkânsızdır → 127.0.0.1'den gelen her istek
    operatörün ters-proxy'sinden gelir ve nginx `proxy_pass` XFF'i KENDİLİĞİNDEN EKLEMEZ.
    Bu clause olmasaydı cihaz-token'lı UZAK biri masaüstü oturumunu okuyabilir ya da kendi
    oturumunu yerleştirebilirdi (oturum sabitleme). `is_local_request` aynı korumayı zaten
    taşıyor; token TAŞIYAN bu uçta evleviyetle gerekli. Klinik profili (0.0.0.0) etkilenmez."""
    from servers import auth

    monkeypatch.setattr(auth, "_LOOPBACK_BIND", None)
    monkeypatch.setattr(auth, "_require", None)
    monkeypatch.setenv("PEMF_API_HOST", "127.0.0.1")
    monkeypatch.setenv("PEMF_REQUIRE_AUTH", "1")
    try:
        assert auth.is_loopback_request("127.0.0.1") is False
        # Cihaz-token'ı OLAN uzak istemci (eşleşmiş telefon) middleware'i geçer → asıl tehdit
        # budur; uç yine de 403 vermeli ve oturumu SIZDIRMAMALI.
        r = _yerel().get("/api/auth/desktop-session", headers={"X-API-Key": auth.get_api_token()})
        assert r.status_code == 403, f"HTTP {r.status_code}: {r.text[:200]}"
    finally:
        monkeypatch.setattr(auth, "_LOOPBACK_BIND", None)
        monkeypatch.setattr(auth, "_require", None)


def test_klinik_profili_ETKILENMEZ(monkeypatch):
    """Yanlış-pozitif kilidi: klinik/launcher (device.env PEMF_API_HOST=0.0.0.0) çalışmaya devam."""
    from servers import auth

    monkeypatch.setattr(auth, "_LOOPBACK_BIND", None)
    monkeypatch.setattr(auth, "_require", None)
    monkeypatch.setenv("PEMF_API_HOST", "0.0.0.0")
    monkeypatch.setenv("PEMF_REQUIRE_AUTH", "1")
    try:
        assert auth.is_loopback_request("127.0.0.1") is True
    finally:
        monkeypatch.setattr(auth, "_LOOPBACK_BIND", None)
        monkeypatch.setattr(auth, "_require", None)


def test_beyan_edilmis_proxy_403(monkeypatch):
    """Başlık EKLEMEYEN bir ters-proxy loopback'ten bağlanırsa da reddedilmeli."""
    from servers import auth

    monkeypatch.setattr(auth, "_TRUSTED_PROXIES", None)
    monkeypatch.setenv("PEMF_TRUSTED_PROXIES", "127.0.0.1/32")
    try:
        assert _yerel().get("/api/auth/desktop-session").status_code == 403
    finally:
        monkeypatch.setattr(auth, "_TRUSTED_PROXIES", None)


# ── TARAYICI/CORS SIZINTISI ──────────────────────────────────────────────────
def test_LAN_kokenli_tarayici_istegi_403():
    """Kötücül LAN sayfası fetch('http://127.0.0.1:8000/...') atarsa soket-IP loopback OLUR;
    Origin denetimi olmasa yanıt (Supabase token) okunabilirdi."""
    _yerel().post("/api/auth/desktop-session", json={"access_token": TOKEN})
    r = _yerel().get("/api/auth/desktop-session", headers={"Origin": "http://192.168.1.50:3000"})
    assert r.status_code == 403
    assert TOKEN not in r.text


@pytest.mark.parametrize("origin", ["http://localhost:8000", "http://127.0.0.1:5173", "http://[::1]:8000"])
def test_loopback_kokeni_GECER(origin):
    """Yerel web arayüzü (masaüstü kısayolu) bozulmamalı."""
    r = _yerel().get("/api/auth/desktop-session", headers={"Origin": origin})
    assert r.status_code == 200, f"{origin} bloklandı"


def test_origin_YOKSA_gecer():
    """Tauri/reqwest yerel istemci Origin göndermez — normal yol."""
    assert _yerel().get("/api/auth/desktop-session").status_code == 200


# ── GÖVDE DAYANIKLILIĞI: doğrulama HİÇ patlamamalı (422 girdiyi yansıtmasın) ─
def test_bozuk_govde_tokeni_YANSITMAZ():
    c = _yerel()
    r = c.post("/api/auth/desktop-session", content=b"{bozuk-json", headers={"Content-Type": "application/json"})
    assert r.status_code == 422  # access_token yok → anlamlı ret
    assert "access_token gerekli" in r.text
    r = c.post("/api/auth/desktop-session", json={"access_token": TOKEN, "expires_at": {"x": 1}})
    assert r.status_code == 200, r.text  # tip uyuşmazlığı ÇÖKERTMEMELİ
    assert TOKEN not in r.text  # yanıt token'ı geri yansıtmamalı


def test_asiri_buyuk_govde_reddedilir():
    r = _yerel().post("/api/auth/desktop-session", json={"access_token": "x" * 20000})
    assert r.status_code == 413


# ── LOG HİJYENİ + DİSKE YAZMA YASAĞI ─────────────────────────────────────────
def test_tokenlar_loga_SIZMAZ(caplog):
    with caplog.at_level(logging.DEBUG):
        c = _yerel()
        c.post(
            "/api/auth/desktop-session",
            json={"access_token": TOKEN, "refresh_token": YENILEME, "email": "vet@klinik.com"},
        )
        c.get("/api/auth/desktop-session")
        c.delete("/api/auth/desktop-session")
    kayit = "\n".join(r.getMessage() for r in caplog.records)
    assert TOKEN not in kayit, "access_token log'a sızdı"
    assert YENILEME not in kayit, "refresh_token log'a sızdı"


def test_diske_YAZILMAZ(monkeypatch, tmp_path):
    """SecretsManager (pemf_secrets.json) KALICI yazar — oturum oraya GİTMEMELİ."""
    from utils import secrets_manager as sm

    yazildi = []
    monkeypatch.setattr(sm, "set_secret", lambda k, v: yazildi.append(k))
    monkeypatch.setattr(sm, "_save", lambda doc: yazildi.append("_save"))

    _yerel().post("/api/auth/desktop-session", json={"access_token": TOKEN, "email": "a@b.com"})
    assert yazildi == [], f"oturum diske yazıldı: {yazildi}"


def test_surec_belleginde_tutulur_ve_SIFIRLANABILIR():
    """Kalıcılık KASITLI olarak client tarafında; backend yeniden başlarsa oturum kaybolur."""
    from servers import auth_router

    _yerel().post("/api/auth/desktop-session", json={"access_token": TOKEN})
    assert auth_router._desktop_session["access_token"] == TOKEN
    auth_router._desktop_session.clear()  # "backend yeniden başladı"
    assert _yerel().get("/api/auth/desktop-session").json() == {}


def test_auth_muafiyetine_EKLENMEDI():
    """Sunucu profilinde (REQUIRE_AUTH=1 + loopback-bind) cihaz-token istenmesi DOĞRU davranış."""
    from servers import auth

    assert not any("desktop-session" in p for p in auth._EXEMPT_PREFIXES)
