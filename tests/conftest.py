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


@pytest.fixture(autouse=True)
def _gercek_kurulumu_koru(tmp_path, monkeypatch):
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
    """
    izole = tmp_path / "_izole_appdata"
    (izole / "PEMF_GUI").mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("PEMF_DATA_DIR", str(izole))
    monkeypatch.setenv("APPDATA", str(izole))
    try:
        import utils.secrets_manager as sm

        sm._cache = None
    except Exception:
        pass
    yield
    try:
        import utils.secrets_manager as sm

        sm._cache = None
    except Exception:
        pass


@pytest.fixture()
def temp_app_data(tmp_path, monkeypatch):
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
    """
    d = tmp_path / "PEMF_GUI"
    d.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setenv("PEMF_DATA_DIR", str(tmp_path))

    def _onbellegi_temizle():
        try:
            import utils.secrets_manager as sm

            sm._cache = None
        except Exception:
            pass

    _onbellegi_temizle()
    yield d
    _onbellegi_temizle()
