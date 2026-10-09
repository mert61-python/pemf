# Author: mertaygn, cglrgrkn
"""D1.44 · B-10.24 · B-10.68 + D1.45 · B-10.25 · B-10.28 — kurulum/kaldırma betikleri pwsh'ta DAVRANIŞLA.

D1.44 (`scripts/setup_services.ps1` env + NSSM bloğu): kapılar metin aramasıydı — `PEMF_ALLOWED_HOSTS`
ayrıştırmadan düşse (servis `*` host ile açılır), ayrıştırıcı `Contains('==')` olsa (servis PEMF_DATA_DIR /
ENCRYPT_AT_REST olmadan açılır), ikinci bir `AppStopMethodConsole 1500` satırı eklense (NSSM graceful bobin
STOP'undan önce öldürür; mevcut kapı İLK eşleşmeye bakıyordu) YEŞİL kalıyordu. Bu kapı bloğu (yalnız o
ifadeler, AST'den) sahte `nssm` ile KOŞTURUR ve kaydedilen argümanları ölçer.

D1.45 (`scripts/pemf_teardown.ps1`): KVKK varsayılan koruma filtresi, servis durdurma sırası (broker EN SON)
ve orkestratörün kasa silmelerini yalnız `-IncludePatientData` ile yapması — hepsi yorum/metin kapısındaydı.

⛔ GÜVENLİK (görev kuralı): gerçek betik DOT-SOURCE EDİLMEZ. Yalnız izin listesindeki fonksiyonlar AST'den
tek tek tanımlanır; kimlik fonksiyonları (`Remove-PemfCredentials`, `Remove-PemfSystemCredentials` — ikincisi
`schtasks`'ı TAM YOLLA çağırdığı için gölgelenemez) HİÇ yüklenmez, kayıtçıyla değiştirilir. `sc.exe`, `cmdkey`,
`schtasks`, `nssm`, `icacls`, `Remove-Item`, `Stop-Service`, `Stop-Process`, `Get-Process`, `Get-Service`,
`Start-Sleep` FONKSİYONLA gölgelenir; çağrıdan ÖNCE kanarya her adın `Function` olarak çözüldüğünü doğrular,
tutmazsa hiçbir şey çağrılmadan çıkılır (çıkış 3). Yalnız geçici köklerde sahte footprint. Yönetici yetkisi
kullanılmaz. Gerçek servis, güvenlik duvarı, görev zamanlayıcı ve kimlik kasası DEĞİŞMEZ (oturum, her koşudan
önce/sonra `cmdkey` PEMF sayısını, servis ve kural sayılarını ölçer).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
TEARDOWN = KOK / "scripts" / "pemf_teardown.ps1"
SETUP = KOK / "scripts" / "setup_services.ps1"
DEVICE_ENV = KOK / "deploy" / "device.env"
_PWSH = shutil.which("pwsh")

pytestmark = [
    pytest.mark.skipif(sys.platform != "win32", reason="pwsh aparatı Windows betik anlamını ölçer"),
    pytest.mark.skipif(_PWSH is None, reason="pwsh (PowerShell 7) bulunamadı"),
]

_APARAT = r"""
param([string]$Teardown, [string]$Setup, [string]$Kok, [string]$Senaryo, [string]$Cikti, [int]$Bekleme = 0)
$ErrorActionPreference = 'Stop'
$script:Kayit = [System.Collections.Generic.List[string]]::new()
function K([string]$s) { $script:Kayit.Add($s) }

# ── 1) GÖLGELER: önce tanımlanır; komut çözümlemesi fonksiyonu uygulamadan ÖNCE bulur ──
# Servis durumu GERÇEKÇİ: `sc stop`/`nssm stop` servisi StopPending yapar; $Bekleme yoklamadan sonra Stopped
# (-1 = hiç durmaz). 1-B inceleme i5: gölge servisi ANINDA Stopped yaptığından bekleme döngüsü hiç sınanmıyordu.
$script:Servis = @{}; $script:Kalan = @{}; $script:Olduruldu = $false
function Durdur([string]$ad) {
    if (-not $script:Servis.ContainsKey($ad)) { return }
    if ($Bekleme -eq 0) { $script:Servis[$ad] = 'Stopped' } else { $script:Servis[$ad] = 'StopPending'; $script:Kalan[$ad] = $Bekleme }
}
function sc.exe { K ("sc " + ($args -join ' ')); if ($args[0] -eq 'stop') { Durdur $args[1] } elseif ($args[0] -eq 'delete') { $script:Servis.Remove($args[1]) }; $global:LASTEXITCODE = 0 }
function sc { sc.exe @args }
function cmdkey { K ("cmdkey " + ($args -join ' ')); $global:LASTEXITCODE = 0 }
function cmdkey.exe { cmdkey @args }
function schtasks { K ("schtasks " + ($args -join ' ')); $global:LASTEXITCODE = 0 }
function schtasks.exe { schtasks @args }
function nssm {
    K ("nssm " + ($args -join ' ')); K ("nssm_json " + (ConvertTo-Json -Compress -InputObject @($args | ForEach-Object { [string]$_ })))
    if ($args[0] -eq 'stop') { Durdur $args[1] } elseif ($args[0] -eq 'remove') { $script:Servis.Remove($args[1]) }
    $global:LASTEXITCODE = 0
}
function nssm.exe { nssm @args }
function icacls { K ("icacls " + ($args -join ' ')); $global:LASTEXITCODE = 0 }
function icacls.exe { icacls @args }
function Stop-Service { [CmdletBinding()] param([Parameter(ValueFromRemainingArguments = $true)]$R) K ("Stop-Service " + ($R -join ' ')) }
function Remove-Item { [CmdletBinding()] param([string]$LiteralPath, [string]$Path, [switch]$Recurse, [switch]$Force) K ("Remove-Item " + $LiteralPath + $Path) }
function Stop-Process { [CmdletBinding()] param([Parameter(ValueFromPipeline = $true)]$InputObject, $Id, [switch]$Force) K "Stop-Process"; $script:Olduruldu = $true }
# D2.74: kaldırma bloğunun staging dalı kendi güvenlik duvarı kuralını siler — gerçek kural silinmez, kayıtçı.
function Remove-NetFirewallRule { [CmdletBinding()] param([string]$DisplayName) K ("FW-SIL " + $DisplayName) }
# Öldürülene kadar bir SAHTE süreç "yaşar" (kill döngüleri en az bir tur dönsün); gerçek süreç listesi okunmaz.
function Get-Process { [CmdletBinding()] param([Parameter(ValueFromRemainingArguments = $true)]$R) if (-not $script:Olduruldu) { [pscustomobject]@{ Name = 'SAHTE_PEMF_Backend'; Id = -1 } } }
function Get-CimInstance { [CmdletBinding()] param([Parameter(ValueFromRemainingArguments = $true)]$R) K "CIM"; @() }
function Set-Location { [CmdletBinding()] param([Parameter(ValueFromRemainingArguments = $true)]$R) K "Set-Location" }
function Start-Sleep { [CmdletBinding()] param([Parameter(ValueFromRemainingArguments = $true)]$R) K "SLEEP" }
# D1.92/D1.93: ACİL DURDUR isteği GERÇEK ağa ÇIKMAZ — kayıtçı. Davranış senaryodan: basari | hata | zaman.
$script:HttpDavranis = 'basari'; $script:AcikPortlar = @()
# O-7.1: porta göre YABANCI yerel servis yanıtı (2xx ama PEMF ACİL DURDUR yanıtı DEĞİL) — senaryo doldurur.
$script:YabanciPortlar = @{}
function Invoke-RestMethod {
    [CmdletBinding()] param([string]$Uri, [string]$Method, $TimeoutSec, [Parameter(ValueFromRemainingArguments = $true)]$R)
    K ("HTTP " + $Method + " " + $Uri)
    K ("HTTP-SURE " + $TimeoutSec)
    if ($script:HttpDavranis -eq 'hata') { throw "sahte: baglanti reddedildi" }
    if ($script:HttpDavranis -eq 'zaman') { throw [System.TimeoutException]::new("sahte: zaman asimi") }
    $port = ([uri]$Uri).Port
    if ($script:YabanciPortlar.ContainsKey($port)) { return $script:YabanciPortlar[$port] }
    # O-13.1 (1-H): GERÇEK `_emergency_stop_all` yanıtının şekli — status + confirmed + stmStopped + mqttResults.
    [pscustomobject]@{ status = 'success'; confirmed = $true; stmStopped = $true; mqttResults = @() }
}
function Invoke-WebRequest { [CmdletBinding()] param([Parameter(ValueFromRemainingArguments = $true)]$R) K "HTTP-IWR"; throw "sahte: IWR kullanilmamali" }
function Get-Service {
    [CmdletBinding()] param([string]$Name)
    if (-not $script:Servis.ContainsKey($Name)) { K ("GS " + $Name + " YOK"); return }
    if ($script:Servis[$Name] -eq 'StopPending' -and $Bekleme -gt 0) {
        if ($script:Kalan[$Name] -gt 0) { $script:Kalan[$Name]-- } else { $script:Servis[$Name] = 'Stopped' }
    }
    K ("GS " + $Name + " " + $script:Servis[$Name])
    [pscustomobject]@{ Name = $Name; Status = $script:Servis[$Name] }
}
$golgeler = 'sc.exe','sc','cmdkey','cmdkey.exe','schtasks','schtasks.exe','nssm','nssm.exe','icacls','icacls.exe','Stop-Service','Remove-Item','Stop-Process','Get-Process','Start-Sleep','Get-Service','Get-CimInstance','Set-Location','Invoke-RestMethod','Invoke-WebRequest','Remove-NetFirewallRule'
foreach ($ad in $golgeler) {
    $c = Get-Command $ad -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $c -or $c.CommandType -ne 'Function') { [Console]::Out.WriteLine("APARAT_HATASI golgelenemedi: $ad"); exit 3 }
}
& sc.exe query KANARYA; & cmdkey /list:KANARYA
if ($script:Kayit.Count -ne 2) { [Console]::Out.WriteLine("APARAT_HATASI kanarya kaydedilmedi"); exit 3 }
$script:Kayit.Clear()

