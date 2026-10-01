# Author: mertaygn, cglrgrkn
"""`c_soy` önişlemciyle ÖLÜ kodu da soyar (1-B bağımsız inceleme i3, D1.23 sınıfı).

Yorumu soyulmuş metinde arayan kapılar (D1.23 / D1.24 / D1.48 / D1.49 …) `#if 0 … #endif` içine alınmış kodu
CANLI sayıyordu: Error_Handler'daki bobin kesme çağrısı `#if 0` içine alınınca 29 STM kapı dosyası 300/300 YEŞİLDİ.
"""

from __future__ import annotations

from pathlib import Path

from c_soyucu import c_soy

KOK = Path(__file__).resolve().parents[1]


def test_KRITIK_if0_icindeki_kod_SOYULUR_else_dali_KALIR():
    src = "a();\n#if 0\nb();\n#else\nc();\n#endif\nd();\n"
    soy = c_soy(src)
    assert "b();" not in soy and all(x in soy for x in ("a();", "c();", "d();")), soy
    assert len(soy) == len(src) and soy.count("\n") == src.count("\n"), "uzunluk/satır yapısı korunmalı"


def test_KRITIK_ic_ice_ve_parantezli_if0():
    src = "#if (0)\n#ifdef X\nx();\n#else\ny();\n#endif\nz();\n#endif\nw();\n"
    soy = c_soy(src)
    assert not any(t in soy for t in ("x();", "y();", "z();")) and "w();" in soy, soy


def test_KARSIT_canli_kosullu_kod_KORUNUR():
    src = "#if defined(STM32)\nk();\n#else\nl();\n#endif\n#ifdef PEMF\nm();\n#endif\n#if 1\nn();\n#endif\n"
    soy = c_soy(src)
    assert all(t in soy for t in ("k();", "l();", "m();", "n();")), soy


def test_KARSIT_firmware_kaynaklarinda_if0_YOK_ve_soyma_KAYIPSIZ():
    """Bugün depo firmware'inde `#if 0` yok: soyucunun bu kolu mevcut kapıların okuduğu metni DEĞİŞTİRMEZ."""
    import re

    for p in (KOK / "firmware").rglob("*"):
        if p.suffix not in (".c", ".h", ".cpp", ".ino"):
            continue
        t = p.read_text(encoding="utf-8", errors="replace")
        assert not re.search(r"^\s*#\s*if\s+\(?\s*0\s*\)?\s*$", t, re.M), f"{p}: `#if 0` var — kapı kapsamı değişir"
