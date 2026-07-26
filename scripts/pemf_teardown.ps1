# =============================================================================
# PEMF TEARDOWN — birleşik kaldırma motoru (Faz 2). pemf_footprint.ps1'i tüketir.
# -----------------------------------------------------------------------------
# TÜKETİCİLER (hepsi AYNI mantık + AYNI KVKK politikası):
#   • setup_services.ps1 -Uninstall      -> Invoke-PemfTeardown -Scope backend
#   • pemf_uninstall_all.ps1 (standalone)-> Invoke-PemfTeardown -Scope all
#   • PEMF_Setup.iss eski-GUI            -> Invoke-PemfTeardown -Scope gui
#
# KVKK: hasta verisi (Kvkk=$true) VARSAYILAN KORUNUR; yalnız -IncludePatientData ile silinir.
# -DryRun: hiçbir şey silmeden ne silineceğini logla (tam-kaldırıcı için güvenli önizleme).
#
# Bu dosya DOT-SOURCE edilmek içindir: . .\pemf_teardown.ps1  ->  Invoke-PemfTeardown ...
# =============================================================================

. (Join-Path $PSScriptRoot 'pemf_footprint.ps1')

# Log yeri: footprint-DIŞI olmalı — aksi halde teardown PEMF_System'i siler, sonra final log satırı
# onu YENİDEN yaratır (kalıntı bırakır). Varsayılan $env:TEMP; standalone Desktop'a override eder
# ($env:PEMF_TEARDOWN_LOG) ki KVKK "sildim" raporu kalıcı olsun.
$script:PemfLog = if ($env:PEMF_TEARDOWN_LOG) { $env:PEMF_TEARDOWN_LOG } else { Join-Path $env:TEMP 'pemf_teardown.log' }
function Write-PemfLog($msg, $color = 'Gray') {
    try {
        $dir = Split-Path $script:PemfLog -Parent
        if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
        ("$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $msg") | Add-Content -Path $script:PemfLog -Encoding UTF8
    } catch {}
    Write-Host "[pemf-teardown] $msg" -ForegroundColor $color
}

# Bir öğe verilen kapsamda kaldırılmalı mı? 'shared' = backend+gui (ve all); client per-user kalır.
function Test-PemfScope([string]$Owner, [string]$Scope) {
    if ($Scope -eq 'all') { return $true }
    if ($Owner -eq $Scope) { return $true }
    if ($Owner -eq 'shared' -and ($Scope -eq 'backend' -or $Scope -eq 'gui')) { return $true }
    return $false
}

# Servisleri durdur + kaldır. TIBBİ GÜVENLİK: önce GRACEFUL sc-stop (→ NSSM Ctrl+C → backend
# bobin-STOP + STM kuyruk-flush) + servis STOPPED olana kadar BEKLE ki bobinler (hasta üzerindeyse)
# güvene alınsın; force-kill'i ÖNCE yaparsak bu graceful bobin-STOP ATLANIR. SONRA sc-delete +
# kalan için force-kill (fallback: graceful asılıysa dosya kilidi kalmasın). (mosquitto'da
# Stop-Service -Force StartPending'de ASILIR → sc + süreç-kill kullanılır.)
function Stop-PemfProcessesAndServices([string[]]$Services) {
    foreach ($svc in $Services) {
        if (Get-Service -Name $svc -ErrorAction SilentlyContinue) { & sc.exe stop $svc *>$null }
    }
    # sc stop asenkron döner → STOPPED olana kadar bekle (NSSM AppStopMethodConsole 15s + pay ~20sn).
    foreach ($svc in $Services) {
        for ($i = 0; $i -lt 40 -and ((Get-Service -Name $svc -ErrorAction SilentlyContinue).Status -in @('Running', 'StopPending')); $i++) { Start-Sleep -Milliseconds 500 }
    }
    foreach ($svc in $Services) {
        if (Get-Service -Name $svc -ErrorAction SilentlyContinue) { & sc.exe delete $svc *>$null; Write-PemfLog "servis kaldırıldı: $svc" }
    }
    Get-Process cloudflared, nssm, mosquitto, PEMF_Backend -ErrorAction SilentlyContinue |
        Stop-Process -Force -ErrorAction SilentlyContinue
    # Kayıtlar gerçekten silinene + handle'lar bırakılana kadar kısa poll.
    foreach ($svc in $Services) {
        for ($i = 0; $i -lt 10 -and (Get-Service -Name $svc -ErrorAction SilentlyContinue); $i++) { Start-Sleep 1 }
    }
}

function Remove-PemfTasks([string[]]$Tasks, [switch]$DryRun) {
    foreach ($t in $Tasks) {
        schtasks /Query /TN $t *>$null
        if ($LASTEXITCODE -eq 0) {
            if ($DryRun) { Write-PemfLog "[DRY] görev: $t" 'Yellow' }
            else { schtasks /Delete /TN $t /F *>$null; Write-PemfLog "görev silindi: $t" }
        }
    }
    # Hotspot keep-alive wscript'i System32\wscript.exe'den çalışır -> cmdline ile yakala.
    if (-not $DryRun) {
        Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -eq 'wscript.exe' -and $_.CommandLine -match 'start_hotspot_hidden' } |
            ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    }
}

function Remove-PemfFirewall([string]$Rx, [switch]$DryRun) {
    Get-NetFirewallRule -ErrorAction SilentlyContinue | Where-Object { $_.DisplayName -match $Rx } | ForEach-Object {
        if ($DryRun) { Write-PemfLog "[DRY] firewall: $($_.DisplayName)" 'Yellow' }
        else { $_ | Remove-NetFirewallRule -ErrorAction SilentlyContinue; Write-PemfLog "firewall silindi: $($_.DisplayName)" }
    }
}

