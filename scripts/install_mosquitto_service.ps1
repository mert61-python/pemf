# =============================================================================
# PEMF — Mosquitto'yu BAĞIMSIZ Windows Servisi olarak kurar (OFFLINE / mühürlü)
# =============================================================================
# Faz 3 hedefi: 24/7 sunucuda Mosquitto kendi otomatik-başlayan Windows servisi
# olsun; PemfBackend servisi ona `depends` ile bağlansın. Bu script bundle'daki
# bin\mosquitto\ ikilisini kullanır — internet GEREKMEZ (sahada offline kurulum).
#
# Kullanım (Yönetici PowerShell):
#   .\install_mosquitto_service.ps1
#   .\install_mosquitto_service.ps1 -Uninstall
# =============================================================================
param(
    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"

function Write-Status($msg, $color = "White") {
    $ts = Get-Date -Format "HH:mm:ss"
    Write-Host "[$ts] $msg" -ForegroundColor $color
}

# --- Admin kontrolü ---
$principal = New-Object System.Security.Principal.WindowsPrincipal([System.Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([System.Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Status "HATA: Bu script Yönetici (Administrator) olarak çalıştırılmalıdır." "Red"
    exit 1
}

# --- Yollar ---
$ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$GuiRoot     = Split-Path -Parent $ScriptDir
$BundledDir  = Join-Path $GuiRoot "bin\mosquitto"
$InstallDir  = "C:\Program Files\PEMF\mosquitto"
$DataRoot    = "C:\ProgramData\PEMF_System\mosquitto"
$DataDir     = "$DataRoot\data"
$LogDir      = "$DataRoot\log"
$ConfDir     = "$DataRoot\conf.d"
$ServiceName = "mosquitto"
$ExePath     = Join-Path $InstallDir "mosquitto.exe"
$ConfPath    = Join-Path $InstallDir "mosquitto.conf"

# --- Uninstall yolu ---
if ($Uninstall) {
    Write-Status "Mosquitto servisi kaldırılıyor..." "Yellow"
    $svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
    if ($svc) {
        if ($svc.Status -eq "Running") { Stop-Service -Name $ServiceName -Force; Start-Sleep 2 }
        if (Test-Path $ExePath) { & $ExePath uninstall 2>$null }
        Start-Sleep 1
    }
    Write-Status "Tamamlandı. (Veri/log korundu: $DataRoot)" "Green"
    exit 0
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  PEMF — Mosquitto Bağımsız Servis Kurulumu" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# --- 1. Bundle kontrolü ---
if (-not (Test-Path (Join-Path $BundledDir "mosquitto.exe"))) {
    Write-Status "HATA: Bundle'da mosquitto.exe yok: $BundledDir" "Red"
    exit 1
}
Write-Status "Bundle bulundu: $BundledDir" "Green"

# --- 2. Dizinleri oluştur ---
foreach ($d in @($InstallDir, $DataDir, $LogDir, $ConfDir)) {
    if (-not (Test-Path $d)) { New-Item -ItemType Directory -Path $d -Force | Out-Null }
}
Write-Status "Dizinler hazır (Program Files + ProgramData)." "Green"

# --- 3. Bundled ikilileri Install dizinine kopyala (varolan servisi durdurarak) ---
$svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($svc -and $svc.Status -eq "Running") {
    Write-Status "Mevcut mosquitto servisi durduruluyor (dosya kilidi için)..." "Yellow"
    Stop-Service -Name $ServiceName -Force
    Start-Sleep 2
}
Copy-Item -Path (Join-Path $BundledDir "*") -Destination $InstallDir -Recurse -Force
Write-Status "Bundled ikililer kopyalandı: $InstallDir" "Green"

# --- 4. Sertleştirilmiş mosquitto.conf yaz ---
# ESP32 cihazları izole hotspot/LAN üzerinden bağlanır; broker yereldir.
$conf = @"
# PEMF — yerel MQTT broker (Faz 3, bağımsız servis). Otomatik üretildi.
listener 1883 0.0.0.0
allow_anonymous true

# Offline veri koruma
persistence true
persistence_location $($DataDir -replace '\\','/')/
autosave_interval 60
autosave_on_changes true

# Mesaj kuyruğu (ESP'ler offline'dayken biriken mesajlar)
max_queued_messages 10000
max_queued_bytes 0
max_inflight_messages 40

# Bağlantı/keepalive limitleri (8 ESP + backend + yedek)
max_connections 30
max_keepalive 120
retain_available true

# Loglama
log_dest file $($LogDir -replace '\\','/')/mosquitto.log
log_type error
log_type warning
log_type notice
log_type information
log_timestamp true
log_timestamp_format %Y-%m-%dT%H:%M:%S

# Opsiyonel bridge (internet varsa) buraya .conf bırakılabilir
include_dir $($ConfDir -replace '\\','/')
"@
Set-Content -Path $ConfPath -Value $conf -Encoding ASCII
Write-Status "Sertleştirilmiş mosquitto.conf yazıldı: $ConfPath" "Green"

# --- 5. Firewall (TCP 1883) ---
if (-not (Get-NetFirewallRule -DisplayName "PEMF Mosquitto MQTT" -ErrorAction SilentlyContinue)) {
    # P0-3 (GÜVENLİK): 1883 yalnız hotspot subnet'inden (ESP bobinleri) — klinik LAN'a KAPALI.
    # (ESP anon bağlandığından MQTT auth açılamaz; savunma hotspot WPA2 + subnet kısıtı.)
    New-NetFirewallRule -DisplayName "PEMF Mosquitto MQTT" -Direction Inbound `
        -Protocol TCP -LocalPort 1883 -RemoteAddress 192.168.137.0/24 -Action Allow -Profile Any | Out-Null
    Write-Status "Firewall kuralı eklendi: TCP 1883 inbound (yalnız hotspot subnet 192.168.137.0/24)." "Green"
}

# --- 6. Servisi (yeniden) kaydet ---
if ($svc) {
    Write-Status "Eski servis kaydı kaldırılıyor..." "Yellow"
    & $ExePath uninstall 2>$null
    Start-Sleep 1
}
Write-Status "Mosquitto servis olarak kaydediliyor (native install)..." "Yellow"
& $ExePath install
Start-Sleep 2

# mosquitto native servisi config'i exe yanından okur; otomatik başlatma + başlat
Set-Service -Name $ServiceName -StartupType Automatic
sc.exe failure $ServiceName reset= 86400 actions= restart/5000/restart/5000/restart/10000 | Out-Null
Start-Service -Name $ServiceName
Start-Sleep 3

# --- 7. Doğrulama ---
$svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($svc -and $svc.Status -eq "Running") {
    Write-Host ""
    Write-Host "============================================" -ForegroundColor Green
    Write-Host "  ✓ Mosquitto servisi çalışıyor (otomatik)" -ForegroundColor Green
    Write-Host "============================================" -ForegroundColor Green
    Write-Host "  Broker : localhost:1883" -ForegroundColor White
    Write-Host "  Exe    : $ExePath" -ForegroundColor White
    Write-Host "  Conf   : $ConfPath" -ForegroundColor White
    Write-Host "  Log    : $LogDir\mosquitto.log" -ForegroundColor White
    Write-Host "  Kurtarma: çökerse 5sn sonra otomatik restart" -ForegroundColor White
    Write-Host ""
    Write-Host "Sonraki adım: PemfBackend servisini kurun (install_backend_service.ps1)." -ForegroundColor Cyan
    Write-Host "Backend bu servise 'depends= mosquitto' ile bağlanacaktır." -ForegroundColor Cyan
} else {
    Write-Status "HATA: Mosquitto servisi başlatılamadı. services.msc → mosquitto kontrol edin." "Red"
    exit 1
}
