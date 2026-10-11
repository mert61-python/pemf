# -*- coding: utf-8 -*-
"""4B-2.8 (4-B incelemesi A2) — S-4B.1'in sınıfı GENEL: ASCII dışı bayt taşıyan her izlenen `.ps1` UTF-8 BOM'lu olmalı.

Windows PowerShell 5.1 BOM'suz dosyayı ANSI (bu makinede cp1254) okur. S-4B.1 yalnız `restore_assets.ps1`'i düzeltti; ölçüldü
(`_inceleme/kayit/k2_ps51_ayristirma_sonda.txt`): 20 izlenen .ps1'den 2'si BOM'suz + ASCII dışı — `build_tools/build_installer.ps1`
(BUILD.md: `.\\build_tools\\build_installer.ps1`) sürüm bilgisi dizesinde 5.1 ayrıştırıcısı şirket adını `'Ä°BÄ°A Tekn…'` okuyor
(pwsh 7: `'İBİA Teknol…'`; `_inceleme/kayit/k2_ps51_sirket_adi_sonda.txt`) → EXE'nin CompanyName / LegalCopyright alanı bozuk.
Ayrıştırma hatası VERMEDİĞİ için (0 hata) yalnız ParseFile'a bakan kapı bunu görmez — kural bayt düzeyinde.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]


def _izlenen_ps1() -> list[str]:
    ham = subprocess.run(
        ["git", "-c", "core.quotepath=off", "ls-files", "-z", "--", "*.ps1"], cwd=KOK, capture_output=True, timeout=120
    ).stdout
    return [x.decode("utf-8") for x in ham.split(b"\x00") if x]


def test_KRITIK_ASCII_disi_bayt_tasiyan_her_ps1_BOMlu():
    dosyalar = _izlenen_ps1()
    assert len(dosyalar) >= 15, f"vakum: {len(dosyalar)} .ps1"
    kotu = []
    for ad in dosyalar:
        b = (KOK / ad).read_bytes()
        if any(c > 127 for c in b) and not b.startswith(b"\xef\xbb\xbf"):
            kotu.append(ad)
    assert not kotu, (
        "BOM'suz + ASCII disi .ps1 (Windows PowerShell 5.1 bunlari ANSI okur: dizeler bozulur, Turkce/em-dash satirlari "
        f"ayristirma hatasi verebilir — S-4B.1 sinifi): {kotu}"
    )


def test_KARSIT_olcucu_kor_degil():
    assert (KOK / "scripts" / "restore_assets.ps1").read_bytes().startswith(b"\xef\xbb\xbf")
    assert any(c > 127 for c in (KOK / "scripts" / "restore_assets.ps1").read_bytes())
