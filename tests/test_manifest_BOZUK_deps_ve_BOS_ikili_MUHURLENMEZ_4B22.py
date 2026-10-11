# -*- coding: utf-8 -*-
"""4B-2.2 (4-B incelemesi A2) — `make_manifest` AÇILAMAYAN deps katmanını ve 0 baytlık ikiliyi MÜHÜRLEMEMELİ.

D4.31 app katmanına asgari yapı + testzip denetimi ekledi; deps katmanına HİÇ bakılmıyor ("bilinen sınır"). Ölçüldü
(`_inceleme/kayit/k1_manifest_girdi_sonda.txt`): 0 baytlık, kesik (merkezi dizinsiz), girdisiz ve zip OLMAYAN `base-deps.zip`
çıkış 0 ile `layers.win-x64.deps`'e mühürlenir; app'te 0 baytlık `PEMF_Backend.exe` de çıkış 0. Mühürlenen sha yüklenen dosyayla
aynı olduğu için launcher'ın sha denetimi geçer, AÇMA düşer: deps'i değişen her kurulum (taze kurulum, "Onar") kırılır.
Ucuz yapısal denetim (merkezi dizin açılır + en az bir girdi; 1,2 GB'ta testzip YOK) bu sınıfı yakalar.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
MAKE_MANIFEST = KOK / "scripts" / "make_manifest.py"

ONCEKI = {
    "schema": 2,
    "version": "1.9.50",
    "tag": "client-app-v1.9.50",
    "launcher": {"version": "1.9.51", "url": "https://x.invalid/setup.exe", "sha256": "a" * 64, "size": 1},
    "layers": {
        "win-x64": {
            "rollout": 100,
            "app": {"url": "https://x.invalid/a/base-app.zip", "sha256": "c" * 64, "size": 3, "kind": "zip"},
            "deps": {"url": "https://x.invalid/b/base-deps.zip", "sha256": "d" * 64, "size": 4, "kind": "zip"},
        }
    },
    "runtimes": {},
    "models": {},
    "profiles": {},
}


def _zip(yol: Path, girdiler: dict[str, bytes]) -> None:
    with zipfile.ZipFile(yol, "w", zipfile.ZIP_STORED) as z:
        for ad, veri in girdiler.items():
            z.writestr(ad, veri)


def _iyi_deps_bayt(tmp: Path) -> bytes:
    _zip(tmp / "_d.zip", {"PEMF_Backend/_internal/torch/lib.dll": b"DEPS" * 100})
    b = (tmp / "_d.zip").read_bytes()
    (tmp / "_d.zip").unlink()
    return b


def _kos(d: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable,
            str(MAKE_MANIFEST),
            "--dir",
            str(d),
            "--version",
            "1.9.52",
            "--tag",
            "client-app-v1.9.52",
            "--repo",
            "ornek/ornek",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        timeout=120,
    )


@pytest.fixture
def dizin(tmp_path):
    (tmp_path / "manifest.json").write_text(json.dumps(ONCEKI), encoding="utf-8")
    _zip(tmp_path / "base-app.zip", {"PEMF_Backend/PEMF_Backend.exe": b"EXE", "PEMF_Backend/_app_roots.json": b"{}"})
    return tmp_path


@pytest.mark.parametrize("vaka", ["sifir_bayt", "kesik_merkezi_dizinsiz", "girdisiz_zip", "zip_degil"])
def test_KRITIK_acilamayan_deps_katmani_MUHURLENMEZ(dizin, vaka):
    iyi = _iyi_deps_bayt(dizin)
    yol = dizin / "base-deps.zip"
    if vaka == "sifir_bayt":
        yol.write_bytes(b"")
    elif vaka == "kesik_merkezi_dizinsiz":
        yol.write_bytes(iyi[:-40])
    elif vaka == "girdisiz_zip":
        _zip(yol, {})
    else:
        yol.write_bytes(b"bu bir zip degil")
    r = _kos(dizin)
    assert r.returncode == 1, f"{vaka}: bozuk base-deps.zip manifeste MUHURLENDI (rc={r.returncode})\n{r.stderr[-800:]}"
    assert "base-deps.zip" in r.stderr and "manifest YAZILMADI" in r.stderr, r.stderr[-800:]
    assert json.loads((dizin / "manifest.json").read_text(encoding="utf-8")) == ONCEKI, f"{vaka}: manifest yazildi"


def test_KRITIK_sifir_baytlik_EXE_MUHURLENMEZ(dizin):
    _zip(dizin / "base-app.zip", {"PEMF_Backend/PEMF_Backend.exe": b"", "PEMF_Backend/_app_roots.json": b"{}"})
    (dizin / "base-deps.zip").write_bytes(_iyi_deps_bayt(dizin))
    r = _kos(dizin)
    assert r.returncode == 1, f"0 baytlik PEMF_Backend.exe muhurlendi (rc={r.returncode})\n{r.stderr[-800:]}"
    assert "PEMF_Backend/PEMF_Backend.exe" in r.stderr, r.stderr[-800:]


def test_KRITIK_CRC_bozuk_ama_ACILABILIR_app_MUHURLENMEZ(dizin):
    """KÖR KAPI güçlendirmesi (HEAD'de YEŞİL): D4.31'in `testzip` kolu hiçbir testte tek başına ölçülmüyordu — `bozuk = None`
    mutantı 4-B'nin 32 dosyalık kümesinde YEŞİL kaldı (`_inceleme/kayit/k1_*`). Merkezi dizin sağlam, EXE verisi bozuk (CRC)."""
    _zip(
        dizin / "base-app.zip", {"PEMF_Backend/PEMF_Backend.exe": b"EXE-ICERIGI", "PEMF_Backend/_app_roots.json": b"{}"}
    )
    ham = bytearray((dizin / "base-app.zip").read_bytes())
    i = ham.find(b"EXE-ICERIGI")
    ham[i : i + 3] = b"XXX"
    (dizin / "base-app.zip").write_bytes(bytes(ham))
    (dizin / "base-deps.zip").write_bytes(_iyi_deps_bayt(dizin))
    r = _kos(dizin)
    assert r.returncode == 1, f"CRC'si bozuk base-app.zip muhurlendi (rc={r.returncode})\n{r.stderr[-800:]}"
    assert "BOZUK girdi" in r.stderr, r.stderr[-800:]


def test_KARSIT_acilabilir_deps_ve_dolu_EXE_MUHURLENIR(dizin):
    (dizin / "base-deps.zip").write_bytes(_iyi_deps_bayt(dizin))
    r = _kos(dizin)
    assert r.returncode == 0, r.stderr[-1200:]
    m = json.loads((dizin / "manifest.json").read_text(encoding="utf-8"))
    assert m["layers"]["win-x64"]["deps"]["url"].endswith("client-app-v1.9.52/base-deps.zip")
