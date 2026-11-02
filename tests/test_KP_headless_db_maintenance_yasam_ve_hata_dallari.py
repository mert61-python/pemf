# -*- coding: utf-8 -*-
"""KP-1 · apps/backend/services/headless_db_maintenance.py · sözleşmeler: kurucu (verilen / varsayılan veri kökü, tedavi DB tekili,
hasta DB açılış kilidinde None, aralıklar EN AZ 1), `start` ikinci çağrıda ikinci iş parçacığı AÇMAZ, `stop` süren turu BEKLER,
modül düzeyi başlat/durdur (idempotent, hata yutulur + günlükte, işçi bırakılır), disk denetimi (KRİTİK uyarısı / sağlayıcı hatası),
bakım turu hatası, yedek doğrulama hatası, tazelikte okunamayan yedek, hasta yedeği hatası, yedek dizini kurulamaz, ayar yedeğinde kökü
sözlük olmayan JSON, şifreli anahtar listesi okunamaz, kurtarma zarfı yazılamaz, rotasyon G/Ç hataları (dizin yok, salt-okunur artık,
okunamayan dosya, aile içi beklenmeyen hata), doğrulanmış kopyada geçici silinemez, hedef yolu çözülemez (fail-closed), makine dışı kurulum
işareti okunamaz → rotasyon YOK.

Sahte EN ALT katta: disk kullanımı sağlayıcısı (gerçek `TreatmentHistoryDB._disk_usage_provider` yuvası), dosya sistemi arızaları GERÇEK
(salt-okunur dosya, dizin yerine dosya / dosya yerine dizin, gömülü NUL) ya da yalnız hedef dosyada `pathlib.Path.stat` (glob ile stat
arasında silinme / erişim reddi biçimi), sır deposu (`utils.secrets_manager.get_secret`). Tedavi DB'si GERÇEK (düz SQLite, tmp kök).
Gerçek DB'nin istisnayı İÇERİDE yuttuğu metotlarda (bakım, yedek doğrulama, hasta yedeği) savunma dalı yalnız o metodu gerçek arıza
biçimiyle (`sqlite3.DatabaseError` / `OperationalError`) patlatan küçük ikizle sınanır.
"""

from __future__ import annotations

import collections
import logging
import os
import sqlite3
import stat
import threading
import time
from datetime import datetime
from pathlib import Path

import pytest

_LOG = "services.headless_db_maintenance"
_MB = 1024 * 1024
_Kullanim = collections.namedtuple("_Kullanim", "total used free")  # shutil.disk_usage dönüş biçimi


def _kayitlar(caplog, seviye=None):
    """Ürün günlüğünün (seviye adı, ileti, istisna türü) üçlüleri."""
    return [
        (r.levelname, r.getMessage(), r.exc_info[0] if r.exc_info else None)
        for r in caplog.records
        if r.name == _LOG and (seviye is None or r.levelno == seviye)
    ]


def _yazilabilir_yap(*yollar):
    for y in yollar:
        try:
            os.chmod(y, stat.S_IWRITE | stat.S_IREAD)
        except OSError:
            pass


@pytest.fixture
def app(temp_app_data, monkeypatch):
    """Düz (şifresiz) kurulum: veri kökü tmp; sqlcipher anahtarı boş; göç kümesi kopyayla değiştirilir (test sonunda eskisi döner)."""
    from database import patient_database as pdb
    from database import sqlcipher_util as su
    from database import treatment_history_db as thdb
    from utils import path_utils

    monkeypatch.delenv("PEMF_ENCRYPT_AT_REST", raising=False)
    monkeypatch.delenv("PEMF_BACKUP_DIR", raising=False)
    for ad in (
        "PEMF_RETAIN_SENSOR_DAYS",
        "PEMF_SENSOR_RETAIN_DAYS",
        "PEMF_RETAIN_DOSE_DAYS",
        "PEMF_RETAIN_EVENT_DAYS",
        "PEMF_RETAIN_OUTBOX_DAYS",
        "PEMF_RETAIN_PII_DAYS",
    ):
        monkeypatch.delenv(ad, raising=False)
    monkeypatch.setattr(su, "get_sqlcipher_key", lambda *a, **k: "")
    monkeypatch.setattr(pdb, "get_sqlcipher_key", lambda *a, **k: "")
    monkeypatch.setattr(thdb.TreatmentHistoryDB, "_get_sqlcipher_key_legacy", lambda self: "")
    monkeypatch.setattr(path_utils, "_GOC_YAPILDI", set(path_utils._GOC_YAPILDI))
    return temp_app_data


@pytest.fixture
def tdb(app):
    from database.treatment_history_db import TreatmentHistoryDB

    db = TreatmentHistoryDB(app)
    assert not getattr(db, "at_rest_encrypted", False), "aparat: düz kurulum bekleniyordu"
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def kasa(monkeypatch):
    """Sır deposu EN ALT katta: bellek içi değerler; `patlat`taki ad okunurken gerçek arıza biçimiyle (OSError) düşer."""
    from utils import secrets_manager as sm

    durum = {"degerler": {}, "patlat": set(), "sorulan": []}

    def _get_secret(ad, default="", generate=True):
        durum["sorulan"].append(ad)
        if ad in durum["patlat"]:
            raise OSError(f"sentetik: sir deposu okunamadi ({ad})")
        return durum["degerler"].get(ad, default)

    monkeypatch.setattr(sm, "get_secret", _get_secret)
    return durum


