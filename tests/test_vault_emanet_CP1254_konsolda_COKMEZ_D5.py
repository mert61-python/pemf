# -*- coding: utf-8 -*-
"""D0Ö §6.4 madde 1 (DALGA-1 §7 → D5; C10 `hasta_anahtari_emanet`in ikizi): `vault_emanet.py` cp1254 (Türkçe Windows konsolu, gömülü
Python'un varsayılanı) çıktıda ÇÖKÜYORDU — `--tatbikat`ın "✓ reddedildi" / "⛔ YANLIS ANAHTARLA ACILDI" ve `--dogrula`nın "✓ … guncel" /
"⚠️ …" satırları cp1254'te kodlanamaz → `UnicodeEncodeError`, kurtarma tatbikatı SONUÇ satırından önce Traceback ile düşer (ölçüldü D5:
9 `print` çağrısı). Akış GERÇEK katı cp1254 `TextIOWrapper` — capsys'in UTF-8 akışı bu hatayı GİZLER. Aparat D2.E05 / D5.25 ile aynı:
betiğin kendi `main()`i, rastgele loopback portunda sahte Vault, sentetik veri kökü + gerçek SQLCipher DB."""

from __future__ import annotations

import io
import sys

import pytest
from cryptography.fernet import Fernet
from sahte_vault_sunucusu import sentetik_veri_koku
from test_vault_emanet_KUR_rc_ve_TATBIKAT_kurtarma_tokeni_D2E05 import (  # noqa: F401  (fikstür)
    KURTARMA,
    ON_YIL_SN,
    SQL_ANAHTARI,
    _sqlcipher,
    _vault,
    ortam,
)

pytestmark = pytest.mark.skipif(_sqlcipher() is None, reason="sqlcipher3 yok — tatbikat zinciri ölçülemez")


def _cp1254_kos(ve, monkeypatch, adres: str, *arg: str) -> tuple[int, str]:
    # stdout ve stderr AYRI akışlar: tek nesne olsaydı birini ayarlamak ötekini de ayarlardı (ölçüldü — "yalnız stderr" mutantı yaşadı).
    tampon = io.BytesIO()
    akis = io.TextIOWrapper(tampon, encoding="cp1254", errors="strict", write_through=True)
    hata_akisi = io.TextIOWrapper(io.BytesIO(), encoding="cp1254", errors="strict", write_through=True)
    monkeypatch.setattr(sys, "stdout", akis)
    monkeypatch.setattr(sys, "stderr", hata_akisi)
    monkeypatch.setattr(ve, "ADRES", adres)
    monkeypatch.setattr(ve, "_KURTARMA_TOKENI", None, raising=False)
    monkeypatch.setattr(sys, "argv", ["vault_emanet.py", *arg])
    try:
        rc = ve.main()
    except SystemExit as e:
        rc = e.code if isinstance(e.code, int) else 1
    except UnicodeEncodeError as e:
        akis.flush()
        pytest.fail(
            f"cp1254 konsolda ÇÖKTÜ ({e!r}) — son çıktı:\n{tampon.getvalue().decode('cp1254', 'replace')[-600:]}"
        )
    akis.flush()
    return rc, tampon.getvalue().decode("cp1254")


def test_KRITIK_tatbikat_cp1254_konsolda_COKMEZ_ve_SONUC_soyler(ortam, monkeypatch):
    ve, tmp = ortam
    sentetik_veri_koku(tmp / "veri", SQL_ANAHTARI, Fernet.generate_key().decode())
    with _vault(kurtarma_ttl=ON_YIL_SN) as v:
        rc, cikti = _cp1254_kos(ve, monkeypatch, v.adres, "--tatbikat", "--token", KURTARMA)
    assert "reddedildi" in cikti, f"aparat: yanlış anahtar kolu (✓ satırı) koşmadı:\n{cikti[-600:]}"
    assert rc == 0 and "TATBIKAT BASARILI" in cikti, f"rc={rc}\n{cikti[-600:]}"


def test_KRITIK_dogrula_cp1254_konsolda_COKMEZ(ortam, monkeypatch):
    ve, tmp = ortam
    sentetik_veri_koku(tmp / "veri", SQL_ANAHTARI, Fernet.generate_key().decode())
    with _vault(kurtarma_ttl=ON_YIL_SN) as v:
        _rc, cikti = _cp1254_kos(ve, monkeypatch, v.adres, "--dogrula")
    assert "auto.sqlcipher_key" in cikti, f"aparat: doğrulama alan satırlarını basmadı:\n{cikti[-600:]}"
