# Author: mertaygn, cglrgrkn
"""
SQLCipher at-rest sifreleme yardimcilari (paylasilan).

patient_database.py + treatment_history_db.py ayni at-rest anahtarini (SecretsManager:
<veri koku>/pemf_secrets.json -> auto.sqlcipher_key, DPAPI ile makineye bagli; keyring / .sqlcipher_key
yalniz ESKI kaynak olarak bir kez okunup oraya tasinir — D6.09) ve ayni plaintext->encrypted goc
GOVDESINI kullanir.
PEMF_ENCRYPT_AT_REST=1 + sqlcipher3 binding varsa whole-DB sifreleme; aksi halde duz-metin
(geriye uyumlu). [audit 2026-06-28 P0: hasta PII whole-DB sifrelenmeli — patient_database
eskiden duz sqlite3 + yalniz alan-Fernet idi; metadata/HMAC-index duz-metin kaliyordu.]

NOT (D6.10 · B-3.54): goc govdesi TEK ve BURADA (`migrate_to_encrypted_if_needed`). Tedavi DB'si kendi
kopyasini TASIMAZ: `thdb_sema.SemaKarisimi._migrate_to_encrypted_if_needed` buraya delege eder (2026-09-15,
A1 · 2/2 — 157 satirlik ikinci kopya kaldirildi); hasta DB'si (`patient_database`) de dogrudan bunu cagirir.
Anahtar ADI ayni oldugundan ayni anahtar paylasilir. `database/yedek_dosyasi.py` de `sqlcipher_export`
cagirir ama goc icin DEGIL — yedek sifreleme / cozme (`duz_dbyi_yedekle`, `sifreli_yedegi_duze_coz`);
MESRU ikinci cagirandir.
Kapilar: tests/test_goc_yarim_kalirsa_db_kaybolmaz.py · tests/test_sqlcipher_goc_govdesi_belgesi_D6_10.py
"""

import contextlib
import gc
import logging
import os
import shutil
import sqlite3
import threading
import time


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
    """At-rest anahtarı TEK kaynaktan: SecretsManager (`pemf_secrets.json`; kritik → DPAPI/MKEY). Eski kaynakları
    (keyring → PEMF_SQLCIPHER_KEY → <veri kökü>/.sqlcipher_key) SecretsManager'ın `legacy` göçü okur. Anahtar yoksa
    YALNIZ PEMF_ENCRYPT_AT_REST=1 iken SecretsManager üretir (diske yazdıktan SONRA döner); aksi '' (düz-metin).

    ⚠️ D2.45 (B-3.51 · B-3.5 · Karar 6 · Y9): SecretsManager sırrı OKUYAMAZ ya da YAZAMAZSA (bozuk/çözülemeyen sır,
    izin, G-Ç, başka Windows hesabına kilitli veri kökü) FAIL-CLOSED: eski yola düşülmez, YENİ ANAHTAR ÜRETİLMEZ,
    sebep loglanır ve `RuntimeError` yükselir → backend DB'siz kısıtlı kipte açılır (ACİL DURDUR + açılış STOP
    mutabakatı çalışır, DB uçları 503, DB arka planda yeniden açılmaya çalışılır — Y43). Eskiden `RuntimeError`
    dışındaki her hata eski yola düşüyor, orada YENİ anahtar üretilip keyring + `.sqlcipher_key`e yazılıyordu →
    mevcut şifreli DB'ler o anahtarla AÇILMIYOR, aynı süreçte iki anahtar dolaşıyordu (karantina, yeniden başlatmada
    0 hasta — ölçüldü). `app_data_dir` imza uyumu için durur: anahtarın konumu SecretsManager'ın veri köküdür.
    Kapı: tests/test_anahtar_yolu_FAIL_CLOSED_Karar6_D245.py."""
    _encrypt = os.getenv("PEMF_ENCRYPT_AT_REST", "0") == "1"
    try:
        from utils.secrets_manager import get_secret

        return get_secret("sqlcipher_key", generate=_encrypt) or ""
    except RuntimeError:
        # DENETIM P2 (brick korumasının devrilmesi): SecretsManager, mevcut şifreli veriyi korumak için BİLEREK
        # RuntimeError yükseltir — "sır saklanmış ama ÇÖZÜLEMİYOR" (DPAPI/makine değişmiş), "pemf_secrets.json BOZUK"
        # ve "karantina kanıtı var" durumlarında; sebebi kendisi loglar. Yutulursa yeni anahtar üretilir ve mevcut
        # patients.db / pemf_treatment_history.db ile TÜM yedekler kalıcı olarak çözülemez hale gelir.
        raise
    except Exception as e:
        _gunluk = logger or logging.getLogger(__name__)
        _ileti = (
            "SQLCipher anahtari SecretsManager'dan OKUNAMADI/YAZILAMADI (%s: %s) — eski yola DUSULMEDI, YENI ANAHTAR "
            "URETILMEDI; veritabani acilmayacak, dosyalara dokunulmadi (Karar 6). Sir dosyasina/veri kokune erisimi "
            "duzeltin; veritabani arka planda yeniden acilir."
        )
        try:
            # O-A2-1.b (D2.80): her açılış denemesinde (Y43) aynı satır — tekrar-kısıtlı (ilk satır + sayım).
            from utils.secrets_manager import tekrar_kisitli_hata

            tekrar_kisitli_hata(_gunluk, "sqlcipher_key", f"{type(e).__name__}: {e}", _ileti, type(e).__name__, e)
        except ImportError:
            _gunluk.error(_ileti, type(e).__name__, e)
        raise RuntimeError(
            f"SQLCipher anahtari okunamadi/yazilamadi ({type(e).__name__}) — yeni anahtar URETILMEDI, eski yola "
            "dusulmedi (Karar 6)."
        ) from e


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


