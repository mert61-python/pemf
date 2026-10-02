# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""1-C bağımsız inceleme i3-F-1 + i2-F5 — AI Pro döngüsünün TEARDOWN STOP'u: mandallıyken her zaman gider, yeni
onaylı seansı öldürmez.

ÖLÇÜLEN KUSURLAR (c5b3c04):
  * i3-F-1 (A-63 · Ö.4-Y8): teardown STOP'u `estop_mandali.baslatma_engeli(nesil)`e bağlıydı; mandal kuruluyken de
    dolu döndüğü için E-stop sonrası teardown STOP'u ATLANIYORDU (STM stop_all 2→1, ESP STOP 3→2). Mandal kuruluyken
    yeni seans imkânsızdır — atlamanın gerekçesi yok, yalnız yedek gönderim azalıyordu.
  * i2-F5: teardown "yeni döngü yok" kararını `_ai_loop_lock` altında verip kilidi bırakıyor, STOP'u SONRA
    gönderiyordu. Aradaki anda başlayan YENİ onaylı seans (B): eski teardown'ın `stop_all_coils`u B'nin bobinlerini
    durdurup nesli artırıyor, B'nin döngüsü "bayat" sayılıp sessizce çıkıyordu — onayı tüketilmiş (30/30).

KAPI: GERÇEK `_ai_pro_loop` (sahte kamera, hızlı sahte lokalizasyon/doz), GERÇEK onay akışı, GERÇEK
`HardwareController` (kayıtçı kuyruk), GERÇEK `_emergency_stop_all`. i2-F5 kolunda teardown'ın STM STOP'u (döngü iş
parçacığından gelen İLK `stop_all_coils`) bir Event'te tutulur ve bu sırada B açılır; 30 deneme. Ölçüt: "kabul edilip
sessizce ölen B" = 0 ve "reddedilip onayı yanan B" = 0 (dürüst 409 + onay korunması güvenli sonuçtur).
"""

from __future__ import annotations

import threading
import time

import ai_pro_aparati as ap
import pytest

DENEME = 30


class _SahteKamera:
    def __init__(self, *a, **k):
        pass

    def isOpened(self):
        return True

    def read(self):
        import numpy as np

        return True, np.zeros((8, 8, 3), dtype=np.uint8)

    def release(self):
        pass


@pytest.fixture
def d(monkeypatch, tmp_path):
    from kayitci_donanim import gercek_hc
    from servers import ai_pro_hedef

    ns = ap.kur(monkeypatch, tmp_path, dongu_noop=False)
    monkeypatch.setattr(ns.air.cv2, "VideoCapture", _SahteKamera)
    monkeypatch.setattr(ai_pro_hedef.KediSaglayici, "yukle", lambda self: None)
    canli = {"n": 0}
    gercek = ns.air._ai_pro_loop

    def _sayan(*a, **k):
        canli["n"] += 1
        try:
            return gercek(*a, **k)
        finally:
            canli["n"] -= 1

    monkeypatch.setattr(ns.air, "_ai_pro_loop", _sayan)
    ns.canli = canli
    kanca = {"ev": None, "girdi": threading.Event()}
    ns.kanca = kanca
    try:
        with gercek_hc() as hc:
            orj_stop_all = hc.stop_all_coils

            def _kancali_stop_all():
                ev = kanca["ev"]
                if ev is not None and threading.current_thread().name == "ai-pro-dongu":
                    kanca["ev"] = None
                    kanca["girdi"].set()
                    assert ev.wait(15), "aparat: teardown engeli kalkmadı"
                return orj_stop_all()

            hc.stop_all_coils = _kancali_stop_all
            monkeypatch.setattr(ns.api.state, "hardware", hc)
            ns.hc = hc
            yield ns
    finally:
        ns.air._ai_loop_active = False
        ap.bekle(lambda: canli["n"] == 0, 8)
        ns.geri()


def _stop_paket(o, once: int) -> int:
    from kayitci_donanim import paket_coz

    return sum(1 for p in o.hc.core._hw_send_queue.paketler[once:] if all(x == 0 for x in paket_coz(p)[0]))


# ── i3-F-1 ─────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_KRITIK_estop_sonrasi_MANDALLIYKEN_dongu_teardown_STOP_GONDERIR(d, monkeypatch):
    from utils import estop_mandali as m

    monkeypatch.setenv("PEMF_ESP_ENABLED", "1")  # ESP yayınları da sayılsın (sahte yayın — ağ yok)
    for _ in range(3):
        ap.mandali_sifirla(d.c)
        assert ap.bekle(lambda: d.canli["n"] == 0, 8), "aparat: önceki döngü bitmedi"
        _pid, r = ap.onayli_baslat(d)
        assert r.status_code == 200 and r.json().get("status") == "success", r.text[:200]
        assert ap.bekle(lambda: bool(ap.calisan(d)), 8), "aparat: döngü bobini sürmedi"
        stop_once = d.hc.stop_all_cagri
        y0 = len(d.yayin)
        d.api._emergency_stop_all("manual")
        stop_estop = d.hc.stop_all_cagri - stop_once
        y_estop = len(d.yayin)
        assert ap.bekle(lambda: d.canli["n"] == 0, 8), "döngü E-stop'tan sonra bitmedi"
        stop_teardown = d.hc.stop_all_cagri - stop_once - stop_estop
        ai_stop = [
            p
            for _t, p in d.yayin[y_estop:]
            if p.get("command") == "stop" and str(p.get("command_id", "")).startswith("ai_stop_")
        ]
        assert m.mandalli_mi(), "aparat: mandal test içinde kalktı (sıfırlanmamalıydı)"
        assert stop_teardown >= 1 and ai_stop, (
            f"MANDAL KURULUYKEN (yeni seans imkânsız) döngü teardown'ı STOP GÖNDERMEDİ: teardown stop_all="
            f"{stop_teardown}, ai_stop ESP={len(ai_stop)} (E-stop: stop_all={stop_estop}, yayın={y_estop - y0}) — "
            "yedek gönderim azaldı (A-63 / Ö.4-Y8)"
        )


def test_KARSIT_ai_pro_stop_ardindan_YENI_elle_seans_ESKI_dongu_teardowni_OLDURMEZ(d):
    """Mandalsız bayat nesil: döngü tahminde bloklu → /ai/pro/stop (nesil++) → YENİ elle seans (bobin 1) → eski döngü
    serbest kalır ve biter. Yeni seansın bobini ÇALIŞMAYA devam eder (teardown onu öldürmez)."""
    d.tahmin.engel = threading.Event()
    d.tahmin.girdi.clear()
    ap.mandali_sifirla(d.c)
    _pid, r = ap.onayli_baslat(d)
    assert r.status_code == 200 and r.json().get("status") == "success", r.text[:200]
    assert d.tahmin.girdi.wait(10), "aparat: döngü tahmine ulaşmadı"
    assert d.c.post("/api/ai/pro/stop").status_code == 200
    rs = d.c.post(
        "/api/session/start",
        json={"mode": "Manuel", "frequency": 100, "duty": 40, "phase": 0, "duration_minutes": 5, "coil_ids": [1]},
    )
    assert rs.status_code == 200, f"aparat: yeni elle seans başlamadı {rs.status_code} {rs.text[:200]}"
    assert d.hc.coils_state[1]["is_running"], "aparat: yeni seansın bobini sürülmedi"
    d.tahmin.engel.set()
    assert ap.bekle(lambda: d.canli["n"] == 0, 8), "eski döngü bitmedi"
    with d.api._session_lock:
        aktif = bool(d.api._active_session.get("is_active"))
    assert d.hc.coils_state[1]["is_running"] and aktif, "ESKİ döngünün teardown'ı YENİ elle seansın bobinini DURDURDU"


# ── i2-F5 ──────────────────────────────────────────────────────────────────────────────────────────────────────────
def _temiz(d):
    d.tahmin.engel = None
    ap.mandali_sifirla(d.c)
    d.c.post("/api/ai/pro/stop")
    assert ap.bekle(lambda: d.canli["n"] == 0, 8), "aparat: önceki döngü bitmedi"
    ap.mandali_sifirla(d.c)


def _tur(d, yaris: bool = True) -> dict:
    from servers import ai_approval

    _temiz(d)
    _pid_a, r = ap.onayli_baslat(d)
    assert r.status_code == 200 and r.json().get("status") == "success", r.text[:200]
    n0 = d.tahmin.sayi
    assert ap.bekle(lambda: d.tahmin.sayi > n0, 5), "aparat: döngü A sürmedi"
    ev = threading.Event()
    d.kanca["girdi"].clear()
    d.kanca["ev"] = ev if yaris else None
    d.air._ai_started_at = time.monotonic() - 100_000  # A'nın KENDİ süresi doldu (yetki geçerli teardown)
    if yaris:
        assert d.kanca["girdi"].wait(8), "aparat: A teardown'ı stop_all_coils'e ulaşmadı"
    else:
        assert ap.bekle(lambda: d.canli["n"] == 0, 8), "aparat: A bitmedi"
    rec = ai_approval.create("ai_pro", {"organ_id": 0, "duration_minutes": 5, "model": "kedi"})
    ai_approval.approve(rec["id"], "hekim@test.local")
    pid_b = rec["id"]
    kutu: dict = {}
    tb = threading.Thread(
        target=lambda: kutu.update(r=d.c.post("/api/ai/pro/start", json={"proposal_id": pid_b})), daemon=True
    )
    tb.start()
    # Düzeltilmiş üründe B'nin `/start`ı teardown'ın kilidinde bekler; engel en geç 1 sn sonra kalkar.
    tb.join(1.0)
    ev.set()
    tb.join(15)
    rb = kutu.get("r")
    assert rb is not None, "aparat: B yanıtı yok"
    b_kabul = rb.status_code == 200 and rb.json().get("status") == "success"
    time.sleep(2.0)  # B'nin döngüsü ~1 sn'lik turla çalışır; ölüyorsa bu sürede çıkar
    with d.api._session_lock:
        s = dict(d.api._active_session)
    return {
        "b_http": rb.status_code,
        "b_kabul": b_kabul,
        "b_onay_durumu": (ai_approval.get(pid_b) or {}).get("status"),
        "b_seans_aktif": bool(s.get("is_active")) and s.get("onay_kimligi") == pid_b,
        "b_dongu_canli": d.canli["n"] >= 1 and bool(d.air._ai_loop_active),
        "calisan": ap.calisan(d),
    }


def test_KRITIK_ESKI_teardown_YENI_onayli_seansi_SESSIZCE_OLDURMEZ_N30(d):
    ihlal = red_onay_yandi = 0
    ornek = None
    for _ in range(DENEME):
        s = _tur(d)
        if not s["b_kabul"]:
            if s["b_onay_durumu"] != "approved":
                red_onay_yandi += 1
                ornek = ornek or s
            continue
        if not (s["b_seans_aktif"] and s["b_dongu_canli"] and s["calisan"]):
            ihlal += 1
            ornek = ornek or s
    assert red_onay_yandi == 0 and ihlal == 0, (
        f"{DENEME} denemede ESKİ döngünün teardown'ı YENİ onaylı seansı öldürdü: kabul edilip sessizce ölen={ihlal}, "
        f"reddedilip onayı yanan={red_onay_yandi}. Örnek: {ornek}"
    )


def test_KARSIT_teardown_bittikten_sonra_yeni_seans_YASAR(d):
    for _ in range(3):
        s = _tur(d, yaris=False)
        assert s["b_kabul"] and s["b_seans_aktif"] and s["b_dongu_canli"] and s["calisan"], s
