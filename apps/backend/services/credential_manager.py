"""
PEMF Credential Manager — Otomatik Cihaz Kimlik Bilgisi Yönetimi

Sistem, her ESP bobini ve Android uygulaması için benzersiz,
yetki kısıtlı kimlik bilgileri üretir. Tek bir "master" şifreye
ihtiyaç yoktur; her bileşen yalnızca kendi topiclerine erişebilir.

Mimari:
  - esp_coil_{id}   : Sadece kendi coil topicini yönetir
  - gui_bridge      : Tam pemf/# erişimi (bridge için)
  - android_{uid}   : Sadece control/status/events okur
  - master          : Sadece yerel yönetim (LattePanda üstünde)

Kullanım:
    python -m services.credential_manager generate --coil-id 6
    python -m services.credential_manager list
    python -m services.credential_manager provision --all
"""

import hashlib
import hmac
import json
import logging
import os
import secrets
import string
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional

# Sır/anahtar dosyalarına NTFS ACL kilidi (Audit P1). Windows'ta os.chmod no-op'tur →
# düz-metin cred/anahtar dosyaları yerel 'Users' tarafından okunabilir kalıyordu.
try:
    from utils.file_acl import lock_down_file
except Exception:  # best-effort: helper yoksa çağıran akış DURMAZ

    def lock_down_file(_path):
        return False


logger = logging.getLogger(__name__)

# ── Yapılandırma ─────────────────────────────────────────────────────────────

# Cihaza özgü credential türetme için master secret.
# Bu key, üretimde ortam değişkeninden ya da şifrelenmiş bir konfigürasyon
# dosyasından okunmalıdır. Asla kaynak kodda bırakılmamalıdır.
_ENV_MASTER_SECRET = "PEMF_MASTER_SECRET"
_DEFAULT_MASTER_SECRET_WARNING = (
    "PEMF_MASTER_SECRET ortam değişkeni ayarlanmamış! Üretim dağıtımı için lütfen güçlü bir değer atayın."
)

# Try to use path_utils for app data directory, fallback if not available
try:
    from utils.path_utils import get_app_data_directory

    _APP_DATA_DIR = get_app_data_directory()
except ImportError:
    import platform

    if platform.system() == "Windows":
        _APP_DATA_DIR = Path(os.getenv('APPDATA')) / "PEMF_GUI"
    else:
        _APP_DATA_DIR = Path.home() / ".local" / "share" / "PEMF_GUI"

# Credential saklama dizini (Kalıcı AppData klasörü)
CREDENTIALS_DIR = _APP_DATA_DIR / "config" / "credentials"


@dataclass
class DeviceCredential:
    """Tek bir kimlik bilgisi kaydı"""

    role: str  # esp_coil / gui_bridge / android_app / master
    username: str
    password: str
    coil_id: Optional[int]  # Sadece ESP kimlik bilgileri için
    allowed_publish: List[str]  # İzinli publish topic kalıpları
    allowed_subscribe: List[str]
    notes: str = ""


