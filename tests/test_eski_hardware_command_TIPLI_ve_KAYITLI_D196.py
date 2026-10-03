# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D1.96 · B-1.33 · S-1.5 — eski `/api/hardware/command` başlatma dalları tipli, kayıtlı ve süresi doğru.

ÖLÇÜLEN KUSURLAR (edddf19):
  * `start_coil {duration: 0.5}` (30 sn) → `normalize_duration_minutes` `int()` ile 0'a kesiyor → HC "süre verilmedi"
    sayıp 120 dk'lık GÖZETİMSİZ kapağı uyguluyordu (deadline 7200 sn — istenmeden enerjili bobin);
  * ham `params` sözlüğü doğrulanmıyordu (kesirli/aralık dışı süre, geçersiz bobin kimliği "error" ya da sessiz kesme);
  * aktif seansta `start_coil`/`start_all_coils` KOŞU KAYDI AÇMIYORDU — 7 bobin kayıtsız sürülebiliyordu.
⚠️ Ö.4-Y8: `stop_all_coils` / `stop_coil` / 0 Hz (A-05 = STOP) hiçbir doğrulamaya TAKILMAZ (karşıt kollar).
"""

from __future__ import annotations

import time

import ai_pro_aparati as ap
import pytest


@pytest.fixture
def o(monkeypatch, tmp_path):
    from kayitci_donanim import gercek_hc

    ns = ap.kur(monkeypatch, tmp_path)
    try:
        with gercek_hc() as hc:
            monkeypatch.setattr(ns.api.state, "hardware", hc)
            # Eski uç çekirdek ister (503 kapısı) — kayıtçı çekirdek yeterli.
            monkeypatch.setattr(ns.api.state, "core", hc.core)
            ns.hc = hc
            yield ns
    finally:
        ns.geri()


def _komut(o, cmd, **params):
    return o.c.post("/api/hardware/command", json={"command": cmd, "params": params})


def _run_paketleri(o, once):
    from kayitci_donanim import paket_coz

    return [p for p in o.hc.core._hw_send_queue.paketler[once:] if any(x > 0 for x in paket_coz(p)[0])]


def test_KRITIK_D196_start_coil_30_sn_GOZETIMSIZ_120_dk_kapaga_DUSMEZ(o):
    """Kesirli süre tipli uçta 422 (sürülmez); doğrudan HC yolunda 0 < süre < 1 dk YUKARI yuvarlanır (≤ 60 sn)."""
    once = len(o.hc.core._hw_send_queue.paketler)
    r = _komut(o, "start_coil", coil_id=1, freq=100, duty=40, phase=0, duration=0.5)
    assert r.status_code == 422, f"kesirli süre (0,5 dk) kabul edildi: {r.status_code} {r.text[:200]}"
    assert not _run_paketleri(o, once) and not o.hc.coils_state[1]["is_running"], "422'ye rağmen bobin sürüldü"
    assert o.hc.update_coil(1, 100, 40, 0, 0.5, start=True) is True
    kalan = o.hc._coil_deadline[1] - time.monotonic()
    assert kalan <= 61.0, f"0,5 dk'lık sürüş {kalan:.0f} sn gözetimsiz kapağa düştü (120 dk = 7200 sn)"


@pytest.mark.parametrize(
    ("params", "neden"),
    [
        ({"coil_id": 1, "duration": -1}, "negatif süre"),
        ({"coil_id": 1, "duration": 10**6}, "protokol üstü süre"),
        ({"coil_id": 1, "duration": "5x"}, "sayı olmayan süre"),
        ({"coil_id": 9, "duration": 5}, "STM dışı bobin"),
        ({"coil_id": 1.5, "duration": 5}, "kesirli bobin kimliği"),
        ({"coil_id": 1, "duration": 5, "freq": "HASTA-ADI-XYZ"}, "sayı olmayan frekans"),
    ],
)
def test_KRITIK_D196_start_coil_GECERSIZ_parametre_422_surulmez(o, params, neden):
    once = len(o.hc.core._hw_send_queue.paketler)
    r = _komut(o, "start_coil", **params)
    assert r.status_code == 422, f"{neden}: {r.status_code} {r.text[:200]}"
    assert "HASTA-ADI" not in r.text, "422 yanıtı ham girdiyi geri döndürdü"
    assert not _run_paketleri(o, once), f"{neden}: 422'ye rağmen sürüldü"


def test_KRITIK_D196_start_all_coils_KESIRLI_sure_422(o):
    once = len(o.hc.core._hw_send_queue.paketler)
    r = _komut(o, "start_all_coils", freq=100, duty=40, phase=0, duration=0.5)
    assert r.status_code == 422, f"start_all_coils kesirli süre kabul edildi: {r.status_code} {r.text[:200]}"
    assert not _run_paketleri(o, once)


def test_KRITIK_D196_aktif_seansta_eski_START_KOSU_KAYDI_acar(o):
    r = o.c.post(
        "/api/session/start",
        json={"mode": "Manuel", "frequency": 100, "duty": 40, "phase": 0, "duration_minutes": 20, "coil_ids": [1]},
    )
    assert r.status_code == 200, r.text[:200]
    sid = o.api._active_session.get("db_session_id")
    assert sid
    r1 = _komut(o, "start_coil", coil_id=2, freq=120, duty=30, phase=0, duration=5)
    assert r1.status_code == 200 and r1.json().get("status") == "success", r1.text[:200]
    kosu2 = [k for k in o.db.get_session_coil_runs(sid) if int(k["coil_id"]) == 2]
    assert kosu2 and abs(float(kosu2[-1]["frequency_hz"]) - 120.0) < 1e-6, (
        f"aktif seansta eski uçla sürülen bobin 2 KAYITSIZ: {kosu2}"
    )
    r2 = _komut(o, "start_all_coils", freq=100, duty=40, phase=0, duration=5)
    assert r2.status_code == 200 and r2.json().get("status") == "success", r2.text[:200]
    kayitli = {int(k["coil_id"]) for k in o.db.get_session_coil_runs(sid) if k["ended_epoch"] is None}
    assert set(range(1, 8)) <= kayitli, f"start_all_coils ile sürülen bobinlerin açık koşusu yok: {sorted(kayitli)}"


def test_KARSIT_Y8_stop_all_coils_stop_coil_ve_0_Hz_DOGRULAMAYA_TAKILMAZ(o):
    """STOP yolları parametre doğrulamasından ve mandaldan bağımsız: E-stop mandallıyken de stop_all_coils 200 + STOP;
    0 Hz `start_coil` (A-05 = STOP) kesirli süreyle bile STOP üretir (422 DEĞİL)."""
    from kayitci_donanim import paket_coz

    _komut(o, "start_coil", coil_id=3, freq=100, duty=40, phase=0, duration=5)
    o.api._emergency_stop_all("manual")
    once = len(o.hc.core._hw_send_queue.paketler)
    r = _komut(o, "stop_all_coils")
    assert r.status_code == 200, r.text[:200]
    r0 = _komut(o, "start_coil", coil_id=3, freq=0, duty=40, phase=0, duration=0.5)
    assert r0.status_code == 200, f"0 Hz (STOP) doğrulamaya takıldı: {r0.status_code} {r0.text[:200]}"
    rs = _komut(o, "stop_coil", coil_id=3, duration="bozuk")
    assert rs.status_code == 200, rs.text[:200]
    yeni = o.hc.core._hw_send_queue.paketler[once:]
    assert len(yeni) >= 3 and all(all(x == 0 for x in paket_coz(p)[0]) for p in yeni), "STOP yolları KAPILANDI"
