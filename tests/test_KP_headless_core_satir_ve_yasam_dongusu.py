# -*- coding: utf-8 -*-
"""KP-1 · apps/backend/headless_core.py · sözleşmeler: STOP paketi tanıma (`_tum_duty_sifir_mi` başlık), yazım izi (`_hw_yazimi_kaydet`
çözülemeyen paket / kurulmamış iz), STOP teyidi beklemesi (ölü gönderici), HWSender canlandırma (canlı / kilit içi yarış), satır işleme
(`_handle_stm_line`: boş satır, kimlik yanıtı, sınıflanamayan NACK, STM_SENS işleyici hatası, ACK alan uyuşmazlığı / taşma, yanıt izi
yazılamaması, STM_ERR), telemetri savunma dönüşümleri, `stm_banner_bekle` süre dolumu, olay yayını hatası, `start_headless_services`,
Y43 arka plan DB yeniden açması (başarı yolu), `quit` kapanış sırası.

Çekirdek `HeadlessCore.__new__` + `__init__`'in iş parçacığı / DB DIŞINDAKİ alanlarıyla kurulur (gerçek `_set_stm_connected` → gerçek
`SimpleSignal` → gerçek `_on_stm_connected_slot` → gerçek `_publish_event`). Sahte EN ALT katta: olay veriyolu (`publish` kaydı), Y43 DB
kurucuları (`acilista_acilamayani_yeniden_ac` — gerçeği SQLCipher + kasa açar), hizmet sınıfları (gerçekleri 1883 / 5051 / 5353 dinler),
iş parçacığı nesnesi (kapanış join süresi). Gerçek seri port / ağ / dinleyici YOK.

Savunma dönüşümleri (`int(...)` / `float(...)` → ValueError dalları): ürünün desenleri yalnız ASCII rakam yakaladığı için gerçek satırla
düşemez (Python 3.10.2'de basamak sınırı yok). Sözleşme, ürünün KENDİ deseninden türetilip yalnız o grubu genişleten desen ÖRNEK
özniteliğine konarak sınanır (sınıf özniteliği değişmez).
"""

from __future__ import annotations

import collections
import logging
import queue
import re
import threading
import time
import types
from pathlib import Path

import headless_core as hcm
import pytest
from event_bus import EventPriority
from utils.simple_signal import SimpleSignal
from utils.stm32_transport import build_stm32_zero_duty_packet

GUNLUK = "HeadlessCore"
YENI_BANNER = "-> STM_READY: DDS v2.3 (7-ch KARMA uni=0x60 + HW_SYNC@PB1) proto=3 pkt=121 Waiting for commands..."
YENI_KIMLIK = "-> STM_ID: DDS v2.3 (7-ch KARMA uni=0x60 + HW_SYNC@PB1) proto=3 pkt=121"
SIFIR_ACK = "-> STM_OK: D=0,0,0,0,0,0,0 P=0,0,0,0,0,0,0 F=0,0,0,0,0,0,0 T=0,0,0,0,0,0,0"


class _Veriyolu:
    """Olay veriyolu (EN ALT kat): `publish(event_type, data, priority, source)` kaydı; `patlat` → yayın istisnası."""

    def __init__(self, patlat: bool = False):
        self.kayit: list[tuple] = []
        self.patlat = patlat
        self._kilit = threading.Lock()

    def publish(self, event_type, data, priority=EventPriority.NORMAL, source=None, correlation_id=None):
        if self.patlat:
            raise RuntimeError("test: olay veriyolu kapandi")
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
    """`__init__`'in iş parçacığı ve DB açılışı DIŞINDAKİ alanları (aynı değerlerle) — sinyal / slot / yayın GERÇEK."""
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


@pytest.fixture
def bus():
    return _Veriyolu()


@pytest.fixture
def c(bus, tmp_path):
    return _cekirdek(bus, tmp_path)


def _mesajlar(caplog, seviye=None) -> list[str]:
    return [r.getMessage() for r in caplog.records if seviye is None or r.levelno == seviye]


# ───────────────────────────── STOP paketi tanıma ve yazım izi ─────────────────────────────


def test_STOP_tanima_BASLIK_AA55_degilse_tum_sifir_govde_STOP_SAYILMAZ():
    """Boyu tam, gövdesi tüm-sıfır ama başlığı 0xAA 0x55 OLMAYAN paket → False ("STOP yazıldı" iddiası kurulmaz); aynı gövde doğru
    başlıkla → True."""
    stop = build_stm32_zero_duty_packet()
    assert hcm._tum_duty_sifir_mi(stop) is True
    assert hcm._tum_duty_sifir_mi(b"\x55\xaa" + stop[2:]) is False
    assert hcm._tum_duty_sifir_mi(b"\xaa\x00" + stop[2:]) is False


class _BoyuYalanPaket(bytes):
    """Boyunu olduğundan BÜYÜK bildiren paket nesnesi: başlık doğru, gövde çözülürken `struct.error`."""

    def __len__(self):
        return 10_000


