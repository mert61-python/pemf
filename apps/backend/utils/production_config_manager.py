# Author: mertaygn, cglrgrkn
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
import json
import logging
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

from cryptography.fernet import Fernet

try:
    from .path_utils import get_app_data_directory as get_shared_app_data_directory
    from .path_utils import kaynak_kokunu_bul
except ImportError:
    from path_utils import get_app_data_directory as get_shared_app_data_directory
    from path_utils import kaynak_kokunu_bul

logger = logging.getLogger(__name__)


def _sahip():
    """⚠️ D2.81 (A-29): `config.json`un SAHİBİ `pemf_gui.config` modülü — şifreli alan anahtarı (`get_config()._encrypt_value` /
    `_decrypt_value`) ve TEK okuyucu / atomik yazıcı / kilit (`config_json_oku` / `config_json_yaz`) oradadır. PCM ayrı anahtar,
    ayrı kilit ya da ayrı ACL TUTMAZ. (`pemf_gui` depo kökünde; doğrudan betik koşumunda kök sys.path'e eklenir.)"""
    try:
        from pemf_gui import config as sahip_modulu
    except ModuleNotFoundError:
        kok = str(kaynak_kokunu_bul(__file__))
        if kok not in sys.path:
            sys.path.insert(0, kok)
        from pemf_gui import config as sahip_modulu
    return sahip_modulu


def kayit_reddi_mi(hata: BaseException) -> bool:
    """`hata`, okunamayan `config.json` yüzünden REDDEDİLEN bir kayıt mı? (`/api/settings` bunu 503'e çevirir.)"""
    return isinstance(hata, _sahip().ConfigKaydiReddedildi)


