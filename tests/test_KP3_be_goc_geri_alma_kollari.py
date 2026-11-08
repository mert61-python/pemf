# -*- coding: utf-8 -*-
"""KP-3 C · `database/thdb_sema._run_startup_migrations_with_rollback` başarısızlık kolları — gerçek `TreatmentHistoryDB` (tmp, düz),
her test bir DAVRANIŞ iddiası. ⚠️ Ürün kodu (VERİ GÖÇÜ) DEĞİŞMEDİ; yalnız test.

- Geri yüklenen yedek yerine KONAMAZ ve kenara alınan `-wal` da geri KONAMAZSA: operatöre yan dosya + kenar adıyla "ELLE geri adlandırın"
  söylenir, kenardaki WAL (canlı DB'nin son çerçeveleri) SİLİNMEZ, geçici kopya temizlenir, hata yükselir (sessiz devam yok).
- Geri alma düşer ve geçici kopya da silinemezse: uyarı yazılır, hata yine yükselir ve geçici dosya (yarım geri almanın imzası) yerinde
  kalır — bir sonraki açılışın "YARIDA kalmış olabilir" uyarısı bu imzaya dayanır.
- Göç öncesi yedek 0 bayt çıkar ve o yarım dosya silinemezse göç yine koşar (rollback güvensiz işaretlenir, akış düşmez).
- Eski yedek rotasyonu listelediği bir dosyayı okuyamazsa (listeleme ile okuma arasında silindi) rotasyon atlanır, göç düşmez.

SAHTE (en alt kat): `thdb_sema` modülünün gördüğü `os.replace` / `os.remove` / `shutil.copy2` (dosya sistemi arızası) · `Path.glob`
(listeleme ↔ okuma yarışı). GERÇEK: göç, yedek, SQLite.
"""

from __future__ import annotations

import logging
import os
import shutil
import sqlite3
import types
from pathlib import Path

import pytest


def _duz_db(monkeypatch, app: Path):
    from database import sqlcipher_util as su
    from database import treatment_history_db as thdb

    monkeypatch.delenv("PEMF_ENCRYPT_AT_REST", raising=False)
    monkeypatch.setattr(su, "get_sqlcipher_key", lambda *a, **k: "")
    monkeypatch.setattr(thdb.TreatmentHistoryDB, "_get_sqlcipher_key_legacy", lambda self: "")
    db = thdb.TreatmentHistoryDB(app)
    sid = db.start_session(treatment_mode="Manuel", patient_name="KP3Taban")
    db.end_session(sid, duration_minutes=3)
    return db


def _checkpointsiz_wal_kur(db_yolu: Path) -> bytes:
    """Ana dosya = WAL'siz taban · `-wal` = son çerçeveyi taşıyan gerçek WAL (kapanış checkpoint'i düşmüş canlı DB görüntüsü)."""
    c = sqlite3.connect(str(db_yolu))
    c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    c.close()
    taban = db_yolu.read_bytes()
    c = sqlite3.connect(str(db_yolu))
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA wal_autocheckpoint=0")
    c.execute(
        "INSERT INTO treatment_sessions (session_date, start_time, treatment_mode, patient_name, session_status) "
        "VALUES (date('now'), time('now'), 'Manuel', 'KP3SonCerceve', 'completed')"
    )
    c.commit()
    wal = Path(str(db_yolu) + "-wal").read_bytes()
    c.close()
    assert len(wal) > 32, "aparat: WAL çerçevesi yakalanamadı"
    db_yolu.write_bytes(taban)
    Path(str(db_yolu) + "-wal").write_bytes(wal)
    shm = Path(str(db_yolu) + "-shm")
    if shm.exists():
        shm.unlink()
    return wal


def _gocu_dusur(monkeypatch, db):
    db._set_system_setting("db_schema_version", "2", "KP3 aparat: göç zorla")

    def _goc(self):
        raise RuntimeError("KP3 aparat: göç adımı düştü")

    monkeypatch.setattr(type(db), "_ensure_schema_version", _goc)


def _os_sahte(monkeypatch, sema, **degisen):
    monkeypatch.setattr(sema, "os", types.SimpleNamespace(**{**vars(os), **degisen}))


