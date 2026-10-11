# -*- coding: utf-8 -*-
"""D4.19 (B-10.74) — build AI kapısında üretilen EXE sağlık ucuna ULAŞILAMAZSA derleme DURUR (çıkış ≠ 0); açık `-SkipAiGate`
olmadan "✓ Headless backend EXE hazır" BASILMAZ.

ARIZA: `scripts/build_backend_exe.ps1` AI hazırlık kapısı EXE açılmazsa `Warn "… kapı ATLANDI"` deyip devam ediyor, betik
"✓ Headless backend EXE hazır" ve ÇIKIŞ 0 ile bitiyordu → hiç açılmayan (ölü doğmuş) bir EXE paketlemeye geçebilir; AI hazırlık,
XAI zinciri, pip yasağı ve çalışma-anı kod koruması denetimleri BİRLİKTE düşer (hafıza: "build başarısızken çıkış 0").

Ölçüm: AI kapısı bloğu ve betiğin SON bloğu ("EXE hazır" / "EXE yok") PowerShell AYRIŞTIRICISIYLA alınıp GERÇEK metinleriyle koşar;
betiğin KENDİ `Info / Warn / Die`'ı kullanılır (Die = `exit 1` → süreç çıkış kodu ölçülür). `Start-Process` gölge (EXE başlatılmaz;
"hemen ölmüş" süreç döner), `Start-Sleep` / `Invoke-RestMethod` gölge (ağ YOK, port YOK), süreç cmdlet'leri gölge.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
BETIK = KOK / "scripts" / "build_backend_exe.ps1"
PWSH = shutil.which("pwsh")

pytestmark = pytest.mark.skipif(PWSH is None, reason="pwsh yok — build betiği pwsh ile koşar")

_SURUCU = r"""
param([string]$Betik, [string]$Kok, [string]$Senaryo)
$ErrorActionPreference = 'Stop'
# Türkçe iletiler ("hazır") konsol kod sayfasında bozulursa "basılmaz" iddiası SAHTE-YEŞİL olur → UTF-8 sabit.
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$tokens = $null; $errs = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($Betik, [ref]$tokens, [ref]$errs)
if ($errs) { throw "build betiği ayrıştırılamadı: $($errs | Out-String)" }
$ust = $ast.EndBlock.Statements
$ai = $ust | Where-Object { $_ -is [System.Management.Automation.Language.IfStatementAst] -and $_.Clauses[0].Item1.Extent.Text -match 'SkipAiGate' } | Select-Object -First 1
$son = $ust[$ust.Count - 1]
if (-not $ai -or -not ($son.Extent.Text -match 'EXE hazır')) { throw "çıpa: AI kapısı ya da son 'EXE hazır' bloğu bulunamadı" }
foreach ($fn in $ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] }, $true)) {
    Invoke-Expression $fn.Extent.Text   # Info / Warn / Die GERÇEK (Die = exit 1)
}
function Start-Sleep { }
function Stop-Process { }
function Wait-Process { }
function Get-Process { @() }
function Start-Process {
    param($FilePath, $ArgumentList, $RedirectStandardOutput, $RedirectStandardError, [switch]$PassThru, $WindowStyle)
    [pscustomobject]@{ Id = 0; HasExited = $true; ExitCode = 3 }   # açılır açılmaz ölen EXE
}
$global:SAGLIKLI = ($Senaryo -eq 'saglikli')
function Invoke-RestMethod {
    param($Uri, $TimeoutSec, $Headers)
    if (-not $global:SAGLIKLI) { throw 'sahte: baglanti reddedildi' }
    if ($Uri -match '/api/health') { return [pscustomobject]@{ status = 'ok' } }
    return [pscustomobject]@{ hazir = 2; toplam = 2; eksik = @(); moduller = @();
        xai = [pscustomobject]@{ hazir = $true; grad_cam = $true; shap = $true; captum = $true; ttach = $true; em_ref_stats_eksik = @() };
        pip_yasagi = [pscustomobject]@{ etkin = $true } }
}
$BuildRoot = $Kok
$dist = Join-Path $Kok 'dist'
$exe = Join-Path $dist 'PEMF_Backend\PEMF_Backend.exe'
New-Item -ItemType File -Force -Path $exe | Out-Null
$SkipAiGate = ($Senaryo -eq 'atla')
$SkipProtect = $true
$dt = [timespan]::Zero
& ([scriptblock]::Create($ai.Extent.Text))
& ([scriptblock]::Create($son.Extent.Text))
Write-Host 'SURUCU-SONU'
exit 0
"""


def _kos(tmp_path: Path, senaryo: str) -> subprocess.CompletedProcess:
    surucu = tmp_path / "surucu.ps1"
    surucu.write_text(_SURUCU, encoding="utf-8-sig")
    kok = tmp_path / "build_kok"
    kok.mkdir()
    env = {**os.environ, "POWERSHELL_TELEMETRY_OPTOUT": "1", "POWERSHELL_UPDATECHECK": "Off"}
    return subprocess.run(
        [
            PWSH,
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(surucu),
            str(BETIK),
            str(kok),
            senaryo,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=300,
    )


def test_KRITIK_EXE_acilmazsa_derleme_DURUR_ve_hazir_BASILMAZ(tmp_path):
    r = _kos(tmp_path, "acilmadi")
    assert "çıpa" not in (r.stdout + r.stderr), r.stderr[-800:]
    assert "AI hazırlık kapısı" in r.stdout, (
        f"kodlama bozuk ya da blok kosmadi (iddialar sahte-yesil olur):\n{r.stdout[-800:]}"
    )
    assert r.returncode != 0, (
        f"EXE saglik ucuna ulasilamadi ama build CIKIS 0 verdi (sahte basari):\n{r.stdout[-1500:]}"
    )
    assert "Headless backend EXE hazır" not in r.stdout, "acilmayan EXE icin 'EXE hazir' basildi"
    assert "SURUCU-SONU" not in r.stdout, "Die betigi durdurmadi"
    assert "-SkipAiGate" in r.stdout, "hata iletisi bilincli gecisin yolunu soylemiyor"


def test_KARSIT_saglikli_EXE_ile_kapi_GECER(tmp_path):
    r = _kos(tmp_path, "saglikli")
    assert r.returncode == 0 and "Headless backend EXE hazır" in r.stdout, f"{r.stdout[-1500:]}\n{r.stderr[-800:]}"


def test_KARSIT_acik_SkipAiGate_bilincli_gecis(tmp_path):
    r = _kos(tmp_path, "atla")
    assert r.returncode == 0 and "Headless backend EXE hazır" in r.stdout, f"{r.stdout[-1500:]}\n{r.stderr[-800:]}"
