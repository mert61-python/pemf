# -*- coding: utf-8 -*-
"""KP-1 · apps/backend/headless_core.py · sözleşmeler: GERÇEK `_hw_sender_worker` — UDP yayın soketi (SO_BROADCAST kurulumu, ESP'ye
gönderim, gönderim hatasında döngünün sürmesi, kapanışta kapatma), kapanışta son seri bağlantının GÖNDERİCİ tarafından kapatılması,
kapatma hatalarının yutulması (devralınan eski bağlantı, okuyucu, port kaybı, yazım hatası, kapanış), el sıkışma hataları (port
açılamaz; READY'siz el sıkışmada kimlik görünürlüğü ya da doğrulama özeti işlenemezse bağlantı SÜRER), kuyruk DOLUYKEN NACK yeniden
oynatma isteği (okuyucu ölmez); `HeadlessCore.__init__` (DB açılamazsa Y43 iş parçacığı, `start_headless_services` çağrısı).

Sahte EN ALT katta: seri taşıma (`Stm32SerialTransport` → gerçek `Stm32OpenResult` döndüren kayıtçı; porta yazılan baytlar, kapatma
denemeleri, port numaralandırması kayıtlı), modülün KENDİ `socket` adı (UDP soketi kaydı), olay veriyolu, DB getter'ları (açılamama),
hizmet sınıfları (gerçekleri 1883 / 5051 / 5353 dinler). İş parçacığı istisnaları `threading.excepthook` ile kaydedilir (yutulması
gereken hata iş parçacığını öldürürse görünür). Gerçek seri port / ağ / dinleyici YOK; test sonunda gönderici, okuyucu ve yeniden bağlanma
iş parçacıkları durdurulup beklenir.
"""

from __future__ import annotations

import logging
import queue
import socket as _gercek_soket
import struct
import threading
import time
import types
import zlib
from pathlib import Path

import headless_core as hcm
import pytest
from event_bus import EventPriority
from utils.simple_signal import SimpleSignal
from utils.stm32_transport import (
    STM_PAKET_BOBIN_SAYISI,
    STM_PAKET_FMT,
    Stm32OpenResult,
    Stm32PortCandidate,
    build_stm32_zero_duty_packet,
)

GUNLUK = "HeadlessCore"
YENI_BANNER = "-> STM_READY: DDS v2.3 (7-ch KARMA uni=0x60 + HW_SYNC@PB1) proto=3 pkt=121 Waiting for commands..."
SIFIR_ACK = "-> STM_OK: D=0,0,0,0,0,0,0 P=0,0,0,0,0,0,0 F=0,0,0,0,0,0,0 T=0,0,0,0,0,0,0"
ARKA_PLAN_ADLARI = ("STM32Reader", "STM32Reconnect")


def _bekle(kosul, sure: float = 5.0) -> bool:
    son = time.monotonic() + sure
    while time.monotonic() < son:
        if kosul():
            return True
        time.sleep(0.01)
    return bool(kosul())


def _paket(duty: float) -> bytes:
    """Firmware biçimli RUN paketi (tüm bobinler `duty`, 100 Hz) + CRC32."""
    n = STM_PAKET_BOBIN_SAYISI
    veri = struct.pack(STM_PAKET_FMT, 0xAA, 0x55, *([duty] * n), *([0.0] * n), *([100.0] * n), *([1] * n), 0, 0)
    return veri + struct.pack("<I", zlib.crc32(veri) & 0xFFFFFFFF)


class _Veriyolu:
    def __init__(self):
        self.kayit: list[tuple] = []
        self._kilit = threading.Lock()

    def publish(self, event_type, data, priority=EventPriority.NORMAL, source=None, correlation_id=None):
        with self._kilit:
            self.kayit.append((event_type, data, priority, source))
        return True

    def turler(self) -> list[str]:
        with self._kilit:
            return [k[0] for k in self.kayit]

    def hepsi(self, tur: str) -> list[tuple]:
        with self._kilit:
            return [k for k in self.kayit if k[0] == tur]


