import subprocess
import sys
import re
from PyQt6.QtCore import QRunnable, QThread, pyqtSignal

class PortalStatusCheckerRunnable(QRunnable):
    """
    ESP portal durumunu kontrol etmek için QRunnable (QThreadPool ile async).
    Bloklayıcı subprocess.run işlemini ana thread'den ayırır.
    Timer Optimization: QThreadPool ile async çalışır.
    """
    def __init__(self, callback, logger=None):
        super().__init__()
        self.callback = callback  # Sonuçları ana thread'e iletmek için callback
        self.logger = logger
    
    def run(self):
        """
        Runnable'ın ana çalışma metodu.
        WiFi ağlarını tarar ve PEMF-Coil-X SSID'lerini bulur.
        """
        try:
            # Windows'ta WiFi ağlarını tara (netsh kullanarak)
            # Timeout'u 3 saniyeye düşürdük (GUI performansı için)
            try:
                result = subprocess.run(
                    ['netsh', 'wlan', 'show', 'networks', 'mode=Bssid'],
                    capture_output=True,
                    text=True,
                    timeout=3,  # 3 saniye timeout (GUI performansı için optimize edildi)
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
                )
                
                if result.returncode != 0:
                    # WiFi tarama başarısız
                    if self.logger:
                        self.logger.debug("WiFi tarama başarısız (netsh komutu çalışmadı)")
                    self.callback([])
                    return
                
                # PEMF-Coil-X SSID'lerini bul (optimize edilmiş regex ile)
                # Regex'i compile ederek performansı artırıyoruz
                pemf_pattern = re.compile(r'PEMF-Coil-(\d+)')
                lines = result.stdout.split('\n')
                pemf_ssids = []
                
                # Set kullanarak duplicate kontrolünü optimize ediyoruz
                seen_ids = set()
                
                for line in lines:
                    # SSID satırını bul (optimize edilmiş kontrol)
                    if 'PEMF-Coil-' in line:
                        # SSID numarasını çıkar (PEMF-Coil-1, PEMF-Coil-2, vb.)
                        match = pemf_pattern.search(line)
                        if match:
                            coil_id = int(match.group(1))
                            if coil_id not in seen_ids:
                                seen_ids.add(coil_id)
                                pemf_ssids.append(coil_id)
                
                # Sonuçları callback ile ana thread'e gönder
                self.callback(pemf_ssids)
                
            except subprocess.TimeoutExpired:
                # WiFi tarama timeout oldu
                if self.logger:
                    self.logger.debug("WiFi tarama timeout oldu (3 saniye)")
                self.callback([])
            except FileNotFoundError:
                # netsh komutu bulunamadı
                if self.logger:
                    self.logger.debug("netsh komutu bulunamadı")
                self.callback([])
            except Exception as e:
                # Diğer hatalar
                if self.logger:
                    self.logger.error(f"WiFi tarama hatası: {e}", exc_info=True)
                self.callback([])
                
        except Exception as e:
            if self.logger:
                self.logger.error(f"Portal durumu kontrolü genel hatası: {e}", exc_info=True)
            self.callback([])

class PortalStatusCheckerThread(QThread):
    """
    ESP portal durumunu kontrol etmek için ayrı thread (DEPRECATED - PortalStatusCheckerRunnable kullanılmalı).
    Bloklayıcı subprocess.run işlemini ana thread'den ayırır.
    """
    # Signal: WiFi tarama sonuçlarını ana thread'e iletir
    # Parametre: pemf_ssids (list[int]) - Bulunan PEMF-Coil-X SSID'lerinin coil ID'leri
    portal_scan_completed = pyqtSignal(list)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = None  # MainWindow'dan set edilecek
    
    def set_logger(self, logger):
        """Logger'ı set et (MainWindow'dan çağrılacak)"""
        self.logger = logger
    
    def run(self):
        """
        Thread'in ana çalışma metodu.
        WiFi ağlarını tarar ve PEMF-Coil-X SSID'lerini bulur.
        """
        try:
            # Windows'ta WiFi ağlarını tara (netsh kullanarak)
            # Timeout'u 3 saniyeye düşürdük (GUI performansı için)
            try:
                result = subprocess.run(
                    ['netsh', 'wlan', 'show', 'networks', 'mode=Bssid'],
                    capture_output=True,
                    text=True,
                    timeout=3,  # 3 saniye timeout (GUI performansı için optimize edildi)
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
                )
                
                if result.returncode != 0:
                    # WiFi tarama başarısız
                    if self.logger:
                        self.logger.debug("WiFi tarama başarısız (netsh komutu çalışmadı)")
                    self.portal_scan_completed.emit([])
                    return
                
                # PEMF-Coil-X SSID'lerini bul (optimize edilmiş regex ile)
                # Regex'i compile ederek performansı artırıyoruz
                pemf_pattern = re.compile(r'PEMF-Coil-(\d+)')
                lines = result.stdout.split('\n')
                pemf_ssids = []
                
                # Set kullanarak duplicate kontrolünü optimize ediyoruz
                seen_ids = set()
                
                for line in lines:
                    # SSID satırını bul (optimize edilmiş kontrol)
                    if 'PEMF-Coil-' in line:
                        # SSID numarasını çıkar (PEMF-Coil-1, PEMF-Coil-2, vb.)
                        match = pemf_pattern.search(line)
                        if match:
                            coil_id = int(match.group(1))
                            if coil_id not in seen_ids:
                                seen_ids.add(coil_id)
                                pemf_ssids.append(coil_id)
                
                # Sonuçları signal ile ana thread'e gönder
                self.portal_scan_completed.emit(pemf_ssids)
                
            except subprocess.TimeoutExpired:
                # WiFi tarama timeout oldu
                if self.logger:
                    self.logger.debug("WiFi tarama timeout oldu (3 saniye)")
                self.portal_scan_completed.emit([])
            except FileNotFoundError:
                # netsh komutu bulunamadı
                if self.logger:
                    self.logger.debug("netsh komutu bulunamadı")
                self.portal_scan_completed.emit([])
            except Exception as e:
                # Diğer hatalar
                if self.logger:
                    self.logger.error(f"WiFi tarama hatası: {e}", exc_info=True)
                self.portal_scan_completed.emit([])
                
        except Exception as e:
            if self.logger:
                self.logger.error(f"Portal durumu kontrolü genel hatası: {e}", exc_info=True)
            self.portal_scan_completed.emit([])
