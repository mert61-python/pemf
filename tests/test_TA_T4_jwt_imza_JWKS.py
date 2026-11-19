# -*- coding: utf-8 -*-
"""TA T4 (Y137 · S-D3.9) · jeton kapısı JWT İMZASINI YERELDE (önbellekli JWKS) doğrular; doğrulanamazsa deftere YAZMAZ.

Önce: ücretli kararın kimliği ve yolda kalan ödeme defterine yazılan `sahip`, imzası DOĞRULANMAYAN JWT gövdesinden okunuyordu
(`_jwt_sahip`) → başkasının `sub`'ını taşıyan sahte belirteçle o hesap adına karar / defter kaydı. Ölçüm 19-11: projenin JWKS'i
asimetrik ES256 anahtar veriyor (`kty EC`, `crv P-256`, `use sig`).
Sahte EN ALT katta: JWKS ağ GET'i (`requests.get` / `_jwks_getir`), kasa (`get_secret`), Supabase RPC (`requests.post`); imza
doğrulaması (`cryptography`) GERÇEK. Test anahtarları süreç içinde üretilir (tests/jwt_test_anahtari.py).
"""

from __future__ import annotations

import json
import time
import types

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
from fastapi import HTTPException
from jwt_test_anahtari import TEST_JWKS, TEST_KID, b64u, ec_jwk, es256_imzala, imzali_jwt
from servers import jeton

ANALIZ = "/api/ai/vision/ornek_analiz"
# Gerçek JWKS taşıması modül İÇE AKTARILIRKEN yakalanır (conftest fikstürü testler sırasında onu test anahtarına bağlar).
_GERCEK_JWKS_GETIR = jeton._jwks_getir


@pytest.fixture
def jwks(monkeypatch):
    """JWKS taşıması sayılır; içerik testten değiştirilebilir. Önbellek sıfırdan."""
    durum = {"govde": TEST_JWKS, "cagri": 0, "hata": None}

    def _getir():
        durum["cagri"] += 1
        if durum["hata"]:
            raise durum["hata"]
        return durum["govde"]

    monkeypatch.setattr(jeton, "_jwks_getir", _getir)
    jeton._jwks_onbellek.update(anahtarlar={}, zaman=None, son_zorla=None)
    yield durum
    jeton._jwks_onbellek.update(anahtarlar={}, zaman=None, son_zorla=None)


def _sahip(sub: str) -> str:
    import hashlib

    return hashlib.sha256(sub.encode("utf-8")).hexdigest()[:16]


# ── imza doğrulaması ─────────────────────────────────────────────────────────────────────────────────────────────────────
def test_KRITIK_test_anahtariyla_ES256_imzali_belirtec_dogrulanir_ozet_jwt_sahip_ile_ayni(jwks):
    t = imzali_jwt({"sub": "kullanici-1"})
    assert jeton._jwt_dogrulanmis_sahip(t) == _sahip("kullanici-1") == jeton._jwt_sahip(t)


def test_KRITIK_imzasiz_ya_da_paylasilan_sirli_belirtec_REDDEDILIR(jwks):
    govde = b64u(json.dumps({"sub": "kurban", "exp": int(time.time()) + 3600}).encode())
    for bas in (
        {"alg": "HS256", "typ": "JWT"},
        {"alg": "HS256", "kid": TEST_KID},
        {"alg": "none", "kid": TEST_KID},
        {"alg": "ES256"},
    ):
        sahte = b64u(json.dumps(bas).encode()) + "." + govde + ".sahte-imza"
        assert jeton._jwt_dogrulanmis_sahip(sahte) is None, bas
        assert jeton._jwt_sahip(sahte) == _sahip("kurban")  # eski (imzasız) okuma kimliği UYDURURDU
    assert jwks["cagri"] == 0, "asimetrik olmayan / kid'siz belirteç için JWKS'e (ağa) gidildi"


def test_KRITIK_baskasinin_sub_u_ile_DEGISTIRILMIS_govde_ya_da_BASKA_anahtarla_imza_REDDEDILIR(jwks):
    gercek = imzali_jwt({"sub": "saldirgan"})
    bas, _govde, imza = gercek.split(".")
    yeni_govde = b64u(json.dumps({"sub": "kurban", "exp": int(time.time()) + 3600}).encode())
    assert jeton._jwt_dogrulanmis_sahip(f"{bas}.{yeni_govde}.{imza}") is None
    yabanci = ec.generate_private_key(ec.SECP256R1())
    assert (
        jeton._jwt_dogrulanmis_sahip(es256_imzala({"sub": "kurban", "exp": int(time.time()) + 3600}, anahtar=yabanci))
        is None
    )


