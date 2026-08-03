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

import base64
import copy
import hashlib
import json
import logging
import threading
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

from cryptography.fernet import Fernet

try:
    from .path_utils import get_app_data_directory as get_shared_app_data_directory
except ImportError:
    from path_utils import get_app_data_directory as get_shared_app_data_directory

logger = logging.getLogger(__name__)

# DENETIM P3: config.json yazimini serilestiren surec-geneli kilit (atomik replace ile birlikte).
_SAVE_LOCK = threading.Lock()


# Gömülü varsayılan config (son çare). Kullanım öncesi copy.deepcopy'lenir — iç içe dict'ler
# _deep_merge ile mutasyona uğradığından bu sabit ASLA doğrudan değiştirilmemeli (paylaşım yok).
_DEFAULT_CONFIG = {
    'mqtt': {
        'broker_url': 'localhost',
        'broker_port': 1883,
        'user': '',
        'pass': '',
        'keepalive': 60,
        'use_tls': False
    },
    'serial': {
        'port': 'COM10',
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


class ProductionConfigManager:
    """
    Production-grade config manager with template fallback and encryption support.
    Thread-safe singleton pattern.
    """
    _instance = None
    _initialized = False
    _cfg_lock = threading.Lock()  # Audit P3: singleton init yarış-koruması

    # Sensitive keys to encrypt
    _ENCRYPTED_KEYS = {
        'mqtt.user',
        'mqtt.pass',
        'api.key',
    }
    
    def __new__(cls):
        if cls._instance is None:
            with cls._cfg_lock:  # Audit P3: çift-instance yarışı önle (double-checked)
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        # Audit P3: TÜM init'i kilit altında yap + _initialized'ı SONA al — eskiden kilitsiz + flag başta
        # set ediliyordu → iki thread eş-zamanlı __init__ geçip _setup_encryption'ı iki kez çalıştırıp
        # .pemf_key/cipher'ı ezebiliyordu (yarım/bozuk config veya iki farklı cipher).
        with type(self)._cfg_lock:
            if self._initialized:  # double-check
                return
            self._config = {}
            self._encryption_key = None
            self._cipher = None
            self._last_save_ts = 0.0
            # Initialize encryption
            self._setup_encryption()
            # Load config with fallback
            self._load_config()
            self._initialized = True   # SONA: init tamamlanınca (yarım-init obje görünmesin)
    
    def _setup_encryption(self):
        """Setup encryption for sensitive config values"""
        try:
            key_file = self._get_app_data_dir() / '.pemf_key'
            
            if key_file.exists():
                with open(key_file, 'rb') as f:
                    self._encryption_key = f.read()
            else:
                # Audit P2: MAC-tabanli anahtar (uuid.getnode → sha256) TAHMIN EDILEBILIR — cihazin
                # MAC'ini bilen, yedek/exfil edilen config.json'daki sirlari (.pemf_key olmadan) cozer.
                # Kriptografik-rastgele 32-byte anahtar uret + dosyada sakla (dosya zaten ACL-kilitli).
                # Mevcut cihazlar kayitli .pemf_key'i dosyadan yukleyip calismaya devam eder (geriye-uyumlu).
                self._encryption_key = base64.urlsafe_b64encode(os.urandom(32))
                
                # Save key with restricted permissions
                key_file.parent.mkdir(parents=True, exist_ok=True)
                with open(key_file, 'wb') as f:
                    f.write(self._encryption_key)
                
                # NTFS ACL kilidi (audit B-1.2): Fernet anahtar dosyası yalnız SYSTEM+Administrators'a
                # açık olsun. os.chmod Windows'ta NO-OP → anahtar dosyası Users'a okunur kalır ve config
                # şifrelemesi anlamsızlaşırdı. Önce ACL; olmazsa chmod (POSIX) yedek.
                try:
                    from utils.file_acl import lock_down_file
                    lock_down_file(key_file)
                except Exception:
                    try:
                        os.chmod(key_file, 0o600)
                    except Exception:
                        pass  # Windows chmod no-op; ACL zaten denendi
            
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
        """Config'i öncelik sırasıyla yükle (düşükten yükseğe derin-birleştir):
        gömülü varsayılan → bundled config.json (veya template) → %APPDATA% kullanıcı config'i."""
        self._config = copy.deepcopy(_DEFAULT_CONFIG)
        logger.info("Loaded hard-coded default config")

        bundled_config_path = self._get_bundled_resource_path('config/config.json')
        template_path = self._get_bundled_resource_path('config/config.json.template')
        self._merge_bundled_or_template(bundled_config_path, template_path)
        self._load_or_create_user_config(bundled_config_path or template_path)

    def _merge_bundled_or_template(self, bundled_path, template_path) -> None:
        """Bundled config.json'ı (varsa), yoksa template'i _config'e derin-birleştir (Production/Plug&Play)."""
        if bundled_path:
            self._merge_json_config(bundled_path, "bundled")
        elif template_path:
            self._merge_json_config(template_path, "template")

    def _merge_json_config(self, path, label: str) -> None:
        """Bir JSON config dosyasını yükleyip _config'e derin-birleştir (hata → logla, sürdür)."""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                self._deep_merge(self._config, json.load(f))
            logger.info(f"Loaded {label} config from: {path}")
        except Exception as e:
            logger.error(f"Failed to load {label} config: {e}")

    def _load_or_create_user_config(self, template_source) -> None:
        """%APPDATA% kullanıcı config'ini yükle (en yüksek öncelik) + template/bundled'dan eksik anahtarları
        tamamla; dosya yoksa mevcut durumdan ilk kullanıcı config'ini oluştur."""
        user_config_path = self._get_app_data_dir() / 'config.json'
        if user_config_path.exists():
            try:
                with open(user_config_path, 'r', encoding='utf-8') as f:
                    self._deep_merge(self._config, json.load(f))
                logger.info(f"Loaded user config from: {user_config_path}")
                # Eksik anahtarları template + bundled credential'lardan tamamla; değişiklik varsa kaydet.
                try:
                    self._upgrade_user_config_with_template(template_source)
                    self._save_user_config()
                except Exception:
                    pass
            except Exception as e:
                logger.error(f"Failed to load user config: {e}")
        else:
            logger.info(f"Creating initial user config at: {user_config_path}")
            try:
                self._upgrade_user_config_with_template(template_source)
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
        
        # DENETIM P3: truncate-then-write idi (gecici dosya + os.replace YOK, kilit YOK).
        # Guc kesintisi ya da es-zamanli iki kaydetme, config.json'i YARIM/BOS birakabiliyordu →
        # TUM kullanici ayarlari sessizce kaybolur (bir sonraki acilista varsayilanlara doner).
        # Ayni projedeki settings_router zaten atomik desen kullaniyor; burada eksikti.
        try:
            with _SAVE_LOCK:
                tmp_path = user_config_path.with_suffix('.json.tmp')
                with open(tmp_path, 'w', encoding='utf-8') as f:
                    json.dump(self._config, f, indent=4, ensure_ascii=False)
                    f.flush()
                    os.fsync(f.fileno())   # once diske indir, sonra atomik takas
                os.replace(tmp_path, user_config_path)
            # NTFS ACL kilidi (audit B-1.2): config hassas alanlar içerebilir → Users'a kapat.
            try:
                from utils.file_acl import lock_down_file
                lock_down_file(user_config_path)
            except Exception:
                pass
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

        # HiveMQ cloud-cred doldurma KALDIRILDI (2026-06-28): bundled hivemq_users.json zaten EXE
        # bundle'dan cikarildi + cloud bridge atil (yerel-only mimari) → blok gereksiz/olu.
    
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
        # DENETIM P3 (yanlis guvence): 'enc:' oneki KOSULSUZ ekleniyordu. _encrypt_value ise
        # cipher kurulamamissa (anahtar yok/kripto import hatasi) degeri OLDUGU GIBI dondurur →
        # diske "enc:<DUZ METIN>" yaziliyordu. Dosyayi inceleyen (ya da guvenlik denetimi yapan)
        # biri sirri sifreli sanar; ustelik _decrypt_value da cipher yokken degeri aynen
        # dondurdugu icin hata hicbir yerde YUZEYE CIKMAZ. Artik onek YALNIZCA gercekten
        # sifrelendiyse eklenir; sifrelenemediyse duz-metin DURUSTCE yazilir + GORUNUR uyarilir.
        if key_path in self._ENCRYPTED_KEYS and isinstance(value, str) and value:
            _enc = self._encrypt_value(value)
            if self._cipher and _enc != value:
                value = 'enc:' + _enc
            else:
                logger.warning(
                    "HASSAS AYAR SIFRELENEMEDI (%s) — DUZ METIN olarak saklaniyor. 'enc:' oneki "
                    "EKLENMEDI (yanlis guvence vermemek icin). Kripto anahtarini/kurulumunu kontrol edin.",
                    key_path)
        
        # Set only if changed
        key_name = keys[-1]
        old_value = config.get(key_name, None)
        if old_value == value:
            return

        config[key_name] = value
        
        if save:
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
            logger.error(f"Decryption failed: {e!r}", exc_info=True)
            return encrypted_value
    

# Global singleton instance
_global_config = None


def get_production_config() -> ProductionConfigManager:
    """Get global production config manager instance (singleton)"""
    global _global_config
    if _global_config is None:
        _global_config = ProductionConfigManager()
    return _global_config