# ── 1b) İZİN LİSTESİ (1-B inceleme i5): yüklenen gerçek koddaki HER komut ya gölge, ya kayıtçı, ya yüklenen
# fonksiyon, ya da salt-okur yerleşik olmalı. Gölge listesi bir YASAK listesi gibi çalışıyordu: fonksiyona
# `taskkill.exe`, tam yollu `sc.exe` ya da `[Diagnostics.Process]::…Kill()` eklense test GERÇEK süreçleri
# öldürürdü. Denetim KOŞTURMADAN ÖNCE yapılır; ihlalde hiçbir şey çağrılmadan çıkılır (çıkış 3).
$kayitcilar = 'Write-PemfLog','Remove-PemfCredentials','Remove-PemfSystemCredentials','Remove-PemfTasks','Remove-PemfFirewall','Remove-PemfEnv','Remove-PemfRegistry','Get-PemfProfileRoots','Get-PemfFootprint','Log','Invoke-PemfTeardown','Test-PemfPortAcik','Get-PemfMakineDisiYedekHedefleri','Write-PemfMakineDisiYedekRaporu'
$yuklenenler = 'Test-PemfScope','Assert-PemfRemoved','Remove-PemfPaths','Stop-PemfProcessesAndServices','Invoke-PemfTeardown','Stop-AppProcs','Send-PemfAcilDurdur','Get-PemfBackendPortAdaylari','Invoke-PemfAcilDurdurIstegi','Get-PemfProfilEnvDosyasi','Read-PemfProfilEnv'
$salt_okur = 'Test-Path','Join-Path','Split-Path','Sort-Object','ForEach-Object','Where-Object','Select-Object','Get-Content'
$izinli = @($golgeler) + $kayitcilar + $yuklenenler + $salt_okur
$izinli_degisken = 'NssmExe','teardownScript'
function Denetle($agac, [string]$ne) {
    foreach ($c in $agac.FindAll({ param($n) $n -is [System.Management.Automation.Language.CommandAst] }, $true)) {
        $ad = $c.GetCommandName()
        if ($ad) {
            if ($izinli -notcontains $ad) { [Console]::Out.WriteLine("APARAT_HATASI izin listesinde olmayan komut ($ne): $ad"); exit 3 }
        } else {
            $ilk = $c.CommandElements[0]
            if (-not ($ilk -is [System.Management.Automation.Language.VariableExpressionAst] -and $izinli_degisken -contains $ilk.VariablePath.UserPath)) {
                [Console]::Out.WriteLine("APARAT_HATASI dinamik komut ($ne): " + $ilk.Extent.Text); exit 3
            }
        }
    }
    foreach ($m in $agac.FindAll({ param($n) $n -is [System.Management.Automation.Language.InvokeMemberExpressionAst] }, $true)) {
        if ($m.Member.Extent.Text -match '^(Kill|Delete|Terminate|CredDelete|SetEnvironmentVariable|Remove|RemoveAll|Move|Stop|Start)$') {
            [Console]::Out.WriteLine("APARAT_HATASI tehlikeli uye cagrisi ($ne): " + $m.Extent.Text); exit 3
        }
        # 1-F inceleme: gölgelenen `Invoke-RestMethod`'u atlayan .NET AĞ çağrısı (D1.92 modüle TcpClient sondası getirdi).
        if ($m.Member.Extent.Text -match '^(Connect|ConnectAsync|BeginConnect|GetAsync|PostAsync|PutAsync|SendAsync|GetStringAsync|UploadString|UploadData|DownloadString|DownloadData|DownloadFile|OpenRead|OpenWrite|GetResponse|GetRequestStream)$') {
            [Console]::Out.WriteLine("APARAT_HATASI ag uye cagrisi ($ne): " + $m.Extent.Text); exit 3
        }
    }
    foreach ($t in $agac.FindAll({ param($n) $n -is [System.Management.Automation.Language.TypeExpressionAst] -or $n -is [System.Management.Automation.Language.TypeConstraintAst] }, $true)) {
        if ($t.TypeName.FullName -match '^(System\.)?Net\.') {
            [Console]::Out.WriteLine("APARAT_HATASI ag tipi ($ne): " + $t.Extent.Text); exit 3
        }
    }
}

