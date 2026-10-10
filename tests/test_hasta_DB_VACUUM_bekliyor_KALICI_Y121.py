# -*- coding: utf-8 -*-
"""Y121 (S-C.3 · D2.57) — hasta veritabanında toplu silmeden sonra DÜŞEN VACUUM kalıcı "VACUUM bekliyor" işaretiyle ertelenir; açılışta
ve günlük bakımda yeniden denenir (AI geçmişindeki D1.58 deseni).

ÖLÇÜLEN KUSUR: D2.57'den beri `clear_all_patients` "silindi, VACUUM başarısız" diyor ama kimse yeniden denemiyordu — silinen hasta
kayıtları (alan şifreli değerler; cihaz anahtarıyla çözülebilir) dosyanın boş sayfalarında süresiz kalıyordu (KVKK silme hakkı).
GERÇEK: PatientDatabase (sentetik, tmp), günlük bakım döngüsünün GERÇEK bir turu (`api_server._daily_maintenance_loop` — ilk turu
açılıştan ~60 sn sonra koşar = "açılışta"; sonra günde bir). Arıza: VACUUM'u sürücü sınırında "database or disk is full" ile düşüren
bağlantı sarmalayıcısı (gerçek arıza biçimi; DELETE ve öteki ifadeler GERÇEK bağlantıya gider).
"""

from __future__ import annotations

import sqlite3
import threading
import time

import pytest


class _VacuumDiskDolu:
    """Gerçek bağlantıyı sarar; YALNIZ `VACUUM` ifadesi SQLite'ın disk-dolu hatasıyla düşer."""

    def __init__(self, c):
        self._c = c

    @staticmethod
    def _denetle(sql):
        if str(sql).strip().upper().startswith("VACUUM"):
            raise sqlite3.OperationalError("database or disk is full")

    def execute(self, sql, *a, **k):
        self._denetle(sql)
        return self._c.execute(sql, *a, **k)

    def cursor(self):
        gercek = self._c.cursor()
        dis = self

        class _K:
            def execute(self, sql, *a, **k):
                dis._denetle(sql)
                return gercek.execute(sql, *a, **k)

            def __getattr__(self, ad):
                return getattr(gercek, ad)

        return _K()

    def __getattr__(self, ad):
        return getattr(self._c, ad)


def _baytlar(yol) -> bytes:
    from pathlib import Path

    p = Path(yol)
    return b"".join(f.read_bytes() for f in (p, p.with_name(p.name + "-wal")) if f.exists())


@pytest.fixture
def pdb(tmp_path):
    from database.patient_database import PatientDatabase

    return PatientDatabase(str(tmp_path / "patients.db"))


def _disk_dolu(pdb):
    with pdb._get_connection():
        pass  # bu iş parçacığının havuz bağlantısını aç
    pdb._local.conn = _VacuumDiskDolu(pdb._local.conn)


def _gercek_baglanti(pdb):
    if isinstance(getattr(pdb._local, "conn", None), _VacuumDiskDolu):
        pdb._local.conn = pdb._local.conn._c


def test_KRITIK_Y121_toplu_silmede_VACUUM_duserse_KALICI_isaret(pdb, tmp_path):
    """MUTASYON: işaret yazılmaz → KIRMIZI."""
    from database.patient_database import PatientDatabase

    for i in range(3):
        pdb.add_patient({"name": f"Hasta Y121 {i}", "owner": "S"})
    _disk_dolu(pdb)
    silinen, vacuum_ok = pdb.clear_all_patients()
    _gercek_baglanti(pdb)
    assert (silinen, vacuum_ok) == (3, False), f"aparat: VACUUM düşmedi ({silinen}, {vacuum_ok})"
    assert pdb.vacuum_bekliyor_mu() is True, "düşen VACUUM için kalıcı 'bekliyor' işareti yazılmadı (Y121)"
    yeni = PatientDatabase(str(tmp_path / "patients.db"))  # yeniden başlatma
    assert yeni.vacuum_bekliyor_mu() is True, "işaret kalıcı değil (yeniden başlatmada kayboldu)"


