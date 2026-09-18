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

import contextlib
import gc
import os
import shutil
import sqlite3
import time

try:
    import keyring
except Exception:  # keyring opsiyonel
    keyring = None

_SERVICE = "PEMF_GUI"
_KEY_NAME = "sqlcipher_key"


@contextlib.contextmanager
def dict_satir_fabrikasi(conn):
    """`conn.row_factory`'yi GEÇİCİ olarak dict üreten fabrikaya çevirir; ÇIKIŞTA GERİ YÜKLER.

    ⚠️ DENETİM BULGUSU 2026-08-17 — HAVUZ BAĞLANTISI KİRLENMESİ. Üç ayrı yer (`denetim_oku`,
    `sync_worker._sync_patients`, `sync_worker._sync_sessions`) `conn.row_factory`'yi dict
    lambda'sına çevirip **geri yüklemiyordu**. Bağlantı HAVUZDAN gelir ve thread-başına YENİDEN
    KULLANILIR (kuşak yalnız migration/restore/close'da artar) → kirlenme **süreç ömrü boyunca**
    sürer ve kendini onarmaz.

    Ölçülen sonuçlar (uçtan uca):
      * `GET /api/audit/events` bir kez → `GET /api/settings/retention` sonsuza dek `pending: 0`
        → arayüzdeki KVKK onay bloğu (`pending > 0`) bir daha çizilmez → operatör geri dönüşsüz
        maskelemeyi ONAYLAYAMAZ (veri FAZLA-SAKLAMA).
      * `POST /api/support/bundle` bir kez → `POST /api/data/export` **ve** `/api/data/import`
        süreç boyunca **500** ("sorun yaşayınca destek paketi üret" → "yedekten dön" BLOKE).
      * `run_integrity_check` sağlam DB'yi `{'ok': False, 'details': ['0']}` raporlar.
    Sebep: dict fabrikası POZİSYONEL erişimi (`row[0]`) `KeyError: 0`'a çevirir.

    ⚠️ RESTORE DEĞERİ SABİTLENEMEZ: havuz bağlantıyı düz SQLite'ta `sqlite3.Row`, at-rest şifreli
    kurulumda `sqlcipher.Row` ile kurar. Bu yüzden ÖNCEKİ değer saklanıp aynen geri konur —
    `None`a sıfırlamak şifreli kurulumda `row["kolon"]` erişimlerini kırardı. (Depoda bunun
    geçici çözümü TESTTE vardı: `tests/test_prod_readiness_fixes.py` → `c.row_factory = None`.)

    Kilit: `tests/test_row_factory_havuz_kirlenmesi.py`.
    """
    onceki = conn.row_factory
    conn.row_factory = lambda c, r: {d[0]: r[i] for i, d in enumerate(c.description)}
    try:
        yield conn
    finally:
        conn.row_factory = onceki


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


def _kilit_direncli_tasi(src, dst, logger=None, deneme=24, bekleme_s=0.25) -> bool:
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

    ⚠️⚠️ BUTCE 0,75 sn -> 6 sn (2026-09-19, OLCULDU). Yukaridaki gerekce YALNIZ BU SURECIN
    kendi yetim SQLCipher tutamacini anlatiyor ve `gc.collect()` onu cozuyor. BASKA bir
    okuyucu varsa cozmuyor:

        deney: dosyada `open(db, "rb")` acikken karantinaya_al -> None
               -> cagiran RuntimeError firlatir -> BACKEND ACILMAZ

    SADECE OKUMA tutamaci bile yetiyor. Uründe tam bunu yapan bir daemon var:
    `api_server._daily_maintenance_loop` gunluk yedegi `shutil.copy2` ile aliyor, yani
    `pemf_treatment_history.db`yi ACIYOR. Anahtar uyusmazligi tam o ana denk gelirse
    tuglalasmayi ONLEMEK icin yazilan zarf tuglalastiriyordu — ilk 4 deneme (0,75 sn)
    kisa bir kopyalamayi bile beklemeye yetmiyor.

    24 x 0,25 sn = 6 sn: kucuk bir DB kopyasi buraya rahat sigar. Acilista en kotu
    durumda 6 sn gecikme, ACILMAMAKTAN kiyaslanamayacak kadar iyidir. Kalici bir
    okuyucu varsa yine duser ve hata mesaji operatore ne yapacagini soyler.

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


