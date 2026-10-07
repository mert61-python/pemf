# -*- coding: utf-8 -*-
"""Y97 (2-A O-2A.1) — karantina taşıması KOPYASIZ (D2.47 deseni).

ÖLÇÜLEN KUSUR (2-A, D2.04 mutant koşusu + D2.46 önce-ölçümü): `karantinaya_al` → `_kilit_direncli_tasi` →
`shutil.move(src, dst)`. Windows'ta açık tutamaklı dosyanın yeniden adlandırması düşünce `shutil.move` `copy2` ile
hedefe TAM bir kopya yazıp kaynağı silmeye çalışır; silme de düşer → her denemede `.acilamadi-*` KOPYASI yazılır, kaynak
yerinde kalır. Günlük "KARANTINA BASARISIZ" der ama diskte "karantinaya alınmış" görünen bir kopya durur (operatör
hangisinin gerçek veritabanı olduğunu ayıramaz).

SAHİP KARARI Y97: karantina da kopyasız taşıma kullanır — kilitli kaynakta yarım `.acilamadi-*` kopyası oluşmaz,
başarısızlık mesajı gerçeği söyler (dosya yerinde, kopya yazılmadı).

Sahte EN ALT katta: (a) GERÇEK okuyucu tutamağı (Windows: `open(..., "rb")` FILE_SHARE_DELETE vermez → yeniden
adlandırma ve silme WinError 32); (b) her platformda aynı arıza biçimi `os.rename` + `os.unlink` katmanında
(yalnız kilitli sayılan yol için) — `shutil.move`un kendisi GERÇEK koşar, `copy_function` sözleşmesi ölçülür.
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
from pathlib import Path

import pytest

_WIN = os.name == "nt"


def _ozet(yol: Path) -> str:
    return hashlib.sha256(yol.read_bytes()).hexdigest()


def _karantina(app: Path) -> list:
    return sorted(p.name for p in app.glob("*.acilamadi-*"))


def _sifreli_gibi(yol: Path, dolgu: bytes = b"\xab") -> Path:
    """SQLite başlığı taşımayan (şifreli/bozuk görünen) dosya → `duz_metin_sqlite_mi` False → karantina yolu işler."""
    yol.write_bytes(dolgu * 8192)
    return yol


@pytest.fixture
def hizli(monkeypatch):
    """24 × 0,25 sn kilit bütçesini testte bekletme (fırlatmayan yama; uyku nöbetçisi etkilenmez)."""
    monkeypatch.setattr(time, "sleep", lambda s: None)


def _os_kilidi(monkeypatch, kilitli: set) -> None:
    """Windows paylaşım ihlalinin biçimi OS katmanında: kilitli yol yeniden adlandırılamaz ve silinemez; okunabilir
    (copy2 okur ve hedefe yazar). `shutil.move` gerçek koşar."""
    gercek_rename, gercek_unlink = os.rename, os.unlink

    def _rename(src, dst, *a, **k):
        if str(src) in kilitli:
            raise PermissionError(32, "Dosya baska bir islem tarafindan kullaniliyor (taklit)", str(src))
        return gercek_rename(src, dst, *a, **k)

    def _unlink(yol, *a, **k):
        if str(yol) in kilitli:
            raise PermissionError(32, "Dosya baska bir islem tarafindan kullaniliyor (taklit)", str(yol))
        return gercek_unlink(yol, *a, **k)

    monkeypatch.setattr(os, "rename", _rename)
    monkeypatch.setattr(os, "unlink", _unlink)
    monkeypatch.setattr(os, "remove", _unlink)


def _kanit(app: Path, yol: Path, once: str, caplog) -> None:
    kopyalar = _karantina(app)
    assert kopyalar == [], (
        f"kilitli kaynakta karantina KOPYASI oluştu (Y97: kopyasız taşıma): {kopyalar}\n{caplog.text[-600:]}"
    )
    assert yol.exists() and _ozet(yol) == once, "kilitli özgün dosya DEĞİŞTİ ya da yerinde değil"
    _mesaj_gercegi_soyler(caplog, yol)
    assert "Yarim kopya kaldi" not in caplog.text, caplog.text[-800:]


def _mesaj_gercegi_soyler(caplog, yol: Path) -> None:
    """Başarısızlık KAYDI (tek satır) dosyanın YERİNDE kaldığını, kopya yazılmadığını ve hangi dosya olduğunu söyler."""
    satirlar = [r.getMessage() for r in caplog.records if "KARANTINA BASARISIZ" in r.getMessage()]
    assert any(str(yol) in m and "YERINDE" in m and "KOPYA YAZILMADI" in m for m in satirlar), (
        f"başarısızlık mesajı gerçeği söylemiyor (dosya yerinde, kopya yazılmadı): {satirlar or caplog.text[-800:]}"
    )


@pytest.mark.skipif(not _WIN, reason="okuyucu tutamaginin yeniden adlandirmayi kilitlemesi Windows'a ozgu")
def test_KRITIK_gercek_okuyucu_kilidinde_karantina_KOPYA_BIRAKMAZ(tmp_path, hizli, caplog):
    """GERÇEK açık tutamak (günlük yedeğin `copy2` okuyucusu, virüs tarayıcı …). HEAD: her denemede `copy2` hedefe tam
    kopya yazar, kaynak silinemez → `pemf_treatment_history.db.acilamadi-*` kalır. MUTASYON: `copy_function` kaldır →
    KIRMIZI."""
    from database import sqlcipher_util as su

    app = tmp_path / "PEMF_GUI"
    app.mkdir()
    yol = _sifreli_gibi(app / "pemf_treatment_history.db")
    once = _ozet(yol)
    with open(yol, "rb"):
        with caplog.at_level(logging.WARNING):
            assert su.karantinaya_al(yol, logging.getLogger("y97")) is None
    _kanit(app, yol, once, caplog)


@pytest.mark.skipif(not _WIN, reason="okuyucu tutamaginin yeniden adlandirmayi kilitlemesi Windows'a ozgu")
def test_KRITIK_gercek_kilitli_WAL_yarim_kopya_BIRAKMAZ_ana_dosya_yerinde(tmp_path, hizli, caplog):
    """Ana dosya taşınır, `-wal` kilitli → kısmi karantina geri alınır (D2.46) ve `-wal`in KOPYASI da kalmaz."""
    from database import sqlcipher_util as su

    app = tmp_path / "PEMF_GUI"
    app.mkdir()
    yol = _sifreli_gibi(app / "pemf_treatment_history.db")
    wal = _sifreli_gibi(app / "pemf_treatment_history.db-wal", b"\xcd")
    once, once_wal = _ozet(yol), _ozet(wal)
    with open(wal, "rb"):
        with caplog.at_level(logging.WARNING):
            assert su.karantinaya_al(yol, logging.getLogger("y97")) is None
    assert _karantina(app) == [], f"kısmi karantinada yarım kopya kaldı: {_karantina(app)}"
    assert _ozet(yol) == once and _ozet(wal) == once_wal, "ana DB ya da -wal yerinde/aynı değil"
    _mesaj_gercegi_soyler(caplog, wal)
    assert "GERI ALINDI" in caplog.text, caplog.text[-800:]


@pytest.mark.parametrize("kilitli_ek", ["", "-wal"])
def test_KRITIK_OS_katmaninda_kilit_karantina_KOPYA_BIRAKMAZ(tmp_path, hizli, monkeypatch, caplog, kilitli_ek):
    """Her platform (CI-Linux dahil): aynı arıza biçimi `os.rename`/`os.unlink` katmanında. `shutil.move` gerçek."""
    from database import sqlcipher_util as su

    app = tmp_path / "PEMF_GUI"
    app.mkdir()
    yol = _sifreli_gibi(app / "pemf_treatment_history.db")
    wal = _sifreli_gibi(app / "pemf_treatment_history.db-wal", b"\xcd")
    kilitli = app / f"pemf_treatment_history.db{kilitli_ek}"
    once = _ozet(kilitli)
    _os_kilidi(monkeypatch, {str(kilitli)})
    with caplog.at_level(logging.WARNING):
        assert su.karantinaya_al(yol, logging.getLogger("y97")) is None
    _kanit(app, kilitli, once, caplog)
    assert yol.exists() and wal.exists(), "kısmi karantina geri alınmadı"


def test_KARSIT_kilit_yoksa_karantina_ESKISI_GIBI_tasir(tmp_path, hizli):
    """Kopyasız kip yeniden ADLANDIRMAYI etkilemez: kilitsiz dosya (+ -wal) karantinaya taşınır, özgün içerikle."""
    from database import sqlcipher_util as su

    app = tmp_path / "PEMF_GUI"
    app.mkdir()
    yol = _sifreli_gibi(app / "pemf_treatment_history.db")
    _sifreli_gibi(app / "pemf_treatment_history.db-wal", b"\xcd")
    once = _ozet(yol)
    hedef = su.karantinaya_al(yol, logging.getLogger("y97"))
    assert hedef and Path(hedef).exists() and not yol.exists()
    assert _ozet(Path(hedef)) == once
    assert len(_karantina(app)) == 2, _karantina(app)