# ── 2) GERÇEK fonksiyonlar YALNIZ izin listesinden, AST'den (dosya dot-source EDİLMEZ) ──
function Yukle([string]$Dosya, [string[]]$Adlar, [switch]$Varsa) {
    $t = $null; $e = $null
    $ast = [System.Management.Automation.Language.Parser]::ParseFile($Dosya, [ref]$t, [ref]$e)
    if ($e) { throw "parse hatasi: $Dosya" }
    foreach ($ad in $Adlar) {
        $f = $ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq $ad }, $true) | Select-Object -First 1
        if (-not $f -and $Varsa) { K ("YUKLENMEDI " + $ad); continue }
        if (-not $f) { throw "fonksiyon yok: $ad" }
        Denetle $f $ad
        . ([ScriptBlock]::Create($f.Extent.Text))
    }
}
# 3) KAYITÇILAR (gerçekleri ASLA yüklenmez) + sahte footprint/profil kökü
function Write-PemfLog($msg, $color = 'Gray') { K ("LOG " + $msg) }
function Remove-PemfCredentials { param([string[]]$TargetNames, [switch]$DryRun) K ("KIMLIK_KULLANICI dry=" + [bool]$DryRun + " n=" + @($TargetNames).Count) }
function Remove-PemfSystemCredentials { param([string[]]$TargetNames, [switch]$DryRun) K ("KIMLIK_SYSTEM dry=" + [bool]$DryRun + " n=" + @($TargetNames).Count) }
function Remove-PemfTasks { param($Tasks, [switch]$DryRun) K "GOREV" }
function Remove-PemfFirewall { param($Rx, [switch]$DryRun) K "FIREWALL" }
function Remove-PemfEnv { param($Rx, [switch]$DryRun) K "ENV" }
function Remove-PemfRegistry { param($Registry, $Scope, [switch]$DryRun) K "REGISTRY" }
# D2.E04: makine dışı yedek kayıtları (gerçek registry/ortam okur) burada kayıtçı — davranışı kendi gölge kapısı ölçer.
function Get-PemfMakineDisiYedekHedefleri { param($Footprint) K "YEDEK_HEDEF_OKU"; @() }
function Write-PemfMakineDisiYedekRaporu { param($Hedefler) K ("YEDEK_RAPOR n=" + @($Hedefler).Count) }
function Get-PemfProfileRoots { @(Join-Path $Kok 'profil') }
function Test-PemfPortAcik([int]$Port) { K ("PROBE " + $Port); return ($script:AcikPortlar -contains $Port) }
$estop_islevleri = @('Send-PemfAcilDurdur', 'Get-PemfBackendPortAdaylari', 'Invoke-PemfAcilDurdurIstegi')