def _cekirdek(bus, tmp_path) -> hcm.HeadlessCore:
    """`__init__`'in iş parçacığı ve DB açılışı DIŞINDAKİ alanları (aynı değerlerle); gönderici testte açıkça başlatılır."""
    c = hcm.HeadlessCore.__new__(hcm.HeadlessCore)
    c.logger = logging.getLogger(GUNLUK)
    c.app_data_dir = Path(tmp_path)
    c.api_port = 8123
    c.event_bus = bus
    c.stm_connected_signal = SimpleSignal()
    c.stm_is_connected = False
    c.stm_kimlik = None
    c.stm_uyumlu = None
    c.stm_uyumsuzluk_sebebi = ""
    c.stm_uyum_kodu = None
    c._stm_state_lock = threading.RLock()
    c.stm_connected_signal.connect(c._on_stm_connected_slot)
    c.db_acilis_hatalari = {}
    c.db_acilis_ayrintilari = {}
    c.mosquitto_supervisor = None
    c.network_status_service = None
    c.udp_discovery_service = None
    c._hw_send_queue = queue.Queue(maxsize=4)
    c._hw_sender_stop = threading.Event()
    c._hw_izlemeyi_kur()
    return c


def _arka_plan_bitti() -> bool:
    return not [t for t in threading.enumerate() if t.name in ARKA_PLAN_ADLARI and t.is_alive()]


@pytest.fixture
def bus():
    return _Veriyolu()


