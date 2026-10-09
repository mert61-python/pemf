# -*- coding: utf-8 -*-
"""Y100 (S2 · O-A2-3.1, 2-A incelemesi) — göç geri alınırken `-wal` / `-shm` SİLİNMEZ, kenara adlandırılır; yerine koyma düşerse
GERİ KONUR.

ÖLÇÜLEN KUSUR: `thdb_sema._run_startup_migrations_with_rollback` geri yüklenecek yedeği geçici dosyaya kopyaladıktan sonra canlı DB'nin
`-wal` / `-shm` dosyalarını `os.replace`ten ÖNCE SİLİYORDU (bayat WAL çerçeveleri geri yüklenen DB'ye uygulanmasın diye — doğru niyet).
Ardından `os.replace(geçici, canlı)` düşerse (canlı DB'yi kısa süre tutan antivirüs / yedekleme aracı tutamağı) ve kapanış checkpoint'i
de düşmüşse canlı DB son çerçevelerini (son seanslar) YİTİRİYORDU; veri yalnız göç öncesi yedekte kalıyor, Y43'ün ardışık denemelerinin
rotasyonu (son 5) o yedeği de düşürebiliyordu.

AYGIT: "kontrol noktası alınmamış WAL" dosya düzeyinde gerçek SQLite ile kurulur (ana dosya = WAL'siz taban, `-wal` = son çerçeveyi
taşıyan gerçek WAL); arıza en alt katta: `thdb_sema` modülünün gördüğü `os.replace` YALNIZ "geçici → canlı" çağrısında WinError 32
benzeri `PermissionError` verir.
"""

from __future__ import annotations

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
    sid = db.start_session(treatment_mode="Manuel", patient_name="Y100Taban")
    db.end_session(sid, duration_minutes=4)
    return db


def _checkpointsiz_wal_kur(db_yolu: Path, isaret: str) -> None:
    """Disk durumu: ana dosya = WAL'siz taban (son çerçeve YOK) · `-wal` = son çerçeveyi (isaret adlı seans) taşıyan gerçek WAL.
    Kapanış checkpoint'i düşmüş bir canlı DB'nin dosya düzeyindeki görüntüsüdür; açılınca SQLite `-wal`'ı uygular."""
    c = sqlite3.connect(str(db_yolu))
    c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    c.close()
    taban = db_yolu.read_bytes()
    c = sqlite3.connect(str(db_yolu))
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA wal_autocheckpoint=0")
    c.execute(
        "INSERT INTO treatment_sessions (session_date, start_time, treatment_mode, patient_name, session_status) "
        "VALUES (date('now'), time('now'), 'Manuel', ?, 'completed')",
        (isaret,),
    )
    c.commit()
    wal = Path(str(db_yolu) + "-wal").read_bytes()
    c.close()  # son bağlantı: SQLite checkpoint eder ve -wal'ı siler — aşağıda "checkpoint düşmüş" hâl geri kurulur
    assert len(wal) > 32, "aparat: WAL çerçevesi yakalanamadı"
    db_yolu.write_bytes(taban)
    Path(str(db_yolu) + "-wal").write_bytes(wal)
    shm = Path(str(db_yolu) + "-shm")
    if shm.exists():
        shm.unlink()


def _seans_adlari(db_yolu: Path) -> list:
    c = sqlite3.connect(str(db_yolu))
    try:
        return [r[0] for r in c.execute("SELECT patient_name FROM treatment_sessions ORDER BY id")]
    finally:
        c.close()


def _goc_dusur(monkeypatch, db, isaret: str, yerine_koyma_duser: bool):
    """Göç düşer; geri alma yedeği geçiciye kopyaladığı ANDA canlı DB'yi 'checkpoint düşmüş' hâle getir; istenirse yerine koyma
    (`geçici → canlı` os.replace) WinError 32 benzeri hatayla düşer."""
    import database.thdb_sema as sema

    db._set_system_setting("db_schema_version", "2", "Y100 aparat: göç zorla")

    def _goc(self):
        raise RuntimeError("Y100 aparat: göç adımı düştü")

    monkeypatch.setattr(type(db), "_ensure_schema_version", _goc)
    gercek_copy2 = sema.shutil.copy2

    def _copy2(kaynak, hedef, *a, **k):
        sonuc = gercek_copy2(kaynak, hedef, *a, **k)
        if str(hedef).endswith(".rollback.tmp"):
            _checkpointsiz_wal_kur(Path(db.db_path), isaret)
        return sonuc

    monkeypatch.setattr(sema, "shutil", types.SimpleNamespace(**{**vars(shutil), "copy2": _copy2}))
    gercek_replace = os.replace
    cagrilar = []

    def _replace(src, dst, *a, **k):
        cagrilar.append((os.path.basename(str(src)), os.path.basename(str(dst))))
        if yerine_koyma_duser and str(src).endswith(".rollback.tmp"):
            raise PermissionError(
                32, "Dosya başka bir işlem tarafından kullanıldığından işlem dosyaya erişemiyor (aparat)"
            )
        return gercek_replace(src, dst, *a, **k)

    monkeypatch.setattr(sema, "os", types.SimpleNamespace(**{**vars(os), "replace": _replace}))
    with pytest.raises(Exception):
        db._run_startup_migrations_with_rollback()
    return cagrilar


def test_KRITIK_Y100_yerine_koyma_DUSERSE_checkpointsiz_WAL_GERI_konur_son_cerceveler_KAYBOLMAZ(
    temp_app_data, monkeypatch
):
    db = _duz_db(monkeypatch, temp_app_data)
    yol = Path(db.db_path)
    try:
        _goc_dusur(monkeypatch, db, "Y100SonCerceve", yerine_koyma_duser=True)
    finally:
        db.close()
    monkeypatch.undo()
    assert Path(str(yol) + "-wal").exists(), (
        "yerine koyma düştü ama canlı DB'nin -wal dosyası YOK — geri alma onu yerine koymadan önce silmiş/kenarda bırakmış"
    )
    adlar = _seans_adlari(yol)
    assert "Y100SonCerceve" in adlar, (
        f"canlı DB checkpoint edilmemiş SON ÇERÇEVELERİNİ yitirdi (geri alma -wal'ı sildi, yerine koyma düştü): {adlar}"
    )


def test_KRITIK_Y100_yerine_koyma_BASARILIYSA_bayat_WAL_SILINMEZ_kenarda_durur_ve_geri_yuklenen_DBye_UYGULANMAZ(
    temp_app_data, monkeypatch
):
    db = _duz_db(monkeypatch, temp_app_data)
    yol = Path(db.db_path)
    try:
        _goc_dusur(monkeypatch, db, "Y100BayatCerceve", yerine_koyma_duser=False)
    finally:
        db.close()
    monkeypatch.undo()
    kenar = sorted(p.name for p in yol.parent.glob(yol.name + "-wal.*"))
    assert kenar, (
        "Y100: geri alma bayat -wal'ı SİLDİ — kenara adlandırılmalıydı (göç öncesi son çerçeveler orada; silinirse geri dönüş yok)"
    )
    assert not Path(str(yol) + "-wal").exists() or Path(str(yol) + "-wal").stat().st_size == 0, (
        "bayat -wal canlı adla duruyor — geri yüklenen DB'ye UYGULANIR (şema / veri karışır)"
    )
    adlar = _seans_adlari(yol)
    assert adlar == ["Y100Taban"], f"geri yüklenen DB yedekle aynı olmalı (bayat çerçeve uygulanmadan): {adlar}"
