#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""
Headless import-graph checker for the PEMF backend.

Statically walks the first-party import graph using `ast` only -- no third-party
packages needed, so it runs on any Python 3.8+ even WITHOUT the heavy ML/Qt stack
installed. It models what actually happens when PyQt6 is NOT installed.

Every import edge is classified on two axes:
  * timing  : EAGER (runs at import: module top-level, inside top-level
              try/if/with/for/while, CLASS BODY, decorators/defaults) vs LAZY
              (inside a def/lambda body).
  * guard   : OPEN (plain) vs GUARDED (inside the `try:` BODY of a
              `try: ... except ImportError:` that does not re-raise). An import in
              an `except` / `else` / `finally` branch is OPEN.
Dynamic imports with a literal name (`importlib.import_module("x")`,
`__import__("x")`) and `matplotlib.use("<Qt/Tk backend>")` count as imports.

A GUARDED import degrades gracefully when the target is missing, so it is a SAFE
boundary -- Qt-absence never crashes past it. The checker therefore does NOT
propagate "reaches Qt" through guarded edges, and does NOT treat guarded Qt
imports as breaks.

Two problem tiers are reported:

  1. HARD BREAK   -- a module reachable from a startup root via ONLY open-eager
     edges has an OPEN (unguarded) module-level Qt import. The process tries to
     import Qt the instant it starts -> headless deployment fails.

  2. LAZY GATEWAY -- an eager-reachable (otherwise clean) module reaches Qt via an
     OPEN lazy edge. Qt loads only if that code path runs (e.g. an endpoint).
     Does not block startup, but the feature breaks without Qt.

Guarded boundaries into Qt-tainted modules are listed separately as SAFE, for
transparency (e.g. opt-in legacy services behind try/except).

Startup roots default to `backend_service` + `servers.api_server` because
backend_service.main() imports api_server unconditionally at startup.

  3. EXE EXCLUDE RISK -- a reachable module OPENLY imports a module that the
     onedir spec removes from the EXE (`Analysis(excludes=[...])`, read from the
     spec itself) -> ModuleNotFoundError in the frozen EXE.

Exit code 1 if any HARD BREAK or EXE EXCLUDE RISK is found; 2 if a startup root,
the spec's excludes or a reachable first-party module cannot be resolved/parsed
(PyInstaller drops an unparsable module silently -- 4B-1.3); else 0. Use as a
pre-build / CI guard.

