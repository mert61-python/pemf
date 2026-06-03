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
import copy
import logging
import time
import threading
import itertools
import socket
import struct
# numpy: lazy import - top-level import LattePanda'da 1+ saniye suruyor ve GUI'yi bloke ediyor.
# Kullanilan yerlerde (ornegin _on_camera_prediction_ready) lokal olarak import edilecek.
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


from utils.responsive_label import ResponsiveImageLabel
from pemf_gui import  get_image_path
from database.session_manager import get_session_manager
from database.patient_database import get_patient_database
from database.treatment_history_db import get_treatment_db
from styles import StyleMixin
from utils.hardware_aware_mixin import HardwareAwareMixin
from utils.device_profile import detect_device_profile, DeviceCategory, DeviceProfile
from utils.responsive_utils import (
    get_screen_info, apply_responsive_widget_scaling,
    scale_value as _sv_ucw, get_responsive_pt as _pt_ucw,
    scale_stylesheet as _ss_ucw,
)  # [RESP-PATCHED]


def _rpt(base_pt: float) -> int:
    """
    Scale a base point size to the current screen's DPI/resolution.
    Uses the same scale_factor as get_screen_info() so fonts grow
    naturally on high-DPI monitors and shrink on small screens.
    Returns an integer suitable for use in stylesheet strings.
    """
    try:
        _, _, scale_factor, _ = get_screen_info()
        # Clamp to a sensible range so text is never unreadably tiny/huge
        scaled = int(round(base_pt * scale_factor))
        return max(6, min(scaled, int(base_pt * 2.5)))
    except Exception:
        return int(base_pt)


def _rpx(base_px: float) -> int:
    """
    Scale a base pixel size to the current screen's DPI/resolution.
    """
    try:
        _, _, scale_factor, _ = get_screen_info()
        scaled = int(round(base_px * scale_factor))
        return max(4, min(scaled, int(base_px * 2.5)))
    except Exception:
        return int(base_px)
from utils.path_utils import resource_path
# AI Mode Controller
try:
    from windows.ai_mode_controller import create_ai_controller, AI_AVAILABLE, AI_IMPORT_ERROR
except Exception as e:
    # Capture the actual import error message so UI can show useful diagnostics
    create_ai_controller = None
    AI_AVAILABLE = False
    AI_IMPORT_ERROR = str(e)

# Custom SpinBox sınıfları - Wheel event'lerini devre dışı bırakmak için
# CameraAIThread opsiyoneldir — kamera/paket yoksa pencere yine de açılır.
try:
    from windows.camera_ai_thread import CameraAIThread
    CAMERA_AVAILABLE = True
except Exception as _cam_err:
    CameraAIThread = None
    CAMERA_AVAILABLE = False
    import logging as _logging
    _logging.getLogger('UnifiedControlWindow').warning(
        f"CameraAIThread yüklenemedi (kamera/paket eksik): {_cam_err}"
    )

# ============================================================
# Rapor §2.1 / §5.1: CoilStateStore — 6 dağınık lock → 1 nesne
# Thread-safe, tek merkezli bobin state deposu
# ============================================================

@dataclass
class CoilState:
    """Tek bir bobinin anlık durumu (snapshot nesnesi)."""
    connected: bool = False
    running: bool = False
    freq: float = 1000.0
    duty: float = 50.0
    duration: int = 0
    remaining_sec: Optional[int] = None
    last_seen: float = 0.0
    mag_mt: float = 0.0


class CoilStateStore:
    """
    Thread-safe, tek merkezli bobin state deposu.

    6 ayrı lock (coil_status_lock, pwm_status_lock, pwm_remaining_time_lock,
    last_mag_measurements_lock, pending_commands_lock, command_id_counter_lock)
    yerine tek bir RLock kullanır.

    Rapor §2.1 / §5.1 implementasyonu.
    """

    def __init__(self, num_coils: int = 8):
        # Reentrant: aynı thread iç içe alabilir
        self._lock = threading.RLock()
        self._states: dict[int, CoilState] = {
            i: CoilState() for i in range(1, num_coils + 1)
        }

    def update(self, coil_id: int, **kwargs) -> CoilState:
        """State'i atomik olarak güncelle, snapshot döndür."""
        with self._lock:
            state = self._states[coil_id]
            for k, v in kwargs.items():
                setattr(state, k, v)
            return CoilState(**state.__dict__)

    def get(self, coil_id: int) -> CoilState:
        """Güvenli snapshot al."""
        with self._lock:
            return CoilState(**self._states[coil_id].__dict__)

    def get_all(self) -> dict[int, CoilState]:
        """Tüm state'lerin kopyasını döndür."""
        with self._lock:
            return {cid: CoilState(**s.__dict__) for cid, s in self._states.items()}

    def mark_stale(self, coil_id: int, timeout_sec: float) -> bool:
        """
        Timeout kontrolü. True dönerse bobin bağlantısı kesildi: UI güncellenmelidir.
        """
        import time as _time
        with self._lock:
            state = self._states[coil_id]
            if state.last_seen > 0 and (_time.time() - state.last_seen) > timeout_sec:
                if state.connected:
                    state.connected = False
                    return True
        return False


def _crc16_ccitt(data: bytes) -> int:
    """CCITT CRC-16 hesapla. Modül düzeyinde tanımlı — her çağrıda yeniden oluşturulmaz.
    
    Rapor §3.3: crc16_ccitt iç içe fonksiyon tanımı performans sorunu giderildi.
    """
    crc = 0xFFFF
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = (crc << 1) ^ 0x1021 if crc & 0x8000 else crc << 1
    return crc & 0xFFFF


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
    stop_time: Optional[datetime] = None  # HATA-5 FIX: durdurulma zamanı

    def get_actual_duration_minutes(self) -> float:
        """Gerçek seans süresini dakika cinsinden döndür"""
        if self.is_active:
            elapsed = datetime.now() - self.start_time
        else:
            # HATA-5 FIX: stop_time kullan; yoksa start_time ile hesapla
            end = self.stop_time if self.stop_time is not None else datetime.now()
            elapsed = end - self.start_time
        return elapsed.total_seconds() / 60.0


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
    """AI hesaplamalarını arka planda yapmak için QThread (U-06 Fix)"""
    calculation_finished = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)

    def __init__(self, controller, treatment_target, patient_info):
        super().__init__()
        self.controller = controller
        self.treatment_target = treatment_target
        self.patient_info = patient_info

    def run(self):
        try:
            recommendation = self.controller.get_recommendations(
                treatment_target=self.treatment_target,
                patient_info=self.patient_info
            )
            self.calculation_finished.emit(recommendation)
        except Exception as e:
            self.error_occurred.emit(str(e))

