# Author: mertaygn, cglrgrkn
"""GÖÇ, ÇÖZÜLEMEYEN BİR ANAHTARI HEDEFE YAZMAMALI + HASTA DB'si GERÇEKTEN TAŞINMALI.

İKİ AYRI KUSUR (2026-08-15 kampanyası, düşmanca doğrulamadan geçti):

**(1) YENİ BİR TUĞLALAŞMA YOLU.** `_sqlcipher_anahtarini_gocur`, eski kökteki HAM
(DPAPI/MKEY ile sarılı) `sqlcipher_key` değerini hedefe OLDUĞU GİBİ kopyalıyordu. Değer BU
makinede çözülemiyorsa (blob başka bir makine/kullanıcı bağlamında sarılmış), hedefte artık
"saklanmış ama çözülemeyen" bir sır bulunur → `get_secret` fail-closed `RuntimeError` atar →
**backend hiç açılmaz.** Yani göç, ÇALIŞAN bir kurulumu açılamaz hâle getirebiliyordu.

⚠️ Kapı `_dec`e devreder — önek/bayrak TEK KAYNAKTA kalsın diye. Kendi ctypes kopyasını
yazmak `DPAPI:` dışındaki `MKEY:` önekini kapsamaz ve aynı tuğlayı açık bırakırdı.

⚠️ ÖZYİNELEME SINIRI (1.9.9/1.9.10'da BSOD'a yol açtı, 1.9.11'de düzeltildi): göç yolu
`get_sqlcipher_key`/`get_app_data_directory` çağırMAMALI. `_dec` yol/dosya katmanına
dokunmaz; testler bunu ölçerek kilitler.

**(2) HASTA DB'si GÖÇTE HİÇ TAŞINMIYORDU.** `_GOC_DOSYALARI` dosyayı "pemf_patients.db"
olarak arıyordu; üretimdeki ad "patients.db". `pemf_patients.db` hiçbir sürümde üretim adı
olmadı (yalnız YEDEK dosya ön-ekidir). Sonuç: "vardiyalı klinikte boş klinik" düzeltmesi
seans geçmişini taşıyor, HASTA KAYITLARINI taşımıyordu.

⚠️ İKİ SATIR BİRLİKTE düzeltilmeli: yalnız `_GOC_DOSYALARI` düzeltilirse `ad in _GOC_SIFRELI`
tutmaz ve şifreli hasta DB'si ANAHTAR KONTROLÜ YAPILMADAN körlemesine kopyalanır.
"""

import base64
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils import path_utils  # noqa: E402
from utils import secrets_manager as sm  # noqa: E402

COZULEMEZ_DPAPI = sm._DPAPI_PREFIX + base64.b64encode(b"baska-makinenin-blobu").decode("ascii")
COZULEMEZ_MKEY = sm._MKEY_PREFIX + base64.b64encode(b"baska-makinenin-fernet").decode("ascii")


def _sir_yaz(kok: Path, anahtar: str):
    kok.mkdir(parents=True, exist_ok=True)
    (kok / "pemf_secrets.json").write_text(
        json.dumps({"auto": {"sqlcipher_key": anahtar}}, ensure_ascii=False), encoding="utf-8"
    )


def _hedef_anahtari(kok: Path):
    j = kok / "pemf_secrets.json"
    if not j.is_file():
        return None
    return (json.loads(j.read_text(encoding="utf-8")).get("auto") or {}).get("sqlcipher_key")


# ── (1) ANAHTAR KAPISI ──────────────────────────────────────────────────────


def test_KRITIK_COZULEMEYEN_anahtar_hedefe_YAZILMAZ(tmp_path):
    """Asıl tuğlalaşma: çözülemeyen blob hedefe yazılırsa backend bir daha hiç açılmaz."""
    eski, hedef = tmp_path / "eski", tmp_path / "hedef"
    _sir_yaz(eski, COZULEMEZ_DPAPI)
    hedef.mkdir(parents=True)

    tasindi = path_utils._sqlcipher_anahtarini_gocur(eski, hedef)

    assert tasindi is False, "cozulemeyen anahtar tasindi → hedefte 'saklanmis ama cozulemez' sir kalir"
    assert _hedef_anahtari(hedef) is None, "hedefe cozulemeyen deger YAZILMIS → backend acilmaz"


def test_KRITIK_MKEY_oneki_de_KAPSANIR(tmp_path):
    """Kapı yalnız `DPAPI:` bakarsa `MKEY:` (Linux/macOS yolu) aynı tuğlayı açık bırakır."""
    eski, hedef = tmp_path / "eski", tmp_path / "hedef"
    _sir_yaz(eski, COZULEMEZ_MKEY)
    hedef.mkdir(parents=True)

    path_utils._sqlcipher_anahtarini_gocur(eski, hedef)

    assert _hedef_anahtari(hedef) is None, "MKEY onekli cozulemeyen deger tasindi (onek kapsami eksik)"


