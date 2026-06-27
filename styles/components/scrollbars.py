# -*- coding: utf-8 -*-
"""
Scrollbar Component Styles
QScrollBar stilleri
"""

from ..design_tokens import DesignTokens as DT
from ..theme_manager import get_current_theme


class ScrollbarStyles:
    """QScrollBar stilleri"""
    
    @staticmethod
    def vertical() -> str:
        """Vertical scrollbar"""
        theme = get_current_theme()
        return f"""
            QScrollBar:vertical {{
                background: rgba(255, 255, 255, 0.05);
                width: {DT.SPACE_3}px;
                border-radius: {DT.SPACE_3 // 2}px;
                margin: 0;
            }}
            
            QScrollBar::handle:vertical {{
                background: rgba(255, 255, 255, 0.2);
                border-radius: {DT.SPACE_3 // 2}px;
                min-height: {DT.SPACE_8}px;
                margin: {DT.SPACE_1}px;
            }}
            
            QScrollBar::handle:vertical:hover {{
                background: rgba(255, 255, 255, 0.3);
            }}
            
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: none;
            }}
        """
    
    @staticmethod
    def horizontal() -> str:
        """Horizontal scrollbar"""
        theme = get_current_theme()
        return f"""
            QScrollBar:horizontal {{
                background: rgba(255, 255, 255, 0.05);
                height: {DT.SPACE_3}px;
                border-radius: {DT.SPACE_3 // 2}px;
                margin: 0;
            }}
            
            QScrollBar::handle:horizontal {{
                background: rgba(255, 255, 255, 0.2);
                border-radius: {DT.SPACE_3 // 2}px;
                min-width: {DT.SPACE_8}px;
                margin: {DT.SPACE_1}px;
            }}
            
            QScrollBar::handle:horizontal:hover {{
                background: rgba(255, 255, 255, 0.3);
            }}
            
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
                width: 0px;
            }}
            
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
                background: none;
            }}
        """
    
    @staticmethod
    def scroll_area() -> str:
        """QScrollArea stilleri"""
        return f"""
            QScrollArea {{
                border: none;
                background: transparent;
            }}
        """
    
    @staticmethod
    def all() -> str:
        """Tüm scrollbar stillerini birleştir"""
        return "\n".join([
            ScrollbarStyles.vertical(),
            ScrollbarStyles.horizontal(),
            ScrollbarStyles.scroll_area(),
        ])


__all__ = ['ScrollbarStyles']