def test_yazim_izi_COZULEMEYEN_paket_YAZIM_sayilir_ama_STOP_SAYILMAZ(c):
    """Porta yazılan paket çözülürken istisna verirse → yazım sayacı artar, STOP yazımı / sırası / yanıt tabanı AÇILMAZ (E-stop teyidi
    çözülemeyen paketten kurulmaz); ardından gerçek STOP → STOP yazımı ve sırası kaydedilir."""
    c._hw_yazimi_kaydet(_BoyuYalanPaket(b"\xaa\x55\x00\x00"), sira=5)
    assert (c._hw_yazim_sayaci, c._hw_son_stop_yazimi, c._hw_son_stop_sirasi) == (1, 0, 0)
    assert list(c._hw_stop_yanit_tabanlari) == []
    c._hw_yazimi_kaydet(build_stm32_zero_duty_packet(), sira=6)
    assert (c._hw_yazim_sayaci, c._hw_son_stop_yazimi, c._hw_son_stop_sirasi) == (2, 2, 6)
    assert list(c._hw_stop_yanit_tabanlari) == [(6, 0)]


def test_yazim_izi_KURULMAMIS_cekirdekte_kayit_SESSIZCE_atlanir():
    """Yazım izi koşulu kurulmamış (`__new__` ile kurulmuş, `_hw_izlemeyi_kur` çağrılmamış) çekirdek → `_hw_yazimi_kaydet` istisnasız döner
    ve sayaç ÖZNİTELİĞİ YARATMAZ."""
    c = hcm.HeadlessCore.__new__(hcm.HeadlessCore)
    assert c._hw_yazimi_kaydet(build_stm32_zero_duty_packet(), sira=1) is None
    assert not hasattr(c, "_hw_yazim_sayaci") and not hasattr(c, "_hw_son_stop_yazimi")


def test_gonderici_OLUYKEN_STOP_teyidi_BEKLEMEDEN_false(c):
    """HWSender ölü (bağlantı açık olsa bile) → `hw_stop_yazildi_bekle` / `hw_stop_sirasi_yazildi_bekle` üst sınırı (5 sn) BEKLEMEDEN
    False (A-63: yazılamayacağı belli STOP için yedek adımlar gecikmez); gönderici canlıyken STOP yazılabilir."""
    c._seri_baglanti = hcm.SeriBaglantiDurumu()
    c._seri_baglanti.yerlestir(types.SimpleNamespace(is_open=True))
    c._hw_sender_thread = threading.Thread(target=lambda: None)  # hiç başlamadı → ölü
    t0 = time.monotonic()
    assert c.hw_stop_yazildi_bekle(c.hw_yazim_isareti(), 5.0) is False
    assert c.hw_stop_sirasi_yazildi_bekle(1, 5.0) is False
    assert time.monotonic() - t0 < 1.0, "ölü göndericide STOP teyidi süre sınırına dek bekledi"
    canli = threading.Event()
    t = threading.Thread(target=canli.wait, daemon=True)
    t.start()
    try:
        c._hw_sender_thread = t
        assert c._hw_stop_yazilabilir_mi() is True
    finally:
        canli.set()
        t.join(timeout=2)


class _SiraliCanlilik:
    """İş parçacığı nesnesi: `is_alive()` sırayla verilen değerleri döndürür (sonuncusu tekrarlanır)."""

    def __init__(self, degerler):
        self._degerler = list(degerler)

    def is_alive(self):
        return self._degerler.pop(0) if len(self._degerler) > 1 else self._degerler[0]


def test_canlandirma_gonderici_CANLIYSA_ya_da_KILIT_icinde_canli_bulunursa_YENI_is_parcacigi_baslatmaz(c):
    """Gönderici canlı → `hw_gondericiyi_canlandir` True, yeni iş parçacığı YOK; kilit dışında ölü görünüp kilit içinde canlı bulunursa
    (başka çağıran canlandırdı) → True, yeni iş parçacığı YOK ve son canlandırma anı DEĞİŞMEZ."""
    once = set(threading.enumerate())
    c._hw_sender_thread = _SiraliCanlilik([True])
    assert c.hw_gondericiyi_canlandir() is True
    yaris = _SiraliCanlilik([False, True])
    c._hw_sender_thread = yaris
    assert c.hw_gondericiyi_canlandir() is True
    assert c._hw_sender_thread is yaris and c._hw_son_canlandirma == 0.0
    assert [t.name for t in threading.enumerate() if t not in once and t.name == "HWSender"] == []


# ───────────────────────────── satır işleme ─────────────────────────────


def test_BOS_satir_hicbir_olay_ve_gunluk_URETMEZ(c, bus, caplog):
    """Boş satır → `_handle_stm_line` hiçbir olay yayınlamaz, günlüğe yazmaz, bağlantı durumunu değiştirmez."""
    with caplog.at_level(logging.DEBUG, logger=GUNLUK):
        c._handle_stm_line("", retry_last_payload=lambda: pytest.fail("bos satir yeniden oynatma istedi"))
    assert bus.kayit == [] and _mesajlar(caplog) == [] and c.stm_is_connected is False


