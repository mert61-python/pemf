# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D2.E04 (İG-9.88 · A-44 / A-45 / A-87 · Y85 · Y99'un temizlik yarısı) — kaldırma makine dışı yedeklere DOKUNMAZ ve raporda yerlerini
söyler; faturalanmamış AI tüketim defteri ve geçici dizine düşen günlükler yalnız tam temizlikte silinir.

Kusur [D2 aday doğrulaması, gölge koşum]: `-IncludePatientData` raporunun son satırı "HASTA VERİSİ DE SİLİNDİ (tam temizlik)" derken
`PEMF_BACKUP_DIR`'deki makine dışı yedekler + `kurtarma-zarfi.enc` ve `<veri kökü>\\jeton_bekleyen.json` duruyordu; raporda yedek yerini
söyleyen satır YOKTU ve yerin tek kaydı (`%LOCALAPPDATA%\\PEMF Vet Client\\backup_dir.txt`) KVKK-dışı yollarla İLK silinen dizindeydi —
sıradan kaldırmada bile. Veri kökü yazılamayınca backend günlüğünün düştüğü `%TEMP%\\PEMF_GUI` (Y99) footprint'te yoktu.

⛔ GERÇEK makinede HİÇBİR ŞEY silinmez (görev kuralı: kurulum/kaldırma betikleri yalnız gölge koşum). Aparat D2 arşivindeki
`teardown_golge.ps1`'in uyarlamasıdır: teardown dot-source edilmeden ÖNCE iki dosyanın üst düzeyi denetlenir (yalnız işlev tanımı, atama,
footprint dot-source); `Get-PemfFootprint`'in mutlak yolları `C:\\X` → `<kök>\\C\\X`'e eşlenir, profil kökleri klon TEMP'indeki sahte
kullanıcıya çevrilir; servis/görev/güvenlik duvarı/ortam/registry/kimlik adımları ve dış komutlar KAYITÇIDIR; `Get-ItemProperty` gerçek
registry'yi OKUMAZ (sahte makine/servis ortamı döner); SON SAVUNMA: global `Remove-Item` / `Set-Content` / `New-Item` … yalnız `<kök>`
altında gerçek iş yapar, dışarısı ve `HKCU:`/`HKLM:` REDDEDİLİR ve kaydedilir. ARAÇ testi bu reddi koşumdan ÖNCE kanıtlar.
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
_PWSH = shutil.which("pwsh")

pytestmark = [
    pytest.mark.skipif(sys.platform != "win32", reason="pwsh gölge koşumu Windows betik anlamını ölçer"),
    pytest.mark.skipif((_PWSH is None) and not capraz.ZORUNLU, reason="pwsh (PowerShell 7) bulunamadı"),
]

