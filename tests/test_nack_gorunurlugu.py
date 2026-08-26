# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""NACK GÖRÜNÜRLÜĞÜ — 2. tur denetimi bulgu [4.5]'in AÇIK YARISI (kapanış 2026-08-22).

ÖLÇÜLEN DURUM: [4.5]'in teslim/kabul yarısı 8. partide kapandı (koşu kaydı yalnız doğrulanmış
publish'te açılıyor). Ama "doğrulanmış publish" yalnız BROKER'ın kabulüdür — ESP'nin kendisi
komutu ÜÇ yerde açıkça REDDEDEBİLİR (8266 .ino:458 rate-limit, :527 validation, :605 unknown;
her seferinde `sendCommandAck(id, false)` + `command_error` eventi yayınlar) ve backend'de:
  · `command_error` eventi HİÇ işlenmiyordu (events dalında eşleşme yok) → operatör reddi ve
    SEBEBİNİ hiç görmüyordu;
  · ack'in success=false hâli yalnız E-stop bekçisinde okunuyordu → manuel start NACK'lense
    bile tedavi geçmişindeki koşu kaydı "koştu" olarak AÇIK kalıyordu (hayalet kayıt, [4.5]'in
    düzeltmeye çalıştığı şeyin ta kendisi — bir katman ötede).

SÖZLEŞME (üç parça):
  1. `command_error` eventi bildirilir (error) + WS'e yayınlanır — SEBEP metni operatöre taşınır.
     RETAINED filtresi korunur (bayat red, yeniden bağlanmada alarm üretmez).
  2. Manuel ESP start'ı ack-bekçisine bağlanır: NACK (success=false) gelirse koşu kaydı KAPANIR
     (bobin hiç başlamadı — kayıt hayalet) + operatör uyarılır.
  3. Ack TIMEOUT'unda kayıt KALIR: ack QoS-0'dır ve kaybolabilir; onaysızlıkta kaydı kapatmak,
     gerçekten çalışan bobinin dozunu kayıttan silmek olurdu (yanlış yönde hata). Timeout yalnız
     uyarı üretir.

⚠️ BU İŞ GÜVENLİK LİMİTİ İŞİ DEĞİLDİR: backend'e freq/duty clamp'i EKLENMEZ (sahip kararı,
pemf-production-readiness — geri ekleme YASAK). Yalnız görünürlük + kayıt doğruluğu.
"""

from __future__ import annotations

import json
import time as _time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

KOK = Path(__file__).resolve().parents[1]


@pytest.fixture()
def api(monkeypatch):
    import servers.api_server as api

    bildirimler: list = []
    ws: list = []
    monkeypatch.setattr(api, "_push_notification", lambda msg, sev="info": bildirimler.append((msg, sev)))
    monkeypatch.setattr(api, "_ws_broadcast_sync", lambda m: ws.append(m))
    monkeypatch.setattr(api, "_reconcile_esp_calisiyor", lambda *a, **k: None)
    return api, bildirimler, ws


def _olay(api, coil_id: int, event_type: str, message: str = "", retain: bool = False):
    class _Msg:
        pass

    m = _Msg()
    m.topic = f"pemf/coil/{coil_id}/events"
    m.retain = retain
    m.payload = json.dumps({"coil_id": coil_id, "event_type": event_type, "message": message, "timestamp": 1}).encode(
        "utf-8"
    )
    api._on_mqtt_message_api(None, None, m)


# ── 1) command_error EVENTİ görünür ──────────────────────────────────────────────


def test_KRITIK_command_error_operatore_SEBEBIYLE_bildirilir(api):
    api, bildirimler, ws = api
    _olay(api, 6, "command_error", "Command validation failed: freq out of range")

    assert bildirimler, (
        "command_error olayı operatöre HİÇ bildirilmedi — ESP'nin açık reddi görünmez, "
        "bobin 'çalışıyor' sanılır (bulgu [4.5] NACK yarısı)"
    )
    mesaj, sev = bildirimler[0]
    assert "6" in mesaj, f"hangi bobinin reddettiği belirsiz: {mesaj!r}"
    assert "freq out of range" in mesaj, f"firmware'in RED SEBEBİ operatöre taşınmadı: {mesaj!r}"
    assert sev == "error"
    assert any(m.get("type") == "command_error" for m in ws), "WS'e command_error yayınlanmadı"


def test_KARSIT_KANIT_RETAINED_command_error_alarm_URETMEZ(api):
    """D-4 filtresi bu olay tipi için de korunmalı: bayat red, reconnect'te alarm üretmez."""
    api, bildirimler, ws = api
    _olay(api, 6, "command_error", "Rate limit exceeded", retain=True)
    assert not bildirimler and not ws, "retained command_error işlendi — bayat red alarm üretti"


