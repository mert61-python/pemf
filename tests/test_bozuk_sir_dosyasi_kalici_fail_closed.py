# Author: mertaygn, cglrgrkn
"""Bozuk `pemf_secrets.json` → tuğla-koruması İKİNCİ çağrıda ve SONRAKİ AÇILIŞTA da tutmalı.

DENETİM BULGUSU (2026-08-17). `_load()` bozulmayı görünce fail-closed davranıyor: dosyayı
`.corrupt.<zaman>` olarak kenara alıyor ve `RuntimeError` yükseltiyor — bu KASITLI ve
`tests/test_security_hardening.py::test_corrupt_secrets_file_is_not_silently_regenerated`
tarafından kilitli (commit `b58d2f2`, "[P0] fail-closed").

**Ama koruma yalnızca İLK çağrıyı kapsıyordu.** Dosya artık YOLDAN KALDIRILMIŞ olduğu için ikinci
`_load()` `p.exists()` → `False` görüp `_empty_doc()` dönüyor, hata YOK. Ardından
`get_secret("sqlcipher_key")` **YENİ bir anahtar üretip** `_save()` ile temiz bir dosya yazıyor.

Ölçülen zincir (gerçek üretim fonksiyonlarıyla):
    ADIM1: get_sqlcipher_key -> RuntimeError (brick korumasi CALISTI)
           ...ama backend_service._initialize_database_safe 'except Exception' ile YUTAR → boot sürer
    ADIM2: _resolve_supabase_credentials sessizce geçti; dosya YENİDEN YAZILDI (sqlcipher_key: '')
    ADIM3: yeni anahtar üretildi — ESKİSİYLE AYNI DEĞİL

Sonuç: `patients.db` + `pemf_treatment_history.db` karantinaya alınır, cihaz BOŞ geçmişle açılır.
Dahası `backup_recovery_code` da sıfırlanır → operatörün kasadaki kurtarma kodu geçersiz olur,
`_fingerprint` değiştiği için zarf yeni anahtarla yeniden yazılır ve `_copy_offsite` off-site zarfı
EZER → eski anahtarın off-machine escrow'u yok olur. ~14 yedek turu sonra eski şifreli yedekler
rotasyonla düşer → **tıbbi kayıt kalıcı okunamaz.**

Tetikleyici gerçek: modülün docstring'i ve `_empty_doc`'un `_comment`'i operatörü dosyayı ELLE
doldurmaya davet ediyor. Dört gerçekçi kaydetme biçimi ölçüldü, dördü de parse edilemez dosya
üretiyor (`p.read_text(encoding="utf-8")` BOM toleranslı DEĞİL):
    UTF-8 BOM (Notepad) · UTF-16 (Notepad Unicode) · ANSI/cp1254 + Türkçe · sondaki fazla virgül

⚠️ SÜREÇ-ÖMÜRLÜ BİR KİLİT YETMEZ: backend sık yeniden başlar ve yeni süreçte dosya yine YOK olur →
aynı yere düşülür. Koruma bu yüzden DİSKTE kalan kanıta (`*.corrupt.*`) bakar.

⚠️ TAZE KURULUM BOZULMAZ: dosya yok VE karantina kanıtı yok → eskisi gibi `_empty_doc()`
(karşı-kanıt testi aşağıda). Operatörün çıkış yolu da açık: karantina dosyalarını kaldırmak.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _gecerli_doc(anahtar_ham: str) -> dict:
    return {
        "_comment": "test",
        "_version": 1,
        "auto": {"sqlcipher_key": anahtar_ham},
        "operator": {},
        "embedded": {},
    }


@pytest.fixture()
def sm(tmp_path, monkeypatch):
    from utils import secrets_manager as _sm

    dosya = tmp_path / "pemf_secrets.json"
    monkeypatch.setattr(_sm, "secrets_path", lambda: dosya)
    monkeypatch.setattr(_sm, "_data_dir", lambda: tmp_path)
    monkeypatch.setattr(_sm, "_cache", None)
    yield _sm
    monkeypatch.setattr(_sm, "_cache", None)


def _boz_ve_ilk_load(sm, tmp_path):
    """Geçerli dosyayı boz, ilk `_load()`'u koştur (fail-closed + karantina)."""
    dosya = sm.secrets_path()
    dosya.write_text(json.dumps(_gecerli_doc("HAM-ANAHTAR-DEGERI")), encoding="utf-8")
    sm._cache = None
    assert sm._load()["auto"]["sqlcipher_key"] == "HAM-ANAHTAR-DEGERI", "on-kosul: gecerli dosya okunmali"

    # Notepad'in "UTF-8 BOM" kaydı — ölçülen dört gerçekçi bozulmadan biri.
    dosya.write_bytes(b"\xef\xbb\xbf" + json.dumps(_gecerli_doc("HAM-ANAHTAR-DEGERI")).encode("utf-8"))
    sm._cache = None
    with pytest.raises(RuntimeError):
        sm._load()
    assert not dosya.exists(), "on-kosul: bozuk dosya karantinaya alinmali"
    assert list(tmp_path.glob("pemf_secrets.json.corrupt.*")), "on-kosul: karantina kaniti olusmali"


