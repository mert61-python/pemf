# -*- coding: utf-8 -*-
"""D2-1.4 (2-D incelemesi, A1) — yazım/kopya ortasında ölen süreçten kalan `<yedek adı>.yazim.tmp` / `.kopya.tmp` artıkları HİÇ temizlenmez.

ÖLÇÜLEN KUSUR (HEAD a76ee0d): `yedek_yaz` / `json_yedegi_yaz` / `duz_dbyi_yedekle` yalnız AYNI ADLI geçiciyi siler; rotasyon deseni
(`pemf_<aile>_<damga><uzantı>`) geçici adlarla eşleşmez. Damga her turda farklı olduğundan, yedek yazılırken süreç öldüğünde (güç kesintisi,
launcher'ın sert sonlandırması) kalan yarım DB kopyası yerelde ve makine dışında SÜRESİZ kalır, günlükte hiç geçmez [ÖLÇTÜM sonda: 4 farklı
damgalı turdan sonra 3 artık yerinde, günlükte 0 satır]. Her olay DB boyu kadar (2000 seansta ~58 MB) yer ve rotasyona girmeyen bir hasta kopyası.
2-D bunu makine dışı için "açık 3" olarak bildirdi; yerelde de aynı.
DÜZELTME: rotasyon, KENDİ ailelerinin geçici adlarını (`<aile adı>.yazim.tmp` / `.kopya.tmp`) 1 saatten ESKİYSE siler ve söyler; taze geçici
(süren yazım / paylaşılan hedefte komşunun kopyası) ve yabancı adlar korunur.
SAHTE EN ALT KATTA: yalnız saat (`datetime.now`); artık dosyaları gerçek yarım DB baytı + `os.utime` ile eski mtime.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import threading
import time
from datetime import datetime as _dt
from pathlib import Path

ESKI = time.time() - 3 * 3600


def _isci(app: Path, db):
    from services.headless_db_maintenance import HeadlessDBMaintenance

    w = object.__new__(HeadlessDBMaintenance)
    w.app_data_dir, w.db, w.patient_db = app, db, None
    w.backup_interval, w.backup_retention_keep = 24 * 3600, 3
    w._stop, w._thread = threading.Event(), None
    return w


def _tur(monkeypatch, w, an):
    import services.headless_db_maintenance as hdm

    class _Saat:
        @staticmethod
        def now(tz=None):
            return an

    monkeypatch.setattr(hdm, "datetime", _Saat)
    w._run_backup()


def test_KRITIK_olen_surecin_yarim_YEDEK_ARTIKLARI_yerel_ve_makine_disinda_temizlenir_ve_soylenir(
    temp_app_data, tmp_path, monkeypatch, caplog
):
    from database import sqlcipher_util as su
    from database.treatment_history_db import TreatmentHistoryDB

    nas = tmp_path / "NAS"
    nas.mkdir()
    monkeypatch.setenv("PEMF_BACKUP_DIR", str(nas))
    monkeypatch.delenv("PEMF_ENCRYPT_AT_REST", raising=False)
    monkeypatch.setattr(su, "get_sqlcipher_key", lambda *a, **k: "")
    monkeypatch.setattr(TreatmentHistoryDB, "_get_sqlcipher_key_legacy", lambda self: "")
    db = TreatmentHistoryDB(temp_app_data)
    bdir = temp_app_data / "backups"
    bdir.mkdir(exist_ok=True)
    try:
        db.start_session(treatment_mode="Manuel", patient_name="Artik")
        kaynak = bdir / "_kaynak.db"
        assert db.create_backup(str(kaynak))
        yarim = kaynak.read_bytes()[: kaynak.stat().st_size // 2]
        kaynak.unlink()
        olu = {
            bdir: [
                "pemf_treatment_history_20261001_030000.db.yazim.tmp",
                "pemf_patients_20261001_030000.db.yazim.tmp",
                "pemf_config_20261001_030000.json.yazim.tmp",
            ],
            nas: [
                "pemf_treatment_history_20261001_030000.db.kopya.tmp",
                "pemf_auth_users_20261001_030000.db.kopya.tmp",
            ],
        }
        taze = {
            bdir: "pemf_treatment_history_20261009_020000.db.yazim.tmp",
            nas: "pemf_patients_20261009_020000.db.kopya.tmp",
        }
        yabanci = {bdir: "notlar.txt.yazim.tmp", nas: "pemf_treatment_history_00_elle.db.kopya.tmp"}
        for d, adlar in olu.items():
            for a in adlar:
                (d / a).write_bytes(yarim)
                os.utime(d / a, (ESKI, ESKI))
            (d / taze[d]).write_bytes(yarim)  # süren yazım / paylaşılan hedefte komşunun kopyası: mtime ŞİMDİ
            (d / yabanci[d]).write_bytes(b"kullanici")
            os.utime(d / yabanci[d], (ESKI, ESKI))
        with caplog.at_level(logging.INFO, logger="services.headless_db_maintenance"):
            _tur(monkeypatch, _isci(temp_app_data, db), _dt(2026, 10, 9, 3, 0, 0))
        kalan = [a for d, adlar in olu.items() for a in adlar if (d / a).exists()]
        assert not kalan, (
            f"yazım/kopya ortasında ölen süreçten kalan yarım yedek artıkları farklı damgalı turda TEMİZLENMEDİ: {kalan}"
        )
        assert any("artig" in r.getMessage().lower() and "yazim.tmp" in r.getMessage() for r in caplog.records), (
            "silinen yarım yedek artığı günlükte söylenmedi"
        )
        for d in (bdir, nas):
            assert (d / taze[d]).exists(), f"TAZE geçici (süren yazım / komşunun kopyası) silindi: {d / taze[d]}"
            assert (d / yabanci[d]).exists() and (d / yabanci[d]).read_bytes() == b"kullanici", (
                f"YABANCI adlı dosyaya dokunuldu: {d / yabanci[d]}"
            )
    finally:
        db.close()
