# -*- coding: utf-8 -*-
"""İG-9.5 artığı (4-A devri #3) — `setup_services.ps1` API / keşif güvenlik duvarı kuralını ADINA göre değil İÇERİĞİNE göre doğrular.

ARIZA (4-A incelemesi, iki ajan): D2.74 (`d4bb030`) staging kuralını kipe bağlı ADA ve doğru PORTA taşıdı; ama döngü hâlâ "bu adda kural VAR mı"
diye bakıp varsa ATLIYORDU. Aynı adlı ESKİ bir kural farklı port (ör. eski `PEMF_API_PORT`), protokol ya da program yolu (taşınmış kurulum)
taşıyorsa düzeltilmez → backend yeni portta dinler ama LAN'dan (mobil / web istemci) erişim engelli kalır; betik "kural tamam" sanır.

Ölçüm (⛔ gerçek güvenlik duvarına DOKUNULMAZ): `$FwKurallar` ataması, staging dışı ekleme ve `foreach` döngüsü betikten AST ile alınıp GERÇEK
metinleriyle koşar; `Get-NetFirewallRule` / `Get-NetFirewallPortFilter` / `Get-NetFirewallApplicationFilter` / `New-` / `Remove-` / `Set-NetFirewallRule`
durum tutan sahte bir kural tablosuna gölgelenir. (Boru hattı girdili gölgeler gelişmiş işlevdir — ortak `-ErrorAction`'ı zaten taşır,
ayrıca bildirilmez.)
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import capraz
import pytest

KOK = Path(__file__).resolve().parents[1]
SETUP = KOK / "scripts" / "setup_services.ps1"
PWSH = shutil.which("pwsh")
EXE = r"C:\PEMF\runtime\PEMF_Backend\PEMF_Backend.exe"

pytestmark = [
    pytest.mark.skipif(sys.platform != "win32", reason="pwsh aparatı Windows betik anlamını ölçer"),
    pytest.mark.skipif((PWSH is None) and not capraz.ZORUNLU, reason="pwsh (PowerShell 7) bulunamadı"),
]

_SURUCU = r"""
param([string]$Setup, [string]$Durum, [string]$Cikti)
$ErrorActionPreference = 'Stop'
$tokens = $null; $errs = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($Setup, [ref]$tokens, [ref]$errs)
if ($errs) { throw "ayristirilamadi" }
$ust = @($ast.EndBlock.Statements)
# D5 M-1: `$FwKurallar = …` → `foreach ($r in $FwKurallar)` bitişik dilimi + döngünün kullandığı kural işlevi (betikten, parser ile).
$bas = -1; $bit = -1
for ($i = 0; $i -lt $ust.Count; $i++) {
    if ($bas -lt 0 -and $ust[$i].Extent.Text -match '^\$FwKurallar\s*=') { $bas = $i }
    if ($ust[$i].Extent.Text -match '^foreach \(\$r in \$FwKurallar\)') { $bit = $i }
}
if ($bas -lt 0 -or $bit -lt $bas) { [IO.File]::WriteAllText($Cikti, (@{ cipa = "FwKurallar blogu bulunamadi: $bas..$bit" } | ConvertTo-Json)); exit 0 }
$sec = @($ust | Where-Object { $_ -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $_.Name -eq 'Ensure-PemfBackendFirewallKurali' }) +
    @($ust[$bas..$bit])
$d = Get-Content -LiteralPath $Durum -Raw | ConvertFrom-Json
$script:Tablo = [System.Collections.Generic.List[object]]::new()
# 4B-3.5: gerçek kural nesnesi Enabled / Action / Direction / Profile da taşır (betik bunları da içerik sayar).
foreach ($k in @($d.kurallar)) { $script:Tablo.Add([pscustomobject]@{ DisplayName = $k.n; Protocol = $k.p; LocalPort = "$($k.port)"; Program = $k.prog
    Enabled = 'True'; Action = 'Allow'; Direction = 'Inbound'; Profile = 'Any' }) }
$script:Cagri = [System.Collections.Generic.List[string]]::new()
function Log { param($m, $c) $script:Cagri.Add("LOG " + $m) }
function Out-Null { param([Parameter(ValueFromPipeline = $true)]$x) process { } }
function Get-NetFirewallRule { param($DisplayName, $ErrorAction) @($script:Tablo | Where-Object { $_.DisplayName -eq $DisplayName }) }
function Get-NetFirewallPortFilter { param([Parameter(ValueFromPipeline = $true)]$InputObject, $AssociatedNetFirewallRule)
    process { $k = if ($InputObject) { $InputObject } else { $AssociatedNetFirewallRule }; [pscustomobject]@{ Protocol = $k.Protocol; LocalPort = $k.LocalPort } } }
function Get-NetFirewallApplicationFilter { param([Parameter(ValueFromPipeline = $true)]$InputObject, $AssociatedNetFirewallRule)
    process { $k = if ($InputObject) { $InputObject } else { $AssociatedNetFirewallRule }; [pscustomobject]@{ Program = $k.Program } } }