@pytest.fixture
def hat(monkeypatch):
    """Seri taşıma + UDP soketi (EN ALT kat). `acilis` = sıradaki `open_and_handshake` davranışları: "baglan" | None (port yok) |
    istisna | {ready_line, dogrulama}. Bitince yoksa None."""
    d = types.SimpleNamespace(
        acilis=[],
        acilis_denemesi=0,
        acilan=[],
        kapatma=[],
        kapat_patlat=set(),
        port_var=True,
        satirlar=queue.Queue(),
        okuma_patlat=False,
        okuma_tut=threading.Event(),
        okuma_bekliyor=threading.Event(),
        okuma_serbest=threading.Event(),
        yazilan=[],
        yazim_patlat=False,
        yazim_bekle=None,
        yazim_basladi=threading.Event(),
        soket_istekleri=[],
        secenekler=[],
        gonderilen=[],
        gonderim_patlat=0,
        udp_kapanma=0,
        udp_kapat_patlat=False,
        istisnalar=[],
        cekirdekler=[],
    )

    class _Conn:
        def __init__(self, ad: str):
            self.ad = ad
            self.port = f"COM_KP_{ad}"
            self.is_open = True

        def readline(self):
            if d.okuma_patlat:
                raise OSError(5, "test: ReadFile basarisiz (kablo cikti)")
            if d.okuma_tut.is_set():  # port zaman aşımı içinde bekleyen okuma
                d.okuma_bekliyor.set()
                d.okuma_serbest.wait(5)
                return b""
            try:
                return d.satirlar.get(timeout=0.02)
            except queue.Empty:
                return b""

        def write(self, b):
            d.yazim_basladi.set()
            bekle, d.yazim_bekle = d.yazim_bekle, None
            if bekle is not None:
                bekle.wait(5)  # port tamponu dolu: yazım takılı
            if d.yazim_patlat:
                raise OSError(22, "test: WriteFile basarisiz (USB yari kopuk)")
            d.yazilan.append((self.ad, bytes(b)))

        def close(self):
            self.is_open = False

    class _Tasima:
        def __init__(self, *_a, **_k):
            pass

        def open_and_handshake(self, stop_event=None, on_line=None):
            d.acilis_denemesi += 1
            davranis = d.acilis.pop(0) if d.acilis else None
            if davranis is None:
                return None
            if isinstance(davranis, BaseException):
                raise davranis
            conn = _Conn(f"C{len(d.acilan)}")
            d.acilan.append(conn)
            ayar = davranis if isinstance(davranis, dict) else {}
            return Stm32OpenResult(
                serial=conn,
                candidate=Stm32PortCandidate(device=conn.port, description="KP sahte STM"),
                ready_line=ayar.get("ready_line", YENI_BANNER),
                dogrulama=ayar.get("dogrulama"),
            )

        def close_serial(self, conn):
            d.kapatma.append(conn.ad)
            if conn.ad in d.kapat_patlat:
                raise OSError(13, "test: CloseHandle reddedildi")
            conn.close()

        def port_hala_var(self, _port):
            return d.port_var

    class _Udp:
        def setsockopt(self, *a):
            d.secenekler.append(a)

        def sendto(self, veri, adres):
            if d.gonderim_patlat:
                d.gonderim_patlat -= 1
                raise OSError(10065, "test: hedef ag ulasilamaz")
            d.gonderilen.append((bytes(veri), adres))

        def close(self):
            d.udp_kapanma += 1
            if d.udp_kapat_patlat:
                raise OSError(10038, "test: soket degil")

    def _soket(aile, tip):
        d.soket_istekleri.append((aile, tip))
        return _Udp()

    def _baslat(c):
        t = threading.Thread(target=c._hw_sender_worker, daemon=True, name="HWSender")
        c._hw_sender_thread = t
        d.cekirdekler.append(c)
        t.start()
        return t

    d.Conn = _Conn
    d.baslat = _baslat
    monkeypatch.setattr(hcm, "Stm32SerialTransport", _Tasima)
    monkeypatch.setattr(
        hcm,
        "socket",
        types.SimpleNamespace(
            socket=_soket,
            AF_INET=_gercek_soket.AF_INET,
            SOCK_DGRAM=_gercek_soket.SOCK_DGRAM,
            SOL_SOCKET=_gercek_soket.SOL_SOCKET,
            SO_BROADCAST=_gercek_soket.SO_BROADCAST,
        ),
    )
    monkeypatch.setattr(
        threading,
        "excepthook",
        lambda a: d.istisnalar.append((getattr(a.thread, "name", None), a.exc_type.__name__, str(a.exc_value))),
    )
    yield d
    for c in d.cekirdekler:
        c._hw_sender_stop.set()
    d.okuma_serbest.set()
    for c in d.cekirdekler:
        c._hw_sender_thread.join(timeout=3)
    _bekle(_arka_plan_bitti, 3.0)


def _mesajlar(caplog, seviye=None) -> list[str]:
    return [r.getMessage() for r in list(caplog.records) if seviye is None or r.levelno == seviye]


def _kayit_var(caplog, mesaj: str) -> bool:
    return any(r.getMessage() == mesaj for r in list(caplog.records))


# ───────────────────────────── UDP yolu ve kapanış ─────────────────────────────


