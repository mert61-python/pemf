# -*- coding: utf-8 -*-
"""
Açılış Ekranı Modülü.

Bu modül, uygulama başlatılırken gösterilen modern ve animasyonlu
açılış ekranını sağlar. Yükleme ilerlemesini gösterir ve kullanıcıya
başlatma sürecinde geri bildirim verir.
@author: merta
"""

import sys
import math
import time
import logging
from PyQt6.QtWidgets import QApplication, QSplashScreen, QWidget
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QRectF, QPointF, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QPixmap, QPainter, QFont, QColor, QLinearGradient, QPen, QBrush, QPainterPath

def draw_rounded_gradient_background(painter, width, height, animation_frame=0):
    """Yuvarlatılmış köşeli ve zengin gradient arka plan çizer."""
    # Ana gradient arka plan
    main_gradient = QLinearGradient(0, 0, 0, height)
    main_gradient.setColorAt(0, QColor(15, 23, 42))  # Koyu mavi
    main_gradient.setColorAt(0.3, QColor(30, 41, 59))  # Orta mavi
    main_gradient.setColorAt(0.7, QColor(51, 65, 85))  # Açık mavi-gri
    main_gradient.setColorAt(1, QColor(30, 41, 59))  # Tekrar orta
    
    painter.setBrush(QBrush(main_gradient))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(0, 0, width, height, 25, 25)
    
    # Animasyonlu parıltı efektleri
    glow_alpha = int(30 + 20 * math.sin(animation_frame / 20))
    glow_gradient = QLinearGradient(width * 0.3, 0, width * 0.7, height)
    glow_gradient.setColorAt(0, QColor(59, 130, 246, 0))
    glow_gradient.setColorAt(0.5, QColor(59, 130, 246, glow_alpha))
    glow_gradient.setColorAt(1, QColor(59, 130, 246, 0))
    
    painter.setBrush(QBrush(glow_gradient))
    painter.drawRoundedRect(0, 0, width, height, 25, 25)
    
    # Üst kısımda hafif ışık efekti
    top_glow = QLinearGradient(width // 2, 0, width // 2, int(height * 0.3))
    top_glow.setColorAt(0, QColor(99, 102, 241, 40))
    top_glow.setColorAt(1, QColor(99, 102, 241, 0))
    painter.setBrush(QBrush(top_glow))
    painter.drawRoundedRect(0, 0, width, int(height * 0.3), 25, 25)

class ModernSplashScreen(QSplashScreen):
    """Modern ve şık PEMF Medical System açılış ekranı.
    
    Bu sınıf, uygulama başlatılırken gösterilen animasyonlu açılış ekranını
    sağlar. İlerleme çubuğu, yükleme metni ve animasyonlu elementler içerir.
    
    Attributes:
        progress_updated: İlerleme değeri güncellendiğinde tetiklenen sinyal.
    """
    
    progress_updated = pyqtSignal(int)
    
    def __init__(self, title="PEMF System", version="1"):
        """ModernSplashScreen sınıfını başlatır.
        
        Açılış ekranının boyutlarını, arka planını ve animasyon değişkenlerini ayarlar.
        
        Args:
            title: Splash screen başlığı (varsayılan: "PEMF System")
            version: Yazılım sürümü (varsayılan: "1")
        """
        self.logger = logging.getLogger(__name__)
        self.width = 600
        self.height = 400
        self.title = title
        self.version = version
        
        pixmap = QPixmap(self.width, self.height)
        pixmap.fill(Qt.GlobalColor.transparent)
        
        super().__init__(pixmap)
        self._render_pixmap = QPixmap(self.width, self.height)
        self._render_pixmap.fill(Qt.GlobalColor.transparent)
        
        self.setWindowFlags(
            Qt.WindowType.SplashScreen | 
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        self.progress_value = 0
        self.loading_text = "Sistem başlatılıyor..."
        self.animation_frame = 0
        
        self.setup_animation_timer()
        self.update_splash()
    
    def closeEvent(self, event):
        """Pencere kapatılırken animation timer'ı durdur"""
        try:
            if hasattr(self, 'animation_timer') and self.animation_timer.isActive():
                self.animation_timer.stop()
                self.logger.debug("Animation timer durduruldu")
        except Exception as e:
            self.logger.warning(f"Animation timer durdurulurken hata: {e}")
        event.accept()

    def setup_animation_timer(self):
        """Animasyon için zamanlayıcıyı ayarlar."""
        self.animation_timer = QTimer(self)
        self.animation_timer.timeout.connect(self.animate_elements)
        self.animation_timer.start(50)

    def set_progress(self, value, text):
        """İlerleme çubuğunu ve yükleme metnini günceller."""
        self.progress_value = max(0, min(100, value))
        self.loading_text = text
        self.update_splash()
        self.progress_updated.emit(self.progress_value)
        QApplication.processEvents()

    def animate_elements(self):
        """Animasyon frame'ini güncelle"""
        self.animation_frame += 1
        self.update_splash()
    
    def update_splash(self):
        """Splash screen'i yeniden çiz"""
        self._render_pixmap.fill(Qt.GlobalColor.transparent)
        
        painter = QPainter(self._render_pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        
        draw_rounded_gradient_background(painter, self.width, self.height, self.animation_frame)
        self.draw_decorative_elements(painter)
        self.draw_logo(painter)
        self.draw_title(painter)
        self.draw_progress_bar(painter)
        self.draw_loading_text(painter)
        self.draw_animated_elements(painter)
        self.draw_bottom_info(painter)
        
        painter.end()
        self.setPixmap(self._render_pixmap)
    
    def showEvent(self, event):
        """Pencere gösterildiğinde fade-in animasyonunu başlatır."""
        super().showEvent(event)
        try:
            self.animation = QPropertyAnimation(self, b"windowOpacity")
            self.animation.setDuration(1000)
            self.animation.setStartValue(0.0)
            self.animation.setEndValue(1.0)
            self.animation.setEasingCurve(QEasingCurve.Type.InOutQuad)
            self.animation.finished.connect(self.animation.deleteLater)
            self.animation.start()
        except Exception as e:
            self.logger.warning(f"Fade-in animasyonu başlatılırken hata: {e}")

    def draw_logo(self, painter):
        """Zengin ve profesyonel bir logo çizer - Kalp şekli PEMF simgesi."""
        painter.save()
        center_x, center_y = self.width // 2, 110
        
        # Dış glow efekti (animasyonlu)
        glow_alpha = int(80 + 40 * math.sin(self.animation_frame / 15))
        glow_pen = QPen(QColor(59, 130, 246, glow_alpha), 8)
        glow_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(glow_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        
        # Ana kalp şekli
        heart_path = QPainterPath()
        size = 50
        heart_x, heart_y = center_x, center_y
        
        # Kalp şekli çizimi
        heart_path.moveTo(heart_x, heart_y + size * 0.2)
        # Sol üst eğri
        heart_path.cubicTo(heart_x - size * 0.5, heart_y - size * 0.3,
                          heart_x - size * 0.7, heart_y - size * 0.7,
                          heart_x, heart_y - size * 0.5)
        # Sağ üst eğri
        heart_path.cubicTo(heart_x + size * 0.7, heart_y - size * 0.7,
                          heart_x + size * 0.5, heart_y - size * 0.3,
                          heart_x, heart_y + size * 0.2)
        # Alt V şekli
        heart_path.cubicTo(heart_x - size * 0.3, heart_y + size * 0.1,
                          heart_x - size * 0.5, heart_y + size * 0.4,
                          heart_x, heart_y + size * 0.6)
        heart_path.cubicTo(heart_x + size * 0.5, heart_y + size * 0.4,
                          heart_x + size * 0.3, heart_y + size * 0.1,
                          heart_x, heart_y + size * 0.2)
        
        # Glow efekti
        painter.drawPath(heart_path)
        
        # Ana kalp dolgusu - zengin gradient
        heart_gradient = QLinearGradient(heart_x - size, heart_y - size, heart_x + size, heart_y + size)
        heart_gradient.setColorAt(0, QColor(239, 68, 68))  # Kırmızı
        heart_gradient.setColorAt(0.3, QColor(236, 72, 153))  # Pembe
        heart_gradient.setColorAt(0.6, QColor(99, 102, 241))  # Mor-mavi
        heart_gradient.setColorAt(1, QColor(59, 130, 246))  # Mavi

        painter.setBrush(QBrush(heart_gradient))
        painter.setPen(QPen(QColor(255, 255, 255, 180), 2))
        painter.drawPath(heart_path)
        
        # İç parıltı efekti
        inner_glow = QLinearGradient(heart_x - size * 0.3, heart_y - size * 0.5, 
                                    heart_x + size * 0.3, heart_y + size * 0.3)
        inner_glow.setColorAt(0, QColor(255, 255, 255, 100))
        inner_glow.setColorAt(1, QColor(255, 255, 255, 0))
        
        inner_path = QPainterPath()
        inner_path.addEllipse(heart_x - size * 0.3, heart_y - size * 0.3, size * 0.6, size * 0.6)
        painter.setBrush(QBrush(inner_glow))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPath(inner_path)
        
        # Elektromanyetik dalga simgesi (kalbin etrafında)
        wave_radius = 60 + 5 * math.sin(self.animation_frame / 10)
        for i in range(3):
            wave_alpha = int(100 - i * 30)
            wave_pen = QPen(QColor(59, 130, 246, wave_alpha), 2)
            painter.setPen(wave_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QPointF(heart_x, heart_y), 
                              wave_radius + i * 8, wave_radius + i * 8)
        
        painter.restore()

    def draw_title(self, painter):
        """Zengin başlık ve versiyon metnini çizer."""
        # Başlık için text shadow efekti
        shadow_offset = 2
        title_font = QFont("Arial", 36, QFont.Weight.Bold)
        painter.setFont(title_font)
        
        # Shadow
        painter.setPen(QColor(0, 0, 0, 100))
        painter.drawText(QRectF(shadow_offset, 152 + shadow_offset, self.width, 50), 
                        Qt.AlignmentFlag.AlignCenter, self.title)
        
        # Ana başlık - gradient text efekti
        title_rect = QRectF(0, 150, self.width, 50)
        text_gradient = QLinearGradient(0, 150, 0, 200)
        text_gradient.setColorAt(0, QColor(255, 255, 255))
        text_gradient.setColorAt(0.5, QColor(200, 220, 255))
        text_gradient.setColorAt(1, QColor(150, 180, 255))
        
        painter.setPen(QPen(QBrush(text_gradient), 1))
        painter.drawText(title_rect, Qt.AlignmentFlag.AlignCenter, self.title)
        
        # Alt başlık (tagline)
        tagline_font = QFont("Arial", 11, QFont.Weight.Normal)
        painter.setFont(tagline_font)
        painter.setPen(QColor(150, 170, 200, 200))
        painter.drawText(QRectF(0, 195, self.width, 25), Qt.AlignmentFlag.AlignCenter, 
                        "Veteriner PEMF Tedavi Sistemi")
        
        # Versiyon badge
        version_font = QFont("Arial", 9, QFont.Weight.Medium)
        painter.setFont(version_font)
        version_text = f"v{self.version}"
        version_rect = QRectF(self.width - 110, self.height - 25, 100, 20)
        
        # Badge arka planı
        badge_gradient = QLinearGradient(version_rect.x(), version_rect.y(),
                                        version_rect.x(), version_rect.y() + version_rect.height())
        badge_gradient.setColorAt(0, QColor(59, 130, 246, 150))
        badge_gradient.setColorAt(1, QColor(37, 99, 235, 150))
        painter.setBrush(QBrush(badge_gradient))
        painter.setPen(QPen(QColor(99, 102, 241, 200), 1))
        painter.drawRoundedRect(version_rect, 8, 8)
        
        # Versiyon metni
        painter.setPen(QColor(255, 255, 255, 220))
        painter.drawText(version_rect, Qt.AlignmentFlag.AlignCenter, version_text)

    def draw_progress_bar(self, painter):
        """Zengin ve modern ilerleme çubuğunu çizer."""
        progress_y = self.height - 130
        progress_width = self.width - 120
        progress_height = 14
        progress_x = 60
        
        # Arka plan (track)
        track_gradient = QLinearGradient(progress_x, progress_y, progress_x, progress_y + progress_height)
        track_gradient.setColorAt(0, QColor(30, 41, 59))
        track_gradient.setColorAt(1, QColor(15, 23, 42))
        
        painter.setPen(QPen(QColor(59, 130, 246, 50), 1))
        painter.setBrush(QBrush(track_gradient))
        painter.drawRoundedRect(progress_x, progress_y, progress_width, progress_height, 7, 7)
        
        # İlerleme çubuğu (fill)
        if self.progress_value > 0:
            fill_width = int((progress_width * self.progress_value) / 100)
            
            # Animasyonlu parıltı efekti
            shimmer_offset = int(20 * math.sin(self.animation_frame / 8))
            
            progress_gradient = QLinearGradient(progress_x + shimmer_offset, progress_y, 
                                              progress_x + fill_width + shimmer_offset, progress_y + progress_height)
            progress_gradient.setColorAt(0, QColor(99, 102, 241))
            progress_gradient.setColorAt(0.3, QColor(59, 130, 246))
            progress_gradient.setColorAt(0.6, QColor(37, 99, 235))
            progress_gradient.setColorAt(0.8, QColor(59, 130, 246))
            progress_gradient.setColorAt(1, QColor(99, 102, 241))
            
            # Glow efekti
            glow_pen = QPen(QColor(59, 130, 246, 100), 3)
            painter.setPen(glow_pen)
            painter.setBrush(QBrush(progress_gradient))
            painter.drawRoundedRect(progress_x, progress_y, fill_width, progress_height, 7, 7)
        
            # Üst highlight
            highlight_height = int(progress_height * 0.5)
            highlight_gradient = QLinearGradient(progress_x, progress_y, 
                                                progress_x, progress_y + highlight_height)
            highlight_gradient.setColorAt(0, QColor(255, 255, 255, 80))
            highlight_gradient.setColorAt(1, QColor(255, 255, 255, 0))
            painter.setBrush(QBrush(highlight_gradient))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(progress_x, progress_y, fill_width, highlight_height, 7, 7)
        
        # Yüzde metni - zengin stil
        progress_font = QFont("Arial", 13, QFont.Weight.Bold)
        painter.setFont(progress_font)
        
        # Text shadow
        painter.setPen(QColor(0, 0, 0, 150))
        painter.drawText(QRectF(0, progress_y + 18, self.width, 22), 
                        Qt.AlignmentFlag.AlignCenter, f"{self.progress_value}%")
        
        # Ana metin
        text_gradient = QLinearGradient(0, progress_y + 18, 0, progress_y + 40)
        text_gradient.setColorAt(0, QColor(255, 255, 255))
        text_gradient.setColorAt(1, QColor(200, 220, 255))
        painter.setPen(QPen(QBrush(text_gradient), 1))
        painter.drawText(QRectF(0, progress_y + 18, self.width, 22), 
                        Qt.AlignmentFlag.AlignCenter, f"{self.progress_value}%")

    def draw_loading_text(self, painter):
        """Zengin yükleme durumu metnini çizer."""
        loading_font = QFont("Arial", 13, QFont.Weight.Medium)
        painter.setFont(loading_font)
        
        # Text shadow
        painter.setPen(QColor(0, 0, 0, 100))
        painter.drawText(QRectF(0, self.height - 75, self.width, 30), 
                        Qt.AlignmentFlag.AlignCenter, self.loading_text)
        
        # Ana metin - gradient
        text_gradient = QLinearGradient(0, self.height - 75, 0, self.height - 45)
        text_gradient.setColorAt(0, QColor(200, 220, 255))
        text_gradient.setColorAt(1, QColor(150, 180, 255))
        painter.setPen(QPen(QBrush(text_gradient), 1))
        painter.drawText(QRectF(0, self.height - 75, self.width, 30), 
                        Qt.AlignmentFlag.AlignCenter, self.loading_text)

    def draw_animated_elements(self, painter):
        """Zengin animasyonlu elementler çizer."""
        center = QPointF(self.width / 2, self.height / 2 - 10)
        
        # Dönen parçacıklar (3 adet, daha büyük ve parlak)
        for i in range(3):
            angle = (self.animation_frame * 4 + i * 120) % 360
            radius = 55 + 8 * math.sin((self.animation_frame + i * 40) / 15)
            alpha = int(180 + 75 * math.sin((angle + self.animation_frame) / 10))
            
            x = center.x() + radius * math.cos(math.radians(angle))
            y = center.y() + radius * math.sin(math.radians(angle))
            
            # Parçacık glow efekti
            glow_gradient = QLinearGradient(x - 8, y - 8, x + 8, y + 8)
            glow_gradient.setColorAt(0, QColor(59, 130, 246, alpha))
            glow_gradient.setColorAt(0.5, QColor(99, 102, 241, alpha))
            glow_gradient.setColorAt(1, QColor(59, 130, 246, alpha // 2))
            
            painter.setBrush(QBrush(glow_gradient))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QPointF(x, y), 6, 6)
            
            # İç parlak nokta
            painter.setBrush(QBrush(QColor(255, 255, 255, alpha)))
            painter.drawEllipse(QPointF(x, y), 2, 2)
        
        # Elektromanyetik dalga simülasyonu (logo etrafında)
        wave_radius_base = 70
        for wave in range(2):
            wave_radius = wave_radius_base + wave * 15
            wave_alpha = int(40 - wave * 15)
            wave_pen = QPen(QColor(59, 130, 246, wave_alpha), 1.5)
            wave_pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(wave_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            
            # Animasyonlu dalga
            animated_radius = wave_radius + 3 * math.sin((self.animation_frame + wave * 30) / 12)
            painter.drawEllipse(QPointF(center.x(), center.y()), animated_radius, animated_radius)
    
    def draw_decorative_elements(self, painter):
        """Arka plan dekoratif öğeleri çizer."""
        # Köşelerde hafif parıltılar
        corner_size = 80
        corner_alpha = int(30 + 20 * math.sin(self.animation_frame / 25))
        
        corners = [
            (0, 0),  # Sol üst
            (self.width, 0),  # Sağ üst
            (0, self.height),  # Sol alt
            (self.width, self.height)  # Sağ alt
        ]
        
        for corner_x, corner_y in corners:
            corner_gradient = QLinearGradient(corner_x, corner_y, 
                                            corner_x + corner_size, corner_y + corner_size)
            corner_gradient.setColorAt(0, QColor(99, 102, 241, corner_alpha))
            corner_gradient.setColorAt(1, QColor(99, 102, 241, 0))
            painter.setBrush(QBrush(corner_gradient))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(corner_x - corner_size // 2, corner_y - corner_size // 2, 
                              corner_size, corner_size)
    
    def draw_bottom_info(self, painter):
        """Alt bilgi çubuğu çizer."""
        info_y = self.height - 35
        info_height = 25
        
        # Bilgi çubuğu arka planı
        info_gradient = QLinearGradient(0, info_y, 0, info_y + info_height)
        info_gradient.setColorAt(0, QColor(15, 23, 42, 150))
        info_gradient.setColorAt(1, QColor(30, 41, 59, 150))
        
        painter.setBrush(QBrush(info_gradient))
        painter.setPen(QPen(QColor(59, 130, 246, 50), 1))
        painter.drawRoundedRect(10, info_y, self.width - 20, info_height, 8, 8)
        
        # Copyright veya bilgi metni
        info_font = QFont("Arial", 8, QFont.Weight.Normal)
        painter.setFont(info_font)
        painter.setPen(QColor(150, 170, 200, 180))
        painter.drawText(QRectF(10, info_y, self.width - 20, info_height), 
                        Qt.AlignmentFlag.AlignCenter, "© 2025 PEMF Medical System")

class ClosingScreen(QWidget):
    """Uygulama kapanırken gösterilecek ekran.
    
    Bu sınıf, uygulama kapatılırken gösterilen animasyonlu kapanış ekranını sağlar.
    """
    
    def __init__(self):
        """ClosingScreen sınıfını başlatır.
        
        Kapanış ekranının boyutlarını ve animasyon değişkenlerini ayarlar.
        """
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.width = 400
        self.height = 250
        
        self.setFixedSize(self.width, self.height)
        self.setWindowFlags(
            Qt.WindowType.SplashScreen | 
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        self.animation_frame = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.animate)
        self.timer.start(30)

    def animate(self):
        """Animasyon karesini günceller ve ekranı yeniler."""
        self.animation_frame += 1
        self.update()
    
    def closeEvent(self, event):
        """Pencere kapatılırken timer'ı durdur"""
        try:
            if hasattr(self, 'timer') and self.timer.isActive():
                self.timer.stop()
                self.logger.debug("Closing screen timer durduruldu")
        except Exception as e:
            self.logger.warning(f"Closing screen timer durdurulurken hata: {e}")
        event.accept()

    def paintEvent(self, event):
        """Zengin kapanış ekranını çizer."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        
        draw_rounded_gradient_background(painter, self.width, self.height, self.animation_frame)
        
        # Dekoratif elementler
        center_x, center_y = self.width // 2, self.height // 2
        
        # Dönen çemberler
        for i in range(2):
            radius = 40 + i * 20
            angle = (self.animation_frame * 2 + i * 90) % 360
            alpha = int(60 - i * 20)
            pen = QPen(QColor(59, 130, 246, alpha), 2)
            pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QPointF(center_x, center_y), radius, radius)
        
        # Ana metin - zengin stil
        alpha = int(180 + 75 * math.sin(self.animation_frame / 8))
        
        # Text shadow
        shadow_font = QFont("Arial", 22, QFont.Weight.Bold)
        painter.setFont(shadow_font)
        painter.setPen(QColor(0, 0, 0, 100))
        painter.drawText(QRectF(2, 2, self.width, self.height), 
                        Qt.AlignmentFlag.AlignCenter, "Sistem Kapatılıyor...")
        
        # Ana metin - gradient
        text_gradient = QLinearGradient(0, center_y - 20, 0, center_y + 20)
        text_gradient.setColorAt(0, QColor(255, 255, 255, alpha))
        text_gradient.setColorAt(0.5, QColor(200, 220, 255, alpha))
        text_gradient.setColorAt(1, QColor(150, 180, 255, alpha))
        
        font = QFont("Arial", 22, QFont.Weight.Bold)
        painter.setFont(font)
        painter.setPen(QPen(QBrush(text_gradient), 1))
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Sistem Kapatılıyor...")
        
        # Alt bilgi - "Sağlıklı günler" mesajı
        info_font = QFont("Arial", 9, QFont.Weight.Normal)
        painter.setFont(info_font)
        painter.setPen(QColor(150, 170, 200, 150))
        painter.drawText(QRectF(0, self.height - 50, self.width, 20), 
                        Qt.AlignmentFlag.AlignCenter, "Lütfen bekleyin...")
        
        # "Sağlıklı günler" mesajı
        goodbye_font = QFont("Arial", 11, QFont.Weight.Medium)
        painter.setFont(goodbye_font)
        goodbye_alpha = int(200 + 55 * math.sin(self.animation_frame / 10))
        goodbye_gradient = QLinearGradient(0, self.height - 30, 0, self.height - 10)
        goodbye_gradient.setColorAt(0, QColor(100, 200, 255, goodbye_alpha))
        goodbye_gradient.setColorAt(1, QColor(150, 220, 255, goodbye_alpha))
        painter.setPen(QPen(QBrush(goodbye_gradient), 1))
        painter.drawText(QRectF(0, self.height - 30, self.width, 20), 
                        Qt.AlignmentFlag.AlignCenter, "Sağlıklı günler dileriz...")

def show_splash_screen(app, version="1"):
    """Splash screen'i gösterir ve döndürür.
    
    Args:
        app: QApplication instance
        version: Yazılım sürümü (varsayılan: "1")
    """
    try:
        splash = ModernSplashScreen(version=version)
        splash.show()
        
        screen = app.primaryScreen().geometry()
        splash.move(
            (screen.width() - splash.width) // 2,
            (screen.height() - splash.height) // 2
        )
        
        # En öne getir
        splash.raise_()
        splash.activateWindow()
        QApplication.processEvents()
        
        return splash
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Splash screen gösterilirken hata: {e}", exc_info=True)
        return None

def show_closing_screen(app):
    """Kapanış ekranını gösterir ve ekran nesnesini döndürür."""
    try:
        closing_screen = ClosingScreen()
        screen = app.primaryScreen().geometry()
        closing_screen.move(
            (screen.width() - closing_screen.width) // 2,
            (screen.height() - closing_screen.height) // 2
        )
        closing_screen.show()
        closing_screen.raise_()
        closing_screen.activateWindow()
        QApplication.processEvents()
        
        return closing_screen
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Closing screen gösterilirken hata: {e}", exc_info=True)
        return None

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    splash = show_splash_screen(app)
    
    # Gerçek yükleme sürecini simüle et
    loading_steps = {
        10: "Sistem kaynakları kontrol ediliyor...",
        25: "Modüller yükleniyor...",
        45: "Veritabanı bağlantısı kuruluyor...",
        70: "Kullanıcı arayüzü hazırlanıyor...",
        90: "Son kontroller yapılıyor...",
        100: "Başlatılıyor!"
    }

    for progress, message in loading_steps.items():
        splash.set_progress(progress, message)
        time.sleep(0.5) # Gerçek bir işlem yerine bekleme

    # Ana uygulama penceresi simülasyonu
    main_window = QWidget()
    main_window.setWindowTitle("Ana Uygulama")
    main_window.resize(800, 600)
    
    splash.close()
    main_window.show()
    
    # Uygulama çalışıyor...
    # ...
    
    # Kapanış sürecini başlat
    original_exit = app.exec
    
    def on_exit():
        main_window.close()
        closing_screen = show_closing_screen(app)
        
        # Gerçek temizleme işlemlerini simüle et
        time.sleep(3) 
        
        closing_screen.close()
        app.quit()

    # Uygulamanın normal kapanışını simüle etmek için bir zamanlayıcı
    QTimer.singleShot(5000, on_exit)

    sys.exit(original_exit())
