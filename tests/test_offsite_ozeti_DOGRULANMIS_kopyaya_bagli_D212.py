# -*- coding: utf-8 -*-
"""D2.12 (B-3.19) — makine dışı (off-site) yedek özetindeki "geri yüklenebilir" güvencesi DOĞRULANMIŞ kopyaya bağlı.

ÖLÇÜLEN KUSUR (DENETIM-03 B-3.19, 2-D'de yeniden ölçüldü): `_copy_offsite` her dosyayı `shutil.copy2` ile doğrudan son ada kopyalıyor,
hatayı WARNING ile geçip özetinde YALNIZ `(hedef / kurtarma-zarfi.enc).exists()`e bakıyordu: hedef doldu / ağ koptu → .db kopyası
YARIM kalıyor, günlük yine INFO "kopyalandi … KURTARMA KODU ile baska makinede geri yuklenebilir" diyordu. Felaket günü yarım dosya
seçilir.
DÜZELTME: her dosya geçici ada kopyalanır, boyut + SHA-256 kaynakla eşitse son ada taşınır; aksi hâlde geçici silinir (önceki sağlam
kopyalara dokunulmaz). "Geri yüklenebilir" INFO'su yalnız TÜM dosyalar ve zarf doğrulanınca; aksi hâlde ERROR + başarısız sayı.
SAHTE EN ALT KATTA, GERÇEK BİÇİMİYLE: `shutil.copy2` hedefe yarısını YAZAR, sonra `OSError(28, disk dolu)`.
"""

from __future__ import annotations

import logging
import os
import shutil
import threading
from pathlib import Path

import pytest

ZARF = "kurtarma-zarfi.enc"


@pytest.fixture
def o(temp_app_data, tmp_path, monkeypatch):
    from database import sqlcipher_util as su
    from database.treatment_history_db import TreatmentHistoryDB
    from services.headless_db_maintenance import HeadlessDBMaintenance

    monkeypatch.delenv("PEMF_ENCRYPT_AT_REST", raising=False)
    monkeypatch.setattr(su, "get_sqlcipher_key", lambda *a, **k: "")
    monkeypatch.setattr(TreatmentHistoryDB, "_get_sqlcipher_key_legacy", lambda self: "")
    tdb = TreatmentHistoryDB(temp_app_data)
    tdb.start_session(treatment_mode="Manuel", patient_name="D212Hasta")
    nas = tmp_path / "NAS"
    monkeypatch.setenv("PEMF_BACKUP_DIR", str(nas))
    w = object.__new__(HeadlessDBMaintenance)
    w.app_data_dir, w.db, w.patient_db = temp_app_data, tdb, None
    w.backup_interval, w.backup_retention_keep = 24 * 3600, 14
    w._stop, w._thread = threading.Event(), None
    bdir = temp_app_data / "backups"
    bdir.mkdir(exist_ok=True)
    yedek = bdir / "pemf_treatment_history_20261009_080000.db"
    assert tdb.create_backup(str(yedek))
    zarf = bdir / ZARF
    zarf.write_bytes(b'{"tur": "kurtarma-zarfi", "v": 1, "aparat": "D212"}')
    try:
        yield type("O", (), {"w": w, "tdb": tdb, "nas": nas, "yedek": yedek, "zarf": zarf})
    finally:
        tdb.close()


