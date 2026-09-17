# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""THIRD_PARTY_LICENSES.md URETECI — atif (NOTICE) envanterini yeniden uretir.

KULLANIM:
    python scripts/lisans_envanteri_uret.py            # dosyayi yeniden yaz
    python scripts/lisans_envanteri_uret.py --kontrol  # yalnizca FARKI bildir (cikis 1)

⚠️ NEDEN VAR (denetim 2026-09-16). Envanter 2026-08-10'da donmustu ve `shap`, `grad-cam`,
`timm`, `captum`, `celldetection` gibi sonradan eklenen bagimliliklari icermiyordu. Elle
yazilan her envanter bayatlar; `README` surum tablosu ayni tuzaga UC kez dustu. Uretec
olmadan dorduncusu kacinilmazdi.

⚠️ IKI KAYNAK BIRLESTIRILIR — ve bu BILINCLI:

  1. `requirements.txt` — SEVK EDILEN calisma-zamani bagimliliklari. Bu liste HER ZAMAN
     okunabilir (temiz checkout, CI dahil) ve dagitilan seyin BEYANIDIR.
  2. `pemf-app-packages/base-deps.zip` icindeki `dist-info/METADATA` — gercek lisans
     METINLERI. Yalniz paket varsa okunur.

⚠️ NEDEN TEK BASINA (2) YETMEZ: PyInstaller cogu paketin metadata'sini AYIKLAR. Olculdu
(2026-09-16): pakette yalniz 26 paketin METADATA'si kaldi ve cogunun lisans alani BOS
("belirtilmemis"). Oysa `numpy`, `pillow`, `opencv-python`, `fastapi` gibi paketler
GERCEKTEN sevk ediliyor. Yalniz pakete bakan bir envanter, atif yuzeyini OLDUGUNDAN
KUCUK gosterir — ticari bir urunde bu, eksik atif demektir.

