# Author: mertaygn, cglrgrkn
"""TD1 (Oturum 13 tezgâhı, 2026-10-14) — KART ↔ UYGULAMA PAKET UYUMU: eski (120 baytlık) kart "uyumlu" görünmez; Y68 kimlik
sorgusu; uyum kararı arayüze ulaşır.

ÖLÇÜLEN KUSUR (tezgâh, gerçek STM32F429ZI + ST-Link, `DENETIM\\tz13\\kanit`):
  * Saha imajı (120 B) ile HEAD imajı (121 B) AYNI banner'ı basıyor: `DDS v2.3 (7-ch KARMA uni=0x60 + HW_SYNC@PB1)`.
  * HEAD backend saha imajlı karta bağlanınca kart HER pakete `-> STM_NACK: CRC` dönüyor, `STM_OK` 0 — ama
    `/api/health stmUyumlu:true`, Ana Ekran "Donanım" yeşil. Boşta hiç paket gitmediği için uyumsuzluk ancak seans
    başlatılınca (409 "…Açılış satırı '7-ch' demeli") görünüyordu; `hardware.stm.uyumsuz` olayının abonesi yoktu.
  * USB yeniden bağlanmasında el sıkışma paketi YOK (25 sn'de `STM_OK` 0) → kart kimliği / kabulü ölçülmüyordu.

SÖZLEŞME (TD1 a / b / c, TD7):
  * Kartın paketimize YANITI paket boyu kanıtıdır: arada `STM_OK` olmadan ≥ 3 `STM_NACK: CRC` → `stmUyumlu:false`
    (kod FW-PAKET); `STM_OK` ya da `RANGE` NACK → kabul. Tek NACK hat gürültüsüdür; kabulden sonraki NACK kararı çevirmez.
    ESKİ firmware'li kartta da çalışır (kart Y68 bilmese de).
  * Y68: kart banner'da ve kimlik sorgusu yanıtında `proto=` / `pkt=` basar → kesin karar; `pkt=` basmayan `uni=` banner'ı
    120 / 121 ayırt edemez → banner'dan karar YOK (None, seans engellenmez).
  * Her bağlantıda (yeniden bağlanma dahil) el sıkışma doğrulama yoklaması: kimlik sorgusu + en çok 3 sıfır-duty paketi.
  * Karar `hardware.stm.uyum` olayıyla canlı duruma (`stmUyum`, WS `stm_uyum`) gider; 409 / bildirim metni sade + kod.
  * ⚠️ ACİL DURDUR hiçbir yeni kapıya bağlanmaz (Ö.4-Y8): uyumsuz kartta STOP gider (mevcut kapı + aşağıda).
"""

from __future__ import annotations

import logging
import queue
import threading
import time

import pytest

#: Tezgâh kanıtındaki GERÇEK satırlar (`tz13\kanit\kok_f_backend_service.log`, `A8_*.txt`, `C6_*`).
SAHA_BANNER = "-> STM_READY: DDS v2.3 (7-ch KARMA uni=0x60 + HW_SYNC@PB1) Waiting for commands..."
CRC_NACK = "-> STM_NACK: CRC"
GERCEK_ACK = (
    "-> STM_OK: D=0,0,0,0,0,0,0 P=0,0,0,0,0,0,0 F=100,100,100,100,100,100,100 T=0,0,0,0,0,0,0 K=96 E=0,0,0,0,0,0,0"
)
RANGE_NACK = "-> STM_NACK: RANGE coil=1 field=duty value_milli=800 max_milli=500 kip=bipolar"
TELE = "-> STM_TELE: C=6,B=1.866,N=284,XN=-0.445,XP=-0.306,YN=1.130,YP=1.262,ZN=-1.359,ZP=-1.139"
#: TD1 sonrası firmware'in banner'ı (main.c biçim dizesi; proto/pkt) ve kimlik yanıtı (banner gövdesinden türer).
YENI_BANNER = "-> STM_READY: DDS v2.3 (7-ch KARMA uni=0x60 + HW_SYNC@PB1) proto=3 pkt=121 Waiting for commands..."
YENI_KIMLIK = "-> STM_ID: DDS v2.3 (7-ch KARMA uni=0x60 + HW_SYNC@PB1) proto=3 pkt=121"


