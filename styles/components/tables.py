# -*- coding: utf-8 -*-
"""
Table Component Styles
QTableWidget, QHeaderView stilleri
"""

from ..design_tokens import DesignTokens as DT
from ..theme_manager import get_current_theme


class TableStyles:
    """QTableWidget stilleri"""
    
    @staticmethod
    def table_widget() -> str:
        """QTableWidget stilleri"""
        theme = get_current_theme()
        return f"""
            QTableWidget {{
                gridline-color: {theme.get_color('border_secondary')};
                background: {theme.get_color('bg_input')};
                alternate-background-color: rgba(255, 255, 255, 0.05);
                selection-background-color: rgba(142, 68, 173, 0.6);
                border: 2px solid {theme.get_color('border_primary')};
                border-radius: {DT.RADIUS_LG}px;
                font-family: {DT.FONT_FAMILY_PRIMARY};
            }}
            
            QTableWidget::item {{
                padding: {DT.SPACE_3}px {DT.SPACE_2}px;
                border-bottom: 1px solid {theme.get_color('border_secondary')};
                color: {theme.get_color('text_primary')};
            }}
            
            QTableWidget::item:selected {{
                background: rgba(142, 68, 173, 0.8);
                color: {theme.get_color('text_primary')};
            }}
            
            QTableWidget::item:hover {{
                background: {theme.get_color('bg_input_focus')};
            }}
        """
    
    @staticmethod
    def header_view() -> str:
        """QHeaderView stilleri"""
        theme = get_current_theme()
        return f"""
            QHeaderView::section {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, 
                    stop:0 {DT.PRIMARY.hex}, stop:1 {DT.PRIMARY_LIGHT.hex});
                color: {theme.get_color('text_primary')};
                padding: {DT.SPACE_3}px {DT.SPACE_2}px;
                border: none;
                font-weight: {DT.FONT_WEIGHT_BOLD};
                font-size: {DT.FONT_SIZE_BASE}px;
                font-family: {DT.FONT_FAMILY_PRIMARY};
            }}
            
            QHeaderView::section:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, 
                    stop:0 {DT.PRIMARY_LIGHT.hex}, stop:1 {DT.PRIMARY_LIGHTER.hex});
            }}
        """
    
    @staticmethod
    def all() -> str:
        """Tüm table stillerini birleştir"""
        return "\n".join([
            TableStyles.table_widget(),
            TableStyles.header_view(),
        ])


__all__ = ['TableStyles']