def test_kimlik_yaniti_AYRISTIRILAMAZSA_uyari_ve_kanit_DEGISMEZ(c, bus, caplog):
    """`STM_ID:` satırı ayrıştırılamazsa → WARNING "kimlik yanıtı ayrıştırılamadı: <satır>", kimlik sorgusu kanıtı boş kalır, uyum olayı
    YOK; geçerli kimlik yanıtı → kanıt yerleşir ve uyum olayı yayınlanır."""
    with caplog.at_level(logging.WARNING, logger=GUNLUK):
        c._handle_stm_line("-> STM_ID: bozuk yanit")
    assert "[STM32] kimlik yanıtı ayrıştırılamadı: -> STM_ID: bozuk yanit" in _mesajlar(caplog, logging.WARNING)
    assert c._stm_kanit()["sorgu"] is None and bus.hepsi("hardware.stm.uyum") == []
    c._handle_stm_line(YENI_KIMLIK)
    assert c._stm_kanit()["sorgu"].kaynak == "sorgu" and c.stm_uyumlu is True
    assert bus.hepsi("hardware.stm.uyum")[-1][1]["uyumlu"] is True


def test_SINIFLANAMAYAN_NACK_paket_kanitini_DEGISTIRMEZ_ama_NACK_olarak_islenir(c, bus):
    """CRC / RANGE içermeyen `STM_NACK` → paket boyu kanıtı (CRC sayacı) DEĞİŞMEZ; satır yine NACK: yanıt izi "nack", HIGH NACK olayı,
    bir yeniden oynatma isteği. CRC NACK ise sayaç 1 olur."""
    istek = []
    c._handle_stm_line("-> STM_NACK: LEN", retry_last_payload=lambda: istek.append(1))
    assert c._stm_kanit()["crc"] == 0 and c._stm_kanit()["kanit"] is None
    assert [t for _n, t, _s in c._stm_yanitlar] == ["nack"] and istek == [1]
    assert bus.hepsi("hardware.stm.nack") == [
        ("hardware.stm.nack", {"message": "-> STM_NACK: LEN"}, EventPriority.HIGH, "headless_core")
    ]
    c._handle_stm_line("-> STM_NACK: CRC", retry_last_payload=lambda: istek.append(2))
    assert c._stm_kanit()["crc"] == 1


def test_STM_SENS_isleyicisi_PATLARSA_satir_YUTULUR_hata_ayiklama_izi(c, bus, caplog):
    """STM_SENS işleyicisi istisna verirse (desen / işleyici uyumsuzluğu) → satır yutulur: DEBUG "STM_SENS islenemedi" (istisna izli),
    hiçbir olay, bağlantı durumu değişmez. Gerçek desenle aynı satır alan bandı olayı üretir."""
    satir = "-> STM_SENS: C=6 I2C2 sicaklik=0x00 alan=0x18 kazanc=7 res=0 ayar=DOGRULANAMADI"
    c._SENS_ALAN_DESENI = re.compile(r"STM_SENS:\s*C=(?P<c>[0-9]+)")  # `ayar` grubu YOK → m.group("ayar") IndexError
    with caplog.at_level(logging.DEBUG, logger=GUNLUK):
        c._handle_stm_line(satir)
    kayit = [r for r in caplog.records if r.getMessage() == "[STM32] STM_SENS islenemedi"]
    assert kayit and kayit[0].levelno == logging.DEBUG and kayit[0].exc_info[0] is IndexError
    assert bus.kayit == [] and c.stm_is_connected is False
    del c._SENS_ALAN_DESENI
    c._handle_stm_line(satir)
    assert bus.hepsi("hardware.stm.telemetry") == [
        ("hardware.stm.telemetry", {"coil_id": 6, "alan_dogrulanamadi": True}, EventPriority.NORMAL, "headless_core")
    ]


def test_ACK_alan_uzunluklari_UYUSMAZSA_satir_REDDEDILIR_bobin_guncellemesi_YOK(c, bus, caplog):
    """`STM_OK` D/P/F/T alan sayıları farklı → `_parse_stm_ok` [] + "headless_core" WARNING (uzunluklar); satır yolunda hiçbir
    `coil_update` / `stop_onayi` yayınlanmaz, yanıt izi "ok" (tüm-sıfır değil)."""
    satir = "-> STM_OK: D=10,0,0 P=0,0 F=100,100,100 T=0,0,0"
    with caplog.at_level(logging.WARNING, logger="headless_core"):
        assert c._parse_stm_ok(satir) == []
    assert "STM parse: alan uzunlukları uyuşmuyor (3, 2, 3, 3) → satır reddedildi." in _mesajlar(
        caplog, logging.WARNING
    )
    c._handle_stm_line(satir)
    assert bus.hepsi("hardware.stm.coil_update") == [] and bus.hepsi("hardware.stm.stop_onayi") == []
    assert [t for _n, t, _s in c._stm_yanitlar] == ["ok"]