def _karar(satir: str):
    from utils.stm32_kimlik import banner_ayristir, uyum_denetle
    from utils.stm32_transport import STM_PAKET_BOBIN_SAYISI

    return uyum_denetle(banner_ayristir(satir), STM_PAKET_BOBIN_SAYISI)


# ── (1) saf karar: banner tek başına 120 / 121'i ayırt edemez; Y68 beyanı kesindir ────────────────────────────────


def test_KRITIK_saha_banneri_TEK_BASINA_uyumlu_SAYILMAZ():
    """Tezgâh: bu banner 120 baytlık saha imajından. Eskiden 121 sayılıp `True` → uyumsuz kart yeşil."""
    uyumlu, sebep = _karar(SAHA_BANNER)
    assert uyumlu is None, f"paket boyu söylemeyen banner'dan kesin karar verildi: {uyumlu!r}"
    assert "120" in sebep and "121" in sebep, f"sebep ayırt edilemezliği söylemiyor: {sebep!r}"


@pytest.mark.parametrize(("pkt", "beklenen"), [(121, True), (120, False), (88, False)])
def test_Y68_banner_pkt_BEYANI_kesin_karar(pkt, beklenen):
    from utils.stm32_kimlik import banner_ayristir

    satir = YENI_BANNER.replace("pkt=121", f"pkt={pkt}")
    k = banner_ayristir(satir)
    assert (k.protokol, k.paket_boyu) == (3, pkt), k
    assert _karar(satir)[0] is beklenen


def test_Y68_kimlik_yaniti_ayrisir_ve_surum_ILK_sirada_O13():
    from utils.stm32_kimlik import firmware_surumu, kimlik_yaniti_ayristir

    k = kimlik_yaniti_ayristir(YENI_KIMLIK)
    assert k is not None and k.kaynak == "sorgu" and (k.kanal, k.maske, k.protokol, k.paket_boyu) == (7, 0x60, 3, 121)
    assert firmware_surumu(k.surum) == "2.3", "proto / pkt sürüm okumasını bozdu (O-1.3)"
    assert kimlik_yaniti_ayristir(SAHA_BANNER) is None


@pytest.mark.parametrize(
    ("satir", "beklenen"),
    [(GERCEK_ACK, "kabul"), (CRC_NACK, "crc"), (RANGE_NACK, "kabul"), (TELE, None), (SAHA_BANNER, None)],
    ids=["ack", "crc", "range", "tele", "banner"],
)
def test_paket_yaniti_siniflandirma_GERCEK_satirlar(satir, beklenen):
    from utils.stm32_kimlik import paket_yaniti_siniflandir

    assert paket_yaniti_siniflandir(satir) == beklenen


# ── (2) çekirdek: GERÇEK `_handle_stm_line` ──────────────────────────────────────────────────────────────────────


@pytest.fixture
def cekirdek():
    import headless_core as hcm

    c = hcm.HeadlessCore.__new__(hcm.HeadlessCore)
    c.logger = logging.getLogger("test-td1")
    c._stm_state_lock = threading.RLock()
    c.stm_kimlik = None
    c.stm_uyumlu = None
    c.stm_uyumsuzluk_sebebi = ""
    c.stm_is_connected = False
    c.olaylar = []
    c._set_stm_connected = lambda v: setattr(c, "stm_is_connected", v)
    c._publish_event = lambda tur, veri=None, **k: c.olaylar.append((tur, veri))
    return c


def _besle(c, *satirlar):
    for s in satirlar:
        c._handle_stm_line(s, retry_last_payload=lambda: None)


def _uyum_olaylari(c):
    return [v for t, v in c.olaylar if t == "hardware.stm.uyum"]


def test_KRITIK_eski_kart_SISTEMATIK_CRC_NACK_uyumsuz_ve_GORUNUR(cekirdek):
    _besle(cekirdek, SAHA_BANNER, CRC_NACK, CRC_NACK, CRC_NACK)
    assert cekirdek.stm_uyumlu is False, f"120 baytlık kart her paketi reddederken karar {cekirdek.stm_uyumlu!r}"
    assert cekirdek.stm_uyum_kodu == "FW-PAKET"
    son = _uyum_olaylari(cekirdek)[-1]
    assert son["uyumlu"] is False and son["kod"] == "FW-PAKET"
    assert son["mesaj"].startswith("Cihaz kartının yazılımı bu uygulama sürümüyle uyumsuz"), son
    assert "CubeIDE" not in son["mesaj"] and "python" not in son["mesaj"] and "7-ch" not in son["mesaj"]
    assert "CRC" in cekirdek.stm_uyumsuzluk_sebebi and "stm_yak" in cekirdek.stm_uyumsuzluk_sebebi  # destek ayrıntısı


