# Author: mertaygn, cglrgrkn
"""D3.07 (B-3.44) — `setup_services.ps1` at-rest doğrulaması PROFİLDEN BAĞIMSIZ: profil yoksa / satır düşmüşse "DOĞRULANDI" denmez;
`/api/health` `atRestEncrypted=true` şart; yanıt gelmezse de kurulum doğrulanmış SAYILMAZ.

ÖLÇÜLEN (HEAD): doğrulama `if ($EnvMap['PEMF_ENCRYPT_AT_REST'] -eq '1') { … }` İÇİNDEYDİ — profil dosyası yoksa ya da satır düşmüşse hiç
sorulmuyor, klinik servisi PII'yi düz metne (LocalSystem profili) yazarken kurulum "Kurulum DOĞRULANDI" + `.install_verified` ile bitiyordu;
istendiğinde bile yanıt gelmezse yalnız UYARI. Bugün üç profil de =1 taşıdığı için latent.
⛔ Gerçek servis / port YOK: doğrulama işlevi PowerShell parser'ıyla çekilir, `Invoke-RestMethod` gölgelenir; çağrı yerinin koşula bağlı
OLMADIĞI betiğin AST'sinden ölçülür.
"""

from __future__ import annotations

import json

import capraz
import pytest
from test_setup_services_firewall_kaniti import PS1, PWSH, _extract_function, _ps_lit, _pwsh_file  # noqa: F401 — aparat

pytestmark = pytest.mark.skipif(
    (PWSH is None) and not capraz.ZORUNLU, reason="pwsh (PowerShell 7) yok — PS işlevi koşturulamaz"
)


@pytest.mark.parametrize(
    ("yanit", "beklenen"),
    [
        ('[pscustomobject]@{ status = "online"; atRestEncrypted = $true }', "dogrulandi"),
        ('[pscustomobject]@{ status = "online"; atRestEncrypted = $false }', "kapali"),
        ('[pscustomobject]@{ status = "online" }', "dogrulanamadi"),
        ("throw 'baglanti reddedildi'", "dogrulanamadi"),
    ],
    ids=["acik", "kapali", "alan_yok", "yanit_yok"],
)
def test_KRITIK_D3_07_durum_ucu_DOGRU_siniflanir(tmp_path, yanit, beklenen):
    func = _extract_function(tmp_path, "Test-PemfAtRestDurumu")
    body = f"""
function Invoke-RestMethod {{ [CmdletBinding()] param($Uri, $TimeoutSec) {yanit} }}
function Start-Sleep {{ param($Seconds) }}
{func}
Write-Output ("DURUM=" + (Test-PemfAtRestDurumu 48123 -Deneme 2 -BeklemeSn 0))
"""
    r = _pwsh_file(tmp_path, "d307.ps1", body)
    assert r.returncode == 0, r.stdout + r.stderr
    assert f"DURUM={beklenen}" in r.stdout, r.stdout + r.stderr


def _cagri_yeri(tmp_path) -> dict:
    out = tmp_path / "ast.json"
    body = f"""
$tokens = $null; $errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile({_ps_lit(PS1)}, [ref]$tokens, [ref]$errors)
if ($errors.Count) {{ Write-Output "PARSE-ERROR"; exit 3 }}
$c = @($ast.FindAll({{ param($n) $n -is [System.Management.Automation.Language.CommandAst] -and $n.GetCommandName() -eq 'Test-PemfAtRestDurumu' }}, $true))
$kosullar = @()
if ($c.Count -eq 1) {{
    $p = $c[0].Parent
    while ($p) {{
        if ($p -is [System.Management.Automation.Language.IfStatementAst]) {{ $kosullar += ($p.Clauses | ForEach-Object {{ $_.Item1.Extent.Text }}) }}
        if ($p -is [System.Management.Automation.Language.FunctionDefinitionAst]) {{ $kosullar += ('FONKSIYON:' + $p.Name) }}
        $p = $p.Parent
    }}
}}
[System.IO.File]::WriteAllText({_ps_lit(out)}, (@{{ sayi = $c.Count; kosullar = @($kosullar); satir = $(if ($c.Count) {{ $c[0].Extent.StartLineNumber }} else {{ 0 }}) }} | ConvertTo-Json -Depth 4))
"""
    r = _pwsh_file(tmp_path, "d307ast.ps1", body)
    assert r.returncode == 0, r.stdout + r.stderr
    return json.loads(out.read_text(encoding="utf-8-sig"))


def test_KRITIK_D3_07_cagri_PROFIL_KOSULUNA_bagli_degil_ve_DOGRULANDI_dan_ONCE_durur(tmp_path):
    a = _cagri_yeri(tmp_path)
    assert a["sayi"] == 1, a
    assert not [k for k in a["kosullar"] if "ENCRYPT_AT_REST" in k], f"doğrulama profil satırına bağlı: {a['kosullar']}"
    assert not [k for k in a["kosullar"] if k.startswith("FONKSIYON:")], a
    satirlar = PS1.read_text(encoding="utf-8-sig").splitlines()
    sonra = "\n".join(satirlar[a["satir"] - 1 :])
    i_bitti = sonra.find('Log "Kurulum DOĞRULANDI')
    blok = sonra[:i_bitti]
    assert i_bitti > 0 and blok.count("exit 1") >= 2, (
        "kapalı / doğrulanamadı yolları 'Kurulum DOĞRULANDI'dan ÖNCE durmuyor"
    )
    assert "'kapali'" in blok and "'dogrulandi'" in blok, blok[:400]


@pytest.mark.parametrize("profil", ["device.env", "server.env", "staging.env"])
def test_KRITIK_D3_07_uc_profil_de_AT_REST_ister(profil):
    satir = [s.strip() for s in (PS1.parents[1] / "deploy" / profil).read_text(encoding="utf-8").splitlines()]
    assert "PEMF_ENCRYPT_AT_REST=1" in satir, f"{profil} PEMF_ENCRYPT_AT_REST=1 taşımıyor"
