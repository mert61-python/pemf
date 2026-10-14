# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D1.113 · B-4.8 — yakmadan önceki YEDEK, yeni ikilinin boyunda değil kartın UYGULAMA ALANI boyunda okunur.

ÖLÇÜLEN KUSUR: `stm_yakma.yakma_akisi` yedeği `yedek_al(cli, yedek, ikili.stat().st_size)` ile — YENİ ikilinin boyunda —
okuyordu (1-H D1.108 önce-kırmızısında görüldü: `-r 0x08000000 704`). Yeni ikili eskisinden küçükse yedek ESKİ
firmware'in KESİK bir kopyasıdır; uyumsuz banner'da geri dönüş bu kesik kopyayı yazar → kart açılmayabilir (ST-Link ile
elle kurtarma). "Geri dönüşü olmayan işlem YOK" değişmezi boşalıyordu.

KAPI: GERÇEK `yakma_akisi` (SAHTE yakıcı `_kos`, gerçek yakıcı/ST-Link YOK) 1234 baytlık yeni ikiliyle → yedek okuma
argümanı `UYGULAMA_ALANI_BAYT`; bu sabit, firmware'in linker betiğindeki FLASH bölgesinin boyuna (STM32F429ZI: 2048K)
EŞİT — beklenen değer mutasyon hedefinden (stm_yakma) değil linker betiğinden okunur. Kartın gerçek uygulama alanı ve
kesik yedekle geri dönüşte açılış: TEZGÂH (Oturum 13).
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
LINKER = KOK / "firmware" / "stm32_pemf" / "STM32F429ZITX_FLASH.ld"


def _linker_flash_bayt() -> int:
    m = re.search(
        r"^\s*FLASH\s*\(rx\)\s*:\s*ORIGIN\s*=\s*0x8000000\s*,\s*LENGTH\s*=\s*(\d+)K\s*$", LINKER.read_text(), re.M
    )
    assert m, "ön koşul: linker betiğinde FLASH bölgesi (ORIGIN 0x8000000) bulunamadı — çapa bayat"
    return int(m.group(1)) * 1024


def test_KRITIK_yedek_UYGULAMA_ALANI_boyunda_okunur_yeni_ikili_boyunda_DEGIL(monkeypatch, tmp_path):
    sy = importlib.import_module("utils.stm_yakma")
    ikili = tmp_path / "pemf.bin"
    ikili.write_bytes(b"\x5a" * 1234)
    okuma: list[str] = []

    def _sahte_kos(cli, argumanlar, timeout=300.0):
        if "-r" in argumanlar:
            okuma.append(argumanlar[argumanlar.index("-r") + 2])
            Path(argumanlar[-1]).parent.mkdir(parents=True, exist_ok=True)
            Path(argumanlar[-1]).write_bytes(b"ESKI")
        return 0, ""

    monkeypatch.setattr(sy, "programmer_cli", lambda: Path("sahte_cli.exe"))
    monkeypatch.setattr(sy, "_kos", _sahte_kos)
    # TD1-e: yakma sonrası geri okuma + yeniden başlatma BU kapının konusu değil (başarılı — gerçek çıktı uzayından); gerçek akış EN ALT katta: test_TD1_yakma_ve_kimlik_betigi_KANITLA (flash öykünmesi).
    monkeypatch.setattr(sy, "geri_oku", lambda _c, _i, _h: (True, "geri okuma: (aparat) bayt bayt AYNI"))
    monkeypatch.setattr(sy, "baslat", lambda _c: (True, ""))
    monkeypatch.setattr(sy, "banner_dogrula", lambda *a, **k: (True, "uyumlu", "-> STM_READY: 2.4.0 (7-ch ...)"))
    monkeypatch.setattr(sy.time, "sleep", lambda _s: None)
    s = sy.yakma_akisi(ikili, guvenlik_kontrolu=lambda: (True, "t"), yedek_dizin=tmp_path / "y")
    assert s.kod == sy.TAMAM, s
    beklenen = _linker_flash_bayt()
    assert okuma == [str(beklenen)], (
        f"yedek {okuma} bayt okundu — kartın uygulama alanı {beklenen} bayt (linker FLASH); yeni ikilinin boyunda (1234) "
        "okunan yedek ESKİ firmware'in KESİK kopyasıdır, geri dönüş kartı açılmaz bırakabilir (B-4.8)"
    )


def test_KRITIK_UYGULAMA_ALANI_sabiti_linker_FLASH_boyuna_ESIT():
    sy = importlib.import_module("utils.stm_yakma")
    assert getattr(sy, "UYGULAMA_ALANI_BAYT", None) == _linker_flash_bayt(), (
        f"stm_yakma.UYGULAMA_ALANI_BAYT={getattr(sy, 'UYGULAMA_ALANI_BAYT', None)} ≠ linker FLASH {_linker_flash_bayt()}"
    )