$sonuc = [ordered]@{ senaryo = $Senaryo }
switch -Wildcard ($Senaryo) {
    'yollar*' {
        . Yukle $Teardown @('Test-PemfScope', 'Assert-PemfRemoved', 'Remove-PemfPaths')
        $kvkk = Join-Path $Kok 'hasta_verisi'; $normal = Join-Path $Kok 'gecici_veri'
        New-Item -ItemType Directory -Force $kvkk, $normal | Out-Null
        $fp = [pscustomobject]@{ Paths = @(
            [pscustomobject]@{ Kind = 'Abs'; Path = $kvkk; Kvkk = $true; Owner = 'backend' },
            [pscustomobject]@{ Kind = 'Abs'; Path = $normal; Kvkk = $false; Owner = 'backend' }) }
        $script:PemfFailed = @()
        if ($Senaryo -eq 'yollar_hasta_dahil') { Remove-PemfPaths -Footprint $fp -Scope backend -IncludePatientData }
        else { Remove-PemfPaths -Footprint $fp -Scope backend }
        $sonuc.kvkk = $kvkk; $sonuc.normal = $normal
    }
    'servis_sirasi' {
        . Yukle $Teardown @('Stop-PemfProcessesAndServices')
        . Yukle $Teardown $estop_islevleri -Varsa
        $script:Servis['mosquitto'] = 'Running'; $script:Servis['PemfBackend'] = 'Running'
        $script:PemfFailed = @()
        Stop-PemfProcessesAndServices -Services @('mosquitto', 'PemfBackend')
    }
    'estop_*' {
        # D1.92/D1.93: GERÇEK Stop-PemfProcessesAndServices + GERÇEK E-stop yardımcıları; ağ ve soket SAHTE.
        . Yukle $Teardown @('Stop-PemfProcessesAndServices')
        . Yukle $Teardown $estop_islevleri -Varsa
        $pd = Join-Path $Kok 'profil\AppData\Local\PEMF Vet Client'
        New-Item -ItemType Directory -Force $pd | Out-Null
        $portDosyasi = Join-Path $pd 'backend.port'
        switch ($Senaryo) {
            'estop_basari' { Set-Content -LiteralPath $portDosyasi -Value '48123'; $script:AcikPortlar = @(48123) }
            'estop_hata' { Set-Content -LiteralPath $portDosyasi -Value '48123'; $script:AcikPortlar = @(48123); $script:HttpDavranis = 'hata' }
            'estop_zaman' { Set-Content -LiteralPath $portDosyasi -Value '48123'; $script:AcikPortlar = @(48123); $script:HttpDavranis = 'zaman' }
            'estop_portyok' { }
            'estop_sira' { Set-Content -LiteralPath $portDosyasi -Value '48123'; $script:AcikPortlar = @(8001, 8002) }
            'estop_bozukdosya' { Set-Content -LiteralPath $portDosyasi -Value '8000; KANARYA'; $script:AcikPortlar = @(8000) }
            # O-7.1: backend.port YOK; 8000'de başka bir yerel servis 2xx döner, gerçek backend 8001'de.
            'estop_yabanci_html' { $script:AcikPortlar = @(8000, 8001); $script:YabanciPortlar = @{ 8000 = '<html><body>baska servis</body></html>' } }
            'estop_yabanci_json' { $script:AcikPortlar = @(8000, 8001); $script:YabanciPortlar = @{ 8000 = [pscustomobject]@{ status = 'ok'; servis = 'baska' } } }
            'estop_yabanci_hepsi' { $script:AcikPortlar = @(8000); $script:YabanciPortlar = @{ 8000 = [pscustomobject]@{ ok = $true } } }
            # O-13.1: yabancı servis PEMF'in `status` DEĞERİNİ döner — imzanın öteki alanları (stmStopped / mqttResults) ayrı ayrı eksik.
            'estop_yabanci_success' { $script:AcikPortlar = @(8000, 8001); $script:YabanciPortlar = @{ 8000 = [pscustomobject]@{ status = 'success' } } }
            'estop_yabanci_success_stm' { $script:AcikPortlar = @(8000, 8001); $script:YabanciPortlar = @{ 8000 = [pscustomobject]@{ status = 'success'; stmStopped = $true } } }
            'estop_yabanci_success_mqtt' { $script:AcikPortlar = @(8000, 8001); $script:YabanciPortlar = @{ 8000 = [pscustomobject]@{ status = 'partial'; mqttResults = @() } } }
        }
        $script:Servis['mosquitto'] = 'Running'; $script:Servis['PemfBackend'] = 'Running'
        $script:PemfFailed = @()
        Stop-PemfProcessesAndServices -Services @('mosquitto', 'PemfBackend')
    }
    'orkestrator*' {
        . Yukle $Teardown @('Test-PemfScope', 'Assert-PemfRemoved', 'Remove-PemfPaths', 'Invoke-PemfTeardown')
        function Get-PemfFootprint { [pscustomobject]@{ Services = @(); Tasks = @(); FirewallRx = 'YOK'; EnvRx = 'YOK'; Registry = @(); Paths = @(); Credentials = @('PEMF_SAHTE@PEMF_GUI') } }
        if ($Senaryo -eq 'orkestrator_dry_hasta') { [void](Invoke-PemfTeardown -Scope backend -DryRun -IncludePatientData) }
        else { [void](Invoke-PemfTeardown -Scope backend -DryRun) }
    }
    'nssm_blogu' {
        $t = $null; $e = $null
        $ast = [System.Management.Automation.Language.Parser]::ParseFile($Setup, [ref]$t, [ref]$e)
        if ($e) { throw "parse hatasi: $Setup" }
        $ifadeler = @($ast.EndBlock.Statements)
        $bas = -1; $son = -1
        for ($i = 0; $i -lt $ifadeler.Count; $i++) {
            $x = $ifadeler[$i].Extent.Text
            if ($bas -lt 0 -and $x -match '^&\s*\$NssmExe\s+set\s+\$ServiceBackend\s+AppDirectory\b') { $bas = $i }
            if ($x -match '^&\s*\$NssmExe\s+set\s+\$ServiceBackend\s+AppEnvironmentExtra\b') { $son = $i }
        }
        if ($bas -lt 0 -or $son -lt $bas) { throw "nssm blogu bulunamadi ($bas, $son)" }
        foreach ($x in $ifadeler[$bas..$son]) { Denetle $x 'nssm_blogu' }
        $metin = ($ifadeler[$bas..$son] | ForEach-Object { $_.Extent.Text }) -join "`n"
        New-Item -ItemType Directory -Force (Join-Path $Kok 'scripts'), (Join-Path $Kok 'deploy'), (Join-Path $Kok 'app') | Out-Null
        Copy-Item (Join-Path (Split-Path -Parent (Split-Path -Parent $Setup)) 'deploy\device.env') (Join-Path $Kok 'deploy\device.env')
        $blok = Join-Path $Kok 'scripts\nssm_blogu.ps1'
        Set-Content -LiteralPath $blok -Value $metin -Encoding UTF8
        $NssmExe = 'nssm'; $ServiceBackend = 'PemfBackend'; $AppDir = Join-Path $Kok 'app'; $LogDir = Join-Path $Kok 'log'; $Mode = 'device'
        function Log { param($m, $c) }
        # Y44: profil dosyası bulma + ayrıştırma işlevleri (ön doğrulamayla ORTAK) AST'den, izin listesiyle.
        . Yukle $Setup @('Get-PemfProfilEnvDosyasi', 'Read-PemfProfilEnv')
        . $blok
    }
    'kaldirma_blogu*' {
        # setup_services.ps1 `if ($Uninstall) { … }` gövdesi AST'den; sondaki `exit 0` dışında AYNEN koşar.
        $t = $null; $e = $null
        $ast = [System.Management.Automation.Language.Parser]::ParseFile($Setup, [ref]$t, [ref]$e)
        if ($e) { throw "parse hatasi: $Setup" }
        $dal = @($ast.EndBlock.Statements | Where-Object { $_ -is [System.Management.Automation.Language.IfStatementAst] -and $_.Clauses[0].Item1.Extent.Text -eq '$Uninstall' })
        if ($dal.Count -ne 1) { throw "if (`$Uninstall) blogu $($dal.Count) kez" }
        $govde = @($dal[0].Clauses[0].Item2.Statements)
        if (-not ($govde[-1] -is [System.Management.Automation.Language.ExitStatementAst])) { throw "kaldirma blogu exit ile bitmiyor (yapi degismis)" }
        $govde = $govde[0..($govde.Count - 2)]
        foreach ($x in $govde) { Denetle $x 'kaldirma_blogu' }
        $AppDir = Join-Path $Kok 'app'
        New-Item -ItemType Directory -Force $AppDir | Out-Null
        if (Test-Path (Join-Path $AppDir 'pemf_teardown.ps1')) { throw "sahte AppDir'de teardown var — dot-source edilirdi" }
        if ($Senaryo -eq 'kaldirma_blogu_estop') {
            # Kayıtçı modül: yalnız iki işlev, gerçek dünyaya dokunmaz (gerçek E-stop yardımcısını estop_* senaryoları koşar).
            $stub = 'function Send-PemfAcilDurdur { K "ESTOP"; 1 }' + "`n" + 'function Invoke-PemfTeardown { param($Scope, [switch]$IncludePatientData) K "TEARDOWN"; $true }'
            Set-Content -LiteralPath (Join-Path $AppDir 'pemf_teardown.ps1') -Encoding UTF8 -Value $stub
        }
        Set-Content -LiteralPath (Join-Path (Get-Location) 'nssm') -Value '' # Test-Path $NssmExe → gölge `nssm`
        $NssmExe = 'nssm'; $ServiceBackend = 'PemfBackend'; $ServiceMosq = 'mosquitto'; $PurgeData = $false; $StagingMi = $false
        $script:Servis['PemfBackend'] = 'Running'; $script:Servis['mosquitto'] = 'Running'
        function Log { param($m, $c) K ("LOG " + $m) }
        function Invoke-PemfTeardown { param($Scope, [switch]$IncludePatientData) K "TEARDOWN"; $true }
        $blok = Join-Path $Kok 'kaldirma_blogu.ps1'
        Set-Content -LiteralPath $blok -Value (($govde | ForEach-Object { $_.Extent.Text }) -join "`n") -Encoding UTF8
        . $blok
    }
}
$sonuc.failed = @($script:PemfFailed | Where-Object { $_ })
$sonuc.kayit = @($script:Kayit)
$sonuc | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $Cikti -Encoding UTF8
exit 0
"""


def _kos(tmp_path: Path, senaryo: str, bekleme: int = 0, teardown: Path = TEARDOWN, beklenen_ret: bool = False):
    aparat = tmp_path / "aparat.ps1"
    aparat.write_text(_APARAT, encoding="utf-8-sig")
    cikti = tmp_path / "cikti.json"
    kok = tmp_path / "kok"
    kok.mkdir()
    r = subprocess.run(
        [
            _PWSH,
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(aparat),
            "-Teardown",
            str(teardown),
            "-Setup",
            str(SETUP),
            "-Kok",
            str(kok),
            "-Senaryo",
            senaryo,
            "-Cikti",
            str(cikti),
            "-Bekleme",
            str(bekleme),
        ],
        capture_output=True,
        timeout=120,
        cwd=str(tmp_path),
    )
    out = r.stdout.decode("utf-8", "replace") + r.stderr.decode("utf-8", "replace")
    if beklenen_ret:
        return {"rc": r.returncode, "cikti_var": cikti.exists(), "out": out}
    assert "APARAT_HATASI" not in out, f"aparat güvenli değil — hiçbir şey çağrılmadı: {out[-600:]}"
    assert r.returncode == 0 and cikti.exists(), f"aparat koşmadı (rc={r.returncode}): {out[-1200:]}"
    return json.loads(cikti.read_text(encoding="utf-8-sig"))


def _yasakli(kayit: list[str]) -> list[str]:
    """Gerçek dünyaya dokunacak her komut gölgede kalmalı; kayıtta yalnız GÖLGE kayıtları olur."""
    return [k for k in kayit if k.startswith(("cmdkey", "schtasks", "icacls"))]


# ── D1.45 ───────────────────────────────────────────────────────────────────


def test_KRITIK_D145_varsayilan_kaldirma_HASTA_VERISINI_silmez(tmp_path):
    s = _kos(tmp_path, "yollar_varsayilan")
    silinen = [k[len("Remove-Item ") :] for k in s["kayit"] if k.startswith("Remove-Item ")]
    assert s["kvkk"] not in silinen, "VARSAYILAN kaldırma Kvkk=$true yolu SİLİYOR — hasta verisi/anahtar gider (KVKK)"
    assert s["normal"] in silinen, (
        f"aparat: KVKK-dışı yol bile silinmek istenmedi (Remove-PemfPaths koşmadı?): {s['kayit']}"
    )
    assert _yasakli(s["kayit"]) == []


def test_KARSIT_D145_IncludePatientData_ile_hasta_verisi_SILINIR(tmp_path):
    s = _kos(tmp_path, "yollar_hasta_dahil")
    silinen = [k[len("Remove-Item ") :] for k in s["kayit"] if k.startswith("Remove-Item ")]
    assert s["kvkk"] in silinen and s["normal"] in silinen, f"-IncludePatientData tam temizlik yapmadı: {silinen}"


def test_KRITIK_D145_servisler_SIRAYLA_broker_EN_SON_ve_kill_STOPLARDAN_sonra(tmp_path):
    s = _kos(tmp_path, "servis_sirasi")
    stoplar = [k.split()[2] for k in s["kayit"] if k.startswith("sc stop ")]
    assert stoplar == ["PemfBackend", "mosquitto"], (
        f"durdurma sırası {stoplar} — broker backend'den ÖNCE kapanırsa backend'in ESP STOP yayını broker'sız kalır"
    )
    son_stop = max(i for i, k in enumerate(s["kayit"]) if k.startswith("sc stop "))
    kill = [i for i, k in enumerate(s["kayit"]) if k == "Stop-Process"]
    assert not kill or min(kill) > son_stop, "force-kill graceful durdurmalardan ÖNCE"
    assert _yasakli(s["kayit"]) == []


def _bekleme_olcumu(kayit: list[str], stop_kaydi: str, servis: str) -> tuple[int, int, int]:
    """(stop dizini, servisin İLK `Stopped` görüldüğü dizin, aradaki SLEEP sayısı); Stopped yoksa -1."""
    bas = kayit.index(stop_kaydi)
    # Pencere: bir sonraki durdurma/kill'e kadar (durmayan serviste sonraki servisin yoklamaları sayılmasın).
    sinir = next(
        (i for i in range(bas + 1, len(kayit)) if kayit[i].startswith(("sc stop ", "nssm stop ", "Stop-Process"))),
        len(kayit),
    )
    dur = next((i for i in range(bas, sinir) if kayit[i] == f"GS {servis} Stopped"), -1)
    son = dur if dur >= 0 else sinir
    return bas, dur, sum(1 for k in kayit[bas:son] if k == "SLEEP")


_K = 3  # servis k yoklama boyunca StopPending kalır


def test_KRITIK_D145_teardown_servis_DURANA_KADAR_bekler_kill_SONRA(tmp_path):
    """1-B inceleme i5: gölge `sc stop` servisi ANINDA Stopped yaptığından bekleme döngüsü (`$i -lt 40` → `-lt 0`)
    hiç sınanmıyordu. Servis k yoklama StopPending kalır; kill, Stopped GÖRÜLDÜKTEN sonra gelmeli."""
    s = _kos(tmp_path, "servis_sirasi", bekleme=_K)
    kayit = s["kayit"]
    kill = kayit.index("Stop-Process") if "Stop-Process" in kayit else -1
    for svc in ("PemfBackend", "mosquitto"):
        bas, dur, uyku = _bekleme_olcumu(kayit, f"sc stop {svc}", svc)
        assert dur > bas and uyku >= _K, (
            f"{svc}: `sc stop` sonrası servis Stopped olmadan ilerlendi (uyku {uyku} < {_K}) — graceful bobin STOP'u "
            "bitmeden sonraki adım/kill çalışır"
        )
        assert kill < 0 or kill > dur, f"{svc}: kill ({kill}) servis DURMADAN ({dur})"
    assert kill > 0, "aparat: kill hiç kaydedilmedi"
    assert s["failed"] == [], f"duran servis için yanlış hata: {s['failed']}"


def test_KRITIK_D145_DURMAYAN_servis_SERVIS_DURMADI_ve_SINIRLI_bekleme(tmp_path):
    s = _kos(tmp_path, "servis_sirasi", bekleme=-1)
    assert "servis: PemfBackend (StopPending)" in s["failed"], f"durmayan servis PemfFailed'a yazılmadı: {s['failed']}"
    assert any(k.startswith("LOG SERVİS DURMADI: PemfBackend") for k in s["kayit"])
    bas, dur, uyku = _bekleme_olcumu(s["kayit"], "sc stop PemfBackend", "PemfBackend")
    assert dur < 0 and 20 <= uyku <= 60, f"durmayan serviste bekleme {uyku} yoklama — sınırsız/çok kısa olmamalı"
    assert "Stop-Process" in s["kayit"], "durmayan serviste kill hiç gelmedi (kaldırma asılı kalır)"


def test_KRITIK_D147a_kaldirma_DAVRANIS_servis_DURANA_KADAR_bekler_kill_SONRA(tmp_path):
    """`setup_services.ps1 -Uninstall` bloğu AST'den koşar: `nssm stop` → servis Stopped olana kadar bekleme →
    ANCAK SONRA Stop-AppProcs (Stop-Process -Force). i5 mutantları: `-in`→`-notin`, `-lt 40`→`-lt 0`."""
    s = _kos(tmp_path, "kaldirma_blogu", bekleme=_K)
    kayit = s["kayit"]
    bas, dur, uyku = _bekleme_olcumu(kayit, "nssm stop PemfBackend", "PemfBackend")
    assert dur > bas and uyku >= _K, f"-Uninstall: servis Stopped olmadan ilerlendi (uyku {uyku} < {_K}): {kayit[:30]}"
    assert "Stop-Process" in kayit, "aparat: -Uninstall kill döngüsü hiç kill yapmadı"
    assert kayit.index("Stop-Process") > dur, "-Uninstall: force-kill servis DURMADAN — bobin STOP'u atlanabilir"
    assert kayit[-2:] == ["sc delete PemfBackend", "sc delete mosquitto"] or "TEARDOWN" in kayit, (
        f"aparat: blok sonuna kadar koşmadı: {kayit[-5:]}"
    )
    assert _yasakli(kayit) == []


def test_KRITIK_D147a_kaldirma_DURMAYAN_serviste_SINIRLI_bekleme_sonra_kill(tmp_path):
    s = _kos(tmp_path, "kaldirma_blogu", bekleme=-1)
    bas, dur, uyku = _bekleme_olcumu(s["kayit"], "nssm stop PemfBackend", "PemfBackend")
    assert dur < 0 and 20 <= uyku <= 60, f"-Uninstall: durmayan serviste bekleme {uyku} yoklama"
    assert "Stop-Process" in s["kayit"]


# ── aparat güvenliği: izin listesi (1-B inceleme i5) ──────────────────────────


@pytest.mark.parametrize(
    ("ad", "satir"),
    [
        ("golgesiz_komut", "    taskkill_KANARYA_yok.exe /F /IM PEMF_Backend.exe\n"),
        ("tam_yollu_komut", "    & 'C:\\Windows\\KANARYA_yok\\sc.exe' stop PemfBackend\n"),
        ("uye_Kill", "    [PemfKanaryaYokTip]::Kill()\n"),
        # 1-F inceleme: D1.92 bu modüle .NET AĞ kodu getirdi (TcpClient sondası). Gölgelenen `Invoke-RestMethod`'u
        # atlayan doğrudan .NET ağ çağrısı yüklenen işleve eklenirse gerçek 127.0.0.1:8000'e (sahibin backend'i)
        # bağlanılırdı. Kanaryalar: VAR OLMAYAN tip / `$null` üzerinde üye — denetim kırık olsa da bağlantı açılamaz.
        ("net_tip", "    [System.Net.Sockets.PemfKanaryaYokIstemci]::new()\n"),
        ("net_uye", "    $null.ConnectAsync('127.0.0.1', 9)\n"),
    ],
)
def test_ARAC_aparat_IZIN_LISTESI_disindaki_komutu_KOSTURMADAN_reddeder(tmp_path, ad, satir):
    """Yüklenen fonksiyona gölgesiz bir komut eklenince aparat HİÇBİR ŞEY çağırmadan çıkış 3 vermeli.
    Kanarya komutları VAR OLMAYAN adlardır: denetim kırık olsa bile gerçek bir süreç öldürülemez."""
    kaynak = TEARDOWN.read_text(encoding="utf-8-sig")
    capa = "function Stop-PemfProcessesAndServices([string[]]$Services) {\n"
    kaynak = kaynak.replace("\r\n", "\n")
    assert kaynak.count(capa) == 1, "çapa çürüdü"
    kopya = tmp_path / "teardown_kopya.ps1"
    kopya.write_text(kaynak.replace(capa, capa + satir), encoding="utf-8-sig")
    (tmp_path / "is").mkdir()
    r = _kos(tmp_path / "is", "servis_sirasi", teardown=kopya, beklenen_ret=True)
    assert r["rc"] == 3 and "APARAT_HATASI" in r["out"] and not r["cikti_var"], (
        f"{ad}: aparat izin listesi dışındaki komutu reddetmedi (rc={r['rc']}): {r['out'][-400:]}"
    )


@pytest.mark.parametrize(
    ("senaryo", "beklenen"),
    [
        ("orkestrator_dry", []),
        ("orkestrator_dry_hasta", ["KIMLIK_KULLANICI dry=True n=1", "KIMLIK_SYSTEM dry=True n=1"]),
    ],
)
def test_KRITIK_D145_orkestrator_kasa_silmesini_YALNIZ_IncludePatientData_ile_ve_DryRun_gecirerek_yapar(
    tmp_path, senaryo, beklenen
):
    s = _kos(tmp_path, senaryo)
    kimlik = [k for k in s["kayit"] if k.startswith("KIMLIK_")]
    assert kimlik == beklenen, (
        f"{senaryo}: kasa çağrıları {kimlik} (beklenen {beklenen}) — varsayılan kaldırmada anahtar silinirse "
        "korunan şifreli DB OKUNAMAZ; önizleme (-DryRun) kasaya dokunmamalı"
    )
    assert _yasakli(s["kayit"]) == []


# ── D1.44 ───────────────────────────────────────────────────────────────────


def _beklenen_env(log_dir: str) -> dict[str, str]:
    """Temel üçlü + device.env'nin etkin `k=v` satırları (aynı anahtarda profil kazanır) — DEĞERLERİYLE."""
    env = {"PYTHONUNBUFFERED": "1", "PEMF_HEADLESS": "1", "PEMF_LOG_DIR": log_dir}
    for ln in DEVICE_ENV.read_text(encoding="utf-8").splitlines():
        t = ln.strip()
        if t and not t.startswith("#") and "=" in t:
            k, v = t.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def test_KRITIK_D144_nssm_env_device_env_ve_temel_uclu_ve_SON_stop_butcesi(tmp_path):
    import backend_service as bs

    s = _kos(tmp_path, "nssm_blogu")
    env = [
        json.loads(k[len("nssm_json ") :])
        for k in s["kayit"]
        if k.startswith("nssm_json ")
        and k[len("nssm_json ") :].startswith('["set","PemfBackend","AppEnvironmentExtra"')
    ]
    assert len(env) == 1, f"AppEnvironmentExtra {len(env)} kez yazıldı"
    ciftler = env[0][3:]
    assert all("=" in p for p in ciftler), f"k=v olmayan env argümanı: {ciftler}"
    yazilan = dict(p.split("=", 1) for p in ciftler)
    assert len(yazilan) == len(ciftler), "aynı env anahtarı iki kez yazıldı"
    beklenen = _beklenen_env(str(tmp_path / "kok" / "log"))
    assert {"PEMF_ALLOWED_HOSTS", "PEMF_DATA_DIR", "PEMF_ENCRYPT_AT_REST"} <= beklenen.keys(), (
        "ön koşul: device.env bu anahtarları taşımıyor"
    )
    # 1-B inceleme i5: yalnız ANAHTAR kümesi karşılaştırılıyordu — `"$_=$EnvMap[$_]"` enterpolasyon hatası
    # değerleri `System.Collections.Specialized.OrderedDictionary[PEMF_DATA_DIR]` yapıyor ve YEŞİL kalıyordu.
    farkli = {k: (yazilan.get(k), v) for k, v in beklenen.items() if yazilan.get(k) != v}
    assert yazilan.keys() == beklenen.keys() and not farkli, (
        f"servise giden env device.env ile birebir değil: eksik={sorted(beklenen.keys() - yazilan.keys())} "
        f"fazla={sorted(yazilan.keys() - beklenen.keys())} farklı değer={farkli}"
    )
    stop = [k for k in s["kayit"] if k.startswith("nssm set PemfBackend AppStopMethodConsole ")]
    assert stop, "AppStopMethodConsole hiç yazılmadı"
    son_ms = int(stop[-1].split()[-1])
    butce_ms = (bs._GRACEFUL_SHUTDOWN_TIMEOUT_S + bs._SAFE_STOP_BUDGET_S) * 1000
    assert son_ms > butce_ms, (
        f"SON AppStopMethodConsole {son_ms} ms ≤ backend kapanış bütçesi {butce_ms:.0f} ms — NSSM graceful bobin "
        "STOP'u bitmeden süreci SERT öldürür"
    )


