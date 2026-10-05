# Author: mertaygn, cglrgrkn
"""D1.103 · B-1.20 · B-1.21 — firmware uyum kararı kanal + PAKET BOYU (banner revizyonu); resetsiz bağlanmada kimliğin
okunamadığı GÖRÜNÜR.

ÖLÇÜLEN KUSURLAR (DENETIM-01 tv-F8_2/tv-F8_3):
  B-1.20 — karar YALNIZ kanal sayısına bakıyordu: 7 kanallı ama 120 baytlık (sürüş kipi baytı olmayan) firmware
           revizyonları "uyumlu" sayılıyordu (o kart backend'in 121 baytlık her paketini NACK'ler); gerçek v2.2 banner'ı
           (kipsiz) "bilinmiyor"a düşüyordu.
  B-1.21 — kart RESETLENMEDEN bağlanınca (banner yalnız açılışta basılır; el sıkışma sıfır-duty yoklamasına STM_OK ile
           biter) kimlik hiç okunmuyor ve bu SESSİZ kalıyordu; resetsiz bağlanan ESKİ kart yoklamayı NACK'lerken el sıkışma
           zaman aşımı "USART3/COM10" diye kablo/port yönüne yönlendiriyordu.

REVİZYON TABLOSU: aşağıdaki satırlar `git show <rev>:firmware/stm32_pemf*/Core/Src/main.c` banner biçim dizelerinden ve
`BinaryCmdPacket_t` düzeninden (kip baytı `unipolar_maskesi` var mı) 2026-10-05'te ÜRETİLDİ (1-G, `d1103_revizyon_tablosu.py`;
derleme bayrağıyla seçilen kip → iki satır). Paket boyu = 16·kanal + 8 (+1 kip baytı). Banner'lar literal: test git
geçmişine bağlı DEĞİL. Sahadaki banner (SAHIP-CEVAPLARI Y7, 2026-09-30) UYUMLU kalmalı.

⚠️ BİLİNEN SINIR (AYIRT EDİLEMEZ): e2b63a5 … a280fa4 (2026-09-11 13:53–15:21) 120 bayt ama banner'ı f367f85+ (121)
ile BAYT BAYT AYNI → banner'dan ayrılamaz; bu tablo onları "uyumlu" (bugünkü karar) diye PİNLER ki biri sessizce
değişmesin. Ayrım firmware banner'ına protokol revizyonu eklenip kart yeniden yakılınca (Oturum 13 / sahip Y1-Y2);
o kartta tepkisel kapı (sistematik NACK → seans durur, B-1.1) devrededir.
"""

from __future__ import annotations

import logging
import queue
import socket as _gercek_socket
import threading
import time
import types

import pytest

SAHA_BANNER = "-> STM_READY: DDS v2.3 (7-ch KARMA uni=0x60 + HW_SYNC@PB1)"  # Y7 (saha günlüğü, 2026-09-30)
_S = " Waiting for commands..."

