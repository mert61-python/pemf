# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D1.81 · B-5.3 · sahip kararı Y4 — ACİL DURDURMA MANDALLANIR: ayrı ve bilinçli "Sıfırla" olmadan HİÇBİR START geçmez.

SAHİP KARARI (SAHIP-CEVAPLARI.md Y4): "E-stop MANDALLANIR; operatörün ayrı ve bilinçli 'sıfırla' eylemi olmadan
hiçbir START kabul edilmez. Kapsam: elle başlatma, AI (Auto), AI Pro `/frame` döngüleri, mobil yol, hepsi.
Sıfırlama kendi başına yeniden başlatmaz; sıfırlamadan sonra yeni bir START ayrıca gerekir."
Ö.4-Y8: mandal YALNIZ START'ı reddeder — STOP ve acil durdurma hiçbir koşulda kapılanmaz.

ÖLÇÜLEN KUSUR (bugün): acil durdurmadan hemen sonra tekil / batch / seans / legacy `hardware/command` /
doğrudan `update_coil`-`start_all_coils` (AI yollarının çağırdığı) START'ları kabul ediliyor; mandal yok.

Kapı GERÇEK uçları ve GERÇEK `HardwareController`'ı (`kayitci_donanim.gercek_hc`) koşar; ölçüt HTTP kodu değil
DONANIMA GİDEN paket (firmware aynası çözücüsü) ve `coils_state`. Acil durdurma her KAYNAĞIYLA (`reason`) sınanır:
mandal yalnız elle basılan düğmeye bağlanırsa kapı kırmızıdır.
"""

from __future__ import annotations

import types

import pytest

# Y53 (sahip): ESP'nin aşırı-sıcaklık alarmı ARTIK acil durdurma kaynağı DEĞİL (yalnız kendi bobinini durdurur, mandal
# kurmaz — `test_Y53_esp_overtemp_alarmi_YALNIZ_bobin8i_durdurur.py`); diğer ESP alarmları (overcurrent) kaynak olarak kalır.
_E_STOP_KAYNAKLARI = [
    "manual",
    "stm_disconnected",
    "stm_komut_reddi",
    "stm_watchdog_timeout",
    "esp_alarm_8_overcurrent",
]
_SIFIRLA_YOLU = "/api/hardware/estop_mandali/sifirla"


def _mandal_modulu():
    try:
        from utils import estop_mandali
    except ImportError:  # önce-kırmızı: modül yok
        return None
    return estop_mandali


class _SahteAlanKaydi:
    def seans_basladi(self, *a, **k):
        return None

    def seans_bitti(self, *a, **k):
        return None


@pytest.fixture
def ortam(monkeypatch, tmp_path):
    from ai_pro_aparati import istemci  # eşzamanlı istek: Selector döngülü istemci (bkz. ISTEMCI_SECENEKLERI)
    from database.treatment_history_db import TreatmentHistoryDB
    from kayitci_donanim import gercek_hc
    from servers import api_server as api
    from servers import coil_run_tracker as crt
    from servers import live_state

    kok = tmp_path / "gecmis"
    kok.mkdir()
    db = TreatmentHistoryDB(kok)
    monkeypatch.setattr(api, "_get_treatment_db", lambda: db)
    monkeypatch.setattr(crt, "_treatment_db_getter", lambda: db)
    monkeypatch.setattr(api, "_kayit_db_hazir", lambda: (True, ""))
    bildirim: list = []
    monkeypatch.setattr(api, "_push_notification", lambda m, t="info": bildirim.append((m, t)))
    ws: list = []
    monkeypatch.setattr(api, "_ws_broadcast_sync", ws.append)
    monkeypatch.setattr(live_state, "_ws_broadcast_sync", ws.append)
    yayin: list = []

    def _yayin(topic, payload):
        yayin.append((topic, dict(payload)))
        return True

    gercek_yayin = api._mqtt_publish  # tek boğaz noktası kolu GERÇEK fonksiyonu sınar
    monkeypatch.setattr(api, "_mqtt_publish", _yayin)
    monkeypatch.setattr(api, "_estop_cloud_mirror", lambda *a, **k: None)
    monkeypatch.setattr(api, "_estop_ack_watch", lambda *a, **k: None)
    monkeypatch.setattr(api, "_start_ack_izle_arka_planda", lambda *a, **k: None)
    monkeypatch.setattr(api, "_broker_reachable", lambda timeout=0.3: True)
    monkeypatch.setattr(api, "_seans_alan", _SahteAlanKaydi())
    monkeypatch.setattr(api.state, "core", types.SimpleNamespace(stm_uyumlu=None))
    monkeypatch.setattr(api, "_RL_REMOTE_MAX", 0)  # "testclient" yerel sayılmaz; hız sınırı bu kapının konusu değil
    live_state.stm_komut_kabulu_bildir()
    m = _mandal_modulu()
    if m is not None:
        m.sifirla("test-izolasyon")
    with api._session_lock:
        eski_seans = dict(api._active_session)
        api._active_session["is_active"] = False
    try:
        with gercek_hc() as hc:
            monkeypatch.setattr(api.state, "hardware", hc)
            yield types.SimpleNamespace(
                api=api,
                hc=hc,
                c=istemci(api.app),
                yayin=yayin,
                ws=ws,
                bildirim=bildirim,
                db=db,
                ls=live_state,
                gercek_yayin=gercek_yayin,
            )
    finally:
        if m is not None:
            m.sifirla("test-izolasyon")
        with api._session_lock:
            api._active_session.clear()
            api._active_session.update(eski_seans)
        live_state.stm_komut_kabulu_bildir()


def _duty(paket) -> tuple:
    from kayitci_donanim import paket_coz

    return tuple(paket_coz(paket)[0])


def _surus_paketleri(o, once: int) -> list:
    """`once` indeksinden sonra donanıma giden ve EN AZ BİR bobini süren (duty>0) paketler."""
    return [_duty(p) for p in o.hc.core._hw_send_queue.paketler[once:] if any(d > 0 for d in _duty(p))]


def _estop(o, reason: str = "manual"):
    """GERÇEK acil durdurma; dönüşte paket indeksi (sonrası 'E-stop SONRASI' sayılır)."""
    o.api._emergency_stop_all(reason)
    return len(o.hc.core._hw_send_queue.paketler)


def _calisan(o) -> list:
    return [i for i, s in o.hc.coils_state.items() if s["is_running"]]


# ── her START yolu mandala takılır ────────────────────────────────────────────────────────────────
def test_KRITIK_estop_sonrasi_TEKIL_START_reddedilir(ortam):
    o = ortam
    sonra = _estop(o)
    r = o.c.post("/api/coil/1/control", json={"start": True, "freq": 100, "duty": 40, "phase": 0, "duration": 60})
    assert not _surus_paketleri(o, sonra), f"E-stop SONRASI tekil START donanımı sürdü: {_surus_paketleri(o, sonra)}"
    assert _calisan(o) == [], f"E-stop sonrası 'çalışıyor' bobin: {_calisan(o)}"
    assert r.status_code == 409, (
        f"mandallıyken tekil START {r.status_code} döndü (409 + 'Sıfırla' bekleniyor): {r.text[:200]}"
    )
    assert "Sıfırla" in r.json().get("detail", ""), f"409 metni eylemi söylemiyor: {r.text[:200]}"


def test_KRITIK_estop_sonrasi_BATCH_START_reddedilir(ortam):
    o = ortam
    sonra = _estop(o)
    o.c.post(
        "/api/coil/batch",
        json={"coil_ids": [1, 2, 3], "start": True, "freq": 100, "duty": 40, "phase": 0, "duration": 60},
    )
    assert not _surus_paketleri(o, sonra), f"E-stop SONRASI batch START donanımı sürdü: {_surus_paketleri(o, sonra)}"
    assert _calisan(o) == []


def test_KRITIK_estop_sonrasi_SEANS_START_reddedilir(ortam):
    o = ortam
    sonra = _estop(o)
    r = o.c.post(
        "/api/session/start",
        json={"coil_ids": [1, 2], "frequency": 100, "duty": 40, "phase": 0, "duration_minutes": 5, "mode": "Manuel"},
    )
    assert not _surus_paketleri(o, sonra), f"E-stop SONRASI seans START donanımı sürdü: {_surus_paketleri(o, sonra)}"
    with o.api._session_lock:
        assert not o.api._active_session.get("is_active"), "E-stop sonrası mandallıyken seans AÇILDI"
    assert r.status_code == 409, f"mandallıyken seans START {r.status_code} döndü: {r.text[:200]}"


@pytest.mark.parametrize("komut", ["start_coil", "start_all_coils"])
def test_KRITIK_estop_sonrasi_LEGACY_hardware_command_START_reddedilir(ortam, komut):
    o = ortam
    sonra = _estop(o)
    o.c.post("/api/hardware/command", json={"command": komut, "params": {"coil_id": 2, "duty": 40, "freq": 100}})
    assert not _surus_paketleri(o, sonra), f"E-stop SONRASI legacy '{komut}' donanımı sürdü"
    assert _calisan(o) == []


@pytest.mark.parametrize("kaynak", _E_STOP_KAYNAKLARI)
def test_KRITIK_HER_estop_kaynagi_mandallar_DONANIM_duzeyinde_yoldan_bagimsiz(ortam, kaynak):
    """AI (Auto) `start_all_coils`, AI Pro / mobil `/frame` ve döngü `update_coil` çağırır — kapı ÇAĞRI DÜZEYİNDE."""
    o = ortam
    sonra = _estop(o, kaynak)
    assert o.hc.update_coil(3, 100.0, 40.0, 0.0, 5, start=True) is False, (
        f"'{kaynak}' sonrası update_coil START kabul etti"
    )
    assert o.hc.start_all_coils(100.0, 40.0, 0.0, 5) is False, f"'{kaynak}' sonrası start_all_coils START kabul etti"
    assert not _surus_paketleri(o, sonra), f"'{kaynak}' E-stop'u SONRASI donanım sürüldü: {_surus_paketleri(o, sonra)}"
    assert _calisan(o) == []


def test_KRITIK_estop_sonrasi_ESP_START_yayini_reddedilir(ortam, monkeypatch):
    """ESP kodu silinmez (Ö.4-Y7) — açıldığında da mandal geçerli: START yayını gitmez, STOP gider."""
    o = ortam
    monkeypatch.setenv("PEMF_ESP_ENABLED", "1")
    _estop(o)
    once = len(o.yayin)
    o.c.post("/api/coil/8/control", json={"start": True, "freq": 100, "duty": 40, "phase": 0, "duration": 60})
    o.c.post(
        "/api/coil/batch", json={"coil_ids": [8], "start": True, "freq": 100, "duty": 40, "phase": 0, "duration": 60}
    )
    o.c.post(
        "/api/session/start",
        json={"coil_ids": [8], "frequency": 100, "duty": 40, "phase": 0, "duration_minutes": 5, "mode": "Manuel"},
    )
    import time as _t

    _t.sleep(0.3)  # seans yolu ESP yayınını arka plan iş parçacığında yapar
    start_yayinlari = [(t, p) for t, p in o.yayin[once:] if str(p.get("command", "")).lower() == "start"]
    assert not start_yayinlari, f"E-stop SONRASI ESP START yayını gitti: {start_yayinlari}"


def test_KRITIK_ESP_START_yayini_SURERKEN_estop_gelirse_ardindan_TELAFI_STOP(ortam, monkeypatch):
    """ESP yayınında kilit TUTULAMAZ (yayın saniyeler sürer; STOP'u bekletemez): START yayını sürerken gelen acil
    durdurmanın STOP'u telde START'tan ÖNCE kalabilir → START'tan SONRA bir STOP daha gitmeli (telafi)."""
    import threading

    o = ortam
    monkeypatch.setenv("PEMF_ESP_ENABLED", "1")
    gelen, birak = threading.Event(), threading.Event()
    tel: list = []  # yayının TAMAMLANMA sırası (= broker'a ulaşma sırası)

    def _yayin(topic, payload):
        if str(payload.get("command")) == "start":
            gelen.set()
            assert birak.wait(10), "aparat: START yayını serbest bırakılmadı"
        tel.append((topic, str(payload.get("command"))))
        return True

    monkeypatch.setattr(o.api, "_mqtt_publish", _yayin)
    kutu: dict = {}
    t = threading.Thread(
        target=lambda: kutu.update(
            r=o.c.post("/api/coil/8/control", json={"start": True, "freq": 100, "duty": 40, "phase": 0, "duration": 60})
        ),
        daemon=True,
    )
    t.start()
    assert gelen.wait(10), "aparat: START yayını başlamadı"
    o.api._emergency_stop_all("manual")
    birak.set()
    t.join(15)
    bobin8 = [k for tp, k in tel if tp == "pemf/coil/8/control"]
    assert "start" in bobin8, f"aparat: START yayını görülmedi: {bobin8}"
    son_start = len(bobin8) - 1 - bobin8[::-1].index("start")
    assert "stop" in bobin8[son_start + 1 :], (
        f"E-stop START yayını SÜRERKEN geldi; telde son komut START kaldı (telafi STOP'u yok): {bobin8}"
    )


def test_KRITIK_mqtt_publish_SON_SAVUNMA_mandalliyken_START_yayinlamaz_STOP_yayinlar(ortam, monkeypatch):
    """Tek boğaz noktası `_mqtt_publish` (GERÇEK; paho istemcisi sahte, broker sondası yamalı — ağa çıkılmaz)."""
    import socket

    import paho.mqtt.client as pm

    o = ortam
    yayinlanan: list = []

    class _SahteIstemci:
        def __init__(self, *a, **k):
            pass

        def username_pw_set(self, *a, **k):
            pass

        def connect(self, *a, **k):
            pass

        def loop_start(self):
            pass

        def loop_stop(self):
            pass

        def disconnect(self):
            pass

        def publish(self, topic, veri, *a, **k):
            yayinlanan.append((topic, veri))
            return types.SimpleNamespace(wait_for_publish=lambda timeout=None: None, is_published=lambda: True)

    monkeypatch.setattr(o.api, "_mqtt_publish", o.gercek_yayin)  # GERÇEK tek boğaz noktası
    monkeypatch.setattr(pm, "Client", _SahteIstemci)
    monkeypatch.setattr(o.ls, "esp_etkin", lambda: True)
    monkeypatch.setattr(o.api, "_mqtt_credentials", lambda: (None, None))
    monkeypatch.setattr(o.api, "_kaydet_esp_komut_niyeti", lambda *a, **k: None)
    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: types.SimpleNamespace(close=lambda: None))
    o.api._emergency_stop_all("manual")
    once = len(yayinlanan)
    o.api._mqtt_publish("pemf/coil/8/control", {"command": "start", "command_id": "t1", "freq": 10, "duty": 5})
    assert len(yayinlanan) == once, f"mandallıyken _mqtt_publish START YAYINLADI: {yayinlanan[once:]}"
    assert o.api._mqtt_publish("pemf/coil/8/control", {"command": "stop", "command_id": "t2"}) is True
    assert len(yayinlanan) == once + 1, "mandallıyken STOP yayınlanmadı (Ö.4-Y8)"


