# -*- coding: utf-8 -*-
"""D4.E02 (İG-9.23, 4-A devri) — onedir spec'inin `hookspath`'i `build_tools/` kancalarını HER derleme cwd'sinde görür.

ARIZA: spec `hookspath=[spec_dir]` diyordu; `spec_dir = os.getcwd()`. Üç ürün derleme yolu da (build_backend_exe.ps1, linux-backend.yml,
build_mac.sh) DEPO KÖKÜNDEN koşar → hookspath depo kökü, `build_tools/hook-paho.mqtt.py` SESSİZCE yüklenmiyordu (4-A incelemesi A3
ölçtü; kanıt `k4_4B_kapilari_HEAD.txt`).

Ölçüm: PyInstaller KOŞMADAN, spec'in KENDİ kodu: baş kısmı (`spec_dir` / `project_path`) verilen cwd ile çalıştırılır, `Analysis(...)`
çağrısındaki `hookspath` ifadesi AST'den alınıp AYNI isim alanında hesaplanır (hazır önce-kırmızı 4-A incelemesinden).
"""

from __future__ import annotations

import ast
import os
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
SPEC = KOK / "build_tools" / "PEMF_Backend_onedir.spec"


def _hookspath(cwd: Path) -> list[Path]:
    agac = ast.parse(SPEC.read_text(encoding="utf-8"))
    # yalnız `spec_dir` / `project_path` atamaları — PyInstaller içe aktarımı ve yan etki YOK
    bas = [d for d in agac.body if isinstance(d, (ast.Assign, ast.If)) and "spec_dir" in ast.unparse(d)][:2]
    ad_alani: dict = {"os": os}
    eski = os.getcwd()
    try:
        os.chdir(cwd)
        exec(compile(ast.Module(body=bas, type_ignores=[]), str(SPEC), "exec"), ad_alani)  # noqa: S102
    finally:
        os.chdir(eski)
    cagri = [n for n in ast.walk(agac) if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "Analysis"]
    assert len(cagri) == 1, f"Analysis çağrısı TAM 1 olmalı: {len(cagri)}"
    hp = [k.value for k in cagri[0].keywords if k.arg == "hookspath"]
    assert hp, "Analysis(hookspath=...) yok"
    return [Path(p).resolve() for p in eval(compile(ast.Expression(hp[0]), str(SPEC), "eval"), ad_alani)]  # noqa: S307


@pytest.mark.parametrize("cwd", ["depo_koku", "build_tools"])
def test_KRITIK_build_tools_kancalari_her_derleme_cwdsinde_YUKLENIR(cwd):
    kancalar = sorted(p.name for p in (KOK / "build_tools").glob("hook-*.py"))
    assert kancalar, "build_tools'ta kanca yok (vakum) — kanca silindiyse bu test de silinmeli"
    yollar = _hookspath(KOK if cwd == "depo_koku" else KOK / "build_tools")
    yuklenmeyen = [k for k in kancalar if not any((y / k).is_file() for y in yollar)]
    assert not yuklenmeyen, (
        f"[{cwd}] hookspath {[str(y) for y in yollar]} bu kancaları GÖRMEZ (sessizce yüklenmez): {yuklenmeyen}"
    )
