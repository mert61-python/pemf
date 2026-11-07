# -*- coding: utf-8 -*-
"""KP-3 C · `servers/auth_router.py` kapsanmayan kolları — her test bir DAVRANIŞ iddiası (uçlar doğrudan çağrılır, ağ YOK):

- `/api/auth/token`: sır deposu okunamazsa 500 + "token alınamadı" (istisna sızmaz, yığın izi yanıtta yok).
- `/api/auth/desktop-session`: sözlük olmayan JSON gövde boş sayılır → erişim jetonu yok → 422.
- `/api/auth/exchange`: çözülemeyen gövde = boş kod → 403 + deneme sayılır; doğru kodda sır deposu patlarsa 500 ve sayaç SIFIRLANIR.
- Kısıtlama kovaları (giriş / sıfırlama / eşleştirme): 1000'i aşınca YALNIZ süresi dolmuşlar atılır (etkin kilitler korunur).
- `_safe_compare`: dizgeye çevrilemeyen girdi → False (500 değil, sayaca yazılabilir).
- Oturum jetonu: sır deposu patlarsa yedek sırla imzalanır (giriş yine çalışır).
- `/api/auth/register`: geçersiz e-posta / zayıf şifre / DB reddi ayrı iletilerle.
- `/api/auth/login`: kayıtlı kullanıcı + doğru şifre → jeton + sayaç sıfırlanır; yanlış şifre → `bad_password` (jenerik kipte `invalid`);
  jenerik kipte kayıtsız e-posta → zamanlama eşitleyici sahte doğrulama (patlasa da) + `invalid`.
- `/api/auth/reset`: yönetici kodu yanlış ama cihaz api_token'ı doğru → kabul (break-glass); ardından geçersiz e-posta / zayıf yeni şifre
  reddedilir; küresel arka-durak eşiğinde küresel kilit kurulur ve sayaç sıfırlanır.
- `/api/auth/admin-code`: cihaz yönetici kodunu döndürür.

Sahte EN ALT katta: sır deposu (`utils.secrets_manager.get_secret`), kimlik DB nesnesi (`get_auth_db` dönüşü), saat (`_time`), istek nesnesi.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import types

import pytest
from database import auth_db
from servers import auth
from servers import auth_router as ar
from utils import ceviri, secrets_manager


class _Istek:
    def __init__(self, govde=None, *, json_hatasi: Exception | None = None, host: str = "127.0.0.1", basliklar=None):
        self._govde = govde
        self._hata = json_hatasi
        self.headers = dict(basliklar or {})
        self.client = types.SimpleNamespace(host=host)

    async def json(self):
        if self._hata:
            raise self._hata
        return self._govde


class _KimlikDb:
    def __init__(self, kullanicilar=None, *, dogrulama_hatasi: Exception | None = None, kayit=(True, "")):
        self.k = dict(kullanicilar or {})
        self.dogrulama_hatasi = dogrulama_hatasi
        self.kayit = kayit
        self.dogrulanan: list = []

    def email_exists(self, e):
        return e in self.k

    def verify(self, e, p):
        self.dogrulanan.append(e)
        if self.dogrulama_hatasi:
            raise self.dogrulama_hatasi
        return self.k.get(e) == p

    def register(self, e, p):
        return self.kayit

    def reset_password(self, e, p):
        self.k[e] = p
        return True, ""


def _sirlar(monkeypatch, degerler: dict | None = None, hata: Exception | None = None):
    def _get(ad, *a, **k):
        if hata:
            raise hata
        return (degerler or {}).get(ad)

    monkeypatch.setattr(secrets_manager, "get_secret", _get)


@pytest.fixture
def temiz_kovalar(monkeypatch):
    monkeypatch.setattr(ar, "_login_throttle", {})
    monkeypatch.setattr(ar, "_exchange_throttle", {})
    monkeypatch.setattr(ar, "_reset_throttle_by_ip", {})
    monkeypatch.setattr(ar, "_reset_throttle", {"fails": 0, "until": 0.0})


def _govde(yanit) -> str:
    return yanit.body.decode("utf-8")


def test_token_ucu_sir_deposu_patlarsa_500(monkeypatch):
    def _patla():
        raise OSError("api_token.txt okunamadı")

    monkeypatch.setattr(auth, "get_api_token", _patla)
    y = asyncio.run(ar._get_auth_token(_Istek()))
    assert y.status_code == 500 and ceviri.t("oturum.hata.tokenAlinamadi") in _govde(y)
    assert "api_token.txt" not in _govde(y), "istisna metni yanıta sızdı"


def test_masaustu_oturumu_sozluk_olmayan_govde_422():
    y = asyncio.run(ar._set_desktop_session(_Istek(["access_token", "x"])))
    assert y.status_code == 422 and ceviri.t("oturum.hata.accessTokenGerekli") in _govde(y)


def test_eslestirme_cozulemeyen_govde_403_ve_dogru_kodda_sir_hatasi_500(monkeypatch, temiz_kovalar):
    _sirlar(monkeypatch, {"pairing_code": "ABC123"})
    y = asyncio.run(ar._exchange_code_for_token(_Istek(json_hatasi=ValueError("bozuk json"), host="10.0.0.9")))
    assert y.status_code == 403
    kova = ar._exchange_throttle["10.0.0.9"]
    assert kova["fails"] == 1, "çözülemeyen gövde deneme sayılmadı"

    def _patla():
        raise OSError("sır deposu kilitli")

    monkeypatch.setattr(auth, "get_api_token", _patla)
    y = asyncio.run(ar._exchange_code_for_token(_Istek({"code": "abc123"}, host="10.0.0.9")))
    assert y.status_code == 500 and ceviri.t("oturum.hata.tokenAlinamadi") in _govde(y)
    assert kova["fails"] == 0, "doğru kod sonrası sayaç sıfırlanmadı"


@pytest.mark.parametrize(
    "kova_adi,fn",
    [
        ("_login_throttle", ar._login_bucket),
        ("_reset_throttle_by_ip", ar._reset_bucket),
        ("_exchange_throttle", ar._exchange_bucket),
    ],
)
def test_kisitlama_kovasi_1000_asinca_yalniz_suresi_dolanlar_atilir(monkeypatch, kova_adi, fn):
    monkeypatch.setattr(ar, "_time", types.SimpleNamespace(time=lambda: 1000.0))
    kova = {f"dolmus{i}": {"fails": 0, "until": 999.0} for i in range(600)}
    kova.update({f"etkin{i}": {"fails": 3, "until": 2000.0} for i in range(401)})
    monkeypatch.setattr(ar, kova_adi, kova)
    yeni = fn("yeni-anahtar")
    assert yeni == {"fails": 0, "until": 0.0}
    assert not any(k.startswith("dolmus") for k in kova), "süresi dolmuş kova atılmadı"
    assert sum(k.startswith("etkin") for k in kova) == 401, "ETKİN kilit temizlikte silindi"


def test_guvenli_karsilastirma_cevrilemeyen_girdide_false():
    class _Cevrilemez:
        def __str__(self):
            raise TypeError("dizgeye çevrilemez")

    assert ar._safe_compare(_Cevrilemez(), "kod") is False
    assert ar._safe_compare("kod", "kod") is True


def test_oturum_jetonu_sir_deposu_patlarsa_yedek_sirla_imzalanir(monkeypatch):
    _sirlar(monkeypatch, hata=OSError("kasa kilitli"))
    jeton = ar._issue_session_token("vet@klinik.test")
    eposta, zaman, imza = base64.urlsafe_b64decode(jeton).decode("utf-8").split("|")
    beklenen = hmac.new(b"pemf-fallback", f"{eposta}|{zaman}".encode(), hashlib.sha256).hexdigest()
    assert eposta == "vet@klinik.test" and imza == beklenen


def test_kayit_gecersiz_eposta_zayif_sifre_db_reddi(monkeypatch):
    db = _KimlikDb(kayit=(False, "Bu e-posta zaten kayıtlı"))
    monkeypatch.setattr(auth_db, "get_auth_db", lambda: db)
    K = ar._AuthCredentials
    assert asyncio.run(ar._register_user(K(email="eposta-degil", password="Parola123"))) == {
        "ok": False,
        "error": ceviri.t("kimlik.hata.gecersizEposta"),
    }
    assert asyncio.run(ar._register_user(K(email="vet@klinik.test", password="kisa"))) == {
        "ok": False,
        "error": ceviri.t("kimlik.hata.sifreKurali"),
    }
    assert asyncio.run(ar._register_user(K(email="vet@klinik.test", password="Parola123"))) == {
        "ok": False,
        "error": "Bu e-posta zaten kayıtlı",
    }


def test_giris_dogru_sifre_jeton_ve_sayac_sifir_yanlis_sifre_kodlari(monkeypatch, temiz_kovalar):
    _sirlar(monkeypatch, {"api_token": "cihaz-sirri"})
    db = _KimlikDb({"vet@klinik.test": "Parola123"})
    monkeypatch.setattr(auth_db, "get_auth_db", lambda: db)
    monkeypatch.setenv("PEMF_GENERIC_LOGIN_ERRORS", "0")
    K = ar._AuthCredentials
    y = asyncio.run(ar._login_user(K(email="Vet@Klinik.test ", password="Yanlis123")))
    assert y == {"ok": False, "code": "bad_password", "error": ceviri.t("kimlik.hata.sifreHatali")}
    assert ar._login_throttle["vet@klinik.test"]["fails"] == 1
    y = asyncio.run(ar._login_user(K(email="vet@klinik.test", password="Parola123")))
    assert y["ok"] is True and y["email"] == "vet@klinik.test" and y["token"]
    assert ar._login_throttle["vet@klinik.test"] == {"fails": 0, "until": 0.0}, "başarılı girişte sayaç sıfırlanmadı"
    monkeypatch.setenv("PEMF_GENERIC_LOGIN_ERRORS", "1")
    y = asyncio.run(ar._login_user(K(email="vet@klinik.test", password="Yanlis123")))
    assert y == {"ok": False, "code": "invalid", "error": ceviri.t("kimlik.hata.epostaSifreHatali")}


def test_jenerik_kipte_kayitsiz_eposta_sahte_dogrulama_patlasa_da_invalid(monkeypatch, temiz_kovalar):
    db = _KimlikDb(dogrulama_hatasi=RuntimeError("kullanıcı yok"))
    monkeypatch.setattr(auth_db, "get_auth_db", lambda: db)
    monkeypatch.setenv("PEMF_GENERIC_LOGIN_ERRORS", "1")
    y = asyncio.run(ar._login_user(ar._AuthCredentials(email="yok@klinik.test", password="Parola123")))
    assert y == {"ok": False, "code": "invalid", "error": ceviri.t("kimlik.hata.epostaSifreHatali")}
    assert db.dogrulanan == ["yok@klinik.test"], "zamanlama eşitleyici sahte doğrulama yapılmadı"


def test_sifirlama_break_glass_api_token_ve_sonraki_dogrulamalar(monkeypatch, temiz_kovalar):
    _sirlar(monkeypatch, {"admin_reset_code": "YONETICI-KODU", "api_token": "cihaz-api-jetonu"})
    db = _KimlikDb({"vet@klinik.test": "Eski12345"})
    monkeypatch.setattr(auth_db, "get_auth_db", lambda: db)
    P = ar._ResetPayload
    y = asyncio.run(
        ar._reset_password(P(email="eposta-degil", admin_code="cihaz-api-jetonu", new_password="Yeni12345"), _Istek())
    )
    assert y == {"ok": False, "error": ceviri.t("kimlik.hata.gecersizEposta")}, "break-glass api_token kabul edilmedi"
    y = asyncio.run(
        ar._reset_password(P(email="vet@klinik.test", admin_code="YONETICI-KODU", new_password="zayif"), _Istek())
    )
    assert y == {"ok": False, "error": ceviri.t("kimlik.hata.yeniSifreKurali")}
    y = asyncio.run(
        ar._reset_password(
            P(email="vet@klinik.test", admin_code="cihaz-api-jetonu", new_password="Yeni12345"), _Istek()
        )
    )
    assert y == {"ok": True} and db.k["vet@klinik.test"] == "Yeni12345"


def test_sifirlama_kuresel_arka_durak_esiginde_kilit_kurulur(monkeypatch, temiz_kovalar):
    _sirlar(monkeypatch, {"admin_reset_code": "YONETICI-KODU"})
    monkeypatch.setattr(ar, "_time", types.SimpleNamespace(time=lambda: 5000.0))
    ar._reset_throttle["fails"] = ar._RESET_GLOBAL_MAX_FAILS - 1
    y = asyncio.run(
        ar._reset_password(
            ar._ResetPayload(email="vet@klinik.test", admin_code="yanlis", new_password="Yeni12345"), _Istek()
        )
    )
    assert y == {"ok": False, "error": ceviri.t("kimlik.hata.yoneticiKodu")}
    assert ar._reset_throttle == {"fails": 0, "until": 5000.0 + ar._THROTTLE_LOCK_SEC}


def test_yonetici_kodu_ucu_kodu_dondurur(monkeypatch):
    _sirlar(monkeypatch, {"admin_reset_code": "  KOD-42  "})
    assert asyncio.run(ar._get_admin_code()) == {"code": "KOD-42"}
    assert json.dumps(asyncio.run(ar._get_admin_code()))
