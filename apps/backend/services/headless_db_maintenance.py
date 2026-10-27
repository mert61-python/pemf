"""Qt-free DB bakım/retention/backup/disk-check zamanlayıcısı (headless üretim servisi).

Eski DBMaintenanceService PyQt6 QTimer'a bağlıydı ve yalnız legacy GUI'de başlatılıyordu →
headless backend'de retention/PII-redaction/backup/disk-check HİÇ çalışmıyordu (KVKK/GDPR +
sınırsız veri büyümesi + yedek yok). Bu modül aynı DB metotlarını Qt'siz daemon thread ile
periyodik çağırır. apply_data_retention_policy() purge (sensor/event/outbox) + PII-redaction'ı
zaten içerir.
"""

import logging
import os
import threading
import time
from datetime import datetime
from pathlib import Path

from utils.backup_recovery import KURTARMA_EXE_NOTU, kurtarma_komutu
from utils.dongu_guvenligi import dongu_hatasini_bildir

logger = logging.getLogger(__name__)

# DENETIM P2: off-machine yedeklerin YANINA birakilan kurtarma notu. Kurtarma anindaki kisi
# (baska bir teknisyen, aylar sonra) log'lara bakamaz; "sifreli .db var ama acilmiyor" ile
# bas basa kalmasin diye NE GEREKTIGI dosyanin yanina yazilir.
_OFFSITE_README_NAME = "OKU-KURTARMA.txt"
#: Operatör hesapları DB'si (`database/auth_db.AuthDB`: `<veri dizini>/auth_users.db`) — D2.51 (A-32) yedek kapsamı.
_HESAP_DB_ADI = "auth_users.db"
# ⚠️ D2.75 (B-11.5): komutlar `utils.backup_recovery.kurtarma_komutu` TEK kaynağından (`@@…@@` yer tutucuları aşağıda doldurulur);
# eskiden `python tools/kurtarma.py` yazıyordu — sahada Python YOK, çalışan yol `PEMF_Backend.exe --kurtarma`.
_OFFSITE_README_SABLON = """PEMF — YEDEK KURTARMA NOTU
=============================================================
Bu dizindeki .db dosyalari SQLCipher ile SIFRELIDIR (sifreli kurulumda).

DOSYALAR — her turden SON N kopya tutulur, eskilerini cihaz SILER
  pemf_treatment_history_<tarih>.db    tedavi gecmisi
  pemf_patients_<tarih>.db             hasta kartlari
  pemf_auth_users_<tarih>.db           operator hesaplari
  pemf_config_<tarih>.json             ayarlar (SIRSIZ: parola/anahtar YOK)
  pemf_system_settings_<tarih>.json    sistem ayarlari (SIRSIZ)
  Cihaz YALNIZ bu adlardaki kendi dosyalarini siler; bu dizindeki baska
  dosyalara dokunmaz. Her cihaz AYRI dizin kullanmalidir: dizinde baska bir
  kurulumun .pemf_kurulum_* isareti varsa cihaz bu dizinde HIC silmez. Kaldirma / "tam temizlik" bu dizine HIC dokunmaz —
  gerekmiyorsa yedekleri elle silin.

Sifre-cozme anahtari yedegi ALAN MAKINEYE baglidir (Windows DPAPI /
CRYPTPROTECT_LOCAL_MACHINE). Bu yuzden .db dosyalari TEK BASINA yetmez.

KURTARMA ZARFI
  Bu dizinde  kurtarma-zarfi.enc  varsa, veritabani anahtarlari onun icinde
  KURTARMA KODU ile sifreli olarak durur. Kod + zarf ile yedekler BASKA bir
  makinede acilabilir.

  Kurtarma kodu, kurulum makinesinde bir kez uretilip
  <veri-dizini>\\KURTARMA-KODU.txt  dosyasina yazilir ve operator tarafindan
  makine disinda (kasa / parola yoneticisi) saklanmalidir.
  Kod BU DIZINDE SAKLANMAZ — zarf ve kod ayni yerde durursa koruma kalmaz.

NASIL GERI YUKLENIR
  1) Yeni makineye PEMF kurun (henuz baslatmadan).
  2) Anahtarlari zarftan cikarip yerlestirin (Komut Istemi / cmd penceresinde):
       @@KURTARMA_ZARF@@
@@KURTARMA_EXE_NOTU@@
  3) Bu dizindeki  pemf_treatment_history_*.db / pemf_patients_*.db  dosyalarindan
     en yenisini veri dizinine  pemf_treatment_history.db / patients.db
     adiyla kopyalayin.
     (⚠️ 2026-08-15: hedef ad `pemf_patients.db` yaziliyordu; uygulama O ADI HIC ACMAZ →
      yonergeyi izleyen klinik hasta kayitlarini geri yukledigini sanip bos liste gorurdu.
      YEDEK dosya on-eki `pemf_patients_<tarih>.db` DEGISMEDI — rotasyon onu kullanir.)
  3b) Operator hesaplari: pemf_auth_users_<tarih>.db sifreliyse (2. adimdan SONRA):
       @@KURTARMA_HESAP@@
      Sifresiz kurulumda dosyayi  auth_users.db  adiyla kopyalamak yeter.
  3c) Ayarlar:  pemf_config_<tarih>.json -> config.json,
      pemf_system_settings_<tarih>.json -> system_settings.json.
      MQTT kullanici/parola ve API anahtari bu kopyalarda YOKTUR — yeniden girin.
  4) Servisi baslatin.

ZARF YOKSA
  Kurtarma icin sunlardan biri gerekir:
    1) Yedegi alan makinedeki  pemf_secrets.json  (yalniz AYNI makinede cozulur), VEYA
    2) Disari alinmis  sqlcipher_key  ve  patient_fernet_key  degerleri.
  Ikisi de yoksa bu yedekler kurtarilamaz.
=============================================================
"""
# ⚠️ E2-3.7: dosya yolları `<bu-dizin>\` ile — cmd %USERPROFILE%'da açılır, göreli ad "zarf bulunamadi" verir.
_OFFSITE_README_TEXT = (
    _OFFSITE_README_SABLON.replace(
        "@@KURTARMA_ZARF@@", kurtarma_komutu("--zarf", "<bu-dizin>\\kurtarma-zarfi.enc", "--kod", "<KOD>", "--yaz")
    )
    .replace(
        "@@KURTARMA_HESAP@@",
        kurtarma_komutu(
            "--hesap-yedegi", "<bu-dizin>\\pemf_auth_users_<tarih>.db", "--cikti", "<veri-dizini>\\auth_users.db"
        ),
    )
    .replace("@@KURTARMA_EXE_NOTU@@", KURTARMA_EXE_NOTU.rstrip("\n"))
)

