"""
DEPRECATED: Use production_config_manager.py instead.
This module is kept for backward compatibility only.
"""

import threading
from typing import Any

# Import new production config manager
from .production_config_manager import get_production_config

class ConfigManager:
    """
    DEPRECATED: Legacy ConfigManager for backward compatibility.
    New code should use production_config_manager.ProductionConfigManager.
    
    This wrapper redirects all calls to the new production config manager.
    """
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._production_config = get_production_config()
        
    def get(self, key_path: str, default: Any = None) -> Any:
        """
        DEPRECATED: Use production_config_manager instead.
        Retrieves a configuration value using dot notation.
        """
        return self._production_config.get(key_path, default)

# Global convenience function
def get_config(key_path: str, default: Any = None) -> Any:
    """
    DEPRECATED: Use production_config_manager.get_config_value() instead.
    """
    return ConfigManager().get(key_path, default)
