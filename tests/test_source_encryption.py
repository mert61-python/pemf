# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""KAYNAK ŞİFRELEME + RUNTIME ÇÖZME (2026-08-06, sahip isteği).

Sınanan sözleşme:
  * Şifreli dosya düz kaynağı İÇERMEZ (gerçekten şifreli, kodlanmış değil).
  * Yanlış parola çözemez ve SESSİZ KALMAZ.
  * Şifrelenmiş modül runtime'da import EDİLEBİLİR ve diske düz kaynak YAZILMAZ.
  * Şifresiz build'de yükleyici hiçbir şey bozmaz (geliştirme ortamı etkilenmez).
"""

import os
import sys

os.environ.pop("PEMF_SIMULATE", None)

import pytest

from build_tools import source_crypto as sc

PW = "test-parola-123"
KAYNAK = b"DEGER = 42\n\ndef topla(a, b):\n    return a + b\n"


# ── kripto katmanı ──────────────────────────────────────────────────────────
def test_sifreli_cikti_duz_kaynagi_ICERMEZ():
    blob = sc.encrypt_bytes(KAYNAK, PW)
    assert b"DEGER = 42" not in blob
    assert b"def topla" not in blob
    assert blob.startswith(sc.MAGIC)


def test_cozme_orijinali_AYNEN_dondurur():
    assert sc.decrypt_bytes(sc.encrypt_bytes(KAYNAK, PW), PW) == KAYNAK


def test_YANLIS_parola_cozemez():
    blob = sc.encrypt_bytes(KAYNAK, PW)
    with pytest.raises(Exception):
        sc.decrypt_bytes(blob, "baska-parola")


def test_sifreli_OLMAYAN_dosya_net_hata_verir():
    with pytest.raises(ValueError, match="imza"):
        sc.decrypt_bytes(b"bu duz metin", PW)


def test_ayni_parola_ayni_anahtari_uretir():
    """Build makinesi ile saha makinesi aynı anahtarı türetmeli (sabit tuz kasıtlı)."""
    assert sc.derive_key(PW) == sc.derive_key(PW)
    assert sc.derive_key(PW) != sc.derive_key(PW + "x")


def test_bos_parola_reddedilir():
    with pytest.raises(ValueError):
        sc.derive_key("")


# ── runtime yükleyici: UÇTAN UCA ────────────────────────────────────────────
def test_sifrelenmis_modul_IMPORT_EDILEBILIR_ve_diske_duz_kaynak_YAZILMAZ(tmp_path, monkeypatch):
    from utils import encrypted_import as ei

    mod = tmp_path / "gizli_modul.py"
    mod.write_bytes(KAYNAK)
    # Şifrele + düz kaynağı SİL (build adımının yaptığı şey)
    (tmp_path / "gizli_modul.pyenc").write_bytes(sc.encrypt_bytes(KAYNAK, PW))
    mod.unlink()
    assert not mod.exists()

    monkeypatch.setenv("PEMF_SOURCE_KEY", PW)
    monkeypatch.syspath_prepend(str(tmp_path))
    finder = ei.EncryptedFinder(PW)
    # İZOLASYON: başka bir test modülü `install()` çağırmış olabilir (parola dosyası varken
    # gerçekten kurulur) → ÜRETİM parolalı bir bulucu meta_path'te durur ve bizim TEST
    # parolamızla şifrelenmiş dosyayı çözemeyip ImportError atar. Kendi bulucumuzu ÖNE koy.
    sys.meta_path.insert(0, finder)
    try:
        sys.modules.pop("gizli_modul", None)
        import gizli_modul  # type: ignore

        assert gizli_modul.DEGER == 42
        assert gizli_modul.topla(2, 3) == 5
    finally:
        sys.meta_path.remove(finder)
        sys.modules.pop("gizli_modul", None)

    # Çözülen kaynak DİSKE yazılmamalı — şifrelemenin tek faydası bu.
    assert not mod.exists()
    assert list(tmp_path.glob("*.py")) == []


def test_yanlis_parolayla_import_SESSIZ_KALMAZ(tmp_path, monkeypatch):
    from utils import encrypted_import as ei

    (tmp_path / "bozuk_modul.pyenc").write_bytes(sc.encrypt_bytes(KAYNAK, PW))
    monkeypatch.syspath_prepend(str(tmp_path))
    finder = ei.EncryptedFinder("yanlis-parola")
    sys.meta_path.append(finder)
    try:
        sys.modules.pop("bozuk_modul", None)
        with pytest.raises(ImportError, match="çözülemedi"):
            import bozuk_modul  # type: ignore  # noqa: F401
    finally:
        sys.meta_path.remove(finder)
        sys.modules.pop("bozuk_modul", None)


def test_DUZ_py_varsa_o_kullanilir_gelistirme_ortami_BOZULMAZ(tmp_path, monkeypatch):
    """Yükleyici meta_path SONUNDA durur → düz kaynak varken devreye girmez."""
    from utils import encrypted_import as ei

    (tmp_path / "ikili_modul.py").write_bytes(b"KAYNAK = 'duz'\n")
    (tmp_path / "ikili_modul.pyenc").write_bytes(sc.encrypt_bytes(b"KAYNAK = 'sifreli'\n", PW))
    monkeypatch.syspath_prepend(str(tmp_path))
    finder = ei.EncryptedFinder(PW)
    sys.meta_path.append(finder)  # SONA
    try:
        sys.modules.pop("ikili_modul", None)
        import ikili_modul  # type: ignore

        assert ikili_modul.KAYNAK == "duz", "şifreli sürüm düz kaynağı EZDİ (geliştirme bozulur)"
    finally:
        sys.meta_path.remove(finder)
        sys.modules.pop("ikili_modul", None)


def test_parola_yokken_yukleyici_SESSIZCE_devre_disi(monkeypatch):
    """Şifresiz build'lerde (geliştirme/test) hiçbir şey bozulmamalı."""
    from utils import encrypted_import as ei

    monkeypatch.delenv("PEMF_SOURCE_KEY", raising=False)
    monkeypatch.setattr(ei, "_password", lambda: "")
    monkeypatch.setattr(ei, "_installed", False)
    assert ei.install() is False


# ── build betiği güvenlik kapısı ────────────────────────────────────────────
def test_build_betigi_KAYNAK_AGACINI_sifrelemeyi_REDDEDER(tmp_path, monkeypatch, capsys):
    """En tehlikeli kaza: geliştirme ağacını şifrelemek. Yol 'dist' içermiyorsa DURMALI."""
    from build_tools import encrypt_sources as es

    kaynak_gibi = tmp_path / "guii" / "ai_hub"
    kaynak_gibi.mkdir(parents=True)
    monkeypatch.setattr(sys, "argv", ["encrypt_sources.py", "--dist", str(tmp_path / "guii")])
    assert es.main() == 2
    assert "dist" in capsys.readouterr().out.lower()
