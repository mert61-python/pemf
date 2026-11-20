# Author: mertaygn, cglrgrkn
"""KP-1 · apps/backend/servers/api_server.py · sözleşmeler: STM olay işleyicisi (`_handle_backend_event`) ve kart reddi yolları —
kopma / firmware watchdog'unda donanım sıfırlaması ya da STOP iş parçacığı başarısız olsa da işleyici sürer ve operatöre söyler;
Y45 mandalı kurulamazsa STOP yine gider; duty reddi (D1.101) kenar dışı tekrarda bildirilir, seanssız kenarda HC sıfırlanamasa
da operatöre söylenir; seansta red ACİL DURDUR iş parçacığı açılamazsa "durdurulamadı" (False) döner; STM telemetrisinde
sensör kaydedici arızası canlı durumu bozmaz; susan alan sensöründe anlık yoğunluk temizlenemese de alan düşürülür.

Sahte EN ALT katta: donanım (`state.hardware` — seri G/Ç arıza biçimi `OSError`), STOP iş parçacığı (`threading.Thread.start`
→ `RuntimeError("can't start new thread")`, yalnız `estop-` adlılar), WS yayını ve bildirim gönderimi kaydedilir.
"""

from __future__ import annotations

import copy
import logging
import threading
from types import SimpleNamespace

import pytest
from topoloji import STM_BOBIN

DUTY_NACK = "-> STM_NACK: RANGE coil=1 field=duty value_milli=800000 max_milli=500000 kip=bipolar"


class _Hc:
    """HardwareController yerine: G/Ç arızasını `OSError` ile taklit eder, çağrıları kaydeder."""

    def __init__(self, calisan=(), disc_hata=False, stop_hata=False):
        self.coils_state = {c: {"is_running": True} for c in calisan}
        self.cagri: list = []
        self._disc_hata, self._stop_hata = disc_hata, stop_hata

    def on_disconnect(self):
        self.cagri.append("on_disconnect")
        if self._disc_hata:
            raise OSError("seri port kapandı")

    def stop_all_coils(self):
        self.cagri.append("stop_all_coils")
        if self._stop_hata:
            raise OSError("seri porta yazılamadı")
        return True


@pytest.fixture
def ortam(monkeypatch):
    from servers import api_server as a
    from servers import live_state as ls

    yayin: list = []
    bildirim: list = []
    acilamayan: list = []

    def _bildirim(mesaj, seviye="info", mesajlar=None):
        bildirim.append((mesaj, seviye, dict(ls._BILDIRIM_MESAJLARI.get() or {})))

    gercek = threading.Thread

    class _AcilmayanThread(gercek):
        def start(self):
            if str(self.name).startswith("estop-"):
                acilamayan.append(self.name)
                raise RuntimeError("can't start new thread")
            return super().start()

    monkeypatch.setattr(threading, "Thread", _AcilmayanThread)
    monkeypatch.setattr(a, "_ws_broadcast_sync", lambda m: yayin.append(m))
    monkeypatch.setattr(ls, "_ws_broadcast_sync", lambda m: yayin.append(m))
    monkeypatch.setattr(a, "_push_notification", _bildirim)
    monkeypatch.setattr(a.state, "hardware", None)
    with a._live_state_lock:
        canli_once = {k: copy.deepcopy(v) for k, v in a._live_state.items()}
    with a._session_lock:
        seans_once = dict(a._active_session)
    olculen_once = copy.deepcopy(a._coil_olculen_alanlar)
    # Y312 (PX, paralel süit): süreç geneli alan damgaları önceki DOSYALARDAN kalabilir (ölçüldü: xdist işçisinde 5 / 6. bobinin
    # damgası → `_olculen_alanlari_tazele` [6, 7, 1] yayınladı) → her test BOŞ sözlükle başlar; sonda yine eski hâli geri konur.
    a._coil_olculen_alanlar.clear()
    tel_once = dict(a._coil_last_telemetry)
    with a._stm_nack_lock:
        a._stm_nack_son.clear()
    ls.stm_komut_kabulu_bildir()
    try:
        yield SimpleNamespace(api=a, ls=ls, yayin=yayin, bildirim=bildirim, acilamayan=acilamayan)
    finally:
        ls.stm_komut_kabulu_bildir()
        with a._stm_nack_lock:
            a._stm_nack_son.clear()
        with a._session_lock:
            a._active_session.clear()
            a._active_session.update(seans_once)
        with a._live_state_lock:
            for k, v in canli_once.items():
                a._live_state[k] = v
        a._coil_olculen_alanlar.clear()
        a._coil_olculen_alanlar.update(olculen_once)
        a._coil_last_telemetry.clear()
        a._coil_last_telemetry.update(tel_once)
        a._akim_guvenilmez_bildirildi.clear()
        a._mag_doygun_son.clear()