@pytest.mark.parametrize("n", [1, 2])
def test_KARSIT_tek_ya_da_iki_NACK_hat_gurultusu_KARAR_DEGIL(cekirdek, n):
    _besle(cekirdek, SAHA_BANNER, *([CRC_NACK] * n))
    assert cekirdek.stm_uyumlu is not False


def test_KARSIT_kabul_goruldu_ise_sonraki_CRC_NACK_kararı_CEVIRMEZ(cekirdek):
    _besle(cekirdek, SAHA_BANNER, GERCEK_ACK, *([CRC_NACK] * 5))
    assert cekirdek.stm_uyumlu is True


def test_kabul_ARADA_NACK_sayacini_sifirlar(cekirdek):
    _besle(cekirdek, SAHA_BANNER, CRC_NACK, CRC_NACK, GERCEK_ACK)
    assert cekirdek.stm_uyumlu is True


def test_RANGE_nack_CRCyi_gecmis_paket_KABUL_kaniti(cekirdek):
    _besle(cekirdek, SAHA_BANNER, RANGE_NACK)
    assert cekirdek.stm_uyumlu is True


def test_eski_kartin_ayni_READY_pingi_RED_kanitini_SILMEZ_yeni_banner_siler(cekirdek):
    _besle(cekirdek, SAHA_BANNER, CRC_NACK, CRC_NACK, CRC_NACK, SAHA_BANNER, SAHA_BANNER)
    assert cekirdek.stm_uyumlu is False, "eski kartın 2 sn'lik READY pingi uyumsuzluk kararını sildi"
    _besle(cekirdek, YENI_BANNER)  # kart yeniden yakıldı (banner değişti) → kanıt sıfır, beyan kesin
    assert cekirdek.stm_uyumlu is True and cekirdek.stm_uyum_kodu is None


def test_red_sonrasi_KABUL_kartin_yeniden_yakildigini_soyler(cekirdek):
    _besle(cekirdek, SAHA_BANNER, CRC_NACK, CRC_NACK, CRC_NACK, GERCEK_ACK)
    assert cekirdek.stm_uyumlu is True


@pytest.mark.parametrize(("pkt", "beklenen"), [(121, True), (120, False)])
def test_Y68_kimlik_yaniti_bannersiz_da_KESIN(cekirdek, pkt, beklenen):
    _besle(cekirdek, YENI_KIMLIK.replace("pkt=121", f"pkt={pkt}"))
    assert cekirdek.stm_uyumlu is beklenen


def test_resetsiz_baglanti_kanitsiz_FW_KIMLIK_kabulle_UYUMLU(cekirdek):
    cekirdek._stm_kimligi_okunamadi()
    assert cekirdek.stm_uyumlu is None and cekirdek.stm_uyum_kodu == "FW-KIMLIK"
    assert _uyum_olaylari(cekirdek)[-1]["mesaj"].startswith("Cihaz kartı doğrulanamadı. Kartın üzerindeki SİYAH")
    _besle(cekirdek, GERCEK_ACK)
    assert cekirdek.stm_uyumlu is True and cekirdek.stm_uyum_kodu is None


def test_dogrulama_yanitsiz_ise_FW_KIMLIK(cekirdek):
    _besle(cekirdek, SAHA_BANNER)
    cekirdek._stm_dogrulama_sonucu({"kabul": False, "kimlik": None, "crc_nack": 0, "yoklama": 3})
    assert cekirdek.stm_uyumlu is None and cekirdek.stm_uyum_kodu == "FW-KIMLIK"


def test_port_kaybolunca_paket_kaniti_SIFIRLANIR(cekirdek):
    _besle(cekirdek, SAHA_BANNER, CRC_NACK, CRC_NACK, CRC_NACK)
    cekirdek._stm_kanit_sifirla("port kayboldu")
    assert cekirdek.stm_uyumlu is None and cekirdek.stm_uyum_kodu is None


# ── (3) taşıma: GERÇEK `Stm32SerialTransport.open_and_handshake`, port bayt düzeyinde sahte (firmware öykünmesi) ──


