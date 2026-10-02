# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D1.E10 · 1-C bağımsız inceleme i6-F-2 / F-3 / F-4 — geciken NACK yalnız KENDİ koşusunu kapatır, devralınmış komutun
NACK'i "bobin ÇALIŞMIYOR" demez (GERÇEK uçlar, sahte yayın, sahte DB; bekçi zaman aşımı GERÇEK sözleşme 2,0 sn).

D1.E10'un iddiası: "geciken NACK kabul edilmiş koşuyu KAPATMAZ"; kusurun operatöre yüzü "REDDEDİLDİ — bobin ÇALIŞMIYOR"
yanlış bildirimiydi. i6 bunu kimlik ÇAKIŞMASI DIŞINDAKİ yollardan çürüttü (ölçüldü):
  F-2 START koşu AÇMADIYSA (seanssız tekil START; DB hıçkırığında `start_coil_run` None) bekçi `run_id=None` alıyor ve
      NACK'te `_finish_coil_run(bobin, only_run_id=None)` = KOŞULSUZ kapat → o an açık OLAN (başka START'ın) koşusu kapanıyordu.
  F-3 kimlikler çakışmasa da geciken NACK#1, KABUL edilmiş start#2 sürerken "REDDEDİLDİ — bobin ÇALIŞMIYOR; koşu kaydı
      düzeltildi" `error` bildirimi üretiyordu (bobin çalışıyor; hiçbir kayıt düzeltilmedi).
  F-4 (kör kapı) kapı yalnız ARDIŞIK İKİ kimliği kıyaslıyordu — aynı tikte ÜÇ start (`% 2` mutantı #1 = #3).
DÜZELTME: koşu açmamış START hiçbir koşuyu kapatmaz; bobin başına SON ack-kayıtlı START kimliği tutulur — devralınmış
komutun NACK'i koşu kapatmaz, `warning` düzeyinde "önceki start reddedildi — sonraki komut geçerli" der.
"""

from __future__ import annotations

import time as _time
import types

import pytest
from fastapi.testclient import TestClient
from topoloji import ESP_BOBIN

GOVDE = {"start": True, "freq": 100, "duty": 50, "phase": 0, "duration": 60}


@pytest.fixture()
def ortam(monkeypatch):
    import servers.api_server as api
    from servers import coil_run_tracker as crt

    monkeypatch.setenv("PEMF_ESP_ENABLED", "1")
    bildirimler: list = []
    ws: list = []
    monkeypatch.setattr(api, "_push_notification", lambda msg, sev="info": bildirimler.append((msg, sev)))
    monkeypatch.setattr(api, "_ws_broadcast_sync", lambda m: ws.append(m))
    monkeypatch.setattr(api, "_reconcile_esp_calisiyor", lambda *a, **k: None)
    monkeypatch.setattr(api, "_mqtt_publish", lambda topic, payload: True)
    monkeypatch.setattr(api, "_START_ACK_TIMEOUT", 2.0, raising=True)  # GERCEK sozlesme
    monkeypatch.setattr(api, "_RL_REMOTE_MAX", 0, raising=True)  # testclient yerel sayilmaz → 429 olmasin
    monkeypatch.setattr(api, "_kayit_db_hazir", lambda: (True, ""))
    monkeypatch.setattr(api, "_broker_reachable", lambda: True)
    sid = {"v": 42}
    monkeypatch.setattr(crt, "_db_session_id_getter", lambda: sid["v"])
    sayac = {"n": 0}
    basarisiz: set = set()

    class _DB:
        def start_coil_run(self, *a, **k):
            sayac["n"] += 1
            return None if sayac["n"] in basarisiz else 900 + sayac["n"]

        def end_coil_run(self, *a, **k):
            return True

        def finish_coil_run(self, *a, **k):
            return True

    monkeypatch.setattr(crt, "_treatment_db_getter", lambda: _DB())
    yield types.SimpleNamespace(api=api, bildirimler=bildirimler, ws=ws, sid=sid, basarisiz=basarisiz)
    # Test hijyeni: ESP bobininin koşu kaydı ve gerçek seansın DB kimliği sonraki teste SIZMAZ (sızan `db_session_id`
    # ile sonraki testin başarılı START'ı koşu açıp kapatmıyordu → `test_esp_freq_clamp` nöbeti 11 hata).
    api._finish_coil_run(int(ESP_BOBIN))
    with api._session_lock:
        api._active_session["is_active"] = False
        api._active_session.pop("db_session_id", None)


def _acik_run(api):
    with api._active_coil_runs_lock:
        return api._active_coil_runs.get(int(ESP_BOBIN))


def _bekleyen(api) -> set:
    with api._pending_acks_lock:
        return set(api._pending_acks.keys())


def _bekle(kosul, saniye: float) -> bool:
    son = _time.monotonic() + saniye
    while _time.monotonic() < son:
        if kosul():
            return True
        _time.sleep(0.01)
    return kosul()


def _calismiyor_bildirimleri(bildirimler) -> list:
    return [(m, s) for m, s in bildirimler if s == "error" and str(ESP_BOBIN) in m and "REDDED" in m]


# ── MERCEK 3: kapi yalniz ARDISIK IKI kimligi kiyaslar; ayni tikte UC start ────────────────────────────────────────
@pytest.mark.parametrize("deneme", range(5))
def test_KRITIK_i6F4_ayni_tikte_UC_hizli_start_kimlikleri_FARKLI_ve_gec_NACK1_kosu3u_KAPATMAZ(
    ortam, monkeypatch, deneme
):
    api = ortam.api
    sabit = _time.time()
    monkeypatch.setattr(_time, "time", lambda: sabit)  # saat DONDURULUR: uc start kesin ayni tik
    c = TestClient(api.app)
    kimlikler = []
    for duty in (50, 55, 60):
        r = c.post(f"/api/coil/{ESP_BOBIN}/control", json={**GOVDE, "duty": duty})
        assert r.status_code == 200, r.text[:200]
        kimlikler.append(r.json()["command_id"])
    run3 = _acik_run(api)
    assert run3 is not None
    api._resolve_ack(kimlikler[0], False)  # start#1'in GECIKEN NACK'i
    _bekle(lambda: _acik_run(api) != run3, 0.3)
    kapandi = _acik_run(api) != run3
    api._finish_coil_run(ESP_BOBIN)
    for k in kimlikler:
        api._resolve_ack(k, True)
    assert len(set(kimlikler)) == 3, f"ayni tikte uc start: kimlik CAKISTI {kimlikler}"
    assert not kapandi, f"geciken NACK#1 KABUL edilmis kosu#3'u ({run3}) KAPATTI — kimlikler {kimlikler}"


# ── MERCEK 2: kimlik cakismasi YOKKEN de yanlis bildirim ──────────────────────────────────────────────────────────
def test_KRITIK_i6F3_gec_NACK1_kabul_edilmis_kosu2_SURERKEN_REDDEDILDI_CALISMIYOR_demez(ortam):
    api = ortam.api
    c = TestClient(api.app)
    r1 = c.post(f"/api/coil/{ESP_BOBIN}/control", json={**GOVDE, "duty": 50})
    r2 = c.post(f"/api/coil/{ESP_BOBIN}/control", json={**GOVDE, "duty": 60})
    assert r1.status_code == r2.status_code == 200
    cid1, cid2 = r1.json()["command_id"], r2.json()["command_id"]
    assert cid1 != cid2  # D1.E10 sonrasi
    run2 = _acik_run(api)
    once = len(ortam.bildirimler)
    api._resolve_ack(cid1, False)  # start#1'in GECIKEN NACK'i (start#2 KABUL edilmis, calisiyor)
    _bekle(lambda: len(_calismiyor_bildirimleri(ortam.bildirimler[once:])) > 0, 1.0)
    yanlis = _calismiyor_bildirimleri(ortam.bildirimler[once:])
    kosu2_acik = _acik_run(api) == run2
    nack_ws = [m for m in ortam.ws if m.get("type") == "coil_ack" and m.get("data", {}).get("commandId") == cid1]
    api._resolve_ack(cid2, True)
    api._finish_coil_run(ESP_BOBIN)
    assert kosu2_acik, "D1.E10 sozlesmesi bozuldu: geciken NACK#1 kosu#2'yi kapatti"
    assert not yanlis, (
        f"kosu#2 ACIK ve bobin start#2 ile CALISIYOR, ama geciken NACK#1 operatore 'error' bildirimi uretti: {yanlis} "
        f"(WS coil_ack ok=False commandId=cid1: {len(nack_ws)} adet)"
    )


def test_KRITIK_i6F2_SEANSSIZ_tekil_START_in_gec_NACK_i_arada_ACILAN_SEANSIN_kosusunu_KAPATMAZ(ortam):
    """run_id=None yolu: seanssiz tekil START'ta `_begin_coil_run` kosu ACMAZ (db_session_id yok) → bekci#1
    `run_id=None` alir → NACK'te `_finish_coil_run(bobin, only_run_id=None)` = KOSULSUZ kapat (D2 korumasi devre disi)."""
    api = ortam.api
    c = TestClient(api.app)
    ortam.sid["v"] = None  # aktif seans yok
    t0 = _time.monotonic()
    r1 = c.post(f"/api/coil/{ESP_BOBIN}/control", json=GOVDE)
    assert r1.status_code == 200, r1.text[:200]
    cid1 = r1.json()["command_id"]
    assert _acik_run(api) is None, "aparat: seanssiz tekil START kosu acmamaliydi"
    ortam.sid["v"] = 42  # operator seansi baslatir (DB satiri acildi)
    once = _bekleyen(api)
    r = c.post(
        "/api/session/start",
        json={"coil_ids": [ESP_BOBIN], "frequency": 100, "duty": 50, "phase": 0, "duration_minutes": 5, "mode": "Test"},
    )
    assert r.status_code == 200, r.text[:300]
    run_s = _acik_run(api)
    sess_kimlik = sorted(_bekleyen(api) - once)
    gecen = _time.monotonic() - t0
    assert run_s is not None, "aparat: seans ESP kosusu acilmadi"
    assert cid1 in _bekleyen(api), f"aparat: bekci#1 penceresi kapanmis (gecen {gecen:.3f} sn)"
    api._resolve_ack(cid1, False)  # tekil start#1'in GECIKEN NACK'i (bekci#1 penceresi icinde)
    _bekle(lambda: _acik_run(api) != run_s, 0.5)
    kapandi = _acik_run(api) != run_s
    yanlis = _calismiyor_bildirimleri(ortam.bildirimler)
    for k in sess_kimlik:
        api._resolve_ack(k, True)
    api._finish_coil_run(ESP_BOBIN)
    assert not kapandi, (
        f"seanssiz tekil START'in geciken NACK'i ({gecen:.3f} sn sonra, bekci 2.0 sn penceresinde) arada acilan SEANSIN "
        f"KABUL edilmis ESP kosusunu ({run_s}) KAPATTI; bildirim: {yanlis}"
    )


def test_KRITIK_i6F2_DB_hickirigi_run_id_None_gec_NACK1_kosu2yi_KAPATMAZ(ortam):
    """Ayni delik seans icinde: start#1'de `start_coil_run` None doner (DB hickirigi) → bekci#1 run_id=None."""
    api = ortam.api
    ortam.basarisiz.add(1)
    c = TestClient(api.app)
    r1 = c.post(f"/api/coil/{ESP_BOBIN}/control", json={**GOVDE, "duty": 50})
    r2 = c.post(f"/api/coil/{ESP_BOBIN}/control", json={**GOVDE, "duty": 60})
    assert r1.status_code == r2.status_code == 200
    cid1, cid2 = r1.json()["command_id"], r2.json()["command_id"]
    run2 = _acik_run(api)
    assert run2 is not None
    api._resolve_ack(cid1, False)
    _bekle(lambda: _acik_run(api) != run2, 0.5)
    kapandi = _acik_run(api) != run2
    api._resolve_ack(cid2, True)
    api._finish_coil_run(ESP_BOBIN)
    assert not kapandi, f"run_id=None bekcisi (start#1) geciken NACK'te KABUL edilmis kosu#2'yi ({run2}) KAPATTI"


def test_KARSIT_ack_kayitsiz_yol_NACK_i_NO_OP(ortam):
    """MERCEK 2 (belge): ack kaydi ACILMAYAN yollar (aiauto_/aipro_/ai_stop_/stop_/stale_/reconcile_/estopcloud_/
    service_stop_/startup_reconcile_) icin gelen NACK `_resolve_ack`ta hicbir sey yapmaz (kayit yok)."""
    api = ortam.api
    run_once = _acik_run(api)
    bekleyen_once = _bekleyen(api)
    for cid in (
        f"aiauto_{ESP_BOBIN}_1790000000000",
        f"stop_{ESP_BOBIN}_1790000000000",
        f"startup_reconcile_{ESP_BOBIN}",
    ):
        api._resolve_ack(cid, False)
    _time.sleep(0.1)
    assert _bekleyen(api) == bekleyen_once and _acik_run(api) == run_once and not ortam.bildirimler


def test_KARSIT_GUNCEL_startin_NACK_i_kosuyu_KAPATIR_ve_REDDEDILDI_der(ortam):
    """Aşırı bastırma yok: NACK'lenen START bobinin GÜNCEL (son) START'ıysa koşu hayalettir — kapanır ve operatöre
    "REDDEDİLDİ — bobin ÇALIŞMIYOR" `error` bildirimi gider (düzeltme yalnız devralınmış komutu ayırır)."""
    api = ortam.api
    c = TestClient(api.app)
    r = c.post(f"/api/coil/{ESP_BOBIN}/control", json=GOVDE)
    assert r.status_code == 200, r.text[:200]
    run = _acik_run(api)
    assert run is not None, "aparat: START koşu açmadı"
    api._resolve_ack(r.json()["command_id"], False)
    kapandi = _bekle(lambda: _acik_run(api) != run, 1.0)
    hata = _bekle(lambda: bool(_calismiyor_bildirimleri(ortam.bildirimler)), 1.0)
    api._finish_coil_run(ESP_BOBIN)
    assert kapandi, f"GÜNCEL START'ın NACK'i hayalet koşuyu ({run}) KAPATMADI"
    assert hata, f"GÜNCEL START'ın NACK'i operatöre 'REDDEDİLDİ' demedi: {ortam.bildirimler}"
