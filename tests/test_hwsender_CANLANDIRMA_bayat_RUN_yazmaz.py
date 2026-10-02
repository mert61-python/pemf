# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D1.55 · 1-C bağımsız inceleme i5-F-1 — canlandırılan HWSender, ölü dönemden kalan BAYAT RUN'ı porta yazmaz.

ÖLÇÜLEN KUSUR (293ff1c, i5 iki koşumda 30/30 + 30/30 + 30/30): gönderici ölüyken HC'nin kuyruğa koyduğu paketler
(keep-alive turu, START) hiç tüketilmez. D1.55'in canlandırdığı yeni çalışan önce `connect_serial` ile bağlantıyı
yeniden kurar → kopuş olayı → GERÇEK `api_server._handle_backend_event` → `HardwareController.on_disconnect()` bütün
bobinleri "durdu"ya çeker (oturum varsa acil durdurma + mandal). Ardından kuyruğu FIFO boşaltınca BAYAT RUN porta
yazılıyordu: (a) oturumsuz sürüşte HC "durdu" derken porta son giden paket RUN; (b) E-stop (operatörün ya da kopuşun)
`stop_all_coils` döndükten SONRA porta duty>0 paket. 293ff1c^'de canlandırma yoktu.

KAPI (i5'in ölçüm aparatı): GERÇEK HeadlessCore (HWSender + okuyucu + connect_serial) + GERÇEK HardwareController +
GERÇEK `_emergency_stop_all` / `_handle_backend_event` (taze EventBus). Sahte: TEK ERİŞİMLİ seri taşıma (yazılan her
paket zaman damgalı; yeniden açılışta el sıkışma 0,15 sn), DB açılışları, UDP soketi, MQTT yayını. Paketler firmware
aynasıyla çözülür. 3 kol × 30 deneme.
"""

from __future__ import annotations

import contextlib
import copy
import socket as _gercek_socket
import threading
import time
import types
from collections import Counter
from pathlib import Path

import pytest

_OLUM = pytest.mark.filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")
DENEME = 30


def _bekle(kosul, sure=5.0):
    son = time.monotonic() + sure
    while time.monotonic() < son and not kosul():
        time.sleep(0.005)
    return kosul()


def _duty(paket: bytes):
    from kayitci_donanim import paket_coz

    return list(paket_coz(paket)[0])


def _stop_mu(paket: bytes) -> bool:
    return all(x == 0.0 for x in _duty(paket))


@contextlib.contextmanager
def _aparat(kok: Path, *, olay: bool = False, gecikme: float = 0.0, seans: bool = False, kapatma: float = 0.0):
    import event_bus as eb
    import headless_core as hcm
    from controllers.hardware_controller import HardwareController
    from servers import api_server as api
    from servers import live_state as ls
    from utils import estop_mandali

    estop_mandali.sifirla("test-izolasyon")
    d = types.SimpleNamespace(
        acilan=[],
        yazilan=[],
        port_var=True,
        acilis_mumkun=True,
        gecikme=gecikme,
        kapi=None,
        kapida=threading.Event(),
        kanca=None,
        durdur_bitti=[],
        mqtt=[],
    )

    class _Conn:
        def __init__(self, ad: str):
            self.ad = ad
            self.port = "COM_TEST"
            self.is_open = True

        def readline(self):
            time.sleep(0.02)
            return b""

        def write(self, b):
            b = bytes(b)
            kapi = d.kapi
            if kapi is not None and not kapi.is_set():
                d.kapida.set()
                kapi.wait(10)
            if d.kanca is not None:
                d.kanca(self, b)
            d.yazilan.append((time.perf_counter(), self.ad, b))

        def close(self):
            self.is_open = False

    class _Tasima:
        def __init__(self, *a, **k):
            pass

        def open_and_handshake(self, stop_event=None, on_line=None):
            if not d.acilis_mumkun or any(c.is_open for c in d.acilan):
                return None  # port yok / TEK ERISIM
            c = _Conn(f"C{len(d.acilan)}")
            d.acilan.append(c)
            if len(d.acilan) > 1 and d.gecikme:
                time.sleep(d.gecikme)  # uretimde VCP_SETTLE_TIME_SEC=2,0 + el sikisma
            return types.SimpleNamespace(serial=c)

        def close_serial(self, c):
            if kapatma and c.is_open:
                time.sleep(kapatma)  # gercek COM: okuyucu readline'da blokluyken kapatma ms surebilir
            c.close()

        def port_hala_var(self, _port):
            return d.port_var

    def _soket_yok(*_a, **_k):
        raise OSError("aparat: UDP soketi kurulmaz")

    def _mqtt(topic, payload):
        d.mqtt.append((time.perf_counter(), topic))
        return False

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(hcm, "Stm32SerialTransport", _Tasima)
        mp.setattr(hcm, "_PORT_CHECK_S", 0.05)
        mp.setattr(
            hcm,
            "socket",
            types.SimpleNamespace(
                socket=_soket_yok,
                AF_INET=_gercek_socket.AF_INET,
                SOCK_DGRAM=_gercek_socket.SOCK_DGRAM,
                SOL_SOCKET=_gercek_socket.SOL_SOCKET,
                SO_BROADCAST=_gercek_socket.SO_BROADCAST,
            ),
        )
        mp.setattr(hcm, "get_patient_database", lambda *_a, **_k: object())
        mp.setattr(hcm, "get_session_manager", lambda *_a, **_k: object())
        mp.setattr(api, "_mqtt_publish", _mqtt)
        mp.setattr(api, "_estop_cloud_mirror", lambda *_a, **_k: None)
        mp.setattr(api, "_push_notification", lambda *_a, **_k: None)
        with api._session_lock:
            eski_seans = dict(api._active_session)
        with ls._live_state_lock:
            eski_canli = copy.deepcopy(ls._live_state)
        yeni_bus = None
        if olay:
            yeni_bus = eb.EventBus()
            mp.setattr(eb, "_event_bus_instance", yeni_bus)
            mp.setattr(api, "_event_bus_registered", False)
            api._register_event_bus_handlers()
            bus = yeni_bus
        else:
            bus = types.SimpleNamespace(publish=lambda *_a, **_k: None)
        core = hc = None
        try:
            with api._session_lock:
                api._active_session.clear()
                api._active_session.update({"is_active": False, "coil_ids": []})
            core = hcm.HeadlessCore(kok, start_headless_services=False, event_bus=bus)
            hc = HardwareController(core)
            hc._keep_alive_stop.set()  # paketler yalniz olcum cagrilarindan (ve elle _tick) gelsin
            hc._keep_alive_thread.join(timeout=2)
            mp.setattr(api.state, "hardware", hc)
            if not olay:
                with ls._live_state_lock:
                    ls._live_state["stm"] = "online"
            assert _bekle(lambda: bool(d.acilan) and core.stm_is_connected), "aparat: STM baglanmadi"
            if olay:
                assert _bekle(lambda: ls._live_state["stm"] == "online"), "aparat: canli durum online olmadi"
            if seans:
                with api._session_lock:
                    api._active_session.update(
                        {
                            "is_active": True,
                            "session_id": "i5-seans",
                            "coil_ids": [1],
                            "db_session_id": None,
                            "started_epoch": time.time(),
                            "start_mono": time.monotonic(),
                            "duration_minutes": 0,
                        }
                    )
            yield core, hc, d, api
        finally:
            with api._session_lock:
                api._active_session.clear()
                api._active_session.update({"is_active": False})
            if core is not None:
                core._hw_sender_stop.set()
                for t in list(threading.enumerate()):
                    if getattr(t, "_target", None) == core._hw_sender_worker:
                        t.join(timeout=3)
            for c in d.acilan:
                c.close()
            if hc is not None:
                hc.stop()
            for t in list(threading.enumerate()):
                if t.name.startswith("estop-"):
                    t.join(timeout=5)
            with api._session_lock:
                api._active_session.clear()
                api._active_session.update(eski_seans)
            with ls._live_state_lock:
                ls._live_state.clear()
                ls._live_state.update(eski_canli)
            if yeni_bus is not None:
                yeni_bus.shutdown()
            estop_mandali.sifirla("test-izolasyon")


def _surulen_bobin(hc, d, coil_id: int = 1) -> None:
    once = len(d.yazilan)
    assert hc.update_coil(coil_id, 100.0, 30.0, 0.0, 1, start=True) is True
    assert _bekle(lambda: any(not _stop_mu(b) for _, _, b in d.yazilan[once:]), 3.0), "aparat: RUN yazilmadi"


def _gondericiyi_oldur(core) -> None:
    """D1.55 kapisindaki ayni yontem: `except Exception`in yakalamadigi SystemExit ile HWSender olur
    (okuyucusu ve acik tutamagi geride kalir)."""
    q = core._hw_send_queue
    orj = q.get
    kez = {"n": 0}

    def _olumcul_get(*a, **k):
        if kez["n"] == 0:
            kez["n"] = 1
            raise SystemExit("aparat: HWSender'i oldur")
        return orj(*a, **k)

    q.get = _olumcul_get
    t = core._hw_sender_thread
    assert _bekle(lambda: not t.is_alive(), 3.0), "aparat: gonderici olmedi"


def _durdurma_zamanini_kaydet(hc, d) -> None:
    orj = hc.stop_all_coils

    def _sayan():
        r = orj()
        d.durdur_bitti.append(time.perf_counter())
        return r

    hc.stop_all_coils = _sayan


def _calisan_gondericiler(core) -> list:
    return [t for t in threading.enumerate() if getattr(t, "_target", None) == core._hw_sender_worker and t.is_alive()]


@_OLUM
def test_KRITIK_canlandirma_BAYAT_RUN_yazmaz_HC_durdu_iken_porta_RUN_gitmez_N30(tmp_path):
    kayit, ihlal = [], 0
    for n in range(DENEME):
        with _aparat(tmp_path / f"t{n}", olay=True, gecikme=0.15) as (core, hc, d, api):
            _surulen_bobin(hc, d)
            _gondericiyi_oldur(core)
            n_acilis, once = len(d.acilan), len(d.yazilan)
            hc._tick()  # keep-alive turu (bobin calisiyor): RUN kuyruga + olu gonderici -> canlandirma
            assert _bekle(lambda: len(d.acilan) > n_acilis and core.stm_is_connected, 3.0), "canlandirma baglanmadi"
            _bekle(lambda: core._hw_send_queue.empty() and len(d.yazilan) > once, 2.0)
            time.sleep(0.1)
            durum = hc.coils_state[1]["is_running"]
            for _ in range(3):
                hc._tick()  # keep-alive: HC 'durdu' ise paket gitmez
                time.sleep(0.05)
            time.sleep(0.1)
            yeni = d.yazilan[once:]
            run = [x for x in yeni if not _stop_mu(x[2])]
            # Ölçüt: CANLANDIRMADAN SONRA porta RUN yazıldı mı (HC "durdu" derken). Ölümden ÖNCE yazılmış son RUN'ı ancak
            # firmware ölü-adamı keser (bağlantı yeniden kurulurken STOP gidemez) — o ayrı bir sınıftır; burada ölçülen,
            # ölü dönemde kuyrukta kalan BAYAT RUN'ın canlandırmayla porta GÖNDERİLMESİ.
            if run and not durum:
                ihlal += 1
            kayit.append(
                f"deneme={n:02d} canlandirma_sonrasi_yazim={len(yeni)} RUN={len(run)} "
                f"STOP={len(yeni) - len(run)} baglanti={sorted({x[1] for x in yeni})} HC_bobin1_calisiyor={durum}"
            )
    assert ihlal == 0, (
        f"canlandirma: HC durdu derken canlandırmadan SONRA porta RUN yazıldı {ihlal}/{DENEME} — ilk: {kayit[:1]}"
    )


@_OLUM
@pytest.mark.parametrize("kaynak", ["seans_kopus_olayi", "operator_el_sikisma_sirasinda"])
def test_KRITIK_canlandirma_sirasinda_ESTOP_sonrasi_porta_duty_pozitif_YAZILMAZ_N30(tmp_path, kaynak):
    from utils import estop_mandali

    kayit, ihlal, mandal = [], 0, 0
    for n in range(DENEME):
        seans = kaynak == "seans_kopus_olayi"
        with _aparat(tmp_path / f"t{n}", olay=True, gecikme=0.15, seans=seans) as (core, hc, d, api):
            _surulen_bobin(hc, d)
            _durdurma_zamanini_kaydet(hc, d)
            _gondericiyi_oldur(core)
            n_acilis, once = len(d.acilan), len(d.yazilan)
            hc._tick()  # keep-alive turu: RUN kuyruga + canlandirma (yeni calisan el sikisiyor)
            govde = None
            if not seans:
                govde = api._emergency_stop_all("manual")  # operator, el sikisma surerken ACIL DURDUR
            assert _bekle(lambda: bool(d.durdur_bitti), 5.0), "E-stop stop_all_coils cagrilmadi"
            assert _bekle(lambda: len(d.acilan) > n_acilis and core.stm_is_connected, 3.0)
            _bekle(lambda: core._hw_send_queue.empty(), 2.0)
            for t in list(threading.enumerate()):
                if t.name.startswith("estop-"):
                    t.join(timeout=5)
            time.sleep(0.1)
            t_stop = d.durdur_bitti[0]
            sonra = [x for x in d.yazilan[once:] if x[0] > t_stop]
            run_sonra = [x for x in sonra if not _stop_mu(x[2])]
            stop_sonra = [x for x in sonra if _stop_mu(x[2])]
            if run_sonra:
                ihlal += 1
            if estop_mandali.mandalli_mi():
                mandal += 1
            aralik = (stop_sonra[0][0] - run_sonra[0][0]) * 1000 if (run_sonra and stop_sonra) else None
            kayit.append(
                f"deneme={n:02d} stop_all_SONRASI_yazim={[('RUN' if not _stop_mu(x[2]) else 'STOP') for x in sonra]} "
                f"RUN->STOP_ms={aralik if aralik is None else round(aralik, 3)} "
                f"stmStopped={None if govde is None else govde['stmStopped']} mandal={estop_mandali.mandalli_mi()}"
            )
    kayit.append(f"ORAN ({kaynak}): E-stop stop_all_coils DONDUKTEN SONRA porta duty>0 paket = {ihlal}/{DENEME}")
    kayit.append(f"ORAN ({kaynak}): deneme sonunda mandal kurulu = {mandal}/{DENEME}")
    assert ihlal == 0, f"E-stop sonrasi porta duty>0 yazim {ihlal}/{DENEME} ({kaynak})"


@_OLUM
def test_KRITIK_Y8_olu_donemde_kuyruga_giren_STOP_canlandirmada_KORUNUR_ve_porta_YAZILIR_N30(tmp_path):
    """Ö.4-Y8: ayıklama yalnız RUN/NACK öğelerini atar — gönderici ölüyken kuyruğa giren STOP (ve onu tetikleyen
    canlandırma) porta YAZILIR (STOP gönderimi azalmaz)."""
    ihlal = 0
    ornek = None
    for n in range(DENEME):
        with _aparat(tmp_path / f"t{n}", olay=True, gecikme=0.15) as (core, hc, d, api):
            _surulen_bobin(hc, d)
            _gondericiyi_oldur(core)
            n_acilis, once = len(d.acilan), len(d.yazilan)
            hc.stop_all_coils()  # STOP kuyruğa + ölü gönderici → canlandırma
            assert _bekle(lambda: len(d.acilan) > n_acilis and core.stm_is_connected, 3.0), "canlandirma baglanmadi"
            _bekle(lambda: any(_stop_mu(x[2]) for x in d.yazilan[once:]), 2.0)
            yeni = d.yazilan[once:]
            if not any(_stop_mu(x[2]) for x in yeni):
                ihlal += 1
                ornek = ornek or [("RUN" if not _stop_mu(x[2]) else "STOP", x[1]) for x in yeni]
    assert ihlal == 0, (
        f"ölü dönemde kuyruğa giren STOP canlandırmadan sonra porta YAZILMADI {ihlal}/{DENEME} (örnek {ornek})"
    )
