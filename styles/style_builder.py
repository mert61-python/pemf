# -*- coding: utf-8 -*-
"""
Style Builder
QSS string oluşturucu utility - Component kombinasyonları ve dynamic style generation
"""

from typing import List, Optional, Dict
from .design_tokens import DesignTokens as DT
from .theme_manager import get_current_theme
from .components import (
    ButtonStyles,
    InputStyles,
    TableStyles,
    TabStyles,
    CardStyles,
    ScrollbarStyles,
    DialogStyles,
    LabelStyles,
    GroupBoxStyles,
)


class StyleBuilder:
    """
    QSS Style Builder
    Fluent API ile stil oluşturma
    """
    
    def __init__(self):
        self._styles: List[str] = []
        self._cache: Dict[str, str] = {}
        
    def reset(self) -> 'StyleBuilder':
        """Builder'ı sıfırla"""
        self._styles.clear()
        return self
    
    def add_custom(self, style: str) -> 'StyleBuilder':
        """Özel stil ekle"""
        self._styles.append(style)
        return self
    
    # ==================== BUTTONS ====================
    
    def button(self, variant: str = 'all') -> 'StyleBuilder':
        """Button stilleri ekle"""
        if variant == 'all':
            self._styles.append(ButtonStyles.all())
        elif variant == 'base':
            self._styles.append(ButtonStyles.base())
        elif variant == 'primary':
            self._styles.append(ButtonStyles.primary())
        elif variant == 'success':
            self._styles.append(ButtonStyles.success())
        elif variant == 'danger':
            self._styles.append(ButtonStyles.danger())
        elif variant == 'secondary':
            self._styles.append(ButtonStyles.secondary())
        elif variant == 'ghost':
            self._styles.append(ButtonStyles.ghost())
        return self
    
    # ==================== INPUTS ====================
    
    def input(self, variant: str = 'all') -> 'StyleBuilder':
        """Input stilleri ekle"""
        if variant == 'all':
            self._styles.append(InputStyles.all())
        elif variant == 'line_edit':
            self._styles.append(InputStyles.line_edit())
        elif variant == 'text_edit':
            self._styles.append(InputStyles.text_edit())
        elif variant == 'spin_box':
            self._styles.append(InputStyles.spin_box())
        elif variant == 'combo_box':
            self._styles.append(InputStyles.combo_box())
        elif variant == 'date_edit':
            self._styles.append(InputStyles.date_edit())
        elif variant == 'slider':
            self._styles.append(InputStyles.slider())
        return self
    
    # ==================== TABLES ====================
    
    def table(self, variant: str = 'all') -> 'StyleBuilder':
        """Table stilleri ekle"""
        if variant == 'all':
            self._styles.append(TableStyles.all())
        elif variant == 'table_widget':
            self._styles.append(TableStyles.table_widget())
        elif variant == 'header_view':
            self._styles.append(TableStyles.header_view())
        return self
    
    # ==================== TABS ====================
    
    def tab(self, variant: str = 'all') -> 'StyleBuilder':
        """Tab stilleri ekle"""
        if variant == 'all':
            self._styles.append(TabStyles.all())
        elif variant == 'tab_widget':
            self._styles.append(TabStyles.tab_widget())
        elif variant == 'tab_bar':
            self._styles.append(TabStyles.tab_bar())
        return self
    
    # ==================== CARDS ====================
    
    def card(self, variant: str = 'all') -> 'StyleBuilder':
        """Card stilleri ekle"""
        if variant == 'all':
            self._styles.append(CardStyles.all())
        elif variant == 'card':
            self._styles.append(CardStyles.card())
        elif variant == 'elevated':
            self._styles.append(CardStyles.card_elevated())
        elif variant == 'bordered':
            self._styles.append(CardStyles.card_bordered())
        return self
    
    # ==================== SCROLLBARS ====================
    
    def scrollbar(self, variant: str = 'all') -> 'StyleBuilder':
        """Scrollbar stilleri ekle"""
        if variant == 'all':
            self._styles.append(ScrollbarStyles.all())
        elif variant == 'vertical':
            self._styles.append(ScrollbarStyles.vertical())
        elif variant == 'horizontal':
            self._styles.append(ScrollbarStyles.horizontal())
        elif variant == 'scroll_area':
            self._styles.append(ScrollbarStyles.scroll_area())
        return self
    
    # ==================== DIALOGS ====================
    
    def dialog(self, variant: str = 'all') -> 'StyleBuilder':
        """Dialog stilleri ekle"""
        if variant == 'all':
            self._styles.append(DialogStyles.all())
        elif variant == 'dialog':
            self._styles.append(DialogStyles.dialog())
        elif variant == 'dark':
            self._styles.append(DialogStyles.dialog_dark())
        elif variant == 'light':
            self._styles.append(DialogStyles.dialog_light())
        elif variant == 'title':
            self._styles.append(DialogStyles.dialog_title())
        elif variant == 'message_box':
            self._styles.append(DialogStyles.message_box())
        return self
    
    # ==================== LABELS ====================
    
    def label(self, variant: str = 'all') -> 'StyleBuilder':
        """Label stilleri ekle"""
        if variant == 'all':
            self._styles.append(LabelStyles.all())
        elif variant == 'base':
            self._styles.append(LabelStyles.base())
        elif variant == 'title':
            self._styles.append(LabelStyles.title())
        elif variant == 'section':
            self._styles.append(LabelStyles.section())
        elif variant == 'status':
            self._styles.append(LabelStyles.status())
        elif variant == 'caption':
            self._styles.append(LabelStyles.caption())
        return self
    
    # ==================== GROUPBOX ====================
    
    def groupbox(self, variant: str = 'all') -> 'StyleBuilder':
        """GroupBox stilleri ekle"""
        if variant == 'all':
            self._styles.append(GroupBoxStyles.all())
        elif variant == 'base':
            self._styles.append(GroupBoxStyles.base())
        elif variant == 'simple':
            self._styles.append(GroupBoxStyles.simple())
        return self
    
    # ==================== WINDOW BACKGROUNDS ====================
    
    def window_background(self, variant: str = 'primary') -> 'StyleBuilder':
        """Window arka plan stilleri"""
        theme = get_current_theme()
        
        if variant == 'primary':
            gradient = theme.get_gradient('bg_window')
        elif variant == 'secondary':
            gradient = theme.get_gradient('bg_window_alt')
        elif variant == 'tertiary':
            gradient = theme.get_gradient('bg_window_tertiary')
        else:
            gradient = theme.get_gradient('bg_window')
        
        style = f"""
            QMainWindow, QWidget {{
                background: {gradient};
                font-family: {DT.FONT_FAMILY_PRIMARY};
                color: {theme.get_color('text_primary')};
            }}
        """
        self._styles.append(style)
        return self
    
    def status_bar(self) -> 'StyleBuilder':
        """Status bar stilleri"""
        style = f"""
            QStatusBar {{
                background: rgba(0, 0, 0, 0.3);
                color: rgba(255, 255, 255, 0.8);
                border-top: 1px solid rgba(255, 255, 255, 0.1);
                padding: {DT.SPACE_2}px;
            }}
        """
        self._styles.append(style)
        return self
    
    # ==================== BUILD ====================
    
    def build(self, cache_key: Optional[str] = None) -> str:
        """QSS string oluştur"""
        if cache_key and cache_key in self._cache:
            return self._cache[cache_key]
        
        result = "\n".join(self._styles)
        
        if cache_key:
            self._cache[cache_key] = result
        
        return result
    
    def clear_cache(self):
        """Cache'i temizle"""
        self._cache.clear()


# Convenience function for common combinations
def get_default_stylesheet() -> str:
    """
    Varsayılan tam stylesheet
    Tüm component'leri içerir
    """
    builder = StyleBuilder()
    return (builder
            .window_background('primary')
            .button('all')
            .input('all')
            .table('all')
            .tab('all')
            .card('all')
            .scrollbar('all')
            .dialog('all')
            .label('all')
            .groupbox('all')
            .status_bar()
            .build(cache_key='default_full'))


def get_minimal_stylesheet() -> str:
    """
    Minimal stylesheet
    Sadece temel component'ler
    """
    builder = StyleBuilder()
    return (builder
            .window_background('primary')
            .button('base')
            .input('line_edit')
            .label('base')
            .scrollbar('all')
            .build(cache_key='minimal'))


__all__ = ['StyleBuilder', 'get_default_stylesheet', 'get_minimal_stylesheet']

