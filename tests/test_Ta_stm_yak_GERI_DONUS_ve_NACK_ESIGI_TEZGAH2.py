# Author: mertaygn, cglrgrkn
"""T-a (Tezgâh-2 #1, C14–C16 · Y195) — `stm_yak.py` uyumsuz ikilide OTOMATİK GERİ DÖNER; kart doğrulamasının yoklama sayısı CRC NACK
karar eşiğiyle TUTARLI; `stm_firmware_kimligi.py` eski kartta "UYUMSUZ" der.

ÖLÇÜLEN KUSUR (tezgâh 2026-10-23, gerçek STM32F429ZI + ST-Link, `DENETIM\\t2\\kanit\\C1_kimlik_once.txt`, `C15_*`):
  * Saha imajlı (120 B, DDS v2.3) kart 12 sn'de 796 `STM_TELE` satırı basarken kimlik betiğinin 3 sıfır-duty yoklamasına YALNIZ 2
    `STM_NACK: CRC` döndü (eski firmware TX meşgulken NACK'i düşürür — D1.106 öncesi). Karar eşiği 3 CRC NACK → hüküm "❓ DOĞRULANAMADI".
  * Geri dönüş provası: v2.4 karta bilerek 120 B imaj yakıldı → kart doğrulaması `uyum=None` → rc 9 (BANNER_TANINMADI), OTOMATİK GERİ DÖNÜŞ
    YOK, kart uyumsuz imajda KALDI; elle kurtarma gerekti (C16).
SÖZLEŞME:
  * Servis araçlarının (kimlik betiği, `stm_yak` doğrulaması) yoklama sayısı ≥ 3 × red eşiği (kayıplı NACK'te de karar verilir).
    Backend el sıkışması DEĞİŞMEZ (Ö.4-Y8: pencere uzarsa yeniden bağlanmada ACİL DURDUR gecikir; geç NACK canlı hatta sızar).
  * Yakma sonrası kart kendini DOĞRULAMADIYSA (uyumsuz YA DA "doğrulanamadı") önceki firmware'e OTOMATİK geri dönülür. İstisna (D1.114):
    port başka süreçte açık → PORT_MESGUL (doğrulama kanalı yok — geri dönüş de doğrulanamazdı).
  * Elle kurtarma (`--kurtarma`): bilinçli eski imaj yazımı uyum hükmüyle GERİ ALINMAZ (yazma + bağımsız geri okuma + kart konuştu).
Kart ve yakıcı SAHTE, EN ALT katta: seri port (`serial.Serial`) ve yakıcı CLI (`stm_yakma._kos`). Gerçek port / ST-Link / yakma YOK.
"""

from __future__ import annotations

import importlib.util
import queue
from pathlib import Path

import pytest
from test_firmware_otomatik_ONKOSULLAR_Y80_Y81_Y82_LN import ortam  # noqa: F401 — fikstür (backend yakma yolu)

KOK = Path(__file__).resolve().parents[1]
SAHA_BANNER = "-> STM_READY: DDS v2.3 (7-ch KARMA uni=0x60 + HW_SYNC@PB1) Waiting for commands..."
YENI_BANNER = "-> STM_READY: DDS v2.5 (7-ch KARMA uni=0x60 + HW_SYNC@PB1) proto=3 pkt=121 Waiting for commands..."
YENI_KIMLIK = "-> STM_ID: DDS v2.5 (7-ch KARMA uni=0x60 + HW_SYNC@PB1) proto=3 pkt=121"
CRC_NACK = "-> STM_NACK: CRC"
TELE = "-> STM_TELE: C=1,I= "
GERCEK_ACK = (
    "-> STM_OK: D=0,0,0,0,0,0,0 P=0,0,0,0,0,0,0 F=100,100,100,100,100,100,100 T=0,0,0,0,0,0,0 K=96 E=0,0,0,0,0,0,0"
)
#: Tezgâh çıktısı biçimi (`DENETIM\\t2\\kanit\\C1_rst_once.txt`): yakıcının bağlandığı probun satırı.
STLINK_LISTESI = (
    "-------- Connected ST-LINK Probes List --------\n\nST-Link Probe 0 :\n   ST-LINK SN  : 066DFF565251887067064422\n"
    "   ST-LINK FW  : V2J46M31\n   Board Name  : NUCLEO-F429ZI\n-----------------------------------------------\n"
)
#: Pinlenen asgari değerler (kapı sabiti mutasyon hedefinden OKUNMAZ).
RED_ESIGI_ASGARI = 3
YOKLAMA_ASGARI = 3 * RED_ESIGI_ASGARI
#: Ö.4-Y8: el sıkışma doğrulama penceresi bundan UZUN olamaz (yeniden bağlanmada ACİL DURDUR'un porta ilk yazımı en çok bu kadar gecikir;
#: TD3 / T2D-1 aparatı `≤ 1,5 sn` varsayar).
PENCERE_AZAMI_SN = 1.5


