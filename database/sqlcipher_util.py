"""
SQLCipher at-rest sifreleme yardimcilari (paylasilan).

patient_database.py + treatment_history_db.py ayni at-rest anahtarini (keyring
'PEMF_GUI'/'sqlcipher_key') ve ayni plaintext->encrypted migrasyon desenini kullanir.
PEMF_ENCRYPT_AT_REST=1 + sqlcipher3 binding varsa whole-DB sifreleme; aksi halde duz-metin
(geriye uyumlu). [audit 2026-06-28 P0: hasta PII whole-DB sifrelenmeli — patient_database
eskiden duz sqlite3 + yalniz alan-Fernet idi; metadata/HMAC-index duz-metin kaliyordu.]

NOT: treatment_history_db.py kendi (calisan, test-edilmis) inline kopyasini korur; bu modul
yeni cagiranlar (patient_database) icindir. Anahtar ADI ayni oldugundan ayni anahtar paylasilir.
"""
import os
import sqlite3
import shutil

try:
    import keyring
except Exception:  # keyring opsiyonel
    keyring = None

_SERVICE = "PEMF_GUI"
_KEY_NAME = "sqlcipher_key"


def import_sqlcipher():
    """sqlcipher3 (Windows wheel) veya pysqlcipher3 binding; yoksa None."""
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


def get_sqlcipher_key(app_data_dir, logger=None) -> str:
    """Anahtar: keyring -> env (PEMF_SQLCIPHER_KEY) -> .sqlcipher_key dosyasi. Hicbiri yok +
    PEMF_ENCRYPT_AT_REST=1 ise yeni uretip saklar (keyring tercih, dosya fallback). Aksi '' (duz-metin)."""
    if keyring is not None:
        try:
            k = (keyring.get_password(_SERVICE, _KEY_NAME) or "").strip()
            if k:
                return k
        except Exception as e:
            if logger:
                logger.warning(f"keyring okuma hatasi: {e}")
    env_key = os.getenv("PEMF_SQLCIPHER_KEY", "").strip()
    if env_key:
        return env_key
    keyfile = app_data_dir / ".sqlcipher_key"
    try:
        if keyfile.exists():
            k = keyfile.read_text(encoding="utf-8").strip()
            if k:
                return k
    except Exception:
        pass
    if os.getenv("PEMF_ENCRYPT_AT_REST", "0") != "1":
        return ""  # acikca istenmedikce sifreleme acma
    import secrets
    newkey = secrets.token_urlsafe(32)
    stored = False
    if keyring is not None:
        try:
            keyring.set_password(_SERVICE, _KEY_NAME, newkey)
            stored = True
        except Exception:
            pass
    if not stored:
        try:
            keyfile.write_text(newkey, encoding="utf-8")
            try:
                os.chmod(keyfile, 0o600)
            except Exception:
                pass
        except Exception:
            pass
    if logger:
        logger.warning("Yeni SQLCipher anahtari uretildi (keyring=%s). ANAHTAR KAYBOLURSA sifreli veri OKUNAMAZ.", stored)
    return newkey


def open_encrypted_conn(db_path, key, sqlcipher_mod, row_factory=None, timeout=10.0, check_same_thread=False):
    """Onceden cozulmus anahtar + binding ile SQLCipher baglantisi ac (PRAGMA key)."""
    conn = sqlcipher_mod.connect(str(db_path), check_same_thread=check_same_thread, timeout=timeout)
    if row_factory is not None:
        conn.row_factory = row_factory
    escaped = key.replace("'", "''")
    conn.execute(f"PRAGMA key='{escaped}'")
    conn.execute("SELECT count(*) FROM sqlite_master")  # yanlis anahtar/migrate gerekli ise burada patlar
    return conn


def migrate_to_encrypted_if_needed(db_path, app_data_dir, logger=None):
    """Anahtar varsa ve mevcut DB DUZ-METIN ise sifreli kopyaya aktar (sqlcipher_export); eski
    duz-metin .plain.bak olur. Anahtar/binding yok veya zaten sifreli ise no-op (veri kaybi yok)."""
    def _close(cn):
        try:
            cn.close()
        except Exception:
            pass
    try:
        key = get_sqlcipher_key(app_data_dir, logger)
        if not key:
            return
        sqlcipher = import_sqlcipher()
        db = str(db_path)
        if sqlcipher is None or not os.path.exists(db):
            return
        keyq = "'" + key.replace("'", "''") + "'"
        # Zaten sifreli mi? — baglantiyi HER durumda kapat (yoksa sonraki move PermissionError).
        c = None
        try:
            c = sqlcipher.connect(db)
            c.execute(f"PRAGMA key={keyq}")
            c.execute("SELECT count(*) FROM sqlite_master")
            return  # acildi -> zaten sifreli
        except Exception:
            pass
        finally:
            if c is not None:
                _close(c)
        # Duz-metin mi? (plain sqlite3 acar) + WAL'i ana dosyaya checkpoint et.
        t = None
        try:
            t = sqlite3.connect(db)
            t.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            t.execute("SELECT count(*) FROM sqlite_master")
        except Exception:
            return  # bilinmeyen format -> DOKUNMA
        finally:
            if t is not None:
                _close(t)
        # MIGRATE: plaintext -> encrypted
        enc_tmp = db + ".enc.tmp"
        if os.path.exists(enc_tmp):
            os.remove(enc_tmp)
        enc_sql = enc_tmp.replace("'", "''")
        conn = None
        try:
            conn = sqlcipher.connect(db)  # anahtar yok -> duz-metin modunda acilir
            conn.execute(f"ATTACH DATABASE '{enc_sql}' AS enc KEY {keyq}")
            conn.execute("SELECT sqlcipher_export('enc')")
            conn.execute("DETACH DATABASE enc")
        finally:
            if conn is not None:
                _close(conn)
        # Dogrula
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
            if logger:
                logger.error("SQLCipher migrate: sifreli kopya bos -> iptal (duz-metin korunur).")
            return
        # Move'dan ONCE eski WAL/SHM'i temizle (acik handle/cakisma -> bozulma onle).
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
        if logger:
            logger.warning("DB plaintext -> SQLCipher MIGRATE edildi (artik sifreli). Duz-metin yedek: %s", backup)
    except Exception:
        if logger:
            logger.exception("SQLCipher migrate hatasi (duz-metin korunur)")
