# Author: mertaygn, cglrgrkn
"""TD3 (tezgâh Oturum 13) — ACİL DURDUR teyidi kartın STOP'a verdiği NACK'i GÖRMELİ.

ÖLÇÜLEN KUSUR (tezgâh, 120 B saha imajlı kart + HEAD backend): kart her pakete — STOP dahil — `-> STM_NACK: CRC` döndü; E-stop yanıtı
`confirmed:true` ("Tüm bobinler durduruldu ✓"). Bugünkü teyit modeli (D1.55 · A-63): STM teyidi = STOP baytları PORTA YAZILDI; kartın
YANITI hiç okunmuyor. Kartın sonradan gelen tüm-sıfır ACK'i (D1.E04) yalnız teyitsiz E-stop'u teyitliye çevirir — ret yönü yok.
SÖZLEŞME: E-stop'un KENDİ STOP'u porta yazıldıktan sonra kartın yanıtı kısa süre (≤ 0,25 sn) beklenir —
  * tüm-sıfır `STM_OK` → kabul (teyit eskisi gibi);
  * yalnız `STM_NACK` (kabul yok) → `confirmed:false`, `stmKartYaniti:"red"`, eylem metni (gücü kes / USB'yi çıkar), canlı teyit
    `stm_red`, bildirim;
  * yanıt yok → bugünkü anlam (porta yazıldı) DEĞİŞMEZ.
⚠️ Ö.4-Y8 / D1.55 / A-63: STOP gönderimi AZALMAZ — NACK'te STOP yeniden yazılır, keep-alive STOP telafisi sürer, mandal kurulur; yanıt
beklemesi yalnız RAPORU etkiler. Aparat: GERÇEK `HeadlessCore._hw_sender_worker` + GERÇEK `Stm32SerialTransport` el sıkışması +
GERÇEK `HardwareController`; yalnız seri port bayt düzeyinde sahte (kart öykünmesi, en alt kat).
"""

from __future__ import annotations

import copy
import logging
import queue
import struct
import threading
import time
from types import SimpleNamespace

import pytest

SAHA_BANNER = "-> STM_READY: DDS v2.3 (7-ch KARMA uni=0x60 + HW_SYNC@PB1) Waiting for commands..."
YENI_BANNER = "-> STM_READY: DDS v2.3 (7-ch KARMA uni=0x60 + HW_SYNC@PB1) proto=3 pkt=121 Waiting for commands..."
YENI_KIMLIK = "-> STM_ID: DDS v2.3 (7-ch KARMA uni=0x60 + HW_SYNC@PB1) proto=3 pkt=121"
CRC_NACK = "-> STM_NACK: CRC"


class _Kart:
    """`red`: her pakete CRC NACK (tezgâhtaki 120 B kart); `kabul`: pakete duty'leriyle GERÇEK biçimli `STM_OK`; `sessiz`: yanıt yok."""

    def __init__(self, tur: str):
        from utils.stm32_transport import STM_KIMLIK_SORGUSU, STM_PAKET_BOBIN_SAYISI, STM_PAKET_BOYU

        self.tur = tur
        self.port = "COM_TD3"
        self.is_open = True
        self._q: queue.Queue = queue.Queue()
        self._q.put(((SAHA_BANNER if tur == "red" else YENI_BANNER) + "\r\n").encode())
        self._sorgu, self._boy, self._n = STM_KIMLIK_SORGUSU, STM_PAKET_BOYU, STM_PAKET_BOBIN_SAYISI
        self.paketler: list[tuple[float, tuple]] = []  # (an, duty'ler)
        self.sessiz = threading.Event()
        #: Paket yanıtının gecikmesi (sn): 121 B @115200 8N1 ≈ 10,5 ms iletim + kartın yanıt satırı. Anında yanıt veren sahte
        #: kart, yanıt beklemesi HİÇ olmayan bir hatayı (yazımdan hemen sonra karar) yakalayamazdı.
        self.gecikme = 0.015

    def readline(self):
        try:
            return self._q.get(timeout=0.02)
        except queue.Empty:
            return b""

    def _ack(self, d) -> str:
        z = ",".join("0" for _ in range(self._n))
        return (
            "-> STM_OK: D="
            + ",".join(str(int(round(x))) for x in d)
            + f" P={z} F="
            + ",".join("100" for _ in d)
            + f" T={z} K=96 E="
            + ",".join(str(int(round(x))) for x in d)
        )

    def write(self, b):
        b = bytes(b)
        if b == self._sorgu:
            if self.tur != "red":
                self._q.put((YENI_KIMLIK + "\r\n").encode())
        elif len(b) == self._boy and b[:2] == b"\xaa\x55":
            d = struct.unpack_from(f"<{self._n}f", b, 2)
            self.paketler.append((time.monotonic(), d))
            if self.tur == "red":
                self._gec((CRC_NACK + "\r\n").encode())
            elif self.tur == "kabul" or not self.sessiz.is_set():
                self._gec((self._ack(d) + "\r\n").encode())
        return len(b)

    def _gec(self, satir: bytes) -> None:
        t = threading.Timer(self.gecikme, self._q.put, args=(satir,))
        t.daemon = True
        t.start()

    def close(self):
        self.is_open = False

    def stoplar(self, sonra: float = 0.0) -> int:
        return sum(1 for t, d in self.paketler if t >= sonra and all(x == 0.0 for x in d))