def _servis(app_dir: Path, db, patient_db=None, keep=14):
    """Kurucusuz örnek (DB'ler aparattan); alanlar gerçek kurucunun ürettiği biçimde."""
    from services.headless_db_maintenance import HeadlessDBMaintenance

    w = object.__new__(HeadlessDBMaintenance)
    w.app_data_dir = app_dir
    w.db = db
    w.patient_db = patient_db
    w.maint_interval = 6 * 3600
    w.backup_interval = 24 * 3600
    w.disk_interval = 30 * 60
    w.backup_retention_keep = keep
    w._stop = threading.Event()
    w._thread = None
    return w


def _gecerli_yedek(tdb, yol: Path, yas_sn=None) -> Path:
    """GERÇEK tedavi DB yedeği (online backup API); `yas_sn` verilirse mtime o kadar geriye alınır."""
    yol.parent.mkdir(parents=True, exist_ok=True)
    assert tdb.create_backup(str(yol)), f"aparat: yedek alınamadı {yol}"
    if yas_sn is not None:
        t = time.time() - yas_sn
        os.utime(yol, (t, t))
    return yol


def _dbm_sayisi():
    return sum(1 for t in threading.enumerate() if t.name == "DBMaintenance" and t.is_alive())


# ───────────────────────────── kurucu ─────────────────────────────


def test_kurucu_VERILEN_kokte_tedavi_DB_tekili_hasta_DB_ACILIS_KILIDINDE_None_araliklar_EN_AZ_1(app, monkeypatch):
    """Kök dizgi olarak verilir + hasta DB'si açılışta açılamamış (kilit) + sıfır/negatif aralıklar → app_data_dir = Path(kök), tedavi DB'si
    o kökteki tekil, patient_db None (istisna kurucudan SIZMAZ), aralıklar 1 sa / 1 sa / 1 dk (sn), tutma 1; durdurma bayrağı inik, iş parçacığı yok."""
    from database import patient_database as pdb
    from database import treatment_history_db as thdb
    from services.headless_db_maintenance import HeadlessDBMaintenance

    monkeypatch.setattr(thdb, "_treatment_db_instance", None)
    monkeypatch.setattr(pdb, "_patient_db", None)
    monkeypatch.setitem(pdb._acilis_kilidi, pdb._kilit_anahtari(app / "patients.db"), "PermissionError")
    kok = app / "verilen_kok"
    kok.mkdir()

    w = HeadlessDBMaintenance(
        str(kok),
        maintenance_interval_hours=0,
        backup_interval_hours=-2,
        disk_check_interval_minutes=0,
        backup_retention_keep=0,
    )
    try:
        assert w.app_data_dir == kok and isinstance(w.app_data_dir, Path)
        assert w.db is thdb._treatment_db_instance
        assert Path(w.db.db_path) == kok / "pemf_treatment_history.db"
        assert w.patient_db is None
        assert (w.maint_interval, w.backup_interval, w.disk_interval, w.backup_retention_keep) == (3600, 3600, 60, 1)
        assert not w._stop.is_set() and w._thread is None
    finally:
        w.db.close()


def test_kurucu_kok_VERILMEZSE_uygulama_veri_dizini_hasta_DB_TEKILI_ve_VARSAYILAN_araliklar(app, monkeypatch):
    """Kök verilmez + hasta DB tekili açık → app_data_dir = uygulama veri dizini (PEMF_DATA_DIR/PEMF_GUI), tedavi DB'si orada,
    patient_db = açık hasta DB tekili; aralıklar 6 sa / 24 sa / 30 dk (sn), tutma 14."""
    from database import patient_database as pdb
    from database import treatment_history_db as thdb
    from services.headless_db_maintenance import HeadlessDBMaintenance

    monkeypatch.setattr(thdb, "_treatment_db_instance", None)
    acik_hasta_db = object()  # açılışta çekirdeğin açtığı tekil (kurucu ona yalnız referans tutar)
    monkeypatch.setattr(pdb, "_patient_db", acik_hasta_db)

    w = HeadlessDBMaintenance()
    try:
        assert w.app_data_dir == app
        assert Path(w.db.db_path) == app / "pemf_treatment_history.db"
        assert w.patient_db is acik_hasta_db
        assert (w.maint_interval, w.backup_interval, w.disk_interval, w.backup_retention_keep) == (
            6 * 3600,
            24 * 3600,
            30 * 60,
            14,
        )
    finally:
        w.db.close()


# ───────────────────────────── start / stop ─────────────────────────────