_APARAT = r"""
#Requires -Version 7
param(
    [Parameter(Mandatory)] [string]$Kok,
    [Parameter(Mandatory)] [string]$Betik,
    [Parameter(Mandatory)] [string]$Kayit,
    [Parameter(Mandatory)] [string]$Cikti,
    [ValidateSet('client', 'backend', 'gui', 'all')] [string]$Scope = 'all',
    [switch]$IncludePatientData,
    [string]$OrtamYedek = '',
    [string]$ServisYedek = '',
    [string]$Kullanici = 'denetim',
    [switch]$YalnizKanit
)
$ErrorActionPreference = 'Stop'
function Red([string]$m) { [Console]::Out.WriteLine("APARAT_HATASI $m"); exit 3 }
$KokTam = [IO.Path]::GetFullPath($Kok).TrimEnd('\')
$Ust = Split-Path $KokTam -Parent
$TempTam = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\')
if (-not $KokTam.StartsWith($TempTam + '\', [StringComparison]::OrdinalIgnoreCase) -or $KokTam -notmatch '\\pytest-of-[^\\]+\\') { Red "kok TEMP/pytest disinda: $KokTam" }
foreach ($y in $Kayit, $Cikti) {
    $f = [IO.Path]::GetFullPath($y)
    if (-not $f.StartsWith($Ust + '\', [StringComparison]::OrdinalIgnoreCase)) { Red "cikti kok ustu disinda: $f" }
}
# Teardown + footprint ÜST DÜZEYİ: yalnız işlev tanımı, (yalnız Join-Path çağıran) atama ve footprint dot-source'u — başka her şey RED.
foreach ($dosya in @($Betik, (Join-Path (Split-Path $Betik -Parent) 'pemf_footprint.ps1'))) {
    $t = $null; $e = $null
    $a = [System.Management.Automation.Language.Parser]::ParseFile($dosya, [ref]$t, [ref]$e)
    if ($e) { Red "parse: $dosya" }
    foreach ($s in $a.EndBlock.Statements) {
        if ($s -is [System.Management.Automation.Language.FunctionDefinitionAst]) { continue }
        if ($s.Extent.Text -eq ". (Join-Path `$PSScriptRoot 'pemf_footprint.ps1')") { continue }
        if (-not ($s -is [System.Management.Automation.Language.AssignmentStatementAst])) { Red ("ust duzey yan etkili ifade: " + $s.Extent.Text) }
        foreach ($c in $s.FindAll({ param($n) $n -is [System.Management.Automation.Language.CommandAst] }, $true)) {
            if ($c.GetCommandName() -ne 'Join-Path') { Red ("ust duzey komut: " + $c.Extent.Text) }
        }
    }
}
$global:GKok = $KokTam
$global:GKayit = [IO.Path]::GetFullPath($Kayit)
$global:GOrtamYedek = $OrtamYedek
$global:GServisYedek = $ServisYedek
Microsoft.PowerShell.Management\New-Item -ItemType Directory -Force -Path $KokTam | Out-Null

function global:GYaz([string]$olay, $ayrinti) {
    $o = [ordered]@{ olay = $olay; ayrinti = $ayrinti }
    Microsoft.PowerShell.Management\Add-Content -LiteralPath $global:GKayit -Value ($o | ConvertTo-Json -Compress -Depth 6) -Encoding utf8
}
function global:GIzinli([string]$p) {
    if ([string]::IsNullOrWhiteSpace($p)) { return $false }
    if ($p -match '^[A-Za-z]{2,}:' -or $p -match '::') { return $false }   # HKLM:, HKCU:, Env:, provider-nitelikli yol
    try { $f = [IO.Path]::GetFullPath($p) } catch { return $false }
    return $f.StartsWith($global:GKok + '\', [StringComparison]::OrdinalIgnoreCase)
}
# ── SON SAVUNMA: dosya sistemi yazma/silme yalnız <kök> altında gerçek ──
function global:Remove-Item {
    [CmdletBinding()]
    param([Parameter(Position = 0, ValueFromPipelineByPropertyName)] [string[]]$Path,
        [Alias('PSPath', 'LP')] [string[]]$LiteralPath, [switch]$Recurse, [switch]$Force, [string]$Filter,
        [string[]]$Include, [string[]]$Exclude)
    process {
        foreach ($h in @(@($LiteralPath) + @($Path) | Where-Object { $_ })) {
            if (GIzinli $h) {
                Microsoft.PowerShell.Management\Remove-Item -LiteralPath $h -Recurse:$Recurse -Force:$Force -ErrorAction SilentlyContinue
                GYaz 'sil_izinli' $h
            } else { GYaz 'ENGEL_sil' $h }
        }
    }
}
foreach ($c in 'Set-Content', 'Add-Content', 'Out-File', 'New-Item', 'Copy-Item', 'Move-Item', 'Rename-Item', 'Clear-Content') {
    $modul = $(if ($c -eq 'Out-File') { 'Utility' } else { 'Management' })
    $govde = @"
[CmdletBinding()] param([Parameter(ValueFromPipeline)] `$InputObject, [Parameter(Position = 0)] [string[]]`$Path,
    [Alias('PSPath','LP')] [string[]]`$LiteralPath, [Parameter(Position = 1)] `$Value, [string]`$Destination, [string]`$NewName,
    [string]`$ItemType, [string]`$Encoding, [switch]`$Force, [switch]`$Append, [switch]`$Recurse, [switch]`$NoNewline)
begin { `$toplanan = [System.Collections.Generic.List[object]]::new() }
process { if (`$PSBoundParameters.ContainsKey('InputObject')) { `$toplanan.Add(`$InputObject) } }
end {
    `$hedefler = @(@(`$LiteralPath) + @(`$Path) + @(`$Destination) | Where-Object { `$_ })
    foreach (`$h in `$hedefler) { if (-not (GIzinli `$h)) { GYaz 'ENGEL_yaz' ('$c ' + `$h); return } }
    `$pb = @{} + `$PSBoundParameters; [void]`$pb.Remove('InputObject')
    if (`$toplanan.Count -gt 0) { `$toplanan | Microsoft.PowerShell.$modul\$c @pb } else { Microsoft.PowerShell.$modul\$c @pb }
}
"@
    Set-Item -Path "function:global:$c" -Value ([scriptblock]::Create($govde))
}
# ── kayıtçılar: sistem/ağ değiştiren cmdlet'ler ve dış komutlar HİÇBİR ŞEY yapmaz ──
foreach ($c in 'Stop-Process', 'Stop-Service', 'Set-Service', 'Start-Service', 'Restart-Service', 'Remove-ItemProperty',
    'Set-ItemProperty', 'New-ItemProperty', 'Remove-NetFirewallRule', 'New-NetFirewallRule', 'Set-NetFirewallRule',
    'Invoke-RestMethod', 'Invoke-WebRequest', 'Start-Process', 'Invoke-CimMethod', 'Remove-CimInstance',
    'Unregister-ScheduledTask', 'Register-ScheduledTask', 'Start-ScheduledTask', 'Stop-ScheduledTask', 'Set-Acl',
    'Remove-LocalUser', 'Stop-Computer', 'Restart-Computer') {
    Set-Item -Path "function:global:$c" -Value ([scriptblock]::Create("GYaz 'ENGEL_cmdlet' ('$c ' + (`$args -join ' ')); if ('$c' -like 'Invoke-*') { throw 'golge: ag yok ($c)' }"))
}
foreach ($c in 'Get-Process', 'Get-CimInstance', 'Get-NetFirewallRule', 'Get-ScheduledTask', 'Get-WmiObject') {
    Set-Item -Path "function:global:$c" -Value ([scriptblock]::Create("GYaz 'sorgu_bos' ('$c ' + (`$args -join ' ')); @()"))
}
Set-Item -Path 'function:global:Get-Service' -Value { GYaz 'sorgu_bos' ('Get-Service ' + ($args -join ' ')); $null }
# Gerçek registry OKUNMAZ: makine ortamı + NSSM servis ortamı SAHTE (senaryodan).
function global:Get-ItemProperty {
    [CmdletBinding()] param([Parameter(Position = 0)] [string[]]$Path, [string[]]$LiteralPath, [Parameter(Position = 1)] [string[]]$Name)
    $h = "$(@(@($LiteralPath) + @($Path) | Where-Object { $_ }) | Select-Object -First 1)"
    GYaz 'sorgu_registry' $h
    if ($h -like '*\Session Manager\Environment' -and $global:GOrtamYedek) { return [pscustomobject]@{ PEMF_BACKUP_DIR = $global:GOrtamYedek } }
    if ($h -like '*\Services\PemfBackend\Parameters' -and $global:GServisYedek) {
        return [pscustomobject]@{ AppEnvironmentExtra = @('PEMF_HEADLESS=1', "PEMF_BACKUP_DIR=$($global:GServisYedek)") }
    }
}
foreach ($ad in 'sc', 'schtasks', 'cmdkey', 'nssm', 'taskkill', 'reg', 'icacls', 'takeown', 'netsh', 'net', 'net1', 'powershell',
    'pwsh', 'cmd', 'wscript', 'cscript', 'cloudflared', 'mosquitto', 'msiexec', 'winget', 'curl', 'wget', 'git', 'robocopy', 'rundll32') {
    foreach ($n in @($ad, "$ad.exe")) {
        Set-Item -Path "function:global:$n" -Value ([scriptblock]::Create("GYaz 'ENGEL_dis_komut' ('$n ' + (`$args -join ' ')); `$global:LASTEXITCODE = 1"))
    }
}

# ── teardown'u yükle ──
$env:PEMF_TEARDOWN_LOG = Join-Path $KokTam 'pemf_teardown.log'
$env:TEMP = Join-Path $KokTam 'temp'; $env:TMP = $env:TEMP
$env:PEMF_BACKUP_DIR = $null
. $Betik

# ── footprint ve profil kökleri <kök>'e eşlenir; sistem adımları kayıtçı ──
$script:GOrjFootprint = ${function:Get-PemfFootprint}
function global:GEsle([string]$p) { if ($p -match '^([A-Za-z]):\\(.*)$') { return (Join-Path $global:GKok ($Matches[1].ToUpper() + '\' + $Matches[2])) }; return $p }
function Get-PemfFootprint {
    $fp = & $script:GOrjFootprint
    foreach ($p in $fp.Paths) { if ($p.Kind -eq 'Abs') { $p.Path = GEsle $p.Path } }
    $fp.Registry = @(); $fp.Tasks = @()
    $fp.FirewallRx = '^GOLGE_ESLESMEZ$'; $fp.EnvRx = '^GOLGE_ESLESMEZ$'
    return $fp
}
function Get-PemfProfileRoots { @((Join-Path $global:GKok "C\Users\$Kullanici"), (Join-Path $global:GKok 'C\Windows\System32\config\systemprofile')) }
foreach ($f in 'Stop-PemfProcessesAndServices', 'Remove-PemfTasks', 'Remove-PemfFirewall', 'Remove-PemfEnv', 'Remove-PemfRegistry',
    'Remove-PemfCredentials', 'Remove-PemfSystemCredentials', 'Send-PemfAcilDurdur', 'Invoke-PemfAcilDurdurIstegi') {
    Set-Item -Path "function:script:$f" -Value ([scriptblock]::Create("GYaz 'atlandi_kayit' '$f'"))
}
$script:PemfSchtasksYolu = 'schtasks.exe'

if ($YalnizKanit) {
    $disari = Join-Path $Ust 'DISARIDA_SILINMEMELI.txt'
    Microsoft.PowerShell.Management\Set-Content -LiteralPath $disari -Value 'koru' -Encoding utf8
    $iceri = Join-Path $KokTam 'iceri_silinmeli.txt'
    Microsoft.PowerShell.Management\Set-Content -LiteralPath $iceri -Value 'sil' -Encoding utf8
    Remove-Item -LiteralPath $disari -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $iceri -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath 'HKCU:\Software\GOLGE_KANIT_YOK' -Recurse -Force -ErrorAction SilentlyContinue
    Set-Content -LiteralPath (Join-Path $Ust 'DISARIYA_YAZILMAMALI.txt') -Value 'x'
    & sc.exe stop GOLGE_KANIT
    $sc_rc = $LASTEXITCODE
    $komutlar = foreach ($n in 'cmdkey', 'cmdkey.exe', 'schtasks.exe', 'sc.exe', 'Remove-Item', 'Stop-Process', 'Get-ItemProperty', 'Remove-PemfSystemCredentials') {
        $k = Get-Command $n -ErrorAction SilentlyContinue | Select-Object -First 1; "$n=$($k.CommandType)"
    }
    $fp = Get-PemfFootprint
    $o = [ordered]@{
        disarisi_duruyor = (Test-Path -LiteralPath $disari)
        iceri_silindi = -not (Test-Path -LiteralPath $iceri)
        disariya_yazilmadi = -not (Test-Path -LiteralPath (Join-Path $Ust 'DISARIYA_YAZILMAMALI.txt'))
        sc_rc = $sc_rc
        komut_turleri = @($komutlar)
        abs_yol_kokte = (@($fp.Paths | Where-Object Kind -eq 'Abs' | Where-Object { -not (GIzinli $_.Path) }).Count -eq 0)
        profil_kokleri = @(Get-PemfProfileRoots)
    }
    Microsoft.PowerShell.Management\Set-Content -LiteralPath $Cikti -Value ($o | ConvertTo-Json -Depth 4) -Encoding utf8
    exit 0
}

$sonuc = Invoke-PemfTeardown -Scope $Scope -IncludePatientData:$IncludePatientData
$log = @(Microsoft.PowerShell.Management\Get-Content -LiteralPath $env:PEMF_TEARDOWN_LOG -Encoding utf8 -ErrorAction SilentlyContinue)
$o = [ordered]@{ sonuc = @($sonuc); failed = @($script:PemfFailed); log = $log }
Microsoft.PowerShell.Management\Set-Content -LiteralPath $Cikti -Value ($o | ConvertTo-Json -Depth 5) -Encoding utf8
exit 0
"""

