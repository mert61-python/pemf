"""KP-1 · apps/backend/services/headless_services.py · sözleşmeler: `MosquittoSupervisor` — izleyici / mDNS yaşam döngüsü, durum okuma,
broker başlatma zinciri (çalışıyorsa dokunma → kayıtlı servise `net start` → ayrık süreç), Popen bayrakları, ikili / yapılandırma arama
(paketli, donmuş paket, POSIX), Linux LAN yapılandırması, kimlik parçası onarımı (Y71) hata / yabancı süreç / yeniden başlatılamama dalları,
servis PID'i, süreç sonlandırma, port kapanma beklemesi, izleme döngüsü üstel geri çekilmesi, sürüm / servis yoklaması hata dalları,
olay yayını hatası.

Sahte EN ALT katta: modülün KENDİ `platform` / `socket` / `subprocess` (run + Popen kaydedici — gerçek mosquitto / net / sc / tasklist /
systemctl ÇALIŞMAZ) / `time` (monotonic + sleep sahte saat) / `os.kill` / `sys` (donmuş paket senaryosu) adları gerçek modüle devreden
vekille; `ctypes.WinDLL` kayıtlı sahte kernel32 (süreç listesi). mDNS hizmeti kayıtçı sınıf: gerçeği zeroconf ile 5353'te çoklu yayın
DİNLER (dinleyici port yasak) — bu dosyada yalnız gözetmenin onu nasıl sürdüğü sınanır. `utils.mqtt_kimlik`, `utils.platform_support`,
`utils.path_utils` GERÇEK (tmp kökler: APPDATA / LOCALAPPDATA / PEMF_DEVICE_IDENTITY_DIR / PEMF_DATA_DIR).
"""

from __future__ import annotations

import ctypes
import errno
import logging
import os
import platform as _gercek_platform
import signal
import socket as _gercek_soket
import subprocess as _gercek_sp
import sys
import threading
import time as _gercek_time
from pathlib import Path
from types import SimpleNamespace

import pytest
from event_bus import EventPriority
from services import headless_services as hs

PORT = 18830
SC_CALISIYOR = "SERVICE_NAME: mosquitto\n        STATE              : 4  RUNNING\n"
SC_DURMUS = "SERVICE_NAME: mosquitto\n        STATE              : 1  STOPPED\n"
LINUX_VARSAYILAN = (
    "listener 18830 0.0.0.0\nallow_anonymous true\npersistence false\n"
    "max_queued_messages 10000\nmax_connections 30\nmax_keepalive 120\n"
)


class _Vekil:
    """Gerçek modüle devreden vekil: yalnız verilen adlar sahte."""

    def __init__(self, gercek, **sahte):
        self.__dict__["_gercek"] = gercek
        self.__dict__.update(sahte)

    def __getattr__(self, ad):
        return getattr(self.__dict__["_gercek"], ad)


class _Platform:
    def __init__(self):
        self.ad = "Windows"

    def system(self):
        return self.ad


class _Soket:
    def __init__(self, ag):
        self.ag = ag
        self.zaman = None

    def settimeout(self, t):
        self.zaman = t

    def connect_ex(self, adres):
        self.ag.kayit.append((adres, self.zaman))
        acik = self.ag.acik_mi(adres) if self.ag.acik_mi else adres in self.ag.acik
        return 0 if acik else errno.ECONNREFUSED

    def close(self):
        pass


class _Ag:
    def __init__(self):
        self.acik: set = set()
        self.kayit: list = []
        self.acik_mi = None

    def socket(self, *a):
        return _Soket(self)


class _Surecler:
    """`subprocess.run` (yanıt (ad, ilk argüman) anahtarıyla — (rc, stdout[, stderr]) / istisna / çağrılabilir) + `Popen` kaydedici.
    Başarılı Popen broker portunu AÇAR (gerçek broker'ın dinlemeye başlaması)."""

    def __init__(self, o):
        self.o = o
        self.cagri: list = []
        self.popen: list = []
        self.popen_hatasi = None
        self.yanit = {
            ("sc", "query"): (1060, "", "[SC] OpenService FAILED 1060"),
            ("sc", "queryex"): (1060, "", "[SC] OpenService FAILED 1060"),
            ("tasklist", "/FI"): (0, "INFO: No tasks are running which match the specified criteria.\n"),
            ("systemctl", "is-enabled"): (1, ""),
            ("mosquitto.exe", "-h"): (3, "", "mosquitto version 2.0.18\n"),
        }

    @staticmethod
    def anahtar(args):
        return (Path(str(args[0])).name.lower(), str(args[1]) if len(args) > 1 else "")

    def run(self, args, **kw):
        a = self.anahtar(args)
        self.cagri.append((a, list(args), kw))
        if a not in self.yanit:
            raise AssertionError(f"beklenmeyen alt süreç: {args}")
        y = self.yanit[a]
        if callable(y) and not isinstance(y, BaseException):
            y = y(args)
        if isinstance(y, BaseException):
            raise y
        return _gercek_sp.CompletedProcess(args, y[0], y[1], y[2] if len(y) > 2 else "")

    def say(self, a):
        return sum(1 for c in self.cagri if c[0] == a)

    def Popen(self, args, **kw):
        self.popen.append((list(args), kw))
        if self.popen_hatasi is not None:
            raise self.popen_hatasi
        self.o.ag.acik.add(("127.0.0.1", self.o.port))
        return object()


class _Saat:
    def __init__(self):
        self.t = 1000.0
        self.uykular: list = []

    def monotonic(self):
        return self.t

    def sleep(self, s):
        self.uykular.append(s)
        self.t += s


class _Olaylar:
    def __init__(self):
        self.yayinlar: list = []
        self.hata = None

    def publish(self, tur, veri, **kw):
        if self.hata is not None:
            raise self.hata
        self.yayinlar.append((tur, veri, kw))


