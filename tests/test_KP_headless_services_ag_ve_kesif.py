"""KP-1 · apps/backend/services/headless_services.py · sözleşmeler: modül ağ yardımcıları (`_windows_creationflags`, `_run_command`,
`_lan_ip_yedegi`, `get_local_ip`, `get_hostname`, `_is_tcp_port_open`, `_surec_yollari`) · `NetworkStatusService` (internet / hotspot /
arayüz IP yoklaması, ağ geçidi kipi, yayın hatası, iş parçacığı yaşam döngüsü) · `UdpDiscoveryService` (soket kurulumu, kendini onarma,
istek süzme, hız sınırı tahliyesi, dış hata, yaşam döngüsü).

Sahte EN ALT katta: modülün KENDİ içe aktardığı `socket` / `subprocess` / `platform` / `time` adları gerçek modüle devreden VEKİLLE
değiştirilir (yalnız soket kurucusu, `getaddrinfo`, `gethostname`, `subprocess.run`, `platform.system`, `time.monotonic`); Windows API'si
(`ctypes.WinDLL("kernel32")`) kayıtlı sahte kernel32. Gerçek ağ / süreç / port / dinleyici YOK.
"""

from __future__ import annotations

import ctypes
import errno
import json
import logging
import platform as _gercek_platform
import socket as _gercek_soket
import subprocess as _gercek_sp
import threading
import time as _gercek_time

import pytest
from event_bus import EventPriority
from services import headless_services as hs

AF_INET = _gercek_soket.AF_INET
SOCK_DGRAM = _gercek_soket.SOCK_DGRAM
SOCK_STREAM = _gercek_soket.SOCK_STREAM
SOL_SOCKET = _gercek_soket.SOL_SOCKET
SO_REUSEADDR = _gercek_soket.SO_REUSEADDR


class _Vekil:
    """Gerçek modüle devreden vekil: `sahte` adlar değiştirilir, `gizli` adlar YOKMUŞ gibi davranır (AttributeError)."""

    def __init__(self, gercek, gizli=(), **sahte):
        self.__dict__["_gercek"] = gercek
        self.__dict__["_gizli"] = frozenset(gizli)
        self.__dict__.update(sahte)

    def __getattr__(self, ad):
        if ad in self.__dict__["_gizli"]:
            raise AttributeError(ad)
        return getattr(self.__dict__["_gercek"], ad)


# ───────────────────────────── sahte ağ (EN ALT kat: soket) ─────────────────────────────


class _Soket:
    def __init__(self, ag, aile, tip):
        self.ag = ag
        self.aile = aile
        self.tip = tip
        self.zaman_asimi = None
        self.kapanma = 0
        self.secenekler: list[tuple] = []
        self.baglanti = None
        self.gelenler = None  # keşif betiği: [(veri, adres, saat) | istisna]
        self.gonderilen: list[tuple] = []

    def settimeout(self, t):
        self.zaman_asimi = t

    def connect(self, adres):
        self.ag.kayit.append(("connect", adres))
        if self.ag.rota_hatasi is not None:
            raise self.ag.rota_hatasi

    def getsockname(self):
        return (self.ag.yerel_ip, 50123)

    def connect_ex(self, adres):
        self.ag.kayit.append(("connect_ex", adres, self.zaman_asimi))
        return 0 if adres in self.ag.acik else errno.ECONNREFUSED

    def setsockopt(self, *a):
        self.secenekler.append(a)

    def bind(self, adres):
        self.baglanti = adres
        if self.ag.bind_hatasi is not None:
            raise self.ag.bind_hatasi

    def recvfrom(self, n):
        if (
            self.gelenler is None
        ):  # yaşam döngüsü: veri yok → kısa bekleme + zaman aşımı (gerçek soketin 1 sn'lik döngüsü)
            _gercek_time.sleep(0.01)
            raise _gercek_soket.timeout()
        if not self.gelenler:
            self.ag.servis._stop_event.set()
            raise _gercek_soket.timeout()
        oge = self.gelenler.pop(0)
        if isinstance(oge, BaseException):
            raise oge
        veri, adres, saat = oge
        self.ag.saat[0] = saat
        return veri, adres

    def sendto(self, veri, adres):
        self.gonderilen.append((adres, json.loads(veri.decode("utf-8")), self.ag.saat[0]))

    def close(self):
        self.kapanma += 1
        if self.ag.kapatma_hatasi is not None:
            raise self.ag.kapatma_hatasi


class _Ag:
    def __init__(self, monkeypatch):
        self.mp = monkeypatch
        self.acik: set = set()
        self.kayit: list[tuple] = []
        self.soketler: list[_Soket] = []
        self.yerel_ip = "10.1.2.3"
        self.rota_hatasi = None
        self.bind_hatasi = None
        self.kapatma_hatasi = None
        self.kurulum_hatasi = None
        self.izinli_soket = None  # kurulum_hatasi bu sayıda soketten SONRA devreye girer (None: hemen)
        self.adresler: list[str] = []
        self.adres_hatasi = None
        self.ad = "KLINIK-PC"
        self.ad_hatasi = None
        self.betik = None
        self.servis = None
        self.saat = [1000.0]

    def socket(self, aile=AF_INET, tip=SOCK_STREAM, *a):
        if self.kurulum_hatasi is not None and (self.izinli_soket is None or len(self.soketler) >= self.izinli_soket):
            raise self.kurulum_hatasi
        s = _Soket(self, aile, tip)
        if self.betik is not None and not self.soketler:  # ilk soket = keşif soketi
            s.gelenler = list(self.betik)
        self.soketler.append(s)
        return s

    def getaddrinfo(self, host, port, family=0, *a):
        self.kayit.append(("getaddrinfo", host, family))
        if self.adres_hatasi is not None:
            raise self.adres_hatasi
        return [(family, SOCK_DGRAM, 17, "", (a, 0)) for a in self.adresler]

    def gethostname(self):
        if self.ad_hatasi is not None:
            raise self.ad_hatasi
        return self.ad

    def kur(self, gizli=(), **ek):
        self.mp.setattr(
            hs,
            "socket",
            _Vekil(
                _gercek_soket,
                gizli=gizli,
                socket=self.socket,
                getaddrinfo=self.getaddrinfo,
                gethostname=self.gethostname,
                **ek,
            ),
        )