# ── 2+3) Manuel start ack-bekçisi ────────────────────────────────────────────────


@pytest.fixture()
def istemci(api, monkeypatch):
    api_mod, bildirimler, ws = api
    monkeypatch.setattr(api_mod, "_mqtt_publish", lambda topic, payload: True)
    # Bekçi timeout'u testte kısa (gerçek değer 2.0 sn — sözleşme ayrı testte kilitli).
    monkeypatch.setattr(api_mod, "_START_ACK_TIMEOUT", 0.3, raising=True)
    yield TestClient(api_mod.app), api_mod, bildirimler
    # TEARDOWN: seans testleri `_active_session`i acik birakabilir (koşu kaydini kapatir ama seansi
    # degil) → sonraki seans testleri "Zaten aktif seans" (409) alir. Global durumu temizle
    # (test izolasyonu; `_active_session` modul-genel).
    with api_mod._session_lock:
        api_mod._active_session["is_active"] = False


def _acik_run_var(api, coil_id: int) -> bool:
    with api._active_coil_runs_lock:
        return int(coil_id) in api._active_coil_runs


def _bekle(kosul, saniye=2.0):
    son = _time.time() + saniye
    while _time.time() < son:
        if kosul():
            return True
        _time.sleep(0.02)
    return kosul()


def test_KRITIK_manuel_start_NACK_inde_kosu_kaydi_KAPANIR(istemci, monkeypatch):
    client, api, bildirimler = istemci
    # Aktif seans olmadan _begin_coil_run no-op olur → run-map'i doğrudan gözlemlemek için
    # sahte seans kimliği enjekte et (coil_run_tracker injection noktası).
    from servers import coil_run_tracker as crt

    monkeypatch.setattr(crt, "_db_session_id_getter", lambda: 42)

    class _DB:  # gercek arayuz: coil_run_tracker start_coil_run/finish_coil_run cagirir
        def start_coil_run(self, *a, **k):
            return 777

        def finish_coil_run(self, *a, **k):
            return True

    monkeypatch.setattr(crt, "_treatment_db_getter", lambda: _DB())

    r = client.post("/api/coil/6/control", json={"start": True, "freq": 100, "duty": 50, "phase": 0, "duration": 60})
    assert r.status_code == 200
    cid = r.json()["command_id"]
    assert _acik_run_var(api, 6), "publish dogrulandi → kosu kaydi acilmali (mevcut [4.5] davranisi)"

    # ESP NACK'ler (firmware sendCommandAck(id, false) → backend _resolve_ack)
    api._resolve_ack(cid, False)

    assert _bekle(lambda: not _acik_run_var(api, 6)), (
        "ESP start'ı REDDETTİ (NACK) ama koşu kaydı AÇIK kaldı — hiç koşmamış bobin tedavi "
        "geçmişine 'koştu' olarak girer (hayalet kayıt, bulgu [4.5])"
    )
    assert _bekle(lambda: any("6" in m and "redd" in m.lower() for m, s in bildirimler)), (
        f"NACK operatöre bildirilmedi: {bildirimler!r}"
    )