def test_start_IKINCI_cagrida_ikinci_is_parcacigi_ACMAZ_stop_SUREN_turu_BEKLER_dongu_biter(
    app, tdb, kasa, caplog, monkeypatch
):
    """Döngü ilk turun disk denetiminde beklerken start() yeniden çağrılır → AYNI iş parçacığı (canlı DBMaintenance sayısı +1);
    stop() → bayrak kalkar, süren tur (bakım + açılış yedeği kararı) stop() join'e girdikten ~0,15 sn SONRA da sürse TAMAMLANIR:
    stop() bakım iş parçacığını 10 sn bütçeyle bekler (yarıda kesik/bozuk SQLite yedeği bırakmaz), iş parçacığı biter, sonra döner."""
    caplog.set_level(logging.INFO, logger=_LOG)
    gercek_thread = threading.Thread
    join_sureleri: list = []
    join_basladi = threading.Event()

    class _JoinKayitliThread(gercek_thread):
        """GERÇEK iş parçacığı (gerçek start/join); yalnız bakım iş parçacığına verilen join süresi kaydedilir."""

        def join(self, timeout=None):
            if self.name == "DBMaintenance":
                join_sureleri.append(timeout)
                join_basladi.set()
            return super().join(timeout)

    monkeypatch.setattr(
        threading, "Thread", _JoinKayitliThread
    )  # ürün `threading.Thread(...)` ile kurar; test sonunda geri gelir
    bdir = app / "backups"
    taze = _gecerli_yedek(tdb, bdir / f"pemf_treatment_history_{datetime.now():%Y%m%d_%H%M%S}.db", yas_sn=60)
    giris, kapi = threading.Event(), threading.Event()
    sorulan = []

    def _saglayici(yol):
        sorulan.append(Path(yol))
        giris.set()
        kapi.wait(10)
        return _Kullanim(total=100_000 * _MB, used=10_000 * _MB, free=90_000 * _MB)

    tdb._disk_usage_provider = _saglayici
    w = _servis(app, tdb)
    w.disk_interval = 60  # kurucunun alt sınırı: ilk turda disk denetimi monotonic saat ≥ 60 sn iken koşar (açılıştan 30 dk koşulu yok)
    once = _dbm_sayisi()
    serbest = None
    w.start()
    try:
        assert giris.wait(5), "döngü disk denetimine girmedi"
        ilk = w._thread
        w.start()
        assert w._thread is ilk and ilk.daemon
        assert _dbm_sayisi() == once + 1

        # Tur, stop() join'e GİRDİKTEN 0,15 sn sonra serbest kalır (stop'tan sonra da süren yedek/bakım turu) → kısa bütçeli
        # bir join turu beklemeden döner; stop() turun bitmesini beklemeli.
        def _serbest_birak():
            if join_basladi.wait(5):
                time.sleep(0.15)
            kapi.set()

        serbest = gercek_thread(target=_serbest_birak, daemon=True)
        serbest.start()
        w.stop()
        assert w._stop.is_set()
        assert not ilk.is_alive(), "stop() süren turu beklemeden döndü"
        assert join_sureleri == [10.0], "stop() süren tur için 10 sn bütçeyle beklemiyor"
        mesajlar = [m for _s, m, _e in _kayitlar(caplog)]
        assert any(m.startswith("DB bakim+retention tamam: maintenance=") for m in mesajlar)
        assert "Acilis yedegi ATLANDI: diskte taze yedek var (restart-dongusu korumasi)." in mesajlar
        assert sorulan == [app]
        assert sorted(p.name for p in bdir.glob("pemf_treatment_history_*.db")) == [taze.name]
    finally:
        kapi.set()
        w._stop.set()
        if w._thread is not None:
            w._thread.join(10)
        if serbest is not None:
            serbest.join(5)


# ───────────────────────────── modül düzeyi başlat / durdur ─────────────────────────────


def test_modul_BASLAT_idempotent_TEK_isci_DURDUR_isciyi_birakir_ikinci_DURDUR_etkisiz(app, kasa, monkeypatch, caplog):
    """start_headless_db_maintenance(kök) iki kez → AYNI işçi, tek DBMaintenance iş parçacığı, işçi kökü = verilen kök;
    stop_headless_db_maintenance() → işçinin bayrağı kalkar, iş parçacığı biter, modül işçisi None; ikinci stop etkisiz
    (hiçbir şey denenmez: istisna yok, günlük kaydı — 'durdurulamadi' ERROR'u dahil — YOK)."""
    import services.headless_db_maintenance as hdm
    from database import patient_database as pdb
    from database import treatment_history_db as thdb

    caplog.set_level(logging.DEBUG, logger=_LOG)
    monkeypatch.setattr(hdm, "_worker", None)
    monkeypatch.setattr(thdb, "_treatment_db_instance", None)
    monkeypatch.setattr(pdb, "_patient_db", None)
    monkeypatch.setitem(pdb._acilis_kilidi, pdb._kilit_anahtari(app / "patients.db"), "PermissionError")
    once = _dbm_sayisi()

    w = hdm.start_headless_db_maintenance(app)
    try:
        assert isinstance(w, hdm.HeadlessDBMaintenance) and hdm._worker is w
        assert w.app_data_dir == app and w.patient_db is None
        is_parcacigi = w._thread
        assert hdm.start_headless_db_maintenance(app) is w
        assert w._thread is is_parcacigi and _dbm_sayisi() == once + 1

        hdm.stop_headless_db_maintenance()
        assert hdm._worker is None
        assert w._stop.is_set() and not is_parcacigi.is_alive()
        caplog.clear()
        hdm.stop_headless_db_maintenance()  # işçi yokken: etkisiz, istisna yok, günlüğe HİÇBİR ŞEY yazılmaz (sahte hata izi yok)
        assert hdm._worker is None
        assert _kayitlar(caplog) == [], "işçi yokken DURDUR bir şey denedi (günlük kaydı düştü)"
    finally:
        w._stop.set()
        if w._thread is not None:
            w._thread.join(10)
        w.db.close()


