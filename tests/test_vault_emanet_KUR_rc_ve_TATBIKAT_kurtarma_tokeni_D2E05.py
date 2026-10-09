# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D2.E05 (İG-9.86 · Y86 · A-84) — `scripts/vault_emanet.py`: `--kur` hata dönüş kodu; `--tatbikat` KURTARMA token'ıyla; varsayılan
kira süresi kısa, kurtarma token'ı açık 10 yıl + yenileme adımı.

İG-9.86 (ölçüldü): `--kur` adım hatalarını yalnız basıp HER durumda 0 dönüyordu (Vault kapalı / her istek 403 → rc 0);
`--tatbikat` `--token`ı yok sayıp KÖK token'la koşuyordu — kurtarma token'ı İPTAL edilmiş olsa bile "TATBIKAT BASARILI".
Y86 (sahip kararı): tatbikat KURTARMA token'ıyla koşar; token işe yaramıyorsa BAŞARISIZ der. A-84 (sahip kararı): Vault'un
varsayılan kira süresi (10 yıl) kısaltılır; emanet betiğinin token yenileme adımıyla birlikte.

Kapı: betiğin KENDİ `main()`i (süreç içi; `betik_modulu`), Vault yerine loopback rastgele portta SAHTE Vault (yalnız betiğin
yolları; her isteğin token SINIFI kaydedilir — kök / kurtarma / iptal), sentetik veri kökü (klon TEMP'i; gerçek kökler
okunmaz) ve sentetik anahtarlı GERÇEK SQLCipher veritabanları. Gerçek `~/pemf-vault-kurtarma.json` okunmaz.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest
from betik_alt_sureci import betik_modulu
from cryptography.fernet import Fernet
from sahte_vault_sunucusu import SahteVault, sentetik_veri_koku, sqlcipher_mod

KOK_DIZIN = Path(__file__).resolve().parents[1]
KOK = "kok-sahte-d2e05"
KURTARMA = "kurtarma-sahte-d2e05"
IPTAL = "iptal-sahte-d2e05"
SQL_ANAHTARI = "d2e05-sql-anahtari"
ON_YIL_SN = 10 * 365 * 24 * 3600


def _sqlcipher():
    return sqlcipher_mod()


@pytest.fixture()
def ortam(tmp_path, monkeypatch):
    """Sentetik kökler (PROGRAMDATA / APPDATA / PEMF_DATA_DIR klon TEMP'inde) + sentetik Vault kurtarma dosyası."""
    for ad in ("PROGRAMDATA", "APPDATA"):
        (tmp_path / ad.lower()).mkdir()
        monkeypatch.setenv(ad, str(tmp_path / ad.lower()))
    monkeypatch.setenv("PEMF_DATA_DIR", str(tmp_path / "veri"))
    ve = betik_modulu("vault_emanet")
    dosya = tmp_path / "pemf-vault-kurtarma.json"
    dosya.write_text(json.dumps({"root_token": KOK, "keys_base64": ["sahte"]}), encoding="utf-8")
    monkeypatch.setattr(ve, "KURTARMA_DOSYASI", dosya)
    return ve, tmp_path


def _kos(ve, monkeypatch, capsys, adres: str, *arg: str) -> tuple[int, str]:
    monkeypatch.setattr(ve, "ADRES", adres)
    monkeypatch.setattr(ve, "_KURTARMA_TOKENI", None, raising=False)
    monkeypatch.setattr(sys, "argv", ["vault_emanet.py", *arg])
    try:
        rc = ve.main()
        mesaj = ""
    except SystemExit as e:
        rc = e.code if isinstance(e.code, int) else 1
        mesaj = "" if isinstance(e.code, int) or e.code is None else str(e.code)
    c = capsys.readouterr()
    return rc, c.out + c.err + mesaj


def _vault(**k) -> SahteVault:
    emanet = {"auto.sqlcipher_key": SQL_ANAHTARI, "auto.patient_fernet_key": Fernet.generate_key().decode()}
    return SahteVault(kok=KOK, kurtarma=KURTARMA, iptal=IPTAL, emanet=emanet, **k)