def test_ACK_sure_alani_TASARSA_PARSE_HATASI_olayi_YUKSEK_oncelik_ham_satirla(c, bus, caplog):
    """`T=` alanı float'ta sonsuza taşan sayı → `int(inf)` OverflowError → ERROR "STM_OK parse error: …" + `hardware.stm.error` (HIGH,
    mesaj + ham satır); hiçbir `coil_update` yayınlanmaz, ACK yanıt izi YAZILMAZ."""
    satir = "-> STM_OK: D=0,0,0,0,0,0,0 P=0,0,0,0,0,0,0 F=0,0,0,0,0,0,0 T=0,0,0,0,0,0," + "9" * 400
    with caplog.at_level(logging.ERROR, logger=GUNLUK):
        c._handle_stm_line(satir)
    assert "STM_OK parse error: cannot convert float infinity to integer" in _mesajlar(caplog, logging.ERROR)
    assert bus.hepsi("hardware.stm.error") == [
        (
            "hardware.stm.error",
            {"message": "STM_OK parse error: cannot convert float infinity to integer", "raw": satir},
            EventPriority.HIGH,
            "headless_core",
        )
    ]
    assert bus.hepsi("hardware.stm.coil_update") == [] and list(c._stm_yanitlar) == []


class _YazilamayanIz(collections.deque):
    """Yanıt izi kabı: ekleme istisna verir (iz yazılamadı)."""

    def append(self, _x):
        raise RuntimeError("test: yanit izi yazilamadi")


def test_ACK_yanit_izi_YAZILAMAZSA_ACK_yine_ISLENIR_hata_olayi_YOK(c, bus, caplog):
    """Tüm-sıfır ACK'in yanıt izi yazılamazsa → istisna günlüğü "ACK yanıt izi yazılamadı (ACK işlendi)"; 7 `coil_update` ve
    `stop_onayi` (bobin_sayisi 7) yine yayınlanır, `hardware.stm.error` YOK."""
    c._stm_yanitlar = _YazilamayanIz(maxlen=64)
    with caplog.at_level(logging.ERROR, logger=GUNLUK):
        c._handle_stm_line(SIFIR_ACK)
    kayit = [r for r in caplog.records if r.getMessage() == "[STM32] ACK yanıt izi yazılamadı (ACK işlendi)"]
    assert kayit and kayit[0].exc_info[0] is RuntimeError
    assert [v["coil_id"] for _t, v, _p, _s in bus.hepsi("hardware.stm.coil_update")] == [1, 2, 3, 4, 5, 6, 7]
    assert [v for _t, v, _p, _s in bus.hepsi("hardware.stm.stop_onayi")] == [{"bobin_sayisi": 7}]
    assert bus.hepsi("hardware.stm.error") == []


def test_NACK_yanit_izi_YAZILAMAZSA_NACK_olayi_ve_yeniden_oynatma_SURER(c, bus, caplog):
    """NACK'in yanıt izi yazılamazsa → istisna günlüğü "NACK yanıt izi yazılamadı (yeniden oynatma sürüyor)"; HIGH NACK olayı yayınlanır
    ve yeniden oynatma isteği BİR kez çağrılır (Ö.4-Y8: STOP yeniden gönderimi izden bağımsız)."""
    c._stm_yanitlar = _YazilamayanIz(maxlen=64)
    istek = []
    with caplog.at_level(logging.ERROR, logger=GUNLUK):
        c._handle_stm_line("-> STM_NACK: CRC", retry_last_payload=lambda: istek.append(1))
    kayit = [
        r for r in caplog.records if r.getMessage() == "[STM32] NACK yanıt izi yazılamadı (yeniden oynatma sürüyor)"
    ]
    assert kayit and kayit[0].exc_info[0] is RuntimeError
    assert istek == [1]
    assert bus.hepsi("hardware.stm.nack") == [
        ("hardware.stm.nack", {"message": "-> STM_NACK: CRC"}, EventPriority.HIGH, "headless_core")
    ]


def test_STM_ERR_satiri_YUKSEK_oncelikli_hata_olayi_baglanti_DEGISMEZ(c, bus):
    """`STM_ERR` satırı → `hardware.stm.error` {message: satır} HIGH (kaynak headless_core); bağlantı durumu değişmez, başka olay yok."""
    c._handle_stm_line("-> STM_ERR: I2C2 zaman asimi")
    assert bus.kayit == [
        ("hardware.stm.error", {"message": "-> STM_ERR: I2C2 zaman asimi"}, EventPriority.HIGH, "headless_core")
    ]
    assert c.stm_is_connected is False