# ── STOP / acil durdurma mandalla KAPILANMAZ (Ö.4-Y8) ────────────────────────────────────────────
def test_KARSIT_mandalliyken_STOP_ve_ikinci_ESTOP_ASLA_kapilanmaz(ortam, monkeypatch):
    o = ortam
    monkeypatch.setenv("PEMF_ESP_ENABLED", "1")
    _estop(o)
    n = len(o.hc.core._hw_send_queue.paketler)
    assert o.hc.update_coil(1, 0.0, 0.0, 0.0, 0, start=False) is True, "mandallıyken update_coil STOP reddedildi"
    assert o.hc.stop_all_coils() is True, "mandallıyken stop_all_coils reddedildi"
    r = o.c.post("/api/coil/2/control", json={"start": False, "freq": 100, "duty": 0, "phase": 0, "duration": 0})
    assert r.status_code == 200, f"mandallıyken tekil STOP {r.status_code}"
    once_yayin = len(o.yayin)
    r2 = o.c.post("/api/hardware/emergency_stop")
    assert r2.status_code == 200, f"mandallıyken İKİNCİ acil durdurma {r2.status_code}"
    stop_yayinlari = [p for t, p in o.yayin[once_yayin:] if str(p.get("command")) == "stop"]
    assert stop_yayinlari, "mandallıyken ikinci acil durdurmanın ESP STOP yayını gitmedi"
    yeni = o.hc.core._hw_send_queue.paketler[n:]
    assert len(yeni) >= 3 and all(not any(d > 0 for d in _duty(p)) for p in yeni), "mandallıyken STOP paketleri gitmedi"


