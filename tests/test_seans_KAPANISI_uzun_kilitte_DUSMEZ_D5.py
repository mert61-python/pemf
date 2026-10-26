# -*- coding: utf-8 -*-
"""D3 devri → D5 · sağlamlık listesi: "kilit bir yazımın `busy_timeout`unu (5 sn) aşarsa durdurma sonrası kapanış yazımları DÜŞER"
(2-C incelemesi §9 #5 — "önceden var; yeniden deneme gerekir").

KUSUR: `_finalize_session_db` → `end_session` tedavi DB'si başka bir yazıcının UZUN işleminde (WAL: okuyucu geçer, ikinci yazıcı
`busy_timeout` 5 sn bekler) `database is locked` ile düşüyordu; istisna yalnız günlüğe yazılıp `db_finalized` kuruluyor, kimse yeniden
denemiyordu → operatörün durdurduğu AI Pro satırı `active` kalıyor, sonraki açılışta kurtarma onu "Elektrik Kesintisi" mühürlüyordu
(olmamış bir güç kaybı). Düzeltme: kapanış yazımı kilit hatasında SINIRLI yeniden denenir (yalnız iş parçacığından çağrılır — olay
döngüsünü / ACİL DURDUR'u bekletmez; STOP kapanıştan ÖNCE gider).
GERÇEK: tedavi DB dosyası İKİNCİ bir SQLite bağlantısının `BEGIN IMMEDIATE` + yazımıyla 7 sn kilitlenir, sonra bırakılır; AI Pro
gerçek uçtan başlatılır / durdurulur (`ai_pro_aparati`), kapanış gerçek kayıt kuyruğunda tamamlanır."""

from __future__ import annotations

import sqlite3
import threading
import time

import pytest

KILIT_SN = 7.0  # busy_timeout (5 sn) ÜSTÜ — bir denemeyi düşürür, ikinciye izin verir


@pytest.fixture
def o(monkeypatch, tmp_path):
    import ai_pro_aparati as ap
    from kayitci_donanim import gercek_hc
    from servers import operator_tokens

    o = ap.kur(monkeypatch, tmp_path)
    operator_tokens.temizle_hepsi()
    try:
        with gercek_hc() as hc:
            monkeypatch.setattr(o.api.state, "hardware", hc)
            o.hc = hc
            yield o
            o.c.post("/api/ai/pro/stop")
    finally:
        o.air._ai_loop_active = False
        o.geri()


def _baslat_ve_sur(o):
    import ai_pro_aparati as ap

    _pid, r = ap.onayli_baslat(o, organ=0)
    assert r.status_code == 200, r.text[:200]
    with o.api._session_lock:
        sid = o.api._active_session.get("db_session_id")
    ap.kare(o)
    assert ap.bekle(lambda: bool(ap.calisan(o)), 3), "aparat: AI Pro bobinleri sürmedi"
    return sid


def _durum(o, sid):
    with o.db._get_connection() as c:
        return c.execute("SELECT session_status FROM treatment_sessions WHERE id=?", (sid,)).fetchone()[0]


def _uzun_yazici(o, sure: float):
    """WAL'de uzun yazım işlemi: okuyucular geçer, ikinci yazıcı `busy_timeout` kadar bekleyip düşer."""
    kc = sqlite3.connect(str(o.db.db_path), isolation_level=None, timeout=5, check_same_thread=False)
    kc.execute("BEGIN IMMEDIATE")
    kc.execute("UPDATE system_settings SET setting_value = setting_value")
    # araç kanıtı: kilit gerçekten tutuluyor (ikinci yazıcı anında düşer)
    t = sqlite3.connect(str(o.db.db_path), timeout=0)
    try:
        with pytest.raises(sqlite3.OperationalError, match="locked"):
            t.execute("BEGIN IMMEDIATE")
    finally:
        t.close()

    def _birak():
        kc.execute("ROLLBACK")
        kc.close()

    zm = threading.Timer(sure, _birak)
    zm.start()
    return zm


def test_KRITIK_uzun_kilitte_AI_Pro_durdurma_KAPANISI_dusmez_satir_completed(o):
    from utils import dongu_disi_yazim

    sid = _baslat_ve_sur(o)
    zm = _uzun_yazici(o, KILIT_SN)
    t0 = time.monotonic()
    r = o.c.post("/api/ai/pro/stop")
    assert r.status_code == 200, r.text[:200]
    assert not ap_calisan(o), "aparat: STOP bobinleri durdurmadı"
    assert dongu_disi_yazim.bosalt(60), "kayıt kuyruğu 60 sn'de boşalmadı"
    zm.join(10)
    gecen = time.monotonic() - t0
    durum = _durum(o, sid)
    assert durum == "completed", (
        f"kilit {KILIT_SN:.0f} sn sürdü (busy_timeout 5 sn) ve kalktı; {gecen:.1f} sn sonra satır hâlâ {durum!r} — operatörün "
        "durdurduğu seans sonraki açılışta 'Elektrik Kesintisi' mühürlenir"
    )


def test_KARSIT_kalici_kilitte_yeniden_deneme_SINIRLI_kapanis_dongu_disi_ve_bitiyor(o):
    """Kilit HİÇ kalkmazsa yeniden deneme sonsuz değildir: kuyruk sınırlı sürede boşalır (satır açık kalır — kurtarma yolu)."""
    from utils import dongu_disi_yazim

    sid = _baslat_ve_sur(o)
    zm = _uzun_yazici(o, 40.0)
    t0 = time.monotonic()
    try:
        r = o.c.post("/api/ai/pro/stop")
        assert r.status_code == 200
        assert dongu_disi_yazim.bosalt(35), "kalıcı kilitte kapanış 35 sn'de bitmedi — yeniden deneme SINIRSIZ"
        gecen = time.monotonic() - t0
    finally:
        zm.cancel()
        zm.function()
    assert gecen < 35, gecen
    assert _durum(o, sid) == "active"


def ap_calisan(o):
    import ai_pro_aparati as ap

    return bool(ap.calisan(o))
