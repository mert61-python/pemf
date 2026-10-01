# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D1.55 · B-1.23 — HWSender ÖLÜRSE STOP teyidi YALAN SÖYLEMEZ; döngü tur hatasında ölmez, ölürse yeniden başlar.

ÖLÇÜLEN KUSUR (plan tv-F4_1): HWSender döngüsünün dış koruması yoktu; tek bir istisna (port yoklaması, kuyruk,
yeniden bağlanma iş parçacığı başlatma) göndericiyi ÖLDÜRÜYORDU. Sonra `HardwareController._send_stm_manual_update`
paketi kuyruğa koyup True dönüyor, `stop_all_coils` True, E-stop `stmStopped=True` yayınlıyordu — porta 0 bayt
(ölü göndericide stop_all ×5 True, yazım 4→4). Tek koruma firmware ölü-adam devresiydi (1,5 sn). Zincir C1-11:
D1.105 (A-63) teyidi STM'e bağladığında bu yalan "teyitli E-stop" olurdu — bu yüzden B-1.23 ÖNCE.

Kapı GERÇEK `HeadlessCore` (yalnız DB açılışları sahte; HWSender GERÇEK) + GERÇEK `HardwareController` + GERÇEK
`/api/hardware/emergency_stop` ile koşar. Sahte olan: TEK ERİŞİMLİ seri taşıma (önceki tutamak açıkken port açılmaz
— Windows COM portu gibi; porta yazılan her paket zaman damgalı kaydedilir), modülün `socket`'i ve olay veriyolu.
Ölçüt HTTP değil PORTA YAZILAN BAYTLAR; paketler firmware aynasıyla çözülür (`kayitci_donanim.paket_coz`).

