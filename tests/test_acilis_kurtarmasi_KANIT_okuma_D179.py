# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D1.79 · B-3.73 · B-3.74 — açılış kurtarması seans bitişini kanıttan türetirken geçici okuma hatasını "kanıt yok"
saymaz, şimdiden İLERİ tarihli kanıta güvenmez.

ÖLÇÜLEN KUSURLAR (88331b2):
  * B-3.73: `_seansin_son_kaniti` HER istisnayı "kanıt yok" sayıyordu → geçici disk hatasında (OperationalError 'disk I/O
    error') seans 0 dk ile `ABORTED_DUE_TO_POWER` MÜHÜRLENİYOR, açık bobin koşuları 0 sn kapanıyordu (geri dönüşsüz).
  * B-3.74: yalnız ALT sınır vardı → saat sıçramasıyla şimdiden günlerce ileri tarihli kanıt, günlerce süren doz kaydı
    üretiyordu (ölçüm: 4380 dk seans, 262800 sn koşu).
⚠️ Eski şema toleransı (yalnız 'no such table/column' = kanıt yok) KORUNUR (karşıt kol). Y9 ile ilgisi yok: tedavi
clamp'i değil, kayıt akla-yatkınlık süzgeci.
"""

from __future__ import annotations

import sqlite3
import time

import pytest


@pytest.fixture
def db(tmp_path):
    from database.treatment_history_db import TreatmentHistoryDB

    d = TreatmentHistoryDB(tmp_path / "gecmis")
    yield d
    d.close()


def _durum(db, sid):
    with db._get_connection() as conn:
        r = conn.execute(
            "SELECT session_status, duration_minutes FROM treatment_sessions WHERE id = ?", (sid,)
        ).fetchone()
    return r[0], r[1]


def _kosu(db, sid):
    return db.get_session_coil_runs(sid)[0]


class _VekilImlec:
    def __init__(self, gercek, hata):
        self._g = gercek
        self._hata = hata

    def execute(self, sql, *a):
        if "FROM session_coil_runs WHERE session_id" in sql and "MAX(" in sql:
            raise self._hata
        return self._g.execute(sql, *a)

    def __getattr__(self, ad):
        return getattr(self._g, ad)


class _VekilBaglanti:
    def __init__(self, gercek, hata):
        self._g = gercek
        self._hata = hata

    def cursor(self):
        return _VekilImlec(self._g.cursor(), self._hata)

    def __getattr__(self, ad):
        return getattr(self._g, ad)


def _hatali_baglanti(monkeypatch, db, hata):
    import contextlib

    gercek = db._get_connection

    @contextlib.contextmanager
    def _vekil():
        with gercek() as conn:
            yield _VekilBaglanti(conn, hata)

    monkeypatch.setattr(db, "_get_connection", _vekil)


def _seans_ve_kosu(db, kanit_ofs_s):
    """Seans 30 dk ÖNCE başlamış (süreç o arada öldü); kanıt başlangıçtan `kanit_ofs_s` sonra."""
    from datetime import datetime, timedelta

    sid = db.start_session(treatment_mode="Manuel", target_condition=None)
    bas_dt = (datetime.now() - timedelta(minutes=30)).replace(microsecond=0)
    with db._get_connection() as conn:
        conn.execute(
            "UPDATE treatment_sessions SET session_date = ?, start_time = ? WHERE id = ?",
            (bas_dt.strftime("%Y-%m-%d"), bas_dt.strftime("%H:%M:%S"), sid),
        )
        conn.commit()
    bas = bas_dt.timestamp()
    db.start_coil_run(sid, 1, frequency_hz=100.0, duty_percent=40.0, phase=0.0, started_epoch=bas + kanit_ofs_s)
    return sid, bas


def test_KRITIK_B373_GECICI_okuma_hatasi_seansi_0_dk_MUHURLEMEZ_sonraki_acilisa_birakir(db, monkeypatch):
    sid, _bas = _seans_ve_kosu(db, 8 * 60)
    _hatali_baglanti(monkeypatch, db, sqlite3.OperationalError("disk I/O error"))
    db.recover_stale_active_sessions(max_age_hours=0)
    monkeypatch.undo()
    durum, sure = _durum(db, sid)
    assert durum == "active", (
        f"geçici okuma hatası 'kanıt yok' sayıldı: seans {durum!r} / {sure} dk MÜHÜRLENDİ (8 dk'lık kanıt varken)"
    )
    assert _kosu(db, sid)["ended_epoch"] is None, "geçici hatada açık bobin koşusu 0 sn kapatıldı"
    # Sonraki açılış (hata geçti): kanıtla doğru mühürlenir.
    db.recover_stale_active_sessions(max_age_hours=0)
    durum2, sure2 = _durum(db, sid)
    assert durum2 == "ABORTED_DUE_TO_POWER" and sure2 == 8, (durum2, sure2)


def test_KARSIT_B373_ESKI_SEMA_tablo_yok_KANIT_YOK_sayilir_seans_kapanir(db, monkeypatch):
    """Eski şema toleransı korunur: 'no such table' = kanıt yok → başlangıçla mühürlenir (açık kalmaz)."""
    sid, _bas = _seans_ve_kosu(db, 8 * 60)
    _hatali_baglanti(monkeypatch, db, sqlite3.OperationalError("no such table: session_coil_runs"))
    db.recover_stale_active_sessions(max_age_hours=0)
    monkeypatch.undo()
    durum, _sure = _durum(db, sid)
    assert durum == "ABORTED_DUE_TO_POWER", f"eski şema (tablo yok) toleransı bozuldu: seans {durum!r} kaldı"


def test_KRITIK_B374_ILERI_tarihli_kanit_GUNLERCE_suren_doz_kaydi_URETMEZ(db):
    sid, bas = _seans_ve_kosu(db, 3 * 86400)  # saat sıçraması: kanıt şimdiden 3 gün ileride
    db.recover_stale_active_sessions(max_age_hours=0)
    durum, sure = _durum(db, sid)
    ust = (time.time() - bas) / 60.0 + 1
    assert durum == "ABORTED_DUE_TO_POWER" and sure <= ust, (
        f"şimdiden ileri tarihli kanıt güvenildi: seans {sure} dk (üst sınır {ust:.1f} dk)"
    )
    k = _kosu(db, sid)
    assert k["duration_seconds"] is not None and k["duration_seconds"] <= (time.time() - bas) + 60, (
        f"koşu {k['duration_seconds']} sn — ileri tarihli kanıtla kapatıldı"
    )
