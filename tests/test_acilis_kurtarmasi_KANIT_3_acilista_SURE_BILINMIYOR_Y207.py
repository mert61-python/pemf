# -*- coding: utf-8 -*-
"""Y207 (S-D5.3) — açılış kurtarması seansın kanıtını 3 AÇILIŞ boyunca okuyamazsa seans "süre bilinmiyor" (`ABORTED_DURATION_UNKNOWN`) kapanır;
süre ve doz UYDURULMAZ (NULL kalır), kayıt (`session_events`) ve ekran (durum etiketi + açıklama, TR + EN) bunu söyler.

ÖLÇÜLEN (D5 DEV-D1§7.D2c · 1-F inc. O-11.1): D1.79 geçici okuma hatasında seansı mühürlemez ve "sonraki açılışta yeniden dener" — kalıcı
arızada seans HER açılışta `active` kalıyordu (ekranda "Aktif", bulut kopyası açık). SAHİP KARARI Y207: 3 açılış → "süre bilinmiyor".
D1.79 güvencesi KORUNUR: 1. ve 2. açılışta seans mühürlenmez (geçici hata "kanıt yok" sayılmaz, 0 dk / 0 sn yazılmaz); arada kanıt okunur
hâle gelirse seans KANITLA doğru mühürlenir.

Kurulum EN ALT katta: kanıt sorgusu GERÇEK `sqlite3.OperationalError('disk I/O error')` ile düşer (D1.79 imleç vekili deseni). GERÇEK
`TreatmentHistoryDB.recover_stale_active_sessions`, GERÇEK katalog.
"""

from __future__ import annotations

import contextlib
import json
import sqlite3
from datetime import datetime, timedelta

import pytest


@pytest.fixture
def db(tmp_path):
    from database.treatment_history_db import TreatmentHistoryDB

    d = TreatmentHistoryDB(tmp_path / "gecmis")
    yield d
    d.close()


class _VekilImlec:
    def __init__(self, gercek, hata):
        self._g, self._hata = gercek, hata

    def execute(self, sql, *a):
        if "FROM session_coil_runs WHERE session_id" in sql and "MAX(" in sql:
            raise self._hata
        return self._g.execute(sql, *a)

    def __getattr__(self, ad):
        return getattr(self._g, ad)


class _VekilBaglanti:
    def __init__(self, gercek, hata):
        self._g, self._hata = gercek, hata

    def cursor(self):
        return _VekilImlec(self._g.cursor(), self._hata)

    def __getattr__(self, ad):
        return getattr(self._g, ad)


def _acilis(db, monkeypatch, hatali: bool):
    """Bir açılışın kurtarması — kanıt okuması `hatali` ise GERÇEK SQLite G/Ç hatasıyla düşer."""
    if hatali:
        gercek = db._get_connection

        @contextlib.contextmanager
        def _vekil():
            with gercek() as conn:
                yield _VekilBaglanti(conn, sqlite3.OperationalError("disk I/O error"))

        monkeypatch.setattr(db, "_get_connection", _vekil)
    try:
        return db.recover_stale_active_sessions(max_age_hours=0)
    finally:
        monkeypatch.undo()


def _seans(db):
    sid = db.start_session(treatment_mode="Manuel", target_condition=None)
    bas_dt = (datetime.now() - timedelta(minutes=30)).replace(microsecond=0)
    with db._get_connection() as conn:
        conn.execute(
            "UPDATE treatment_sessions SET session_date = ?, start_time = ? WHERE id = ?",
            (bas_dt.strftime("%Y-%m-%d"), bas_dt.strftime("%H:%M:%S"), sid),
        )
        conn.commit()
    db.start_coil_run(
        sid, 1, frequency_hz=100.0, duty_percent=40.0, phase=0.0, started_epoch=bas_dt.timestamp() + 8 * 60
    )
    return sid


def _satir(db, sid):
    with db._get_connection() as conn:
        return conn.execute(
            "SELECT session_status, duration_minutes, end_time, sync_status FROM treatment_sessions WHERE id = ?",
            (sid,),
        ).fetchone()


def _olaylar(db, sid, tur):
    with db._get_connection() as conn:
        rows = conn.execute(
            "SELECT severity, payload FROM session_events WHERE session_id = ? AND event_type = ? ORDER BY id",
            (sid, tur),
        ).fetchall()
    return [(r[0], json.loads(r[1])) for r in rows]


