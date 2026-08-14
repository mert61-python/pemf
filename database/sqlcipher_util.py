# Author: mertaygn, cglrgrkn
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
import shutil
import sqlite3

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
    # TEK-DOSYA: SecretsManager (keyring->env->.sqlcipher_key MİGRATE eder; tek dosyada DPAPI saklar).
    # Üretim YALNIZ PEMF_ENCRYPT_AT_REST=1 iken; MEVCUT anahtar HER ZAMAN migrate → mevcut şifreli DB okunabilir kalır.
    try:
        from utils.secrets_manager import get_secret

        _encrypt = os.getenv("PEMF_ENCRYPT_AT_REST", "0") == "1"
        _k = get_secret("sqlcipher_key", generate=_encrypt)
        if _k:
            return _k
        if not _encrypt:
            return ""  # şifreleme kapalı + mevcut anahtar yok → düz-metin
        # encrypt=True ama boş (üreteç hatası) → aşağıdaki eski yola düş
    except RuntimeError:
        # DENETIM P2 (brick korumasının deviril­mesi): SecretsManager, mevcut şifreli veriyi
        # korumak için BİLEREK RuntimeError yükseltir — "sır saklanmış ama ÇÖZÜLEMİYOR"
        # (DPAPI/makine değişmiş) ve "pemf_secrets.json BOZUK" durumlarında. Aşağıdaki geniş
        # `except Exception` bunu YUTUP eski yola düşüyordu; eski yol ise YENİ bir SQLCipher
        # anahtarı üretip keyring + .sqlcipher_key'e yazıyordu → mevcut patients.db /
        # pemf_treatment_history.db ve TÜM yedekler kalıcı olarak çözülemez hale geliyordu.
        # Tam da fail-closed korumasının önlemek için var olduğu sonuç. Yeniden yükselt:
        # backend açılmaz ama VERİ SAĞLAM kalır (operatör yedekten/doğru makineden döner).
        raise
    except Exception as _e:
        if logger:
            logger.warning(f"SecretsManager sqlcipher_key okunamadı, eski yola düşülüyor: {_e}")
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
    # DAYANIKLI DOSYA-YEDEGI: servis LocalSystem olarak kostugunda keyring, LocalSystem hesabinin
    # Credential Manager kasasina yazar -> operatore GORUNMEZ + servis hesabi degisirse / PC
    # tasinirsa KAYBOLUR. Bu yuzden keyring BASARILI olsa BILE anahtari ayrica dosyaya yaz:
    # yedeklenebilir ve hesaptan bagimsiz okunur (okuma yolu keyring->env->dosya sirasini zaten dener).
    keyfile_written = False
    try:
        keyfile.write_text(newkey, encoding="utf-8")
        # NTFS ACL kilidi: yalnız SYSTEM + Administrators okuyabilsin (audit B-1.2 — os.chmod
        # Windows'ta no-op'tu; anahtar dosyası Users'a açık kalıyordu). Escrow amacıyla dosya
        # KALIR ama artık kilitli. Best-effort.
        try:
            from utils.file_acl import lock_down_file

            lock_down_file(keyfile)
        except Exception:
            pass
        keyfile_written = True
    except Exception:
        pass
    if logger:
        logger.warning(
            "Yeni SQLCipher anahtari uretildi (keyring=%s, dosya-yedek=%s @ %s). "
            "BU ANAHTARI YEDEKLEYIN — kaybolursa sifreli hasta verisi KALICI OKUNAMAZ.",
            stored,
            keyfile_written,
            keyfile,
        )
    return newkey


def open_encrypted_conn(db_path, key, sqlcipher_mod, row_factory=None, timeout=10.0, check_same_thread=False):
    """Onceden cozulmus anahtar + binding ile SQLCipher baglantisi ac (PRAGMA key).

    ⚠️ HATA YOLUNDA BAGLANTI SIZDIRILMAZ. Yanlis anahtarda `SELECT ... sqlite_master` patlar;
    eskiden acik `conn` oylece birakiliyordu. Windows'ta o tutamak DOSYAYI KILITLER → sonraki
    karantina `shutil.move`u PermissionError ile duser ve cihaz yine acilmaz (yani tuglalasma
    korumasi tam da ihtiyac duyulan anda calismaz). Bu yuzden hata halinde KAPAT ve yeniden firlat.
    """
    conn = sqlcipher_mod.connect(str(db_path), check_same_thread=check_same_thread, timeout=timeout)
    try:
        if row_factory is not None:
            conn.row_factory = row_factory
        escaped = key.replace("'", "''")
        conn.execute(f"PRAGMA key='{escaped}'")
        conn.execute("SELECT count(*) FROM sqlite_master")  # yanlis anahtar/migrate gerekli ise burada patlar
        return conn
    except Exception:
        try:
            conn.close()
        except Exception:
            pass
        raise


