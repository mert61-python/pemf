# -*- coding: utf-8 -*-
"""
PEMF GUI Theme Manager
Tema yönetimi ve tema switching altyapısı
"""

from typing import Dict, Optional, Callable, List
from enum import Enum
import threading
from .design_tokens import DesignTokens as DT


class ThemeType(Enum):
    """Tema tipleri"""
    DARK = "dark"
    LIGHT = "light"  # Future implementation


class Theme:
    """Tema sınıfı - Tema-specific değerler"""
    
    def __init__(self, name: str, theme_type: ThemeType):
        self.name = name
        self.type = theme_type
        self._colors: Dict[str, str] = {}
        self._gradients: Dict[str, str] = {}
        
    def set_color(self, key: str, value: str):
        """Tema rengi ayarla"""
        self._colors[key] = value
        
    def set_gradient(self, key: str, value: str):
        """Tema gradient ayarla"""
        self._gradients[key] = value
        
    def get_color(self, key: str, default: str = "#ffffff") -> str:
        """Tema rengi al"""
        return self._colors.get(key, default)
    
    def get_gradient(self, key: str, default: str = "") -> str:
        """Tema gradient al"""
        return self._gradients.get(key, default)


class DarkTheme(Theme):
    """Dark tema - Mevcut mor gradyan tema"""
    
    def __init__(self):
        super().__init__("Dark Purple", ThemeType.DARK)
        
        # Background colors
        self.set_color("bg_primary", DT.BG_DARK_PRIMARY.hex)
        self.set_color("bg_secondary", DT.BG_DARK_SECONDARY.hex)
        self.set_color("bg_tertiary", DT.BG_DARK_TERTIARY.hex)
        self.set_color("bg_card", DT.rgba(DT.WHITE, DT.OPACITY_10))
        self.set_color("bg_card_elevated", DT.rgba(DT.WHITE, DT.OPACITY_15))
        self.set_color("bg_input", DT.rgba(DT.WHITE, DT.OPACITY_10))
        self.set_color("bg_input_focus", DT.rgba(DT.WHITE, DT.OPACITY_20))
        
        # Text colors
        self.set_color("text_primary", DT.WHITE.hex)
        self.set_color("text_secondary", DT.rgba(DT.WHITE, DT.OPACITY_80))
        self.set_color("text_tertiary", DT.rgba(DT.WHITE, DT.OPACITY_60))
        self.set_color("text_disabled", DT.rgba(DT.WHITE, DT.OPACITY_40))
        
        # Border colors
        self.set_color("border_primary", DT.rgba(DT.WHITE, DT.OPACITY_30))
        self.set_color("border_secondary", DT.rgba(DT.WHITE, DT.OPACITY_20))
        self.set_color("border_focus", DT.PRIMARY.hex)
        
        # Primary colors
        self.set_color("primary", DT.PRIMARY.hex)
        self.set_color("primary_hover", DT.PRIMARY_LIGHT.hex)
        self.set_color("primary_active", DT.PRIMARY_DARK.hex)
        
        # Semantic colors
        self.set_color("success", DT.SUCCESS.hex)
        self.set_color("success_hover", DT.rgba(DT.SUCCESS, DT.OPACITY_90))
        self.set_color("warning", DT.WARNING.hex)
        self.set_color("warning_hover", DT.rgba(DT.WARNING, DT.OPACITY_90))
        self.set_color("error", DT.ERROR.hex)
        self.set_color("error_hover", DT.rgba(DT.ERROR, DT.OPACITY_90))
        self.set_color("info", DT.INFO.hex)
        self.set_color("info_hover", DT.rgba(DT.INFO, DT.OPACITY_90))
        
        # Gradients
        self.set_gradient("bg_window", DT.GRADIENT_PRIMARY)
        self.set_gradient("bg_window_alt", DT.GRADIENT_SECONDARY)
        self.set_gradient("bg_window_tertiary", DT.GRADIENT_TERTIARY)
        self.set_gradient("button_primary", DT.GRADIENT_BUTTON_PRIMARY)
        self.set_gradient("button_success", DT.GRADIENT_BUTTON_SUCCESS)
        self.set_gradient("button_danger", DT.GRADIENT_BUTTON_DANGER)


class ThemeManager:
    """
    Tema yöneticisi - Singleton pattern (thread-safe)
    Runtime'da tema değişikliği ve tema-aware rendering
    """
    
    _instance: Optional['ThemeManager'] = None
    _lock = threading.Lock()
    _current_theme: Theme = None
    _themes: Dict[str, Theme] = {}
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialize()
        return cls._instance
    
    def _initialize(self):
        """Theme manager'ı başlat"""
        self._themes = {}
        self._listeners: List[Callable[[Theme], None]] = []

        # Register built-in themes
        dark_theme = DarkTheme()
        self._themes[dark_theme.name] = dark_theme
        
        # Set default theme
        self._current_theme = dark_theme
    
    @property
    def current_theme(self) -> Theme:
        """Aktif tema"""
        return self._current_theme
    
    @property
    def available_themes(self) -> List[str]:
        """Mevcut tema isimleri"""
        return list(self._themes.keys())
    
    def get_theme(self, name: str) -> Optional[Theme]:
        """İsme göre tema al (thread-safe)"""
        with self._lock:
            return self._themes.get(name)
    
    def register_theme(self, theme: Theme):
        """Yeni tema kaydet (thread-safe)"""
        with self._lock:
            self._themes[theme.name] = theme
    
    def set_theme(self, theme_name: str) -> bool:
        """Tema değiştir (thread-safe)"""
        with self._lock:
            theme = self._themes.get(theme_name)
            if theme is None:
                return False
            
            old_theme = self._current_theme
            self._current_theme = theme
            
            # Notify listeners (outside lock to avoid deadlock)
            if old_theme != theme:
                listeners_copy = self._listeners.copy()
            else:
                listeners_copy = []
        
        # Notify listeners outside lock
        if listeners_copy:
            self._notify_listeners(theme, listeners_copy)
        
        return True
    
    def add_listener(self, callback: Callable[[Theme], None]):
        """Tema değişikliği listener ekle (thread-safe)"""
        with self._lock:
            if callback not in self._listeners:
                self._listeners.append(callback)
    
    def remove_listener(self, callback: Callable[[Theme], None]):
        """Tema değişikliği listener kaldır (thread-safe)"""
        with self._lock:
            if callback in self._listeners:
                self._listeners.remove(callback)
    
    def _notify_listeners(self, theme: Theme, listeners: Optional[list] = None):
        """Listener'ları bilgilendir"""
        if listeners is None:
            with self._lock:
                listeners = self._listeners.copy()
        
        for listener in listeners:
            try:
                listener(theme)
            except Exception as e:
                print(f"Theme listener error: {e}")
    
    # Convenience methods for current theme
    def get_color(self, key: str, default: str = "#ffffff") -> str:
        """Aktif temadan renk al"""
        return self._current_theme.get_color(key, default)
    
    def get_gradient(self, key: str, default: str = "") -> str:
        """Aktif temadan gradient al"""
        return self._current_theme.get_gradient(key, default)


# Singleton instance
_theme_manager = ThemeManager()


def get_theme_manager() -> ThemeManager:
    """Theme manager instance al"""
    return _theme_manager


# Convenience function
def get_current_theme() -> Theme:
    """Aktif tema al"""
    return _theme_manager.current_theme


__all__ = ['ThemeManager', 'Theme', 'ThemeType', 'DarkTheme', 'get_theme_manager', 'get_current_theme']

