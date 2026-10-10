# Author: mertaygn, cglrgrkn
"""
Tedavi Geçmişi Veritabanı Modülü
PEMF tedavi seanslarının kaydedilmesi ve yönetimi için SQLite veritabanı
"""

import logging
import os
import shutil
import sqlite3
import threading
import weakref
from contextlib import contextmanager
from pathlib import Path

try:
    import keyring
except Exception:  # pragma: no cover - optional dependency fallback
    keyring = None

# SQLCipher + sqlite3 istisna demetleri TEK KAYNAKTAN. Eskiden bu blok BURADA ve
# `patient_database.py` icinde AYRI AYRI duruyordu; iki kopya ZATEN AYRISMISTI (bu dosya
# yalniz `sqlcipher3` deniyordu, oteki `import_sqlcipher()` ile pysqlcipher3'u de).
# Bkz. database/db_hatalari.py bas yorumu — A1b ile ayni sinif.
from database.db_hatalari import _DB_ERROR, _DB_INTEGRITY, _DB_OPERATIONAL, _DB_VEYA_RUNTIME  # noqa: E402,F401

# Anahtar-uyusmazliginda karantina (tuglalasma korumasi) — hasta DB'siyle TEK KAYNAK.
from database.sqlcipher_util import anahtar_uyusmazligi_mi, karantinaya_al  # noqa: E402

# ── B4 BOLME (2026-09-18) ────────────────────────────────────────────────────────────────
# Denetim B4: bu sinif TEK BASINA 93 metot tasiyordu (seans + bobin kosusu + sensor + AI
# gecmisi + denetim izi + outbox + sema gocu + PII). Olcut satir sayisi DEGIL — bu depoda
# yorumlar ozelliktir — sorun tek nesnedeki yedi ayri sorumluluk.
#
# ⚠️ KARISIM (mixin) SECILDI, ISBIRLIKCI NESNE DEGIL: `get_treatment_db(...)` urunun her
# yerinden aliniyor ve metotlar dogrudan cagriliyor. Isbirlikciye cevirmek TUM cagri
# yerlerini degistirirdi. Karisim GENEL API'yi BIREBIR korur (ayni nesne, ayni metotlar).
# Govdeler bayt bayt tasindi; davranis degisikligi AYRI commit'e.
from database.thdb_ai_gecmisi import AiGecmisiKarisimi  # noqa: E402
from database.thdb_bakim import BakimKarisimi  # noqa: E402
from database.thdb_denetim import DenetimKarisimi  # noqa: E402
from database.thdb_outbox import OutboxKarisimi  # noqa: E402
from database.thdb_pii import PiiKarisimi  # noqa: E402
from database.thdb_seans import SeansKarisimi  # noqa: E402
from database.thdb_sema import SemaKarisimi  # noqa: E402
from database.thdb_telemetri import TelemetriKarisimi  # noqa: E402

# `_DB_VEYA_RUNTIME` de TEK KAYNAKTA (database/db_hatalari.py) — yukarida import ediliyor.
# Gerekcesi orada: `_DB_ERROR` zaten bir demet olabilir, `except (_DB_ERROR, RuntimeError)`
# ic-ice demet uretir ve Python "catching classes that do not inherit from BaseException" der.


#: ACİL DURDURMA ile biten seansın `session_status` değeri.
#
# ⚠️ KAMPANYA BULGUSU S09 (2026-08-14): e-stop ile biten seans geçmişte normal bitenden AYIRT
# EDİLEMİYORDU — üçü de `'completed'`. Bir denetimde "bu hastada acil durdurma yaşandı mı?"
# sorusu cevapsız kalıyordu; kesintiyle biten tedavi sorunsuz görünüyordu. Bilgi zaten vardı
# (`_emergency_stop_all` → `_finalize_session_db(reason="acil-durdurma:…")`) ama yalnız
# LOGLANIYOR, kayda yazılmıyordu.
#
# ⚠️ Bu sabiti değiştirirsen KPI sorgusunu da güncelle (`servers/system_router.py`): yazan ile
# okuyan ayrı yerlerde ve ayrışırsa `stoppedSessions` SESSİZCE 0 kalır.
# `tests/test_acil_durdurma_gecmiste_gorunur.py` bu ayrışmayı kilitler.
SEANS_DURUMU_ACIL_DURDURMA = "EMERGENCY_STOPPED"

