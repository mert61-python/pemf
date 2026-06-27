# -*- coding: utf-8 -*-
"""
Style Mixin
Widget'lara kolay stil uygulama için mixin class
"""

from typing import Optional
from ..style_builder import StyleBuilder, get_default_stylesheet
from ..theme_manager import get_theme_manager, Theme


class StyleMixin:
    """
    Style Mixin - Widget'lara stil uygulama kolaylığı
    
    Kullanım:
        class MyWindow(QMainWindow, StyleMixin):
            def __init__(self):
                super().__init__()
                self.apply_theme()  # Otomatik tema uygulama
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._style_builder: Optional[StyleBuilder] = None
        self._theme_listener_registered = False
    
    @property
    def style_builder(self) -> StyleBuilder:
        """StyleBuilder instance al"""
        if self._style_builder is None:
            self._style_builder = StyleBuilder()
        return self._style_builder
    
    def apply_theme(self, stylesheet: Optional[str] = None, auto_update: bool = True):
        """
        Tema uygula
        
        Args:
            stylesheet: Özel stylesheet (None ise default kullanılır)
            auto_update: Tema değiştiğinde otomatik güncelle
        """
        if stylesheet is None:
            stylesheet = self.get_default_stylesheet()
        
        # Apply stylesheet
        if hasattr(self, 'setStyleSheet'):
            self.setStyleSheet(stylesheet)
        
        # Register theme change listener
        if auto_update and not self._theme_listener_registered:
            theme_manager = get_theme_manager()
            theme_manager.add_listener(self._on_theme_changed)
            self._theme_listener_registered = True
    
    def get_default_stylesheet(self) -> str:
        """
        Varsayılan stylesheet al
        Override edilebilir
        """
        return get_default_stylesheet()
    
    def get_custom_styles(self) -> str:
        """
        Özel stiller
        Alt sınıflar override edebilir
        """
        return ""
    
    def _on_theme_changed(self, theme: Theme):
        """Tema değiştiğinde çağrılır"""
        # Rebuild and reapply stylesheet
        custom_styles = self.get_custom_styles()
        if custom_styles:
            full_stylesheet = self.get_default_stylesheet() + "\n" + custom_styles
        else:
            full_stylesheet = self.get_default_stylesheet()
        
        if hasattr(self, 'setStyleSheet'):
            self.setStyleSheet(full_stylesheet)
    
    def update_styles(self):
        """Stilleri manuel güncelle"""
        self.apply_theme()
    
    def cleanup_theme_listener(self):
        """Tema listener'ı temizle"""
        if self._theme_listener_registered:
            theme_manager = get_theme_manager()
            theme_manager.remove_listener(self._on_theme_changed)
            self._theme_listener_registered = False
    
    def closeEvent(self, event):
        """Window kapatılırken cleanup"""
        self.cleanup_theme_listener()
        # Call parent's closeEvent if it exists
        # Using MRO to find the next class with closeEvent
        for cls in self.__class__.__mro__[1:]:
            if hasattr(cls, 'closeEvent') and cls != StyleMixin:
                cls.closeEvent(self, event)
                break


__all__ = ['StyleMixin']