def _tasi_yeniden_dene(kaynak, hedef, denemeler=5, bekleme=0.2, logger=None):
    """`shutil.move`, Windows'ta GECICI kilitlere karsi sinirli yeniden-deneme ile.

    ⚠️ NEDEN: dosya tasima Windows'ta baska bir surec (virus tarayici, yedekleyici, indeksleyici
    ya da ayni anda kosan ikinci bir backend) dosyayi acik tuttugu anda `PermissionError`
    (WinError 32/5) ile duser. Bu ANLIK bir durumdur; 100-200 ms sonra genelde gecer.
    Bu depoda ayni sinif daha once yasandi (bkz. bellek `pemf-build-dll-kilidi-ve-sahte-cikis-kodu`:
    yetim mosquitto bir DLL'i kilitleyip derlemeyi dusurmustu).

    ⚠️ SINIRLI: sonsuz denemez. Kilit kalicysa cagiran GERI ALMA yapabilsin diye istisna yukselir.
    """
    son = None
    for i in range(max(1, denemeler)):
        try:
            shutil.move(kaynak, hedef)
            return
        except Exception as e:  # PermissionError ve akrabalari
            son = e
            if i + 1 < denemeler:
                # ⚠️ gc.collect(): OLCULEN kok neden. WinError 32'yi tutan sey cogu zaman
                # DIS bir surec degil, AYNI surecteki ARTIK BASVURULMAYAN ama henuz
                # toplanmamis bir sqlite/sqlcipher baglantisidir (ornegin onceki bir
                # TreatmentHistoryDB ornegi acikca close() edilmeden birakilmis).
                # CPython'da refcount sifirlanınca tutamak kapanir; `gc.collect()` dongusel
                # basvurulari da kirip kapanmayi TETIKLER. Beklemek tek basina yetmez —
                # kimse tutamagi birakmaz. (Olculdu 2026-09-13: tam suitte
                # `test_ikinci_acilis_yeniden_GOCMEZ` bu yuzden araliklarla dusuyordu.)
                gc.collect()
                time.sleep(bekleme * (i + 1))  # artan bekleme
    if logger:
        logger.warning("Dosya tasima %d denemede basarisiz: %s -> %s (%s)", denemeler, kaynak, hedef, son)
    raise son if son is not None else RuntimeError("tasima basarisiz")


def _kilidi_gevset(yol, logger=None):
    """ACL kilidini, SURECI CALISTIRAN HESABA da erisim verecek sekilde yeniden uygula.

    ⚠️ OLCULDU 2026-09-13 (urun, frozen EXE): `backend_service._harden_secret_file_acls`
    acilista `*.plain.bak` dosyalarini `keep_current_user=False` ile kilitliyor. Backend
    YUKSELTILMEMIS calisiyorsa (launcher ile baslatma) Administrators SID'i suzulur ve surec
    KENDI yazdigi yedegi acamaz; yarim-goc toparlamasi `[Errno 13] Permission denied` ile duser.
    `file_acl.lock_down_file`in docstring'i bu sinifi zaten "DENETIM P3 — sahada yasandi" diye
    kaydetmis; ayni kor nokta `.plain.bak`ta tekrar etti.

    Dosyanin SAHIBI her zaman ortulu WRITE_DAC tasir; yedegi yazan bizdik, bu yuzden kilidi
    gevsetebiliriz. Koruma KAYBOLMAZ: Users/Authenticated Users yine disarida kalir.
    """
    try:
        from utils.file_acl import lock_down_file

        return bool(lock_down_file(yol, keep_current_user=True))
    except Exception:
        if logger:
            logger.debug("ACL gevsetme denenemedi: %s", yol, exc_info=True)
        return False


