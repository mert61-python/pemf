# Author: mertaygn, cglrgrkn
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
    # ⚠️ `pemf_gui` depo KOKUNDE (2026-09-18, F4): bu modul `apps/backend/database/`
    # altina indi, "bir ust dizin" artik kok DEGIL.
    from utils.path_utils import kaynak_kokunu_bul

    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = str(kaynak_kokunu_bul(__file__))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    from pemf_gui.config import get_config

# P0 audit 2026-06-28: hasta PII whole-DB SQLCipher sifrelemesi (paylasilan yardimci modul).
# P0 audit 2026-06-28: SQLCipher baglantilarinda exception'lar sqlcipher3.dbapi2.* tipinde gelir;
# duz sqlite3.* except'leri bunlari YAKALAMAZ (ornek: ALTER 'duplicate column' patlar).
#
# ⚠️ 2026-09-18: bu blok BURADA ve `treatment_history_db.py` icinde AYRI AYRI duruyordu ve
# ikisi ZATEN AYRISMISTI — oradaki yalniz `sqlcipher3` deniyordu, burasi `import_sqlcipher()`
# ile `pysqlcipher3`u de. Yani yalniz pysqlcipher3 bulunan bir ortamda tedavi DB'si
# sqlite3-only demete dusuyor ve sifreli yolda firlayan hatayi YAKALAMADAN geciyordu.
# TEK KAYNAK: database/db_hatalari.py (guclu olan, yani buradaki davranis korundu).
from database.db_hatalari import _DB_ERROR, _DB_INTEGRITY, _DB_OPERATIONAL  # noqa: E402,F401
from database.sqlcipher_util import (
    anahtar_uyusmazligi_mi,
    get_sqlcipher_key,
    import_sqlcipher,
    karantinaya_al,
    migrate_to_encrypted_if_needed,
    open_encrypted_conn,
)

# DENETIM P3: cozulemeyen (farkli anahtar / eski surum / template) sifreli alan icin UI'ya
# gonderilen yer-tutucu. Bu metin GERI YAZILIRSA orijinal ciphertext KALICI kaybolur →
# update_patient bunu ozel olarak eler (bkz. "CIPHERTEXT KORUMA").
_UNREADABLE_PLACEHOLDER = "[okunamayan kayıt]"