# ── D1.92 · D1.93 (B-9.23 · B-10.58) — teardown ACİL DURDUR'u kill'den ÖNCE ─────────────────────
# Bağımsız kaldırıcı PEMF_Backend'i `Stop-Process -Force` ile öldürüyordu; öncesinde ACİL DURDUR YOKTU (launcher
# dağıtımında servis yok → `sc stop` hiçbir şeyi durdurmaz, `_safe_stop_outputs` koşmaz). Ağ/soket SAHTE: istek
# `Invoke-RestMethod` gölgesine, port sondası `Test-PemfPortAcik` kayıtçısına gider (8000'e ASLA bağlanılmaz).


def _ilk(kayit: list[str], onek: str) -> int:
    return next((i for i, k in enumerate(kayit) if k.startswith(onek)), -1)


def _sondalar(kayit: list[str]) -> list[int]:
    return [int(k.split()[1]) for k in kayit if k.startswith("PROBE ")]


def test_KRITIK_D192_teardown_ACIL_DURDURU_servis_durdurma_ve_KILLden_ONCE_gonderir(tmp_path):
    s = _kos(tmp_path, "estop_basari")
    k = s["kayit"]
    post = _ilk(k, "HTTP Post http://127.0.0.1:48123/api/hardware/emergency_stop")
    assert post >= 0, f"teardown ACİL DURDUR GÖNDERMEDİ (backend.port 48123 açık): {k[:14]}"
    stop, kill = _ilk(k, "sc stop "), _ilk(k, "Stop-Process")
    assert kill > post and stop > post, (
        f"ACİL DURDUR (#{post}) servis durdurma (#{stop}) / force-kill'den (#{kill}) SONRA — bobin kill anında enerjili"
    )
    assert _ilk(k, "HTTP-IWR") < 0 and _yasakli(k) == []


