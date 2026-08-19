# Author: mertaygn, cglrgrkn
"""STM main.c TEK KAYNAK SAĞLIK KAPISI — CubeMX ezmesi + build-çıktısı sızıntısı.

2026-08-19: `firmware/main.c` (kök kopya) SİLİNDİ. Artık TEK KAYNAK, derlemenin gerçekten
okuduğu proje içindeki dosyadır: `firmware/stm32_pemf/Core/Src/main.c`. Eski
`test_stm_main_tek_kaynak.py` iki kopyanın bayt-eşitliğini kilitliyordu; tek dosya kalınca
o parite anlamsız — ama iki gerçek risk DURUYOR ve bu kapı onları koruyor:

  1. **CubeMX "Generate Code" ezmesi**: `PEMF.ioc` Device Configuration'da açılıp kod
     üretilirse main.c iskeletle EZİLİR (dosya elle yazılmış — USER CODE işaretçisi YOK,
     1500+ satır, denetim düzeltmeleri dahil). İskelet ~450 satır ve USER CODE bloklarıyla
     gelir → bu kapı yakalar.
  2. **Build çıktısı sızıntısı**: CubeIDE `Debug/` (31 MB .elf/.o/.map) depoya girmemeli.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
MAIN = KOK / "firmware" / "stm32_pemf" / "Core" / "Src" / "main.c"


def test_KRITIK_tek_kaynak_main_c_YERINDE():
    """Tek kaynak var ve elle yazılmış denetim-düzeltmeli sürüm (iskelet DEĞİL)."""
    assert MAIN.exists(), f"STM tek kaynağı yok: {MAIN}"
    metin = MAIN.read_text(encoding="utf-8", errors="replace")

    assert len(metin.splitlines()) > 1000, (
        f"main.c yalnızca {len(metin.splitlines())} satır — CubeMX 'Generate Code' iskeletiyle "
        "EZİLMİŞ olabilir (elle yazılmış sürüm 1500+ satır)."
    )
    assert "USER CODE BEGIN" not in metin, (
        "main.c'de 'USER CODE' işaretçileri belirdi = CubeMX iskeletine dönmüş. Elle yazılmış "
        "firmware 'Generate Code' ile EZİLDİ. `.ioc`'tan kod üretmeyin; üretildiyse geri alın."
    )
    assert "PEMF_ForceAllCoilOutputsLow" in metin, (
        "güvenlik fonksiyonu PEMF_ForceAllCoilOutputsLow kaybolmuş — bu main.c denetim düzeltmeli sürüm DEĞİL."
    )


def test_KRITIK_eski_kok_kopya_GERI_GELMEDI():
    """`firmware/main.c` (silinen ikinci kopya) geri eklenmemeli — 'tek el' kararı."""
    eski = KOK / "firmware" / "main.c"
    assert not eski.exists(), (
        "firmware/main.c geri gelmiş — 2026-08-19'da SİLİNDİ (tek kaynak = stm32_pemf içindeki "
        "proje dosyası). İki kopya sessiz ayrışma üretir; kanonik yol "
        "firmware/stm32_pemf/Core/Src/main.c'dir."
    )


def test_KRITIK_build_ciktisi_Debug_izlenmiyor():
    """CubeIDE Debug/ çıktısı (31 MB .elf/.o/.map) depoya sızmamalı."""
    ch = subprocess.run(
        ["git", "ls-files", "--", "firmware/stm32_pemf/Debug"],
        cwd=KOK,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if ch.returncode != 0:
        pytest.skip("git deposu değil")
    assert not ch.stdout.strip(), (
        f"Debug/ build çıktısı izleniyor: {ch.stdout.splitlines()[:3]} — .gitignore kuralı "
        "(firmware/stm32_pemf/Debug/) düşmüş olabilir."
    )
    # karşıt-kanıt: proje kaynağı GERÇEKTEN izleniyor (kural fazla geniş değil)
    ch2 = subprocess.run(
        ["git", "ls-files", "--", "firmware/stm32_pemf"],
        cwd=KOK,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert len(ch2.stdout.splitlines()) > 90, (
        "stm32_pemf kaynağı izlenmiyor/eksik — gitignore kuralı projeyi de yutmuş olabilir"
    )