#: Duz-metin yedegin emanete (escrow) alinip alinmayacagini belirleyen KANONIK bayrak.
DUZ_METIN_YEDEK_BAYRAGI = "PEMF_KEEP_PLAIN_BACKUP"
#: ESKI ad. 2026-09-15'e kadar `treatment_history_db.py` politikayi BU addan okuyordu.
DUZ_METIN_YEDEK_BAYRAGI_ESKI = "PEMF_KEEP_PLAIN_BAK"


def duz_metin_yedegi_emanete_al_mi(logger=None) -> bool:
    """`.plain.bak` emanete mi alinsin (True) yoksa guvenli-mi-silinsin (False)?

    ⚠️ BU FONKSIYON BIR ARIZADAN DOGDU (olculdu 2026-09-15). Goc kodu iki dosyaya
    kopyalanmisti ve kopyalar AYNI politikayi IKI FARKLI ortam degiskeninden okuyordu:

        database/sqlcipher_util.py        -> PEMF_KEEP_PLAIN_BACKUP  (hasta DB'si)
        database/treatment_history_db.py  -> PEMF_KEEP_PLAIN_BAK     (tedavi + AI gecmisi)

    Emanet isteyen bir operator bayragi set ettiginde IKI veritabanindan YALNIZ BIRI
    etkileniyordu; digeri sessizce duz-metin yedegi guvenli-siliyordu. Tersi de dogruydu:
    emaneti kapatmak isteyen biri yalniz birini kapatiyor, otekinin TUM PII'sinin duz-metin
    kopyasi diskte KALIYORDU. Hangisinin hangisi oldugu ne belgede ne log'da yaziliydi.
    Ustelik testler yalniz eski adi taniyordu — kanonik ad icin SIFIR kapi vardi.

    ⚠️ ESKI AD OKUNMAYA DEVAM EDER. Sahada `PEMF_KEEP_PLAIN_BAK=1` set etmis biri olabilir;
    sessizce yok saymak, emanet BEKLEYEN birinin tek geri-donus kopyasini siler. Gecis
    okumayi BIRAKARAK degil UYARARAK yapilir.

    ⚠️ VARSAYILAN "0" = GUVENLI-SIL ve bu bilincli bir sahip kararidir (denetim 2026-08-08):
    `.plain.bak` TUM duz-metin PII'yi tasir ve SQLCipher'i baypas eder; disk calinir,
    imajlanir ya da buluta senkronlanirsa at-rest garantisi COKER. Varsayilani "1" YAPMAYIN.

    Kapi: tests/test_duz_metin_yedek_bayragi_tek_ad.py
    """
    if os.getenv(DUZ_METIN_YEDEK_BAYRAGI, "0") == "1":
        return True
    if os.getenv(DUZ_METIN_YEDEK_BAYRAGI_ESKI, "0") == "1":
        if logger:
            logger.warning(
                "%s ESKI bir addir; %s kullanin. Eski ad su an icin okunmaya devam ediyor "
                "(emanet KORUNDU) ama ileride kaldirilabilir.",
                DUZ_METIN_YEDEK_BAYRAGI_ESKI,
                DUZ_METIN_YEDEK_BAYRAGI,
            )
        return True
    return False