@pytest.mark.parametrize("senaryo", ["estop_hata", "estop_zaman"])
def test_KRITIK_D192_ACIL_DURDUR_HATASI_ya_da_ZAMAN_ASIMI_kill_i_ENGELLEMEZ(tmp_path, senaryo):
    s = _kos(tmp_path, senaryo)
    k = s["kayit"]
    post = _ilk(k, "HTTP Post http://127.0.0.1:48123/")
    assert post >= 0, f"aparat: ACİL DURDUR denenmedi: {k[:14]}"
    assert "Stop-Process" in k and k.index("Stop-Process") > post, (
        f"{senaryo}: ACİL DURDUR başarısız olunca kaldırma DURDU — E-stop KAPIYA dönüştü (kill/temizlik yok)"
    )
    assert [x.split()[2] for x in k if x.startswith("sc stop ")] == ["PemfBackend", "mosquitto"]
    assert any(x.startswith("LOG ACİL DURDUR başarısız: 127.0.0.1:48123") for x in k), "E-stop hatası günlüğe yazılmadı"
    # 1-F inceleme: backend BULUNDU ve istek denendi — özet "bulunamadı" demez (yanlış teşhis), teyitsizliği söyler.
    assert not any("bulunamadı" in x for x in k if x.startswith("LOG ")), (
        f"{senaryo}: backend bulunup istek BAŞARISIZ olduğu hâlde günlük 'backend bulunamadı' diyor"
    )
    assert any(x.startswith("LOG ACİL DURDUR TEYİT EDİLEMEDİ") for x in k), f"{senaryo}: teyitsizlik özeti yok"


