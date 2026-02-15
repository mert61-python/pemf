# -*- coding: utf-8 -*-
"""
Card Component Styles
Card, elevated card, bordered card stilleri
"""

from ..design_tokens import DesignTokens as DT
from ..theme_manager import get_current_theme


class CardStyles:
    """Card component stilleri"""
    
    @staticmethod
    def card() -> str:
        """Temel card stilleri"""
        theme = get_current_theme()
        return f"""
            QWidget[class="card"] {{
                background: {theme.get_color('bg_card')};
                border: 1px solid {theme.get_color('border_secondary')};
                border-radius: {DT.RADIUS_XL}px;
                margin: {DT.SPACE_2}px;
                padding: {DT.SPACE_4}px;
            }}
        """
    
    @staticmethod
    def card_elevated() -> str:
        """Elevated card (daha belirgin)"""
        theme = get_current_theme()
        return f"""
            QWidget[class="card-elevated"] {{
                background: {theme.get_color('bg_card_elevated')};
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: {DT.RADIUS_XL}px;
                margin: {DT.SPACE_2}px;
                padding: {DT.SPACE_5}px;
            }}
        """
    
    @staticmethod
    def card_bordered() -> str:
        """Bordered card (kalın kenarlık)"""
        theme = get_current_theme()
        return f"""
            QWidget[class="card-bordered"] {{
                background: {theme.get_color('bg_card')};
                border: 2px solid {theme.get_color('border_primary')};
                border-radius: {DT.RADIUS_XL}px;
                margin: {DT.SPACE_2}px;
                padding: {DT.SPACE_4}px;
            }}
        """
    
    @staticmethod
    def all() -> str:
        """Tüm card stillerini birleştir"""
        return "\n".join([
            CardStyles.card(),
            CardStyles.card_elevated(),
            CardStyles.card_bordered(),
        ])


__all__ = ['CardStyles']