class _Fn:
    def __init__(self, f):
        self.f = f
        self.restype = None
        self.argtypes = None

    def __call__(self, *a):
        return self.f(*a)


class _Kernel32:
    """Sahte kernel32 süreç listesi: [(pid, exe_adi, tam_yol)]."""

    def __init__(self, surecler):
        self.surecler = list(surecler)
        self._yollar = {p: y for p, _, y in self.surecler}
        self._i = 0
        self.CreateToolhelp32Snapshot = _Fn(lambda bayrak, pid: 0x1234)
        self.Process32FirstW = _Fn(self._ilk)
        self.Process32NextW = _Fn(self._doldur_)
        self.OpenProcess = _Fn(lambda erisim, devral, pid: 0x5000 + int(pid))
        self.QueryFullProcessImageNameW = _Fn(self._yol)
        self.CloseHandle = _Fn(lambda h: None)

    def _doldur_(self, anlik, ref):
        if self._i >= len(self.surecler):
            return 0
        pid, ad, _ = self.surecler[self._i]
        ref._obj.th32ProcessID = pid
        ref._obj.szExeFile = ad
        self._i += 1
        return 1

    def _ilk(self, anlik, ref):
        self._i = 0
        return self._doldur_(anlik, ref)

    def _yol(self, tutamac, bayrak, tampon, boy_ref):
        tampon.value = self._yollar[tutamac - 0x5000]
        return 1


def _kernel32_kur(monkeypatch, k32):
    monkeypatch.setattr(ctypes, "WinDLL", lambda ad, use_last_error=False: k32, raising=False)


@pytest.fixture
def o(monkeypatch, tmp_path):
    from utils import mqtt_kimlik, path_utils

    d = SimpleNamespace(tmp=tmp_path, port=PORT, oldurulen=[], oldurme_hatasi=None, mp=monkeypatch, mk=mqtt_kimlik)
    d.plat = _Platform()
    d.ag = _Ag()
    d.sp = _Surecler(d)
    d.saat = _Saat()
    d.bus = _Olaylar()

    def _kill(pid, sig):
        d.oldurulen.append((pid, sig))
        if d.oldurme_hatasi is not None:
            raise d.oldurme_hatasi
        d.ag.acik.discard(("127.0.0.1", PORT))

    monkeypatch.setattr(hs, "platform", _Vekil(_gercek_platform, system=d.plat.system))
    monkeypatch.setattr(hs, "socket", _Vekil(_gercek_soket, socket=d.ag.socket))
    monkeypatch.setattr(
        hs,
        "subprocess",
        _Vekil(_gercek_sp, run=d.sp.run, Popen=d.sp.Popen, CREATE_NO_WINDOW=0x08000000, DETACHED_PROCESS=0x00000008),
    )
    monkeypatch.setattr(hs, "time", _Vekil(_gercek_time, monotonic=d.saat.monotonic, sleep=d.saat.sleep))
    monkeypatch.setattr(hs, "os", _Vekil(os, kill=_kill))
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "yerel"))
    monkeypatch.setenv("PEMF_DEVICE_IDENTITY_DIR", str(tmp_path / "makine"))
    monkeypatch.setenv("PEMF_DATA_DIR", str(tmp_path / "veri"))
    for ad in ("PEMF_MQTT_BIND", "PEMF_MQTT_REQUIRE_AUTH", "PEMF_MQTT_PASSWORD_FILE"):
        monkeypatch.delenv(ad, raising=False)
    monkeypatch.setattr(hs.MosquittoSupervisor, "MOSQUITTO_EXE_PATHS", [str(tmp_path / "pf" / "mosquitto.exe")])
    monkeypatch.setattr(
        path_utils, "_GOC_YAPILDI", set(path_utils._GOC_YAPILDI)
    )  # süreç-başı göç işareti testte kirlenmesin
    mqtt_kimlik._onbellek.clear()
    yield d
    mqtt_kimlik._onbellek.clear()


@pytest.fixture
def mdns(monkeypatch):
    from services import mdns_service

    kayit = SimpleNamespace(ornekler=[], hata={}, calisiyor=True, ip="192.168.137.1")

    class _Mdns:
        def __init__(self, mqtt_port=1883):
            self.mqtt_port = mqtt_port
            self.olaylar: list = []
            kayit.ornekler.append(self)

        def _adim(self, ad):
            self.olaylar.append(ad)
            if ad in kayit.hata:
                raise kayit.hata[ad]

        def start(self):
            self._adim("start")
            return True

        def stop(self):
            self._adim("stop")

        def is_running(self):
            self._adim("is_running")
            return kayit.calisiyor

        def get_current_ip(self):
            self._adim("get_current_ip")
            return kayit.ip

    monkeypatch.setattr(mdns_service, "MDNSService", _Mdns)
    return kayit


@pytest.fixture
def is_parcaciklari(monkeypatch, mdns):
    kayit: list = []

    class _Thread:
        def __init__(self, target=None, name=None, daemon=None):
            self.target, self.name, self.daemon = target, name, daemon
            self.basladi = False
            self.bekleme = None
            self.mdns_onceden = None
            kayit.append(self)

        def start(self):
            self.basladi = True
            self.mdns_onceden = [list(m.olaylar) for m in mdns.ornekler]

        def is_alive(self):
            return self.basladi

        def join(self, timeout=None):
            self.bekleme = timeout
            self.basladi = False

    monkeypatch.setattr(hs, "threading", _Vekil(threading, Thread=_Thread))
    return kayit


class _SayacliOlay:
    """`threading.Event` yerine: wait(t) kaydedilir (gerçek bekleme yok); `dur_sonra` beklemeden sonra olay kurulur."""

    def __init__(self, dur_sonra, her_bekleme=None):
        self.dur_sonra = dur_sonra
        self.her_bekleme = her_bekleme
        self.bekleme: list = []
        self._kurulu = False

    def is_set(self):
        return self._kurulu

    def set(self):
        self._kurulu = True

    def clear(self):
        self._kurulu = False

    def wait(self, t=None):
        self.bekleme.append(t)
        if self.her_bekleme:
            self.her_bekleme(len(self.bekleme))
        if len(self.bekleme) >= self.dur_sonra:
            self._kurulu = True
        return self._kurulu


