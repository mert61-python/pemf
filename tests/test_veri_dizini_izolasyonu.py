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
from pathlib import Path

import pytest


def _gercek_kokler() -> list[Path]:
    """Korunması gereken GERÇEK makine yolları (env monkeypatch'lenmeden ÖNCEki değerler).

    conftest APPDATA'yı test sırasında değiştirir; bu yüzden gerçek değeri toplama anında
    (modül import'unda) yakalıyoruz.
    """
    return [k for k in _GERCEK if k is not None]


_ham_appdata = os.environ.get("APPDATA")
_GERCEK = [
    Path(_ham_appdata) / "PEMF_GUI" if _ham_appdata else None,
    Path(os.path.expanduser("~")) / ".pemf_gui",
]


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