def goc_sonrasi_yedek_politikasi(backup, logger=None, etiket="DB"):
    """Goc BASARIYLA bittikten sonra `.plain.bak` ile ne yapilacagini uygular.

    ⚠️ BU FONKSIYON UC AYRI AYRISMADAN DOGDU (olculdu 2026-09-15). Ayni politika iki
    dosyaya kopyalanmisti ve kopyalar UC yerden ayrismisti:

      1. BAYRAK ADI     : `PEMF_KEEP_PLAIN_BACKUP` (hasta DB) vs `PEMF_KEEP_PLAIN_BAK`
                          (tedavi DB) -> operator bayragi set edince IKI veritabanindan
                          YALNIZ BIRI etkileniyordu.
      2. ACL BASARISIZLIGI: tedavi DB fail-closed (guvenli-sil), hasta DB FAIL-OPEN
                          (korumasiz yedegi diskte BIRAKIYORDU) — daha hassas olan taraf
                          daha gevsekti.
      3. LOG SEVIYESI   : silme duserse tedavi DB `error` + "ELLE SILIN", hasta DB
                          `warning` + "elle sil onerilir".

    Ucu de tek tek bulundu; hicbiri denetimde gorunmuyordu. Bu fonksiyon, ayrisacak yer
    birakmamak icin var. Iki cagiran da BUNU cagirir; kendi kopyalarini YAZMAYIN.

    SOZLESME:
      · Emanet istenmiyorsa (varsayilan) -> GUVENLI-SIL (uzerine-yaz + fsync + unlink).
        Yalniz `unlink` icerigi diskte birakir, dosya kurtarma araclariyla geri gelir.
      · Emanet isteniyorsa -> ACL ile kilitle. Kilit TUTARSA sakla.
      · ⚠️ Kilit TUTMAZSA yine GUVENLI-SIL (FAIL-CLOSED). `lock_down_file` basarisizlikta
        FIRLATMAZ, `False` DONER (utils/file_acl.py) — donusu YOK SAYMAYIN. Korumasiz
        emanet, at-rest sifrelemesinin kendisini anlamsiz kilar.
      · ⚠️ Log yalnizca GERCEKTEN olani soyler: kilit tutmadiysa "ACL-kilitli" DENMEZ.

    `etiket`: log satirlarinda hangi veritabani oldugunu belirtir ("DB", "Tedavi DB").
    Kapilar: tests/test_escrow_acl_dusunce_fail_closed.py ·
             tests/test_duz_metin_yedek_bayragi_tek_ad.py
    """
    kilitlendi = False
    if duz_metin_yedegi_emanete_al_mi(logger):
        try:
            from utils.file_acl import lock_down_file

            kilitlendi = bool(lock_down_file(backup))
        except Exception:
            if logger:
                logger.warning(".plain.bak ACL kilidi hata verdi: %s", backup, exc_info=True)
        if kilitlendi:
            if logger:
                logger.warning(
                    "%s plaintext -> SQLCipher MIGRATE edildi; düz-metin yedek ESCROW saklandı (ACL-kilitli): %s",
                    etiket,
                    backup,
                )
            return True
        if logger:
            logger.warning(
                "ACL uygulanamadı → escrow'dan VAZGEÇİLDİ, güvenli-siliniyor: %s "
                "(korumasız escrow, at-rest şifrelemesini anlamsız kılar)",
                backup,
            )
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
                "%s plaintext -> SQLCipher MIGRATE edildi; düz-metin yedek GÜVENLİ-SİLİNDİ "
                "(at-rest PII riski kapatıldı).",
                etiket,
            )
    except Exception:
        # ⚠️ `error` SEVIYESI BILINCLI: diskte kalan sey TUM PII'nin korumasiz duz-metin
        # kopyasidir; bu bir "oneri" degil ZORUNLU islemdir.
        if logger:
            logger.error("KRİTİK: korumasız düz-metin yedek SİLİNEMEDİ → ELLE SİLİN: %s", backup, exc_info=True)
    return False


