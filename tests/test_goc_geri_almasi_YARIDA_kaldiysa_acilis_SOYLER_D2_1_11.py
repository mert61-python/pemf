# -*- coding: utf-8 -*-
"""D2-1.11 (2-D incelemesi, A1) — Y100: kenara alma ile `os.replace(geçici → canlı)` ARASINDA süreç ölürse sonraki açılış checkpoint'siz son
çerçeveleri SESSİZCE yitirir.

ÖLÇÜLEN KUSUR (HEAD a76ee0d, `database/thdb_sema.py:565-575`): geri alma `-wal` / `-shm`'yi `<db>-wal.rollback-<damga>` adına alır, sonra geçici
kopyayı canlı ada taşır. İkisi arasında süreç ölürse (güç kesintisi; WAL zaten kapanış checkpoint'i DÜŞTÜĞÜ için oradadır) sonraki açılış ana
dosyayı WAL'SİZ açar, göçü yeniden koşar ve devam eder: checkpoint'siz son seanslar görünmez, günlükte kenardaki dosyalardan ve `.rollback.tmp`
artığından HİÇ söz edilmez [ÖLÇTÜM sonda: seanslar=['Y100Taban'], kenardaki WAL elle geri adlandırılınca 'K6SonCerceve' görünüyor].
DÜZELTME (S-D.5 ile uyumlu — dosyalara dokunulmaz, otomatik işlem yok): açılışta `<db>.rollback.tmp` varsa (yalnız yarıda kalan geri almanın
imzası: başarılı yolda taşınır, istisna yolunda silinir) kenardaki dosyalarla birlikte ERROR yazılır. Başarılı geri almanın bilerek bıraktığı
kenar dosyaları tek başına ERROR üretmez (karşıt).
"ÖLÜM" İSTİSNA DEĞİL: `os.replace(geçici → canlı)` çağrısı ANINDA veri dizininin anlık görüntüsü alınır (istisna yolu çalışmadan); sonraki
açılış = anlık görüntüde YENİ bir TreatmentHistoryDB örneği. Aparat 2-D'nin Y100 kapısından (gerçek checkpoint'siz WAL).
"""

from __future__ import annotations

import logging
import os
import shutil
import types
from pathlib import Path

import pytest
import test_goc_rollback_WAL_SHM_KENARA_alinir_Y100 as y100


class _Olum(BaseException):
    pass


def _goc_kur(monkeypatch, db, isaret, replace_kancasi):
    import database.thdb_sema as sema

    db._set_system_setting("db_schema_version", "2", "D2-1.11 aparat: göç zorla")

    def _goc(self):
        raise RuntimeError("D2-1.11 aparat: göç adımı düştü")

    monkeypatch.setattr(type(db), "_ensure_schema_version", _goc)
    gercek_copy2 = sema.shutil.copy2

    def _copy2(kaynak, hedef, *a, **k):
        sonuc = gercek_copy2(kaynak, hedef, *a, **k)
        if str(hedef).endswith(".rollback.tmp"):
            y100._checkpointsiz_wal_kur(Path(db.db_path), isaret)
        return sonuc

    monkeypatch.setattr(sema, "shutil", types.SimpleNamespace(**{**vars(shutil), "copy2": _copy2}))
    gercek_replace = os.replace

    def _replace(src, dst, *a, **k):
        replace_kancasi(str(src), str(dst))
        return gercek_replace(src, dst, *a, **k)

    monkeypatch.setattr(sema, "os", types.SimpleNamespace(**{**vars(os), "replace": _replace}))


def _sonraki_acilis(monkeypatch, kok: Path, caplog):
    from database import sqlcipher_util as su
    from database import treatment_history_db as thdb

    monkeypatch.delenv("PEMF_ENCRYPT_AT_REST", raising=False)
    monkeypatch.setattr(su, "get_sqlcipher_key", lambda *a, **k: "")
    monkeypatch.setattr(thdb.TreatmentHistoryDB, "_get_sqlcipher_key_legacy", lambda self: "")
    caplog.clear()
    with caplog.at_level(logging.WARNING):
        db2 = thdb.TreatmentHistoryDB(kok)
        db2.close()
    return [r for r in caplog.records if r.levelno >= logging.ERROR and ".rollback" in r.getMessage()]


def test_KRITIK_Y100_geri_alma_YARIDA_kaldiysa_sonraki_acilis_kenardaki_dosyalari_ERROR_ile_SOYLER(
    temp_app_data, tmp_path, monkeypatch, caplog
):
    db = y100._duz_db(monkeypatch, temp_app_data)
    yol = Path(db.db_path)
    goruntu = tmp_path / "olum_ani" / "PEMF_GUI"

    def _kanca(src, dst):
        if src.endswith(".rollback.tmp"):
            goruntu.mkdir(parents=True)
            for p in yol.parent.iterdir():
                if p.is_file():
                    shutil.copy2(p, goruntu / p.name)
            raise _Olum("süreç burada öldü (anlık görüntü alındı)")

    _goc_kur(monkeypatch, db, "D2111SonCerceve", _kanca)
    try:
        with pytest.raises(BaseException):
            db._run_startup_migrations_with_rollback()
    finally:
        db.close()
    monkeypatch.undo()
    assert (goruntu / (yol.name + ".rollback.tmp")).exists() and list(goruntu.glob(yol.name + "-wal.rollback-*")), (
        f"aparat: ölüm anı görüntüsü beklenen dosyaları taşımıyor: {sorted(p.name for p in goruntu.iterdir())}"
    )
    kayitlar = _sonraki_acilis(monkeypatch, goruntu, caplog)
    assert kayitlar, (
        "göç geri alması YARIDA kalmış (.rollback.tmp + kenardaki -wal) ama sonraki açılış hiçbir şey söylemedi — checkpoint'siz son "
        "seanslar sessizce görünmez oldu"
    )
    mesaj = kayitlar[0].getMessage()
    kenar_ad = sorted(goruntu.glob(yol.name + "-wal.rollback-*"))[
        0
    ].name  # GERÇEK dosya adı (mesaj şablonundaki metin değil)
    assert kenar_ad in mesaj, f"ERROR kenardaki WAL dosyasını ({kenar_ad}) adıyla söylemiyor: {mesaj[:300]}"


def test_KARSIT_BASARILI_geri_almanin_kenar_dosyalari_ERROR_uretmez_ve_temiz_acilis_sessiz(
    temp_app_data, tmp_path, monkeypatch, caplog
):
    db = y100._duz_db(monkeypatch, temp_app_data)
    yol = Path(db.db_path)
    _goc_kur(
        monkeypatch, db, "D2111Bayat", lambda s, d: None
    )  # geri alma BAŞARILI → kenar dosyaları bilerek kalır (S-D.5)
    try:
        with pytest.raises(Exception):
            db._run_startup_migrations_with_rollback()
    finally:
        db.close()
    monkeypatch.undo()
    assert (
        list(yol.parent.glob(yol.name + "-wal.rollback-*")) and not (yol.parent / (yol.name + ".rollback.tmp")).exists()
    )
    assert not _sonraki_acilis(monkeypatch, yol.parent, caplog), (
        "başarılı geri almanın kenar dosyaları her açılışta ERROR üretiyor"
    )
    temiz = tmp_path / "temiz" / "PEMF_GUI"
    temiz.mkdir(parents=True)
    assert not _sonraki_acilis(monkeypatch, temiz, caplog)
