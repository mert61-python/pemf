"""
PEMF GUI Application

This package contains the main GUI application for the PEMF (Pulsed Electromagnetic Field) system.
"""

import os
import sys
from pathlib import Path

def resource_path(relative_path):
    """Get the absolute path to a resource file.
    
    Works for development and for PyInstaller one-file mode.
    
    Args:
        relative_path: Relative path to the resource file
        
    Returns:
        str: Absolute path to the resource file
    """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = Path(sys._MEIPASS)
    except AttributeError:
        # Not running in a PyInstaller bundle, use the script's directory
        base_path = Path(__file__).resolve().parent
    
    # Get the absolute path to the resource
    path = base_path / relative_path
    
    # For development, try to find the file in the package directory
    if not path.exists():
        # Get the directory of the current module
        base_dir = Path(__file__).resolve().parent
        path = base_dir / relative_path
    
    return str(path)

def get_icon_path(icon_name):
    """Get the full path to an icon file."""
    return resource_path(os.path.join("resources", "icons", icon_name))

def get_style_path(style_name):
    """Get the full path to a style file."""
    return resource_path(os.path.join("resources", "styles", style_name))

def get_template_path(template_name):
    """Get the full path to a template file."""
    return resource_path(os.path.join("resources", "templates", template_name))

def get_image_path(image_name):
    """Get the full path to an image file."""
    return resource_path(os.path.join("resources", "images", image_name))
