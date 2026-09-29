# Author: mertaygn, cglrgrkn
"""Denetim 2026-08-15: test süiti GERÇEK kullanıcı veri dizinine yazamamalı.

`tests/conftest.py::_gercek_kurulumu_koru` her testi izole bir veri dizinine bağlar. Bu
koruma 2026-08-08'de eklendi çünkü testler GERÇEK `%APPDATA%\\PEMF_GUI` içinde SQLCipher
anahtarı üretiyordu; anahtar orada belirince canlı (düz-metin) klinik veritabanı bir sonraki
açılışta göçe giriyor, `.plain.bak`/`.enc.tmp` artıkları kalıyor ve DB açılamaz hale
geliyordu. Yani süit, kurulu bir geliştirici/klinik makinesinde HASTA VERİSİNE dokunuyordu.

⚠️ Koruma 2026-08-15'te GERİ ALINABİLİR bulundu. Fixture testin PAYLAŞILAN `monkeypatch`
örneğini kullanıyordu; pytest test başına tek örnek verir ve `undo()` o örnekteki TÜM
işlemleri geri alır. Kendi amacı için `monkeypatch.undo()` yazan bir test (ör.
`test_at_rest_encryption_rollout::_yukselt`) korumayı da siliyordu → sonrasında
`get_app_data_directory()` gerçek `%APPDATA%`ya çözümlenip anahtarı oraya yazıyordu.
Ölçüldü: 13 test sızdırıyordu. Fixture kendi `MonkeyPatch` örneğine geçirildi.

Bu dosya iki şeyi kilitler: (1) izolasyon gerçekten yürürlükte, (2) `monkeypatch.undo()`
onu SÖKEMİYOR. Yollar üretim koduyla (`utils.path_utils`) doğrulanır, kopyalanmaz.
"""

import os
import sys
from pathlib import Path

import pytest

#: pytest'in YÜKLEDİĞİ conftest (`import conftest` DEĞİL: başka bir içe aktarma kipinde ikinci bir kopya
#: yaratır, bütün modül-düzeyi yan etkileri yeniden koşturur ve kopya-2'nin "orijinal" APPDATA'sı
#: kopya-1'in temp kökü olurdu → sentinel sessizce kör). Yoksa meta-test KIRMIZI olur.
_conftest = sys.modules.get("conftest")


def _gercek_kokler() -> list[Path]:
    """Korunması gereken GERÇEK makine yolları (env monkeypatch'lenmeden ÖNCEki değerler).

    ⚠️ D0Ö.05 (B-10.51): APPDATA'yı conftest süreç başında ezer; bu modül toplanırken
    `os.environ["APPDATA"]` ZATEN oturum temp köküdür. Gerçek değer conftest'in ezmeden önce
    sakladığı `_ORIJINAL_APPDATA`'dan alınır (eskiden buradan okunuyordu → sentinel temp
    dizini izliyor, gerçek hasta dizinine yazan yeni bir yol GÖRÜNMÜYORDU).
    """
    return [k for k in _GERCEK if k is not None]


_ham_appdata = getattr(_conftest, "_ORIJINAL_APPDATA", None)
_GERCEK = [
    Path(_ham_appdata) / "PEMF_GUI" if _ham_appdata else None,
    Path(os.path.expanduser("~")) / ".pemf_gui",
]


