# -*- coding: utf-8 -*-
"""D4.17 (B-9.2) · D4.18 (B-10.71) — onedir spec'i birinci-taraf ürün paketlerini (servers / utils / database / services /
controllers) `hiddenimports`'a GERÇEKTEN toplar; toplama boş dönerse derleme DURUR. (A-31: onefile spec'i D2.36'da silindi.)

ARIZA (F4 `283c419`, 2026-09-18'den beri): ürün paketleri `apps/backend`'e taşındı; spec `collect_submodules(pkg)`'u yalnız depo kökü
`sys.path`'teyken çağırıyor ve `except Exception: pass` ile yutuyordu → beş paketin beşi 0 modül (bugün zararsız: statik import
edilenler Analysis'in kendi taramasıyla giriyor). Ama YALNIZ dinamik yüklenen (string / importlib) yeni bir modül donmuş EXE'den
SESSİZCE düşer — örnek `services.credential_manager` PYZ dışı kalıyordu.

Ölçüm: spec PyInstaller OLMADAN, GERÇEK metniyle alt süreçte koşar (Analysis / PYZ / EXE / COLLECT sahte, `hiddenimports` yakalanır);
`collect_submodules` birinci-taraf paketler için GERÇEK PyInstaller işlevidir (yalıtılmış alt süreçte paketleri içe aktarır — derleme
DEĞİL), üçüncü-taraf paketler için boş (ağır içe aktarmaya girmeden). Veri toplayıcılar boş.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
SPEC = KOK / "build_tools" / "PEMF_Backend_onedir.spec"
BIRINCI_TARAF = ("controllers", "services", "database", "servers", "utils", "ai", "ai_hub")

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="spec yalnız Windows derlemesinde koşar")

_SURUCU = r'''
import json, os, sys, types
spec, cikti = sys.argv[1], sys.argv[2]
birinci = set(json.loads(os.environ["BIRINCI_TARAF"]))
bos_donsun = os.environ.get("BOS_DONSUN", "")
from PyInstaller.utils import hooks as _gercek
def _bos(*a, **k):
    return []
def _hepsi(*a, **k):
    return ([], [], [])
cagrilar = []
def _collect_submodules(pkg, *a, **k):
    if pkg not in birinci:
        # 4B-2.9: spec pickle-zorunlu üçüncü-taraf paket (sklearn) boşsa durur → sahte toplayıcı üçüncü-taraf için boş OLMAYAN liste
        return [pkg + "._sahte"]
    hedef = os.path.normcase(os.path.normpath(os.path.join(os.getcwd(), "apps", "backend")))
    cagrilar.append([pkg, any(os.path.normcase(os.path.normpath(p)) == hedef for p in sys.path)])
    if pkg == bos_donsun:
        return []
    return _gercek.collect_submodules(pkg, *a, **k)
hooks = types.ModuleType("PyInstaller.utils.hooks")
hooks.collect_data_files = hooks.collect_dynamic_libs = hooks.copy_metadata = _bos
hooks.collect_all = _hepsi
hooks.collect_submodules = _collect_submodules
sys.modules["PyInstaller.utils.hooks"] = hooks
yakalanan = {}
class Analysis:
    def __init__(self, scripts, **kw):
        yakalanan["hidden"] = list(kw.get("hiddenimports", []))
        self.datas = [(os.path.join(d, os.path.basename(s)), s, "DATA") for s, d in kw.get("datas", [])]
        self.pure, self.scripts, self.binaries, self.zipfiles = [], [], [], []
class _Bos:
    def __init__(self, *a, **k):
        pass
g = {"__name__": "__main__", "__file__": spec, "Analysis": Analysis, "PYZ": _Bos, "EXE": _Bos, "COLLECT": _Bos}
exec(compile(open(spec, encoding="utf-8").read(), spec, "exec"), g)
yakalanan["cagrilar"] = cagrilar
json.dump(yakalanan, open(cikti, "w", encoding="utf-8"), ensure_ascii=False)
'''


def _kos(tmp_path: Path, bos_donsun: str = "") -> tuple[subprocess.CompletedProcess, dict]:
    surucu, cikti = tmp_path / "surucu.py", tmp_path / "cikti.json"
    surucu.write_text(_SURUCU, encoding="utf-8")
    env = {**os.environ, "BIRINCI_TARAF": json.dumps(BIRINCI_TARAF), "BOS_DONSUN": bos_donsun, "PEMF_EMBED_MODELS": "0"}
    p = subprocess.run(
        [sys.executable, str(surucu), str(SPEC), str(cikti)],
        cwd=str(KOK),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=600,
    )
    return p, (json.loads(cikti.read_text(encoding="utf-8")) if cikti.exists() else {})


@pytest.fixture(scope="module")
def kosum(tmp_path_factory) -> dict:
    p, veri = _kos(tmp_path_factory.mktemp("spec_d418"))
    assert p.returncode == 0 and veri, f"spec koşmadı (rc={p.returncode}):\n{p.stdout[-1500:]}\n{p.stderr[-1500:]}"
    return veri


def test_KRITIK_birinci_taraf_paketler_hiddenimports_ta_D418(kosum):
    hidden = set(kosum["hidden"])
    for onek in ("servers.", "utils.", "database.", "services.", "controllers."):
        assert any(h.startswith(onek) for h in hidden), (
            f"'{onek}*' hiddenimports'ta YOK — collect_submodules apps/backend yola girmeden cagriliyor; "
            "yalniz dinamik yuklenen bir urun modulu donmus EXE'den SESSIZCE duser"
        )


def test_KRITIK_dinamik_yuklenen_modul_TOPLANIR_D417(kosum):
    assert "services.credential_manager" in set(kosum["hidden"]), (
        "services.credential_manager toplanmadi (PYZ disi kalir)"
    )


def test_KRITIK_collect_submodules_apps_backend_YOLDAYKEN_cagrilir(kosum):
    yolsuz = sorted(
        {
            pkg
            for pkg, yolda in kosum["cagrilar"]
            if not yolda and pkg in ("controllers", "services", "database", "servers", "utils")
        }
    )
    assert kosum["cagrilar"], "spec birinci-taraf paket icin collect_submodules HIC cagirmadi (vakum)"
    assert not yolsuz, f"bu paketler apps/backend sys.path'te DEGILKEN toplandi: {yolsuz}"


def test_KRITIK_birinci_taraf_toplama_BOS_donerse_derleme_DURUR_D417(tmp_path):
    """`except: pass` / boş liste sessizce geçilmemeli: toplama 0 modül dönerse spec SystemExit ile durmalı (derleme DURUR)."""
    p, _ = _kos(tmp_path, bos_donsun="services")
    assert p.returncode != 0, f"services 0 modul dondugu halde spec BASARIYLA bitti (sessiz dusus):\n{p.stdout[-1200:]}"
    assert "services" in (p.stdout + p.stderr), (
        f"hangi paketin bos dondugu soylenmedi:\n{(p.stdout + p.stderr)[-1200:]}"
    )