def test_KRITIK_ack_TIMEOUT_unda_kayit_KALIR_yalniz_uyari(istemci, monkeypatch):
    """Ack QoS-0 — kaybolabilir. Onaysızlıkta kaydı kapatmak, gerçekten çalışan bobinin dozunu
    kayıttan silmek olurdu. Timeout: kayıt KALIR + uyarı çıkar."""
    client, api, bildirimler = istemci
    from servers import coil_run_tracker as crt

    monkeypatch.setattr(crt, "_db_session_id_getter", lambda: 42)

    class _DB:
        def start_coil_run(self, *a, **k):
            return 778

        def finish_coil_run(self, *a, **k):
            return True

    monkeypatch.setattr(crt, "_treatment_db_getter", lambda: _DB())

    r = client.post("/api/coil/7/control", json={"start": True, "freq": 100, "duty": 50, "phase": 0, "duration": 60})
    assert r.status_code == 200
    # ack HİÇ gelmiyor → bekçi timeout'a düşer
    assert _bekle(lambda: any("7" in m and "onay" in m.lower() for m, s in bildirimler), saniye=3.0), (
        f"ack timeout'u operatöre uyarı üretmedi: {bildirimler!r}"
    )
    assert _acik_run_var(api, 7), "timeout'ta koşu kaydı KAPATILMIŞ — kayıp ack, gerçek koşuyu kayıttan siler"
    api._finish_coil_run(7)  # temizlik


def test_KARSIT_KANIT_basarili_ack_gurultu_URETMEZ(istemci, monkeypatch):
    client, api, bildirimler = istemci
    from servers import coil_run_tracker as crt

    monkeypatch.setattr(crt, "_db_session_id_getter", lambda: 42)

    class _DB:
        def start_coil_run(self, *a, **k):
            return 779

        def finish_coil_run(self, *a, **k):
            return True

    monkeypatch.setattr(crt, "_treatment_db_getter", lambda: _DB())

    r = client.post("/api/coil/8/control", json={"start": True, "freq": 100, "duty": 50, "phase": 0, "duration": 60})
    cid = r.json()["command_id"]
    api._resolve_ack(cid, True)
    _time.sleep(0.5)
    assert _acik_run_var(api, 8), "başarılı ack'te koşu kaydı kapanmamalı"
    # ⚠️ İZOLASYON: `_estop_ack_watch` ARKA PLAN thread'idir; süitteki BAŞKA testlerin acil-durdurma
    # çağrıları 2 sn sonra bu testin monkeypatch'li `_push_notification`'ına "acil durdurma ... GELMEDİ"
    # bildirimi sızdırabilir (api_server.py:1643). Bu test HİÇ E-stop tetiklemez → o bildirimler bu
    # testin start/ack yolundan GELEMEZ. Sözleşme "başarılı ack, start/ack yolundan hata gürültüsü
    # üretmez"; yabancı asenkron E-stop bekçi gürültüsünü dışla (start-yolu hatası hâlâ yakalanır).
    start_yolu_hatalari = [(m, s) for m, s in bildirimler if s == "error" and "acil durdurma" not in m]
    assert not start_yolu_hatalari, f"başarılı start'ta hata bildirimi: {start_yolu_hatalari!r}"
    api._finish_coil_run(8)  # temizlik


def test_KARSIT_KANIT_bekci_timeout_sozlesmesi_2_saniye():
    """Gerçek timeout 2.0 sn (E-stop bekçisiyle aynı) — sessizce kısalırsa yavaş WiFi'de her
    start sahte uyarı üretir (alarm yorgunluğu), uzarsa NACK düzeltmesi gecikir."""
    import servers.api_server as api

    assert getattr(api, "_START_ACK_TIMEOUT", None) == 2.0, (
        f"_START_ACK_TIMEOUT beklenen 2.0, bulunan: {getattr(api, '_START_ACK_TIMEOUT', None)!r}"
    )


def test_KRITIK_BATCH_start_NACK_inde_de_kayit_kapanir(istemci, monkeypatch):
    """Tekil yol duzeltilip batch unutulursa deponun 1 numarali deseni tekrarlanir
    (ayni kural, iki yuzey). Batch ESP satiri da ayni bekciye baglanmali."""
    client, api, bildirimler = istemci
    from servers import coil_run_tracker as crt

    monkeypatch.setattr(crt, "_db_session_id_getter", lambda: 42)

    class _DB:
        def start_coil_run(self, *a, **k):
            return 780

        def finish_coil_run(self, *a, **k):
            return True

    monkeypatch.setattr(crt, "_treatment_db_getter", lambda: _DB())

    r = client.post(
        "/api/coil/batch",
        json={"coil_ids": [6], "start": True, "freq": 100, "duty": 50, "phase": 0, "duration": 60},
    )
    assert r.status_code == 200
    satirlar = r.json().get("results") or []
    esp_satir = next((s for s in satirlar if s.get("coilId") == 6), None)
    assert esp_satir is not None, f"batch yaniti bobin 6 icermiyor: {satirlar!r}"
    assert _acik_run_var(api, 6), "batch publish dogrulandi → kosu kaydi acilmali"

    # command_id batch yanitinda satir-bazinda yoksa pending kayittan bul
    with api._pending_acks_lock:
        adaylar = list(api._pending_acks.keys())
    assert adaylar, "batch start pending-ack kaydi ACMADI — bekci hic baglanmamis (kismi duzeltme)"
    for cid in adaylar:
        api._resolve_ack(cid, False)

    assert _bekle(lambda: not _acik_run_var(api, 6)), (
        "BATCH start NACK'lendi ama kosu kaydi acik kaldi — tekil yol duzeltilmis, batch unutulmus"
    )


