# -*- coding: utf-8 -*-
"""KP-3 C · `servers/firmware_manager._firmware_uygula` — Y80 kaydı (`son_yakma.json`) YAZILAMAZSA (DAVRANIŞ iddiası):
açılış denetimi DÜŞMEZ, sonuç yine dürüst ("yakıldı ama kart hedef sürümü bildirmedi", uygulanmadı), günlüğe "aynı ikili sonraki açılışta
yeniden denenebilir" yazılır ve kayıt dosyası oluşmaz. ⚠️ Ürün kodu (firmware yakma) DEĞİŞMEDİ; yalnız test.

AYGIT: `test_firmware_otomatik_ONKOSULLAR_Y80_Y81_Y82_LN.py` ile aynı — sahte EN ALT katta: ağ (`update_manager._pinli_ac`) ve
yakıcı CLI (`stm_yakma._kos`, sahte STM32F429 belleği). Arıza: `_kayit_yaz` YALNIZ `son_yakma.json` için OSError (disk dolu).
"""

from __future__ import annotations

import hashlib
import importlib
import io
import json
import logging
from pathlib import Path
from types import SimpleNamespace

import pytest
from stlink_sahte import liste as stlink_liste

KURAL = [{"clientMin": "1.9.50", "clientMax": "", "firmwareMin": "2.4", "firmwareMax": ""}]
BANNER = "-> STM_READY: DDS v{} (7-ch KARMA uni=0x60 + HW_SYNC@PB1) proto=3 pkt=121 Waiting for commands..."


class _SahteKart:
    def __init__(self, eski: bytes = b"ESKI-FW-" * 64):
        self.flash = bytearray(eski)
        self.yazilan: list[str] = []

    def kos(self, cli, argumanlar, timeout=300.0):
        a = list(argumanlar)
        if a[:1] == ["-l"]:
            return 0, stlink_liste()
        if "-w" in a:
            ikili = Path(a[a.index("-w") + 1])
            veri = ikili.read_bytes()
            self.flash[: len(veri)] = veri
            self.yazilan.append(ikili.name)
            return 0, "sahte: yazıldı + doğrulandı"
        if "-r" in a:
            i = a.index("-r")
            boy, hedef = int(a[i + 2]), Path(a[i + 3])
            hedef.parent.mkdir(parents=True, exist_ok=True)
            hedef.write_bytes(bytes(self.flash[:boy]))
            return 0, "sahte: okundu"
        return 0, "sahte: -rst"


@pytest.fixture()
def ortam(monkeypatch, tmp_path):
    import servers.update_manager as um
    import utils.stm_yakma as sy

    fm = importlib.reload(importlib.import_module("servers.firmware_manager"))
    monkeypatch.setattr(um, "get_current_version", lambda: "1.9.51")
    kart = _SahteKart()
    monkeypatch.setattr(sy, "_kos", kart.kos)
    monkeypatch.setattr(sy, "programmer_cli", lambda: Path(r"C:\sahte\STM32_Programmer_CLI.exe"))
    monkeypatch.setattr(sy, "BANNER_SURESI", 0.05)
    monkeypatch.setattr(fm, "_surec_ici_guvenlik_kontrolu", lambda: (True, "sahte: seans yok, bobin sürülmüyor"))
    ikili = b"YENI-FW-2.4-" * 50
    fw_url = f"https://github.com/{um._UPDATE_REPO}/releases/download/fw-test/pemf_fw.bin"

    class _Yanit(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def _pinli_ac(url, timeout, headers=None):
        if url == fm.UYUM_URL:
            veri = {
                "firmware": {"stm32": {"version": "2.4", "url": fw_url, "sha256": hashlib.sha256(ikili).hexdigest()}},
                "uyumluluk": KURAL,
            }
            return _Yanit(json.dumps(veri).encode("utf-8"))
        if url == fw_url:
            return _Yanit(ikili)
        raise AssertionError(f"beklenmeyen ağ isteği: {url}")

    monkeypatch.setattr(um, "_pinli_ac", _pinli_ac)

    def banner_kaynagi():
        # Kart yakmadan sonra da 2.3 bildirir → hedefe ulaşılmadı → Y80 kaydı yazılmaya çalışılır.
        return sy.BannerKaynagi(isaret=lambda: 1, bekle=lambda isaret, sure: BANNER.format("2.3"))

    veri_koku = Path(__import__("utils.path_utils", fromlist=["x"]).get_app_data_directory())
    yield SimpleNamespace(fm=fm, kart=kart, banner=banner_kaynagi, kok=veri_koku / "firmware_yedek")
    importlib.reload(importlib.import_module("servers.firmware_manager"))


def test_y80_kaydi_yazilamazsa_acilis_dusmez_sonuc_durust_gunluk_soyler(ortam, monkeypatch, caplog):
    gercek = ortam.fm._kayit_yaz

    def _y80_yazilamaz(kok, ad, veri):
        if ad == ortam.fm.SON_YAKMA_DOSYASI:
            raise OSError(28, "disk dolu (sahte)")
        return gercek(kok, ad, veri)

    monkeypatch.setattr(ortam.fm, "_kayit_yaz", _y80_yazilamaz)
    with caplog.at_level(logging.ERROR, logger=ortam.fm.logger.name):
        d = ortam.fm.acilis_denetimi(firmware_surum="2.3", stm_bagli=True, uygula=True, banner_kaynagi=ortam.banner())
    assert len(ortam.kart.yazilan) == 1, f"aparat: karta yazılmadı {ortam.kart.yazilan}"
    assert d["uygulandi"] is False and "hedef sürümü bildirmedi" in d["hata"], d
    assert any("YAZILAMADI" in r.getMessage() and "yeniden denenebilir" in r.getMessage() for r in caplog.records), [
        r.getMessage() for r in caplog.records
    ]
    assert not (ortam.kok / "son_yakma.json").exists()
