# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""CI KAPISI — "sqlcipher" nedenli ATLAMA varsa iş KIRMIZI (A-46 · D2.07 · B-3.47).

NEDEN: şifreleme / göç / karantina / kurtarma kapılarının çoğu `pytest.importorskip("sqlcipher3")`
ya da `skipif(import_sqlcipher() is None)` ile korunuyor. CI'da sqlcipher3 kurulamayınca bu
testler SESSİZCE atlanıyor ve iş YEŞİL bitiyordu: Windows işinde sqlcipher3 hiç kurulmuyordu,
Linux işinde kurulum `|| echo` ile yutuluyordu. Ölçüldü (2026-10-06, 2-A): sqlcipher3 yokken
karantina bütçesini 1 denemeye indiren mutant tüm modül atlandığı için YEŞİL kalıyordu.
Sahip kararı A-46: "sqlcipher3 kurulamazsa CI KIRMIZI olur; şifreleme/kurtarma testleri
sessizce atlanmaz."

KULLANIM (CI, test adımından sonra):
    python scripts/ci_sqlcipher_atlama_kapisi.py <pytest --junitxml dosyası>

ÇIKIŞ: 0 = "sqlcipher" nedenli atlama YOK · 1 = VAR (sayı ve ilk testler basılır) ·
       2 = XML okunamadı ya da HİÇ test yok (kapı KÖR — KIRMIZI sayılır).
Neden araması büyük/küçük harf duyarsızdır ("SQLCipher", "sqlcipher3", "pysqlcipher3" hepsi sayılır).
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET

#: Atlama nedeninde bu dize geçerse (harf duyarsız) atlama SAYILIR.
ANAHTAR = "sqlcipher"


def sqlcipher_atlamalari(junit_yolu: str) -> tuple[int, list[str]]:
    """(toplam test sayısı, "sqlcipher" nedenli atlanan testlerin kimlikleri)."""
    kok = ET.parse(junit_yolu).getroot()
    toplam = 0
    atlananlar: list[str] = []
    for tc in kok.iter("testcase"):
        toplam += 1
        for alt in tc:
            if alt.tag != "skipped":
                continue
            neden = f"{alt.get('message') or ''} {alt.text or ''}"
            if ANAHTAR in neden.lower():
                atlananlar.append(
                    f"{tc.get('classname', '')}::{tc.get('name', '')} — {(alt.get('message') or '').strip()}"
                )
            break
    return toplam, atlananlar


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 1:
        print("kullanim: ci_sqlcipher_atlama_kapisi.py <junit.xml>", file=sys.stderr)
        return 2
    try:
        toplam, atlananlar = sqlcipher_atlamalari(argv[0])
    except (OSError, ET.ParseError) as e:
        print(f"KAPI KOR: junit XML okunamadi ({argv[0]}): {e}", file=sys.stderr)
        return 2
    if toplam == 0:
        print(f"KAPI KOR: junit XML'de HIC test yok ({argv[0]}) — test adimi kosmamis olabilir", file=sys.stderr)
        return 2
    if atlananlar:
        print(f"KIRMIZI (A-46): {len(atlananlar)} test 'sqlcipher' nedeniyle ATLANDI / {toplam} test.")
        print("sqlcipher3 bu islerde KURULU OLMALI; sifreleme/goc/karantina kapilari sessizce atlanamaz.")
        for satir in atlananlar[:40]:
            print(f"  - {satir}")
        if len(atlananlar) > 40:
            print(f"  ... (+{len(atlananlar) - 40})")
        return 1
    print(f"TAMAM: {toplam} test, 'sqlcipher' nedenli atlama 0.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
