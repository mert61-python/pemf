"""
Configuration management for the PEMF GUI application.
Handles loading/saving settings including serial port configuration.
"""

import json
import os
import logging
from typing import Dict, Any
from cryptography.fernet import Fernet
import base64
import hashlib

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Create console handler with a higher log level
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)

# Create formatter and add it to the handlers
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
ch.setFormatter(formatter)

# Add the handlers to the logger
if not logger.handlers:  # Avoid adding handlers multiple times
    logger.addHandler(ch)

class ConfigManager:
    # CRITICAL FIX: Sensitive config keys to encrypt
    _ENCRYPTED_KEYS = {
        'mqtt.user',
        'mqtt.pass',
        'email.password',
        'api.key',
        'mqtt.cloud_broker.tls_cert_sha256',
    }
    
    def __init__(self, config_file: str = None):
        """Initialize the configuration manager.
        
        Args:
            config_file: Path to the configuration file. If None, uses default location.
        """
        if config_file is None:
            # Default config location: user's app data directory
            self.config_dir = os.path.join(os.path.expanduser('~'), '.pemf_gui')
            os.makedirs(self.config_dir, exist_ok=True)
            self.config_file = os.path.join(self.config_dir, 'config.json')
        else:
            self.config_file = config_file
            self.config_dir = os.path.dirname(config_file)
        
        # CRITICAL FIX: Initialize encryption
        self._encryption_key = self._get_or_create_key()
        self._cipher = Fernet(self._encryption_key)
        
        # Default configuration
        self.default_config = {
            'serial': {
                'port': '',  # Auto-detect if empty
                'baudrate': 115200,
                'timeout': 1.0,
                'emulation_mode': False,  # Run without hardware
                'auto_connect': True,     # Try to auto-connect on startup
            },
            'recent_files': [],
            'window_geometry': None,
            'window_state': None,
        }
        
        self.config = self.default_config.copy()
        self.load()
    
    def _get_or_create_key(self) -> bytes:
        """Get or create encryption key (machine-specific)"""
        key_file = os.path.join(self.config_dir, '.pemf_key')
        
        if os.path.exists(key_file):
            with open(key_file, 'rb') as f:
                return f.read()
        
        # Generate machine-specific key
        import uuid
        machine_id = str(uuid.getnode()).encode()
        key = base64.urlsafe_b64encode(hashlib.sha256(machine_id).digest())
        
        # Save key (restricted permissions)
        with open(key_file, 'wb') as f:
            f.write(key)
        
        # Restrict file permissions (Windows/Unix compatible)
        try:
            os.chmod(key_file, 0o600)
        except Exception:
            pass
        
        logger.info("Generated new encryption key")
        return key
    
    def _encrypt_value(self, value: str) -> str:
        """Encrypt sensitive value"""
        if not value:
            return value
        encrypted = self._cipher.encrypt(value.encode())
        return base64.urlsafe_b64encode(encrypted).decode()
    
    def _decrypt_value(self, encrypted_value: str) -> str:
        """Decrypt sensitive value"""
        if not encrypted_value:
            return encrypted_value
        try:
            encrypted_bytes = base64.urlsafe_b64decode(encrypted_value.encode())
            decrypted = self._cipher.decrypt(encrypted_bytes)
            return decrypted.decode()
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            return encrypted_value  # Return as-is if decryption fails
    
    def load(self) -> Dict[str, Any]:
        """Load configuration from file."""
        try:
            if os.path.exists(self.config_file):
                logger.debug(f"Loading configuration from {self.config_file}")
                with open(self.config_file, 'r') as f:
                    loaded = json.load(f)
                    self._merge_config(loaded)
                logger.info("Configuration loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load configuration: {e}")
            self.config = self.default_config.copy()
        
        return self.config
    
    def save(self) -> None:
        """Save current configuration to file."""
        try:
            # Ensure config directory exists
            os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
            
            logger.debug(f"Saving configuration to {self.config_file}")
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=4)
            logger.info("Configuration saved successfully")
            
        except Exception as e:
            logger.error(f"Failed to save configuration: {e}")
            raise
        
    def _merge_config(self, new_config: Dict[str, Any]) -> None:
        """Merge new configuration with existing one."""
        def merge(dest, source):
            for key, value in source.items():
                if key in dest and isinstance(dest[key], dict) and isinstance(value, dict):
                    merge(dest[key], value)
                else:
                    dest[key] = value
        
        merge(self.config, new_config)
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value using dot notation (auto-decrypt if encrypted)."""
        keys = key.split('.')
        value = self.config
        
        try:
            for k in keys:
                value = value[k]
            
            # CRITICAL FIX: Decrypt if sensitive key
            if key in self._ENCRYPTED_KEYS and isinstance(value, str):
                # Check if value is encrypted (starts with encryption marker)
                if value.startswith('enc:'):
                    return self._decrypt_value(value[4:])  # Remove 'enc:' prefix
            
            return value
        except (KeyError, TypeError):
            return default
    
    def set(self, key: str, value: Any, save: bool = True) -> None:
        """Set a configuration value using dot notation (auto-encrypt if sensitive)."""
        keys = key.split('.')
        config = self.config
        
        # Navigate to the parent dict
        for k in keys[:-1]:
            if k not in config or not isinstance(config[k], dict):
                config[k] = {}
            config = config[k]
        
        # CRITICAL FIX: Encrypt if sensitive key
        if key in self._ENCRYPTED_KEYS and isinstance(value, str) and value:
            value = 'enc:' + self._encrypt_value(value)  # Add 'enc:' prefix
        
        # Set the value
        config[keys[-1]] = value
        
        if save:
            self.save()

# Global config instance
config = ConfigManager()

def get_config() -> ConfigManager:
    """Get the global configuration instance."""
    return config