def test_banner_bekle_SURE_dolunca_None_isaretten_SONRA_gelen_banner_doner(c):
    """İşaretten sonra banner gelmediyse süre (0 sn) dolunca → None; işaretten SONRA okunan READY satırı → o satırın kendisi."""
    isaret = c.stm_banner_isareti()
    assert c.stm_banner_bekle(isaret, 0.0) is None
    c._handle_stm_line(YENI_BANNER)
    assert c.stm_banner_bekle(isaret, 0.0) == YENI_BANNER.strip()


# ───────────────────────────── telemetri savunma dönüşümleri ─────────────────────────────


def _genis_desen(desen: re.Pattern, eski: str, yeni: str) -> re.Pattern:
    assert desen.pattern.count(eski) == 1, eski
    return re.compile(desen.pattern.replace(eski, yeni))


def test_tele_bobin_kimligi_TAMSAYI_degilse_satir_None(c):
    """Desen bobin alanına rakam dışı bir değer yakalarsa (`int` ValueError) → `_parse_stm_tele` None (satır çöpe, istisna yok); gerçek
    desen aynı satırdan yalnız rakam kısmını alır."""
    satir = "-> STM_TELE: C=6x,T=34.20"
    assert c._parse_stm_tele(satir) == {"coil_id": 6, "object_temp": 34.2}
    c._TELE_DESENI = _genis_desen(hcm.HeadlessCore._TELE_DESENI, "(?P<c>[0-9]+)", r"(?P<c>[^,\s]+)")
    assert c._parse_stm_tele(satir) is None


def test_tele_olcum_alani_SAYI_degilse_YALNIZ_o_alan_atlanir(c):
    """Sıcaklık alanı float'a çevrilemezse → o anahtar HİÇ konmaz (0.0 da değil), öteki ölçümler korunur."""
    c._TELE_DESENI = _genis_desen(hcm.HeadlessCore._TELE_DESENI, "(?P<t>[+-]?[0-9]*[.]?[0-9]+)", r"(?P<t>[^,\s]+)")
    assert c._parse_stm_tele("-> STM_TELE: C=6,T=--,A=27.10") == {"coil_id": 6, "ambient_temp": 27.1}


def test_tele_ornek_sayisi_TAMSAYI_degilse_ornek_anahtari_YOK_alan_korunur(c):
    """Doğrulanmış alan satırında `N=` tamsayıya çevrilemezse → `magnetic_samples` konmaz, `magnetic_field` korunur."""
    c._TELE_DESENI = _genis_desen(hcm.HeadlessCore._TELE_DESENI, "(?P<n>[0-9]+)", r"(?P<n>[^,\s]+)")
    govde = c._parse_stm_tele("-> STM_TELE: C=6,T=30.0,B=1.842,N=4OO,GS=7")
    assert govde == {"coil_id": 6, "object_temp": 30.0, "magnetic_field": 1.842}


def test_sens_bobin_kimligi_TAMSAYI_degilse_bant_olayi_YOK(c, bus):
    """STM_SENS bobin alanı tamsayıya çevrilemezse → olay yayınlanmaz; aynı satır geçerli bobinle alan bandı olayı üretir."""
    c._SENS_ALAN_DESENI = _genis_desen(hcm.HeadlessCore._SENS_ALAN_DESENI, "(?P<c>[0-9]+)", r"(?P<c>[^\s]+)")
    c._stm_sens_isle("-> STM_SENS: C=6x I2C2 sicaklik=0x00 alan=0x18 kazanc=7 res=0 ayar=DOGRULANAMADI")
    assert bus.kayit == []
    c._stm_sens_isle("-> STM_SENS: C=6 I2C2 sicaklik=0x00 alan=0x18 kazanc=7 res=0 ayar=DOGRULANAMADI")
    assert [v for _t, v, _p, _s in bus.kayit] == [{"coil_id": 6, "alan_dogrulanamadi": True}]


# ───────────────────────────── olay yayını ve hizmetler ─────────────────────────────


def test_olay_yayini_PATLARSA_istisna_gunlugu_ve_cagiran_SURER(tmp_path, caplog):
    """Olay veriyolu `publish` istisna verirse → `_publish_event` fırlatmaz, ERROR "Event publish failed: <tür>" (istisna izli); satır
    işleme de fırlatmaz."""
    c = _cekirdek(_Veriyolu(patlat=True), tmp_path)
    with caplog.at_level(logging.ERROR, logger=GUNLUK):
        c._publish_event("hardware.stm.nack", {"message": "x"}, priority=EventPriority.HIGH)
        c._handle_stm_line("-> STM_ERR: x")
    kayit = [r for r in caplog.records if r.getMessage().startswith("Event publish failed: ")]
    assert [r.getMessage() for r in kayit] == [
        "Event publish failed: hardware.stm.nack",
        "Event publish failed: hardware.stm.error",
    ]
    assert kayit[0].exc_info[0] is RuntimeError