def _olay(tur, **veri):
    return SimpleNamespace(event_type=tur, data=veri)


def _stm_seansi(a, monkeypatch):
    monkeypatch.setitem(a._active_session, "is_active", True)
    monkeypatch.setitem(a._active_session, "coil_ids", [STM_BOBIN])


def _mesajlar(caplog):
    return [r.getMessage() for r in caplog.records]


def test_KOPMA_on_disconnect_ve_STOP_is_parcacigi_basarisiz_isleyici_SURER_ve_soyler(ortam, monkeypatch, caplog):
    """STM koptu + STM bobinli aktif seans + HC `on_disconnect` OSError + STOP iş parçacığı açılamıyor → işleyici istisna
    sızdırmaz; canlı STM durumu "warning", `bildirim.stmKoptuSeansDurdu` "error" bildirimi gider, STOP iş parçacığı denenmiştir
    ve iki arıza da günlüğe yazılır ("STM on_disconnect failed", "STM disconnect STOP failed")."""
    from utils import ceviri

    a = ortam.api
    hc = _Hc(calisan=[STM_BOBIN], disc_hata=True)
    monkeypatch.setattr(a.state, "hardware", hc)
    _stm_seansi(a, monkeypatch)
    caplog.set_level(logging.ERROR)
    a._handle_backend_event(_olay("hardware.stm.disconnected"))
    assert hc.cagri == ["on_disconnect"]
    assert a._live_state["stm"] == "warning"
    assert (ceviri.t("bildirim.stmKoptuSeansDurdu", dil="tr"), "error") in [(m, s) for m, s, _ in ortam.bildirim]
    assert ortam.acilamayan == ["estop-stm_disconnected"]
    log = _mesajlar(caplog)
    assert "STM on_disconnect failed" in log and "STM disconnect STOP failed" in log


def test_WATCHDOG_HC_sifirlama_ve_STOP_basarisiz_isleyici_SURER(ortam, monkeypatch, caplog):
    """Firmware watchdog'u + STM bobinli aktif seans + `stop_all_coils` OSError + STOP iş parçacığı açılamıyor → istisna sızmaz,
    `stop_all_coils` denenmiştir, STOP iş parçacığı denenmiştir; "STM watchdog sonrasi HC sifirlama basarisiz" ve
    "STM watchdog STOP failed" günlüğe yazılır, operatöre "error" düzeyli bildirim gider."""
    a = ortam.api
    hc = _Hc(calisan=[STM_BOBIN], stop_hata=True)
    monkeypatch.setattr(a.state, "hardware", hc)
    _stm_seansi(a, monkeypatch)
    caplog.set_level(logging.ERROR)
    a._handle_backend_event(_olay("hardware.stm.watchdog_timeout"))
    assert "stop_all_coils" in hc.cagri
    assert ortam.acilamayan == ["estop-stm_watchdog_timeout"[:24]]  # ürün iş parçacığı adını 24 karakterde keser
    log = _mesajlar(caplog)
    assert "STM watchdog sonrasi HC sifirlama basarisiz" in log and "STM watchdog STOP failed" in log
    assert any(s == "error" for _, s, _ in ortam.bildirim)