def test_KRITIK_aktif_seans_YOKKEN_session_stop_calisan_bobine_STOP_yollar(ortam):
    """D1.81 başlığı: `/api/session/stop` 'Aktif seans yok' derken de çalışan bobinlere STOP göndermeli (İG-5.3)."""
    o = ortam
    assert o.hc.update_coil(2, 100.0, 40.0, 0.0, 5, start=True) is True, "aparat: bobin 2 sürülemedi"
    n = len(o.hc.core._hw_send_queue.paketler)
    r = o.c.post("/api/session/stop")
    assert r.status_code == 200
    assert "Aktif seans yok" in r.json().get("message", ""), r.text[:200]
    yeni = [_duty(p) for p in o.hc.core._hw_send_queue.paketler[n:]]
    assert yeni and not any(d > 0 for d in yeni[-1]), f"seanssız /session/stop STOP paketi göndermedi: {yeni}"
    assert _calisan(o) == [], f"seanssız /session/stop sonrası çalışan bobin: {_calisan(o)}"


# ── Sıfırla: ayrı, bilinçli eylem; kendi başına BAŞLATMAZ ──────────────────────────────────────────
def test_KRITIK_SIFIRLA_hicbir_seyi_BASLATMAZ_sonra_YENI_START_calisir(ortam):
    o = ortam
    sonra = _estop(o)
    o.c.post("/api/coil/1/control", json={"start": True, "freq": 100, "duty": 40, "phase": 0, "duration": 60})
    r = o.c.post(_SIFIRLA_YOLU, json={"onay": True})
    assert r.status_code == 200, f"Sıfırla ucu {r.status_code}: {r.text[:200]}"
    assert not _surus_paketleri(o, sonra), "Sıfırla mandallıyken reddedilen START'ı DİRİLTTİ (kendi başına başlattı)"
    assert _calisan(o) == []
    with o.api._session_lock:
        assert not o.api._active_session.get("is_active"), "Sıfırla seans açtı"
    n = len(o.hc.core._hw_send_queue.paketler)
    r2 = o.c.post("/api/coil/1/control", json={"start": True, "freq": 100, "duty": 40, "phase": 0, "duration": 60})
    assert r2.status_code == 200 and r2.json().get("status") == "success", (
        f"Sıfırla sonrası YENİ START reddedildi: {r2.text}"
    )
    assert _surus_paketleri(o, n), "Sıfırla sonrası yeni START donanımı sürmedi"


