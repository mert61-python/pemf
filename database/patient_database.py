"""
Hasta Veritabani Yonetim Sistemi.

Bu modul, PEMF vet sisteminde hasta bilgilerinin saklanmasi ve yonetimi icin
SQLite tabanli bir veritabani sistemi saglar.
"""

import base64
import contextlib
import hashlib
import hmac
import logging
import os
import re
import sqlite3
import sys
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

try:
    from pemf_gui.config import get_config
except ModuleNotFoundError:
    # Support direct script execution (e.g. Spyder %runfile)
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    from pemf_gui.config import get_config

# P0 audit 2026-06-28: hasta PII whole-DB SQLCipher sifrelemesi (paylasilan yardimci modul).
from database.sqlcipher_util import (
    get_sqlcipher_key,
    import_sqlcipher,
    migrate_to_encrypted_if_needed,
    open_encrypted_conn,
)

# P0 audit 2026-06-28: SQLCipher baglantilarinda exception'lar sqlcipher3.dbapi2.* tipinde gelir;
# duz sqlite3.* except'leri bunlari YAKALAMAZ (ornek: ALTER 'duplicate column' patlar). Hem
# sqlite3 hem sqlcipher3 variantini yakala (treatment_history_db deseni).
_sqlcipher_mod_exc = import_sqlcipher()
if _sqlcipher_mod_exc is not None:
    _DB_OPERATIONAL = (sqlite3.OperationalError, _sqlcipher_mod_exc.OperationalError)
    _DB_ERROR = (sqlite3.Error, _sqlcipher_mod_exc.Error)
    _DB_INTEGRITY = (sqlite3.IntegrityError, _sqlcipher_mod_exc.IntegrityError)
else:
    _DB_OPERATIONAL = sqlite3.OperationalError
    _DB_ERROR = sqlite3.Error
    _DB_INTEGRITY = sqlite3.IntegrityError