def test_KRITIK_IKINCI_load_da_FAIL_CLOSED_kalir(sm, tmp_path):
    """İkinci `_load()` boş doküman DÖNMEMELİ — hata yükseltmeye devam etmeli."""
    _boz_ve_ilk_load(sm, tmp_path)

    sm._cache = None  # aynı süreçte ikinci çağrı
    with pytest.raises(RuntimeError):
        sm._load()


def test_KRITIK_SONRAKI_ACILISTA_da_FAIL_CLOSED_kalir(sm, tmp_path):
    """Süreç yeniden başlasa bile koruma tutmalı — kilit BELLEKTE olamaz.

    Yeni süreç taklidi: modül durumu tamamen sıfırlanır. Dosya diskte YOK, ama karantina kanıtı
    VAR → bu taze bir kurulum DEĞİL, sırları karantinaya alınmış bir makinedir."""
    _boz_ve_ilk_load(sm, tmp_path)

    sm._cache = None
    if hasattr(sm, "_bozuk_kanit"):  # süreç-ömürlü bir latch varsa onu da sıfırla
        sm._bozuk_kanit = None

    with pytest.raises(RuntimeError):
        sm._load()


def test_KRITIK_bozulmadan_sonra_YENI_ANAHTAR_URETILMEZ(sm, tmp_path):
    """En ağır sonuç: `get_secret` yeni bir SQLCipher anahtarı üretip dosyayı YAZMAMALI."""
    _boz_ve_ilk_load(sm, tmp_path)
    sm._cache = None

    with pytest.raises(RuntimeError):
        sm.get_secret("sqlcipher_key")

    assert not sm.secrets_path().exists(), (
        "bozulmadan sonra TEMIZ bir pemf_secrets.json yazildi → eski anahtar kayboldu, "
        "sifreli hasta verisi kalici okunamaz hale gelir"
    )


def test_KRITIK_backup_recovery_code_da_YENIDEN_URETILMEZ(sm, tmp_path):
    """Kurtarma kodu da sıfırlanmamalı: operatörün kasadaki kodu geçersiz olur ve off-site zarf ezilir."""
    _boz_ve_ilk_load(sm, tmp_path)
    sm._cache = None

    with pytest.raises(RuntimeError):
        sm.get_secret("backup_recovery_code")


def test_TAZE_KURULUM_bozulmaz_karsit_kanit(sm):
    """Karşı-kanıt: dosya YOK + karantina kanıtı YOK → eskisi gibi boş doküman (taze kurulum)."""
    doc = sm._load()
    assert isinstance(doc, dict) and "auto" in doc, "taze kurulum bozuldu"


def test_KARANTINA_KALDIRILINCA_yeniden_calisir_karsit_kanit(sm, tmp_path):
    """Karşı-kanıt: operatörün çıkış yolu AÇIK olmalı.

    "Durumu ele aldım" demek karantina dosyalarını kaldırmaktır; ondan sonra makine normal
    çalışmaya dönmeli. Aksi hâlde cihazı KALICI açılamaz yapardık — düzeltmeye çalıştığımız
    şeyden daha kötüsü."""
    _boz_ve_ilk_load(sm, tmp_path)
    for p in tmp_path.glob("pemf_secrets.json.corrupt.*"):
        p.unlink()

    sm._cache = None
    doc = sm._load()
    assert isinstance(doc, dict) and "auto" in doc, "karantina kaldirildiktan sonra hala kilitli"


def test_GECERLI_dosya_varsa_karantina_kaniti_ENGEL_OLMAZ_karsit_kanit(sm, tmp_path):
    """Karşı-kanıt: geçmişte çözülmüş bir olay bugünü bozmamalı.

    Operatör yedekten geri yükledi → `pemf_secrets.json` VAR. Yanında duran eski `.corrupt.*`
    dosyası zararsızdır ve açılışı engellememeli."""
    _boz_ve_ilk_load(sm, tmp_path)
    sm.secrets_path().write_text(json.dumps(_gecerli_doc("GERI-YUKLENEN-ANAHTAR")), encoding="utf-8")

    sm._cache = None
    assert sm._load()["auto"]["sqlcipher_key"] == "GERI-YUKLENEN-ANAHTAR"


if __name__ == "__main__":
    import os

    raise SystemExit(pytest.main([os.path.abspath(__file__), "-v"]))