class CredentialManager:
    """
    Merkezi PEMF kimlik bilgisi yöneticisi.

    Tüm credential üretimi, saklanması ve doğrulaması bu sınıf üzerinden yapılır.
    MASTER_SECRET değişmediği sürece aynı coil_id → aynı credential üretilir
    (deterministik), böylece cihaz yeniden flash'lansa bile aynı şifre geçerlidir.
    """

    def __init__(self, master_secret: Optional[str] = None):
        # TEK-DOSYA: env yoksa SecretsManager'dan master_secret (migrate; YOKSA üretme → eski uyarı+dosya yolu korunur).
        _sm_secret = None
        try:
            from utils.secrets_manager import get_secret

            _sm_secret = get_secret("master_secret", generate=False) or None
        except Exception:
            pass
        self._master_secret = (
            master_secret or os.environ.get(_ENV_MASTER_SECRET) or _sm_secret or self._warn_and_use_default()
        )
        CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)
        self._credential_file = CREDENTIALS_DIR / "credentials.json"
        self._credentials: Dict[str, DeviceCredential] = {}
        self._load()

    # ── Public API ────────────────────────────────────────────────────────

    def get_or_create_esp_credential(self, coil_id: int) -> DeviceCredential:
        """Belirtilen bobine ait credential'ı döndürür; yoksa oluşturur."""
        key = f"esp_coil_{coil_id}"
        if key in self._credentials:
            return self._credentials[key]
        return self._create_esp_credential(coil_id)

    def get_or_create_bridge_credential(self) -> DeviceCredential:
        """LattePanda MQTT Bridge credential'ı (tam pemf/# erişimi)."""
        key = "gui_bridge"
        if key in self._credentials:
            return self._credentials[key]
        return self._create_bridge_credential()

    def get_or_create_android_credential(self, uid: Optional[str] = None) -> DeviceCredential:
        """Android uygulaması için sınırlı yetkili credential."""
        uid = uid or "prod"
        key = f"android_{uid}"
        if key in self._credentials:
            return self._credentials[key]
        return self._create_android_credential(uid)

    def get_credential(self, username: str) -> Optional[DeviceCredential]:
        """Kullanıcı adına göre credential sorgular."""
        for cred in self._credentials.values():
            if cred.username == username:
                return cred
        return None

    def list_credentials(self) -> List[DeviceCredential]:
        """Kayıtlı tüm credential'ları döndürür."""
        return list(self._credentials.values())

    def export_mosquitto_password_file(self, output_path: Optional[str] = None) -> str:
        """
        Mosquitto password_file formatında dışa aktarır.
        mosquitto_passwd ile uyumlu satır formatı: username:hashed_password
        Bu fonksiyon PLAIN text password yazar; mosquitto_passwd ile hash'lenmelidir.
        """
        path = Path(output_path) if output_path else CREDENTIALS_DIR / "mosquitto_passwords.txt"
        lines = []
        for cred in self._credentials.values():
            lines.append(f"{cred.username}:{cred.password}")
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        lock_down_file(path)  # düz-metin şifreler → sadece SYSTEM+Admin okusun (Audit P1)
        logger.info(f"Mosquitto password file yazıldı: {path}")
        return str(path)

    def export_acl_file(self, output_path: Optional[str] = None) -> str:
        """Mosquitto ACL (Access Control List) dosyası oluşturur."""
        path = Path(output_path) if output_path else CREDENTIALS_DIR / "mosquitto_acl.conf"
        lines = [
            "# PEMF MQTT Access Control List",
            "# Otomatik oluşturulmuştur — CredentialManager tarafından",
            "",
        ]
        for cred in self._credentials.values():
            lines.append(f"user {cred.username}")
            for topic in cred.allowed_publish:
                lines.append(f"topic write {topic}")
            for topic in cred.allowed_subscribe:
                lines.append(f"topic read {topic}")
            lines.append("")
        path.write_text("\n".join(lines), encoding="utf-8")
        lock_down_file(path)
        logger.info(f"Mosquitto ACL file yazıldı: {path}")
        return str(path)

    def export_hivemq_config(self, output_path: Optional[str] = None) -> str:
        """
        HiveMQ Cloud kimlik bilgileri için JSON dışa aktarımı.
        HiveMQ Cloud web panelinde el ile girilmek üzere hazırlanır.
        """
        path = Path(output_path) if output_path else CREDENTIALS_DIR / "hivemq_users.json"
        hivemq_users = []
        for cred in self._credentials.values():
            hivemq_users.append(
                {
                    "username": cred.username,
                    "password": cred.password,
                    "role": cred.role,
                    "publish_topics": cred.allowed_publish,
                    "subscribe_topics": cred.allowed_subscribe,
                }
            )
        path.write_text(json.dumps({"users": hivemq_users}, indent=2, ensure_ascii=False), encoding="utf-8")
        lock_down_file(path)  # düz-metin şifreler → ACL kilidi (Audit P1)
        logger.info(f"HiveMQ kullanıcı listesi yazıldı: {path}")
        return str(path)

    def export_esp_secrets(self, coil_id: int, output_path: Optional[str] = None) -> str:
        """
        Belirtilen bobin için Secrets.h içeriği oluşturur.
        Bu dosya ESP32'ye flash'lanmadan önce Secrets.h ile birleştirilir.
        """
        cred = self.get_or_create_esp_credential(coil_id)
        path = Path(output_path) if output_path else CREDENTIALS_DIR / f"secrets_coil_{coil_id}.h"
        content = f"""// AUTO-GENERATED — PEMF CredentialManager tarafından üretilmiştir.
// Değiştirmeyin. Yeniden üretmek için: python -m services.credential_manager generate --coil-id {coil_id}

#ifndef SECRETS_GENERATED_H
#define SECRETS_GENERATED_H

// Cihaz Kimliği
#define FACTORY_COIL_ID {coil_id}

// Cloud MQTT Kimlik Bilgileri (Bu bobine özgü, sınırlı yetkili)
static const char* DEFAULT_CLOUD_MQTT_USER = "{cred.username}";
static const char* DEFAULT_CLOUD_MQTT_PASS = "{cred.password}";

#endif // SECRETS_GENERATED_H
"""
        path.write_text(content, encoding="utf-8")
        lock_down_file(path)  # ESP MQTT şifresi düz-metin → ACL kilidi (Audit P1)
        logger.info(f"ESP Secrets dosyası yazıldı: {path}")
        return str(path)

    # ── Credential Üreticiler ─────────────────────────────────────────────

    def _create_esp_credential(self, coil_id: int) -> DeviceCredential:
        """ESP coil için deterministik credential üretir."""
        username = f"esp_coil_{coil_id}"
        password = self._derive_password(f"esp:{coil_id}")
        cred = DeviceCredential(
            role="esp_coil",
            username=username,
            password=password,
            coil_id=coil_id,
            allowed_publish=[
                f"pemf/coil/{coil_id}/status",
                f"pemf/coil/{coil_id}/sensors",
                f"pemf/coil/{coil_id}/events",
                f"pemf/coil/{coil_id}/ack",
                f"pemf/coil/{coil_id}/system/log",
            ],
            allowed_subscribe=[
                f"pemf/coil/{coil_id}/control",
                "pemf/coil/all/control",  # Broadcast komutları da alabilmeli
            ],
            notes=f"ESP32 Bobin #{coil_id} — Sadece kendi topic'i",
        )
        self._credentials[f"esp_coil_{coil_id}"] = cred
        self._save()
        return cred

    def _create_bridge_credential(self) -> DeviceCredential:
        """LattePanda Mosquitto Bridge için tam yetkili credential."""
        password = self._derive_password("gui_bridge:mosquitto")
        cred = DeviceCredential(
            role="gui_bridge",
            username="gui_bridge",
            password=password,
            coil_id=None,
            allowed_publish=["pemf/#"],
            allowed_subscribe=["pemf/#"],
            notes="LattePanda MQTT Bridge — Tam pemf/# erişimi",
        )
        self._credentials["gui_bridge"] = cred
        self._save()
        return cred

    def _create_android_credential(self, uid: str) -> DeviceCredential:
        """Android uygulaması için sınırlı yetkili credential."""
        username = f"android_{uid}"
        password = self._derive_password(f"android:{uid}")
        cred = DeviceCredential(
            role="android_app",
            username=username,
            password=password,
            coil_id=None,
            allowed_publish=[
                "pemf/coil/+/control",  # Kontrol komutu gönderebilir
                "pemf/coil/all/control",  # Broadcast komutları gönderebilir
            ],
            allowed_subscribe=[
                "pemf/coil/+/status",
                "pemf/coil/+/sensors",
                "pemf/coil/+/events",
                "pemf/coil/+/ack",
                "pemf/system/session",
            ],
            notes=f"Android App ({uid}) — Kontrol + Okuma, yönetim yok",
        )
        self._credentials[f"android_{uid}"] = cred
        self._save()
        return cred

    # ── Yardımcılar ──────────────────────────────────────────────────────

    def _derive_password(self, context: str, length: int = 32) -> str:
        """
        HMAC-SHA256 tabanlı deterministik şifre türetimi.
        Aynı master_secret + context → daima aynı şifre.
        Bu sayede cihaz yeniden flash'lansa bile şifre değişmez.
        """
        h = hmac.new(
            self._master_secret.encode("utf-8"),
            context.encode("utf-8"),
            hashlib.sha256,
        )
        # URL-safe base64 karakter seti ile şifre oluştur
        charset = string.ascii_letters + string.digits + "!@#$%^&*"
        digest_bytes = h.digest()
        # Her byte'ı charset'e eşle
        password = "".join(charset[b % len(charset)] for b in digest_bytes)
        return password[:length]

    @staticmethod
    def _warn_and_use_default() -> str:
        """
        Master secret ortam değişkeni yoksa:
        1. config/pemf_secret.key dosyasından okumayı dene (önceki otomatik üretim)
        2. Dosya da yoksa cryptographically secure bir secret üret ve dosyaya kaydet
        Bu sayede uyarı yalnızca gerçek bir güvenlik sorunu olduğunda çıkar.
        """
        # Audit #17: PEMF_MASTER_SECRET ayarlanmamış. Üretimde set EDİLMELİ (cihazlar/yeniden
        # kurulumlar arası kimlik tutarlılığı + merkezi yönetim). PEMF_REQUIRE_MASTER_SECRET=1
        # ise FAIL-FAST; değilse GÖRÜNÜR uyarı + cihaza özgü otomatik dosya secret'i (çalışır
        # ama taşınmaz/yedeklenmezse kurtarılamaz). Eskiden bu sessizce gerçekleşiyordu.
        if os.environ.get("PEMF_REQUIRE_MASTER_SECRET") == "1":
            raise RuntimeError(
                "PEMF_MASTER_SECRET ayarlanmamış ve PEMF_REQUIRE_MASTER_SECRET=1 → fail-fast "
                "(üretim güvenlik politikası: master secret zorunlu)."
            )
        logger.warning(_DEFAULT_MASTER_SECRET_WARNING)
        secret_file = CREDENTIALS_DIR.parent / "pemf_secret.key"

        # Mevcut secret dosyasını oku
        if secret_file.exists():
            try:
                stored = secret_file.read_text(encoding="utf-8").strip()
                if stored and len(stored) >= 32:
                    logger.debug("PEMF master secret config/pemf_secret.key dosyasından yüklendi.")
                    return stored
            except Exception as e:
                logger.warning(f"Secret dosyası okunamadı: {e}")

        # İlk çalıştırma: yeni, güçlü bir secret otomatik üret ve kaydet
        new_secret = secrets.token_hex(32)  # 256-bit kriptografik rastgelelik
        try:
            CREDENTIALS_DIR.parent.mkdir(parents=True, exist_ok=True)
            secret_file.write_text(new_secret, encoding="utf-8")
            # Yazımdan HEMEN sonra ACL kilidi (Audit P1): eski os.chmod Windows'ta NO-OP'tu →
            # master KDF secret'i yerel 'Users' tarafından okunup TÜM cihaz/ESP/bridge şifreleri
            # türetilebiliyordu. lock_down_file Windows'ta icacls, POSIX'te 0o600 uygular.
            lock_down_file(secret_file)
            logger.info(
                f"PEMF master secret otomatik üretildi ve kaydedildi: {secret_file}\n"
                "Güvenlik için bu dosyayı yedekleyin ve yetkisiz erişime kapatın."
            )
        except Exception as e:
            logger.warning(f"Secret dosyası kaydedilemedi ({e}), oturum için geçici secret kullanılıyor.")

        return new_secret

    def _load(self):
        """Credential dosyasını diskten yükler."""
        if not self._credential_file.exists():
            return
        try:
            data = json.loads(self._credential_file.read_text(encoding="utf-8"))
            for key, value in data.items():
                self._credentials[key] = DeviceCredential(**value)
            logger.info(f"{len(self._credentials)} credential yüklendi.")
        except Exception as e:
            logger.error(f"Credential yükleme hatası: {e}")

    def _save(self):
        """Credential'ları diske kaydeder."""
        try:
            data = {key: asdict(cred) for key, cred in self._credentials.items()}
            self._credential_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            lock_down_file(self._credential_file)  # cihaz cred'leri düz-metin → ACL kilidi (Audit P1)
        except Exception as e:
            logger.error(f"Credential kaydetme hatası: {e}")


