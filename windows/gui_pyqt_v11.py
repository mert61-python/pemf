"""
PEMF vet system GUI Uygulaması

Bu modül, PEMF (Pulsed Electromagnetic Field) vet sisteminin grafik kullanıcı arayüzünü (GUI) 
sağlar. Uygulama, sensör verilerini gerçek zamanlı olarak görselleştirir ve PWM sinyallerini kontrol eder.

Ana Bileşenler:
    - MainWindow: Ana uygulama penceresi ve tüm GUI bileşenlerini içerir
    - SensorDataWindow: Sensör verilerini görselleştiren pencere
    - SignalGeneratorWindow: PWM sinyallerini kontrol eden pencere

Sorumluluklar:
    - Sistem durumunu izleme ve loglama
    - Kullanıcı arayüzü etkileşimlerini yönetme
@author: merta
"""

import os
import sys
import time
import json

# Add parent directory to path for module imports
if __name__ == "__main__":
    current_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(current_dir)
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)

from utils.patient_input_validator import PatientInputValidator
from utils.path_utils import get_unique_device_id, initialize_database
import matplotlib
import threading
import logging
import logging.handlers
import ctypes
import shutil
import subprocess
import tempfile
from datetime import datetime
from collections import deque
from queue import Queue
from typing import Optional

# Add parent directory to path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

import paho.mqtt.client as mqtt
import ssl  # SSL/TLS için gerekli
import socket  # DNS ve network hataları için gerekli

matplotlib.use("QtAgg")
from PyQt6.QtWidgets import QMessageBox
from pathlib import Path
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QLabel,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QScrollArea,
    QLineEdit,
    QGridLayout,
    QSizePolicy,
    QProgressBar,
    QProgressDialog
)
from PyQt6.QtCore import QTimer, Qt, pyqtSignal, QThread, QThreadPool, QRunnable
from PyQt6.QtGui import QIcon, QPixmap
from windows.splash_screen import show_splash_screen, show_closing_screen
from utils.notification_panel import NotificationPanel
from database.patient_database import get_patient_database
from database.treatment_history_db import get_treatment_db
from database.session_manager import get_session_manager
# Design System
from styles import StyleMixin
# Responsive Utils
from utils.responsive_utils import (
    make_resizable, scale_font, scale_margins, 
    get_responsive_spacing, get_responsive_font_size,
    apply_responsive_layout, get_screen_info
)
# Metrics Collection
from utils.metrics_collector import get_metrics_collector, timer as metrics_timer
# Local imports
import numpy as np
import pyqtgraph as pg
# scipy import kaldırıldı - Spline interpolation artık kullanılmıyor (performans ve netlik için)

# OpenGL devre dışı - eski bilgisayarlarda uyumluluk için software rendering kullan
pg.setConfigOptions(useOpenGL=False, enableExperimental=False)
pg.setConfigOption('background', '#1e1e2e')

class TicksAxis(pg.AxisItem):
    def tickStrings(self, values, scale, spacing):
        return [f"{value:.1f}" for value in values]

def resource_path(relative_path):
    """
    Kaynak dosyalarının mutlak yolunu alır, hem geliştirme hem de PyInstaller için çalışır.
    """
    # PyInstaller'ın geçici yolunu kullan veya geliştirme ortamında göreceli yolu kullan
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        base_path = Path(sys._MEIPASS)
        # PyInstaller'da pemf_gui klasörü root'ta olabilir
        full_path = base_path / relative_path
        if not full_path.exists():
            # pemf_gui prefix'i ile dene
            full_path = base_path / "pemf_gui" / relative_path
        return str(full_path)
    else:
        # Geliştirme ortamında, bu dosyanın konumuna göre yolu belirle
        base_path = Path(__file__).parent.parent / "pemf_gui"
    return str(base_path / relative_path)

def get_app_data_directory() -> Path:
    """
    Uygulama yapılandırması ve durum verilerini saklamak için dizini alır.
    
    İşletim sistemine göre uygun uygulama veri dizinini belirler ve dizinin var olduğundan emin olur.
    Windows'ta AppData/Local, diğer sistemlerde ~/.local/share dizinini kullanır.
    
    Returns:
        Path: Uygulama veri dizininin yolu (Windows'ta AppData/Local içinde)
    """
    if sys.platform == 'win32':
        app_data = Path(os.getenv('LOCALAPPDATA', Path.home() / 'AppData' / 'Local'))
    else:
        app_data = Path.home() / '.local' / 'share'

    app_dir = app_data / 'PEMF_System'
    app_dir.mkdir(parents=True, exist_ok=True)
    return app_dir

class DigitalTwinFileCopyThread(QThread):
    """
    Tek EXE performans optimizasyonu:
    Dosyaları her seferinde Temp'e açmak yerine, AppData'ya bir kez açar.
    Sadece sürüm değişirse tekrar kopyalar.
    """
    # Signal: İlerleme bilgisini ana thread'e iletir
    # Parametreler: current_step (int), total_steps (int), message (str)
    progress_updated = pyqtSignal(int, int, str)
    
    # Signal: Hata oluştuğunda
    # Parametre: error_message (str)
    error_occurred = pyqtSignal(str)
    
    # Signal: Kopyalama tamamlandığında
    # Parametreler: exe_path (str), pemf_temp_dir (str), success (bool)
    copy_completed = pyqtSignal(str, str, bool)
    
    def __init__(self, build_pemf_path, pemf_temp_dir, logger, parent=None):
        super().__init__(parent)
        self.build_pemf_path = Path(build_pemf_path)  # PyInstaller içindeki gömülü kaynak (_MEIPASS)
        self.pemf_temp_dir = Path(pemf_temp_dir)      # Kalıcı hedef klasör (AppData)
        self.logger = logger
    
    def get_embedded_version(self):
        """Gömülü dosyaların versiyonunu (veya tarihini) alır"""
        try:
            # En basit yöntem: Gömülü EXE'nin boyutunu ve tarihini referans al
            # Veya build sırasında koyduğunuz bir version.txt dosyasını okuyun
            embedded_exe = self.build_pemf_path / "PEMF.exe"
            if embedded_exe.exists():
                stat = embedded_exe.stat()
                return f"{stat.st_size}_{stat.st_mtime}"
            return "0"
        except Exception:
            return "0"
    
    def run(self):
        """
        Thread'in ana çalışma metodu.
        Sürüm kontrolü yapar, gerekirse dosyaları kopyalar.
        """
        try:
            # Hedef klasör yoksa oluştur
            self.pemf_temp_dir.mkdir(parents=True, exist_ok=True)
            
            # 1. VERSİYON KONTROLÜ (Performansın Sırrı Burası)
            current_version_hash = self.get_embedded_version()
            version_file = self.pemf_temp_dir / "version.lock"
            
            should_copy = True
            
            # Eğer hedefte sürüm dosyası varsa ve uyuşuyorsa kopyalamayı atla
            if version_file.exists() and (self.pemf_temp_dir / "PEMF.exe").exists():
                try:
                    with open(version_file, 'r') as f:
                        installed_version = f.read().strip()
                    
                    if installed_version == current_version_hash:
                        if self.logger:
                            self.logger.info("Digital Twin dosyaları güncel. Kopyalama atlanıyor (Hızlı Başlatma).")
                        should_copy = False
                except Exception:
                    should_copy = True  # Dosya bozuksa tekrar kopyala
            
            if not should_copy:
                # HIZLI YOL: Kopyalama yok, direkt bitir
                exe_path = self.pemf_temp_dir / "PEMF.exe"
                self.progress_updated.emit(100, 100, "Hazır!")
                self.copy_completed.emit(str(exe_path), str(self.pemf_temp_dir), True)
                return
            
            # --- KOPYALAMA İŞLEMİ (Sadece ilk kez veya güncellemede çalışır) ---
            if self.logger:
                self.logger.info("Digital Twin kurulumu yapılıyor (İlk Çalıştırma)...")
            
            # Temiz kurulum için eski dosyaları sil
            if self.pemf_temp_dir.exists():
                try:
                    shutil.rmtree(self.pemf_temp_dir)
                    self.pemf_temp_dir.mkdir(parents=True, exist_ok=True)
                except Exception as e:
                    if self.logger:
                        self.logger.warning("Eski dosyalar temizlenirken hata (kritik değil): %s", e)
            
            # Kopyalanacaklar listesi (Unity Build Klasör Yapısı)
            items_to_copy = [
                "PEMF.exe",
                "UnityPlayer.dll",
                "UnityCrashHandler64.exe",
                "PEMF_Data",
                "MonoBleedingEdge"
            ]
            
            total_items = len(items_to_copy)
            
            for index, item_name in enumerate(items_to_copy):
                src = self.build_pemf_path / item_name
                dst = self.pemf_temp_dir / item_name
                
                self.progress_updated.emit(index + 1, total_items + 1, f"Kuruluyor: {item_name}...")
                
                if not src.exists():
                    # Bazı buildlerde MonoBleedingEdge olmayabilir, devam et
                    if self.logger:
                        self.logger.debug("Kaynak bulunamadı (atlanıyor): %s", src)
                    continue
                    
                try:
                    if src.is_dir():
                        shutil.copytree(src, dst)
                    else:
                        shutil.copy2(src, dst)
                    if self.logger:
                        self.logger.debug("Kopyalandı: %s -> %s", item_name, dst)
                except Exception as e:
                    if self.logger:
                        self.logger.warning("Kopyalama hatası (%s): %s", item_name, e)
                    # Kritik dosya değilse devam et
            
            # Yeni versiyon bilgisini yaz
            try:
                with open(self.pemf_temp_dir / "version.lock", 'w') as f:
                    f.write(current_version_hash)
            except Exception as e:
                if self.logger:
                    self.logger.warning("Versiyon dosyası yazılamadı: %s", e)
            
            # --- DÜZELTME 1: Dosya sisteminin rahatlaması için bekleme ---
            # Antivirüs taraması ve I/O flush için işletim sistemine zaman tanıyoruz
            if self.logger:
                self.logger.info("Dosya sistemi stabilizasyonu bekleniyor (8 saniye)...")
            
            # İlk kurulumda daha uzun bekle (antivirüs taraması için)
            for i in range(8):
                time.sleep(1.0)
                if self.logger:
                    self.logger.debug(f"Bekleme: {i+1}/8 saniye")
            # -------------------------------------------------------------

            exe_path = self.pemf_temp_dir / "PEMF.exe"
            
            # Son kontrol: PEMF.exe erişilebilir mi?
            if not exe_path.exists():
                error_msg = f"Kopyalama sonrası PEMF.exe bulunamadı: {exe_path}"
                if self.logger:
                    self.logger.error(error_msg)
                self.error_occurred.emit(error_msg)
                self.copy_completed.emit("", "", False)
                return
            
            if self.logger:
                self.logger.info(f"Kurulum başarılı! PEMF.exe hazır: {exe_path}")
            
            self.progress_updated.emit(total_items + 1, total_items + 1, "Kurulum tamamlandı!")
            self.copy_completed.emit(str(exe_path), str(self.pemf_temp_dir), True)
            
        except Exception as e:
            error_msg = f"Dosya kopyalama hatası: {str(e)}"
            if self.logger:
                self.logger.error(error_msg, exc_info=True)
            self.error_occurred.emit(error_msg)
            self.copy_completed.emit("", "", False)

class AsyncFileWriter(QRunnable):
    """
    Async file writing to prevent main thread blocking.
    """
    def __init__(self, file_path, data, logger=None):
        super().__init__()
        self.file_path = file_path
        self.data = data
        self.logger = logger
    
    def run(self):
        """Write data to file in background thread"""
        try:
            with open(self.file_path, 'w', encoding='utf-8') as f:
                f.write(str(self.data))
            if self.logger:
                self.logger.debug(f"Async file write completed: {self.file_path}")
        except Exception as e:
            if self.logger:
                self.logger.error(f"Async file write failed: {e}")

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
            import subprocess
            import re
            
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