def test_UDP_yayin_soketi_KURULUR_paketler_ESPye_gider_kapanista_seri_ve_UDP_KAPATILIR(hat, bus, tmp_path):
    """Gönderici başlarken → tek UDP soketi (AF_INET/SOCK_DGRAM) SO_BROADCAST=1 ile kurulur; kuyruktaki her paketin UDP kısmı kendi
    ESP adresine gider, STM kısmı porta yazılır (STM baytı boşsa yalnız UDP). Okuyucu port zaman aşımında beklerken gönderici durursa →
    son seri bağlantıyı GÖNDERİCİ kapatır ve UDP soketini kapatır; iş parçacıkları istisnasız biter."""
    hat.acilis = ["baglan"]
    c = _cekirdek(bus, tmp_path)
    t = hat.baslat(c)
    assert _bekle(lambda: c.stm_is_connected), "aparat: STM baglanmadi"
    stop = build_stm32_zero_duty_packet()
    c._hw_send_queue.put((b"", b"\x01ESP", "192.168.137.50", 4210))
    c._hw_send_queue.put((stop, b"\x02ESP", "192.168.137.51", 4211))
    assert _bekle(lambda: len(hat.gonderilen) == 2 and len(hat.yazilan) == 1)
    hat.okuma_tut.set()
    assert hat.okuma_bekliyor.wait(2), "aparat: okuyucu beklemeye girmedi"
    c._hw_sender_stop.set()
    t.join(timeout=3)
    assert not t.is_alive()
    assert hat.kapatma == ["C0"] and hat.acilan[0].is_open is False, hat.kapatma
    assert hat.udp_kapanma == 1
    assert hat.soket_istekleri == [(_gercek_soket.AF_INET, _gercek_soket.SOCK_DGRAM)]
    assert hat.secenekler == [(_gercek_soket.SOL_SOCKET, _gercek_soket.SO_BROADCAST, 1)]
    assert hat.gonderilen == [(b"\x01ESP", ("192.168.137.50", 4210)), (b"\x02ESP", ("192.168.137.51", 4211))]
    assert hat.yazilan == [("C0", stop)] and c._hw_son_stop_yazimi == 1
    hat.okuma_serbest.set()
    assert _bekle(_arka_plan_bitti, 3.0)
    assert hat.istisnalar == []


def test_kapanista_seri_ve_UDP_KAPATMA_hatalari_YUTULUR_okuyucu_da_istisnasiz_biter(hat, bus, tmp_path):
    """Kapanışta son seri bağlantının ve UDP soketinin kapatılması istisna verirse → gönderici yine istisnasız biter; ardından okuyucu
    (artık yabancı bağlantı) kendi portunu kapatmayı DENER, o da patlar → okuyucu da istisnasız biter (iki kapatma denemesi)."""
    hat.acilis = ["baglan"]
    c = _cekirdek(bus, tmp_path)
    t = hat.baslat(c)
    assert _bekle(lambda: c.stm_is_connected)
    hat.kapat_patlat = {"C0"}
    hat.udp_kapat_patlat = True
    hat.okuma_tut.set()
    assert hat.okuma_bekliyor.wait(2)
    c._hw_sender_stop.set()
    t.join(timeout=3)
    assert not t.is_alive()
    assert hat.kapatma == ["C0"] and hat.acilan[0].is_open is True and hat.udp_kapanma == 1
    hat.okuma_serbest.set()
    assert _bekle(_arka_plan_bitti, 3.0)
    assert hat.kapatma == ["C0", "C0"]
    assert hat.istisnalar == []


def test_UDP_gonderimi_PATLARSA_uyari_ve_SONRAKI_paket_yine_gider(hat, bus, tmp_path, caplog):
    """UDP `sendto` istisna verirse → WARNING "[UDP SEND] <hata>", gönderici ölmez ve sonraki paketin UDP kısmı gönderilir."""
    hat.acilis = [None]  # STM yok: yalnız ESP yolu
    hat.gonderim_patlat = 1
    c = _cekirdek(bus, tmp_path)
    with caplog.at_level(logging.WARNING, logger=GUNLUK):
        t = hat.baslat(c)
        c._hw_send_queue.put((b"", b"\x01", "192.168.137.60", 4210))
        c._hw_send_queue.put((b"", b"\x02", "192.168.137.61", 4210))
        assert _bekle(lambda: len(hat.gonderilen) == 1)
    assert hat.gonderilen == [(b"\x02", ("192.168.137.61", 4210))]
    assert "[UDP SEND] [Errno 10065] test: hedef ag ulasilamaz" in _mesajlar(caplog, logging.WARNING)
    assert t.is_alive() and hat.istisnalar == []


# ───────────────────────────── NACK tekrarı: kuyruk dolu ─────────────────────────────


