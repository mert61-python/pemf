# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D1.E10 (DUZELTME-D1B §4 · NACK-D2 kökü) — manuel/batch/seans `command_id` aynı milisaniyede ÇAKIŞMAZ.

ÖLÇÜLEN KUSUR (1-B, `kayit/nack_d2*.jsonl`): kimlik `react_{bobin}_{int(time.time()*1000)}` (batch `react_batch_…`,
seans `sess_…`). Windows'ta `time.time()` çözünürlüğü başka uygulamaların isteğine göre 1–15,625 ms arası değişir; 64 Hz'e
yuvarlanınca aynı bobine iki hızlı start'ın (5–7 ms arayla) ~yarısı AYNI kimliği alıyordu (40'ta 20). `_register_ack`
ikinci kaydı birinciyi EZİYOR; start#1'in geciken NACK'i (`_resolve_ack(cid1, False)`) start#2'nin bekçisini uyandırıyor
→ bekçi#2 KENDİ (kabul edilmiş, çalışan) koşusunu kapatıyor ve operatöre "REDDEDİLDİ — bobin ÇALIŞMIYOR" deniyordu.
Kırmızılık makinenin o anki zamanlayıcısına bağlı olduğu için `test_nack_gorunurlugu::…D2_geciken_NACK…` "kararsız"
görünüyordu — gerçek bir ürün yarışının doğru sinyaliydi. E-stop kimliği bunu `_estop_sira` ekiyle çözmüştü.

YARIŞ KAPISI — zamanlama ZORLANIR, tek koşuma güvenilmez: süreç saati yalnız bu testlerde 64 Hz'e YUVARLANIR ve senaryo
40 KEZ koşulur; ölçüt "çakışma 0 ve yanlış kapanma 0" (önce-kırmızı ORAN olarak raporlanır). Seans kolunda saat
DONDURULUR (iki kimlik kesin aynı tikte).

Firmware tamponları (Ö.4-Y7: ESP kodu silinmez — yalnız ölçüldü): 8266 gelen kimlik `char[64]`, tekrar önbelleği
`char[48]`; S3 `SharedDefs.h` `command_id[36]` (35 karakter + NUL, fazlası KESİLİR → ack eşleşmez). Kimlikler ≤35 pinlenir.
"""

from __future__ import annotations

import math
import time as _time

import pytest
from fastapi.testclient import TestClient
from topoloji import ESP_BOBIN

DENEME = 40
S3_KIMLIK_AZAMI = 35


@pytest.fixture()
def ortam(monkeypatch):
    import servers.api_server as api
    from servers import coil_run_tracker as crt

    monkeypatch.setenv("PEMF_ESP_ENABLED", "1")  # ESP kod yolu (silinmez — Ö.4-Y7); yayın sahte
    bildirimler: list = []
    monkeypatch.setattr(api, "_push_notification", lambda msg, sev="info": bildirimler.append((msg, sev)))
    monkeypatch.setattr(api, "_ws_broadcast_sync", lambda m: None)
    monkeypatch.setattr(api, "_reconcile_esp_calisiyor", lambda *a, **k: None)
    monkeypatch.setattr(api, "_mqtt_publish", lambda topic, payload: True)
    monkeypatch.setattr(api, "_START_ACK_TIMEOUT", 2.0, raising=True)
    monkeypatch.setattr(crt, "_db_session_id_getter", lambda: 42)
    sayac = {"n": 0}

    class _DB:
        def start_coil_run(self, *a, **k):
            sayac["n"] += 1
            return 900 + sayac["n"]  # her start FARKLI run_id

        def finish_coil_run(self, *a, **k):
            return True

    monkeypatch.setattr(crt, "_treatment_db_getter", lambda: _DB())
    yield api, bildirimler
    with api._session_lock:
        api._active_session["is_active"] = False


@pytest.fixture()
def saat_64hz(monkeypatch):
    """Süreç saatini Windows varsayılan zamanlayıcı adımına (15,625 ms) yuvarlar — YALNIZ bu testte."""
    gercek = _time.time
    adim = 1.0 / 64
    monkeypatch.setattr(_time, "time", lambda: math.floor(gercek() / adim) * adim)


def _acik_run(api):
    with api._active_coil_runs_lock:
        return api._active_coil_runs.get(int(ESP_BOBIN))


def _bekleyen_kimlikler(api) -> set:
    with api._pending_acks_lock:
        return set(api._pending_acks.keys())


def _iki_hizli_start(api, c, yol: str):
    """Aynı bobine iki hızlı start; her start'ın kaydettiği ack kimliği döner (kayıt EZİLİRSE ikisi aynıdır)."""
    govde = {"start": True, "freq": 100, "duty": 50, "phase": 0, "duration": 60}
    kimlikler = []
    for duty in (50, 60):
        once = _bekleyen_kimlikler(api)
        if yol == "tekil":
            r = c.post(f"/api/coil/{ESP_BOBIN}/control", json={**govde, "duty": duty})
            kimlikler.append(r.json()["command_id"])
        else:
            r = c.post("/api/coil/batch", json={"coil_ids": [ESP_BOBIN], **govde, "duty": duty})
            yeni = _bekleyen_kimlikler(api) - once
            kimlikler.append(next(iter(yeni)) if yeni else kimlikler[-1])  # yeni kayıt yoksa ÖNCEKİNİ ezmiştir
        assert r.status_code == 200, r.text[:200]
    return kimlikler