def test_KRITIK_gercek_kok_sentineli_conftest_EZMEDEN_ONCEKI_appdata():
    """D0Ö.05 (B-10.51): "gerçek kök" sentineli conftest'in OTURUM TEMP KÖKÜNÜ değil, conftest'in
    APPDATA'yı ezmeden önce sakladığı GERÇEK `%APPDATA%\\PEMF_GUI`'yi izlemeli. Aksi hâlde bu
    dosyanın bütün "gerçek dizine yazılmadı" iddiaları temp dizini ölçer; gerçek hasta DB'sine
    yazan yeni bir yol (2026-08-08 hasarı sınıfı) GÖRÜNMEZ."""
    _c = _conftest
    assert _c is not None and Path(_c.__file__).resolve() == (Path(__file__).parent / "conftest.py").resolve(), (
        "pytest'in yüklediği tests/conftest.py bulunamadı (içe aktarma kipi değişmiş olabilir) — sentinel ölçülemez"
    )
    oturum = Path(_c._OTURUM_IZOLE).resolve()
    if _GERCEK[0] is not None:
        assert not _GERCEK[0].resolve().is_relative_to(oturum), (
            f"'gerçek kök' sentineli conftest'in OTURUM TEMP kökünde: {_GERCEK[0]} — gerçek dizin izlenmiyor (kör)"
        )
        # Kopyadan bağımsız: hangi conftest kopyası olursa olsun hiçbir oturum temp kökü gerçek sayılmaz.
        assert not any(p.startswith("pemf_test_veri_") for p in _GERCEK[0].parts), (
            f"sentinel bir test oturumu temp kökünü izliyor: {_GERCEK[0]}"
        )
    assert hasattr(_c, "_ORIJINAL_APPDATA"), "conftest APPDATA'nın ezilmeden önceki değerini SAKLAMIYOR"
    if os.name == "nt":
        # Windows'ta APPDATA her zaman tanımlıdır; boş/None değer sentineli SESSİZCE düşürürdü.
        assert _c._ORIJINAL_APPDATA, "conftest'in sakladığı APPDATA BOŞ — gerçek kök sentineli sessizce düştü"
    beklenen = Path(_c._ORIJINAL_APPDATA) / "PEMF_GUI" if _c._ORIJINAL_APPDATA else None
    assert _GERCEK[0] == beklenen, (
        f"sentinel conftest'in sakladığı gerçek değerden türemiyor: {_GERCEK[0]} != {beklenen}"
    )
    # Tüketiciler de aynı değeri görmeli (davranış testleri `_gercek_kokler()`/`_ham_appdata`'yı kullanır).
    assert _ham_appdata == _c._ORIJINAL_APPDATA, f"_ham_appdata ({_ham_appdata!r}) conftest'in değerinden türemiyor"
    if beklenen is not None:
        assert beklenen in _gercek_kokler(), f"gerçek APPDATA kökü izlenen kökler arasında YOK: {_gercek_kokler()}"


def test_izolasyon_yururlukte():
    """Üretim yol çözücüsü temp dizine bakmalı — gerçek `%APPDATA%`ya DEĞİL."""
    from utils.path_utils import get_app_data_directory

    coz = get_app_data_directory()
    for gercek in _gercek_kokler():
        assert coz != gercek, (
            f"veri dizini GERÇEK kuruluma çözümlendi: {coz}. conftest izolasyonu çalışmıyor — "
            "bu süit canlı klinik verisine yazabilir."
        )
    assert "PEMF_DATA_DIR" in os.environ, "izolasyon PEMF_DATA_DIR'i ayarlamamış"


def test_KRITIK_makine_kimlik_deposu_da_IZOLE(tmp_path):
    """⚠️ ÖLÇÜLEN SIZINTI (2026-08-28): süit GERÇEK makine kimlik deposuna yazdı.

    `device_registry_secret` artık veri kökünün DIŞINDA, makine kapsamlı bir dosyada tutuluyor
    (`%ProgramData%\\PEMF_System\\device_identity.json`) — bu yol `PEMF_DATA_DIR`e BAKMAZ,
    dolayısıyla mevcut izolasyon onu kapsamıyordu. Süit gerçek dosyaya TEST SIRRI yazdı ve
    oradaki değer klinik cihazınkinden FARKLI çıktı (ölçüldü). Sonucu sinsi: veri kökü bir gün
    yenilendiğinde o yanlış sır kullanılır ve yeni düzeltilen `secret_mismatch` arızası GERİ
    GELİR — üstelik sebebi test süiti olur.
    """
    from utils.secrets_manager import _cihaz_kimlik_deposu

    assert "PEMF_DEVICE_IDENTITY_DIR" in os.environ, (
        "conftest makine kimlik deposunu izole etmemiş — süit gerçek cihaz sırrını EZEBİLİR"
    )
    coz = str(_cihaz_kimlik_deposu()).lower()
    for gercek in (r"c:\programdata\pemf_system", "/var/lib/pemf"):
        assert not coz.startswith(gercek.lower()), (
            f"makine kimlik deposu GERÇEK kuruluma çözümlendi: {coz} — süit klinik cihazının bulut sırrını bozabilir"
        )


