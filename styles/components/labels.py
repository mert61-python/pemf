# -*- coding: utf-8 -*-
"""
Label Component Styles
QLabel stilleri (title, subtitle, body, caption, status)
"""

from ..design_tokens import DesignTokens as DT
from ..theme_manager import get_current_theme


class LabelStyles:
    """QLabel stilleri"""
    
    @staticmethod
    def base() -> str:
        """Temel label stilleri"""
        theme = get_current_theme()
        return f"""
            QLabel {{
                color: {theme.get_color('text_primary')};
                font-size: {DT.FONT_SIZE_BASE}px;
                font-family: {DT.FONT_FAMILY_PRIMARY};
            }}
        """
    
    @staticmethod
    def title() -> str:
        """Title label (büyük başlık)"""
        theme = get_current_theme()
        return f"""
            #titleLabel {{
                font-size: {DT.FONT_SIZE_3XL}px;
                font-weight: {DT.FONT_WEIGHT_BOLD};
                color: {theme.get_color('text_primary')};
                margin: {DT.SPACE_2}px 0;
                padding: {DT.SPACE_4}px;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, 
                    stop:0 rgba(142, 68, 173, 0.8), 
                    stop:1 rgba(155, 89, 182, 0.8));
                border-radius: {DT.RADIUS_LG}px;
                border: 2px solid {theme.get_color('border_secondary')};
            }}
        """
    
    @staticmethod
    def section() -> str:
        """Section label (bölüm başlığı)"""
        theme = get_current_theme()
        return f"""
            #sectionLabel {{
                font-size: {DT.FONT_SIZE_LG}px;
                font-weight: {DT.FONT_WEIGHT_BOLD};
                color: {DT.PRIMARY.hex};
                margin: {DT.SPACE_1}px 0;
            }}
        """
    
    @staticmethod
    def status() -> str:
        """Status label'ları (success, warning, error, info)"""
        theme = get_current_theme()
        return f"""
            QLabel[class="status-success"] {{
                color: {theme.get_color('success')};
                font-weight: {DT.FONT_WEIGHT_SEMIBOLD};
            }}
            
            QLabel[class="status-warning"] {{
                color: {theme.get_color('warning')};
                font-weight: {DT.FONT_WEIGHT_SEMIBOLD};
            }}
            
            QLabel[class="status-error"] {{
                color: {theme.get_color('error')};
                font-weight: {DT.FONT_WEIGHT_SEMIBOLD};
            }}
            
            QLabel[class="status-info"] {{
                color: {theme.get_color('info')};
                font-weight: {DT.FONT_WEIGHT_SEMIBOLD};
            }}
        """
    
    @staticmethod
    def caption() -> str:
        """Caption label (küçük açıklama metni)"""
        theme = get_current_theme()
        return f"""
            QLabel[class="caption"] {{
                color: {theme.get_color('text_tertiary')};
                font-size: {DT.FONT_SIZE_SM}px;
            }}
        """
    
    @staticmethod
    def all() -> str:
        """Tüm label stillerini birleştir"""
        return "\n".join([
            LabelStyles.base(),
            LabelStyles.title(),
            LabelStyles.section(),
            LabelStyles.status(),
            LabelStyles.caption(),
        ])


__all__ = ['LabelStyles']