@pytest.mark.parametrize("yol", ["tekil", "batch"])
def test_KRITIK_64Hz_saatte_iki_hizli_start_KIMLIK_CAKISMAZ_ve_geciken_NACK_kosu2yi_KAPATMAZ(ortam, saat_64hz, yol):
    api, _b = ortam
    c = TestClient(api.app)
    cakisma = kapanma = 0
    uzun: list = []
    for _ in range(DENEME):
        cid1, cid2 = _iki_hizli_start(api, c, yol)
        run2 = _acik_run(api)
        uzun += [k for k in (cid1, cid2) if len(k) > S3_KIMLIK_AZAMI]
        if cid1 == cid2:
            cakisma += 1
        api._resolve_ack(cid1, False)  # start#1'in GECİKEN NACK'i
        bitis = _time.monotonic() + 0.3
        while _time.monotonic() < bitis and _acik_run(api) == run2:
            _time.sleep(0.01)
        if _acik_run(api) != run2:
            kapanma += 1
        api._finish_coil_run(ESP_BOBIN)
        api._resolve_ack(cid2, True)  # bekçi#2'yi bitir (sonraki denemeye taşmasın)
    assert not uzun, f"S3 tamponuna (35) SIGMAYAN kimlik: {uzun[:3]}"
    assert cakisma == 0 and kapanma == 0, (
        f"{yol}: 64 Hz saatte {DENEME} denemede {cakisma} AYNI command_id, {kapanma} kez geciken NACK#1 KABUL edilmis "
        "kosu#2'yi KAPATTI ('REDDEDILDI — bobin CALISMIYOR' yanlis bildirimi)"
    )


def test_KRITIK_ayni_tikte_iki_seans_kimligi_FARKLI(ortam, monkeypatch):
    """Seans kimliği (`sess_…`): saat DONDURULUR (aynı tik kesin) — seans başlat, durdur, yeniden başlat."""
    api, _b = ortam
    monkeypatch.setattr(api, "_kayit_db_hazir", lambda: (True, ""))
    monkeypatch.setattr(api, "_broker_reachable", lambda: True)
    sabit = _time.time()
    monkeypatch.setattr(_time, "time", lambda: sabit)
    c = TestClient(api.app)
    govde = {"coil_ids": [ESP_BOBIN], "frequency": 100, "duty": 50, "phase": 0, "duration_minutes": 5, "mode": "Test"}
    kimlikler = []
    for _ in range(2):
        once = _bekleyen_kimlikler(api)
        r = c.post("/api/session/start", json=govde)
        assert r.status_code == 200, r.text[:200]
        yeni = _bekleyen_kimlikler(api) - once
        # Yeni kayıt görünmüyorsa kimlik ÖNCEKİYLE AYNIDIR (kayıt ezildi) — çakışmanın kendisi.
        kimlikler.append(next(iter(yeni)) if yeni else (kimlikler[-1] if kimlikler else None))
        c.post("/api/session/stop")
    assert kimlikler[0], f"aparat: ilk seans ack kaydi acilmadi {kimlikler}"
    assert kimlikler[0] != kimlikler[1], f"ayni tikte iki seans AYNI command_id aldi (ack kaydi ezildi): {kimlikler}"
    assert all(len(k) <= S3_KIMLIK_AZAMI for k in kimlikler), f"S3 tamponuna sigmayan seans kimligi: {kimlikler}"
    for k in kimlikler:
        api._resolve_ack(k, True)


def test_KRITIK_i6F4_DONMUS_saatte_1000_ardisik_kimlik_BENZERSIZ(monkeypatch):
    """1-C bağımsız inceleme i6-F-4 (kör kapı): yukarıdaki kollar yalnız ARDIŞIK İKİ kimliği karşılaştırır → sıra ekinin
    modülünü küçülten her mutant (`% 2`, `% 10` …) YEŞİL kalıyordu. `% 2` ölçülmüş GERÇEK bir gerilemedir: aynı tikte ÜÇ
    hızlı start'ta #1 ile #3 aynı kimliği alır ve geciken NACK#1 kabul edilmiş koşu#3'ü kapatır (D1.E10 kusurunun kendisi).
    Donmuş saatte 1000 ardışık kimlik BENZERSİZ olmalı (1000'den küçük her modül yakalanır) ve S3 tamponuna sığmalı."""
    import servers.api_server as api

    sabit = _time.time()
    monkeypatch.setattr(_time, "time", lambda: sabit)
    for on_ek in ("react", "react_batch", "sess"):
        kimlikler = [api._komut_kimligi(on_ek, ESP_BOBIN) for _ in range(1000)]
        assert len(set(kimlikler)) == 1000, f"{on_ek}: donmuş saatte 1000 kimlikten {len(set(kimlikler))} benzersiz"
        assert max(map(len, kimlikler)) <= S3_KIMLIK_AZAMI, f"{on_ek}: S3 tamponuna sığmayan kimlik"
