# =============================================================================
# PEMF Headless — KURULU layout için servis kurulumu (installer'dan çağrılır).
# -----------------------------------------------------------------------------
# PEMF_Backend_Setup.iss bunu [Run]'da çağırır: {app} dizinine kurulu EXE +
# bundled mosquitto'dan iki Windows servisini kurar (non-interaktif).
#
#   setup_services.ps1 -AppDir "C:\Program Files\PEMF Backend"
#   setup_services.ps1 -AppDir "..." -Uninstall
# =============================================================================
param(
    [string]$AppDir = "",
    [switch]$Uninstall
)
$ErrorActionPreference = "Continue"   # installer akışını tek bir hata kesmesin
function Log($m, $c = "White") { Write-Host "[setup-services] $m" -ForegroundColor $c }

if (-not $AppDir) { $AppDir = Split-Path -Parent $MyInvocation.MyCommand.Path }

$ServiceBackend = "PemfBackend"
$ServiceMosq    = "mosquitto"
$LogDir         = "C:\ProgramData\PEMF_System\logs"
$NssmExe        = "C:\nssm\nssm.exe"
$MosqInstallDir = "C:\Program Files\PEMF\mosquitto"
$MosqDataRoot   = "C:\ProgramData\PEMF_System\mosquitto"
$BackendExe     = Join-Path $AppDir "PEMF_Backend.exe"

# Bundled mosquitto kaynağı (PyInstaller onedir: {app}\_internal\bin\mosquitto)
$MosqSrc = Join-Path $AppDir "_internal\bin\mosquitto"
if (-not (Test-Path (Join-Path $MosqSrc "mosquitto.exe"))) {
    $alt = Join-Path $AppDir "bin\mosquitto"
    if (Test-Path (Join-Path $alt "mosquitto.exe")) { $MosqSrc = $alt }
}

# ───────────────────────── UNINSTALL ─────────────────────────
if ($Uninstall) {
    Log "Servisler kaldırılıyor..." "Yellow"
    if (Test-Path $NssmExe) {
        & $NssmExe stop $ServiceBackend *>$null
        & $NssmExe remove $ServiceBackend confirm *>$null
    }
    $svc = Get-Service -Name $ServiceMosq -ErrorAction SilentlyContinue
    if ($svc) {
        Stop-Service $ServiceMosq -Force -ErrorAction SilentlyContinue
        $mexe = Join-Path $MosqInstallDir "mosquitto.exe"
        if (Test-Path $mexe) { & $mexe uninstall *>$null }
    }
    foreach ($r in @("PEMF Backend API", "PEMF UDP Discovery", "PEMF Mosquitto MQTT")) {
        netsh advfirewall firewall delete rule name="$r" *>$null
    }
    Log "Servisler kaldırıldı. (Veri/log korundu: $MosqDataRoot, $LogDir)" "Green"
    exit 0
}

New-Item -ItemType Directory -Path $LogDir -Force | Out-Null

# ───────────────────── 1. MOSQUITTO SERVİSİ ─────────────────────
if (Test-Path (Join-Path $MosqSrc "mosquitto.exe")) {
    Log "Mosquitto servisi kuruluyor (bundled → $MosqInstallDir)..." "Yellow"
    New-Item -ItemType Directory -Path $MosqInstallDir, "$MosqDataRoot\data", "$MosqDataRoot\log", "$MosqDataRoot\conf.d" -Force | Out-Null

    # varolan servisi durdur (dosya kilidi için)
    $svc = Get-Service -Name $ServiceMosq -ErrorAction SilentlyContinue
    $mexe = Join-Path $MosqInstallDir "mosquitto.exe"
    if ($svc) { Stop-Service $ServiceMosq -Force -ErrorAction SilentlyContinue; if (Test-Path $mexe) { & $mexe uninstall *>$null }; Start-Sleep 2 }

    Copy-Item -Path (Join-Path $MosqSrc "*") -Destination $MosqInstallDir -Recurse -Force

    $conf = @"
# PEMF — yerel MQTT broker (installer ile kuruldu, otomatik üretildi)
listener 1883 0.0.0.0
allow_anonymous true
persistence true
persistence_location $($MosqDataRoot -replace '\\','/')/data/
autosave_interval 60
max_queued_messages 10000
max_connections 30
max_keepalive 120
retain_available true
log_dest file $($MosqDataRoot -replace '\\','/')/log/mosquitto.log
log_type error
log_type warning
log_type notice
log_timestamp true
include_dir $($MosqDataRoot -replace '\\','/')/conf.d
"@
    Set-Content -Path (Join-Path $MosqInstallDir "mosquitto.conf") -Value $conf -Encoding ASCII

    & $mexe install
    Start-Sleep 2
    Set-Service -Name $ServiceMosq -StartupType Automatic
    sc.exe failure $ServiceMosq reset= 86400 actions= restart/5000/restart/5000/restart/10000 | Out-Null
    if (-not (Get-NetFirewallRule -DisplayName "PEMF Mosquitto MQTT" -ErrorAction SilentlyContinue)) {
        New-NetFirewallRule -DisplayName "PEMF Mosquitto MQTT" -Direction Inbound -Protocol TCP -LocalPort 1883 -Action Allow -Profile Any | Out-Null
    }
    Start-Service $ServiceMosq -ErrorAction SilentlyContinue
    Log "Mosquitto servisi hazır." "Green"
} else {
    Log "UYARI: Bundled mosquitto bulunamadı ($MosqSrc). MQTT servisi atlandı." "Yellow"
}

