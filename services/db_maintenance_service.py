"""DB Maintenance Service - scheduled maintenance/backup/retention for production."""

import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

try:
    from database.treatment_history_db import get_treatment_db
    from utils.path_utils import get_app_data_directory
except ModuleNotFoundError:
    # Support direct script execution (e.g. Spyder %runfile)
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    from database.treatment_history_db import get_treatment_db
    from utils.path_utils import get_app_data_directory

logger = logging.getLogger(__name__)


class DBMaintenanceService(QObject):
    """Periyodik DB bakım, backup ve retention policy servisi."""

    maintenance_completed = pyqtSignal(dict)
    backup_completed = pyqtSignal(str)
    maintenance_failed = pyqtSignal(str)
    disk_space_critical = pyqtSignal(dict)

    def __init__(self,
                 app_data_dir: Optional[Path] = None,
                 maintenance_interval_hours: int = 6,
                 backup_interval_hours: int = 24,
                 disk_check_interval_minutes: int = 1,
                 backup_retention_days: int = 14,
                 parent=None):
        super().__init__(parent)
        self._app_data_dir = app_data_dir or get_app_data_directory()
        self._db = get_treatment_db(self._app_data_dir)
        self._backup_retention_days = max(1, int(backup_retention_days))

        self._maintenance_timer = QTimer(self)
        self._maintenance_timer.timeout.connect(self.run_maintenance_now)
        self._maintenance_interval_ms = max(1, int(maintenance_interval_hours)) * 3600 * 1000

        self._backup_timer = QTimer(self)
        self._backup_timer.timeout.connect(self.run_backup_now)
        self._backup_interval_ms = max(1, int(backup_interval_hours)) * 3600 * 1000

        self._disk_timer = QTimer(self)
        self._disk_timer.timeout.connect(self.check_disk_space_now)
        self._disk_interval_ms = max(1, int(disk_check_interval_minutes)) * 60 * 1000

    def start(self):
        """Servisi başlat."""
        self._maintenance_timer.start(self._maintenance_interval_ms)
        self._backup_timer.start(self._backup_interval_ms)
        self._disk_timer.start(self._disk_interval_ms)
        logger.info("DBMaintenanceService started")

    def stop(self):
        """Servisi durdur."""
        self._maintenance_timer.stop()
        self._backup_timer.stop()
        self._disk_timer.stop()
        logger.info("DBMaintenanceService stopped")

    def check_disk_space_now(self) -> Dict[str, object]:
        """Disk alanı kritik mi kontrol et, kritikse sinyal üret."""
        status = self._db.get_disk_space_status()
        if bool(status.get('critical', False)):
            msg = (
                f"Disk alanı kritik: {status.get('free_mb')}MB < "
                f"{status.get('threshold_mb')}MB"
            )
            self.maintenance_failed.emit(msg)
            self.disk_space_critical.emit(status)
            logger.warning(msg)
        return status

    def run_maintenance_now(self) -> Dict[str, object]:
        """Bakım + retention işlemini hemen çalıştır."""
        try:
            maintenance_report = self._db.run_maintenance()
            retention_report = self._db.apply_data_retention_policy()
            result = {
                'maintenance': maintenance_report,
                'retention': retention_report,
                'health': self._db.get_database_health_snapshot(),
            }
            self.maintenance_completed.emit(result)
            return result
        except Exception as e:
            error_msg = f"DB maintenance error: {e}"
            self.maintenance_failed.emit(error_msg)
            logger.error(error_msg)
            return {'error': error_msg}

    def run_backup_now(self) -> str:
        """Yedeği hemen üret ve eski yedekleri temizle."""
        backup_dir = self._app_data_dir / 'backups'
        backup_dir.mkdir(parents=True, exist_ok=True)

        stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_file = backup_dir / f'pemf_treatment_history_{stamp}.db'

        if self._db.create_backup(str(backup_file)):
            self._cleanup_old_backups(backup_dir)
            self.backup_completed.emit(str(backup_file))
            logger.info(f"DB backup completed: {backup_file}")
            return str(backup_file)

        error_msg = "DB backup failed"
        self.maintenance_failed.emit(error_msg)
        logger.error(error_msg)
        return ""

    def _cleanup_old_backups(self, backup_dir: Path):
        """Retention dışı backup dosyalarını temizle."""
        try:
            files = sorted(backup_dir.glob('pemf_treatment_history_*.db'))
            max_keep = self._backup_retention_days
            if len(files) <= max_keep:
                return
            for old_file in files[:-max_keep]:
                try:
                    old_file.unlink(missing_ok=True)
                except Exception:
                    pass
        except Exception as e:
            logger.warning(f"Backup cleanup warning: {e}")
