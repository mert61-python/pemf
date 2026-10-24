# Author: mertaygn, cglrgrkn
"""TD6 (tezgâh Oturum 13 "Kullanıcı geri bildirimi" K3 / K9 / K12) — operatör metinleri SADE ve EYLEM söyler; tekil bobin API'si kartın
duty reddinde `success` DÖNMEZ.

ÖLÇÜLEN (tezgâh, çift yönlü bobin 1'e %80):
  * K3 — tekil bobin: API `success`, bobin başlamıyor, sebep görünmüyor. Bildirim metni jargonluydu: "%80 duty iki yönlü (bipolar)
    sürüşte UYGULANAMAZ — kart komutu REDDETTİ (üst sınır %50)".
  * K12 — mandal bandı her nedende aynı eylemi söylüyordu ("Bobinlerin durduğunu cihazda kontrol edin… Sıfırla"); kart reddinde neyin
    reddedildiği ve ne yapılacağı yoktu.
  * K9 — petri plaka reddi: "ızgarayı doğrulayan kuyucuk adayı 3 — beklenen ≥2; ince hizalama başarısız" (jargon + çelişkili sayı).
SÖZLEŞME: duty reddi = "Bobin 1 çift yönlü kipte en fazla %50 çalışabilir; %80 kabul edilmedi. Duty'yi %50 veya altına indirip yeniden
başlatın" (+ Y74 seçeneği / "Sıfırla" adımı). Tekil bobin START'ı kartın yanıtını ≤ 0,5 sn bekler: bu bobinin duty reddinde
`status:"error"` + `mesaj`, koşu kaydı AÇILMAZ; kabul / yanıtsız kartta davranış DEĞİŞMEZ; STOP BEKLEMEZ (Ö.4-Y8). Duty tavanı
firmware'de KALIR (backend sınır EKLEMEZ, Ö.4-Y9). Aparat: GERÇEK HeadlessCore gönderici + el sıkışma + HardwareController; kart bayt
düzeyinde sahte, NACK gerekçesi ve ACK satırı firmware hizalı simülatörden (`tools.stm32_simulator`) — duty kuralı testte KOPYALANMAZ.
"""

from __future__ import annotations

import asyncio
import copy
import logging
import queue
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

KOK = Path(__file__).resolve().parents[1]
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

import tools.stm32_simulator as sim  # noqa: E402

YENI_BANNER = "-> STM_READY: DDS v2.3 (7-ch KARMA uni=0x60 + HW_SYNC@PB1) proto=3 pkt=121 Waiting for commands..."
YENI_KIMLIK = "-> STM_ID: DDS v2.3 (7-ch KARMA uni=0x60 + HW_SYNC@PB1) proto=3 pkt=121"
K3_BOBIN1 = "Bobin 1 çift yönlü kipte en fazla %50 çalışabilir; %80 kabul edilmedi. Duty'yi %50 veya altına indirip yeniden başlatın"
JARGON = ("bipolar", "unipolar)", "UYGULANAMAZ", "REDDETTİ", "milli", "kip=", "field=")


def _nack(bobin: int, istenen_milli: int, tavan_milli: int, kip: str) -> str:
    return f"-> STM_NACK: RANGE coil={bobin} field=duty value_milli={istenen_milli} max_milli={tavan_milli} kip={kip}"


# ── 1) K3 metni ──────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_KRITIK_K3_duty_reddi_metni_SADE_ve_EYLEM():
    from servers import live_state as ls

    m = ls.stm_duty_reddi_metni(_nack(1, 800, 500, "bipolar"))
    assert m.startswith(K3_BOBIN1), m
    assert "Sürüş Kipi" in m and "Unipolar" in m, f"Y74 seçeneği (Unipolar) düştü: {m}"
    assert not any(j in m for j in JARGON), f"jargon: {m}"
    u = ls.stm_duty_reddi_metni(_nack(6, 1200, 1000, "unipolar"))
    assert (
        u
        == "Bobin 6 tek yönlü kipte en fazla %100 çalışabilir; %120 kabul edilmedi. Duty'yi %100 veya altına indirip yeniden başlatın."
    ), u
    s = ls.stm_duty_reddi_metni(_nack(1, 800, 500, "bipolar"), "seans DURDURULDU", sifirla=True)
    assert s.startswith("Bobin 1 çift yönlü kipte en fazla %50 çalışabilir; %80 kabul edilmedi; seans DURDURULDU. "), s
    assert "sonra 'Sıfırla'ya basın" in s and not any(j in s for j in JARGON), s
    assert ls.stm_duty_reddi_metni("-> STM_NACK: CRC") == ""


