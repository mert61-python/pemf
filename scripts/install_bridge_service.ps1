# =============================================================================
# PEMF MQTT Bridge — Windows Servisi Kurulumu (NSSM ile)
# =============================================================================
# Gereksinimler: Yönetici PowerShell
# Kullanim: .\install_bridge_service.ps1
# =============================================================================

$ErrorActionPreference = "Stop"

function Write-Status($msg, $color = "White") {
    $ts = Get-Date -Format "HH:mm:ss"
    Write-Host "[$ts] $msg" -ForegroundColor $color
}

# --- Yönetici kontrolü ---
$id = [System.Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object System.Security.Principal.WindowsPrincipal($id)
if (-not $principal.IsInRole([System.Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Status "HATA: Bu script Yonetici olarak calistirilmalidir!" "Red"
    Write-Status "Sag tik -> 'PowerShell'i Yonetici Olarak Calistir'" "Yellow"
    pause
    exit 1
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  PEMF MQTT Bridge Servis Kurulumu" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# --- Yollar ---
$ScriptDir    = Split-Path -Parent $MyInvocation.MyCommand.Path
$GuiRoot      = Split-Path -Parent $ScriptDir
$PythonExe    = "C:\Users\LattePanda\anaconda3\envs\gui\python.exe"
$NssmDir      = "C:\nssm"
$NssmExe      = "$NssmDir\nssm.exe"
$ServiceName  = "PemfMqttBridge"
$LogDir       = "C:\ProgramData\PEMF_System\logs"

# --- Python kontrolü ---
if (-not (Test-Path $PythonExe)) {
    # Conda base ortamında da ara
    $fallback = "C:\Users\merta\AppData\Local\Programs\Python\Python39\python.exe"
    $found = Get-Command python -ErrorAction SilentlyContinue
    if ($found) {
        $PythonExe = $found.Source
        Write-Status "Python PATH'te bulundu: $PythonExe" "Green"
    } elseif (Test-Path $fallback) {
        $PythonExe = $fallback
        Write-Status "Python bulundu: $PythonExe" "Green"
    } else {
        Write-Status "HATA: Python bulunamadi: $PythonExe" "Red"
        Write-Status "PythonExe degiskenini script icinde duzeltin." "Yellow"
        pause
        exit 1
    }
} else {
    Write-Status "Python bulundu: $PythonExe" "Green"
}

# --- Bridge script kontrolü ---
$BridgeModule = "$GuiRoot\services\mqtt_bridge.py"
if (-not (Test-Path $BridgeModule)) {
    Write-Status "HATA: Bridge script bulunamadi: $BridgeModule" "Red"
    pause
    exit 1
}
Write-Status "Bridge script bulundu: $BridgeModule" "Green"

# --- Log dizini oluştur ---
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
    Write-Status "Log dizini olusturuldu: $LogDir" "Green"
}

# --- NSSM indir (yoksa) ---
if (-not (Test-Path $NssmExe)) {
    Write-Status "NSSM bulunamadi, indiriliyor..." "Yellow"
    try {
        if (-not (Test-Path $NssmDir)) {
            New-Item -ItemType Directory -Path $NssmDir -Force | Out-Null
        }
        $NssmZip = "$env:TEMP\nssm.zip"
        $NssmUrl = "https://nssm.cc/release/nssm-2.24.zip"
        Write-Status "Indiriliyor: $NssmUrl" "Yellow"
        Invoke-WebRequest -Uri $NssmUrl -OutFile $NssmZip -UseBasicParsing
        Expand-Archive -Path $NssmZip -DestinationPath "$env:TEMP\nssm_ext" -Force
        # 64-bit binary bul
        $NssmBin = Get-ChildItem "$env:TEMP\nssm_ext" -Filter "nssm.exe" -Recurse |
            Where-Object { $_.FullName -like "*win64*" } | Select-Object -First 1
        if (-not $NssmBin) {
            $NssmBin = Get-ChildItem "$env:TEMP\nssm_ext" -Filter "nssm.exe" -Recurse |
                Select-Object -First 1
        }
        Copy-Item $NssmBin.FullName $NssmExe -Force
        Write-Status "NSSM kuruldu: $NssmExe" "Green"
    } catch {
        Write-Status "NSSM indirilemedi: $_" "Red"
        Write-Status "Manuel indirin: https://nssm.cc/download" "Yellow"
        Write-Status "nssm.exe dosyasini buraya koyun: $NssmExe" "Yellow"
        pause
        exit 1
    }
} else {
    Write-Status "NSSM bulundu: $NssmExe" "Green"
}

# --- Mevcut servisi kaldır ---
Write-Status "Mevcut servis kontrol ediliyor..." "Yellow"
$svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue

if ($svc) {
    Write-Status "Mevcut servis kaldiriliyor..." "Yellow"
    & $NssmExe stop $ServiceName *>$null
    Start-Sleep -Seconds 2
    & $NssmExe remove $ServiceName confirm *>$null
    Start-Sleep -Seconds 2
    Write-Status "Eski servis kaldirildi" "Green"
}

# --- Servisi kur ---
Write-Status "Servis kuruluyor: $ServiceName" "Yellow"

& $NssmExe install $ServiceName $PythonExe "$BridgeModule"

& $NssmExe set $ServiceName AppDirectory       $GuiRoot
& $NssmExe set $ServiceName DisplayName        "PEMF MQTT Bridge Service"
& $NssmExe set $ServiceName Description        "PEMF sisteminin yerel Mosquitto broker ile HiveMQ Cloud arasinda kopru servisi. GUI kapali olsa bile ESP verilerini buluta iletir."
& $NssmExe set $ServiceName Start              SERVICE_AUTO_START
& $NssmExe set $ServiceName ObjectName         LocalSystem

# Log dosyaları
& $NssmExe set $ServiceName AppStdout          "$LogDir\mqtt_bridge_service.log"
& $NssmExe set $ServiceName AppStderr          "$LogDir\mqtt_bridge_service_error.log"
& $NssmExe set $ServiceName AppRotateFiles     1
& $NssmExe set $ServiceName AppRotateBytes     10485760

# Crash recovery — otomatik yeniden başlat
& $NssmExe set $ServiceName AppExit            Default Restart
& $NssmExe set $ServiceName AppRestartDelay    5000

# Python path
& $NssmExe set $ServiceName AppEnvironmentExtra "PYTHONPATH=$GuiRoot" "PYTHONUNBUFFERED=1"

Write-Status "Servis yapilandirmasi tamamlandi" "Green"

# --- Mosquitto bağımlılığı (Mosquitto önce başlasın) ---
try {
    $svc = Get-Service -Name "mosquitto" -ErrorAction SilentlyContinue
    if ($svc) {
        sc.exe config $ServiceName depend= mosquitto | Out-Null
        Write-Status "Mosquitto bagimlilik eklendi (Mosquitto once baslar)" "Green"
    }
} catch { }

# --- Firewall kuralı ---
try {
    $rule = Get-NetFirewallRule -DisplayName "PEMF MQTT Bridge" -ErrorAction SilentlyContinue
    if (-not $rule) {
        New-NetFirewallRule `
            -DisplayName "PEMF MQTT Bridge" `
            -Direction Outbound `
            -Program $PythonExe `
            -Action Allow `
            -Profile Any | Out-Null
        Write-Status "Firewall kurali eklendi (Python outbound)" "Green"
    }
} catch {
    Write-Status "Firewall kurali eklenemedi (opsiyonel): $_" "Yellow"
}

# --- Servisi başlat ---
Write-Status "Servis baslatiliyor..." "Yellow"
Start-Sleep -Seconds 1
try {
    & $NssmExe start $ServiceName
    Start-Sleep -Seconds 4
    $status = & $NssmExe status $ServiceName 2>&1
    if ($status -like "*SERVICE_RUNNING*") {
        Write-Status "Servis basariyla baslatildi!" "Green"
    } else {
        Write-Status "Servis durumu: $status" "Yellow"
        Write-Status "Log: Get-Content '$LogDir\mqtt_bridge_service.log' -Tail 20" "Cyan"
    }
} catch {
    Write-Status "Servis baslatma hatasi: $_" "Red"
}

# --- Sonuç ---
Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "  Kurulum Tamamlandi!" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Servis adi   : $ServiceName" -ForegroundColor White
Write-Host "  Python       : $PythonExe" -ForegroundColor White
Write-Host "  Baslama      : Otomatik (Windows acilisinda)" -ForegroundColor White
Write-Host "  Log dosyasi  : $LogDir\mqtt_bridge_service.log" -ForegroundColor White
Write-Host ""
Write-Host "  Yonetim komutlari:" -ForegroundColor Cyan
Write-Host "    Durum   : $NssmExe status $ServiceName" -ForegroundColor Gray
Write-Host "    Durdur  : $NssmExe stop $ServiceName" -ForegroundColor Gray
Write-Host "    Baslar  : $NssmExe start $ServiceName" -ForegroundColor Gray
Write-Host "    Kaldir  : $NssmExe remove $ServiceName confirm" -ForegroundColor Gray
Write-Host "    Canlı log: Get-Content '$LogDir\mqtt_bridge_service.log' -Tail 30 -Wait" -ForegroundColor Gray
Write-Host ""
pause
