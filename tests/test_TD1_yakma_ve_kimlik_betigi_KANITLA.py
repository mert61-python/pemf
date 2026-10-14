# Author: mertaygn, cglrgrkn
"""TD1-d / TD1-e (tezgâh Oturum 13, K10 · FAZ H) — servis betiği ve ürün yakma akışı uyumu BANNER'la değil KANITLA söyler.

ÖLÇÜLEN KUSUR (tezgâh 2026-10-14):
  * `scripts/stm_firmware_kimligi.py` 120 baytlık saha imajlı kartta "✅ UYUMLU FIRMWARE YUKLU … Bobinler baslamiyorsa sebep
    firmware DEGIL" dedi (K10, YANLIŞ YÖN) — banner 120 / 121 ayırt edemiyor.
  * Ürün yakma akışı (`scripts/stm_yak.py` → `utils/stm_yakma.yakma_akisi`) yakmadan ÖNCE ve SONRA aynı banner'ı görüp iki
    yönde de "uyum=True" dedi; yakmanın gerçekleştiğini kanıtlayan tek şey `-v` + elle geri okumaydı.
SÖZLEŞME:
  * Betik: banner tek başına → "DOĞRULANAMADI"; kartın paketimize yanıtı (STM_OK / sistematik CRC NACK) ya da Y68 kimlik
    yanıtı → kesin; aktif doğrulama (kimlik sorgusu + sıfır-duty) `utils/stm32_uart.kart_dogrula` (sevk edilen kod).
  * Yakma: TAMAM ancak (1) yakıcı + (2) BAĞIMSIZ geri okuma yazılan ikiliyle bayt bayt AYNI + (3) kart kendini doğruladı
    (Y68 beyanı / paket kabulü). Geri okuma tutmazsa GERI_OKUMA_TUTMADI + otomatik geri dönüş; eski firmware hâlâ koşuyorsa
    (CRC NACK) uyumsuz → geri dönüş. Kart / seri port SAHTE (EN ALT kat: `_kos` flash öykünmesi, `kart_dogrula` satırları).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
SAHA_BANNER = "-> STM_READY: DDS v2.3 (7-ch KARMA uni=0x60 + HW_SYNC@PB1) Waiting for commands..."
YENI_BANNER = "-> STM_READY: DDS v2.3 (7-ch KARMA uni=0x60 + HW_SYNC@PB1) proto=3 pkt=121 Waiting for commands..."
YENI_KIMLIK = "-> STM_ID: DDS v2.3 (7-ch KARMA uni=0x60 + HW_SYNC@PB1) proto=3 pkt=121"
CRC_NACK = "-> STM_NACK: CRC"
GERCEK_ACK = (
    "-> STM_OK: D=0,0,0,0,0,0,0 P=0,0,0,0,0,0,0 F=100,100,100,100,100,100,100 T=0,0,0,0,0,0,0 K=96 E=0,0,0,0,0,0,0"
)


@pytest.fixture(scope="module")
def betik():
    p = KOK / "scripts" / "stm_firmware_kimligi.py"
    spec = importlib.util.spec_from_file_location("_stm_firmware_kimligi_td1", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


# ── TD1-d · K10: servis betiği ────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("satirlar", "beklenen"),
    [
        ([SAHA_BANNER], None),
        ([SAHA_BANNER, CRC_NACK, CRC_NACK, CRC_NACK], False),
        ([SAHA_BANNER, GERCEK_ACK], True),
        ([YENI_BANNER, YENI_KIMLIK, GERCEK_ACK], True),
        ([YENI_KIMLIK.replace("pkt=121", "pkt=120")], False),
    ],
    ids=["yalniz_banner", "eski_kart_CRC", "kabul", "y68", "y68_120"],
)
def test_KRITIK_betik_karari_KANITTAN(betik, satirlar, beklenen):
    uyumlu, sebep, _k = betik.firmware_karari(satirlar)
    assert uyumlu is beklenen, f"{satirlar}: {uyumlu!r} ({sebep})"


def test_KRITIK_K10_eski_kartta_UYUMLU_ve_SEBEP_FIRMWARE_DEGIL_DEMEZ(betik, monkeypatch, capsys):
    monkeypatch.setattr(betik, "_portlari_bul", lambda _p: ["COM_TD1"])
    monkeypatch.setattr(
        betik, "_kart_dogrula", lambda port, sure: ([SAHA_BANNER, CRC_NACK, CRC_NACK, CRC_NACK], {"crc_nack": 3})
    )
    monkeypatch.setattr("sys.argv", ["stm_firmware_kimligi.py", "--port", "COM_TD1"])
    rc = betik.main()
    out = capsys.readouterr().out
    assert rc == 1, out
    assert "UYUMLU FIRMWARE" not in out and "sebep firmware DEGIL" not in out, out
    assert "UYUMSUZ" in out


def test_KRITIK_K10_yalniz_banner_DOGRULANAMADI_der(betik, monkeypatch, capsys):
    monkeypatch.setattr(betik, "_portlari_bul", lambda _p: ["COM_TD1"])
    monkeypatch.setattr(betik, "_kart_dogrula", lambda port, sure: ([SAHA_BANNER], {"crc_nack": 0}))
    monkeypatch.setattr("sys.argv", ["stm_firmware_kimligi.py", "--port", "COM_TD1"])
    rc = betik.main()
    out = capsys.readouterr().out
    assert rc == 2 and "DOĞRULANAMADI" in out and "UYUMLU FIRMWARE" not in out, out


# ── TD1-e: ürün yakma akışı — geri okuma + kartın kendi doğrulaması ──────────────────────────────────────────────


class _Flash:
    """EN ALT kat sahtesi: yakıcı CLI (`_kos`) — `-w <dosya>` flash'a yazar (`bozuk` ise son bayt bozulur), `-r <adr>
    <boy> <dosya>` flash'ın ilk <boy> baytını dosyaya yazar, `-rst` kartı yeniden başlatır (sayılır)."""

    def __init__(self, ilk: bytes, bozuk: bool = False):
        self.flash = bytearray(ilk) + bytearray(b"\xff" * 64)
        self.bozuk = bozuk
        self.cagri: list[list[str]] = []

    def __call__(self, _cli, argumanlar, timeout=300.0):
        self.cagri.append(list(argumanlar))
        if "-w" in argumanlar:
            veri = bytearray(Path(argumanlar[argumanlar.index("-w") + 1]).read_bytes())
            if self.bozuk:
                veri[-1] ^= 0xFF
            self.flash[: len(veri)] = veri
        if "-r" in argumanlar:
            i = argumanlar.index("-r")
            boy, hedef = int(argumanlar[i + 2]), Path(argumanlar[i + 3])
            hedef.parent.mkdir(parents=True, exist_ok=True)
            hedef.write_bytes(bytes(self.flash[:boy]).ljust(boy, b"\xff"))
        return 0, "sahte yakici: tamam"


@pytest.fixture
def yakma(monkeypatch, tmp_path):
    import utils.stm_yakma as sy

    monkeypatch.setattr(sy, "programmer_cli", lambda: Path("sahte_cli.exe"))
    monkeypatch.setattr(sy.time, "sleep", lambda _s: None)
    ikili = tmp_path / "pemf.bin"
    ikili.write_bytes(b"YENI-FIRMWARE-" * 8)
    return sy, ikili


def _kos(sy, ikili, tmp_path, monkeypatch, flash: _Flash, kart_satirlari: list[str]):
    monkeypatch.setattr(sy, "_kos", flash)
    monkeypatch.setattr(sy, "kart_dogrula", lambda port, sure: (list(kart_satirlari), {}))
    monkeypatch.setattr(sy, "port_adaylari", lambda _p=None: ["COM_TD1"])
    return sy.yakma_akisi(ikili, guvenlik_kontrolu=lambda: (True, "test"), yedek_dizin=tmp_path / "y")


def test_KRITIK_yalniz_AYNI_banner_yakmayi_KANITLAMAZ(yakma, tmp_path, monkeypatch):
    """Tezgâh: yakmadan önceki ve sonraki banner birebir aynıydı; akış "uyum=True / yakıldı ve kart kendi kimliğiyle
    doğruladı" dedi. Paket boyu söylemeyen banner + kanıt yok → TAMAM DEĞİL."""
    sy, ikili = yakma
    s = _kos(sy, ikili, tmp_path, monkeypatch, _Flash(b"ESKI" * 32), [SAHA_BANNER])
    assert s.kod != sy.TAMAM, f"banner'la 'yakıldı ve doğrulandı' dendi: {s.ozet} / {s.adimlar}"


def test_KRITIK_TAMAM_ancak_GERI_OKUMA_ve_KART_dogrulamasiyla(yakma, tmp_path, monkeypatch):
    sy, ikili = yakma
    flash = _Flash(b"ESKI" * 32)
    s = _kos(sy, ikili, tmp_path, monkeypatch, flash, [YENI_BANNER, YENI_KIMLIK, GERCEK_ACK])
    assert s.kod == sy.TAMAM, f"{s.kod} {s.ozet} {s.adimlar}"
    assert any("geri okuma" in a and "AYNI" in a for a in s.adimlar), s.adimlar
    okumalar = [c for c in flash.cagri if "-r" in c]
    assert any(str(ikili.stat().st_size) in c for c in okumalar), f"ikili boyunda geri okuma yok: {okumalar}"


def test_KRITIK_GERI_OKUMA_tutmazsa_TAMAM_degil_ve_GERI_DONULUR(yakma, tmp_path, monkeypatch):
    sy, ikili = yakma
    flash = _Flash(b"ESKI" * 32, bozuk=True)
    s = _kos(sy, ikili, tmp_path, monkeypatch, flash, [YENI_BANNER, YENI_KIMLIK, GERCEK_ACK])
    assert s.kod == sy.GERI_OKUMA_TUTMADI, f"{s.kod} {s.ozet}"
    assert sum(1 for c in flash.cagri if "-w" in c) == 2, f"otomatik geri dönüş yazımı yok: {flash.cagri}"


def test_KRITIK_eski_firmware_HALA_kosuyorsa_UYUMSUZ_ve_GERI_DONULUR(yakma, tmp_path, monkeypatch):
    """Kart yakmadan sonra eski imajın davranışını gösterirse (CRC NACK) — yakma gerçekte tutmamış — uyumsuz sayılır."""
    sy, ikili = yakma
    flash = _Flash(b"ESKI" * 32)
    s = _kos(sy, ikili, tmp_path, monkeypatch, flash, [SAHA_BANNER, CRC_NACK, CRC_NACK, CRC_NACK])
    assert s.kod in (sy.UYUMSUZ_GERI_DONULDU, sy.GERI_DONUS_DOGRULANAMADI), f"{s.kod} {s.ozet}"
