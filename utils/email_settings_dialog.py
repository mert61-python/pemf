"""
E-posta Ayarları Dialog Modülü
PDF raporlarını e-posta ile göndermek için ayarlar ve gönderim dialog'u
"""

import sys
import json
import os
import re
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QCheckBox,
    QWidget,
    QMessageBox,
    QScrollArea,
    QFrame,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from pathlib import Path
import logging

# Design System
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)
from styles import StyleMixin

try:
    from .path_utils import get_app_data_directory
except ImportError:
    from path_utils import get_app_data_directory


EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


class EmailWorkerThread(QThread):
    """SMTP işlemlerini UI thread dışında çalıştırır."""

    completed = pyqtSignal(str, bool, str)

    def __init__(self, operation: str, payload: dict, parent=None):
        super().__init__(parent)
        self.operation = operation
        self.payload = payload

    def run(self):
        try:
            try:
                from .email_sender import get_email_sender
            except ImportError:
                from email_sender import get_email_sender

            email_sender = get_email_sender()

            if self.operation == 'test_connection':
                success = email_sender.test_email_connection(
                    self.payload['sender_email'],
                    self.payload['sender_password']
                )
                message = "Bağlantı testi tamamlandı"

            elif self.operation == 'send_email':
                success = email_sender.send_report_email(
                    sender_email=self.payload['sender_email'],
                    sender_password=self.payload['sender_password'],
                    recipient_emails=self.payload['recipient_emails'],
                    pdf_file_path=self.payload['pdf_file_path'],
                    patient_name=self.payload.get('patient_name', ''),
                    clinic_name=self.payload.get('clinic_name', 'Veteriner Kliniği'),
                    additional_message=self.payload.get('additional_message', '')
                )
                message = "Gönderim tamamlandı"

            else:
                success = False
                message = f"Bilinmeyen işlem: {self.operation}"

            self.completed.emit(self.operation, success, message)

        except Exception as e:
            self.completed.emit(self.operation, False, str(e))

