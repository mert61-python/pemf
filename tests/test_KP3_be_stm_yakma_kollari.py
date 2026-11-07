# -*- coding: utf-8 -*-
"""KP-3 C · `utils/stm_yakma.py` (STM firmware yakma / kurtarma) kapsanmayan kolları — her test bir DAVRANIŞ iddiası. ⚠️ Ürün kodu
DEĞİŞMEDİ; GERÇEK ST-Link / CubeIDE / COM YOK: yakıcı koşucusu (`_kos`), ST-Link seçimi, yaz / geri oku / yeniden başlat ve port
adayları EN ALT katta sahtelenir.

- Yakıcı arama: PATH'te varsa o; yoksa arama köklerinde (olmayan kök atlanır) ilk `STM32_Programmer_CLI.exe`; hiçbiri yoksa None.
- Geri okuma komutu başarısızsa "geri okuma YAPILAMADI" + yakıcı çıktısının kuyruğu (yakma kanıtlanmış sayılmaz).
- Banner doğrulama: port yok → "seri port bulunamadı"; hiçbir adayda `STM_` satırı yok → "STM_READY satırı hiç görülmedi".
- Yakma akışı: `.bin` yok → BIN_YOK; yakıcı yok → YAKICI_YOK (karta DOKUNULMAZ).
- Yedekten geri dönüş (yarım yakma kurtarması): yedek yok → BIN_YOK; güvenlik denetimi patlarsa → DONANIM_MESGUL (fail-closed, yakılmaz);
  yakıcı yok → YAKICI_YOK; geri yazma başarısız / geri okuma tutmadı → GERI_DONUS_BASARISIZ (elle kurtarma iletisi); kart kimliğini
  söylemezse → GERI_DONUS_DOGRULANAMADI.
- Elle kurtarma: `.bin` yok → BIN_YOK.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from utils import stm_yakma as sy


def test_yakici_arama_path_kokler_ve_yok(monkeypatch, tmp_path):
    monkeypatch.setattr(sy.shutil, "which", lambda ad: r"C:\araclar\STM32_Programmer_CLI.exe")
    assert sy.programmer_cli() == Path(r"C:\araclar\STM32_Programmer_CLI.exe")
    monkeypatch.setattr(sy.shutil, "which", lambda ad: None)
    gomulu = tmp_path / "kok2" / "eklenti" / "bin" / "STM32_Programmer_CLI.exe"
    gomulu.parent.mkdir(parents=True)
    gomulu.write_bytes(b"MZ")
    monkeypatch.setattr(sy, "CLI_ARAMA", (tmp_path / "olmayan_kok", tmp_path / "kok2"))
    assert sy.programmer_cli() == gomulu
    monkeypatch.setattr(sy, "CLI_ARAMA", (tmp_path / "olmayan_kok",))
    assert sy.programmer_cli() is None


def test_geri_okuma_komutu_basarisizsa_kanit_yok(monkeypatch, tmp_path):
    ikili = tmp_path / "pemf.bin"
    ikili.write_bytes(b"\x00" * 64)
    monkeypatch.setattr(sy, "_baglan", lambda cli: ["-c", "port=SWD"])
    monkeypatch.setattr(sy, "_kos", lambda cli, arg, timeout=300.0: (1, "x" * 400 + "ST-LINK baglanti hatasi"))
    tamam, bilgi = sy.geri_oku(Path("cli.exe"), ikili, tmp_path / "okuma" / "geri.bin")
    assert tamam is False and bilgi.startswith("geri okuma YAPILAMADI: ") and bilgi.endswith("ST-LINK baglanti hatasi")
    assert len(bilgi) == len("geri okuma YAPILAMADI: ") + 300


def test_banner_port_yok_ve_stm_satiri_hic_gorulmedi(monkeypatch):
    monkeypatch.setattr(sy, "port_adaylari", lambda port=None: [])
    assert sy.banner_dogrula() == (None, "seri port bulunamadı — banner okunamadı", "")
    monkeypatch.setattr(sy, "port_adaylari", lambda port=None: ["COM9", "COM11"])
    monkeypatch.setattr(sy, "kart_dogrula", lambda p, sure: (["gurultu", ""], {}))
    assert sy.banner_dogrula() == (None, "STM_READY satırı hiç görülmedi (karta RESET atmayı deneyin)", "")


def test_yakma_akisi_bin_yok_ve_yakici_yok(monkeypatch, tmp_path):
    assert sy.yakma_akisi(tmp_path / "yok.bin").kod == sy.BIN_YOK
    ikili = tmp_path / "pemf.bin"
    ikili.write_bytes(b"\x01" * 32)
    monkeypatch.setattr(sy, "programmer_cli", lambda: None)
    s = sy.yakma_akisi(ikili, guvenlik_kontrolu=lambda: (True, "seans yok, bobin boşta"))
    assert s.kod == sy.YAKICI_YOK and "STM32_Programmer_CLI bulunamadı" in s.ozet


@pytest.fixture
def yedek(tmp_path):
    y = tmp_path / "onceki_firmware.bin"
    y.write_bytes(b"\x02" * 32)
    return y


def test_yedekten_geri_donus_on_kollari(monkeypatch, tmp_path, yedek):
    assert sy.yedekten_geri_don(tmp_path / "yok.bin", guvenlik_kontrolu=lambda: (True, "")).kod == sy.BIN_YOK

    def _patla():
        raise RuntimeError("seans durumu okunamadı")

    s = sy.yedekten_geri_don(yedek, guvenlik_kontrolu=_patla)
    assert s.kod == sy.DONANIM_MESGUL and "DOĞRULANAMADI (RuntimeError) — yakılmaz" in s.ozet
    monkeypatch.setattr(sy, "programmer_cli", lambda: None)
    assert sy.yedekten_geri_don(yedek, guvenlik_kontrolu=lambda: (True, "boşta")).kod == sy.YAKICI_YOK


class _Banner:
    def isaret(self):
        return 0


def _yazim_ortami(monkeypatch, *, yaz=True, geri=True, banner_ham=""):
    monkeypatch.setattr(sy, "programmer_cli", lambda: Path("cli.exe"))
    monkeypatch.setattr(sy, "stlink_sec", lambda cli, sn=None: ("SN-1", "tek prob"))
    monkeypatch.setattr(sy, "yak", lambda cli, ikili: (yaz, "" if yaz else "Error: flash yazilamadi"))
    monkeypatch.setattr(
        sy, "geri_oku", lambda cli, ikili, hedef: (geri, "geri okuma AYNI" if geri else "geri okuma FARKLI")
    )
    monkeypatch.setattr(sy, "baslat", lambda cli: (True, ""))
    monkeypatch.setattr(sy, "_banner_kaynaktan", lambda kaynak, isaret: (None, "kart sessiz", banner_ham))


def test_yedekten_geri_donus_yazma_okuma_ve_kimlik_kollari(monkeypatch, tmp_path, yedek):
    _yazim_ortami(monkeypatch, yaz=False)
    s = sy.yedekten_geri_don(yedek, guvenlik_kontrolu=lambda: (True, ""), banner_kaynagi=_Banner(), kok=tmp_path)
    assert s.kod == sy.GERI_DONUS_BASARISIZ and "GERİ YAZILAMADI" in s.ozet and "flash yazilamadi" in s.ozet
    _yazim_ortami(monkeypatch, geri=False)
    s = sy.yedekten_geri_don(yedek, guvenlik_kontrolu=lambda: (True, ""), banner_kaynagi=_Banner(), kok=tmp_path)
    assert s.kod == sy.GERI_DONUS_BASARISIZ and "geri okuma TUTMADI" in s.ozet
    _yazim_ortami(monkeypatch, banner_ham="")
    s = sy.yedekten_geri_don(yedek, guvenlik_kontrolu=lambda: (True, ""), banner_kaynagi=_Banner(), kok=tmp_path)
    assert s.kod == sy.GERI_DONUS_DOGRULANAMADI and "KİMLİĞİNİ söylemedi (kart sessiz)" in s.ozet


def test_elle_kurtarma_bin_yok(tmp_path):
    assert sy.elle_kurtarma(tmp_path / "yok.bin", beklenen_sha256="ab" * 32).kod == sy.BIN_YOK