@pytest.fixture
def ag(monkeypatch):
    a = _Ag(monkeypatch)
    a.kur()
    return a


class _Platform:
    def __init__(self):
        self.ad = "Windows"

    def system(self):
        if isinstance(self.ad, BaseException):
            raise self.ad
        return self.ad


@pytest.fixture
def plat(monkeypatch):
    p = _Platform()
    monkeypatch.setattr(hs, "platform", _Vekil(_gercek_platform, system=p.system))
    return p


class _Surecler:
    """`subprocess.run` kaydedici: yanıt komut adına (args[0]) göre — (rc, stdout[, stderr]) ya da fırlatılacak istisna."""

    def __init__(self, monkeypatch):
        self.mp = monkeypatch
        self.cagri: list[tuple[list, dict]] = []
        self.yanit: dict = {}

    def run(self, args, **kw):
        self.cagri.append((list(args), kw))
        y = self.yanit.get(args[0])
        if y is None:
            raise AssertionError(f"beklenmeyen alt süreç: {args}")
        if isinstance(y, BaseException):
            raise y
        return _gercek_sp.CompletedProcess(args, y[0], y[1], y[2] if len(y) > 2 else "")

    def _popen(self, *a, **k):
        raise AssertionError(f"beklenmeyen Popen: {a}")

    def kur(self, gizli=(), **ek):
        self.mp.setattr(hs, "subprocess", _Vekil(_gercek_sp, gizli=gizli, run=self.run, Popen=self._popen, **ek))


@pytest.fixture
def sp(monkeypatch):
    s = _Surecler(monkeypatch)
    s.kur()
    return s


class _Saat:
    def __init__(self):
        self.t = 1000.0

    def monotonic(self):
        return self.t


@pytest.fixture
def saat(monkeypatch):
    s = _Saat()
    monkeypatch.setattr(hs, "time", _Vekil(_gercek_time, monotonic=s.monotonic))
    return s


class _Olaylar:
    def __init__(self, hata=None):
        self.yayinlar: list[tuple] = []
        self.hata = hata
        self.ilk = threading.Event()

    def publish(self, tur, veri, **kw):
        if self.hata is not None:
            raise self.hata
        self.yayinlar.append((tur, veri, kw))
        self.ilk.set()

    def turler(self):
        return [y[0] for y in self.yayinlar]


# ───────────────────────────── alt süreç bayrakları ─────────────────────────────


def test_windows_DISI_platformda_alt_surec_PENCERE_bayragi_almaz_cp857_ile_metin_yakalar(plat, sp):
    """platform Linux → `_windows_creationflags()` 0; `_run_command` subprocess.run'a creationflags GEÇİRMEZ; çıktı yakalama + metin +
    cp857 + replace + verilen zaman aşımı geçer, sonuç AYNEN döner."""
    plat.ad = "Linux"
    sp.yanit["arp"] = (0, "ok\n")
    assert hs._windows_creationflags() == 0
    r = hs._run_command(["arp", "-a"], timeout=7)
    assert (r.returncode, r.stdout) == (0, "ok\n")
    args, kw = sp.cagri[-1]
    assert args == ["arp", "-a"]
    assert kw == {"capture_output": True, "text": True, "timeout": 7, "encoding": "cp857", "errors": "replace"}


def test_windowsta_CREATE_NO_WINDOW_varsa_alt_surec_PENCERESIZ_yoksa_bayraksiz(plat, sp):
    """Windows + `CREATE_NO_WINDOW` var → `_run_command` o bayrakla (varsayılan zaman aşımı 5); sabit YOKSA (eski Python) bayrak 0 ve
    creationflags hiç geçirilmez."""
    plat.ad = "Windows"
    sp.yanit["arp"] = (0, "")
    sp.kur(CREATE_NO_WINDOW=0x08000000)
    assert hs._windows_creationflags() == 0x08000000
    hs._run_command(["arp", "-a"])
    assert sp.cagri[-1][1]["creationflags"] == 0x08000000 and sp.cagri[-1][1]["timeout"] == 5
    sp.kur(gizli=("CREATE_NO_WINDOW",))
    assert hs._windows_creationflags() == 0
    hs._run_command(["arp", "-a"])
    assert "creationflags" not in sp.cagri[-1][1]


# ───────────────────────────── LAN adresi ─────────────────────────────


def test_lan_yedegi_HOTSPOT_adresini_diger_ozel_adreslerden_ONCE_secer(ag):
    """Arayüz adresleri içinde 192.168.137.x varsa → o (sıralamada önde olan 10.x'e rağmen); makine adı AF_INET ile çözülür."""
    ag.adresler = ["10.0.0.5", "127.0.0.1", "8.8.4.4", "192.168.137.20", "172.16.0.9"]
    assert hs._lan_ip_yedegi() == "192.168.137.20"
    assert ag.kayit[-1] == ("getaddrinfo", "KLINIK-PC", AF_INET)


def test_lan_yedegi_hotspot_yoksa_SIRALI_ilk_ozel_adres_yalniz_genel_ya_da_dongu_varsa_None(ag):
    """Hotspot alt ağı yok → genel (8.8.4.4) ve döngü (127.x) elenir, kalan özel adreslerin SIRALI ilki; özel adres yoksa None."""
    ag.adresler = ["172.16.0.9", "8.8.4.4", "10.0.0.5", "127.0.0.1"]
    assert hs._lan_ip_yedegi() == "10.0.0.5"
    ag.adresler = ["8.8.4.4", "127.0.0.1"]
    assert hs._lan_ip_yedegi() is None