class _Kart:
    """Bayt düzeyinde kart öykünmesi (`serial.Serial` yerine). Türler:
    `eski`   — 120 B saha imajı: kimlik sorgusunu yok sayar, her 121 B pakete CRC NACK — ama TELEMETRİ basarken her 3. NACK'i DÜŞÜRÜR
               (tezgâh: 3 yoklamaya 2 NACK); `sessiz` — banner basar, paketlere hiç yanıt vermez; `yeni` — STM_ID + STM_OK."""

    def __init__(self, tur: str):
        from utils.stm32_transport import STM_KIMLIK_SORGUSU, STM_PAKET_BOYU

        self.tur = tur
        self.is_open = True
        self._q: queue.Queue = queue.Queue()
        self._sorgu = STM_KIMLIK_SORGUSU
        self._boy = STM_PAKET_BOYU
        self.paket = 0
        self.yazilan: list[bytes] = []
        self._koy(YENI_BANNER if tur == "yeni" else SAHA_BANNER)
        if tur == "eski":
            self._koy(TELE)

    def _koy(self, satir: str) -> None:
        self._q.put((satir + "\r\n").encode())

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        self.is_open = False
        return False

    def readline(self):
        try:
            return self._q.get(timeout=0.02)
        except queue.Empty:
            return b""

    def read(self, _n=1):
        return self.readline()

    def write(self, b):
        b = bytes(b)
        self.yazilan.append(b)
        if b == self._sorgu:
            if self.tur == "yeni":
                self._koy(YENI_KIMLIK)
        elif len(b) == self._boy and b[:2] == b"\xaa\x55":
            self.paket += 1
            if self.tur == "yeni":
                self._koy(GERCEK_ACK)
            elif self.tur == "eski":
                self._koy(TELE)
                if self.paket % 3:  # her 3. NACK telemetri yüzünden DÜŞER (eski firmware: TX meşgul)
                    self._koy(CRC_NACK)
        return len(b)

    def close(self):
        self.is_open = False


@pytest.fixture
def kart(monkeypatch):
    """`serial.Serial` → sahte kart (tür testte seçilir). Açılan her port aynı tür kartı görür (yakma sonrası ve geri dönüş sonrası)."""
    import serial

    durum = {"tur": "eski", "acilan": []}

    def _ac(port, baud=115200, timeout=None, **_k):
        k = _Kart(durum["tur"])
        durum["acilan"].append((port, k))
        return k

    monkeypatch.setattr(serial, "Serial", _ac)
    monkeypatch.setattr("utils.stm32_uart.portlari_listele", lambda: [])  # gerçek COM numaralandırması YOK
    return durum


