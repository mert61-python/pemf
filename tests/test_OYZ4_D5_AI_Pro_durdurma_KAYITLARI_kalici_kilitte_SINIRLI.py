# -*- coding: utf-8 -*-
"""OYZ4 (zincir 56 AŞAMA 4 · D5 kalıcı kilit gerilemesi): AŞAMA 3 C3 (`cc531a1d`) AI Pro durdurmasının bobin çalışma kayıtlarını kayıt
kuyruğunda satırdan ÖNCE tek tek kapatıyordu; `end_coil_run` / özet yazımı kilit hatasını yutup her biri `busy_timeout` (5 sn) bekliyordu
→ kalıcı kilitte kuyruk 35 sn'de boşalmıyordu (`test_seans_KAPANISI_uzun_kilitte_DUSMEZ_D5` KARŞIT, yığının ucunda KIRMIZI).
SÖZLEŞME:
  · `acik_kosulari_kapat`: seansın açık koşularını TEK deyimde kapatır (açılış kurtarmasıyla aynı kural), başka seansa dokunmaz;
  · `_finalize_session_db` satır kapanışında seansın açık koşularını da kapatır (kilitte satırla AYNI sınırlı yeniden deneme);
  · AI Pro durdurma işi ÖNCE satırı kapatır; kapanış bütçesi tükendiyse kalan koşular DB'ye yazılmadan bellekten düşer (`kosuyu_unut`)
    — sonraki seansa sızmaz, DB'de satırla kapanmıştır.
GERÇEK: şifreli tedavi DB'si (geçici kök) + AI Pro aparatı (onaylı başlat → sürüş → /api/ai/pro/stop)."""

from __future__ import annotations

import pytest


@pytest.fixture
def o(monkeypatch, tmp_path):
    import ai_pro_aparati as ap
    from kayitci_donanim import gercek_hc

    o = ap.kur(monkeypatch, tmp_path)
    try:
        with gercek_hc() as hc:
            monkeypatch.setattr(o.api.state, "hardware", hc)
            o.hc = hc
            yield o
            o.c.post("/api/ai/pro/stop")
    finally:
        o.air._ai_loop_active = False
        o.geri()


def _yeni_seans(db) -> int:
    with db._get_connection() as c:
        cur = c.execute(
            "INSERT INTO treatment_sessions (session_date, start_time, session_status, treatment_mode) VALUES "
            "('2026-11-20', '01:00:00', 'active', 'Manuel')"
        )
        c.commit()
        return int(cur.lastrowid)


def test_acik_kosulari_kapat_YALNIZ_o_seansin_ACIK_kosulari(o):
    db = o.db
    s1, s2 = _yeni_seans(db), _yeni_seans(db)
    r1 = db.start_coil_run(
        s1, 1, started_epoch=1000.0, frequency_hz=100, duty_percent=40, phase=0, intensity_mt=None, hw_type="STM"
    )
    r2 = db.start_coil_run(
        s1, 2, started_epoch=1000.0, frequency_hz=100, duty_percent=40, phase=0, intensity_mt=None, hw_type="STM"
    )
    r3 = db.start_coil_run(
        s2, 3, started_epoch=1000.0, frequency_hz=100, duty_percent=40, phase=0, intensity_mt=None, hw_type="STM"
    )
    db.end_coil_run(r2, 1010.0)
    assert db.acik_kosulari_kapat(s1, 1100.0) == 1
    with db._get_connection() as c:
        satir = {
            r[0]: (r[1], r[2]) for r in c.execute("SELECT id, ended_epoch, duration_seconds FROM session_coil_runs")
        }
    assert satir[r1] == (1100.0, 100.0)
    assert satir[r2] == (1010.0, 10.0), "kapanmış koşu yeniden yazıldı"
    assert satir[r3] == (None, None), "başka seansın koşusu kapatıldı"


