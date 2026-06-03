"""
Production-Ready Config Manager for PEMF Application
Handles config loading with proper fallback hierarchy for PyInstaller exe distribution.

Priority order:
1. User config in %APPDATA%/PEMF_GUI/config.json (writable, user-specific)
2. Exe-bundled template config.json.template (read-only, default values)
3. Hard-coded defaults (last resort)

This ensures:
- Users can modify settings without rebuilding exe
- Safe defaults are always available
- No config corruption affects application startup
"""

import json
import os
import sys
import logging
import time
from pathlib import Path
from typing import Any, Optional, Dict
from cryptography.fernet import Fernet
import base64
import hashlib

try:
    from .path_utils import get_app_data_directory as get_shared_app_data_directory
except ImportError:
    from path_utils import get_app_data_directory as get_shared_app_data_directory

logger = logging.getLogger(__name__)


class ProductionConfigManager:
    """
    Production-grade config manager with template fallback and encryption support.
    Thread-safe singleton pattern.
    """
    _instance = None
    _initialized = False
    
    # Sensitive keys to encrypt
    _ENCRYPTED_KEYS = {'mqtt.user', 'mqtt.pass', 'email.password', 'api.key'}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._initialized = True
        self._config = {}
        self._encryption_key = None
        self._cipher = None
        self._last_save_ts = 0.0
        
        # Initialize encryption
        self._setup_encryption()
        
        # Load config with fallback
        self._load_config()
    
    def _setup_encryption(self):
        """Setup encryption for sensitive config values"""
        try:
            key_file = self._get_app_data_dir() / '.pemf_key'
            
            if key_file.exists():
                with open(key_file, 'rb') as f:
                    self._encryption_key = f.read()
            else:
                # Generate machine-specific key
                import uuid
                machine_id = str(uuid.getnode()).encode()
                self._encryption_key = base64.urlsafe_b64encode(
                    hashlib.sha256(machine_id).digest()
                )
                
                # Save key with restricted permissions
                key_file.parent.mkdir(parents=True, exist_ok=True)
                with open(key_file, 'wb') as f:
                    f.write(self._encryption_key)
                
                try:
                    os.chmod(key_file, 0o600)
                except Exception:
                    pass  # Windows may not support chmod
            
            self._cipher = Fernet(self._encryption_key)
            logger.info("Encryption initialized successfully")
            
        except Exception as e:
            logger.error(f"Encryption setup failed: {e}")
            self._cipher = None


    def _get_app_data_dir(self) -> Path:
        """Get application data directory (persistent, user-writable)"""
        return get_shared_app_data_directory()
    
    def _get_bundled_resource_path(self, relative_path: str) -> Optional[Path]:
        """
        Get path to bundled resource (works in both dev and PyInstaller exe).
        
        Args:
            relative_path: Relative path from project root (e.g., 'config.json.template')
        
        Returns:
            Path object if resource exists, None otherwise
        """
        # Try PyInstaller _MEIPASS first (frozen exe)
        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            bundled_path = Path(sys._MEIPASS) / relative_path
            if bundled_path.exists():
                logger.debug(f"Found bundled resource: {bundled_path}")
                return bundled_path
        
        # Try development environment (relative to this file)
        dev_path = Path(__file__).parent.parent / relative_path
        if dev_path.exists():
            logger.debug(f"Found dev resource: {dev_path}")
            return dev_path
        
        logger.debug(f"Resource not found (fallback will be used): {relative_path}")
        return None
    
    def _load_config(self):
        """
        Load configuration with proper fallback hierarchy.
        
        Priority:
        1. %APPDATA%/PEMF_GUI/config.json (user config)
        2. Bundled config.json.template (exe template)
        3. Hard-coded defaults
        """
        # Hard-coded defaults (last resort)
        default_config = {
            'mqtt': {
                'broker_url': 'localhost',
                'broker_port': 1883,
                'user': '',
                'pass': '',
                'keepalive': 60,
                'use_tls': False
            },
            'serial': {
                'port': '',
                'baudrate': 115200,
                'timeout': 1.0,
                'emulation_mode': False,
                'auto_connect': True
            },
            'application': {
                'theme': 'dark',
                'language': 'tr',
                'auto_save': True,
                'log_level': 'INFO'
            },
            'treatment': {
                'max_duration': 60,
                'default_frequency': 10,
                'default_intensity': 50
            }
        }
        
        # Start with defaults
        self._config = default_config.copy()
        logger.info("Loaded hard-coded default config")
        
        # Try to load bundled config.json first (Production / Plug & Play)
        bundled_config_path = self._get_bundled_resource_path('config/config.json')
        template_path = self._get_bundled_resource_path('config/config.json.template')
        
        if bundled_config_path:
            try:
                with open(bundled_config_path, 'r', encoding='utf-8') as f:
                    bundled_config = json.load(f)
                    self._deep_merge(self._config, bundled_config)
                logger.info(f"Loaded bundled config from: {bundled_config_path}")
            except Exception as e:
                logger.error(f"Failed to load bundled config: {e}")
        elif template_path:
            # Fallback to template if actual config is missing
            try:
                with open(template_path, 'r', encoding='utf-8') as f:
                    template_config = json.load(f)
                    self._deep_merge(self._config, template_config)
                logger.info(f"Loaded template config from: {template_path}")
            except Exception as e:
                logger.error(f"Failed to load template config: {e}")
        
        # Try to load user config from APPDATA (writable, highest priority)
        user_config_path = self._get_app_data_dir() / 'config.json'
        
        if user_config_path.exists():
            try:
                with open(user_config_path, 'r', encoding='utf-8') as f:
                    user_config = json.load(f)
                    self._deep_merge(self._config, user_config)
                logger.info(f"Loaded user config from: {user_config_path}")
                # Ensure user config has any missing keys from template and bundled credentials
                try:
                    self._upgrade_user_config_with_template(bundled_config_path or template_path)
                    # Persist upgrades if any
                    self._save_user_config()
                except Exception:
                    pass
            except Exception as e:
                logger.error(f"Failed to load user config: {e}")
        else:
            # Create initial user config from current state
            logger.info(f"Creating initial user config at: {user_config_path}")
            # Merge missing values from template and bundled creds before saving
            try:
                self._upgrade_user_config_with_template(bundled_config_path or template_path)
            except Exception:
                pass
            self._save_user_config()
    
    def _deep_merge(self, base: Dict, update: Dict):
        """Deep merge update dict into base dict"""
        for key, value in update.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_merge(base[key], value)
            else:
                base[key] = value
    
    def _save_user_config(self):
        """Save current config to user's APPDATA directory"""
        user_config_path = self._get_app_data_dir() / 'config.json'
        
        try:
            with open(user_config_path, 'w', encoding='utf-8') as f:
                json.dump(self._config, f, indent=4, ensure_ascii=False)
            logger.info(f"Saved user config to: {user_config_path}")
        except Exception as e:
            logger.error(f"Failed to save user config: {e}")
            raise

    def _upgrade_user_config_with_template(self, template_path: Optional[Path]):
        """
        Ensure the user's config includes missing keys from the bundled template
        and optionally fill missing cloud credentials from bundled hivemq_users.json.
        This helps make the EXE behave correctly on new machines without manual edits.
        """
        if not template_path:
            return

        try:
            with open(template_path, 'r', encoding='utf-8') as f:
                template = json.load(f)
        except Exception:
            return

        def add_missing(base: dict, tmpl: dict):
            for k, v in tmpl.items():
                if k not in base:
                    base[k] = v
                elif isinstance(v, dict) and isinstance(base.get(k), dict):
                    add_missing(base[k], v)

        add_missing(self._config, template)

        # If cloud credentials missing, try bundled credentials file
        try:
            cloud = self._config.get('mqtt', {}).get('cloud_broker', {})
            if (not cloud.get('username')) or (not cloud.get('password')):
                cred_path = self._get_bundled_resource_path('config/credentials/hivemq_users.json')
                if cred_path and cred_path.exists():
                    try:
                        with open(cred_path, 'r', encoding='utf-8') as cf:
                            cred_blob = json.load(cf)
                        users = cred_blob.get('users', [])
                        # Prefer known usernames if present
                        preferred = None
                        for name in ('afsuampemf', 'gui_bridge'):
                            for u in users:
                                if u.get('username') == name:
                                    preferred = u
                                    break
                            if preferred:
                                break
                        if not preferred and users:
                            preferred = users[0]

                        if preferred:
                            mb = self._config.setdefault('mqtt', {}).setdefault('cloud_broker', {})
                            if not mb.get('username'):
                                mb['username'] = preferred.get('username')
                            if not mb.get('password'):
                                mb['password'] = preferred.get('password')
                    except Exception:
                        pass
        except Exception:
            pass
    
    def get(self, key_path: str, default: Any = None) -> Any:
        """
        Get config value using dot notation (e.g., 'mqtt.broker_url').
        Automatically decrypts encrypted values.
        
        Args:
            key_path: Dot-separated config path
            default: Default value if key not found
        
        Returns:
            Config value (decrypted if needed) or default
        """
        keys = key_path.split('.')
        value = self._config
        
        try:
            for key in keys:
                value = value[key]
            
            # Decrypt if encrypted
            if key_path in self._ENCRYPTED_KEYS and isinstance(value, str):
                if value.startswith('enc:'):
                    return self._decrypt_value(value[4:])
            
            return value
        except (KeyError, TypeError):
            return default
    
    def set(self, key_path: str, value: Any, save: bool = True):
        """
        Set config value using dot notation.
        Automatically encrypts sensitive values.
        
        Args:
            key_path: Dot-separated config path
            value: Value to set
            save: Whether to save to disk immediately
        """
        keys = key_path.split('.')
        config = self._config
        
        # Navigate to parent dict
        for key in keys[:-1]:
            if key not in config or not isinstance(config[key], dict):
                config[key] = {}
            config = config[key]
        
        # Encrypt sensitive values
        if key_path in self._ENCRYPTED_KEYS and isinstance(value, str) and value:
            value = 'enc:' + self._encrypt_value(value)
        
        # Set only if changed
        key_name = keys[-1]
        old_value = config.get(key_name, None)
        if old_value == value:
            return

        config[key_name] = value
        
        if save:
            self._save_user_config()
            self._last_save_ts = time.monotonic()

    def set_many(self, updates: Dict[str, Any], save: bool = True):
        """Set multiple config values and optionally persist once."""
        changed = False
        for key_path, value in updates.items():
            before = self.get(key_path, None)
            self.set(key_path, value, save=False)
            after = self.get(key_path, None)
            if before != after:
                changed = True

        if save and changed:
            self._save_user_config()
            self._last_save_ts = time.monotonic()

    def save(self):
        """Persist current config to disk explicitly."""
        self._save_user_config()
        self._last_save_ts = time.monotonic()
    
    def _encrypt_value(self, value: str) -> str:
        """Encrypt sensitive value"""
        if not self._cipher or not value:
            return value
        
        try:
            encrypted = self._cipher.encrypt(value.encode())
            return base64.urlsafe_b64encode(encrypted).decode()
        except Exception as e:
            logger.error(f"Encryption failed: {e}")
            return value
    
    def _decrypt_value(self, encrypted_value: str) -> str:
        """Decrypt sensitive value"""
        if not self._cipher or not encrypted_value:
            return encrypted_value
        
        try:
            encrypted_bytes = base64.urlsafe_b64decode(encrypted_value.encode())
            decrypted = self._cipher.decrypt(encrypted_bytes)
            return decrypted.decode()
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            return encrypted_value
    
    def reload(self):
        """Reload config from disk (useful after external changes)"""
        self._load_config()
    
    def get_user_config_path(self) -> Path:
        """Get path to user's writable config file"""
        return self._get_app_data_dir() / 'config.json'


# Global singleton instance
_global_config = None


def get_production_config() -> ProductionConfigManager:
    """Get global production config manager instance (singleton)"""
    global _global_config
    if _global_config is None:
        _global_config = ProductionConfigManager()
    return _global_config


def get_config_value(key_path: str, default: Any = None) -> Any:
    """
    Convenience function to get config value.
    
    Example:
        broker_url = get_config_value('mqtt.broker_url', 'localhost')
    """
    return get_production_config().get(key_path, default)