# ── ANAHTAR UYUSMAZLIGI: CIHAZI TUGLALASTIRMA ────────────────────────────────────────────────
# SAHA HATASI (2026-08-11). Kullanici PEMF'i kaldirip yeniden kurdu. `patients.db` KVKK geregi
# KORUNUR, ama `pemf_secrets.json` yeniden uretilince at-rest anahtari degisti → SQLCipher
# "file is not a database" atti → `_init_database` RuntimeError → **backend cikis kodu 1 ile oldu.**
# Launcher'da gorulen tek sey 59 SAAT once yazilmis bayat bir gunluktu; kullanici cihazi bir daha
# hic acamadi ve sebebini gormesinin YOLU YOKTU (backend stderr'i launcher'da Stdio::null'a gider —
# bu, 1.9.5'teki deadlock duzeltmesidir, geri alinamaz).
#
# TASARIM KARARI — neden otomatik karantina:
#   Anahtar GITTIYSE veri zaten KALICI OKUNAMAZ. Cihazi calismaz halde tutmak veriyi kurtarmaz,
#   yalnizca klinigi cihazsiz birakir. Bu yuzden dosya KENARA ALINIR (yeniden adlandirilir) ve
#   temiz bir DB olusur. **ASLA SILINMEZ** — anahtar sonradan bulunursa (yedekten) geri donulebilir.
#
# ⚠️ KARANTINA YALNIZ ANAHTAR *OKUNABILDI AMA UYMUYOR* ISE. Anahtar hic okunamadiysa (DPAPI/keyring
# gecici hatasi, profil bozulmasi) hata GECICI olabilir ve dosyayi kenara almak KURTARILABILIR
# hasta verisini yetim birakir. O durumda hata yukari firlar — cagiran tugla kalir ama VERI DURUR.
_QUARANTINE_SUFFIX = "acilamadi"


def anahtar_uyusmazligi_mi(exc: BaseException) -> bool:
    """Istisna 'bu dosya bu anahtarla acilmiyor' anlamina mi geliyor?

    SQLCipher yanlis anahtarda sifre cozemedigi icin dosyayi SQLite gibi bile goremez ve
    `DatabaseError: file is not a database` atar. Disk bozulmasi da ayni mesaji verebilir;
    ikisinde de tek guvenli davranis ayni (kenara al, yeni DB ac), o yuzden ayirmiyoruz."""
    return "file is not a database" in str(exc).lower()


def _kilit_direncli_tasi(src, dst, logger=None, deneme=4, bekleme_s=0.25) -> bool:
    """Dosyayi kenara al; Windows'ta ORPHAN tutamac yuzunden kilitliyse GC ile serbest birakip yeniden dene.

    ⚠️ NEDEN (saha, 2026-08-14 — CIHAZ HIC ACILMIYORDU): at-rest anahtari DB'ye uymadiginda
    kurtarma zarfi dosyayi karantinaya alip TEMIZ bir DB ile acilmayi surduruyor. Ama karantina
    `[WinError 32] dosya baska bir islem tarafindan kullaniliyor` ile dusuyordu ve cagiran bunu
    "karantina ALINAMADI" sayip RuntimeError firlatiyordu → backend ACILMIYORDU. Yani tuglalasmayi
    ONLEMEK icin yazilmis zarfin kendisi tuglalasmaya sebep oluyordu.

    Kilidi tutan BASKA bir surec DEGIL, bu surecteki basarisiz SQLCipher baglanti nesneleridir:
    aday-anahtar dongusu `close()` cagiriyor, fakat acilamayan bir SQLCipher baglantisinda alttaki
    dosya tutamaci nesne TOPLANANA kadar serbest kalmiyor. Bu yuzden yeniden denemeden once
    `gc.collect()` cagirmak gerekiyor — bekleme tek basina yetmez.

    Doner: tasindiysa True.
    """
    import gc
    import time

    son_hata = None
    for i in range(deneme):
        try:
            shutil.move(src, dst)
            if i and logger:
                logger.warning("KARANTINA: %s ancak %d. denemede tasinabildi (tutamac gec birakildi).", src, i + 1)
            return True
        except Exception as e:
            son_hata = e
            gc.collect()  # yetim baglanti nesnelerini kapat → tutamac serbest kalsin
            time.sleep(bekleme_s)
    if logger:
        logger.error("KARANTINA BASARISIZ (%s), %d deneme: %s", src, deneme, son_hata)
    return False