def test_KRITIK_SEANS_start_NACK_inde_de_kayit_kapanir(istemci, monkeypatch):
    """🔴 E1 (denetim 2026-08-24): 18. parti ack-mimarisi tekil+batch yollarina baglandi ama
    /api/session/start ESP dali DISARIDA kaldi (deponun 1 numarali deseni: ayni kural, UCUNCU yuzey).
    Termal-kilitli 8266 seans-start'i NACK'lerse hayalet kosu kaydi seans boyu acik kalir ve
    kapanista TAM SURELI muhurlenir → tedavi gecmisine hic kosmamis bobin 'kostu' yazilir.

    ⚠️ 8. parti bilincli karari KORUNUR: publish fire-and-forget (snappy start) + kosulsuz
    _begin_coil_run; bekci yalniz broker CANLIYKEN baglanir. Yani broker-olu yarisi DEGISMEZ; yalniz
    NACK yarisi kapanir (karsit-kanit asagida)."""
    client, api, bildirimler = istemci
    from servers import coil_run_tracker as crt

    monkeypatch.setattr(crt, "_db_session_id_getter", lambda: 42)

    class _DB:
        def start_coil_run(self, *a, **k):
            return 781

        def finish_coil_run(self, *a, **k):
            return True

    monkeypatch.setattr(crt, "_treatment_db_getter", lambda: _DB())
    monkeypatch.setattr(api, "_kayit_db_hazir", lambda: (True, ""))
    monkeypatch.setattr(api, "_broker_reachable", lambda: True)
    with api._session_lock:  # onceki testten sizan seansi temizle (test izolasyonu)
        api._active_session["is_active"] = False
    with api._pending_acks_lock:
        api._pending_acks.clear()

    r = client.post(
        "/api/session/start",
        json={
            "coil_ids": [6],
            "frequency": 100,
            "duty": 50,
            "phase": 0,
            "duration_minutes": 20,
            "intensity": 50,
            "mode": "Test",
        },
    )
    assert r.status_code == 200, r.text
    assert _acik_run_var(api, 6), "seans ESP bobini kosu kaydi acilmali (mevcut davranis)"

    with api._pending_acks_lock:
        adaylar = list(api._pending_acks.keys())
    assert adaylar, "seans start pending-ack kaydi ACMADI — bekci hic baglanmamis (E1: seans yolu ack-mimarisiz)"
    for cid in adaylar:
        api._resolve_ack(cid, False)

    assert _bekle(lambda: not _acik_run_var(api, 6)), (
        "SEANS start NACK'lendi ama kosu kaydi acik kaldi — tekil/batch duzeltilmis, seans yolu unutulmus (E1)"
    )
    assert _bekle(lambda: any("6" in m and "redd" in m.lower() for m, s in bildirimler)), (
        f"seans NACK operatore bildirilmedi: {bildirimler!r}"
    )


