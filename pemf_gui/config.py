"""
Configuration management for the PEMF GUI application.
Handles loading/saving settings including serial port configuration.
"""

import base64
import hashlib
import json
import logging
import os
import threading
from typing import Any, Dict

from cryptography.fernet import Fernet, MultiFernet

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


# ══════════════════════════════════════════════════════════════════════════════════════════════════════════════════════
# ⚠️ D2.81 (A-29 sahip kararı · B-3.40 · B-3.41): `config.json`un SAHİBİ bu modülün ConfigManager'ıdır. `/api/settings`in
# ProductionConfigManager'ı (PCM) ona BAĞLANIR: şifreli alanları bu sınıfın anahtarıyla (`patient_fernet_key`) yazar/okur ve
# dosyayı aşağıdaki TEK okuyucu / yazıcı / kilitle okur-yazar. Eskiden iki yönetici aynı dosyayı ayrı anahtar, ayrı kilit ve ayrı
# ACL ile yazıyordu: PCM ortak veri dizinine rastgele `.pemf_key` yazıp eski MAC-türevli hasta alanlarını "[okunamayan kayıt]"
# yapıyor (B-3.40), kaydettiği dosyayı yalnız SYSTEM + Administrators'a kilitleyip yükseltilmemiş (launcher) backend'in bir
# sonraki açılışta KENDİ ayarını okuyamamasına yol açıyordu; `POST /api/settings` "success" deyip diske yazamıyordu (B-3.41).
# Kapı: tests/test_config_TEK_SAHIP_pemf_key_ve_kilit_D281.py · atomiklik: tests/test_pcm_yazim_DAVRANISI_D231.py
# ══════════════════════════════════════════════════════════════════════════════════════════════════════════════════════
_YAZIM_KILIDI = threading.Lock()


class ConfigKaydiReddedildi(RuntimeError):
    """`config.json` diskte VAR ama okunamadığı için kayıt REDDEDİLDİ: bellekteki değerler varsayılanlardır, yazmak klinik
    ayarlarını (MQTT broker / port …) silerdi."""


def _config_oku(yol) -> dict:
    with open(yol, 'r', encoding='utf-8') as f:
        veri = json.load(f)
    if not isinstance(veri, dict):
        raise ValueError(f"config.json bir JSON nesnesi degil ({type(veri).__name__})")
    return veri


def config_json_oku(yol) -> dict:
    """`config.json`u oku (UTF-8). Erişim REDDEDİLİRSE kilit BİR KEZ süreç hesabı korunarak yeniden uygulanır ve okuma yeniden
    denenir: dosyanın sahibi bu hesapsa (1.9.50'nin yükseltilmemiş backend'i kendi dosyasını SYSTEM + Administrators'a
    kilitlemişti) Windows sahibe ACL değiştirme hakkı verir → dosya güncellemeden sonra kendiliğinden açılır; başka hesabın
    dosyasıysa hiçbir şey değişmez. Kalan hata (bozuk JSON / hâlâ erişim yok) çağırana yükselir — çağıran kaydı kapatır."""
    try:
        return _config_oku(yol)
    except PermissionError as ilk:
        try:
            from utils.file_acl import lock_down_file

            onarildi = bool(lock_down_file(yol, keep_current_user=True))
        except Exception:
            onarildi = False
        if not onarildi:
            raise
        logger.warning(
            "config.json okunamiyordu (%s) — ACL kilidi surecin hesabi korunarak yeniden uygulandi, yeniden okunuyor: %s",
            ilk,
            yol,
        )
        return _config_oku(yol)


