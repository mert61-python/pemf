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

# SQLCipher (sqlcipher3) kendi exception class'larını fırlatır; sqlite3 except'leri bunları
# YAKALAMAZ. Aşağıdaki tuple'lar ikisini de kapsar (şifreli + düz-metin yol birlikte çalışsın).
try:
    from sqlcipher3 import dbapi2 as _sqlcipher_mod
    _DB_OPERATIONAL = (sqlite3.OperationalError, _sqlcipher_mod.OperationalError)
    _DB_ERROR = (sqlite3.Error, _sqlcipher_mod.Error)
    _DB_INTEGRITY = (sqlite3.IntegrityError, _sqlcipher_mod.IntegrityError)
except Exception:
    _DB_OPERATIONAL = sqlite3.OperationalError
    _DB_ERROR = sqlite3.Error
    _DB_INTEGRITY = sqlite3.IntegrityError

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

        # SQLCipher anahtarı yapılandırılmışsa ve mevcut DB düz-metinse → şifreliye MIGRATE et.
        self._migrate_to_encrypted_if_needed()

        # Veritabanını başlat
        self._init_database()
        self._run_startup_migrations_with_rollback()
        self.recover_stale_active_sessions(max_age_hours=12)
        # Açılışta otomatik bütünlük kontrolü (bozulmayı erken yakala — eskiden hiç çağrılmıyordu).
        try:
            _ic = self.run_integrity_check(quick=True)
            if not _ic.get("ok"):
                self.logger.error("DB BUTUNLUK KONTROLU BASARISIZ (acilis): %s", _ic.get("details"))
        except Exception:
            self.logger.exception("Acilis butunluk kontrolu hatasi")

    def _connect_plain_sqlite(self):
        """Standart sqlite3 bağlantısı oluştur."""
        conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _import_sqlcipher(self):
        """Pre-built sqlcipher3 (Windows wheel) veya pysqlcipher3 binding'ini dener; yoksa None."""
        try:
            from sqlcipher3 import dbapi2 as sqlcipher  # type: ignore
            return sqlcipher
        except Exception:
            pass
        try:
            from pysqlcipher3 import dbapi2 as sqlcipher  # type: ignore
            return sqlcipher
        except Exception:
            return None

    def _get_sqlcipher_key(self) -> str:
        """SQLCipher anahtarı: keyring → env → key-dosyası. Hiçbiri yoksa ve PEMF_ENCRYPT_AT_REST=1
        ise yeni anahtar üretip saklar (keyring tercih, dosya fallback). Aksi halde '' (düz-metin)."""
        service_name = "PEMF_GUI"
        key_name = "sqlcipher_key"
        if keyring is not None:
            try:
                credential_key = (keyring.get_password(service_name, key_name) or "").strip()
                if credential_key:
                    return credential_key
            except Exception as e:
                self.logger.warning(f"keyring okuma hatasi: {e}")
        env_key = os.getenv('PEMF_SQLCIPHER_KEY', '').strip()
        if env_key:
            return env_key
        keyfile = self.app_data_dir / ".sqlcipher_key"
        try:
            if keyfile.exists():
                k = keyfile.read_text(encoding="utf-8").strip()
                if k:
                    return k
        except Exception:
            pass
        if os.getenv("PEMF_ENCRYPT_AT_REST", "0") != "1":
            return ""  # açıkça istenmedikçe şifreleme açma (geriye uyumlu)
        import secrets
        newkey = secrets.token_urlsafe(32)
        stored_in_keyring = False
        if keyring is not None:
            try:
                keyring.set_password(service_name, key_name, newkey)
                stored_in_keyring = True
            except Exception:
                pass
        if not stored_in_keyring:
            try:
                keyfile.write_text(newkey, encoding="utf-8")
                try:
                    os.chmod(keyfile, 0o600)
                except Exception:
                    pass
            except Exception:
                pass
        self.logger.warning("Yeni SQLCipher anahtari uretildi (keyring=%s). ANAHTAR KAYBOLURSA sifreli veri OKUNAMAZ.", stored_in_keyring)
        return newkey

    def _connect_sqlcipher_if_configured(self):
        """SQLCipher anahtarı varsa SQLCipher bağlantısı dene, yoksa None döndür."""
        cipher_key = self._get_sqlcipher_key()
        if not cipher_key:
            return None

        sqlcipher = self._import_sqlcipher()
        if sqlcipher is None:
            self.logger.warning("SQLCipher anahtari var ama binding (sqlcipher3) kurulu DEGIL → duz-metin fallback.")
            return None
        try:
            conn = sqlcipher.connect(str(self.db_path), check_same_thread=False, timeout=10.0)
            conn.row_factory = getattr(sqlcipher, "Row", sqlite3.Row)  # sqlcipher3 cursor uyumlu Row
            escaped_key = cipher_key.replace("'", "''")
            conn.execute(f"PRAGMA key='{escaped_key}'")
            conn.execute('SELECT count(*) FROM sqlite_master')
            return conn
        except Exception as e:
            self.logger.warning(f"SQLCipher acilamadi (yanlis anahtar veya migrate gerekli?): {e}")
            return None

    def _migrate_to_encrypted_if_needed(self):
        """Bir SQLCipher anahtarı varsa ve mevcut DB DÜZ-METİN ise içeriği şifreli kopyaya aktarır
        (sqlcipher_export) ve dosyayı değiştirir; eski düz-metin .plain.bak olarak kalır. Anahtar yok /
        binding yok / zaten şifreli ise no-op (geriye uyumlu, veri kaybı yok)."""
        def _close(cn):
            try:
                cn.close()
            except Exception:
                pass

        try:
            key = self._get_sqlcipher_key()
            if not key:
                return
            sqlcipher = self._import_sqlcipher()
            db = str(self.db_path)
            if sqlcipher is None or not os.path.exists(db):
                return
            keyq = "'" + key.replace("'", "''") + "'"
            # Zaten şifreli mi? — bağlantıyı HER durumda kapat (yoksa sonraki move PermissionError).
            c = None
            try:
                c = sqlcipher.connect(db)
                c.execute(f"PRAGMA key={keyq}")
                c.execute("SELECT count(*) FROM sqlite_master")
                return  # açıldı → zaten şifreli
            except Exception:
                pass
            finally:
                if c is not None:
                    _close(c)
            # Düz-metin mi? (plain sqlite3 açıyor) + WAL'i ana dosyaya checkpoint et.
            t = None
            try:
                t = sqlite3.connect(db)
                t.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                t.execute("SELECT count(*) FROM sqlite_master")
            except Exception:
                return  # bilinmeyen format → DOKUNMA
            finally:
                if t is not None:
                    _close(t)
            # MIGRATE: plaintext → encrypted
            enc_tmp = db + ".enc.tmp"
            if os.path.exists(enc_tmp):
                os.remove(enc_tmp)
            enc_sql = enc_tmp.replace("'", "''")
            conn = None
            try:
                conn = sqlcipher.connect(db)  # anahtar yok → düz-metin modunda açılır
                conn.execute(f"ATTACH DATABASE '{enc_sql}' AS enc KEY {keyq}")
                conn.execute("SELECT sqlcipher_export('enc')")
                conn.execute("DETACH DATABASE enc")
            finally:
                if conn is not None:
                    _close(conn)
            # Doğrula
            v = None
            n = 0
            try:
                v = sqlcipher.connect(enc_tmp)
                v.execute(f"PRAGMA key={keyq}")
                n = v.execute("SELECT count(*) FROM sqlite_master").fetchone()[0]
            finally:
                if v is not None:
                    _close(v)
            if not n or n <= 0:
                if os.path.exists(enc_tmp):
                    os.remove(enc_tmp)
                self.logger.error("SQLCipher migrate: sifreli kopya bos → iptal (duz-metin korunur).")
                return
            # Move'dan ÖNCE eski WAL/SHM'i temizle (açık handle/çakışma olmasın → bozulma önle).
            for suffix in ("-wal", "-shm"):
                f = db + suffix
                if os.path.exists(f):
                    try:
                        os.remove(f)
                    except Exception:
                        pass
            backup = db + ".plain.bak"
            if os.path.exists(backup):
                os.remove(backup)
            shutil.move(db, backup)
            shutil.move(enc_tmp, db)
            self.logger.warning("Tedavi DB plaintext -> SQLCipher MIGRATE edildi (artik sifreli). Duz-metin yedek: %s", backup)
        except Exception:
            self.logger.exception("SQLCipher migrate hatasi (duz-metin korunur)")

    def _create_connection(self):
        """Yeni SQLite bağlantısı oluştur ve bağlantı ayarlarını uygula."""
        sqlcipher_conn = self._connect_sqlcipher_if_configured()
        if sqlcipher_conn is not None:
            self.at_rest_encrypted = True
            conn = sqlcipher_conn
        else:
            # GÖRÜNÜRLÜK: at-rest şifreleme yoksa SESSİZCE düz-metne düşme — operatör bilsin.
            self.at_rest_encrypted = False
            if not getattr(self, "_encryption_warned", False):
                self._encryption_warned = True
                self.logger.warning(
                    "AT-REST SIFRELEME KAPALI: tedavi gecmisi (seans/sensor/PII) DUZ-METIN SQLite "
                    "olarak yaziliyor. Uretimde pysqlcipher3 kurun + PEMF_SQLCIPHER_KEY (keyring) "
                    "ayarlayin. (health endpoint: at_rest_encrypted=false)"
                )
            conn = self._connect_plain_sqlite()
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
        except _DB_OPERATIONAL as e:
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
            except _DB_OPERATIONAL as fallback_err:
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
                        updated_at TEXT,
                        sync_status INTEGER DEFAULT 0
                    )
                ''')
                
                try:
                    cursor.execute("ALTER TABLE treatment_sessions ADD COLUMN sync_status INTEGER DEFAULT 0")
                except _DB_OPERATIONAL:
                    pass

                # KRİTİK: mevcut DB'lerde updated_at yoksa ekle — end_session ve
                # update_session_notes bu kolonu yazıyor; yoksa OperationalError (seans bitirme/not patlar).
                try:
                    cursor.execute("ALTER TABLE treatment_sessions ADD COLUMN updated_at TEXT")
                except _DB_OPERATIONAL:
                    pass
                
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
                except _DB_OPERATIONAL:
                    # Sütun zaten varsa hata vermez
                    pass

                # Session bazlı idempotent kimlik
                try:
                    cursor.execute('ALTER TABLE treatment_sessions ADD COLUMN session_uuid TEXT')
                    self.logger.info("session_uuid sütunu eklendi")
                except _DB_OPERATIONAL:
                    pass

                try:
                    cursor.execute('ALTER TABLE outbox_messages ADD COLUMN idempotency_key TEXT')
                    self.logger.info("idempotency_key sütunu eklendi")
                except _DB_OPERATIONAL:
                    pass

                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_treatment_sessions_uuid
                    ON treatment_sessions(session_uuid)
                ''')

                # === VETERINER YEREL KATMAN GENISLETMESI (geriye uyumlu, idempotent) ===
                # Hasta (patient) kayit defteri — cloud sync icin sync_status ile.
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS patients (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        patient_uuid TEXT UNIQUE,
                        name TEXT NOT NULL,
                        species TEXT,
                        breed TEXT,
                        age TEXT,
                        weight_kg REAL,
                        owner_name TEXT,
                        vet_contact TEXT,
                        veteriner TEXT,
                        notes TEXT,
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                        updated_at TEXT,
                        sync_status INTEGER DEFAULT 0
                    )
                ''')

                # Bobin calismalari — "hangi bobin, hangi parametreyle, saat kacta
                # basladi/durdu, ne kadar surdu" sorusunu cevaplar.
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS session_coil_runs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id INTEGER,
                        coil_id INTEGER NOT NULL,
                        started_epoch REAL NOT NULL,
                        ended_epoch REAL,
                        duration_seconds REAL,
                        frequency_hz REAL,
                        duty_percent REAL,
                        phase REAL,
                        intensity_mt REAL,
                        hw_type TEXT,
                        created_at REAL NOT NULL
                    )
                ''')

                # Bobin calismasi basina sensor ozet istatistigi (1-1, coil_run_id UNIQUE).
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS sensor_run_summary (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        coil_run_id INTEGER UNIQUE,
                        sample_count INTEGER,
                        temp_min REAL,
                        temp_max REAL,
                        temp_avg REAL,
                        current_avg REAL,
                        field_avg REAL,
                        created_at REAL NOT NULL
                    )
                ''')

                # treatment_sessions yeni kolonlari (her biri ayri try/except, nullable).
                try:
                    cursor.execute('ALTER TABLE treatment_sessions ADD COLUMN patient_id INTEGER')
                    self.logger.info("treatment_sessions.patient_id sütunu eklendi")
                except _DB_OPERATIONAL:
                    pass
                try:
                    cursor.execute('ALTER TABLE treatment_sessions ADD COLUMN started_epoch REAL')
                    self.logger.info("treatment_sessions.started_epoch sütunu eklendi")
                except _DB_OPERATIONAL:
                    pass
                try:
                    cursor.execute('ALTER TABLE treatment_sessions ADD COLUMN ended_epoch REAL')
                    self.logger.info("treatment_sessions.ended_epoch sütunu eklendi")
                except _DB_OPERATIONAL:
                    pass

                # sensor_samples yeni kolonlari (her biri ayri try/except, nullable).
                # SEMANTIK NOT: sensor_samples artik DAKIKA-ORTALAMASI tutabilir;
                # sample_count = ortalamaya giren ham okuma sayisi. Sema ayni kalir,
                # mevcut satirlar (ham okuma) icin bu kolonlar NULL kalir — geriye uyumlu.
                try:
                    cursor.execute('ALTER TABLE sensor_samples ADD COLUMN coil_run_id INTEGER')
                    self.logger.info("sensor_samples.coil_run_id sütunu eklendi")
                except _DB_OPERATIONAL:
                    pass
                try:
                    cursor.execute('ALTER TABLE sensor_samples ADD COLUMN ambient_temp_c REAL')
                    self.logger.info("sensor_samples.ambient_temp_c sütunu eklendi")
                except _DB_OPERATIONAL:
                    pass
                try:
                    cursor.execute('ALTER TABLE sensor_samples ADD COLUMN phase REAL')
                    self.logger.info("sensor_samples.phase sütunu eklendi")
                except _DB_OPERATIONAL:
                    pass
                try:
                    cursor.execute('ALTER TABLE sensor_samples ADD COLUMN sample_count INTEGER')
                    self.logger.info("sensor_samples.sample_count sütunu eklendi")
                except _DB_OPERATIONAL:
                    pass

                # Yeni tablolar icin indeksler (mevcut idx'lere dokunulmadi).
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_coil_runs_session
                    ON session_coil_runs(session_id, started_epoch)
                ''')
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_coil_runs_coil
                    ON session_coil_runs(coil_id, started_epoch)
                ''')
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_sensor_run_summary
                    ON sensor_run_summary(coil_run_id)
                ''')
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_patients_name
                    ON patients(name)
                ''')

                conn.commit()
                self.logger.info(f"Veritabanı başarıyla başlatıldı: {self.db_path}")
                
        except _DB_ERROR as e:
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
            'at_rest_encrypted': bool(getattr(self, 'at_rest_encrypted', False)),
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
        """Çalışan DB'den dosya yedeği üret (online backup API). DB ŞİFRELİYSE yedek de aynı
        anahtarla ŞİFRELİ olur (plain hedefe yedek hem uyumsuz hem düz-metin PII sızdırır)."""
        try:
            backup_dir = os.path.dirname(backup_path)
            if backup_dir:
                os.makedirs(backup_dir, exist_ok=True)

            with self._get_connection() as src_conn:
                if getattr(self, "at_rest_encrypted", False):
                    key = self._get_sqlcipher_key()
                    sqlcipher = self._import_sqlcipher()
                    dst_conn = sqlcipher.connect(backup_path)
                    dst_conn.execute("PRAGMA key='{}'".format(key.replace("'", "''")))
                else:
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
                
        except _DB_ERROR as e:
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
                
        except _DB_ERROR as e:
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
                           COALESCE(sp_name.parameter_value, ts.patient_name) as patient_name,
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
                
        except _DB_ERROR as e:
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
                
        except _DB_ERROR as e:
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
                
        except _DB_ERROR as e:
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
                
        except _DB_ERROR as e:
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
                # Çocuk kayıtları sil — FK ON DELETE CASCADE yok; aksi halde veri-içeren seansı
                # silmek FOREIGN KEY hatasıyla 500 döner.
                cursor.execute('DELETE FROM sensor_samples WHERE session_id = ?', (session_id,))
                cursor.execute('DELETE FROM session_events WHERE session_id = ?', (session_id,))

                # Sonra seansı sil
                cursor.execute('DELETE FROM treatment_sessions WHERE id = ?',
                             (session_id,))
                
                conn.commit()
                self.logger.info(f"Tedavi seansı silindi: ID {session_id}")
                
        except _DB_ERROR as e:
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
        except _DB_INTEGRITY:
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
        """Aktif seans için sensör örneklerini batch olarak kaydet.

        Geriye uyumlu genisletme: her ornek dict'i opsiyonel olarak coil_run_id,
        ambient_temp_c, phase, sample_count alanlarini icerebilir; verilmezse NULL
        yazilir. Mevcut cagiranlar (sadece eski alanlari veren) bozulmaz.
        sensor_samples artik dakika-ortalamasi tutabilir; sample_count = ortalamaya
        giren ham okuma sayisi.
        """
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
                    now_ts,
                    sample.get('coil_run_id'),
                    sample.get('ambient_temp_c'),
                    sample.get('phase'),
                    sample.get('sample_count')
                ))

            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.executemany('''
                    INSERT INTO sensor_samples
                    (session_id, coil_id, sample_ts, temperature_c, magnetic_field_mt,
                     current_a, pwm_frequency_hz, pwm_duty_percent, payload, created_at,
                     coil_run_id, ambient_temp_c, phase, sample_count)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', rows)
                conn.commit()
                return len(rows)
        except Exception as e:
            self.logger.error(f"Sensor sample batch kaydetme hatası: {e}")
            return 0

    def upsert_patient(self, patient: Dict) -> Optional[int]:
        """Hasta kaydini ekle/guncelle. patient_uuid varsa ona gore, yoksa
        name (+owner_name) ile eslestir; varsa UPDATE, yoksa INSERT eder.
        Geri donus: patient_id (int) veya hata halinde None."""
        try:
            self._ensure_write_guardrail()
            name = patient.get('name')
            if not name:
                self.logger.warning("upsert_patient: 'name' zorunlu, atlandi")
                return None

            patient_uuid = patient.get('patient_uuid')
            owner_name = patient.get('owner_name')
            now_iso = datetime.now().isoformat(sep=' ', timespec='seconds')

            with self._get_connection() as conn:
                cursor = conn.cursor()

                existing_id = None
                if patient_uuid:
                    cursor.execute(
                        'SELECT id FROM patients WHERE patient_uuid = ?',
                        (patient_uuid,)
                    )
                    row = cursor.fetchone()
                    if row:
                        existing_id = int(row['id'])
                else:
                    # name (+ owner_name) ile eslestir
                    if owner_name is not None:
                        cursor.execute(
                            'SELECT id FROM patients WHERE name = ? AND IFNULL(owner_name, "") = ? '
                            'ORDER BY id LIMIT 1',
                            (name, owner_name)
                        )
                    else:
                        cursor.execute(
                            'SELECT id FROM patients WHERE name = ? AND owner_name IS NULL '
                            'ORDER BY id LIMIT 1',
                            (name,)
                        )
                    row = cursor.fetchone()
                    if row:
                        existing_id = int(row['id'])

                if existing_id is not None:
                    cursor.execute('''
                        UPDATE patients SET
                            patient_uuid = COALESCE(?, patient_uuid),
                            name = ?,
                            species = ?,
                            breed = ?,
                            age = ?,
                            weight_kg = ?,
                            owner_name = ?,
                            vet_contact = ?,
                            veteriner = ?,
                            notes = ?,
                            updated_at = ?,
                            sync_status = 0
                        WHERE id = ?
                    ''', (
                        patient_uuid,
                        name,
                        patient.get('species'),
                        patient.get('breed'),
                        patient.get('age'),
                        patient.get('weight_kg'),
                        owner_name,
                        patient.get('vet_contact'),
                        patient.get('veteriner'),
                        patient.get('notes'),
                        now_iso,
                        existing_id
                    ))
                    conn.commit()
                    return existing_id

                cursor.execute('''
                    INSERT INTO patients
                    (patient_uuid, name, species, breed, age, weight_kg, owner_name,
                     vet_contact, veteriner, notes, updated_at, sync_status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                ''', (
                    patient_uuid,
                    name,
                    patient.get('species'),
                    patient.get('breed'),
                    patient.get('age'),
                    patient.get('weight_kg'),
                    owner_name,
                    patient.get('vet_contact'),
                    patient.get('veteriner'),
                    patient.get('notes'),
                    now_iso
                ))
                conn.commit()
                return cursor.lastrowid
        except Exception as e:
            self.logger.error(f"Hasta upsert hatası: {e}")
            return None

    def start_coil_run(self, session_id: Optional[int], coil_id: int, *,
                       frequency_hz: Optional[float] = None,
                       duty_percent: Optional[float] = None,
                       phase: Optional[float] = None,
                       intensity_mt: Optional[float] = None,
                       hw_type: Optional[str] = None,
                       started_epoch: float) -> Optional[int]:
        """Bir bobinin calismaya basladigini kaydet. created_at=started_epoch.
        Geri donus: run_id (int) veya hata halinde None."""
        try:
            self._ensure_write_guardrail()
            started = float(started_epoch)
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO session_coil_runs
                    (session_id, coil_id, started_epoch, ended_epoch, duration_seconds,
                     frequency_hz, duty_percent, phase, intensity_mt, hw_type, created_at)
                    VALUES (?, ?, ?, NULL, NULL, ?, ?, ?, ?, ?, ?)
                ''', (
                    session_id,
                    int(coil_id),
                    started,
                    frequency_hz,
                    duty_percent,
                    phase,
                    intensity_mt,
                    hw_type,
                    started
                ))
                conn.commit()
                return cursor.lastrowid
        except Exception as e:
            self.logger.error(f"Coil run baslatma hatası: {e}")
            return None

    def end_coil_run(self, run_id: int, ended_epoch: float) -> None:
        """Bobin calismasini bitir; duration_seconds = ended_epoch - started_epoch
        (started_epoch satirdan okunur)."""
        try:
            self._ensure_write_guardrail()
            ended = float(ended_epoch)
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'SELECT started_epoch FROM session_coil_runs WHERE id = ?',
                    (int(run_id),)
                )
                row = cursor.fetchone()
                if not row or row['started_epoch'] is None:
                    self.logger.warning(f"end_coil_run: run_id {run_id} bulunamadi/started_epoch yok")
                    return
                started = float(row['started_epoch'])
                cursor.execute('''
                    UPDATE session_coil_runs
                    SET ended_epoch = ?, duration_seconds = ?
                    WHERE id = ?
                ''', (ended, ended - started, int(run_id)))
                conn.commit()
        except Exception as e:
            self.logger.error(f"Coil run bitirme hatası: {e}")

    def add_sensor_run_summary(self, coil_run_id: int, *, sample_count=None,
                               temp_min=None, temp_max=None, temp_avg=None,
                               current_avg=None, field_avg=None) -> None:
        """Bir bobin calismasinin sensor ozet istatistigini kaydet.
        coil_run_id UNIQUE oldugu icin INSERT OR REPLACE kullanilir (yeniden hesapta uzerine yazar)."""
        try:
            self._ensure_write_guardrail()
            now_ts = datetime.now().timestamp()
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT OR REPLACE INTO sensor_run_summary
                    (coil_run_id, sample_count, temp_min, temp_max, temp_avg,
                     current_avg, field_avg, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    int(coil_run_id),
                    sample_count,
                    temp_min,
                    temp_max,
                    temp_avg,
                    current_avg,
                    field_avg,
                    now_ts
                ))
                conn.commit()
        except Exception as e:
            self.logger.error(f"Sensor run summary kaydetme hatası: {e}")

    def set_session_meta(self, session_id, *, started_epoch=None, ended_epoch=None, patient_id=None) -> None:
        """treatment_sessions satirina yeni kolonlari (gercek wall-clock epoch + patient_id FK)
        baglar. Mevcut start_session/end_session bu Asama-2 kolonlarini bilmedigi icin ayrica cagrilir.
        Yalniz verilen alanlar UPDATE edilir; hepsi best-effort."""
        try:
            self._ensure_write_guardrail()
            sets, params = [], []
            if started_epoch is not None:
                sets.append('started_epoch = ?'); params.append(float(started_epoch))
            if ended_epoch is not None:
                sets.append('ended_epoch = ?'); params.append(float(ended_epoch))
            if patient_id is not None:
                sets.append('patient_id = ?'); params.append(int(patient_id))
            if not sets:
                return
            params.append(int(session_id))
            with self._get_connection() as conn:
                conn.execute('UPDATE treatment_sessions SET ' + ', '.join(sets) + ' WHERE id = ?', params)
                conn.commit()
        except Exception as e:
            self.logger.error(f"set_session_meta hatası: {e}")

    def get_session_coil_runs(self, session_id: int) -> List[Dict]:
        """Bir seansa ait bobin calismalarini rapor icin getir
        (coil_id, started/ended_epoch, duration, parametreler)."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT id, session_id, coil_id, started_epoch, ended_epoch,
                           duration_seconds, frequency_hz, duty_percent, phase,
                           intensity_mt, hw_type, created_at
                    FROM session_coil_runs
                    WHERE session_id = ?
                    ORDER BY started_epoch ASC
                ''', (session_id,))
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
        except _DB_ERROR as e:
            self.logger.error(f"Coil run listeleme hatası: {e}")
            return []

    def get_run_summaries(self, session_id: int) -> Dict:
        """Bir seansin tum bobin-calismalarinin sensor ozetlerini getir.
        sensor_run_summary'yi session_coil_runs ile JOIN'leyip o seansa ait
        coil_run_id'leri filtreler.
        Donus: {coil_run_id: {sample_count, temp_min, temp_max, temp_avg,
                              current_avg, field_avg}}.
        Ozet bulunmayan run'lar sozlukte yer almaz (rapor tarafinda null'a duser)."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT s.coil_run_id, s.sample_count, s.temp_min, s.temp_max,
                           s.temp_avg, s.current_avg, s.field_avg
                    FROM sensor_run_summary s
                    JOIN session_coil_runs r ON r.id = s.coil_run_id
                    WHERE r.session_id = ?
                ''', (session_id,))
                rows = cursor.fetchall()
                summaries = {}
                for row in rows:
                    d = dict(row)
                    summaries[d['coil_run_id']] = {
                        'sample_count': d.get('sample_count'),
                        'temp_min': d.get('temp_min'),
                        'temp_max': d.get('temp_max'),
                        'temp_avg': d.get('temp_avg'),
                        'current_avg': d.get('current_avg'),
                        'field_avg': d.get('field_avg'),
                    }
                return summaries
        except _DB_ERROR as e:
            self.logger.error(f"Run summary listeleme hatası: {e}")
            return {}

    def get_sensor_samples(self, session_id: int) -> List[Dict]:
        """Bir seansin sensor orneklerini grafik icin getir (sample_ts ASC).
        Donus alanlari: coil_id, sample_ts, temperature_c, ambient_temp_c,
        current_a, magnetic_field_mt, pwm_frequency_hz, pwm_duty_percent,
        coil_run_id, sample_count."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT coil_id, sample_ts, temperature_c, ambient_temp_c,
                           current_a, magnetic_field_mt, pwm_frequency_hz,
                           pwm_duty_percent, coil_run_id, sample_count
                    FROM sensor_samples
                    WHERE session_id = ?
                    ORDER BY sample_ts ASC
                ''', (session_id,))
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
        except _DB_ERROR as e:
            self.logger.error(f"Sensor sample listeleme hatası: {e}")
            return []


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
