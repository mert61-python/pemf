# -*- coding: utf-8 -*-
"""KP-1 · `servers/auth.py` · sözleşmeler (güvenlik — FAIL-CLOSED): API token kaynağı sırası ortam → sır deposu → eski dosya → ÜRET (dosyaya
yazılır ve kilitlenir); sır deposu / kilit / dosya hatası açılışı durdurmaz, token BOŞ kalmaz · token dosyası kökü çözücü düşerse
PEMF_DATA_DIR → APPDATA (win32) / Library (darwin) / ~/.local/share (diğer) · güvenilir ağ / proxy listesinde geçersiz değer yok sayılır ·
"localhost" bağlaması loopback'tir, çözülemeyen host değildir · istek nesnesi bozuksa token / operatör jetonu BOŞ, ayrıcalık ve
"cihazın kendisi" denetimi REDDEDER · kimlik DB'si okunamazsa arıza görünür (okunamıyor = True, yol "?"), operatör çözümlemesi SAHİPSİZ.

Ağ / gerçek kasa / gerçek veri kökü YOK: sır deposu (`utils.secrets_manager.get_secret`), ACL (`utils.file_acl`), kimlik DB'si
(`database.auth_db.get_auth_db`) ve istek nesnesi EN ALT katta sahte; modül önbellekleri her testte geri konur.
"""

from __future__ import annotations

import ipaddress
import logging
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import utils.file_acl as fa
import utils.secrets_manager as sm
from servers import auth


@pytest.fixture
def temiz(monkeypatch, tmp_path):
    for ad in ("_token", "_TRUSTED_NETS", "_TRUSTED_PROXIES", "_LOOPBACK_BIND"):
        monkeypatch.setattr(auth, ad, None)
    for ad in ("PEMF_API_TOKEN", "PEMF_TRUSTED_PROXIES", "PEMF_API_HOST"):
        monkeypatch.delenv(ad, raising=False)
    monkeypatch.setenv("PEMF_DATA_DIR", str(tmp_path / "veri"))
    kilit: list = []
    monkeypatch.setattr(fa, "lock_down_file", lambda p, **k: kilit.append(Path(p)) or True)
    return kilit


def _kok_cozulemez(monkeypatch):
    import utils.path_utils as pu

    monkeypatch.setattr(pu, "get_app_data_directory", lambda: (_ for _ in ()).throw(RuntimeError("kök yok")))


def test_token_dosyasi_koku_cozucu_DUSERSE_platforma_gore(temiz, monkeypatch, tmp_path):
    _kok_cozulemez(monkeypatch)
    assert auth._token_file() == tmp_path / "veri" / "PEMF_GUI" / "api_token.txt"
    monkeypatch.delenv("PEMF_DATA_DIR")
    monkeypatch.setenv("APPDATA", str(tmp_path / "ad"))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "ev"))
    monkeypatch.setattr(sys, "platform", "win32")
    assert auth._token_file() == tmp_path / "ad" / "PEMF_GUI" / "api_token.txt"
    monkeypatch.setattr(sys, "platform", "darwin")
    assert auth._token_file() == tmp_path / "ev" / "Library" / "Application Support" / "PEMF_GUI" / "api_token.txt"
    monkeypatch.setattr(sys, "platform", "linux")
    assert auth._token_file() == tmp_path / "ev" / ".local" / "share" / "PEMF_GUI" / "api_token.txt"


def test_token_dizini_OLUSTURULAMAZSA_yol_yine_doner(temiz, monkeypatch, tmp_path):
    _kok_cozulemez(monkeypatch)
    (tmp_path / "dosya").write_text("x", encoding="utf-8")
    monkeypatch.setenv("PEMF_DATA_DIR", str(tmp_path / "dosya"))  # kök bir DOSYA → mkdir düşer
    assert auth._token_file() == tmp_path / "dosya" / "PEMF_GUI" / "api_token.txt"


def test_KRITIK_sir_deposu_DUSERSE_eski_dosyaya_duser_YOKSA_uretir_yazar_KILITLER(temiz, monkeypatch, caplog):
    monkeypatch.setattr(sm, "get_secret", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("sır dosyası bozuk")))
    with caplog.at_level(logging.ERROR, logger=auth.logger.name):
        t = auth.get_api_token()
    assert len(t) >= 24 and auth._token_file().read_text(encoding="utf-8") == t, (
        "üretilen token kalıcılaşmadı (istemciler kopar)"
    )
    assert auth._token_file() in temiz, "düz-metin token dosyası kilitlenmedi"
    assert any("SecretsManager api_token okunamadı" in r.getMessage() for r in caplog.records)
    assert auth.get_api_token() == t, "token önbelleği yok (her çağrıda değişir)"
    auth._token = None
    assert auth.get_api_token() == t, "var olan token dosyası yeniden okunmadı"


