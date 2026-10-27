# -*- coding: utf-8 -*-
"""4B-1.2 — D4.28 kapısının iki iddiası ÖLÇÜLMÜYORDU (kör kapı; ölçüldü: iki mutant 4-B kümesinde 24/24 YEŞİL).

  (a) "ölü EXE için 3 dakika yoklama YOK" — `if ($proc.HasExited) { break }` → `continue` mutantında kapı 90×2 sn UYUR ama
      sağlığı yoklamaz; 4-B testi yalnız SAĞLIK çağrısını sayıyordu (Start-Sleep gölgesi sayılmıyordu).
  (b) "Nonce kapı ortam tablosunda → blok sonunda build sürecinden geri alınır" — nonce tablodan çıkarılıp `$env:` ile
      verilse build sürecinde (ve betiği nokta-eğik çizgiyle çağıran etkileşimli oturumda / `build_installer.ps1`'in sürecinde) KALIR;
      ortam-geri-yükleme testi PEMF_HEALTH_NONCE'u listesinde taşımıyordu.

AI bloğu ve son blok GERÇEK metinleriyle, betiğin GERÇEK Info/Warn/Die'ı; gerçek EXE / ağ / port YOK.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import capraz
import pytest

KOK = Path(__file__).resolve().parents[1]
BETIK = KOK / "scripts" / "build_backend_exe.ps1"
PWSH = shutil.which("pwsh")
pytestmark = pytest.mark.skipif((PWSH is None) and not capraz.ZORUNLU, reason="pwsh yok — build betiği pwsh ile koşar")

_SURUCU = r"""
param([string]$Betik, [string]$Kok, [string]$Senaryo, [string]$Cikti)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$tokens = $null; $errs = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($Betik, [ref]$tokens, [ref]$errs)
if ($errs) { throw "ayrıştırılamadı: $($errs | Out-String)" }
$ust = $ast.EndBlock.Statements
$ai = $ust | Where-Object { $_ -is [System.Management.Automation.Language.IfStatementAst] -and $_.Clauses[0].Item1.Extent.Text -match 'SkipAiGate' } | Select-Object -First 1
if (-not $ai) { throw "çıpa: AI kapısı bulunamadı" }
foreach ($fn in $ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] }, $true)) {
    Invoke-Expression $fn.Extent.Text   # GERÇEK Info/Warn/Die (Die = exit 1)
}
$global:SENARYO = $Senaryo
$global:UYKU = 0; $global:SAGLIK = 0
function Start-Sleep { $global:UYKU++ }
function Stop-Process { }
function Wait-Process { }
function Get-Process { @() }
function Start-Process {
    param($FilePath, $ArgumentList, $RedirectStandardOutput, $RedirectStandardError, [switch]$PassThru, $WindowStyle)
    $global:COCUK_NONCE = [Environment]::GetEnvironmentVariable('PEMF_HEALTH_NONCE', 'Process')
    [pscustomobject]@{ Id = 0; HasExited = ($global:SENARYO -eq 'olu'); ExitCode = 3 }
}
function Invoke-RestMethod {
    param($Uri, $TimeoutSec)
    if ($Uri -match '/api/health') { $global:SAGLIK++; return [pscustomobject]@{ status = 'ok'; launcherNonce = $global:COCUK_NONCE } }
    [pscustomobject]@{ hazir = 1; toplam = 1; eksik = @(); moduller = @([pscustomobject]@{ modul = 'm'; hazir = $true; yukleme = 'pyd' });
        xai = [pscustomobject]@{ hazir = $true; grad_cam = $true; shap = $true; captum = $true; ttach = $true; em_ref_stats_eksik = @() };
        pip_yasagi = [pscustomobject]@{ etkin = $true } }
}
$BuildRoot = $Kok
$dist = Join-Path $Kok 'dist'
$exe = Join-Path $dist 'PEMF_Backend\PEMF_Backend.exe'
New-Item -ItemType File -Force -Path $exe | Out-Null
$SkipAiGate = $false
$SkipProtect = $true
# Ölçüm, Die (exit 1) olsa da yazılsın: sonuç `trap` yerine kendi try/finally'mizde.
try { & ([scriptblock]::Create($ai.Extent.Text)) }
finally {
    [ordered]@{
        uyku = $global:UYKU; saglik = $global:SAGLIK
        cocuk_nonce_uzunluk = ([string]$global:COCUK_NONCE).Length
        sonra_nonce = [Environment]::GetEnvironmentVariable('PEMF_HEALTH_NONCE', 'Process')
    } | ConvertTo-Json | Set-Content -LiteralPath $Cikti -Encoding UTF8
}
"""


def _kos(tmp_path: Path, senaryo: str, onceki_nonce: str | None) -> dict:
    tmp_path.mkdir(parents=True, exist_ok=True)
    surucu, cikti = tmp_path / "surucu.ps1", tmp_path / "olcum.json"
    surucu.write_text(_SURUCU, encoding="utf-8-sig")
    kok = tmp_path / "build_kok"
    kok.mkdir(exist_ok=True)
    ortam = {k: v for k, v in os.environ.items() if k.upper() != "PEMF_HEALTH_NONCE"}
    ortam.update({"POWERSHELL_TELEMETRY_OPTOUT": "1", "POWERSHELL_UPDATECHECK": "Off"})
    if onceki_nonce is not None:
        ortam["PEMF_HEALTH_NONCE"] = onceki_nonce  # ör. betik launcher çocuğu bir oturumdan çağrıldı
    r = subprocess.run(
        [PWSH, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(surucu),
         str(BETIK), str(kok), senaryo, str(cikti)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", env=ortam, timeout=300,
    )  # fmt: skip
    assert cikti.exists(), f"ölçüm yazılmadı (rc={r.returncode}):\n{r.stdout[-1200:]}\n{r.stderr[-1200:]}"
    o = json.loads(cikti.read_text(encoding="utf-8-sig"))
    o["rc"] = r.returncode
    return o


def test_KRITIK_olu_EXE_icin_kapi_UYUYARAK_da_BEKLEMEZ(tmp_path):
    o = _kos(tmp_path, "olu", None)
    assert o["rc"] != 0
    assert o["uyku"] <= 2, (
        f"EXE ölü (HasExited) olduğu hâlde kapı {o['uyku']} kez 2 sn uyudu (~{2 * o['uyku']} sn) — "
        "sağlık yoklanmasa da döngü sürüyor (break yerine continue)"
    )


@pytest.mark.parametrize("onceki", [None, "LAUNCHER-OTURUMUNUN-NONCE-U"])
def test_KRITIK_kapi_nonce_u_blok_sonunda_build_surecinden_GERI_ALINIR(tmp_path, onceki):
    o = _kos(tmp_path, "kendi", onceki)
    assert o["rc"] == 0, o
    assert o["cocuk_nonce_uzunluk"] >= 16, "EXE'ye nonce verilmedi (aparat)"
    assert o["sonra_nonce"] == onceki, (
        f"blok bitince build sürecindeki PEMF_HEALTH_NONCE = {('<' + str(len(o['sonra_nonce'])) + ' karakter>') if o['sonra_nonce'] else o['sonra_nonce']!r}, "
        f"beklenen {onceki!r} — kapı nonce'u build sürecine (ve çağıran oturuma) SIZDIRDI"
    )


def test_KRITIK_Die_yolunda_da_nonce_SIZMAZ(tmp_path):
    o = _kos(tmp_path, "olu", None)
    assert o["rc"] != 0
    assert o["sonra_nonce"] is None, "Die (exit 1) yolunda nonce build sürecinde kaldı"
