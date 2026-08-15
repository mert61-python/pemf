# Author: mertaygn, cglrgrkn
"""pytest ortak ayarı — guii kökünü import yoluna ekler ve izole temp app_data sağlar."""

import os
import sys
import tempfile
from pathlib import Path

import pytest

_GUII_ROOT = Path(__file__).resolve().parent.parent
if str(_GUII_ROOT) not in sys.path:
    sys.path.insert(0, str(_GUII_ROOT))


# ─────────────────────────────────────────────────────────────────────────────
# TOPLAMA-ZAMANI KORUMASI (fixture'lardan ÖNCE — MODÜL SEVİYESİNDE ÇALIŞIR)
# ─────────────────────────────────────────────────────────────────────────────
# ⚠️ DENETİM 2026-08-15: aşağıdaki `_gercek_kurulumu_koru` fixture'ı YETMİYOR, çünkü pytest
# test modüllerini TOPLAMA sırasında import eder ve bu, hiçbir fixture çalışmadan ÖNCE olur.
# Bazı test modülleri modül seviyesinde üretim modülü import ediyor; zincir şuraya varıyor:
#     tests/test_patient_encryption.py (import)
#       → database/patient_database.py  (modül seviyesi)
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


@pytest.fixture(autouse=True)
def _gercek_kurulumu_koru(tmp_path):
    """⚠️ HİÇBİR TEST GERÇEK KURULUMA DOKUNAMAZ — 2026-08-08 denetiminde bulundu.

    ARIZA: `TestClient(api_server.app)` kullanan test dosyaları (test_auth, test_api_design,
    test_ai_review…) izole bir veri dizini AYARLAMIYORDU. `utils/secrets_manager` yolunu global
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
    Eskiden yalnız `APPDATA` ayarlanıyordu. Ama `utils/secrets_manager` yolunu kendisine geçilen
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
