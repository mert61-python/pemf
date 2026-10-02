# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""Test aparatı: KAYITÇI `cmdkey` — testler GERÇEK Windows kimlik kasasına YAZMAZ, ondan OKUMAZ.

Kaynak: e035b25 (1-B §9 #10 hijyeni; `test_teardown_system_kasasi`) — 1-D'de (1-C §9 #16) ortak modüle alındı ve
`test_teardown_kimlik_dogrulama` da buna geçti (o dosya Python'dan yalın `cmdkey /add:PEMF_GATE_<uuid>` ile gerçek
kasaya yazıp `finally`'de siliyordu: her tam süitte 8 gerçek kasa çağrısı; süreç arada ölürse sahte kayıt kalırdı).

Sürücüler/betikler `cmdkey`i ADIYLA çağırır → PowerShell PATH sırasıyla çözer → PATH'in başındaki kayıtçı `cmdkey.cmd`
gerçek `System32\\cmdkey.exe`den ÖNCE bulunur. Kayıtçı sahte kasa dosyası üzerinde gerçek cmdkey'in tel sözleşmesini taklit
eder (ölçülen gerçek davranış, bkz. `scripts/pemf_teardown.ps1`):
  /generic:<ad> ve /add:<ad> → ekler (rc 0) · /delete:<ad> → varsa siler (rc 0), yoksa "CMDKEY: Element not found." (rc 1) ·
  /list:<ad> → varsa ad 2 KEZ (başlık + "Target:"), yoksa "* NONE *" (ad 1 kez) · /list → her kayıt için "Target: <ad>".
Her çağrı satır olarak kaydedilir (`cagrilar`): betiğin çağrılarının KAYITÇIYA geldiği iddia edilir (gelmeseydi gerçek
kasaya gitmiş olurdu). Python tarafı kayıtçıyı TAM YOLLA çağırır (`cmdkey`) — Windows CreateProcess System32'yi PATH'ten
ÖNCE arar, yalın "cmdkey" GERÇEK aracı bulurdu; Python'dan yalın `cmdkey` süreci başlatılırsa test KIRMIZI (bekçi).
"""

from __future__ import annotations

import os
import subprocess
import types
from pathlib import Path

KAYITCI_CMD = (
    "@echo off\r\n"
    'powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "%~dp0kayitci_cmdkey.ps1" %*\r\n'
    "exit /b %ERRORLEVEL%\r\n"
)
KAYITCI_PS1 = r"""
param([Parameter(ValueFromRemainingArguments=$true)][string[]]$a)
$kasa = $env:PEMF_SAHTE_KASA
$kayit = $env:PEMF_CMDKEY_KAYIT
if (-not $kasa -or -not $kayit) { 'kayitci: PEMF_SAHTE_KASA / PEMF_CMDKEY_KAYIT yok'; exit 99 }
if (-not $a) { $a = @() }
Add-Content -LiteralPath $kayit -Value ($a -join ' ') -Encoding UTF8
$var = @()
if (Test-Path -LiteralPath $kasa) { $var = @(Get-Content -LiteralPath $kasa -Encoding UTF8 | Where-Object { $_ -ne '' }) }
$ilk = if ($a.Count -gt 0) { $a[0] } else { '' }
if ($ilk -like '/generic:*' -or $ilk -like '/add:*') {
    $ad = $ilk.Substring($ilk.IndexOf(':') + 1)
    if ($var -notcontains $ad) { Add-Content -LiteralPath $kasa -Value $ad -Encoding UTF8 }
    'CMDKEY: Credential added successfully.'; exit 0
}
if ($ilk -like '/delete:*') {
    $ad = $ilk.Substring(8)
    if ($var -contains $ad) {
        Set-Content -LiteralPath $kasa -Value @($var | Where-Object { $_ -ne $ad }) -Encoding UTF8
        'CMDKEY: Credential deleted successfully.'; exit 0
    }
    'CMDKEY: Element not found.'; exit 1
}
if ($ilk -like '/list:*') {
    $ad = $ilk.Substring(6)
    "Currently stored credentials for ${ad}:"
    ''
    if ($var -contains $ad) { "    Target: $ad"; '    Type: Generic'; '    User: x' } else { '* NONE *' }
    exit 0
}
if ($ilk -eq '/list') {
    'Currently stored credentials:'
    ''
    if ($var.Count -eq 0) { '* NONE *' } else { foreach ($v in $var) { "    Target: $v"; '    Type: Generic'; '' } }
    exit 0
}
'kayitci: bilinmeyen cmdkey komutu'; exit 2
"""


def kur(tmp_path: Path, monkeypatch) -> types.SimpleNamespace:
    """PATH başında kayıtçı cmdkey + boş sahte kasa + çağrı kaydı; Python'dan yalın `cmdkey` YASAK (bekçi)."""
    kok = tmp_path / "kayitci_cmdkey"
    kok.mkdir()
    (kok / "cmdkey.cmd").write_text(KAYITCI_CMD, encoding="ascii", newline="")
    (kok / "kayitci_cmdkey.ps1").write_text(KAYITCI_PS1, encoding="utf-8-sig")
    kasa = tmp_path / "sahte_kasa.txt"
    kasa.write_text("", encoding="utf-8")
    cagri = tmp_path / "cmdkey_cagrilari.txt"
    monkeypatch.setenv("PATH", f"{kok}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setenv("PEMF_SAHTE_KASA", str(kasa))
    monkeypatch.setenv("PEMF_CMDKEY_KAYIT", str(cagri))
    monkeypatch.setenv("PEMF_KAYITCI_CMDKEY", str(kok / "cmdkey.cmd"))
    gercek_run = subprocess.run

    def _bekci_run(args, *a, **k):
        ilk = args[0] if isinstance(args, (list, tuple)) else str(args).split()[0]
        if os.path.basename(str(ilk)).lower() in ("cmdkey", "cmdkey.exe"):
            raise AssertionError(f"bu test GERÇEK cmdkey'i (kimlik kasası) çağırdı: {args!r} — kayıtçı kullanılmalı")
        return gercek_run(args, *a, **k)

    monkeypatch.setattr(subprocess, "run", _bekci_run)
    return types.SimpleNamespace(kok=kok, kasa=kasa, cagri=cagri)


def cagrilar(kayitci) -> list[str]:
    return kayitci.cagri.read_text(encoding="utf-8-sig").splitlines() if kayitci.cagri.exists() else []


def cmdkey(*args: str) -> subprocess.CompletedProcess:
    """KAYITÇI cmdkey (TAM YOL) — gerçek kasaya ASLA gitmez; kayıtçı kurulmamışsa KIRMIZI (sessiz geri düşüş yok)."""
    kayitci = os.environ.get("PEMF_KAYITCI_CMDKEY", "")
    assert kayitci and Path(kayitci).exists(), "kayıtçı cmdkey kurulmamış — gerçek kasaya düşülmez"
    return subprocess.run(["cmd.exe", "/c", kayitci, *args], capture_output=True, timeout=30)
