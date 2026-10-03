# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D1.77 · B-3.9 — disk yazma korkuluğu kritikken (< 500 MB) seans ve AI Pro BAŞLATMA reddedilir; `/api/health` görür.

ÖLÇÜLEN KUSUR (022492d): `TreatmentHistoryDB._ensure_write_guardrail` her yazımı reddederken başlatma kapısı
(`_kayit_db_hazir` → `is_ready`) yalnız `SELECT` deniyordu → seans 200 dönüp bobinler hastaya SÜRÜLÜYOR, ama seans/doz/olay
kaydı 0 (kaydedilen ≠ uygulanan; E-stop ile biten seans açılışta 'Elektrik Kesintisi' mühürlenir). Orkestratör notu: aynı
"kayıtsız tedavi başlamaz" kapısı AI Pro başlatmasına da (İG-5.12) uygulanır. Ölçüt HTTP kodu değil TEL ve DB.
⚠️ Yalnız BAŞLATMA kapılanır: seans ortası kesilmez, ACİL DURDUR'a dokunulmaz (Ö.4-Y8 — karşıt kol).
"""

from __future__ import annotations

import types

import ai_pro_aparati as ap
import pytest

_KRITIK = types.SimpleNamespace(total=500 * 2**30, used=500 * 2**30 - 100 * 2**20, free=100 * 2**20)  # 100 MB boş


@pytest.fixture
def o(monkeypatch, tmp_path):
    from kayitci_donanim import gercek_hc
    from servers import api_server as _api0

    gercek_hazir = _api0._kayit_db_hazir
    ns = ap.kur(monkeypatch, tmp_path)
    monkeypatch.setattr(ns.api, "_kayit_db_hazir", gercek_hazir)  # aparatın "hep hazır" yamasını GERİ al
    try:
        with gercek_hc() as hc:
            monkeypatch.setattr(ns.api.state, "hardware", hc)
            ns.hc = hc
            yield ns
    finally:
        ns.geri()


def _disk_kritik(o, monkeypatch):
    monkeypatch.setattr(o.db, "_disk_usage_provider", lambda _p: _KRITIK)


def _surus(o, once):
    from kayitci_donanim import paket_coz

    return [p for p in o.hc.core._hw_send_queue.paketler[once:] if any(x > 0 for x in paket_coz(p)[0])]


def _satir_sayisi(o):
    with o.db._get_connection() as conn:
        return conn.execute("SELECT COUNT(*) FROM treatment_sessions").fetchone()[0]


def test_KRITIK_disk_kritikken_seans_BASLAMAZ_telde_START_yok_kayit_yok(o, monkeypatch):
    _disk_kritik(o, monkeypatch)
    once, n = len(o.hc.core._hw_send_queue.paketler), _satir_sayisi(o)
    r = o.c.post(
        "/api/session/start",
        json={"mode": "Manuel", "frequency": 100, "duty": 40, "phase": 0, "duration_minutes": 20, "coil_ids": [1, 2]},
    )
    assert not _surus(o, once) and not any(s["is_running"] for s in o.hc.coils_state.values()), (
        f"disk kritikken (kayıt yazılamaz) bobinler SÜRÜLDÜ — kayıtsız tedavi (yanıt {r.status_code})"
    )
    assert r.status_code == 503 and "disk" in r.text.lower(), f"{r.status_code} {r.text[:200]}"
    assert _satir_sayisi(o) == n


def test_KRITIK_disk_kritikken_saglik_dbReady_FALSE_ve_nedeni_DISK(o, monkeypatch):
    _disk_kritik(o, monkeypatch)
    h = o.c.get("/api/health").json()
    assert h.get("dbReady") is False, f"disk kritikken sağlık dbReady={h.get('dbReady')!r}"
    assert "disk" in str(h.get("dbSebep") or "").lower(), f"neden diski söylemiyor: {h.get('dbSebep')!r}"


def test_KRITIK_disk_kritikken_AI_Pro_BASLAMAZ_ve_ONAY_YANMAZ(o, monkeypatch):
    from servers import ai_approval

    _disk_kritik(o, monkeypatch)
    once = len(o.hc.core._hw_send_queue.paketler)
    pid, r = ap.onayli_baslat(o)
    assert r.status_code == 503 and "disk" in r.text.lower(), f"AI Pro disk kritikken: {r.status_code} {r.text[:200]}"
    assert not _surus(o, once) and not o.air._ai_loop_active
    ai_approval.dogrula(pid)  # onay TÜKETİLMEDİ (disk düzelince aynı onayla başlatılabilir) — fırlatırsa KIRMIZI


def test_KARSIT_Y8_disk_kritikken_ACIL_DURDUR_calisir(o, monkeypatch):
    from kayitci_donanim import paket_coz

    o.hc.update_coil(1, 100, 40, 0, 5, start=True)
    _disk_kritik(o, monkeypatch)
    once = len(o.hc.core._hw_send_queue.paketler)
    r = o.c.post("/api/hardware/emergency_stop")
    assert r.status_code == 200
    yeni = o.hc.core._hw_send_queue.paketler[once:]
    assert yeni and all(all(x == 0 for x in paket_coz(p)[0]) for p in yeni), "disk kritikken E-stop STOP göndermedi"


def test_KARSIT_disk_yeterliyken_seans_BASLAR(o):
    r = o.c.post(
        "/api/session/start",
        json={"mode": "Manuel", "frequency": 100, "duty": 40, "phase": 0, "duration_minutes": 20, "coil_ids": [1]},
    )
    assert r.status_code == 200 and r.json().get("status") == "success", r.text[:200]
    o.c.post("/api/session/stop")
