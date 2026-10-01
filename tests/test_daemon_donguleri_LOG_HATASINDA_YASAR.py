# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D1.18 · B-4.17 — sekiz daemon döngüsü, dış `except`teki günlük çağrısı FIRLATSA da YAŞAR (davranış).

ÖLÇÜLEN (DENETİM-04 B-4.17, sonda D1–D8): her döngüde gövde hatası + modül logger'ı fırlatacak şekilde
yamalıyken sekizinin sekizi de ÖLÜYORDU (KONTROL: aynı gövde hatası, logger sağlam → yaşıyor).
Üretim tetiği nadir (stdlib `Handler.emit` hatayı `handleError`'a verip yutar; yalnız `sys.stderr`
KAPALI bir akışken `handleError`'ın kendisi fırlatır — D0), ama tetiklenirse ilgili servis (uzaktan
erişim tüneli, cihaz kaydı, broker gözetimi, ağ durumu, UDP keşif, DB bakımı/yedeği, mDNS) süreç
ömrü boyunca SESSİZCE durur. Şekil tarayıcısı (`test_dongu_hata_bildirimi_OLDURMEZ.py`) bu döngüleri
görmüyordu; bu kapı ŞEKİLDEN BAĞIMSIZDIR: döngü gerçek iş parçacığında koşar ve canlılığı ölçülür.