# ── 2) K3 tekil bobin API'si — gerçek çekirdek + simülatör hizalı kart ────────────────────────────────────────────────
def _ack_satiri(sonuc) -> str:
    duty, phase, freq, duration, _ref, kip = sonuc
    n = sim.NUM_COILS
    etkin = (sim.UNIPOLAR_YETENEK_MASKESI | int(kip)) & ((1 << n) - 1)
    return (
        "-> STM_OK: "
        f"D={','.join(str(sim.firmware_ack_yuzdesi(duty[i])) for i in range(n))} "
        f"P={','.join(str(int(phase[i])) for i in range(n))} "
        f"F={','.join(str(int(freq[i])) for i in range(n))} "
        f"T={','.join(str(duration[i]) for i in range(n))} K={etkin} "
        f"E={','.join(str(sim.firmware_etkin_binde(duty[i], freq[i], (etkin >> i) & 1)) for i in range(n))}"
    )


class _Kart:
    """`sim`: paketi simülatörün firmware hizalı çözümleyicisiyle doğrular — red → `STM_NACK: <gerekçe>`, kabul → `STM_OK`;
    `sessiz`: el sıkışmadan sonra paketlere yanıt yok."""

    def __init__(self, tur: str):
        from utils.stm32_transport import STM_KIMLIK_SORGUSU, STM_PAKET_BOYU

        self.tur = tur
        self.port = "COM_TD6"
        self.is_open = True
        self._q: queue.Queue = queue.Queue()
        self._q.put((YENI_BANNER + "\r\n").encode())
        self._sorgu, self._boy = STM_KIMLIK_SORGUSU, STM_PAKET_BOYU
        self.sessiz = threading.Event()
        self.gecikme = 0.015  # 121 B @115200 ≈ 10,5 ms + kartın satırı (anında yanıt bekleme hatasını gizlerdi)

    def readline(self):
        try:
            return self._q.get(timeout=0.02)
        except queue.Empty:
            return b""

    def write(self, b):
        b = bytes(b)
        if b == self._sorgu:
            self._q.put((YENI_KIMLIK + "\r\n").encode())
        elif len(b) == self._boy and b[:2] == b"\xaa\x55":
            if self.sessiz.is_set():
                return len(b)
            sonuc, sebep = sim.decode_packet(b)
            satir = f"-> STM_NACK: {sebep}" if sonuc is None else _ack_satiri(sonuc)
            t = threading.Timer(self.gecikme, self._q.put, args=((satir + "\r\n").encode(),))
            t.daemon = True
            t.start()
        return len(b)

    def close(self):
        self.is_open = False


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
    monkeypatch.setattr(ls, "_ws_broadcast_sync", lambda *a, **k: None)
    monkeypatch.setattr(api, "_ws_broadcast_sync", lambda *a, **k: None)
    monkeypatch.setattr(api, "_push_notification", lambda *a, **k: None)
    kosular = []
    monkeypatch.setattr(api, "_begin_coil_run", lambda *a, **k: kosular.append(("basla", a)))
    monkeypatch.setattr(api, "_finish_coil_run", lambda *a, **k: kosular.append(("bitir", a)))
    with ls._live_state_lock:
        eski = {k: copy.deepcopy(ls._live_state.get(k)) for k in ("coils", "stm")}
    calisan = []

    def _kur(tur: str):
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
        core.logger = logging.getLogger("test-td6")
        core._hw_sender_stop = threading.Event()
        core._hw_send_queue = queue.Queue()
        core._stm_state_lock = threading.RLock()
        core.stm_kimlik = None
        core.stm_uyumlu = None
        core.stm_uyumsuzluk_sebebi = ""
        core.baglanti, core.olaylar = [], []
        core._set_stm_connected = lambda v: core.baglanti.append(v)
        core._publish_event = lambda tur_, veri=None, **k: core.olaylar.append((tur_, veri))
        t = threading.Thread(target=core._hw_sender_worker, daemon=True, name="test-HWSender-TD6")
        core._hw_sender_thread = (
            t  # üretimde __init__ kurar; START kapısı göndericinin canlılığını buradan okur (D1.55)
        )
        t.start()
        hc = HardwareController(core)
        calisan.append((core, t, hc))
        bitis = time.monotonic() + 8.0
        while time.monotonic() < bitis and core.baglanti[-1:] != [True]:
            time.sleep(0.01)
        assert core.baglanti[-1:] == [True], f"aparat: bağlantı kurulmadı {core.baglanti}"
        time.sleep(1.8)  # el sıkışma doğrulama yoklaması bitsin (≤ 1,5 sn)
        if tur == "sessiz":
            kart.sessiz.set()
        with ls._live_state_lock:
            ls._live_state["stm"] = "online"  # START kapısı arayüzün gördüğü alanı okur (`stm_surus_hazir`)
        monkeypatch.setattr(api.state, "hardware", hc)
        return SimpleNamespace(api=api, ls=ls, core=core, hc=hc, kart=kart, kosular=kosular)

    yield _kur
    for core, t, hc in calisan:
        try:
            hc.stop_all_coils()
        except Exception:
            pass
        try:
            hc._keep_alive_stop.set()
        except Exception:
            pass
        core._hw_sender_stop.set()
        t.join(3)
    with ls._live_state_lock:
        for k, v in eski.items():
            ls._live_state[k] = v


