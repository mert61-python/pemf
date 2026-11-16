# Author: mertaygn, cglrgrkn
"""KP-1 · apps/backend/servers/api_server.py · sözleşmeler: ACİL DURDUR (`_emergency_stop_all`) hiçbir yan arızada istisna
sızdırmaz ve STOP'ları gönderir (mandal kurulamaz, STM yazım izi / STOP sırası okunamaz, STM STOP patlar, onay bekçisi ve bulut
aynası iş parçacığı açılamaz, mandal diske yazılamaz, kayıt kuyruğu yok, yakma penceresi okunamaz, teyit yayını patlar);
seans kaydı kapanışında olay ve koşu kaydı hataları yutulur ve seans "Acil Durduruldu" mühürlenir; STM STOP yazım / kart yanıtı
yardımcılarının arıza dalları; kart reddi / yanıtsızlığı bildirimi patlasa da sonuç döner; `_durdurma_is_parcaciginda`
(iş hatası bekleyene geçer, bekleyen vazgeçmişse günlüğe, iş parçacığı açılamazsa eşzamanlı koşar); kapanış ve Sıfırla
uçlarında bozuk JSON 400, Sıfırla'da denetim izi yazılamasa da mandal kalkar.

Sahte EN ALT katta: donanım (`state.hardware` + `core` yazım izi yöntemleri; G/Ç arıza biçimi `OSError`), MQTT yayını
(`_mqtt_publish`), iş parçacığı açılışı (`threading.Thread.start` → `RuntimeError("can't start new thread")`, adla seçilir),
kayıt kuyruğu (`utils.dongu_disi_yazim`), tedavi DB'si (`_get_treatment_db` → `sqlite3.OperationalError` atan kayıtçı),
bildirim gönderimi ve WS yayını kaydı.
"""

from __future__ import annotations

import asyncio
import copy
import logging
import sqlite3
import threading
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from topoloji import STM_BOBIN, TUM_ESP


@pytest.fixture
def ortam(monkeypatch):
    from servers import api_server as a
    from servers import live_state as ls

    yayin: list = []
    bildirim: list = []
    mqtt: list = []
    acilamayan: list = []
    engelli: list = []

    gercek = threading.Thread

    class _Secici(gercek):
        def start(self):
            if any(str(self.name).startswith(on) for on in engelli):
                acilamayan.append(self.name)
                raise RuntimeError("can't start new thread")
            return super().start()

    monkeypatch.setattr(threading, "Thread", _Secici)
    monkeypatch.setattr(a, "_ws_broadcast_sync", lambda m: yayin.append(m))
    monkeypatch.setattr(ls, "_ws_broadcast_sync", lambda m: yayin.append(m))
    monkeypatch.setattr(a, "_push_notification", lambda m, s="info", mesajlar=None: bildirim.append((m, s)))
    monkeypatch.setattr(a, "_mqtt_publish", lambda t, p: mqtt.append((t, p.get("command"))) or True)
    monkeypatch.setattr(a.state, "hardware", None)
    with a._live_state_lock:
        canli_once = {k: copy.deepcopy(v) for k, v in a._live_state.items()}
    with a._session_lock:
        seans_once = dict(a._active_session)
    with a._pending_acks_lock:
        bekleyen_once = dict(a._pending_acks)
    try:
        yield SimpleNamespace(
            a=a, ls=ls, yayin=yayin, bildirim=bildirim, mqtt=mqtt, acilamayan=acilamayan, engelli=engelli
        )
    finally:
        with a._session_lock:
            a._active_session.clear()
            a._active_session.update(seans_once)
        with a._live_state_lock:
            for k, v in canli_once.items():
                a._live_state[k] = v
        with a._pending_acks_lock:
            a._pending_acks.clear()
            a._pending_acks.update(bekleyen_once)


def _patlayan(hata):
    def _f(*_a, **_k):
        raise hata

    return _f


def _log(caplog):
    return [r.getMessage() for r in caplog.records]


class _KayitDb:
    """Tedavi DB'si yerine: olay yazımı kilitli-disk hatası verir; kapanış çağrılarını kaydeder."""

    def __init__(self, olay_hatasi=True):
        self.cagri: list = []
        self._oh = olay_hatasi

    def record_session_event(self, *a, **k):
        self.cagri.append(("record_session_event", a[:2]))
        if self._oh:
            raise sqlite3.OperationalError("disk I/O error")

    def end_session(self, sid, duration_minutes=0, session_status="completed"):
        self.cagri.append(("end_session", sid, session_status))

    def set_session_meta(self, sid, **k):
        self.cagri.append(("set_session_meta", sid, tuple(sorted(k))))

    def add_sensor_samples_batch(self, sid, rows):
        self.cagri.append(("add_sensor_samples_batch", sid, len(rows)))
        return len(rows)