def test_modul_BASLAT_kurucu_PATLARSA_hata_GUNLUGE_doner_None_isci_yok(app, monkeypatch, caplog):
    """Tedavi DB'si açılışta açılamamış (açılış kilidi → kurucu RuntimeError) → start_headless_db_maintenance None döner, modül işçisi
    None kalır, yeni iş parçacığı yok; ERROR 'Headless DB bakim servisi baslatilamadi' istisna iziyle."""
    import services.headless_db_maintenance as hdm
    from database import treatment_history_db as thdb

    monkeypatch.setattr(hdm, "_worker", None)
    monkeypatch.setattr(thdb, "_treatment_db_instance", None)
    monkeypatch.setitem(thdb._acilis_kilidi, thdb._kilit_anahtari(app / "pemf_treatment_history.db"), "PermissionError")
    once = _dbm_sayisi()

    assert hdm.start_headless_db_maintenance(app) is None
    assert hdm._worker is None and _dbm_sayisi() == once
    assert _kayitlar(caplog, logging.ERROR) == [("ERROR", "Headless DB bakim servisi baslatilamadi", RuntimeError)]


def test_modul_DURDUR_bakim_HIC_BASLAMAMISSA_etkisiz_SAHTE_hata_izi_YOK(monkeypatch, caplog):
    """Modül işçisi yokken (bakım açılışta başlatılamamış ya da hiç başlatılmamış; `_shutdown` her kapanışta çağırır)
    stop_headless_db_maintenance() → hiçbir şey denenmez: istisna yok, işçi None kalır, günlükte HİÇBİR kayıt yok
    ('durdurulamadi' ERROR'u + izi basılmaz)."""
    import services.headless_db_maintenance as hdm

    monkeypatch.setattr(hdm, "_worker", None)
    caplog.set_level(logging.DEBUG, logger=_LOG)
    hdm.stop_headless_db_maintenance()
    assert hdm._worker is None
    assert _kayitlar(caplog) == []


def test_modul_DURDUR_isci_KENDI_is_parcacigindan_durdurulursa_hata_GUNLUGE_isci_yine_BIRAKILIR(
    app, monkeypatch, caplog
):
    """Durdurma işçinin KENDİ iş parçacığında çağrılır (join → RuntimeError 'cannot join current thread') → istisna dışarı sızmaz,
    ERROR 'Headless DB bakim servisi durdurulamadi' izle yazılır, işçinin bayrağı kalkmış ve modül işçisi yine None olur."""
    import services.headless_db_maintenance as hdm

    w = _servis(app, None)
    w._thread = threading.current_thread()  # durdurma çağrısı bakım iş parçacığının kendisinden geliyor
    monkeypatch.setattr(hdm, "_worker", w)

    hdm.stop_headless_db_maintenance()

    assert hdm._worker is None and w._stop.is_set()
    assert _kayitlar(caplog, logging.ERROR) == [("ERROR", "Headless DB bakim servisi durdurulamadi", RuntimeError)]


# ───────────────────────────── disk denetimi / bakım ─────────────────────────────


@pytest.mark.parametrize(
    "bos_mb, uyari",
    [(120, True), (499, True), (500, False)],
    ids=["120MB_KRITIK", "499MB_esik_alti_KRITIK", "500MB_esikte_KRITIK_DEGIL"],
)
def test_disk_denetimi_BOS_alan_ESIGIN_ALTINDAYSA_DISK_KRITIK_uyarisi_MB_degerleriyle(app, tdb, caplog, bos_mb, uyari):
    """Disk sağlayıcısı (DB dizini için sorulur) `bos_mb` boş döndürür; eşik 500 MB → altındaysa WARNING 'DISK KRITIK: <boş>MB < 500MB',
    eşikte/üstündeyse günlük yok; istisna yok."""
    sorulan = []

    def _saglayici(yol):
        sorulan.append(Path(yol))
        return _Kullanim(total=10_000 * _MB, used=(10_000 - bos_mb) * _MB, free=bos_mb * _MB)

    tdb._disk_usage_provider = _saglayici
    _servis(app, tdb)._check_disk()

    assert sorulan == [app]
    beklenen = [("WARNING", f"DISK KRITIK: {bos_mb}MB < {tdb.MIN_FREE_DISK_MB}MB", None)] if uyari else []
    assert tdb.MIN_FREE_DISK_MB == 500
    assert _kayitlar(caplog) == beklenen


def test_disk_denetimi_SAGLAYICI_patlarsa_istisna_SIZMAZ_ERROR_iziyle(app, tdb, caplog):
    """Disk kullanımı okunamaz (sürücü hazır değil: OSError) → _check_disk istisna fırlatmaz; ERROR 'disk check hatasi' OSError iziyle."""

    def _saglayici(yol):
        raise OSError(22, "Aygit hazir degil", str(yol))

    tdb._disk_usage_provider = _saglayici
    _servis(app, tdb)._check_disk()

    assert _kayitlar(caplog) == [("ERROR", "disk check hatasi", OSError)]


class _BakimiPatlayanDB:
    """Bakım adımı gerçek arıza biçimiyle (bozuk DB görüntüsü) düşer; saklama çağrısı kaydedilir (gerçek DB bakımda istisnayı İÇERİDE yutar)."""

    def __init__(self):
        self.saklama_cagrilari = []

    def run_maintenance(self):
        raise sqlite3.DatabaseError("database disk image is malformed")

    def apply_data_retention_policy(self, **kw):
        self.saklama_cagrilari.append(kw)
        return {}


