# -*- coding: utf-8 -*-
"""2-E incelemesi S-E2I.4'ün KALAN yarısı — makine dışı yedek hedefi (`PEMF_BACKUP_DIR`) PEMF veri kökünün İÇİNDE olamaz.

S-E2I.4 (a) [ÖNERİLEN UYGULANDI, `bcf9876`] kaldırma raporunu doğru söyletti; silme kapsamı DEĞİŞMEDİ (geri döndürülemez yön). Kalan yarı:
hedef doğrulaması. ÖLÇÜLEN KUSUR: `_copy_offsite` hedefi hiç denetlemiyordu — `PEMF_BACKUP_DIR` veri kökünün altındaki bir klasörü gösterince
"makine dışı" kopya AYNI diske ve kaldırma / tam temizliğin sileceği köke yazılıyor, günlük "off-machine kopyalandi ve DOGRULANDI …
baska makinede geri yuklenebilir" diyordu (yanlış güvence: disk arızasında ya da kaldırmada yedekle birlikte gider).
Düzeltme: hedef veri kökünün içindeyse kopya YAPILMAZ, ERROR (neden + çare). Başlatıcı (Rust) yarısı: cargo bu oturumda yasak → devreden.
GERÇEK: HeadlessDBMaintenance `_copy_offsite`, gerçek tedavi DB yedeği (D2.12 aparatı).
"""

from __future__ import annotations

import logging
import threading

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
    tdb.start_session(treatment_mode="Manuel", patient_name="SE2I4Hasta")
    w = object.__new__(HeadlessDBMaintenance)
    w.app_data_dir, w.db, w.patient_db = temp_app_data, tdb, None
    w.backup_interval, w.backup_retention_keep = 24 * 3600, 14
    w._stop, w._thread = threading.Event(), None
    bdir = temp_app_data / "backups"
    bdir.mkdir(exist_ok=True)
    yedek = bdir / "pemf_treatment_history_20261010_080000.db"
    assert tdb.create_backup(str(yedek))
    zarf = bdir / ZARF
    zarf.write_bytes(b'{"tur": "kurtarma-zarfi", "v": 1, "aparat": "SE2I4"}')
    try:
        yield type("O", (), {"w": w, "kok": temp_app_data, "dosyalar": [str(yedek), str(zarf)], "tmp": tmp_path})
    finally:
        tdb.close()


def test_KRITIK_SE2I4_hedef_PEMF_KOKU_ALTINDAYSA_kopya_YAPILMAZ_ERROR(o, monkeypatch, caplog):
    """MUTASYON: kök denetimi kaldırılır → KIRMIZI."""
    hedef = o.kok / "harici_yedek"
    monkeypatch.setenv("PEMF_BACKUP_DIR", str(hedef))
    with caplog.at_level(logging.INFO, logger="services.headless_db_maintenance"):
        o.w._copy_offsite(o.dosyalar)
    kopyalanan = sorted(p.name for p in hedef.glob("*")) if hedef.exists() else []
    assert not kopyalanan, f"veri kökünün İÇİNDEKİ 'makine dışı' hedefe kopyalandı: {kopyalanan}"
    hatalar = [r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR]
    assert any("veri koku" in m and "olamaz" in m for m in hatalar), f"neden + çare ERROR olarak yazılmadı: {hatalar}"
    assert not any("geri yuklenebilir" in r.getMessage() for r in caplog.records), (
        "yanlış güvence (INFO 'geri yuklenebilir') verildi"
    )


def test_KRITIK_SE2I4_goreli_ve_buyuk_kucuk_harf_dolambaci_da_REDDEDILIR(o, monkeypatch):
    """`..` / büyük-küçük harf farkıyla yazılmış ama veri kökünün içine çözülen hedef de reddedilir (Windows yolu harf duyarsız)."""
    import os

    hedef = o.kok / "alt" / ".." / "Harici2"
    yol = str(hedef)
    if os.name == "nt":
        yol = yol.upper()
    monkeypatch.setenv("PEMF_BACKUP_DIR", yol)
    o.w._copy_offsite(o.dosyalar)
    gercek = o.kok / "Harici2"
    assert not (gercek.exists() and any(gercek.iterdir())), "dolambaçlı yazılmış kök-içi hedefe kopyalandı"


def test_KARSIT_kok_DISI_hedefe_kopyalanir(o, monkeypatch):
    hedef = o.tmp / "USB_YEDEK"
    monkeypatch.setenv("PEMF_BACKUP_DIR", str(hedef))
    o.w._copy_offsite(o.dosyalar)
    assert (hedef / ZARF).exists() and any(p.suffix == ".db" for p in hedef.iterdir())