def _baslat_ve_sur(o) -> int:
    import ai_pro_aparati as ap

    _pid, r = ap.onayli_baslat(o, organ=0)
    assert r.status_code == 200, r.text[:200]
    with o.api._session_lock:
        sid = o.api._active_session.get("db_session_id")
    ap.kare(o)
    assert ap.bekle(lambda: bool(ap.calisan(o)), 3), "aparat: AI Pro bobinleri sürmedi"
    from utils import dongu_disi_yazim

    assert dongu_disi_yazim.bosalt(15)  # koşu başlatma kayıtları kuyrukta yazılır
    return sid


def test_KRITIK_butce_TUKENDIYSE_kosular_bellekten_duser_DB_de_satirla_kapanir(o, monkeypatch):
    from utils import dongu_disi_yazim

    sid = _baslat_ve_sur(o)
    with o.db._get_connection() as c:
        acik_once = c.execute(
            "SELECT COUNT(*) FROM session_coil_runs WHERE session_id=? AND ended_epoch IS NULL", (sid,)
        ).fetchone()[0]
    assert acik_once >= 2, "aparat: sürüş koşu kaydı açmadı"
    yazilan = []
    monkeypatch.setattr(o.api, "_finish_coil_run", lambda cid, *a, **k: yazilan.append(cid))
    monkeypatch.setattr(o.api, "KAPANIS_KILIT_SURESI_SN", -1.0)  # bütçe baştan tükenmiş (kalıcı kilit benzetimi)
    r = o.c.post("/api/ai/pro/stop")
    assert r.status_code == 200
    assert dongu_disi_yazim.bosalt(30)
    assert yazilan == [], "bütçe tükenmişken koşular tek tek yazılmaya çalışıldı"
    with o.api._active_coil_runs_lock:
        assert not o.api._active_coil_runs, f"koşular bellekte kaldı (sonraki seansa sızar): {o.api._active_coil_runs}"
    with o.db._get_connection() as c:
        kosu_idleri = {r[0] for r in c.execute("SELECT id FROM session_coil_runs WHERE session_id=?", (sid,))}
    assert not kosu_idleri & set(o.api._coil_run_stats), "unutulan koşuların istatistiği bellekte kaldı"
    with o.db._get_connection() as c:
        durum = c.execute("SELECT session_status FROM treatment_sessions WHERE id=?", (sid,)).fetchone()[0]
        acik = c.execute(
            "SELECT COUNT(*) FROM session_coil_runs WHERE session_id=? AND ended_epoch IS NULL", (sid,)
        ).fetchone()[0]
    assert durum == "stopped" and acik == 0, (durum, acik)


def test_KARSIT_butce_VARKEN_koşular_tek_tek_ozetiyle_yazilir_satir_ONCE(o, monkeypatch):
    from utils import dongu_disi_yazim

    sid = _baslat_ve_sur(o)
    sira = []
    gercek_fin, gercek_sat = o.api._finish_coil_run, o.air._ai_pro_satirini_kapat
    monkeypatch.setattr(
        o.api, "_finish_coil_run", lambda cid, *a, **k: (sira.append(("kosu", cid)), gercek_fin(cid, *a, **k))[1]
    )
    monkeypatch.setattr(
        o.air, "_ai_pro_satirini_kapat", lambda *a, **k: (sira.append(("satir", None)), gercek_sat(*a, **k))[1]
    )
    assert o.c.post("/api/ai/pro/stop").status_code == 200
    assert dongu_disi_yazim.bosalt(30)
    assert sira[0] == ("satir", None) and [c for t, c in sira[1:]] == list(range(1, 9)), sira
    with o.db._get_connection() as c:
        acik = c.execute(
            "SELECT COUNT(*) FROM session_coil_runs WHERE session_id=? AND ended_epoch IS NULL", (sid,)
        ).fetchone()[0]
    assert acik == 0


def test_kosuyu_unut_GECERSIZ_kimlik_ve_kosusuz_bobin_DOKUNMAZ():
    from servers import coil_run_tracker as crt

    with crt._active_coil_runs_lock:
        once = dict(crt._active_coil_runs)
    crt.kosuyu_unut("bobin-yok")
    crt.kosuyu_unut(None)
    crt.kosuyu_unut(99)
    with crt._active_coil_runs_lock:
        assert dict(crt._active_coil_runs) == once