def test_lan_yedegi_ad_cozumu_PATLARSA_ya_da_adres_BOZUKSA_None(ag):
    """getaddrinfo gaierror → None; çözülen listede ayrıştırılamayan adres → None (istisna sızmaz)."""
    ag.adres_hatasi = _gercek_soket.gaierror(11001, "getaddrinfo failed")
    assert hs._lan_ip_yedegi() is None
    ag.adres_hatasi = None
    ag.adresler = ["10.0.0.5", "bozuk-adres"]
    assert hs._lan_ip_yedegi() is None


def test_yerel_ip_ROTA_varsa_kaynak_adresi_doner_UDP_soket_KAPATILIR_paket_gonderilmez(ag):
    """Varsayılan rota var → UDP soketin 8.8.8.8:80'e `connect` sonrası kaynak adresi; soket bir kez kapatılır, veri GÖNDERİLMEZ."""
    ag.yerel_ip = "192.168.1.44"
    assert hs.get_local_ip() == "192.168.1.44"
    (s,) = ag.soketler
    assert (s.aile, s.tip) == (AF_INET, SOCK_DGRAM)
    assert ("connect", ("8.8.8.8", 80)) in ag.kayit
    assert s.kapanma == 1 and s.gonderilen == []


def test_yerel_ip_ROTA_yoksa_arayuz_yedegi_o_da_yoksa_DONGU_adresi(ag):
    """connect ENETUNREACH → arayüz yedeği (hotspot önce); yedek de boşsa "127.0.0.1"; her denemede soket kapatılır."""
    ag.rota_hatasi = OSError(errno.ENETUNREACH, "Network is unreachable")
    ag.adresler = ["10.0.0.8", "192.168.137.5"]
    assert hs.get_local_ip() == "192.168.137.5"
    ag.adresler = []
    assert hs.get_local_ip() == "127.0.0.1"
    assert [s.kapanma for s in ag.soketler] == [1, 1]


def test_yerel_ip_soket_KAPATMA_hatasi_sonucu_BOZMAZ(ag):
    """Rota adresi okundu ama `close` OSError → adres yine döner (istisna sızmaz)."""
    ag.kapatma_hatasi = OSError(10038, "not a socket")
    ag.yerel_ip = "10.9.8.7"
    assert hs.get_local_ip() == "10.9.8.7"
    assert ag.soketler[0].kapanma == 1


def test_yerel_ip_soket_KURULAMAZSA_yedege_duser(ag):
    """socket() OSError → arayüz yedeği döner; kapatılacak soket yoktur."""
    ag.kurulum_hatasi = OSError(10047, "address family not supported")
    ag.adresler = ["10.0.0.8"]
    assert hs.get_local_ip() == "10.0.0.8"
    assert ag.soketler == []


def test_makine_adi_BOS_ya_da_OKUNAMAZSA_PEMF_Gateway(ag):
    """gethostname normal → ad; boş dize → "PEMF-Gateway"; OSError → "PEMF-Gateway"."""
    assert hs.get_hostname() == "KLINIK-PC"
    ag.ad = ""
    assert hs.get_hostname() == "PEMF-Gateway"
    ag.ad_hatasi = OSError("gethostname failed")
    assert hs.get_hostname() == "PEMF-Gateway"


# ───────────────────────────── TCP port yoklaması ─────────────────────────────


def test_tcp_port_ACIKSA_True_KAPALIYSA_False_zaman_asimi_ve_TAMSAYI_port_uygulanir(ag):
    """connect_ex 0 → True, ret → False; port dizesi int'e çevrilir; verilen zaman aşımı (varsayılan 2.0) sokete uygulanır; TCP soket
    her yoklamada kapatılır."""
    ag.acik = {("127.0.0.1", 18830)}
    assert hs._is_tcp_port_open("127.0.0.1", "18830", timeout=0.7) is True
    assert ag.kayit[-1] == ("connect_ex", ("127.0.0.1", 18830), 0.7)
    assert (ag.soketler[-1].aile, ag.soketler[-1].tip) == (AF_INET, SOCK_STREAM)
    assert hs._is_tcp_port_open("127.0.0.1", 18831) is False
    assert ag.kayit[-1] == ("connect_ex", ("127.0.0.1", 18831), 2.0)
    assert [s.kapanma for s in ag.soketler] == [1, 1]


def test_tcp_port_soket_KURULAMAZ_ya_da_port_GECERSIZSE_False_kapatma_hatasi_sonucu_bozmaz(ag):
    """socket() OSError → False; port "abc" (int hatası) → False ve soket yine kapatılır; açık portta close OSError → True korunur."""
    ag.kurulum_hatasi = OSError(10055, "no buffer space")
    assert hs._is_tcp_port_open("127.0.0.1", 18830) is False
    assert ag.soketler == []
    ag.kurulum_hatasi = None
    assert hs._is_tcp_port_open("127.0.0.1", "abc") is False
    assert ag.soketler[-1].kapanma == 1 and not any(k[0] == "connect_ex" for k in ag.kayit)
    ag.acik = {("127.0.0.1", 18830)}
    ag.kapatma_hatasi = OSError(10038, "not a socket")
    assert hs._is_tcp_port_open("127.0.0.1", 18830) is True


# ───────────────────────────── süreç yolları (Windows API sahte) ─────────────────────────────


class _Fn:
    def __init__(self, f):
        self.f = f
        self.restype = None
        self.argtypes = None

    def __call__(self, *a):
        return self.f(*a)