def test_sure_kid_alg_ve_govde_kollari(jwks, monkeypatch):
    simdi = int(time.time())
    assert jeton._jwt_dogrulanmis_sahip(imzali_jwt({"sub": "a", "exp": simdi - 30})) == _sahip("a"), (
        "saat payı (60 sn) içinde"
    )
    for govde in (
        {"sub": "a", "exp": simdi - 120},
        {"sub": "a", "exp": True},
        {"sub": "a", "exp": "yarin"},
        {"sub": "a", "exp": None},
    ):
        assert jeton._jwt_dogrulanmis_sahip(es256_imzala(govde)) is None, govde
    assert jeton._jwt_dogrulanmis_sahip(es256_imzala({"sub": "a"})) is None, "exp yok"
    assert jeton._jwt_dogrulanmis_sahip(imzali_jwt({})) is None, "sub yok"
    assert jeton._jwt_dogrulanmis_sahip(imzali_jwt({"sub": ""})) is None
    t = imzali_jwt({"sub": "a"})
    bas, govde, imza = t.split(".")
    assert jeton._jwt_dogrulanmis_sahip(f"{bas}.{govde}.{b64u(b'kisa')}") is None, "ES256 imzası 64 bayt değil"
    assert jeton._jwt_dogrulanmis_sahip(f"{bas}.{govde}") is None
    assert jeton._jwt_dogrulanmis_sahip("") is None and jeton._jwt_dogrulanmis_sahip(None) is None  # type: ignore[arg-type]
    assert jeton._jwt_dogrulanmis_sahip("%%%.%%%.%%%") is None
    rs_bas = {"alg": "RS256", "typ": "JWT", "kid": TEST_KID}  # kid EC anahtarı ama başlık RS256 → alg uyuşmazlığı
    assert jeton._jwt_dogrulanmis_sahip(es256_imzala({"sub": "a", "exp": simdi + 60}, baslik=rs_bas)) is None


def test_iss_varsa_proje_adresiyle_ESLESMELI(jwks, monkeypatch):
    monkeypatch.setattr(jeton, "_proje_kok", lambda: "https://proje.supabase.test")
    assert jeton._jwt_dogrulanmis_sahip(
        imzali_jwt({"sub": "a", "iss": "https://proje.supabase.test/auth/v1"})
    ) == _sahip("a")
    assert jeton._jwt_dogrulanmis_sahip(imzali_jwt({"sub": "a", "iss": "https://baska.supabase.test/auth/v1"})) is None


def test_RS256_JWKS_anahtari_da_dogrulanir(jwks):
    rsa_anahtar = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    n = rsa_anahtar.public_key().public_numbers()
    jwk = {
        "kty": "RSA",
        "kid": "rsa-1",
        "use": "sig",
        "n": b64u(n.n.to_bytes(256, "big")),
        "e": b64u(n.e.to_bytes(3, "big")),
    }
    jwks["govde"] = {"keys": [jwk]}
    bas = b64u(json.dumps({"alg": "RS256", "kid": "rsa-1"}).encode())
    govde = b64u(json.dumps({"sub": "r", "exp": int(time.time()) + 60}).encode())
    imza = rsa_anahtar.sign(f"{bas}.{govde}".encode(), padding.PKCS1v15(), hashes.SHA256())
    assert jeton._jwt_dogrulanmis_sahip(f"{bas}.{govde}.{b64u(imza)}") == _sahip("r")
    assert jeton._jwt_dogrulanmis_sahip(f"{bas}.{govde}.{b64u(imza[::-1])}") is None


# ── JWKS önbelleği ───────────────────────────────────────────────────────────────────────────────────────────────────────
def test_JWKS_ONBELLEKLI_TTL_icinde_tek_cekim_sonra_yeniden(jwks, monkeypatch):
    saat = {"t": 1000.0}
    monkeypatch.setattr(jeton, "time", types.SimpleNamespace(monotonic=lambda: saat["t"], time=time.time))
    for _ in range(3):
        assert jeton._jwt_dogrulanmis_sahip(imzali_jwt({"sub": "a"}))
    assert jwks["cagri"] == 1
    saat["t"] += jeton._JWKS_TTL + 1
    assert jeton._jwt_dogrulanmis_sahip(imzali_jwt({"sub": "a"}))
    assert jwks["cagri"] == 2


