# =============================================================================
# PEMF Gateway — Mosquitto Kurulum ve Yapılandırma Scripti
# =============================================================================
# LattePanda üzerinde Mosquitto MQTT broker'ı kurar ve yapılandırır.
# Kullanım: PowerShell -ExecutionPolicy Bypass -File install_mosquitto.ps1
# =============================================================================

param(
    [switch]$SkipDownload,
    [string]$MosquittoVersion = "2.0.18"
)

$ErrorActionPreference = "Stop"

# --- PATHS ---
$MOSQUITTO_INSTALL_DIR = "C:\Program Files\mosquitto"
$MOSQUITTO_DATA_DIR    = "C:\ProgramData\mosquitto"
$MOSQUITTO_CONF_DIR    = "$MOSQUITTO_DATA_DIR\conf.d"
$MOSQUITTO_LOG_DIR     = "$MOSQUITTO_DATA_DIR\log"
$MOSQUITTO_PERSIST_DIR = "$MOSQUITTO_DATA_DIR\data"
$MOSQUITTO_CERTS_DIR   = "$MOSQUITTO_DATA_DIR\certs"

# Proje config dizini (bu scriptin bulunduğu yer ../config/mosquitto)
$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$PROJECT_CONFIG_DIR = Join-Path (Split-Path -Parent $SCRIPT_DIR) "config\mosquitto"

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  PEMF Gateway - Mosquitto Kurulumu" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# --- 1. Admin Kontrolü ---
$currentPrincipal = New-Object System.Security.Principal.WindowsPrincipal([System.Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $currentPrincipal.IsInRole([System.Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "[HATA] Bu script Administrator olarak çalıştırılmalıdır!" -ForegroundColor Red
    Write-Host "PowerShell'i Yönetici olarak açıp tekrar deneyin." -ForegroundColor Yellow
    exit 1
}

# --- 2. Mosquitto Kurulumu Kontrolü ---
$mosquittoExe = Join-Path $MOSQUITTO_INSTALL_DIR "mosquitto.exe"
if (Test-Path $mosquittoExe) {
    Write-Host "[✓] Mosquitto zaten kurulu: $mosquittoExe" -ForegroundColor Green
} else {
    if (-not $SkipDownload) {
        Write-Host "[*] Mosquitto indiriliyor (v$MosquittoVersion)..." -ForegroundColor Yellow
        
        $downloadUrl = "https://mosquitto.org/files/binary/win64/mosquitto-$MosquittoVersion-install-windows-x64.exe"
        $installerPath = "$env:TEMP\mosquitto-installer.exe"
        
        try {
            [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
            Invoke-WebRequest -Uri $downloadUrl -OutFile $installerPath -UseBasicParsing
            Write-Host "[✓] İndirme tamamlandı." -ForegroundColor Green
        } catch {
            Write-Host "[HATA] İndirme başarısız: $_" -ForegroundColor Red
            Write-Host "Manuel olarak indirin: https://mosquitto.org/download/" -ForegroundColor Yellow
            exit 1
        }
        
        Write-Host "[*] Mosquitto kuruluyor (silent)..." -ForegroundColor Yellow
        Start-Process -FilePath $installerPath -ArgumentList "/S" -Wait
        
        if (Test-Path $mosquittoExe) {
            Write-Host "[✓] Mosquitto kurulumu tamamlandı." -ForegroundColor Green
        } else {
            Write-Host "[HATA] Kurulum başarısız oldu." -ForegroundColor Red
            exit 1
        }
        
        Remove-Item $installerPath -Force -ErrorAction SilentlyContinue
    } else {
        Write-Host "[HATA] Mosquitto bulunamadı ve -SkipDownload belirtildi." -ForegroundColor Red
        exit 1
    }
}

# --- 3. Dizinler Oluştur ---
Write-Host "[*] Dizinler oluşturuluyor..." -ForegroundColor Yellow
@($MOSQUITTO_DATA_DIR, $MOSQUITTO_CONF_DIR, $MOSQUITTO_LOG_DIR, $MOSQUITTO_PERSIST_DIR, $MOSQUITTO_CERTS_DIR) | ForEach-Object {
    if (-not (Test-Path $_)) {
        New-Item -ItemType Directory -Path $_ -Force | Out-Null
        Write-Host "  Oluşturuldu: $_" -ForegroundColor Gray
    }
}

# --- 4. Config Dosyalarını Kopyala ---
Write-Host "[*] Yapılandırma dosyaları kopyalanıyor..." -ForegroundColor Yellow

# Ana config
$mainConf = Join-Path $PROJECT_CONFIG_DIR "mosquitto.conf"
if (Test-Path $mainConf) {
    Copy-Item $mainConf -Destination (Join-Path $MOSQUITTO_INSTALL_DIR "mosquitto.conf") -Force
    Write-Host "  [✓] mosquitto.conf kopyalandı" -ForegroundColor Green
} else {
    Write-Host "  [!] mosquitto.conf bulunamadı: $mainConf" -ForegroundColor Yellow
}

# Bridge config
$bridgeConf = Join-Path $PROJECT_CONFIG_DIR "bridge_hivemq.conf"
if (Test-Path $bridgeConf) {
    Copy-Item $bridgeConf -Destination (Join-Path $MOSQUITTO_CONF_DIR "bridge_hivemq.conf") -Force
    Write-Host "  [✓] bridge_hivemq.conf kopyalandı" -ForegroundColor Green
} else {
    Write-Host "  [!] bridge_hivemq.conf bulunamadı: $bridgeConf" -ForegroundColor Yellow
}

# --- 5. Windows Firewall Kuralı ---
Write-Host "[*] Firewall kuralı ekleniyor (port 1883)..." -ForegroundColor Yellow

$firewallRule = Get-NetFirewallRule -DisplayName "Mosquitto MQTT" -ErrorAction SilentlyContinue
if ($firewallRule) {
    Write-Host "  [✓] Firewall kuralı zaten mevcut." -ForegroundColor Green
} else {
    New-NetFirewallRule `
        -DisplayName "Mosquitto MQTT" `
        -Direction Inbound `
        -Protocol TCP `
        -LocalPort 1883 `
        -Action Allow `
        -Profile Any `
        -Description "PEMF Gateway - ESP32 cihazlarından MQTT bağlantılarına izin ver" | Out-Null
    Write-Host "  [✓] Firewall kuralı eklendi." -ForegroundColor Green
}

# --- 6. Mosquitto Servisini Yapılandır ---
Write-Host "[*] Mosquitto servisi yapılandırılıyor..." -ForegroundColor Yellow

$service = Get-Service -Name "mosquitto" -ErrorAction SilentlyContinue
if ($service) {
    # Servisi durdur, yeniden yapılandır
    if ($service.Status -eq "Running") {
        Stop-Service -Name "mosquitto" -Force
        Start-Sleep -Seconds 2
    }
    
    # Otomatik başlatma ayarla
    Set-Service -Name "mosquitto" -StartupType Automatic
    
    # Servisi başlat
    Start-Service -Name "mosquitto"
    Write-Host "  [✓] Mosquitto servisi çalışıyor (Otomatik Başlatma)." -ForegroundColor Green
} else {
    # Servis olarak kaydet
    Write-Host "  [*] Servis olarak kaydediliyor..." -ForegroundColor Yellow
    $configPath = Join-Path $MOSQUITTO_INSTALL_DIR "mosquitto.conf"
    & "$mosquittoExe" install --config "$configPath"
    Start-Sleep -Seconds 2
    
    Set-Service -Name "mosquitto" -StartupType Automatic
    Start-Service -Name "mosquitto"
    Write-Host "  [✓] Mosquitto servisi kaydedildi ve başlatıldı." -ForegroundColor Green
}

# --- 7. Doğrulama ---
Write-Host ""
Write-Host "[*] Kurulum doğrulanıyor..." -ForegroundColor Yellow
Start-Sleep -Seconds 3

$service = Get-Service -Name "mosquitto" -ErrorAction SilentlyContinue
if ($service -and $service.Status -eq "Running") {
    Write-Host ""
    Write-Host "============================================" -ForegroundColor Green
    Write-Host "  ✓ Mosquitto Kurulumu Başarılı!" -ForegroundColor Green
    Write-Host "============================================" -ForegroundColor Green
    Write-Host "  Broker: localhost:1883" -ForegroundColor White
    Write-Host "  Servis: Otomatik Başlatma" -ForegroundColor White
    Write-Host "  Bridge: HiveMQ Cloud (internet varsa)" -ForegroundColor White
    Write-Host "  Log: $MOSQUITTO_LOG_DIR\mosquitto.log" -ForegroundColor White
    Write-Host "============================================" -ForegroundColor Green
} else {
    Write-Host "[HATA] Mosquitto servisi başlatılamadı!" -ForegroundColor Red
    Write-Host "Manuel kontrol: services.msc → mosquitto" -ForegroundColor Yellow
    exit 1
}