_ISTEMCI = Path("C/Users/denetim/AppData/Local/PEMF Vet Client")
_VERI = Path("C/ProgramData/PEMF_System")
_GECICI = ("C/Users/denetim/AppData/Local/Temp", "C/Windows/Temp", "C/Windows/SystemTemp")


def _agac(kok: Path, kayit: bool = True) -> dict:
    """Ürün kodunun GERÇEK yerleriyle sahte kurulum ağacı (`<kök>\\C\\…` = makinenin `C:\\…`'si; `E`, `F`, `G` = makine dışı hedefler)."""

    def yaz(rel: Path, icerik: bytes = b"SENTETIK") -> Path:
        p = kok / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(icerik)
        return p

    y: dict = {
        "disari_dizin": kok / "E" / "PEMF_Yedek",
        "ortam_dizin": kok / "F" / "Yedek2",
        "servis_dizin": kok / "G" / "Yedek3_BAGLI_DEGIL",
    }
    y["hasta_db"] = yaz(_VERI / "PEMF_GUI" / "patients.db")
    y["yerel_yedek"] = yaz(_VERI / "PEMF_GUI" / "backups" / "pemf_patients_20261009_0300.db")
    y["yerel_zarf"] = yaz(_VERI / "PEMF_GUI" / "backups" / "kurtarma-zarfi.enc")
    y["jeton"] = yaz(_VERI / "jeton_bekleyen.json", b'{"bekleyen": []}')
    yaz(_VERI / "logs" / "backend.log")
    yaz(_ISTEMCI / "runtime" / "PEMF_Backend" / "PEMF_Backend.exe")
    y["kayit"] = yaz(_ISTEMCI / "backup_dir.txt", (str(y["disari_dizin"]) + "\r\n").encode("utf-8")) if kayit else None
    y["disari"] = [
        yaz(Path("E/PEMF_Yedek") / ad)
        for ad in (
            "pemf_patients_20261009_0300.db",
            "pemf_treatment_history_20261009_0300.db",
            "kurtarma-zarfi.enc",
            "OKU-KURTARMA.txt",
        )
    ]
    y["ortam"] = [
        yaz(Path("F/Yedek2") / ad)
        for ad in ("pemf_patients_20261008_0300.db", "pemf_treatment_history_20261008_0300.db")
    ]
    y["gecici"] = [yaz(Path(t) / "PEMF_GUI" / "logs" / "backend.log").parents[1] for t in _GECICI]
    return y