def test_bakim_adimi_PATLARSA_saklama_UYGULANMAZ_istisna_SIZMAZ_ERROR_iziyle(app, caplog):
    """run_maintenance DatabaseError → _run_maintenance dışarı istisna vermez, bu turda saklama (silme/maskeleme) ÇAĞRILMAZ,
    'tamam' INFO'su yazılmaz; ERROR 'maintenance hatasi' DatabaseError iziyle."""
    caplog.set_level(logging.INFO, logger=_LOG)
    db = _BakimiPatlayanDB()
    _servis(app, db)._run_maintenance()

    assert db.saklama_cagrilari == []
    assert _kayitlar(caplog) == [("ERROR", "maintenance hatasi", sqlite3.DatabaseError)]


# ───────────────────────────── yedek doğrulama / tazelik ─────────────────────────────


class _DogrulamasiPatlayanHastaDB:
    """Hasta DB'si yedek doğrulamasında gerçek arıza biçimiyle düşer; sorulan yollar kaydedilir."""

    def __init__(self):
        self.sorulan = []

    def yedek_acilir_mi(self, yol):
        self.sorulan.append(Path(yol))
        raise sqlite3.OperationalError("unable to open database file")


def test_hasta_yedegi_DOGRULANAMAZSA_ACILAMAZ_sayilir_uyari_TEDAVI_yedegi_tedavi_DBsiyle_dogrulanir(app, tdb, caplog):
    """`pemf_patients_*` yedeği hasta DB'sine sorulur; doğrulayıcı patlarsa → False + WARNING 'Yedek dogrulanamadi: <yol>' izle;
    tedavi yedeği hasta DB'sine SORULMAZ, gerçek tedavi DB'siyle açılır (True)."""
    bdir = app / "backups"
    hasta = bdir / "pemf_patients_20260101_080000.db"
    tedavi = _gecerli_yedek(tdb, bdir / "pemf_treatment_history_20260101_080000.db")
    hasta.write_bytes(tedavi.read_bytes())
    hdb = _DogrulamasiPatlayanHastaDB()
    w = _servis(app, tdb, patient_db=hdb)

    assert w._yedek_acilir_mi(hasta) is False
    assert w._yedek_acilir_mi(tedavi) is True
    assert hdb.sorulan == [hasta]
    assert _kayitlar(caplog) == [("WARNING", f"Yedek dogrulanamadi: {hasta}", sqlite3.OperationalError)]


def test_tazelikte_en_yeni_yedegin_DURUMU_okunamazsa_ATLANIR_siradaki_acilabilen_yedegin_YASI_doner(
    app, tdb, monkeypatch
):
    """En yeni yedek glob ile stat arasında kaybolur (stat → FileNotFoundError) → o dosya atlanır; yaş sıradaki açılabilen yedeğin
    mtime'ından (≈ 2 sa) — None (yedek al) da 0 (taze) da DEĞİL."""
    bdir = app / "backups"
    eski = _gecerli_yedek(tdb, bdir / "pemf_treatment_history_20260101_080000.db", yas_sn=7200)
    yeni = _gecerli_yedek(tdb, bdir / "pemf_treatment_history_20260101_100000.db", yas_sn=60)
    gercek_stat = Path.stat

    def _stat(self, *a, **k):
        if self.name == yeni.name:
            raise FileNotFoundError(2, "Sistem belirtilen dosyayi bulamiyor", str(self))
        return gercek_stat(self, *a, **k)

    monkeypatch.setattr(Path, "stat", _stat)
    yas = _servis(app, tdb)._en_yeni_gecerli_yedek_yasi()

    assert eski.exists()
    assert yas is not None and 7200 - 5 <= yas < 7200 + 120


# ───────────────────────────── yedek turu ─────────────────────────────


class _YedegiPatlayanHastaDB:
    """Hasta DB'si yedeği gerçek arıza biçimiyle (kilit) düşer; istenen hedef yolu kaydedilir."""

    def __init__(self):
        self.istenen = []

    def create_backup(self, yol):
        self.istenen.append(Path(yol))
        raise sqlite3.OperationalError("database is locked")


def test_hasta_yedegi_PATLARSA_tedavi_yedegi_YINE_alinir_ve_makine_disina_YALNIZ_o_gider(
    app, tdb, kasa, monkeypatch, tmp_path, caplog
):
    """Hasta DB'si yedeği OperationalError → WARNING 'Hasta DB yedegi hatasi' izle; aynı damgalı tedavi yedeği yerelde ALINIR,
    hasta yedeği yerelde YOK; makine dışı hedefe yalnız tedavi yedeği kopyalanır (bu turun 'üretilen' listesi)."""
    usb = tmp_path / "usb"
    monkeypatch.setenv("PEMF_BACKUP_DIR", str(usb))
    hdb = _YedegiPatlayanHastaDB()
    w = _servis(app, tdb, patient_db=hdb)

    w._run_backup()

    bdir = app / "backups"
    tedavi = sorted(bdir.glob("pemf_treatment_history_*.db"))
    assert len(tedavi) == 1
    damga = tedavi[0].name[len("pemf_treatment_history_") : -len(".db")]
    assert hdb.istenen == [bdir / f"pemf_patients_{damga}.db"]
    assert list(bdir.glob("pemf_patients_*")) == []
    assert sorted(p.name for p in usb.glob("pemf_*")) == [tedavi[0].name]
    assert ("WARNING", "Hasta DB yedegi hatasi", sqlite3.OperationalError) in _kayitlar(caplog, logging.WARNING)


