# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""BE 2 · Y226 / Y227 — PC'deki uygulama BOŞTAYKEN kapatılınca istemciye ALARM gitmez; "teyitsiz" düğme yalnız bir şey çalışıyorduysa.

Sahip (31.10, telefonda gördükleri): "bu acil durdur mandalı her yerde çıkıyor … bobinler çalışmıyorken de çıkıyor". ÖLÇÜLEN KÖK: başlatıcı
HER pencere kapanışında `kapanis_durdur` → `_emergency_stop_all(kalici=False)` bellekteki mandalı kurup YAYINLIYOR; telefon kopmadan hemen
önce alıp kırmızı "MANDALLI — uygulama seans ya da bobin çalışırken kapatıldı" (yanlış neden) gösteriyordu; kart yokken teyit düşünce
"ACİL DURDUR (teyitsiz)" her ekranda kalıyordu.

SÖZLEŞME:
  · Boşta kapanış: STOP'lar ve bellekteki mandal AYNEN (Ö.4-Y8, öldürmeye dek START reddi), mandal durumunda `bostaKapanis: true`
    (arayüz alarm bandı yerine nötr satır), teyit iletisinde `calisiyordu: false`, istemciye ALARM bildirimi YOK (kart yanıtsız / ret dahil).
  · Çalışırken kapanış: bugünkü gibi — `bostaKapanis: false`, `calisiyordu: true`, alarm bildirimi + diske mandal (Y45 / Y46).
  · Durum okunamazsa `calisiyordu: null` (bilinmiyor → düğme KALIR).
  · YAPIŞKAN: çalışırken verilen teyitsiz durdurmayı sonraki (istemcinin aynı basıştaki ikinci isteği) "boştaydı"ya İNDİREMEZ; teyit gelince sıfırlanır.
  · `calisiyordu` STOP'tan ÖNCE okunur ama BEKLEMEZ: canlı durum kilidi meşgulse None.