# ── CLI ──────────────────────────────────────────────────────────────────────


def _setup_logging():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")


def main():
    import argparse

    _setup_logging()

    parser = argparse.ArgumentParser(description="PEMF Credential Manager")
    subparsers = parser.add_subparsers(dest="command")

    # generate
    gen = subparsers.add_parser("generate", help="Credential oluştur")
    gen.add_argument("--coil-id", type=int, help="ESP Bobin ID (1-8)")
    gen.add_argument("--android-uid", type=str, default="prod", help="Android kullanıcı UID")
    gen.add_argument("--all-coils", type=int, nargs="+", metavar="ID", help="Birden fazla bobin")

    # list
    subparsers.add_parser("list", help="Mevcut credential'ları listele")

    # export
    exp = subparsers.add_parser("export", help="Dışa aktar")
    exp.add_argument("--mosquitto-pass", action="store_true")
    exp.add_argument("--mosquitto-acl", action="store_true")
    exp.add_argument("--hivemq", action="store_true")
    exp.add_argument("--esp-secrets", type=int, metavar="COIL_ID")

    # provision
    prov = subparsers.add_parser("provision", help="Tüm sistemi sıfırdan hazırla")
    prov.add_argument("--coil-ids", type=int, nargs="+", default=list(range(1, 9)), metavar="ID")

    args = parser.parse_args()
    mgr = CredentialManager()

    if args.command == "generate":
        # Audit P3: şifreleri STDOUT'a YAZMA — 'generate > setup.log' ESP/bridge/android düz şifrelerini
        # log/destek-paketi/git'e sızdırıyordu. Şifreler zaten ACL-kilitli export dosyalarında; burada
        # yalnız kullanıcı-adı göster.
        if args.all_coils:
            for cid in args.all_coils:
                c = mgr.get_or_create_esp_credential(cid)
                print(f"  ESP Coil {cid}: user={c.username}")
        elif args.coil_id:
            c = mgr.get_or_create_esp_credential(args.coil_id)
            print(f"  ESP Coil {args.coil_id}: user={c.username}")
        bc = mgr.get_or_create_bridge_credential()
        print(f"  Bridge:       user={bc.username}")
        ac = mgr.get_or_create_android_credential(args.android_uid if hasattr(args, 'android_uid') else "prod")
        print(f"  Android:      user={ac.username}")

    elif args.command == "list":
        for c in mgr.list_credentials():
            print(f"  [{c.role:15s}] {c.username:30s} | {c.notes}")

    elif args.command == "export":
        if args.mosquitto_pass:
            path = mgr.export_mosquitto_password_file()
            print(f"[OK] Mosquitto password file: {path}")
        if args.mosquitto_acl:
            path = mgr.export_acl_file()
            print(f"[OK] Mosquitto ACL file: {path}")
        if args.hivemq:
            path = mgr.export_hivemq_config()
            print(f"[OK] HiveMQ config: {path}")
        if args.esp_secrets:
            path = mgr.export_esp_secrets(args.esp_secrets)
            print(f"[OK] ESP Secrets: {path}")

    elif args.command == "provision":
        print("=== PEMF Sistem Provision ===")
        for coil_id in args.coil_ids:
            c = mgr.get_or_create_esp_credential(coil_id)
            print(f"  [OK] Coil {coil_id}: {c.username}")
        bc = mgr.get_or_create_bridge_credential()
        print(f"  [OK] Bridge: {bc.username}")
        ac = mgr.get_or_create_android_credential("prod")
        print(f"  [OK] Android: {ac.username}")

        mgr.export_mosquitto_password_file()
        mgr.export_acl_file()
        mgr.export_hivemq_config()
        print(f"\n[OK] Tum dosyalar: {CREDENTIALS_DIR}")
        print("\nSonraki adim:")
        print("  1. config/credentials/mosquitto_passwords.txt -> LattePanda'ya kopyala")
        print("  2. mosquitto_passwd -U config/credentials/mosquitto_passwords.txt (hash'le)")
        print("  3. config/credentials/mosquitto_acl.conf -> mosquitto.conf'a ekle")
        print("  4. config/credentials/hivemq_users.json -> HiveMQ Cloud paneline gir")
        print("  5. Her ESP icin: python -m services.credential_manager export --esp-secrets <ID>")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
