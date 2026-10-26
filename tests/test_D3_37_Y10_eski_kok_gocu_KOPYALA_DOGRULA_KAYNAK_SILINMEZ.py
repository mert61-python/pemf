# Author: mertaygn, cglrgrkn
"""D3.37 · Y10 (sahip) · S-E2I.5 — eski veri kökünden (NSSM / LocalSystem `systemprofile\\AppData\\Roaming\\PEMF_GUI`, kullanıcı `%APPDATA%`)
yeni köke (`PEMF_DATA_DIR`) OTOMATİK TAŞIMA: KOPYALA → SHA-256 ile DOĞRULA → kaynak SİLİNMEZ; doğrulama tutmazsa açılış eski veriyi
DEĞİŞTİRMEDEN durur (o DB açılmaz → kısıtlı kip, "göç bekliyor") ve uyarır.

ÖLÇÜLEN (HEAD, gerçek `_kullanicidan_makineye_gocur` + gerçek `AuthDB`, sahte eski / yeni kök):
  · yalnız `.db` kopyalanıyordu — WAL kipinde DB'ye henüz işlenmemiş kayıtlar (servis öldürülmüş / güç kesilmiş) `-wal`da kalır → yeni
    kökte o kayıtlar YOK (ölçüldü: 3 satırdan 0'ı);
  · kopya DOĞRULANMIYORDU — bozuk / kesik kopya hedefe yerleşiyor, kaynak ise "taşındı" sayılıp bir daha denenmiyordu;
  · kopyalama düşünce hedefte iz kalabiliyor, DB kurucusu o yolda BOŞ DB kurup "boş klinik" gösteriyordu.
Her senaryoda kaynak dosyaların SHA-256'sı önce / sonra AYNI (kaynak yalnız okunur). ACİL DURDUR ucu DB'siz kipte ayakta:
`tests/test_acilis_DB_acilamasa_ACIL_DURDUR_yasar.py` (GocBekliyorHatasi dahil açılış hatası sınıfı).
"""

from __future__ import annotations

import hashlib
import shutil
import sqlite3
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="göç yalnız Windows'ta koşar (path_utils)")


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


@pytest.fixture
def kokler(tmp_path, monkeypatch):
    from utils import path_utils as pu

    eski_appdata = tmp_path / "systemprofile" / "AppData" / "Roaming"
    eski = eski_appdata / "PEMF_GUI"
    eski.mkdir(parents=True)
    yeni = tmp_path / "ProgramData" / "PEMF_System" / "PEMF_GUI"
    yeni.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(eski_appdata))
    monkeypatch.setattr(pu, "_GOC_YAPILDI", set())
    monkeypatch.setattr(pu, "_GOC_ENGELI", {}, raising=False)  # HEAD ölçümünde öznitelik yok
    return pu, eski, yeni


def _wal_db(yol: Path, satir: int) -> None:
    """Servis öldürülmüş gibi: kayıtlar `-wal`da, DB'ye henüz işlenmemiş (kontrol noktası yok). Bağlantı açıkken dosyalar kopyalanır."""
    gecici = yol.parent / "_canli"
    gecici.mkdir(exist_ok=True)
    db = gecici / yol.name
    c = sqlite3.connect(db)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA wal_autocheckpoint=0")
    c.execute("CREATE TABLE t (i INTEGER)")
    c.commit()
    for i in range(satir):
        c.execute("INSERT INTO t VALUES (?)", (i,))
        c.commit()
    shutil.copyfile(db, yol)
    shutil.copyfile(str(db) + "-wal", str(yol) + "-wal")
    c.close()
    shutil.rmtree(gecici, ignore_errors=True)