class PatientDatabase:
    """Hasta veritabani yonetim sinifi."""

    _ENCRYPTED_FIELDS = {"name", "owner", "vet_contact", "species", "breed", "age", "weight", "owner_email", "operator_email"}
    _SEARCHABLE_FIELDS = ("name", "owner", "species", "breed", "age", "weight")

    def __init__(self, db_file: str = "patients.db"):
        self.db_file = Path(db_file)
        self.lock = threading.Lock()
        self.logger = logging.getLogger("PatientDatabase")
        self.config_manager = get_config()
        self._local = threading.local()  # Performans Fix (4.2): Thread-local connection pool

        # P0 audit 2026-06-28: whole-DB SQLCipher at-rest (keyring 'sqlcipher_key' — treatment
        # DB ile AYNI anahtar). Anahtar/binding BIR KEZ cozulur (per-op keyring okumasi olmasin).
        self._key_dir = Path(self.db_file).resolve().parent
        self._sqlcipher_mod = import_sqlcipher()
        self._cipher_key = get_sqlcipher_key(self._key_dir, self.logger)
        self.at_rest_encrypted = bool(self._cipher_key and self._sqlcipher_mod is not None)
        # B-1.4 (audit 2026-07-06): TreatmentHistoryDB ile TUTARLI fail-closed. PEMF_ENCRYPT_AT_REST=1
        # ACIKCA istendi ama SQLCipher saglanamadi (binding yok / anahtar acilamadi) → hasta PII'sini
        # DUZ-METIN yazmaktansa patients.db'yi ACMA. Eskiden PatientDatabase sessizce duz-metine
        # dusuyordu (TreatmentHistoryDB hard-fail ederken) → "sifreli sanip cleartext PII yazma"
        # sessiz sizinti + iki DB arasi tutarsiz PII garantisi. Uretimde sqlcipher3 EXE'ye bundle'li
        # + anahtar var → buraya DUSMEZ. (test/dev: bayrak kapali → duz-metin, geriye uyumlu.)
        if not self.at_rest_encrypted and os.getenv("PEMF_ENCRYPT_AT_REST", "0") == "1":
            raise RuntimeError(
                "PEMF_ENCRYPT_AT_REST=1 ama hasta DB'si icin SQLCipher saglanamadi (sqlcipher3 binding "
                "yok veya .sqlcipher_key/keyring anahtari acilamadi) → hasta PII'sini duz-metin "
                "yazmamak icin patients.db ACILMADI. sqlcipher3'u kurun ve anahtari dogrulayin."
            )
        # P0 audit 2026-06-28: SQLCipher cursor'i sqlite3.Row KABUL ETMEZ (TypeError) -> baglantiya
        # uygun Row sec (sqlcipher3.Row sifreli iken, sqlite3.Row duz-metin iken).
        self._row_factory = getattr(self._sqlcipher_mod, "Row", sqlite3.Row) if self.at_rest_encrypted else sqlite3.Row
        # Mevcut DB duz-metinse ve anahtar varsa -> sifreliye MIGRATE et (.plain.bak yedek).
        migrate_to_encrypted_if_needed(self.db_file, self._key_dir, self.logger)

        # Ayrik bir arama HMAC anahtari tureterek sifreleme anahtarini dogrudan kullanmiyoruz.
        self._search_hmac_key = hashlib.sha256(
            self.config_manager._encryption_key + b":patient_search_index:v1"
        ).digest()
        self._init_database()

    @contextlib.contextmanager
    def _get_connection(self):
        """Thread-local baglanti havuzu — baglanti thread yasadikca YENIDEN KULLANILIR. Eskiden HER
        context cikisinda kapatiliyordu → SQLCipher KDF'i her islemde yeniden turetiliyor (agir) ve
        havuz anlamsizlasiyordu. Hata durumunda rollback ile transaction sizintisi temizlenir;
        baglanti bozuksa kapatilip sifirlanir (sonraki cagri temiz baglanti acar)."""
        created_here = False
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            # P0 audit 2026-06-28: whole-DB SQLCipher (anahtar+binding varsa); yoksa duz-metin
            # sqlite (geriye uyumlu) + operatore GORUNUR tek-seferlik uyari.
            if self._cipher_key and self._sqlcipher_mod is not None:
                conn = open_encrypted_conn(self.db_file, self._cipher_key, self._sqlcipher_mod)
            else:
                if not getattr(self, "_enc_warned", False):
                    self._enc_warned = True
                    self.logger.warning(
                        "PATIENT DB AT-REST SIFRELEME KAPALI: hasta PII duz-metin SQLite yaziliyor. "
                        "Uretimde sqlcipher3 + PEMF_ENCRYPT_AT_REST=1 (keyring) ayarlayin."
                    )
                conn = sqlite3.connect(self.db_file, timeout=30.0, check_same_thread=False)  # B-6.2
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA foreign_keys=ON")   # B-7.3: patient_search_index ON DELETE CASCADE aktif
            conn.execute("PRAGMA busy_timeout=5000")  # B-6.2: 'database is locked' yerine bekle
            self._local.conn = conn
            created_here = True

        try:
            yield self._local.conn
        except Exception:
            # Transaction sizintisini temizle (retained-connection tutarliligi); baglanti bozuksa
            # kapat+sifirla → sonraki cagri temiz baglanti acar (bozuk baglantiyi yeniden kullanma).
            try:
                self._local.conn.rollback()
            except Exception:
                try:
                    self._local.conn.close()
                except Exception:
                    pass
                self._local.conn = None
            raise
        finally:
            # B-6.2: kisa-omurlu WORKER thread'lerinde baglanti birikmesini onle — bu context'te
            # ACILDIYSA + ana thread DEGILSE kapat. Ana thread'de REUSE korunur (SQLCipher KDF maliyeti).
            if (created_here and self._local.conn is not None
                    and threading.current_thread() is not threading.main_thread()):
                try:
                    self._local.conn.close()
                except Exception:
                    pass
                self._local.conn = None

    def create_backup(self, backup_path: str) -> bool:
        """Çalışan hasta DB'sinden dosya yedeği (online backup API). DB ŞİFRELİYSE yedek de AYNI
        anahtarla ŞİFRELİ olur (düz hedefe yedek PII sızdırır). audit B-7.2: PatientDB'nin yedeği yoktu."""
        try:
            bdir = os.path.dirname(backup_path)
            if bdir:
                os.makedirs(bdir, exist_ok=True)
            with self._get_connection() as src:
                if self.at_rest_encrypted and self._sqlcipher_mod is not None:
                    dst = self._sqlcipher_mod.connect(backup_path)
                    dst.execute("PRAGMA key='{}'".format(self._cipher_key.replace("'", "''")))
                else:
                    dst = sqlite3.connect(backup_path)
                try:
                    src.backup(dst)
                    dst.commit()
                finally:
                    dst.close()
            return True
        except Exception:
            self.logger.exception("PatientDB create_backup hatası")
            return False

    def _safe_add_column(self, cursor, table: str, column_def: str) -> None:
        """Idempotent şema-migrasyonu: ALTER TABLE ADD COLUMN; sütun zaten varsa sessizce geç.
        (Eski DB'lere yeni kolon eklemenin tek noktası — tekrarlanan try/except kalıbı buraya toplandı.)"""
        try:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column_def}")
        except _DB_OPERATIONAL:
            pass

    def _init_database(self) -> None:
        """SQLite şemasını oluştur + HMAC arama indeksini garanti et."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                self._create_patient_schema(cursor)
                self._ensure_search_index(cursor)
                conn.commit()
        except _DB_ERROR as e:
            raise RuntimeError(f"Database initialization failed: {e}") from e

    def _create_patient_schema(self, cursor) -> None:
        """patients + patient_search_index tabloları/indeksleri + idempotent kolon-migrasyonları."""
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS patients (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                species TEXT,
                breed TEXT,
                age TEXT,
                weight TEXT,
                owner TEXT,
                vet_contact TEXT,
                owner_email TEXT,
                operator_email TEXT,
                last_treatment_at TEXT,
                anonymized INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                sync_status INTEGER DEFAULT 0
            )
            """
        )
        # Eski DB'lere idempotent kolon eklemeleri (yeni DB'de CREATE zaten içerir → ALTER sessizce geçer):
        self._safe_add_column(cursor, "patients", "sync_status INTEGER DEFAULT 0")
        self._safe_add_column(cursor, "patients", "owner_email TEXT")
        # Klinik-ici hasta sahipligi (2026-07-12): kaydi olusturan hekimin e-postasi (sifreli).
        # "Benim Hastalarim" vs "Tum Klinik" gorunum filtresi icin; klinikler-arasi izolasyon zaten local-DB ile.
        self._safe_add_column(cursor, "patients", "operator_email TEXT")
        # KVKK retention (2026-06-28): son tedavi tarihi + anonim bayragi (inaktiflik bazli anonimlestirme).
        self._safe_add_column(cursor, "patients", "last_treatment_at TEXT")
        self._safe_add_column(cursor, "patients", "anonymized INTEGER DEFAULT 0")

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_patient_name
            ON patients(name)
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_patient_owner
            ON patients(owner)
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS patient_search_index (
                patient_id TEXT NOT NULL,
                field_name TEXT NOT NULL,
                token_hmac TEXT NOT NULL,
                PRIMARY KEY (patient_id, field_name, token_hmac),
                FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE CASCADE
            )
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_patient_search_token
            ON patient_search_index(token_hmac)
            """
        )

    def _ensure_search_index(self, cursor) -> None:
        """HMAC arama indeksini garanti et: tablo BOŞSA veya arama-anahtarı DEĞİŞTİYSE yeniden kur.
        (P2 audit: HMAC indeksi _search_hmac_key'e bağlı; anahtar değişirse eski token'lar eşleşmez →
        arama SESSİZCE bozulur. Anahtar parmak-izini saklayıp değişimi tespit ediyoruz.)"""
        cursor.execute("SELECT COUNT(*) FROM patient_search_index")
        count = cursor.fetchone()[0]
        _fp = hashlib.sha256(self._search_hmac_key).hexdigest()[:16]
        _fp_file = self._key_dir / ".patient_search_keyfp"
        _stored_fp = ""
        try:
            if _fp_file.exists():
                _stored_fp = _fp_file.read_text(encoding="utf-8").strip()
        except Exception:
            pass
        if count == 0 or (_stored_fp and _stored_fp != _fp):
            if count > 0:
                self.logger.warning("Hasta arama anahtari degismis → HMAC indeksi yeniden kuruluyor.")
            self._rebuild_search_index(cursor)
        try:
            _fp_file.write_text(_fp, encoding="utf-8")
        except Exception:
            pass

    def _normalize_search_value(self, value: str) -> str:
        text = str(value or "").strip().lower()
        return re.sub(r"\s+", " ", text)

    def _tokenize_for_search(self, value: str) -> Set[str]:
        normalized = self._normalize_search_value(value)
        if not normalized:
            return set()
        tokens = set(re.findall(r"[\w\-\.]+", normalized))
        tokens.add(normalized)
        return {token for token in tokens if token}

    def _hmac_token(self, token: str) -> str:
        return hmac.new(self._search_hmac_key, token.encode("utf-8"), hashlib.sha256).hexdigest()

    def _decrypt_patient_fields(self, patient: Dict[str, Any]) -> Dict[str, Any]:
        for field in self._ENCRYPTED_FIELDS:
            patient[field] = self._decrypt_field(patient.get(field, ""))
        return patient

    def _index_patient_search_terms(self, cursor: sqlite3.Cursor, patient_id: str, patient_info: Dict[str, str]) -> None:
        cursor.execute("DELETE FROM patient_search_index WHERE patient_id = ?", (patient_id,))

        index_rows = []
        for field in self._SEARCHABLE_FIELDS:
            tokens = self._tokenize_for_search(patient_info.get(field, "") or "")
            for token in tokens:
                index_rows.append((patient_id, field, self._hmac_token(token)))

        if index_rows:
            cursor.executemany(
                """
                INSERT OR IGNORE INTO patient_search_index (patient_id, field_name, token_hmac)
                VALUES (?, ?, ?)
                """,
                index_rows,
            )

    def _rebuild_search_index(self, cursor: sqlite3.Cursor) -> None:
        cursor.execute("DELETE FROM patient_search_index")
        cursor.execute(
            """
            SELECT id, name, species, breed, age, weight, owner, vet_contact
            FROM patients
            """
        )
        rows = cursor.fetchall()

        for row in rows:
            patient = {
                "id": row[0],
                "name": self._decrypt_field(row[1] or ""),
                "species": self._decrypt_field(row[2] or ""),
                "breed": self._decrypt_field(row[3] or ""),
                "age": self._decrypt_field(row[4] or ""),
                "weight": self._decrypt_field(row[5] or ""),
                "owner": self._decrypt_field(row[6] or ""),
                "vet_contact": self._decrypt_field(row[7] or ""),
            }
            self._index_patient_search_terms(cursor, patient["id"], patient)

    def _refresh_search_index_for_patient(self, cursor: sqlite3.Cursor, patient_id: str) -> None:
        cursor.execute(
            """
            SELECT id, name, species, breed, age, weight, owner, vet_contact
            FROM patients
            WHERE id = ?
            """,
            (patient_id,),
        )
        row = cursor.fetchone()
        if not row:
            cursor.execute("DELETE FROM patient_search_index WHERE patient_id = ?", (patient_id,))
            return

        patient = {
            "id": row[0],
            "name": self._decrypt_field(row[1] or ""),
            "species": self._decrypt_field(row[2] or ""),
            "breed": self._decrypt_field(row[3] or ""),
            "age": self._decrypt_field(row[4] or ""),
            "weight": self._decrypt_field(row[5] or ""),
            "owner": self._decrypt_field(row[6] or ""),
            "vet_contact": self._decrypt_field(row[7] or ""),
        }
        self._index_patient_search_terms(cursor, patient_id, patient)

    def _encrypt_field(self, value: str) -> str:
        if value is None:
            return ""
        if isinstance(value, str) and value == "":
            return ""
        value = str(value)
        # Tag encrypted values to avoid decrypt attempts on legacy/plain text rows.
        return "enc:" + self.config_manager._encrypt_value(value)

    def _decrypt_field(self, value: str) -> str:
        if value is None:
            return ""
        value = str(value)
        if value == "":
            return ""
        if value.startswith("enc:"):
            inner = value[4:]
            try:
                dec = self.config_manager._decrypt_value(inner)
            except Exception:
                dec = inner
            # _decrypt_value başarısızsa girdiyi aynen döndürür → çözülemeyen (farklı anahtar/eski/template) kayıt.
            if dec == inner or (isinstance(dec, str) and dec.startswith("Z0FBQUFB")):
                return "[okunamayan kayıt]"
            return dec

        # Backward compatibility: older rows may contain encrypted payloads
        # without the enc: prefix. Try silent decrypt, otherwise return as-is.
        try:
            encrypted_bytes = base64.urlsafe_b64decode(value.encode())
            decrypted = self.config_manager._cipher.decrypt(encrypted_bytes)
            return decrypted.decode()
        except Exception:
            # Çözülemedi. Fernet token gibi görünüyorsa (farklı anahtarla şifrelenmiş eski/şablon
            # kayıt) ham ciphertext'i KULLANICIYA GÖSTERME; düz-metin legacy ise olduğu gibi bırak.
            try:
                if base64.urlsafe_b64decode(value.encode()).startswith(b"gAAAAA"):
                    return "[okunamayan kayıt]"
            except Exception:
                pass
            return value

    def add_patient(self, patient_info: Dict[str, str]) -> str:
        """Yeni hasta ekler ve olusan patient_id degerini dondurur."""
        with self.lock:
            patient_id = str(uuid.uuid4())
            now = datetime.now().isoformat()

            try:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        """
                        INSERT INTO patients
                        (id, name, species, breed, age, weight, owner, vet_contact, owner_email, operator_email, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            patient_id,
                            self._encrypt_field(patient_info.get("name", "")),
                            self._encrypt_field(patient_info.get("species", "")),
                            self._encrypt_field(patient_info.get("breed", "")),
                            self._encrypt_field(patient_info.get("age", "")),
                            self._encrypt_field(patient_info.get("weight", "")),
                            self._encrypt_field(patient_info.get("owner", "")),
                            self._encrypt_field(patient_info.get("vet_contact", "")),
                            self._encrypt_field(patient_info.get("owner_email", "")),
                            self._encrypt_field(patient_info.get("operator_email", "")),
                            now,
                            now,
                        ),
                    )
                    self._index_patient_search_terms(cursor, patient_id, patient_info)
                    conn.commit()
                return patient_id
            except _DB_ERROR as e:
                raise RuntimeError(f"Failed to add patient: {e}") from e

    def get_patient(self, patient_id: str) -> Optional[Dict[str, Any]]:
        """Belirtilen ID'ye sahip hastayi getirir."""
        with self.lock:
            try:
                with self._get_connection() as conn:
                    conn.row_factory = self._row_factory
                    cursor = conn.cursor()
                    cursor.execute("SELECT * FROM patients WHERE id = ?", (patient_id,))
                    row = cursor.fetchone()

                    if not row:
                        return None

                    patient = dict(row)
                    return self._decrypt_patient_fields(patient)
            except _DB_ERROR:
                return None

    def get_all_patients(self) -> List[Dict[str, Any]]:
        """Tum hastalari getirir."""
        with self.lock:
            try:
                with self._get_connection() as conn:
                    conn.row_factory = self._row_factory
                    cursor = conn.cursor()
                    cursor.execute("SELECT * FROM patients ORDER BY created_at DESC")
                    rows = cursor.fetchall()

                    patients: List[Dict[str, Any]] = []
                    for row in rows:
                        patient = dict(row)
                        patients.append(self._decrypt_patient_fields(patient))
                    return patients
            except _DB_ERROR:
                return []

    def update_patient(self, patient_id: str, patient_info: Dict[str, str]) -> bool:
        """Hasta bilgilerini gunceller."""
        with self.lock:
            try:
                with self._get_connection() as conn:
                    cursor = conn.cursor()

                    updates: List[str] = []
                    values: List[Any] = []
                    for key, value in patient_info.items():
                        # operator_email = kaydi olusturan hekim; yalnizca add_patient'ta set edilir,
                        # duzenlemede DEGISTIRILEMEZ (sahiplik sabit kalir).
                        if key == "operator_email":
                            continue
                        if key in self._ENCRYPTED_FIELDS:
                            updates.append(f"{key} = ?")
                            values.append(self._encrypt_field(value))

                    if not updates:
                        return False

                    updates.append("updated_at = ?")
                    values.append(datetime.now().isoformat())
                    values.append(patient_id)

                    query = f"UPDATE patients SET {', '.join(updates)} WHERE id = ?"
                    cursor.execute(query, values)
                    if cursor.rowcount > 0:
                        self._refresh_search_index_for_patient(cursor, patient_id)
                    conn.commit()
                    return cursor.rowcount > 0
            except _DB_ERROR:
                return False

    def touch_last_treatment(self, patient_id: str) -> None:
        """KVKK retention: bir tedavi gerceklestiginde hastanin last_treatment_at'ini guncelle
        (inaktiflik-bazli anonimlestirmenin tarih kaynagi). Hata sessizce loglanir (tedaviyi bloklamaz)."""
        if not patient_id:
            return
        try:
            with self.lock:
                with self._get_connection() as conn:
                    conn.execute("UPDATE patients SET last_treatment_at = ? WHERE id = ?",
                                 (datetime.now().isoformat(), patient_id))
                    conn.commit()
        except Exception:
            self.logger.debug("touch_last_treatment hatasi", exc_info=True)

    def anonymize_inactive_patients(self, inactive_days: int = 1825) -> List[str]:
        """KVKK: son tedaviden (yoksa kayit tarihinden) inactive_days'ten (vars. 5 YIL=1825) uzun
        sure gecmis hastalarin PII'sini (ad/sahip/iletisim/e-posta) ANONIMLESTIR — SILMEZ (klinik
        istatistikleri/tedavi gecmisi korunur). Muafiyet yok. Anonimlestirilen UUID listesini doner
        (treatment-history DB'deki hasta kopyasi da guncellensin diye)."""
        cutoff = (datetime.now() - timedelta(days=max(1, int(inactive_days)))).isoformat()
        anonymized: List[str] = []
        try:
            with self.lock:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT id FROM patients WHERE COALESCE(anonymized,0)=0 "
                        "AND COALESCE(last_treatment_at, created_at) < ?", (cutoff,))
                    ids = [r[0] for r in cursor.fetchall()]
                    enc_anon = self._encrypt_field("[ANONIM]")
                    enc_empty = self._encrypt_field("")
                    now_iso = datetime.now().isoformat()
                    for pid in ids:
                        cursor.execute(
                            # Audit P2: sync_status=0 → anonimleştirme (redaction) bulut PUSH ile
                            # yayılsın; aksi halde sonraki PULL orijinal PII'yi geri yazıp de-anonymize ediyordu.
                            "UPDATE patients SET name=?, owner=?, vet_contact=?, owner_email=?, "
                            "anonymized=1, sync_status=0, updated_at=? WHERE id=?",
                            (enc_anon, enc_anon, enc_empty, enc_empty, now_iso, pid))
                        # Arama indeksini tazele — eski ad/sahip token'lari gitsin (artik aranmaz).
                        self._refresh_search_index_for_patient(cursor, pid)
                    conn.commit()
            # Audit P2: pid'leri YALNIZ commit BASARILI olduktan sonra raporla. Eskiden dongu-ici
            # append + orta-hata rollback'i → patients.db PII'yi TUTAR ama caller 'anonimlestirildi'
            # sanip history-DB'yi anonimlestirir (iki-DB tutarsizligi + KVKK retention ihlali).
            anonymized = list(ids)
            if anonymized:
                self.logger.warning("KVKK: %d inaktif hasta (>%d gun) anonimlestirildi.", len(anonymized), inactive_days)
        except Exception:
            self.logger.exception("anonymize_inactive_patients hatasi")
        return anonymized

    def delete_patient(self, patient_id: str) -> bool:
        """Belirtilen hastayi siler."""
        lock_acquired = self.lock.acquire(timeout=10.0)
        if not lock_acquired:
            return False

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id FROM patients WHERE id = ?", (patient_id,))
                if not cursor.fetchone():
                    return False

                cursor.execute("DELETE FROM patients WHERE id = ?", (patient_id,))
                rowcount = cursor.rowcount
                cursor.execute("DELETE FROM patient_search_index WHERE patient_id = ?", (patient_id,))
                conn.commit()
                return rowcount > 0
        except _DB_ERROR:
            return False
        finally:
            self.lock.release()

    def clear_all_patients(self) -> bool:
        """Tum hasta kayitlarini temizler."""
        with self.lock:
            try:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM patient_search_index")
                    cursor.execute("DELETE FROM patients")
                    conn.commit()
                    cursor.execute("VACUUM")
                    return True
            except _DB_ERROR:
                return False

    def search_patients(self, search_term: str) -> List[Dict[str, Any]]:
        """Hasta adi/sahibi/tur bilgisine gore arama yapar."""
        term = (search_term or "").strip()
        if not term:
            return self.get_all_patients()

        # ARAMA-TOKEN'LARI (false-negative fix): _tokenize_for_search hem kelime-token'larını HEM tam-normalize
        # 'birleşik' string'i döndürür. Birleşik token yalnız İNDEKSLEME için yararlı; aramada her token gerekli
        # sayıldığından ('HAVING COUNT(DISTINCT token_hmac)=len'), çok-kelimeli/çok-ALANLI arama ('Ali Veli' =
        # ad+sahip) için birleşik token tek bir alanın tamamına eşit olmadığından İNDEKSTE bulunmaz → tüm sonuç
        # YANLIŞLIKLA boş dönerdi. Aramada birleşik token'ı çıkar → kelime-token'ların AND'i (tek kelimede korunur).
        all_tokens = self._tokenize_for_search(term)
        normalized = self._normalize_search_value(term)
        tokens = sorted(t for t in all_tokens if t != normalized) or sorted(all_tokens)
        if not tokens:
            return []
        token_hashes = [self._hmac_token(token) for token in tokens]

        with self.lock:
            try:
                with self._get_connection() as conn:
                    conn.row_factory = self._row_factory
                    cursor = conn.cursor()

                    placeholders = ", ".join("?" for _ in token_hashes)
                    query = f"""
                        SELECT p.*
                        FROM patients p
                        INNER JOIN (
                            SELECT patient_id
                            FROM patient_search_index
                            WHERE token_hmac IN ({placeholders})
                            GROUP BY patient_id
                            HAVING COUNT(DISTINCT token_hmac) = ?
                        ) idx ON idx.patient_id = p.id
                        ORDER BY p.created_at DESC
                    """
                    cursor.execute(query, (*token_hashes, len(token_hashes)))
                    rows = cursor.fetchall()

                    results: List[Dict[str, Any]] = []
                    for row in rows:
                        patient = dict(row)
                        results.append(self._decrypt_patient_fields(patient))

                    return results
            except _DB_ERROR:
                return []

    def get_patient_count(self) -> int:
        """Toplam hasta sayisini dondurur."""
        with self.lock:
            try:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT COUNT(*) FROM patients")
                    return int(cursor.fetchone()[0])
            except _DB_ERROR:
                return 0


_patient_db = None
_patient_db_lock = threading.Lock()


def get_patient_database(app_data_dir=None) -> PatientDatabase:
    """Global hasta veritabani instance'ini dondurur."""
    global _patient_db
    with _patient_db_lock:
        if _patient_db is None:
            if app_data_dir is None:
                try:
                    from utils.path_utils import get_app_data_directory

                    app_data_dir = get_app_data_directory()
                except Exception:
                    app_data_dir = Path.home() / ".pemf_gui"

            db_file = app_data_dir / "patients.db"
            _patient_db = PatientDatabase(str(db_file))
    return _patient_db