def _hizmet_siniflari(kayit: list, patlat: dict | None = None):
    """Hizmet sınıfı kayıtçıları: kurucu kwargs / start / stop / get_status; `patlat[(ad, adim)]` → o adımda istisna."""
    patlat = patlat or {}

    def _sinif(ad):
        class _Hizmet:
            def __init__(self, **kw):
                kayit.append((ad, "kur", kw))
                if (ad, "kur") in patlat:
                    raise patlat[(ad, "kur")]

            def start(self):
                kayit.append((ad, "start", None))
                if (ad, "start") in patlat:
                    raise patlat[(ad, "start")]

            def stop(self):
                kayit.append((ad, "stop", None))
                if (ad, "stop") in patlat:
                    raise patlat[(ad, "stop")]

            def get_status(self):
                return {"hizmet": ad}

        return _Hizmet

    return _sinif("mosquitto"), _sinif("ag"), _sinif("udp")


def test_hizmetler_SIRAYLA_dogru_portlarla_kurulur_ve_baslatilir(c, bus, monkeypatch, caplog):
    """`start_headless_services(ensure_mosquitto=False)` → MosquittoSupervisor(port 1883, ensure_running False, start_mdns True) →
    NetworkStatusService(mqtt_port 1883) → UdpDiscoveryService(api_port, discovery_port 5051, mqtt_port 1883, logger) sırasıyla kurulup
    başlatılır; üç INFO; durum özeti üçünü de içerir."""
    kayit: list = []
    mq, ag, udp = _hizmet_siniflari(kayit)
    monkeypatch.setattr(hcm, "MosquittoSupervisor", mq)
    monkeypatch.setattr(hcm, "NetworkStatusService", ag)
    monkeypatch.setattr(hcm, "UdpDiscoveryService", udp)
    with caplog.at_level(logging.INFO, logger=GUNLUK):
        c.start_headless_services(ensure_mosquitto=False)
    assert kayit == [
        ("mosquitto", "kur", {"port": 1883, "ensure_running": False, "start_mdns": True, "event_bus": bus}),
        ("mosquitto", "start", None),
        ("ag", "kur", {"mqtt_port": 1883, "event_bus": bus}),
        ("ag", "start", None),
        (
            "udp",
            "kur",
            {
                "api_port": 8123,
                "discovery_port": 5051,
                "mqtt_port": 1883,
                "event_bus": bus,
                "logger_instance": c.logger,
            },
        ),
        ("udp", "start", None),
    ]
    assert [m for m in _mesajlar(caplog, logging.INFO) if m.endswith(" started.")] == [
        "MosquittoSupervisor started.",
        "NetworkStatusService started.",
        "UdpDiscoveryService started.",
    ]
    durum = c.get_service_status()
    assert (durum["mosquitto"], durum["network"], durum["discovery"]) == (
        {"hizmet": "mosquitto"},
        {"hizmet": "ag"},
        {"hizmet": "udp"},
    )


def test_hizmet_KURULAMAZ_ya_da_BASLATILAMAZSA_uyari_ve_SONRAKI_hizmet_yine_denenir(c, monkeypatch, caplog):
    """Mosquitto kurucusu, ağ durumu `start`'ı, keşif kurucusu patlarsa → her biri için WARNING "<Hizmet> could not start: <hata>"; üç
    hizmet de denenir; kurucusu patlayan öznitelik None kalır, `start`'ı patlayan kurulmuş örnek olarak kalır."""
    kayit: list = []
    mq, ag, udp = _hizmet_siniflari(
        kayit,
        {
            ("mosquitto", "kur"): OSError(2, "mosquitto.exe bulunamadi"),
            ("ag", "start"): RuntimeError("is parcacigi baslatilamadi"),
            ("udp", "kur"): OSError(10048, "adres kullanimda"),
        },
    )
    monkeypatch.setattr(hcm, "MosquittoSupervisor", mq)
    monkeypatch.setattr(hcm, "NetworkStatusService", ag)
    monkeypatch.setattr(hcm, "UdpDiscoveryService", udp)
    with caplog.at_level(logging.WARNING, logger=GUNLUK):
        c.start_headless_services()
    assert [(a, s) for a, s, _k in kayit] == [("mosquitto", "kur"), ("ag", "kur"), ("ag", "start"), ("udp", "kur")]
    assert _mesajlar(caplog, logging.WARNING) == [
        "MosquittoSupervisor could not start: [Errno 2] mosquitto.exe bulunamadi",
        "NetworkStatusService could not start: is parcacigi baslatilamadi",
        "UdpDiscoveryService could not start: [Errno 10048] adres kullanimda",
    ]
    assert c.mosquitto_supervisor is None and c.udp_discovery_service is None
    assert isinstance(c.network_status_service, ag)


# ───────────────────────────── Y43 arka plan DB yeniden açması ─────────────────────────────


