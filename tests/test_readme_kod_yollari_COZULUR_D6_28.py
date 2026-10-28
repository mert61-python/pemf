# -*- coding: utf-8 -*-
"""D6.28 (B-6.4 · B-7.13): arayüz ve site README'lerindeki KOD-BİÇİMLİ göreli yollar da ÇÖZÜLSÜN.

🔴 ÖLÇÜLEN (HEAD ebf1c3fe): `test_readme_baglanti_ve_sayi_BAYATLAMAZ` yalnız markdown BAĞLANTISINI (`[x](y)`) çözer; kod-biçimli
yol (`` `../../x.bundle` ``) ve bağlantı ETİKETİ hiç ölçülmüyordu. Çözülmeyenler:
  · `apps/ui/README.md:13`  `../../pemf-frontend-arsiv-2026-08-18.bundle` — böyle bir dosya YOK; eski depo geçmişi gitignore'lu
    `apps/ui/.git.arsiv-20260818-1647/` dizininde (yalnız geliştirme makinesinde);
  · `apps/web/README.md:76` `../../pemf-vet-web-arsiv-2026-08-18.bundle` — aynı (gerçeği `apps/web/.git.arsiv-20260818-1647/`, A-39);
  · `apps/ui/README.md:46`  `..\\build_tools\\build_apk.ps1` "(guii kökünden)" — depo DIŞINI gösterir (betik `build_tools/build_apk.ps1`);
  · `apps/ui/README.md:42/:52` bağlantı etiketleri `../BUILD.md`, `../versions.json` — `apps/` altını gösterir (hedefleri `../../`).

ÖLÇÜT: iki README'de kod çiti DIŞINDAKİ her kod-biçimli parça (`` `…` ``, boşluksuz) `../`, `..\\`, `apps/` ya da `apps\\` ile başlıyorsa yol
sayılır; ters bölü `/`'ye çevrilir; `apps/` depo kökünden, `../` README'nin dizininden çözülür. Yol TEMİZ AĞAÇTA (git ls-files: dosya ya
da dizin) olmalı ya da DEPONUN `.gitignore`'u onu dışlamalı (yerel / üretilen çıktı: `apps/ui/dist`, `frontend/`, `.git.arsiv-*/` — CI'ın
temiz klonunda olmaması arıza değil, belgenin "yerel" iddiası `.gitignore` ile ölçülür). Depo dışına çıkan yol ÇÖZÜLMEZ.
Yardımcılar ( `_izlenen`, `_cit_disi`, `gitignore_disliyor_mu`, `_sahte_depo`) bağlantı kapısıyla ORTAK — iki kapı aynı ağacı görür.
"""

from __future__ import annotations

import posixpath
import re
from pathlib import Path

from test_readme_baglanti_ve_sayi_BAYATLAMAZ import _cit_disi, _izlenen, _sahte_depo, gitignore_disliyor_mu
from utils.path_utils import kaynak_kokunu_bul

KOK = kaynak_kokunu_bul(__file__)

README_LER = ("apps/ui/README.md", "apps/web/README.md")
_ONEKLER = ("../", "apps/")
_KOD = re.compile(r"`([^`\s]+)`")


def _coz(kok: Path, readme_rel: str, yol: str) -> bool:
    """Kod-biçimli yol temiz ağaçta mı, ya da deponun .gitignore'u mu dışlıyor (yerel / üretilen)."""
    duz = yol.replace("\\", "/")
    temel = "" if duz.startswith("apps/") else posixpath.dirname(readme_rel)
    hedef = posixpath.normpath(posixpath.join(temel, duz))
    if hedef == ".." or hedef.startswith("../"):
        return False
    dosyalar, dizinler = _izlenen(str(kok))
    hedef = hedef.rstrip("/")
    if hedef in dosyalar or hedef in dizinler:
        return True
    # Dizin kuralı (`dist/`, `.git.arsiv-*/`) dizinin İÇİNDEKİ bir yolla sorulur (CRLF .gitignore boş satır tuzağı, bağlantı kapısı notu).
    return gitignore_disliyor_mu(kok, hedef) or gitignore_disliyor_mu(kok, posixpath.join(hedef, "_kod_yolu_sondasi"))


def cozulmeyen_kod_yollari(kok: Path = KOK, readme_ler: tuple[str, ...] = README_LER) -> list[tuple[str, int, str]]:
    """[(README, satır, yol)] — kapının tek karar noktası."""
    bulgular = []
    for rel in readme_ler:
        metin = _cit_disi((kok / rel).read_bytes().decode("utf-8"))
        for no, satir in enumerate(metin.splitlines(), 1):
            for m in _KOD.finditer(satir):
                yol = m.group(1)
                if not yol.replace("\\", "/").startswith(_ONEKLER):
                    continue
                if not _coz(kok, rel, yol):
                    bulgular.append((rel, no, yol))
    return bulgular


def test_KARSIT_KANIT_kod_yolu_cozucu_AYIRIYOR(tmp_path):
    """Çözücü önce kendini kanıtlar: izlenen dosya / dizin ve gitignore'lu yerel dizin GEÇER; olmayan dosya, depo dışı, ters bölülü
    yanlış göreli yol ve bağlantı etiketindeki yanlış yol KIRIK; kod çitindeki yol SAYILMAZ."""
    readme = "\n".join(
        [
            "`apps/x/src/a.ts` `../../docs/A.md` `apps/x/src/` `apps\\x\\dist` `apps/x/.git.arsiv-1/`",
            "`../../yok.bundle` `..\\docs\\A.md` `../../../disari.md` [`../A.md`](../../docs/A.md) `src/serbest.ts`",
            "```",
            "`../../cit_icinde.bundle`",
            "```",
        ]
    )
    kok = _sahte_depo(
        tmp_path / "depo",
        {"apps/x/README.md": readme, "apps/x/src/a.ts": "a", "docs/A.md": "d"},
        {"apps/x/dist/i.js": "u", "apps/x/.git.arsiv-1/HEAD": "h"},
        gitignore=b"dist/\r\n.git.arsiv-*/\r\n\r\n",
    )
    assert cozulmeyen_kod_yollari(kok, ("apps/x/README.md",)) == [
        ("apps/x/README.md", 2, "../../yok.bundle"),
        ("apps/x/README.md", 2, "..\\docs\\A.md"),
        ("apps/x/README.md", 2, "../../../disari.md"),
        ("apps/x/README.md", 2, "../A.md"),
    ]


def test_KRITIK_ui_ve_site_README_kod_yollari_COZULUR():
    """Okuyucu README'deki yolu açtığında dosyayı bulur (ya da yolun yerel/üretilen olduğu .gitignore'dan kanıtlıdır)."""
    sayac = 0
    for rel in README_LER:
        sayac += sum(
            1
            for m in _KOD.finditer(_cit_disi((KOK / rel).read_bytes().decode("utf-8")))
            if m.group(1).replace("\\", "/").startswith(_ONEKLER)
        )
    assert sayac >= 5, f"VAKUM: iki README'de yalnız {sayac} kod-biçimli göreli yol bulundu — tarama bozuk"
    kirik = cozulmeyen_kod_yollari()
    assert not kirik, (
        "ÇÖZÜLMEYEN kod-biçimli yol (temiz ağaçta yok, .gitignore'da da değil):\n  "
        + "\n  ".join(f"{d}:{n} -> {y}" for d, n, y in kirik)
        + "\nYolu depodaki gerçek konuma göre yeniden hesaplayın; dosya gerçekten yoksa yolu kaldırıp gerçeği yazın."
    )