def _kontrol(o, bobin: int, duty: float, start: bool = True):
    p = o.api.CoilControlPayload(freq=100.0, duty=duty, phase=0.0, duration=60, start=start)
    t0 = time.monotonic()
    yanit = asyncio.run(o.api.control_single_coil(bobin, p))
    return yanit, time.monotonic() - t0


#: Erken dönüşü duvar saatinden bağımsız kanıtlamak için bekleme BİLEREK uzun: tam bekleseydi ≥ 5 sn sürerdi (yük altında da).
_UZUN_BEKLEME_S = 5.0


def test_KRITIK_K3_tekil_bobin_kart_REDDEDERSE_success_DONMEZ_ve_kosu_ACILMAZ(ortam, monkeypatch):
    o = ortam("sim")
    monkeypatch.setattr(o.api, "_STM_BASLATMA_YANIT_BEKLEME_S", _UZUN_BEKLEME_S)
    yanit, sure = _kontrol(o, 1, 80.0)
    assert yanit["status"] == "error", f"kart duty'yi reddetti ama API {yanit!r} döndü (tezgâh K3)"
    assert yanit.get("kartReddetti") is True and str(yanit.get("mesaj", "")).startswith(K3_BOBIN1), yanit
    assert not [k for k in o.kosular if k[0] == "basla"], f"reddedilen START koşu kaydı açtı: {o.kosular}"
    assert sure < _UZUN_BEKLEME_S * 0.8, f"kartın reddi görülünce bekleme bitmeliydi ({sure:.2f} sn)"


def test_KARSIT_K3_kabul_edilen_START_success_ve_ERKEN_doner(ortam, monkeypatch):
    o = ortam("sim")
    monkeypatch.setattr(o.api, "_STM_BASLATMA_YANIT_BEKLEME_S", _UZUN_BEKLEME_S)
    yanit, sure = _kontrol(o, 1, 40.0)
    assert yanit["status"] == "success" and "kartReddetti" not in yanit, yanit
    assert [k for k in o.kosular if k[0] == "basla"], "kabul edilen START koşu kaydı açmadı"
    assert sure < _UZUN_BEKLEME_S * 0.8, f"kartın kabulü görülünce bekleme bitmeliydi ({sure:.2f} sn)"


