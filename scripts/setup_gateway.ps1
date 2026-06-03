# =============================================================================
# PEMF Gateway — Windows Mobile Hotspot + Mosquitto + GUI Başlatma
# =============================================================================
# LattePanda açıldığında bu script çalışır:
# 1. Windows Mobile Hotspot'u etkinleştirir
# 2. Mosquitto MQTT broker çalışıyor mu kontrol eder
# 3. GUI uygulamasını başlatır
#
# Kullanım: PowerShell -ExecutionPolicy Bypass -File setup_gateway.ps1
# Otomatik başlatma: Task Scheduler'a kaydet veya shell:startup'a kısayol ekle
# =============================================================================

param(
    [string]$HotspotSSID = "PEMF-Gateway",
    [string]$HotspotPassword = "pemf1234",
    [switch]$StartGUI,
    [switch]$SkipHotspot
)

$ErrorActionPreference = "Continue"

function Write-Status($message, $color = "White") {
    $timestamp = Get-Date -Format "HH:mm:ss"
    Write-Host "[$timestamp] $message" -ForegroundColor $color
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  PEMF Gateway - Sistem Başlatma" -ForegroundColor Cyan  
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# =============================================================================
# 1. WINDOWS MOBILE HOTSPOT
# =============================================================================
if (-not $SkipHotspot) {
    Write-Status "Mobile Hotspot yapılandırılıyor..." "Yellow"
    
    try {
        # Windows Mobile Hotspot API (Windows 10/11)
        Add-Type -AssemblyName System.Runtime.WindowsRuntime
        
        # IAsyncAction icin (sonuc donmeyen async — ConfigureAccessPointAsync)
        $asTaskAction = ([System.WindowsRuntimeSystemExtensions].GetMethods() | 
            Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncAction' })[0]
        
        # IAsyncOperation<T> icin (sonuc donen async — StartTetheringAsync)
        $asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | 
            Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
        
        Function Await($WinRtTask) {
            $netTask = $asTaskAction.Invoke($null, @($WinRtTask))
            $netTask.Wait(-1) | Out-Null
        }
        
        Function AwaitResult($WinRtTask, $ResultType) {
            $asTask = $asTaskGeneric.MakeGenericMethod($ResultType)
            $netTask = $asTask.Invoke($null, @($WinRtTask))
            $netTask.Wait(-1) | Out-Null
            $netTask.Result
        }
        
        # Tethering Manager al
        [Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager, Windows.Networking.NetworkOperators, ContentType=WindowsRuntime] | Out-Null
        $connectionProfile = [Windows.Networking.Connectivity.NetworkInformation, Windows.Networking.Connectivity, ContentType=WindowsRuntime]::GetInternetConnectionProfile()
        
        if ($connectionProfile) {
            $tetheringManager = [Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager]::CreateFromConnectionProfile($connectionProfile)
        } else {
            # Internet yoksa varsayilan WiFi adaptor ile hotspot ac
            Write-Status "Internet baglantisi yok, varsayilan adaptor ile devam ediliyor..." "Yellow"
            # Alternatif: netsh kullan
            $useNetsh = $true
        }
        
        if (-not $useNetsh -and $tetheringManager) {
            # Yapilandirmayi ayarla
            $config = $tetheringManager.GetCurrentAccessPointConfiguration()
            $config.Ssid = $HotspotSSID
            $config.Passphrase = $HotspotPassword
            
            # Band: 2.4GHz (ESP32 uyumlu)
            try {
                # Windows 11 ile band secimi
                $config.Band = [Windows.Networking.NetworkOperators.TetheringWiFiBand]::TwoPointFourGigahertz
            } catch {
                # Windows 10'da band secimi olmayabilir
            }
            
            # ConfigureAccessPointAsync -> IAsyncAction (sonuc donmez)
            Await ($tetheringManager.ConfigureAccessPointAsync($config))
            Write-Status "Hotspot yapilandirmasi uygulandi." "White"
            
            # Hotspot durumunu kontrol et
            $state = $tetheringManager.TetheringOperationalState
            
            if ($state -ne "On") {
                Write-Status "Hotspot baslatiliyor (SSID: $HotspotSSID)..." "Yellow"
                # StartTetheringAsync -> IAsyncOperation<Result> (sonuc doner)
                $startResult = AwaitResult ($tetheringManager.StartTetheringAsync()) ([Windows.Networking.NetworkOperators.NetworkOperatorTetheringOperationResult])
                
                if ($startResult.Status -eq "Success") {
                    Write-Status "Mobile Hotspot aktif: $HotspotSSID" "Green"
                } else {
                    Write-Status "Hotspot baslatma sorunu: $($startResult.Status)" "Yellow"
                    Write-Status "netsh ile deneniyor..." "Yellow"
                    $useNetsh = $true
                }
            } else {
                Write-Status "Mobile Hotspot zaten aktif: $HotspotSSID" "Green"
            }
        }
        
        # netsh fallback
        if ($useNetsh) {
            netsh wlan set hostednetwork mode=allow ssid=$HotspotSSID key=$HotspotPassword | Out-Null
            netsh wlan start hostednetwork | Out-Null
            Write-Status "Mobile Hotspot baslatildi (netsh): $HotspotSSID" "Green"
        }
    }
    catch {
        Write-Status "Hotspot otomatik baslatilamadi: $_" "Red"
        Write-Status "Manuel olarak baslatin:" "Yellow"
        Write-Status "  Ayarlar > Ag ve Internet > Mobil Erisim Noktasi" "Yellow"
        Write-Status "  SSID: $HotspotSSID | Band: 2.4GHz" "Yellow"
    }
}

# =============================================================================
# 2. MOSQUITTO BROKER
# =============================================================================
Write-Status "Mosquitto broker kontrol ediliyor..." "Yellow"

$service = Get-Service -Name "mosquitto" -ErrorAction SilentlyContinue

if (-not $service) {
    Write-Status "Mosquitto servisi bulunamadı!" "Red"
    Write-Status "Önce install_mosquitto.ps1 scriptini çalıştırın." "Yellow"
} elseif ($service.Status -ne "Running") {
    Write-Status "Mosquitto servisi başlatılıyor..." "Yellow"
    try {
        Start-Service -Name "mosquitto"
        Start-Sleep -Seconds 2
        
        $service = Get-Service -Name "mosquitto"
        if ($service.Status -eq "Running") {
            Write-Status "✓ Mosquitto broker çalışıyor (port 1883)" "Green"
        } else {
            Write-Status "Mosquitto başlatılamadı!" "Red"
        }
    } catch {
        Write-Status "Mosquitto başlatma hatası: $_" "Red"
    }
} else {
    Write-Status "✓ Mosquitto broker çalışıyor (port 1883)" "Green"
}

# =============================================================================
# 3. AĞ BİLGİLERİ
# =============================================================================
Write-Status "Ağ bilgileri:" "Cyan"

# Hotspot IP
$hotspotIP = "192.168.137.1"
$adapters = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | 
    Where-Object { $_.IPAddress -like "192.168.137.*" }
if ($adapters) {
    $hotspotIP = $adapters[0].IPAddress
}
Write-Status "  Hotspot IP: $hotspotIP" "White"

# Internet IP
$internetIP = (Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | 
    Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "192.168.137.*" -and $_.IPAddress -notlike "169.254.*" -and $_.InterfaceAlias -notlike "*Loopback*" } | 
    Select-Object -First 1).IPAddress
if ($internetIP) {
    Write-Status "  Internet IP: $internetIP" "White"
} else {
    Write-Status "  Internet: Bağlı değil (offline mod)" "Yellow"
}

# MQTT broker bağlantı durumu
try {
    $tcpClient = New-Object System.Net.Sockets.TcpClient
    $tcpClient.Connect("127.0.0.1", 1883)
    $tcpClient.Close()
    Write-Status "  MQTT Broker: ✓ Port 1883 açık" "Green"
} catch {
    Write-Status "  MQTT Broker: ✗ Port 1883 kapalı" "Red"
}

# =============================================================================
# 4. GUI BAŞLATMA (Opsiyonel)
# =============================================================================
if ($StartGUI) {
    Write-Status "PEMF GUI başlatılıyor..." "Yellow"
    
    $guiDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
    $pythonPath = "C:\Users\LattePanda\anaconda3\envs\gui\python.exe"
    $mainPy = Join-Path $guiDir "main.py"
    
    if (Test-Path $pythonPath) {
        Start-Process -FilePath $pythonPath -ArgumentList $mainPy -WorkingDirectory $guiDir
        Write-Status "✓ GUI başlatıldı." "Green"
    } else {
        Write-Status "Python bulunamadı: $pythonPath" "Red"
    }
}

# =============================================================================
# ÖZET
# =============================================================================
Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  PEMF Gateway Durumu" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  Hotspot SSID : $HotspotSSID" -ForegroundColor White
Write-Host "  Hotspot IP   : $hotspotIP" -ForegroundColor White
Write-Host "  MQTT Broker  : localhost:1883" -ForegroundColor White
if ($internetIP) {
    Write-Host "  Internet     : Bağlı ($internetIP)" -ForegroundColor Green
    Write-Host "  Bridge       : HiveMQ Cloud aktif" -ForegroundColor Green
} else {
    Write-Host "  Internet     : Offline" -ForegroundColor Yellow
    Write-Host "  Bridge       : Devre dışı (offline mod)" -ForegroundColor Yellow
}
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "ESP'ler '$HotspotSSID' WiFi ağına bağlanmalı." -ForegroundColor White
Write-Host "MQTT broker adresi: $hotspotIP`:1883" -ForegroundColor White
