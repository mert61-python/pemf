# Author: mertaygn, cglrgrkn
"""D1.32 · B-10.33 — STM seri YAZIM HATASI dalı DAVRANIŞLA: port kapanır, bayat paket düşer, kimlik korunur.

ÖLÇÜLEN KÖRLÜK: `test_coil_transport::test_serial_write_failure_closes_port_and_drops_stale_payload`
`inspect.getsource` diliminde metin arıyordu (`close_serial(`, `last_payload[0] = None`, `_benim`).
Üç mutant bugün YEŞİL kalıyordu: `_benim = True` (eski yazım hatası YENİ bağlantıyı da düşürür →
"geri takınca hazıra dönmüyor"), `close_serial` `if False:` altında (port açık-ama-ölü kalır, yeniden
bağlanma tetiklenmez), bayat paket düşürme `if False:` altında (NACK yeniden oynatması kopuk/yeni hatta
eski paketi tekrar gönderir — STOP'tan sonra yeniden enerjileme sınıfı).

Kapı GERÇEK `HeadlessCore._hw_sender_worker`ı koşar (`__new__` çekirdek; sahte olan yalnız taşıma,
`socket` ve paylaşılan bağlantı nesnesinin GÖZLEMCİ alt sınıfı). Paketler gerçek kuyruğa konur;
yeniden oynatma GERÇEK `retry_last_payload` (okuyucunun `_handle_stm_line`'a verdiği geri çağrı) ile
denenir. Karşıt kol: yazım başarılıyken aynı geri çağrı paketi GERÇEKTEN yeniden kuyruğa koyar
(aparat canlı; "hiç oynatmayan" bir mutant da yakalanır).
"""

from __future__ import annotations

import queue
import socket as _gercek_socket
import threading
import time
import types

import pytest


class _KayitciKuyruk(queue.Queue):
    def __init__(self):
        super().__init__()
        self.konan: list = []

    def put_nowait(self, item):
        self.konan.append(item)
        return super().put_nowait(item)


def _bekle(kosul, sure=5.0):
    son = time.monotonic() + sure
    while time.monotonic() < son and not kosul():
        time.sleep(0.01)
    return kosul()


@pytest.fixture
def aparat(monkeypatch):
    import headless_core as hcm

    d = types.SimpleNamespace(
        baglanti_nesneleri=[], acilan=[], kapanan=[], stm=[], geri_cagri=None, yazim_davranisi=None
    )

    class _GozlemciBaglanti(hcm.SeriBaglantiDurumu):
        def __init__(self):
            super().__init__()
            d.baglanti_nesneleri.append(self)

    class _Conn:
        def __init__(self, ad):
            self.ad = ad
            self.port = f"COM_{ad}"
            self.is_open = True
            self.yazilan: list = []
            self._satir_verildi = False

        def readline(self):
            # İlk satır: okuyucu `_handle_stm_line(satir, retry_last_payload)` çağırır → geri çağrı yakalanır.
            if not self._satir_verildi:
                self._satir_verildi = True
                return b"-> STM_OK: test\n"
            time.sleep(0.02)
            return b""

        def write(self, b):
            self.yazilan.append(b)
            if d.yazim_davranisi:
                d.yazim_davranisi(self, b)

        def close(self):
            self.is_open = False

    class _Tasima:
        def __init__(self, *a, **k):
            pass

        def open_and_handshake(self, stop_event=None, on_line=None):
            c = _Conn(f"A{len(d.acilan)}")
            d.acilan.append(c)
            return types.SimpleNamespace(serial=c)

        def close_serial(self, c):
            d.kapanan.append(c)
            c.close()

        def port_hala_var(self, _port):
            return True

    def _soket_yok(*_a, **_k):
        raise OSError("test: UDP soketi kurulmaz")

    monkeypatch.setattr(hcm, "SeriBaglantiDurumu", _GozlemciBaglanti)
    monkeypatch.setattr(hcm, "Stm32SerialTransport", _Tasima)
    monkeypatch.setattr(hcm, "_RETRY_MAX_AGE_S", 5.0)  # yaş sınırı testin zamanlamasını belirlemesin
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
    core = hcm.HeadlessCore.__new__(hcm.HeadlessCore)
    core.logger = __import__("logging").getLogger("test-hwsender-yazim")
    core._hw_sender_stop = threading.Event()
    core._hw_send_queue = _KayitciKuyruk()
    core._set_stm_connected = lambda v: d.stm.append(v)

    def _satir(line, retry, **_k):  # O-1.1: okuyucu `baglanti_etkin=` de verir (aparat imzası)
        d.geri_cagri = retry

    core._handle_stm_line = _satir
    t = threading.Thread(target=core._hw_sender_worker, daemon=True, name="test-HWSender-yazim")
    t.start()
    assert _bekle(lambda: d.acilan and d.geri_cagri is not None), f"aparat: STM bağlanmadı / okuyucu satır vermedi {d}"
    try:
        yield core, d, t
    finally:
        core._hw_sender_stop.set()
        t.join(timeout=3)