# ── --kur: adım hatası → sıfır olmayan çıkış ─────────────────────────────────────────────────────────────────────────


def test_KRITIK_kur_HER_istege_403_iken_cikis_kodu_SIFIR_DEGIL_D2E05(ortam, monkeypatch, capsys):
    ve, _ = ortam
    with _vault() as v:
        v.kip = "hepsi_403"
        rc, cikti = _kos(ve, monkeypatch, capsys, v.adres, "--kur")
    assert "HATA 403" in cikti, f"aparat: adım hatası basılmadı: {cikti[-400:]}"
    assert rc != 0, f"--kur üç adımı da düştü ama çıkış kodu {rc} — otomasyon kurulumu tamam sanır"


def test_KRITIK_kur_VAULT_KAPALIYKEN_cikis_kodu_SIFIR_DEGIL_D2E05(ortam, monkeypatch, capsys):
    ve, _ = ortam
    with _vault() as v:
        kapali = v.adres  # sunucu kapanınca port kapalı (bağlantı reddedilir)
    rc, cikti = _kos(ve, monkeypatch, capsys, kapali, "--kur")
    assert "HATA 0" in cikti, f"aparat: bağlantı hatası basılmadı: {cikti[-400:]}"
    assert rc != 0, f"Vault kapalıyken --kur çıkış kodu {rc}"


def test_KARSIT_kur_saglam_Vaultta_0_doner_ve_UC_adimi_KOK_tokenla_kurar_D2E05(ortam, monkeypatch, capsys):
    ve, _ = ortam
    with _vault() as v:
        rc, cikti = _kos(ve, monkeypatch, capsys, v.adres, "--kur")
    assert rc == 0, cikti[-600:]
    assert "pemf/" in v.mountlar and "file/" in v.denetim and "pemf-kurtarma" in v.politikalar
    assert set(v.siniflar()) == {"kok"}, v.istekler


# ── --tatbikat: KURTARMA token'ıyla (Y86) ────────────────────────────────────────────────────────────────────────────


def test_KRITIK_tatbikat_IPTAL_kurtarma_tokeniyla_BASARISIZ_kok_token_KULLANILMAZ_D2E05(ortam, monkeypatch, capsys):
    ve, _ = ortam
    with _vault(kurtarma_ttl=ON_YIL_SN) as v:
        rc, cikti = _kos(ve, monkeypatch, capsys, v.adres, "--tatbikat", "--token", IPTAL)
    assert "TATBIKAT BASARILI" not in cikti, (
        f"İPTAL edilmiş kurtarma token'ıyla tatbikat 'BASARILI' dedi: {cikti[-500:]}"
    )
    assert rc != 0
    assert "iptal" in v.siniflar(), f"tatbikat verilen kurtarma token'ını HİÇ kullanmadı: {v.istekler}"
    assert "kok" not in v.siniflar(), f"tatbikat KÖK token'la koştu (Y86): {v.istekler}"


def test_KRITIK_tatbikat_TOKENSIZ_SINANMADI_der_kok_tokenla_KOSMAZ_D2E05(ortam, monkeypatch, capsys):
    ve, _ = ortam
    with _vault(kurtarma_ttl=ON_YIL_SN) as v:
        rc, cikti = _kos(ve, monkeypatch, capsys, v.adres, "--tatbikat")
    assert "TATBIKAT BASARILI" not in cikti and "SINANMADI" in cikti, cikti[-500:]
    assert rc != 0
    assert v.siniflar() == [], f"token verilmeden Vault'a istek gitti (kök token?): {v.istekler}"


def test_KRITIK_tatbikat_KOK_token_verilirse_kurtarma_tokeni_SINANMADI_der_D2E05(ortam, monkeypatch, capsys):
    ve, _ = ortam
    with _vault(kurtarma_ttl=ON_YIL_SN) as v:
        rc, cikti = _kos(ve, monkeypatch, capsys, v.adres, "--tatbikat", "--token", KOK)
    assert "TATBIKAT BASARILI" not in cikti and "SINANMADI" in cikti, cikti[-500:]
    assert rc != 0
    assert not v.siniflar("/v1/pemf/data/"), f"kök token'la emanet okundu: {v.istekler}"