class MainWindow(QMainWindow, StyleMixin):
    """
    PEMF Medikal Sistem uygulamasının ana pencere sınıfı.
    
    Bu sınıf, uygulamanın ana penceresini ve tüm temel işlevlerini yönetir.
    kullanıcı arayüzünü oluşturur ve alt pencereleri 
    (sensör verileri, sinyal üreteci, vb.) yönetir.
    
    Design System entegrasyonu ile merkezi stil yönetimi kullanır.
    """
    # Yazılım sürümü
    SOFTWARE_VERSION = "1"
    
    # Benzersiz cihaz kimliği (uzaktan izleme için)
    device_id = None
    
    # MQTT sensor data signal - coil_id (str), sensor_data (dict)
    sensor_data_received = pyqtSignal(str, dict)
    # ESP status update signal - coil_id (str), status_data (dict)
    esp_status_received = pyqtSignal(str, dict)
    # Coil status updated signal - coil_id (str), status_data (dict) - for UnifiedControlWindow
    coil_status_updated = pyqtSignal(str, dict)
    # Sensor data updated signal - coil_id (str), sensor_data (dict) - for UnifiedControlWindow
    sensor_data_updated = pyqtSignal(str, dict)
    # MQTT connected signal - for UnifiedControlWindow
    mqtt_connected = pyqtSignal()
    # MQTT disconnected signal - for UnifiedControlWindow
    mqtt_disconnected = pyqtSignal()
    
    # Portal notification signal (coil_id, message)
    portal_notification_received = pyqtSignal(str, str)
    
    # Thread-safe signals for coil control (from UnifiedControlWindow)
    # These signals ensure only MainWindow writes to MQTT, preventing conflicts
    # Parameters: int (coil_num), dict (command with 'command', 'command_id', 'freq', 'duty', 'duration', 'timestamp')
    coil_control_requested = pyqtSignal(int, dict)
    
    # Patient saved signal - notify unified control window to refresh patient list
    patient_saved = pyqtSignal()
    
    # ============ Thread-Safe Active Coils Management ============
    @property
    def active_coils(self):
        """Thread-safe getter for active coils set"""
        self.active_coils_mutex.lock()
        try:
            return set(self._active_coils)  # Return copy
        finally:
            self.active_coils_mutex.unlock()
    
    def add_active_coil(self, coil_id):
        """
        Thread-safe method to add a coil to active set
        Returns: bool - True if this is the first coil
        """
        self.active_coils_mutex.lock()
        try:
            self._active_coils.add(coil_id)
            return len(self._active_coils) == 1
        finally:
            self.active_coils_mutex.unlock()
    
    def remove_active_coil(self, coil_id):
        """
        Thread-safe method to remove a coil from active set
        Returns: bool - True if this was the last coil
        """
        self.active_coils_mutex.lock()
        try:
            self._active_coils.discard(coil_id)
            return len(self._active_coils) == 0
        finally:
            self.active_coils_mutex.unlock()
    
    def is_coil_active(self, coil_id):
        """
        Thread-safe method to check if a coil is active
        Returns: bool
        """
        self.active_coils_mutex.lock()
        try:
            return coil_id in self._active_coils
        finally:
            self.active_coils_mutex.unlock()
    
    def get_active_coils_count(self):
        """
        Thread-safe method to get number of active coils
        Returns: int
        """
        self.active_coils_mutex.lock()
        try:
            return len(self._active_coils)
        finally:
            self.active_coils_mutex.unlock()
    # ============================================================

    def handle_connection_error(self, error_message):
        """
        Bağlantı hatalarını işler ve kullanıcıya bildirir.
        
        GUI'yi dondurmamak için QMessageBox yerine notification panel kullanır.
        Notification panel mevcut değilse, hata mesajını log dosyasına kaydeder.
        
        Args:
            error_message (str): Gösterilecek hata mesajı
        """


        # Non-blocking bildirim göster
        if hasattr(self, 'notification_panel'):
            self.notification_panel.add_notification(f"Bağlantı Hatası: {error_message}", "error")
        else:
            # Fallback: konsola yazdır
            self.logger.error(f"Bağlantı Hatası: {error_message}")

   

    def closeEvent(self, event):
        """
        Uygulama kapatıldığında çağrılır - hızlı ve basit kapanış
        Thread-safe cleanup ve async file I/O
        """
        # Kapanma durumunu işaretle
        self.is_closing = True
        
        try:
            # MQTT callback cleanup (Memory Leak Fix)
            if hasattr(self, 'mqtt_client') and self.mqtt_client:
                self.logger.info("Cleaning up MQTT callbacks...")
                self.mqtt_client.on_connect = None
                self.mqtt_client.on_disconnect = None
                self.mqtt_client.on_message = None
                self.mqtt_client.on_subscribe = None
            # Tüm timer'ları durdur ve temizle (Orphaned Timer Fix)
            for timer_name in ['unified_1hz_timer', 'graph_update_timer', 'connection_check_timer', 
                             'mqtt_reconnect_timer', 'portal_check_timer']:
                if hasattr(self, timer_name):
                    timer = getattr(self, timer_name)
                    if timer and timer.isActive():
                        timer.stop()
                        timer.deleteLater()  # Proper cleanup
            
            # Portal thread pool - kısa timeout
            if hasattr(self, 'portal_thread_pool'):
                self.portal_thread_pool.waitForDone(50)
            
            # ❌ KALDIRILDI: Tüm bobinlere stop komutu gönderme
            # Kullanıcı GUI'yi kapatsa bile ESP'ler çalışmaya devam etsin
            # PWM sadece kullanıcı açıkça stop butonuna bastığında dursun
            # if hasattr(self, 'mqtt_client') and self.mqtt_client:
            #     for coil_id in range(1, 9):
            #         command = {"command": "stop", "command_id": f"close_{coil_id}_{int(current_time * 1000)}"}
            #         self.mqtt_client.publish(f"pemf/coil/{coil_id}/control", json.dumps(command), qos=0)
            
            # Alt pencereleri kapat
            for attr_name in ['unified_control_window', 'treatment_history_window', 'sensor_data_window', 'kpi_dashboard_window']:
                if hasattr(self, attr_name):
                    window = getattr(self, attr_name, None)
                    if window:
                        try:
                            window.close()
                        except:
                            pass
            
            # Çalışma süresini async kaydet (File I/O Optimization)
            if hasattr(self, 'working_time_file') and hasattr(self, 'working_seconds'):
                try:
                    writer = AsyncFileWriter(
                        self.working_time_file,
                        self.working_seconds,
                        self.logger
                    )
                    QThreadPool.globalInstance().start(writer)
                except:
                    pass
            
            # MQTT temizle
            if hasattr(self, 'mqtt_client') and self.mqtt_client:
                try:
                    self.mqtt_client.disconnect()
                except:
                    pass
        except:
            pass
        
        # Hemen kapat
        event.accept()
        QApplication.quit()

    def __init__(self, current_user=None):
        """
        MainWindow sınıfının başlatıcı metodu.
        
        Bu metod, ana pencereyi oluşturur, sunucuları başlatır, kullanıcı arayüzünü
        hazırlar ve gerekli bağlantıları kurar. Ayrıca log sistemi, çalışma süresi
        takibi ve veri yapılarını da başlatır.
        
        Args:
            current_user: Authenticated user object
        """
        super().__init__()
        
        # User context
        self.current_user = current_user
        if current_user:
            self.logger_prefix = f"[{current_user.username}] "
        else:
            self.logger_prefix = "[system] "
        
        # Race Condition Fix: Uygulama kapanma durumunu takip et
        self.is_closing = False
        
        # --- Centralized Logging System (Performance Optimized) ---
        from utils.logger_config import get_logger_config, get_logger
        
        app_data_dir = get_app_data_directory()
        self.app_data_dir = app_data_dir  # Store for later use
        log_dir = app_data_dir / 'logs'
        
        # Setup centralized logger
        logger_config = get_logger_config()
        logger_config.setup_logging(
            log_dir=log_dir,
            console_level=logging.WARNING,   # Production mode: only warnings and errors
            file_level=logging.INFO,         # File logging remains INFO for troubleshooting
            enable_console=True,
            enable_file=True,
            max_file_size=10 * 1024 * 1024,  # 10 MB per file (explicit)
            backup_count=5                   # 5 backup files (explicit)
        )
        
        # --- ASENKRON LOGLAMA ENTEGRASYONU (BAŞLANGIÇ) ---
        # logger_config.py zaten asenkron loglama kuruyor, ancak MainWindow seviyesinde
        # ek kontrol ve optimizasyon için burada da yapılandırıyoruz
        root_logger = logging.getLogger()
        
        # Mevcut FileHandler'ı bul ve ana thread'den kopar (eğer varsa)
        file_handler = None
        for h in root_logger.handlers:
            if isinstance(h, logging.FileHandler) or isinstance(h, logging.handlers.RotatingFileHandler):
                file_handler = h
                break
        
        # Eğer FileHandler bulunduysa ve henüz QueueHandler yoksa, asenkron yapıyı kur
        if file_handler and not any(isinstance(h, logging.handlers.QueueHandler) for h in root_logger.handlers):
            # Dosya yazıcısını ana thread'den çıkarıyoruz
            root_logger.removeHandler(file_handler)
            
            # Log kuyruğu oluştur (Sınırsız boyut)
            log_queue = Queue(-1)
            
            # QueueHandler oluştur (Ana thread sadece buraya yazar - çok hızlıdır)
            queue_handler = logging.handlers.QueueHandler(log_queue)
            root_logger.addHandler(queue_handler)
            
            # QueueListener oluştur (Arka planda kuyruğu dinleyip diske yazar)
            self.log_listener = logging.handlers.QueueListener(
                log_queue, 
                file_handler, 
                respect_handler_level=True
            )
            self.log_listener.start()
        else:
            # logger_config.py zaten asenkron yapıyı kurmuş, listener'a erişim sağla
            self.log_listener = logger_config.queue_listener
        
        # Logger'ı oluştur
        self.logger = get_logger('MainWindow')
        
        # Benzersiz cihaz kimliğini al (uzaktan izleme için)
        self.device_id = get_unique_device_id()
        self.logger.info(f"Cihaz ID: {self.device_id}")
        
        # Initialize metrics collector (after logger is created)
        self.metrics = get_metrics_collector()
        self.logger.info("Metrics collector initialized")
        
        # Asenkron loglama durumunu logla
        if file_handler and not any(isinstance(h, logging.handlers.QueueHandler) for h in root_logger.handlers):
            self.logger.info("Asenkron loglama (Non-Blocking I/O) aktif edildi. GUI artık log yazmayı beklemeyecek.")
        else:
            self.logger.info("Asenkron loglama (Non-Blocking I/O) aktif. GUI artık log yazmayı beklemeyecek.")
        # --- ASENKRON LOGLAMA ENTEGRASYONU (BİTİŞ) ---
        
        self.logger.info("=== GUI Application Started ===")
        self.logger.info(f"Log directory: {log_dir}")
        
        # Log user context
        if self.current_user:
            self.logger.info(f"{self.logger_prefix}User: {self.current_user.full_name or self.current_user.username} (Role: {self.current_user.role.value})")
        
        # Patient Database
        self.patient_db = get_patient_database(self.app_data_dir)
        if self.current_user:
            self.patient_db.current_user = self.current_user
            self.logger.info(f"{self.logger_prefix}Patient DB initialized with user context: {self.current_user.username}")
        
        # Session manager'ı başlat
        self.session_manager = get_session_manager(app_data_dir)
        self.current_session_id = None
        
        # Çalışma süresini takip etmek ve kaydetmek için gerekli değişkenler
        self.working_time_file = app_data_dir / 'working_time.txt'
        self.working_seconds = 0
        if self.working_time_file.exists():
            try:
                with open(self.working_time_file, 'r') as f:
                    self.working_seconds = int(f.read().strip())
            except Exception:
                self.working_seconds = 0



        # ESP durumlarını takip etmek için değişkenler
        self.esp_status = {}  # ESP ID -> durum bilgileri
        self.esp_widgets = {}  # ESP ID -> UI widget'ları
        
        # ESP status güncelleme buffer'ı (timer tabanlı güncelleme için)
        self.esp_status_buffer = {}  # ESP ID -> en son durum bilgileri
        self.latest_sensor_data = {}  # En son sensör verilerini sakla
        self.latest_sensor_data_timestamp = 0  # Son veri güncellenme zamanı (time.time())
        
        # Performance optimization: Sensor data log throttling (10 seconds per coil)
        self.last_sensor_log_time = {}  # coil_id -> timestamp
        
        # Performance optimization: Timer exception throttling
        self.graph_error_count = 0
        self.last_graph_error_time = 0
        
        # Thread-safe durum değişkenleri (GUI öğelerine farklı thread'lerden erişim için)
        self.current_frequency = 0.0  # Hz
        self.current_intensity = 0.0  # mT
        self.current_duration = 0  # dakika
        self.treatment_active = False  # Tedavi aktif mi?
        
        # Connect portal notification signal
        self.portal_notification_received.connect(self.show_portal_dialog)
        
        # MQTT Reconnection (GUI Stability Fix #1)
        from PyQt6.QtCore import QMutex
        self.mqtt_mutex = QMutex()  # Thread safety için
        
        # Thread safety mutex'leri (Thread Safety Fix)
        self.esp_status_buffer_mutex = QMutex()  # esp_status_buffer için thread safety
        self.graph_data_mutex = QMutex()  # graph_magnetic_field_data ve graph_temperature_data için thread safety
        self.active_coils_mutex = QMutex()  # active_coils için thread safety
        
        # Enerji takibi (KPI Dashboard bağımsız)
        self.COIL_RESISTANCE = 9.0  # Ohm (bobin direnci)
        self.total_energy_wh = 0.0  # Watt-hour cinsinden toplam enerji
        self.last_energy_update_time = time.time()
        
        self.mqtt_reconnect_timer = QTimer(self)  # Parent widget'a bağla
        self.mqtt_reconnect_timer.timeout.connect(self._attempt_mqtt_reconnect)
        self.mqtt_retry_count = 0
        self.mqtt_retry_delay = 2000  # 2 saniye başlangıç
        self.max_mqtt_retry_delay = 60000  # 60 saniye max
        self.max_mqtt_retries = 10
        self.mqtt_connected_state = False  # Boolean state (signal değil)
        
        self.setWindowTitle("Pemf Vet sistemi")
        self.setWindowIcon(QIcon(resource_path("resources/icons/pemf_heart_emf_icon.ico")))
        
        # Responsive window sizing
        self._setup_responsive_window()
        
        # Window flags to enable maximize and resize
        self.setWindowFlags(Qt.WindowType.Window | 
                           Qt.WindowType.WindowMinimizeButtonHint | 
                           Qt.WindowType.WindowMaximizeButtonHint | 
                           Qt.WindowType.WindowCloseButtonHint)

        # Apply design system theme
        self.apply_theme()
        
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        make_resizable(central_widget)
        main_layout.setSpacing(0)
        
        # Apply responsive layout
        apply_responsive_layout(central_widget, base_margins=(0, 0, 0, 0), base_spacing=0)

        # --- Top Bar ---
        top_bar_widget = QWidget()
        # Responsive top bar styling
        top_margin = scale_margins(top_bar_widget, 8)
        side_margin = scale_margins(top_bar_widget, 32)
        top_padding = scale_margins(top_bar_widget, 6)
        spacing = get_responsive_spacing(20)
        
        top_bar_widget.setStyleSheet(f"""
            background: transparent;
            border-radius: 18px;
            margin: {top_margin}px {side_margin}px 0 {side_margin}px;
            padding: 0;
        """)
        top_bar_layout = QHBoxLayout(top_bar_widget)
        top_bar_layout.setContentsMargins(side_margin, top_padding, side_margin, top_padding)
        top_bar_layout.setSpacing(spacing)

        # Logo + Text
        logo_layout = QHBoxLayout()
        logo_layout.setContentsMargins(0, 0, 0, 0)
        logo_layout.setSpacing(get_responsive_spacing(12))

        icon_label = QLabel()
        icon_path = resource_path("resources/images/pemf_heart_emf_icon.png")
        if os.path.exists(icon_path):
            icon_pixmap = QPixmap(str(icon_path)).scaled(48, 48, Qt.AspectRatioMode.KeepAspectRatio,
                                                         Qt.TransformationMode.SmoothTransformation)
            if not icon_pixmap.isNull():
                icon_label.setPixmap(icon_pixmap)
            else:
                icon_label.setText("💚")
                icon_font_size = get_responsive_font_size(32)
                icon_label.setStyleSheet(f"font-size: {icon_font_size}px;")
        else:
            icon_label.setText("💚")
            icon_label.setStyleSheet("font-size: 32px;")

        # Responsive text sizing
        title_size = get_responsive_font_size(28)
        subtitle_size = get_responsive_font_size(16)
        
        text_label = QLabel(
            f"<b style='color:#fff; font-size:{title_size}px;'>PEMF Vet Sistemi</b> "
            f"<span style='color:#6cffb0; font-size:{subtitle_size}px;'>✓ Sertifikalı</span>"
        )
        text_label.setStyleSheet("color: #fff;")

        logo_layout.addWidget(icon_label)
        logo_layout.addWidget(text_label)

        logo_container = QWidget()
        logo_container.setLayout(logo_layout)

        top_bar_layout.addWidget(logo_container)
        top_bar_layout.addStretch(1)



        # Clock label
        self.clock = QLabel()
        # Responsive clock styling
        clock_font_size = get_responsive_font_size(15)
        clock_margin = scale_margins(self.clock, 24)
        
        self.clock.setStyleSheet(f"""
            color: #fff;
            font-size: {clock_font_size}px;
            margin-left: {clock_margin}px;
            background: transparent;
            border-radius: 0;
        """)
        top_bar_layout.addWidget(self.clock)

        # Silent mode toggle button
        self.silent_mode_btn = QPushButton("🔊")
        self.silent_mode_btn.setToolTip("Sessiz Mod (Bildirimleri Kapat/Aç)")
        # Responsive button styling
        btn_font_size = get_responsive_font_size(16)
        btn_padding_h = scale_margins(self.silent_mode_btn, 12)
        btn_padding_v = scale_margins(self.silent_mode_btn, 8)
        btn_margin = scale_margins(self.silent_mode_btn, 16)
        btn_min_width = scale_margins(self.silent_mode_btn, 40)
        
        self.silent_mode_btn.setStyleSheet(f"""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #4a90e2, stop:1 #7bb3f0);
            color: white;
            border: none;
            border-radius: 8px;
            font-size: {btn_font_size}px;
            font-weight: bold;
            padding: {btn_padding_v}px {btn_padding_h}px;
            margin-left: {btn_margin}px;
            min-width: {btn_min_width}px;
        """)
        self.silent_mode_btn.clicked.connect(self.toggle_silent_mode)
        top_bar_layout.addWidget(self.silent_mode_btn)

        # User Manual button
        self.user_manual_btn = QPushButton("📖 Kullanım Kılavuzu")
        self.user_manual_btn.setToolTip("PDF Kullanım Kılavuzunu Aç")
        self.user_manual_btn.setStyleSheet(f"""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #6c2b8f, stop:1 #9b4ec8);
            color: white;
            border: none;
            border-radius: 8px;
            font-size: {btn_font_size}px;
            font-weight: bold;
            padding: {btn_padding_v}px {btn_padding_h}px;
            margin-left: {btn_margin}px;
            min-width: {btn_min_width}px;
        """)
        self.user_manual_btn.clicked.connect(self.open_user_manual)
        top_bar_layout.addWidget(self.user_manual_btn)

        # Emergency stop button
        emergency_btn = QPushButton("ACİL DURDURMA")
        emergency_btn.clicked.connect(self.send_global_stop_command)
        # Responsive emergency button styling
        emergency_font_size = get_responsive_font_size(18)
        emergency_padding_h = scale_margins(emergency_btn, 32)
        emergency_padding_v = scale_margins(emergency_btn, 12)
        emergency_margin = scale_margins(emergency_btn, 32)
        
        emergency_btn.setStyleSheet(f"""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #ff5e62, stop:1 #ff9966);
            color: white;
            border: none;
            border-radius: 12px;
            font-size: {emergency_font_size}px;
            font-weight: bold;
            padding: {emergency_padding_v}px {emergency_padding_h}px;
            margin-left: {emergency_margin}px;
        """)
        top_bar_layout.addWidget(emergency_btn)

        main_layout.addWidget(top_bar_widget)

        # --- Unified 1Hz Timer (Timer Optimization) ---
        # Tüm 1Hz güncellemeleri tek timer'da birleştirildi (performans için)
        self.unified_1hz_timer = QTimer(self)
        self.unified_1hz_timer.timeout.connect(self._on_unified_1hz_tick)
        self.unified_1hz_timer.start(1000)  # 1 Hz
        self.update_clock()  # İlk güncelleme
        
        # --- Graph Update Timer (FPS Optimization) ---
        # Grafik güncellemesi ayrı timer'da (50ms = 20 FPS) - akıcı görüntü için
        # Veri işleme ve commit de bu timer'da yapılır
        # Adaptive FPS: Sadece yeni veri varsa güncelleme yapar
        self.graph_update_timer = QTimer(self)
        self.graph_update_timer.timeout.connect(self._on_graph_update_tick)
        self.graph_update_timer.start(50)  # 50ms = 20 FPS (anlık veri görüntüleme için)
        
        # JSON Parse Cache (Performance Optimization)
        self._json_parse_cache = {}  # payload_hash -> parsed_data
        self._json_cache_max_size = 100  # Max cache entries

        # --- Main Content Area ---
        content_layout = QHBoxLayout()
        # Responsive content margins and spacing
        content_margin_h = scale_margins(self, 32)
        content_margin_v = scale_margins(self, 16)
        content_spacing = get_responsive_spacing(32)
        
        content_layout.setContentsMargins(content_margin_h, content_margin_v, content_margin_h, content_margin_v)
        content_layout.setSpacing(content_spacing)
        main_layout.addLayout(content_layout, stretch=1)
        # Sidebar
        sidebar = QVBoxLayout()
        sidebar.setSpacing(get_responsive_spacing(18))
        sidebar.setContentsMargins(0, 0, 0, 0)

        sidebar_widget = QWidget()
        # Responsive sidebar styling
        sidebar_padding = scale_margins(sidebar_widget, 16)
        
        sidebar_widget.setStyleSheet(f"""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #2d185a, stop:1 #6c2b8f);
            padding: {sidebar_padding}px;
            border-radius: 16px;
        """)
        sidebar_widget.setLayout(sidebar)
        content_layout.addWidget(sidebar_widget, 1)  # Stretch 1 ile esneklik verildi

        # Sidebar başlığı
        sidebar_title = QLabel("Sistem Parametreleri")
        # Responsive title styling
        title_font_size = get_responsive_font_size(18)
        sidebar_title.setStyleSheet(f"color: #fff; font-size: {title_font_size}px; font-weight: bold; margin: 0;")
        sidebar.addWidget(sidebar_title)

        # Scroll destekli giriş + bilgi paneli
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("""
            QScrollArea {
                background: transparent;
                border: none;
            }
            QScrollBar:vertical, QScrollBar:horizontal {
                width: 0px;
                height: 0px;
            }
        """)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)  # Corrected line
        scroll_layout.setSpacing(18)
        scroll_area.setWidget(scroll_content)
        sidebar.addWidget(scroll_area)

        # Ayırıcı çizgi
        separator = QWidget()
        separator_margin = scale_margins(separator, 20)
        separator_height = max(1, int(2 * (get_screen_info()[2])))
        separator.setStyleSheet(f"background: #6c2b8f; margin: {separator_margin}px 0;")
        separator.setFixedHeight(separator_height)
        scroll_layout.addWidget(separator)

        # ESP Bağlantı Durumu Paneli
        self.create_esp_status_panel(scroll_layout)

        # Ayırıcı çizgi
        separator2 = QWidget()
        separator2_margin = scale_margins(separator2, 20)
        separator2_height = max(1, int(2 * (get_screen_info()[2])))
        separator2.setStyleSheet(f"background: #6c2b8f; margin: {separator2_margin}px 0;")
        separator2.setFixedHeight(separator2_height)
        scroll_layout.addWidget(separator2)

        # 2. Sistem Parametreleri
        param_title = QLabel("⚙️ Hasta Kaydı")
        param_title_font_size = get_responsive_font_size(16)
        param_title.setStyleSheet(f"color: #6cffb0; font-size: {param_title_font_size}px; font-weight: bold; margin: 10px 0;")
        scroll_layout.addWidget(param_title)

        param_labels = [
            "Hayvanın Adı","Hayvanın Türü", "Hayvanın Irkı", "Hayvanın Yaşı"," Hayvanın Ağırlığı","Hayvanın Sahibi","Veteriner İletişim Bilgileri"
        ]

        self.input_fields = []
        self.validation_labels = []  # Validasyon mesajları için label'lar
        self.validator = PatientInputValidator()  # Validator instance

        for label in param_labels:
            vbox = QVBoxLayout()
            vbox.setSpacing(6)
            lbl = QLabel(label)
            label_font_size = get_responsive_font_size(14)
            lbl.setStyleSheet(f"color: #fff; font-size: {label_font_size}px; font-weight: bold; margin-left: 2px; margin-bottom: 5px;")

            field = QLineEdit()
            field.setPlaceholderText("Enter value...")
            field_font_size = get_responsive_font_size(14)
            field_padding_h = scale_margins(field, 12)
            field_padding_v = scale_margins(field, 7)
            field_height = max(24, int(28 * (get_screen_info()[2])))
            field.setStyleSheet(
                f"background: #3d206b; color: white; border: none; border-radius: 10px; "
                f"padding: {field_padding_v}px {field_padding_h}px; font-size: {field_font_size}px;"
            )
            field.setFixedHeight(field_height)
            
            # Validasyon mesajı label'ı
            validation_label = QLabel("")
            validation_label.setStyleSheet(
                "color: #ffa726; font-size: 11px; margin-left: 2px; margin-top: 2px;"
            )
            validation_label.setWordWrap(True)
            validation_label.setVisible(False)

            vbox.addWidget(lbl)
            vbox.addWidget(field)
            vbox.addWidget(validation_label)
            scroll_layout.addLayout(vbox)
            
            self.input_fields.append(field)
            self.validation_labels.append(validation_label)
            
            # Gerçek zamanlı validasyon bağla
            field_index = len(self.input_fields) - 1
            field.textChanged.connect(lambda text, idx=field_index: self._validate_field(idx, text))

        # Hastayı Kaydet butonu
        save_patient_btn = QPushButton("💾 Hastayı Kaydet")
        save_btn_font_size = get_responsive_font_size(16)
        save_btn_padding_h = scale_margins(save_patient_btn, 24)
        save_btn_padding_v = scale_margins(save_patient_btn, 12)
        save_btn_margin = scale_margins(save_patient_btn, 10)
        save_patient_btn.setStyleSheet(f"""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #28a745, stop:1 #20c997);
            color: white;
            border: none;
            border-radius: 12px;
            font-size: {save_btn_font_size}px;
            font-weight: bold;
            padding: {save_btn_padding_v}px {save_btn_padding_h}px;
            margin: {save_btn_margin}px 0;
        """)
        save_patient_btn.clicked.connect(self.save_patient)
        scroll_layout.addWidget(save_patient_btn)

        # Bottom navigation bar
        nav_bar = QHBoxLayout()
        nav_bar.setContentsMargins(32, 0, 32, 24)
        nav_bar.setSpacing(40)
        nav_widget = QWidget()
        nav_widget.setStyleSheet(
            "background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #2d185a, stop:1 #6c2b8f); border-radius: 18px;")
        nav_widget.setLayout(nav_bar)
        nav_items = [
            ("📈", "Sensör Verisi", self.open_sensor_data_window),
            ("🎛️", "Seans Kontrol Paneli", self.open_unified_control),
            ("🗺", "Dijital İkiz", self.open_digital_twin_window),
            ("📊", "Sistem Performansı", self.open_kpi_dashboard),
            ("📋", "Seans Geçmişi", self.open_treatment_history)
        ]
        for icon, text, slot in nav_items:
            btn = QPushButton(f"{icon}  {text}")
            nav_btn_font_size = get_responsive_font_size(18)
            nav_btn_padding_h = scale_margins(btn, 24)
            nav_btn_padding_v = scale_margins(btn, 18)
            btn.setStyleSheet(
                f"background: transparent; color: #fff; border: none; font-size: {nav_btn_font_size}px; font-weight: bold; padding: {nav_btn_padding_v}px {nav_btn_padding_h}px;")
            btn.clicked.connect(slot)
            nav_bar.addWidget(btn)
        main_layout.addWidget(nav_widget)

        # 2. Smart Treatment Card
        self.smart_treatment_card = QWidget()
        card_padding_h = scale_margins(self.smart_treatment_card, 16)
        card_padding_v = scale_margins(self.smart_treatment_card, 18)
        self.smart_treatment_card.setStyleSheet(f"""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #3d206b, stop:1 #6c2b8f);
            border-radius: 14px;
            padding: {card_padding_v}px {card_padding_h}px;
        """)
        smart_treatment_layout = QVBoxLayout(self.smart_treatment_card)
        smart_treatment_layout.setSpacing(5)

        st_title = QLabel("~ Aktif Seans")
        st_title_font_size = get_responsive_font_size(14)
        st_title.setStyleSheet(f"color: #6cffb0; font-size: {st_title_font_size}px; font-weight: bold;")
        smart_treatment_layout.addWidget(st_title)

        def make_row(label_text, value_text, value_color="#fff", value_size="14px"):
            row = QHBoxLayout()
            label = QLabel(label_text)
            row_font_size = get_responsive_font_size(14)
            label.setStyleSheet(f"color: #fff; font-size: {row_font_size}px; font-weight: bold;")
            # value_size parametresi de responsive yap
            if value_size.endswith("px"):
                value_size_num = int(value_size[:-2])
                value_size_responsive = get_responsive_font_size(value_size_num)
                value_size = f"{value_size_responsive}px"
            value = QLabel(
                f"<span style='color:{value_color}; font-weight:bold; font-size:{value_size};'>{value_text}</span>")
            value.setStyleSheet(f"font-size: {row_font_size}px; font-weight: bold;")
            row.addWidget(label)
            row.addStretch(1)
            row.addWidget(value)
            return row, value  # Return both the layout and the value label

        treatment_type_row, self.treatment_type_value = make_row("Seans Türü:", "Seçili Değil")
        smart_treatment_layout.addLayout(treatment_type_row)

        freq_row, self.freq_value = make_row("Frekans:", "0 Hz", "#4f8cff")
        smart_treatment_layout.addLayout(freq_row)

        intensity_row, self.intensity_value = make_row("Yoğunluk:", "0 mT", "#4f8cff", "14px")
        smart_treatment_layout.addLayout(intensity_row)

        st_time_row = QHBoxLayout()
        st_time_icon = QLabel("\u23F1")
        st_time_font_size = get_responsive_font_size(14)
        st_time_icon.setStyleSheet(f"color: #fff; font-size: {st_time_font_size}px; font-weight: bold;")
        st_time_label = QLabel("Süre:")
        st_time_label.setStyleSheet(f"color: #fff; font-size: {st_time_font_size}px; font-weight: bold;")
        self.st_time_value = QLabel("0/0 dk")
        self.st_time_value.setStyleSheet(f"color: #fff; font-size: {st_time_font_size}px; font-weight: bold;")
        st_time_row.addWidget(st_time_icon)
        st_time_row.addWidget(st_time_label)
        st_time_row.addStretch(1)
        st_time_row.addWidget(self.st_time_value)
        smart_treatment_layout.addLayout(st_time_row)

        self.st_progress = QProgressBar()
        progress_height = max(10, int(14 * (get_screen_info()[2])))
        self.st_progress.setFixedHeight(progress_height)
        self.st_progress.setMinimum(0)
        self.st_progress.setMaximum(100)
        self.st_progress.setValue(0)
        self.st_progress.setTextVisible(True)
        self.st_progress.setFormat("%p%")  # Yüzde gösterimi
        self.st_progress.setStyleSheet("""
            QProgressBar {
                border: none;
                border-radius: 7px;
                background-color: #2d1b69;
                text-align: center;
                color: white;
                font-weight: bold;
                font-size: 12px;
            }
            QProgressBar::chunk {
                background-color: #3b82f6;
                border-top-left-radius: 7px;
                border-bottom-left-radius: 7px;
                border-top-right-radius: 0px;
                border-bottom-right-radius: 0px;
                margin: 0px;
            }
        """)
        smart_treatment_layout.addWidget(self.st_progress)

        st_status_row = QHBoxLayout()
        status_font_size = get_responsive_font_size(14)
        status_display_font_size = get_responsive_font_size(16)
        status_padding_h = scale_margins(self, 16)
        status_padding_v = scale_margins(self, 4)
        status_margin_top = scale_margins(self, 6)
        self.st_status = QLabel(f"<span style='color:#6b7280; font-size: {status_font_size}px; font-weight: bold;'>● Beklemede</span>")
        self.st_status.setStyleSheet(
            f"background: #f3f4f6; border-radius: 6px; padding: {status_padding_v}px {status_padding_h}px; margin-top: {status_margin_top}px; font-size: {status_display_font_size}px;")
        st_status_row.addWidget(self.st_status)
        st_status_row.addStretch(1)
        smart_treatment_layout.addLayout(st_status_row)

        scroll_layout.addWidget(self.smart_treatment_card)

        # 3. KPI Card
        kpi_card = QWidget()
        kpi_card.setStyleSheet("background: transparent;")
        kpi_layout = QVBoxLayout(kpi_card)
        kpi_layout.setContentsMargins(0, 0, 0, 0)
        kpi_layout.setSpacing(8)

        kpi_title = QLabel("Performans")
        kpi_title_font_size = get_responsive_font_size(15)
        kpi_title.setStyleSheet(f"color: #fff; font-size: {kpi_title_font_size}px; font-weight: bold;")
        kpi_layout.addWidget(kpi_title)

        def make_kpi(bg, icon, icon_color, label, label_color, value, value_color):
            widget = QWidget()
            kpi_padding_h = scale_margins(widget, 10)
            kpi_padding_v = scale_margins(widget, 6)
            widget.setStyleSheet(f"background: {bg}; border-radius: 8px; padding: {kpi_padding_v}px {kpi_padding_h}px;")
            layout = QHBoxLayout(widget)
            kpi_margin_h = scale_margins(widget, 8)
            kpi_margin_v = scale_margins(widget, 4)
            layout.setContentsMargins(kpi_margin_h, kpi_margin_v, kpi_margin_h, kpi_margin_v)
            layout.setSpacing(2)
            icon_font_size = get_responsive_font_size(18)
            icon_lbl = QLabel(f"<span style='color:{icon_color}; font-size: {icon_font_size}px;'>{icon}</span>")
            text_lbl = QLabel(label)
            label_font_size = get_responsive_font_size(13)
            text_lbl.setStyleSheet(f"color: {label_color}; font-size: {label_font_size}px; font-weight: bold;")
            value_font_size = get_responsive_font_size(16)
            val_lbl = QLabel(f"<span style='color:{value_color}; font-size: {value_font_size}px; font-weight: bold;'>{value}</span>")
            layout.addWidget(icon_lbl)
            layout.addWidget(text_lbl)
            layout.addStretch(1)
            layout.addWidget(val_lbl)
            return widget, val_lbl

        # Store KPI value labels as attributes
        widget1, self.kpi1_value = make_kpi("#d1fae5", "✅", "#22c55e", "Seans Etkinlik Oranı", "#166534", "78%",
                                            "#22c55e")
        kpi_layout.addWidget(widget1)

        widget2, self.kpi2_value = make_kpi("#fef9c3", "⚡", "#eab308", "Enerji Tüketimi", "#a16207", "0.0 Wh",
                                            "#eab308")
        kpi_layout.addWidget(widget2)

        widget3, self.kpi3_value = make_kpi("#dbeafe", "⚙️", "#2563eb", "Cihaz Çalışma Oranı", "#2563eb", "95%",
                                            "#2563eb")
        kpi_layout.addWidget(widget3)

        scroll_layout.addWidget(kpi_card)
        scroll_layout.addStretch(1)

        scroll_area.setWidget(scroll_content)
        sidebar.addWidget(scroll_area)

        # Center: Coil control panel
        center_panel = QWidget()
        center_panel.setStyleSheet("""
            background: rgba(40,20,80,0.85);
            border-radius: 24px;
        """)
        center_panel_layout = QVBoxLayout(center_panel)
        center_panel_layout.setContentsMargins(32, 32, 32, 32)
        center_panel_layout.setSpacing(24)

        # --- Sistem Durumu Başlık ---
        system_status_title = QLabel("<b style='color:#fff;font-size:22px;'>Sistem Durumu</b>")
        system_status_title.setAlignment(Qt.AlignmentFlag.AlignLeft)
        center_panel_layout.addWidget(system_status_title)

        # --- Durum Bilgileri Satırı ---
        status_row = QHBoxLayout()
        status_row.setSpacing(32)
        status_row.setContentsMargins(0, 0, 0, 0)

        def make_status_label(label, value, color):
            return QLabel(f"<span style='color:#bdb8e3;font-size:13px;'>{label}</span> "
                          f"<span style='color:{color}; font-size:14px; font-weight:bold;'>{value}</span>")



        status_row_widget = QWidget()
        status_row_widget.setLayout(status_row)
        status_row_widget.setStyleSheet("background: transparent;")
        center_panel_layout.addWidget(status_row_widget)

        # --- Çoklu Bobin Gerçek Zamanlı Grafik ---
        self._active_coils = set()  # Track which coils are active (thread-safe via mutex)
        self.graph_start_time = None
        self.has_new_sensor_data = False  # Flag for adaptive FPS
        # DEĞİŞİKLİK: maxlen=100 yerine maxlen=2000 (10 saniye için yeterli kapasite)
        self.graph_time_data = deque(maxlen=2000)
        self.graph_data_collection_active = False  # Veri toplama aktif mi?

        # Initialize data storage for each coil (1-8)
        # DEĞİŞİKLİK: maxlen=100 yerine maxlen=2000 (10 saniye için yeterli kapasite)
        self.graph_magnetic_field_data = {i: deque(maxlen=2000) for i in range(1, 9)}
        self.graph_temperature_data = {i: deque(maxlen=2000) for i in range(1, 9)}
        
        # Last known values for step-like graph plotting (Thread-Safe with graph_data_mutex)
        self.last_known_mag = {i: np.nan for i in range(1, 9)}
        self.last_known_temp = {i: np.nan for i in range(1, 9)}

        # --- Real-time Graph ---
        # Create a GraphicsLayoutWidget for advanced layout control
        self.plot_widget = pg.GraphicsLayoutWidget()
        self.plot_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.plot_widget.setMinimumHeight(200)
        self.plot_widget.setBackground(pg.mkColor(40, 20, 80, 200))

        # Add the main plot item for magnetic field
        self.plot_item = self.plot_widget.addPlot(row=0, col=1)
        self.plot_item.setLabel('left', 'Manyetik Alan (mT)', color='#22c55e', size='14pt')
        self.plot_item.setLabel('bottom', 'Zaman (s)', color='#fff', size='12pt')
        self.plot_item.showGrid(x=True, y=True, alpha=0.3)
        # Use custom TicksAxis for the default axes
        self.plot_item.getAxis('left').__class__ = TicksAxis
        self.plot_item.getAxis('bottom').__class__ = TicksAxis

        # Create and add the temperature axis to the left of the main plot
        self.temp_axis = TicksAxis(orientation='left')
        self.temp_axis.setLabel('Bobin Sıcaklığı (°C)', color='#ef4444')
        self.plot_widget.addItem(self.temp_axis, row=0, col=0)
        
        # Create a second ViewBox for the temperature data, overlay it on the main plot
        self.p2 = pg.ViewBox()
        self.plot_item.scene().addItem(self.p2)
        
        # Link the temperature axis and the second ViewBox
        self.temp_axis.linkToView(self.p2)
        self.p2.setXLink(self.plot_item)
        
        # Synchronize the two ViewBoxes' geometries
        self.plot_item.getViewBox().sigResized.connect(self._update_dual_axis_views)
        
        # Enable auto-ranging for Y-axis to properly scale with data
        self.plot_item.enableAutoRange(axis=pg.ViewBox.YAxis, enable=True)
        self.p2.enableAutoRange(axis=pg.ViewBox.YAxis, enable=True)
        
        # Add legend to the main plot item, anchored to the top-right
        legend = self.plot_item.addLegend(offset=(10, 10))
        legend.anchor(itemPos=(1, 0), parentPos=(1, 0), offset=(-10, 10))

        # Initialize dictionaries to hold plot curve objects
        self.mag_field_curves = {}
        self.temp_curves = {}

        # Define colors for each coil
        colors = [
            '#FF5252', '#FF4081', '#E040FB', '#7C4DFF',
            '#536DFE', '#448AFF', '#40C4FF', '#18FFFF'
        ]

        # Create frequency and intensity curves for each coil
        for coil in range(1, 9):
            color = colors[coil - 1]
            # Solid green line for magnetic field
            self.mag_field_curves[coil] = self.plot_item.plot(
                pen=pg.mkPen(color='#22c55e', width=2),
                name=f'Bobin {coil}',
                antialias=True
            )
            # Downsampling optimizasyonu (mean method - gürültüyü bastırır)
            self.mag_field_curves[coil].setDownsampling(auto=True, method='mean')
            self.mag_field_curves[coil].setClipToView(True)
            
            # Dashed line for temperature, linked to the second Y-axis
            # PlotCurveItem yerine PlotDataItem kullanın (setDownsampling desteği için)
            temp_curve = pg.PlotDataItem(
                pen=pg.mkPen(color=color, width=1, style=Qt.PenStyle.DashLine),
                name=f'Bobin {coil} Sıcaklık (°C)',
                antialias=True
            )
            # Downsampling optimizasyonu (mean method - gürültüyü bastırır)
            temp_curve.setDownsampling(auto=True, method='mean')
            temp_curve.setClipToView(True)
            self.temp_curves[coil] = temp_curve
            self.p2.addItem(temp_curve)

        center_panel_layout.addWidget(self.plot_widget)
        center_panel_layout.setStretchFactor(self.plot_widget, 1)

        # --- Bobin Kontrol Paneli BaÅŸlÄ±k ---
        coil_panel = QVBoxLayout()
        coil_panel.setSpacing(18)
        coil_panel_title = QLabel("<b style='color:#fff;font-size:22px;'>Grafik Kontrol Paneli</b>")
        coil_panel.addWidget(coil_panel_title)

        # --- 8 Adet Bobin Butonu ---
        grid = QGridLayout()
        grid.setSpacing(18)
        self.coil_buttons = []

        # Create coil buttons first
        for i in range(8):
            btn = QPushButton(f"⚡ Bobin-{i + 1}")
            btn.setStyleSheet("""
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #1ed6b5, stop:1 #3ed6b5);
                    color: white;
                    border: none;
                    border-radius: 14px;
                    font-size: 18px;
                    font-weight: bold;
                    padding: 18px 0;
                }
                QPushButton:checked {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #ff6b6b, stop:1 #ff8e8e);
                }
                QPushButton:hover {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #3ed6b5, stop:1 #5ed6b5);
                }
                QPushButton:pressed {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #00b894, stop:1 #00cec9);
                }
                QPushButton:disabled {
                    background: rgba(100, 100, 100, 0.3);
                    color: rgba(255, 255, 255, 0.4);
                }
            """)
            btn.setCheckable(True)
            # CRITICAL FIX: Başlangıçta tüm butonları disable et (ESP bağlanana kadar)
            btn.setEnabled(False)
            btn.setToolTip(f"Bobin {i + 1} - Bağlantı Bekleniyor")
            self.coil_buttons.append(btn)
            grid.addWidget(btn, i // 4, i % 4)  # 2 rows, 4 columns

            # Connect button click to toggle functionality
            btn.clicked.connect(lambda checked, ch=i + 1: self._on_coil_button_toggled(checked, ch))

        # Initially hide all curves
        for coil in range(1, 9):
            self.mag_field_curves[coil].hide()
            self.temp_curves[coil].hide()
        coil_panel.addLayout(grid)

        # --- Bobinleri Durdur Butonu ---
        stop_btn = QPushButton("🚫 Bobin Kapat!")
        stop_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #ff5e62, stop:1 #ff9966);
                color: white;
                border: none;
                border-radius: 14px;
                font-size: 20px;
                font-weight: bold;
                padding: 18px 0;
                margin-top: 18px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #e45357, stop:1 #ff7f50);
            }
        """)
        stop_btn.setMinimumHeight(80)
        stop_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        stop_btn.clicked.connect(self.send_global_stop_command)
        coil_panel.addWidget(stop_btn)

        center_panel_layout.addLayout(coil_panel)
        content_layout.addWidget(center_panel, stretch=2)

        # Right: Info panel
        info_panel = QWidget()
        info_panel.setStyleSheet("""
            background: rgba(40,20,80,0.85);
            border-radius: 24px;
        """)
        info_layout = QVBoxLayout(info_panel)
        info_layout.setContentsMargins(22, 22, 22, 22)
        info_layout.setSpacing(12)

        info_title = QLabel("<b style='color:#fff;font-size:22px;'>Sistem Bilgileri</b>")
        info_layout.addWidget(info_title)

        # System Info Compact Card (vertical list, compact)
        system_info_card = QWidget()
        system_info_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        system_info_card.setMinimumWidth(250)
        system_info_card.setStyleSheet("""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #3d206b, stop:1 #6c2b8f);
            border-radius: 16px;
            padding: 16px;
            margin-top: 12px;
        """)

        system_info_layout = QVBoxLayout(system_info_card)
        system_info_layout.setContentsMargins(0, 0, 0, 0)
        system_info_layout.setSpacing(4)

        # YardÄ±mcÄ± fonksiyon
        def add_info_row(label_text, value_label, value_style=None):
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(8)

            label = QLabel(label_text)
            label.setStyleSheet("color: #bdb8e3; font-size: 11px;")  # KÃ¼Ã§Ã¼k aÃ§Ä±klama metni

            value_label.setStyleSheet(
                value_style or "color: #fff; font-size: 14px; font-weight: bold;")  # DeÄŸer net ve belirgin

            row.addWidget(label)
            row.addStretch(1)
            row.addWidget(value_label)
            system_info_layout.addLayout(row)

        # Dinamik deÄŸer alanlarÄ±
        self.working_time_label = QLabel()
        self.total_treatment_label = QLabel("0 seans")

        # Bilgi satÄ±rlarÄ±
        add_info_row("🔄 Yazılım Sürümü:", QLabel(f"v{self.SOFTWARE_VERSION}"), "color: #ffffff; font-size: 12px; font-weight: bold;")
        add_info_row("💻 Donanım Sürümü:", QLabel("HW-2025.1"), "color: #ffffff; font-size: 12px; font-weight: bold;")
        add_info_row("📅 Son Güncelleme:", QLabel("8.11.2025"),
                     "color: #ffffff; font-size: 12px; font-weight: bold;")
        add_info_row("🆔 Cihaz ID:", QLabel("PEMF-001-2025"), "color: #ffffff; font-size: 12px; font-weight: bold;")
        add_info_row("⏳ Çalışma Süresi:", self.working_time_label,
                     "color: #ffffff; font-size: 12px; font-weight: bold;")
        add_info_row("📈 Toplam Seans:", self.total_treatment_label,
                     "color: #ffffff; font-size: 12px; font-weight: bold;")

        info_layout.addWidget(system_info_card)

        # Çalışma süresi güncelle
        self.update_working_time_label()
        
        # Toplam tedavi sayısını güncelle
        self.update_total_treatment_count()

        # Bildirim Kartı
        notification_card = QWidget()
        notification_card.setStyleSheet("""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #3d206b, stop:1 #6c2b8f);
            border-radius: 16px;
            padding: 16px;
            margin-top: 12px;
        """)
        notification_card_layout = QVBoxLayout(notification_card)
        notification_card_layout.setContentsMargins(0, 0, 0, 0)
        notification_card_layout.setSpacing(10)

        notification_title = QLabel("Bildirimler")
        notification_title_font_size = get_responsive_font_size(14)
        notification_margin_bottom = scale_margins(notification_card, 10)
        notification_title.setStyleSheet(f"color: #ffffff; font-size: {notification_title_font_size}px; font-weight: bold; margin-bottom: {notification_margin_bottom}px;")
        notification_card_layout.addWidget(notification_title)

        self.notification_panel = NotificationPanel(self)
        self.notification_panel.setStyleSheet("""
            background: transparent;
            border-radius: 0px;
            padding: 0px;
            margin-top: 0px;
        """)
        notification_card_layout.addWidget(self.notification_panel)

        info_layout.addWidget(notification_card)

        content_layout.addWidget(info_panel, stretch=1)

        # --- Seans Süresi Takibi ---
        self.treatment_start_time = None
        self.treatment_duration_minutes = 0
        self.treatment_elapsed_seconds = 0
        self.is_treatment_active = False
        
        # Seans ilerlemesi unified_1hz_timer ile yapılıyor (Timer Optimization)
        
        # --- Working Time Persistence ---
        # Working time unified_1hz_timer ile yapılıyor (Timer Optimization)
        
        # --- ESP Status Update Timer ---
        # --- ESP Connection Heartbeat ---
        self.esp_last_seen = {}
        self.ESP_TIMEOUT = 3.0  # saniye (heartbeat check için)
        self.ESP_CLEANUP_TIMEOUT = 3.5  # saniye (bağlantısı kopanları hemen temizle)
        self.connection_check_timer = QTimer(self)
        self.connection_check_timer.timeout.connect(self.check_esp_connections)
        self.connection_check_timer.start(3000)  # 1 saniyede bir kontrol et (Hızlı tepki)
        
        # ✅ ESP stale data cleanup timer (1 second interval)
        # Bağlantısı kopan cihazları anlık olarak arayüzden temizler
        self.esp_cleanup_timer = QTimer(self)
        self.esp_cleanup_timer.timeout.connect(self._cleanup_stale_esp_devices)
        self.esp_cleanup_timer.start(3000)  # 1 saniyede bir cleanup
        
        # --- ESP Portal Status Check ---
        self.esp_portal_status = {}  # coil_id -> portal status dict
        self.portal_notified = set()  # portal bildirimi yapılan bobinler
        self.portal_check_timer = QTimer(self)
        self.portal_check_timer.timeout.connect(self._start_portal_status_check)
        self.portal_check_timer.start(7000)  # 5 saniyede bir kontrol et
        
        # Portal status checker için QThreadPool (Timer Optimization - async)
        self.portal_thread_pool = QThreadPool.globalInstance()
        self.portal_thread_pool.setMaxThreadCount(1)  # Portal check için tek thread yeterli
        self.last_portal_check_time = 0  # Son portal kontrol zamanı (performans için)
        
        # Connect coil_control_requested signal to handle_coil_control_request slot
        # Bu signal sadece GUI içi kullanım için (UnifiedControlWindow'dan komut almak için)
        self.coil_control_requested.connect(self.handle_coil_control_request, Qt.ConnectionType.QueuedConnection)
        self.logger.info("coil_control_requested signal connected to handle_coil_control_request slot")
        
        # --- Sessiz Mod Ayarı ---
        self.silent_mode = False
        
        # --- MQTT Client Initialization ---
        # Initialize MQTT-related attributes
        self.mqtt_client = None
        
        # Connect ESP status signal to update function (Thread-Safe: QueuedConnection)
        self.esp_status_received.connect(self.update_esp_status_internal, Qt.ConnectionType.QueuedConnection)
        
        # MQTT istemcisini başlat (HiveMQ Cloud'a bağlanacak)
        self.setup_mqtt_client()

    def _cleanup_mqtt_client(self):
        """
        MQTT client'ı düzgün şekilde temizler (MQTT Cleanup).
        Callback'leri kaldırarak memory leak'i önler.
        """
        try:
            if hasattr(self, 'mqtt_client') and self.mqtt_client:
                # Callback'leri kaldır (memory leak önleme)
                self.mqtt_client.on_connect = None
                self.mqtt_client.on_message = None
                self.mqtt_client.on_disconnect = None
                self.mqtt_client.on_subscribe = None
                
                # Loop'u durdur (timeout ile)
                try:
                    # loop_stop zaten non-blocking ama error durumunda çıkılmalı
                    stop_thread = threading.Thread(target=self.mqtt_client.loop_stop, daemon=True)
                    stop_thread.start()
                    stop_thread.join(timeout=0.1)  # Max 100ms bekle
                except Exception:
                    pass
                
                # Bağlantıyı kes (timeout ile - best effort)
                try:
                    disconnect_thread = threading.Thread(target=self.mqtt_client.disconnect, daemon=True)
                    disconnect_thread.start()
                    disconnect_thread.join(timeout=0.1)  # Max 100ms bekle
                except Exception:
                    pass
                
                # Client'ı None yap
                self.mqtt_client = None
                self.logger.debug("MQTT client temizlendi (best-effort)")
        except Exception as e:
            self.logger.error(f"MQTT client temizleme hatası: {e}", exc_info=True)
    
    def setup_mqtt_client(self):
        """
        MQTT istemcisini kurar ve HiveMQ Cloud broker'a SSL/TLS ile bağlar.
        Retry mekanizması ile.
        """
        # Eski client'ı temizle (MQTT Cleanup)
        self._cleanup_mqtt_client()
        
        # HiveMQ Cloud bilgileri
        BROKER_URL = "8593bfdb2f324ad88d08b54b5e37c0a9.s1.eu.hivemq.cloud"
        BROKER_PORT = 8883  # SSL/TLS portu
        BROKER_USER = "afsuampemf"  # HiveMQ Cloud kullanıcı adı
        BROKER_PASS = "Pemf1234"  # HiveMQ Cloud şifre
        
        max_retries = 3
        retry_delay = 2  # saniye
        
        for attempt in range(max_retries):
            try:
                # clean_session=False ile oluştur - retained message'ları alabilmek için
                # Bu sayede uygulama kapalıyken gönderilen pemf/system/session mesajlarını alabilir
                self.mqtt_client = mqtt.Client(
                    mqtt.CallbackAPIVersion.VERSION2, 
                    client_id="pemf_gui_client",
                    clean_session=False  # Retained message'lar için gerekli
                )
                self.mqtt_client.on_connect = self.on_mqtt_connect
                self.mqtt_client.on_message = self.on_mqtt_message
                self.mqtt_client.on_disconnect = self.on_mqtt_disconnect
                self.mqtt_client.on_subscribe = self.on_mqtt_subscribe
                
                # Kullanıcı adı ve şifre ayarla
                self.mqtt_client.username_pw_set(BROKER_USER, BROKER_PASS)
                
                # SSL/TLS yapılandırması (HiveMQ Cloud zorunlu TLS kullanır)
                # ca_certs=None yaparak sistemin varsayılan sertifikalarını kullanırız
                self.mqtt_client.tls_set(
                    ca_certs=None,  # Sistem varsayılan CA sertifikalarını kullan
                    certfile=None,
                    keyfile=None,
                    cert_reqs=ssl.CERT_REQUIRED,
                    tls_version=ssl.PROTOCOL_TLSv1_2
                )
                
                # HiveMQ Cloud'a bağlan
                self.logger.info(f"HiveMQ Cloud'a bağlanılıyor: {BROKER_URL}:{BROKER_PORT}")
                self.mqtt_client.connect(BROKER_URL, BROKER_PORT, 60)
                self.mqtt_client.loop_start()
                
                self.logger.info(f"MQTT istemcisi HiveMQ Cloud broker'a bağlanıyor...")
                return  # Başarılı, fonksiyondan çık
                
            except Exception as e:
                self.logger.warning(f"MQTT istemci kurulumu başarısız (deneme {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                else:
                    self.logger.error(f"MQTT istemci kurulumu {max_retries} denemeden sonra başarısız oldu")

    def on_mqtt_connect(self, client, userdata, flags, rc, properties=None):
        """
        MQTT broker'a bağlantı kurulduğunda çalışır.
        """
        if rc == 0:
            self.mqtt_mutex.lock()
            self.mqtt_connected_state = True
            self.mqtt_mutex.unlock()
            
            # Reconnect timer'ı durdur (GUI Stability Fix #1)
            if self.mqtt_reconnect_timer.isActive():
                self.mqtt_reconnect_timer.stop()
                self.mqtt_retry_count = 0
                self.mqtt_retry_delay = 2000
            
            self.logger.info("MQTT broker'a başarıyla bağlanıldı")
            
            # MQTT connected signal'ı emit et (UnifiedControlWindow için)
            self.mqtt_connected.emit()
            
            # Notification panel'e bildir
            if hasattr(self, 'notification_panel'):
                self.notification_panel.add_notification(
                    "Cihaz bağlantısı kuruldu", 
                    "success"
                )
            
            # Subscribe to ESP8266 sensor and status topics for all coils
            result1, mid1 = client.subscribe("pemf/coil/+/sensors")
            result2, mid2 = client.subscribe("pemf/coil/+/status")
            result3, mid3 = client.subscribe("pemf/coil/+/alarm")  # Alarm topic'i ekle
            result4, mid4 = client.subscribe("pemf/coil/+/ack")  # ACK topic'i ekle (GUI Stability Fix #4)
            result5, mid5 = client.subscribe("pemf/coil/+/events")  # WiFi/MQTT event topic'i ekle
            result6, mid6 = client.subscribe("pemf/system/session/control")  # Android session control
            
            self.logger.info("MQTT topic'lere abone olundu (sensors, status, alarm, ack, events, session/control)")
            
            # Eğer aktif bir seans varsa, durumu hemen gönder (retain mesaj olarak)
            # Bu sayede app sonradan açılırsa aktif seansı görebilir
            if hasattr(self, 'is_treatment_active') and self.is_treatment_active:
                self.logger.info("Aktif seans tespit edildi, durum MQTT'ye gönderiliyor...")
                self.broadcast_session_status()
            
            self.logger.info("MQTT konularına abone olundu: pemf/coil/+/sensors, pemf/coil/+/status, pemf/coil/+/alarm, pemf/coil/+/ack, pemf/coil/+/events")
            self.logger.debug(f"Subscription results: sensors={result1}, status={result2}, alarm={result3}, ack={result4}, events={result5}")
        else:
            self.logger.error(f"MQTT broker bağlantısı başarısız, kod: {rc}")

    def on_mqtt_disconnect(self, client, userdata, flags, rc, properties=None):
        """
        MQTT broker bağlantısı kesildiğinde çalışır ve auto-reconnect başlatır.
        """
        # Race Condition Fix: Eğer uygulama kapanıyorsa reconnect timer'ı başlatma
        if getattr(self, 'is_closing', False):
            self.logger.info("Uygulama kapanıyor, MQTT reconnect timer başlatılmayacak.")
            return
        
        self.mqtt_mutex.lock()
        self.mqtt_connected_state = False
        self.mqtt_mutex.unlock()
        
        self.logger.warning(f"MQTT broker bağlantısı kesildi, kod: {rc}")
        
        # Tüm ESP'leri bağlı değil olarak işaretle
        for coil_id in list(self.esp_widgets.keys()):
            disconnected_status = {
                'wifi_connected': False,
                'mqtt_connected': False,
                'sensors_ok': False,
                'pwm_active': False
            }
            # UI'ı güncelle (signal ile - QueuedConnection)
            self.esp_status_received.emit(coil_id, disconnected_status)
            # esp_last_seen'i sıfırla
            if hasattr(self, 'esp_last_seen'):
                self.esp_last_seen.pop(coil_id, None)
        
        # MQTT disconnected signal'ı emit et (UnifiedControlWindow için)
        self.mqtt_disconnected.emit()
        
        # Notification panel'e bildir
        if hasattr(self, 'notification_panel'):
            self.notification_panel.add_notification(
                "Sinyal akışı koptu, yeniden bağlantı kuruluyor...", 
                "warning"
            )
        
        # Auto-reconnect başlat (GUI Stability Fix #1)
        # ✅ THREAD SAFETY FIX: Timer'ları sadece main thread'den başlat
        # MQTT callback thread'inden QTimer.start() çağrılmamalı
        if not self.mqtt_reconnect_timer.isActive():
            self.mqtt_retry_count = 0
            self.mqtt_retry_delay = 2000
            # ✅ Use QMetaObject.invokeMethod for thread-safe timer start
            from PyQt6.QtCore import QMetaObject, Q_ARG
            QMetaObject.invokeMethod(
                self.mqtt_reconnect_timer,
                "start",
                Qt.ConnectionType.QueuedConnection,
                Q_ARG(int, self.mqtt_retry_delay)
            )
            self.logger.info("MQTT auto-reconnect başlatıldı (thread-safe)")

    def on_mqtt_subscribe(self, client, userdata, mid, granted_qos, properties=None):
        """
        MQTT subscription onaylandığında çalışır.
        """
        self.logger.info(f"MQTT subscription onaylandı: mid={mid}, qos={granted_qos}")
        
        # QoS 128 = hata, 0-2 = başarılı
        if not all(qos < 128 for qos in granted_qos):
            self.logger.warning(f"Bazı subscription'lar başarısız oldu: {granted_qos}")
    
    def _parse_json_with_fallback(self, payload, topic=""):
        """
        JSON parse with multiple fallback strategies.
        Returns: parsed dict or None if all attempts fail
        """
        import re
        
        # First attempt: Try parsing without any cleaning (fast path for clean data)
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            pass
        
        # Second attempt: Remove control characters
        try:
            payload_cleaned = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F]', '', payload)
            return json.loads(payload_cleaned)
        except json.JSONDecodeError:
            pass
        
        # Third attempt: More aggressive cleaning
        try:
            payload_aggressive = re.sub(r'[\x00-\x1F]', '', payload)
            return json.loads(payload_aggressive)
        except json.JSONDecodeError:
            pass
        
        # Last resort: Extract first balanced JSON object
        def _extract_first_balanced_json(s: str) -> Optional[str]:
            depth = 0
            start = None
            for i, c in enumerate(s):
                if c == '{':
                    if depth == 0:
                        start = i
                    depth += 1
                elif c == '}':
                    depth -= 1
                    if depth == 0 and start is not None:
                        return s[start:i+1]
            return None
        
        extracted = _extract_first_balanced_json(payload)
        if extracted:
            try:
                return json.loads(extracted)
            except json.JSONDecodeError:
                pass
        
        # All attempts failed
        self.logger.error(f"JSON parse başarısız (topic: {topic})")
        # Payload'ı her zaman logla (ERROR seviyesinde)
        payload_size = len(payload)
        if payload_size > 500:
            self.logger.error(f"Payload (ilk 500/{payload_size} karakter): {payload[:500]}")
        else:
            self.logger.error(f"Payload ({payload_size} karakter): {payload}")
        return None

    def on_mqtt_message(self, client, userdata, msg):
        """
        MQTT mesajları geldiğinde çalışır.
        
        pemf/coil/+/sensors ve pemf/coil/+/status konularından gelen
        JSON verilerini işler.
        
        Performance: JSON parse cache kullanır - aynı payload'ları tekrar parse etmez.
        """
        try:
            # Check if MainWindow object is still valid
            try:
                # Test if object is still alive by accessing an attribute
                _ = self.mqtt_client
            except RuntimeError:
                # Object has been deleted, silently return
                return
            
            topic = msg.topic
            payload = msg.payload.decode('utf-8', errors='replace')
            
            # CRITICAL FIX: Retained message filtering (prevents stale ESP data on restart)
            # Retained messages are last-known state from broker - ignore them for real-time data
            is_retained = getattr(msg, 'retain', False)
            
            if is_retained:
                # Retained messages - ignore them for status and sensor data
                # They represent old state, not current ESP status
                if topic.endswith('/status') or topic.endswith('/sensors'):
                    if self.logger.isEnabledFor(logging.DEBUG):
                        self.logger.debug("Ignoring retained message from %s (stale data)", topic)
                    return
            
            # Clean logging: Only debug level for MQTT messages
            # Performans optimizasyonu: Lazy evaluation kullan (%s formatı)
            if self.logger.isEnabledFor(logging.DEBUG):
                self.logger.debug("MQTT message received: %s (retained=%s)", topic, is_retained)
            
            # JSON Parse Cache (Performance Optimization)
            payload_hash = hash(payload)
            if payload_hash in self._json_parse_cache:
                data = self._json_parse_cache[payload_hash]
            else:
                # Cache miss - parse and store
                data = self._parse_json_with_fallback(payload, topic)
                if data is not None:
                    # LRU-like cache: Remove oldest entry if cache is full
                    if len(self._json_parse_cache) >= self._json_cache_max_size:
                        # Remove first (oldest) entry
                        first_key = next(iter(self._json_parse_cache))
                        del self._json_parse_cache[first_key]
                    self._json_parse_cache[payload_hash] = data
            
            # If still no data, skip message
            if data is None:
                return
            
            # Extract coil ID from topic
            topic_parts = topic.split('/')
            if len(topic_parts) >= 3:
                coil_id = topic_parts[2]
                
                if topic.endswith('/sensors'):
                    # Metrics: MQTT mesaj counter
                    self.metrics.increment(f'mqtt_messages_received')
                    self.metrics.increment(f'mqtt_sensor_data_{coil_id}')
                    
                    # DEBUG: MQTT mesajı geldi - timestamp logla (1Hz veri akışı)
                    mqtt_receive_time = time.time()
                    temp_value = data.get('object_temp', 0)
                    mag_value = data.get('magnetic_field', 0)
                    current_value = data.get('current', 0)
                    # Verbose 1Hz logging removed for performance
                    
                    # Metrics: Sensor değerlerini gauge olarak kaydet
                    self.metrics.set_gauge(f'sensor_temp_{coil_id}', temp_value)
                    self.metrics.set_gauge(f'sensor_magnetic_{coil_id}', mag_value)
                    self.metrics.set_gauge(f'sensor_current_{coil_id}', current_value)
                    
                    # Performans optimizasyonu: Throttled logging (10 saniyede bir)
                    if self.logger.isEnabledFor(logging.DEBUG):
                        current_time = time.time()
                        if current_time - self.last_sensor_log_time.get(coil_id, 0) > 10:
                            # None değerleri 0 ile değiştir (logging hatası önleme)
                            temp_log = temp_value if temp_value is not None else 0.0
                            mag_log = mag_value if mag_value is not None else 0.0
                            current_log = current_value if current_value is not None else 0.0
                            self.logger.debug("Sensor data from coil %s: T=%.1f°C, M=%.2fmT, I=%.2fA", 
                                            coil_id, temp_log, mag_log, current_log)
                            self.last_sensor_log_time[coil_id] = current_time
                    
                    # Thread-safe sensor data update (GUI Stability Fix #2)
                    self.mqtt_mutex.lock()
                    try:
                        # ESP'den pwm_duty_cycle olarak gelebilir, pwm_duty olarak kaydediyoruz
                        pwm_duty_value = data.get('pwm_duty_cycle') or data.get('pwm_duty', 0)
                        self.latest_sensor_data = {
                            'object_temp': data.get('object_temp', 0),
                            'ambient_temp': data.get('ambient_temp', 0),
                            'magnetic_field': data.get('magnetic_field', 0),
                            'current': data.get('current', 0),
                            'coil_id': coil_id,
                            'timestamp': data.get('timestamp', 0),
                            'sensors_ok': data.get('sensors_ok', False),
                            'temp_sensor_ok': data.get('temp_sensor_ok', False),
                            'magnetic_sensor_ok': data.get('magnetic_sensor_ok', False),
                            'current_sensor_ok': data.get('current_sensor_ok', True),
                            # PWM status from ESP8266 (if available in sensor data)
                            # ESP'den pwm_duty_cycle olarak gelebilir, pwm_duty olarak kaydediyoruz
                            'pwm_active': data.get('pwm_active', False),
                            'pwm_frequency': data.get('pwm_frequency', 0),
                            'pwm_duty': pwm_duty_value,
                            'pwm_duration': data.get('pwm_duration'),
                            'pwm_remaining_time': data.get('pwm_remaining_time')
                        }
                        # Veri güncellenme zamanını kaydet
                        self.latest_sensor_data_timestamp = time.time()
                        
                        # Adaptive FPS: Flag'i set et - yeni veri var, grafik güncellensin
                        self.has_new_sensor_data = True
                    finally:
                        self.mqtt_mutex.unlock()
                    
                    # Sensor verilerini SensorDataWindow'a gönder (with safety check)
                    try:
                        self.sensor_data_received.emit(coil_id, data)
                    except RuntimeError:
                        # Object deleted during emission, return silently
                        return
                    
                    # UnifiedControlWindow için sensor_data_updated signal'ı emit et
                    try:
                        self.sensor_data_updated.emit(coil_id, data)
                    except RuntimeError:
                        return
                    
                    # Sensor verilerinden basit status oluştur
                    sensor_status = {
                        'coil_id': coil_id,
                        'wifi_connected': True,  # Mesaj geliyorsa WiFi bağlı
                        'mqtt_connected': True,  # Mesaj geliyorsa MQTT bağlı
                        'sensors_ok': data.get('sensors_ok', False),
                        'temp_sensor_ok': data.get('temp_sensor_ok', False),
                        'magnetic_sensor_ok': data.get('magnetic_sensor_ok', False),
                        'current_sensor_ok': data.get('current_sensor_ok', True),
                        'timestamp': data.get('timestamp', 0),
                        'uptime': data.get('timestamp', 0)  # timestamp'i uptime olarak kullan
                    }
                    # ESP durum panelini güncelle (signal ile main thread'de) with safety check
                    try:
                        self.esp_status_received.emit(coil_id, sensor_status)
                    except RuntimeError:
                        return

                    # Heartbeat timestamp'ini güncelle
                    if hasattr(self, 'esp_last_seen'):
                        self.esp_last_seen[coil_id] = time.time()
                    
                    # Enerji hesaplama (KPI Dashboard bağımsız)
                    try:
                        current_A = data.get('current', 0.0)
                        if current_A and current_A > 0.01:  # 0.01A minimum eşik
                            # Voltaj hesapla: V = I * R
                            voltage_V = current_A * self.COIL_RESISTANCE
                            # Güç hesapla: P = V * I = I² * R
                            power_W = current_A * voltage_V
                            
                            # Geçen süreyi hesapla
                            current_time = time.time()
                            time_elapsed_s = current_time - self.last_energy_update_time
                            
                            self.last_energy_update_time = current_time
                            
                            # Enerji birikimi: E = P * t (Wh = W * h)
                            energy_increment_wh = power_W * (time_elapsed_s / 3600.0)
                            self.total_energy_wh += energy_increment_wh
                            
                            # KPI'yı güncelle
                            self.update_kpi_energy(self.total_energy_wh)
                    except Exception as e:
                        if self.logger.isEnabledFor(logging.DEBUG):
                            self.logger.debug(f"Enerji hesaplama hatası: {e}")
                
                elif topic.endswith('/events'):
                    # Handle event messages (e.g., WiFi Disconnected)
                    # Payload example: {"type":"wifi_disconnected", "message":"Exiting Cloud Mode"}
                    event_type = data.get('type')
                    message = data.get('message')
                    
                    if event_type == 'wifi_disconnected':
                        # Alert User via Notification Center or Popup
                        error_msg = f"COIL {coil_id} IS OFFLINE!\nReason: WiFi Connection Lost.\nDevice has switched to BLE Mode.\n\nNOTE: To continue control from PC, ensure BLE is active. If not supported, use the Android App."
                        
                        self.logger.warning(f"Device {coil_id} went offline (BLE Mode).")
                        
                        # Eğer GUI thread içindeysek direkt göster, değilse signal
                        # on_mqtt_message, MQTT thread'inde çalışır -> Signal şart
                        self.error_occurred.emit(error_msg)
                    
                    # KPI Dashboard'a sensor verisi gönder (gerçek zamanlı enerji izleme)
                    if hasattr(self, 'kpi_dashboard_window') and self.kpi_dashboard_window and self.kpi_dashboard_window.isVisible():
                        try:
                            self.kpi_dashboard_window.update_sensor_data(coil_id, self.latest_sensor_data)
                        except Exception as e:
                            if self.logger.isEnabledFor(logging.DEBUG):
                                self.logger.debug(f"KPI dashboard güncelleme hatası: {e}")

                    # Sadece aktif bobinlerin verilerini işle
                    received_coil_id = int(coil_id)
                    
                    # Thread-safe active_coils kontrolü (Thread Safety Fix)
                    is_coil_active = self.is_coil_active(received_coil_id)
                    
                    # Veri toplama aktifse ve bu bobin aktifse işle
                    if self.graph_data_collection_active and is_coil_active:
                        # Update main graph data
                        if self.graph_start_time is None:
                            self.graph_start_time = time.time()
                            self.logger.info(f"Grafik başlangıç zamanı ayarlandı (ilk veri): Bobin {received_coil_id}")
                        
                        # Zaman verisi sadece bir kez eklenir (tüm aktif bobinler aynı zaman eksenini kullanır)
                        # Her sensör mesajı için zaman ekle (tüm bobinler senkronize)
                        current_time = time.time() - self.graph_start_time
                        
                        # Update the last known value and graph data (Thread-Safe)
                        mag_value = data.get('magnetic_field', 0)
                        temp_value = data.get('object_temp', 0)
                        
                        # Thread-safe update: Tüm grafik verileri mutex ile korunuyor
                        self.graph_data_mutex.lock()
                        try:
                            # Update last known values
                            self.last_known_mag[received_coil_id] = mag_value
                            self.last_known_temp[received_coil_id] = temp_value
                            
                            # Zaman verisi sadece henüz eklenmemişse veya yeni bir zaman adımı varsa ekle
                            if not self.graph_time_data or current_time > self.graph_time_data[-1]:
                                self.graph_time_data.append(current_time)
                            
                            # Sadece aktif bobinin verilerini deques'e ekle
                            self.graph_magnetic_field_data[received_coil_id].append(mag_value)
                            self.graph_temperature_data[received_coil_id].append(temp_value)
                        finally:
                            self.graph_data_mutex.unlock()
                    else:
                        # Veri toplama aktif değil veya bobin aktif değil, sadece son değerleri güncelle (Thread-Safe)
                        self.graph_data_mutex.lock()
                        try:
                            self.last_known_mag[received_coil_id] = data.get('magnetic_field', 0)
                            self.last_known_temp[received_coil_id] = data.get('object_temp', 0)
                        finally:
                            self.graph_data_mutex.unlock()

                
                elif topic.endswith('/status'):
                    # ESP8266 durum mesajı (WiFi, MQTT, PWM, sensör durumu)
                    # Performans optimizasyonu: Lazy evaluation
                    if self.logger.isEnabledFor(logging.DEBUG):
                        self.logger.debug("Coil %s durum verisi: WiFi=%s, Portal=%s, MQTT=%s", 
                                        coil_id, data.get('wifi_connected'), data.get('portal_active'), data.get('mqtt_connected'))
                    
                    # CRITICAL: Portal durumu kontrolü - kullanıcıya bildir
                    # Portal açıksa ve daha önce bildirilmediyse dialog göster
                    portal_active = data.get('portal_active', False)
                    if portal_active:
                        # Portal açık - kullanıcıya bildirim göster
                        if not hasattr(self, '_portal_notified_coils'):
                            self._portal_notified_coils = set()
                        
                        # Bu bobin için henüz bildirim gösterilmediyse göster
                        if coil_id not in self._portal_notified_coils:
                            portal_ssid = data.get('portal_ssid', f'PEMF-Coil-{coil_id}')
                            portal_ip = data.get('portal_ip', '192.168.4.1')
                            portal_message = f"Bobin portal SSID: {portal_ssid}\nPortal IP: {portal_ip}"
                            
                            # Portal bildirimi gönder (signal ile main thread'de dialog açılacak)
                            try:
                                self.portal_notification_received.emit(coil_id, portal_message)
                                self._portal_notified_coils.add(coil_id)
                                self.logger.info(f"Portal notification sent for Coil {coil_id}: {portal_ssid}")
                            except RuntimeError:
                                return
                    else:
                        # Portal kapalı - bildirim listesinden kaldır (tekrar açılırsa gösterilsin)
                        if hasattr(self, '_portal_notified_coils') and coil_id in self._portal_notified_coils:
                            self._portal_notified_coils.discard(coil_id)
                            self.logger.info(f"Portal closed for Coil {coil_id} - removed from notification list")
                    
                    # Update latest_sensor_data with PWM status from status message if available
                    # ESP'den pwm_duty_cycle olarak geliyor, pwm_duty olarak kaydediyoruz
                    if 'pwm_active' in data or 'pwm_frequency' in data or 'pwm_duty_cycle' in data or 'pwm_duty' in data:
                        self.mqtt_mutex.lock()
                        try:
                            if not hasattr(self, 'latest_sensor_data') or self.latest_sensor_data is None:
                                self.latest_sensor_data = {}
                            # Update PWM status in latest_sensor_data
                            # ESP'den pwm_duty_cycle olarak geliyor, pwm_duty olarak kaydediyoruz
                            if 'pwm_active' in data:
                                self.latest_sensor_data['pwm_active'] = data.get('pwm_active', False)
                            if 'pwm_frequency' in data:
                                self.latest_sensor_data['pwm_frequency'] = data.get('pwm_frequency', 0)
                            # ESP'den pwm_duty_cycle olarak geliyor, pwm_duty olarak kaydediyoruz
                            pwm_duty_value = data.get('pwm_duty_cycle') or data.get('pwm_duty', 0)
                            self.latest_sensor_data['pwm_duty'] = pwm_duty_value
                            if 'pwm_duration' in data:
                                self.latest_sensor_data['pwm_duration'] = data.get('pwm_duration')
                            if 'pwm_remaining_time' in data:
                                self.latest_sensor_data['pwm_remaining_time'] = data.get('pwm_remaining_time')
                            self.latest_sensor_data['coil_id'] = coil_id
                            self.latest_sensor_data_timestamp = time.time()
                            # Performans optimizasyonu: Lazy evaluation
                            if self.logger.isEnabledFor(logging.DEBUG):
                                self.logger.debug("Updated PWM status from status message for coil %s: pwm_active=%s, pwm_frequency=%s, pwm_duty=%s, pwm_duration=%s, pwm_remaining_time=%s",
                                                coil_id, data.get('pwm_active'), data.get('pwm_frequency'), pwm_duty_value, 
                                                data.get('pwm_duration'), data.get('pwm_remaining_time'))
                        finally:
                            self.mqtt_mutex.unlock()
                    
                    # ESP durum panelini güncelle (signal ile main thread'de) with safety check
                    try:
                        self.esp_status_received.emit(coil_id, data)
                    except RuntimeError:
                        return
                    
                    # Heartbeat timestamp'ini güncelle (/status mesajı geldiğinde de)
                    if hasattr(self, 'esp_last_seen'):
                        self.esp_last_seen[coil_id] = time.time()
                    
                    # UnifiedControlWindow için coil_status_updated signal'ı emit et
                    # PWM bilgisini de status_data'ya ekle
                    status_data_with_pwm = data.copy()
                    if 'pwm_active' in data:
                        status_data_with_pwm['pwm_active'] = data['pwm_active']
                    if 'pwm_frequency' in data:
                        status_data_with_pwm['pwm_frequency'] = data['pwm_frequency']
                    if 'pwm_duty_cycle' in data:
                        status_data_with_pwm['pwm_duty_cycle'] = data['pwm_duty_cycle']
                    if 'pwm_duration' in data:
                        status_data_with_pwm['pwm_duration'] = data['pwm_duration']
                    if 'pwm_remaining_time' in data:
                        status_data_with_pwm['pwm_remaining_time'] = data['pwm_remaining_time']
                    self.coil_status_updated.emit(coil_id, status_data_with_pwm)

                elif topic.endswith('/events'):
                    # ESP8266'dan gelen olay bildirimleri
                    event_type = data.get('event_type')
                    message = data.get('message', '')
                    
                    self.logger.info(f"Event received from Coil {coil_id}: {event_type} - {message}")
                    
                    if event_type == 'portal_opened':
                        self.portal_notification_received.emit(coil_id, message)

                elif topic.endswith('/ack'):
                    # ESP8266'dan gelen command acknowledgment (GUI Stability Fix #4)

                    command_id = data.get('command_id')
                    success = data.get('success', False)
                    
                    # UnifiedControlWindow'a ACK ilet
                    if hasattr(self, 'unified_control_window') and self.unified_control_window:
                        try:
                            self.unified_control_window._handle_command_ack(int(coil_id), command_id, success)
                        except Exception as e:
                            self.logger.error(f"ACK handling error: {e}")
                
                elif topic.endswith('/events'):
                    # ESP8266'dan gelen WiFi/MQTT event mesajları
                    event_type = data.get('event_type', 'unknown')
                    message = data.get('message', '')
                    wifi_connected = data.get('wifi_connected', False)
                    portal_active = data.get('portal_active', False)
                    
                    # Performans optimizasyonu: Lazy evaluation (%s formatı)
                    self.logger.info("Coil %s event: %s - %s", coil_id, event_type, message)
                    
                    # Event tipine göre işle
                    if event_type == 'wifi_disconnected':
                        # WiFi bağlantısı kesildi
                        # Performans optimizasyonu: Lazy evaluation
                        self.logger.warning("Coil %s WiFi bağlantısı kesildi", coil_id)
                        if hasattr(self, 'notification_panel'):
                            self.notification_panel.add_notification(
                                f"⚠️ Coil {coil_id} WiFi bağlantısı kesildi, yeniden bağlanılıyor...",
                                "warning"
                            )
                        portal_ssid = ''
                        portal_ip = ''
                        if portal_active:
                            portal_ssid = data.get('portal_ssid', 'PEMF-Coil-' + str(coil_id))
                            raw_portal_ip = data.get('portal_ip', '')
                            portal_ip = self._maybe_notify_portal_open(coil_id, portal_ssid, raw_portal_ip)
                        # ESP durum panelini güncelle
                        status_data = {
                            'coil_id': coil_id,
                            'wifi_connected': False,
                            'portal_active': portal_active,
                            'wifi_ssid': '',
                            'wifi_ip': '',
                            'portal_ssid': portal_ssid,
                            'portal_ip': portal_ip
                        }
                        try:
                            self.esp_status_received.emit(coil_id, status_data)
                        except RuntimeError:
                            return
                        if portal_active:
                            self.esp_portal_status[coil_id] = {
                                'coil_id': coil_id,
                                'portal_active': True,
                                'portal_ssid': portal_ssid,
                                'portal_ip': portal_ip
                            }
                    
                    elif event_type == 'wifi_connected':
                        # WiFi bağlantısı kuruldu
                        wifi_ssid = data.get('wifi_ssid', '')
                        wifi_ip = data.get('wifi_ip', '')
                        # RSSI verisi kaldırıldı (event mesajından RSSI işlenmiyor)
                        # Performans optimizasyonu: Lazy evaluation
                        self.logger.info("Coil %s WiFi bağlantısı kuruldu: %s (%s)", coil_id, wifi_ssid, wifi_ip)
                        if hasattr(self, 'notification_panel'):
                            self.notification_panel.add_notification(
                                f"✅ Coil {coil_id} WiFi bağlantısı kuruldu: {wifi_ssid}\n"
                                f"IP: {wifi_ip}",
                                "success"
                            )
                        # ESP durum panelini güncelle
                        status_data = {
                            'coil_id': coil_id,
                            'wifi_connected': True,
                            'portal_active': False,
                            'wifi_ssid': wifi_ssid,
                            'wifi_ip': wifi_ip,
                            'portal_ssid': '',
                            'portal_ip': ''
                        }
                        try:
                            self.esp_status_received.emit(coil_id, status_data)
                        except RuntimeError:
                            return
                        self.portal_notified.discard(coil_id)
                        self.esp_portal_status[coil_id] = {
                            'coil_id': coil_id,
                            'portal_active': False,
                            'portal_ssid': '',
                            'portal_ip': ''
                        }
                    
                    elif event_type == 'portal_opened':
                        # WiFi Portal açıldı
                        portal_ssid = data.get('portal_ssid', 'PEMF-Coil-' + str(coil_id))
                        raw_portal_ip = data.get('portal_ip', '')
                        portal_ip = self._maybe_notify_portal_open(coil_id, portal_ssid, raw_portal_ip)
                        # Performans optimizasyonu: Lazy evaluation
                        self.logger.warning("Coil %s WiFi Portal açıldı: %s", coil_id, portal_ssid)
                        # ESP durum panelini güncelle
                        status_data = {
                            'coil_id': coil_id,
                            'wifi_connected': False,
                            'portal_active': True,
                            'wifi_ssid': '',
                            'wifi_ip': '',
                            'portal_ssid': portal_ssid,
                            'portal_ip': portal_ip
                        }
                        try:
                            self.esp_status_received.emit(coil_id, status_data)
                        except RuntimeError:
                            return
                        self.esp_portal_status[coil_id] = {
                            'coil_id': coil_id,
                            'portal_active': True,
                            'portal_ssid': portal_ssid,
                            'portal_ip': portal_ip
                        }
                    
                    elif event_type == 'portal_closed':
                        # WiFi Portal kapatıldı
                        # Performans optimizasyonu: Lazy evaluation
                        self.logger.info("Coil %s WiFi Portal kapatıldı", coil_id)
                        self._notify_portal_closed(coil_id, f"✅ Coil {coil_id} WiFi Portal kapatıldı", "info")
                    
                    elif event_type == 'portal_timeout':
                        # Portal timeout
                        # Performans optimizasyonu: Lazy evaluation
                        self.logger.warning("Coil %s WiFi Portal timeout (5 dakika)", coil_id)
                        self._notify_portal_closed(
                            coil_id,
                            f"⏱️ Coil {coil_id} WiFi Portal timeout - 5 dakika sonra otomatik kapandı",
                            "warning"
                        )
                    
                    elif event_type == 'mqtt_connected':
                        # MQTT bağlantısı kuruldu
                        # Performans optimizasyonu: Lazy evaluation
                        self.logger.info("Coil %s MQTT broker'a bağlandı", coil_id)
                        # ESP durum panelini güncelle
                        status_data = {
                            'coil_id': coil_id,
                            'mqtt_connected': True
                        }
                        try:
                            self.esp_status_received.emit(coil_id, status_data)
                        except RuntimeError:
                            return
                    
                    elif event_type == 'device_ready':
                        # ESP8266 başlatıldı
                        # Performans optimizasyonu: Lazy evaluation
                        self.logger.info("Coil %s ESP8266 başlatıldı ve hazır", coil_id)
                        if hasattr(self, 'notification_panel'):
                            self.notification_panel.add_notification(
                                f"✅ Bobin {coil_id} başlatıldı ve hazır",
                                "success"
                            )
                
                elif topic.endswith('/alarm'):
                    # ESP8266'dan gelen alarm mesajları (GUI Stability Fix - ESP entegrasyonu)

                    # Performans optimizasyonu: Lazy evaluation
                    self.logger.warning("Coil %s alarm: %s", coil_id, data)
                    
                    alarm_type = data.get('alarm_type', 'unknown')
                    reason = data.get('reason', 'Bilinmeyen sebep')
                    
                    # Notification panel'e bildir
                    if hasattr(self, 'notification_panel'):
                        if alarm_type == 'safety_violation':
                            self.notification_panel.add_notification(
                                f"🚨 Coil {coil_id} Güvenlik Uyarısı: {reason}",
                                "error"
                            )
                        elif alarm_type == 'low_memory':
                            free_heap = data.get('free_heap', 0)
                            self.notification_panel.add_notification(
                                f"⚠️ Coil {coil_id} Düşük Bellek: {free_heap} bytes",
                                "warning"
                            )
                        else:
                            self.notification_panel.add_notification(
                                f"⚠️ Coil {coil_id} Alarm: {reason}",
                                "warning"
                            )
            
            # Handle session control messages from Android
            elif topic == "pemf/system/session/control":
                try:
                    command = data.get('command')
                    if command == 'start_session':
                        # Android'den session başlatma komutu geldi
                        patient_name = data.get('patient_name', 'Android Kullanıcısı')
                        duration = data.get('duration_minutes', 15)
                        frequency = data.get('frequency', 50.0)
                        intensity = data.get('intensity', 20.0)
                        target = data.get('target', 'Genel Tedavi')
                        
                        self.logger.info(f"Android'den session başlatma komutu: {patient_name}, {duration}dk")
                        
                        # UI'da notification göster
                        if hasattr(self, 'notification_panel'):
                            self.notification_panel.add_notification(
                                f"📱 Android'den tedavi başlatma: {patient_name}",
                                "info"
                            )
                        
                        # Session başlat (eğer halihazırda aktif değilse)
                        if not getattr(self, 'is_treatment_active', False):
                            # Start treatment with data from Android
                            # Note: Bu metod MainWindow'da implement edilmeli
                            if hasattr(self, 'start_treatment_from_mqtt'):
                                self.start_treatment_from_mqtt(patient_name, duration, frequency, intensity, target)
                            else:
                                self.logger.warning("start_treatment_from_mqtt metodu implement edilmemiş")
                        else:
                            self.logger.warning("Zaten aktif bir session var, Android komutu ignore edildi")
                    
                    elif command == 'stop_session':
                        # Android'den session durdurma komutu geldi
                        self.logger.info("Android'den session durdurma komutu")
                        
                        # UI'da notification göster
                        if hasattr(self, 'notification_panel'):
                            self.notification_panel.add_notification(
                                "📱 Android'den tedavi durdurma komutu",
                                "info"
                            )
                        
                        # Session durdur
                        if getattr(self, 'is_treatment_active', False):
                            # Stop treatment
                            if hasattr(self, 'stop_treatment'):
                                self.stop_treatment()
                            else:
                                self.logger.warning("stop_treatment metodu bulunamadı")
                        else:
                            self.logger.info("Aktif session yok, Android durdurma komutu ignore edildi")
                    
                    else:
                        self.logger.warning(f"Bilinmeyen session control command: {command}")
                        
                except Exception as e:
                    self.logger.error(f"Session control message handling error: {e}", exc_info=True)
            
            else:
                self.logger.debug(f"Unknown MQTT topic format: {topic}")
                    
        except json.JSONDecodeError as e:
            self.logger.error(f"MQTT mesaj JSON parse hatası: {e}", exc_info=True)
        except Exception as e:
            self.logger.error(f"MQTT mesaj işleme hatası: {e}", exc_info=True)

    def update_clock(self):
        """Saat göstergesini güncelle"""
        try:
            now = datetime.now()
            self.clock.setText(f"\u23F0 {now.strftime('%d/%m/%Y %H:%M:%S')}")
        except Exception as e:
            self.logger.error(f"Clock güncelleme hatası: {e}", exc_info=True)
    
    def _on_graph_update_tick(self):
        """
        Grafik güncelleme timer'ı callback'i (50ms = 20 FPS).
        Adaptive FPS: Sadece yeni veri varsa güncelleme yapar.
        """
        try:
            # Adaptive FPS: Sadece yeni veri geldiyse grafik güncelle
            if self.has_new_sensor_data:
                # Metrics: Grafik güncelleme süresi
                with metrics_timer('graph_update'):
                    self.update_main_graph()
                self.has_new_sensor_data = False  # Flag'i sıfırla
            # Veri yoksa skip et - CPU tasarrufu
        except Exception as e:
            # Metrics: Hata tracking
            self.metrics.record_error('graph_update_error', str(e))
            
            # Performans optimizasyonu: Exception throttling (5 saniyede bir detaylı log)
            current_time = time.time()
            self.graph_error_count += 1
            if current_time - self.last_graph_error_time > 5:
                self.logger.error("Graph update hatası (%d hata son 5 saniyede): %s", self.graph_error_count, e, exc_info=True)
                self.graph_error_count = 0
                self.last_graph_error_time = current_time
    
    def _on_unified_1hz_tick(self):
        """
        Birleşik 1Hz timer callback'i (Timer Optimization).
        Tüm 1Hz güncellemeleri burada yapılır:
        - Saat güncellemesi
        - Çalışma süresi artırma
        - Seans ilerlemesi güncelleme
        
        NOT: Grafik güncellemesi graph_update_timer'da (50ms = 20 FPS) çalışıyor.
        Graph verileri MQTT callback'de direkt deque'ya ekleniyor (thread-safe).
        """
        try:
            # 1. Saat güncellemesi
            self.update_clock()
            
            # 2. Çalışma süresi artırma
            self.increment_working_time()
            
            # 3. Seans ilerlemesi güncelleme (eğer aktifse)
            if hasattr(self, 'is_treatment_active') and self.is_treatment_active:
                self.update_treatment_progress()
        except Exception as e:
            # Performans optimizasyonu: Lazy evaluation
            self.logger.error("Unified 1Hz timer hatası: %s", e, exc_info=True)

    def input_button_clicked(self):
        sender = self.sender()
        button_text = sender.text()
        self.logger.info(f"Button clicked: {button_text}")




    def open_sensor_data_window(self):
        import sys
        if getattr(sys, 'frozen', False):
            # Frozen exe - use absolute import
            from windows.sensor_data_window import SensorDataWindow
        else:
            # Development - try both paths
            try:
                from windows.sensor_data_window import SensorDataWindow
            except (ImportError, ModuleNotFoundError):
                from sensor_data_window import SensorDataWindow
        if not hasattr(self, 'sensor_data_window') or not self.sensor_data_window.isVisible():
            self.sensor_data_window = SensorDataWindow()
            self.sensor_data_window.setMainWindow(self)
            # MQTT sensor data signal-slot bağlantısını kur
            self.sensor_data_window.connect_to_main_window(self)
            self.sensor_data_window.show()
        else:
            self.sensor_data_window.activateWindow()
            self.sensor_data_window.raise_()

    # --- EKLENEN METOD BURASI ---
    def _wait_for_file_access(self, file_path, timeout=10.0):
        """Belirtilen dosya erişilebilir olana kadar bekle (max timeout sn)."""
        import time
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                with open(file_path, 'rb') as f:
                    f.read(1)
                return True
            except Exception:
                time.sleep(0.2)
        return False
    # ---------------------------

    def open_digital_twin_window(self):
        """PEMF Digital Twin uygulamasını gömülü dosyalardan çalıştır"""
        from pathlib import Path
        
        # CRITICAL DEBUG: Sistem bilgilerini logla
        self.logger.info("="*60)
        self.logger.info("DIGITAL TWIN BAŞLATMA - DEBUG BİLGİLERİ")
        self.logger.info(f"sys.frozen: {getattr(sys, 'frozen', False)}")
        self.logger.info(f"sys._MEIPASS var mı: {hasattr(sys, '_MEIPASS')}")
        if hasattr(sys, '_MEIPASS'):
            self.logger.info(f"sys._MEIPASS: {sys._MEIPASS}")
        self.logger.info(f"__file__: {__file__}")
        self.logger.info(f"Current working directory: {os.getcwd()}")
        self.logger.info("="*60)
        
        # Eğer zaten açılıyorsa (opening flag), bekle
        if hasattr(self, 'digital_twin_opening') and self.digital_twin_opening:
            self.logger.info("Digital Twin zaten açılıyor, lütfen bekleyin...")
            if hasattr(self, 'notification_panel'):
                self.notification_panel.add_notification(
                    "Digital Twin açılıyor, lütfen bekleyin...", 
                    "info"
                )
            return
        
        # Eğer zaten çalışan bir Digital Twin process varsa, onu öne getir
        if hasattr(self, 'digital_twin_process') and self.digital_twin_process is not None:
            try:
                # Process hala çalışıyor mu kontrol et
                if self.digital_twin_process.poll() is None:
                    # Process aktif, pencereyi öne getir
                    self.logger.info("Digital Twin zaten çalışıyor, pencere öne getiriliyor...")
                    if sys.platform == 'win32' and hasattr(self, 'digital_twin_pid'):
                        self._bring_digital_twin_to_front(self.digital_twin_pid)
                    if hasattr(self, 'notification_panel'):
                        self.notification_panel.add_notification(
                            "Digital Twin zaten açık", 
                            "info"
                        )
                    return
                else:
                    # Process bitmiş, yeni instance açılabilir
                    self.digital_twin_process = None
                    self.digital_twin_pid = None
            except Exception as e:
                self.logger.warning(f"Digital Twin process kontrolü hatası: {e}")
                self.digital_twin_process = None
                self.digital_twin_pid = None
        
        # Açılıyor flag'ini set et
        self.digital_twin_opening = True
        
        try:
            self.logger.info("Digital Twin penceresi açılıyor...")
            
            # PyInstaller bundle içindeki gömülü dosyaların yolu
            bundle_path = None
            
            if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
                # PyInstaller'da dosyalar buildPEMF klasörü altında
                possible_paths = [
                    Path(sys._MEIPASS) / "buildPEMF",
                    Path(sys._MEIPASS) / "PEMF_Data" / "buildPEMF",
                    Path(sys.executable).parent / "buildPEMF",
                ]
                self.logger.info("PyInstaller modu - buildPEMF aranıyor...")
                for possible_path in possible_paths:
                    self.logger.info(f"  Kontrol ediliyor: {possible_path}")
                    self.logger.info(f"    Var mı: {possible_path.exists()}")
                    if possible_path.exists():
                        pemf_exe = possible_path / "PEMF.exe"
                        self.logger.info(f"    PEMF.exe var mı: {pemf_exe.exists()}")
                        if pemf_exe.exists():
                            bundle_path = possible_path
                            self.logger.info(f"  ✓ buildPEMF bulundu: {bundle_path}")
                            break
                
                if bundle_path is None:
                    # Son çare: _MEIPASS'ın içeriğini listele
                    self.logger.error("buildPEMF BULUNAMADI! _MEIPASS içeriği:")
                    try:
                        meipass_contents = list(Path(sys._MEIPASS).iterdir())
                        for item in meipass_contents[:20]:  # İlk 20 öğe
                            self.logger.error(f"  - {item.name}")
                    except Exception as e:
                        self.logger.error(f"_MEIPASS listelenemedi: {e}")
                    
                    QMessageBox.critical(
                        self,
                        "Kritik Hata",
                        f"Digital Twin dosyaları exe içinde bulunamadı!\n\n"
                        f"Aranan konum: {sys._MEIPASS}\\buildPEMF\\PEMF.exe\n\n"
                        f"Bu bir PyInstaller paketleme hatasıdır.\n"
                        f"Lütfen PEMF_GUI.spec dosyasını kontrol edin.\n\n"
                        f"buildPEMF klasörü datas listesine eklenmiş olmalı."
                    )
                    return
            else:
                # Geliştirme ortamında buildPEMF klasörünü kullan
                bundle_path = Path(__file__).parent.parent / "buildPEMF"
                self.logger.info(f"Geliştirme ortamı yolu: {bundle_path}")
            
            build_pemf_path = bundle_path
            self.logger.info(f"Seçilen buildPEMF kaynak yolu: {build_pemf_path}")
            self.logger.info(f"Kaynak PEMF.exe var mı: {(build_pemf_path / 'PEMF.exe').exists()}")
            
            # Kritik dosyaların varlığını kontrol et
            if not (build_pemf_path / 'PEMF.exe').exists():
                error_msg = (
                    f"PEMF.exe kaynak dosyası bulunamadı!\n\n"
                    f"Aranan konum: {build_pemf_path / 'PEMF.exe'}\n\n"
                    f"buildPEMF klasörü eksik veya bozuk."
                )
                self.logger.error(error_msg)
                QMessageBox.critical(self, "Kritik Hata", error_msg)
                return
            
            # HEDEF KONUM (Kalıcı ve Hızlı)
            # Windows: %LOCALAPPDATA%/PEMF_DigitalTwin_Installation
            app_data = Path(os.getenv('LOCALAPPDATA', tempfile.gettempdir()))
            pemf_temp_dir = app_data / "PEMF_DigitalTwin_Installation"
            pemf_temp_dir.mkdir(parents=True, exist_ok=True)
            self.logger.info("Kaynak: %s", build_pemf_path)
            self.logger.info("Hedef (Kalıcı): %s", pemf_temp_dir)
            
            # Progress dialog
            progress_dialog = QProgressDialog("Digital Twin yükleniyor...", "İptal", 0, 100, self)
            progress_dialog.setWindowTitle("Sistem Başlatılıyor")
            progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
            progress_dialog.setMinimumDuration(0)
            
            # Dosya kopyalama thread'ini oluştur ve başlat
            copy_thread = DigitalTwinFileCopyThread(
                build_pemf_path,
                pemf_temp_dir,
                self.logger,
                self
            )
            
            # Signal-slot bağlantıları
            def on_progress_updated(current_step, total_steps, message):
                """İlerleme güncellemesi"""
                if total_steps > 0:
                    progress_dialog.setValue(int(current_step / total_steps * 100))
                progress_dialog.setLabelText(message)
                QApplication.processEvents()  # GUI'yi güncelle
            
            def on_error_occurred(error_message):
                """Hata oluştuğunda"""
                progress_dialog.close()
                QMessageBox.warning(self, "Hata", f"Dosya kopyalama hatası:\n{error_message}")
            
            def on_copy_completed(exe_path, pemf_temp_dir_str, success):
                """Kopyalama tamamlandığında"""
                progress_dialog.close()
                
                # Thread'i temizle
                copy_thread.deleteLater()
                
                if not success:
                    error_msg = (
                        f"PEMF Digital Twin dosyaları kopyalanamadı.\n\n"
                        f"Kaynak konum: {build_pemf_path}\n"
                        f"Hedef konum: {pemf_temp_dir_str}\n\n"
                        f"Lütfen buildPEMF klasörünün doğru konumda olduğundan emin olun."
                    )
                    self.logger.error(error_msg)
                    QMessageBox.warning(self, "Hata", error_msg)
                    return
                
                # PEMF.exe'yi çalıştır
                exe_path_obj = Path(exe_path)
                if exe_path_obj.exists():
                    self.logger.info(f"PEMF.exe bulundu, başlatılıyor: {exe_path}")
                    self.logger.info(f"Çalışma dizini: {pemf_temp_dir_str}")
                    # --- Dosya erişim kontrolü: Tüm dosyalar erişilebilir mi? ---
                    pemf_exe_path = str(exe_path)
                    # Daha sağlam dosya hazır olma kontrolleri: exe ve UnityPlayer.dll erişilebilir mi? PEMF_Data dizini var mı?
                    unity_dll_path = str(Path(pemf_temp_dir_str) / "UnityPlayer.dll")
                    pemf_data_dir = Path(pemf_temp_dir_str) / "PEMF_Data"

                    # Wait for critical files (up to 30s each) to avoid first-run race conditions
                    max_wait = 30.0
                    if not self._wait_for_file_access(pemf_exe_path, timeout=max_wait):
                        self.logger.warning(f"PEMF.exe dosyasına erişilemiyor (timeout): {pemf_exe_path}")
                        QMessageBox.warning(self, "Hata", f"PEMF.exe dosyasına erişilemiyor (kilitli veya kopyalanamadı):\n{pemf_exe_path}")
                        return
                    if Path(unity_dll_path).exists():
                        if not self._wait_for_file_access(unity_dll_path, timeout=max_wait):
                            self.logger.warning(f"UnityPlayer.dll dosyasına erişilemiyor (timeout): {unity_dll_path}")
                            QMessageBox.warning(self, "Hata", f"UnityPlayer.dll dosyasına erişilemiyor (kilitli veya kopyalanamadı):\n{unity_dll_path}")
                            return
                    else:
                        # Eğer UnityPlayer.dll yoksa logla ama devam et (bazı build'lerde olmayabilir)
                        self.logger.debug(f"UnityPlayer.dll bulunamadı: {unity_dll_path} (devam ediliyor)")

                    # PEMF_Data dizinini kontrol et (en az bir dosya olmalı)
                    if not pemf_data_dir.exists() or not any(pemf_data_dir.rglob('*')):
                        # Kısa süre bekle ve tekrar kontrol et (toplam max_wait saniye)
                        start_t = time.time()
                        while time.time() - start_t < max_wait:
                            if pemf_data_dir.exists() and any(pemf_data_dir.rglob('*')):
                                break
                            time.sleep(0.5)
                        else:
                            self.logger.warning(f"PEMF_Data dizini eksik veya boş: {pemf_data_dir}")
                            QMessageBox.warning(self, "Hata", f"PEMF_Data dizini eksik veya boş olabilir:\n{pemf_data_dir}")
                            return
                    
                    # İLK AÇILIŞ BEYAZ EKRAN DÜZELTMESİ:
                    # Unity başlatmadan önce ek bekleme - tüm dosyaların tamamen hazır olmasını sağla
                    # İlk kopyalamadan sonra dosya sistemi ve antivirüs taramaları için ekstra süre
                    self.logger.info("Unity başlatma öncesi hazırlık bekleniyor...")
                    time.sleep(2.0)  # 2 saniye ek bekleme - dosya sistemi stabilizasyonu
                    
                    # Unity uygulamasını pencere modunda aç
                    # Unity uygulamaları kendi dizinlerinde çalışmalı
                    try:
                        # CRITICAL DEBUG: Başlatma öncesi tüm bilgileri logla
                        self.logger.info("="*60)
                        self.logger.info("UNITY BAŞLATMA - DETAYLI BİLGİ")
                        self.logger.info(f"Exe yolu: {exe_path}")
                        self.logger.info(f"Çalışma dizini: {pemf_temp_dir_str}")
                        self.logger.info(f"Exe var mı: {Path(exe_path).exists()}")
                        self.logger.info(f"Exe boyutu: {Path(exe_path).stat().st_size if Path(exe_path).exists() else 'N/A'}")
                        self.logger.info(f"UnityPlayer.dll var mı: {Path(pemf_temp_dir_str).joinpath('UnityPlayer.dll').exists()}")
                        self.logger.info(f"PEMF_Data var mı: {Path(pemf_temp_dir_str).joinpath('PEMF_Data').exists()}")
                        
                        # Data klasörü içeriğini kontrol et
                        pemf_data_path = Path(pemf_temp_dir_str) / "PEMF_Data"
                        if pemf_data_path.exists():
                            data_contents = list(pemf_data_path.iterdir())
                            self.logger.info(f"PEMF_Data içeriği ({len(data_contents)} öğe):")
                            for item in data_contents[:10]:
                                self.logger.info(f"  - {item.name}")
                        else:
                            self.logger.error("PEMF_Data klasörü bulunamadı!")
                        self.logger.info("="*60)
                        
                        # Unity uygulamasını pencere modunda aç (tam ekran değil)
                        # -screen-fullscreen 0: Tam ekranı kapat, normal pencere modu (tüm butonlar aktif)
                        # -screen-width ve -screen-height: Pencere boyutunu ayarla
                        # -logFile: Log dosyası oluştur (debug için)
                        log_file = Path(pemf_temp_dir_str) / "unity_player.log"
                        process = subprocess.Popen(
                            [
                                str(exe_path),
                                "-screen-fullscreen", "0",
                                "-screen-width", "1920",
                                "-screen-height", "1080",
                                "-logFile", str(log_file)
                            ],
                            cwd=str(pemf_temp_dir_str),
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            stdin=subprocess.DEVNULL,
                            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
                        )
                        self.logger.info(f"PEMF Digital Twin başlatıldı (PID: {process.pid}): {exe_path} (Pencere modu)")
                        self.logger.info(f"Unity log dosyası: {log_file}")
                        
                        # Process'i ve PID'yi HEMEN kaydet (callback öncesi - tek instance kontrolü için)
                        self.digital_twin_process = process
                        self.digital_twin_pid = process.pid
                        self.digital_twin_opening = False  # Açılış tamamlandı
                        
                        # İLK AÇILIŞ BEYAZ EKRAN DÜZELTMESİ:
                        # Unity'nin ilk render için biraz zaman tanı (pencere oluşturma + shader derleme)
                        # Bu süre boyunca Unity arka planda hazırlanır
                        self.logger.info("Unity render başlatması bekleniyor (ilk açılış optimizasyonu)...")
                        time.sleep(3.0)  # 3 saniye - Unity'nin splash screen ve ilk scene render için
                        
                        # Unity penceresini bulup maximize butonunu aktif et
                        if sys.platform == 'win32':
                            for delay in [1000, 3000, 5000, 7000]:  # 1s, 3s, 5s, 7s sonra dene (daha erken başlat)
                                QTimer.singleShot(delay, lambda pid=process.pid: self._enable_maximize_button(pid))
                        # Başarı mesajı göster
                        if hasattr(self, 'notification_panel'):
                            self.notification_panel.add_notification(
                                "PEMF Digital Twin başlatıldı", 
                                "success"
                            )
                    except Exception as e:
                        self.logger.error(f"subprocess.Popen hatası: {e}", exc_info=True)
                        self.digital_twin_opening = False  # Hata durumunda flag'i temizle
                        # Fallback: os.startfile kullan (parametreler olmadan)
                        try:
                            os.startfile(str(exe_path))
                            self.logger.info(f"PEMF Digital Twin os.startfile ile başlatıldı: {exe_path}")
                            self.digital_twin_opening = False  # Açılış tamamlandı
                            if hasattr(self, 'notification_panel'):
                                self.notification_panel.add_notification(
                                    "PEMF Digital Twin başlatıldı", 
                                    "success"
                                )
                        except Exception as e2:
                            self.logger.error(f"os.startfile hatası: {e2}", exc_info=True)
                            self.digital_twin_opening = False  # Hata durumunda flag'i temizle
                            error_msg = (
                                f"PEMF Digital Twin başlatılamadı:\n\n"
                                f"Hata: {str(e2)}\n\n"
                                f"Konum: {exe_path}\n"
                                f"Çalışma dizini: {pemf_temp_dir_str}"
                            )
                            QMessageBox.warning(self, "Hata", error_msg)
                else:
                    # Dosya bulunamadı - hata mesajı göster
                    self.digital_twin_opening = False  # Hata durumunda flag'i temizle
                    error_msg = (
                        f"PEMF Digital Twin uygulaması bulunamadı.\n\n"
                        f"Aranan konum: {exe_path}\n"
                        f"Kaynak konum: {build_pemf_path}\n\n"
                        f"Lütfen buildPEMF klasörünün doğru konumda olduğundan emin olun."
                    )
                    self.logger.error(error_msg)
                    QMessageBox.warning(self, "Hata", error_msg)
            
            # Signal bağlantıları
            copy_thread.progress_updated.connect(on_progress_updated)
            copy_thread.error_occurred.connect(on_error_occurred)
            copy_thread.copy_completed.connect(on_copy_completed)
            
            # Thread'i başlat
            copy_thread.start()
            
            # Progress dialog'u göster ve thread bitene kadar bekle
            # Dialog iptal edilirse thread'i durdur
            def on_cancel():
                if copy_thread.isRunning():
                    copy_thread.terminate()
                    copy_thread.wait(1000)
                copy_thread.deleteLater()
                progress_dialog.close()
            
            progress_dialog.canceled.connect(on_cancel)
                    
        except Exception as e:
            self.logger.error(f"Digital Twin açılırken hata: {e}", exc_info=True)
            self.digital_twin_opening = False  # Hata durumunda flag'i temizle
            QMessageBox.warning(self, "Hata", f"PEMF Digital Twin açılamadı:\n{e}")

    def _enable_maximize_button(self, process_id):
        """Unity penceresini bulup maximize butonunu aktif et"""
        try:
            if sys.platform != 'win32':
                return
            
            # Windows API sabitleri
            GWL_STYLE = -16
            WS_MAXIMIZEBOX = 0x00010000
            WS_MINIMIZEBOX = 0x00020000
            WS_SYSMENU = 0x00080000
            
            # EnumWindows callback fonksiyonu
            def enum_windows_callback(hwnd, lParam):
                try:
                    # Process ID'yi kontrol et
                    process_ids = ctypes.c_ulong()
                    ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_ids))
                    if process_ids.value != process_id:
                        return True
                    
                    # Pencere başlığını kontrol et (Unity pencereleri genellikle "Unity" içerir)
                    window_text = ctypes.create_unicode_buffer(512)
                    ctypes.windll.user32.GetWindowTextW(hwnd, window_text, 512)
                    window_title = window_text.value
                    
                    # PEMF veya Unity içeren pencereyi bul (boş olmayan pencere başlıkları)
                    if window_title and ("PEMF" in window_title or "Unity" in window_title):
                        # Mevcut pencere stilini al
                        current_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_STYLE)
                        
                        # Maximize butonunu ekle
                        new_style = current_style | WS_MAXIMIZEBOX | WS_MINIMIZEBOX | WS_SYSMENU
                        ctypes.windll.user32.SetWindowLongW(hwnd, GWL_STYLE, new_style)
                        
                        # Pencereyi yeniden çiz
                        ctypes.windll.user32.SetWindowPos(
                            hwnd, 0, 0, 0, 0, 0,
                            0x0001 | 0x0002 | 0x0004  # SWP_NOMOVE | SWP_NOSIZE | SWP_FRAMECHANGED
                        )
                        
                        self.logger.info(f"Maximize butonu aktif edildi: {window_title} (HWND: {hwnd})")
                        return False  # Pencere bulundu, aramayı durdur
                    
                except Exception as e:
                    self.logger.debug(f"EnumWindows callback hatası: {e}")
                
                return True  # Devam et
            
            # EnumWindows callback tipi (HWND, LPARAM)
            WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
            callback = WNDENUMPROC(enum_windows_callback)
            
            # Tüm pencereleri listele
            ctypes.windll.user32.EnumWindows(callback, 0)
            
        except Exception as e:
            self.logger.error(f"Maximize butonu aktif edilirken hata: {e}", exc_info=True)
    
    def _bring_digital_twin_to_front(self, process_id):
        """Digital Twin penceresini öne getirir"""
        try:
            if sys.platform != 'win32':
                return
            
            # EnumWindows callback fonksiyonu
            def enum_windows_callback(hwnd, lParam):
                try:
                    # Process ID'yi kontrol et
                    process_ids = ctypes.c_ulong()
                    ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_ids))
                    if process_ids.value != process_id:
                        return True
                    
                    # Pencere başlığını kontrol et
                    window_text = ctypes.create_unicode_buffer(512)
                    ctypes.windll.user32.GetWindowTextW(hwnd, window_text, 512)
                    window_title = window_text.value
                    
                    # PEMF veya Unity içeren pencereyi bul
                    if window_title and ("PEMF" in window_title or "Unity" in window_title):
                        # Pencereyi öne getir ve aktif et
                        ctypes.windll.user32.SetForegroundWindow(hwnd)
                        ctypes.windll.user32.ShowWindow(hwnd, 9)  # SW_RESTORE = 9
                        ctypes.windll.user32.BringWindowToTop(hwnd)
                        self.logger.info(f"Digital Twin penceresi öne getirildi: {window_title}")
                        return False  # Pencere bulundu, aramayı durdur
                    
                except Exception as e:
                    self.logger.debug(f"EnumWindows callback hatası: {e}")
                
                return True  # Devam et
            
            # EnumWindows callback tipi
            WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
            callback = WNDENUMPROC(enum_windows_callback)
            
            # Tüm pencereleri listele
            ctypes.windll.user32.EnumWindows(callback, 0)
            
        except Exception as e:
            self.logger.error(f"Digital Twin öne getirme hatası: {e}", exc_info=True)

    def open_kpi_dashboard(self):
        import sys
        if getattr(sys, 'frozen', False):
            # Frozen exe - use absolute import
            from windows.kpi_dashboard_window import KPIDashboardWindow
        else:
            # Development - try both paths
            try:
                from windows.kpi_dashboard_window import KPIDashboardWindow
            except (ImportError, ModuleNotFoundError):
                from kpi_dashboard_window import KPIDashboardWindow
        if not hasattr(self, 'kpi_dashboard_window') or not self.kpi_dashboard_window.isVisible():
            self.kpi_dashboard_window = KPIDashboardWindow(main_window=self)
            self.kpi_dashboard_window.show()
        else:
            self.kpi_dashboard_window.activateWindow()
            self.kpi_dashboard_window.raise_()



    def open_unified_control(self):
        """Yeni birleşik kontrol penceresini açar (Signal Generator + Autonomous Mode)"""
        import sys
        if getattr(sys, 'frozen', False):
            # Frozen exe - use absolute import
            from windows.unified_control_window import UnifiedControlWindow
        else:
            # Development - try both paths
            try:
                from windows.unified_control_window import UnifiedControlWindow
            except (ImportError, ModuleNotFoundError):
                from unified_control_window import UnifiedControlWindow
        if not hasattr(self, 'unified_control_window') or not self.unified_control_window.isVisible():
            self.unified_control_window = UnifiedControlWindow(main_window=self)
            # Patient saved sinyalini bağla
            self.patient_saved.connect(self.unified_control_window._load_patient_list)
            self.unified_control_window.show()
        else:
            self.unified_control_window.activateWindow()
            self.unified_control_window.raise_()
        
        # Hasta bilgilerini güncelle
        if hasattr(self, 'unified_control_window') and self.unified_control_window:
            self.unified_control_window.update_patient_info()

    def open_treatment_history(self):
        import sys
        if getattr(sys, 'frozen', False):
            # Frozen exe - use absolute import
            from windows.treatment_history_window import TreatmentHistoryWindow
        else:
            # Development - try both paths
            try:
                from windows.treatment_history_window import TreatmentHistoryWindow
            except (ImportError, ModuleNotFoundError):
                from treatment_history_window import TreatmentHistoryWindow
        if not hasattr(self, 'treatment_history_window') or not self.treatment_history_window.isVisible():
            self.treatment_history_window = TreatmentHistoryWindow(main_window=self)
            self.treatment_history_window.show()
        else:
            self.treatment_history_window.activateWindow()
            self.treatment_history_window.raise_()

    def toggle_silent_mode(self):
        """Sessiz modu aç/kapat"""
        self.silent_mode = not self.silent_mode
        
        if self.silent_mode:
            # Sessiz mod açık
            self.silent_mode_btn.setText("🔇")
            self.silent_mode_btn.setStyleSheet("""
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #ff6b6b, stop:1 #ff8e8e);
                color: white;
                border: none;
                border-radius: 8px;
                font-size: 16px;
                font-weight: bold;
                padding: 8px 12px;
                margin-left: 16px;
                min-width: 40px;
            """)
            self.silent_mode_btn.setToolTip("Sessiz Mod Açık (Bildirimleri Aç)")
            self.logger.info("Sessiz mod açıldı")
            # Sessiz mod açıldığına dair bildirim (bu gösterilecek çünkü henüz sessiz mod aktif değildi)
            if hasattr(self, 'notification_panel'):
                self.notification_panel.add_notification("Sessiz mod açıldı - Sadece kritik hatalar gösterilecek", "info")
        else:
            # Sessiz mod kapalı
            self.silent_mode_btn.setText("🔊")
            self.silent_mode_btn.setStyleSheet("""
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #4a90e2, stop:1 #7bb3f0);
                color: white;
                border: none;
                border-radius: 8px;
                font-size: 16px;
                font-weight: bold;
                padding: 8px 12px;
                margin-left: 16px;
                min-width: 40px;
            """)
            self.silent_mode_btn.setToolTip("Sessiz Mod (Bildirimleri Kapat/Aç)")
            self.logger.info("Sessiz mod kapatıldı")
            if hasattr(self, 'notification_panel'):
                self.notification_panel.add_notification("Sessiz mod kapatıldı - Tüm bildirimler gösterilecek", "success")
    
    def open_user_manual(self):
        """Generate and open user manual PDF"""
        try:
            import sys
            from pathlib import Path
            import os
            
            # Add parent directory to path - handle both dev and frozen exe
            if getattr(sys, 'frozen', False):
                # Frozen exe - use _MEIPASS for bundled resources
                if hasattr(sys, '_MEIPASS'):
                    parent_dir = Path(sys._MEIPASS)
                else:
                    parent_dir = Path(sys.executable).parent
            else:
                # Development mode
                parent_dir = Path(__file__).parent.parent
            
            if str(parent_dir) not in sys.path:
                sys.path.insert(0, str(parent_dir))
            
            # scripts klasörünü de ekle
            scripts_dir = parent_dir / 'scripts'
            if str(scripts_dir) not in sys.path:
                sys.path.insert(0, str(scripts_dir))
            
            # Import and generate (try both import methods)
            try:
                from scripts.generate_user_manual import generate_manual
            except (ImportError, ModuleNotFoundError):
                from generate_user_manual import generate_manual
            
            # Generate the PDF and get its path
            pdf_path = generate_manual()
            
            if pdf_path and Path(pdf_path).exists():
                # Open PDF with default viewer (Windows)
                os.startfile(str(pdf_path))
                self.logger.info(f"Kullanım kılavuzu açıldı: {pdf_path}")
                if hasattr(self, 'notification_panel'):
                    self.notification_panel.add_notification("Kullanım kılavuzu açıldı", "success")
            else:
                raise FileNotFoundError("PDF dosyası oluşturulamadı")
                
        except Exception as e:
            self.logger.error(f"Kullanım kılavuzu açılamadı: {e}", exc_info=True)
            QMessageBox.warning(
                self, 
                "Hata", 
                f"Kullanım kılavuzu açılamadı:\n{str(e)}"
            )

    def handle_coil_control_request(self, coil_num, command):
        """
        Thread-safe slot for coil_control_requested signal.
        Called from GUI thread when UnifiedControlWindow requests coil control.
        This ensures only MainWindow writes to MQTT, preventing conflicts.
        
        Args:
            coil_num (int): Coil number (1-8)
            command (dict): MQTT command with 'command', 'command_id', 'freq', 'duty', 'duration', 'timestamp' keys
        """
        try:
            if not hasattr(self, 'mqtt_client') or not self.mqtt_client or not self.mqtt_connected_state:
                print(f"[MainWindow] WARNING: MQTT client not available, cannot send coil {coil_num} command")
                self.logger.warning(f"MQTT client not available, cannot send coil {coil_num} command")
                return
            
            # If UnifiedControlWindow is open, add command to its pending_commands
            if hasattr(self, 'unified_control_window') and self.unified_control_window and self.unified_control_window.isVisible():
                try:
                    self.unified_control_window.add_pending_command(coil_num, command)
                except Exception as e:
                    self.logger.warning(f"Failed to add pending command to UnifiedControlWindow: {e}")
            
            # Send MQTT command (MainWindow is the only one that writes to MQTT)
            topic = f"pemf/coil/{coil_num}/control"
            command_json = json.dumps(command)
            
            result = self.mqtt_client.publish(topic, command_json, qos=1)
            
            if result.rc != 0:
                print(f"[MainWindow] ✗ Failed to send coil {coil_num} command '{command.get('command', 'unknown')}' to topic {topic}: MQTT publish failed (rc={result.rc})")
                self.logger.error(f"✗ Failed to send coil {coil_num} command '{command.get('command', 'unknown')}' to topic {topic}: MQTT publish failed (rc={result.rc})")
                
        except Exception as e:
            print(f"[MainWindow] ERROR: Error handling coil control request: {e}")
            import traceback
            print(f"[MainWindow] Traceback: {traceback.format_exc()}")
            self.logger.error(f"Error handling coil control request: {e}", exc_info=True)
    
    def update_treatment_parameters(self, params):
        """Update the main window with new treatment parameters"""
        # Store the parameters
        self.current_treatment = params

        try:
            # Extract raw values for state variables (thread-safe)
            frequency = float(params.get('frequency', 0))
            intensity = float(params.get('intensity', 0))
            duration = int(params.get('duration', 0))
            
            # Update thread-safe state variables FIRST (before GUI updates)
            self.current_frequency = frequency
            self.current_intensity = intensity
            self.current_duration = duration
            
            # Format the parameters for display
            formatted_freq = f"{frequency:.1f} Hz"
            formatted_intensity = f"{int(round(intensity))} mT"

            # Update session manager with new parameters if session is active
            if hasattr(self, 'session_manager') and self.session_manager.is_session_active():
                target = params.get('target', 'Genel Rahatlama')
                
                # Update parameters in session manager (using already extracted variables)
                if frequency > 0:
                    self.session_manager.add_parameter('frequency', frequency, 'Hz')
                if intensity > 0:
                    self.session_manager.add_parameter('intensity', intensity, 'mT')
                if duration > 0:
                    self.session_manager.add_parameter('duration', duration, 'minutes')
                
                self.session_manager.add_parameter('target_condition', target)
                
                self.logger.info(f"Dinamik parametreler güncellendi: Freq={frequency}Hz, Int={intensity}mT, Dur={duration}dk")

            # Update the treatment card UI elements
            if hasattr(self, 'treatment_type_value'):
                self.treatment_type_value.setText(params.get('target', 'Seçili Değil'))
            if hasattr(self, 'freq_value'):
                self.freq_value.setText(formatted_freq)
            if hasattr(self, 'intensity_value'):
                self.intensity_value.setText(formatted_intensity)
            if hasattr(self, 'st_time_value'):
                self.st_time_value.setText(f"0/{duration} dk")
            if hasattr(self, 'st_status'):
                self.st_status.setText(
                    "<span style='color:#22c55e; font-size: 16px; font-weight: bold;'>Çalışıyor</span>")
                self.st_status.setStyleSheet(
                    "background: #d1fae5; border-radius: 6px; padding: 4px 16px; margin-top: 6px; font-size: 16px;")

            # Make sure the treatment card is visible
            if hasattr(self, 'smart_treatment_card'):
                self.smart_treatment_card.show()

            # Set treatment duration and start treatment
            self.treatment_duration_minutes = duration
            if hasattr(self, 'st_progress'):
                self.st_progress.setValue(0)  # Reset progress bar
            
            # Start treatment automatically only if no session is already active
            if not (hasattr(self, 'session_manager') and self.session_manager.is_session_active()):
                self.start_treatment()
            else:
                # If session is already active, just start the treatment timer
                self.is_treatment_active = True
                self.treatment_active = True  # Thread-safe state variable
                self.treatment_start_time = time.time()
                self.treatment_elapsed_seconds = 0
                # Timer artık unified_1hz_timer ile yapılıyor (Timer Optimization)
                self.logger.info(f"Mevcut seans devam ediyor: {self.treatment_duration_minutes} dakika")

            self.logger.info(f"Treatment parameters updated: {params}")

            # Update status bar
            if hasattr(self, 'statusBar'):
                self.statusBar().showMessage(
                    f"Seans parametreleri güncellendi - {params.get('target', 'Bilinmeyen')} ({params.get('profile', 'VarsayÄ±lan')})",
                    5000
                )

        except Exception as e:
            self.logger.error(f"Error updating treatment parameters: {e}", exc_info=True)
            if hasattr(self, 'statusBar'):
                self.statusBar().showMessage(f"Hata: Seans parametreleri güncellenirken bir hata oluştu: {str(e)}",
                                             5000)


    def increment_working_time(self):
        self.working_seconds += 1
        try:
            with open(self.working_time_file, 'w') as f:
                f.write(str(self.working_seconds))
        except Exception:
            pass
        self.update_working_time_label()

    def update_working_time_label(self):
        s = self.working_seconds
        hours = s // 3600
        minutes = (s % 3600) // 60
        seconds = s % 60
        self.working_time_label.setText(f"{hours}:{minutes}:{seconds}")

    def update_total_treatment_count(self):
        """Seans geçmişinden toplam seans sayısını güncelle"""
        try:
            db = get_treatment_db(self.app_data_dir)
            stats = db.get_statistics()
            total_sessions = stats.get('total_sessions', 0)
            self.total_treatment_label.setText(f"{total_sessions} seans")
            self.logger.info(f"Toplam seans sayısı güncellendi: {total_sessions}")
        except Exception as e:
            self.logger.error(f"Toplam seans sayısı güncellenirken hata oluştu: {e}")
            self.total_treatment_label.setText("0 seans")

    def update_treatment_progress(self):
        """Seans ilerlemesini güncelle"""
        if not self.is_treatment_active:
            return
            
        self.treatment_elapsed_seconds += 1
        elapsed_minutes = self.treatment_elapsed_seconds // 60
        
        # Süre labelını güncelle
        if hasattr(self, 'st_time_value'):
            self.st_time_value.setText(f"{elapsed_minutes}/{self.treatment_duration_minutes} dk")
        
        # Progress bar'ı güncelle
        if hasattr(self, 'st_progress') and self.treatment_duration_minutes > 0:
            progress_percentage = min(100, (elapsed_minutes / self.treatment_duration_minutes) * 100)
            self.st_progress.setValue(int(progress_percentage))
        
        # Seans tamamlandıysa durdur
        if elapsed_minutes >= self.treatment_duration_minutes:
            self.stop_treatment()

    def start_treatment(self, create_session=True):
        """Seans başlat (create_session=False ise unified_control session yönetir)"""
        if self.treatment_duration_minutes > 0:
            # Session kaydı SADECE unified_control tarafından yapılır
            # Main window artık session yaratmıyor - sadece UI güncellemesi
            if create_session:
                # Manuel mod veya diğer modlar için INFO seviyesinde log
                self.logger.info(
                    "start_treatment called with create_session=True. "
                    "Session management is handled by unified_control_window for automatic/AI modes. "
                    "Manual mode sessions are not recorded."
                )
            else:
                self.logger.info("start_treatment: unified_control manages session")
            
            self.is_treatment_active = True
            self.treatment_active = True  # Thread-safe state variable
            self.treatment_start_time = time.time()
            self.treatment_elapsed_seconds = 0
            # Timer artık unified_1hz_timer ile yapılıyor (Timer Optimization)
            self.logger.info(f"Tedavi başlatıldı: {self.treatment_duration_minutes} dakika")
            
            # Seans durumunu buluta gönder (Event-Based)
            self.broadcast_session_status()

    def stop_treatment(self, from_unified_control=False):
        """Seans durdur"""
        self.is_treatment_active = False
        self.treatment_active = False  # Thread-safe state variable
        # Timer artık unified_1hz_timer ile yapılıyor, stop gerekmez (Timer Optimization)
        
        # DEPRECATED: Eski session_manager.end_session kullanımı kaldırıldı
        # Unified control window kendi SessionState ile yönetiyor ve stop_treatment()'ta DB'ye kaydediyor
        # Main window artık session sonlandırmıyor - sadece UI güncellemesi
        if self.current_session_id and not from_unified_control:
            self.logger.warning(
                f"stop_treatment: current_session_id={self.current_session_id} found, "
                "but session management is now handled by unified_control_window. "
                "This session was created by old system and will not be closed."
            )
            self.current_session_id = None
        
        if hasattr(self, 'st_status'):
            self.st_status.setText(
                "<span style='color:#ef4444; font-size: 16px; font-weight: bold;'>Durduruldu</span>")
            self.st_status.setStyleSheet(
                "background: #fecaca; border-radius: 6px; padding: 4px 16px; margin-top: 6px; font-size: 16px;")
        
        # Seans tamamlandıysa gözlem notları dialog'unu aç (sadece ana pencereden çağrıldığında)
        # DEPRECATED: Observation notes dialog kaldırıldı - unified_control halledecek
        # if hasattr(self, 'treatment_start_time') and self.treatment_start_time and not from_unified_control:
        #     self.show_observation_notes_dialog()
        self.logger.info("Seans durduruldu")
        
        # Seans durumunu buluta gönder (Event-Based)
        self.broadcast_session_status()
    
    def show_portal_dialog(self, coil_id, message):
        """
        Shows a user-friendly dialog when an ESP opens a WiFi portal.
        Kullanıcıya bobin WiFi bağlantısı için adım adım yönlendirme gösterir.
        """
        dialog = QMessageBox(self)
        dialog.setWindowTitle("📡 Bobin WiFi Bağlantısı Gerekli")
        
        # Ana başlık - büyük ve dikkat çekici
        dialog.setText(f"<h2 style='color: #f59e0b;'>🔌 Bobin {coil_id} WiFi'ye Bağlanmayı Bekliyor</h2>")
        
        # Detaylı talimatlar - adım adım
        detailed_message = f"""
