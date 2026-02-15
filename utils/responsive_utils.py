# -*- coding: utf-8 -*-
"""
Responsive Utils - GUI Responsive Design Utilities

Bu modül, GUI uygulamasının farklı ekran boyutları ve çözünürlüklerde
responsive olarak çalışmasını sağlayan yardımcı fonksiyonları içerir.

@author: merta
@date: 2025-01-28
"""

import sys
from typing import Tuple, Optional
from PyQt6.QtWidgets import (
    QSizePolicy, QSpacerItem, QApplication
)

def make_resizable(widget, horizontal=True, vertical=True):
    """
    Make a widget resizable in the specified directions.
    
    Args:
        widget: The widget to make resizable
        horizontal: Allow horizontal resizing
        vertical: Allow vertical resizing
    """
    policy = QSizePolicy(
        QSizePolicy.Policy.Expanding if horizontal else QSizePolicy.Policy.Fixed,
        QSizePolicy.Policy.Expanding if vertical else QSizePolicy.Policy.Fixed
    )
    policy.setHeightForWidth(widget.sizePolicy().hasHeightForWidth())
    widget.setSizePolicy(policy)

def create_stretch():
    """Create a stretch item for layouts."""
    return QSpacerItem(20, 40, 
                      QSizePolicy.Policy.Minimum, 
                      QSizePolicy.Policy.Expanding)

def create_horizontal_stretch():
    """Create a horizontal stretch item for layouts."""
    return QSpacerItem(40, 20, 
                      QSizePolicy.Policy.Expanding, 
                      QSizePolicy.Policy.Minimum)

def get_screen_info() -> Tuple[int, int, float, str]:
    """
    Get comprehensive screen information including resolution, DPI, and scaling.
    
    Returns:
        Tuple of (width, height, scale_factor, screen_type)
    """
    try:
        app = QApplication.instance()
        if not app:
            return 1920, 1080, 1.0, "unknown"
            
        screen = app.primaryScreen()
        if not screen:
            return 1920, 1080, 1.0, "unknown"
            
        geometry = screen.availableGeometry()
        width = geometry.width()
        height = geometry.height()
        
        # DPI scaling factor
        dpi = screen.logicalDotsPerInch()
        base_dpi = 96.0  # Windows standard DPI
        dpi_scale = dpi / base_dpi
        
        # Resolution-based scaling
        base_width, base_height = 1920, 1080
        resolution_scale = min(width / base_width, height / base_height)
        
        # Combined scale factor
        scale_factor = min(resolution_scale * dpi_scale, 2.0)  # Cap at 2x
        
        # Determine screen type
        if width < 1024:
            screen_type = "mobile"
        elif width < 1366:
            screen_type = "tablet"
        elif width < 1920:
            screen_type = "laptop"
        elif width < 2560:
            screen_type = "desktop"
        else:
            screen_type = "ultrawide"
            
        return width, height, scale_factor, screen_type
        
    except Exception:
        return 1920, 1080, 1.0, "unknown"

def scale_margins(widget, base_margin):
    """
    Scale margins based on screen resolution, DPI, and screen type.
    
    Args:
        widget: The widget to scale margins for
        base_margin: Base margin size at 1920x1080 resolution
        
    Returns:
        int: Scaled margin value
    """
    try:
        width, height, scale_factor, screen_type = get_screen_info()
        
        # Screen type specific adjustments
        type_multipliers = {
            "mobile": 0.6,
            "tablet": 0.8,
            "laptop": 1.0,
            "desktop": 1.2,
            "ultrawide": 1.4
        }
        
        type_multiplier = type_multipliers.get(screen_type, 1.0)
        scaled_margin = base_margin * scale_factor * type_multiplier
        
        # Ensure minimum and maximum values
        min_margin = max(2, int(base_margin * 0.3))
        max_margin = int(base_margin * 2.0)
        
        return max(min_margin, min(int(scaled_margin), max_margin))
        
    except Exception:
        return base_margin

def scale_font(widget, base_size):
    """
    Scale font size based on screen resolution, DPI, and screen type.
    
    Args:
        widget: The widget whose font to scale
        base_size: Base font size at 1920x1080 resolution
    """
    try:
        width, height, scale_factor, screen_type = get_screen_info()
        
        # Screen type specific font adjustments
        type_multipliers = {
            "mobile": 0.8,
            "tablet": 0.9,
            "laptop": 1.0,
            "desktop": 1.1,
            "ultrawide": 1.2
        }
        
        type_multiplier = type_multipliers.get(screen_type, 1.0)
        scaled_size = base_size * scale_factor * type_multiplier
        
        # Ensure readable font sizes
        min_size = max(8, int(base_size * 0.6))
        max_size = int(base_size * 2.0)
        final_size = max(min_size, min(int(scaled_size), max_size))
        
        font = widget.font()
        font.setPointSizeF(final_size)
        widget.setFont(font)
        
    except Exception:
        # Fallback to original behavior
        font = widget.font()
        font.setPointSizeF(base_size)
        widget.setFont(font)

def get_responsive_spacing(base_spacing: int, screen_type: Optional[str] = None) -> int:
    """
    Get responsive spacing value based on screen type.
    
    Args:
        base_spacing: Base spacing value
        screen_type: Optional screen type override
        
    Returns:
        int: Responsive spacing value
    """
    try:
        if screen_type is None:
            _, _, _, screen_type = get_screen_info()
            
        type_multipliers = {
            "mobile": 0.6,
            "tablet": 0.8,
            "laptop": 1.0,
            "desktop": 1.2,
            "ultrawide": 1.4
        }
        
        multiplier = type_multipliers.get(screen_type, 1.0)
        return max(2, int(base_spacing * multiplier))
        
    except Exception:
        return base_spacing

def get_responsive_font_size(base_size: int, screen_type: Optional[str] = None) -> int:
    """
    Get responsive font size based on screen type.
    
    Args:
        base_size: Base font size
        screen_type: Optional screen type override
        
    Returns:
        int: Responsive font size
    """
    try:
        if screen_type is None:
            _, _, scale_factor, screen_type = get_screen_info()
        else:
            _, _, scale_factor, _ = get_screen_info()
            
        type_multipliers = {
            "mobile": 0.8,
            "tablet": 0.9,
            "laptop": 1.0,
            "desktop": 1.1,
            "ultrawide": 1.2
        }
        
        multiplier = type_multipliers.get(screen_type, 1.0)
        scaled_size = base_size * scale_factor * multiplier
        
        return max(8, min(int(scaled_size), int(base_size * 2.0)))
        
    except Exception:
        return base_size

def apply_responsive_layout(widget, base_margins=(16, 16, 16, 16), base_spacing=8):
    """
    Apply responsive layout settings to a widget.
    
    Args:
        widget: Widget to apply responsive settings to
        base_margins: Base margins (left, top, right, bottom)
        base_spacing: Base spacing value
    """
    try:
        width, height, scale_factor, screen_type = get_screen_info()
        
        # Scale margins
        scaled_margins = tuple(scale_margins(widget, margin) for margin in base_margins)
        scaled_spacing = get_responsive_spacing(base_spacing, screen_type)
        
        # Apply to layout if it exists
        if hasattr(widget, 'layout') and widget.layout():
            widget.layout().setContentsMargins(*scaled_margins)
            widget.layout().setSpacing(scaled_spacing)
            
    except Exception:
        pass  # Silent error handling