def test_KARSIT_K3_kart_SESSIZ_ise_bugunku_anlam_DEGISMEZ(ortam, monkeypatch):
    o = ortam("sessiz")
    monkeypatch.setattr(o.api, "_STM_BASLATMA_YANIT_BEKLEME_S", 0.3)
    yanit, sure = _kontrol(o, 1, 80.0)
    assert yanit["status"] == "success" and "kartReddetti" not in yanit, yanit
    assert sure >= 0.3, f"yanıtsız kartta yanıt beklenmedi ({sure:.2f} sn)"


def test_KRITIK_K3_STOP_kart_yanitini_BEKLEMEZ(ortam, monkeypatch):
    o = ortam("sessiz")
    monkeypatch.setattr(o.api, "_STM_BASLATMA_YANIT_BEKLEME_S", _UZUN_BEKLEME_S)
    yanit, sure = _kontrol(o, 1, 0.0, start=False)
    assert yanit["status"] == "success", yanit
    assert sure < _UZUN_BEKLEME_S * 0.4, f"STOP kartın yanıtını bekledi ({sure:.2f} sn) — Ö.4-Y8"


def test_KRITIK_K3_baska_bobinin_reddi_bu_baslatmayi_REDDETMEZ(monkeypatch):
    """İçerik eşlemesi: yalnız BU bobinin duty reddi ret sayılır (önceki canlı tutma paketinin yanıtı karışmasın)."""
    from servers import api_server as api

    satirlar = [("nack", _nack(2, 800, 500, "bipolar")), ("nack", "-> STM_NACK: CRC")]
    core = SimpleNamespace(stm_yanitlari_sonra=lambda taban: list(satirlar), _parse_stm_ok=lambda s: [])
    monkeypatch.setattr(api.state, "hardware", SimpleNamespace(core=core))
    monkeypatch.setattr(api, "_STM_BASLATMA_YANIT_BEKLEME_S", 0.05)
    assert asyncio.run(api._stm_baslatma_kart_yaniti(1, 80.0, 0)) == ""
    satirlar.append(("nack", _nack(1, 800, 500, "bipolar")))
    assert asyncio.run(api._stm_baslatma_kart_yaniti(1, 80.0, 0)).startswith(K3_BOBIN1)


# ── 3) K12 mandal bandı eylemi ─────────────────────────────────────────────────────────────────────────────────────────
def test_KRITIK_K12_mandal_eylemi_YALNIZ_ayni_nedenli_mandala_gider():
    from utils import estop_mandali

    try:
        estop_mandali.eylem_birak("stm_komut_reddi", "EYLEM-K3")
        estop_mandali.mandalla("manual")
        assert estop_mandali.durum()["eylem"] == "", "başka nedenli mandal bırakılan eylemi aldı"
        estop_mandali.mandalla("stm_komut_reddi")
        assert estop_mandali.durum()["eylem"] == "EYLEM-K3"
        estop_mandali.sifirla("test")
        assert estop_mandali.durum()["eylem"] == ""
        estop_mandali.mandalla("stm_komut_reddi")
        assert estop_mandali.durum()["eylem"] == "", "eylem bir kez kullanılır (sonraki mandal bayat metni taşımaz)"
    finally:
        estop_mandali.sifirla("test")


