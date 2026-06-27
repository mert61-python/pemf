# =============================================================================
# PEMF Headless Backend — Windows Service kurulumu (NSSM).  Faz 5 (sağlamlaştırılmış)
# =============================================================================
# Öncelik: frozen EXE (dist\PEMF_Backend\PEMF_Backend.exe). Yoksa python + script.
# Mosquitto KENDİ servisidir (install_mosquitto_service.ps1) -> backend ona
# 'depends' ile bağlanır ve broker'ı kendi başlatmaz (--no-mosquitto-ensure).
# Çökme -> NSSM otomatik restart. Kapanış -> backend_service donanımı güvenli durdurur.
#
# Yönetici PowerShell:  .\install_backend_service.ps1
# =============================================================================
$ErrorActionPreference = "Stop"

function Write-Status($msg, $color = "White") {
    $ts = Get-Date -Format "HH:mm:ss"
    Write-Host "[$ts] $msg" -ForegroundColor $color
}

$principal = New-Object System.Security.Principal.WindowsPrincipal([System.Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([System.Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Status "HATA: Bu script Yönetici olarak çalıştırılmalıdır." "Red"
    pause; exit 1
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  PEMF Backend Service Kurulumu (NSSM)" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

$ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$GuiRoot     = Split-Path -Parent $ScriptDir
$BackendFile = "$GuiRoot\backend_service.py"
$ExePath     = @("C:\PEMF_BUILD\dist\PEMF_Backend\PEMF_Backend.exe", "$GuiRoot\dist\PEMF_Backend\PEMF_Backend.exe") |
               Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $ExePath) { $ExePath = "$GuiRoot\dist\PEMF_Backend\PEMF_Backend.exe" }
$NssmDir     = "C:\nssm"
$NssmExe     = "$NssmDir\nssm.exe"
$ServiceName = "PemfBackend"
$LogDir      = "C:\ProgramData\PEMF_System\logs"

# --- Servis ikilisi: önce frozen EXE, yoksa python + backend_service.py ---
# Ortak argüman: Mosquitto kendi servisi olduğu için broker'ı backend BAŞLATMAZ,
# sadece izler -> --no-mosquitto-ensure.
$CommonArgs = @("--host", "0.0.0.0", "--port", "8000", "--no-mosquitto-ensure")
if (Test-Path $ExePath) {
    $SvcBinary       = $ExePath
    $SvcArgs         = $CommonArgs
    $AppDir          = Split-Path -Parent $ExePath
    $FirewallProgram = $ExePath
    $UsingExe        = $true
    Write-Status "Servis ikilisi: frozen EXE -> $ExePath" "Green"
} else {
    $foundPython = Get-Command python -ErrorAction SilentlyContinue
    if (-not $foundPython) {
        Write-Status "HATA: Ne frozen EXE ne PATH'te python var. Önce build_backend_exe.ps1 çalıştırın." "Red"
        pause; exit 1
    }
    if (-not (Test-Path $BackendFile)) {
        Write-Status "HATA: backend_service.py bulunamadı: $BackendFile" "Red"
        pause; exit 1
    }
    $SvcBinary       = $foundPython.Source
    $SvcArgs         = @("$BackendFile") + $CommonArgs
    $AppDir          = $GuiRoot
    $FirewallProgram = $foundPython.Source
    $UsingExe        = $false
    Write-Status "Frozen EXE yok; python+script (dev) ile: $SvcBinary" "Yellow"
}

if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
    Write-Status "Log dizini oluşturuldu: $LogDir" "Green"
}

# --- NSSM hazır mı? (yoksa indir) ---
if (-not (Test-Path $NssmExe)) {
    Write-Status "NSSM bulunamadı, indiriliyor..." "Yellow"
    if (-not (Test-Path $NssmDir)) { New-Item -ItemType Directory -Path $NssmDir -Force | Out-Null }
    $NssmZip = "$env:TEMP\nssm.zip"
    Invoke-WebRequest -Uri "https://nssm.cc/release/nssm-2.24.zip" -OutFile $NssmZip -UseBasicParsing
    Expand-Archive -Path $NssmZip -DestinationPath "$env:TEMP\nssm_ext" -Force
    $NssmBin = Get-ChildItem "$env:TEMP\nssm_ext" -Filter "nssm.exe" -Recurse |
        Where-Object { $_.FullName -like "*win64*" } | Select-Object -First 1
    if (-not $NssmBin) { $NssmBin = Get-ChildItem "$env:TEMP\nssm_ext" -Filter "nssm.exe" -Recurse | Select-Object -First 1 }
    Copy-Item $NssmBin.FullName $NssmExe -Force
    Write-Status "NSSM kuruldu: $NssmExe" "Green"
} else {
    Write-Status "NSSM bulundu: $NssmExe" "Green"
}

# --- Varolan servisi kaldır ---
if (Get-Service -Name $ServiceName -ErrorAction SilentlyContinue) {
    Write-Status "Mevcut servis kaldırılıyor..." "Yellow"
    & $NssmExe stop $ServiceName *>$null
    Start-Sleep -Seconds 2
    & $NssmExe remove $ServiceName confirm *>$null
    Start-Sleep -Seconds 2
}

# --- Kur ---
Write-Status "Servis kuruluyor: $ServiceName" "Yellow"
& $NssmExe install $ServiceName $SvcBinary @SvcArgs

& $NssmExe set $ServiceName AppDirectory       $AppDir
& $NssmExe set $ServiceName DisplayName        "PEMF Backend Service"
& $NssmExe set $ServiceName Description         "Headless PEMF backend: FastAPI, WebSocket, STM32, MQTT, React Web."
& $NssmExe set $ServiceName Start               SERVICE_AUTO_START
& $NssmExe set $ServiceName ObjectName          LocalSystem

# Log (NSSM stdout/stderr yakalar + döndürür)
& $NssmExe set $ServiceName AppStdout           "$LogDir\backend_service_stdout.log"
& $NssmExe set $ServiceName AppStderr           "$LogDir\backend_service_stderr.log"
& $NssmExe set $ServiceName AppRotateFiles      1
& $NssmExe set $ServiceName AppRotateBytes      10485760

# Çökme kurtarma + güvenli durdurma süresi (backend_service finally bloğu donanımı durdurur)
& $NssmExe set $ServiceName AppExit             Default Restart
& $NssmExe set $ServiceName AppRestartDelay     5000
& $NssmExe set $ServiceName AppStopMethodConsole 15000
& $NssmExe set $ServiceName AppThrottle         5000

# Ortam değişkenleri (EXE'de PYTHONPATH'e gerek yok -> bundled modüller kullanılır)
if ($UsingExe) {
    & $NssmExe set $ServiceName AppEnvironmentExtra `
        "PYTHONUNBUFFERED=1" "PEMF_HEADLESS=1" "PEMF_LOG_DIR=$LogDir"
} else {
    & $NssmExe set $ServiceName AppEnvironmentExtra `
        "PYTHONPATH=$GuiRoot" "PYTHONUNBUFFERED=1" "PEMF_HEADLESS=1" "PEMF_LOG_DIR=$LogDir"
}

# --- Mosquitto bağımlılığı (kendi servisi varsa) ---
if (Get-Service -Name "mosquitto" -ErrorAction SilentlyContinue) {
    sc.exe config $ServiceName depend= mosquitto | Out-Null
    Write-Status "Bağımlılık eklendi: PemfBackend -> mosquitto" "Green"
} else {
    Write-Status "UYARI: 'mosquitto' servisi yok. Önce install_mosquitto_service.ps1 çalıştırın." "Yellow"
}

# --- Firewall (API 8000 TCP + keşif 5051 UDP) ---
try {
    if (-not (Get-NetFirewallRule -DisplayName "PEMF Backend API" -ErrorAction SilentlyContinue)) {
        New-NetFirewallRule -DisplayName "PEMF Backend API" -Direction Inbound `
            -Program $FirewallProgram -Action Allow -Protocol TCP -LocalPort 8000 -Profile Any | Out-Null
        Write-Status "Firewall: TCP 8000 inbound eklendi." "Green"
    }
    if (-not (Get-NetFirewallRule -DisplayName "PEMF UDP Discovery" -ErrorAction SilentlyContinue)) {
        New-NetFirewallRule -DisplayName "PEMF UDP Discovery" -Direction Inbound `
            -Program $FirewallProgram -Action Allow -Protocol UDP -LocalPort 5051 -Profile Any | Out-Null
        Write-Status "Firewall: UDP 5051 inbound eklendi." "Green"
    }
} catch {
    Write-Status "Firewall kuralı eklenemedi: $_" "Yellow"
}

# --- Başlat ---
Write-Status "Servis başlatılıyor..." "Yellow"
& $NssmExe start $ServiceName
Start-Sleep -Seconds 4
$status = & $NssmExe status $ServiceName 2>&1
Write-Status "Servis durumu: $status" "Cyan"

Write-Host ""
Write-Host "Backend servisi kuruldu." -ForegroundColor Green
Write-Host "  Servis : $ServiceName  (ikili: $(if($UsingExe){'frozen EXE'}else{'python+script'}))"
Write-Host "  URL    : http://localhost:8000"
Write-Host "  Loglar : $LogDir\backend_service.log"
Write-Host "  Bağımlılık: mosquitto (otomatik sıra: mosquitto -> PemfBackend)"
Write-Host ""
Write-Host "Yönetim: $NssmExe (status|stop|start|restart|remove) $ServiceName"
Write-Host ""
pause