function Remove-PemfEnv([string]$Rx, [switch]$DryRun) {
    $key = 'HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Environment'
    (Get-ItemProperty $key -ErrorAction SilentlyContinue).PSObject.Properties |
        Where-Object { $_.Name -match $Rx } | ForEach-Object {
            if ($DryRun) { Write-PemfLog "[DRY] env (Makine): $($_.Name)" 'Yellow' }
            else { Remove-ItemProperty -Path $key -Name $_.Name -Force -ErrorAction SilentlyContinue; Write-PemfLog "env silindi: $($_.Name)" }
        }
}

function Remove-PemfRegistry($Registry, [string]$Scope, [switch]$DryRun) {
    foreach ($r in $Registry) {
        if (-not (Test-PemfScope $r.Owner $Scope)) { continue }
        if (Test-Path -LiteralPath $r.Path) {
            if ($DryRun) { Write-PemfLog "[DRY] registry: $($r.Path)" 'Yellow' }
            else { Remove-Item -LiteralPath $r.Path -Recurse -Force -ErrorAction SilentlyContinue; Write-PemfLog "registry silindi: $($r.Path)" }
        }
    }
}

function Remove-PemfPaths($Footprint, [string]$Scope, [switch]$IncludePatientData, [switch]$DryRun) {
    $profileRoots = Get-PemfProfileRoots
    # Non-KVKK ÖNCE: alt-dizin (ör. PEMF_GUI\ai_models) üst KVKK-dizininden önce temizlensin.
    $ordered = @($Footprint.Paths | Sort-Object { [int][bool]$_.Kvkk })
    foreach ($item in $ordered) {
        if (-not (Test-PemfScope $item.Owner $Scope)) { continue }
        if ($item.Kvkk -and -not $IncludePatientData) { continue }   # KVKK: koru
        $targets = if ($item.Kind -eq 'Abs') { @($item.Path) }
        else { $profileRoots | ForEach-Object { Join-Path $_ $item.Path } }
        foreach ($t in $targets) {
            if (Test-Path -LiteralPath $t -ErrorAction SilentlyContinue) {
                $tag = if ($item.Kvkk) { 'HASTA-VERİSİ' } else { 'veri' }
                if ($DryRun) { Write-PemfLog "[DRY] silinecek ($tag): $t" 'Yellow' }
                else { Remove-Item -LiteralPath $t -Recurse -Force -ErrorAction SilentlyContinue; Write-PemfLog "silindi ($tag): $t" }
            }
        }
    }
}

# NOT: $TargetNames = Windows Credential Manager HEDEF ADLARI (ör. 'PEMF_GUI') — PAROLA DEĞİL,
# yalnız cmdkey /delete için tanımlayıcı. (İsim 'Cred' içerince analyzer parola sanıyordu.)
function Remove-PemfCredentials([string[]]$TargetNames, [switch]$DryRun) {
    foreach ($c in $TargetNames) {
        if ($DryRun) { Write-PemfLog "[DRY] kimlik (KVKK): $c" 'Yellow' }
        else { & cmdkey /delete:$c *>$null; Write-PemfLog "kimlik silindi (KVKK): $c" }
    }
}

# ───────────────────────────── ORKESTRATÖR ─────────────────────────────
function Invoke-PemfTeardown {
    [CmdletBinding()]
    param(
        [ValidateSet('client', 'backend', 'gui', 'all')] [string]$Scope = 'all',
        [switch]$IncludePatientData,   # KVKK: hasta DB + şifreleme anahtarlarını da KALICI sil
        [switch]$DryRun                # hiçbir şey silme, yalnız logla (önizleme)
    )
    $fp = Get-PemfFootprint
    Write-PemfLog "TEARDOWN başladı — Scope=$Scope IncludePatientData=$IncludePatientData DryRun=$DryRun" 'Cyan'

    # 1. Süreç+servis (yalnız backend/all — client/gui'de NSSM servisi yok)
    if ($Scope -eq 'backend' -or $Scope -eq 'all') {
        if ($DryRun) { foreach ($s in $fp.Services) { if (Get-Service -Name $s -ErrorAction SilentlyContinue) { Write-PemfLog "[DRY] servis: $s" 'Yellow' } } }
        else { Stop-PemfProcessesAndServices -Services $fp.Services }
    }
    # 2. Görevler + hotspot wscript
    Remove-PemfTasks -Tasks $fp.Tasks -DryRun:$DryRun
    # 3. Firewall (wildcard)
    Remove-PemfFirewall -Rx $fp.FirewallRx -DryRun:$DryRun
    # 4. Makine ortam değişkenleri PEMF_*
    Remove-PemfEnv -Rx $fp.EnvRx -DryRun:$DryRun
    # 5. Registry (owner-filtreli)
    Remove-PemfRegistry -Registry $fp.Registry -Scope $Scope -DryRun:$DryRun
    # 6. Yollar (non-KVKK her zaman; KVKK yalnız -IncludePatientData; owner-filtreli)
    Remove-PemfPaths -Footprint $fp -Scope $Scope -IncludePatientData:$IncludePatientData -DryRun:$DryRun
    # 7. Kimlikler (KVKK — yalnız -IncludePatientData)
    if ($IncludePatientData) { Remove-PemfCredentials -TargetNames $fp.Credentials -DryRun:$DryRun }

    $policy = if ($IncludePatientData) { 'HASTA VERİSİ DE SİLİNDİ (tam temizlik)' } else { 'HASTA VERİSİ KORUNDU (KVKK; -IncludePatientData ile silinir)' }
    Write-PemfLog "TEARDOWN bitti — $policy" 'Green'
}