def _sup(o, **kw):
    ayar = dict(port=PORT, interval_seconds=10.0, ensure_running=True, start_mdns=False, event_bus=o.bus)
    ayar.update(kw)
    return hs.MosquittoSupervisor(**ayar)


def _kurulum(o, conf=True):
    """Paketli broker: %APPDATA%\\PEMF_GUI\\mosquitto\\mosquitto.exe (+ yanında taban conf)."""
    d = o.tmp / "appdata" / "PEMF_GUI" / "mosquitto"
    d.mkdir(parents=True, exist_ok=True)
    exe = d / "mosquitto.exe"
    exe.write_bytes(b"MZ")
    if conf:
        (d / "mosquitto.conf").write_text("listener 18830 0.0.0.0\nallow_anonymous true\n", encoding="utf-8")
    return exe


def _donmus(o, **ek):
    paket = o.tmp / "paket"
    paket.mkdir(exist_ok=True)
    ayar = {"frozen": True, "executable": str(paket / "PEMF.exe")}
    ayar.update(ek)
    o.mp.setattr(hs, "sys", _Vekil(sys, **ayar))
    return paket


def _ikili_yok(o):
    """Donmuş paket, paket / APPDATA / ek adaylarda ikili YOK, PATH boş dizin → `_find_mosquitto_exe` None."""
    _donmus(o)
    o.mp.setenv("PATH", str(o.tmp / "bos_path"))


def _onarilacak_kimlik(o):
    """Kaldır-kur: kimlik deposu VAR (gerçek `hazirla`), broker dosyaları silinmiş → `parcayi_onar` "onarildi" döner."""
    bd = o.mk.varsayilan_broker_dizini()
    o.mk.hazirla(bd)
    for ad in (o.mk.PASSWD_ADI, o.mk.ACL_ADI):
        (bd / ad).unlink()
    for p in (bd / o.mk.CONF_DIZINI).glob("*"):
        p.unlink()
    o.mk._onbellek.clear()
    return bd


# ───────────────────────────── yaşam döngüsü · mDNS · durum ─────────────────────────────


class _CanliIs:
    def is_alive(self):
        return True

    def join(self, timeout=None):
        pass


def test_start_izleyici_ZATEN_canliysa_IKINCI_is_parcacigi_ve_mdns_ACILMAZ(o, mdns, is_parcaciklari):
    """İzleme iş parçacığı canlıyken start → yeni Thread yok, mDNS başlatılmaz, durdurma bayrağı TEMİZLENMEZ."""
    sup = _sup(o, start_mdns=True)
    canli = _CanliIs()
    sup._thread = canli
    sup._stop_event.set()
    sup.start()
    assert sup._thread is canli and is_parcaciklari == [] and mdns.ornekler == []
    assert sup._stop_event.is_set()


def test_start_mDNS_istenirse_BROKER_portuyla_izleyiciden_ONCE_baslar_stop_BEKLER_ve_mdnsi_BIRAKIR(
    o, mdns, is_parcaciklari
):
    """start_mdns=True → MDNSService(mqtt_port=port).start() izleme iş parçacığından ÖNCE; iş parçacığı hedefi `_monitor_loop`, adı
    "MosquittoSupervisor", daemon; durdurma bayrağı temizlenir. stop → bayrak kurulur, join(3.0), mDNS durdurulup bırakılır."""
    sup = _sup(o, start_mdns=True)
    sup._stop_event.set()
    sup.start()
    (m,) = mdns.ornekler
    assert m.mqtt_port == PORT and m.olaylar == ["start"]
    (t,) = is_parcaciklari
    assert t.target == sup._monitor_loop and t.name == "MosquittoSupervisor" and t.daemon is True and t.basladi
    assert t.mdns_onceden == [["start"]]
    assert not sup._stop_event.is_set()
    sup.stop()
    assert sup._stop_event.is_set() and t.bekleme == 3.0
    assert m.olaylar == ["start", "stop"] and sup._mdns_service is None


def test_mdns_BASLATILAMAZSA_uyari_ve_izleyici_YINE_baslar(o, mdns, is_parcaciklari, caplog):
    """MDNSService.start OSError → "MQTT mDNS could not start" uyarısı (istisna sızmaz); izleme iş parçacığı yine başlatılır."""
    mdns.hata["start"] = OSError(10048, "5353 kullanimda")
    sup = _sup(o, start_mdns=True)
    with caplog.at_level(logging.WARNING, logger=hs.logger.name):
        sup.start()
    assert "MQTT mDNS could not start" in caplog.text and "5353 kullanimda" in caplog.text
    assert len(is_parcaciklari) == 1 and is_parcaciklari[0].basladi


def test_mdns_DURDURMA_hatasi_uyari_ve_hizmet_YINE_birakilir_ikinci_durdurma_SESSIZ(o, mdns, caplog):
    """mDNS stop RuntimeError → "MQTT mDNS stop failed" uyarısı + hizmet None; hizmet yokken `_stop_mdns` hiçbir şey çağırmaz."""
    sup = _sup(o, start_mdns=True)
    sup._start_mdns()
    (m,) = mdns.ornekler
    mdns.hata["stop"] = RuntimeError("zeroconf kapali")
    with caplog.at_level(logging.WARNING, logger=hs.logger.name):
        sup._stop_mdns()
    assert sup._mdns_service is None and "MQTT mDNS stop failed" in caplog.text
    sup._stop_mdns()
    assert m.olaylar == ["start", "stop"]


