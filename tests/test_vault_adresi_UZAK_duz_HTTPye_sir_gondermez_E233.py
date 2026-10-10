# -*- coding: utf-8 -*-
"""E2-3.3 (2-E incelemesi A3) — `PEMF_VAULT_ADRES` uzak bir ana makineyi DÜZ HTTP ile gösterirse betik kök token'ı ve hasta
anahtarlarını oraya GÖNDERMEZ.

D2.E05 sabit `http://127.0.0.1:8200` adresini `PEMF_VAULT_ADRES` ile değiştirilebilir yaptı (sınama / farklı port için); değer
hiç denetlenmiyor. Ölçüldü: `PEMF_VAULT_ADRES=http://192.0.2.10:8201` ile `--yaz` → TEK istek, `X-Vault-Token` = KÖK token,
gövdede `auto.sqlcipher_key` + `auto.patient_fernet_key` DÜZ METİN, şema http, ana makine uzak. `--kur` beş isteği aynı token'la
oraya yollar. Vault yalnız bu makinedeki konteynerdir (`docker/docker-compose.vault.yml`, 127.0.0.1:8200); uzak Vault
gerekiyorsa TLS (https) şarttır.

Kapı: betiğin KENDİ `main()`i (süreç içi), sentetik sır kökü (tmp_path), HTTP isteği EN ALT katta (`http.client.HTTPConnection
.request`) KAYDEDİLİP reddedilir — ağa ÇIKILMAZ (TEST-NET adresi 192.0.2.10 zaten yönlendirilmez; ayrıca bekçi engeller).
Değerler sentetik; yazdırılmaz.
"""

from __future__ import annotations

import http.client
import json
import sys

import pytest
from betik_alt_sureci import betik_modulu
from sahte_vault_sunucusu import SahteVault

KOK = "kok-sahte-e233"
SQL = "sql-sahte-e233"
FER = "fernet-sahte-e233"


@pytest.fixture()
def ve(tmp_path, monkeypatch):
    for ad in ("PROGRAMDATA", "APPDATA"):
        (tmp_path / ad.lower()).mkdir()
        monkeypatch.setenv(ad, str(tmp_path / ad.lower()))
    veri = tmp_path / "veri"
    (veri / "PEMF_GUI").mkdir(parents=True)
    (veri / "PEMF_GUI" / "pemf_secrets.json").write_text(
        json.dumps({"auto": {"sqlcipher_key": SQL, "patient_fernet_key": FER}}), encoding="utf-8"
    )
    monkeypatch.setenv("PEMF_DATA_DIR", str(veri))
    m = betik_modulu("vault_emanet")
    dosya = tmp_path / "pemf-vault-kurtarma.json"
    dosya.write_text(json.dumps({"root_token": KOK, "keys_base64": ["sahte"]}), encoding="utf-8")
    monkeypatch.setattr(m, "KURTARMA_DOSYASI", dosya)
    return m


@pytest.fixture()
def kayit(monkeypatch):
    """En alt kat: HTTP isteği kaydedilir (ana makine, şema, kök token başlıkta mı, sır gövdede mi) ve REDDEDİLİR."""
    istekler: list[dict] = []

    def _kaydet(self, method, url, body=None, headers={}, **k):  # noqa: B006
        b = body if isinstance(body, bytes) else (str(body).encode() if body else b"")
        hb = {str(a).lower(): str(c) for a, c in dict(headers).items()}
        istekler.append(
            {
                "host": self.host,
                "sema": "https" if isinstance(self, http.client.HTTPSConnection) else "http",
                "kok_token": hb.get("x-vault-token") == KOK,
                "sir_govdede": SQL.encode() in b or FER.encode() in b,
            }
        )
        raise ConnectionRefusedError("kapı: ağa çıkılmaz (en alt kat kaydedici)")

    monkeypatch.setattr(http.client.HTTPConnection, "request", _kaydet)
    return istekler


def _kos(m, monkeypatch, capsys, adres, *arg):
    monkeypatch.setattr(m, "ADRES", adres)
    monkeypatch.setattr(sys, "argv", ["vault_emanet.py", *arg])
    try:
        rc = m.main()
    except SystemExit as e:
        rc = e.code if isinstance(e.code, int) else 1
    c = capsys.readouterr()
    return rc, c.out + c.err


@pytest.mark.parametrize("arg", [["--yaz"], ["--kur"], ["--durum"]], ids=["yaz", "kur", "durum"])
@pytest.mark.parametrize("adres", ["http://192.0.2.10:8201", "http://vault.klinik.lan:8200"], ids=["ip", "ad"])
def test_KRITIK_UZAK_duz_HTTP_adrese_KOK_token_ve_SIR_gitmez_E233(ve, kayit, monkeypatch, capsys, arg, adres):
    rc, cikti = _kos(ve, monkeypatch, capsys, adres, *arg)
    sizan = [i for i in kayit if i["sema"] == "http" and (i["kok_token"] or i["sir_govdede"])]
    assert not sizan, f"{arg} kök token / hasta anahtarını DÜZ HTTP ile uzak ana makineye ({adres}) gönderdi: {sizan}"
    assert rc != 0, cikti


def test_KARSIT_UZAK_https_adrese_istek_GIDER_E233(ve, kayit, monkeypatch, capsys):
    _kos(ve, monkeypatch, capsys, "https://192.0.2.10:8201", "--yaz")
    assert kayit and kayit[0]["sema"] == "https", f"TLS'li uzak Vault reddedilmemeli: {kayit}"


@pytest.mark.parametrize("ana", ["127.0.0.1", "localhost"])
def test_KARSIT_YEREL_duz_HTTP_calisir_E233(ve, monkeypatch, capsys, ana):
    with SahteVault(kok=KOK, kurtarma="kurtarma-sahte-e233") as v:
        rc, cikti = _kos(ve, monkeypatch, capsys, v.adres.replace("127.0.0.1", ana), "--yaz")
        assert rc == 0, cikti
        assert v.emanet.get("auto.sqlcipher_key") == SQL