def test_kuyruk_DOLUYKEN_NACK_tekrar_istegi_DUSER_okuyucu_ve_baglanti_SURER(hat, bus, tmp_path):
    """Son RUN yazılırken (port tamponu takılı) kuyruk 4/4 dolarsa ve kart NACK dönerse → yeniden oynatma işareti kuyruğa giremez ve
    SESSİZCE düşer: okuyucu ölmez (sonraki satırı işler), STM bağlı kalır; tampon açılınca yalnız beklenen 5 paket yazılır."""
    hat.acilis = ["baglan"]
    tampon = threading.Event()
    hat.yazim_bekle = tampon
    c = _cekirdek(bus, tmp_path)
    hat.baslat(c)
    assert _bekle(lambda: c.stm_is_connected)
    p1 = _paket(40.0)
    c._hw_send_queue.put((p1, None, None, None))
    assert hat.yazim_basladi.wait(2), "aparat: ilk yazim baslamadi"
    sonrakiler = [_paket(10.0 + i) for i in range(4)]
    for p in sonrakiler:
        c._hw_send_queue.put_nowait((p, None, None, None))
    assert c._hw_send_queue.full()
    hat.satirlar.put(b"-> STM_NACK: CRC\r\n")
    hat.satirlar.put(b"-> STM_ERR: isaret\r\n")
    try:
        assert _bekle(lambda: bus.hepsi("hardware.stm.error")), "NACK'ten sonra okuyucu satır işlemedi (öldü mü?)"
        assert bus.hepsi("hardware.stm.nack") and c.stm_is_connected is True
        assert c._hw_send_queue.qsize() == 4
        assert not [o for o in list(c._hw_send_queue.queue) if isinstance(o, hcm._NackTekrari)]
    finally:
        tampon.set()
    assert _bekle(lambda: len(hat.yazilan) == 5)
    assert [b for _ad, b in hat.yazilan] == [p1, *sonrakiler]
    assert hat.istisnalar == []


# ───────────────────────────── bağlantı kurma ve kapatma hataları ─────────────────────────────


def test_devralinan_ESKI_baglanti_KAPATILAMAZSA_yine_YENI_baglanti_kurulur(hat, bus, tmp_path):
    """Yeniden başlatılan gönderici, önceki çalışanın bağlantısını devralır; onu kapatmak istisna verirse → istisna yutulur, el sıkışma
    yine denenir ve YENİ bağlantı etkin olur (`hardware.stm.connected`)."""
    hat.acilis = ["baglan"]
    hat.kapat_patlat = {"ESKI"}
    c = _cekirdek(bus, tmp_path)
    eski = hat.Conn("ESKI")
    c._seri_baglanti = hcm.SeriBaglantiDurumu()
    c._seri_baglanti.yerlestir(eski)
    hat.baslat(c)
    assert _bekle(lambda: c.stm_is_connected)
    assert hat.kapatma[0] == "ESKI" and eski.is_open is True
    assert c._seri_baglanti.aktif() is hat.acilan[0]
    assert [v for _t, v, _p, _s in bus.hepsi("hardware.stm.connected")] == [{"connected": True}]
    assert hat.istisnalar == []


def test_seri_port_ACILAMAZSA_uyari_KOPUK_kalir_dongu_SURER(hat, bus, tmp_path, caplog):
    """El sıkışma istisna verirse (COM portu başka süreçte açık) → WARNING "[STM32] Serial open failed: <hata>", STM kopuk, porta yazım
    YOK; gönderici döngüsü sürer (UDP kısmı gider)."""
    hat.acilis = [PermissionError(13, "test: COM portu baska surecte acik")]
    c = _cekirdek(bus, tmp_path)
    with caplog.at_level(logging.WARNING, logger=GUNLUK):
        t = hat.baslat(c)
        c._hw_send_queue.put((build_stm32_zero_duty_packet(), b"\x03", "192.168.137.70", 4210))
        assert _bekle(lambda: hat.gonderilen)
    assert "[STM32] Serial open failed: [Errno 13] test: COM portu baska surecte acik" in _mesajlar(
        caplog, logging.WARNING
    )
    assert c.stm_is_connected is False and c._seri_baglanti.aktif() is None and hat.yazilan == []
    assert t.is_alive() and hat.istisnalar == []