def test_KRITIK_kanit_3_ACILIS_okunamazsa_SURE_BILINMIYOR_kapanir_doz_UYDURULMAZ(db, monkeypatch):
    sid = _seans(db)
    for n in (1, 2):
        _acilis(db, monkeypatch, hatali=True)
        assert _satir(db, sid)[0] == "active", (
            f"{n}. açılışta (D1.79) seans mühürlendi — geçici hata 'kanıt yok' sayılmamalı"
        )
    assert db.get_session_coil_runs(sid)[0]["ended_epoch"] is None
    assert _acilis(db, monkeypatch, hatali=True) == 1, "3. açılış kurtarması seansı saymadı"
    durum, sure, bitis, sync = _satir(db, sid)
    assert durum == "ABORTED_DURATION_UNKNOWN", (
        f"kanıt 3 açılış boyunca okunamadı ama seans {durum!r} kaldı — her açılışta 'sürüyor' görünür (Y207 / S-D5.3)"
    )
    assert sure is None and bitis is None, f"süre UYDURULDU: {sure!r} dk, bitiş {bitis!r} (Y207: NULL kalmalı)"
    k = db.get_session_coil_runs(sid)[0]
    assert k["duration_seconds"] is None, f"bobin koşusunun dozu UYDURULDU: {k['duration_seconds']!r} sn"
    assert sync == 0, "kapanış buluta gönderilmek üzere işaretlenmedi (D2.65 sözleşmesi)"
    denemeler = _olaylar(db, sid, "kurtarma_kaniti_okunamadi")
    assert [p.get("deneme") for _s, p in denemeler] == [1, 2, 3] and all(s == "warning" for s, _p in denemeler), (
        denemeler
    )
    son = _olaylar(db, sid, "seans_sure_bilinmiyor")
    assert len(son) == 1 and son[0][0] == "warning" and son[0][1].get("neden") == "kanit_okunamadi", son
    # 4. açılış: seans artık `active` değil → yeniden işlenmez, yeni olay yazılmaz.
    _acilis(db, monkeypatch, hatali=True)
    assert len(_olaylar(db, sid, "kurtarma_kaniti_okunamadi")) == 3 and _satir(db, sid)[0] == "ABORTED_DURATION_UNKNOWN"


def test_KARSIT_kanit_2_acilistan_sonra_OKUNURSA_kanitla_DOGRU_muhurlenir(db, monkeypatch):
    sid = _seans(db)
    _acilis(db, monkeypatch, hatali=True)
    _acilis(db, monkeypatch, hatali=True)
    _acilis(db, monkeypatch, hatali=False)
    durum, sure, _b, _s = _satir(db, sid)
    assert durum == "ABORTED_DUE_TO_POWER" and sure == 8, (durum, sure)
    assert _olaylar(db, sid, "seans_sure_bilinmiyor") == []


def test_ekran_ve_PDF_etiketi_iki_dilde_ve_aciklama_KATALOGDA():
    """Durum etiketi sunucu (PDF / CSV) ve arayüz haritasında; açıklama notu iki dilde dolu ve 'uydurulmadı / no estimated' der."""
    import i18n_yardimci as iy
    from utils.seans_durum import DURUM_ETIKETLERI

    assert DURUM_ETIKETLERI.get("aborted_duration_unknown") == "seans.durum.aborted_duration_unknown"
    sv_tr, sv_en = iy.katalog("sunucu", "tr"), iy.katalog("sunucu", "en")
    ui_tr, ui_en = iy.katalog("arayuz", "tr"), iy.katalog("arayuz", "en")
    assert (
        sv_tr["seans.durum.aborted_duration_unknown"]
        == ui_tr["seans.durum.aborted_duration_unknown"]
        == "Süre Bilinmiyor"
    )
    assert (
        sv_en["seans.durum.aborted_duration_unknown"]
        == ui_en["seans.durum.aborted_duration_unknown"]
        == "Duration Unknown"
    )
    assert "tahmini bir değer yazılmadı" in ui_tr["seans.detay.sureBilinmiyorNotu"]
    assert "no estimated value was recorded" in ui_en["seans.detay.sureBilinmiyorNotu"]