@author : migration tooling (Faz 0)
"""

from __future__ import annotations

import ast
import re
import sys
from collections import deque
from pathlib import Path

GUI_PACKAGES = {
    "PyQt6", "PyQt5", "PyQt4", "PySide6", "PySide2", "pyqtgraph", "PyOpenGL", "OpenGL",
    # D4.28 (B-10.93): Qt soyutlamasi ve Tk de GUI'dir — spec tkinter'i EXE'den CIKARIR (donmus EXE'de YOK).
    "qtpy", "tkinter", "_tkinter", "Tkinter", "wx",
}  # fmt: skip
#: Headless'te mesru bir paketin GUI ALT modulleri: matplotlib'in Qt/Tk backend'leri (spec Qt olanlari cikarir).
GUI_MODUL_ONEKLERI = (
    "matplotlib.backends.backend_qt",
    "matplotlib.backends.backend_tk",
    "matplotlib.backends.qt_compat",
)
#: `matplotlib.use("<backend>")` ile secilen GUI backend'i (Agg/pdf/svg mesru).
_MPL_GUI_BACKEND = re.compile(r"qt|tk|wx|gtk", re.IGNORECASE)
SAFE_HANDLERS = {"ImportError", "ModuleNotFoundError", "Exception", "BaseException"}
_TRY_DUGUMLERI = (ast.Try, *((ast.TryStar,) if hasattr(ast, "TryStar") else ()))
# ⚠️ D4.28 (B-10.93): spec'in EXE'den CIKARDIGI moduller TEK KAYNAKTAN, spec'in `Analysis(excludes=[...])`
# listesinden okunur (`spec_excludes`). Eskiden burada elle tutulan {windows, pemf_gui, styles, threads}
# spec'ten ayrismisti: spec tkinter + mpl Qt backend'lerini cikariyor, pemf_gui'yi CIKARMIYOR
# (pemf_gui.config headless'te canli). Headless zincir cikarilan bir modulu ACIK import ederse donmus EXE
# ModuleNotFoundError verir -> guard KIRMIZI (eskiden yalniz yazdiriliyordu, cikis 0 kaliyordu).
SPEC_GORELI = Path("build_tools") / "PEMF_Backend_onedir.spec"
ROOT = Path(__file__).resolve().parents[1]  # guii/
DEFAULT_ROOTS = ["backend_service", "servers.api_server"]


#: Import KOKLERI. `apps/backend` 2026-09-18'de (F4) eklendi; giris noktalari da
#: 2026-09-19'da (F-E) oraya tasindi. Import ADLARI degismedi (`servers.api_server`),
#: degisen yalniz DISK yolu — bu yuzden iki kok de aranir.
IMPORT_KOKLERI = [ROOT, ROOT / "apps" / "backend"]


def module_to_path(modname: str):
    """Map 'a.b.c' -> <kok>/a/b/c.py or <kok>/a/b/c/__init__.py (None if not first-party)."""
    parts = modname.split(".")
    for kok in IMPORT_KOKLERI:
        base = kok.joinpath(*parts)
        if base.with_suffix(".py").is_file():
            return base.with_suffix(".py")
        if (base / "__init__.py").is_file():
            return base / "__init__.py"
    return None


def _resolve_relative(path: Path, level: int, module):
    """Resolve a relative import (from . / .. import x) to an absolute dotted name."""
    try:
        pkg_parts = list(path.parent.relative_to(ROOT).parts)
    except ValueError:
        return None
    climb = level - 1
    if climb > len(pkg_parts):
        return None
    if climb:
        pkg_parts = pkg_parts[:-climb]
    base = ".".join(pkg_parts)
    if module:
        return f"{base}.{module}" if base else module
    return base or None


def _gui_mi(ad: str) -> bool:
    return ad.split(".")[0] in GUI_PACKAGES or ad.startswith(GUI_MODUL_ONEKLERI)


def _haric_mi(ad: str, haric) -> bool:
    return any(ad == e or ad.startswith(e + ".") for e in haric)


def spec_excludes(spec: Path) -> tuple:
    """Onedir spec'inin `Analysis(excludes=[...])` listesi — donmus EXE'de OLMAYACAK moduller."""
    tree = ast.parse(spec.read_text(encoding="utf-8"), filename=str(spec))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "Analysis":
            for kw in node.keywords:
                if kw.arg == "excludes":
                    return tuple(ast.literal_eval(kw.value))
    raise ValueError(f"{spec}: Analysis(excludes=[...]) bulunamadi")


def _hemen_kosanlar(govde):
    """`govde` (deyim listesi) kosturuldugu AN calisan dugumler. def/lambda GOVDESINE inmez (cagrilinca kosar) ama
    dekoratorlere ve varsayilan degerlere iner (tanim aninda kosar). ⚠️ D4.28: SINIF GOVDESI de tanim aninda kosar —
    eskiden ClassDef atlaniyordu ve sinif govdesindeki `from PyQt6 import QtCore` guard'i YESIL geciyordu."""
    yigin = list(govde)
    while yigin:
        n = yigin.pop()
        yield n
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            yigin.extend(getattr(n, "decorator_list", ()))
            yigin.extend(n.args.defaults)
            yigin.extend(d for d in n.args.kw_defaults if d is not None)
        else:
            yigin.extend(ast.iter_child_nodes(n))


def _eager_import_ids(tree: ast.Module):
    """IDs of the nodes that execute at import time (see `_hemen_kosanlar`)."""
    return {id(n) for n in _hemen_kosanlar(tree.body)}


def _guvenli_handler(h: ast.ExceptHandler) -> bool:
    # `except ImportError: raise` yeniden firlatir -> koruma DEGIL (D4.28).
    if any(isinstance(s, ast.Raise) for s in h.body):
        return False
    if h.type is None:
        return True
    names = []
    if isinstance(h.type, ast.Name):
        names = [h.type.id]
    elif isinstance(h.type, ast.Tuple):
        names = [e.id for e in h.type.elts if isinstance(e, ast.Name)]
    return any(n in SAFE_HANDLERS for n in names)


def _guarded_import_ids(tree: ast.Module):
    """IDs of the nodes that execute inside the `try:` BODY of a try/except catching
    ImportError/ModuleNotFoundError/Exception/BaseException (or bare) without
    re-raising. Such an import degrades to a fallback instead of crashing -> a safe
    boundary. ⚠️ D4.28: `except` / `else` / `finally` branches are NOT protected by their
    own try (eskiden tum Try agaci korunmus sayiliyordu)."""
    guarded = set()
    for node in ast.walk(tree):
        if isinstance(node, _TRY_DUGUMLERI) and any(_guvenli_handler(h) for h in node.handlers):
            guarded.update(id(n) for n in _hemen_kosanlar(node.body))
    return guarded


