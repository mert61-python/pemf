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
import tempfile

# Add parent directory to path for module imports
if __name__ == "__main__":
    current_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(current_dir)
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)

from utils.patient_input_validator import PatientInputValidator
from utils.path_utils import get_unique_device_id, initialize_database, get_app_data_directory as shared_get_app_data_directory
import matplotlib
import threading
import logging
import logging.handlers
import ctypes
import shutil
import subprocess
from datetime import datetime
from collections import deque
from queue import Queue, Empty, Full
from typing import Optional

# PREVENT QWebEngineView IMPORT ERROR
try:
    from PyQt6 import QtWebEngineWidgets
except ImportError:
    pass

# Add parent directory to path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

import paho.mqtt.client as mqtt
import ssl  # SSL/TLS için gerekli
import socket  # DNS ve network hataları için gerekli
import uuid  # Benzersiz MQTT client ID üretimi için

# Gateway services
from services.mosquitto_manager import MosquittoManager
from services.network_monitor import NetworkMonitor
from services.db_maintenance_service import DBMaintenanceService
from services.hotspot_manager import HotspotManager
from windows.gateway_status_widget import GatewayStatusWidget
from windows.ble_provision_dialog import BLEProvisionDialog
from threads.discovery_service_thread import DiscoveryServiceThread
from threads.digital_twin_thread import DigitalTwinFileCopyThread

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
from PyQt6.QtCore import QTimer, Qt, pyqtSignal, QThread, QThreadPool, QRunnable, QObject, QSize
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QFont, QColor
from windows.splash_screen import show_splash_screen, show_closing_screen


def _render_emoji_icon(emoji_char: str, size: int = 22) -> QIcon:
    """
    Emoji karakterini QPixmap üzerine çizer ve QIcon olarak döner.
    Bu yöntemle emoji QPushButton metnine yazılmaz, dolayısıyla
    emoji fallback fontunun büyük ascent/descent değerleri buton
    yüksekliğini ve metin hizalamasını bozmaz.
    """
    px = QPixmap(size, size)
    px.fill(QColor(0, 0, 0, 0))          # şeffaf arka plan
    painter = QPainter(px)
    font = QFont()
    font.setPixelSize(max(10, size - 2))
    painter.setFont(font)
    painter.setPen(QColor("white"))
    painter.drawText(px.rect(), Qt.AlignmentFlag.AlignCenter, emoji_char)
    painter.end()
    return QIcon(px)
from utils.notification_panel import NotificationPanel
from database.patient_database import get_patient_database
from database.treatment_history_db import get_treatment_db
from database.session_manager import get_session_manager
# Design System
from styles import StyleMixin
# Responsive Utils
from utils.responsive_utils import (
    make_resizable, scale_font, scale_margins, scale_value,
    get_responsive_spacing, get_responsive_font_size,
    apply_responsive_layout, get_screen_info,
    scale_stylesheet, get_responsive_pt, RS,
    invalidate_screen_cache,
)
# Metrics Collection
from utils.metrics_collector import get_metrics_collector, timer as metrics_timer
# Local imports
from utils.path_utils import resource_path, get_app_data_directory
import numpy as np
import pyqtgraph as pg
# scipy import kaldırıldı - Spline interpolation artık kullanılmıyor (performans ve netlik için)

# OpenGL devre dış - eski bilgisayarlarda uyumluluk için software rendering kullan
pg.setConfigOptions(useOpenGL=False, enableExperimental=False)
pg.setConfigOption('background', '#1e1e2e')

class TicksAxis(pg.AxisItem):
    def tickStrings(self, values, scale, spacing):
        return [f"{value:.1f}" for value in values]

class LegacyDigitalTwinFileCopyThread(QThread):
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
    
    def stop(self) -> None:
        """
        Thread'i güvenli şekilde durdurur.
        Qt'nun requestInterruption() mekanizmasını kullanır;
        run() içindeki isInterruptionRequested() kontrolleri bu flagı okur.
        """
        self.requestInterruption()
        if self.isRunning():
            if not self.wait(5000):                   # 5 saniye bekle
                import logging
                logging.getLogger(__name__).warning("Thread %s 5 sn icinde kapanmadi (terminate() iptal edildi)", self.__class__.__name__)
                self.wait(1000)

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
                if self.isInterruptionRequested():
                    return
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


class PatientSaveSignals(QObject):
    """Signals for async patient save worker."""
    success = pyqtSignal(str, dict)  # patient_id, patient_info
    error = pyqtSignal(str)


