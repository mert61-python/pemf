# -*- coding: utf-8 -*-
"""Y93 · Y94 (sahip) — düz dönem yedeklerinin (`migration_backups/*.db`, `backups/*.db`) şifrelenmesi açılışı BEKLETMEZ (arka planda) ve
göç anı dışında da HER açılışta taranır; dosya tarihleri korunur, silme yok (A-08).

ÖLÇÜLEN (HEAD): `duz_metin_yedekleri_sifrele` YALNIZ göç anında ve EŞZAMANLI çağrılıyordu — açılış yedek boyutu kadar (~107 MB/sn, Y94
ölçümü) bekliyordu; DB zaten şifreliyken (göç yok) düz dönemden kalmış / önceki tarama yarıda kesilmiş yedeklere HİÇ bakılmıyordu (Y93).
Sahte EN ALT katta: SQLCipher bağlayıcısı (`sahte_sqlcipher` — gerçek bağlayıcı varsa o da) ve anahtar; göç / tarama GERÇEK.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import threading
import time
from pathlib import Path

import pytest
import sahte_sqlcipher

K = "Y93-at-rest-anahtar"
_SQLITE_BASLIK = b"SQLite format 3\x00"


@pytest.fixture(params=sahte_sqlcipher.BAGLAYICILAR)
def baglayici(request, monkeypatch):
    return sahte_sqlcipher.baglayici_kur(request.param, monkeypatch)


def _duz_db(yol: Path, ad: str) -> None:
    yol.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(yol))
    c.execute("CREATE TABLE kayit (ad TEXT)")
    c.execute("INSERT INTO kayit VALUES (?)", (ad,))
    c.commit()
    c.close()


@pytest.fixture
def kok(tmp_path, monkeypatch):
    from database import sqlcipher_util as su

    monkeypatch.setattr(su, "get_sqlcipher_key", lambda *a, **k: K)
    monkeypatch.delenv("PEMF_KEEP_PLAIN_BACKUP", raising=False)
    app = tmp_path / "PEMF_GUI"
    db = app / "pemf_treatment_history.db"
    _duz_db(db, "CanliHasta-Y93")
    yield su, app, db
    if hasattr(su, "yedek_sifrelemesini_bekle"):
        su.yedek_sifrelemesini_bekle(30)


def test_KRITIK_Y94_gocteki_yedek_sifrelemesi_ACILISI_BEKLETMEZ(baglayici, kok, monkeypatch):
    su, app, db = kok
    _duz_db(app / "backups" / "pemf_patients_20261001_000000.db", "Yedek-Y94")
    birak = threading.Event()
    calisan = {}

    def _yavas(*a, **k):
        calisan["is"] = threading.current_thread()
        birak.wait(6)
        return {"sifrelendi": [], "sifrelenemedi": []}

    monkeypatch.setattr(su, "duz_metin_yedekleri_sifrele", _yavas)
    t0 = time.monotonic()
    su.migrate_to_encrypted_if_needed(db, app, logging.getLogger("y94"))
    gecen = time.monotonic() - t0
    birak.set()
    assert db.read_bytes()[:16] != _SQLITE_BASLIK, "ön koşul: canlı DB göçmeli"
    assert gecen < 3.0, f"göç yedek şifrelemesini BEKLEDİ ({gecen:.1f} sn) — açılış bloklanıyor (Y94)"
    assert calisan.get("is") is not None and calisan["is"] is not threading.main_thread()


def test_KRITIK_Y93_zaten_SIFRELI_DB_acilisinda_duz_yedek_ARKA_PLANDA_sifrelenir_tarih_korunur(baglayici, kok):
    su, app, db = kok
    su.migrate_to_encrypted_if_needed(db, app, logging.getLogger("y93"))  # 1. açılış: göç (yedek yok)
    assert db.read_bytes()[:16] != _SQLITE_BASLIK
    if hasattr(su, "yedek_sifrelemesini_bekle"):
        su.yedek_sifrelemesini_bekle(30)
    y = app / "migration_backups" / "pre_migration_v2_20261001_000000.db"  # göç anı dışında kalmış düz kopya
    _duz_db(y, "GecKalan-Y93")
    os.utime(y, (1_700_000_000, 1_700_000_000))
    su.migrate_to_encrypted_if_needed(db, app, logging.getLogger("y93"))  # 2. açılış: DB zaten şifreli
    if hasattr(su, "yedek_sifrelemesini_bekle"):
        assert su.yedek_sifrelemesini_bekle(30)
    assert y.exists(), "yedek SİLİNDİ (A-08: silinmez)"
    assert y.read_bytes()[:16] != _SQLITE_BASLIK, "zaten şifreli kurulumda düz yedek taranmadı (Y93)"
    assert int(y.stat().st_mtime) == 1_700_000_000, "değişiklik zamanı korunmadı (rotasyon yanlış sıralar)"


def test_KARSIT_Y93_ayni_veri_kokunde_TEK_is_ve_hata_GUNLUGE(kok, monkeypatch, caplog):
    su, app, _ = kok
    birak = threading.Event()
    say = []

    def _bekle(*a, **k):
        say.append(1)
        birak.wait(5)
        raise OSError("disk dolu (aparat)")

    monkeypatch.setattr(su, "duz_metin_yedekleri_sifrele", _bekle)
    with caplog.at_level(logging.ERROR):
        t1 = su.duz_yedekleri_arka_planda_sifrele(app, "'x'", None, logging.getLogger("y93"))
        t2 = su.duz_yedekleri_arka_planda_sifrele(app, "'x'", None, logging.getLogger("y93"))
        assert t1 is t2, "aynı kökte ikinci iş başlatıldı"
        birak.set()
        assert su.yedek_sifrelemesini_bekle(10)
    assert len(say) == 1
    assert any("DUSTU" in r.getMessage() for r in caplog.records), "arka plan hatası günlüğe yazılmadı"