def _dinamik_import_adi(node, mpl_adlari):
    """`importlib.import_module("x")` / `import_module("x")` / `__import__("x")` -> "x";
    `<matplotlib>.use("QtAgg")` -> "matplotlib.backends.backend_qtagg". Sabit dize olmayan ad -> None."""
    if not isinstance(node, ast.Call) or not node.args:
        return None
    a0 = node.args[0]
    if not (isinstance(a0, ast.Constant) and isinstance(a0.value, str)) or not a0.value:
        return None
    f = node.func
    ad = f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else None)
    if ad in ("import_module", "__import__"):
        return None if a0.value.startswith(".") else a0.value
    if ad == "use" and isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id in mpl_adlari:
        return f"matplotlib.backends.backend_{a0.value.lower()}" if _MPL_GUI_BACKEND.search(a0.value) else None
    return None


# dependency buckets: (timing, guard); ex_* = spec'in EXE'den cikardigi moduller (acik / korunan)
_KEYS = ("fp_eager", "fp_eager_g", "fp_lazy", "fp_lazy_g", "qt_eager", "qt_lazy", "qt_guarded", "ex_open", "ex_guarded")


def _empty():
    return {k: set() for k in _KEYS}


#: startup kokunden ulasilan ama AYRISTIRILAMAYAN birinci-taraf moduller {yol: neden} (4B-1.3) -> cikis 2.
AYRISTIRILAMAYAN: dict = {}


def analyze(path: Path, haric=()):
    """Return import buckets keyed by timing (eager/lazy) and guard (open/guarded).
    `haric`: spec'in EXE'den cikardigi moduller (`spec_excludes`) -> ex_open / ex_guarded."""
    src = path.read_text(encoding="utf-8", errors="ignore")
    try:
        tree = ast.parse(src, filename=str(path))
    except SyntaxError as e:
        # ⚠️ 4B-1.3: eskiden SESSIZCE bos sayiliyordu. PyInstaller da onu yalniz warn-*.txt'e "invalid module named"
        # yazip pakete ALMADAN surer (olculdu, 6.20) -> main() cikis 2 verir (yarim kapsamli yesil YOK).
        AYRISTIRILAMAYAN[str(path)] = f"{e.msg} (satir {e.lineno})"
        return _empty()

    eager_ids = _eager_import_ids(tree)
    guarded_ids = _guarded_import_ids(tree)
    out = _empty()
    mpl_adlari = {
        (a.asname or a.name)
        for n in ast.walk(tree)
        if isinstance(n, ast.Import)
        for a in n.names
        if a.name == "matplotlib"
    }

    def add(name: str, is_qt: bool, eager: bool, guarded: bool):
        if is_qt:
            out["qt_guarded" if guarded else ("qt_eager" if eager else "qt_lazy")].add(name)
        elif eager:
            out["fp_eager_g" if guarded else "fp_eager"].add(name)
        else:
            out["fp_lazy_g" if guarded else "fp_lazy"].add(name)

    def haric_kaydet(name: str, guarded: bool) -> bool:
        if haric and _haric_mi(name, haric):
            out["ex_guarded" if guarded else "ex_open"].add(name)
            return True
        return False

    def modul_kaydet(name: str, eager: bool, guarded: bool):
        haric_kaydet(name, guarded)
        if _gui_mi(name):
            add(name, True, eager, guarded)
        elif module_to_path(name) is not None:
            add(name, False, eager, guarded)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            eager = id(node) in eager_ids
            guarded = id(node) in guarded_ids
            for a in node.names:
                modul_kaydet(a.name, eager, guarded)

        elif isinstance(node, ast.ImportFrom):
            eager = id(node) in eager_ids
            guarded = id(node) in guarded_ids
            base = _resolve_relative(path, node.level, node.module) if node.level else node.module
            if not base:
                continue
            taban_haric = haric_kaydet(base, guarded)
            if _gui_mi(base):
                add(base, True, eager, guarded)
                continue
            handled = False
            for a in node.names:
                cand = f"{base}.{a.name}"
                if not taban_haric:
                    haric_kaydet(cand, guarded)
                if _gui_mi(cand):
                    add(cand, True, eager, guarded)
                    handled = True
                elif module_to_path(cand) is not None:
                    add(cand, False, eager, guarded)
                    handled = True
            if not handled and module_to_path(base) is not None:
                add(base, False, eager, guarded)

        else:
            # ⚠️ D4.28: sabit adli dinamik import (importlib / __import__) ve matplotlib GUI backend secimi de import'tur.
            dinamik = _dinamik_import_adi(node, mpl_adlari)
            if dinamik:
                modul_kaydet(dinamik, id(node) in eager_ids, id(node) in guarded_ids)

    return out


