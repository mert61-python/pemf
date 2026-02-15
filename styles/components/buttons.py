# -*- coding: utf-8 -*-
"""
Button Component Styles
QPushButton stilleri
"""

from ..design_tokens import DesignTokens as DT
from ..theme_manager import get_current_theme


class ButtonStyles:
    """QPushButton stilleri"""
    
    @staticmethod
    def base() -> str:
        """Temel button stilleri"""
        theme = get_current_theme()
        return f"""
            QPushButton {{
                background: {theme.get_gradient('button_primary')};
                border: 1px solid rgba(99, 102, 241, 0.3);
                border-radius: {DT.RADIUS_MD}px;
                color: {theme.get_color('text_primary')};
                font-size: {DT.FONT_SIZE_MD}px;
                font-weight: {DT.FONT_WEIGHT_SEMIBOLD};
                font-family: {DT.FONT_FAMILY_PRIMARY};
                padding: {DT.SPACE_3}px {DT.SPACE_6}px;
                min-height: {DT.SPACE_5}px;
            }}
            
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                    stop:0 rgba(99, 102, 241, 1.0), stop:1 rgba(67, 56, 202, 1.0));
                border: 2px solid rgba(99, 102, 241, 0.6);
                padding: {DT.SPACE_3 - 1}px {DT.SPACE_6 - 1}px;
            }}
            
            QPushButton:pressed {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                    stop:0 rgba(67, 56, 202, 0.9), stop:1 rgba(55, 48, 163, 0.9));
                border: 2px solid rgba(67, 56, 202, 0.8);
                padding: {DT.SPACE_3 + 1}px {DT.SPACE_6 + 1}px;
            }}
            
            QPushButton:disabled {{
                background: {theme.get_color('bg_input')};
                border-color: {theme.get_color('border_secondary')};
                color: {theme.get_color('text_disabled')};
            }}
        """
    
    @staticmethod
    def primary() -> str:
        """Primary button"""
        theme = get_current_theme()
        return f"""
            QPushButton[class="primary"] {{
                background: {theme.get_gradient('button_primary')};
                border-color: rgba(99, 102, 241, 0.5);
            }}
            
            QPushButton[class="primary"]:hover {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                    stop:0 rgba(99, 102, 241, 1.0), stop:1 rgba(67, 56, 202, 1.0));
                border-color: rgba(99, 102, 241, 0.7);
            }}
        """
    
    @staticmethod
    def success() -> str:
        """Success button (yeşil)"""
        theme = get_current_theme()
        return f"""
            QPushButton[class="success"], QPushButton#startButton {{
                background: {theme.get_gradient('button_success')};
                border-color: rgba(34, 197, 94, 0.3);
            }}
            
            QPushButton[class="success"]:hover, QPushButton#startButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                    stop:0 rgba(34, 197, 94, 1.0), stop:1 rgba(21, 128, 61, 1.0));
                border-color: rgba(34, 197, 94, 0.6);
            }}
            
            QPushButton[class="success"]:pressed, QPushButton#startButton:pressed {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                    stop:0 rgba(21, 128, 61, 0.9), stop:1 rgba(20, 83, 45, 0.9));
            }}
        """
    
    @staticmethod
    def danger() -> str:
        """Danger button (kırmızı)"""
        theme = get_current_theme()
        return f"""
            QPushButton[class="danger"], QPushButton#stopButton {{
                background: {theme.get_gradient('button_danger')};
                border-color: rgba(239, 68, 68, 0.3);
            }}
            
            QPushButton[class="danger"]:hover, QPushButton#stopButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                    stop:0 rgba(239, 68, 68, 1.0), stop:1 rgba(185, 28, 28, 1.0));
                border-color: rgba(239, 68, 68, 0.6);
            }}
            
            QPushButton[class="danger"]:pressed, QPushButton#stopButton:pressed {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                    stop:0 rgba(185, 28, 28, 0.9), stop:1 rgba(153, 27, 27, 0.9));
            }}
        """
    
    @staticmethod
    def secondary() -> str:
        """Secondary button (gri/transparent)"""
        theme = get_current_theme()
        return f"""
            QPushButton[class="secondary"] {{
                background: {theme.get_color('bg_input')};
                border: 1px solid {theme.get_color('border_primary')};
                color: {theme.get_color('text_secondary')};
            }}
            
            QPushButton[class="secondary"]:hover {{
                background: {theme.get_color('bg_input_focus')};
                border-color: {theme.get_color('border_focus')};
                color: {theme.get_color('text_primary')};
            }}
            
            QPushButton[class="secondary"]:pressed {{
                background: rgba(255, 255, 255, 0.25);
            }}
        """
    
    @staticmethod
    def ghost() -> str:
        """Ghost button (transparent)"""
        theme = get_current_theme()
        return f"""
            QPushButton[class="ghost"] {{
                background: transparent;
                border: none;
                color: {theme.get_color('text_secondary')};
            }}
            
            QPushButton[class="ghost"]:hover {{
                background: {theme.get_color('bg_input')};
                color: {theme.get_color('text_primary')};
            }}
            
            QPushButton[class="ghost"]:pressed {{
                background: {theme.get_color('bg_input_focus')};
            }}
        """
    
    @staticmethod
    def all() -> str:
        """Tüm button stillerini birleştir"""
        return "\n".join([
            ButtonStyles.base(),
            ButtonStyles.primary(),
            ButtonStyles.success(),
            ButtonStyles.danger(),
            ButtonStyles.secondary(),
            ButtonStyles.ghost(),
        ])


__all__ = ['ButtonStyles']

