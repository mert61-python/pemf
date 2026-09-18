# Author: mertaygn, cglrgrkn
"""pytest ortak ayarı — guii kökünü import yoluna ekler ve izole temp app_data sağlar."""

import os
import sys
import tempfile
import threading
from pathlib import Path

import pytest

_GUII_ROOT = Path(__file__).resolve().parent.parent
if str(_GUII_ROOT) not in sys.path:
    sys.path.insert(0, str(_GUII_ROOT))

# ⚠️ URUN PAKETLERI `apps/backend/` ALTINDA (2026-09-18, klasor duzeni F4).
# Import adlari degismedi (`from utils.x import y`) ama o dizin yola EKLENMELI.
# Buraya konmasi 202 test dosyasinin hepsini kapsar: onlarin kendi
# `sys.path.insert(kok)` satirlari ARTIK YETMEZ, kok paketleri tasimiyor.
_BACKEND_KOKU = _GUII_ROOT / "apps" / "backend"
if str(_BACKEND_KOKU) not in sys.path:
    sys.path.insert(0, str(_BACKEND_KOKU))


# ─────────────────────────────────────────────────────────────────────────────
# TOPLAMA-ZAMANI KORUMASI (fixture'lardan ÖNCE — MODÜL SEVİYESİNDE ÇALIŞIR)
# ─────────────────────────────────────────────────────────────────────────────
# ⚠️ DENETİM 2026-08-15: aşağıdaki `_gercek_kurulumu_koru` fixture'ı YETMİYOR, çünkü pytest
# test modüllerini TOPLAMA sırasında import eder ve bu, hiçbir fixture çalışmadan ÖNCE olur.
# Bazı test modülleri modül seviyesinde üretim modülü import ediyor; zincir şuraya varıyor:
#     tests/test_patient_encryption.py (import)
#       → apps/backend/database/patient_database.py  (modül seviyesi)
#         → pemf_gui/config.py:346      (modül seviyesi SINGLETON)
#           → Config.__init__ → _get_or_create_key → secrets_manager.get_secret
# Yani PUAN: sadece `import` etmek bile GERÇEK `%APPDATA%\PEMF_GUI` içinde bir şifreleme
# anahtarı (`pemf_secrets.json`) ÜRETİP DİSKE YAZIYORDU. Anahtar orada belirince canlı
# (düz-metin) klinik veritabanı bir sonraki açılışta göçe girer, `.plain.bak` artığı bırakır
# ve "file is not a database" ile açılamaz hale gelir — yani süit, kurulu bir makinede HASTA
# VERİSİNE dokunuyordu. Ölçüldü: fixture düzeltmesinden SONRA bile 7 test sızdırıyordu.
#
# ÇÖZÜM: izolasyonu süreç başına, conftest IMPORT EDİLİRKEN kur. conftest her zaman test
# modüllerinden ÖNCE import edilir → import yan etkileri de yakalanır. Test başına izolasyon
# (aşağıdaki fixture) bunun ÜSTÜNE biner; bu yalnızca taban güvenliktir.
# (Regresyonu `test_veri_dizini_izolasyonu.py` kilitliyor.)
_OTURUM_IZOLE = Path(tempfile.mkdtemp(prefix="pemf_test_veri_"))
(_OTURUM_IZOLE / "PEMF_GUI").mkdir(parents=True, exist_ok=True)
os.environ["PEMF_DATA_DIR"] = str(_OTURUM_IZOLE)
os.environ["APPDATA"] = str(_OTURUM_IZOLE)
# ⚠️ DENETİM 2026-08-28 #02: `device_registry_secret` artık VERİ KÖKÜNÜN DIŞINDA, makine
# kapsamlı bir dosyada tutuluyor (`apps/backend/utils/secrets_manager._cihaz_kimlik_deposu`). O yol
# `PEMF_DATA_DIR`e BAKMAZ → yukarıdaki izolasyon onu KAPSAMAZ. ÖLÇÜLDÜ: süit, gerçek
# `C:\ProgramData\PEMF_System\device_identity.json` dosyasına TEST SIRRI yazdı ve
# oradaki değer klinik cihazınkinden FARKLIYDI. Sonucu sinsi: veri kökü bir gün
# yenilendiğinde o yanlış sır kullanılır ve düzeltilen `secret_mismatch` arızası GERİ GELİR.
# (Aynı sınıf: `test_veri_dizini_izolasyonu.py`nin kilitlediği eski sızıntı.)
os.environ["PEMF_DEVICE_IDENTITY_DIR"] = str(_OTURUM_IZOLE / "makine_kimligi")
# Scratch CPN warmup thread'i testte ASLA başlamasın (CI ölçümü 2026-08-26, exit 134:
# daemon thread + interpreter kapanışı yarışı — app.py'de find_spec ön-kontrolü de var,
# bu satır çift emniyet + testlerin startup davranışını deterministik kılar).
os.environ.setdefault("PEMF_SCRATCH_WARMUP", "0")


