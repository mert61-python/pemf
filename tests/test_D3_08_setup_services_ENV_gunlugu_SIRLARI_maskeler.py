# Author: mertaygn, cglrgrkn
"""D3.08 + D3.29 (B-3.46 · B-10.69) — `setup_services.ps1` NSSM ortamını günlüğe yazarken SIR adlı anahtarların DEĞERİNİ maskeler.

ÖLÇÜLEN (HEAD): `Log ("Env (" + $Mode + "): " + ($AppEnv -join '  '))` — profil ortamı HAM yazılıyordu; `device.env`'e girilen NAMED
tünel belirteci ya da MQTT parolası `ProgramData\\PEMF_System\\logs\\setup_services.log`'a (dizin Users RX kalıtır) düz düşerdi.
SÖZLEŞME: PASS / TOKEN / SECRET / KEY / CREDENTIAL / PRIVATE / `_PAT` adlı anahtarın değeri `***` (boşsa `(boş)`), ad görünür; öteki
değerler aynen; günlük satırı bu işlevden geçer. Gerçek sır KULLANILMAZ (rastgele nöbetçi). İşlev PowerShell parser'ıyla çekilir.
"""

from __future__ import annotations

import secrets

import capraz
import pytest
from test_setup_services_firewall_kaniti import PS1, PWSH, _extract_function, _ps_lit, _pwsh_file  # noqa: F401 — aparat

pytestmark = pytest.mark.skipif(
    (PWSH is None) and not capraz.ZORUNLU, reason="pwsh (PowerShell 7) yok — PS fonksiyonu koşturulamaz"
)


def test_KRITIK_D3_08_sir_adli_degerler_GUNLUGE_DUSMEZ_adlar_gorunur(tmp_path):
    func = _extract_function(tmp_path, "Format-PemfEnvGunluk")
    nobetci = {
        k: "NOBETCI_" + secrets.token_hex(8)
        for k in (
            "PEMF_MQTT_PASS",
            "PEMF_CLOUDFLARE_TUNNEL_TOKEN",
            "PEMF_API_KEY",
            "SUPABASE_PAT",
            "PEMF_MASTER_SECRET",
        )
    }
    satirlar = "; ".join(f'"{k}" = {_ps_lit(v)}' for k, v in nobetci.items())
    body = f"""
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
{func}
$m = [ordered]@{{ "PYTHONUNBUFFERED" = "1"; "PEMF_HEADLESS" = "1"; {satirlar}; "PEMF_TEST_TOKEN" = ""; "PEMF_ENCRYPT_AT_REST" = "1" }}
Write-Output ("GUNLUK=" + (Format-PemfEnvGunluk $m))
"""
    r = _pwsh_file(tmp_path, "d308.ps1", body)
    assert r.returncode == 0, r.stdout + r.stderr
    gunluk = next(s for s in r.stdout.splitlines() if s.startswith("GUNLUK="))
    for k, v in nobetci.items():
        assert v not in gunluk, f"{k} değeri günlüğe düz düştü"
        assert f"{k}=***" in gunluk, f"{k} adı / maskesi görünmüyor: {gunluk}"
    assert "PEMF_TEST_TOKEN=(boş)" in gunluk and "PEMF_HEADLESS=1" in gunluk and "PEMF_ENCRYPT_AT_REST=1" in gunluk, (
        gunluk
    )


def test_KRITIK_D3_08_env_gunluk_satiri_MASKELEYICIDEN_gecer():
    metin = PS1.read_text(encoding="utf-8-sig")
    satir = [s for s in metin.splitlines() if s.lstrip().startswith("Log (") and '"Env ("' in s]
    assert len(satir) == 1, satir
    assert "Format-PemfEnvGunluk $EnvMap" in satir[0] and "$AppEnv -join" not in satir[0], satir[0]