class _KirilganGunluk:
    """Gerçek günlüğe devreder; `kirik_onek` ile başlayan WARNING'de disk dolu hatası verir (günlük yazılamadı)."""

    def __init__(self, gercek: logging.Logger, kirik_onek: str):
        self._gercek = gercek
        self._kirik = kirik_onek

    def warning(self, msg, *a, **k):
        if str(msg).startswith(self._kirik):
            raise OSError(28, "test: gunluk diski dolu")
        return self._gercek.warning(msg, *a, **k)

    def __getattr__(self, ad):
        return getattr(self._gercek, ad)


def test_READYsiz_el_sikismada_kimlik_GORUNURLUGU_yazilamazsa_baglanti_SURER(hat, bus, tmp_path, caplog):
    """El sıkışma STM_READY'siz bitti (kart resetlenmeden bağlandı) ve "kimlik okunamadı" uyarısı yazılamazsa → DEBUG "kimlik gorunurlugu
    yazilamadi (baglanti SURUYOR)" (istisna izli); "okunamadı" kararı yine işaretlenir, bağlantı etkin kalır, okuyucu satır işler."""
    hat.acilis = [{"ready_line": SIFIR_ACK}]
    c = _cekirdek(bus, tmp_path)
    c.logger = _KirilganGunluk(logging.getLogger(GUNLUK), "STM32 firmware kimligi okunamadi — kart resetlenmeden")
    mesaj = "[STM32] kimlik gorunurlugu yazilamadi (baglanti SURUYOR)"
    with caplog.at_level(logging.DEBUG, logger=GUNLUK):
        hat.baslat(c)
        assert _bekle(lambda: c.stm_is_connected)
        assert _bekle(lambda: _kayit_var(caplog, mesaj))
        hat.satirlar.put(b"-> STM_ERR: canli\r\n")
        assert _bekle(lambda: bus.hepsi("hardware.stm.error"))
    kayit = [r for r in list(caplog.records) if r.getMessage() == mesaj]
    assert kayit[0].levelno == logging.DEBUG and kayit[0].exc_info[0] is OSError
    assert c._stm_kanit()["okunamadi"] is True
    assert c.stm_is_connected is True and c._seri_baglanti.aktif() is hat.acilan[0]
    assert hat.istisnalar == []


def test_dogrulama_OZETI_islenemezse_hata_ayiklama_izi_baglanti_SURER(hat, bus, tmp_path, caplog):
    """El sıkışma doğrulama özeti bozuksa (`crc_nack` sayı değil) → DEBUG "dogrulama sonucu islenemedi (baglanti SURUYOR)" (ValueError
    izli); "doğrulanamadı" kararı kurulmaz, bağlantı etkin kalır."""
    hat.acilis = [{"dogrulama": {"kabul": False, "kimlik": False, "crc_nack": "bozuk", "yoklama": 3}}]
    c = _cekirdek(bus, tmp_path)
    mesaj = "[STM32] dogrulama sonucu islenemedi (baglanti SURUYOR)"
    with caplog.at_level(logging.DEBUG, logger=GUNLUK):
        hat.baslat(c)
        assert _bekle(lambda: _kayit_var(caplog, mesaj))
    kayit = [r for r in list(caplog.records) if r.getMessage() == mesaj]
    assert kayit[0].levelno == logging.DEBUG and kayit[0].exc_info[0] is ValueError
    assert c._stm_kanit()["dogrulanamadi"] is False
    assert c.stm_is_connected is True and c._seri_baglanti.aktif() is hat.acilan[0]
    assert hat.istisnalar == []


