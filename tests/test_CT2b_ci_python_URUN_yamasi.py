# -*- coding: utf-8 -*-
"""CT2 b (istem 66 · Y326 katman 2) — CI'ın Python yaması = ürünün GÖNDERDİĞİ yorumlayıcı.

ÖLÇÜLDÜ (28-11): sevk ağacı `PEMF_BUILD\\dist\\PEMF_Backend\\_internal\\python310.dll` FileVersion 3.10.2 (SHA-256 gömülü derleme
Python'unun `python310.dll`'iyle AYNI); derleme betiği (`scripts/build_backend_exe.ps1`) myenv yoksa gömülü 3.10.2'yi kullanır. CI ise
setup-python "3.10" ile 3.10.11 kuruyordu (gh-101283 sınıfı davranış farkı: YS1g alt süreç bekçisi). Kaynak TEK: `scripts/ci_sozlesmesi.json`
`urun_python`. Ürünü yükseltmek AYRI karar ([SAHİBE]) — CI ürüne uydurulur.
  · ürün Python kodunu KOŞAN her Windows işi (setup-python) TAM yama sürümüyle
  · ubuntu işleri (ruff · pip-audit `--disable-pip`) yorumlayıcıdan bağımsız; 22.04 / 24.04'te 3.10.2 tekerleği yok → aynı KÜÇÜK sürüm
  · yayın makinesinde (Y30) sevk ağacının DLL'i sözleşmeyle aynı (yalnız yayın makinesi — CI'da gerekçeli atlar)
"""

from __future__ import annotations

import ctypes
import json
import os
import sys
from pathlib import Path

import pytest
import yaml

KOK = Path(__file__).resolve().parents[1]
W = KOK / ".github" / "workflows"
URUN = json.loads((KOK / "scripts" / "ci_sozlesmesi.json").read_text(encoding="utf-8"))["urun_python"]


def _setup_pythonlar() -> list[tuple[str, str, str, str]]:
    """(dosya, iş, koşucu, python-version) — her setup-python adımı."""
    sonuc = []
    for p in sorted(W.glob("*.yml")):
        d = yaml.safe_load(p.read_text(encoding="utf-8"))
        for is_id, is_ in (d.get("jobs") or {}).items():
            kosucu = str(is_.get("runs-on", ""))
            if "matrix.os" in kosucu:
                m = is_["strategy"]["matrix"]
                kosucu = " ".join(m.get("os") or [x["os"] for x in m.get("include", [])])
            for a in is_.get("steps") or []:
                if str(a.get("uses", "")).startswith("actions/setup-python@"):
                    sonuc.append((p.name, is_id, kosucu, str((a.get("with") or {}).get("python-version"))))
    return sonuc


def ihlaller(kayitlar: list[tuple[str, str, str, str]], urun: str) -> list[str]:
    kucuk = ".".join(urun.split(".")[:2])
    sorun = []
    for dosya, is_, kosucu, surum in kayitlar:
        if "windows" in kosucu:
            if surum != urun:
                sorun.append(f"{dosya}/{is_}: Windows işi python-version {surum!r} ≠ ürün {urun!r}")
        elif surum != kucuk:
            sorun.append(f"{dosya}/{is_}: {kosucu} işi python-version {surum!r} ≠ ürünün küçük sürümü {kucuk!r}")
    return sorun


def test_KRITIK_CI_python_URUN_yamasiyla_AYNI():
    kayit = _setup_pythonlar()
    assert any("windows" in k for _, _, k, _ in kayit), "VAKUM: Windows setup-python adımı bulunamadı"
    assert not ihlaller(kayit, URUN), ihlaller(kayit, URUN)
    windows = [(d, i) for d, i, k, s in kayit if "windows" in k]
    assert ("tests.yml", "backend") in windows and ("tests.yml", "firmware") in windows, windows


def test_KARSIT_olcu_kor_degil():
    assert ihlaller([("x.yml", "b", "windows-latest", "3.10")], "3.10.2"), (
        "\"3.10\" (setup-python → 3.10.11) yakalanmadı"
    )
    assert ihlaller([("x.yml", "b", "windows-latest", "3.10.11")], "3.10.2")
    assert ihlaller([("x.yml", "l", "ubuntu-latest", "3.11")], "3.10.2")
    assert not ihlaller([("x.yml", "l", "ubuntu-latest", "3.10"), ("x.yml", "b", "windows-latest", "3.10.2")], "3.10.2")


def _dll_surumu(yol: Path) -> str:
    """Windows sürüm kaynağından CPython sürümü (a.b.c)."""
    ver = ctypes.windll.version
    boy = ver.GetFileVersionInfoSizeW(str(yol), None)
    assert boy, f"sürüm kaynağı yok: {yol}"
    tampon = ctypes.create_string_buffer(boy)
    assert ver.GetFileVersionInfoW(str(yol), 0, boy, tampon)
    isaretci, uzunluk = ctypes.c_void_p(), ctypes.c_uint()
    assert ver.VerQueryValueW(tampon, "\\", ctypes.byref(isaretci), ctypes.byref(uzunluk))
    ms, ls = ctypes.cast(isaretci, ctypes.POINTER(ctypes.c_uint32 * 4)).contents[2:4]
    # CPython FILEVERSION 3. alanı = MİKRO × 1000 + düzey × 10 + seri (3.10.2 son sürüm → 2150)
    return f"{ms >> 16}.{ms & 0xFFFF}.{(ls >> 16) // 1000}"


@pytest.mark.yalniz_yayin_makinesi  # CT2 b: sevk ağacı yalnız yayın makinesinde — CI'da gerekçeli atlar, Y30'da atlarsa KIRMIZI
def test_KRITIK_sevk_agacinin_python_DLLi_SOZLESMEYLE_AYNI():
    agac = os.environ.get("PEMF_SEVK_AGACI", "").strip()
    if not agac or sys.platform != "win32":
        pytest.skip("PEMF_SEVK_AGACI verilmedi (sevk ağacı yalnız yayın makinesinde; Y30 betiği verir)")
    dll = sorted(Path(agac).glob("**/python3[0-9]*.dll"))
    assert dll, f"sevk ağacında python3XY.dll yok: {agac}"
    surum = _dll_surumu(dll[0])
    assert surum == URUN, (
        f"ürün {surum} gönderiyor, CI {URUN} ile koşuyor — scripts/ci_sozlesmesi.json `urun_python` + iş akışları güncellenmeli "
        "(ürünü yükseltmek AYRI karar)"
    )


def test_dll_surum_okuyucu_GERCEK_dll_ile(tmp_path):
    if sys.platform != "win32":
        pytest.skip("Windows sürüm kaynağı API'si")
    surum = _dll_surumu(Path(sys.base_prefix) / f"python{sys.version_info.major}{sys.version_info.minor}.dll")
    assert surum == ".".join(map(str, sys.version_info[:3])), surum