def _yedegi_kenara_al(backup, logger=None):
    """Var olan duz-metin yedegi SILME — zaman damgali bir ada TASI.

    ⚠️ BU SATIR VERI YOK EDIYORDU (olculdu 2026-09-13, urun): goc kodu yer-degistirme
    penceresine girmeden once `if os.path.exists(backup): os.remove(backup)` yapiyordu.
    Normalde `.plain.bak` goc kodunun KENDI biraz once yazdigi dosyadir, silmek zararsizdir.
    Ama YARIM GOC kalmissa `.plain.bak` kliniğin TEK veri kopyasidir ve toparlama (ACL kilidi
    yuzunden) dusmusse hala oradadir. O durumda bu `remove`, sablondan yeni bir DB yaratmadan
    hemen once hasta gecmisini GERI DONULMEZ sekilde siliyordu — sonra da yeni yedek "guvenli
    silindi" diye loglaniyordu; disaridan "veri kayboldu" bile denmiyordu.

    Artik hicbir sey silinmez: eski yedek `.plain.bak.<zaman>` olur ve diskte DURUR.
    """
    if not os.path.exists(backup):
        return
    damga = time.strftime("%Y%m%d_%H%M%S")
    kenar = f"{backup}.{damga}"
    i = 0
    while os.path.exists(kenar):
        i += 1
        kenar = f"{backup}.{damga}.{i}"
    try:
        _tasi_yeniden_dene(backup, kenar, logger=logger)
        if logger:
            logger.warning(
                "ONCEKI duz-metin yedek SILINMEDI, kenara alindi: %s -> %s. Yarim kalmis bir "
                "goc kaldiysa KLINIK VERISI BU DOSYADADIR.",
                backup,
                kenar,
            )
    except Exception:
        # Tasinamadiysa da SILME. Goc bu turda iptal olsun; veri yerinde kalsin.
        if logger:
            logger.error(
                "ONCEKI duz-metin yedek ne tasinabildi ne de silindi (%s) — goc IPTAL, veri yerinde BIRAKILDI.",
                backup,
            )
        raise


def _yarim_goc_toparla(db, logger=None):
    """ONCEKI yarim goc kaldiysa orijinali GERI KOY.

    ⚠️ Diskteki tehlikeli durum: `db` YOK + `db.plain.bak` VAR. Surec tam yer-degistirme
    penceresinde olduyse (elektrik, kill, kilit) boyle kalir. Toparlanmazsa bir sonraki acilis
    `os.path.exists(db)` False gorur, goc erken doner ve uygulama **YENI BOS** bir veritabani
    yaratir → klinik hasta gecmisini BOS gorur. Veri diskte durur ama kimse bakmaz.
    """
    yedek = db + ".plain.bak"
    if os.path.exists(db) or not os.path.exists(yedek):
        return False
    try:
        _tasi_yeniden_dene(yedek, db, logger=logger)
        if logger:
            logger.warning("Yarim kalmis goc toparlandi: duz-metin yedek geri konuldu (%s).", db)
        return True
    except Exception:
        # ⚠️ IKINCI SANS — ACL. Ilk yazimda burada pes ediyordum ve urunde HEP buraya
        # dusuyordu: acilis sirasi `_harden_secret_file_acls` -> toparlama oldugu icin yedek
        # zaten kilitlenmis oluyordu (Errno 13, kaynak dosyada). Sira duzeltildi, ama ESKI
        # surumlerin kilitledigi yedekler sahada duruyor — onlari da acabilmeliyiz.
        if not _kilidi_gevset(yedek, logger):
            if logger:
                logger.error("Yarim kalmis goc TOPARLANAMADI — veri %s dosyasinda duruyor.", yedek)
            return False
        try:
            _tasi_yeniden_dene(yedek, db, logger=logger)
        except Exception:
            if logger:
                logger.error(
                    "Yarim kalmis goc TOPARLANAMADI (ACL gevsetildi ama tasima yine dustu) — "
                    "veri %s dosyasinda duruyor.",
                    yedek,
                )
            return False
        if logger:
            logger.warning("Yarim kalmis goc toparlandi (ACL kilidi gevsetildikten sonra): %s.", db)
        return True


