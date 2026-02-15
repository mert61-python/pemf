# -*- coding: utf-8 -*-
"""
KPI Dashboard Window
PEMF tedavi sisteminin KPI (Key Performance Indicators) göstergelerini yönetir

Gerçek Zamanlı Enerji İzleme:
- Akım sensöründen gelen veri ile güç ve enerji hesaplaması
- Voltaj = Akım × Direnç (9Ω)
- Güç = Voltaj × Akım = I² × R
- Enerji = Güç × Süre (Watt-hour)

KPI Metrikleri (Otomatik Hesaplama):

1. Tedavi Etkinliği (%):
   - Başarı oranı = (Başarılı tedavi sayısı / Toplam tedavi) × 100
   - Başarılı tedavi: 5-60 dakika arası süren tedaviler
   - Gerçek zamanlı güncellenir

2. Ortalama Tedavi Süresi (dakika):
   - Toplam tedavi süresi / Tedavi sayısı
   - Aktif tedaviler dahil hesaplanır
   - Her tedavi bitiminde güncellenir

3. Enerji Tüketimi (kWh/seans):
   - Akım sensöründen hesaplanan toplam enerji / Seans sayısı
   - I² × R formülü ile güç hesaplanır
   - Her saniye güncellenir

4. Cihaz Çalışma Oranı (%):
   - (Aktif tedavi süresi / Toplam açık kalma süresi) × 100
   - Panel açıldığından itibaren hesaplanır
   - Gerçek zamanlı izlenir

5. Hasta Memnuniyeti (1-10 skor):
   - Otomatik Hesaplama:
     * Temel skor: 7.0
     * Süre optimizasyonu bonusu: +0.5 ile +1.5 (ideal: 15-20 dk)
     * Güvenlik bonusu: +0.5 ile +1.5 (alarm yokluğuna göre)
   - Manuel giriş de yapılabilir (callback ile kaydedilir)

6. Bakım Süresi (dk/gün):
   - Otomatik Tahmin:
     * Temel bakım: 5 dk/gün
     * Alarm bazlı: Her 10 alarm için +5 dk
     * Kullanım bazlı: %80 üzeri çalışma oranı için +10 dk
   - Manuel giriş de yapılabilir

Gerçek Zamanlı Göstergeler (Üst Panel):
- ⚡ Anlık Güç (W)
- 📊 Toplam Enerji (Wh/kWh)
- 🔄 Aktif Bobin Sayısı
- ⚙️ Ortalama Akım (A)

Veri Kaynakları:
- MQTT sensor data (pemf/coil/+/sensors)
- Treatment database (son 30 günlük kayıtlar)
- Gerçek zamanlı bobin durumu
"""

import sys
import os
import logging
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QGridLayout, QSizePolicy, QDoubleSpinBox, QSpinBox, QApplication,
    QGraphicsDropShadowEffect
)
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
import time
from collections import deque
from datetime import datetime

# Design System - Frozen exe compatible imports
try:
    from styles import StyleMixin
except ImportError:
    # Development mode fallback
    current_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(current_dir)
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)
    from styles import StyleMixin

# Responsive Utils
try:
    from utils.responsive_utils import get_screen_info
except ImportError:
    # Development mode fallback already handled by sys.path above
    from utils.responsive_utils import get_screen_info

