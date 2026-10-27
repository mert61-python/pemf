# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D5.46 (B-10.73) — `scripts/build_backend_exe.ps1`'in iki derleme koruması DAVRANIŞLA kapılı.

KORUMALAR (betikte vardı, hiçbir test ÇALIŞTIRMIYORDU — silinmeleri 112 testte YEŞİL, ölçüldü):
  (b) BAYAT BULUT PROVİZYONU: `make_cloud_provision.py` başarısızsa eski `data\\cloud_mqtt_provision.json` SİLİNİR — kalırsa
      PyInstaller onu pakete gömer ve "BULUT-AYNASIZ çıkacak" uyarısı YALAN olur (bayat / döndürülmüş kimlik sevk edilir).
  (c) YETİM SÜREÇ TEMİZLİĞİ: yapı ağacından (`$BuildRoot`) çalışan süreçler (önceki AI kapısının yetim mosquitto'su) durdurulur —
      yoksa DLL kilidi sonraki build'i düşürür. YALNIZ yapı ağacındakiler: kurulu runtime'a / başka süreçlere DOKUNULMAZ.
  (a) Qt-sızıntı bekçisi (`check_headless_imports.py`) zaten D4.28 kapılarında (`test_build_AI_kapisi_KENDI_SURECINE_bagli…`,
      `test_headless_bekcisi_KOR_BICIMLERI_gorur_D428`) davranışla ölçülüyor — burada tekrarlanmaz.

ÖLÇÜM: bloklar PowerShell AYRIŞTIRICISIYLA betikten alınır (çağrı + hemen ardındaki deyim; yetim için atama + foreach) ve GERÇEK
metinleriyle koşar. `$PY` sahte bir işlevdir (yalnız `$LASTEXITCODE` ayarlar — Python BAŞLATILMAZ). `Get-Process`, `Stop-Process`,
`Start-Sleep` GÖLGE işlevler: sahte süreç listesi döner, durdurma yalnız KAYDEDİLİR — gölgelerin çözüldüğü (`Get-Command` → Function)
bloktan ÖNCE denetlenir, değilse sürücü 99 ile çıkar (gerçek süreç ASLA durdurulmaz). Tüm yollar geçici dizinde.
MUTASYON: bayat dosya silmesini ya da `Stop-Process` satırını kaldırmak / yol süzgecini genişletmek → KIRMIZI.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
BETIK = KOK / "scripts" / "build_backend_exe.ps1"
PWSH = shutil.which("pwsh")

pytestmark = pytest.mark.skipif(PWSH is None, reason="pwsh (PowerShell 7) yok — build betiği pwsh ile koşar")

_SURUCU = r"""
param([string]$Betik, [string]$Kok, [int]$Kod, [string]$Cikti)
$ErrorActionPreference = 'Stop'
$tokens = $null; $errs = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($Betik, [ref]$tokens, [ref]$errs)
if ($errs) { throw "build betiği ayrıştırılamadı: $($errs | Out-String)" }
$global:UYARI = [System.Collections.Generic.List[string]]::new()
$global:DURDURULAN = [System.Collections.Generic.List[int]]::new()
function Info { }
function Warn($m) { $global:UYARI.Add([string]$m) }
function Die($m) { throw "DIE: $m" }
function SahtePy { $global:LASTEXITCODE = $global:KOD }
function Start-Sleep { }
function Stop-Process { param([int]$Id, [switch]$Force, $EA, $ErrorAction) $global:DURDURULAN.Add($Id) }
function Get-Process { param($EA, $ErrorAction) $global:SAHTE_SURECLER }
foreach ($ad in 'Stop-Process', 'Get-Process', 'Start-Sleep') {
  if ((Get-Command $ad).CommandType -ne 'Function') { Write-Output "GOLGE DEVREDE DEGIL: $ad"; exit 99 }
}
$PY = 'SahtePy'
$GuiRoot = Join-Path $Kok 'guii'
$BuildRoot = Join-Path $Kok 'PEMF_BUILD'
$global:KOD = $Kod

# (b) make_cloud_provision çağrısı + hemen ardındaki deyim
$cagri = @($ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.CommandAst] -and
    $n.InvocationOperator -eq 'Ampersand' -and $n.CommandElements[0].Extent.Text -eq '$PY' -and
    $n.Extent.Text -match 'make_cloud_provision\.py' }, $true))
if ($cagri.Count -ne 1) { throw "make_cloud_provision çağrısı tam 1 değil: $($cagri.Count)" }
$deyim = $cagri[0].Parent
$liste = @($deyim.Parent.Statements)
$i = [array]::IndexOf($liste, $deyim)
& ([scriptblock]::Create($deyim.Extent.Text + "`n" + $liste[$i + 1].Extent.Text))

# Bir deyimin ÖNÜNDEKİ bağımlı atamalar (aynı blokta, deyimin okuduğu değişkenlere SON atama) — sürücünün kendi verdikleri hariç.
function Bagimli($deyim, [string[]]$dis) {
  $liste = @($deyim.Parent.Statements); $i = [array]::IndexOf($liste, $deyim)
  $adlar = @($deyim.FindAll({ param($n) $n -is [System.Management.Automation.Language.VariableExpressionAst] }, $true) |
    ForEach-Object { $_.VariablePath.UserPath } | Sort-Object -Unique)
  $metin = @()
  foreach ($ad in $adlar) {
    if ($dis -contains $ad) { continue }
    $son = $null
    for ($j = 0; $j -lt $i; $j++) {
      $s = $liste[$j]
      if ($s -is [System.Management.Automation.Language.AssignmentStatementAst] -and $s.Left.Extent.Text -eq ('$' + $ad)) { $son = $s }
    }
    if ($son) { $metin += $son.Extent.Text }
  }
  $metin -join "`n"
}

# (c) yetim süreç temizliği: `$yetim = …` ataması + onu gezen foreach
$atama = @($ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.AssignmentStatementAst] -and
    $n.Left.Extent.Text -eq '$yetim' }, $true))
if ($atama.Count -ne 1) { throw "`$yetim ataması tam 1 değil: $($atama.Count)" }
$gez = @($ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.ForEachStatementAst] -and
    $n.Condition.Extent.Text -eq '$yetim' }, $true))
if ($gez.Count -ne 1) { throw "`$yetim foreach'i tam 1 değil: $($gez.Count)" }
$ayni = ($BuildRoot.ToUpperInvariant())   # yol karşılaştırması büyük/küçük harf DUYARSIZ olmalı (Windows)
$global:SAHTE_SURECLER = @(
  [pscustomobject]@{ ProcessName = 'mosquitto'; Id = 4101; Path = (Join-Path $ayni 'dist\PEMF_Backend\_internal\bin\mosquitto\mosquitto.exe') },
  [pscustomobject]@{ ProcessName = 'PEMF_Backend'; Id = 4102; Path = (Join-Path $Kok 'KURULU\runtime\PEMF_Backend\PEMF_Backend.exe') },
  [pscustomobject]@{ ProcessName = 'PEMF_BUILD_eski'; Id = 4103; Path = ($BuildRoot + '_eski\dist\x.exe') },
  [pscustomobject]@{ ProcessName = 'sistem'; Id = 4104; Path = $null }
)
& ([scriptblock]::Create((Bagimli $atama[0] @('BuildRoot', '_')) + "`n" + $atama[0].Extent.Text + "`n" + $gez[0].Extent.Text))
$yapi_durdurulan = @($global:DURDURULAN); $global:DURDURULAN.Clear()

# (c2) AI kapısı `finally`sindeki ikiz: `$dist` altından çalışan yetimler
$gez2 = @($ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.ForEachStatementAst] -and
    $n.Condition.Extent.Text -match 'StartsWith\(\$dist' }, $true))
if ($gez2.Count -ne 1) { throw "`$dist yetim foreach'i tam 1 değil: $($gez2.Count)" }
$dist = Join-Path $BuildRoot 'dist'
$global:SAHTE_SURECLER = @(
  [pscustomobject]@{ ProcessName = 'mosquitto'; Id = 4201; Path = (Join-Path $dist.ToUpperInvariant() 'PEMF_Backend\_internal\bin\mosquitto\mosquitto.exe') },
  [pscustomobject]@{ ProcessName = 'eski_dist'; Id = 4202; Path = ($dist + '_eski\PEMF_Backend\PEMF_Backend.exe') },
  [pscustomobject]@{ ProcessName = 'sistem'; Id = 4203; Path = 'C:\Windows\System32\svchost.exe' }
)
& ([scriptblock]::Create((Bagimli $gez2[0] @('dist', '_', 'c')) + "`n" + $gez2[0].Extent.Text))

[ordered]@{
  provizyon_var = (Test-Path -LiteralPath (Join-Path $GuiRoot 'data\cloud_mqtt_provision.json'))
  uyari = @($global:UYARI)
  durdurulan = $yapi_durdurulan
  kapi_durdurulan = @($global:DURDURULAN)
} | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $Cikti -Encoding UTF8
"""


def _kos(tmp_path: Path, kod: int) -> dict:
    kok = tmp_path / "kok"
    prov = kok / "guii" / "data" / "cloud_mqtt_provision.json"
    prov.parent.mkdir(parents=True)
    prov.write_text('{"bayat": "eski kimlik"}', encoding="utf-8")
    surucu = tmp_path / "surucu.ps1"
    surucu.write_text(_SURUCU, encoding="utf-8-sig")
    cikti = tmp_path / "cikti.json"
    r = subprocess.run(
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
            str(kod),
            str(cikti),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    assert "GOLGE DEVREDE DEGIL" not in r.stdout, f"süreç cmdlet gölgesi devrede değil — blok KOŞTURULMADI: {r.stdout}"
    assert r.returncode == 0 and cikti.is_file(), (
        f"sürücü düştü (rc={r.returncode}):\n{r.stdout[-1500:]}\n{r.stderr[-1500:]}"
    )
    return json.loads(cikti.read_text(encoding="utf-8-sig"))


def test_KRITIK_provizyon_URETILEMEZSE_bayat_dosya_SILINIR_ve_soylenir(tmp_path):
    v = _kos(tmp_path, kod=1)
    assert v["provizyon_var"] is False, (
        "make_cloud_provision başarısızken ESKİ cloud_mqtt_provision.json diskte KALDI — PyInstaller onu pakete gömer, "
        "'BULUT-AYNASIZ' uyarısı yalan olur (D5.46 / C7)"
    )
    assert any("BAYAT" in u for u in v["uyari"]), f"bayat dosyanın silindiği söylenmedi: {v['uyari']}"


def test_KARSIT_provizyon_URETILINCE_dosyaya_DOKUNULMAZ(tmp_path):
    v = _kos(tmp_path, kod=0)
    assert v["provizyon_var"] is True and not any("BAYAT" in u for u in v["uyari"]), v


def test_KRITIK_yalniz_YAPI_AGACINDAN_calisan_yetim_surec_DURDURULUR(tmp_path):
    v = _kos(tmp_path, kod=0)
    assert v["durdurulan"] == [4101], (
        f"durdurulan süreçler {v['durdurulan']} — beklenen YALNIZ yapı ağacındaki yetim (4101). Yetim kalırsa DLL kilidi sonraki "
        "build'i düşürür; kurulu runtime (4102), benzer adlı başka kök (4103) ve yolsuz süreç (4104) ASLA durdurulmaz (D5.46)"
    )


def test_KRITIK_AI_kapisi_sonrasi_yalniz_DIST_altindaki_yetim_DURDURULUR(tmp_path):
    """İkiz çağrı yeri: AI kapısının `finally`si `dist` altından çalışan çocukları toplar — kardeş `dist_eski` DEĞİL."""
    v = _kos(tmp_path, kod=0)
    assert v["kapi_durdurulan"] == [4201], (
        f"kapı sonrası durdurulan süreçler {v['kapi_durdurulan']} — beklenen YALNIZ dist altındaki yetim (4201); kardeş dizin "
        "(4202) ve sistem süreci (4203) durdurulmaz (D5.46)"
    )
