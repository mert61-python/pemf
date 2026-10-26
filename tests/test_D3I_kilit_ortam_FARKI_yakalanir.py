# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D3I-A2.7 (D3.41 · D3.44) — `scripts/kilit_denetimi.py --ortam` (derleme betiğinde PyInstaller ÖNCESİ "fark → Die") KIRMIZI KOLU.

ÖLÇÜLEN BOŞLUK: `tests/test_D3_41_…`teki tek ortam testi gerçek yorumlayıcının `ortam(...) == []` olduğunu ölçer — yokluk ölçütlü kapı:
`ortam()`ın sürüm karşılaştırması `if False:` yapılınca (fark HİÇ raporlanmaz) D3.41 kümesi YEŞİL kalıyordu (ölçüldü). Bu dosya karşıtı
ekler: kurulu bir dağıtımın kilitte FARKLI sürümü ve kurulu OLMAYAN dağıtım satır satır raporlanır; PEP 440 eşdeğer yazımlar (sahadaki
`thop` `0.1.1.post2209072238` ↔ `0.1.1-2209072238`) fark SAYILMAZ (yanlış pozitif → derleme boşuna durur). Ürün DEĞİŞMEZ.
"""

from __future__ import annotations

import importlib.metadata as md
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK / "scripts"))
import kilit_denetimi as kd  # noqa: E402


def test_KARSIT_D3I_A2_7_ortam_SURUM_farkini_ve_KURULU_OLMAYANI_raporlar():
    """MUTASYON: `ortam()` sürüm karşılaştırması `if False:` → KIRMIZI; kurulu-değil dalı raporlamaz → KIRMIZI."""
    kurulu = md.version("packaging")
    hata = kd.ortam({"packaging": kurulu}, {"packaging": kurulu + ".post999", "d3i-a2-7-olmayan-dagitim": "1.0"})
    assert any("`packaging` kurulu" in h and "≠ kilit" in h for h in hata), hata
    assert any("d3i-a2-7-olmayan-dagitim" in h and "KURULU DEĞİL" in h for h in hata), hata
    assert not any("requirements.txt" in h for h in hata), f"aynı sürüm fark sayıldı: {hata}"


def test_KARSIT_D3I_A2_7_PEP440_esdeger_yazim_FARK_SAYILMAZ_gercek_fark_SAYILIR():
    """`thop` kilitte `0.1.1-2209072238`, kurulu `0.1.1.post2209072238` (PEP 440 aynı sürüm). MUTASYON: `ayni` düz metin karşılaştırması
    → KIRMIZI (derleme yanlış pozitifle durur)."""
    assert kd.ayni("0.1.1.post2209072238", "0.1.1-2209072238")
    assert kd.ayni("2.1.2+cpu", "2.1.2+cpu")
    assert not kd.ayni("2.1.2+cpu", "2.1.2")
    assert not kd.ayni("1.26.4", "1.26.3")