class KPIDashboardWindow(QMainWindow, StyleMixin):
    """KPI Paneli - Design System entegrasyonu"""
    
    # Signal for real-time updates
    sensor_data_updated = pyqtSignal(str, dict)  # coil_id, sensor_data
    
    def __init__(self, main_window=None):
        super().__init__()
        self.setWindowTitle("Performans")
        self.main_window = main_window
        
        # Setup logger
        self.logger = logging.getLogger(__name__)
        
        # Gerçek zamanlı enerji izleme değişkenleri
        self.COIL_RESISTANCE = 9.0  # Ohm (bobin direnci)
        self.current_readings = {}  # coil_id -> deque of (timestamp, current_A)
        self.power_readings = {}    # coil_id -> deque of (timestamp, power_W)
        self.total_energy_wh = 0.0  # Watt-hour cinsinden toplam enerji
        self.session_start_time = None
        self.active_coils = set()   # Aktif bobinler
        
        # Her bobin için veri deque'ları (son 60 saniye)
        for coil_id in range(1, 9):
            self.current_readings[coil_id] = deque(maxlen=60)
            self.power_readings[coil_id] = deque(maxlen=60)
        
        # Tedavi istatistikleri
        self.treatment_count = 0
        self.total_treatment_duration_min = 0.0
        self.treatment_start_times = {}  # coil_id -> start_timestamp
        
        # Tedavi etkinliği ve hasta memnuniyeti izleme
        self.completed_treatments = []  # (timestamp, duration, success_rate, satisfaction)
        self.treatment_success_count = 0
        self.total_satisfaction_score = 0.0
        self.satisfaction_count = 0
        
        # Bakım ve hata izleme
        self.maintenance_events = []  # (timestamp, duration_minutes, reason)
        self.last_maintenance_time = None
        self.error_count = 0
        self.warning_count = 0
        
        # Sıcaklık ve alarm izleme
        self.high_temp_events = 0
        self.high_current_events = 0
        
        # Set window icon if available
        if main_window and hasattr(main_window, 'windowIcon') and not main_window.windowIcon().isNull():
            self.setWindowIcon(main_window.windowIcon())
        
        # Apply design system theme
        self.apply_theme()
        
        # Responsive window sizing (after theme is applied)
        self._setup_responsive_window()
        
        # Gerçek zamanlı güncelleme timer'ı (1 saniyede bir)
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self._update_realtime_kpis)
        self.update_timer.start(1000)  # 1 saniye
        
        # Başlangıç verilerini yükle (veritabanından)
        QTimer.singleShot(500, self._load_historical_data)
        
        # Create main widget and layout with shadow effect
        main_widget = QWidget(self)
        main_widget.setObjectName("mainWidget")
        self.setCentralWidget(main_widget)
        
        # Add shadow effect to main widget
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 100))
        shadow.setOffset(0, 4)
        main_widget.setGraphicsEffect(shadow)
        
        main_layout = QVBoxLayout(main_widget)
        main_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        main_layout.setContentsMargins(30, 30, 30, 30)
        main_layout.setSpacing(25)
        
        # Header with title and close button
        header = QWidget()
        header.setObjectName("header")
        header.setStyleSheet("""
            #header {
                background: transparent;
                border-bottom: 1px solid rgba(255, 255, 255, 0.1);
                padding-bottom: 15px;
            }
        """)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        
        # Title with icon
        title_container = QWidget()
        title_layout = QHBoxLayout(title_container)
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(12)
        
        # Add icon if available
        if hasattr(main_window, 'windowIcon') and not main_window.windowIcon().isNull():
            icon_label = QLabel()
            icon_pixmap = main_window.windowIcon().pixmap(32, 32)
            icon_label.setPixmap(icon_pixmap)
            title_layout.addWidget(icon_label)
        
        title_layout.addStretch()
        
        # Close button
        close_btn = QPushButton("×")
        close_btn.setFixedSize(32, 32)
        close_btn.setStyleSheet("""
            QPushButton {
                background: rgba(239, 68, 68, 0.1);
                color: #ef4444;
                border: 1px solid rgba(239, 68, 68, 0.3);
                border-radius: 8px;
                font-size: 20px;
                font-weight: bold;
                padding: 0;
                margin: 0;
            }
            QPushButton:hover {
                background: rgba(239, 68, 68, 0.2);
            }
            QPushButton:pressed {
                background: rgba(239, 68, 68, 0.3);
            }
        """)
        close_btn.clicked.connect(self.close)
        
        header_layout.addWidget(title_container, 1)
        header_layout.addWidget(close_btn, 0, Qt.AlignmentFlag.AlignRight)
        
        main_layout.addWidget(header)
        
        # Gerçek zamanlı enerji gösterge paneli
        realtime_panel = self._create_realtime_panel()
        main_layout.addWidget(realtime_panel)
        
        # KPI data with icons and colors (Enerji Tüketimi kaldırıldı - üst panel yeterli)
        kpis = [
            ("Tedavi Etkinliği", "%", "Tedavi sonrası hasta iyileşme oranının ölçümü.", 
             "Tedavinin biyolojik etkinliğini değerlendirin ve başarı oranını artırın.",
             "📊", "#3b82f6"),
            ("Ort. Tedavi Süresi", "dk", "Bir seansta uygulanan ortalama tedavi süresi.", 
             "Tedavi süresini optimize ederek verimliliği artırın.",
             "⏱️", "#10b981"),
            ("Cihaz Çalışma Oranı", "%", "Toplam çalışma süresi içindeki aktif kullanım oranı.", 
             "Cihazın kullanılabilirliğini ve güvenilirliğini ölçün.",
             "🔄", "#8b5cf6"),
            ("Hasta Memnuniyeti", "", "Tedavi sonrası memnuniyet skoru (1-10).", 
             "Kullanıcı memnuniyetini artırın ve geri bildirim toplayın.",
             "⭐", "#ec4899"),
            ("Bakım Süresi", "dk/gün", "Planlı duruşların toplam süresi.", 
             "Arızaları ve duruş nedenlerini analiz ederek sürekliliği sağlayın.",
             "🔧", "#6366f1")
        ]
        
        # Create scroll area for KPI cards
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        # Container for the grid
        container = QWidget()
        container.setObjectName("container")
        container.setStyleSheet("""
            #container {
                background: transparent;
                padding: 5px;
            }
        """)
        
        # Use a grid layout that adapts to window size
        grid = QGridLayout(container)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(20)
        grid.setVerticalSpacing(20)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        
        # Input widgets list
        self.input_widgets = []
        
        # Create KPI cards
        for i, (name, unit, definition, purpose, icon, color) in enumerate(kpis):
            # Create card with modern styling
            card = QWidget()
            card.setObjectName(f"card_{i}")
            card.setMinimumHeight(220)
            card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.MinimumExpanding)
            
            # Card styling with hover effect
            card.setStyleSheet(f"""
                #card_{i} {{
                    background: rgba(255, 255, 255, 0.05);
                    border: 1px solid rgba(255, 255, 255, 0.1);
                    border-radius: 16px;
                    padding: 0;
                }}
                #card_{i}:hover {{
                    background: rgba(255, 255, 255, 0.08);
                    border-color: {color}40;
                }}
            """)
            
            # Card layout with proper spacing
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(20, 20, 20, 20)
            card_layout.setSpacing(15)
            
            # Header with icon and title
            header = QWidget()
            header_layout = QHBoxLayout(header)
            header_layout.setContentsMargins(0, 0, 0, 0)
            header_layout.setSpacing(12)
            
            # Icon
            icon_label = QLabel(icon)
            icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            icon_label.setStyleSheet(f"""
                QLabel {{
                    font-size: 24px;
                    color: {color};
                    padding: 8px;
                    background: {color}20;
                    border-radius: 12px;
                    min-width: 40px;
                    min-height: 40px;
                    max-width: 40px;
                    max-height: 40px;
                }}
            """)
            
            # Title and unit
            title_widget = QWidget()
            title_layout = QVBoxLayout(title_widget)
            title_layout.setContentsMargins(0, 0, 0, 0)
            title_layout.setSpacing(2)
            
            title_label = QLabel(name)
            title_label.setStyleSheet(f"""
                QLabel {{
                    font-size: 16px;
                    font-weight: 600;
                    color: #ffffff;
                }}
            """)
            
            unit_label = QLabel(unit if unit else "")
            unit_label.setStyleSheet(f"""
                QLabel {{
                    font-size: 12px;
                    color: {color};
                    opacity: 0.8;
                }}
            """)
            
            title_layout.addWidget(title_label)
            if unit:
                title_layout.addWidget(unit_label)
            
            header_layout.addWidget(icon_label, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            header_layout.addWidget(title_widget, 1)
            
            # Input field with modern styling
            input_container = QWidget()
            input_layout = QHBoxLayout(input_container)
            input_layout.setContentsMargins(0, 0, 0, 0)
            input_layout.setSpacing(8)
            
            # Configure input widget based on KPI type
            if i == 0:  # Treatment Effectiveness
                input_widget = QDoubleSpinBox()
                input_widget.setSuffix(" %")
                input_widget.setRange(0, 100)
                input_widget.setDecimals(1)
                input_widget.setValue(78.0)
                input_widget.setSingleStep(0.1)
                # Safe callback with hasattr check
                def on_effectiveness_changed(val):
                    if self.main_window and hasattr(self.main_window, 'update_kpi_effectiveness'):
                        try:
                            self.main_window.update_kpi_effectiveness(val)
                        except Exception as e:
                            self.logger.warning(f"KPI effectiveness update failed: {e}")
                input_widget.valueChanged.connect(on_effectiveness_changed)
            elif i == 1:  # Average Treatment Duration
                input_widget = QDoubleSpinBox()
                input_widget.setSuffix(" min")
                input_widget.setRange(0, 120)
                input_widget.setDecimals(1)
                input_widget.setValue(15.0)
                input_widget.setSingleStep(0.5)
            elif i == 2:  # Device Operation Rate (Enerji Tüketimi kaldırıldı, indeks kaydı)
                input_widget = QDoubleSpinBox()
                input_widget.setSuffix(" %")
                input_widget.setRange(0, 100)
                input_widget.setDecimals(1)
                input_widget.setValue(95.0)
                input_widget.setSingleStep(0.5)
                # Safe callback with hasattr check
                def on_operation_rate_changed(val):
                    if self.main_window and hasattr(self.main_window, 'update_kpi_operation_rate'):
                        try:
                            self.main_window.update_kpi_operation_rate(val)
                        except Exception as e:
                            self.logger.warning(f"KPI operation rate update failed: {e}")
                input_widget.valueChanged.connect(on_operation_rate_changed)
            elif i == 3:  # Patient Satisfaction
                input_widget = QDoubleSpinBox()
                input_widget.setRange(1, 10)
                input_widget.setDecimals(1)
                input_widget.setValue(7.0)
                input_widget.setSingleStep(0.1)
                # Manuel giriş yapıldığında kaydet
                def on_satisfaction_changed(val):
                    self.satisfaction_count += 1
                    self.total_satisfaction_score += val
                    if self.main_window and hasattr(self.main_window, 'update_kpi_satisfaction'):
                        try:
                            self.main_window.update_kpi_satisfaction(val)
                        except Exception as e:
                            self.logger.warning(f"KPI satisfaction update failed: {e}")
                input_widget.valueChanged.connect(on_satisfaction_changed)
            else:  # Maintenance Time (i == 4)
                input_widget = QSpinBox()
                input_widget.setSuffix(" min")
                input_widget.setRange(0, 1440)
                input_widget.setValue(5)
                # Manuel bakım kaydı
                def on_maintenance_changed(val):
                    if val > 0:
                        self.maintenance_events.append({
                            'timestamp': time.time(),
                            'duration': val,
                            'type': 'manual_entry'
                        })
                    if self.main_window and hasattr(self.main_window, 'update_kpi_maintenance'):
                        try:
                            self.main_window.update_kpi_maintenance(val)
                        except Exception as e:
                            self.logger.warning(f"KPI maintenance update failed: {e}")
                input_widget.valueChanged.connect(on_maintenance_changed)
            
            # Style the input widget
            input_widget.setStyleSheet(f"""
                QSpinBox, QDoubleSpinBox {{
                    background: rgba(255, 255, 255, 0.05);
                    border: 1px solid rgba(255, 255, 255, 0.15);
                    border-radius: 8px;
                    padding: 8px 12px;
                    color: #ffffff;
                    font-size: 16px;
                    font-weight: 500;
                    min-height: 40px;
                    selection-background-color: {color};
                    selection-color: #ffffff;
                }}
                QSpinBox::up-button, QDoubleSpinBox::up-button {{
                    subcontrol-origin: border;
                    subcontrol-position: right;
                    width: 24px;
                    border-left: 1px solid rgba(255, 255, 255, 0.1);
                    border-radius: 0 8px 0 0;
                    background: rgba(255, 255, 255, 0.05);
                }}
                QSpinBox::down-button, QDoubleSpinBox::down-button {{
                    subcontrol-origin: border;
                    subcontrol-position: right;
                    width: 24px;
                    border-left: 1px solid rgba(255, 255, 255, 0.1);
                    border-top: 1px solid rgba(255, 255, 255, 0.05);
                    border-radius: 0 0 8px 0;
                    background: rgba(255, 255, 255, 0.05);
                }}
                QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
                    image: url('data:image/svg+xml;utf8,<svg fill=\"white\" height=\"24\" viewBox=\"0 0 24 24\" width=\"24\" xmlns=\"http://www.w3.org/2000/svg\"><path d=\"M7 14l5-5 5 5z\"/></svg>');
                    width: 16px;
                    height: 16px;
                }}
                QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
                    image: url('data:image/svg+xml;utf8,<svg fill=\"white\" height=\"24\" viewBox=\"0 0 24 24\" width=\"24\" xmlns=\"http://www.w3.org/2000/svg\"><path d=\"M7 10l5 5 5-5z\"/></svg>');
                    width: 16px;
                    height: 16px;
                }}
                QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
                QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{
                    background: rgba(255, 255, 255, 0.1);
                }}
                QSpinBox::up-button:pressed, QDoubleSpinBox::up-button:pressed,
                QSpinBox::down-button:pressed, QDoubleSpinBox::down-button:pressed {{
                    background: rgba(255, 255, 255, 0.15);
                }}
                QSpinBox:focus, QDoubleSpinBox:focus {{
                    border: 2px solid {color}80;
                    padding: 7px 11px;  /* Adjusted for border */
                }}
                QSpinBox:hover, QDoubleSpinBox:hover {{
                    border-color: {color}80;
                }}
            """)
            
            # Add input widget to layout
            input_layout.addStretch()
            input_layout.addWidget(input_widget)
            input_layout.addStretch()
            
            # KPI definition
            kpi_def = QLabel(definition)
            kpi_def.setWordWrap(True)
            kpi_def.setStyleSheet("""
                QLabel {
                    font-size: 13px;
                    color: #94a3b8;
                    line-height: 1.4;
                }
            """)
            
            # KPI purpose with color accent
            purpose_container = QWidget()
            purpose_container.setStyleSheet(f"""
                QWidget {{
                    background: {color}15;
                    border-left: 3px solid {color};
                    border-radius: 0 8px 8px 0;
                    padding: 8px 12px;
                }}
            """)
            purpose_layout = QHBoxLayout(purpose_container)
            purpose_layout.setContentsMargins(8, 6, 8, 6)
            
            purpose_icon = QLabel("💡")
            purpose_icon.setStyleSheet("font-size: 14px; margin-right: 8px;")
            
            kpi_purpose = QLabel(purpose)
            kpi_purpose.setWordWrap(True)
            kpi_purpose.setStyleSheet("""
                QLabel {
                    font-size: 12px;
                    color: #cbd5e1;
                    line-height: 1.4;
                }
            """)
            
            purpose_layout.addWidget(purpose_icon, 0, Qt.AlignmentFlag.AlignTop)
            purpose_layout.addWidget(kpi_purpose, 1)
            
            # Add all widgets to card layout
            card_layout.addWidget(header)
            card_layout.addWidget(input_container)
            card_layout.addWidget(kpi_def)
            card_layout.addWidget(purpose_container)
            card_layout.addStretch()
            
            # Store the input widget
            self.input_widgets.append(input_widget)
            
            # Add card to grid (responsive layout)
            row = i // 2
            col = i % 2
            grid.addWidget(card, row, col, 1, 1, alignment=Qt.AlignmentFlag.AlignTop)
            
            # Set stretch factors for responsive behavior
            grid.setRowStretch(row, 1)
            grid.setColumnStretch(col, 1)
        
        # Set up the scroll area
        scroll.setWidget(container)
        
        # Add scroll area to main layout with stretch factor
        main_layout.addWidget(scroll, 1)  # Add stretch factor to make it take remaining space
        
        # Set stretch for the scroll area
        main_layout.setStretch(1, 1)
        
        # Status bar
        self.statusBar().showMessage("Perormans parametreleri hazır")
        
        # Use native window frame with standard controls
        self.setWindowFlag(Qt.WindowType.WindowMinMaxButtonsHint, True)
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, True)
        
        # Set window style
        self.setStyleSheet("""
            QMainWindow {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #1e1b4b, stop:1 #4c1d95);
            }
            QWidget {
                font-family: 'Segoe UI', 'Arial', sans-serif;
                color: #e2e8f0;
            }
            QScrollArea {
                border: none;
                background: transparent;
            }
            QScrollBar:vertical {
                background: rgba(255, 255, 255, 0.1);
                width: 10px;
                margin: 0px;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical {
                background: rgba(255, 255, 255, 0.3);
                min-height: 30px;
                border-radius: 5px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            /* Style for the title bar */
            QWidget#titleBar {
                background: transparent;
                padding: 5px;
            }
            /* Style for the window */
            QMainWindow::title {
                color: white;
                font-size: 14px;
                font-weight: bold;
            }
        """)
    
    def _create_realtime_panel(self):
        """Gerçek zamanlı enerji izleme panelini oluştur"""
        panel = QWidget()
        panel.setObjectName("realtimePanel")
        panel.setStyleSheet("""
            #realtimePanel {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                    stop:0 rgba(59, 130, 246, 0.15),
                    stop:1 rgba(139, 92, 246, 0.15));
                border: 2px solid rgba(59, 130, 246, 0.3);
                border-radius: 16px;
                padding: 20px;
            }
        """)
        
        layout = QHBoxLayout(panel)
        layout.setSpacing(20)
        
        # Anlık Güç
        power_container = QWidget()
        power_layout = QVBoxLayout(power_container)
        power_layout.setSpacing(8)
        
        power_title = QLabel("⚡ Anlık Güç")
        power_title.setStyleSheet("""
            font-size: 14px;
            font-weight: 600;
            color: #f59e0b;
        """)
        
        self.realtime_power_label = QLabel("0.0 W")
        self.realtime_power_label.setStyleSheet("""
            font-size: 24px;
            font-weight: 700;
            color: #ffffff;
            background: rgba(245, 158, 11, 0.1);
            border-radius: 8px;
            padding: 8px 16px;
        """)
        
        power_layout.addWidget(power_title)
        power_layout.addWidget(self.realtime_power_label)
        
        # Toplam Enerji
        energy_container = QWidget()
        energy_layout = QVBoxLayout(energy_container)
        energy_layout.setSpacing(8)
        
        energy_title = QLabel("📊 Toplam Enerji")
        energy_title.setStyleSheet("""
            font-size: 14px;
            font-weight: 600;
            color: #3b82f6;
        """)
        
        self.realtime_energy_label = QLabel("0.00 Wh")
        self.realtime_energy_label.setStyleSheet("""
            font-size: 24px;
            font-weight: 700;
            color: #ffffff;
            background: rgba(59, 130, 246, 0.1);
            border-radius: 8px;
            padding: 8px 16px;
        """)
        
        energy_layout.addWidget(energy_title)
        energy_layout.addWidget(self.realtime_energy_label)
        
        # Aktif Bobin
        coil_container = QWidget()
        coil_layout = QVBoxLayout(coil_container)
        coil_layout.setSpacing(8)
        
        coil_title = QLabel("🔄 Aktif Bobin")
        coil_title.setStyleSheet("""
            font-size: 14px;
            font-weight: 600;
            color: #10b981;
        """)
        
        self.realtime_coil_label = QLabel("0")
        self.realtime_coil_label.setStyleSheet("""
            font-size: 24px;
            font-weight: 700;
            color: #ffffff;
            background: rgba(16, 185, 129, 0.1);
            border-radius: 8px;
            padding: 8px 16px;
        """)
        
        coil_layout.addWidget(coil_title)
        coil_layout.addWidget(self.realtime_coil_label)
        
        # Ortalama Akım
        current_container = QWidget()
        current_layout = QVBoxLayout(current_container)
        current_layout.setSpacing(8)
        
        current_title = QLabel("⚙️ Ort. Akım")
        current_title.setStyleSheet("""
            font-size: 14px;
            font-weight: 600;
            color: #8b5cf6;
        """)
        
        self.realtime_current_label = QLabel("0.00 A")
        self.realtime_current_label.setStyleSheet("""
            font-size: 24px;
            font-weight: 700;
            color: #ffffff;
            background: rgba(139, 92, 246, 0.1);
            border-radius: 8px;
            padding: 8px 16px;
        """)
        
        current_layout.addWidget(current_title)
        current_layout.addWidget(self.realtime_current_label)
        
        # Layout'a ekle
        layout.addWidget(power_container, 1)
        layout.addWidget(energy_container, 1)
        layout.addWidget(coil_container, 1)
        layout.addWidget(current_container, 1)
        
        return panel
    
    def _load_historical_data(self):
        """Veritabanından geçmiş tedavi verilerini yükle"""
        try:
            if not self.main_window:
                self.logger.warning("Ana pencere bulunamadı, geçmiş veri yüklenemedi")
                return
            
            # Tedavi veritabanına eriş
            if hasattr(self.main_window, 'treatment_db'):
                treatment_db = self.main_window.treatment_db
                
                # Son 30 günlük tedavi kayıtlarını al
                thirty_days_ago = datetime.now() - timedelta(days=30)
                
                try:
                    # Veritabanından tedavi kayıtlarını çek
                    # Not: Bu metodlar treatment_history_db.py'de tanımlı olmalı
                    if hasattr(treatment_db, 'get_sessions_by_date_range'):
                        sessions = treatment_db.get_sessions_by_date_range(
                            thirty_days_ago.strftime('%Y-%m-%d'),
                            datetime.now().strftime('%Y-%m-%d')
                        )
                        
                        if sessions:
                            self.logger.info(f"{len(sessions)} adet geçmiş tedavi kaydı yüklendi")
                            
                            # Kayıtları işle
                            for session in sessions:
                                duration = session.get('duration_minutes', 0)
                                if duration > 0:
                                    self.treatment_count += 1
                                    self.total_treatment_duration_min += duration
                                    
                                    # Başarılı tedavi sayısını güncelle (5-60 dakika arası)
                                    if 5 <= duration <= 60:
                                        self.treatment_success_count += 1
                    
                    self.logger.info(
                        f"Geçmiş veri özeti: "
                        f"{self.treatment_count} tedavi, "
                        f"toplam {self.total_treatment_duration_min:.1f} dk"
                    )
                    
                except Exception as e:
                    self.logger.warning(f"Veritabanı sorgusu hatası: {e}")
            else:
                self.logger.debug("Treatment DB bulunamadı, sadece gerçek zamanlı veri kullanılacak")
                
        except Exception as e:
            self.logger.error(f"Geçmiş veri yükleme hatası: {e}", exc_info=True)
    def _setup_responsive_window(self):
        """Setup responsive window sizing and positioning"""
        try:
            width, height, scale_factor, screen_type = get_screen_info()
            
            # Base dimensions for different screen types
            base_configs = {
                "mobile": {"width": 800, "height": 600, "min_width": 600, "min_height": 500},
                "tablet": {"width": 900, "height": 700, "min_width": 800, "min_height": 600},
                "laptop": {"width": 1000, "height": 800, "min_width": 900, "min_height": 700},
                "desktop": {"width": 1200, "height": 900, "min_width": 1000, "min_height": 800},
                "ultrawide": {"width": 1400, "height": 1000, "min_width": 1200, "min_height": 900}
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
            # Fallback to default sizing
            self.logger.warning(f"Responsive window setup failed: {e}, using default size")
            self.setMinimumSize(900, 700)
    
    # Handle window resizing for responsive design
    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Update layout on resize
        self.centralWidget().adjustSize()
    
    def paintEvent(self, event):
        # Only draw the background for the main content area
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Draw window background with slight transparency
        painter.fillRect(self.rect(), QColor(30, 27, 75, 245))  # Slightly transparent background
                
    def closeEvent(self, event):
        """Pencere kapatılırken çağrılır - Kaynakları temizle"""
        self.logger.info("KPIDashboardWindow kapatılıyor")
        
        # Timer'ı durdur
        if hasattr(self, 'update_timer'):
            self.update_timer.stop()
        
        # Ana pencereyi aktif et
        try:
            if hasattr(self, 'main_window') and self.main_window:
                self.main_window.activateWindow()
                self.main_window.raise_()
        except Exception as e:
            self.logger.warning(f"Ana pencereyi aktif etme hatası: {e}")
        
        event.accept()
    
    def update_sensor_data(self, coil_id_str: str, sensor_data: dict):
        """
        Ana pencereden gelen sensor verilerini işle
        
        Args:
            coil_id_str: Bobin ID'si (string olarak, örn: "1")
            sensor_data: Sensor verisi dict'i (current, temperature, etc.)
        """
        try:
            coil_id = int(coil_id_str)
            current_time = time.time()
            
            # Akım verisini al
            current_A = sensor_data.get('current', 0.0)
            if current_A is None:
                current_A = 0.0
            
            # PWM aktif mi kontrol et
            pwm_active = sensor_data.get('pwm_active', False)
            
            # Voltaj hesapla: V = I * R (Ohm Kanunu)
            voltage_V = current_A * self.COIL_RESISTANCE
            
            # Güç hesapla: P = V * I = I² * R
            power_W = current_A * voltage_V
            
            # Veri kaydet
            self.current_readings[coil_id].append((current_time, current_A))
            self.power_readings[coil_id].append((current_time, power_W))
            
            # PWM aktifse bobini aktif listesine ekle
            if pwm_active and current_A > 0.1:  # 0.1A eşik değeri
                if coil_id not in self.active_coils:
                    self.active_coils.add(coil_id)
                    self.treatment_start_times[coil_id] = current_time
                    self.logger.info(f"Bobin {coil_id} tedavi başladı")
            elif not pwm_active and coil_id in self.active_coils:
                # Bobin durdu
                self.active_coils.remove(coil_id)
                if coil_id in self.treatment_start_times:
                    duration_sec = current_time - self.treatment_start_times[coil_id]
                    self.total_treatment_duration_min += duration_sec / 60.0
                    self.treatment_count += 1
                    
                    # Tedavi başarı oranı hesapla (basit metrik: süre hedefine yakınlık)
                    # Normal tedavi 10-30 dakika arası kabul edelim
                    duration_min = duration_sec / 60.0
                    if 5 <= duration_min <= 60:  # Makul süre aralığı
                        self.treatment_success_count += 1
                    
                    # Tamamlanan tedaviyi kaydet
                    self.completed_treatments.append({
                        'timestamp': current_time,
                        'duration': duration_min,
                        'coil_id': coil_id
                    })
                    
                    del self.treatment_start_times[coil_id]
                    self.logger.info(f"Bobin {coil_id} tedavi bitti (süre: {duration_min:.1f} dk)")
            
            # Alarm ve uyarı kontrolü
            temp = sensor_data.get('object_temp', 0.0)
            if temp and temp > 60:  # 60°C üzeri yüksek sıcaklık
                self.high_temp_events += 1
            
            if current_A > 5.0:  # 5A üzeri yüksek akım
                self.high_current_events += 1
            
        except Exception as e:
            self.logger.error(f"Sensor data işleme hatası: {e}", exc_info=True)
    
    def _update_realtime_kpis(self):
        """Gerçek zamanlı KPI değerlerini güncelle (her saniye)"""
        try:
            current_time = time.time()
            
            # Enerji tüketimi hesapla (son saniyedeki)
            total_power_W = 0.0
            total_current_A = 0.0
            active_coil_count = 0
            
            for coil_id in range(1, 9):
                if self.power_readings[coil_id]:
                    # Son güç okumasını al
                    _, last_power = self.power_readings[coil_id][-1]
                    total_power_W += last_power
                
                if self.current_readings[coil_id]:
                    # Son akım okumasını al
                    _, last_current = self.current_readings[coil_id][-1]
                    if last_current > 0.1:  # 0.1A eşik değeri
                        total_current_A += last_current
                        active_coil_count += 1
            
            # Enerji birikimi (Wh = W * h, 1 saniye = 1/3600 saat)
            energy_increment_wh = total_power_W / 3600.0
            self.total_energy_wh += energy_increment_wh
            
            # Gerçek zamanlı göstergeleri güncelle
            if hasattr(self, 'realtime_power_label'):
                self.realtime_power_label.setText(f"{total_power_W:.2f} W")
            
            if hasattr(self, 'realtime_energy_label'):
                # Wh veya kWh olarak göster
                if self.total_energy_wh < 1000:
                    self.realtime_energy_label.setText(f"{self.total_energy_wh:.2f} Wh")
                else:
                    self.realtime_energy_label.setText(f"{self.total_energy_wh/1000:.3f} kWh")
            
            if hasattr(self, 'realtime_coil_label'):
                self.realtime_coil_label.setText(f"{active_coil_count}")
            
            if hasattr(self, 'realtime_current_label'):
                avg_current = total_current_A / active_coil_count if active_coil_count > 0 else 0.0
                self.realtime_current_label.setText(f"{avg_current:.2f} A")
            
            # Ana penceredeki KPI'yı güncelle (Wh cinsinden)
            if self.main_window and hasattr(self.main_window, 'update_kpi_energy'):
                try:
                    self.main_window.update_kpi_energy(self.total_energy_wh)
                except Exception as e:
                    if self.logger.isEnabledFor(logging.DEBUG):
                        self.logger.debug(f"Ana pencere KPI güncelleme hatası: {e}")
            
            # Ortalama tedavi süresi hesapla
            avg_treatment_duration = 0.0
            if self.treatment_count > 0:
                avg_treatment_duration = self.total_treatment_duration_min / self.treatment_count
            
            # Aktif tedavilerin süresini ekle
            active_duration_min = 0.0
            for coil_id, start_time in self.treatment_start_times.items():
                active_duration_min += (current_time - start_time) / 60.0
            
            if self.treatment_count + len(self.active_coils) > 0:
                avg_treatment_duration = (self.total_treatment_duration_min + active_duration_min) / (self.treatment_count + len(self.active_coils))
            
            # Seans başına enerji tüketimi
            total_sessions = self.treatment_count + len(self.active_coils)
            energy_per_session = 0.0
            if total_sessions > 0:
                energy_per_session = self.total_energy_wh / 1000.0 / total_sessions  # kWh'ye çevir
            
            # Alarm sayısını hesapla (tüm hesaplamalarda kullanılacak)
            total_events = self.high_temp_events + self.high_current_events
            
            # Çalışma oranını hesapla (bakım hesaplamasında kullanılacak)
            operation_rate = 0.0
            if self.session_start_time:
                total_session_time = (current_time - self.session_start_time) / 60.0
                if total_session_time > 0:
                    active_time = self.total_treatment_duration_min + active_duration_min
                    operation_rate = (active_time / total_session_time) * 100.0
            
            # UI widget'larını güncelle
            if hasattr(self, 'input_widgets') and len(self.input_widgets) >= 5:
                # 0. Tedavi Etkinliği (Treatment Effectiveness) - Başarı oranı
                if self.treatment_count > 0:
                    effectiveness = (self.treatment_success_count / self.treatment_count) * 100.0
                    self.input_widgets[0].setValue(effectiveness)
                
                # 1. Ortalama Tedavi Süresi (Average Treatment Duration)
                self.input_widgets[1].setValue(avg_treatment_duration)
                
                # 2. Cihaz Çalışma Oranı (Device Operation Rate) - Enerji Tüketimi kaldırıldı
                self.input_widgets[2].setValue(min(operation_rate, 100.0))
                
                # 3. Hasta Memnuniyeti (Patient Satisfaction)
                # Otomatik hesaplama: Tedavi süresi hedefine yakınlık + alarm yokluğu
                if self.treatment_count > 0:
                    # Temel skor: 7.0
                    base_score = 7.0
                    
                    # Süre optimizasyonu bonusu (+1.5 puan max)
                    # 15-20 dakika arası ideal kabul edelim
                    if avg_treatment_duration > 0:
                        if 15 <= avg_treatment_duration <= 20:
                            duration_bonus = 1.5
                        elif 10 <= avg_treatment_duration < 15:
                            duration_bonus = 1.0
                        elif 20 < avg_treatment_duration <= 30:
                            duration_bonus = 1.0
                        else:
                            duration_bonus = 0.5
                    else:
                        duration_bonus = 0.0
                    
                    # Güvenlik bonusu (+1.5 puan max)
                    if total_events == 0:
                        safety_bonus = 1.5
                    elif total_events <= 2:
                        safety_bonus = 1.0
                    elif total_events <= 5:
                        safety_bonus = 0.5
                    else:
                        safety_bonus = 0.0
                    
                    satisfaction = min(10.0, base_score + duration_bonus + safety_bonus)
                    self.input_widgets[3].setValue(satisfaction)
                
                # 4. Bakım Süresi (Maintenance Time)
                # Alarm sayısına göre tahmini bakım süresi
                maintenance_per_day = 5.0  # Temel bakım: 5 dk/gün
                
                # Her 10 alarm için +5 dakika
                alarm_based_maintenance = (total_events // 10) * 5.0
                
                # Yüksek kullanım için +10 dakika
                if operation_rate > 80:
                    usage_maintenance = 10.0
                elif operation_rate > 60:
                    usage_maintenance = 5.0
                else:
                    usage_maintenance = 0.0
                
                total_maintenance = maintenance_per_day + alarm_based_maintenance + usage_maintenance
                self.input_widgets[4].setValue(int(total_maintenance))
            
            # Cihaz çalışma oranı hesapla
            if self.session_start_time is None and len(self.active_coils) > 0:
                self.session_start_time = current_time
            
            # Anlık güç ve akım bilgisi (info için her 10 saniyede)
            if self.logger.isEnabledFor(logging.INFO):
                # Throttle logging to every 10 seconds
                if not hasattr(self, '_last_info_log_time'):
                    self._last_info_log_time = 0
                
                if current_time - self._last_info_log_time > 10:
                    self._last_info_log_time = current_time
                    
                    # Temel istatistikler
                    effectiveness = (self.treatment_success_count / self.treatment_count * 100.0) if self.treatment_count > 0 else 0.0
                    
                    self.logger.info(
                        f"KPI Özet - "
                        f"Güç: {total_power_W:.1f}W, "
                        f"Enerji: {self.total_energy_wh:.2f}Wh, "
                        f"Aktif: {active_coil_count}, "
                        f"Tedavi: {self.treatment_count}, "
                        f"Etkinlik: {effectiveness:.1f}%, "
                        f"Ort.Süre: {avg_treatment_duration:.1f}dk"
                    )
                
        except Exception as e:
            self.logger.error(f"Gerçek zamanlı KPI güncelleme hatası: {e}", exc_info=True)
                
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = KPIDashboardWindow()
    window.show()
    sys.exit(app.exec())