# Gömülü varsayılan config (son çare). Kullanım öncesi copy.deepcopy'lenir — iç içe dict'ler
# _deep_merge ile mutasyona uğradığından bu sabit ASLA doğrudan değiştirilmemeli (paylaşım yok).
_DEFAULT_CONFIG = {
    'mqtt': {'broker_url': 'localhost', 'broker_port': 1883, 'user': '', 'pass': '', 'keepalive': 60, 'use_tls': False},
    'serial': {'port': 'COM10', 'baudrate': 115200, 'timeout': 1.0, 'emulation_mode': False, 'auto_connect': True},
    'application': {'theme': 'dark', 'language': 'tr', 'auto_save': True, 'log_level': 'INFO'},
    'treatment': {'max_duration': 60, 'default_frequency': 10, 'default_intensity': 50},
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
            #: Kullanıcı config'i diskte VAR ama okunamadıysa hata metni (fail-closed kapısı).
            self._user_config_unreadable = None
            #: Kaydedilmemiş değişiklik var mı — okunamayan dosyada kayıt reddi yalnız o zaman HATA yükseltir (D2.81).
            self._kirli = False
            self._last_save_ts = 0.0
            # ⚠️ D2.81 (A-29 · B-3.40): şifreleme KURULUMU YOK — anahtar `config.json`un sahibininkidir (`_sahip`); PCM `.pemf_key`
            # ÜRETMEZ. Eskiden `.pemf_key` yoksa ortak veri dizinine RASTGELE anahtar yazıyordu → sahibin eski-anahtar zinciri o
            # dosyayı seçip MAC-türevli anahtarla şifrelenmiş eski hasta alanlarını "[okunamayan kayıt]" yapıyordu.
            # Load config with fallback
            self._load_config()
            self._initialized = True  # SONA: init tamamlanınca (yarım-init obje görünmesin)

    def _eski_pcm_anahtari(self):
        """1.9.50 ve öncesinin PCM'i şifreli alanları KENDİ veri dizinindeki `.pemf_key`le yazıyordu — o değerler yalnız OKUNUR
        (dosya ÜRETİLMEZ, yazımda kullanılmaz). Yoksa / geçersizse None."""
        try:
            anahtar = (self._get_app_data_dir() / '.pemf_key').read_bytes().strip()
            return Fernet(anahtar) if anahtar else None
        except Exception:
            return None

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
        dev_path = kaynak_kokunu_bul(__file__) / relative_path
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
                # D2.81 (A-29 · B-3.41): sahibin ORTAK okuyucusu — erişim reddinde kilidi süreç hesabı korunarak bir kez onarır
                # (1.9.50'nin kendi dosyasını SYSTEM + Administrators'a kilitlediği yükseltilmemiş kurulum güncellemede açılır).
                self._deep_merge(self._config, _sahip().config_json_oku(user_config_path))
                logger.info(f"Loaded user config from: {user_config_path}")
                # Eksik anahtarları template + bundled credential'lardan tamamla; değişiklik varsa kaydet.
                try:
                    self._upgrade_user_config_with_template(template_source)
                    self._save_user_config()
                except Exception:
                    pass
            except Exception as e:
                # ⚠️ FAIL-CLOSED (denetim 2026-08-17): dosya VAR ama OKUNAMIYOR (izin reddi, bozuk
                # JSON, disk hatası). Eskiden yalnız log basılıp VARSAYILANLARLA devam ediliyordu;
                # sonraki İLK `save()` kullanıcının override'larını SESSİZCE siliyordu.
                # Gerçek senaryo: `backend_service` `config.json`u SYSTEM+Admin ACL'ine kilitliyor;
                # süreç sonradan yetkisiz bir kullanıcıyla koşarsa okuma düşer, ilk kayıt klinik
                # ayarlarını siler → `mqtt.broker_url` `localhost`a döner → ESP bobinleri (6-8)
                # broker'ı BULAMAZ. Ölçüldü (bu makinede, kaza eseri): dosya varsayılanlarla ezildi.
                # Bu, bozuk `pemf_secrets.json` bulgusunun (yeni SQLCipher anahtarı) AYNI sınıfı.
                self._user_config_unreadable = str(e)
                logger.error(
                    "Failed to load user config: %s -- KAYDETME KAPATILDI (mevcut dosya EZILMEYECEK). "
                    "Cozum: dosyayi okunabilir yapin (ACL) ya da bozuksa yedekten geri yukleyin: %s",
                    e,
                    user_config_path,
                )
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
        """Save current config to user's APPDATA directory.

        ⚠️ FAIL-CLOSED KAPISI (denetim 2026-08-17): kullanıcı config'i diskte VAR ama YÜKLENEMEDİYSE
        bellekteki `self._config` yalnızca bundled+template VARSAYILANLARIDIR. Onu diske yazmak,
        okunamayan dosyadaki gerçek klinik ayarlarını (MQTT broker/port gibi) SESSİZCE SİLER.
        Yazma reddedilir; operatöre ne yapacağı söylenir.

        ⚠️ D2.81 (B-3.41): ret artık SESSİZ DEĞİL — kaydedilmemiş değişiklik varsa `ConfigKaydiReddedildi` yükselir
        (`POST /api/settings` eskiden "success" deyip diske yazmıyordu). Yazım sahibin ORTAK atomik yazıcısıyla (tmp + fsync +
        replace, sahiple AYNI kilit) ve süreç hesabını KORUYAN ACL ile (eskiden yalnız SYSTEM + Administrators → yükseltilmemiş
        backend bir sonraki açılışta KENDİ ayarını okuyamıyordu)."""
        sahip = _sahip()
        if getattr(self, "_user_config_unreadable", None):
            logger.error(
                "config.json YUKLENEMEDIGI icin KAYDETME REDDEDILDI (%s). Mevcut dosya korunuyor; "
                "varsayilanlarla UZERINE YAZILMASI kullanici ayarlarini yok ederdi.",
                self._user_config_unreadable,
            )
            if getattr(self, "_kirli", False):
                raise sahip.ConfigKaydiReddedildi(
                    f"Ayar KAYDEDILMEDI: config.json okunamiyor ({self._user_config_unreadable}). Mevcut dosya korunuyor "
                    "(varsayilanlarla ezilmedi). Yapilacak: dosyayi uygulamayi kuran Windows hesabiyla acin ya da izinlerini "
                    "duzelttirin; bozuksa yedekteki pemf_config_<tarih>.json dosyasini config.json olarak geri yukleyin."
                )
            return
        user_config_path = self._get_app_data_dir() / 'config.json'
        try:
            sahip.config_json_yaz(user_config_path, copy.deepcopy(self._config))
            self._kirli = False
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
            if _enc:  # D2.81: `_encrypt_value` şifreleyemezse None döner (sahibin anahtarı alınamadı / şifreleme düştü)
                value = 'enc:' + _enc
            else:
                logger.warning(
                    "HASSAS AYAR SIFRELENEMEDI (%s) — DUZ METIN olarak saklaniyor. 'enc:' oneki "
                    "EKLENMEDI (yanlis guvence vermemek icin). Kripto anahtarini/kurulumunu kontrol edin.",
                    key_path,
                )

        # Set only if changed
        key_name = keys[-1]
        old_value = config.get(key_name, None)
        if old_value == value:
            return

        config[key_name] = value
        self._kirli = True

        if save:
            self._save_user_config()
            self._last_save_ts = time.monotonic()

    def save(self):
        """Persist current config to disk explicitly."""
        self._save_user_config()
        self._last_save_ts = time.monotonic()

    def _encrypt_value(self, value: str) -> Optional[str]:
        """Hassas değeri `config.json`un SAHİBİNİN anahtarıyla (`patient_fernet_key`) şifrele (D2.81 · A-29) — sahip ve PCM aynı
        değeri okuyabilsin. Şifrelenemezse None (çağıran düz yazar ve uyarır; sahte 'enc:' öneki YOK)."""
        if not value:
            return value
        try:
            return _sahip().get_config()._encrypt_value(value)
        except Exception as e:
            logger.error("Encryption failed (%s)", type(e).__name__)
            return None

    def _decrypt_value(self, encrypted_value: str) -> str:
        """Sahibin zinciriyle çöz (birincil `patient_fernet_key` → eski `.pemf_key` + MAC-türevli); eski PCM'in kendi veri
        dizinindeki `.pemf_key` ile yazdığı değerler için o dosya da (yalnız OKUNUR) denenir. Çözülemezse ham değer (D2.81).

        Eskiden PCM yalnız KENDİ `.pemf_key`iyle çözüyordu: sahibin `patient_fernet_key` ile şifrelediği `mqtt.pass` (ör. açılıştaki
        düz-metin sır göçü) PCM'den şifreli metin olarak dönüyordu."""
        if not encrypted_value:
            return encrypted_value
        try:
            cozulen = _sahip().get_config()._decrypt_value(encrypted_value, sessiz=True)
        except Exception:
            cozulen = encrypted_value
        if cozulen != encrypted_value:
            return cozulen
        eski = self._eski_pcm_anahtari()
        if eski is not None:
            try:
                return eski.decrypt(base64.urlsafe_b64decode(encrypted_value.encode())).decode()
            except Exception:
                pass
        logger.error("Decryption failed (sahibin anahtarlari + eski PCM .pemf_key)")
        return encrypted_value


# Global singleton instance
_global_config = None


def get_production_config() -> ProductionConfigManager:
    """Get global production config manager instance (singleton)"""
    global _global_config
    if _global_config is None:
        _global_config = ProductionConfigManager()
    return _global_config
