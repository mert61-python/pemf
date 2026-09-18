# Author: mertaygn, cglrgrkn
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
            logger.warning(
                "auth_users.db ACL kilidi uygulanamadi (elle icacls onerilir): %s", self.db_path, exc_info=True
            )

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

            # ── CİHAZ OPERATÖRLERİ (2026-08-08) ──────────────────────────────────────────
            # NEDEN: tek makineyi 3-4 veteriner paylaşıyor ama uygulamaya TEK e-postayla
            # giriliyordu → her kayda AYNI `operator_email` yazılıyor, "Benim Hastalarım /
            # Tüm Klinik" ayrımı ANLAMSIZ kalıyordu. Veri modeli çoklu operatörü zaten
            # destekliyor; eksik olan kimlik katmanıydı.
            #
            # NEDEN AYRI TABLO: kimlik Supabase'den gelir; bu tablo yerel şifre sisteminden
            # (app_users) BAĞIMSIZ, yalnız "bu cihazda kayıtlı operatörler + hızlı geçiş PIN'i".
            #
            # NEDEN PIN: her hasta arasında Supabase e-posta+şifre yazmak pratikte kullanılmaz
            # → veterinerler tek hesabı paylaşmaya döner (özelliği boşa çıkarır). Ayrıca
            # Supabase girişi İNTERNET ister; internetsiz klinikte operatör değiştirilemezdi.
            # PIN yerel doğrulanır → ÇEVRİMDIŞI çalışır.
            #
            # ⚠️ PIN uzayı küçüktür (6 hane = 10^6). Koruma üç katmanlı: PBKDF2 200k tur,
            # dosya ACL'i (SYSTEM+Admin) ve AŞAĞIDAKİ KİLİTLENME. Kilitlenme olmadan yerel
            # kaba kuvvet dakikalar sürerdi.
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS device_operators (
                    email TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL DEFAULT '',
                    pin_hash TEXT NOT NULL,
                    pin_salt TEXT NOT NULL,
                    fail_count INTEGER NOT NULL DEFAULT 0,
                    locked_until REAL NOT NULL DEFAULT 0,
                    enrolled_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    last_active TEXT NOT NULL DEFAULT ''
                )
                """
            )

    # ── CİHAZ OPERATÖRLERİ ───────────────────────────────────────────────────────────────
    PIN_RE = re.compile(r"^\d{6}$")
    _PIN_MAX_FAIL = 5  # bu kadar hatadan sonra kilit
    _PIN_LOCK_SECONDS = 300  # 5 dk (art arda kilitlerde katlanır)

    def enroll_operator(self, email: str, display_name: str, pin: str, eski_pin: str = ""):
        """Bu cihaza operatör kaydet / PIN'ini güncelle. Dönen: (ok, hata_kodu|None).

        ÇAĞIRAN ZORUNLULUĞU: kimlik ÖNCEDEN doğrulanmış olmalı (Supabase oturumu). Bu metod
        kimlik doğrulamaz, yalnız hızlı-geçiş PIN'ini saklar.

        ⚠️ DENETİM 2026-08-09 (ENGEL) — MEVCUT KAYIT ARTIK ESKİ PIN İSTER.
        Önceki hâli `ON CONFLICT DO UPDATE SET pin_hash=..., fail_count=0, locked_until=0` idi:
        yani bu ucu çağırabilen herkes BAŞKA bir hekimin PIN'ini ezebiliyor VE kaba-kuvvet
        kilidini sıfırlayabiliyordu. İkisi birlikte, PBKDF2 200k + üstel kilitlenme korumasının
        TAMAMINI tek çağrıyla baypas ediyordu — üstelik özelliğin amacı (kaydın DOĞRU hekime
        atfedilmesi) tam olarak bunun tersiydi.
        Yeni kural: e-posta zaten kayıtlıysa ESKİ PIN doğrulanmadan güncelleme YAPILMAZ; kilitli
        bir operatörün kilidi bu yolla AÇILAMAZ (kilit süresi dolmalı).
        """
        email = self._norm(email)
        if not EMAIL_RE.match(email):
            return False, "invalid_email"
        if not self.PIN_RE.match(pin or ""):
            return False, "invalid_pin"  # 6 hane şart (klinik uzlaşısı)

        if self.operator_exists(email):
            # Mevcut kaydın sahipliği KANITLANMALI. `verify_pin` kilitlenmeyi de uygular →
            # bu yol kaba kuvvete karşı kayıt ucunu da korur.
            ok, err = self.verify_pin(email, eski_pin or "")
            if not ok:
                return False, ("locked" if err == "locked" else "wrong_old_pin")

        salt = secrets.token_bytes(16)
        try:
            with self._lock, self._conn() as c:
                c.execute(
                    """INSERT INTO device_operators (email, display_name, pin_hash, pin_salt)
                       VALUES (?, ?, ?, ?)
                       ON CONFLICT(email) DO UPDATE SET
                         display_name=excluded.display_name, pin_hash=excluded.pin_hash,
                         pin_salt=excluded.pin_salt, fail_count=0, locked_until=0""",
                    (email, (display_name or "").strip()[:80], _hash_password(pin, salt), salt.hex()),
                )
            return True, None
        except Exception:
            logger.exception("operator kaydi basarisiz")
            return False, "db_error"

    def operator_exists(self, email: str) -> bool:
        """Bu e-posta cihazda kayıtlı mı (PIN güncellemesinde eski-PIN kapısı için)."""
        try:
            with self._lock, self._conn() as c:
                return (
                    c.execute("SELECT 1 FROM device_operators WHERE email = ?", (self._norm(email),)).fetchone()
                    is not None
                )
        except Exception:
            logger.exception("operator varlik kontrolu basarisiz")
            return False

    def list_operators(self):
        """Cihazda kayıtlı operatörler — SIR İÇERMEZ (hash/salt asla dışarı verilmez)."""
        try:
            with self._lock, self._conn() as c:
                rows = c.execute(
                    "SELECT email, display_name, enrolled_at, last_active, locked_until "
                    "FROM device_operators ORDER BY last_active DESC, email ASC"
                ).fetchall()
            import time as _t

            simdi = _t.time()
            return [
                {
                    "email": r["email"],
                    "display_name": r["display_name"],
                    "enrolled_at": r["enrolled_at"],
                    "last_active": r["last_active"],
                    "locked": float(r["locked_until"] or 0) > simdi,
                }
                for r in rows
            ]
        except Exception:
            logger.exception("operator listesi okunamadi")
            return []

    def verify_pin(self, email: str, pin: str):
        """PIN doğrula. Dönen: (ok, hata_kodu|None). Hatalarda kilitlenme uygulanır."""
        import time as _t

        email = self._norm(email)
        try:
            with self._lock, self._conn() as c:
                row = c.execute(
                    "SELECT pin_hash, pin_salt, fail_count, locked_until FROM device_operators WHERE email = ?",
                    (email,),
                ).fetchone()
                if not row:
                    # Zamanlamayı yaklaşık eşitle (operatör-enumeration'ı zorlaştır).
                    _hash_password(pin, secrets.token_bytes(16))
                    return False, "no_operator"
                simdi = _t.time()
                kilit = float(row["locked_until"] or 0)
                if kilit > simdi:
                    return False, "locked"
                ok = hmac.compare_digest(_hash_password(pin, bytes.fromhex(row["pin_salt"])), row["pin_hash"])
                if ok:
                    c.execute(
                        "UPDATE device_operators SET fail_count=0, locked_until=0, "
                        "last_active=datetime('now') WHERE email=?",
                        (email,),
                    )
                    return True, None
                # ⚠️ KİLİTLENME: 6 haneli PIN'in tek gerçek koruması. Art arda kilitlerde süre
                # katlanır → yerel kaba kuvvet pratik olmaktan çıkar.
                n = int(row["fail_count"] or 0) + 1
                yeni_kilit = 0.0
                if n >= self._PIN_MAX_FAIL:
                    kat = 2 ** min(n - self._PIN_MAX_FAIL, 5)
                    yeni_kilit = simdi + self._PIN_LOCK_SECONDS * kat
                c.execute(
                    "UPDATE device_operators SET fail_count=?, locked_until=? WHERE email=?", (n, yeni_kilit, email)
                )
                return False, ("locked" if yeni_kilit else "bad_pin")
        except Exception:
            logger.exception("PIN dogrulama hatasi")
            return False, "db_error"

    def remove_operator(self, email: str) -> bool:
        """Operatörü bu cihazdan çıkar (kayıtları ETKİLEMEZ — tıbbi kayıt korunur)."""
        try:
            with self._lock, self._conn() as c:
                cur = c.execute("DELETE FROM device_operators WHERE email = ?", (self._norm(email),))
                return cur.rowcount > 0
        except Exception:
            logger.exception("operator silinemedi")
            return False

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