class _Kart:
    """Bayt düzeyinde kart öykünmesi: `eski` = 120 baytlık saha imajı (kimlik sorgusunu YOK sayar, 121 baytlık her pakete
    CRC NACK); `yeni` = TD1 firmware'i (STM_ID + STM_OK)."""

    def __init__(self, tur: str, banner: str):
        from utils.stm32_transport import STM_KIMLIK_SORGUSU, STM_PAKET_BOYU

        self.tur = tur
        self.port = "COM_TD1"
        self.is_open = True
        self._q: queue.Queue = queue.Queue()
        self._q.put((banner + "\r\n").encode())
        self._sorgu = STM_KIMLIK_SORGUSU
        self._boy = STM_PAKET_BOYU
        self.yazilan: list[bytes] = []

    def readline(self):
        try:
            return self._q.get(timeout=0.02)
        except queue.Empty:
            return b""

    def write(self, b):
        b = bytes(b)
        self.yazilan.append(b)
        if b == self._sorgu:
            if self.tur == "yeni":
                self._q.put((YENI_KIMLIK + "\r\n").encode())
        elif len(b) == self._boy and b[:2] == b"\xaa\x55":
            self._q.put(((CRC_NACK if self.tur == "eski" else GERCEK_ACK) + "\r\n").encode())
        return len(b)

    def close(self):
        self.is_open = False


def _tasima(kart: _Kart):
    from utils import stm32_transport as st

    class _T(st.Stm32SerialTransport):
        def _select_candidate(self):
            return st.Stm32PortCandidate(device=kart.port, description="test")

        def _open_serial(self, candidate):
            return kart

    return _T(logging.getLogger("test-td1-tasima"), handshake_timeout_sec=2.0)


@pytest.fixture
def hizli(monkeypatch):
    from utils import stm32_transport as st

    monkeypatch.setattr(st, "VCP_SETTLE_TIME_SEC", 0.0)
    monkeypatch.setattr(st, "HANDSHAKE_PASSIVE_LISTEN_SEC", 0.05)


def test_KRITIK_TD7_el_sikisma_DOGRULAMA_yoklamasi_eski_karti_YAKALAR(hizli):
    kart = _Kart("eski", SAHA_BANNER)
    satirlar: list[str] = []
    t0 = time.monotonic()
    sonuc = _tasima(kart).open_and_handshake(stop_event=None, on_line=satirlar.append)
    sure = time.monotonic() - t0
    assert sonuc is not None, "aparat: el sıkışma kurulmadı"
    ozet = getattr(sonuc, "dogrulama", None)
    assert ozet is not None, "el sıkışmadan sonra doğrulama YOKLAMASI yok (banner'la yetiniliyor)"
    assert ozet["crc_nack"] >= 3 and not ozet["kabul"], ozet
    assert sum(1 for s in satirlar if "STM_NACK: CRC" in s) >= 3, "NACK satırları çekirdeğe (on_line) iletilmedi"
    from utils.stm32_transport import STM_KIMLIK_SORGUSU

    assert kart.yazilan[0] == STM_KIMLIK_SORGUSU, "kimlik sorgusu gönderilmedi"
    assert sure < 3.0, f"doğrulama bağlantıyı {sure:.2f} sn geciktirdi"


def test_KARSIT_yeni_kart_kimlik_ve_KABUL_tek_yoklamada(hizli):
    kart = _Kart("yeni", YENI_BANNER)
    sonuc = _tasima(kart).open_and_handshake(stop_event=None, on_line=lambda s: None)
    ozet = sonuc.dogrulama
    assert ozet["kabul"] and ozet["kimlik"] and ozet["crc_nack"] == 0, ozet
    assert ozet["yoklama"] == 1, f"kabul görüldükten sonra fazladan yoklama: {ozet}"


def test_KRITIK_eski_kart_yoklamalari_SIFIR_DUTY_STOP_paketi(hizli):
    """Yoklama paketleri çıkışlara güvenli: tüm duty 0 (STOP). Ö.4-Y8: STOP yalnız artar."""
    import struct

    from utils.stm32_transport import STM_PAKET_BOBIN_SAYISI, STM_PAKET_BOYU

    kart = _Kart("eski", SAHA_BANNER)
    _tasima(kart).open_and_handshake(stop_event=None, on_line=lambda s: None)
    paketler = [b for b in kart.yazilan if len(b) == STM_PAKET_BOYU]
    assert paketler and len(paketler) <= 3, f"yoklama sayısı {len(paketler)}"
    for p in paketler:
        assert all(d == 0.0 for d in struct.unpack_from(f"<{STM_PAKET_BOBIN_SAYISI}f", p, 2)), "yoklama STOP değil"