def _kos(
    tmp_path: Path,
    *,
    hasta: bool = True,
    ortam: bool = True,
    servis: bool = True,
    kayit: bool = True,
    kanit: bool = False,
) -> dict:
    kok = tmp_path / "kok"
    y = {} if kanit else _agac(kok, kayit=kayit)
    aparat = tmp_path / "aparat.ps1"
    aparat.write_text(_APARAT, encoding="utf-8-sig")
    kayit_dosyasi, cikti = tmp_path / "golge.jsonl", tmp_path / "cikti.json"
    arg = [_PWSH, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(aparat), "-Kok", str(kok),
           "-Betik", str(TEARDOWN), "-Kayit", str(kayit_dosyasi), "-Cikti", str(cikti)]  # fmt: skip
    if kanit:
        arg.append("-YalnizKanit")
    else:
        if hasta:
            arg.append("-IncludePatientData")
        if ortam:
            arg += ["-OrtamYedek", str(y["ortam_dizin"])]
        if servis:
            arg += ["-ServisYedek", str(y["servis_dizin"])]
    p = subprocess.run(arg, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
    assert p.returncode == 0 and cikti.exists(), (
        f"aparat düştü (rc={p.returncode}):\n{p.stdout[-2000:]}\n{p.stderr[-2000:]}"
    )
    s = json.loads(cikti.read_text(encoding="utf-8-sig"))
    s["kayitlar"] = [json.loads(ln) for ln in kayit_dosyasi.read_text(encoding="utf-8-sig").splitlines() if ln.strip()]
    s["engel"] = [r for r in s["kayitlar"] if r["olay"].startswith("ENGEL")]
    s["agac"] = y
    if not kanit:
        # sonuc dizisinin SON öğesi işlevin dönüşü (araya karışan çıktı varsa önce gelir)
        s["donus"] = s["sonuc"][-1] if s["sonuc"] else None
    return s


def _satirlar(log: list[str], parca: str) -> list[str]:
    return [ln for ln in log if parca in ln]


def test_ARAC_golge_aparati_KOK_DISI_silme_ve_yazmayi_REDDEDER_kayitcilari_GOLGELER_D2E04(tmp_path):
    """Koşumdan ÖNCE: kök dışı silme + `HKCU:` silmesi + kök dışı yazma REDDEDİLİR, kök içi silme yapılır; kasa/görev/servis komutları işlevdir."""
    s = _kos(tmp_path, kanit=True)
    assert s["disarisi_duruyor"] and s["iceri_silindi"] and s["disariya_yazilmadi"], s
    assert s["sc_rc"] == 1 and s["abs_yol_kokte"], s
    assert all(t.endswith("=Function") for t in s["komut_turleri"]), s["komut_turleri"]
    reddedilen = [str(r["ayrinti"]) for r in s["engel"]]
    assert any("DISARIDA_SILINMEMELI" in r for r in reddedilen) and any("HKCU:" in r for r in reddedilen), reddedilen
    assert any("DISARIYA_YAZILMAMALI" in r for r in reddedilen), reddedilen
    assert all(str(k).startswith(str(tmp_path / "kok")) for k in s["profil_kokleri"]), s["profil_kokleri"]


def test_KRITIK_tam_temizlik_MAKINE_DISI_yedege_DOKUNMAZ_yerini_ve_durumunu_SOYLER_D2E04(tmp_path):
    s = _kos(tmp_path)
    y, log = s["agac"], s["log"]
    silinen = [str(p) for p in y["disari"] + y["ortam"] if not p.exists()]
    assert not silinen, f"tam temizlik MAKİNE DIŞI yedeği sildi (A-45): {silinen}"
    assert not s["engel"], f"gölge koşumda kök dışı işlem denendi: {s['engel']}"
    e = _satirlar(log, str(y["disari_dizin"]))
    assert len(e) == 1 and "DURUYOR" in e[0] and "4 dosya" in e[0] and "kurtarma-zarfi.enc VAR" in e[0], (
        f"rapor launcher kaydındaki (backup_dir.txt) makine dışı yedeğin yerini/durumunu SÖYLEMİYOR: {e}\n"
        + "\n".join(log)
    )
    f = _satirlar(log, str(y["ortam_dizin"]))
    assert len(f) == 1 and "2 dosya" in f[0] and "kurtarma-zarfi.enc YOK" in f[0], (
        f"makine ortamındaki PEMF_BACKUP_DIR raporlanmadı: {f}"
    )
    g = _satirlar(log, str(y["servis_dizin"]))
    assert len(g) == 1 and "ERİŞİLEMİYOR" in g[0], f"servis ortamındaki erişilemeyen hedef raporlanmadı: {g}"
    son = log[-1]
    assert "HASTA VERİSİ DE SİLİNDİ" not in son and "BU MAKİNEDEN SİLİNDİ" in son and "DURUYOR" in son, (
        f"son satır makinede doğrulanandan fazlasını söylüyor (A-44): {son!r}"
    )
    assert s["donus"] is True and not y["hasta_db"].exists(), s


def test_KARSIT_tam_temizlik_YEREL_yedek_ve_yerel_zarfi_SILER_D2E04(tmp_path):
    """A-45 yalnız MAKİNE DIŞINI korur: veri kökündeki yedekler ve yanlarındaki zarf hasta verisidir, silinir ve doğrulanır."""
    s = _kos(tmp_path)
    y = s["agac"]
    assert not y["yerel_yedek"].exists() and not y["yerel_zarf"].exists(), "yerel yedek/zarf tam temizlikte kaldı"
    assert _satirlar(s["log"], "silindi (HASTA-VERİSİ)"), s["log"]


def test_KRITIK_Y85_jeton_defteri_YALNIZ_tam_temizlikte_silinir_ve_DOGRULANIR_D2E04(tmp_path):
    s = _kos(tmp_path / "tam")
    assert not s["agac"]["jeton"].exists(), "tam temizlik jeton_bekleyen.json'ı bıraktı (Y85)"
    assert [ln for ln in s["log"] if "silindi (HASTA-VERİSİ)" in ln and ln.endswith("jeton_bekleyen.json")], (
        "jeton defterinin silindiği DOĞRULANARAK raporlanmadı:\n" + "\n".join(s["log"])
    )
    sade = _kos(tmp_path / "sade", hasta=False)
    assert sade["agac"]["jeton"].exists(), (
        "sıradan kaldırma jeton defterini SİLDİ (faturalanmamış tüketim kaybolur — Y85)"
    )


def test_KRITIK_Y99_gecici_dizine_dusen_gunlukler_TAM_temizlikte_SILINIR_sade_kaldirmada_KALIR_D2E04(tmp_path):
    s = _kos(tmp_path / "tam")
    kalan = [str(t) for t in s["agac"]["gecici"] if t.exists()]
    assert not kalan, f"tam temizlik %TEMP%\\PEMF_GUI günlüklerini bıraktı (Y99): {kalan}"
    sade = _kos(tmp_path / "sade", hasta=False)
    assert all(t.exists() for t in sade["agac"]["gecici"]), "sıradan kaldırma KVKK günlüklerini sildi"


def test_KRITIK_sade_kaldirma_da_yedek_YERINI_kaydi_SILINMEDEN_once_okur_ve_RAPORLAR_D2E04(tmp_path):
    """Sıradan kaldırma (`-Scope all`, bayraksız) kurulum kökünü — yerin TEK kaydı backup_dir.txt ile — siler; rapor yeri yine söyler."""
    s = _kos(tmp_path, hasta=False)
    y = s["agac"]
    assert not y["kayit"].exists(), "aparat: kayıt dosyası silinmedi, kol anlamsız"
    e = _satirlar(s["log"], str(y["disari_dizin"]))
    assert len(e) == 1 and "DURUYOR" in e[0], f"kaydı silinen makine dışı yedeğin yeri raporda YOK: {s['log']}"
    assert "KORUNDU" in s["log"][-1] and y["hasta_db"].exists(), s["log"][-1]


def test_KRITIK_kayit_OKUNAMAZSA_yedek_yeri_BILINMIYOR_der_D2E04(tmp_path):
    import msvcrt

    kok = tmp_path / "kok"
    y = _agac(kok)
    boyut = y["kayit"].stat().st_size
    with open(y["kayit"], "rb+") as fh:
        msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, boyut)
        try:
            s = _kos_hazir(tmp_path, y)
        finally:
            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, boyut)
    satir = [ln for ln in s["log"] if "BİLİNMİYOR" in ln and str(y["kayit"]) in ln]
    assert len(satir) == 1, "okunamayan yedek kaydı için 'yedek yeri bilinmiyor' denmedi:\n" + "\n".join(s["log"])