⚠️ `requirements-dev.txt` DISARIDA: ruff/pytest/pre-commit sevk EDILMEZ, atif gerektirmez.
"""

from __future__ import annotations

import argparse
import re
import sys
import zipfile
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
_REQ = KOK / "requirements.txt"
_PAKET = KOK / "pemf-app-packages" / "base-deps.zip"
_HEDEF = KOK / "THIRD_PARTY_LICENSES.md"

_BASLIK_SONU = "## Dağıtılan pakette tespit edilen bileşenler"

#: Paket adi -> lisans. `dist-info/METADATA` okunamayan paketler icin elle dogrulanmis
#: degerler. ⚠️ Her satir PyPI sayfasindan dogrulanmistir; tahmin YAZILMAZ.
_BILINEN_LISANSLAR = {
    "fastapi": "MIT",
    "uvicorn": "BSD-3-Clause",
    "starlette": "BSD-3-Clause",
    "pydantic": "MIT",
    "numpy": "BSD-3-Clause",
    "scipy": "BSD-3-Clause",
    "pandas": "BSD-3-Clause",
    "matplotlib": "PSF-based (matplotlib licence)",
    "pillow": "MIT-CMU",
    "opencv-python": "Apache-2.0",
    "opencv-python-headless": "Apache-2.0",
    "onnxruntime": "MIT",
    "scikit-learn": "BSD-3-Clause",
    "xgboost": "Apache-2.0",
    "joblib": "BSD-3-Clause",
    "shap": "MIT",
    "captum": "BSD-3-Clause",
    "timm": "Apache-2.0",
    "grad-cam": "MIT",
    "ttach": "MIT",
    "celldetection": "Apache-2.0",
    "safetensors": "Apache-2.0",
    "slicer": "MIT",
    "paho-mqtt": "EPL-2.0 / EDL-1.0",
    "pyserial": "BSD-3-Clause",
    "zeroconf": "LGPL-2.1",
    "reportlab": "BSD-3-Clause",
    "python-multipart": "Apache-2.0",
    "httpx": "BSD-3-Clause",
    "supabase": "MIT",
    "sentry-sdk": "MIT",
    "pyyaml": "MIT",
    "imageio-ffmpeg": "BSD-2-Clause",
    "ultralytics": "AGPL-3.0",
}


#: `requirements.txt`te listeli ama URUNLE SEVK EDILMEYEN araclar. Atif gerektirmezler:
#: kullanicinin eline gecen pakette bulunmazlar (olculdu — base-deps.zip'te METADATA'lari yok).
#: ⚠️ Buraya bir sey eklemek "bu paket dagitilmiyor" beyanidir; olcmeden eklemeyin.
_SEVK_EDILMEYEN = {"pyinstaller", "pytest"}


def _req_paketleri() -> list[str]:
    """`requirements.txt`teki SEVK EDILEN paket adlari (yorum/secenek satirlari haric)."""
    adlar = []
    for satir in _REQ.read_text(encoding="utf-8").splitlines():
        s = satir.strip()
        if not s or s.startswith("#") or s.startswith("-"):
            continue
        ad = re.split(r"[=<>!~\[; ]", s)[0].strip()
        if ad:
            adlar.append(ad.lower())
    return sorted(set(adlar))


def metadata_lisansi(meta: str) -> str:
    """Bir `dist-info/METADATA` metninden lisans alanini cikar.

    ⚠️ `License-Expression` ONCELIKLI (PEP 639). Bu alani okumayan bir ayristirici, modern
    paketlerin lisansini BOS gorur. Olculdu (2026-09-16, sevk edilen base-deps.zip):
    100 paketin **30'unun** lisansi eski okuyucuyla BOS cikiyordu, yeni okuyucuyla 0.

    ⚠️ BUGUN GIZLI BIR UYUMSUZLUK YOK: iki okuyucu da kopyleft kumesini AYNI buluyor
    (`{ultralytics}`). Yani bu, yasanmis bir ihlal degil, GELECEK icin acik bir delikti —
    `License-Expression: AGPL-3.0` diyen yeni bir paket kopyleft kapisina GORUNMEZ olurdu.

    ⚠️ TEK KAYNAK: `tests/test_license_surface.py` bu fonksiyonu IMPORT eder, kendi
    kopyasini yazmaz. (Bu depo 2026-09-15'te "ayni kural iki yerde -> sessizce ayristi"
    arizasini UC ayri noktada yasadi.)
    """
    ifade = klasik = siniflandirici = ""
    for satir in meta.splitlines()[:80]:
        if satir.startswith("License-Expression:"):
            ifade = satir.split(":", 1)[1].strip()
        elif satir.startswith("License:"):
            klasik = klasik or satir.split(":", 1)[1].strip()
        elif satir.startswith("Classifier: License ::"):
            siniflandirici = siniflandirici or satir.split("::")[-1].strip()
    return ifade or klasik or siniflandirici


def paket_lisanslari(paket: Path | None = None) -> dict[str, tuple[str, str]]:
    """Sevk edilen pakette (paket adi -> (surum, lisans)). Paket yoksa bos sozluk."""
    yol = paket or _PAKET
    out: dict[str, tuple[str, str]] = {}
    if not yol.exists():
        return out
    with zipfile.ZipFile(yol) as z:
        for n in z.namelist():
            m = re.match(r"PEMF_Backend/_internal/([^/]+)-([^/]+)\.dist-info/METADATA$", n)
            if not m:
                continue
            lic = metadata_lisansi(z.read(n).decode("utf-8", "replace"))
            out[m.group(1).lower().replace("_", "-")] = (m.group(2), lic)
    return out


def _paket_metadata_lisanslari() -> dict[str, tuple[str, str]]:
    return paket_lisanslari()


def envanter() -> list[tuple[str, str, str]]:
    """(paket, surum, lisans) — ad sirali. Surum/lisans bilinmiyorsa '—'."""
    meta = _paket_metadata_lisanslari()
    satirlar = []
    for ad in _req_paketleri():
        if ad in _SEVK_EDILMEYEN:
            continue
        surum, lisans = meta.get(ad, ("", ""))
        if not lisans:
            lisans = _BILINEN_LISANSLAR.get(ad, "")
        satirlar.append((ad, surum or "—", lisans or "⚠️ doğrulanmadı"))
    # Pakette olup requirements'ta olmayanlar (dolayli bagimliliklar) da atif gerektirir.
    reqler = set(_req_paketleri())
    for ad, (surum, lisans) in sorted(meta.items()):
        if ad not in reqler:
            satirlar.append((ad, surum or "—", lisans or _BILINEN_LISANSLAR.get(ad, "belirtilmemiş")))
    return sorted(satirlar, key=lambda t: t[0])


def _tablo(satirlar) -> str:
    bas = "| Paket | Sürüm | Lisans |\n|---|---|---|\n"
    return bas + "\n".join(f"| `{a}` | {s} | {li} |" for a, s, li in satirlar) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--kontrol", action="store_true", help="yazma; yalniz fark varsa 1 don")
    a = ap.parse_args()

    satirlar = envanter()
    mevcut = _HEDEF.read_text(encoding="utf-8")
    bas = mevcut.index(_BASLIK_SONU)
    ust = mevcut[:bas]
    yeni_govde = (
        f"{_BASLIK_SONU}\n\n"
        "Aşağıdaki liste **üretilmiştir** (`scripts/lisans_envanteri_uret.py`); elle\n"
        "düzenlemeyin. Kaynaklar: `requirements.txt` (sevk edilen çalışma-zamanı\n"
        "bağımlılıkları) + `pemf-app-packages/base-deps.zip` içindeki `dist-info/METADATA`.\n\n"
        "⚠️ PyInstaller çoğu paketin metadata'sını ayıkladığı için sürüm/lisans alanları\n"
        "pakette bulunamayan satırlarda doğrulanmış sabit tablodan gelir.\n\n" + _tablo(satirlar)
    )
    yeni = ust + yeni_govde

    if a.kontrol:
        if yeni.strip() != mevcut.strip():
            print("[FARK] THIRD_PARTY_LICENSES.md guncel DEGIL -> `python scripts/lisans_envanteri_uret.py`")
            return 1
        print("[OK] envanter guncel")
        return 0

    _HEDEF.write_text(yeni, encoding="utf-8")
    print(f"[OK] {_HEDEF.name} yeniden uretildi: {len(satirlar)} bilesen")
    dogrulanmamis = [a_ for a_, _, li in satirlar if "doğrulanmadı" in li]
    if dogrulanmamis:
        print(f"[!!] lisansi DOGRULANMAMIS {len(dogrulanmamis)} paket: {dogrulanmamis}")
        print("     `_BILINEN_LISANSLAR`a PyPI'dan dogrulayarak ekleyin (tahmin YAZMAYIN).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