@pytest.fixture
def db_kurucular(monkeypatch):
    """Y43 kurucuları (EN ALT kat: DB modülünün yeniden açma işlevi) — sıra kaydı; `tedavi_hata` listesi sırayla fırlatılır."""
    from database import patient_database as _pdb
    from database import treatment_history_db as _thdb

    d = types.SimpleNamespace(cagri=[], hasta=object(), oturum=object(), tedavi_hata=[])

    def _hasta(kok):
        d.cagri.append(("hasta", Path(kok)))
        return d.hasta

    def _tedavi(kok):
        d.cagri.append(("tedavi", Path(kok)))
        if d.tedavi_hata:
            raise d.tedavi_hata.pop(0)

    def _oturum(kok):
        d.cagri.append(("oturum", Path(kok)))
        return d.oturum

    monkeypatch.setattr(_pdb, "acilista_acilamayani_yeniden_ac", _hasta)
    monkeypatch.setattr(_thdb, "acilista_acilamayani_yeniden_ac", _tedavi)
    monkeypatch.setattr(hcm, "get_session_manager", _oturum)
    return d


def _donguyu_kostur(c, sure=5.0):
    """Y43 döngüsünü kendi iş parçacığında koştur (üretimdeki gibi); süresinde bitmezse durdur ve başarısız say."""
    t = threading.Thread(target=c._db_yeniden_deneme_dongusu, daemon=True, name="db-yeniden-ac")
    t.start()
    t.join(timeout=sure)
    bitti = not t.is_alive()
    if not bitti:
        c._db_yeniden_dur.set()
        t.join(timeout=2)
    return bitti


def test_arka_plan_DB_yeniden_acma_BASARINCA_neden_DUSER_ornekler_YERLESIR(c, tmp_path, db_kurucular, caplog):
    """Açılışta iki DB de açılamamışken arka plan denemesi başarılı → hasta örneği ve yeni oturum yöneticisi yerleşir, iki neden ve
    ayrıntısı düşer, her DB için WARNING "<ad> ARKA PLANDA AÇILDI (deneme 1)"; döngü kendiliğinden biter."""
    c.DB_YENIDEN_DENEME_ARALIKLARI_SN = (0.01,)
    c._db_yeniden_dur = threading.Event()
    c.patient_db = None
    c.session_manager = None
    c.db_acilis_hatalari = {"hasta": "Hasta veritabanı açılamadı", "tedavi": "Tedavi kaydı açılamadı"}
    c.db_acilis_ayrintilari = {"hasta": ("acilamadi", "RuntimeError"), "tedavi": ("acilamadi", "OSError")}
    with caplog.at_level(logging.WARNING, logger=GUNLUK):
        assert _donguyu_kostur(c), "Y43 döngüsü başarıdan sonra bitmedi"
    assert db_kurucular.cagri == [("hasta", tmp_path), ("tedavi", tmp_path), ("oturum", tmp_path)]
    assert c.patient_db is db_kurucular.hasta and c.session_manager is db_kurucular.oturum
    assert c.db_acilis_hatalari == {} and c.db_acilis_ayrintilari == {}
    assert [m for m in _mesajlar(caplog, logging.WARNING) if "ARKA PLANDA AÇILDI" in m] == [
        "Hasta veritabanı ARKA PLANDA AÇILDI (deneme 1) — DB'siz kısıtlı kip kalktı.",
        "Tedavi kaydı veritabanı ARKA PLANDA AÇILDI (deneme 1) — DB'siz kısıtlı kip kalktı.",
    ]


def test_arka_plan_DB_yeniden_acma_ILK_deneme_basarisiz_IKINCIDE_acilir_ayrinti_sozlugu_YOKSA_dokunulmaz(
    c, tmp_path, db_kurucular, caplog
):
    """Yalnız tedavi DB'si açılamamış, ilk deneme dosya kilidi (PermissionError) → WARNING (deneme 1: PermissionError) ve neden KALIR;
    ikinci denemede açılır → neden
    düşer, "(deneme 2)". Ayrıntı sözlüğü olmayan (eski) çekirdekte ayrıntı özniteliği YARATILMAZ; hasta DB'si yeniden açılmaz."""
    c.DB_YENIDEN_DENEME_ARALIKLARI_SN = (0.01, 0.02)
    c._db_yeniden_dur = threading.Event()
    c.patient_db = "mevcut-hasta-db"
    c.session_manager = None
    c.db_acilis_hatalari = {"tedavi": "Tedavi kaydı açılamadı"}
    del c.db_acilis_ayrintilari
    db_kurucular.tedavi_hata.append(PermissionError(13, "dosya baska surecte kilitli"))
    with caplog.at_level(logging.WARNING, logger=GUNLUK):
        assert _donguyu_kostur(c)
    assert db_kurucular.cagri == [("tedavi", tmp_path), ("tedavi", tmp_path), ("oturum", tmp_path)]
    uyarilar = _mesajlar(caplog, logging.WARNING)
    assert (
        "Tedavi kaydı veritabanı arka planda yeniden açılamadı (deneme 1: PermissionError); sonraki deneme 0 sn sonra."
        in uyarilar
    )
    assert "Tedavi kaydı veritabanı ARKA PLANDA AÇILDI (deneme 2) — DB'siz kısıtlı kip kalktı." in uyarilar
    assert c.db_acilis_hatalari == {} and c.patient_db == "mevcut-hasta-db" and c.session_manager is db_kurucular.oturum
    assert not hasattr(c, "db_acilis_ayrintilari")