def test_durum_mDNS_CANLI_degerlerini_tasir_okunamazsa_KAYITLI_degerler_kalir(o, mdns):
    """get_status: mDNS varsa is_running / get_current_ip kopyaya yazılır (iç durum DEĞİŞMEZ); okuma fırlatırsa kayıtlı değerler
    (False / None) döner."""
    sup = _sup(o, start_mdns=True)
    sup._start_mdns()
    d = sup.get_status()
    assert (d["mdns_running"], d["mdns_ip"], d["port"]) == (True, "192.168.137.1", PORT)
    assert sup._status["mdns_running"] is False and sup._status["mdns_ip"] is None
    mdns.hata["is_running"] = RuntimeError("zeroconf kapandi")
    d2 = sup.get_status()
    assert (d2["mdns_running"], d2["mdns_ip"]) == (False, None)


# ───────────────────────────── broker başlatma zinciri ─────────────────────────────


def test_broker_ZATEN_calisiyorsa_net_start_ve_SUREC_yok(o):
    """Kayıtlı servis RUNNING → start_broker True; `net start` yok, Popen yok, bekleme yok."""
    _kurulum(o)
    o.sp.yanit[("sc", "query")] = (0, SC_CALISIYOR)
    assert _sup(o).start_broker() is True
    assert o.sp.say(("net", "start")) == 0 and o.sp.popen == [] and o.saat.uykular == []


def test_KAYITLI_durmus_servis_net_start_ile_baslar_TEYIT_taze_sorguyla(o):
    """Windows + servis kayıtlı STOPPED → `net start mosquitto` (15 sn) rc 0 → 1 sn bekleme, önbellek boşaltılıp TAZE `sc query`
    teyidi; True, Popen YOK; durum running True ve `mqtt.broker.status` yayını running True."""
    _kurulum(o)
    durum = {"calisiyor": False}
    o.sp.yanit[("sc", "query")] = lambda a: (0, SC_CALISIYOR if durum["calisiyor"] else SC_DURMUS)

    def _net(a):
        durum["calisiyor"] = True
        return (0, "mosquitto hizmeti basariyla baslatildi.\n")

    o.sp.yanit[("net", "start")] = _net
    sup = _sup(o)
    assert sup.start_broker() is True
    ((_, args, kw),) = [c for c in o.sp.cagri if c[0] == ("net", "start")]
    assert args == ["net", "start", "mosquitto"] and kw["timeout"] == 15
    assert o.saat.uykular == [1]
    assert o.sp.say(("sc", "query")) == 2 and o.sp.popen == []
    assert sup.get_status()["running"] is True
    ((_, veri, _),) = [y for y in o.bus.yayinlar if y[0] == "mqtt.broker.status"]
    assert veri["running"] is True and veri["service_exists"] is True


def test_net_start_REDDEDILIRSE_uyari_ve_DOGRUDAN_ayrik_surec_taban_confla(o, caplog):
    """`net start` rc 2 → stderr'li "Mosquitto service start failed" uyarısı; ardından paketli ikili `-c <yanındaki conf>` ile
    CREATE_NO_WINDOW | DETACHED_PROCESS bayraklı AYRIK süreç; 1 sn bekleme; True."""
    exe = _kurulum(o)
    o.sp.yanit[("sc", "query")] = (0, SC_DURMUS)
    o.sp.yanit[("net", "start")] = (2, "", "Sistem hatasi 5 olustu.\r\nErisim engellendi.\r\n")
    with caplog.at_level(logging.WARNING, logger=hs.logger.name):
        assert _sup(o).start_broker() is True
    assert "Mosquitto service start failed: Sistem hatasi 5 olustu." in caplog.text
    ((args, kw),) = o.sp.popen
    assert args == [str(exe), "-c", str(exe.parent / "mosquitto.conf")]
    assert kw == {"creationflags": 0x08000000 | 0x00000008}
    assert o.saat.uykular == [1]


def test_net_start_ZAMAN_ASIMI_uyari_ve_SURECE_duser(o, caplog):
    """`net start` TimeoutExpired → uyarı (istisna sızmaz) ve doğrudan süreç başlatılır."""
    _kurulum(o)
    o.sp.yanit[("sc", "query")] = (0, SC_DURMUS)
    o.sp.yanit[("net", "start")] = _gercek_sp.TimeoutExpired(["net", "start", "mosquitto"], 15)
    with caplog.at_level(logging.WARNING, logger=hs.logger.name):
        assert _sup(o).start_broker() is True
    assert "Mosquitto service start failed" in caplog.text and "timed out" in caplog.text
    assert len(o.sp.popen) == 1


def test_POSIXte_broker_YENI_oturumda_ayrik_baslar(o):
    """platform Linux → Popen bayrakları yalnız {"start_new_session": True}."""
    o.plat.ad = "Linux"
    assert _sup(o)._broker_popen_kwargs() == {"start_new_session": True}


def test_ikili_BULUNAMAZSA_YUKSEK_oncelikli_hata_olayi_SUREC_baslatilmaz(o):
    """İkili yok → False; Popen yok, bekleme yok; tek olay `mqtt.broker.error` {"message": "Mosquitto executable or service was not
    found."} HIGH öncelikli."""
    _ikili_yok(o)
    assert _sup(o)._launch_broker_process() is False
    assert o.sp.popen == [] and o.saat.uykular == []
    assert o.bus.yayinlar == [
        (
            "mqtt.broker.error",
            {"message": "Mosquitto executable or service was not found."},
            {"priority": EventPriority.HIGH, "source": "mosquitto_supervisor"},
        )
    ]