def test_okuyucu_OKUMA_hatasinda_KOPUK_yayinlar_portunu_KAPATAMASA_da_istisnasiz_biter(hat, bus, tmp_path, caplog):
    """Okuma istisnası (kablo çıktı) → WARNING "[STM32 READER] <hata>", okuyucu kendi bağlantısını bırakır → `hardware.stm.disconnected`;
    portunu kapatmak istisna verse de okuyucu iş parçacığı istisnasız biter, gönderici sürer."""
    hat.acilis = ["baglan"]
    c = _cekirdek(bus, tmp_path)
    t = hat.baslat(c)
    assert _bekle(lambda: c.stm_is_connected)
    hat.kapat_patlat = {"C0"}
    with caplog.at_level(logging.WARNING, logger=GUNLUK):
        hat.okuma_patlat = True
        assert _bekle(lambda: bus.hepsi("hardware.stm.disconnected"))
        assert _bekle(_arka_plan_bitti, 3.0)
    assert "[STM32 READER] [Errno 5] test: ReadFile basarisiz (kablo cikti)" in _mesajlar(caplog, logging.WARNING)
    assert "C0" in hat.kapatma and hat.acilan[0].is_open is True
    assert c.stm_is_connected is False and c._seri_baglanti.aktif() is None
    assert t.is_alive() and hat.istisnalar == []


def test_PORT_KAYBINDA_baglanti_dusurulur_portu_KAPATAMASA_da_dongu_SURER(hat, bus, tmp_path, monkeypatch, caplog):
    """Port numaralandırmadan düşerse → bağlantı geçersizlenir, `hardware.stm.disconnected`, WARNING "Seri port kayboldu (<port>)";
    portu kapatmak istisna verse de gönderici sürer."""
    monkeypatch.setattr(hcm, "_PORT_CHECK_S", 0.05)
    hat.acilis = ["baglan"]
    c = _cekirdek(bus, tmp_path)
    t = hat.baslat(c)
    assert _bekle(lambda: c.stm_is_connected)
    hat.kapat_patlat = {"C0"}
    mesaj = "[STM32] Seri port kayboldu (COM_KP_C0) → bağlantı düşürülüyor, bobinler çevrimdışı."
    with caplog.at_level(logging.WARNING, logger=GUNLUK):
        hat.port_var = False
        assert _bekle(lambda: bus.hepsi("hardware.stm.disconnected"))
        assert _bekle(lambda: _kayit_var(caplog, mesaj))
    assert "C0" in hat.kapatma and c._seri_baglanti.aktif() is None and c.stm_is_connected is False
    assert t.is_alive() and hat.istisnalar == []


def test_YAZIM_hatasinda_baglanti_dusurulur_portu_KAPATAMASA_da_dongu_SURER(hat, bus, tmp_path, caplog):
    """Porta yazım istisna verirse → WARNING "[STM32 SEND] <hata>", bağlantı düşer (`hardware.stm.disconnected`), yazım izi SAYILMAZ;
    portu kapatmak istisna verse de gönderici sürer."""
    hat.acilis = ["baglan"]
    c = _cekirdek(bus, tmp_path)
    t = hat.baslat(c)
    assert _bekle(lambda: c.stm_is_connected)
    hat.kapat_patlat = {"C0"}
    hat.yazim_patlat = True
    mesaj = "[STM32 SEND] [Errno 22] test: WriteFile basarisiz (USB yari kopuk)"
    with caplog.at_level(logging.WARNING, logger=GUNLUK):
        c._hw_send_queue.put((build_stm32_zero_duty_packet(), None, None, None))
        assert _bekle(lambda: bus.hepsi("hardware.stm.disconnected"))
        assert _bekle(lambda: _kayit_var(caplog, mesaj))
    assert c._hw_yazim_sayaci == 0 and hat.yazilan == []
    assert "C0" in hat.kapatma and c.stm_is_connected is False and c._seri_baglanti.aktif() is None
    assert t.is_alive() and hat.istisnalar == []


