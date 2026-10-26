# -*- coding: utf-8 -*-
"""D3 devri → D5 · sağlamlık listesi "`backup()` BUSY'de zaman aşımsız" (2-D kapanışı · D2C incelemesi §9).

CPython / sqlcipher3 `Connection.backup` kaynak kilitliyken (SQLITE_BUSY / SQLITE_LOCKED) adımı 250 ms uyuyup SONSUZA DEK yeniler;
bağlantının `timeout`u yalnız TEK adımın bekleyişini sınırlar. Kaynak DB DELETE kipindeyken (tedavi DB'sinin WAL kurulamayınca düştüğü
kip) ya da başka bir süreç `locking_mode=EXCLUSIVE` ile tutarken yedek çağrısı kilit bırakılana dek DÖNMÜYORDU [ÖLÇTÜM D5 sondası:
`timeout=2` ile 14 sn sonunda hâlâ asılı]. Sınır: `yedek_dosyasi.YEDEK_KILIT_SURESI_SN` — dolunca yedek istisnayla iptal edilir, son ad
oluşmaz, geçici dosya kalmaz; kilit sınırdan ÖNCE bırakılırsa yedek yine alınır (bekleme kaldırılmadı, yalnız sınırlandı).

Kilit EN ALT katta kurulur: ikinci bir GERÇEK SQLite bağlantısı `BEGIN EXCLUSIVE` + yazım tutar (DELETE kipinde okuyucuyu da engeller)."""

from __future__ import annotations

import logging
import os
import sqlite3
import threading
import time

import pytest
from database import yedek_dosyasi as yd

_log = logging.getLogger("test_yedek_kilit")
_ASILI_SINIR_SN = 20.0


def _kaynak(tmp_path):
    yol = str(tmp_path / "kaynak.db")
    c = sqlite3.connect(yol)
    c.execute("PRAGMA journal_mode=DELETE")
    c.execute("CREATE TABLE t(x)")
    c.executemany("INSERT INTO t VALUES (?)", [(i,) for i in range(300)])
    c.commit()
    c.close()
    return yol


def _kilitle(yol):
    k = sqlite3.connect(yol, timeout=1, isolation_level=None, check_same_thread=False)
    k.execute("BEGIN EXCLUSIVE")
    k.execute("INSERT INTO t VALUES (-1)")
    return k


def _birak(k):
    try:
        k.execute("ROLLBACK")
    finally:
        k.close()


def _kostur(is_):
    """`is_`i iş parçacığında koşar; (bitti_mi, sonuç) döndürür. Asılı kalırsa çağıran kilidi bırakınca iş parçacığı biter."""
    sonuc = {}

    def sar():
        t0 = time.monotonic()
        try:
            is_()
            sonuc["r"] = "TAMAM"
        except Exception as e:  # noqa: BLE001 — sonuç olarak ölçülür
            sonuc["r"] = e
        sonuc["sure"] = time.monotonic() - t0

    th = threading.Thread(target=sar, daemon=True)
    th.start()
    th.join(_ASILI_SINIR_SN)
    return th, sonuc


@pytest.fixture
def kisa_sinir(monkeypatch):
    # raising=False: sınır sabiti yokken (düzeltme öncesi) test ASILI ölçümüyle kırmızı olur, AttributeError ile değil.
    monkeypatch.setattr(yd, "YEDEK_KILIT_SURESI_SN", 1.0, raising=False)
    monkeypatch.setattr(yd, "KAYNAK_BUSY_SN", 0.3, raising=False)


def _dogrula_iptal(th, sonuc, kilit, hedef):
    asili = th.is_alive()
    _birak(kilit)
    th.join(30)
    assert not asili, f"kaynak kilitliyken yedek {_ASILI_SINIR_SN:.0f} sn sonunda HÂLÂ asılı (zaman aşımı yok)"
    assert isinstance(sonuc.get("r"), Exception), f"kilitli kaynakta yedek istisnasız döndü: {sonuc}"
    assert "kilitli" in str(sonuc["r"]), f"hata nedeni kilit olarak söylenmiyor: {sonuc['r']!r}"
    assert sonuc["sure"] < 10, f"sınır 1 sn iken iptal {sonuc['sure']:.1f} sn sürdü"
    assert not os.path.exists(hedef), "iptal edilen yedekte son ad OLUŞTU"
    assert not os.path.exists(yd.gecici_yol(hedef)), "iptal edilen yedeğin geçici dosyası KALDI"


def test_KRITIK_duz_yedek_kilitli_kaynakta_SINIRDA_iptal(tmp_path, kisa_sinir):
    kaynak = _kaynak(tmp_path)
    hedef = str(tmp_path / "pemf_treatment_history_20261027_010101.db")
    kilit = _kilitle(kaynak)

    def is_():
        src = sqlite3.connect(kaynak, timeout=0.3)
        try:
            yd.yedek_yaz(src, hedef, sqlite3, "", _log)
        finally:
            src.close()

    th, sonuc = _kostur(is_)
    _dogrula_iptal(th, sonuc, kilit, hedef)


def test_KRITIK_hesap_yedegi_sifreli_kolda_kilitli_kaynakta_SINIRDA_iptal(tmp_path, kisa_sinir):
    sqlcipher3 = pytest.importorskip("sqlcipher3")
    kaynak = _kaynak(tmp_path)
    hedef = str(tmp_path / "pemf_auth_users_20261027_010101.db")
    kilit = _kilitle(kaynak)
    th, sonuc = _kostur(lambda: yd.duz_dbyi_yedekle(kaynak, hedef, sqlcipher3, "d5-hesap-anahtari", _log))
    _dogrula_iptal(th, sonuc, kilit, hedef)


def test_KARSIT_kilit_SINIRDAN_once_birakilirsa_yedek_ALINIR(tmp_path, monkeypatch):
    monkeypatch.setattr(yd, "YEDEK_KILIT_SURESI_SN", 8.0, raising=False)
    monkeypatch.setattr(yd, "KAYNAK_BUSY_SN", 0.3, raising=False)
    kaynak = _kaynak(tmp_path)
    hedef = str(tmp_path / "pemf_treatment_history_20261027_020202.db")
    kilit = _kilitle(kaynak)
    threading.Timer(1.0, _birak, args=(kilit,)).start()

    def is_():
        src = sqlite3.connect(kaynak, timeout=0.3)
        try:
            yd.yedek_yaz(src, hedef, sqlite3, "", _log)
        finally:
            src.close()

    th, sonuc = _kostur(is_)
    assert not th.is_alive() and sonuc.get("r") == "TAMAM", f"kısa kilitten sonra yedek alınmadı: {sonuc}"
    assert sonuc["sure"] >= 0.8, f"kilit sürerken yedek bitti ({sonuc['sure']:.2f} sn) — aparat kilidi kurmadı"
    c = sqlite3.connect(hedef)
    try:
        assert c.execute("SELECT count(*) FROM t").fetchone()[0] == 300
    finally:
        c.close()
