"""
PDF E-posta Gönderme Dialog Penceresi
PEMF tedavi raporlarının e-posta ile gönderilmesi
"""

import os
import re
import ssl
import smtplib
import json
import logging
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from urllib.parse import quote

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QTextEdit,
    QPushButton, QGroupBox, QGridLayout, QMessageBox, QProgressBar
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

# Design System
import sys
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)
from styles import StyleMixin
from utils.responsive_utils import get_screen_info

try:
    import keyring
    KEYRING_AVAILABLE = True
except Exception:
    KEYRING_AVAILABLE = False


class EmailSendThread(QThread):
    """Email gönderme işlemini arka planda çalıştıran thread (with graceful shutdown)"""
    finished = pyqtSignal(bool, str)  # success, message
    
    def __init__(self, gmail_email, gmail_password, recipient_email, 
                 subject, body, pdf_file_path):
        super().__init__()
        self.gmail_email = gmail_email
        self.gmail_password = gmail_password
        self.recipient_email = recipient_email
        self.subject = subject
        self.body = body
        self.pdf_file_path = pdf_file_path
        self.logger = logging.getLogger(__name__)
        self.stop_requested = False  # Graceful shutdown flag
    
    def run(self):
        """Email gönderme işlemini çalıştır (with graceful shutdown support)"""
        # Graceful shutdown kontrolü
        if self.stop_requested:
            self.finished.emit(False, "E-posta gönderimi iptal edildi")
            return
            
        try:
            # E-posta oluştur
            msg = MIMEMultipart()
            msg['From'] = self.gmail_email
            msg['To'] = self.recipient_email
            msg['Subject'] = self.subject
            
            # Mesaj içeriği
            msg.attach(MIMEText(self.body, 'plain', 'utf-8'))
            
            # PDF eki
            with open(self.pdf_file_path, "rb") as attachment:
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(attachment.read())
            
            encoders.encode_base64(part)
            
            # Dosya adını URL encode et (özel karakterler için)
            safe_filename = quote(os.path.basename(self.pdf_file_path))
            part.add_header(
                'Content-Disposition',
                f'attachment; filename*=UTF-8\'\'{safe_filename}'
            )
            msg.attach(part)
            
            # Gmail SMTP ayarları
            smtp_server = "smtp.gmail.com"
            smtp_port = 587
            
            # SSL context oluştur
            context = ssl.create_default_context()
            
            # E-posta gönder
            with smtplib.SMTP(smtp_server, smtp_port, timeout=30) as server:
                server.starttls(context=context)
                server.login(self.gmail_email, self.gmail_password)
                
                text = msg.as_string()
                server.sendmail(self.gmail_email, self.recipient_email, text)
            
            self.logger.info(f"E-posta başarıyla gönderildi: {self.recipient_email}")
            self.finished.emit(True, f"PDF raporu başarıyla gönderildi:\n{self.recipient_email}")
            
        except smtplib.SMTPAuthenticationError as e:
            error_msg = str(e)
            if "Username and Password not accepted" in error_msg or "535" in error_msg:
                message = (
                    "Gmail App Password Gerekli!\n\n"
                    "Gmail artık normal şifre ile giriş yapmaya izin vermiyor!\n\n"
                    "Çözüm:\n"
                    "1. Gmail hesabınızda 2-Step Verification'ı açın\n"
                    "2. Google Account > Security > App passwords\n"
                    "3. Yeni App Password oluşturun\n"
                    "4. Bu App Password'ü kodda kullanın\n\n"
                    "Detaylı bilgi için: myaccount.google.com/apppasswords"
                )
            else:
                message = f"Gmail kimlik doğrulama hatası: {error_msg}"
            self.logger.error(f"SMTP Authentication Error: {e}")
            self.finished.emit(False, message)
            
        except smtplib.SMTPRecipientsRefused as e:
            message = f"Alıcı e-posta adresi geçersiz: {self.recipient_email}"
            self.logger.error(f"SMTP Recipients Refused: {e}")
            self.finished.emit(False, message)
            
        except smtplib.SMTPServerDisconnected as e:
            message = "SMTP sunucusu bağlantısı kesildi. Lütfen internet bağlantınızı kontrol edin."
            self.logger.error(f"SMTP Server Disconnected: {e}")
            self.finished.emit(False, message)
            
        except smtplib.SMTPException as e:
            message = f"SMTP hatası: {str(e)}"
            self.logger.error(f"SMTP Exception: {e}")
            self.finished.emit(False, message)
            
        except OSError as e:
            message = f"Ağ bağlantı hatası: {str(e)}\n\nLütfen internet bağlantınızı kontrol edin."
            self.logger.error(f"OS Error: {e}")
            self.finished.emit(False, message)
            
        except FileNotFoundError:
            message = f"PDF dosyası bulunamadı: {self.pdf_file_path}"
            self.logger.error(f"PDF file not found: {self.pdf_file_path}")
            self.finished.emit(False, message)
            
        except Exception as e:
            message = (
                f"E-posta gönderilirken beklenmeyen bir hata oluştu:\n{str(e)}\n\n"
                "Kontrol edilecekler:\n"
                "• Gmail için App Password kullanıyor musunuz?\n"
                "• İnternet bağlantısı var mı?\n"
                "• E-posta adresleri doğru mu?\n"
                "• PDF dosyası erişilebilir mi?"
            )
            self.logger.error(f"Unexpected error sending email: {e}", exc_info=True)
            self.finished.emit(False, message)