# ───────────────────────────── çekirdek kurulumu ─────────────────────────────


def _hizmet_siniflari(kayit: list):
    def _sinif(ad):
        class _Hizmet:
            def __init__(self, **kw):
                kayit.append((ad, "kur", kw))

            def start(self):
                kayit.append((ad, "start", None))

            def stop(self):
                kayit.append((ad, "stop", None))

            def get_status(self):
                return {"hizmet": ad}

        return _Hizmet

    return _sinif("mosquitto"), _sinif("ag"), _sinif("udp")


def test_cekirdek_KURULUMU_DB_acilamazsa_Y43_is_parcacigi_baslar_HIZMETLER_istenen_kiple_baslar(
    hat, monkeypatch, tmp_path
):
    """`HeadlessCore(start_headless_services=True, ensure_mosquitto=False)` iki DB de açılamazken → çekirdek kurulur (DB'siz kısıtlı),
    nedenler kaydedilir, Y43 arka plan iş parçacığı ("db-yeniden-ac", daemon) ÇALIŞIR; hizmetler sırayla `ensure_running=False` ve verilen
    API portuyla başlatılır; `system.core.started` yayınlanır. `quit` → Y43 ve gönderici iş parçacıkları biter, hizmetler durdurulur."""
    from database import patient_database as _pdb
    from database import treatment_history_db as _thdb

    monkeypatch.setattr(_pdb, "_acilis_kilidi", dict(_pdb._acilis_kilidi))
    monkeypatch.setattr(_thdb, "_acilis_kilidi", dict(_thdb._acilis_kilidi))

    def _hasta_yok(_kok):
        raise RuntimeError("test: Karar-6 fail-closed")

    def _tedavi_yok(_kok):
        raise PermissionError(13, "test: tedavi DB kilitli")

    monkeypatch.setattr(hcm, "get_patient_database", _hasta_yok)
    monkeypatch.setattr(hcm, "get_session_manager", _tedavi_yok)
    kayit: list = []
    mq, ag, udp = _hizmet_siniflari(kayit)
    monkeypatch.setattr(hcm, "MosquittoSupervisor", mq)
    monkeypatch.setattr(hcm, "NetworkStatusService", ag)
    monkeypatch.setattr(hcm, "UdpDiscoveryService", udp)
    hat.acilis = [None]
    bus = _Veriyolu()
    kok = tmp_path / "veri"
    core = hcm.HeadlessCore(kok, api_port=8124, start_headless_services=True, ensure_mosquitto=False, event_bus=bus)
    try:
        y43 = core._db_yeniden_thread
        assert y43 is not None and y43.name == "db-yeniden-ac" and y43.daemon and y43.is_alive()
        assert core.patient_db is None and core.session_manager is None
        assert core.db_acilis_ayrintilari == {
            "hasta": ("acilamadi", "RuntimeError"),
            "tedavi": ("acilamadi", "PermissionError"),
        }
        assert set(core.db_acilis_hatalari) == {"hasta", "tedavi"}
        assert [(a, s) for a, s, _k in kayit] == [
            ("mosquitto", "kur"),
            ("mosquitto", "start"),
            ("ag", "kur"),
            ("ag", "start"),
            ("udp", "kur"),
            ("udp", "start"),
        ]
        assert kayit[0][2]["ensure_running"] is False and kayit[4][2]["api_port"] == 8124
        assert ("system.core.started", {"appDataDir": str(kok)}) in [(t, v) for t, v, _p, _s in bus.kayit]
    finally:
        core.quit()
    assert not core._db_yeniden_thread.is_alive() and not core._hw_sender_thread.is_alive()
    assert [(a, s) for a, s, _k in kayit][-3:] == [("udp", "stop"), ("ag", "stop"), ("mosquitto", "stop")]
    assert _bekle(_arka_plan_bitti, 3.0) and hat.istisnalar == []
