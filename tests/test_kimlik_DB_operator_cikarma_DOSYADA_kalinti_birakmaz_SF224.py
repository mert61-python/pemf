# -*- coding: utf-8 -*-
"""S-F2-2.4 (2-F incelemesi A2 · Y123 önerilen) — kimlik DB'si (`auth_users.db`, her kurulumda düz SQLite) Y13 güvenli silme kapsamında:
çıkarılan hekimin e-postası ve görünen adı, çıkarma + denetim noktasından sonra dosyada (ana dosya + -wal) KALMAZ.

ÖLÇÜLEN (A2 sondası `K2\\sonda_operator_silme_kalintisi.py`): tedavi / hasta DB'lerinin aksine kimlik DB'sinde `secure_delete` KAPALIYDI —
`remove_operator` + TRUNCATE denetim noktasından sonra (SQL'de canlı satır 0) e-posta ham baytlarda duruyordu (benzersiz e-posta dizininin
serbest bırakılan hücresi). Aynı e-posta ekleme-only denetim izinde bilerek kalır (`operator.remove`); bu kapı yalnız kimlik DB'sini ölçer.
GERÇEK `AuthDB` (geçici dizin); denetim noktası ayrı bağlantıdan (üründe son bağlantı kapanınca SQLite kendisi yapar).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

E = "dr.cikarilan.sf224@klinik.com"
AD = "Dr Cikarilan SF224"


def _ham(db_path) -> bytes:
    p = Path(db_path)
    return b"".join(f.read_bytes() for f in (p, Path(str(p) + "-wal")) if f.exists())


def _denetim_noktasi(db_path) -> None:
    c = sqlite3.connect(str(db_path))
    try:
        c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        c.close()


def test_KRITIK_cikarilan_hekimin_eposta_ve_adi_DOSYADA_kalmaz(tmp_path):
    """MUTASYON: `AuthDB._conn` `secure_delete=ON` kurmaz → KIRMIZI."""
    from database.auth_db import AuthDB

    adb = AuthDB(tmp_path)
    assert adb.enroll_operator(E, AD, "123456")[0] is True
    _denetim_noktasi(adb.db_path)
    ham = _ham(adb.db_path)
    assert E.encode() in ham and AD.encode() in ham, "aparat KÖR: kayıt dosyada görünmüyor"
    assert adb.remove_operator(E) is True
    _denetim_noktasi(adb.db_path)
    with sqlite3.connect(str(adb.db_path)) as c:
        assert c.execute("SELECT COUNT(*) FROM device_operators WHERE email=?", (E,)).fetchone()[0] == 0
    ham = _ham(adb.db_path)
    kalan = [ad for ad, b in (("e-posta", E.encode()), ("ad", AD.encode())) if b in ham]
    assert not kalan, f"çıkarılan hekimin {kalan} kimlik DB'si dosyasında KALDI (Y13 güvenli silme)"


def test_KARSIT_cikarilmayan_hekim_KALIR(tmp_path):
    from database.auth_db import AuthDB

    adb = AuthDB(tmp_path)
    adb.enroll_operator(E, AD, "123456")
    adb.enroll_operator("dr.kalan.sf224@klinik.com", "Dr Kalan SF224", "654321")
    adb.remove_operator(E)
    _denetim_noktasi(adb.db_path)
    assert b"dr.kalan.sf224@klinik.com" in _ham(adb.db_path)