def test_KRITIK_K12_seansta_duty_reddi_mandal_bandina_K3_metnini_tasir(monkeypatch, tmp_path):
    import event_bus as eb
    import headless_core as hcm
    from database.treatment_history_db import TreatmentHistoryDB
    from servers import api_server as api
    from servers import live_state as ls
    from utils import estop_mandali

    class _Donanim:
        def stop_all_coils(self):
            return True

        def on_disconnect(self):
            return True

    db = TreatmentHistoryDB(tmp_path)
    monkeypatch.setattr(api, "_get_treatment_db", lambda: db)
    monkeypatch.setattr(api, "_ws_broadcast_sync", lambda *a, **k: None)
    monkeypatch.setattr(api, "_push_notification", lambda *a, **k: None)
    monkeypatch.setattr(api, "_estop_cloud_mirror", lambda *a, **k: None)
    monkeypatch.setattr(api.state, "hardware", _Donanim())
    yeni_bus = eb.EventBus()
    monkeypatch.setattr(eb, "_event_bus_instance", yeni_bus)
    monkeypatch.setattr(api, "_event_bus_registered", False)
    ls.stm_komut_kabulu_bildir()
    with api._stm_nack_lock:
        api._stm_nack_son.clear()
    with api._session_lock:
        eski_seans = dict(api._active_session)
    with ls._live_state_lock:
        eski_canli = copy.deepcopy(ls._live_state)
    assert not estop_mandali.mandalli_mi(), "aparat: mandal KURULU başladı"
    core = hcm.HeadlessCore.__new__(hcm.HeadlessCore)
    core.logger = logging.getLogger("test-td6-k12")
    core.event_bus = yeni_bus
    try:
        api._register_event_bus_handlers()
        sid = db.start_session(treatment_mode="Manuel", target_condition="test", patient_name="Pamuk")
        with api._session_lock:
            api._active_session.clear()
            api._active_session.update(
                {
                    "is_active": True,
                    "session_id": "td6",
                    "coil_ids": [1, 2],
                    "db_session_id": sid,
                    "started_epoch": time.time() - 60,
                    "start_mono": time.monotonic() - 60,
                }
            )
        core._handle_stm_line(_nack(1, 800, 500, "bipolar"), None)
        bitis = time.monotonic() + 15
        while time.monotonic() < bitis and not estop_mandali.mandalli_mi():
            time.sleep(0.02)
        for t in [t for t in threading.enumerate() if t.name.startswith("estop-stm")]:
            t.join(15)
        d = estop_mandali.durum()
        assert d["aktif"] and d["neden"] == "stm_komut_reddi", d
        assert d["eylem"].startswith("Bobin 1 çift yönlü kipte en fazla %50 çalışabilir; %80 kabul edilmedi"), d
        assert "sonra 'Sıfırla'ya basın" in d["eylem"], d
    finally:
        for t in [t for t in threading.enumerate() if t.name.startswith("estop-stm")]:
            t.join(15)
        estop_mandali.sifirla("test")
        ls.stm_komut_kabulu_bildir()
        with api._stm_nack_lock:
            api._stm_nack_son.clear()
        with api._session_lock:
            api._active_session.clear()
            api._active_session.update(eski_seans)
        with ls._live_state_lock:
            ls._live_state.clear()
            ls._live_state.update(eski_canli)
        yeni_bus.shutdown()


# ── 4) K9 petri plaka reddi ────────────────────────────────────────────────────────────────────────────────────────────
def test_KRITIK_K9_plaka_reddi_SADE_sayilar_OLCUMDE():
    from ai_hub.inference_petri_dish import plausibility as pl

    ok, m = pl.evaluate_plate({"n_inliers": 3, "ecc_ok": False}, guard=True)
    assert ok is False and m["n_inliers"] == 3 and m["ecc_ok"] is False, f"destek ayrıntısı (sayılar) kayboldu: {m}"
    metin = m["message"]
    assert metin.startswith(
        "24 kuyucuklu plaka ızgarası oturmadı. Plakayı kareyi dolduracak kadar yakından, tepeden ve dik çekin."
    ), metin
    for j in ("kuyucuk adayı", "ince hizalama", "beklenen", "≥", "3"):
        assert j not in metin, f"K9: kullanıcı metninde {j!r}: {metin}"
    # T3 · Y193: tekil kap kipi arayüzden kalktı → metin o kipe YÖNLENDİRMEZ (yapılamayan eylem söylenmez)
    assert (
        "Tekil petri kapları" not in metin and "ilgili modüle" in metin and "Gelişmiş (araştırma) ayarları" in metin
    ), metin