@pytest.fixture(scope="module")
def betik():
    p = KOK / "scripts" / "stm_firmware_kimligi.py"
    spec = importlib.util.spec_from_file_location("_stm_firmware_kimligi_ta", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


# ── (1) eşik tutarlılığı ──────────────────────────────────────────────────────────────────────────────────────────


def test_KRITIK_arac_yoklama_sayisi_RED_ESIGININ_uc_kati_ve_PENCERE_yeter():
    from utils import stm32_kimlik as sk
    from utils import stm32_transport as st
    from utils import stm32_uart as su

    assert sk.PAKET_RED_CRC_ESIGI == RED_ESIGI_ASGARI, "red eşiği değişti — kapıyı ve kart davranışını yeniden ölç"
    assert su.ARAC_DOGRULAMA_YOKLAMA_SAYISI >= YOKLAMA_ASGARI, (
        f"araç yoklaması {su.ARAC_DOGRULAMA_YOKLAMA_SAYISI} < {YOKLAMA_ASGARI}: kayıplı NACK'te (tezgâh 3 yoklama → 2 NACK) karar "
        "eşiğine ulaşılamaz"
    )
    assert su.ARAC_OKUMA_ZAMAN_ASIMI_SN >= 0.3 and st.DOGRULAMA_ARALIK_SN > 0


def test_KRITIK_backend_el_sikisma_penceresi_UZAMAZ_Y8():
    """Ö.4-Y8: backend el sıkışması pencere bitmeden dönmez → yeniden bağlanmada ACİL DURDUR'un porta ilk yazımı en çok bu kadar gecikir.
    T-a ilk denemesi pencereyi 4,2 sn'ye çıkarınca TD3 / T2D-1 kapısında yanıtsız kartta E-stop STOP'u porta yazılamadı."""
    from utils import stm32_transport as st

    assert st.DOGRULAMA_SURESI_SN <= PENCERE_AZAMI_SN, st.DOGRULAMA_SURESI_SN
    assert st.DOGRULAMA_YOKLAMA_SAYISI <= RED_ESIGI_ASGARI, (
        "backend el sıkışmasına fazladan yoklama: geç NACK'leri el sıkışmadan sonra canlı hatta düşer (TD3 saha_gec_nack)"
    )


def test_KRITIK_kart_dogrula_KAYIPLI_NACKte_eski_karti_REDDEDER(kart):
    """Servis araçlarının ortak doğrulaması (`stm32_uart.kart_dogrula`: kimlik betiği + `stm_yak` yakma sonrası)."""
    from utils.stm32_kimlik import satirlardan_karar
    from utils.stm32_transport import STM_PAKET_BOBIN_SAYISI
    from utils.stm32_uart import kart_dogrula

    kart["tur"] = "eski"
    satirlar, ozet = kart_dogrula("COM_TA", 0.2)
    uyumlu, sebep, _ = satirlardan_karar(satirlar, STM_PAKET_BOBIN_SAYISI)
    assert ozet["crc_nack"] >= RED_ESIGI_ASGARI and not ozet["kabul"], ozet
    assert uyumlu is False, f"kayıplı NACK'li eski kart reddedilmedi: {uyumlu!r} ({sebep}) {ozet}"


def test_KARSIT_kart_dogrula_yeni_kart_ILK_yoklamada_kabul_fazladan_yoklama_YOK(kart):
    from utils.stm32_uart import kart_dogrula

    kart["tur"] = "yeni"
    _satirlar, ozet = kart_dogrula("COM_TA", 0.2)
    assert ozet["kabul"] and ozet["kimlik"] and ozet["yoklama"] == 1, ozet


# ── (2) servis betiği: eski kartta "UYUMSUZ" ─────────────────────────────────────────────────────────────────────


def test_KRITIK_kimlik_betigi_KAYIPLI_NACKli_eski_kartta_UYUMSUZ_der(betik, kart, monkeypatch, capsys):
    kart["tur"] = "eski"
    monkeypatch.setattr("sys.argv", ["stm_firmware_kimligi.py", "--port", "COM_TA", "--sure", "0.2"])
    rc = betik.main()
    out = capsys.readouterr().out
    assert rc == 1, f"rc {rc} (1 = UYUMSUZ beklenirdi):\n{out}"
    assert "UYUMSUZ" in out and "DOĞRULANAMADI" not in out, out


# ── (3) yakma akışı (CLI): doğrulanamadı / uyumsuz → OTOMATİK geri dönüş ─────────────────────────────────────────


class _Flash:
    """EN ALT kat: yakıcı CLI (`_kos`) — `-l st-link` tek prob listesi, `-w` flash'a yazar, `-r` flash'tan okur, `-rst` sayılır."""

    def __init__(self, ilk: bytes):
        self.flash = bytearray(ilk) + bytearray(b"\xff" * 64)
        self.cagri: list[list[str]] = []

    def __call__(self, _cli, argumanlar, timeout=300.0):
        self.cagri.append(list(argumanlar))
        if argumanlar[:1] == ["-l"]:
            return 0, STLINK_LISTESI
        if "-w" in argumanlar:
            veri = Path(argumanlar[argumanlar.index("-w") + 1]).read_bytes()
            self.flash[: len(veri)] = veri
        if "-r" in argumanlar:
            i = argumanlar.index("-r")
            boy, hedef = int(argumanlar[i + 2]), Path(argumanlar[i + 3])
            hedef.parent.mkdir(parents=True, exist_ok=True)
            hedef.write_bytes(bytes(self.flash[:boy]).ljust(boy, b"\xff"))
        return 0, "sahte yakici: tamam"

    def yazim(self) -> int:
        return sum(1 for c in self.cagri if "-w" in c)


@pytest.fixture
def yakma(monkeypatch, tmp_path):
    import utils.stm_yakma as sy

    flash = _Flash(b"ONCEKI-FW-" * 16)
    monkeypatch.setattr(sy, "programmer_cli", lambda: Path("sahte_cli.exe"))
    monkeypatch.setattr(sy, "_kos", flash)
    monkeypatch.setattr(sy.time, "sleep", lambda _s: None)
    ikili = tmp_path / "pemf.bin"
    ikili.write_bytes(b"YENI-FIRMWARE-" * 8)
    return sy, ikili, flash


def _akis(sy, ikili, tmp_path):
    return sy.yakma_akisi(ikili, port="COM_TA", guvenlik_kontrolu=lambda: (True, "test"), yedek_dizin=tmp_path / "y")


def test_KRITIK_uyumsuz_ikili_KAYIPLI_NACKte_de_OTOMATIK_GERI_DONER(yakma, kart, tmp_path):
    """Tezgâh C15: 120 B imaj yakıldı, kart 3 yoklamaya 2 NACK verdi → `uyum=None`, rc 9, geri dönüş YOK."""
    sy, ikili, flash = yakma
    kart["tur"] = "eski"
    s = _akis(sy, ikili, tmp_path)
    assert flash.yazim() == 2, f"otomatik geri dönüş yazımı yok (kod {s.kod}: {s.ozet})\n{s.adimlar}"
    assert s.kod == sy.UYUMSUZ_GERI_DONULDU, f"{s.kod} {s.ozet}"
    assert bytes(flash.flash[:10]) == b"ONCEKI-FW-", "kart önceki firmware'e dönmedi"


def test_KRITIK_kart_kendini_DOGRULAMADIYSA_GERI_DONER(yakma, kart, tmp_path):
    """Kart banner basıyor ama paketlere hiç yanıt vermiyor (kanıt yok → `uyum=None`): yeni firmware doğrulanmadan kartta KALMAZ."""
    sy, ikili, flash = yakma
    kart["tur"] = "sessiz"
    s = _akis(sy, ikili, tmp_path)
    assert flash.yazim() == 2, f"doğrulanamayan firmware kartta bırakıldı (kod {s.kod}: {s.ozet})"
    assert s.kod == getattr(sy, "DOGRULANAMADI_GERI_DONULDU", -1), f"{s.kod} {s.ozet}"
    assert "DOĞRULA" in s.ozet.upper() and "geri dönüldü" in s.ozet, s.ozet


def test_KARSIT_kart_KENDINI_dogrularsa_TAMAM_ve_tek_yazim(yakma, kart, tmp_path):
    sy, ikili, flash = yakma
    kart["tur"] = "yeni"
    s = _akis(sy, ikili, tmp_path)
    assert s.kod == sy.TAMAM and flash.yazim() == 1, f"{s.kod} {s.ozet} {flash.cagri}"


# ── (4) elle kurtarma: bilinçli eski imaj yazımı uyum hükmüyle GERİ ALINMAZ ────────────────────────────────────────


def _cli(argv):
    p = KOK / "scripts" / "stm_yak.py"
    spec = importlib.util.spec_from_file_location("_stm_yak_ta", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m.main(argv)


def test_KRITIK_KURTARMA_kipi_eski_imaji_yazar_ve_GERI_ALMAZ(yakma, kart, tmp_path, monkeypatch, capsys):
    """Prosedür "Elle kurtarma": `stm_yak.py --bin saha_yedek_1.bin` → eski (120 B) imaj uyumsuz sayılıp otomatik GERİ DÖNÜLÜRSE kurtarma
    kendini bozar. `--kurtarma` kipi: ön kontrol + yaz + bağımsız geri okuma + kart konuştu = TAMAM; uyum hükmü yalnız raporlanır."""
    import utils.stm_yakma as sy

    _sy, _ikili, flash = yakma
    monkeypatch.setattr(sy, "seans_ve_bobin_kontrolu", lambda _b: (True, "test: backend kapalı"))
    eski = tmp_path / "saha_yedek_1.bin"
    eski.write_bytes(b"SAHA-IMAJI-" * 12)
    kart["tur"] = "eski"
    rc = _cli(["--kurtarma", "--bin", str(eski), "--sha256", sy.sha256(eski), "--port", "COM_TA"])
    out = capsys.readouterr().out
    assert rc == 0, out
    assert flash.yazim() == 1, f"kurtarma yazımı geri alındı ya da tekrarlandı: {flash.cagri}"
    assert bytes(flash.flash[:11]) == b"SAHA-IMAJI-", "eski imaj karta yazılmadı"


def test_KRITIK_KURTARMA_sha_TUTMAZSA_yazmaz(yakma, kart, tmp_path, monkeypatch, capsys):
    import utils.stm_yakma as sy

    _sy, _ikili, flash = yakma
    monkeypatch.setattr(sy, "seans_ve_bobin_kontrolu", lambda _b: (True, "test: backend kapalı"))
    eski = tmp_path / "saha_yedek_1.bin"
    eski.write_bytes(b"SAHA-IMAJI-" * 12)
    rc = _cli(["--kurtarma", "--bin", str(eski), "--sha256", "0" * 64, "--port", "COM_TA"])
    assert rc == sy.BUTUNLUK and flash.yazim() == 0, (rc, flash.cagri, capsys.readouterr().out)


# ── (5) backend yakması (oto-firmware, Y1 kapalı): aynı kural + Y82 yarım kaydı geri dönüş doğrulanınca silinir ──────────────


def test_KRITIK_backend_yolu_KANITSIZ_bannerda_GERI_DONER_ve_yarim_kayit_SILINIR(ortam):
    """Çekirdeğin okuyucusundan gelen banner paket boyunu söylemiyor (`uyum=None`) → önceki firmware'e dönülür (kod 15) ve kart geri
    dönülen firmware'le konuştuğu için "yarım yakma" kaydı silinir (doğrulanmış hâl); Y80: aynı SHA yeniden denenmez (`son_yakma`).
    Fikstür LN L1 kapısınınki (ağ `_pinli_ac`, yakıcı `stm_yakma._kos` sahte FLASH — EN ALT kat)."""
    import test_firmware_otomatik_ONKOSULLAR_Y80_Y81_Y82_LN as ln

    o = ortam
    beyansiz = "-> STM_READY: DDS v2.4 (7-ch KARMA uni=0x60 + HW_SYNC@PB1) Waiting for commands..."
    o.banner = lambda: o.sy.BannerKaynagi(isaret=lambda: 1, bekle=lambda _i, _s: beyansiz)
    eski = bytes(o.kart.flash[:32])
    d = ln._ac(o)
    assert "[15]" in str(d.get("hata")), d
    assert bytes(o.kart.flash[:32]) == eski, "kart önceki firmware'e dönmedi"
    assert not (o.kok / o.fm.YARIM_YAKMA_DOSYASI).exists(), "geri dönüş doğrulandı ama yarım yakma kaydı KALDI"
    assert (o.kok / o.fm.SON_YAKMA_DOSYASI).exists(), (
        "Y80: kanıtsız ikilinin SHA'sı kaydedilmedi (her açılış yeniden yakardı)"
    )