class PatientDatabase:
    """Hasta veritabani yonetim sinifi."""

    _ENCRYPTED_FIELDS = {
        "name",
        "owner",
        "vet_contact",
        "species",
        "breed",
        "age",
        "weight",
        "owner_email",
        "operator_email",
    }
    _SEARCHABLE_FIELDS = ("name", "owner", "species", "breed", "age", "weight")

    def __init__(self, db_file: str = "patients.db"):
        self.db_file = Path(db_file)
        self.lock = threading.Lock()
        self.logger = logging.getLogger("PatientDatabase")
        self.config_manager = get_config()
        # ⚠️ 2-A inceleme A2-1.1 (D2.45 · Y9): alan şifreleme anahtarı (patient_fernet_key) artık modül yüklenirken değil
        # BURADA alınır; alınamazsa (bozuk / bu makinede çözülemeyen sır) hasta DB'sine DOKUNULMADAN `RuntimeError` →
        # DB'siz kısıtlı kip; arka plan yeniden açması (Y43) her denemede yeniden alır.
        self.config_manager._anahtar_hazirla()
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
            try:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA synchronous=NORMAL")
                conn.execute("PRAGMA foreign_keys=ON")  # B-7.3: patient_search_index ON DELETE CASCADE aktif
                conn.execute("PRAGMA busy_timeout=5000")  # B-6.2: 'database is locked' yerine bekle
                # ⚠️ D2.29 (Y13): GÜVENLİ SİLME — silinen hastanın (alan şifreli) saklanan değerleri sıfırlanır; eskiden serbest
                # listede kalıyor, aynı cihazın anahtarıyla ÇÖZÜLEBİLİYORDU. Kapı: tests/test_sifresiz_kurulumda_GUVENLI_SILME_Y13_D229.py
                conn.execute("PRAGMA secure_delete=ON")
            except BaseException:
                # ⚠️ Y98 (O-2A.2): PRAGMA hatasında ("file is not a database" = DatabaseError) açılan bağlantı
                # KAPATILIR. Eskiden istisna izindeki çerçevede açık kalıyor, istisnayı tutan her şey dosya tutamağını da
                # tutuyordu → Windows'ta karantina/göç taşıması WinError 32 ile ~6 sn bekliyordu (ölçüldü).
                # Kapı: tests/test_PRAGMA_hatasinda_baglanti_KAPANIR_Y98.py.
                try:
                    conn.close()
                except Exception:
                    pass
                raise
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
            if (
                created_here
                and self._local.conn is not None
                and threading.current_thread() is not threading.main_thread()
            ):
                try:
                    self._local.conn.close()
                except Exception:
                    pass
                self._local.conn = None

    def _reset_thread_conn(self) -> None:
        """Bu thread'in bağlantısını kapat + unut. Karantina ÖNCESİ zorunlu: açık bir SQLCipher
        tutamacı dosyayı Windows'ta kilitler ve `shutil.move` PermissionError verir."""
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
        self._local.conn = None

    def _db_hatasini_yaz(self, ne: str) -> None:
        """⚠️ D2.66 (B-3.110): hasta DB'si okunamaz / yazılamazken yöntemler boş / None / False / 0 döner — ama artık SESSİZ DEĞİL:
        WARNING + istisna izi. Eskiden operatör "hasta yok" görüyor, günlükte hiçbir iz olmuyordu; arıza sırasında alınan cihaz-taşıma
        yedeği hasta listesiz "başarılı" çıkıyordu. Kapı: tests/test_hasta_DB_okunamazken_SESSIZ_DEGIL_D266.py"""
        self.logger.warning(
            "Hasta DB'si %s basarisiz (DB okunamiyor/yazilamiyor) — sonuc bos/False dondu; bu 'hasta yok' DEMEK DEGIL.",
            ne,
            exc_info=True,
        )

    def create_backup(self, backup_path: str) -> bool:
        """Çalışan hasta DB'sinden dosya yedeği (online backup API). DB ŞİFRELİYSE yedek de AYNI
        anahtarla ŞİFRELİ olur (düz hedefe yedek PII sızdırır). audit B-7.2: PatientDB'nin yedeği yoktu.

        ⚠️ D2.61 (B-3.70) · D2.63 (B-3.20): tedavi DB'siyle AYNI kural ve AYNI yazıcı (`database/yedek_dosyasi.yedek_yaz`) —
        geçici ad → açılarak doğrulama → son ada taşıma; başarısız deneme hedefte 0 baytlık / yarım dosya BIRAKMAZ.
        Kapılar: tests/test_at_rest_bayragi_ve_yarim_yedek_D261.py · tests/test_yerel_yedek_penceresi_KORUNUR_D263.py"""
        from database.yedek_dosyasi import yedek_yaz

        try:
            bdir = os.path.dirname(backup_path)
            if bdir:
                os.makedirs(bdir, exist_ok=True)
            with self._get_connection() as src:
                if self.at_rest_encrypted and self._sqlcipher_mod is not None:
                    yedek_yaz(src, backup_path, self._sqlcipher_mod, self._cipher_key, self.logger)
                else:
                    yedek_yaz(src, backup_path, sqlite3, "", self.logger)
            return True
        except Exception:
            self.logger.exception("PatientDB create_backup hatası")
            return False

    def yedek_acilir_mi(self, yol, tam: bool = False) -> bool:
        """Bu kurulumun anahtarıyla hasta DB yedeği açılıyor mu? (D2.63 rotasyon / tazelik) ASLA istisna atmaz."""
        from database.yedek_dosyasi import yedek_acilir_mi

        if self.at_rest_encrypted and self._sqlcipher_mod is not None:
            return yedek_acilir_mi(yol, self._sqlcipher_mod, self._cipher_key, tam=tam)
        return yedek_acilir_mi(yol, None, "", tam=tam)

    def _safe_add_column(self, cursor, table: str, column_def: str) -> None:
        """Idempotent şema-migrasyonu: ALTER TABLE ADD COLUMN; sütun zaten varsa (`duplicate column`) sessizce geç.
        (Eski DB'lere yeni kolon eklemenin tek noktası — tekrarlanan try/except kalıbı buraya toplandı.)

        ⚠️ D2.24 (B-3.81 · Y9): BAŞKA her `OperationalError` (kilit, G-Ç, disk dolu) WARNING ile loglanır ve YÜKSELİR →
        `_init_database` `RuntimeError` verir (karantina YOK — anahtar uyuşmazlığı değil) → backend DB'siz kısıtlı kipte
        açılır. Eskiden hepsi yutuluyor, hasta tablosu KOLONSUZ açılıyordu. İkiz: `thdb_sema._safe_add_column`.
        Kapı: tests/test_sema_gocu_KILITTE_sessiz_gecmez_D224.py."""
        try:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column_def}")
        except _DB_OPERATIONAL as e:
            if "duplicate column" in str(e).lower():
                return
            self.logger.warning(
                "Sema gocu: %s.%s kolonu eklenemedi (%s) — hasta DB'si HAZIR DEGIL, acilis durduruluyor "
                "(dosyaya dokunulmadi; kilit kalkinca kolon eklenir).",
                table,
                column_def.split()[0],
                e,
            )
            raise

    def _init_database(self) -> None:
        """SQLite şemasını oluştur + HMAC arama indeksini garanti et.

        ⚠️ ANAHTAR UYUŞMAZLIĞINDA CİHAZ TUĞLALAŞMAZ (saha hatası 2026-08-11). Kaldır-yeniden-kur
        sonrası `patients.db` korunur ama at-rest anahtarı yenilenmişse SQLCipher dosyayı
        açamaz; eskiden buradan fırlayan RuntimeError backend'i **çıkış kodu 1** ile öldürüyor,
        launcher'da yalnızca günler öncesine ait bayat bir günlük görünüyordu. Artık dosya
        kenara alınır (SİLİNMEZ) ve temiz bir DB açılır.

        Karantina YALNIZ anahtar okunabildiği hâlde uymuyorsa yapılır — bkz. sqlcipher_util.
        Anahtar hiç yoksa hata yukarı fırlar: o durumda sorun geçici olabilir ve dosyayı kenara
        almak KURTARILABİLİR hasta verisini yetim bırakır."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                self._create_patient_schema(cursor)
                _fp = self._ensure_search_index(cursor)
                conn.commit()
            # ⚠️ D2.25 (B-3.106): parmak izi YALNIZ yeniden kurulumu içeren işlem COMMIT edildikten SONRA yazılır.
            self._parmak_izini_yaz(_fp)
            return
        except _DB_ERROR as e:
            # ⚠️ D2.46 (B-3.48): karar anahtarın VARLIĞINA değil ŞİFRELİ BAĞLANTIYA bakar. Anahtar var ama sqlcipher3
            # binding YOKSA düz bağlantı şifreli dosyayı açamaz — bu uyuşmazlık DEĞİLDİR; eskiden sağlam şifreli
            # patients.db karantinaya gidiyor, yerine DÜZ-METİN DB kuruluyordu (ölçüldü). Artık fail-closed, dosyaya
            # dokunulmaz. Kapı: tests/test_karantina_YALNIZ_gercek_uyusmazlikta_D246.py.
            if not (self.at_rest_encrypted and anahtar_uyusmazligi_mi(e)):
                if self._cipher_key and not self.at_rest_encrypted and anahtar_uyusmazligi_mi(e):
                    self.logger.error(
                        "Hasta veritabani ACILAMADI: at-rest anahtari VAR ama sqlcipher3 binding YOK — dosya sifreli "
                        "olabilir; KARANTINAYA ALINMADI, dokunulmadi. sqlcipher3'u kurun."
                    )
                raise RuntimeError(f"Database initialization failed: {e}") from e
            self.logger.error("Hasta veritabani mevcut at-rest anahtariyla ACILAMADI (%s) → karantina denenecek.", e)

        # Bozuk bağlantıyı bırak, dosyayı kenara al, sıfırdan aç.
        self._reset_thread_conn()
        if karantinaya_al(self.db_file, self.logger) is None:
            raise RuntimeError(
                "Hasta veritabani acilamadi ve karantinaya ALINAMADI (dosya kilitli olabilir). "
                "Baska bir PEMF surecinin calismadigindan emin olup yeniden deneyin."
            )
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                self._create_patient_schema(cursor)
                _fp = self._ensure_search_index(cursor)
                conn.commit()
        except _DB_ERROR as e:
            raise RuntimeError(f"Database initialization failed (karantina sonrasi): {e}") from e
        self._parmak_izini_yaz(_fp)

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
        # SG.G1 (2026-10-14): kaydın oluşturulduğu ARAYÜZ profili (veterinarian / researcher / pet_owner; şifresiz üst veri — kişisel
        # veri değil). EKLEMELİ, boş varsayılan: eski satırlar DEĞİŞMEZ (`utils/profil.hasta_profilde_mi` okumada türetir).
        self._safe_add_column(cursor, "patients", "profil TEXT DEFAULT ''")

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
        # Y121 (S-C.3): kalıcı bakım işaretleri (ör. ertelenmiş KVKK VACUUM'u) — yeniden başlatmada kaybolmaz.
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS bakim_durumu (anahtar TEXT PRIMARY KEY, deger TEXT, guncellendi TEXT)"
        )

    #: Y121: toplu silmede düşen VACUUM'un kalıcı işareti (`bakim_durumu`).
    VACUUM_BEKLIYOR_ANAHTARI = "kvkk_vacuum_bekliyor"

    def vacuum_bekliyor_mu(self) -> bool:
        """Y121: ertelenmiş KVKK VACUUM'u var mı? Okunamazsa True (emin değilsek yeniden dene — VACUUM zararsız)."""
        try:
            with self._get_connection() as conn:
                r = conn.execute(
                    "SELECT deger FROM bakim_durumu WHERE anahtar=?", (self.VACUUM_BEKLIYOR_ANAHTARI,)
                ).fetchone()
                return bool(r) and str(r[0]) == "1"
        except _DB_ERROR:
            self.logger.warning("Hasta DB VACUUM isareti okunamadi — bekliyor sayiliyor", exc_info=True)
            return True

    def _vacuum_isaretini_yaz(self, deger: str) -> bool:
        try:
            with self._get_connection() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO bakim_durumu (anahtar, deger, guncellendi) VALUES (?,?,?)",
                    (self.VACUUM_BEKLIYOR_ANAHTARI, deger, datetime.now().isoformat(timespec="seconds")),
                )
                conn.commit()
            return True
        except _DB_ERROR:
            self.logger.error(
                "Hasta DB VACUUM isareti yazilamadi (%s) — ertelenmis VACUUM kendiliginden yeniden denenmeyebilir.",
                deger,
                exc_info=True,
            )
            return False

    def bekleyen_vacuum_calistir(self) -> bool:
        """Y121: ertelenmiş KVKK VACUUM'u koş (ÇAĞIRAN seans olmadığını denetler — günlük bakım döngüsü). @return koştu mu."""
        if not self.vacuum_bekliyor_mu():
            return False
        with self.lock:
            try:
                with self._get_connection() as conn:
                    conn.cursor().execute("VACUUM")
                    # WAL kipinde VACUUM yeni sayfaları WAL'a yazar; eski sayfalar denetim noktasına kadar ana dosyada KALIR (ölçüldü).
                    tamam = self._silme_sonrasi_denetim_noktasi(conn, "ertelenmis VACUUM")
            except _DB_ERROR:
                self.logger.warning("Hasta DB ertelenmis KVKK VACUUM'u yine yapilamadi (bekliyor)", exc_info=True)
                return False
        if not tamam:
            return False  # F2-2.5: kalıntı duruyor → işaret KALIR (eskiden 0 yazılıyordu — "tamamlandı" yalanı)
        self._vacuum_isaretini_yaz("0")
        self.logger.info("Hasta DB ertelenmis KVKK VACUUM'u tamamlandi.")
        return True

    def _ensure_search_index(self, cursor) -> Optional[str]:
        """HMAC arama indeksini garanti et: tablo BOŞSA veya arama-anahtarı DEĞİŞTİYSE yeniden kur.
        (P2 audit: HMAC indeksi _search_hmac_key'e bağlı; anahtar değişirse eski token'lar eşleşmez →
        arama SESSİZCE bozulur. Anahtar parmak-izini saklayıp değişimi tespit ediyoruz.)

        ⚠️ D2.25 (B-3.106): parmak izini YAZMAZ, yazılması gereken değeri DÖNDÜRÜR (değişmediyse None). Çağıran
        (`_init_database`) yeniden kurulumu içeren işlem COMMIT edildikten SONRA `_parmak_izini_yaz` ile yazar.
        Eskiden burada, commit'ten ÖNCE yazılıyordu: commit düşerse yeniden kurma geri alınıyor ama dosya YENİ
        sürümü taşıyordu → sonraki açılışlar yeniden kurmuyor, hasta Türkçe aramada bulunamıyordu (ölçüldü).
        Kapı: tests/test_hasta_arama_turkce.py::test_KRITIK_D225_…"""
        cursor.execute("SELECT COUNT(*) FROM patient_search_index")
        count = cursor.fetchone()[0]
        # ⚠️ Parmak izi HMAC anahtarını VE normalize sürümünü kapsar: normalize mantığı
        # değişince (ör. Türkçe katlama, 2026-08-30) eski indeks yeni aramalarla eşleşmez →
        # sürümü parmak izine katmak sahadaki indeksi açılışta KENDİLİĞİNDEN yeniden kurar.
        _fp = hashlib.sha256(self._search_hmac_key + f"|norm{self._SEARCH_NORM_VERSION}".encode()).hexdigest()[:16]
        _fp_file = self._key_dir / ".patient_search_keyfp"
        _stored_fp = ""
        try:
            if _fp_file.exists():
                _stored_fp = _fp_file.read_text(encoding="utf-8").strip()
        except Exception:
            pass
        # ⚠️ Y101 (S3 · O-A2-9.b, 2-C): parmak izi DOSYASI YOKKEN (silinmiş / okunamamış / taşımada geride kalmış) dolu indeks
        # de BİR KEZ yeniden kurulur — eskiden kurulmuyor, dosyaya güncel sürüm yazılıyordu → eski kuralla kurulmuş indeks bir
        # daha tazelenmiyordu (ölçüldü). Kurulumdan sonra dosya yazılır (D2.25: commit SONRASI) → tek seferlik.
        # Kapı: tests/test_arama_indeksi_PARMAK_IZI_YOKSA_bir_kez_kurulur_Y101.py.
        if count == 0 or _stored_fp != _fp:
            if count > 0:
                self.logger.warning(
                    "Hasta arama indeksi parmak izi %s → HMAC indeksi yeniden kuruluyor.",
                    "YOK" if not _stored_fp else "degismis",
                )
            self._rebuild_search_index(cursor)
        return _fp if _fp != _stored_fp else None

    def _parmak_izini_yaz(self, fp: Optional[str]) -> None:
        """Arama indeksi parmak izini diske yaz — YALNIZ kurulum işlemi commit edildikten sonra çağrılır (D2.25)."""
        if not fp:
            return
        try:
            # ⚠️ C2-2.10 (2-C inceleme · Y101 "bir kez"): dosya VAR ama OKUNAMIYORSA (izin) üstüne yazmak izni korur → her
            # açılış yeniden kuruyordu (ölçüldü 3/3). Geçici dosyaya yazılıp `os.replace` ile değiştirilir: yeni dosya dizinin
            # iznini miras alır, sonraki açılış okur (tek seferlik). Yerine koyma da düşerse uyarı (sonraki açılışta yeniden denenir).
            hedef = self._key_dir / ".patient_search_keyfp"
            gecici = hedef.with_name(hedef.name + ".tmp")
            gecici.write_text(fp, encoding="utf-8")
            os.replace(gecici, hedef)
        except Exception:
            self.logger.warning(
                "Arama indeksi parmak izi yazilamadi (sonraki acilista yeniden denenir).", exc_info=True
            )

    # ⚠️ NORMALİZE SÜRÜMÜ — arama indeksi parmak-izine dahil (bkz. _ensure_search_index).
    # ORTAK KAYNAK: `utils.turkce_metin.SURUM` (arama katlaması orada tek yerde tanımlı;
    # aynı tuzak PDF rapor filtresinde de vardı — iki yüzey artık aynı fonksiyonu kullanır).
    # Katlama mantığı her değişince `utils.turkce_metin.SURUM`ı ARTIR → sahadaki indeks açılışta
    # KENDİLİĞİNDEN yeniden kurulur.
    from utils.turkce_metin import SURUM as _SEARCH_NORM_VERSION

    def _normalize_search_value(self, value: str) -> str:
        """Arama token'ı — Türkçe-güvenli katlamaya delege eder (bkz. utils.turkce_metin).

        ⚠️ TÜRKÇE COLLATION TUZAĞI (saha bulgusu 2026-08-30): `str.lower()` 'İ'yi birleşik-noktalı
        'i̇'ye, 'I'yı 'i'ye çeviriyordu → "İhsan" kaydedip "ihsan" arayan doktor hastayı bulamıyordu.
        Katlama TEK yerde toplandı ki PDF rapor filtresiyle ayrışmasın."""
        from utils.turkce_metin import arama_katla

        return arama_katla(value)

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

    def _index_patient_search_terms(
        self, cursor: sqlite3.Cursor, patient_id: str, patient_info: Dict[str, str]
    ) -> None:
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
                return _UNREADABLE_PLACEHOLDER
            return dec

        # Backward compatibility: older rows may contain encrypted payloads
        # without the enc: prefix. Try silent decrypt, otherwise return as-is.
        # ⚠️ D2.26 (B-3.108): `enc:` dalıyla AYNI zincir (birincil → legacy MAC-türevli anahtar). Eskiden burada YALNIZ
        # birincil anahtar deneniyordu → legacy anahtarla şifrelenmiş öneksiz alan '[okunamayan kayıt]' görünüyor ve
        # cihaz taşımada (get_all_patients → add_patient) yer-tutucu hedefe KALICI yazılıyordu (ölçüldü). `sessiz`:
        # değer düz-metin de olabilir — başarısızlık ERROR değildir. Kapı: test_hasta_alani_ESKI_anahtar_oneksiz_COZULUR_D226.py
        try:
            dec = self.config_manager._decrypt_value(value, sessiz=True)
        except Exception:
            dec = value
        if dec != value:
            return dec
        # Çözülemedi. Fernet token gibi görünüyorsa (farklı anahtarla şifrelenmiş eski/şablon
        # kayıt) ham ciphertext'i KULLANICIYA GÖSTERME; düz-metin legacy ise olduğu gibi bırak.
        try:
            if base64.urlsafe_b64decode(value.encode()).startswith(b"gAAAAA"):
                return _UNREADABLE_PLACEHOLDER
        except Exception:
            pass
        return value

    def add_patient(self, patient_info: Dict[str, str], patient_id: Optional[str] = None) -> str:
        """Yeni hasta ekler ve olusan patient_id degerini dondurur.

        `patient_id` YALNIZ ICE AKTARMA icindir (cihaz tasima / yedekten geri yukleme).

        ⚠️ DENETIM 2026-08-17 — KOPUK UUID ZINCIRI. Bu fonksiyon gelen `id`'yi YOK SAYIP her
        cagrida `uuid.uuid4()` uretiyordu. `/api/data/import` hasta satirlarini dogrudan buraya
        verdigi icin `patients.db` ↔ tedavi-DB bagi **HER ice aktarimda** kopuyordu (`REPLACE_ALL`
        sarti YOK; bos bir hedefe normal tasimada da):
            KAYNAK patients.db id        : 1295eb8f-...
            HEDEF  patients.db id        : ec1ced28-...   <- yeni uuid4
            HEDEF  treatment patient_uuid: 1295eb8f-...   <- paketle DOGRU tasindi
        Somut sonuc (sessiz): `api_server` gunluk bakiminda
        `_pdb.anonymize_inactive_patients(1825)` -> `db.anonymize_patients_by_uuid(...)` zinciri
        tasinmis hastalarin **tedavi gecmisindeki ad kopyalarina ULASAMAZ** -> 5 yil inaktif
        hastada `patients.db` anonimlesir ama tedavi gecmisindeki ad `[REDACTED]` OLMAZ (KVKK).

        ⚠️ Gecersiz/bos `id` ICE AKTARMAYI DUSURMEZ: yeni bir uuid uretilir ve satir yine yazilir.
        Eski/elle duzenlenmis paketlerde bozuk `id` olabilir; tek bozuk satirin tum klinik
        gecmisinin tasinmasini engellemesi daha kotu olurdu.

        Kilit: `tests/test_ice_aktarma_hasta_uuid_zinciri.py` (karsit-kanit testleri dahil).
        """
        with self.lock:
            # Verilen id yalnizca GERCEK bir UUID ise onurlandirilir; aksi halde uretilir.
            _verilen = (str(patient_id) if patient_id else "").strip()
            if _verilen:
                try:
                    uuid.UUID(_verilen)
                except (ValueError, AttributeError, TypeError):
                    self.logger.warning(
                        "Ice aktarma: gecersiz hasta id'si (%r) — yeni id uretiliyor; bu satir icin "
                        "patients.db ↔ tedavi-DB zinciri kurulamaz.",
                        _verilen[:64],
                    )
                    _verilen = ""
            patient_id = _verilen or str(uuid.uuid4())
            now = datetime.now().isoformat()
            # ⚠️ D2.53 (B-3.30 · B-3.31): İÇE AKTARMADA (patient_id verildiğinde) satır EKSİKSİZ taşınır:
            #   · `created_at` / `updated_at` / `last_treatment_at` / `anonymized` paketteki değerleriyle — eskiden kayıt tarihi içe
            #     aktarma anına SIFIRLANIYOR, KVKK'nın 5 yıllık inaktiflik saati baştan başlıyor, anonim hasta "anonim değil" oluyordu;
            #   · çözülemeyen alan (`_sifreli_ham`, bkz. `disa_aktarim_hastalari`) ÖZGÜN şifreli değeriyle AYNEN yazılır ve arama
            #     dizinine katılmaz — eskiden "[okunamayan kayıt]" yer tutucusu gerçek değer diye şifreleniyor, özgün değer kayboluyordu.
            # Yeni hasta (patient_id yok) bugünkü gibi. Kapı: tests/test_cihaz_tasima_hasta_satiri_EKSIKSIZ_D253.py
            ice_aktarma = bool(_verilen)
            ham = patient_info.get("_sifreli_ham") if ice_aktarma else None
            ham = {k: v for k, v in (ham or {}).items() if k in self._ENCRYPTED_FIELDS and isinstance(v, str) and v}

            def _alan(ad: str) -> str:
                return ham[ad] if ad in ham else self._encrypt_field(patient_info.get(ad, ""))

            def _tarih(ad: str, varsayilan):
                deger = patient_info.get(ad) if ice_aktarma else None
                if deger in (None, ""):
                    return varsayilan
                try:
                    datetime.fromisoformat(str(deger))
                    return str(deger)
                except ValueError:
                    self.logger.warning("Ice aktarma: gecersiz %s (%r) — varsayilan kullanildi.", ad, str(deger)[:40])
                    return varsayilan

            olusturma = _tarih("created_at", now)
            guncelleme = _tarih("updated_at", olusturma)
            son_tedavi = _tarih("last_treatment_at", None)
            anonim = 1 if ice_aktarma and str(patient_info.get("anonymized") or 0) in ("1", "True", "true") else 0
            # SG.G1: yeni kayıtta isteğin profili (router), içe aktarmada paketteki değer AYNEN (cihaz taşıma korur).
            from utils.profil import gecerli_profil

            profil = gecerli_profil(patient_info.get("profil")) or ""
            dizin_icin = {k: ("" if k in ham else v) for k, v in patient_info.items()}

            try:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        """
                        INSERT INTO patients
                        (id, name, species, breed, age, weight, owner, vet_contact, owner_email, operator_email, created_at, updated_at,
                         last_treatment_at, anonymized, profil)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            patient_id,
                            _alan("name"),
                            _alan("species"),
                            _alan("breed"),
                            _alan("age"),
                            _alan("weight"),
                            _alan("owner"),
                            _alan("vet_contact"),
                            _alan("owner_email"),
                            _alan("operator_email"),
                            olusturma,
                            guncelleme,
                            son_tedavi,
                            anonim,
                            profil,
                        ),
                    )
                    self._index_patient_search_terms(cursor, patient_id, dizin_icin)
                    conn.commit()
                return patient_id
            except _DB_ERROR as e:
                raise RuntimeError(f"Failed to add patient: {e}") from e

    def disa_aktarim_hastalari(self) -> List[Dict[str, Any]]:
        """Cihaz taşıma paketi için TÜM hasta satırları (tarihler ve `anonymized` dahil) — KATI okuma (hata yükselir, D2.66).

        ⚠️ D2.53 (B-3.31): çözülemeyen (farklı / eski anahtarla şifreli) alan YER TUTUCU olarak pakete GİRMEZ: alan boş bırakılır ve
        özgün şifreli değeri `_sifreli_ham` altında taşınır; içe aktarma onu aynen yazar (`add_patient`). Eskiden "[okunamayan kayıt]"
        metni paketleniyor, yeni cihazda gerçek değer diye şifreleniyordu — özgün değer kayboluyordu."""
        with self.lock:
            with self._get_connection() as conn:
                conn.row_factory = self._row_factory
                satirlar = conn.cursor().execute("SELECT * FROM patients ORDER BY created_at DESC").fetchall()
        sonuc: List[Dict[str, Any]] = []
        for satir in satirlar:
            ham = dict(satir)
            hasta = self._decrypt_patient_fields(dict(ham))
            okunamayan = {a: ham.get(a) for a in self._ENCRYPTED_FIELDS if hasta.get(a) == _UNREADABLE_PLACEHOLDER}
            if okunamayan:
                for a in okunamayan:
                    hasta[a] = ""
                hasta["_sifreli_ham"] = okunamayan
            sonuc.append(hasta)
        return sonuc

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
                self._db_hatasini_yaz("hasta okuma")
                return None

    def operator_sahipleri(self, patient_ids) -> Dict[str, str]:
        """{hasta kimliği: kaydı oluşturan hekimin e-postası (deşifre)} — YALNIZ var olan kayıtlar.

        Silme yetkisi (D2.72 · Y92) için. ⚠️ Hata YUTULMAZ: okunamayan sahiplik "sahibi yok" sayılırsa silme kapısı
        boş sözlükle geçerdi (fail-open) — istisna çağırana gider, uç 500 döner, hiçbir şey silinmez."""
        kimlikler = sorted({str(x) for x in (patient_ids or ()) if str(x or "").strip()})
        if not kimlikler:
            return {}
        yer = ",".join("?" for _ in kimlikler)
        with self.lock:
            with self._get_connection() as conn:
                satirlar = conn.execute(
                    f"SELECT id, operator_email FROM patients WHERE id IN ({yer})", kimlikler
                ).fetchall()
        return {str(s[0]): self._decrypt_field(s[1] or "") for s in satirlar}

    @staticmethod
    def _profil_kosulu(profil: Optional[str]) -> tuple:
        """SG.G1: hasta listesi / sayımı / toplu silme için TEK profil koşulu (`utils/profil.hasta_profilde_mi` ile aynı kural):
        yazılmış profil → yalnız o; boş (eski) kayıt → `ESKI_HASTA_PROFILLERI`. Profil yok → koşul YOK (eski istemci)."""
        from utils.profil import ESKI_HASTA_PROFILLERI, gecerli_profil

        p = gecerli_profil(profil)
        if not p:
            return "1 = 1", ()
        if p in ESKI_HASTA_PROFILLERI:
            return "(COALESCE(profil, '') = ? OR COALESCE(profil, '') = '')", (p,)
        return "COALESCE(profil, '') = ?", (p,)

    def count_patients(self, profil: Optional[str] = None) -> int:
        """Toplam hasta sayisi (sayfalamada 'total' icin — desifre GEREKTIRMEZ). SG.G1: `profil` verilirse o profilinkiler."""
        kosul, param = self._profil_kosulu(profil)
        with self.lock:
            try:
                with self._get_connection() as conn:
                    return int(
                        conn.cursor().execute(f"SELECT COUNT(*) FROM patients WHERE {kosul}", param).fetchone()[0]
                    )
            except _DB_ERROR:
                self._db_hatasini_yaz("hasta sayimi")
                return 0

    def get_all_patients(
        self, limit: int = 0, offset: int = 0, kati: bool = False, profil: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Hastalari getirir. limit>0 ise SAYFAYI SQL'de sinirlar (limit=0 → hepsi, geriye uyumlu).

        DENETIM P2: sayfalama YALNIZCA cagiran tarafinda (Python dilimi) yapiliyordu; bu metod
        her cagrida TUM hastalari cekip TUMUNUN alan-basi Fernet desifresini yapiyor ve bunu
        `self.lock` TUTARAK sonuclandiriyordu. Sonuc: /api/patients?limit=20 istegi bile binlerce
        kayitlik klinikte tum tabloyu desifre ediyor, o sure boyunca hasta-DB'sine erisen HER
        islem (yeni hasta, seans basligi, arama) blokleniyordu. Sayfalama artik SQL'e itiliyor →
        yalnizca istenen sayfa desifre edilir.
        """
        with self.lock:
            try:
                with self._get_connection() as conn:
                    conn.row_factory = self._row_factory
                    cursor = conn.cursor()
                    # SG.G1: profil süzgeci SQL'de (sayfalama süzülmüş kümeyle tutarlı); profil yoksa koşul her zaman doğru.
                    kosul, param = self._profil_kosulu(profil)
                    if limit and limit > 0:
                        cursor.execute(
                            f"SELECT * FROM patients WHERE {kosul} ORDER BY created_at DESC LIMIT ? OFFSET ?",
                            (*param, int(limit), max(0, int(offset))),
                        )
                    elif offset and offset > 0:
                        # LIMIT olmadan OFFSET SQLite'ta gecersiz → -1 "sinirsiz" demektir.
                        cursor.execute(
                            f"SELECT * FROM patients WHERE {kosul} ORDER BY created_at DESC LIMIT -1 OFFSET ?",
                            (*param, int(offset)),
                        )
                    else:
                        cursor.execute(f"SELECT * FROM patients WHERE {kosul} ORDER BY created_at DESC", param)
                    rows = cursor.fetchall()

                    patients: List[Dict[str, Any]] = []
                    for row in rows:
                        patient = dict(row)
                        patients.append(self._decrypt_patient_fields(patient))
                    return patients
            except _DB_ERROR:
                if kati:  # C2-1.2: "defter boş" ile "defter okunamadı" ayrılır (tek seferlik taşıma işaret koymasın)
                    raise
                self._db_hatasini_yaz("hasta listesi")
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
                            # CIPHERTEXT KORUMA (DENETIM P3): cozulemeyen alan UI'ya
                            # "[okunamayan kayıt]" olarak gider. Operator baska bir alani duzenleyip
                            # kaydettiginde form bu yer-tutucuyu AYNEN geri gonderiyordu → orijinal
                            # (belki dogru anahtarla hala kurtarilabilir) ciphertext bu sabit metnin
                            # sifrelenmis haliyle EZILIYOR ve hasta verisi KALICI kayboluyordu.
                            # Yer-tutucu geldiginde o alani GUNCELLEME (mevcut deger korunur).
                            if isinstance(value, str) and value.strip() == _UNREADABLE_PLACEHOLDER:
                                self.logger.warning(
                                    "Hasta %s alani '%s' cozulemeyen yer-tutucu ile geri yazilmak "
                                    "istendi → ATLANDI (orijinal sifreli deger korundu).",
                                    patient_id,
                                    key,
                                )
                                continue
                            updates.append(f"{key} = ?")
                            values.append(self._encrypt_field(value))

                    if not updates:
                        return False

                    # Eksik-taraması P2 (2026-08-22): anonim kayda GERÇEK PII geri yazılırsa bayrak
                    # SIFIRLANIR — yoksa kayıt retention döngüsünden SONSUZA DEK muaf kalıyordu
                    # (COALESCE(anonymized,0)=0 filtresi onu bir daha görmez; sessiz KVKK boşluğu).
                    # Reddetmek yerine sıfırlama seçildi: meşru senaryo var (hasta geri geldi).
                    # Tür/ırk PII-DIŞI sayılır (anonimleştirme de onları korur) — yalnız kimlik
                    # kuran alanlar bayrağı düşürür; boş/yer-tutucu değer kimlik KURMAZ.
                    _PII_ALANLAR = {"name", "owner", "vet_contact", "owner_email", "age", "weight"}
                    _pii_geri_yazildi = any(
                        k in _PII_ALANLAR and isinstance(v, str) and v.strip() and v.strip() != _UNREADABLE_PLACEHOLDER
                        for k, v in patient_info.items()
                    )
                    if _pii_geri_yazildi:
                        updates.append("anonymized = 0")

                    updates.append("updated_at = ?")
                    values.append(datetime.now().isoformat())
                    values.append(patient_id)

                    query = f"UPDATE patients SET {', '.join(updates)} WHERE id = ?"
                    cursor.execute(query, values)
                    # ⚠️ D2.27 (B-3.111): sonuç UPDATE'in KENDİ rowcount'undan, indeks tazelemesinden ÖNCE alınır. Tazeleme
                    # aynı imleçte DELETE (+ varsa INSERT) koşar → eskiden dönüş SON ifadenin sayısıydı: aranabilir
                    # alanları boş hastada 0 → False → uç "error", arayüz "hata oluştu" diyordu; oysa yazım COMMIT
                    # edilmişti (ölçüldü). Kapı: tests/test_hasta_kismi_guncelleme.py::test_KRITIK_D227_…
                    guncellendi = cursor.rowcount > 0
                    if guncellendi:
                        self._refresh_search_index_for_patient(cursor, patient_id)
                    conn.commit()
                    return guncellendi
            except _DB_ERROR:
                self._db_hatasini_yaz("hasta guncelleme")
                return False

    def touch_last_treatment(self, patient_id: str) -> None:
        """KVKK retention: bir tedavi gerceklestiginde hastanin last_treatment_at'ini guncelle
        (inaktiflik-bazli anonimlestirmenin tarih kaynagi). Hata sessizce loglanir (tedaviyi bloklamaz)."""
        if not patient_id:
            return
        try:
            with self.lock:
                with self._get_connection() as conn:
                    conn.execute(
                        "UPDATE patients SET last_treatment_at = ? WHERE id = ?",
                        (datetime.now().isoformat(), patient_id),
                    )
                    conn.commit()
        except Exception:
            self.logger.debug("touch_last_treatment hatasi", exc_info=True)

    def anonimlestirilecek_hastalar(self, inactive_days: int = 1825) -> List[Dict[str, Any]]:
        """D2.54 · A-06: anonimleştirmeyi BEKLEYEN hastalar (kuru — hiçbir şey değiştirmez) → [{id, name, owner, owner_email}]
        (şifresi çözülmüş). Operatöre "kaç hasta" sorusunu sormak ve tedavi-DB adımının kimlik metinlerini kanonik adımdan ÖNCE kalıcı
        bekleyen listeye yazmak için. Okuma hatası YÜKSELİR (çağıran turu atlar; "0 bekleyen" yalanı yok)."""
        if int(inactive_days) <= 0:
            return []
        cutoff = (datetime.now() - timedelta(days=int(inactive_days))).isoformat()
        with self.lock:
            with self._get_connection() as conn:
                conn.row_factory = self._row_factory
                satirlar = conn.execute(
                    "SELECT id, name, owner, owner_email FROM patients WHERE COALESCE(anonymized,0)=0 "
                    "AND COALESCE(last_treatment_at, created_at) < ?",
                    (cutoff,),
                ).fetchall()
                return [self._decrypt_patient_fields(dict(r)) for r in satirlar]

    def anonymize_inactive_patients(self, inactive_days: int = 1825, yalniz=None) -> List[str]:
        """KVKK: son tedaviden (yoksa kayit tarihinden) inactive_days'ten (vars. 5 YIL=1825) uzun
        sure gecmis hastalarin PII'sini (ad/sahip/iletisim/e-posta) ANONIMLESTIR — SILMEZ (klinik
        istatistikleri/tedavi gecmisi korunur). Muafiyet yok. Anonimlestirilen UUID listesini doner
        (treatment-history DB'deki hasta kopyasi da guncellensin diye).

        ⚠️ D2.54 · A-06: `yalniz` verilirse YALNIZ o kimlikler (hâlâ aday olanlar) anonimleşir — operatörün onayladığı ve kimlik
        metinleri tedavi-DB adımı için kalıcı listeye yazılmış aday kümesi; tur sırasında aday olan YENİ hasta bu turda işlenmez."""
        # ⚠️ F2-1.8 (2-F incelemesi · D2.49 kuralı): süre 0/negatif → HİÇBİR hasta anonimleşmez. Eskiden `max(1, …)` 0'ı 1 GÜNE
        # çeviriyordu: dünden önce tedavi görmüş TÜM hastalar geri dönüşsüz anonimleşirdi (ölçüldü).
        if int(inactive_days) <= 0:
            return []
        cutoff = (datetime.now() - timedelta(days=int(inactive_days))).isoformat()
        anonymized: List[str] = []
        try:
            with self.lock:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT id FROM patients WHERE COALESCE(anonymized,0)=0 "
                        "AND COALESCE(last_treatment_at, created_at) < ?",
                        (cutoff,),
                    )
                    ids = [r[0] for r in cursor.fetchall()]
                    if yalniz is not None:
                        izinli = {str(x) for x in yalniz}
                        ids = [i for i in ids if str(i) in izinli]
                    enc_anon = self._encrypt_field("[ANONIM]")
                    enc_empty = self._encrypt_field("")
                    now_iso = datetime.now().isoformat()
                    for pid in ids:
                        cursor.execute(
                            # Audit P2: sync_status=0 → anonimleştirme (redaction) bulut PUSH ile
                            # yayılsın; aksi halde sonraki PULL orijinal PII'yi geri yazıp de-anonymize ediyordu.
                            # Eksik-taraması P2 (2026-08-22): YAŞ+KİLO da silinir — küçük klinikte
                            # (tür, ırk, yaş, kilo) dörtlüsü tek hastayı işaret eder (re-identification).
                            # Tür/ırk BİLEREK kalır: klinik istatistikleri anonimleştirmenin amacı
                            # gereği korunur; en ayırt edici ikili olan yaş+kilo yeterli kırpmadır.
                            "UPDATE patients SET name=?, owner=?, vet_contact=?, owner_email=?, "
                            "age=?, weight=?, "
                            "anonymized=1, sync_status=0, updated_at=? WHERE id=?",
                            (enc_anon, enc_anon, enc_empty, enc_empty, enc_empty, enc_empty, now_iso, pid),
                        )
                        # Arama indeksini tazele — eski ad/sahip token'lari gitsin (artik aranmaz).
                        self._refresh_search_index_for_patient(cursor, pid)
                    conn.commit()
            # Audit P2: pid'leri YALNIZ commit BASARILI olduktan sonra raporla. Eskiden dongu-ici
            # append + orta-hata rollback'i → patients.db PII'yi TUTAR ama caller 'anonimlestirildi'
            # sanip history-DB'yi anonimlestirir (iki-DB tutarsizligi + KVKK retention ihlali).
            anonymized = list(ids)
            if anonymized:
                self.logger.warning(
                    "KVKK: %d inaktif hasta (>%d gun) anonimlestirildi.", len(anonymized), inactive_days
                )
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
                if rowcount > 0:
                    self._silme_sonrasi_denetim_noktasi(conn, "hasta silme")
                return rowcount > 0
        except _DB_ERROR:
            self._db_hatasini_yaz("hasta silme")
            return False
        finally:
            self.lock.release()

    #: F2-4.3: denetim noktasının okuyucuyu (ve arkasında bloklanan yazarları) bekleme sınırı — tedavi DB'sindeki eşiyle aynı.
    DENETIM_NOKTASI_BEKLEME_MS = 200

    def _silme_sonrasi_denetim_noktasi(self, conn, ne: str) -> bool:
        """D2.29 (Y13): silmeden sonra WAL denetim noktası (TRUNCATE) — `secure_delete` yeni sayfa sürümünü sıfırlar ama WAL kipinde
        eski sayfa denetim noktasına kadar ana dosyada, eklemenin çerçevesi WAL dosyasında durur (ölçüldü). Okuyucu varsa
        tamamlanamayabilir → uyarı; silme sonucu DEĞİŞMEZ. (Tedavi DB'sindeki eşi: `thdb_ai_gecmisi._silme_sonrasi_denetim_noktasi`.)
        ⚠️ F2-4.3: TRUNCATE okuyucuyu beklerken yeni yazarları da bloklar → kısa bekleme (`DENETIM_NOKTASI_BEKLEME_MS`); tamamlanamazsa
        kalıcı işaret (F2-2.5) ve günlük bakımda yeniden."""
        try:
            onceki = conn.execute("PRAGMA busy_timeout").fetchone()[0]
            conn.execute(f"PRAGMA busy_timeout={int(self.DENETIM_NOKTASI_BEKLEME_MS)}")
            try:
                sonuc = conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
            finally:
                conn.execute(f"PRAGMA busy_timeout={int(onceki)}")
            if sonuc and sonuc[0]:
                self.logger.warning(
                    "%s: silme sonrasi denetim noktasi tamamlanamadi (acik okuyucu) — silinen icerik sonraki denetim noktasina "
                    "dek WAL'da kalabilir; kalici isaretle gunluk bakimda yeniden denenecek.",
                    ne,
                )
                # F2-2.5: kalıntı için kalıcı işaret (Y121'in işareti) — günlük bakım seans yokken VACUUM + denetim noktasını yeniden dener.
                self._vacuum_isaretini_yaz("1")
                return False
            return True
        except Exception:
            self.logger.warning("%s: silme sonrasi denetim noktasi yapilamadi.", ne, exc_info=True)
            self._vacuum_isaretini_yaz("1")
            return False

    #: Tek istekte silinebilecek AZAMİ hasta sayısı (seans tarafıyla AYNI gerekçe ve AYNI sayı).
    TOPLU_SILME_AZAMI = 500

    def delete_patients_bulk(self, patient_ids) -> int:
        """Birden çok hastayı TEK İŞLEMDE (atomik) siler; silinen kayıt sayısını döndürür.

        ⚠️ NEDEN DÖNGÜYLE `delete_patient` DEĞİL: 40 hastadan 23.'sünde hata çıkarsa yarısı
        gitmiş olur ve operatör hangisinin gittiğini bilemez — geri alınamaz bir işlemde
        "kısmen oldu" en kötü sonuçtur. `clear_all_patients` ile aynı atomiklik gerekçesi (P3).

        ⚠️ ARAMA İNDEKSİ DE SİLİNİR: eskiden `patient_search_index` orphan kalırsa silinmiş bir
        hasta aramada görünmeye devam ediyordu.
        """
        kimlikler = [str(x) for x in (patient_ids or ()) if str(x or "").strip()]
        kimlikler = sorted(set(kimlikler))
        if not kimlikler:
            return 0
        if len(kimlikler) > self.TOPLU_SILME_AZAMI:
            raise ValueError(f"Tek istekte en fazla {self.TOPLU_SILME_AZAMI} hasta silinebilir.")
        if not self.lock.acquire(timeout=10.0):
            return 0
        try:
            yer = ",".join("?" for _ in kimlikler)
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(f"DELETE FROM patients WHERE id IN ({yer})", kimlikler)
                silinen = cursor.rowcount if cursor.rowcount and cursor.rowcount > 0 else 0
                cursor.execute(f"DELETE FROM patient_search_index WHERE patient_id IN ({yer})", kimlikler)
                conn.commit()
                if silinen:
                    self._silme_sonrasi_denetim_noktasi(conn, "toplu hasta silme")  # D2.29 · Y13
                return silinen
        except _DB_ERROR:
            self._db_hatasini_yaz("toplu hasta silme")
            return 0
        finally:
            self.lock.release()

    def clear_all_patients(self, profil: Optional[str] = None) -> tuple:
        """Tum hasta kayitlarini temizler → `(silinen, vacuum_ok)`; DELETE düşerse `(-1, False)` (kayıtlar DURUR).

        ⚠️ SG.G1: `profil` verilirse kapsam YALNIZ DARALIR — yalnız o profilin listesinde GÖRÜNEN hastalar (`_profil_kosulu`;
        liste ile AYNI koşul). Profil yoksa bugünkü gibi tamamı.

        ⚠️ D2.57 (B-3.109): DELETE commit edildikten SONRA VACUUM düşerse (disk dolu / G-Ç) silme GERÇEKLEŞMİŞTİR — sonuç
        "silindi, VACUUM başarısız" olarak AYRI bildirilir. Eskiden ikisi tek `try`'daydı: `False` dönüyor, KVKK denetim izi
        "hata" yazıyor, arayüz "başarısız" deyip listeyi yenilemiyordu (operatör verinin durduğunu sanıyordu)."""
        with self.lock:
            try:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    kosul, param = self._profil_kosulu(profil)
                    cursor.execute(f"SELECT COUNT(*) FROM patients WHERE {kosul}", param)
                    silinen = int(cursor.fetchone()[0] or 0)
                    if param:
                        cursor.execute(
                            f"DELETE FROM patient_search_index WHERE patient_id IN (SELECT id FROM patients WHERE {kosul})",
                            param,
                        )
                    else:
                        cursor.execute("DELETE FROM patient_search_index")
                    cursor.execute(f"DELETE FROM patients WHERE {kosul}", param)
                    conn.commit()
            except _DB_ERROR:
                self.logger.exception("Toplu hasta silme basarisiz (kayitlar DURUYOR).")
                return -1, False
            try:
                with self._get_connection() as conn:
                    conn.cursor().execute("VACUUM")
                    # Y121: WAL kipinde eski sayfalar denetim noktasına kadar ana dosyada kalır (ölçüldü) → TRUNCATE.
                    self._silme_sonrasi_denetim_noktasi(conn, "toplu hasta silme VACUUM")
                return silinen, True
            except _DB_ERROR:
                self.logger.warning(
                    "Hastalar SILINDI ama VACUUM yapilamadi — silinen veri dosyanin bos sayfalarinda kalabilir; "
                    "kalici 'VACUUM bekliyor' isaretiyle acilista ve gunluk bakimda yeniden denenecek (Y121).",
                    exc_info=True,
                )
                # ⚠️ Y121 (S-C.3 · D2.57): eskiden kimse yeniden denemiyordu — silinen kayıtlar süresiz dosyada kalıyordu.
                # Kapı: tests/test_hasta_DB_VACUUM_bekliyor_KALICI_Y121.py
                self._vacuum_isaretini_yaz("1")
                return silinen, False

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
                self._db_hatasini_yaz("hasta arama")
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
                self._db_hatasini_yaz("hasta sayimi")
                return 0