class _Kernel32:
    GECERSIZ = ctypes.c_void_p(-1).value

    def __init__(self, surecler, anlik=0x1234):
        # surecler: [(pid, exe_adi, tam_yol | None (OpenProcess reddi) | "" (QueryFullProcessImageNameW başarısız))]
        self.surecler = list(surecler)
        self._yollar = {p: y for p, _, y in self.surecler}
        self._i = 0
        self.anlik = anlik
        self.anlik_bayragi = None
        self.acilan: list[tuple] = []
        self.kapatilan: list = []
        self.CreateToolhelp32Snapshot = _Fn(self._anlik_al)
        self.Process32FirstW = _Fn(self._ilk)
        self.Process32NextW = _Fn(self._sonraki)
        self.OpenProcess = _Fn(self._ac)
        self.QueryFullProcessImageNameW = _Fn(self._yol)
        self.CloseHandle = _Fn(self.kapatilan.append)

    def _anlik_al(self, bayrak, pid):
        self.anlik_bayragi = bayrak
        return self.anlik

    def _doldur(self, ref):
        if self._i >= len(self.surecler):
            return 0
        pid, ad, _ = self.surecler[self._i]
        ref._obj.th32ProcessID = pid
        ref._obj.szExeFile = ad
        self._i += 1
        return 1

    def _ilk(self, anlik, ref):
        self._i = 0
        return self._doldur(ref)

    def _sonraki(self, anlik, ref):
        return self._doldur(ref)

    def _ac(self, erisim, devral, pid):
        self.acilan.append((erisim, int(pid)))
        return 0 if self._yollar[int(pid)] is None else 0x5000 + int(pid)

    def _yol(self, tutamac, bayrak, tampon, boy_ref):
        yol = self._yollar[tutamac - 0x5000]
        if not yol:
            return 0
        tampon.value = yol
        return 1


def _kernel32_kur(monkeypatch, k32):
    yuklenen = []

    def _yukle(ad, use_last_error=False):
        yuklenen.append((ad, use_last_error))
        return k32

    monkeypatch.setattr(ctypes, "WinDLL", _yukle, raising=False)
    return yuklenen


def test_surec_yollari_ADI_eslesen_surecleri_TAM_yoluyla_listeler_tutamaclari_KAPATIR(plat, monkeypatch):
    """Windows: ad büyük/küçük harf duyarsız eşleşir; yolu okunan süreç tam yoluyla, OpenProcess reddi ya da yol okunamazsa "" yolla
    döner; eşleşmeyen süreç listede YOK; açılan her süreç tutamacı ve anlık görüntü KAPATILIR; erişim PROCESS_QUERY_LIMITED_INFORMATION."""
    plat.ad = "Windows"
    k32 = _Kernel32(
        [
            (100, "mosquitto.exe", r"C:\PEMF\bin\mosquitto\mosquitto.exe"),
            (200, "python.exe", r"C:\py\python.exe"),
            (300, "MOSQUITTO.EXE", None),
            (400, "mosquitto.exe", ""),
        ]
    )
    yuklenen = _kernel32_kur(monkeypatch, k32)
    assert hs._surec_yollari("Mosquitto.exe") == [(100, r"C:\PEMF\bin\mosquitto\mosquitto.exe"), (300, ""), (400, "")]
    assert yuklenen == [("kernel32", True)]
    assert k32.anlik_bayragi == 0x00000002
    assert k32.acilan == [(0x1000, 100), (0x1000, 300), (0x1000, 400)]
    assert sorted(k32.kapatilan) == sorted([0x5000 + 100, 0x5000 + 400, 0x1234])


@pytest.mark.parametrize("anlik", [0, _Kernel32.GECERSIZ], ids=["NULL", "INVALID_HANDLE_VALUE"])
def test_surec_yollari_ANLIK_goruntu_alinamazsa_BOS_liste_surec_sorulmaz(plat, monkeypatch, anlik):
    """CreateToolhelp32Snapshot 0 / INVALID_HANDLE_VALUE → [] (hiçbir süreç açılmaz, kapatılacak tutamaç yok)."""
    plat.ad = "Windows"
    k32 = _Kernel32([(100, "mosquitto.exe", r"C:\m\mosquitto.exe")], anlik=anlik)
    _kernel32_kur(monkeypatch, k32)
    assert hs._surec_yollari("mosquitto.exe") == []
    assert k32.acilan == [] and k32.kapatilan == []


def test_surec_yollari_kernel32_YUKLENEMEZSE_bos_liste_ve_hata_ayiklama_kaydi(plat, monkeypatch, caplog):
    """WinDLL OSError → [] (çağıran hiçbir süreci sonlandırmaz) + DEBUG "surec listesi okunamadi"."""
    plat.ad = "Windows"

    def _yukle(ad, use_last_error=False):
        raise OSError(126, "Belirtilen modül bulunamadı")

    monkeypatch.setattr(ctypes, "WinDLL", _yukle, raising=False)
    with caplog.at_level(logging.DEBUG, logger=hs.logger.name):
        assert hs._surec_yollari("mosquitto.exe") == []
    assert "surec listesi okunamadi" in caplog.text


def test_surec_yollari_WINDOWS_DISINDA_api_YUKLENMEZ_bos_liste(plat, monkeypatch):
    """platform Linux → [] ve kernel32 hiç yüklenmez."""
    plat.ad = "Linux"
    yuklenen = _kernel32_kur(monkeypatch, _Kernel32([]))
    assert hs._surec_yollari("mosquitto") == []
    assert yuklenen == []


# ───────────────────────────── NetworkStatusService ─────────────────────────────

ARP = (
    "\nInterface: 192.168.137.1 --- 0x12\n"
    "  Internet Address      Physical Address      Type\n"
    "  192.168.137.20        aa-bb-cc-dd-ee-01     dynamic\n"
    "  192.168.137.21        aa-bb-cc-dd-ee-02     DYNAMIC\n"
    "  192.168.137.255       ff-ff-ff-ff-ff-ff     static\n"
    "  192.168.1.5           aa-bb-cc-dd-ee-03     dynamic\n"
)

IP_TABLOSU = (
    "\r\n"
    "192.168.137.1   Yerel Ag Baglantisi* 10\r\n"
    "10.0.0.5        Ethernet 2\r\n"
    "192.168.1.20    Wi-Fi\r\n"
    "192.168.56.1    VirtualBox Host-Only Network\r\n"
    "10.9.9.9\r\n"
)

BOS_IP = {"ethernet": None, "wifi": None, "hotspot": None}
KAPALI_HOTSPOT = {"active": False, "ssid": "", "ip": "", "clients": 0}