#: ⚠️ TEK KAYNAK — Windows gecici dosya kilidi butcesi.
#: 2026-09-19'da `_kilit_direncli_tasi` 6 sn'ye cikarildi ama `_tasi_yeniden_dene`
#: 2 sn'de KALDI ve goc yolu KIRILMAYA DEVAM ETTI (tam suit kosum 4'te olculdu:
#: `os.remove(enc_tmp)` WinError 32 -> tasima 5 denemede dustu -> goc iptal ->
#: cagiran duz-metin DB'yi karantinaya aldi -> "goc sirasinda SEANS kayboldu").
#: Ikisi de ARTIK BURAYI okur. Kapi: tests/test_kilit_butcesi_TEK_KAYNAK.py
_KILIT_BEKLEME_SN = 0.25
_KILIT_BUTCESI_SN = 6.0
_KILIT_DENEME = int(_KILIT_BUTCESI_SN / _KILIT_BEKLEME_SN)  # 24


def _kilit_direncli_sil(yol, logger=None) -> bool:
    """`os.remove`, gecici Windows kilidine karsi AYNI butceyle yeniden-denemeli.

    ⚠️ NEDEN VAR: goc yolundaki `os.remove(enc_tmp)` HIC korumasizdi ve olculen
    arizanin BASLATICISI oydu. Tasima yardimcilari 6 sn bekliyordu; hemen oncesindeki
    silme ise ilk `PermissionError`da dusuyordu — zincirin en zayif halkasi.

    Donus: silindi mi (dosya zaten yoksa True).
    """
    yol = str(yol)
    for i in range(_KILIT_DENEME):
        if not os.path.exists(yol):
            return True
        try:
            os.remove(yol)
            return True
        except Exception as e:  # PermissionError ve akrabalari
            if i + 1 >= _KILIT_DENEME:
                if logger:
                    logger.warning("Dosya silinemedi (%.1f sn denendi): %s (%s)", _KILIT_BUTCESI_SN, yol, e)
                return False
            # gc.collect(): AYNI surecteki toplanmamis sqlite tutamagi olabilir.
            gc.collect()
            time.sleep(_KILIT_BEKLEME_SN)
    return False