# ── (4) uçtan uca: GERÇEK `_hw_sender_worker` + GERÇEK taşıma, yalnız port sahte ─────────────────────────────────


@pytest.fixture
def isci(monkeypatch, hizli):
    import socket as _s
    import types

    import headless_core as hcm

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
    calisan = []

    def _kos(kart: _Kart):
        from utils import stm32_transport as st

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
        core.logger = logging.getLogger("test-td1-isci")
        core._hw_sender_stop = threading.Event()
        core._hw_send_queue = queue.Queue()
        core._stm_state_lock = threading.RLock()
        core.stm_kimlik = None
        core.stm_uyumlu = None
        core.stm_uyumsuzluk_sebebi = ""
        core.baglanti, core.olaylar = [], []
        core._set_stm_connected = lambda v: core.baglanti.append(v)
        core._publish_event = lambda tur, veri=None, **k: core.olaylar.append((tur, veri))
        t = threading.Thread(target=core._hw_sender_worker, daemon=True, name="test-HWSender-TD1")
        t.start()
        calisan.append((core, t))
        bitis = time.monotonic() + 8.0
        while time.monotonic() < bitis and core.baglanti[-1:] != [True]:
            time.sleep(0.01)
        assert core.baglanti[-1:] == [True], f"aparat: bağlantı kurulmadı {core.baglanti}"
        # Bağlantı göstergesi READY satırında "bağlı" olur; doğrulama yoklaması (kimlik sorgusu + ≤ 3 sıfır-duty) ondan
        # SONRA biter → kararı en çok 3 sn bekle (tabanda karar hiç değişmez → test süre dolunca ölçer).
        bitis = time.monotonic() + 3.0
        while time.monotonic() < bitis and not any(
            t == "hardware.stm.uyum" and v.get("neden") in ("paket yanıtı", "kimlik sorgusu", "el sıkışma doğrulaması")
            for t, v in core.olaylar
        ):
            time.sleep(0.02)
        time.sleep(0.1)
        return core

    yield _kos
    for core, t in calisan:
        core._hw_sender_stop.set()
        t.join(3)


def test_KRITIK_ESKI_firmwareli_kart_baglaninca_HEMEN_uyumsuz_seans_beklenmez(isci):
    core = isci(_Kart("eski", SAHA_BANNER))
    assert core.stm_uyumlu is False, (
        f"120 baytlık saha imajlı kart bağlandı, karar {core.stm_uyumlu!r} — Donanım YEŞİL görünürdü (tezgâh A2)"
    )
    assert any(t == "hardware.stm.uyum" and v["kod"] == "FW-PAKET" for t, v in core.olaylar)


def test_KARSIT_yeni_firmwareli_kart_UYUMLU_kimlikle(isci):
    core = isci(_Kart("yeni", YENI_BANNER))
    assert core.stm_uyumlu is True and core.stm_uyum_kodu is None


# ── (5) canlı durum + metinler ───────────────────────────────────────────────────────────────────────────────────


def test_uyum_olayi_CANLI_DURUMA_ve_WS_e_gider(monkeypatch):
    from servers import api_server as api
    from servers import live_state

    yayin = []
    monkeypatch.setattr(live_state, "_ws_broadcast_sync", lambda m: yayin.append(m))
    monkeypatch.setitem(live_state._live_state, "stmUyum", None)

    class _Olay:
        event_type = "hardware.stm.uyum"
        data = {"uyumlu": False, "kod": "FW-PAKET", "sebep": "teknik", "mesaj": "operatör", "banner": SAHA_BANNER}

    api._handle_backend_event(_Olay())
    assert live_state._build_ws_snapshot()["stmUyum"] == {
        "uyumlu": False,
        "kod": "FW-PAKET",
        "mesaj": "operatör",
        "ayrinti": "teknik",
    }
    assert any(m.get("type") == "stm_uyum" and m["data"]["kod"] == "FW-PAKET" for m in yayin), yayin


def test_K1_red_metinleri_SADE_ve_KODLU():
    from servers import api_server as api

    for metin in (api.STM_RED_MESAJI,):
        assert "FW-PAKET" in metin and "7-ch" not in metin and "CubeIDE" not in metin, metin