function New-NetFirewallRule { param($DisplayName, $Direction, $Program, $Action, $Protocol, $LocalPort, $Profile, $ErrorAction)
    $script:Cagri.Add("FW-YENI $DisplayName $Protocol $LocalPort")
    $script:Tablo.Add([pscustomobject]@{ DisplayName = $DisplayName; Protocol = $Protocol; LocalPort = "$LocalPort"; Program = $Program
        Enabled = 'True'; Action = $Action; Direction = $Direction; Profile = $Profile }) }
# D5 M-1: kural TEK TEK (boru hattıyla) silinir — gölge hem nesneyi hem adı kabul eder (gelişmiş işlev: -ErrorAction ortak parametre).
function Remove-NetFirewallRule { param([Parameter(ValueFromPipeline = $true)]$InputObject, $DisplayName)
    process {
        $ad = $(if ($InputObject) { $InputObject.DisplayName } else { $DisplayName })
        $script:Cagri.Add("FW-SIL $ad")
        $hedef = $(if ($InputObject) { @($InputObject) } else { @($script:Tablo | Where-Object { $_.DisplayName -eq $DisplayName }) })
        foreach ($k in $hedef) { [void]$script:Tablo.Remove($k) } } }
function Set-NetFirewallRule { param([Parameter(ValueFromPipeline = $true)]$InputObject, $DisplayName, $Protocol, $LocalPort, $Program)
    process { $script:Cagri.Add("FW-DEGISTIR $DisplayName $LocalPort") } }
$StagingMi = [bool]$d.staging
$probePort = [int]$d.port
$BackendExe = $d.exe
foreach ($s in $sec) { . ([scriptblock]::Create($s.Extent.Text)) }
$son = @($script:Tablo | ForEach-Object { [ordered]@{ n = $_.DisplayName; p = $_.Protocol; port = $_.LocalPort; prog = $_.Program } })
[IO.File]::WriteAllText($Cikti, ([ordered]@{ tablo = $son; cagri = @($script:Cagri) } | ConvertTo-Json -Depth 5))
"""


def _kos(tmp_path: Path, staging: bool, port: int, kurallar: list[dict]) -> dict:
    surucu, durum, cikti = tmp_path / "surucu.ps1", tmp_path / "durum.json", tmp_path / "cikti.json"
    surucu.write_text(_SURUCU, encoding="utf-8-sig")
    durum.write_text(json.dumps({"staging": staging, "port": port, "exe": EXE, "kurallar": kurallar}), encoding="utf-8")
    r = subprocess.run(
        [PWSH, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(surucu), "-Setup", str(SETUP),
         "-Durum", str(durum), "-Cikti", str(cikti)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
    )  # fmt: skip
    assert cikti.exists(), f"sürücü sonuç yazmadı (rc={r.returncode}):\n{r.stdout[-800:]}\n{r.stderr[-800:]}"
    veri = json.loads(cikti.read_text(encoding="utf-8-sig"))
    assert "cipa" not in veri, veri
    veri["tablo"] = veri.get("tablo") or []
    if isinstance(veri["tablo"], dict):
        veri["tablo"] = [veri["tablo"]]
    veri["cagri"] = veri.get("cagri") or []
    return veri


def _kural(ad, p, port, prog=EXE):
    return {"n": ad, "p": p, "port": port, "prog": prog}


def _bul(veri: dict, ad: str) -> list[dict]:
    return [k for k in veri["tablo"] if k["n"] == ad]


def test_KRITIK_ayni_adli_ESKI_PORTLU_staging_kurali_DUZELTILIR(tmp_path):
    veri = _kos(tmp_path, True, 8010, [_kural("PEMF Backend API (staging)", "TCP", 8099)])
    kurallar = _bul(veri, "PEMF Backend API (staging)")
    assert [k["port"] for k in kurallar] == ["8010"], (
        f"aynı adlı kural ESKİ portta (8099) bırakıldı — staging backend'i 8010'da dinler, LAN'dan erişilemez: {veri}"
    )


def test_KRITIK_tasinmis_kurulumun_PROGRAM_yolu_eski_kural_DUZELTILIR(tmp_path):
    veri = _kos(tmp_path, False, 8000, [_kural("PEMF Backend API", "TCP", 8000, r"D:\ESKI\PEMF_Backend.exe")])
    assert [k["prog"] for k in _bul(veri, "PEMF Backend API")] == [EXE], (
        f"eski program yolundaki kural düzeltilmedi: {veri}"
    )


def test_KARSIT_dogru_kural_VARKEN_dokunulmaz(tmp_path):
    veri = _kos(
        tmp_path,
        False,
        8000,
        [_kural("PEMF Backend API", "TCP", 8000), _kural("PEMF UDP Discovery", "UDP", 5051)],
    )
    yazan = [c for c in veri["cagri"] if c.startswith(("FW-YENI", "FW-SIL", "FW-DEGISTIR"))]
    assert not yazan, f"doğru kurallar varken güvenlik duvarı DEĞİŞTİRİLDİ: {yazan}"


def test_KARSIT_kural_YOKKEN_dogru_portla_acilir(tmp_path):
    veri = _kos(tmp_path, True, 8010, [])
    assert [(k["p"], k["port"], k["prog"]) for k in _bul(veri, "PEMF Backend API (staging)")] == [
        ("TCP", "8010", EXE)
    ], veri
    assert not _bul(veri, "PEMF UDP Discovery"), "staging keşif kuralı açtı (D2.74)"