@pytest.fixture
def ag_durumu(ag, plat, sp, saat):
    bus = _Olaylar()
    n = hs.NetworkStatusService(interval_seconds=60.0, mqtt_port=18830, event_bus=bus)
    yield n, bus
    n.stop()


def _uclar(ag):
    return [k[1] for k in ag.kayit if k[0] == "connect_ex"]


def test_internet_ILK_acik_DNS_ucunda_True_SONRAKILER_denenmez(ag_durumu, ag):
    """8.8.8.8:53 kapalı, 1.1.1.1:53 açık → True; üçüncü uç (208.67.222.222) denenmez; her yoklama 2 sn zaman aşımlı."""
    n, _ = ag_durumu
    ag.acik = {("1.1.1.1", 53)}
    assert n._check_internet() is True
    assert _uclar(ag) == [("8.8.8.8", 53), ("1.1.1.1", 53)]
    assert all(k[2] == 2.0 for k in ag.kayit if k[0] == "connect_ex")


def test_internet_hicbir_DNS_ucu_acik_degilse_False_UC_uc_de_denenir(ag_durumu, ag):
    """Hiçbir uç açık değil → False; üç uç sırayla denenir."""
    n, _ = ag_durumu
    assert n._check_internet() is False
    assert _uclar(ag) == [("8.8.8.8", 53), ("1.1.1.1", 53), ("208.67.222.222", 53)]


def test_hotspot_WINDOWSta_ilk_137_adresi_ve_yalniz_DINAMIK_hotspot_istemcileri_sayilir(ag_durumu, plat, sp):
    """powershell 137.x adresleri + arp tablosu → active True, ip = İLK satır, clients = hotspot alt ağındaki dynamic (büyük/küçük harf
    duyarsız) satır sayısı (static ve başka alt ağ sayılmaz); powershell süzgeci 192.168.137.* ister, arp `-a` ile koşar."""
    n, _ = ag_durumu
    plat.ad = "Windows"
    sp.yanit["powershell"] = (0, "192.168.137.1\r\n192.168.137.77\r\n")
    sp.yanit["arp"] = (0, ARP)
    assert n._check_hotspot_uncached() == {"active": True, "ssid": "", "ip": "192.168.137.1", "clients": 2}
    ps, arp = sp.cagri[0][0], sp.cagri[1][0]
    assert ps[:2] == ["powershell", "-Command"] and "192.168.137.*" in ps[2]
    assert arp == ["arp", "-a"]


def test_hotspot_powershell_BASARISIZ_ya_da_BOS_ise_KAPALI_arp_basarisizsa_istemci_0(ag_durumu, plat, sp):
    """powershell rc≠0 → active False; rc 0 ama yalnız boşluk → active False (ip boş); arp rc≠0 → clients 0, rc 0 → sayılır."""
    n, _ = ag_durumu
    plat.ad = "Windows"
    sp.yanit["powershell"] = (1, "", "Get-NetIPAddress : erisim")
    sp.yanit["arp"] = (1, ARP)
    assert n._check_hotspot_uncached() == KAPALI_HOTSPOT
    sp.yanit["powershell"] = (0, "  \r\n")
    sp.yanit["arp"] = (0, ARP)
    assert n._check_hotspot_uncached() == {"active": False, "ssid": "", "ip": "", "clients": 2}


def test_hotspot_arp_ZAMAN_ASIMI_onceki_bulguyu_SILMEZ(ag_durumu, plat, sp):
    """powershell hotspot'u buldu, arp TimeoutExpired → active True + ip korunur, clients 0 (istisna sızmaz)."""
    n, _ = ag_durumu
    plat.ad = "Windows"
    sp.yanit["powershell"] = (0, "192.168.137.1\n")
    sp.yanit["arp"] = _gercek_sp.TimeoutExpired(["arp", "-a"], 5)
    assert n._check_hotspot_uncached() == {"active": True, "ssid": "", "ip": "192.168.137.1", "clients": 0}


def test_hotspot_WINDOWS_DISINDA_alt_surec_KOSMAZ_kapali_bilgi(ag_durumu, plat, sp):
    """platform Linux → kapalı hotspot bilgisi, hiçbir alt süreç yok."""
    n, _ = ag_durumu
    plat.ad = "Linux"
    assert n._check_hotspot_uncached() == KAPALI_HOTSPOT
    assert sp.cagri == []


def test_hotspot_ilk_yoklama_PATLARSA_guvenli_varsayilan_TTL_icinde_onbellek_sonra_SON_BILINEN(
    ag_durumu, plat, sp, saat
):
    """Önbellek boş + üretici fırlatır → kapalı varsayılan; başarılı yoklama 60 sn önbellekte (yeniden powershell YOK); TTL sonra üretici
    fırlatırsa SON BİLİNEN değer döner (titreme yok)."""
    n, _ = ag_durumu
    plat.ad = RuntimeError("platform okunamadi")
    assert n._check_hotspot() == KAPALI_HOTSPOT
    plat.ad = "Windows"
    sp.yanit["powershell"] = (0, "192.168.137.1\n")
    sp.yanit["arp"] = (0, ARP)
    ilk = n._check_hotspot()
    assert ilk == {"active": True, "ssid": "", "ip": "192.168.137.1", "clients": 2}
    sp.yanit["powershell"] = (1, "")
    saat.t += 59.0
    assert n._check_hotspot() == ilk
    assert sum(1 for c in sp.cagri if c[0][0] == "powershell") == 1
    saat.t += 2.0
    plat.ad = RuntimeError("platform okunamadi")
    assert n._check_hotspot() == ilk