def karantinaya_al(db_path, logger=None, zaman_damgasi=None):
    """Acilamayan DB'yi (ve -wal/-shm yoldaslarini) KENARA AL. Silme YOK.

    Doner: yeniden adlandirilan ana dosyanin yolu (str) ya da None (dosya yoksa/tasinamadiysa).
    """
    import datetime

    db = str(db_path)
    if not os.path.exists(db):
        return None
    ts = zaman_damgasi or datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    tasinan = None
    # WAL/SHM de tasinmali: geride kalan -wal, YENI ve bos DB'ye uygulanmaya calisilir → bozulma.
    for suffix in ("", "-wal", "-shm"):
        src = db + suffix
        if not os.path.exists(src):
            continue
        dst = f"{src}.{_QUARANTINE_SUFFIX}-{ts}"
        if not _kilit_direncli_tasi(src, dst, logger):
            return None  # gercekten tasinamadi → cagiran hatayi gormeli
        if suffix == "":
            tasinan = dst
    if logger:
        logger.error(
            "VERITABANI ACILAMADI — at-rest anahtari bu dosyaya UYMUYOR. Dosya KENARA ALINDI "
            "(SILINMEDI): %s . Temiz bir veritabani olusturuluyor, cihaz calismaya devam eder. "
            "SEBEP: kaldirma/yeniden kurulum sirasinda sir dosyasi (pemf_secrets.json) yenilenmis "
            "olabilir. ESKI ANAHTARINIZ VARSA bu dosyayi geri adlandirip anahtari yerine koyun; "
            "yoksa icerigi KALICI OKUNAMAZ.",
            tasinan,
        )
    return tasinan


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
        # op-doğrulama #8: .plain.bak TÜM eski düz-metin DB'yi içerir → SQLCipher'ı baypas eden PII
        # kopyası. Escrow (migration-kurtarma) için TUTULUR ama SIKI ACL (SYSTEM+Admin) ile kilitlenir
        # → yerel kullanıcı düz-metin PII okuyamaz (B-1.2 .sqlcipher_key escrow deseniyle tutarlı).
        # Audit P3: .plain.bak TÜM düz-metin PII'yi (SQLCipher-bypass) taşır → disk-çalınırsa/yedek/bulut-sync
        # okursa at-rest garantisi çöker. Migrasyon başarılı (enc DB yerinde) → VARSAYILAN GÜVENLİ-SİL
        # (üzerine-yaz + unlink). PEMF_KEEP_PLAIN_BACKUP=1 ile ACL-kilitli escrow saklanabilir (eski davranış).
        if os.environ.get("PEMF_KEEP_PLAIN_BACKUP", "0") == "1":
            try:
                from utils.file_acl import lock_down_file

                lock_down_file(backup)
            except Exception:
                if logger:
                    logger.warning(".plain.bak ACL kilidi uygulanamadi (elle icacls onerilir): %s", backup)
            if logger:
                logger.warning("DB SQLCipher MIGRATE edildi; düz-metin yedek ESCROW saklandı (ACL-kilitli): %s", backup)
        else:
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
                if logger:
                    logger.warning(
                        "DB SQLCipher MIGRATE edildi; düz-metin yedek GÜVENLİ-SİLİNDİ (at-rest PII riski kapatıldı)."
                    )
            except Exception:
                if logger:
                    logger.warning(".plain.bak güvenli-silinemedi (elle sil önerilir): %s", backup)
    except Exception:
        if logger:
            logger.exception("SQLCipher migrate hatasi (duz-metin korunur)")