@pytest.mark.skipif(_sqlcipher() is None, reason="sqlcipher3 yok — tatbikat zinciri ölçülemez")
def test_KARSIT_tatbikat_GECERLI_kurtarma_tokeniyla_BASARILI_anahtar_BASILMAZ_D2E05(ortam, monkeypatch, capsys):
    ve, tmp = ortam
    sentetik_veri_koku(tmp / "veri", SQL_ANAHTARI, Fernet.generate_key().decode())
    with _vault(kurtarma_ttl=ON_YIL_SN) as v:
        rc, cikti = _kos(ve, monkeypatch, capsys, v.adres, "--tatbikat", "--token", KURTARMA)
    assert rc == 0 and "TATBIKAT BASARILI" in cikti, cikti[-800:]
    assert v.siniflar("/v1/pemf/data/") == ["kurtarma"] and "kok" not in v.siniflar(), v.istekler
    assert SQL_ANAHTARI not in cikti and KURTARMA not in cikti, "tatbikat çıktısı sırrı / token'ı BASTI"
    assert "YENILEYIN" not in cikti, "10 yıllık token için yenileme uyarısı (yanlış alarm)"


# ── A-84: kısa varsayılan kira + kurtarma token'ı açık 10 yıl + yenileme adımı ────────────────────────────────────────


@pytest.mark.skipif(_sqlcipher() is None, reason="sqlcipher3 yok — tatbikat zinciri ölçülemez")
def test_KRITIK_A84_kurtarma_tokeninin_OMRU_AZALINCA_tatbikat_YENILEMEYI_soyler_D2E05(ortam, monkeypatch, capsys):
    ve, tmp = ortam
    sentetik_veri_koku(tmp / "veri", SQL_ANAHTARI, Fernet.generate_key().decode())
    with _vault(kurtarma_ttl=100 * 24 * 3600) as v:
        rc, cikti = _kos(ve, monkeypatch, capsys, v.adres, "--tatbikat", "--token", KURTARMA)
    assert rc == 0 and "TATBIKAT BASARILI" in cikti, cikti[-800:]
    assert "YENILEYIN" in cikti and "--token-uret" in cikti, (
        f"100 gün kalan kurtarma token'ı için yenileme yok: {cikti[-600:]}"
    )


def _saat(deger: str) -> float:
    m = re.fullmatch(r"(\d+)([hms])", deger)
    assert m, f"aparat: süre biçimi tanınmadı: {deger}"
    return int(m.group(1)) * {"h": 1, "m": 1 / 60, "s": 1 / 3600}[m.group(2)]


def test_KRITIK_A84_varsayilan_kira_KISA_kurtarma_tokeni_ACIK_10_yil_uretilir_D2E05(ortam, monkeypatch, capsys):
    hcl = (KOK_DIZIN / "docker" / "vault" / "config" / "vault.hcl").read_text(encoding="utf-8")
    deger = {k: v for k, v in re.findall(r'^\s*(default_lease_ttl|max_lease_ttl)\s*=\s*"([^"]+)"', hcl, re.M)}
    assert _saat(deger["default_lease_ttl"]) <= 768, f"varsayılan kira süresi KISALTILMADI (A-84): {deger}"
    assert _saat(deger["max_lease_ttl"]) >= 87600, f"üst sınır 10 yılın altında — kurtarma token'ı üretilemez: {deger}"
    ve, _ = ortam
    with _vault() as v:
        rc, _cikti = _kos(ve, monkeypatch, capsys, v.adres, "--token-uret")
    assert rc == 0 and v.uretilen, "kurtarma token'ı üretilmedi"
    assert v.uretilen[0].get("ttl") == "87600h" and v.uretilen[0].get("policies") == ["pemf-kurtarma"], v.uretilen
