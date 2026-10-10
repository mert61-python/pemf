# -*- coding: utf-8 -*-
"""D2.23 (B-3.79) — günlük bakımın haftalık VACUUM adımı havuzdaki bağlantıyı AUTOCOMMIT'te bırakmaz.

ÖLÇÜLEN KUSUR: `api_server._daily_maintenance_loop` haftalık VACUUM için `conn.isolation_level = None` yapıyor ve GERİ YÜKLEMİYORDU.
Bağlantı `TreatmentHistoryDB`'nin iş parçacığı başına havuzundan geliyor ve döngü iş parçacığında süreç ömrü boyunca KALIYOR → sonraki her
turda aynı iş parçacığındaki yazımlar autocommit'te koşuyordu. En ağırı KVKK anonimleştirmesi: `anonymize_patients_by_uuid`'in hasta
kopyası, seans ve parametre UPDATE'leri tek işlem sanılıyor; ikinci UPDATE düşerse birincisi COMMIT'li kalıyor → tedavi DB'sinde YARIM
anonimleştirme (hasta kopyası [ANONIM], seans geçmişinde ad duruyor) ve kanonik taraf `anonymized=1` olduğu için bir daha denenmiyor.

Ölçüm aracı: GERÇEK döngü AYRI bir iş parçacığında 8 tur koşar (VACUUM `run_count % 7 == 0` turunda); `time.sleep` yaması YALNIZ o iş
parçacığında (ilk uyku = açılış beklemesi atlanır; 9. uyku = 8. tur sonu → durur). Döngü durduktan sonra AYNI iş parçacığında (aynı havuz
bağlantısı) ölçüm yapılır. Arıza EN ALT katta: ikinci UPDATE'i GERÇEK bir SQLite tetikleyicisi (`RAISE(ABORT)`) düşürür; VACUUM arızası
bağlantının `cursor().execute`'unda yalnız "VACUUM" metninde `OperationalError`.
"""

from __future__ import annotations

import sqlite3
import threading
import time

import pytest


class _TurBitti(BaseException):
    """Döngünün N. `sleep`i → istenen tur sayısı tamam. BaseException: döngünün `except Exception`'ı yutmasın."""


@pytest.fixture
def ortam(tmp_path, monkeypatch):
    from database.treatment_history_db import TreatmentHistoryDB
    from servers import api_server as api

    monkeypatch.delenv("PEMF_MASK_HISTORY_PII", raising=False)
    db = TreatmentHistoryDB(tmp_path)
    monkeypatch.setattr(api, "_get_treatment_db", lambda: db)
    monkeypatch.setattr(api, "get_patient_database", lambda: None)
    with api._session_lock:
        assert not api._active_session.get("is_active"), "aparat: aktif seans varken VACUUM atlanır (kapı kör olur)"
    try:
        yield api, db
    finally:
        db.close_connections()


def _hasta_ve_seans(db, kimlik="uuid-d223", ad="Pamuk D223"):
    pid = db.upsert_patient({"name": ad, "patient_uuid": kimlik})
    sid = int(db.start_session(treatment_mode="Manuel", patient_name=ad))
    db.set_session_meta(sid, patient_id=pid)
    db.end_session(sid, duration_minutes=5)
    return pid, sid


def _dongu_sonra_ayni_is_parcaciginda(api, tur: int, sonra):
    """GERÇEK `_daily_maintenance_loop`u `tur` tur koşturur, durduktan sonra AYNI iş parçacığında `sonra()`yı çağırır."""
    orj_sleep = time.sleep
    durum = {"ident": None, "uyku": 0}
    sonuc: dict = {}
    hatalar: list = []

    def _sleep(s):
        if threading.get_ident() == durum["ident"]:
            durum["uyku"] += 1
            if durum["uyku"] >= tur + 1:
                raise _TurBitti()
            return None
        return orj_sleep(s)

    def _kos():
        durum["ident"] = threading.get_ident()
        try:
            api._daily_maintenance_loop()
        except _TurBitti:
            try:
                sonuc["deger"] = sonra()
            except BaseException as e:  # noqa: BLE001 — aşağıda iddia edilir
                hatalar.append(e)
        except BaseException as e:  # noqa: BLE001
            hatalar.append(e)

    time.sleep = _sleep
    try:
        th = threading.Thread(target=_kos, daemon=True, name="bakim-d223")
        th.start()
        th.join(60)
    finally:
        time.sleep = orj_sleep
    assert not th.is_alive() and not hatalar and durum["uyku"] == tur + 1, (
        f"ölçüm aracı: döngü {tur} tur koşmadı (canlı={th.is_alive()}, uyku={durum['uyku']}, hata={hatalar})"
    )
    return sonuc["deger"]


def _havuz_ayari(db):
    with db._get_connection() as conn:  # aynı iş parçacığı → aynı havuz bağlantısı
        return conn.isolation_level, id(conn)


def test_KRITIK_VACUUM_turundan_sonra_havuz_baglantisi_VARSAYILAN_islem_kipinde(ortam):
    """MUTASYON: VACUUM sonrası `isolation_level` geri yüklemesi silinir → KIRMIZI."""
    api, db = ortam
    ayar, _ = _dongu_sonra_ayni_is_parcaciginda(api, 8, lambda: _havuz_ayari(db))
    assert ayar == "", f"haftalık VACUUM havuz bağlantısını autocommit'te bıraktı (isolation_level={ayar!r})"


