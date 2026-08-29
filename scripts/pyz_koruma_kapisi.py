# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""5. KORUMA KAPISI — sevk edilen EXE'nin PYZ arsivinde ai_hub VAR MI? (denetim 2026-08-28 #07)

MEVCUT DORT KAPININ DORDU DE ayni soruyu soruyordu: "DISKTE duz .py kaldi mi?"
  * build_tools/make_base_zip.py::_korumasiz_ai_hub()
  * build_tools/build_installer.ps1  (KORUMA-KAPISI blogu)
  * scripts/build_backend_exe.ps1    ($kalan sayimi)
  * tests/test_installer_korumali_ai_hub_sevk_eder.py
Dordu de YESIL yaniyordu. Olculdu: EXE'nin ICINDEKI PYZ arsivinde 87 ai_hub girisi (65 modul +
18 paket + 4 namespace paketi) tam okunabilir bytecode olarak duruyordu; calisan surecte yuklu
ai_hub .pyd sayisi 1/65 idi ve o tek modul, PYZ'de ikizi OLMAYAN tek modul (cat_segmentation).
Yani Cython katmaninin koruma katkisi SIFIRDI ve hicbir kapi bunu goremiyordu.

Bu kapi, o dort kapinin goremedigi tek seyi olcer. Ikisi BIRLIKTE anlamlidir:
  (1) PYZ'de ai_hub YOK   (bu kapi)
  (2) Diskte duz .py YOK  (mevcut kapilar)
Yalniz (1) koruma kaniti DEGILDIR: Linux/macOS hedefleri ayni spec'i kosar ama compile_pyd'yi
HIC kosmaz -> orada ai_hub PYZ'den cikar ve diskte duz .py olarak kalir (islevsel olarak
sorunsuz, koruma sifir). Bu yuzden --duz-py-de-kontrol bayragi ile ikisi birlikte istenebilir.

Kullanim:
    python scripts/pyz_koruma_kapisi.py PEMF_BUILD/dist/PEMF_Backend/PEMF_Backend.exe
    python scripts/pyz_koruma_kapisi.py <exe> --paket ai_hub --duz-py-de-kontrol <dist_dizini>
Cikis: 0 temiz, 1 koruma delik.
"""

from __future__ import annotations

import argparse
import marshal
import struct
import sys
from pathlib import Path


def pyz_toc(exe: Path) -> dict:
    """EXE'nin CArchive'indan PYZ'yi cek ve TOC'unu dondur (ad -> (tip, offset, boyut))."""
    from PyInstaller.archive.readers import CArchiveReader

    car = CArchiveReader(str(exe))
    adaylar = [ad for ad in car.toc if str(ad).lower().endswith(".pyz")]
    if not adaylar:
        raise SystemExit(f"HATA: {exe} icinde PYZ arsivi yok (PyInstaller formati degismis olabilir).")
    ham = car.extract(adaylar[0])
    if isinstance(ham, tuple):  # bazi surumler (bayrak, veri) dondurur
        ham = ham[1]
    if ham[:4] != b"PYZ\x00":
        raise SystemExit("HATA: PYZ imzasi tutmuyor.")
    toc_offset = struct.unpack("!I", ham[8:12])[0]
    toc = marshal.loads(ham[toc_offset:])
    return dict(toc) if isinstance(toc, list) else toc


def duz_py_var_mi(dist_dizini: Path, paket: str) -> list[str]:
    """Sevk agacinda korumasiz duz .py kaldi mi (mevcut kapilarin olcutu)."""
    kok = dist_dizini / "_internal" / paket
    if not kok.is_dir():
        kok = dist_dizini / paket
    if not kok.is_dir():
        return []
    # __init__.py MESRUDUR (paket sinirlari icin gerekir, is mantigi tasimaz).
    return [str(p.relative_to(kok)) for p in kok.rglob("*.py") if p.name != "__init__.py"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("exe", type=Path, help="uretilen PEMF_Backend.exe")
    ap.add_argument("--paket", default="ai_hub", help="PYZ'de bulunmamasi gereken paket koku")
    ap.add_argument(
        "--duz-py-de-kontrol",
        type=Path,
        default=None,
        metavar="DIST",
        help="ayrica sevk agacinda duz .py kalmadigini dogrula (koruma kaniti icin ikisi birlikte gerekir)",
    )
    a = ap.parse_args()

    if not a.exe.is_file():
        print(f"[pyz-kapi] HATA: EXE yok: {a.exe}")
        return 1

    toc = pyz_toc(a.exe)
    kok = a.paket + "."
    girisler = sorted(ad for ad in toc if ad == a.paket or ad.startswith(kok))

    if girisler:
        print(f"[pyz-kapi] KIRMIZI: PYZ arsivinde {len(girisler)} '{a.paket}' girisi VAR.")
        for ad in girisler[:10]:
            print(f"    - {ad}")
        if len(girisler) > 10:
            print(f"    ... (+{len(girisler) - 10})")
        print(
            "[pyz-kapi] Bu girisler okunabilir bytecode'dur ve import'ta diskteki .pyd'yi YENER\n"
            "           (PyiFrozenFinder once PYZ'ye bakar). Kod korumasi ETKISIZDIR.\n"
            "           Cozum: spec'te `a.pure[:] = [x for x in a.pure if x[0].split('.')[0] != "
            f"'{a.paket}']` satiri PYZ(a.pure) cagrisindan ONCE olmali."
        )
        return 1

    print(f"[pyz-kapi] PYZ temiz: '{a.paket}' girisi yok ({len(toc)} toplam giris tarandi).")

    if a.duz_py_de_kontrol is not None:
        kalan = duz_py_var_mi(a.duz_py_de_kontrol, a.paket)
        if kalan:
            print(f"[pyz-kapi] KIRMIZI: sevk agacinda {len(kalan)} korumasiz duz .py var: {kalan[:5]}")
            print("[pyz-kapi] PYZ temiz ama disk degil -> koruma yine SIFIR (import duz kaynaga duser).")
            return 1
        print("[pyz-kapi] Sevk agaci da temiz: duz .py yok -> koruma GERCEKTEN etkin.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