#: Donanım komutu REDDETTİĞİ için hiç başlayamayan seansın `session_status` değeri.
#
# ⚠️ SAHİP BİLDİRİMİ (2026-09-12): "bobinlere komut gitmemesine rağmen seans başlatınca
# gerçekten başlıyormuş gibi her şey sorunsuz devam ediyor." Böyle bir seans geçmişe
# `'completed'` yazılıyordu — yani hiç uygulanmamış bir tedavi, uygulanmış olarak
# BELGELENİYORDU. Tıbbi kaydın söyleyebileceği en kötü yalan budur.
#
# ⚠️ NEDEN AYRI BİR DEĞER, NEDEN `EMERGENCY_STOPPED` DEĞİL: acil durdurmada tedavi
# BAŞLAMIŞ ve kesilmiştir (hasta bir doz almıştır). Burada HİÇ başlamamıştır. İkisini tek
# kutuya koymak, "bu hastaya ne uygulandı?" sorusunu yine cevapsız bırakırdı.
#
# ⚠️ Değiştirirsen Türkçe etiket haritalarını da güncelle (`utils/seans_durum.py` +
# `TreatmentHistoryScreen.tsx`); `tests/test_seans_durum_etiketi.py` bu ayrışmayı kilitler.
SEANS_DURUMU_DONANIM_REDDI = "HARDWARE_REJECTED"