def test_KRITIK_VACUUM_turundan_sonra_anonimlestirme_ATOMIK_ikinci_UPDATE_duserse_birincisi_GERI_alinir(ortam):
    """Yarım anonimleştirme yok: seans UPDATE'i GERÇEK tetikleyiciyle düşer → hasta kopyasının UPDATE'i de geri alınmış olmalı."""
    api, db = ortam
    _hasta_ve_seans(db)
    with db._get_connection() as c:
        c.execute(
            "CREATE TRIGGER d223_ariza BEFORE UPDATE OF patient_name ON treatment_sessions "
            "BEGIN SELECT RAISE(ABORT, 'D2.23 enjekte ariza'); END"
        )
        c.commit()

    def _anonimlestir():
        n = db.anonymize_patients_by_uuid(["uuid-d223"])
        with db._get_connection() as c:
            return n, c.execute("SELECT name FROM patients WHERE patient_uuid='uuid-d223'").fetchone()[0]

    n, ad = _dongu_sonra_ayni_is_parcaciginda(api, 8, _anonimlestir)
    # D2.54 (B-3.34): hata artık -1 (eskiden sessiz 0) — çağıran kalıcı bekleyen listeden düşürmez, yeniden dener.
    assert n == -1, f"aparat: ikinci UPDATE düşmedi (dönüş {n})"
    assert ad == "Pamuk D223", (
        f"ikinci UPDATE düştü ama hasta kopyası anonimleşmiş KALDI (yarım anonimleştirme): {ad!r}"
    )


def test_KARSIT_VACUUMsuz_7_turda_ayni_ariza_ZATEN_atomik(ortam):
    """Kusurun nedeni VACUUM turudur: VACUUM'suz 7 turdan sonra aynı arıza hasta kopyasını da geri alır (bugün de yeşil)."""
    api, db = ortam
    _hasta_ve_seans(db)
    with db._get_connection() as c:
        c.execute(
            "CREATE TRIGGER d223_ariza BEFORE UPDATE OF patient_name ON treatment_sessions "
            "BEGIN SELECT RAISE(ABORT, 'D2.23 enjekte ariza'); END"
        )
        c.commit()

    def _anonimlestir():
        db.anonymize_patients_by_uuid(["uuid-d223"])
        with db._get_connection() as c:
            return c.execute("SELECT name FROM patients WHERE patient_uuid='uuid-d223'").fetchone()[0]

    assert _dongu_sonra_ayni_is_parcaciginda(api, 7, _anonimlestir) == "Pamuk D223"


class _VacuumDusurenImlec:
    def __init__(self, imlec):
        self._imlec = imlec

    def execute(self, sql, *a):
        if str(sql).strip().upper().startswith("VACUUM"):
            raise sqlite3.OperationalError("database or disk is full")
        return self._imlec.execute(sql, *a)

    def __getattr__(self, ad):
        return getattr(self._imlec, ad)


class _VacuumDusurenBaglanti:
    """Havuzdaki GERÇEK bağlantıya her şeyi iletir (öznitelik yazımı dahil); yalnız imlecin VACUUM'u düşer."""

    def __init__(self, conn):
        object.__setattr__(self, "_conn", conn)

    def cursor(self, *a, **k):
        return _VacuumDusurenImlec(self._conn.cursor(*a, **k))

    def __getattr__(self, ad):
        return getattr(self._conn, ad)

    def __setattr__(self, ad, deger):
        setattr(self._conn, ad, deger)


def test_KRITIK_VACUUM_DUSERSE_de_havuz_baglantisi_VARSAYILAN_kipe_doner(ortam, monkeypatch):
    """MUTASYON: geri yükleme `finally` yerine yalnız başarılı yolda → KIRMIZI (disk dolu VACUUM'u bağlantıyı autocommit'te bırakırdı)."""
    from contextlib import contextmanager

    api, db = ortam
    asil = db._get_connection

    @contextmanager
    def _sarili():
        with asil() as conn:
            yield _VacuumDusurenBaglanti(conn)

    monkeypatch.setattr(db, "_get_connection", _sarili)
    ayar, _ = _dongu_sonra_ayni_is_parcaciginda(api, 8, lambda: _havuz_ayari(db))
    assert ayar == "", f"VACUUM düşünce havuz bağlantısı autocommit'te kaldı (isolation_level={ayar!r})"


def test_KARSIT_VACUUM_turu_GERCEKTEN_kosar(ortam, monkeypatch):
    """Araç kör değil: 8. turda VACUUM gerçekten çağrılır (7 turda çağrılmaz)."""
    from contextlib import contextmanager

    api, db = ortam
    asil = db._get_connection
    gorulen: list = []

    class _Imlec(_VacuumDusurenImlec):
        def execute(self, sql, *a):
            if str(sql).strip().upper().startswith("VACUUM"):
                gorulen.append(sql)
            return self._imlec.execute(sql, *a)

    class _Baglanti(_VacuumDusurenBaglanti):
        def cursor(self, *a, **k):
            return _Imlec(self._conn.cursor(*a, **k))

    @contextmanager
    def _sarili():
        with asil() as conn:
            yield _Baglanti(conn)

    monkeypatch.setattr(db, "_get_connection", _sarili)
    _dongu_sonra_ayni_is_parcaciginda(api, 7, lambda: None)
    assert gorulen == [], "7 turda VACUUM koşmamalıydı"
    _dongu_sonra_ayni_is_parcaciginda(api, 8, lambda: None)
    assert gorulen == ["VACUUM"], f"8. turda VACUUM koşmadı: {gorulen}"