def test_yedek_dizini_KURULAMAZSA_tur_ERROR_ile_biter_hicbir_yedek_ya_da_kopya_YOK(
    app, tdb, monkeypatch, tmp_path, caplog
):
    """Veri kökünde `backups` adında DOSYA var (mkdir → FileExistsError) → _run_backup istisna vermez, ERROR 'backup hatasi' izle;
    dosyaya dokunulmaz, makine dışı hedef hiç oluşturulmaz."""
    (app / "backups").write_text("kullanici dosyasi", encoding="utf-8")
    usb = tmp_path / "usb"
    monkeypatch.setenv("PEMF_BACKUP_DIR", str(usb))

    _servis(app, tdb)._run_backup()

    assert (app / "backups").read_text(encoding="utf-8") == "kullanici dosyasi"
    assert not usb.exists()
    assert _kayitlar(caplog) == [("ERROR", "backup hatasi", FileExistsError)]


def test_kurtarma_zarfi_YAZILAMAZSA_yedek_YINE_alinir_zarf_YOK_uyari(app, tdb, kasa, caplog):
    """Kurtarılacak anahtar var ama kurtarma kodu okunurken sır deposu düşer (OSError) → _run_backup tedavi yedeğini ALIR, zarf
    YAZILMAZ; WARNING 'kurtarma zarfi guncellenemedi (yedekler ALINDI)' OSError izle; sır deposuna önce anahtarlar sonra kod sorulur."""
    from utils.backup_recovery import ENVELOPE_NAME

    kasa["degerler"]["sqlcipher_key"] = "KP-sentetik-anahtar"
    kasa["patlat"].add("backup_recovery_code")
    w = _servis(app, tdb)

    w._run_backup()

    bdir = app / "backups"
    assert len(list(bdir.glob("pemf_treatment_history_*.db"))) == 1
    assert not (bdir / ENVELOPE_NAME).exists()
    assert kasa["sorulan"] == ["sqlcipher_key", "patient_fernet_key", "backup_recovery_code"]
    assert ("WARNING", "kurtarma zarfi guncellenemedi (yedekler ALINDI)", OSError) in _kayitlar(caplog, logging.WARNING)


def test_ayar_yedegi_koku_SOZLUK_DEGILSE_ham_kopya_ALINMAZ_digeri_YINE_yedeklenir(app, tdb, caplog):
    """config.json kökü liste → ERROR '... HAM kopya ALINMADI (sir icerebilir)' ValueError izle, pemf_config_* YOK; system_settings.json
    (sözlük) yine yedeklenir ve dönen liste yalnız onu içerir."""
    import json

    (app / "config.json").write_text(json.dumps([{"mqtt": {"pass": "gizli"}}]), encoding="utf-8")
    (app / "system_settings.json").write_text(json.dumps({"dil": "tr"}), encoding="utf-8")
    bdir = app / "backups"
    bdir.mkdir()
    damga = "20260101_080000"

    uretilen = _servis(app, tdb)._ek_kapsam_yedekle(bdir, damga)

    assert uretilen == [bdir / f"pemf_system_settings_{damga}.json"]
    assert json.loads(uretilen[0].read_text(encoding="utf-8")) == {"dil": "tr"}
    assert list(bdir.glob("pemf_config_*")) == []
    assert (
        "ERROR",
        "config.json yedegi BASARISIZ (okunamadi / yazilamadi) — HAM kopya ALINMADI (sir icerebilir)",
        ValueError,
    ) in _kayitlar(caplog, logging.ERROR)


def test_sifreli_anahtar_listesi_OKUNAMAZSA_bos_kume_uyari_ve_ad_desenli_sirlar_YINE_ayiklanir(
    app, tdb, monkeypatch, caplog
):
    """Config yöneticisinin şifreli anahtar listesi okunamaz (öznitelik yok → AttributeError) → _config_sir_yollari boş küme +
    WARNING; ayar yedeği yine alınır ve adı sır desenli alan (mqtt.pass) yedeğe GİRMEZ, sırsız alanlar kalır."""
    import json

    from services.headless_db_maintenance import HeadlessDBMaintenance
    from utils.production_config_manager import ProductionConfigManager

    monkeypatch.delattr(ProductionConfigManager, "_ENCRYPTED_KEYS")
    assert HeadlessDBMaintenance._config_sir_yollari() == frozenset()

    (app / "config.json").write_text(
        json.dumps({"mqtt": {"host": "127.0.0.1", "pass": "gizli"}, "dil": "tr"}), encoding="utf-8"
    )
    bdir = app / "backups"
    bdir.mkdir()
    uretilen = _servis(app, tdb)._ek_kapsam_yedekle(bdir, "20260101_080000")

    assert uretilen == [bdir / "pemf_config_20260101_080000.json"]
    assert json.loads(uretilen[0].read_text(encoding="utf-8")) == {"mqtt": {"host": "127.0.0.1"}, "dil": "tr"}
    uyari = (
        "WARNING",
        "config sir anahtari listesi okunamadi — yalniz ad deseni ve 'enc:' oneki ile ayiklanir",
        AttributeError,
    )
    assert _kayitlar(caplog, logging.WARNING).count(uyari) == 2


