"""Qt-free DB bakım/retention/backup/disk-check zamanlayıcısı (headless üretim servisi).

Eski DBMaintenanceService PyQt6 QTimer'a bağlıydı ve yalnız legacy GUI'de başlatılıyordu →
headless backend'de retention/PII-redaction/backup/disk-check HİÇ çalışmıyordu (KVKK/GDPR +
sınırsız veri büyümesi + yedek yok). Bu modül aynı DB metotlarını Qt'siz daemon thread ile
periyodik çağırır. apply_data_retention_policy() purge (sensor/event/outbox) + PII-redaction'ı
zaten içerir.
"""
import logging
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_worker = None  # type: Optional[HeadlessDBMaintenance]


class HeadlessDBMaintenance:
    def __init__(self, app_data_dir=None,
                 maintenance_interval_hours: int = 6,
                 backup_interval_hours: int = 24,
                 disk_check_interval_minutes: int = 30,
                 backup_retention_keep: int = 14):
        from utils.path_utils import get_app_data_directory
        from database.treatment_history_db import get_treatment_db
        self.app_data_dir = Path(app_data_dir) if app_data_dir else get_app_data_directory()
        self.db = get_treatment_db(self.app_data_dir)
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
                if first or now - last_backup >= self.backup_interval:
                    self._run_backup(); last_backup = now
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

    def _run_maintenance(self):
        try:
            m = self.db.run_maintenance()
            r = self.db.apply_data_retention_policy()
            logger.info("DB bakim+retention tamam: maintenance=%s retention=%s", m, r)
        except Exception:
            logger.exception("maintenance hatasi")

    def _run_backup(self):
        try:
            backup_dir = self.app_data_dir / "backups"
            backup_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_file = backup_dir / f"pemf_treatment_history_{stamp}.db"
            if self.db.create_backup(str(backup_file)):
                logger.info("DB yedegi alindi: %s", backup_file)
                self._cleanup_backups(backup_dir)
            else:
                logger.error("DB yedegi BASARISIZ")
        except Exception:
            logger.exception("backup hatasi")

    def _cleanup_backups(self, backup_dir: Path):
        try:
            files = sorted(backup_dir.glob("pemf_treatment_history_*.db"))
            if len(files) > self.backup_retention_keep:
                for old in files[:-self.backup_retention_keep]:
                    try:
                        old.unlink(missing_ok=True)
                    except Exception:
                        pass
        except Exception:
            logger.warning("backup temizlik uyarisi")


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