def test_KRITIK_D2_geciken_NACK_araya_giren_kosuyu_KAPATMAZ(istemci, monkeypatch):
    """🔴 D2 (denetim 2026-08-24): NACK bekçisi `_finish_coil_run(coil_id)` ile o an açık HANGİ run
    varsa kapatıyordu (command/run eşlemesi YOK). Aynı bobine hızlı çift-start'ta start#1'in GECİKEN
    NACK'i, araya giren KABUL edilmiş start#2'nin ÇALIŞAN koşusunu düşürüyordu (+ 'bobin çalışmıyor'
    yanlış bildirim). Bekçi YALNIZ kendi run'ını (başlatıldığı andaki run_id) hedeflemeli."""
    client, api, bildirimler = istemci
    from servers import coil_run_tracker as crt

    monkeypatch.setattr(crt, "_db_session_id_getter", lambda: 42)
    _sayac = {"n": 0}

    class _DB:
        def start_coil_run(self, *a, **k):
            _sayac["n"] += 1
            return 900 + _sayac["n"]  # her start FARKLI run_id (901, 902, ...)

        def finish_coil_run(self, *a, **k):
            return True

    monkeypatch.setattr(crt, "_treatment_db_getter", lambda: _DB())
    monkeypatch.setattr(api, "_START_ACK_TIMEOUT", 2.0, raising=True)

    # start#1 → run#1 (901); bekçi#1 başlar (run_id=901'i yakalamalı).
    r1 = client.post("/api/coil/6/control", json={"start": True, "freq": 100, "duty": 50, "phase": 0, "duration": 60})
    cid1 = r1.json()["command_id"]
    assert _acik_run_var(api, 6), "start#1 sonrası açık run olmalı"

    # start#2 → begin#2 run#1'i (normal) kapatır, run#2 (902) açar; bekçi#2 run_id=902 yakalar.
    r2 = client.post("/api/coil/6/control", json={"start": True, "freq": 100, "duty": 60, "phase": 0, "duration": 60})
    assert r2.status_code == 200
    assert _acik_run_var(api, 6), "start#2 sonrası açık run olmalı (run#2)"

    # start#1'in GECİKEN NACK'i gelir → bekçi#1 (run_id=901) yalnız 901'i hedefler; run#2 (902) KORUNMALI.
    api._resolve_ack(cid1, False)
    _time.sleep(0.3)
    assert _acik_run_var(api, 6), (
        "geciken NACK#1, araya giren KABUL edilmiş start#2'nin ÇALIŞAN koşusunu (run#2) düşürdü — "
        "bobin çalışıyor ama açık koşu kaydı yok, operatöre 'çalışmıyor' yanlış bildirimi (D2)"
    )
    api._finish_coil_run(6)  # temizlik


def test_KARSIT_KANIT_SEANS_broker_OLU_iken_bekci_baglanmaz(istemci, monkeypatch):
    """8. parti bilincli karari: broker oluyken seans ESP yolu snappy-start + `esp_unreachable`
    uyarisi. Bekci broker oluyken baglanMAZ — NACK gelemez zaten (publish gitmedi) ve gereksiz
    timeout WARN 'esp_unreachable' ile CIFT uyari uretirdi. Bu test broker-olu yarisini kilitler."""
    client, api, bildirimler = istemci
    from servers import coil_run_tracker as crt

    monkeypatch.setattr(crt, "_db_session_id_getter", lambda: 42)

    class _DB:
        def start_coil_run(self, *a, **k):
            return 782

        def finish_coil_run(self, *a, **k):
            return True

    monkeypatch.setattr(crt, "_treatment_db_getter", lambda: _DB())
    monkeypatch.setattr(api, "_kayit_db_hazir", lambda: (True, ""))
    monkeypatch.setattr(api, "_broker_reachable", lambda: False)  # BROKER OLU
    with api._session_lock:  # onceki testten sizan seansi temizle (test izolasyonu)
        api._active_session["is_active"] = False
    with api._pending_acks_lock:
        api._pending_acks.clear()

    r = client.post(
        "/api/session/start",
        json={
            "coil_ids": [7],
            "frequency": 100,
            "duty": 50,
            "phase": 0,
            "duration_minutes": 20,
            "intensity": 50,
            "mode": "Test",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json().get("esp_unreachable") is True, "broker olu → esp_unreachable uyarisi (8. parti) KORUNMALI"
    with api._pending_acks_lock:
        adaylar = list(api._pending_acks.keys())
    assert not adaylar, "broker OLUYKEN bekci baglandi — NACK gelemez, esp_unreachable ile cift-uyari (bilincli hayir)"
    api._finish_coil_run(7)  # temizlik (kosu kaydi seans yolunda kosulsuz acilir)