class EmailPDFDialog(QDialog, StyleMixin):
    """PDF e-posta gönderme dialog penceresi - Design System entegrasyonu"""
    
    # Email validation regex (RFC 5322 uyumlu basitleştirilmiş)
    EMAIL_REGEX = re.compile(
        r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    )
    
    # Gmail dosya boyutu limiti (25MB)
    MAX_FILE_SIZE_MB = 25
    MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
    
    def __init__(self, pdf_file_path, parent=None):
        super().__init__(parent)
        self.pdf_file_path = pdf_file_path
        self.logger = logging.getLogger(__name__)
        
        # PDF dosya kontrolü
        if not pdf_file_path or not os.path.exists(pdf_file_path):
            QMessageBox.critical(
                parent or self,
                "Dosya Hatası",
                f"PDF dosyası bulunamadı:\n{pdf_file_path or 'None'}\n\n"
                "Lütfen PDF dosyasının varlığını kontrol edin.",
                QMessageBox.StandardButton.Ok
            )
            # Dialog'u kapat
            self.reject()
            return
        
        # Dosya boyutu kontrolü
        file_size = os.path.getsize(pdf_file_path)
        if file_size > self.MAX_FILE_SIZE_BYTES:
            QMessageBox.warning(
                parent or self,
                "Dosya Çok Büyük",
                f"PDF dosyası çok büyük ({file_size / (1024*1024):.1f} MB).\n\n"
                f"Gmail'in maksimum dosya boyutu: {self.MAX_FILE_SIZE_MB} MB\n\n"
                "Lütfen daha küçük bir dosya seçin veya dosyayı sıkıştırın.",
                QMessageBox.StandardButton.Ok
            )
            self.reject()
            return
        
        # Gmail bilgileri config.json'dan yükleniyor (güvenlik için)
        self.gmail_email, self.gmail_password = self._load_email_credentials()
        
        # Email thread
        self.email_thread = None
        
        self.setWindowTitle("PDF E-posta Gönder")
        self.setModal(True)
        
        # Apply design system theme
        self.apply_theme()
        
        # Setup responsive window
        self._setup_responsive_window()
        
        self.setup_ui()
    
    def setup_ui(self):
        """UI oluştur"""
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        
        # Başlık
        title_label = QLabel("PDF Raporu E-posta ile Gönder")
        title_label.setObjectName("emailTitle")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)
        
        # Açıklama metni
        info_label = QLabel(
            "Bu pencereden tedavi raporunuzu e-posta ile gönderebilirsiniz.\n"
            "Alıcı e-posta adresini girin ve mesajınızı özelleştirin."
        )
        info_label.setStyleSheet("color: #e0e0e0; font-style: italic; padding: 5px;")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        # Dosya bilgisi
        file_info_group = QGroupBox("Gönderilecek Dosya")
        file_info_layout = QVBoxLayout(file_info_group)
        
        file_name = os.path.basename(self.pdf_file_path)
        file_size = os.path.getsize(self.pdf_file_path) / 1024  # KB
        file_size_mb = file_size / 1024  # MB
        
        # Dosya bilgilerini daha detaylı göster
        file_info_text = f"<b>Dosya Adı:</b> {file_name}<br/>"
        if file_size_mb >= 1:
            file_info_text += f"<b>Boyut:</b> {file_size_mb:.2f} MB ({file_size:.0f} KB)"
        else:
            file_info_text += f"<b>Boyut:</b> {file_size:.1f} KB"
        
        file_info_label = QLabel(file_info_text)
        file_info_label.setWordWrap(True)
        file_info_layout.addWidget(file_info_label)
        
        layout.addWidget(file_info_group)
        
        # E-posta bilgileri
        email_group = QGroupBox("E-posta Bilgileri")
        email_layout = QGridLayout(email_group)
        email_layout.setVerticalSpacing(12)
        
        # Alıcı e-posta
        recipient_label = QLabel("<b>Alıcı E-posta:</b>")
        email_layout.addWidget(recipient_label, 0, 0, Qt.AlignmentFlag.AlignTop)
        
        recipient_container = QVBoxLayout()
        self.recipient_edit = QLineEdit()
        self.recipient_edit.setPlaceholderText("hasta@example.com (örnek: ahmet@gmail.com)")
        self.recipient_edit.setMinimumWidth(300)
        recipient_container.addWidget(self.recipient_edit)
        
        recipient_help = QLabel("<i>Raporun gönderileceği e-posta adresi</i>")
        recipient_help.setStyleSheet("color: #aaa; font-size: 8pt;")
        recipient_container.addWidget(recipient_help)
        email_layout.addLayout(recipient_container, 0, 1)
        
        # Konu
        subject_label = QLabel("<b>Konu:</b>")
        email_layout.addWidget(subject_label, 1, 0, Qt.AlignmentFlag.AlignTop)
        
        subject_container = QVBoxLayout()
        self.subject_edit = QLineEdit()
        self.subject_edit.setText(f"PEMF Tedavi Raporu - {datetime.now().strftime('%d.%m.%Y')}")
        self.subject_edit.setMinimumWidth(300)
        subject_container.addWidget(self.subject_edit)
        
        subject_help = QLabel("<i>E-posta konusu (isteğe bağlı düzenlenebilir)</i>")
        subject_help.setStyleSheet("color: #aaa; font-size: 8pt;")
        subject_container.addWidget(subject_help)
        email_layout.addLayout(subject_container, 1, 1)
        
        # Mesaj
        message_label = QLabel("<b>Mesaj:</b>")
        email_layout.addWidget(message_label, 2, 0, Qt.AlignmentFlag.AlignTop)
        
        message_container = QVBoxLayout()
        self.message_edit = QTextEdit()
        self.message_edit.setPlainText(
            "Sayın Hasta Sahibi,\n\n"
            "PEMF tedavi seans raporunuz ekte yer almaktadır.\n"
            "Raporu inceleyip gerekli takip işlemlerini yapabilirsiniz.\n\n"
            "Sorularınız için lütfen kliniğimizle iletişime geçiniz.\n\n"
            "Sağlıklı günler dileriz."
        )
        self.message_edit.setMinimumHeight(120)
        self.message_edit.setMaximumHeight(150)
        message_container.addWidget(self.message_edit)
        
        message_help = QLabel("<i>E-posta mesajı (isteğe bağlı düzenlenebilir)</i>")
        message_help.setStyleSheet("color: #aaa; font-size: 8pt;")
        message_container.addWidget(message_help)
        email_layout.addLayout(message_container, 2, 1)
        
        layout.addWidget(email_group)
        
        # Gmail bilgisi
        gmail_info_group = QGroupBox("Gönderen Bilgisi")
        gmail_info_layout = QVBoxLayout(gmail_info_group)
        
        gmail_info_label = QLabel(
            f"<b>Gönderen E-posta:</b> {self.gmail_email}<br/>"
            "<i>E-posta bu adres üzerinden gönderilecektir.</i>"
        )
        gmail_info_label.setStyleSheet("color: #e0e0e0;")
        gmail_info_label.setWordWrap(True)
        gmail_info_layout.addWidget(gmail_info_label)
        
        # Gmail App Password uyarısı
        gmail_warning = QLabel(
            "<b>Not:</b> Gmail güvenliği için App Password kullanılmaktadır. "
            "Normal Gmail şifresi ile gönderim yapılamaz."
        )
        gmail_warning.setStyleSheet(
            "color: #ffc107; font-size: 8pt; padding: 5px; "
            "background-color: rgba(255, 193, 7, 0.1); border-radius: 3px;"
        )
        gmail_warning.setWordWrap(True)
        gmail_info_layout.addWidget(gmail_warning)
        
        layout.addWidget(gmail_info_group)
        
        # Progress bar (başlangıçta gizli)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # Indeterminate progress
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        # Butonlar
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)
        button_layout.addStretch()
        
        self.cancel_btn = QPushButton("İptal")
        self.cancel_btn.setMinimumWidth(100)
        self.cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_btn)
        
        self.send_btn = QPushButton("E-posta Gönder")
        self.send_btn.setMinimumWidth(120)
        self.send_btn.setDefault(True)  # Enter tuşu ile gönder
        self.send_btn.clicked.connect(self.send_email)
        button_layout.addWidget(self.send_btn)
        
        layout.addLayout(button_layout)
        
        # Klavye kısayolu bilgisi
        shortcut_label = QLabel("<i>İpucu: Enter tuşuna basarak hızlıca gönderebilirsiniz</i>")
        shortcut_label.setStyleSheet("color: #888; font-size: 8pt;")
        shortcut_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(shortcut_label)
    
    def validate_email(self, email: str) -> bool:
        """Email adresini validate et"""
        if not email or not email.strip():
            return False
        email = email.strip()
        return bool(self.EMAIL_REGEX.match(email))
    
    def send_email(self):
        """E-posta gönder"""
        # Gerekli alanları kontrol et
        recipient_email = self.recipient_edit.text().strip()
        if not recipient_email:
            QMessageBox.warning(
                self,
                "Eksik Bilgi",
                "Lütfen alıcı e-posta adresini girin.\n\n"
                "Örnek: hasta@example.com",
                QMessageBox.StandardButton.Ok
            )
            self.recipient_edit.setFocus()
            return
        
        # E-posta adresinin geçerli olup olmadığını kontrol et
        if not self.validate_email(recipient_email):
            QMessageBox.warning(
                self,
                "Geçersiz E-posta",
                "Lütfen geçerli bir e-posta adresi girin.\n\n"
                "Geçerli format: kullanici@example.com\n"
                "Örnekler:\n"
                "• ahmet@gmail.com\n"
                "• hasta@klinik.com.tr\n"
                "• info@veteriner.net",
                QMessageBox.StandardButton.Ok
            )
            self.recipient_edit.setFocus()
            self.recipient_edit.selectAll()
            return
        
        # PDF dosyasının hala var olduğunu kontrol et
        if not os.path.exists(self.pdf_file_path):
            QMessageBox.critical(
                self,
                "Dosya Hatası",
                f"PDF dosyası bulunamadı:\n{self.pdf_file_path}\n\n"
                "Dosya silinmiş veya taşınmış olabilir.",
                QMessageBox.StandardButton.Ok
            )
            return
        
        # Dosya boyutunu tekrar kontrol et
        file_size = os.path.getsize(self.pdf_file_path)
        if file_size > self.MAX_FILE_SIZE_BYTES:
            QMessageBox.warning(
                self,
                "Dosya Çok Büyük",
                f"PDF dosyası çok büyük ({file_size / (1024*1024):.1f} MB).\n\n"
                f"Gmail'in maksimum dosya boyutu: {self.MAX_FILE_SIZE_MB} MB",
                QMessageBox.StandardButton.Ok
            )
            return
        
        # UI'ı disable et ve progress göster
        self.send_btn.setEnabled(False)
        self.cancel_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # Indeterminate
        
        # Email thread oluştur ve başlat
        subject = self.subject_edit.text().strip() or f"PEMF Seans Raporu - {datetime.now().strftime('%d.%m.%Y')}"
        body = self.message_edit.toPlainText()
        
        self.email_thread = EmailSendThread(
            self.gmail_email,
            self.gmail_password,
            recipient_email,
            subject,
            body,
            self.pdf_file_path
        )
        self.email_thread.finished.connect(self.on_email_finished)
        self.email_thread.start()
        
        self.logger.info(f"Email gönderimi başlatıldı: {recipient_email}")
    
    def on_email_finished(self, success: bool, message: str):
        """Email gönderme işlemi tamamlandığında çağrılır"""
        # UI'ı tekrar enable et
        self.send_btn.setEnabled(True)
        self.cancel_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        
        if success:
            QMessageBox.information(
                self,
                "E-posta Gönderildi",
                message,
                QMessageBox.StandardButton.Ok
            )
            self.accept()
        else:
            QMessageBox.critical(
                self,
                "E-posta Gönderme Hatası",
                message,
                QMessageBox.StandardButton.Ok
            )
        
        # Thread'i temizle
        if self.email_thread:
            self.email_thread.quit()
            self.email_thread.wait(1000)  # 1 saniye bekle
            self.email_thread = None
    
    def closeEvent(self, event):
        """Dialog kapatılırken thread'i graceful shutdown ile temizle"""
        if self.email_thread and self.email_thread.isRunning():
            reply = QMessageBox.question(
                self,
                "E-posta Gönderiliyor",
                "E-posta hala gönderiliyor. Kapatmak istediğinize emin misiniz?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                # Graceful shutdown - terminate() yerine flag kullan
                self.email_thread.stop_requested = True
                # Thread'in bitmesini bekle (max 5 saniye)
                if not self.email_thread.wait(5000):
                    self.logger.warning("Email thread graceful shutdown timeout, ignoring termination to prevent resource leak.")
            else:
                event.ignore()
                return
        
        super().closeEvent(event)
    
    def _load_email_credentials(self):
        """Email bilgilerini config.json dosyasından yükle"""
        try:
            # 1) En güvenli kaynak: Windows Credential Manager / keyring
            if KEYRING_AVAILABLE:
                kr_email = keyring.get_password("pemf_gui", "gmail_email")
                kr_password = keyring.get_password("pemf_gui", "gmail_app_password")
                if kr_email and kr_password:
                    self.logger.info("Email credentials loaded from keyring")
                    return kr_email, kr_password

            # 2) Ortam değişkeni fallback
            env_email = os.environ.get("PEMF_GMAIL_EMAIL")
            env_password = os.environ.get("PEMF_GMAIL_APP_PASSWORD")
            if env_email and env_password:
                self.logger.info("Email credentials loaded from environment variables")
                return env_email, env_password

            # Config dosyasının konumunu belirle
            current_dir = os.path.dirname(os.path.abspath(__file__))
            parent_dir = os.path.dirname(current_dir)
            config_path = os.path.join(parent_dir, 'config.json')
            
            # Alternatif olarak mevcut dizinde de ara
            if not os.path.exists(config_path):
                config_path = os.path.join(current_dir, 'config.json')
            
            if not os.path.exists(config_path):
                # Config dosyası bulunamadı, hata göster
                QMessageBox.critical(
                    self.parent() or self,
                    "Yapılandırma Hatası",
                    f"config.json dosyası bulunamadı:\n{config_path}\n\n"
                    "Lütfen config.json dosyasını oluşturun ve email bilgilerini ekleyin.\n\n"
                    "Örnek yapı:\n"
                    '{\n'
                    '  "email": {\n'
                    '    "gmail_email": "your-email@gmail.com",\n'
                    '    "gmail_password": "your-app-password"\n'
                    '  }\n'
                    '}',
                    QMessageBox.StandardButton.Ok
                )
                raise FileNotFoundError(f"config.json not found: {config_path}")
            
            # Config dosyasını oku
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            # Email bilgilerini al
            email_config = config.get('email', {})
            gmail_email = email_config.get('gmail_email')
            gmail_password = email_config.get('gmail_password')
            
            if not gmail_email or not gmail_password:
                raise ValueError(
                    "config.json dosyasında email bilgileri eksik. "
                    "'email.gmail_email' ve 'email.gmail_password' alanlarını kontrol edin."
                )

            self.logger.warning(
                "Email credentials loaded from plain config.json. "
                "For better security, prefer keyring or PEMF_GMAIL_* environment variables."
            )
            return gmail_email, gmail_password
            
        except FileNotFoundError as e:
            self.logger.error(f"Config file not found: {e}")
            raise
        except json.JSONDecodeError as e:
            error_msg = f"config.json dosyası geçersiz JSON formatında:\n{str(e)}"
            self.logger.error(error_msg)
            QMessageBox.critical(
                self.parent() or self,
                "Yapılandırma Hatası",
                error_msg,
                QMessageBox.StandardButton.Ok
            )
            raise ValueError(error_msg)
        except Exception as e:
            error_msg = f"Email bilgileri yüklenirken hata oluştu: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            QMessageBox.critical(
                self.parent() or self,
                "Yapılandırma Hatası",
                error_msg,
                QMessageBox.StandardButton.Ok
            )
            raise
    
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
    
    def apply_styles(self):
        """Dialog stillerini uygula"""
        self.setStyleSheet("""
            QDialog {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, 
                    stop:0 #2d185a, stop:1 #6c2b8f);
                color: #ffffff;
            }
            
            #emailTitle {
                font-size: 14pt;
                font-weight: bold;
                color: white;
                margin: 10px 0;
                padding: 10px;
                background: rgba(142, 68, 173, 0.8);
                border-radius: 8px;
            }
            
            QGroupBox {
                font-weight: bold;
                border: 2px solid rgba(255, 255, 255, 0.3);
                border-radius: 8px;
                margin: 10px 0;
                padding-top: 10px;
                background: rgba(255, 255, 255, 0.1);
            }
            
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
                color: #ffffff;
                background: rgba(142, 68, 173, 0.8);
                border-radius: 4px;
            }
            
            QLineEdit, QTextEdit {
                background: rgba(255, 255, 255, 0.1);
                border: 2px solid rgba(255, 255, 255, 0.3);
                border-radius: 6px;
                padding: 8px;
                color: white;
                font-size: 9pt;
            }
            
            QLineEdit:focus, QTextEdit:focus {
                border-color: #8e44ad;
                background: rgba(255, 255, 255, 0.2);
            }
            
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, 
                    stop:0 #8e44ad, stop:1 #9b59b6);
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 6px;
                font-weight: bold;
                font-size: 9pt;
                min-width: 80px;
            }
            
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, 
                    stop:0 #9b59b6, stop:1 #a569bd);
            }
            
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, 
                    stop:0 #7d3c98, stop:1 #8e44ad);
            }
            
            QLabel {
                color: white;
            }
        """)
