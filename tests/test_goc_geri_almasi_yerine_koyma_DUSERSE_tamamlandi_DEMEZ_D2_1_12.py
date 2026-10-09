# -*- coding: utf-8 -*-
"""D2-1.12 (2-D incelemesi, A1) — KÖR KAPI: Y100 kapısı "yerine koyma düşerse" kolunda yalnız WAL'in geri konmasını ölçer; hatanın YUKARI
taşındığını (günlüğün gerçeği söylediğini, geçici kopyanın temizlendiğini) ölçmez.

`thdb_sema._run_startup_migrations_with_rollback`'te yan dosyaları geri koyduktan sonraki `raise` kaldırılırsa (iç `except` hatayı yutar) WAL yine
geri konur — 2-D kapıları YEŞİL kalır [ÖLÇTÜM kayit/K6_mutasyon.txt a1k6_m1: 10 passed] — ama günlük "Rollback: canli DB'nin yan dosyalari …
kenara alindi" ve "Migration rollback tamamlandı" der (canlı DB DEĞİŞMEDİ, yarım göçlü hâlde duruyor) ve `<db>.rollback.tmp` (DB boyu kopya)
diskte kalır. Bu kol ikisini de kilitler. Aparat 2-D'nin Y100 kapısından (gerçek checkpoint'siz WAL; `os.replace` yalnız "geçici → canlı"da
WinError 32 benzeri PermissionError).
"""

from __future__ import annotations

import logging
from pathlib import Path

import test_goc_rollback_WAL_SHM_KENARA_alinir_Y100 as y100


def test_KRITIK_Y100_yerine_koyma_DUSERSE_gunluk_tamamlandi_DEMEZ_gecici_kopya_KALMAZ(
    temp_app_data, monkeypatch, caplog
):
    db = y100._duz_db(monkeypatch, temp_app_data)
    yol = Path(db.db_path)
    try:
        with caplog.at_level(logging.INFO):
            y100._goc_dusur(monkeypatch, db, "D2112SonCerceve", yerine_koyma_duser=True)
    finally:
        db.close()
    monkeypatch.undo()
    yalan = [r.getMessage()[:120] for r in caplog.records if "rollback tamamland" in r.getMessage().lower()]
    assert not yalan, (
        f"yerine koyma DÜŞTÜ (canlı DB değişmedi) ama günlük geri almanın TAMAMLANDIĞINI söylüyor: {yalan}"
    )
    assert not (yol.parent / (yol.name + ".rollback.tmp")).exists(), (
        "yerine koyma düştü, DB boyu geçici kopya diskte KALDI"
    )
    assert any(r.levelno >= logging.ERROR and "rollback" in r.getMessage().lower() for r in caplog.records), (
        "geri almanın başarısızlığı ERROR ile söylenmedi"
    )
