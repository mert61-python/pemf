# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""CI GÖRÜNÜRLÜK (istem 66 CT2 d · Y326 katman 7) — iş sayfasına (GITHUB_STEP_SUMMARY) Markdown özet; üçüncü parti eylem YOK.

Üç kip:
  <junit.xml> [--baslik B]   test sayıları + KIRMIZILAR (ad + iletinin ilk satırı) + ATLANANLAR (neden; atlanan defterindeki sınıfı)
  --fw-boyut <dizin>         STM32 ikilisi boyutu (text / data / bss — arm-none-eabi-size; .bin bayt + SHA-256)
  --isler-env <DEĞİŞKEN>     `toJSON(needs)` → iş başına sonuç tablosu (dal / commit başına TEK özet); kırmızı iş varsa çıkış 1
Özet yazımı bilgi amaçlıdır: junit / ikili yoksa not düşer, çıkış 0 (eksik eser kendi adımında zaten KIRMIZI).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
DEFTER = KOK / "tests" / "ci_atlanan_defteri.json"
KIRMIZI = {"failure", "cancelled", "timed_out"}


def _defter() -> dict[str, str]:
    try:
        return {k["test"]: k["sinif"] for k in json.loads(DEFTER.read_text(encoding="utf-8"))["kayitlar"]}
    except (OSError, ValueError, KeyError):
        return {}


def junit_ozet(yol: Path, baslik: str = "pytest") -> str:
    if not yol.is_file():
        return f"### {baslik}\n\n⚠️ junit raporu yok (`{yol.name}`) — test adımı koşmadı ya da raporu yazamadan düştü.\n"
    kok = ET.parse(yol).getroot()
    toplam = kirmizi_say = atlanan_say = 0
    kirmizilar: list[str] = []
    nedenler: Counter[str] = Counter()
    defter = _defter()
    for tc in kok.iter("testcase"):
        toplam += 1
        kimlik = f"{tc.get('classname', '')}::{tc.get('name', '')}"
        for c in tc:
            if c.tag in ("failure", "error"):
                kirmizi_say += 1
                ilk = (c.get("message") or (c.text or "")).strip().splitlines()
                kirmizilar.append(f"| `{kimlik}` | {c.tag} | {(ilk[0] if ilk else '')[:160].replace('|', '/')} |")
            elif c.tag == "skipped":
                atlanan_say += 1
                neden = (c.get("message") or "").strip().splitlines()
                nedenler[f"{defter.get(kimlik, 'DEFTER DIŞI')} · {(neden[0] if neden else '?')[:120]}"] += 1
    gecen = toplam - kirmizi_say - atlanan_say
    s = [
        f"### {baslik}",
        "",
        f"**{gecen} geçti · {kirmizi_say} kırmızı · {atlanan_say} atlandı** (toplam {toplam})",
        "",
    ]
    if kirmizilar:
        s += ["#### Kırmızılar", "", "| test | tür | ileti |", "|---|---|---|", *kirmizilar[:40]]
        if len(kirmizilar) > 40:
            s.append(f"| … | | {len(kirmizilar) - 40} kırmızı daha (junit eseri) |")
        s.append("")
    if nedenler:
        s += ["#### Atlananlar (sınıf · neden)", "", "| sayı | sınıf · neden |", "|---|---|"]
        s += [f"| {n} | {k.replace('|', '/')} |" for k, n in nedenler.most_common(25)]
        s.append("")
    return "\n".join(s) + "\n"


def fw_boyut(dizin: Path) -> str:
    elf, bin_ = dizin / "pemf.elf", dizin / "pemf.bin"
    if not elf.is_file():
        return "### Kart yazılımı (STM32) boyutu\n\n⚠️ `pemf.elf` yok — derleme adımına bakın.\n"
    s = ["### Kart yazılımı (STM32) boyutu", ""]
    boyut = shutil.which("arm-none-eabi-size")
    if boyut:
        r = subprocess.run([boyut, str(elf)], capture_output=True, text=True, encoding="utf-8", errors="replace")
        satir = [x.split() for x in r.stdout.strip().splitlines()]
        if len(satir) >= 2 and len(satir[1]) >= 3:
            t, d, b = satir[1][:3]
            s += ["| text (flash) | data | bss (RAM) |", "|---:|---:|---:|", f"| {t} | {d} | {b} |", ""]
    if bin_.is_file():
        ozet = hashlib.sha256(bin_.read_bytes()).hexdigest()
        s.append(f"`pemf.bin` {bin_.stat().st_size} bayt · SHA-256 `{ozet}`")
    return "\n".join(s) + "\n"


def isler_ozet(needs: dict) -> tuple[str, int]:
    dal, kosu = os.environ.get("DAL", ""), os.environ.get("KOSU", "")
    s = [f"### CI özeti · `{dal}`", "", "| iş | sonuç |", "|---|---|"]
    kirmizi = []
    for ad, v in sorted(needs.items()):
        sonuc = (v or {}).get("result", "?")
        isaret = "✅" if sonuc == "success" else ("⏭️" if sonuc == "skipped" else "❌")
        s.append(f"| {ad} | {isaret} {sonuc} |")
        if sonuc in KIRMIZI:
            kirmizi.append(ad)
    s.append("")
    if kirmizi:
        s.append(
            f"**KIRMIZI:** {', '.join(kirmizi)} — ayrıntı: her işin kendi özeti ve junit / kapsam eserleri ({kosu})"
        )
    else:
        s.append("Bu iş akışındaki bütün işler yeşil.")
    return "\n".join(s) + "\n", (1 if kirmizi else 0)


def _yaz(metin: str, cikti: Path | None) -> None:
    if cikti is None:
        sys.stdout.write(metin)
        return
    with cikti.open("a", encoding="utf-8") as f:
        f.write(metin)


def main(argv: list[str] | None = None) -> int:
    for akis in (sys.stdout, sys.stderr):
        if hasattr(akis, "reconfigure"):
            akis.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="CI iş özeti (GITHUB_STEP_SUMMARY)")
    ap.add_argument("junit", nargs="?", type=Path)
    ap.add_argument("--baslik", default="pytest")
    ap.add_argument("--fw-boyut", type=Path)
    ap.add_argument("--isler-env")
    ap.add_argument("--cikti", type=Path)
    a = ap.parse_args(argv)
    if a.isler_env:
        metin, kod = isler_ozet(json.loads(os.environ.get(a.isler_env) or "{}"))
        _yaz(metin, a.cikti)
        return kod
    if a.fw_boyut:
        _yaz(fw_boyut(a.fw_boyut), a.cikti)
        return 0
    if a.junit is None:
        ap.error("junit dosyası, --fw-boyut ya da --isler-env gerekli")
    _yaz(junit_ozet(a.junit, a.baslik), a.cikti)
    return 0


if __name__ == "__main__":
    sys.exit(main())