def test_LINUXta_yaninda_conf_olmayan_ikili_URETILEN_LAN_confiyla_YENI_oturumda_baslar(o):
    """Linux + donmuş paketteki ikilinin yanında / paket dizinlerinde conf yok → veri kökünde LAN yapılandırması ÜRETİLİR
    (0.0.0.0 + anonim) ve `-c` ile verilir; Popen start_new_session; True."""
    o.plat.ad = "Linux"
    paket = _donmus(o)
    exe = paket / "bin" / "mosquitto" / "mosquitto.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"\x7fELF")
    assert _sup(o)._launch_broker_process() is True
    ((args, kw),) = o.sp.popen
    conf = o.tmp / "veri" / "PEMF_GUI" / "mosquitto.conf"
    assert Path(args[0]).resolve() == exe.resolve() and args[1:] == ["-c", str(conf)]
    assert kw == {"start_new_session": True}
    assert conf.read_text(encoding="utf-8") == LINUX_VARSAYILAN


def test_surec_BASLATILAMAZSA_False_ve_YUKSEK_oncelikli_hata_olayi_BEKLEMEZ(o, caplog):
    """Popen PermissionError → False; `mqtt.broker.error` "Mosquitto process start failed: …" HIGH; bekleme yok; uyarı günlükte."""
    _kurulum(o)
    o.sp.popen_hatasi = PermissionError(13, "Erisim engellendi")
    with caplog.at_level(logging.WARNING, logger=hs.logger.name):
        assert _sup(o)._launch_broker_process() is False
    ((tur, veri, kw),) = o.bus.yayinlar
    assert tur == "mqtt.broker.error" and veri["message"].startswith("Mosquitto process start failed: ")
    assert "Erisim engellendi" in veri["message"] and kw["priority"] == EventPriority.HIGH
    assert o.saat.uykular == [] and "Mosquitto process start failed" in caplog.text


# ───────────────────────────── Y71 kimlik parçası onarımı ─────────────────────────────


def test_kimlik_deposu_dizini_KURULAMAZSA_onarim_HATA_doner_broker_DOKUNULMAZ(o, monkeypatch, caplog):
    """Kimlik deposu kökü bir DOSYA (mkdir FileExistsError) → "hata" + "Y71: broker kimlik parcasi denetlenemedi"; süreç sonlandırma /
    başlatma YOK."""
    engel = o.tmp / "makine_dosya"
    engel.write_text("x", encoding="utf-8")
    monkeypatch.setenv("PEMF_DEVICE_IDENTITY_DIR", str(engel))
    with caplog.at_level(logging.WARNING, logger=hs.logger.name):
        assert _sup(o)._kimlik_parcasini_onar() == "hata"
    assert "Y71: broker kimlik parcasi denetlenemedi" in caplog.text
    assert o.sp.popen == [] and o.oldurulen == []


def test_onarilan_kimlik_ama_portu_YABANCI_surec_tutuyor_servis_YOK_yeniden_baslatma_YOK(o, monkeypatch, caplog):
    """Parça onarıldı + port açık, ama çalışan mosquitto.exe backend'in ikilisi DEĞİL ve servis kayıtlı değil → "onarildi" + "backend'in
    KENDI broker'i tutmuyor" uyarısı; sonlandırma / başlatma YOK."""
    _onarilacak_kimlik(o)
    _kurulum(o)
    o.ag.acik.add(("127.0.0.1", PORT))
    _kernel32_kur(monkeypatch, _Kernel32([(777, "mosquitto.exe", r"C:\baska\mosquitto.exe")]))
    with caplog.at_level(logging.WARNING, logger=hs.logger.name):
        assert _sup(o)._kimlik_parcasini_onar() == "onarildi"
    assert "1883'u backend'in KENDI broker'i tutmuyor" in caplog.text
    assert o.oldurulen == [] and o.sp.popen == []


def test_KENDI_broker_sonlandirilir_ama_yeniden_BASLATILAMAZSA_onarildi_doner(o, monkeypatch):
    """Kendi ikilisinden çalışan süreç (4242) SIGTERM ile sonlandırılır (yabancı 4343'e dokunulmaz), port kapanır, yeniden başlatma
    denenir (Popen OSError) → "yeniden_baslatildi" DEĞİL "onarildi"."""
    _onarilacak_kimlik(o)
    exe = _kurulum(o)
    o.ag.acik.add(("127.0.0.1", PORT))
    _kernel32_kur(
        monkeypatch, _Kernel32([(4242, "mosquitto.exe", str(exe)), (4343, "mosquitto.exe", r"C:\baska\mosquitto.exe")])
    )
    o.sp.popen_hatasi = OSError(errno.ENOENT, "mosquitto.exe bulunamadi")
    assert _sup(o)._kimlik_parcasini_onar() == "onarildi"
    assert o.oldurulen == [(4242, signal.SIGTERM)]
    assert len(o.sp.popen) == 1 and o.sp.popen[0][0][0] == str(exe)


def test_servis_PIDi_windows_DISINDA_None_PID_0_ya_da_sorgu_BASARISIZ_None_PATLARSA_None(o, caplog):
    """Linux → None (sorgu yok); `sc queryex` PID 4242 → 4242; PID 0 → None; rc≠0 (PID metni olsa da) → None; TimeoutExpired → None."""
    sup = _sup(o)
    o.plat.ad = "Linux"
    assert sup._servis_pid() is None and o.sp.cagri == []
    o.plat.ad = "Windows"
    o.sp.yanit[("sc", "queryex")] = (0, "SERVICE_NAME: mosquitto\n  STATE : 4 RUNNING\n  PID : 4242\n")
    assert sup._servis_pid() == 4242
    o.sp.yanit[("sc", "queryex")] = (0, "SERVICE_NAME: mosquitto\n  STATE : 1 STOPPED\n  PID : 0\n")
    assert sup._servis_pid() is None
    o.sp.yanit[("sc", "queryex")] = (1060, "PID : 4242\n")
    assert sup._servis_pid() is None
    o.sp.yanit[("sc", "queryex")] = _gercek_sp.TimeoutExpired(["sc", "queryex", "mosquitto"], 5)
    with caplog.at_level(logging.DEBUG, logger=hs.logger.name):
        assert sup._servis_pid() is None
    assert "mosquitto servis PID'i okunamadi" in caplog.text


