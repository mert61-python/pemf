# -*- coding: utf-8 -*-
"""E2-2.2 (2-E incelemesi, A2) — Windows PowerShell 5.1'de kaldırma raporu Türkçe harfli makine dışı yedek yolunu BOZAR.

Launcher `backup_dir.txt`'yi BOM'suz UTF-8 yazar (`launcher/core/src/install.rs` `backup_dir_yaz` → `std::fs::write`). Klinik kaldırması
Inno'dan `powershell.exe` (5.1) ile `setup_services.ps1 -Uninstall` → `pemf_teardown.ps1` olarak koşar (`build_tools/PEMF_Backend_Setup.iss`
`Exec('powershell.exe', …)`). 5.1'de `Get-Content -Raw` BOM'suz dosyayı ANSI (cp1254) okur → `D:\\Yedek\\Şube` → `D:\\Yedek\\Å\\x9eube`:
hedef VAR iken rapor "şu an ERİŞİLEMİYOR: <bozuk yol>" der; operatöre verilen yer YANLIŞ (A-45/A-87: rapor yerini söyler).

⛔ Kaldırma betiği KOŞMAZ: yalnız iki salt-okur işlev (`Get-PemfMakineDisiYedekHedefleri`, `Write-PemfMakineDisiYedekRaporu`) AST'den
dilimlenir; gövdeleri izin listesi dışında komut içerirse aparat HİÇBİR şey koşmadan çıkar (3). Registry okuyan
`Get-PemfYedekOrtamDegerleri` YÜKLENMEZ (kayıtçı gölge, boş döner); profil kökü pytest tmp_path'tir.
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
TEARDOWN = KOK / "scripts" / "pemf_teardown.ps1"
_PS51 = shutil.which("powershell.exe") or shutil.which("powershell")
_PWSH = shutil.which("pwsh")

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows PowerShell 5.1 anlamı")

_APARAT = r"""
param([Parameter(Mandatory)][string]$Betik, [Parameter(Mandatory)][string]$Profil, [Parameter(Mandatory)][string]$Cikti)
$ErrorActionPreference = 'Stop'
$izinli = @('Get-PemfProfileRoots', 'Join-Path', 'Test-Path', 'Get-Content', 'Get-PemfYedekOrtamDegerleri', 'Add-Member',
    'Get-ChildItem', 'Write-PemfLog', 'Where-Object', 'ForEach-Object', 'Select-Object')
$t = $null; $e = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($Betik, [ref]$t, [ref]$e)
if ($e) { [Console]::Out.WriteLine('APARAT_HATASI parse'); exit 3 }
$script:Log = New-Object System.Collections.Generic.List[string]
function Write-PemfLog($msg, $color) { $script:Log.Add([string]$msg) }
function Get-PemfProfileRoots { @($Profil) }
function Get-PemfYedekOrtamDegerleri { param([string[]]$Services) @() }
function Get-ItemProperty { throw 'golge: registry okunmaz' }
foreach ($ad in 'Get-PemfMakineDisiYedekHedefleri', 'Write-PemfMakineDisiYedekRaporu') {
    $f = @($ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq $ad }, $false))
    if ($f.Count -ne 1) { [Console]::Out.WriteLine('APARAT_HATASI islev yok ' + $ad); exit 3 }
    foreach ($c in $f[0].FindAll({ param($n) $n -is [System.Management.Automation.Language.CommandAst] }, $true)) {
        if ($izinli -notcontains $c.GetCommandName()) { [Console]::Out.WriteLine('APARAT_HATASI izin disi ' + $c.Extent.Text); exit 3 }
    }
    . ([ScriptBlock]::Create($f[0].Extent.Text))
}
$h = @(Get-PemfMakineDisiYedekHedefleri -Footprint ([pscustomobject]@{ Services = @() }))
[void](Write-PemfMakineDisiYedekRaporu -Hedefler $h)
$o = @{ surum = $PSVersionTable.PSVersion.ToString(); yollar = @($h | ForEach-Object { [string]$_.Yol }); log = @($script:Log) }
[IO.File]::WriteAllText($Cikti, ($o | ConvertTo-Json -Depth 4), (New-Object Text.UTF8Encoding($false)))
exit 0
"""


def _kos(tmp_path: Path, kabuk: str, bom: bool) -> tuple[dict, Path]:
    profil = tmp_path / "profil"
    kurulum = profil / "AppData" / "Local" / "PEMF Vet Client"
    kurulum.mkdir(parents=True)
    hedef = tmp_path / "Yedek_Şube_Çağrı_Öğün"
    hedef.mkdir()
    (hedef / "kurtarma-zarfi.enc").write_bytes(b"SENTETIK")
    (hedef / "pemf_patients_20261009_0300.db").write_bytes(b"SENTETIK")
    # launcher backup_dir_yaz ile AYNI: dir.trim() baytları, BOM'suz UTF-8 (std::fs::write)
    (kurulum / "backup_dir.txt").write_bytes((b"\xef\xbb\xbf" if bom else b"") + str(hedef).encode("utf-8"))
    aparat = tmp_path / "aparat.ps1"
    aparat.write_text(_APARAT, encoding="utf-8-sig")
    cikti = tmp_path / "cikti.json"
    p = subprocess.run(
        [kabuk, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(aparat), "-Betik", str(TEARDOWN),
         "-Profil", str(profil), "-Cikti", str(cikti)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
    )  # fmt: skip
    assert p.returncode == 0 and cikti.exists(), (
        f"aparat düştü (rc={p.returncode}):\n{p.stdout[-1500:]}\n{p.stderr[-1500:]}"
    )
    return json.loads(cikti.read_text(encoding="utf-8-sig")), hedef


def _dogru(s: dict, hedef: Path) -> None:
    assert s["yollar"] == [str(hedef)], (
        f"PS {s['surum']}: backup_dir.txt yolu BOZUK okundu: {s['yollar']!r} ≠ {str(hedef)!r}"
    )
    satir = [ln for ln in s["log"] if str(hedef) in ln]
    assert len(satir) == 1 and "DURUYOR" in satir[0] and "2 dosya" in satir[0], (
        f"PS {s['surum']}: var olan makine dışı yedek doğru yerle raporlanmadı: {s['log']}"
    )


@pytest.mark.skipif((_PS51 is None) and not capraz.ZORUNLU, reason="Windows PowerShell 5.1 yok")
def test_KRITIK_ps51_BOMsuz_turkce_yedek_yolu_DOGRU_okunur_ve_DURUYOR_raporlanir_E2_2_2(tmp_path):
    s, hedef = _kos(tmp_path, _PS51, bom=False)
    assert s["surum"].startswith("5."), s["surum"]
    _dogru(s, hedef)


@pytest.mark.skipif((_PS51 is None) and not capraz.ZORUNLU, reason="Windows PowerShell 5.1 yok")
def test_KARSIT_ps51_BOMlu_dosya_HEADde_de_dogru_E2_2_2(tmp_path):
    s, hedef = _kos(tmp_path, _PS51, bom=True)
    _dogru(s, hedef)


@pytest.mark.skipif((_PWSH is None) and not capraz.ZORUNLU, reason="pwsh yok")
def test_KARSIT_pwsh7_BOMsuz_dosya_dogru_E2_2_2(tmp_path):
    s, hedef = _kos(tmp_path, _PWSH, bom=False)
    assert s["surum"].startswith("7."), s["surum"]
    _dogru(s, hedef)
