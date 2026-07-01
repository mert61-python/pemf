# PyInstaller runtime hook for numpy
# Fixes circular import typing<->numpy.typing issue in frozen mode

import sys
import os

# Ensure typing module is fully initialized BEFORE numpy.typing tries to import from it
if getattr(sys, 'frozen', False):
    # Pre-import typing to avoid circular import with numpy.typing
    import typing
    from typing import NamedTuple, Any
    
    # We're running in a PyInstaller bundle
    bundle_dir = sys._MEIPASS
    
    # Add numpy paths to sys.path
    numpy_path = os.path.join(bundle_dir, 'numpy')
    if os.path.exists(numpy_path) and numpy_path not in sys.path:
        sys.path.insert(0, numpy_path)
    
    # Set environment variable to help numpy find its libraries
    os.environ['NUMPY_EXPERIMENTAL_ARRAY_FUNCTION'] = '0'
