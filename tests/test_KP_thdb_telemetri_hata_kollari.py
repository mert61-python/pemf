# -*- coding: utf-8 -*-
"""KP-1 · `database/thdb_telemetri.py` · sözleşmeler: telemetri DB yolu (sensör örnekleri, bobin koşuları, koşu özetleri, saklama, ÷5 göçü)
DB arızasında istisna SIZDIRMAZ ve güvenli varsayılana döner (0 / None / [] / {}), kaybı görünür kılar (yazılamayan örnek SAYISI günlükte) ·
boş örnek listesi DB'ye gitmez · bilinmeyen koşu bitirilmez · içe aktarma sonrası ÷5 göçü düşerse ayar "bekliyor"a çekilmeye çalışılır,
o da düşerse uyarı (açılış yeniden dener).

GERÇEK TreatmentHistoryDB (tmp). Arıza EN ALT katta ve GERÇEK biçimde: `_get_connection` `sqlite3.OperationalError("disk I/O error")` yükseltir.
"""

from __future__ import annotations

import logging
import sqlite3
import time

import pytest


@pytest.fixture
def db(tmp_path, monkeypatch):
    from database.treatment_history_db import TreatmentHistoryDB

    for ad in ("PEMF_RETAIN_PII_DAYS", "PEMF_MASK_HISTORY_PII", "PEMF_RETAIN_EVENT_DAYS", "PEMF_RETAIN_SENSOR_DAYS"):
        monkeypatch.delenv(ad, raising=False)
    d = TreatmentHistoryDB(tmp_path / "gecmis")
    try:
        yield d
    finally:
        d.close_connections()


def _dus():
    raise sqlite3.OperationalError("disk I/O error")


def test_KRITIK_DB_arizasinda_telemetri_yolu_ISTISNA_SIZDIRMAZ_guvenli_varsayilana_doner(db, monkeypatch, caplog):
    sid = db.start_session(treatment_mode="Manuel")
    run = db.start_coil_run(sid, 3, started_epoch=time.time())
    assert run, "ön koşul: sağlam DB'de koşu açılmadı"
    monkeypatch.setattr(db, "_get_connection", _dus)
    with caplog.at_level(logging.WARNING, logger=db.logger.name):
        assert db.purge_old_sensor_samples(30) == 0
        assert db.purge_old_coil_runs(30) == 0
        assert db.add_sensor_samples_batch(sid, [{"coil_id": 3, "temperature_c": 36.6}, {"coil_id": 3}]) == 0
        assert db.start_coil_run(sid, 3, started_epoch=time.time()) is None
        db.end_coil_run(run, time.time())
        db.add_sensor_run_summary(run, sample_count=2, temp_avg=36.6)
        assert db.get_session_coil_runs(sid) == []
        assert db.get_run_summaries(sid) == {}
        assert db.get_sensor_samples(sid) == []
    mesajlar = " ".join(r.getMessage() for r in caplog.records)
    assert "2 ORNEK YAZILAMADI" in mesajlar, "kayıp miktarı görünür değil (sessiz telemetri kaybı)"
    for parca in (
        "Sensor retention temizleme uyarısı",
        "Coil run baslatma hatası",
        "Coil run bitirme hatası",
        "Sensor run summary kaydetme hatası",
    ):
        assert parca in mesajlar, f"hata kolu günlüğe yazmadı: {parca}"


def test_bos_ornek_listesi_DB_ye_GITMEZ(db, monkeypatch):
    monkeypatch.setattr(db, "_get_connection", _dus)
    assert db.add_sensor_samples_batch(1, []) == 0 and db.add_sensor_samples_batch(1, None) == 0


def test_bilinmeyen_kosu_BITIRILMEZ_uyari_yazilir(db, caplog):
    with caplog.at_level(logging.WARNING, logger=db.logger.name):
        db.end_coil_run(987654, time.time())
    assert any("run_id 987654 bulunamadi" in r.getMessage() for r in caplog.records)


def test_ice_aktarma_sonrasi_bol5_gocu_DUSERSE_ayar_BEKLIYOR_o_da_duserse_uyari(db, monkeypatch, caplog):
    yazilan: list = []
    monkeypatch.setattr(db, "_set_system_setting", lambda k, v, d="": yazilan.append((k, v)))
    monkeypatch.setattr(db, "_get_connection", _dus)
    assert db._mt_bolu5_gocu(zorla=True) == -1
    assert yazilan and yazilan[-1][1] == "bekliyor", (
        "içe aktarma sonrası düşen göç 'tamam' kaldı → açılış yeniden denemez"
    )
    monkeypatch.setattr(db, "_set_system_setting", lambda *a, **k: _dus())
    with caplog.at_level(logging.WARNING, logger=db.logger.name):
        assert db._mt_bolu5_gocu(zorla=True) == -1
    assert any("'bekliyor'a cekilemedi" in r.getMessage() for r in caplog.records)
