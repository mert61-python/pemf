"""Qt-free DB bakım/retention/backup/disk-check zamanlayıcısı (headless üretim servisi).

Eski DBMaintenanceService PyQt6 QTimer'a bağlıydı ve yalnız legacy GUI'de başlatılıyordu →
headless backend'de retention/PII-redaction/backup/disk-check HİÇ çalışmıyordu (KVKK/GDPR +
sınırsız veri büyümesi + yedek yok). Bu modül aynı DB metotlarını Qt'siz daemon thread ile
periyodik çağırır. apply_data_retention_policy() purge (sensor/event/outbox) + PII-redaction'ı
zaten içerir.
"""
import logging
import os
import threading
import time
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# DENETIM P2: off-machine yedeklerin YANINA birakilan kurtarma notu. Kurtarma anindaki kisi
# (baska bir teknisyen, aylar sonra) log'lara bakamaz; "sifreli .db var ama acilmiyor" ile
# bas basa kalmasin diye NE GEREKTIGI dosyanin yanina yazilir.
_OFFSITE_README_NAME = "OKU-KURTARMA.txt"
_OFFSITE_README_TEXT = """PEMF — YEDEK KURTARMA NOTU
=============================================================
Bu dizindeki .db dosyalari SQLCipher ile SIFRELIDIR.

Sifre-cozme anahtari yedegi ALAN MAKINEYE baglidir (Windows DPAPI /
CRYPTPROTECT_LOCAL_MACHINE). Bu yuzden .db dosyalari TEK BASINA yetmez.

KURTARMA ZARFI
  Bu dizinde  kurtarma-zarfi.enc  varsa, veritabani anahtarlari onun icinde
  KURTARMA KODU ile sifreli olarak durur. Kod + zarf ile yedekler BASKA bir
  makinede acilabilir.

  Kurtarma kodu, kurulum makinesinde bir kez uretilip
  <veri-dizini>\\KURTARMA-KODU.txt  dosyasina yazilir ve operator tarafindan
  makine disinda (kasa / parola yoneticisi) saklanmalidir.
  Kod BU DIZINDE SAKLANMAZ — zarf ve kod ayni yerde durursa koruma kalmaz.

NASIL GERI YUKLENIR
  1) Yeni makineye PEMF kurun (henuz baslatmadan).
  2) Anahtarlari zarftan cikarip yerlestirin:
       python tools/kurtarma.py --zarf kurtarma-zarfi.enc --kod <KOD> --yaz
  3) Bu dizindeki  pemf_treatment_history_*.db / pemf_patients_*.db  dosyalarindan
     en yenisini veri dizinine  pemf_treatment_history.db / pemf_patients.db
     adiyla kopyalayin.
  4) Servisi baslatin.

ZARF YOKSA
  Kurtarma icin sunlardan biri gerekir:
    1) Yedegi alan makinedeki  pemf_secrets.json  (yalniz AYNI makinede cozulur), VEYA
    2) Disari alinmis  sqlcipher_key  ve  patient_fernet_key  degerleri.
  Ikisi de yoksa bu yedekler kurtarilamaz.
=============================================================
"""

_worker = None  # type: Optional[HeadlessDBMaintenance]


