"""
Tedavi Geçmişi Veritabanı Modülü
PEMF tedavi seanslarının kaydedilmesi ve yönetimi için SQLite veritabanı
"""

import sqlite3
import os
import shutil
import json
import uuid
import hashlib
import logging
import threading
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from contextlib import contextmanager

try:
    import keyring
except Exception:  # pragma: no cover - optional dependency fallback
    keyring = None

class TreatmentHistoryDB:
    """PEMF tedavi geçmişi veritabanı yönetim sınıfı (Connection Pool + WAL mode)"""

    TARGET_SCHEMA_VERSION = 3
    MIN_FREE_DISK_MB = 500
    
    def __init__(self, app_data_dir):
        """
        Veritabanı bağlantısını başlat
        
        Args:
            app_data_dir: Uygulama veri dizini (Path). Veritabanı dosyası bu dizinde oluşturulur.
        """
        app_data_dir.mkdir(parents=True, exist_ok=True)
        self.app_data_dir = app_data_dir
        self.db_path = app_data_dir / "pemf_treatment_history.db"
        self.logger = logging.getLogger(__name__)
        self._disk_usage_provider = shutil.disk_usage
        
        # HIGH FIX: Thread-local connection storage (connection pool pattern)
        self._local = threading.local()
        self._lock = threading.Lock()
        
        # Veritabanını başlat
        self._init_database()
        self._run_startup_migrations_with_rollback()
        self.recover_stale_active_sessions(max_age_hours=12)

    def _connect_plain_sqlite(self):
        """Standart sqlite3 bağlantısı oluştur."""
        conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _get_sqlcipher_key(self) -> str:
        """SQLCipher anahtarını önce Credential Manager/keyring'den alır."""
        service_name = "PEMF_GUI"
        key_name = "sqlcipher_key"

        if keyring is not None:
            try:
                credential_key = (keyring.get_password(service_name, key_name) or "").strip()
                if credential_key:
                    return credential_key
            except Exception as e:
                self.logger.warning(f"Credential Manager okuma hatası, fallback denenecek: {e}")

        env_key = os.getenv('PEMF_SQLCIPHER_KEY', '').strip()
        if env_key:
            self.logger.warning("PEMF_SQLCIPHER_KEY kullanımı deprecated; keyring/Credential Manager kullanın")
        return env_key

    def _connect_sqlcipher_if_configured(self):
        """SQLCipher anahtarı varsa SQLCipher bağlantısı dene, yoksa None döndür."""
        cipher_key = self._get_sqlcipher_key()
        if not cipher_key:
            return None

        try:
            from pysqlcipher3 import dbapi2 as sqlcipher  # type: ignore
            conn = sqlcipher.connect(self.db_path, check_same_thread=False, timeout=10.0)
            conn.row_factory = sqlite3.Row
            escaped_key = cipher_key.replace("'", "''")
            conn.execute(f"PRAGMA key='{escaped_key}'")
            conn.execute('SELECT count(*) FROM sqlite_master')
            self.logger.info("SQLCipher bağlantısı aktif")
            return conn
        except Exception as e:
            self.logger.warning(f"SQLCipher etkinleştirilemedi, sqlite3 fallback kullanılacak: {e}")
            return None

    def _create_connection(self):
        """Yeni SQLite bağlantısı oluştur ve bağlantı ayarlarını uygula."""
        conn = self._connect_sqlcipher_if_configured() or self._connect_plain_sqlite()
        conn.execute('PRAGMA foreign_keys=ON')
        conn.execute('PRAGMA busy_timeout=5000')

        # WAL bazı disk/ortam kombinasyonlarında başarısız olabilir.
        try:
            # Eğer zaten WAL modundaysa tekrar set etmeye çalışıp kilit (lock) hatası alma
            current_mode = conn.execute('PRAGMA journal_mode').fetchone()[0]
            if current_mode.upper() != 'WAL':
                conn.execute('PRAGMA journal_mode=WAL')
            
            conn.execute('PRAGMA synchronous=NORMAL')
            conn.execute('PRAGMA wal_autocheckpoint=1000')
            conn.execute('PRAGMA journal_size_limit=33554432')
        except sqlite3.OperationalError as e:
            # Beklenen bir durum olabildiğinden bunu DEBUG seviyesinde logluyoruz (Uyarıyı gizler)
            self.logger.debug(f"WAL modu ayarlanamadı (zaten açık veya kilitli olabilir), DELETE moda geçiliyor: {e}")
            try:
                conn.close()
            except Exception:
                pass

            conn = self._connect_plain_sqlite()
            conn.execute('PRAGMA foreign_keys=ON')
            conn.execute('PRAGMA busy_timeout=5000')
            try:
                conn.execute('PRAGMA journal_mode=DELETE')
                conn.execute('PRAGMA synchronous=FULL')
            except sqlite3.OperationalError as fallback_err:
                self.logger.error(f"Fallback DELETE modu da hataya düştü: {fallback_err}")

        return conn

    def get_disk_space_status(self) -> Dict[str, object]:
        """DB volume disk alanı durumunu döndür."""
        usage = self._disk_usage_provider(self.db_path.parent)
        free_mb = int(usage.free / (1024 * 1024))
        return {
            'total_bytes': int(usage.total),
            'used_bytes': int(usage.used),
            'free_bytes': int(usage.free),
            'free_mb': free_mb,
            'critical': free_mb < self.MIN_FREE_DISK_MB,
            'threshold_mb': self.MIN_FREE_DISK_MB,
        }

    def _ensure_write_guardrail(self):
        """Kritik düşük disk alanında yazma işlemini engelle."""
        status = self.get_disk_space_status()
        if bool(status.get('critical', False)):
            raise RuntimeError(
                f"Disk free space critical: {status.get('free_mb')}MB < {status.get('threshold_mb')}MB"
            )
    
    @contextmanager
    def _get_connection(self):
        """
        HIGH FIX: Thread-safe connection pool context manager.
        Her thread kendi connection'ını kullanır, shared state yok.
        """
        created_in_this_context = False

        # Check if this thread already has a connection
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            # Create new connection for this thread
            self._local.conn = self._create_connection()
            created_in_this_context = True
        
        try:
            yield self._local.conn
        except Exception:
            # Rollback on error
            if getattr(self._local, 'conn', None) is not None:
                self._local.conn.rollback()
            raise
        finally:
            # Worker thread'lerde açılan bağlantıları context sonunda kapat
            # böylece kısa ömürlü thread'lerde connection birikimi olmaz.
            if created_in_this_context and threading.current_thread() is not threading.main_thread():
                try:
                    self._local.conn.close()
                finally:
                    self._local.conn = None
    
    def close_connections(self):
        """Close all thread-local connections (call on shutdown)"""
        if hasattr(self._local, 'conn') and self._local.conn is not None:
            try:
                self._local.conn.close()
                self._local.conn = None
            except Exception as e:
                self.logger.error(f"Error closing connection: {e}")
    
    def _init_database(self):
        """Veritabanı tablolarını oluştur (HIGH FIX: WAL mode enabled)"""
        try:
            # HIGH FIX: Use connection pool
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # Tedavi seansları tablosu
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS treatment_sessions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_date TEXT NOT NULL,
                        start_time TEXT NOT NULL,
                        end_time TEXT,
                        duration_minutes INTEGER,
                        treatment_mode TEXT NOT NULL,
                        target_condition TEXT,
                        frequency_hz REAL,
                        intensity_mt REAL,
                        pulse_duration_ms INTEGER,
                        operator_name TEXT,
                        patient_name TEXT,
                        patient_notes TEXT,
                        session_status TEXT DEFAULT 'completed',
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # Tedavi parametreleri detay tablosu
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS session_parameters (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id INTEGER NOT NULL,
                        parameter_name TEXT NOT NULL,
                        parameter_value TEXT NOT NULL,
                        parameter_unit TEXT,
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (session_id) REFERENCES treatment_sessions (id)
                    )
                ''')
                
                # Sistem ayarları tablosu
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS system_settings (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        setting_key TEXT UNIQUE NOT NULL,
                        setting_value TEXT NOT NULL,
                        description TEXT,
                        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                    )
                ''')

                # Schema migration kayıtları
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS schema_migrations (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        version INTEGER NOT NULL,
                        description TEXT,
                        applied_at TEXT DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(version)
                    )
                ''')

                # Unified outbox (cloud sync kuyruğu)
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS outbox_messages (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        message_uuid TEXT UNIQUE NOT NULL,
                        idempotency_key TEXT,
                        topic TEXT NOT NULL,
                        payload TEXT NOT NULL,
                        qos INTEGER DEFAULT 0,
                        retain INTEGER DEFAULT 0,
                        status TEXT NOT NULL DEFAULT 'pending',
                        retry_count INTEGER NOT NULL DEFAULT 0,
                        available_at REAL NOT NULL,
                        sent_at REAL,
                        last_error TEXT,
                        source TEXT,
                        correlation_id TEXT,
                        created_at REAL NOT NULL
                    )
                ''')

                # Session'e ait ham sensör örnekleri
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS sensor_samples (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id INTEGER NOT NULL,
                        coil_id TEXT NOT NULL,
                        sample_ts REAL NOT NULL,
                        temperature_c REAL,
                        magnetic_field_mt REAL,
                        current_a REAL,
                        pwm_frequency_hz REAL,
                        pwm_duty_percent REAL,
                        payload TEXT,
                        created_at REAL NOT NULL,
                        FOREIGN KEY (session_id) REFERENCES treatment_sessions (id)
                    )
                ''')

                # Session lifecycle / operational events
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS session_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        event_uuid TEXT UNIQUE NOT NULL,
                        session_id INTEGER,
                        event_type TEXT NOT NULL,
                        severity TEXT NOT NULL DEFAULT 'info',
                        payload TEXT,
                        created_at REAL NOT NULL,
                        FOREIGN KEY (session_id) REFERENCES treatment_sessions (id)
                    )
                ''')
                
                # İndeksler oluştur
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_session_date 
                    ON treatment_sessions(session_date)
                ''')
                
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_treatment_mode 
                    ON treatment_sessions(treatment_mode)
                ''')
                
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_session_parameters 
                    ON session_parameters(session_id)
                ''')

                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_outbox_status_available
                    ON outbox_messages(status, available_at)
                ''')

                cursor.execute('''
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_outbox_idempotency
                    ON outbox_messages(idempotency_key)
                    WHERE idempotency_key IS NOT NULL
                ''')

                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_outbox_created_at
                    ON outbox_messages(created_at)
                ''')

                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_session_events_session
                    ON session_events(session_id, created_at)
                ''')

                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_sensor_samples_session_ts
                    ON sensor_samples(session_id, sample_ts)
                ''')

                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_sensor_samples_coil_ts
                    ON sensor_samples(coil_id, sample_ts)
                ''')
                
                # Mevcut tabloya patient_name sütunu ekle (migration)
                try:
                    cursor.execute('ALTER TABLE treatment_sessions ADD COLUMN patient_name TEXT')
                    self.logger.info("patient_name sütunu eklendi")
                except sqlite3.OperationalError:
                    # Sütun zaten varsa hata vermez
                    pass

                # Session bazlı idempotent kimlik
                try:
                    cursor.execute('ALTER TABLE treatment_sessions ADD COLUMN session_uuid TEXT')
                    self.logger.info("session_uuid sütunu eklendi")
                except sqlite3.OperationalError:
                    pass

                try:
                    cursor.execute('ALTER TABLE outbox_messages ADD COLUMN idempotency_key TEXT')
                    self.logger.info("idempotency_key sütunu eklendi")
                except sqlite3.OperationalError:
                    pass

                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_treatment_sessions_uuid
                    ON treatment_sessions(session_uuid)
                ''')
                
                conn.commit()
                self.logger.info(f"Veritabanı başarıyla başlatıldı: {self.db_path}")
                
        except sqlite3.Error as e:
            self.logger.error(f"Veritabanı başlatma hatası: {e}")
            raise

    def _get_system_setting(self, key: str) -> Optional[str]:
        """System setting değeri oku."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'SELECT setting_value FROM system_settings WHERE setting_key = ?',
                    (key,)
                )
                row = cursor.fetchone()
                return str(row['setting_value']) if row else None
        except Exception:
            return None

    def _set_system_setting(self, key: str, value: str, description: str = ''):
        """System setting değeri upsert et."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO system_settings (setting_key, setting_value, description, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(setting_key) DO UPDATE SET
                    setting_value = excluded.setting_value,
                    description = excluded.description,
                    updated_at = CURRENT_TIMESTAMP
            ''', (key, value, description))
            conn.commit()

    def _run_startup_migrations_with_rollback(self):
        """Migration çalıştır; hata olursa backup'tan geri dön."""
        version_key = 'db_schema_version'
        current_raw = self._get_system_setting(version_key)
        current_version = int(current_raw) if current_raw and current_raw.isdigit() else 0

        if current_version >= self.TARGET_SCHEMA_VERSION:
            return

        backup_dir = self.app_data_dir / 'migration_backups'
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = backup_dir / f'pre_migration_v{current_version}_{stamp}.db'

        # Migration öncesi backup
        self.create_backup(str(backup_path))

        try:
            self._ensure_schema_version()
        except Exception as migration_error:
            self.logger.error(f"Schema migration başarısız, rollback deneniyor: {migration_error}")
            try:
                self.close_connections()
                if os.path.exists(self.db_path):
                    os.remove(self.db_path)
                shutil.copy2(backup_path, self.db_path)
                self.logger.warning(f"Migration rollback tamamlandı: {backup_path}")
            except Exception as rollback_error:
                self.logger.error(f"Migration rollback başarısız: {rollback_error}")
                raise
            raise

    def _ensure_schema_version(self):
        """Schema version metadata'sını garanti altına al."""
        version_key = 'db_schema_version'
        current_raw = self._get_system_setting(version_key)
        current_version = int(current_raw) if current_raw and current_raw.isdigit() else 0

        if current_version == 0:
            # İlk kez kurulan veya eski sürümde metadata'sı olmayan DB
            self._set_system_setting(
                version_key,
                str(self.TARGET_SCHEMA_VERSION),
                'PEMF DB schema version'
            )
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'INSERT OR IGNORE INTO schema_migrations (version, description) VALUES (?, ?)',
                    (self.TARGET_SCHEMA_VERSION, 'bootstrap schema version')
                )
                conn.commit()
            return

        if current_version < self.TARGET_SCHEMA_VERSION:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                for version in range(current_version + 1, self.TARGET_SCHEMA_VERSION + 1):
                    cursor.execute(
                        'INSERT OR IGNORE INTO schema_migrations (version, description) VALUES (?, ?)',
                        (version, f'upgrade schema to v{version}')
                    )
                conn.commit()
            self._set_system_setting(
                version_key,
                str(self.TARGET_SCHEMA_VERSION),
                'PEMF DB schema version'
            )

    def get_schema_version(self) -> int:
        """Aktif DB schema version değerini döndür."""
        value = self._get_system_setting('db_schema_version')
        try:
            return int(value) if value is not None else 0
        except (TypeError, ValueError):
            return 0

    def recover_stale_active_sessions(self, max_age_hours: int = 12) -> int:
        """Açık kalmış eski active seansları güvenli şekilde kapat (recovery)."""
        recovered_count = 0
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT id, session_date, start_time
                    FROM treatment_sessions
                    WHERE session_status = 'active'
                ''')
                rows = cursor.fetchall()

                now = datetime.now()
                threshold = now - timedelta(hours=max(1, int(max_age_hours)))

                for row in rows:
                    session_id = int(row['id'])
                    session_date = str(row['session_date'])
                    start_time = str(row['start_time'])

                    try:
                        started_at = datetime.strptime(
                            f"{session_date} {start_time}",
                            '%Y-%m-%d %H:%M:%S'
                        )
                    except ValueError:
                        # Parse edilemeyen kaydı da recovery et
                        started_at = now - timedelta(hours=max_age_hours + 1)

                    if started_at > threshold:
                        continue

                    duration_minutes = max(1, int((now - started_at).total_seconds() / 60))
                    cursor.execute('''
                        UPDATE treatment_sessions
                        SET end_time = ?,
                            duration_minutes = ?,
                            session_status = 'ABORTED_DUE_TO_POWER',
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                    ''', (now.strftime('%H:%M:%S'), duration_minutes, session_id))
                    recovered_count += 1

                conn.commit()

            if recovered_count > 0:
                self.logger.warning(f"Recovery: {recovered_count} stale active session kurtarıldı (ABORTED_DUE_TO_POWER)")
        except Exception as e:
            self.logger.warning(f"Stale session recovery uyarısı: {e}")

        return recovered_count

    def run_integrity_check(self, quick: bool = True) -> Dict[str, object]:
        """SQLite integrity check çalıştır ve sonucu döndür."""
        pragma_name = 'quick_check' if quick else 'integrity_check'
        result = {
            'ok': False,
            'check': pragma_name,
            'details': []
        }
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(f'PRAGMA {pragma_name}')
                rows = cursor.fetchall()
                details = [str(row[0]) for row in rows] if rows else ['unknown']
                result['details'] = details
                result['ok'] = len(details) > 0 and details[0].lower() == 'ok'
        except Exception as e:
            result['details'] = [str(e)]
            result['ok'] = False
        return result

    def get_database_health_snapshot(self) -> Dict[str, object]:
        """DB health snapshot: schema, integrity, session/outbox sayıları."""
        health = {
            'db_path': str(self.db_path),
            'schema_version': self.get_schema_version(),
            'integrity': self.run_integrity_check(quick=True),
            'disk': self.get_disk_space_status(),
            'sessions': {
                'total': 0,
                'active': 0,
                'completed': 0,
                'aborted_recovered': 0,
            },
            'outbox': self.get_outbox_status_counts(),
        }

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT COUNT(*) FROM treatment_sessions')
                health['sessions']['total'] = int(cursor.fetchone()[0])

                cursor.execute("SELECT COUNT(*) FROM treatment_sessions WHERE session_status = 'active'")
                health['sessions']['active'] = int(cursor.fetchone()[0])

                cursor.execute("SELECT COUNT(*) FROM treatment_sessions WHERE session_status = 'completed'")
                health['sessions']['completed'] = int(cursor.fetchone()[0])

                cursor.execute("SELECT COUNT(*) FROM treatment_sessions WHERE session_status = 'aborted_recovered'")
                health['sessions']['aborted_recovered'] = int(cursor.fetchone()[0])
        except Exception as e:
            health['integrity']['ok'] = False
            health['integrity']['details'].append(f'health snapshot error: {e}')

        return health

    def run_maintenance(self) -> Dict[str, object]:
        """Periyodik DB bakım işlemleri: checkpoint + optimize + quick_check."""
        report = {
            'checkpoint': None,
            'optimize': False,
            'integrity': None,
        }
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                try:
                    cursor.execute('PRAGMA wal_checkpoint(TRUNCATE)')
                    row = cursor.fetchone()
                    report['checkpoint'] = list(row) if row else None
                except Exception:
                    report['checkpoint'] = None

                try:
                    cursor.execute('PRAGMA optimize')
                    report['optimize'] = True
                except Exception:
                    report['optimize'] = False

            report['integrity'] = self.run_integrity_check(quick=True)
        except Exception as e:
            report['integrity'] = {'ok': False, 'check': 'quick_check', 'details': [str(e)]}
        return report

    def create_backup(self, backup_path: str) -> bool:
        """Çalışan DB'den dosya yedeği üret (online backup API)."""
        try:
            backup_dir = os.path.dirname(backup_path)
            if backup_dir:
                os.makedirs(backup_dir, exist_ok=True)

            with self._get_connection() as src_conn:
                dst_conn = sqlite3.connect(backup_path)
                try:
                    src_conn.backup(dst_conn)
                    dst_conn.commit()
                finally:
                    dst_conn.close()
            return True
        except Exception as e:
            self.logger.error(f"DB backup hatası: {e}")
            return False

    def redact_old_session_pii(self, retain_days: int = 365) -> Dict[str, int]:
        """Eski seans kayıtlarında PII alanlarını maskele."""
        report = {
            'sessions_redacted': 0,
            'parameters_redacted': 0,
        }
        cutoff_date = (datetime.now() - timedelta(days=max(1, int(retain_days)))).strftime('%Y-%m-%d')

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute('''
                    UPDATE treatment_sessions
                    SET patient_name = CASE WHEN patient_name IS NOT NULL AND patient_name != '' THEN '[REDACTED]' ELSE patient_name END,
                        operator_name = CASE WHEN operator_name IS NOT NULL AND operator_name != '' THEN '[REDACTED]' ELSE operator_name END,
                        patient_notes = CASE WHEN patient_notes IS NOT NULL AND patient_notes != '' THEN '[REDACTED]' ELSE patient_notes END,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE session_date < ?
                ''', (cutoff_date,))
                report['sessions_redacted'] = int(cursor.rowcount)

                cursor.execute('''
                    UPDATE session_parameters
                    SET parameter_value = '[REDACTED]'
                    WHERE session_id IN (
                        SELECT id FROM treatment_sessions WHERE session_date < ?
                    )
                    AND parameter_name IN (
                        'patient_name', 'patient_surname', 'patient_owner', 'patient_vet_contact',
                        'patient_veteriner', 'patient_email', 'patient_phone', 'patient_address',
                        'patient_medical_history'
                    )
                ''', (cutoff_date,))
                report['parameters_redacted'] = int(cursor.rowcount)

                conn.commit()
        except Exception as e:
            self.logger.warning(f"PII redaction uyarısı: {e}")

        return report

    def purge_old_sensor_samples(self, retain_days: int = 90) -> int:
        """Retention süresini aşan sensör örneklerini temizle."""
        cutoff_ts = datetime.now().timestamp() - (max(1, int(retain_days)) * 86400)
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM sensor_samples WHERE sample_ts < ?', (cutoff_ts,))
                removed = int(cursor.rowcount)
                conn.commit()
                return removed
        except Exception as e:
            self.logger.warning(f"Sensor retention temizleme uyarısı: {e}")
            return 0

    def purge_old_session_events(self, retain_days: int = 365) -> int:
        """Retention süresini aşan session event kayıtlarını temizle."""
        cutoff_ts = datetime.now().timestamp() - (max(1, int(retain_days)) * 86400)
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM session_events WHERE created_at < ?', (cutoff_ts,))
                removed = int(cursor.rowcount)
                conn.commit()
                return removed
        except Exception as e:
            self.logger.warning(f"Session event retention temizleme uyarısı: {e}")
            return 0

    def purge_old_dead_outbox(self, retain_days: int = 30) -> int:
        """Uzun süreli dead outbox kayıtlarını temizle."""
        cutoff_ts = datetime.now().timestamp() - (max(1, int(retain_days)) * 86400)
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    DELETE FROM outbox_messages
                    WHERE status = 'dead' AND available_at < ?
                ''', (cutoff_ts,))
                removed = int(cursor.rowcount)
                conn.commit()
                return removed
        except Exception as e:
            self.logger.warning(f"Dead outbox retention temizleme uyarısı: {e}")
            return 0

    def apply_data_retention_policy(self,
                                    sensor_retain_days: int = 90,
                                    event_retain_days: int = 365,
                                    dead_outbox_retain_days: int = 30,
                                    pii_retain_days: int = 365) -> Dict[str, int]:
        """Toplu retention policy uygula (ticari operasyon bakımı)."""
        report = {
            'sensor_samples_removed': 0,
            'session_events_removed': 0,
            'dead_outbox_removed': 0,
            'sessions_pii_redacted': 0,
            'parameters_pii_redacted': 0,
        }

        report['sensor_samples_removed'] = self.purge_old_sensor_samples(sensor_retain_days)
        report['session_events_removed'] = self.purge_old_session_events(event_retain_days)
        report['dead_outbox_removed'] = self.purge_old_dead_outbox(dead_outbox_retain_days)

        pii_report = self.redact_old_session_pii(pii_retain_days)
        report['sessions_pii_redacted'] = int(pii_report.get('sessions_redacted', 0))
        report['parameters_pii_redacted'] = int(pii_report.get('parameters_redacted', 0))

        return report
    
    def start_session(self, treatment_mode: str, target_condition: str = None, 
                     operator_name: str = None, patient_name: str = None) -> int:
        """
        Yeni tedavi seansı başlat
        
        Args:
            treatment_mode: Tedavi modu (Autonomous, Manual, vb.)
            target_condition: Hedef durum (artrit, yara iyileşmesi, vb.)
            operator_name: Uygulayıcı adı
            patient_name: Hasta adı
            
        Returns:
            int: Oluşturulan seans ID'si
        """
        try:
            self._ensure_write_guardrail()
            # HIGH FIX: Use connection pool instead of new connection
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                now = datetime.now()
                session_date = now.strftime('%Y-%m-%d')
                start_time = now.strftime('%H:%M:%S')
                session_uuid = str(uuid.uuid4())
                
                cursor.execute('''
                    INSERT INTO treatment_sessions 
                    (session_date, start_time, treatment_mode, target_condition, 
                     operator_name, patient_name, session_status, session_uuid)
                    VALUES (?, ?, ?, ?, ?, ?, 'active', ?)
                ''', (session_date, start_time, treatment_mode, target_condition, operator_name, patient_name, session_uuid))
                
                session_id = cursor.lastrowid
                conn.commit()
                
                self.logger.info(f"Yeni tedavi seansı başlatıldı: ID {session_id}")
                return session_id
                
        except sqlite3.Error as e:
            self.logger.error(f"Seans başlatma hatası: {e}")
            raise
    
    def end_session(self, session_id: int, parameters: Dict = None, 
                   patient_notes: str = None, duration_minutes: int = None):
        """
        Tedavi seansını sonlandır
        
        Args:
            session_id: Seans ID'si
            parameters: Tedavi parametreleri sözlüğü
            patient_notes: Hasta notları
        """
        try:
            self._ensure_write_guardrail()
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # Seans bilgilerini al
                cursor.execute('''
                    SELECT start_time, session_date FROM treatment_sessions 
                    WHERE id = ?
                ''', (session_id,))
                
                result = cursor.fetchone()
                if not result:
                    raise ValueError(f"Seans bulunamadı: {session_id}")
                
                start_time_str, session_date = result
                
                # Süreyi hesapla (opsiyonel override varsa kullan)
                now = datetime.now()
                end_time = now.strftime('%H:%M:%S')

                if duration_minutes is None:
                    start_datetime = datetime.strptime(f"{session_date} {start_time_str}", 
                                                     '%Y-%m-%d %H:%M:%S')
                    duration_minutes = int((now - start_datetime).total_seconds() / 60)
                
                # Seans bilgilerini güncelle
                update_data = [end_time, duration_minutes, 'completed', session_id]
                update_query = '''
                    UPDATE treatment_sessions 
                    SET end_time = ?, duration_minutes = ?, session_status = ?,
                        updated_at = CURRENT_TIMESTAMP
                '''
                
                if parameters:
                    # Ana parametreleri güncelle
                    if 'frequency_hz' in parameters:
                        update_query += ', frequency_hz = ?'
                        update_data.insert(-1, parameters['frequency_hz'])
                    if 'intensity_mt' in parameters:
                        update_query += ', intensity_mt = ?'
                        update_data.insert(-1, parameters['intensity_mt'])
                    if 'pulse_duration_ms' in parameters:
                        update_query += ', pulse_duration_ms = ?'
                        update_data.insert(-1, parameters['pulse_duration_ms'])
                
                if patient_notes:
                    update_query += ', patient_notes = ?'
                    update_data.insert(-1, patient_notes)
                
                update_query += ' WHERE id = ?'
                
                cursor.execute(update_query, update_data)
                
                # Detaylı parametreleri kaydet
                if parameters:
                    for param_name, param_value in parameters.items():
                        if param_name not in ['frequency_hz', 'intensity_mt', 'pulse_duration_ms']:
                            cursor.execute('''
                                INSERT INTO session_parameters 
                                (session_id, parameter_name, parameter_value)
                                VALUES (?, ?, ?)
                            ''', (session_id, param_name, str(param_value)))
                
                conn.commit()
                self.logger.info(f"Tedavi seansı sonlandırıldı: ID {session_id}")
                
        except sqlite3.Error as e:
            self.logger.error(f"Seans sonlandırma hatası: {e}")
            raise
    
    def get_session_history(self, limit: int = 100, 
                           start_date: str = None, 
                           end_date: str = None,
                           treatment_mode: str = None) -> List[Dict]:
        """
        Tedavi geçmişini getir
        
        Args:
            limit: Maksimum kayıt sayısı
            start_date: Başlangıç tarihi (YYYY-MM-DD)
            end_date: Bitiş tarihi (YYYY-MM-DD)
            treatment_mode: Tedavi modu filtresi
            
        Returns:
            List[Dict]: Tedavi seansları listesi
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                query = '''
                    SELECT ts.id, ts.session_date, ts.start_time, ts.end_time, ts.duration_minutes,
                           ts.treatment_mode, ts.target_condition, ts.frequency_hz, ts.intensity_mt,
                           ts.pulse_duration_ms, ts.operator_name, ts.patient_notes, ts.session_status,
                           sp_name.parameter_value as patient_name,
                           sp_surname.parameter_value as patient_surname,
                           sp_age.parameter_value as patient_age,
                           sp_species.parameter_value as patient_species,
                           sp_breed.parameter_value as patient_breed,
                           sp_weight.parameter_value as patient_weight,
                           sp_owner.parameter_value as patient_owner,
                           sp_vet.parameter_value as patient_vet_contact,
                           sp_veteriner.parameter_value as patient_veteriner,
                           sp_duration.parameter_value as treatment_duration
                    FROM treatment_sessions ts
                    LEFT JOIN session_parameters sp_name ON ts.id = sp_name.session_id AND sp_name.parameter_name = 'patient_name'
                    LEFT JOIN session_parameters sp_surname ON ts.id = sp_surname.session_id AND sp_surname.parameter_name = 'patient_surname'
                    LEFT JOIN session_parameters sp_age ON ts.id = sp_age.session_id AND sp_age.parameter_name = 'patient_age'
                    LEFT JOIN session_parameters sp_species ON ts.id = sp_species.session_id AND sp_species.parameter_name = 'patient_species'
                    LEFT JOIN session_parameters sp_breed ON ts.id = sp_breed.session_id AND sp_breed.parameter_name = 'patient_breed'
                    LEFT JOIN session_parameters sp_weight ON ts.id = sp_weight.session_id AND sp_weight.parameter_name = 'patient_weight'
                    LEFT JOIN session_parameters sp_owner ON ts.id = sp_owner.session_id AND sp_owner.parameter_name = 'patient_owner'
                    LEFT JOIN session_parameters sp_vet ON ts.id = sp_vet.session_id AND sp_vet.parameter_name = 'patient_vet_contact'
                    LEFT JOIN session_parameters sp_veteriner ON ts.id = sp_veteriner.session_id AND sp_veteriner.parameter_name = 'patient_veteriner'
                    LEFT JOIN session_parameters sp_duration ON ts.id = sp_duration.session_id AND sp_duration.parameter_name = 'duration'
                    WHERE 1=1
                '''
                params = []
                
                if start_date:
                    query += ' AND session_date >= ?'
                    params.append(start_date)
                
                if end_date:
                    query += ' AND session_date <= ?'
                    params.append(end_date)
                
                if treatment_mode:
                    query += ' AND treatment_mode = ?'
                    params.append(treatment_mode)
                
                query += ' ORDER BY session_date DESC, start_time DESC LIMIT ?'
                params.append(limit)
                
                cursor.execute(query, params)
                rows = cursor.fetchall()
                
                # Sonuçları sözlük formatına çevir
                columns = [desc[0] for desc in cursor.description]
                sessions = []
                
                for row in rows:
                    session = dict(zip(columns, row))
                    sessions.append(session)
                
                return sessions
                
        except sqlite3.Error as e:
            self.logger.error(f"Geçmiş getirme hatası: {e}")
            raise
    
    def get_session_details(self, session_id: int) -> Optional[Dict]:
        """
        Belirli bir seansın detaylarını getir
        
        Args:
            session_id: Seans ID'si
            
        Returns:
            Dict: Seans detayları ve parametreleri
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # Ana seans bilgileri
                cursor.execute('''
                    SELECT * FROM treatment_sessions WHERE id = ?
                ''', (session_id,))
                
                session_row = cursor.fetchone()
                if not session_row:
                    return None
                
                columns = [desc[0] for desc in cursor.description]
                session = dict(zip(columns, session_row))
                
                # Parametreler
                cursor.execute('''
                    SELECT parameter_name, parameter_value, parameter_unit
                    FROM session_parameters WHERE session_id = ?
                ''', (session_id,))
                
                parameters = {}
                for param_row in cursor.fetchall():
                    param_name, param_value, param_unit = param_row
                    parameters[param_name] = {
                        'value': param_value,
                        'unit': param_unit
                    }
                
                session['parameters'] = parameters
                return session
                
        except sqlite3.Error as e:
            self.logger.error(f"Seans detayları getirme hatası: {e}")
            raise
    
    def get_statistics(self) -> Dict:
        """
        Tedavi istatistiklerini getir
        
        Returns:
            Dict: İstatistik bilgileri
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                stats = {}
                
                # Toplam seans sayısı
                cursor.execute('SELECT COUNT(*) FROM treatment_sessions')
                stats['total_sessions'] = cursor.fetchone()[0]
                
                # Bu ay seans sayısı
                current_month = datetime.now().strftime('%Y-%m')
                cursor.execute('''
                    SELECT COUNT(*) FROM treatment_sessions 
                    WHERE session_date LIKE ?
                ''', (f"{current_month}%",))
                stats['monthly_sessions'] = cursor.fetchone()[0]
                
                # Tedavi modlarına göre dağılım
                cursor.execute('''
                    SELECT treatment_mode, COUNT(*) 
                    FROM treatment_sessions 
                    GROUP BY treatment_mode
                ''')
                stats['mode_distribution'] = dict(cursor.fetchall())
                
                # Ortalama seans süresi
                cursor.execute('''
                    SELECT AVG(duration_minutes) 
                    FROM treatment_sessions 
                    WHERE duration_minutes IS NOT NULL
                ''')
                avg_duration = cursor.fetchone()[0]
                stats['average_duration'] = round(avg_duration, 1) if avg_duration else 0
                
                return stats
                
        except sqlite3.Error as e:
            self.logger.error(f"İstatistik getirme hatası: {e}")
            raise
    
    def update_session_notes(self, session_id: int, notes: str):
        """
        Tedavi seansının notlarını güncelle
        
        Args:
            session_id: Güncellenecek seans ID'si
            notes: Yeni notlar
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    UPDATE treatment_sessions 
                    SET patient_notes = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (notes, session_id))
                
                conn.commit()
                self.logger.info(f"Seans notları güncellendi: ID {session_id}")
                
        except sqlite3.Error as e:
            self.logger.error(f"Seans notları güncelleme hatası: {e}")
            raise
    
    def save_completed_session(self, mode: str, patient_info: dict, target_condition: str,
                               start_time: datetime, duration_minutes: float, 
                               planned_duration: int, parameters: dict, 
                               stop_reason: str, connected_coils: List[int]) -> int:
        """
        Tamamlanmış seansı veritabanına kaydet (TEK KAYIT - Basitleştirilmiş Yapı)
        
        Bu metod sadece seans durdurulduğunda çağrılır. Çoklu kayıt sorunu çözülür.
        
        Args:
            mode: Seans modu ('automatic', 'ai', 'manual')
            patient_info: Hasta bilgileri dict
            target_condition: Hedef durum
            start_time: Seans başlangıç zamanı
            duration_minutes: Gerçek seans süresi (dakika)
            planned_duration: Planlanan süre (dakika)
            parameters: Seans parametreleri (frequency, duty, intensity vb.)
            stop_reason: Durma nedeni ('completed', 'user_stopped', 'error')
            connected_coils: Bağlı bobin listesi
            
        Returns:
            int: Oluşturulan session_id
        """
        try:
            self._ensure_write_guardrail()
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # Hasta bilgilerini parse et (BASİTLEŞTİRİLDİ)
                # patient_info yapısı: {'id': X, 'info': {'name', 'species', 'breed', 'age', 'weight', 'owner', ...}}
                patient_species = "Bilinmiyor"
                patient_breed = ""
                patient_age = ""
                patient_weight = ""
                owner_name = ""
                veteriner_name = ""
                patient_name = "Bilinmiyor"
                
                if patient_info:
                    # Önce 'info' dict'inden al, yoksa root'tan al
                    info_dict = patient_info.get('info', patient_info)
                    patient_name = info_dict.get('name', 'Bilinmiyor')
                    patient_species = info_dict.get('species', 'Bilinmiyor')
                    patient_breed = info_dict.get('breed', '')
                    
                    # Yaş ve ağırlık string/number olabilir
                    age_val = info_dict.get('age', '')
                    patient_age = str(age_val) if age_val else ''
                    weight_val = info_dict.get('weight', '')
                    patient_weight = str(weight_val) if weight_val else ''
                    
                    owner_name = info_dict.get('owner', '')
                    # Veteriner bilgisi için hem 'veteriner' hem 'vet_contact' kontrol et
                    veteriner_name = info_dict.get('veteriner', '') or info_dict.get('vet_contact', '')
                
                # Seans bilgilerini kaydet
                session_date = start_time.strftime('%Y-%m-%d')
                start_time_str = start_time.strftime('%H:%M:%S')
                end_time = datetime.now()
                end_time_str = end_time.strftime('%H:%M:%S')
                
                # Session status belirleme
                if stop_reason == 'completed':
                    session_status = 'completed'
                elif stop_reason == 'user_stopped':
                    session_status = 'interrupted'
                else:
                    session_status = 'error'
                
                # Parametrelerden frekans ve yoğunluk al
                frequency = parameters.get('frequency', 0)
                intensity = parameters.get('intensity', 0)
                duty_cycle = parameters.get('duty', 0)
                
                # Notlar oluştur
                notes_parts = [
                    f"Mod: {mode.capitalize()}",
                    f"Hedef: {target_condition}",
                    f"Planlanan Süre: {planned_duration} dk",
                    f"Gerçek Süre: {duration_minutes:.1f} dk",
                    f"Durum: {stop_reason}",
                    f"Bağlı Bobinler: {', '.join(map(str, connected_coils))}"
                ]
                
                if patient_breed:
                    notes_parts.append(f"Irk: {patient_breed}")
                if patient_age:
                    notes_parts.append(f"Yaş: {patient_age}")
                if patient_weight:
                    notes_parts.append(f"Ağırlık: {patient_weight}")
                
                patient_notes = " | ".join(notes_parts)
                
                # INSERT session
                cursor.execute('''
                    INSERT INTO treatment_sessions 
                    (session_date, start_time, end_time, duration_minutes, 
                     treatment_mode, target_condition, frequency_hz, intensity_mt,
                     operator_name, patient_name, patient_notes, session_status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    session_date, start_time_str, end_time_str, round(duration_minutes),
                    mode, target_condition, frequency, intensity,
                    owner_name, patient_name, patient_notes, session_status
                ))
                
                session_id = cursor.lastrowid
                
                # Parametreleri kaydet (JSON değil, ayrı kayıtlar)
                # stop_reason'ı Türkçeye çevir
                stop_reason_turkish = {
                    'completed': 'Tedavi Başarıyla Tamamlandı',
                    'user_stopped': 'Manuel Müdahale',
                    'manual_stop': 'Manuel Müdahale',
                    'error': 'Hata',
                    'emergency': 'Acil Durdurma'
                }.get(stop_reason, stop_reason)
                
                param_records = [
                    ('frequency_hz', str(frequency), 'Hz'),
                    ('duty_cycle', str(duty_cycle), '%'),
                    ('intensity_mt', str(intensity), 'mT'),
                    ('planned_duration', str(planned_duration), 'min'),
                    ('actual_duration', f"{duration_minutes:.1f}", 'min'),
                    ('stop_reason', stop_reason_turkish, ''),
                    ('connected_coils', ','.join(map(str, connected_coils)), ''),
                    # Hasta bilgileri
                    ('patient_name', patient_name, ''),
                    ('patient_species', patient_species, ''),
                    ('patient_breed', patient_breed, ''),
                    ('patient_age', patient_age, ''),
                    ('patient_weight', patient_weight, 'kg'),
                    ('patient_owner', owner_name, ''),
                    ('patient_veteriner', veteriner_name, ''),
                ]
                
                for param_name, param_value, param_unit in param_records:
                    cursor.execute('''
                        INSERT INTO session_parameters 
                        (session_id, parameter_name, parameter_value, parameter_unit)
                        VALUES (?, ?, ?, ?)
                    ''', (session_id, param_name, param_value, param_unit))
                
                conn.commit()
                
                self.logger.info(
                    f"Completed session saved: ID={session_id}, mode={mode}, "
                    f"patient={patient_name}, duration={duration_minutes:.1f}min, "
                    f"status={session_status}"
                )
                
                return session_id
                
        except Exception as e:
            self.logger.error(f"Failed to save completed session: {e}", exc_info=True)
            raise
    
    def delete_session(self, session_id: int):
        """
        Tedavi seansını sil
        
        Args:
            session_id: Silinecek seans ID'si
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # Önce parametreleri sil
                cursor.execute('DELETE FROM session_parameters WHERE session_id = ?', 
                             (session_id,))
                
                # Sonra seansı sil
                cursor.execute('DELETE FROM treatment_sessions WHERE id = ?', 
                             (session_id,))
                
                conn.commit()
                self.logger.info(f"Tedavi seansı silindi: ID {session_id}")
                
        except sqlite3.Error as e:
            self.logger.error(f"Seans silme hatası: {e}")
            raise
    
    def close(self):
        """Veritabanı bağlantısını kapat"""
        self.close_connections()

    def record_session_event(self, session_id: Optional[int], event_type: str,
                             payload: Optional[Dict] = None, severity: str = 'info') -> Optional[int]:
        """Seans olayını local event tablosuna kaydet."""
        try:
            self._ensure_write_guardrail()
            payload_json = json.dumps(payload or {}, ensure_ascii=True)
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO session_events
                    (event_uuid, session_id, event_type, severity, payload, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (
                    str(uuid.uuid4()),
                    session_id,
                    event_type,
                    severity,
                    payload_json,
                    datetime.now().timestamp()
                ))
                conn.commit()
                return cursor.lastrowid
        except Exception as e:
            self.logger.warning(f"Session event kaydedilemedi: {e}")
            return None

    def enqueue_outbox_message(self, topic: str, payload: str, qos: int = 0,
                               retain: bool = False, source: str = 'gateway',
                               correlation_id: Optional[str] = None,
                               available_at: Optional[float] = None,
                               idempotency_key: Optional[str] = None) -> Optional[int]:
        """Cloud'a gönderilecek mesajı unified outbox tablosuna ekle."""
        try:
            self._ensure_write_guardrail()
            now_ts = datetime.now().timestamp()
            ready_at = available_at if available_at is not None else now_ts
            derived_key = idempotency_key
            if derived_key:
                digest_src = f"{derived_key}|{topic}|{int(qos)}|{int(bool(retain))}".encode('utf-8')
                derived_key = hashlib.sha256(digest_src).hexdigest()

            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO outbox_messages
                    (message_uuid, idempotency_key, topic, payload, qos, retain, status, retry_count,
                     available_at, source, correlation_id, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, 'pending', 0, ?, ?, ?, ?)
                ''', (
                    str(uuid.uuid4()),
                    derived_key,
                    topic,
                    payload,
                    int(qos),
                    int(bool(retain)),
                    ready_at,
                    source,
                    correlation_id,
                    now_ts
                ))
                conn.commit()
                return cursor.lastrowid
        except sqlite3.IntegrityError:
            # Idempotency key duplicate -> mevcut kaydı tekrar ekleme
            if not derived_key:
                return None
            try:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        'SELECT id FROM outbox_messages WHERE idempotency_key = ?',
                        (derived_key,)
                    )
                    row = cursor.fetchone()
                    return int(row['id']) if row else None
            except Exception:
                return None
        except Exception as e:
            self.logger.error(f"Outbox enqueue hatası: {e}")
            return None

    def get_pending_outbox_messages(self, limit: int = 100) -> List[Dict]:
        """Gönderime hazır pending outbox mesajlarını getir."""
        try:
            now_ts = datetime.now().timestamp()
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT id, message_uuid, topic, payload, qos, retain, retry_count,
                           available_at, created_at, source, correlation_id
                    FROM outbox_messages
                    WHERE status = 'pending' AND available_at <= ?
                    ORDER BY created_at ASC
                    LIMIT ?
                ''', (now_ts, limit))
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            self.logger.error(f"Pending outbox okuma hatası: {e}")
            return []

    def mark_outbox_sent(self, message_ids: List[int]):
        """Başarıyla gönderilen outbox mesajlarını sent olarak işaretle."""
        if not message_ids:
            return

        try:
            sent_at = datetime.now().timestamp()
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.executemany('''
                    UPDATE outbox_messages
                    SET status = 'sent', sent_at = ?, last_error = NULL
                    WHERE id = ?
                ''', [(sent_at, int(msg_id)) for msg_id in message_ids])
                conn.commit()
        except Exception as e:
            self.logger.error(f"Outbox sent işaretleme hatası: {e}")

    def mark_outbox_inflight(self, message_ids: List[int]):
        """Gönderim denemesi başlayan mesajları in_flight olarak işaretle."""
        if not message_ids:
            return

        try:
            now_ts = datetime.now().timestamp()
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.executemany('''
                    UPDATE outbox_messages
                    SET status = 'in_flight', available_at = ?, last_error = NULL
                    WHERE id = ? AND status = 'pending'
                ''', [(now_ts, int(msg_id)) for msg_id in message_ids])
                conn.commit()
        except Exception as e:
            self.logger.error(f"Outbox in_flight işaretleme hatası: {e}")

    @staticmethod
    def _retry_backoff_seconds(retry_count: int) -> int:
        """Exponential backoff: 1,2,4,... max 300 saniye."""
        return min(300, max(1, 2 ** max(0, retry_count)))

    def mark_outbox_failed(self, message_id: int, error_text: str, retry_count: int,
                           max_retry_count: int = 20) -> bool:
        """Gönderim hatasında retry sayısını ve tekrar deneme zamanını güncelle."""
        try:
            next_retry_at = datetime.now().timestamp() + self._retry_backoff_seconds(retry_count)
            next_status = 'dead' if retry_count >= max_retry_count else 'pending'
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE outbox_messages
                    SET status = ?, retry_count = ?, available_at = ?, last_error = ?
                    WHERE id = ?
                ''', (next_status, int(retry_count), next_retry_at, str(error_text), int(message_id)))
                conn.commit()
                return next_status == 'dead'
        except Exception as e:
            self.logger.error(f"Outbox failed işaretleme hatası: {e}")
            return False

    def requeue_stale_inflight(self, stale_seconds: int = 120) -> int:
        """Uzun süre in_flight kalan mesajları tekrar pending yap."""
        try:
            cutoff_ts = datetime.now().timestamp() - max(1, int(stale_seconds))
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE outbox_messages
                    SET status = 'pending',
                        available_at = ?,
                        last_error = COALESCE(last_error, 'requeued stale in_flight')
                    WHERE status = 'in_flight' AND available_at < ?
                ''', (datetime.now().timestamp(), cutoff_ts))
                affected = int(cursor.rowcount)
                conn.commit()
                return affected
        except Exception as e:
            self.logger.warning(f"Stale in_flight requeue uyarısı: {e}")
            return 0

    def get_pending_outbox_count(self) -> int:
        """Bekleyen outbox mesaj sayısını getir."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM outbox_messages WHERE status IN ('pending', 'in_flight')")
                return int(cursor.fetchone()[0])
        except Exception:
            return 0

    def get_outbox_status_counts(self) -> Dict[str, int]:
        """Outbox durum dağılımını döndür (pending/in_flight/sent/dead)."""
        counts = {'pending': 0, 'in_flight': 0, 'sent': 0, 'dead': 0}
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT status, COUNT(*) as cnt
                    FROM outbox_messages
                    GROUP BY status
                ''')
                for row in cursor.fetchall():
                    status = str(row['status'])
                    if status in counts:
                        counts[status] = int(row['cnt'])
            return counts
        except Exception:
            return counts

    def purge_sent_outbox(self, older_than_hours: int = 72):
        """Belirtilen süreden eski sent kayıtlarını temizle."""
        try:
            cutoff_ts = datetime.now().timestamp() - (older_than_hours * 3600)
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    DELETE FROM outbox_messages
                    WHERE status = 'sent' AND sent_at IS NOT NULL AND sent_at < ?
                ''', (cutoff_ts,))
                conn.commit()
        except Exception as e:
            self.logger.warning(f"Outbox temizleme uyarısı: {e}")

    def clear_pending_outbox(self):
        """Bekleyen outbox kayıtlarını temizle (operasyonel bakım)."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM outbox_messages WHERE status IN ('pending', 'in_flight')")
                conn.commit()
        except Exception as e:
            self.logger.warning(f"Pending outbox temizleme uyarısı: {e}")

    def add_sensor_samples_batch(self, session_id: int, samples: List[Dict]) -> int:
        """Aktif seans için sensör örneklerini batch olarak kaydet."""
        if not samples:
            return 0

        try:
            self._ensure_write_guardrail()
            rows = []
            now_ts = datetime.now().timestamp()
            for sample in samples:
                rows.append((
                    int(session_id),
                    str(sample.get('coil_id', 'unknown')),
                    float(sample.get('sample_ts', now_ts)),
                    sample.get('temperature_c'),
                    sample.get('magnetic_field_mt'),
                    sample.get('current_a'),
                    sample.get('pwm_frequency_hz'),
                    sample.get('pwm_duty_percent'),
                    json.dumps(sample.get('payload', {}), ensure_ascii=True),
                    now_ts
                ))

            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.executemany('''
                    INSERT INTO sensor_samples
                    (session_id, coil_id, sample_ts, temperature_c, magnetic_field_mt,
                     current_a, pwm_frequency_hz, pwm_duty_percent, payload, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', rows)
                conn.commit()
                return len(rows)
        except Exception as e:
            self.logger.error(f"Sensor sample batch kaydetme hatası: {e}")
            return 0


# Singleton instance
_treatment_db_instance = None
_treatment_db_lock = threading.Lock()

def get_treatment_db(app_data_dir):
    """Tedavi geçmişi veritabanı singleton instance'ını getir"""
    global _treatment_db_instance
    with _treatment_db_lock:
        requested_db_path = app_data_dir / "pemf_treatment_history.db"
        current_db_path = getattr(_treatment_db_instance, 'db_path', None)

        if _treatment_db_instance is None or current_db_path != requested_db_path:
            _treatment_db_instance = TreatmentHistoryDB(app_data_dir)
    return _treatment_db_instance