class UnifiedControlWindow(QMainWindow, HardwareAwareMixin, StyleMixin):
    """
    Birleşik PEMF Kontrol Penceresi
    
    Bu sınıf, manuel ve otomatik PEMF kontrol modlarını tek bir arayüzde birleştirir:
    - Manuel Mod: Bireysel bobinler için detaylı kontrol
    - Otomatik Mod: Tedavi hedeflerine göre önceden tanımlanmış parametreler
    
    Design System entegrasyonu ile merkezi stil yönetimi kullanır.
    """
    
    # === CONSTANTS (Code Quality Fix - Magic Numbers) ===
    # Timeouts
    ESP_HEARTBEAT_TIMEOUT_SEC = 5.0  # ESP timeout süresi (saniye)
    MQTT_COMMAND_TIMEOUT_SEC = 2.0   # MQTT komut timeout (saniye)
    MQTT_COMMAND_MAX_RETRIES = 3     # Max retry count for commands
    
    # Throttling
    SENSOR_UPDATE_THROTTLE_MS = 1000  # Sensor UI update throttle (ms) - 1Hz Senkronizasyon
    CRITICAL_TEMP_THRESHOLD = 60     # Critical temperature (°C)
    CRITICAL_CURRENT_THRESHOLD = 5   # Critical current (A)
    
    # Time conversion
    SECONDS_PER_MINUTE = 60
    MILLISECONDS_PER_SECOND = 1000
    
    # Timer intervals (default values, can be overridden from settings)
    DEFAULT_UNIFIED_1HZ_INTERVAL = 1000      # 1 second
    DEFAULT_ESP_CONNECTION_CHECK_INTERVAL = 2000  # 2 seconds
    
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
    _safe_update_temperature_signal = pyqtSignal(int, float)  # coil_id, temperature
    # --- YENİ GÜVENLİ SİNYALLER SONU ---
    _session_saved_signal = pyqtSignal(object, str, str)  # session_id, patient_name, stop_reason
    
    def __init__(self, main_window=None):
        super().__init__()
        # Explicitly initialize Python mixins because QMainWindow.__init__ doesn't call super()
        try:
            StyleMixin.__init__(self)
        except NameError:
            pass # In case StyleMixin is not imported correctly, though it should be if it's in the class signature
        try:
            HardwareAwareMixin.__init__(self)
        except NameError:
            pass
        self._connect_screen_change_signal()
        self._setup_window_for_profile()
        self.main_window = main_window
        self.stm_is_connected = False
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
        
        # ================================================================
        # LOCK ALIŞ SIRASI — Bu sıraya KESINLIKLE uy, aksi deadlock doğurur:
        #
        #   1. coil_status_lock
        #   2. pwm_status_lock
        #   3. pwm_remaining_time_lock
        #   4. last_mag_measurements_lock
        #   5. pending_commands_lock
        #   6. command_id_counter_lock
        #
        # İki lock aynı anda gerekiyorsa her zaman yukarıdaki sıraya göre al.
        # Örnek DOĞRU:   with coil_status_lock: ... with pwm_status_lock: ...
        # Örnek YANLIŞ:  with pwm_status_lock: ... with coil_status_lock: ...
        # ================================================================
        self.coil_status_lock          = threading.Lock()
        self.pwm_status_lock           = threading.Lock()
        self.pwm_remaining_time_lock   = threading.Lock()
        self.last_mag_measurements_lock = threading.Lock()
        self.pending_commands_lock     = threading.Lock()
        # Rapor §2.2.3: command_id_counter_lock gereksiz — itertools.count atomik
        # self.command_id_counter_lock kaldırıldı
        self._cmd_counter = itertools.count(1)  # Thread-safe, lock gerekmez
        
        # ESP timeout optimizasyonu: ESP 1Hz (1000ms) status update yapıyor
        # Network delay + processing: ~100-300ms normal, 3 saniye güvenli margin
        self.ESP_TIMEOUT = self.ESP_HEARTBEAT_TIMEOUT_SEC  # Use class constant
        self.treatment_active = False
        # Rapor §4.3: Widget'lar __init__'te None ile başlatıldı → hasattr kontrolü gerekmez
        self.ai_pro_result_labels: Optional[dict] = None
        self.lbl_ai_pro_countdown = None
        self._udp_seq_main: int = 0
        
        self._last_ai_recommendation: Optional[dict] = None  # Rapor §3.4: AI önerisi state deposu

        # Son sıcaklık değerlerini cache'le (gereksiz UI güncellemesini azaltmak için)
        self._last_sensor_values = {}  # {coil_id: {'temp': float}}
        
        # PID Closed-Loop State
        self.last_mag_measurements = {} # {coil_id: float (mT)}
        self.PID_Kp = 1.0 # Eğer mT %1 saparsa, duty cycle'ı bu katsayı ile telafi et
        
        # Status update optimizasyonu için önceki durum
        self._last_status_text = None  # Debounce için önceki status text
        
        # MQTT Command Tracking (GUI Stability Fix #4 - QoS 1 + ACK)
        self.pending_commands = {}  # {command_id: {'coil_num', 'command', 'timestamp', 'retry_count'}}
        # UI dondurma: komut gönderilince set edilir, ESP status titrenmesini önler
        # {coil_id: deadline_float}  — deadline geçince kilit kalkar
        self._coil_ui_locked_until: dict = {i: 0.0 for i in range(1, 9)}
        # Command timeout optimizasyonu: 
        # - MQTT network delay: ~50-200ms (local network)
        # - ESP processing: ~10-50ms
        # - ACK QoS 1 ile güvenilir delivery: ~100-300ms toplam
        # - 2 saniye güvenli margin, retry mekanizması var (3 retry = 6 saniye toplam)
        self.command_timeout = self.MQTT_COMMAND_TIMEOUT_SEC  # Use class constant
        self.max_command_retries = self.MQTT_COMMAND_MAX_RETRIES  # Use class constant
        # command_id_counter → _cmd_counter (itertools.count) ile değiştirildi (Rapor §2.2.3)
        
        # Timer Optimizasyonu: Configurable interval'lar
        # Timer interval'ları settings'ten okunabilir (default değerler)
        self.timer_intervals = {
            'unified_1hz': 1000,      # Unified 1Hz timer interval (ms) - combines status, command_timeout, treatment_countdown
            'esp_connection': self.DEFAULT_ESP_CONNECTION_CHECK_INTERVAL,   # ESP connection check interval (ms)
        }
        
        # Settings'ten timer interval'larını yükle (varsa)
        self._load_timer_intervals()
        
        # Timer Optimization: Unified 1Hz timer (combines status, command_timeout, treatment_countdown)
        # Reduces timer overhead by ~60% (6 timers -> 2 timers)
        self.unified_1hz_timer = QTimer(self)  # Parent widget'a bağla
        self.unified_1hz_timer.timeout.connect(self._on_unified_1hz_tick)
        self.unified_1hz_timer.start(self.timer_intervals['unified_1hz'])
        
        # ESP connection heartbeat checker timer (separate for longer interval)
        self.esp_connection_check_timer = QTimer(self)  # Parent widget'a bağla
        self.esp_connection_check_timer.timeout.connect(self._check_esp_connections)
        self.esp_connection_check_timer.start(self.timer_intervals['esp_connection'])
        
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
        self.db = get_treatment_db(self.app_data_dir)
        
        # NEW: Active session state (memory only, saved on stop)
        self.active_session: Optional[SessionState] = None
        # Rapor §4.2.2: _stopping_treatment → threading.Event (daha açık, güvenli)
        self._stop_in_progress = threading.Event()  # set() = durdurma devam ediyor
        
        # Patient list load thread (None until first load)
        self._patient_list_thread = None
        self._patient_list_reload_pending = False
        
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
        self._safe_update_temperature_signal.connect(
            self._safe_update_temperature_label,
            Qt.ConnectionType.QueuedConnection
        )
        self._session_saved_signal.connect(
            self._on_session_saved,
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
        self._apply_styles()
        self._init_ui()
        self._load_settings()
        
        # Initialize AI controller
        self._init_ai_controller()
        
        # Hasta bilgilerini güncelle
        self.update_patient_info()
        
    @property
    def is_treatment_active(self) -> bool:
        """
        Tedavinin gerçekten aktif olup olmadığını tek kaynaktan döndürür.

        Rapor §4.2.1: treatment_active (bool) ve active_session iki ayrı state
        yerine bu property tek kaynak (single source of truth) olarak kullanılmalıdır.
        Mevcut treatment_active alanı geriye dönük uyumluluk için korunmuştur;
        yeni kodda if self.is_treatment_active kullanın.
        """
        return self.active_session is not None and self.active_session.is_active

    def _apply_profile_to_layouts(self, profile) -> None:
        """
        UnifiedControlWindow'a özgü ek layout'lara profil uygula.

        HardwareAwareMixin'in temel davranışı (centralWidget + tab_widget
        layout'ları) super() ile korunur.  Burada sadece proje-spesifik
        ek layout'lar eklenir.

        Eklenen layout'lar:
            • automatic_tab / manual_tab / ai_tab / ai_pro_tab  → içerik boşluğu
            • header_frame → kompakt ekranda sıkışmaması için margin azalt
        """
        # ── Temel: centralWidget + tab_widget layout'larını güncelle ─────────
        super()._apply_profile_to_layouts(profile)  # type: ignore[misc]

        # ── Ek: Her tab'ın kendi iç layout'u ────────────────────────────────
        #
        # tab_widget.widget(i) üzerinden erişmek yerine attribute isimleriyle
        # gidiyoruz — böylece sadece var olan sekmeleri güncelliyoruz.
        #
        _extra_tabs = (
            getattr(self, "automatic_tab",         None),
            getattr(self, "manual_tab",            None),
            getattr(self, "ai_tab",                None),
            getattr(self, "ai_pro_tab",            None),
            getattr(self, "cat_disease_tab",       None),
            getattr(self, "feline_reticulocytes_tab", None),
            getattr(self, "cat_vision_tab",        None),
        )
        for tab in _extra_tabs:
            if tab is not None and tab.layout() is not None:
                tab.layout().setContentsMargins(
                    profile.content_margin,
                    profile.content_margin,
                    profile.content_margin,
                    profile.content_margin,
                )
                tab.layout().setSpacing(profile.layout_spacing)

        # ── Header frame: kompakt ekranda margin'i yarıya indir ──────────────
        # Header her zaman görünür kalır; sadece iç boşluğu ayarlıyoruz.
        header_frame = getattr(self, "_header_frame", None)
        if header_frame and header_frame.layout():
            m = max(4, profile.layout_margin // 2) if profile.is_compact else profile.layout_margin
            header_frame.layout().setContentsMargins(m, m, m, m)

        self.logger.debug(
            "_apply_profile_to_layouts [UCW override]: spacing=%d, margin=%d, content_margin=%d",
            profile.layout_spacing,
            profile.layout_margin,
            profile.content_margin,
        )

    # =========================================================================
    # OVERRIDE 2 — COMPACT_TOUCH  (<10 inç Kiosk / Endüstriyel Panel)
    # =========================================================================

    def _adapt_for_compact_touch(self, profile) -> None:
        """
        UnifiedControlWindow — Kompakt dokunmatik panel uyarlamaları.

        super() çağrısı HardwareAwareMixin'in bilinen attribute listelerini
        tarar (auto_start_btn, stop_all_btn, patient_combo vb.).
        Buraya SADECE o listede olmayan, projeye özgü widget'lar eklenir.

        Strateji:
            ┌─────────────────────────────────────────────────────────────┐
            │  COMPACT_TOUCH Ana Kuralları                                │
            │  ─────────────────────────────────────────────────────────  │
            │  ① Tüm tıklanabilir öğeler → min yükseklik 60px+           │
            │  ② İkincil / dekoratif widget'lar → hide()                 │
            │  ③ Tab isimleri kısaltıldı (mixin halleder)                │
            │  ④ Gizlenen widget'lar hide() ile gizlenir,               │
            │     show() ile geri getirilebilir (LARGE_TV için korunur)  │
            └─────────────────────────────────────────────────────────────┘
        """
        # ── Temel: mixin'in bilinen attribute listelerini tara ───────────────
        super()._adapt_for_compact_touch(profile)  # type: ignore[misc]

        btn_h = profile.touch_safe_btn_height  # örn. 60–64 px

        # ── 1. Projeye Özgü Butonlar ─────────────────────────────────────────
        #   (HardwareAwareMixin'in listesinde OLMAYAN ek butonlar buraya)
        _extra_btns = (
            "ai_calculate_btn",           # AI hesaplama butonu
            "ai_start_btn",               # AI seans başlat
            "ai_stop_btn",                # AI seans durdur
            "btn_reset_pwms",             # Tüm bobinleri sıfırla
        )
        for attr in _extra_btns:
            btn = getattr(self, attr, None)
            if btn is not None:
                btn.setMinimumHeight(btn_h)

        # ── 2. AI Tab SpinBox / ComboBox öğeleri ─────────────────────────────
        _ai_combos = ("ai_patient_combo", "ai_target_combo")
        for attr in _ai_combos:
            cb = getattr(self, attr, None)
            if cb:
                cb.setMinimumHeight(btn_h - 4)

        # ── 3. Gizlenecek İkincil Widget'lar ─────────────────────────────────
        #
        # GEREKÇE: Küçük ekranda her piksel değerlidir.
        # Klinik iş akışı açısından kritik olmayan bilgi ve dekorasyon
        # öğeleri gizlenerek terapist için yeterli tıklama alanı sağlanır.
        #
        # ŞEMALASTIRİLMIŞ KURAL:
        #   • Göster  → Hasta seçimi, Tedavi kontrolü, Bobin durumu
        #   • Gizle   → Alt başlıklar, AI açıklama metni, büyük parametre
        #               tablosu butonu, progress label (kısa ekranda çakışır)
        #
        _extra_hide = (
            # --- Header bölümü ---
            "status_subtext",           # "Tüm sistemler çalışıyor" alt başlığı
            "patient_info_label",       # Hasta bilgisi etiketi (menüde zaten var)
            # --- Otomatik Tab ---
            "progress_label",           # "Seans başlatılmadı" bilgi etiketi
            # --- AI Tab ---
            "ai_message_label",         # Uzun AI açıklama metni
            "ai_patient_info_label",    # AI hasta bilgi etiketi (comboda var)
            # --- Genel ---
            "param_table_button",       # Büyük parametre tablosu butonu
        )
        for attr in _extra_hide:
            widget = getattr(self, attr, None)
            if widget is not None:
                widget.hide()

        # ── 4. remaining_time_label — zaten None başlıyor, ek koruma ─────────
        # progress_label gizlendi; remaining_time_label açık kalabilir (küçük)
        remaining = getattr(self, "remaining_time_label", None)
        if remaining is not None:
            remaining.setStyleSheet(
                f"font-size: {profile.small_font_pt}pt; "
                "color: rgba(255,255,255,0.9); font-weight: 600;"
            )

        logger.debug(
            "COMPACT_TOUCH UCW override uygulandı: btn_h=%d", btn_h
        )

    # =========================================================================
    # OVERRIDE 3 — LARGE_TV  (>32 inç Büyük Ekran TV)
    # =========================================================================

    def _adapt_for_large_tv(self, profile) -> None:
        """
        UnifiedControlWindow — Büyük ekran TV uyarlamaları.

        super() çağrısı HardwareAwareMixin'in bilinen attribute listelerini
        tara (genel butonlar, status_text, progress/countdown etiketleri).
        Buraya SADECE o listede olmayan ek widget'lar eklenir.

        Strateji:
            ┌──────────────────────────────────────────────────────────────┐
            │  LARGE_TV Ana Kuralları                                      │
            │  ──────────────────────────────────────────────────────────  │
            │  ① Font boyutları uzaktan okunabilir seviyeye çıkarılır     │
            │  ② Buton yükseklikleri artırılır                            │
            │  ③ Ek padding ile widget'lar sıkışık görünmez               │
            │  ④ ComboBox / SpinBox'lar da büyütülür                     │
            │  ⑤ COMPACT'te gizlenen widget'lar geri gösterilir          │
            └──────────────────────────────────────────────────────────────┘
        """
        # ── Temel: mixin'in bilinen listelerini tara ─────────────────────────
        super()._adapt_for_large_tv(profile)  # type: ignore[misc]

        btn_h   = profile.min_button_height  # örn. 56–80 px
        f_title = profile.title_font_pt      # örn. 18 pt
        f_base  = profile.base_font_pt       # örn. 13 pt
        f_small = profile.small_font_pt      # örn. 11 pt

        # ── 1. AI Tab Butonları ───────────────────────────────────────────────
        _ai_btns = ("ai_calculate_btn", "ai_start_btn", "ai_stop_btn")
        for attr in _ai_btns:
            btn = getattr(self, attr, None)
            if btn is not None:
                btn.setMinimumHeight(btn_h)
                btn.setStyleSheet(
                    btn.styleSheet()
                    + f"\nQPushButton {{ font-size: {f_base}pt; }}"
                )

        # ── 2. AI Öneri Değer Etiketleri (büyük ve kalın) ────────────────────
        _ai_value_labels = {
            "ai_freq_value":      f"color:#6cffb0; font-size:{f_title}pt; font-weight:700;",
            "ai_intensity_value": f"color:#6cffb0; font-size:{f_title}pt; font-weight:700;",
            "ai_duration_value":  f"color:#6cffb0; font-size:{f_title}pt; font-weight:700;",
        }
        for attr, style in _ai_value_labels.items():
            lbl = getattr(self, attr, None)
            if lbl:
                lbl.setStyleSheet(style)

        # ── 3. AI Açıklama Metni — TV'de büyük ve okunabilir olmalı ──────────
        ai_msg = getattr(self, "ai_message_label", None)
        if ai_msg is not None:
            ai_msg.show()  # COMPACT'te gizlenmiş olabilir, TV'de göster
            ai_msg.setStyleSheet(
                f"color: rgba(255,255,255,0.7); font-size: {f_small}pt; "
                f"font-style: italic;"
            )
            ai_msg.setFont(QFont("Segoe UI", f_small))

        # ── 4. Hasta Bilgisi Etiketleri ───────────────────────────────────────
        _patient_labels = {
            "patient_info_label":    f"color:#fff; font-size:{f_base}pt; font-weight:700;",
            "ai_patient_info_label": f"color:#ccc; font-size:{f_small}pt;",
        }
        for attr, style in _patient_labels.items():
            lbl = getattr(self, attr, None)
            if lbl:
                lbl.show()  # COMPACT'te gizlenmiş olabilir
                lbl.setStyleSheet(style)

        # ── 5. Kalan Süre / İlerleme Etiketleri ──────────────────────────────
        #   (HardwareAwareMixin progress_label'ı halleder;
        #    remaining_time_label UCW'a özgüdür)
        remaining = getattr(self, "remaining_time_label", None)
        if remaining is not None:
            remaining.show()
            remaining.setStyleSheet(
                f"color: #6cffb0; font-size: {f_title}pt; font-weight: 700;"
            )
            remaining.setFont(QFont("Segoe UI", f_title, QFont.Weight.Bold))

        # ── 6. Progress Label ─────────────────────────────────────────────────
        progress_lbl = getattr(self, "progress_label", None)
        if progress_lbl is not None:
            progress_lbl.show()
            progress_lbl.setStyleSheet(
                f"color: rgba(255,255,255,0.8); font-size: {f_base}pt;"
            )

        # ── 7. Alt Başlık (status_subtext) ────────────────────────────────────
        subtext = getattr(self, "status_subtext", None)
        if subtext is not None:
            subtext.show()
            subtext.setStyleSheet(
                f"color: rgba(255,255,255,0.6); font-size: {f_base}pt;"
            )

        # ── 8. Param Tablosu Butonu ───────────────────────────────────────────
        param_btn = getattr(self, "param_table_button", None)
        if param_btn is not None:
            param_btn.show()
            param_btn.setMinimumHeight(btn_h - 6)
            param_btn.setStyleSheet(
                param_btn.styleSheet()
                + f"\nQPushButton {{ font-size: {f_small}pt; }}"
            )

        # ── 9. Sıfırlama Butonu ───────────────────────────────────────────────
        reset_btn = getattr(self, "btn_reset_pwms", None)
        if reset_btn is not None:
            reset_btn.setMinimumHeight(btn_h)
            reset_btn.setStyleSheet(
                reset_btn.styleSheet()
                + f"\nQPushButton {{ font-size: {f_base}pt; }}"
            )

        # ── 10. AI Tab ComboBox'ları ──────────────────────────────────────────
        tv_cb_h = max(btn_h - 4, 52)
        for attr in ("ai_patient_combo", "ai_target_combo"):
            cb = getattr(self, attr, None)
            if cb:
                cb.setMinimumHeight(tv_cb_h)

        # ── 11. Tab başlıklarını TV için büyüt ────────────────────────────────
        tab_widget = getattr(self, "tab_widget", None)
        if tab_widget is not None:
            tab_bar = tab_widget.tabBar()
            if tab_bar:
                font = tab_bar.font()
                font.setPointSize(f_small)
                font.setBold(True)
                tab_bar.setFont(font)

        logger.debug(
            "LARGE_TV UCW override uygulandı: btn_h=%d, f_title=%dpt, f_base=%dpt",
            btn_h, f_title, f_base,
        )



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
        s10 = _rpt(10)
        s9  = _rpt(9)
        s8  = _rpt(8)
        return f"""
        /* Sekme Başlıkları (QTabBar) Kompakt ve Adaptif Tasarımı */
        QTabBar::tab {{
            padding: 6px 16px;
            font-size: {s10}pt;
            font-weight: 600;
            min-height: 28px;
        }}
        
        /* Coil Status LED - Property Selector (Performance Fix) */
        QLabel[status_led="running"] {{
            color: #22c55e;
            font-size: {s9}pt;
        }}
        QLabel[status_led="stopped"] {{
            color: #ef4444;
            font-size: {s9}pt;
        }}
        
        /* Coil Status Container - Property Selector (Performance Fix) */
        QWidget[status_container="running"] {{
            background: rgba(34, 197, 94, 0.1);
            border-radius: 12px;
            border: 1px solid rgba(34, 197, 94, 0.3);
        }}
        QWidget[status_container="stopped"] {{
            background: rgba(239, 68, 68, 0.1);
            border-radius: 12px;
            border: 1px solid rgba(239, 68, 68, 0.3);
        }}
        
        /* Connection Status Label - Property Selector (Performance Fix #1) */
        QLabel[conn_status="connected"] {{
            color: #22c55e;
            font-size: {s9}pt;
            font-weight: bold;
        }}
        QLabel[conn_status="disconnected"] {{
            color: #ef4444;
            font-size: {s9}pt;
            font-weight: bold;
        }}
        QLabel[conn_status="unknown"] {{
            color: #f59e0b;
            font-size: {s9}pt;
            font-weight: bold;
        }}
        
        /* Temperature Status Label - Property Selector (Performance Fix) */
        QLabel[temp_status="critical"] {{
            color: #ef4444;
            font-size: {s8}pt;
            font-weight: 600;
        }}
        QLabel[temp_status="warning"] {{
            color: #f59e0b;
            font-size: {s8}pt;
            font-weight: 600;
        }}
        QLabel[temp_status="normal"] {{
            color: #10b981;
            font-size: {s8}pt;
            font-weight: 600;
        }}
        """
        
    def _init_ui(self):
        """Ana kullanıcı arayüzünü oluştur"""
        # Ana widget ve layout
        main_widget = QWidget(self)
        self.setCentralWidget(main_widget)
        
        main_layout = QVBoxLayout(main_widget)
        # Adaptif ve kompakt dış boşluklar
        _m12 = _sv_ucw(12); _sp12 = _sv_ucw(12)
        main_layout.setContentsMargins(_m12, _m12, _m12, _m12)
        main_layout.setSpacing(_sp12)
        
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

        # AI Pro Tab (Dataset 1)
        self.ai_pro_tab = self._create_ai_pro_tab()
        ai_pro_tab_icon = QIcon(get_image_path("activity.svg")) # Reusing the icon
        self.tab_widget.addTab(self.ai_pro_tab, ai_pro_tab_icon, " AI Pro")
        
        # Cat Disease Tab (Lazy)
        self.cat_disease_tab = QWidget()
        self.cat_disease_layout = QVBoxLayout(self.cat_disease_tab)
        loading_label1 = QLabel("Modül Yükleniyor...")
        loading_label1.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cat_disease_layout.addWidget(loading_label1)
        self.cat_disease_loaded = False
        disease_tab_icon = QIcon(get_image_path("activity.svg")) 
        self.tab_widget.addTab(self.cat_disease_tab, disease_tab_icon, " Kedi Hastalık Analizi")

        # Feline Reticulocytes Tab (Lazy)
        self.feline_reticulocytes_tab = QWidget()
        self.feline_retic_layout = QVBoxLayout(self.feline_reticulocytes_tab)
        loading_label2 = QLabel("Modül Yükleniyor...")
        loading_label2.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.feline_retic_layout.addWidget(loading_label2)
        self.feline_retic_loaded = False
        retic_tab_icon = QIcon(get_image_path("activity.svg")) 
        self.tab_widget.addTab(self.feline_reticulocytes_tab, retic_tab_icon, " Kedi Retikülosit Sayımı")

        # Cat Vision Tab (Lazy)
        self.cat_vision_tab = QWidget()
        self.cat_vision_layout = QVBoxLayout(self.cat_vision_tab)
        loading_label3 = QLabel("Modül Yükleniyor...")
        loading_label3.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cat_vision_layout.addWidget(loading_label3)
        self.cat_vision_loaded = False
        cat_vision_icon = QIcon(get_image_path("activity.svg"))
        self.tab_widget.addTab(self.cat_vision_tab, cat_vision_icon, " Kedi Görüntü Analizi")
        
        # Tab değişikliği sinyali
        self.tab_widget.currentChanged.connect(self._on_tab_changed)
        
        main_layout.addWidget(self.tab_widget)
        
        # Status bar
        self.status_bar = QStatusBar()
        self.status_bar.setStyleSheet(_ss_ucw("""
            QStatusBar {
                background: rgba(0, 0, 0, 0.3);
                color: rgba(255, 255, 255, 0.8);
                border-top: 1px solid rgba(255, 255, 255, 0.1);
                padding: 8px;
            }
        """))
        self.status_bar.showMessage("Sistem hazır")
        self.setStatusBar(self.status_bar)
        self._apply_device_profile_adaptations()
        apply_responsive_widget_scaling(self)  # [RESP-PATCHED]
        
    def _create_header(self, parent_layout):
        """Modern ve kompakt header bölümünü oluştur"""
        header_frame = QFrame()
        header_frame.setProperty("class", "card-elevated")
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(
            _sv_ucw(16), _sv_ucw(10), _sv_ucw(16), _sv_ucw(10))
        header_layout.setSpacing(_sv_ucw(16))
        
        # Sol taraf - Başlık ve açıklama
        left_layout = QVBoxLayout()
        left_layout.setSpacing(_sv_ucw(4))
        
        # Modern başlık tasarımı
        title_container = QWidget()
        title_container_layout = QHBoxLayout(title_container)
        title_container_layout.setContentsMargins(0, 0, 0, 0)
        title_container_layout.setSpacing(_sv_ucw(10))
        
        # Icon
        icon_label = QLabel()
        icon_label.setPixmap(QIcon(get_image_path("intensity.svg")).pixmap(_rpx(22), _rpx(22)))
        _icon_sz = _rpx(32)
        icon_label.setStyleSheet(f"""
            color: #6366f1;
            background: rgba(99, 102, 241, 0.1);
            border-radius: 10px;
            padding: 6px;
            min-width: {_icon_sz}px;
            max-width: {_icon_sz}px;
            min-height: {_icon_sz}px;
            max-height: {_icon_sz}px;
        """)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Başlık ve alt başlık
        title_text_layout = QVBoxLayout()
        title_text_layout.setSpacing(2)
        
        title_label = QLabel("PEMF Kontrol Merkezi")
        title_label.setStyleSheet(f"""
            font-size: 18pt;
            font-weight: 800;
            color: white;
            margin: 0;
            letter-spacing: -0.5px;
        """)
        
        subtitle_label = QLabel("Birleşik manuel ve otomatik seans kontrol sistemi")
        subtitle_label.setStyleSheet(f"""
            font-size: 10pt;
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
        
        # Modern ve kompakt sistem durumu
        status_widget = QWidget()
        status_layout = QHBoxLayout(status_widget)
        status_layout.setContentsMargins(
            _sv_ucw(12), _sv_ucw(8), _sv_ucw(12), _sv_ucw(8))
        status_layout.setSpacing(_sv_ucw(10))
        
        # Status icon
        status_icon_container = QWidget()
        _sz_ic = _rpx(26)
        status_icon_container.setFixedSize(_sz_ic, _sz_ic)
        status_icon_container.setStyleSheet(f"""
            background: rgba(34, 197, 94, 0.2);
            border-radius: 13px;
            border: 2px solid rgba(34, 197, 94, 0.4);
        """)
        
        status_icon_layout = QHBoxLayout(status_icon_container)
        status_icon_layout.setContentsMargins(0, 0, 0, 0)
        
        self.status_dot = QLabel("✓")
        self.status_dot.setStyleSheet(
            f"color: #22c55e; font-size: 10pt; font-weight: bold;")
        self.status_dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status_icon_layout.addWidget(self.status_dot)
        
        # Status text
        status_text_layout = QVBoxLayout()
        status_text_layout.setSpacing(2)
        
        self.status_text = QLabel("Sistem Hazır")
        self.status_text.setStyleSheet(
            f"color: #ffffff; font-size: 10pt; font-weight: 700;")
        
        self.status_subtext = QLabel("Tüm sistemler çalışıyor")
        self.status_subtext.setStyleSheet(
            f"color: rgba(255, 255, 255, 0.6); font-size: 8pt;")
        
        status_text_layout.addWidget(self.status_text)
        status_text_layout.addWidget(self.status_subtext)
        
        status_layout.addWidget(status_icon_container)
        status_layout.addLayout(status_text_layout)
        status_layout.addStretch()
        
        status_widget.setStyleSheet(_ss_ucw("""
            background: rgba(34, 197, 94, 0.08);
            border-radius: 14px;
            border: 1px solid rgba(34, 197, 94, 0.2);
        """))
        
        # Modern ve kompakt hasta bilgileri
        self.patient_info_widget = QWidget()
        patient_info_layout = QHBoxLayout(self.patient_info_widget)
        patient_info_layout.setContentsMargins(
            _sv_ucw(12), _sv_ucw(8), _sv_ucw(12), _sv_ucw(8))
        patient_info_layout.setSpacing(_sv_ucw(10))
        
        # Parametre tablosu butonu (hasta bilgisinin solunda)
        self.param_table_button = QPushButton("📊 Parametre Tablosu")
        self.param_table_button.setStyleSheet(_ss_ucw(f"""
            QPushButton {{
                background: rgba(102, 126, 234, 0.15);
                border: 1px solid rgba(102, 126, 234, 0.3);
                border-radius: 10px;
                padding: 6px 12px;
                color: #ffffff;
                font-size: 9pt;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: rgba(102, 126, 234, 0.25);
                border: 1px solid rgba(102, 126, 234, 0.5);
            }}
            QPushButton:pressed {{
                background: rgba(102, 126, 234, 0.35);
            }}
        """))
        self.param_table_button.clicked.connect(self.show_parameter_table)
        patient_info_layout.addWidget(self.param_table_button)
        
        # Patient icon
        patient_icon_container = QWidget()
        patient_icon_container.setFixedSize(_sz_ic, _sz_ic)
        patient_icon_container.setStyleSheet(f"""
            background: rgba(59, 130, 246, 0.2);
            border-radius: 13px;
            border: 2px solid rgba(59, 130, 246, 0.4);
        """)
        
        patient_icon_layout = QHBoxLayout(patient_icon_container)
        patient_icon_layout.setContentsMargins(0, 0, 0, 0)
        
        patient_icon = QLabel()
        patient_icon.setPixmap(QIcon(get_image_path("pemf_heart_icon.png")).pixmap(_rpx(14), _rpx(14)))
        patient_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        patient_icon_layout.addWidget(patient_icon)
        
        # Patient info text
        patient_text_layout = QVBoxLayout()
        patient_text_layout.setSpacing(2)
        
        self.patient_info_label = QLabel("Hasta Bilgisi")
        self.patient_info_label.setStyleSheet(
            f"color: #ffffff; font-size: 10pt; font-weight: 700;")
        
        self.patient_status_label = QLabel("Hasta kaydedilmedi")
        self.patient_status_label.setStyleSheet(
            f"color: rgba(255, 255, 255, 0.6); font-size: 8pt;")
        
        patient_text_layout.addWidget(self.patient_info_label)
        patient_text_layout.addWidget(self.patient_status_label)
        
        patient_info_layout.addWidget(patient_icon_container)
        patient_info_layout.addLayout(patient_text_layout)
        patient_info_layout.addStretch()
        
        self.patient_info_widget.setStyleSheet(_ss_ucw("""
            background: rgba(59, 130, 246, 0.08);
            border-radius: 14px;
            border: 1px solid rgba(59, 130, 246, 0.2);
        """))
        
        right_layout.addWidget(status_widget)
        right_layout.addWidget(self.patient_info_widget)
        header_layout.addLayout(right_layout)
        
        parent_layout.addWidget(header_frame)
        
    def _create_automatic_tab(self):
        """Otomatik mod tab'ını oluştur"""
        tab_widget = QWidget()
        tab_layout = QVBoxLayout(tab_widget)
        _m24t = _sv_ucw(24); _sp24t = _sv_ucw(24)
        tab_layout.setContentsMargins(_m24t, _m24t, _m24t, _m24t)
        tab_layout.setSpacing(_sp24t)
        
        # Scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent; border: none;")
        
        container = QWidget()
        scroll.setWidget(container)
        content_layout = QVBoxLayout(container)
        content_layout.setContentsMargins(0, 0, _sv_ucw(20), 0)
        content_layout.setSpacing(_sv_ucw(20))
        
        # Hasta Seçimi (YENİ - Otomatik kontrol kısmının üstüne eklendi)
        patient_group = QGroupBox()
        patient_group.setTitle("👤 Hasta Seçimi")
        patient_layout = QVBoxLayout(patient_group)
        patient_layout.setContentsMargins(
            _sv_ucw(24), _sv_ucw(28), _sv_ucw(24), _sv_ucw(24))
        patient_layout.setSpacing(_sv_ucw(16))
        
        # Hasta seçimi için görsel container
        patient_selection_container = QWidget()
        patient_selection_container.setStyleSheet(_ss_ucw(f"""
            QWidget {{
                background: rgba(139, 92, 246, 0.08);
                border: 1px solid rgba(139, 92, 246, 0.2);
                border-radius: 12px;
                padding: 12px;
            }}
        """))
        patient_selection_layout = QHBoxLayout(patient_selection_container)
        patient_selection_layout.setContentsMargins(_sv_ucw(16), _sv_ucw(12), _sv_ucw(16), _sv_ucw(12))
        patient_selection_layout.setSpacing(_sv_ucw(12))
        
        # Hasta ikonu
        patient_icon_label = QLabel("👤")
        patient_icon_label.setStyleSheet(_ss_ucw(f"""
            font-size: 16pt;
            color: #8b5cf6;
            background: rgba(139, 92, 246, 0.15);
            border-radius: 8px;
            padding: 8px;
            min-width: 36px;
            max-width: 36px;
            min-height: 36px;
            max-height: 36px;
        """))
        patient_icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Combo box container
        patient_combo_container = QWidget()
        patient_combo_layout = QVBoxLayout(patient_combo_container)
        patient_combo_layout.setContentsMargins(0, 0, 0, 0)
        patient_combo_layout.setSpacing(_sv_ucw(4))
        
        patient_label = QLabel("Hasta Seçin:")
        patient_label.setStyleSheet(_ss_ucw(f"font-weight: 600; color: #8b5cf6; font-size: 11pt;"))
        
        self.patient_combo = QComboBox()
        self.patient_combo.setStyleSheet(_ss_ucw(f"""
            QComboBox {{
                background: rgba(255, 255, 255, 0.12);
                border: 2px solid rgba(139, 92, 246, 0.3);
                border-radius: 8px;
                padding: 10px 12px;
                font-size: 11pt;
                color: #ffffff;
                min-height: {_sv_ucw(40, min_ratio=0.7, max_ratio=1.3)}px;
                font-weight: 500;
            }}
            QComboBox:focus {{
                border: 2px solid rgba(139, 92, 246, 0.8);
                background: rgba(255, 255, 255, 0.18);
            }}
        """))
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
        patient_actions_layout.setSpacing(_sv_ucw(8))
        
        # Seçili hastayı sil butonu
        self.delete_selected_patient_btn = QPushButton("Seçili Hastayı Sil")
        self.delete_selected_patient_btn.setStyleSheet(_ss_ucw(f"""
            QPushButton {{
                background: rgba(239, 68, 68, 0.2);
                border: 2px solid rgba(239, 68, 68, 0.4);
                border-radius: 8px;
                padding: 8px 16px;
                font-size: 10pt;
                color: #ffffff;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: rgba(239, 68, 68, 0.3);
                border: 2px solid rgba(239, 68, 68, 0.6);
            }}
            QPushButton:pressed {{
                background: rgba(239, 68, 68, 0.4);
            }}
            QPushButton:disabled {{
                background: rgba(239, 68, 68, 0.1);
                border: 2px solid rgba(239, 68, 68, 0.2);
                color: rgba(255, 255, 255, 0.4);
            }}
        """))
        self.delete_selected_patient_btn.clicked.connect(self._delete_selected_patient)
        self.delete_selected_patient_btn.setEnabled(False)  # Başlangıçta devre dışı
        
        # Tümünü sil butonu
        self.delete_all_patients_btn = QPushButton("Tümünü Sil")
        self.delete_all_patients_btn.setStyleSheet(_ss_ucw(f"""
            QPushButton {{
                background: rgba(220, 38, 38, 0.2);
                border: 2px solid rgba(220, 38, 38, 0.4);
                border-radius: 8px;
                padding: 8px 16px;
                font-size: 10pt;
                color: #ffffff;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: rgba(220, 38, 38, 0.3);
                border: 2px solid rgba(220, 38, 38, 0.6);
            }}
            QPushButton:pressed {{
                background: rgba(220, 38, 38, 0.4);
            }}
            QPushButton:disabled {{
                background: rgba(220, 38, 38, 0.1);
                border: 2px solid rgba(220, 38, 38, 0.2);
                color: rgba(255, 255, 255, 0.4);
            }}
        """))
        self.delete_all_patients_btn.clicked.connect(self._delete_all_patients)
        
        patient_actions_layout.addWidget(self.delete_selected_patient_btn)
        patient_actions_layout.addWidget(self.delete_all_patients_btn)
        patient_actions_layout.addStretch()
        
        patient_layout.addWidget(patient_actions_container)
        content_layout.addWidget(patient_group)

        # Görsel ayırıcı
        separator0 = QFrame()
        separator0.setFrameShape(QFrame.Shape.HLine)
        separator0.setStyleSheet("background: rgba(255, 255, 255, 0.1); margin: 8px 0;")
        content_layout.addWidget(separator0)
        
        # Tedavi Hedefi Seçimi
        target_group = QGroupBox()
        target_group.setTitle("🎯 Seans Hedefi")
        target_layout = QVBoxLayout(target_group)
        target_layout.setContentsMargins(_sv_ucw(24), _sv_ucw(28), _sv_ucw(24), _sv_ucw(24))
        target_layout.setSpacing(_sv_ucw(16))
        
        # Tedavi hedefi seçimi için görsel container
        target_selection_container = QWidget()
        target_selection_container.setStyleSheet(_ss_ucw(f"""
            QWidget {{
                background: rgba(99, 102, 241, 0.08);
                border: 1px solid rgba(99, 102, 241, 0.2);
                border-radius: 12px;
                padding: 12px;
            }}
        """))
        target_selection_layout = QHBoxLayout(target_selection_container)
        target_selection_layout.setContentsMargins(_sv_ucw(16), _sv_ucw(12), _sv_ucw(16), _sv_ucw(12))
        target_selection_layout.setSpacing(_sv_ucw(12))
        
        # Tedavi hedefi ikonu
        target_icon_label = QLabel("🏥")
        target_icon_label.setStyleSheet(_ss_ucw(f"""
            font-size: 16pt;
            color: #6366f1;
            background: rgba(99, 102, 241, 0.15);
            border-radius: 8px;
            padding: 8px;
            min-width: 36px;
            max-width: 36px;
            min-height: 36px;
            max-height: 36px;
        """))
        target_icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Combo box container
        combo_container = QWidget()
        combo_layout = QVBoxLayout(combo_container)
        combo_layout.setContentsMargins(0, 0, 0, 0)
        combo_layout.setSpacing(_sv_ucw(4))
        
        target_label = QLabel("Seans Hedefi Seçin:")
        target_label.setStyleSheet(_ss_ucw(f"font-weight: 600; color: #6366f1; font-size: 11pt;"))
        
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
        self.target_combo.setStyleSheet(_ss_ucw(f"""
            QComboBox {{
                background: rgba(255, 255, 255, 0.12);
                border: 2px solid rgba(99, 102, 241, 0.3);
                border-radius: 8px;
                padding: 10px 12px;
                font-size: 11pt;
                color: #ffffff;
                min-height: {_sv_ucw(40, min_ratio=0.7, max_ratio=1.3)}px;
                font-weight: 500;
            }}
            QComboBox:focus {{
                border: 2px solid rgba(99, 102, 241, 0.8);
                background: rgba(255, 255, 255, 0.18);
            }}
        """))
        
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
        auto_params_layout.setContentsMargins(_sv_ucw(24), _sv_ucw(28), _sv_ucw(24), _sv_ucw(24))
        auto_params_layout.setSpacing(_sv_ucw(16))
        
        # Frekans parametresi
        freq_container = QWidget()
        freq_container.setStyleSheet(_ss_ucw(f"""
            QWidget {{
                background: rgba(99, 102, 241, 0.08);
                border: 1px solid rgba(99, 102, 241, 0.2);
                border-radius: 12px;
                padding: 12px;
            }}
        """))
        freq_layout = QHBoxLayout(freq_container)
        freq_layout.setContentsMargins(_sv_ucw(16), _sv_ucw(12), _sv_ucw(16), _sv_ucw(12))
        freq_layout.setSpacing(_sv_ucw(12))
        
        freq_icon = QLabel("📊")
        freq_icon.setStyleSheet(_ss_ucw(f"""
            font-size: 14pt;
            background: rgba(99, 102, 241, 0.15);
            border-radius: 8px;
            padding: 8px;
            min-width: 32px;
            max-width: 32px;
            min-height: 32px;
            max-height: 32px;
        """))
        freq_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        freq_content = QWidget()
        freq_content_layout = QVBoxLayout(freq_content)
        freq_content_layout.setContentsMargins(0, 0, 0, 0)
        freq_content_layout.setSpacing(_sv_ucw(4))
        
        freq_label = QLabel("Frekans:")
        freq_label.setStyleSheet(_ss_ucw(f"font-weight: 600; color: #6366f1; font-size: 11pt;"))
        
        self.auto_frequency_spin = NoWheelDoubleSpinBox()
        self.auto_frequency_spin.setRange(0.1, 50000.0)
        self.auto_frequency_spin.setValue(10.0)
        self.auto_frequency_spin.setSuffix(" Hz")
        self.auto_frequency_spin.setStyleSheet(_ss_ucw(f"""
            QDoubleSpinBox {{
                background: rgba(255, 255, 255, 0.12);
                border: 2px solid rgba(99, 102, 241, 0.3);
                border-radius: 8px;
                padding: 8px 12px;
                font-size: 10pt;
                color: #ffffff;
                min-height: {_sv_ucw(36, min_ratio=0.7, max_ratio=1.3)}px;
                font-weight: 500;
            }}
            QDoubleSpinBox:focus {{
                border: 2px solid rgba(99, 102, 241, 0.8);
                background: rgba(255, 255, 255, 0.18);
            }}
        """))
        
        freq_content_layout.addWidget(freq_label)
        freq_content_layout.addWidget(self.auto_frequency_spin)
        
        freq_layout.addWidget(freq_icon)
        freq_layout.addWidget(freq_content, stretch=1)
        
        auto_params_layout.addWidget(freq_container)
        
        # Süre parametresi
        duration_container = QWidget()
        duration_container.setStyleSheet(_ss_ucw(f"""
            QWidget {{
                background: rgba(16, 185, 129, 0.08);
                border: 1px solid rgba(16, 185, 129, 0.2);
                border-radius: 12px;
                padding: 12px;
            }}
        """))
        duration_layout = QHBoxLayout(duration_container)
        duration_layout.setContentsMargins(_sv_ucw(16), _sv_ucw(12), _sv_ucw(16), _sv_ucw(12))
        duration_layout.setSpacing(_sv_ucw(12))
        
        duration_icon = QLabel("⏱️")
        duration_icon.setStyleSheet(_ss_ucw(f"""
            font-size: 14pt;
            background: rgba(16, 185, 129, 0.15);
            border-radius: 8px;
            padding: 8px;
            min-width: 32px;
            max-width: 32px;
            min-height: 32px;
            max-height: 32px;
        """))
        duration_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        duration_content = QWidget()
        duration_content_layout = QVBoxLayout(duration_content)
        duration_content_layout.setContentsMargins(0, 0, 0, 0)
        duration_content_layout.setSpacing(_sv_ucw(4))
        
        duration_label = QLabel("Süre:")
        duration_label.setStyleSheet(_ss_ucw(f"font-weight: 600; color: #10b981; font-size: 11pt;"))
        
        self.auto_duration_spin = NoWheelSpinBox()
        self.auto_duration_spin.setRange(1, 9999)
        self.auto_duration_spin.setValue(30)
        self.auto_duration_spin.setSuffix(" dakika")
        self.auto_duration_spin.setStyleSheet(_ss_ucw(f"""
            QSpinBox {{
                background: rgba(255, 255, 255, 0.12);
                border: 2px solid rgba(16, 185, 129, 0.3);
                border-radius: 8px;
                padding: 8px 12px;
                font-size: 10pt;
                color: #ffffff;
                min-height: {_sv_ucw(36, min_ratio=0.7, max_ratio=1.3)}px;
                font-weight: 500;
            }}
            QSpinBox:focus {{
                border: 2px solid rgba(16, 185, 129, 0.8);
                background: rgba(255, 255, 255, 0.18);
            }}
        """))
        
        duration_content_layout.addWidget(duration_label)
        duration_content_layout.addWidget(self.auto_duration_spin)
        
        duration_layout.addWidget(duration_icon)
        duration_layout.addWidget(duration_content, stretch=1)
        
        auto_params_layout.addWidget(duration_container)
        
        # Yoğunluk parametresi
        intensity_container = QWidget()
        intensity_container.setStyleSheet(_ss_ucw(f"""
            QWidget {{
                background: rgba(245, 158, 11, 0.08);
                border: 1px solid rgba(245, 158, 11, 0.2);
                border-radius: 12px;
                padding: 12px;
            }}
        """))
        intensity_layout = QHBoxLayout(intensity_container)
        intensity_layout.setContentsMargins(_sv_ucw(16), _sv_ucw(12), _sv_ucw(16), _sv_ucw(12))
        intensity_layout.setSpacing(_sv_ucw(12))
        
        intensity_icon = QLabel("⚡")
        intensity_icon.setStyleSheet(_ss_ucw(f"""
            font-size: 14pt;
            background: rgba(245, 158, 11, 0.15);
            border-radius: 8px;
            padding: 8px;
            min-width: 32px;
            max-width: 32px;
            min-height: 32px;
            max-height: 32px;
        """))
        intensity_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        intensity_content = QWidget()
        intensity_content_layout = QVBoxLayout(intensity_content)
        intensity_content_layout.setContentsMargins(0, 0, 0, 0)
        intensity_content_layout.setSpacing(_sv_ucw(4))
        
        intensity_label = QLabel("Yoğunluk:")
        intensity_label.setStyleSheet(_ss_ucw(f"font-weight: 600; color: #f59e0b; font-size: 11pt;"))
        
        self.auto_intensity_spin = NoWheelDoubleSpinBox()  # mT değerleri için ondalık gerekli
        self.auto_intensity_spin.setRange(0.1, 5.0)  # Bilimsel aralık: 0.1-5.0 mT (güvenli veteriner PEMF aralığı)
        self.auto_intensity_spin.setDecimals(1)  # 1 ondalık basamak
        self.auto_intensity_spin.setSingleStep(0.1)  # 0.1 mT artışlar
        self.auto_intensity_spin.setValue(1.0)  # Güvenli başlangıç değeri
        self.auto_intensity_spin.setSuffix(" mT")
        self.auto_intensity_spin.setStyleSheet(_ss_ucw(f"""
            QDoubleSpinBox {{
                background: rgba(255, 255, 255, 0.12);
                border: 2px solid rgba(245, 158, 11, 0.3);
                border-radius: 8px;
                padding: 8px 12px;
                font-size: 10pt;
                color: #ffffff;
                min-height: {_sv_ucw(36, min_ratio=0.7, max_ratio=1.3)}px;
                font-weight: 500;
            }}
            QSpinBox:focus {{
                border: 2px solid rgba(245, 158, 11, 0.8);
                background: rgba(255, 255, 255, 0.18);
            }}
        """))
        
        intensity_content_layout.addWidget(intensity_label)
        intensity_content_layout.addWidget(self.auto_intensity_spin)
        
        intensity_layout.addWidget(intensity_icon)
        intensity_layout.addWidget(intensity_content, stretch=1)
        
        auto_params_layout.addWidget(intensity_container)
        
        # Duty Cycle parametresi
        duty_cycle_container = QWidget()
        duty_cycle_container.setStyleSheet(_ss_ucw(f"""
            QWidget {{
                background: rgba(139, 92, 246, 0.08);
                border: 1px solid rgba(139, 92, 246, 0.2);
                border-radius: 12px;
                padding: 12px;
            }}
        """))
        duty_cycle_layout = QHBoxLayout(duty_cycle_container)
        duty_cycle_layout.setContentsMargins(_sv_ucw(16), _sv_ucw(12), _sv_ucw(16), _sv_ucw(12))
        duty_cycle_layout.setSpacing(_sv_ucw(12))
        
        duty_cycle_icon = QLabel("🔄")
        duty_cycle_icon.setStyleSheet(_ss_ucw(f"""
            font-size: 14pt;
            background: rgba(139, 92, 246, 0.15);
            border-radius: 8px;
            padding: 8px;
            min-width: 32px;
            max-width: 32px;
            min-height: 32px;
            max-height: 32px;
        """))
        duty_cycle_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        duty_cycle_content = QWidget()
        duty_cycle_content_layout = QVBoxLayout(duty_cycle_content)
        duty_cycle_content_layout.setContentsMargins(0, 0, 0, 0)
        duty_cycle_content_layout.setSpacing(_sv_ucw(4))
        
        duty_cycle_label = QLabel("Duty Cycle:")
        duty_cycle_label.setStyleSheet(_ss_ucw(f"font-weight: 600; color: #8b5cf6; font-size: 11pt;"))
        
        self.auto_duty_cycle_spin = NoWheelDoubleSpinBox()
        self.auto_duty_cycle_spin.setRange(1.0, 99.0)
        self.auto_duty_cycle_spin.setDecimals(1)
        self.auto_duty_cycle_spin.setSingleStep(0.1)
        self.auto_duty_cycle_spin.setValue(50.0)
        self.auto_duty_cycle_spin.setSuffix(" %")
        self.auto_duty_cycle_spin.setStyleSheet(_ss_ucw(f"""
            QDoubleSpinBox {{
                background: rgba(255, 255, 255, 0.12);
                border: 2px solid rgba(139, 92, 246, 0.3);
                border-radius: 8px;
                padding: 8px 12px;
                font-size: 10pt;
                color: #ffffff;
                min-height: {_sv_ucw(36, min_ratio=0.7, max_ratio=1.3)}px;
                font-weight: 500;
            }}
            QDoubleSpinBox:focus {{
                border: 2px solid rgba(139, 92, 246, 0.8);
                background: rgba(255, 255, 255, 0.18);
            }}
        """))
        
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
        auto_control_layout.setContentsMargins(_sv_ucw(24), _sv_ucw(28), _sv_ucw(24), _sv_ucw(24))
        auto_control_layout.setSpacing(_sv_ucw(16))
        
        # Başlat butonu container
        start_container = QWidget()
        start_container.setStyleSheet(_ss_ucw(f"""
            QWidget {{
                background: rgba(34, 197, 94, 0.08);
                border: 1px solid rgba(34, 197, 94, 0.2);
                border-radius: 12px;
                padding: 12px;
            }}
        """))
        start_layout = QHBoxLayout(start_container)
        start_layout.setContentsMargins(_sv_ucw(16), _sv_ucw(12), _sv_ucw(16), _sv_ucw(12))
        start_layout.setSpacing(_sv_ucw(12))
        
        start_icon = QLabel("▶️")
        start_icon.setStyleSheet(_ss_ucw(f"""
            font-size: 16pt;
            background: rgba(34, 197, 94, 0.15);
            border-radius: 8px;
            padding: 8px;
            min-width: 36px;
            max-width: 36px;
            min-height: 36px;
            max-height: 36px;
        """))
        start_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.auto_start_btn = QPushButton("Otomatik Seans Başlat")
        self.auto_start_btn.setIcon(QIcon(get_image_path("play.svg")))
        self.auto_start_btn.setProperty("class", "success")
        self.auto_start_btn.clicked.connect(self.start_automatic_treatment)
        self.auto_start_btn.setStyleSheet(_ss_ucw(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(34, 197, 94, 0.9), stop:1 rgba(21, 128, 61, 0.9));
                border: 2px solid rgba(34, 197, 94, 0.4);
                border-radius: 10px;
                color: #ffffff;
                font-size: 12pt;
                font-weight: 700;
                padding: 14px 28px;
                min-height: {_sv_ucw(40, min_ratio=0.7, max_ratio=1.3)}px;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(34, 197, 94, 1.0), stop:1 rgba(21, 128, 61, 1.0));
                border: 2px solid rgba(34, 197, 94, 0.8);
            }}
            QPushButton:pressed {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(21, 128, 61, 0.9), stop:1 rgba(15, 118, 110, 0.9));
            }}
        """))
        
        start_layout.addWidget(start_icon)
        start_layout.addWidget(self.auto_start_btn, stretch=1)
        
        auto_control_layout.addWidget(start_container)
        
        # Durdur butonu container
        stop_container = QWidget()
        stop_container.setStyleSheet(_ss_ucw(f"""
            QWidget {{
                background: rgba(239, 68, 68, 0.08);
                border: 1px solid rgba(239, 68, 68, 0.2);
                border-radius: 12px;
                padding: 12px;
            }}
        """))
        stop_layout = QHBoxLayout(stop_container)
        stop_layout.setContentsMargins(_sv_ucw(16), _sv_ucw(12), _sv_ucw(16), _sv_ucw(12))
        stop_layout.setSpacing(_sv_ucw(12))
        
        stop_icon = QLabel("⏹️")
        stop_icon.setStyleSheet(_ss_ucw(f"""
            font-size: 16pt;
            background: rgba(239, 68, 68, 0.15);
            border-radius: 8px;
            padding: 8px;
            min-width: 36px;
            max-width: 36px;
            min-height: 36px;
            max-height: 36px;
        """))
        stop_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.auto_stop_btn = QPushButton("Seans Durdur")
        self.auto_stop_btn.setIcon(QIcon(get_image_path("stop.svg")))
        self.auto_stop_btn.setProperty("class", "danger")
        self.auto_stop_btn.clicked.connect(lambda: self.stop_treatment(stop_reason='user_stopped'))
        self.auto_stop_btn.setEnabled(False)
        self.auto_stop_btn.setStyleSheet(_ss_ucw(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(239, 68, 68, 0.9), stop:1 rgba(185, 28, 28, 0.9));
                border: 2px solid rgba(239, 68, 68, 0.4);
                border-radius: 10px;
                color: #ffffff;
                font-size: 12pt;
                font-weight: 700;
                padding: 14px 28px;
                min-height: {_sv_ucw(40, min_ratio=0.7, max_ratio=1.3)}px;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(239, 68, 68, 1.0), stop:1 rgba(185, 28, 28, 1.0));
                border: 2px solid rgba(239, 68, 68, 0.8);
            }}
            QPushButton:pressed {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(185, 28, 28, 0.9), stop:1 rgba(153, 27, 27, 0.9));
            }}
            QPushButton:disabled {{
                background: rgba(255, 255, 255, 0.1);
                border-color: rgba(255, 255, 255, 0.1);
                color: rgba(255, 255, 255, 0.4);
            }}
        """))
        
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
        progress_layout.setContentsMargins(_sv_ucw(24), _sv_ucw(28), _sv_ucw(24), _sv_ucw(24))
        progress_layout.setSpacing(_sv_ucw(16))
        
        # İlerleme durumu container
        progress_container = QWidget()
        progress_container.setStyleSheet(_ss_ucw(f"""
            QWidget {{
                background: rgba(59, 130, 246, 0.08);
                border: 1px solid rgba(59, 130, 246, 0.2);
                border-radius: 12px;
                padding: 12px;
            }}
        """))
        progress_container_layout = QHBoxLayout(progress_container)
        progress_container_layout.setContentsMargins(_sv_ucw(16), _sv_ucw(12), _sv_ucw(16), _sv_ucw(12))
        progress_container_layout.setSpacing(_sv_ucw(12))
        
        # İlerleme ikonu
        progress_icon = QLabel("📊")
        progress_icon.setStyleSheet(_ss_ucw(f"""
            font-size: 16pt;
            background: rgba(59, 130, 246, 0.15);
            border-radius: 8px;
            padding: 8px;
            min-width: 36px;
            max-width: 36px;
            min-height: 36px;
            max-height: 36px;
        """))
        progress_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # İlerleme bilgileri
        progress_info_container = QWidget()
        progress_info_layout = QVBoxLayout(progress_info_container)
        progress_info_layout.setContentsMargins(0, 0, 0, 0)
        progress_info_layout.setSpacing(_sv_ucw(6))
        
        progress_title = QLabel("Seans Durumu:")
        progress_title.setStyleSheet(_ss_ucw(f"font-weight: 600; color: #3b82f6; font-size: 11pt;"))
        
        self.progress_label = QLabel("Seans başlatılmadı")
        self.progress_label.setStyleSheet(_ss_ucw(f"""
            font-size: 12pt; 
            color: rgba(255, 255, 255, 0.9);
            font-weight: 600;
            background: rgba(255, 255, 255, 0.05);
            border-radius: 6px;
            padding: 8px 12px;
        """))
        
        progress_info_layout.addWidget(progress_title)
        progress_info_layout.addWidget(self.progress_label)
        
        progress_container_layout.addWidget(progress_icon)
        progress_container_layout.addWidget(progress_info_container, stretch=1)
        
        progress_layout.addWidget(progress_container)
        
        # Kalan süre container
        time_container = QWidget()
        time_container.setStyleSheet(_ss_ucw(f"""
            QWidget {{
                background: rgba(168, 85, 247, 0.08);
                border: 1px solid rgba(168, 85, 247, 0.2);
                border-radius: 12px;
                padding: 12px;
            }}
        """))
        time_container_layout = QHBoxLayout(time_container)
        time_container_layout.setContentsMargins(_sv_ucw(16), _sv_ucw(12), _sv_ucw(16), _sv_ucw(12))
        time_container_layout.setSpacing(_sv_ucw(12))
        
        # Zaman ikonu
        time_icon = QLabel("⏰")
        time_icon.setStyleSheet(_ss_ucw(f"""
            font-size: 16pt;
            background: rgba(168, 85, 247, 0.15);
            border-radius: 8px;
            padding: 8px;
            min-width: 36px;
            max-width: 36px;
            min-height: 36px;
            max-height: 36px;
        """))
        time_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Zaman bilgileri
        time_info_container = QWidget()
        time_info_layout = QVBoxLayout(time_info_container)
        time_info_layout.setContentsMargins(0, 0, 0, 0)
        time_info_layout.setSpacing(_sv_ucw(6))
        
        time_title = QLabel("Kalan Süre:")
        time_title.setStyleSheet(_ss_ucw(f"font-weight: 600; color: #a855f7; font-size: 11pt;"))
        
        self.remaining_time_label = QLabel("--")
        self.remaining_time_label.setStyleSheet(_ss_ucw(f"""
            font-size: 12pt; 
            color: rgba(255, 255, 255, 0.9);
            font-weight: 600;
            background: rgba(255, 255, 255, 0.05);
            border-radius: 6px;
            padding: 8px 12px;
        """))
        
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
        tab_layout.setContentsMargins(_sv_ucw(24), _sv_ucw(24), _sv_ucw(24), _sv_ucw(24))
        tab_layout.setSpacing(_sv_ucw(24))
        
        # Scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent; border: none;")
        
        container = QWidget()
        scroll.setWidget(container)
        content_layout = QVBoxLayout(container)
        content_layout.setContentsMargins(0, 0, _sv_ucw(24), 0)
        content_layout.setSpacing(_sv_ucw(24))
        
        # Ana Kontroller
        master_group = QGroupBox()
        master_group.setTitle(" Ana Kontroller")
        master_layout = QGridLayout(master_group)
        master_layout.setContentsMargins(_sv_ucw(24), _sv_ucw(28), _sv_ucw(24), _sv_ucw(24))
        master_layout.setSpacing(_sv_ucw(20))
        master_layout.setHorizontalSpacing(_sv_ucw(24))
        master_layout.setVerticalSpacing(_sv_ucw(20))
        
        # Ana Frekans - Görsel ayrım ile
        freq_container = QWidget()
        freq_layout = QVBoxLayout(freq_container)
        freq_layout.setContentsMargins(_sv_ucw(12), _sv_ucw(12), _sv_ucw(12), _sv_ucw(12))
        freq_layout.setSpacing(_sv_ucw(8))
        
        freq_label = QLabel()
        freq_label.setPixmap(QIcon(get_image_path("frequency.svg")).pixmap(16, 16))
        freq_label.setText(" Ana Frekans")
        freq_label.setStyleSheet(_ss_ucw(f"""
            QLabel {{
                font-size: 11pt;
                font-weight: 600;
                color: #6366f1;
                padding: 4px 0;
                border-bottom: 2px solid rgba(99, 102, 241, 0.3);
                margin-bottom: 8px;
            }}
        """))
        
        self.master_freq_spin = NoWheelSpinBox()
        self.master_freq_spin.setRange(1, 10000)
        self.master_freq_spin.setValue(1000)
        self.master_freq_spin.setSuffix(" Hz")
        self.master_freq_spin.setStyleSheet(_ss_ucw(f"""
            QSpinBox {{
                background: rgba(99, 102, 241, 0.1);
                border: 2px solid rgba(99, 102, 241, 0.3);
                border-radius: 8px;
                padding: 8px 12px;
                font-size: 10pt;
                font-weight: 500;
            }}
            QSpinBox:focus {{
                border-color: #6366f1;
                background: rgba(99, 102, 241, 0.15);
            }}
        """))
        
        freq_layout.addWidget(freq_label)
        freq_layout.addWidget(self.master_freq_spin)
        master_layout.addWidget(freq_container, 0, 0)
        
        # Ana Görev Döngüsü - Görsel ayrım ile
        duty_container = QWidget()
        duty_layout = QVBoxLayout(duty_container)
        duty_layout.setContentsMargins(_sv_ucw(12), _sv_ucw(12), _sv_ucw(12), _sv_ucw(12))
        duty_layout.setSpacing(_sv_ucw(8))
        
        duty_label = QLabel()
        duty_label.setPixmap(QIcon(get_image_path("intensity.svg")).pixmap(16, 16))
        duty_label.setText(" Ana Görev Döngüsü")
        duty_label.setStyleSheet(_ss_ucw(f"""
            QLabel {{
                font-size: 11pt;
                font-weight: 600;
                color: #10b981;
                padding: 4px 0;
                border-bottom: 2px solid rgba(16, 185, 129, 0.3);
                margin-bottom: 8px;
            }}
        """))
        
        self.master_duty_spin = NoWheelDoubleSpinBox()
        self.master_duty_spin.setRange(0.1, 99.9)
        self.master_duty_spin.setValue(50.0)
        self.master_duty_spin.setSuffix(" %")
        self.master_duty_spin.setStyleSheet(_ss_ucw(f"""
            QDoubleSpinBox {{
                background: rgba(16, 185, 129, 0.1);
                border: 2px solid rgba(16, 185, 129, 0.3);
                border-radius: 8px;
                padding: 8px 12px;
                font-size: 10pt;
                font-weight: 500;
            }}
            QDoubleSpinBox:focus {{
                border-color: #10b981;
                background: rgba(16, 185, 129, 0.15);
            }}
        """))
        
        duty_layout.addWidget(duty_label)
        duty_layout.addWidget(self.master_duty_spin)
        master_layout.addWidget(duty_container, 0, 1)
        
        # Ana Süre - Görsel ayrım ile
        duration_container = QWidget()
        duration_layout = QVBoxLayout(duration_container)
        duration_layout.setContentsMargins(_sv_ucw(12), _sv_ucw(12), _sv_ucw(12), _sv_ucw(12))
        duration_layout.setSpacing(_sv_ucw(8))
        
        duration_label = QLabel()
        duration_label.setPixmap(QIcon(get_image_path("duration.svg")).pixmap(16, 16))
        duration_label.setText(" Ana Süre")
        duration_label.setStyleSheet(_ss_ucw(f"""
            QLabel {{
                font-size: 11pt;
                font-weight: 600;
                color: #f59e0b;
                padding: 4px 0;
                border-bottom: 2px solid rgba(245, 158, 11, 0.3);
                margin-bottom: 8px;
            }}
        """))
        
        self.master_duration_spin = NoWheelSpinBox()
        self.master_duration_spin.setRange(0, 9999)
        self.master_duration_spin.setValue(0)
        self.master_duration_spin.setSuffix(" dakika (0=süresiz)")
        self.master_duration_spin.setStyleSheet(_ss_ucw(f"""
            QSpinBox {{
                background: rgba(245, 158, 11, 0.1);
                border: 2px solid rgba(245, 158, 11, 0.3);
                border-radius: 8px;
                padding: 8px 12px;
                font-size: 10pt;
                font-weight: 500;
            }}
            QSpinBox:focus {{
                border-color: #f59e0b;
                background: rgba(245, 158, 11, 0.15);
            }}
        """))
        
        duration_layout.addWidget(duration_label)
        duration_layout.addWidget(self.master_duration_spin)
        master_layout.addWidget(duration_container, 1, 0)
        
        # Ana Faz (Phase) - STM Time Shift
        phase_container = QWidget()
        phase_layout = QVBoxLayout(phase_container)
        phase_layout.setContentsMargins(_sv_ucw(12), _sv_ucw(12), _sv_ucw(12), _sv_ucw(12))
        phase_layout.setSpacing(_sv_ucw(8))
        
        phase_label = QLabel()
        phase_label.setPixmap(QIcon(get_image_path("intensity.svg")).pixmap(16, 16))
        phase_label.setText(" Ana Faz Açısı")
        phase_label.setStyleSheet(_ss_ucw(f"""
            QLabel {{
                font-size: 11pt;
                font-weight: 600;
                color: #8b5cf6;
                padding: 4px 0;
                border-bottom: 2px solid rgba(139, 92, 246, 0.3);
                margin-bottom: 8px;
            }}
        """))
        
        self.master_phase_spin = NoWheelDoubleSpinBox()
        self.master_phase_spin.setRange(0.0, 360.0)
        self.master_phase_spin.setValue(0.0)
        self.master_phase_spin.setSingleStep(15.0)
        self.master_phase_spin.setSuffix(" °")
        self.master_phase_spin.setStyleSheet(_ss_ucw(f"""
            QDoubleSpinBox {{
                background: rgba(139, 92, 246, 0.1);
                border: 2px solid rgba(139, 92, 246, 0.3);
                border-radius: 8px;
                padding: 8px 12px;
                font-size: 10pt;
                font-weight: 500;
            }}
            QDoubleSpinBox:focus {{
                border-color: #8b5cf6;
                background: rgba(139, 92, 246, 0.15);
            }}
        """))
        
        phase_layout.addWidget(phase_label)
        phase_layout.addWidget(self.master_phase_spin)
        master_layout.addWidget(phase_container, 1, 1)
        
        # Görsel ayırıcı çizgi
        master_separator = QFrame()
        master_separator.setFrameShape(QFrame.Shape.HLine)
        master_separator.setFrameShadow(QFrame.Shadow.Sunken)
        master_separator.setStyleSheet(_ss_ucw(f"""
            QFrame {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                    stop:0 transparent, 
                    stop:0.5 rgba(99, 102, 241, 0.4), 
                    stop:1 transparent);
                border: none;
                height: 2px;
                margin: 12px 0;
            }}
        """))
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
        coils_layout.setContentsMargins(_sv_ucw(24), _sv_ucw(28), _sv_ucw(24), _sv_ucw(24))
        coils_layout.setSpacing(_sv_ucw(20))
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
        coil_group.setStyleSheet(_ss_ucw(f"""
            QGroupBox {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                    stop:0 rgba(255, 255, 255, 0.12), 
                    stop:1 rgba(255, 255, 255, 0.06));
                border: 2px solid rgba(99, 102, 241, 0.3);
                border-radius: 18px;
                margin: 8px;
                padding-top: 12px;
                font-weight: 700;
                font-size: 11pt;
            }}
            QGroupBox:hover {{
                border-color: rgba(99, 102, 241, 0.5);
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                    stop:0 rgba(255, 255, 255, 0.15), 
                    stop:1 rgba(255, 255, 255, 0.08));
            }}
        """))
        coil_layout = QVBoxLayout(coil_group)
        coil_layout.setContentsMargins(_sv_ucw(24), _sv_ucw(24), _sv_ucw(24), _sv_ucw(24))
        coil_layout.setSpacing(_sv_ucw(18))
        
        # Header - Bobin adı ve durum
        header_layout = QHBoxLayout()
        header_layout.setSpacing(_sv_ucw(12))
        
        # Bobin numarası ve ikonu
        coil_title_layout = QHBoxLayout()
        coil_title_layout.setSpacing(_sv_ucw(8))
        
        coil_icon = QLabel()
        coil_icon.setPixmap(QIcon(get_image_path("intensity.svg")).pixmap(18, 18))
        coil_icon.setStyleSheet("color: #3b82f6;")
        
        coil_title = QLabel(f"Bobin {coil_num}")
        coil_title.setStyleSheet(_ss_ucw(f"font-size: 12pt; font-weight: 700; color: #ffffff;"))
        
        # Bağlantı durumu göstergesi
        connection_status_label = QLabel("Bağlı Değil")
        connection_status_label.setObjectName("connectionStatus")
        connection_status_label.setStyleSheet(_ss_ucw(f"""
            font-size: 9pt; 
            font-weight: 600; 
            color: #ef4444;
            padding: 4px 8px;
            background: rgba(239, 68, 68, 0.15);
            border-radius: 8px;
            border: 1px solid rgba(239, 68, 68, 0.3);
        """))
        
        coil_title_layout.addWidget(coil_icon)
        coil_title_layout.addWidget(coil_title)
        coil_title_layout.addWidget(connection_status_label)
        coil_title_layout.addStretch()
        
        # Durum göstergesi
        status_container = QWidget()
        status_layout = QHBoxLayout(status_container)
        status_layout.setContentsMargins(_sv_ucw(8), _sv_ucw(4), _sv_ucw(8), _sv_ucw(4))
        status_layout.setSpacing(_sv_ucw(6))
        
        status_led = QLabel("●")
        status_led.setObjectName("statusLed")
        status_led.setStyleSheet(_ss_ucw(f"color: #ef4444; font-size: 9pt;"))
        
        status_label = QLabel("Durduruldu")
        status_label.setStyleSheet(_ss_ucw(f"font-size: 8pt; color: rgba(255, 255, 255, 0.8); font-weight: 600;"))
        
        remaining_time_label = QLabel("")
        remaining_time_label.setObjectName("remainingTimeLabel")
        remaining_time_label.setStyleSheet(_ss_ucw(f"font-size: 8pt; color: rgba(255, 255, 255, 0.9); font-weight: 600;"))
        remaining_time_label.setVisible(False)
        
        # Sıcaklık göstergesi
        temp_label = QLabel("--°C")
        temp_label.setObjectName("tempLabel")
        temp_label.setStyleSheet(_ss_ucw(f"font-size: 8pt; color: rgba(255, 255, 255, 0.7); font-weight: 600;"))
        temp_label.setToolTip("Bobin sıcaklığı")
        
        status_layout.addWidget(status_led)
        status_layout.addWidget(status_label)
        status_layout.addWidget(remaining_time_label)
        status_layout.addWidget(temp_label)
        status_layout.addStretch()
        
        status_container.setStyleSheet(_ss_ucw(f"""
            background: rgba(239, 68, 68, 0.1);
            border-radius: 12px;
            border: 1px solid rgba(239, 68, 68, 0.3);
        """))
        
        header_layout.addLayout(coil_title_layout)
        header_layout.addWidget(status_container)
        
        coil_layout.addLayout(header_layout)
        
        # Parametreler - Grid layout
        params_widget = QWidget()
        params_layout = QGridLayout(params_widget)
        params_layout.setContentsMargins(0, 0, 0, 0)
        params_layout.setSpacing(_sv_ucw(12))
        
        # Frekans - Görsel ayrım ile
        freq_container = QWidget()
        freq_container.setStyleSheet(_ss_ucw(f"""
            QWidget {{
                background: rgba(99, 102, 241, 0.08);
                border: 1px solid rgba(99, 102, 241, 0.2);
                border-radius: 8px;
                padding: 8px;
                margin: 2px;
            }}
        """))
        freq_container_layout = QVBoxLayout(freq_container)
        freq_container_layout.setContentsMargins(_sv_ucw(8), _sv_ucw(8), _sv_ucw(8), _sv_ucw(8))
        freq_container_layout.setSpacing(_sv_ucw(4))
        
        freq_label = QLabel()
        freq_label.setPixmap(QIcon(get_image_path("frequency.svg")).pixmap(12, 12))
        freq_label.setText(" Frekans")
        freq_label.setStyleSheet(_ss_ucw(f"font-size: 9pt; color: #6366f1; font-weight: 700;"))
        freq_spin = NoWheelSpinBox()
        freq_spin.setRange(1, 50000)
        freq_spin.setValue(1000)
        freq_spin.setSuffix(" Hz")
        freq_spin.setMinimumHeight(_sv_ucw(32, min_ratio=0.7, max_ratio=1.3))
        freq_spin.setStyleSheet(_ss_ucw(f"""
            QSpinBox {{
                background: rgba(255, 255, 255, 0.1);
                border: 1px solid rgba(99, 102, 241, 0.3);
                border-radius: 6px;
                padding: 4px 8px;
                font-weight: 600;
            }}
            QSpinBox:focus {{
                border-color: #6366f1;
                background: rgba(255, 255, 255, 0.15);
            }}
        """))
        
        freq_container_layout.addWidget(freq_label)
        freq_container_layout.addWidget(freq_spin)
        params_layout.addWidget(freq_container, 0, 0)
        
        # Görev döngüsü - Görsel ayrım ile
        duty_container = QWidget()
        duty_container.setStyleSheet(_ss_ucw(f"""
            QWidget {{
                background: rgba(16, 185, 129, 0.08);
                border: 1px solid rgba(16, 185, 129, 0.2);
                border-radius: 8px;
                padding: 8px;
                margin: 2px;
            }}
        """))
        duty_container_layout = QVBoxLayout(duty_container)
        duty_container_layout.setContentsMargins(_sv_ucw(8), _sv_ucw(8), _sv_ucw(8), _sv_ucw(8))
        duty_container_layout.setSpacing(_sv_ucw(4))
        
        duty_label = QLabel()
        duty_label.setPixmap(QIcon(get_image_path("intensity.svg")).pixmap(12, 12))
        duty_label.setText(" Görev Döngüsü")
        duty_label.setStyleSheet(_ss_ucw(f"font-size: 9pt; color: #10b981; font-weight: 700;"))
        duty_spin = NoWheelDoubleSpinBox()
        duty_spin.setRange(0.1, 99.9)
        duty_spin.setValue(50.0)
        duty_spin.setSuffix(" %")
        duty_spin.setMinimumHeight(_sv_ucw(32, min_ratio=0.7, max_ratio=1.3))
        duty_spin.setStyleSheet(_ss_ucw(f"""
            QDoubleSpinBox {{
                background: rgba(255, 255, 255, 0.1);
                border: 1px solid rgba(16, 185, 129, 0.3);
                border-radius: 6px;
                padding: 4px 8px;
                font-weight: 600;
            }}
            QDoubleSpinBox:focus {{
                border-color: #10b981;
                background: rgba(255, 255, 255, 0.15);
            }}
        """))
        
        duty_container_layout.addWidget(duty_label)
        duty_container_layout.addWidget(duty_spin)
        params_layout.addWidget(duty_container, 0, 1)
        
        # Süre - Görsel ayrım ile
        duration_container = QWidget()
        duration_container.setStyleSheet(_ss_ucw(f"""
            QWidget {{
                background: rgba(245, 158, 11, 0.08);
                border: 1px solid rgba(245, 158, 11, 0.2);
                border-radius: 8px;
                padding: 8px;
                margin: 2px;
            }}
        """))
        duration_container_layout = QVBoxLayout(duration_container)
        duration_container_layout.setContentsMargins(_sv_ucw(8), _sv_ucw(8), _sv_ucw(8), _sv_ucw(8))
        duration_container_layout.setSpacing(_sv_ucw(4))
        
        duration_label = QLabel()
        duration_label.setPixmap(QIcon(get_image_path("duration.svg")).pixmap(12, 12))
        duration_label.setText(" Süre")
        duration_label.setStyleSheet(_ss_ucw(f"font-size: 9pt; color: #f59e0b; font-weight: 700;"))
        duration_spin = NoWheelSpinBox()
        duration_spin.setRange(0, 9999)
        duration_spin.setValue(0)
        duration_spin.setSuffix(" dk")
        duration_spin.setMinimumHeight(_sv_ucw(32, min_ratio=0.7, max_ratio=1.3))
        duration_spin.setStyleSheet(_ss_ucw(f"""
            QSpinBox {{
                background: rgba(255, 255, 255, 0.1);
                border: 1px solid rgba(245, 158, 11, 0.3);
                border-radius: 6px;
                padding: 4px 8px;
                font-weight: 600;
            }}
            QSpinBox:focus {{
                border-color: #f59e0b;
                background: rgba(255, 255, 255, 0.15);
            }}
        """))
        
        duration_container_layout.addWidget(duration_label)
        duration_container_layout.addWidget(duration_spin)
        params_layout.addWidget(duration_container, 1, 0)
        
        # Faz (Phase) - STM Time Shift
        phase_container = QWidget()
        phase_container.setStyleSheet(_ss_ucw(f"""
            QWidget {{
                background: rgba(139, 92, 246, 0.08);
                border: 1px solid rgba(139, 92, 246, 0.2);
                border-radius: 8px;
                padding: 8px;
                margin: 2px;
            }}
        """))
        phase_container_layout = QVBoxLayout(phase_container)
        phase_container_layout.setContentsMargins(_sv_ucw(8), _sv_ucw(8), _sv_ucw(8), _sv_ucw(8))
        phase_container_layout.setSpacing(_sv_ucw(4))
        
        phase_label = QLabel()
        phase_label.setPixmap(QIcon(get_image_path("intensity.svg")).pixmap(12, 12)) 
        phase_label.setText(" Faz (Time Shift)")
        phase_label.setStyleSheet(_ss_ucw(f"font-size: 9pt; color: #8b5cf6; font-weight: 700;"))
        phase_label.setToolTip("Bobin faz açısı (0-360 derece). STM32 tarafında senkron pwm time shift için kullanılır.")
        
        phase_spin = NoWheelDoubleSpinBox()
        phase_spin.setRange(0.0, 360.0)
        phase_spin.setValue(0.0)
        phase_spin.setSingleStep(15.0)
        phase_spin.setSuffix(" °")
        phase_spin.setMinimumHeight(_sv_ucw(32, min_ratio=0.7, max_ratio=1.3))
        phase_spin.setStyleSheet(_ss_ucw(f"""
            QDoubleSpinBox {{
                background: rgba(255, 255, 255, 0.1);
                border: 1px solid rgba(139, 92, 246, 0.3);
                border-radius: 6px;
                padding: 4px 8px;
                font-weight: 600;
            }}
            QDoubleSpinBox:focus {{
                border-color: #8b5cf6;
                background: rgba(255, 255, 255, 0.15);
            }}
        """))
        
        phase_container_layout.addWidget(phase_label)
        phase_container_layout.addWidget(phase_spin)
        params_layout.addWidget(phase_container, 1, 1)
        
        coil_layout.addWidget(params_widget)
        
        # Görsel ayırıcı çizgi
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        separator.setStyleSheet(_ss_ucw(f"""
            QFrame {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                    stop:0 transparent, 
                    stop:0.5 rgba(99, 102, 241, 0.4), 
                    stop:1 transparent);
                border: none;
                height: 2px;
                margin: 8px 0;
            }}
        """))
        coil_layout.addWidget(separator)
        
        # Kontrol butonları - Modern tasarım
        control_layout = QHBoxLayout()
        control_layout.setSpacing(_sv_ucw(12))
        
        start_btn = QPushButton()
        start_btn.setIcon(QIcon(get_image_path("play.svg")))
        start_btn.setText(f" Bobin {coil_num} Başlat")
        start_btn.setProperty("class", "success")
        start_btn.setMinimumHeight(_sv_ucw(42, min_ratio=0.7, max_ratio=1.3))
        start_btn.setStyleSheet(_ss_ucw(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                    stop:0 rgba(34, 197, 94, 0.9), 
                    stop:1 rgba(21, 128, 61, 0.9));
                border: 2px solid rgba(34, 197, 94, 0.4);
                border-radius: 12px;
                color: #ffffff;
                font-size: 10pt;
                font-weight: 700;
                padding: 8px 16px;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                    stop:0 rgba(34, 197, 94, 1.0), 
                    stop:1 rgba(21, 128, 61, 1.0));
                border: 2px solid rgba(34, 197, 94, 0.6);
                padding: 7px 15px;
            }}
            QPushButton:disabled {{
                background: rgba(34, 197, 94, 0.3);
                border-color: rgba(34, 197, 94, 0.2);
                color: rgba(255, 255, 255, 0.5);
            }}
        """))
        start_btn.clicked.connect(partial(self.start_coil, coil_num))
        
        stop_btn = QPushButton()
        stop_btn.setIcon(QIcon(get_image_path("stop.svg")))
        stop_btn.setText(f" Bobin {coil_num} Durdur")
        stop_btn.setProperty("class", "danger")
        stop_btn.setMinimumHeight(_sv_ucw(42, min_ratio=0.7, max_ratio=1.3))
        stop_btn.setStyleSheet(_ss_ucw(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                    stop:0 rgba(239, 68, 68, 0.9), 
                    stop:1 rgba(185, 28, 28, 0.9));
                border: 2px solid rgba(239, 68, 68, 0.4);
                border-radius: 12px;
                color: #ffffff;
                font-size: 10pt;
                font-weight: 700;
                padding: 8px 16px;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                    stop:0 rgba(239, 68, 68, 1.0), 
                    stop:1 rgba(185, 28, 28, 1.0));
                border: 2px solid rgba(239, 68, 68, 0.6);
                padding: 7px 15px;
            }}
            QPushButton:disabled {{
                background: rgba(239, 68, 68, 0.3);
                border-color: rgba(239, 68, 68, 0.2);
                color: rgba(255, 255, 255, 0.5);
            }}
        """))
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
            'phase_spin': phase_spin,
            'start_btn': start_btn,
            'stop_btn': stop_btn
        }
        
        parent_layout.addWidget(coil_group, row, col)
    
    def _init_ai_controller(self):
        """Initialize AI controller (target-only literature recommendation mode)."""
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

            self.logger.info("AI controller initialized successfully (target-only mode)")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize AI controller: {e}")
            self.ai_controller = None
    
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
        
        # AI recommendation can run immediately after patient selection.
        if hasattr(self, 'ai_calculate_btn'):
            self.ai_calculate_btn.setEnabled(True)

        # Start button remains disabled until recommendation is calculated.
        if hasattr(self, 'ai_start_btn'):
            self.ai_start_btn.setEnabled(False)
        
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
                    font-size: 12pt;
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
            font-size: 16pt;
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
        patient_label.setStyleSheet("font-size: 11pt; font-weight: 600; color: #6366f1;")
        
        self.ai_patient_combo = QComboBox()
        self.ai_patient_combo.setMinimumHeight(40)
        self.ai_patient_combo.setStyleSheet("""
            QComboBox {
                background: rgba(255, 255, 255, 0.12);
                color: white;
                border: 2px solid rgba(99, 102, 241, 0.3);
                border-radius: 8px;
                padding: 10px 12px;
                font-size: 11pt;
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
                font-size: 9pt;
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
            font-size: 16pt;
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
        target_label.setStyleSheet("font-weight: 600; color: #6366f1; font-size: 11pt;")
        
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
                font-size: 11pt;
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
        
        self.ai_status_label = QLabel("● Literatür Modu Hazır")
        self.ai_status_label.setStyleSheet("""
            QLabel {
                color: #22c55e;
                font-size: 14pt;
                font-weight: 700;
            }
        """)
        
        self.ai_confidence_label = QLabel("Kaynak: Literatür Protokolleri")
        self.ai_confidence_label.setStyleSheet("""
            QLabel {
                color: rgba(255, 255, 255, 0.7);
                font-size: 11pt;
            }
        """)
        
        status_container_layout.addWidget(self.ai_status_label)
        status_container_layout.addWidget(self.ai_confidence_label)
        status_container_layout.addStretch()
        
        status_layout.addWidget(status_container)
        
        # AI message display
        self.ai_message_label = QLabel("AI yalnızca seans hedefine göre literatür protokol değerleri önerir. Hasta seçip hesapla butonuna basın.")
        self.ai_message_label.setWordWrap(True)
        self.ai_message_label.setStyleSheet("""
            QLabel {
                color: rgba(255, 255, 255, 0.8);
                font-size: 10pt;
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
                font-size: 10pt;
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
        self.ai_start_btn.setEnabled(False)  # Enabled after recommendation is calculated
        self.ai_start_btn.clicked.connect(self._start_ai_session)
        self.ai_start_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #22c55e, stop:1 #16a34a);
                color: white;
                font-size: 11pt;
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
                font-size: 11pt;
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

    def _create_ai_pro_tab(self):
        """AI Pro Modu - Kamera Entegrasyonu ve Anlık Tracking"""
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)
        
        # --- 1. KAMERA VE KONTROL PANELİ ---
        top_layout = QHBoxLayout()
        
        # Kamera Görüntüsü
        _cam_init_text = (
            "⚠️ Kamera Bağlı Değil\n\nAI Pro modu kamera gerektirmektedir.\n(cv2 / mediapipe / onnxruntime eksik veya kamera takılı değil)"
            if not CAMERA_AVAILABLE
            else "📷 Kamera Hazırlanıyor...\n\nAI Pro sekmesine geçince kamera başlar."
        )
        self.camera_label = ResponsiveImageLabel(_cam_init_text)
        self.camera_label.setMinimumSize(400, 300)
        self.camera_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.camera_label.setStyleSheet("background-color: black; color: white; border: 2px solid #555;")
        top_layout.addWidget(self.camera_label)
        
        # Yan Kontrol Paneli (Koordinatlar ve Kalibrasyon)
        coord_group = QGroupBox("📌 Canlı Hedef (x, y, z)")
        coord_layout = QVBoxLayout(coord_group)
        
        self.lbl_x = QLabel("X: 0.0 mm")
        self.lbl_y = QLabel("Y: 0.0 mm")
        self.lbl_z = QLabel("Z: 0.0 mm")
        self.lbl_e_field = QLabel("Anlık E-Alan: 0.0 V/m")
        self.lbl_x.setStyleSheet("font-size: 12pt; font-weight: bold;")
        self.lbl_y.setStyleSheet("font-size: 12pt; font-weight: bold;")
        self.lbl_z.setStyleSheet("font-size: 12pt; font-weight: bold;")
        self.lbl_e_field.setStyleSheet("font-size: 14pt; font-weight: bold; color: #10b981; margin-top: 10px;")
        
        coord_layout.addWidget(self.lbl_x)
        coord_layout.addWidget(self.lbl_y)
        coord_layout.addWidget(self.lbl_z)
        coord_layout.addWidget(self.lbl_e_field)
        
        # Bobinleri Sıfırla Butonu (Yeni Eklenti)
        self.btn_reset_pwms = QPushButton("🔄 Tüm Bobinleri Sıfırla")
        self.btn_reset_pwms.setMinimumHeight(40)
        self.btn_reset_pwms.clicked.connect(self._reset_all_pwms)
        self.btn_reset_pwms.setStyleSheet("""
            QPushButton {
                background-color: #ef4444; /* Red */
                color: white;
                font-weight: bold;
                border-radius: 8px;
                margin-top: 8px;
                font-size: 11pt;
            }
            QPushButton:hover {
                background-color: #dc2626;
            }
        """)
        coord_layout.addWidget(self.btn_reset_pwms)
        coord_layout.addStretch()
        
        self.btn_calibrate = QPushButton("🎯 Z Ekseni Kalibre Et")
        self.btn_calibrate.setMinimumHeight(40)
        self.btn_calibrate.clicked.connect(self._calibrate_camera)
        coord_layout.addWidget(self.btn_calibrate)
        
        # Self-Test Butonu Ekle (Güvenlik Öncesi Test)
        self.btn_hardware_selftest = QPushButton("🏥 Cihaz Self-Test")
        self.btn_hardware_selftest.setMinimumHeight(40)
        self.btn_hardware_selftest.clicked.connect(self._trigger_hardware_selftest)
        self.btn_hardware_selftest.setStyleSheet("""
            QPushButton {
                background-color: #f59e0b; /* Amber */
                color: white;
                font-weight: bold;
                border-radius: 8px;
            }
        """)
        coord_layout.addWidget(self.btn_hardware_selftest)
        
        # Organ Seçimi Ekle
        lbl_organ = QLabel("🧠 Hedef Organ:")
        lbl_organ.setStyleSheet("font-size: 11pt; font-weight: bold;")
        coord_layout.addWidget(lbl_organ)
        
        self.cb_organ_select = QComboBox()
        self.cb_organ_select.setMinimumHeight(35)
        # {0: 'kutu_butun', 1: 'mide', 2: 'bobrek', 3: 'karaciger', 4: 'mesane', 5: 'pankreas', 6: 'bagirsak'}
        organ_list = [
            ("Kutu Bütün", 0),
            ("Mide", 1),
            ("Böbrek", 2),
            ("Karaciğer", 3),
            ("Mesane", 4),
            ("Pankreas", 5),
            ("Bağırsak", 6)
        ]
        for name, oid in organ_list:
            self.cb_organ_select.addItem(name, oid)
        
        self.cb_organ_select.currentIndexChanged.connect(self._on_ai_organ_changed)
        coord_layout.addWidget(self.cb_organ_select)

        # ---- Seans Suresi Secimi ----
        lbl_duration = QLabel("⏱ Seans Süresi:")
        lbl_duration.setStyleSheet("font-size: 11pt; font-weight: bold;")
        coord_layout.addWidget(lbl_duration)

        duration_row = QWidget()
        duration_row_layout = QHBoxLayout(duration_row)
        duration_row_layout.setContentsMargins(0, 0, 0, 0)
        duration_row_layout.setSpacing(6)

        self.spin_ai_pro_duration = QSpinBox()
        self.spin_ai_pro_duration.setRange(5, 120)
        self.spin_ai_pro_duration.setSingleStep(5)
        self.spin_ai_pro_duration.setValue(20)
        self.spin_ai_pro_duration.setSuffix(" dk")
        self.spin_ai_pro_duration.setMinimumHeight(32)
        self.spin_ai_pro_duration.setStyleSheet(
            "font-size: 11pt; font-weight: bold; color: #f59e0b;"
        )
        duration_row_layout.addWidget(self.spin_ai_pro_duration, 1)

        self.lbl_ai_pro_countdown = QLabel("--:--")
        self.lbl_ai_pro_countdown.setStyleSheet(
            "font-size: 16pt; font-weight: bold; color: #10b981; min-width: 60px;"
        )
        self.lbl_ai_pro_countdown.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        duration_row_layout.addWidget(self.lbl_ai_pro_countdown)
        coord_layout.addWidget(duration_row)

        # Geri sayim timer (1 saniyede bir gunceller)
        from PyQt6.QtCore import QTimer
        self._ai_pro_session_timer = QTimer(self)
        self._ai_pro_session_timer.setInterval(1000)  # 1 saniye
        self._ai_pro_session_timer.timeout.connect(self._ai_pro_tick)
        self._ai_pro_remaining_secs = 0

        self.btn_start_ai_pro = QPushButton("🚀 AI Uygulamayı Başlat (1Hz DDS)")
        self.btn_start_ai_pro.setMinimumHeight(50)
        self.btn_start_ai_pro.setCheckable(True)
        self.btn_start_ai_pro.clicked.connect(self._toggle_ai_pro_tracking)
        self.btn_start_ai_pro.setStyleSheet("""
            QPushButton {
                background-color: #3b82f6; 
                color: white;
                font-weight: bold;
                border-radius: 8px;
            }
            QPushButton:checked {
                background-color: #ef4444; /* Stop color */
            }
        """)
        coord_layout.addWidget(self.btn_start_ai_pro)
        
        top_layout.addWidget(coord_group)
        top_layout.setStretch(0, 2)
        top_layout.setStretch(1, 1)
        
        layout.addLayout(top_layout)
        
# --- 2. ÇIKTI TABLOSU VE DIAGNOSTİK ---
        results_group = QGroupBox("📊 AI Anlık Çıktıları ve Diagnostik")
        results_layout = QGridLayout(results_group)

        self.ai_pro_result_labels = {}
        # Kolon başlıkları
        results_layout.addWidget(QLabel("<b>Bobin</b>"), 0, 0)
        results_layout.addWidget(QLabel("<b>Açı (Faz) Modeli</b>"), 0, 1)
        results_layout.addWidget(QLabel("<b>Duty Modeli</b>"), 0, 2)
        results_layout.addWidget(QLabel("<b>Self-Test Durumu</b>"), 0, 3)

        for i in range(1, 9):
            results_layout.addWidget(QLabel(f"Bobin {i}:"), i, 0)
            
            lbl_p = QLabel("-- °")
            lbl_d = QLabel("-- %")
            lbl_status = QLabel("Bekliyor ⏳")
            lbl_status.setStyleSheet("color: gray;")
            
            results_layout.addWidget(lbl_p, i, 1)
            results_layout.addWidget(lbl_d, i, 2)
            results_layout.addWidget(lbl_status, i, 3)
            
            self.ai_pro_result_labels[i] = {
                'p': lbl_p,
                'd': lbl_d,
                'status': lbl_status
            }
            
        layout.addWidget(results_group)
        layout.addStretch()
        
        scroll_area.setWidget(container)
        
        self.ai_pro_tracking_active = False
        self.camera_thread = None
        
        return scroll_area

    def _start_camera_thread(self):
        if not CAMERA_AVAILABLE or CameraAIThread is None:
            self._show_toast(
                "Kamera bağlı değil veya gerekli paketler yüklenmemiş.\n"
                "(cv2 / mediapipe / onnxruntime eksik olabilir)",
                "warning"
            )
            if hasattr(self, 'camera_label'):
                self.camera_label.setText(
                    "⚠️ Kamera Bağlı Değil\n\nAI Pro modu kamera gerektirmektedir."
                )
            return

        import os
        base_path = str(resource_path(os.path.join('ai_hub', 'em_kedi')))
        self.camera_thread = CameraAIThread(base_path)
        self.camera_thread.frame_ready.connect(self._on_camera_frame_ready)
        self.camera_thread.prediction_ready.connect(self._on_camera_prediction_ready)
        self.camera_thread.error_occurred.connect(self._on_camera_error)
        self.camera_thread.start()

    def _on_camera_error(self, error_msg):
        """Kamera hatası oluştuğunda UI'yi güncelle"""
        self._show_toast(f"Kamera: {error_msg}", "error")
        if hasattr(self, 'camera_label'):
            self.camera_label.setText(
                f"⚠️ Kamera Hatası\n\n{error_msg}"
            )
        # Thread'i None yap ki tekrar denenebilsin
        self.camera_thread = None

    def _calibrate_camera(self):
        if hasattr(self, 'camera_thread') and self.camera_thread:
            self.camera_thread.calibrate()
            self._show_toast("Kamera kalibrasyon isteği gönderildi.", "success")

    def _on_ai_organ_changed(self, index):
        organ_id = self.cb_organ_select.itemData(index)
        if hasattr(self, 'camera_thread') and self.camera_thread:
            self.camera_thread.set_organ_id(organ_id)
            self._show_toast(f"Hedef organ ID {organ_id} olarak seçildi.", "success")

    def _on_camera_frame_ready(self, q_img):
        from PyQt6.QtGui import QPixmap
        self.camera_label.setPixmap(QPixmap.fromImage(q_img))
        # Cat Vision sekmesine anlık kare ilet (snapshot için)
        if getattr(self, '_real_cat_vision_tab', None) is not None:
            self._real_cat_vision_tab.receive_camera_frame(q_img)

    def _on_camera_prediction_ready(self, x, y, z, duties, phases, e_field):
        # 1. UI Güncelle (Koordinatlar)
        self.lbl_x.setText(f"X: {x:.1f} mm")
        self.lbl_y.setText(f"Y: {y:.1f} mm")
        self.lbl_z.setText(f"Z: {z:.1f} mm")
        self.lbl_e_field.setText(f"Anlık E-Alan: {e_field:.2f} V/m")
        
        # 2. UI Güncelle (Tahmin Tablosu)
        num_coils_to_update = min(8, len(duties), len(phases))
        for i in range(num_coils_to_update):
            coil_id = i + 1
            duty_val = duties[i] * 100.0  # % formatına çevir
            
            # Limit UI duty reflection
            if duty_val < 0.1: duty_val = 0.0
            if duty_val > 50.0: duty_val = 50.0
                
            phase_val = phases[i]
            
            self.ai_pro_result_labels[coil_id]['d'].setText(f"{duty_val:.1f} %")
            self.ai_pro_result_labels[coil_id]['p'].setText(f"{phase_val:.1f} °")
            
        # 3. Eğer Cihaza gönderim aktifse ESP'lere yolla (20Hz limitli thread'den geliyor)
        if self.ai_pro_tracking_active:
            self._send_udp_live_update(duties, phases)

    def _send_udp_live_update(self, duties, phases):
        """
        STM32 + ESP32 verilerini arka plan thread'e kuyruğa gönderir.
        Ana thread bloke olmaz.
        """
        import struct

        ESP32_IP   = "192.168.137.255"
        ESP32_PORT = 5005

        if not self.main_window or not hasattr(self.main_window, '_hw_send_queue'):
            return

        # _udp_seq_main __init__'te 0 ile başlatıldı; hasattr kontrolü kaldırıldı (Rapor §4.3)

        final_duties_u16 = []
        final_phases_u16 = []
        stm32_duties  = []
        stm32_phases  = []

        for i, (duty_ratio, phase_val) in enumerate(zip(duties, phases)):
            duty_ratio = max(0.0, min(0.49, float(duty_ratio)))
            phase_val  = max(0.0, min(360.0, float(phase_val)))
            final_duties_u16.append(int(round(duty_ratio * 65535)) % 65536)
            final_phases_u16.append(int(round(phase_val * 65535 / 360.0)) % 65536)
            if i < 5:
                stm32_duties.append(min(0.49, duty_ratio))
                stm32_phases.append(phase_val)

        # Pad to 8 elements
        while len(final_duties_u16) < 8:
            final_duties_u16.append(0)
            final_phases_u16.append(0)
        while len(stm32_duties) < 5:
            stm32_duties.append(0.0)
            stm32_phases.append(0.0)

        import time as _t
        if stm32_phases:
            ref = stm32_phases[0]  # Bobin 1'in ham faz açısı — evrensel referans
            stm32_phases = [(ph - ref) % 360.0 for ph in stm32_phases]
            stm32_phases[0] = 0.0

            # STM32 bobinleri (1-5, indeks 0-4): zaten stm32_phases'den güncellendi
            for i, ph in enumerate(stm32_phases):
                final_phases_u16[i] = int(round(ph * 65535 / 360.0)) % 65536

            # ESP32/ESP8266 bobinleri (6-8, indeks 5-7): aynı referansa göre hizala
            # Donanım sync pulse (STM32 PB1 → GPIO7) faz kilitini garanti eder;
            # bu yazılımsal düzeltme ise GUI'den gönderilen başlangıç açısını
            # yine Bobin 1'e göre normalize eder.
            for j in range(5, min(len(final_phases_u16), len(phases))):
                raw_phase = max(0.0, min(360.0, float(phases[j])))
                corrected  = (raw_phase - ref) % 360.0
                final_phases_u16[j] = int(round(corrected * 65535 / 360.0)) % 65536

        ref_ms = int(_t.monotonic() * 1000) % 10

        # STM32 mesajı
        stm_msg = (
            f"ST[{stm32_duties[0]:.2f},{stm32_duties[1]:.2f},"
            f"{stm32_duties[2]:.2f},{stm32_duties[3]:.2f},{stm32_duties[4]:.2f}]"
            f"[{stm32_phases[0]:.1f},{stm32_phases[1]:.1f},"
            f"{stm32_phases[2]:.1f},{stm32_phases[3]:.1f},{stm32_phases[4]:.1f}]"
            f"[{ref_ms}]EN"
        )

        # UDP paketi — Rapor §3.3: iç içe crc16_ccitt kaldırıldı, modül düzeyindeki _crc16_ccitt kullanılıyor
        magic   = b'\xA5\x5A'
        payload = struct.pack('<2sI8H8H', magic, self._udp_seq_main,
                              *final_duties_u16, *final_phases_u16)
        crc     = _crc16_ccitt(payload)
        udp_pkt = payload + struct.pack('<H', crc)
        self._udp_seq_main = (self._udp_seq_main + 1) & 0xFFFFFFFF

        # Kuyruğa ekle (doluysa eski paketi at — gecikmiş veri gönderme)
        # Rapor §4.1.1: Spesifik exception türleri kullan (queue.Full / queue.Empty)
        import queue as _queue_mod
        try:
            self.main_window._hw_send_queue.put_nowait((stm_msg, udp_pkt, ESP32_IP, ESP32_PORT))
        except _queue_mod.Full:
            # Kuyruk dolu: en eski paketi at, yenisini ekle
            try:
                self.main_window._hw_send_queue.get_nowait()
                self.main_window._hw_send_queue.put_nowait((stm_msg, udp_pkt, ESP32_IP, ESP32_PORT))
            except _queue_mod.Empty:
                self.logger.warning("[UDP queue] Beklenmeyen durum: Full sonrası Empty")

    def _send_stm_manual_update(self):
        """
        Manuel modda çalışan ilk 5 bobinin (STM32'ye bağlı) güncel durumunu UART üzerinden gönderir.
        """
        if not self.main_window or not hasattr(self.main_window, '_hw_send_queue'):
            return

        stm32_duties = []
        stm32_phases = []
        stm32_freqs = []
        stm32_durs = []
        
        for i in range(1, 6): # Sadece Bobin 1-5
            if i in self.coil_controls:
                controls = self.coil_controls[i]
                # Eğer start butonu aktif değilse bobin ya çalışıyordur ya da start komutu yeni gitmiştir
                is_running_ui = not controls['start_btn'].isEnabled()
                
                if is_running_ui:
                    duty_val = max(0.0, float(controls['duty_spin'].value()) / 100.0)
                    phase_val = max(0.0, min(360.0, float(controls['phase_spin'].value())))
                    freq_val = max(1.0, min(10000.0, float(controls['freq_spin'].value())))
                    dur_val = int(controls['duration_spin'].value())
                else:
                    duty_val = 0.0
                    phase_val = 0.0
                    freq_val = float(controls['freq_spin'].value()) if 'freq_spin' in controls else 100.0
                    dur_val = 0
                
                stm32_duties.append(duty_val)
                stm32_phases.append(phase_val)
                stm32_freqs.append(freq_val)
                stm32_durs.append(dur_val)
            else:
                stm32_duties.append(0.0)
                stm32_phases.append(0.0)
                stm32_freqs.append(100.0)
                stm32_durs.append(0)

        import time as _t
        ref_ms = int(_t.monotonic() * 1000) % 10

        # STM32 mesajı: ST[d0..4][p0..4][f0..4][dur0..4][ref]EN
        stm_msg = (
            f"ST[{stm32_duties[0]:.2f},{stm32_duties[1]:.2f},"
            f"{stm32_duties[2]:.2f},{stm32_duties[3]:.2f},{stm32_duties[4]:.2f}]"
            f"[{stm32_phases[0]:.1f},{stm32_phases[1]:.1f},"
            f"{stm32_phases[2]:.1f},{stm32_phases[3]:.1f},{stm32_phases[4]:.1f}]"
            f"[{stm32_freqs[0]:.1f},{stm32_freqs[1]:.1f},"
            f"{stm32_freqs[2]:.1f},{stm32_freqs[3]:.1f},{stm32_freqs[4]:.1f}]"
            f"[{stm32_durs[0]},{stm32_durs[1]},{stm32_durs[2]},{stm32_durs[3]},{stm32_durs[4]}]"
            f"[{ref_ms}]EN"
        )
        
        udp_pkt = b''
        ESP32_IP = "192.168.137.255"
        ESP32_PORT = 5005
        
        import queue as _queue_mod
        try:
            self.main_window._hw_send_queue.put_nowait((stm_msg, udp_pkt, ESP32_IP, ESP32_PORT))
        except _queue_mod.Full:
            try:
                self.main_window._hw_send_queue.get_nowait()
                self.main_window._hw_send_queue.put_nowait((stm_msg, udp_pkt, ESP32_IP, ESP32_PORT))
            except _queue_mod.Empty:
                pass
                
    def _trigger_hardware_selftest(self):
        connected_coils = self._get_connected_coils()
        if not connected_coils:
            self.show_warning("Bağlı cihaz bulanamadı!")
            return
            
        import time

        for coil_id in connected_coils:
            command_id = self._get_next_command_id(coil_id)
            command = {
                "command": "SELFTEST",
                "command_id": command_id,
                "timestamp": time.time()
            }
            
            # Pending commands listesine de ekleyelim ki zaman aşımı takibi yapılabilsin
            self.add_pending_command(coil_id, command)
            
            # Güvenli signal akışıyla ana pencereden gönderim
            if self.main_window and hasattr(self.main_window, 'coil_control_requested'):
                self.main_window.coil_control_requested.emit(coil_id, command)
                
            self.logger.info(f"Coil {coil_id} için SELFTEST komutu (ID: {command_id}) gönderildi.")

        self._show_toast(f"{len(connected_coils)} cihaza Self-Test komutu gönderildi. Lütfen bekleyin...", "info")
        
    def _reset_all_pwms(self):
        """Kullanıcının butona basmasıyla 8 bobinin sıfırlanması ve PWM durdurulması."""
        # 1. Eğer AI Tracking (Canlı Aktarım) açıksa onu kapat.
        if hasattr(self, 'btn_start_ai_pro') and self.btn_start_ai_pro.isChecked():
            self.btn_start_ai_pro.setChecked(False)
            self._toggle_ai_pro_tracking()
            
        # 2. Stop_all_coils fonksiyonu bağlı olan cihazlara stop gönderir
        self.stop_all_coils()
        
        # 3. Her bobine ayri "stop" komutu gonder -- "start"+duty=0 ESP'de
        #    minimum duty enforcement'i tetikler (0.2% sorun). Stop kesin kapatir.
        if hasattr(self, 'main_window') and self.main_window.mqtt_client and self.main_window.mqtt_client.is_connected():
            for i in range(1, 9):
                command_id = self._get_next_command_id(i)
                command = {
                    "command": "stop",
                    "command_id": command_id,
                    "timestamp": time.time()
                }
                topic = f"pemf/coil_{i}/cmd"
                try:
                    self.main_window.mqtt_client.publish(topic, json.dumps(command))
                except Exception as _pub_err:
                    # Rapor §4.1.2: Sessiz hata kaldırıldı
                    self.logger.warning(f"[_reset_all_pwms] Coil {i} MQTT publish hatası: {_pub_err}")

        # 4. Arayüzdeki diagnostik tablosunu temizle
        # Rapor §4.3: hasattr yerine None kontrolü
        if self.ai_pro_result_labels is not None:
            for i in range(1, 9):
                if i in self.ai_pro_result_labels:
                    self.ai_pro_result_labels[i]['p'].setText("0.0 °")
                    self.ai_pro_result_labels[i]['d'].setText("0.0 %")
                    self.ai_pro_result_labels[i]['status'].setText("Sıfırlandı 🛑")
                    self.ai_pro_result_labels[i]['status'].setStyleSheet("color: #ef4444; font-weight: bold;")
                    
        # STM32 Manuel Kontrol Güncellemesi (Hepsi durduruldu)
        self._send_stm_manual_update()
                    
        self._show_toast("Tüm 8 bobinin PWM çıkışları durduruldu ve 0'landı.", "info")

    def _toggle_ai_pro_tracking(self):
        if not self.btn_start_ai_pro.isChecked():
            # Stop tracking
            self.ai_pro_tracking_active = False
            # Geri sayim timer'ini durdur
            if hasattr(self, '_ai_pro_session_timer'):
                self._ai_pro_session_timer.stop()
            # Rapor §4.3: hasattr yerine None kontrolü
            if self.lbl_ai_pro_countdown is not None:
                self.lbl_ai_pro_countdown.setText("--:--")
                self.lbl_ai_pro_countdown.setStyleSheet(
                    "font-size: 16pt; font-weight: bold; color: #10b981; min-width: 60px;"
                )
            self.btn_start_ai_pro.setText("🚀 AI Uygulamayı Başlat (1Hz)")
            self.btn_start_ai_pro.setStyleSheet("""
                QPushButton {
                    background-color: #3b82f6; 
                    color: white;
                    font-weight: bold;
                    border-radius: 8px;
                }
            """)
            self.stop_all_coils() # Uygulama bittiğinde bobinleri kapat
            self._show_toast("AI Pro cihaza veri aktarımı durduruldu.", "info")
            return
            
        # Start Tracking
        self.ai_pro_tracking_active = True

        # Geri sayim baslat
        if hasattr(self, 'spin_ai_pro_duration') and hasattr(self, '_ai_pro_session_timer'):
            self._ai_pro_remaining_secs = self.spin_ai_pro_duration.value() * 60
            self._ai_pro_session_timer.start()
            self._update_countdown_label()

        # ESP32'leri UDP dinleme moduna almak icin SYNC_ALL gonder.
        # KRITIK: duty=0 -> ESP PWM balatmaz, sadece UDP dinlemeye hazirlanir.
        # Gercek duty degerleri ilk kamera tahminiyle _send_udp_live_update'ten gelecek.
        batch_command = {
            "command": "SYNC_ALL",
            "coils": {}
        }
        for i in range(7):
            coil_id = i + 1
            start_freq = 100  # AI Pro her zaman 100 Hz senkronizasyonu gerektirir

            if coil_id in self.coil_controls:
                self.coil_controls[coil_id]['freq_spin'].setValue(100)

            batch_command["coils"][str(coil_id)] = {
                "freq": start_freq,
                "duty": 0.0,   # PWM BASLATMA: ilk UDP frame'i gelene kadar sifir
                "duration": 60
            }
            
        if self.main_window and hasattr(self.main_window, 'batch_coil_control_requested'):
            self.main_window.batch_coil_control_requested.emit(batch_command)
            
        self.btn_start_ai_pro.setText("🛑 AI Uygulamayı Durdur")
        self._show_toast("AI Pro cihaza veri aktarımı başladı.", "success")

    def _ai_pro_tick(self):
        """Her saniye cagrilan geri sayim ticki."""
        self._ai_pro_remaining_secs -= 1
        self._update_countdown_label()

        if self._ai_pro_remaining_secs <= 0:
            # Sure doldu -- otomatik durdur
            self._ai_pro_session_timer.stop()
            self.btn_start_ai_pro.setChecked(False)
            self._toggle_ai_pro_tracking()  # stop branch'ini cagir
            self._show_toast("AI Pro seans suresi doldu, otomatik durduruldu.", "warning")

    def _update_countdown_label(self):
        """Kalan sureyi MM:SS formatinda goster."""
        # Rapor §4.3: hasattr yerine None kontrolü
        if self.lbl_ai_pro_countdown is None:
            return
        secs = max(0, self._ai_pro_remaining_secs)
        minutes, seconds = divmod(secs, 60)
        self.lbl_ai_pro_countdown.setText(f"{minutes:02d}:{seconds:02d}")
        # Son 60 saniyede kirmizi renk uyarisi
        color = "#ef4444" if secs <= 60 else "#10b981"
        self.lbl_ai_pro_countdown.setStyleSheet(
            f"font-size: 16pt; font-weight: bold; color: {color}; min-width: 60px;"
        )

    def _calculate_ai_recommendations(self):
        """Calculate target-only literature recommendations."""
        if not self.ai_controller or not AI_AVAILABLE:
            QMessageBox.warning(self, "AI Hatası", "AI controller kullanılamıyor.")
            return
        
        if not self.selected_patient:
            QMessageBox.warning(self, "Hasta Seçilmedi", "Lütfen önce bir hasta seçin.")
            return
        
        # UI'ı hazırla ve kilitle
        self.ai_calculate_btn.setEnabled(False)
        self.ai_message_label.setText("🔄 Literatür protokolü hesaplanıyor...")

        treatment_target = self.ai_target_combo.currentText()
        
        self.ai_calc_thread = AICalculationThread(self.ai_controller, treatment_target, self.selected_patient)
        self.ai_calc_thread.calculation_finished.connect(lambda rec: self._on_ai_calc_finished(rec, treatment_target))
        self.ai_calc_thread.error_occurred.connect(self._on_ai_calc_error)
        self.ai_calc_thread.start()

    def _on_ai_calc_finished(self, recommendation, treatment_target):
        try:
            if recommendation.get('status') != 'success':
                raise ValueError(recommendation.get('message', 'Bilinmeyen hata'))

            # Sonuçları UI'da göster
            final_freq = float(recommendation['frequency'])
            intensities = recommendation.get('intensities', [])
            final_duty = float(sum(intensities) / len(intensities)) if intensities else 0.0
            final_duration = int(recommendation['duration'])
            evidence = recommendation.get('evidence', 'unknown')
            source = recommendation.get('source', 'literature_exact')

            # Rapor §3.4: UI widget'ını state deposu olarak kullanmak yerine
            # öneriyi bu dict'te saklıyoruz; _start_ai_session buradan okur.
            self._last_ai_recommendation = {
                'frequency': final_freq,
                'duty': final_duty,
                'duration': final_duration,
                'intensities': intensities,
                'evidence': evidence,
                'source': source,
                'target': treatment_target,
            }

            self.ai_freq_value.setText(f"{final_freq} Hz")
            self.ai_intensity_value.setText(f"{final_duty:.1f} %")
            self.ai_duration_value.setText(f"{final_duration} dakika")
            
            # Kaynak ve kanıt seviyesi bilgisi
            source_text = {
                'literature_exact': 'Literatür (Tam Eşleşme)',
                'literature_keyword': 'Literatür (Anahtar Kelime Eşleşmesi)',
                'default_wellness': 'Varsayılan Wellness Protokolü'
            }.get(source, 'Bilinmiyor')
            
            evidence_emoji = {
                'high': '⭐⭐⭐⭐',
                'medium': '⭐⭐⭐',
                'unknown': '❓'
            }.get(evidence, '❓')

            self.ai_confidence_label.setText(f"Kanıt Seviyesi: {evidence_emoji}")
            
            self.ai_message_label.setText(
                f"✅ Öneriler hazır ({evidence_emoji})\n"
                f"Kaynak: {source_text}\n"
                f"Hedef: {treatment_target}"
            )
            
            # Log detaylı bilgi
            self.logger.info(
                f"AI Recommendation: {final_freq}Hz, {final_duty:.1f}%, {final_duration}min | "
                f"Source: {source}, Evidence: {evidence} | "
                f"Target: {treatment_target}"
            )
            
            # Buton ve durum güncelle
            self.ai_calculate_btn.setEnabled(True)
            self.ai_calculate_btn.setText("🔮 AI Parametre Hesapla")
            self.ai_start_btn.setEnabled(True)
            
        except Exception as e:
            self._on_ai_calc_error(str(e))

    def _on_ai_calc_error(self, error_msg):
        self.logger.error(f"AI parametre hesaplama hatası: {error_msg}")
        # Hasta seçiliyse butonu tekrar aç
        if hasattr(self, 'selected_patient') and self.selected_patient:
            self.ai_calculate_btn.setEnabled(True)
        else:
            self.ai_calculate_btn.setEnabled(False)
        self.ai_calculate_btn.setText("🔮 AI Parametre Hesapla")
        self.ai_start_btn.setEnabled(False)
        self.ai_message_label.setText(f"❌ Hata: {error_msg}")

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

            # Rapor §3.4: AI parametrelerini UI widget'ından değil, _last_ai_recommendation'dan oku.
            # UI widget'ı sadece gösterim amaçlıdır; gerçek state burada tutulur.
            if self._last_ai_recommendation:
                rec = self._last_ai_recommendation
                ai_freq      = rec.get('frequency')
                ai_intensity = rec.get('duty')
                ai_duration  = rec.get('duration')
                self.logger.debug(
                    f"AI parametreleri (cache): freq={ai_freq}, intensity={ai_intensity}, duration={ai_duration}"
                )
            else:
                # Geriye dönük uyumluluk: öneri yoksa UI'dan parse et (deprecated path)
                try:
                    freq_text      = self.ai_freq_value.text().replace(' Hz', '').strip()
                    intensity_text = self.ai_intensity_value.text().replace(' %', '').strip()
                    duration_text  = self.ai_duration_value.text().replace(' dakika', '').strip()
                    self.logger.warning(
                        "AI parametreleri UI widget'ından okunuyor (_last_ai_recommendation boş). "
                        "Önce 'Hesapla' butonuna basıldığından emin olun."
                    )
                    if freq_text and freq_text not in ('-', '--'):
                        ai_freq = float(freq_text)
                    if intensity_text and intensity_text not in ('-', '--'):
                        ai_intensity = float(intensity_text)
                    if duration_text and duration_text not in ('-', '--'):
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
                        font-size: 14pt;
                        font-weight: 700;
                    }
                """)
                
                # Durum güncellemeleri
                self.status_dot.setStyleSheet("color: #22c55e; font-size: 14pt;")
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
                    font-size: 14pt;
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
                font-size: 14pt;
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
    
    def _on_tab_changed(self, index):
        """Tab değiştiğinde çağrılır"""
        tab_name = self.tab_widget.tabText(index)
        
        if tab_name == " AI Pro":
            if self.camera_thread is None:
                self._start_camera_thread()
                
        elif tab_name == " Kedi Hastalık Analizi" and not getattr(self, 'cat_disease_loaded', False):
            from windows.tabs.cat_disease_tab import CatDiseaseTab
            for i in reversed(range(self.cat_disease_layout.count())): 
                widget_to_remove = self.cat_disease_layout.itemAt(i).widget()
                if widget_to_remove:
                    widget_to_remove.setParent(None)
            real_tab = CatDiseaseTab()
            self.cat_disease_layout.addWidget(real_tab)
            self.cat_disease_loaded = True

        elif tab_name == " Kedi Retikülosit Sayımı" and not getattr(self, 'feline_retic_loaded', False):
            from windows.tabs.feline_reticulocytes_tab import FelineReticulocytesTab
            for i in reversed(range(self.feline_retic_layout.count())): 
                widget_to_remove = self.feline_retic_layout.itemAt(i).widget()
                if widget_to_remove:
                    widget_to_remove.setParent(None)
            real_tab = FelineReticulocytesTab()
            self.feline_retic_layout.addWidget(real_tab)
            self.feline_retic_loaded = True

        elif tab_name == " Kedi Görüntü Analizi" and not getattr(self, 'cat_vision_loaded', False):
            from windows.tabs.cat_vision_tab import CatVisionTab
            for i in reversed(range(self.cat_vision_layout.count())): 
                widget_to_remove = self.cat_vision_layout.itemAt(i).widget()
                if widget_to_remove:
                    widget_to_remove.setParent(None)
            real_tab = CatVisionTab(parent=self)
            self.cat_vision_layout.addWidget(real_tab)
            self._real_cat_vision_tab = real_tab
            self.cat_vision_loaded = True
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
        
    def start_automatic_treatment(self, override_duration=None, override_target=None):
        """
        Otomatik tedavi başlat - BASITLEŞTIRILMIŞ YAPI
        
        Değişiklikler:
        - Session DB'ye kaydedilmiyor (sadece memory'de SessionState)
        - Main window session yaratmıyor (sadece UI güncelle)
        - Stop edildiğinde tek kayıt yapılacak
        - Android'den MQTT ile geldiğinde QInputDialog'u bypass eder (override_duration)
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

            if not self.main_window.mqtt_client.is_connected() and not getattr(self, 'stm_is_connected', False):
                self.show_warning("MQTT veya STM bağlantısı yok! Lütfen bağlantıyı kontrol edin.")
                return

            connected_coils = self._get_connected_coils()
            if not connected_coils:
                self.show_warning("Bağlı Bobin bulunamadı! Lütfen bobin bağlantılarını kontrol edin.")
                return

            # Süre kontrolü (Button click 'False' gönderebilir, isinstance ile kontrol et)
            if override_duration is not None and not isinstance(override_duration, bool):
                duration = int(override_duration)
            else:
                # GUI üzerindeki hazır auto_duration_spin değerini kullan (Diyalog sorusu kaldırıldı)
                duration = int(self.auto_duration_spin.value())

            # Parametreleri sabitle
            frequency = int(round(self.auto_frequency_spin.value()))
            duty_cycle = self.auto_duty_cycle_spin.value()
            intensity = self.auto_intensity_spin.value()
            target = override_target if override_target else self.target_combo.currentText()
            
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
            self.treatment_timer.start(duration * 60 * 1000)
            
            # Durum güncellemeleri
            self.status_dot.setStyleSheet("color: #f59e0b; font-size: 14pt;")
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
        if self._stop_in_progress.is_set():
            self.logger.debug("stop_treatment tekrar çağrısı engellendi")
            return

        if not self.treatment_active and not (self.active_session and self.active_session.is_active):
            self.logger.debug("stop_treatment no-op: aktif tedavi/session yok")
            return

        self._stop_in_progress.set()
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

                        if self.main_window and hasattr(self.main_window, 'coil_control_requested'):
                            self.main_window.coil_control_requested.emit(coil_id, command)
                        else:
                            self.logger.warning("coil_control_requested sinyali yok, stop komutu gönderilemedi")
                    
                    self.logger.info(f"{len(connected_coils)} bağlı bobine stop komutu gönderildi")
                else:
                    self.logger.warning("Bağlı bobin bulunamadı, stop komutu gönderilemedi")
            
            # === YENİ: Active session'ı DB'ye tek kayıt olarak yaz ===
            if self.active_session and self.active_session.is_active:
                # Stop reason'u set et
                self.active_session.stop_reason = stop_reason
                self.active_session.stop_time = datetime.now()  # HATA-5 FIX: durdurulma zamanını kaydet
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
                    species = self.active_session.patient_info.get('info', {}).get('species', None)
                    breed = self.active_session.patient_info.get('info', {}).get('breed', None)
                    owner = self.active_session.patient_info.get('info', {}).get('owner', None)
                    veterinarian = self.active_session.patient_info.get('info', {}).get('veterinarian', None)

                    self.logger.info(
                        f"Session saved to DB: id={session_id}, mode={self.active_session.mode}, "
                        f"patient={patient_name}, duration={actual_duration}min, reason={stop_reason}"
                    )
                    
                    # 1) MAIN_WINDOW'a session_id'yi verelim (Observation Notes vs. çalışması için)
                    if self.main_window:
                        self.main_window.current_session_id = session_id
                    
                    # 2) Android app'in Raporlar sayfasına MQTT'den senkronize edelim
                    try:
                        import json
                        
                        start_ts = int(self.active_session.start_time.timestamp() * 1000) if self.active_session.start_time else int(time.time() * 1000)
                        end_ts = int(self.active_session.stop_time.timestamp() * 1000) if self.active_session.stop_time else int(time.time() * 1000)
                        
                        active_esp_ids = [f"ESP_{coil_id:03d}" for coil_id in self.active_session.connected_coils]

                        report_data = {
                            "sessionId": session_id,
                            "patientName": patient_name,
                            "species": species,
                            "breed": breed,
                            "ownerName": owner,
                            "veterinarian": veterinarian,
                            "durationMinutes": int(actual_duration),
                            "frequencyHz": float(self.active_session.parameters.get("Frequency", 0.0)) if hasattr(self.active_session, 'parameters') else 0.0,
                            "treatmentMode": self.active_session.mode,
                            "targetRegion": self.active_session.target_condition.get('name', 'Unknown') if isinstance(self.active_session.target_condition, dict) else str(self.active_session.target_condition),
                            "startTimestampMs": start_ts,
                            "endTimestampMs": end_ts,
                            "activeEspIds": active_esp_ids,
                            "completedNormally": (stop_reason == "completed")
                        }
                        
                        if hasattr(self, 'main_window') and self.main_window and hasattr(self.main_window, 'mqtt_client') and self.main_window.mqtt_client:
                            self.main_window.mqtt_client.publish("pemf/system/reports", json.dumps(report_data), qos=1, retain=True)
                            self.logger.info(f"Published session {session_id} to pemf/system/reports")
                    except Exception as e_mqtt:
                        self.logger.error(f"MQTT Report publish failed: {e_mqtt}")

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
            
            # DB kayıt işlemini arka plana al (thread bloklamasını engeller)
            if hasattr(self, 'active_session') and self.active_session:
                from threading import Thread
                import copy
                
                # Sadece gerekli verileri kopyala (widget referansları vb. içermeyen)
                session_snapshot = copy.copy(self.active_session)
                
                def _save_session_task():
                    try:
                        self.logger.info("DB işlem thread başlatıldı: _save_session_task")
                        # DB kaydı - bu işlem I/O yoğun olabilir
                        session_id = self.db.save_completed_session(session_snapshot)
                        if session_id:
                            # Sinyal çağrısı yap ki QTimer main thread'de çalışsın
                            self._session_saved_signal.emit(session_id)
                    except Exception as ex:
                        self.logger.error(f"Seans veritabanına kaydedilirken hata oluştu: {ex}")
                
                # Thread'i başlat
                t = Thread(target=_save_session_task, daemon=True)
                t.start()
                
            # Log kaydet (eski auto_logger - backward compatibility)
            if hasattr(self, 'auto_logger'):
                self.auto_logger.log_treatment_event("stop", f"Seans durduruldu: {stop_reason}")
                
        except Exception as e:
            self.logger.error(f"Seans durdurulamadı: {e}", exc_info=True)
            self.show_error(f"Seans durdurulamadı: {str(e)}")
            if hasattr(self, 'auto_logger'):
                self.auto_logger.log_treatment_event("error", f"Seans durdurma hatası: {str(e)}")
        finally:
            self._stop_in_progress.clear()

    def _on_session_saved(self, session_id):
        """DB kaydı tamamlandığında ana thread'de çağrılan slot"""
        self.logger.info(f"Seans başarıyla kaydedildi: ID={session_id}")
        
        # Seans tamamlandıysa gözlem notları dialog'unu aç (Eğer seans düzgün oluşturulmuşsa)
        if self.main_window and hasattr(self.main_window, 'show_observation_notes_dialog'):
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(500, self.main_window.show_observation_notes_dialog)

    def _start_all_with_apply(self):
        # Apply global settings and start all coils
        self.apply_to_all_coils()
        self.start_all_coils()

    def apply_to_all_coils(self):
        """Ana parametreleri tüm bağlı bobinlere uygula - UI ve ESP'leri güncelle"""
        try:
            freq = self.master_freq_spin.value()
            duty = self.master_duty_spin.value()
            duration = self.master_duration_spin.value()
            phase = getattr(self, 'master_phase_spin', None)
            phase_val = phase.value() if phase else 0.0
            
            # 1. UI'daki tüm bobinlerin spin box'larını güncelle
            for coil_num in range(1, 9):
                controls = self.coil_controls[coil_num]
                controls['freq_spin'].setValue(freq)
                controls['duty_spin'].setValue(duty)
                controls['duration_spin'].setValue(duration)
                if 'phase_spin' in controls:
                    controls['phase_spin'].setValue(phase_val)
            
            # 2. Bağlı ESP'lere set_params komutu gönder
            if not self.main_window or not hasattr(self.main_window, 'mqtt_client') or not self.main_window.mqtt_client:
                self.show_warning("MQTT bağlantısı bulunamadı! UI güncellendi ancak bobinlere komut gönderilemedi.")
                return
            
            # MQTT bağlantısını kontrol et
            mqtt_connected = False
            if self.main_window.mqtt_client and self.main_window.mqtt_client.is_connected():
                mqtt_connected = True
            
            if not mqtt_connected and not getattr(self, 'stm_is_connected', False):
                self.show_warning("MQTT ve STM bağlantısı yok! UI güncellendi ancak bobinlere komut gönderilemedi.")
                return
            
            connected_coils = self._get_connected_coils()

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
                    "duty": int(round(float(duty))),  # HATA-4 FIX: float→int truncation önlendi
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
                
            # STM32 Manuel Kontrol Güncellemesi (Tüm UI parametreleri güncellendiği için)
            self._send_stm_manual_update()
            
        except Exception as e:
            self.logger.error(f"Error in apply_to_all_coils: {e}", exc_info=True)
            self.show_error(f"Parametreler uygulanırken hata oluştu: {str(e)}")

    # ------------------------------------------------------------------ #
    # OPTİMİSTİK UI DURUMU YÖNETİCİSİ                                      #
    # ------------------------------------------------------------------ #
    def _set_coil_ui_state(self, coil_num: int, state: str) -> None:
        """
        Bobin UI durumunu tek bir merkezden günceller.
        Durumlar:
          sync_waiting  – komut gönderildi, ESP ack bekleniyor (start için)
          running       – ESP çalışıyor (ACK başarılı)
          sending_stop  – stop komutu gönderildi, ACK bekleniyor
          stopped       – ESP durduruldu
          error         – komut başarısız / timeout
        """
        if coil_num not in self.coil_controls:
            return
        controls = self.coil_controls[coil_num]

        if state == "sync_waiting":
            # Komut gönderildi; kullanıcı dur diyebilmeli → stop_btn açık
            controls['status_led'].setStyleSheet("color: #3b82f6; font-size: 9pt;")
            controls['status_label'].setText("Senkron bekleniyor...")
            controls['status_container'].setStyleSheet("""
                background: rgba(59, 130, 246, 0.1);
                border-radius: 12px;
                border: 1px solid rgba(59, 130, 246, 0.3);
            """)
            controls['start_btn'].setEnabled(False)
            controls['stop_btn'].setEnabled(True)   # ← optimistik: iptal edilebilir

        elif state == "running":
            controls['status_led'].setStyleSheet("color: #22c55e; font-size: 9pt;")
            controls['status_label'].setText("Çalışıyor")
            controls['status_container'].setStyleSheet("""
                background: rgba(34, 197, 94, 0.1);
                border-radius: 12px;
                border: 1px solid rgba(34, 197, 94, 0.3);
            """)
            controls['start_btn'].setEnabled(False)
            controls['stop_btn'].setEnabled(True)

        elif state == "sending_stop":
            # Stop komutu gönderildi; kullanıcı yeniden başlatabilmeli → start_btn açık
            controls['status_led'].setStyleSheet("color: #f59e0b; font-size: 9pt;")
            controls['status_label'].setText("Durduruluyor...")
            controls['status_container'].setStyleSheet("""
                background: rgba(245, 158, 11, 0.1);
                border-radius: 12px;
                border: 1px solid rgba(245, 158, 11, 0.3);
            """)
            controls['start_btn'].setEnabled(True)  # ← optimistik: yeniden başlatılabilir
            controls['stop_btn'].setEnabled(False)

        elif state == "stopped":
            controls['status_led'].setStyleSheet("color: #ef4444; font-size: 9pt;")
            controls['status_label'].setText("Durduruldu")
            controls['status_container'].setStyleSheet("""
                background: rgba(239, 68, 68, 0.1);
                border-radius: 12px;
                border: 1px solid rgba(239, 68, 68, 0.3);
            """)
            controls['start_btn'].setEnabled(True)
            controls['stop_btn'].setEnabled(False)
            
        elif state == "idle":
            controls['status_led'].setStyleSheet("color: #6b7280; font-size: 9pt;")
            controls['status_label'].setText("Tamamlandı")
            controls['status_container'].setStyleSheet("""
                background: rgba(107, 114, 128, 0.1);
                border-radius: 12px;
                border: 1px solid rgba(107, 114, 128, 0.3);
            """)
            controls['start_btn'].setEnabled(True)
            controls['stop_btn'].setEnabled(False)

        elif state == "error":
            controls['status_led'].setStyleSheet("color: #ef4444; font-size: 9pt;")
            controls['status_label'].setText("Hata - Tekrar Dene")
            controls['status_container'].setStyleSheet("""
                background: rgba(239, 68, 68, 0.15);
                border-radius: 12px;
                border: 1px solid rgba(239, 68, 68, 0.5);
            """)
            controls['start_btn'].setEnabled(True)  # kullanıcı tekrar deneyebilir
            controls['stop_btn'].setEnabled(False)

    # ------------------------------------------------------------------ #

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
            
            # MQTT komutu oluştur (command_id ekle)
            command = {
                "command": "start",
                "command_id": command_id,
                "freq": freq,
                "duty": duty,
                "duration": duration,
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
            
            # OPTİMİSTİK UI: komut gönderilir gönderilmez stop_btn aktif olur
            # (kullanıcı 5sn sync buffer süresince iptal edebilir)
            self._set_coil_ui_state(coil_num, "sync_waiting")
            # UI kilið¸: 5sn sync buffer + 2sn margin boyunca ESP status'tan gelen
            # pwm_active=False mesajları butonu "Durduruldu"ya döndüremez
            self._coil_ui_locked_until[coil_num] = time.time() + 7.0

            self.logger.info(f"Coil {coil_num} start command requested via MainWindow signal: {command_id}")
            
            # STM32 Güncellemesini Tetikle (Tekil Bobin Start)
            self._send_stm_manual_update()

        except Exception as e:
            self._set_coil_ui_state(coil_num, "error")
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
            
            # OPTİMİSTİK UI: komut gönderilir gönderilmez start_btn aktif olur
            # (kullanıcı ACK beklenmeden yeniden başlatmayı deneyebilir)
            self._set_coil_ui_state(coil_num, "sending_stop")
            # UI kilidi: ACK + ESP işleme marjı boyunca titreme engellenir
            self._coil_ui_locked_until[coil_num] = time.time() + 3.0
            
            # STM UI Timer iptali
            if hasattr(self, '_stm_ui_timers') and coil_num in self._stm_ui_timers:
                self._stm_ui_timers[coil_num].stop()

            self.logger.info(f"Coil {coil_num} stop command requested via MainWindow signal: {command_id}")
            
            # STM32 Güncellemesini Tetikle (Tekil Bobin Stop)
            self._send_stm_manual_update()

        except Exception as e:
            self._set_coil_ui_state(coil_num, "error")
            self.show_error(f"Bobin {coil_num} durdurulamadı: {str(e)}")

    def _get_connected_coils(self) -> List[int]:
        """Bağlı olan ESP bobinlerinin listesini döndür."""
        connected_coils = []
        current_time = time.time()
        esp_timeout = getattr(self, 'ESP_TIMEOUT', 5.0)
        coil_status_map = getattr(self, 'coil_connection_status', {})
        last_status_map = getattr(self, 'coil_last_status_time', {})

        for coil_id in range(1, 9):
            if coil_id <= 5:
                # STM bobinleri: heartbeat/MQTT yok, sadece STM bağlantı durumu
                if getattr(self, 'stm_is_connected', False):
                    connected_coils.append(coil_id)
            else:
                # ESP bobinleri (6–8): eski heartbeat + MQTT mantığı devam
                last_status_time = last_status_map.get(coil_id, 0)
                heartbeat_ok = (last_status_time > 0 and
                                (current_time - last_status_time) <= esp_timeout)
                status_flag = coil_status_map.get(coil_id, False)
                if heartbeat_ok and status_flag:
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
            
            if not mqtt_connected and not getattr(self, 'stm_is_connected', False):
                self.show_warning("MQTT ve STM bağlantısı yok! Komut gönderilemiyor.")
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
                
                # OPTİMİSTİK UI: sync_waiting → stop_btn hemen aktif olur
                self._set_coil_ui_state(coil_id, "sync_waiting")
                self._coil_ui_locked_until[coil_id] = time.time() + 7.0
                
                # STM32 Manuel Mod Süre GUI Eşitlemesi
                if duration > 0 and getattr(self, 'stm_is_connected', False) and coil_id <= 5:
                    if not hasattr(self, '_stm_ui_timers'):
                        self._stm_ui_timers = {}
                    if coil_id in self._stm_ui_timers:
                        self._stm_ui_timers[coil_id].stop()
                    from PyQt6.QtCore import QTimer
                    timer = QTimer()
                    timer.setSingleShot(True)
                    timer.timeout.connect(lambda c=coil_id: self._set_coil_ui_state(c, "idle"))
                    timer.start(duration * 60000)
                    self._stm_ui_timers[coil_id] = timer
            
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
                
            # STM32 Manuel Kontrol Güncellemesi
            self._send_stm_manual_update()
            
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
            
            if not mqtt_connected and not getattr(self, 'stm_is_connected', False):
                self.show_warning("MQTT ve STM bağlantısı yok! Bağlı bobinlere komut gönderilemiyor.")
                return
            
            connected_coils = self._get_connected_coils()

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
                
                # OPTİMİSTİK UI: sending_stop → start_btn hemen aktif olur
                self._set_coil_ui_state(coil_id, "sending_stop")
                self._coil_ui_locked_until[coil_id] = time.time() + 3.0
                
                if hasattr(self, '_stm_ui_timers') and coil_id in self._stm_ui_timers:
                    self._stm_ui_timers[coil_id].stop()
            
            if commands_sent > 0:
                self.show_info(f"{commands_sent} bağlı bobin durduruldu (Toplam {len(connected_coils)} bağlı bobin)")
            else:
                self.show_warning("Hiçbir bobin durdurulamadı!")
                
            # STM32 Manuel Kontrol Güncellemesi
            self._send_stm_manual_update()
                
        except Exception as e:
            self.logger.error(f"Error in stop_all_coils: {e}", exc_info=True)
            self.show_error(f"Bobinler durdurulamadı: {str(e)}")

    def _connect_mqtt_signals(self):
        """MQTT sinyallerini bağla"""
        if self.main_window and hasattr(self.main_window, 'coil_status_updated'):
            self.main_window.coil_status_updated.connect(
                self.on_coil_status_updated,
                Qt.ConnectionType.QueuedConnection
            )
        if self.main_window and hasattr(self.main_window, 'esp_status_received'):
            # ESP durum güncellemelerini de dinle (bağlantı durumunu güncellemek için)
            self.main_window.esp_status_received.connect(
                self.on_esp_status_received,
                Qt.ConnectionType.QueuedConnection
            )
        if self.main_window and hasattr(self.main_window, 'sensor_data_updated'):
            self.main_window.sensor_data_updated.connect(
                self.on_sensor_data_updated,
                Qt.ConnectionType.QueuedConnection
            )
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
    
    def _update_connection_status_label(self, coil_id, is_connected, show_toast=True):
        """Bağlantı durumu label'ını güncelle ve bağlantı kesildiğinde sıcaklığı sıfırla"""
        if coil_id not in self.coil_controls:
            return
        
        controls = self.coil_controls[coil_id]
        if 'connection_status_label' not in controls:
            return
        
        label = controls['connection_status_label']
        if is_connected:
            if coil_id <= 5:
                label.setText("STM ✓")
                label.setToolTip("STM32 üzerinden kontrol ediliyor.")
            else:
                label.setText("Bağlı")
                label.setToolTip("Cihaz bağlı ve kontrol edilebilir durumda.")
            label.setStyleSheet("""
                font-size: 9pt; 
                font-weight: 600; 
                color: #22c55e;
                padding: 4px 8px;
                background: rgba(34, 197, 94, 0.15);
                border-radius: 8px;
                border: 1px solid rgba(34, 197, 94, 0.3);
            """)
        else:
            if coil_id <= 5:
                label.setText("Bağlantı Yok")
                label.setToolTip("Bağlantı bekleniyor.")
            else:
                label.setText("Bağlı Değil")
                label.setToolTip("Cihaz bağlantıyı yeniden kurmaya çalışıyor. Uzun süre düzelmezse yeniden eşleştirme gerekebilir.")
            label.setStyleSheet("""
                font-size: 9pt; 
                font-weight: 600; 
                color: #ef4444;
                padding: 4px 8px;
                background: rgba(239, 68, 68, 0.15);
                border-radius: 8px;
                border: 1px solid rgba(239, 68, 68, 0.3);
            """)
            
            # Kullanıcıyı notify et - BLE mekanizması açıklamasıyla (Debounced)
            if hasattr(self, 'show_warning') and show_toast and coil_id >= 6:
                if not hasattr(self, '_last_disconnect_toast_time'):
                    self._last_disconnect_toast_time = 0
                
                current_time = time.time()
                if current_time - self._last_disconnect_toast_time > 3.0: # 3 saniyede bir toast
                    self._last_disconnect_toast_time = current_time
                    from PyQt6.QtCore import QTimer
                    msg = f"Cihaz {coil_id} bağlantısı koptu. Yeniden bağlanma deneniyor."
                    QTimer.singleShot(0, lambda: self.show_warning(msg))
            
            # Bağlantı kesildiğinde sıcaklık gösterimini 0°C olarak ayarla
            temp_label = controls.get('temp_label')
            if temp_label:
                temp_label.setProperty("temp_status", "normal")
                temp_label.setText("0.0°C")
                temp_label.style().unpolish(temp_label)
                temp_label.style().polish(temp_label)
            
            # Sensor cache'i temizle
            if coil_id in self._last_sensor_values:
                self._last_sensor_values[coil_id].pop('temp', None)

    def _update_coil_connectivity(self, coil_id_int: int, status_data: dict):
        """Coil bağlantı/heartbeat durumunu merkezi olarak güncelle."""
        if 'mqtt_connected' in status_data:
            is_connected = bool(status_data.get('mqtt_connected', False))
            status_changed = False
            connected_count = 0
            with self.coil_status_lock:
                if self.coil_connection_status.get(coil_id_int, False) != is_connected:
                    self.coil_connection_status[coil_id_int] = is_connected
                    status_changed = True
                connected_count = sum(1 for status in self.coil_connection_status.values() if status)

            if status_changed:
                self._update_connection_status_label(coil_id_int, is_connected)
                
                # FAİLS-SAFE (Senaryo 3): Tedavi aktifken kopma yaşanırsa tüm cihazlar koptuysa tedaviyi durdur/iptal et
                if hasattr(self, 'treatment_active') and self.treatment_active and not is_connected:
                    if connected_count == 0:
                        self.logger.error("FAİLS-SAFE TETİKLENDİ: Tüm cihazların bağlantısı koptu (LWT). Tedavi ERROR moduna alınıyor.")
                        # Thread güvenli UI çağrısı
                        from PyQt6.QtCore import QTimer
                        QTimer.singleShot(0, lambda: self.stop_treatment(stop_reason="all_devices_offline"))
                        QTimer.singleShot(100, lambda: self.show_error("KRİTİK HATA: Tüm cihazların bağlantısı koptu!\nCihazlar güç dalgalanmasından resetlenmiş olabilir.\nTedavi güvenliğe alındı (Durduruldu)."))

        if status_data.get('mqtt_connected', False):
            with self.coil_status_lock:
                self.coil_last_status_time[coil_id_int] = time.time()

    def _safe_update_temperature_label(self, coil_id: int, temp: float):
        """Sadece ilgili bobinin sıcaklık label'ını güncelle."""
        last_temp = self._last_sensor_values.get(coil_id, {}).get('temp', -1.0)
        if abs(last_temp - temp) < 0.1:
            return

        self._last_sensor_values.setdefault(coil_id, {})['temp'] = temp

        if coil_id not in self.coil_controls:
            return

        temp_label = self.coil_controls[coil_id].get('temp_label')
        if not temp_label:
            return

        temp_label.setText(f"{temp:.1f}°C")

    
    def _safe_on_coil_status_updated(self, coil_id, status_data):
        """
        Bu fonksiyon %100 ana thread'de çalışır (QueuedConnection sayesinde).
        MQTT thread'inden gelen veriler burada güvenli bir şekilde UI'ı günceller.
        """
        try:
            # coil_id string olarak gelebilir, int'e çevir
            coil_id_int = int(coil_id) if isinstance(coil_id, str) else coil_id

            # Rapor §2.2.1: _cleanup_stale_esp_devices'tan gelen özel sinyal
            if status_data.get('_stale_cleanup'):
                self._update_connection_status_label(coil_id_int, False, show_toast=False)
                return

            if coil_id_int in self.coil_controls:
                controls = self.coil_controls[coil_id_int]

                self._update_coil_connectivity(coil_id_int, status_data)
                
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

                    # --- UI TİTREMESİ GUARD -----------------------------------
                    # Komut gönderildikten sonra ESP status mesajları henüz eski
                    # (pwm_active=False) durumu rapor edebilir. Kilit süresi veya
                    # bekleyen bir komut varken buton/durum etiketine dokunma.
                    # Sensör verileri (sıcaklık, akım) aşağıda normal şekilde güncellenir.
                    with self.pending_commands_lock:
                        _has_pending = any(
                            info['coil_num'] == coil_id_int
                            for info in self.pending_commands.values()
                        )
                    _ui_locked = (
                        _has_pending
                        or time.time() < self._coil_ui_locked_until.get(coil_id_int, 0.0)
                    )
                    # ----------------------------------------------------------

                    if not _ui_locked:
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
                    else:
                        self.logger.debug(
                            "Coil %s UI ünleme kilidinde, status titremesı engellendi "
                            "(pending=%s, lock_remaining=%.2fs)",
                            coil_id_int, _has_pending,
                            max(0.0, self._coil_ui_locked_until.get(coil_id_int, 0.0) - time.time())
                        )
                
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
                command_type = cmd_info['command']['command']

                if command_type == "start":
                    freq_value = cmd_info['command'].get('freq', 0)
                    duty_value = cmd_info['command'].get('duty', 0.0)
                    duration_value = cmd_info['command'].get('duration', 0)

                    with self.pwm_status_lock:
                        self.pwm_status[coil_num]['running'] = True
                        self.pwm_status[coil_num]['freq'] = freq_value
                        self.pwm_status[coil_num]['duty'] = duty_value
                        self.pwm_status[coil_num]['duration'] = duration_value

                    # Spinbox'ları güncelle (Android app'ten gelen komutlar için)
                    if coil_num in self.coil_controls:
                        controls = self.coil_controls[coil_num]
                        for key, val, cast in (
                            ('freq_spin', freq_value, int),
                            ('duty_spin', duty_value, float),
                            ('duration_spin', duration_value, int),
                        ):
                            try:
                                controls[key].setValue(cast(val))
                            except (ValueError, TypeError) as e:
                                self.logger.warning(f"Bobin {coil_num} {key} geçersiz değer {val}: {e}")

                    self._set_coil_ui_state(coil_num, "running")

                    # Kalan süreyi güncelle
                    duration = cmd_info['command'].get('duration', 0)
                    if duration and duration > 0:
                        self.pwm_remaining_time[coil_num] = duration * 60
                    else:
                        self.pwm_remaining_time[coil_num] = None
                    self._update_coil_remaining_time_display(coil_num)

                elif command_type in ("stop", "set_params"):
                    if command_type == "stop":
                        with self.pwm_status_lock:
                            self.pwm_status[coil_num]['running'] = False
                        self._set_coil_ui_state(coil_num, "stopped")
                    # set_params için UI değişmez (durum zaten sync_waiting/running)

                self.logger.info(f"Command ACK received: {command_id} - SUCCESS")
            else:
                # Komut başarısız (ESP reddetti)
                self._set_coil_ui_state(coil_num, "error")
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
    
    def set_stm_connected(self, connected: bool):
        """
        MainWindow'dan çağrılır. STM bağlantı durumunu UCW'de günceller.
        Coil 1–5'i bağlı/kopuk olarak işaretler ve UI'ı yeniler.
        """
        self.stm_is_connected = connected
        # coil_connection_status 1–5'i güncelle
        for coil_id in range(1, 6):
            self.coil_connection_status[coil_id] = connected
            self._update_connection_status_label(coil_id, connected, show_toast=False)
        # UCW header güncelle
        self._on_stm_connected(connected)

    def _on_stm_connected(self, connected: bool):
        """STM32 UI güncellemeleri (sadece UCW görsel kısmı)."""
        try:
            if connected:
                if hasattr(self, 'status_text'):
                    self.status_text.setText("STM Bağlandı (5 Bobin)")
                    self.status_text.setStyleSheet("color:#22c55e; font-size: 11pt; font-weight:700;")
                if hasattr(self, 'status_subtext'):
                    self.status_subtext.setText("Donanım iletişimi aktif")
                if hasattr(self, 'status_dot'):
                    self.status_dot.setText("✓")
                    self.status_dot.setStyleSheet("color:#22c55e; font-size: 12pt; font-weight:bold;")
                if hasattr(self, 'ai_pro_result_labels') and self.ai_pro_result_labels:
                    for i in range(1, 6):
                        if i in self.ai_pro_result_labels:
                            lbl = self.ai_pro_result_labels[i]['status']
                            lbl.setText("Onaylandı ✅")
                            lbl.setStyleSheet("color:#22c55e; font-weight:bold;")
            else:
                if hasattr(self, 'status_text'):
                    self.status_text.setText("STM Bağlantısı Yok")
                    self.status_text.setStyleSheet("color:#ef4444; font-size: 11pt; font-weight:700;")
        except Exception as e:
            self.logger.error(f"_on_stm_connected HATA: {e}", exc_info=True)

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
        MQTT thread'inden çağrılır.
        Sensor data gösterimi MainWindow ve SensorDataWindow'da yapılıyor.
        WebSocket server'a iletme MainWindow tarafından yapılıyor.
        
        PWM durumu sensor mesajından da gelebilir, bu durumda UI'ı güncelle.
        """
        try:
            # coil_id'yi int'e çevir
            coil_id_int = int(coil_id) if isinstance(coil_id, str) else coil_id
            
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
                temp = sensor_data.get('object_temp', None)
                if temp is None:
                    temp = sensor_data.get('temperature', None)
                # None kontrolü ve tip kontrolü (TypeError önleme)
                if temp is not None and isinstance(temp, (int, float)):
                    self._safe_update_temperature_signal.emit(coil_id_int, float(temp))
                    
                    # Yüksek sıcaklık uyarısı
                    if temp > 60:
                        # Anında uyarı gönder
                        self._safe_update_sensor_warning_signal.emit(
                            coil_id_int, 
                            f"Bobin {coil_id_int} yüksek sıcaklık: {temp:.1f}°C", 
                            "warning"
                        )
                        
            # PID (Hata düzeltme) Döngüsü İçin Manyetik Alan Verisi Kaydı
            if 'mag_field' in sensor_data:
                mag = sensor_data.get('mag_field')
                if mag is not None:
                    with self.last_mag_measurements_lock:
                        self.last_mag_measurements[coil_id_int] = float(mag)
            elif 'magnetic_field' in sensor_data:
                mag = sensor_data.get('magnetic_field')
                if mag is not None:
                    with self.last_mag_measurements_lock:
                        self.last_mag_measurements[coil_id_int] = float(mag)

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
            
            event_type = status_data.get('event_type')
            if event_type == 'selftest_ok':
                self._show_toast(f"✅ Bobin {coil_id_int} Self-Test BAŞARILI!", "success")
                if self.ai_pro_result_labels is not None and coil_id_int in self.ai_pro_result_labels:
                    lbl = self.ai_pro_result_labels[coil_id_int]['status']
                    lbl.setText("Çalışıyor ✅")
                    lbl.setStyleSheet("color: #10b981; font-weight: bold;")
                return
            elif event_type == 'selftest_fail':
                reason = status_data.get('message', 'Self-Test eşiği sağlanamadı.')
                self._show_toast(f"🚨 Bobin {coil_id_int} Self-Test BAŞARISIZ! {reason}", "error")
                if self.ai_pro_result_labels is not None and coil_id_int in self.ai_pro_result_labels:
                    lbl = self.ai_pro_result_labels[coil_id_int]['status']
                    lbl.setText("Devre Dışı ❌")
                    lbl.setStyleSheet("color: #ef4444; font-weight: bold;")
                return

            if coil_id_int in range(1, 9) and coil_id_int in self.coil_controls:
                self._update_coil_connectivity(coil_id_int, status_data)
                    
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
            status_changed = False
            with self.coil_status_lock:
                if self.coil_connection_status.get(coil_id, False):       
                    self.coil_connection_status[coil_id] = False
                    status_changed = True
            
            if status_changed:
                self._update_connection_status_label(coil_id, False, show_toast=False)
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

    def show_info(self, message):
        """Bilgi mesajı göster - Modern toast notification"""
        self.status_bar.showMessage(f"INFO: {message}", 3000)
        self._show_toast(message, "info")
        
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
            message_label.setStyleSheet("font-size: 11pt; font-weight: 600;")
            
            # Close button
            close_btn = QPushButton("×")
            close_btn.setFixedSize(24, 24)
            close_btn.setStyleSheet("""
                QPushButton {
                    background: transparent;
                    border: none;
                    font-size: 14pt;
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
            QTimer.singleShot(4000, toast.deleteLater)
            
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
    
    def _update_pwm_countdowns(self):
        pass

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
            
            # 5. Broadcast UDP for manual mode
            if not getattr(self, 'ai_pro_tracking_active', False):
                self._send_manual_udp_update()
            
            # 6. STM32 Keepalive: Watchdog 1500ms'de kapatıyor, 1Hz'de besle
            if getattr(self, 'stm_is_connected', False):
                active_stm_coils = [
                    i for i in range(1, 6)
                    if i in self.coil_controls
                    and not self.coil_controls[i]['start_btn'].isEnabled()
                ]
                if active_stm_coils:
                    self._send_stm_manual_update()
                
        except Exception as e:
            self.logger.error(f"Unified 1Hz tick error: {e}", exc_info=True)

    def _send_manual_udp_update(self):
        """Send 1Hz UDP packets based on Manual GUI spinbox values when AI is not predicting."""
        try:
            # We need 8 coil values (duties 0.0 to 1.0 format relative to 100%, phases 0-360)
            duties = []
            phases = []
            for i in range(1, 9):
                if i in self.coil_controls:
                    # Sadece PWM aktifse duty değerini gönder, değilse 0 yolla
                    is_running = False
                    with self.pwm_status_lock:
                        is_running = self.pwm_status.get(i, {}).get('running', False)
                    
                    if is_running:
                        # GUI shows duty 0-50, _send_udp_live_update expects 0.0-0.5
                        duty = float(self.coil_controls[i]['duty_spin'].value()) / 100.0
                    else:
                        duty = 0.0
                        
                    duties.append(duty)
                    # For manual mode phase shift isn't explicitly defined in GUI usually except TIM offsets, let's use 0 for now or derive
                    phases.append(0.0)
                else:
                    duties.append(0.0)
                    phases.append(0.0)
                    
            if hasattr(self, '_send_udp_live_update'):
                self._send_udp_live_update(duties, phases)
        except Exception as e:
            self.logger.error(f"Manual UDP update error: {e}", exc_info=True)

    def _load_patient_list(self):
        """Hasta listesini veritabanından arka planda yükle ve combo box'a ekle (Performance Fix - QThread with cleanup)"""
        try:
            if not hasattr(self, 'app_data_dir'):
                return
            
            # Zaten yükleme devam ediyorsa UI thread'i bloklamadan yeniden yükleme isteğini kuyruğa al.
            if self._patient_list_thread is not None:
                try:
                    if self._patient_list_thread.isRunning():
                        self._patient_list_reload_pending = True
                        self.logger.debug("Hasta listesi yükleniyor; yeniden yükleme isteği kuyruğa alındı.")
                        return
                except (RuntimeError, AttributeError):
                    # Thread nesnesi Qt tarafından temizlenmiş olabilir.
                    self._patient_list_thread = None
            
            # Yeni thread oluştur ve başlat
            self._patient_list_thread = PatientListLoadThread(self.app_data_dir)
            self._patient_list_thread.patients_loaded.connect(self._on_patients_loaded)
            self._patient_list_thread.error_occurred.connect(self._on_patient_load_error)
            self._patient_list_thread.finished.connect(self._on_patient_list_thread_finished)
            self._patient_list_thread.finished.connect(self._patient_list_thread.deleteLater)
            self._patient_list_thread.start()
            
            self.logger.debug("Hasta listesi arka planda yüklenmeye başladı...")
        except Exception as e:
            self.logger.error(f"Hasta listesi yüklenirken hata: {e}", exc_info=True)

    def _on_patient_list_thread_finished(self):
        """Hasta listesi thread temizliği ve gerekirse bekleyen yeniden yükleme tetikleme."""
        self._patient_list_thread = None
        if self._patient_list_reload_pending:
            self._patient_list_reload_pending = False
            QTimer.singleShot(0, self._load_patient_list)
    
    def _on_patients_loaded(self, patients_sorted):
        """Hasta listesi yüklendiğinde çağrılır (GUI thread'de çalışır)"""
        try:
            # Otomatik Mod combo box'ı temizle ve doldur
            if hasattr(self, 'patient_combo'):
                self.patient_combo.clear()
                self.patient_combo.addItem("Hasta Seçin...", None)
                for patient in patients_sorted:
                    name = patient.get("name", "İsimsiz")
                    species = patient.get("species", "")
                    display_text = f"{name} ({species})" if species else name
                    self.patient_combo.addItem(display_text, patient)
                if hasattr(self, "delete_selected_patient_btn"):
                    self.delete_selected_patient_btn.setEnabled(len(patients_sorted) > 0)
                if hasattr(self, "delete_all_patients_btn"):
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
            
            cmd_info = self.pending_commands[command_id].copy()
            coil_num = cmd_info['coil_num']
            retry_count = cmd_info['retry_count']
            command_copy = copy.deepcopy(cmd_info['command'])
        
        if retry_count < self.max_command_retries:
            # Retry
            with self.pending_commands_lock:
                if command_id in self.pending_commands:
                    self.pending_commands[command_id]['retry_count'] += 1
                    self.pending_commands[command_id]['timestamp'] = time.time()
            
            # MQTT ile tekrar gönder (Signal kullanarak)
            if self.main_window and hasattr(self.main_window, 'coil_control_requested'):
                self.main_window.coil_control_requested.emit(coil_num, command_copy)
            
            self.logger.warning(f"Command timeout, retrying ({retry_count + 1}/{self.max_command_retries}): {command_id}")
            
        else:
            # Max retry aşıldı, fail
            with self.pending_commands_lock:
                if command_id in self.pending_commands:
                    del self.pending_commands[command_id]
            
            # Timeout sonrası hata durumu — start_btn açılır, kullanıcı tekrar deneyebilir
            self._set_coil_ui_state(coil_num, "error")
            self.show_error(f"Bobin {coil_num} komutu başarısız (timeout)")
            self.logger.error(f"Command failed after {self.max_command_retries} retries: {command_id}")
    
    def _check_esp_connections(self):
        """
        ESP bağlantılarını heartbeat'e göre kontrol et.
        Sadece MQTT bağlantısı kontrol edilir - MQTT bağlıysa ESP bağlı sayılır.
        Belirli bir süre içinde status mesajı gelmezse bağlantı kesilmiş sayılır.
        """
        # MQTT bağlantısını kontrol et
        mqtt_connected = False
        if self.main_window and hasattr(self.main_window, 'mqtt_client'):
            if self.main_window.mqtt_client and self.main_window.mqtt_client.is_connected():
                mqtt_connected = True
        
        current_time = time.time()
        
        to_update = []
        with self.coil_status_lock:
            for coil_id in range(1, 9):
                # STM32 bağlıysa ilk 5 bobin kopuk (timeout) olamaz!
                if getattr(self, 'stm_is_connected', False) and 1 <= coil_id <= 5:
                    if not self.coil_connection_status.get(coil_id, False):
                        self.coil_connection_status[coil_id] = True
                        to_update.append((coil_id, True, f"Coil {coil_id} STM üzerinden zorunlu olarak bağlı işaretlendi"))
                    continue

                # MQTT bağlı değilse kalan bobinleri bağlı değil olarak işaretle
                if not mqtt_connected:
                    if self.coil_connection_status.get(coil_id, False):
                        self.coil_connection_status[coil_id] = False
                        to_update.append((coil_id, False, f"Coil {coil_id} için MQTT bağlantısı yok - bağlantı kesildi olarak işaretlendi"))
                else:
                    # MQTT bağlı, heartbeat kontrolü yap
                    last_status_time = self.coil_last_status_time.get(coil_id, 0)
                    
                    # Timeout check inside lock to prevent race condition
                    if last_status_time > 0 and (current_time - last_status_time > self.ESP_TIMEOUT):
                        if self.coil_connection_status.get(coil_id, False):
                            # Bağlantı kesilmiş, durumu güncelle
                            self.coil_connection_status[coil_id] = False
                            to_update.append((coil_id, False, f"Coil {coil_id} için heartbeat timeout - bağlantı kesildi olarak işaretlendi"))
                            
        for coil_id, status, msg in to_update:
            self._update_connection_status_label(coil_id, status)
            self.logger.debug(msg)
    
    def _get_next_command_id(self, coil_num):
        """
        Thread-safe command ID üreteci — itertools.count ile lock'suz.

        Rapor §2.2.3: threading.Lock yerine itertools.count kullanımı;
        Python'da next(itertools.count) GIL altında atomiktir, lock gereksizdir.

        Args:
            coil_num (int): Coil number (1-8)

        Returns:
            str: Unique command ID format: "cmd_{coil_num}_{counter}_{timestamp_ms}"
        """
        n = next(self._cmd_counter) % self.MAX_COMMAND_ID_COUNTER
        return f"cmd_{coil_num}_{n}_{int(time.time() * self.MILLISECONDS_PER_SECOND)}"
    
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
        # NOT: Log _safe_handle_command_ack'da yazılıyor (duplicate log fix)
        self._safe_handle_ack_signal.emit(coil_num, command_id, success, cmd_info)
    
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
                        # Treatment timer timeout zaten stop_treatment çağırır
                        return
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
            if saved_tab == 0:
                self.current_mode = "automatic"
            elif saved_tab == 1:
                self.current_mode = "manual"
            else:
                self.current_mode = "ai"
        
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
        
    def _update_coil_remaining_time_display(self, coil_id_int):
        pass

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
                # MainWindow'un buffer'ındaki mevcut durumu al with mutex
                all_coils_status = {}
                self.main_window.esp_status_buffer_mutex.lock()
                try:
                    all_coils_status = dict(self.main_window.esp_status_buffer)
                finally:
                    self.main_window.esp_status_buffer_mutex.unlock()

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
                            status_changed = False
                            with self.coil_status_lock:
                                if self.coil_connection_status.get(coil_id_int, False) != is_connected:
                                    self.coil_connection_status[coil_id_int] = is_connected
                                    status_changed = True
                            
                            if status_changed:
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
                            self._update_widget_property(controls['status_led'], "status_led", "running")
                            controls['status_label'].setText("Çalışıyor")
                            self._update_widget_property(controls['status_container'], "status_container", "running")
                            controls['start_btn'].setEnabled(False)
                            controls['stop_btn'].setEnabled(True)
                        else:
                            self._update_widget_property(controls['status_led'], "status_led", "stopped")
                            controls['status_label'].setText("Durduruldu")
                            self._update_widget_property(controls['status_container'], "status_container", "stopped")
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
                            
                            with self.pwm_remaining_time_lock:
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
                            with self.pwm_remaining_time_lock:
                                self.pwm_remaining_time[coil_id_int] = None
                        
                        # Remaining time display'ini güncelle
                        self._update_coil_remaining_time_display(coil_id_int)
                        # Countdown timer'ı yönet
                        # Timer management removed - using unified_1hz_timer (Performance Optimization)

                    else:
                        # Bu bobin için MainWindow'da durum bilgisi yok (henüz görülmedi)
                        with self.coil_status_lock:
                            self.coil_connection_status[coil_id_int] = False
                        self._update_connection_status_label(coil_id_int, False, show_toast=False)
                        # Durumu 'Durduruldu' olarak ayarla (default)
                        self._update_widget_property(controls['status_led'], "status_led", "stopped")
                        controls['status_label'].setText("Durduruldu")
                        self._update_widget_property(controls['status_container'], "status_container", "stopped")
                        controls['start_btn'].setEnabled(True)
                        controls['stop_btn'].setEnabled(False)
                        
                        # Clear remaining time when stopped
                        with self.pwm_remaining_time_lock:
                            self.pwm_remaining_time[coil_id_int] = None
                        self._update_coil_remaining_time_display(coil_id_int)
                        # Timer management removed - using unified_1hz_timer (Performance Optimization)
                        
        except Exception as e:
            self.logger.warning(f"_synchronize_status_from_main_window hatası: {e}", exc_info=True)
    
    def showEvent(self, event):
        """Pencere gösterildiğinde çağrılır"""
        super().showEvent(event)
        
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
        
        # Tüm timer'ları durdur ve temizle
        timer_list = [
            ('treatment_timer', 'Seans timer'),
            ('unified_1hz_timer', 'Unified 1Hz timer'),
            ('esp_connection_check_timer', 'ESP connection check timer'),
            ('esp_cleanup_timer', 'ESP cleanup timer')
            # pwm_countdown_timer removed - merged into unified_1hz_timer (Performance Optimization)
        ]

        for timer_attr, timer_name in timer_list:
            try:
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
                # Thread referansını local'e al: finished callback aynı anda None yapabilir
                thread = self._patient_list_thread
                self._patient_list_thread = None
                try:
                    # FIXED: Safe thread check - wrapped C++ object error prevention
                    if thread.isRunning():
                        # Database reader thread'ine terminate atilmaz, DB lock/corruption riski var
                        thread.requestInterruption()
                        thread.wait(1000)
                except (RuntimeError, AttributeError):
                    # Thread already deleted (deleteLater called)
                    self.logger.debug("Patient list thread already deleted")
                finally:
                    # Don't call deleteLater() here - it's already connected to finished signal
                    # Just set to None to release reference
                    self.logger.debug("Hasta listesi yükleme thread'i temizlendi")
        except Exception as e:
            self.logger.error(f"Hasta listesi thread temizlenirken hata: {e}")
        
        # AI model load thread'ini temizle (Thread Safety - Graceful Shutdown)
        try:
            if hasattr(self, 'ai_model_load_thread') and self.ai_model_load_thread is not None:
                try:
                    if self.ai_model_load_thread.isRunning():
                        self.ai_model_load_thread.stop_requested = True
                        # Asla .terminate() atma! Modeller iniyorsa (QProgressDialog) GUI donup kalır.
                        # Sadece çok kısa bekle, inme sürüyorsa serbest bırakıp arka planda tamamlanmasını sağla.
                        self.ai_model_load_thread.wait(500)
                except RuntimeError:
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
                    if self.calc_thread.isRunning():
                        if hasattr(self.calc_thread, 'stop_requested'):
                            self.calc_thread.stop_requested = True
                        
                        # Yine terminate etmiyoruz. Sinyalleri koparıp bırakıyoruz.
                        self.calc_thread.wait(500)
                except RuntimeError:
                    self.logger.debug("AI calculation thread already deleted")
                finally:
                    self.calc_thread = None
                    self.logger.debug("AI calculation thread'i temizlendi")
        except Exception as e:
            self.logger.error(f"AI calculation thread temizlenirken hata: {e}")
        
        # Kamera thread'ini temizle
        try:
            if hasattr(self, 'camera_thread') and self.camera_thread is not None:
                try:
                    try:
                        self.camera_thread.frame_ready.disconnect()
                        self.camera_thread.prediction_ready.disconnect()
                        self.camera_thread.error_occurred.disconnect()
                    except TypeError:
                        pass
                    
                    self.camera_thread._running = False
                    if self.camera_thread.isRunning():
                        self.camera_thread.stop()
                except (RuntimeError, AttributeError):
                    pass
                finally:
                    self.camera_thread = None
                    self.logger.debug("Kamera thread'i durduruldu")
        except Exception as e:
            self.logger.error(f"Kamera thread durdurulamadı: {e}")
        
        # Ana pencereyi aktif et
        try:
            if self.main_window:
                self.main_window.activateWindow()
        except Exception as e:
            self.logger.warning(f"Ana pencere aktif edilirken hata: {e}")
        
        self.logger.info("UnifiedControlWindow temizliği tamamlandı")
        
        # Pencereyi destroy etme, sadece gizle.
        # WA_DeleteOnClose kaldırıldı — TFLite/AI aynı process'te ikinci kez init edilemiyor.
        event.ignore()
        self.hide()


    def _adapt_for_compact_touch(self, profile) -> None:
        super()._adapt_for_compact_touch(profile)
        btn_h = profile.touch_safe_btn_height
        for group_attr in ("treatment_group", "patient_group", "coil_grid_group"):
            group = getattr(self, group_attr, None)
            if group and group.layout():
                m = profile.layout_margin
                group.layout().setContentsMargins(m, m + 4, m, m)
        patient_widget = getattr(self, "patient_info_widget", None)
        if patient_widget:
            patient_widget.setMaximumHeight(profile.touch_safe_btn_height * 2)

    def _adapt_for_large_tv(self, profile) -> None:
        super()._adapt_for_large_tv(profile)
        f_title = profile.title_font_pt
        f_base  = profile.base_font_pt
        title_lbl = getattr(self, "title_label", None)
        if title_lbl:
            title_lbl.setStyleSheet(
                f"font-size: {f_title}pt; font-weight: 800; color: white; letter-spacing: -0.5px;"
            )
        tab_widget = getattr(self, "tab_widget", None)
        if tab_widget:
            tab_widget.setStyleSheet(
                tab_widget.styleSheet()
                + f"\nQTabBar::tab {{ font-size: {f_base}pt; min-height: {profile.min_button_height // 2}px; }}"
            )
        extra = profile.tv_padding_extra
        if extra > 0:
            coil_grid = getattr(self, "coil_grid_widget", None)
            if coil_grid and coil_grid.layout():
                coil_grid.layout().setSpacing(profile.layout_spacing + extra // 2)
