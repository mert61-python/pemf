# -*- coding: utf-8 -*-
"""S-4B.3 [ÖNERİLEN UYGULANDI] (4-A incelemesi A1 S4) — Y30 süit betiğinin `PSModulePath` nötrleştirmesi otoyüklemeye DAYANIKLI.

ARIZA (ölçüldü, 4-B): Y30 (`scripts/yayin_oncesi_suit.ps1`) pwsh 7'nin modül yolunu pytest'in açtığı Windows PowerShell 5.1'e sızdırmamak için
değişkeni `Remove-Item Env:PSModulePath` ile SİLİYORDU. pwsh, silinmiş değişkeni bir sonraki modül yüklemesinde/otoyüklemesinde KENDİ yollarıyla
yeniden kurar → python → `powershell.exe` 5.1 yine `Microsoft.PowerShell.Security`'nin 7 sürümünü görür, `Get-Acl … module could not be loaded`
(sonda: silme = dokunmama = KIRMIZI; boş dize = YEŞİL). Bugün betikte silme ile çağrı arasında otoyükleme olmadığı için çalışıyor; araya
henüz yüklenmemiş bir cmdlet giren her düzenleme Y30'u SESSİZCE bozar (9 ACL testi yalancı kırmızı → her yayın durur).

Ölçüm: nötrleştirme deyimleri betikten AST ile alınır (`$psModulYolu = $env:PSModulePath` ataması ile `Push-Location` arası) ve taze pwsh'ta
GERÇEK metinleriyle koşar; ardından süreç içi otoyükleme (`Get-Acl` → Security modülü) ve python → `powershell.exe` 5.1 `Get-Acl`. Geri yükleme:
değişken önceden YOKKEN betiğin yakalama + nötrleştirme deyimleri ve `finally` bloğu AST'den alınıp koşar → değişken yine YOK
kalmalı ('' kalmamalı; boş dize nötrleştirmesinin yeni geri yükleme dalı).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
BETIK = KOK / "scripts" / "yayin_oncesi_suit.ps1"
PWSH = shutil.which("pwsh")

pytestmark = pytest.mark.skipif(
    PWSH is None or os.name != "nt" or not shutil.which("powershell.exe"),
    reason="pwsh 7 + Windows PowerShell 5.1 gerekir",
)

_YARDIMCI = """import subprocess, sys
r = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                    "(Get-Acl -LiteralPath '" + sys.argv[1] + "').Sddl.Substring(0,2)"], capture_output=True, text=True)
print("ALT51", r.returncode, (r.stdout + r.stderr).strip()[:200])
"""

_SURUCU = r"""
param([string]$Betik, [string]$Py, [string]$Yardimci, [string]$Dizin, [string]$Kol)
$tokens = $null; $errs = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($Betik, [ref]$tokens, [ref]$errs)
if ($errs) { [Console]::WriteLine("CIPA: ayristirilamadi"); exit 3 }
$ust = @($ast.EndBlock.Statements)
$bas = -1; $son = -1
for ($i = 0; $i -lt $ust.Count; $i++) {
    if ($bas -lt 0 -and $ust[$i].Extent.Text -match '^\$psModulYolu\s*=\s*\$env:PSModulePath') { $bas = $i }
    elseif ($bas -ge 0 -and $son -lt 0 -and $ust[$i].Extent.Text -match '^Push-Location') { $son = $i }
}
if ($bas -lt 0 -or $son -le $bas + 1) { [Console]::WriteLine("CIPA: notrlestirme blogu bulunamadi"); exit 3 }
if ($Kol -eq 'notr') {
    for ($i = $bas; $i -lt $son; $i++) { . ([scriptblock]::Create($ust[$i].Extent.Text)) }
    $null = Get-Acl -LiteralPath $Dizin          # surec ici modul otoyuklemesi (pwsh modul yolunu yeniden kurabilir)
    $o = & $Py $Yardimci $Dizin 2>&1 | Out-String
    [Console]::WriteLine($o.Trim())
    exit 0
}
# Kol 'geri': finally blogu, onceden YOK olan degiskenle
$dene = $ust[$son + 1]
if (-not ($dene -is [System.Management.Automation.Language.TryStatementAst]) -or -not $dene.Finally) {
    [Console]::WriteLine("CIPA: try/finally bulunamadi"); exit 3
}
function Pop-Location { }
Remove-Item -LiteralPath 'Env:PSModulePath' -ErrorAction SilentlyContinue   # onceden YOK (SetEnvironmentVariable($null) '' birakir)
if ($null -ne [Environment]::GetEnvironmentVariable('PSModulePath', 'Process')) { [Console]::WriteLine('CIPA: onceden-yok kurulamadi'); exit 3 }
for ($i = $bas; $i -lt $son; $i++) { . ([scriptblock]::Create($ust[$i].Extent.Text)) }   # yakalama + notrlestirme
foreach ($d in $dene.Finally.Statements) { . ([scriptblock]::Create($d.Extent.Text)) }
$v = [Environment]::GetEnvironmentVariable('PSModulePath', 'Process')
[Console]::WriteLine("GERI: " + $(if ($null -eq $v) { 'YOK' } else { "VAR[" + $v + "]" }))
exit 0
"""


def _kos(tmp_path: Path, kol: str) -> subprocess.CompletedProcess:
    dizin = tmp_path / "acl_hedefi"
    dizin.mkdir(exist_ok=True)
    (tmp_path / "yardimci.py").write_text(_YARDIMCI, encoding="utf-8")
    surucu = tmp_path / "surucu.ps1"
    surucu.write_text(_SURUCU, encoding="utf-8-sig")
    return subprocess.run(
        [PWSH, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(surucu), "-Betik", str(BETIK),
         "-Py", sys.executable, "-Yardimci", str(tmp_path / "yardimci.py"), "-Dizin", str(dizin), "-Kol", kol],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300,
    )  # fmt: skip


def test_KRITIK_notrlestirme_OTOYUKLEMEDEN_sonra_da_alt_PowerShell51_GetAcl_calisir(tmp_path):
    r = _kos(tmp_path, "notr")
    assert "CIPA" not in r.stdout, r.stdout
    assert "ALT51 0 O:" in r.stdout, (
        "Y30 nötrleştirmesinden sonra bir modül otoyüklemesi pwsh 7 modül yolunu geri getirdi → python → powershell.exe 5.1 Get-Acl "
        f"DÜŞTÜ (9 ACL testi yalancı kırmızı, Y30 yayını durdurur):\n{r.stdout[-800:]}\n{r.stderr[-400:]}"
    )


def test_KRITIK_onceden_YOK_olan_PSModulePath_geri_yuklemede_YOK_kalir(tmp_path):
    r = _kos(tmp_path, "geri")
    assert "CIPA" not in r.stdout, r.stdout
    assert "GERI: YOK" in r.stdout, f"önceden olmayan PSModulePath süitten sonra '' / değerle KALDI:\n{r.stdout[-400:]}"