class PatientSaveWorker(QRunnable):
    """Save patient to DB on a background thread."""
    def __init__(self, app_data_dir, patient_info, current_user=None, logger=None):
        super().__init__()
        self.app_data_dir = app_data_dir
        self.patient_info = patient_info
        self.current_user = current_user
        self.logger = logger
        self.signals = PatientSaveSignals()

    def run(self):
        try:
            db = get_patient_database(self.app_data_dir)
            if self.current_user:
                db.current_user = self.current_user
            patient_id = db.add_patient(self.patient_info)
            self.signals.success.emit(patient_id, self.patient_info)
        except Exception as e:
            if self.logger:
                self.logger.error("Async patient save failed: %s", e, exc_info=True)
            self.signals.error.emit(str(e))


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
    
    # Thread-safe signals for coil control (from UnifiedControlWindow)
    # These signals ensure only MainWindow writes to MQTT, preventing conflicts
    # Parameters: int (coil_num), dict (command with 'command', 'command_id', 'freq', 'duty', 'duration', 'timestamp')
    coil_control_requested = pyqtSignal(int, dict)
    batch_coil_control_requested = pyqtSignal(dict)  # Yeni: Toplu komut gönderimi için
    
    # Patient saved signal - notify unified control window to refresh patient list
    patient_saved = pyqtSignal()
    
    # STM32 donanım bağlantı durumu sinyali (Rapor §4.1)
    stm_connected_signal = pyqtSignal(bool)
    
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

    def _is_window_alive(self, win):
        return win is not None and getattr(win, 'isVisible', lambda: False)()

    def _on_stm_connected_slot(self, connected: bool):
        """STM bağlantı durumu değiştiğinde çağrılır."""
        self.stm_is_connected = connected
        if connected:
            self.connection_status_label.setText("🔗 Sürücü Bağlı (5 Bobin)")
            self.connection_status_label.setStyleSheet(
                RS.connection_status_stm(color="#22c55e")
            )
            self.statusBar().showMessage("Sürücü Bağlandı — 5 Bobin PWM Aktif")
            self.statusBar().setStyleSheet(RS.status_bar_connected())
            
            # İlk 5 bobini sistem genelinde "Aktif" işaretle ve ESP panelinde göster
            for i in range(1, 6):
                self._add_active_coil(i)
                mock_data = {
                    'mqtt_connected': True,
                    'wifi_connected': True,
                    'stm32_driven': True
                }
                self.update_esp_status_internal(str(i), mock_data)
        else:
            self.connection_status_label.setText("⚠️ Sürücü Bağlı Değil")
            self.connection_status_label.setStyleSheet(
                RS.connection_status_stm(color="#ef4444")
            )
            self.statusBar().showMessage("Sürücü Bağlantısı Bekleniyor...")
            self.statusBar().setStyleSheet(RS.status_bar_disconnected())
        # UCW açıksa ilet
        if self._is_window_alive(self.unified_control_window):
            self.unified_control_window.set_stm_connected(connected)

    def send_stm_packet(self, stm_msg: str, udp_pkt=None, esp_ip="", esp_port=0):
        """UCW'den doğrudan STM mesajı göndermek için public API."""
        try:
            self._hw_send_queue.put_nowait((stm_msg, udp_pkt, esp_ip, esp_port))
        except Full:
            try:
                self._hw_send_queue.get_nowait()
                self._hw_send_queue.put_nowait((stm_msg, udp_pkt, esp_ip, esp_port))
            except Empty:
                pass

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
            QTimer.singleShot(0, lambda: self.notification_panel.add_notification(f"Bağlantı Hatası: {error_message}", "error"))
        else:
            # Fallback: konsola yazdır
            self.logger.error(f"Bağlantı Hatası: {error_message}")

    def check_for_updates(self):
        try:
            from services.updater_service import UpdateCheckerThread
            url = "https://raw.githubusercontent.com/mert61-python/pemf-update/main/version.json"
            self.update_checker = UpdateCheckerThread(self.SOFTWARE_VERSION, url, self)
            self.update_checker.update_available.connect(self.on_update_available)
            self.update_checker.start()
        except Exception as e:
            if hasattr(self, 'logger'):
                self.logger.error(f"Updater başlatılamadı: {e}")

    def on_update_available(self, version, download_url, release_notes):
        from PyQt6.QtWidgets import QMessageBox, QProgressDialog
        from PyQt6.QtCore import Qt
        reply = QMessageBox.question(
            self, 'Güncelleme Bulundu',
            f'Yeni bir sürüm (v{version}) yayınlandı!\n\nDeğişiklikler:\n{release_notes}\n\nŞimdi otomatik olarak indirip kurmak ister misiniz?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            # Otomatik indir ve kur (Sessiz Kurulum)
            self.progress_dialog = QProgressDialog("Güncelleme indiriliyor...", "İptal", 0, 100, self)
            self.progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
            self.progress_dialog.setWindowTitle("İndiriliyor")
            self.progress_dialog.setAutoClose(True)
            self.progress_dialog.setAutoReset(True)
            self.progress_dialog.show()

            from services.updater_service import UpdateDownloaderThread, launch_installer_and_exit
            self.update_downloader = UpdateDownloaderThread(download_url, self)
            
            def on_progress(percent):
                if hasattr(self, 'progress_dialog') and not self.progress_dialog.wasCanceled():
                    self.progress_dialog.setValue(percent)

            def on_download_finished(file_path):
                if hasattr(self, 'progress_dialog'):
                    self.progress_dialog.setValue(100)
                QMessageBox.information(self, "İndirme Tamamlandı", "Kurulum arka planda başlatılıyor. Uygulama güncellenmek üzere kapanacak...")
                launch_installer_and_exit(file_path)

            def on_download_error(error_msg):
                if hasattr(self, 'progress_dialog'):
                    self.progress_dialog.close()
                QMessageBox.critical(self, "İndirme Hatası", f"Güncelleme indirilirken hata oluştu:\n{error_msg}")

            def on_cancel():
                if hasattr(self, 'update_downloader'):
                    self.update_downloader.cancel()

            self.update_downloader.progress.connect(on_progress)
            self.update_downloader.download_finished.connect(on_download_finished)
            self.update_downloader.download_error.connect(on_download_error)
            
            self.progress_dialog.canceled.connect(on_cancel)

            self.update_downloader.start()


    def closeEvent(self, event):
        """
        Uygulama kapatıldığında çağrılır - hızlı ve basit kapanış
        Thread-safe cleanup ve async file I/O
        """
        # Kapanma durumunu işaretle
        self.is_closing = True
        
        try:
            # Gateway servisleri durdur
            if hasattr(self, 'network_monitor') and self.network_monitor:
                try:
                    self.network_monitor.stop_monitoring()
                except Exception:
                    pass
            if hasattr(self, 'mosquitto_manager') and self.mosquitto_manager:
                try:
                    self.mosquitto_manager.stop_monitoring()
                except Exception:
                    pass
            if hasattr(self, 'hotspot_manager'):
                pass  # Hotspot'u kapatmıyoruz — ESP'ler bağlı kalabilir
            if hasattr(self, 'digital_twin_copy_thread') and self.digital_twin_copy_thread:
                try:
                    t = self.digital_twin_copy_thread
                    if t.isRunning():
                        t.stop()               # requestInterruption + terminate fallback
                except Exception:
                    pass
            if hasattr(self, 'discovery_thread') and self.discovery_thread:
                try:
                    t = self.discovery_thread
                    if t.isRunning():
                        t.stop()
                        if not t.wait(3000):   # 3 s → daha uzun UDP soketi kapanması için
                            t.terminate()
                            t.wait(500)
                except Exception:
                    pass
            if hasattr(self, '_mqtt_connection_thread') and self._mqtt_connection_thread:
                try:
                    t = self._mqtt_connection_thread
                    if t.isRunning():
                        if hasattr(t, 'stop') and callable(t.stop):
                            t.stop()               # _is_running=False + requestInterruption
                        else:
                            t.requestInterruption()
                            t.quit()
                        if not t.wait(2000):       # 2 s bekle
                            t.terminate()
                            t.wait(500)
                except Exception:
                    pass
            if hasattr(self, 'waiter_thread') and self.waiter_thread:
                try:
                    t = self.waiter_thread
                    if t.isRunning():
                        if hasattr(t, 'stop') and callable(t.stop):
                            t.stop()               # requestInterruption + wait içinde
                        else:
                            t.requestInterruption()
                            t.quit()
                        if not t.wait(2000):
                            t.terminate()
                            t.wait(500)
                except Exception:
                    pass
            if hasattr(self, '_hw_sender_stop'):
                self._hw_sender_stop.set()
            if hasattr(self, '_hw_sender_thread') and getattr(self._hw_sender_thread, 'is_alive', lambda: False)():
                try:
                    self._hw_sender_thread.join(timeout=1.0)
                except Exception:
                    pass
            if hasattr(self, 'db_maintenance_service') and self.db_maintenance_service:
                try:
                    self.db_maintenance_service.stop()
                except Exception:
                    pass
            
            # MQTT callback cleanup (Memory Leak Fix)
            if hasattr(self, 'mqtt_client') and self.mqtt_client:
                self.logger.info("Cleaning up MQTT callbacks...")
                self.mqtt_client.on_connect = None
                self.mqtt_client.on_disconnect = None
                self.mqtt_client.on_message = None
                self.mqtt_client.on_subscribe = None
            # Tüm timer'ları durdur ve temizle (Orphaned Timer Fix)
            for timer_name in ['unified_1hz_timer', 'graph_update_timer', 'connection_check_timer', 
                             'mqtt_reconnect_timer']:
                if hasattr(self, timer_name):
                    timer = getattr(self, timer_name)
                    if timer and timer.isActive():
                        timer.stop()
                        timer.deleteLater()  # Proper cleanup
            
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
                        except Exception as e:
                            if hasattr(self, 'logger'): self.logger.error(f"Pencere kapatma hatasi ({attr_name}): {e}")
            
            # Çalışma süresini async kaydet (File I/O Optimization)
            if hasattr(self, 'working_time_file') and hasattr(self, 'working_seconds'):
                try:
                    writer = AsyncFileWriter(
                        self.working_time_file,
                        self.working_seconds,
                        self.logger
                    )
                    QThreadPool.globalInstance().start(writer)
                except Exception as e:
                    if hasattr(self, 'logger'): self.logger.error(f"Calisma suresi kaydedilemedi: {e}")
            
            # MQTT temizle
            if hasattr(self, 'mqtt_client') and self.mqtt_client:
                try:
                    self.mqtt_client.disconnect()
                except Exception as e:
                    if hasattr(self, 'logger'): self.logger.error(f"MQTT disconnect hatasi: {e}")
                    
            # Arka plan işlemlerinin bitmesini bekle (Async file I/O bitmesi için)
            QThreadPool.globalInstance().waitForDone(500)
            # Genel güvenli thread temizliği: self içindeki QThread örneklerini tespit et
            try:
                from PyQt6.QtCore import QThread
                for attr_name, attr_val in list(vars(self).items()):
                    try:
                        if isinstance(attr_val, QThread):
                            # Öncelikle custom stop() metodu varsa çağır
                            if hasattr(attr_val, 'stop') and callable(getattr(attr_val, 'stop')):
                                try:
                                    attr_val.stop()
                                except Exception:
                                    pass
                            else:
                                # quit() uygunsa çağır
                                if hasattr(attr_val, 'quit') and callable(getattr(attr_val, 'quit')):
                                    try:
                                        attr_val.quit()
                                    except Exception:
                                        pass

                            # Eğer hâlâ çalışıyorsa kısa süre bekle
                            try:
                                if getattr(attr_val, 'isRunning', lambda: False)():
                                    try:
                                        attr_val.wait(2000)
                                    except Exception:
                                        pass
                            except Exception:
                                pass
                    except Exception:
                        # Herhangi bir attribute okuma hatası yoksay
                        pass
            except Exception:
                pass

        except Exception as e:
            if hasattr(self, 'logger'):
                self.logger.error("closeEvent sirasinda beklenmeyen hata", exc_info=True)
            else:
                import logging
                logging.error(f"closeEvent sirasinda beklenmeyen hata: {e}", exc_info=True)
        
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
            console_level=logging.INFO,   # Production mode: only warnings and errors
            file_level=logging.INFO,         # File logging remains INFO for troubleshooting
            enable_console=True,
            enable_file=True,
            max_file_size=10 * 1024 * 1024,  # 10 MB per file (explicit)
            backup_count=5                   # 5 backup files (explicit)
        )
        
        self.log_listener = logger_config.queue_listener
        self.logger = get_logger('MainWindow')
        
        # Benzersiz cihaz kimliğini al (uzaktan izleme için)
        self.device_id = get_unique_device_id()
        self.logger.info("Cihaz ID: %s", self.device_id)
        
        # Initialize metrics collector (after logger is created)
        self.metrics = get_metrics_collector()
        self.logger.info("Metrics collector initialized")
        
        # Asenkron loglama durumunu logla
        self.logger.info("Asenkron loglama (Non-Blocking I/O) logger_config üzerinden aktif.")
        
        self.logger.info("=== GUI Application Started ===")
        self.logger.info(f"Log directory: {log_dir}")
        
        # ─── FRONTEND OTO-GÜNCELLEYİCİ BAŞLAT ─────────
        try:
            from services.frontend_updater_service import FrontendUpdaterThread
            self.frontend_updater = FrontendUpdaterThread(current_version="1.0.0", parent=self)
            self.frontend_updater.update_finished.connect(
                lambda msg: QTimer.singleShot(3000, lambda: self.notification_panel.add_notification(msg, "info")) if hasattr(self, 'notification_panel') else self.logger.info(msg)
            )
            self.frontend_updater.start()
        except Exception as e:
            self.logger.error(f"Frontend Updater başlatılamadı: {e}")
        
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

        # Lazy-initialized secondary windows (create on first use)
        self.sensor_data_window = None
        self.unified_control_window = None
        self.kpi_dashboard_window = None
        self.treatment_history_window = None

        # Async patient save state
        self._patient_save_in_progress = False
        self.save_patient_btn = None
        
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

        # Faz 1 ölçüm enstrümantasyonu (MQTT alım -> GUI render gecikmesi)
        performance_cfg = self._load_performance_config()
        metrics_cfg = performance_cfg.get('metrics', {})
        self._latency_target_ms = float(performance_cfg.get('latency_target_ms', 200.0))
        self._latency_history_size = max(200, int(metrics_cfg.get('latency_history_size', 2000)))
        self._latency_publish_every_renders = max(1, int(metrics_cfg.get('publish_every_renders', 5)))
        self._pending_render_receive_ts = deque(maxlen=5000)
        self._render_latency_samples_ms = deque(maxlen=self._latency_history_size)
        self._render_tick_count = 0
        
        # Thread-safe durum değişkenleri (GUI öğelerine farklı thread'lerden erişim için)
        self.current_frequency = 0.0  # Hz
        self.current_intensity = 0.0  # mT
        self.current_duration = 0  # dakika
        self.treatment_active = False  # Tedavi aktif mi?
        
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
        
        # --- Gateway Services (LattePanda Offline-First) ---
        self._init_gateway_services()
        
        # --- STM32 Serial + UDP Hardware Sender (Rapor §4.1) ---
        self.stm_is_connected = False
        self.stm_connected_signal.connect(
            self._on_stm_connected_slot,
            Qt.ConnectionType.QueuedConnection
        )
        self._hw_send_queue = Queue(maxsize=4)
        self._hw_sender_stop = threading.Event()
        
        def _hw_sender_worker():
            """STM32 serial ve UDP gönderimlerini ana thread'den bağımsız çalıştırır."""
            _serial = None
            _udp_sock = None
            _stm_ready_emitted = [False]  # closure için mutable
            
            # Serial port aç
            try:
                import serial as _serial_lib
                import serial.tools.list_ports as _list_ports
                from PyQt6.QtCore import QSettings
                _settings = QSettings("Mertacor", "PEMF_GUI")
                port_name = _settings.value("stm32_com_port", "AUTO", type=str)
                if port_name in ("AUTO", "COM10"):
                    detected_port = None
                    ports = list(_list_ports.comports())
                    for p in ports:
                        desc = p.description.lower()
                        hwid = p.hwid.lower()
                        if "ch340" in desc or "stlink" in desc or "stm32" in desc \
                                or "vid:pid=0483" in hwid or "vid:pid=1a86" in hwid:
                            detected_port = p.device
                            break
                    if not detected_port:
                        for p in ports:
                            if "usb" in p.hwid.lower() or "serial" in p.description.lower():
                                detected_port = p.device
                                break
                    if detected_port:
                        port_name = detected_port
                        _settings.setValue("stm32_com_port", port_name)
                        self.logger.info(f"🔍 [STM32 OTO-TANIMA] {port_name}")
                    else:
                        port_name = "COM10"

                _serial = _serial_lib.Serial(
                    port_name, 115200, timeout=1, dsrdtr=False, rtscts=False
                )
                self.logger.info(f"🚀 [STM32] {port_name} portu açıldı")

                def _reader():
                    while _serial and _serial.is_open and not self._hw_sender_stop.is_set():
                        try:
                            line = _serial.readline()
                            if line:
                                decoded = line.decode('utf-8', errors='ignore').strip()
                                if decoded:
                                    self.logger.info(f"✅ [STM32] {decoded}")
                                    # STM_READY mesajı ilk kez geldiğinde sinyal emit et
                                    if "STM_READY" in decoded and not _stm_ready_emitted[0]:
                                        _stm_ready_emitted[0] = True
                                        self.stm_connected_signal.emit(True)
                        except Exception as _e:
                            self.logger.warning(f"⚠️ [STM32 READER] {_e}")
                            break
                    # Reader thread bittiğinde/koptuğunda durumu False yap
                    if _stm_ready_emitted[0]:
                        _stm_ready_emitted[0] = False
                        self.stm_connected_signal.emit(False)

                threading.Thread(target=_reader, daemon=True, name="STM32Reader").start()

            except Exception as e:
                self.logger.warning(f"❌ [STM32] Serial açılamadı: {e}")
                _serial = None
                self.stm_connected_signal.emit(False)

            # UDP soketi aç
            try:
                import socket as _socket_lib
                _udp_sock = _socket_lib.socket(_socket_lib.AF_INET, _socket_lib.SOCK_DGRAM)
                _udp_sock.setsockopt(_socket_lib.SOL_SOCKET, _socket_lib.SO_BROADCAST, 1)
            except Exception as e:
                self.logger.warning(f"❌ [UDP] Soket açılamadı: {e}")
                _udp_sock = None

            # Ana gönderim döngüsü
            while not self._hw_sender_stop.is_set():
                try:
                    payload_tuple = self._hw_send_queue.get(timeout=0.5)
                except Empty:
                    continue
                stm_msg, udp_pkt, esp_ip, esp_port = payload_tuple
                if _serial and _serial.is_open and stm_msg:
                    try:
                        _serial.write(stm_msg.encode('utf-8'))
                    except Exception as e:
                        self.logger.warning(f"❌ [STM32 SEND] {e}")
                        # Gönderim hatası kopma anlamına gelir
                        if _stm_ready_emitted[0]:
                            _stm_ready_emitted[0] = False
                            self.stm_connected_signal.emit(False)
                if _udp_sock and udp_pkt:
                    try:
                        _udp_sock.sendto(udp_pkt, (esp_ip, esp_port))
                    except Exception as e:
                        self.logger.warning(f"❌ [UDP SEND] {e}")

            # Temizlik
            if _serial and _serial.is_open:
                try: _serial.close()
                except: pass
            if _udp_sock:
                try: _udp_sock.close()
                except: pass

        self._hw_sender_thread = threading.Thread(
            target=_hw_sender_worker, daemon=True, name="HWSender"
        )
        self._hw_sender_thread.start()
        
        self.setWindowTitle("Pemf Vet sistemi")
        self.setWindowIcon(QIcon(resource_path("resources/icons/pemf_heart_emf_icon.ico")))
        
        # Responsive window sizing
        self._setup_responsive_window()
        
        # Window flags to enable maximize and resize
        self.setWindowFlags(Qt.WindowType.Window | 
                           Qt.WindowType.WindowMinimizeButtonHint | 
                           Qt.WindowType.WindowMaximizeButtonHint | 
                           Qt.WindowType.WindowCloseButtonHint)

        # Responsive layout and styling
        self.apply_theme()
        
        # Native statusBar gizle — custom status label main_layout içinde kullanılır
        # (nav_widget altında örtüşme sorununu önler)
        self.statusBar().hide()
        
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
        
        top_bar_widget.setStyleSheet(RS.top_bar_widget(margin_top=top_margin, margin_side=side_margin))
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
            _icon_size = scale_value(48, min_ratio=0.6, max_ratio=1.8)
            icon_pixmap = QPixmap(str(icon_path)).scaled(_icon_size, _icon_size, Qt.AspectRatioMode.KeepAspectRatio,
                                                         Qt.TransformationMode.SmoothTransformation)
            if not icon_pixmap.isNull():
                icon_label.setPixmap(icon_pixmap)
            else:
                icon_label.setText("💚")
                icon_font_size = get_responsive_font_size(32)
                icon_label.setStyleSheet(RS.icon_emoji(base_pt=25))
        else:
            icon_label.setText("💚")
            icon_label.setStyleSheet(RS.icon_emoji(base_pt=25))

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
        
        self.clock.setStyleSheet(RS.clock_label(base_pt=15))
        top_bar_layout.addWidget(self.clock)

        # Silent mode toggle button
        self.silent_mode_btn = QPushButton("🔊")
        self.silent_mode_btn.setToolTip("Sessiz Mod (Bildirimleri Kapat/Aç)")
        
        self.silent_mode_btn.setStyleSheet(RS.silent_mode_btn(active=False))
        self.silent_mode_btn.clicked.connect(self.toggle_silent_mode)
        top_bar_layout.addWidget(self.silent_mode_btn)

        # User Manual button
        self.user_manual_btn = QPushButton("📖 Kullanım Kılavuzu")
        self.user_manual_btn.setToolTip("PDF Kullanım Kılavuzunu Aç")
        self.user_manual_btn.setStyleSheet(RS.user_manual_btn())
        self.user_manual_btn.clicked.connect(self.open_user_manual)
        top_bar_layout.addWidget(self.user_manual_btn)

        # Connection Status Label (Rapor §4.1)
        self.connection_status_label = QLabel("⚠️ Sürücü Bekleniyor")
        self.connection_status_label.setStyleSheet(RS.connection_status_label())
        self.connection_status_label.setToolTip("STM32 bağlantı durumu")
        top_bar_layout.addWidget(self.connection_status_label)

        # Emergency stop button
        emergency_btn = QPushButton("ACİL DURDURMA")
        emergency_btn.clicked.connect(self.send_global_stop_command)
        
        emergency_btn.setStyleSheet(RS.emergency_stop_btn())
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
        # config.json -> timers -> graph_update_ms (default 250 for LattePanda)
        _graph_ms = 250
        try:
            import json as _json, os as _os
            _cfg_path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)),
                                      '..', 'config', 'config.json')
            with open(_cfg_path, 'r', encoding='utf-8') as _f:
                _cfg = _json.load(_f)
            _graph_ms = max(100, int(_cfg.get('timers', {}).get('graph_update_ms', 250)))
        except Exception:
            pass
        self.graph_update_timer.start(_graph_ms)
        
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
        sidebar.setSpacing(get_responsive_spacing(4))
        sidebar.setContentsMargins(0, 0, 0, 0)

        sidebar_widget = QWidget()
        # Responsive sidebar styling
        sidebar_padding = scale_margins(sidebar_widget, 16)
        
        sidebar_widget.setStyleSheet(RS.sidebar_widget())
        sidebar_widget.setLayout(sidebar)
        sidebar_widget.setMinimumWidth(scale_value(260, min_ratio=0.5))
        sidebar_widget.setMaximumWidth(scale_value(420, min_ratio=0.6, max_ratio=1.5))
        sidebar_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        content_layout.addWidget(sidebar_widget, 2)  # Stretch 2: sidebar/center/info = 2:5:2

        # Sidebar başlığı
        sidebar_title = QLabel("Sistem Parametreleri")
        # Responsive title styling
        title_font_size = get_responsive_font_size(18)
        sidebar_title.setStyleSheet(RS.sidebar_title())
        sidebar.addWidget(sidebar_title)

        # Scroll destekli giriş + bilgi paneli
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet(RS.scroll_area())
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        scroll_content = QWidget()
        # Şeffaf arka plan: sidebar_widget gradient'ı scroll alanından sızmasın
        scroll_content.setStyleSheet("background: transparent;")
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setSpacing(get_responsive_spacing(6))
        scroll_layout.setContentsMargins(scale_value(2), 0, scale_value(2), scale_value(4))
        scroll_area.setWidget(scroll_content)
        sidebar.addWidget(scroll_area, stretch=1)

        # Gateway Durum Paneli (LattePanda)  [separator kaldırıldı — boşluk kaynağıydı]
        self.gateway_status_widget = GatewayStatusWidget()
        scroll_layout.addWidget(self.gateway_status_widget)
        
        # Gateway servis sinyallerini widget'a bağla
        if hasattr(self, 'network_monitor') and self.network_monitor:
            self.network_monitor.network_status_updated.connect(self.gateway_status_widget.update_network_status)
        if hasattr(self, 'mosquitto_manager') and self.mosquitto_manager:
            self.mosquitto_manager.status_changed.connect(
                self.gateway_status_widget.update_broker_status
            )
            self.mosquitto_manager.bridge_status_changed.connect(
                self.gateway_status_widget.update_bridge_status
            )
        
        # BLE Cihaz Ekle butonu
        ble_add_btn = QPushButton("➕ Cihaz Ekle (BLE)")
        ble_btn_font_size = get_responsive_font_size(13)
        ble_add_btn.setStyleSheet(RS.ble_add_btn())
        ble_add_btn.clicked.connect(self._open_ble_provision_dialog)
        scroll_layout.addWidget(ble_add_btn)
        
        # Ayırıcı çizgi (gateway ile ESP arası)
        separator_gw = QWidget()
        _sep_gw_h = max(1, int(2 * (get_screen_info()[2])))
        separator_gw.setStyleSheet(RS.separator())
        separator_gw.setMinimumHeight(_sep_gw_h)
        separator_gw.setMaximumHeight(_sep_gw_h * 2)
        separator_gw.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        scroll_layout.addWidget(separator_gw)
        
        # ESP Bağlantı Durumu Paneli
        self.create_esp_status_panel(scroll_layout)

        # Ayırıcı çizgi
        separator2 = QWidget()
        _sep2_margin = scale_margins(separator2, 20)
        _sep2_h = max(1, int(2 * (get_screen_info()[2])))
        separator2.setStyleSheet(f"background: #6c2b8f; margin: {_sep2_margin}px 0;")
        separator2.setMinimumHeight(_sep2_h)
        separator2.setMaximumHeight(_sep2_h * 2)
        separator2.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        scroll_layout.addWidget(separator2)

        # 2. Sistem Parametreleri
        param_title = QLabel("⚙️ Hasta Kaydı")
        param_title_font_size = get_responsive_font_size(16)
        param_title.setStyleSheet(RS.param_title())
        scroll_layout.addWidget(param_title)

        param_labels = [
            "Hayvanın Adı","Hayvanın Türü", "Hayvanın Irkı", "Hayvanın Yaşı"," Hayvanın Ağırlığı","Hayvanın Sahibi","Veteriner İletişim Bilgileri"
        ]

        self.input_fields = []
        self.validation_labels = []  # Validasyon mesajları için label'lar
        self.validator = PatientInputValidator()  # Validator instance

        for label in param_labels:
            vbox = QVBoxLayout()
            vbox.setSpacing(get_responsive_spacing(4))
            _vbox_bm = scale_value(8)
            vbox.setContentsMargins(0, 0, 0, _vbox_bm)
            lbl = QLabel(label)
            lbl.setStyleSheet(RS.field_label())

            field = QLineEdit()
            field.setPlaceholderText("Değer girin...")
            field.setStyleSheet(RS.line_edit())
            _fh = max(32, int(36 * (get_screen_info()[2])))
            field.setMinimumHeight(_fh)
            field.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            
            # Validasyon mesajı label'ı
            validation_label = QLabel("")
            validation_label.setStyleSheet(RS.validation_label_inline())
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
        # NEDEN: 💾 emojisi Qt emoji fallback fontunu tetikler → metin yüksekliği 2x olur
        # ÇÖZÜM: emoji QIcon olarak render edilir, metin temiz kalır
        save_patient_btn = QPushButton(" Hastayı Kaydet")
        _save_icon_sz = max(20, scale_value(24))
        save_patient_btn.setIcon(_render_emoji_icon("💾", _save_icon_sz))
        save_patient_btn.setIconSize(QSize(_save_icon_sz, _save_icon_sz))
        _save_min_h = max(60, scale_value(68))
        save_patient_btn.setMinimumHeight(_save_min_h)
        save_btn_font_size = get_responsive_font_size(16)
        save_btn_padding_h = scale_margins(save_patient_btn, 24)
        save_btn_padding_v = scale_margins(save_patient_btn, 12)
        save_btn_margin = scale_margins(save_patient_btn, 10)
        save_patient_btn.setStyleSheet(RS.save_patient_btn())
        save_patient_btn.clicked.connect(self.save_patient)
        scroll_layout.addWidget(save_patient_btn)
        self.save_patient_btn = save_patient_btn

        # ── Bottom navigation bar ───────────────────────────────────────────────────────
        nav_widget = QWidget()
        nav_bar = QHBoxLayout()
        _nav_side_m = scale_margins(nav_widget, 12)
        _nav_v_m    = scale_margins(nav_widget, 8)  # artırıldı: metin kesilmesini önler
        nav_bar.setContentsMargins(_nav_side_m, _nav_v_m, _nav_side_m, _nav_v_m)
        nav_bar.setSpacing(get_responsive_spacing(2))
        nav_widget.setStyleSheet(RS.nav_widget())
        nav_widget.setLayout(nav_bar)
        # setFixedHeight: bar, pencere boyutu ne olursa olsun sabit yükseklikte kalır
        # 80px: emoji QIcon + metin için yeterli nefes alanı (önceki 72px metni kesiyordu)
        _nav_h = scale_value(80, min_ratio=0.75, max_ratio=1.4)
        nav_widget.setFixedHeight(_nav_h)
        nav_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        # (emoji, etiket, slot) — emoji QIcon olarak render edilir, metin LINE-HEIGHT'ı etkilemez
        nav_items_def = [
            ("📈", "Sensör Verisi",  self.open_sensor_data_window),
            ("🎛", "Seans Kontrol",  self.open_unified_control),
            ("🗺", "Dijital İkiz",   self.open_digital_twin_window),
            ("🎮", "Terapi Sim.",    self.open_dema_simulator_window),
            ("📊", "Performans",     self.open_kpi_dashboard),
            ("📋", "Seans Geçmişi",  self.open_treatment_history),
        ]
        _icon_sz = max(18, scale_value(22))
        self.nav_buttons = []
        for emoji, text, slot in nav_items_def:
            btn = QPushButton(text)
            btn.setIcon(_render_emoji_icon(emoji, _icon_sz))
            btn.setIconSize(QSize(_icon_sz, _icon_sz))
            btn.setStyleSheet(RS.nav_btn())
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            btn.clicked.connect(slot)
            nav_bar.addWidget(btn)
            self.nav_buttons.append(btn)
        self._nav_widget_ref = nav_widget          # resize'da erişim için
        main_layout.addWidget(nav_widget)

        # ── Custom status bar (native statusBar yerine — örtüşme sorununu önler) ──
        self._custom_status_bar = QLabel("Sürücü Bağlantısı Bekleniyor...")
        _csb_fs = get_responsive_font_size(11)
        _csb_ph = scale_value(10)
        _csb_pv = scale_value(2)
        self._custom_status_bar.setStyleSheet(
            f"color: #aaa;"
            f"background: #1a1230;"
            f"padding: {_csb_pv}px {_csb_ph}px;"
            f"font-size: {_csb_fs}px;"
            f"border-top: 1px solid rgba(255,255,255,0.08);"
        )
        self._custom_status_bar.setFixedHeight(scale_value(22, min_ratio=0.7, max_ratio=1.3))
        self._custom_status_bar.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        main_layout.addWidget(self._custom_status_bar)

        # 2. Smart Treatment Card
        self.smart_treatment_card = QWidget()
        card_padding_h = scale_margins(self.smart_treatment_card, 16)
        card_padding_v = scale_margins(self.smart_treatment_card, 18)
        self.smart_treatment_card.setStyleSheet(RS.treatment_card())
        smart_treatment_layout = QVBoxLayout(self.smart_treatment_card)
        smart_treatment_layout.setSpacing(get_responsive_spacing(5))

        st_title = QLabel("~ Aktif Seans")
        st_title_font_size = get_responsive_font_size(14)
        st_title.setStyleSheet(RS.treatment_card_title())
        smart_treatment_layout.addWidget(st_title)

        def make_row(label_text, value_text, value_color="#fff", value_size="14px"):
            row = QHBoxLayout()
            label = QLabel(label_text)
            row_font_size = get_responsive_font_size(14)
            label.setStyleSheet(RS.treatment_row_label())
            # value_size parametresi de responsive yap
            if value_size.endswith("px"):
                value_size_num = int(value_size[:-2])
                value_size_responsive = get_responsive_font_size(value_size_num)
                value_size = f"{value_size_responsive}px"
            value = QLabel(
                f"<span style='color:{value_color}; font-weight:bold; font-size:{value_size};'>{value_text}</span>")
            value.setStyleSheet(RS.treatment_row_value())
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
        st_time_icon.setStyleSheet(RS.treatment_time_icon())
        st_time_label = QLabel("Süre:")
        st_time_label.setStyleSheet(RS.treatment_row_label())
        self.st_time_value = QLabel("0/0 dk")
        self.st_time_value.setStyleSheet(RS.treatment_row_value())
        st_time_row.addWidget(st_time_icon)
        st_time_row.addWidget(st_time_label)
        st_time_row.addStretch(1)
        st_time_row.addWidget(self.st_time_value)
        smart_treatment_layout.addLayout(st_time_row)

        self.st_progress = QProgressBar()
        _progress_h = max(10, int(14 * (get_screen_info()[2])))
        self.st_progress.setMinimumHeight(_progress_h)
        self.st_progress.setMaximumHeight(int(_progress_h * 1.5))
        self.st_progress.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.st_progress.setMinimum(0)
        self.st_progress.setMaximum(100)
        self.st_progress.setValue(0)
        self.st_progress.setTextVisible(True)
        self.st_progress.setFormat("%p%")  # Yüzde gösterimi
        self.st_progress.setStyleSheet(RS.progress_bar())
        smart_treatment_layout.addWidget(self.st_progress)

        st_status_row = QHBoxLayout()
        self.st_status = QLabel(RS.initial_status_html())
        self.st_status.setStyleSheet(RS.initial_status_badge())
        st_status_row.addWidget(self.st_status)
        st_status_row.addStretch(1)
        smart_treatment_layout.addLayout(st_status_row)

        scroll_layout.addWidget(self.smart_treatment_card)

        # 3. KPI Card
        kpi_card = QWidget()
        kpi_card.setStyleSheet("background: transparent;")
        kpi_layout = QVBoxLayout(kpi_card)
        kpi_layout.setContentsMargins(0, 0, 0, 0)
        kpi_layout.setSpacing(get_responsive_spacing(8))

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

        # scroll_area.setWidget(scroll_content) ve sidebar.addWidget(scroll_area) zaten yukarıda yapıldı.

        # Center: Coil control panel
        center_panel = QWidget()
        center_panel.setStyleSheet(RS.center_panel())
        center_panel_layout = QVBoxLayout(center_panel)
        _cm = scale_margins(center_panel, 32)
        center_panel_layout.setContentsMargins(_cm, _cm, _cm, _cm)
        center_panel_layout.setSpacing(get_responsive_spacing(24))

        # --- Sistem Durumu Başlık ---
        system_status_title = QLabel(RS.html_span('Sistem Durumu', base_pt=17))
        system_status_title.setAlignment(Qt.AlignmentFlag.AlignLeft)
        center_panel_layout.addWidget(system_status_title)

        # --- Durum Bilgileri Satırı ---
        status_row = QHBoxLayout()
        status_row.setSpacing(get_responsive_spacing(32))
        status_row.setContentsMargins(0, 0, 0, 0)

        def make_status_label(label, value, color):
            return QLabel(RS.status_make_html(label, value, color))



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
        self.plot_widget.setMinimumHeight(scale_value(200, min_ratio=0.5))
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
        coil_panel.setSpacing(get_responsive_spacing(18))
        coil_panel_title = QLabel(RS.html_span('Grafik Kontrol Paneli', base_pt=17))
        coil_panel.addWidget(coil_panel_title)

        # --- 8 Adet Bobin Butonu ---
        grid = QGridLayout()
        grid.setSpacing(get_responsive_spacing(18))
        self.coil_buttons = []

        # Create coil buttons first
        for i in range(8):
            btn = QPushButton(f"⚡ Bobin-{i + 1}")
            btn.setStyleSheet(RS.coil_btn())
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
        stop_btn.setStyleSheet(RS.stop_all_btn())
        stop_btn.setMinimumHeight(scale_value(80, min_ratio=0.5))
        stop_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        stop_btn.clicked.connect(self.send_global_stop_command)
        coil_panel.addWidget(stop_btn)

        center_panel_layout.addLayout(coil_panel)
        center_panel.setMinimumWidth(scale_value(400, min_ratio=0.5))
        center_panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        content_layout.addWidget(center_panel, stretch=5)  # Stretch 5: sidebar/center/info = 2:5:2

        # Right: Info panel
        info_panel = QWidget()
        info_panel.setStyleSheet(RS.info_panel())
        info_layout = QVBoxLayout(info_panel)
        _im = scale_margins(info_panel, 22)
        info_layout.setContentsMargins(_im, _im, _im, _im)
        info_layout.setSpacing(get_responsive_spacing(12))

        info_title = QLabel(RS.html_span('Sistem Bilgileri', base_pt=17))
        info_layout.addWidget(info_title)

        # System Info Compact Card (vertical list, compact)
        system_info_card = QWidget()
        system_info_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        system_info_card.setMinimumWidth(scale_value(260, min_ratio=0.65))
        system_info_card.setMinimumHeight(scale_value(240, min_ratio=0.6))
        system_info_card.setStyleSheet(RS.system_info_card())

        system_info_layout = QVBoxLayout(system_info_card)
        # Responsive iç margin: card'ın QSS padding'i ile çakışmayı önler
        _si_m = scale_margins(system_info_card, 6)
        system_info_layout.setContentsMargins(_si_m, _si_m, _si_m, _si_m)
        system_info_layout.setSpacing(get_responsive_spacing(8))

        # ── Responsive add_info_row ───────────────────────────────────────────
        def add_info_row(label_text, value_label, value_style=None):
            """
            Her satırı QWidget pill kapsayıcıya sarar.
            Label: sol hizalı, pill arka planlı, elide ile kesilmez.
            Value: sağ hizalı, koyu pill arka planlı, elide ile kesilmez.
            """
            # Dış kapsayıcı widget (arka planlı satır)
            row_widget = QWidget()
            row_widget.setStyleSheet(RS.info_row_container())
            row_widget.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
            )
            _row_h = scale_value(36, min_ratio=0.7, max_ratio=1.4)
            row_widget.setFixedHeight(_row_h)

            row = QHBoxLayout(row_widget)
            _rh_m = scale_margins(row_widget, 4)
            row.setContentsMargins(_rh_m, 0, _rh_m, 0)
            row.setSpacing(get_responsive_spacing(6))

            # Sol: label pill
            label = QLabel(label_text)
            label.setStyleSheet(RS.info_row_label_pill())
            label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            # Uzun metinlerin kesilmesi için minimum + maximum genişlik
            _lbl_min = scale_value(120, min_ratio=0.6)
            _lbl_max = scale_value(200, min_ratio=0.6)
            label.setMinimumWidth(_lbl_min)
            label.setMaximumWidth(_lbl_max)
            label.setWordWrap(False)

            # Sağ: value pill
            value_label.setStyleSheet(value_style or RS.info_row_value_pill())
            value_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)
            value_label.setWordWrap(False)
            # Cihaz ID gibi uzun değerler için elide
            _val_max = scale_value(220, min_ratio=0.5)
            value_label.setMaximumWidth(_val_max)

            row.addWidget(label, stretch=0)
            row.addStretch(1)
            row.addWidget(value_label, stretch=0)

            if not hasattr(self, 'info_rows'):
                self.info_rows = []
            self.info_rows.append(row_widget)
            system_info_layout.addWidget(row_widget)

        # Dinamik değer alanları
        self.working_time_label = QLabel()
        self.total_treatment_label = QLabel("0 seans")

        # Bilgi satırları
        add_info_row("🔄 Yazılım Sürümü:", QLabel(f"v{self.SOFTWARE_VERSION}"), RS.info_row_version_px())
        add_info_row("💻 Donanım Sürümü:", QLabel("HW-2025.1"), RS.info_row_version_px())
        add_info_row("📅 Son Güncelleme:", QLabel("8.11.2025"), RS.info_row_version_px())
        device_id_val = self.device_id if hasattr(self, 'device_id') else "PEMF-001-2025"
        add_info_row("🆔 Cihaz ID:", QLabel(device_id_val), RS.info_row_version_px())
        add_info_row("⏳ Çalışma Süresi:", self.working_time_label, RS.info_row_version_px())
        add_info_row("📈 Toplam Seans:", self.total_treatment_label, RS.info_row_version_px())

        info_layout.addWidget(system_info_card, stretch=0)

        # Çalışma süresi güncelle
        self.update_working_time_label()
        
        # Toplam tedavi sayısını güncelle
        self.update_total_treatment_count()

        # Bildirim Kartı
        notification_card = QWidget()
        notification_card.setStyleSheet(RS.notification_card())
        notification_card_layout = QVBoxLayout(notification_card)
        notification_card_layout.setContentsMargins(0, 0, 0, 0)
        notification_card_layout.setSpacing(get_responsive_spacing(10))

        notification_title = QLabel("🔔 Bildirimler")
        notification_title.setStyleSheet(RS.notification_title())
        notification_card_layout.addWidget(notification_title)

        self.notification_panel = NotificationPanel(self)
        self.notification_panel.setStyleSheet(RS.notification_panel_inner())
        notification_card_layout.addWidget(self.notification_panel, stretch=1)

        # Placeholder shown when panel has no messages
        self._notif_empty_lbl = QLabel("Henüz bildirim yok")
        self._notif_empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._notif_empty_lbl.setStyleSheet(RS.empty_state_label())
        self._notif_empty_lbl.setWordWrap(True)
        notification_card_layout.addWidget(self._notif_empty_lbl, stretch=1)

        notification_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.notification_panel.setMinimumHeight(scale_value(80, min_ratio=0.5))
        self.notification_panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        info_layout.addWidget(notification_card, stretch=1)

        info_panel.setMinimumWidth(scale_value(260, min_ratio=0.5))
        info_panel.setMaximumWidth(scale_value(420, min_ratio=0.6, max_ratio=1.5))
        info_panel.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        content_layout.addWidget(info_panel, stretch=2)  # Stretch 2: sidebar/center/info = 2:5:2

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
        # config.json -> timers -> connection_check_ms (default 5000 for LattePanda)
        _conn_ms = 5000
        try:
            import json as _j, os as _o
            _cp = _o.path.join(_o.path.dirname(_o.path.abspath(__file__)), '..', 'config', 'config.json')
            with open(_cp, 'r', encoding='utf-8') as _f:
                _conn_ms = max(3000, int(_j.load(_f).get('timers', {}).get('connection_check_ms', 5000)))
        except Exception:
            pass
        self.connection_check_timer.start(_conn_ms)
        
        # ✅ ESP stale data cleanup timer
        self.esp_cleanup_timer = QTimer(self)
        self.esp_cleanup_timer.timeout.connect(self._cleanup_stale_esp_devices)
        self.esp_cleanup_timer.start(_conn_ms)  # Connection check ile aynı interval
        
        # Connect coil_control_requested signal to handle_coil_control_request slot
        # Bu signal sadece GUI içi kullanım için (UnifiedControlWindow'dan komut almak için)
        self.coil_control_requested.connect(self.handle_coil_control_request, Qt.ConnectionType.QueuedConnection)
        self.batch_coil_control_requested.connect(self.handle_batch_coil_control_request, Qt.ConnectionType.QueuedConnection)
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

    def _init_gateway_services(self):
        """
        LattePanda gateway servislerini başlatır:
        - MosquittoManager: Yerel broker yaşam döngüsü
        - NetworkMonitor: Internet/hotspot durum takibi
        - DiscoveryServiceThread: Android/cihaz keşif servisi (UDP 5051)
        """
        try:
            # Mosquitto Manager
            self.mosquitto_manager = MosquittoManager()
            self.mosquitto_manager.status_changed.connect(self._on_mosquitto_status_changed)
            self.mosquitto_manager.error_occurred.connect(
                lambda e: self.logger.warning(f"Mosquitto hatası: {e}")
            )
            self.mosquitto_manager.start_monitoring()
            # Vet kullanıcıları servis yönetimi yapmasın diye broker'ı otomatik ayağa kaldır.
            self.mosquitto_manager.ensure_running()
            self.logger.info("MosquittoManager başlatıldı (auto-start etkin)")
            
            # Python MQTT Bridge (Mosquitto native bridge TLS bug workaround)
            self.mosquitto_manager.start_bridge()
            self.logger.info("Python MQTT Bridge başlatıldı")
        except Exception as e:
            self.mosquitto_manager = None
            self.logger.warning(f"MosquittoManager başlatılamadı: {e}")

        try:
            # Network Monitor
            self.network_monitor = NetworkMonitor()
            self.network_monitor.gateway_mode_changed.connect(
                lambda mode: self.logger.info(f"Gateway modu: {mode}")
            )
            self.network_monitor.start_monitoring()
            self.logger.info("NetworkMonitor başlatıldı")
        except Exception as e:
            self.network_monitor = None
            self.logger.warning(f"NetworkMonitor başlatılamadı: {e}")

        try:
            # Discovery Service Thread (UDP broadcast - Android/ESP keşif)
            # Discovery dış istemcilere broker IP'si duyurur → hotspot IP kullanılmalı
            # GUI'nin kendisi 127.0.0.1'e bağlanır (config.json local_broker)
            # ama ESPs/Android 192.168.137.1 (hotspot gateway) üzerinden bağlanır
            discovery_mqtt_host = "192.168.137.1"  # Hotspot gateway IP (dış istemciler için)
            mqtt_port = 1883
            mqtt_tls = False
            try:
                config_path = Path(__file__).parent.parent / "config" / "config.json"
                with open(config_path, 'r', encoding='utf-8') as f:
                    cfg = json.load(f)
                local_b = cfg.get('mqtt', {}).get('local_broker', {})
                mqtt_port = local_b.get('broker_port', mqtt_port)
                mqtt_tls = local_b.get('use_tls', mqtt_tls)
            except Exception:
                pass

            self.discovery_thread = DiscoveryServiceThread(
                mqtt_broker_host=discovery_mqtt_host,
                mqtt_broker_port=mqtt_port,
                mqtt_broker_tls=mqtt_tls
            )
            self.discovery_thread.start()
            self.logger.info("DiscoveryServiceThread başlatıldı (UDP 5051)")
        except Exception as e:
            self.discovery_thread = None
            self.logger.warning(f"DiscoveryServiceThread başlatılamadı: {e}")

        try:
            self.db_maintenance_service = DBMaintenanceService(app_data_dir=self.app_data_dir)
            self.db_maintenance_service.maintenance_failed.connect(
                lambda err: self.logger.warning(f"DBMaintenanceService: {err}")
            )
            self.db_maintenance_service.disk_space_critical.connect(
                lambda status: self.notification_panel.add_notification(
                    f"⚠️ Disk alanı kritik: {status.get('free_mb')}MB kaldı. Yazma işlemleri durabilir.",
                    "error"
                ) if hasattr(self, 'notification_panel') else None
            )
            self.db_maintenance_service.start()
            self.logger.info("DBMaintenanceService başlatıldı")
        except Exception as e:
            self.db_maintenance_service = None
            self.logger.warning(f"DBMaintenanceService başlatılamadı: {e}")

        try:
            # Hotspot Manager — Windows Mobile Hotspot otomatik açma
            self.hotspot_manager = HotspotManager()
            self.hotspot_manager.error_occurred.connect(
                lambda e: self.logger.warning(f"Hotspot: {e}")
            )
            self.hotspot_manager.hotspot_enabled.connect(
                lambda ok: self.logger.info(f"Hotspot durumu: {'aktif' if ok else 'kapalı'}")
            )
            # Hotspot kapalıysa açmayı dene
            self.hotspot_manager.enable_hotspot()
            self.logger.info("HotspotManager başlatıldı")
        except Exception as e:
            self.hotspot_manager = None
            self.logger.warning(f"HotspotManager başlatılamadı: {e}")

    def _on_mosquitto_status_changed(self, status: dict):
        """Durum loglarını tekrar etmeden sadece anlamlı değişikliklerde yaz."""
        try:
            bridge_stats = status.get('bridge_stats', {}) if isinstance(status, dict) else {}
            signature = (
                bool(status.get('running', False)),
                bool(status.get('bridge_connected', False)),
                bool(status.get('bridge_running', False)),
                bool(status.get('port_open', False)),
                bool(bridge_stats.get('local_connected', False)),
                bool(bridge_stats.get('cloud_connected', False)),
                bool(bridge_stats.get('bridge_active', False)),
            )

            if getattr(self, '_last_mosquitto_status_signature', None) == signature:
                return

            self._last_mosquitto_status_signature = signature
            self.logger.info(
                "Mosquitto broker durumu: running=%s, bridge_connected=%s, bridge_running=%s, port_open=%s, local_connected=%s, cloud_connected=%s, bridge_active=%s",
                signature[0], signature[1], signature[2], signature[3], signature[4], signature[5], signature[6]
            )
        except Exception as e:
            self.logger.debug(f"Mosquitto status log dedupe fallback: {e}")

    def _open_ble_provision_dialog(self):
        """BLE Provisioning dialog penceresini aç."""
        try:
            dialog = BLEProvisionDialog(self)
            dialog.exec()
        except Exception as e:
            self.logger.error(f"BLE Provisioning dialog hatası: {e}")
            if hasattr(self, 'notification_panel'):
                self.notification_panel.add_notification(
                    f"BLE Provisioning açılamadı: {e}", "error"
                )

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

    class MqttConnectionThread(QThread):
        connection_result = pyqtSignal(bool)

        def __init__(self, obj, config_path, logger):
            super().__init__()
            self.obj = obj
            self.config_path = config_path
            self.logger = logger
            self._is_running = True

        def run(self):
            mqtt_config = {}
            try:
                import json
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                mqtt_config = config.get('mqtt', {})
            except Exception as e:
                self.logger.debug(f"Config okunamadi (fallback kullanilacak): {e}")

            mqtt_mode = mqtt_config.get('mode', 'hybrid')
            
            success = False

            if mqtt_mode in ['hybrid', 'local']:
                self.logger.info("=== LOKAL MQTT BROKER (EDGE) DENENIYOR ===")
                local_config = mqtt_config.get('local_broker', {})
                success = self._try_connect_broker_sync(
                    broker_url=local_config.get('broker_url', 'localhost'),
                    broker_port=local_config.get('broker_port', 1883),
                    broker_user=local_config.get('username', ''),
                    broker_pass=local_config.get('password', ''),
                    use_tls=local_config.get('use_tls', False),
                    broker_name="Local Broker (Mosquitto/LattePanda)",
                    timeout=5
                )

            if not success and mqtt_mode in ['hybrid', 'cloud'] and self._is_running:
                self.logger.info("=== CLOUD MQTT BROKER (YEDEK/UZAK) DENENIYOR ===")
                cloud_config = mqtt_config.get('cloud_broker', {})
                success = self._try_connect_broker_sync(
                    broker_url=cloud_config.get('broker_url', '8593bfdb2f324ad88d08b54b5e37c0a9.s1.eu.hivemq.cloud'),
                    broker_port=cloud_config.get('broker_port', 8883),
                    broker_user=cloud_config.get('username', 'afsuampemf'),
                    broker_pass=cloud_config.get('password', 'Pemf1234'),
                    use_tls=cloud_config.get('use_tls', True),
                    broker_name="Cloud Broker (HiveMQ)",
                    timeout=10
                )

            if not success and self._is_running:
                self.logger.error("=== MQTT BAGLANTI HATASI ===")
                self.logger.error("Hicbir MQTT broker'a baglanti saglanamadi!")
                self.logger.error("Sistem MQTT olmadan calisacak (sadece local arayuz modunda)")
            
            self.connection_result.emit(success)

        def _try_connect_broker_sync(self, broker_url, broker_port, broker_user, broker_pass, use_tls, broker_name, timeout=5):
            try:
                import time
                self.logger.info(f"[{broker_name}] Deneniyor: {broker_url}:{broker_port} (TLS: {use_tls})")
                
                # Sabit client_id kullanmak, aynı isimle zaten bağlı bir istemci varsa
                # broker tarafından zorla koparılmaya (client ID conflict) yol açar.
                # uuid ile her bağlantıya benzersiz bir kimlik atıyoruz.
                unique_client_id = f"pemf_gui_client_{uuid.uuid4().hex[:8]}"
                self.logger.debug(f"[{broker_name}] Kullanılan Client ID: {unique_client_id}")
                
                client = mqtt.Client(
                    mqtt.CallbackAPIVersion.VERSION2,
                    client_id=unique_client_id,
                    clean_session=True  # Benzersiz ID ile clean_session=True daha tutarlı çalışır
                )
                client.on_connect = self.obj.on_mqtt_connect
                client.on_message = self.obj.on_mqtt_message
                client.on_disconnect = self.obj.on_mqtt_disconnect
                client.on_subscribe = self.obj.on_mqtt_subscribe
                
                if broker_user and broker_pass:
                    client.username_pw_set(broker_user, broker_pass)
                
                if use_tls:
                    client.tls_set(
                        cert_reqs=ssl.CERT_REQUIRED,
                        tls_version=ssl.PROTOCOL_TLSv1_2
                    )
                
                self.obj.mqtt_client = client
                client.connect(broker_url, broker_port, 60)
                client.loop_start()
                
                start_time = time.monotonic()
                while time.monotonic() - start_time < timeout:
                    if not self._is_running:
                        return False
                    if self.obj.mqtt_connected_state:
                        self.logger.info(f"[{broker_name}] BAGLANTI BASARILI!")
                        return True
                    time.sleep(0.05)
                
                self.logger.warning(f"[{broker_name}] Timeout ({timeout}s), baglanti kurulamadi")
                self.obj._cleanup_mqtt_client()
                return False
                
            except Exception as e:
                self.logger.warning(f"[{broker_name}] Baglanti hatasi: {e}")
                self.obj._cleanup_mqtt_client()
                return False

        def stop(self) -> None:
            """
            Bağlantı döngüsünü durdurur.
            _is_running=False ile while döngüsünden çıkılır;
            requestInterruption() Qt'nun standart iptal mekanizmasını da tetikler.
            wait() çağrısı caller tarafından yapılmalıdır (closeEvent içinde).
            """
            self._is_running = False
            self.requestInterruption()

    def setup_mqtt_client(self):
        """
        MQTT istemcisini kurar.
        Config dosyasindaki (hybrid/local/cloud) moda gore baglanmayi dener.
        """
        self._cleanup_mqtt_client()
        config_path = Path(__file__).parent.parent / "config" / "config.json"
        
        self._mqtt_connection_thread = self.MqttConnectionThread(self, config_path, self.logger)
        self._mqtt_connection_thread.start()

    def on_mqtt_connect(self, client, userdata, flags, rc, properties=None):
        """
        MQTT broker'a bağlantı kurulduğunda çalışır.
        """
        if rc == 0:
            self.mqtt_mutex.lock()
            self.mqtt_connected_state = True
            self.mqtt_mutex.unlock()
            
            # Reset retry count AND stop reconnect timer unconditionally
            self.mqtt_retry_count = 0
            self.mqtt_retry_delay = 2000
            
            # Reconnect timer'ı durdur (callback thread'inden dogrudan timer erisimi yapma)
            from PyQt6.QtCore import QMetaObject
            QMetaObject.invokeMethod(
                self.mqtt_reconnect_timer,
                "stop",
                Qt.ConnectionType.QueuedConnection
            )
            
            self.logger.info("MQTT broker'a başarıyla bağlanıldı")
            
            # MQTT connected signal'ı emit et (UnifiedControlWindow için)
            self.mqtt_connected.emit()
            
            # Notification panel'e bildir
            if hasattr(self, 'notification_panel'):
                import PyQt6.QtCore as qtcore
                qtcore.QTimer.singleShot(0, lambda: self.notification_panel.add_notification(
                    "Cihaz bağlantısı kuruldu", 
                    "success"
                ))
            
            # Subscribe to ESP8266 sensor and status topics for all coils
            result1, mid1 = client.subscribe("pemf/coil/+/sensors")
            result2, mid2 = client.subscribe("pemf/coil/+/status")
            result3, mid3 = client.subscribe("pemf/coil/+/alarm")  # Alarm topic'i ekle
            result4, mid4 = client.subscribe("pemf/coil/+/ack")  # ACK topic'i ekle (GUI Stability Fix #4)
            result5, mid5 = client.subscribe("pemf/coil/+/events")  # WiFi/MQTT event topic'i ekle
            result6, mid6 = client.subscribe("pemf/system/session/control")  # Android session control
            result7, mid7 = client.subscribe("pemf/coil/+/system/log")  # ESP32 system log (WARN/ERROR)
            result8, mid8 = client.subscribe("pemf/bridge/status")  # Mosquitto bridge durumu
            
            self.logger.info("MQTT topic'lere abone olundu (sensors, status, alarm, ack, events, session/control, system/log, bridge/status)")
            
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
        
        def handle_disconnect_loop():
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
                self.esp_status_buffer_mutex.lock()
                try:
                    if hasattr(self, 'esp_last_seen'):
                        self.esp_last_seen.pop(coil_id, None)
                finally:
                    self.esp_status_buffer_mutex.unlock()

        import PyQt6.QtCore as qtcore
        qtcore.QTimer.singleShot(0, handle_disconnect_loop)
        
        # MQTT disconnected signal'ı emit et (UnifiedControlWindow için)
        self.mqtt_disconnected.emit()
        
        # Notification panel'e bildir
        if hasattr(self, 'notification_panel'):
            import PyQt6.QtCore as qtcore
            qtcore.QTimer.singleShot(0, lambda: self.notification_panel.add_notification(
                "Sinyal akışı koptu, yeniden bağlantı kuruluyor...", 
                "warning"
            ))
        
        # Auto-reconnect başlat (GUI Stability Fix #1)
        # MQTT callback thread'inden QTimer metotlarina dogrudan erisme
        self.mqtt_retry_count = 0
        self.mqtt_retry_delay = 2000
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

    def _append_graph_data(self, coil_id_int: int, mag_value: float, temp_value: float):
        """
        Grafik deque'larına thread-safe veri ekler.
        Sadece /sensors handler'dan çağrılmalıdır.
        """
        if self.graph_data_collection_active and self.is_coil_active(coil_id_int):
            if self.graph_start_time is None:
                self.graph_start_time = time.time()
            current_t = time.time() - self.graph_start_time

            self.graph_data_mutex.lock()
            try:
                self.last_known_mag[coil_id_int] = mag_value
                self.last_known_temp[coil_id_int] = temp_value
                if not hasattr(self, 'per_coil_time_data'):
                    self.per_coil_time_data = {i: deque(maxlen=2000) for i in range(1, 9)}
                self.per_coil_time_data[coil_id_int].append(current_t)
                self.graph_magnetic_field_data[coil_id_int].append(mag_value)
                self.graph_temperature_data[coil_id_int].append(temp_value)
            finally:
                self.graph_data_mutex.unlock()
        else:
            self.graph_data_mutex.lock()
            try:
                self.last_known_mag[coil_id_int] = mag_value
                self.last_known_temp[coil_id_int] = temp_value
            finally:
                self.graph_data_mutex.unlock()

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
                # Retained messages - ignore them for any coil-specific topic
                # They represent old state (past connections), not current ESP status
                if topic.startswith('pemf/coil/'):
                    if self.logger.isEnabledFor(logging.DEBUG):
                        self.logger.debug("Ignoring retained message from %s (stale data)", topic)
                    return
            
            # Clean logging: Only debug level for MQTT messages
            # Performans optimizasyonu: Lazy evaluation kullan (%s formatı)
            if self.logger.isEnabledFor(logging.DEBUG):
                self.logger.debug("MQTT message received: %s (retained=%s)", topic, is_retained)
            
            # JSON Parse Cache (Performance Optimization)
            payload_hash = hash(payload)
            self.mqtt_mutex.lock()
            try:
                data = self._json_parse_cache.get(payload_hash)
            finally:
                self.mqtt_mutex.unlock()

            if data is None:
                # Cache miss - parse and store
                data = self._parse_json_with_fallback(payload, topic)
                if data is not None:
                    self.mqtt_mutex.lock()
                    try:
                        # Baska bir callback bu arada ayni payload'i eklemis olabilir
                        cached = self._json_parse_cache.get(payload_hash)
                        if cached is None:
                            # LRU-like cache: Remove oldest entry if cache is full
                            if len(self._json_parse_cache) >= self._json_cache_max_size:
                                # Drop oldest 20% to avoid doing this every message once full
                                drop_count = max(1, self._json_cache_max_size // 5)
                                keys_to_drop = list(self._json_parse_cache.keys())[:drop_count]
                                for k in keys_to_drop:
                                    del self._json_parse_cache[k]
                            self._json_parse_cache[payload_hash] = data
                        else:
                            data = cached
                    finally:
                        self.mqtt_mutex.unlock()
            
            # If still no data, skip message
            if data is None:
                return
            
            # --- Non-coil topics: handle before coil extraction ---
            # Bridge status (payload is plain "1"/"0", not JSON dict)
            if topic == "pemf/bridge/status":
                try:
                    # Retained bridge status onceki calismadan stale gelebilir;
                    # gercek durum MosquittoManager/Python bridge tarafindan dogrulanir.
                    if is_retained:
                        if self.logger.isEnabledFor(logging.DEBUG):
                            self.logger.debug("Ignoring retained bridge status message")
                        return

                    bridge_connected = payload.strip() in ('1', 'true', 'connected')
                    previous_bridge = getattr(self, '_last_bridge_status_topic_value', None)
                    if previous_bridge != bridge_connected:
                        self._last_bridge_status_topic_value = bridge_connected
                        self.logger.info(f"Bridge durumu: {'bağlı' if bridge_connected else 'bağlı değil'}")
                    
                    if hasattr(self, 'gateway_status_widget'):
                        QTimer.singleShot(0, lambda c=bridge_connected: self.gateway_status_widget.update_bridge_status(c))
                    if hasattr(self, 'mosquitto_manager') and self.mosquitto_manager:
                        QTimer.singleShot(0, lambda c=bridge_connected: self.mosquitto_manager.update_bridge_status(c))
                    if hasattr(self, 'notification_panel') and previous_bridge != bridge_connected:
                        if bridge_connected:
                            QTimer.singleShot(0, lambda: self.notification_panel.add_notification(
                                "☁️ Cloud bridge bağlantısı kuruldu", "success"))
                        else:
                            QTimer.singleShot(0, lambda: self.notification_panel.add_notification(
                                "☁️ Cloud bridge bağlantısı kesildi (offline mod)", "warning"))
                except Exception as e:
                    self.logger.error(f"Bridge status message handling error: {e}", exc_info=True)
                return
            
            # Session control (from Android)
            if topic == "pemf/system/session/control":
                try:
                    if not isinstance(data, dict):
                        self.logger.warning(f"Session control: beklenen dict, gelen {type(data).__name__}")
                        return
                    self._handle_session_control(data)
                except Exception as e:
                    self.logger.error(f"Session control message handling error: {e}", exc_info=True)
                return
            
            # --- Coil topics: pemf/coil/{id}/... ---
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

                    # Active session varsa sensör örneğini local DB'ye batch ekle
                    self._persist_sensor_sample_if_session_active(coil_id, data)
                    
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
                        pwm_duty_value = data.get('pwm_duty', 0)
                        
                        # CRITICAL FIX (Bug 3): Global dict yerine per-coil dict kullanılmalı
                        if not hasattr(self, 'latest_sensor_data') or not isinstance(self.latest_sensor_data, dict) or 'coil_id' in self.latest_sensor_data:
                            # Eski yapıdan yeni yapıya geçiş (sadece ilk seferde)
                            self.latest_sensor_data = {}
                            
                        self.latest_sensor_data[coil_id] = {
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
                        self._pending_render_receive_ts.append(mqtt_receive_time)
                    finally:
                        self.mqtt_mutex.unlock()
                    
                    # Sensor verilerini SensorDataWindow'a gönder (with safety check)
                    try:
                        self.sensor_data_received.emit(coil_id, data)
                    except RuntimeError:
                        # Object deleted during emission, return silently
                        return
                    
                    # UnifiedControlWindow'a sadece sıcaklık değeri gönder (büyük dict yerine)
                    temp_value = data.get('object_temp', 0.0)
                    try:
                        temp_value = float(temp_value)
                    except (TypeError, ValueError):
                        temp_value = 0.0
                    if hasattr(self, 'unified_control_window') and self._is_window_alive(self.unified_control_window):
                        try:
                            self.unified_control_window._safe_update_temperature_signal.emit(int(coil_id), temp_value)
                        except (RuntimeError, ValueError, TypeError):
                            pass
                    
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
                    self.esp_status_buffer_mutex.lock()
                    try:
                        if hasattr(self, 'esp_last_seen'):
                            self.esp_last_seen[coil_id] = time.time()
                            try:
                                self.esp_last_seen[int(coil_id)] = time.time()
                            except ValueError:
                                pass
                    finally:
                        self.esp_status_buffer_mutex.unlock()
                    
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
                            
                            def update_kpi_thread_safe():
                                self.total_energy_wh += energy_increment_wh
                                self.update_kpi_energy(self.total_energy_wh)
                            
                            # KPI'yı güncelle
                            QTimer.singleShot(0, update_kpi_thread_safe)
                    except Exception as e:
                        if self.logger.isEnabledFor(logging.DEBUG):
                            self.logger.debug(f"Enerji hesaplama hatası: {e}")
                
                elif topic.endswith('/events'):
                    # Handle event messages (e.g., WiFi Disconnected)
                    # Payload example: {"type":"wifi_disconnected", "message":"Exiting Cloud Mode"}
                    event_type = data.get('type') or data.get('event_type', 'unknown')
                    message = data.get('message', '')
                    
                    if event_type == 'wifi_disconnected' or event_type == 'offline':
                        # Alert User via Notification Center or Popup
                        if event_type == 'offline':
                            error_msg = f"COIL {coil_id} BAĞLANTISI KOPTU!\nCihaz muhtemelen kapandı veya gücü kesildi (LWT Tetiklendi).\nLütfen cihazı kontrol edin."
                        else:
                            error_msg = f"COIL {coil_id} WiFi bağlantısı kesildi.\nCihaz yeniden bağlanmayı deniyor."
                            if message:
                                error_msg += f"\nDetay: {message}"
                        
                        self.logger.warning(f"Device {coil_id} went offline ({event_type}).")

                        # Aynı coil/event için kısa sürede tekrar popup göstermeyi engelle.
                        if not hasattr(self, '_last_offline_event_notice'):
                            self._last_offline_event_notice = {}
                        notice_key = f"{coil_id}:{event_type}"
                        now_ts = time.time()
                        last_ts = float(self._last_offline_event_notice.get(notice_key, 0.0))
                        should_notify = (now_ts - last_ts) > 30.0
                        if should_notify:
                            self._last_offline_event_notice[notice_key] = now_ts
                        
                        # Eğer GUI thread içindeysek direkt göster, değilse signal
                        # on_mqtt_message, MQTT thread'inde çalışır -> Signal şart
                        if should_notify and hasattr(self, 'error_occurred'):
                            try:
                                self.error_occurred.emit(error_msg)
                            except RuntimeError:
                                pass
                                
                        # ESP durum panelini güncelle
                        status_data = {
                            'coil_id': coil_id,
                            'wifi_connected': False,
                            'wifi_ssid': '',
                            'wifi_ip': ''
                        }
                        try:
                            self.esp_status_received.emit(coil_id, status_data)
                        except RuntimeError:
                            pass
                            
                    elif event_type == 'wifi_connected':
                        # WiFi bağlantısı kuruldu
                        wifi_ssid = data.get('wifi_ssid', '')
                        wifi_ip = data.get('wifi_ip', '')
                        self.logger.info("Coil %s WiFi bağlantısı kuruldu: %s (%s)", coil_id, wifi_ssid, wifi_ip)
                        if hasattr(self, 'notification_panel'):
                            QTimer.singleShot(0, lambda: self.notification_panel.add_notification(f"✅ Coil {coil_id} WiFi bağlantısı kuruldu: {wifi_ssid}\n" f"IP: {wifi_ip}", "success"))
                        # ESP durum panelini güncelle
                        status_data = {
                            'coil_id': coil_id,
                            'wifi_connected': True,
                            'wifi_ssid': wifi_ssid,
                            'wifi_ip': wifi_ip
                        }
                        try:
                            self.esp_status_received.emit(coil_id, status_data)
                        except RuntimeError:
                            pass
                            
                    elif event_type == 'mqtt_connected':
                        # MQTT bağlantısı kuruldu
                        self.logger.info("Coil %s MQTT broker'a bağlandı", coil_id)
                        # ESP durum panelini güncelle
                        status_data = {
                            'coil_id': coil_id,
                            'mqtt_connected': True
                        }
                        try:
                            self.esp_status_received.emit(coil_id, status_data)
                        except RuntimeError:
                            pass
                            
                    elif event_type == 'selftest_ok':
                        self.logger.info(f"Coil {coil_id} Self-Test Basarili")
                        data['event_type'] = 'selftest_ok'
                        try:
                            self.esp_status_received.emit(coil_id, data)
                        except RuntimeError:
                            pass
                            
                    elif event_type == 'selftest_fail':
                        fail_message = data.get('message', 'Self-Test esik degeri saglanamadi')
                        self.logger.warning(f"Coil {coil_id} Self-Test Basarisiz: {fail_message}")
                        data['event_type'] = 'selftest_fail'
                        try:
                            self.esp_status_received.emit(coil_id, data)
                        except RuntimeError:
                            pass

                    elif event_type == 'device_ready':
                        # ESP8266 başlatıldı
                        self.logger.info("Coil %s ESP8266 başlatıldı ve hazır", coil_id)
                        if hasattr(self, 'notification_panel'):
                            QTimer.singleShot(0, lambda: QTimer.singleShot(0, lambda: self.notification_panel.add_notification(f"✅ Bobin {coil_id} başlatıldı ve hazır", "success")))
                        # ESP durum panelini güncelle
                        status_data = {
                            'coil_id': coil_id,
                            'sensors_ok': True
                        }
                        
                        try:
                            self.esp_status_received.emit(coil_id, status_data)
                        except RuntimeError:
                            pass
                    
                    # KPI Dashboard'a sensor verisi gönder (gerçek zamanlı enerji izleme)
                    kpi_dashboard_ref = getattr(self, 'kpi_dashboard_window', None)
                    if kpi_dashboard_ref and self._is_window_alive(kpi_dashboard_ref):
                        try:
                            # Sadece pencere gerçekten açık ve çalışır durumdaysa sinyal gönder
                            if kpi_dashboard_ref.isVisible():
                                kpi_dashboard_ref.sensor_data_updated.emit(str(coil_id), dict(self.latest_sensor_data))
                        except (RuntimeError, ValueError) as e:
                            # Silinmiş C++ objesi hatası olursa sessizce atla ve referansı temizle
                            self.kpi_dashboard_window = None
                        except Exception as e:
                            if self.logger.isEnabledFor(logging.DEBUG):
                                self.logger.debug(f"KPI dashboard güncelleme hatası: {e}")

                    # Sadece aktif bobinlerin verilerini işle
                    received_coil_id = int(coil_id)
                    
                    # Thread-safe active_coils kontrolü (Thread Safety Fix)
                    is_coil_active = self.is_coil_active(received_coil_id)
                    
                    mag_value = data.get('magnetic_field', 0)
                    temp_value = data.get('object_temp', 0)
                    self._append_graph_data(received_coil_id, mag_value, temp_value)

                
                elif topic.endswith('/status'):
                    # ESP8266 durum mesajı (WiFi, MQTT, PWM, sensör durumu)
                    # Performans optimizasyonu: Lazy evaluation
                    if self.logger.isEnabledFor(logging.DEBUG):
                        self.logger.debug("Coil %s durum verisi: WiFi=%s, MQTT=%s", 
                                        coil_id, data.get('wifi_connected'), data.get('mqtt_connected'))
                    
                    # Update latest_sensor_data with PWM status from status message if available
                    # ESP'den pwm_duty_cycle olarak geliyor, pwm_duty olarak kaydediyoruz
                    if 'pwm_active' in data or 'pwm_frequency' in data or 'pwm_duty_cycle' in data or 'pwm_duty' in data:
                        self.mqtt_mutex.lock()
                        try:
                            if not hasattr(self, 'latest_sensor_data') or self.latest_sensor_data is None:
                                self.latest_sensor_data = {}
                            if coil_id not in self.latest_sensor_data or not isinstance(self.latest_sensor_data[coil_id], dict):
                                self.latest_sensor_data[coil_id] = {}
                                
                            # Update PWM status in latest_sensor_data
                            # ESP'den pwm_duty_cycle olarak geliyor, pwm_duty olarak kaydediyoruz
                            if 'pwm_active' in data:
                                self.latest_sensor_data[coil_id]['pwm_active'] = data.get('pwm_active', False)
                            if 'pwm_frequency' in data:
                                self.latest_sensor_data[coil_id]['pwm_frequency'] = data.get('pwm_frequency', 0)
                            pwm_duty_value = data.get('pwm_duty', 0)
                            self.latest_sensor_data[coil_id]['pwm_duty'] = pwm_duty_value
                            if 'pwm_duration' in data:
                                self.latest_sensor_data[coil_id]['pwm_duration'] = data.get('pwm_duration')
                            if 'pwm_remaining_time' in data:
                                self.latest_sensor_data[coil_id]['pwm_remaining_time'] = data.get('pwm_remaining_time')
                            self.latest_sensor_data[coil_id]['coil_id'] = coil_id
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
                    self.esp_status_buffer_mutex.lock()
                    try:
                        if hasattr(self, 'esp_last_seen'):
                            self.esp_last_seen[coil_id] = time.time()
                            try:
                                self.esp_last_seen[int(coil_id)] = time.time()
                            except ValueError:
                                pass
                    finally:
                        self.esp_status_buffer_mutex.unlock()
                    
                    # UYUMSUZ-6 DÜZELTMESİ: /sensors topic kaldırıldı, tüm sensör verisi /status'tan geliyor.
                    # SensorDataWindow grafikleri için sensor_data_received signal'ını /status'tan da emit et.
                    # Ana pencere grafikleri için graph_data da /status'tan güncelleniyor.
                    if any(k in data for k in ('object_temp', 'ambient_temp', 'magnetic_field', 'current')):
                        # NOT: _persist ve grafik append KASITLI OLARAK KALDIRILDI.
                        # Bu veriler /sensors handler'ında zaten işleniyor.
                        # /status'tan sadece SensorDataWindow ve UnifiedControlWindow'u güncelle.
                        try:
                            self.sensor_data_received.emit(coil_id, data)
                        except RuntimeError:
                            return

                        # Sıcaklık sinyali UnifiedControlWindow için
                        temp_value_status = data.get('object_temp', 0.0)
                        try:
                            temp_value_status = float(temp_value_status)
                        except (TypeError, ValueError):
                            temp_value_status = 0.0
                        if hasattr(self, 'unified_control_window') and self._is_window_alive(self.unified_control_window):
                            try:
                                self.unified_control_window._safe_update_temperature_signal.emit(int(coil_id), temp_value_status)
                            except (RuntimeError, ValueError, TypeError):
                                pass

                        # last_known güncelle (grafik eksen takibi için — append değil)
                        received_coil_id_status = int(coil_id)
                        self.graph_data_mutex.lock()
                        try:
                            self.last_known_mag[received_coil_id_status] = data.get('magnetic_field', 0)
                            self.last_known_temp[received_coil_id_status] = data.get('object_temp', 0)
                        finally:
                            self.graph_data_mutex.unlock()
                    
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

                elif topic.endswith('/ack'):
                    # ESP8266'dan gelen command acknowledgment (GUI Stability Fix #4)

                    command_id = data.get('command_id')
                    success = data.get('success', False)
                    
                    # UnifiedControlWindow'a ACK ilet
                    if hasattr(self, 'unified_control_window') and self._is_window_alive(self.unified_control_window):
                        try:
                            self.unified_control_window._handle_command_ack(int(coil_id), command_id, success)
                        except Exception as e:
                            self.logger.error(f"ACK handling error: {e}")

                elif topic.endswith('/alarm'):
                    # ESP8266'dan gelen alarm mesajları (GUI Stability Fix - ESP entegrasyonu)

                    # Performans optimizasyonu: Lazy evaluation
                    self.logger.warning("Coil %s alarm: %s", coil_id, data)
                    
                    alarm_type = data.get('alarm_type', 'unknown')
                    reason = data.get('reason', 'Bilinmeyen sebep')
                    
                    # Notification panel'e bildir
                    if hasattr(self, 'notification_panel'):
                        if alarm_type == 'safety_violation':
                            QTimer.singleShot(0, lambda: self.notification_panel.add_notification(
                                f"🚨 Coil {coil_id} Güvenlik Uyarısı: {reason}",
                                "error"
                            ))
                        elif alarm_type == 'low_memory':
                            free_heap = data.get('free_heap', 0)
                            QTimer.singleShot(0, lambda: self.notification_panel.add_notification(
                                f"⚠️ Coil {coil_id} Düşük Bellek: {free_heap} bytes",
                                "warning"
                            ))
                        else:
                            QTimer.singleShot(0, lambda: self.notification_panel.add_notification(
                                f"⚠️ Coil {coil_id} Alarm: {reason}",
                                "warning"
                            ))
            
            # Handle ESP32 system log messages (WARN/ERROR)
            elif topic.endswith('/system/log'):
                try:
                    log_level = data.get('level', 0)  # 0=INFO, 1=WARN, 2=ERROR
                    log_msg = data.get('msg', '')
                    heap = data.get('heap', 0)
                    
                    # Log seviyesine göre işlem yap
                    if log_level == 2:  # ERROR
                        self.logger.error(f"Coil {coil_id} ESP32 ERROR: {log_msg} (heap: {heap})")
                        if hasattr(self, 'notification_panel'):
                            QTimer.singleShot(0, lambda: self.notification_panel.add_notification(
                                f"❌ Coil {coil_id}: {log_msg}",
                                "error"
                            ))
                    elif log_level == 1:  # WARN
                        self.logger.warning(f"Coil {coil_id} ESP32 WARN: {log_msg} (heap: {heap})")
                        if hasattr(self, 'notification_panel'):
                            QTimer.singleShot(0, lambda: self.notification_panel.add_notification(
                                f"⚠️ Coil {coil_id}: {log_msg}",
                                "warning"
                            ))
                except Exception as e:
                    self.logger.error(f"System log message handling error: {e}", exc_info=True)
            
            else:
                self.logger.debug(f"Unknown MQTT topic format: {topic}")
                    
        except json.JSONDecodeError as e:
            self.logger.error(f"MQTT mesaj JSON parse hatası: {e}", exc_info=True)
        except Exception as e:
            self.logger.error(f"MQTT mesaj işleme hatası: {e}", exc_info=True)

    def _handle_session_control(self, data: dict):
        """Android'den gelen session control komutlarını işle."""
        command = data.get('command')
        if command == 'start_session':
            patient_name = data.get('patient_name', 'Android Kullanıcısı')
            duration = data.get('duration_minutes', 15)
            frequency = data.get('frequency', 50.0)
            intensity = data.get('intensity', 20.0)
            target = data.get('target', 'Genel Tedavi')
            mode = data.get('mode', 'Otonom Mod')  # Android'den gelen mod bilgisi
            
            self.logger.info(f"Android'den session başlatma komutu: {patient_name}, {duration}dk, {mode}")
            if hasattr(self, 'notification_panel'):
                QTimer.singleShot(0, lambda: self.notification_panel.add_notification(
                    f"📱 Android'den tedavi başlatma: {patient_name} ({mode})", "info"
                ))
            
            if not getattr(self, 'is_treatment_active', False):
                if hasattr(self, 'start_treatment_from_mqtt'):
                    self.start_treatment_from_mqtt(patient_name, duration, frequency, intensity, target, mode)
                else:
                    self.logger.warning("start_treatment_from_mqtt metodu implement edilmemiş")
            else:
                self.logger.warning("Zaten aktif bir session var, Android komutu ignore edildi")
        
        elif command == 'stop_session':
            self.logger.info("Android'den session durdurma komutu")
            if hasattr(self, 'notification_panel'):
                QTimer.singleShot(0, lambda: self.notification_panel.add_notification(
                    "📱 Android'den tedavi durdurma komutu", "info"
                ))
            
            if getattr(self, 'is_treatment_active', False):
                # Eger unified window uzerinden kapatiliyorsa oraya ilet
                if hasattr(self, 'unified_control_window') and self._is_window_alive(self.unified_control_window):
                    try:
                        self.unified_control_window.stop_treatment(stop_reason="android_stop")
                    except Exception as e:
                        self.logger.error(f"Unified window Android durdurma hatası: {e}")
                        if hasattr(self, 'stop_treatment'):
                            self.stop_treatment()
                elif hasattr(self, 'stop_treatment'):
                    self.stop_treatment()
                else:
                    self.logger.warning("stop_treatment metodu bulunamadı")
            else:
                self.logger.info("Aktif session yok, Android durdurma komutu ignore edildi")

    def start_treatment_from_mqtt(self, patient_name, duration, frequency, intensity, target, mode):
        """Android'den gelen komutla tedaviyi Unified Control panelinden başlatır."""
        try:
            # Unified Control Window'un açık olduğundan emin ol
            self.show_unified_control()
            unified = self.unified_control_window
            
            # TODO: Seçili hastayı arayabilmek için patient_name'den basit eşleşme yapılabilir.
            # Şimdilik memory/UI'ı bypass etmeden varsayılan bir hasta nesnesi oluşturuyoruz
            # eğer gerçek seçili yoksa.
            if not unified.selected_patient:
                unified.selected_patient = {
                    'id': 'android_remote_' + str(int(time.time())),
                    'info': {'name': patient_name, 'species': 'unknown'}
                }
                unified.patient_label.setText(f"Hasta: {patient_name} (Remote)")

            # Modlara göre Unified Panelini güncelle ve başlat
            if "AI" in mode or "ai" in mode.lower():
                unified.tab_widget.setCurrentIndex(2)  # AI Sekmesi
                unified.ai_target_combo.setCurrentText(target)
                unified.ai_duration_value.setText(f"{duration} dakika")
                unified.ai_freq_value.setText(f"{frequency:.1f} Hz")
                unified.ai_intensity_value.setText(f"{intensity:.0f} %")  # Duty/Intensity mapped
                unified._start_ai_session()
                
            elif "Manuel" in mode or "manual" in mode.lower():
                unified.tab_widget.setCurrentIndex(1)  # Manuel Sekmesi
                unified.master_freq_spin.setValue(int(frequency))
                unified.master_duty_spin.setValue(int(intensity))
                unified.master_duration_spin.setValue(int(duration))
                unified.apply_to_all_coils()
                # Manuel başlatma tüm ESP'lere set the params AND then start
                unified.start_all_coils()
                # Simulate session start locally
                self.treatment_duration_minutes = duration
                self.start_treatment(create_session=False) 
                # (Sadece ana window timer update için manual trigger)
                
            else:
                # Otonom Mod
                unified.tab_widget.setCurrentIndex(0)  # Otomatik Sekmesi
                unified.target_combo.setCurrentText(target)
                unified.auto_frequency_spin.setValue(int(frequency))
                unified.auto_duty_cycle_spin.setValue(50)  # Varsayılan %50 duty
                unified.auto_intensity_spin.setValue(float(intensity))
                # Dialog popup'ını ezerek doğrudan süreyi ve hedefi geç
                unified.start_automatic_treatment(override_duration=duration, override_target=target)

            self.logger.info(f"Android MQTT seansı {mode} modunda başlatıldı.")
            
        except Exception as e:
            self.logger.error(f"start_treatment_from_mqtt sırasında hata: {e}", exc_info=True)


    def _persist_sensor_sample_if_session_active(self, coil_id: str, sensor_data: dict):
        """Aktif seans sırasında gelen sensör verisini seans DB'sine kuyruğa ekle."""
        try:
            if not hasattr(self, 'session_manager') or self.session_manager is None:
                return
            if not self.session_manager.is_session_active():
                return
            # Ana thread'e ertele — MQTT thread'ini bloke etme
            snapshot = dict(sensor_data)  # MQTT thread paylaşımlı dict'i kopyala
            QTimer.singleShot(0, lambda: self._persist_sensor_main_thread(coil_id, snapshot))
        except Exception as e:
            if self.logger.isEnabledFor(logging.DEBUG):
                self.logger.debug(f"Sensor sample persist skip: {e}")

    def _persist_sensor_main_thread(self, coil_id: str, sensor_data: dict):
        """Ana thread'de çalışır — session_manager thread-safe değilse buradan çağrılmalı."""
        try:
            if self.session_manager and self.session_manager.is_session_active():
                self.session_manager.add_sensor_sample(coil_id, sensor_data)
        except Exception as e:
            if self.logger.isEnabledFor(logging.DEBUG):
                self.logger.debug(f"Sensor persist error: {e}")

    def _load_performance_config(self) -> dict:
        """config/config.json içinden performance bölümünü güvenli şekilde yükle."""
        try:
            config_path = Path(__file__).resolve().parent.parent / "config" / "config.json"
            with open(config_path, 'r', encoding='utf-8') as handle:
                cfg = json.load(handle)
            return cfg.get('performance', {})
        except Exception:
            return {}

    def _record_gui_render_latency_metrics(self):
        """MQTT alım zamanı ile GUI render zamanı arasındaki gecikmeyi p50/p95/p99 olarak ölç."""
        self.mqtt_mutex.lock()
        try:
            if not self._pending_render_receive_ts:
                return
            pending_receive_times = list(self._pending_render_receive_ts)
            self._pending_render_receive_ts.clear()
        finally:
            self.mqtt_mutex.unlock()

        render_ts = time.time()
        for rx_ts in pending_receive_times:
            latency_ms = (render_ts - float(rx_ts)) * 1000.0
            if 0.0 <= latency_ms <= 10_000.0:
                self._render_latency_samples_ms.append(latency_ms)

        if not self._render_latency_samples_ms:
            return

        self._render_tick_count += 1
        if self._render_tick_count % self._latency_publish_every_renders != 0:
            return

        latencies = np.array(self._render_latency_samples_ms, dtype=np.float64)
        latest_ms = float(latencies[-1])
        p50_ms = float(np.percentile(latencies, 50))
        p95_ms = float(np.percentile(latencies, 95))
        p99_ms = float(np.percentile(latencies, 99))

        self.metrics.set_gauge('latency_mqtt_to_render_latest_ms', latest_ms)
        self.metrics.set_gauge('latency_mqtt_to_render_p50_ms', p50_ms)
        self.metrics.set_gauge('latency_mqtt_to_render_p95_ms', p95_ms)
        self.metrics.set_gauge('latency_mqtt_to_render_p99_ms', p99_ms)
        self.metrics.set_gauge('latency_mqtt_to_render_sample_count', float(len(latencies)))

        if p95_ms > self._latency_target_ms:
            self.metrics.increment('latency_mqtt_to_render_slo_violation_p95_count')

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
                self._record_gui_render_latency_metrics()
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

    def _prevent_rapid_window_open(self):
        """[Geriye dönük uyumluluk - artık kullanılmıyor]"""
        return False

    def _is_window_creating(self, key: str) -> bool:
        return getattr(self, '_window_creating_flags', {}).get(key, False)

    def _set_window_creating(self, key: str, value: bool):
        if not hasattr(self, '_window_creating_flags'):
            self._window_creating_flags = {}
        self._window_creating_flags[key] = value
        if value:
            import PyQt6.QtCore as QtCore
            QtCore.QTimer.singleShot(10000, lambda k=key: self._set_window_creating(k, False))
        # Global ağır pencere kilidi
        if not hasattr(self, '_heavy_window_creating'):
            self._heavy_window_creating = False
        if value:
            self._heavy_window_creating = True
        else:
            # Hâlâ devam eden başka bir ağır pencere var mı?
            self._heavy_window_creating = any(
                self._window_creating_flags.get(k, False)
                for k in self._window_creating_flags
            )

    def _is_heavy_window_creating(self) -> bool:
        """Herhangi bir ağır pencere şu an başlatılıyor mu?"""
        if getattr(self, '_heavy_window_creating', False):
            return True
        # Digital Twin kendi bayrağını kullandığı için ayrıca kontrol et
        if getattr(self, 'digital_twin_opening', False):
            return True
        return False

    def open_sensor_data_window(self):
        if self._is_window_creating('sensor_data'): return
        self._set_window_creating('sensor_data', True)
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
        if not self._is_window_alive(self.sensor_data_window):
            try:
                self.sensor_data_window = SensorDataWindow()
                self.sensor_data_window.setMainWindow(self)
                # MQTT sensor data signal-slot bağlantısını kur
                self.sensor_data_window.connect_to_main_window(self)
                self.sensor_data_window.destroyed.connect(lambda _=None: setattr(self, 'sensor_data_window', None))
            finally:
                self._set_window_creating('sensor_data', False)
        else:
            self._set_window_creating('sensor_data', False)

        if not self.sensor_data_window.isVisible():
            self.sensor_data_window.show()
            
        if self.sensor_data_window.isMinimized():
            self.sensor_data_window.showNormal()
            
        self.sensor_data_window.setWindowState(self.sensor_data_window.windowState() & ~Qt.WindowState.WindowMinimized | Qt.WindowState.WindowActive)
        self.sensor_data_window.activateWindow()
        self.sensor_data_window.raise_()

    def open_dema_simulator_window(self):
        if self._is_window_creating('dema_simulator'): return
        if self._is_heavy_window_creating():
            self.logger.warning("Başka bir pencere başlatılıyor, Dema Simulator bekleniyor...")
            return
        self._set_window_creating('dema_simulator', True)
        """Bölünmüş Dema Terapi Simülatörü penceresini açar"""
        try:
            from windows.dema_simulator_window import DemaSimulatorWindow
            if not hasattr(self, 'dema_simulator_window') or self.dema_simulator_window is None:
                try:
                    self.dema_simulator_window = DemaSimulatorWindow(self)
                    self.dema_simulator_window.show()
                finally:
                    self._set_window_creating('dema_simulator', False)
            else:
                self._set_window_creating('dema_simulator', False)
                if not self.dema_simulator_window.isVisible():
                    self.dema_simulator_window.show()
                # Windows'da minimize durumu handle etmek için:
                if self.dema_simulator_window.isMinimized():
                    self.dema_simulator_window.showNormal()
                self.dema_simulator_window.activateWindow()
                self.dema_simulator_window.raise_()
        except ImportError as e:
            self._set_window_creating('dema_simulator', False)
            self.logger.error(f"PyQt6 WebEngineWidgets modülü eksik: {str(e)}")
            import traceback
            self.logger.error(traceback.format_exc())
            QMessageBox.warning(self, "Modül Eksik", "Simülatör için PyQt6-WebEngine gereklidir. Geliştirici konsolundan yükleyin:\npip install PyQt6-WebEngine")
        except Exception as e:
            self.logger.error(f"Dema Simulator Window açılamadı: {str(e)}")
            import traceback
            self.logger.error(traceback.format_exc())

    def open_digital_twin_window(self):
        if self._is_heavy_window_creating():
            self.logger.warning("Başka bir pencere başlatılıyor, Digital Twin bekleniyor...")
            if hasattr(self, 'notification_panel'):
                self.notification_panel.add_notification(
                    "Lütfen bekleyin, başka bir pencere açılıyor...", "info"
                )
            return
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
                    unity_dll_path = str(Path(pemf_temp_dir_str) / "UnityPlayer.dll")
                    pemf_data_dir = Path(pemf_temp_dir_str) / "PEMF_Data"

                    class FileAccessWaiterThread(QThread):
                        finished_signal = pyqtSignal(bool, str)

                        def __init__(self, _pemf_exe_path, _unity_dll_path, _pemf_data_dir):
                            super().__init__()
                            self.pemf_exe_path = _pemf_exe_path
                            self.unity_dll_path = _unity_dll_path
                            self.pemf_data_dir = _pemf_data_dir

                        def stop(self) -> None:
                            """İptal bayrağını set eder; run() döngüsü kontrol eder."""
                            self.requestInterruption()
                            if self.isRunning():
                                if not self.wait(3000):
                                    import logging
                                    logging.getLogger(__name__).warning("DigitalTwinWaitThread kapanamadi")

                        def run(self):
                            import time
                            from pathlib import Path
                            max_wait = 30.0

                            def wait_for_file(file_path, timeout):
                                start_time = time.time()
                                while time.time() - start_time < timeout:
                                    if self.isInterruptionRequested():
                                        return False          # iptal edildi
                                    try:
                                        with open(file_path, 'rb') as f:
                                            f.read(1)
                                        return True
                                    except Exception:
                                        time.sleep(0.2)
                                return False

                            if not wait_for_file(self.pemf_exe_path, max_wait):
                                self.finished_signal.emit(False, f"PEMF.exe dosyasına erişilemiyor (kilitli veya kopyalanamadı):\n{self.pemf_exe_path}")
                                return
                            
                            if Path(self.unity_dll_path).exists():
                                if not wait_for_file(self.unity_dll_path, max_wait):
                                    self.finished_signal.emit(False, f"UnityPlayer.dll dosyasına erişilemiyor (kilitli veya kopyalanamadı):\n{self.unity_dll_path}")
                                    return
                            
                            self.finished_signal.emit(True, "")

                    self.logger.info("Dosyalara erişim bekleniyor (arka planda)...")
                    
                    def on_wait_finished(success, error_msg):
                        self.waiter_thread.deleteLater()
                        if not success:
                            self.logger.warning(error_msg.replace('\n', ' '))
                            QMessageBox.warning(self, "Hata", error_msg)
                            return

                        # PEMF_Data dizinini kontrol et (en az bir dosya olmalı)
                        if not pemf_data_dir.exists() or not any(pemf_data_dir.rglob('*')):
                            # İlk kontrol başarısızsa sadece logla, ancak donma yapmadan devam et
                            self.logger.warning(f"PEMF_Data dizini ilk kontrolde eksik veya boş: {pemf_data_dir}")
                        
                        # İLK AÇILIŞ BEYAZ EKRAN DÜZELTMESİ:
                        # Unity başlatmadan önce ek bekleme - tüm dosyaların tamamen hazır olmasını sağla
                        # İlk kopyalamadan sonra dosya sistemi ve antivirüs taramaları için ekstra süre
                        self.logger.info("Unity başlatma öncesi hazırlık bekleniyor (QTimer)...")
                        
                        def launch_unity():
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
                            
                                # İLK AÇILIŞ BEYAZ EKRAN DÜZELTMESİ (Async Timer)
                                self.logger.info("Unity render başlatması bekleniyor (QTimer)...")
                            
                                # Unity penceresini bulup maximize butonunu aktif et
                                def enable_maximization():
                                    if sys.platform == 'win32':
                                        for delay in [1000, 3000, 5000, 7000]:  # 1s, 3s, 5s, 7s sonra dene
                                            QTimer.singleShot(delay, lambda pid=process.pid: self._enable_maximize_button(pid))
                                
                                    # Başarı mesajı göster
                                    if hasattr(self, 'notification_panel'):
                                        self.notification_panel.add_notification(
                                            "PEMF Digital Twin başlatıldı", 
                                            "success"
                                        )
                            
                                # Unity render için 3 saniye non-blocking süre tanı
                                QTimer.singleShot(3000, enable_maximization)
                            
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

                        # ÖNEMLİ: launch_unity sadece tanımlanmıştı; burada non-blocking olarak gerçekten tetikle.
                        QTimer.singleShot(800, launch_unity)

                    self.waiter_thread = FileAccessWaiterThread(pemf_exe_path, unity_dll_path, pemf_data_dir)
                    self.waiter_thread.finished_signal.connect(on_wait_finished)
                    self.waiter_thread.start()
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
            
            # EnumWindows callback tipi
            from ctypes import wintypes
            WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
            
            def enum_windows_callback(hwnd, lParam):
                try:
                    # Process ID'yi kontrol et
                    process_ids = ctypes.c_ulong()
                    ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_ids))
                    if process_ids.value != process_id:
                        return 1
                    
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
                        return 0  # Pencere bulundu, aramayı durdur
                    
                except Exception as e:
                    self.logger.debug(f"EnumWindows callback hatası: {e}")
                
                return 1  # Devam et
            
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
            
            # EnumWindows callback tipi
            from ctypes import wintypes
            WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
            
            def enum_windows_callback(hwnd, lParam):
                try:
                    # Process ID'yi kontrol et
                    process_ids = ctypes.c_ulong()
                    ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_ids))
                    if process_ids.value != process_id:
                        return 1
                    
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
                        return 0  # Pencere bulundu, aramayı durdur
                    
                except Exception as e:
                    self.logger.debug(f"EnumWindows callback hatası: {e}")
                
                return 1  # Devam et
            
            callback = WNDENUMPROC(enum_windows_callback)
            
            # Tüm pencereleri listele
            ctypes.windll.user32.EnumWindows(callback, 0)
            
        except Exception as e:
            self.logger.error(f"Digital Twin öne getirme hatası: {e}", exc_info=True)

    def open_kpi_dashboard(self):
        if self._is_window_creating('kpi_dashboard'): return
        self._set_window_creating('kpi_dashboard', True)
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
        if not self._is_window_alive(self.kpi_dashboard_window):
            try:
                self.kpi_dashboard_window = KPIDashboardWindow(main_window=self)
                self.kpi_dashboard_window.destroyed.connect(lambda _=None: setattr(self, 'kpi_dashboard_window', None))
            finally:
                self._set_window_creating('kpi_dashboard', False)
        else:
            self._set_window_creating('kpi_dashboard', False)

        if not self.kpi_dashboard_window.isVisible():
            self.kpi_dashboard_window.show()
            
        if self.kpi_dashboard_window.isMinimized():
            self.kpi_dashboard_window.showNormal()
            
        self.kpi_dashboard_window.setWindowState(self.kpi_dashboard_window.windowState() & ~Qt.WindowState.WindowMinimized | Qt.WindowState.WindowActive)
        self.kpi_dashboard_window.activateWindow()
        self.kpi_dashboard_window.raise_()

    def open_unified_control(self):
        if self._is_window_creating('unified_control'): return
        self._set_window_creating('unified_control', True)
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
        if not self._is_window_alive(self.unified_control_window):
            try:
                # Ağır pencere oluşumu öncesi UI'ı güncelle ve imleci meşgul yap
                from PyQt6.QtWidgets import QApplication
                QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
                QApplication.processEvents()
                
                self.unified_control_window = UnifiedControlWindow(main_window=self)
                # Sinyal duplikasyonunu önle: önce kes, sonra bağla
                try:
                    self.patient_saved.disconnect(self.unified_control_window._load_patient_list)
                except (TypeError, RuntimeError):
                    pass
                self.patient_saved.connect(self.unified_control_window._load_patient_list)
                self.stm_connected_signal.connect(
                    self.unified_control_window.set_stm_connected,
                    Qt.ConnectionType.QueuedConnection
                )
                if getattr(self, 'stm_is_connected', False):
                    QTimer.singleShot(100, lambda: getattr(self.unified_control_window, 'set_stm_connected', lambda x: None)(True))
            finally:
                self._set_window_creating('unified_control', False)
                try:
                    from PyQt6.QtWidgets import QApplication
                    QApplication.restoreOverrideCursor()
                except:
                    pass
        else:
            self._set_window_creating('unified_control', False)

        if not self.unified_control_window.isVisible():
            self.unified_control_window.show()
            
        if self.unified_control_window.isMinimized():
            self.unified_control_window.showNormal()
            
        self.unified_control_window.setWindowState(self.unified_control_window.windowState() & ~Qt.WindowState.WindowMinimized | Qt.WindowState.WindowActive)
        self.unified_control_window.activateWindow()
        self.unified_control_window.raise_()
        
        # Hasta bilgilerini güncelle
        if hasattr(self, 'unified_control_window') and self._is_window_alive(self.unified_control_window):
            self.unified_control_window.update_patient_info()

    def open_treatment_history(self):
        if self._is_window_creating('treatment_history'): return
        self._set_window_creating('treatment_history', True)
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
        if not self._is_window_alive(self.treatment_history_window):
            try:
                self.treatment_history_window = TreatmentHistoryWindow(main_window=self)
                self.treatment_history_window.destroyed.connect(lambda _=None: setattr(self, 'treatment_history_window', None))
            finally:
                self._set_window_creating('treatment_history', False)
        else:
            self._set_window_creating('treatment_history', False)

        if not self.treatment_history_window.isVisible():
            self.treatment_history_window.show()
            
        if self.treatment_history_window.isMinimized():
            self.treatment_history_window.showNormal()
            
        self.treatment_history_window.setWindowState(self.treatment_history_window.windowState() & ~Qt.WindowState.WindowMinimized | Qt.WindowState.WindowActive)
        self.treatment_history_window.activateWindow()
        self.treatment_history_window.raise_()

    def _is_window_alive(self, window_obj):
        """Return True if a Qt window reference is valid and not deleted."""
        if window_obj is None:
            return False
            
        try:
            # C++ objesine erişerek silinip silinmediğini kontrol et
            window_obj.objectName()
            return True
        except (RuntimeError, AttributeError):
            return False

    def toggle_silent_mode(self):
        """Sessiz modu aç/kapat"""
        self.silent_mode = not self.silent_mode
        
        if self.silent_mode:
            # Sessiz mod açık
            self.silent_mode_btn.setText("🔇")
            self.silent_mode_btn.setStyleSheet(RS.silent_mode_btn(active=True))
            self.silent_mode_btn.setToolTip("Sessiz Mod Açık (Bildirimleri Aç)")
            self.logger.info("Sessiz mod açıldı")
            # Sessiz mod açıldığına dair bildirim (bu gösterilecek çünkü henüz sessiz mod aktif değildi)
            if hasattr(self, 'notification_panel'):
                self.notification_panel.add_notification("Sessiz mod açıldı - Sadece kritik hatalar gösterilecek", "info")
        else:
            # Sessiz mod kapalı
            self.silent_mode_btn.setText("🔊")
            self.silent_mode_btn.setStyleSheet(RS.silent_mode_btn(active=False))
            self.silent_mode_btn.setToolTip("Sessiz Mod (Bildirimleri Kapat/Aç)")
            self.logger.info("Sessiz mod kapatıldı")
            if hasattr(self, 'notification_panel'):
                self.notification_panel.add_notification("Sessiz mod kapatıldı - Tüm bildirimler gösterilecek", "success")
    
    def open_user_manual(self):
        if self._is_window_creating('user_manual'): return
        self._set_window_creating('user_manual', True)
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
                self.logger.warning(f"MQTT client not available, cannot send coil {coil_num} command")
                return

            # If UnifiedControlWindow is open, add command to its pending_commands
            if hasattr(self, 'unified_control_window') and self._is_window_alive(self.unified_control_window) and self.unified_control_window.isVisible():
                try:
                    self.unified_control_window.add_pending_command(coil_num, command)
                except Exception as e:
                    self.logger.warning(f"Failed to add pending command to UnifiedControlWindow: {e}")

            # Send MQTT command (MainWindow is the only one that writes to MQTT)
            topic = f"pemf/coil/{coil_num}/control"
            command_json = json.dumps(command)

            result = self.mqtt_client.publish(topic, command_json, qos=1)

            if result.rc != 0:
                self.logger.error(f"✗ Failed to send coil {coil_num} command '{command.get('command', 'unknown')}' to topic {topic}: MQTT publish failed (rc={result.rc})")

        except Exception as e:
            self.logger.error(f"Error handling coil control request: {e}", exc_info=True)

    def handle_batch_coil_control_request(self, batch_command):
        """
        Thread-safe slot for batch_coil_control_requested signal.
        Sends a single SYNC_ALL command to the broadcast topic.
        """
        try:
            if not hasattr(self, 'mqtt_client') or not self.mqtt_client or not self.mqtt_connected_state:
                self.logger.warning("MQTT client not available, cannot send batch command")
                return

            # If UnifiedControlWindow is open, add command to its pending_commands
            if hasattr(self, 'unified_control_window') and self._is_window_alive(self.unified_control_window) and self.unified_control_window.isVisible():      
                try:
                    # add_pending_command can still track per-coil commands to receive acks.
                    # but here we just need to send the batch command once. we can assume it's logged
                    pass
                except Exception as e:
                    self.logger.warning(f"Failed to add pending batch command to UnifiedControlWindow: {e}")

            # Send MQTT command (MainWindow is the only one that writes to MQTT)
            topic = "pemf/coil/all/control"
            command_json = json.dumps(batch_command)

            result = self.mqtt_client.publish(topic, command_json, qos=1)       

            if result.rc != 0:
                self.logger.error(f"✗ Failed to send batch command '{batch_command.get('command', 'unknown')}' to topic {topic}: MQTT publish failed (rc={result.rc})")

        except Exception as e:
            self.logger.error(f"Error handling batch coil control request: {e}", exc_info=True)

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
                self.st_status.setText(RS.treatment_status_html(stopped=False))
                self.st_status.setStyleSheet(RS.treatment_status_bg(stopped=False))

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
            if hasattr(self, '_custom_status_bar'):
                self._custom_status_bar.setText(
                    f"Seans parametreleri güncellendi - {params.get('target', 'Bilinmeyen')} ({params.get('profile', 'Varsayılan')})"
                )

        except Exception as e:
            self.logger.error(f"Error updating treatment parameters: {e}", exc_info=True)
            if hasattr(self, '_custom_status_bar'):
                self._custom_status_bar.setText(f"Hata: Seans parametreleri güncellenirken bir hata oluştu: {str(e)}")


    def increment_working_time(self):
        self.working_seconds += 1
        if self.working_seconds % 60 == 0:
            try:
                # FIX: AsyncFileWriter kullanılarak I/O blocking önlendi
                writer = AsyncFileWriter(
                    self.working_time_file,
                    self.working_seconds,
                    self.logger
                )
                QThreadPool.globalInstance().start(writer)
            except Exception as e:
                self.logger.error(f"Çalışma süresi kaydedilemedi: {e}")
        self.update_working_time_label()

    def update_working_time_label(self):
        s = self.working_seconds
        hours = s // 3600
        minutes = (s % 3600) // 60
        seconds = s % 60
        self.working_time_label.setText(f"{hours}:{minutes}:{seconds}")

    def update_total_treatment_count(self):
        """Seans geçmişinden toplam seans sayısını güncelle"""
        class DbWorker(QRunnable):
            def __init__(self, main_window):
                super().__init__()
                self.main_window = main_window
            
            def run(self):
                try:
                    db = get_treatment_db(self.main_window.app_data_dir)
                    stats = db.get_statistics()
                    total_sessions = stats.get('total_sessions', 0)
                    
                    def update_gui():
                        self.main_window.total_treatment_label.setText(f"{total_sessions} seans")
                        self.main_window.logger.info(f"Toplam seans sayısı güncellendi: {total_sessions}")
                        
                    import PyQt6.QtCore as qtcore
                    qtcore.QTimer.singleShot(0, update_gui)
                except Exception as e:
                    self.main_window.logger.error(f"Toplam seans sayısı güncellenirken hata: {e}")
                    import PyQt6.QtCore as qtcore
                    qtcore.QTimer.singleShot(0, lambda: self.main_window.total_treatment_label.setText("0 seans"))
                    
        from PyQt6.QtCore import QThreadPool
        QThreadPool.globalInstance().start(DbWorker(self))

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
            self.st_status.setText(RS.treatment_status_html(stopped=True))
            self.st_status.setStyleSheet(RS.treatment_status_bg(stopped=True))
        
        # Seans tamamlandıysa gözlem notları dialog'unu aç (sadece ana pencereden çağrıldığında)
        # DEPRECATED: Observation notes dialog kaldırıldı - unified_control halledecek
        # if hasattr(self, 'treatment_start_time') and self.treatment_start_time and not from_unified_control:
            # self.show_observation_notes_dialog()

        self.logger.info("Seans durduruldu")
        
        # Seans durumunu buluta gönder (Event-Based)
        self.broadcast_session_status()
    
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
            if mode == 'Manuel Mod' and hasattr(self, 'unified_control_window') and self._is_window_alive(self.unified_control_window) and self.unified_control_window.isVisible():
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
            payload_json = json.dumps(payload)
            
            # Cihaz ID'sine özel topic kullan (uzaktan izleme için)
            if not self.device_id:
                self.device_id = get_unique_device_id()
            
            # Android app "pemf/system/session" topic'ini dinliyor (retained=True)
            # Aynı mesajı her iki kanala da publish ediyoruz:
            #   1. pemf/system/session   → Android'in beklediği sabit kanal
            #   2. pemf/{id}/session      → cihaza özel kanal (geriye uyumluluk)
            system_topic = "pemf/system/session"
            device_topic = f"pemf/{self.device_id}/session"
            
            for topic in (system_topic, device_topic):
                result = self.mqtt_client.publish(topic, payload_json, qos=1, retain=True)
                if result.rc == 0:
                    self.logger.info(f"Seans durumu gönderildi → {topic}")
                else:
                    self.logger.error(f"Seans durumu gönderilemedi ({topic}). MQTT rc: {result.rc}")

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
            if treatment_mode == 'Manuel Mod' and hasattr(self, 'unified_control_window') and self._is_window_alive(self.unified_control_window) and self.unified_control_window.isVisible():
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
                RS.validation_label(color=color)
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
            if self._patient_save_in_progress:
                self.logger.info("Hasta kayıt işlemi zaten devam ediyor")
                return

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
            
            self._patient_save_in_progress = True
            if self.save_patient_btn:
                self.save_patient_btn.setEnabled(False)
                self.save_patient_btn.setText("Kaydediliyor...")

            worker = PatientSaveWorker(
                app_data_dir=self.app_data_dir,
                patient_info=patient_info,
                current_user=self.current_user,
                logger=self.logger
            )
            worker.signals.success.connect(self._on_patient_saved_success)
            worker.signals.error.connect(self._on_patient_saved_error)
            QThreadPool.globalInstance().start(worker)
            
        except Exception as e:
            self.logger.error(f"Hasta kayıt hatası: {e}", exc_info=True)
            self._patient_save_in_progress = False
            if self.save_patient_btn:
                self.save_patient_btn.setEnabled(True)
                self.save_patient_btn.setText("💾 Hastayı Kaydet")
            QMessageBox.critical(
                self,
                "Hata",
                f"Hasta kaydedilirken bir hata oluştu:\n{str(e)}"
            )

    def _on_patient_saved_success(self, patient_id, patient_info):
        """Handle async patient save completion on the GUI thread."""
        self._patient_save_in_progress = False
        if self.save_patient_btn:
            self.save_patient_btn.setEnabled(True)
            self.save_patient_btn.setText("💾 Hastayı Kaydet")

        # --- MQTT ile uzaktan bildirim ---
        if hasattr(self, 'mqtt_client') and self.mqtt_client and hasattr(self, 'mqtt_connected_state') and self.mqtt_connected_state:
            try:
                if not self.device_id:
                    self.device_id = get_unique_device_id()

                topic = f"pemf/{self.device_id}/new_patient"
                payload = {
                    "event": "patient_registered",
                    "patient_id": patient_id[:8],
                    "patient_name": patient_info['name'],
                    "species": patient_info['species'],
                    "owner": patient_info['owner'],
                    "timestamp": int(time.time() * 1000)
                }
                self.mqtt_client.publish(topic, json.dumps(payload), qos=1)
                self.logger.info(f"Yeni hasta bilgisi MQTT ile gönderildi -> {topic}")
            except Exception as e:
                self.logger.error(f"MQTT hasta bildirimi hatası: {e}")

        QMessageBox.information(
            self,
            "Başarılı",
            f"Hasta başarıyla kaydedildi!\n\n"
            f"Hasta Adı: {patient_info['name']}\n"
            f"Tür: {patient_info['species']}\n"
            f"Sahibi: {patient_info['owner']}\n"
            f"Hasta ID: {patient_id[:8]}..."
        )

        for field in self.input_fields:
            field.clear()

        self.last_saved_patient = {
            "id": patient_id,
            "info": patient_info
        }

        if self._is_window_alive(self.unified_control_window) and self.unified_control_window.isVisible():
            self.unified_control_window.update_patient_info()

        self.patient_saved.emit()
        QTimer.singleShot(0, self.open_unified_control)
        self.logger.info(f"Hasta kaydedildi: {patient_info['name']} (ID: {patient_id})")

    def _on_patient_saved_error(self, error_text):
        """Handle async patient save failure on the GUI thread."""
        self._patient_save_in_progress = False
        if self.save_patient_btn:
            self.save_patient_btn.setEnabled(True)
            self.save_patient_btn.setText("💾 Hastayı Kaydet")
        QMessageBox.critical(
            self,
            "Hata",
            f"Hasta kaydedilirken bir hata oluştu:\n{error_text}"
        )

    def create_esp_status_panel(self, parent_layout):
        """
        ESP bağlantı durumu panelini oluşturur.
        """
        self.logger.debug("🔧 ESP bağlantı durumu paneli oluşturuluyor...")
        self.logger.info("ESP bağlantı durumu paneli oluşturuluyor")
        
        # Bobin Bağlantı Durumu başlığı
        esp_title = QLabel("📡 Bobin Bağlantı Durumu")
        esp_title.setStyleSheet(RS.esp_section_title())
        parent_layout.addWidget(esp_title)
        self.logger.debug("ESP panel başlığı eklendi")
        
        # ESP durumları için container
        self.esp_container = QWidget()
        self.esp_container.setStyleSheet(RS.esp_container())
        
        self.esp_layout = QVBoxLayout(self.esp_container)
        self.esp_layout.setSpacing(get_responsive_spacing(8))
        
        # Başlangıçta "Bobin bulunamadı" mesajı
        self.no_esp_label = QLabel("🔍 Bobin cihazları aranıyor...")
        self.no_esp_label.setStyleSheet(RS.no_esp_label())
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
        
        # CRITICAL FIX: Widget oluşturulduğunda ESP'yi last_seen'e ekle (zaman damgası ile)
        # Bu sayede cleanup mekanizması düzgün çalışır ve ESP hiç mesaj göndermese bile 
        # timeout süresi sonunda ekrandan kaldırılır.
        if not hasattr(self, 'esp_last_seen'):
            self.esp_last_seen = {}
        self.esp_last_seen[coil_id] = time.time()
        
        esp_widget = QWidget()
        esp_widget.setStyleSheet(RS.esp_item_bg())
        
        layout = QVBoxLayout(esp_widget)
        layout.setSpacing(get_responsive_spacing(6))
        
        # Bobin başlığı
        header_layout = QHBoxLayout()
        esp_title = QLabel(f"🔌 Bobin {coil_id}")
        esp_title.setStyleSheet(RS.esp_title())
        
        # Bağlantı durumu göstergesi - FIXED: Başlangıçta GRİ (bilinmiyor)
        status_indicator = QLabel("●")
        status_indicator.setStyleSheet(RS.esp_indicator())
        
        header_layout.addWidget(esp_title)
        header_layout.addStretch()
        header_layout.addWidget(status_indicator)
        layout.addLayout(header_layout)
        
        # Durum bilgileri
        info_layout = QGridLayout()
        info_layout.setSpacing(get_responsive_spacing(4))
        
        # WiFi durumu
        wifi_label = QLabel("📶 WiFi:")
        wifi_label.setStyleSheet(RS.esp_info_label())
        wifi_status = QLabel("Bağlı değil")
        wifi_status.setStyleSheet(RS.esp_status_text("#ff4444"))
        info_layout.addWidget(wifi_label, 0, 0)
        info_layout.addWidget(wifi_status, 0, 1)
        
        # MQTT durumu
        mqtt_label = QLabel("📡 Bağlantı")
        mqtt_label.setStyleSheet(RS.esp_info_label())
        mqtt_status = QLabel("Bağlı değil")
        mqtt_status.setStyleSheet(RS.esp_status_text("#ff4444"))
        info_layout.addWidget(mqtt_label, 1, 0)
        info_layout.addWidget(mqtt_status, 1, 1)
        
        # Sensör durumu
        sensor_label = QLabel("🔬 Sensörler:")
        sensor_label.setStyleSheet(RS.esp_info_label())
        sensor_status = QLabel("Bilinmiyor")
        sensor_status.setStyleSheet(RS.esp_status_text("#ffa500"))
        info_layout.addWidget(sensor_label, 2, 0)
        info_layout.addWidget(sensor_status, 2, 1)
        
        # Uptime
        uptime_label = QLabel("⏱️ Çalışma:")
        uptime_label.setStyleSheet(RS.esp_info_label())
        uptime_status = QLabel("0s")
        uptime_status.setStyleSheet(RS.esp_info_label())
        info_layout.addWidget(uptime_label, 3, 0)
        info_layout.addWidget(uptime_status, 3, 1)
        
        # PWM durumu
        pwm_label = QLabel("⚡ Güç:")
        pwm_label.setStyleSheet(RS.esp_info_label())
        pwm_status = QLabel("Devre Dışı")
        pwm_status.setStyleSheet(RS.esp_status_text("#ff4444"))
        info_layout.addWidget(pwm_label, 4, 0)
        info_layout.addWidget(pwm_status, 4, 1)
        
        layout.addLayout(info_layout)
        
        # Sensör detayları (başlangıçta gizli)
        sensor_details = QWidget()
        sensor_details.setStyleSheet(RS.esp_sensor_details_bg())
        sensor_details_layout = QVBoxLayout(sensor_details)
        sensor_details_layout.setSpacing(get_responsive_spacing(3))
        
        # Sıcaklık Sensörü
        mlx90614_label = QLabel("🌡️ Sıcaklık Sensörü")
        mlx90614_label.setStyleSheet(RS.esp_sensor_detail("#ccc"))
        sensor_details_layout.addWidget(mlx90614_label)
        
        # Manyetik Alan Sensörü
        mlx90393_label = QLabel("🧲 Manyetik Alan Sensörü")
        mlx90393_label.setStyleSheet(RS.esp_sensor_detail("#ccc"))
        sensor_details_layout.addWidget(mlx90393_label)
        
        # Akım Sensörü
        acs712_label = QLabel("⚡ Akım Sensörü")
        acs712_label.setStyleSheet(RS.esp_sensor_detail("#ccc"))
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
        
        _ind_px = get_responsive_font_size(16)
        if not has_any_data:
            widgets['status_indicator'].setStyleSheet(f"color: #888888; font-size: {_ind_px}px;")  # Gri - bilinmiyor
        elif wifi_connected and mqtt_connected:
            widgets['status_indicator'].setStyleSheet(f"color: #44ff44; font-size: {_ind_px}px;")  # Yeşil - her şey OK
        elif wifi_connected:
            widgets['status_indicator'].setStyleSheet(f"color: #ffaa44; font-size: {_ind_px}px;")  # Turuncu - WiFi var ama MQTT yok
        else:
            widgets['status_indicator'].setStyleSheet(f"color: #ff4444; font-size: {_ind_px}px;")  # Kırmızı - WiFi yok
        
        # WiFi durumu (detaylı)
        if wifi_connected:
            wifi_ssid = status_data.get('wifi_ssid', '')
            wifi_ip = status_data.get('wifi_ip', '')
            if wifi_ssid:
                wifi_text = f"{wifi_ssid}"
            else:
                wifi_text = "Bağlı"
            widgets['wifi_status'].setText(wifi_text)
            widgets['wifi_status'].setStyleSheet(RS.esp_status_text("#44ff44"))
        else:
            widgets['wifi_status'].setText("Bağlı değil")
            widgets['wifi_status'].setStyleSheet(RS.esp_status_text("#ff4444"))
        
        # MQTT durumu
        if mqtt_connected:
            widgets['mqtt_status'].setText("Bağlı")
            widgets['mqtt_status'].setStyleSheet(RS.esp_status_text("#44ff44"))
        else:
            widgets['mqtt_status'].setText("Bağlı değil")
            widgets['mqtt_status'].setStyleSheet(RS.esp_status_text("#ff4444"))
        
        # Sensör durumu (genel)
        if sensors_ok:
            widgets['sensor_status'].setText("Çalışıyor")
            widgets['sensor_status'].setStyleSheet(RS.esp_status_text("#44ff44"))
        else:
            widgets['sensor_status'].setText("Hata")
            widgets['sensor_status'].setStyleSheet(RS.esp_status_text("#ff4444"))
        
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
            widgets['pwm_status'].setStyleSheet(RS.esp_status_text("#44ff44"))
        else:
            widgets['pwm_status'].setText("Devre Dışı")
            widgets['pwm_status'].setStyleSheet(RS.esp_status_text("#ff4444"))
        
        # Sensör detayları (her sensör için ayrı durum)
        # Sıcaklık Sensörü durumu
        if temp_sensor_ok:
            widgets['mlx90614_label'].setText("🌡️ Sıcaklık Sensörü")
            widgets['mlx90614_label'].setStyleSheet(RS.esp_sensor_detail("#44ff44"))
        else:
            widgets['mlx90614_label'].setText("🌡️ Sıcaklık Sensörü")
            widgets['mlx90614_label'].setStyleSheet(RS.esp_sensor_detail("#ff4444"))
        
        # Manyetik Alan Sensörü durumu
        if magnetic_sensor_ok:
            widgets['mlx90393_label'].setText("🧲 Manyetik Alan Sensörü")
            widgets['mlx90393_label'].setStyleSheet(RS.esp_sensor_detail("#44ff44"))
        else:
            widgets['mlx90393_label'].setText("🧲 Manyetik Alan Sensörü")
            widgets['mlx90393_label'].setStyleSheet(RS.esp_sensor_detail("#ff4444"))
        
        # Akım Sensörü durumu
        if current_sensor_ok:
            widgets['acs712_label'].setText("⚡ Akım Sensörü")
            widgets['acs712_label'].setStyleSheet(RS.esp_sensor_detail("#44ff44"))
        else:
            widgets['acs712_label'].setText("⚡ Akım Sensörü")
            widgets['acs712_label'].setStyleSheet(RS.esp_sensor_detail("#ff4444"))
        
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
                        if wifi_connected:
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
            
            reconnect_ok = False
            try:
                # Reconnect dene
                self.mqtt_client.reconnect()
                reconnect_ok = True
            finally:
                # reconnect() hata verse bile loop tekrar ayaga kaldirilsin
                try:
                    self.mqtt_client.loop_start()
                    self.logger.info("MQTT client loop yeniden başlatıldı")
                except Exception as loop_error:
                    self.logger.error(f"MQTT loop yeniden başlatma hatası: {loop_error}")
            
            if reconnect_ok:
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
                    self.mqtt_retry_count = 0
                    self.mqtt_retry_delay = 2000
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
                    self.mqtt_retry_count = 0
                    self.mqtt_retry_delay = 2000
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
        """Setup responsive window sizing and positioning for any screen size/DPI."""
        try:
            width, height, scale_factor, screen_type = get_screen_info()

            # Minimum sizes per screen type (logical pixels at 96 DPI baseline)
            min_sizes = {
                "mobile":    (600,  500),
                "tablet":    (800,  600),
                "laptop":    (1024, 700),
                "desktop":   (1280, 800),
                "ultrawide": (1540, 900),
            }
            min_w_base, min_h_base = min_sizes.get(screen_type, (1024, 700))

            # Target: 90% of available screen, never smaller than minimum
            target_w = max(int(min_w_base * scale_factor), int(width  * 0.90))
            target_h = max(int(min_h_base * scale_factor), int(height * 0.88))
            # But don't exceed the screen
            target_w = min(target_w, int(width  * 0.96))
            target_h = min(target_h, int(height * 0.94))

            # Centre on screen
            x = max(0, (width  - target_w) // 2)
            y = max(0, (height - target_h) // 2)

            self.setGeometry(x, y, target_w, target_h)
            self.setMinimumSize(
                scale_value(min_w_base, min_ratio=0.6),
                scale_value(min_h_base, min_ratio=0.6),
            )

            # On small/tablet screens open maximised for best use of space
            if screen_type in ("mobile", "tablet"):
                self.showMaximized()

            self._enable_responsive_features()

        except Exception:
            # Responsive fallback: use available screen dimensions
            _fb_w, _fb_h, _fb_scale, _ = get_screen_info()
            _fb_win_w = int(min(1540 * _fb_scale, _fb_w * 0.92))
            _fb_win_h = int(min(900 * _fb_scale, _fb_h * 0.90))
            _fb_x = (_fb_w - _fb_win_w) // 2
            _fb_y = (_fb_h - _fb_win_h) // 2
            self.setGeometry(_fb_x, _fb_y, _fb_win_w, _fb_win_h)
            self.setMinimumSize(scale_value(1024, min_ratio=0.6), scale_value(700, min_ratio=0.6))

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
            invalidate_screen_cache()
            
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
        """Apply compact styles for small screens (<1024px wide)"""
        try:
            if hasattr(self, 'clock'):
                scale_font(self.clock, 11)
            self._refresh_input_field_heights()
            self._refresh_progress_bar_height()
            self._refresh_nav_bar()
            self._refresh_info_row_heights()
        except Exception:
            pass

    def _apply_medium_styles(self):
        """Apply medium styles for medium screens (1024-1399px wide)"""
        try:
            if hasattr(self, 'clock'):
                scale_font(self.clock, 14)
            self._refresh_input_field_heights()
            self._refresh_progress_bar_height()
            self._refresh_nav_bar()
            self._refresh_info_row_heights()
        except Exception:
            pass

    def _apply_large_styles(self):
        """Apply large styles for large screens (>=1400px wide)"""
        try:
            if hasattr(self, 'clock'):
                scale_font(self.clock, 17)
            self._refresh_input_field_heights()
            self._refresh_progress_bar_height()
            self._refresh_nav_bar()
            self._refresh_info_row_heights()
        except Exception:
            pass

    def _refresh_input_field_heights(self):
        """Dynamically recalculate input field min-heights on resize."""
        try:
            _fh = max(24, int(28 * get_screen_info()[2]))
            for field in getattr(self, 'input_fields', []):
                field.setMinimumHeight(_fh)
        except Exception:
            pass

    def _refresh_info_row_heights(self):
        """Dynamically recalculate info row heights on resize."""
        try:
            if hasattr(self, 'info_rows') and self.info_rows:
                _row_h = scale_value(36, min_ratio=0.7, max_ratio=1.4)
                for row_widget in self.info_rows:
                    row_widget.setFixedHeight(_row_h)
        except Exception:
            pass

    def _refresh_progress_bar_height(self):
        """Dynamically recalculate progress bar height on resize."""
        try:
            if hasattr(self, 'st_progress'):
                _ph = max(10, int(14 * get_screen_info()[2]))
                self.st_progress.setMinimumHeight(_ph)
                self.st_progress.setMaximumHeight(int(_ph * 1.5))
        except Exception:
            pass

    def _refresh_nav_bar(self):
        """
        Pencere yeniden boyutlandırıldığında nav bar'ı günceller.
        setFixedHeight + buton QSS'ini ekrandaki scale_factor'a göre yeniden hesaplar.
        """
        try:
            _nav_h = scale_value(80, min_ratio=0.75, max_ratio=1.4)  # resize handler güncellendi
            nw = getattr(self, '_nav_widget_ref', None)
            if nw is not None:
                nw.setFixedHeight(_nav_h)
                nw.setStyleSheet(RS.nav_widget())
            btn_style = RS.nav_btn()
            for btn in getattr(self, 'nav_buttons', []):
                btn.setStyleSheet(btn_style)
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
                    self.esp_status_buffer_mutex.lock()
                    try:
                        if hasattr(self, 'esp_last_seen'):
                            self.esp_last_seen.pop(coil_id, None)
                    finally:
                        self.esp_status_buffer_mutex.unlock()
            
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
        # esp_last_seen'i de ayni mutex altinda koru
        self.esp_status_buffer_mutex.lock()
        try:
            buffer_snapshot = dict(self.esp_status_buffer)
            # Create a shallow copy to iterate without race conditions
            if hasattr(self, 'esp_last_seen'):
                esp_last_seen_snapshot = dict(self.esp_last_seen)
            else:
                esp_last_seen_snapshot = {}
        finally:
            self.esp_status_buffer_mutex.unlock()
        
        # Bilinen tüm ESP widget'larını kontrol et (mutex dışında)
        for coil_id in list(self.esp_widgets.keys()):
            last_seen = esp_last_seen_snapshot.get(coil_id)
            
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
            
            # Create a shallow copy to iterate without race conditions
            self.esp_status_buffer_mutex.lock()
            try:
                if hasattr(self, 'esp_last_seen'):
                    esp_last_seen_snapshot = dict(self.esp_last_seen)
                else:
                    esp_last_seen_snapshot = {}
            finally:
                self.esp_status_buffer_mutex.unlock()

            # Temizlenecek ESP'leri bul
            for coil_id in list(self.esp_widgets.keys()):
                last_seen = esp_last_seen_snapshot.get(coil_id)
                
                if last_seen is None:
                    # Widget var ama heartbeat hiç gelmemiş veya None set edilmiş
                    stale_coils.append(coil_id)
                    self.logger.debug(f"Removing stale ESP Coil {coil_id} (never seen/no heartbeat)")
                else:
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
                    
                    # esp_status_buffer and esp_last_seen'den kaldır (Thread-Safe)
                    self.esp_status_buffer_mutex.lock()
                    try:
                        self.esp_status_buffer.pop(coil_id, None)
                        if hasattr(self, 'esp_last_seen'):
                            self.esp_last_seen.pop(coil_id, None)
                    finally:
                        self.esp_status_buffer_mutex.unlock()
                    
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
                        self.no_esp_label.setStyleSheet(RS.no_esp_label())
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
                
                # Bobin verilerini kopyala
                graph_mag_data = {}
                graph_temp_data = {}
                graph_per_coil_time = {}
                
                # UYUMSUZ-4 DÜZELTMESİ: Her bobinin kendi zaman dizisini al
                if hasattr(self, 'per_coil_time_data'):
                    for coil_id in active_coils_copy:
                        if coil_id in self.per_coil_time_data and len(self.per_coil_time_data[coil_id]) > 0:
                            graph_per_coil_time[coil_id] = np.array(self.per_coil_time_data[coil_id], dtype=np.float64)
                        if coil_id in self.graph_magnetic_field_data:
                            graph_mag_data[coil_id] = np.array(self.graph_magnetic_field_data[coil_id], dtype=np.float64)
                        if coil_id in self.graph_temperature_data:
                            graph_temp_data[coil_id] = np.array(self.graph_temperature_data[coil_id], dtype=np.float64)
                else:
                    return
            finally:
                self.graph_data_mutex.unlock()

            # Tüm bobinlerin son zaman damgasını bul
            max_timestamp = 0.0
            for coil_id, time_data in graph_per_coil_time.items():
                if len(time_data) > 0 and time_data[-1] > max_timestamp:
                    max_timestamp = time_data[-1]
                    
            if max_timestamp == 0.0:
                return

            # --- 2. Zaman Penceresini Hesapla ---
            start_timestamp = max_timestamp - 10.0  # Son 10 saniye
            
            # Grafiğin X eksenini zorla bu aralığa kilitle (Kayan Pencere Efekti)
            self.plot_item.setXRange(start_timestamp, max_timestamp, padding=0)

            # --- 3. Verileri İşle ve Çiz (Direct Plotting) ---
            for coil_id in active_coils_copy:
                if coil_id not in graph_per_coil_time:
                    continue
                    
                coil_time = graph_per_coil_time[coil_id]
                
                # --- Manyetik Alan ---
                if coil_id in self.mag_field_curves and coil_id in graph_mag_data:
                    raw_y = graph_mag_data[coil_id]
                    min_len = min(len(coil_time), len(raw_y))
                    
                    if min_len > 0:
                        # Sadece son 10 saniye maskesi — round/isfinite kaldırıldı (veri MQTT'de zaten temiz)
                        mask = coil_time[:min_len] >= start_timestamp
                        if mask.any():
                            self.mag_field_curves[coil_id].setData(
                                coil_time[:min_len][mask],
                                raw_y[:min_len][mask]
                            )

                # --- Sıcaklık ---
                if coil_id in self.temp_curves and coil_id in graph_temp_data:
                    raw_y = graph_temp_data[coil_id]
                    min_len = min(len(coil_time), len(raw_y))
                    
                    if min_len > 0:
                        mask = coil_time[:min_len] >= start_timestamp
                        if mask.any():
                            self.temp_curves[coil_id].setData(
                                coil_time[:min_len][mask],
                                raw_y[:min_len][mask]
                            )

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
            
            # 2. GUI-HATA-3 DÜZELTME: esp_last_seen fallback'ı yalnızca buffer'da hiç kaydı
            # olmayan (yani henüz status göndermemiş) ESP'ler için kullan.
            # Buffer'da kaydı var ama mqtt_connected=False ise ekleme - komut kaybolur.
            if hasattr(self, 'esp_last_seen') and self.esp_last_seen:
                # Buffer'daki tüm coil_id'leri topla (mqtt_connected durumundan bağımsız)
                all_buffered_coils = set()
                if hasattr(self, 'esp_status_buffer') and self.esp_status_buffer:
                    try:
                        self.esp_status_buffer_mutex.lock()
                        all_buffered_coils = {
                            int(cid) if isinstance(cid, str) else cid
                            for cid in self.esp_status_buffer.keys()
                            if isinstance(cid, int) or (isinstance(cid, str) and cid.isdigit())
                        }
                    finally:
                        self.esp_status_buffer_mutex.unlock()

                for coil_id in range(1, 9):
                    # Sadece buffer'da hiç kaydı olmayan ESP'lere bak
                    if coil_id not in checked_coils and coil_id not in all_buffered_coils:
                        last_seen = self.esp_last_seen.get(coil_id)
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
    
    
    def keyPressEvent(self, event):
        """
        Handle keyboard shortcuts.
        """
        try:
            # Call parent implementation
            super().keyPressEvent(event)
            
        except Exception as e:
            self.logger.error(f"Key press event handler error: {e}", exc_info=True)
    

def main():
    """
    PEMF GUI ana başlatıcı — Hardware-Aware sürüm.

    ÇAĞRI KURALI:
        Bu fonksiyon doğrudan çalıştırılabilir (python -m gui_pyqt_v11)
        VEYA main.py tarafından High-DPI kurulumu tamamlandıktan sonra
        çağrılabilir.

        main.py'den geliyorsa:
            • QApplication.instance() dolu olacak       → yeni oluşturulmaz
            • app.property("device_profile") dolu olacak → yeniden tespit edilmez
            • primaryScreenChanged zaten bağlı          → tekrar bağlanmaz

        Doğrudan çalıştırılıyorsa (python gui_pyqt_v11.py):
            • QApplication yoksa oluşturulur
            • device_profile yoksa tespit edilir
            • primaryScreenChanged bağlanır
            ⚠ Bu durumda High-DPI env-var'ları önceden set edilmemiş olur;
              doğrudan çalıştırmak geliştirme içindir, production'da main.py
              kullanılmalıdır.
    """
    logger = logging.getLogger("gui_pyqt_v11.main")

    # ── 1. QApplication (mevcut instance varsa yeniden kullan) ──────────────
    app = QApplication.instance()
    if app is None:
        # Doğrudan çalıştırma (python gui_pyqt_v11.py) — geliştirme ortamı
        logger.warning(
            "main() çağrısında QApplication bulunamadı. "
            "Production için main.py kullanın (High-DPI env-var'ları eksik kalacak)."
        )
        app = QApplication(sys.argv)

    # ── 2. DeviceProfile — main.py'den geldiyse hazır, yoksa burada tespit et
    profile: Optional["DeviceProfile"] = app.property("device_profile")

    if profile is None:
        # main.py'siz doğrudan çalıştırma (geliştirme / test)
        logger.info("DeviceProfile bulunamadı — tespit ediliyor...")
        try:
            from utils.device_profile import detect_device_profile, invalidate_profile
            profile = detect_device_profile()
            app.setProperty("device_profile", profile)

            # primaryScreenChanged — main.py yoksa buradan bağla
            if not getattr(app, "_screen_change_bound", False):
                def _on_screen_changed(_screen=None):
                    invalidate_profile()
                    new_p = detect_device_profile(force_refresh=True)
                    app.setProperty("device_profile", new_p)
                    logger.info("Ekran değişti → %s", new_p.category.value)

                app.primaryScreenChanged.connect(_on_screen_changed)
                app._screen_change_bound = True  # Çift bağlanmayı önle

        except Exception as exc:
            logger.warning("DeviceProfile tespit hatası: %s", exc)
            profile = None

    # Profile loglama (her iki çalıştırma yolunda da)
    if profile is not None:
        logger.info(
            "gui_pyqt_v11.main(): %s — %.1f″ — %dx%d px — %.0f DPI",
            profile.category.value,
            profile.diagonal_inches,
            profile.screen_width,
            profile.screen_height,
            profile.physical_dpi,
        )
    else:
        logger.info("gui_pyqt_v11.main(): DeviceProfile yok — varsayılan boyutlar")

    # ── 3. Uygulama ikonu ─────────────────────────────────────────────────
    # (Mevcut kodunuzdan alındı — değiştirilmedi)
    try:
        # resource_path() zaten mevcut gui_pyqt_v11.py içinde tanımlı
        from utils.path_utils import resource_path as _rp
        icon_path = _rp("resources/icons/pemf_heart_emf_icon.ico")
        if os.path.exists(icon_path):
            app.setWindowIcon(QIcon(icon_path))
    except Exception as exc:
        logger.warning("Uygulama ikonu yüklenemedi: %s", exc)

    # ── 4. Splash Screen ──────────────────────────────────────────────────
    # (Mevcut kodunuzdan alındı — değiştirilmedi)
    try:
        from windows.splash_screen import show_splash_screen
        splash = show_splash_screen(app, version=MainWindow.SOFTWARE_VERSION)
        splash.raise_()
        splash.activateWindow()
        app.processEvents()
    except Exception as exc:
        logger.warning("Splash screen açılamadı: %s", exc)
        splash = None

    # ── 5. Veritabanı başlatma ────────────────────────────────────────────
    if splash:
        splash.set_progress(10, "Sistem kaynakları kontrol ediliyor...")
        app.processEvents()
        splash.set_progress(20, "Veritabanı hazırlanıyor...")
        app.processEvents()

    try:
        from utils.path_utils import initialize_database
        initialize_database()
    except Exception as exc:
        logger.error("Veritabanı başlatma hatası: %s", exc)

    # ── 6. Ana pencere oluşturma ──────────────────────────────────────────
    #
    # DEĞİŞİKLİK: MainWindow artık isteğe bağlı device_profile parametresi
    # alıyor.  MainWindow.__init__ bu parametreyi alabiliyorsa doğrudan
    # iletilir; alamıyorsa eski davranış korunur (app.property üzerinden
    # HardwareAwareMixin zaten okuyacak).
    #
    if splash:
        splash.set_progress(30, "Modüller yükleniyor...")
        app.processEvents()

    main_win = MainWindow()
    # NOT: MainWindow.__init__ içinde HardwareAwareMixin._setup_window_for_profile()
    # zaten çağrılıyor.  Burada ek pencere boyutu ayarı YAPMA.

    if splash:
        splash.set_progress(60, "Veritabanı bağlantısı kuruluyor...")
        app.processEvents()
        splash.set_progress(80, "Kullanıcı arayüzü hazırlanıyor...")
        app.processEvents()
        splash.set_progress(90, "Son kontroller yapılıyor...")
        app.processEvents()

    # ── 7. Splash kapat → Ana pencere göster ─────────────────────────────
    def on_loading_finished():
        if splash:
            splash.set_progress(100, "Başlatılıyor!")
            app.processEvents()

        def _finish_loading():
            if splash:
                splash.close()
            main_win.show()
            main_win.setWindowState(Qt.WindowState.WindowActive)
            main_win.raise_()
            main_win.activateWindow()
            main_win.setFocus()

            # Windows: pencereyi ön plana getir
            if sys.platform == "win32":
                try:
                    import ctypes
                    hwnd = int(main_win.winId())
                    ctypes.windll.user32.SetForegroundWindow(hwnd)
                    ctypes.windll.user32.ShowWindow(hwnd, 9)   # SW_RESTORE
                    ctypes.windll.user32.BringWindowToTop(hwnd)
                except Exception:
                    pass
                    
            # Otomatik güncelleme kontrolünü başlat (Açılıştan 4 saniye sonra)
            QTimer.singleShot(4000, main_win.check_for_updates)

        QTimer.singleShot(300, _finish_loading)

    if splash:
        splash.progress_updated.connect(lambda _p: app.processEvents())
    QTimer.singleShot(500, on_loading_finished)

    # ── 8. Kapanış temizliği ──────────────────────────────────────────────
    def cleanup_and_quit():
        try:
            if main_win.isVisible():
                main_win.hide()
            app.processEvents()

            try:
                from windows.splash_screen import show_closing_screen
                from PyQt6.QtCore import QEventLoop
                closing = show_closing_screen(app)
                loop = QEventLoop()
                QTimer.singleShot(1500, loop.quit)
                loop.exec()
                closing.close()
            except Exception:
                pass
        except Exception as exc:
            logger.error("Kapanış hatası: %s", exc)

    app.aboutToQuit.connect(cleanup_and_quit)

    sys.exit(app.exec())


# ─────────────────────────────────────────────────────────────────────────────
# Doğrudan çalıştırma (python gui_pyqt_v11.py) — yalnızca geliştirme amaçlı
# Production'da her zaman main.py kullanın.
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # UYARI: Bu yolda High-DPI env-var'ları ve
    # QApplication.setHighDpiScaleFactorRoundingPolicy() çağrısı eksik.
    # Görsel bozukluk olabilir — yalnızca hızlı test içindir.
    main()
