# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D1.E06 (İG-5.16) — `/api/ai/pro/start` önce TÜM denetimleri yapar, onayı EN SON ve kilit altında tüketir;
başarısız başlatma globalleri DEĞİŞTİRMEZ.

ÖLÇÜLEN KUSUR (aday doğrulaması D0, ayrı süreç): onay kilitten ve denetimlerden ÖNCE tüketiliyordu —
  (b) döngü sürerken ikinci `/start` 200 "Already running" dönüp YENİ onayı yakıyordu (yeniden kullanım 428),
  (c) eşzamanlı iki `/start`'ta ikisi de tüketiliyordu,
  (d) STM sistematik redde 409 + onay YANDI + global süre başlamayan seansın değerine (2 → 7 dk) geçiyordu (İG-5.9'u
      besleyen bayat global).
Hekim onayı tek kullanımlık bir TEDAVİ kararıdır; başlamayan tedavi onu tüketmemeli. Y4: mandallıyken `/start` 409 ve
onay korunur.
"""

from __future__ import annotations

import threading

import ai_pro_aparati as ap
import pytest


@pytest.fixture
def o(monkeypatch, tmp_path):
    from kayitci_donanim import gercek_hc

    ns = ap.kur(monkeypatch, tmp_path)
    try:
        with gercek_hc() as hc:
            monkeypatch.setattr(ns.api.state, "hardware", hc)
            ns.hc = hc
            yield ns
    finally:
        ns.geri()


def _onay(sure_dk: int = 7, organ: int = 3, model: str = "kedi") -> str:
    from servers import ai_approval

    rec = ai_approval.create("ai_pro", {"organ_id": organ, "duration_minutes": sure_dk, "model": model})
    ai_approval.approve(rec["id"], "hekim@test.local")
    return rec["id"]


def _durum(pid: str) -> str:
    from servers import ai_approval

    return (ai_approval.get(pid) or {}).get("status")


def _globaller(air) -> tuple:
    return (air._ai_duration_min, air._ai_organ_id, air._ai_hedef_modeli)


def test_KRITIK_b_dongu_SURERKEN_ikinci_start_onayi_YAKMAZ(o):
    _pid1, r1 = ap.onayli_baslat(o, sure_dk=2)
    assert r1.status_code == 200 and r1.json().get("status") == "success", r1.text[:200]
    pid2 = _onay()
    r2 = o.c.post("/api/ai/pro/start", json={"proposal_id": pid2})
    assert r2.status_code == 200 and r2.json().get("message") == "Already running", r2.text[:200]
    assert _durum(pid2) == "approved", f"döngü sürerken reddedilen /start onayı YAKTI: {_durum(pid2)}"
    assert o.air._ai_duration_min == 2, f"reddedilen /start global süreyi değiştirdi: {o.air._ai_duration_min}"


def test_KRITIK_c_ESZAMANLI_iki_start_yalniz_BASLAYANIN_onayi_tuketilir(o):
    pids = [_onay(), _onay()]
    kapi = threading.Barrier(2)
    yanit: dict = {}

    def _baslat(pid):
        kapi.wait(5)
        yanit[pid] = o.c.post("/api/ai/pro/start", json={"proposal_id": pid})

    ts = [threading.Thread(target=_baslat, args=(p,), daemon=True) for p in pids]
    for t in ts:
        t.start()
    for t in ts:
        t.join(15)
    basladi = [p for p in pids if yanit[p].json().get("message") == "AI Pro Closed-Loop Started"]
    assert len(basladi) == 1, f"eşzamanlı iki /start'tan tam biri başlamalı: {[yanit[p].text[:80] for p in pids]}"
    digeri = [p for p in pids if p not in basladi][0]
    assert _durum(basladi[0]) == "consumed"
    assert _durum(digeri) == "approved", f"başlamayan eşzamanlı /start onayı YAKTI: {_durum(digeri)}"


def test_KRITIK_d_STM_RED_409_onay_KORUNUR_globaller_DEGISMEZ(o):
    from servers import live_state

    once = _globaller(o.air)
    for _ in range(live_state.STM_RED_ESIGI + 1):
        live_state.stm_komut_reddi_bildir("-> STM_NACK: CRC (test)")
    assert live_state.stm_komutlari_reddediyor(), "aparat: STM sistematik red durumu kurulamadı"
    pid = _onay(sure_dk=7, organ=3)
    r = o.c.post("/api/ai/pro/start", json={"proposal_id": pid})
    assert r.status_code == 409, f"STM sistematik redde /start {r.status_code}"
    assert _durum(pid) == "approved", f"STM reddiyle başlamayan /start onayı YAKTI: {_durum(pid)}"
    assert _globaller(o.air) == once, f"başarısız /start globalleri değiştirdi: {once} → {_globaller(o.air)}"
    assert o.air._ai_loop_active is False, "başarısız /start döngü bayrağını kirletti"


@pytest.mark.parametrize(
    "kurulum, beklenen",
    [
        ({"organ": 9, "model": "kedi"}, 422),  # kedi 0-6 dışı hedef
        ({"organ": 0, "model": "petri"}, 409),  # araştırma bayrağı kapalı
    ],
)
def test_KRITIK_dogrulamada_REDDEDILEN_start_onayi_YAKMAZ(o, kurulum, beklenen, monkeypatch):
    monkeypatch.delenv(o.air.ARASTIRMA_AIPRO_BAYRAGI, raising=False)
    once = _globaller(o.air)
    pid = _onay(organ=kurulum["organ"], model=kurulum["model"])
    r = o.c.post("/api/ai/pro/start", json={"proposal_id": pid})
    assert r.status_code == beklenen, r.text[:200]
    assert _durum(pid) == "approved", f"{beklenen} ile reddedilen /start onayı YAKTI: {_durum(pid)}"
    assert _globaller(o.air) == once, f"reddedilen /start globalleri değiştirdi: {once} → {_globaller(o.air)}"


def test_KRITIK_mandalliyken_start_409_onay_KORUNUR(o):
    o.api._emergency_stop_all("manual")
    pid = _onay()
    r = o.c.post("/api/ai/pro/start", json={"proposal_id": pid})
    assert r.status_code == 409, f"E-stop mandallıyken AI Pro /start {r.status_code} döndü: {r.text[:200]}"
    assert _durum(pid) == "approved", f"mandallıyken reddedilen /start onayı YAKTI: {_durum(pid)}"
    with o.api._session_lock:
        assert not o.api._active_session.get("is_active"), "mandallıyken AI Pro seansı açıldı"


def test_KARSIT_basarili_start_onayi_TUKETIR_ve_muhru_uygular(o):
    pid, r = ap.onayli_baslat(o, sure_dk=4, organ=2)
    assert r.status_code == 200 and r.json().get("status") == "success", r.text[:200]
    assert _durum(pid) == "consumed", "başarılı /start onayı tüketmedi (tek kullanımlık kural)"
    assert (o.air._ai_duration_min, o.air._ai_organ_id) == (4, 2), "mühür uygulanmadı"
    r2 = o.c.post("/api/ai/pro/start", json={"proposal_id": pid})
    assert r2.status_code in (200, 428)
    if r2.status_code == 200:
        assert r2.json().get("message") == "Already running"