def _ikiz_zaman_asimi(yol: Path) -> int:
    """İkizin (Inno / NSIS) emergency_stop komut satırındaki `-TimeoutSec` değeri — kaynaktan (kopya sürüklenmesin)."""
    import re

    # YORUM satırları sayılmaz (iki ikizde de yorum "-TimeoutSec 10" der — yorum kapıyı yeşil tutmasın).
    kod = [
        x
        for x in yol.read_text(encoding="utf-8", errors="replace").splitlines()
        if not x.strip().startswith(("//", ";"))
    ]
    satirlar = [x for x in kod if "-TimeoutSec" in x]
    degerler = [int(m.group(1)) for x in satirlar for m in [re.search(r"-TimeoutSec\s+(\d+)", x)] if m]
    assert degerler, f"aparat: {yol.name} içinde E-stop -TimeoutSec bulunamadı (çapa çürüdü)"
    return max(degerler)


def test_KRITIK_D192_ACIL_DURDUR_zaman_asimi_INNO_ve_NSIS_ikizleriyle_AYNI(tmp_path):
    """1-F inceleme: ikizler `-TimeoutSec 10` kullanır ve gerekçesi ÖLÇÜLMÜŞTÜR ("backend bu ucu senkron MQTT publish ~7 sn
    worst-case diye belgeliyor; daha kısa değer ESP bobinleri yayınlanmadan dolabiliyordu — NSIS ikizinde ölçüldü").
    PowerShell yardımcısı 5 sn ile başarılı bir E-stop'u "başarısız" sayıp flush beklemesini atlıyordu."""
    kok = Path(__file__).resolve().parent.parent
    ikiz = max(
        _ikiz_zaman_asimi(kok / "build_tools" / "PEMF_Backend_Setup.iss"),
        _ikiz_zaman_asimi(kok / "launcher" / "app" / "windows" / "hooks.nsi"),
    )
    s = _kos(tmp_path, "estop_basari")
    sure = [x.split()[1] for x in s["kayit"] if x.startswith("HTTP-SURE ")]
    assert sure, f"aparat: ACİL DURDUR isteği kaydedilmedi: {s['kayit'][:10]}"
    assert all(float(x) >= ikiz for x in sure), (
        f"ACİL DURDUR isteğinin zaman aşımı {sure} sn < ikizlerin {ikiz} sn'si — yavaş (ESP) E-stop 'başarısız' sayılır"
    )