def test_ag_ipleri_WINDOWSta_arayuz_adina_gore_ayrilir_HOTSPOT_alt_agi_once(ag_durumu, plat, sp):
    """powershell IP/arayüz tablosu → 137.x hotspot, "ethernet" ethernet, "wi-fi" wifi; tanınmayan arayüz ve arayüzsüz satır atlanır;
    "eth0" / "wlan0" eşanlamlıları da tanınır; komut döngü (127.*) ve APIPA (169.254.*) adreslerini süzer."""
    n, _ = ag_durumu
    plat.ad = "Windows"
    sp.yanit["powershell"] = (0, IP_TABLOSU)
    assert n._get_network_ips_uncached() == {"ethernet": "10.0.0.5", "wifi": "192.168.1.20", "hotspot": "192.168.137.1"}
    komut = sp.cagri[-1][0][2]
    assert "-notlike '127.*'" in komut and "-notlike '169.254.*'" in komut
    sp.yanit["powershell"] = (0, "10.0.0.6 eth0\n172.16.4.4 wlan0\n")
    assert n._get_network_ips_uncached() == {"ethernet": "10.0.0.6", "wifi": "172.16.4.4", "hotspot": None}


def test_ag_ipleri_powershell_BASARISIZ_ya_da_PATLARSA_hepsi_None(ag_durumu, plat, sp):
    """rc≠0 → tablo okunmaz (hepsi None); TimeoutExpired → hepsi None (istisna sızmaz)."""
    n, _ = ag_durumu
    plat.ad = "Windows"
    sp.yanit["powershell"] = (1, IP_TABLOSU)
    assert n._get_network_ips_uncached() == BOS_IP
    sp.yanit["powershell"] = _gercek_sp.TimeoutExpired(["powershell"], 5)
    assert n._get_network_ips_uncached() == BOS_IP


def test_ag_ipleri_WINDOWS_DISINDA_yerel_ip_WIFI_sayilir_DONGU_adresi_sayilmaz(ag_durumu, plat, sp, ag):
    """platform Linux → alt süreç YOK; get_local_ip LAN adresi → wifi; rota + yedek yok (127.0.0.1) → wifi None."""
    n, _ = ag_durumu
    plat.ad = "Linux"
    ag.yerel_ip = "192.168.1.33"
    assert n._get_network_ips_uncached() == {"ethernet": None, "wifi": "192.168.1.33", "hotspot": None}
    ag.rota_hatasi = OSError(errno.ENETUNREACH, "Network is unreachable")
    assert n._get_network_ips_uncached() == BOS_IP
    assert sp.cagri == []


def test_ag_ipleri_ilk_yoklama_PATLARSA_guvenli_varsayilan(ag_durumu, plat):
    """Önbellek boş + üretici fırlatır → {ethernet, wifi, hotspot: None}."""
    n, _ = ag_durumu
    plat.ad = RuntimeError("platform okunamadi")
    assert n._get_network_ips() == BOS_IP


@pytest.mark.parametrize(
    "internet,hotspot,beklenen",
    [(True, True, "online"), (False, True, "offline"), (True, False, "hybrid"), (False, False, "disconnected")],
)
def test_gecit_kipi_internet_ve_hotspot_BIRLESIMINE_gore(ag_durumu, internet, hotspot, beklenen):
    """internet+hotspot → online · yalnız hotspot → offline · yalnız internet → hybrid · hiçbiri → disconnected."""
    n, _ = ag_durumu
    assert n._determine_gateway_mode({"internet_connected": internet, "hotspot_active": hotspot}) == beklenen


def test_ag_durumu_yayini_PATLARSA_check_once_yine_DURUM_doner_hata_gunluge(plat, ag, sp, saat, caplog):
    """Olay veriyolu fırlatır → check_once yine ölçülen durumu döner (internet + broker portu + hybrid) ve
    "Event publish failed: network.status" günlüğe yazılır."""
    plat.ad = "Linux"
    n = hs.NetworkStatusService(
        interval_seconds=60.0, mqtt_port=18830, event_bus=_Olaylar(hata=RuntimeError("veriyolu kapali"))
    )
    ag.acik = {("8.8.8.8", 53), ("127.0.0.1", 18830)}
    with caplog.at_level(logging.ERROR, logger=hs.logger.name):
        d = n.check_once()
    assert d["internet_connected"] is True and d["mqtt_broker_reachable"] is True and d["gateway_mode"] == "hybrid"
    assert "Event publish failed: network.status" in caplog.text


def test_ag_izleyici_TEK_is_parcacigi_ilk_turda_yayinlar_stop_ile_BITER(plat, ag, sp, saat):
    """start → izleme iş parçacığı ilk turda `network.status` yayınlar; ikinci start YENİ iş parçacığı açmaz; stop → iş parçacığı biter."""
    plat.ad = "Linux"
    bus = _Olaylar()
    n = hs.NetworkStatusService(interval_seconds=60.0, mqtt_port=18830, event_bus=bus)
    try:
        n.start()
        ilk = n._thread
        assert bus.ilk.wait(5.0)
        n.start()
        assert n._thread is ilk
    finally:
        n.stop()
    assert not ilk.is_alive()
    tur, veri, kw = bus.yayinlar[0]
    assert (
        tur == "network.status"
        and kw == {"source": "network_status_service"}
        and veri["gateway_mode"] == "disconnected"
    )


# ───────────────────────────── UdpDiscoveryService ─────────────────────────────

ISTEK = json.dumps({"type": "discovery"}).encode()


@pytest.fixture
def kesif(ag, monkeypatch):
    bus = _Olaylar()
    s = hs.UdpDiscoveryService(api_port=8123, discovery_port=15051, mqtt_port=18830, event_bus=bus)
    ag.servis = s
    monkeypatch.setattr(_gercek_time, "time", lambda: ag.saat[0])  # `_run` saati `import time as _tm` ile okur
    yield s, bus
    ag.kapatma_hatasi = None
    s.stop()


def _kos(s, ag, betik):
    ag.betik = betik
    s._run()
    return ag.soketler[0]