#: D2-1.1: dosya zamanı bu kadar saniyeden fazla İLERİDEYSE saat güvenilmez sayılır (tazelik kararında yok sayılır).
_SAAT_TOLERANSI_SN = 600.0

#: D2-1.4: bu kadar saniyeden eski kendi-adlı geçici yedek artığı (`.yazim.tmp` / `.kopya.tmp`) yarıda kalmış sayılır ve silinir.
_ARTIK_YASI_SN = 3600.0

#: D2-1.2: makine dışı hedefteki kurulum işaret dosyası öneki (rotasyon deseni `pemf_<aile>_<damga>` ile EŞLEŞMEZ).
_KURULUM_ISARETI = ".pemf_kurulum_"

_worker = None  # type: Optional[HeadlessDBMaintenance]


class HeadlessDBMaintenance:
    def __init__(
        self,
        app_data_dir=None,
        maintenance_interval_hours: int = 6,
        backup_interval_hours: int = 24,
        disk_check_interval_minutes: int = 30,
        backup_retention_keep: int = 14,
    ):
        from database.treatment_history_db import get_treatment_db
        from utils.path_utils import get_app_data_directory

        self.app_data_dir = Path(app_data_dir) if app_data_dir else get_app_data_directory()
        self.db = get_treatment_db(self.app_data_dir)
        # audit B-7.2: PatientDB de yedeklensin (eskiden yalnız treatment yedekleniyordu).
        try:
            from database.patient_database import get_patient_database

            self.patient_db = get_patient_database()
        except Exception:
            self.patient_db = None
        self.maint_interval = max(1, maintenance_interval_hours) * 3600
        self.backup_interval = max(1, backup_interval_hours) * 3600
        self.disk_interval = max(1, disk_check_interval_minutes) * 60
        self.backup_retention_keep = max(1, backup_retention_keep)
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._loop, daemon=True, name="DBMaintenance")
        self._thread.start()
        logger.info("Headless DB bakim servisi baslatildi (retention/PII-redaction/backup/disk-check aktif).")

    def stop(self):
        self._stop.set()
        # In-progress bakim/backup turunun bitmesine kisa sure taniy → servis kapanirken
        # yaridan kesik/bozuk SQLite yedegi veya kilitli DB dosyasi birakilmaz.
        t = self._thread
        if t and t.is_alive():
            t.join(timeout=10.0)

    def _loop(self):
        last_maint = last_disk = 0.0
        last_backup = None
        first = True
        while not self._stop.is_set():
            now = time.monotonic()
            try:
                if now - last_disk >= self.disk_interval:
                    self._check_disk()
                    last_disk = now
                if first or now - last_maint >= self.maint_interval:
                    self._run_maintenance()
                    last_maint = now
                # DENETIM P2 (restart-dongusu yedek imhasi): kosul `first or ...` idi → servis HER
                # acilista yedek aliyordu. Rotasyon yalnizca son N yedegi tuttugundan, bir crash-loop
                # ya da operatorun art arda yeniden baslatmasi N acilista TUM YEDEK GECMISINI ayni
                # gunun kopyalariyla degistiriyordu (felaket-kurtarma penceresi yok olur).
                # Cozum: acilista yedek al AMA yalnizca diskteki EN YENI yedek bayatsa. Boylece
                # "servis uzun sure kapali kaldi" durumu yine yedeklenir, restart dongusu yedegi imha etmez.
                # ⚠️ D2.63 (B-3.11): açılış kararı YALNIZ diskteki en yeni AÇILABİLEN yedeğin yaşından verilir. Eskiden koşul
                # `(first and not recent) or now - last_backup >= interval` ve `last_backup = 0.0` idi: `now` monotonic olduğu
                # için 24 saatten uzun açık makinede ikinci terim ilk turda hep doğruydu → koruma ölü, her yeniden başlatma
                # yedek alıyordu (ölçüldü). Atlanan açılış yedeğinde sayaç o yedeğin YAŞINA göre kurulur: sonraki yedek
                # "en yeni yedek + aralık"ta gelir (şimdiye kurmak 2 güne yakın gecikme demekti).
                # Kapı: tests/test_yerel_yedek_penceresi_KORUNUR_D263.py
                if first:
                    yas = self._en_yeni_gecerli_yedek_yasi()
                    if yas is None or yas >= self.backup_interval:
                        self._run_backup()
                        last_backup = now
                    else:
                        logger.info("Acilis yedegi ATLANDI: diskte taze yedek var (restart-dongusu korumasi).")
                        last_backup = now - yas
                elif last_backup is None or now - last_backup >= self.backup_interval:
                    self._run_backup()
                    last_backup = now
            except Exception:
                # D1.18 (B-4.17): bildirim fırlatırsa bakım/yedek/disk denetimi süreç ömrü boyunca ölürdü.
                dongu_hatasini_bildir("DB bakim turu hatasi", logger=logger)
            first = False
            self._stop.wait(60)

    def _check_disk(self):
        try:
            status = self.db.get_disk_space_status()
            if bool(status.get("critical", False)):
                logger.warning("DISK KRITIK: %sMB < %sMB", status.get("free_mb"), status.get("threshold_mb"))
        except Exception:
            logger.exception("disk check hatasi")

    @staticmethod
    def _retain_days(env_name: str, default: int) -> int:
        """Retention suresi (gun). Tanimsiz → varsayilan. 0 → O ADIM KAPALI.

        ⚠️ S-F2-1.5 (2-F incelemesi · Y123): GECERSIZ ya da BOS deger → adim KAPALI (0) + WARNING. Eskiden varsayilana dusuyordu →
        niyeti okunamayan (ör. 'silme' niyetiyle bos birakilmis `PEMF_RETAIN_DOSE_DAYS=`) geri donussuz silme SURUYORDU. Ekran
        (`/api/settings/retention`) ve gunluk dongunun olay silmesi de BU okuyucuyu kullanir (tutarli).
        Kapi: tests/test_saklama_GECERSIZ_ya_da_BOS_deger_adimi_KAPATIR_SF215.py"""
        ham = os.environ.get(env_name)
        if ham is None:
            return default
        try:
            return int(ham)
        except (TypeError, ValueError):
            logger.warning(
                "%s gecersiz (%r) — bu saklama adimi KAPALI (hicbir sey silinmez/maskelenmez); gecerli gun sayisi yazin.",
                env_name,
                ham,
            )
            return 0

    #: ⚠️ D2.44 (O-B2.1): `api_server` günlük döngüsünün okuduğu, hiçbir yerde belgelenmemiş ESKİ sensör saklama adı.
    _ESKI_SENSOR_ADI = "PEMF_SENSOR_RETAIN_DAYS"

    @classmethod
    def _eski_sensor_adiyla(cls, yeni_ad_degeri: int) -> int:
        """Sensör saklama süresi: `PEMF_RETAIN_SENSOR_DAYS` (vars. 90, 0 = adım kapalı) — çağıran onu okuyup buraya verir.

        ⚠️ D2.44 (B-4.18 · O-B2.1): eski ad `PEMF_SENSOR_RETAIN_DAYS` YALNIZ yeni ad ayarlanmamışsa takma ad olarak uygulanır ve
        uyarı yazılır — eski ada "0" (silme) yazmış klinikte telemetri sessizce 90 günde silinmesin. İkisi birden varsa YENİ ad kazanır.
        Günlük döngü (`api_server`) artık sensör silmez; tek silici burası. Kapı: tests/test_bakim_TEK_silici_sensor_sozlesmesi_D244.py"""
        if os.environ.get("PEMF_RETAIN_SENSOR_DAYS") is None and os.environ.get(cls._ESKI_SENSOR_ADI) is not None:
            gun = cls._retain_days(cls._ESKI_SENSOR_ADI, 90)
            logger.warning(
                "%s KULLANIMDAN KALKTI — %d gun uygulandi; dagitim dosyasinda (device.env) PEMF_RETAIN_SENSOR_DAYS yazin.",
                cls._ESKI_SENSOR_ADI,
                gun,
            )
            return gun
        return yeni_ad_degeri

    def _run_maintenance(self):
        try:
            m = self.db.run_maintenance()
            # DENETIM P2: apply_data_retention_policy() PARAMETRESIZ cagriliyordu → sabit-kodlu
            # 90/365/30/365 gun ZORLANIYORDU ve bobin-calisma kayitlari + seans olaylari
            # GERI DONUSSUZ siliniyor, hasta/operator adlari maskeleniyordu; opt-out YOKTU.
            # Tibbi-hukuki saklama suresi ulkeye/kliniğe gore degisir → operator karari.
            # 0 = o adim KAPALI (hicbir sey silinmez/maskelenmez).
            r = self.db.apply_data_retention_policy(
                sensor_retain_days=self._eski_sensor_adiyla(self._retain_days("PEMF_RETAIN_SENSOR_DAYS", 90)),
                # ⚠️ DOZ kaydı AYRI ayar (denetim 2026-08-17): uygulanan doz telemetri
                # saklama süresiyle silinemez. `0` = adım kapalı.
                dose_retain_days=self._retain_days("PEMF_RETAIN_DOSE_DAYS", 3650),
                event_retain_days=self._retain_days("PEMF_RETAIN_EVENT_DAYS", 365),
                dead_outbox_retain_days=self._retain_days("PEMF_RETAIN_OUTBOX_DAYS", 30),
                pii_retain_days=self._retain_days("PEMF_RETAIN_PII_DAYS", 365),
            )
            logger.info("DB bakim+retention tamam: maintenance=%s retention=%s", m, r)
        except Exception:
            logger.exception("maintenance hatasi")

    def _yedek_acilir_mi(self, yol: Path) -> bool:
        """Yedek dosyası bu kurulumun anahtarıyla AÇILIYOR mu? Hasta yedekleri hasta DB'siyle, yoksa tedavi DB'siyle (iki DB
        aynı birincil anahtarı kullanır) doğrulanır. Doğrulayıcı yoksa AÇILAMAZ sayılır. ASLA istisna atmaz.
        D2.51: hesap yedekleri de tedavi DB'siyle (aynı birincil anahtar); ayar yedekleri (`.json`) kökü sözlük olan geçerli JSON ise."""
        if yol.suffix == ".json":
            from database.yedek_dosyasi import json_yedegi_gecerli_mi

            return json_yedegi_gecerli_mi(yol)
        db = self.patient_db if yol.name.startswith("pemf_patients_") and self.patient_db is not None else self.db
        try:
            return bool(db.yedek_acilir_mi(yol))
        except Exception:
            logger.warning("Yedek dogrulanamadi: %s", yol, exc_info=True)
            return False

    def _en_yeni_gecerli_yedek_yasi(self):
        """Diskteki EN YENİ AÇILABİLEN tedavi yedeğinin yaşı (sn, ≥ 0) — yoksa None.

        "Son yedek ne zaman alındı" bilgisi ayrı bir durum dosyasında tutulmaz; yedek dosyalarının KENDİ mtime'ından türetilir —
        süreç yeniden başladığında da geçerli kalan tek gerçek kaynak budur.
        ⚠️ D2.63 (B-3.20): yalnız AÇILABİLEN yedek sayılır. Eskiden en yeni mtime'lı DOSYA alınıyordu: başarısız yedeğin bıraktığı
        0 baytlık artık "taze yedek" sayılıp açılış yedeğini 24 saat bastırıyordu (yedek sessizce alınmamış olur — ölçüldü).
        ⚠️ D2-1.1 (2-D incelemesi): mtime'ı GELECEKTE olan yedek (saat geri gitti ya da bir gün ileri gidip düzeldi) tazelik
        kararında SAYILMAZ. Eskiden "yaş 0 = taze" sayılıyordu: her gün kapanan klinik PC'sinde (süreç 24 saat yaşamaz) açılış yedeği
        o tarihe kadar HER GÜN atlanıyordu (ölçüldü). Kapı: tests/test_rotasyon_SAAT_GERIDE_bu_turun_yedegi_KALIR_D2_1_1.py"""
        try:
            backup_dir = self.app_data_dir / "backups"
            simdi = time.time()
            adaylar, gelecek = [], []
            for p in backup_dir.glob("pemf_treatment_history_*.db"):
                try:
                    st = p.stat()
                except OSError:
                    continue
                if st.st_size > 0:
                    (gelecek if st.st_mtime > simdi + _SAAT_TOLERANSI_SN else adaylar).append((st.st_mtime, p))
            if gelecek:
                logger.warning(
                    "Yedek tazeligi: %d yedegin tarihi GELECEKTE (%s) — sistem saati geride olabilir; bu yedekler tazelik "
                    "kararinda SAYILMADI.",
                    len(gelecek),
                    ", ".join(p.name for _m, p in gelecek[:3]),
                )
            for mtime, p in sorted(adaylar, key=lambda x: x[0], reverse=True):
                if self._yedek_acilir_mi(p):
                    return max(0.0, simdi - mtime)
            return None
        except Exception:
            logger.warning("yedek tazelik kontrolu basarisiz — yedek ALINACAK", exc_info=True)
            return None  # emin degilsek yedek AL (veri kaybetmektense fazladan yedek)

    def _recent_backup_exists(self) -> bool:
        """Diskteki EN YENİ AÇILABİLEN yedek `backup_interval`'dan taze mi? (restart-döngüsü korumasi)"""
        yas = self._en_yeni_gecerli_yedek_yasi()
        return yas is not None and yas < self.backup_interval

    def _run_backup(self):
        try:
            backup_dir = self.app_data_dir / "backups"
            backup_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            created = []
            # Tedavi geçmişi DB'si.
            backup_file = backup_dir / f"pemf_treatment_history_{stamp}.db"
            if self.db.create_backup(str(backup_file)):
                logger.info("Tedavi DB yedegi alindi: %s", backup_file)
                created.append(backup_file)
            else:
                logger.error("Tedavi DB yedegi BASARISIZ")
            # audit B-7.2: Hasta DB'si (eskiden yedeklenmiyordu).
            if self.patient_db is not None:
                pfile = backup_dir / f"pemf_patients_{stamp}.db"
                try:
                    if self.patient_db.create_backup(str(pfile)):
                        logger.info("Hasta DB yedegi alindi: %s", pfile)
                        created.append(pfile)
                except Exception:
                    logger.warning("Hasta DB yedegi hatasi", exc_info=True)
            # ⚠️ D2.51 (A-32, sahip kararı): operatör hesapları + config + sistem ayarları da yedeklenir; SIR dosyaları HARİÇ.
            created.extend(self._ek_kapsam_yedekle(backup_dir, stamp))
            self._cleanup_backups(backup_dir, frozenset(p.name for p in created))
            # DENETIM: kurtarma zarfi .db'lerden ONCE yazilir ki off-site kopyaya da GİRSİN —
            # zarfsiz bir off-site kopya donanim arizasindan sonra acilamaz.
            env = self._refresh_recovery(backup_dir)
            if env is not None:
                created.append(env)
            self._copy_offsite(created)  # audit B-7.2: off-machine kopya (PEMF_BACKUP_DIR)
        except Exception:
            logger.exception("backup hatasi")

    def _ek_kapsam_yedekle(self, backup_dir: Path, stamp: str) -> list:
        """⚠️ D2.51 (A-32, sahip kararı): otomatik yedek kapsamı — operatör hesapları (`auth_users.db`), `config.json`,
        `system_settings.json`. AÇIK İZİN LİSTESİ: yalnız bu üç dosya; SIR dosyaları (`pemf_secrets.json`, `.pemf_key`, `.sqlcipher_key`,
        `KURTARMA-KODU.txt`, `api_token.txt`, `admin_reset_code.txt`, cihaz kimliği) yapısal olarak kapsama GİREMEZ.
          · Hesap DB'si: şifreli kurulumda yedek BİRİNCİL anahtarla ŞİFRELİ (kaynak düz olsa da) — e-posta + 6 haneli PIN özeti makine
            dışına düz gitmez. Geri yükleme: `PEMF_Backend.exe --kurtarma --hesap-yedegi` (`kurtarma_komutu`).
          · Ayar dosyaları: SIRSIZ kopya — parola / jeton / API anahtarı / `enc:` değerleri ayıklanır (geri yüklemede yeniden girilir).
            Kaynak okunamazsa HAM kopya ALINMAZ (sır içerebilir).
        Biri düşerse ötekiler ve klinik DB yedekleri etkilenmez; düşen ERROR ile söylenir. Döndürür: üretilen yedek yolları.
        Kapı: tests/test_offsite_ROTASYON_ve_yedek_KAPSAMI_D251_Y11_A32_A45.py"""
        import json

        from database.yedek_dosyasi import duz_dbyi_yedekle, json_yedegi_yaz, sirsiz_ayarlar

        uretilen = []
        hesap = self.app_data_dir / _HESAP_DB_ADI
        if hesap.is_file():
            hedef = backup_dir / f"pemf_auth_users_{stamp}.db"
            try:
                mod, anahtar = self.db.yedek_sifre_bilgisi()
                duz_dbyi_yedekle(str(hesap), str(hedef), mod, anahtar, logger)
                logger.info("Hesap DB yedegi alindi (%s): %s", "sifreli" if anahtar else "sifresiz kurulum", hedef)
                uretilen.append(hedef)
            except Exception:
                logger.error("Hesap DB yedegi BASARISIZ — operator hesaplari bu turda YEDEKLENMEDI", exc_info=True)
        for kaynak_adi, tur in (("config.json", "config"), ("system_settings.json", "system_settings")):
            kaynak = self.app_data_dir / kaynak_adi
            if not kaynak.is_file():
                continue
            hedef = backup_dir / f"pemf_{tur}_{stamp}.json"
            try:
                veri = json.loads(kaynak.read_text(encoding="utf-8-sig"))
                if not isinstance(veri, dict):
                    raise ValueError("kok nesne sozluk degil")
                temiz, ayiklanan = sirsiz_ayarlar(veri, self._config_sir_yollari())
                json_yedegi_yaz(temiz, str(hedef), logger)
                logger.info("%s yedegi alindi (SIRSIZ; %d sir alani ayiklandi): %s", kaynak_adi, len(ayiklanan), hedef)
                uretilen.append(hedef)
            except Exception:
                logger.error(
                    "%s yedegi BASARISIZ (okunamadi / yazilamadi) — HAM kopya ALINMADI (sir icerebilir)",
                    kaynak_adi,
                    exc_info=True,
                )
        return uretilen

    @staticmethod
    def _config_sir_yollari() -> frozenset:
        """Config yöneticisinin ŞİFRELEDİĞİ anahtar yolları — ayar yedeğinden ayıklanır (ad deseni ve `enc:` önekine EK)."""
        try:
            from utils.production_config_manager import ProductionConfigManager

            return frozenset(ProductionConfigManager._ENCRYPTED_KEYS)
        except Exception:
            logger.warning(
                "config sir anahtari listesi okunamadi — yalniz ad deseni ve 'enc:' oneki ile ayiklanir", exc_info=True
            )
            return frozenset()

    def _refresh_recovery(self, backup_dir: Path):
        """DENETIM (offsite-backup-no-key-escrow): yedeklerin yanina kurtarma zarfini yaz.

        Zarf olmadan hicbir yedek — yerel ya da off-site — donanim arizasindan sonra
        acilamazdi (anahtar DPAPI ile makineye bagli). Zarf, sistem uretimi 150-bit
        kurtarma koduyla sifrelidir; kod operatorde, zarf yedeklerin yaninda durur.

        Yedek almanin KENDISI bundan etkilenmemeli → tum hatalar yutulur (zarf
        yazilamasa bile .db yedekleri alinmis olur). Returns: zarf yolu ya da None.
        """
        try:
            from utils.backup_recovery import ENVELOPE_NAME, refresh_recovery_material

            if refresh_recovery_material(self.app_data_dir, [backup_dir]):
                p = backup_dir / ENVELOPE_NAME
                return p if p.exists() else None
        except Exception:
            logger.warning("kurtarma zarfi guncellenemedi (yedekler ALINDI)", exc_info=True)
        return None

    def _cleanup_backups(self, backup_dir: Path, koru=frozenset()):
        """Yerel `backups/` rotasyonu — kural `_rotasyon`da (makine dışı hedefle AYNI).
        Kapılar: tests/test_yerel_yedek_penceresi_KORUNUR_D263.py · tests/test_offsite_ROTASYON_ve_yedek_KAPSAMI_D251_Y11_A32_A45.py"""
        self._rotasyon(backup_dir, "yerel", koru)

    def _rotasyon(self, dizin: Path, yer: str, koru=frozenset()):
        """Her yedek ailesinde son N AÇILABİLEN yedek kalır (N = `backup_retention_keep`). Yerel ve makine dışı hedefte AYNI kural.

        ⚠️ D2.63 (B-3.20): eskiden dosyalar YALNIZ adla sayılıyordu — 0 baytlık / başarısız yedek artıkları rotasyonda SAĞLAM
        yedeklerin yuvasını alıyor, en eski sağlam yedek siliniyordu (ölçüldü). Şimdi:
          · 0 baytlık dosya veri taşımaz → silinir;
          · DOLU ama bu kurulumun anahtarıyla AÇILAMAYAN dosya (anahtar değişiminden önceki yedek olabilir — kurtarılabilir veri)
            SİLİNMEZ ve geçerli yedek sayısına KATILMAZ; günlükte söylenir;
          · yalnız açılabilen yedekler arasında son N tutulur (ad = damga sırası).
        ⚠️ D2.51 (Y11 · A-45): makine dışı hedefe de uygulanır; bu yüzden kapsam DAR: YALNIZ `pemf_<aile>_<YYYYMMDD_HHMMSS><uzantı>`
        adlı (`yedek_dosyasi.yedek_ailesi`) DÜZENLİ dosyalar. Elle alınmış kopya, aynı adlı dizin, kısayol, kurtarma zarfı, not ve
        kullanıcı dosyaları YOK SAYILIR — hedef yanlışlıkla bir kullanıcı dizini seçilse de silme bu adlarla sınırlı kalır."""
        from database.yedek_dosyasi import yedek_ailesi

        try:
            girdiler = sorted(dizin.iterdir())
        except OSError:
            logger.warning("Yedek rotasyonu (%s): dizin listelenemedi: %s", yer, dizin, exc_info=True)
            return
        aileler: dict = {}
        simdi = time.time()
        for f in girdiler:
            aile = yedek_ailesi(f.name)
            if aile is not None:
                aileler.setdefault(aile, []).append(f)
                continue
            # ⚠️ D2-1.4 (2-D incelemesi): yazım/kopya ortasında ölen süreçten kalan KENDİ yedek adımızın geçicisi (`.yazim.tmp` /
            # `.kopya.tmp`) — yazıcılar yalnız AYNI adlı geçiciyi siler, damga her turda farklı → süresiz kalıyordu (ölçüldü). Yalnız
            # 1 saatten eski olanlar: taze geçici süren bir yazım ya da paylaşılan hedefte komşunun kopyası olabilir.
            for ek in (".yazim.tmp", ".kopya.tmp"):
                if f.name.endswith(ek) and yedek_ailesi(f.name[: -len(ek)]) is not None:
                    try:
                        if f.is_file() and not f.is_symlink() and simdi - f.stat().st_mtime > _ARTIK_YASI_SN:
                            f.unlink()
                            logger.info(
                                "Yarim kalmis yedek artigi silindi (%s; onceki yazim/kopya yarida kesilmis): %s",
                                yer,
                                f.name,
                            )
                    except OSError:
                        logger.warning("Yarim yedek artigi silinemedi (%s): %s", yer, f, exc_info=True)
        for aile, dosyalar in aileler.items():
            try:
                gecerli, acilamayan = [], []
                for f in dosyalar:
                    try:
                        if f.is_symlink() or not f.is_file():
                            continue
                        bos = f.stat().st_size == 0
                    except OSError:
                        logger.warning("Yedek rotasyonu (%s): dosya okunamadi, ATLANDI: %s", yer, f, exc_info=True)
                        continue
                    if bos:
                        try:
                            f.unlink(missing_ok=True)
                            logger.info("0 baytlik yedek artigi silindi (%s; veri tasimaz): %s", yer, f.name)
                        except OSError:
                            logger.warning("0 baytlik yedek artigi silinemedi (%s): %s", yer, f, exc_info=True)
                        continue
                    (gecerli if self._yedek_acilir_mi(f) else acilamayan).append(f)
                if acilamayan:
                    logger.warning(
                        "Yedek rotasyonu (%s): %d ACILAMAYAN yedek (%s) bu kurulumun anahtariyla acilmiyor — SAYILMADI ve SILINMEDI "
                        "(onceki bir anahtarla sifrelenmis olabilir; kurtarma zarfi/kodu ile acilabilir). Gerekmiyorsa elle kaldirin.",
                        yer,
                        len(acilamayan),
                        ", ".join(p.name for p in acilamayan[:5]),
                    )
                if len(gecerli) > self.backup_retention_keep:
                    for old in gecerli[: -self.backup_retention_keep]:
                        if old.name in koru:
                            # ⚠️ D2-1.1 (2-D incelemesi): BU TURUN yedeği en eski damgalı görünüyor = sistem saati geride. Ad sırasıyla
                            # silinseydi yeni yedek aynı turda giderdi ve saat damgayı geçene dek hiçbir yeni seans yedeğe girmezdi
                            # (ölçüldü). Bu turun yedeği kalır (son N + 1); bir sonraki turda bir önceki turunki silinir.
                            logger.error(
                                "Yedek rotasyonu (%s): bu turun yedegi %s mevcut yedeklerden ESKI damgali — sistem saati GERIDE "
                                "olabilir. Bu turun yedegi SILINMEDI; saati duzeltin.",
                                yer,
                                old.name,
                            )
                            continue
                        try:
                            old.unlink(missing_ok=True)
                        except OSError:
                            logger.warning("Eski yedek silinemedi (%s; yedekler birikir): %s", yer, old, exc_info=True)
            except Exception:
                logger.warning("Yedek rotasyonu uyarisi (%s, %s)", yer, aile, exc_info=True)

    @staticmethod
    def _dogrulanmis_kopya(kaynak: Path, hedef: Path) -> bool:
        """⚠️ D2.12 (B-3.19): `kaynak`ı `hedef`e DOĞRULANARAK kopyalar — geçici ada (`<ad>.kopya.tmp`), boyut + SHA-256 kaynakla eşitse
        `os.replace` ile son ada. Düşerse geçici silinir, son addaki ÖNCEKİ sağlam kopyaya dokunulmaz. Eskiden `shutil.copy2` doğrudan
        son ada yazıyordu: hedef dolunca / ağ kopunca YARIM dosya "yedek" adıyla kalıyordu."""
        import hashlib
        import shutil

        def _ozet(yol: Path) -> str:
            h = hashlib.sha256()
            with open(yol, "rb") as f:
                for parca in iter(lambda: f.read(1 << 20), b""):
                    h.update(parca)
            return h.hexdigest()

        gecici = hedef.with_name(hedef.name + ".kopya.tmp")
        try:
            shutil.copy2(kaynak, gecici)
            if gecici.stat().st_size != kaynak.stat().st_size or _ozet(gecici) != _ozet(kaynak):
                raise OSError(f"kopya kaynakla ESIT DEGIL: {gecici}")
            os.replace(gecici, hedef)
            return True
        except Exception:
            logger.warning("off-machine kopya hatasi (DOGRULANMADI): %s", kaynak, exc_info=True)
            try:
                if gecici.exists():
                    gecici.unlink()
            except OSError:
                logger.warning("off-machine gecici kopya silinemedi: %s", gecici, exc_info=True)
            return False

    def _kurulum_kimligi(self) -> str:
        """D2-1.2: bu kurulumun makine dışı işaret kimliği — yerel `backups/.kurulum_kimligi` (ilk çağrıda üretilir; SIR DEĞİL)."""
        import uuid

        yol = self.app_data_dir / "backups" / ".kurulum_kimligi"
        try:
            k = yol.read_text(encoding="utf-8").strip()
            if len(k) == 12 and all(c in "0123456789abcdef" for c in k):
                return k
        except FileNotFoundError:
            pass
        k = uuid.uuid4().hex[:12]
        yol.parent.mkdir(parents=True, exist_ok=True)
        yol.write_text(k, encoding="utf-8")
        return k

    def _makine_disi_paylasiliyor_mu(self, dpath: Path) -> bool:
        """D2-1.2 (A-45): hedefe bu kurulumun işaretini (`.pemf_kurulum_<kimlik>`) bırakır; BAŞKA bir kurulumun işareti varsa True + ERROR.
        Kapı: tests/test_makine_disi_rotasyon_YALNIZ_bu_kurulumun_kopyalarini_siler_D2_1_2.py"""
        ben = f"{_KURULUM_ISARETI}{self._kurulum_kimligi()}"
        (dpath / ben).write_text("PEMF kurulum isareti - bu dizine yedekleyen kurulum. Silmeyin.\n", encoding="utf-8")
        digerleri = sorted(p.name for p in dpath.iterdir() if p.name.startswith(_KURULUM_ISARETI) and p.name != ben)
        if digerleri:
            logger.error(
                "Makine disi yedek dizini BASKA bir PEMF kurulumuyla PAYLASILIYOR (%s) — bu dizinde rotasyon YAPILMADI (komsu "
                "cihazin yedekleri silinmesin; A-45). Her cihaz icin AYRI dizin kullanin; o kurulum kaldirildiysa isaret dosyasini "
                "silin: %s",
                ", ".join(digerleri),
                dpath,
            )
            return True
        return False

    @staticmethod
    def _yerel_esdeger(yol: str) -> str:
        """F2-3.7 (2-F incelemesi): `\\\\?\\` uzun yol önekini ve AYNI makinenin yönetici paylaşımını (`\\\\localhost\\C$\\…`,
        `\\\\127.0.0.1\\C$\\…`, `\\\\<bu makine>\\C$\\…`) yerel sürücü yoluna indirger — ağa ÇIKMADAN (yalnız dizgi + yerel makine adı).
        `realpath` önekli girdiyi önekli bırakır, UNC'yi sürücü harfine çevirmez → kök-içi hedef "kök dışı" sayılıyordu (ölçüldü)."""
        import re

        y = str(yol)
        if y.startswith("\\\\?\\UNC\\"):
            y = "\\\\" + y[8:]
        elif y.startswith("\\\\?\\"):
            y = y[4:]
        m = re.match(r"^\\\\([^\\]+)\\([A-Za-z])\$(\\.*)?$", y)
        if m and HeadlessDBMaintenance._bu_makine_mi(m.group(1)):
            y = f"{m.group(2)}:{m.group(3) or os.sep}"
        return y

    @staticmethod
    def _bu_makine_mi(ana: str) -> bool:
        """UNC ana bilgisayar adı BU makine mi — yalnız dizgi + yerel makine adı (ağ / DNS sorgusu YOK)."""
        import socket

        yerel = {"localhost", "127.0.0.1", "::1", "[::1]", "."}
        for ad in (os.environ.get("COMPUTERNAME", ""), socket.gethostname()):
            if ad:
                yerel.add(ad.lower())
        a = str(ana).lower()
        return a in yerel or a.startswith("127.")

    @staticmethod
    def _ayni_makinenin_paylasimi_mi(dest: str) -> bool:
        """2-F incelemesi §10 #8 (D5): hedef BU makinenin yönetici OLMAYAN bir paylaşımı mı (`\\\\KLINIK-PC\\PEMF_Yedek`,
        `\\\\localhost\\PEMF_Yedek`)? Yönetici paylaşımı (`X$`) `_yerel_esdeger`le yerel yola iner; adlı paylaşımın hangi klasöre denk
        geldiği ağ / API sorgusu (NetShareGetInfo) olmadan bilinemez — YAPILMAZ. Yalnız dizgi. Kapı:
        tests/test_makine_disi_hedef_AYNI_makine_paylasimi_UYARIR_D5E8.py"""
        import re

        y = HeadlessDBMaintenance._yerel_esdeger(dest)
        m = re.match(r"^\\\\([^\\?.][^\\]*)\\[^\\]+", y)
        return bool(m) and HeadlessDBMaintenance._bu_makine_mi(m.group(1))

    def _hedef_veri_kokunde_mi(self, dest: str) -> bool:
        """S-E2I.4: `dest` (mutlak + gerçek yol, Windows'ta harf duyarsız) veri kökünün KENDİSİ ya da altı mı? Çözülemezse True
        (fail-closed: kopya yapılmaz, ERROR — yerel yedekler sürer). F2-3.7: `\\\\?\\` öneki ve aynı makinenin yönetici paylaşımı
        yerel yola indirgenir (`_yerel_esdeger`)."""
        _y = self._yerel_esdeger
        try:
            hedef = os.path.normcase(_y(os.path.realpath(os.path.abspath(_y(dest)))))
            kok = os.path.normcase(_y(os.path.realpath(os.path.abspath(_y(str(self.app_data_dir))))))
        except (OSError, ValueError, TypeError):
            return True
        return hedef == kok or hedef.startswith(kok.rstrip("\\/") + os.sep)

    def _copy_offsite(self, files):
        """audit B-7.2: PEMF_BACKUP_DIR set ise YENİ yedekleri harici hedefe (ağ paylaşımı/USB) kopyala
        → aynı-disk yedek felaketi (disk arızası/ransomware) tek nokta olmasın. Set değilse no-op.

        ⚠️ D2.12 (B-3.19): her dosya DOĞRULANARAK kopyalanır (`_dogrulanmis_kopya`); "geri yüklenebilir" güvencesi (INFO) YALNIZ tüm
        dosyalar ve kurtarma zarfı bu turda doğrulanınca verilir. Bir dosya bile düşerse ERROR + başarısız sayı. Eskiden özet yalnız
        `(hedef / zarf).exists()`e bakıyordu: yarım .db kopyası varken "KURTARMA KODU ile geri yuklenebilir" deniyordu.
        Kapı: tests/test_offsite_ozeti_DOGRULANMIS_kopyaya_bagli_D212.py"""
        dest = os.environ.get("PEMF_BACKUP_DIR", "").strip()
        if not dest or not files:
            return
        if self._hedef_veri_kokunde_mi(dest):
            # ⚠️ S-E2I.4 (2-E incelemesi, kalan yarı): hedef veri kökünün içindeyse "makine dışı" kopya AYNI diske ve kaldırma / tam
            # temizliğin sileceği köke yazılıyor, günlük "geri yuklenebilir" diyordu (yanlış güvence — ölçüldü). Kopya YAPILMAZ.
            # Kapı: tests/test_makine_disi_yedek_hedefi_PEMF_KOKU_ALTINDA_olamaz_SE2I4.py
            logger.error(
                "Makine disi yedek hedefi (PEMF_BACKUP_DIR=%s) PEMF veri kokunun ICINDE olamaz: ayni diske ve kaldirma / tam "
                "temizligin silecegi koke yazilir, felaket kopyasi degildir — kopya YAPILMADI. Cozum: hedefi veri koku (%s) disindaki "
                "bir USB / ag paylasimi yapin.",
                dest,
                self.app_data_dir,
            )
            return
        if self._ayni_makinenin_paylasimi_mi(dest):
            # ⚠️ 2-F incelemesi §10 #8 (D5 · A3 açık #9): BU makinenin adlı paylaşımı "makine dışı" sayılıyor, kopya doğrulanınca günlük
            # "baska makinede geri yuklenebilir" diyordu — kopya AYNI bilgisayarda kalır ve paylaşım veri kökünü gösteriyorsa kaldırma /
            # tam temizlik onu da siler (ağ sorgusu olmadan çözülemez). Kopya DURMAZ (paylaşım kök dışında olabilir); uyarı her turda.
            logger.warning(
                "Makine disi yedek hedefi (PEMF_BACKUP_DIR=%s) BU bilgisayarin paylasimi — kopya ayni bilgisayarda kalir (disk arizasinda "
                "yedekle birlikte kaybolabilir) ve paylasimin hangi klasore denk geldigi ag sorgusu yapilmadan bilinemez (PEMF veri koku "
                "icindeyse kaldirma / tam temizlik onu da siler). Cozum: baska bir bilgisayarin paylasimini ya da USB disk kullanin.",
                dest,
            )
        try:
            dpath = Path(dest)
            dpath.mkdir(parents=True, exist_ok=True)
            from utils.backup_recovery import ENVELOPE_NAME as _ENV_NAME

            dogrulanan, basarisiz = [], []
            for f in files:
                kaynak = Path(f)
                (dogrulanan if self._dogrulanmis_kopya(kaynak, dpath / kaynak.name) else basarisiz).append(kaynak.name)
            zarf_dogrulandi = _ENV_NAME in dogrulanan
            # DENETIM P2 (yanlis guvence): kopyalanan .db dosyalari SQLCipher ile sifreli ve onlari acan anahtar
            # pemf_secrets.json icinde CRYPTPROTECT_LOCAL_MACHINE (DPAPI) ile MAKINEYE bagli → zarf olmadan baska makinede ACILMAZ.
            if basarisiz:
                logger.error(
                    "Off-machine yedek kopyasi BASARISIZ: %d / %d dosya DOGRULANAMADI (%s) — bu kopyalar off-site'ta GERI "
                    "YUKLENEMEZ; hedef dolu / erisilemez olabilir: %s",
                    len(basarisiz),
                    len(files),
                    ", ".join(basarisiz[:10]),
                    dest,
                )
            elif zarf_dogrulandi:
                logger.info(
                    "Yedekler off-machine kopyalandi ve DOGRULANDI: %s (%d dosya). Kurtarma zarfi (%s) yerinde → "
                    "KURTARMA KODU ile baska makinede geri yuklenebilir.",
                    dest,
                    len(dogrulanan),
                    _ENV_NAME,
                )
            else:
                logger.warning(
                    "Yedekler off-machine kopyalandi: %s (%d dosya). DIKKAT: kurtarma zarfi (%s) bu turda kopyalanmadi "
                    "→ dosyalar SQLCipher ile sifreliyse anahtar BU MAKINEYE bagli (DPAPI); donanim arizasinda ACILAMAZLAR. bkz. %s",
                    dest,
                    len(dogrulanan),
                    _ENV_NAME,
                    _OFFSITE_README_NAME,
                )
            # ⚠️ D2.51 (B-3.22 · Y11, sahip kararı): makine dışı hedefte de her yedek türünden SON N kopya kalır (yerel ile aynı kural ve
            # N). Eskiden yalnız kopyalanıyordu: hedef sınırsız büyüyor (doldukça B-3.19) ve canlı DB'den SİLİNEN hastanın adı ilk
            # kopyada süresiz kalıyordu (KVKK; zarf + kodla açılabilir — ölçüldü). Kopyalardan SONRA: bu turun kopyası düşse de
            # yalnız açılabilen kopyalar sayılır, eskiler gereksiz yere gitmez. A-45: yalnız kendi adlı dosyalar (bkz. `_rotasyon`).
            # ⚠️ D2-1.2 (2-D incelemesi, A-45): ad + açılabilirlik "bu kurulumun yedeği" demek DEĞİL — düz kurulumda her düz SQLite
            # anahtarsız açılır. Aynı hedefi paylaşan ikinci kurulum varsa rotasyon O dizinde yapılmaz (komşunun kopyaları silinmez).
            try:
                paylasimli = self._makine_disi_paylasiliyor_mu(dpath)
            except OSError:
                logger.warning(
                    "Makine disi kurulum isareti yazilamadi/okunamadi — rotasyon YAPILMADI: %s", dest, exc_info=True
                )
                paylasimli = True
            if not paylasimli:
                self._rotasyon(dpath, "makine disi", frozenset(dogrulanan))
            # Yedeklerin YANINA ne gerektigini yaz: kurtarma anindaki kisi log'lara bakamayabilir.
            try:
                (dpath / _OFFSITE_README_NAME).write_text(_OFFSITE_README_TEXT, encoding="utf-8")
            except Exception:
                # ⚠️ D2-3.6 (2-D incelemesi): not felaket günü okunacak TEK talimattır — yazılamazsa (hedefte eski / hiç not) SESSİZ
                # kalmaz. Eskiden DEBUG idi; aynı turda INFO "geri yuklenebilir" yazılıyordu.
                # Kapı: tests/test_kurtarma_notu_YAZILAMAZSA_SESSIZ_DEGIL_D236.py
                logger.warning(
                    "off-machine kurtarma notu (%s) YAZILAMADI — hedefteki not eski ya da yok; kurtarma adimlari icin "
                    "docs/RUNBOOK.md 'Felaket kurtarma' bolumune bakin: %s",
                    _OFFSITE_README_NAME,
                    dest,
                    exc_info=True,
                )
        except Exception:
            logger.warning("off-machine backup dizini hatasi (%s)", dest, exc_info=True)


def start_headless_db_maintenance(app_data_dir=None):
    """Idempotent — headless backend startup'ından çağrılır."""
    global _worker
    if _worker is None:
        try:
            _worker = HeadlessDBMaintenance(app_data_dir)
            _worker.start()
        except Exception:
            logger.exception("Headless DB bakim servisi baslatilamadi")
    return _worker


def stop_headless_db_maintenance():
    """Idempotent — shutdown'da çağrılır. In-progress backup/maintenance turunun bitmesini
    kisa sure bekler (join) → bozuk yedek/kilitli DB birakmaz. Eskiden HIC durdurulmuyordu."""
    global _worker
    if _worker is not None:
        try:
            _worker.stop()
        except Exception:
            logger.exception("Headless DB bakim servisi durdurulamadi")
        _worker = None