def test_KRITIK_D192_backend_BULUNAMAZSA_adaylar_SIRAYLA_denenir_GUNLUGE_yazilir_kill_SURER(tmp_path):
    s = _kos(tmp_path, "estop_portyok")
    k = s["kayit"]
    assert _sondalar(k) == list(range(8000, 8050)), f"aday portlar 8000..8049 sırayla denenmedi: {_sondalar(k)[:6]}…"
    assert _ilk(k, "HTTP ") < 0, "açık port yokken istek gönderildi"
    assert any(x.startswith("LOG ACİL DURDUR: çalışan PEMF backend'i bulunamadı") for x in k), "sonuç günlüğe yazılmadı"
    assert "Stop-Process" in k, "backend bulunamayınca kaldırma durdu"


def test_KRITIK_D192_port_SIRASI_backend_port_8000_8001_ve_ILK_basarida_durur(tmp_path):
    s = _kos(tmp_path, "estop_sira")
    k = s["kayit"]
    sonda = _sondalar(k)
    assert sonda[:3] == [48123, 8000, 8001], f"port sırası backend.port → 8000 → 8001 değil: {sonda[:5]}"
    http = [x for x in k if x.startswith("HTTP ")]
    assert http == ["HTTP Post http://127.0.0.1:8001/api/hardware/emergency_stop"], http
    assert 8002 not in sonda, "ilk başarılı ACİL DURDUR'dan sonra taramaya devam edildi (yabancı servislere istek)"


@pytest.mark.parametrize(
    "senaryo",
    [
        "estop_yabanci_html",
        "estop_yabanci_json",
        "estop_yabanci_success",
        "estop_yabanci_success_stm",
        "estop_yabanci_success_mqtt",
    ],
)
def test_KRITIK_O71_YABANCI_servisin_2xxi_GONDERILDI_sayilmaz_tarama_SURER(tmp_path, senaryo):
    """O-7.1 (1-F inceleme): tarama ilk 2xx yanıtta duruyordu. `backend.port` yok/bayatken ÖNDEKİ bir yerel servis (8000)
    bu yola 2xx dönerse gerçek backend (8001) ACİL DURDUR almıyordu. Yanıt PEMF yanıtı olmalı: `status` ∈ success/partial/
    error (`_emergency_stop_all`'ın değerleri); HTML ya da başka `status` değeri 'gönderildi' sayılmaz, tarama SÜRER.
    O-13.1 (1-G inceleme → 1-H): `status` DEĞERİNİ taklit eden yabancı servis de ('success' / 'partial') PEMF sayılmaz —
    imza `stmStopped` VE `mqttResults` alanlarını da ister (gönderim AZALMAZ: istek zaten gitmiştir, yalnız tarama sürer)."""
    s = _kos(tmp_path, senaryo)
    k = s["kayit"]
    http = [x for x in k if x.startswith("HTTP ")]
    assert http == [
        "HTTP Post http://127.0.0.1:8000/api/hardware/emergency_stop",
        "HTTP Post http://127.0.0.1:8001/api/hardware/emergency_stop",
    ], (
        f"{senaryo}: 8000'deki YABANCI servisin 2xx'i 'gönderildi' sayıldı, tarama durdu — backend (8001) E-stop almadı: {http}"
    )
    assert any(x.startswith("LOG ACİL DURDUR gönderildi: 127.0.0.1:8001") for x in k), "8001'e gönderim günlükte yok"
    assert not any(x.startswith("LOG ACİL DURDUR gönderildi: 127.0.0.1:8000") for x in k), "yabancı servis 'gönderildi'"
    assert "Stop-Process" in k and k.index("Stop-Process") > _ilk(k, "HTTP Post http://127.0.0.1:8001/")


def test_KRITIK_O71_yalniz_YABANCI_servis_varsa_TEYIT_EDILEMEDI_der_kill_SURER(tmp_path):
    s = _kos(tmp_path, "estop_yabanci_hepsi")
    k = s["kayit"]
    assert _ilk(k, "HTTP Post http://127.0.0.1:8000/") >= 0, f"aparat: 8000 denenmedi: {k[:12]}"
    assert not any(x.startswith("LOG ACİL DURDUR gönderildi") for x in k), "yabancı servisin 2xx'i 'gönderildi' sayıldı"
    assert any(x.startswith("LOG ACİL DURDUR TEYİT EDİLEMEDİ") for x in k), f"teyitsizlik özeti yok: {k}"
    assert "Stop-Process" in k, "yabancı servis yanıtında kaldırma durdu"


def test_KRITIK_D192_bozuk_backend_port_dosyasi_KULLANILMAZ_tarama_SURER(tmp_path):
    """`backend.port` kullanıcı-yazılabilir: sayı olmayan içerik aday olmaz (Inno/NSIS ikizleriyle aynı denetim), yardımcı
    çökmez, tarama 8000'den sürer."""
    s = _kos(tmp_path, "estop_bozukdosya")
    k = s["kayit"]
    assert _sondalar(k)[:1] == [8000], _sondalar(k)[:3]
    assert [x for x in k if x.startswith("HTTP ")] == ["HTTP Post http://127.0.0.1:8000/api/hardware/emergency_stop"]


def test_KRITIK_D192_setup_services_kaldirma_ACIL_DURDURU_nssm_stop_ve_KILLden_ONCE(tmp_path):
    """`setup_services.ps1 -Uninstall` force-kill döngüsü ADINA göre TÜM PEMF_Backend'leri (launcher'ınki dahil)
    öldürür → birleşik teardown'ın ACİL DURDUR'u en başta. (Gerçek yardımcıyı estop_* senaryoları koşar; burada
    sahte AppDir'deki kayıtçı modül.)"""
    s = _kos(tmp_path, "kaldirma_blogu_estop", bekleme=_K)
    k = s["kayit"]
    assert "ESTOP" in k, f"-Uninstall ACİL DURDUR çağırmadı: {k[:12]}"
    e = k.index("ESTOP")
    assert e < k.index("nssm stop PemfBackend") and e < k.index("Stop-Process"), (
        "-Uninstall: ACİL DURDUR nssm stop / force-kill'den SONRA"
    )
