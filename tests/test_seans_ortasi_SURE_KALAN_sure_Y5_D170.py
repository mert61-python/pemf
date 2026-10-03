# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D1.70 · B-1.8 · sahip kararı Y5 — seans ORTASINDA girilen süre KALAN süredir; kayda GERÇEK sürüş süresi yazılır.

ÖLÇÜLEN KUSUR (f870777 → 9079e93): `/api/session/parametre_guncelle` süreyi yalnız parametre satırı olarak kaydedip
"success" dönüyordu; seansın süresine ve süre bekçisine İŞLENMİYORDU. Arayüz yeni süreyi bobinlere "şimdiden itibaren"
gönderiyor (`/coil/batch` duration = dk × 60). Sonuç:
  * KISALTMA (20 dk'lık seansın 10. dk'sında 5 dk): bobinler 15. dk'da durdu ama seans 20. dk'ya kadar AKTİF kaldı ve
    kayıt "completed 20" yazdı (kaydedilen ≠ uygulanan);
  * UZATMA (10. dk'da 15 dk): bekçi seansı 20. dk'da kesti — bobinler 25. dk'ya kadar sürülecekti;
  * kalan süre (`/api/session/active`) eski toplamdan hesaplanıyordu.

KAPI: GERÇEK uçlar + GERÇEK `HardwareController` (kayıtçı kuyruk) + GERÇEK süre bekçisi turu (`tests/dongu_tek_tur.py`).
Monotonik saat yalnız İLERİ kaydırılır (istekler arasında).
"""

from __future__ import annotations

import time

import ai_pro_aparati as ap
import pytest
from dongu_tek_tur import bir_tur_kos


@pytest.fixture
def o(monkeypatch, tmp_path):
    from kayitci_donanim import gercek_hc

    ns = ap.kur(monkeypatch, tmp_path)
    gercek = time.monotonic
    ns.ofs = {"s": 0.0}
    monkeypatch.setattr(time, "monotonic", lambda: gercek() + ns.ofs["s"])
    try:
        with gercek_hc() as hc:
            monkeypatch.setattr(ns.api.state, "hardware", hc)
            ns.hc = hc
            yield ns
    finally:
        ns.geri()


def _seans(o, sure_dk=20):
    r = o.c.post(
        "/api/session/start",
        json={"mode": "Manuel", "frequency": 100, "duty": 40, "phase": 0, "duration_minutes": sure_dk, "coil_ids": [1]},
    )
    assert r.status_code == 200 and r.json().get("status") == "success", r.text[:300]
    return o.api._active_session.get("db_session_id")


def _guncelle(o, kalan_dk):
    """Arayüzün sırası (`ControlScreen.handleParametreGuncelle`): önce bobinlere yeni süre, sonra kayıt/seans."""
    rb = o.c.post(
        "/api/coil/batch",
        json={"coil_ids": [1], "freq": 100, "duty": 40, "phase": 0, "duration": kalan_dk * 60, "start": True},
    )
    assert rb.status_code == 200, rb.text[:300]
    return o.c.post("/api/session/parametre_guncelle", json={"duration_minutes": kalan_dk, "coil_ids": [1]})


def _tur(o):
    _uyku, hatalar = bir_tur_kos(o.api._session_duration_watchdog)
    assert not hatalar, f"aparat: bekçi turu hata verdi: {hatalar!r}"


def _aktif(o):
    return bool(o.api._active_session.get("is_active"))


def _satir(o, sid):
    with o.db._get_connection() as conn:
        r = conn.execute(
            "SELECT session_status, duration_minutes FROM treatment_sessions WHERE id = ?", (sid,)
        ).fetchone()
    return r[0], r[1]


def test_KRITIK_Y5_KISALTMA_seans_KALAN_sureyle_biter_kayit_GERCEK_sureyi_yazar(o):
    sid = _seans(o, 20)
    o.ofs["s"] = 600.0  # 10. dakika
    r = _guncelle(o, 5)
    assert r.status_code == 200 and r.json().get("status") == "success", r.text[:300]
    o.ofs["s"] = 600.0 + 290.0
    _tur(o)
    assert _aktif(o), "seans KALAN süre dolmadan bitti"
    o.ofs["s"] = 600.0 + 305.0
    _tur(o)
    assert not _aktif(o), (
        "10. dk'da girilen 5 dk KALAN süre doldu (15. dk) ama seans AKTİF — bobinler durdu, kayıt seansı sürüyor sayar"
    )
    durum, sure = _satir(o, sid)
    assert durum == "completed" and sure == 15, f"kayıt GERÇEK süreyi yazmalı (15 dk): durum={durum!r} süre={sure!r}"


def test_KRITIK_Y5_UZATMA_bekci_seansi_ESKI_surede_KESMEZ(o):
    sid = _seans(o, 20)
    o.ofs["s"] = 600.0
    r = _guncelle(o, 15)
    assert r.status_code == 200 and r.json().get("status") == "success", r.text[:300]
    o.ofs["s"] = 1230.0  # eski bitişten (20. dk) 30 sn sonra
    _tur(o)
    assert _aktif(o), "uzatılan seans ESKİ sürede (20. dk) kesildi — bobinler 25. dk'ya dek sürülecekti"
    assert any(s["is_running"] for s in o.hc.coils_state.values()), "eski sürede bobinler de durduruldu"
    o.ofs["s"] = 600.0 + 905.0
    _tur(o)
    assert not _aktif(o)
    durum, sure = _satir(o, sid)
    assert durum == "completed" and sure == 25, f"kayıt GERÇEK süreyi yazmalı (25 dk): durum={durum!r} süre={sure!r}"


def test_KRITIK_Y5_aktif_seans_KALAN_sureyi_YENI_bitisten_hesaplar(o):
    _seans(o, 20)
    o.ofs["s"] = 600.0
    assert _guncelle(o, 5).status_code == 200
    s = o.c.get("/api/session/active").json()
    assert abs(int(s["remaining_sec"]) - 300) <= 5, f"kalan süre eski toplamdan hesaplanıyor: {s['remaining_sec']} sn"


def test_KRITIK_Y5_ISLENEMEYEN_sure_success_DONMEZ_bitis_DEGISMEZ(o):
    """0 / negatif kalan süre işlenemez: 422, seansın bitişi değişmez (eskiden kayda yazılıp 'success')."""
    _seans(o, 20)
    o.ofs["s"] = 600.0
    r = o.c.post("/api/session/parametre_guncelle", json={"duration_minutes": 0, "coil_ids": [1]})
    assert r.status_code == 422, f"işlenemeyen süre 'success' döndü: {r.status_code} {r.text[:200]}"
    o.ofs["s"] = 1190.0
    _tur(o)
    assert _aktif(o)
    o.ofs["s"] = 1205.0
    _tur(o)
    assert not _aktif(o), "seans planlanan sürede (20. dk) bitmedi"


def test_KRITIK_Y5_AI_Pro_onayli_SURESI_buradan_DEGISMEZ_409(o):
    """AI Pro süresi hekim onayının mührüdür (döngü kendi süresini mühürden okur): bu uçtan değiştirilemez — 'success'
    demek, uygulanmayan bir değişikliği uygulandı göstermek olurdu."""
    ap.muhurlu_seans_yaz(o.api, sure_dk=20)
    r = o.c.post("/api/session/parametre_guncelle", json={"duration_minutes": 5})
    assert r.status_code == 409, f"AI Pro seansında süre değişikliği kabul edildi: {r.status_code} {r.text[:200]}"
