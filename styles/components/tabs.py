# -*- coding: utf-8 -*-
"""
Tab Component Styles
QTabWidget, QTabBar stilleri
"""

from ..design_tokens import DesignTokens as DT
from ..theme_manager import get_current_theme


class TabStyles:
    """QTabWidget stilleri"""
    
    @staticmethod
    def tab_widget() -> str:
        """QTabWidget stilleri"""
        theme = get_current_theme()
        return f"""
            QTabWidget::pane {{
                border: 2px solid {theme.get_color('border_primary')};
                border-radius: {DT.RADIUS_LG}px;
                background: {theme.get_color('bg_input')};
                margin-top: {DT.SPACE_2}px;
            }}
            
            QTabWidget::tab-bar {{
                alignment: center;
            }}
        """
    
    @staticmethod
    def tab_bar() -> str:
        """QTabBar stilleri"""
        theme = get_current_theme()
        return f"""
            QTabBar::tab {{
                background: rgba(255, 255, 255, 0.05);
                border: 1px solid {theme.get_color('border_secondary')};
                padding: {DT.SPACE_3}px {DT.SPACE_6}px;
                margin-right: {DT.SPACE_1}px;
                border-top-left-radius: {DT.RADIUS_MD}px;
                border-top-right-radius: {DT.RADIUS_MD}px;
                font-size: {DT.FONT_SIZE_MD}px;
                font-weight: {DT.FONT_WEIGHT_SEMIBOLD};
                font-family: {DT.FONT_FAMILY_PRIMARY};
                color: {theme.get_color('text_secondary')};
                min-width: 120px;
            }}
            
            QTabBar::tab:selected {{
                background: rgba(99, 102, 241, 0.2);
                border-color: rgba(99, 102, 241, 0.5);
                color: {theme.get_color('text_primary')};
            }}
            
            QTabBar::tab:hover {{
                background: {theme.get_color('bg_input_focus')};
                color: {theme.get_color('text_primary')};
            }}
        """
    
    @staticmethod
    def all() -> str:
        """Tüm tab stillerini birleştir"""
        return "\n".join([
            TabStyles.tab_widget(),
            TabStyles.tab_bar(),
        ])


__all__ = ['TabStyles']

