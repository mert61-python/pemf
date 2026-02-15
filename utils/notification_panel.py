# -*- coding: utf-8 -*-
"""
Bildirim Paneli Modülü.

Bu modül, uygulama içinde kullanıcıya bildirimler göstermek için
kullanılan bildirim paneli bileşenini sağlar.
@author: merta
"""
import time 
from PyQt6.QtWidgets import (
    QLabel,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QScrollArea,
    QSizeGrip
)
from PyQt6.QtCore import Qt, QTimer

# Design System
import sys
import os
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)
from styles import StyleMixin

def make_resizable(widget):
    """Widget'ı yeniden boyutlandırılabilir yapar.
    
    Args:
        widget: Yeniden boyutlandırılabilir yapılacak widget.
    """
    size_grip = QSizeGrip(widget)
    widget.layout().addWidget(size_grip, 0, Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight)

class NotificationPanel(QWidget, StyleMixin):
    """Bildirim paneli bileşeni - Design System entegrasyonu.
    
    Bu sınıf, uygulama içinde kullanıcıya bildirimler göstermek için
    kullanılan bir panel sağlar. Bildirimler, zaman damgalı olarak
    gösterilir ve farklı bildirim türleri desteklenir.
    """
    def __init__(self, parent=None):
        """Bildirim panelini başlatır.
        
        Args:
            parent: Üst widget, varsayılan olarak None.
        """
        super().__init__(parent)
        self.notifications = []
        self.parent_window = parent  # Ana pencere referansı
        
        # Apply design system theme
        self.apply_theme()
        
        self.init_ui()

    def init_ui(self):
        """Kullanıcı arayüzünü başlatır.
        
        Panel düzenini ve kaydırma alanını oluşturur.
        """
        self.layout = QVBoxLayout()
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(8)
        self.setLayout(self.layout)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("""
            QScrollArea {
                border: none;
                background: transparent;
            }
            QScrollBar:vertical {
                border: none;
                background: #2d185a;
                width: 8px;
                margin: 0px 0px 0px 0px;
            }
            QScrollBar::handle:vertical {
                background: #6c2b8f;
                border-radius: 4px;
                min-height: 20px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                background: none;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
            }
        """)

        self.notification_content_widget = QWidget()
        self.notification_content_layout = QVBoxLayout(self.notification_content_widget)
        self.notification_content_layout.setContentsMargins(0, 0, 0, 0)
        self.notification_content_layout.setSpacing(8)
        self.notification_content_layout.addStretch(1)  # Notifications will push from bottom

        self.scroll_area.setWidget(self.notification_content_widget)
        self.layout.addWidget(self.scroll_area)

    def add_notification(self, message, type="info"):
        """Yeni bir bildirim ekler.
        
        Args:
            message: Bildirim mesajı.
            type: Bildirim türü ("info", "warning", "error" vb.), varsayılan olarak "info".
        """
        # Sessiz mod kontrolü
        if self.parent_window and hasattr(self.parent_window, 'silent_mode') and self.parent_window.silent_mode:
            # Sessiz modda sadece kritik hataları göster
            if type not in ["error", "critical"]:
                return
        
        # Thread-safe olarak main thread'de çalıştır
        QTimer.singleShot(0, lambda: self._add_notification_internal(message, type))
    
    def _add_notification_internal(self, message, type="info"):
        """Internal notification ekleme metodu - main thread'de çalışır"""
        timestamp = time.strftime("%H:%M:%S")
        self.notifications.append({'message': message, 'timestamp': timestamp, 'type': type})
        self.update_display()

    def update_display(self):
        """Bildirim görüntüsünü günceller.
        
        Mevcut bildirimleri temizler ve en son bildirimleri gösterir.
        """
        # Mevcut bildirimleri aşağıdan yukarıya doğru temizle
        for i in reversed(range(self.notification_content_layout.count() - 1)):  # -1 to preserve the stretch
            widget_to_remove = self.notification_content_layout.itemAt(i).widget()
            if widget_to_remove:
                self.notification_content_layout.removeWidget(widget_to_remove)
                widget_to_remove.setParent(None)

        # Add new notifications from the most recent (end of list) to the top
        for notification in reversed(self.notifications):
            notification_widget = self.create_notification_widget(notification)
            self.notification_content_layout.insertWidget(0, notification_widget)  # Insert at top

        # Ensure scroll bar is at the bottom to show latest notifications
        self.scroll_area.verticalScrollBar().setValue(self.scroll_area.verticalScrollBar().maximum())

    def create_notification_widget(self, notification):
        """Bildirim widget'ını oluşturur.
        
        Args:
            notification: Bildirim verisi içeren sözlük.
            
        Returns:
            QWidget: Oluşturulan bildirim widget'ı.
        """
        widget = QWidget()
        widget.setStyleSheet("""
            background: #2d185a;
            border-radius: 8px;
            padding: 8px;
        """)
        h_layout = QHBoxLayout(widget)
        h_layout.setContentsMargins(5, 2, 5, 2)
        h_layout.setSpacing(10)

        # Ikon yerine emoji kullan
        icon_label = QLabel()
        if notification['type'] == 'info':
            icon_label.setText("ℹ️")
        elif notification['type'] == 'warning':
            icon_label.setText("⚠️")
        elif notification['type'] == 'error':
            icon_label.setText("❌")
        elif notification['type'] == 'success':
            icon_label.setText("✅")
        else:
            icon_label.setText("📢")
        
        icon_label.setStyleSheet("font-size: 16px;")
        h_layout.addWidget(icon_label)

        message_label = QLabel(
            f"<span style='color:#fff; font-size: 13px;'>{notification['message']}</span>")
        message_label.setWordWrap(True)
        h_layout.addWidget(message_label)

        h_layout.addStretch(1)

        timestamp_label = QLabel(
            f"<span style='color:#aaa; font-size: 11px;'>{notification['timestamp']}</span>")
        h_layout.addWidget(timestamp_label)

        return widget