def test_surec_sonlandirma_SIGTERM_ile_REDDEDILIRSE_uyari_FIRLATMAZ(o, caplog):
    """`_sureci_sonlandir("4242")` → os.kill(4242, SIGTERM); PermissionError → "sonlandirilamadi" uyarısı, istisna sızmaz."""
    sup = _sup(o)
    sup._sureci_sonlandir("4242")
    assert o.oldurulen == [(4242, signal.SIGTERM)]
    o.oldurme_hatasi = PermissionError(13, "Access is denied")
    with caplog.at_level(logging.WARNING, logger=hs.logger.name):
        sup._sureci_sonlandir(4243)
    assert o.oldurulen[-1] == (4243, signal.SIGTERM)
    assert "Y71: broker sureci (pid 4243) sonlandirilamadi" in caplog.text


def test_port_kapanmasi_0_2sn_ARALIKLA_yoklanir_kapaninca_DONER(o):
    """Port iki yoklamada açık, üçüncüde kapalı → iki kez 0,2 sn bekleme; her yoklama 0,5 sn zaman aşımlı yerel broker portuna."""
    kalan = [2]

    def acik_mi(adres):
        kalan[0] -= 1
        return kalan[0] >= 0

    o.ag.acik_mi = acik_mi
    _sup(o)._port_kapanmasini_bekle()
    assert o.saat.uykular == [0.2, 0.2]
    assert o.ag.kayit == [(("127.0.0.1", PORT), 0.5)] * 3


def test_port_HIC_kapanmazsa_EN_COK_verilen_sure_kadar_bekler(o):
    """Port hep açık → yalnız 0,2 sn adımlarla, toplam ≈ sure_sn (1,0 sn; en çok bir adım taşma) sonra döner (sonsuz döngü yok)."""
    o.ag.acik.add(("127.0.0.1", PORT))
    t0 = o.saat.t
    _sup(o)._port_kapanmasini_bekle(sure_sn=1.0)
    assert set(o.saat.uykular) == {0.2}
    assert 1.0 <= o.saat.t - t0 <= 1.2 + 1e-9


# ───────────────────────────── izleme döngüsü ─────────────────────────────


def test_izleme_dongusu_kimlik_ONARIMI_patlasa_da_DONGU_surer(o, monkeypatch, caplog):
    """Açılış onarımı ("onarildi" + port açık) ikili aramasında patlar (donmuş paket, `sys.executable` None — Python belgesi:
    yorumlayıcı yolu alınamazsa None) → "Y71: kimlik parcasi onarimi basarisiz" uyarısı; döngü YİNE tur atar (tur hatası bildirilir) ve
    aralık kadar bekler; süreç sonlandırma / başlatma YOK."""
    _onarilacak_kimlik(o)
    o.ag.acik.add(("127.0.0.1", PORT))
    monkeypatch.setattr(hs, "sys", _Vekil(sys, frozen=True, executable=None))
    sup = _sup(o, interval_seconds=7.0)
    sup._stop_event = olay = _SayacliOlay(dur_sonra=1)
    with caplog.at_level(logging.WARNING, logger=hs.logger.name):
        sup._monitor_loop()
    assert "Y71: kimlik parcasi onarimi basarisiz" in caplog.text
    assert "Mosquitto monitor error" in caplog.text
    assert olay.bekleme == [7.0]
    assert o.sp.popen == [] and o.oldurulen == []


def test_baslatilamayan_broker_USTEL_geri_cekilmeyle_denenir_UST_SINIR_300sn_uyari_TEK(o, caplog):
    """ensure_running + broker başlatılamıyor (ikili yok) → bekleme aralık·2^min(n,5), üst sınır 300 sn: 20,40,80,160,300,300,300;
    "Mosquitto baslatilamadi" uyarısı YALNIZ ilk başarısızlıkta; her denemede `mqtt.broker.error`."""
    _ikili_yok(o)
    sup = _sup(o, interval_seconds=10.0)
    sup._stop_event = olay = _SayacliOlay(dur_sonra=7)
    with caplog.at_level(logging.WARNING, logger=hs.logger.name):
        sup._monitor_loop()
    assert olay.bekleme == [20.0, 40.0, 80.0, 160.0, 300.0, 300.0, 300.0]
    assert caplog.text.count("Mosquitto baslatilamadi") == 1
    assert sum(1 for y in o.bus.yayinlar if y[0] == "mqtt.broker.error") == 7


def test_broker_ayaga_KALKINCA_geri_cekilme_SIFIRLANIR(o):
    """İki başarısızlık (20, 40) → broker portu açılınca normal aralık (10) → yeniden düşünce geri çekilme BAŞTAN (20)."""
    _ikili_yok(o)

    def _her(n):
        if n == 2:
            o.ag.acik.add(("127.0.0.1", PORT))
        if n == 3:
            o.ag.acik.discard(("127.0.0.1", PORT))

    sup = _sup(o, interval_seconds=10.0)
    sup._stop_event = olay = _SayacliOlay(dur_sonra=4, her_bekleme=_her)
    sup._monitor_loop()
    assert olay.bekleme == [20.0, 40.0, 10.0, 20.0]


# ───────────────────────────── ikili / yapılandırma arama ─────────────────────────────


def test_paket_dizinleri_DONMUS_exede_APPDATA_exe_yani_ve_MEIPASS_sirasiyla(o, monkeypatch):
    """Donmuş: [%APPDATA%\\PEMF_GUI\\mosquitto, <exe dizini>\\bin\\mosquitto, <_MEIPASS>\\bin\\mosquitto]; APPDATA ve _MEIPASS
    yoksa yalnız exe yanı."""
    paket = _donmus(o, _MEIPASS=str(o.tmp / "mei"))
    sup = _sup(o)
    exe_yani = Path(str(paket / "PEMF.exe")).resolve().parent / "bin" / "mosquitto"
    assert sup._mosquitto_bundle_dirs() == [
        o.tmp / "appdata" / "PEMF_GUI" / "mosquitto",
        exe_yani,
        o.tmp / "mei" / "bin" / "mosquitto",
    ]
    monkeypatch.delenv("APPDATA")
    _donmus(o)
    assert sup._mosquitto_bundle_dirs() == [exe_yani]