def test_KRITIK_mandal_DURUMU_saglik_ve_WS_anlik_goruntusunde_gorunur(ortam):
    """Arayüz (Welcome/Auth dahil) mandalı ve 'Sıfırla'yı gösterebilsin: sağlık ucu (auth-muaf) + WS anlık görüntü."""
    o = ortam
    _estop(o)
    h = o.c.get("/api/health").json()
    assert (h.get("estopMandali") or {}).get("aktif") is True, (
        f"sağlık ucunda mandal görünmüyor: {h.get('estopMandali')}"
    )
    assert (o.ls._build_ws_snapshot().get("estopMandali") or {}).get("aktif") is True, (
        "WS anlık görüntüsünde mandal yok"
    )
    assert any(m.get("type") == "estop_mandali" and (m.get("data") or {}).get("aktif") for m in o.ws), (
        "mandal kurulunca WS yayını yok"
    )
    o.c.post(_SIFIRLA_YOLU, json={"onay": True})
    assert (o.c.get("/api/health").json().get("estopMandali") or {}).get("aktif") is False, (
        "Sıfırla sonrası hâlâ mandallı"
    )
    assert any(m.get("type") == "estop_mandali" and (m.get("data") or {}).get("aktif") is False for m in o.ws), (
        "Sıfırla sonrası WS yayını yok"
    )