def config_json_yaz(yol, veri: dict) -> None:
    """ATOMİK yaz (tmp + fsync + `os.replace`, süreç geneli kilit) ve süreç hesabını KORUYAN ACL ile kilitle (Users yine dışarıda).
    Hata çağırana yükselir; `config.json` önceki baytlarla kalır."""
    tmp = f"{yol}.{os.getpid()}.tmp"
    with _YAZIM_KILIDI:
        os.makedirs(os.path.dirname(os.path.abspath(yol)), exist_ok=True)
        try:
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(veri, f, indent=4, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())  # önce diske indir, sonra atomik takas
            os.replace(tmp, yol)
        finally:
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except Exception:
                pass
    try:
        from utils.file_acl import lock_down_file

        lock_down_file(yol, keep_current_user=True)
    except Exception:
        logger.debug("config.json ACL kilidi uygulanamadi", exc_info=True)


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
            # Kanonik veri dizini: PEMF_DATA_DIR (SecretsManager + SQLCipher anahtari ile AYNI kok →
            # ~/.pemf_gui SPLIT-BRAIN'i kapanir). Birincil Fernet anahtari zaten SecretsManager'dadir;
            # burada config.json + LEGACY fallback anahtar dosyalari da kanonik dizine tasinir.
            override = os.getenv("PEMF_DATA_DIR", "").strip()
            if override:
                self.config_dir = os.path.join(override, "PEMF_GUI")
            else:
                self.config_dir = os.path.join(os.path.expanduser('~'), '.pemf_gui')
            os.makedirs(self.config_dir, exist_ok=True)
            # Geriye-uyumlu ILERI-TASIMA (VERI KAYBI YOK): eski ~/.pemf_gui dosyalari yeni dizinde
            # YOKSA kopyala (asla silme) → eski kurulumlarin config/legacy-anahtarlari korunur.
            self._migrate_legacy_config_dir()
            self.config_file = os.path.join(self.config_dir, 'config.json')
        else:
            self.config_file = config_file
            self.config_dir = os.path.dirname(config_file)

        # CRITICAL FIX: Initialize encryption
        # ⚠️ 2-A inceleme A2-1.1 · A2-1.3 (D2.45 · Y9 · Ö.4-Y8): birincil anahtar MODÜL YÜKLENİRKEN ALINMAZ, ilk
        # ihtiyaçta alınır (`_anahtar_hazirla`). Bu sınıfın modül düzeyi singleton'ı `backend_service` → `headless_core`
        # → `patient_database` zincirinde İÇE AKTARILIRKEN kuruluyordu:
        #   * sır dosyası BOZUKKEN ya da `patient_fernet_key` bu makinede ÇÖZÜLEMEZKEN (makine değişimi / Windows yeniden
        #     kurulumu) fail-closed `RuntimeError` içe aktarmadan kaçıyor, backend HİÇ açılmıyordu — ACİL DURDUR, sağlık
        #     ucu, açılış STOP mutabakatı ve günlük YOK; kurtarma aracı (`--kurtarma`) da açılamıyordu (ölçüldü);
        #   * taze kurulumda içe aktarma YENİ bir anahtar üretip sır dosyasına yazıyor, `--kurtarma --yaz` onu "mevcut"
        #     sayıp DURUYORDU (ölçüldü).
        # Anahtar artık hasta DB'si açılırken alınır; alınamazsa o DB açılmaz (DB'siz kısıtlı kip — Y9), arka plan yeniden
        # açması (Y43) her denemede yeniden dener. Kapı: tests/test_alan_anahtari_ICE_AKTARMADA_alinmaz_A21.py ve
        # tests/test_acilis_DB_acilamasa_ACIL_DURDUR_yasar.py ("sir_bozuk", "sir_cozulemez_ikisi").
        self._encryption_key = None
        self._cipher = None
        self._legacy_cipher = self._get_legacy_cipher()  # eski MAC-türevli anahtar (yalnız decrypt fallback)

        # Default configuration
        self.default_config = {
            'serial': {
                'port': 'COM13',
                'baudrate': 115200,
                'timeout': 1.0,
                'emulation_mode': False,  # Run without hardware
                'auto_connect': True,  # Try to auto-connect on startup
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

    def _migrate_legacy_config_dir(self) -> None:
        """Eski ~/.pemf_gui'deki config.json + fallback anahtar dosyalarini (.pemf_key_v2, .pemf_key)
        kanonik config_dir'e KOPYALA — yalniz yeni dizinde YOKSA; ASLA silme. Split-brain kapanir,
        veri kaybi olmaz. (Birincil Fernet anahtari zaten SecretsManager/ProgramData'da; bu, keyring
        ve SecretsManager ikisi de basarisiz olursa devreye giren LEGACY fallback dosyalari icindir.)"""
        try:
            legacy = os.path.join(os.path.expanduser('~'), '.pemf_gui')
            if os.path.abspath(legacy) == os.path.abspath(self.config_dir) or not os.path.isdir(legacy):
                return
            import shutil as _sh

            for fn in ('config.json', '.pemf_key_v2', '.pemf_key'):
                src = os.path.join(legacy, fn)
                dst = os.path.join(self.config_dir, fn)
                if os.path.exists(src) and not os.path.exists(dst):
                    _sh.copy2(src, dst)
                    try:
                        from utils.file_acl import lock_down_file

                        # audit B-1.2: NTFS ACL (os.chmod Windows'ta no-op). D2.81 (B-3.41): süreç hesabı KORUNUR — varsayılan
                        # (yalnız SYSTEM + Administrators) yükseltilmemiş backend'i kopyaladığı kendi config'inden dışarı atardı.
                        lock_down_file(dst, keep_current_user=True)
                    except Exception:
                        pass
        except Exception:
            logger.warning("Legacy config_dir ileri-tasima atlandi (kritik degil).", exc_info=True)

    def _get_or_create_key(self) -> bytes:
        """Birincil şifreleme anahtarı (RASTGELE, MAC'ten bağımsız) TEK kaynaktan: SecretsManager (`patient_fernet_key`,
        DPAPI/MKEY ile saklanır). Eski kaynakları (keyring → `.pemf_key_v2`) SecretsManager'ın `legacy` göçü okur; anahtar
        hiç yoksa SecretsManager üretir (diske yazdıktan SONRA döner). Eski MAC-türevli anahtar BİRİNCİL DEĞİL (yalnız
        `_get_legacy_cipher` ile decrypt fallback).

        ⚠️ 2-A inceleme A2-1.2 (D2.45 · Karar 6 "TÜM anahtar yollarında" · Y9): SecretsManager'ın HER hatası fail-closed
        `RuntimeError`'dır — eski yola (keyring → `.pemf_key_v2` → YOKSA YENİ anahtar üretip GERÇEK Windows kimlik kasasına /
        dosyaya yazma) DÜŞÜLMEZ. Eskiden `RuntimeError` OLMAYAN hata (sır dizinine erişilemiyor — ikinci Windows hesabı; ilk
        kalıcılaştırma bir kez düştü) bu yola düşüyor, YENİ Fernet anahtarı üretip kasaya yazıyordu (ölçüldü: veri kökü başka
        SID'e kilitliyken `keyring.set_password('PEMF_GUI', 'patient_fernet_key')`); kasa yazamazsa anahtar YALNIZ bellekte
        kalıyor, o süreçte şifrelenen hasta alanları yeniden başlatmada ÇÖZÜLEMİYORDU (ölçüldü, null kasa). `sqlcipher_key`
        yolunun D2.45'teki ikizi. Kapı: tests/test_alan_anahtari_eski_yol_YOK_Karar6_A12.py."""
        try:
            from utils.secrets_manager import get_secret

            _k = get_secret("patient_fernet_key")
        except RuntimeError:
            # Audit P3: SecretsManager brick-koruma (kritik anahtar VAR ama çözülemez → fail-closed
            # RuntimeError) → YUTMA. Yeni patient_fernet_key üretmek mevcut şifreli PII'yi kalıcı
            # okunamaz yapar (veri-kaybı) → fail-closed propagate et.
            logger.error(
                "patient_fernet_key BRICK (var ama çözülemez) → yeni anahtar ÜRETİLMİYOR (veri-kaybı önlendi)."
            )
            raise
        except Exception as _e:
            _ileti = (
                "patient_fernet_key SecretsManager'dan OKUNAMADI/YAZILAMADI (%s: %s) — eski yola DUSULMEDI, YENI ANAHTAR "
                "URETILMEDI; hasta veritabani acilmayacak, dosyalara dokunulmadi (Karar 6). Sir dosyasina/veri kokune "
                "erisimi duzeltin; veritabani arka planda yeniden acilir."
            )
            try:
                # O-A2-1.b (D2.80): her açılış denemesinde (Y43) aynı satır — tekrar-kısıtlı (ilk satır + sayım).
                from utils.secrets_manager import tekrar_kisitli_hata

                tekrar_kisitli_hata(
                    logger, "patient_fernet_key", f"{type(_e).__name__}: {_e}", _ileti, type(_e).__name__, _e
                )
            except ImportError:
                logger.error(_ileti, type(_e).__name__, _e)
            raise RuntimeError(
                f"patient_fernet_key okunamadi/yazilamadi ({type(_e).__name__}) — yeni anahtar URETILMEDI, eski yola "
                "dusulmedi (Karar 6)."
            ) from _e
        if not _k:
            raise RuntimeError("patient_fernet_key bos dondu — yeni anahtar URETILMEDI, eski yola dusulmedi (Karar 6).")
        return _k.encode() if isinstance(_k, str) else _k

    def _get_legacy_cipher(self):
        """Eski anahtarlar — yalnız ESKİ kayıtları çözmek için: `.pemf_key` (varsa) VE MAC-türevli anahtar, sırayla. Hiçbiri yoksa None.

        ⚠️ D2.81 (B-3.40): eskiden `.pemf_key` VARSA yalnız o deneniyordu. 1.9.50'nin ProductionConfigManager'ı ortak veri dizinine
        `.pemf_key` yoksa RASTGELE anahtar yazıyordu → o andan sonra MAC-türevli anahtarla şifrelenmiş eski hasta alanları (ad / sahip)
        "[okunamayan kayıt]" görünüyordu (veri durur). İkisi de denenir; PCM artık `.pemf_key` ÜRETMEZ."""
        anahtarlar = []
        try:
            key_file = os.path.join(self.config_dir, '.pemf_key')
            if os.path.exists(key_file):
                with open(key_file, 'rb') as f:
                    dosya_anahtari = f.read().strip()
                if dosya_anahtari:
                    anahtarlar.append(Fernet(dosya_anahtari))
        except Exception:
            logger.debug(".pemf_key eski anahtar olarak kullanilamadi", exc_info=True)
        try:
            import uuid

            machine_id = str(uuid.getnode()).encode()
            anahtarlar.append(Fernet(base64.urlsafe_b64encode(hashlib.sha256(machine_id).digest())))
        except Exception:
            logger.debug("MAC-turevli eski anahtar kurulamadi", exc_info=True)
        return MultiFernet(anahtarlar) if anahtarlar else None

    def _anahtar_hazirla(self) -> Fernet:
        """Birincil alan anahtarını İLK İHTİYAÇTA al (2-A inceleme A2-1.1). Alınamazsa `RuntimeError` yükselir (fail-closed:
        yeni anahtar üretilmez, düz-metin yazılmaz); sonraki çağrı yeniden dener (Y43)."""
        if self._cipher is None:
            anahtar = self._get_or_create_key()
            cipher = Fernet(anahtar)
            self._encryption_key = anahtar
            self._cipher = cipher
        return self._cipher

    def _encrypt_value(self, value: str) -> str:
        """Encrypt sensitive value"""
        if not value:
            return value
        encrypted = self._anahtar_hazirla().encrypt(value.encode())
        return base64.urlsafe_b64encode(encrypted).decode()

    def _decrypt_value(self, encrypted_value: str, sessiz: bool = False) -> str:
        """Decrypt: önce BİRİNCİL (rastgele) anahtar, sonra ESKİ MAC-türevli (geriye dönük).
        İkisi de başarısızsa ham değeri döndürür (üst katman maskeleyebilir).

        `sessiz=True`: başarısızlık ERROR olarak loglanmaz — değerin şifreli OLDUĞU bilinmeyen çağıran içindir
        (D2.26: hasta DB'sinin öneksiz eski alanları; düz-metin bir eski değer de base64 gibi çözülebilir)."""
        if not encrypted_value:
            return encrypted_value
        try:
            encrypted_bytes = base64.urlsafe_b64decode(encrypted_value.encode())
        except Exception:
            return encrypted_value
        try:
            return self._anahtar_hazirla().decrypt(encrypted_bytes).decode()
        except Exception:
            pass
        legacy = getattr(self, "_legacy_cipher", None)
        if legacy is not None:
            try:
                return legacy.decrypt(encrypted_bytes).decode()
            except Exception:
                pass
        if not sessiz:
            logger.error("Decryption failed (birincil + legacy anahtar)")
        return encrypted_value

    def load(self) -> Dict[str, Any]:
        """Load configuration from file (ortak okuyucu: UTF-8, erişim reddinde kilit bir kez onarılır — D2.81).

        Dosya VAR ama okunamazsa (bozuk JSON / erişim yok) bellekte varsayılanlar kalır ve kayıt KAPATILIR: `save()`
        `ConfigKaydiReddedildi` yükseltir — varsayılanlar klinik ayarlarını EZMEZ (PCM'deki 2026-08-17 kapısının sahipteki ikizi)."""
        self._yuklenemedi = None
        try:
            if os.path.exists(self.config_file):
                logger.debug(f"Loading configuration from {self.config_file}")
                self._merge_config(config_json_oku(self.config_file))
                logger.info("Configuration loaded successfully")
        except Exception as e:
            self._yuklenemedi = f"{type(e).__name__}: {e}"
            logger.error(
                "Failed to load configuration: %s -- KAYDETME KAPATILDI (mevcut dosya EZILMEYECEK): %s",
                e,
                self.config_file,
            )
            self.config = self.default_config.copy()

        return self.config

    def save(self) -> None:
        """Save current configuration to file — ortak ATOMİK yazıcı (PCM ile AYNI kilit) + süreç hesabını koruyan ACL (D2.81)."""
        if getattr(self, "_yuklenemedi", None):
            raise ConfigKaydiReddedildi(
                f"config.json okunamadigi icin KAYDEDILMEDI ({self._yuklenemedi}); mevcut dosya korunuyor: {self.config_file}"
            )
        try:
            logger.debug(f"Saving configuration to {self.config_file}")
            config_json_yaz(self.config_file, self.config)
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