def test_bilinmeyen_kid_ZORLA_yeniden_ceker_ama_en_cok_aralikta_bir(jwks, monkeypatch):
    saat = {"t": 1000.0}
    monkeypatch.setattr(jeton, "time", types.SimpleNamespace(monotonic=lambda: saat["t"], time=time.time))
    yeni = ec.generate_private_key(ec.SECP256R1())
    assert jeton._jwt_dogrulanmis_sahip(imzali_jwt({"sub": "a"}))  # 1. çekim
    dondu = es256_imzala({"sub": "a", "exp": int(time.time()) + 60}, anahtar=yeni, kid="yeni-kid")
    assert (
        jeton._jwt_dogrulanmis_sahip(dondu) is None and jwks["cagri"] == 2
    )  # bilinmeyen kid → zorla çekim (henüz yok)
    assert jeton._jwt_dogrulanmis_sahip(dondu) is None and jwks["cagri"] == 2  # aralık dolmadı → ağa ÇIKILMAZ
    jwks["govde"] = {"keys": [*TEST_JWKS["keys"], ec_jwk(yeni, "yeni-kid")]}  # anahtar dönüşü yayımlandı
    saat["t"] += jeton._JWKS_ZORLA_ARALIK
    assert jeton._jwt_dogrulanmis_sahip(dondu) == _sahip("a") and jwks["cagri"] == 3


def test_JWKS_alinamazsa_ELDEKI_anahtarlar_kullanilir_hic_yoksa_REDDEDILIR(jwks, monkeypatch):
    saat = {"t": 1000.0}
    monkeypatch.setattr(jeton, "time", types.SimpleNamespace(monotonic=lambda: saat["t"], time=time.time))
    jwks["hata"] = ConnectionError("ağ yok")
    assert jeton._jwt_dogrulanmis_sahip(imzali_jwt({"sub": "a"})) is None, "önbellek boş + ağ yok → doğrulanamaz"
    jwks["hata"] = None
    assert jeton._jwt_dogrulanmis_sahip(imzali_jwt({"sub": "a"}))
    saat["t"] += jeton._JWKS_TTL + 1
    jwks["hata"] = ConnectionError("ağ yok")
    assert jeton._jwt_dogrulanmis_sahip(imzali_jwt({"sub": "a"})) == _sahip("a"), "bayat önbellek kullanılır"


def test_JWKS_bozuk_girdileri_ATLANIR_saglam_anahtar_kalir(jwks):
    jwks["govde"] = {
        "keys": [
            "metin",
            {"kty": "EC", "crv": "P-256", "use": "sig"},  # kid yok
            {"kty": "EC", "crv": "P-256", "kid": "sifreleme", "use": "enc", "x": "AA", "y": "AA"},
            {"kty": "oct", "kid": "simetrik", "k": "c2Ly"},
            {"kty": "EC", "crv": "P-256", "kid": "bozuk"},  # x / y yok → atlanır, günlüğe
            *TEST_JWKS["keys"],
        ]
    }
    assert set(jeton._jwks_anahtarlari()) == {TEST_KID}
    jeton._jwks_onbellek.update(anahtarlar={}, zaman=None, son_zorla=None)
    jwks["govde"] = ["liste"]
    assert jeton._jwks_anahtarlari() == {}


def test_JWKS_tasimasi_proje_adresinden_GET_eder_yapilandirma_yoksa_raise(monkeypatch):
    import requests

    cagri: list = []

    class _Y:
        def __init__(self, ok=True):
            self.ok = ok

        def raise_for_status(self):
            if not self.ok:
                raise RuntimeError("HTTP 503")

        def json(self):
            return {"keys": []}

    durum = {"ok": True}
    monkeypatch.setattr(requests, "get", lambda url, **k: (cagri.append((url, k)), _Y(durum["ok"]))[1])
    monkeypatch.setattr(jeton, "_proje_kok", lambda: "")
    with pytest.raises(ConnectionError):
        _GERCEK_JWKS_GETIR()
    assert cagri == []
    monkeypatch.setattr(jeton, "_proje_kok", lambda: "https://proje.supabase.test")
    assert _GERCEK_JWKS_GETIR() == {"keys": []}
    assert cagri == [
        ("https://proje.supabase.test/auth/v1/.well-known/jwks.json", {"timeout": jeton._SUPABASE_TIMEOUT})
    ]
    durum["ok"] = False
    with pytest.raises(RuntimeError):
        _GERCEK_JWKS_GETIR()


