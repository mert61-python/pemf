# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""CI ATLANAN DEFTERİ KAPISI (CT1 c · istem 66 · Y324) — sessiz atlama biter.

NEDEN: CI yeşil bitse de yüzlerce test "eser yok" diye ATLIYORDU (63 YS1: 226) ve hiçbiri görünmüyordu. Artık CI'da atlanan HER test
`tests/ci_atlanan_defteri.json`'da gerekçesiyle yazılı olmalı; defter yalnız iki sınıfı kabul eder:
  Y — yalnız yayın makinesinde bulunan eser (kurucu EXE, APK, base-deps.zip, sevk ağacı …): CI'da gerekçeli atlar; Y30'da
      (`PEMF_YAYIN_MAKINESI=1`, `tests/yayin_makinesi_kapisi.py`) atlarsa KIRMIZI — yayından önce mutlaka koşar.
  P — platform / ortam (CI koşucusunda var olamayan: donanım, oturum belirteci, SYSTEM kasası, alt-süreç tasarımı): atlama kalır.
Model ağırlığı / test girdisi eksikliği (M) ya da başka neden (D) deftere GİREMEZ: M CI model paketine girer, D düzeltilir.

KURALLAR (her biri KIRMIZI): defterde olmayan atlama · M / D / bilinmeyen sınıf ya da gerekçesiz (< 20 karakter) kayıt · atlama nedeni
model / eser yokluğu olan kayıt (M kılıklı Y / P) · koşuda ATLAMAYAN kayıt (geçti ya da hiç yok = BAYAT; `--kismi` yalnız koşuda HİÇ
olmayanı affeder — değişen alan kümesi koşuları için; `"ortamda_kosabilir": true` taşıyan P kaydı — koşucuda var olamayan
ama geliştirici makinesinde bulunabilen koşul, ör. üyelikli yerel grup — atlamadığında bayat sayılmaz).
Kimlik = junit `classname::name` (toplama atlaması: yalnız modül adı). Kullanım:
    python scripts/ci_atlanan_kapisi.py pytest-junit.xml [--defter tests/ci_atlanan_defteri.json] [--kismi]
ÇIKIŞ: 0 = tamam · 1 = kural ihlali · 2 = junit / defter okunamadı ya da junit boş (kör kapı).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
DEFTER = KOK / "tests" / "ci_atlanan_defteri.json"
SINIFLAR = {"Y": "yalnız yayın makinesi eseri", "P": "platform / ortam"}
#: Atlama nedeni bunlardan birini taşıyorsa eksik olan MODEL / TEST GİRDİSİDİR (M) → defter onu saklayamaz, CI paketine girer.
M_DESENI = re.compile(
    r"ağırlı[kğ]|ai_models|PEMF_AI_MODELS_DIR|PEMF_AI_Test_Girdileri|\.onnx\b|\.pt\b|\.pkl\b|PT ikiz|model[ _]?a[gğ]ırl|"
    r"ürün çözücüsünde yok|eser yok \[|celldetection",
    re.I,
)


def _kimlik(tc: ET.Element) -> str:
    c, n = tc.get("classname", ""), tc.get("name", "")
    return f"{c}::{n}" if c else n


def _junit_oku(yol: Path) -> dict[str, str | None]:
    """kimlik → atlama nedeni (atlamadıysa None)."""
    sonuc: dict[str, str | None] = {}
    for tc in ET.parse(yol).getroot().iter("testcase"):
        sk = tc.find("skipped")
        sonuc[_kimlik(tc)] = None if sk is None else (sk.get("message") or sk.text or "").strip()
    return sonuc


def denetle(junit: Path, defter: Path = DEFTER, kismi: bool = False) -> int:
    try:
        kosu = _junit_oku(junit)
    except (OSError, ET.ParseError) as e:
        print(f"!!! junit okunamadı ({junit}): {type(e).__name__}: {e}")
        return 2
    if not kosu:
        print(f"!!! junit BOŞ ({junit}) — kapı kör; test koşmadı mı?")
        return 2
    kayitlar = json.loads(defter.read_text(encoding="utf-8"))["kayitlar"]
    hatalar: list[str] = []
    for k in kayitlar:
        if k.get("sinif") not in SINIFLAR:
            hatalar.append(f"geçersiz sınıf {k.get('sinif')!r} (yalnız Y / P; M / D deftere GİREMEZ): {k.get('test')}")
        if len(str(k.get("gerekce", "")).strip()) < 20:
            hatalar.append(f"gerekçe yok / çok kısa: {k.get('test')}")
    defterde = {k.get("test"): k for k in kayitlar}
    atlanan = {t: n for t, n in kosu.items() if n is not None}
    for t, neden in sorted(atlanan.items()):
        if t not in defterde:
            hatalar.append(f"defterde OLMAYAN atlama: {t} — {neden[:200]}")
        elif M_DESENI.search(neden):
            hatalar.append(
                f"M sınıfı (model / test girdisi) atlaması defterle SAKLANAMAZ — CI paketine girmeli: {t} — {neden[:200]}"
            )
    for t, k in defterde.items():
        if t in atlanan or k.get(
            "ortamda_kosabilir"
        ):  # P (ORTAM): bazı makinelerde koşar (ör. üyelikli yerel grup) — bayat sayılmaz
            continue
        if t in kosu:
            hatalar.append(f"BAYAT kayıt: {t} bu koşuda ATLAMADI (geçti / düştü) — defterden çıkarın")
        elif not kismi:
            hatalar.append(f"BAYAT kayıt: {t} bu koşuda YOK (silindi / yeniden adlandırıldı) — defterden çıkarın")
    say = {s: sum(1 for t in atlanan if defterde.get(t, {}).get("sinif") == s) for s in SINIFLAR}
    print(
        f"atlanan {len(atlanan)} / {len(kosu)} test · defter {len(kayitlar)} kayıt · "
        + " ".join(f"{s}={n}" for s, n in say.items())
    )
    if hatalar:
        print(f"!!! ATLANAN DEFTERİ KAPISI KIRMIZI — {len(hatalar)} ihlal:")
        for h in hatalar:
            print("  " + h)
        return 1
    print("atlanan defteri kapısı: tamam (her atlama defterde, gerekçeli, M / D yok)")
    return 0


def _konsol_utf8(akislar=None) -> None:
    """windows-latest konsolu cp1252 (YS1a dersi): Türkçe ileti yazımı düşmesin — yazılamayan karakter '?' olur."""
    for akis in akislar or (sys.stdout, sys.stderr):
        if hasattr(akis, "reconfigure"):
            akis.reconfigure(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    _konsol_utf8()
    ap = argparse.ArgumentParser(description="CI atlanan defteri kapısı (CT1 c · Y324)")
    ap.add_argument("junit", type=Path)
    ap.add_argument("--defter", type=Path, default=DEFTER)
    ap.add_argument("--kismi", action="store_true", help="kısmi koşu: koşuda hiç olmayan kaydı bayat sayma")
    a = ap.parse_args(argv)
    try:
        return denetle(a.junit, a.defter, a.kismi)
    except (OSError, ValueError, KeyError) as e:
        print(f"!!! defter okunamadı ({a.defter}): {type(e).__name__}: {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