def test_kesif_soketi_YAYIN_portuna_baglanir_REUSEADDR_1sn_zaman_asimi_REUSEPORT_yoksa_ATLANIR(kesif, ag):
    """SO_REUSEPORT tanımsız (Windows) → yalnız SO_REUSEADDR; ("", keşif portu)'na bağlanır; 1.0 sn zaman aşımı; soket örnekte tutulur."""
    s, _ = kesif
    ag.kur(gizli=("SO_REUSEPORT",))
    s._open_socket()
    (k,) = ag.soketler
    assert (k.aile, k.tip) == (AF_INET, SOCK_DGRAM)
    assert k.secenekler == [(SOL_SOCKET, SO_REUSEADDR, 1)]
    assert k.baglanti == ("", 15051) and k.zaman_asimi == 1.0
    assert s._socket is k


def test_kesif_soketi_REUSEPORT_destekleniyorsa_O_DA_acilir(kesif, ag):
    """SO_REUSEPORT tanımlı (POSIX) → REUSEADDR ardından REUSEPORT açılır."""
    s, _ = kesif
    ag.kur(SO_REUSEPORT=15)
    s._open_socket()
    assert ag.soketler[0].secenekler == [(SOL_SOCKET, SO_REUSEADDR, 1), (SOL_SOCKET, 15, 1)]


def test_kesif_soketi_yeniden_kurulurken_ESKI_soketi_kapatma_hatasi_ONARIMI_engellemez(kesif, ag, caplog):
    """Eski soket close OSError → yine yeni soket kurulur, True döner, "yeniden kuruldu (port 15051)" günlüğe yazılır."""
    s, _ = kesif
    s._open_socket()
    eski = s._socket
    ag.kapatma_hatasi = OSError(10038, "not a socket")
    with caplog.at_level(logging.INFO, logger=hs.logger.name):
        assert s._reopen_socket() is True
    assert eski.kapanma == 1 and s._socket is not eski and s._socket.baglanti == ("", 15051)
    assert "UDP kesif soketi yeniden kuruldu (port 15051)" in caplog.text


def test_kesif_GECERSIZ_ya_da_BASKA_turden_istek_YANITSIZ(kesif, ag):
    """Bozuk bayt / JSON dizi / başka tür → yanıt yok; "pemf_discovery" türü yanıtlanır; sayaç yalnız yanıtlananı sayar."""
    s, _ = kesif
    k = _kos(
        s,
        ag,
        [
            (b"\xff\xfe{bozuk", ("192.168.137.20", 40000), 1000.0),
            (json.dumps([1, 2]).encode(), ("192.168.137.20", 40000), 1000.0),
            (json.dumps({"type": "ping"}).encode(), ("192.168.137.20", 40000), 1000.0),
            (json.dumps({"type": "pemf_discovery"}).encode(), ("192.168.137.21", 40001), 1000.0),
        ],
    )
    assert [a for a, _, _ in k.gonderilen] == [("192.168.137.21", 40001)]
    st = s.get_status()
    assert st["requestsHandled"] == 1 and st["lastClientIp"] == "192.168.137.21"


def test_kesif_istek_tanima_JSON_nesnesi_ve_TUR_ister():
    """`_is_discovery_request`: {"type": discovery|pemf_discovery} → True; bozuk / dizi / başka tür → False (istisna sızmaz)."""
    s = hs.UdpDiscoveryService(event_bus=_Olaylar())
    assert s._is_discovery_request(json.dumps({"type": "pemf_discovery"}).encode()) is True
    assert s._is_discovery_request(ISTEK) is True
    assert s._is_discovery_request(b"{bozuk") is False
    assert s._is_discovery_request(b"[1]") is False
    assert s._is_discovery_request(json.dumps({"type": "x"}).encode()) is False


def test_kesif_COZULEMEYEN_kaynak_adresi_YANITSIZ(kesif, ag):
    """Kaynak adresi ip_address ile ayrıştırılamıyor ("bozuk", "999.1.1.1") → yanıt yok; geçerli özel kaynak yanıtlanır."""
    s, _ = kesif
    k = _kos(
        s,
        ag,
        [(ISTEK, ("bozuk", 1), 1000.0), (ISTEK, ("999.1.1.1", 1), 1000.0), (ISTEK, ("10.0.0.7", 1), 1000.0)],
    )
    assert [a[0] for a, _, _ in k.gonderilen] == ["10.0.0.7"]


def test_kesif_AYNI_kaynaga_YARIM_saniye_icinde_TEK_yanit_sonra_yeniden(kesif, ag):
    """Aynı kaynak 0,0 / 0,3 / 0,49 / 0,5 sn → 0,0 ve 0,5'te yanıt (aralık < 0,5 sn ise atlanır)."""
    s, _ = kesif
    k = _kos(s, ag, [(ISTEK, ("10.0.0.7", 1), t) for t in (1000.0, 1000.3, 1000.49, 1000.5)])
    assert [t for _, _, t in k.gonderilen] == [1000.0, 1000.5]


def test_kesif_hiz_tablosu_DOLUYKEN_ESKIYEN_girdiler_atilir_YENI_kaynak_yanit_alir(kesif, ag):
    """256 taze girdi → yeni kaynak YANITSIZ; 0,6 sn sonra yeni kaynak → eskiyen (≥0,5 sn) girdiler atılır, yeni kaynak ve atılmış eski
    kaynak yanıt alır."""
    s, _ = kesif
    dolgu = [(ISTEK, (f"10.0.{i // 200}.{i % 200 + 1}", 1), 1000.0) for i in range(256)]
    k = _kos(
        s,
        ag,
        dolgu + [(ISTEK, ("10.9.9.9", 1), 1000.2), (ISTEK, ("10.8.8.8", 1), 1000.6), (ISTEK, ("10.0.0.1", 1), 1000.61)],
    )
    kaynaklar = [a[0] for a, _, _ in k.gonderilen]
    assert len(kaynaklar) == 256 + 2
    assert "10.9.9.9" not in kaynaklar
    assert kaynaklar[-2:] == ["10.8.8.8", "10.0.0.1"]


