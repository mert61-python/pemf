"""
Seans Geçmişi Görüntüleme Penceresi
PEMF seanslarının görüntülenmesi ve yönetimi
"""

import sys
import os
import logging
import platform
import subprocess
from datetime import datetime

# Add parent directory to path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, 
                            QTableWidgetItem, QPushButton, QLabel, QDateEdit,
                            QComboBox, QLineEdit, QTextEdit, QDialog, QDialogButtonBox,
                            QGroupBox, QGridLayout, QHeaderView, QMessageBox,
                            QSplitter, QScrollArea, QTabWidget, QApplication)
from PyQt6.QtCore import Qt, QDate, QRunnable, QThreadPool, pyqtSignal, QObject
from database.treatment_history_db import get_treatment_db
from windows.email_pdf_dialog import EmailPDFDialog
from utils.value_utils import get_safe_value
from styles import StyleMixin
# Responsive Utils
from utils.responsive_utils import get_screen_info

# PDF raporu için gerekli import
try:
    from utils.pdf_report_generator import get_pdf_generator
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False


class HistoryLoaderSignals(QObject):
    """Signals for HistoryLoaderRunnable"""
    finished = pyqtSignal(list)  # Emitted with sessions list
    error = pyqtSignal(str)  # Emitted with error message


class HistoryLoaderRunnable(QRunnable):
    """
    QRunnable for loading treatment history from database in background thread.
    Prevents UI blocking during database queries.
    """
    
    def __init__(self, app_data_dir, start_date, end_date, treatment_mode, logger):
        super().__init__()
        self.app_data_dir = app_data_dir
        self.start_date = start_date
        self.end_date = end_date
        self.treatment_mode = treatment_mode
        self.logger = logger
        self.signals = HistoryLoaderSignals()
    
    def run(self):
        """Execute database query in background thread"""
        try:
            db = get_treatment_db(self.app_data_dir)
            sessions = db.get_session_history(
                limit=1000,
                start_date=self.start_date,
                end_date=self.end_date,
                treatment_mode=self.treatment_mode
            )
            self.signals.finished.emit(sessions)
        except Exception as e:
            self.logger.error(f"HistoryLoaderRunnable error: {e}", exc_info=True)
            self.signals.error.emit(str(e))


class PDFGeneratorSignals(QObject):
    """Signals for PDFGeneratorRunnable"""
    finished = pyqtSignal(str, int)  # Emitted with (pdf_path, session_count)
    error = pyqtSignal(str)  # Emitted with error message


class SessionDetailLoaderSignals(QObject):
    """Signals for SessionDetailLoaderRunnable"""
    finished = pyqtSignal(dict)  # Emitted with session details dict
    error = pyqtSignal(str)  # Emitted with error message


class SessionDetailLoaderRunnable(QRunnable):
    """
    QRunnable for loading session details from database in background thread.
    Prevents UI blocking during database queries.
    """
    
    def __init__(self, app_data_dir, session_id, logger):
        super().__init__()
        self.app_data_dir = app_data_dir
        self.session_id = session_id
        self.logger = logger
        self.signals = SessionDetailLoaderSignals()
    
    def run(self):
        """Execute database query in background thread"""
        try:
            db = get_treatment_db(self.app_data_dir)
            session = db.get_session_details(self.session_id)
            if session:
                self.signals.finished.emit(session)
            else:
                self.signals.error.emit(f"Seans bulunamadı: {self.session_id}")
        except Exception as e:
            self.logger.error(f"SessionDetailLoaderRunnable error: {e}", exc_info=True)
            self.signals.error.emit(str(e))


class PDFGeneratorRunnable(QRunnable):
    """
    QRunnable for generating PDF reports in background thread.
    Prevents UI blocking during PDF generation.
    """
    
    def __init__(self, app_data_dir, session_ids, output_path, include_patient_info, 
                 include_statistics, logger):
        super().__init__()
        self.app_data_dir = app_data_dir
        self.session_ids = session_ids
        self.output_path = output_path
        self.include_patient_info = include_patient_info
        self.include_statistics = include_statistics
        self.logger = logger
        self.signals = PDFGeneratorSignals()
    
    def run(self):
        """Execute PDF generation in background thread"""
        try:
            generator = get_pdf_generator(self.app_data_dir)
            pdf_file = generator.generate_session_report(
                session_ids=self.session_ids,
                output_path=self.output_path,
                include_patient_info=self.include_patient_info,
                include_statistics=self.include_statistics
            )
            self.signals.finished.emit(pdf_file, len(self.session_ids))
        except Exception as e:
            self.logger.error(f"PDFGeneratorRunnable error: {e}", exc_info=True)
            self.signals.error.emit(str(e))


