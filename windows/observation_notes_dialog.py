"""
Seans Sonrası Gözlem Notları Dialog Modülü
Tedavi seansı sonrasında hayvanın tepkilerini kaydetmek için dialog penceresi
"""

import sys
import os

# Add parent directory to path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from PyQt6.QtWidgets import (
    QVBoxLayout, QHBoxLayout,
    QGroupBox, QLabel, QPushButton,
    QButtonGroup, QMessageBox, QFormLayout,
    QTextEdit, QDialog, QApplication
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QTextCursor
from datetime import datetime
import logging
from styles import StyleMixin
from utils.responsive_utils import get_screen_info

class ObservationNotesDialog(QDialog, StyleMixin):
    """Seans sonrası gözlem notları dialog penceresi - Design System entegrasyonu"""
    
    def __init__(self, parent=None, session_id=None, patient_name="", treatment_mode=""):
        super().__init__(parent)
        self.session_id = session_id
        self.patient_name = patient_name
        self.treatment_mode = treatment_mode
        self.logger = logging.getLogger(__name__)
        
        # Get app_data_dir from parent (main_window) or fallback
        self.app_data_dir = None
        if parent and hasattr(parent, 'app_data_dir'):
            self.app_data_dir = parent.app_data_dir
        else:
            # Try to get from main_window if parent is not main_window
            try:
                from windows.gui_pyqt_v11 import get_app_data_directory
                self.app_data_dir = get_app_data_directory()
            except Exception as e:
                self.logger.warning(f"app_data_dir alınamadı, varsayılan kullanılacak: {e}")
                from pathlib import Path
                self.app_data_dir = Path.home() / ".pemf_gui"
        
        # Apply design system theme
        self.apply_theme()

        self._setup_responsive_window()
        
        self.init_ui()
        self.setup_connections()
    
    def init_ui(self):
        """Kullanıcı arayüzünü başlat"""
        self.setWindowTitle("Seans Sonrası Gözlem Notları")
        self.setModal(True)
        
        # Ana layout
        layout = QVBoxLayout()
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Başlık
        title_label = QLabel("🐾 Seans Sonrası Gözlem Notları")
        title_label.setStyleSheet("""
            QLabel {
                font-size: 18px;
                font-weight: bold;
                color: #2c3e50;
                padding: 10px;
                background-color: #ecf0f1;
                border-radius: 8px;
                margin-bottom: 10px;
            }
        """)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)
        
        # Hasta bilgileri
        info_group = QGroupBox("Seans Bilgileri")
        info_layout = QFormLayout()
        
        self.patient_label = QLabel(self.patient_name or "Bilinmiyor")
        self.mode_label = QLabel(self.treatment_mode or "Bilinmiyor")
        self.date_label = QLabel(datetime.now().strftime("%d.%m.%Y %H:%M"))
        
        info_layout.addRow("Hasta Adı:", self.patient_label)
        info_layout.addRow("Seans Modu:", self.mode_label)
        info_layout.addRow("Tarih/Saat:", self.date_label)
        
        info_group.setLayout(info_layout)
        layout.addWidget(info_group)
        
        # Hızlı tepki seçenekleri
        reaction_group = QGroupBox("Hayvanın Tepkisi (Hızlı Seçim)")
        reaction_layout = QVBoxLayout()
        
        self.reaction_buttons = QButtonGroup()
        
        reactions = [
            ("😌 Sakinleşti", "sakinlesti", "#27ae60"),
            ("🏃 Hareket etti / Aktif", "hareket_etti", "#3498db"),
            ("😴 Uyudu / Dinlendi", "uyudu", "#9b59b6"),
            ("😰 Endişeli / Gergin", "endiseli", "#e67e22"),
            ("😐 Hiçbir tepki yok", "tepki_yok", "#95a5a6"),
            ("🤕 Rahatsızlık belirtisi", "rahatsizlik", "#e74c3c")
        ]
        
        for text, value, color in reactions:
            btn = QPushButton(text)
            btn.setCheckable(True)
            btn.setProperty("reaction_value", value)
            btn.setStyleSheet(f"""
                QPushButton {{
                    padding: 10px;
                    border: 2px solid {color};
                    border-radius: 8px;
                    background-color: white;
                    font-size: 12px;
                    margin: 2px;
                }}
                QPushButton:checked {{
                    background-color: {color};
                    color: white;
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    background-color: {color}22;
                }}
            """)
            self.reaction_buttons.addButton(btn)
            reaction_layout.addWidget(btn)
        
        reaction_group.setLayout(reaction_layout)
        layout.addWidget(reaction_group)
        
        # Detaylı notlar
        notes_group = QGroupBox("Detaylı Gözlem Notları")
        notes_layout = QVBoxLayout()
        
        self.notes_text = QTextEdit()
        self.notes_text.setPlaceholderText(
            "Hayvanın seans sırasında ve sonrasındaki davranışları, "
            "fiziksel tepkileri ve genel durumu hakkında detaylı notlar yazabilirsiniz...\n\n"
            "Örnek:\n"
            "- Seans sırasında sakin kaldı\n"
            "- İlk 5 dakika sonra rahatladı\n"
            "- Seans sonrası daha aktif görünüyor\n"
            "- Ağrılı bölgeye dokunmaya daha az tepki veriyor"
        )
        self.notes_text.setMinimumHeight(150)
        self.notes_text.setStyleSheet("""
            QTextEdit {
                border: 2px solid #bdc3c7;
                border-radius: 8px;
                padding: 10px;
                font-size: 11px;
                line-height: 1.4;
            }
            QTextEdit:focus {
                border-color: #3498db;
            }
        """)
        
        notes_layout.addWidget(self.notes_text)
        notes_group.setLayout(notes_layout)
        layout.addWidget(notes_group)
        
        # Butonlar
        button_layout = QHBoxLayout()
        
        self.save_btn = QPushButton("💾 Kaydet")
        self.save_btn.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                border: none;
                padding: 12px 24px;
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #229954;
            }
            QPushButton:pressed {
                background-color: #1e8449;
            }
        """)
        
        self.cancel_btn = QPushButton("❌ İptal")
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                border: none;
                padding: 12px 24px;
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
            QPushButton:pressed {
                background-color: #a93226;
            }
        """)
        
        button_layout.addWidget(self.cancel_btn)
        button_layout.addStretch()
        button_layout.addWidget(self.save_btn)
        
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
    
    def setup_connections(self):
        """Sinyal bağlantılarını kur"""
        self.save_btn.clicked.connect(self.save_notes)
        self.cancel_btn.clicked.connect(self.reject)
        
        # Hızlı seçim butonları için bağlantı
        for button in self.reaction_buttons.buttons():
            button.clicked.connect(self.on_reaction_selected)
    
    def on_reaction_selected(self):
        """Hızlı tepki seçildiğinde"""
        sender = self.sender()
        reaction_value = sender.property("reaction_value")
        reaction_text = sender.text()
        
        # Mevcut notlara ekle
        current_text = self.notes_text.toPlainText()
        if current_text and not current_text.endswith('\n'):
            current_text += '\n'
        
        timestamp = datetime.now().strftime("%H:%M")
        new_note = f"[{timestamp}] Hayvan tepkisi: {reaction_text}\n"
        
        self.notes_text.setPlainText(current_text + new_note)
        # Cursor'ı text'in sonuna taşı
        cursor = self.notes_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.notes_text.setTextCursor(cursor)
    
    def save_notes(self):
        """Notları kaydet"""
        try:
            # Seçili tepkiyi al
            selected_reaction = None
            for button in self.reaction_buttons.buttons():
                if button.isChecked():
                    selected_reaction = button.property("reaction_value")
                    break
            
            # Notları al
            notes = self.notes_text.toPlainText().strip()
            
            if not notes and not selected_reaction:
                QMessageBox.information(
                    self,
                    "Bilgi",
                    "Lütfen en az bir tepki seçin veya not yazın.",
                    QMessageBox.StandardButton.Ok
                )
                return
            
            # Notları birleştir
            final_notes = ""
            if selected_reaction:
                reaction_text = ""
                for button in self.reaction_buttons.buttons():
                    if button.property("reaction_value") == selected_reaction:
                        reaction_text = button.text()
                        break
                final_notes += f"Tepki: {reaction_text}\n"
            
            if notes:
                if final_notes:
                    final_notes += "\nDetaylı Notlar:\n"
                final_notes += notes
            
            # Veritabanına kaydet
            if not self.session_id:
                QMessageBox.warning(
                    self,
                    "Hata",
                    "Seans ID'si bulunamadı.",
                    QMessageBox.StandardButton.Ok
                )
                return
            
            if not self.app_data_dir:
                QMessageBox.warning(
                    self,
                    "Hata",
                    "Uygulama veri dizini bulunamadı.",
                    QMessageBox.StandardButton.Ok
                )
                return
            
            try:
                from database.treatment_history_db import get_treatment_db
                from pathlib import Path
                
                # app_data_dir'yi Path'e çevir
                if isinstance(self.app_data_dir, str):
                    app_data_dir = Path(self.app_data_dir)
                else:
                    app_data_dir = self.app_data_dir
                
                db = get_treatment_db(app_data_dir)
                
                # Mevcut notları al ve güncelle
                session = db.get_session_details(self.session_id)
                if session:
                    existing_notes = session.get('patient_notes', '') or ''
                    if existing_notes:
                        final_notes = existing_notes + "\n\n--- Seans Sonrası Gözlemler ---\n" + final_notes
                    
                    # Notları güncelle
                    db.update_session_notes(self.session_id, final_notes)
                    
                    self.logger.info(f"Gözlem notları kaydedildi: Session ID {self.session_id}")
                    
                    QMessageBox.information(
                        self,
                        "Başarılı",
                        "Gözlem notları başarıyla kaydedildi.",
                        QMessageBox.StandardButton.Ok
                    )
                    
                    self.accept()
                else:
                    self.logger.warning(f"Seans bulunamadı: Session ID {self.session_id}")
                    QMessageBox.warning(
                        self,
                        "Hata",
                        "Seans bilgileri bulunamadı.",
                        QMessageBox.StandardButton.Ok
                    )
            except ImportError as e:
                self.logger.error(f"Veritabanı modülü import hatası: {e}")
                QMessageBox.critical(
                    self,
                    "Hata",
                    f"Veritabanı modülü yüklenemedi:\n{str(e)}",
                    QMessageBox.StandardButton.Ok
                )
            except Exception as db_error:
                self.logger.error(f"Veritabanı işlemi hatası: {db_error}")
                QMessageBox.critical(
                    self,
                    "Hata",
                    f"Notlar kaydedilirken veritabanı hatası oluştu:\n{str(db_error)}",
                    QMessageBox.StandardButton.Ok
                )
                
        except Exception as e:
            self.logger.error(f"Gözlem notları kaydetme hatası: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "Hata",
                f"Notlar kaydedilirken beklenmeyen bir hata oluştu:\n{str(e)}",
                QMessageBox.StandardButton.Ok
            )
    
    def get_notes(self):
        """Girilen notları döndür"""
        return self.notes_text.toPlainText().strip()

    def closeEvent(self, event):
        """Dialog kapatılırken çağrılır - Kaynakları temizle"""
        self.logger.debug("ObservationNotesDialog kapatılıyor")
        event.accept()

    def _setup_responsive_window(self):
        """Setup responsive window sizing and positioning for the dialog."""
        try:
            width, height, scale_factor, screen_type = get_screen_info()
            
            # Base dimensions for dialog
            base_configs = {
                "mobile": {"width": 500, "height": 600, "min_width": 450, "min_height": 550},
                "tablet": {"width": 550, "height": 650, "min_width": 500, "min_height": 600},
                "laptop": {"width": 600, "height": 700, "min_width": 500, "min_height": 600},
                "desktop": {"width": 600, "height": 700, "min_width": 500, "min_height": 600},
                "ultrawide": {"width": 600, "height": 700, "min_width": 500, "min_height": 600}
            }
            
            config = base_configs.get(screen_type, base_configs["desktop"])
            
            # Scale dimensions based on actual screen size
            target_width = min(int(config["width"] * scale_factor), width * 0.9)
            target_height = min(int(config["height"] * scale_factor), height * 0.9)
            
            # Center window on screen
            x = (width - target_width) // 2
            y = (height - target_height) // 2
            
            # Set window properties
            self.setGeometry(int(x), int(y), int(target_width), int(target_height))
            self.setMinimumSize(config["min_width"], config["min_height"])
            
        except Exception as e:
            self.logger.warning(f"Could not setup responsive window: {e}")
            # Fallback to default sizing
            self.resize(500, 600)
            self.setMinimumSize(450, 550)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Test için dialog aç
    dialog = ObservationNotesDialog(
        session_id=1,
        patient_name="Test Köpeği",
        treatment_mode="Otonom Mod"
    )
    
    if dialog.exec() == QDialog.DialogCode.Accepted:
        # Notlar kaydedildi
        pass
    else:
        pass
    
    sys.exit()
