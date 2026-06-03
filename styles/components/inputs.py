# -*- coding: utf-8 -*-
"""
Input Component Styles
QLineEdit, QTextEdit, QSpinBox, QComboBox stilleri
"""

from ..design_tokens import DesignTokens as DT
from ..theme_manager import get_current_theme


class InputStyles:
    """Input component stilleri"""
    
    @staticmethod
    def line_edit() -> str:
        """QLineEdit stilleri"""
        theme = get_current_theme()
        return f"""
            QLineEdit {{
                background: {theme.get_color('bg_input')};
                border: 2px solid {theme.get_color('border_primary')};
                border-radius: {DT.RADIUS_MD}px;
                padding: {DT.SPACE_2}px {DT.SPACE_3}px;
                color: {theme.get_color('text_primary')};
                font-size: {DT.FONT_SIZE_BASE}px;
                font-family: {DT.FONT_FAMILY_PRIMARY};
                min-height: {DT.SPACE_5}px;
            }}
            
            QLineEdit:focus {{
                border-color: {theme.get_color('border_focus')};
                background: {theme.get_color('bg_input_focus')};
            }}
            
            QLineEdit:disabled {{
                background: rgba(255, 255, 255, 0.05);
                color: {theme.get_color('text_disabled')};
                border-color: {theme.get_color('border_secondary')};
            }}
        """
    
    @staticmethod
    def text_edit() -> str:
        """QTextEdit stilleri"""
        theme = get_current_theme()
        return f"""
            QTextEdit {{
                background: {theme.get_color('bg_input')};
                border: 2px solid {theme.get_color('border_primary')};
                border-radius: {DT.RADIUS_MD}px;
                padding: {DT.SPACE_3}px;
                color: {theme.get_color('text_primary')};
                font-size: {DT.FONT_SIZE_BASE}px;
                font-family: {DT.FONT_FAMILY_PRIMARY};
            }}
            
            QTextEdit:focus {{
                border-color: {theme.get_color('border_focus')};
                background: {theme.get_color('bg_input_focus')};
            }}
            
            QTextEdit:disabled {{
                background: rgba(255, 255, 255, 0.05);
                color: {theme.get_color('text_disabled')};
            }}
        """
    
    @staticmethod
    def spin_box() -> str:
        """QSpinBox, QDoubleSpinBox stilleri"""
        theme = get_current_theme()
        return f"""
            QSpinBox, QDoubleSpinBox {{
                background: {theme.get_color('bg_input')};
                border: 1px solid {theme.get_color('border_primary')};
                border-radius: {DT.RADIUS_MD}px;
                padding: {DT.SPACE_2}px {DT.SPACE_3}px;
                font-size: {DT.FONT_SIZE_BASE}px;
                font-family: {DT.FONT_FAMILY_PRIMARY};
                color: {theme.get_color('text_primary')};
                min-height: {DT.SPACE_5}px;
            }}
            
            QSpinBox:focus, QDoubleSpinBox:focus {{
                border: 2px solid {theme.get_color('border_focus')};
                background: {theme.get_color('bg_input_focus')};
            }}
            
            QSpinBox:disabled, QDoubleSpinBox:disabled {{
                background: rgba(255, 255, 255, 0.05);
                color: {theme.get_color('text_disabled')};
            }}
            
            QSpinBox::up-button, QDoubleSpinBox::up-button {{
                background: rgba(255, 255, 255, 0.1);
                border: none;
                border-top-right-radius: {DT.RADIUS_MD}px;
                width: {DT.SPACE_4}px;
            }}
            
            QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover {{
                background: rgba(255, 255, 255, 0.2);
            }}
            
            QSpinBox::down-button, QDoubleSpinBox::down-button {{
                background: rgba(255, 255, 255, 0.1);
                border: none;
                border-bottom-right-radius: {DT.RADIUS_MD}px;
                width: {DT.SPACE_4}px;
            }}
            
            QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{
                background: rgba(255, 255, 255, 0.2);
            }}
        """
    
    @staticmethod
    def combo_box() -> str:
        """QComboBox stilleri"""
        theme = get_current_theme()
        return f"""
            QComboBox {{
                background: {theme.get_color('bg_input')};
                border: 1px solid {theme.get_color('border_primary')};
                border-radius: {DT.RADIUS_MD}px;
                padding: {DT.SPACE_2}px {DT.SPACE_3}px;
                font-size: {DT.FONT_SIZE_BASE}px;
                font-family: {DT.FONT_FAMILY_PRIMARY};
                color: {theme.get_color('text_primary')};
                min-height: {DT.SPACE_5}px;
            }}
            
            QComboBox:focus {{
                border: 2px solid {theme.get_color('border_focus')};
                background: {theme.get_color('bg_input_focus')};
            }}
            
            QComboBox:disabled {{
                background: rgba(255, 255, 255, 0.05);
                color: {theme.get_color('text_disabled')};
            }}
            
            QComboBox::drop-down {{
                border: none;
                width: {DT.SPACE_5}px;
            }}
            
            QComboBox::down-arrow {{
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid {theme.get_color('text_secondary')};
                margin-right: 5px;
            }}
            
            QComboBox QAbstractItemView {{
                background: rgba(26, 26, 46, 0.95);
                border: 1px solid {theme.get_color('border_primary')};
                border-radius: {DT.RADIUS_MD}px;
                selection-background-color: rgba(99, 102, 241, 0.3);
                color: {theme.get_color('text_primary')};
                padding: {DT.SPACE_1}px;
            }}
        """
    
    @staticmethod
    def date_edit() -> str:
        """QDateEdit stilleri"""
        theme = get_current_theme()
        return f"""
            QDateEdit {{
                background: {theme.get_color('bg_input')};
                border: 2px solid {theme.get_color('border_primary')};
                border-radius: {DT.RADIUS_MD}px;
                padding: {DT.SPACE_2}px {DT.SPACE_3}px;
                color: {theme.get_color('text_primary')};
                font-size: {DT.FONT_SIZE_BASE}px;
                font-family: {DT.FONT_FAMILY_PRIMARY};
                min-height: {DT.SPACE_5}px;
            }}
            
            QDateEdit:focus {{
                border-color: {theme.get_color('border_focus')};
                background: {theme.get_color('bg_input_focus')};
            }}
        """
    
    @staticmethod
    def slider() -> str:
        """QSlider stilleri"""
        theme = get_current_theme()
        return f"""
            QSlider::groove:horizontal {{
                border: 1px solid {theme.get_color('border_primary')};
                height: 6px;
                background: {theme.get_color('bg_input')};
                border-radius: 3px;
            }}
            
            QSlider::handle:horizontal {{
                background: {theme.get_gradient('button_primary')};
                border: 1px solid rgba(99, 102, 241, 0.5);
                width: 18px;
                margin: -6px 0;
                border-radius: 9px;
            }}
            
            QSlider::handle:horizontal:hover {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                    stop:0 rgba(99, 102, 241, 1.0), stop:1 rgba(67, 56, 202, 1.0));
            }}
        """
    
    @staticmethod
    def all() -> str:
        """Tüm input stillerini birleştir"""
        return "\n".join([
            InputStyles.line_edit(),
            InputStyles.text_edit(),
            InputStyles.spin_box(),
            InputStyles.combo_box(),
            InputStyles.date_edit(),
            InputStyles.slider(),
        ])


__all__ = ['InputStyles']

