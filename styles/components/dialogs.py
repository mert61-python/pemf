# -*- coding: utf-8 -*-
"""
Dialog Component Styles
QDialog, QMessageBox stilleri
"""

from ..design_tokens import DesignTokens as DT
from ..theme_manager import get_current_theme


class DialogStyles:
    """QDialog stilleri"""
    
    @staticmethod
    def dialog() -> str:
        """Temel dialog stilleri"""
        theme = get_current_theme()
        return f"""
            QDialog {{
                background: {theme.get_gradient('bg_window')};
                color: {theme.get_color('text_primary')};
                font-family: {DT.FONT_FAMILY_PRIMARY};
            }}
        """
    
    @staticmethod
    def dialog_dark() -> str:
        """Dark dialog (daha koyu arka plan)"""
        theme = get_current_theme()
        return f"""
            QDialog[class="dark"] {{
                background-color: #2b2b2b;
                color: {theme.get_color('text_primary')};
            }}
        """
    
    @staticmethod
    def dialog_light() -> str:
        """Light dialog (açık renkli)"""
        return f"""
            QDialog[class="light"] {{
                background: {DT.GRADIENT_LIGHT};
                color: #333333;
            }}
        """
    
    @staticmethod
    def dialog_title() -> str:
        """Dialog başlık stilleri"""
        theme = get_current_theme()
        return f"""
            #dialogTitle, #emailTitle {{
                font-size: {DT.FONT_SIZE_XL}px;
                font-weight: {DT.FONT_WEIGHT_BOLD};
                color: {theme.get_color('text_primary')};
                margin: {DT.SPACE_2}px 0;
                padding: {DT.SPACE_2}px;
                background: rgba(142, 68, 173, 0.8);
                border-radius: {DT.RADIUS_MD}px;
            }}
        """
    
    @staticmethod
    def message_box() -> str:
        """QMessageBox stilleri"""
        theme = get_current_theme()
        return f"""
            QMessageBox {{
                background: {theme.get_gradient('bg_window')};
                color: {theme.get_color('text_primary')};
                font-family: {DT.FONT_FAMILY_PRIMARY};
            }}
            
            QMessageBox QLabel {{
                color: {theme.get_color('text_primary')};
                font-size: {DT.FONT_SIZE_BASE}px;
            }}
        """
    
    @staticmethod
    def all() -> str:
        """Tüm dialog stillerini birleştir"""
        return "\n".join([
            DialogStyles.dialog(),
            DialogStyles.dialog_dark(),
            DialogStyles.dialog_light(),
            DialogStyles.dialog_title(),
            DialogStyles.message_box(),
        ])


__all__ = ['DialogStyles']

