# -*- coding: utf-8 -*-
"""
GroupBox Component Styles
QGroupBox stilleri
"""

from ..design_tokens import DesignTokens as DT
from ..theme_manager import get_current_theme


class GroupBoxStyles:
    """QGroupBox stilleri"""
    
    @staticmethod
    def base() -> str:
        """Temel groupbox stilleri"""
        theme = get_current_theme()
        return f"""
            QGroupBox {{
                font-size: {DT.FONT_SIZE_MD}px;
                font-weight: {DT.FONT_WEIGHT_SEMIBOLD};
                font-family: {DT.FONT_FAMILY_PRIMARY};
                border: 3px solid {theme.get_color('border_primary')};
                border-radius: {DT.RADIUS_XL}px;
                margin: {DT.SPACE_3}px {DT.SPACE_2}px;
                padding-top: {DT.SPACE_4}px;
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                    stop:0 rgba(255, 255, 255, 0.12), 
                    stop:1 rgba(255, 255, 255, 0.06));
            }}
            
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: {DT.SPACE_5}px;
                padding: {DT.SPACE_2}px {DT.SPACE_4}px;
                color: {theme.get_color('text_primary')};
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                    stop:0 rgba(99, 102, 241, 0.8), 
                    stop:1 rgba(67, 56, 202, 0.8));
                border: 1px solid rgba(99, 102, 241, 0.4);
                border-radius: {DT.RADIUS_MD}px;
                font-weight: {DT.FONT_WEIGHT_BOLD};
            }}
        """
    
    @staticmethod
    def simple() -> str:
        """Basit groupbox (daha az vurgulu)"""
        theme = get_current_theme()
        return f"""
            QGroupBox[class="simple"] {{
                font-weight: {DT.FONT_WEIGHT_SEMIBOLD};
                border: 2px solid {theme.get_color('border_primary')};
                border-radius: {DT.RADIUS_MD}px;
                margin: {DT.SPACE_2}px 0;
                padding-top: {DT.SPACE_2}px;
                background: {theme.get_color('bg_input')};
            }}
            
            QGroupBox[class="simple"]::title {{
                subcontrol-origin: margin;
                left: {DT.SPACE_2}px;
                padding: 0 {DT.SPACE_1}px;
                color: {theme.get_color('text_primary')};
                background: rgba(142, 68, 173, 0.8);
                border-radius: {DT.RADIUS_SM}px;
            }}
        """
    
    @staticmethod
    def all() -> str:
        """Tüm groupbox stillerini birleştir"""
        return "\n".join([
            GroupBoxStyles.base(),
            GroupBoxStyles.simple(),
        ])


__all__ = ['GroupBoxStyles']