def test_Y45_mandal_KURULAMAZSA_STOP_yine_gider_mandal_yayini_YOK(ortam, monkeypatch, caplog):
    """Seanssız elle sürüşte kopma + `mandalla` istisna atıyor → `_y45_mandal_kur` False döner (mandal kurulmadı), HC
    `on_disconnect` (STOP) YİNE çağrılır, `estop_mandali` WS yayını yapılmaz, hata "Y45: mandal kurulamadi" ile yazılır."""
    from utils import estop_mandali

    a = ortam.api
    hc = _Hc(calisan=[STM_BOBIN])
    monkeypatch.setattr(a.state, "hardware", hc)
    monkeypatch.setitem(a._active_session, "is_active", False)

    def _patlayan(*_a, **_k):
        raise RuntimeError("mandal kilidi bozuk")

    monkeypatch.setattr(estop_mandali, "mandalla", _patlayan)
    caplog.set_level(logging.ERROR)
    assert a._y45_mandal_kur("stm_disconnected") is False
    a._handle_backend_event(_olay("hardware.stm.disconnected"))
    assert hc.cagri == ["on_disconnect"]
    assert not [m for m in ortam.yayin if m.get("type") == "estop_mandali"]
    assert "Y45: mandal kurulamadi (durdurma SURUYOR)" in _mesajlar(caplog)


def test_Y45_mandal_sonrasi_YAYIN_hatasi_yutulur_ve_gunluge_yazilir(ortam, monkeypatch, caplog):
    """Mandal kuruldu, ardından `estop_mandali` WS yayını istisna atıyor → `_y45_mandal_sonrasi` istisna sızdırmaz, mandal bildirimi
    basılmaz (yayından sonra gelir), "Y45: mandal bildirimi yapilamadi" günlüğe yazılır."""
    a = ortam.api

    def _yayin(m):
        if m.get("type") == "estop_mandali":
            raise ConnectionResetError("WS kapandı")
        ortam.yayin.append(m)

    monkeypatch.setattr(a, "_ws_broadcast_sync", _yayin)
    caplog.set_level(logging.ERROR)
    a._y45_mandal_sonrasi("stm_watchdog_timeout")
    assert ortam.bildirim == []
    assert "Y45: mandal bildirimi yapilamadi" in _mesajlar(caplog)


def test_DUTY_reddi_KENAR_DISI_tekrar_bastirilmamissa_bildirilir(ortam):
    """Duty tavanı NACK'i, kenar DIŞI (ilk_kez=False) ve bastırma penceresi boş → TEK "error" bildirimi:
    "⛔ " + `stm_duty_reddi_metni(ham, sifirla=mandalli_mi())`; ikinci aynı tekrar pencerede bastırılır."""
    from utils import estop_mandali

    a, ls = ortam.api, ortam.ls
    a._stm_duty_reddini_isle(DUTY_NACK, False)
    beklenen = "⛔ " + ls.stm_duty_reddi_metni(DUTY_NACK, sifirla=estop_mandali.mandalli_mi(), dil="tr")
    assert [(m, s) for m, s, _ in ortam.bildirim] == [(beklenen, "error")]
    a._stm_duty_reddini_isle(DUTY_NACK, False)
    assert len(ortam.bildirim) == 1


def test_DUTY_reddi_seanssiz_KENAR_HC_sifirlanamazsa_DURMADI_metni(ortam, monkeypatch, caplog):
    """Seanssız kenarda duty reddi + `stop_all_coils` OSError → bildirim `_duty_cikislar_metni(ham, d, False)` (çıkışlar
    durdurulamadı kolu), "D1.101: duty reddi sonrasi STM surus durumu sifirlanamadi" günlüğe yazılır."""
    a = ortam.api
    hc = _Hc(stop_hata=True)
    monkeypatch.setattr(a.state, "hardware", hc)
    monkeypatch.setitem(a._active_session, "is_active", False)
    caplog.set_level(logging.ERROR)
    a._stm_duty_reddini_isle(DUTY_NACK, True)
    assert hc.cagri == ["stop_all_coils"]
    assert [(m, s) for m, s, _ in ortam.bildirim] == [("⛔ " + a._duty_cikislar_metni(DUTY_NACK, "tr", False), "error")]
    assert "D1.101: duty reddi sonrasi STM surus durumu sifirlanamadi" in _mesajlar(caplog)


def test_DUTY_reddi_islenemezse_istisna_SIZMAZ(ortam, caplog):
    """`ham` metin değil (bastırma özeti çıkarılamıyor) → `_stm_duty_reddini_isle` istisna sızdırmaz, bildirim yok,
    "D1.101: duty reddi islenemedi" günlüğe yazılır."""
    caplog.set_level(logging.ERROR)
    ortam.api._stm_duty_reddini_isle(None, False)
    assert ortam.bildirim == []
    assert "D1.101: duty reddi islenemedi" in _mesajlar(caplog)