@pytest.fixture
def ortam(monkeypatch):
    import socket as _s
    import types

    import headless_core as hcm
    from controllers.hardware_controller import HardwareController
    from servers import api_server as api
    from servers import live_state as ls
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
    yayinlar, bildirimler = [], []
    kaydet = lambda m, *a, **k: yayinlar.append(copy.deepcopy(m))  # noqa: E731
    monkeypatch.setattr(ls, "_ws_broadcast_sync", kaydet)
    monkeypatch.setattr(api, "_ws_broadcast_sync", kaydet)
    monkeypatch.setattr(api, "_push_notification", lambda m, s="info", *a, **k: bildirimler.append((m, s)))
    monkeypatch.setattr(api, "_estop_cloud_mirror", lambda *a, **k: None)
    monkeypatch.delenv("PEMF_ESP_ENABLED", raising=False)
    with api._session_lock:
        api._active_session.clear()
    with ls._live_state_lock:
        eski = {k: copy.deepcopy(ls._live_state.get(k)) for k in ("coils", "activeTreatment", "estopTeyit")}
    calisan = []

    def _kur(tur: str, esp_basarili: bool = False):
        monkeypatch.setattr(api, "_mqtt_publish", lambda topic, payload: esp_basarili)
        kart = _Kart(tur)

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
        core.logger = logging.getLogger("test-td3")
        core._hw_sender_stop = threading.Event()
        core._hw_send_queue = queue.Queue()
        core._stm_state_lock = threading.RLock()
        core.stm_kimlik = None
        core.stm_uyumlu = None
        core.stm_uyumsuzluk_sebebi = ""
        core.baglanti, core.olaylar = [], []
        core._set_stm_connected = lambda v: core.baglanti.append(v)
        core._publish_event = lambda tur_, veri=None, **k: core.olaylar.append((tur_, veri))
        t = threading.Thread(target=core._hw_sender_worker, daemon=True, name="test-HWSender-TD3")
        t.start()
        hc = HardwareController(core)
        calisan.append((core, t, hc))
        bitis = time.monotonic() + 8.0
        while time.monotonic() < bitis and core.baglanti[-1:] != [True]:
            time.sleep(0.01)
        assert core.baglanti[-1:] == [True], f"aparat: bağlantı kurulmadı {core.baglanti}"
        time.sleep(1.8)  # el sıkışma doğrulama yoklaması bitsin (≤ 1,5 sn)
        monkeypatch.setattr(api.state, "hardware", hc)
        monkeypatch.setattr(api.state, "core", core)
        return SimpleNamespace(api=api, ls=ls, core=core, hc=hc, kart=kart, yayinlar=yayinlar, bildirimler=bildirimler)

    yield _kur
    for core, t, hc in calisan:
        try:
            hc._keep_alive_stop.set()
        except Exception:
            pass
        core._hw_sender_stop.set()
        t.join(3)
    with ls._live_state_lock:
        for k, v in eski.items():
            ls._live_state[k] = v