def _kos_hazir(tmp_path: Path, y: dict) -> dict:
    """Ağaç ZATEN kurulu (kilit testi): yalnız aparatı koşturur."""
    kok = tmp_path / "kok"
    aparat = tmp_path / "aparat.ps1"
    aparat.write_text(_APARAT, encoding="utf-8-sig")
    kayit_dosyasi, cikti = tmp_path / "golge.jsonl", tmp_path / "cikti.json"
    arg = [_PWSH, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(aparat), "-Kok", str(kok),
           "-Betik", str(TEARDOWN), "-Kayit", str(kayit_dosyasi), "-Cikti", str(cikti), "-IncludePatientData"]  # fmt: skip
    p = subprocess.run(arg, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
    assert p.returncode == 0 and cikti.exists(), (
        f"aparat düştü (rc={p.returncode}):\n{p.stdout[-2000:]}\n{p.stderr[-2000:]}"
    )
    s = json.loads(cikti.read_text(encoding="utf-8-sig"))
    s["agac"] = y
    return s


def test_KRITIK_kayitli_hedef_YOKSA_son_satir_yalniz_BU_MAKINEYI_soyler_D2E04(tmp_path):
    s = _kos(tmp_path, kayit=False, ortam=False, servis=False)
    son = s["log"][-1]
    assert "BU MAKİNEDEN SİLİNDİ" in son and "kayıtlı makine dışı yedek hedefi yok" in son, son