class EmailSettingsDialog(QDialog, StyleMixin):
    """E-posta ayarları ve gönderim dialog'u - Design System entegrasyonu"""
    
    def __init__(self, parent=None, pdf_file_path=None):
        super().__init__(parent)
        self.pdf_file_path = pdf_file_path
        self.logger = logging.getLogger(__name__)
        self.settings_file = get_app_data_directory() / "email_settings.json"
        self._active_worker = None
        
        # Apply design system theme
        self.apply_theme()
        
        self.init_ui()
        self.load_settings()
        self.setup_connections()
    
    def init_ui(self):
        """Kullanıcı arayüzünü başlat"""
        self.setWindowTitle("📧 E-posta ile Rapor Gönder")
        self.setWindowFlags(
            self.windowFlags()
            | Qt.WindowType.Window
            | Qt.WindowType.WindowMinMaxButtonsHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.setModal(True)
        self.resize(550, 700)
        self.setMinimumSize(550, 700)

        # Responsive davranış için tüm içeriği scroll alanına al
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)

        content_widget = QWidget()
        
        # Ana layout
        layout = QVBoxLayout(content_widget)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Başlık
        title_label = QLabel("📧 E-posta ile PDF Raporu Gönder")
        title_label.setStyleSheet("""
            QLabel {
                font-size: 14pt;
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
        
        # Gönderen bilgileri
        sender_group = QGroupBox("Gönderen Bilgileri")
        sender_layout = QFormLayout()
        
        self.sender_email_edit = QLineEdit()
        self.sender_email_edit.setPlaceholderText("ornek@gmail.com")
        
        self.sender_password_edit = QLineEdit()
        self.sender_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.sender_password_edit.setPlaceholderText("E-posta şifresi veya App Password")
        
        self.clinic_name_edit = QLineEdit()
        self.clinic_name_edit.setPlaceholderText("Veteriner Kliniği Adı")
        
        # Şifre göster/gizle butonu
        password_layout = QHBoxLayout()
        password_layout.addWidget(self.sender_password_edit)
        
        self.show_password_btn = QPushButton("👁")
        self.show_password_btn.setFixedSize(30, 30)
        self.show_password_btn.setCheckable(True)
        self.show_password_btn.setToolTip("Şifreyi göster/gizle")
        password_layout.addWidget(self.show_password_btn)
        
        password_widget = QWidget()
        password_widget.setLayout(password_layout)
        
        sender_layout.addRow("E-posta Adresi:", self.sender_email_edit)
        sender_layout.addRow("Şifre:", password_widget)
        sender_layout.addRow("Klinik Adı:", self.clinic_name_edit)
        
        sender_group.setLayout(sender_layout)
        layout.addWidget(sender_group)
        
        # Test bağlantı butonu
        self.test_connection_btn = QPushButton("🔗 Bağlantıyı Test Et")
        self.test_connection_btn.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 6px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
        """)
        layout.addWidget(self.test_connection_btn)
        
        # Alıcı bilgileri
        recipient_group = QGroupBox("Alıcı Bilgileri")
        recipient_layout = QVBoxLayout()
        
        # Alıcı e-posta listesi
        recipient_label = QLabel("Alıcı E-posta Adresleri:")
        recipient_layout.addWidget(recipient_label)
        
        self.recipients_text = QTextEdit()
        self.recipients_text.setMaximumHeight(100)
        self.recipients_text.setPlaceholderText(
            "E-posta adreslerini her satıra bir tane gelecek şekilde yazın:\n"
            "doktor1@example.com\n"
            "doktor2@example.com"
        )
        recipient_layout.addWidget(self.recipients_text)
        
        recipient_group.setLayout(recipient_layout)
        layout.addWidget(recipient_group)
        
        # Ek mesaj
        message_group = QGroupBox("Ek Mesaj (İsteğe Bağlı)")
        message_layout = QVBoxLayout()
        
        self.additional_message_text = QTextEdit()
        self.additional_message_text.setMaximumHeight(80)
        self.additional_message_text.setPlaceholderText(
            "Rapor ile birlikte göndermek istediğiniz ek mesajı buraya yazabilirsiniz..."
        )
        message_layout.addWidget(self.additional_message_text)
        
        message_group.setLayout(message_layout)
        layout.addWidget(message_group)
        
        # PDF dosya bilgisi
        if self.pdf_file_path:
            file_group = QGroupBox("Gönderilecek Dosya")
            file_layout = QVBoxLayout()
            
            file_name = os.path.basename(self.pdf_file_path)
            file_size = os.path.getsize(self.pdf_file_path) / 1024  # KB
            
            file_info_label = QLabel(f"📄 {file_name}\n📊 Boyut: {file_size:.1f} KB")
            file_info_label.setStyleSheet("""
                QLabel {
                    background-color: #f8f9fa;
                    padding: 10px;
                    border: 1px solid #dee2e6;
                    border-radius: 6px;
                    font-family: monospace;
                }
            """)
            file_layout.addWidget(file_info_label)
            
            file_group.setLayout(file_layout)
            layout.addWidget(file_group)
        
        # Ayarları kaydet checkbox
        self.save_settings_cb = QCheckBox("E-posta ayarlarını kaydet (şifre hariç)")
        self.save_settings_cb.setChecked(True)
        layout.addWidget(self.save_settings_cb)
        
        # Butonlar
        button_layout = QHBoxLayout()
        
        self.send_btn = QPushButton("📧 Gönder")
        self.send_btn.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                border: none;
                padding: 12px 24px;
                border-radius: 8px;
                font-size: 11pt;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #229954;
            }
            QPushButton:disabled {
                background-color: #95a5a6;
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
                font-size: 11pt;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
        """)
        
        button_layout.addWidget(self.cancel_btn)
        button_layout.addStretch()
        button_layout.addWidget(self.send_btn)
        
        layout.addLayout(button_layout)
        
        scroll_area.setWidget(content_widget)
        outer_layout.addWidget(scroll_area)
    
    def setup_connections(self):
        """Sinyal bağlantılarını kur"""
        self.send_btn.clicked.connect(self.send_email)
        self.cancel_btn.clicked.connect(self.reject)
        self.test_connection_btn.clicked.connect(self.test_connection)
        self.show_password_btn.toggled.connect(self.toggle_password_visibility)
    
    def toggle_password_visibility(self, checked):
        """Şifre görünürlüğünü değiştir"""
        if checked:
            self.sender_password_edit.setEchoMode(QLineEdit.EchoMode.Normal)
            self.show_password_btn.setText("🙈")
        else:
            self.sender_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
            self.show_password_btn.setText("👁")
    
    def load_settings(self):
        """Kaydedilmiş ayarları yükle"""
        try:
            if self.settings_file.exists():
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                
                self.sender_email_edit.setText(settings.get('sender_email', ''))
                self.clinic_name_edit.setText(settings.get('clinic_name', ''))
                self.recipients_text.setPlainText(settings.get('recipients', ''))
                
        except Exception as e:
            self.logger.error(f"Ayarlar yükleme hatası: {e}")
    
    def save_settings(self):
        """Ayarları kaydet"""
        try:
            if self.save_settings_cb.isChecked():
                settings = {
                    'sender_email': self.sender_email_edit.text(),
                    'clinic_name': self.clinic_name_edit.text(),
                    'recipients': self.recipients_text.toPlainText()
                }
                
                with open(self.settings_file, 'w', encoding='utf-8') as f:
                    json.dump(settings, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            self.logger.error(f"Ayarlar kaydetme hatası: {e}")
    
    def test_connection(self):
        """E-posta bağlantısını test et"""
        sender_email = self.sender_email_edit.text().strip()
        sender_password = self.sender_password_edit.text()
        
        if not sender_email or not sender_password:
            QMessageBox.warning(
                self,
                "Eksik Bilgi",
                "Lütfen e-posta adresi ve şifre girin.",
                QMessageBox.StandardButton.Ok
            )
            return
        
        self.test_connection_btn.setEnabled(False)
        self.test_connection_btn.setText("🔄 Test ediliyor...")

        self._active_worker = EmailWorkerThread(
            operation='test_connection',
            payload={
                'sender_email': sender_email,
                'sender_password': sender_password,
            },
            parent=self,
        )
        self._active_worker.completed.connect(self._on_email_operation_completed)
        self._active_worker.start()
    
    def send_email(self):
        """E-postayı gönder"""
        # Bilgileri kontrol et
        sender_email = self.sender_email_edit.text().strip()
        sender_password = self.sender_password_edit.text()
        clinic_name = self.clinic_name_edit.text().strip() or "Veteriner Kliniği"
        recipients_text = self.recipients_text.toPlainText().strip()
        additional_message = self.additional_message_text.toPlainText().strip()
        
        if not sender_email or not sender_password:
            QMessageBox.warning(
                self,
                "Eksik Bilgi",
                "Lütfen gönderen e-posta adresi ve şifre girin.",
                QMessageBox.StandardButton.Ok
            )
            return
        
        if not recipients_text:
            QMessageBox.warning(
                self,
                "Eksik Bilgi",
                "Lütfen en az bir alıcı e-posta adresi girin.",
                QMessageBox.StandardButton.Ok
            )
            return
        
        if not self.pdf_file_path or not os.path.exists(self.pdf_file_path):
            QMessageBox.warning(
                self,
                "Dosya Hatası",
                "PDF dosyası bulunamadı.",
                QMessageBox.StandardButton.Ok
            )
            return
        
        # Alıcı listesini hazırla
        recipient_emails = []
        for line in recipients_text.split('\n'):
            email = line.strip()
            if email and EMAIL_RE.match(email):
                recipient_emails.append(email)
        
        if not recipient_emails:
            QMessageBox.warning(
                self,
                "Geçersiz E-posta",
                "Geçerli e-posta adresi bulunamadı.",
                QMessageBox.StandardButton.Ok
            )
            return
        
        # Onay al
        reply = QMessageBox.question(
            self,
            "E-posta Gönder",
            f"PDF raporu {len(recipient_emails)} alıcıya gönderilsin mi?\n\n"
            f"Alıcılar: {', '.join(recipient_emails[:3])}"
            f"{'...' if len(recipient_emails) > 3 else ''}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )
        
        if reply != QMessageBox.StandardButton.Yes:
            return
        
        self.send_btn.setEnabled(False)
        self.send_btn.setText("📤 Gönderiliyor...")

        # Hasta adını PDF dosya adından çıkarmaya çalış
        patient_name = ""
        filename = os.path.basename(self.pdf_file_path)
        if "Hasta_" in filename:
            try:
                patient_name = filename.split("Hasta_")[1].split("_")[0]
            except Exception:
                patient_name = ""

        self._active_worker = EmailWorkerThread(
            operation='send_email',
            payload={
                'sender_email': sender_email,
                'sender_password': sender_password,
                'recipient_emails': recipient_emails,
                'pdf_file_path': self.pdf_file_path,
                'patient_name': patient_name,
                'clinic_name': clinic_name,
                'additional_message': additional_message,
            },
            parent=self,
        )
        self._active_worker.completed.connect(self._on_email_operation_completed)
        self._active_worker.start()

    def _on_email_operation_completed(self, operation: str, success: bool, message: str):
        """Arka plan SMTP işlemleri tamamlandığında UI güncelle."""
        if operation == 'test_connection':
            self.test_connection_btn.setEnabled(True)
            self.test_connection_btn.setText("🔗 Bağlantıyı Test Et")

            if success:
                QMessageBox.information(
                    self,
                    "Bağlantı Başarılı",
                    "E-posta bağlantısı başarıyla test edildi!",
                    QMessageBox.StandardButton.Ok
                )
            else:
                QMessageBox.warning(
                    self,
                    "Bağlantı Hatası",
                    "E-posta bağlantısı başarısız!\n\n"
                    "Lütfen kontrol edin:\n"
                    "• E-posta adresi doğru mu?\n"
                    "• Şifre doğru mu?\n"
                    "• Gmail kullanıyorsanız App Password kullanın\n"
                    "• İnternet bağlantınız aktif mi?\n\n"
                    f"Detay: {message}",
                    QMessageBox.StandardButton.Ok
                )

        elif operation == 'send_email':
            self.send_btn.setEnabled(True)
            self.send_btn.setText("📧 Gönder")

            if success:
                self.save_settings()
                recipient_count = len([
                    line.strip()
                    for line in self.recipients_text.toPlainText().split('\n')
                    if line.strip() and EMAIL_RE.match(line.strip())
                ])

                QMessageBox.information(
                    self,
                    "Gönderim Başarılı",
                    f"PDF raporu başarıyla gönderildi!\n\n"
                    f"Alıcı sayısı: {recipient_count}",
                    QMessageBox.StandardButton.Ok
                )
                self.accept()
            else:
                QMessageBox.critical(
                    self,
                    "Gönderim Hatası",
                    "E-posta gönderilemedi!\n\n"
                    "Lütfen ayarlarınızı kontrol edin ve tekrar deneyin.\n\n"
                    f"Detay: {message}",
                    QMessageBox.StandardButton.Ok
                )

        self._active_worker = None


if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Test için dialog aç
    dialog = EmailSettingsDialog(pdf_file_path="test_report.pdf")
    
    if dialog.exec() == QDialog.DialogCode.Accepted:
        print("E-posta gönderimi başarılı!")
    else:
        print("E-posta gönderimi iptal edildi.")
    
    sys.exit()