<div style='font-size: 14px; line-height: 1.6;'>
    <p><b>Bobin {coil_id} WiFi ağına bağlanamadı ve portal moduna geçti.</b></p>
    
    <p style='margin-top: 12px;'><b>📱 Android App Kullanarak Bağlama:</b></p>
    <ol style='margin-left: 20px;'>
        <li>Android uygulamasını açın</li>
        <li>"Bobin Ayarları" veya "WiFi Yapılandırma" sekmesine gidin</li>
        <li>Bobin {coil_id}'i seçin ve WiFi bilgilerinizi girin</li>
        <li>Bağlantı tamamlanana kadar bekleyin</li>
    </ol>
    
    <p style='margin-top: 12px; color: #6b7280;'><i>💡 Not: Bobin otomatik olarak WiFi ağını arayacaktır. 
    Bağlantı başarılı olduğunda bu bildirim kaybolacaktır.</i></p>
</div>
        """
        
        dialog.setInformativeText(detailed_message)
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setStandardButtons(QMessageBox.StandardButton.Ok)
        
        # Dialog stilini özelleştir
        dialog.setStyleSheet("""
            QMessageBox {
                background-color: #1e1e2e;
            }
            QMessageBox QLabel {
                color: #ffffff;
                min-width: 400px;
            }
            QMessageBox QPushButton {
                background-color: #3b82f6;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 24px;
                font-size: 14px;
                font-weight: bold;
                min-width: 100px;
            }
            QMessageBox QPushButton:hover {
                background-color: #2563eb;
            }
        """)
        
        dialog.exec()

    def broadcast_session_status(self):
        """Seans durumunu MQTT'ye gönder (Event-Based - sadece Start/Stop anlarında)"""
        # MQTT client kontrolü
        if not hasattr(self, 'mqtt_client') or not self.mqtt_client:
            self.logger.warning("broadcast_session_status: MQTT client yok")
            return
        
        # MQTT bağlantı durumu kontrolü
        if not hasattr(self, 'mqtt_connected_state') or not self.mqtt_connected_state:
            self.logger.warning("broadcast_session_status: MQTT bağlı değil")
            return
        
        # MQTT client'ın gerçekten bağlı olup olmadığını kontrol et
        try:
            if not self.mqtt_client.is_connected():
                self.logger.warning("broadcast_session_status: MQTT client bağlı değil (is_connected() = False)")
                return
        except Exception as e:
            self.logger.warning(f"broadcast_session_status: MQTT bağlantı kontrolü hatası: {e}")
            return
        
        # Şu anki zaman (Milisaniye cinsinden)
        current_timestamp_ms = int(time.time() * 1000)
        
        if self.is_treatment_active:
            # Hasta ve Mod bilgilerini al
            patient_name = "Bilinmiyor"
            if hasattr(self, 'last_saved_patient') and self.last_saved_patient:
                patient_info = self.last_saved_patient.get('info', {})
                patient_name = patient_info.get('name', 'Bilinmiyor')
            
            # Mod bilgisini current_treatment'tan al (AI Mod, Otonom Mod, Manuel Mod)
            mode = getattr(self, 'current_treatment', {}).get('mode', 'Manuel Mod')
            
            # E\u011fer mode bilgisi yoksa, unified_control_window'dan kontrol et
            if mode == 'Manuel Mod' and hasattr(self, 'unified_control_window') and self.unified_control_window.isVisible():
                if hasattr(self.unified_control_window, 'tab_widget'):
                    current_tab = self.unified_control_window.tab_widget.currentIndex()
                    if current_tab == 0:
                        mode = "Otonom Mod"
                    elif current_tab == 2:
                        mode = "AI Mod"
            
            # BAŞLANGIÇ ZAMANI ÇOK ÖNEMLİ
            # self.treatment_start_time saniye cinsindendir, ms'ye çeviriyoruz
            if not hasattr(self, 'treatment_start_time') or self.treatment_start_time is None:
                self.logger.warning("broadcast_session_status: treatment_start_time set edilmemiş, şu anki zaman kullanılıyor")
                start_time_ms = int(time.time() * 1000)
            else:
                start_time_ms = int(self.treatment_start_time * 1000)
            
            # Seans parametrelerini al
            frequency = getattr(self, 'current_treatment', {}).get('frequency', 0)
            intensity = getattr(self, 'current_treatment', {}).get('intensity', 0)
            target = getattr(self, 'current_treatment', {}).get('target', 'Bilinmiyor')
            
            # treatment_duration_minutes kontrolü
            if not hasattr(self, 'treatment_duration_minutes'):
                self.logger.warning("broadcast_session_status: treatment_duration_minutes set edilmemiş, 0 kullanılıyor")
                duration_minutes = 0
            else:
                duration_minutes = self.treatment_duration_minutes
            
            payload = {
                "active": True,
                "patient_name": patient_name,
                "mode": mode,
                "target": target,  # Yeni: Tedavi hedefi
                "start_timestamp": start_time_ms,  # KRİTİK: Seansın başladığı an (Unix Epoch ms)
                "duration_minutes": duration_minutes,
                "frequency": frequency,
                "intensity": intensity
            }
        else:
            payload = {
                "active": False,
                "start_timestamp": 0,
                "duration_minutes": 0
            }
        
        try:
            # Retain=True OLMALI! App sonradan açılırsa bu son mesajı alıp senkronize olacak.
            payload_json = json.dumps(payload)
            
            # Cihaz ID'sine özel topic kullan (uzaktan izleme için)
            if not self.device_id:
                self.device_id = get_unique_device_id()
            
            topic = f"pemf/{self.device_id}/session"
            result = self.mqtt_client.publish(topic, payload_json, qos=1, retain=True)
            
            if result.rc == 0:
                self.logger.info(f"Seans durumu buluta gönderildi -> {topic}. Payload: {payload_json}")
            else:
                self.logger.error(f"Seans durumu gönderilemedi. MQTT rc: {result.rc}")
        except Exception as e:
            self.logger.error(f"Seans durumu yayınlanırken hata: {e}", exc_info=True)
    
    def show_observation_notes_dialog(self):
        """Seans sonrası gözlem notları dialog'unu göster"""
        try:
            from windows.observation_notes_dialog import ObservationNotesDialog
            
            # Son kaydedilen hasta bilgilerini al
            patient_name = "Bilinmiyor"
            if hasattr(self, 'last_saved_patient') and self.last_saved_patient:
                patient_info = self.last_saved_patient.get('info', {})
                patient_name = patient_info.get('name', 'Bilinmiyor')
            
            # Seans modunu al
            treatment_mode = getattr(self, 'current_treatment', {}).get('mode', 'Manuel Mod')
            
            # E\u011fer mode bilgisi yoksa, unified_control_window'dan kontrol et
            if treatment_mode == 'Manuel Mod' and hasattr(self, 'unified_control_window') and self.unified_control_window.isVisible():
                if hasattr(self.unified_control_window, 'tab_widget'):
                    current_tab = self.unified_control_window.tab_widget.currentIndex()
                    if current_tab == 0:
                        treatment_mode = "Otonom Mod"
                    elif current_tab == 2:
                        treatment_mode = "AI Mod"
            
            # Dialog'u aç
            dialog = ObservationNotesDialog(
                parent=self,
                session_id=getattr(self, 'current_session_id', None),
                patient_name=patient_name,
                treatment_mode=treatment_mode
            )
            
            dialog.exec()
            
        except Exception as e:
            self.logger.error(f"Gözlem notları dialog hatası: {e}", exc_info=True)
            QMessageBox.information(
                self,
                "Bilgi",
                "Gözlem notları özelliği şu anda kullanılamıyor.",
                QMessageBox.StandardButton.Ok
            )
    
    def show_metrics_summary(self):
        """Performans metriklerini göster"""
        try:
            summary = self.metrics.get_summary()
            self.logger.info("\n" + summary)
            
            # Dialog ile de göster
            QMessageBox.information(
                self,
                "📊 Performans Metrikleri",
                summary,
                QMessageBox.StandardButton.Ok
            )
        except Exception as e:
            self.logger.error(f"Metrics summary hatası: {e}", exc_info=True)

    def update_kpi_effectiveness(self, value):
        if hasattr(self, 'kpi1_value'):
            self.kpi1_value.setText(
                f"<span style='color:#22c55e; font-size: 16px; font-weight: bold;'>{value:.1f}%</span>")

    def update_kpi_energy(self, value):
        """
        Enerji tüketimini güncelle (Wh cinsinden)
        KPI Dashboard'dan gerçek zamanlı enerji verisi alınır
        """
        if hasattr(self, 'kpi2_value'):
            # Wh veya kWh olarak göster
            if value < 1000:
                self.kpi2_value.setText(
                    f"<span style='color:#eab308; font-size: 16px; font-weight: bold;'>{value:.2f} Wh</span>")
            else:
                kwh_value = value / 1000.0
                self.kpi2_value.setText(
                    f"<span style='color:#eab308; font-size: 16px; font-weight: bold;'>{kwh_value:.3f} kWh</span>")

    def update_kpi_operation_rate(self, value):
        if hasattr(self, 'kpi3_value'):
            self.kpi3_value.setText(
                f"<span style='color:#2563eb; font-size: 16px; font-weight: bold;'>{value:.1f}%</span>")


    def _on_coil_button_toggled(self, checked, coil_id):
        """Bobin butonuna tıklandığında çağrılır (Thread-Safe)"""
        try:
            if checked:
                # Thread-safe active coils metod kullan (Thread Safety Fix)
                is_first_coil = self.add_active_coil(coil_id)
                
                self.mag_field_curves[coil_id].show()
                self.temp_curves[coil_id].show()
                
                # İlk bobin aktif olduğunda veri toplamayı başlat
                if is_first_coil:
                    self.graph_data_collection_active = True
                    self.graph_start_time = None  # İlk veri geldiğinde ayarlanacak (gecikme önleme)
                    
                    self.logger.info(f"[GRAPH INIT] Veri toplama başlatıldı - İlk bobin aktif: {coil_id}, graph_start_time=None")
                    
                    # Thread-safe graph data temizleme (Deque Memory Optimization)
                    self.graph_data_mutex.lock()
                    try:
                        # Yeni deque oluştur (memory optimization - clear() yerine)
                        self.graph_time_data = deque(maxlen=2000)
                        for c_id in range(1, 9):
                            self.graph_magnetic_field_data[c_id] = deque(maxlen=2000)
                            self.graph_temperature_data[c_id] = deque(maxlen=2000)
                    finally:
                        self.graph_data_mutex.unlock()
                    
                    self.logger.info(f"Veri toplama başlatıldı - İlk bobin aktif: {coil_id}")
                
                self.logger.info(f"Bobin {coil_id} aktif edildi")
            else:
                # Thread-safe active coils metod kullan (Thread Safety Fix)
                is_last_coil = self.remove_active_coil(coil_id)
                
                self.mag_field_curves[coil_id].hide()
                self.temp_curves[coil_id].hide()
                
                # Son bobin deaktif olduğunda veri toplamayı durdur
                if is_last_coil:
                    self.graph_data_collection_active = False
                    self.graph_start_time = None
                    
                    # Thread-safe graph data temizleme (Deque Memory Optimization)
                    self.graph_data_mutex.lock()
                    try:
                        # Yeni deque oluştur (memory optimization - clear() yerine)
                        self.graph_time_data = deque(maxlen=2000)
                        for c_id in range(1, 9):
                            self.graph_magnetic_field_data[c_id] = deque(maxlen=2000)
                            self.graph_temperature_data[c_id] = deque(maxlen=2000)
                    finally:
                        self.graph_data_mutex.unlock()
                    
                    self.logger.info("Tüm bobinler deaktif - Veri toplama durduruldu")
                
                self.logger.info(f"Bobin {coil_id} deaktif edildi")
                
        except Exception as e:
            self.logger.error(f"Bobin toggle hatası: {e}")

    def _validate_field(self, field_index: int, text: str):
        """
        Tek bir alanı validate et ve gerçek zamanlı geri bildirim ver.
        
        Args:
            field_index: Alan indexi (0=name, 1=species, 2=breed, 3=age, 4=weight, 5=owner, 6=vet_contact)
            text: Alan içeriği
        """
        if field_index >= len(self.validation_labels):
            return
            
        validation_label = self.validation_labels[field_index]
        
        # Boş alan - mesaj gösterme
        if not text.strip():
            validation_label.setVisible(False)
            return
        
        # Alana göre validasyon
        is_valid = False
        message = ""
        suggestion = None
        
        try:
            if field_index == 0:  # Hayvan adı
                is_valid, message, suggestion = self.validator.validate_name(text)
            elif field_index == 1:  # Tür
                is_valid, message, suggestion = self.validator.validate_species(text)
            elif field_index == 2:  # Irk
                species_text = self.input_fields[1].text() if len(self.input_fields) > 1 else ""
                is_valid, message, suggestion = self.validator.validate_breed(text, species_text)
            elif field_index == 3:  # Yaş
                is_valid, message, suggestion = self.validator.validate_age(text)
            elif field_index == 4:  # Ağırlık
                species_text = self.input_fields[1].text() if len(self.input_fields) > 1 else ""
                is_valid, message, suggestion = self.validator.validate_weight(text, species_text)
            elif field_index == 5:  # Sahip
                is_valid, message, suggestion = self.validator.validate_owner(text)
            else:  # Veteriner iletişim (opsiyonel)
                validation_label.setVisible(False)
                return
        except Exception as e:
            self.logger.error(f"Validasyon hatası: {e}")
            return
        
        # Mesaj göster
        if message:
            validation_label.setText(message)
            
            # Renk ayarla (hata/uyarı/başarı)
            if "❌" in message:
                color = "#ff5252"  # Kırmızı
            elif "⚠️" in message:
                color = "#ffa726"  # Turuncu
            elif "ℹ️" in message:
                color = "#64b5f6"  # Mavi
            else:  # ✅
                color = "#66bb6a"  # Yeşil
            
            validation_label.setStyleSheet(
                f"color: {color}; font-size: 11px; margin-left: 2px; margin-top: 2px;"
            )
            validation_label.setVisible(True)
        else:
            validation_label.setVisible(False)
    
    def save_patient(self):
        """
        Hasta bilgilerini veritabanına kaydeder.
        
        Kullanıcının girdiği hasta bilgilerini alır, doğrular ve 
        JSON veritabanına kaydeder. Başarılı kayıt sonrası kullanıcıya
        bilgi mesajı gösterir.
        """
        try:
            # Hasta bilgilerini input alanlarından al
            patient_info = {}
            field_names = [
                "name", "species", "breed", "age", 
                "weight", "owner", "vet_contact"
            ]
            
            # Boş alan kontrolü
            empty_fields = []
            for i, field_name in enumerate(field_names):
                value = self.input_fields[i].text().strip()
                if not value:
                    empty_fields.append(field_name)
                patient_info[field_name] = value
            
            # Zorunlu alanların kontrolü
            required_fields = ["name", "species", "owner"]
            missing_required = [field for field in required_fields if field in empty_fields]
            
            if missing_required:
                QMessageBox.warning(
                    self,
                    "Eksik Bilgi",
                    f"Lütfen şu zorunlu alanları doldurun:\n" + 
                    "\n".join([f"• {field.title()}" for field in missing_required])
                )
                return
            
            # Veritabanına kaydet (use instance variable instead of function call)
            patient_id = self.patient_db.add_patient(patient_info)
            
            # --- YENİ: MQTT İle Uzaktan Bildirim ---
            if hasattr(self, 'mqtt_client') and self.mqtt_client and hasattr(self, 'mqtt_connected_state') and self.mqtt_connected_state:
                try:
                    if not self.device_id:
                        self.device_id = get_unique_device_id()
                    
                    topic = f"pemf/{self.device_id}/new_patient"
                    payload = {
                        "event": "patient_registered",
                        "patient_id": patient_id[:8],  # Kısa versiyon (gizlilik)
                        "patient_name": patient_info['name'],
                        "species": patient_info['species'],
                        "owner": patient_info['owner'],
                        "timestamp": int(time.time() * 1000)
                    }
                    self.mqtt_client.publish(topic, json.dumps(payload), qos=1)
                    self.logger.info(f"Yeni hasta bilgisi MQTT ile gönderildi -> {topic}")
                except Exception as e:
                    self.logger.error(f"MQTT hasta bildirimi hatası: {e}")
            # ----------------------------------
            
            # Başarı mesajı
            QMessageBox.information(
                self,
                "Başarılı",
                f"Hasta başarıyla kaydedildi!\n\n"
                f"Hasta Adı: {patient_info['name']}\n"
                f"Tür: {patient_info['species']}\n"
                f"Sahibi: {patient_info['owner']}\n"
                f"Hasta ID: {patient_id[:8]}..."
            )
            
            # Input alanlarını temizle
            for field in self.input_fields:
                field.clear()
            
            # Kayıtlı hasta bilgisini sakla (dinamik mod için)
            self.last_saved_patient = {
                "id": patient_id,
                "info": patient_info
            }
            
            # Eğer Unified Control penceresi açıksa hasta bilgilerini güncelle
            if hasattr(self, 'unified_control_window') and self.unified_control_window and self.unified_control_window.isVisible():
                self.unified_control_window.update_patient_info()
            
            # Hasta kaydedildi sinyalini gönder (unified control window hasta listesini yenileyecek)
            self.patient_saved.emit()
            
            # Hasta kaydettikten sonra birleşik mod penceresini otomatik aç
            self.open_unified_control()
            
            self.logger.info(f"Hasta kaydedildi: {patient_info['name']} (ID: {patient_id})")
            
        except Exception as e:
            self.logger.error(f"Hasta kayıt hatası: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "Hata",
                f"Hasta kaydedilirken bir hata oluştu:\n{str(e)}"
            )

    def create_esp_status_panel(self, parent_layout):
        """
        ESP bağlantı durumu panelini oluşturur.
        """
        self.logger.debug("🔧 ESP bağlantı durumu paneli oluşturuluyor...")
        self.logger.info("ESP bağlantı durumu paneli oluşturuluyor")
        
        # Bobin Bağlantı Durumu başlığı
        esp_title = QLabel("📡 Bobin Bağlantı Durumu")
        esp_title.setStyleSheet("color: #6cffb0; font-size: 16px; font-weight: bold; margin: 10px 0;")
        parent_layout.addWidget(esp_title)
        self.logger.debug("ESP panel başlığı eklendi")
        
        # ESP durumları için container
        self.esp_container = QWidget()
        self.esp_container.setStyleSheet("""
            background: rgba(61, 32, 107, 0.3);
            border: 1px solid #6c2b8f;
            border-radius: 12px;
            padding: 12px;
            margin: 5px 0;
        """)
        
        self.esp_layout = QVBoxLayout(self.esp_container)
        self.esp_layout.setSpacing(8)
        
        # Başlangıçta "Bobin bulunamadı" mesajı
        self.no_esp_label = QLabel("🔍 Bobin cihazları aranıyor...")
        self.no_esp_label.setStyleSheet("color: #ffa500; font-size: 14px; text-align: center; padding: 20px;")
        self.esp_layout.addWidget(self.no_esp_label)
        
        parent_layout.addWidget(self.esp_container)
        self.logger.debug("🎉 ESP bağlantı durumu paneli başarıyla oluşturuldu!")
        self.logger.info("ESP bağlantı durumu paneli başarıyla oluşturuldu")

    def update_esp_status_internal(self, coil_id, status_data):
        """
        ESP durumunu günceller (internal method).
        esp_status_received sinyalinden QueuedConnection ile çağrılır (Thread-Safe).
        Buffer'ı birleştirir VE UI'ı günceller.
        
        Args:
            coil_id (str): ESP ID'si
            status_data (dict): ESP durum bilgileri (parçalı - /sensors veya /status)
        """
        try:
            # --- BİRLEŞTİRME MANTIĞI (Thread-Safe) ---
            # Thread-safe buffer erişimi
            self.esp_status_buffer_mutex.lock()
            try:
                # Mevcut durumu kalıcı buffer'dan al
                old_status = self.esp_status_buffer.get(coil_id, {}).copy()  # Deep copy to avoid race condition
                current_status = old_status.copy()
                
                # Yeni (parçalı) veriyi mevcut durum üzerine 'update' et (merge)
                current_status.update(status_data)
                
                # Performans optimizasyonu: Sadece durum değiştiğinde logla
                if self.logger.isEnabledFor(logging.DEBUG) and old_status != current_status:
                    self.logger.debug("ESP %s status changed: %s", coil_id, status_data)
                
                # Birleştirilmiş veriyi kalıcı buffer'a geri yaz (ASLA TEMİZLEME)
                self.esp_status_buffer[coil_id] = current_status
            finally:
                self.esp_status_buffer_mutex.unlock()
            # --- BİRLEŞTİRME MANTIĞI SONU ---
            
            # CRITICAL FIX: Widget oluşturma mantığı - sadece MQTT bağlıysa widget oluştur
            mqtt_connected = current_status.get('mqtt_connected', False)
            wifi_connected = current_status.get('wifi_connected', False)
            
            # Widget oluşturma koşulu: En az bir bağlantı bilgisi var
            should_create_widget = (mqtt_connected or wifi_connected or 
                                   'uptime' in current_status or 
                                   'sensors_ok' in current_status)
            
            if should_create_widget:
                # "ESP aranıyor" mesajını kaldır
                if self.no_esp_label and self.no_esp_label.parent():
                    self.logger.debug("🗑 'ESP aranıyor' mesajı kaldırılıyor...")
                    self.no_esp_label.setParent(None)
                    self.no_esp_label = None
                
                # ESP widget'ı yoksa oluştur
                if coil_id not in self.esp_widgets:
                    self.create_esp_widget(coil_id)
                
                # Widget'ı GÜNCELLENMİŞ (MERGED) VERİ ile güncelle
                self.update_esp_widget(coil_id, current_status)
            else:
                # Veri geldiyse ama bağlantı bilgisi yoksa logla (hata durumu)
                self.logger.debug(f"ESP {coil_id} veri gönderdi ama bağlantı bilgisi yok: {current_status}")
        
        except Exception as e:
            self.logger.error(f"update_esp_status_internal hatası: {e}", exc_info=True)
            


    def create_esp_widget(self, coil_id):
        """
        Belirli bir ESP için widget oluşturur.
        FIXED: Widget oluşturulduğunda ESP hiç görülmemiş olarak işaretle (last_seen None).
        """

        self.logger.info(f"create_esp_widget başlatıldı: {coil_id}")
        
        # CRITICAL FIX: Widget oluşturulduğunda ESP'yi last_seen'e ekle (hiç görülmedi)
        if not hasattr(self, 'esp_last_seen'):
            self.esp_last_seen = {}
        # None ile işaretle: Widget var ama ESP'den hiç mesaj gelmedi
        # check_esp_connections bu durumda timeout olarak algılayacak ve "Bağlı değil" gösterecek
        self.esp_last_seen[coil_id] = None
        
        esp_widget = QWidget()
        esp_widget.setStyleSheet("""
            background: rgba(45, 24, 90, 0.6);
            border: 1px solid #4a2c7a;
            border-radius: 8px;
            padding: 8px;
            margin: 2px;
        """)
        
        layout = QVBoxLayout(esp_widget)
        layout.setSpacing(6)
        
        # Bobin başlığı
        header_layout = QHBoxLayout()
        esp_title = QLabel(f"🔌 Bobin {coil_id}")
        esp_title.setStyleSheet("color: #fff; font-size: 14px; font-weight: bold;")
        
        # Bağlantı durumu göstergesi - FIXED: Başlangıçta GRİ (bilinmiyor)
        status_indicator = QLabel("●")
        status_indicator.setStyleSheet("color: #888888; font-size: 16px;")  # FIXED: Başlangıçta gri (bilinmiyor)
        
        header_layout.addWidget(esp_title)
        header_layout.addStretch()
        header_layout.addWidget(status_indicator)
        layout.addLayout(header_layout)
        
        # Durum bilgileri
        info_layout = QGridLayout()
        info_layout.setSpacing(4)
        
        # WiFi durumu
        wifi_label = QLabel("📶 WiFi:")
        wifi_label.setStyleSheet("color: #ccc; font-size: 12px;")
        wifi_status = QLabel("Bağlı değil")
        wifi_status.setStyleSheet("color: #ff4444; font-size: 12px;")
        info_layout.addWidget(wifi_label, 0, 0)
        info_layout.addWidget(wifi_status, 0, 1)
        
        # MQTT durumu
        mqtt_label = QLabel("📡 Bağlantı")
        mqtt_label.setStyleSheet("color: #ccc; font-size: 12px;")
        mqtt_status = QLabel("Bağlı değil")
        mqtt_status.setStyleSheet("color: #ff4444; font-size: 12px;")
        info_layout.addWidget(mqtt_label, 1, 0)
        info_layout.addWidget(mqtt_status, 1, 1)
        
        # Sensör durumu
        sensor_label = QLabel("🔬 Sensörler:")
        sensor_label.setStyleSheet("color: #ccc; font-size: 12px;")
        sensor_status = QLabel("Bilinmiyor")
        sensor_status.setStyleSheet("color: #ffa500; font-size: 12px;")
        info_layout.addWidget(sensor_label, 2, 0)
        info_layout.addWidget(sensor_status, 2, 1)
        
        # Uptime
        uptime_label = QLabel("⏱️ Çalışma:")
        uptime_label.setStyleSheet("color: #ccc; font-size: 12px;")
        uptime_status = QLabel("0s")
        uptime_status.setStyleSheet("color: #ccc; font-size: 12px;")
        info_layout.addWidget(uptime_label, 3, 0)
        info_layout.addWidget(uptime_status, 3, 1)
        
        # PWM durumu
        pwm_label = QLabel("⚡ Güç:")
        pwm_label.setStyleSheet("color: #ccc; font-size: 12px;")
        pwm_status = QLabel("Devre Dışı")
        pwm_status.setStyleSheet("color: #ff4444; font-size: 12px;")
        info_layout.addWidget(pwm_label, 4, 0)
        info_layout.addWidget(pwm_status, 4, 1)
        
        layout.addLayout(info_layout)
        
        # Sensör detayları (başlangıçta gizli)
        sensor_details = QWidget()
        sensor_details.setStyleSheet("""
            background: rgba(30, 20, 50, 0.5);
            border-radius: 6px;
            padding: 6px;
            margin-top: 4px;
        """)
        sensor_details_layout = QVBoxLayout(sensor_details)
        sensor_details_layout.setSpacing(3)
        
        # Sıcaklık Sensörü
        mlx90614_label = QLabel("🌡️ Sıcaklık Sensörü")
        mlx90614_label.setStyleSheet("color: #ccc; font-size: 11px;")
        sensor_details_layout.addWidget(mlx90614_label)
        
        # Manyetik Alan Sensörü
        mlx90393_label = QLabel("🧲 Manyetik Alan Sensörü")
        mlx90393_label.setStyleSheet("color: #ccc; font-size: 11px;")
        sensor_details_layout.addWidget(mlx90393_label)
        
        # Akım Sensörü
        acs712_label = QLabel("⚡ Akım Sensörü")
        acs712_label.setStyleSheet("color: #ccc; font-size: 11px;")
        sensor_details_layout.addWidget(acs712_label)
        
        layout.addWidget(sensor_details)
        
        # Widget referanslarını sakla
        self.esp_widgets[coil_id] = {
            'widget': esp_widget,
            'status_indicator': status_indicator,
            'wifi_status': wifi_status,
            'mqtt_status': mqtt_status,
            'sensor_status': sensor_status,
            'uptime_status': uptime_status,
            'pwm_status': pwm_status,
            'mlx90614_label': mlx90614_label,
            'mlx90393_label': mlx90393_label,
            'acs712_label': acs712_label,
            'sensor_details': sensor_details
        }
        
        self.esp_layout.addWidget(esp_widget)

        self.logger.info(f"ESP widget oluşturuldu ve layout'a eklendi: {coil_id}")

    def update_esp_widget(self, coil_id, status_data):
        """
        ESP widget'ını günceller.
        """
        if coil_id not in self.esp_widgets:
            return
        
        widgets = self.esp_widgets[coil_id]
        
        # Ana bağlantı durumu (WiFi ve MQTT)
        wifi_connected = status_data.get('wifi_connected', False)
        mqtt_connected = status_data.get('mqtt_connected', False)
        sensors_ok = status_data.get('sensors_ok', False)
        # Hem /status'tan gelen 'running' hem de /sensors'tan gelen 'pwm_active' kontrol edilir
        pwm_active = status_data.get('running', status_data.get('pwm_active', False))
        
        # Her sensör için ayrı durum (status mesajından veya sensor mesajından)
        temp_sensor_ok = status_data.get('temp_sensor_ok', False)
        magnetic_sensor_ok = status_data.get('magnetic_sensor_ok', False)
        current_sensor_ok = status_data.get('current_sensor_ok', True)
        
        # FIXED: Durum göstergesi rengi (WiFi, Portal, MQTT durumuna göre)
        portal_active = status_data.get('portal_active', False)
        # CRITICAL: Hiçbir veri yoksa GRİ göster (bilinmiyor durumu)
        has_any_data = ('uptime' in status_data or 'sensors_ok' in status_data or 
                       wifi_connected or mqtt_connected or portal_active)
        
        if not has_any_data:
            widgets['status_indicator'].setStyleSheet("color: #888888; font-size: 16px;")  # Gri - bilinmiyor
        elif wifi_connected and mqtt_connected:
            widgets['status_indicator'].setStyleSheet("color: #44ff44; font-size: 16px;")  # Yeşil - her şey OK
        elif portal_active:
            widgets['status_indicator'].setStyleSheet("color: #ffaa44; font-size: 16px;")  # Turuncu - portal açık
        elif wifi_connected:
            widgets['status_indicator'].setStyleSheet("color: #ffaa44; font-size: 16px;")  # Turuncu - WiFi var ama MQTT yok
        else:
            widgets['status_indicator'].setStyleSheet("color: #ff4444; font-size: 16px;")  # Kırmızı - WiFi yok
        
        # WiFi durumu (detaylı)
        portal_active = status_data.get('portal_active', False)
        if wifi_connected:
            wifi_ssid = status_data.get('wifi_ssid', '')
            wifi_ip = status_data.get('wifi_ip', '')
            # RSSI gösterimi kaldırıldı (event mesajından RSSI işlenmiyor)
            if wifi_ssid:
                wifi_text = f"{wifi_ssid}"
            else:
                wifi_text = "Bağlı"
            widgets['wifi_status'].setText(wifi_text)
            widgets['wifi_status'].setStyleSheet("color: #44ff44; font-size: 12px;")
        elif portal_active:
            # Portal açık - WiFi bağlantısı yok ama portal aktif
            portal_ssid = status_data.get('portal_ssid', 'PEMF-Coil-' + str(coil_id))
            portal_ip = status_data.get('portal_ip', '')
            if portal_ssid and portal_ip:
                widgets['wifi_status'].setText(f"🔧 Portal: {portal_ssid}")
                widgets['wifi_status'].setStyleSheet("color: #ffaa44; font-size: 12px;")  # Turuncu - portal açık
            else:
                widgets['wifi_status'].setText("🔧 Portal Açık")
                widgets['wifi_status'].setStyleSheet("color: #ffaa44; font-size: 12px;")
        else:
            widgets['wifi_status'].setText("Bağlı değil")
            widgets['wifi_status'].setStyleSheet("color: #ff4444; font-size: 12px;")
        
        # MQTT durumu
        if mqtt_connected:
            widgets['mqtt_status'].setText("Bağlı")
            widgets['mqtt_status'].setStyleSheet("color: #44ff44; font-size: 12px;")
        else:
            widgets['mqtt_status'].setText("Bağlı değil")
            widgets['mqtt_status'].setStyleSheet("color: #ff4444; font-size: 12px;")
        
        # Sensör durumu (genel)
        if sensors_ok:
            widgets['sensor_status'].setText("Çalışıyor")
            widgets['sensor_status'].setStyleSheet("color: #44ff44; font-size: 12px;")
        else:
            widgets['sensor_status'].setText("Hata")
            widgets['sensor_status'].setStyleSheet("color: #ff4444; font-size: 12px;")
        
        # Uptime
        uptime_ms = status_data.get('uptime', 0)
        uptime_seconds = uptime_ms // 1000
        if uptime_seconds < 60:
            uptime_text = f"{uptime_seconds}s"
        elif uptime_seconds < 3600:
            uptime_text = f"{uptime_seconds // 60}m {uptime_seconds % 60}s"
        else:
            hours = uptime_seconds // 3600
            minutes = (uptime_seconds % 3600) // 60
            uptime_text = f"{hours}h {minutes}m"
        
        widgets['uptime_status'].setText(uptime_text)
        
        # PWM durumu
        if pwm_active:
            widgets['pwm_status'].setText("Aktif")
            widgets['pwm_status'].setStyleSheet("color: #44ff44; font-size: 12px;")
        else:
            widgets['pwm_status'].setText("Devre Dışı")
            widgets['pwm_status'].setStyleSheet("color: #ff4444; font-size: 12px;")
        
        # Sensör detayları (her sensör için ayrı durum)
        # Sıcaklık Sensörü durumu
        if temp_sensor_ok:
            widgets['mlx90614_label'].setText("🌡️ Sıcaklık Sensörü")
            widgets['mlx90614_label'].setStyleSheet("color: #44ff44; font-size: 11px;")
        else:
            widgets['mlx90614_label'].setText("🌡️ Sıcaklık Sensörü")
            widgets['mlx90614_label'].setStyleSheet("color: #ff4444; font-size: 11px;")
        
        # Manyetik Alan Sensörü durumu
        if magnetic_sensor_ok:
            widgets['mlx90393_label'].setText("🧲 Manyetik Alan Sensörü")
            widgets['mlx90393_label'].setStyleSheet("color: #44ff44; font-size: 11px;")
        else:
            widgets['mlx90393_label'].setText("🧲 Manyetik Alan Sensörü")
            widgets['mlx90393_label'].setStyleSheet("color: #ff4444; font-size: 11px;")
        
        # Akım Sensörü durumu
        if current_sensor_ok:
            widgets['acs712_label'].setText("⚡ Akım Sensörü")
            widgets['acs712_label'].setStyleSheet("color: #44ff44; font-size: 11px;")
        else:
            widgets['acs712_label'].setText("⚡ Akım Sensörü")
            widgets['acs712_label'].setStyleSheet("color: #ff4444; font-size: 11px;")
        
        # CRITICAL FIX: Bobin kontrol paneli butonlarını bağlantı durumuna göre enable/disable et
        try:
            # coil_id string olabilir, int'e çevir
            coil_num = int(coil_id) if isinstance(coil_id, str) else coil_id
            if hasattr(self, 'coil_buttons') and 1 <= coil_num <= 8:
                button_index = coil_num - 1  # 0-indexed
                if button_index < len(self.coil_buttons):
                    button = self.coil_buttons[button_index]
                    
                    # MQTT bağlıysa butonu enable et, değilse disable et
                    if mqtt_connected:
                        button.setEnabled(True)
                        button.setToolTip(f"Bobin {coil_num} - Bağlı ve Hazır")
                    else:
                        button.setEnabled(False)
                        # CRITICAL FIX: Bağlantı koptuğunda buton checked ise işareti kaldır
                        if button.isChecked():
                            button.setChecked(False)
                            self.logger.debug(f"Bobin {coil_num} butonu işareti kaldırıldı (MQTT bağlantısı yok)")
                        if portal_active:
                            button.setToolTip(f"Bobin {coil_num} - Portal Açık (MQTT Bağlı Değil)")
                        elif wifi_connected:
                            button.setToolTip(f"Bobin {coil_num} - WiFi Bağlı ama MQTT Bağlı Değil")
                        else:
                            button.setToolTip(f"Bobin {coil_num} - Bağlı Değil")
        except Exception as e:
            self.logger.error(f"Bobin buton durumu güncellenirken hata: {e}")

    def _attempt_mqtt_reconnect(self):
        """
        MQTT reconnection denemesi (exponential backoff ile).
        GUI Stability Fix #1 + MQTT Cleanup + Network Error Handling
        """
        self.mqtt_mutex.lock()
        is_connected = self.mqtt_connected_state
        self.mqtt_mutex.unlock()
        
        if is_connected:
            # Zaten bağlı, timer'ı durdur
            self.mqtt_reconnect_timer.stop()
            return
        
        self.mqtt_retry_count += 1
        self.logger.info(f"MQTT reconnect denemesi #{self.mqtt_retry_count} (delay: {self.mqtt_retry_delay}ms)")
        
        try:
            # MQTT client var mı kontrol et
            if not hasattr(self, 'mqtt_client') or self.mqtt_client is None:
                self.logger.error("MQTT client bulunamadı, reconnect yapılamıyor")
                self.mqtt_reconnect_timer.stop()
                return
            
            # Eski client'ı temizle (MQTT Cleanup - reconnect'te cleanup)
            try:
                self.mqtt_client.loop_stop()
            except Exception:
                pass
            try:
                self.mqtt_client.disconnect()
            except Exception:
                pass
            
            # Reconnect dene
            self.mqtt_client.reconnect()
            
            # CRITICAL FIX: reconnect() sonrası loop_start() çağrısı gerekli!
            # Loop başlatılmazsa mesaj alımı gerçekleşmez
            self.mqtt_client.loop_start()
            self.logger.info("MQTT client loop yeniden başlatıldı")
            
            # Exponential backoff
            self.mqtt_retry_delay = min(self.mqtt_retry_delay * 2, self.max_mqtt_retry_delay)
            self.mqtt_reconnect_timer.setInterval(self.mqtt_retry_delay)
            
        except socket.gaierror as e:
            # DNS resolution hatası - ağ bağlantısı yok veya DNS çözümlenemiyor
            self.logger.error(f"MQTT reconnect DNS hatası (ağ bağlantısı yok): {e}")
            
            # DNS hatalarında daha uzun bekleme süresi kullan
            self.mqtt_retry_delay = min(self.mqtt_retry_delay * 3, self.max_mqtt_retry_delay)
            self.mqtt_reconnect_timer.setInterval(self.mqtt_retry_delay)
            
            # Kullanıcıya bildirim göster (sadece ilk DNS hatasında)
            if self.mqtt_retry_count == 1 and hasattr(self, 'notification_panel'):
                self.notification_panel.add_notification(
                    "MQTT bağlantısı kurulamıyor: İnternet bağlantısını kontrol edin",
                    "warning"
                )
            
            # Maksimum retry sayısına ulaşıldı mı?
            if self.mqtt_retry_count >= self.max_mqtt_retries:
                self.logger.error(f"MQTT reconnect {self.max_mqtt_retries} denemeden sonra başarısız oldu (DNS hatası)")
                self.mqtt_reconnect_timer.stop()
                
                # Eski client'ı temizle (MQTT Cleanup)
                self._cleanup_mqtt_client()
                
                # Notification panel'e bildir
                if hasattr(self, 'notification_panel'):
                    self.notification_panel.add_notification(
                        f"MQTT bağlantısı başarısız: İnternet bağlantınızı kontrol edin ve uygulamayı yeniden başlatın",
                        "error"
                    )
                    
        except (ConnectionRefusedError, OSError) as e:
            # Bağlantı reddedildi veya ağ hatası
            self.logger.error(f"MQTT reconnect bağlantı hatası: {e}")
            
            # Exponential backoff
            self.mqtt_retry_delay = min(self.mqtt_retry_delay * 2, self.max_mqtt_retry_delay)
            self.mqtt_reconnect_timer.setInterval(self.mqtt_retry_delay)
            
            # Maksimum retry sayısına ulaşıldı mı?
            if self.mqtt_retry_count >= self.max_mqtt_retries:
                self.logger.error(f"MQTT reconnect {self.max_mqtt_retries} denemeden sonra başarısız oldu")
                self.mqtt_reconnect_timer.stop()
                
                # Eski client'ı temizle (MQTT Cleanup)
                self._cleanup_mqtt_client()
                
                # Notification panel'e bildir
                if hasattr(self, 'notification_panel'):
                    self.notification_panel.add_notification(
                        f"MQTT bağlantısı {self.max_mqtt_retries} denemeden sonra başarısız oldu. Lütfen MQTT broker'ı kontrol edin.",
                        "error"
                    )
                
                # MQTT client'ı yeniden başlat
                try:
                    self.setup_mqtt_client()
                except Exception as setup_error:
                    self.logger.error(f"MQTT client yeniden başlatma hatası: {setup_error}")
                    
        except Exception as e:
            # Genel hatalar için mevcut mantığı koru
            self.logger.error(f"MQTT reconnect hatası: {e}", exc_info=True)
            
            # Maksimum retry sayısına ulaşıldı mı?
            if self.mqtt_retry_count >= self.max_mqtt_retries:
                self.logger.error(f"MQTT reconnect {self.max_mqtt_retries} denemeden sonra başarısız oldu")
                self.mqtt_reconnect_timer.stop()
                
                # Eski client'ı temizle (MQTT Cleanup)
                self._cleanup_mqtt_client()
                
                # Notification panel'e bildir
                if hasattr(self, 'notification_panel'):
                    self.notification_panel.add_notification(
                        f"MQTT bağlantısı {self.max_mqtt_retries} denemeden sonra başarısız oldu. Lütfen MQTT broker'ı kontrol edin.",
                        "error"
                    )
                
                # MQTT client'ı yeniden başlat
                try:
                    self.setup_mqtt_client()
                except Exception as setup_error:
                    self.logger.error(f"MQTT client yeniden başlatma hatası: {setup_error}")
    
    def get_last_saved_patient(self):
        """
        Son kaydedilen hasta bilgilerini döndürür.
        
        Returns:
            dict: Son kaydedilen hasta bilgileri veya None
        """
        return getattr(self, 'last_saved_patient', None)

    def _setup_responsive_window(self):
        """Setup responsive window sizing and positioning"""
        try:
            width, height, scale_factor, screen_type = get_screen_info()
            
            # Base dimensions for different screen types
            base_configs = {
                "mobile": {"width": 800, "height": 600, "min_width": 600, "min_height": 500},
                "tablet": {"width": 1024, "height": 768, "min_width": 800, "min_height": 600},
                "laptop": {"width": 1280, "height": 800, "min_width": 1024, "min_height": 700},
                "desktop": {"width": 1540, "height": 900, "min_width": 1280, "min_height": 800},
                "ultrawide": {"width": 1920, "height": 1080, "min_width": 1540, "min_height": 900}
            }
            
            config = base_configs.get(screen_type, base_configs["desktop"])
            
            # Scale dimensions based on actual screen size
            target_width = min(int(config["width"] * scale_factor), width * 0.95)
            target_height = min(int(config["height"] * scale_factor), height * 0.9)
            
            # Center window on screen
            x = (width - target_width) // 2
            y = (height - target_height) // 2
            
            # Set window properties
            self.setGeometry(int(x), int(y), int(target_width), int(target_height))
            self.setMinimumSize(config["min_width"], config["min_height"])
            
            # Enable responsive features
            self._enable_responsive_features()
            
        except Exception as e:
            # Fallback to default sizing
            self.setGeometry(100, 100, 1540, 900)
            self.setMinimumSize(1280, 800)

    def _enable_responsive_features(self):
        """Enable responsive features for the window"""
        try:
            # Connect resize event for dynamic adjustments
            self.resizeEvent = self._on_window_resize
            
            # Apply responsive layout to central widget
            if hasattr(self, 'centralWidget'):
                central_widget = self.centralWidget()
                if central_widget:
                    apply_responsive_layout(central_widget, base_margins=(0, 0, 0, 0), base_spacing=0)
                    
        except Exception as e:
            self.logger.debug(f"Responsive window resize hatası: {e}", exc_info=True)

    def _on_window_resize(self, event):
        """Handle window resize events for responsive adjustments"""
        try:
            super().resizeEvent(event)
            
            # Get new window size
            new_size = event.size()
            width = new_size.width()
            height = new_size.height()
            
            # Determine responsive breakpoints
            is_small = width < 1024
            is_medium = 1024 <= width < 1400
            is_large = width >= 1400
            
            # Apply responsive adjustments
            self._apply_responsive_adjustments(is_small, is_medium, is_large)
            
        except Exception as e:
            self.logger.debug(f"Responsive window resize hatası: {e}", exc_info=True)

    def _apply_responsive_adjustments(self, is_small, is_medium, is_large):
        """Apply responsive adjustments based on window size"""
        try:
            # Update font sizes for different breakpoints
            if is_small:
                self._apply_compact_styles()
            elif is_medium:
                self._apply_medium_styles()
            else:
                self._apply_large_styles()
                
        except Exception as e:
            self.logger.debug(f"Responsive window resize hatası: {e}", exc_info=True)

    def _apply_compact_styles(self):
        """Apply compact styles for small screens"""
        try:
            # Update font sizes for compact view
            if hasattr(self, 'clock'):
                scale_font(self.clock, 12)
            # Add more compact style adjustments as needed
        except Exception:
            pass

    def _apply_medium_styles(self):
        """Apply medium styles for medium screens"""
        try:
            # Update font sizes for medium view
            if hasattr(self, 'clock'):
                scale_font(self.clock, 15)
            # Add more medium style adjustments as needed
        except Exception:
            pass

    def _apply_large_styles(self):
        """Apply large styles for large screens"""
        try:
            # Update font sizes for large view
            if hasattr(self, 'clock'):
                scale_font(self.clock, 18)
            # Add more large style adjustments as needed
        except Exception:
            pass

    def check_esp_connections(self):
        """ESP bağlantılarını heartbeat'e göre kontrol et"""
        current_time = time.time()
        
        # MQTT bağlantısını kontrol et
        mqtt_connected = False
        if self.mqtt_client and self.mqtt_client.is_connected():
            mqtt_connected = True
        
        # MQTT bağlı değilse tüm ESP'leri bağlı değil olarak işaretle
        if not mqtt_connected:
            for coil_id in list(self.esp_widgets.keys()):
                # Sadece durumu zaten bağlıysa güncelle (gereksiz güncellemeyi önle)
                if self.esp_status.get(coil_id, {}).get('mqtt_connected', False):
                    self.logger.warning(f"MQTT bağlantısı yok - Coil {coil_id} bağlantı kesildi olarak işaretleniyor.")
                    
                    disconnected_status = {
                        'wifi_connected': False,
                        'mqtt_connected': False,
                        'sensors_ok': False,
                        'pwm_active': False
                    }
                    # UI'ı doğrudan güncelle (sinyal yerine)
                    self.update_esp_status_internal(coil_id, disconnected_status)
                    # esp_last_seen'i sıfırla
                    if hasattr(self, 'esp_last_seen'):
                        self.esp_last_seen.pop(coil_id, None)
            
            # CRITICAL FIX: MQTT bağlı değilse tüm butonları da disable et
            if hasattr(self, 'coil_buttons'):
                for i, button in enumerate(self.coil_buttons):
                    if button.isEnabled():
                        button.setEnabled(False)
                        button.setChecked(False)
                        button.setToolTip(f"Bobin {i + 1} - MQTT Bağlantısı Yok")
                        self.logger.debug(f"Bobin {i + 1} butonu disable edildi (MQTT bağlantısı yok)")
            
            return  # MQTT bağlı değilse heartbeat kontrolü yapma
        
        # ESP status buffer'dan snapshot al (Batch Processing - Thread Safety Fix)
        self.esp_status_buffer_mutex.lock()
        try:
            buffer_snapshot = dict(self.esp_status_buffer)
        finally:
            self.esp_status_buffer_mutex.unlock()
        
        # Bilinen tüm ESP widget'larını kontrol et (mutex dışında)
        for coil_id in list(self.esp_widgets.keys()):
            last_seen = self.esp_last_seen.get(coil_id)
            
            # FIXED: Eğer hiç görülmediyse (None) veya timeout olduysa
            # None durumu: Widget oluşturuldu ama ESP'den hiç mesaj gelmedi
            if last_seen is None:
                # Widget var ama ESP'den hiç mesaj gelmedi - "Bağlı değil" göster
                self.logger.debug(f"Coil {coil_id} widget'ı var ama hiç mesaj gelmedi. Bağlı değil olarak işaretleniyor.")
                
                disconnected_status = {
                    'wifi_connected': False,
                    'mqtt_connected': False,
                    'sensors_ok': False,
                    'pwm_active': False
                }
                # UI'ı güncelle (signal ile - QueuedConnection)
                self.esp_status_received.emit(coil_id, disconnected_status)
                
            elif (current_time - last_seen > self.ESP_TIMEOUT):
                # Snapshot'tan bağlantı durumunu kontrol et (mutex dışında - safe)
                is_connected = buffer_snapshot.get(coil_id, {}).get('mqtt_connected', False)
                
                # Sadece durumu zaten bağlıysa güncelle (gereksiz güncellemeyi önle)
                if is_connected:
                    self.logger.warning(f"Coil {coil_id} için heartbeat zaman aşımına uğradı. Bağlantı kesildi olarak işaretleniyor.")
                    
                    disconnected_status = {
                        'wifi_connected': False,
                        'mqtt_connected': False,
                        'sensors_ok': False,
                        'pwm_active': False
                    }
                    # UI'ı güncelle (signal ile - QueuedConnection)
                    self.esp_status_received.emit(coil_id, disconnected_status)
                    # esp_last_seen'i sıfırlama! Cleanup mekanizmasının çalışması için last_seen'e ihtiyacı var.
                    # self.esp_last_seen.pop(coil_id, None)  <-- BU SATIR KALDIRILMALI
    
    def _cleanup_stale_esp_devices(self):
        """
        ✅ Periyodik ESP cleanup: 5 saniyeden eski ESP'leri kaldır.
        Bu, retained MQTT messages'dan gelen eski ESP'lerin UI'da görünmesini önler.
        Android MqttService.kt ve unified_control_window.py ile aynı mantık.
        """
        try:
            current_time = time.time()
            stale_coils = []
            
            # Temizlenecek ESP'leri bul
            for coil_id in list(self.esp_widgets.keys()):
                last_seen = self.esp_last_seen.get(coil_id)
                
                if last_seen is not None:
                    age_seconds = current_time - last_seen
                    
                    # 5 saniyeden uzun süredir görünmüyor
                    if age_seconds > self.ESP_CLEANUP_TIMEOUT:
                        stale_coils.append(coil_id)
                        self.logger.debug(f"Removing stale ESP Coil {coil_id} (last seen {age_seconds:.0f}s ago)")
            
            # Temizle - esp_widgets, esp_status, esp_last_seen'den tamamen kaldır
            if stale_coils:
                for coil_id in stale_coils:
                    # esp_widgets'tan kaldır (UI widget'ları)
                    if coil_id in self.esp_widgets:
                        # Widget'ları UI'dan kaldır
                        widget_data = self.esp_widgets[coil_id]
                        
                        # Widget'ı al (dict içinde 'widget' key'inde saklanıyor olabilir)
                        widget = None
                        if isinstance(widget_data, dict) and 'widget' in widget_data:
                            widget = widget_data['widget']
                        elif hasattr(widget_data, 'parent'): # Direkt widget ise (geriye uyumluluk)
                            widget = widget_data
                        
                        # CRITICAL FIX: Widget'ı layout'tan direkt kaldır
                        if widget:
                            # esp_layout'tan widget'ı kaldır
                            if hasattr(self, 'esp_layout') and self.esp_layout:
                                self.esp_layout.removeWidget(widget)
                            # Widget'ı sil
                            widget.setParent(None)
                            widget.deleteLater()
                            self.logger.debug(f"Widget removed from layout and deleted: Coil {coil_id}")
                        
                        del self.esp_widgets[coil_id]
                    
                    # esp_status'tan kaldır
                    self.esp_status.pop(coil_id, None)
                    
                    # esp_status_buffer'dan kaldır (Thread-Safe)
                    self.esp_status_buffer_mutex.lock()
                    try:
                        self.esp_status_buffer.pop(coil_id, None)
                    finally:
                        self.esp_status_buffer_mutex.unlock()
                    
                    # esp_last_seen'den kaldır
                    self.esp_last_seen.pop(coil_id, None)
                    
                    # CRITICAL FIX: Grafik kontrol panelindeki butonu da disable et
                    try:
                        coil_num = int(coil_id) if isinstance(coil_id, str) else coil_id
                        if hasattr(self, 'coil_buttons') and 1 <= coil_num <= 8:
                            button_index = coil_num - 1  # 0-indexed
                            if button_index < len(self.coil_buttons):
                                button = self.coil_buttons[button_index]
                                button.setEnabled(False)
                                button.setChecked(False)  # Eğer işaretliyse işareti kaldır
                                button.setToolTip(f"Bobin {coil_num} - Bağlantı Bekleniyor")
                                self.logger.debug(f"Bobin {coil_num} butonu disable edildi (bağlantı koptu)")
                    except Exception as btn_err:
                        self.logger.error(f"Bobin buton durumu güncellenirken hata (cleanup): {btn_err}")
                
                self.logger.info(f"ESP cleanup: removed {len(stale_coils)} stale devices (Coils: {stale_coils})")
                
                # Eğer hiç cihaz kalmadıysa "Aranıyor" mesajını geri getir
                if not self.esp_widgets:
                    if not getattr(self, 'no_esp_label', None):
                        self.no_esp_label = QLabel("🔍 Bobin cihazları aranıyor...")
                        self.no_esp_label.setStyleSheet("color: #ffa500; font-size: 14px; text-align: center; padding: 20px;")
                        if hasattr(self, 'esp_layout') and self.esp_layout:
                            self.esp_layout.addWidget(self.no_esp_label)
        
        except Exception as e:
            self.logger.error(f"Error in _cleanup_stale_esp_devices: {e}", exc_info=True)

    def _update_dual_axis_views(self):
        """Updates the geometry of the secondary Y-axis viewbox to match the primary one."""
        if hasattr(self, 'p2') and self.p2 and hasattr(self, 'plot_item') and self.plot_item:
            self.p2.setGeometry(self.plot_item.getViewBox().sceneBoundingRect())
            self.p2.linkedViewChanged(self.plot_item.getViewBox(), self.p2.XAxis)

    def update_main_graph(self):
        """
        Ana grafiği günceller.
        OPTIMİZE EDİLMİŞ VERSİYON:
        1. Spline/Yumuşatma kaldırıldı (Step-like net görüntü).
        2. Veri yuvarlama (Rounding) eklendi (Gürültü önleme).
        3. NumPy maskeleme ile performans artırıldı.
        4. Thread-safe active coils kontrolü.
        """
        try:
            # --- 1. Veri Hazırlığı (Thread-Safe) ---
            self.graph_data_mutex.lock()
            try:
                # Aktif bobin yoksa veya veri toplama kapalıysa çık
                if not self.graph_data_collection_active:
                    return
                
                # Thread-safe active coils snapshot (Thread Safety Fix)
                active_coils_copy = self.active_coils  # Property returns copy
                if not active_coils_copy:
                    return
                
                # Zaman verisi yoksa çık
                if len(self.graph_time_data) == 0:
                    return

                # Ana zaman dizisini numpy array'e çevir
                full_time_data = np.array(self.graph_time_data, dtype=np.float64)
                
                # Bobin verilerini kopyala
                graph_mag_data = {}
                graph_temp_data = {}
                
                for coil_id in active_coils_copy:
                    if coil_id in self.graph_magnetic_field_data:
                        graph_mag_data[coil_id] = np.array(self.graph_magnetic_field_data[coil_id], dtype=np.float64)
                    if coil_id in self.graph_temperature_data:
                        graph_temp_data[coil_id] = np.array(self.graph_temperature_data[coil_id], dtype=np.float64)
            finally:
                self.graph_data_mutex.unlock()

            # --- 2. Zaman Penceresini Hesapla ---
            if len(full_time_data) == 0:
                return
            
            last_timestamp = full_time_data[-1]
            start_timestamp = last_timestamp - 10.0  # Son 10 saniye
            
            # Grafiğin X eksenini zorla bu aralığa kilitle (Kayan Pencere Efekti)
            self.plot_item.setXRange(start_timestamp, last_timestamp, padding=0)

            # --- 3. Verileri İşle ve Çiz (Direct Plotting) ---
            for coil_id in active_coils_copy:
                
                # --- Manyetik Alan ---
                if coil_id in self.mag_field_curves and coil_id in graph_mag_data:
                    raw_y = graph_mag_data[coil_id]
                    min_len = min(len(full_time_data), len(raw_y))
                    
                    if min_len > 0:
                        curr_time = full_time_data[:min_len]
                        curr_y = raw_y[:min_len]
                        
                        # Filtrele: Sadece son 10 saniye
                        mask = curr_time >= start_timestamp
                        # NaN temizle
                        valid_mask = np.isfinite(curr_y) & mask
                        
                        if np.any(valid_mask):
                            final_x = curr_time[valid_mask]
                            # OPTIMIZASYON: 1 basamağa yuvarla (Net çizgi için)
                            final_y = np.round(curr_y[valid_mask], 1)
                            
                            # Doğrudan çiz (Spline yok)
                            self.mag_field_curves[coil_id].setData(final_x, final_y)

                # --- Sıcaklık ---
                if coil_id in self.temp_curves and coil_id in graph_temp_data:
                    raw_y = graph_temp_data[coil_id]
                    min_len = min(len(full_time_data), len(raw_y))
                    
                    if min_len > 0:
                        curr_time = full_time_data[:min_len]
                        curr_y = raw_y[:min_len]
                        
                        mask = curr_time >= start_timestamp
                        valid_mask = np.isfinite(curr_y) & mask
                        
                        if np.any(valid_mask):
                            final_x = curr_time[valid_mask]
                            # OPTIMIZASYON: 1 basamağa yuvarla
                            final_y = np.round(curr_y[valid_mask], 1)
                            
                            # Doğrudan çiz
                            self.temp_curves[coil_id].setData(final_x, final_y)

        except Exception as e:
            self.logger.error("Ana grafik güncelleme hatası: %s", e, exc_info=True)

    def send_global_stop_command(self):
        """Sends a global stop command to all MQTT-connected ESPs with ESP ACK support (FIXED: Only MQTT-connected ESPs)."""
        try:
            if not hasattr(self, 'mqtt_client') or not self.mqtt_client or not self.mqtt_connected_state:
                self.logger.warning("MQTT istemcisi bağlı değil. Global durdurma komutu gönderilemedi.")
                if hasattr(self, 'notification_panel'):
                    self.notification_panel.add_notification("MQTT bağlantısı yok! Komut gönderilemedi.", "warning")
                return
            
            # CRITICAL FIX: Sadece MQTT'ye bağlı ESP'leri bul (widget var ama MQTT bağlı değilse sayma)
            current_time = time.time()
            connected_coils = []
            checked_coils = set()
            
            # 1. esp_status_buffer'dan MQTT bağlı olanları bul (en doğru kaynak)
            if hasattr(self, 'esp_status_buffer') and self.esp_status_buffer:
                # Thread-safe buffer snapshot
                self.esp_status_buffer_mutex.lock()
                try:
                    buffer_snapshot = dict(self.esp_status_buffer)
                finally:
                    self.esp_status_buffer_mutex.unlock()
                
                # MQTT bağlı olanları filtrele
                for coil_id, status_data in buffer_snapshot.items():
                    mqtt_connected = status_data.get('mqtt_connected', False)
                    if mqtt_connected:
                        try:
                            coil_id_int = int(coil_id) if isinstance(coil_id, str) else coil_id
                            if 1 <= coil_id_int <= 8:
                                connected_coils.append(coil_id_int)
                                checked_coils.add(coil_id_int)
                        except (ValueError, TypeError):
                            pass
            
            # 2. esp_last_seen'den de kontrol et (son heartbeat zamanı)
            if hasattr(self, 'esp_last_seen') and self.esp_last_seen:
                for coil_id in range(1, 9):
                    if coil_id not in checked_coils:
                        last_seen = self.esp_last_seen.get(coil_id)
                        # last_seen None değilse ve timeout olmamışsa (3 saniye)
                        if last_seen is not None and (current_time - last_seen <= self.ESP_TIMEOUT):
                            connected_coils.append(coil_id)
                            checked_coils.add(coil_id)
            
            # CRITICAL FIX: Eğer hiç MQTT bağlı ESP yoksa UYARI ver, boşa komut gönderme
            if not connected_coils:
                self.logger.warning("⚠️ Hiçbir ESP MQTT'ye bağlı değil! Komut gönderilemedi.")
                if hasattr(self, 'notification_panel'):
                    self.notification_panel.add_notification("⚠️ Bağlı bobin yok! Komut gönderilemedi.", "warning")
                return
            
            # Duplicate'leri kaldır ve sırala
            connected_coils = sorted(list(set(connected_coils)))
            
            self.logger.info(f"✅ Global stop komutu gönderiliyor - MQTT bağlı {len(connected_coils)} bobin: {connected_coils}")
            
            # Sadece MQTT bağlı ESP'lere komut gönder
            commands_sent = 0
            for coil_id in connected_coils:
                # Unique command ID oluştur
                command_id = f"global_stop_{coil_id}_{int(time.time() * 1000)}"
                command = {
                    "command": "stop",
                    "command_id": command_id,  # ESP ACK için gerekli
                    "timestamp": time.time()
                }
                topic = f"pemf/coil/{coil_id}/control"
                self.mqtt_client.publish(topic, json.dumps(command), qos=1)
                commands_sent += 1
                self.logger.info(f"Global stop command sent to connected coil {coil_id}")
            
            self.logger.info(f"Tüm bağlı bobinlere global durdurma komutu gönderildi ({commands_sent} ESP'ye komut gönderildi).")
            if hasattr(self, 'notification_panel'):
                self.notification_panel.add_notification(f"Tüm bağlı bobinler durduruldu ({commands_sent} ESP).", "info")
        except Exception as e:
            self.logger.error(f"Global durdurma komutu gönderilirken hata oluştu: {e}", exc_info=True)
            if hasattr(self, 'notification_panel'):
                self.notification_panel.add_notification(f"Hata: {str(e)}", "error")
    
    def _maybe_notify_portal_open(self, coil_id, portal_ssid, portal_ip):
        """Portal açılış bildirimini tek noktadan ve tekrar etmeyecek şekilde göster."""
        try:
            portal_ip = portal_ip or "192.168.4.1"
            if coil_id not in self.portal_notified and hasattr(self, 'notification_panel'):
                message = (
                    f"ESP{coil_id} WiFi'ye bağlanamadı. "
                    f"Lütfen telefonunuzdan '{portal_ssid}' WiFi ağına bağlanın ve "
                    f"tarayıcınızda {portal_ip} adresine gidin."
                )
                self.notification_panel.add_notification(message, "warning")
            self.portal_notified.add(coil_id)
            return portal_ip
        except Exception as e:
            self.logger.error(f"Portal bildirimi oluşturulamadı (coil {coil_id}): {e}")
            return portal_ip or "192.168.4.1"

    def _notify_portal_closed(self, coil_id, message=None, level="info"):
        """Portal kapandığında paneli ve UI'yi güncelle."""
        try:
            if message and hasattr(self, 'notification_panel'):
                self.notification_panel.add_notification(message, level)
            self.portal_notified.discard(coil_id)
            self.esp_portal_status[coil_id] = {
                'coil_id': coil_id,
                'portal_active': False,
                'portal_ssid': '',
                'portal_ip': ''
            }
            status_data = {
                'coil_id': coil_id,
                'portal_active': False,
                'portal_ssid': '',
                'portal_ip': ''
            }
            # ✅ FIX: coil_id str'ye çevir (signal type: str, dict)
            self.esp_status_received.emit(str(coil_id), status_data)
        except Exception as e:
            self.logger.error(f"Portal kapanış güncellemesi yapılamadı (coil {coil_id}): {e}")

    def _start_portal_status_check(self):
        """
        Portal durumu kontrolü için QRunnable başlatır (Timer Optimization - QThreadPool ile async).
        Timer tarafından çağrılır, bloklayıcı I/O işlemini thread pool'a taşır.
        """
        # Minimum kontrol aralığı kontrolü (performans için)
        # Eğer son kontrol 3 saniyeden kısa bir süre önce yapıldıysa, yeni kontrol başlatma
        current_time = time.time()
        if hasattr(self, 'last_portal_check_time') and (current_time - self.last_portal_check_time) < 3.0:
            self.logger.debug("Portal kontrolü çok sık yapılıyor, atlanıyor")
            return
        
        # Thread pool'da aktif görev sayısını kontrol et (overlap önleme)
        if self.portal_thread_pool.activeThreadCount() > 0:
            self.logger.debug("Portal status checker hala çalışıyor, yeni görev başlatılmıyor")
            return
        
        # Son kontrol zamanını güncelle
        self.last_portal_check_time = current_time
        
        # QRunnable oluştur ve thread pool'a ekle (Timer Optimization)
        runnable = PortalStatusCheckerRunnable(
            callback=self._on_portal_scan_completed,
            logger=self.logger
        )
        self.portal_thread_pool.start(runnable)
    
    def _on_portal_scan_completed(self, pemf_ssids):
        """
        Portal tarama tamamlandığında çağrılır (signal slot).
        Ana thread'de çalışır, GUI güncellemeleri yapılabilir.
        
        Args:
            pemf_ssids (list[int]): Bulunan PEMF-Coil-X SSID'lerinin coil ID'leri
        """
        try:
            # Bulunan ESP'lerin portal durumunu kontrol et
            for coil_id in pemf_ssids:
                # Portal SSID görünürse, portal açık demektir
                # Portal durumu değişti mi kontrol et
                old_status = self.esp_portal_status.get(coil_id, {})
                old_portal_active = old_status.get('portal_active', False)
                
                if not old_portal_active:
                    portal_ssid = f"PEMF-Coil-{coil_id}"
                    portal_ip = self._maybe_notify_portal_open(coil_id, portal_ssid, "192.168.4.1")
                    self.logger.warning(f"ESP {coil_id} portal açıldı: {portal_ssid} ({portal_ip})")
                    self.esp_portal_status[coil_id] = {
                        'portal_active': True,
                        'coil_id': coil_id,
                        'portal_ssid': portal_ssid,
                        'portal_ip': portal_ip
                    }
            
            # Portal kapalı olan ESP'leri kontrol et (daha önce açıktı ama şimdi yok)
            for coil_id in list(self.esp_portal_status.keys()):
                if coil_id not in pemf_ssids:
                    old_status = self.esp_portal_status.get(coil_id, {})
                    if old_status.get('portal_active', False):
                        self._notify_portal_closed(coil_id, f"✅ ESP {coil_id} WiFi Portal kapatıldı", "info")
                        self.logger.info(f"ESP {coil_id} portal kapandı")
                        
        except Exception as e:
            self.logger.error(f"Portal durumu işleme hatası: {e}", exc_info=True)
    
    
    def keyPressEvent(self, event):
        """
        Handle keyboard shortcuts.
        """
        try:
            # Call parent implementation
            super().keyPressEvent(event)
            
        except Exception as e:
            self.logger.error(f"Key press event handler error: {e}", exc_info=True)
            super().keyPressEvent(event)
    