class HeadlessDBMaintenance:
    def __init__(self, app_data_dir=None,
                 maintenance_interval_hours: int = 6,
                 backup_interval_hours: int = 24,
                 disk_check_interval_minutes: int = 30,
                 backup_retention_keep: int = 14):
        from database.treatment_history_db import get_treatment_db
        from utils.path_utils import get_app_data_directory
        self.app_data_dir = Path(app_data_dir) if app_data_dir else get_app_data_directory()
        self.db = get_treatment_db(self.app_data_dir)
        # audit B-7.2: PatientDB de yedeklensin (eskiden yalnız treatment yedekleniyordu).
        try:
            from database.patient_database import get_patient_database
            self.patient_db = get_patient_database()
        except Exception:
            self.patient_db = None
        self.maint_interval = max(1, maintenance_interval_hours) * 3600
        self.backup_interval = max(1, backup_interval_hours) * 3600
        self.disk_interval = max(1, disk_check_interval_minutes) * 60
        self.backup_retention_keep = max(1, backup_retention_keep)
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._loop, daemon=True, name="DBMaintenance")
        self._thread.start()
        logger.info("Headless DB bakim servisi baslatildi (retention/PII-redaction/backup/disk-check aktif).")

    def stop(self):
        self._stop.set()
        # In-progress bakim/backup turunun bitmesine kisa sure taniy → servis kapanirken
        # yaridan kesik/bozuk SQLite yedegi veya kilitli DB dosyasi birakilmaz.
        t = self._thread
        if t and t.is_alive():
            t.join(timeout=10.0)

    def _loop(self):
        last_maint = last_backup = last_disk = 0.0
        first = True
        while not self._stop.is_set():
            now = time.monotonic()
            try:
                if now - last_disk >= self.disk_interval:
                    self._check_disk(); last_disk = now
                if first or now - last_maint >= self.maint_interval:
                    self._run_maintenance(); last_maint = now
                # DENETIM P2 (restart-dongusu yedek imhasi): kosul `first or ...` idi → servis HER
                # acilista yedek aliyordu. Rotasyon yalnizca son N yedegi tuttugundan, bir crash-loop
                # ya da operatorun art arda yeniden baslatmasi N acilista TUM YEDEK GECMISINI ayni
                # gunun kopyalariyla degistiriyordu (felaket-kurtarma penceresi yok olur).
                # Cozum: acilista yedek al AMA yalnizca diskteki EN YENI yedek bayatsa. Boylece
                # "servis uzun sure kapali kaldi" durumu yine yedeklenir, restart dongusu yedegi imha etmez.
                if (first and not self._recent_backup_exists()) or now - last_backup >= self.backup_interval:
                    self._run_backup(); last_backup = now
                elif first:
                    logger.info("Acilis yedegi ATLANDI: diskte taze yedek var (restart-dongusu korumasi).")
            except Exception:
                logger.exception("DB bakim turu hatasi")
            first = False
            self._stop.wait(60)

    def _check_disk(self):
        try:
            status = self.db.get_disk_space_status()
            if bool(status.get("critical", False)):
                logger.warning("DISK KRITIK: %sMB < %sMB", status.get("free_mb"), status.get("threshold_mb"))
        except Exception:
            logger.exception("disk check hatasi")

    @staticmethod
    def _retain_days(env_name: str, default: int) -> int:
        """Retention suresi (gun). 0 → O ADIM KAPALI. Gecersiz deger → varsayilan."""
        try:
            return int(os.environ.get(env_name, default))
        except (TypeError, ValueError):
            logger.warning("%s gecersiz — varsayilan %d gun kullaniliyor.", env_name, default)
            return default

    def _run_maintenance(self):
        try:
            m = self.db.run_maintenance()
            # DENETIM P2: apply_data_retention_policy() PARAMETRESIZ cagriliyordu → sabit-kodlu
            # 90/365/30/365 gun ZORLANIYORDU ve bobin-calisma kayitlari + seans olaylari
            # GERI DONUSSUZ siliniyor, hasta/operator adlari maskeleniyordu; opt-out YOKTU.
            # Tibbi-hukuki saklama suresi ulkeye/kliniğe gore degisir → operator karari.
            # 0 = o adim KAPALI (hicbir sey silinmez/maskelenmez).
            r = self.db.apply_data_retention_policy(
                sensor_retain_days=self._retain_days("PEMF_RETAIN_SENSOR_DAYS", 90),
                event_retain_days=self._retain_days("PEMF_RETAIN_EVENT_DAYS", 365),
                dead_outbox_retain_days=self._retain_days("PEMF_RETAIN_OUTBOX_DAYS", 30),
                pii_retain_days=self._retain_days("PEMF_RETAIN_PII_DAYS", 365),
            )
            logger.info("DB bakim+retention tamam: maintenance=%s retention=%s", m, r)
        except Exception:
            logger.exception("maintenance hatasi")

    def _recent_backup_exists(self) -> bool:
        """Diskteki EN YENI yedek `backup_interval`'dan taze mi? (restart-dongusu korumasi)

        "Son yedek ne zaman alindi" bilgisini ayri bir durum dosyasinda tutmak yerine yedek
        dosyalarinin KENDI mtime'indan turetiyoruz — surec yeniden basladiginda da gecerli
        kalan tek gercek kaynak budur.
        """
        try:
            backup_dir = self.app_data_dir / "backups"
            newest = max(
                (p.stat().st_mtime for p in backup_dir.glob("pemf_treatment_history_*.db")),
                default=0.0,
            )
            return newest > 0.0 and (time.time() - newest) < self.backup_interval
        except Exception:
            logger.debug("yedek tazelik kontrolu basarisiz", exc_info=True)
            return False   # emin degilsek yedek AL (veri kaybetmektense fazladan yedek)

    def _run_backup(self):
        try:
            backup_dir = self.app_data_dir / "backups"
            backup_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            created = []
            # Tedavi geçmişi DB'si.
            backup_file = backup_dir / f"pemf_treatment_history_{stamp}.db"
            if self.db.create_backup(str(backup_file)):
                logger.info("Tedavi DB yedegi alindi: %s", backup_file)
                created.append(backup_file)
            else:
                logger.error("Tedavi DB yedegi BASARISIZ")
            # audit B-7.2: Hasta DB'si (eskiden yedeklenmiyordu).
            if self.patient_db is not None:
                pfile = backup_dir / f"pemf_patients_{stamp}.db"
                try:
                    if self.patient_db.create_backup(str(pfile)):
                        logger.info("Hasta DB yedegi alindi: %s", pfile)
                        created.append(pfile)
                except Exception:
                    logger.warning("Hasta DB yedegi hatasi", exc_info=True)
            self._cleanup_backups(backup_dir)
            # DENETIM: kurtarma zarfi .db'lerden ONCE yazilir ki off-site kopyaya da GİRSİN —
            # zarfsiz bir off-site kopya donanim arizasindan sonra acilamaz.
            env = self._refresh_recovery(backup_dir)
            if env is not None:
                created.append(env)
            self._copy_offsite(created)  # audit B-7.2: off-machine kopya (PEMF_BACKUP_DIR)
        except Exception:
            logger.exception("backup hatasi")

    def _refresh_recovery(self, backup_dir: Path):
        """DENETIM (offsite-backup-no-key-escrow): yedeklerin yanina kurtarma zarfini yaz.

        Zarf olmadan hicbir yedek — yerel ya da off-site — donanim arizasindan sonra
        acilamazdi (anahtar DPAPI ile makineye bagli). Zarf, sistem uretimi 150-bit
        kurtarma koduyla sifrelidir; kod operatorde, zarf yedeklerin yaninda durur.

        Yedek almanin KENDISI bundan etkilenmemeli → tum hatalar yutulur (zarf
        yazilamasa bile .db yedekleri alinmis olur). Returns: zarf yolu ya da None.
        """
        try:
            from utils.backup_recovery import ENVELOPE_NAME, refresh_recovery_material
            if refresh_recovery_material(self.app_data_dir, [backup_dir]):
                p = backup_dir / ENVELOPE_NAME
                return p if p.exists() else None
        except Exception:
            logger.warning("kurtarma zarfi guncellenemedi (yedekler ALINDI)", exc_info=True)
        return None

    def _cleanup_backups(self, backup_dir: Path):
        # Her iki yedek ailesini de ayrı ayrı rotasyona sok (son N).
        for pattern in ("pemf_treatment_history_*.db", "pemf_patients_*.db"):
            try:
                files = sorted(backup_dir.glob(pattern))
                if len(files) > self.backup_retention_keep:
                    for old in files[:-self.backup_retention_keep]:
                        try:
                            old.unlink(missing_ok=True)
                        except Exception:
                            pass
            except Exception:
                logger.warning("backup temizlik uyarisi (%s)", pattern)

    def _copy_offsite(self, files):
        """audit B-7.2: PEMF_BACKUP_DIR set ise YENİ yedekleri harici hedefe (ağ paylaşımı/USB) kopyala
        → aynı-disk yedek felaketi (disk arızası/ransomware) tek nokta olmasın. Set değilse no-op."""
        import os
        import shutil
        dest = os.environ.get("PEMF_BACKUP_DIR", "").strip()
        if not dest or not files:
            return
        try:
            dpath = Path(dest)
            dpath.mkdir(parents=True, exist_ok=True)
            for f in files:
                try:
                    shutil.copy2(f, dpath / Path(f).name)
                except Exception:
                    logger.warning("off-machine kopya hatasi: %s", f, exc_info=True)
            # DENETIM P2 (yanlis guvence): eskiden yalnizca "kopyalandi" bilgisi loglaniyordu; bu,
            # yedeklerin FELAKET KURTARMA icin kullanilabilir oldugu izlenimini veriyordu. Oysa
            # kopyalanan .db dosyalari SQLCipher ile sifreli ve onlari acan anahtar
            # pemf_secrets.json icinde CRYPTPROTECT_LOCAL_MACHINE (DPAPI) ile MAKINEYE bagliydi
            # → anakart/disk arizasinda bu yedekler ACILAMIYORDU. Cozuldu: _refresh_recovery
            # yedeklerin yanina kurtarma zarfini yaziyor. Zarfin GERCEKTEN yerinde olup
            # olmadigina gore log seviyesi degisir — "kopyalandi" demek yetmez, kurtarilabilir
            # olup olmadigini soylemek gerekir.
            from utils.backup_recovery import ENVELOPE_NAME as _ENV_NAME
            if (dpath / _ENV_NAME).exists():
                logger.info(
                    "Yedekler off-machine kopyalandi: %s (%d dosya). Kurtarma zarfi (%s) yerinde → "
                    "KURTARMA KODU ile baska makinede geri yuklenebilir.", dest, len(files), _ENV_NAME)
            else:
                logger.warning(
                    "Yedekler off-machine kopyalandi: %s (%d dosya). DIKKAT: kurtarma zarfi (%s) YOK "
                    "→ bu dosyalar SQLCipher ile sifreli ve anahtar BU MAKINEYE bagli (DPAPI); donanim "
                    "arizasinda ACILAMAZLAR. bkz. %s", dest, len(files), _ENV_NAME, _OFFSITE_README_NAME)
            # Yedeklerin YANINA ne gerektigini yaz: kurtarma anindaki kisi log'lara bakamayabilir.
            try:
                (dpath / _OFFSITE_README_NAME).write_text(_OFFSITE_README_TEXT, encoding="utf-8")
            except Exception:
                logger.debug("off-machine kurtarma notu yazilamadi", exc_info=True)
        except Exception:
            logger.warning("off-machine backup dizini hatasi (%s)", dest, exc_info=True)


def start_headless_db_maintenance(app_data_dir=None):
    """Idempotent — headless backend startup'ından çağrılır."""
    global _worker
    if _worker is None:
        try:
            _worker = HeadlessDBMaintenance(app_data_dir)
            _worker.start()
        except Exception:
            logger.exception("Headless DB bakim servisi baslatilamadi")
    return _worker


def stop_headless_db_maintenance():
    """Idempotent — shutdown'da çağrılır. In-progress backup/maintenance turunun bitmesini
    kisa sure bekler (join) → bozuk yedek/kilitli DB birakmaz. Eskiden HIC durdurulmuyordu."""
    global _worker
    if _worker is not None:
        try:
            _worker.stop()
        except Exception:
            logger.exception("Headless DB bakim servisi durdurulamadi")
        _worker = None