_patient_db = None
_patient_db_lock = threading.Lock()
#: D1.37 (B-3.8): backend AÇILIŞINDA açılamayan hasta DB yolu → neden. İSTEK YOLUNDA yeniden DENENMEZ
#: (bkz. `treatment_history_db._acilis_kilidi` — aynı gerekçe: her istekte ≥6 sn göç denemesi); Y43: yalnız arka
#: plan yeniden açması (`acilista_acilamayani_yeniden_ac`) başarıyla KALDIRIR.
_acilis_kilidi: dict[str, str] = {}


def _kilit_anahtari(db_path) -> str:
    return os.path.normcase(os.path.abspath(str(db_path)))


def acilis_hatasini_kilitle(app_data_dir, exc: BaseException) -> None:
    """İstek yolunda bu hasta DB'sini açmayı bırak: sonraki `get_patient_database` HEMEN `RuntimeError` verir
    (arka plan yeniden açması başarılı olana dek — Y43)."""
    with _patient_db_lock:
        _acilis_kilidi[_kilit_anahtari(Path(app_data_dir) / "patients.db")] = type(exc).__name__


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
            kilit = _acilis_kilidi.get(_kilit_anahtari(db_file))
            if kilit is not None:
                raise RuntimeError(
                    f"Hasta DB'si acilista ACILAMADI ({kilit}); istek yolunda denenmez, arka planda yeniden deneniyor."
                )
            _patient_db = PatientDatabase(str(db_file))
    return _patient_db


def acilista_acilamayani_yeniden_ac(app_data_dir) -> PatientDatabase:
    """Y43 (sahip — D1.37 devamı): açılışta açılamamış hasta DB'sini ARKA PLAN iş parçacığından yeniden aç.
    Kurucu `_patient_db_lock` DIŞINDA koşar (bkz. `treatment_history_db.acilista_acilamayani_yeniden_ac`)."""
    global _patient_db
    db_file = Path(app_data_dir) / "patients.db"
    with _patient_db_lock:
        if _patient_db is not None:
            _acilis_kilidi.pop(_kilit_anahtari(db_file), None)
            return _patient_db
    yeni = PatientDatabase(str(db_file))
    with _patient_db_lock:
        if _patient_db is None:
            _patient_db = yeni
        _acilis_kilidi.pop(_kilit_anahtari(db_file), None)
        return _patient_db