Sahte EN ALT katta: HardwareController (STM yazımı), MQTT yayını, WS yayını, bildirim — `_emergency_stop_all` / `kapanis_durdur` GERÇEK.
"""

from __future__ import annotations

import threading
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from topoloji import ESP_BOBIN, TUM_STM

_UC = "/api/hardware/kapanis_durdur"


@pytest.fixture
def ortam(monkeypatch, tmp_path):
    from servers import api_server as api
    from servers import live_state
    from utils import estop_mandali

    olaylar: list = []
    yayinlar: list = []
    calisan = {"bobin": False}
    kart = {"yanit": None}

    class _SahteHC:
        @property
        def coils_state(self):
            if calisan["bobin"] == "okunamaz":
                raise RuntimeError("durum okunamadi")
            # ⚠️ TUM_STM bir KÜME: `TUM_STM[0]` istisna atar ve "bobin" kolunu sessizce "okunamaz" yoluna sokar (ölçüldü).
            return {b: {"is_running": bool(calisan["bobin"]) and b == min(TUM_STM)} for b in TUM_STM}

        def stop_all_coils(self):
            olaylar.append(("stop", "stm"))
            return True

        def update_coil(self, *a, **k):
            return True

    def _yayin(topic, payload):
        if payload.get("command") == "stop":
            olaylar.append(("stop", topic))
        return False

    def _ws(mesaj):
        yayinlar.append(mesaj)

    monkeypatch.setattr(api.state, "hardware", _SahteHC())
    monkeypatch.setattr(api, "_mqtt_publish", _yayin)
    monkeypatch.setattr(api, "_estop_cloud_mirror", lambda *a, **k: None)
    monkeypatch.setattr(api, "_ws_broadcast_sync", _ws)
    monkeypatch.setattr(live_state, "_ws_broadcast_sync", _ws)
    monkeypatch.setattr(api, "_push_notification", lambda *a, **k: olaylar.append(("bildirim", a[0] if a else "")))
    monkeypatch.setattr(api, "_stm_stop_kart_yaniti", lambda *_a, **_k: kart["yanit"])
    with api._session_lock:
        api._active_session.clear()
    with live_state._live_state_lock:
        live_state._live_state["estopTeyit"] = None
    estop_mandali.sifirla("test")
    estop_mandali.kalicilik_kur(tmp_path / "estop_mandali.json")
    c = TestClient(api.app, client=("127.0.0.1", 51261))
    yield SimpleNamespace(
        api=api,
        ls=live_state,
        mandal=estop_mandali,
        olaylar=olaylar,
        yayinlar=yayinlar,
        calisan=calisan,
        kart=kart,
        c=c,
    )
    estop_mandali.kalicilik_kapat()
    estop_mandali.sifirla("test")
    with api._session_lock:
        api._active_session.clear()
    with live_state._live_state_lock:
        live_state._live_state["estopTeyit"] = None


def _son(o, tur):
    v = [m["data"] for m in o.yayinlar if m.get("type") == tur]
    return v[-1] if v else None


def _bildirimler(o):
    return [n for t, n in o.olaylar if t == "bildirim"]


def _stoplar(o):
    return [n for t, n in o.olaylar if t == "stop"]


@pytest.mark.parametrize("kart_yaniti", [None, "yanitsiz", "red"])
def test_KRITIK_BOSTA_kapanis_STOP_ve_mandal_AYNEN_ama_ALARM_YOK_notr_isaret_VAR(ortam, kart_yaniti):
    o = ortam
    o.kart["yanit"] = kart_yaniti
    r = o.c.post(_UC, json={"onay": True})
    assert r.status_code == 200, r.text
    assert r.json()["mandalKalici"] is False
    assert "stm" in _stoplar(o) and f"pemf/coil/{ESP_BOBIN}/control" in _stoplar(o), f"STOP gitmedi: {o.olaylar}"
    assert o.mandal.mandalli_mi() is True, "boşta kapanışta bellekteki mandal kurulmadı (öldürmeye dek START reddi)"
    mandal = _son(o, "estop_mandali")
    assert mandal and mandal["aktif"] is True, "mandal yayını yok"
    assert mandal.get("bostaKapanis") is True, (
        f"boşta kapanış mandalı ALARM olarak yayınlandı (nötr işaret yok): {mandal}"
    )
    teyit = _son(o, "estop_teyit")
    assert teyit is not None and teyit.get("calisiyordu") is False, f"teyit iletisi 'boştaydı' demiyor: {teyit}"
    assert r.json().get("calisiyordu") is False
    assert _bildirimler(o) == [], f"boşta kapanışta istemciye ALARM bildirimi gitti: {_bildirimler(o)}"


@pytest.mark.parametrize("hal", ["bobin", "seans"])
def test_KRITIK_CALISIRKEN_kapanis_bugunku_gibi_ALARM_bant_ve_dogru_neden(ortam, hal):
    o = ortam
    o.kart["yanit"] = "yanitsiz"
    if hal == "seans":
        with o.api._session_lock:
            o.api._active_session.update(is_active=True, coil_ids=[1])
    else:
        o.calisan["bobin"] = True
    r = o.c.post(_UC, json={"onay": True})
    assert r.status_code == 200 and r.json()["mandalKalici"] is True
    mandal = _son(o, "estop_mandali")
    assert mandal["aktif"] is True and mandal.get("bostaKapanis") is False, mandal
    assert mandal["neden"] == "uygulama_kapanisi", mandal
    teyit = _son(o, "estop_teyit")
    assert teyit["teyitli"] is False and teyit.get("calisiyordu") is True, teyit
    assert len(_bildirimler(o)) >= 2, f"çalışırken kapanış alarmı (mandal + kart yanıtsız) gitmedi: {_bildirimler(o)}"


def test_KRITIK_durum_OKUNAMAZSA_calisiyordu_BILINMIYOR_dugme_kalir(ortam):
    o = ortam
    o.calisan["bobin"] = "okunamaz"
    o.kart["yanit"] = "yanitsiz"
    o.api._emergency_stop_all("manual")
    teyit = _son(o, "estop_teyit")
    assert teyit["teyitli"] is False and "calisiyordu" in teyit and teyit["calisiyordu"] is None, teyit


def test_KRITIK_YAPISKAN_calisirkenki_teyitsiz_durdurma_ikinci_istekle_bostaya_INMEZ_teyitle_sifirlanir(ortam):
    o = ortam
    o.kart["yanit"] = "yanitsiz"
    o.calisan["bobin"] = True
    o.api._emergency_stop_all("manual")  # istemcinin 1. adımı — bobin çalışıyordu
    assert _son(o, "estop_teyit")["calisiyordu"] is True
    o.calisan["bobin"] = False
    o.api._emergency_stop_all("manual")  # aynı basışın 2. adımı — bobinler artık durmuş görünüyor
    teyit = _son(o, "estop_teyit")
    assert teyit["teyitli"] is False and teyit["calisiyordu"] is True, f"ikinci istek düğmeyi düşürdü: {teyit}"
    o.kart["yanit"] = None  # kart yanıt verdi → teyit
    o.api._emergency_stop_all("manual")
    assert _son(o, "estop_teyit")["teyitli"] is True
    o.kart["yanit"] = "yanitsiz"
    o.api._emergency_stop_all("manual")  # teyitten sonra boştaki yeni teyitsiz durdurma
    assert _son(o, "estop_teyit")["calisiyordu"] is False


def test_KRITIK_BOSTA_manuel_durdurma_teyitsiz_ama_calisiyordu_FALSE(ortam):
    o = ortam
    o.kart["yanit"] = "yanitsiz"
    sonuc = o.api._emergency_stop_all("manual")
    assert sonuc["confirmed"] is False and sonuc["calisiyordu"] is False
    teyit = _son(o, "estop_teyit")
    assert teyit["teyitli"] is False and teyit["calisiyordu"] is False
    assert _son(o, "estop_mandali")["bostaKapanis"] is False, "operatörün ACİL DURDUR'u nötr satıra döndü"


def test_KRITIK_calisiyordu_okumasi_KILIDI_BEKLEMEZ_STOP_gecikmez(ortam):
    o = ortam
    with o.ls._live_state_lock:
        o.ls._live_state["coils"][0]["running"] = True
    try:
        assert o.api._durdurma_aninda_calisiyor_mu(False) is True
        tutuldu = threading.Event()
        birak = threading.Event()

        def _tut():
            with o.ls._live_state_lock:
                tutuldu.set()
                birak.wait(5)

        t = threading.Thread(target=_tut, daemon=True)
        t.start()
        assert tutuldu.wait(5)
        t0 = time.monotonic()
        try:
            assert o.api._durdurma_aninda_calisiyor_mu(False) is None
        finally:
            sure = time.monotonic() - t0
            birak.set()
            t.join(5)
        assert sure < 0.2, f"durum okuması kilidi BEKLEDİ ({sure:.3f} sn) — STOP gecikir"
        assert o.api._durdurma_aninda_calisiyor_mu(True) is True
    finally:
        with o.ls._live_state_lock:
            o.ls._live_state["coils"][0]["running"] = False


def test_mandal_durumu_bostaKapanis_sifirla_ve_sonraki_mandalla_ile_kalkar(ortam):
    m = ortam.mandal
    m.mandalla("uygulama_kapanisi", bosta_kapanis=True)
    assert m.durum()["bostaKapanis"] is True
    m.mandalla("manual")
    assert m.durum()["bostaKapanis"] is False
    m.mandalla("uygulama_kapanisi", bosta_kapanis=True)
    m.sifirla("operator")
    assert m.durum()["bostaKapanis"] is False
