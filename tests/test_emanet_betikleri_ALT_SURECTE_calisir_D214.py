# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D2.14 (B-3.42) — emanet betikleri (`hasta_anahtari_emanet.py`, `vault_emanet.py`) depo kökünden ALT SÜREÇTE koşar.

F4 taşımasından (283c419) sonra `apps/backend` kökte değildi; sır okuyan alt komutlar `ModuleNotFoundError` veriyordu — emanet
fark edilmeden eskiyor, tatbikat hiç koşamıyordu. Düzeltme `a7a2b48` (D0Ö.19) ile geldi (kök İŞARET dosyasıyla bulunur,
`apps/backend` sys.path'e eklenir); bu dosya planın kapısını GERÇEK yorumlayıcıda kurar — süreç içi koşu (conftest yolları)
kusuru MASKELER.

Ortam: `betik_alt_sureci.yalitik_ortam` (kullanıcı/makine kökleri klon TEMP'inde, null kasa, PEMF_* yok) + sentetik veri kökü
(`PEMF_DATA_DIR`); Vault yerine loopback rastgele portta SAHTE Vault (`PEMF_VAULT_ADRES`, D2.E05). Gerçek kökler okunmaz.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from betik_alt_sureci import kostur, yalitik_ortam
from cryptography.fernet import Fernet
from sahte_vault_sunucusu import SahteVault, sentetik_veri_koku, sqlcipher_mod

DEPO = Path(__file__).resolve().parents[1]
KOK = "kok-sahte-d214"
KURTARMA = "kurtarma-sahte-d214"
SQL_ANAHTARI = "d214-sql-anahtari"
ON_YIL_SN = 10 * 365 * 24 * 3600


def _sqlcipher():
    return sqlcipher_mod()


def _ortam(tmp_path: Path) -> dict:
    env = yalitik_ortam(tmp_path / "ev")
    env["PEMF_DATA_DIR"] = str(tmp_path / "veri")
    return env


def _iz_yok(p) -> None:
    metin = p.stdout + p.stderr
    assert "Traceback" not in metin and "ModuleNotFoundError" not in metin, f"alt süreç ÇÖKTÜ:\n{metin[-1500:]}"


def test_KRITIK_hasta_anahtari_emanet_PARMAK_IZI_alt_surecte_CALISIR_deger_BASMAZ_D214(tmp_path):
    fernet = Fernet.generate_key().decode()
    veri = tmp_path / "veri" / "PEMF_GUI"
    veri.mkdir(parents=True)
    (veri / "pemf_secrets.json").write_text(
        '{"auto": {"sqlcipher_key": "%s", "patient_fernet_key": "%s"}}' % (SQL_ANAHTARI, fernet), encoding="utf-8"
    )
    p = kostur([str(DEPO / "scripts" / "hasta_anahtari_emanet.py"), "--parmak-izi"], cwd=DEPO, env=_ortam(tmp_path))
    _iz_yok(p)
    assert p.returncode == 0, f"rc={p.returncode}\n{p.stdout[-800:]}{p.stderr[-800:]}"
    assert p.stdout.count("parmak=") == 2, f"iki anahtarın parmak izi basılmadı:\n{p.stdout[-800:]}"
    assert SQL_ANAHTARI not in p.stdout + p.stderr and fernet not in p.stdout + p.stderr, "anahtar DEĞERİ basıldı"


@pytest.mark.skipif(_sqlcipher() is None, reason="sqlcipher3 yok — tatbikat zinciri ölçülemez")
def test_KRITIK_vault_emanet_TATBIKAT_alt_surecte_ZINCIRI_kosar_D214(tmp_path):
    """`tatbikat`ın `database` içe aktarması Vault'tan anahtar ALINDIKTAN SONRA koşar — ağsız kol o satıra hiç varmaz (planın
    "kör kapı"sı). Sahte Vault anahtarı verir; zincir (kurtarma token'ı → Vault → anahtar → SQLCipher → tablo) GERÇEK
    yorumlayıcıda koşar."""
    sentetik_veri_koku(tmp_path / "veri", SQL_ANAHTARI, Fernet.generate_key().decode())
    env = _ortam(tmp_path)
    emanet = {"auto.sqlcipher_key": SQL_ANAHTARI}
    with SahteVault(kok=KOK, kurtarma=KURTARMA, emanet=emanet, kurtarma_ttl=ON_YIL_SN) as v:
        env["PEMF_VAULT_ADRES"] = v.adres
        p = kostur(
            [str(DEPO / "scripts" / "vault_emanet.py"), "--tatbikat", "--token", KURTARMA], cwd=DEPO, env=env, sure=120
        )
    _iz_yok(p)
    assert p.returncode == 0 and "TATBIKAT BASARILI" in p.stdout, f"rc={p.returncode}\n{p.stdout[-1200:]}"
    assert v.siniflar("/v1/pemf/data/") == ["kurtarma"], v.istekler
    assert SQL_ANAHTARI not in p.stdout + p.stderr, "tatbikat anahtarı BASTI"
