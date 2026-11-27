# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""KART YAZILIMI KAPSAMI (CT1 g · istem 66 · Y326) — STM32 güvenlik mantığının bilgisayarda (ana makine koşum takımı) ölçümü.

Koşum takımı (`tests/firmware_host_aparat.py`) GERÇEK `firmware/stm32_pemf/Core/Src/main.c`'yi satır numarası KORUNARAK dönüştürüp
(`main_host.c`) gcc ile derler; `PEMF_FW_KAPSAM=1` iken `--coverage` ekler → test koşusunun ardından her derleme dizininde `.gcda` kalır.
Bu betik onları `gcov --json-format` ile okur, kopya adını gerçek kaynağa eşler ve lcov yazar (fark kapsamı kapısı okur).
DIŞARIDA (gerekçeli, ölçülmez): CubeMX üretimi başlatma işlevleri (`SystemClock_Config`, `MX_*_Init`, `HAL_*MspInit` …) + HAL /
CMSIS / sürücüler (eşlenmez) + ESP kart yazılımı (Ö.4-Y7: ESP devre dışı, kod silinmez — ürünle sevk edilmez).
Kullanım: python scripts/firmware_kapsam.py --kok <gcda kökü> [--gcov gcov] [--lcov firmware.info]
ÇIKIŞ: 0 = ölçüldü · 2 = hiç .gcda yok (kör) ya da gcov düştü.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
CORE_SRC = "firmware/stm32_pemf/Core/Src"
#: koşum takımının yazdığı kopya adı → gerçek kaynak (satır numarası korunur — dönüşümler aynı satırda)
#: CT2 f2 (Y344-1): ana döngü koşum takımı gcc kolu `pemf_akim.c`yi DEĞİŞTİRMEDEN (gerçek yolundan) derler → adıyla eşlenir.
ESLEME = {
    "main_host.c": f"{CORE_SRC}/main.c",
    "pemf_sensor_host.c": f"{CORE_SRC}/pemf_sensor.c",
    "pemf_akim.c": f"{CORE_SRC}/pemf_akim.c",
}
#: CubeMX üretimi / donanım başlatma — ana makinede anlamsız, ölçüm DIŞI
DISARIDA_ISLEV = re.compile(r"^(SystemClock_Config|MX_\w+_Init|HAL_\w*Msp\w*Init|Error_Handler|assert_failed)$")


def gcov_oku(gcda: Path, gcov: str = "gcov") -> list[dict]:
    r = subprocess.run(
        [gcov, "--json-format", "--stdout", gcda.name],
        cwd=gcda.parent,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
    )
    if r.returncode != 0:
        raise RuntimeError(f"gcov düştü ({gcda}): {r.stderr[-500:]}")
    return [json.loads(s) for s in r.stdout.splitlines() if s.strip().startswith("{")]


def _satir_sayisi(hedef: str) -> int:
    """Gerçek kaynağın satır sayısı — kopyanın SONUNA eklenen koşum takımı sondası (ör. `pemf_host_aktif_maske`) gerçek dosyada
    yoktur, ölçüme girmez (CT2 f2). Kaynak yoksa (sahte gcov çıktısı) sınır yok."""
    yol = KOK / hedef
    return len(yol.read_text(encoding="utf-8", errors="replace").splitlines()) if yol.is_file() else sys.maxsize


def birlestir(belgeler: list[dict]) -> dict[str, dict[int, int]]:
    """gcov JSON belgeleri → gerçek kaynak → {satır: sayım} (dışarıdaki işlevlerin satırları atılır, sayımlar toplanır)."""
    sonuc: dict[str, dict[int, int]] = {}
    for b in belgeler:
        for f in b.get("files", []):
            hedef = ESLEME.get(Path(f.get("file", "")).name)
            if hedef is None:
                continue
            disari = set()
            for fn in f.get("functions", []):
                if DISARIDA_ISLEV.match(fn.get("demangled_name") or fn.get("name", "")):
                    disari.update(range(int(fn["start_line"]), int(fn["end_line"]) + 1))
            satirlar = sonuc.setdefault(hedef, {})
            ust = _satir_sayisi(hedef)
            for ln in f.get("lines", []):
                no = int(ln["line_number"])
                if no not in disari and no <= ust:
                    satirlar[no] = satirlar.get(no, 0) + int(ln["count"])
    return sonuc


def lcov_yaz(olcum: dict[str, dict[int, int]], yol: Path) -> None:
    s = []
    for d, satirlar in sorted(olcum.items()):
        s.append(f"SF:{d}")
        s += [f"DA:{n},{c}" for n, c in sorted(satirlar.items())]
        s += [f"LF:{len(satirlar)}", f"LH:{sum(1 for c in satirlar.values() if c > 0)}", "end_of_record"]
    yol.write_text("\n".join(s) + "\n", encoding="utf-8")


def yuzde(olcum: dict[str, dict[int, int]]) -> float:
    tum = [c for s in olcum.values() for c in s.values()]
    return 0.0 if not tum else 100.0 * sum(1 for c in tum if c > 0) / len(tum)


def _konsol_utf8(akislar=None) -> None:
    """windows-latest konsolu cp1252 (YS1a dersi; CT1'de giriş noktası testi yakaladı): Türkçe ileti yazımı düşmesin."""
    for akis in akislar or (sys.stdout, sys.stderr):
        if hasattr(akis, "reconfigure"):
            akis.reconfigure(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    _konsol_utf8()
    ap = argparse.ArgumentParser(description="Kart yazılımı kapsamı (gcov → lcov)")
    ap.add_argument("--kok", type=Path, required=True)
    ap.add_argument("--gcov", default="gcov")
    ap.add_argument("--lcov", type=Path)
    # CT2 f2 (Y311 / Y344-1): ölçülen yüzde tests/kapsam_tabani.json → kart_yazilimi.satir ALTINA inerse KIRMIZI (CI kart işi)
    ap.add_argument("--taban", type=Path, help="kapsam_tabani.json — kart_yazilimi.satir altı = çıkış 1")
    a = ap.parse_args(argv)
    gcdalar = sorted(a.kok.rglob("*.gcda"))
    if not gcdalar:
        print(f"!!! {a.kok} altında .gcda yok — PEMF_FW_KAPSAM=1 ile gcc koşusu yapıldı mı? (kör)")
        return 2
    try:
        olcum = birlestir([b for g in gcdalar for b in gcov_oku(g, a.gcov)])
    except (RuntimeError, OSError, ValueError) as e:
        print(f"!!! {e}")
        return 2
    if a.lcov:
        lcov_yaz(olcum, a.lcov)
    for d, s in sorted(olcum.items()):
        print(f"{d}: {sum(1 for c in s.values() if c > 0)} / {len(s)} satır")
    olculen = yuzde(olcum)
    print(f"kart yazılımı (ölçülen güvenlik mantığı): %{olculen:.2f} · {len(gcdalar)} derleme")
    if a.taban:
        taban = float(json.loads(a.taban.read_text(encoding="utf-8"))["paketler"]["kart_yazilimi"]["satir"])
        if round(olculen, 2) < taban:
            print(
                f"!!! kart yazılımı %{olculen:.2f} < taban %{taban:.2f} — eşik DÜŞÜRÜLMEZ, test ekleyin (CLAUDE.md 'Test kapsamı')"
            )
            return 1
        print(f"taban %{taban:.2f} · tamam")
    return 0


if __name__ == "__main__":
    sys.exit(main())
