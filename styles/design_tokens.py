# -*- coding: utf-8 -*-
"""
PEMF GUI Design Tokens
Merkezi tasarım değişkenleri ve token sistemi
"""

from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class ColorToken:
    """Renk token'ı"""
    hex: str
    rgb: Tuple[int, int, int]
    rgba: str
    
    @classmethod
    def from_hex(cls, hex_color: str, alpha: float = 1.0):
        """Hex renkten ColorToken oluştur"""
        hex_color = hex_color.lstrip('#')
        r, g, b = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        rgba = f"rgba({r}, {g}, {b}, {alpha})"
        return cls(hex=f"#{hex_color}", rgb=(r, g, b), rgba=rgba)


class DesignTokens:
    """
    PEMF GUI Design Tokens
    Tüm tasarım değişkenlerinin merkezi tanımı
    """
    
    # ==================== COLORS ====================
    
    # Primary Colors (Mor/Purple theme)
    PRIMARY = ColorToken.from_hex("#8e44ad")
    PRIMARY_DARK = ColorToken.from_hex("#7c3aed")
    PRIMARY_LIGHT = ColorToken.from_hex("#9b59b6")
    PRIMARY_LIGHTER = ColorToken.from_hex("#a569bd")
    PRIMARY_DARKER = ColorToken.from_hex("#7d3c98")
    
    # Secondary Colors
    SECONDARY = ColorToken.from_hex("#6c2b8f")
    SECONDARY_LIGHT = ColorToken.from_hex("#9b59b6")
    SECONDARY_DARK = ColorToken.from_hex("#5d2473")
    
    # Accent Colors
    ACCENT = ColorToken.from_hex("#c39bd3")
    ACCENT_LIGHT = ColorToken.from_hex("#d5b7d5")
    ACCENT_DARK = ColorToken.from_hex("#a569bd")
    
    # Semantic Colors
    SUCCESS = ColorToken.from_hex("#22c55e")
    SUCCESS_DARK = ColorToken.from_hex("#15803d")
    WARNING = ColorToken.from_hex("#f59e0b")
    WARNING_DARK = ColorToken.from_hex("#d97706")
    ERROR = ColorToken.from_hex("#ef4444")
    ERROR_DARK = ColorToken.from_hex("#b91c1c")
    INFO = ColorToken.from_hex("#3b82f6")
    INFO_DARK = ColorToken.from_hex("#1e40af")
    
    # Neutral Colors
    WHITE = ColorToken.from_hex("#ffffff")
    BLACK = ColorToken.from_hex("#000000")
    GRAY_50 = ColorToken.from_hex("#f8fafc")
    GRAY_100 = ColorToken.from_hex("#f1f5f9")
    GRAY_200 = ColorToken.from_hex("#e2e8f0")
    GRAY_300 = ColorToken.from_hex("#cbd5e1")
    GRAY_400 = ColorToken.from_hex("#94a3b8")
    GRAY_500 = ColorToken.from_hex("#64748b")
    GRAY_600 = ColorToken.from_hex("#475569")
    GRAY_700 = ColorToken.from_hex("#334155")
    GRAY_800 = ColorToken.from_hex("#1e293b")
    GRAY_900 = ColorToken.from_hex("#0f172a")
    
    # Dark Theme Background Colors
    BG_DARK_PRIMARY = ColorToken.from_hex("#1a1a2e")
    BG_DARK_SECONDARY = ColorToken.from_hex("#16213e")
    BG_DARK_TERTIARY = ColorToken.from_hex("#2d185a")
    BG_DARK_QUATERNARY = ColorToken.from_hex("#1e1b4b")
    
    # ==================== GRADIENTS ====================
    
    GRADIENT_PRIMARY = "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #2d185a, stop:1 #6c2b8f)"
    GRADIENT_SECONDARY = "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #1a1a2e, stop:1 #16213e)"
    GRADIENT_TERTIARY = "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #1e1b4b, stop:1 #4c1d95)"
    GRADIENT_BUTTON_PRIMARY = "qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(99, 102, 241, 0.8), stop:1 rgba(67, 56, 202, 0.8))"
    GRADIENT_BUTTON_SUCCESS = "qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(34, 197, 94, 0.8), stop:1 rgba(21, 128, 61, 0.8))"
    GRADIENT_BUTTON_DANGER = "qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(239, 68, 68, 0.8), stop:1 rgba(185, 28, 28, 0.8))"
    GRADIENT_LIGHT = "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #f4ecf7, stop:0.3 #e8daef, stop:0.7 #d5b7d5, stop:1 #c39bd3)"
    
    # ==================== TYPOGRAPHY ====================
    
    # Font Families
    FONT_FAMILY_PRIMARY = "'Segoe UI', Arial, sans-serif"
    FONT_FAMILY_SECONDARY = "'Segoe UI', 'Roboto', 'Helvetica Neue', Arial, sans-serif"
    FONT_FAMILY_MONOSPACE = "'Consolas', 'Monaco', 'Courier New', monospace"
    
    # Font Sizes (px)
    FONT_SIZE_XS = 10
    FONT_SIZE_SM = 12
    FONT_SIZE_BASE = 13
    FONT_SIZE_MD = 14
    FONT_SIZE_LG = 16
    FONT_SIZE_XL = 18
    FONT_SIZE_2XL = 20
    FONT_SIZE_3XL = 24
    FONT_SIZE_4XL = 28
    FONT_SIZE_5XL = 32
    
    # Font Weights
    FONT_WEIGHT_NORMAL = 400
    FONT_WEIGHT_MEDIUM = 500
    FONT_WEIGHT_SEMIBOLD = 600
    FONT_WEIGHT_BOLD = 700
    FONT_WEIGHT_EXTRABOLD = 800
    
    # Line Heights
    LINE_HEIGHT_TIGHT = 1.2
    LINE_HEIGHT_NORMAL = 1.5
    LINE_HEIGHT_RELAXED = 1.6
    LINE_HEIGHT_LOOSE = 2.0
    
    # ==================== SPACING ====================
    
    # Spacing Scale (4px grid system)
    SPACE_0 = 0
    SPACE_1 = 4
    SPACE_2 = 8
    SPACE_3 = 12
    SPACE_4 = 16
    SPACE_5 = 20
    SPACE_6 = 24
    SPACE_7 = 28
    SPACE_8 = 32
    SPACE_10 = 40
    SPACE_12 = 48
    SPACE_16 = 64
    SPACE_20 = 80
    SPACE_24 = 96
    
    # ==================== BORDER RADIUS ====================
    
    RADIUS_NONE = 0
    RADIUS_SM = 4
    RADIUS_BASE = 6
    RADIUS_MD = 8
    RADIUS_LG = 12
    RADIUS_XL = 16
    RADIUS_2XL = 20
    RADIUS_FULL = 9999
    
    # ==================== SHADOWS ====================
    
    SHADOW_NONE = "none"
    SHADOW_SM = "0 1px 2px rgba(0, 0, 0, 0.05)"
    SHADOW_BASE = "0 4px 6px rgba(0, 0, 0, 0.1)"
    SHADOW_MD = "0 8px 25px rgba(0, 0, 0, 0.15)"
    SHADOW_LG = "0 15px 35px rgba(0, 0, 0, 0.2)"
    SHADOW_XL = "0 20px 50px rgba(0, 0, 0, 0.25)"
    SHADOW_INNER = "inset 0 2px 4px rgba(0, 0, 0, 0.06)"
    
    # ==================== TRANSITIONS ====================
    
    TRANSITION_FAST = "0.15s"
    TRANSITION_BASE = "0.3s"
    TRANSITION_SLOW = "0.5s"
    TRANSITION_SLOWER = "0.7s"
    
    EASING_LINEAR = "linear"
    EASING_EASE = "ease"
    EASING_EASE_IN = "ease-in"
    EASING_EASE_OUT = "ease-out"
    EASING_EASE_IN_OUT = "ease-in-out"
    EASING_CUBIC = "cubic-bezier(0.4, 0, 0.2, 1)"
    
    # ==================== Z-INDEX ====================
    
    Z_INDEX_DROPDOWN = 1000
    Z_INDEX_STICKY = 1020
    Z_INDEX_FIXED = 1030
    Z_INDEX_MODAL_BACKDROP = 1040
    Z_INDEX_MODAL = 1050
    Z_INDEX_POPOVER = 1060
    Z_INDEX_TOOLTIP = 1070
    Z_INDEX_NOTIFICATION = 9999
    
    # ==================== OPACITY ====================
    
    OPACITY_0 = 0.0
    OPACITY_5 = 0.05
    OPACITY_10 = 0.1
    OPACITY_15 = 0.15
    OPACITY_20 = 0.2
    OPACITY_25 = 0.25
    OPACITY_30 = 0.3
    OPACITY_40 = 0.4
    OPACITY_50 = 0.5
    OPACITY_60 = 0.6
    OPACITY_70 = 0.7
    OPACITY_75 = 0.75
    OPACITY_80 = 0.8
    OPACITY_90 = 0.9
    OPACITY_95 = 0.95
    OPACITY_100 = 1.0
    
    # ==================== HELPER METHODS ====================
    
    @staticmethod
    def rgba(color: ColorToken, alpha: float) -> str:
        """Renk token'ından RGBA string oluştur"""
        r, g, b = color.rgb
        return f"rgba({r}, {g}, {b}, {alpha})"
    
    @staticmethod
    def get_spacing(multiplier: int) -> int:
        """Spacing değeri al (4px grid system)"""
        return 4 * multiplier
    
    @staticmethod
    def transition(duration: str, easing: str = None) -> str:
        """Transition string oluştur"""
        easing = easing or DesignTokens.EASING_CUBIC
        return f"all {duration} {easing}"


# Convenience aliases
DT = DesignTokens


# Export all
__all__ = ['DesignTokens', 'DT', 'ColorToken']

