"""
PEMF GUI Application

This package contains the main GUI application for the PEMF (Pulsed Electromagnetic Field) system.
"""

import os
import sys
from pathlib import Path

from utils.path_utils import resource_path

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