def test_KRITIK_Y10_WAL_ile_TASINIR_kayitlar_KAYBOLMAZ_kaynak_DEGISMEZ(kokler):
    pu, eski, yeni = kokler
    _wal_db(eski / "auth_users.db", 3)
    once = {p.name: _sha(p) for p in eski.iterdir()}
    pu._kullanicidan_makineye_gocur(yeni)
    assert {p.name: _sha(p) for p in eski.iterdir()} == once, "KAYNAK değişti / silindi"
    assert _sha(yeni / "auth_users.db") == once["auth_users.db"]
    c = sqlite3.connect(yeni / "auth_users.db")
    try:
        assert c.execute("SELECT COUNT(*) FROM t").fetchone()[0] == 3, (
            "WAL'daki kayıtlar yeni kökte YOK (yalnız .db taşındı)"
        )
    finally:
        c.close()
    assert pu.goc_engeli(yeni / "auth_users.db") is None
    assert not list(yeni.glob("*.goc.part"))


@pytest.mark.parametrize("kip", ["bozuk_kopya", "kopya_hatasi", "yerlestirme_hatasi"])
def test_KRITIK_Y10_dogrulanamayan_kopya_YERLESMEZ_DB_ACILMAZ_kaynak_DEGISMEZ(kokler, monkeypatch, kip):
    pu, eski, yeni = kokler
    for ad in ("auth_users.db", "patients.db"):
        c = sqlite3.connect(eski / ad)
        c.execute("CREATE TABLE t (i INTEGER)")
        c.execute("INSERT INTO t VALUES (42)")
        c.commit()
        c.close()
    once = {p.name: _sha(p) for p in eski.iterdir()}
    gercek_kopya, gercek_replace = shutil.copy2, pu.os.replace
    if kip == "bozuk_kopya":

        def kesik(k, v, *a, **kw):
            gercek_kopya(k, v)
            with open(v, "r+b") as f:
                f.truncate(100)

        monkeypatch.setattr(pu.shutil, "copy2", kesik)
    elif kip == "kopya_hatasi":

        def dus(k, v, *a, **kw):
            Path(v).write_bytes(b"yarim")
            raise OSError(28, "disk dolu")

        monkeypatch.setattr(pu.shutil, "copy2", dus)
    else:

        def reddet(a, b):
            raise PermissionError(13, "salt-okur dizin")

        monkeypatch.setattr(pu.os, "replace", reddet)
    pu._kullanicidan_makineye_gocur(yeni)
    monkeypatch.setattr(pu.shutil, "copy2", gercek_kopya)
    monkeypatch.setattr(pu.os, "replace", gercek_replace)
    assert {p.name: _sha(p) for p in eski.iterdir()} == once, "KAYNAK değişti / silindi"
    assert not (yeni / "auth_users.db").exists() and not (yeni / "patients.db").exists(), "doğrulanmamış kopya yerleşti"
    assert not list(yeni.glob("*.goc.part")), "yarım kopya hedefte kaldı"
    assert pu.goc_engeli(yeni / "auth_users.db"), "göç hatası kaydedilmedi (DB açılırsa BOŞ kurulur)"
    from database.auth_db import AuthDB
    from database.sqlcipher_util import GocBekliyorHatasi

    with pytest.raises(GocBekliyorHatasi):
        AuthDB(yeni)
    assert not (yeni / "auth_users.db").exists(), "göçü doğrulanamayan yolda BOŞ DB kuruldu (boş klinik)"


def test_KARSIT_Y10_ikinci_acilis_ve_hedefte_VAR_olan_DOKUNULMAZ(kokler):
    pu, eski, yeni = kokler
    _wal_db(eski / "auth_users.db", 2)
    pu._kullanicidan_makineye_gocur(yeni)
    sonra = {p.name: _sha(p) for p in yeni.iterdir()}
    pu._GOC_YAPILDI.clear()  # yeni süreç
    pu._kullanicidan_makineye_gocur(yeni)
    assert {p.name: _sha(p) for p in yeni.iterdir()} == sonra, "ikinci açılış hedefi değiştirdi"


def test_KARSIT_Y10_engel_YOKKEN_DB_kurucusu_normal(kokler):
    pu, _, yeni = kokler
    from database.auth_db import AuthDB

    assert pu.goc_engeli(yeni / "auth_users.db") is None
    AuthDB(yeni)
    assert (yeni / "auth_users.db").exists()