@pytest.fixture
def casus(monkeypatch):
    """`platform_support.find_executable` GEÇİRGEN casus: argümanları kaydeder, GERÇEK aramayı yapar."""
    from utils import platform_support as ps

    kayit: list = []
    gercek = ps.find_executable

    def _casus(stem, bundle_dirs=(), extra=(), prefer_system=None):
        bundle_dirs, extra = list(bundle_dirs), list(extra)
        kayit.append((stem, bundle_dirs, extra))
        return gercek(stem, bundle_dirs, extra=extra, prefer_system=prefer_system)

    monkeypatch.setattr(ps, "find_executable", _casus)
    return SimpleNamespace(kayit=kayit, ps=ps)


def test_ikili_arama_WINDOWSta_PAKETLI_dizin_once_ek_adaylar_PROGRAM_yollari(o, casus, monkeypatch):
    """Windows → "mosquitto" kökü, ilk paket dizini %APPDATA%\\PEMF_GUI\\mosquitto, ek adaylar = MOSQUITTO_EXE_PATHS; paketli ikili
    bulunur."""
    monkeypatch.setattr(casus.ps, "IS_WIN", True)
    exe = _kurulum(o, conf=False)
    assert _sup(o)._find_mosquitto_exe() == exe
    ((stem, dizinler, ek),) = casus.kayit
    assert stem == "mosquitto" and dizinler[0] == o.tmp / "appdata" / "PEMF_GUI" / "mosquitto"
    assert ek == [o.tmp / "pf" / "mosquitto.exe"]


def test_ikili_arama_POSIXte_ek_adaylar_SISTEM_yollari_paketli_uzantisiz_bulunur(o, casus, monkeypatch):
    """POSIX → ek adaylar apt / yerel / Homebrew sistem yolları (sırayla); PATH'te yokken paket dizinindeki uzantısız ikili bulunur."""
    monkeypatch.setattr(casus.ps, "IS_WIN", False)
    monkeypatch.setenv("PATH", str(o.tmp / "bos_path"))
    d = o.tmp / "appdata" / "PEMF_GUI" / "mosquitto"
    d.mkdir(parents=True)
    paketli = d / "mosquitto"
    paketli.write_bytes(b"\x7fELF")
    assert _sup(o)._find_mosquitto_exe() == paketli
    ((_, _, ek),) = casus.kayit
    assert ek == [
        Path(p)
        for p in (
            "/usr/sbin/mosquitto",
            "/usr/bin/mosquitto",
            "/usr/local/sbin/mosquitto",
            "/usr/local/bin/mosquitto",
            "/opt/homebrew/sbin/mosquitto",
            "/opt/homebrew/bin/mosquitto",
        )
    ]


def test_kimlik_HAZIRKEN_taban_conf_OKUNAMAZSA_taban_AYNEN_doner_calisma_kopyasi_YAZILMAZ(o, caplog):
    """Kimlik hazır (depo + passwd + acl) ama taban conf yok (okuma FileNotFoundError) → taban yolu AYNEN + "Broker kimlik parcasi
    eklenemedi (taban kullaniliyor)" uyarısı; hesaba özel çalışma kopyası oluşmaz."""
    bd = o.mk.varsayilan_broker_dizini()
    bd.mkdir(parents=True, exist_ok=True)
    o.mk._depo_yolu().write_text("{}", encoding="utf-8")
    (bd / o.mk.PASSWD_ADI).write_text("x", encoding="utf-8")
    (bd / o.mk.ACL_ADI).write_text("x", encoding="utf-8")
    assert o.mk.calisma_kopyasi_yonergeleri(bd) is not None  # ön koşul: kimlik HAZIR sayılır
    taban = o.tmp / "kurulum_yok" / "mosquitto.conf"
    with caplog.at_level(logging.WARNING, logger=hs.logger.name):
        assert _sup(o)._kimlik_dahil_conf(taban) == taban
    assert "Broker kimlik parcasi eklenemedi (taban kullaniliyor)" in caplog.text
    assert not (o.tmp / "yerel" / "PEMF_System" / "mosquitto" / "pemf_calisma.conf").exists()


def test_linux_broker_conf_VARSAYILAN_tum_arayuzler_ANONIM_ve_SINIRLAR(o):
    """Ortam yok → veri kökü/PEMF_GUI/mosquitto.conf: listener <port> 0.0.0.0, anonim açık, kalıcılık yok, kuyruk / bağlantı / keepalive
    sınırları."""
    conf = _sup(o)._ensure_linux_broker_config()
    assert conf == o.tmp / "veri" / "PEMF_GUI" / "mosquitto.conf"
    assert conf.read_text(encoding="utf-8") == LINUX_VARSAYILAN


