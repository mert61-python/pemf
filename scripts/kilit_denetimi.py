# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D3.41 + D3.44 (B-9.11 · B-9.15 · B-10.64 · B-10.65) — kurtarma kilidi (`build_tools/myenv-requirements.txt`) sevk edilen paketle ve
derleme yorumlayıcısıyla AYNI mı? Tek kaynak: test (`tests/test_D3_41_kurtarma_kilidi_SEVK_AGACIYLA_ayni.py`) ve derleme betiği
(`scripts/build_backend_exe.ps1` — fark → Die) bunu çağırır.

ÖLÇÜLEN (10-25, 1.9.51 derlemesi `_internal`): sevk edilen 100 dağıtımın 12'si kilitte YOKTU (albumentations / scikit-image /
pytorch-lightning …) — kilitten kurtarma o paketleri kurmaz, AI kâhin çıktısı sessizce değişirdi; kilitte kurulu `opencv-contrib-python
4.9.0.80` BAYAT İKİZ meta veridir (cv2\\ dosyaları opencv-python 4.11.0.86'nın): kilitten kurulursa cv2'yi 4.9'a düşürür.

Kipler:
  --ortam            bu yorumlayıcıdaki kurulu sürümler requirements.txt + kilit sabitleriyle aynı mı (derleme ÖNCESİ)
  --sevk <dizin>     PyInstaller onedir çıktısı (`…\\PEMF_Backend`): `_internal\\*.dist-info` kümesi kilitte ve aynı sürümde mi;
                     dist-info'suz paketler modül sürüm sabitinden: cv2 (`cv2\\version.py`), zeroconf (EXE'deki PYZ içinden
                     `__version__`) — zeroconf requirements.txt pininin altındaysa KIRMIZI (5 mDNS CVE, LAN'a açık)
  (her iki kipte)    statik: requirements.txt sabitlerinin HEPSİ kilitte ve aynı; onnx / torch pinleri SABİT (Y3 — yükseltme önerilmez)
Çıkış: 0 temiz · 1 fark (satır satır yazılır) · 2 kullanım.
"""

from __future__ import annotations

import argparse
import importlib.metadata as md
import marshal
import re
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
URETIM = KOK / "requirements.txt"
KILIT = KOK / "build_tools" / "myenv-requirements.txt"
_SATIR = re.compile(r"^\s*([A-Za-z0-9_.\-]+)(\[[^\]]*\])?\s*==\s*([^\s;#]+)")

# Kilitte BİLEREK sabitlenmeyen kurulu dağıtımlar (gerekçeli). Sevk ağacında görülürlerse yine KIRMIZI.
ISTISNA = {
    "opencv-contrib-python": "bayat ikiz meta veri (4.9.0.80) — cv2\\ dosyaları opencv-python 4.11.0.86'nın; kilitten KURULMAZ (cv2'yi "
    "4.9'a düşürür). `pip uninstall` YAPILMAZ: RECORD paylaşılan cv2\\ dosyalarını siler → `import cv2` kırılır. Temizlik [SAHİBE]",
}
# Y3 / Ö.4: AI çıktısını belirleyen pinler — kilitte ve requirements.txt'te TAM bu sürüm (yükseltme önerilmez, Dependabot dahil — A-42).
SABIT = {"onnx": "1.15.0", "torch": "2.1.2+cpu", "torchvision": "0.16.2+cpu"}


def ad(x: str) -> str:
    return re.sub(r"[-_.]+", "-", x).lower()


def sabitler(yol: Path) -> dict[str, str]:
    return {ad(m.group(1)): m.group(3) for s in yol.read_text(encoding="utf-8").splitlines() if (m := _SATIR.match(s))}


def ayni(a: str, b: str) -> bool:
    try:
        from packaging.version import Version

        return Version(a) == Version(b)
    except Exception:
        return a == b


def kucuk(a: str, b: str) -> bool:
    from packaging.version import Version

    return Version(a) < Version(b)


def statik(uretim: dict[str, str], kilit: dict[str, str]) -> list[str]:
    hata = [f"requirements.txt `{k}=={v}` kilitte YOK" for k, v in uretim.items() if k not in kilit]
    hata += [
        f"`{k}` requirements.txt {v} ≠ kilit {kilit[k]}"
        for k, v in uretim.items()
        if k in kilit and not ayni(v, kilit[k])
    ]
    for k, v in SABIT.items():
        for kaynak, d in (("kilit", kilit), ("requirements.txt", uretim)):
            if k in d and d[k] != v:
                hata.append(f"`{k}` {kaynak} {d[k]} — SABİT pin {v} (Y3: yükseltme önerilmez)")
        if k not in kilit:
            hata.append(f"`{k}` SABİT pin kilitte YOK")
    hata += [f"`{k}` kilitte SABİTLİ ama istisna listesinde (kilitten kurulmamalı)" for k in ISTISNA if k in kilit]
    return hata


def ortam(uretim: dict[str, str], kilit: dict[str, str]) -> list[str]:
    hata = []
    for kaynak, d in (("requirements.txt", uretim), ("kilit", kilit)):
        for k, v in d.items():
            try:
                kurulu = md.version(k)
            except md.PackageNotFoundError:
                hata.append(f"`{k}=={v}` ({kaynak}) bu yorumlayıcıda KURULU DEĞİL")
                continue
            if not ayni(kurulu, v):
                hata.append(f"`{k}` kurulu {kurulu} ≠ {kaynak} {v}")
    return sorted(set(hata))


def _pyz_surumu(exe: Path, modul: str) -> str | None:
    """PyInstaller EXE'sine gömülü PYZ'den `modul.__version__` (kod nesnesinin dize sabitleri; ÇALIŞTIRILMAZ)."""
    from PyInstaller.archive.readers import CArchiveReader

    pyz = CArchiveReader(str(exe)).open_embedded_archive("PYZ.pyz")
    kod = pyz.extract(modul)
    kod = marshal.loads(kod) if isinstance(kod, (bytes, bytearray)) else kod
    adlar, sabit = kod.co_names, kod.co_consts
    if "__version__" not in adlar:
        return None
    adaylar = [s for s in sabit if isinstance(s, str) and re.fullmatch(r"\d+\.\d+\.\d+(\.\w+)?", s)]
    return adaylar[0] if len(adaylar) == 1 else None


def sevk(dizin: Path, uretim: dict[str, str], kilit: dict[str, str]) -> list[str]:
    ic = dizin / "_internal"
    if not ic.is_dir():
        return [f"sevk ağacı yok: {ic}"]
    hata, dagitim = [], {}
    for p in ic.glob("*.dist-info"):
        meta = p / "METADATA"
        if not meta.is_file():
            hata.append(f"{p.name}: METADATA yok")
            continue
        t = meta.read_text(encoding="utf-8", errors="replace")
        n, v = re.search(r"^Name:\s*(.+)$", t, re.M), re.search(r"^Version:\s*(.+)$", t, re.M)
        if not (n and v):
            hata.append(f"{p.name}: Name/Version okunamadı")
            continue
        dagitim[ad(n.group(1).strip())] = v.group(1).strip()
    if not dagitim:
        hata.append("sevk ağacında hiç dist-info yok — ölçüm boş (kör)")
    for k, v in sorted(dagitim.items()):
        if k in ISTISNA:
            hata.append(f"`{k}` sevk ediliyor ama istisna ({ISTISNA[k][:40]}…)")
        elif k not in kilit:
            hata.append(f"`{k}=={v}` SEVK EDİLİYOR ama kilitte YOK (kilitten kurtarma onu kurmaz)")
        elif not ayni(v, kilit[k]):
            hata.append(f"`{k}` sevk {v} ≠ kilit {kilit[k]}")
    cv2 = ic / "cv2" / "version.py"
    if cv2.is_file():
        m = re.search(r"""opencv_version\s*=\s*['"]([^'"]+)""", cv2.read_text(encoding="utf-8", errors="replace"))
        if not m:
            hata.append("cv2/version.py: opencv_version okunamadı")
        elif "opencv-python" in kilit and not ayni(m.group(1), kilit["opencv-python"]):
            hata.append(f"cv2 sevk {m.group(1)} ≠ kilit opencv-python {kilit['opencv-python']}")
    exe = next(iter(sorted(dizin.glob("*.exe"))), None)
    if (ic / "zeroconf").is_dir():
        zc = None
        try:
            zc = _pyz_surumu(exe, "zeroconf") if exe else None
        except Exception as e:  # noqa: BLE001 — okunamazsa KIRMIZI (aşağıda)
            hata.append(f"zeroconf sürümü PYZ'den okunamadı: {type(e).__name__}: {e}")
        if zc is None:
            hata.append("zeroconf sevk ediliyor ama sürümü okunamadı (EXE / PYZ) — doğrulanamayan mDNS yığını")
        else:
            if "zeroconf" in kilit and not ayni(zc, kilit["zeroconf"]):
                hata.append(f"zeroconf sevk {zc} ≠ kilit {kilit['zeroconf']}")
            if "zeroconf" in uretim and kucuk(zc, uretim["zeroconf"]):
                hata.append(
                    f"zeroconf sevk {zc} < requirements.txt pini {uretim['zeroconf']} (5 mDNS CVE — LAN'a açık)"
                )
    return hata


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--ortam", action="store_true")
    g.add_argument("--sevk", type=Path)
    ap.add_argument("--uretim", type=Path, default=URETIM)
    ap.add_argument("--kilit", type=Path, default=KILIT)
    a = ap.parse_args(argv)
    uretim, kilit = sabitler(a.uretim), sabitler(a.kilit)
    hata = statik(uretim, kilit)
    if a.ortam:
        hata += ortam(uretim, kilit)
    elif a.sevk is not None:
        hata += sevk(a.sevk, uretim, kilit)
    for h in hata:
        print(f"[KILIT] {h}")
    print(f"[KILIT] {'TEMİZ' if not hata else f'{len(hata)} FARK'} (kilit {len(kilit)} · requirements {len(uretim)})")
    return 1 if hata else 0


if __name__ == "__main__":
    sys.exit(main())