class TreatmentHistoryWindow(QWidget, StyleMixin):
    """Seans geçmişi ana penceresi - Design System entegrasyonu"""
    
    # Signals for thread-safe communication
    history_loaded = pyqtSignal(list)  # Emitted when history data is loaded
    history_load_error = pyqtSignal(str)  # Emitted on load error
    session_detail_loaded = pyqtSignal(dict)  # Emitted when session detail is loaded
    session_detail_load_error = pyqtSignal(str)  # Emitted on session detail load error
    pdf_generated = pyqtSignal(str, int)  # Emitted when PDF is generated (path, session_count)
    pdf_generation_error = pyqtSignal(str)  # Emitted on PDF generation error
    email_pdf_generated = pyqtSignal(str, int)  # Emitted when PDF is generated for email (path, session_count)
    
    def __init__(self, parent=None, main_window=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.main_window = main_window
        
        # Get app_data_dir from main_window or create it
        if main_window and hasattr(main_window, 'app_data_dir'):
            self.app_data_dir = main_window.app_data_dir
        else:
            from windows.gui_pyqt_v11 import get_app_data_directory
            self.app_data_dir = get_app_data_directory()
        
        self.db = get_treatment_db(self.app_data_dir)
        self.logger = logging.getLogger(__name__)
        self.last_generated_pdf = None  # Son oluşturulan PDF dosyasını takip et
        self._pending_session_id = None
        
        self.setWindowTitle("PEMF Seans Geçmişi")
        
        # Apply design system theme
        self.apply_theme()
        
        # Responsive window sizing (after theme is applied)
        self._setup_responsive_window()
        
        # Ana layout
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(20, 20, 20, 20)
        self.main_layout.setSpacing(15)
        
        self.setup_ui()
        self.apply_styles()
        
        # Initialize thread pool for background operations
        self.thread_pool = QThreadPool.globalInstance()
        
        # Connect signals to handlers
        self.history_loaded.connect(self._on_history_loaded)
        self.history_load_error.connect(self._on_history_load_error)
        self.session_detail_loaded.connect(self._on_session_detail_loaded)
        self.session_detail_load_error.connect(self._on_session_detail_load_error)
        self.pdf_generated.connect(self._on_pdf_generated)
        self.pdf_generation_error.connect(self._on_pdf_generation_error)
        self.email_pdf_generated.connect(self._on_email_pdf_generated)
        
        self.load_history()
    
    def setup_ui(self):
        """UI bileşenlerini oluştur"""
        
        # Başlık
        title_label = QLabel("📋 Seans Geçmişi")
        title_label.setObjectName("titleLabel")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.main_layout.addWidget(title_label)
        
        # Filtre bölümü
        self.create_filter_section()
        
        # Ana içerik bölümü
        self.create_main_content()
        
        # Alt butonlar
        self.create_bottom_buttons()
    
    def create_filter_section(self):
        """Filtre bölümünü oluştur"""
        filter_group = QGroupBox("Filtreler")
        filter_layout = QGridLayout(filter_group)
        
        # Tarih filtreleri
        filter_layout.addWidget(QLabel("Başlangıç Tarihi:"), 0, 0)
        self.start_date_edit = QDateEdit()
        self.start_date_edit.setDate(QDate.currentDate().addDays(-30))
        self.start_date_edit.setCalendarPopup(True)
        filter_layout.addWidget(self.start_date_edit, 0, 1)
        
        filter_layout.addWidget(QLabel("Bitiş Tarihi:"), 0, 2)
        self.end_date_edit = QDateEdit()
        self.end_date_edit.setDate(QDate.currentDate())
        self.end_date_edit.setCalendarPopup(True)
        filter_layout.addWidget(self.end_date_edit, 0, 3)
        
        # Seans modu filtresi
        filter_layout.addWidget(QLabel("Seans Modu:"), 1, 0)
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Tümü", "Autonomous", "Manual", "Custom"])
        filter_layout.addWidget(self.mode_combo, 1, 1)
        
        # Arama kutusu
        filter_layout.addWidget(QLabel("Arama:"), 1, 2)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Hasta notu veya uygulayıcı ara...")
        filter_layout.addWidget(self.search_edit, 1, 3)
        
        # Filtre butonları
        filter_btn_layout = QHBoxLayout()
        
        self.filter_btn = QPushButton("Filtrele")
        self.filter_btn.clicked.connect(self.apply_filters)
        filter_btn_layout.addWidget(self.filter_btn)
        
        self.clear_filter_btn = QPushButton("Temizle")
        self.clear_filter_btn.clicked.connect(self.clear_filters)
        filter_btn_layout.addWidget(self.clear_filter_btn)
        
        filter_btn_layout.addStretch()
        
        filter_layout.addLayout(filter_btn_layout, 2, 0, 1, 4)
        
        self.main_layout.addWidget(filter_group)
    
    def create_main_content(self):
        """Ana içerik bölümünü oluştur"""
        
        # Splitter ile tablo ve detay bölümünü ayır
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Sol taraf - Tablo
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        
        # İstatistikler
        self.create_statistics_section(left_layout)
        
        # Seans tablosu
        self.create_treatment_table(left_layout)
        
        splitter.addWidget(left_widget)
        
        # Sağ taraf - Detaylar
        self.create_details_section(splitter)
        
        # Splitter oranları
        splitter.setSizes([800, 400])
        
        self.main_layout.addWidget(splitter)
    
    def create_statistics_section(self, parent_layout):
        """İstatistik bölümünü oluştur"""
        stats_group = QGroupBox("İstatistikler")
        stats_layout = QHBoxLayout(stats_group)
        
        self.total_sessions_label = QLabel("Toplam Seans: 0")
        self.monthly_sessions_label = QLabel("Bu Ay: 0")
        self.avg_duration_label = QLabel("Ort. Süre: 0 dk")
        
        stats_layout.addWidget(self.total_sessions_label)
        stats_layout.addWidget(self.monthly_sessions_label)
        stats_layout.addWidget(self.avg_duration_label)
        stats_layout.addStretch()
        
        parent_layout.addWidget(stats_group)
    
    def create_treatment_table(self, parent_layout):
        """Seans tablosunu oluştur"""
        # Tablo başlığı ve kontrol butonları
        table_header_layout = QHBoxLayout()
        
        table_label = QLabel("Seanslar")
        table_label.setObjectName("sectionLabel")
        table_header_layout.addWidget(table_label)
        
        table_header_layout.addStretch()
        
        # Toplu seçim butonları
        self.select_all_btn = QPushButton("Tümünü Seç")
        self.select_all_btn.clicked.connect(self.select_all_sessions)
        self.select_all_btn.setMaximumWidth(120)
        table_header_layout.addWidget(self.select_all_btn)
        
        self.deselect_all_btn = QPushButton("Seçimi Kaldır")
        self.deselect_all_btn.clicked.connect(self.deselect_all_sessions)
        self.deselect_all_btn.setMaximumWidth(120)
        table_header_layout.addWidget(self.deselect_all_btn)
        
        self.delete_selected_btn = QPushButton("Seçilenleri Sil")
        self.delete_selected_btn.clicked.connect(self.delete_selected_sessions)
        self.delete_selected_btn.setMaximumWidth(120)
        self.delete_selected_btn.setEnabled(False)
        table_header_layout.addWidget(self.delete_selected_btn)
        
        parent_layout.addLayout(table_header_layout)
        
        self.treatment_table = QTableWidget()
        self.treatment_table.setColumnCount(12)  # Frekans sütunu kaldırıldı
        self.treatment_table.setHorizontalHeaderLabels([
            "Seç", "Tarih", "Başlangıç", "Süre (dk)", "Hasta Adı", "Tür/Irk", "Yaş", 
            "Ağırlık", "Sahip", "Mod", "Hedef", "Veteriner"
        ])
        
        # Tablo ayarları
        header = self.treatment_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.treatment_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.treatment_table.setAlternatingRowColors(True)
        
        # Tablo seçim olayı
        self.treatment_table.itemSelectionChanged.connect(self.on_session_selected)
        
        parent_layout.addWidget(self.treatment_table)
    
    def create_details_section(self, splitter):
        """Detay bölümünü oluştur"""
        details_widget = QWidget()
        details_layout = QVBoxLayout(details_widget)
        
        details_label = QLabel("Seans Detayları")
        details_label.setObjectName("sectionLabel")
        details_layout.addWidget(details_label)
        
        # Tab widget ile detayları organize et
        self.details_tabs = QTabWidget()
        
        # Genel bilgiler tab
        self.create_general_info_tab()
        
        # Parametreler tab
        self.create_parameters_tab()
        
        # Notlar tab
        self.create_notes_tab()
        
        details_layout.addWidget(self.details_tabs)
        
        # Detay butonları
        detail_btn_layout = QHBoxLayout()
        
        self.view_details_btn = QPushButton("Detaylı Görünüm")
        self.view_details_btn.clicked.connect(self.show_detailed_view)
        self.view_details_btn.setEnabled(False)
        detail_btn_layout.addWidget(self.view_details_btn)
        
        self.delete_session_btn = QPushButton("Seansı Sil")
        self.delete_session_btn.clicked.connect(self.delete_selected_session)
        self.delete_session_btn.setEnabled(False)
        detail_btn_layout.addWidget(self.delete_session_btn)
        
        detail_btn_layout.addStretch()
        
        details_layout.addLayout(detail_btn_layout)
        
        splitter.addWidget(details_widget)
    
    def create_general_info_tab(self):
        """Genel bilgiler tab'ını oluştur"""
        general_tab = QWidget()
        layout = QGridLayout(general_tab)
        
        # Seans bilgileri
        self.session_id_label = QLabel("-")
        self.session_date_label = QLabel("-")
        self.session_duration_label = QLabel("-")
        self.session_mode_label = QLabel("-")
        self.session_target_label = QLabel("-")
        self.session_operator_label = QLabel("-")
        self.session_status_label = QLabel("-")
        
        # Hasta bilgileri
        self.patient_name_label = QLabel("-")
        self.patient_age_label = QLabel("-")
        self.patient_species_label = QLabel("-")
        self.patient_breed_label = QLabel("-")
        self.patient_weight_label = QLabel("-")
        self.patient_owner_label = QLabel("-")
        self.patient_vet_label = QLabel("-")
        
        # Seans bilgileri bölümü
        layout.addWidget(QLabel("SEANS BİLGİLERİ"), 0, 0, 1, 2)
        layout.addWidget(QLabel("Seans ID:"), 1, 0)
        layout.addWidget(self.session_id_label, 1, 1)
        
        layout.addWidget(QLabel("Tarih:"), 2, 0)
        layout.addWidget(self.session_date_label, 2, 1)
        
        layout.addWidget(QLabel("Süre:"), 3, 0)
        layout.addWidget(self.session_duration_label, 3, 1)
        
        layout.addWidget(QLabel("Mod:"), 4, 0)
        layout.addWidget(self.session_mode_label, 4, 1)
        
        layout.addWidget(QLabel("Hedef:"), 5, 0)
        layout.addWidget(self.session_target_label, 5, 1)
        
        layout.addWidget(QLabel("Durum:"), 6, 0)
        layout.addWidget(self.session_status_label, 6, 1)
        
        # Hasta bilgileri bölümü
        layout.addWidget(QLabel("HASTA BİLGİLERİ"), 7, 0, 1, 2)
        layout.addWidget(QLabel("Hasta Adı:"), 8, 0)
        layout.addWidget(self.patient_name_label, 8, 1)
        
        layout.addWidget(QLabel("Yaş:"), 9, 0)
        layout.addWidget(self.patient_age_label, 9, 1)
        
        layout.addWidget(QLabel("Tür:"), 10, 0)
        layout.addWidget(self.patient_species_label, 10, 1)
        
        layout.addWidget(QLabel("Irk:"), 11, 0)
        layout.addWidget(self.patient_breed_label, 11, 1)
        
        layout.addWidget(QLabel("Ağırlık:"), 12, 0)
        layout.addWidget(self.patient_weight_label, 12, 1)
        
        layout.addWidget(QLabel("Sahip:"), 13, 0)
        layout.addWidget(self.patient_owner_label, 13, 1)
        
        layout.addWidget(QLabel("Veteriner:"), 14, 0)
        layout.addWidget(self.patient_vet_label, 14, 1)
        
        layout.setRowStretch(15, 1)
        
        self.details_tabs.addTab(general_tab, "Genel")
    
    def create_parameters_tab(self):
        """Parametreler tab'ını oluştur"""
        params_tab = QWidget()
        layout = QVBoxLayout(params_tab)
        
        self.params_scroll = QScrollArea()
        self.params_widget = QWidget()
        self.params_layout = QGridLayout(self.params_widget)
        
        self.params_scroll.setWidget(self.params_widget)
        self.params_scroll.setWidgetResizable(True)
        
        layout.addWidget(self.params_scroll)
        
        self.details_tabs.addTab(params_tab, "Parametreler")
    
    def create_notes_tab(self):
        """Notlar tab'ını oluştur"""
        notes_tab = QWidget()
        layout = QVBoxLayout(notes_tab)
        
        self.notes_text = QTextEdit()
        self.notes_text.setReadOnly(True)
        layout.addWidget(self.notes_text)
        
        self.details_tabs.addTab(notes_tab, "Notlar")
    
    def create_bottom_buttons(self):
        """Alt butonları oluştur"""
        button_layout = QHBoxLayout()
        
        # PDF Raporu butonları
        self.pdf_selected_btn = QPushButton("📄 Seçili Seanslar PDF")
        self.pdf_selected_btn.clicked.connect(self.generate_selected_pdf)
        self.pdf_selected_btn.setToolTip("Seçili seanslar için PDF raporu oluştur")
        button_layout.addWidget(self.pdf_selected_btn)
        
        self.pdf_all_btn = QPushButton("📋 Tüm Seanslar PDF")
        self.pdf_all_btn.clicked.connect(self.generate_all_pdf)
        self.pdf_all_btn.setToolTip("Filtrelenmiş tüm seanslar için PDF raporu oluştur")
        button_layout.addWidget(self.pdf_all_btn)
        
        self.email_pdf_btn = QPushButton("📧 E-posta ile Gönder")
        self.email_pdf_btn.clicked.connect(self.send_email_pdf)
        self.email_pdf_btn.setToolTip("Seçili seanslar için PDF oluşturup e-posta ile gönder veya son oluşturulan PDF'i gönder")
        self.email_pdf_btn.setEnabled(False)  # Başlangıçta deaktif
        button_layout.addWidget(self.email_pdf_btn)
        
        self.export_btn = QPushButton("Dışa Aktar")
        self.export_btn.clicked.connect(self.export_history)
        button_layout.addWidget(self.export_btn)
        
        self.refresh_btn = QPushButton("Yenile")
        self.refresh_btn.clicked.connect(self.load_history)
        button_layout.addWidget(self.refresh_btn)
        
        button_layout.addStretch()
        
        self.close_btn = QPushButton("Kapat")
        self.close_btn.clicked.connect(self.close)
        button_layout.addWidget(self.close_btn)
        
        self.main_layout.addLayout(button_layout)
    
    def apply_styles(self):
        """Stil uygula"""
        self.setStyleSheet("""
            QWidget {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, 
                    stop:0 #2d185a, stop:1 #6c2b8f);
                color: #ffffff;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 9pt;
            }
            
            #titleLabel {
                font-size: 19pt;
                font-weight: bold;
                color: white;
                margin: 10px 0;
                padding: 15px;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, 
                    stop:0 rgba(142, 68, 173, 0.8), 
                    stop:1 rgba(155, 89, 182, 0.8));
                border-radius: 12px;
                border: 2px solid rgba(255, 255, 255, 0.2);
            }
            
            #sectionLabel {
                font-size: 12pt;
                font-weight: bold;
                color: #8e44ad;
                margin: 5px 0;
            }
            
            QGroupBox {
                font-weight: bold;
                border: 1px solid #30363d;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 15px;
                background: transparent;
            }
            
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 6px 0 6px;
                color: #8b949e;
                font-weight: bold;
                background: transparent;
                border-radius: 0;
            }
            
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, 
                    stop:0 #8e44ad, stop:1 #9b59b6);
                color: white;
                border: none;
                padding: 12px 24px;
                border-radius: 8px;
                font-weight: bold;
                font-size: 10pt;
                min-height: 20px;
                min-width: 100px;
            }
            
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, 
                    stop:0 #9b59b6, stop:1 #a569bd);
            }
            
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, 
                    stop:0 #7d3c98, stop:1 #8e44ad);
            }
            
            QPushButton:disabled {
                background-color: #555555;
                color: #888888;
            }
            
            QTableWidget {
                gridline-color: rgba(255, 255, 255, 0.2);
                background: rgba(255, 255, 255, 0.1);
                alternate-background-color: rgba(255, 255, 255, 0.05);
                selection-background-color: rgba(142, 68, 173, 0.6);
                border: 2px solid rgba(255, 255, 255, 0.3);
                border-radius: 12px;
            }
            
            QTableWidget::item {
                padding: 12px 8px;
                border-bottom: 1px solid rgba(255, 255, 255, 0.1);
                color: white;
            }
            
            QTableWidget::item:selected {
                background: rgba(142, 68, 173, 0.8);
                color: white;
            }
            
            QTableWidget::item:hover {
                background: rgba(255, 255, 255, 0.1);
            }
            
            QHeaderView::section {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, 
                    stop:0 #8e44ad, stop:1 #9b59b6);
                color: white;
                padding: 12px 8px;
                border: none;
                font-weight: bold;
                font-size: 10pt;
            }
            
            QComboBox, QLineEdit, QDateEdit {
                padding: 10px 12px;
                border: 2px solid rgba(255, 255, 255, 0.3);
                border-radius: 8px;
                background: rgba(255, 255, 255, 0.1);
                color: #ffffff;
                font-size: 10pt;
                min-height: 20px;
            }
            
            QComboBox:focus, QLineEdit:focus, QDateEdit:focus {
                border-color: #8e44ad;
                background: rgba(255, 255, 255, 0.2);
            }
            
            QComboBox::drop-down {
                border: none;
                background: rgba(142, 68, 173, 0.8);
                border-radius: 4px;
                width: 20px;
            }
            
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid white;
                margin: 5px;
            }
            
            QTextEdit {
                background: rgba(255, 255, 255, 0.1);
                border: 2px solid rgba(255, 255, 255, 0.3);
                border-radius: 8px;
                padding: 12px;
                color: #ffffff;
                font-size: 10pt;
            }
            
            QTabWidget::pane {
                border: 2px solid rgba(255, 255, 255, 0.3);
                border-radius: 12px;
                background: rgba(255, 255, 255, 0.1);
            }
            
            QTabBar::tab {
                background: rgba(255, 255, 255, 0.1);
                color: #ffffff;
                padding: 10px 20px;
                margin-right: 2px;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                font-weight: bold;
            }
            
            QTabBar::tab:selected {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, 
                    stop:0 #8e44ad, stop:1 #9b59b6);
                color: white;
            }
            
            QTabBar::tab:hover {
                background: rgba(255, 255, 255, 0.2);
            }
            
            QScrollBar:vertical {
                background: rgba(255, 255, 255, 0.1);
                width: 14px;
                border-radius: 7px;
                margin: 0;
            }
            
            QScrollBar::handle:vertical {
                background: rgba(142, 68, 173, 0.8);
                border-radius: 7px;
                min-height: 30px;
                margin: 2px;
            }
            
            QScrollBar::handle:vertical:hover {
                background: rgba(155, 89, 182, 0.9);
            }
            
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            
            QLabel {
                color: #ffffff;
                font-size: 10pt;
            }
            
            QScrollArea {
                border: none;
                background-color: transparent;
            }
        """)
    def _setup_responsive_window(self):
        """Setup responsive window sizing and positioning"""
        try:
            width, height, scale_factor, screen_type = get_screen_info()
            
            # Base dimensions for different screen types
            base_configs = {
                "mobile": {"width": 800, "height": 600, "min_width": 600, "min_height": 500},
                "tablet": {"width": 1024, "height": 768, "min_width": 800, "min_height": 600},
                "laptop": {"width": 1200, "height": 800, "min_width": 1000, "min_height": 700},
                "desktop": {"width": 1400, "height": 900, "min_width": 1200, "min_height": 800},
                "ultrawide": {"width": 1600, "height": 1000, "min_width": 1400, "min_height": 900}
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
            self.setGeometry(100, 100, 1200, 800)

    def load_history(self):
        """Seans geçmişini yükle (non-blocking - background thread)"""
        # Filtreleri al
        start_date = self.start_date_edit.date().toString("yyyy-MM-dd")
        end_date = self.end_date_edit.date().toString("yyyy-MM-dd")
        treatment_mode = None if self.mode_combo.currentText() == "Tümü" else self.mode_combo.currentText()
        
        # Disable refresh button during loading (optional UI feedback)
        if hasattr(self, 'refresh_btn'):
            self.refresh_btn.setEnabled(False)
            self.refresh_btn.setText("Yükleniyor...")
        
        # Create and start background task
        runnable = HistoryLoaderRunnable(
            app_data_dir=self.app_data_dir,
            start_date=start_date,
            end_date=end_date,
            treatment_mode=treatment_mode,
            logger=self.logger
        )
        
        # Connect runnable signals to window signals (thread-safe)
        runnable.signals.finished.connect(self.history_loaded.emit)
        runnable.signals.error.connect(self.history_load_error.emit)
        
        # Start in thread pool
        self.thread_pool.start(runnable)
    
    def update_table(self, sessions):
        """Tabloyu güncelle"""
        self.treatment_table.blockSignals(True)
        try:
            self.treatment_table.setRowCount(len(sessions))
            
            for row, session in enumerate(sessions):
                # Checkbox - İlk sütun
                checkbox_item = QTableWidgetItem()
                checkbox_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
                checkbox_item.setCheckState(Qt.CheckState.Unchecked)
                checkbox_item.setData(Qt.ItemDataRole.UserRole, session.get('id'))  # Session ID'yi checkbox'ta sakla
                self.treatment_table.setItem(row, 0, checkbox_item)
            
                # Tarih
                self.treatment_table.setItem(row, 1, QTableWidgetItem(session.get('session_date', '')))
            
                # Başlangıç saati
                self.treatment_table.setItem(row, 2, QTableWidgetItem(session.get('start_time', '')))
            
                # Süre - get_session_history'den gelen treatment_duration kullan
                duration = session.get('treatment_duration') or session.get('duration_minutes', 0) or 0
            
                if duration and str(duration).replace('.', '').isdigit():
                    duration_display = f"{float(duration):.0f}" if float(duration) == int(float(duration)) else f"{float(duration):.1f}"
                else:
                    duration_display = "0"
                self.treatment_table.setItem(row, 3, QTableWidgetItem(duration_display))
            
                # Hasta Adı - kaydedilen değerleri olduğu gibi göster
                patient_name = get_safe_value(session.get('patient_name'), '')
                patient_surname = get_safe_value(session.get('patient_surname'), '')
                patient_name = patient_name or 'Bilinmiyor'
            
                if patient_name != 'Bilinmiyor' and patient_surname:
                    full_name = f"{patient_name} {patient_surname}".strip()
                elif patient_name != 'Bilinmiyor':
                    full_name = patient_name
                elif patient_surname:
                    full_name = patient_surname
                else:
                    full_name = "Bilinmiyor"
                
                self.treatment_table.setItem(row, 4, QTableWidgetItem(full_name))
            
                # Tür/Irk - kaydedilen değerleri olduğu gibi göster
                patient_species = str(session.get('patient_species', '')).strip() or 'Bilinmiyor'
                patient_breed = str(session.get('patient_breed', '')).strip() or ''
                
                if patient_species != 'Bilinmiyor' and patient_breed:
                    species_breed = f"{patient_species} - {patient_breed}"
                elif patient_species != 'Bilinmiyor':
                    species_breed = patient_species
                elif patient_breed:
                    species_breed = patient_breed
                else:
                    species_breed = "Bilinmiyor"
                
                self.treatment_table.setItem(row, 5, QTableWidgetItem(species_breed))
            
                # Hasta Yaşı - kaydedilen değerleri olduğu gibi göster
                patient_age = str(session.get('patient_age', '')).strip() or 'Bilinmiyor'
                self.treatment_table.setItem(row, 6, QTableWidgetItem(patient_age))
            
                # Ağırlık - kaydedilen değerleri olduğu gibi göster
                patient_weight = str(session.get('patient_weight', '')).strip() or 'Bilinmiyor'
                self.treatment_table.setItem(row, 7, QTableWidgetItem(patient_weight))
            
                # Sahip - kaydedilen değerleri olduğu gibi göster
                patient_owner = str(session.get('patient_owner', '')).strip() or 'Bilinmiyor'
                self.treatment_table.setItem(row, 8, QTableWidgetItem(patient_owner))
            
                # Mod
                self.treatment_table.setItem(row, 9, QTableWidgetItem(session.get('treatment_mode', '')))
            
                # Hedef
                self.treatment_table.setItem(row, 10, QTableWidgetItem(session.get('target_condition', '') or '-'))
            
                # Veteriner İletişim - get_session_history'den doğrudan al
                # Veteriner - patient_veteriner'i kontrol et, yoksa patient_vet_contact, yoksa operator_name
                vet_name = get_safe_value(session.get('patient_veteriner', ''))
                if vet_name == 'Bilinmiyor' or not vet_name:
                    vet_name = get_safe_value(session.get('patient_vet_contact', ''))
                if vet_name == 'Bilinmiyor' or not vet_name:
                    vet_name = get_safe_value(session.get('operator_name', ''))
                self.treatment_table.setItem(row, 11, QTableWidgetItem(vet_name))
        finally:
            self.treatment_table.blockSignals(False)

    def update_statistics(self, sessions=None):
            """İstatistikleri güncelle (Yüklenen session listesi üzerinden yap, main thread DB sorgusu yapma)"""
            if sessions is not None:
                self.update_statistics_from_sessions(sessions)
            else:
                self.logger.warning("update_statistics called without sessions parameter")

    def update_statistics_from_sessions(self, sessions):
        """Yüklenen session listesi üzerinden hızlı istatistik güncelle (main thread DB sorgusu yapmaz)."""
        try:
            total_sessions = len(sessions or [])
            monthly_sessions = total_sessions

            durations = []
            for session in sessions or []:
                duration = session.get('duration_minutes')
                if isinstance(duration, (int, float)) and duration > 0:
                    durations.append(duration)

            average_duration = (sum(durations) / len(durations)) if durations else 0

            self.total_sessions_label.setText(f"Toplam Seans: {total_sessions}")
            self.monthly_sessions_label.setText(f"Bu Ay: {monthly_sessions}")
            self.avg_duration_label.setText(f"Ort. Süre: {average_duration:.1f} dk")
        except Exception as e:
            self.logger.error(f"Session listesiyle istatistik güncelleme hatası: {e}", exc_info=True)
    
    def _on_history_loaded(self, sessions):
        """Signal handler for history loaded (called from background thread via signal)"""
        # Re-enable refresh button
        if hasattr(self, 'refresh_btn'):
            self.refresh_btn.setEnabled(True)
            self.refresh_btn.setText("Yenile")
        
        # Update UI (this is called on main thread via signal)
        self.update_table(sessions)
        self.update_statistics_from_sessions(sessions)
    
    def _on_history_load_error(self, error_msg):
        """Signal handler for history load error (called from background thread via signal)"""
        # Re-enable refresh button
        if hasattr(self, 'refresh_btn'):
            self.refresh_btn.setEnabled(True)
            self.refresh_btn.setText("Yenile")
        
        # Show error message (this is called on main thread via signal)
        self.logger.error(f"Geçmiş yükleme hatası: {error_msg}", exc_info=True)
        QMessageBox.critical(self, "Hata", f"Seans geçmişi yüklenirken hata oluştu:\n{error_msg}")
    
    def _on_pdf_generated(self, pdf_path, session_count):
        """Signal handler for PDF generation success (called from background thread via signal)"""
        # Re-enable PDF buttons
        if hasattr(self, 'pdf_selected_btn'):
            self.pdf_selected_btn.setEnabled(True)
            self.pdf_selected_btn.setText("📄 Seçili Seanslar PDF")
        if hasattr(self, 'pdf_all_btn'):
            self.pdf_all_btn.setEnabled(True)
            self.pdf_all_btn.setText("📋 Tüm Seanslar PDF")
        
        # Show success message and open file (this is called on main thread via signal)
        QMessageBox.information(
            self,
            "PDF Oluşturuldu",
            f"PDF raporu başarıyla oluşturuldu:\n{pdf_path}\n\n"
            f"Toplam {session_count} seans rapor edildi.",
            QMessageBox.StandardButton.Ok
        )
        
        # Store PDF path and enable email button
        self.last_generated_pdf = pdf_path
        if hasattr(self, 'email_pdf_btn'):
            self.email_pdf_btn.setEnabled(True)
        
        # Open file (platform-specific)
        try:
            if platform.system() == 'Windows':
                os.startfile(pdf_path)
            elif platform.system() == 'Darwin':  # macOS
                # CRITICAL FIX: Use subprocess instead of os.system to prevent command injection
                subprocess.run(['open', str(pdf_path)], check=False, shell=False)
            else:  # Linux
                # CRITICAL FIX: Use subprocess instead of os.system to prevent command injection
                subprocess.run(['xdg-open', str(pdf_path)], check=False, shell=False)
        except Exception as e:
            self.logger.warning(f"PDF dosyası açılırken hata: {e}")
    
    def _on_pdf_generation_error(self, error_msg):
        """Signal handler for PDF generation error (called from background thread via signal)"""
        # Re-enable PDF buttons
        if hasattr(self, 'pdf_selected_btn'):
            self.pdf_selected_btn.setEnabled(True)
            self.pdf_selected_btn.setText("📄 Seçili Seanslar PDF")
        if hasattr(self, 'pdf_all_btn'):
            self.pdf_all_btn.setEnabled(True)
            self.pdf_all_btn.setText("📋 Tüm Seanslar PDF")
        if hasattr(self, 'email_pdf_btn'):
            self.email_pdf_btn.setEnabled(False)  # Disable email button on error
            self.email_pdf_btn.setText("📧 E-posta ile Gönder")
        
        # Clear last generated PDF on error
        self.last_generated_pdf = None
        
        # Show error message (this is called on main thread via signal)
        self.logger.error(f"PDF oluşturma hatası: {error_msg}", exc_info=True)
        QMessageBox.critical(
            self,
            "PDF Oluşturma Hatası",
            f"PDF raporu oluşturulurken bir hata oluştu:\n{error_msg}",
            QMessageBox.StandardButton.Ok
        )
    
    def _on_email_pdf_generated(self, pdf_path, session_count):
        """Signal handler for email PDF generation success (called from background thread via signal)"""
        # Re-enable email button
        if hasattr(self, 'email_pdf_btn'):
            self.email_pdf_btn.setEnabled(True)
            self.email_pdf_btn.setText("📧 E-posta ile Gönder")
        
        # Open email dialog (this is called on main thread via signal)
        self.logger.info(f"Geçici PDF oluşturuldu: {pdf_path} ({session_count} seans)")
        
        dialog = EmailPDFDialog(pdf_path, self)
        
        # Dialog kapatıldığında geçici dosyayı sil
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # E-posta başarıyla gönderildi, geçici dosyayı sil
            try:
                if os.path.exists(pdf_path):
                    os.remove(pdf_path)
                    self.logger.info(f"Geçici PDF dosyası silindi: {pdf_path}")
            except Exception as e:
                self.logger.warning(f"Geçici PDF dosyası silinemedi: {e}")
        else:
            # Kullanıcı iptal etti, geçici dosyayı tut (kullanıcıya sor)
            reply = QMessageBox.question(
                self,
                "Geçici PDF Dosyası",
                f"PDF dosyası geçici dizinde oluşturuldu:\n{pdf_path}\n\n"
                "Dosyayı silmek ister misiniz?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                try:
                    if os.path.exists(pdf_path):
                        os.remove(pdf_path)
                        self.logger.info(f"Geçici PDF dosyası silindi: {pdf_path}")
                except Exception as e:
                    self.logger.warning(f"Geçici PDF dosyası silinemedi: {e}")
    
    def on_session_selected(self):
        """Seans seçildiğinde detayları göster"""
        current_row = self.treatment_table.currentRow()
        if current_row >= 0:
            # Session ID'yi checkbox sütunundan al
            session_id = self.treatment_table.item(current_row, 0).data(Qt.ItemDataRole.UserRole)
            
            if session_id:
                self._pending_session_id = session_id
                self.load_session_details(session_id)
                self.view_details_btn.setEnabled(True)
                self.delete_session_btn.setEnabled(True)
            else:
                self.clear_session_details()
                self.view_details_btn.setEnabled(False)
                self.delete_session_btn.setEnabled(False)
    
    def load_session_details(self, session_id):
        """Seans detaylarını yükle (non-blocking - background thread)"""
        self._pending_session_id = session_id
        # Create and start background task
        runnable = SessionDetailLoaderRunnable(
            app_data_dir=self.app_data_dir,
            session_id=session_id,
            logger=self.logger
        )
        
        # Connect runnable signals to window signals (thread-safe)
        runnable.signals.finished.connect(self.session_detail_loaded.emit)
        runnable.signals.error.connect(self.session_detail_load_error.emit)
        
        # Start in thread pool
        self.thread_pool.start(runnable)
    
    def _on_session_detail_loaded(self, session):
        """Handle session detail loaded (main thread)"""
        try:
            if self._pending_session_id is not None and session.get('id') != self._pending_session_id:
                return

            # session already loaded from background thread
            if session:
                # Seans bilgileri
                self.session_id_label.setText(str(session.get('id', '-')))
                self.session_date_label.setText(f"{session.get('session_date', '-')} {session.get('start_time', '')}")
                
                # Süre - Önce dinamik mod süresini kontrol et
                parameters = session.get('parameters', {})
                duration = parameters.get('duration', {}).get('value') if 'duration' in parameters else session.get('duration_minutes', 0) or 0
                if duration and str(duration).replace('.', '').isdigit():
                    duration_display = f"{float(duration):.0f}" if float(duration) == int(float(duration)) else f"{float(duration):.1f}"
                else:
                    duration_display = "0"
                self.session_duration_label.setText(f"{duration_display} dakika")
                
                self.session_mode_label.setText(session.get('treatment_mode', '-'))
                self.session_target_label.setText(session.get('target_condition', '-') or '-')
                self.session_status_label.setText(session.get('session_status', '-'))
                
                # Hasta bilgileri - kaydedilen değerleri olduğu gibi göster
                def get_safe_param_value(param_dict):
                    """Dictionary parametrelerinden güvenli değer al"""
                    if isinstance(param_dict, dict):
                        value = param_dict.get('value', '')
                        # None, 'None', boş string kontrolü
                        if value is None or str(value).lower() == 'none' or str(value).strip() == '':
                            return 'Belirtilmemiş'
                        return str(value).strip()
                    # None, 'None', boş string kontrolü
                    if param_dict is None or str(param_dict).lower() == 'none' or str(param_dict).strip() == '':
                        return 'Belirtilmemiş'
                    return str(param_dict).strip()
                
                self.patient_name_label.setText(get_safe_param_value(parameters.get('patient_name', {})))
                self.patient_age_label.setText(get_safe_param_value(parameters.get('patient_age', {})))
                self.patient_species_label.setText(get_safe_param_value(parameters.get('patient_species', {})))
                self.patient_breed_label.setText(get_safe_param_value(parameters.get('patient_breed', {})))
                self.patient_weight_label.setText(get_safe_param_value(parameters.get('patient_weight', {})))
                self.patient_owner_label.setText(get_safe_param_value(parameters.get('patient_owner', {})))
                
                # Veteriner bilgisi - önce parametrelerden, sonra operator_name'den al
                vet_info = get_safe_param_value(parameters.get('patient_vet_contact', {}))
                if vet_info == 'Belirtilmemiş':
                    vet_info = session.get('operator_name', 'Belirtilmemiş') or 'Belirtilmemiş'
                self.patient_vet_label.setText(vet_info)
                
                # Parametreler
                self.update_parameters_display(parameters)
                
                # Notlar
                notes = session.get('patient_notes', '')
                if notes and notes.strip():
                    self.notes_text.setText(notes)
                else:
                    self.notes_text.setText('Bu seans için not bulunmuyor.')
                
        except Exception as e:
            self.logger.error(f"Seans detayları görüntüleme hatası: {e}", exc_info=True)
            self.clear_session_details()
    
    def _on_session_detail_load_error(self, error_msg):
        """Handle session detail load error (main thread)"""
        self.logger.error(f"Seans detay yükleme hatası: {error_msg}")
        self.clear_session_details()
        QMessageBox.warning(
            self,
            "Yükleme Hatası",
            f"Seans detayları yüklenirken hata oluştu:\n{error_msg}",
            QMessageBox.StandardButton.Ok
        )
    
    def update_parameters_display(self, parameters):
        """Parametreler görünümünü güncelle"""
        # Önceki parametreleri temizle
        for i in reversed(range(self.params_layout.count())):
            self.params_layout.itemAt(i).widget().setParent(None)
        
        row = 0
        
        # Parametre isimlerinin Türkçe karşılıkları
        param_translations = {
            'frequency_hz': 'Frekans',
            'intensity_mt': 'Yoğunluk',
            'duty_cycle': 'Duty Cycle',
            'pulse_duration_ms': 'Pulse Süresi',
            'duration': 'Süre',
            'planned_duration': 'Planlanan Süre',
            'actual_duration': 'Gerçek Süre',
            'stop_reason': 'Durdurma Nedeni',
            'connected_coils': 'Bağlı Bobinler',
            'patient_name': 'Hasta Adı',
            'patient_age': 'Hasta Yaşı',
            'patient_species': 'Hasta Türü',
            'patient_breed': 'Hasta Irkı',
            'patient_weight': 'Hasta Ağırlığı',
            'patient_owner': 'Hasta Sahibi',
            'patient_veteriner': 'Veteriner',
            'patient_vet_contact': 'Veteriner İletişim',
            'target_condition': 'Hedef Durum',
            'treatment_mode': 'Seans Modu',
            'operator_name': 'Uygulayıcı'
        }
        
        # Ana parametreler önce gösterilsin
        main_params = ['frequency_hz', 'duty_cycle', 'intensity_mt', 'planned_duration', 'actual_duration']
        
        # Ana parametreleri göster
        for param_key in main_params:
            if param_key in parameters:
                param_data = parameters[param_key]
                display_name = param_translations.get(param_key, param_key.replace('_', ' ').title())
                
                if isinstance(param_data, dict):
                    value = param_data.get('value', '')
                    unit = param_data.get('unit', '')
                    
                    # None veya boş değerleri kontrol et
                    if value is None or str(value).strip() == '' or str(value).lower() == 'none':
                        display_value = 'Belirtilmemiş'
                    else:
                        # Unit kontrolü - None, boş string veya 'none' ise unit ekleme
                        if unit is None or str(unit).strip() == '' or str(unit).lower() == 'none':
                            display_value = str(value)
                        else:
                            display_value = f"{value} {unit}".strip()
                else:
                    # None veya boş değerleri kontrol et
                    if param_data is None or str(param_data).strip() == '' or str(param_data).lower() == 'none':
                        display_value = 'Belirtilmemiş'
                    else:
                        display_value = str(param_data)
                
                self.params_layout.addWidget(QLabel(f"{display_name}:"), row, 0)
                self.params_layout.addWidget(QLabel(display_value), row, 1)
                row += 1
        
        # Diğer parametreler (hasta bilgileri hariç)
        patient_params = ['patient_name', 'patient_age', 'patient_species', 'patient_breed', 
                         'patient_weight', 'patient_owner', 'patient_veteriner', 'patient_vet_contact']
        
        for param_name, param_data in parameters.items():
            if param_name not in main_params and param_name not in patient_params:
                display_name = param_translations.get(param_name, param_name.replace('_', ' ').title())
                
                if isinstance(param_data, dict):
                    value = param_data.get('value', '')
                    unit = param_data.get('unit', '')
                    
                    # None veya boş değerleri kontrol et
                    if value is None or str(value).strip() == '' or str(value).lower() == 'none':
                        display_value = 'Belirtilmemiş'
                    else:
                        # Unit kontrolü - None, boş string veya 'none' ise unit ekleme
                        if unit is None or str(unit).strip() == '' or str(unit).lower() == 'none':
                            display_value = str(value)
                        else:
                            display_value = f"{value} {unit}".strip()
                else:
                    # None veya boş değerleri kontrol et
                    if param_data is None or str(param_data).strip() == '' or str(param_data).lower() == 'none':
                        display_value = 'Belirtilmemiş'
                    else:
                        display_value = str(param_data)
                
                self.params_layout.addWidget(QLabel(f"{display_name}:"), row, 0)
                self.params_layout.addWidget(QLabel(display_value), row, 1)
                row += 1
        
        if row == 0:
            self.params_layout.addWidget(QLabel("Parametre bulunmuyor."), 0, 0, 1, 2)
    
    def clear_session_details(self):
        """Seans detaylarını temizle"""
        self.session_id_label.setText("-")
        self.session_date_label.setText("-")
        self.session_duration_label.setText("-")
        self.session_mode_label.setText("-")
        self.session_target_label.setText("-")
        self.session_operator_label.setText("-")
        self.session_status_label.setText("-")
        
        # Parametreleri temizle
        for i in reversed(range(self.params_layout.count())):
            self.params_layout.itemAt(i).widget().setParent(None)
        
        self.notes_text.setText("")
    
    def apply_filters(self):
        """Filtreleri uygula"""
        self.load_history()
    
    def clear_filters(self):
        """Filtreleri temizle"""
        self.start_date_edit.setDate(QDate.currentDate().addDays(-30))
        self.end_date_edit.setDate(QDate.currentDate())
        self.mode_combo.setCurrentIndex(0)
        self.search_edit.clear()
        self.load_history()
    
    def show_detailed_view(self):
        """Detaylı görünüm penceresini aç"""
        current_row = self.treatment_table.currentRow()
        if current_row >= 0:
            session_id = self.treatment_table.item(current_row, 0).data(Qt.ItemDataRole.UserRole)
            if session_id:
                dialog = SessionDetailDialog(session_id, self.db, self)
                dialog.exec()
    
    def delete_selected_session(self):
        """Seçili seansı sil"""
        current_row = self.treatment_table.currentRow()
        if current_row >= 0:
            session_id = self.treatment_table.item(current_row, 0).data(Qt.ItemDataRole.UserRole)
            if session_id:
                reply = QMessageBox.question(
                    self, "Seansı Sil", 
                    "Bu seansı silmek istediğinizden emin misiniz?\n\nBu işlem geri alınamaz.",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No
                )
                
                if reply == QMessageBox.StandardButton.Yes:
                    try:
                        self.db.delete_session(session_id)
                        self.load_history()
                        self.clear_session_details()
                        QMessageBox.information(self, "Başarılı", "Seans başarıyla silindi.")
                    except Exception as e:
                        self.logger.error(f"Seans silme hatası: {e}")
                        QMessageBox.critical(self, "Hata", f"Seans silinirken hata oluştu:\n{str(e)}")
    
    def export_history(self):
        """Geçmişi dışa aktar"""
        # Bu özellik gelecekte implement edilebilir
        QMessageBox.information(self, "Bilgi", "Dışa aktarma özelliği yakında eklenecek.")
    
    def closeEvent(self, event):
        """Pencere kapatılırken"""
        try:
            # Ana pencereyi aktif et
            if self.main_window:
                try:
                    self.main_window.raise_()
                    self.main_window.activateWindow()
                except Exception as e:
                    self.logger.warning(f"Ana pencere aktif edilirken hata: {e}")
        except Exception as e:
            self.logger.warning(f"closeEvent hatası: {e}")
        
        event.accept()
    
    def generate_selected_pdf(self):
        """Seçili seanslar için PDF raporu oluştur"""
        if not PDF_AVAILABLE:
            QMessageBox.warning(
                self,
                "PDF Özelliği Kullanılamıyor",
                "PDF raporu oluşturmak için 'reportlab' kütüphanesi gerekli.\n"
                "Lütfen 'pip install reportlab' komutunu çalıştırın.",
                QMessageBox.StandardButton.Ok
            )
            return
        
        session_ids = self.get_selected_session_ids()

        # Backward compatibility: if the user selected table rows/cells instead of
        # checking the first-column boxes, use those selected rows too.
        if not session_ids:
            selected_rows = set()
            for item in self.treatment_table.selectedItems():
                selected_rows.add(item.row())

            for row in selected_rows:
                item = self.treatment_table.item(row, 0)
                session_id = item.data(Qt.ItemDataRole.UserRole) if item else None
                if session_id:
                    session_ids.append(session_id)

        if not session_ids:
            QMessageBox.information(
                self,
                "Seçim Gerekli",
                "Lütfen rapor oluşturmak istediğiniz seansları seçin.",
                QMessageBox.StandardButton.Ok
            )
            return
        
        # Disable PDF buttons during generation
        if hasattr(self, 'pdf_selected_btn'):
            self.pdf_selected_btn.setEnabled(False)
            self.pdf_selected_btn.setText("PDF Oluşturuluyor...")
        
        # Prepare output path
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        desktop_path = os.path.expanduser("~/Desktop")
        output_path = os.path.join(desktop_path, f"PEMF_Secili_Seanslar_{timestamp}.pdf")
        
        # Create and start background task
        runnable = PDFGeneratorRunnable(
            app_data_dir=self.app_data_dir,
            session_ids=session_ids,
            output_path=output_path,
            include_patient_info=True,
            include_statistics=True,
            logger=self.logger
        )
        
        # Connect runnable signals to window signals (thread-safe)
        runnable.signals.finished.connect(self.pdf_generated.emit)
        runnable.signals.error.connect(self.pdf_generation_error.emit)
        
        # Start in thread pool
        self.thread_pool.start(runnable)
    
    def generate_all_pdf(self):
        """Filtrelenmiş tüm seanslar için PDF raporu oluştur"""
        if not PDF_AVAILABLE:
            QMessageBox.warning(
                self,
                "PDF Özelliği Kullanılamıyor",
                "PDF raporu oluşturmak için 'reportlab' kütüphanesi gerekli.\n"
                "Lütfen 'pip install reportlab' komutunu çalıştırın.",
                QMessageBox.StandardButton.Ok
            )
            return
        
        # Tablodaki tüm seans ID'lerini al
        session_ids = []
        for row in range(self.treatment_table.rowCount()):
            session_id = self.treatment_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
            if session_id:
                session_ids.append(session_id)
        
        if not session_ids:
            QMessageBox.information(
                self,
                "Veri Yok",
                "Rapor oluşturmak için seans verisi bulunamadı.",
                QMessageBox.StandardButton.Ok
            )
            return
        
        # Disable PDF buttons during generation
        if hasattr(self, 'pdf_all_btn'):
            self.pdf_all_btn.setEnabled(False)
            self.pdf_all_btn.setText("PDF Oluşturuluyor...")
        
        # Prepare output path
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        desktop_path = os.path.expanduser("~/Desktop")
        output_path = os.path.join(desktop_path, f"PEMF_Tum_Seanslar_{timestamp}.pdf")
        
        # Create and start background task
        runnable = PDFGeneratorRunnable(
            app_data_dir=self.app_data_dir,
            session_ids=session_ids,
            output_path=output_path,
            include_patient_info=True,
            include_statistics=True,
            logger=self.logger
        )
        
        # Connect runnable signals to window signals (thread-safe)
        runnable.signals.finished.connect(self.pdf_generated.emit)
        runnable.signals.error.connect(self.pdf_generation_error.emit)
        
        # Start in thread pool
        self.thread_pool.start(runnable)
    
    def send_email_pdf(self):
        """E-posta ile PDF gönder - Seçili seanslar varsa onlar için PDF oluştur, yoksa son PDF'i gönder"""
        # Önce seçili seansları kontrol et
        selected_session_ids = self.get_selected_session_ids()
        
        if selected_session_ids:
            # Seçili seanslar var - Onlar için PDF oluşturup gönder
            self._send_selected_sessions_email(selected_session_ids)
        elif self.last_generated_pdf and os.path.exists(self.last_generated_pdf):
            # Seçili seans yok ama son PDF var - Onu gönder
            dialog = EmailPDFDialog(self.last_generated_pdf, self)
            dialog.exec()
        else:
            # Ne seçili seans var ne de son PDF
            QMessageBox.warning(
                self,
                "PDF Bulunamadı",
                "Gönderilecek PDF dosyası bulunamadı.\n\n"
                "Lütfen:\n"
                "• Seansları seçip e-posta ile gönderin, veya\n"
                "• Önce bir PDF raporu oluşturun.",
                QMessageBox.StandardButton.Ok
            )
    
    def _send_selected_sessions_email(self, session_ids):
        """Seçili seanslar için PDF oluşturup direkt e-posta ile gönder (internal method)"""
        if not PDF_AVAILABLE:
            QMessageBox.warning(
                self,
                "PDF Özelliği Kullanılamıyor",
                "PDF raporu oluşturmak için 'reportlab' kütüphanesi gerekli.\n"
                "Lütfen 'pip install reportlab' komutunu çalıştırın.",
                QMessageBox.StandardButton.Ok
            )
            return
        
        # Disable email button during generation
        if hasattr(self, 'email_pdf_btn'):
            self.email_pdf_btn.setEnabled(False)
            self.email_pdf_btn.setText("PDF Oluşturuluyor...")
        
        # Prepare temporary output path
        import tempfile
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        temp_dir = tempfile.gettempdir()
        temp_pdf_path = os.path.join(temp_dir, f"PEMF_Secili_Seanslar_{timestamp}.pdf")
        
        # Store session_ids for email handler
        self._pending_email_session_ids = session_ids
        
        # Create and start background task
        runnable = PDFGeneratorRunnable(
            app_data_dir=self.app_data_dir,
            session_ids=session_ids,
            output_path=temp_pdf_path,
            include_patient_info=True,
            include_statistics=True,
            logger=self.logger
        )
        
        # Connect runnable signals to email-specific handler (thread-safe)
        runnable.signals.finished.connect(self.email_pdf_generated.emit)
        runnable.signals.error.connect(self.pdf_generation_error.emit)
        
        # Start in thread pool
        self.thread_pool.start(runnable)

    def select_all_sessions(self):
        """Tüm seansları seç"""
        for row in range(self.treatment_table.rowCount()):
            checkbox_item = self.treatment_table.item(row, 0)
            if checkbox_item:
                checkbox_item.setCheckState(Qt.CheckState.Checked)
        self.update_delete_button_state()
    
    def deselect_all_sessions(self):
        """Tüm seansların seçimini kaldır"""
        for row in range(self.treatment_table.rowCount()):
            checkbox_item = self.treatment_table.item(row, 0)
            if checkbox_item:
                checkbox_item.setCheckState(Qt.CheckState.Unchecked)
        self.update_delete_button_state()
    
    def on_checkbox_changed(self, item):
        """Checkbox değiştiğinde çağrılır"""
        if item.column() == 0:  # Sadece checkbox sütunu için
            self.update_delete_button_state()
    
    def update_delete_button_state(self):
        """Seçili seans sayısına göre sil butonunu aktif/pasif yap"""
        selected_count = self.get_selected_session_count()
        self.delete_selected_btn.setEnabled(selected_count > 0)
        
        if selected_count > 0:
            self.delete_selected_btn.setText(f"Seçilenleri Sil ({selected_count})")
        else:
            self.delete_selected_btn.setText("Seçilenleri Sil")
        
        # E-posta butonunu güncelle: Seçili seans varsa veya son PDF varsa aktif
        if hasattr(self, 'email_pdf_btn') and self.email_pdf_btn is not None:
            has_selected = selected_count > 0
            has_last_pdf = bool(self.last_generated_pdf and os.path.exists(self.last_generated_pdf)) if (hasattr(self, 'last_generated_pdf') and self.last_generated_pdf) else False
            self.email_pdf_btn.setEnabled(has_selected or has_last_pdf)
            
            if has_selected:
                self.email_pdf_btn.setText(f"📧 Seçili Seansları E-posta ile Gönder ({selected_count})")
            else:
                self.email_pdf_btn.setText("📧 E-posta ile Gönder")
    
    def get_selected_session_count(self):
        """Seçili seans sayısını döndür"""
        count = 0
        for row in range(self.treatment_table.rowCount()):
            checkbox_item = self.treatment_table.item(row, 0)
            if checkbox_item and checkbox_item.checkState() == Qt.CheckState.Checked:
                count += 1
        return count
    
    def get_selected_session_ids(self):
        """Seçili seans ID'lerini döndür"""
        selected_ids = []
        for row in range(self.treatment_table.rowCount()):
            checkbox_item = self.treatment_table.item(row, 0)
            if checkbox_item and checkbox_item.checkState() == Qt.CheckState.Checked:
                session_id = checkbox_item.data(Qt.ItemDataRole.UserRole)
                if session_id:
                    selected_ids.append(session_id)
        return selected_ids
    
    def delete_selected_sessions(self):
        """Seçili seansları sil"""
        selected_ids = self.get_selected_session_ids()
        
        if not selected_ids:
            QMessageBox.information(self, "Bilgi", "Silinecek seans seçilmedi.")
            return
        
        # Onay iste
        reply = QMessageBox.question(
            self, 
            "Seansları Sil", 
            f"{len(selected_ids)} adet seansı silmek istediğinizden emin misiniz?\n\n"
            "Bu işlem geri alınamaz!",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                # Seansları tek tek sil
                deleted_count = 0
                failed_count = 0
                
                for session_id in selected_ids:
                    try:
                        self.db.delete_session(session_id)
                        deleted_count += 1
                    except Exception as e:
                        self.logger.error(f"Seans {session_id} silinirken hata: {e}", exc_info=True)
                        failed_count += 1
                
                # Sonuç mesajı
                if deleted_count > 0:
                    message = f"{deleted_count} seans başarıyla silindi."
                    if failed_count > 0:
                        message += f"\n{failed_count} seans silinemedi."
                    
                    QMessageBox.information(self, "Başarılı", message)
                    
                    # Tabloyu yenile
                    self.load_history()
                    
                    # Detay bölümünü temizle
                    self.clear_session_details()
                    self.view_details_btn.setEnabled(False)
                    self.delete_session_btn.setEnabled(False)
                    
                else:
                    QMessageBox.warning(self, "Hata", "Hiçbir seans silinemedi.")
                    
            except Exception as e:
                self.logger.error(f"Toplu silme hatası: {e}", exc_info=True)
                QMessageBox.critical(self, "Hata", f"Seanslar silinirken hata oluştu:\n{str(e)}")


class SessionDetailDialog(QDialog):
    """Seans detay dialog penceresi"""
    
    def __init__(self, session_id, db, parent=None):
        super().__init__(parent)
        self.session_id = session_id
        self.db = db
        self.logger = logging.getLogger(__name__)
        
        self.setWindowTitle("Seans Detayları")
        self.setModal(True)
        self.resize(600, 500)
        
        self.setup_ui()
        self.load_session_data()
        self.apply_styles()
    
    def setup_ui(self):
        """UI oluştur"""
        layout = QVBoxLayout(self)
        
        # Scroll area
        scroll = QScrollArea()
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        
        self.content_layout = scroll_layout
        
        scroll.setWidget(scroll_widget)
        scroll.setWidgetResizable(True)
        layout.addWidget(scroll)
        
        # Butonlar
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
    
    def load_session_data(self):
        """Seans verilerini yükle"""
        try:
            session = self.db.get_session_details(self.session_id)
            
            if session:
                # Başlık
                title = QLabel(f"Seans #{session.get('id')} - {session.get('session_date')}")
                title.setObjectName("dialogTitle")
                self.content_layout.addWidget(title)
                
                # Genel bilgiler grubu
                general_group = QGroupBox("Genel Bilgiler")
                general_layout = QGridLayout(general_group)
                
                general_layout.addWidget(QLabel("Tarih:"), 0, 0)
                general_layout.addWidget(QLabel(session.get('session_date', '-')), 0, 1)
                
                general_layout.addWidget(QLabel("Başlangıç:"), 1, 0)
                general_layout.addWidget(QLabel(session.get('start_time', '-')), 1, 1)
                
                general_layout.addWidget(QLabel("Bitiş:"), 2, 0)
                general_layout.addWidget(QLabel(session.get('end_time', '-') or '-'), 2, 1)
                
                duration = session.get('duration_minutes', 0) or 0
                general_layout.addWidget(QLabel("Süre:"), 3, 0)
                general_layout.addWidget(QLabel(f"{duration} dakika"), 3, 1)
                
                general_layout.addWidget(QLabel("Mod:"), 4, 0)
                general_layout.addWidget(QLabel(session.get('treatment_mode', '-')), 4, 1)
                
                general_layout.addWidget(QLabel("Hedef:"), 5, 0)
                general_layout.addWidget(QLabel(session.get('target_condition', '-') or '-'), 5, 1)
                
                general_layout.addWidget(QLabel("Uygulayıcı:"), 6, 0)
                general_layout.addWidget(QLabel(session.get('operator_name', '-') or '-'), 6, 1)
                
                self.content_layout.addWidget(general_group)
                
                # Parametreler grubu
                if session.get('parameters'):
                    params_group = QGroupBox("Seans Parametreleri")
                    params_layout = QGridLayout(params_group)
                    
                    # Parametre isimlerinin Türkçe karşılıkları
                    param_translations = {
                        'frequency_hz': 'Frekans (Hz)',
                        'intensity_mt': 'Yoğunluk (mT)',
                        'duty_cycle': 'Duty Cycle',
                        'pulse_duration_ms': 'Pulse Süresi (ms)',
                        'duration': 'Süre (dakika)',
                        'planned_duration': 'Planlanan Süre',
                        'actual_duration': 'Gerçekleşen Süre',
                        'stop_reason': 'Durdurma Nedeni',
                        'connected_coils': 'Bağlı Bobinler',
                        'patient_name': 'Hasta Adı',
                        'patient_age': 'Hasta Yaşı',
                        'patient_species': 'Hasta Türü',
                        'patient_breed': 'Hasta Irkı',
                        'patient_weight': 'Hasta Ağırlığı',
                        'patient_owner': 'Hasta Sahibi',
                        'patient_veteriner': 'Hasta Veterineri',
                        'patient_vet_contact': 'Veteriner İletişim',
                        'target_condition': 'Hedef Durum',
                        'treatment_mode': 'Seans Modu',
                        'operator_name': 'Uygulayıcı'
                    }
                    
                    row = 0
                    for param_name, param_data in session['parameters'].items():
                        # Parametre adını Türkçe'ye çevir
                        display_name = param_translations.get(param_name, param_name.replace('_', ' ').title())
                        
                        if isinstance(param_data, dict):
                            value = param_data.get('value', '')
                            unit = param_data.get('unit', '')
                            
                            # None veya boş değerleri kontrol et
                            if value is None or value == '' or str(value).lower() == 'none':
                                display_value = 'Belirtilmemiş'
                            else:
                                display_value = f"{value} {unit}".strip()
                        else:
                            # None veya boş değerleri kontrol et
                            if param_data is None or param_data == '' or str(param_data).lower() == 'none':
                                display_value = 'Belirtilmemiş'
                            else:
                                display_value = str(param_data)
                        
                        params_layout.addWidget(QLabel(f"{display_name}:"), row, 0)
                        params_layout.addWidget(QLabel(display_value), row, 1)
                        row += 1
                    
                    self.content_layout.addWidget(params_group)
                
                # Hasta bilgileri grubu (parametrelerden ayrı olarak)
                patient_group = QGroupBox("Hasta Bilgileri")
                patient_layout = QGridLayout(patient_group)
                
                parameters = session.get('parameters', {})
                
                # Hasta bilgilerini göster
                patient_info = [
                    ('Hasta Adı', parameters.get('patient_name', {}).get('value', 'Belirtilmemiş')),
                    ('Hasta Yaşı', parameters.get('patient_age', {}).get('value', 'Belirtilmemiş')),
                    ('Hasta Türü', parameters.get('patient_species', {}).get('value', 'Belirtilmemiş')),
                    ('Hasta Irkı', parameters.get('patient_breed', {}).get('value', 'Belirtilmemiş')),
                    ('Hasta Ağırlığı', parameters.get('patient_weight', {}).get('value', 'Belirtilmemiş')),
                    ('Hasta Sahibi', parameters.get('patient_owner', {}).get('value', 'Belirtilmemiş')),
                    ('Veteriner İletişim', parameters.get('patient_vet_contact', {}).get('value', 'Belirtilmemiş'))
                ]
                
                row = 0
                for label, value in patient_info:
                    # None veya boş değerleri kontrol et
                    if value is None or value == '' or str(value).lower() == 'none':
                        display_value = 'Belirtilmemiş'
                    else:
                        display_value = str(value)
                    
                    patient_layout.addWidget(QLabel(f"{label}:"), row, 0)
                    patient_layout.addWidget(QLabel(display_value), row, 1)
                    row += 1
                
                self.content_layout.addWidget(patient_group)
                
                # Notlar grubu
                notes = session.get('patient_notes', '')
                if notes and notes.strip():
                    notes_group = QGroupBox("Hasta Notları")
                    notes_layout = QVBoxLayout(notes_group)
                    
                    notes_text = QTextEdit()
                    notes_text.setPlainText(notes)
                    notes_text.setReadOnly(True)
                    
                    notes_layout.addWidget(notes_text)
                    self.content_layout.addWidget(notes_group)
                else:
                    # Notlar yoksa bilgi ver
                    notes_group = QGroupBox("Hasta Notları")
                    notes_layout = QVBoxLayout(notes_group)
                    
                    no_notes_label = QLabel("Bu seans için not bulunmuyor.")
                    no_notes_label.setStyleSheet("color: #888888; font-style: italic;")
                    notes_layout.addWidget(no_notes_label)
                    
                    self.content_layout.addWidget(notes_group)
                
        except Exception as e:
            self.logger.error(f"Seans detayları yüklenirken hata: {e}", exc_info=True)
            error_label = QLabel(f"Seans detayları yüklenirken hata oluştu: {str(e)}")
            error_label.setStyleSheet("color: #ff6b6b; font-weight: bold;")
            self.content_layout.addWidget(error_label)
    
    def apply_styles(self):
        """Dialog stillerini uygula"""
        self.setStyleSheet("""
            QDialog {
                background-color: #2b2b2b;
                color: #ffffff;
            }
            
            #dialogTitle {
                font-size: 14pt;
                font-weight: bold;
                color: #8e44ad;
                margin: 10px 0;
            }
            
            QGroupBox {
                font-weight: bold;
                border: 1px solid #30363d;
                border-radius: 6px;
                margin: 10px 0;
                padding-top: 10px;
            }
            
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
                color: #8b949e;
            }
            
            QTextEdit {
                background-color: #3c3c3c;
                border: 2px solid #555555;
                border-radius: 6px;
                padding: 8px;
                color: white;
            }
        """)


if __name__ == "__main__":
    
    app = QApplication(sys.argv)
    window = TreatmentHistoryWindow()
    window.show()
    sys.exit(app.exec())