def test_linux_broker_conf_KIMLIK_zorunluysa_anonim_KAPALI_parola_dosyasi_YALNIZ_verilirse(o, monkeypatch):
    """PEMF_MQTT_BIND (kırpılır) + REQUIRE_AUTH=1 + PASSWORD_FILE → listener o adres, anonim false, password_file satırı SONDA;
    parola dosyası yoksa satır yok; boş BIND → 0.0.0.0; REQUIRE_AUTH≠1 → anonim true ve parola dosyası YAZILMAZ."""
    sup = _sup(o)
    monkeypatch.setenv("PEMF_MQTT_BIND", " 192.168.137.1 ")
    monkeypatch.setenv("PEMF_MQTT_REQUIRE_AUTH", "1")
    monkeypatch.setenv("PEMF_MQTT_PASSWORD_FILE", " /etc/mosquitto/pemf_passwd ")
    s = sup._ensure_linux_broker_config().read_text(encoding="utf-8").splitlines()
    assert s[:2] == ["listener 18830 192.168.137.1", "allow_anonymous false"]
    assert s[-1] == "password_file /etc/mosquitto/pemf_passwd" and len(s) == 7
    monkeypatch.delenv("PEMF_MQTT_PASSWORD_FILE")
    monkeypatch.setenv("PEMF_MQTT_BIND", "   ")
    s = sup._ensure_linux_broker_config().read_text(encoding="utf-8").splitlines()
    assert s[:2] == ["listener 18830 0.0.0.0", "allow_anonymous false"] and len(s) == 6
    monkeypatch.setenv("PEMF_MQTT_REQUIRE_AUTH", "0")
    monkeypatch.setenv("PEMF_MQTT_PASSWORD_FILE", "/etc/mosquitto/pemf_passwd")
    s = sup._ensure_linux_broker_config().read_text(encoding="utf-8").splitlines()
    assert s[1] == "allow_anonymous true" and not any(x.startswith("password_file") for x in s)


def test_linux_broker_conf_YAZILAMAZSA_None_ve_UYARI(o, monkeypatch, caplog):
    """Veri kökü bir DOSYANIN altında (mkdir hatası) → None + "Linux broker config yazilamadi" (istisna sızmaz)."""
    engel = o.tmp / "engel"
    engel.write_text("dosya", encoding="utf-8")
    monkeypatch.setenv("PEMF_DATA_DIR", str(engel))
    with caplog.at_level(logging.WARNING, logger=hs.logger.name):
        assert _sup(o)._ensure_linux_broker_config() is None
    assert "Linux broker config yazilamadi" in caplog.text


# ───────────────────────────── sürüm · servis yoklaması · yayın ─────────────────────────────


def test_surum_ikili_YOKSA_bos_ALT_SUREC_patlarsa_bos(o):
    """`_read_version(None)` → "" (alt süreç yok); `-h` TimeoutExpired → "" (istisna sızmaz)."""
    sup = _sup(o)
    assert sup._read_version(None) == "" and o.sp.cagri == []
    o.sp.yanit[("mosquitto.exe", "-h")] = _gercek_sp.TimeoutExpired(["mosquitto.exe", "-h"], 5)
    assert sup._read_version(o.tmp / "m" / "mosquitto.exe") == ""
    assert o.sp.say(("mosquitto.exe", "-h")) == 1


def test_surum_ikili_STAT_okunamazsa_yine_OKUNUR_anahtar_yol_TTL_icinde_ONBELLEKTEN(o):
    """İkili stat OSError → önbellek anahtarı (yol, None, None); sürüm `-h` çıktısından okunur ve 60 sn TTL içinde ikinci çağrı alt
    süreç BAŞLATMAZ."""
    exe = o.tmp / "yok" / "mosquitto.exe"
    sup = _sup(o)
    assert sup._surum(exe) == "mosquitto version 2.0.18"
    o.saat.t += 30.0
    assert sup._surum(exe) == "mosquitto version 2.0.18"
    assert o.sp.say(("mosquitto.exe", "-h")) == 1
    assert sup._yoklama_onbellegi["surum"][1] == (str(exe), None, None)


def test_servis_sorgusu_PATLARSA_gorev_listesine_DUSER_bozuk_PID_None(o):
    """`sc query` TimeoutExpired → görev listesine düşülür; mosquitto.exe görünüyor → running True, PID sütunu sayı değil → pid None."""
    o.sp.yanit[("sc", "query")] = _gercek_sp.TimeoutExpired(["sc", "query", "mosquitto"], 5)
    o.sp.yanit[("tasklist", "/FI")] = (0, "mosquitto.exe   PID?   Console   1   9.000 K\n")
    assert _sup(o)._check_service_status() == {"service_exists": False, "running": True, "pid": None}


def test_gorev_listesi_de_PATLARSA_VARSAYILAN_durum_systemd_SORULMAZ(o):
    """Windows: `sc query` ve `tasklist` fırlatır → {service_exists False, running False, pid None}; systemctl çağrılmaz."""
    o.sp.yanit[("sc", "query")] = _gercek_sp.TimeoutExpired(["sc"], 5)
    o.sp.yanit[("tasklist", "/FI")] = OSError(errno.EACCES, "tasklist erisim")
    assert _sup(o)._check_service_status() == {"service_exists": False, "running": False, "pid": None}
    assert o.sp.say(("systemctl", "is-enabled")) == 0


def test_systemd_sorgusu_PATLARSA_VARSAYILAN_durum_Windows_sorgulari_YOK(o):
    """Linux: `systemctl is-enabled` FileNotFoundError → varsayılan durum; yalnız o sorgu yapılır (sc / tasklist yok)."""
    o.plat.ad = "Linux"
    o.sp.yanit[("systemctl", "is-enabled")] = FileNotFoundError(errno.ENOENT, "systemctl bulunamadi")
    assert _sup(o)._check_service_status() == {"service_exists": False, "running": False, "pid": None}
    assert [c[0] for c in o.sp.cagri] == [("systemctl", "is-enabled")]


def test_olay_yayini_PATLARSA_gunluge_yazilir_DURUM_yine_doner(o, caplog):
    """Olay veriyolu fırlatır → check_once yine ölçülen durumu döner (kurulu, port açık, çalışıyor) ve "Event publish failed:
    mqtt.broker.status" günlüğe yazılır."""
    o.bus.hata = RuntimeError("veriyolu kapali")
    o.ag.acik.add(("127.0.0.1", PORT))
    _kurulum(o)
    with caplog.at_level(logging.ERROR, logger=hs.logger.name):
        d = _sup(o).check_once()
    assert d["running"] is True and d["port_open"] is True and d["installed"] is True
    assert "Event publish failed: mqtt.broker.status" in caplog.text