def main():
    app = QApplication(sys.argv)
    
    # Setup logger for main function
    from utils.logger_config import get_logger
    logger = get_logger('MainWindow.main')
    
    # Set application icon
    try:
        icon_path = resource_path('resources/icons/pemf_heart_emf_icon.ico')
        if os.path.exists(icon_path):
            app.setWindowIcon(QIcon(icon_path))
        else:
            # Try alternative paths for PyInstaller
            if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
                alt_path = Path(sys._MEIPASS) / 'pemf_gui' / 'resources' / 'icons' / 'pemf_heart_emf_icon.ico'
                if alt_path.exists():
                    app.setWindowIcon(QIcon(str(alt_path)))
    except Exception as e:
        logger.warning(f"Icon yüklenemedi: {e}", exc_info=True)
    
 
    # Splash screen'i göster ve en öne getir
    splash = show_splash_screen(app, version=MainWindow.SOFTWARE_VERSION)
    splash.raise_()
    splash.activateWindow()
    QApplication.processEvents()
    
    # Progress güncellemeleri
    splash.set_progress(10, "Sistem kaynakları kontrol ediliyor...")
    QApplication.processEvents()
    
    # Veritabanı hazırlanıyor (0 km kurulum)
    splash.set_progress(20, "Veritabanı hazırlanıyor...")
    QApplication.processEvents()
    initialize_database()
    
    # Ana pencereyi oluştur
    splash.set_progress(30, "Modüller yükleniyor...")
    QApplication.processEvents()
    
    main_win = MainWindow()
    
    splash.set_progress(60, "Veritabanı bağlantısı kuruluyor...")
    QApplication.processEvents()
    
    splash.set_progress(80, "Kullanıcı arayüzü hazırlanıyor...")
    QApplication.processEvents()
    
    splash.set_progress(90, "Son kontroller yapılıyor...")
    QApplication.processEvents()
    
    # Yükleme tamamlandığında splash'i kapat ve ana pencereyi göster
    def on_loading_finished():
        splash.set_progress(100, "Başlatılıyor!")
        QApplication.processEvents()
        time.sleep(0.3)  # Kısa bir gecikme
        splash.close()
        QApplication.processEvents()
        
        # Ana pencereyi göster ve en üste getir
        main_win.show()
        QApplication.processEvents()
        
        # Windows'ta pencereyi en üste getirmek için ekstra adımlar
        main_win.setWindowState(Qt.WindowState.WindowActive)
        main_win.raise_()
        main_win.activateWindow()
        main_win.setFocus()
        
        # Windows API ile pencereyi zorla en üste getir
        if sys.platform == 'win32':
            try:
                hwnd = int(main_win.winId())
                ctypes.windll.user32.SetForegroundWindow(hwnd)
                ctypes.windll.user32.ShowWindow(hwnd, 9)  # SW_RESTORE = 9
                ctypes.windll.user32.BringWindowToTop(hwnd)
            except Exception as e:
                logger.warning(f"Windows API ile pencereyi en üste getirme hatası: {e}", exc_info=True)
        
        QApplication.processEvents()

    # Splash screen'in progress'i 100 olunca ana pencereyi göster
    splash.progress_updated.connect(lambda p: app.processEvents())
    QTimer.singleShot(500, on_loading_finished)  # Kısa bir gecikme sonrası kapat

    # Kapanış ekranı için sinyal-slot bağlantısı
    def cleanup_and_quit():
        try:
            # Ana pencereyi gizle
            if main_win.isVisible():
                main_win.hide()
            QApplication.processEvents()
            
            # Kapanış ekranını göster
            closing_screen = show_closing_screen(app)
            QApplication.processEvents()
            
            # Kapanış ekranı gösterildikten sonra kapat
            closing_screen.close()
        except Exception as e:
            logger.error(f"Kapanış ekranı gösterilirken hata: {e}", exc_info=True)
    
    app.aboutToQuit.connect(cleanup_and_quit)

    sys.exit(app.exec())


if __name__ == '__main__':
    main()
