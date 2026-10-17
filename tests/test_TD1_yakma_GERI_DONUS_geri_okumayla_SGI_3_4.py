# Author: mertaygn, cglrgrkn
# SGI-3.4 (A3 · K1.5 · TD1-e) — ÖNCE-KIRMIZI: otomatik GERİ DÖNÜŞ "eski firmware'e geri dönüldü" demeden önce flash'ı GERİ OKUMALI.
# TD1-e ileri yolu düzeltti (yakılan ikili BAĞIMSIZ geri okumayla bayt bayt AYNI olmadan TAMAM yok — "banner yakmayı kanıtlamaz",
# tezgâh 2026-10-14). Ama `_geri_don` geri dönüş yazımını hâlâ yalnız "kart bir banner bastı mı" ile doğruluyor (`if not g_ham`):
# yedek yazımı tutmasa da (aynı arızalı flash / ST-Link) sonuç 13 / 8 + "eski firmware'e geri dönüldü" döner. Tezgâh geri dönüşü
# 2 MB geri okumayla doğruladı (kanit\H_geri_donus_okuma.txt, sha256 = ilk yedek) — ürün akışı bunu yapmıyor.
# Sahte EN ALT katta: yakıcı CLI `_kos` (flash öykünmesi: -w yazar, -r okur, -rst sayar) + `kart_dogrula` satırları.
from __future__ import annotations

from pathlib import Path

import pytest

SAHA_BANNER = "-> STM_READY: DDS v2.3 (7-ch KARMA uni=0x60 + HW_SYNC@PB1) Waiting for commands..."
YENI_BANNER = "-> STM_READY: DDS v2.3 (7-ch KARMA uni=0x60 + HW_SYNC@PB1) proto=3 pkt=121 Waiting for commands..."
YENI_KIMLIK = "-> STM_ID: DDS v2.3 (7-ch KARMA uni=0x60 + HW_SYNC@PB1) proto=3 pkt=121"
CRC_NACK = "-> STM_NACK: CRC"
GERCEK_ACK = (
    "-> STM_OK: D=0,0,0,0,0,0,0 P=0,0,0,0,0,0,0 F=100,100,100,100,100,100,100 T=0,0,0,0,0,0,0 K=96 E=0,0,0,0,0,0,0"
)


class _Flash:
    """Yakıcı CLI öykünmesi. `bozuk_yazimlar`: kaçıncı `-w` yazımlarının (1'den) TUTMADIĞI (son bayt bozulur)."""

    def __init__(self, ilk: bytes, bozuk_yazimlar: set[int]):
        self.flash = bytearray(ilk) + bytearray(b"\xff" * 64)
        self.bozuk = set(bozuk_yazimlar)
        self.yazim = 0
        self.cagri: list[list[str]] = []

    def __call__(self, _cli, argumanlar, timeout=300.0):
        self.cagri.append(list(argumanlar))
        if "-w" in argumanlar:
            self.yazim += 1
            veri = bytearray(Path(argumanlar[argumanlar.index("-w") + 1]).read_bytes())
            if self.yazim in self.bozuk:
                veri[-1] ^= 0xFF
            if len(self.flash) < len(veri):
                self.flash.extend(b"\xff" * (len(veri) - len(self.flash)))
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
    monkeypatch.setattr(sy, "UYGULAMA_ALANI_BAYT", 4096)  # 2 MB yerine küçük yedek (davranış aynı; süre kısa)
    ikili = tmp_path / "pemf.bin"
    ikili.write_bytes(b"YENI-FIRMWARE-" * 8)
    return sy, ikili


def _kos(sy, ikili, tmp_path, monkeypatch, flash: _Flash, kart_satirlari: list[str]):
    monkeypatch.setattr(sy, "_kos", flash)
    monkeypatch.setattr(sy, "kart_dogrula", lambda port, sure: (list(kart_satirlari), {}))
    monkeypatch.setattr(sy, "port_adaylari", lambda _p=None: ["COM_SGI34"])
    return sy.yakma_akisi(ikili, guvenlik_kontrolu=lambda: (True, "test"), yedek_dizin=tmp_path / "y")


def _yedek_flash_ayni_mi(flash: _Flash, s) -> bool:
    yedek = Path(s.yedek).read_bytes()
    return bytes(flash.flash[: len(yedek)]).ljust(len(yedek), b"\xff") == yedek


def test_KRITIK_GERI_OKUMA_tutmadi_ve_GERI_DONUS_de_tutmadi_GERI_DONULDU_DENMEZ(yakma, tmp_path, monkeypatch):
    """Aynı arızalı flash: yeni ikili de yedek de tutmuyor. Kart yine bir banner basıyor (sahte kart satırları)."""
    sy, ikili = yakma
    flash = _Flash(b"ESKI" * 32, bozuk_yazimlar={1, 2})
    s = _kos(sy, ikili, tmp_path, monkeypatch, flash, [SAHA_BANNER])
    assert not _yedek_flash_ayni_mi(flash, s), "aparat: geri dönüş yazımı bozulmalıydı"
    assert s.kod not in (sy.GERI_OKUMA_TUTMADI, sy.UYUMSUZ_GERI_DONULDU, sy.TAMAM), (
        f"flash yedekle AYNI DEĞİL ama sonuç {s.kod}: {s.ozet!r}"
    )
    assert "geri dönüldü" not in s.ozet, s.ozet