class TreatmentHistoryDB(
    OutboxKarisimi,
    DenetimKarisimi,
    AiGecmisiKarisimi,
    TelemetriKarisimi,
    PiiKarisimi,
    SemaKarisimi,
    SeansKarisimi,
    BakimKarisimi,
):
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
        """sqlcipher3 / pysqlcipher3 binding'i — ORTAK (2026-09-15).

        ⚠️ Bu metot `sqlcipher_util.import_sqlcipher`in BIREBIR kopyasiydi (14 satir). Uc
        cagirani var, bu yuzden metot KALDI ama govdesi delege ediyor: yeni bir binding
        eklendiginde iki yerde guncellenmesi gereken bir sey kalmasin.
        """
        from database.sqlcipher_util import import_sqlcipher

        return import_sqlcipher()

    def _get_sqlcipher_key(self) -> str:
        """SQLCipher BİRİNCİL anahtarı — D-3 fix: patient_database ile TEK paylaşımlı yol
        (sqlcipher_util.get_sqlcipher_key → SecretsManager-öncelikli). Eskiden bu metod
        SecretsManager'ı ATLIYORDU (keyring→env→file→YENİ-üret) → taze şifreli kurulumda patient DB
        önce init olursa SecretsManager K üretir, treatment DB SONRA K' üretirdi = ÇİFT ANAHTAR
        (treatment DB latent OKUNAMAZ hale gelirdi). Artık ikisi de aynı kaynak → yeni DB birleşik;
        üretim de TEK yerde (çift-üretim divergence'ı kökten biter). Mevcut şifreli DB: shared yol
        keyring/env/file'ı zaten migrate ettiğinden AYNI anahtarı döndürür → sorunsuz açılır.

        ⚠️ D2.45 (B-3.14 · Karar 6 · Y9): birincil anahtar OKUNAMAZSA (`RuntimeError` — çözülemeyen/bozuk sır ya da
        sır dosyasına erişilemiyor) hata YUTULMAZ, legacy yola DÜŞÜLMEZ: yükselir → tedavi DB'si açılmaz, dosyaya
        DOKUNULMAZ, backend DB'siz kısıtlı kipte açılır. Eskiden her istisna legacy'e düşüyordu; legacy kaynakta FARKLI
        bir anahtar varsa tek aday o oluyor, açmayınca "uyuşmazlık" sayılıp kurtarılabilir geçmiş KARANTİNAYA gidiyor,
        yerine bayat anahtarla BOŞ DB kuruluyordu (ölçüldü). D-3 kurtarma adayı (legacy) yalnız birincil HATASIZ
        döndüğünde denenir. Kapı: tests/test_anahtar_yolu_FAIL_CLOSED_Karar6_D245.py."""
        from database.sqlcipher_util import get_sqlcipher_key

        return get_sqlcipher_key(self.app_data_dir, self.logger)

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
        birincil_hatasi = None
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
                if label == "birincil":
                    birincil_hatasi = e
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
        # ⚠️ Anahtar uyuşmazlığı bu depoda TUĞLALAŞMAYA yol açtı; toplu sonuç tam zincirle
        # bildirilir (döngü içindeki tek tek denemeler beklenen başarısızlıklardır, orada zincir
        # gürültü olurdu — ayrım BİLEREK burada).
        self.logger.warning(
            "SQLCipher hicbir aday anahtarla acilamadi (yanlis anahtar/migrate?): %s",
            last_err,
            exc_info=last_err,
        )
        # TUGLALASMA KORUMASI (2026-08-11): "anahtar VARDI ama dosyayi ACMADI"yi, "anahtar/binding
        # HIC YOKTU"dan ayirt edilebilir kil. Karantina YALNIZ birincisinde yapilir — ikincisinde
        # sorun gecici olabilir ve dosyayi kenara almak KURTARILABILIR hasta verisini yetim birakir.
        # ⚠️ D2.45 (Karar 6): karar YALNIZ BİRİNCİL anahtarın gerçek uyuşmazlığından verilir. Eskiden SON adayın
        # hatasına bakılıyordu → birincil boşken ya da geçici bir hatayla düşmüşken legacy adayın uyuşmazlığı tek başına
        # kurtarılabilir geçmişi karantinaya gönderiyordu (D2.04 ile aynı ilke: anahtar YOKKEN karantina yok).
        self._anahtar_vardi_ama_acmadi = birincil_hatasi is not None and anahtar_uyusmazligi_mi(birincil_hatasi)
        return None

    def _create_connection(self):
        """Yeni SQLite bağlantısı oluştur ve bağlantı ayarlarını uygula."""
        # ⚠️ D2.61 (B-3.70): `at_rest_encrypted` YALNIZ bağlantı BAŞARIYLA kurulunca (fonksiyon sonunda) yazılır. Eskiden düz
        # dala girer girmez False yazılıyor, ardından `PEMF_ENCRYPT_AT_REST=1` için `RuntimeError` geliyordu: tek bir iş
        # parçacığındaki GEÇİCİ şifreli bağlantı arızası örnek düzeyindeki bayrağı düşürüyor → `/api/health` şifreli DB'yi
        # "şifresiz" diyor, `create_backup` havuzdaki şifreli bağlantıdan DÜZ hedefe sapıp yedek almadan 0 baytlık dosya
        # bırakıyordu (ölçüldü). Kapı: tests/test_at_rest_bayragi_ve_yarim_yedek_D261.py
        sqlcipher_conn = self._connect_sqlcipher_if_configured()
        if sqlcipher_conn is not None:
            conn = sqlcipher_conn
        else:
            # GÖRÜNÜRLÜK: at-rest şifreleme yoksa SESSİZCE düz-metne düşme — operatör bilsin.
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
        # ⚠️ Y98 (O-2A.2): ayarlar sırasında HERHANGİ bir hata (ilk okuyan `PRAGMA journal_mode`'un "file is not a
        # database"ı `DatabaseError`dır, OperationalError DEĞİL) o anki bağlantıyı KAPATIR. Eskiden bağlantı istisnanın
        # izindeki çerçevede açık kalıyor, istisnayı tutan her şey dosya tutamağını da tutuyordu → Windows'ta karantina
        # taşıması WinError 32 ile ~6 sn bekliyordu (ölçüldü). Kapı: tests/test_PRAGMA_hatasinda_baglanti_KAPANIR_Y98.py.
        try:
            conn.execute('PRAGMA foreign_keys=ON')
            conn.execute('PRAGMA busy_timeout=5000')
            # ⚠️ D2.29 (B-3.91 · Y13): GÜVENLİ SİLME her bağlantıda — silinen satırın içeriği sıfırlanır; eskiden serbest
            # listede OKUNABİLİR kalıyordu (şifresiz kurulumda haftalık VACUUM'a kadar). Şifreli (SQLCipher) kurulumda zararsız.
            # Kapı: tests/test_sifresiz_kurulumda_GUVENLI_SILME_Y13_D229.py
            conn.execute('PRAGMA secure_delete=ON')

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
                self.logger.debug(
                    f"WAL modu ayarlanamadı (zaten açık veya kilitli olabilir), DELETE moda geçiliyor: {e}"
                )
                try:
                    conn.close()
                except Exception:
                    pass
                conn = None

                # ⚠️ D2.46 (B-3.10 · Karar 6): ŞİFRELİ bağlantı DÜZ-METNE DÜŞMEZ. Eskiden burada koşulsuz düz `sqlite3`
                # açılıyordu: doğru anahtarla açılmış şifreli geçmiş "file is not a database" ile UYUŞMAZLIK sayılıp
                # karantinaya gidiyor, ilk kurulumda şema + PII DÜZ-METİN yazılıyor, `at_rest_encrypted` True kalıyordu
                # (ölçüldü). Şifreli bağlantı aynı (önbellekli) anahtarla YENİDEN açılır; açılamazsa fail-closed.
                # Kapı: tests/test_karantina_YALNIZ_gercek_uyusmazlikta_D246.py.
                if sqlcipher_conn is not None:
                    conn = self._connect_sqlcipher_if_configured()
                    if conn is None:
                        raise RuntimeError(
                            "Tedavi DB'si: WAL ayarlanamadi ve SIFRELI baglanti yeniden ACILAMADI — duz-metin "
                            "baglantiya DUSULMEDI (Karar 6)."
                        ) from e
                else:
                    conn = self._connect_plain_sqlite()
                conn.execute('PRAGMA foreign_keys=ON')
                conn.execute('PRAGMA busy_timeout=5000')
                conn.execute('PRAGMA secure_delete=ON')  # D2.29 · Y13 (yukarıdaki not)
                try:
                    conn.execute('PRAGMA journal_mode=DELETE')
                    conn.execute('PRAGMA synchronous=FULL')
                except _DB_OPERATIONAL as fallback_err:
                    # O-A2-2.b (2-A inceleme): başka bir bağlantı WAL'de açıkken DELETE'e geçilemez; bağlantı mevcut
                    # kipte (WAL) sürer ve çalışır (ölçüldü) — zararsız, ERROR değil. Kapı: test_WAL_DELETE_gecisi_UYARI_OA22b.
                    self.logger.warning(
                        "WAL ayarlanamadi, DELETE kipine de gecilemedi (%s) — baglanti MEVCUT kipte suruyor (baska bir "
                        "baglanti WAL'de acik olabilir; zararsiz).",
                        fallback_err,
                    )
        except BaseException:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass
            raise

        self.at_rest_encrypted = sqlcipher_conn is not None
        return conn

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
        except Exception as e:
            self.logger.error("Tibbi kayit DB'si HAZIR DEGIL: %s", e, exc_info=True)
            return False, str(e)[:200]
        # ⚠️ D1.77 (B-3.9): YAZMA korkuluğu kritikse (`_ensure_write_guardrail` her yazımı reddeder) kayıt YAZILAMAZ →
        # hazır DEĞİL. Eskiden yalnız SELECT denendiği için seans 200 dönüp bobinler SÜRÜLÜYOR, seans/doz/olay kaydı 0
        # kalıyordu (kaydedilen ≠ uygulanan). Metin yol/istisna içermez (`/api/health` auth-muaf, tünelden erişilir).
        try:
            disk = self.get_disk_space_status()
        except Exception:
            self.logger.warning("Disk alani okunamadi (hazirlik engellenmedi)", exc_info=True)
            return True, ""
        if bool(disk.get("critical")):
            return False, (
                f"Disk boş alanı kritik ({disk.get('free_mb')} MB < {disk.get('threshold_mb')} MB) — tıbbi kayıt "
                "yazılamaz; yeni seans başlatılamaz. Disk alanı açın."
            )
        return True, ""

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

    #: Operatörün "geri dönüşsüz maskelemeyi anladım" onayı (system_settings).
    PII_ONAY_ANAHTARI = "pii_redaction_acknowledged_at"
    #: Operatörün seçtiği saklama süresi (gün). Yoksa ortam değişkeni/varsayılan geçerli.
    PII_SURE_ANAHTARI = "pii_retention_days"

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

    #: Tek istekte silinebilecek AZAMİ seans sayısı.
    #: ⚠️ SINIR VAR ÇÜNKÜ: toplu silme geri alınamaz ve tek bir yanlış "tümünü seç" tıklaması
    #: kliniğin bütün geçmişini götürebilir. Sınır, kazayı YAVAŞLATIR (operatör ikinci kez
    #: seçmek zorunda kalır) ve tek SQL ifadesinin parametre sayısını da makul tutar.
    TOPLU_SILME_AZAMI = 500

    def close(self):
        """Veritabanı bağlantısını kapat"""
        self.close_connections()

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

    @staticmethod
    def _retry_backoff_seconds(retry_count: int) -> int:
        """Exponential backoff: 1,2,4,... max 300 saniye."""
        return min(300, max(1, 2 ** max(0, retry_count)))


