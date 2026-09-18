# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""SEMA KURULUMU VE GOCU — (B4 · 8/N, 2026-09-18).

⚠️ AYRILMA GEREKCESI: bkz. `database/thdb_outbox.py` bas yorumu (B4 · 1/N).
Bu kume tablolari/indeksleri kurar, sema surumunu yonetir ve duz-metin -> SQLCipher gocunu
tetikler.

⚠️ EN HASSAS KUME. 2026-09-13'te hasta gecmisini kaybettiren yol TAM BURADAN geciyordu:
yarim kalmis bir goc diskte `db` YOK + `db.plain.bak` VAR birakiyor, toparlanmazsa bir
sonraki acilis BOS bir veritabani yaratiyor ve klinik gecmisi BOS goruyordu. Bu yuzden:
  · `_migrate_to_encrypted_if_needed` KENDI govdesini TASIMAZ — `sqlcipher_util`e delege eder
    (A1 birlestirmesi). Buraya govde GERI YAZMAYIN; iki kopya sessizce ayrisir.
  · `_run_startup_migrations_with_rollback` her goc adimini GERI ALINABILIR tutar.
Kapilar: 10 yarim-goc testi + 48 urun senaryosunun A grubu (donmus EXE'de kosar).

⚠️ `_safe_add_column` var-olan sutunu SESSIZCE atlar (idempotent). Bunu "hata gizliyor" diye
sertlestirmeyin: sema gocu her aciliste kosar ve ikinci kosuda patlamamalidir.

⚠️ GOVDELER DEGISTIRILMEDI — AST ile bayt bayt tasindi.

`self` uzerinden kullandigi ve ANA SINIFTA kalan uyeler: `_get_connection`, `logger`,
`db_path`, `app_data_dir`.
"""

from __future__ import annotations

import os
import shutil
from datetime import datetime

# ⚠️ Modul duzeyi istisna demeti — tasinan `except` dallari kullanir. Bkz. db_hatalari.py.
from database.db_hatalari import _DB_OPERATIONAL


class SemaKarisimi:
    def _migrate_to_encrypted_if_needed(self):
        """Duz-metin tedavi DB'sini SQLCipher'a gocurur — GOVDE ORTAK (A1 · 2/2, 2026-09-15).

        ⚠️ BURADA 157 SATIRLIK BIR KOPYA VARDI. `sqlcipher_util.migrate_to_encrypted_if_needed`
        ile %91 ayniydi ve kalan farklarin TAMAMI mekanikti (metot/fonksiyon imzasi, yerel
        import'lar, `if logger:` korumalari, etiket metni). Olculdu:
          · `self._get_sqlcipher_key()` ZATEN `sqlcipher_util.get_sqlcipher_key`e delege ediyor,
          · `self._import_sqlcipher()` BIREBIR kopyaydi (o da delege edildi),
          · tek davranissal fark sanilan `_yarim_goc_toparla` try/except'i OLU: o fonksiyon
            kendi hatalarini yutup `False` doner, HIC firlatmaz.
        Yani enjeksiyon gerekmedi; parametre yetti.

        ⚠️ NEDEN BIRLESTIRILDI: bu kopya, TEK bir oturumda UC ayri yerden ayristigi olculen
        kuyrugun sahibiydi (bayrak adi · ACL fail-open · log seviyesi) ve ayrismalarin hicbiri
        denetimde gorunmuyordu. Dorduncusu kacinilmazdi. Kendi kopyanizi YAZMAYIN.
        Kapilar: tests/test_goc_yarim_kalirsa_db_kaybolmaz.py ·
                 tests/test_at_rest_encryption_rollout.py ·
                 tests/test_escrow_acl_dusunce_fail_closed.py
        """
        from database.sqlcipher_util import migrate_to_encrypted_if_needed

        migrate_to_encrypted_if_needed(self.db_path, self.app_data_dir, self.logger, etiket="Tedavi DB")

    def _safe_add_column(self, cursor, table: str, column_def: str, log_msg: str = None) -> None:
        """Idempotent şema-migrasyonu: `ALTER TABLE <table> ADD COLUMN <column_def>`.
        Sütun zaten varsa (yeni DB / önceki migrasyon) `_DB_OPERATIONAL` yutulur → sessizce geçilir.
        Eski DB'lere yeni kolon eklemenin TEK noktası (tekrarlanan try/except kalıbı buraya toplandı)."""
        try:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column_def}")
            if log_msg:
                self.logger.info(log_msg)
        except _DB_OPERATIONAL:
            pass

    def _semayi_kur(self, conn):
        cursor = conn.cursor()
        self._create_core_tables(cursor)
        self._create_core_indexes(cursor)
        self._migrate_and_index_core(cursor)
        self._create_vet_tables(cursor)
        self._migrate_vet_columns(cursor)
        self._create_vet_indexes(cursor)
        self._create_audit_table(cursor)
        conn.commit()

    def _create_core_tables(self, cursor):
        """Çekirdek tabloları oluştur (seans + parametreler + ayarlar + migration-kaydı + outbox + sensör örnekleri + event'ler)."""
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
                operator_email TEXT,
                patient_name TEXT,
                patient_notes TEXT,
                session_status TEXT DEFAULT 'completed',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT,
                sync_status INTEGER DEFAULT 0
            )
        ''')

        self._safe_add_column(cursor, "treatment_sessions", "sync_status INTEGER DEFAULT 0")
        # KRİTİK: mevcut DB'lerde updated_at yoksa ekle — end_session ve
        # update_session_notes bu kolonu yazıyor; yoksa OperationalError (seans bitirme/not patlar).
        self._safe_add_column(cursor, "treatment_sessions", "updated_at TEXT")

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

        # AI Analiz Geçmişi (2026-07): profesyonel DETAYLI kayıt — eski düz-metin ai_diagnoses.jsonl
        # yerine SQLCipher-ŞİFRELİ (hasta adı TAM yazılabilir, KVKK-güvenli). TÜM profillerin AI analizleri.
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ai_analyses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                mode TEXT,
                module_id TEXT,
                module_label TEXT,
                patient_name TEXT,
                operator_email TEXT,
                input_type TEXT,
                result_summary TEXT,
                result_detail TEXT,
                confidence REAL
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_ai_analyses_module ON ai_analyses(module_id)')
        # Klinik-ici sahiplik (2026-07-12): islemi yapan hekim e-postasi (eski DB'lere idempotent).
        self._safe_add_column(cursor, "ai_analyses", "operator_email TEXT", "ai_analyses.operator_email eklendi")

        # HEKİM DEĞERLENDİRMESİ (2026-08-06, sahip isteği: "veteriner red/onay/düzeltme — AI modlarında").
        # AI çıktısı bir ÖNERİdir; klinik karar hekimindir. Bu üç kolon kararın kalıcı izini tutar:
        #   review_status  : "" (değerlendirilmedi) | "approved" | "rejected" | "corrected"
        #   review_note    : red gerekçesi / düzeltme metni (hekimin kendi teşhisi)
        #   reviewed_by/at : kim, ne zaman karar verdi (klinik sorumluluk zinciri)
        # ⚠️ Varsayılan BOŞ — geçmişteki kayıtlar "onaylanmış" GİBİ görünmemeli; değerlendirilmemiş
        # bir AI çıktısını onaylı saymak yanlış güvence olurdu.
        self._safe_add_column(
            cursor, "ai_analyses", "review_status TEXT DEFAULT ''", "ai_analyses.review_status eklendi"
        )
        self._safe_add_column(cursor, "ai_analyses", "review_note TEXT DEFAULT ''", "ai_analyses.review_note eklendi")
        self._safe_add_column(cursor, "ai_analyses", "reviewed_by TEXT DEFAULT ''", "ai_analyses.reviewed_by eklendi")
        self._safe_add_column(cursor, "ai_analyses", "reviewed_at TEXT DEFAULT ''", "ai_analyses.reviewed_at eklendi")

        # ── HASTA KİMLİĞİ BAĞI (sahip isteği 2026-09-12) ───────────────────────────────
        # ⚠️ ANALİZLER HASTAYA *ADLA* BAĞLIYDI ve bunun üç ayrı kırılganlığı vardı:
        #   1) AYNI ADLI İKİ HAYVAN: "Mia" adlı iki kedinin analizleri karışıyordu.
        #   2) AD DEĞİŞİKLİĞİ: hasta kaydında ad düzeltilince eski analizler KOPUYORDU.
        #   3) MASKELEME: `PEMF_MASK_HISTORY_PII=1` açıkken ad `[SIFRELENMEMIS-DB]` yazılır →
        #      TÜM analizler aynı "ada" düşer ve eşleme bütünüyle çöker.
        # `patient_uuid` PII DEĞİLDİR (opak kimlik) → maskelenmez, şifrelemeden bağımsız çalışır.
        # ⚠️ AD KOLONU SİLİNMEZ: eski kayıtların tek bağı o ve gösterimde hâlâ kullanılıyor.
        self._safe_add_column(cursor, "ai_analyses", "patient_uuid TEXT DEFAULT ''", "ai_analyses.patient_uuid eklendi")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ai_analyses_patient_uuid ON ai_analyses(patient_uuid)")

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

    def _create_core_indexes(self, cursor):
        """Çekirdek tabloların sorgu indekslerini oluştur."""
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
        # B-6.3: get_session_history 11× self-JOIN'i (session_id + parameter_name filtreler) hızlandır →
        # composite index ile her JOIN indeksli lookup olur (aksi halde parameter_name için tarama).
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_session_params_sid_name
            ON session_parameters(session_id, parameter_name)
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

    def _migrate_and_index_core(self, cursor):
        """Çekirdek kolon-migrasyonları (patient_name/session_uuid/idempotency_key) + bağımlı session_uuid indeksi."""
        # Mevcut tabloya patient_name sütunu ekle (migration)
        self._safe_add_column(cursor, "treatment_sessions", "patient_name TEXT", "patient_name sütunu eklendi")
        # Session bazlı idempotent kimlik
        self._safe_add_column(cursor, "treatment_sessions", "session_uuid TEXT", "session_uuid sütunu eklendi")
        self._safe_add_column(cursor, "outbox_messages", "idempotency_key TEXT", "idempotency_key sütunu eklendi")

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_treatment_sessions_uuid
            ON treatment_sessions(session_uuid)
        ''')

    def _create_vet_tables(self, cursor):
        """Veteriner katmanı tabloları: patients + bobin çalışmaları + sensör-özeti (geriye uyumlu)."""
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
                owner_email TEXT,
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

    def _migrate_vet_columns(self, cursor):
        """Veteriner katmanı için idempotent kolon-migrasyonları (treatment_sessions/patients/sensor_samples)."""
        # treatment_sessions yeni kolonlari (idempotent, nullable).
        self._safe_add_column(
            cursor, "treatment_sessions", "patient_id INTEGER", "treatment_sessions.patient_id sütunu eklendi"
        )
        self._safe_add_column(
            cursor, "treatment_sessions", "started_epoch REAL", "treatment_sessions.started_epoch sütunu eklendi"
        )
        self._safe_add_column(
            cursor, "treatment_sessions", "ended_epoch REAL", "treatment_sessions.ended_epoch sütunu eklendi"
        )
        # Klinik-ici sahiplik (2026-07-12): seansi baslatan hekim e-postasi ("Benim/Tum Klinik" filtresi).
        self._safe_add_column(
            cursor, "treatment_sessions", "operator_email TEXT", "treatment_sessions.operator_email sütunu eklendi"
        )
        # patients.owner_email (rapor e-postasi) — eski DB'lere idempotent ekle.
        self._safe_add_column(cursor, "patients", "owner_email TEXT", "patients.owner_email sütunu eklendi")
        # sensor_samples yeni kolonlari (idempotent, nullable).
        # SEMANTIK NOT: sensor_samples artik DAKIKA-ORTALAMASI tutabilir;
        # sample_count = ortalamaya giren ham okuma sayisi. Sema ayni kalir,
        # mevcut satirlar (ham okuma) icin bu kolonlar NULL kalir — geriye uyumlu.
        self._safe_add_column(
            cursor, "sensor_samples", "coil_run_id INTEGER", "sensor_samples.coil_run_id sütunu eklendi"
        )
        self._safe_add_column(
            cursor, "sensor_samples", "ambient_temp_c REAL", "sensor_samples.ambient_temp_c sütunu eklendi"
        )
        self._safe_add_column(cursor, "sensor_samples", "phase REAL", "sensor_samples.phase sütunu eklendi")
        self._safe_add_column(
            cursor, "sensor_samples", "sample_count INTEGER", "sensor_samples.sample_count sütunu eklendi"
        )

    def _create_vet_indexes(self, cursor):
        """Veteriner tablo indeksleri + (migration SONRASI) treatment_sessions.patient_id indeksi."""
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
        # P2 audit 2026-06-28: get_session_history patients'a ts.patient_id ile JOIN yapar;
        # index yoksa full-scan (binlerce seansta yavas). patient_id sutunu migration'dan
        # SONRA olustugu icin index'i burada (sema sonrasi) ekliyoruz.
        try:
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_ts_patient_id ON treatment_sessions(patient_id)')
        except _DB_OPERATIONAL:
            pass  # patient_id sutunu yoksa (cok eski DB) sessizce atla

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

        # Migration öncesi backup.
        # DENETIM P2: donus degeri YOK SAYILIYORDU. create_backup hata halinde istisnayi yutup
        # sessizce False doner ve geride 0-baytlik/yarim bir dosya BIRAKABILIR. Asagidaki rollback
        # dali ise yedegin gecerliligini HIC dogrulamadan once CANLI DB'yi siliyordu → disk-dolu
        # gibi bilesik bir arizada (once create_backup, sonra _ensure_schema_version basarisiz)
        # tum tedavi gecmisi bos/bozuk bir dosyayla degistirilip KALICI kayboluyordu.
        _backup_ok = False
        try:
            _backup_ok = bool(self.create_backup(str(backup_path)))
        except Exception:
            self.logger.exception("Migration oncesi yedek alinamadi (istisna).")
        if not _backup_ok or not os.path.exists(backup_path) or os.path.getsize(backup_path) == 0:
            _backup_ok = False
            self.logger.error(
                "Migration oncesi yedek OLUSTURULAMADI (%s) → rollback GUVENLI DEGIL; "
                "yarim yedek dosyasi temizleniyor ve rollback denenmeyecek.",
                backup_path,
            )
            try:
                if os.path.exists(backup_path):
                    os.remove(backup_path)
            except Exception:
                pass
        # B-7.2: migration_backups ROTASYONU — son 5; eskiden her migration bir tam-DB kopyası
        # bırakıp sınırsız büyüyordu.
        try:
            _mbks = sorted(backup_dir.glob("pre_migration_*.db"))
            for _old in _mbks[:-5]:
                try:
                    _old.unlink()
                except Exception:
                    pass
        except Exception:
            pass

        try:
            self._ensure_schema_version()
        except Exception as migration_error:
            self.logger.error(f"Schema migration başarısız, rollback deneniyor: {migration_error}")
            # DENETIM P2: yedek GECERSIZSE rollback yapma — canli DB'yi silip yerine bos/bozuk
            # dosya koymak, migration hatasindan cok daha kotudur (kalici veri kaybi). Yedek yoksa
            # canli DB'ye DOKUNMA ve orijinal hatayi yukselt; veri diskte saglam kalir.
            if not _backup_ok:
                self.logger.error(
                    "Gecerli yedek YOK → rollback ATLANDI, canli DB'ye DOKUNULMADI. "
                    "Veri saglam; migration hatasi yukseltiliyor."
                )
                raise
            try:
                self.close_connections()
                if os.path.exists(self.db_path):
                    os.remove(self.db_path)
                # DENETIM P2: WAL modunda kalan yan-dosyalar SILINMIYORDU. Son baglanti temiz
                # kapandiginda SQLite bunlari kendi siler; ama kapanis-checkpoint'i de basarisiz
                # olduysa (ayni disk-dolu/I-O arizasi) bayat -wal cerceveleri geri-yuklenen DB'ye
                # REPLAY edilip sema/veriyi karistirir. Kopyalamadan once acikca temizle
                # (sqlcipher_util'daki dogrulanmis desenin aynisi).
                for _sfx in ("-wal", "-shm"):
                    try:
                        # ⚠️ DENETİM 2026-08-17: burada `self.db_path + _sfx` yazıyordu ve
                        # `self.db_path` bir `Path` → `TypeError: unsupported operand type(s) for
                        # +: 'WindowsPath' and 'str'`. İfade `os.remove`a HİÇ ulaşmıyor, aşağıdaki
                        # `except` yalnız "temizlenemedi" uyarısı basıyordu → **koruma ölü koddu.**
                        # Doğru kardeş desen: `database/auth_db.py` → `Path(str(...) + _sfx)`.
                        # Kilit: `tests/test_rollback_wal_temizligi.py` (bileşik arızayı modelleyip
                        # temizliği DAVRANIŞSAL ölçer; eski "koruma" bir kaynak-metin grep'iydi ve
                        # TypeError'lı kodu geçiriyordu).
                        _side = str(self.db_path) + _sfx
                        if os.path.exists(_side):
                            os.remove(_side)
                    except Exception:
                        self.logger.warning("Rollback: %s temizlenemedi", _sfx, exc_info=True)
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
            self._set_system_setting(version_key, str(self.TARGET_SCHEMA_VERSION), 'PEMF DB schema version')
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'INSERT OR IGNORE INTO schema_migrations (version, description) VALUES (?, ?)',
                    (self.TARGET_SCHEMA_VERSION, 'bootstrap schema version'),
                )
                conn.commit()
            return

        if current_version < self.TARGET_SCHEMA_VERSION:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                for version in range(current_version + 1, self.TARGET_SCHEMA_VERSION + 1):
                    cursor.execute(
                        'INSERT OR IGNORE INTO schema_migrations (version, description) VALUES (?, ?)',
                        (version, f'upgrade schema to v{version}'),
                    )
                conn.commit()
            self._set_system_setting(version_key, str(self.TARGET_SCHEMA_VERSION), 'PEMF DB schema version')

    def get_schema_version(self) -> int:
        """Aktif DB schema version değerini döndür."""
        value = self._get_system_setting('db_schema_version')
        try:
            return int(value) if value is not None else 0
        except (TypeError, ValueError):
            return 0