def main(argv):
    roots = argv[1:] or DEFAULT_ROOTS
    # ⚠️ SESSIZ KAPSAM KAYBI (2026-09-19'da olculdu): burada eskiden
    #     roots = [r for r in roots if module_to_path(r) is not None]
    # vardi. F4'te `servers/` -> `apps/backend/servers/` tasininca o kok
    # COZULEMEDI ve SESSIZCE listeden dustu; guard iki kokten BIRIYLE yesil
    # kalmaya devam etti. Kapsam yarilandi ve hicbir yerde uyari cikmadi.
    # Artik cozulemeyen kok HATADIR: yarim kapsamli yesil, kirmizidan tehlikelidir.
    cozulemeyen = [r for r in roots if module_to_path(r) is None]
    if cozulemeyen:
        print(f"HATA: giris modulu COZULEMEDI: {cozulemeyen}")
        print(f"      aranan kokler: {[str(k) for k in IMPORT_KOKLERI]}")
        print("      (tasindiysa IMPORT_KOKLERI ya da DEFAULT_ROOTS guncellenmeli)")
        return 2
    if not roots:
        print("HATA: gecerli giris modulu yok.")
        return 2
    # D4.28: EXE'den cikarilan moduller bilinmeden "exclude guvenli" denemez — spec okunamazsa yarim kapsamli yesil YOK.
    spec = ROOT / SPEC_GORELI
    try:
        haric = spec_excludes(spec)
    except (OSError, SyntaxError, ValueError) as e:
        print(f"HATA: spec excludes OKUNAMADI: {e}")
        print("      (EXE'den cikarilan moduller bilinmeden guard YESIL veremez)")
        return 2

    cache = {}
    AYRISTIRILAMAYAN.clear()

    def get(mod):
        if mod not in cache:
            p = module_to_path(mod)
            cache[mod] = analyze(p, haric) if p else None
        return cache[mod]

    # --- eager-reach: BFS following only OPEN eager edges (import-time closure) ---
    eager_parent = {}
    dq = deque()
    for r in roots:
        if r not in eager_parent:
            eager_parent[r] = None
            dq.append(r)
    while dq:
        mod = dq.popleft()
        info = get(mod)
        if not info:
            continue
        for dep in sorted(info["fp_eager"]):
            if dep not in eager_parent:
                eager_parent[dep] = mod
                dq.append(dep)
    eager_reach = set(eager_parent)

    # --- reaches_qt: OPEN edges only; guarded edges are safe boundaries ---
    memo = {}

    def reaches_qt(mod, stack=()):
        if mod in memo:
            return memo[mod]
        info = get(mod)
        if not info:
            memo[mod] = False
            return False
        if info["qt_eager"] or info["qt_lazy"]:
            memo[mod] = True
            return True
        if mod in stack:
            return False
        result = False
        for dep in info["fp_eager"] | info["fp_lazy"]:
            if reaches_qt(dep, stack + (mod,)):
                result = True
                break
        memo[mod] = result
        return result

    def chain(mod):
        out, cur = [mod], mod
        while eager_parent.get(cur):
            cur = eager_parent[cur]
            out.append(cur)
        return " <- ".join(out)

    # 1) HARD breaks
    hard = []
    for mod in sorted(eager_reach):
        info = get(mod)
        if info and info["qt_eager"]:
            hard.append((mod, sorted(info["qt_eager"])))

    # 2) LAZY gateways: OPEN lazy edge from a clean eager-reachable module into Qt
    gateways = []
    seen = set()
    for parent_mod in sorted(eager_reach):
        info = get(parent_mod)
        if not info:
            continue
        for child in sorted(info["fp_lazy"]):
            if child in eager_reach or child in seen:
                continue
            if reaches_qt(child):
                seen.add(child)
                ci = get(child)
                direct = sorted(ci["qt_eager"] | ci["qt_lazy"]) if ci else []
                gateways.append((parent_mod, child, direct))

    # 3) SAFE guarded boundaries into Qt-tainted modules (transparency)
    full = set()
    dq = deque(roots)
    full.update(roots)
    while dq:
        mod = dq.popleft()
        info = get(mod)
        if not info:
            continue
        for dep in info["fp_eager"] | info["fp_eager_g"] | info["fp_lazy"] | info["fp_lazy_g"]:
            if dep not in full:
                full.add(dep)
                dq.append(dep)
    boundaries = []
    seen_b = set()
    for parent_mod in sorted(full):
        info = get(parent_mod)
        if not info:
            continue
        for child in sorted(info["fp_eager_g"] | info["fp_lazy_g"]):
            if child in seen_b:
                continue
            if reaches_qt(child):
                seen_b.add(child)
                boundaries.append((parent_mod, child))

    print("== Headless import taramasi ==")
    print(f"Startup kokleri : {', '.join(roots)}")
    print(f"Eager (import-time) ulasilabilir modul: {len(eager_reach)} | tum ulasilabilir: {len(full)}")
    print()

    if hard:
        print(f"[X] HARD BREAK ({len(hard)}) -- startup'ta import-time'da Qt yuklenir, headless KIRAR:")
        for mod, qts in hard:
            print(f"    - {mod}  ->  {', '.join(qts)}")
            print(f"        eager zincir: {chain(mod)}")
    else:
        print("[OK] HARD BREAK YOK -- startup eager kapanisinda acik modul-seviyesi Qt importu yok.")
    print()

    if gateways:
        print(f"[!] LAZY GATEWAY ({len(gateways)}) -- temiz modul, Qt'li modulu ACIK lazy import ediyor")
        print("    (startup'i kirmaz; ilgili ozellik Qt'siz calismaz):")
        for parent_mod, child, direct in gateways:
            tail = f"  [dogrudan: {', '.join(direct)}]" if direct else "  [alt-agacta Qt]"
            print(f"    - {parent_mod}  --open-lazy-->  {child}{tail}")
    else:
        print("[OK] LAZY GATEWAY YOK.")
    print()

    if boundaries:
        print(f"[i] GUVENLI guarded sinir ({len(boundaries)}) -- try/except ile korunmus, Qt'siz graceful:")
        for parent_mod, child in boundaries:
            print(f"    - {parent_mod}  --guarded-->  {child}")
        print()

    # --- EXE excludes validasyonu: headless'in import ettigi, spec'in EXE'den CIKARDIGI moduller ---
    excl_open, excl_guarded = [], []
    for mod in sorted(full):
        info = get(mod)
        if not info:
            continue
        excl_open += [(mod, name) for name in sorted(info["ex_open"])]
        excl_guarded += [(mod, name) for name in sorted(info["ex_guarded"])]
    if excl_open:
        print(
            f"[X] EXE EXCLUDE RISKI ({len(excl_open)}) -- headless, spec'in EXE'den CIKARDIGI modulu ACIK import ediyor;"
        )
        print("    spec excludes'tan CIKARILMALI ya da import try/except ImportError ile korunmali,")
        print("    yoksa donmus EXE 'ModuleNotFoundError' verir:")
        for mod, name in excl_open:
            print(f"    - {mod}  ->  {name}")
        print()
    if excl_guarded:
        print(f"[i] spec'in cikardigi modul GUARDED import ({len(excl_guarded)}) -- exclude GUVENLI:")
        for mod, name in excl_guarded:
            print(f"    - {mod}  --guarded-->  {name}")
        print()

    if AYRISTIRILAMAYAN:
        print(
            f"HATA: ulasilan {len(AYRISTIRILAMAYAN)} birinci-taraf modul AYRISTIRILAMADI (PyInstaller onu pakete ALMAZ, derleme surer):"
        )
        for yol, neden in sorted(AYRISTIRILAMAYAN.items()):
            print(f"    - {yol}: {neden}")
        print("SONUC: KIRMIZI (ayristirilamayan modul -- tarama yarim kapsamli)")
        return 2
    if hard:
        print("SONUC: KIRMIZI (hard break var)")
    elif excl_open:
        print("SONUC: KIRMIZI (EXE exclude riski)")
    else:
        print("SONUC: YESIL (startup Qt-free)")
    return 1 if (hard or excl_open) else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
