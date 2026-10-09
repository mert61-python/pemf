# -*- coding: utf-8 -*-
"""D2-2.8 (2-D incelemesi A2 · K3) — KÖR KAPI: A-13'ün DOĞRULAMA yüzü. Legacy (D-3) anahtarla açılmış tedavi DB'sinde yedekler BİRİNCİL
anahtarla yazılır (A-13 — 2-D kapısı kilitliyor); rotasyon / tazelik doğrulaması (`thdb_bakim.yedek_acilir_mi`) da BİRİNCİL anahtarla
yapılmalı. Ürün BUGÜN doğru [ÖLÇTÜM]; kapı yoktu: doğrulamayı DB'yi AÇAN (legacy) anahtarla yapan mutant (k3_m3) D262 + D263 + D251 + D261
kapılarında `34 passed` YAŞADI. Sonuçları: legacy-açık kurulumda her yedek "AÇILAMAYAN" sayılır → rotasyon hiçbirini silmez (disk dolar),
açılış tazelik kararı None → her yeniden başlatmada yedek (D2.63 korumasının ölümü), ve S-D.4 uyarısı her turda yanlış alarm verir.

Gerçek sqlcipher3; sahte yalnız anahtar kaynağı (birincil / legacy) — D262 kapısının aparatı.
"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest
import sahte_sqlcipher

P = "D2-2-8-birincil-anahtar"
L = "D2-2-8-legacy-anahtar"


def _anahtarlar(monkeypatch, birincil, legacy=""):
    from database import sqlcipher_util as su
    from database import treatment_history_db as thdb

    monkeypatch.setenv("PEMF_ENCRYPT_AT_REST", "1")
    monkeypatch.setattr(su, "get_sqlcipher_key", lambda *a, **k: birincil)
    monkeypatch.setattr(thdb.TreatmentHistoryDB, "_get_sqlcipher_key_legacy", lambda self: legacy)
    return thdb


def test_KAPI_D2_2_8_legacy_acik_DBde_yedek_dogrulamasi_ve_tazelik_BIRINCIL_anahtarla(temp_app_data, monkeypatch):
    sahte_sqlcipher.baglayici_kur("gercek", monkeypatch)
    thdb = _anahtarlar(monkeypatch, L)
    ilk = thdb.TreatmentHistoryDB(temp_app_data)
    ilk.end_session(ilk.start_session(treatment_mode="Manuel", patient_name="D228Hasta"), duration_minutes=3)
    ilk.close()
    thdb = _anahtarlar(monkeypatch, P, legacy=L)
    db = thdb.TreatmentHistoryDB(temp_app_data)
    try:
        assert getattr(db, "_cipher_key_cache", None) == L, "ön koşul: DB LEGACY anahtarla açılmış olmalı (D-3)"
        bdir = temp_app_data / "backups"
        hedef = bdir / "pemf_treatment_history_20261009_010101.db"
        assert db.create_backup(str(hedef)) is True
        assert db.yedek_acilir_mi(hedef) is True, (
            "A-13 yedeği (birincil anahtarlı) bu kurulumun doğrulamasında AÇILAMAYAN sayıldı — doğrulama DB'yi açan (legacy) anahtarla"
        )
        from services.headless_db_maintenance import HeadlessDBMaintenance

        w = object.__new__(HeadlessDBMaintenance)
        w.app_data_dir, w.db, w.patient_db = temp_app_data, db, None
        w.backup_interval, w.backup_retention_keep = 24 * 3600, 14
        w._stop, w._thread = threading.Event(), None
        yas = w._en_yeni_gecerli_yedek_yasi()
        assert yas is not None and yas < 3600, f"taze A-13 yedeği açılış tazelik kararında görülmedi (yaş={yas})"
    finally:
        db.close()
    _ = Path
    _ = pytest
