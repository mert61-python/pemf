"""
PEMF GUI Application

This package contains the main GUI application for the PEMF (Pulsed Electromagnetic Field) system.
"""

import os

from utils.path_utils import resource_path


def get_icon_path(icon_name):
    """Get the full path to an icon file."""
    return resource_path(os.path.join("resources", "icons", icon_name))