def _yarim_kopya(monkeypatch):
    gercek = shutil.copy2

    def _copy2(kaynak, hedef, *a, **k):
        if str(kaynak).endswith(".db"):
            veri = Path(kaynak).read_bytes()
            with open(hedef, "wb") as f:
                f.write(veri[: len(veri) // 2])  # hedef doldu: yarısı yazıldı
            raise OSError(28, "No space left on device (aparat)")
        return gercek(kaynak, hedef, *a, **k)

    monkeypatch.setattr(shutil, "copy2", _copy2)  # `_copy_offsite` shutil'i işlev içinde içe aktarır → modül özniteliği


def test_KRITIK_D212_db_kopyasi_YARIM_kalinca_geri_yuklenebilir_DENMEZ_ozet_ERROR_ve_sayi(o, monkeypatch, caplog):
    _yarim_kopya(monkeypatch)
    with caplog.at_level(logging.INFO, logger="services.headless_db_maintenance"):
        o.w._copy_offsite([o.yedek, o.zarf])
    mesajlar = [(r.levelno, r.getMessage()) for r in caplog.records if r.name == "services.headless_db_maintenance"]
    assert not any(lv == logging.INFO and "geri yuklenebilir" in m for lv, m in mesajlar), (
        "off-site .db kopyası YARIM kaldı ama özet 'geri yuklenebilir' (INFO) dedi — felaket günü yarım dosya seçilir"
    )
    hatalar = [m for lv, m in mesajlar if lv >= logging.ERROR]
    assert hatalar and any("1" in m for m in hatalar), f"özet ERROR + başarısız dosya sayısı vermedi: {mesajlar}"
    kalan = sorted(p.name for p in o.nas.iterdir())
    assert o.yedek.name not in kalan, f"YARIM kopya son adla duruyor: {kalan}"
    assert not [k for k in kalan if k.endswith(".tmp")], f"geçici kopya artığı kaldı: {kalan}"


def test_KRITIK_D212_yarim_kopya_ONCEKI_saglam_off_site_kopyaya_DOKUNMAZ(o, monkeypatch):
    o.nas.mkdir(parents=True, exist_ok=True)
    onceki = o.nas / o.yedek.name
    shutil.copy2(o.yedek, onceki)
    ozet = onceki.read_bytes()
    _yarim_kopya(monkeypatch)
    o.w._copy_offsite([o.yedek])
    assert onceki.read_bytes() == ozet, "başarısız kopya ÖNCEKİ sağlam off-site kopyanın üzerine YARIM yazdı"


def test_KARSIT_D212_saglam_kopyada_ozet_INFO_geri_yuklenebilir_ve_dosyalar_ESIT(o, caplog):
    with caplog.at_level(logging.INFO, logger="services.headless_db_maintenance"):
        o.w._copy_offsite([o.yedek, o.zarf])
    assert any(r.levelno == logging.INFO and "geri yuklenebilir" in r.getMessage() for r in caplog.records)
    for p in (o.yedek, o.zarf):
        assert (o.nas / p.name).read_bytes() == p.read_bytes()
    assert not [p for p in o.nas.iterdir() if p.name.endswith(".tmp")]
    assert os.path.exists(o.nas / "OKU-KURTARMA.txt")


def test_KRITIK_D212_kopya_SESSIZCE_eksik_yazilirsa_ozet_dogrulamasi_YAKALAR(o, monkeypatch, caplog):
    """Hedef (ağ sürücüsü / USB) hata vermeden eksik yazarsa: yalnız boyut + SHA-256 doğrulaması yakalar."""
    gercek = shutil.copy2

    def _sessiz_eksik(kaynak, hedef, *a, **k):
        if str(kaynak).endswith(".db"):
            veri = Path(kaynak).read_bytes()
            with open(hedef, "wb") as f:
                f.write(veri[:-512])
            return hedef
        return gercek(kaynak, hedef, *a, **k)

    monkeypatch.setattr(shutil, "copy2", _sessiz_eksik)
    with caplog.at_level(logging.INFO, logger="services.headless_db_maintenance"):
        o.w._copy_offsite([o.yedek, o.zarf])
    assert not any(r.levelno == logging.INFO and "geri yuklenebilir" in r.getMessage() for r in caplog.records)
    assert any(r.levelno >= logging.ERROR for r in caplog.records)
    assert o.yedek.name not in {p.name for p in o.nas.iterdir()}, "eksik yazılmış kopya son adla kaldı"


# D2-3.7 (2-D incelemesi): SHA-256 kolu — tam boyutta bozuk kopya (boyut denetimi tek başına yakalamaz; mutant "yalnız boyut" bu kolla KIRMIZI).
def test_KRITIK_D212_ayni_BOYUTTA_bozuk_kopya_geri_yuklenebilir_DENMEZ_ve_son_adla_KALMAZ(o, monkeypatch, caplog):
    gercek = shutil.copy2

    def _copy2(kaynak, hedef, *a, **k):
        if str(kaynak).endswith(".db"):
            veri = bytearray(Path(kaynak).read_bytes())
            veri[len(veri) // 2] ^= 0xFF  # tam boyut, tek bayt bozuk, hata YOK
            Path(hedef).write_bytes(bytes(veri))
            return str(hedef)
        return gercek(kaynak, hedef, *a, **k)

    monkeypatch.setattr(shutil, "copy2", _copy2)
    with caplog.at_level(logging.INFO, logger="services.headless_db_maintenance"):
        o.w._copy_offsite([o.yedek, o.zarf])
    k = [(r.levelno, r.getMessage()) for r in caplog.records if r.name == "services.headless_db_maintenance"]
    assert not any(lv == logging.INFO and "geri yuklenebilir" in m for lv, m in k), (
        "aynı boyutta BOZUK .db kopyası için 'geri yuklenebilir' (INFO) denildi — SHA-256 doğrulaması çalışmıyor"
    )
    assert any(lv >= logging.ERROR for lv, _ in k), k
    assert o.yedek.name not in {p.name for p in o.nas.iterdir()}, "bozuk kopya son adla duruyor"