def test_proje_kok_kasadan_okunur_sondaki_bolu_atilir(monkeypatch):
    import utils.secrets_manager as sm

    monkeypatch.setattr(
        sm, "get_secret", lambda ad, *a, **k: "https://proje.supabase.test/" if ad == "supabase_url" else None
    )
    assert jeton._proje_kok() == "https://proje.supabase.test"
    monkeypatch.setattr(sm, "get_secret", lambda ad, *a, **k: None)
    assert jeton._proje_kok() == ""


# ── kapı: doğrulanamayan kimlikle karar YOK, deftere kayıt YOK ───────────────────────────────────────────────────────────
class _Istek:
    def __init__(self, token: str):
        self.headers = {"authorization": f"Bearer {token}"}
        self.url = types.SimpleNamespace(path=ANALIZ)
        self.state = types.SimpleNamespace()


@pytest.fixture
def kapi(jwks, tmp_path, monkeypatch):
    monkeypatch.setenv("PEMF_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(jeton, "_DEFTER_GOCU", {})
    monkeypatch.setattr(jeton, "JETON_ENFORCED", True)
    durum = {"okuma": 0, "gonder": 0}

    def _oku(token):
        durum["okuma"] += 1
        return {"aylik_hak": 50, "satin_alinan": 0, "odeme_modeli": "on_odemeli", "kullandikca_borc": 0}

    def _gonder(token, **k):
        durum["gonder"] += 1
        return False  # ağ koptu → yolda kalan ödeme deftere yazılır (YALNIZ doğrulanmış kimlikte)

    monkeypatch.setattr(jeton, "_bakiye_satiri_oku", _oku)
    monkeypatch.setattr(jeton, "_tuketim_gonder_canli", _gonder)
    monkeypatch.setattr(jeton, "_uzlastirmayi_tetikle", lambda token: False)
    durum["defter"] = tmp_path
    return durum


def test_KRITIK_sahte_imzali_KURBAN_kimligiyle_istek_402_ve_eylem_iletisi_bakiye_ve_DEFTER_hic_degmez(kapi):
    govde = b64u(json.dumps({"sub": "kurban", "exp": int(time.time()) + 3600}).encode())
    sahte = b64u(json.dumps({"alg": "HS256", "typ": "JWT"}).encode()) + "." + govde + ".sahte-imza"
    with pytest.raises(HTTPException) as e:
        jeton._jeton_on_karari(_Istek(sahte))
    assert e.value.status_code == 402
    assert e.value.headers[jeton.JETON_SEBEP_BASLIGI] == "kimlik_dogrulanamadi"
    assert e.value.detail == jeton._oturum_dogrulanamadi_mesaj()
    assert kapi["okuma"] == 0 and kapi["gonder"] == 0, "doğrulanamayan kimlikle Supabase'e / tüketime gidildi"
    assert jeton._defter_yoneticisi(sahip=_sahip("kurban")).sahibin_bekleyen_sayisi() == 0


def test_KARSIT_imzasi_dogrulanan_kimlik_karar_alir_ve_yolda_kalan_odeme_KENDI_adina_deftere_yazilir(kapi):
    t = imzali_jwt({"sub": "gercek-kullanici"})
    tuketici = jeton._jeton_on_karari(_Istek(t))
    assert tuketici is not None and kapi["okuma"] == 1
    karar = tuketici()
    assert karar.izinli and kapi["gonder"] == 1
    assert jeton._defter_yoneticisi(sahip=_sahip("gercek-kullanici")).sahibin_bekleyen_sayisi() == 1


def test_ileti_TR_ve_EN_eylem_soyler_seans_ve_acil_durdurma_etkilenmez():
    from utils import ceviri

    tr = json.loads((jeton.Path(ceviri.__file__).resolve().parents[1] / "i18n" / "tr.json").read_text(encoding="utf-8"))
    en = json.loads((jeton.Path(ceviri.__file__).resolve().parents[1] / "i18n" / "en.json").read_text(encoding="utf-8"))
    t, e = tr["jeton"]["mesaj"]["oturumDogrulanamadi"], en["jeton"]["mesaj"]["oturumDogrulanamadi"]
    assert "yeniden giriş" in t and "acil durdurma" in t.lower() and "ETKİLENMEZ" in t
    assert "sign in again" in e.lower() and "emergency stop" in e.lower() and "NOT affected" in e
