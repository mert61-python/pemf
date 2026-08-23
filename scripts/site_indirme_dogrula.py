# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""SITEDEKI INDIRME BUTONLARININ ISARET ETTIGI DOSYALAR GERCEKTEN YAYINDA MI? (2026-08-23)

⚠️ NEDEN AYRI BIR BETIK. `tests/test_site_indirme_varligi_URETILDI.py` dosyanin YERELDE
URETILDIGINI olcer; ag gerektirmez. Ama 2026-08-22 yayininda ariza tam da o kapinin GORMEDIGI
yerde oldu: `release_assets/PEMFVetClient-Setup-1.9.34.exe` URETILMISTI ama yayina yalniz
SURUMSUZ ad (`PEMFVetClient-Setup.exe`) yuklendi. Site adi etiketten TURETIYOR
(`PEMFVetClient-Setup-<surum>.exe`) → "Windows icin indir" dugmesi **404** verdi ve bir gun
boyunca fark edilmedi.

Yerel kapi "yukleyecek dosya var mi?" sorusunu sorar; BU betik "yuklendi mi?" sorusunu sorar.
Ikisi farkli arizalari yakalar ve ikisi de gerekir.

KULLANIM (yayin akisinin SON adimi):
    ..\\python.exe scripts\\site_indirme_dogrula.py

Cikis 0 = sitedeki her indirme baglantisi HTTP 200. Cikis 1 = en az biri kirik (ad ve URL yazilir).

TEK KAYNAK: adlar/etiketler `pemf-vet-web/src/config.ts`ten okunur — yani SITENIN GERCEKTEN
KULLANDIGI degerlerden. Burada elle yazilan bir ad olsaydi, bu betik sitenin kirilmasini
gormeden yesil kalabilirdi.
"""

from __future__ import annotations

import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

KOK = Path(__file__).resolve().parents[1]
CONFIG = KOK / "pemf-vet-web" / "src" / "config.ts"

# GitHub, User-Agent'siz istekleri reddedebiliyor (Cloudflare 1010) — bkz. scripts/supabase_sql.py.
_UA = {"User-Agent": "pemf-site-indirme-dogrula/1.0"}


def _al(desen: str, kaynak: str, ad: str) -> str:
    m = re.search(desen, kaynak)
    if not m:
        raise SystemExit(f"[HATA] config.ts icinde {ad} bulunamadi — bicim degismis olabilir")
    return m.group(1)


def hedefler() -> list[tuple[str, str]]:
    """(etiket_aciklamasi, url) listesi — sitenin urettigi adreslerin AYNISI."""
    src = CONFIG.read_text(encoding="utf-8", errors="replace")

    sahip = _al(r"githubOwner:\s*'([^']+)'", src, "githubOwner")
    depo = _al(r"githubRepo:\s*'([^']+)'", src, "githubRepo")
    win_tag = _al(r"windowsTag:\s*'([^']+)'", src, "windowsTag")
    and_tag = _al(r"androidTag:\s*'([^']+)'", src, "androidTag")
    and_surum = _al(r"androidVersion:\s*'([^']+)'", src, "androidVersion")

    win_sablon = _al(r"get windowsAsset\(\):\s*string\s*\{\s*return\s*`([^`]+)`", src, "windowsAsset")
    and_sablon = _al(r"get androidAsset\(\):\s*string\s*\{\s*return\s*`([^`]+)`", src, "androidAsset")

    win_ad = win_sablon.replace("${this.windowsTag.replace(/^launcher-v/, '')}", win_tag.replace("launcher-v", ""))
    and_ad = and_sablon.replace("${this.androidVersion}", and_surum)

    kok = f"https://github.com/{sahip}/{depo}/releases/download"
    return [
        ("Windows kurulumu", f"{kok}/{win_tag}/{win_ad}"),
        ("Android APK", f"{kok}/{and_tag}/{and_ad}"),
    ]


def kontrol(url: str) -> tuple[int, str]:
    """HEAD yerine Range'li GET: GitHub varlik yonlendirmesinde HEAD bazen 403 doner."""
    istek = urllib.request.Request(url, headers={**_UA, "Range": "bytes=0-0"})
    try:
        with urllib.request.urlopen(istek, timeout=30) as r:
            return r.status, r.headers.get("Content-Range", "") or str(r.headers.get("Content-Length", ""))
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as e:  # ag yok / DNS / TLS
        return 0, f"{type(e).__name__}: {e}"


def main() -> int:
    print("=== Site indirme baglantilari (kaynak: pemf-vet-web/src/config.ts) ===")
    kirik = []
    for ad, url in hedefler():
        kod, bilgi = kontrol(url)
        durum = "OK " if kod in (200, 206) else "KIRIK"
        print(f"  [{durum}] {kod:>3}  {ad}")
        print(f"          {url}")
        if bilgi:
            print(f"          {bilgi}")
        if kod not in (200, 206):
            kirik.append((ad, url, kod))

    if kirik:
        print("\n[HATA] Sitedeki indirme butonu KIRIK:")
        for ad, url, kod in kirik:
            print(f"  - {ad}: HTTP {kod}")
            print(f"    {url}")
        print(
            "\nEn olasi sebep: varlik yayina SURUMSUZ adla yuklendi (OTA icin gerekli) ama site\n"
            "SURUMLU adi bekliyor. Cozum: ayni ikiliyi surumlu adla da yukleyin —\n"
            "  gh release upload <etiket> -R <sahip>/<depo> release_assets/<surumlu-ad>\n"
            "(Silme YOK, yalniz ek ad. --clobber gerekmez.)"
        )
        return 1

    print("\n[TAMAM] Sitedeki tum indirme baglantilari canli.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