#: (revizyon, proje, firmware paket boyu, banner) — git geçmişinden üretildi (yukarıya bkz.).
REVIZYONLAR = [
    ("a0487c3", "bip", 88, "-> STM_READY: DDS v2.2 (5-ch + HW_SYNC@PB1)" + _S),
    *[
        (r, "bip", 88, "-> STM_READY: DDS v2.3 (5-ch SYM-BIPOLAR + HW_SYNC@PB1)" + _S)
        for r in ("356d576", "c39658b", "3f06695")
    ],
    *[
        (r, "bip", 88, f"-> STM_READY: DDS v2.3 (5-ch {k} + HW_SYNC@PB1)" + _S)
        for r in ("88b8ea1", "b347cb0", "d314bd8", "587c738", "27c0743", "2b8b661")
        for k in ("UNIPOLAR tek-bacak", "SYM-BIPOLAR")
    ],
    *[
        (r, "bip", 120, f"-> STM_READY: DDS v2.3 (7-ch {k} + HW_SYNC@PB1)" + _S)
        for r in ("07c2d4c", "34a5e6c", "55a9183", "ae7544d", "8aace69")
        for k in ("UNIPOLAR tek-bacak", "SYM-BIPOLAR")
    ],
    ("e2b63a5", "bip", 120, "-> STM_READY: DDS v2.3 (7-ch KARMA uni=0x60 + HW_SYNC@PB1)" + _S),
    ("e2b63a5", "uni", 120, "-> STM_READY: DDS v2.3 (7-ch UNIPOLAR tek-bacak uni=0x7F + HW_SYNC@PB1)" + _S),
    ("43bc8a7", "bip", 120, "-> STM_READY: DDS v2.3 (7-ch KARMA uni=0x60 + HW_SYNC@PB1)" + _S),
    ("43bc8a7", "uni", 120, "-> STM_READY: DDS v2.3 (7-ch UNIPOLAR tek-bacak uni=0x7F + HW_SYNC@PB1)" + _S),
    ("a280fa4", "bip", 120, "-> STM_READY: DDS v2.3 (7-ch KARMA uni=0x60 + HW_SYNC@PB1)" + _S),
    *[
        (r, "bip", 121, "-> STM_READY: DDS v2.3 (7-ch KARMA uni=0x60 + HW_SYNC@PB1)" + _S)
        for r in ("f367f85", "15aa121", "13d772c", "f5f417e", "814685f", "9ae63c7")
    ],
]
#: Banner'dan AYIRT EDİLEMEYEN 120 baytlık revizyonlar (bilinen sınır — yukarıya bkz.).
AYIRT_EDILEMEZ = {"e2b63a5", "43bc8a7", "a280fa4"}
_ID = [f"{r}_{p}_{b}B_{i}" for i, (r, p, b, _x) in enumerate(REVIZYONLAR)]


def _karar(banner: str):
    """Ürünün ÇAĞIRDIĞI biçim (headless_core / stm_yakma / betik: kimlik + kanal; paket boyu varsayılandan)."""
    from utils.stm32_kimlik import banner_ayristir, uyum_denetle
    from utils.stm32_transport import STM_PAKET_BOBIN_SAYISI

    return uyum_denetle(banner_ayristir(banner), STM_PAKET_BOBIN_SAYISI)


def test_ON_KOSUL_tablo_tam_ve_uygulama_7_kanal_121_bayt():
    from utils.stm32_transport import STM_PAKET_BOBIN_SAYISI, STM_PAKET_BOYU

    assert (STM_PAKET_BOBIN_SAYISI, STM_PAKET_BOYU) == (7, 121), "uygulamanın paketi değişti — tablo gözden geçirilmeli"
    assert len(REVIZYONLAR) == 37 and len({r for r, *_ in REVIZYONLAR}) == 24


@pytest.mark.parametrize(("rev", "proje", "boy", "banner"), REVIZYONLAR, ids=_ID)
def test_KRITIK_B120_her_firmware_revizyonunun_KARARI_paket_boyuyla_ESLESIR(rev, proje, boy, banner):
    from utils.stm32_kimlik import banner_ayristir

    kimlik = banner_ayristir(banner)
    assert kimlik is not None, f"{rev}: gerçek firmware banner'ı TANINMADI (bilinmiyor) — {banner!r}"
    uyumlu, sebep = _karar(banner)
    beklenen = True if rev in AYIRT_EDILEMEZ else (kimlik.kanal == 7 and boy == 121)
    assert uyumlu is beklenen, (
        f"{rev} ({proje}, {kimlik.kanal} kanal, {boy} bayt): karar {uyumlu!r}, beklenen {beklenen!r} — {sebep!r}"
    )
    if uyumlu is False:
        assert str(boy) in sebep or str(kimlik.kanal) in sebep, f"sebep çatışan sayıyı söylemiyor: {sebep!r}"
        assert "SAHA-ISLERI-REHBERI" in sebep, f"sebep eylem söylemiyor: {sebep!r}"


def test_KRITIK_Y7_SAHA_banner_i_UYUMLU():
    uyumlu, sebep = _karar(SAHA_BANNER)
    assert uyumlu is True, f"sahadaki kartın banner'ı UYUMSUZ sayıldı — sonraki yayında her START 409: {sebep!r}"