@pytest.fixture(autouse=True)
def _gercek_kurulumu_koru(tmp_path):
    """⚠️ HİÇBİR TEST GERÇEK KURULUMA DOKUNAMAZ — 2026-08-08 denetiminde bulundu.

    ARIZA: `TestClient(api_server.app)` kullanan test dosyaları (test_auth, test_api_design,
    test_ai_review…) izole bir veri dizini AYARLAMIYORDU. `apps/backend/utils/secrets_manager` yolunu global
    `get_app_data_directory()`'den aldığı için bu testler GERÇEK `%APPDATA%\\PEMF_GUI` dizinine
    yazıyordu: orada SQLCipher anahtarı üretildi → gerçek (düz-metin) klinik veritabanı bir
    sonraki açılışta GÖÇE girdi, `.plain.bak` / `.enc.tmp` artıkları bıraktı ve testler
    "file is not a database" ile düşmeye başladı.

    Yani test süiti, canlı kurulumu olan bir geliştirici/klinik makinesinde HASTA
    VERİTABANINI değiştirebiliyordu. Bu fixture zinciri kökten keser: her test kendi temp
    dizinini kullanır. Gerçek dizine yazmak İSTEYEN bir test olursa bunu AÇIKÇA ezmelidir.

    ⚠️ DENETİM 2026-08-15 — KORUMA GERİ ALINABİLİYORDU (sızıntı ÖLÇÜLDÜ, 13 test).
    Bu fixture testin `monkeypatch` fixture'ını kullanıyordu. pytest test başına TEK
    `MonkeyPatch` örneği verir ve `undo()` o örnekteki TÜM işlemleri geri alır — yani bir
    testin kendi amacı için yazdığı `monkeypatch.undo()`, farkında olmadan BU KORUMAYI da
    siliyordu. Sonrasında `get_app_data_directory()` gerçek `%APPDATA%`ya çözümlenip
    `pemf_secrets.json`i (SQLCipher anahtarı) GERÇEK dizine yazıyordu — docstring'in
    yukarıda anlattığı hasarın aynısı, farklı bir kapıdan.
    ÇÖZÜM: koruma artık KENDİ `MonkeyPatch` örneğini kullanır. Testin `undo()`su ona
    erişemez; koruma yalnız bu fixture'ın teardown'ında kalkar.
    (Tekrarını `test_veri_dizini_izolasyonu.py` kilitliyor.)
    """
    izole = tmp_path / "_izole_appdata"
    (izole / "PEMF_GUI").mkdir(parents=True, exist_ok=True)
    mp = pytest.MonkeyPatch()
    mp.setenv("PEMF_DATA_DIR", str(izole))
    mp.setenv("APPDATA", str(izole))
    # Denetim #02: makine kapsamlı bulut-kimlik deposu da izole edilmeli (veri kökünün dışında).
    mp.setenv("PEMF_DEVICE_IDENTITY_DIR", str(izole / "makine_kimligi"))
    try:
        import utils.secrets_manager as sm

        sm._cache = None
    except Exception:
        pass
    yield
    mp.undo()
    try:
        import utils.secrets_manager as sm

        sm._cache = None
    except Exception:
        pass


