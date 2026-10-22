# -*- coding: utf-8 -*-
"""YH D2 — bağımlılık sabitleri (requirements) ile KURULU sürüm aynı; zeroconf ağa açık olduğu için hiçbir ortamda atlanmaz.

ÖLÇÜLEN (YH, 2026-10-22): `requirements.txt` / `requirements-test.txt` `zeroconf==0.149.16` (SEC-8: 5 mDNS CVE düzeltmesi) diyordu ama
derleme ortamında (gömülü Python — PyInstaller paketi BURADAN toplanır) **0.148.0** kuruluydu; build kilidi `build_tools/myenv-requirements.txt`
0.149.0 diyordu, BUILD.md de "tekerlek yok, 0.148 kalır" diyordu (tekerlek VAR — `--no-deps --only-binary :all:` ile kuruldu). Yani CVE
düzeltmesi kâğıt üstündeydi: sahaya giden paket eski mDNS yığınını taşıyacaktı ve hiçbir kapı sabit ile kurulu sürümü karşılaştırmıyordu.
Aynı kilitte pillow / cryptography / opencv-python da `requirements.txt`in gerisinde kalmıştı (kurulu ortam requirements.txt ile aynıydı).

Kapı:
  · zeroconf KURULU (CI `requirements-test.txt`ten kurar; derleme ortamında var), TEK dağıtım, sürümü üç dosyadaki sabitle aynı — atlama YOK.
  · `requirements.txt` ∩ `requirements-test.txt` ve `requirements.txt` ∩ build kilidi sabitleri AYNI (statik; CI'da da anlamlı).
  · `requirements-test.txt`teki her paket kuruluysa sürümü sabitle aynı (CI'da hepsi kurulu → tam ölçüm).
  · Gömülü (derleme) Python'da: `requirements.txt` + build kilidindeki her kurulu paket sabitle aynı (CI bunu ATLAR — orada geçişli
    bağımlılıklar başka sürümde olabilir; derleme ortamı değildir).
Sürümler PEP 440'a göre karşılaştırılır (`0.1.1-2209072238` == `0.1.1.post2209072238`), adlar PEP 503'e göre.
"""

from __future__ import annotations

import importlib.metadata as md
import re
import sys
from pathlib import Path

import pytest
from packaging.version import InvalidVersion, Version

KOK = Path(__file__).resolve().parents[1]
URETIM = KOK / "requirements.txt"
TEST = KOK / "requirements-test.txt"
KILIT = KOK / "build_tools" / "myenv-requirements.txt"
_SATIR = re.compile(r"^\s*([A-Za-z0-9_.\-]+)(\[[^\]]*\])?\s*==\s*([^\s;#]+)")


def _ad(x: str) -> str:
    return re.sub(r"[-_.]+", "-", x).lower()


def _sabitler(yol: Path) -> dict[str, str]:
    sonuc = {}
    for satir in yol.read_text(encoding="utf-8").splitlines():
        m = _SATIR.match(satir)
        if m:
            sonuc[_ad(m.group(1))] = m.group(3)
    return sonuc


def _ayni(a: str, b: str) -> bool:
    try:
        return Version(a) == Version(b)
    except InvalidVersion:
        return a == b


def _kurulu(ad: str) -> str | None:
    try:
        return md.version(ad)
    except md.PackageNotFoundError:
        return None


def _gomulu_derleme_pythonu() -> bool:
    """PyInstaller paketinin toplandığı gömülü Python (`python310.zip` yanında) — CI / venv DEĞİL."""
    return (Path(sys.base_prefix) / f"python{sys.version_info.major}{sys.version_info.minor}.zip").exists()


def test_KRITIK_zeroconf_KURULU_tek_dagitim_ve_UC_sabitle_ayni():
    pin = _sabitler(URETIM)["zeroconf"]
    assert _sabitler(TEST)["zeroconf"] == pin and _sabitler(KILIT)["zeroconf"] == pin, (
        f"zeroconf sabitleri ayrışmış: requirements={pin} test={_sabitler(TEST).get('zeroconf')} kilit={_sabitler(KILIT).get('zeroconf')}"
    )
    dagitimlar = [d for d in md.distributions() if _ad(d.metadata["Name"] or "") == "zeroconf"]
    assert dagitimlar, (
        "zeroconf KURULU DEĞİL — CI requirements-test.txt'ten kurar; derleme ortamında paket mDNS'siz toplanır"
    )
    surumler = sorted({d.version for d in dagitimlar})
    assert len(dagitimlar) == 1, (
        f"birden çok zeroconf dist-info ({surumler}) — hangi sürümün yüklendiği belirsiz (yarım kurulum artığı)"
    )
    assert _ayni(surumler[0], pin), (
        f"kurulu zeroconf {surumler[0]} ≠ sabit {pin} — CVE düzeltmesi (SEC-8) yalnız kâğıt üstünde; "
        f"`python -m pip install --no-deps --only-binary :all: zeroconf=={pin}`"
    )


def test_KRITIK_uretim_test_ve_build_kilidi_sabitleri_ORTAK_paketlerde_ayni():
    uretim, test, kilit = _sabitler(URETIM), _sabitler(TEST), _sabitler(KILIT)
    t = {k: (uretim[k], test[k]) for k in uretim.keys() & test.keys() if not _ayni(uretim[k], test[k])}
    k = {a: (uretim[a], kilit[a]) for a in uretim.keys() & kilit.keys() if not _ayni(uretim[a], kilit[a])}
    eksik = sorted(uretim.keys() - kilit.keys())
    assert not t, f"requirements.txt ↔ requirements-test.txt ayrışık (CI sahaya gidenden farklı sürümü sınar): {t}"
    assert not k, f"requirements.txt ↔ build kilidi ayrışık (kilitten geri kurulan ortam eski sürümü paketler): {k}"
    assert not eksik, f"requirements.txt'teki paket build kilidinde YOK: {eksik}"


def test_KRITIK_requirements_test_sabitleri_KURULU_surumle_ayni():
    """CI'da hepsi kurulu → tam ölçüm; yerelde kurulu olmayan (ör. opencv-python-headless) atlanır."""
    farkli = {
        ad: (pin, kur)
        for ad, pin in _sabitler(TEST).items()
        if (kur := _kurulu(ad)) is not None and not _ayni(kur, pin)
    }
    assert not farkli, f"requirements-test.txt sabiti ≠ kurulu sürüm (sabit: kurulu): {farkli}"


def test_KRITIK_derleme_ortaminda_uretim_ve_kilit_sabitleri_KURULU_surumle_ayni():
    if not _gomulu_derleme_pythonu():
        pytest.skip(
            "gömülü derleme Python'u değil (CI / venv) — geçişli bağımlılıklar başka sürümde olabilir; zeroconf + test sabitleri yine ölçüldü"
        )
    farkli = {}
    for yol in (URETIM, KILIT):
        for ad, pin in _sabitler(yol).items():
            kur = _kurulu(ad)
            if kur is not None and not _ayni(kur, pin):
                farkli[f"{yol.name}:{ad}"] = (pin, kur)
    assert not farkli, f"derleme ortamı sabitlerden SAPMIŞ — paket bu sürümlerle toplanır (sabit: kurulu): {farkli}"
