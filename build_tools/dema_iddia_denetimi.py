# Author: mertaygn, cglrgrkn
"""D1.91 · B-7.29/B-7.30 · A-37 (sahip) — DEMA simülatörü TANITIM/EĞİTİM aracıdır; dayanaksız iddia taşıyamaz.

Sahip kararı A-37: "tanıtım/eğitim amaçlıdır, cihaz davranışını temsil etmez" etiketi zorunlu; dayanaksız "ISO 13485"
iddiası ve fiziksel modeli olmayan "Canlı" rozetli V/m E-alan göstergesi kalkar; dizin SİLİNMEZ.

Bu modül hem kapı testinin (kaynak) hem derleme betiğinin (sevk edilen `dist`) ORTAK ölçütüdür: `dist` depoda takipsizdir
(yerelde derlenir) — kaynak düzeltilse de bayat bir `dist` eski iddiaları pakete taşırdı. Spec, gömmeden önce bunu çağırır.
"""

from __future__ import annotations

import re
from pathlib import Path

#: (ad, desen) — sevk edilen metinde GEÇMEMELİ.
YASAKLI_IDDIALAR: tuple[tuple[str, re.Pattern], ...] = (
    ("ISO 13485 uyumluluk iddiası", re.compile(r"ISO\s*13485", re.IGNORECASE)),
    ("'tek DEMA cihazı' iddiası", re.compile(r"\btek\s+DEMA\b", re.IGNORECASE)),
    ("V/m E-alan göstergesi (fiziksel model yok)", re.compile(r"V/m")),
    ("'Canlı' rozeti (canlı ölçüm yok)", re.compile(r"Canl[ıi]\b")),
)
#: Sevk edilen simülatörde BULUNMASI ZORUNLU etiket (A-37 metni).
ZORUNLU_ETIKET = "cihaz davranışını temsil etmez"

_METIN_UZANTILARI = {".html", ".js", ".mjs", ".css", ".json", ".tsx", ".ts"}


def metin_dosyalari(dizin: Path) -> list[Path]:
    return sorted(p for p in Path(dizin).rglob("*") if p.is_file() and p.suffix.lower() in _METIN_UZANTILARI)


def denetle(dizin: Path) -> list[str]:
    """Dizindeki metin dosyalarında yasaklı iddiaları ve zorunlu etiketin YOKLUĞUNU listeler (boş liste = temiz)."""
    sorunlar: list[str] = []
    etiket_var = False
    for p in metin_dosyalari(dizin):
        metin = p.read_text(encoding="utf-8", errors="replace")
        etiket_var = etiket_var or ZORUNLU_ETIKET in metin
        for ad, desen in YASAKLI_IDDIALAR:
            if desen.search(metin):
                sorunlar.append(f"{p.name}: {ad}")
    if not etiket_var:
        sorunlar.append(f"zorunlu etiket yok: '{ZORUNLU_ETIKET}'")
    return sorunlar