# Singleton instance
_treatment_db_instance = None
_treatment_db_lock = threading.Lock()
#: D1.37 (B-3.8): backend AÇILIŞINDA açılamayan tedavi DB yolu → neden. İSTEK YOLUNDA yeniden DENENMEZ:
#: kilitsiz her `get_treatment_db` (async `/api/health` dahil) göçü kalıcı kilitte ≥6 sn tekrar dener → olay
#: döngüsü, dolayısıyla ACİL DURDUR bloklanır. Yalnız `HeadlessCore` açılışı başarısız olunca kurulur; Y43: yalnız
#: arka plan yeniden açması (`acilista_acilamayani_yeniden_ac`) başarıyla KALDIRIR.
_acilis_kilidi: dict[str, str] = {}


def _kilit_anahtari(db_path) -> str:
    return os.path.normcase(os.path.abspath(str(db_path)))


def acilis_hatasini_kilitle(app_data_dir, exc: BaseException) -> None:
    """İstek yolunda bu tedavi DB'sini açmayı bırak: sonraki `get_treatment_db` HEMEN `RuntimeError` verir
    (arka plan yeniden açması başarılı olana dek — Y43)."""
    anahtar = _kilit_anahtari(os.path.join(str(app_data_dir), "pemf_treatment_history.db"))
    with _treatment_db_lock:
        _acilis_kilidi[anahtar] = type(exc).__name__


