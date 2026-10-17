# Author: mertaygn, cglrgrkn
"""SGI-3.1 (bağımsız inceleme) — STM okuyucusu zaman aşımında dönen YARIM satırı tam satır gibi işlememeli.

ÖLÇÜLEN (549ce2b0): pyserial `readline()` portun zaman aşımında (0,3 sn) satır sonunu beklemeden döner — satırın ortasında 0,35 sn
boşlukta ilk okuma 40 B (yarım), ikincisi kalan 44 B (ölçüldü, pyserial 3.5). Okuyucu her okumayı ayrı satır sayıyordu: yarım READY
"banner DEĞİŞTİ" sayılır (TD1 kanıtı SIFIRLANIR — eski kartın RED kanıtı silinir, FW-PAKET bandı kalkar), kalan parça çöp satır olur;
aynı yol bir ACK'i ikiye bölüp E-stop teyidini de kaçırabilir.
SÖZLEŞME: satır sonu olmadan dönen parça bir sonraki okumayla BİRLEŞTİRİLİR; sonraki okuma boş dönerse (gerçekten kesik satır — ör. kart
satır ortasında yeniden başladı) parça bugünkü gibi işlenir. Aparat: GERÇEK `HeadlessCore._hw_sender_worker` (okuyucu dahil) + GERÇEK
`Stm32SerialTransport` el sıkışması; yalnız seri port bayt düzeyinde sahte (uyumlu kart — NACK yok, ölçüm penceresi sessiz).
"""

from __future__ import annotations

import logging
import queue
import struct
import threading
import time

import pytest

YENI_BANNER = "-> STM_READY: DDS v2.3 (7-ch KARMA uni=0x60 + HW_SYNC@PB1) proto=3 pkt=121 Waiting for commands..."
YENI_KIMLIK = "-> STM_ID: DDS v2.3 (7-ch KARMA uni=0x60 + HW_SYNC@PB1) proto=3 pkt=121"
YARIM = b"-> STM_READY: DDS v2.3 (7-ch KARMA uni=0x60 + HW_SY"
KALAN = b"NC@PB1) proto=3 pkt=121 Waiting for commands...\r\n"


class _Kart:
    """Uyumlu kart: kimlik sorgusuna Y68 yanıtı, pakete GERÇEK biçimli `STM_OK`. `readline` kuyruktaki parçayı AYNEN döner."""

    def __init__(self):
        from utils.stm32_transport import STM_KIMLIK_SORGUSU, STM_PAKET_BOBIN_SAYISI, STM_PAKET_BOYU

        self.port = "COM_SGI31"
        self.is_open = True
        self.q: queue.Queue = queue.Queue()
        self.q.put((YENI_BANNER + "\r\n").encode())
        self._sorgu, self._boy, self._n = STM_KIMLIK_SORGUSU, STM_PAKET_BOYU, STM_PAKET_BOBIN_SAYISI

    def readline(self):
        try:
            return self.q.get(timeout=0.02)
        except queue.Empty:
            return b""

    def write(self, b):
        b = bytes(b)
        if b == self._sorgu:
            self.q.put((YENI_KIMLIK + "\r\n").encode())
        elif len(b) == self._boy and b[:2] == b"\xaa\x55":
            d = struct.unpack_from(f"<{self._n}f", b, 2)
            z = ",".join("0" for _ in range(self._n))
            duty = ",".join(str(int(round(x))) for x in d)
            ack = f"-> STM_OK: D={duty} P={z} F=" + ",".join("100" for _ in d) + f" T={z} K=96 E={duty}"
            self.q.put((ack + "\r\n").encode())
        return len(b)

    def close(self):
        self.is_open = False


@pytest.fixture
def cekirdek(monkeypatch):
    import socket as _s
    import types

    import headless_core as hcm
    from utils import stm32_transport as st

    monkeypatch.setattr(st, "VCP_SETTLE_TIME_SEC", 0.0)
    monkeypatch.setattr(st, "HANDSHAKE_PASSIVE_LISTEN_SEC", 0.05)
    monkeypatch.setattr(hcm, "_PORT_CHECK_S", 0.05)

    def _soket_yok(*_a, **_k):
        raise OSError("test: UDP soketi kurulmaz")

    monkeypatch.setattr(
        hcm,
        "socket",
        types.SimpleNamespace(
            socket=_soket_yok,
            AF_INET=_s.AF_INET,
            SOCK_DGRAM=_s.SOCK_DGRAM,
            SOL_SOCKET=_s.SOL_SOCKET,
            SO_BROADCAST=_s.SO_BROADCAST,
        ),
    )
    kart = _Kart()

    class _T(st.Stm32SerialTransport):
        def __init__(self, logger, *a, **k):
            super().__init__(logger, handshake_timeout_sec=2.0)

        def _select_candidate(self):
            return st.Stm32PortCandidate(device=kart.port, description="test")

        def _open_serial(self, candidate):
            return kart

        def port_hala_var(self, _port):
            return True

    monkeypatch.setattr(hcm, "Stm32SerialTransport", _T)
    core = hcm.HeadlessCore.__new__(hcm.HeadlessCore)
    core.logger = logging.getLogger("test-sgi31")
    core._hw_sender_stop = threading.Event()
    core._hw_send_queue = queue.Queue()
    core._stm_state_lock = threading.RLock()
    core.stm_kimlik = None
    core.stm_uyumlu = None
    core.stm_uyumsuzluk_sebebi = ""
    core.baglanti, core.olaylar = [], []
    core._set_stm_connected = lambda v: core.baglanti.append(v)
    core._publish_event = lambda tur_, veri=None, **k: core.olaylar.append((tur_, veri))
    t = threading.Thread(target=core._hw_sender_worker, daemon=True, name="test-HWSender-SGI31")
    core._hw_sender_thread = t  # gerçek kurucu gibi (gönderici bekçisi bunu okur)
    t.start()
    try:
        bitis = time.monotonic() + 8.0
        while time.monotonic() < bitis and core.baglanti[-1:] != [True]:
            time.sleep(0.01)
        assert core.baglanti[-1:] == [True], f"aparat: bağlantı kurulmadı {core.baglanti}"
        time.sleep(1.8)  # el sıkışma doğrulama yoklaması bitsin (≤ 1,5 sn)
        yield core, kart
    finally:
        core._hw_sender_stop.set()
        t.join(3)


def _sayac(core) -> int:
    return int(getattr(core, "_stm_banner_sayaci", 0))


def test_KRITIK_ikiye_bolunmus_READY_TEK_tam_banner_olarak_islenir(cekirdek):
    core, kart = cekirdek
    once = _sayac(core)
    kart.q.put(YARIM)  # zaman aşımında yarım dönen okuma
    kart.q.put(KALAN)  # devamı bir sonraki okumada
    time.sleep(0.4)
    assert getattr(core, "_stm_son_banner", None) == YENI_BANNER, (
        f"ikiye bölünmüş READY tam satır olarak işlenmedi: son banner {getattr(core, '_stm_son_banner', None)!r}"
    )
    assert _sayac(core) == once + 1, f"tek READY {_sayac(core) - once} banner olarak sayıldı"


def test_KARSIT_devami_GELMEYEN_kesik_satir_bugunku_gibi_ISLENIR(cekirdek):
    """Sonraki okuma boş dönerse (gerçekten kesik satır) parça satır olarak işlenir — bilgi kaybolmaz, yalnız bir okuma gecikir."""
    core, kart = cekirdek
    kart.q.put(YARIM)
    time.sleep(0.4)
    assert getattr(core, "_stm_son_banner", None) == YARIM.decode(), core._stm_son_banner