def test_KARSIT_taninmayan_GELECEK_kip_kelimesi_BILINMIYOR_kalir_REDDEDILMEZ():
    """Kip artık `+`/`)` önünde eksik olabilir (v2.2); ama tanınmayan bir kip kelimesi "kipsiz eski firmware" diye REDDE
    düşmemeli — gelecekte uyumlu bir firmware'i durdururdu. (`uni=` yok sayılıp 120 bayt hükmü verilirse KIRMIZI.)"""
    uyumlu, _s = _karar("-> STM_READY: DDS v2.4 (7-ch HIBRIT uni=0x60 + HW_SYNC@PB1)" + _S)
    assert uyumlu is None, f"tanınmayan kip kelimesi {uyumlu!r} kararı aldı (beklenen None = bilinmiyor)"


# ── B-1.21: resetsiz bağlantı — GERÇEK `_hw_sender_worker` + GERÇEK `Stm32SerialTransport` (yalnız port sahte) ──────

_OK = b"-> STM_OK: D=0,0,0,0,0,0,0 P=0,0,0,0,0,0,0 F=100,100,100,100,100,100,100 T=0,0,0,0,0,0,0 K=96\n"


class _Kart:
    """Seri port taklidi: `acilis` satırları (banner) port açılınca okunur; her yazılan pakete `yanit` döner."""

    def __init__(self, acilis: list[bytes], yanit: bytes | None):
        self.port = "COM_TEST"
        self.is_open = True
        self._satirlar: queue.Queue = queue.Queue()
        for s in acilis:
            self._satirlar.put(s)
        self._yanit = yanit
        self.yazilan = 0

    def readline(self):
        if not self.is_open:
            raise OSError("test: port kapali")
        try:
            return self._satirlar.get(timeout=0.02)
        except queue.Empty:
            return b""

    def write(self, b):
        self.yazilan += 1
        if self._yanit is not None:
            self._satirlar.put(self._yanit)
        return len(b)

    def close(self):
        self.is_open = False


def _tasima_sinifi(kart: _Kart, zaman_asimi: float):
    from utils import stm32_transport as st

    class _Tasima(st.Stm32SerialTransport):
        def __init__(self, logger, *a, **k):
            super().__init__(logger, handshake_timeout_sec=zaman_asimi)

        def _select_candidate(self):
            return st.Stm32PortCandidate(device="COM_TEST", description="test")

        def _open_serial(self, candidate):
            return kart

        def port_hala_var(self, _port):
            return True

    return _Tasima


@pytest.fixture
def isci(monkeypatch, caplog):
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
            AF_INET=_gercek_socket.AF_INET,
            SOCK_DGRAM=_gercek_socket.SOCK_DGRAM,
            SOL_SOCKET=_gercek_socket.SOL_SOCKET,
            SO_BROADCAST=_gercek_socket.SO_BROADCAST,
        ),
    )
    caplog.set_level(logging.INFO)
    calisan: list = []

    def _kos(kart: _Kart):
        monkeypatch.setattr(hcm, "Stm32SerialTransport", _tasima_sinifi(kart, 5.0))
        core = hcm.HeadlessCore.__new__(hcm.HeadlessCore)
        core.logger = logging.getLogger("test-d1103")
        core._hw_sender_stop = threading.Event()
        core._hw_send_queue = queue.Queue()
        core._stm_state_lock = threading.RLock()
        core.stm_kimlik = None
        core.stm_uyumlu = None
        core.stm_uyumsuzluk_sebebi = ""
        core.baglanti, core.olaylar = [], []
        core._set_stm_connected = lambda v: core.baglanti.append(v)
        core._publish_event = lambda tur, veri=None, **k: core.olaylar.append((tur, veri))
        t = threading.Thread(target=core._hw_sender_worker, daemon=True, name="test-HWSender-D1103")
        t.start()
        calisan.append((core, t))
        bitis = time.monotonic() + 8.0
        while time.monotonic() < bitis and core.baglanti[-1:] != [True]:
            time.sleep(0.01)
        assert core.baglanti[-1:] == [True], (
            f"aparat: el sıkışma bağlantı kurmadı {core.baglanti} (yazılan {kart.yazilan})"
        )
        time.sleep(0.3)  # bağlantı sonrası adımlar
        return core

    yield _kos
    for core, t in calisan:
        core._hw_sender_stop.set()
        t.join(3)