# ───────────────────────────── rotasyon G/Ç dalları ─────────────────────────────


def test_rotasyon_dizini_LISTELENEMEZSE_uyari_ve_SESSIZ_donus(app, tdb, caplog):
    """Makine dışı dizin yok (iterdir → FileNotFoundError) → _rotasyon istisna vermez; WARNING 'Yedek rotasyonu (makine disi): dizin
    listelenemedi: <dizin>' izle."""
    yok = app / "takili_olmayan_usb"
    _servis(app, tdb)._rotasyon(yok, "makine disi")

    assert _kayitlar(caplog) == [
        ("WARNING", f"Yedek rotasyonu (makine disi): dizin listelenemedi: {yok}", FileNotFoundError)
    ]


def test_rotasyon_SALT_OKUNUR_yarim_yedek_artigi_SILINEMEZSE_uyari_digeri_YINE_silinir(app, tdb, caplog):
    """1 saatten eski iki yarım yedek artığı: salt-okunur olan silinemez (PermissionError) → WARNING 'Yarim yedek artigi silinemedi
    (yerel): <yol>' izle ve dosya kalır; yazılabilir olan silinir."""
    caplog.set_level(logging.INFO, logger=_LOG)
    bdir = app / "backups"
    bdir.mkdir()
    kilitli = bdir / "pemf_treatment_history_20260101_080000.db.yazim.tmp"
    serbest = bdir / "pemf_config_20260101_080000.json.kopya.tmp"
    eski = time.time() - 7200
    for f in (kilitli, serbest):
        f.write_bytes(b"yarim")
        os.utime(f, (eski, eski))
    os.chmod(kilitli, stat.S_IREAD)
    try:
        _servis(app, tdb)._rotasyon(bdir, "yerel")

        assert kilitli.exists() and not serbest.exists()
        kayit = _kayitlar(caplog, logging.WARNING)
        assert kayit == [("WARNING", f"Yarim yedek artigi silinemedi (yerel): {kilitli}", PermissionError)]
    finally:
        _yazilabilir_yap(kilitli)


def test_rotasyon_OKUNAMAYAN_dosya_ATLANIR_sayilmaz_silinmez_kalanlar_kurala_gore_doner(app, tdb, monkeypatch, caplog):
    """Tutma 1; üç tedavi yedeğinden ortadakinin durumu okunamaz (PermissionError) → WARNING 'Yedek rotasyonu (yerel): dosya okunamadi,
    ATLANDI: <yol>' izle, o dosya kalır ve sayılmaz; açılabilen iki yedekten EN ESKİSİ silinir, en yenisi kalır."""
    bdir = app / "backups"
    a = _gecerli_yedek(tdb, bdir / "pemf_treatment_history_20260101_080000.db")
    b = _gecerli_yedek(tdb, bdir / "pemf_treatment_history_20260101_090000.db")
    c = _gecerli_yedek(tdb, bdir / "pemf_treatment_history_20260101_100000.db")
    gercek_stat = Path.stat

    def _stat(self, *args, **kw):
        if self.name == b.name:
            raise PermissionError(13, "Erisim engellendi", str(self))
        return gercek_stat(self, *args, **kw)

    monkeypatch.setattr(Path, "stat", _stat)
    _servis(app, tdb, keep=1)._rotasyon(bdir, "yerel")
    monkeypatch.setattr(Path, "stat", gercek_stat)

    assert (a.exists(), b.exists(), c.exists()) == (False, True, True)
    assert _kayitlar(caplog, logging.WARNING) == [
        ("WARNING", f"Yedek rotasyonu (yerel): dosya okunamadi, ATLANDI: {b}", PermissionError)
    ]


def test_rotasyon_SALT_OKUNUR_0_baytlik_artik_SILINEMEZSE_uyari_ve_KALIR(app, tdb, caplog):
    """0 baytlık yedek artığı salt-okunur (unlink → PermissionError) → WARNING '0 baytlik yedek artigi silinemedi (yerel): <yol>' izle;
    dosya kalır; açılabilen yedek dokunulmadan kalır."""
    bdir = app / "backups"
    saglam = _gecerli_yedek(tdb, bdir / "pemf_treatment_history_20260101_090000.db")
    bos = bdir / "pemf_treatment_history_20260101_080000.db"
    bos.write_bytes(b"")
    os.chmod(bos, stat.S_IREAD)
    try:
        _servis(app, tdb)._rotasyon(bdir, "yerel")

        assert bos.exists() and saglam.exists()
        assert _kayitlar(caplog, logging.WARNING) == [
            ("WARNING", f"0 baytlik yedek artigi silinemedi (yerel): {bos}", PermissionError)
        ]
    finally:
        _yazilabilir_yap(bos)


