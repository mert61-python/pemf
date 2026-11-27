# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""KAPSAM TABANI KAPISI (CT1 f-2 / g · istem 66 · Y311 / Y325 / Y326) — Python paketlerinin toplamı tabanın ALTINA inemez.

Taban `tests/kapsam_tabani.json`'da (makinece okunur; insan okur tablo `DENETIM\\KAPSAM-TABANI.md`). Bu betik pytest-cov'un bıraktığı
birleşik `.coverage` verisinden iki Python paketini ölçer:
  sunucu — `pyproject.toml [tool.coverage]` raporu AYNEN (ai_hub `report.omit` ile toplam DIŞINDA; `fail_under` = taban)
  ai_hub — Y326: ürün yolu ÖLÇÜLÜR (`run.source`'ta), kendi tabanı var; dışarıdakiler `run.omit`te gerekçeli (JSON `ai_hub.disarida`)
ve fark kapsamı kapısının (`scripts/fark_kapsami.py --covjson`) okuyacağı birleşik JSON raporunu (sunucu + ai_hub; yollar depo
köküne göre TEK anlamlı — Cobertura XML paket köküne göre yazar, `__init__.py` adları çakışır) yazar.
Jest / vitest eşikleri kendi yapılandırmalarında JSON'dan okunur; cargo eşiği iş akışında (`--fail-under-lines`) — tutarlılık:
tests/test_CT1f_kapsam_tabani_KILIDI.py.
Kullanım: python scripts/kapsam_tabani_kapisi.py [--veri .coverage] [--json coverage.json]
ÇIKIŞ: 0 = her paket ≥ taban · 1 = taban altı · 2 = veri / taban okunamadı.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
TABAN = KOK / "tests" / "kapsam_tabani.json"
AI_HUB_DESENI = "*/ai_hub/*"


def taban_oku(yol: Path = TABAN) -> dict:
    return json.loads(yol.read_text(encoding="utf-8"))["paketler"]


def olc(veri: Path, birlesik: Path | None, ayar: Path = KOK / "pyproject.toml") -> dict[str, float]:
    """`.coverage` → {"sunucu": %, "ai_hub": %}; `birlesik` verilirse sunucu + ai_hub birleşik JSON raporunu yazar."""
    import coverage

    cov = coverage.Coverage(data_file=str(veri), config_file=str(ayar))
    cov.load()
    with tempfile.TemporaryDirectory() as g:
        sunucu = cov.json_report(outfile=str(Path(g) / "s.json"))
        # omit verilince yapılandırmanın report.omit'i (ai_hub) YERİNE geçer → yalnız ai_hub raporlanır
        ai_hub = cov.json_report(outfile=str(Path(g) / "a.json"), include=[AI_HUB_DESENI], omit=["*/__pycache__/*"])
    if birlesik is not None:
        cov.json_report(outfile=str(birlesik), omit=["*/__pycache__/*", "tests/*"])
    return {"sunucu": float(sunucu), "ai_hub": float(ai_hub)}


def karsilastir(olcum: dict[str, float], taban: dict) -> list[str]:
    """Taban altı paketlerin iletileri (boş = tamam). %100 taban kesin 100 ister (yuvarlama payı yok); diğerleri 2 basamakta."""
    sorun = []
    for ad, deger in olcum.items():
        t = float(taban[ad]["satir"])
        dusuk = deger < 100.0 if t >= 100.0 else round(deger, 2) < t
        if dusuk:
            sorun.append(
                f"{ad}: ölçülen %{deger:.2f} < taban %{t:.2f} — test ekleyerek kapatın (eşik DÜŞÜRÜLMEZ, Y311)"
            )
    return sorun


def _konsol_utf8(akislar=None) -> None:
    for akis in akislar or (sys.stdout, sys.stderr):
        if hasattr(akis, "reconfigure"):
            akis.reconfigure(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    _konsol_utf8()
    ap = argparse.ArgumentParser(description="Kapsam tabanı kapısı (Python paketleri)")
    ap.add_argument("--veri", type=Path, default=Path(".coverage"))
    ap.add_argument("--json", type=Path, dest="birlesik")
    ap.add_argument("--taban", type=Path, default=TABAN)
    a = ap.parse_args(argv)
    if not a.veri.is_file():
        print(f"!!! kapsam verisi yok: {a.veri} — pytest --cov koştu mu? (kapı kör)")
        return 2
    try:
        taban = taban_oku(a.taban)
        olcum = olc(a.veri, a.birlesik)
    except Exception as e:  # noqa: BLE001 — okunamayan veri / taban = kör kapı, ayrıntıyla
        print(f"!!! kapsam verisi / taban okunamadı: {type(e).__name__}: {e}")
        return 2
    for ad, d in olcum.items():
        print(f"{ad}: %{d:.2f} (taban %{float(taban[ad]['satir']):.2f})")
    sorun = karsilastir(olcum, taban)
    if sorun:
        print("!!! KAPSAM TABANI KAPISI KIRMIZI:\n  " + "\n  ".join(sorun))
        return 1
    print("kapsam tabanı kapısı: tamam (her Python paketi ≥ taban)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
