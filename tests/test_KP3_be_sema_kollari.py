# -*- coding: utf-8 -*-
"""KP-3 C · `database/thdb_sema.py` + `database/treatment_history_db.py` kapsanmayan kolları — gerçek `TreatmentHistoryDB` (tmp), her test
bir DAVRANIŞ iddiası. ⚠️ Ürün kodu (VERİ GÖÇÜ / karantina) DEĞİŞMEDİ; yalnız test.

- Şema sürümü kaydı sayı değilse sürüm 0 sayılır (göç yeniden denenir; istisna yok).
- Çok eski DB'de (`patient_id` sütunu yok) seans→hasta indeksi kurulamazsa şema kurulumu DÜŞMEZ.
- Açılışta anahtar uyuşmazlığı + dosya karantinaya ALINAMIYORSA (kilitli) açık hata yükselir (boş DB sessizce kurulmaz).
- Göç: önceki geri almanın yarım kaldığı işaret varsa (kenar dosyaları listelenemese de) operatöre günlükle söylenir; göç öncesi yedek
  istisnayla alınamazsa günlüğe yazılır ve göç yine koşar; eski yedek rotasyonunda silinemeyen (açık tutamaçlı) yedek göçü düşürmez,
  silinebilenler budanır.
"""

from __future__ import annotations

import contextlib
import logging
import os
import sqlite3

import pytest
from database import thdb_sema
from database import treatment_history_db as thdb_mod
from database.treatment_history_db import TreatmentHistoryDB


@pytest.fixture
def db(tmp_path):
    d = TreatmentHistoryDB(tmp_path / "gecmis")
    yield d
    with contextlib.suppress(Exception):
        d.close()


class _SecenekliImlec:
    def __init__(self, imlec, desen):
        self._i = imlec
        self._d = desen

    def execute(self, sql, *a):
        if self._d in sql:
            raise sqlite3.OperationalError("no such column: patient_id")
        return self._i.execute(sql, *a)


def test_bozuk_surum_kaydi_sifir_sayilir(db):
    db._set_system_setting("db_schema_version", "iki", "test")
    assert db.get_schema_version() == 0


def test_eski_dbde_hasta_indeksi_kurulamazsa_sema_dusmez(db):
    with db._get_connection() as conn:
        db._create_vet_indexes(_SecenekliImlec(conn.cursor(), "idx_ts_patient_id"))
        conn.commit()


def test_karantinaya_alinamayan_db_acik_hata_yukseltir(db, monkeypatch):
    def _anahtar_reddi():
        raise RuntimeError("file is not a database")

    monkeypatch.setattr(db, "_get_connection", _anahtar_reddi)
    monkeypatch.setattr(db, "_cipher_key_cache", "eski-anahtar", raising=False)
    monkeypatch.setattr(thdb_mod, "anahtar_uyusmazligi_mi", lambda e: True)
    monkeypatch.setattr(thdb_mod, "karantinaya_al", lambda yol, logger: None)
    monkeypatch.setattr(db, "_baglantiyi_birak", lambda: None)
    with pytest.raises(RuntimeError, match="karantinaya ALINAMADI"):
        db._init_database()


def test_goc_yarim_isaret_yedek_istisnasi_ve_kilitli_eski_yedek(db, monkeypatch, caplog):
    yarim = str(db.db_path) + ".rollback.tmp"
    with open(yarim, "wb") as f:
        f.write(b"yarim")
    gercek_listdir = os.listdir

    def _listelenemez(yol="."):
        if os.path.normcase(os.path.abspath(yol)) == os.path.normcase(
            os.path.abspath(os.path.dirname(str(db.db_path)))
        ):
            raise PermissionError(13, "listelenemedi")
        return gercek_listdir(yol)

    monkeypatch.setattr(thdb_sema.os, "listdir", _listelenemez)
    yedekler = db.app_data_dir / "migration_backups"
    yedekler.mkdir(parents=True, exist_ok=True)
    eskiler = []
    for i in range(6):
        p = yedekler / f"pre_migration_v0_2026010{i}_000000.db"
        p.write_bytes(b"eski")
        os.utime(p, (1_000_000 + i, 1_000_000 + i))
        eskiler.append(p)

    def _yedek_patla(yol):
        raise OSError(28, "disk dolu")

    monkeypatch.setattr(db, "create_backup", _yedek_patla)
    db._set_system_setting("db_schema_version", "0", "test")
    with open(eskiler[0], "rb"), caplog.at_level(logging.WARNING, logger=db.logger.name):
        db._run_startup_migrations_with_rollback()
    mesajlar = " | ".join(r.getMessage() for r in caplog.records)
    assert "YARIDA kalmis olabilir" in mesajlar and "kenar dosyasi yok" in mesajlar
    assert "Migration oncesi yedek alinamadi (istisna)" in mesajlar
    assert db.get_schema_version() == db.TARGET_SCHEMA_VERSION, "yedek alınamayınca göç koşmadı"
    assert eskiler[0].exists(), "açık tutamaçlı yedek silinmiş görünüyor"
    assert not eskiler[1].exists(), "rotasyon silinebilen eski yedeği budamadı"
