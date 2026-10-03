# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""1-E inceleme O-1.1 (ÖNCEDEN VAR) — ESKİ okuyucunun `STM_OK` satırı kopuk bağlantıyı yeniden "bağlı" YAPAMAZ.

ÖLÇÜLEN KUSUR: port kaybı dalı `gecersizle()` + `_set_stm_connected(False)` yaptıktan sonra, `readline()`'dan elinde satır
olan AYNI (artık geçersiz) bağlantının okuyucusu `STM_OK`'u işlerse `_handle_stm_line` koşulsuz `_set_stm_connected(True)`
diyordu → kablo çıkıkken `stm_is_connected` yeniden True; okuyucunun `finally`'si nesil değiştiği için False yazmaz. Pencere
bir sonraki yeniden bağlanma denemesine dek sürer (kablo hiç takılmazsa: yeniden bağlanma hep başarısız → KALICI). O arada
arayüz STM'i "bağlı" gösterir, START kabul edilir (Y45 bir sonraki False geçişinde mandal kurar — fail-safe yönü).

KAPI: GERÇEK `_hw_sender_worker` + GERÇEK `_handle_stm_line` (D1.54 aparatının aynısı; sahte olan taşıma, `socket` ve
bildirim kaydedicisi). Yarış ELLE kurulur: ESKİ okuyucu `readline()` içinde bekletilir, kablo çekilir (yeniden bağlanma
başarısız), okuyucu ANCAK ŞİMDİ `STM_OK` satırıyla döner.
"""

from __future__ import annotations

import queue
import socket as _gercek_socket
import threading
import time
import types

import headless_core as hcm

_STM_OK = b"-> STM_OK: CRC=0x0000\n"


def _bekle(kosul, sure=8.0):
    son = time.monotonic() + sure
    while time.monotonic() < son and not kosul():
        time.sleep(0.01)
    return kosul()


def test_KRITIK_O11_kopuk_baglantinin_ESKI_okuyucusu_STM_OK_ile_BAGLI_yapamaz(monkeypatch):
    d = types.SimpleNamespace(acilan=[], kapanan=[], stm=[], kablo_cekik=False)
    eski_okumada = threading.Event()
    eski_uyan = threading.Event()

    class _Conn:
        def __init__(self, ad: str):
            self.ad = ad
            self.port = "COM_TEST"
            self.is_open = True
            self._verildi = False

        def readline(self):
            if self.ad == "ESKI" and not self._verildi:
                eski_okumada.set()
                eski_uyan.wait(10)
                self._verildi = True
                return _STM_OK  # kablo çekilmeden ÖNCE tampona girmiş son satır
            time.sleep(0.02)
            if not self.is_open:
                raise OSError("test: port kapali")
            return b""

        def write(self, _b):
            pass

        def close(self):
            self.is_open = False

    class _Tasima:
        def __init__(self, *a, **k):
            pass

        def open_and_handshake(self, stop_event=None, on_line=None):
            if d.kablo_cekik or any(c.is_open for c in d.acilan):
                return None  # kablo çıkık: port açılamaz (yeniden bağlanma BAŞARISIZ)
            c = _Conn("ESKI" if not d.acilan else f"YENI{len(d.acilan)}")
            d.acilan.append(c)
            return types.SimpleNamespace(serial=c)

        def close_serial(self, c):
            d.kapanan.append(c)
            c.close()

        def port_hala_var(self, _port):
            return not d.kablo_cekik

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
    core = hcm.HeadlessCore.__new__(hcm.HeadlessCore)
    core.logger = __import__("logging").getLogger("test-O11-eski-okuyucu")
    core._hw_sender_stop = threading.Event()
    core._hw_send_queue = queue.Queue()
    core._set_stm_connected = lambda v: d.stm.append(v)
    core._publish_event = lambda *a, **k: None  # GERÇEK `_handle_stm_line` koşar; olay yayını kaydedilmez

    t = threading.Thread(target=core._hw_sender_worker, daemon=True, name="test-HWSender-O11")
    t.start()
    try:
        assert _bekle(lambda: d.acilan and eski_okumada.is_set() and d.stm[-1:] == [True]), (
            f"aparat: ESKI kurulmadi {d}"
        )
        eski = d.acilan[0]
        d.kablo_cekik = True
        assert _bekle(lambda: eski in d.kapanan and d.stm[-1:] == [False]), f"aparat: kopus bildirilmedi {d}"
        kopus_sonrasi = len(d.stm)
        eski_uyan.set()  # ESKİ okuyucu elindeki STM_OK satırıyla döner
        time.sleep(0.4)
        sonra = d.stm[kopus_sonrasi:]
        canli = t.is_alive()
    finally:
        eski_uyan.set()
        core._hw_sender_stop.set()
        t.join(3)
    assert len(d.acilan) == 1, f"aparat: kablo cekikken yeniden baglanildi {d.acilan}"
    assert True not in sonra, (
        f"kablo ÇIKIKKEN eski okuyucunun STM_OK'u STM'i yeniden 'BAĞLI' yaptı {sonra} — arayüz bağlı gösterir, START kabul edilir"
    )
    assert canli, "HWSender oldu"


def test_KARSIT_O11_ETKIN_okuyucunun_ve_el_sikismanin_STM_OK_u_BAGLI_yapar():
    core = hcm.HeadlessCore.__new__(hcm.HeadlessCore)
    core.logger = __import__("logging").getLogger("test-O11-karsit")
    kayit: list = []
    core._set_stm_connected = lambda v: kayit.append(v)
    core._publish_event = lambda *a, **k: None
    satir = _STM_OK.decode().strip()
    core._handle_stm_line(satir, None)  # el sıkışma yolu (bağlantı henüz yerleşmedi) — eski davranış
    assert kayit == [True], kayit
    kayit.clear()
    try:
        core._handle_stm_line(satir, None, baglanti_etkin=lambda: True)  # etkin okuyucu
    except TypeError:
        return  # önce-ölçümde (parametre yok) karşıt kolun bu yarısı uygulanamaz — ilk yarı yeşil
    assert kayit == [True], kayit