def test_KRITIK_Y121_gunluk_bakim_turu_bekleyen_VACUUMU_yapar_kalinti_GIDER(pdb, monkeypatch):
    """Günlük bakımın GERÇEK turu (ilk tur = açılış) seans yokken hasta DB'sinin bekleyen VACUUM'unu koşar: işaret kalkar, silinen
    hastaların saklanan değerleri dosyadan gider. MUTASYON: döngüde hasta DB çağrısı yok → KIRMIZI."""
    from servers import api_server as api

    kimlikler = [pdb.add_patient({"name": f"Kalinti Y121 {i}", "owner": "Sahip Y121"}) for i in range(3)]
    with pdb._get_connection() as c:
        saklanan = [r[0] for r in c.execute("SELECT name FROM patients").fetchall()]
    assert kimlikler and all(s.encode() in _baytlar(pdb.db_file) for s in saklanan), "aparat KÖR"
    # secure_delete + denetim noktası (D2.29) olmadan önceki durum: VACUUM düştü, işaret yazıldı.
    with pdb._get_connection() as c:
        c.execute("PRAGMA secure_delete=OFF")
    _disk_dolu(pdb)
    assert pdb.clear_all_patients() == (3, False)
    _gercek_baglanti(pdb)
    assert pdb.vacuum_bekliyor_mu() is True

    monkeypatch.setattr(api, "get_patient_database", lambda *a, **k: pdb)
    monkeypatch.setattr(api, "_get_treatment_db", lambda: None)  # tedavi DB'si bu turun konusu değil
    with api._session_lock:
        eski = dict(api._active_session)
        api._active_session["is_active"] = False
    try:
        _bir_tur(api)
    finally:
        with api._session_lock:
            api._active_session.clear()
            api._active_session.update(eski)
    assert pdb.vacuum_bekliyor_mu() is False, "günlük bakım turu hasta DB'sinin bekleyen VACUUM'unu yapmadı (Y121)"
    kalan = [s for s in saklanan if s.encode() in _baytlar(pdb.db_file)]
    assert not kalan, f"VACUUM'dan sonra silinen hastaların saklanan değerleri ({len(kalan)}) dosyada KALDI"


def test_KARSIT_seans_SURERKEN_bekleyen_VACUUM_yapilmaz(pdb, monkeypatch):
    """VACUUM tüm DB'yi kilitler — seans sürerken ATLANIR (D1.58 ile aynı kural), işaret kalır."""
    from servers import api_server as api

    pdb.add_patient({"name": "Seans Y121", "owner": "S"})
    _disk_dolu(pdb)
    pdb.clear_all_patients()
    _gercek_baglanti(pdb)
    monkeypatch.setattr(api, "get_patient_database", lambda *a, **k: pdb)
    monkeypatch.setattr(api, "_get_treatment_db", lambda: None)
    with api._session_lock:
        eski = dict(api._active_session)
        api._active_session["is_active"] = True
    try:
        _bir_tur(api)
    finally:
        with api._session_lock:
            api._active_session.clear()
            api._active_session.update(eski)
    assert pdb.vacuum_bekliyor_mu() is True


def test_KARSIT_VACUUM_basariliysa_isaret_YOK(pdb):
    pdb.add_patient({"name": "Normal Y121", "owner": "S"})
    assert pdb.clear_all_patients() == (1, True)
    assert pdb.vacuum_bekliyor_mu() is False


class _TurBitti(Exception):
    pass


def _bir_tur(api):
    """`_daily_maintenance_loop`un tek turu: açılış beklemesi (1. uyku) atlanır, 2. uykuda (tur sonu) çıkılır."""
    orj = time.sleep
    durum = {"ident": None, "uyku": 0}

    def _sleep(s):
        if threading.get_ident() == durum["ident"]:
            durum["uyku"] += 1
            if durum["uyku"] >= 2:
                raise _TurBitti()
            return None
        return orj(s)

    def _kos():
        durum["ident"] = threading.get_ident()
        try:
            api._daily_maintenance_loop()
        except _TurBitti:
            pass

    time.sleep = _sleep
    try:
        th = threading.Thread(target=_kos, daemon=True)
        th.start()
        th.join(30)
    finally:
        time.sleep = orj
    assert durum["uyku"] == 2 and not th.is_alive(), f"aparat: döngü tek tur koşmadı ({durum})"


def test_KRITIK_Y121_basarili_toplu_silme_VACUUMundan_sonra_kalinti_YOK(pdb):
    """VACUUM başarılı yolda da WAL kipinde eski sayfalar denetim noktasına kadar ana dosyada kalır (ölçüldü) — silme sonrası
    TRUNCATE denetim noktası. MUTASYON: VACUUM sonrası denetim noktası yok → KIRMIZI."""
    for i in range(3):
        pdb.add_patient({"name": f"Basarili Y121 {i}", "owner": "Sahip"})
    with pdb._get_connection() as c:
        c.execute("PRAGMA secure_delete=OFF")  # yalnız VACUUM + denetim noktası ölçülsün
        saklanan = [r[0] for r in c.execute("SELECT name FROM patients").fetchall()]
    assert pdb.clear_all_patients() == (3, True)
    kalan = [s for s in saklanan if s.encode() in _baytlar(pdb.db_file)]
    assert not kalan, f"başarılı toplu silme + VACUUM sonrası saklanan değerler ({len(kalan)}) dosyada KALDI"