@pytest.fixture()
def temp_app_data(tmp_path):
    """Her test için izole app_data dizini (gerçek %APPDATA%/PEMF_GUI'ye dokunma).

    ⚠️ DENETİM 2026-08-08 — GERÇEK KURULUMU BOZAN SIZINTI KAPATILDI.
    Eskiden yalnız `APPDATA` ayarlanıyordu. Ama `apps/backend/utils/secrets_manager` yolunu kendisine geçilen
    `app_data_dir` argümanından DEĞİL, global `utils.path_utils.get_app_data_directory()`'den
    alır ve o da önce `PEMF_DATA_DIR`'e bakar. Sonuç: temp dizinle kurulan bir test DB'si,
    SQLCipher anahtarını GERÇEK `%APPDATA%\\PEMF_GUI\\pemf_secrets.json` dosyasına yazıyordu.
    Anahtar orada belirince gerçek (düz-metin) klinik veritabanı bir sonraki açılışta GÖÇE
    giriyor; `.plain.bak` / `.enc.tmp` artıkları bırakıyor ve testler "file is not a database"
    ile patlıyordu. Yani test süiti, canlı kurulumu olan bir makinede HASTA VERİTABANINA
    dokunabiliyordu. `PEMF_DATA_DIR` de izole edilerek zincir kesildi.

    Ayrıca süreç-geneli sır önbelleği temizlenir: bir testte üretilen anahtar sonraki testin
    BAŞKA dizinine taşınırsa, onun düz-metin DB'si şifreli sanılır ve testler birbirini düşürür.

    ⚠️ DENETİM 2026-08-15: bu fixture de testin PAYLAŞILAN `monkeypatch`ini kullanıyordu →
    testin kendi amacı için yazdığı `monkeypatch.undo()` izolasyonu da siliyordu
    (ayrıntı: `_gercek_kurulumu_koru`). Kendi `MonkeyPatch` örneğine geçirildi.
    """
    d = tmp_path / "PEMF_GUI"
    d.mkdir(parents=True, exist_ok=True)
    mp = pytest.MonkeyPatch()
    mp.setenv("APPDATA", str(tmp_path))
    mp.setenv("PEMF_DATA_DIR", str(tmp_path))
    # Denetim #02: bkz. yukarıdaki not — bu yol PEMF_DATA_DIR'e bakmaz, ayrıca izole edilir.
    mp.setenv("PEMF_DEVICE_IDENTITY_DIR", str(tmp_path / "makine_kimligi"))

    def _onbellegi_temizle():
        try:
            import utils.secrets_manager as sm

            sm._cache = None
        except Exception:
            pass

    _onbellegi_temizle()
    yield d
    mp.undo()
    _onbellegi_temizle()