def test_KRITIK_UYUMSUZ_yeni_firmware_GERI_DONUS_tutmadi_GERI_DONULDU_DENMEZ(yakma, tmp_path, monkeypatch):
    """Yeni ikili tuttu (geri okuma AYNI) ama kart uyumsuz (3 CRC NACK) → geri dönüş yazımı TUTMADI → kart hâlâ uyumsuz imajda."""
    sy, ikili = yakma
    flash = _Flash(b"ESKI" * 32, bozuk_yazimlar={2})
    s = _kos(sy, ikili, tmp_path, monkeypatch, flash, [SAHA_BANNER, CRC_NACK, CRC_NACK, CRC_NACK])
    assert not _yedek_flash_ayni_mi(flash, s), "aparat: geri dönüş yazımı bozulmalıydı"
    assert s.kod not in (sy.UYUMSUZ_GERI_DONULDU, sy.TAMAM), f"flash yedekle AYNI DEĞİL ama sonuç {s.kod}: {s.ozet!r}"
    assert "geri dönüldü" not in s.ozet, s.ozet


def test_KARSIT_GERI_DONUS_tuttu_GERI_DONULDU_der(yakma, tmp_path, monkeypatch):
    sy, ikili = yakma
    flash = _Flash(b"ESKI" * 32, bozuk_yazimlar={1})
    s = _kos(sy, ikili, tmp_path, monkeypatch, flash, [SAHA_BANNER])
    assert _yedek_flash_ayni_mi(flash, s)
    assert s.kod == sy.GERI_OKUMA_TUTMADI and "geri dönüldü" in s.ozet, (s.kod, s.ozet)


def test_KARSIT_UYUMSUZ_GERI_DONUS_tuttu_8(yakma, tmp_path, monkeypatch):
    sy, ikili = yakma
    flash = _Flash(b"ESKI" * 32, bozuk_yazimlar=set())
    s = _kos(sy, ikili, tmp_path, monkeypatch, flash, [SAHA_BANNER, CRC_NACK, CRC_NACK, CRC_NACK])
    assert s.kod == sy.UYUMSUZ_GERI_DONULDU, (s.kod, s.ozet)


def test_KARSIT_TAMAM_yolu_DEGISMEDI(yakma, tmp_path, monkeypatch):
    sy, ikili = yakma
    flash = _Flash(b"ESKI" * 32, bozuk_yazimlar=set())
    s = _kos(sy, ikili, tmp_path, monkeypatch, flash, [YENI_BANNER, YENI_KIMLIK, GERCEK_ACK])
    assert s.kod == sy.TAMAM, (s.kod, s.ozet)


def _okumadan_sonra_rst_var_mi(flash: _Flash, kacinci_okuma: int) -> bool:
    """`kacinci_okuma`ncı (1'den; -1 = son) SWD geri okumasından SONRA yalnız-yeniden-başlatma (`-c port=SWD -rst`) çağrısı var mı?
    (SWD okuması çekirdeği durdurmuş olabilir — kart doğrulaması ancak yeniden başlatmadan sonra anlamlı; TD1-e.)"""
    okumalar = [i for i, c in enumerate(flash.cagri) if "-r" in c]
    i = okumalar[kacinci_okuma if kacinci_okuma < 0 else kacinci_okuma - 1]
    return any(c == ["-c", "port=SWD", "-rst"] for c in flash.cagri[i + 1 :])


def test_KRITIK_GERI_DONUS_geri_okumasindan_SONRA_kart_YENIDEN_baslatilir(yakma, tmp_path, monkeypatch):
    sy, ikili = yakma
    flash = _Flash(b"ESKI" * 32, bozuk_yazimlar={1})
    s = _kos(sy, ikili, tmp_path, monkeypatch, flash, [SAHA_BANNER])
    assert s.kod == sy.GERI_OKUMA_TUTMADI, (s.kod, s.ozet)
    assert _okumadan_sonra_rst_var_mi(flash, -1), f"geri dönüş geri okumasından sonra -rst yok: {flash.cagri}"


def test_KRITIK_ILERI_yol_geri_okumasindan_SONRA_kart_YENIDEN_baslatilir(yakma, tmp_path, monkeypatch):
    sy, ikili = yakma
    flash = _Flash(b"ESKI" * 32, bozuk_yazimlar=set())
    s = _kos(sy, ikili, tmp_path, monkeypatch, flash, [YENI_BANNER, YENI_KIMLIK, GERCEK_ACK])
    assert s.kod == sy.TAMAM, (s.kod, s.ozet)
    # 1. okuma = yakma öncesi yedek, 2. okuma = yazılan ikilinin bağımsız geri okuması
    assert _okumadan_sonra_rst_var_mi(flash, 2), f"ileri yol geri okumasından sonra -rst yok: {flash.cagri}"
