"""Operatör hesapları (login/kayıt) — e-posta + PBKDF2-hash'lenmiş şifre. Yerel SQLite (app_data).

Şifreler PBKDF2-HMAC-SHA256 (200k iterasyon + rastgele 16-byte salt) ile saklanır → hash'ler at-rest
güvenli (düz-metin şifre ASLA saklanmaz; PBKDF2 kaba-kuvveti pahalılaştırır). Hasta PII değil, operatör
hesabıdır. `.edu` içeren e-posta → araştırma-modu profili görünür (gating frontend'de, e-posta'ya bakar).
"""
import hashlib
import hmac
import logging
import re
import secrets
import sqlite3
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

_PBKDF2_ITERS = 200_000
# Şifre kuralı: en az 8 karakter + EN AZ 1 büyük harf + 1 küçük harf + 1 rakam.
PASSWORD_RE = re.compile(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).{8,}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _hash_password(password: str, salt: bytes) -> str:
    return hashlib.pbkdf2_hmac("sha256", (password or "").encode("utf-8"), salt, _PBKDF2_ITERS).hex()


class AuthDB:
    def __init__(self, app_data_dir):
        self.db_path = Path(app_data_dir) / "auth_users.db"
        self._lock = threading.Lock()
        self._init()
        self._harden_permissions()

    def _harden_permissions(self) -> None:
        """DENETIM P3: auth_users.db (operator e-postalari + PBKDF2 hash'leri) duz SQLite ve NTFS
        ACL kilidi YOK → ProgramData'nin miras izinleriyle makinedeki herhangi bir kullanici
        hash'leri kopyalayip CEVRIMDISI kaba-kuvvet uygulayabilir.

        ⚠️ Bu DB, sir dosyalarindan FARKLI olarak surekli acilip yazilir (her giris/kayit).
        Kilidi SYSTEM+Administrators ile SINIRLAMAK, yonetici OLMAYAN bir surecte (Tauri launcher
        "kullanici-basina kurulum, yonetici hakki GEREKTIRMEZ") sureci KENDI DB'sinden disari
        atar ve kimlik dogrulamayi TAMAMEN kirar — bulgunun kendisinden kotu bir sonuc (bu
        gelistirme sirasinda fiilen yasandi). Bu yuzden keep_current_user=True kullanilir:
        yerel `Users` grubu yine erisemez, ama sureci calistiran hesap erisimini KORUR.
        """
        try:
            from utils.file_acl import lock_down_file
            for _sfx in ("", "-wal", "-shm"):
                _f = Path(str(self.db_path) + _sfx)
                if _f.exists():
                    # keep_current_user=True ZORUNLU: bu DB surekli acilip yazilir; kilidi
                    # SYSTEM+Admins ile SINIRLAMAK yonetici olmayan surecte (launcher) kimlik
                    # dogrulamayi tamamen kirar. Yerel `Users` grubu yine ERISEMEZ.
                    lock_down_file(_f, keep_current_user=True)
        except Exception:
            logger.warning("auth_users.db ACL kilidi uygulanamadi (elle icacls onerilir): %s",
                           self.db_path, exc_info=True)

    def _conn(self):
        c = sqlite3.connect(str(self.db_path), check_same_thread=False, timeout=10.0)
        c.row_factory = sqlite3.Row
        try:
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("PRAGMA busy_timeout=5000")
        except Exception:
            pass
        return c

    def _init(self):
        with self._lock, self._conn() as c:
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS app_users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT UNIQUE NOT NULL,
                    pw_hash TEXT NOT NULL,
                    salt TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    @staticmethod
    def _norm(email: str) -> str:
        return (email or "").strip().lower()

    def email_exists(self, email: str) -> bool:
        """E-posta kayıtlı mı? (login'de 'kullanıcı yok' ile 'şifre yanlış'ı ayırt etmek için — klinik-yerel
        cihaz olduğundan e-posta enumeration düşük risk; net UX tercih edildi.)"""
        email = self._norm(email)
        try:
            with self._lock, self._conn() as c:
                return c.execute("SELECT 1 FROM app_users WHERE email = ?", (email,)).fetchone() is not None
        except Exception:
            logger.exception("email_exists hatası")
            return False

    def register(self, email: str, password: str):
        """(ok: bool, error: str). E-posta/şifre BİÇİM doğrulaması router'da; burada benzersizlik + saklama."""
        email = self._norm(email)
        salt = secrets.token_bytes(16)
        pw_hash = _hash_password(password, salt)
        try:
            with self._lock, self._conn() as c:
                c.execute(
                    "INSERT INTO app_users (email, pw_hash, salt) VALUES (?, ?, ?)",
                    (email, pw_hash, salt.hex()),
                )
            return (True, "")
        except sqlite3.IntegrityError:
            return (False, "Bu e-posta ile zaten bir hesap var. Giriş yapın.")
        except Exception:
            logger.exception("kullanıcı kaydı hatası")
            return (False, "Kayıt başarısız (sunucu hatası).")

    def reset_password(self, email: str, new_password: str):
        """Yönetici yetkisiyle şifre sıfırla (router yönetici-kodu + şifre-kuralını doğrular). (ok, error).
        Var-olmayan e-posta → (False, ...); enumeration burada önemsiz (yönetici-kodu zaten kanıtlandı)."""
        email = self._norm(email)
        salt = secrets.token_bytes(16)
        pw_hash = _hash_password(new_password, salt)
        try:
            with self._lock, self._conn() as c:
                cur = c.execute(
                    "UPDATE app_users SET pw_hash = ?, salt = ? WHERE email = ?",
                    (pw_hash, salt.hex(), email),
                )
                if cur.rowcount == 0:
                    return (False, "Bu e-posta ile kayıtlı bir hesap yok.")
            return (True, "")
        except Exception:
            logger.exception("şifre sıfırlama hatası")
            return (False, "Sıfırlama başarısız (sunucu hatası).")

    def verify(self, email: str, password: str) -> bool:
        email = self._norm(email)
        try:
            with self._lock, self._conn() as c:
                row = c.execute("SELECT pw_hash, salt FROM app_users WHERE email = ?", (email,)).fetchone()
        except Exception:
            logger.exception("kullanıcı doğrulama hatası")
            return False
        if not row:
            # Kullanıcı-yok ile yanlış-şifre zamanlamasını yaklaşık eşitle (enumeration'ı zorlaştır).
            _hash_password(password, secrets.token_bytes(16))
            return False
        expected = _hash_password(password, bytes.fromhex(row["salt"]))
        return hmac.compare_digest(expected, row["pw_hash"])


_auth_db = None
_auth_db_lock = threading.Lock()


def get_auth_db() -> AuthDB:
    """Süreç-genelinde tek AuthDB (çift-kontrollü kilit)."""
    global _auth_db
    if _auth_db is None:
        with _auth_db_lock:
            if _auth_db is None:
                from utils.path_utils import get_app_data_directory
                _auth_db = AuthDB(get_app_data_directory())
    return _auth_db