@pytest.fixture(autouse=True)
def _masaustunu_koru(tmp_path):
    """⚠️ HİÇBİR TEST SAHİBİN MASAÜSTÜNE DOSYA BIRAKAMAZ — 2026-09-11'de ölçüldü.

    ===========================================================================
    ARIZA
    ===========================================================================
    Sahip "uygulama açık bile değil, masaüstüne sürekli yeni CSV geliyor" dedi.
    Masaüstünde 18 adet `PEMF_alan_*.csv` birikmişti; içerikleri
    `operator_name,op` / `patient_name,Boncuk` — yani TEST FIXTURE verisi. Zaman
    damgaları süit koşularıyla birebir örtüşüyordu.

    `/session/start` yolundan geçen her test `api_server._seans_alan` SINGLETON'ını
    tetikliyor, o da `masaustu_dizini()` → `~/Desktop` çözüp oraya GERÇEKTEN dosya
    yazıyordu. Kendi fixture'ında yolu yamalayan iki test (`test_seans_alan_kaydi`,
    `test_seans_yogunluk_uctan_uca`) temizdi; DİĞER HEPSİ sızdırıyordu.

    ===========================================================================
    ⚠️ NEDEN `_gercek_kurulumu_koru` BUNU YAKALAMADI
    ===========================================================================
    O fixture VERİ KÖKÜNÜ izole eder (`APPDATA`, `PEMF_DATA_DIR`, cihaz kimliği).
    Masaüstü veri kökü DEĞİLDİR ve `~` üzerinden çözülür. 2026-09-11'de masaüstüne
    yazan yeni bir özellik eklendiğinde izolasyon onunla birlikte genişletilmedi —
    bu deponun tekrar eden "koruma yazıldı ama YENİ yola uygulanmadı" sınıfı.

    ===========================================================================
    ⚠️ NEDEN `HOME`/`USERPROFILE` EZİLMEDİ (denendi, REDDEDİLDİ)
    ===========================================================================
    Tek satırda her `~` kullanıcısını (CSV + PDF + gelecekteki her yazıcı) kapatırdı
    ama İKİ ZARARI ölçüldü:
      1. `test_veri_dizini_izolasyonu.py` GERÇEK `~/.pemf_gui`ye bakarak sızıntı arar.
         `~` sahteye çevrilseydi o kapı izole dizini ölçer ve SESSİZCE sahte-yeşile
         dönerdi — var olan bir korumayı hadım etmek, yeni bir koruma eklemekten
         daha pahalıdır.
      2. `test_gitleaks_config_derlenir.py` gitleaks ikilisini `Path.home()/.cache`
         altında arar; bulamazsa kapı işlevsizleşir.
    Bu yüzden `~` DOKUNULMADAN kalır; yalnız masaüstüne YAZAN uçlar yönlendirilir.

    ===========================================================================
    NEDEN MODÜL NİTELİĞİ YAMANIYOR (import edilmiş ada DEĞİL)
    ===========================================================================
    `seans_basladi()` her çağrıda modül globalinden `masaustu_dizini()` okur → yama
    etkilidir. Buna karşılık `test_seans_alan_kaydi.py` fonksiyonu `from ... import`
    ile ALMIŞTIR; o bağ import anında kurulduğu için ORİJİNALİ gösterir ve
    `systemprofile` davranışını sınayan kapı BOZULMADAN çalışmaya devam eder.
    (İkisi de ölçüldü.)

    Kapı: `tests/test_masaustu_sizintisi.py` — bu fixture kaldırılırsa KIRMIZI.
    """
    hedef = tmp_path / "sahte_masaustu"
    hedef.mkdir(parents=True, exist_ok=True)
    mp = pytest.MonkeyPatch()

    try:
        import servers.seans_alan_kaydi as _sak

        # ⚠️ ORİJİNAL SAKLANIR: üretim mantığını (systemprofile reddi, aday sırası)
        # SINAYAN testler buna ihtiyaç duyar. Yamalı sürümle sınamak, kapının
        # KENDİ SAHTESİNİ doğrulaması olurdu.
        # ⚠️ Fonksiyon GÖVDESİNDE `from ... import masaustu_dizini` yapmak YETMEZ:
        # o satır test sırasında koşar ve YAMALI niteliği alır (ölçüldü). Yalnız
        # MODÜL SEVİYESİNDE import eden dosyalar (test_seans_alan_kaydi.py)
        # orijinale bağlı kalır — çünkü o bağ toplama anında kurulur.
        mp.setattr(_sak, "_orijinal_masaustu_dizini", _sak.masaustu_dizini, raising=False)
        mp.setattr(_sak, "masaustu_dizini", lambda: (hedef, "test izolasyonu"), raising=False)
    except Exception:
        pass

    # PDF raporları da masaüstüne yazar (`apps/backend/utils/pdf_report_generator._default_output_path`).
    # ⚠️ Bugün süitte sızıntı ÜRETMİYOR (masaüstünde test PDF'i yok) ama AYNI SINIF:
    # yolu burada da kapatmak, yarın bir testin rapor üretmesiyle sızıntının geri
    # gelmesini engeller. Sınıfı kapatmak, örneği kapatmaktan daha ucuzdur.
    try:
        from utils.pdf_report_generator import PDFReportGenerator as _PDF

        _orijinal = _PDF._default_output_path

        def _izole_yol(self, prefix: str, name_hint: str = "") -> str:
            ham = _orijinal(self, prefix, name_hint)
            return str(hedef / Path(ham).name)

        mp.setattr(_PDF, "_default_output_path", _izole_yol, raising=False)
    except Exception:
        pass

    yield hedef
    mp.undo()