def _ayni_db_yolu(a, b) -> bool:
    """D1.57 (B-3.75): iki yol AYNI DB dosyası mı — yazımdan bağımsız (`kök/x/..`, 8.3 kısa ad, ayraç/harf farkı).
    Dosyalar varsa `samefile` (gerçek kimlik), yoksa normalize mutlak yol."""
    if a is None or b is None:
        return False
    try:
        if os.path.exists(a) and os.path.exists(b):
            return os.path.samefile(a, b)
    except OSError:
        pass
    return _kilit_anahtari(a) == _kilit_anahtari(b)


def get_treatment_db(app_data_dir):
    """Tedavi geçmişi veritabanı singleton instance'ını getir"""
    global _treatment_db_instance
    with _treatment_db_lock:
        requested_db_path = app_data_dir / "pemf_treatment_history.db"
        current_db_path = getattr(_treatment_db_instance, 'db_path', None)

        # ⚠️ D1.57 (B-3.75): karşılaştırma YAZIMDAN bağımsız. Eskiden ham `Path` eşitsizliğiydi: aynı dosyaya giden başka
        # bir yazım YENİ örnek kuruyor, kurucunun açılış kurtarması (`recover_stale_active_sessions(max_age_hours=0)`)
        # SÜREN seansı ve açık koşuları `ABORTED_DUE_TO_POWER` mühürlüyor, eski örneğin havuzu da açık kalıyordu.
        if _treatment_db_instance is None or not _ayni_db_yolu(current_db_path, requested_db_path):
            kilit = _acilis_kilidi.get(_kilit_anahtari(requested_db_path))
            if kilit is not None:
                raise RuntimeError(
                    f"Tedavi kaydi DB'si acilista ACILAMADI ({kilit}); istek yolunda denenmez, arka planda yeniden deneniyor."
                )
            eski = _treatment_db_instance
            _treatment_db_instance = TreatmentHistoryDB(app_data_dir)
            if eski is not None:
                # Gerçekten BAŞKA bir DB'ye geçiş: eski örneğin bağlantı havuzu kapatılır (sızmasın). Eski örneği tutan
                # bir iş parçacığı yeni kuşakta taze bağlantı açar (`close_connections` sözleşmesi).
                try:
                    eski.close()
                except Exception:
                    logging.getLogger(__name__).warning("eski tedavi DB ornegi kapatilamadi", exc_info=True)
    return _treatment_db_instance


def acilista_acilamayani_yeniden_ac(app_data_dir):
    """Y43 (sahip — D1.37 devamı): açılışta açılamamış tedavi DB'sini ARKA PLAN iş parçacığından yeniden aç.

    Kurucu (göç, açılış kurtarması — kalıcı kilitte saniyeler) `_treatment_db_lock` DIŞINDA koşar: o sürede
    `get_treatment_db` (sağlık ucu dahil) açılış kilidini görüp HEMEN `RuntimeError` verir, beklemez. Başarılıysa örnek
    kurulur ve açılış kilidi KALKAR; başarısızsa istisna yükselir, kilit yerinde kalır. Kurucu açılıştakiyle AYNI
    (yeni anahtar üretimi / karantina kuralları değişmez)."""
    global _treatment_db_instance
    istenen = Path(app_data_dir) / "pemf_treatment_history.db"
    with _treatment_db_lock:
        mevcut = _treatment_db_instance
        if mevcut is not None and _ayni_db_yolu(getattr(mevcut, "db_path", None), istenen):
            _acilis_kilidi.pop(_kilit_anahtari(istenen), None)
            return mevcut
    yeni = TreatmentHistoryDB(Path(app_data_dir))
    with _treatment_db_lock:
        eski = _treatment_db_instance
        _treatment_db_instance = yeni
        _acilis_kilidi.pop(_kilit_anahtari(istenen), None)
    if eski is not None and eski is not yeni:
        try:
            eski.close()
        except Exception:
            logging.getLogger(__name__).warning("eski tedavi DB ornegi kapatilamadi", exc_info=True)
    return yeni