def test_ESTOP_her_yan_arizada_istisnasiz_STOP_gonderir_kismi_sonuc(ortam, monkeypatch, caplog):
    """Mandal kurulamaz + STM yazım izi / STOP sırası okunamaz + `stop_all_coils` OSError + onay bekçisi ve bulut aynası iş
    parçacığı açılamaz + mandal diske yazılamaz + kayıt kuyruğu RuntimeError + yakma penceresi okunamaz + teyit yayını patlar →
    istisna sızmaz; her ESP bobinine iki STOP konusu yayınlanır, ESP sonucu "success", STM durmadı → status "partial",
    confirmed False, firmwareYakiliyor False; bekleyen onay kaydı temizlenir; `emergency_stop` WS iletisi nedenle gider; her
    arıza kendi metniyle günlüğe yazılır."""
    from servers import live_state as ls
    from utils import dongu_disi_yazim, estop_mandali, firmware_yakma_penceresi

    a = ortam.a
    # YH-A3 (Y289): bulut aynası iş parçacığı YALNIZ ESP AÇIKKEN açılır — "her yan arıza" senaryosu aynanın açılamamasını da kapsar.
    monkeypatch.setenv("PEMF_ESP_ENABLED", "1")
    ortam.engelli.extend(["estop-ack-", "estop-cloud-mirror"])
    core = SimpleNamespace(hw_yazim_isareti=_patlayan(OSError("iz yok")))
    hc = SimpleNamespace(
        core=core,
        son_stop_sirasi=_patlayan(ValueError("sıra bozuk")),
        stop_all_coils=_patlayan(OSError("seri port yok")),
        coils_state={},
    )
    monkeypatch.setattr(a.state, "hardware", hc)
    monkeypatch.setattr(estop_mandali, "mandalla", _patlayan(RuntimeError("mandal kilidi")))
    monkeypatch.setattr(estop_mandali, "diske_yaz_arka_planda", _patlayan(OSError("disk dolu")))
    monkeypatch.setattr(dongu_disi_yazim, "sirada_calistir", _patlayan(RuntimeError("kuyruk yok")))
    monkeypatch.setattr(firmware_yakma_penceresi, "acik_mi", _patlayan(OSError("pencere okunamadı")))
    monkeypatch.setattr(ls, "estop_teyidi_yaz", _patlayan(RuntimeError("yayın kapalı")))
    caplog.set_level(logging.WARNING)
    sonuc = a._emergency_stop_all("kp-test")
    assert sonuc["mqttResults"] == [{"coilId": c, "mqtt": "success"} for c in sorted(TUM_ESP)]
    assert sorted(ortam.mqtt) == sorted(
        [(f"pemf/coil/{c}/control", "stop") for c in TUM_ESP] + [(f"pemf/esp32_{c}/command", "stop") for c in TUM_ESP]
    )
    assert (sonuc["status"], sonuc["confirmed"], sonuc["stmStopped"], sonuc["firmwareYakiliyor"]) == (
        "partial",
        False,
        False,
        False,
    )
    assert not [k for k in a._pending_acks if str(k).startswith("estop_")]
    assert {"type": "emergency_stop"} == {
        k: v for k, v in [m for m in ortam.yayin if m.get("type") == "emergency_stop"][0].items() if k == "type"
    }
    assert [m["data"]["reason"] for m in ortam.yayin if m.get("type") == "emergency_stop"] == ["kp-test"]
    log = _log(caplog)
    for parca in (
        "E-stop: mandal kurulamadi (durdurma SURUYOR)",
        "STM emergency stop failed",
        "E-stop: STM yazim isareti okunamadi",
        "E-stop: STM STOP sirasi okunamadi",
        "E-stop bulut-ayna thread'i açılamadı (yerel yol sürüyor).",
        "E-stop: mandal diske yazdirilamadi (durdurma tamam)",
        "E-stop: seans kaydi kapatilamadi (durdurma tamam)",
        "E-stop: teyit durumu yayinlanamadi (durdurma tamam)",
    ):
        assert parca in log, parca
    assert any("ack-izleme thread'i açılamadı" in m for m in log)