def migrate_to_encrypted_if_needed(db_path, app_data_dir, logger=None, etiket="DB"):
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
        # ⚠️ ONCE yarim kalmis bir goc var mi — VARSA orijinali geri koy. Bu, asagidaki
        # `os.path.exists(db)` erken-donusunden ONCE olmak ZORUNDA: aksi halde `db` yok
        # sayilir, goc atlanir ve uygulama BOS bir veritabani yaratir.
        _yarim_goc_toparla(db, logger)
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
        # ⚠️ SILME — KENARA AL. Eskiden `os.remove(backup)` idi ve yarim kalmis bir gocun
        # tek veri kopyasini yok ediyordu (bkz. `_yedegi_kenara_al`).
        _yedegi_kenara_al(backup, logger)
        # ══════════════════════════════════════════════════════════════════════════════
        # ⚠️ YER-DEGISTIRME PENCERESI — BURADA `db` BIR AN YOKTUR.
        # ══════════════════════════════════════════════════════════════════════════════
        # Iki ayri tasima var; ikincisi duserse `db` YOK, veri `.plain.bak`ta, sifreli kopya
        # `.enc.tmp`te kalir. Ustelik bu fonksiyonun tamami `except Exception` ile sarili ve
        # hatayi YUTAR → bir sonraki acilista uygulama BOS bir DB yaratir ve klinik hasta
        # gecmisini BOS gorur. Sessiz bir veri-erisilemezligi.
        #
        # Bu yuzden: ikinci tasima yeniden-denemeli, DUSERSE orijinal GERI KONUR ve goc
        # temiz sekilde iptal edilir (veri duz-metin olarak SAGLAM kalir; sonraki acilis
        # yeniden dener).
        _tasi_yeniden_dene(db, backup, logger=logger)
        try:
            _tasi_yeniden_dene(enc_tmp, db, logger=logger)
        except Exception:
            # GERI ALMA: orijinali yerine koy — `db`yi asla yok birakma.
            try:
                if not os.path.exists(db):
                    _tasi_yeniden_dene(backup, db, logger=logger)
            except Exception:
                if logger:
                    logger.error("GOC GERI ALINAMADI — veri %s dosyasinda duruyor, ELLE geri koyun.", backup)
                return
            try:
                if os.path.exists(enc_tmp):
                    os.remove(enc_tmp)
            except Exception:
                pass
            if logger:
                logger.warning(
                    "SQLCipher goc IPTAL (dosya kilidi): duz-metin veri yerinde KORUNDU; "
                    "sonraki aciliste yeniden denenecek."
                )
            return
        # op-doğrulama #8: .plain.bak TÜM eski düz-metin DB'yi içerir → SQLCipher'ı baypas eden PII
        # kopyası. Escrow (migration-kurtarma) için TUTULUR ama SIKI ACL (SYSTEM+Admin) ile kilitlenir
        # → yerel kullanıcı düz-metin PII okuyamaz (B-1.2 .sqlcipher_key escrow deseniyle tutarlı).
        # Audit P3: .plain.bak TÜM düz-metin PII'yi (SQLCipher-bypass) taşır → disk-çalınırsa/yedek/bulut-sync
        # okursa at-rest garantisi çöker. Migrasyon başarılı (enc DB yerinde) → VARSAYILAN GÜVENLİ-SİL
        # (üzerine-yaz + unlink). PEMF_KEEP_PLAIN_BACKUP=1 ile ACL-kilitli escrow saklanabilir (eski davranış).
        # ⚠️ KARAR TEK YERDEN GELİR (2026-09-15): `duz_metin_yedegi_emanete_al_mi`. Bayrak burada
        # doğrudan okunuyordu ve `treatment_history_db.py` BAŞKA bir ad okuyordu → operatör
        # bayrağı set ettiğinde iki DB'den yalnız biri etkileniyordu. Doğrudan okumaya DÖNMEYİN.
        # ⚠️ POLITIKA TEK YERDEN GELIR (2026-09-15): `goc_sonrasi_yedek_politikasi`.
        # Bu kuyruk `treatment_history_db.py` icine de KOPYALANMISTI ve iki kopya UC ayri
        # yerden ayrismisti (bayrak adi · ACL basarisizlik politikasi · log seviyesi).
        # Kendi kopyanizi YAZMAYIN — ayrisacak yer birakmamak icin ortak fonksiyon var.
        goc_sonrasi_yedek_politikasi(backup, logger, etiket=etiket)
    except Exception:
        if logger:
            logger.exception("SQLCipher migrate hatasi (duz-metin korunur)")