def _kimlik_uyarilari(caplog) -> list[str]:
    return [
        r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING and "kimligi okunamadi" in r.getMessage()
    ]


def test_KRITIK_B121_resetsiz_baglantida_kimlik_okunamadi_GUNLUK_ve_OLAYLA_gorunur(isci, caplog):
    core = isci(_Kart(acilis=[], yanit=_OK))  # banner YOK; yoklamaya STM_OK (kart zaten çalışıyordu)
    uyarilar = _kimlik_uyarilari(caplog)
    olaylar = [v for tur, v in core.olaylar if tur == "hardware.stm.uyumsuz"]
    assert uyarilar, "resetsiz bağlantıda kimliğin okunamadığı GÜNLÜKTE görünmüyor (sessiz)"
    assert olaylar and olaylar[-1].get("uyumlu") is None, (
        f"`hardware.stm.uyumsuz` (uyumlu=None) olayı yok: {core.olaylar}"
    )
    assert "resetlenmeden" in olaylar[-1].get("sebep", ""), olaylar[-1]
    assert core.stm_uyumlu is None, (
        "kimlik okunmadan karar verildi (False/True) — 'bilinmiyor' seansı ENGELLEMEZ kalmalı"
    )
    assert core.baglanti.count(True) >= 1 and False not in core.baglanti[1:], (
        "bağlantı göstergesi etkilendi (2 durumlu)"
    )


def test_KARSIT_B121_banner_gorulen_baglantida_UYARI_YOK_karar_UYUMLU(isci, caplog):
    core = isci(_Kart(acilis=[(SAHA_BANNER + _S + "\n").encode()], yanit=_OK))
    assert _kimlik_uyarilari(caplog) == [], f"banner okunan bağlantıda 'okunamadı' uyarısı: {_kimlik_uyarilari(caplog)}"
    assert core.stm_uyumlu is True, f"saha banner'ı okununca karar {core.stm_uyumlu!r}"


def _el_sikis(kart: _Kart, caplog):
    from utils import stm32_transport as st

    st_mp = pytest.MonkeyPatch()
    st_mp.setattr(st, "VCP_SETTLE_TIME_SEC", 0.0)
    st_mp.setattr(st, "HANDSHAKE_PASSIVE_LISTEN_SEC", 0.05)
    st_mp.setattr(st, "HANDSHAKE_PROBE_INTERVAL_SEC", 0.1)
    try:
        caplog.set_level(logging.INFO)
        logger = logging.getLogger("test-d1103-tasima")
        sonuc = _tasima_sinifi(kart, 1.0)(logger).open_and_handshake(stop_event=None)
    finally:
        st_mp.undo()
    return sonuc, [r.getMessage() for r in caplog.records if "Handshake zaman" in r.getMessage()]


def test_KRITIK_B121_yoklamayi_NACKleyen_karta_zaman_asimi_KABLO_degil_FIRMWARE_der(caplog):
    """Resetsiz bağlanan ESKİ firmware (88/120 bayt) yoklamayı CRC ile NACK'ler ve banner basmaz (d01t83 durum D)."""
    sonuc, uyarilar = _el_sikis(_Kart(acilis=[], yanit=b"-> STM_NACK: CRC\n"), caplog)
    assert sonuc is None and uyarilar, f"aparat: zaman aşımı oluşmadı ({sonuc}, {uyarilar})"
    assert "REDDETT" in uyarilar[-1] and "USART3" not in uyarilar[-1], (
        f"kart yanıt verip yoklamayı reddederken teşhis kablo/port yönüne yönlendiriyor: {uyarilar[-1]!r}"
    )


def test_KARSIT_B121_hic_yanit_vermeyen_portta_KABLO_PORT_teshisi_KALIR(caplog):
    sonuc, uyarilar = _el_sikis(_Kart(acilis=[], yanit=None), caplog)
    assert sonuc is None and uyarilar and "USART3" in uyarilar[-1], f"sessiz portun teşhisi değişti: {uyarilar}"