# ⚠️ `tests/` dizinini de yola ekle: `capraz.py` ve `topoloji.py` YARDIMCI modüllerdir
# (adları `test_*` olmadığı için pytest onları toplamaz) ve test dosyaları bunları
# `import topoloji` ile alır. Eskiden her dosya kendi `sys.path.insert`ini yapıyordu;
# tek yerde olması, yeni bir test dosyasının import'u unutup ImportError almasını önler.
if str(_TESTS_DIR := Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(_TESTS_DIR))


@pytest.fixture(autouse=True)
def _ack_bekcilerini_bosalt():
    """⚠️ ACK BEKÇİSİ SONRAKİ TESTE SIZAR — 2026-09-15'te CI'da ölçüldü (koşu 35005619586).

    ===========================================================================
    ARIZA
    ===========================================================================
    `windows-latest` matrisinde `test_KARSIT_KANIT_timeout_metni_DEGISMEDI` düştü.
    Kendi `uyarilar` listesinde BEŞ kayıt vardı ve kendi uyarısı ÜÇÜNCÜ sıradaydı:

        [('⚠️ Bobin 8: start onayı gelmedi …', 'warning'),      <- YABANCI
         ('⚠️ Bobin 8: start onayı gelmedi …', 'warning'),      <- YABANCI
         ('⚠️ Bobin 8: acil durdurma ESP onayı GELMEDİ …', 'error'),   <- kendi
         …]

    KÖK NEDEN: `_start_ack_izle_arka_planda` **daemon thread** açıyor
    (`start-ack-{coil}`) ve o thread `_START_ACK_TIMEOUT = 2.0` sn bekleyip
    `_push_notification` çağırıyor. Testler 2 sn'den KISA sürüyor → thread SONRAKİ
    testin içinde ateşliyor ve o an `_push_notification`'a takılı olan BAŞKA testin
    monkeypatch'ine yazıyor. E-stop bekçisi (`estop-ack-{coil}`) aynı desende.

    ⚠️ NEDEN YERELDE GEÇİYOR, CI'DA DÜŞÜYOR: tamamen ZAMANLAMA. Tam süit bu makinede
    iki kez yeşil geçti; CI runner'ının farklı hızında sıra kaydı. "Kararsız test"
    denip geçilecek sınıf DEĞİL — bu bir test-izolasyon arızası ve hangi testi
    vuracağı rastgele.

    ===========================================================================
    ⚠️ NEDEN TEARDOWN'DA (setup'ta değil)
    ===========================================================================
    Sızıntıyı ÜRETEN test kendi teardown'ında temizlemeli; sonraki testin setup'ına
    bırakmak, araya giren her fixture sırasında pencereyi açık bırakır. Ayrıca
    autouse conftest fixture'ı testin kendi `monkeypatch`inden ÖNCE kurulur, yani
    SONRA yıkılır → burada `_push_notification` artık GERÇEK fonksiyondur ve
    boşaltma kimsenin listesine yazmaz.

    ⚠️ THREAD ÖLDÜRÜLEMEZ (Python). Bu yüzden bekleyen `Event`'ler SET edilir →
    `_wait_ack` hemen döner → thread kendi akışını tamamlayıp biter; sonra `join`.
    Kayıt sözlüğü de temizlenir.
    """
    yield
    try:
        from servers import api_server as _api
    except Exception:
        return
    try:
        with _api._pending_acks_lock:
            for _giris in list(_api._pending_acks.values()):
                try:
                    _giris["event"].set()
                except Exception:
                    pass
            _api._pending_acks.clear()
    except Exception:
        pass
    for _t in list(threading.enumerate()):
        _ad = getattr(_t, "name", "") or ""
        if _ad.startswith(("start-ack-", "estop-ack-")) and _t.is_alive():
            try:
                _t.join(timeout=2.5)
            except Exception:
                pass
