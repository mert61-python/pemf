"""
Hotspot Manager — Windows Mobile Hotspot Yönetim Servisi

LattePanda gateway başlatıldığında:
- Windows Mobile Hotspot durumunu kontrol eder
- Kapalıysa otomatik açmayı dener
- Durumu periyodik olarak izler

Not: Hotspot açma/kapama admin yetkisi gerektirebilir.
"""

import subprocess
import logging
from PyQt6.QtCore import QObject, pyqtSignal

logger = logging.getLogger(__name__)


class HotspotManager(QObject):
    """
    Windows Mobile Hotspot yönetim servisi.
    
    Signals:
        hotspot_enabled(bool): Hotspot açma/kapama sonucu
        error_occurred(str): Hata mesajı
    """
    
    hotspot_enabled = pyqtSignal(bool)
    error_occurred = pyqtSignal(str)
    
    # Varsayılan SSID ve şifre (Secrets.h ile uyumlu)
    DEFAULT_SSID = "PEMF-Gateway"
    DEFAULT_PASS = "pemf1234"
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_enabled = False
    
    def check_hotspot_status(self) -> bool:
        """Hotspot aktif mi kontrol et (192.168.137.x IP varlığına bakarak)."""
        try:
            result = subprocess.run(
                ["powershell", "-Command",
                 "Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | "
                 "Where-Object { $_.IPAddress -like '192.168.137.*' } | "
                 "Select-Object -ExpandProperty IPAddress"],
                capture_output=True, text=True, timeout=8,
                encoding='cp857', errors='replace',
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            active = bool(result.returncode == 0 and result.stdout.strip())
            self._is_enabled = active
            return active
        except Exception as e:
            logger.debug(f"Hotspot kontrol hatası: {e}")
            return False
    
    def enable_hotspot(self) -> bool:
        """
        Windows Mobile Hotspot'u PowerShell üzerinden aç.
        
        Modern Windows 10/11 Mobile Hotspot API'sini kullanır.
        Not: Admin yetkisi gerektirebilir.
        """
        import threading
        
        def _enable_task():
            if self.check_hotspot_status():
                logger.info("Hotspot zaten aktif.")
                self._is_enabled = True
                self.hotspot_enabled.emit(True)
                return
            
            logger.info("Hotspot açılıyor...")
            
            try:
                # Yöntem 1: Windows Settings API (WinRT) — admin gerekmez
                ps_script = '''
try {
    Add-Type -AssemblyName System.Runtime.WindowsRuntime
    
    $asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { 
        $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and 
        $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' 
    })[0]

    $asTaskAction = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { 
        $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and 
        $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncAction' 
    })[0]
    
    function AwaitResult($WinRtTask, $ResultType) {
        $asTask = $asTaskGeneric.MakeGenericMethod($ResultType)
        $netTask = $asTask.Invoke($null, @($WinRtTask))
        $netTask.Wait(-1) | Out-Null
        return $netTask.Result
    }

    function AwaitAction($WinRtTask) {
        $netTask = $asTaskAction.Invoke($null, @($WinRtTask))
        $netTask.Wait(-1) | Out-Null
    }
    
    [Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager, Windows.Networking.NetworkOperators, ContentType=WindowsRuntime] | Out-Null
    [Windows.Networking.Connectivity.NetworkInformation, Windows.Networking.Connectivity, ContentType=WindowsRuntime] | Out-Null
    
    $connectionProfile = [Windows.Networking.Connectivity.NetworkInformation]::GetInternetConnectionProfile()
    
    # Internet yoksa bile herhangi bir aktif ag profili bul (Windows apisi bos profil ile cokuyor)
    if (-not $connectionProfile) {
        $profiles = [Windows.Networking.Connectivity.NetworkInformation]::GetConnectionProfiles()
        $connectionProfile = $profiles | Select-Object -First 1
    }
    
    if (-not $connectionProfile) {
        Write-Output "NO_PROFILE"
        exit
    }
    
    $manager = [Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager]::CreateFromConnectionProfile($connectionProfile)
    
    # ==========================
    # ESP32 ÇÖZÜMÜ: ŞİFRE, İSİM VE 2.4 GHz BAND ZORLAMASI
    # ==========================
    try {
        $config = $manager.GetCurrentAccessPointConfiguration()
        
        # Ağ ismini ve şifresini Windows üzerinde otomatik ayarla
        $config.Ssid = "PEMF-Gateway"
        $config.Passphrase = "pemf1234"
        
        # Band secimi eger destekleniyorsa 2.4GHz'e sabitlenir. ESP32 5 GHz desteklemez!
        $config.Band = [Windows.Networking.NetworkOperators.TetheringWiFiBand]::TwoPointFourGigahertz
        
        AwaitAction ($manager.ConfigureAccessPointAsync($config))
    } catch {
        # Bazi Windows surumlerinde 2.4GHz secimi veya isim degisikligi desteklenmeyebilir, yoksay.
    }
    
    if ($manager.TetheringOperationalState -ne 'On') {
        $result = AwaitResult ($manager.StartTetheringAsync()) ([Windows.Networking.NetworkOperators.NetworkOperatorTetheringOperationResult])
        if ($result.Status -eq 'Success') {
            Write-Output "OK"
        } else {
            Write-Output "ERROR: $($result.Status)"
        }
    } else {
        Write-Output "ALREADY_ON"
    }
} catch {
    Write-Output "ERROR: $_"
}
'''
                result = subprocess.run(
                    ["powershell", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
                    capture_output=True, text=True, timeout=15,
                    encoding='cp857', errors='replace',
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
                
                output = result.stdout.strip()
                
                if "OK" in output or "ALREADY_ON" in output:
                    logger.info(f"Hotspot başarıyla açıldı: {output}")
                    self._is_enabled = True
                    self.hotspot_enabled.emit(True)
                elif "NO_PROFILE" in output:
                    logger.warning("Hotspot açılamadı: Hiçbir ağ bağlantısı (Ethernet/WiFi) bulunamadı.")
                    
                    # Eski nesil wifi kartlari icin HostedNetwork fallback denemesi
                    try:
                        netsh_res = subprocess.run(
                            "netsh wlan start hostednetwork", 
                            capture_output=True, text=True, shell=True, creationflags=subprocess.CREATE_NO_WINDOW
                        )
                        if "started" in netsh_res.stdout.lower() or "başlatıldı" in netsh_res.stdout.lower():
                            logger.info("Hotspot (HostedNetwork Fallback) ile açıldı.")
                            self._is_enabled = True
                            self.hotspot_enabled.emit(True)
                            return
                    except Exception:
                        pass
                    
                    self.error_occurred.emit(
                        "Cihazda internet veya hiçbir ağ bağlantısı olmadığı için Mobile Hotspot açılamıyor. Wi-Fi'ye bağlanın."
                    )
                    self.hotspot_enabled.emit(False)
                    
            except subprocess.TimeoutExpired:
                logger.error("Hotspot açma timeout")
                self.error_occurred.emit("Hotspot açma zaman aşımına uğradı.")
                self.hotspot_enabled.emit(False)
            except Exception as e:
                logger.error(f"Hotspot açma hatası: {e}")
                self.error_occurred.emit(f"Hotspot açma hatası: {e}")
                self.hotspot_enabled.emit(False)

        # Arka planda çalıştır ve anında dön (GUI block'unu önle)
        threading.Thread(target=_enable_task, daemon=True).start()
        return True
    
    @property
    def is_enabled(self) -> bool:
        return self._is_enabled
