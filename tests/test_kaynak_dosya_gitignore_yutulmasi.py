# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""HICBIR KAYNAK DOSYA `.gitignore` TARAFINDAN YUTULMAMALI (2026-08-22, yayin sirasinda bulundu).

OLCULEN ARIZA. Kok `.gitignore` Python paketleme ciktilari icin `lib/` satiri tasiyordu.
Gitignore'da EGIK CIZGI ICERMEYEN bir desen HER DIZIN DERINLIGINDE eslesir — yani kural
`pemf-vet-web/src/lib/` klasorunu de kapsiyordu. O klasordeki ESKI dosyalar kural eklenmeden
once izlendigi icin sorun GORUNMUYORDU; ama sonradan eklenen her YENI kaynak dosya
(`authHatalari.ts`, `jeton.ts`, `planFiyat.ts`) commit'e SESSIZCE girmiyordu.

Belirti aldatici: yerelde her sey calisir (dosyalar diskte), CI ise
`error TS2307: Cannot find module '../lib/planFiyat'` der. Uc dosya birden eksikti ve site
CI'si kirmiziydi; yayin icin commit atilana kadar fark edilmedi.

DERS: "yerelde calisiyor ama CI'da yok" sinifinin en sinsi sebebi, dosyanin depoda HIC var
olmamasidir. Kapi: izlenen kaynak agaclarindaki hicbir kaynak dosya yoksayilmis olamaz.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

_KOK = Path(__file__).resolve().parents[1]

# Kaynak agaclari + o agacta kaynak sayilan uzantilar.
_AGACLAR = {
    "pemf-vet-web/src": (".ts", ".tsx", ".css"),
    "pemf-vet-web/api": (".ts",),
    "pf/src": (".ts", ".tsx"),
    "servers": (".py",),
    "controllers": (".py",),
    "services": (".py",),
    "database": (".sql",),
    "scripts": (".py",),
    "build_tools": (".py",),
    "tests": (".py",),
}

# Kaynak agaci ICINDE de mesru olarak yoksayilan seyler (uretim ciktisi / bagimlilik).
_MESRU = ("node_modules", "__pycache__", ".gradle", "dist", "build", ".expo")

# ⚠️ BILEREK YOKSAYILAN KAYNAK DOSYALAR — her biri tek tek dogrulanmali.
# `build_tools/_static_password.py`: kaynak sifreleme parolasini tasir; depoya GIRMEMELIDIR
# (izlenen surumu `_static_password.example.py` sablonudur). Yoksayilmasi DOGRUDUR.
# ⚠️ Bu kumeye ekleme yapmadan once sorun: dosya gercekten SIR mi, yoksa kaybolan bir
# kaynak dosya mi? Ikincisiyse cozum muafiyet degil, .gitignore desenini daraltmaktir.
_BILEREK_YOKSAYILAN = frozenset(
    {
        "build_tools/_static_password.py",
    }
)

_NUL = chr(0)


def _check_ignore(yollar: list[str]) -> list[str] | None:
    """Yoksayilan yollari dondurur; git calistirilamazsa None (test atlanir).

    ⚠️ `-z` (NUL-ayracli) mod SART. Duz `--stdin` modunda git, satir sonu CR tasiyan ya da
    ozel karakter iceren yollari TIRNAKLAYARAK yaziyor (ornegin `"yol\\r"`), boylece dizge
    karsilastirmasi sessizce tutmuyor — bu testin ilk yaziminda tam olarak bu oldu.
    """
    r = subprocess.run(
        ["git", "check-ignore", "--stdin", "-z"],
        input=_NUL.join(yollar).encode("utf-8"),
        capture_output=True,
        cwd=str(_KOK),
        timeout=180,
    )
    if r.returncode not in (0, 1):  # 1 = hicbiri yoksayilmiyor (beklenen durum)
        return None
    return [s for s in r.stdout.decode("utf-8", "replace").split(_NUL) if s]


def _adaylar() -> list[Path]:
    bulunan: list[Path] = []
    for agac, uzantilar in _AGACLAR.items():
        kok = _KOK / agac
        if not kok.exists():
            continue
        for p in kok.rglob("*"):
            if not p.is_file() or p.suffix not in uzantilar:
                continue
            if any(parca in _MESRU for parca in p.parts):
                continue
            bulunan.append(p)
    return bulunan


def test_KRITIK_kaynak_dosyalar_gitignore_ile_YUTULMUYOR():
    adaylar = _adaylar()
    assert adaylar, "hic kaynak dosya bulunamadi (agac listesi bozulmus olabilir)"

    yutulan = _check_ignore([str(p.relative_to(_KOK).as_posix()) for p in adaylar])
    if yutulan is None:
        pytest.skip("git check-ignore calistirilamadi")
    yutulan = [y for y in yutulan if y not in _BILEREK_YOKSAYILAN]

    assert not yutulan, (
        "Asagidaki KAYNAK dosyalar .gitignore tarafindan yutuluyor — commit'e GIRMEZLER ve "
        "CI 'Cannot find module' ile kirilir (yerelde calistigi icin fark edilmez):\n  "
        + "\n  ".join(yutulan)
        + "\n\nSebep genelde egik-cizgisiz bir desendir (or. `lib/` HER derinlikte eslesir). "
        "Kural depo kokune sabitlenmeli: `/lib/`."
    )


def test_KARSIT_KANIT_uretim_ciktisi_HALA_yoksayiliyor():
    """Asiri-genisleme korumasi: kapiyi gecmenin ucuz yolu `.gitignore`u bosaltmaktir; o zaman
    node_modules/dist/__pycache__ depoya girer. Bunlarin yoksayildigini ayrica dogrula."""
    ornekler = [
        "pemf-vet-web/node_modules/x.js",
        "pemf-vet-web/dist/index.html",
        "servers/__pycache__/x.pyc",
    ]
    yoksayilan = _check_ignore(ornekler)
    if yoksayilan is None:
        pytest.skip("git check-ignore calistirilamadi")
    eksik = [o for o in ornekler if o not in set(yoksayilan)]
    assert not eksik, f".gitignore artik uretim ciktisini yoksaymiyor: {eksik}"
