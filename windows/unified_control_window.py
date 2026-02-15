# -*- coding: utf-8 -*-
"""
Birleşik Kontrol Penceresi - Signal Generator ve Autonomous Mode'u birleştiren modern arayüz

Bu modül, manuel ve otomatik PEMF kontrol modlarını tek bir pencerede birleştirir.
Tedavi hedefleri, frekans, süre ve yoğunluk kontrollerini içerir.

@author: merta
@date: 2025-01-20
"""

import sys
import os
import json
import logging
import time
import threading
import numpy as np
from datetime import datetime
from dataclasses import dataclass
from functools import partial
from typing import List, Optional

# Add parent directory to path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QGroupBox, QLabel, QSpinBox, QDoubleSpinBox, QPushButton,
    QScrollArea, QStatusBar, QApplication, QSizePolicy, 
    QComboBox, QFrame, QMessageBox,
    QTabWidget, QInputDialog
)
from PyQt6.QtCore import Qt, QSettings, pyqtSignal,QTimer, QThread, QUrl
from PyQt6.QtGui import QIcon, QWheelEvent, QDesktopServices


from pemf_gui import  get_image_path
from database.session_manager import get_session_manager
from database.patient_database import get_patient_database
from database.treatment_history_db import TreatmentHistoryDB
from styles import StyleMixin
# Responsive Utils
from utils.responsive_utils import get_screen_info
# AI Mode Controller
try:
    from windows.ai_mode_controller import create_ai_controller, AI_AVAILABLE, AI_IMPORT_ERROR
except Exception as e:
    # Capture the actual import error message so UI can show useful diagnostics
    create_ai_controller = None
    AI_AVAILABLE = False
    AI_IMPORT_ERROR = str(e)

# Custom SpinBox sınıfları - Wheel event'lerini devre dışı bırakmak için
class NoWheelSpinBox(QSpinBox):
    """Wheel event'lerini devre dışı bırakan QSpinBox"""
    def wheelEvent(self, event: QWheelEvent):
        # Wheel event'lerini ignore et, böylece scroll sırasında değer değişmez
        event.ignore()

class NoWheelDoubleSpinBox(QDoubleSpinBox):
    """Wheel event'lerini devre dışı bırakan QDoubleSpinBox"""
    def wheelEvent(self, event: QWheelEvent):
        # Wheel event'lerini ignore et, böylece scroll sırasında değer değişmez
        event.ignore()


@dataclass
class SessionState:
    """
    Memory'de tutulan aktif session bilgileri.
    
    Session sadece stop edildiğinde DB'ye kaydedilir.
    Bu sayede:
    - Çoklu kayıt sorunu çözülür
    - Crash durumunda eksik session kaydı olmaz
    - Gerçek süre hesaplanabilir
    """
    start_time: datetime
    mode: str  # 'automatic' / 'ai' / 'manual'
    patient_info: dict
    target_condition: str
    planned_duration: int  # dakika
    parameters: dict
    connected_coils: List[int]
    
    # Runtime tracking
    is_active: bool = True
    stop_reason: Optional[str] = None  # 'completed' / 'user_stopped' / 'error'
    
    def get_actual_duration_minutes(self) -> float:
        """Gerçek seans süresini dakika cinsinden döndür"""
        if self.is_active:
            elapsed = datetime.now() - self.start_time
        else:
            # Durdurulmuş, son süreyi kullan
            elapsed = datetime.now() - self.start_time
        return elapsed.total_seconds() / 60.0


class AIModelLoadThread(QThread):
    """AI modellerini arka planda yüklemek için QThread (GUI freeze prevention)"""
    models_loaded = pyqtSignal(bool)  # Modeller yüklendiğinde emit edilir
    progress_update = pyqtSignal(str)  # İlerleme mesajları
    error_occurred = pyqtSignal(str)  # Hata oluştuğunda emit edilir
    
    # Retry configuration
    MAX_RETRIES = 3
    RETRY_DELAY_MS = 1000  # Start with 1 second, exponential backoff
    
    def __init__(self, ai_controller, retry_count=0):
        super().__init__()
        self.ai_controller = ai_controller
        self.retry_count = retry_count
        self.stop_requested = False
    
    def run(self):
        """AI modellerini yükle (with retry & exception handling) - Loop-based implementation"""
        for attempt in range(self.MAX_RETRIES + 1):
            try:
                if self.stop_requested:
                    self.error_occurred.emit("Model loading cancelled")
                    return
                
                self.progress_update.emit(f"Model loading attempt {attempt + 1}/{self.MAX_RETRIES + 1}")
                
                success = self.ai_controller.load_models()
                
                if success:
                    self.progress_update.emit("AI modelleri başarıyla yüklendi ✓")
                    self.models_loaded.emit(True)
                    return  # Başarılı, çık
                
                # Son deneme değilse, bekle ve tekrar dene
                if attempt < self.MAX_RETRIES:
                    delay = self.RETRY_DELAY_MS * (2 ** attempt)  # Exponential backoff
                    self.progress_update.emit(f"Retry in {delay}ms (attempt {attempt + 1}/{self.MAX_RETRIES})")
                    self.msleep(delay)
                    
                    if self.stop_requested:
                        self.error_occurred.emit("Model loading cancelled during retry")
                        return
                        
            except Exception as e:
                error_msg = f"Exception loading AI models: {str(e)} (attempt {attempt + 1}/{self.MAX_RETRIES + 1})"
                logging.error(error_msg)
                
                # Son denemede exception, hata emit et
                if attempt >= self.MAX_RETRIES:
                    self.error_occurred.emit(error_msg)
                    self.models_loaded.emit(False)
                    return
                # Son deneme değilse, devam et (retry)
        
        # Tüm denemeler başarısız
        self.error_occurred.emit(f"Failed to load models after {self.MAX_RETRIES + 1} attempts")
        self.models_loaded.emit(False)

class PatientListLoadThread(QThread):
    """Hasta listesini arka planda yüklemek için QThread (Performance Fix)"""
    patients_loaded = pyqtSignal(list)  # Hasta listesi yüklendiğinde emit edilir
    error_occurred = pyqtSignal(str)  # Hata oluştuğunda emit edilir
    
    def __init__(self, app_data_dir):
        super().__init__()
        self.app_data_dir = app_data_dir
    
    def run(self):
        """Arka planda hasta listesini yükle"""
        try:

            db = get_patient_database(self.app_data_dir)
            patients = db.get_all_patients()
            
            # Yeniden eskiye doğru sırala (created_at'e göre ters sıralama)
            patients_sorted = sorted(
                patients,
                key=lambda p: p.get('created_at', ''),
                reverse=True  # En yeni en üstte (yeniden eskiye)
            )
            
            # Sonuçları signal ile gönder
            self.patients_loaded.emit(patients_sorted)
        except Exception as e:
            self.error_occurred.emit(str(e))

class PatientDeleteThread(QThread):
    """Hasta silme işlemlerini arka planda yapmak için QThread (GUI freeze prevention)"""
    delete_finished = pyqtSignal(bool, str)  # success, message
    
    def __init__(self, app_data_dir, patient_ids):
        super().__init__()
        self.app_data_dir = app_data_dir
        self.patient_ids = patient_ids if isinstance(patient_ids, list) else [patient_ids]
        # Logger setup
        from utils.logger_config import get_logger
        self.logger = get_logger('PatientDeleteThread')
    
    def run(self):
        """Arka planda hasta silme işlemi"""
        try:
            from database.patient_database import get_patient_database
            db = get_patient_database(self.app_data_dir)
            
            deleted_count = 0
            for patient_id in self.patient_ids:
                result = db.delete_patient(patient_id)
                if result:
                    deleted_count += 1
            
            if deleted_count == len(self.patient_ids):
                if len(self.patient_ids) == 1:
                    self.delete_finished.emit(True, "Hasta başarıyla silindi.")
                else:
                    self.delete_finished.emit(True, f"{deleted_count} hasta silindi.")
            elif deleted_count > 0:
                self.delete_finished.emit(True, f"{deleted_count}/{len(self.patient_ids)} hasta silindi.")
            else:
                self.delete_finished.emit(False, "Hasta silinirken bir hata oluştu.")
        except Exception as e:
            self.logger.error(f"Hasta silme hatası: {e}", exc_info=True)
            self.delete_finished.emit(False, f"Hata: {str(e)}")

class AICalculationThread(QThread):
    """AI Hesaplamalarını arka planda yapmak için Thread (with graceful shutdown)"""
    calculation_finished = pyqtSignal(dict)  # Sonuçları döner
    error_occurred = pyqtSignal(str)
    
    def __init__(self, ai_controller, ecg_features, sensor_data, context_data):
        super().__init__()
        self.ai_controller = ai_controller
        self.ecg_features = ecg_features
        self.sensor_data = sensor_data
        self.context_data = context_data
        self.stop_requested = False  # Graceful shutdown flag
        
    def run(self):
        try:
            if self.stop_requested:
                self.error_occurred.emit("Calculation cancelled")
                return
            
            # Ağır işlem burada yapılır
            results = self.ai_controller.get_recommendations(
                ecg_features=self.ecg_features,
                sensor_data=self.sensor_data,
                context_data=self.context_data
            )
            
            if not self.stop_requested:
                self.calculation_finished.emit(results)
        except Exception as e:
            if not self.stop_requested:
                self.error_occurred.emit(str(e))

