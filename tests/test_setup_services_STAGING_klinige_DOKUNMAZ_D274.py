# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D2.74 (B-9.7) — `setup_services.ps1 -Mode staging` klinik kurulumuna DOKUNMAZ: servis adı, NSSM log dizini ve güvenlik duvarı kuralı
kipe bağlı; kurulum ve kaldırma klinik `PemfBackend` servisini durdurmaz / silmez, klinik backend'ini öldürmez, klinik ACİL DURDUR'unu
göndermez; klinik kurulum dizininden koşulursa (varsayılan -AppDir = betiğin dizini) hiçbir şey değiştirmeden durur; footprint (tam
temizlik) staging servisini de tanır.

Kusur (1.9.50'de de VAR; setup_services sahadaki base-app.zip içinde): `$ServiceBackend = "PemfBackend"` SABİTTİ → tek saha
makinesinde `-Mode staging` klinik servisini durdurup SİLİYOR, yerine `PEMF_SIMULATE=1` + başka veri kökü (C:\\ProgramData\\PEMF_Staging)
koyuyordu: hasta/seans geçmişi "kaybolmuş" görünür, bobin sürülmez, seanslar simülasyonda kaydedilir. Zorla-öldürme ADINA göre TÜM
`PEMF_Backend` süreçlerini (klinik dahil) öldürüyor; güvenlik duvarı API kuralı SABİT 8000 (staging 8010'u açmıyordu); kaldırma ise
klinik ACİL DURDUR'u (8000) + birleşik teardown'ı (klinik servisleri / kökleri) çağırıyordu.

⛔ Betik GERÇEKTEN koşmaz. Aparat üst düzey ifadeleri sırayla dolaşır: YALNIZ izin listesindeki komutlardan oluşanlar koşar (indirme,
dosya yazımı, `icacls`, sağlık sondası … ATLANIR). Yan etkili çağrılar KAYITÇIDIR: `& $NssmExe` ifade metninde `Nssm-Kayit`e
yönlendirilir; `Get-Service` (klinik + staging servisi "var"), `Get-CimInstance` / `Get-Process` (iki sahte backend süreci: KLİNİK kurulum
dizininde 101, bu kurulumda 202; `Stop-Process` öldüreni tablodan siler), `Get-ItemProperty` (klinik servisinin NSSM `Application`ı KLİNİK
dizinde), güvenlik duvarı, ACİL DURDUR ve teardown kayıtçıdır. `exit N` (iç içe olanlar dahil) ifade metninde "çıkış kodunu kaydet + dön"e
çevrilir ve koşum orada BİTER. Kaldırma senaryosunda koşulu doğru olan kaldırma dalının gövdesi koşar. `$AppDir` klon TEMP'indeki sahte
dizindir; "ortak" senaryolarda klinik dizinin TA KENDİSİDİR.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import capraz
import pytest

KOK = Path(__file__).resolve().parents[1]
SETUP = KOK / "scripts" / "setup_services.ps1"
FOOTPRINT = KOK / "scripts" / "pemf_footprint.ps1"
_PWSH = shutil.which("pwsh")

pytestmark = [
    pytest.mark.skipif(sys.platform != "win32", reason="pwsh aparatı Windows betik anlamını ölçer"),
    pytest.mark.skipif((_PWSH is None) and not capraz.ZORUNLU, reason="pwsh (PowerShell 7) bulunamadı"),
]

_APARAT = r"""
param([string]$Setup, [string]$Footprint, [string]$App, [string]$Klinik, [string]$Senaryo, [string]$Cikti)
$ErrorActionPreference = 'Stop'
$script:Kayit = [System.Collections.Generic.List[string]]::new()
$script:Atlanan = 0
$script:CikisKodu = $null
$script:Servis = @{ 'PemfBackend' = 'Running'; 'PemfBackendStaging' = 'Running' }
$script:Canli = [System.Collections.Generic.List[int]]::new(); $script:Canli.Add(101); $script:Canli.Add(202)
function K([string]$m) { $script:Kayit.Add($m) }
function Log { param($m, $c) K ("LOG " + $m) }
function Write-Host { }
function Out-Null { param([Parameter(ValueFromPipeline = $true)]$x) process { } }
function Start-Sleep { }
function Set-Location { }
function Nssm-Kayit {
    $a = @($args | Where-Object { "$_" -notmatch '^\*?>' })
    K ("nssm " + ($a -join ' '))
    if ($a[0] -eq 'stop') { $script:Servis[[string]$a[1]] = 'Stopped' }
    if ($a[0] -eq 'remove') { $script:Servis.Remove([string]$a[1]) }
    $global:LASTEXITCODE = 0
}
function Get-Service { param([string]$Name, $ErrorAction)
    if ($script:Servis.ContainsKey($Name)) { [pscustomobject]@{ Name = $Name; Status = $script:Servis[$Name] } } }
function Get-CimInstance { param($ClassName, $Filter, $ErrorAction)
    if ($script:Canli.Contains(101)) { [pscustomobject]@{ ProcessId = 101; Name = 'PEMF_Backend.exe'; ExecutablePath = (Join-Path $Klinik 'PEMF_Backend.exe') } }
    if ($script:Canli.Contains(202)) { [pscustomobject]@{ ProcessId = 202; Name = 'PEMF_Backend.exe'; ExecutablePath = (Join-Path $App 'PEMF_Backend.exe') } } }
# [Parameter] öznitelikli kayıtçılar gelişmiş işlevdir: -ErrorAction ortak parametredir, ayrıca BİLDİRİLMEZ.
function Get-Process { param([Parameter(Position = 0)][string[]]$Name)
    if ($Name -contains 'PEMF_Backend') { foreach ($p in @($script:Canli)) { [pscustomobject]@{ Id = $p; Name = 'PEMF_Backend' } } } }
function Stop-Process { param([Parameter(ValueFromPipeline = $true)]$InputObject, $Id, [switch]$Force)
    process {
        $p = $(if ($Id) { [int]$Id } elseif ($InputObject) { [int]$InputObject.Id } else { $null })
        if ($null -ne $p) { K ("Stop-Process " + $p); [void]$script:Canli.Remove($p) }
    } }
function Get-ItemProperty { param($LiteralPath, $Path, $Name, $ErrorAction)
    if ("$LiteralPath$Path" -like '*\Services\PemfBackend\Parameters') { [pscustomobject]@{ Application = (Join-Path $Klinik 'PEMF_Backend.exe') } } }
function Get-NetFirewallRule { param($DisplayName, $ErrorAction) }
function New-NetFirewallRule { param($DisplayName, $Direction, $Program, $Action, $Protocol, $LocalPort, $Profile, $ErrorAction)
    K ("FW-YENI " + $DisplayName + " " + $Protocol + " " + $LocalPort) }
function Remove-NetFirewallRule { param($DisplayName, $ErrorAction) K ("FW-SIL " + $DisplayName) }
# İG-9.5 artığı: kural artık İÇERİKLE doğrulanır (port / program filtresi) → filtre gölgeleri de izinli (aparat izin listesi dersi).
function Get-NetFirewallPortFilter { param([Parameter(ValueFromPipeline = $true)]$InputObject) process { } }
function Get-NetFirewallApplicationFilter { param([Parameter(ValueFromPipeline = $true)]$InputObject) process { } }
function Send-PemfAcilDurdur { K 'ACIL-DURDUR'; 1 }
function Invoke-PemfTeardown { param($Scope, [switch]$IncludePatientData) K ("TEARDOWN " + $Scope); $true }
function Teardown-Yukle { }
function sc.exe { K ("sc.exe " + ($args -join ' ')) }
$izinli = [System.Collections.Generic.List[string]]@('K', 'Log', 'Write-Host', 'Out-Null', 'Start-Sleep', 'Set-Location', 'Nssm-Kayit',
    'Get-Service', 'Get-CimInstance', 'Get-Process', 'Stop-Process', 'Get-NetFirewallRule', 'New-NetFirewallRule', 'Remove-NetFirewallRule',
    'Get-NetFirewallPortFilter', 'Get-NetFirewallApplicationFilter',
    'Send-PemfAcilDurdur', 'Invoke-PemfTeardown', 'Teardown-Yukle', 'sc.exe', 'Join-Path', 'Split-Path', 'Test-Path', 'Where-Object',
    'Select-Object', 'ForEach-Object', 'Get-Content', 'Get-Date', 'Test-PemfApiPortDegeri', 'Get-PemfProfilEnvDosyasi', 'Read-PemfProfilEnv',
    'Stop-PemfKurulumBackendi', 'Stop-AppProcs', 'Get-ItemProperty',
    # D5 M-1: API / keşif kuralı işleve alındı (install_backend_service.ps1 ile birebir) — gövdesi saf değilse yüklenmez, döngü ATLANIR.
    'Ensure-PemfBackendFirewallKurali',
    # D3.07: at-rest doğrulaması işleve alındı (çağrı yeri koşulsuz) — gövdesi saf değilse (Invoke-RestMethod gölgesi yok) düşer.
    'Test-PemfAtRestDurumu')
# `exit N` → çıkış kodunu kaydet + betik bloğundan dön (iç içe if/for içindekiler dahil); döngü kayıt görünce DURUR.
function CikisiYakala($s) {
    $metin = $s.Extent.Text; $bas = $s.Extent.StartOffset
    $cikislar = @($s.FindAll({ param($n) $n -is [System.Management.Automation.Language.ExitStatementAst] }, $true))
    if ($s -is [System.Management.Automation.Language.ExitStatementAst] -and -not ($cikislar -contains $s)) { $cikislar += $s }
    foreach ($c in @($cikislar | Sort-Object { $_.Extent.StartOffset } -Descending)) {
        $kod = $(if ($c.Pipeline) { $c.Pipeline.Extent.Text } else { '0' })
        $i = $c.Extent.StartOffset - $bas
        $metin = $metin.Substring(0, $i) + "`$script:CikisKodu = [int]($kod); return" + $metin.Substring($i + $c.Extent.Text.Length)
    }
    $metin
}
function Donustur([string]$m) {
    $m = [regex]::Replace($m, '&\s*\$NssmExe\b', 'Nssm-Kayit')
    $m = [regex]::Replace($m, '(?m)^(\s*)\.\s+\$teardownScript\s*$', '$1Teardown-Yukle')
    # Dinamik betik bloğunda $MyInvocation.MyCommand.Path boştur → betiğin GERÇEK yolu (profil araması betik dizinine bakar).
    $m.Replace('$MyInvocation.MyCommand.Path', "'" + $Setup + "'")
}
function Saf([string]$m) {
    $t = $null; $e = $null
    $a = [System.Management.Automation.Language.Parser]::ParseInput($m, [ref]$t, [ref]$e)
    if ($e) { return $false }
    if ($a.Find({ param($n) $n -is [System.Management.Automation.Language.ExitStatementAst] }, $true)) { return $false }
    foreach ($c in $a.FindAll({ param($n) $n -is [System.Management.Automation.Language.CommandAst] }, $true)) {
        $ad = $c.GetCommandName()
        if (-not $ad -or -not $izinli.Contains($ad)) { return $false }
    }
    $true
}
$t = $null; $e = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($Setup, [ref]$t, [ref]$e)
if ($e) { [Console]::Out.WriteLine("APARAT_HATASI parse"); exit 3 }
$sonuc = [ordered]@{}
if ($Senaryo -eq 'footprint') {
    . $Footprint
    $sonuc.servisler = @((Get-PemfFootprint).Services)
    ConvertTo-Json -InputObject $sonuc -Depth 4 | Set-Content -LiteralPath $Cikti -Encoding UTF8
    exit 0
}
# Betik işlevleri: gövdesi (dönüştürülmüş) saf olanlar yüklenir; olmayanlar kayıtçıyı GÖLGELEMEZ ve izin listesinden düşer.
foreach ($f in $ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] }, $false)) {
    if ($f.Name -eq 'Log') { continue }
    $metin = Donustur $f.Extent.Text
    if (Saf $metin) { . ([ScriptBlock]::Create($metin)) } else { [void]$izinli.Remove($f.Name) }
}
$Mode = $(if ($Senaryo -like '*staging*') { 'staging' } else { 'device' })
$Uninstall = [switch]($Senaryo -like 'kaldirma*'); $PurgeData = [switch]$false
$AppDir = $App; $NssmExe = Join-Path $App '_internal\bin\nssm\nssm.exe'
$korunan = 'AppDir', 'NssmExe', 'Mode', 'Uninstall', 'PurgeData', 'ErrorActionPreference'
function Kos($s) {
    if ($s -is [System.Management.Automation.Language.FunctionDefinitionAst]) {
        $metin = Donustur $s.Extent.Text
        if (Saf $metin) { . ([ScriptBlock]::Create($metin)) }
        return
    }
    if ($s -is [System.Management.Automation.Language.AssignmentStatementAst] -and $korunan -contains $s.Left.Extent.Text.TrimStart('$')) { return }
    $metin = Donustur (CikisiYakala $s)
    if (-not (Saf $metin)) { $script:Atlanan++; return }
    . ([ScriptBlock]::Create($metin))
}
$bitti = $false
foreach ($s in @($ast.EndBlock.Statements)) {
    if ($s -is [System.Management.Automation.Language.FunctionDefinitionAst]) { continue }
    if ($s -is [System.Management.Automation.Language.IfStatementAst] -and $s.Clauses[0].Item1.Extent.Text -match '^\$Uninstall\b') {
        if ($Uninstall -and (Invoke-Expression $s.Clauses[0].Item1.Extent.Text)) {
            $bitti = $true
            foreach ($g in $s.Clauses[0].Item2.Statements) {
                . Kos $g
                if ($null -ne $script:CikisKodu) { break }
            }
            break
        }
        continue
    }
    . Kos $s
    if ($null -ne $script:CikisKodu) { break }
}
$sonuc.kayit = @($script:Kayit)
$sonuc.atlanan = $script:Atlanan
$sonuc.cikis = $script:CikisKodu
$sonuc.servis = $ServiceBackend
$sonuc.logdir = $LogDir
$sonuc.kaldirma_dali_kostu = $bitti
ConvertTo-Json -InputObject $sonuc -Depth 4 | Set-Content -LiteralPath $Cikti -Encoding UTF8
exit 0
"""


def _kos(tmp_path: Path, senaryo: str, ortak: bool = False) -> dict:
    app = tmp_path / "PEMF_Staging_App"
    klinik = app if ortak else tmp_path / "Program Files" / "PEMF Backend"
    for yol in (app / "_internal" / "bin" / "nssm", app / "deploy", klinik):
        yol.mkdir(parents=True, exist_ok=True)
    for bos in (app / "_internal" / "bin" / "nssm" / "nssm.exe", app / "PEMF_Backend.exe", app / "pemf_teardown.ps1"):
        bos.write_bytes(b"")
    for profil in ("staging.env", "device.env"):
        shutil.copy2(KOK / "deploy" / profil, app / "deploy" / profil)
    aparat = tmp_path / "aparat.ps1"
    aparat.write_text(_APARAT, encoding="utf-8-sig")
    cikti = tmp_path / "cikti.json"
    p = subprocess.run(
        [_PWSH, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(aparat),
         "-Setup", str(SETUP), "-Footprint", str(FOOTPRINT), "-App", str(app), "-Klinik", str(klinik),
         "-Senaryo", senaryo, "-Cikti", str(cikti)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180,
    )  # fmt: skip
    assert p.returncode == 0 and cikti.exists(), (
        f"aparat düştü (rc={p.returncode}):\n{p.stdout[-1500:]}\n{p.stderr[-1500:]}"
    )
    return json.loads(cikti.read_text(encoding="utf-8-sig"))


def _klinige_dokunan(kayit: list[str]) -> list[str]:
    return [
        k
        for k in kayit
        if re.match(r"nssm (stop|remove|install|set|start) PemfBackend(\s|$)", k)
        or k == "Stop-Process 101"
        or k in ("ACIL-DURDUR",)
        or k.startswith("TEARDOWN")
    ]


def test_KRITIK_staging_KURULUMU_klinik_servisine_ve_surecine_DOKUNMAZ_ad_ve_port_KIPE_bagli_D274(tmp_path):
    s = _kos(tmp_path, "kurulum_staging")
    k = s["kayit"]
    assert not _klinige_dokunan(k), f"-Mode staging KLİNİK kurulumuna dokundu: {_klinige_dokunan(k)}"
    assert any(x.startswith("nssm install PemfBackendStaging ") for x in k), f"staging servisi ayrı adla kurulmadı: {k}"
    assert [x for x in k if x.startswith("Stop-Process")] == ["Stop-Process 202"], (
        "zorla-öldürme yalnız bu kurulumun süreci değil"
    )
    fw = [x for x in k if x.startswith("FW-YENI")]
    assert fw == ["FW-YENI PEMF Backend API (staging) TCP 8010"], (
        f"staging güvenlik duvarı kuralı kipe/porta bağlı değil: {fw}"
    )
    assert s["logdir"] == _staging_env()["PEMF_LOG_DIR"], (
        f"NSSM log dizini staging profiliyle aynı değil: {s['logdir']}"
    )


def test_KRITIK_staging_KALDIRMASI_klinik_ACIL_DURDUR_teardown_ve_surecine_DOKUNMAZ_D274(tmp_path):
    s = _kos(tmp_path, "kaldirma_staging")
    k = s["kayit"]
    assert s["kaldirma_dali_kostu"] and s["cikis"] == 0, f"aparat: kaldırma dalı koşmadı / çıkmadı: {s}"
    assert not _klinige_dokunan(k), f"staging KALDIRMASI klinik kurulumuna dokundu: {_klinige_dokunan(k)}"
    assert "nssm remove PemfBackendStaging confirm" in k and "FW-SIL PEMF Backend API (staging)" in k, k
    assert [x for x in k if x.startswith("Stop-Process")] == ["Stop-Process 202"], k


def _ortak_dizin_reddi(s: dict) -> None:
    k = s["kayit"]
    assert s["cikis"] == 1, f"klinik kurulum dizininden staging DURMADI (çıkış={s['cikis']}): {k}"
    assert [x for x in k if not x.startswith("LOG ")] == [], f"staging klinik dizininde DEĞİŞİKLİK yaptı: {k}"
    assert any("KLİNİK servisinin" in x for x in k), f"ret nedeni günlüğe yazılmadı: {k}"


def test_KRITIK_staging_KURULUMU_klinik_kurulum_DIZININDEN_hicbir_sey_degistirmeden_DURUR_D274(tmp_path):
    """-AppDir verilmezse betiğin KENDİ dizini kullanılır: klinik kurulumundaki kopyayla `-Mode staging` → {app} süreç temizliği
    klinik backend'ini (aynı dizin) ACİL DURDUR'suz öldürürdü."""
    _ortak_dizin_reddi(_kos(tmp_path, "kurulum_staging_ortak", ortak=True))


def test_KRITIK_staging_KALDIRMASI_klinik_kurulum_DIZININDEN_hicbir_sey_degistirmeden_DURUR_D274(tmp_path):
    _ortak_dizin_reddi(_kos(tmp_path, "kaldirma_staging_ortak", ortak=True))


def test_KRITIK_klinik_kurulumu_da_BASKA_kurulumun_backendini_OLDURMEZ_D274(tmp_path):
    """Zorla-öldürme kuralı kipten bağımsız: klinik (device) yeniden kurulumu da yalnız KENDİ dizinindeki backend'i öldürür."""
    k = _kos(tmp_path, "kurulum_device")["kayit"]
    assert [x for x in k if x.startswith("Stop-Process")] == ["Stop-Process 202"], k


def test_KARSIT_klinik_kurulumu_PemfBackend_8000_ve_kesif_5051_D274(tmp_path):
    s = _kos(tmp_path, "kurulum_device")
    k = s["kayit"]
    assert s["servis"] == "PemfBackend" and any(x.startswith("nssm install PemfBackend ") for x in k), k
    assert [x for x in k if x.startswith("FW-YENI")] == [
        "FW-YENI PEMF Backend API TCP 8000",
        "FW-YENI PEMF UDP Discovery UDP 5051",
    ], k


def test_KARSIT_klinik_KALDIRMASI_once_ACIL_DURDUR_sonra_teardown_D274(tmp_path):
    s = _kos(tmp_path, "kaldirma_device")
    k = s["kayit"]
    assert s["cikis"] == 0 and "ACIL-DURDUR" in k and "TEARDOWN backend" in k, s
    ilk_oldurme = next((i for i, x in enumerate(k) if x.startswith("Stop-Process")), len(k))
    assert k.index("ACIL-DURDUR") < ilk_oldurme, f"bobin STOP'u öldürmeden ÖNCE değil: {k}"


def test_KRITIK_tam_temizlik_STAGING_servisini_de_tanir_D274(tmp_path):
    assert "PemfBackendStaging" in _kos(tmp_path, "footprint")["servisler"], "footprint staging servisini tanımıyor"


def _staging_env() -> dict:
    d = {}
    for ln in (KOK / "deploy" / "staging.env").read_text(encoding="utf-8").splitlines():
        t = ln.strip()
        if t and not t.startswith("#") and "=" in t:
            a, b = t.split("=", 1)
            d[a.strip()] = b.strip()
    return d