def test_ortam_tokeni_ONCE_gelir(temiz, monkeypatch):
    monkeypatch.setattr(sm, "get_secret", lambda *a, **k: "depo-tokeni")
    monkeypatch.setenv("PEMF_API_TOKEN", " sabit-dagitim-tokeni ")
    assert auth.get_api_token() == "sabit-dagitim-tokeni"


def test_token_kilidi_ya_da_dosyasi_DUSERSE_token_yine_BOS_DEGIL(temiz, monkeypatch):
    monkeypatch.setattr(sm, "get_secret", lambda *a, **k: "")
    monkeypatch.setattr(fa, "lock_down_file", lambda *a, **k: (_ for _ in ()).throw(OSError("icacls yok")))
    t1 = auth.get_api_token()
    assert t1 and auth._token_file().read_text(encoding="utf-8") == t1
    auth._token = None
    _kok_cozulemez(monkeypatch)
    import tempfile

    monkeypatch.setenv("PEMF_DATA_DIR", tempfile.mkdtemp(prefix="kp_"))
    monkeypatch.setattr(Path, "write_text", lambda *a, **k: (_ for _ in ()).throw(PermissionError("salt okunur")))
    assert auth.get_api_token(), "dosya yazılamayınca token BOŞ kaldı (check_token herkesi reddeder / açar)"


def test_gecersiz_guvenilir_ag_ve_proxy_degerleri_YOK_SAYILIR(temiz, monkeypatch, caplog):
    gercek = ipaddress.ip_network
    monkeypatch.setattr(
        ipaddress,
        "ip_network",
        lambda c, *a, **k: (_ for _ in ()).throw(ValueError("x")) if c == "fc00::/7" else gercek(c, *a, **k),
    )
    aglar = auth._trusted_nets()
    assert gercek("192.168.0.0/16") in aglar and len(aglar) == 6 and gercek("fc00::/7") not in aglar
    monkeypatch.setenv("PEMF_TRUSTED_PROXIES", "10.1.2.3, bozuk-deger ,,172.18.0.0/16")
    with caplog.at_level(logging.WARNING, logger=auth.logger.name):
        proxyler = auth._trusted_proxies()
    assert [str(p) for p in proxyler] == ["10.1.2.3/32", "172.18.0.0/16"]
    assert any("bozuk-deger" in r.getMessage() for r in caplog.records)


@pytest.mark.parametrize("host,beklenen", [("localhost", True), ("[::1]", True), ("pemf-cihaz.local", False)])
def test_yalniz_loopback_baglamasi_localhost_EVET_cozulemeyen_ad_HAYIR(temiz, monkeypatch, host, beklenen):
    monkeypatch.setenv("PEMF_API_HOST", host)
    assert auth._loopback_only_bind() is beklenen


class _BozukIstek:
    @property
    def headers(self):
        raise RuntimeError("istek ayrıştırılamadı")

    client = SimpleNamespace(host="10.0.0.5")
    query_params = {}


def test_KRITIK_bozuk_istekte_token_ve_operator_BOS_ayricalik_REDDEDILIR(temiz, caplog):
    r = _BozukIstek()
    assert auth._istek_tokeni(r) == "" and auth._operator_jetonu(r) == ""
    with caplog.at_level(logging.ERROR, logger=auth.logger.name):
        assert auth.is_privileged_request(r) is False
        assert auth.cihazin_kendisinden_mi(r) is False
    mesajlar = " ".join(r.getMessage() for r in caplog.records)
    assert "ayricalikli istek denetimi hatasi" in mesajlar and "cihaz-kendisi denetimi hatasi" in mesajlar


def test_KRITIK_kimlik_DB_okunamazsa_ariza_GORUNUR_operator_SAHIPSIZ(temiz, monkeypatch):
    import database.auth_db as adb

    monkeypatch.setattr(adb, "_auth_db", None)
    assert auth._kimlik_db_yolu() == "?"
    monkeypatch.setattr(adb, "get_auth_db", lambda: (_ for _ in ()).throw(OSError("auth_users.db kilitli")))
    assert auth.kimlik_db_okunamiyor() is True
    assert auth.kimliksiz_detayi("Operatör seçin") == auth.kimlik_db_okunamiyor_metni()
    assert auth._kayitli_operator_mu("dr@ornek.vet") is True, "kimlik DB'si okunamazken kanıtsız beyan kabul edildi"
    monkeypatch.setattr(adb, "_auth_db", SimpleNamespace())  # db_path yok → öznitelik hatası
    assert auth._kimlik_db_yolu() == "?"


def test_operator_cozumleme_PATLARSA_kayit_SAHIPSIZ_bos_eposta_kayitli_DEGIL(temiz, caplog):
    class _KapsamiBozuk:
        @property
        def scope(self):
            raise RuntimeError("ASGI kapsamı bozuk")

    with caplog.at_level(logging.ERROR, logger=auth.logger.name):
        assert auth.cozumlenmis_operator(_KapsamiBozuk(), "dr@ornek.vet") == ""
    assert any("operator cozumleme hatasi" in r.getMessage() for r in caplog.records)
    assert auth._kayitli_operator_mu("  ") is False