class UnifiedControlWindow(QMainWindow, StyleMixin):
    """
    Birleşik PEMF Kontrol Penceresi
    
    Bu sınıf, manuel ve otomatik PEMF kontrol modlarını tek bir arayüzde birleştirir:
    - Manuel Mod: Bireysel bobinler için detaylı kontrol
    - Otomatik Mod: Tedavi hedeflerine göre önceden tanımlanmış parametreler
    
    Design System entegrasyonu ile merkezi stil yönetimi kullanır.
    """
    
    # === CONSTANTS (Code Quality Fix - Magic Numbers) ===
    # Timeouts
    ESP_HEARTBEAT_TIMEOUT_SEC = 3.0  # ESP timeout süresi (saniye)
    MQTT_COMMAND_TIMEOUT_SEC = 2.0   # MQTT komut timeout (saniye)
    MQTT_COMMAND_MAX_RETRIES = 3     # Max retry count for commands
    
    # Throttling
    SENSOR_UPDATE_THROTTLE_MS = 200  # Sensor UI update throttle (ms)
    CRITICAL_TEMP_THRESHOLD = 60     # Critical temperature (°C)
    CRITICAL_CURRENT_THRESHOLD = 5   # Critical current (A)
    
    # Time conversion
    SECONDS_PER_MINUTE = 60
    MILLISECONDS_PER_SECOND = 1000
    
    # Timer intervals (default values, can be overridden from settings)
    DEFAULT_UNIFIED_1HZ_INTERVAL = 1000      # 1 second
    DEFAULT_ESP_CONNECTION_CHECK_INTERVAL = 3500  # 3.5 seconds
    
    # Command ID
    MAX_COMMAND_ID_COUNTER = 1000000  # Reset counter at 1 million
    
    # Signals
    sendCommandSignal = pyqtSignal(str)
    parametersUpdated = pyqtSignal(dict)
    
    # --- YENİ GÜVENLİ SİNYALLER ---
    # Bu sinyaller, UI'ı güvenli bir şekilde güncellemek için kullanılacak
    # QueuedConnection ile bağlanacak, böylece MQTT thread'inden gelen veriler
    # ana thread'de işlenecek
    _safe_update_status_signal = pyqtSignal(str, dict)  # coil_id (string), status_data
    _safe_handle_ack_signal = pyqtSignal(int, str, bool, dict)  # coil_num, command_id, success, cmd_info
    _safe_show_toast_signal = pyqtSignal(str, str)  # message, toast_type
    _safe_update_sensor_warning_signal = pyqtSignal(int, str, str)  # coil_id, message, warning_type
    # --- YENİ GÜVENLİ SİNYALLER SONU ---
    
    def __init__(self, main_window=None):
        super().__init__()
        self.main_window = main_window
        self.settings = QSettings("Mertacor", "PEMF_GUI")
        
        # Setup logger
        from utils.logger_config import get_logger
        self.logger = get_logger('UnifiedControlWindow')
        
        # State management
        self.current_mode = "automatic"  # "manual" or "automatic"
        self.coil_controls = {}
        self.selected_patient = None  # Seçilen hasta bilgisi
        self.pwm_status = {i: {'running': False, 'freq': 1000, 'duty': 50.0, 'duration': 0} for i in range(1, 9)}
        self.pwm_remaining_time = {i: None for i in range(1, 9)}  # Remaining time in seconds for each coil
        self.coil_connection_status = {i: False for i in range(1, 9)}  # Bobin bağlantı durumu takibi
        self.coil_last_status_time = {i: 0 for i in range(1, 9)}  # Son status mesajı zamanı (heartbeat için)
        # Thread-safe dictionary erişimi için lock'lar
        self.pwm_status_lock = threading.Lock()  # pwm_status yazma işlemleri için
        self.coil_status_lock = threading.Lock()  # coil_connection_status ve coil_last_status_time için
        self.ui_update_lock = threading.Lock()  # last_ui_update_time için thread-safe erişim
        self.pwm_remaining_time_lock = threading.Lock()  # pwm_remaining_time için thread-safe erişim
        # ESP timeout optimizasyonu: ESP 10Hz (100ms) status update yapıyor
        # Network delay + processing: ~100-300ms normal, 3 saniye güvenli margin
        self.ESP_TIMEOUT = self.ESP_HEARTBEAT_TIMEOUT_SEC  # Use class constant
        self.treatment_active = False
        
        # UI Throttling - Sensor data için (Performance Fix)
        self.last_ui_update_time = {}  # {coil_id: timestamp}
        
        # PERFORMANCE FIX: Value change detection - avoid redundant updates
        self._last_sensor_values = {}  # {coil_id: {'temp': float, 'current': float, ...}}
        self._sensor_value_lock = threading.Lock()  # Thread-safe access to sensor cache
        
        # Status update optimizasyonu için önceki durum
        self._last_status_text = None  # Debounce için önceki status text
        
        # MQTT Command Tracking (GUI Stability Fix #4 - QoS 1 + ACK)
        self.pending_commands = {}  # {command_id: {'coil_num', 'command', 'timestamp', 'retry_count'}}
        self.pending_commands_lock = threading.Lock()  # Thread-safe erişim için
        # Command timeout optimizasyonu: 
        # - MQTT network delay: ~50-200ms (local network)
        # - ESP processing: ~10-50ms
        # - ACK QoS 1 ile güvenilir delivery: ~100-300ms toplam
        # - 2 saniye güvenli margin, retry mekanizması var (3 retry = 6 saniye toplam)
        self.command_timeout = self.MQTT_COMMAND_TIMEOUT_SEC  # Use class constant
        self.max_command_retries = self.MQTT_COMMAND_MAX_RETRIES  # Use class constant
        self.command_id_counter = 0
        self.command_id_counter_lock = threading.Lock()  # Thread-safe command_id_counter için
        
        # Timer Optimizasyonu: Configurable interval'lar
        # Timer interval'ları settings'ten okunabilir (default değerler)
        self.timer_intervals = {
            'unified_1hz': 1000,      # Unified 1Hz timer interval (ms) - combines status, command_timeout, treatment_countdown
            'esp_connection': 3500,   # ESP connection check interval (ms) - optimized from 2000ms (heartbeat timeout is 3s)
        }
        
        # Settings'ten timer interval'larını yükle (varsa)
        self._load_timer_intervals()
        
        # Timer Optimization: Unified 1Hz timer (combines status, command_timeout, treatment_countdown)
        # Reduces timer overhead by ~60% (6 timers → 2 timers)
        self.unified_1hz_timer = QTimer(self)  # Parent widget'a bağla
        self.unified_1hz_timer.timeout.connect(self._on_unified_1hz_tick)
        self.unified_1hz_timer.start(self.timer_intervals['unified_1hz'])
        
        # ESP connection heartbeat checker timer (separate for longer interval)
        self.esp_connection_check_timer = QTimer(self)  # Parent widget'a bağla
        self.esp_connection_check_timer.timeout.connect(self._check_esp_connections)
        self.esp_connection_check_timer.start(self.timer_intervals['esp_connection'])
        
        # ✅ ESP stale data cleanup timer (30 seconds interval, removes ESP devices not seen in 90s)
        # Bu timer, retained MQTT messages'dan gelen eski ESP verilerini temizler
        self.esp_cleanup_timer = QTimer(self)  # Parent widget'a bağla
        self.esp_cleanup_timer.timeout.connect(self._cleanup_stale_esp_devices)
        self.esp_cleanup_timer.start(30000)  # 30 saniyede bir cleanup
        
        # PWM countdown merged into unified_1hz_timer (Performance Optimization - Timer Merge)
        # No separate timer needed - handled in _on_unified_1hz_tick()
        
        # Treatment timer for timeout (one-shot timer, started when treatment begins)
        self.treatment_timer = QTimer(self)
        self.treatment_timer.setSingleShot(True)
        # Timer bittiğinde stop_treatment'ı 'completed' reason ile çağır
        self.treatment_timer.timeout.connect(lambda: self.stop_treatment(stop_reason='completed'))
        
        # Session manager ve auto logger başlat
        # Get app_data_dir from main_window or create it
        if main_window and hasattr(main_window, 'app_data_dir'):
            self.app_data_dir = main_window.app_data_dir
        else:
            from windows.gui_pyqt_v11 import get_app_data_directory
            self.app_data_dir = get_app_data_directory()
        
        self.session_manager = get_session_manager(self.app_data_dir)
        # Auto logger is created by session_manager, get it from there
        from database.session_manager import AutoSessionLogger
        self.auto_logger = AutoSessionLogger(self.session_manager)
        self.current_session_id = None
        
        # NEW: TreatmentHistoryDB for simplified session recording
        self.db = TreatmentHistoryDB(self.app_data_dir)
        
        # NEW: Active session state (memory only, saved on stop)
        self.active_session: Optional[SessionState] = None
        
        # Patient list load thread (None until first load)
        self._patient_list_thread = None
        
        # MQTT sinyal bağlantıları
        self._connect_mqtt_signals()
        
        # --- YENİ GÜVENLİ SİNYAL BAĞLANTILARI ---
        # QueuedConnection kullanarak MQTT thread'inden gelen verileri
        # ana thread'de işlemek için güvenli sinyaller
        self._safe_update_status_signal.connect(
            self._safe_on_coil_status_updated, 
            Qt.ConnectionType.QueuedConnection
        )
        self._safe_handle_ack_signal.connect(
            self._safe_handle_command_ack, 
            Qt.ConnectionType.QueuedConnection
        )
        self._safe_show_toast_signal.connect(
            self._safe_show_toast_callback, 
            Qt.ConnectionType.QueuedConnection
        )
        self._safe_update_sensor_warning_signal.connect(
            self._safe_update_sensor_warning, 
            Qt.ConnectionType.QueuedConnection
        )
        # --- YENİ GÜVENLİ SİNYAL BAĞLANTILARI SONU ---
        
        self.setWindowTitle("Birleşik PEMF Kontrol Merkezi")
        
        # Window flags to enable maximize and resize
        self.setWindowFlags(Qt.WindowType.Window |
                           Qt.WindowType.WindowMinimizeButtonHint |
                           Qt.WindowType.WindowMaximizeButtonHint |
                           Qt.WindowType.WindowCloseButtonHint)
        
        # Responsive window sizing
        self._setup_responsive_window()
        
        # Enable responsive features
        self._enable_responsive_features()
        
        # Enable accessibility features
        self._enable_accessibility_features()
        
        self._apply_styles()
        self._init_ui()
        self._load_settings()
        
        # Initialize AI controller
        self._init_ai_controller()
        
        # Hasta bilgilerini güncelle
        self.update_patient_info()
        
    def _apply_styles(self):
        """Modern, responsive stil uygula - Design System entegrasyonu"""
        # Custom styles'i ekleyerek apply_theme çağır
        custom_styles = self.get_custom_styles()
        if custom_styles:
            full_stylesheet = self.get_default_stylesheet() + "\n" + custom_styles
            self.apply_theme(stylesheet=full_stylesheet)
        else:
            self.apply_theme()  # StyleMixin'den gelen metod
    
    def get_custom_styles(self) -> str:
        """
        Property selector'ları içeren custom stiller (Performance Fix - CSS Parsing Optimization)
        setStyleSheet yerine setProperty kullanarak CSS parse overhead'ini azaltır
        """
        return """
        /* Coil Status LED - Property Selector (Performance Fix) */
        QLabel[status_led="running"] {
            color: #22c55e;
            font-size: 12px;
        }
        QLabel[status_led="stopped"] {
            color: #ef4444;
            font-size: 12px;
        }
        
        /* Coil Status Container - Property Selector (Performance Fix) */
        QWidget[status_container="running"] {
            background: rgba(34, 197, 94, 0.1);
            border-radius: 12px;
            border: 1px solid rgba(34, 197, 94, 0.3);
        }
        QWidget[status_container="stopped"] {
            background: rgba(239, 68, 68, 0.1);
            border-radius: 12px;
            border: 1px solid rgba(239, 68, 68, 0.3);
        }
        
        /* Connection Status Label - Property Selector (Performance Fix #1) */
        QLabel[conn_status="connected"] {
            color: #22c55e;
            font-size: 12px;
            font-weight: bold;
        }
        QLabel[conn_status="disconnected"] {
            color: #ef4444;
            font-size: 12px;
            font-weight: bold;
        }
        QLabel[conn_status="unknown"] {
            color: #f59e0b;
            font-size: 12px;
            font-weight: bold;
        }
        
        /* Temperature Status Label - Property Selector (Performance Fix) */
        QLabel[temp_status="critical"] {
            color: #ef4444;
            font-size: 11px;
            font-weight: 600;
        }
        QLabel[temp_status="warning"] {
            color: #f59e0b;
            font-size: 11px;
            font-weight: 600;
        }
        QLabel[temp_status="normal"] {
            color: #10b981;
            font-size: 11px;
            font-weight: 600;
        }
        """
        
    def _init_ui(self):
        """Ana kullanıcı arayüzünü oluştur"""
        # Ana widget ve layout
        main_widget = QWidget(self)
        self.setCentralWidget(main_widget)
        
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(24, 24, 24, 24)
        main_layout.setSpacing(24)
        
        # Header section
        self._create_header(main_layout)
        
        # Tab widget for different modes
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabPosition(QTabWidget.TabPosition.North)
        
        # Otomatik Mod Tab
        self.automatic_tab = self._create_automatic_tab()
        automatic_tab_icon = QIcon(get_image_path("target.svg"))
        self.tab_widget.addTab(self.automatic_tab, automatic_tab_icon, " Otomatik Mod")
        
        # Manuel Mod Tab
        self.manual_tab = self._create_manual_tab()
        manual_tab_icon = QIcon(get_image_path("settings.svg"))
        self.tab_widget.addTab(self.manual_tab, manual_tab_icon, " Manuel Mod")
        
        # AI Mod Tab
        self.ai_tab = self._create_ai_tab()
        ai_tab_icon = QIcon(get_image_path("activity.svg"))  # or create custom AI icon
        self.tab_widget.addTab(self.ai_tab, ai_tab_icon, " PEMF AI Mod")
        
        # Tab değişikliği sinyali
        self.tab_widget.currentChanged.connect(self._on_tab_changed)
        
        main_layout.addWidget(self.tab_widget)
        
        # Status bar
        self.status_bar = QStatusBar()
        self.status_bar.setStyleSheet("""
            QStatusBar {
                background: rgba(0, 0, 0, 0.3);
                color: rgba(255, 255, 255, 0.8);
                border-top: 1px solid rgba(255, 255, 255, 0.1);
                padding: 8px;
            }
        """)
        self.status_bar.showMessage("Sistem hazır")
        self.setStatusBar(self.status_bar)
        
    def _create_header(self, parent_layout):
        """Modern header bölümünü oluştur"""
        header_frame = QFrame()
        header_frame.setProperty("class", "card-elevated")
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(24, 16, 24, 16)
        header_layout.setSpacing(20)
        
        # Sol taraf - Başlık ve açıklama
        left_layout = QVBoxLayout()
        left_layout.setSpacing(8)
        
        # Modern başlık tasarımı
        title_container = QWidget()
        title_container_layout = QHBoxLayout(title_container)
        title_container_layout.setContentsMargins(0, 0, 0, 0)
        title_container_layout.setSpacing(12)
        
        # Icon
        icon_label = QLabel()
        icon_label.setPixmap(QIcon(get_image_path("intensity.svg")).pixmap(32, 32))
        icon_label.setStyleSheet("""
            color: #6366f1;
            background: rgba(99, 102, 241, 0.1);
            border-radius: 12px;
            padding: 8px;
            min-width: 48px;
            max-width: 48px;
            min-height: 48px;
            max-height: 48px;
        """)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Başlık ve alt başlık
        title_text_layout = QVBoxLayout()
        title_text_layout.setSpacing(4)
        
        title_label = QLabel("PEMF Kontrol Merkezi")
        title_label.setStyleSheet("""
            font-size: 32px;
            font-weight: 800;
            color: white;
            margin: 0;
            letter-spacing: -0.5px;
        """)
        
        subtitle_label = QLabel("Birleşik manuel ve otomatik seans kontrol sistemi")
        subtitle_label.setStyleSheet("""
            font-size: 16px;
            color: rgba(255, 255, 255, 0.7);
            margin: 0;
            font-weight: 500;
        """)
        
        title_text_layout.addWidget(title_label)
        title_text_layout.addWidget(subtitle_label)
        
        title_container_layout.addWidget(icon_label)
        title_container_layout.addLayout(title_text_layout)
        
        left_layout.addWidget(title_container)
        header_layout.addLayout(left_layout, stretch=1)
        
        # Sağ taraf - Durum ve hasta bilgileri
        right_layout = QVBoxLayout()
        right_layout.setAlignment(Qt.AlignmentFlag.AlignRight)
        
        # Modern sistem durumu
        status_widget = QWidget()
        status_layout = QHBoxLayout(status_widget)
        status_layout.setContentsMargins(16, 12, 16, 12)
        status_layout.setSpacing(12)
        
        # Status icon
        status_icon_container = QWidget()
        status_icon_container.setFixedSize(32, 32)
        status_icon_container.setStyleSheet("""
            background: rgba(34, 197, 94, 0.2);
            border-radius: 16px;
            border: 2px solid rgba(34, 197, 94, 0.4);
        """)
        
        status_icon_layout = QHBoxLayout(status_icon_container)
        status_icon_layout.setContentsMargins(0, 0, 0, 0)
        
        self.status_dot = QLabel("✓")
        self.status_dot.setStyleSheet("color: #22c55e; font-size: 16px; font-weight: bold;")
        self.status_dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status_icon_layout.addWidget(self.status_dot)
        
        # Status text
        status_text_layout = QVBoxLayout()
        status_text_layout.setSpacing(2)
        
        self.status_text = QLabel("Sistem Hazır")
        self.status_text.setStyleSheet("color: #ffffff; font-size: 14px; font-weight: 700;")
        
        self.status_subtext = QLabel("Tüm sistemler çalışıyor")
        self.status_subtext.setStyleSheet("color: rgba(255, 255, 255, 0.6); font-size: 12px;")
        
        status_text_layout.addWidget(self.status_text)
        status_text_layout.addWidget(self.status_subtext)
        
        status_layout.addWidget(status_icon_container)
        status_layout.addLayout(status_text_layout)
        status_layout.addStretch()
        
        status_widget.setStyleSheet("""
            background: rgba(34, 197, 94, 0.08);
            border-radius: 16px;
            border: 1px solid rgba(34, 197, 94, 0.2);
        """)
        
        # Modern hasta bilgileri
        self.patient_info_widget = QWidget()
        patient_info_layout = QHBoxLayout(self.patient_info_widget)
        patient_info_layout.setContentsMargins(16, 12, 16, 12)
        patient_info_layout.setSpacing(12)
        
        # Parametre tablosu butonu (hasta bilgisinin solunda)
        self.param_table_button = QPushButton("📊 Parametre Tablosu")
        self.param_table_button.setStyleSheet("""
            QPushButton {
                background: rgba(102, 126, 234, 0.15);
                border: 1px solid rgba(102, 126, 234, 0.3);
                border-radius: 12px;
                padding: 8px 16px;
                color: #ffffff;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: rgba(102, 126, 234, 0.25);
                border: 1px solid rgba(102, 126, 234, 0.5);
            }
            QPushButton:pressed {
                background: rgba(102, 126, 234, 0.35);
            }
        """)
        self.param_table_button.clicked.connect(self.show_parameter_table)
        patient_info_layout.addWidget(self.param_table_button)
        
        # Patient icon
        patient_icon_container = QWidget()
        patient_icon_container.setFixedSize(32, 32)
        patient_icon_container.setStyleSheet("""
            background: rgba(59, 130, 246, 0.2);
            border-radius: 16px;
            border: 2px solid rgba(59, 130, 246, 0.4);
        """)
        
        patient_icon_layout = QHBoxLayout(patient_icon_container)
        patient_icon_layout.setContentsMargins(0, 0, 0, 0)
        
        patient_icon = QLabel()
        patient_icon.setPixmap(QIcon(get_image_path("pemf_heart_icon.png")).pixmap(16, 16))
        patient_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        patient_icon_layout.addWidget(patient_icon)
        
        # Patient info text
        patient_text_layout = QVBoxLayout()
        patient_text_layout.setSpacing(2)
        
        self.patient_info_label = QLabel("Hasta Bilgisi")
        self.patient_info_label.setStyleSheet("color: #ffffff; font-size: 14px; font-weight: 700;")
        
        self.patient_status_label = QLabel("Hasta kaydedilmedi")
        self.patient_status_label.setStyleSheet("color: rgba(255, 255, 255, 0.6); font-size: 12px;")
        
        patient_text_layout.addWidget(self.patient_info_label)
        patient_text_layout.addWidget(self.patient_status_label)
        
        patient_info_layout.addWidget(patient_icon_container)
        patient_info_layout.addLayout(patient_text_layout)
        patient_info_layout.addStretch()
        
        self.patient_info_widget.setStyleSheet("""
            background: rgba(59, 130, 246, 0.08);
            border-radius: 16px;
            border: 1px solid rgba(59, 130, 246, 0.2);
        """)
        
        right_layout.addWidget(status_widget)
        right_layout.addWidget(self.patient_info_widget)
        header_layout.addLayout(right_layout)
        
        parent_layout.addWidget(header_frame)
        
    def _create_automatic_tab(self):
        """Otomatik mod tab'ını oluştur"""
        tab_widget = QWidget()
        tab_layout = QVBoxLayout(tab_widget)
        tab_layout.setContentsMargins(24, 24, 24, 24)
        tab_layout.setSpacing(24)
        
        # Scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent; border: none;")
        
        container = QWidget()
        scroll.setWidget(container)
        content_layout = QVBoxLayout(container)
        content_layout.setContentsMargins(0, 0, 20, 0)
        content_layout.setSpacing(20)
        
        # Hasta Seçimi (YENİ - Otomatik kontrol kısmının üstüne eklendi)
        patient_group = QGroupBox()
        patient_group.setTitle("👤 Hasta Seçimi")
        patient_layout = QVBoxLayout(patient_group)
        patient_layout.setContentsMargins(24, 28, 24, 24)
        patient_layout.setSpacing(16)
        
        # Hasta seçimi için görsel container
        patient_selection_container = QWidget()
        patient_selection_container.setStyleSheet("""
            QWidget {
                background: rgba(139, 92, 246, 0.08);
                border: 1px solid rgba(139, 92, 246, 0.2);
                border-radius: 12px;
                padding: 12px;
            }
        """)
        patient_selection_layout = QHBoxLayout(patient_selection_container)
        patient_selection_layout.setContentsMargins(16, 12, 16, 12)
        patient_selection_layout.setSpacing(12)
        
        # Hasta ikonu
        patient_icon_label = QLabel("👤")
        patient_icon_label.setStyleSheet("""
            font-size: 20px;
            color: #8b5cf6;
            background: rgba(139, 92, 246, 0.15);
            border-radius: 8px;
            padding: 8px;
            min-width: 36px;
            max-width: 36px;
            min-height: 36px;
            max-height: 36px;
        """)
        patient_icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Combo box container
        patient_combo_container = QWidget()
        patient_combo_layout = QVBoxLayout(patient_combo_container)
        patient_combo_layout.setContentsMargins(0, 0, 0, 0)
        patient_combo_layout.setSpacing(4)
        
        patient_label = QLabel("Hasta Seçin:")
        patient_label.setStyleSheet("font-weight: 600; color: #8b5cf6; font-size: 14px;")
        
        self.patient_combo = QComboBox()
        self.patient_combo.setStyleSheet("""
            QComboBox {
                background: rgba(255, 255, 255, 0.12);
                border: 2px solid rgba(139, 92, 246, 0.3);
                border-radius: 8px;
                padding: 10px 12px;
                font-size: 14px;
                color: #ffffff;
                min-height: 24px;
                font-weight: 500;
            }
            QComboBox:focus {
                border: 2px solid rgba(139, 92, 246, 0.8);
                background: rgba(255, 255, 255, 0.18);
            }
        """)
        self.patient_combo.currentIndexChanged.connect(self._on_patient_selected)
        
        patient_combo_layout.addWidget(patient_label)
        patient_combo_layout.addWidget(self.patient_combo)
        
        patient_selection_layout.addWidget(patient_icon_label)
        patient_selection_layout.addWidget(patient_combo_container, stretch=1)
        
        patient_layout.addWidget(patient_selection_container)
        
        # Silme butonları container
        patient_actions_container = QWidget()
        patient_actions_layout = QHBoxLayout(patient_actions_container)
        patient_actions_layout.setContentsMargins(0, 0, 0, 0)
        patient_actions_layout.setSpacing(8)
        
        # Seçili hastayı sil butonu
        self.delete_selected_patient_btn = QPushButton("Seçili Hastayı Sil")
        self.delete_selected_patient_btn.setStyleSheet("""
            QPushButton {
                background: rgba(239, 68, 68, 0.2);
                border: 2px solid rgba(239, 68, 68, 0.4);
                border-radius: 8px;
                padding: 8px 16px;
                font-size: 13px;
                color: #ffffff;
                font-weight: 600;
            }
            QPushButton:hover {
                background: rgba(239, 68, 68, 0.3);
                border: 2px solid rgba(239, 68, 68, 0.6);
            }
            QPushButton:pressed {
                background: rgba(239, 68, 68, 0.4);
            }
            QPushButton:disabled {
                background: rgba(239, 68, 68, 0.1);
                border: 2px solid rgba(239, 68, 68, 0.2);
                color: rgba(255, 255, 255, 0.4);
            }
        """)
        self.delete_selected_patient_btn.clicked.connect(self._delete_selected_patient)
        self.delete_selected_patient_btn.setEnabled(False)  # Başlangıçta devre dışı
        
        # Tümünü sil butonu
        self.delete_all_patients_btn = QPushButton("Tümünü Sil")
        self.delete_all_patients_btn.setStyleSheet("""
            QPushButton {
                background: rgba(220, 38, 38, 0.2);
                border: 2px solid rgba(220, 38, 38, 0.4);
                border-radius: 8px;
                padding: 8px 16px;
                font-size: 13px;
                color: #ffffff;
                font-weight: 600;
            }
            QPushButton:hover {
                background: rgba(220, 38, 38, 0.3);
                border: 2px solid rgba(220, 38, 38, 0.6);
            }
            QPushButton:pressed {
                background: rgba(220, 38, 38, 0.4);
            }
            QPushButton:disabled {
                background: rgba(220, 38, 38, 0.1);
                border: 2px solid rgba(220, 38, 38, 0.2);
                color: rgba(255, 255, 255, 0.4);
            }
        """)
        self.delete_all_patients_btn.clicked.connect(self._delete_all_patients)
        
        patient_actions_layout.addWidget(self.delete_selected_patient_btn)
        patient_actions_layout.addWidget(self.delete_all_patients_btn)
        patient_actions_layout.addStretch()
        
        patient_layout.addWidget(patient_actions_container)
        content_layout.addWidget(patient_group)
        
        # Hasta listesini yükle
        self._load_patient_list()
        
        # Görsel ayırıcı
        separator0 = QFrame()
        separator0.setFrameShape(QFrame.Shape.HLine)
        separator0.setStyleSheet("background: rgba(255, 255, 255, 0.1); margin: 8px 0;")
        content_layout.addWidget(separator0)
        
        # Tedavi Hedefi Seçimi
        target_group = QGroupBox()
        target_group.setTitle("🎯 Seans Hedefi")
        target_layout = QVBoxLayout(target_group)
        target_layout.setContentsMargins(24, 28, 24, 24)
        target_layout.setSpacing(16)
        
        # Tedavi hedefi seçimi için görsel container
        target_selection_container = QWidget()
        target_selection_container.setStyleSheet("""
            QWidget {
                background: rgba(99, 102, 241, 0.08);
                border: 1px solid rgba(99, 102, 241, 0.2);
                border-radius: 12px;
                padding: 12px;
            }
        """)
        target_selection_layout = QHBoxLayout(target_selection_container)
        target_selection_layout.setContentsMargins(16, 12, 16, 12)
        target_selection_layout.setSpacing(12)
        
        # Tedavi hedefi ikonu
        target_icon_label = QLabel("🏥")
        target_icon_label.setStyleSheet("""
            font-size: 20px;
            color: #6366f1;
            background: rgba(99, 102, 241, 0.15);
            border-radius: 8px;
            padding: 8px;
            min-width: 36px;
            max-width: 36px;
            min-height: 36px;
            max-height: 36px;
        """)
        target_icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Combo box container
        combo_container = QWidget()
        combo_layout = QVBoxLayout(combo_container)
        combo_layout.setContentsMargins(0, 0, 0, 0)
        combo_layout.setSpacing(4)
        
        target_label = QLabel("Seans Hedefi Seçin:")
        target_label.setStyleSheet("font-weight: 600; color: #6366f1; font-size: 14px;")
        
        self.target_combo = QComboBox()
        self.target_combo.addItems([
            "🦴 Kronik Artrit",
            "🦴 Osteoartrit",
            "🔥 İnflamasyon",
            "🩹 Kırık İyileşmesi",
            "🏥 Post-op Yara İyileşmesi",
            "🧵 Doku İyileşmesi",
            "🧠 Anksiyete/Stres",
            "💪 Kas Gerginliği/Spazm",
            "🧠 Nörolojik (IVDD, Nöropati)",
            "😌 Genel Rahatlama/Wellness",
            "💧 Ödematöz Dokular",
            "🔗 Tendon/Ligament Yaralanması"
        ])
        self.target_combo.currentTextChanged.connect(self.update_automatic_parameters)
        self.target_combo.setStyleSheet("""
            QComboBox {
                background: rgba(255, 255, 255, 0.12);
                border: 2px solid rgba(99, 102, 241, 0.3);
                border-radius: 8px;
                padding: 10px 12px;
                font-size: 14px;
                color: #ffffff;
                min-height: 24px;
                font-weight: 500;
            }
            QComboBox:focus {
                border: 2px solid rgba(99, 102, 241, 0.8);
                background: rgba(255, 255, 255, 0.18);
            }
        """)
        
        combo_layout.addWidget(target_label)
        combo_layout.addWidget(self.target_combo)
        
        target_selection_layout.addWidget(target_icon_label)
        target_selection_layout.addWidget(combo_container, stretch=1)
        
        target_layout.addWidget(target_selection_container)
        content_layout.addWidget(target_group)
        
        # Görsel ayırıcı
        separator1 = QFrame()
        separator1.setFrameShape(QFrame.Shape.HLine)
        separator1.setStyleSheet("background: rgba(255, 255, 255, 0.1); margin: 8px 0;")
        content_layout.addWidget(separator1)
        
        # Otomatik Parametreler
        auto_params_group = QGroupBox()
        auto_params_group.setTitle("⚙️ Otomatik Parametreler")
        auto_params_layout = QVBoxLayout(auto_params_group)
        auto_params_layout.setContentsMargins(24, 28, 24, 24)
        auto_params_layout.setSpacing(16)
        
        # Frekans parametresi
        freq_container = QWidget()
        freq_container.setStyleSheet("""
            QWidget {
                background: rgba(99, 102, 241, 0.08);
                border: 1px solid rgba(99, 102, 241, 0.2);
                border-radius: 12px;
                padding: 12px;
            }
        """)
        freq_layout = QHBoxLayout(freq_container)
        freq_layout.setContentsMargins(16, 12, 16, 12)
        freq_layout.setSpacing(12)
        
        freq_icon = QLabel("📊")
        freq_icon.setStyleSheet("""
            font-size: 18px;
            background: rgba(99, 102, 241, 0.15);
            border-radius: 8px;
            padding: 8px;
            min-width: 32px;
            max-width: 32px;
            min-height: 32px;
            max-height: 32px;
        """)
        freq_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        freq_content = QWidget()
        freq_content_layout = QVBoxLayout(freq_content)
        freq_content_layout.setContentsMargins(0, 0, 0, 0)
        freq_content_layout.setSpacing(4)
        
        freq_label = QLabel("Frekans:")
        freq_label.setStyleSheet("font-weight: 600; color: #6366f1; font-size: 14px;")
        
        self.auto_frequency_spin = NoWheelDoubleSpinBox()
        self.auto_frequency_spin.setRange(0.1, 1000.0)
        self.auto_frequency_spin.setValue(10.0)
        self.auto_frequency_spin.setSuffix(" Hz")
        self.auto_frequency_spin.setStyleSheet("""
            QDoubleSpinBox {
                background: rgba(255, 255, 255, 0.12);
                border: 2px solid rgba(99, 102, 241, 0.3);
                border-radius: 8px;
                padding: 8px 12px;
                font-size: 13px;
                color: #ffffff;
                min-height: 20px;
                font-weight: 500;
            }
            QDoubleSpinBox:focus {
                border: 2px solid rgba(99, 102, 241, 0.8);
                background: rgba(255, 255, 255, 0.18);
            }
        """)
        
        freq_content_layout.addWidget(freq_label)
        freq_content_layout.addWidget(self.auto_frequency_spin)
        
        freq_layout.addWidget(freq_icon)
        freq_layout.addWidget(freq_content, stretch=1)
        
        auto_params_layout.addWidget(freq_container)
        
        # Süre parametresi
        duration_container = QWidget()
        duration_container.setStyleSheet("""
            QWidget {
                background: rgba(16, 185, 129, 0.08);
                border: 1px solid rgba(16, 185, 129, 0.2);
                border-radius: 12px;
                padding: 12px;
            }
        """)
        duration_layout = QHBoxLayout(duration_container)
        duration_layout.setContentsMargins(16, 12, 16, 12)
        duration_layout.setSpacing(12)
        
        duration_icon = QLabel("⏱️")
        duration_icon.setStyleSheet("""
            font-size: 18px;
            background: rgba(16, 185, 129, 0.15);
            border-radius: 8px;
            padding: 8px;
            min-width: 32px;
            max-width: 32px;
            min-height: 32px;
            max-height: 32px;
        """)
        duration_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        duration_content = QWidget()
        duration_content_layout = QVBoxLayout(duration_content)
        duration_content_layout.setContentsMargins(0, 0, 0, 0)
        duration_content_layout.setSpacing(4)
        
        duration_label = QLabel("Süre:")
        duration_label.setStyleSheet("font-weight: 600; color: #10b981; font-size: 14px;")
        
        self.auto_duration_spin = NoWheelSpinBox()
        self.auto_duration_spin.setRange(1, 9999)
        self.auto_duration_spin.setValue(30)
        self.auto_duration_spin.setSuffix(" dakika")
        self.auto_duration_spin.setStyleSheet("""
            QSpinBox {
                background: rgba(255, 255, 255, 0.12);
                border: 2px solid rgba(16, 185, 129, 0.3);
                border-radius: 8px;
                padding: 8px 12px;
                font-size: 13px;
                color: #ffffff;
                min-height: 20px;
                font-weight: 500;
            }
            QSpinBox:focus {
                border: 2px solid rgba(16, 185, 129, 0.8);
                background: rgba(255, 255, 255, 0.18);
            }
        """)
        
        duration_content_layout.addWidget(duration_label)
        duration_content_layout.addWidget(self.auto_duration_spin)
        
        duration_layout.addWidget(duration_icon)
        duration_layout.addWidget(duration_content, stretch=1)
        
        auto_params_layout.addWidget(duration_container)
        
        # Yoğunluk parametresi
        intensity_container = QWidget()
        intensity_container.setStyleSheet("""
            QWidget {
                background: rgba(245, 158, 11, 0.08);
                border: 1px solid rgba(245, 158, 11, 0.2);
                border-radius: 12px;
                padding: 12px;
            }
        """)
        intensity_layout = QHBoxLayout(intensity_container)
        intensity_layout.setContentsMargins(16, 12, 16, 12)
        intensity_layout.setSpacing(12)
        
        intensity_icon = QLabel("⚡")
        intensity_icon.setStyleSheet("""
            font-size: 18px;
            background: rgba(245, 158, 11, 0.15);
            border-radius: 8px;
            padding: 8px;
            min-width: 32px;
            max-width: 32px;
            min-height: 32px;
            max-height: 32px;
        """)
        intensity_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        intensity_content = QWidget()
        intensity_content_layout = QVBoxLayout(intensity_content)
        intensity_content_layout.setContentsMargins(0, 0, 0, 0)
        intensity_content_layout.setSpacing(4)
        
        intensity_label = QLabel("Yoğunluk:")
        intensity_label.setStyleSheet("font-weight: 600; color: #f59e0b; font-size: 14px;")
        
        self.auto_intensity_spin = NoWheelDoubleSpinBox()  # mT değerleri için ondalık gerekli
        self.auto_intensity_spin.setRange(0.1, 5.0)  # Bilimsel aralık: 0.1-5.0 mT (güvenli veteriner PEMF aralığı)
        self.auto_intensity_spin.setDecimals(1)  # 1 ondalık basamak
        self.auto_intensity_spin.setSingleStep(0.1)  # 0.1 mT artışlar
        self.auto_intensity_spin.setValue(1.0)  # Güvenli başlangıç değeri
        self.auto_intensity_spin.setSuffix(" mT")
        self.auto_intensity_spin.setStyleSheet("""
            QDoubleSpinBox {
                background: rgba(255, 255, 255, 0.12);
                border: 2px solid rgba(245, 158, 11, 0.3);
                border-radius: 8px;
                padding: 8px 12px;
                font-size: 13px;
                color: #ffffff;
                min-height: 20px;
                font-weight: 500;
            }
            QSpinBox:focus {
                border: 2px solid rgba(245, 158, 11, 0.8);
                background: rgba(255, 255, 255, 0.18);
            }
        """)
        
        intensity_content_layout.addWidget(intensity_label)
        intensity_content_layout.addWidget(self.auto_intensity_spin)
        
        intensity_layout.addWidget(intensity_icon)
        intensity_layout.addWidget(intensity_content, stretch=1)
        
        auto_params_layout.addWidget(intensity_container)
        
        # Duty Cycle parametresi
        duty_cycle_container = QWidget()
        duty_cycle_container.setStyleSheet("""
            QWidget {
                background: rgba(139, 92, 246, 0.08);
                border: 1px solid rgba(139, 92, 246, 0.2);
                border-radius: 12px;
                padding: 12px;
            }
        """)
        duty_cycle_layout = QHBoxLayout(duty_cycle_container)
        duty_cycle_layout.setContentsMargins(16, 12, 16, 12)
        duty_cycle_layout.setSpacing(12)
        
        duty_cycle_icon = QLabel("🔄")
        duty_cycle_icon.setStyleSheet("""
            font-size: 18px;
            background: rgba(139, 92, 246, 0.15);
            border-radius: 8px;
            padding: 8px;
            min-width: 32px;
            max-width: 32px;
            min-height: 32px;
            max-height: 32px;
        """)
        duty_cycle_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        duty_cycle_content = QWidget()
        duty_cycle_content_layout = QVBoxLayout(duty_cycle_content)
        duty_cycle_content_layout.setContentsMargins(0, 0, 0, 0)
        duty_cycle_content_layout.setSpacing(4)
        
        duty_cycle_label = QLabel("Duty Cycle:")
        duty_cycle_label.setStyleSheet("font-weight: 600; color: #8b5cf6; font-size: 14px;")
        
        self.auto_duty_cycle_spin = NoWheelDoubleSpinBox()
        self.auto_duty_cycle_spin.setRange(1.0, 99.0)
        self.auto_duty_cycle_spin.setDecimals(1)
        self.auto_duty_cycle_spin.setSingleStep(0.1)
        self.auto_duty_cycle_spin.setValue(50.0)
        self.auto_duty_cycle_spin.setSuffix(" %")
        self.auto_duty_cycle_spin.setStyleSheet("""
            QDoubleSpinBox {
                background: rgba(255, 255, 255, 0.12);
                border: 2px solid rgba(139, 92, 246, 0.3);
                border-radius: 8px;
                padding: 8px 12px;
                font-size: 13px;
                color: #ffffff;
                min-height: 20px;
                font-weight: 500;
            }
            QDoubleSpinBox:focus {
                border: 2px solid rgba(139, 92, 246, 0.8);
                background: rgba(255, 255, 255, 0.18);
            }
        """)
        
        duty_cycle_content_layout.addWidget(duty_cycle_label)
        duty_cycle_content_layout.addWidget(self.auto_duty_cycle_spin)
        
        duty_cycle_layout.addWidget(duty_cycle_icon)
        duty_cycle_layout.addWidget(duty_cycle_content, stretch=1)
        
        auto_params_layout.addWidget(duty_cycle_container)
        
        content_layout.addWidget(auto_params_group)
        
        # Görsel ayırıcı
        separator2 = QFrame()
        separator2.setFrameShape(QFrame.Shape.HLine)
        separator2.setStyleSheet("background: rgba(255, 255, 255, 0.1); margin: 8px 0;")
        content_layout.addWidget(separator2)
        
        # Otomatik Kontrol Butonları
        auto_control_group = QGroupBox()
        auto_control_group.setTitle("🔄 Otomatik Kontrol")
        auto_control_layout = QVBoxLayout(auto_control_group)
        auto_control_layout.setContentsMargins(24, 28, 24, 24)
        auto_control_layout.setSpacing(16)
        
        # Başlat butonu container
        start_container = QWidget()
        start_container.setStyleSheet("""
            QWidget {
                background: rgba(34, 197, 94, 0.08);
                border: 1px solid rgba(34, 197, 94, 0.2);
                border-radius: 12px;
                padding: 12px;
            }
        """)
        start_layout = QHBoxLayout(start_container)
        start_layout.setContentsMargins(16, 12, 16, 12)
        start_layout.setSpacing(12)
        
        start_icon = QLabel("▶️")
        start_icon.setStyleSheet("""
            font-size: 20px;
            background: rgba(34, 197, 94, 0.15);
            border-radius: 8px;
            padding: 8px;
            min-width: 36px;
            max-width: 36px;
            min-height: 36px;
            max-height: 36px;
        """)
        start_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.auto_start_btn = QPushButton("Otomatik Seans Başlat")
        self.auto_start_btn.setIcon(QIcon(get_image_path("play.svg")))
        self.auto_start_btn.setProperty("class", "success")
        self.auto_start_btn.clicked.connect(self.start_automatic_treatment)
        self.auto_start_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(34, 197, 94, 0.9), stop:1 rgba(21, 128, 61, 0.9));
                border: 2px solid rgba(34, 197, 94, 0.4);
                border-radius: 10px;
                color: #ffffff;
                font-size: 16px;
                font-weight: 700;
                padding: 14px 28px;
                min-height: 24px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(34, 197, 94, 1.0), stop:1 rgba(21, 128, 61, 1.0));
                border: 2px solid rgba(34, 197, 94, 0.8);
            }
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(21, 128, 61, 0.9), stop:1 rgba(15, 118, 110, 0.9));
            }
        """)
        
        start_layout.addWidget(start_icon)
        start_layout.addWidget(self.auto_start_btn, stretch=1)
        
        auto_control_layout.addWidget(start_container)
        
        # Durdur butonu container
        stop_container = QWidget()
        stop_container.setStyleSheet("""
            QWidget {
                background: rgba(239, 68, 68, 0.08);
                border: 1px solid rgba(239, 68, 68, 0.2);
                border-radius: 12px;
                padding: 12px;
            }
        """)
        stop_layout = QHBoxLayout(stop_container)
        stop_layout.setContentsMargins(16, 12, 16, 12)
        stop_layout.setSpacing(12)
        
        stop_icon = QLabel("⏹️")
        stop_icon.setStyleSheet("""
            font-size: 20px;
            background: rgba(239, 68, 68, 0.15);
            border-radius: 8px;
            padding: 8px;
            min-width: 36px;
            max-width: 36px;
            min-height: 36px;
            max-height: 36px;
        """)
        stop_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.auto_stop_btn = QPushButton("Seans Durdur")
        self.auto_stop_btn.setIcon(QIcon(get_image_path("stop.svg")))
        self.auto_stop_btn.setProperty("class", "danger")
        self.auto_stop_btn.clicked.connect(lambda: self.stop_treatment(stop_reason='user_stopped'))
        self.auto_stop_btn.setEnabled(False)
        self.auto_stop_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(239, 68, 68, 0.9), stop:1 rgba(185, 28, 28, 0.9));
                border: 2px solid rgba(239, 68, 68, 0.4);
                border-radius: 10px;
                color: #ffffff;
                font-size: 16px;
                font-weight: 700;
                padding: 14px 28px;
                min-height: 24px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(239, 68, 68, 1.0), stop:1 rgba(185, 28, 28, 1.0));
                border: 2px solid rgba(239, 68, 68, 0.8);
            }
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(185, 28, 28, 0.9), stop:1 rgba(153, 27, 27, 0.9));
            }
            QPushButton:disabled {
                background: rgba(255, 255, 255, 0.1);
                border-color: rgba(255, 255, 255, 0.1);
                color: rgba(255, 255, 255, 0.4);
            }
        """)
        
        stop_layout.addWidget(stop_icon)
        stop_layout.addWidget(self.auto_stop_btn, stretch=1)
        
        auto_control_layout.addWidget(stop_container)
        
        content_layout.addWidget(auto_control_group)
        
        # Görsel ayırıcı
        separator3 = QFrame()
        separator3.setFrameShape(QFrame.Shape.HLine)
        separator3.setStyleSheet("background: rgba(255, 255, 255, 0.1); margin: 8px 0;")
        content_layout.addWidget(separator3)
        
        # Tedavi İlerlemesi
        progress_group = QGroupBox()
        progress_group.setTitle("📈 Seans İlerlemesi")
        progress_layout = QVBoxLayout(progress_group)
        progress_layout.setContentsMargins(24, 28, 24, 24)
        progress_layout.setSpacing(16)
        
        # İlerleme durumu container
        progress_container = QWidget()
        progress_container.setStyleSheet("""
            QWidget {
                background: rgba(59, 130, 246, 0.08);
                border: 1px solid rgba(59, 130, 246, 0.2);
                border-radius: 12px;
                padding: 12px;
            }
        """)
        progress_container_layout = QHBoxLayout(progress_container)
        progress_container_layout.setContentsMargins(16, 12, 16, 12)
        progress_container_layout.setSpacing(12)
        
        # İlerleme ikonu
        progress_icon = QLabel("📊")
        progress_icon.setStyleSheet("""
            font-size: 20px;
            background: rgba(59, 130, 246, 0.15);
            border-radius: 8px;
            padding: 8px;
            min-width: 36px;
            max-width: 36px;
            min-height: 36px;
            max-height: 36px;
        """)
        progress_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # İlerleme bilgileri
        progress_info_container = QWidget()
        progress_info_layout = QVBoxLayout(progress_info_container)
        progress_info_layout.setContentsMargins(0, 0, 0, 0)
        progress_info_layout.setSpacing(6)
        
        progress_title = QLabel("Seans Durumu:")
        progress_title.setStyleSheet("font-weight: 600; color: #3b82f6; font-size: 14px;")
        
        self.progress_label = QLabel("Seans başlatılmadı")
        self.progress_label.setStyleSheet("""
            font-size: 16px; 
            color: rgba(255, 255, 255, 0.9);
            font-weight: 600;
            background: rgba(255, 255, 255, 0.05);
            border-radius: 6px;
            padding: 8px 12px;
        """)
        
        progress_info_layout.addWidget(progress_title)
        progress_info_layout.addWidget(self.progress_label)
        
        progress_container_layout.addWidget(progress_icon)
        progress_container_layout.addWidget(progress_info_container, stretch=1)
        
        progress_layout.addWidget(progress_container)
        
        # Kalan süre container
        time_container = QWidget()
        time_container.setStyleSheet("""
            QWidget {
                background: rgba(168, 85, 247, 0.08);
                border: 1px solid rgba(168, 85, 247, 0.2);
                border-radius: 12px;
                padding: 12px;
            }
        """)
        time_container_layout = QHBoxLayout(time_container)
        time_container_layout.setContentsMargins(16, 12, 16, 12)
        time_container_layout.setSpacing(12)
        
        # Zaman ikonu
        time_icon = QLabel("⏰")
        time_icon.setStyleSheet("""
            font-size: 20px;
            background: rgba(168, 85, 247, 0.15);
            border-radius: 8px;
            padding: 8px;
            min-width: 36px;
            max-width: 36px;
            min-height: 36px;
            max-height: 36px;
        """)
        time_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Zaman bilgileri
        time_info_container = QWidget()
        time_info_layout = QVBoxLayout(time_info_container)
        time_info_layout.setContentsMargins(0, 0, 0, 0)
        time_info_layout.setSpacing(6)
        
        time_title = QLabel("Kalan Süre:")
        time_title.setStyleSheet("font-weight: 600; color: #a855f7; font-size: 14px;")
        
        self.remaining_time_label = QLabel("--")
        self.remaining_time_label.setStyleSheet("""
            font-size: 16px; 
            color: rgba(255, 255, 255, 0.9);
            font-weight: 600;
            background: rgba(255, 255, 255, 0.05);
            border-radius: 6px;
            padding: 8px 12px;
        """)
        
        time_info_layout.addWidget(time_title)
        time_info_layout.addWidget(self.remaining_time_label)
        
        time_container_layout.addWidget(time_icon)
        time_container_layout.addWidget(time_info_container, stretch=1)
        
        progress_layout.addWidget(time_container)
        
        content_layout.addWidget(progress_group)
        
        # Stretch
        content_layout.addStretch()
        
        tab_layout.addWidget(scroll)
        return tab_widget
        
    def _create_manual_tab(self):
        """Manuel mod tab'ını oluştur"""
        tab_widget = QWidget()
        tab_layout = QVBoxLayout(tab_widget)
        tab_layout.setContentsMargins(24, 24, 24, 24)
        tab_layout.setSpacing(24)
        
        # Scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent; border: none;")
        
        container = QWidget()
        scroll.setWidget(container)
        content_layout = QVBoxLayout(container)
        content_layout.setContentsMargins(0, 0, 24, 0)
        content_layout.setSpacing(24)
        
        # Ana Kontroller
        master_group = QGroupBox()
        master_group.setTitle(" Ana Kontroller")
        master_layout = QGridLayout(master_group)
        master_layout.setContentsMargins(24, 28, 24, 24)
        master_layout.setSpacing(20)
        master_layout.setHorizontalSpacing(24)
        master_layout.setVerticalSpacing(20)
        
        # Ana Frekans - Görsel ayrım ile
        freq_container = QWidget()
        freq_layout = QVBoxLayout(freq_container)
        freq_layout.setContentsMargins(12, 12, 12, 12)
        freq_layout.setSpacing(8)
        
        freq_label = QLabel()
        freq_label.setPixmap(QIcon(get_image_path("frequency.svg")).pixmap(16, 16))
        freq_label.setText(" Ana Frekans")
        freq_label.setStyleSheet("""
            QLabel {
                font-size: 14px;
                font-weight: 600;
                color: #6366f1;
                padding: 4px 0;
                border-bottom: 2px solid rgba(99, 102, 241, 0.3);
                margin-bottom: 8px;
            }
        """)
        
        self.master_freq_spin = NoWheelSpinBox()
        self.master_freq_spin.setRange(1, 10000)
        self.master_freq_spin.setValue(1000)
        self.master_freq_spin.setSuffix(" Hz")
        self.master_freq_spin.setStyleSheet("""
            QSpinBox {
                background: rgba(99, 102, 241, 0.1);
                border: 2px solid rgba(99, 102, 241, 0.3);
                border-radius: 8px;
                padding: 8px 12px;
                font-size: 13px;
                font-weight: 500;
            }
            QSpinBox:focus {
                border-color: #6366f1;
                background: rgba(99, 102, 241, 0.15);
            }
        """)
        
        freq_layout.addWidget(freq_label)
        freq_layout.addWidget(self.master_freq_spin)
        master_layout.addWidget(freq_container, 0, 0)
        
        # Ana Görev Döngüsü - Görsel ayrım ile
        duty_container = QWidget()
        duty_layout = QVBoxLayout(duty_container)
        duty_layout.setContentsMargins(12, 12, 12, 12)
        duty_layout.setSpacing(8)
        
        duty_label = QLabel()
        duty_label.setPixmap(QIcon(get_image_path("intensity.svg")).pixmap(16, 16))
        duty_label.setText(" Ana Görev Döngüsü")
        duty_label.setStyleSheet("""
            QLabel {
                font-size: 14px;
                font-weight: 600;
                color: #10b981;
                padding: 4px 0;
                border-bottom: 2px solid rgba(16, 185, 129, 0.3);
                margin-bottom: 8px;
            }
        """)
        
        self.master_duty_spin = NoWheelDoubleSpinBox()
        self.master_duty_spin.setRange(0.1, 99.9)
        self.master_duty_spin.setValue(50.0)
        self.master_duty_spin.setSuffix(" %")
        self.master_duty_spin.setStyleSheet("""
            QDoubleSpinBox {
                background: rgba(16, 185, 129, 0.1);
                border: 2px solid rgba(16, 185, 129, 0.3);
                border-radius: 8px;
                padding: 8px 12px;
                font-size: 13px;
                font-weight: 500;
            }
            QDoubleSpinBox:focus {
                border-color: #10b981;
                background: rgba(16, 185, 129, 0.15);
            }
        """)
        
        duty_layout.addWidget(duty_label)
        duty_layout.addWidget(self.master_duty_spin)
        master_layout.addWidget(duty_container, 0, 1)
        
        # Ana Süre - Görsel ayrım ile
        duration_container = QWidget()
        duration_layout = QVBoxLayout(duration_container)
        duration_layout.setContentsMargins(12, 12, 12, 12)
        duration_layout.setSpacing(8)
        
        duration_label = QLabel()
        duration_label.setPixmap(QIcon(get_image_path("duration.svg")).pixmap(16, 16))
        duration_label.setText(" Ana Süre")
        duration_label.setStyleSheet("""
            QLabel {
                font-size: 14px;
                font-weight: 600;
                color: #f59e0b;
                padding: 4px 0;
                border-bottom: 2px solid rgba(245, 158, 11, 0.3);
                margin-bottom: 8px;
            }
        """)
        
        self.master_duration_spin = NoWheelSpinBox()
        self.master_duration_spin.setRange(0, 9999)
        self.master_duration_spin.setValue(0)
        self.master_duration_spin.setSuffix(" dakika (0=süresiz)")
        self.master_duration_spin.setStyleSheet("""
            QSpinBox {
                background: rgba(245, 158, 11, 0.1);
                border: 2px solid rgba(245, 158, 11, 0.3);
                border-radius: 8px;
                padding: 8px 12px;
                font-size: 13px;
                font-weight: 500;
            }
            QSpinBox:focus {
                border-color: #f59e0b;
                background: rgba(245, 158, 11, 0.15);
            }
        """)
        
        duration_layout.addWidget(duration_label)
        duration_layout.addWidget(self.master_duration_spin)
        master_layout.addWidget(duration_container, 1, 0, 1, 2)
        
        # Görsel ayırıcı çizgi
        master_separator = QFrame()
        master_separator.setFrameShape(QFrame.Shape.HLine)
        master_separator.setFrameShadow(QFrame.Shadow.Sunken)
        master_separator.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                    stop:0 transparent, 
                    stop:0.5 rgba(99, 102, 241, 0.4), 
                    stop:1 transparent);
                border: none;
                height: 2px;
                margin: 12px 0;
            }
        """)
        master_layout.addWidget(master_separator, 3, 0, 1, 2)
        
        # Ana kontrol butonları
        master_control_layout = QHBoxLayout()
        
        self.apply_all_btn = QPushButton(" Tümüne Uygula")
        self.apply_all_btn.setIcon(QIcon(get_image_path("settings.svg")))
        self.apply_all_btn.setProperty("class", "secondary")
        self.apply_all_btn.clicked.connect(self.apply_to_all_coils)
        
        self.start_all_btn = QPushButton(" Tümünü Başlat")
        self.start_all_btn.setIcon(QIcon(get_image_path("play.svg")))
        self.start_all_btn.setProperty("class", "success")
        self.start_all_btn.clicked.connect(self._start_all_with_apply)
        
        self.stop_all_btn = QPushButton(" Tümünü Durdur")
        self.stop_all_btn.setIcon(QIcon(get_image_path("settings.svg")))
        self.stop_all_btn.setProperty("class", "danger")
        self.stop_all_btn.clicked.connect(self.stop_all_coils)
        
        master_control_layout.addWidget(self.apply_all_btn)
        master_control_layout.addWidget(self.start_all_btn)
        master_control_layout.addWidget(self.stop_all_btn)
        
        master_layout.addLayout(master_control_layout, 4, 0, 1, 2)
        content_layout.addWidget(master_group)
        
        # Bireysel Bobin Kontrolleri
        coils_group = QGroupBox()
        coils_group.setTitle(" Bireysel Bobin Kontrolleri")
        coils_layout = QGridLayout(coils_group)
        coils_layout.setContentsMargins(24, 28, 24, 24)
        coils_layout.setSpacing(20)
        coils_layout.setHorizontalSpacing(24)
        coils_layout.setVerticalSpacing(20)
        
        # 8 bobin için kontroller oluştur
        for i in range(1, 9):
            self._create_coil_control(coils_layout, i)
            
        content_layout.addWidget(coils_group)
        content_layout.addStretch()
        
        tab_layout.addWidget(scroll)
        return tab_widget
        
    def _create_coil_control(self, parent_layout, coil_num):
        """Bireysel bobin kontrolü oluştur - Modern tasarım"""
        row = (coil_num - 1) // 2
        col = (coil_num - 1) % 2
        
        # Modern bobin kartı - Geliştirilmiş görsel ayrım
        coil_group = QGroupBox()
        coil_group.setProperty("class", "card-elevated")
        coil_group.setStyleSheet(f"""
            QGroupBox {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                    stop:0 rgba(255, 255, 255, 0.12), 
                    stop:1 rgba(255, 255, 255, 0.06));
                border: 2px solid rgba(99, 102, 241, 0.3);
                border-radius: 18px;
                margin: 8px;
                padding-top: 12px;
                font-weight: 700;
                font-size: 14px;
            }}
            QGroupBox:hover {{
                border-color: rgba(99, 102, 241, 0.5);
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                    stop:0 rgba(255, 255, 255, 0.15), 
                    stop:1 rgba(255, 255, 255, 0.08));
            }}
        """)
        coil_layout = QVBoxLayout(coil_group)
        coil_layout.setContentsMargins(24, 24, 24, 24)
        coil_layout.setSpacing(18)
        
        # Header - Bobin adı ve durum
        header_layout = QHBoxLayout()
        header_layout.setSpacing(12)
        
        # Bobin numarası ve ikonu
        coil_title_layout = QHBoxLayout()
        coil_title_layout.setSpacing(8)
        
        coil_icon = QLabel()
        coil_icon.setPixmap(QIcon(get_image_path("intensity.svg")).pixmap(18, 18))
        coil_icon.setStyleSheet("color: #3b82f6;")
        
        coil_title = QLabel(f"Bobin {coil_num}")
        coil_title.setStyleSheet("font-size: 16px; font-weight: 700; color: #ffffff;")
        
        # Bağlantı durumu göstergesi
        connection_status_label = QLabel("Bağlı Değil")
        connection_status_label.setObjectName("connectionStatus")
        connection_status_label.setStyleSheet("""
            font-size: 12px; 
            font-weight: 600; 
            color: #ef4444;
            padding: 4px 8px;
            background: rgba(239, 68, 68, 0.15);
            border-radius: 8px;
            border: 1px solid rgba(239, 68, 68, 0.3);
        """)
        
        coil_title_layout.addWidget(coil_icon)
        coil_title_layout.addWidget(coil_title)
        coil_title_layout.addWidget(connection_status_label)
        coil_title_layout.addStretch()
        
        # Durum göstergesi
        status_container = QWidget()
        status_layout = QHBoxLayout(status_container)
        status_layout.setContentsMargins(8, 4, 8, 4)
        status_layout.setSpacing(6)
        
        status_led = QLabel("●")
        status_led.setObjectName("statusLed")
        status_led.setStyleSheet("color: #ef4444; font-size: 12px;")
        
        status_label = QLabel("Durduruldu")
        status_label.setStyleSheet("font-size: 11px; color: rgba(255, 255, 255, 0.8); font-weight: 600;")
        
        remaining_time_label = QLabel("")
        remaining_time_label.setObjectName("remainingTimeLabel")
        remaining_time_label.setStyleSheet("font-size: 11px; color: rgba(255, 255, 255, 0.9); font-weight: 600;")
        remaining_time_label.setVisible(False)
        
        # Sıcaklık göstergesi
        temp_label = QLabel("--°C")
        temp_label.setObjectName("tempLabel")
        temp_label.setStyleSheet("font-size: 11px; color: rgba(255, 255, 255, 0.7); font-weight: 600;")
        temp_label.setToolTip("Bobin sıcaklığı")
        
        status_layout.addWidget(status_led)
        status_layout.addWidget(status_label)
        status_layout.addWidget(remaining_time_label)
        status_layout.addWidget(temp_label)
        status_layout.addStretch()
        
        status_container.setStyleSheet("""
            background: rgba(239, 68, 68, 0.1);
            border-radius: 12px;
            border: 1px solid rgba(239, 68, 68, 0.3);
        """)
        
        header_layout.addLayout(coil_title_layout)
        header_layout.addWidget(status_container)
        
        coil_layout.addLayout(header_layout)
        
        # Parametreler - Grid layout
        params_widget = QWidget()
        params_layout = QGridLayout(params_widget)
        params_layout.setContentsMargins(0, 0, 0, 0)
        params_layout.setSpacing(12)
        
        # Frekans - Görsel ayrım ile
        freq_container = QWidget()
        freq_container.setStyleSheet("""
            QWidget {
                background: rgba(99, 102, 241, 0.08);
                border: 1px solid rgba(99, 102, 241, 0.2);
                border-radius: 8px;
                padding: 8px;
                margin: 2px;
            }
        """)
        freq_container_layout = QVBoxLayout(freq_container)
        freq_container_layout.setContentsMargins(8, 8, 8, 8)
        freq_container_layout.setSpacing(4)
        
        freq_label = QLabel()
        freq_label.setPixmap(QIcon(get_image_path("frequency.svg")).pixmap(12, 12))
        freq_label.setText(" Frekans")
        freq_label.setStyleSheet("font-size: 12px; color: #6366f1; font-weight: 700;")
        freq_spin = NoWheelSpinBox()
        freq_spin.setRange(1, 10000)
        freq_spin.setValue(1000)
        freq_spin.setSuffix(" Hz")
        freq_spin.setMinimumHeight(32)
        freq_spin.setStyleSheet("""
            QSpinBox {
                background: rgba(255, 255, 255, 0.1);
                border: 1px solid rgba(99, 102, 241, 0.3);
                border-radius: 6px;
                padding: 4px 8px;
                font-weight: 600;
            }
            QSpinBox:focus {
                border-color: #6366f1;
                background: rgba(255, 255, 255, 0.15);
            }
        """)
        
        freq_container_layout.addWidget(freq_label)
        freq_container_layout.addWidget(freq_spin)
        params_layout.addWidget(freq_container, 0, 0)
        
        # Görev döngüsü - Görsel ayrım ile
        duty_container = QWidget()
        duty_container.setStyleSheet("""
            QWidget {
                background: rgba(16, 185, 129, 0.08);
                border: 1px solid rgba(16, 185, 129, 0.2);
                border-radius: 8px;
                padding: 8px;
                margin: 2px;
            }
        """)
        duty_container_layout = QVBoxLayout(duty_container)
        duty_container_layout.setContentsMargins(8, 8, 8, 8)
        duty_container_layout.setSpacing(4)
        
        duty_label = QLabel()
        duty_label.setPixmap(QIcon(get_image_path("intensity.svg")).pixmap(12, 12))
        duty_label.setText(" Görev Döngüsü")
        duty_label.setStyleSheet("font-size: 12px; color: #10b981; font-weight: 700;")
        duty_spin = NoWheelDoubleSpinBox()
        duty_spin.setRange(0.1, 99.9)
        duty_spin.setValue(50.0)
        duty_spin.setSuffix(" %")
        duty_spin.setMinimumHeight(32)
        duty_spin.setStyleSheet("""
            QDoubleSpinBox {
                background: rgba(255, 255, 255, 0.1);
                border: 1px solid rgba(16, 185, 129, 0.3);
                border-radius: 6px;
                padding: 4px 8px;
                font-weight: 600;
            }
            QDoubleSpinBox:focus {
                border-color: #10b981;
                background: rgba(255, 255, 255, 0.15);
            }
        """)
        
        duty_container_layout.addWidget(duty_label)
        duty_container_layout.addWidget(duty_spin)
        params_layout.addWidget(duty_container, 0, 1)
        
        # Süre - Görsel ayrım ile
        duration_container = QWidget()
        duration_container.setStyleSheet("""
            QWidget {
                background: rgba(245, 158, 11, 0.08);
                border: 1px solid rgba(245, 158, 11, 0.2);
                border-radius: 8px;
                padding: 8px;
                margin: 2px;
            }
        """)
        duration_container_layout = QVBoxLayout(duration_container)
        duration_container_layout.setContentsMargins(8, 8, 8, 8)
        duration_container_layout.setSpacing(4)
        
        duration_label = QLabel()
        duration_label.setPixmap(QIcon(get_image_path("duration.svg")).pixmap(12, 12))
        duration_label.setText(" Süre")
        duration_label.setStyleSheet("font-size: 12px; color: #f59e0b; font-weight: 700;")
        duration_spin = NoWheelSpinBox()
        duration_spin.setRange(0, 9999)
        duration_spin.setValue(0)
        duration_spin.setSuffix(" dk")
        duration_spin.setMinimumHeight(32)
        duration_spin.setStyleSheet("""
            QSpinBox {
                background: rgba(255, 255, 255, 0.1);
                border: 1px solid rgba(245, 158, 11, 0.3);
                border-radius: 6px;
                padding: 4px 8px;
                font-weight: 600;
            }
            QSpinBox:focus {
                border-color: #f59e0b;
                background: rgba(255, 255, 255, 0.15);
            }
        """)
        
        duration_container_layout.addWidget(duration_label)
        duration_container_layout.addWidget(duration_spin)
        params_layout.addWidget(duration_container, 1, 0, 1, 2)
        
        coil_layout.addWidget(params_widget)
        
        # Görsel ayırıcı çizgi
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        separator.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                    stop:0 transparent, 
                    stop:0.5 rgba(99, 102, 241, 0.4), 
                    stop:1 transparent);
                border: none;
                height: 2px;
                margin: 8px 0;
            }
        """)
        coil_layout.addWidget(separator)
        
        # Kontrol butonları - Modern tasarım
        control_layout = QHBoxLayout()
        control_layout.setSpacing(12)
        
        start_btn = QPushButton()
        start_btn.setIcon(QIcon(get_image_path("play.svg")))
        start_btn.setText(f" Bobin {coil_num} Başlat")
        start_btn.setProperty("class", "success")
        start_btn.setMinimumHeight(42)
        start_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                    stop:0 rgba(34, 197, 94, 0.9), 
                    stop:1 rgba(21, 128, 61, 0.9));
                border: 2px solid rgba(34, 197, 94, 0.4);
                border-radius: 12px;
                color: #ffffff;
                font-size: 13px;
                font-weight: 700;
                padding: 8px 16px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                    stop:0 rgba(34, 197, 94, 1.0), 
                    stop:1 rgba(21, 128, 61, 1.0));
                border: 2px solid rgba(34, 197, 94, 0.6);
                padding: 7px 15px;
            }
            QPushButton:disabled {
                background: rgba(34, 197, 94, 0.3);
                border-color: rgba(34, 197, 94, 0.2);
                color: rgba(255, 255, 255, 0.5);
            }
        """)
        start_btn.clicked.connect(partial(self.start_coil, coil_num))
        
        stop_btn = QPushButton()
        stop_btn.setIcon(QIcon(get_image_path("stop.svg")))
        stop_btn.setText(f" Bobin {coil_num} Durdur")
        stop_btn.setProperty("class", "danger")
        stop_btn.setMinimumHeight(42)
        stop_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                    stop:0 rgba(239, 68, 68, 0.9), 
                    stop:1 rgba(185, 28, 28, 0.9));
                border: 2px solid rgba(239, 68, 68, 0.4);
                border-radius: 12px;
                color: #ffffff;
                font-size: 13px;
                font-weight: 700;
                padding: 8px 16px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                    stop:0 rgba(239, 68, 68, 1.0), 
                    stop:1 rgba(185, 28, 28, 1.0));
                border: 2px solid rgba(239, 68, 68, 0.6);
                padding: 7px 15px;
            }
            QPushButton:disabled {
                background: rgba(239, 68, 68, 0.3);
                border-color: rgba(239, 68, 68, 0.2);
                color: rgba(255, 255, 255, 0.5);
            }
        """)
        stop_btn.clicked.connect(partial(self.stop_coil, coil_num))
        
        control_layout.addWidget(start_btn)
        control_layout.addWidget(stop_btn)
        
        coil_layout.addLayout(control_layout)
        
        # Kontrolleri sakla
        self.coil_controls[coil_num] = {
            'group': coil_group,
            'status_led': status_led,
            'status_label': status_label,
            'remaining_time_label': remaining_time_label,
            'temp_label': temp_label,
            'status_container': status_container,
            'connection_status_label': connection_status_label,  # Bağlantı durumu göstergesi
            'freq_spin': freq_spin,
            'duty_spin': duty_spin,
            'duration_spin': duration_spin,
            'start_btn': start_btn,
            'stop_btn': stop_btn
        }
        
        parent_layout.addWidget(coil_group, row, col)
    
    def _init_ai_controller(self):
        """Initialize AI controller (models will be loaded on-demand when Calculate button is pressed)"""
        try:
            mqtt_client = self.main_window.mqtt_client if hasattr(self.main_window, 'mqtt_client') else None
            coil_manager = self.main_window.coil_manager if hasattr(self.main_window, 'coil_manager') else None
            
            # create_ai_controller may be None if import failed; guard against that
            if not callable(create_ai_controller):
                self.logger.error(f"AI controller factory not available: {AI_IMPORT_ERROR}")
                self.ai_controller = None
                return

            self.ai_controller = create_ai_controller(
                mqtt_client=mqtt_client,
                app_data_dir=self.app_data_dir,
                coil_manager=coil_manager
            )
            
            # Connect AI controller signals
            if hasattr(self.ai_controller, 'status_changed'):
                self.ai_controller.status_changed.connect(self._on_ai_status_changed)
            if hasattr(self.ai_controller, 'parameters_updated'):
                self.ai_controller.parameters_updated.connect(self._on_ai_parameters_updated)
            if hasattr(self.ai_controller, 'anomaly_detected'):
                self.ai_controller.anomaly_detected.connect(self._on_ai_anomaly_detected)
            
            self.logger.info("AI controller initialized successfully (models not loaded yet)")
            
            # Thread-safe model loading state
            self.ai_models_loaded = False
            self.ai_models_loading = False
            self.ai_model_load_lock = threading.Lock()
            
            # DON'T load models here - they will be loaded when Calculate button is pressed
            
        except Exception as e:
            self.logger.error(f"Failed to initialize AI controller: {e}")
            self.ai_controller = None
    
    def _load_ai_models_async(self):
        """Load AI models in background thread (FIXED: Added thread cleanup)"""
        if not self.ai_controller:
            return
        
        self.ai_model_load_thread = AIModelLoadThread(self.ai_controller)
        self.ai_model_load_thread.progress_update.connect(self._on_ai_model_load_progress)
        self.ai_model_load_thread.models_loaded.connect(self._on_ai_models_loaded)
        self.ai_model_load_thread.error_occurred.connect(self._on_ai_model_load_error)
        # FIXED: Add thread cleanup to prevent memory leak
        self.ai_model_load_thread.finished.connect(self.ai_model_load_thread.deleteLater)
        self.ai_model_load_thread.start()
        
        # Update AI tab status
        if hasattr(self, 'ai_status_label'):
            self.ai_status_label.setText("🔄 AI modelleri yükleniyor...")
            self.ai_status_label.setStyleSheet("color: #FFA500; font-weight: bold;")
    
    def _on_ai_model_load_progress(self, message: str):
        """Handle AI model loading progress updates"""
        self.logger.info(message)
        if hasattr(self, 'ai_status_label'):
            self.ai_status_label.setText(message)
    
    def _on_ai_models_loaded(self, success: bool):
        """Handle AI models loaded event (thread-safe)"""
        # Thread-safe update of loading state
        with self.ai_model_load_lock:
            self.ai_models_loading = False
            self.ai_models_loaded = success
        
        if success:
            self.logger.info("✓ AI models loaded successfully")
            if hasattr(self, 'ai_status_label'):
                self.ai_status_label.setText("✓ AI modelleri hazır")
                self.ai_status_label.setStyleSheet("color: #00FF00; font-weight: bold;")
            
            # Enable calculate button if patient is selected
            if hasattr(self, 'selected_patient') and self.selected_patient:
                if hasattr(self, 'ai_calculate_btn'):
                    self.ai_calculate_btn.setEnabled(False)  # Disable during calculation
                    self.ai_calculate_btn.setText("⚙️ Hesaplanıyor...")
                    # Automatically trigger calculation after models load
                    self.ai_message_label.setText("✓ Modeller yüklendi, hesaplama başlatılıyor...")
                    QApplication.processEvents()
                    # Use QTimer to call calculation after returning to event loop
                    QTimer.singleShot(100, self._calculate_ai_recommendations)
                if hasattr(self, 'ai_start_btn'):
                    self.ai_start_btn.setEnabled(True)
            else:
                # Hasta seçili değilse butonu kapat
                if hasattr(self, 'ai_calculate_btn'):
                    self.ai_calculate_btn.setEnabled(False)
                    self.ai_calculate_btn.setText("🔮 AI Parametre Hesapla")
        else:
            self.logger.warning("⚠ AI models not loaded")
            if hasattr(self, 'ai_status_label'):
                self.ai_status_label.setText("⚠ AI modelleri yüklenemedi")
                self.ai_status_label.setStyleSheet("color: #FFA500; font-weight: bold;")
            
            # Re-enable calculate button to allow retry (only if patient selected)
            if hasattr(self, 'ai_calculate_btn'):
                if hasattr(self, 'selected_patient') and self.selected_patient:
                    self.ai_calculate_btn.setEnabled(True)
                else:
                    self.ai_calculate_btn.setEnabled(False)
            if hasattr(self, 'ai_start_btn'):
                self.ai_start_btn.setEnabled(False)
            
            # Show error to user
            self.ai_message_label.setText("❌ AI modelleri yüklenemedi. Lütfen tekrar deneyin.")
    
    def _on_ai_model_load_error(self, error_msg: str):
        """AI model yükleme hatası - Clear loading flag (Critical Fix BUG #4)"""
        # CRITICAL: Clear ai_models_loading flag on error (BUG #4 fix)
        with self.ai_model_load_lock:
            self.ai_models_loading = False
            self.ai_models_loaded = False
        
        self.logger.error(f"AI model load error: {error_msg}")
        
        if hasattr(self, 'ai_status_label'):
            self.ai_status_label.setText(f"❌ Hata: {error_msg}")
            self.ai_status_label.setStyleSheet("color: #FF0000; font-weight: bold;")
        
        # Re-enable calculate button so user can retry (only if patient selected)
        if hasattr(self, 'ai_calculate_btn'):
            if hasattr(self, 'selected_patient') and self.selected_patient:
                self.ai_calculate_btn.setEnabled(True)
            else:
                self.ai_calculate_btn.setEnabled(False)
            self.ai_calculate_btn.setText("🔄 Yeniden Dene")
            self.ai_calculate_btn.setText("🔄 Yeniden Dene")
        
        self.show_error(f"AI modelleri yüklenemedi: {error_msg}")

    def _on_ai_patient_changed(self, index):
        """Handle AI patient selection change"""
        if index < 0:  # Invalid index
            return
            
        patient = self.ai_patient_combo.itemData(index)
        
        if not patient:  # "Hasta seçiniz..." or None
            self.selected_patient = None
            self.ai_patient_info_label.setText("Hasta seçilmedi")
            self.ai_start_btn.setEnabled(False)
            if hasattr(self, 'ai_calculate_btn'):
                self.ai_calculate_btn.setEnabled(False)
            # Header'ı güncelle
            self._update_header_patient_info()
            return
        
        # Valid patient selected - Tüm hasta bilgilerini doğru formatta kaydet
        self.selected_patient = {
            'id': patient.get('id'),
            'info': {
                'name': patient.get('name', ''),
                'species': patient.get('species', ''),
                'breed': patient.get('breed', ''),
                'age': patient.get('age', ''),
                'weight': patient.get('weight', ''),
                'owner': patient.get('owner', ''),
                'vet_contact': patient.get('vet_contact', '')
            }
        }
        
        # Main window'a hasta bilgisini kaydet
        if self.main_window:
            self.main_window.last_saved_patient = self.selected_patient
        
        # Update info display (AI tab içindeki)
        name = patient.get('name', 'İsimsiz')
        species = patient.get('species', 'Bilinmiyor')
        age = patient.get('age', '?')
        weight = patient.get('weight', '?')
        
        info_text = f"🐾 {name} | Tür: {species} | Yaş: {age} | Kilo: {weight} kg"
        self.ai_patient_info_label.setText(info_text)
        
        # Header'ı güncelle (sağ üstteki hasta bilgisi)
        self._update_header_patient_info()
        
        # Otomatik mod hasta combo'sunu da senkronize et
        if hasattr(self, 'patient_combo'):
            # Aynı hastayı otomatik mod combo'sunda bul ve seç
            for i in range(self.patient_combo.count()):
                combo_patient = self.patient_combo.itemData(i)
                if combo_patient and combo_patient.get('id') == patient.get('id'):
                    # currentIndexChanged sinyalini geçici olarak blokla
                    self.patient_combo.blockSignals(True)
                    self.patient_combo.setCurrentIndex(i)
                    self.patient_combo.blockSignals(False)
                    break
        
        # Enable AI calculate button when patient is selected (lazy loading - models load on first click)
        # Start button only enabled after models are loaded
        if hasattr(self, 'ai_calculate_btn'):
            self.ai_calculate_btn.setEnabled(True)  # Always enable for lazy loading
        
        # Start button requires loaded models
        models_loaded = (
            self.ai_controller and 
            hasattr(self.ai_controller, 'models_loaded') and 
            self.ai_controller.models_loaded
        )
        if hasattr(self, 'ai_start_btn'):
            self.ai_start_btn.setEnabled(models_loaded)
        
        self.logger.info(f"AI patient selected: {name}")
    
    def _create_ai_tab(self):
        """AI mod tab'ını oluştur"""
        tab_widget = QWidget()
        tab_layout = QVBoxLayout(tab_widget)
        tab_layout.setContentsMargins(24, 24, 24, 24)
        tab_layout.setSpacing(24)

        # Check if AI is available and show detailed error if not
        if not AI_AVAILABLE:
            error_text = f"⚠️ AI modülleri yüklenemedi.\n\nHata Detayı:\n{AI_IMPORT_ERROR}"

            error_label = QLabel(error_text)
            error_label.setStyleSheet("""
                QLabel {
                    color: #ef4444;
                    font-size: 16px;
                    font-weight: 600;
                    padding: 40px;
                    background: rgba(239, 68, 68, 0.1);
                    border-radius: 12px;
                    border: 2px solid rgba(239, 68, 68, 0.3);
                }
            """)
            error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            tab_layout.addWidget(error_label)
            return tab_widget
        
        # Scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent; border: none;")
        
        container = QWidget()
        scroll.setWidget(container)
        content_layout = QVBoxLayout(container)
        content_layout.setContentsMargins(0, 0, 24, 0)
        content_layout.setSpacing(24)
        
        # Patient Selection Panel
        patient_group = QGroupBox()
        patient_group.setTitle("🐾 Hasta Seçimi")
        patient_layout = QVBoxLayout(patient_group)
        patient_layout.setContentsMargins(24, 28, 24, 24)
        patient_layout.setSpacing(16)
        
        # Patient combo box with styling similar to auto mode
        patient_select_container = QWidget()
        patient_select_container.setStyleSheet("""
            QWidget {
                background: rgba(99, 102, 241, 0.08);
                border: 1px solid rgba(99, 102, 241, 0.2);
                border-radius: 12px;
                padding: 12px;
            }
        """)
        patient_select_layout = QHBoxLayout(patient_select_container)
        patient_select_layout.setContentsMargins(16, 12, 16, 12)
        patient_select_layout.setSpacing(12)
        
        # Patient icon
        patient_icon_label = QLabel("🐾")
        patient_icon_label.setStyleSheet("""
            font-size: 20px;
            color: #6366f1;
            background: rgba(99, 102, 241, 0.15);
            border-radius: 8px;
            padding: 8px;
            min-width: 36px;
            max-width: 36px;
            min-height: 36px;
            max-height: 36px;
        """)
        patient_icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Combo container
        patient_combo_container = QWidget()
        patient_combo_layout = QVBoxLayout(patient_combo_container)
        patient_combo_layout.setContentsMargins(0, 0, 0, 0)
        patient_combo_layout.setSpacing(4)
        
        patient_label = QLabel("Hasta Seçin:")
        patient_label.setStyleSheet("font-size: 14px; font-weight: 600; color: #6366f1;")
        
        self.ai_patient_combo = QComboBox()
        self.ai_patient_combo.setMinimumHeight(40)
        self.ai_patient_combo.setStyleSheet("""
            QComboBox {
                background: rgba(255, 255, 255, 0.12);
                color: white;
                border: 2px solid rgba(99, 102, 241, 0.3);
                border-radius: 8px;
                padding: 10px 12px;
                font-size: 14px;
                font-weight: 500;
            }
            QComboBox:hover {
                border-color: #6366f1;
                background: rgba(255, 255, 255, 0.18);
            }
            QComboBox:focus {
                border: 2px solid rgba(99, 102, 241, 0.8);
            }
            QComboBox::drop-down {
                border: none;
                width: 30px;
            }
            QComboBox::down-arrow {
                image: url(none);
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 6px solid white;
                margin-right: 8px;
            }
            QComboBox QAbstractItemView {
                background: #2d3748;
                color: white;
                selection-background-color: #6366f1;
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 8px;
                padding: 4px;
            }
        """)
        self.ai_patient_combo.currentIndexChanged.connect(self._on_ai_patient_changed)
        
        patient_combo_layout.addWidget(patient_label)
        patient_combo_layout.addWidget(self.ai_patient_combo)
        
        patient_select_layout.addWidget(patient_icon_label)
        patient_select_layout.addWidget(patient_combo_container, 1)
        
        patient_layout.addWidget(patient_select_container)
        
        # Patient info display
        self.ai_patient_info_label = QLabel("Hasta seçilmedi")
        self.ai_patient_info_label.setStyleSheet("""
            QLabel {
                color: rgba(255, 255, 255, 0.6);
                font-size: 12px;
                padding: 8px;
                background: rgba(0, 0, 0, 0.2);
                border-radius: 6px;
            }
        """)
        patient_layout.addWidget(self.ai_patient_info_label)
        
        content_layout.addWidget(patient_group)
        
        # Treatment Target Selection Panel
        target_group = QGroupBox()
        target_group.setTitle("🎯 Seans Hedefi")
        target_layout = QVBoxLayout(target_group)
        target_layout.setContentsMargins(24, 28, 24, 24)
        target_layout.setSpacing(16)
        
        # Target selection container
        target_selection_container = QWidget()
        target_selection_container.setStyleSheet("""
            QWidget {
                background: rgba(99, 102, 241, 0.08);
                border: 1px solid rgba(99, 102, 241, 0.2);
                border-radius: 12px;
                padding: 12px;
            }
        """)
        target_selection_layout = QHBoxLayout(target_selection_container)
        target_selection_layout.setContentsMargins(16, 12, 16, 12)
        target_selection_layout.setSpacing(12)
        
        # Target icon
        target_icon_label = QLabel("🏥")
        target_icon_label.setStyleSheet("""
            font-size: 20px;
            color: #6366f1;
            background: rgba(99, 102, 241, 0.15);
            border-radius: 8px;
            padding: 8px;
            min-width: 36px;
            max-width: 36px;
            min-height: 36px;
            max-height: 36px;
        """)
        target_icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Combo box container
        target_combo_container = QWidget()
        target_combo_layout = QVBoxLayout(target_combo_container)
        target_combo_layout.setContentsMargins(0, 0, 0, 0)
        target_combo_layout.setSpacing(4)
        
        target_label = QLabel("Seans Hedefi Seçin:")
        target_label.setStyleSheet("font-weight: 600; color: #6366f1; font-size: 14px;")
        
        self.ai_target_combo = QComboBox()
        self.ai_target_combo.addItems([
            "🦴 Kronik Artrit",
            "🦴 Osteoartrit",
            "🔥 İnflamasyon",
            "🩹 Kırık İyileşmesi",
            "🏥 Post-op Yara İyileşmesi",
            "🧵 Doku İyileşmesi",
            "🧠 Anksiyete/Stres",
            "💪 Kas Gerginliği/Spazm",
            "🧠 Nörolojik (IVDD, Nöropati)",
            "😌 Genel Rahatlama/Wellness",
            "💧 Ödematöz Dokular",
            "🔗 Tendon/Ligament Yaralanması"
        ])
        self.ai_target_combo.setStyleSheet("""
            QComboBox {
                background: rgba(255, 255, 255, 0.12);
                border: 2px solid rgba(99, 102, 241, 0.3);
                border-radius: 8px;
                padding: 10px 12px;
                font-size: 14px;
                color: #ffffff;
                min-height: 24px;
                font-weight: 500;
            }
            QComboBox:focus {
                border: 2px solid rgba(99, 102, 241, 0.8);
                background: rgba(255, 255, 255, 0.18);
            }
            QComboBox::drop-down {
                border: none;
                width: 30px;
            }
            QComboBox::down-arrow {
                image: url(none);
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 6px solid white;
                margin-right: 8px;
            }
            QComboBox QAbstractItemView {
                background: #2d3748;
                color: white;
                selection-background-color: #6366f1;
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 8px;
                padding: 4px;
            }
        """)
        
        target_combo_layout.addWidget(target_label)
        target_combo_layout.addWidget(self.ai_target_combo)
        
        target_selection_layout.addWidget(target_icon_label)
        target_selection_layout.addWidget(target_combo_container, 1)
        
        target_layout.addWidget(target_selection_container)
        content_layout.addWidget(target_group)
        
        # AI Status Panel
        status_group = QGroupBox()
        status_group.setTitle("🤖 AI Tedavi Durumu")
        status_layout = QVBoxLayout(status_group)
        status_layout.setContentsMargins(24, 28, 24, 24)
        status_layout.setSpacing(16)
        
        # Status display
        status_container = QWidget()
        status_container_layout = QHBoxLayout(status_container)
        status_container_layout.setContentsMargins(16, 16, 16, 16)
        status_container_layout.setSpacing(16)
        
        self.ai_status_label = QLabel("⏳ AI Modelleri Hazır Değil")
        self.ai_status_label.setStyleSheet("""
            QLabel {
                color: #FFA500;
                font-size: 18px;
                font-weight: 700;
            }
        """)
        
        self.ai_confidence_label = QLabel("İlk hesaplamada yüklenecek")
        self.ai_confidence_label.setStyleSheet("""
            QLabel {
                color: rgba(255, 255, 255, 0.7);
                font-size: 14px;
            }
        """)
        
        status_container_layout.addWidget(self.ai_status_label)
        status_container_layout.addWidget(self.ai_confidence_label)
        status_container_layout.addStretch()
        
        status_layout.addWidget(status_container)
        
        # AI message display
        self.ai_message_label = QLabel("AI modelleri ilk 'Parametre Hesapla' tıklamasında yüklenecek. Hasta seçin ve hesapla butonuna basın.")
        self.ai_message_label.setWordWrap(True)
        self.ai_message_label.setStyleSheet("""
            QLabel {
                color: rgba(255, 255, 255, 0.8);
                font-size: 13px;
                padding: 12px;
                background: rgba(0, 0, 0, 0.2);
                border-radius: 8px;
            }
        """)
        status_layout.addWidget(self.ai_message_label)
        
        content_layout.addWidget(status_group)
        
        # AI Recommendations Panel
        recommendations_group = QGroupBox()
        recommendations_group.setTitle("💡 AI Önerileri")
        recommendations_layout = QGridLayout(recommendations_group)
        recommendations_layout.setContentsMargins(24, 28, 24, 24)
        recommendations_layout.setSpacing(16)
        
        # Frequency
        freq_label = QLabel("Frekans:")
        self.ai_freq_value = QLabel("-- Hz")
        self.ai_freq_value.setStyleSheet("font-weight: 600; color: #6366f1;")
        recommendations_layout.addWidget(freq_label, 0, 0)
        recommendations_layout.addWidget(self.ai_freq_value, 0, 1)
        
        # Intensity
        intensity_label = QLabel("Ortalama Yoğunluk:")
        self.ai_intensity_value = QLabel("-- %")
        self.ai_intensity_value.setStyleSheet("font-weight: 600; color: #6366f1;")
        recommendations_layout.addWidget(intensity_label, 1, 0)
        recommendations_layout.addWidget(self.ai_intensity_value, 1, 1)
        
        # Duration
        duration_label = QLabel("Süre:")
        self.ai_duration_value = QLabel("-- dakika")
        self.ai_duration_value.setStyleSheet("font-weight: 600; color: #6366f1;")
        recommendations_layout.addWidget(duration_label, 2, 0)
        recommendations_layout.addWidget(self.ai_duration_value, 2, 1)
        
        # Calculate button
        self.ai_calculate_btn = QPushButton("🧮 AI Önerilerini Hesapla")
        self.ai_calculate_btn.setMinimumHeight(40)
        self.ai_calculate_btn.setEnabled(False)
        self.ai_calculate_btn.clicked.connect(self._calculate_ai_recommendations)
        self.ai_calculate_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #6366f1, stop:1 #4f46e5);
                color: white;
                font-size: 13px;
                font-weight: 600;
                border-radius: 8px;
                padding: 10px 20px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #4f46e5, stop:1 #4338ca);
            }
            QPushButton:disabled {
                background: rgba(100, 100, 100, 0.3);
                color: rgba(255, 255, 255, 0.3);
            }
        """)
        recommendations_layout.addWidget(self.ai_calculate_btn, 3, 0, 1, 2)
        
        content_layout.addWidget(recommendations_group)
        
        # Control Buttons
        control_group = QGroupBox()
        control_group.setTitle("🎮 AI Tedavi Kontrolü")
        control_layout = QHBoxLayout(control_group)
        control_layout.setContentsMargins(24, 28, 24, 24)
        control_layout.setSpacing(16)
        
        self.ai_start_btn = QPushButton("AI Seansı Başlat")
        self.ai_start_btn.setIcon(QIcon(get_image_path("play.svg")))
        self.ai_start_btn.setMinimumHeight(48)
        self.ai_start_btn.setEnabled(False)  # Disabled until models loaded and patient selected
        self.ai_start_btn.clicked.connect(self._start_ai_session)
        self.ai_start_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #22c55e, stop:1 #16a34a);
                color: white;
                font-size: 14px;
                font-weight: 600;
                border-radius: 8px;
                padding: 12px 24px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #16a34a, stop:1 #15803d);
            }
            QPushButton:disabled {
                background: rgba(100, 100, 100, 0.3);
                color: rgba(255, 255, 255, 0.3);
            }
        """)
        
        self.ai_stop_btn = QPushButton("AI Seansı Durdur")
        self.ai_stop_btn.setIcon(QIcon(get_image_path("stop-circle.svg")))
        self.ai_stop_btn.setMinimumHeight(48)
        self.ai_stop_btn.clicked.connect(lambda: self._stop_ai_session(stop_reason='user_stopped'))
        self.ai_stop_btn.setEnabled(False)
        self.ai_stop_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #ef4444, stop:1 #dc2626);
                color: white;
                font-size: 14px;
                font-weight: 600;
                border-radius: 8px;
                padding: 12px 24px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #dc2626, stop:1 #b91c1c);
            }
            QPushButton:disabled {
                background: rgba(100, 100, 100, 0.3);
                color: rgba(255, 255, 255, 0.3);
            }
        """)
        
        control_layout.addWidget(self.ai_start_btn)
        control_layout.addWidget(self.ai_stop_btn)
        
        content_layout.addWidget(control_group)
        
        content_layout.addStretch()
        
        tab_layout.addWidget(scroll)
        
        # Patients will be loaded automatically by _on_patients_loaded when _load_patient_list() is called
        
        return tab_widget
    
    def _calculate_ai_recommendations(self):
        """Calculate AI recommendations asynchronously (loads models on first call)"""
        if not self.ai_controller or not AI_AVAILABLE:
            QMessageBox.warning(self, "AI Hatası", "AI controller kullanılamıyor.")
            return
        
        if not self.selected_patient:
            QMessageBox.warning(self, "Hasta Seçilmedi", "Lütfen önce bir hasta seçin.")
            return
        
        # Thread-safe model loading check
        # PERFORMANCE FIX C4: Move UI operations outside lock
        should_load_models = False
        is_loading = False
        
        with self.ai_model_load_lock:
            is_loading = self.ai_models_loading
            if not self.ai_models_loaded and not self.ai_models_loading:
                should_load_models = True
                self.ai_models_loading = True
        
        # UI operations outside lock (Performance Fix C4)
        if is_loading:
            QMessageBox.information(
                self,
                "Lütfen Bekleyin",
                "AI modelleri yükleniyor, lütfen bekleyin."
            )
            return
        
        if should_load_models:
            # Start loading models in background
            self.ai_calculate_btn.setEnabled(False)
            self.ai_calculate_btn.setText("⏳ Modeller Yükleniyor...")
            self.ai_message_label.setText("🔄 AI modelleri yükleniyor... (İlk yükleme)")
            QApplication.processEvents()
            self._load_ai_models_async()
            return  # Exit here - will be called again after models load
        
        # Models are loaded - proceed with calculation
        # UI'ı hazırla ve kilitle
        self.ai_calculate_btn.setEnabled(False)
        self.ai_message_label.setText("🔄 AI hesaplama yapılıyor... (Hibrit sistem)")
        QApplication.processEvents()

        try:
            # Verileri hazırla
            patient_id = self.selected_patient.get('id')
            # Species'i doğru yerden al
            species = self.selected_patient.get('info', {}).get('species', 'dog') if 'info' in self.selected_patient else self.selected_patient.get('species', 'dog')
            
            # Age ve weight'i de info'dan al
            patient_info = self.selected_patient.get('info', {}) if 'info' in self.selected_patient else self.selected_patient
            
            try:
                age = float(patient_info.get('age', 5))
            except (ValueError, TypeError):
                age = 5.0
            
            try:
                weight = float(patient_info.get('weight', 10))
            except (ValueError, TypeError):
                weight = 10.0
            
            treatment_target = self.ai_target_combo.currentText()
            
            # HİBRİT RECOMMENDER SİSTEMİ - Literatür + Adaptasyon + İnterpolasyon
            from ai.hybrid_recommender import get_recommendation
            
            recommendation = get_recommendation(
                patient_info={
                    'species': species,
                    'age': age,
                    'weight': weight
                },
                treatment_target=treatment_target,
                app_data_dir=self.app_data_dir
            )
            
            # Sonuçları UI'da göster
            final_freq = recommendation['freq']
            final_duty = recommendation['duty']
            final_duration = recommendation['duration']
            evidence = recommendation['evidence']
            source = recommendation['source']
            
            self.ai_freq_value.setText(f"{final_freq} Hz")
            self.ai_intensity_value.setText(f"{final_duty:.1f} %")
            self.ai_duration_value.setText(f"{final_duration} dakika")
            
            # Kaynak ve kanıt seviyesi bilgisi
            source_text = {
                'literature_exact': 'Literatür (Tam Eşleşme)',
                'interpolated': 'Benzer Protokollerden Tahmin',
                'default_wellness': 'Varsayılan Wellness Protokolü'
            }.get(source, 'Bilinmiyor')
            
            evidence_emoji = {
                'high': '⭐⭐⭐⭐',
                'medium': '⭐⭐⭐',
                'interpolated': '🔮',
                'unknown': '❓'
            }.get(evidence, '❓')
            
            self.ai_message_label.setText(
                f"✅ Öneriler hazır ({evidence_emoji})\n"
                f"Kaynak: {source_text}\n"
                f"Hasta: {species.capitalize()}, {age} yaş, {weight}kg"
            )
            
            # Log detaylı bilgi
            self.logger.info(
                f"AI Recommendation: {final_freq}Hz, {final_duty:.1f}%, {final_duration}min | "
                f"Source: {source}, Evidence: {evidence} | "
                f"Patient: {species}/{age}y/{weight}kg | "
                f"Target: {treatment_target}"
            )
            
            # Buton ve durum güncelle
            self.ai_calculate_btn.setEnabled(True)
            self.ai_calculate_btn.setText("🔮 AI Parametre Hesapla")
            
        except Exception as e:
            self.logger.error(f"AI parametre hesaplama hatası: {e}", exc_info=True)
            # Hasta seçiliyse butonu tekrar aç
            if self.selected_patient:
                self.ai_calculate_btn.setEnabled(True)
            else:
                self.ai_calculate_btn.setEnabled(False)
            self.ai_calculate_btn.setText("🔮 AI Parametre Hesapla")
            self.ai_message_label.setText(f"❌ Hata: {str(e)}")

    def _on_ai_calculation_finished(self, recommendations):
        """AI hesaplaması bittiğinde çağrılır"""
        # Hasta seçiliyse butonu tekrar aç
        if self.selected_patient:
            self.ai_calculate_btn.setEnabled(True)
        else:
            self.ai_calculate_btn.setEnabled(False)
        self.ai_calculate_btn.setText("🔮 AI Parametre Hesapla")
        
        if recommendations['status'] == 'success':
            freq = recommendations['frequency']
            intensities = recommendations['intensities']
            duration = recommendations['duration']
            confidence = recommendations['confidence']
            target = self.ai_target_combo.currentText()
            
            self.ai_freq_value.setText(f"{freq:.1f} Hz")
            self.ai_intensity_value.setText(f"{np.mean(intensities):.1f} %")
            self.ai_duration_value.setText(f"{int(duration)} dakika")
            
            self.ai_message_label.setText(
                f"✅ AI önerileri hesaplandı (Güven: %{int(confidence * 100)})\n"
                f"Hedef: {target}"
            )
        else:
            error_msg = recommendations.get('message', 'Bilinmeyen hata')
            self.ai_message_label.setText(f"❌ Hesaplama hatası: {error_msg}")

    def _on_ai_calculation_error(self, error_msg):
        """AI hesaplamasında hata olursa"""
        # Hasta seçiliyse butonu tekrar aç
        if self.selected_patient:
            self.ai_calculate_btn.setEnabled(True)
        else:
            self.ai_calculate_btn.setEnabled(False)
        self.ai_calculate_btn.setText("🔮 AI Parametre Hesapla")
        self.ai_message_label.setText(f"❌ Kritik Hata: {error_msg}")
        self.logger.error(f"AI Calculation thread error: {error_msg}")
    
    def _start_ai_session(self):
        """
        AI-controlled treatment session başlat - BASITLEŞTIRILMIŞ YAPI
        
        Değişiklikler:
        - Session DB'ye kaydedilmiyor (sadece memory'de SessionState)
        - AI controller sadece monitoring için kullanılıyor (session yaratmıyor)
        - Main window session yaratmıyor (sadece UI güncelle)
        - Stop edildiğinde tek kayıt yapılacak
        """
        if not self.ai_controller or not AI_AVAILABLE:
            QMessageBox.warning(self, "AI Hatası", "AI controller kullanılamıyor.")
            return
        
        if not self.selected_patient:
            QMessageBox.warning(self, "Hasta Seçilmedi", "Lütfen önce bir hasta seçin.")
            return
        
        # MQTT ve bağlı ESP kontrolü
        if not self.main_window or not hasattr(self.main_window, 'mqtt_client') or not self.main_window.mqtt_client:
            self.show_warning("MQTT bağlantısı bulunamadı!")
            return

        if not self.main_window.mqtt_client.is_connected():
            self.show_warning("MQTT bağlantısı yok! Lütfen bağlantıyı kontrol edin.")
            return

        connected_coils = self._get_connected_coils()
        if not connected_coils:
            self.show_warning("Bağlı Bobin bulunamadı! Lütfen bobin bağlantılarını kontrol edin.")
            return
        
        try:
            patient_id = self.selected_patient.get('id')
            # Species'i doğru yerden al
            species = self.selected_patient.get('info', {}).get('species', 'dog') if 'info' in self.selected_patient else self.selected_patient.get('species', 'dog')
            
            self.logger.info(f"AI seans başlatılıyor: patient_id={patient_id}, species={species}")
            
            # Önce AI önerilerini al (eğer hesaplanmışsa)
            ai_freq = None
            ai_intensity = None
            ai_duration = None
            
            try:
                # AI önerilerini parse et
                freq_text = self.ai_freq_value.text().replace(' Hz', '').strip()
                intensity_text = self.ai_intensity_value.text().replace(' %', '').strip()
                duration_text = self.ai_duration_value.text().replace(' dakika', '').strip()
                
                self.logger.debug(f"AI parametreleri: freq={freq_text}, intensity={intensity_text}, duration={duration_text}")
                
                if freq_text and freq_text != '-' and freq_text != '--':
                    ai_freq = float(freq_text)
                if intensity_text and intensity_text != '-' and intensity_text != '--':
                    ai_intensity = float(intensity_text)
                if duration_text and duration_text != '-' and duration_text != '--':
                    ai_duration = int(duration_text)
            except (ValueError, AttributeError) as e:
                self.logger.warning(f"AI parametreleri parse edilemedi: {e}")
            
            # Eğer AI parametreleri yoksa varsayılan değerleri kullan
            if not ai_freq or not ai_intensity or not ai_duration:
                self.logger.warning(f"AI parametreleri eksik: freq={ai_freq}, intensity={ai_intensity}, duration={ai_duration}")
                QMessageBox.warning(
                    self,
                    "AI Parametreleri Eksik",
                    "Lütfen önce 'AI Önerilerini Hesapla' butonuna tıklayın."
                )
                return
            
            self.logger.info(f"AI parametreleri hazır: freq={ai_freq} Hz, intensity={ai_intensity}%, duration={ai_duration} dk")
            
            # === YENİ: SessionState Oluştur (DB'ye kaydetme!) ===
            patient_info = self.selected_patient
            target_condition = 'AI Mod - ' + self.ai_target_combo.currentText()
            
            self.active_session = SessionState(
                start_time=datetime.now(),
                mode='ai',
                patient_info=patient_info,
                target_condition=target_condition,
                planned_duration=ai_duration,
                parameters={
                    'frequency': ai_freq,
                    'duty': ai_intensity,  # AI yoğunluk % cinsinden duty cycle olarak
                    'intensity': ai_intensity,
                },
                connected_coils=connected_coils,
                is_active=True,
                stop_reason=None
            )
            
            self.logger.info(
                f"AI session started (memory only): "
                f"patient={patient_info.get('info', {}).get('name', 'Unknown')}, "
                f"duration={ai_duration}min, target={target_condition}"
            )
            
            # AI controller ile monitoring başlat (SADECE monitoring, session yaratmıyor!)
            self.logger.info("AI controller başlatılıyor (monitoring only)...")
            success = self.ai_controller.start_ai_session(
                patient_id=patient_id,
                species=species,
                create_db_session=False  # unified_control SessionState ile yönetiyor
            )
            
            if success:
                self.logger.info("AI monitoring başlatıldı, şimdi bobinlere güç komutları gönderiliyor...")
                
                # ESP'lere PWM komutlarını gönder
                ai_freq_int = int(ai_freq)
                ai_duty = ai_intensity
                ai_duration_int = int(ai_duration)
                
                # start_all_coils ile tüm bağlı ESP'lere komut gönder
                self.start_all_coils(
                    override_freq=ai_freq_int,
                    override_duty=ai_duty,
                    override_duration=ai_duration_int
                )
                
                self.logger.info(f"Bobinlere güç komutları gönderildi: {ai_freq_int} Hz, {ai_duty}%, {ai_duration_int} dk")
                
                # Hasta bilgilerini main window'a kaydet
                if self.main_window:
                    self.main_window.last_saved_patient = patient_info
                
                # Main window'daki parametreleri güncelle (UI only, no session creation!)
                if self.main_window:
                    self.main_window.update_treatment_parameters({
                        'frequency': ai_freq,
                        'duration': ai_duration,
                        'intensity': ai_intensity,
                        'target': target_condition,
                        'mode': 'AI Mod'
                    })
                    
                    # Tedavi süresini ayarla
                    self.main_window.treatment_duration_minutes = ai_duration
                    
                    # IMPORTANT: start_treatment'a session kaydını ATLAT
                    self.main_window.start_treatment(create_session=False)
                
                # UI durumunu güncelle
                self.treatment_active = True
                self.ai_start_btn.setEnabled(False)
                self.ai_stop_btn.setEnabled(True)
                
                # Kalan süre gösterimi için gereken değişkenleri ayarla
                self.treatment_start_time = time.time()
                self.treatment_duration = ai_duration * 60  # dakikayı saniyeye çevir
                
                self.ai_message_label.setText(
                    f"✅ AI tedavisi başlatıldı\n"
                    f"Frekans: {ai_freq:.1f} Hz, Yoğunluk: {ai_intensity:.1f}%, Süre: {ai_duration} dk\n"
                    f"Bağlı Bobin sayısı: {len(connected_coils)}"
                )
                self.ai_status_label.setText("● Aktif")
                self.ai_status_label.setStyleSheet("""
                    QLabel {
                        color: #22c55e;
                        font-size: 18px;
                        font-weight: 700;
                    }
                """)
                
                # Durum güncellemeleri
                self.status_dot.setStyleSheet("color: #22c55e; font-size: 18px;")
                self.status_text.setText("AI Seansı Aktif")
                
                # ✅ MQTT'ye session bilgilerini publish et (Android app için)
                self._publish_session_status_to_mqtt(
                    active=True,
                    mode='ai',
                    patient_name=patient_info['info'].get('name', 'Bilinmiyor') if patient_info and 'info' in patient_info else 'Bilinmiyor',
                    target=target_condition,
                    duration_minutes=ai_duration,
                    frequency=ai_freq,
                    intensity=ai_intensity,
                    duty_cycle=ai_duty,
                    connected_coils_count=len(connected_coils)
                )
                
                self.logger.info(
                    f"AI session started for patient {patient_id}: "
                    f"freq={ai_freq}Hz, intensity={ai_intensity}%, duration={ai_duration}min, "
                    f"connected_coils={len(connected_coils)}"
                )
                
                # Başarı mesajı
                patient_name = patient_info['info'].get('name', 'Bilinmiyor') if patient_info and 'info' in patient_info else 'Bilinmiyor'
                patient_species = patient_info['info'].get('species', 'Bilinmiyor') if patient_info and 'info' in patient_info else 'Bilinmiyor'
                
                QMessageBox.information(
                    self,
                    "AI Seansı Başlatıldı",
                    f"AI Mod Seansı başlatıldı:\n"
                    f"Hasta: {patient_name} ({patient_species})\n"
                    f"Frekans: {ai_freq:.1f} Hz\n"
                    f"Yoğunluk: {ai_intensity:.1f}%\n"
                    f"Süre: {ai_duration} dakika\n"
                    f"Hedef: {self.ai_target_combo.currentText()}\n"
                    f"Bağlı Bobin sayısı: {len(connected_coils)}\n\n"
                    f"Not: Seans durduğunda otomatik kaydedilecek.",
                    QMessageBox.StandardButton.Ok
                )
            else:
                QMessageBox.warning(self, "Başlatma Hatası", "AI monitoring başlatılamadı.")
        except Exception as e:
            self.logger.error(f"Failed to start AI session: {e}", exc_info=True)
            QMessageBox.critical(self, "Hata", f"AI seansı başlatılamadı: {str(e)}")
    
    def _stop_ai_session(self, stop_reason: str = 'manual_stop'):
        """
        AI-controlled treatment session durdur - BASITLEŞTIRILMIŞ YAPI
        
        Değişiklikler:
        - stop_treatment() metodunu kullanarak tek kayıt yapılıyor
        - AI controller sadece monitoring'i durduruyor (session kapatmıyor)
        
        Args:
            stop_reason: Durma sebebi (completed/manual_stop/error/emergency)
        """
        if not self.ai_controller:
            return
        
        try:
            # stop_treatment() metodunu kullan (session'ı kaydedecek)
            self.stop_treatment(stop_reason=stop_reason)
            
            # AI controller'ı durdur (sadece monitoring'i durdurur, DB session kapatmaz)
            summary = self.ai_controller.stop_ai_session(close_db_session=False)
            
            # UI durumunu güncelle (AI-specific)
            self.ai_start_btn.setEnabled(True)
            self.ai_stop_btn.setEnabled(False)
            self.ai_message_label.setText(f"AI tedavisi durduruldu ({stop_reason})")
            self.ai_status_label.setText("● Durduruldu")
            self.ai_status_label.setStyleSheet("""
                QLabel {
                    color: #ef4444;
                    font-size: 18px;
                    font-weight: 700;
                }
            """)
            
            # Show summary
            if summary:
                total_alerts = summary.get('total_alerts', 0)
                msg = f"AI seansı tamamlandı.\n\nToplam uyarı: {total_alerts}"
                QMessageBox.information(self, "Seans Tamamlandı", msg)
            
            self.logger.info(f"AI session stopped with reason: {stop_reason}")
        except Exception as e:
            self.logger.error(f"Failed to stop AI session: {e}", exc_info=True)
    
    def _on_ai_status_changed(self, status: str, confidence: float, details: dict):
        """Handle AI status changes"""
        # Update status label
        color = "#22c55e" if status == "Normal" else "#fbbf24" if status == "Warning" else "#ef4444"
        self.ai_status_label.setText(f"● {status}")
        self.ai_status_label.setStyleSheet(f"""
            QLabel {{
                color: {color};
                font-size: 18px;
                font-weight: 700;
            }}
        """)
        
        # Update confidence
        self.ai_confidence_label.setText(f"Güven: %{int(confidence * 100)}")
        
        # Update message
        if 'message' in details:
            self.ai_message_label.setText(details['message'])
    
    def _on_ai_parameters_updated(self, parameters: dict):
        """Handle AI parameter updates"""
        freq = parameters.get('frequency', 0)
        intensities = parameters.get('intensities', [])
        duration = parameters.get('duration', 0)
        
        # Update recommendation display
        self.ai_freq_value.setText(f"{freq:.1f} Hz")
        if intensities:
            avg_intensity = sum(intensities) / len(intensities)
            self.ai_intensity_value.setText(f"{avg_intensity:.0f} %")
        self.ai_duration_value.setText(f"{duration:.0f} dakika")
    
    def _on_ai_anomaly_detected(self, alert_type: str, details: dict):
        """Handle AI anomaly detection"""
        message = details.get('message', 'Anomali tespit edildi')
        action = details.get('action', 'continue')
        
        if action == 'stop_immediately':
            QMessageBox.critical(self, "KRİTİK UYARI", f"Tedavi durduruldu!\n\n{message}")
            self._stop_ai_session()
        elif action == 'reduce_intensity':
            QMessageBox.warning(self, "UYARI", f"Yoğunluk azaltıldı.\n\n{message}")
        
        self.logger.warning(f"AI anomaly: {alert_type} - {message}")
        
    def _on_tab_changed(self, index):
        """Tab değiştiğinde çağrılır"""
        if index == 0:
            self.current_mode = "automatic"
            self.status_bar.showMessage("Otomatik mod aktif")
        elif index == 1:
            self.current_mode = "manual"
            self.status_bar.showMessage("Manuel mod aktif")
        elif index == 2:
            self.current_mode = "ai"
            self.status_bar.showMessage("AI mod aktif")
            
    def update_automatic_parameters(self):
        """
        Seçilen hedefe göre otomatik parametreleri güncelle
        
        Parametreler pemf_optimized_table.html'deki optimize edilmiş parametre tablosuna göre ayarlanmıştır.
        Frekans aralığı: 50-150 Hz (cihaz kapasitesine uygun)
        Yoğunluk aralığı: 0.8-2.5 mT
        Süre: 20-60 dakika
        Duty Cycle: 35-50%
        """
        target = self.target_combo.currentText()
        
        # Varsayılan parametreler (Genel Rahatlama/Wellness)
        params = {
            'frequency': 77.5,  # 65-90 Hz aralığının ortası
            'duration': 30,
            'intensity': 1.0,   # 0.8-1.2 mT aralığının ortası
            'duty_cycle': 50.0
        }
        
        # Hedefe göre optimize edilmiş parametre tablosundaki değerleri ayarla
        if "Kronik Artrit" in target:
            # 60-80 Hz, 1.5-2.0 mT, 30 dk, 50%
            params = {'frequency': 70.0, 'duration': 30, 'intensity': 1.75, 'duty_cycle': 50.0}
        elif "Osteoartrit" in target:
            # 70-90 Hz, 1.5-2.0 mT, 30 dk, 50%
            params = {'frequency': 80.0, 'duration': 30, 'intensity': 1.75, 'duty_cycle': 50.0}
        elif "İnflamasyon" in target:
            # 75-100 Hz, 1.0-1.5 mT, 25-30 dk, 45-50%
            params = {'frequency': 87.5, 'duration': 27, 'intensity': 1.25, 'duty_cycle': 47.5}
        elif "Kırık İyileşmesi" in target:
            # 50-70 Hz, 1.8-2.2 mT, 45-60 dk, 35-40%
            params = {'frequency': 60.0, 'duration': 52, 'intensity': 2.0, 'duty_cycle': 37.5}
        elif "Post-op Yara İyileşmesi" in target:
            # 80-110 Hz, 1.0-2.0 mT, 30 dk, 50%
            params = {'frequency': 95.0, 'duration': 30, 'intensity': 1.5, 'duty_cycle': 50.0}
        elif "Doku İyileşmesi" in target:
            # 90-120 Hz, 1.0-2.0 mT, 30 dk, 50%
            params = {'frequency': 105.0, 'duration': 30, 'intensity': 1.5, 'duty_cycle': 50.0}
        elif "Anksiyete/Stres" in target:
            # 50-75 Hz, 1.5-2.5 mT, 30-45 dk, 45%
            params = {'frequency': 62.5, 'duration': 37, 'intensity': 2.0, 'duty_cycle': 45.0}
        elif "Kas Gerginliği/Spazm" in target:
            # 85-110 Hz, 1.2-1.8 mT, 20-30 dk, 50%
            params = {'frequency': 97.5, 'duration': 25, 'intensity': 1.5, 'duty_cycle': 50.0}
        elif "Nörolojik" in target or "IVDD" in target or "Nöropati" in target:
            # 55-85 Hz, 0.8-1.5 mT, 30-45 dk, 40-45%
            params = {'frequency': 70.0, 'duration': 37, 'intensity': 1.15, 'duty_cycle': 42.5}
        elif "Genel Rahatlama/Wellness" in target:
            # 65-90 Hz, 0.8-1.2 mT, 30 dk, 50%
            params = {'frequency': 77.5, 'duration': 30, 'intensity': 1.0, 'duty_cycle': 50.0}
        elif "Ödematöz Dokular" in target:
            # 95-125 Hz, 1.0-2.0 mT, 20-30 dk, 45%
            params = {'frequency': 110.0, 'duration': 25, 'intensity': 1.5, 'duty_cycle': 45.0}
        elif "Tendon/Ligament Yaralanması" in target:
            # 60-90 Hz, 1.5-2.0 mT, 30-45 dk, 40%
            params = {'frequency': 75.0, 'duration': 37, 'intensity': 1.75, 'duty_cycle': 40.0}
        
        # UI'yi güncelle
        self.auto_frequency_spin.setValue(params['frequency'])
        self.auto_duration_spin.setValue(params['duration'])
        self.auto_intensity_spin.setValue(params['intensity'])
        self.auto_duty_cycle_spin.setValue(params['duty_cycle'])
        
        # Log bilimsel protokol bilgisi
        self.logger.info(f"Otomatik parametreler güncellendi: {target} -> "
                        f"Frekans: {params['frequency']} Hz, "
                        f"Yoğunluk: {params['intensity']} mT, "
                        f"Süre: {params['duration']} dk, "
                        f"Duty Cycle: {params['duty_cycle']}% (Optimize edilmiş parametre tablosuna göre)")
        
    def start_automatic_treatment(self):
        """
        Otomatik tedavi başlat - BASITLEŞTIRILMIŞ YAPI
        
        Değişiklikler:
        - Session DB'ye kaydedilmiyor (sadece memory'de SessionState)
        - Main window session yaratmıyor (sadece UI güncelle)
        - Stop edildiğinde tek kayıt yapılacak
        """
        try:
            # Hasta seçimi kontrolü
            if not self.selected_patient:
                QMessageBox.warning(
                    self,
                    "Hasta Seçimi Gerekli",
                    "Lütfen tedavi başlatmadan önce bir hasta seçin.",
                    QMessageBox.StandardButton.Ok
                )
                return
            
            # MQTT ve bağlı ESP kontrolü
            if not self.main_window or not hasattr(self.main_window, 'mqtt_client') or not self.main_window.mqtt_client:
                self.show_warning("MQTT bağlantısı bulunamadı!")
                return

            if not self.main_window.mqtt_client.is_connected():
                self.show_warning("MQTT bağlantısı yok! Lütfen bağlantıyı kontrol edin.")
                return

            connected_coils = self._get_connected_coils()
            if not connected_coils:
                self.show_warning("Bağlı Bobin bulunamadı! Lütfen bobin bağlantılarını kontrol edin.")
                return

            # Süre diyalogu
            duration, ok = QInputDialog.getInt(
                self,
                "Seans Süresi",
                "Güç süresi (dakika):",
                20,
                1,
                120,
                1
            )
            if not ok:
                return

            # Parametreleri sabitle
            frequency = 100
            duty_cycle = 50.0
            intensity = self.auto_intensity_spin.value()
            target = self.target_combo.currentText()
            
            # Hasta bilgilerini al (seçilen hastadan)
            patient_info = self.selected_patient
            
            # === YENİ: Session State Oluştur (DB'ye kaydetme!) ===
            self.active_session = SessionState(
                start_time=datetime.now(),
                mode='automatic',
                patient_info=patient_info,
                target_condition=target,
                planned_duration=duration,
                parameters={
                    'frequency': frequency,
                    'duty': duty_cycle,
                    'intensity': intensity,
                },
                connected_coils=connected_coils,
                is_active=True,
                stop_reason=None
            )
            
            self.logger.info(
                f"Automatic session started (memory only): "
                f"patient={patient_info.get('info', {}).get('name', 'Unknown')}, "
                f"duration={duration}min, target={target}"
            )
            
            # Main window'a hasta bilgisini kaydet
            if self.main_window:
                self.main_window.last_saved_patient = patient_info
            
            # Ana pencereye tedavi parametrelerini gönder (UI update only, no session creation!)
            if self.main_window:
                # Tedavi parametrelerini güncelle
                self.main_window.update_treatment_parameters({
                    'frequency': frequency,
                    'duration': duration,
                    'intensity': intensity,
                    'target': target,
                    'mode': 'Otonom Mod'
                })
                
                # Tedavi süresini ayarla
                self.main_window.treatment_duration_minutes = duration
                
                # IMPORTANT: start_treatment'a session kaydını ATLAT
                # (unified_control SessionState ile yönetiyor)
                self.main_window.start_treatment(create_session=False)

            # Bağlı tüm ESP'lere sabit PWM komutu gönder
            self.start_all_coils(
                override_freq=frequency,
                override_duty=duty_cycle,
                override_duration=duration
            )
            
            # UI durumunu güncelle
            self.treatment_active = True
            self.auto_start_btn.setEnabled(False)
            self.auto_stop_btn.setEnabled(True)
            
            # Kalan süre gösterimi için gereken değişkenleri ayarla
            self.treatment_start_time = time.time()
            self.treatment_duration = duration * 60  # dakikayı saniyeye çevir
            
            # Durum güncellemeleri
            self.status_dot.setStyleSheet("color: #f59e0b; font-size: 18px;")
            self.status_text.setText("Seans Aktif")
            self.progress_label.setText(f"Seans başlatıldı: {target}")
            
            # ✅ MQTT'ye session bilgilerini publish et (Android app için)
            self._publish_session_status_to_mqtt(
                active=True,
                mode='automatic',
                patient_name=patient_info['info'].get('name', 'Bilinmiyor') if patient_info and 'info' in patient_info else 'Bilinmiyor',
                target=target,
                duration_minutes=duration,
                frequency=frequency,
                intensity=intensity,
                duty_cycle=duty_cycle,
                connected_coils_count=len(connected_coils)
            )
            
            # Başarı mesajı
            patient_name = patient_info['info'].get('name', 'Bilinmiyor') if patient_info and 'info' in patient_info else 'Bilinmiyor'
            patient_species = patient_info['info'].get('species', 'Bilinmiyor') if patient_info and 'info' in patient_info else 'Bilinmiyor'
            
            QMessageBox.information(
                self,
                "Seans Başlatıldı",
                f"Otomatik Seans başlatıldı:\n"
                f"Hasta: {patient_name} ({patient_species})\n"
                f"Frekans: {frequency:.0f} Hz\n"
                f"Duty Cycle: {duty_cycle:.0f}%\n"
                f"Süre: {duration} dakika\n"
                f"Yoğunluk: {intensity} mT\n"
                f"Hedef: {target}\n"
                f"Bağlı Bobin sayısı: {len(connected_coils)}\n\n"
                f"Not: Seans durduğunda otomatik kaydedilecek.",
                QMessageBox.StandardButton.Ok
            )
            
        except Exception as e:
            self.logger.error(f"Otomatik seans başlatılırken hata: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "Hata",
                f"Seans başlatılırken hata oluştu:\n{str(e)}",
                QMessageBox.StandardButton.Ok
            )

    def stop_treatment(self, stop_reason: str = 'manual_stop'):
        """
        Tedaviyi durdur - BASITLEŞTIRILMIŞ YAPI
        
        Değişiklikler:
        - stop_reason parametresi eklendi (completed, manual_stop, error, emergency)
        - active_session bilgilerini DB'ye tek kayıt olarak yazıyor
        - Eski session_manager.end_session kaldırıldı
        
        Args:
            stop_reason: Durma sebebi (completed/manual_stop/error/emergency)
        """
        try:
            # ESP'lere stop komutu gönder
            if self.main_window and hasattr(self.main_window, 'mqtt_client') and self.main_window.mqtt_client:
                connected_coils = self._get_connected_coils()
                
                if connected_coils:
                    for coil_id in connected_coils:
                        command_id = self._get_next_command_id(coil_id)
                        
                        command = {
                            "command": "stop",
                            "command_id": command_id,
                            "timestamp": time.time()
                        }
                        
                        with self.pending_commands_lock:
                            self.pending_commands[command_id] = {
                                'coil_num': coil_id,
                                'command': command,
                                'timestamp': time.time(),
                                'retry_count': 0
                            }
                        
                        topic = f"pemf/coil/{coil_id}/control"
                        self.main_window.mqtt_client.publish(topic, json.dumps(command), qos=1)
                    
                    self.logger.info(f"{len(connected_coils)} bağlı bobine stop komutu gönderildi")
                else:
                    self.logger.warning("Bağlı bobin bulunamadı, stop komutu gönderilemedi")
            
            # === YENİ: Active session'ı DB'ye tek kayıt olarak yaz ===
            if self.active_session and self.active_session.is_active:
                # Stop reason'u set et
                self.active_session.stop_reason = stop_reason
                self.active_session.is_active = False
                
                # Gerçek süreyi hesapla
                actual_duration = self.active_session.get_actual_duration_minutes()
                
                # DB'ye kaydet (TEK KAYIT)
                try:
                    session_id = self.db.save_completed_session(
                        mode=self.active_session.mode,
                        patient_info=self.active_session.patient_info,
                        target_condition=self.active_session.target_condition,
                        start_time=self.active_session.start_time,
                        duration_minutes=actual_duration,
                        planned_duration=self.active_session.planned_duration,
                        parameters=self.active_session.parameters,
                        stop_reason=stop_reason,
                        connected_coils=self.active_session.connected_coils
                    )
                    
                    patient_name = self.active_session.patient_info.get('info', {}).get('name', 'Unknown')
                    self.logger.info(
                        f"Session saved to DB: id={session_id}, mode={self.active_session.mode}, "
                        f"patient={patient_name}, duration={actual_duration}min, reason={stop_reason}"
                    )
                    
                    # Session'ı temizle
                    self.active_session = None
                    
                except Exception as e:
                    self.logger.error(f"Session DB'ye kaydedilemedi: {e}", exc_info=True)
                    self.show_error(f"Seans kaydı başarısız: {str(e)}")
            else:
                self.logger.warning("stop_treatment çağrıldı ama active_session yok!")
            
            # Eski session_manager kullanımı KALDIRILDI
            # if self.current_session_id:
            #     self.session_manager.end_session(session_id=self.current_session_id, final_notes="Seans tamamlandı")
            #     self.current_session_id = None
            
            # UI güncelle
            self.treatment_active = False
            self.auto_start_btn.setEnabled(True)
            self.auto_stop_btn.setEnabled(False)
            self.progress_label.setText("Seans durduruldu")
            self.remaining_time_label.setText("--")
            
            # Kalan süre değişkenlerini temizle
            if hasattr(self, 'treatment_start_time'):
                delattr(self, 'treatment_start_time')
            if hasattr(self, 'treatment_duration'):
                delattr(self, 'treatment_duration')
            
            # Timer'ları durdur
            self.treatment_timer.stop()
            # treatment_countdown_timer merged into unified_1hz_timer (no separate timer)
            
            # Ana penceredeki tedavi durumunu güncelle
            if self.main_window and hasattr(self.main_window, 'stop_treatment'):
                self.main_window.stop_treatment(from_unified_control=True)
            
            self.show_info(f"Seans durduruldu (sebep: {stop_reason})")
            
            # ✅ MQTT'ye session durduruldu bilgisi gönder (Android app için)
            self._publish_session_status_to_mqtt(
                active=False,
                mode='',
                patient_name='',
                target='',
                duration_minutes=0,
                frequency=0,
                intensity=0,
                duty_cycle=0,
                connected_coils_count=0
            )
            
            # Log kaydet (eski auto_logger - backward compatibility)
            if hasattr(self, 'auto_logger'):
                self.auto_logger.log_treatment_event("stop", f"Seans durduruldu: {stop_reason}")
            
        except Exception as e:
            self.logger.error(f"Seans durdurulamadı: {e}", exc_info=True)
            self.show_error(f"Seans durdurulamadı: {str(e)}")
            if hasattr(self, 'auto_logger'):
                self.auto_logger.log_treatment_event("error", f"Seans durdurma hatası: {str(e)}")

    def apply_to_all_coils(self):
        """Ana parametreleri tüm bağlı bobinlere uygula - UI ve ESP'leri güncelle"""
        try:
            freq = self.master_freq_spin.value()
            duty = self.master_duty_spin.value()
            duration = self.master_duration_spin.value()
            
            # 1. UI'daki tüm bobinlerin spin box'larını güncelle
            for coil_num in range(1, 9):
                controls = self.coil_controls[coil_num]
                controls['freq_spin'].setValue(freq)
                controls['duty_spin'].setValue(duty)
                controls['duration_spin'].setValue(duration)
            
            # 2. Bağlı ESP'lere set_params komutu gönder
            if not self.main_window or not hasattr(self.main_window, 'mqtt_client') or not self.main_window.mqtt_client:
                self.show_warning("MQTT bağlantısı bulunamadı! UI güncellendi ancak bobinlere komut gönderilemedi.")
                return
            
            # MQTT bağlantısını kontrol et
            mqtt_connected = False
            if self.main_window.mqtt_client and self.main_window.mqtt_client.is_connected():
                mqtt_connected = True
            
            if not mqtt_connected:
                self.show_warning("MQTT bağlantısı yok! UI güncellendi ancak bobinlere komut gönderilemedi.")
                return
            
            # Bağlı ESP'leri kontrol et
            current_time = time.time()
            connected_coils = []
            
            for coil_id in range(1, 9):
                # MQTT bağlı, heartbeat kontrolü yap
                last_status_time = getattr(self, 'coil_last_status_time', {}).get(coil_id, 0)
                is_connected = False
                
                if last_status_time > 0:
                    # Heartbeat timeout kontrolü (ESP_TIMEOUT kullan, yoksa 5 saniye)
                    esp_timeout = getattr(self, 'ESP_TIMEOUT', 5.0)
                    is_connected = (current_time - last_status_time) <= esp_timeout
                else:
                    # Hiç status mesajı gelmemiş, bağlı değil sayılır
                    is_connected = False
                
                # coil_connection_status dictionary'sinden de kontrol et
                coil_connection_status = getattr(self, 'coil_connection_status', {})
                if coil_id in coil_connection_status:
                    is_connected = coil_connection_status[coil_id]
                
                if is_connected:
                    connected_coils.append(coil_id)
            
            if not connected_coils:
                self.show_warning("Bağlı Bobin bulunamadı! UI güncellendi ancak bobinlere komut gönderilemedi.")
                return
            
            # Sadece bağlı bobinlere komut gönder
            commands_sent = 0
            for coil_id in connected_coils:
                # Unique command ID oluştur (thread-safe)
                command_id = self._get_next_command_id(coil_id)
                
                command = {
                    "command": "set_params",
                    "command_id": command_id,
                    "freq": int(freq),
                    "duty": float(duty),
                    "duration": int(duration),
                    "timestamp": time.time()
                }
                
                # Pending commands'a ekle (thread-safe)
                with self.pending_commands_lock:
                    self.pending_commands[command_id] = {
                        'coil_num': coil_id,
                        'command': command,
                        'timestamp': time.time(),
                        'retry_count': 0
                    }
                
                # Send command via MainWindow signal (ensures only MainWindow writes to MQTT)
                if self.main_window and hasattr(self.main_window, 'coil_control_requested'):
                    self.main_window.coil_control_requested.emit(coil_id, command)
                    commands_sent += 1
                    self.logger.info(f"Set params command sent to connected coil {coil_id}")
                else:
                    self.show_warning("MainWindow coil control signal not available!")
                    return
            
            if commands_sent > 0:
                self.show_success(f"Ana parametreler tüm bobinlere uygulandı ({commands_sent} bağlı bobine komut gönderildi)")
            else:
                self.show_info("Ana parametreler tüm bobinlere uygulandı (bobinlere komut gönderilemedi)")
            
        except Exception as e:
            self.logger.error(f"Error in apply_to_all_coils: {e}", exc_info=True)
            self.show_error(f"Parametreler uygulanırken hata oluştu: {str(e)}")

    def start_coil(self, coil_num):
        """Belirli bobini başlat (GUI Stability Fix #4 - QoS 1 + ACK)"""
        try:
            if not self.main_window or not hasattr(self.main_window, 'mqtt_client') or not self.main_window.mqtt_client:
                self.show_warning("MQTT bağlantısı bulunamadı!")
                return
                
            controls = self.coil_controls[coil_num]
            
            # Parametreleri al
            freq_raw = controls['freq_spin'].value()
            duty_raw = controls['duty_spin'].value()
            duration_raw = controls['duration_spin'].value()
            
            # DEBUG: Log raw değerleri
            self.logger.debug(f"Coil {coil_num} raw parametreler: freq={freq_raw}, duty={duty_raw}, duration={duration_raw}")
            
            # Tip dönüşümü (MQTT validation için gerekli)
            freq = int(round(freq_raw))
            duty = float(duty_raw)
            duration = int(round(duration_raw))
            
            # DEBUG: Log dönüştürülmüş değerleri
            self.logger.debug(f"Coil {coil_num} dönüştürülmüş parametreler: freq={freq}, duty={duty}, duration={duration}")
            
            # Unique command ID oluştur (thread-safe)
            command_id = self._get_next_command_id(coil_num)
            
            # Hedef başlangıç zamanı (NTP tabanlı senkronizasyon için)
            # Şu anki zaman + 5000ms buffer (tek ESP için yeterli)
            target_start_time = int(time.time() * 1000) + 5000
            
            # MQTT komutu oluştur (command_id ve start_at ekle)
            command = {
                "command": "start",
                "command_id": command_id,
                "freq": freq,
                "duty": duty,
                "duration": duration,
                "start_at": target_start_time,  # NTP tabanlı senkronizasyon için hedef zaman
                "timestamp": time.time()
            }
            
            # Pending commands'a ekle (thread-safe)
            with self.pending_commands_lock:
                self.pending_commands[command_id] = {
                    'coil_num': coil_num,
                    'command': command,
                    'timestamp': time.time(),
                    'retry_count': 0
                }
            
            # Send command via MainWindow signal (ensures only MainWindow writes to MQTT)
            # This prevents conflicts when multiple windows try to control the same coil
            if self.main_window and hasattr(self.main_window, 'coil_control_requested'):
                self.main_window.coil_control_requested.emit(coil_num, command)
            else:
                self.show_warning("MainWindow coil control signal not available!")
                return
            
            # UI güncelle - "Gönderiliyor" durumu
            controls['status_led'].setStyleSheet("color: #f59e0b; font-size: 12px;")
            controls['status_label'].setText("Gönderiliyor...")
            controls['status_container'].setStyleSheet("""
                background: rgba(245, 158, 11, 0.1);
                border-radius: 12px;
                border: 1px solid rgba(245, 158, 11, 0.3);
            """)
            controls['start_btn'].setEnabled(False)
            
            self.logger.info(f"Coil {coil_num} start command requested via MainWindow signal: {command_id}")
            
        except Exception as e:
            self.show_error(f"Bobin {coil_num} başlatılamadı: {str(e)}")
            
    def stop_coil(self, coil_num):
        """Belirli bobini durdur (GUI Stability Fix #4 - QoS 1 + ACK)"""
        try:
            if not self.main_window or not hasattr(self.main_window, 'mqtt_client') or not self.main_window.mqtt_client:
                self.show_warning("MQTT bağlantısı bulunamadı!")
                return
                
            controls = self.coil_controls[coil_num]
            
            # Unique command ID oluştur (thread-safe)
            command_id = self._get_next_command_id(coil_num)
            
            # MQTT komutu oluştur (command_id ekle)
            command = {
                "command": "stop",
                "command_id": command_id,
                "timestamp": time.time()
            }
            
            # Pending commands'a ekle (thread-safe)
            with self.pending_commands_lock:
                self.pending_commands[command_id] = {
                    'coil_num': coil_num,
                    'command': command,
                    'timestamp': time.time(),
                    'retry_count': 0
                }
            
            # Send command via MainWindow signal (ensures only MainWindow writes to MQTT)
            # This prevents conflicts when multiple windows try to control the same coil
            if self.main_window and hasattr(self.main_window, 'coil_control_requested'):
                self.main_window.coil_control_requested.emit(coil_num, command)
            else:
                self.show_warning("MainWindow coil control signal not available!")
                return
            
            # UI güncelle - "Gönderiliyor" durumu
            controls['status_led'].setStyleSheet("color: #f59e0b; font-size: 12px;")
            controls['status_label'].setText("Durduruluyor...")
            controls['status_container'].setStyleSheet("""
                background: rgba(245, 158, 11, 0.1);
                border-radius: 12px;
                border: 1px solid rgba(245, 158, 11, 0.3);
            """)
            controls['stop_btn'].setEnabled(False)
            
            self.logger.info(f"Coil {coil_num} stop command requested via MainWindow signal: {command_id}")
            
        except Exception as e:
            self.show_error(f"Bobin {coil_num} durdurulamadı: {str(e)}")

    def _get_connected_coils(self) -> List[int]:
        """Bağlı olan ESP bobinlerinin listesini döndür."""
        connected_coils = []
        current_time = time.time()
        esp_timeout = getattr(self, 'ESP_TIMEOUT', 5.0)
        coil_status_map = getattr(self, 'coil_connection_status', {})
        last_status_map = getattr(self, 'coil_last_status_time', {})

        for coil_id in range(1, 9):
            is_connected = False
            last_status_time = last_status_map.get(coil_id, 0)

            if last_status_time > 0:
                is_connected = (current_time - last_status_time) <= esp_timeout

            if coil_id in coil_status_map:
                is_connected = coil_status_map[coil_id]

            if is_connected:
                connected_coils.append(coil_id)

        return connected_coils

    def start_all_coils(self, override_freq: Optional[float] = None, override_duty: Optional[float] = None, override_duration: Optional[int] = None):
        """Tüm bağlı bobinleri başlat - sadece bağlı ESP'lere komut gönderir"""
        try:
            if not self.main_window or not hasattr(self.main_window, 'mqtt_client') or not self.main_window.mqtt_client:
                self.show_warning("MQTT bağlantısı bulunamadı!")
                return
            
            # MQTT bağlantısını kontrol et
            mqtt_connected = False
            if self.main_window.mqtt_client and self.main_window.mqtt_client.is_connected():
                mqtt_connected = True
            
            if not mqtt_connected:
                self.show_warning("MQTT bağlantısı yok! Bağlı ESP'lere komut gönderilemiyor.")
                return
            
            connected_coils = self._get_connected_coils()
            
            if not connected_coils:
                self.show_warning("Bağlı Bobin bulunamadı! Hiçbir bobin başlatılamadı.")
                return
            
            # NTP/Epoch Time tabanlı senkronizasyon için hedef zaman hesapla
            # Dinamik buffer: ESP sayısına göre ayarla (her ESP için ~50ms + network delay)
            # Minimum 5000ms, her ESP için +200ms ekle
            buffer_ms = max(5000, 5000 + (len(connected_coils) * 200))
            target_start_time = int(time.time() * 1000) + buffer_ms  # Milisaniye cinsinden epoch
            
            # BATCH GÖNDERİM: Önce tüm komutları hazırla, sonra hızlıca gönder
            # Bu sayede gönderim süresi minimize edilir ve senkronizasyon iyileşir
            prepared_commands = []  # [(coil_id, command, command_id)]
            
            for coil_id in connected_coils:
                # Her bobin için kendi kutusundaki değerleri al
                controls = self.coil_controls[coil_id]
                
                # Override parametreler varsa onları kullan, yoksa bobin'in kendi değerlerini al
                if override_freq is not None:
                    freq = override_freq
                else:
                    freq = controls['freq_spin'].value()
                
                if override_duty is not None:
                    duty = override_duty
                else:
                    duty = controls['duty_spin'].value()
                
                if override_duration is not None:
                    duration = override_duration
                else:
                    duration = controls['duration_spin'].value()
                
                # DEBUG: Log değerleri kontrol et
                self.logger.debug(
                    f"Coil {coil_id} parametreleri: freq_raw={freq}, duty_raw={duty}, duration_raw={duration}, "
                    f"override_freq={override_freq}, override_duty={override_duty}, override_duration={override_duration}"
                )
                
                # MQTT validation needs integer frequency and duration
                freq = int(round(freq))
                duration = int(round(duration))
                duty = float(duty)
                
                # DEBUG: Log dönüştürülmüş değerleri
                self.logger.debug(f"Coil {coil_id} dönüştürülmüş parametreler: freq={freq}, duty={duty}, duration={duration}")
                
                # Unique command ID oluştur (thread-safe)
                command_id = self._get_next_command_id(coil_id)
                
                # Komut oluştur (her ESP'ye kendi parametreleri ve aynı start_at zamanı ile)
                command = {
                    "command": "start",
                    "command_id": command_id,  # ESP ACK için gerekli
                    "freq": freq,
                    "duty": duty,
                    "duration": duration,
                    "start_at": target_start_time,  # KRİTİK: NTP tabanlı senkronizasyon için hedef zaman
                    "timestamp": time.time()
                }
                    
                # Pending commands'a ekle (thread-safe)
                with self.pending_commands_lock:
                    self.pending_commands[command_id] = {
                        'coil_num': coil_id,
                        'command': command,
                        'timestamp': time.time(),
                        'retry_count': 0
                    }
                
                # Komutu hazırla (henüz gönderme)
                prepared_commands.append((coil_id, command, command_id))
                
                # UI güncelle - "Başlatılıyor" durumu (göndermeden önce)
                coil_controls = self.coil_controls[coil_id]
                coil_controls['status_container'].setStyleSheet("""
                    background: rgba(245, 158, 11, 0.1);
                    border-radius: 12px;
                    border: 1px solid rgba(245, 158, 11, 0.3);
                """)
                coil_controls['start_btn'].setEnabled(False)
                coil_controls['status_led'].setStyleSheet("color: #f59e0b; font-size: 12px;")
                coil_controls['status_label'].setText("Başlatılıyor...")
            
            # Tüm komutları hızlıca gönder (batch gönderim)
            commands_sent = 0
            send_start_time = time.time()
            
            if not self.main_window or not hasattr(self.main_window, 'coil_control_requested'):
                self.show_warning("MainWindow coil control signal not available!")
                return
            
            for coil_id, command, command_id in prepared_commands:
                # Send command via MainWindow signal (ensures only MainWindow writes to MQTT)
                self.main_window.coil_control_requested.emit(coil_id, command)
                commands_sent += 1
            
            send_duration_ms = (time.time() - send_start_time) * 1000
            
            if commands_sent > 0:
                # Hedef zamanı okunabilir formata çevir (saat:dakika:saniye.milisaniye)
                target_datetime = datetime.fromtimestamp(target_start_time / 1000.0)
                target_time_str = target_datetime.strftime("%H:%M:%S") + f".{target_start_time % 1000:03d}"
                self.logger.info(
                    f"{commands_sent} bağlı bobine senkron başlama komutu gönderildi (her bobin kendi değerleriyle). "
                    f"Hedef zaman: {target_time_str}, Buffer: {buffer_ms}ms, "
                    f"Gönderim süresi: {send_duration_ms:.1f}ms"
                )
                self.show_success(
                    f"{commands_sent} bağlı bobine başlama komutu gönderildi. "
                    f"Hedef zaman: {target_time_str}"
                )
            else:
                self.show_warning("Hiçbir bobine komut gönderilemedi!")
            
        except Exception as e:
            self.logger.error(f"Error in start_all_coils: {e}", exc_info=True)
            self.show_error(f"Bobinler başlatılamadı: {str(e)}")
        
    def stop_all_coils(self):
        """Tüm bağlı bobinleri durdur - sadece bağlı ESP'lere komut gönderir"""
        try:
            if not self.main_window or not hasattr(self.main_window, 'mqtt_client') or not self.main_window.mqtt_client:
                self.show_warning("MQTT bağlantısı bulunamadı!")
                return
            
            # MQTT bağlantısını kontrol et
            mqtt_connected = False
            if self.main_window.mqtt_client and self.main_window.mqtt_client.is_connected():
                mqtt_connected = True
            
            if not mqtt_connected:
                self.show_warning("MQTT bağlantısı yok! Bağlı bobinlere komut gönderilemiyor.")
                return
            
            # Bağlı ESP'leri kontrol et
            current_time = time.time()
            connected_coils = []
            
            for coil_id in range(1, 9):
                # MQTT bağlı, heartbeat kontrolü yap
                last_status_time = getattr(self, 'coil_last_status_time', {}).get(coil_id, 0)
                is_connected = False
                
                if last_status_time > 0:
                    # Heartbeat timeout kontrolü (ESP_TIMEOUT kullan, yoksa 5 saniye)
                    esp_timeout = getattr(self, 'ESP_TIMEOUT', 5.0)
                    is_connected = (current_time - last_status_time) <= esp_timeout
                else:
                    # Hiç status mesajı gelmemiş, bağlı değil sayılır
                    is_connected = False
                
                # coil_connection_status dictionary'sinden de kontrol et
                coil_connection_status = getattr(self, 'coil_connection_status', {})
                if coil_id in coil_connection_status:
                    is_connected = coil_connection_status[coil_id]
                
                if is_connected:
                    connected_coils.append(coil_id)
            
            if not connected_coils:
                self.show_warning("Bağlı Bobin bulunamadı! Hiçbir bobin durdurulamadı.")
                return
            
            # Sadece bağlı bobinlere komut gönder
            commands_sent = 0
            for coil_id in connected_coils:
                # Unique command ID oluştur (thread-safe)
                command_id = self._get_next_command_id(coil_id)
                
                command = {
                    "command": "stop",
                    "command_id": command_id,  # ESP ACK için gerekli
                    "timestamp": time.time()
                }
                
                # Pending commands'a ekle (thread-safe)
                with self.pending_commands_lock:
                    self.pending_commands[command_id] = {
                        'coil_num': coil_id,
                        'command': command,
                        'timestamp': time.time(),
                        'retry_count': 0
                    }
                
                # Send command via MainWindow signal (ensures only MainWindow writes to MQTT)
                if self.main_window and hasattr(self.main_window, 'coil_control_requested'):
                    self.main_window.coil_control_requested.emit(coil_id, command)
                    commands_sent += 1
                    self.logger.info(f"Stop command sent to connected coil {coil_id}")
                else:
                    self.show_warning("MainWindow coil control signal not available!")
                    return
                
                # UI güncelle - "Durduruluyor" durumu (ACK gelene kadar)
                controls = self.coil_controls[coil_id]
                controls['status_led'].setStyleSheet("color: #f59e0b; font-size: 12px;")
                controls['status_label'].setText("Durduruluyor...")
                controls['status_container'].setStyleSheet("""
                    background: rgba(245, 158, 11, 0.1);
                    border-radius: 12px;
                    border: 1px solid rgba(245, 158, 11, 0.3);
                """)
                controls['stop_btn'].setEnabled(False)
                # ACK geldiğinde _handle_command_ack tarafından güncellenecek
            
            if commands_sent > 0:
                self.show_info(f"{commands_sent} bağlı bobin durduruldu (Toplam {len(connected_coils)} bağlı bobin)")
            else:
                self.show_warning("Hiçbir bobin durdurulamadı!")
                
        except Exception as e:
            self.logger.error(f"Error in stop_all_coils: {e}", exc_info=True)
            self.show_error(f"Bobinler durdurulamadı: {str(e)}")

    def _connect_mqtt_signals(self):
        """MQTT sinyallerini bağla"""
        if self.main_window and hasattr(self.main_window, 'coil_status_updated'):
            self.main_window.coil_status_updated.connect(self.on_coil_status_updated)
        if self.main_window and hasattr(self.main_window, 'esp_status_received'):
            # ESP durum güncellemelerini de dinle (bağlantı durumunu güncellemek için)
            self.main_window.esp_status_received.connect(self.on_esp_status_received)
        if self.main_window and hasattr(self.main_window, 'sensor_data_updated'):
            self.main_window.sensor_data_updated.connect(self.on_sensor_data_updated)
        if self.main_window and hasattr(self.main_window, 'mqtt_connected'):
            self.main_window.mqtt_connected.connect(self.on_mqtt_connected)
        if self.main_window and hasattr(self.main_window, 'mqtt_disconnected'):
            self.main_window.mqtt_disconnected.connect(self.on_mqtt_disconnected)

    # --- GÜVENLİ SLOT FONKSİYONLARI (Ana Thread'de Çalışır) ---
    
    def _update_widget_property(self, widget, property_name, property_value):
        """
        Widget property'sini güncelle ve stil yenile (Performance Fix - CSS Parsing Optimization)
        setStyleSheet yerine setProperty kullanarak CSS parse overhead'ini azaltır
        """
        widget.setProperty(property_name, property_value)
        widget.style().unpolish(widget)
        widget.style().polish(widget)
    
    def _update_connection_status_label(self, coil_id, is_connected):
        """Bağlantı durumu label'ını güncelle ve bağlantı kesildiğinde sıcaklığı sıfırla"""
        if coil_id not in self.coil_controls:
            return
        
        controls = self.coil_controls[coil_id]
        if 'connection_status_label' not in controls:
            return
        
        label = controls['connection_status_label']
        if is_connected:
            label.setText("Bağlı")
            label.setStyleSheet("""
                font-size: 12px; 
                font-weight: 600; 
                color: #22c55e;
                padding: 4px 8px;
                background: rgba(34, 197, 94, 0.15);
                border-radius: 8px;
                border: 1px solid rgba(34, 197, 94, 0.3);
            """)
        else:
            label.setText("Bağlı Değil")
            label.setStyleSheet("""
                font-size: 12px; 
                font-weight: 600; 
                color: #ef4444;
                padding: 4px 8px;
                background: rgba(239, 68, 68, 0.15);
                border-radius: 8px;
                border: 1px solid rgba(239, 68, 68, 0.3);
            """)
            
            # Bağlantı kesildiğinde sıcaklık gösterimini 0°C olarak ayarla
            temp_label = controls.get('temp_label')
            if temp_label:
                temp_label.setProperty("temp_status", "normal")
                temp_label.setText("0.0°C")
                temp_label.style().unpolish(temp_label)
                temp_label.style().polish(temp_label)
            
            # Sensor cache'i temizle
            with self._sensor_value_lock:
                if coil_id in self._last_sensor_values:
                    self._last_sensor_values[coil_id].pop('temp', None)

    
    def _safe_on_coil_status_updated(self, coil_id, status_data):
        """
        Bu fonksiyon %100 ana thread'de çalışır (QueuedConnection sayesinde).
        MQTT thread'inden gelen veriler burada güvenli bir şekilde UI'ı günceller.
        """
        try:
            # coil_id string olarak gelebilir, int'e çevir
            coil_id_int = int(coil_id) if isinstance(coil_id, str) else coil_id
            
            if coil_id_int in self.coil_controls:
                controls = self.coil_controls[coil_id_int]
                
                # Bağlantı durumunu güncelle - Sadece MQTT bağlantısını kontrol et
                # MQTT bağlıysa ESP bağlı sayılır
                # Status mesajında mqtt_connected bilgisi varsa ve True ise güncelle
                if 'mqtt_connected' in status_data:
                    mqtt_connected = bool(status_data.get('mqtt_connected', False))
                    is_connected = mqtt_connected
                    
                    # Sadece durum değiştiyse güncelle (sürekli güncellemeyi önlemek için)
                    with self.coil_status_lock:
                        if self.coil_connection_status.get(coil_id_int, False) != is_connected:
                            self.coil_connection_status[coil_id_int] = is_connected
                            self._update_connection_status_label(coil_id_int, is_connected)
                
                # Son status mesajı zamanını güncelle (heartbeat için)
                # MQTT bağlıysa heartbeat zamanını güncelle
                if status_data.get('mqtt_connected', False):
                    with self.coil_status_lock:
                        self.coil_last_status_time[coil_id_int] = time.time()
                
                # Durum verilerini güncelle
                # Hem 'running' (status'tan) hem de 'pwm_active' (sensörden) kontrol et
                # ÖNEMLİ: pwm_active False olduğunda da güncelleme yapılmalı
                is_running = None
                if 'running' in status_data:
                    is_running = bool(status_data.get('running'))
                elif 'pwm_active' in status_data:
                    is_running = bool(status_data.get('pwm_active'))
                
                # PWM durumu bilgisi varsa (True veya False) güncelle
                if 'pwm_active' in status_data or 'running' in status_data:
                    if is_running is None:
                        # Eğer hiçbir değer bulunamadıysa, pwm_active'ı kontrol et
                        is_running = bool(status_data.get('pwm_active', False))
                    
                    with self.pwm_status_lock:
                        self.pwm_status[coil_id_int]['running'] = is_running
                    # Guard clause: Pahalı işlemler sadece DEBUG aktifse yapılır
                    if self.logger.isEnabledFor(logging.DEBUG):
                        self.logger.debug("Unified window: Coil %s PWM durumu güncellendi: running=%s", coil_id_int, is_running)

                    if is_running:
                        # Performance Fix: setProperty kullan (CSS parse overhead'i yok)
                        self._update_widget_property(controls['status_led'], "status_led", "running")
                        controls['status_label'].setText("Çalışıyor")
                        self._update_widget_property(controls['status_container'], "status_container", "running")
                        controls['start_btn'].setEnabled(False)
                        controls['stop_btn'].setEnabled(True)
                    else:
                        # Performance Fix: setProperty kullan (CSS parse overhead'i yok)
                        self._update_widget_property(controls['status_led'], "status_led", "stopped")
                        controls['status_label'].setText("Durduruldu")
                        self._update_widget_property(controls['status_container'], "status_container", "stopped")
                        controls['start_btn'].setEnabled(True)
                        controls['stop_btn'].setEnabled(False)
                        # Clear remaining time when stopped
                        self.pwm_remaining_time[coil_id_int] = None
                        self._update_coil_remaining_time_display(coil_id_int)
                        # Timer management removed - using unified_1hz_timer (Performance Optimization)
                
                # Parametreleri güncelle (hem pwm_status hem de spinbox'ları)
                if 'freq' in status_data:
                    freq_value = status_data['freq']
                    with self.pwm_status_lock:
                        self.pwm_status[coil_id_int]['freq'] = freq_value
                    # Spinbox'ı güncelle
                    try:
                        controls['freq_spin'].setValue(int(freq_value))
                    except (ValueError, TypeError) as e:
                        self.logger.warning(f"Bobin {coil_id_int} için geçersiz freq değeri: {freq_value}, hata: {e}")
                
                if 'duty' in status_data:
                    duty_value = status_data['duty']
                    with self.pwm_status_lock:
                        self.pwm_status[coil_id_int]['duty'] = duty_value
                    # Spinbox'ı güncelle
                    try:
                        controls['duty_spin'].setValue(float(duty_value))
                    except (ValueError, TypeError) as e:
                        self.logger.warning(f"Bobin {coil_id_int} için geçersiz duty değeri: {duty_value}, hata: {e}")
                
                if 'duration' in status_data:
                    duration_value = status_data['duration']
                    with self.pwm_status_lock:
                        self.pwm_status[coil_id_int]['duration'] = duration_value
                    # Spinbox'ı güncelle
                    try:
                        controls['duration_spin'].setValue(int(duration_value))
                    except (ValueError, TypeError) as e:
                        self.logger.warning(f"Bobin {coil_id_int} için geçersiz duration değeri: {duration_value}, hata: {e}")
                
                # Update remaining time from status data
                # IMPORTANT: If duration is 0 or null, clear remaining time (unlimited PWM)
                duration_value = status_data.get('pwm_duration') or status_data.get('duration')
                
                # DEBUG: Log status_data to check what's received
                self.logger.debug(f"Coil {coil_id_int} status_data keys: {list(status_data.keys())}")
                self.logger.debug(f"Coil {coil_id_int} duration_value={duration_value}, pwm_start_timestamp={status_data.get('pwm_start_timestamp')}")
                
                # Calculate remaining time from start_timestamp (Time-Based Synchronization)
                if 'pwm_start_timestamp' in status_data:
                    start_timestamp = status_data.get('pwm_start_timestamp')
                    pwm_active = status_data.get('pwm_active', False)
                    
                    # Thread-safe access to pwm_remaining_time (Critical Fix H2)
                    with self.pwm_remaining_time_lock:
                        # Clear remaining time if PWM not active, no duration, or duration is 0 (unlimited PWM)
                        if not pwm_active or duration_value is None or duration_value <= 0 or not start_timestamp:
                            self.pwm_remaining_time[coil_id_int] = None
                        else:
                            # Calculate remaining time locally from start_timestamp
                            try:
                                start_timestamp_ms = int(start_timestamp)
                                duration_ms = duration_value * 60 * 1000  # Convert minutes to milliseconds
                                end_timestamp_ms = start_timestamp_ms + duration_ms
                                current_time_ms = int(time.time() * 1000)  # Current time in milliseconds
                                remaining_ms = end_timestamp_ms - current_time_ms
                                
                                # CRITICAL FIX BUG #6: Clock adjustment detection
                                # If start_timestamp is in the future (scheduled start), remaining_ms > duration_ms
                                # is expected (remaining = duration + time_until_start). Only warn when
                                # start_timestamp is in the past and remaining_ms > duration_ms.
                                if remaining_ms < 0:
                                    # Already expired
                                    self.logger.warning(f"Clock adjustment / expired session for coil {coil_id_int}: remaining_ms={remaining_ms}")
                                    self.pwm_remaining_time[coil_id_int] = None
                                elif remaining_ms > duration_ms:
                                    if start_timestamp_ms > current_time_ms:
                                        # Scheduled to start in the future: compute remaining and do not warn
                                        remaining_seconds = remaining_ms // 1000
                                        if remaining_seconds > 0:
                                            self.pwm_remaining_time[coil_id_int] = remaining_seconds
                                        else:
                                            self.pwm_remaining_time[coil_id_int] = None
                                    else:
                                        # Unexpectedly larger than duration (clock issues)
                                        self.logger.warning(f"Clock adjustment detected for coil {coil_id_int}: remaining_ms={remaining_ms}, duration_ms={duration_ms}")
                                        self.pwm_remaining_time[coil_id_int] = None
                                else:
                                    remaining_seconds = remaining_ms // 1000  # Convert to seconds
                                    if remaining_seconds > 0:
                                        self.pwm_remaining_time[coil_id_int] = remaining_seconds
                                    else:
                                        # Session expired
                                        self.pwm_remaining_time[coil_id_int] = None
                            except (ValueError, TypeError) as e:
                                self.logger.warning(f"Error calculating remaining time for coil {coil_id_int}: {e}")
                                self.pwm_remaining_time[coil_id_int] = None
                elif duration_value is None or duration_value <= 0:
                    # Clear remaining time if duration is 0 or null
                    with self.pwm_remaining_time_lock:
                        self.pwm_remaining_time[coil_id_int] = None
                
                # Update remaining time display
                self._update_coil_remaining_time_display(coil_id_int)
                
                # Start/stop countdown timer based on active PWM count
                # Timer management removed - using unified_1hz_timer (Performance Optimization)
                    
        except Exception as e:
            self.logger.error(f"_safe_on_coil_status_updated HATA: {e}", exc_info=True)
    
    def _safe_handle_command_ack(self, coil_num, command_id, success, cmd_info):
        """
        Bu fonksiyon %100 ana thread'de çalışır (QueuedConnection sayesinde).
        ESP8266'dan gelen command acknowledgment'ı burada güvenli bir şekilde işler.
        cmd_info: Komut bilgisi (sinyal parametresi olarak geçirilir)
        """
        try:
            if success and cmd_info:
                # Komut başarılı
                if coil_num in self.coil_controls:
                    controls = self.coil_controls[coil_num]
                    
                    command_type = cmd_info['command']['command']
                    
                    if command_type == "start":
                        # PWM başlatıldı
                        freq_value = cmd_info['command'].get('freq', 0)
                        duty_value = cmd_info['command'].get('duty', 0.0)
                        duration_value = cmd_info['command'].get('duration', 0)
                        
                        with self.pwm_status_lock:
                            self.pwm_status[coil_num]['running'] = True
                            self.pwm_status[coil_num]['freq'] = freq_value
                            self.pwm_status[coil_num]['duty'] = duty_value
                            self.pwm_status[coil_num]['duration'] = duration_value
                        
                        # Spinbox'ları güncelle (Android app'ten gelen komutlar için)
                        try:
                            controls['freq_spin'].setValue(int(freq_value))
                        except (ValueError, TypeError) as e:
                            self.logger.warning(f"Bobin {coil_num} için geçersiz freq değeri: {freq_value}, hata: {e}")
                        
                        try:
                            controls['duty_spin'].setValue(float(duty_value))
                        except (ValueError, TypeError) as e:
                            self.logger.warning(f"Bobin {coil_num} için geçersiz duty değeri: {duty_value}, hata: {e}")
                        
                        try:
                            controls['duration_spin'].setValue(int(duration_value))
                        except (ValueError, TypeError) as e:
                            self.logger.warning(f"Bobin {coil_num} için geçersiz duration değeri: {duration_value}, hata: {e}")
                        
                        controls['status_led'].setStyleSheet("color: #22c55e; font-size: 12px;")
                        controls['status_label'].setText("Çalışıyor")
                        controls['status_container'].setStyleSheet("""
                            background: rgba(34, 197, 94, 0.1);
                            border-radius: 12px;
                            border: 1px solid rgba(34, 197, 94, 0.3);
                        """)
                        controls['start_btn'].setEnabled(False)
                        controls['stop_btn'].setEnabled(True)
                        
                        # Update remaining time if available in command
                        if 'duration' in cmd_info['command']:
                            duration = cmd_info['command']['duration']
                            if duration is not None and duration > 0:
                                # Calculate remaining time from duration (in minutes)
                                remaining_seconds = duration * 60
                                self.pwm_remaining_time[coil_num] = remaining_seconds
                            else:
                                # Duration is 0 or null (unlimited PWM), clear remaining time
                                self.pwm_remaining_time[coil_num] = None
                        
                        # Update display and manage timer
                        self._update_coil_remaining_time_display(coil_num)
                        # Timer management removed - using unified_1hz_timer (Performance Optimization)
                        
                    elif command_type == "stop":
                        # PWM durduruldu
                        with self.pwm_status_lock:
                            self.pwm_status[coil_num]['running'] = False
                        
                        controls['status_led'].setStyleSheet("color: #ef4444; font-size: 12px;")
                        controls['status_label'].setText("Durduruldu")
                        controls['status_container'].setStyleSheet("""
                            background: rgba(239, 68, 68, 0.1);
                            border-radius: 12px;
                            border: 1px solid rgba(239, 68, 68, 0.3);
                        """)
                        controls['start_btn'].setEnabled(True)
                        controls['stop_btn'].setEnabled(False)
                
                self.logger.info(f"Command ACK received: {command_id} - SUCCESS")
            else:
                # Komut başarısız
                if coil_num in self.coil_controls:
                    controls = self.coil_controls[coil_num]
                    controls['status_led'].setStyleSheet("color: #ef4444; font-size: 12px;")
                    controls['status_label'].setText("Hata")
                    controls['status_container'].setStyleSheet("""
                        background: rgba(239, 68, 68, 0.1);
                        border-radius: 12px;
                        border: 1px solid rgba(239, 68, 68, 0.3);
                    """)
                    controls['start_btn'].setEnabled(True)
                    controls['stop_btn'].setEnabled(False)
                
                self.show_error(f"Bobin {coil_num} komutu ESP tarafından reddedildi")
                self.logger.error(f"Command ACK received: {command_id} - FAILED")
                
        except Exception as e:
            self.logger.error(f"_safe_handle_command_ack HATA: {e}", exc_info=True)
    
    def _safe_show_toast_callback(self, message, toast_type):
        """
        _show_toast'un güvenli çağrıcısı.
        Bu fonksiyon %100 ana thread'de çalışır (QueuedConnection sayesinde).
        """
        try:
            # _show_toast bir QWidget yarattığı için ana thread'de olmalı
            self._show_toast(message, toast_type)
        except Exception as e:
            self.logger.error(f"_safe_show_toast_callback HATA: {e}", exc_info=True)
    
    def _safe_update_sensor_warning(self, coil_id, message, warning_type):
        """
        Sensör uyarılarını güvenli bir şekilde göster.
        Bu fonksiyon %100 ana thread'de çalışır (QueuedConnection sayesinde).
        """
        try:
            if warning_type == "warning":
                self.show_warning(message)
            elif warning_type == "error":
                self.show_error(message)
            else:
                self.show_info(message)
        except Exception as e:
            self.logger.error(f"_safe_update_sensor_warning HATA: {e}", exc_info=True)
    
    # --- GÜVENLİ SLOT FONKSİYONLARI SONU ---

    def on_coil_status_updated(self, coil_id, status_data):
        """
        MQTT thread'inden çağrılır. ASLA UI güncellemesi yapmayın.
        Sadece veriyi ana thread'e yolla.
        FIXED: Dictionary check moved inside lock to prevent race condition.
        """
        try:
            # coil_id string olarak gelebilir, int'e çevir
            coil_id_int = int(coil_id) if isinstance(coil_id, str) else coil_id
            
            # FIXED: Thread-safe veri güncellemesi - lock içinde kontrol et
            with self.pwm_status_lock:
                if coil_id_int in self.pwm_status:
                    if 'running' in status_data:
                        self.pwm_status[coil_id_int]['running'] = status_data['running']
                    elif 'pwm_active' in status_data:
                        # pwm_active de running olarak kaydedilebilir
                        self.pwm_status[coil_id_int]['running'] = status_data['pwm_active']
            
            # Güvenli sinyali emit et (UI güncellemesi ana thread'de yapılacak)
            # coil_id'yi string olarak gönder (int'e çevirme işlemi _safe_on_coil_status_updated'da yapılacak)
            self._safe_update_status_signal.emit(str(coil_id_int), status_data)
                    
        except Exception as e:
            self.logger.error(f"on_coil_status_updated hatası: {e}", exc_info=True)
            # Notify user on critical errors
            self._safe_show_toast_signal.emit(f"⚠️ Coil status hatası: {str(e)[:50]}", "error")

    def on_sensor_data_updated(self, coil_id, sensor_data):
        """
        MQTT thread'inden çağrılır. UI güncellemelerini sınırlar (Throttling).
        Sensor data gösterimi MainWindow ve SensorDataWindow'da yapılıyor.
        WebSocket server'a iletme MainWindow tarafından yapılıyor.
        
        PWM durumu sensor mesajından da gelebilir, bu durumda UI'ı güncelle.
        """
        try:
            # coil_id'yi int'e çevir
            coil_id_int = int(coil_id) if isinstance(coil_id, str) else coil_id
            current_time = time.time()
            
            # Throttling: Her bobin için max 5 FPS (200ms)
            # Kritik uyarılar (sıcaklık/akım) her zaman geçer
            is_critical = False
            if 'temperature' in sensor_data and sensor_data['temperature'] and sensor_data['temperature'] > self.CRITICAL_TEMP_THRESHOLD:
                is_critical = True
            if 'current' in sensor_data and sensor_data['current'] and sensor_data['current'] > self.CRITICAL_CURRENT_THRESHOLD:
                is_critical = True
            
            # Thread-safe access to last_ui_update_time (Critical Fix H1)
            with self.ui_update_lock:
                last_update = self.last_ui_update_time.get(coil_id_int, 0)
                
                if not is_critical and (current_time - last_update) < 0.2:  # 200ms limit
                    return
                
                self.last_ui_update_time[coil_id_int] = current_time
            
            # PWM durumu sensor mesajından gelebilir - UI'ı güncelle
            if 'pwm_active' in sensor_data or 'pwm_frequency' in sensor_data or 'pwm_duty_cycle' in sensor_data or 'pwm_duty' in sensor_data:
                # PWM bilgisini status_data formatına çevir
                status_data = {}
                # pwm_active her zaman eklenmeli (True veya False)
                if 'pwm_active' in sensor_data:
                    status_data['pwm_active'] = bool(sensor_data['pwm_active'])
                if 'pwm_frequency' in sensor_data:
                    status_data['pwm_frequency'] = sensor_data['pwm_frequency']
                    status_data['freq'] = sensor_data['pwm_frequency']  # Unified format
                # ESP'den pwm_duty_cycle olarak gelebilir
                pwm_duty = sensor_data.get('pwm_duty_cycle') or sensor_data.get('pwm_duty', 0)
                if pwm_duty or 'pwm_duty_cycle' in sensor_data or 'pwm_duty' in sensor_data:
                    status_data['pwm_duty'] = pwm_duty
                    status_data['duty'] = pwm_duty  # Unified format
                
                # PWM duration and remaining time from sensor data
                if 'pwm_duration' in sensor_data:
                    status_data['pwm_duration'] = sensor_data['pwm_duration']
                    status_data['duration'] = sensor_data['pwm_duration']  # Unified format
                # Handle start_timestamp from sensor data (Time-Based Synchronization)
                if 'pwm_start_timestamp' in sensor_data:
                    status_data['pwm_start_timestamp'] = sensor_data.get('pwm_start_timestamp')
                # Legacy support: if pwm_remaining_time is present, convert to start_timestamp calculation
                elif 'pwm_remaining_time' in sensor_data:
                    # This is legacy data, but we'll handle it for backward compatibility
                    # Calculate start_timestamp from remaining_time if possible
                    remaining_time = sensor_data.get('pwm_remaining_time')
                    duration_value = status_data.get('pwm_duration') or status_data.get('duration')
                    if remaining_time is not None and duration_value and duration_value > 0:
                        # Estimate start_timestamp: current_time - (duration - remaining_time)
                        try:
                            remaining_time_int = int(remaining_time)
                            if remaining_time_int > 3600:
                                remaining_time_int = remaining_time_int // 1000  # Convert ms to seconds
                            duration_seconds = duration_value * 60
                            elapsed_seconds = duration_seconds - remaining_time_int
                            estimated_start_timestamp = int(time.time() * 1000) - (elapsed_seconds * 1000)
                            status_data['pwm_start_timestamp'] = estimated_start_timestamp
                        except (ValueError, TypeError):
                            pass
                
                # Guard clause: Pahalı işlemler sadece DEBUG aktifse yapılır
                if self.logger.isEnabledFor(logging.DEBUG):
                    self.logger.debug("Unified window: Sensor PWM durumu - coil_id=%s, active=%s, dur=%s, rem=%s",
                                      coil_id,
                                      status_data.get('pwm_active'),
                                      status_data.get('pwm_duration'),
                                      status_data.get('pwm_remaining_time'))
                
                # Güvenli sinyali emit et (UI güncellemesi ana thread'de yapılacak)
                # coil_id'yi string olarak gönder
                self._safe_update_status_signal.emit(str(coil_id), status_data)
            
            # KRİTİK UYARILAR - Sadece yüksek sıcaklık ve akım kontrolü
            # ESP'den gelen nesne sıcaklığı (object_temp) kullanılır - tıpkı izleme ekranındaki gibi
            if 'object_temp' in sensor_data or 'temperature' in sensor_data:
                # Öncelik: object_temp (nesne sıcaklığı), fallback: temperature
                temp = sensor_data.get('object_temp') or sensor_data.get('temperature')
                # None kontrolü ve tip kontrolü (TypeError önleme)
                if temp is not None and isinstance(temp, (int, float)):
                    # PERFORMANCE FIX: Value change detection - only update if changed
                    with self._sensor_value_lock:
                        last_temp = self._last_sensor_values.get(coil_id_int, {}).get('temp')
                        temp_changed = (last_temp is None or abs(temp - last_temp) > 0.5)  # 0.5°C threshold
                        
                        if temp_changed:
                            # Update cache
                            if coil_id_int not in self._last_sensor_values:
                                self._last_sensor_values[coil_id_int] = {}
                            self._last_sensor_values[coil_id_int]['temp'] = temp
                    
                    # Only update UI if value changed significantly
                    if temp_changed and coil_id_int in self.coil_controls:
                        temp_label = self.coil_controls[coil_id_int].get('temp_label')
                        if temp_label:
                            # OPTIMIZED: Use setProperty instead of setStyleSheet (Performance Fix)
                            if temp > 60:
                                temp_label.setProperty("temp_status", "critical")
                                temp_label.setText(f"🔥 {temp:.1f}°C")
                            elif temp > 45:
                                temp_label.setProperty("temp_status", "warning")
                                temp_label.setText(f"⚠️ {temp:.1f}°C")
                            else:
                                temp_label.setProperty("temp_status", "normal")
                                temp_label.setText(f"{temp:.1f}°C")
                            # Refresh style
                            temp_label.style().unpolish(temp_label)
                            temp_label.style().polish(temp_label)
                    
                    # Yüksek sıcaklık uyarısı
                    if temp > 60:
                        # Anında uyarı gönder
                        self._safe_update_sensor_warning_signal.emit(
                            coil_id_int, 
                            f"Bobin {coil_id_int} yüksek sıcaklık: {temp:.1f}°C", 
                            "warning"
                        )
                        
            if 'current' in sensor_data:
                current = sensor_data.get('current', 0)
                # None kontrolü ve tip kontrolü (TypeError önleme)
                if current is not None and isinstance(current, (int, float)) and current > 5:  # Yüksek akım uyarısı
                    # Anında uyarı gönder
                    self._safe_update_sensor_warning_signal.emit(
                        coil_id_int, 
                        f"Bobin {coil_id_int} yüksek akım: {current:.2f}A", 
                        "warning"
                    )
                        
        except Exception as e:
            self.logger.error(f"on_sensor_data_updated hatası: {e}", exc_info=True)
            # FIXED: Notify user on sensor data errors
            self._safe_show_toast_signal.emit(f"⚠️ Sensor veri hatası (Bobin {coil_id}): {str(e)[:40]}", "error")

    def on_esp_status_received(self, coil_id, status_data):
        """
        ESP durum güncellemesi alındığında çağrılır.
        Bağlantı durumunu güncellemek için kullanılır.
        """
        try:
            # coil_id string olarak gelebilir, int'e çevir
            coil_id_int = int(coil_id) if isinstance(coil_id, str) else coil_id
            
            if coil_id_int in range(1, 9) and coil_id_int in self.coil_controls:
                controls = self.coil_controls[coil_id_int]
                
                # Sadece MQTT bağlantısını kontrol et
                # MQTT bağlıysa ESP bağlı sayılır
                # Status mesajında mqtt_connected bilgisi varsa ve True ise güncelle
                if 'mqtt_connected' in status_data:
                    mqtt_connected = bool(status_data.get('mqtt_connected', False))
                    is_connected = mqtt_connected
                    
                    # Sadece durum değiştiyse güncelle (sürekli güncellemeyi önlemek için)
                    with self.coil_status_lock:
                        if self.coil_connection_status.get(coil_id_int, False) != is_connected:
                            self.coil_connection_status[coil_id_int] = is_connected
                            self._update_connection_status_label(coil_id_int, is_connected)
                
                # Son status mesajı zamanını güncelle (heartbeat için)
                # MQTT bağlıysa heartbeat zamanını güncelle
                if status_data.get('mqtt_connected', False):
                    with self.coil_status_lock:
                        self.coil_last_status_time[coil_id_int] = time.time()
                    
        except Exception as e:
            self.logger.warning(f"on_esp_status_received hatası: {e}", exc_info=True)

    def on_mqtt_connected(self):
        """MQTT bağlandığında"""
        self.show_info("MQTT bağlantısı kuruldu")
        # MQTT bağlandığında bağlantı durumunu güncelleme
        # Status mesajları geldiğinde otomatik olarak güncellenecek
        
    def on_mqtt_disconnected(self):
        """MQTT bağlantısı kesildiğinde"""
        self.show_warning("MQTT bağlantısı kesildi")
        # Tüm bobinlerin bağlantı durumunu "Bağlı Değil" olarak güncelle
        for coil_id in range(1, 9):
            # Sadece durum değiştiyse güncelle (sürekli güncellemeyi önlemek için)
            with self.coil_status_lock:
                if self.coil_connection_status.get(coil_id, False):
                    self.coil_connection_status[coil_id] = False
                    self._update_connection_status_label(coil_id, False)
        
    def show_info(self, message):
        """Bilgi mesajı göster - Modern toast notification"""
        self.status_bar.showMessage(f"INFO: {message}", 3000)
        self._show_toast(message, "info")
        
    def show_warning(self, message):
        """Uyarı mesajı göster - Modern toast notification"""
        self.status_bar.showMessage(f"WARNING: {message}", 5000)
        self._show_toast(message, "warning")
        
    def show_error(self, message):
        """Hata mesajı göster - Modern toast notification"""
        self.status_bar.showMessage(f"❌ {message}", 5000)
        self._show_toast(message, "error")
        
    def show_success(self, message):
        """Başarı mesajı göster - Modern toast notification"""
        self.status_bar.showMessage(f"✅ {message}", 3000)
        self._show_toast(message, "success")
        
    def _show_toast(self, message, toast_type="info"):
        """Modern toast notification göster"""
        try:
            # Toast container oluştur
            toast = QWidget(self)
            toast.setFixedSize(350, 80)
            toast.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
            
            # Toast layout
            layout = QHBoxLayout(toast)
            layout.setContentsMargins(16, 12, 16, 12)
            layout.setSpacing(12)
            
            # Icon
            icon_label = QLabel()
            icon_label.setFixedSize(24, 24)
            icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            
            # Message
            message_label = QLabel(message)
            message_label.setWordWrap(True)
            message_label.setStyleSheet("font-size: 14px; font-weight: 600;")
            
            # Close button
            close_btn = QPushButton("×")
            close_btn.setFixedSize(24, 24)
            close_btn.setStyleSheet("""
                QPushButton {
                    background: transparent;
                    border: none;
                    font-size: 18px;
                    font-weight: bold;
                    color: rgba(255, 255, 255, 0.7);
                }
                QPushButton:hover {
                    color: rgba(255, 255, 255, 1);
                    background: rgba(255, 255, 255, 0.1);
                    border-radius: 12px;
                }
            """)
            close_btn.clicked.connect(toast.close)
            
            layout.addWidget(icon_label)
            layout.addWidget(message_label, 1)
            layout.addWidget(close_btn)
            
            # Toast type'a göre stil
            if toast_type == "success":
                icon_label.setText("✅")
                toast.setStyleSheet("""
                    QWidget {
                        background: rgba(34, 197, 94, 0.9);
                        border-radius: 12px;
                        border: 1px solid rgba(34, 197, 94, 1);
                    }
                    QLabel { color: white; }
                """)
            elif toast_type == "warning":
                icon_label.setText("!")
                toast.setStyleSheet("""
                    QWidget {
                        background: rgba(251, 191, 36, 0.9);
                        border-radius: 12px;
                        border: 1px solid rgba(251, 191, 36, 1);
                    }
                    QLabel { color: white; }
                """)
            elif toast_type == "error":
                icon_label.setText("X")
                toast.setStyleSheet("""
                    QWidget {
                        background: rgba(239, 68, 68, 0.9);
                        border-radius: 12px;
                        border: 1px solid rgba(239, 68, 68, 1);
                    }
                    QLabel { color: white; }
                """)
            else:  # info
                icon_label.setText("i")
                toast.setStyleSheet("""
                    QWidget {
                        background: rgba(59, 130, 246, 0.9);
                        border-radius: 12px;
                        border: 1px solid rgba(59, 130, 246, 1);
                    }
                    QLabel { color: white; }
                """)
            
            # Position toast
            parent_rect = self.rect()
            toast_x = parent_rect.width() - toast.width() - 20
            toast_y = 80
            toast.move(toast_x, toast_y)
            
            # Show toast
            toast.show()
            toast.raise_()
            
            # Auto close after 4 seconds
            QTimer.singleShot(4000, toast.close)
            
        except Exception as e:
            self.logger.warning(f"Toast notification hatası: {e}", exc_info=True)

    def update_status(self):
        """
        Durum bilgilerini güncelle - Debounce ile gereksiz UI güncellemelerini önle
        Sadece durum değiştiğinde status_bar'ı günceller
        """
        if self.main_window and hasattr(self.main_window, 'mqtt_client'):
            if self.main_window.mqtt_client and self.main_window.mqtt_client.is_connected():
                mqtt_status = "🟢 Bağlı"
            else:
                mqtt_status = "🔴 Bağlantısız"
        else:
            mqtt_status = "🔴 Bulunamadı"
            
        # Aktif bobin sayısını hesapla (thread-safe okuma)
        with self.pwm_status_lock:
            active_coils = sum(1 for status in self.pwm_status.values() if status.get('running', False))
        
        status_text = f"Bağlantı: {mqtt_status} | Aktif Bobinler: {active_coils}/8"
        
        if self.treatment_active:
            # Treatment countdown _update_treatment_countdown() tarafından güncelleniyor
            # Burada sadece status text'e ekle
            if hasattr(self, 'treatment_start_time') and hasattr(self, 'treatment_duration'):
                if self.treatment_duration > 0:
                    elapsed = time.time() - self.treatment_start_time
                    remaining = max(0, self.treatment_duration - elapsed)
                    minutes = int(remaining // 60)
                    seconds = int(remaining % 60)
                    time_str = f"{minutes:02d}:{seconds:02d}"
                    status_text += f" | 🔄 Seans: {time_str}"
                else:
                    status_text += " | 🔄 Seans Aktif (Süresiz)"
            else:
                status_text += " | 🔄 Seans Aktif"
        
        # Debounce: Sadece durum değiştiğinde UI'ı güncelle
        if status_text != getattr(self, '_last_status_text', None):
            self._last_status_text = status_text
            # status_bar henüz oluşturulmamış olabilir (init sırasında)
            if hasattr(self, 'status_bar') and self.status_bar:
                self.status_bar.showMessage(status_text)
    
    def _on_unified_1hz_tick(self):
        """
        Unified 1Hz timer callback (Timer Optimization - Enhanced).
        Combines status update, command timeout check, treatment countdown, and PWM countdown.
        Reduces timer overhead by ~75% compared to separate timers (4 timers -> 2 timers).
        """
        try:
            # 1. Update status bar
            self.update_status()
            
            # 2. Check command timeouts
            self._check_command_timeouts()
            
            # 3. Update treatment countdown (if active)
            if self.treatment_active:
                self._update_treatment_countdown()
            
            # 4. Update PWM countdowns (Performance Fix - Merged from separate timer)
            self._update_pwm_countdowns()
                
        except Exception as e:
            self.logger.error(f"Unified 1Hz tick error: {e}", exc_info=True)

    def _load_patient_list(self):
        """Hasta listesini veritabanından arka planda yükle ve combo box'a ekle (Performance Fix - QThread with cleanup)"""
        try:
            if not hasattr(self, 'app_data_dir'):
                return
            
            # Eğer önceki thread hala çalışıyorsa, durdur
            # Güvenli thread kontrolü - wrapped C++ object hatası önlenir
            if hasattr(self, '_patient_list_thread') and self._patient_list_thread is not None:
                # Thread'i local değişkene al (race condition önleme)
                thread = self._patient_list_thread
                self._patient_list_thread = None  # Önce None yap, sonra cleanup
                
                try:
                    if thread.isRunning():
                        thread.terminate()
                        thread.wait()
                except (RuntimeError, AttributeError) as e:
                    # Thread already deleted (deleteLater called) or attribute error
                    self.logger.debug(f"Thread cleanup error (expected): {e}")
            
            # Yeni thread oluştur ve başlat
            self._patient_list_thread = PatientListLoadThread(self.app_data_dir)
            self._patient_list_thread.patients_loaded.connect(self._on_patients_loaded)
            self._patient_list_thread.error_occurred.connect(self._on_patient_load_error)
            # FIXED: Add thread cleanup to prevent memory leak
            self._patient_list_thread.finished.connect(self._patient_list_thread.deleteLater)
            self._patient_list_thread.finished.connect(lambda: setattr(self, '_patient_list_thread', None))
            self._patient_list_thread.start()
            
            self.logger.debug("Hasta listesi arka planda yüklenmeye başladı...")
        except Exception as e:
            self.logger.error(f"Hasta listesi yüklenirken hata: {e}", exc_info=True)
    
    def _on_patients_loaded(self, patients_sorted):
        """Hasta listesi yüklendiğinde çağrılır (GUI thread'de çalışır)"""
        try:
            # Otomatik Mod combo box'ı temizle ve doldur
            if hasattr(self, 'patient_combo'):
                self.patient_combo.clear()
                self.patient_combo.addItem("Hasta Seçin...", None)
                
                # Hastaları ekle (yeniden eskiye doğru)
                for patient in patients_sorted:
                    name = patient.get('name', 'İsimsiz')
                    species = patient.get('species', '')
                    display_text = f"{name} ({species})" if species else name
                    self.patient_combo.addItem(display_text, patient)
                
                # Silme butonlarını güncelle
                if hasattr(self, 'delete_selected_patient_btn'):
                    self.delete_selected_patient_btn.setEnabled(len(patients_sorted) > 0)
                if hasattr(self, 'delete_all_patients_btn'):
                    self.delete_all_patients_btn.setEnabled(len(patients_sorted) > 0)
            
            # AI Mod combo box'ı da doldur
            if hasattr(self, 'ai_patient_combo'):
                self.ai_patient_combo.clear()
                self.ai_patient_combo.addItem("Hasta seçiniz...", None)
                
                # Hastaları ekle (aynı sırayla)
                for patient in patients_sorted:
                    name = patient.get('name', 'İsimsiz')
                    species = patient.get('species', '')
                    display_text = f"{name} ({species})" if species else name
                    self.ai_patient_combo.addItem(display_text, patient)
                
                # Enable AI calculate button if patient already selected (lazy loading fix)
                if self.selected_patient and hasattr(self, 'ai_calculate_btn'):
                    self.ai_calculate_btn.setEnabled(True)
                
        except Exception as e:
            self.logger.error(f"_on_patients_loaded hatası: {e}", exc_info=True)
    
    def _on_patient_load_error(self, error_msg):
        """Hasta listesi yüklenirken hata oluştuğunda çağrılır"""
        self.logger.error(f"Hasta listesi yüklenirken hata: {error_msg}", exc_info=True)
    
    def _on_patient_selected(self, index):
        """Hasta seçildiğinde çağrılır"""
        try:
            if index > 0 and hasattr(self, 'patient_combo'):
                patient_data = self.patient_combo.itemData(index)
                if patient_data:
                    self.selected_patient = {
                        'id': patient_data.get('id'),
                        'info': {
                            'name': patient_data.get('name', ''),
                            'species': patient_data.get('species', ''),
                            'breed': patient_data.get('breed', ''),
                            'age': patient_data.get('age', ''),
                            'weight': patient_data.get('weight', ''),
                            'owner': patient_data.get('owner', ''),
                            'vet_contact': patient_data.get('vet_contact', '')
                        }
                    }
                    # Main window'a hasta bilgisini kaydet
                    if self.main_window:
                        self.main_window.last_saved_patient = self.selected_patient
                    
                    # Sağ üstteki hasta bilgisini güncelle
                    self._update_header_patient_info()
                    
                    # AI tab'ındaki hasta combo'sunu da senkronize et
                    if hasattr(self, 'ai_patient_combo'):
                        # Aynı hastayı AI combo'sunda bul ve seç
                        for i in range(self.ai_patient_combo.count()):
                            ai_patient = self.ai_patient_combo.itemData(i)
                            if ai_patient and ai_patient.get('id') == patient_data.get('id'):
                                # currentIndexChanged sinyalini geçici olarak blokla
                                self.ai_patient_combo.blockSignals(True)
                                self.ai_patient_combo.setCurrentIndex(i)
                                self.ai_patient_combo.blockSignals(False)
                                # AI patient info label'ı güncelle
                                name = patient_data.get('name', 'İsimsiz')
                                species = patient_data.get('species', 'Bilinmiyor')
                                age = patient_data.get('age', '?')
                                weight = patient_data.get('weight', '?')
                                info_text = f"🐾 {name} | Tür: {species} | Yaş: {age} | Kilo: {weight} kg"
                                self.ai_patient_info_label.setText(info_text)
                                break
                    
                    # Silme butonunu etkinleştir
                    if hasattr(self, 'delete_selected_patient_btn'):
                        self.delete_selected_patient_btn.setEnabled(True)
                    
                    # AI parametre hesapla butonunu etkinleştir
                    if hasattr(self, 'ai_calculate_btn'):
                        self.ai_calculate_btn.setEnabled(True)
                    
                    self.logger.info(f"Hasta seçildi: {self.selected_patient['info'].get('name')}")
                else:
                    self.selected_patient = None
                    self._update_header_patient_info()
                    if hasattr(self, 'delete_selected_patient_btn'):
                        self.delete_selected_patient_btn.setEnabled(False)
                    if hasattr(self, 'ai_calculate_btn'):
                        self.ai_calculate_btn.setEnabled(False)
            else:
                self.selected_patient = None
                self._update_header_patient_info()
                if hasattr(self, 'delete_selected_patient_btn'):
                    self.delete_selected_patient_btn.setEnabled(False)
                if hasattr(self, 'ai_calculate_btn'):
                    self.ai_calculate_btn.setEnabled(False)
        except Exception as e:
            self.logger.error(f"Hasta seçimi hatası: {e}", exc_info=True)
            self.selected_patient = None
            self._update_header_patient_info()
            if hasattr(self, 'ai_calculate_btn'):
                self.ai_calculate_btn.setEnabled(False)
    
    def _update_header_patient_info(self):
        """Sağ üstteki hasta bilgisini güncelle (seçili hastaya göre)"""
        try:
            if hasattr(self, 'patient_info_label') and hasattr(self, 'patient_status_label'):
                if self.selected_patient and 'info' in self.selected_patient:
                    info = self.selected_patient['info']
                    patient_name = str(info.get('name', '')).strip() or 'Belirtilmemiş'
                    patient_species = str(info.get('species', '')).strip() or 'Belirtilmemiş'
                    patient_text = f"{patient_name} ({patient_species})"
                    self.patient_info_label.setText(patient_text)
                    self.patient_status_label.setText("Hasta seçildi")
                    self.patient_info_widget.setStyleSheet("""
                        background: rgba(34, 197, 94, 0.1);
                        border-radius: 12px;
                        border: 1px solid rgba(34, 197, 94, 0.3);
                    """)
                else:
                    self.patient_info_label.setText("Hasta Bilgisi")
                    self.patient_status_label.setText("Hasta seçilmedi")
                    self.patient_info_widget.setStyleSheet("""
                        background: rgba(255, 255, 255, 0.05);
                        border-radius: 12px;
                        border: 1px solid rgba(255, 255, 255, 0.1);
                    """)
        except Exception as e:
            self.logger.error(f"Hasta bilgisi güncellenirken hata: {e}", exc_info=True)
    
    def update_patient_info(self):
        """Hasta bilgilerini güncelle (hem header hem de hasta listesi)"""
        # Header'daki hasta bilgisini güncelle
        self._update_header_patient_info()
        # Hasta listesini yenile
        self._load_patient_list()
    
    def show_parameter_table(self):
        """PEMF parametre tablosunu varsayılan tarayıcıda aç"""
        try:
            # HTML dosyasının yolunu bul (docs klasöründe)
            html_file_path = os.path.join(parent_dir, "docs", "pemf_optimized_table.html")
            
            if not os.path.exists(html_file_path):
                QMessageBox.warning(
                    self,
                    "Dosya Bulunamadı",
                    f"Parametre tablosu dosyası bulunamadı:\n{html_file_path}",
                    QMessageBox.StandardButton.Ok
                )
                return
            
            # HTML dosyasını varsayılan tarayıcıda aç
            file_url = QUrl.fromLocalFile(os.path.abspath(html_file_path))
            QDesktopServices.openUrl(file_url)
            
        except Exception as e:
            self.logger.error(f"Parametre tablosu açılırken hata: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "Hata",
                f"Parametre tablosu açılırken bir hata oluştu:\n{str(e)}",
                QMessageBox.StandardButton.Ok
            )
    
    def _delete_selected_patient(self):
        """Seçili hastayı sil - arka plan thread'de"""
        try:
            # Eğer zaten bir silme işlemi çalışıyorsa, yeni başlatma
            if hasattr(self, '_delete_thread') and self._delete_thread is not None:
                if self._delete_thread.isRunning():
                    self.show_warning("Silme işlemi zaten devam ediyor, lütfen bekleyin.")
                    return
            
            if not self.selected_patient or not self.selected_patient.get('id'):
                self.show_warning("Lütfen silmek için bir hasta seçin.")
                return
            
            patient_name = self.selected_patient['info'].get('name', 'Bilinmiyor')
            patient_id = self.selected_patient['id']
            
            # Onay mesajı (sadece confirmation dialog bloklu kalabilir - kullanıcı onayı için gerekli)
            reply = QMessageBox.question(
                self,
                "Hastayı Sil",
                f"'{patient_name}' adlı hastayı silmek istediğinize emin misiniz?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                # Progress indicator göster
                self.show_info(f"'{patient_name}' siliniyor...")
                
                # Arka planda silme işlemini başlat (non-blocking)
                self._delete_thread = PatientDeleteThread(self.app_data_dir, patient_id)
                self._delete_thread.delete_finished.connect(self._on_patient_deleted)
                self._delete_thread.finished.connect(lambda: setattr(self, '_delete_thread', None))
                self._delete_thread.start()
                
                # UI'ı hemen temizle (kullanıcı deneyimi)
                self.selected_patient = None
                if self.main_window:
                    self.main_window.last_saved_patient = None
        except Exception as e:
            self.logger.error(f"Hasta silme hatası: {e}", exc_info=True)
            self.show_error(f"Hasta silinirken hata oluştu: {str(e)}")
    
    def _delete_all_patients(self):
        """Tüm hastaları sil - arka plan thread'de"""
        try:
            # Eğer zaten bir silme işlemi çalışıyorsa, yeni başlatma
            if hasattr(self, '_delete_thread') and self._delete_thread is not None:
                if self._delete_thread.isRunning():
                    self.show_warning("Silme işlemi zaten devam ediyor, lütfen bekleyin.")
                    return
            
            # Hasta sayısını patient_combo'dan al (zaten yüklü)
            if not hasattr(self, 'patient_combo'):
                self.show_error("Hasta listesi yüklenemedi.")
                return
            
            patient_count = self.patient_combo.count() - 1  # İlk item "Hasta Seçin..."
            
            if patient_count <= 0:
                self.show_info("Silinecek hasta bulunmamaktadır.")
                return
            
            # Tüm hasta ID'lerini combo'dan topla
            patient_ids = []
            for i in range(1, self.patient_combo.count()):  # 0. item "Hasta Seçin..."
                patient = self.patient_combo.itemData(i)
                if patient and patient.get('id'):
                    patient_ids.append(patient.get('id'))
            
            if not patient_ids:
                self.show_error("Hasta bilgileri alınamadı.")
                return
            
            # Onay mesajı (sadece confirmation dialog bloklu kalabilir - kullanıcı onayı için gerekli)
            reply = QMessageBox.question(
                self,
                "Tüm Hastaları Sil",
                f"Tüm hastaları ({len(patient_ids)} adet) silmek istediğinize emin misiniz?\n\nBu işlem geri alınamaz!",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                # Progress indicator göster
                self.show_info(f"{len(patient_ids)} hasta siliniyor...")
                
                # Arka planda silme işlemini başlat (non-blocking)
                self._delete_thread = PatientDeleteThread(self.app_data_dir, patient_ids)
                self._delete_thread.delete_finished.connect(self._on_patient_deleted)
                self._delete_thread.finished.connect(lambda: setattr(self, '_delete_thread', None))
                self._delete_thread.start()
                
                # UI'ı hemen temizle (kullanıcı deneyimi)
                self.selected_patient = None
                if self.main_window:
                    self.main_window.last_saved_patient = None
        except Exception as e:
            self.logger.error(f"Tüm hastaları silme hatası: {e}", exc_info=True)
            self.show_error(f"Hastalar silinirken hata oluştu: {str(e)}")
    
    def _on_patient_deleted(self, success, message):
        """Hasta silme işlemi tamamlandığında çağrılır (thread callback)"""
        try:
            if success:
                self.show_success(message)
            else:
                self.show_error(message)
            
            # Arka planda listeyi yenile
            self._load_patient_list()
            # Header'ı güncelle
            self._update_header_patient_info()
        except Exception as e:
            self.logger.error(f"Patient delete callback hatası: {e}", exc_info=True)
    
    def _check_command_timeouts(self):
        """
        Timeout olan komutları kontrol et ve retry et.
        GUI Stability Fix #4 - Command timeout handling
        Bu fonksiyon ana thread'de çalışır (QTimer'dan çağrılır).
        
        Optimizasyon: Timeout olan komutları önce filtrele, sonra işle.
        Bu sayede büyük dictionary'lerde performans artışı sağlanır.
        """
        current_time = time.time()
        timed_out_commands = []
        
        # Thread-safe erişim - Timeout olanları önce filtrele
        with self.pending_commands_lock:
            # Dictionary boşsa erken çık
            if not self.pending_commands:
                return
            
            # Timeout olan komutları bul (list comprehension ile optimize)
            timed_out_commands = [
                command_id 
                for command_id, cmd_info in self.pending_commands.items()
                if (current_time - cmd_info['timestamp']) > self.command_timeout
            ]
        
        # Timeout olan komutları işle (lock dışında, böylece diğer thread'ler beklemek zorunda kalmaz)
        for command_id in timed_out_commands:
            self._handle_command_timeout(command_id)
    
    def _handle_command_timeout(self, command_id):
        """
        Timeout olan komutu retry et veya fail et.
        GUI Stability Fix #4 - Command retry mechanism
        Bu fonksiyon ana thread'de çalışır.
        """
        # Thread-safe erişim
        with self.pending_commands_lock:
            if command_id not in self.pending_commands:
                return
            
            cmd_info = self.pending_commands[command_id]
            coil_num = cmd_info['coil_num']
            retry_count = cmd_info['retry_count']
        
        if retry_count < self.max_command_retries:
            # Retry
            with self.pending_commands_lock:
                if command_id in self.pending_commands:
                    self.pending_commands[command_id]['retry_count'] += 1
                    self.pending_commands[command_id]['timestamp'] = time.time()
            
            # MQTT ile tekrar gönder
            if self.main_window and hasattr(self.main_window, 'mqtt_client') and self.main_window.mqtt_client:
                topic = f"pemf/coil/{coil_num}/control"
                self.main_window.mqtt_client.publish(
                    topic, 
                    json.dumps(cmd_info['command']), 
                    qos=1
                )
            
            self.logger.warning(f"Command timeout, retrying ({retry_count + 1}/{self.max_command_retries}): {command_id}")
            
        else:
            # Max retry aşıldı, fail
            with self.pending_commands_lock:
                if command_id in self.pending_commands:
                    del self.pending_commands[command_id]
            
            # UI güncelle - hata durumu (ana thread'de olduğumuz için güvenli)
            if coil_num in self.coil_controls:
                controls = self.coil_controls[coil_num]
                controls['status_led'].setStyleSheet("color: #ef4444; font-size: 12px;")
                controls['status_label'].setText("Komut Başarısız")
                controls['status_container'].setStyleSheet("""
                    background: rgba(239, 68, 68, 0.1);
                    border-radius: 12px;
                    border: 1px solid rgba(239, 68, 68, 0.3);
                """)
                controls['start_btn'].setEnabled(True)
                controls['stop_btn'].setEnabled(False)
            
            self.show_error(f"Bobin {coil_num} komutu başarısız (timeout)")
            self.logger.error(f"Command failed after {self.max_command_retries} retries: {command_id}")
    
    def _check_esp_connections(self):
        """
        ESP bağlantılarını heartbeat'e göre kontrol et.
        Sadece MQTT bağlantısı kontrol edilir - MQTT bağlıysa ESP bağlı sayılır.
        Belirli bir süre içinde status mesajı gelmezse bağlantı kesilmiş sayılır.
        
        CRITICAL FIX M1: Hold lock during entire operation to prevent race conditions
        """
        # MQTT bağlantısını kontrol et
        mqtt_connected = False
        if self.main_window and hasattr(self.main_window, 'mqtt_client'):
            if self.main_window.mqtt_client and self.main_window.mqtt_client.is_connected():
                mqtt_connected = True
        
        current_time = time.time()
        
        for coil_id in range(1, 9):
            # MQTT bağlı değilse tüm bobinleri bağlı değil olarak işaretle
            if not mqtt_connected:
                with self.coil_status_lock:
                    if self.coil_connection_status.get(coil_id, False):
                        self.coil_connection_status[coil_id] = False
                        self._update_connection_status_label(coil_id, False)
                        self.logger.debug(f"Coil {coil_id} için MQTT bağlantısı yok - bağlantı kesildi olarak işaretlendi")
            else:
                # MQTT bağlı, heartbeat kontrolü yap
                # CRITICAL FIX M1: Hold lock during entire operation
                with self.coil_status_lock:
                    last_status_time = self.coil_last_status_time.get(coil_id, 0)
                    
                    # Timeout check inside lock to prevent race condition
                    if last_status_time > 0 and (current_time - last_status_time > self.ESP_TIMEOUT):
                        if self.coil_connection_status.get(coil_id, False):
                            # Bağlantı kesilmiş, durumu güncelle
                            self.coil_connection_status[coil_id] = False
                            self._update_connection_status_label(coil_id, False)
                            self.logger.debug(f"Coil {coil_id} için heartbeat timeout - bağlantı kesildi olarak işaretlendi")
    
    def _get_next_command_id(self, coil_num):
        """
        Thread-safe command ID generator.
        Her çağrıda benzersiz bir command_id döndürür.
        
        CRITICAL FIX BUG #5: Command ID counter overflow handling with modulo.
        Counter resets to 0 after 1 million to prevent overflow issues.
        
        Args:
            coil_num (int): Coil number (1-8)
            
        Returns:
            str: Unique command ID format: "cmd_{coil_num}_{counter}_{timestamp_ms}"
        """
        with self.command_id_counter_lock:
            # Overflow protection: Reset counter at 1 million (BUG #5 fix - use class constant)
            self.command_id_counter = (self.command_id_counter + 1) % self.MAX_COMMAND_ID_COUNTER
            command_id = f"cmd_{coil_num}_{self.command_id_counter}_{int(time.time() * self.MILLISECONDS_PER_SECOND)}"
        return command_id
    
    def add_pending_command(self, coil_num, command):
        """
        Add a command to pending_commands dictionary.
        Called from MainWindow when WebSocket server sends a command.
        This ensures UnifiedControlWindow can track commands sent from Android app.
        
        Args:
            coil_num (int): Coil number (1-8)
            command (dict): MQTT command with 'command', 'command_id', etc.
        """
        try:
            command_id = command.get('command_id')
            if not command_id:
                self.logger.warning(f"Command missing command_id, cannot add to pending: {command}")
                return
            
            with self.pending_commands_lock:
                self.pending_commands[command_id] = {
                    'coil_num': coil_num,
                    'command': command,
                    'timestamp': time.time(),
                    'retry_count': 0
                }
            self.logger.debug(f"Added pending command: {command_id} for coil {coil_num}")
        except Exception as e:
            self.logger.error(f"Error adding pending command: {e}", exc_info=True)
    
    def _handle_command_ack(self, coil_num, command_id, success):
        """
        MQTT thread'inden çağrılır. ESP8266'dan gelen command acknowledgment'ı işle.
        GUI Stability Fix #4 - ACK handling
        ASLA UI güncellemesi yapmayın. Sadece veriyi ana thread'e yolla.
        """
        # Thread-safe erişim
        cmd_info = None
        with self.pending_commands_lock:
            if command_id in self.pending_commands:
                # Komut bilgisini al ve sil
                cmd_info = self.pending_commands[command_id]
                del self.pending_commands[command_id]
        
        if cmd_info is None:
            # Komut bulunamadı, log kaydet ve çık
            # Note: This can happen if command was sent from WebSocket server (Android app)
            # and UnifiedControlWindow wasn't tracking it. This is OK - just log as debug.
            self.logger.debug(f"Command ACK received for unknown command: {command_id} (may be from WebSocket/Android app)")
            return
        
        # Güvenli sinyali emit et (UI güncellemesi ana thread'de yapılacak)
        # cmd_info'yu sinyal parametresi olarak geçir
        self._safe_handle_ack_signal.emit(coil_num, command_id, success, cmd_info)
        
        # Log kaydet (thread-safe)
        if success:
            self.logger.info(f"Command ACK received: {command_id} - SUCCESS")
        else:
            self.logger.error(f"Command ACK received: {command_id} - FAILED")
    
    def _load_timer_intervals(self):
        """
        Timer interval'larını settings'ten yükle (configurable).
        Timer Optimization: Yeni unified timer yapısına uyumlu (6→2 timers).
        """
        try:
            # Settings'ten timer interval'larını oku (varsa)
            unified_1hz = self.settings.value("timer_interval_unified_1hz", self.timer_intervals['unified_1hz'], type=int)
            esp_connection = self.settings.value("timer_interval_esp_connection", self.timer_intervals['esp_connection'], type=int)
            
            # Değerleri güncelle (minimum değerler ile)
            # unified_1hz: Min 500ms (2 FPS) - Status, command timeout, treatment countdown
            # esp_connection: Min 1000ms (1 FPS) - ESP connection heartbeat check
            self.timer_intervals['unified_1hz'] = max(500, unified_1hz)
            self.timer_intervals['esp_connection'] = max(1000, esp_connection)
            
            self.logger.debug(f"Timer intervals loaded (optimized 6→2): {self.timer_intervals}")
        except Exception as e:
            self.logger.warning(f"Timer intervals yüklenirken hata: {e}, default değerler kullanılıyor")
    
    def _update_treatment_countdown(self):
        """
        Treatment countdown'u gerçek zamanlı güncelle.
        Timer Optimizasyonu: unified_1hz_timer tarafından çağrılır.
        """
        try:
            if not self.treatment_active:
                # Treatment aktif değilse, sadece return (timer unified_1hz_timer tarafından yönetiliyor)
                return
            
            # Treatment aktif, countdown'u güncelle
            if hasattr(self, 'treatment_start_time') and hasattr(self, 'treatment_duration'):
                elapsed = time.time() - self.treatment_start_time
                
                if self.treatment_duration > 0:
                    remaining = max(0, self.treatment_duration - elapsed)
                    minutes = int(remaining // 60)
                    seconds = int(remaining % 60)
                    time_str = f"{minutes:02d}:{seconds:02d}"
                    
                    # UI'da countdown'u güncelle
                    if hasattr(self, 'remaining_time_label'):
                        self.remaining_time_label.setText(time_str)
                    
                    # Süre doldu mu kontrol et
                    if remaining <= 0:
                        # Treatment süresi doldu, durdur
                        self.stop_treatment()
                else:
                    # Süresiz seans
                    if hasattr(self, 'remaining_time_label'):
                        self.remaining_time_label.setText("Süresiz")
                        
        except Exception as e:
            self.logger.error(f"_update_treatment_countdown HATA: {e}", exc_info=True)
                
    def _load_settings(self):
        """Ayarları yükle"""
        # Otomatik mod ayarları
        self.auto_frequency_spin.setValue(self.settings.value("auto_frequency", 10.0, type=float))
        self.auto_duration_spin.setValue(self.settings.value("auto_duration", 30, type=int))
        self.auto_intensity_spin.setValue(self.settings.value("auto_intensity", 1.0, type=float))  # mT cinsinden
        
        # Otomatik mod - seçili hedef
        if hasattr(self, 'target_combo'):
            saved_target = self.settings.value("auto_target", "", type=str)
            if saved_target:
                target_index = self.target_combo.findText(saved_target)
                if target_index >= 0:
                    self.target_combo.setCurrentIndex(target_index)
        
        # Manuel mod ayarları
        self.master_freq_spin.setValue(self.settings.value("master_frequency", 1000, type=int))
        self.master_duty_spin.setValue(self.settings.value("master_duty", 50.0, type=float))
        self.master_duration_spin.setValue(self.settings.value("master_duration", 0, type=int))
        
        # Her bobin için ayarları yükle
        for coil_num in range(1, 9):
            if coil_num in self.coil_controls:
                controls = self.coil_controls[coil_num]
                
                # Frekans
                freq_key = f"coil_{coil_num}_frequency"
                if self.settings.contains(freq_key):
                    controls['freq_spin'].setValue(self.settings.value(freq_key, 1000, type=int))
                
                # Duty
                duty_key = f"coil_{coil_num}_duty"
                if self.settings.contains(duty_key):
                    controls['duty_spin'].setValue(self.settings.value(duty_key, 50.0, type=float))
                
                # Süre
                duration_key = f"coil_{coil_num}_duration"
                if self.settings.contains(duration_key):
                    controls['duration_spin'].setValue(self.settings.value(duration_key, 0, type=int))
        
        # Seçili tab'ı yükle
        saved_tab = self.settings.value("current_tab", 0, type=int)
        if hasattr(self, 'tab_widget') and 0 <= saved_tab < self.tab_widget.count():
            self.tab_widget.setCurrentIndex(saved_tab)
            self.current_mode = "automatic" if saved_tab == 0 else "manual"
        
    def _save_settings(self):
        """Ayarları kaydet"""
        # Otomatik mod ayarları
        self.settings.setValue("auto_frequency", self.auto_frequency_spin.value())
        self.settings.setValue("auto_duration", self.auto_duration_spin.value())
        self.settings.setValue("auto_intensity", self.auto_intensity_spin.value())
        
        # Otomatik mod - seçili hedef
        if hasattr(self, 'target_combo'):
            self.settings.setValue("auto_target", self.target_combo.currentText())
        
        # Manuel mod ayarları
        self.settings.setValue("master_frequency", self.master_freq_spin.value())
        self.settings.setValue("master_duty", self.master_duty_spin.value())
        self.settings.setValue("master_duration", self.master_duration_spin.value())
        
        # Her bobin için ayarları kaydet
        for coil_num in range(1, 9):
            if coil_num in self.coil_controls:
                controls = self.coil_controls[coil_num]
                
                # Frekans
                self.settings.setValue(f"coil_{coil_num}_frequency", controls['freq_spin'].value())
                
                # Duty
                self.settings.setValue(f"coil_{coil_num}_duty", controls['duty_spin'].value())
                
                # Süre
                self.settings.setValue(f"coil_{coil_num}_duration", controls['duration_spin'].value())
        
        # Seçili tab'ı kaydet
        if hasattr(self, 'tab_widget'):
            self.settings.setValue("current_tab", self.tab_widget.currentIndex())
        
    def _synchronize_status_from_main_window(self):
        """
        Main window'dan mevcut ESP durumlarını al ve bağlantı/PWM durumlarını senkronize et.
        Pencere her açıldığında çağrılır.
        """
        try:
            if not self.main_window:
                self.logger.warning("Main window bulunamadı, senkronizasyon atlandı.")
                return

            if hasattr(self.main_window, 'esp_status_buffer'):
                # MainWindow'un buffer'ındaki mevcut durumu al
                all_coils_status = self.main_window.esp_status_buffer

                # Tüm bobinleri (1-8) döngüye al
                for coil_id_int in range(1, 9):
                    coil_id_str = str(coil_id_int)

                    # Kontrollerin var olduğundan emin ol
                    if coil_id_int not in self.coil_controls:
                        continue

                    controls = self.coil_controls[coil_id_int]

                    if coil_id_str in all_coils_status:
                        # Bu bobin için durum bilgisi var
                        status_data = all_coils_status[coil_id_str]

                        # 1. Bağlantı Durumunu Güncelle
                        # Sadece MQTT bağlantısını kontrol et - MQTT bağlıysa ESP bağlı sayılır
                        if 'mqtt_connected' in status_data:
                            mqtt_connected = bool(status_data.get('mqtt_connected', False))
                            is_connected = mqtt_connected
                            
                            # Sadece durum değiştiyse güncelle (sürekli güncellemeyi önlemek için)
                            with self.coil_status_lock:
                                if self.coil_connection_status.get(coil_id_int, False) != is_connected:
                                    self.coil_connection_status[coil_id_int] = is_connected
                                    self._update_connection_status_label(coil_id_int, is_connected)
                            
                            # Son görülme zamanını güncelle (heartbeat için)
                            # MQTT bağlıysa heartbeat zamanını güncelle
                            if is_connected:
                                with self.coil_status_lock:
                                    self.coil_last_status_time[coil_id_int] = time.time()

                        # 2. PWM Durumunu Güncelle (En ÖNEMLİ KISIM)
                        # Hem 'running' (status'tan) hem de 'pwm_active' (sensörden) kontrol et
                        is_running = status_data.get('running', status_data.get('pwm_active', False))
                        with self.pwm_status_lock:
                            self.pwm_status[coil_id_int]['running'] = is_running

                        if is_running:
                            controls['status_led'].setStyleSheet("color: #22c55e; font-size: 12px;")
                            controls['status_label'].setText("Çalışıyor")
                            controls['status_container'].setStyleSheet("""
                                background: rgba(34, 197, 94, 0.1);
                                border-radius: 12px;
                                border: 1px solid rgba(34, 197, 94, 0.3);
                            """)
                            controls['start_btn'].setEnabled(False)
                            controls['stop_btn'].setEnabled(True)
                        else:
                            controls['status_led'].setStyleSheet("color: #ef4444; font-size: 12px;")
                            controls['status_label'].setText("Durduruldu")
                            controls['status_container'].setStyleSheet("""
                                background: rgba(239, 68, 68, 0.1);
                                border-radius: 12px;
                                border: 1px solid rgba(239, 68, 68, 0.3);
                            """)
                            controls['start_btn'].setEnabled(True)
                            controls['stop_btn'].setEnabled(False)

                        # 3. Parametreleri Güncelle (Spinbox'ları ayarla)
                        # Bu, UI'ın ESP'deki gerçek değerleri göstermesini sağlar
                        if 'freq' in status_data:
                            try:
                                controls['freq_spin'].setValue(int(status_data['freq']))
                            except ValueError:
                                self.logger.warning(f"Bobin {coil_id_int} için geçersiz freq değeri: {status_data['freq']}")
                        if 'duty' in status_data:
                            try:
                                controls['duty_spin'].setValue(float(status_data['duty']))
                            except ValueError:
                                self.logger.warning(f"Bobin {coil_id_int} için geçersiz duty değeri: {status_data['duty']}")
                        if 'duration' in status_data:
                            try:
                                controls['duration_spin'].setValue(int(status_data['duration']))
                            except ValueError:
                                self.logger.warning(f"Bobin {coil_id_int} için geçersiz duration değeri: {status_data['duration']}")
                        
                        # 4. PWM Duration ve Remaining Time'ı Güncelle
                        # pwm_duration ve pwm_remaining_time bilgilerini senkronize et
                        duration_value = status_data.get('pwm_duration') or status_data.get('duration')
                        if duration_value is not None:
                            with self.pwm_status_lock:
                                self.pwm_status[coil_id_int]['duration'] = duration_value
                        
                        # Calculate remaining time from start_timestamp (Time-Based Synchronization)
                        if 'pwm_start_timestamp' in status_data:
                            start_timestamp = status_data.get('pwm_start_timestamp')
                            pwm_active = status_data.get('pwm_active', False)
                            
                            if not pwm_active or duration_value is None or duration_value <= 0 or not start_timestamp:
                                self.pwm_remaining_time[coil_id_int] = None
                            else:
                                try:
                                    start_timestamp_ms = int(start_timestamp)
                                    duration_ms = duration_value * 60 * 1000
                                    end_timestamp_ms = start_timestamp_ms + duration_ms
                                    current_time_ms = int(time.time() * 1000)
                                    remaining_ms = end_timestamp_ms - current_time_ms
                                    remaining_seconds = max(0, remaining_ms // 1000)
                                    
                                    if remaining_seconds > 0:
                                        self.pwm_remaining_time[coil_id_int] = remaining_seconds
                                    else:
                                        self.pwm_remaining_time[coil_id_int] = None
                                except (ValueError, TypeError):
                                    self.pwm_remaining_time[coil_id_int] = None
                        elif duration_value is None or duration_value <= 0:
                            # Clear remaining time if duration is 0 or null
                            self.pwm_remaining_time[coil_id_int] = None
                        
                        # Remaining time display'ini güncelle
                        self._update_coil_remaining_time_display(coil_id_int)
                        # Countdown timer'ı yönet
                        # Timer management removed - using unified_1hz_timer (Performance Optimization)

                    else:
                        # Bu bobin için MainWindow'da durum bilgisi yok (henüz görülmedi)
                        with self.coil_status_lock:
                            self.coil_connection_status[coil_id_int] = False
                            self._update_connection_status_label(coil_id_int, False)
                        # Durumu 'Durduruldu' olarak ayarla (default)
                        controls['status_led'].setStyleSheet("color: #ef4444; font-size: 12px;")
                        controls['status_label'].setText("Durduruldu")
                        controls['status_container'].setStyleSheet("""
                            background: rgba(239, 68, 68, 0.1);
                            border-radius: 12px;
                            border: 1px solid rgba(239, 68, 68, 0.3);
                        """)
                        controls['start_btn'].setEnabled(True)
                        controls['stop_btn'].setEnabled(False)
                        
                        # Clear remaining time when stopped
                        self.pwm_remaining_time[coil_id_int] = None
                        self._update_coil_remaining_time_display(coil_id_int)
                        # Timer management removed - using unified_1hz_timer (Performance Optimization)
                        
        except Exception as e:
            self.logger.warning(f"_synchronize_status_from_main_window hatası: {e}", exc_info=True)
    
    def showEvent(self, event):
        """Pencere gösterildiğinde çağrılır"""
        super().showEvent(event)
        
        # Hasta listesini yeniden yükle (main window'da yeni hasta kaydedilmiş olabilir)
        self._load_patient_list()
        
        # Hasta bilgilerini güncelle
        self.update_patient_info()
        
        # Main window'dan mevcut ESP durumlarını al ve bağlantı/PWM durumlarını senkronize et
        self._synchronize_status_from_main_window()
        
    def closeEvent(self, event):
        """
        Pencere kapatılırken çağrılır - Tüm timer'ları temizle ve kaynakları serbest bırak
        
        Bu metod tüm timer'ları durdurur, deleteLater() çağırır ve ayarları kaydeder.
        İki closeEvent metodu birleştirildi (eski: satır 3667 ve 4004).
        """
        self.logger.info("UnifiedControlWindow kapatılıyor - Temizlik başlatılıyor")
        
        # HIGH FIX: Disconnect all signals to prevent memory leaks
        try:
            signal_list = [
                'treatment_status_changed',
                'treatment_progress_updated',
                'parameter_updated',
                'pwm_status_changed',
                'esp_connection_changed',
                'treatment_completed',
                'treatment_error',
                'command_sent'
            ]
            
            for signal_name in signal_list:
                if hasattr(self, signal_name):
                    try:
                        signal = getattr(self, signal_name)
                        signal.disconnect()
                    except TypeError:
                        pass  # No connections
            
            self.logger.debug("All signals disconnected")
        except Exception as e:
            self.logger.error(f"Error disconnecting signals: {e}")
        
        # Tüm timer'ları durdur ve temizle (Thread-safe with lock)
        timer_list = [
            ('treatment_timer', 'Seans timer'),
            ('unified_1hz_timer', 'Unified 1Hz timer'),
            ('esp_connection_check_timer', 'ESP connection check timer')
            # pwm_countdown_timer removed - merged into unified_1hz_timer (Performance Optimization)
        ]
        
        # CRITICAL FIX: Lock timer cleanup to prevent race conditions
        timer_cleanup_lock = threading.Lock()
        
        for timer_attr, timer_name in timer_list:
            try:
                with timer_cleanup_lock:
                    if hasattr(self, timer_attr):
                        timer = getattr(self, timer_attr)
                        if timer is not None:
                            try:
                                if timer.isActive():
                                    timer.stop()
                                    self.logger.debug(f"{timer_name} durduruldu")
                                # Timer'ı temizle (memory leak önleme)
                                timer.deleteLater()
                                setattr(self, timer_attr, None)
                            except RuntimeError:
                                # Timer zaten silinmiş, görmezden gel
                                self.logger.debug(f"{timer_name} zaten temizlenmiş")
                                setattr(self, timer_attr, None)
            except Exception as e:
                self.logger.error(f"{timer_name} temizlenirken hata: {e}")
        
        # Ayarları kaydet
        try:
            self._save_settings()
            self.logger.debug("Ayarlar kaydedildi")
        except Exception as e:
            self.logger.error(f"Ayarlar kaydedilirken hata: {e}")
        
        # ❌ KALDIRILDI: Aktif session'ı otomatik durdur ve kaydet
        # Kullanıcı pencereyi kapatsa bile tedavi devam etsin
        # PWM sadece kullanıcı açıkça stop butonuna bastığında dursun
        # ESP'ler bağımsız çalışmaya devam eder
        try:
            # Sadece UI state'i temizle, ESP'lere stop komutu gönderme
            if hasattr(self, 'active_session') and self.active_session and self.active_session.is_active:
                self.logger.info(f"Uygulama kapatılırken aktif session var (mode={self.active_session.mode}), ESP devam ediyor")
                # UI temizle ama ESP'lere stop gönderme
                self.treatment_active = False
                if hasattr(self, 'treatment_timer') and self.treatment_timer:
                    self.treatment_timer.stop()
            elif self.treatment_active:
                self.logger.info("treatment_active=True, UI temizleniyor, ESP'ler etkilenmiyor")
                self.treatment_active = False
        except Exception as e:
            self.logger.error(f"UI temizlenirken hata: {e}", exc_info=True)
        
        # Hasta listesi yükleme thread'ini temizle (Performance Fix)
        try:
            if hasattr(self, '_patient_list_thread') and self._patient_list_thread is not None:
                try:
                    # FIXED: Safe thread check - wrapped C++ object error prevention
                    if self._patient_list_thread.isRunning():
                        self._patient_list_thread.terminate()
                        self._patient_list_thread.wait(1000)  # 1 saniye bekle
                except RuntimeError:
                    # Thread already deleted (deleteLater called)
                    self.logger.debug("Patient list thread already deleted")
                finally:
                    # Don't call deleteLater() here - it's already connected to finished signal
                    # Just set to None to release reference
                    self._patient_list_thread = None
                    self.logger.debug("Hasta listesi yükleme thread'i temizlendi")
        except Exception as e:
            self.logger.error(f"Hasta listesi thread temizlenirken hata: {e}")
        
        # AI model load thread'ini temizle (Thread Safety - Graceful Shutdown)
        try:
            if hasattr(self, 'ai_model_load_thread') and self.ai_model_load_thread is not None:
                try:
                    # FIXED: Safe thread check - wrapped C++ object error prevention
                    if self.ai_model_load_thread.isRunning():
                        # CRITICAL FIX AI #4: Graceful shutdown with stop flag
                        self.ai_model_load_thread.stop_requested = True
                        if not self.ai_model_load_thread.wait(2000):  # 2 seconds for graceful shutdown
                            self.logger.warning("AI model load thread did not stop gracefully, terminating")
                            self.ai_model_load_thread.terminate()
                            self.ai_model_load_thread.wait(1000)  # Wait for termination
                except RuntimeError:
                    # Thread already deleted (deleteLater called)
                    self.logger.debug("AI model load thread already deleted")
                finally:
                    self.ai_model_load_thread = None
                    self.logger.debug("AI model load thread'i temizlendi")
        except Exception as e:
            self.logger.error(f"AI model load thread temizlenirken hata: {e}")
        
        # AI calculation thread'ini temizle (Thread Safety - Graceful Shutdown)
        try:
            if hasattr(self, 'calc_thread') and self.calc_thread is not None:
                try:
                    # FIXED: Safe thread check - wrapped C++ object error prevention
                    if self.calc_thread.isRunning():
                        # CRITICAL FIX AI #4: Add graceful shutdown for calculation thread
                        # Set stop flag if thread supports it
                        if hasattr(self.calc_thread, 'stop_requested'):
                            self.calc_thread.stop_requested = True
                        
                        if not self.calc_thread.wait(2000):  # 2 seconds for graceful shutdown
                            self.logger.warning("AI calculation thread did not stop gracefully, terminating")
                            self.calc_thread.terminate()
                            self.calc_thread.wait(1000)  # Wait for termination
                except RuntimeError:
                    # Thread already deleted (deleteLater called)
                    self.logger.debug("AI calculation thread already deleted")
                finally:
                    self.calc_thread = None
                    self.logger.debug("AI calculation thread'i temizlendi")
        except Exception as e:
            self.logger.error(f"AI calculation thread temizlenirken hata: {e}")
        
        # Ana pencereyi aktif et
        try:
            if self.main_window:
                self.main_window.activateWindow()
        except Exception as e:
            self.logger.warning(f"Ana pencere aktif edilirken hata: {e}")
        
        self.logger.info("UnifiedControlWindow temizliği tamamlandı")
        
        # Parent class'ın closeEvent'ini çağır
        super().closeEvent(event)
    
    def _setup_responsive_window(self):
        """Responsive pencere boyutlandırması ayarla"""
        try:
            width, height, scale_factor, screen_type = get_screen_info()
            
            # Base dimensions for different screen types
            base_configs = {
                "mobile": {"width": 800, "height": 600, "min_width": 600, "min_height": 500},
                "tablet": {"width": 1000, "height": 700, "min_width": 800, "min_height": 600},
                "laptop": {"width": 1200, "height": 900, "min_width": 1000, "min_height": 700},
                "desktop": {"width": 1400, "height": 1000, "min_width": 1200, "min_height": 800},
                "ultrawide": {"width": 1600, "height": 1100, "min_width": 1400, "min_height": 900}
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
            
        except Exception as e:
            self.logger.warning(f"Responsive window setup failed: {e}, using default size", exc_info=True)
            # Fallback boyutlar
            self.setMinimumSize(800, 600)
            self.resize(1200, 900)

    
    def _enable_responsive_features(self):
        """Responsive özelliklerini etkinleştir"""
        try:
            # Pencere yeniden boyutlandırma olayını bağla
            self.resizeEvent = self._on_window_resize
            
            # Responsive layout politikaları
            if hasattr(self, 'central_widget'):
                self.central_widget.setSizePolicy(
                    QSizePolicy.Policy.Expanding,
                    QSizePolicy.Policy.Expanding
                )
                
        except Exception as e:
            self.logger.warning(f"_enable_responsive_features hatası: {e}", exc_info=True)

    def _on_window_resize(self, event):
        """Pencere boyutu değiştiğinde çağrılır"""
        try:
            super().resizeEvent(event)
            
            # Yeni boyutları al
            new_size = event.size()
            width = new_size.width()
            height = new_size.height()
            
            # Responsive breakpoints
            is_small = width < 1000
            is_medium = 1000 <= width < 1400
            is_large = width >= 1400
            
            # Layout'u boyuta göre ayarla
            self._adjust_layout_for_size(is_small, is_medium, is_large)
            
            # Toast pozisyonlarını güncelle
            self._update_toast_positions()
            
        except Exception as e:
            self.logger.warning(f"_on_window_resize hatası: {e}", exc_info=True)

    def _adjust_layout_for_size(self, is_small, is_medium, is_large):
        """Boyuta göre layout'u ayarla"""
        try:
            # Küçük ekranlar için kompakt mod
            if is_small:
                # Daha küçük fontlar ve spacing
                self._apply_compact_styles()
            elif is_medium:
                # Orta boyut stilleri
                self._apply_medium_styles()
            else:
                # Büyük ekran stilleri
                self._apply_large_styles()
                
        except Exception as e:
            self.logger.warning(f"_adjust_layout_for_size hatası: {e}", exc_info=True)

    def _apply_compact_styles(self):
        """Kompakt ekran stilleri - Şu anda kullanılmıyor, gelecekte responsive tasarım için hazır"""
        pass

    def _apply_medium_styles(self):
        """Orta boyut ekran stilleri - Şu anda kullanılmıyor, gelecekte responsive tasarım için hazır"""
        pass

    def _apply_large_styles(self):
        """Büyük ekran stilleri - Şu anda kullanılmıyor, gelecekte responsive tasarım için hazır"""
        pass

    def _update_toast_positions(self):
        """Toast pozisyonlarını pencere boyutuna göre güncelle - Şu anda kullanılmıyor"""
        pass

    def _enable_accessibility_features(self):
        """Erişilebilirlik özelliklerini etkinleştir"""
        try:
            # Klavye navigasyonu
            self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            
            # Yüksek kontrast desteği
            self._setup_high_contrast_support()
            
            # Klavye kısayolları
            self._setup_keyboard_shortcuts()
            
            # Tooltip'ler ve açıklamalar
            self._setup_accessibility_tooltips()
            
        except Exception as e:
            self.logger.warning(f"_enable_accessibility_features hatası: {e}", exc_info=True)

    def _setup_high_contrast_support(self):
        """Yüksek kontrast desteği"""
        try:
            # Sistem tema ayarlarını kontrol et
            palette = QApplication.palette()
            
            # Yüksek kontrast modunda farklı renkler kullan
            if self._is_high_contrast_mode():
                self._apply_high_contrast_styles()
                
        except Exception as e:
            self.logger.warning(f"_setup_high_contrast_support hatası: {e}", exc_info=True)

    def _is_high_contrast_mode(self):
        """Yüksek kontrast modunda olup olmadığını kontrol et"""
        try:
            # Windows yüksek kontrast ayarını kontrol et
            import winreg
            try:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, 
                                   r"Control Panel\Accessibility\HighContrast")
                value, _ = winreg.QueryValueEx(key, "Flags")
                winreg.CloseKey(key)
                return bool(value & 1)  # HCF_HIGHCONTRASTON flag
            except:
                return False
        except:
            return False
    
    def _apply_high_contrast_styles(self):
        """Yüksek kontrast stilleri uygula"""
        try:
            high_contrast_style = """
                QWidget {
                    background-color: black;
                    color: white;
                    border: 2px solid white;
                }
                QPushButton {
                    background-color: black;
                    color: yellow;
                    border: 3px solid yellow;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: yellow;
                    color: black;
                }
                QLabel {
                    color: white;
                    font-weight: bold;
                }
            """
            self.setStyleSheet(high_contrast_style)
        except Exception as e:
            self.logger.warning(f"_apply_high_contrast_styles hatası: {e}", exc_info=True)

    def _setup_keyboard_shortcuts(self):
        """Klavye kısayollarını ayarla"""
        try:
            from PyQt6.QtGui import QShortcut, QKeySequence
            
            # Ctrl+S: Ayarları kaydet
            save_shortcut = QShortcut(QKeySequence("Ctrl+S"), self)
            save_shortcut.activated.connect(self._save_settings)
            
            # Ctrl+R: Yenile/Sıfırla
            refresh_shortcut = QShortcut(QKeySequence("Ctrl+R"), self)
            refresh_shortcut.activated.connect(self._refresh_interface)
            
            # F1: Yardım
            help_shortcut = QShortcut(QKeySequence("F1"), self)
            help_shortcut.activated.connect(self._show_help)
            
            # Esc: Acil durdur
            emergency_shortcut = QShortcut(QKeySequence("Escape"), self)
            emergency_shortcut.activated.connect(self._emergency_stop)
            
            # Space: Başlat/Durdur toggle
            toggle_shortcut = QShortcut(QKeySequence("Space"), self)
            toggle_shortcut.activated.connect(self._toggle_treatment)
            
        except Exception as e:
            self.logger.warning(f"_setup_keyboard_shortcuts hatası: {e}", exc_info=True)

    def _setup_accessibility_tooltips(self):
        """Erişilebilirlik tooltip'lerini ayarla"""
        try:
            # Ana pencere için tooltip
            self.setToolTip("PEMF Seans Kontrol Merkezi - Klavye kısayolları: F1=Yardım, Esc=Acil Durdur, Space=Başlat/Durdur")
            
            # Coil kontrolleri için tooltip'ler eklenecek
            # Bu _create_coil_control metodunda yapılacak
            
        except Exception as e:
            self.logger.warning(f"_setup_accessibility_tooltips hatası: {e}", exc_info=True)
    
    def _refresh_interface(self):
        """Arayüzü yenile (Ctrl+R)"""
        try:
            self.update_status()
            self.show_info("Arayüz yenilendi")
        except Exception as e:
            self.show_error(f"Arayüz yenilenemedi: {e}")
    
    def _show_help(self):
        """Yardım göster (F1)"""
        try:
            help_text = """
            PEMF Kontrol Merkezi Yardım
            
            Klavye Kısayolları:
            • F1: Bu yardım menüsü
            • Esc: Acil durdur (tüm bobinler)
            • Space: Seans başlat/durdur
            • Ctrl+S: Ayarları kaydet
            • Ctrl+R: Arayüzü yenile
            
            Kontroller:
            • Otomatik mod: Hedef seçerek Seans başlatın
            • Manuel mod: Her bobini ayrı ayrı kontrol edin
            • Frekans: 1-10000 Hz arası
            • Duty Cycle: %1-100 arası
            • Süre: 1-3600 saniye arası
            
            Güvenlik:
            • Acil durumda Esc tuşuna basın
            • Seans sırasında parametreleri değiştirmeyin
            • Cihaz bağlantısını kontrol edin
            """
            
            from PyQt6.QtWidgets import QMessageBox
            msg = QMessageBox(self)
            msg.setWindowTitle("Yardım")
            msg.setText(help_text)
            msg.setIcon(QMessageBox.Icon.Information)
            msg.exec()
            
        except Exception as e:
            self.show_error(f"Yardım gösterilemedi: {e}")
    
    def _emergency_stop(self):
        """Acil durdur (Esc)"""
        try:
            self.stop_treatment()
            self.show_warning("ACİL DURDUR - Tüm bobinler durduruldu!")
        except Exception as e:
            self.show_error(f"Acil durdur hatası: {e}")
    
    def _toggle_treatment(self):
        """Tedavi başlat/durdur toggle (Space)"""
        try:
            if self.treatment_active:
                self.stop_treatment()
            else:
                if self.current_mode == "automatic":
                    self.start_automatic_treatment()
                else:
                    self.start_all_coils()
        except Exception as e:
            self.show_error(f"Toggle treatment hatası: {e}")
    
    
    def format_remaining_time(self, seconds: int) -> str:
        """Format remaining time as 'Kalan: X:YY'"""
        if seconds <= 0:
            return ""
        minutes = seconds // 60
        secs = seconds % 60
        return f"Kalan: {minutes}:{secs:02d}"
    
    def _update_coil_remaining_time_display(self, coil_id: int):
        """Update remaining time display for a specific coil (FIXED: Added thread-safe locks)"""
        try:
            if coil_id not in self.coil_controls:
                return
            
            controls = self.coil_controls[coil_id]
            
            # FIXED: Thread-safe dictionary access with locks
            with self.pwm_remaining_time_lock:
                remaining_time = self.pwm_remaining_time.get(coil_id)
            
            with self.pwm_status_lock:
                is_running = self.pwm_status.get(coil_id, {}).get('running', False)
                duration = self.pwm_status.get(coil_id, {}).get('duration', 0)
            
            # IMPORTANT: If duration is 0 or null, don't show remaining time (unlimited PWM)
            if is_running and duration is not None and duration > 0 and remaining_time is not None and remaining_time > 0:
                formatted = self.format_remaining_time(remaining_time)
                if formatted:
                    controls['remaining_time_label'].setText(formatted)
                    controls['remaining_time_label'].setVisible(True)
                else:
                    controls['remaining_time_label'].setVisible(False)
            else:
                controls['remaining_time_label'].setVisible(False)
        except Exception as e:
            self.logger.error(f"Error updating remaining time display for coil {coil_id}: {e}", exc_info=True)
            # Don't show toast for display update errors (too frequent)
    
    def _update_pwm_countdowns(self):
        """
        Update countdown for all active PWM coils.
        Called from unified_1hz_timer (Performance Optimization - No separate timer).
        FIXED: Nested lock deadlock - read all data first, then process without holding locks.
        """
        try:
            # STEP 1: Read all PWM status data (avoid nested locks)
            with self.pwm_status_lock:
                pwm_statuses = {i: self.pwm_status.get(i, {}).copy() for i in range(1, 9)}
            
            # STEP 2: Read remaining times
            with self.pwm_remaining_time_lock:
                remaining_times = {i: self.pwm_remaining_time.get(i) for i in range(1, 9)}
            
            # STEP 3: Process countdowns (no locks held)
            updates = {}  # Track changes to apply
            for coil_id in range(1, 9):
                is_running = pwm_statuses[coil_id].get('running', False)
                duration = pwm_statuses[coil_id].get('duration', 0)
                remaining_time = remaining_times[coil_id]
                
                # Only countdown if duration > 0 (not unlimited)
                if is_running and duration is not None and duration > 0 and remaining_time is not None and remaining_time > 0:
                    # Schedule decrement
                    updates[coil_id] = remaining_time - 1
                elif is_running:
                    # PWM running but no countdown (unlimited or expired), hide display
                    if coil_id in self.coil_controls:
                        self.coil_controls[coil_id]['remaining_time_label'].setVisible(False)
            
            # STEP 4: Apply updates with lock
            if updates:
                with self.pwm_remaining_time_lock:
                    for coil_id, new_time in updates.items():
                        self.pwm_remaining_time[coil_id] = new_time
                
                # STEP 5: Update UI (outside lock)
                for coil_id in updates.keys():
                    self._update_coil_remaining_time_display(coil_id)
                    
        except Exception as e:
            self.logger.error(f"Error updating PWM countdowns: {e}", exc_info=True)
            self._safe_show_toast_signal.emit(f"⚠️ Countdown hatası: {str(e)[:50]}", "error")
    
    def _publish_session_status_to_mqtt(
        self,
        active: bool,
        mode: str,
        patient_name: str,
        target: str,
        duration_minutes: int,
        frequency: float,
        intensity: float,
        duty_cycle: float,
        connected_coils_count: int
    ):
        """
        ✅ MQTT'ye session bilgilerini publish et (Android app için).
        
        Topic: pemf/system/session
        Retained: True (Android app bağlandığında son durumu görsün)
        
        Args:
            active: Session aktif mi?
            mode: 'automatic', 'ai', veya ''
            patient_name: Hasta adı
            target: Tedavi hedefi
            duration_minutes: Planlanan süre (dakika)
            frequency: Frekans (Hz)
            intensity: Yoğunluk (mT veya %)
            duty_cycle: Duty cycle (%)
            connected_coils_count: Bağlı bobin sayısı
        """
        try:
            if not self.main_window or not hasattr(self.main_window, 'mqtt_client') or not self.main_window.mqtt_client:
                self.logger.warning("MQTT client yok, session bilgisi gönderilemedi")
                return
            
            if not self.main_window.mqtt_client.is_connected():
                self.logger.warning("MQTT bağlı değil, session bilgisi gönderilemedi")
                return
            
            # Session payload (Android app ile uyumlu format)
            payload = {
                "active": active,
                "mode": mode,
                "patient_name": patient_name,
                "treatment_mode": mode.upper() if mode else "",  # "AUTOMATIC", "AI"
                "treatment_target": target,
                "target": target,  # Backward compatibility
                "duration_minutes": duration_minutes,
                "start_timestamp": int(self.treatment_start_time * 1000) if hasattr(self, 'treatment_start_time') and active else 0,  # Unix Epoch ms
                "frequency": frequency,
                "intensity": intensity,
                "duty_cycle": duty_cycle,
                "connected_coils": connected_coils_count,
                "timestamp": int(time.time() * 1000)  # Current timestamp
            }
            
            topic = "pemf/system/session"
            payload_json = json.dumps(payload)
            
            # Retained=True: Android app bağlandığında son session durumunu görsün
            self.main_window.mqtt_client.publish(topic, payload_json, qos=1, retain=True)
            
            self.logger.info(
                f"Session status published to MQTT: active={active}, mode={mode}, "
                f"patient={patient_name}, duration={duration_minutes}min"
            )
            
        except Exception as e:
            self.logger.error(f"Session bilgisi MQTT'ye gönderilemedi: {e}", exc_info=True)
    
    def _cleanup_stale_esp_devices(self):
        """
        ✅ Periyodik ESP cleanup: 5 saniyeden eski ESP'leri kaldır.
        Bu, retained MQTT messages'dan gelen eski ESP'lerin UI'da görünmesini önler.
        Android MqttService.kt ile aynı mantık.
        """
        try:
            ESP_TIMEOUT_MS = 5_000  # 5 seconds
            current_time_ms = int(time.time() * 1000)
            
            with self.coil_status_lock:
                # Temizlenecek ESP'leri bul
                stale_coils = []
                for coil_id in range(1, 9):
                    last_status_time_sec = self.coil_last_status_time.get(coil_id, 0)
                    last_status_time_ms = int(last_status_time_sec * 1000)
                    age_ms = current_time_ms - last_status_time_ms
                    
                    if age_ms > ESP_TIMEOUT_MS:
                        # ESP 5 saniyeden uzun süredir görünmüyor - tamamen temizle
                        stale_coils.append(coil_id)
                        self.logger.debug(f"Removing stale ESP Coil {coil_id} (last seen {age_ms / 1000:.0f}s ago)")
                        # coil_last_status_time'dan kaldır
                        self.coil_last_status_time.pop(coil_id, None)
                
                # UI'da bağlantı durumunu güncelle
                if stale_coils:
                    for coil_id in stale_coils:
                        self.coil_connection_status[coil_id] = False
                        self._update_connection_status_label(coil_id, False)
                    
                    self.logger.info(f"ESP cleanup: removed {len(stale_coils)} stale devices (Coils: {stale_coils})")
        
        except Exception as e:
            self.logger.error(f"Error in _cleanup_stale_esp_devices: {e}", exc_info=True)
    
    def _start_all_with_apply(self):
        """
        Manuel mod 'Tümünü Başlat' için wrapper fonksiyon.
        Önce master parametreleri tüm bobinlere uygular (set_params),
        ardından tüm bobinleri başlatır (start).
        Bu sayede spinbox update sorunu çözülür.
        """
        try:
            # Adım 1: Master parametreleri tüm bobinlere uygula (UI + set_params)
            self.apply_to_all_coils()
            
            # Adım 2: Qt event loop'un işlemesi için kısa bir bekleme
            # Bu sayede setValue() işlemleri tamamlanır
            QApplication.processEvents()
            
            # Adım 3: Şimdi tüm bobinleri başlat
            # Not: apply_to_all_coils zaten set_params gönderdi,
            # şimdi start komutunu göndereceğiz
            self.start_all_coils()
            
        except Exception as e:
            self.logger.error(f"Error in _start_all_with_apply: {e}", exc_info=True)
            self.show_error(f"Tümünü başlat hatası: {str(e)}")


if __name__ == "__main__":
    # Tek başına çalıştırıldığında basit loglama
    logging.basicConfig(level=logging.DEBUG)
    
    app = QApplication(sys.argv)
    window = UnifiedControlWindow()
    window.show()
    sys.exit(app.exec())