def test_rotasyon_bir_AILEDE_beklenmeyen_hata_o_aileyi_KORUR_sonraki_aile_YINE_islenir(app, tdb, caplog):
    """Tutma sayısı tam sayı değil (2.5) → 3 geçerli config yedeğinin dilimlenmesi TypeError → WARNING 'Yedek rotasyonu uyarisi (yerel,
    config)' izle, config yedeklerinin HİÇBİRİ silinmez; sonraki aile (treatment_history) yine işlenir: 0 baytlık artığı silinir."""
    import json

    caplog.set_level(logging.INFO, logger=_LOG)
    bdir = app / "backups"
    bdir.mkdir()
    configler = []
    for gun in ("01", "02", "03"):
        f = bdir / f"pemf_config_202601{gun}_080000.json"
        f.write_text(json.dumps({"dil": "tr"}), encoding="utf-8")
        configler.append(f)
    bos = bdir / "pemf_treatment_history_20260101_080000.db"
    bos.write_bytes(b"")

    _servis(app, tdb, keep=2.5)._rotasyon(bdir, "yerel")

    assert all(f.exists() for f in configler)
    assert not bos.exists()
    assert _kayitlar(caplog, logging.WARNING) == [("WARNING", "Yedek rotasyonu uyarisi (yerel, config)", TypeError)]
    assert ("INFO", f"0 baytlik yedek artigi silindi (yerel; veri tasimaz): {bos.name}", None) in _kayitlar(caplog)


# ───────────────────────────── doğrulanmış kopya / makine dışı hedef ─────────────────────────────


def test_dogrulanmis_kopya_SON_ada_tasinamaz_ve_GECICI_silinemezse_False_iki_uyari_hedefe_DOKUNULMAZ(
    app, tmp_path, caplog
):
    """Son ad yerinde DİZİN var (os.replace reddeder) ve kaynak salt-okunur (geçici kopya da salt-okunur → silinemez) → False;
    WARNING 'off-machine kopya hatasi (DOGRULANMADI): <kaynak>' ve 'off-machine gecici kopya silinemedi: <geçici>' (ikisi de OSError izi);
    hedef dizin boş kalır."""
    from services.headless_db_maintenance import HeadlessDBMaintenance

    kaynak = tmp_path / "kaynak" / "pemf_treatment_history_20260101_080000.db"
    kaynak.parent.mkdir()
    kaynak.write_bytes(b"SQLite format 3\x00" + b"\x01" * 4096)
    os.chmod(kaynak, stat.S_IREAD)
    hedef = tmp_path / "usb" / kaynak.name
    hedef.mkdir(parents=True)
    gecici = hedef.with_name(hedef.name + ".kopya.tmp")
    try:
        assert HeadlessDBMaintenance._dogrulanmis_kopya(kaynak, hedef) is False

        assert hedef.is_dir() and list(hedef.iterdir()) == []
        assert gecici.exists()
        kayit = _kayitlar(caplog, logging.WARNING)
        assert [m for _s, m, _e in kayit] == [
            f"off-machine kopya hatasi (DOGRULANMADI): {kaynak}",
            f"off-machine gecici kopya silinemedi: {gecici}",
        ]
        assert all(e is not None and issubclass(e, OSError) for _s, _m, e in kayit)
    finally:
        _yazilabilir_yap(kaynak, gecici)


def test_hedef_yolu_COZULEMEZSE_veri_kokunde_SAYILIR_fail_closed(app, tmp_path):
    """Makine dışı hedef dizgisi gömülü NUL içerir (abspath/realpath → ValueError) → _hedef_veri_kokunde_mi True (kopya yapılmaz);
    çözülebilen kök dışı hedef → False."""
    w = _servis(app, None)

    assert w._hedef_veri_kokunde_mi("D:\\PEMF_Yedek\x00kotu") is True
    assert w._hedef_veri_kokunde_mi(str(tmp_path / "usb")) is False


def test_makine_disi_kurulum_ISARETI_okunamazsa_ROTASYON_YAPILMAZ_eski_kopyalar_KALIR_not_YINE_yazilir(
    app, tdb, monkeypatch, tmp_path, caplog
):
    """Yerel kurulum kimliği dosyası yerine DİZİN var (okuma → PermissionError) → makine dışı kopya doğrulanır ama rotasyon YAPILMAZ:
    tutma 1 olsa da eski iki kopya KALIR, hedefe kurulum işareti yazılmaz; WARNING 'Makine disi kurulum isareti yazilamadi/okunamadi
    — rotasyon YAPILMADI: <hedef>' izle; kurtarma notu yine yazılır."""
    import services.headless_db_maintenance as hdm

    usb = tmp_path / "usb"
    eski1 = _gecerli_yedek(tdb, usb / "pemf_treatment_history_20260101_080000.db")
    eski2 = _gecerli_yedek(tdb, usb / "pemf_treatment_history_20260102_080000.db")
    bdir = app / "backups"
    (bdir / ".kurulum_kimligi").mkdir(parents=True)
    yeni = _gecerli_yedek(tdb, bdir / "pemf_treatment_history_20260105_080000.db")
    monkeypatch.setenv("PEMF_BACKUP_DIR", str(usb))

    _servis(app, tdb, keep=1)._copy_offsite([yeni])

    assert sorted(p.name for p in usb.glob("pemf_*")) == sorted([eski1.name, eski2.name, yeni.name])
    assert (usb / yeni.name).read_bytes() == yeni.read_bytes()
    assert not [p.name for p in usb.iterdir() if p.name.startswith(hdm._KURULUM_ISARETI)]
    assert (usb / hdm._OFFSITE_README_NAME).read_text(encoding="utf-8") == hdm._OFFSITE_README_TEXT
    assert (
        "WARNING",
        f"Makine disi kurulum isareti yazilamadi/okunamadi — rotasyon YAPILMADI: {usb}",
        PermissionError,
    ) in _kayitlar(caplog, logging.WARNING)
