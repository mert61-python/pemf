# -*- coding: utf-8 -*-
# Author: mertaygn
"""STM32 WORKSPACE'İNİ FLASH İÇİN KOPYALA — derleme artıkları HARİÇ.

===============================================================================
⚠️ NEDEN VAR — SAHADA BİR GÜN KAYBETTİREN TUZAK (2026-09-11)
===============================================================================
Workspace masaüstüne `Debug/` klasörüyle birlikte kopyalandı. O klasörde **8 Eylül
tarihli, 5 BOBİNLİK** bir `PEMF_UNIPOLAR.elf` duruyordu (7 bobin geçişi 10 Eylül'de
oldu). CubeIDE kaynağı yeniden derlemek yerine **o bayat ikiliyi flashladı**.

Sonuç sinsi: kart bağlı, uygulama STM'i görüyor, ama backend'in 120 baytlık paketini
88 bayt bekleyen firmware çerçeveliyor → CRC tutmuyor → **her pakete `STM_NACK: CRC`**
→ hiçbir bobin çalışmıyor (1-5 dahil). Ekranda "başarılı" görünür; arıza yalnız
bildirim selinden ve UART banner'ından anlaşılır.

Kaynağın doğru olması, KARTA YÜKLENDİĞİNİ kanıtlamaz. Bu betik artıkları taşımayarak
CubeIDE'yi yeniden derlemeye ZORLAR ve kopyanın gerçekten 7 bobinlik olduğunu DOĞRULAR.

KULLANIM:
    python scripts/stm_workspace_kopyala.py                    # masaüstüne, tarihli klasör
    python scripts/stm_workspace_kopyala.py --hedef D:/yedek   # başka yere
"""

from __future__ import annotations

import argparse
import datetime as _dt
import os
import re
import shutil
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
#: ⚠️ TEK PROJE (2026-09-11): `stm32_pemf_unipolar` aynasi KALDIRILDI. Surus kipi artik
#: `PEMF_BOBIN_UNIPOLAR_MASKESI` ile bobin basina seciliyor; ikinci bir derleme gerekmiyor.
PROJELER = ["stm32_pemf"]

#: Kopyaya ASLA girmeyecek dizinler — DERLEME ÇIKTISI.
#: ⚠️ `Debug`/`Release` burada OLMAK ZORUNDA: içlerindeki `.elf` doğrudan flashlanabilir
#: ve CubeIDE yeniden derlemeden onu yükleyebilir (bu betiğin var oluş sebebi).
#: ⚠️ `.settings` BİLEREK HARİÇ DEĞİL: CubeIDE proje tercihleri (indeksleyici/biçimlendirici)
#: oradadır, derlemeyi `.cproject` belirler. Dışlamak kopyayı sahibin çalışan kurulumundan
#: gereksizce ayrıştırırdı; kopya, derleme artıkları DIŞINDA depo kaynağıyla BİREBİR kalmalı.
HARIC_DIZIN = {"Debug", "Release", ".metadata", "__pycache__"}
#: Kopyaya ASLA girmeyecek dosya uzantıları — flashlanabilir ikililer.
HARIC_UZANTI = {".elf", ".bin", ".hex", ".map", ".o", ".d", ".su", ".lst"}


def _atla(dizin: str, adlar: list[str]) -> set[str]:
    atlanan = {a for a in adlar if a in HARIC_DIZIN}
    for a in adlar:
        if Path(a).suffix.lower() in HARIC_UZANTI and not (Path(dizin) / a).is_dir():
            atlanan.add(a)
    return atlanan


def _bobin_sayisi(main_c: Path) -> int | None:
    try:
        m = re.search(r"#define\s+NUM_COILS\s+(\d+)", main_c.read_text(encoding="utf-8", errors="replace"))
        return int(m.group(1)) if m else None
    except OSError:
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hedef", default=None, help="hedef kök (varsayılan: Masaüstü)")
    a = ap.parse_args()

    kok = Path(a.hedef) if a.hedef else Path(os.path.expanduser("~/Desktop"))
    if not kok.is_dir():
        print(f"[HATA] hedef kok yok: {kok}", file=sys.stderr)
        return 2

    hedef = kok / f"PEMF_STM32_workspace_{_dt.date.today().isoformat()}"
    if hedef.exists():
        shutil.rmtree(hedef)
    hedef.mkdir(parents=True)

    for p in PROJELER:
        kaynak = KOK / "firmware" / p
        if not kaynak.is_dir():
            print(f"[HATA] proje yok: {kaynak}", file=sys.stderr)
            return 2
        shutil.copytree(kaynak, hedef / p, ignore=_atla)
        print(f"  kopyalandi: {p}")

    # ── DOĞRULAMA — kopyanın kendisi ölçülür, kopyalandığı varsayılmaz ──────────
    sorun: list[str] = []

    artiklar = [q for q in hedef.rglob("*") if q.suffix.lower() in HARIC_UZANTI and q.is_file()]
    if artiklar:
        sorun.append(f"derleme artigi TASINDI ({len(artiklar)}): {[str(x.name) for x in artiklar[:5]]}")

    for p in PROJELER:
        n = _bobin_sayisi(hedef / p / "Core" / "Src" / "main.c")
        if n is None:
            sorun.append(f"{p}: NUM_COILS okunamadi")
        elif n != 7:
            sorun.append(f"{p}: NUM_COILS={n} (7 bekleniyordu) — BAYAT KAYNAK")
        else:
            print(f"  dogrulandi : {p}  NUM_COILS=7")

    print()
    if sorun:
        for s in sorun:
            print(f"[HATA] {s}", file=sys.stderr)
        return 1

    print(f"HAZIR: {hedef}")
    print()
    print("⚠️ CubeIDE'de FLASH ETMEDEN ONCE:")
    print("   1) Project -> Clean...   (bayat nesne dosyasi kalmasin)")
    print("   2) Project -> Build      (yeni .elf URETILSIN)")
    print("   3) Run/Debug ile yukle")
    print("   4) DOGRULA: UART banner 'STM_READY: ... (7-ch ...' demeli.")
    print("      '5-ch' goruyorsan ESKI ikili yuklenmis demektir.")
    print("      Hizli kontrol:  python scripts/stm_firmware_kimligi.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