def test_KRITIK_suit_gercek_cihaz_sirrini_YAZMAZ():
    """Davranışsal: gerçek depo dosyası bu süit sırasında DEĞİŞMEMELİ.

    (Dosya yoksa test anlamlıdır: oluşmamış olması da doğru sonuçtur.)"""
    from pathlib import Path

    gercek = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "PEMF_System" / "device_identity.json"
    onceki = gercek.read_bytes() if gercek.is_file() else None

    from utils.secrets_manager import get_secret

    get_secret("device_registry_secret")  # izole ortamda koşmalı

    sonraki = gercek.read_bytes() if gercek.is_file() else None
    assert onceki == sonraki, "süit GERÇEK makine kimlik deposunu değiştirdi — klinik cihazının bulut mührü bozulabilir"


def test_KRITIK_monkeypatch_undo_izolasyonu_SOKEMEZ(monkeypatch):
    """🔴 ASIL REGRESYON: bir testin `monkeypatch.undo()`su korumayı kaldırmamalı.

    Koruma testin paylaşılan `monkeypatch`ine geri taşınırsa bu test kırmızıya döner.
    """
    from utils.path_utils import get_app_data_directory

    onceki = get_app_data_directory()
    # Testin kendi amacı için yaptığı tipik şey — sonra hepsini geri alması:
    monkeypatch.setenv("PEMF_ORNEK_DEGISKEN", "1")
    monkeypatch.undo()

    sonraki = get_app_data_directory()
    assert sonraki == onceki, (
        f"monkeypatch.undo() veri-dizini izolasyonunu SÖKTÜ ({onceki} -> {sonraki}). "
        "conftest koruması KENDİ MonkeyPatch örneğini kullanmalı; testin paylaşılan "
        "`monkeypatch` fixture'ını DEĞİL."
    )
    for gercek in _gercek_kokler():
        assert sonraki != gercek, f"undo() sonrası GERÇEK kuruluma düştü: {sonraki}"


def test_KRITIK_undo_sonrasi_sir_yazimi_gercek_dizine_GITMEZ(monkeypatch, tmp_path):
    """Sonuç odaklı kanıt: `undo()` sonrası üretilen SQLCipher anahtarı nereye yazılıyor?

    Yol karşılaştırması dolaylıdır; bu test GERÇEKTEN sır yazdırır ve gerçek dizinin
    dokunulmamış kaldığını dosya sistemiyle doğrular. Asıl hasar buydu.
    """
    from utils.secrets_manager import secrets_path, set_secret

    gercekler = _gercek_kokler()
    onceki_durum = {g: (sorted(p.name for p in g.iterdir()) if g.is_dir() else None) for g in gercekler}

    monkeypatch.setenv("PEMF_ORNEK_DEGISKEN", "1")
    monkeypatch.undo()

    # ⚠️ YAZIMDAN ÖNCE DUR (inceleme bulgusu): sentinel artık GERÇEK dizini izliyor; izolasyon gerilerse
    # aşağıdaki `set_secret` sahibin GERÇEK `pemf_secrets.json`'undaki at-rest anahtarını test değeriyle
    # EZER — kırmızı gelmeden önce hasar olurdu. Yol gerçek bir köke çözülüyorsa hiç yazılmaz.
    yazilacak = secrets_path()
    for g in gercekler:
        if str(yazilacak).lower().startswith(str(g).lower()):
            pytest.fail(f"undo() sonrası sır yolu GERÇEK veri dizinine çözüldü ({yazilacak}) — YAZILMADAN durduruldu")

    set_secret("sqlcipher_key", "TEST-ANAHTARI-DISKE-YAZILMAMALI")
    yazilan = secrets_path()

    for g in gercekler:
        assert not str(yazilan).lower().startswith(str(g).lower()), f"sır GERÇEK veri dizinine yazıldı: {yazilan}"
        simdiki = sorted(p.name for p in g.iterdir()) if g.is_dir() else None
        assert simdiki == onceki_durum[g], f"GERÇEK dizin değişti: {g}\n  önce: {onceki_durum[g]}\n  sonra: {simdiki}"
    assert yazilan.is_file(), "sır hiç yazılmamış — test kendi ön koşulunu kuramadı"