Her kol: döngü gerçek iş parçacığında başlar → gövde en az bir tur döner (logger sağlam) → gövde
hatası açılır (ve "patlak" kolunda logger da PermissionError fırlatır) → gövde ≥3 tur DAHA döner
ve iş parçacığı CANLIDIR. Log yolunun gerçekten denendiği (`cagri ≥ 1`) ayrıca iddia edilir —
kapı vakumda geçmez. Gövdeler ve beklemeler sahtedir: ağ, alt süreç, gerçek soket YOK.
"""

from __future__ import annotations

import io
import socket
import sys
import threading
import time
import types

import pytest

#: Hata açıldıktan sonra beklenen ek tur ve süre üst sınırı.
EK_TUR = 3
SURE_S = 5.0


class _Logger:
    """Sağlamken sayar; `patlat` kurulunca HER çağrıda fırlatır (Windows kilitli log / kapalı akış)."""

    def __init__(self):
        self.patlat = threading.Event()
        self.cagri = 0

    def _cagir(self, *a, **k):
        self.cagri += 1
        if self.patlat.is_set():
            raise PermissionError(13, "log dosyasi kilitli (test)")

    debug = info = warning = warn = error = exception = critical = _cagir

    def log(self, *a, **k):
        self._cagir()

    def isEnabledFor(self, *_a):
        return True


class _HizliOlay(threading.Event):
    """Döngülerin dakikalık/saatlik beklemelerini test süresine indirir (durdurma anlamı aynı)."""

    def wait(self, timeout=None):
        return super().wait(0.01 if timeout is None else min(float(timeout), 0.01))


class _SahteBus:
    def publish(self, *a, **k):
        return None


class _Senaryo:
    def __init__(self):
        self.lg = _Logger()
        self.hata = threading.Event()  # gövde hatası açık mı
        self.tur = 0
        self.ek_tur = EK_TUR
        self.thread: threading.Thread | None = None
        self.durdur = lambda: None

    def govde(self, deger=None):
        self.tur += 1
        if self.hata.is_set():
            raise RuntimeError("GOVDE-HATASI (test)")
        return deger


# ── sekiz döngünün kurulumları (her biri `s.thread` ve `s.durdur`u doldurur) ─────────────────────


def _tunel(s, mp):
    import servers.tunnel_manager as tm

    mp.setattr(tm, "logger", s.lg)
    mp.setattr(tm, "_internet_up", lambda: s.govde(False))  # sağlamken "çevrimdışı" → bekle, devam
    mp.setattr(tm, "_watchdog_thread", None)
    tm.start_tunnel_watchdog(port=8000, check_interval=0.01)
    s.thread = tm._watchdog_thread

    def durdur():
        tm._watchdog_stop.set()
        s.thread.join(SURE_S)
        tm._watchdog_stop.clear()

    s.durdur = durdur


def _bulut_senkron(s, mp):
    import servers.sync_worker as sw

    mp.setattr(sw, "logger", s.lg)
    mp.setattr(sw, "get_patient_database", lambda *a, **k: object())
    mp.setattr(sw, "get_treatment_db", lambda *a, **k: object())
    w = sw.CloudSyncWorker("", "", interval_sec=0.01)  # boş yapılandırma: istemci KURULMAZ (ağ yok)
    w.client = object()
    w.supabase_url, w.supabase_key = "https://ornek.invalid", "x"
    w.patient_sync_enabled = True  # iki dış except'in ikisi de koşsun (:yayın ve :hasta senkronu)
    w._publish_device_registry = lambda: s.govde(True)
    w._sync_patients = lambda _db: s.govde()
    w._sync_sessions = lambda _db: None
    s.thread = threading.Thread(target=w._sync_loop, daemon=True, name="test-CloudSyncWorker")
    s.thread.start()

    def durdur():
        w.stop_event.set()
        s.thread.join(SURE_S)

    s.durdur = durdur


def _guncelleme(s, mp):
    import servers.update_manager as um

    mp.setenv("PEMF_LEGACY_EXE_UPDATE", "1")
    mp.setattr(um, "logger", s.lg)
    mp.setattr(um, "_stop", _HizliOlay())
    mp.setattr(um, "sweep_stale_update_temp", lambda: None)
    mp.setattr(um, "check_for_update", lambda: s.govde({"available": False}))
    mp.setattr(um, "_check_thread", None)
    um.start_update_checker(interval_sec=0.01)
    s.thread = um._check_thread

    def durdur():
        um._stop.set()
        s.thread.join(SURE_S)

    s.durdur = durdur


def _mosquitto(s, mp):
    import services.headless_services as hs

    mp.setattr(hs, "logger", s.lg)
    svc = hs.MosquittoSupervisor(interval_seconds=0.01, ensure_running=False, start_mdns=False, event_bus=_SahteBus())
    svc.check_once = lambda: s.govde({"running": True})
    svc.start()
    s.thread = svc._thread

    def durdur():
        svc._stop_event.set()
        s.thread.join(SURE_S)

    s.durdur = durdur


def _ag_durumu(s, mp):
    import services.headless_services as hs

    mp.setattr(hs, "logger", s.lg)
    svc = hs.NetworkStatusService(interval_seconds=0.01, event_bus=_SahteBus())
    svc.check_once = lambda: s.govde({})
    svc.start()
    s.thread = svc._thread

    def durdur():
        svc._stop_event.set()
        s.thread.join(SURE_S)

    s.durdur = durdur


def _udp_kesif(s, mp):
    import services.headless_services as hs

    class _SahteSoket:
        def recvfrom(self, _n):
            time.sleep(0.005)
            s.tur += 1
            if s.hata.is_set():  # gövde hatası = soket hatası → dış except + `_reopen_socket` yolu
                raise OSError("GOVDE-HATASI soket (test)")
            raise socket.timeout()  # sağlamken boş tur

        def close(self):
            pass

    svc = hs.UdpDiscoveryService(discovery_port=5051, event_bus=_SahteBus(), logger_instance=s.lg)
    svc._stop_event = _HizliOlay()

    def _ac():  # gerçek bind YOK
        svc._socket = _SahteSoket()

    svc._open_socket = _ac
    svc.start()
    s.thread = svc._thread

    def durdur():
        svc._stop_event.set()
        s.thread.join(SURE_S)

    s.durdur = durdur


def _db_bakim(s, mp):
    import services.headless_db_maintenance as hdm

    mp.setattr(hdm, "logger", s.lg)
    svc = hdm.HeadlessDBMaintenance.__new__(hdm.HeadlessDBMaintenance)  # gerçek DB AÇILMAZ
    svc._stop, svc._thread = _HizliOlay(), None
    svc.disk_interval, svc.maint_interval, svc.backup_interval = 0, 10**9, 10**9
    svc._check_disk = lambda: s.govde()
    svc._run_maintenance = lambda: None
    svc._run_backup = lambda: None
    svc._recent_backup_exists = lambda: True
    svc.start()
    s.thread = svc._thread

    def durdur():
        svc._stop.set()
        s.thread.join(SURE_S)

    s.durdur = durdur


def _mdns(s, mp, kurulum_hep_patlar=True):
    import services.mdns_service as ms
    import utils.zeroconf_singleton as zs

    mp.setattr(ms, "logger", s.lg)
    mp.setattr(ms, "time", types.SimpleNamespace(time=time.time, sleep=lambda _s: time.sleep(0.005)))
    svc = ms.MDNSService()

    def kurulum():
        if kurulum_hep_patlar:
            raise RuntimeError("mDNS kurulum hatasi (test)")

    svc._ip_monitor_kurulum = kurulum
    mp.setattr(zs, "ensure_interfaces_current", lambda: s.govde())
    svc._running = True
    s.ek_tur = 12  # `hata_sayisi % 10 == 0` uyarı dalı da koşsun
    s.thread = threading.Thread(target=svc._ip_monitor_loop, daemon=True, name="test-MDNS-IPMonitor")
    s.thread.start()

    def durdur():
        svc._running = False
        s.thread.join(SURE_S)

    s.durdur = durdur


DONGULER = {
    "tunel_bekcisi": _tunel,
    "bulut_senkron": _bulut_senkron,
    "guncelleme_denetleyici": _guncelleme,
    "mosquitto_gozetmeni": _mosquitto,
    "ag_durumu": _ag_durumu,
    "udp_kesif": _udp_kesif,
    "db_bakim": _db_bakim,
    "mdns_ip_izleyici": _mdns,
}


def _bekle(kosul, sure=SURE_S) -> bool:
    son = time.monotonic() + sure
    while time.monotonic() < son:
        if kosul():
            return True
        time.sleep(0.005)
    return kosul()


@pytest.fixture()
def sahte_stderr(monkeypatch):
    akis = io.StringIO()
    monkeypatch.setattr(sys, "__stderr__", akis)  # `dongu_hatasini_bildir` son çare kanalı
    return akis


@pytest.mark.parametrize("patlak", [False, True], ids=["KONTROL_logger_saglam", "logger_PATLAK"])
@pytest.mark.parametrize("ad", list(DONGULER))
def test_KRITIK_daemon_dongusu_govde_ve_LOG_hatasinda_YASAR(ad, patlak, monkeypatch, sahte_stderr):
    s = _Senaryo()
    try:
        DONGULER[ad](s, monkeypatch)
        assert s.thread is not None and _bekle(lambda: s.tur >= 1), f"{ad}: döngü hiç dönmedi (aparat)"
        once = s.lg.cagri
        if patlak:
            s.lg.patlat.set()
        s.hata.set()
        n0 = s.tur
        dondu = _bekle(lambda: s.tur >= n0 + s.ek_tur)
        canli = s.thread.is_alive()
    finally:
        s.lg.patlat.clear()  # kapanış günlükleri ("stopped") iş parçacığını istisnayla bitirmesin
        s.durdur()
    assert not s.thread.is_alive(), f"{ad}: durdurulamadı (aparat)"
    assert dondu and canli, (
        f"{ad}: gövde hatası{' + LOG hatası' if patlak else ''} sonrası döngü ÖLDÜ "
        f"(hatadan sonra {s.tur - n0} tur, canlı={canli}) — servis süreç ömrü boyunca sessizce durur"
    )
    assert s.lg.cagri > once, f"{ad}: hata yolu günlüğe hiç uğramadı — kapı vakumda"
    if patlak:
        assert "logging BASARISIZ" in sahte_stderr.getvalue(), f"{ad}: son çare kanalı (stderr) kullanılmadı"


def test_KRITIK_mdns_ILK_kurulum_hatasi_LOG_patlakken_dongu_YASAR(monkeypatch, sahte_stderr):
    """`hata_sayisi == 1` dalı yalnız ilk turda koşar: logger baştan patlak, kurulum ilk turda düşer."""
    s = _Senaryo()
    s.lg.patlat.set()
    try:
        _mdns(s, monkeypatch, kurulum_hep_patlar=True)
        dondu = _bekle(lambda: s.tur >= EK_TUR)
        canli = s.thread.is_alive()
    finally:
        s.lg.patlat.clear()
        s.durdur()
    assert dondu and canli, f"mDNS ilk kurulum hatası + log hatası döngüyü ÖLDÜRDÜ ({s.tur} tur)"
    assert s.lg.cagri >= 1


# ── yardımcının D1.18 eki: `%` argümanları ve `exc_info=False` günlük İÇERİĞİNİ değiştirmez ──────────


def _kayitci_logger():
    import logging

    kayitlar: list = []

    class _Toplayici(logging.Handler):
        def emit(self, record):
            kayitlar.append(record)

    lg = logging.getLogger("d118_yardimci_testi")
    lg.handlers = [_Toplayici()]
    lg.propagate = False
    lg.setLevel(logging.DEBUG)
    return lg, kayitlar


def test_yardimci_ARGUMANLI_ve_yigin_izsiz_cagri_eski_gunluk_kaydiyla_AYNI():
    """`logger.warning("... %s", exc)` → `dongu_hatasini_bildir("... %s", exc, seviye=WARNING, exc_info=False)`:
    mesaj, seviye ve "yığın izi yok" AYNEN korunur (sarmalama yalnız fırlatmamayı ekler)."""
    import logging

    from utils.dongu_guvenligi import dongu_hatasini_bildir

    lg, kayitlar = _kayitci_logger()
    try:
        raise OSError("soket-42")
    except OSError as e:
        assert dongu_hatasini_bildir("UDP hatasi: %s", e, logger=lg, seviye=logging.WARNING, exc_info=False) == "logger"
        assert dongu_hatasini_bildir("tur hatasi", logger=lg) == "logger"
    assert [r.getMessage() for r in kayitlar] == ["UDP hatasi: soket-42", "tur hatasi"]
    assert [r.levelno for r in kayitlar] == [logging.WARNING, logging.ERROR]
    assert not kayitlar[0].exc_info, "exc_info=False iken yığın izi EKLENDİ — günlük içeriği değişti"
    assert kayitlar[1].exc_info and kayitlar[1].exc_info[1].args == ("soket-42",), "varsayılan yığın izi kayboldu"


def test_yardimci_logger_PATLARSA_argumanli_mesaj_STDERRE_bicimlenir(sahte_stderr):
    from utils.dongu_guvenligi import dongu_hatasini_bildir

    lg = _Logger()
    lg.patlat.set()
    try:
        raise OSError("soket-42")
    except OSError as e:
        assert dongu_hatasini_bildir("UDP hatasi: %s", e, logger=lg, exc_info=False) == "stderr"
    metin = sahte_stderr.getvalue()
    assert "UDP hatasi: soket-42" in metin and "logging BASARISIZ" in metin, metin