def test_kesif_yaniti_LAN_adresini_ve_PORTLARI_ilan_eder_istek_olayi_yayinlanir(kesif, ag):
    """Yanıt: tür discovery_response, ip = get_local_ip, base/ws URL'leri api portuyla, broker host/port, makine adı; yanıt aynen
    `discovery.request` olayıyla (clientIp) yayınlanır."""
    s, bus = kesif
    ag.yerel_ip = "192.168.137.1"
    k = _kos(s, ag, [(ISTEK, ("192.168.137.20", 40000), 1000.0)])
    ((adres, cevap, _),) = k.gonderilen
    assert adres == ("192.168.137.20", 40000)
    assert cevap["type"] == "discovery_response" and cevap["service"] == "PEMF-Vet" and cevap["ip"] == "192.168.137.1"
    assert cevap["base_url"] == "http://192.168.137.1:8123" and cevap["api_url"] == "http://192.168.137.1:8123/api"
    assert cevap["websocket_url"] == "ws://192.168.137.1:8123/ws" and cevap["ports"] == [8123]
    assert (
        cevap["mqtt_broker_host"] == "192.168.137.1"
        and cevap["mqtt_broker_port"] == 18830
        and cevap["hostname"] == "KLINIK-PC"
    )
    istek = [(v, kw) for t, v, kw in bus.yayinlar if t == "discovery.request"]
    assert istek == [
        (
            {"clientIp": "192.168.137.20", "response": cevap},
            {"priority": EventPriority.NORMAL, "source": "udp_discovery"},
        )
    ]


def test_kesif_soketi_BAGLANAMAZSA_HATA_olayi_YUKSEK_oncelikle_ve_DURDU_olayi(kesif, ag, caplog):
    """bind OSError (port kullanımda) → `discovery.error` (mesaj + HIGH) ardından `discovery.stopped`; soket kapatılıp bırakılır;
    "UDP discovery failed" uyarısı."""
    s, bus = kesif
    ag.bind_hatasi = OSError(10048, "Only one usage of each socket address")
    with caplog.at_level(logging.WARNING, logger=hs.logger.name):
        s._run()
    assert bus.turler() == ["discovery.error", "discovery.stopped"]
    _, veri, kw = bus.yayinlar[0]
    assert "Only one usage" in veri["message"]
    assert kw == {"priority": EventPriority.HIGH, "source": "udp_discovery"}
    assert ag.soketler[0].kapanma == 1 and s._socket is None
    assert "UDP discovery failed" in caplog.text


class _DurOlay:
    """`threading.Event` yerine: wait(t) kaydedilir, olay KURULUR ve True döner (gerçek 5 sn bekleme yok)."""

    def __init__(self):
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
        self._kurulu = True
        return True


def test_kesif_soket_HATASI_ve_yeniden_kurulamama_5sn_BEKLER_durdurulmussa_DONGU_biter(kesif, ag, caplog):
    """recvfrom OSError → yeniden kurma (socket() OSError) başarısız → stop olayı 5.0 sn beklenir; durdurulmuşsa döngü biter,
    `discovery.stopped` yayınlanır, "yeniden kurulamadi" bildirilir."""
    s, bus = kesif
    ag.izinli_soket = 1
    ag.kurulum_hatasi = OSError(10050, "ag calismiyor")
    s._stop_event = olay = _DurOlay()
    with caplog.at_level(logging.DEBUG, logger=hs.logger.name):
        _kos(s, ag, [OSError(10054, "uzak ana bilgisayar baglantiyi kapatti")])
    assert olay.bekleme == [5.0]
    assert bus.turler() == ["discovery.started", "discovery.stopped"]
    assert "UDP kesif soketi yeniden kurulamadi" in caplog.text
    assert len(ag.soketler) == 1 and ag.soketler[0].kapanma >= 1


def test_kesif_bitiste_soket_KAPATMA_hatasi_yutulur_DURDU_olayi_YINE_yayinlanir(kesif, ag):
    """Döngü biter, finally'deki close OSError → yutulur; soket bırakılır, `discovery.stopped` yayınlanır."""
    s, bus = kesif
    ag.kapatma_hatasi = OSError(10038, "not a socket")
    _kos(s, ag, [])
    assert bus.turler() == ["discovery.started", "discovery.stopped"] and s._socket is None


def test_kesif_olay_yayini_PATLARSA_gunluge_yazilir_KESIF_surer(ag, monkeypatch, caplog):
    """Olay veriyolu fırlatır → her yayın hatası günlüğe ("Event publish failed: …"), istek YİNE yanıtlanır ve sayılır."""
    s = hs.UdpDiscoveryService(
        api_port=8123, discovery_port=15051, mqtt_port=18830, event_bus=_Olaylar(RuntimeError("kapali"))
    )
    ag.servis = s
    monkeypatch.setattr(_gercek_time, "time", lambda: ag.saat[0])
    with caplog.at_level(logging.ERROR, logger=hs.logger.name):
        k = _kos(s, ag, [(ISTEK, ("10.0.0.7", 1), 1000.0)])
    assert len(k.gonderilen) == 1 and s.get_status()["requestsHandled"] == 1
    assert "Event publish failed: discovery.started" in caplog.text
    assert "Event publish failed: discovery.request" in caplog.text


def test_kesif_servisi_TEK_is_parcacigi_stop_soketi_KAPATIR_ve_BEKLER(kesif, ag):
    """start → `discovery.started`; ikinci start yeni iş parçacığı açmaz; stop → soket kapatma hatası yutulur, iş parçacığı biter,
    son olay `discovery.stopped`, durum running False."""
    s, bus = kesif
    s.start()
    ilk = s._thread
    assert bus.ilk.wait(5.0)
    assert bus.turler()[0] == "discovery.started"
    s.start()
    assert s._thread is ilk and s.get_status()["running"] is True
    ag.kapatma_hatasi = OSError(10038, "not a socket")
    s.stop()
    assert not ilk.is_alive()
    assert bus.turler()[-1] == "discovery.stopped" and s.get_status()["running"] is False
    assert ag.soketler[0].kapanma >= 1
