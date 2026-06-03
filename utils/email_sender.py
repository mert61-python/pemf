"""
E-posta Gönderme Modülü
PDF raporlarını e-posta ile gönderme işlevselliği
"""

import smtplib
import ssl
import os
import logging
import sqlite3
import threading
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime, timedelta
from pathlib import Path
from typing import List

try:
    from .path_utils import get_app_data_directory
except ImportError:
    from utils.path_utils import get_app_data_directory

class EmailSender:
    """E-posta gönderme sınıfı"""

    COOLDOWN_SECONDS = 60
    DAILY_LIMIT = 100
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # Varsayılan SMTP ayarları (Gmail)
        self.smtp_server = "smtp.gmail.com"
        self.smtp_port = 587
        self._rate_lock = threading.Lock()
        self._rate_db_path = Path(get_app_data_directory()) / "email_rate_limit.db"
        self._init_rate_limit_db()

    def _init_rate_limit_db(self) -> None:
        with sqlite3.connect(self._rate_db_path, timeout=5.0) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS email_rate_limits (
                    date_key TEXT PRIMARY KEY,
                    sent_count INTEGER NOT NULL DEFAULT 0,
                    last_sent_at TEXT
                )
                """
            )
            conn.commit()

    def _check_and_reserve_send_slot(self) -> bool:
        now = datetime.now()
        date_key = now.strftime("%Y-%m-%d")

        with self._rate_lock:
            with sqlite3.connect(self._rate_db_path, timeout=5.0) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                cursor.execute(
                    "SELECT sent_count, last_sent_at FROM email_rate_limits WHERE date_key = ?",
                    (date_key,),
                )
                row = cursor.fetchone()

                sent_count = int(row["sent_count"]) if row else 0
                if sent_count >= self.DAILY_LIMIT:
                    self.logger.warning("E-posta günlük limitine ulaşıldı: %d", self.DAILY_LIMIT)
                    return False

                if row and row["last_sent_at"]:
                    try:
                        last_sent_at = datetime.fromisoformat(row["last_sent_at"])
                        remaining = timedelta(seconds=self.COOLDOWN_SECONDS) - (now - last_sent_at)
                        if remaining.total_seconds() > 0:
                            self.logger.warning(
                                "E-posta cooldown aktif. Kalan süre: %.1f saniye",
                                remaining.total_seconds(),
                            )
                            return False
                    except ValueError:
                        pass

                if row:
                    cursor.execute(
                        """
                        UPDATE email_rate_limits
                        SET sent_count = sent_count + 1, last_sent_at = ?
                        WHERE date_key = ?
                        """,
                        (now.isoformat(), date_key),
                    )
                else:
                    cursor.execute(
                        """
                        INSERT INTO email_rate_limits (date_key, sent_count, last_sent_at)
                        VALUES (?, ?, ?)
                        """,
                        (date_key, 1, now.isoformat()),
                    )

                conn.commit()
                return True
        
    def send_report_email(self, 
                         sender_email: str,
                         sender_password: str,
                         recipient_emails: List[str],
                         pdf_file_path: str,
                         patient_name: str = "",
                         clinic_name: str = "Veteriner Kliniği",
                         additional_message: str = "") -> bool:
        """
        PDF raporunu e-posta ile gönder
        
        Args:
            sender_email: Gönderen e-posta adresi
            sender_password: Gönderen e-posta şifresi (App Password önerilir)
            recipient_emails: Alıcı e-posta adresleri listesi
            pdf_file_path: Gönderilecek PDF dosya yolu
            patient_name: Hasta adı
            clinic_name: Klinik adı
            additional_message: Ek mesaj
            
        Returns:
            bool: Gönderim başarılı ise True
        """
        try:
            if not self._check_and_reserve_send_slot():
                return False

            # PDF dosyasının varlığını kontrol et
            if not os.path.exists(pdf_file_path):
                self.logger.error(f"PDF dosyası bulunamadı: {pdf_file_path}")
                return False
            
            # E-posta mesajını oluştur
            msg = MIMEMultipart()
            msg['From'] = sender_email
            msg['To'] = ", ".join(recipient_emails)
            msg['Subject'] = f"PEMF Tedavi Raporu - {patient_name}" if patient_name else "PEMF Tedavi Raporu"
            
            # E-posta içeriği
            body = self._create_email_body(patient_name, clinic_name, additional_message)
            msg.attach(MIMEText(body, 'html', 'utf-8'))
            
            # PDF dosyasını ekle
            with open(pdf_file_path, "rb") as attachment:
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(attachment.read())
            
            encoders.encode_base64(part)
            
            # Dosya adını al
            filename = os.path.basename(pdf_file_path)
            part.add_header(
                'Content-Disposition',
                f'attachment; filename= {filename}',
            )
            
            msg.attach(part)
            
            # E-postayı gönder
            context = ssl.create_default_context()
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls(context=context)
                server.login(sender_email, sender_password)
                text = msg.as_string()
                server.sendmail(sender_email, recipient_emails, text)
            
            self.logger.info(f"E-posta başarıyla gönderildi: {recipient_emails}")
            return True
            
        except Exception as e:
            self.logger.error(f"E-posta gönderme hatası: {e}")
            return False
    
    def _create_email_body(self, patient_name: str, clinic_name: str, additional_message: str) -> str:
        """E-posta içeriğini oluştur"""
        current_date = datetime.now().strftime("%d.%m.%Y %H:%M")
        
        body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    max-width: 600px;
                    margin: 0 auto;
                    padding: 20px;
                }}
                .header {{
                    background-color: #2c3e50;
                    color: white;
                    padding: 20px;
                    text-align: center;
                    border-radius: 8px 8px 0 0;
                }}
                .content {{
                    background-color: #f8f9fa;
                    padding: 20px;
                    border: 1px solid #dee2e6;
                }}
                .footer {{
                    background-color: #e9ecef;
                    padding: 15px;
                    text-align: center;
                    border-radius: 0 0 8px 8px;
                    font-size: 9pt;
                    color: #6c757d;
                }}
                .patient-info {{
                    background-color: white;
                    padding: 15px;
                    margin: 15px 0;
                    border-left: 4px solid #007bff;
                    border-radius: 4px;
                }}
                .highlight {{
                    color: #007bff;
                    font-weight: bold;
                }}
            </style>
        </head>
        <body>
            <div class="header">
                <h2>🐾 PEMF Tedavi Raporu</h2>
                <p>{clinic_name}</p>
            </div>
            
            <div class="content">
                <p>Sayın Meslektaşım,</p>
                
                <p>Ekte <span class="highlight">PEMF (Pulsed Electromagnetic Field)</span> tedavi raporunu bulabilirsiniz.</p>
                
                {f'<div class="patient-info"><strong>Hasta:</strong> {patient_name}</div>' if patient_name else ''}
                
                <p><strong>Rapor Tarihi:</strong> {current_date}</p>
                
                <p>Bu rapor aşağıdaki bilgileri içermektedir:</p>
                <ul>
                    <li>Tedavi seansları detayları</li>
                    <li>Kullanılan parametreler (frekans, yoğunluk, süre)</li>
                    <li>Tedavi istatistikleri</li>
                    <li>Gözlem notları</li>
                </ul>
                
                {f'<div style="margin: 20px 0; padding: 15px; background-color: #fff3cd; border: 1px solid #ffeaa7; border-radius: 4px;"><strong>Ek Notlar:</strong><br>{additional_message}</div>' if additional_message else ''}
                
                <p>Herhangi bir sorunuz olması durumunda lütfen bizimle iletişime geçmekten çekinmeyin.</p>
                
                <p>Saygılarımla,<br>
                <strong>{clinic_name}</strong></p>
            </div>
            
            <div class="footer">
                <p>Bu e-posta PEMF Tedavi Sistemi tarafından otomatik olarak oluşturulmuştur.</p>
                <p>Gönderim Zamanı: {current_date}</p>
            </div>
        </body>
        </html>
        """
        
        return body
    
    def test_email_connection(self, email: str, password: str) -> bool:
        """E-posta bağlantısını test et"""
        try:
            context = ssl.create_default_context()
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls(context=context)
                server.login(email, password)
            
            self.logger.info("E-posta bağlantısı başarılı")
            return True
            
        except Exception as e:
            self.logger.error(f"E-posta bağlantı hatası: {e}")
            return False


# Singleton instance
_email_sender = None

def get_email_sender() -> EmailSender:
    """E-posta gönderici singleton instance'ını getir"""
    global _email_sender
    if _email_sender is None:
        _email_sender = EmailSender()
    return _email_sender


if __name__ == "__main__":
    # Test için
    sender = get_email_sender()
    
    # Test e-posta bağlantısı
    test_email = "test@gmail.com"
    test_password = "test_password"
    
    if sender.test_email_connection(test_email, test_password):
        print("E-posta bağlantısı başarılı!")
    else:
        print("E-posta bağlantısı başarısız!")

