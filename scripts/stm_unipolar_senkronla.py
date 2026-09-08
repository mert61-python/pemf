# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""stm32_pemf (kanonik) → stm32_pemf_unipolar: Core/ agacini BAYT-BAYT ayna yap.

Iki CubeIDE projesi ayni firmware'i iki SURUS KIPIYLE derler (bkz. Core/Inc/pemf_surus.h):
  stm32_pemf/          PEMF_SURUS_UNIPOLAR 0  (simetrik bipolar, IN_A+IN_B)
  stm32_pemf_unipolar/ PEMF_SURUS_UNIPOLAR 1  (tek-bacak duz surus, yalniz IN_A)

Tek kaynak kurali (2026-08-19'daki 'iki kopya sessizce ayristi' dersi): unipolar proje ELLE
DUZENLENMEZ. main.c ya da baska bir Core dosyasi kanonikte degistiginde bu betik kosturulur;
kapi (tests/test_stm_main_saglik.py) ayrismayi kirmizi yapar.

Kullanim:  python scripts/stm_unipolar_senkronla.py [--kontrol]
  --kontrol : hicbir sey yazma, farklari listele (cikis 1 = ayrisma var)
"""

from __future__ import annotations

import filecmp
import shutil
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

KOK = Path(__file__).resolve().parents[1] / "firmware"
KANONIK = KOK / "stm32_pemf" / "Core"
AYNA = KOK / "stm32_pemf_unipolar" / "Core"
# Iki projede FARKLI olmasi gereken TEK dosya (Core'a goreli).
ISTISNA = Path("Inc") / "pemf_surus.h"


def farklar() -> list[tuple[str, Path]]:
    """(neden, goreli_yol) — 'eksik' / 'farkli' / 'fazla'."""
    sonuc: list[tuple[str, Path]] = []
    kanonik_dosyalar = {p.relative_to(KANONIK) for p in KANONIK.rglob("*") if p.is_file()}
    ayna_dosyalar = {p.relative_to(AYNA) for p in AYNA.rglob("*") if p.is_file()} if AYNA.exists() else set()
    for g in sorted(kanonik_dosyalar):
        if g == ISTISNA:
            continue
        h = AYNA / g
        if not h.exists():
            sonuc.append(("eksik", g))
        elif not filecmp.cmp(KANONIK / g, h, shallow=False):
            sonuc.append(("farkli", g))
    for g in sorted(ayna_dosyalar - kanonik_dosyalar):
        sonuc.append(("fazla", g))
    return sonuc


def main() -> int:
    kontrol = "--kontrol" in sys.argv
    if not AYNA.parent.exists():
        print(f"[HATA] unipolar proje yok: {AYNA.parent} — once proje iskeleti olusturulmali")
        return 2
    f = farklar()
    if not f:
        print("ayna guncel: Core/ (pemf_surus.h haric) bayt-bayt ayni")
        return 0
    for neden, g in f:
        print(f"  {neden:6s} {g}")
    if kontrol:
        print(f"[AYRISMA] {len(f)} dosya — `python scripts/stm_unipolar_senkronla.py` ile senkronlayin")
        return 1
    for neden, g in f:
        if neden == "fazla":
            (AYNA / g).unlink()
        else:
            (AYNA / g).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(KANONIK / g, AYNA / g)
    print(f"senkronlandi: {len(f)} dosya")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