def _kilit_direncli_tasi(src, dst, logger=None, deneme=_KILIT_DENEME, bekleme_s=_KILIT_BEKLEME_SN) -> bool:
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

    SADECE OKUMA tutamaci bile yetiyor. Anahtar uyusmazligi tam bir okuma anina denk gelirse
    tuglalasmayi ONLEMEK icin yazilan zarf tuglalastiriyordu — ilk 4 deneme (0,75 sn) kisa bir
    okumayi bile beklemeye yetmiyor.

    ⚠️ D6.07 · B-4.22: bu gerekce 2026-09-19'da sucluyu `api_server._daily_maintenance_loop`un
    gunluk dosya kopyasi olarak gosteriyordu; o kopyalayici KALDIRILDI (yedegi artik
    `services/headless_db_maintenance` → `create_backup` alir: surec ici online backup API,
    dosyayi ayrica acan bir kopyalama yok). Karantina DB nesnesi KURULURKEN (`_init_database`) kosar; o anda
    dosyayi tutabilecek okuyucu surec DISINDANDIR: antivirus taramasi, dosya yedekleyici /
    indeksleyici, ikinci bir backend ornegi ya da elle acilmis bir DB goruntuleyicisi. Butce
    onlar icin KORUNUR. Kapi: tests/test_belge_capalari_ve_yedek_iddiasi_D6_07.py

    24 x 0,25 sn = 6 sn: kisa bir dis okuma buraya rahat sigar. Acilista en kotu
    durumda 6 sn gecikme, ACILMAMAKTAN kiyaslanamayacak kadar iyidir. Kalici bir
    okuyucu varsa yine duser ve hata mesaji operatore ne yapacagini soyler.

    ⚠️ Y97 (O-2A.1): KOPYASIZ taşıma (D2.47 deseni). `shutil.move`un `copy2` geri dönüşü kilitli kaynakta her denemede
    hedefe TAM bir kopya yazıyor, kaynağı silemiyordu → "KARANTINA BASARISIZ" denirken diskte `.acilamadi-*` kopyası
    duruyordu (ölçüldü). Karantina aynı dizinde yeniden adlandırmadır; kilit kalıcıysa taşıma düşer, dosya yerinde kalır.
    Kapı: tests/test_karantina_KOPYASIZ_tasima_Y97.py.

    Doner: tasindiysa True.
    """
    import gc
    import time

    son_hata = None
    for i in range(deneme):
        try:
            shutil.move(src, dst, copy_function=_kopya_yazma)
            if i and logger:
                logger.warning("KARANTINA: %s ancak %d. denemede tasinabildi (tutamac gec birakildi).", src, i + 1)
            return True
        except Exception as e:
            son_hata = e
            gc.collect()  # yetim baglanti nesnelerini kapat → tutamac serbest kalsin
            time.sleep(bekleme_s)
    if logger:
        logger.error(
            "KARANTINA BASARISIZ (%s): %d denemede yeniden adlandirilamadi (%s) — dosya YERINDE birakildi, "
            "KOPYA YAZILMADI. Dosyayi acik tutan sureci (virus tarayici/yedekleyici/ikinci backend) kapatip yeniden deneyin.",
            src,
            deneme,
            son_hata,
        )
    return False


class GocBekliyorHatasi(RuntimeError):
    """Dosya DUZ-METIN ve at-rest gocu henuz tamamlanmadi — anahtar uyusmazligi DEGIL.

    ⚠️ SAHIP KARARI 2026-09-20. Eskiden bu durum da karantinaya gidiyordu: dosya
    `.acilamadi-TARIH` olarak yeniden adlandirilip YERINE BOS SEMA kuruluyordu
    (`_semayi_kur`). Yani yeni seanslar BOS DB'ye yazilmaya baslar ve kurtarma
    "geri adlandir" degil BIRLESTIRME isine donerdi.

    Oysa bu bir anahtar uyusmazligi degil, "goc henuz olmadi" durumudur ve gocun
    kendi mesaji da "sonraki aciliste yeniden denenecek" der. Dogru davranis:
    DOSYAYA DOKUNMA, ACMA, cagirana haber ver. Sonraki acilis gocu yeniden dener
    ve basarili olunca TUM gecmis kendiliginden geri gelir.

    ⚠️ Bu istisna `RuntimeError` turevidir: mevcut `except Exception` sarmallari
    (ornegin `api_server._get_treatment_db`, `backend_service._initialize_database_safe`)
    onu zaten yakalar → CIHAZ ACILMAYA DEVAM EDER, yalniz tedavi DB'si o oturumda yok.
    """


class EskiKokGocuBekliyorHatasi(GocBekliyorHatasi):
    """Y200 (sahip · S-D3I.1) / D3.37 · Y10: ESKI KOK gocu (`%APPDATA%\\PEMF_GUI` → `PEMF_DATA_DIR`) bu DB'yi tasiyamadi ya da
    dogrulayamadi (`utils.path_utils.goc_engelini_denetle`) — hedefte BOS DB KURULMAZ. `GocBekliyorHatasi` turevi: ayni kisitli kip
    (ACIL DURDUR + STOP calisir), ayni yakalayicilar; yalniz operator iletisi (`headless_core.db_acilis_metni` "eskiKok") at-rest
    gocunun degil eski kok gocunun cikis yolunu soyler."""


#: SQLite dosya basligi. SQLCipher ile sifrelenmis dosyada BU BULUNMAZ (ilk sayfa da sifrelidir).
_SQLITE_BASLIK = b"SQLite format 3\x00"


def duz_metin_sqlite_mi(db_path) -> bool:
    """Dosya SIFRESIZ, okunabilir bir SQLite veritabani mi?

    IKI kosul da aranir:
      1. Dosya basligi `SQLite format 3\0` — sifreli dosyada yoktur.
      2. `sqlite3` ile acilip `sqlite_master` okunabiliyor.

    ⚠️ BASLIK KONTROLU TEK BASINA YETMEZ ama SART: bos (0 bayt) bir dosyayi
    `sqlite3.connect` SORUNSUZ acar ve `sqlite_master` BOS doner — istisna ATMAZ.
    O yuzden basliksiz dosya (bos/bozuk/sifreli) buradan False doner ve normal
    karantina yolu isler.
    """
    db = str(db_path)
    try:
        with open(db, "rb") as fh:
            if fh.read(len(_SQLITE_BASLIK)) != _SQLITE_BASLIK:
                return False
    except OSError:
        return False
    c = None
    try:
        c = sqlite3.connect(db)
        c.execute("SELECT count(*) FROM sqlite_master").fetchone()
        return True
    except Exception:
        return False
    finally:
        # ⚠️ `_close` modul duzeyinde DEGIL (migrate_to_encrypted_if_needed icinde ic-fonksiyon).
        # Tutamak MUTLAKA kapanmali: acik kalirsa Windows'ta bir sonraki tasima/silme
        # WinError 32 ile duser — bu dosyanin konusu olan arizanin ta kendisi.
        if c is not None:
            try:
                c.close()
            except Exception:
                pass


def sifreli_gorunur_mu(db_path) -> bool:
    """Dosya VAR, en az başlık boyunda ve `SQLite format 3` başlığı TAŞIMIYOR → şifreli (ya da başlığı bozuk). Okuma hatası → False.
    O-A2-2.a: anahtar YOKKEN açılamayan dosyanın iletisini seçmek için (davranışı DEĞİŞTİRMEZ)."""
    try:
        with open(str(db_path), "rb") as fh:
            bas = fh.read(len(_SQLITE_BASLIK))
    except OSError:
        return False
    return len(bas) == len(_SQLITE_BASLIK) and bas != _SQLITE_BASLIK


def anahtarsiz_sifreli_iletisi(logger, db_path) -> None:
    """O-A2-2.a (2-A incelemesi): at-rest anahtarı YOKKEN şifreli görünen dosya — eskiden yalnız "file is not a database" yazılıyordu,
    operatör dosyayı bozuk sanıp silebilirdi (hafıza "Hata mesajı EYLEM söylesin"). Dosyaya DOKUNULMAZ; ileti yalnız EYLEMİ söyler.
    Günlük satırıdır (kullanıcı metni değil); hangi DB olduğu dosya adından okunur."""
    logger.error(
        "Veritabani %s SIFRELI gorunuyor (SQLite basligi yok) ama at-rest anahtari YOK — sir dosyasi kayip ya da yenilenmis olabilir. "
        "Dosya KARANTINAYA ALINMADI, DOKUNULMADI: %s . YAPILACAK: sir dosyasini kurtarma zarfi + kurtarma koduyla geri yukleyin "
        "(PEMF_Backend.exe --kurtarma --zarf <zarf> --kod <kod>) ve yeniden baslatin; dosyayi SILMEYIN.",
        os.path.basename(str(db_path)),
        db_path,
    )


def karantinaya_al(db_path, logger=None, zaman_damgasi=None):
    """Acilamayan DB'yi (ve -wal/-shm yoldaslarini) KENARA AL. Silme YOK.

    Doner: yeniden adlandirilan ana dosyanin yolu (str) ya da None (dosya yoksa/tasinamadiysa).
    """
    import datetime

    db = str(db_path)
    if not os.path.exists(db):
        return None
    # ⚠️ SAHIP KARARI 2026-09-20 — DUZ-METIN DOSYA KARANTINAYA ALINMAZ.
    # Goc gecici bir dosya kilidi yuzunden iptal olduysa dosya SIFRESIZ kalir ve
    # at-rest anahtariyla acilamaz. Bu bir anahtar UYUSMAZLIGI degildir; karantina
    # burada veriyi `.acilamadi-*` altina itip YERINE BOS SEMA kurar ve yeni seanslar
    # oraya yazilir (kurtarma = birlestirme). Bkz. GocBekliyorHatasi.
    if duz_metin_sqlite_mi(db):
        if logger:
            logger.error(
                "Tedavi/hasta DB'si DUZ-METIN: at-rest gocu henuz tamamlanmadi (gecici dosya "
                "kilidi olabilir). Dosya KARANTINAYA ALINMADI ve DOKUNULMADI: %s . "
                "YAPILACAK: cihazi yeniden baslatin — goc yeniden denenecek ve gecmis geri gelecek. "
                "Tekrarlarsa dosyayi kilitleyen sureci (virus tarayici/yedekleyici/ikinci backend) arayin.",
                db,
            )
        raise GocBekliyorHatasi(f"DB duz-metin, at-rest gocu bekliyor (karantina YAPILMADI): {db}")
    ts = zaman_damgasi or datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    tasinan = None
    tasinanlar = []  # (kaynak, hedef) — başarıyla kenara alınanlar (kısmi karantinada geri alınır)
    # WAL/SHM de tasinmali: geride kalan -wal, YENI ve bos DB'ye uygulanmaya calisilir → bozulma.
    for suffix in ("", "-wal", "-shm"):
        src = db + suffix
        if not os.path.exists(src):
            continue
        dst = f"{src}.{_QUARANTINE_SUFFIX}-{ts}"
        if not _kilit_direncli_tasi(src, dst, logger):
            # ⚠️ D2.46 (B-3.53): KISMİ karantina GERİ ALINIR. Eskiden ana dosya karantinada, `-wal` yerinde kalıp
            # yalnız None dönülüyordu → sonraki açılış ana dosyayı YOK görüp BOŞ DB kuruyor, yetim `-wal` ona
            # uygulanmaya çalışılıyordu (ölçüldü). Kapı: tests/test_karantina_YALNIZ_gercek_uyusmazlikta_D246.py.
            _kismi_karantinayi_geri_al(tasinanlar, src, dst, logger)
            return None  # gercekten tasinamadi → cagiran hatayi gormeli
        tasinanlar.append((src, dst))
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


def _kismi_karantinayi_geri_al(tasinanlar, dusen_kaynak, dusen_hedef, logger=None) -> bool:
    """D2.46 (B-3.53): karantinada bir dosya taşınamayınca ÖNCEDEN taşınanları ters sırayla yerine koyar.

    Silme YOK: taşınamayan dosyanın `copy2` geri dönüşüyle hedefte kalmış yarım/tam KOPYASI (özgünü yerinde) adıyla
    loglanır, dokunulmaz (A-08 ilkesi). Geri taşıma da düşerse ELLE KURTARMA yönergesi (hangi dosya nereye) loglanır.
    Döner: her şey yerine kondu mu."""
    kalan = [(s, d) for s, d in reversed(tasinanlar) if not _kilit_direncli_tasi(d, s, logger)]
    yarim_kopya = dusen_hedef if os.path.exists(dusen_hedef) else None
    _log = logger or logging.getLogger(__name__)
    if kalan:
        _log.error(
            "KISMI KARANTINA geri ALINAMADI: %s tasinamadi ve onceden kenara alinan dosya(lar) yerine KONAMADI. "
            "ELLE KURTARMA: %s . Yarim kopya: %s . Veritabani bu dosyalar yerine konmadan ACILMAMALI.",
            dusen_kaynak,
            "; ".join(f"'{d}' dosyasini '{s}' adina geri tasiyin" for s, d in kalan),
            yarim_kopya or "yok",
        )
        return False
    _log.error(
        "KISMI KARANTINA GERI ALINDI: %s tasinamadi; onceden kenara alinan %d dosya yerine kondu, veritabanina "
        "DOKUNULMADI.%s",
        dusen_kaynak,
        len(tasinanlar),
        f" Yarim kopya kaldi (ozgunu yerinde, silinmedi): {yarim_kopya}" if yarim_kopya else "",
    )
    return True


def _kopya_yazma(kaynak, hedef, *a, **k):
    """`shutil.move` geri dönüşü YERİNE: kopya YAZMA (D2.47 · B-3.15 · A-08).

    Windows'ta açık tutamaklı (okuyucu kilidi) dosyanın yeniden adlandırması düşünce `shutil.move` `copy2` ile hedefe
    TAM bir kopya yazıp kaynağı silmeye çalışır; silme de düşer → hedefte, kaynak düz-metin DB ise TÜM PII'nin
    korumasız kopyası kalır (ölçüldü: gerçek okuyucu bağlantısıyla `.plain.bak`). Aynı dizindeki taşımada kopyaya hiç
    gerek yoktur; kilit kalıcıysa taşıma düşmeli, çağıran geri alıp göçü iptal etmelidir."""
    raise PermissionError(13, "kaynak kilitli — yalniz yeniden adlandirma yapilir, KOPYA YAZILMADI (A-08)", str(kaynak))


def _tasi_yeniden_dene(kaynak, hedef, denemeler=_KILIT_DENEME, bekleme=_KILIT_BEKLEME_SN, logger=None, kopyalama=True):
    """`shutil.move`, Windows'ta GECICI kilitlere karsi sinirli yeniden-deneme ile.

    ⚠️ NEDEN: dosya tasima Windows'ta baska bir surec (virus tarayici, yedekleyici, indeksleyici
    ya da ayni anda kosan ikinci bir backend) dosyayi acik tuttugu anda `PermissionError`
    (WinError 32/5) ile duser. Bu ANLIK bir durumdur; 100-200 ms sonra genelde gecer.
    Bu depoda ayni sinif daha once yasandi (bkz. bellek `pemf-build-dll-kilidi-ve-sahte-cikis-kodu`:
    yetim mosquitto bir DLL'i kilitleyip derlemeyi dusurmustu).

    ⚠️ SINIRLI: sonsuz denemez. Kilit kalicysa cagiran GERI ALMA yapabilsin diye istisna yukselir.

    `kopyalama=False` (D2.47 · B-3.15 · A-08): yalnız yeniden adlandırma — `shutil.move`un `copy2` geri dönüşü
    kapatılır (`_kopya_yazma`); kilitli düz-metin kaynağın kopyası hedefte KALMAZ. Göçün `db → .plain.bak` taşıması
    bu kiple yapılır. (Test dikişi korunur: `shutil.move` yine tek nokta, `copy_function` anahtar sözcükle geçer.)
    """
    son = None
    for i in range(max(1, denemeler)):
        try:
            if kopyalama:
                shutil.move(kaynak, hedef)
            else:
                shutil.move(kaynak, hedef, copy_function=_kopya_yazma)
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
                # ⚠️ SABIT bekleme: artan olsaydi 24 deneme ~75 sn surerdi ve acilisi
                #    kilitlerdi. Butce `_KILIT_BUTCESI_SN` ile TEK yerde tanimli.
                time.sleep(bekleme)
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


def _kalan_duz_metin_kopyalari_koru(backup, logger=None) -> list:
    """D2.47 (B-3.15 · A-08): `backup`ın kenara alınmış kardeşleri (`<db>.plain.bak.<zaman>[.<n>]`) arasında DÜZ-METİN
    olanları SİLMEZ; ACL ile korumaya alır (sürecin hesabı korunarak — yarım-göç toparlaması kendi yedeğini açabilsin;
    açılıştaki `_harden_secret_file_acls` ile aynı ilke) ve her birini ADIYLA loglar. Döner: kalan kopya yolları.

    Eskiden bu kopyalar (önceki kilitli göçün `copy2` artığı / yarım göçün tek kopyası) korumasız diskte kalırken
    günlük "at-rest PII riski kapatıldı" diyordu (ölçüldü). Kapı: tests/test_goc_duz_metin_kopya_A08_D247.py."""
    import glob

    kalanlar = []
    for yol in sorted(glob.glob(glob.escape(str(backup)) + ".*")):
        try:
            if not duz_metin_sqlite_mi(yol):
                continue
        except Exception:
            continue
        korundu = False
        try:
            from utils.file_acl import lock_down_file

            korundu = bool(lock_down_file(yol, keep_current_user=True))
        except Exception:
            korundu = False
        if logger:
            logger.error(
                "DUZ-METIN KOPYA DISKTE KALDI (A-08: SILINMEDI): %s — %s. Tum hasta PII'sini SQLCipher'siz tasir; "
                "dogrulandiktan sonra guvenli silinmesi onerilir.",
                yol,
                "ACL korumasina alindi" if korundu else "ACL korumasi UYGULANAMADI (yerel kullanicilara acik olabilir)",
            )
        kalanlar.append(yol)
    return kalanlar


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
             tests/test_duz_metin_yedek_bayragi_tek_ad.py · tests/test_goc_duz_metin_kopya_A08_D247.py
    """
    # ⚠️ D2.47 (A-08): önceki göçlerden kalan düz-metin kopyalar SİLİNMEZ, korumaya alınır ve ADIYLA bildirilir;
    # varken "PII riski kapatıldı" DENMEZ.
    kalanlar = _kalan_duz_metin_kopyalari_koru(backup, logger)
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
        if logger and kalanlar:
            logger.error(
                "%s plaintext -> SQLCipher MIGRATE edildi; bu turun düz-metin yedeği GÜVENLİ-SİLİNDİ ama ÖNCEKİ düz-metin "
                "kopya(lar) DİSKTE: %s — at-rest PII riski KAPATILMADI (A-08: silinmedi, korumaya alındı).",
                etiket,
                ", ".join(kalanlar),
            )
        elif logger:
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
            # Y93 (sahip): zaten şifreli → düz dönemden kalan yedekler HER açılışta, açılıştan SONRA arka planda taranır (göç anı
            # dışında kalmış / önceki tarama yarıda kesilmiş kopyalar da şifrelenir; silme yok — A-08).
            duz_yedekleri_arka_planda_sifrele(app_data_dir, keyq, sqlcipher, logger, etiket=etiket)
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
        # ⚠️ OLCULEN BASLATICI (2026-09-19): burasi ciplak `os.remove` idi ve
        #    WinError 32 ile dusunce TUM goc iptal oluyordu.
        if not _kilit_direncli_sil(enc_tmp, logger):
            if logger:
                logger.warning("SQLCipher goc: onceki .enc.tmp silinemedi -> goc ERTELENDI.")
            return
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
                    # ⚠️ 2026-09-20 triyaji: burasi `pass` idi. Ustteki yorum bu temizligin
                    # "acik handle/cakisma -> BOZULMA onle" icin oldugunu soyluyor; yani
                    # basarisizligi masum DEGIL. Akis degismez (goc devam eder) ama artik
                    # bir sonraki bozulma teshis edilebilir.
                    if logger:
                        logger.warning(
                            "Goc oncesi %s temizlenemedi — geride kalan dosya YENI DB'ye "
                            "uygulanmaya calisilabilir (bozulma riski).",
                            f,
                            exc_info=True,
                        )
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
        # ⚠️ D2.47 (B-3.15 · A-08): KOPYASIZ taşıma. Kalıcı okuyucu kilidinde `shutil.move`un `copy2` geri dönüşü
        # `.plain.bak`a TÜM düz-metin PII'nin kopyasını bırakıyordu (göç iptal olsa da kopya kalıyordu — ölçüldü).
        # Kilitte göç kopya yazmadan durur; canlı düz-metin DB yerinde kalır (karantina YOK), sonraki açılış yeniden dener.
        _tasi_yeniden_dene(db, backup, logger=logger, kopyalama=False)
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
        # ⚠️ D2.48 (B-3.29 · A-08): göç DOĞRULANMIŞ başarıyla bitti (şifreli DB yerinde) → düz dönemden kalan
        # `migration_backups/*.db` ve `backups/*.db` kopyaları AYNI anahtarla ŞİFRELENİR (silinmez).
        # ⚠️ Y94 (sahip): eskiden EŞZAMANLIYDI — açılış yedek boyutu kadar (~107 MB/sn) bekliyordu; artık açılıştan sonra arka planda.
        duz_yedekleri_arka_planda_sifrele(app_data_dir, keyq, sqlcipher, logger, etiket=etiket)
    except Exception:
        if logger:
            logger.exception("SQLCipher migrate hatasi (duz-metin korunur)")


#: Y93 / Y94 (sahip): düz dönem yedek şifrelemesi ARKA PLANDA — veri kökü başına TEK iş (iki DB aynı kökü paylaşır).
_yedek_isleri: dict = {}
_yedek_isleri_kilidi = threading.Lock()


def duz_yedekleri_arka_planda_sifrele(app_data_dir, keyq, sqlcipher, logger=None, etiket="DB"):
    """Y93 / Y94: `duz_metin_yedekleri_sifrele`yi açılışı BEKLETMEDEN arka planda koştur. Veri kökü başına tek iş (sürüyorsa yenisi
    başlatılmaz, süreni döner). Dosya tarihleri korunur, silme yok (işlevin kendisi — A-08); yarıda kesilirse Y95 artığı sonraki
    açılışın taramasında toparlanır. ACİL DURDUR / olay döngüsü etkilenmez (ayrı iş parçacığı)."""
    anahtar = os.path.normcase(os.path.abspath(str(app_data_dir)))
    with _yedek_isleri_kilidi:
        suren = _yedek_isleri.get(anahtar)
        if suren is not None and suren.is_alive():
            return suren

        def _calis():
            try:
                duz_metin_yedekleri_sifrele(app_data_dir, keyq, sqlcipher, logger, etiket=etiket)
            except Exception:
                if logger:
                    logger.error(
                        "DUZ-METIN YEDEK SIFRELEMESI (arka plan) DUSTU — yedekler SILINMEDI, sonraki acilista yeniden taranir.",
                        exc_info=True,
                    )

        t = threading.Thread(target=_calis, name=f"duz-yedek-sifreleme ({etiket})", daemon=True)
        _yedek_isleri[anahtar] = t
        t.start()
        return t


def yedek_sifrelemesini_bekle(sure: float = 60.0) -> bool:
    """Testler / kapanış için: süren arka plan yedek şifrelemelerini bekle. True = hepsi bitti."""
    with _yedek_isleri_kilidi:
        isler = list(_yedek_isleri.values())
    for t in isler:
        t.join(sure)
    return not any(t.is_alive() for t in isler)


#: D2.48 (B-3.29): göç sonrası şifrelenen düz dönem yedek dizinleri (veri kökü altında).
_DUZ_DONEM_YEDEK_DIZINLERI = ("migration_backups", "backups")


#: Y95: şifreli kopya yerine konurken ESKİ düz içeriğe verilen geçici ikinci ad (sabit bağ). Yalnız bu ad sıfırlanır.
_DUZ_SIL_EK = ".duz.sil"


def _duz_icerigi_sifirla_ve_sil(eski, logger=None) -> bool:
    """Y95 (Y13 güvenli silme ilkesi): YALNIZ eski düz içeriğe giden adın baytlarını sıfırlar, diske zorlar, siler.
    SSD/eMMC'de en iyi çaba (aşınma dengeleme eski blokları başka yerde tutabilir). Sıfırlanamazsa yalnız silinir (eski
    davranış) ve uyarı loglanır — hiçbir durumda bugünkünden kötü değil. Döner: içerik sıfırlandı mı."""
    sifirlandi = False
    try:
        boyut = os.path.getsize(eski)
        blok = b"\0" * (1 << 16)
        with open(eski, "r+b") as fh:
            kalan = boyut
            while kalan > 0:
                n = min(kalan, len(blok))
                fh.write(blok[:n])
                kalan -= n
            fh.flush()
            os.fsync(fh.fileno())
        sifirlandi = True
    except Exception as e:
        if logger:
            logger.warning(
                "DUZ-METIN ESKI ICERIGIN UZERINE YAZILAMADI (%s: %s): %s — yalniz silinecek (eski davranis).",
                type(e).__name__,
                e,
                eski,
            )
    try:
        os.remove(eski)
    except Exception as e:
        if logger:
            logger.error(
                "DUZ-METIN ESKI ICERIK SILINEMEDI (%s: %s): %s — dosyayi elle silin (icerik %s).",
                type(e).__name__,
                e,
                eski,
                "sifirlandi" if sifirlandi else "DUZ-METIN",
            )
    return sifirlandi


def _anahtarla_dogrulama_hatasi(yol, keyq, sqlcipher):
    """Y95 yarım işlem toparlaması: dosya at-rest anahtarıyla açılıp şeması boş değilse None; değilse NEDEN (çağıran
    loglar — başarısızlık yutulmaz)."""
    try:
        v = sqlcipher.connect(yol)
    except Exception as e:
        return f"acilamadi ({type(e).__name__}: {e})"
    try:
        v.execute(f"PRAGMA key={keyq}")
        if not v.execute("SELECT count(*) FROM sqlite_master").fetchone()[0]:
            return "sema bos"
        return None
    except Exception as e:
        return f"anahtarla okunamadi ({type(e).__name__}: {e})"
    finally:
        v.close()


def _yarim_kalan_duz_icerigi_toparla(sil, keyq, sqlcipher, logger=None):
    """Y95: önceki bir şifrelemenin değiştirme ile sıfırlama ARASINDA kesilmesinden kalan `<yedek>.db.duz.sil`.
    Özgün ad ŞİFRELİ ve anahtarla doğrulanıyorsa eski düz içerik sıfırlanıp silinir; özgün adla AYNI dosyaysa (bağ
    kurulup değiştirme yapılmadan kesildi) yalnız ikinci ad kaldırılır; başka her durumda DOKUNULMAZ ve loglanır."""
    asil = sil[: -len(_DUZ_SIL_EK)]
    neden = "ozgun ad YOK"
    try:
        if os.path.exists(asil) and os.path.samefile(asil, sil):
            os.remove(sil)  # yalnız ikinci ad; içerik özgün adda aynen duruyor
            return
        if os.path.exists(asil):
            if duz_metin_sqlite_mi(asil):
                neden = "ozgun ad DUZ-METIN"
            else:
                neden = _anahtarla_dogrulama_hatasi(asil, keyq, sqlcipher)
            if neden is None:
                _duz_icerigi_sifirla_ve_sil(sil, logger)
                if logger:
                    logger.warning("Y95: yarim kalan guvenli silme tamamlandi (sifreli kopya yerinde): %s", sil)
                return
    except Exception as e:
        if logger:
            logger.error("Y95 yarim islem toparlanamadi (%s: %s): %s", type(e).__name__, e, sil)
        return
    if logger:
        logger.error(
            "DUZ-METIN ESKI ICERIK KALDI: %s — ozgun ad (%s) dogrulanmis sifreli kopya degil (%s); DOKUNULMADI, "
            "elle bakin.",
            sil,
            asil,
            neden,
        )


def _duz_kopyayi_sifrele(yol, keyq, sqlcipher, logger=None) -> bool:
    """Düz-metin SQLite kopyasını AYNI adla, doğrulanmış şifreli eşiyle değiştirir (sqlcipher_export → şema sayısı
    karşılaştırması → `os.replace`). Değişiklik zamanı KORUNUR: `migration_backups` (D2.64) ve `backups` (günlük
    bakımın tazelik/rotasyon kararı) mtime'a göre sıralanır — şifreleme eski kopyayı "en yeni" yapmamalı. Hata
    yükselir; geçici dosya her durumda temizlenir, özgün dosyanın yerine YALNIZ doğrulanmış şifreli kopya geçer.

    ⚠️ Y95 (SAHİP KARARI, Y13 ilkesi): değiştirmeden ÖNCE eski düz içeriğe ikinci bir ad (sabit bağ, aynı dizin)
    verilir; doğrulanmış şifreli kopya özgün adla atomik yerine konunca YALNIZ o ikinci ad sıfırlanıp silinir. Eskiden
    `os.replace` eski düz blokları üzerine YAZMADAN serbest bırakıyordu (hasta adları diskte okunur kalıyordu). Özgün ad
    hiçbir anda eksik kalmaz; değiştirme düşerse yalnız ikinci ad kaldırılır, düz dosya aynen durur; doğrulanmış kopya
    yoksa düz dosyaya HİÇ dokunulmaz. Bağ kurulamazsa (FAT/exFAT) eski davranış + uyarı.
    Kapı: tests/test_duz_yedek_uzerine_YAZILIR_Y95.py. Döner: eski düz içerik sıfırlandı mı."""
    gecici = yol + ".enc.tmp"
    eski = yol + _DUZ_SIL_EK
    st = os.stat(yol)
    if os.path.exists(gecici):
        os.remove(gecici)
    try:
        k = sqlite3.connect(yol)
        try:
            n_kaynak = k.execute("SELECT count(*) FROM sqlite_master").fetchone()[0]
        finally:
            k.close()
        c = sqlcipher.connect(yol)  # anahtar yok -> duz-metin kipinde acilir
        try:
            hedef = gecici.replace("'", "''")
            c.execute(f"ATTACH DATABASE '{hedef}' AS enc KEY {keyq}")
            c.execute("SELECT sqlcipher_export('enc')")
            c.execute("DETACH DATABASE enc")
        finally:
            c.close()
        v = sqlcipher.connect(gecici)
        try:
            v.execute(f"PRAGMA key={keyq}")
            n = v.execute("SELECT count(*) FROM sqlite_master").fetchone()[0]
        finally:
            v.close()
        if not n or n != n_kaynak:
            raise RuntimeError(f"sifreli kopya dogrulanamadi (sema {n} != {n_kaynak})")
        # ── Y95: doğrulanmış şifreli kopya HAZIR — ancak şimdi eski düz içeriğe ikinci ad verilir.
        if os.path.exists(eski):
            if not os.path.samefile(yol, eski):
                raise RuntimeError(f"onceki yarim islemden kalan farkli dosya var, dokunulmadi: {eski}")
            os.remove(eski)  # yalnız ikinci ad (aynı dosya) — içerik özgün adda
        try:
            os.link(yol, eski)
        except OSError as e:
            eski = None
            if logger:
                logger.warning(
                    "DUZ-METIN yedek icin sabit bag kurulamadi (%s: %s): %s — sifreli kopya yine yerine konuyor ama "
                    "eski duz icerigin UZERINE YAZILAMAYACAK (dosya sistemi bag desteklemiyor olabilir).",
                    type(e).__name__,
                    e,
                    yol,
                )
        try:
            os.replace(gecici, yol)
        except BaseException:
            if eski:
                try:
                    os.remove(eski)  # yalnız ikinci ad; düz dosya özgün adda AYNEN
                except Exception:
                    pass
            raise
        os.utime(yol, ns=(st.st_atime_ns, st.st_mtime_ns))
        if not eski:
            return False
        if os.path.samefile(yol, eski):  # savunma: şifreli kopyanın kendisi ASLA sıfırlanmaz
            raise RuntimeError(f"Y95: ikinci ad sifreli kopyayi gosteriyor, sifirlanmadi: {eski}")
        return _duz_icerigi_sifirla_ve_sil(eski, logger)
    finally:
        if os.path.exists(gecici):
            try:
                os.remove(gecici)
            except Exception:
                pass


def duz_metin_yedekleri_sifrele(app_data_dir, keyq, sqlcipher, logger=None, etiket="DB") -> dict:
    """D2.48 (B-3.29 · A-08): düz dönemden kalan `migration_backups/*.db` ve `backups/*.db` kopyalarını at-rest
    anahtarıyla ŞİFRELER — SİLMEZ (aynı ad, aynı veri, şifreli; mtime korunur). Düz-metin SQLite olmayan dosyaya
    (zaten şifreli, JSON vb.) dokunulmaz. Şifrelenemeyen kopya DÜZ ama SAĞLAM bırakılır ve adıyla ERROR loglanır.

    Eskiden at-rest göçü yalnız canlı DB'yi şifreliyordu; düz dönemde alınmış göç öncesi ve günlük yedekler hasta
    adlarını diskte düz taşımaya devam ediyordu (ölçüldü). Kapı: tests/test_goc_sonrasi_duz_yedekler_SIFRELENIR_D248.py.
    Döner: {"sifrelendi": [...], "sifrelenemedi": [...]} (listelenemeyen dizin `sifrelenemedi`de dizin yoluyla)."""
    sonuc = {"sifrelendi": [], "sifrelenemedi": []}
    for alt in _DUZ_DONEM_YEDEK_DIZINLERI:
        dizin = os.path.join(str(app_data_dir), alt)
        if not os.path.isdir(dizin):
            continue
        # ⚠️ 2-A inceleme A2-9.1 (O-2A.4): dizin listelenemezse (ACL/kilit) YALNIZ o dizin atlanır ve adıyla ERROR
        # loglanır — eskiden istisna döngüden göçün dış `except`ine kaçıyordu: sıradaki dizin (backups/) hiç
        # şifrelenmiyor, BAŞARILI göç "migrate hatasi (duz-metin korunur)" diye loglanıyordu (ölçüldü).
        try:
            adlar = sorted(os.listdir(dizin))
        except Exception as e:
            sonuc["sifrelenemedi"].append(dizin)
            if logger:
                logger.error(
                    "DUZ-METIN YEDEK DIZINI OKUNAMADI (%s: %s): %s — icindeki duz yedekler SIFRELENMEDI (silinmedi); "
                    "hasta PII'si tasiyabilirler.",
                    type(e).__name__,
                    e,
                    dizin,
                )
            continue
        for ad in adlar:
            yol = os.path.join(dizin, ad)
            if ad.endswith(".db" + _DUZ_SIL_EK) and os.path.isfile(yol):
                _yarim_kalan_duz_icerigi_toparla(yol, keyq, sqlcipher, logger)  # Y95: kesilmiş önceki işlem
                continue
            if not ad.endswith(".db") or not os.path.isfile(yol):
                continue
            try:
                if not duz_metin_sqlite_mi(yol):
                    continue
            except Exception:
                continue
            try:
                if not _duz_kopyayi_sifrele(yol, keyq, sqlcipher, logger):
                    sonuc.setdefault("duz_icerik_sifirlanamadi", []).append(yol)
                sonuc["sifrelendi"].append(yol)
            except Exception as e:
                sonuc["sifrelenemedi"].append(yol)
                if logger:
                    logger.error(
                        "DUZ-METIN YEDEK SIFRELENEMEDI (%s: %s): %s — dosya DUZ-METIN ama SAGLAM birakildi (SILINMEDI); "
                        "hasta PII'si tasiyabilir.",
                        type(e).__name__,
                        e,
                        yol,
                    )
    # D3I-A2.2 (Y93 · A-08): at-rest göçü `.enc.tmp → db` ile `.plain.bak`ın güvenli silinmesi ARASINDA kesildiyse veri kökünde DÜZ
    # `<db>.plain.bak` (tüm PII) süresiz kalıyordu — tarama yalnız yukarıdaki dizinlere bakıyordu. Aynı yolla şifrelenir (SİLİNMEZ, aynı ad,
    # mtime korunur, Y95); YALNIZ canlı `<db>` yerinde VE at-rest anahtarıyla açılıyorsa (yarım göçün `.plain.bak`ına — `db` YOK —
    # `_yarim_goc_toparla` dokunur) ve emanet istenmiyorsa (emanet ACL'le korunur). `.plain.bak.<zaman>` kardeşleri A-08 kolunda kalır.
    if not duz_metin_yedegi_emanete_al_mi(logger):
        kok = str(app_data_dir)
        try:
            kok_adlari = sorted(os.listdir(kok))
        except Exception as e:
            kok_adlari = []
            sonuc["sifrelenemedi"].append(kok)
            if logger:
                logger.error(
                    "VERI KOKU OKUNAMADI (%s: %s): %s — kokteki .plain.bak SIFRELENMEDI.", type(e).__name__, e, kok
                )
        for ad in kok_adlari:
            yol = os.path.join(kok, ad)
            if ad.endswith(".plain.bak" + _DUZ_SIL_EK) and os.path.isfile(yol):
                _yarim_kalan_duz_icerigi_toparla(yol, keyq, sqlcipher, logger)  # Y95: kesilmiş önceki işlem
                continue
            if not ad.endswith(".plain.bak") or not os.path.isfile(yol):
                continue
            canli = yol[: -len(".plain.bak")]
            try:
                if not duz_metin_sqlite_mi(yol) or not os.path.isfile(canli):
                    continue
                if _anahtarla_dogrulama_hatasi(canli, keyq, sqlcipher) is not None:
                    continue  # canlı DB doğrulanmış şifreli DEĞİL → göç bitmemiş olabilir; dokunma
            except Exception:
                continue
            try:
                if not _duz_kopyayi_sifrele(yol, keyq, sqlcipher, logger):
                    sonuc.setdefault("duz_icerik_sifirlanamadi", []).append(yol)
                sonuc["sifrelendi"].append(yol)
            except Exception as e:
                sonuc["sifrelenemedi"].append(yol)
                if logger:
                    logger.error(
                        "DUZ-METIN GOC YEDEGI (.plain.bak) SIFRELENEMEDI (%s: %s): %s — DUZ-METIN ama SAGLAM birakildi (SILINMEDI).",
                        type(e).__name__,
                        e,
                        yol,
                    )
    if logger and sonuc["sifrelendi"]:
        logger.warning(
            "%s goc sonrasi duz donem yedekleri at-rest anahtariyla SIFRELENDI (silinmedi, ayni ad): %s",
            etiket,
            ", ".join(sonuc["sifrelendi"]),
        )
    return sonuc