def _paket(ad: bytes):
    return (ad, None, None, None)


def test_KARSIT_yazim_basariliyken_NACK_yeniden_oynatmasi_paketi_KUYRUGA_koyar(aparat):
    core, d, _t = aparat
    a = d.acilan[0]
    core._hw_send_queue.put(_paket(b"P1"))
    assert _bekle(lambda: a.yazilan == [b"P1"]), f"aparat: paket yazılmadı {a.yazilan}"
    d.geri_cagri()
    # D1.72 (B-1.17): kuyruğa paketin kendisi değil `_NackTekrari` işareti girer (kararı gönderici verir).
    assert any(getattr(x, "paket", x) == _paket(b"P1") for x in core._hw_send_queue.konan), (
        "yeniden oynatma hiç çalışmıyor (aparat ya da ürün)"
    )
    assert _bekle(lambda: a.yazilan == [b"P1", b"P1"]), "yeniden oynatılan paket yazılmadı"


def test_KRITIK_yazim_hatasi_PORTU_KAPATIR_ve_BAYAT_paketi_DUSURUR(aparat):
    core, d, t = aparat
    a = d.acilan[0]

    def _patla(conn, b):
        raise OSError(22, "test: USB yarı kopuk — WriteFile başarısız")

    d.yazim_davranisi = _patla
    core._hw_send_queue.put(_paket(b"P_RUN"))
    assert _bekle(lambda: a in d.kapanan), "yazım hatasında port KAPATILMADI — yeniden bağlanma hiç tetiklenmez"
    assert False in d.stm[2:], f"yazım hatası 'STM kopuk' bildirmedi: {d.stm}"
    assert t.is_alive(), "yazım hatası HWSender'ı öldürdü"
    oncesi = len(core._hw_send_queue.konan)
    d.geri_cagri()  # gecikmiş NACK, kopuk hatta son paketi yeniden oynatmaya çalışır
    assert core._hw_send_queue.konan[oncesi:] == [], (
        "kopuk hatta BAYAT paket yeniden kuyruğa kondu (yeni bağlantıda eski komut / STOP sonrası enerjileme)"
    )


def test_KRITIK_ESKI_yazim_hatasi_YENI_baglantiyi_DUSURMEZ(aparat):
    """Yazım bloklanırken yeniden bağlanma tamamlandıysa (B yerleşti), A'nın hatası B'yi geçersizlememeli."""
    core, d, t = aparat
    a = d.acilan[0]
    baglanti = d.baglanti_nesneleri[0]
    b_conn = types.SimpleNamespace(port="COM_B", is_open=True, write=lambda _b: None, close=lambda: None)

    def _yeniden_baglanip_patla(conn, _b):
        if conn is a:
            baglanti.gecersizle()
            baglanti.yerlestir(b_conn)
            raise OSError(22, "test: eski bağlantıda gecikmiş yazım hatası")

    d.yazim_davranisi = _yeniden_baglanip_patla
    stm_once = len(d.stm)
    core._hw_send_queue.put(_paket(b"P_RUN"))
    assert _bekle(lambda: a in d.kapanan), "eski bağlantı (kendi kaynağı) kapatılmadı"
    time.sleep(0.1)
    assert baglanti.aktif() is b_conn, "ESKİ yazım hatası YENİ bağlantıyı düşürdü — kablo takılıyken hazıra dönmez"
    assert b_conn.is_open and b_conn not in d.kapanan, "yeni bağlantı kapatıldı"
    assert False not in d.stm[stm_once:], f"eski hata yeni bağlantıyı 'kopuk' ilan etti: {d.stm[stm_once:]}"
    assert t.is_alive()