def test_ESTOP_seans_kaydi_OLAY_ve_KOSU_hatasi_yutulur_seans_ACIL_DURDURULDU(ortam, monkeypatch, caplog):
    """Aktif seans (db 77) + açık koşu kaydı + olay yazımı OperationalError + koşu kapatma kuyruğu RuntimeError → seans satırı
    `SEANS_DURUMU_ACIL_DURDURMA` ile kapanır, "estop: session_event yazilamadi" ve "estop: kosu kaydi kapatilamadi (bobin N)"
    yazılır, `db_finalized` damgalanır."""
    from database.treatment_history_db import SEANS_DURUMU_ACIL_DURDURMA
    from utils import dongu_disi_yazim

    a = ortam.a
    db = _KayitDb()
    monkeypatch.setattr(a, "_get_treatment_db", lambda: db)
    gercek_calistir = dongu_disi_yazim.calistir

    def _kuyruk(fn, *x, ad="kayit", **k):
        if str(ad).startswith("bobin kosu kaydi bitir"):
            raise RuntimeError("cannot schedule new futures after shutdown")
        return gercek_calistir(fn, *x, ad=ad, **k)

    monkeypatch.setattr(dongu_disi_yazim, "calistir", _kuyruk)
    ortam.engelli.extend(["estop-cloud-mirror", "estop-ack-"])
    with a._session_lock:
        a._active_session.update(
            is_active=True,
            db_session_id=77,
            coil_ids=[STM_BOBIN],
            session_id="kp-s",
            started_epoch=time.time() - 60,
            start_mono=time.monotonic() - 60,
        )
    with a._active_coil_runs_lock:
        a._active_coil_runs[STM_BOBIN] = 9001
    caplog.set_level(logging.WARNING)
    a._emergency_stop_all("kp-kayit")
    assert ("end_session", 77, SEANS_DURUMU_ACIL_DURDURMA) in db.cagri
    assert ("record_session_event", (77, "emergency_stop")) in db.cagri
    log = _log(caplog)
    assert "estop: session_event yazilamadi" in log
    assert f"estop: kosu kaydi kapatilamadi (bobin {STM_BOBIN})" in log


class _Core:
    def __init__(self, **yontem):
        for k, v in yontem.items():
            setattr(self, k, v)


def test_STM_yazim_teyidi_ARIZA_dallari(ortam, monkeypatch):
    """`_stm_stop_yazildi_mi`: sıralı bekleme istisna → False; sırasız ve bekleme yöntemi yok → True (eski anlam); bekleme yöntemi
    True → True, istisna → False. `_stm_stop_kart_yaniti`: yanıt beklemesi istisna → None."""
    a = ortam.a
    monkeypatch.setattr(
        a.state, "hardware", SimpleNamespace(core=_Core(hw_stop_sirasi_yazildi_bekle=_patlayan(OSError("x"))))
    )
    assert a._stm_stop_yazildi_mi(True, 3, stop_sirasi=7) is False
    monkeypatch.setattr(a.state, "hardware", SimpleNamespace(core=_Core()))
    assert a._stm_stop_yazildi_mi(True, 3) is True
    monkeypatch.setattr(a.state, "hardware", SimpleNamespace(core=_Core(hw_stop_yazildi_bekle=lambda i, s: True)))
    assert a._stm_stop_yazildi_mi(True, 3) is True
    monkeypatch.setattr(a.state, "hardware", SimpleNamespace(core=_Core(hw_stop_yazildi_bekle=_patlayan(OSError("y")))))
    assert a._stm_stop_yazildi_mi(True, 3) is False
    monkeypatch.setattr(a.state, "hardware", SimpleNamespace(core=_Core(hw_stop_yaniti_bekle=_patlayan(OSError("z")))))
    assert a._stm_stop_kart_yaniti(7) is None


@pytest.mark.parametrize(
    ("yanit", "gunluk"),
    [
        ("red", "E-stop: kart reddi bildirilemedi (durdurma tamam)"),
        ("yanitsiz", "E-stop: kart yanitsizligi bildirilemedi (durdurma tamam)"),
    ],
)
def test_ESTOP_kart_RED_ve_YANITSIZ_bildirimi_patlasa_da_sonuc_doner(ortam, monkeypatch, caplog, yanit, gunluk):
    """STM STOP porta yazıldı ama kart reddetti / yanıt vermedi + bildirim kanalı patlıyor → sonuç `stmKartYaniti` = yanıt,
    confirmed False, `stmRedMesaji` ürünün metni; bildirim hatası "…bildirilemedi" ile yazılır."""
    from utils import stm32_kimlik

    a = ortam.a
    ortam.engelli.extend(["estop-cloud-mirror", "estop-ack-"])
    core = _Core(
        hw_yazim_isareti=lambda: 1,
        hw_stop_sirasi_yazildi_bekle=lambda s, t: True,
        hw_stop_yaniti_bekle=lambda s, t: yanit,
    )
    monkeypatch.setattr(
        a.state,
        "hardware",
        SimpleNamespace(core=core, son_stop_sirasi=lambda: 5, stop_all_coils=lambda: True, coils_state={}),
    )
    monkeypatch.setattr(a, "_push_notification", _patlayan(ConnectionResetError("bildirim kanalı kapandı")))
    caplog.set_level(logging.ERROR)
    sonuc = a._emergency_stop_all("kp-kart")
    beklenen_metin = stm32_kimlik.estop_kart_red_metni() if yanit == "red" else stm32_kimlik.estop_kart_yanitsiz_metni()
    assert (sonuc["stmKartYaniti"], sonuc["confirmed"], sonuc["stmRedMesaji"]) == (yanit, False, beklenen_metin)
    assert gunluk in _log(caplog)