def test_DUZ_METIN_anahtar_TASINIR_karsit_kanit(tmp_path):
    """Karşı-kanıt: kapı her şeyi reddederek de geçemez. Düz-metin (önek yok) değer makineye
    bağlı DEĞİLDİR; taşınması güvenlidir ve "boş klinik" düzeltmesi buna dayanır."""
    eski, hedef = tmp_path / "eski", tmp_path / "hedef"
    _sir_yaz(eski, "DUZ-METIN-ANAHTAR")
    hedef.mkdir(parents=True)

    tasindi = path_utils._sqlcipher_anahtarini_gocur(eski, hedef)

    assert tasindi is True, "duz-metin anahtar tasinmadi → 'bos klinik' regresyonu"
    assert _hedef_anahtari(hedef) == "DUZ-METIN-ANAHTAR"


def test_COZULEBILIR_sarili_anahtar_TASINIR_karsit_kanit(tmp_path):
    """Karşı-kanıt: BU makinede gerçekten çözülebilen sarılı bir değer taşınmalı."""
    eski, hedef = tmp_path / "eski", tmp_path / "hedef"
    _sir_yaz(eski, sm._enc("GERCEK-ANAHTAR"))
    hedef.mkdir(parents=True)

    tasindi = path_utils._sqlcipher_anahtarini_gocur(eski, hedef)

    assert tasindi is True, "bu makinede cozulebilen anahtar tasinmadi → sifreli kurulumda 'bos klinik'"


def test_HEDEFTE_anahtar_VARKEN_kapi_calismaz(tmp_path):
    """Hedefte anahtar varsa zaten dokunulmaz; kapı ORADAN ÖNCE çalışırsa operatöre gereksiz
    "backend açılmazdı" korkutması loglanır (yanlış destek çağrısı)."""
    eski, hedef = tmp_path / "eski", tmp_path / "hedef"
    _sir_yaz(eski, COZULEMEZ_DPAPI)
    _sir_yaz(hedef, "HEDEFIN-KENDI-ANAHTARI")

    tasindi = path_utils._sqlcipher_anahtarini_gocur(eski, hedef)

    assert tasindi is False
    assert _hedef_anahtari(hedef) == "HEDEFIN-KENDI-ANAHTARI", "hedefin anahtari EZILDI"


def test_KRITIK_kapi_YOL_KATMANINA_dokunmaz_ozyineleme_yok(tmp_path, monkeypatch):
    """⚠️ 1.9.9/1.9.10'da BSOD'a yol açan özyinelemeyi geri getirmeme kilidi.

    `get_app_data_directory → göç → get_sqlcipher_key → secrets_manager._load → _data_dir →
    get_app_data_directory` döngüsü cihazı açılışta belleği tüketerek öldürüyordu. Kapı
    `_dec`e devreder ve `_dec` yol katmanına DOKUNMAZ; bu test çağrı sayısını ÖLÇER."""
    sayac = {"n": 0}
    gercek = path_utils.get_app_data_directory

    def _sayan(*a, **k):
        sayac["n"] += 1
        return gercek(*a, **k)

    monkeypatch.setattr(path_utils, "get_app_data_directory", _sayan)

    eski, hedef = tmp_path / "eski", tmp_path / "hedef"
    _sir_yaz(eski, COZULEMEZ_DPAPI)
    hedef.mkdir(parents=True)
    path_utils._sqlcipher_anahtarini_gocur(eski, hedef)

    assert sayac["n"] == 0, f"goc yolu get_app_data_directory'yi {sayac['n']} kez cagirdi → OZYINELEME RISKI"


# ── (2) HASTA DB'si GÖÇ ADI ─────────────────────────────────────────────────


def test_KRITIK_goc_listesi_URETIM_adini_kullanir():
    """Göç listesi üretimdeki gerçek dosya adını aramalı; aksi hâlde hasta kayıtları HİÇ taşınmaz."""
    import inspect

    from database.patient_database import PatientDatabase

    varsayilan = inspect.signature(PatientDatabase.__init__).parameters["db_file"].default
    assert varsayilan == "patients.db", "uretim adi degismis — goc listesi de guncellenmeli"
    assert varsayilan in path_utils._GOC_DOSYALARI, (
        f"goc listesi '{varsayilan}' aramiyor → 'bos klinik' duzeltmesi HASTA KAYITLARINI tasimiyor"
    )
    assert "pemf_patients.db" not in path_utils._GOC_DOSYALARI, (
        "'pemf_patients.db' YEDEK dosya on-ekidir, uretim DB adi degil"
    )


def test_KRITIK_hasta_DBsi_SIFRELI_kumesinde_de_olmali():
    """⚠️ İki satır BİRLİKTE düzeltilmeli. Yalnız `_GOC_DOSYALARI` düzeltilirse
    `ad in _GOC_SIFRELI` TUTMAZ ve şifreli hasta DB'si, hedefin anahtarıyla açılıp
    açılmayacağı KONTROL EDİLMEDEN körlemesine kopyalanır."""
    assert "patients.db" in path_utils._GOC_SIFRELI, (
        "hasta DB'si sifreli kumesinde YOK → anahtar kontrolu ATLANIR (korlemesine kopyalama)"
    )


if __name__ == "__main__":
    import os

    raise SystemExit(pytest.main([os.path.abspath(__file__), "-v"]))
