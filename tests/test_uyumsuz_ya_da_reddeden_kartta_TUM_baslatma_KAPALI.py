# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D1.52 · B-1.4 — firmware UYUMSUZ ya da kart SİSTEMATİK REDDEDİYORKEN tüm BAŞLATMA yolları kapalı; STOP kapısız.

ÖLÇÜLEN KUSUR (plan probe_f12): firmware-uyum (`stm_uyumlu is False`) ve sistematik-NACK (`stm_komutlari_reddediyor`)
kapıları yalnız `/api/session/start`'ta (ve AI Pro başlatmasında) vardı. `HardwareController._stm_surus_hazir` yalnız
BAĞLANTIYA bakıyordu → tekil `/api/coil/{id}/control`, `/api/coil/batch` ve `/api/hardware/command` start_coil /
start_all_coils (ve aynı yardımcıyı kullanan AI (Auto)) 200 "success" dönüyor, tekil ve batch KOŞU KAYDI da açıyordu —
kart paketi reddederken (gösterilen/kaydedilen ≠ uygulanan). İki kaynak yorum (ai_router "start_all_coils reddi …
firmware uyuşmaz", api_server `_start_stm_coils` "kart kopuk · firmware/CRC uyuşmaz") bu reddin VAR olduğunu iddia
ediyordu.

Kapı GERÇEK `HardwareController` (`kayitci_donanim.gercek_hc`: kuyruğa giden her paket firmware aynasıyla çözülür) ve
GERÇEK uçlarla koşar; ölçüt HTTP değil KUYRUKTAKİ PAKET + bobin durumu. İki engel kolu: kesin firmware uyumsuzluğu ve
GERÇEK `stm_komut_reddi_bildir`'e SABİT 3 NACK. KARŞIT: aynı engelde STOP / ACİL DURDUR yolları çalışır (Ö.4-Y8).
"""

from __future__ import annotations

import pytest
from topoloji import TUM_STM

_UCLAR = sorted({min(TUM_STM), max(TUM_STM)})
_SURUS = {"freq": 100, "duty": 30, "phase": 0}


@pytest.fixture(params=["uyumsuz_firmware", "sistematik_NACK"])
def engel(request, monkeypatch):
    from kayitci_donanim import gercek_hc
    from servers import api_server as api
    from servers import live_state as ls

    monkeypatch.setattr(api, "_mqtt_publish", lambda topic, payload: False)  # ESP konu dışı; ack bekçisi doğmaz
    monkeypatch.setitem(api._active_session, "is_active", False)
    ls.stm_komut_kabulu_bildir()
    with gercek_hc() as hc:
        monkeypatch.setattr(api.state, "hardware", hc)
        monkeypatch.setattr(api.state, "core", hc.core)
        if request.param == "uyumsuz_firmware":
            hc.core.stm_uyumlu = False
            hc.core.stm_uyumsuzluk_sebebi = "test: 5-ch firmware, 7-ch paket"
        else:
            for _ in range(3):  # SABİT 3 (eşik kaynaktan okunmaz — D1.50)
                ls.stm_komut_reddi_bildir("STM_NACK: CRC")
            assert ls.stm_komutlari_reddediyor(), "aparat: sistematik red kurulamadi"
        try:
            yield api, hc
        finally:
            ls.stm_komut_kabulu_bildir()


def _surus_paketleri(hc) -> list:
    from kayitci_donanim import paket_coz

    return [p for p in hc.core._hw_send_queue.paketler if any(d > 0 for d in paket_coz(p)[0])]


def test_KRITIK_engelde_TUM_baslatma_yollari_REDDEDILIR_ve_donanima_SURUS_GITMEZ(engel):
    from fastapi.testclient import TestClient

    api, hc = engel
    c = TestClient(api.app)
    basarili: list[str] = []
    for b in _UCLAR:
        r = c.post(f"/api/coil/{b}/control", json={"start": True, "duration": 60, **_SURUS})
        if r.status_code < 400 and r.json().get("status") == "success":
            basarili.append(f"/api/coil/{b}/control")
        r = c.post(
            "/api/hardware/command",
            json={"command": "start_coil", "params": {"coil_id": b, "duration": 1, **_SURUS}},
        )
        if r.status_code < 400 and r.json().get("status") == "success":
            basarili.append(f"hardware/command start_coil {b}")
    r = c.post("/api/coil/batch", json={"coil_ids": _UCLAR, "start": True, "duration": 60, **_SURUS})
    basarili += [f"batch {x['coilId']}" for x in r.json().get("results", []) if x.get("status") == "success"]
    r = c.post("/api/hardware/command", json={"command": "start_all_coils", "params": {"duration": 1, **_SURUS}})
    if r.status_code < 400 and r.json().get("status") == "success":
        basarili.append("hardware/command start_all_coils")
    # AI (Auto) aynı yardımcıyı (`start_all_coils`) kullanır → doğrudan çağrıyla da ölçülür.
    if hc.start_all_coils(100.0, 30.0, 0.0, 1):
        basarili.append("HardwareController.start_all_coils (AI Auto yolu)")

    assert not basarili, f"engel varken BASLATMA 'basarili' dondu: {basarili}"
    assert not _surus_paketleri(hc), "engel varken donanim kuyruguna duty>0 paket GITTI"
    assert not any(s["is_running"] for s in hc.coils_state.values()), "reddedilen START bobin durumunu YAZDI"


def test_KARSIT_ayni_engelde_STOP_ve_ACIL_DURDUR_CALISIR(engel):
    """Ö.4-Y8: kapı YALNIZ başlatmadadır. Uyumsuz/reddeden kartta durduramamak asıl tehlike olurdu."""
    from fastapi.testclient import TestClient
    from kayitci_donanim import paket_coz

    api, hc = engel
    c = TestClient(api.app)
    oncesi = len(hc.core._hw_send_queue.paketler)
    for b in _UCLAR:
        r = c.post(f"/api/coil/{b}/control", json={"start": False, **_SURUS})
        assert r.status_code == 200 and r.json().get("status") == "success", f"tekil STOP {b}: {r.status_code} {r.text}"
        r = c.post("/api/hardware/command", json={"command": "stop_coil", "params": {"coil_id": b}})
        assert r.status_code == 200 and r.json().get("status") == "success", f"stop_coil {b}: {r.text}"
    r = c.post("/api/coil/batch", json={"coil_ids": _UCLAR, "start": False, **_SURUS})
    assert all(x.get("status") == "success" for x in r.json()["results"]), f"batch STOP: {r.json()}"
    r = c.post("/api/hardware/command", json={"command": "stop_all_coils", "params": {}})
    assert r.status_code == 200 and r.json().get("status") == "success", f"stop_all_coils: {r.text}"
    r = c.post("/api/hardware/emergency_stop")
    assert r.status_code == 200, f"ACIL DURDUR {r.status_code} — E-stop hicbir kosulda reddedilmez"
    assert hc.stop_all_cagri >= 2, "ACIL DURDUR / stop_all_coils donanima STOP vermedi"
    yeni = hc.core._hw_send_queue.paketler[oncesi:]
    assert yeni and all(all(d == 0.0 for d in paket_coz(p)[0]) for p in yeni), "STOP yollari tum-sifir paket uretmedi"


def test_KARSIT_uyum_BILINMIYORKEN_ve_red_YOKKEN_baslatma_ENGELLENMEZ(monkeypatch):
    """Banner tanınmadıysa (`stm_uyumlu is None`) başlatma ENGELLENMEZ — tanınmayan ama uyumlu bir firmware çalışan
    kliniği durdurmasın (kayıtlı karar, `headless_core._stm_kimligini_isle`). Kapı "her şeyi reddet"e dönmesin."""
    from fastapi.testclient import TestClient
    from kayitci_donanim import gercek_hc
    from servers import api_server as api
    from servers import live_state as ls

    monkeypatch.setattr(api, "_mqtt_publish", lambda topic, payload: False)
    ls.stm_komut_kabulu_bildir()
    # Koşu kaydı bu kapının konusu değil; kayıtçı (gerçek tedavi DB'sine satır yazılmasın).
    kosular: list = []
    monkeypatch.setattr(api, "_begin_coil_run", lambda *a, **k: kosular.append(a))
    monkeypatch.setattr(api, "_finish_coil_run", lambda *a, **k: None)
    with gercek_hc() as hc:
        monkeypatch.setattr(api.state, "hardware", hc)
        monkeypatch.setattr(api.state, "core", hc.core)
        hc.core.stm_uyumlu = None
        b = _UCLAR[0]
        r = TestClient(api.app).post(f"/api/coil/{b}/control", json={"start": True, "duration": 60, **_SURUS})
        assert r.json().get("status") == "success", f"engel YOKKEN baslatma reddedildi: {r.text}"
        assert _surus_paketleri(hc), "engel yokken donanima surus paketi gitmedi"
        assert kosular, "engel yokken kabul edilen baslatma kosu kaydi acmadi"
        r = TestClient(api.app).post(f"/api/coil/{b}/control", json={"start": False, **_SURUS})
        assert r.json().get("status") == "success"