# ───────────────────── 2. NSSM (yoksa indir) ─────────────────────
if (-not (Test-Path $NssmExe)) {
    Log "NSSM indiriliyor..." "Yellow"
    New-Item -ItemType Directory -Path (Split-Path $NssmExe) -Force | Out-Null
    try {
        $zip = "$env:TEMP\nssm.zip"
        Invoke-WebRequest "https://nssm.cc/release/nssm-2.24.zip" -OutFile $zip -UseBasicParsing
        Expand-Archive $zip "$env:TEMP\nssm_ext" -Force
        $bin = Get-ChildItem "$env:TEMP\nssm_ext" -Filter nssm.exe -Recurse | Where-Object { $_.FullName -like "*win64*" } | Select-Object -First 1
        if (-not $bin) { $bin = Get-ChildItem "$env:TEMP\nssm_ext" -Filter nssm.exe -Recurse | Select-Object -First 1 }
        Copy-Item $bin.FullName $NssmExe -Force
    } catch {
        Log "HATA: NSSM indirilemedi: $_" "Red"
    }
}

# ───────────────────── 3. BACKEND SERVİSİ (NSSM) ─────────────────────
if (-not (Test-Path $BackendExe)) { Log "HATA: Backend EXE yok: $BackendExe" "Red"; exit 1 }
if (-not (Test-Path $NssmExe))    { Log "HATA: NSSM yok, backend servisi kurulamadı." "Red"; exit 1 }

Log "Backend servisi kuruluyor: $BackendExe" "Yellow"
if (Get-Service -Name $ServiceBackend -ErrorAction SilentlyContinue) {
    & $NssmExe stop $ServiceBackend *>$null
    & $NssmExe remove $ServiceBackend confirm *>$null
    Start-Sleep 2
}
# Mosquitto kendi servisi olduğu için backend onu başlatmaz, sadece izler.
& $NssmExe install $ServiceBackend $BackendExe "--host" "0.0.0.0" "--port" "8000" "--no-mosquitto-ensure"
& $NssmExe set $ServiceBackend AppDirectory        $AppDir
& $NssmExe set $ServiceBackend DisplayName         "PEMF Backend Service"
& $NssmExe set $ServiceBackend Description          "Headless PEMF backend: FastAPI, WebSocket, STM32, MQTT, React Web."
& $NssmExe set $ServiceBackend Start                SERVICE_AUTO_START
& $NssmExe set $ServiceBackend ObjectName           LocalSystem
& $NssmExe set $ServiceBackend AppStdout            "$LogDir\backend_service_stdout.log"
& $NssmExe set $ServiceBackend AppStderr            "$LogDir\backend_service_stderr.log"
& $NssmExe set $ServiceBackend AppRotateFiles       1
& $NssmExe set $ServiceBackend AppRotateBytes       10485760
& $NssmExe set $ServiceBackend AppExit              Default Restart
& $NssmExe set $ServiceBackend AppRestartDelay      5000
& $NssmExe set $ServiceBackend AppStopMethodConsole 15000
& $NssmExe set $ServiceBackend AppThrottle          5000
& $NssmExe set $ServiceBackend AppEnvironmentExtra  "PYTHONUNBUFFERED=1" "PEMF_HEADLESS=1" "PEMF_LOG_DIR=$LogDir"

if (Get-Service -Name $ServiceMosq -ErrorAction SilentlyContinue) {
    sc.exe config $ServiceBackend depend= mosquitto | Out-Null
    Log "Bağımlılık: PemfBackend → mosquitto" "Green"
}

foreach ($r in @(@{n = "PEMF Backend API"; p = "TCP"; port = 8000 }, @{n = "PEMF UDP Discovery"; p = "UDP"; port = 5051 })) {
    if (-not (Get-NetFirewallRule -DisplayName $r.n -ErrorAction SilentlyContinue)) {
        New-NetFirewallRule -DisplayName $r.n -Direction Inbound -Program $BackendExe -Action Allow -Protocol $r.p -LocalPort $r.port -Profile Any | Out-Null
    }
}

& $NssmExe start $ServiceBackend
Start-Sleep 4
Log "Backend servisi durumu: $(& $NssmExe status $ServiceBackend 2>&1)" "Cyan"
Log "Kurulum tamam → http://localhost:8000" "Green"