def test_yerine_koyma_ve_kenar_geri_koyma_duserse_ELLE_iletisi_kenardaki_WAL_DURUR(temp_app_data, monkeypatch, caplog):
    import database.thdb_sema as sema

    db = _duz_db(monkeypatch, temp_app_data)
    yol = Path(db.db_path)
    _gocu_dusur(monkeypatch, db)
    wal_icerik = {}
    gercek_copy2 = sema.shutil.copy2

    def _copy2(kaynak, hedef, *a, **k):
        sonuc = gercek_copy2(kaynak, hedef, *a, **k)
        if str(hedef).endswith(".rollback.tmp"):
            wal_icerik["bayt"] = _checkpointsiz_wal_kur(yol)
        return sonuc

    monkeypatch.setattr(sema, "shutil", types.SimpleNamespace(**{**vars(shutil), "copy2": _copy2}))
    gercek_replace = os.replace

    def _replace(src, dst, *a, **k):
        if str(src).endswith(".rollback.tmp"):
            raise PermissionError(32, "canlı DB başka işlemce tutuluyor (aparat)")
        if ".rollback-" in str(src):
            raise PermissionError(32, "kenar dosyası geri adlandırılamadı (aparat)")
        return gercek_replace(src, dst, *a, **k)

    _os_sahte(monkeypatch, sema, replace=_replace)
    try:
        with caplog.at_level(logging.WARNING, logger=db.logger.name), pytest.raises(PermissionError):
            db._run_startup_migrations_with_rollback()
    finally:
        db.close()
    monkeypatch.undo()
    mesajlar = " | ".join(r.getMessage() for r in caplog.records)
    assert "GERI KONAMADI" in mesajlar and "ELLE" in mesajlar, mesajlar
    kenar = sorted(yol.parent.glob(yol.name + "-wal.rollback-*"))
    assert len(kenar) == 1 and kenar[0].name in mesajlar, f"kenar adı iletide yok: {kenar} · {mesajlar}"
    assert kenar[0].read_bytes() == wal_icerik["bayt"], (
        "canlı DB'nin son çerçevelerini taşıyan kenar WAL SİLİNDİ / değişti"
    )
    assert not Path(str(yol) + ".rollback.tmp").exists(), "geri alma düştü ama geçici kopya bırakıldı"
    assert yol.exists(), "canlı DB dosyası kayboldu"


def test_geri_alma_duser_ve_gecici_silinemezse_uyari_hata_yukselir_imza_kalir(temp_app_data, monkeypatch, caplog):
    import database.thdb_sema as sema

    db = _duz_db(monkeypatch, temp_app_data)
    yol = Path(db.db_path)
    gecici = Path(str(yol) + ".rollback.tmp")
    _gocu_dusur(monkeypatch, db)
    gercek_replace, gercek_remove = os.replace, os.remove

    def _replace(src, dst, *a, **k):
        if str(src).endswith(".rollback.tmp"):
            raise PermissionError(32, "canlı DB başka işlemce tutuluyor (aparat)")
        return gercek_replace(src, dst, *a, **k)

    def _remove(p, *a, **k):
        if str(p).endswith(".rollback.tmp"):
            raise PermissionError(32, "geçici kopya kilitli (aparat)")
        return gercek_remove(p, *a, **k)

    _os_sahte(monkeypatch, sema, replace=_replace, remove=_remove)
    try:
        with caplog.at_level(logging.WARNING, logger=db.logger.name), pytest.raises(PermissionError):
            db._run_startup_migrations_with_rollback()
    finally:
        db.close()
    mesajlar = " | ".join(r.getMessage() for r in caplog.records)
    assert "Migration rollback başarısız" in mesajlar
    assert "Rollback gecici dosyasi temizlenemedi" in mesajlar
    assert gecici.exists(), "silinemeyen geçici kopya (yarım geri alma imzası) yerinde değil"


def test_sifir_baytlik_yedek_silinemese_de_goc_kosar(temp_app_data, monkeypatch, caplog):
    import database.thdb_sema as sema

    db = _duz_db(monkeypatch, temp_app_data)
    db._set_system_setting("db_schema_version", "0", "KP3 aparat: göç zorla")

    def _bos_yedek(yol):
        Path(yol).write_bytes(b"")
        return True

    monkeypatch.setattr(db, "create_backup", _bos_yedek)
    gercek_remove = os.remove

    def _remove(p, *a, **k):
        if "pre_migration_" in str(p):
            raise PermissionError(32, "yarım yedek kilitli (aparat)")
        return gercek_remove(p, *a, **k)

    _os_sahte(monkeypatch, sema, remove=_remove)
    try:
        with caplog.at_level(logging.WARNING, logger=db.logger.name):
            db._run_startup_migrations_with_rollback()
        assert db.get_schema_version() == db.TARGET_SCHEMA_VERSION, "yarım yedek silinemeyince göç koşmadı"
    finally:
        db.close()
    assert "OLUSTURULAMADI" in " | ".join(r.getMessage() for r in caplog.records)


def test_rotasyon_listeledigi_yedegi_okuyamazsa_atlanir_goc_dusmez(temp_app_data, monkeypatch):
    db = _duz_db(monkeypatch, temp_app_data)
    db._set_system_setting("db_schema_version", "0", "KP3 aparat: göç zorla")
    yedekler = db.app_data_dir / "migration_backups"
    yolsinif = type(yedekler)
    gercek_glob = yolsinif.glob

    class _Kaybolan:
        def __init__(self, yol):
            self._y = yol

        def __str__(self):
            return str(self._y)

        def stat(self):
            raise FileNotFoundError(2, "listelendikten sonra silindi (aparat)", str(self._y))

    def _glob(self, desen, *a, **k):
        if desen == "pre_migration_*.db":
            return iter([_Kaybolan(self / "pre_migration_v0_20260101_000000.db")])
        return gercek_glob(self, desen, *a, **k)

    monkeypatch.setattr(yolsinif, "glob", _glob)
    try:
        db._run_startup_migrations_with_rollback()
        monkeypatch.setattr(yolsinif, "glob", gercek_glob)
        assert db.get_schema_version() == db.TARGET_SCHEMA_VERSION, "rotasyon arızası göçü düşürdü"
        assert list(yedekler.glob("pre_migration_v0_*.db")), "taze göç öncesi yedek yok"
    finally:
        db.close()