# ───────────────────────────── kapanış (`quit`) ─────────────────────────────


class _IsParcacigi:
    """DB yeniden açma iş parçacığı nesnesi: `join` süresini kaydeder; `biter` False ise join'den sonra da canlı kalır (takılı göç)."""

    def __init__(self, biter: bool):
        self.join_sureleri: list = []
        self._biter = biter
        self._canli = True

    def is_alive(self):
        return self._canli

    def join(self, timeout=None):
        self.join_sureleri.append(timeout)
        if self._biter:
            self._canli = False


def test_quit_SIRASI_durdurma_isaretleri_hizmet_hatalari_YUTULUR_TAKILI_DB_uyarisi(c, bus, monkeypatch, caplog):
    """`quit` → önce `system.core.stopping`; Y43 ve HWSender durdurma işaretleri kurulur, gönderici join edilir (ÖLÜ); takılı DB iş
    parçacığı 10 sn sınırıyla beklenir ve WARNING "10 sn'de bitmedi"; keşif → ağ → mosquitto sırasıyla durdurulur, üçünün istisnası da
    ERROR günlüğe yazılır ve sonraki durdurma yine koşar; bağlı STM "kopuk"a çekilir (`hardware.stm.disconnected`); en son `system.core.stopped`.
    `stop` = `quit`."""
    kayit: list = []
    mq, ag, udp = _hizmet_siniflari(
        kayit,
        {
            ("udp", "stop"): RuntimeError("soket kapanmadi"),
            ("ag", "stop"): TimeoutError("yoklama is parcacigi bitmedi"),
            ("mosquitto", "stop"): OSError(5, "erisim engellendi"),
        },
    )
    c.udp_discovery_service, c.network_status_service, c.mosquitto_supervisor = udp(), ag(), mq()
    kayit.clear()
    c._set_stm_connected(True)
    bus.kayit.clear()
    c._db_yeniden_dur = threading.Event()
    db_is = _IsParcacigi(biter=False)
    c._db_yeniden_thread = db_is
    gonderici = threading.Thread(target=c._hw_sender_stop.wait, daemon=True, name="KP-HWSender-vekili")
    gonderici.start()
    c._hw_sender_thread = gonderici
    try:
        with caplog.at_level(logging.WARNING, logger=GUNLUK):
            c.quit()
        assert not gonderici.is_alive(), "quit HWSender'ı durdurmadan join etti"
    finally:
        c._hw_sender_stop.set()
        gonderici.join(timeout=2)
    assert bus.turler() == ["system.core.stopping", "hardware.stm.disconnected", "system.core.stopped"]
    assert bus.kayit[0][3] == "headless_core" and c.stm_is_connected is False
    assert c._db_yeniden_dur.is_set() and db_is.join_sureleri == [10.0]
    assert "DB yeniden açma denemesi 10 sn'de bitmedi; kapanış sürüyor." in _mesajlar(caplog, logging.WARNING)
    assert [(a, s) for a, s, _k in kayit] == [("udp", "stop"), ("ag", "stop"), ("mosquitto", "stop")]
    hatalar = {r.getMessage(): r.exc_info[0] for r in caplog.records if r.levelno == logging.ERROR}
    assert hatalar == {
        "UDP discovery shutdown failed": RuntimeError,
        "Network status service shutdown failed": TimeoutError,
        "Mosquitto supervisor shutdown failed": OSError,
    }
    assert hcm.HeadlessCore.stop is hcm.HeadlessCore.quit


def test_quit_HIZMETSIZ_ve_DB_is_parcacigi_BITERSE_uyari_yok_kopuk_olayi_yok(c, bus, caplog):
    """Hizmet yok, STM zaten kopuk, Y43 durdurma işareti hiç kurulmamış, DB iş parçacığı join'de biter → yalnız `stopping` / `stopped`
    olayları; uyarı / hata günlüğü YOK."""
    db_is = _IsParcacigi(biter=True)
    c._db_yeniden_thread = db_is
    gonderici = threading.Thread(target=c._hw_sender_stop.wait, daemon=True, name="KP-HWSender-vekili")
    gonderici.start()
    c._hw_sender_thread = gonderici
    try:
        with caplog.at_level(logging.WARNING, logger=GUNLUK):
            c.quit()
    finally:
        c._hw_sender_stop.set()
        gonderici.join(timeout=2)
    assert bus.turler() == ["system.core.stopping", "system.core.stopped"]
    assert db_is.join_sureleri == [10.0] and _mesajlar(caplog) == []