def test_KRITIK_koruma_TOPLAMA_zamaninda_kurulur():
    """🔴 İKİNCİ REGRESYON: koruma fixture'ları BEKLEYEMEZ — import zamanı da kapsanmalı.

    pytest test modüllerini TOPLAMA sırasında import eder; bu, hiçbir fixture çalışmadan önce
    olur. Bazı test modülleri modül seviyesinde üretim modülü import ediyor ve zincir
    `pemf_gui/config.py`'deki modül-seviyesi singleton'a varıyor — o da constructor'ında
    şifreleme anahtarı üretip DİSKE YAZIYOR. Yani sadece `import` etmek bile GERÇEK
    `%APPDATA%\\PEMF_GUI\\pemf_secrets.json` dosyasını oluşturuyordu (ölçüldü: fixture
    düzeltmesinden sonra bile 7 test sızdırıyordu).

    Bu test conftest'i AYRI bir süreçte, GERÇEK env ile import eder ve izolasyonun daha
    import anında kurulduğunu doğrular. Koruma yalnızca fixture'a geri taşınırsa kırmızıya
    döner.
    """
    import subprocess
    import sys

    tests_dizini = str(Path(__file__).parent)
    kod = (
        "import os, sys\n"
        f"sys.path.insert(0, r'{tests_dizini}')\n"
        "import conftest\n"
        "print('DATA_DIR=' + os.environ.get('PEMF_DATA_DIR', ''))\n"
        "print('APPDATA=' + os.environ.get('APPDATA', ''))\n"
    )
    # ⚠️ Alt sürece GERÇEK değerleri ver: bu test pytest içinde koştuğu için os.environ ZATEN
    # izole; onu miras alırsak test kendini kandırır (koruma sökülse bile yeşil kalırdı).
    ortam = {**os.environ}
    if _ham_appdata:
        ortam["APPDATA"] = _ham_appdata
    ortam.pop("PEMF_DATA_DIR", None)

    r = subprocess.run(
        [sys.executable, "-c", kod],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=ortam,
        timeout=120,
    )
    assert r.returncode == 0, f"conftest import edilemedi:\n{r.stdout}\n{r.stderr}"

    degerler = dict(s.split("=", 1) for s in r.stdout.strip().splitlines() if "=" in s)
    assert degerler.get("DATA_DIR"), (
        "conftest import edilince PEMF_DATA_DIR ayarlanmadı → toplama sırasındaki import "
        "yan etkileri GERÇEK veri dizinine yazar."
    )
    for anahtar in ("DATA_DIR", "APPDATA"):
        deger = degerler.get(anahtar, "")
        if _ham_appdata:
            assert deger != _ham_appdata, f"{anahtar} import sonrası hâlâ GERÇEK yolu gösteriyor ({deger})."


def test_konteyner_fixture_de_kendi_monkeypatchini_kullanir():
    """`temp_app_data` de aynı hataya düşmemeli — kaynak kodda doğrula.

    Davranışsal testi zor (fixture'ı undo eden bir testi burada kuramayız), ama regresyonun
    tek belirtisi net: paylaşılan `monkeypatch` parametresini geri almak.
    """
    kaynak = (Path(__file__).parent / "conftest.py").read_text(encoding="utf-8")
    for fixture in ("_gercek_kurulumu_koru", "temp_app_data"):
        govde = kaynak.split(f"def {fixture}(", 1)
        assert len(govde) == 2, f"{fixture} conftest'te bulunamadı"
        imza = govde[1].split(")", 1)[0]
        assert "monkeypatch" not in imza, (
            f"{fixture} PAYLAŞILAN `monkeypatch` fixture'ını alıyor (imza: {imza}). "
            "Bir testin `monkeypatch.undo()`su izolasyonu siler — kendi "
            "`pytest.MonkeyPatch()` örneğini kullanmalı."
        )