def _estop(o):
    t0 = time.monotonic()
    sonuc = o.api._emergency_stop_all("manual")
    return sonuc, time.monotonic() - t0, t0


def test_KRITIK_kart_STOPu_NACKlerse_confirmed_FALSE_ve_EYLEM_metni(ortam):
    o = ortam("red")
    sonuc, sure, t0 = _estop(o)
    assert o.kart.stoplar(t0) >= 1, "aparat: E-stop'un STOP'u porta yazılmadı"
    assert sonuc["confirmed"] is False, (
        f"kart STOP'u reddetti (CRC NACK) ama E-stop teyitli döndü: {sonuc.get('status')} stmStopped={sonuc.get('stmStopped')}"
    )
    assert sonuc.get("stmKartYaniti") == "red", sonuc
    metin = sonuc.get("stmRedMesaji") or ""
    assert "reddetti" in metin and "gücünü kesin" in metin and "USB" in metin, metin
    assert o.ls._live_state["estopTeyit"]["teyitli"] is False and o.ls._live_state["estopTeyit"]["kaynak"] == "stm_red"
    assert any("reddetti" in m for m, _s in o.bildirimler), o.bildirimler
    assert sure < 1.5, f"E-stop yanıtı {sure:.2f} sn sürdü"


def test_KRITIK_STOP_gonderimi_AZALMAZ_NACKte_STOP_yeniden_yazilir(ortam):
    """Ö.4-Y8: kart reddetse de STOP yeniden gönderilir (NACK yeniden oynatması + keep-alive telafisi)."""
    o = ortam("red")
    _sonuc, _sure, t0 = _estop(o)
    time.sleep(1.2)
    assert o.kart.stoplar(t0) >= 3, f"NACK'ten sonra STOP yeniden yazılmadı: {o.kart.stoplar(t0)}"
    from utils import estop_mandali

    assert estop_mandali.durum()["aktif"] is True, "mandal kurulmadı"


def test_KARSIT_kart_STOPu_KABUL_ederse_teyitli(ortam):
    o = ortam("kabul")
    sonuc, sure, _t0 = _estop(o)
    assert sonuc["confirmed"] is True and sonuc.get("stmKartYaniti") == "kabul", sonuc
    assert sure < 1.0, f"kabulde yanıt {sure:.2f} sn sürdü"


def test_KARSIT_kart_YANITSIZsa_bugunku_anlam_DEGISMEZ(ortam):
    o = ortam("sessiz")
    o.kart.sessiz.set()
    sonuc, _sure, _t0 = _estop(o)
    assert sonuc["confirmed"] is True and sonuc.get("stmKartYaniti") is None, sonuc


def test_ESP_ACIK_kolu_STM_reddi_teyidi_yine_DUSURUR(ortam, monkeypatch):
    monkeypatch.setenv("PEMF_ESP_ENABLED", "1")
    o = ortam("red", esp_basarili=True)
    sonuc, _sure, _t0 = _estop(o)
    assert sonuc["confirmed"] is False and sonuc.get("stmKartYaniti") == "red", sonuc


def test_red_metni_backend_ve_arayuzde_AYNI():
    """Tek kaynak çifti: `stm32_kimlik.ESTOP_KART_RED_METNI` ↔ `emergencyStop.ts::EMERGENCY_STOP_KART_RED_BODY`."""
    import re
    from pathlib import Path

    from utils.stm32_kimlik import ESTOP_KART_RED_METNI

    ts = (Path(__file__).resolve().parents[1] / "apps" / "ui" / "src" / "services" / "emergencyStop.ts").read_text(
        encoding="utf-8"
    )
    m = re.search(r'EMERGENCY_STOP_KART_RED_BODY =\s*"([^"]+)"', ts)
    assert m and m.group(1) == ESTOP_KART_RED_METNI, (m and m.group(1), ESTOP_KART_RED_METNI)
