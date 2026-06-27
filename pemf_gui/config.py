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
        'mqtt.cloud_broker.username',
        'mqtt.cloud_broker.password',
        'mqtt.cloud_broker.tls_cert_sha256',
        'email.password',
        'email.gmail_password',
        'api.key',
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
        self._legacy_cipher = self._get_legacy_cipher()  # eski MAC-türevli anahtar (yalnız decrypt fallback)
        
        # Default configuration
        self.default_config = {
            'serial': {
                'port': 'COM13',
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
        # At-rest güvenlik (audit P2): _ENCRYPTED_KEYS listesindeki ama config.json'da hâlâ
        # DÜZ-METİN duran sırları (Gmail App Password, MQTT/email/api creds) bir kereye mahsus
        # şifrele. Eskiden bu değerler düz-metin hardcoded duruyordu.
        self._migrate_plaintext_secrets()

    def _get_or_create_key(self) -> bytes:
        """Birincil şifreleme anahtarı: keyring'de RASTGELE (yüksek entropi, MAC'ten bağımsız → ağ
        kartı/makine değişse bile stabil). Keyring yoksa .pemf_key_v2 dosyası fallback. Eski
        MAC-türevli anahtar artık BİRİNCİL DEĞİL (yalnız _get_legacy_cipher ile decrypt fallback)."""
        service, name = "PEMF_GUI", "patient_fernet_key"
        kr = None
        try:
            import keyring as kr  # type: ignore
        except Exception:
            kr = None
        if kr is not None:
            try:
                k = kr.get_password(service, name)
                if k:
                    return k.encode()
            except Exception:
                pass
        key_file_v2 = os.path.join(self.config_dir, '.pemf_key_v2')
        if os.path.exists(key_file_v2):
            try:
                with open(key_file_v2, 'rb') as f:
                    k = f.read().strip()
                if k:
                    return k
            except Exception:
                pass
        new_key = Fernet.generate_key()
        stored = False
        if kr is not None:
            try:
                kr.set_password(service, name, new_key.decode())
                stored = True
            except Exception:
                pass
        if not stored:
            try:
                with open(key_file_v2, 'wb') as f:
                    f.write(new_key)
                try:
                    os.chmod(key_file_v2, 0o600)
                except Exception:
                    pass
            except Exception:
                pass
        logger.info("Yeni RASTGELE Fernet anahtari uretildi (keyring=%s).", stored)
        return new_key

    def _get_legacy_cipher(self):
        """Eski MAC-türevli (veya .pemf_key) anahtar — yalnız ESKİ kayıtları çözmek için. Yoksa None."""
        try:
            legacy_key = None
            key_file = os.path.join(self.config_dir, '.pemf_key')
            if os.path.exists(key_file):
                with open(key_file, 'rb') as f:
                    legacy_key = f.read().strip()
            if not legacy_key:
                import uuid
                machine_id = str(uuid.getnode()).encode()
                legacy_key = base64.urlsafe_b64encode(hashlib.sha256(machine_id).digest())
            return Fernet(legacy_key)
        except Exception:
            return None
    
    def _encrypt_value(self, value: str) -> str:
        """Encrypt sensitive value"""
        if not value:
            return value
        encrypted = self._cipher.encrypt(value.encode())
        return base64.urlsafe_b64encode(encrypted).decode()
    
    def _decrypt_value(self, encrypted_value: str) -> str:
        """Decrypt: önce BİRİNCİL (rastgele) anahtar, sonra ESKİ MAC-türevli (geriye dönük).
        İkisi de başarısızsa ham değeri döndürür (üst katman maskeleyebilir)."""
        if not encrypted_value:
            return encrypted_value
        try:
            encrypted_bytes = base64.urlsafe_b64decode(encrypted_value.encode())
        except Exception:
            return encrypted_value
        try:
            return self._cipher.decrypt(encrypted_bytes).decode()
        except Exception:
            pass
        legacy = getattr(self, "_legacy_cipher", None)
        if legacy is not None:
            try:
                return legacy.decrypt(encrypted_bytes).decode()
            except Exception:
                pass
        logger.error("Decryption failed (birincil + legacy anahtar)")
        return encrypted_value
    
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

    def _raw_get(self, key: str):
        """Ham (decrypt edilmemiş) değeri döndürür — düz-metin/şifreli (enc:) ayrımı için."""
        node = self.config
        for k in key.split('.'):
            if not isinstance(node, dict) or k not in node:
                return None
            node = node[k]
        return node

    def _migrate_plaintext_secrets(self) -> None:
        """_ENCRYPTED_KEYS'te olup config.json'da hâlâ DÜZ-METİN (enc: öneksiz) duran sırları
        at-rest şifrele (audit P2). Şifreleme mekanizması öncesi yazılmış / elle girilmiş
        değerleri tek seferde korur; enc: önekli olanlara dokunmaz."""
        changed = False
        for dotted in self._ENCRYPTED_KEYS:
            raw = self._raw_get(dotted)
            if isinstance(raw, str) and raw and not raw.startswith('enc:'):
                try:
                    self.set(dotted, raw, save=False)  # set() enc: önekli şifreli değere çevirir
                    changed = True
                except Exception:
                    pass
        if changed:
            try:
                self.save()
                logger.info("At-rest: config.json'daki duz-metin sirlar sifrelendi (audit P2).")
            except Exception:
                pass

# Global config instance
config = ConfigManager()

def get_config() -> ConfigManager:
    """Get the global configuration instance."""
    return config