def test_SEANSTA_red_eylem_metni_birakilamasa_da_STOP_denenir(ortam, monkeypatch, caplog):
    """STM bobinli aktif seans + mandal eylem metni bırakılamıyor (`eylem_birak` istisna) → uyarı "K12: mandal eylem metni
    bırakılamadı" yazılır, STOP iş parçacığı YİNE denenir; açılamadığı için `_stm_red_aktif_seansi_durdur` False döner ve
    "STM red sonrasi seans durdurma basarisiz" yazılır."""
    from utils import estop_mandali

    a = ortam.api
    _stm_seansi(a, monkeypatch)

    def _patlayan(*_a, **_k):
        raise RuntimeError("eylem deposu bozuk")

    monkeypatch.setattr(estop_mandali, "eylem_birak", _patlayan)
    caplog.set_level(logging.WARNING)
    assert a._stm_red_aktif_seansi_durdur(DUTY_NACK) is False
    assert ortam.acilamayan == ["estop-stm_komut_reddi"]
    log = _mesajlar(caplog)
    assert "K12: mandal eylem metni bırakılamadı (durdurma SÜRÜYOR)" in log
    assert "STM red sonrasi seans durdurma basarisiz" in log


def test_STM_telemetrisi_KAYDEDICI_arizasinda_canli_durum_yine_yazilir(ortam, monkeypatch):
    """Sensör kaydedici kuyruğu istisna atıyor → STM telemetrisinin sıcaklığı canlı duruma yazılır (`objectTemp`, 1 basamak),
    telemetri damgası tazelenir; istisna sızmaz."""
    a = ortam.api

    def _patlayan(*_a, **_k):
        raise RuntimeError("kayıt kuyruğu dolu")

    monkeypatch.setattr(a._sensor_kaydedici, "kaydet_arka_planda", _patlayan)
    a._coil_last_telemetry.pop(STM_BOBIN - 1, None)
    a._handle_backend_event(_olay("hardware.stm.telemetry", coil_id=STM_BOBIN, object_temp=31.46))
    assert a._live_state["coils"][STM_BOBIN - 1]["objectTemp"] == 31.5
    assert (STM_BOBIN - 1) in a._coil_last_telemetry


@pytest.mark.parametrize("deger", ["abc", None, [1]])
def test_akim_SAYI_DEGILSE_guvenilmez_sayilir(ortam, deger):
    """Telemetri akımı sayıya çevrilemiyor (metin / None / liste) → `_akim_guvenilmez_mi` True (ölçüm kabul edilmez)."""
    assert ortam.api._akim_guvenilmez_mi({"current": deger}) is True


def test_alan_tazeligi_GECERSIZ_indeks_atlanir_gecerli_bobin_dusurulur_zirve_hatasi_yutulur(ortam, monkeypatch, caplog):
    """`_coil_olculen_alanlar`da aralık dışı indeks + seans bobininin alan damgası bayat + seans zirvesi okunamıyor →
    geçerli bobinin `measuredFields`'ından "magneticMt" düşer ve `coil_status` yayınlanır, aralık dışı indeks yok sayılır,
    zirve hatası "susan alan sensörünün anlık yoğunluğu temizlenemedi" ile yutulur."""
    a = ortam.api
    idx = STM_BOBIN - 1
    a._coil_olculen_alanlar[99] = {"magneticMt": 0.0}
    a._coil_olculen_alanlar[idx] = {"magneticMt": -1e9}
    with a._live_state_lock:
        a._live_state["coils"][idx]["measuredFields"] = ["magneticMt"]
        monkeypatch.setitem(a._live_state["activeTreatment"], "measuredIntensityCoil", STM_BOBIN)

    def _patlayan():
        raise OSError("alan kaydı okunamadı")

    monkeypatch.setattr(a._seans_alan, "zirve", _patlayan)
    caplog.set_level(logging.ERROR)
    a._olculen_alanlari_tazele()
    assert a._live_state["coils"][idx]["measuredFields"] == []
    durum = [m for m in ortam.yayin if m.get("type") == "coil_status"]
    assert [m["coilId"] for m in durum] == [STM_BOBIN]
    assert "susan alan sensörünün anlık yoğunluğu temizlenemedi" in _mesajlar(caplog)
