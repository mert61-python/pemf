# -*- coding: utf-8 -*-
"""D2-1.3 (2-D incelemesi, A1) — KÖR KAPI: D2.51 A-45 kolu ad deseninin HARF DUYARLI olduğunu kilitlemiyor.

Windows dosya sistemi harf duyarsızdır; `yedek_dosyasi._YEDEK_ADI` harf DUYARLI tam eşleşme yapar (bugün doğru). `re.IGNORECASE` eklenirse
`Pemf_treatment_history_<damga>.db` gibi kullanıcının elle adlandırdığı geçerli bir DB "bu kurulumun yedeği" sayılıp silinir — 2-D kapısı
(test_offsite_ROTASYON_ve_yedek_KAPSAMI_D251_Y11_A32_A45.py) bu mutantta YEŞİL kalır [ÖLÇTÜM kayit/K1_mutasyon.txt a1k1_m3]. Bu kol onu kilitler.
Önerilen yer: D2.51 kapısının A-45 kolundaki `yabanci` sözlüğüne aynı dosyayı eklemek (ayrı dosya olarak da koşar).
"""

from __future__ import annotations

import os
import sqlite3
import threading
from datetime import datetime as _dt
from datetime import timedelta
from pathlib import Path


def _gecerli_duz_db(yol: Path, ad: str) -> bytes:
    c = sqlite3.connect(str(yol))
    c.execute("CREATE TABLE treatment_sessions (id INTEGER PRIMARY KEY, patient_name TEXT)")
    c.execute("INSERT INTO treatment_sessions (patient_name) VALUES (?)", (ad,))
    c.commit()
    c.close()
    return yol.read_bytes()


def test_KRITIK_A45_rotasyon_KARISIK_HARFLI_kullanici_dosyasina_dokunmaz(temp_app_data, tmp_path, monkeypatch):
    import services.headless_db_maintenance as hdm
    from database import sqlcipher_util as su
    from database.treatment_history_db import TreatmentHistoryDB
    from services.headless_db_maintenance import HeadlessDBMaintenance

    nas = tmp_path / "NAS"
    nas.mkdir()
    monkeypatch.setenv("PEMF_BACKUP_DIR", str(nas))
    yabanci = {}
    for ad in (
        "Pemf_treatment_history_20200101_000000.db",
        "pemf_treatment_history_20200101_000001.DB",
        "PEMF_TREATMENT_HISTORY_20200101_000002.DB",
    ):
        yabanci[ad] = _gecerli_duz_db(nas / ad, "KullaniciKopyasi")

    monkeypatch.delenv("PEMF_ENCRYPT_AT_REST", raising=False)
    monkeypatch.setattr(su, "get_sqlcipher_key", lambda *a, **k: "")
    monkeypatch.setattr(TreatmentHistoryDB, "_get_sqlcipher_key_legacy", lambda self: "")
    db = TreatmentHistoryDB(temp_app_data)
    try:
        db.start_session(treatment_mode="Manuel", patient_name="Pamuk")
        w = object.__new__(HeadlessDBMaintenance)
        w.app_data_dir, w.db, w.patient_db = temp_app_data, db, None
        w.backup_interval, w.backup_retention_keep = 24 * 3600, 2
        w._stop, w._thread = threading.Event(), None
        for gun in range(4):
            an = _dt(2026, 10, 1, 3) + timedelta(days=gun)

            class _Saat:
                @staticmethod
                def now(tz=None, an=an):
                    return an

            monkeypatch.setattr(hdm, "datetime", _Saat)
            w._run_backup()
    finally:
        db.close()
    adlar = set(os.listdir(nas))  # harf duyarsız FS'de gerçek adı görmek için listdir
    for ad, veri in yabanci.items():
        assert ad in adlar and (nas / ad).read_bytes() == veri, (
            f"rotasyon harf-farklı KULLANICI dosyasını sildi/değiştirdi: {ad}"
        )
