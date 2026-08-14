# Author: mertaygn, cglrgrkn
"""
Tedavi Geçmişi Veritabanı Modülü
PEMF tedavi seanslarının kaydedilmesi ve yönetimi için SQLite veritabanı
"""

import hashlib
import json
import logging
import os
import shutil
import sqlite3
import threading
import uuid
import weakref
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

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

# Anahtar-uyusmazliginda karantina (tuglalasma korumasi) — hasta DB'siyle TEK KAYNAK.
from database.sqlcipher_util import anahtar_uyusmazligi_mi, karantinaya_al  # noqa: E402

# `_DB_ERROR` ZATEN bir demet olabilir; `except (_DB_ERROR, RuntimeError)` ic-ice demet uretir ve
# Python "catching classes that do not inherit from BaseException" der. Duzlestirilmis hali:
_DB_VEYA_RUNTIME = (*_DB_ERROR, RuntimeError) if isinstance(_DB_ERROR, tuple) else (_DB_ERROR, RuntimeError)


class TreatmentHistoryDB:
    """PEMF tedavi geçmişi veritabanı yönetim sınıfı (Connection Pool + WAL mode)"""

    TARGET_SCHEMA_VERSION = 3
    MIN_FREE_DISK_MB = 500

    # ── Bağlantı havuzu sınırı ────────────────────────────────────────────────
    # Ana-thread-dışı bağlantılar artık context sonunda KAPATILMIYOR (aşağıdaki
    # _get_connection'a bakın): SQLCipher'da her açılış tam PRAGMA key PBKDF2'si
    # demek (ölçüm: 86 ms/bağlantı; sorgunun kendisi 0,025 ms → maliyetin %99,5'i
    # anahtar türetme). DB'ye dokunan thread'lerin hepsi uzun-ömürlü daemon
    # döngüleri ya da anyio'nun SINIRLI + yeniden-kullanılan havuz thread'leri
    # olduğundan bağlantı sayısı doğal olarak küçük kalır; bu tavan yine de bir
    # emniyet valfi: aşılırsa fazlalık bağlantılar ESKİ davranışa (context sonunda
    # kapat) düşer — yavaş ama doğru. 24 × ~2 MB sayfa önbelleği ≈ 48 MB tavan.
    MAX_POOLED_CONNECTIONS = 24

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

        # ── Havuz defteri ─────────────────────────────────────────────────────
        # _conn_generation: DB DOSYASI altımızdan değiştiğinde (migration rollback,
        # yedekten geri yükleme, re-key) artar. Bir thread'in sakladığı bağlantı
        # eski kuşaktansa bir sonraki kullanımda kapatılıp yeniden açılır → bayat
        # dosya tanıtıcısıyla çalışma imkânsız. Havuzun TEK gerçek riski buydu.
        # _live_conns: ident -> (thread'e weakref, conn). Ölmüş thread'lerin
        # bağlantıları burada takılı kalmasın diye her yaratımda budanır
        # (threading.local zaten bırakır ama defter güçlü referans tutar).
        self._conn_generation = 0
        self._live_conns = {}
        self._pool_lock = threading.Lock()

        # SQLCipher anahtarı yapılandırılmışsa ve mevcut DB düz-metinse → şifreliye MIGRATE et.
        self._migrate_to_encrypted_if_needed()

        # Veritabanını başlat
        self._init_database()
        self._run_startup_migrations_with_rollback()
        # ⚠️ 0 = YAŞ FİLTRESİ YOK. Burası AÇILIŞ yoludur; açılışta bu cihazın hiçbir seansı
        # canlı olamaz. Eski 12 saatlik eşik yüzünden çökmeden kalan seanslar `active` kalıyor
        # ve uygulanan doz hiç yazılmıyordu (kampanya bulgusu S01).
        self.recover_stale_active_sessions(max_age_hours=0)
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
        """SQLCipher BİRİNCİL anahtarı — D-3 fix: patient_database ile TEK paylaşımlı yol
        (sqlcipher_util.get_sqlcipher_key → SecretsManager-öncelikli). Eskiden bu metod
        SecretsManager'ı ATLIYORDU (keyring→env→file→YENİ-üret) → taze şifreli kurulumda patient DB
        önce init olursa SecretsManager K üretir, treatment DB SONRA K' üretirdi = ÇİFT ANAHTAR
        (treatment DB latent OKUNAMAZ hale gelirdi). Artık ikisi de aynı kaynak → yeni DB birleşik;
        üretim de TEK yerde (çift-üretim divergence'ı kökten biter). Mevcut şifreli DB: shared yol
        keyring/env/file'ı zaten migrate ettiğinden AYNI anahtarı döndürür → sorunsuz açılır."""
        try:
            from database.sqlcipher_util import get_sqlcipher_key

            return get_sqlcipher_key(self.app_data_dir, self.logger)
        except Exception as e:
            self.logger.warning(f"paylasimli sqlcipher_key alinamadi, legacy yola dusuluyor: {e}")
            return self._get_sqlcipher_key_legacy()

    def _get_sqlcipher_key_legacy(self) -> str:
        """ESKİ anahtar yolu (keyring → env → .sqlcipher_key), ÜRETMEDEN (yoksa ''). D-3: divergence
        yaşamış ESKİ kurulumda treatment DB bu anahtarla şifrelenmiş olabilir → _connect FALLBACK
        adayı (veri-kaybı önlenir). Üretim BİLEREK yok: yeni anahtar YALNIZ paylaşımlı yolda üretilir."""
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
        return ""

    def _connect_sqlcipher_if_configured(self):
        """SQLCipher anahtarı varsa bağlantı dener, yoksa None. D-3 fix: BİRDEN ÇOK aday anahtar
        dener — [birincil(paylaşımlı/SecretsManager), legacy(keyring/file)] — ilk AÇAN bağlantıyı
        döner. Böylece divergence yaşamış eski treatment DB legacy anahtarıyla GÜVENLE açılır
        (veri-kaybı yok); yeni/mevcut-birleşik DB birincil ile açılır. Hiçbiri açmazsa None (düz-metin)."""
        # DENETIM P2 (cagri-basi sir arama): ana-thread DISINDAKI her DB cagrisi yeni baglanti
        # aciyor (FastAPI senkron uclari, asyncio.to_thread, tum arka-plan thread'leri) ve her
        # baglantida SecretsManager + keyring YENIDEN okunuyordu — keyring cagrisi Windows'ta
        # RPC'dir. Calisan anahtari ornekte cache'le: sonraki baglantilar sir aramasini ATLAR.
        # KAPSAM NOTU: PRAGMA key'in PBKDF2 maliyeti baglanti basina KALIR — onu kaldirmak
        # baglanti HAVUZU ister; havuz, her hasta/seans yazisinin gectigi cekirdek yoldur ve
        # thread-safety/WAL/kilit semantigini degistirir → donanim-uzeri dogrulama olmadan
        # BILEREK yapilmadi (bkz. denetim raporu per-call-sqlcipher-connect).
        _cached = getattr(self, "_cipher_key_cache", None)
        if _cached:
            candidates = [("cache", _cached)]
        else:
            primary = self._get_sqlcipher_key()
            legacy = self._get_sqlcipher_key_legacy()
            # Aday sıra: birincil ÖNCE (birleştirme), sonra farklıysa legacy (kurtarma). Boş/yinelenen atlanır.
            candidates = []
            if primary:
                candidates.append(("birincil", primary))
            if legacy and legacy != primary:
                candidates.append(("legacy", legacy))
        if not candidates:
            return None

        sqlcipher = self._import_sqlcipher()
        if sqlcipher is None:
            self.logger.warning("SQLCipher anahtari var ama binding (sqlcipher3) kurulu DEGIL → duz-metin fallback.")
            return None
        last_err = None
        for label, cipher_key in candidates:
            conn = None
            try:
                conn = sqlcipher.connect(str(self.db_path), check_same_thread=False, timeout=10.0)
                conn.row_factory = getattr(sqlcipher, "Row", sqlite3.Row)  # sqlcipher3 cursor uyumlu Row
                escaped_key = cipher_key.replace("'", "''")
                conn.execute(f"PRAGMA key='{escaped_key}'")
                conn.execute('SELECT count(*) FROM sqlite_master')
                if label == "legacy":
                    self.logger.warning(
                        "treatment DB LEGACY anahtarla acildi (D-3 anahtar-divergence "
                        "tespit + KURTARILDI). Birlestirme icin ileride re-key onerilir."
                    )
                self._cipher_key_cache = cipher_key  # CALISAN anahtari hatirla (sir aramasini atla)
                return conn
            except Exception as e:
                last_err = e
                if label == "cache":
                    # Cache'lenmis anahtar artik ACMIYOR (re-key / anahtar degisimi) → cache'i
                    # bosalt ve TAM cozumleme ile bir kez daha dene (kurtarma yolu korunur).
                    self._cipher_key_cache = None
                    self.logger.info("Cache'li SQLCipher anahtari acmadi → tam anahtar cozumlemesi yeniden denenecek.")
                    if conn is not None:
                        try:
                            conn.close()
                        except Exception:
                            pass
                    return self._connect_sqlcipher_if_configured()
                if conn is not None:
                    try:
                        conn.close()
                    except Exception:
                        pass
                continue
        self.logger.warning(f"SQLCipher hicbir aday anahtarla acilamadi (yanlis anahtar/migrate?): {last_err}")
        # TUGLALASMA KORUMASI (2026-08-11): "anahtar VARDI ama dosyayi ACMADI"yi, "anahtar/binding
        # HIC YOKTU"dan ayirt edilebilir kil. Karantina YALNIZ birincisinde yapilir — ikincisinde
        # sorun gecici olabilir ve dosyayi kenara almak KURTARILABILIR hasta verisini yetim birakir.
        self._anahtar_vardi_ama_acmadi = bool(last_err) and anahtar_uyusmazligi_mi(last_err)
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
            # op-doğrulama #8: .plain.bak = tüm eski düz-metin PII → SQLCipher'ı baypas eder. Escrow
            # için tutulur ama SIKI ACL (SYSTEM+Admin) ile kilitlenir (B-1.2 escrow deseniyle tutarlı).
            # DENETIM P2: ACL BASARISIZ olursa eskiden yalnizca UYARI loglaniyor ve TUM hasta
            # PII'sinin duz-metin tam kopyasi korumasiz diskte KALIYORDU — SQLCipher'i tamamen
            # baypas eden bir dosya. Escrow degerlidir ama korumasiz escrow, sifrelemenin kendisini
            # anlamsiz kilar. FAIL-CLOSED: kilitlenemiyorsa SIL (sifreli DB zaten yerinde).
            # PEMF_KEEP_PLAIN_BAK=0 ile escrow tamamen kapatilabilir (kilit basarili olsa bile silinir).
            # ⚠️ DENETİM 2026-08-08 — VARSAYILAN TERSİNE ÇEVRİLDİ (escrow-sakla → güvenli-sil).
            # `sqlcipher_util.py` (HASTA DB'si) bu kararı Audit P3'te zaten almıştı: ".plain.bak
            # TÜM düz-metin PII'yi (SQLCipher-bypass) taşır → disk çalınırsa / yedek / bulut-sync
            # okursa at-rest garantisi ÇÖKER" → orada varsayılan GÜVENLİ-SİL. Aynı düzeltme
            # BURAYA, tedavi + AI geçmişi DB'sine hiç uygulanmamıştı: aynı hassasiyetteki veri,
            # ZIT varsayılan. Launcher artık at-rest şifrelemeyi açtığı için bu tutarsızlık
            # sahadaki HER klinikte tüm geçmişin düz-metin tam kopyasını diskte bırakırdı —
            # üstelik sitede "cihazda şifreli" beyanı varken. ACL yalnız yerel kullanıcıya karşı
            # korur; disk çalınmasına/imajlanmasına karşı HİÇBİR şey yapmaz ve at-rest
            # şifrelemenin asıl tehdit modeli tam olarak odur.
            # ESCROW İSTEYEN: PEMF_KEEP_PLAIN_BAK=1 (eski davranış; ACL kilitlenebilirse saklar).
            # ⚠️ Anahtar kaybı = geçmiş kaybı. Yedek yolu artık Ayarlar → "Veri Taşıma"
            # (parola korumalı şifreli dışa aktarma) ve SecretsManager kurtarma kodudur.
            _keep = os.getenv("PEMF_KEEP_PLAIN_BAK", "0") == "1"
            if _keep:
                _locked = False
                try:
                    from utils.file_acl import lock_down_file

                    _locked = bool(lock_down_file(backup))
                except Exception:
                    self.logger.warning(".plain.bak ACL kilidi hata verdi: %s", backup, exc_info=True)
                if _locked:
                    self.logger.warning(
                        "Tedavi DB plaintext -> SQLCipher MIGRATE edildi. Duz-metin yedek ESCROW "
                        "saklandi (ACL-kilitli): %s",
                        backup,
                    )
                    return
                # Kilitlenemedi → korumasız escrow şifrelemenin kendisini anlamsız kılar → SİL.
                self.logger.warning("ACL uygulanamadi → escrow'dan vazgecildi, guvenli-siliniyor.")
            # GÜVENLİ SİL: yalnız `unlink` içeriği diskte bırakır (dosya kurtarma araçlarıyla geri
            # gelir). Üzerine rastgele veri yaz + fsync, sonra sil — hasta DB yolundaki desenin aynısı.
            try:
                _bsz = os.path.getsize(backup)
                with open(backup, "r+b") as _bf:
                    _rem = _bsz
                    _rnd = os.urandom(1 << 20)
                    while _rem > 0:
                        _bf.write(_rnd if _rem >= len(_rnd) else _rnd[:_rem])
                        _rem -= len(_rnd)
                    _bf.flush()
                    os.fsync(_bf.fileno())
                os.remove(backup)
                self.logger.warning(
                    "Tedavi DB plaintext -> SQLCipher MIGRATE edildi; duz-metin yedek "
                    "GUVENLI-SILINDI (at-rest PII riski kapatildi)."
                )
            except Exception:
                self.logger.error(
                    "KRITIK: korumasiz duz-metin yedek SILINEMEDI → ELLE SILIN: %s", backup, exc_info=True
                )
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
            # P0 (KVKK): şifreleme AÇIKÇA istendiyse (PEMF_ENCRYPT_AT_REST=1) ama sağlanamıyorsa
            # (sqlcipher3 binding yok / anahtar açılamadı) hasta PII'sini DÜZ-METİN yazmaktansa
            # HARD FAIL et. Aksi halde "şifreli sanıp cleartext PII yazma" sessiz veri sızıntısı olur.
            # Üretimde sqlcipher3 EXE'ye bundle'lı → şifre bağlantısı açılır, buraya DÜŞMEZ.
            if os.getenv("PEMF_ENCRYPT_AT_REST", "0") == "1":
                raise RuntimeError(
                    "PEMF_ENCRYPT_AT_REST=1 ama SQLCipher sağlanamadı (sqlcipher3 binding yok veya "
                    "anahtar açılamadı) → hasta PII'sini düz-metin yazmamak için tedavi DB'si AÇILMADI. "
                    "sqlcipher3'ü kurun ve .sqlcipher_key/keyring anahtarını doğrulayın."
                )
            if not getattr(self, "_encryption_warned", False):
                self._encryption_warned = True
                self.logger.warning(
                    "AT-REST SIFRELEME KAPALI: tedavi gecmisi DUZ-METIN SQLite olarak yaziliyor. "
                    "B-1.3 KORUMASI: kisi-tanimlayici PII (hasta/sahip/operator adi, e-posta, notlar) "
                    "'%s' ile MASKELENIR (sifresiz DB'ye gercek PII yazilmaz). Uretimde pysqlcipher3 "
                    "kurun + PEMF_ENCRYPT_AT_REST=1 → gercek degerler yazilir. (health: at_rest_encrypted=false)",
                    self._PII_REDACTION,
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
            raise RuntimeError(f"Disk free space critical: {status.get('free_mb')}MB < {status.get('threshold_mb')}MB")

    def _prune_dead_pool_entries(self):
        """Ölmüş thread'lere ait bağlantıları defterden düşür ve kapat.

        threading.local, thread ölünce kendi sözlüğünü bırakır; ama _live_conns
        güçlü referans tuttuğu için bağlantı (ve dosya tanıtıcısı) GC olamazdı.
        Yalnız yeni bağlantı yaratılırken çağrılır → sıcak yolda maliyeti yok.
        """
        dead = []
        for ident, (thr_ref, conn) in list(self._live_conns.items()):
            thr = thr_ref()
            if thr is None or not thr.is_alive():
                dead.append(ident)
                try:
                    conn.close()
                except Exception:
                    pass
        for ident in dead:
            self._live_conns.pop(ident, None)

    @contextmanager
    def _get_connection(self):
        """
        Thread-safe bağlantı havuzu. Her thread kendi bağlantısını kullanır.

        DENETİM (per-call-sqlcipher-connect): eskiden ana-thread-DIŞI her context
        yeni bağlantı açıp kapatıyordu → SQLCipher'da her seferinde tam PBKDF2
        (ölçüm: 86,49 ms/çağrı; yeniden kullanımda 0,025 ms). Bağlantı artık
        thread'de KALIYOR. Ana thread bunu ilk günden beri zaten böyle yapıyordu;
        yeni olan tek şey aynı davranışın worker thread'lere de uygulanması.
        Üç koruma eklendi:
          1) Kuşak kontrolü — DB dosyası değiştiyse bayat bağlantı yeniden açılır.
          2) MAX_POOLED_CONNECTIONS tavanı — aşılırsa eski (aç-kapa) davranışa düş.
          3) Açık-kalmış işlem denetimi — commit'i unutulmuş bir yazma işlemi
             eskiden close() ile düşerdi; havuzda kalsa RESERVED kilidini tutup
             TÜM yazarları bloke ederdi. Context çıkışında rollback + uyarı.
        """
        ephemeral = False
        gen = self._conn_generation

        conn = getattr(self._local, 'conn', None)

        # (1) Kuşak eskimiş mi? (migration rollback / restore / re-key sonrası)
        if conn is not None and getattr(self._local, 'conn_gen', None) != gen:
            try:
                conn.close()
            except Exception:
                pass
            with self._pool_lock:
                self._live_conns.pop(threading.get_ident(), None)
            self._local.conn = conn = None

        if conn is None:
            conn = self._create_connection()
            cur = threading.current_thread()
            with self._pool_lock:
                self._prune_dead_pool_entries()
                # (2) Tavan aşıldıysa bu bağlantı GEÇİCİ: eski davranış (yavaş ama doğru).
                if len(self._live_conns) >= self.MAX_POOLED_CONNECTIONS and cur is not threading.main_thread():
                    ephemeral = True
                else:
                    self._live_conns[threading.get_ident()] = (weakref.ref(cur), conn)
            if not ephemeral:
                self._local.conn = conn
                self._local.conn_gen = gen

        try:
            yield conn
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            raise
        finally:
            if ephemeral:
                try:
                    conn.close()
                except Exception:
                    pass
            else:
                # (3) Açık kalmış işlem havuzda kilit tutar → geri al ve haber ver.
                try:
                    if conn.in_transaction:
                        conn.rollback()
                        self.logger.warning(
                            "DB baglantisi commit edilmemis islemle birakildi → rollback yapildi "
                            "(cagiran kod commit'i atliyor)."
                        )
                except Exception:
                    pass

    def _invalidate_connections(self, reason: str = ""):
        """DB dosyası altımızdan değişti → tüm havuz bağlantılarını geçersiz kıl.

        Kuşak ÖNCE artırılır: yarışan bir thread bu andan sonra taze bağlantı alır.
        Ardından defterdeki bağlantılar kapatılır (migration rollback / kapanış gibi
        tek-thread'li anlarda çağrılır; yine de her kapatma tek tek korunur).
        """
        with self._pool_lock:
            self._conn_generation += 1
            entries = list(self._live_conns.items())
            self._live_conns.clear()
        for _ident, (_ref, conn) in entries:
            try:
                conn.close()
            except Exception:
                pass
        if getattr(self._local, 'conn', None) is not None:
            try:
                self._local.conn.close()
            except Exception:
                pass
            self._local.conn = None
        if reason:
            self.logger.info("DB baglanti havuzu gecersiz kilindi (%s), kusak=%d", reason, self._conn_generation)

    def close_connections(self):
        """TÜM havuz bağlantılarını kapat (kapanışta / DB dosyası değişmeden önce).

        DENETİM: eskiden YALNIZ çağıran thread'in bağlantısını kapatıyordu; migration
        rollback burayı çağırıp hemen ardından db dosyasını siliyordu → diğer
        thread'lerin tanıtıcıları açık kalıyordu. Artık defterdeki hepsi kapanır ve
        kuşak artar (geri dönen thread taze bağlantı açar).
        """
        try:
            self._invalidate_connections("close_connections")
        except Exception as e:
            self.logger.error(f"Error closing connection: {e}")

    def is_ready(self) -> tuple:
        """Tıbbi kayıt yazılabilir durumda mı → (hazir: bool, sebep: str).

        ⚠️ DENETİM 2026-08-09 (ENGEL) — TIBBİ KAYIT KAYBI.
        Seans başlatma yolu DB hatalarını "best-effort" sayıp YUTUYORDU: DB açılamazsa
        `db_session_id=None` ile devam ediliyor, bobinler enerjileniyor ve tedavi
        UYGULANIYOR — ama hastanın aldığı doz HİÇBİR YERE yazılmıyordu. Operatör bunu
        fark etmiyordu; sonradan "bu hayvana ne verildi?" sorusunun cevabı YOK.
        Kayıtsız tedavi, tıbbi cihazda kabul edilemez: geriye dönük doz takibi, yan etki
        soruşturması ve yasal saklama yükümlülüğü tamamen bu kayda dayanır.

        KAPSAM (dürüstlük notu): bu sağlama "bağlantı açılıyor ve şema okunabiliyor" der.
        Yanlış SQLCipher anahtarı, bozuk sayfa, silinmiş/erişilemez dosya BURADA yakalanır.
        Dolu disk / salt-okunur birim gibi YAZMA-anı hatalarını yakalamaz (onlar yazarken
        patlar ve zaten loglanır) — bu yüzden `SELECT 1` ötesine geçip sahte bir yazma
        denemesi YAPILMAZ: gerçek kaydı kirletmeden yazılabilirliği kanıtlamanın ucuz bir
        yolu yok ve yanlış-negatif üretmek tedaviyi gereksiz yere engellerdi.
        """
        try:
            with self._get_connection() as conn:
                conn.execute("SELECT count(*) FROM sqlite_master").fetchone()
            return True, ""
        except Exception as e:
            self.logger.error("Tibbi kayit DB'si HAZIR DEGIL: %s", e, exc_info=True)
            return False, str(e)[:200]

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

    def _init_database(self):
        """Veritabanı tablolarını oluştur (HIGH FIX: WAL mode enabled).

        ⚠️ ANAHTAR UYUŞMAZLIĞINDA CİHAZ TUĞLALAŞMAZ (saha hatası 2026-08-11) — hasta DB'siyle
        AYNI gerekçe ve AYNI kural: kaldır-yeniden-kur sonrası at-rest anahtarı yenilenmişse
        dosya kenara alınır (SİLİNMEZ) ve temiz bir DB açılır. Bkz. sqlcipher_util.karantinaya_al
        ve database/patient_database._init_database."""
        self._anahtar_vardi_ama_acmadi = False
        try:
            with self._get_connection() as conn:
                self._semayi_kur(conn)
                self.logger.info(f"Veritabanı başarıyla başlatıldı: {self.db_path}")
            return
        except _DB_VEYA_RUNTIME as e:
            # ⚠️ İSTİSNA TİPİ İKİ TÜRLÜ GELİR — ikisini de karşılamak ZORUNLU:
            #   (a) `_DB_ERROR`  — bağlantı açıldı, sonraki bir sorgu patladı;
            #   (b) `RuntimeError` — `_create_connection`, aday anahtarların HİÇBİRİ açmayınca
            #       "PEMF_ENCRYPT_AT_REST=1 ama SQLCipher sağlanamadı" diye fırlatır. SAHADA GELEN
            #       BUDUR (2026-08-11); yalnız (a) yakalansaydı bu düzeltme hiç çalışmazdı.
            uyusmazlik = getattr(self, "_anahtar_vardi_ama_acmadi", False) or (
                getattr(self, "_cipher_key_cache", None) and anahtar_uyusmazligi_mi(e)
            )
            if not uyusmazlik:
                self.logger.error(f"Veritabanı başlatma hatası: {e}")
                raise
            self.logger.error("Tedavi gecmisi DB'si at-rest anahtariyla ACILAMADI (%s) → karantina.", e)

        self._baglantiyi_birak()
        if karantinaya_al(self.db_path, self.logger) is None:
            raise RuntimeError("Tedavi gecmisi veritabani acilamadi ve karantinaya ALINAMADI (dosya kilitli olabilir).")
        with self._get_connection() as conn:
            self._semayi_kur(conn)
            self.logger.info(f"Veritabanı karantina sonrasi yeniden olusturuldu: {self.db_path}")

    def _baglantiyi_birak(self) -> None:
        """Bu thread'in bağlantısını kapat + HAVUZDAN da düşür — karantina öncesi dosya kilidi
        kalmasın (Windows'ta açık SQLCipher tutamacı `shutil.move`'u PermissionError'a düşürür).

        ⚠️ `self._local.conn`i sıfırlamak YETMEZ: `_live_conns` havuzu aynı bağlantıya ayrı bir
        referans tutar ve o referans dosyayı açık tutmaya devam eder."""
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
        self._local.conn = None
        with self._pool_lock:
            self._live_conns.pop(threading.get_ident(), None)

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

    # ═══════════════════════════════════════════════════════════════════════════════════════
    # DENETİM İZİ (2026-08-09 denetimi, Tier 3)
    # ───────────────────────────────────────────────────────────────────────────────────────
    # ARIZA: geri dönüşsüz işlemlerin (toplu silme, dışa/içe aktarma, operatör ekleme-çıkarma,
    # PII redaksiyonu) tek izi 60 MB'lık DÖNEN bir metin log'unda, kimliksiz tek bir satırdı.
    # Yani: "hasta kayıtlarım kayboldu" denildiğinde kimin, ne zaman, nereden, kaç kaydı
    # sildiğini gösterecek hiçbir şey yoktu — üstelik log dönünce o satır da yok oluyordu.
    #
    # TASARIM:
    #  • Tablo ŞİFRELİ DB'nin içinde (SQLCipher) — ayrı bir düz-metin dosya değil.
    #  • EKLEME-ONLY: kod yolunda UPDATE/DELETE YOK; tetikleyicilerle veritabanı seviyesinde de
    #    engellenir (bir SQL istemcisiyle bağlanan biri geçmişi sessizce düzeltemesin).
    #  • Saklama politikası bu tabloya DOKUNMAZ ve "hepsini sil" onu SİLMEZ: silme kaydının
    #    kendisi silinirse denetim izinin anlamı kalmaz.
    # ═══════════════════════════════════════════════════════════════════════════════════════

    def _create_audit_table(self, cursor):
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS audit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts_utc TEXT NOT NULL,
                event_type TEXT NOT NULL,
                operator_email TEXT,
                client_ip TEXT,
                scope TEXT,
                item_count INTEGER,
                outcome TEXT,
                detail TEXT,
                app_version TEXT,
                build_id TEXT
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_events(ts_utc)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_audit_type ON audit_events(event_type, ts_utc)')
        # EKLEME-ONLY mühür: SQLite tetikleyicileri. Uygulama kodu zaten UPDATE/DELETE yapmıyor;
        # bu, DB dosyasına doğrudan erişen birine karşı ikinci kapı.
        cursor.execute('''
            CREATE TRIGGER IF NOT EXISTS audit_events_no_update
            BEFORE UPDATE ON audit_events
            BEGIN SELECT RAISE(ABORT, 'denetim izi degistirilemez (ekleme-only)'); END
        ''')
        cursor.execute('''
            CREATE TRIGGER IF NOT EXISTS audit_events_no_delete
            BEFORE DELETE ON audit_events
            BEGIN SELECT RAISE(ABORT, 'denetim izi silinemez (ekleme-only)'); END
        ''')

    def denetim_yaz(
        self,
        event_type: str,
        *,
        operator_email: str = "",
        client_ip: str = "",
        scope: str = "",
        item_count=None,
        outcome: str = "ok",
        detail=None,
    ) -> bool:
        """Denetim olayını yaz. **ASLA istisna atmaz** ve çağıranın işlemini bozmaz.

        ⚠️ Bilinçli tasarım: denetim yazımı bir silme/dışa-aktarma işlemini ENGELLEMEZ. Aksi
        hâlde dolu bir diskte veteriner hiçbir şey yapamaz hâle gelirdi. Ama yazamama sessiz
        de kalmaz — log'a ERROR düşer ve `outcome` alanı çağıranın sonucunu taşır.
        """
        import datetime as _dt
        import json as _json

        try:
            from utils.path_utils import get_app_version, get_build_id

            surum, yapi = get_app_version(), get_build_id()
        except Exception:
            surum, yapi = "", ""
        try:
            ayrinti = _json.dumps(detail, ensure_ascii=False)[:4000] if detail is not None else None
        except Exception:
            ayrinti = None
        try:
            with self._lock:
                with self._get_connection() as conn:
                    conn.execute(
                        "INSERT INTO audit_events (ts_utc, event_type, operator_email, client_ip, "
                        "scope, item_count, outcome, detail, app_version, build_id) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (
                            _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
                            str(event_type)[:64],
                            (operator_email or "")[:200],
                            (client_ip or "")[:64],
                            (scope or "")[:200],
                            int(item_count) if item_count is not None else None,
                            (outcome or "")[:32],
                            ayrinti,
                            surum,
                            yapi,
                        ),
                    )
                    conn.commit()
            return True
        except Exception as e:
            self.logger.error("DENETIM IZI YAZILAMADI (%s): %s", event_type, e)
            return False

    def denetim_oku(self, limit: int = 200, event_type: str = "") -> list:
        """Son denetim olayları (en yeni önce). Salt-okuma."""
        try:
            with self._lock:
                with self._get_connection() as conn:
                    conn.row_factory = lambda c, r: {d[0]: r[i] for i, d in enumerate(c.description)}
                    sorgu = (
                        "SELECT * FROM audit_events "
                        + ("WHERE event_type = ? " if event_type else "")
                        + "ORDER BY id DESC LIMIT ?"
                    )
                    par = (event_type, int(limit)) if event_type else (int(limit),)
                    return [dict(r) for r in conn.execute(sorgu, par).fetchall()]
        except Exception as e:
            self.logger.error("Denetim izi okunamadi: %s", e)
            return []

    def denetim_sayisi(self) -> int:
        try:
            with self._lock:
                with self._get_connection() as conn:
                    return int(conn.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0])
        except Exception:
            return 0

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

    def _get_system_setting(self, key: str) -> Optional[str]:
        """System setting değeri oku."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT setting_value FROM system_settings WHERE setting_key = ?', (key,))
                row = cursor.fetchone()
                return str(row['setting_value']) if row else None
        except Exception:
            return None

    def _set_system_setting(self, key: str, value: str, description: str = ''):
        """System setting değeri upsert et."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                '''
                INSERT INTO system_settings (setting_key, setting_value, description, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(setting_key) DO UPDATE SET
                    setting_value = excluded.setting_value,
                    description = excluded.description,
                    updated_at = CURRENT_TIMESTAMP
            ''',
                (key, value, description),
            )
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
                        _side = self.db_path + _sfx
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

    def _seansin_son_kaniti(self, cursor, session_id: int, baslangic_epoch: float):
        """Seansın DİSKTE İZ BIRAKAN son anı (epoch) — yoksa None.

        ⚠️ Bitişi `datetime.now()` yazmak YANLIŞ TIBBİ KAYIT üretir: cihaz günlerce kapalı
        kalmış olabilir ve kayıt "3 gün süren tedavi" der. Yanlış kayıt, eksik kayıttan daha
        kötüdür — denetimde gerçek sanılır. Bu yüzden bitiş KANITTAN türetilir: son bobin
        çalışması ve son sensör örneği (ikisinin en büyüğü).
        """
        en_son = None
        for sorgu, parametre in (
            (
                "SELECT MAX(COALESCE(ended_epoch, started_epoch)) FROM session_coil_runs WHERE session_id = ?",
                (session_id,),
            ),
            ("SELECT MAX(sample_ts) FROM sensor_samples WHERE session_id = ?", (session_id,)),
        ):
            try:
                deger = cursor.execute(sorgu, parametre).fetchone()[0]
            except Exception:
                deger = None  # tablo/sütun yoksa (eski şema) kanıt aramayı BOZMA
            if deger is not None and (en_son is None or float(deger) > en_son):
                en_son = float(deger)
        # Kanıt seans başlangıcından ÖNCEYSE güvenilmez (saat değişimi / bozuk satır).
        if en_son is not None and en_son < baslangic_epoch:
            return None
        return en_son

    def recover_stale_active_sessions(self, max_age_hours: int = 12) -> int:
        """Açık kalmış `active` seansları güvenli şekilde kapat (recovery).

        `max_age_hours <= 0` → YAŞ FİLTRESİ YOK, tüm `active` seanslar kapatılır.

        ⚠️ AÇILIŞTA YAŞ FİLTRESİ UYGULANMAZ (kampanya bulgusu S01, 2026-08-14). Bu metodun
        TEK çağrıldığı yer `__init__`, yani BACKEND AÇILIŞIDIR; açılışta bu cihazın hiçbir
        seansı canlı olamaz — süreç yeni başlamıştır. Eski 12 saatlik eşik, çalıştığı tek
        bağlamda hiçbir şey korumuyor, yalnızca kaydı belirsiz bırakıyordu: seans sürerken
        çöken bir cihaz yeniden açıldığında kayıt `active` / `end_time=NULL` /
        `duration_minutes=NULL` kalıyor, üstelik bobin çalışmaları da kapanmıyordu →
        **hastaya uygulanan doz hiç yazılmıyordu.**
        """
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
                yas_filtresi = int(max_age_hours) > 0
                threshold = now - timedelta(hours=max(1, int(max_age_hours))) if yas_filtresi else None

                for row in rows:
                    session_id = int(row['id'])
                    session_date = str(row['session_date'])
                    start_time = str(row['start_time'])

                    try:
                        started_at = datetime.strptime(f"{session_date} {start_time}", '%Y-%m-%d %H:%M:%S')
                    except ValueError:
                        # Parse edilemeyen kaydı da recovery et
                        started_at = now - timedelta(hours=abs(int(max_age_hours)) + 1)

                    if yas_filtresi and started_at > threshold:
                        continue

                    # Bitiş: KANITTAN (bkz. `_seansin_son_kaniti`); kanıt yoksa başlangıç.
                    baslangic_epoch = started_at.timestamp()
                    son_kanit = self._seansin_son_kaniti(cursor, session_id, baslangic_epoch)
                    bitis_epoch = son_kanit if son_kanit is not None else baslangic_epoch
                    bitis_dt = datetime.fromtimestamp(bitis_epoch)
                    duration_minutes = max(0, int((bitis_epoch - baslangic_epoch) / 60))

                    # ⚠️ DOZ KAYDI seans satırında DEĞİL, bobin çalışmalarında durur. Seansı
                    # kapatıp bunları açık bırakmak "hangi bobin ne kadar sürdü"yü cevapsız
                    # bırakır — kaydın tıbbi değeri kalmaz.
                    try:
                        cursor.execute(
                            '''
                            UPDATE session_coil_runs
                            SET ended_epoch = ?,
                                duration_seconds = MAX(0, ? - started_epoch)
                            WHERE session_id = ? AND ended_epoch IS NULL
                        ''',
                            (bitis_epoch, bitis_epoch, session_id),
                        )
                    except Exception:
                        self.logger.warning("Kurtarma: bobin calismalari kapatilamadi (seans %s)", session_id)

                    cursor.execute(
                        '''
                        UPDATE treatment_sessions
                        SET end_time = ?,
                            duration_minutes = ?,
                            session_status = 'ABORTED_DUE_TO_POWER',
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                    ''',
                        (bitis_dt.strftime('%H:%M:%S'), duration_minutes, session_id),
                    )
                    recovered_count += 1

                conn.commit()

            if recovered_count > 0:
                self.logger.warning(
                    f"Recovery: {recovered_count} stale active session kurtarıldı (ABORTED_DUE_TO_POWER)"
                )
        except Exception as e:
            self.logger.warning(f"Stale session recovery uyarısı: {e}")

        return recovered_count

    def run_integrity_check(self, quick: bool = True) -> Dict[str, object]:
        """SQLite integrity check çalıştır ve sonucu döndür."""
        pragma_name = 'quick_check' if quick else 'integrity_check'
        result = {'ok': False, 'check': pragma_name, 'details': []}
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

                # Audit P3: recover_stale_active_sessions 'ABORTED_DUE_TO_POWER' yazar; eski sorgu
                # 'aborted_recovered' ile HİÇ eşleşmiyordu → güç-kaybı kurtarma sayacı daima 0 (izleme kör).
                cursor.execute("SELECT COUNT(*) FROM treatment_sessions WHERE session_status = 'ABORTED_DUE_TO_POWER'")
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

    #: Operatörün "geri dönüşsüz maskelemeyi anladım" onayı (system_settings).
    PII_ONAY_ANAHTARI = "pii_redaction_acknowledged_at"
    #: Operatörün seçtiği saklama süresi (gün). Yoksa ortam değişkeni/varsayılan geçerli.
    PII_SURE_ANAHTARI = "pii_retention_days"

    def redaksiyon_bekleyen_sayisi(self, retain_days: int = 365) -> int:
        """Bu ayarla KAÇ seans maskelenecek? (kuru çalışma — hiçbir şey değiştirmez)

        ⚠️ DENETİM 2026-08-09 (Tier 1): maskeleme GERİ DÖNÜŞSÜZ ve tamamen SESSİZ çalışıyordu.
        Klinik 366. günde hasta adı yerine `[REDACTED]` görüyor, sebebini hiçbir yerde bulamıyor
        ve "veritabanım bozuldu" diye destek arıyordu. Kararı operatörün ALMASI gerekir; bu
        fonksiyon "ne kaybedeceğini" önceden gösterebilmek için var.
        """
        try:
            cutoff = (datetime.now() - timedelta(days=max(1, int(retain_days)))).strftime('%Y-%m-%d')
            with self._get_connection() as conn:
                r = conn.execute(
                    "SELECT COUNT(*) FROM treatment_sessions WHERE session_date < ? AND "
                    "patient_name IS NOT NULL AND patient_name != '' AND patient_name != '[REDACTED]'",
                    (cutoff,),
                ).fetchone()
                return int(r[0] or 0)
        except Exception:
            self.logger.debug("redaksiyon on-sayimi basarisiz", exc_info=True)
            return 0

    def pii_onayi_var_mi(self) -> bool:
        """Operatör geri dönüşsüz maskelemeyi onayladı mı?"""
        return bool(self._get_system_setting(self.PII_ONAY_ANAHTARI))

    def pii_onayla(self) -> None:
        self._set_system_setting(
            self.PII_ONAY_ANAHTARI,
            datetime.now().isoformat(timespec="seconds"),
            "Operator geri donussuz PII maskelemesini onayladi",
        )

    def pii_suresi_oku(self) -> Optional[int]:
        """Operatörün seçtiği süre (gün) ya da None (ayarlanmamış)."""
        v = self._get_system_setting(self.PII_SURE_ANAHTARI)
        try:
            return int(v) if v is not None else None
        except (TypeError, ValueError):
            return None

    def pii_suresi_yaz(self, gun: int) -> None:
        """Saklama süresini ayarla. 0 → maskeleme KAPALI (tıbbi-hukuki saklama ülkeye göre
        değişir; karar operatöründür)."""
        self._set_system_setting(
            self.PII_SURE_ANAHTARI, str(max(0, int(gun))), "Seans PII maskeleme suresi (gun); 0 = kapali"
        )

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

                cursor.execute(
                    '''
                    UPDATE treatment_sessions
                    SET patient_name = CASE WHEN patient_name IS NOT NULL AND patient_name != '' THEN '[REDACTED]' ELSE patient_name END,
                        operator_name = CASE WHEN operator_name IS NOT NULL AND operator_name != '' THEN '[REDACTED]' ELSE operator_name END,
                        patient_notes = CASE WHEN patient_notes IS NOT NULL AND patient_notes != '' THEN '[REDACTED]' ELSE patient_notes END,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE session_date < ?
                ''',
                    (cutoff_date,),
                )
                report['sessions_redacted'] = int(cursor.rowcount)

                # Audit P2: PII isim listesini TEK-KAYNAK self._PII_PARAM_NAMES'ten al. Gömülü liste
                # sapmıştı — gerçek-yazılan 'patient_owner_email'i ATLIYOR, hiç-yazılmayan 'patient_email'i
                # sayıyordu → owner e-postası retention sonrası süresiz düz-metin kalıyordu (KVKK).
                _pii_names = tuple(self._PII_PARAM_NAMES)
                _pii_ph = ",".join("?" * len(_pii_names))
                cursor.execute(
                    f'''
                    UPDATE session_parameters
                    SET parameter_value = '[REDACTED]'
                    WHERE session_id IN (
                        SELECT id FROM treatment_sessions WHERE session_date < ?
                    )
                    AND parameter_name IN ({_pii_ph})
                ''',
                    (cutoff_date, *_pii_names),
                )
                report['parameters_redacted'] = int(cursor.rowcount)

                conn.commit()
        except Exception as e:
            self.logger.warning(f"PII redaction uyarısı: {e}")

        return report

    def anonymize_patients_by_uuid(self, patient_uuids) -> int:
        """KVKK retention (2026-06-28): patient_database'de anonimlestirilen hastalarin bu DB'deki
        kopyasini da anonimlestir (get_session_history JOIN'i eski ad/sahibi gostermesin). Canonical
        karar patient_database.anonymize_inactive_patients'te; bu yalniz kopyayi senkronlar."""
        uuids = [u for u in (patient_uuids or []) if u]
        if not uuids:
            return 0
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                ph = ",".join("?" * len(uuids))
                # 1) patients kopyasi (get_session_history JOIN ile gösterdiği ad/sahip)
                cursor.execute(
                    f"UPDATE patients SET name='[ANONIM]', owner_name='[ANONIM]', vet_contact='', "
                    f"owner_email='', updated_at=CURRENT_TIMESTAMP WHERE patient_uuid IN ({ph})",
                    uuids,
                )
                n = int(cursor.rowcount)
                # 2) KVKK BÜTÜNLÜK (sağ-unutulma): get_session_history patient_name'i session_parameters ve
                #    ts.patient_name'den de okur (COALESCE). Şifreli-at-rest üretimde bu DENORMALİZE PII de
                #    silinmezse anonimleştirme EKSİK kalırdı → ilgili session'ları patient_id üstünden temizle.
                cursor.execute(f"SELECT id FROM patients WHERE patient_uuid IN ({ph})", uuids)
                pids = [r[0] for r in cursor.fetchall() if r[0] is not None]
                if pids:
                    pph = ",".join("?" * len(pids))
                    cursor.execute(
                        f"UPDATE treatment_sessions SET patient_name='[ANONIM]', operator_name='[ANONIM]', "
                        f"patient_notes='[ANONIM]' WHERE patient_id IN ({pph})",
                        pids,
                    )
                    pn_ph = ",".join("?" * len(self._PII_PARAM_NAMES))
                    cursor.execute(
                        f"UPDATE session_parameters SET parameter_value='[ANONIM]' "
                        f"WHERE parameter_name IN ({pn_ph}) AND session_id IN "
                        f"(SELECT id FROM treatment_sessions WHERE patient_id IN ({pph}))",
                        (*self._PII_PARAM_NAMES, *pids),
                    )
                conn.commit()
                return n
        except Exception as e:
            self.logger.warning(f"treatment-history hasta anonimlestirme uyarisi: {e}")
            return 0

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

    def purge_old_coil_runs(self, retain_days: int = 90) -> int:
        """P2 audit 2026-06-28: retention suresini asan per-bobin run kayitlarini (session_coil_runs
        + sensor_run_summary) temizle — eskiden HIC temizlenmiyordu (sinirsiz buyume)."""
        cutoff_ts = datetime.now().timestamp() - (max(1, int(retain_days)) * 86400)
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'DELETE FROM sensor_run_summary WHERE coil_run_id IN '
                    '(SELECT id FROM session_coil_runs WHERE started_epoch < ?)',
                    (cutoff_ts,),
                )
                cursor.execute('DELETE FROM session_coil_runs WHERE started_epoch < ?', (cutoff_ts,))
                removed = int(cursor.rowcount)
                conn.commit()
                return removed
        except Exception as e:
            self.logger.warning(f"Coil-run retention temizleme uyarisi: {e}")
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
                cursor.execute(
                    '''
                    DELETE FROM outbox_messages
                    WHERE status = 'dead' AND available_at < ?
                ''',
                    (cutoff_ts,),
                )
                removed = int(cursor.rowcount)
                conn.commit()
                return removed
        except Exception as e:
            self.logger.warning(f"Dead outbox retention temizleme uyarısı: {e}")
            return 0

    def apply_data_retention_policy(
        self,
        sensor_retain_days: int = 90,
        event_retain_days: int = 365,
        dead_outbox_retain_days: int = 30,
        pii_retain_days: int = 365,
    ) -> Dict[str, int]:
        """Toplu retention policy uygula (ticari operasyon bakımı).

        DENETIM P2: her sure <= 0 ise O ADIM ATLANIR (kapali). Eskiden adimlar kosulsuzdu ve
        cagiran hicbir parametre gecirmedigi icin sabit 90/365/30/365 gun ZORLANIYORDU:
        bobin-calisma kayitlari ve seans olaylari GERI DONUSSUZ siliniyor, hasta/operator
        adlari maskeleniyordu — opt-out YOKTU. Tibbi-hukuki saklama suresi ulkeye/kliniğe gore
        degisir (KVKK silmeyi ister, dava dosyasi saklamayi) → operator karari olmali.
        Yapilandirma: services/headless_db_maintenance.py (PEMF_RETAIN_* env degiskenleri).
        """
        report = {
            'sensor_samples_removed': 0,
            'coil_runs_removed': 0,
            'session_events_removed': 0,
            'dead_outbox_removed': 0,
            'sessions_pii_redacted': 0,
            'parameters_pii_redacted': 0,
        }

        if sensor_retain_days and sensor_retain_days > 0:
            report['sensor_samples_removed'] = self.purge_old_sensor_samples(sensor_retain_days)
            report['coil_runs_removed'] = self.purge_old_coil_runs(sensor_retain_days)  # P2 audit 2026-06-28
        if event_retain_days and event_retain_days > 0:
            report['session_events_removed'] = self.purge_old_session_events(event_retain_days)
        if dead_outbox_retain_days and dead_outbox_retain_days > 0:
            report['dead_outbox_removed'] = self.purge_old_dead_outbox(dead_outbox_retain_days)

        # ── PII MASKELEME: OPERATÖR ONAYI OLMADAN ÇALIŞMAZ (2026-08-09 denetimi, Tier 1) ──────
        # Maskeleme GERİ DÖNÜŞSÜZDÜR ve tamamen SESSİZ çalışıyordu: klinik 366. günde hasta adı
        # yerine `[REDACTED]` görüyor, sebebini hiçbir yerde bulamıyor, "veritabanım bozuldu"
        # diye destek arıyordu. Süre yalnız bir ortam değişkeniyle (PEMF_RETAIN_PII_DAYS)
        # ayarlanabiliyordu — hiçbir veteriner bunu bilmez.
        #
        # Yeni kural: maskelenecek KAYIT VARSA ve operatör bunu ONAYLAMAMIŞSA, hiçbir şey
        # maskelenmez; rapor `pii_pending` ile kaç kaydın beklediğini söyler ve arayüz sorar.
        # Operatörün seçtiği süre varsa ortam değişkenini EZER (ayar arayüzden yönetilir).
        _secilen = self.pii_suresi_oku()
        if _secilen is not None:
            pii_retain_days = _secilen
        report['pii_pending'] = 0
        if pii_retain_days and pii_retain_days > 0:
            if not self.pii_onayi_var_mi():
                bekleyen = self.redaksiyon_bekleyen_sayisi(pii_retain_days)
                report['pii_pending'] = bekleyen
                if bekleyen:
                    self.logger.warning(
                        "KVKK: %d seans kaydı maskelenmeyi bekliyor ama operatör ONAYI YOK — "
                        "maskeleme YAPILMADI (geri dönüşsüz işlem sessizce uygulanmaz).",
                        bekleyen,
                    )
            else:
                pii_report = self.redact_old_session_pii(pii_retain_days)
                report['sessions_pii_redacted'] = int(pii_report.get('sessions_redacted', 0))
                report['parameters_pii_redacted'] = int(pii_report.get('parameters_redacted', 0))
                # Denetim izi (2026-08-09, Tier 3): maskeleme GERİ DÖNÜŞSÜZ ve arka planda,
                # kimse bakmadan çalışır. Kaç kaydın hangi eşikle maskelendiği yazılmazsa,
                # klinik 366. günde [REDACTED] görüp sebebini hiçbir yerde bulamaz.
                if report['sessions_pii_redacted'] or report['parameters_pii_redacted']:
                    self.denetim_yaz(
                        "retention.pii_maskelendi",
                        scope="otomatik",
                        item_count=report['sessions_pii_redacted'],
                        detail={"gun": int(pii_retain_days), "parametre": report['parameters_pii_redacted']},
                    )

        return report

    # ── B-1.3 (audit) — at-rest şifreleme YOKken PII düz-metin yazma koruması ──────────
    # Tedavi-DB PII kolonları SQL'de display için okunur (whole-DB SQLCipher üretimde ZORUNLU +
    # fail-closed → şifreli). Ama at_rest_encrypted=False iken (yalnız dev/yanlış-yapılandırma)
    # gerçek PII'yi DÜZ-METİN yazmak yerine maskele: "kazara düz-metni kes" (kullanıcı kararı).
    # session_parameters içindeki PII olan parametre ADLARI (değeri maskelenir; ad PII değil):
    _PII_PARAM_NAMES = frozenset(
        {
            "patient_name",
            "patient_surname",
            "patient_owner",
            "patient_owner_email",
            "patient_owner_phone",
            "patient_vet_contact",
            "patient_veteriner",
        }
    )
    _PII_REDACTION = "[SIFRELENMEMIS-DB]"

    def _redact_pii(self, value):
        """at_rest_encrypted=True → değer AYNEN (whole-DB SQLCipher = birincil koruma, şifreli saklanır).

        at_rest_encrypted=False → SAHİP KARARI (2026-07-28): maskeleme VARSAYILAN KAPALI. Tedavi
        geçmişinde hasta/sahip/operatör adları GERÇEK görünür. Gerekçe: AYNI PII zaten patients.db'de
        DÜZ-METİN tutuluyor → yalnız tedavi-geçmişinde maskelemek tutarsız bir yarım-önlemdi (klinik
        kullanılabilirliği bozuyor '[SIFRELENMEMIS-DB]', gerçek gizlilik EKLEMİYOR). Eski maskeleme
        davranışı PEMF_MASK_HISTORY_PII=1 ile geri açılabilir (opt-in). DOĞRU üretim çözümü:
        PEMF_ENCRYPT_AT_REST=1 + sqlcipher → değerler ŞİFRELİ saklanır AMA gerçek görünür.
        NOT: Bu değişiklik İLERİYE dönük — daha önce maskelenmiş kayıtlarda gerçek ad yazıya hiç
        girmediği için geri getirilemez (yeni seanslar gerçek adla yazılır)."""
        if value is None or value == "":
            return value
        if getattr(self, "at_rest_encrypted", False):
            return value
        if os.getenv("PEMF_MASK_HISTORY_PII", "0") == "1":
            return self._PII_REDACTION
        return value

    def start_session(
        self,
        treatment_mode: str,
        target_condition: str = None,
        operator_name: str = None,
        patient_name: str = None,
        operator_email: str = None,
    ) -> int:
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

                cursor.execute(
                    '''
                    INSERT INTO treatment_sessions
                    (session_date, start_time, treatment_mode, target_condition,
                     operator_name, operator_email, patient_name, session_status, session_uuid)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?)
                ''',
                    (
                        session_date,
                        start_time,
                        treatment_mode,
                        target_condition,
                        self._redact_pii(operator_name),
                        (operator_email or None),
                        self._redact_pii(patient_name),
                        session_uuid,
                    ),
                )

                session_id = cursor.lastrowid
                conn.commit()

                self.logger.info(f"Yeni tedavi seansı başlatıldı: ID {session_id}")
                return session_id

        except _DB_ERROR as e:
            self.logger.error(f"Seans başlatma hatası: {e}")
            raise

    def end_session(
        self, session_id: int, parameters: Dict = None, patient_notes: str = None, duration_minutes: int = None
    ):
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
                cursor.execute(
                    '''
                    SELECT start_time, session_date FROM treatment_sessions
                    WHERE id = ?
                ''',
                    (session_id,),
                )

                result = cursor.fetchone()
                if not result:
                    raise ValueError(f"Seans bulunamadı: {session_id}")

                start_time_str, session_date = result

                # Süreyi hesapla (opsiyonel override varsa kullan)
                now = datetime.now()
                end_time = now.strftime('%H:%M:%S')

                if duration_minutes is None:
                    # Savunmali: negatif-clamp (saat kaymasi/DST/session_date tutarsizligi) + malformed
                    # tarih guard'i (strptime patlarsa end_session komple basarisiz olmasin, 0 yaz).
                    try:
                        start_datetime = datetime.strptime(f"{session_date} {start_time_str}", '%Y-%m-%d %H:%M:%S')
                        duration_minutes = max(0, int((now - start_datetime).total_seconds() / 60))
                    except Exception:
                        self.logger.warning(
                            "Sure hesaplanamadi (session_date=%s start=%s) → 0 dk.", session_date, start_time_str
                        )
                        duration_minutes = 0

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
                    update_data.insert(-1, self._redact_pii(patient_notes))

                update_query += ' WHERE id = ?'

                cursor.execute(update_query, update_data)

                # Detaylı parametreleri kaydet
                if parameters:
                    for param_name, param_value in parameters.items():
                        if param_name not in ['frequency_hz', 'intensity_mt', 'pulse_duration_ms']:
                            _pv = str(param_value)
                            if param_name in self._PII_PARAM_NAMES:
                                _pv = self._redact_pii(_pv)
                            cursor.execute(
                                '''
                                INSERT INTO session_parameters
                                (session_id, parameter_name, parameter_value)
                                VALUES (?, ?, ?)
                            ''',
                                (session_id, param_name, _pv),
                            )

                conn.commit()
                self.logger.info(f"Tedavi seansı sonlandırıldı: ID {session_id}")

        except _DB_ERROR as e:
            self.logger.error(f"Seans sonlandırma hatası: {e}")
            raise

    def get_session_history(
        self,
        limit: int = 100,
        start_date: str = None,
        end_date: str = None,
        treatment_mode: str = None,
        before_id: int = None,
        internal_full: bool = False,
        session_ids=None,
    ) -> List[Dict]:
        """
        Tedavi geçmişini getir

        Args:
            limit: Maksimum kayıt sayısı
            start_date: Başlangıç tarihi (YYYY-MM-DD)
            end_date: Bitiş tarihi (YYYY-MM-DD)
            treatment_mode: Tedavi modu filtresi
            before_id: audit B-8.2 keyset (cursor) pagination — verilirse yalnız bu id'den ESKİ
                       (daha küçük id) seanslar döner. Bir sonraki sayfa için: son öğenin id'sini geçir.

        Returns:
            List[Dict]: Tedavi seansları listesi (id DESC = kronolojik, yeni önce)
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                query = '''
                    SELECT ts.id, ts.session_date, ts.start_time, ts.end_time, ts.duration_minutes,
                           ts.treatment_mode, ts.target_condition, ts.frequency_hz, ts.intensity_mt,
                           ts.pulse_duration_ms, ts.operator_name, ts.operator_email, ts.patient_notes, ts.session_status,
                           COALESCE(sp_name.parameter_value, ts.patient_name) as patient_name,
                           sp_surname.parameter_value as patient_surname,
                           sp_age.parameter_value as patient_age,
                           sp_species.parameter_value as patient_species,
                           sp_breed.parameter_value as patient_breed,
                           sp_weight.parameter_value as patient_weight,
                           sp_owner.parameter_value as patient_owner,
                           sp_vet.parameter_value as patient_vet_contact,
                           sp_veteriner.parameter_value as patient_veteriner,
                           sp_duration.parameter_value as treatment_duration,
                           COALESCE(NULLIF(sp_owner_email.parameter_value, ''), pt.owner_email) as owner_email
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
                    LEFT JOIN session_parameters sp_owner_email ON ts.id = sp_owner_email.session_id AND sp_owner_email.parameter_name = 'patient_owner_email'
                    LEFT JOIN patients pt ON ts.patient_id = pt.id
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

                # audit B-8.2: keyset (cursor) pagination — before_id verilirse ondan ESKI (daha kucuk id)
                # satirlar. id PK (monoton+benzersiz, indexli) → buyuk-OFFSET taramasi YOK + araya yeni
                # seans girse de sayfa kaymasi/atlama YOK (offset'in aksine). id DESC = kronolojik (yeni once);
                # pratikte session_date DESC ile ozdes (id insertion-order = tedavi-baslama-order).
                if before_id is not None:
                    query += ' AND ts.id < ?'
                    params.append(int(before_id))

                # DENETIM P3: cagiranlar (CSV export, PDF) istenen id kumesini SQL'e HIC
                # gecirmiyor; 10.000 satirlik tam sonucu 11 LEFT JOIN ile cekip Python'da
                # filtreliyorlardi (olculen tepe ~24 MB + gereksiz JOIN isi). Filtre artik
                # SQL'de: yalnizca istenen satirlar okunur/materyalize edilir.
                # GUVENLIK: id'ler int()'e zorlanir → SQL enjeksiyonu yuzeyi yok.
                # None = filtre YOK (geriye uyumlu). BOS LISTE = "hicbir kayit" demektir:
                # istemci ?session_ids=, gonderdiginde filtreyi yok sayip TUM KLINIGI dokmek
                # KVKK ihlalidir ("Benim Seanslarim" secili iken tum-klinik PII dokumu).
                if session_ids is not None:
                    _ids = [int(x) for x in session_ids]
                    if not _ids:
                        return []
                    query += f" AND ts.id IN ({','.join('?' * len(_ids))})"
                    params.extend(_ids)

                query += ' ORDER BY ts.id DESC LIMIT ?'
                # DoS-clamp: istemci-kontrollü limit'i [1,500]'e sabitle (get_ai_analyses ile tutarlı) →
                # limit=99999999 ile devasa fetch/RAM engellenir. Audit P2: iç export/PDF yolları
                # (internal_full=True) TAM-geçmiş çektiği için daha yüksek kapak — eskiden 500'e sessizce
                # kırpılıyor, >500 seanslı klinikte eski medikal kayıtlar 'tümü indirildi' denip düşüyordu.
                _cap = 100000 if internal_full else 500
                params.append(max(1, min(int(limit), _cap)))

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
                cursor.execute(
                    '''
                    SELECT * FROM treatment_sessions WHERE id = ?
                ''',
                    (session_id,),
                )

                session_row = cursor.fetchone()
                if not session_row:
                    return None

                columns = [desc[0] for desc in cursor.description]
                session = dict(zip(columns, session_row))

                # Parametreler
                cursor.execute(
                    '''
                    SELECT parameter_name, parameter_value, parameter_unit
                    FROM session_parameters WHERE session_id = ?
                ''',
                    (session_id,),
                )

                parameters = {}
                for param_row in cursor.fetchall():
                    param_name, param_value, param_unit = param_row
                    parameters[param_name] = {'value': param_value, 'unit': param_unit}

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

                # Tamamlanan seans (mobil KPI fallback 'completed_sessions' okuyor)
                cursor.execute(
                    "SELECT COUNT(*) FROM treatment_sessions WHERE LOWER(COALESCE(session_status,'')) = 'completed'"
                )
                stats['completed_sessions'] = cursor.fetchone()[0]

                # Bu ay seans sayısı
                current_month = datetime.now().strftime('%Y-%m')
                cursor.execute(
                    '''
                    SELECT COUNT(*) FROM treatment_sessions
                    WHERE session_date LIKE ?
                ''',
                    (f"{current_month}%",),
                )
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

    def update_session_finalized_extras(
        self, session_id: int, notes: str = None, frequency_hz=None, intensity_mt=None
    ) -> None:
        """ZATEN kapatilmis (finalized) bir seansta YALNIZ not/parametre alanlarini gunceller.

        DENETIM P1: gozlem-notu akisi (POST /api/session/notes) eskiden end_session'i TEKRAR
        cagiriyordu; end_session ise end_time / duration_minutes / session_status alanlarini
        KOSULSUZ yeniden yaziyor ve duration_minutes=None gelirse sureyi `now - start` ile
        YENIDEN hesapliyor. Sonuc: /stop'un yazdigi GERCEK tedavi suresi, istemcinin gonderdigi
        PLANLANAN sure ile (4 dk -> 20 dk) ya da notun yazildigi ana kadar gecen sureyle
        (45 dk sonra not -> 65 dk) eziliyordu = tibbi kayit bozulmasi. Bu metod zaman/durum
        alanlarina DOKUNMAZ; yalnizca verilen alanlari gunceller.
        """
        try:
            self._ensure_write_guardrail()
            if not session_id:
                return
            sets, vals = [], []
            if notes is not None:
                sets.append('patient_notes = ?')
                vals.append(self._redact_pii(notes))
            if frequency_hz is not None:
                sets.append('frequency_hz = ?')
                vals.append(frequency_hz)
            if intensity_mt is not None:
                sets.append('intensity_mt = ?')
                vals.append(intensity_mt)
            if not sets:
                return
            sets.append('updated_at = CURRENT_TIMESTAMP')
            vals.append(int(session_id))
            with self._get_connection() as conn:
                cursor = conn.cursor()
                # SET parcalari yalnizca yukaridaki SABIT literallerden gelir (kullanici girdisi
                # DEGIL); tum degerler parametrelidir → enjeksiyon yuzeyi yok.
                cursor.execute('UPDATE treatment_sessions SET ' + ', '.join(sets) + ' WHERE id = ?', vals)
                conn.commit()
            self.logger.info(f"Kapatilmis seansin not/parametreleri guncellendi: ID {session_id}")
        except _DB_ERROR as e:
            self.logger.error(f"update_session_finalized_extras hatasi: {e}")

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

                cursor.execute(
                    '''
                    UPDATE treatment_sessions
                    SET patient_notes = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''',
                    (self._redact_pii(notes), session_id),
                )  # Audit P3: end_session ile tutarlı PII maskesi (şifresiz modda da uygula)

                conn.commit()
                self.logger.info(f"Seans notları güncellendi: ID {session_id}")

        except _DB_ERROR as e:
            self.logger.error(f"Seans notları güncelleme hatası: {e}")
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
                cursor.execute('DELETE FROM session_parameters WHERE session_id = ?', (session_id,))
                # Çocuk kayıtları sil — FK ON DELETE CASCADE yok; aksi halde veri-içeren seansı
                # silmek FOREIGN KEY hatasıyla 500 döner.
                cursor.execute('DELETE FROM sensor_samples WHERE session_id = ?', (session_id,))
                cursor.execute('DELETE FROM session_events WHERE session_id = ?', (session_id,))
                # P2 audit 2026-06-28: per-bobin run tablolari da silinsin (eskiden orphan kaliyordu).
                cursor.execute(
                    'DELETE FROM sensor_run_summary WHERE coil_run_id IN '
                    '(SELECT id FROM session_coil_runs WHERE session_id = ?)',
                    (session_id,),
                )
                cursor.execute('DELETE FROM session_coil_runs WHERE session_id = ?', (session_id,))

                # Sonra seansı sil
                cursor.execute('DELETE FROM treatment_sessions WHERE id = ?', (session_id,))

                conn.commit()
                self.logger.info(f"Tedavi seansı silindi: ID {session_id}")

        except _DB_ERROR as e:
            self.logger.error(f"Seans silme hatası: {e}")
            raise

    def close(self):
        """Veritabanı bağlantısını kapat"""
        self.close_connections()

    def record_session_event(
        self, session_id: Optional[int], event_type: str, payload: Optional[Dict] = None, severity: str = 'info'
    ) -> Optional[int]:
        """Seans olayını local event tablosuna kaydet."""
        try:
            self._ensure_write_guardrail()
            payload_json = json.dumps(payload or {}, ensure_ascii=True)
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    '''
                    INSERT INTO session_events
                    (event_uuid, session_id, event_type, severity, payload, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''',
                    (str(uuid.uuid4()), session_id, event_type, severity, payload_json, datetime.now().timestamp()),
                )
                conn.commit()
                return cursor.lastrowid
        except Exception as e:
            self.logger.warning(f"Session event kaydedilemedi: {e}")
            return None

    # ---- AI Analiz Geçmişi (profesyonel detaylı kayıt; SQLCipher-şifreli → KVKK-güvenli) ----
    def add_ai_analysis(
        self,
        mode: str = "",
        module_id: str = "",
        module_label: str = "",
        patient_name: str = "",
        input_type: str = "",
        result_summary: str = "",
        result_detail: Optional[Dict] = None,
        confidence: Optional[float] = None,
        operator_email: str = "",
    ) -> Optional[int]:
        """Bir AI analiz sonucunu şifreli geçmişe ekle. Tüm profillerin tüm modelleri buraya yazar.
        operator_email = analizi yapan hekim (klinik-içi "Benim/Tüm Klinik" filtresi; yeni param SONDA → pozisyonel çağrılar bozulmaz)."""
        try:
            self._ensure_write_guardrail()
            # B-1.3 deseni (start_session ile tutarlı): at-rest şifreleme KAPALIYSA gerçek isim yerine
            # [SIFRELENMEMIS-DB] yazılır → şifresiz DB'de düz-metin PII sızmaz. Şifreliyse isim korunur.
            patient_name = self._redact_pii(patient_name)
            # operator_email = hekimin KENDİ login e-postası (hasta PII'si değil); filtre için ham saklanır
            # (üretimde DB zaten SQLCipher-şifreli). _redact_pii uygulanırsa "Benim" filtresi maskede bozulurdu.
            operator_email = operator_email or ""
            detail_json = json.dumps(result_detail or {}, ensure_ascii=False)
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    '''
                    INSERT INTO ai_analyses
                    (created_at, mode, module_id, module_label, patient_name, operator_email, input_type, result_summary, result_detail, confidence)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                    (
                        datetime.now().isoformat(timespec="seconds"),
                        mode,
                        module_id,
                        module_label,
                        patient_name,
                        operator_email,
                        input_type,
                        result_summary,
                        detail_json,
                        confidence,
                    ),
                )
                conn.commit()
                return cursor.lastrowid
        except Exception as e:
            self.logger.warning(f"AI analiz kaydedilemedi: {e}")
            return None

    def set_ai_review(self, analysis_id: int, status: str, note: str = "", reviewed_by: str = "") -> bool:
        """AI analizine HEKİM DEĞERLENDİRMESİ yaz (2026-08-06, sahip isteği).

        `status`: "approved" | "rejected" | "corrected".
        ⚠️ Kayıt SİLİNMEZ, AI çıktısı DEĞİŞTİRİLMEZ — hekimin kararı YANINA yazılır. AI'ın ne
        dediği ile hekimin ne dediği ayrı ayrı görünür kalmalı (klinik denetlenebilirlik: sonradan
        "model ne demişti?" sorusunun cevabı kaybolmamalı).
        """
        if status not in ("approved", "rejected", "corrected"):
            raise ValueError(f"Geçersiz değerlendirme durumu: {status}")
        try:
            with self._get_connection() as conn:
                cur = conn.cursor()
                cur.execute(
                    "UPDATE ai_analyses SET review_status=?, review_note=?, reviewed_by=?, reviewed_at=? WHERE id=?",
                    (
                        status,
                        str(note or ""),
                        str(reviewed_by or ""),
                        datetime.now().isoformat(timespec="seconds"),
                        int(analysis_id),
                    ),
                )
                conn.commit()
                return cur.rowcount > 0
        except Exception as e:
            self.logger.warning(f"AI değerlendirmesi yazılamadı: {e}")
            return False

    # ---- CİHAZ TAŞIMA: şifreli dışa/içe aktarma (2026-08-08) ----
    # ⚠️ DENETİM 2026-08-09 (ENGEL) — CİHAZ TAŞIMA EKSİK VERİ TAŞIYORDU.
    # Dışa aktarma YALNIZCA `treatment_sessions` + `ai_analyses` alıyordu. Oysa tıbbi kaydın ASIL
    # gövdesi bağlı tablolarda:
    #     session_coil_runs   → HANGİ bobin, hangi frekans/duty ile, ne kadar süre çalıştı (= DOZ)
    #     sensor_samples      → sıcaklık/akım/alan telemetrisi (yan etki soruşturmasının kanıtı)
    #     session_events      → acil durdurma dahil denetim izi
    #     session_parameters  → seansın uygulanan parametreleri
    #     sensor_run_summary  → bobin-koşusu başına sensör özeti
    # Yani veteriner "kliniğimin geçmişini taşıdım" diyor, gerçekte seans BAŞLIKLARI taşınıyor;
    # uygulanan dozun kaydı eski makinede kalıyordu. Eski makine silinirse geri dönülemez kayıp.
    #
    # İKİNCİ ENGEL: `import_rows` `id`'yi düşürüyordu. Bağlı tabloları eklesek bile `session_id`
    # hedefte BAŞKA bir seansı gösterirdi (sessiz kayıt karışması — hastanın verisi başka hastaya).
    # `treatment_sessions.patient_id` de aynı sebeple kopuyordu.
    # ÇÖZÜM: id'ler dışa aktarılır, içe aktarmada ESKİ→YENİ eşlemesi kurulur ve tüm çocuk satırlar
    # yeniden bağlanır. Kimlikler yine AUTOINCREMENT'tir; korunan şey İLİŞKİdir.

    #: Dışa aktarılan tablolar — sıra ÖNEMLİ (ebeveyn önce; içe aktarma bu sırayı izler).
    _TASINAN_TABLOLAR = (
        "patients",
        "treatment_sessions",
        "session_parameters",
        "session_coil_runs",
        "sensor_run_summary",
        "sensor_samples",
        "session_events",
        "ai_analyses",
    )

    #: Tablo -> hedefte AYNI kaydı bulmaya yarayan UNIQUE doğal anahtar. Mükerrer bir satırda
    #: (aynı hasta / aynı olay) INSERT patlar; bu anahtarla mevcut kaydın id'si bulunup eşlemeye
    #: yazılır → çocuk satırlar mevcut kayda bağlanır, sessizce ATILMAZ.
    _DOGAL_ANAHTAR = {"patients": "patient_uuid", "session_events": "event_uuid"}

    #: (tablo, kolon) -> hangi tablonun id'sine bakıyor. İçe aktarmada bu kolonlar YENİDEN YAZILIR.
    _ILISKILER = {
        ("treatment_sessions", "patient_id"): "patients",
        ("session_parameters", "session_id"): "treatment_sessions",
        ("session_coil_runs", "session_id"): "treatment_sessions",
        ("sensor_samples", "session_id"): "treatment_sessions",
        ("session_events", "session_id"): "treatment_sessions",
        ("sensor_run_summary", "coil_run_id"): "session_coil_runs",
    }

    def export_rows(self) -> Dict[str, List[Dict]]:
        """Taşınabilir TÜM tabloların satırlarını ham olarak döner (dışa aktarma için).

        `get_session_history`/`get_ai_analyses` limit uyguladığı için taşımada kullanılamaz —
        sessizce kayıp veriye yol açardı.

        ⚠️ `id` kolonları KORUNUR: içe aktarma ilişkileri onlarla yeniden kurar (bkz. üstteki not).
        """
        out: Dict[str, List[Dict]] = {t: [] for t in self._TASINAN_TABLOLAR}
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                mevcut = {r[0] for r in cursor.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
                for tablo in self._TASINAN_TABLOLAR:
                    if tablo not in mevcut:  # çok eski DB — tablo henüz yok
                        continue
                    cursor.execute(f"SELECT * FROM {tablo} ORDER BY id ASC")
                    cols = [c[0] for c in cursor.description]
                    out[tablo] = [dict(zip(cols, r)) for r in cursor.fetchall()]
        except Exception:
            self.logger.exception("Dışa aktarma için satırlar okunamadı.")
            raise
        return out

    def import_rows(self, data: Dict[str, List[Dict]], replace: bool = False) -> Dict[str, int]:
        """Dışa aktarılmış satırları geri yükler — İLİŞKİLERİ KORUYARAK.

        ⚠️ `id` DEĞERLERİ korunmaz (AUTOINCREMENT, hedefte çakışabilir) ama İLİŞKİLER korunur:
        her tablo eklenirken ESKİ id → YENİ id eşlemesi tutulur ve çocuk satırların
        `session_id`/`patient_id`/`coil_run_id` kolonları yeniden yazılır. Bu olmadan bir seansın
        bobin-koşuları/telemetrisi hedefte BAŞKA bir seansa bağlanırdı — hastanın verisi başka
        hastanın kaydında görünürdü (bkz. `_ILISKILER` üstündeki denetim notu).

        ⚠️ `replace=True` hedefteki TÜM taşınan tabloları SİLER. Varsayılan `False` EKLER —
        aynı dosyayı iki kez içe aktarmak KAYITLARI ÇOĞALTIR; çağıran (API) bunu boş-hedef
        kuralıyla engeller.

        GERİYE UYUM: v1 yedekleri yalnız `treatment_sessions` + `ai_analyses` içerir; eksik
        tablolar boş geçilir, ilişki eşlemesi yine kurulur (o yedeklerde bağlı satır yoktur).
        """
        sonuc = {t: 0 for t in self._TASINAN_TABLOLAR}
        # tablo -> {eski_id: yeni_id}
        eslem: Dict[str, Dict[Any, int]] = {t: {} for t in self._TASINAN_TABLOLAR}
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if replace:
                # Çocuktan ebeveyne doğru sil (FK ihlali olmasın).
                for tablo in reversed(self._TASINAN_TABLOLAR):
                    try:
                        cursor.execute(f"DELETE FROM {tablo}")
                    except Exception:
                        self.logger.debug("temizlenemedi: %s", tablo, exc_info=True)

            var_olan_tablolar = {
                r[0] for r in cursor.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            }

            for tablo in self._TASINAN_TABLOLAR:
                satirlar = data.get(tablo) or []
                if not satirlar or tablo not in var_olan_tablolar:
                    continue
                cursor.execute(f"PRAGMA table_info({tablo})")
                gecerli = {r[1] for r in cursor.fetchall()} - {"id"}
                # Bu tablonun hangi kolonları hangi tabloya bakıyor?
                yeniden_bagla = {
                    kol: hedef for (t, kol), hedef in self._ILISKILER.items() if t == tablo and kol in gecerli
                }
                for s in satirlar:
                    # Hedef şemada OLMAYAN kolonları at (eski/yeni sürüm arası uyum).
                    alan = {k: v for k, v in s.items() if k in gecerli}
                    if not alan:
                        continue
                    atla = False
                    for kol, hedef_tablo in yeniden_bagla.items():
                        eski = alan.get(kol)
                        if eski is None:
                            continue  # seansa bağlı olmayan satır (NULL) — normal
                        yeni = eslem[hedef_tablo].get(eski)
                        if yeni is None:
                            # Ebeveyni taşınmamış çocuk satır: SESSİZCE YANLIŞ BAĞLAMAK yerine ATLA.
                            # Yanlış bağlamak, bir hastanın telemetrisini başka bir hastanın
                            # kaydında gösterirdi — sessiz ve teşhis edilemez bir tıbbi hata.
                            self.logger.warning(
                                "İçe aktarma: %s satırı ebeveyni bulunamadığı için atlandı (%s=%r).", tablo, kol, eski
                            )
                            atla = True
                            break
                        alan[kol] = yeni
                    if atla:
                        continue
                    ph = ", ".join("?" for _ in alan)
                    try:
                        cursor.execute(f"INSERT INTO {tablo} ({', '.join(alan)}) VALUES ({ph})", list(alan.values()))
                    except Exception:
                        # UNIQUE çakışması: bu satır hedefte ZATEN VAR (aynı hasta/olay).
                        #
                        # ⚠️ Burada "atla ve devam et" demek YETMEZ: eşlemeye giriş yazılmazsa o
                        # ebeveyne bağlı TÜM çocuk satırlar (seanslar, bobin koşuları, telemetri)
                        # yukarıdaki "ebeveyni bulunamadı" dalına düşüp SESSİZCE ATILIR. Yani tek
                        # bir mükerrer hasta, o hastanın bütün geçmişini yok ederdi.
                        # Doğrusu BİRLEŞTİRMEKtir: mevcut satırın id'sini doğal anahtarla bul ve
                        # eşlemeye yaz → çocuklar mevcut kayda bağlanır.
                        mevcut_id = None
                        dogal = self._DOGAL_ANAHTAR.get(tablo)
                        if dogal and s.get(dogal) is not None:
                            try:
                                r = cursor.execute(f"SELECT id FROM {tablo} WHERE {dogal} = ?", (s[dogal],)).fetchone()
                                mevcut_id = r[0] if r else None
                            except Exception:
                                mevcut_id = None
                        if mevcut_id is not None and s.get("id") is not None:
                            eslem[tablo][s["id"]] = mevcut_id
                            self.logger.info(
                                "İçe aktarma: %s satırı hedefte zaten var, MEVCUT kayda bağlandı (%s=%r).",
                                tablo,
                                dogal,
                                s[dogal],
                            )
                        else:
                            self.logger.warning("İçe aktarma: %s satırı eklenemedi, atlandı.", tablo, exc_info=True)
                        continue
                    if s.get("id") is not None:
                        eslem[tablo][s["id"]] = cursor.lastrowid
                    sonuc[tablo] += 1
            conn.commit()
        return sonuc

    def delete_ai_analysis(self, analysis_id: int, operator_email: Optional[str] = None) -> bool:
        """TEK bir AI analiz kaydını siler.

        `operator_email` verilirse yalnız O KİŞİYE ait (veya sahipsiz) kayıt silinir — böylece
        klinik profili olmayan kullanıcı başkasının kaydını silemez. KVKK silme hakkı için gerekli:
        kullanıcı kendi kaydını kaldırabilmeli, başkasınınkini kaldıramamalı.
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                if operator_email:
                    cursor.execute(
                        "DELETE FROM ai_analyses WHERE id = ? AND "
                        "(operator_email IS NULL OR operator_email = '' OR LOWER(operator_email) = ?)",
                        (int(analysis_id), operator_email.strip().lower()),
                    )
                else:
                    cursor.execute("DELETE FROM ai_analyses WHERE id = ?", (int(analysis_id),))
                silindi = cursor.rowcount > 0
                conn.commit()
                return silindi
        except Exception:
            self.logger.exception("AI analiz kaydı silinemedi (id=%s).", analysis_id)
            return False

    def clear_ai_analyses(self, operator_email: Optional[str] = None) -> int:
        """AI analiz geçmişini TOPLU siler; silinen kayıt sayısını döner.

        ⚠️ VACUUM ŞART: `DELETE` satırları yalnız serbest listeye bırakır — hasta adı ve analiz
        özeti dosyada OKUNABİLİR kalır. `clear_all_patients` ile aynı kural (audit P3).
        VACUUM tüm dosyayı yeniden yazdığı için silinen kişisel veri gerçekten gider.
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                if operator_email:
                    op = operator_email.strip().lower()
                    cursor.execute(
                        "SELECT COUNT(*) FROM ai_analyses WHERE "
                        "(operator_email IS NULL OR operator_email = '' OR LOWER(operator_email) = ?)",
                        (op,),
                    )
                    n = int(cursor.fetchone()[0] or 0)
                    cursor.execute(
                        "DELETE FROM ai_analyses WHERE "
                        "(operator_email IS NULL OR operator_email = '' OR LOWER(operator_email) = ?)",
                        (op,),
                    )
                else:
                    cursor.execute("SELECT COUNT(*) FROM ai_analyses")
                    n = int(cursor.fetchone()[0] or 0)
                    cursor.execute("DELETE FROM ai_analyses")
                conn.commit()
                cursor.execute("VACUUM")
                return n
        except Exception:
            self.logger.exception("AI analiz geçmişi temizlenemedi.")
            return -1

    def get_ai_analyses(
        self,
        limit: int = 50,
        module_id: Optional[str] = None,
        patient_name: Optional[str] = None,
        before_id: Optional[int] = None,
    ) -> List[Dict]:
        """AI analiz geçmişini getir (id DESC = yeni önce). Filtre: modül / hasta / keyset-pagination."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                clauses, params = [], []
                if module_id:
                    clauses.append("module_id = ?")
                    params.append(module_id)
                if patient_name:
                    clauses.append("patient_name LIKE ?")
                    params.append(f"%{patient_name}%")
                if before_id:
                    clauses.append("id < ?")
                    params.append(int(before_id))
                where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
                params.append(max(1, min(int(limit), 500)))
                cursor.execute(
                    "SELECT id, created_at, mode, module_id, module_label, patient_name, operator_email, "
                    "input_type, result_summary, result_detail, confidence, "
                    # Hekim değerlendirmesi (2026-08-06) — AI çıktısı öneri, karar hekimin.
                    "COALESCE(review_status,'') AS review_status, COALESCE(review_note,'') AS review_note, "
                    "COALESCE(reviewed_by,'') AS reviewed_by, COALESCE(reviewed_at,'') AS reviewed_at "
                    f"FROM ai_analyses{where} ORDER BY id DESC LIMIT ?",
                    params,
                )
                cols = [c[0] for c in cursor.description]
                out = []
                for r in cursor.fetchall():
                    d = dict(zip(cols, r))
                    try:
                        d["result_detail"] = json.loads(d.get("result_detail") or "{}")
                    except Exception:
                        d["result_detail"] = {}
                    out.append(d)
                return out
        except Exception as e:
            self.logger.warning(f"AI analiz geçmişi okunamadı: {e}")
            return []

    def enqueue_outbox_message(
        self,
        topic: str,
        payload: str,
        qos: int = 0,
        retain: bool = False,
        source: str = 'gateway',
        correlation_id: Optional[str] = None,
        available_at: Optional[float] = None,
        idempotency_key: Optional[str] = None,
    ) -> Optional[int]:
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
                cursor.execute(
                    '''
                    INSERT INTO outbox_messages
                    (message_uuid, idempotency_key, topic, payload, qos, retain, status, retry_count,
                     available_at, source, correlation_id, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, 'pending', 0, ?, ?, ?, ?)
                ''',
                    (
                        str(uuid.uuid4()),
                        derived_key,
                        topic,
                        payload,
                        int(qos),
                        int(bool(retain)),
                        ready_at,
                        source,
                        correlation_id,
                        now_ts,
                    ),
                )
                conn.commit()
                return cursor.lastrowid
        except _DB_INTEGRITY:
            # Idempotency key duplicate -> mevcut kaydı tekrar ekleme
            if not derived_key:
                return None
            try:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute('SELECT id FROM outbox_messages WHERE idempotency_key = ?', (derived_key,))
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
                cursor.execute(
                    '''
                    SELECT id, message_uuid, topic, payload, qos, retain, retry_count,
                           available_at, created_at, source, correlation_id
                    FROM outbox_messages
                    WHERE status = 'pending' AND available_at <= ?
                    ORDER BY created_at ASC
                    LIMIT ?
                ''',
                    (now_ts, limit),
                )
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
                cursor.executemany(
                    '''
                    UPDATE outbox_messages
                    SET status = 'sent', sent_at = ?, last_error = NULL
                    WHERE id = ?
                ''',
                    [(sent_at, int(msg_id)) for msg_id in message_ids],
                )
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
                cursor.executemany(
                    '''
                    UPDATE outbox_messages
                    SET status = 'in_flight', available_at = ?, last_error = NULL
                    WHERE id = ? AND status = 'pending'
                ''',
                    [(now_ts, int(msg_id)) for msg_id in message_ids],
                )
                conn.commit()
        except Exception as e:
            self.logger.error(f"Outbox in_flight işaretleme hatası: {e}")

    @staticmethod
    def _retry_backoff_seconds(retry_count: int) -> int:
        """Exponential backoff: 1,2,4,... max 300 saniye."""
        return min(300, max(1, 2 ** max(0, retry_count)))

    def mark_outbox_failed(self, message_id: int, error_text: str, retry_count: int, max_retry_count: int = 20) -> bool:
        """Gönderim hatasında retry sayısını ve tekrar deneme zamanını güncelle."""
        try:
            next_retry_at = datetime.now().timestamp() + self._retry_backoff_seconds(retry_count)
            next_status = 'dead' if retry_count >= max_retry_count else 'pending'
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    '''
                    UPDATE outbox_messages
                    SET status = ?, retry_count = ?, available_at = ?, last_error = ?
                    WHERE id = ?
                ''',
                    (next_status, int(retry_count), next_retry_at, str(error_text), int(message_id)),
                )
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
                cursor.execute(
                    '''
                    UPDATE outbox_messages
                    SET status = 'pending',
                        available_at = ?,
                        last_error = COALESCE(last_error, 'requeued stale in_flight')
                    WHERE status = 'in_flight' AND available_at < ?
                ''',
                    (datetime.now().timestamp(), cutoff_ts),
                )
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
                cursor.execute(
                    '''
                    DELETE FROM outbox_messages
                    WHERE status = 'sent' AND sent_at IS NOT NULL AND sent_at < ?
                ''',
                    (cutoff_ts,),
                )
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
                rows.append(
                    (
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
                        sample.get('sample_count'),
                    )
                )

            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.executemany(
                    '''
                    INSERT INTO sensor_samples
                    (session_id, coil_id, sample_ts, temperature_c, magnetic_field_mt,
                     current_a, pwm_frequency_hz, pwm_duty_percent, payload, created_at,
                     coil_run_id, ambient_temp_c, phase, sample_count)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                    rows,
                )
                conn.commit()
                return len(rows)
        except Exception as e:
            # DENETIM P2: hata SESSIZCE 0 donuyordu ve cagiran bunu "yazacak satir yoktu"dan
            # AYIRT EDEMIYORDU → 'basarisizsa buffer'a geri koy' kurtarma yollari fiilen olu
            # kaliyor, seansin sensor/sicaklik telemetrisi kayboluyordu. Donus sozlesmesi
            # (int) KORUNDU (tum cagiranlar try/except icinde ve int bekliyor); ayirt
            # edilebilirlik cagiran tarafinda "pending vardi ama 0 yazildi" ile saglanir.
            # Kayip miktarini GORUNUR yap: sessiz kayip en kotu turden veri kaybidir.
            self.logger.error(
                "Sensor sample batch kaydetme hatasi (session_id=%s): %s — %d ORNEK YAZILAMADI.",
                session_id,
                e,
                len(samples or []),
            )
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

            # B-1.3: at-rest şifreleme YOKken kişi-tanımlayıcı PII'yi maskele (dedup öncesi de →
            # maskeli name/owner tutarlı eşleşir). Üretimde (SQLCipher) değerler AYNEN geçer.
            name = self._redact_pii(name)
            owner_name = self._redact_pii(owner_name)
            _owner_email = self._redact_pii(patient.get('owner_email') or None)
            _vet_contact = self._redact_pii(patient.get('vet_contact'))
            _veteriner = self._redact_pii(patient.get('veteriner'))
            _notes = self._redact_pii(patient.get('notes'))

            with self._get_connection() as conn:
                cursor = conn.cursor()

                existing_id = None
                if patient_uuid:
                    cursor.execute('SELECT id FROM patients WHERE patient_uuid = ?', (patient_uuid,))
                    row = cursor.fetchone()
                    if row:
                        existing_id = int(row['id'])
                else:
                    # name (+ owner_name) ile eslestir
                    if owner_name is not None:
                        cursor.execute(
                            'SELECT id FROM patients WHERE name = ? AND IFNULL(owner_name, "") = ? ORDER BY id LIMIT 1',
                            (name, owner_name),
                        )
                    else:
                        cursor.execute(
                            'SELECT id FROM patients WHERE name = ? AND owner_name IS NULL ORDER BY id LIMIT 1', (name,)
                        )
                    row = cursor.fetchone()
                    if row:
                        existing_id = int(row['id'])

                if existing_id is not None:
                    cursor.execute(
                        '''
                        UPDATE patients SET
                            patient_uuid = COALESCE(?, patient_uuid),
                            name = ?,
                            species = ?,
                            breed = ?,
                            age = ?,
                            weight_kg = ?,
                            owner_name = ?,
                            owner_email = COALESCE(?, owner_email),
                            vet_contact = ?,
                            veteriner = ?,
                            notes = ?,
                            updated_at = ?,
                            sync_status = 0
                        WHERE id = ?
                    ''',
                        (
                            patient_uuid,
                            name,
                            patient.get('species'),
                            patient.get('breed'),
                            patient.get('age'),
                            patient.get('weight_kg'),
                            owner_name,
                            _owner_email,
                            _vet_contact,
                            _veteriner,
                            _notes,
                            now_iso,
                            existing_id,
                        ),
                    )
                    conn.commit()
                    return existing_id

                cursor.execute(
                    '''
                    INSERT INTO patients
                    (patient_uuid, name, species, breed, age, weight_kg, owner_name,
                     owner_email, vet_contact, veteriner, notes, updated_at, sync_status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                ''',
                    (
                        patient_uuid,
                        name,
                        patient.get('species'),
                        patient.get('breed'),
                        patient.get('age'),
                        patient.get('weight_kg'),
                        owner_name,
                        _owner_email,
                        _vet_contact,
                        _veteriner,
                        _notes,
                        now_iso,
                    ),
                )
                conn.commit()
                return cursor.lastrowid
        except Exception as e:
            self.logger.error(f"Hasta upsert hatası: {e}")
            return None

    def start_coil_run(
        self,
        session_id: Optional[int],
        coil_id: int,
        *,
        frequency_hz: Optional[float] = None,
        duty_percent: Optional[float] = None,
        phase: Optional[float] = None,
        intensity_mt: Optional[float] = None,
        hw_type: Optional[str] = None,
        started_epoch: float,
    ) -> Optional[int]:
        """Bir bobinin calismaya basladigini kaydet. created_at=started_epoch.
        Geri donus: run_id (int) veya hata halinde None."""
        try:
            self._ensure_write_guardrail()
            started = float(started_epoch)
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    '''
                    INSERT INTO session_coil_runs
                    (session_id, coil_id, started_epoch, ended_epoch, duration_seconds,
                     frequency_hz, duty_percent, phase, intensity_mt, hw_type, created_at)
                    VALUES (?, ?, ?, NULL, NULL, ?, ?, ?, ?, ?, ?)
                ''',
                    (
                        session_id,
                        int(coil_id),
                        started,
                        frequency_hz,
                        duty_percent,
                        phase,
                        intensity_mt,
                        hw_type,
                        started,
                    ),
                )
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
                cursor.execute('SELECT started_epoch FROM session_coil_runs WHERE id = ?', (int(run_id),))
                row = cursor.fetchone()
                if not row or row['started_epoch'] is None:
                    self.logger.warning(f"end_coil_run: run_id {run_id} bulunamadi/started_epoch yok")
                    return
                started = float(row['started_epoch'])
                cursor.execute(
                    '''
                    UPDATE session_coil_runs
                    SET ended_epoch = ?, duration_seconds = ?
                    WHERE id = ?
                ''',
                    (ended, ended - started, int(run_id)),
                )
                conn.commit()
        except Exception as e:
            self.logger.error(f"Coil run bitirme hatası: {e}")

    def add_sensor_run_summary(
        self,
        coil_run_id: int,
        *,
        sample_count=None,
        temp_min=None,
        temp_max=None,
        temp_avg=None,
        current_avg=None,
        field_avg=None,
    ) -> None:
        """Bir bobin calismasinin sensor ozet istatistigini kaydet.
        coil_run_id UNIQUE oldugu icin INSERT OR REPLACE kullanilir (yeniden hesapta uzerine yazar)."""
        try:
            self._ensure_write_guardrail()
            now_ts = datetime.now().timestamp()
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    '''
                    INSERT OR REPLACE INTO sensor_run_summary
                    (coil_run_id, sample_count, temp_min, temp_max, temp_avg,
                     current_avg, field_avg, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                    (int(coil_run_id), sample_count, temp_min, temp_max, temp_avg, current_avg, field_avg, now_ts),
                )
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
                sets.append('started_epoch = ?')
                params.append(float(started_epoch))
            if ended_epoch is not None:
                sets.append('ended_epoch = ?')
                params.append(float(ended_epoch))
            if patient_id is not None:
                sets.append('patient_id = ?')
                params.append(int(patient_id))
            if not sets:
                return
            params.append(int(session_id))
            with self._get_connection() as conn:
                conn.execute('UPDATE treatment_sessions SET ' + ', '.join(sets) + ' WHERE id = ?', params)
                conn.commit()
        except Exception as e:
            self.logger.error(f"set_session_meta hatası: {e}")

    def set_session_parameter(
        self, session_id, parameter_name: str, parameter_value: str, parameter_unit: str = ''
    ) -> None:
        """Seansa tek bir parametre yaz (varsa GUNCELLE, yoksa EKLE) — idempotent.
        React seans-akisinda hasta meta-parametrelerini (orn. patient_owner_email)
        kaydetmek icin. Best-effort: hata seansi/donanimi DURDURMAZ."""
        try:
            self._ensure_write_guardrail()
            if not session_id or not parameter_name:
                return
            _pv = str(parameter_value)
            if parameter_name in self._PII_PARAM_NAMES:
                _pv = self._redact_pii(_pv)  # B-1.3: şifresiz DB'ye gerçek PII yazma
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'UPDATE session_parameters SET parameter_value = ?, parameter_unit = ? '
                    'WHERE session_id = ? AND parameter_name = ?',
                    (_pv, parameter_unit, int(session_id), parameter_name),
                )
                if cursor.rowcount == 0:
                    cursor.execute(
                        'INSERT INTO session_parameters '
                        '(session_id, parameter_name, parameter_value, parameter_unit) '
                        'VALUES (?, ?, ?, ?)',
                        (int(session_id), parameter_name, _pv, parameter_unit),
                    )
                conn.commit()
        except Exception as e:
            self.logger.error(f"set_session_parameter hatası: {e}")

    def get_session_coil_runs(self, session_id: int) -> List[Dict]:
        """Bir seansa ait bobin calismalarini rapor icin getir
        (coil_id, started/ended_epoch, duration, parametreler)."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    '''
                    SELECT id, session_id, coil_id, started_epoch, ended_epoch,
                           duration_seconds, frequency_hz, duty_percent, phase,
                           intensity_mt, hw_type, created_at
                    FROM session_coil_runs
                    WHERE session_id = ?
                    ORDER BY started_epoch ASC
                ''',
                    (session_id,),
                )
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
                cursor.execute(
                    '''
                    SELECT s.coil_run_id, s.sample_count, s.temp_min, s.temp_max,
                           s.temp_avg, s.current_avg, s.field_avg
                    FROM sensor_run_summary s
                    JOIN session_coil_runs r ON r.id = s.coil_run_id
                    WHERE r.session_id = ?
                ''',
                    (session_id,),
                )
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
                cursor.execute(
                    '''
                    SELECT coil_id, sample_ts, temperature_c, ambient_temp_c,
                           current_a, magnetic_field_mt, pwm_frequency_hz,
                           pwm_duty_percent, coil_run_id, sample_count
                    FROM sensor_samples
                    WHERE session_id = ?
                    ORDER BY sample_ts ASC
                ''',
                    (session_id,),
                )
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