def test_durdurma_isi_HATASI_bekleyene_gecer(ortam):
    """İş istisna atıyor ve bekleyen var → `await` aynı istisnayı yükseltir."""

    def _is():
        raise ValueError("STOP yazılamadı")

    async def _bekle():
        return await ortam.a._durdurma_is_parcaciginda(_is, ad="kp-hata")

    with pytest.raises(ValueError, match="STOP yazılamadı"):
        asyncio.run(_bekle())


def test_durdurma_isi_bekleyen_VAZGECTIYSE_hata_gunluge_is_yine_kosar(ortam, monkeypatch, caplog):
    """Bekleyen (istemci zaman aşımı) iş koşmadan iptal edildi → iş YİNE koşar; istisnası "…: durdurma işi hata verdi (bekleyen
    yok)" uyarısıyla yazılır."""
    a = ortam.a
    hedef: list = []
    gercek = threading.Thread

    class _Tutan(gercek):
        def start(self):
            if self.name == "kp-vazgecti":
                hedef.append(self._target)
                return None
            return super().start()

    monkeypatch.setattr(threading, "Thread", _Tutan)
    kostu: list = []

    def _is():
        kostu.append(1)
        raise OSError("port kapandı")

    async def _senaryo():
        bekleyen = a._durdurma_is_parcaciginda(_is, ad="kp-vazgecti")
        bekleyen.cancel()
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    asyncio.run(_senaryo())
    caplog.set_level(logging.WARNING)
    hedef[0]()
    assert kostu == [1]
    assert "kp-vazgecti: durdurma işi hata verdi (bekleyen yok)" in _log(caplog)


def test_durdurma_is_parcacigi_ACILAMAZSA_eszamanli_kosar_sonuc_doner(ortam, caplog):
    """İş parçacığı açılamıyor → hata günlüğe yazılır, iş ÇAĞIRANDA eşzamanlı koşar ve sonucu döner (STOP gider)."""
    ortam.engelli.append("kp-esz")
    caplog.set_level(logging.ERROR)

    async def _bekle():
        return await ortam.a._durdurma_is_parcaciginda(lambda x: x * 2, 21, ad="kp-esz")

    sonuc = asyncio.run(_bekle())
    assert sonuc == 42
    assert "kp-esz: iş parçacığı açılamadı — durdurma EŞZAMANLI koşuyor (Ö.4-Y8)" in _log(caplog)


@pytest.mark.parametrize(
    ("yol", "anahtar"),
    [
        ("/api/hardware/kapanis_durdur", "sistem.hata.kapanisOnay"),
        ("/api/hardware/estop_mandali/sifirla", "sistem.hata.sifirlaOnay"),
    ],
)
def test_kapanis_ve_sifirla_BOZUK_json_400(ortam, yol, anahtar):
    """Yerelden, `Content-Type: application/json` ama gövde ayrıştırılamıyor → 400 + onay metni; mandal / STOP yolu çalışmaz."""
    from utils import ceviri

    with TestClient(ortam.a.app, client=("127.0.0.1", 50200)) as c:
        r = c.post(yol, content=b"{bozuk", headers={"content-type": "application/json"})
    assert r.status_code == 400 and r.json()["detail"] == ceviri.t(anahtar, dil="tr")
    assert ortam.mqtt == []


def test_sifirla_DENETIM_IZI_yazilamasa_da_mandal_kalkar(ortam, monkeypatch, caplog):
    """Mandal kurulu + Sıfırla {"onay": true} + denetim izi yazımı OperationalError → 200, mandalKuruluydu True, mandal artık kurulu
    değil, `bildirim.mandalSifirlandi` "warning" gider, "Mandal sıfırlama denetim izi yazılamadı." yazılır."""
    from utils import ceviri, estop_mandali

    a = ortam.a
    db = _KayitDb()
    monkeypatch.setattr(a, "_get_treatment_db", lambda: db)
    estop_mandali.mandalla("kp-test")
    caplog.set_level(logging.WARNING)
    with TestClient(a.app, client=("127.0.0.1", 50201)) as c:
        r = c.post("/api/hardware/estop_mandali/sifirla", json={"onay": True})
    assert r.status_code == 200 and r.json()["mandalKuruluydu"] is True
    assert estop_mandali.mandalli_mi() is False
    assert (ceviri.t("bildirim.mandalSifirlandi", dil="tr"), "warning") in ortam.bildirim
    assert "Mandal sıfırlama denetim izi yazılamadı." in _log(caplog)
    assert db.cagri[0][0] == "record_session_event"