Ö.4-Y8: hiçbir iddia STOP'u kapılamaz — gönderici ölü ve canlandırılamazken bile STOP durumu yazılır ve paket
kuyrukta KALIR; yalnız RAPORLANAN teyit dürüstleşir.
"""

from __future__ import annotations

import socket as _gercek_socket
import threading
import time
import types

import pytest


def _bekle(kosul, sure=5.0):
    son = time.monotonic() + sure
    while time.monotonic() < son and not kosul():
        time.sleep(0.01)
    return kosul()


def _stop_mu(paket: bytes) -> bool:
    """Firmware aynasıyla çözülen paketin TÜM bobin duty'leri 0 mı (NACK'lenecek paket → AssertionError)."""
    from kayitci_donanim import paket_coz

    return all(d == 0.0 for d in paket_coz(paket)[0])


@pytest.fixture
def aparat(monkeypatch, tmp_path, request):
    import headless_core as hcm
    from controllers.hardware_controller import HardwareController
    from servers import live_state as _ls

    d = types.SimpleNamespace(
        acilan=[], yazilan=[], port_var=True, port_patlat=0, acilis_mumkun=True, yazim_patlat=False
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
            if d.yazim_patlat:
                raise OSError(22, "test: WriteFile basarisiz (USB yari kopuk)")
            d.yazilan.append((time.perf_counter(), self.ad, bytes(b)))

        def close(self):
            self.is_open = False

    class _Tasima:
        def __init__(self, *a, **k):
            pass

        def open_and_handshake(self, stop_event=None, on_line=None):
            if not d.acilis_mumkun or any(c.is_open for c in d.acilan):
                return None  # port yok / TEK ERİŞİM: önceki tutamak kapanmadan port açılamaz
            c = _Conn(f"C{len(d.acilan)}")
            d.acilan.append(c)
            return types.SimpleNamespace(serial=c)

        def close_serial(self, c):
            c.close()

        def port_hala_var(self, _port):
            if d.port_patlat:
                d.port_patlat -= 1
                raise RuntimeError("test: port numaralandirmasi BIR KEZ patladi")
            return d.port_var

    def _soket_yok(*_a, **_k):
        raise OSError("test: UDP soketi kurulmaz")

    monkeypatch.setattr(hcm, "Stm32SerialTransport", _Tasima)
    monkeypatch.setattr(hcm, "_PORT_CHECK_S", 0.05)
    monkeypatch.setattr(
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
    monkeypatch.setattr(hcm, "get_patient_database", lambda *_a, **_k: object())
    monkeypatch.setattr(hcm, "get_session_manager", lambda *_a, **_k: object())
    ayar = getattr(request, "param", None) or {}
    d.ilk_patlama = {"n": 0}
    if ayar.get("ilk_baglanti_patlat"):
        # İlk bağlantı denemesinin İLK durum geçişi fırlatır (ör. okuyucu iş parçacığı başlatılamadı) — bu
        # çağrı çalışanın döngüsünden ÖNCE, korumasız `connect_serial()` içindeydi.
        _orj_set = hcm.HeadlessCore._set_stm_connected

        def _ilk_kez_patlak(self, connected):
            if d.ilk_patlama["n"] == 0:
                d.ilk_patlama["n"] = 1
                raise RuntimeError("test: ilk baglanti denemesi patladi")
            return _orj_set(self, connected)

        monkeypatch.setattr(hcm.HeadlessCore, "_set_stm_connected", _ilk_kez_patlak)
    bus = types.SimpleNamespace(publish=lambda *_a, **_k: None)
    core = hcm.HeadlessCore(tmp_path / "veri", start_headless_services=False, event_bus=bus)
    with _ls._live_state_lock:
        eski_stm = _ls._live_state["stm"]
        _ls._live_state["stm"] = "online"
    hc = HardwareController(core)
    hc._keep_alive_stop.set()  # paketler yalnız test edilen çağrılardan gelsin
    hc._keep_alive_thread.join(timeout=2)
    try:
        d.baglandi = _bekle(lambda: bool(d.acilan) and core.stm_is_connected)
        if not ayar.get("ilk_baglanti_patlat"):
            assert d.baglandi, f"aparat: STM baglanmadi {d}"
        yield core, hc, d
    finally:
        core._hw_sender_stop.set()
        core._hw_sender_thread.join(timeout=3)
        for c in d.acilan:
            c.close()
        hc.stop()
        with _ls._live_state_lock:
            _ls._live_state["stm"] = eski_stm


def _surulen_bobin(hc, d, coil_id: int = 1) -> None:
    """Senaryo: STOP'tan ÖNCE bobin GERÇEKTEN sürülür ve porta duty>0 paket yazılır (yoksa 'son paket duty 0'
    her pakette zaten doğrudur)."""
    assert hc.update_coil(coil_id, 100.0, 30.0, 0.0, 1, start=True) is True
    assert _bekle(lambda: any(not _stop_mu(b) for _, _, b in d.yazilan), 3.0), "aparat: surus paketi porta yazilmadi"


def _gondericiyi_oldur(core) -> None:
    """Göndericiyi `except Exception`ın YAKALAMADIĞI bir istisnayla öldürür (iş parçacığı sessizce biter; okuyucusu
    ve açık tutamağı geride kalır — ölü çalışanın portu TUTTUĞU gerçek durum)."""
    q = core._hw_send_queue
    orj = q.get
    kez = {"n": 0}

    def _olumcul_get(*a, **k):
        if kez["n"] == 0:
            kez["n"] = 1
            raise SystemExit("test: HWSender'i oldur")
        return orj(*a, **k)

    q.get = _olumcul_get
    t = core._hw_sender_thread
    assert _bekle(lambda: not t.is_alive(), 3.0), "aparat: gonderici olmedi"


def _acil_durdur(monkeypatch, hc):
    from fastapi.testclient import TestClient
    from servers import api_server as api

    monkeypatch.setattr(api.state, "hardware", hc)
    # ESP yayını bu kapının konusu değil; False → ack bekçisi iş parçacığı DOĞMAZ (teste taşmasın).
    monkeypatch.setattr(api, "_mqtt_publish", lambda topic, payload: False)
    monkeypatch.setitem(api._active_session, "is_active", False)
    r = TestClient(api.app).post("/api/hardware/emergency_stop")
    return r, time.perf_counter()


# Göndericiyi bilerek öldürüyoruz (SystemExit iş parçacığında) — pytest bunu "işlenmemiş iş parçacığı istisnası" uyarısı sayar.
_OLUM_UYARISI = pytest.mark.filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")


@pytest.mark.parametrize("nokta", ["kuyruk", "port_yoklama"])
def test_KRITIK_tur_hatasi_HWSender_OLDURMEZ_STOP_porta_YAZILIR(aparat, nokta):
    core, hc, d = aparat
    _surulen_bobin(hc, d)
    t0 = core._hw_sender_thread
    if nokta == "kuyruk":
        q = core._hw_send_queue
        orj = q.get
        kez = {"n": 0}

        def _patlak_get(*a, **k):
            if kez["n"] == 0:
                kez["n"] = 1
                raise RuntimeError("test: kuyruk BIR KEZ patladi")
            return orj(*a, **k)

        q.get = _patlak_get
        assert _bekle(lambda: kez["n"] == 1, 3.0), "aparat: enjeksiyon tetiklenmedi"
    else:
        d.port_patlat = 1
        assert _bekle(lambda: d.port_patlat == 0, 3.0), "aparat: enjeksiyon tetiklenmedi"
    time.sleep(0.2)
    canli_sonra = t0.is_alive()
    yazim_once = len(d.yazilan)
    assert hc.stop_all_coils() is True
    assert _bekle(lambda: any(_stop_mu(b) for _, _, b in d.yazilan[yazim_once:]), 3.0), (
        f"tur hatasindan sonra STOP porta YAZILMADI ({nokta})"
    )
    assert canli_sonra and core._hw_sender_thread is t0, (
        f"TEK bir tur hatasi ({nokta}) HWSender'i OLDURDU — STOP ancak yeniden baslatmayla yazilabildi"
    )
    assert len(d.acilan) == 1, f"tur hatasi baglantiyi dusurdu / yeniden baglanma gerekti: {len(d.acilan)} acilis"


@_OLUM_UYARISI
def test_KRITIK_OLU_gonderici_YENIDEN_BASLAR_ve_STOP_porta_YAZILIR(aparat):
    """Plan ölçütü: ölü göndericiden sonra `stop_all_coils` YA porta STOP baytı yazdırır (gönderici yeniden
    başladıysa) YA DA False döner. True deyip yazmamak (bugünkü yalan) yasak; yeniden başlatma da pinlenir."""
    core, hc, d = aparat
    _surulen_bobin(hc, d)
    t0 = core._hw_sender_thread
    _gondericiyi_oldur(core)
    yazim_once = len(d.yazilan)
    ok = hc.stop_all_coils()
    stop_yazildi = _bekle(lambda: any(_stop_mu(b) for _, _, b in d.yazilan[yazim_once:]), 3.0)
    assert not (ok and not stop_yazildi), (
        f"stop_all_coils True dedi ama STOP porta YAZILMADI (yazim {yazim_once}→{len(d.yazilan)}) — "
        "E-stop bunu stmStopped diye yayinlar (B-1.23)"
    )
    yeni = core._hw_sender_thread
    assert yeni is not t0 and yeni.is_alive(), "olu gonderici yeniden BASLATILMADI"
    assert ok is True and stop_yazildi, "yeniden baslayan gonderici STOP'u porta yazmadi"
    assert len(d.acilan) == 2 and not d.acilan[0].is_open, (
        "eski (olu calisanin) tutamagi kapatilmadi — tek erisimli portta yeni baglanti kurulamazdi"
    )


@_OLUM_UYARISI
def test_KRITIK_OLU_gonderici_CANLANDIRILAMAZSA_STOP_False_START_RED_STOP_yine_KUYRUKTA(aparat, monkeypatch):
    import headless_core as hcm

    core, hc, d = aparat
    _surulen_bobin(hc, d, coil_id=2)
    _gondericiyi_oldur(core)

    class _BaslamayanIsParcacigi(threading.Thread):
        def start(self):
            raise RuntimeError("can't start new thread (test: is parcacigi tukenmesi)")

    monkeypatch.setattr(
        hcm,
        "threading",
        types.SimpleNamespace(
            Thread=_BaslamayanIsParcacigi,
            Lock=threading.Lock,
            RLock=threading.RLock,
            Event=threading.Event,
            Condition=threading.Condition,
        ),
    )
    yazim_once = len(d.yazilan)

    # STOP: durum YİNE sıfırlanır ve paket kuyrukta KALIR (Y8), ama "verildi" DENMEZ.
    assert hc.stop_all_coils() is False, "olu ve canlandirilamayan gondericide stop_all 'kuyruga verildi' dedi"
    assert not any(s["is_running"] for s in hc.coils_state.values()), "STOP durumu YAZILMADI (Y8 ihlali)"
    kuyruk = list(core._hw_send_queue.queue)
    assert kuyruk and _stop_mu(kuyruk[-1][0]), "STOP paketi kuyruga KONMADI (gonderim azaldi — Y8 ihlali)"
    assert hc.update_coil(3, 0, 0, 0, 0, start=False) is False, "tekil STOP 'verildi' dedi"

    # START reddedilir ve durum YAZILMAZ (gönderici dönünce keep-alive bobini habersiz enerjilemesin).
    assert hc.update_coil(1, 100.0, 30.0, 0.0, 1, start=True) is False, "olu gondericide START 'basarili' dondu"
    assert hc.coils_state[1]["is_running"] is False, "reddedilen START durumu YAZDI"
    assert hc.start_all_coils(100.0, 30.0, 0.0, 1) is False, "olu gondericide start_all 'basarili' dondu"
    assert not any(s["is_running"] for s in hc.coils_state.values())

    r, _ = _acil_durdur(monkeypatch, hc)
    assert r.status_code == 200, f"ACIL DURDUR {r.status_code} — E-stop hicbir kosulda reddedilmez (Y8)"
    assert r.json()["stmStopped"] is False, f"porta 0 bayt giderken stmStopped True: {r.json()!r}"
    assert len(d.yazilan) == yazim_once, "aparat: olu gondericiye ragmen porta yazim oldu"


@pytest.mark.parametrize("hat", ["saglikli", "kablo_cikik", "yazim_hatasi"])
def test_KRITIK_ACIL_DURDUR_stmStopped_YALNIZ_STOP_porta_YAZILDIYSA(aparat, monkeypatch, hat):
    """`stmStopped`: STOP baytları yanıt dönmeden ÖNCE porta yazıldı. Kuyruğa vermek YETMEZ (gönderici canlı ama
    bağlantı yoksa paket porta hiç gitmez). KARŞIT: sağlıklı hatta True ve yazım yanıttan önce."""
    core, hc, d = aparat
    _surulen_bobin(hc, d)
    if hat == "kablo_cikik":
        d.acilis_mumkun = False
        d.port_var = False
        assert _bekle(lambda: not core.stm_is_connected and not any(c.is_open for c in d.acilan), 3.0), (
            "aparat: kablo cekildi ama gonderici baglantiyi dusurmedi"
        )
    elif hat == "yazim_hatasi":
        d.acilis_mumkun = False  # yazım hatası portu kapatır; yeniden açılış başka bir yazım getirmesin
        d.yazim_patlat = True
    yazim_once = len(d.yazilan)
    r, t_yanit = _acil_durdur(monkeypatch, hc)
    assert r.status_code == 200
    govde = r.json()
    stop_yanittan_once = [ts for ts, _, b in d.yazilan[yazim_once:] if _stop_mu(b) and ts <= t_yanit]
    if govde["stmStopped"] is True:
        assert stop_yanittan_once, f"stmStopped True ama yanit donerken STOP porta YAZILMAMISTI ({hat}): {govde!r}"
    if hat == "saglikli":
        assert govde["stmStopped"] is True and stop_yanittan_once, f"saglikli hatta STOP teyidi yok: {govde!r}"
    else:
        assert govde["stmStopped"] is False, f"STOP porta yazilamadi ({hat}) ama stmStopped True: {govde!r}"


def test_KRITIK_yazim_izi_YALNIZ_STOP_paketini_STOP_sayar(aparat):
    """`hw_stop_yazildi_bekle`: işaretten SONRA yazılan RUN paketi STOP SAYILMAZ; tüm-duty-0 paketi sayılır.
    (Bir bobin sürülürken diğerlerinin duty'si 0'dır — "herhangi biri 0" ölçütü RUN'ı STOP sanardı.)"""
    core, hc, d = aparat
    isaret = core.hw_yazim_isareti()
    yazim_once = len(d.yazilan)
    assert hc.update_coil(1, 100.0, 30.0, 0.0, 1, start=True) is True
    assert _bekle(lambda: len(d.yazilan) > yazim_once, 3.0), "aparat: RUN paketi porta yazilmadi"
    assert not _stop_mu(d.yazilan[-1][2]), "aparat: yazilan paket RUN degil"
    assert core.hw_stop_yazildi_bekle(isaret, 0.3) is False, "porta yalniz RUN yazilmisken 'STOP yazildi' dendi"
    assert hc.stop_all_coils() is True
    assert core.hw_stop_yazildi_bekle(isaret, 3.0) is True, "STOP porta yazildi ama yazim izi gormedi"


@pytest.mark.parametrize("aparat", [{"ilk_baglanti_patlat": True}], indirect=True)
def test_KRITIK_ilk_baglanti_denemesi_patlasa_da_HWSender_DONGUYE_girer(aparat):
    """Çalışanın döngü ÖNCESİ ilk `connect_serial()` çağrısı korumasızdı: orada bir istisna (okuyucu iş parçacığı
    başlatılamaması, durum bildirimi) göndericiyi DAHA DÖNGÜYE GİRMEDEN öldürüyordu — hiç bağlanmaz, kuyruktaki
    hiçbir paket (STOP dahil) yazılmazdı. Artık döngüye girer ve yeniden bağlanma toparlar."""
    core, hc, d = aparat
    assert d.ilk_patlama["n"] == 1, "aparat: ilk deneme patlatilamadi"
    assert core._hw_sender_thread.is_alive(), "ilk baglanti denemesindeki istisna HWSender'i OLDURDU"
    assert d.baglandi, f"ilk deneme patlayinca STM bir daha BAGLANMADI {d}"
    _surulen_bobin(hc, d)
    yazim_once = len(d.yazilan)
    assert hc.stop_all_coils() is True
    assert _bekle(lambda: any(_stop_mu(b) for _, _, b in d.yazilan[yazim_once:]), 3.0), "STOP porta yazilmadi"
