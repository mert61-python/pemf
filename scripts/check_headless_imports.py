#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""
Headless import-graph checker for the PEMF backend.

Statically walks the first-party import graph using `ast` only -- no third-party
packages needed, so it runs on any Python 3.8+ even WITHOUT the heavy ML/Qt stack
installed. It models what actually happens when PyQt6 is NOT installed.

Every import edge is classified on two axes:
  * timing  : EAGER (module top-level, runs at import) vs LAZY (inside a def).
  * guard   : OPEN (plain) vs GUARDED (inside `try: ... except ImportError:`).

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

Exit code 1 if any HARD BREAK is found, else 0. Use as a pre-build / CI guard.

@author : migration tooling (Faz 0)
"""

from __future__ import annotations

import ast
import sys
from collections import deque
from pathlib import Path

GUI_PACKAGES = {"PyQt6", "PyQt5", "PySide6", "PySide2", "pyqtgraph", "PyOpenGL", "OpenGL"}
SAFE_HANDLERS = {"ImportError", "ModuleNotFoundError", "Exception", "BaseException"}
# Birinci-parti paketler ki PyInstaller spec'te EXE'den exclude ediliyorlar (GUI/legacy).
# Headless zincir bunlardan birini ACIK (guard'sız) import ediyorsa, EXE runtime'da
# ModuleNotFoundError verir -> spec excludes'tan cikarilmalidir.
EXCLUDED_GUI_PACKAGES = {"windows", "pemf_gui", "styles", "threads"}
ROOT = Path(__file__).resolve().parents[1]  # guii/
DEFAULT_ROOTS = ["backend_service", "servers.api_server"]


def module_to_path(modname: str):
    """Map 'a.b.c' -> guii/a/b/c.py or guii/a/b/c/__init__.py (None if not first-party)."""
    parts = modname.split(".")
    base = ROOT.joinpath(*parts)
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


def _eager_import_ids(tree: ast.Module):
    """IDs of Import/ImportFrom nodes that execute at import time (top-level, or
    inside a top-level try/if/with/for/while). Imports nested inside a
    FunctionDef/ClassDef are NOT eager."""
    eager = set()

    def mark(node):
        for child in ast.walk(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            if isinstance(child, (ast.Import, ast.ImportFrom)):
                eager.add(id(child))

    for n in ast.iter_child_nodes(tree):
        if isinstance(n, (ast.Import, ast.ImportFrom)):
            eager.add(id(n))
        elif isinstance(n, (ast.Try, ast.If, ast.With, ast.For, ast.While)):
            mark(n)
    return eager


def _guarded_import_ids(tree: ast.Module):
    """IDs of Import/ImportFrom nodes wrapped in a try/except that catches
    ImportError/ModuleNotFoundError/Exception/BaseException (or is bare). Such an
    import degrades to a fallback instead of crashing -> a safe boundary."""
    guarded = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        safe = False
        for h in node.handlers:
            if h.type is None:
                safe = True
                break
            names = []
            if isinstance(h.type, ast.Name):
                names = [h.type.id]
            elif isinstance(h.type, ast.Tuple):
                names = [e.id for e in h.type.elts if isinstance(e, ast.Name)]
            if any(n in SAFE_HANDLERS for n in names):
                safe = True
                break
        if not safe:
            continue
        for child in ast.walk(node):
            if isinstance(child, (ast.Import, ast.ImportFrom)):
                guarded.add(id(child))
    return guarded


# dependency buckets: (timing, guard)
_KEYS = ("fp_eager", "fp_eager_g", "fp_lazy", "fp_lazy_g", "qt_eager", "qt_lazy", "qt_guarded")


def _empty():
    return {k: set() for k in _KEYS}


def analyze(path: Path):
    """Return import buckets keyed by timing (eager/lazy) and guard (open/guarded)."""
    src = path.read_text(encoding="utf-8", errors="ignore")
    try:
        tree = ast.parse(src, filename=str(path))
    except SyntaxError:
        return _empty()

    eager_ids = _eager_import_ids(tree)
    guarded_ids = _guarded_import_ids(tree)
    out = _empty()

    def add(name: str, is_qt: bool, eager: bool, guarded: bool):
        if is_qt:
            out["qt_guarded" if guarded else ("qt_eager" if eager else "qt_lazy")].add(name)
        elif eager:
            out["fp_eager_g" if guarded else "fp_eager"].add(name)
        else:
            out["fp_lazy_g" if guarded else "fp_lazy"].add(name)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            eager = id(node) in eager_ids
            guarded = id(node) in guarded_ids
            for a in node.names:
                if a.name.split(".")[0] in GUI_PACKAGES:
                    add(a.name, True, eager, guarded)
                elif module_to_path(a.name) is not None:
                    add(a.name, False, eager, guarded)

        elif isinstance(node, ast.ImportFrom):
            eager = id(node) in eager_ids
            guarded = id(node) in guarded_ids
            base = _resolve_relative(path, node.level, node.module) if node.level else node.module
            if not base:
                continue
            if base.split(".")[0] in GUI_PACKAGES:
                add(base, True, eager, guarded)
                continue
            handled = False
            for a in node.names:
                cand = f"{base}.{a.name}"
                if cand.split(".")[0] in GUI_PACKAGES:
                    add(cand, True, eager, guarded)
                    handled = True
                elif module_to_path(cand) is not None:
                    add(cand, False, eager, guarded)
                    handled = True
            if not handled and module_to_path(base) is not None:
                add(base, False, eager, guarded)

    return out


def main(argv):
    roots = argv[1:] or DEFAULT_ROOTS
    roots = [r for r in roots if module_to_path(r) is not None]
    if not roots:
        print("HATA: gecerli giris modulu yok.")
        return 2

    cache = {}

    def get(mod):
        if mod not in cache:
            p = module_to_path(mod)
            cache[mod] = analyze(p) if p else None
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

    # --- EXE excludes validasyonu: headless'in import ettigi GUI/legacy paketler ---
    excl_open, excl_guarded = [], []
    seen_e = set()
    for mod in sorted(full):
        info = get(mod)
        if not info:
            continue
        for name in sorted(info["fp_eager"] | info["fp_lazy"]):
            if name.split(".")[0] in EXCLUDED_GUI_PACKAGES and (mod, name) not in seen_e:
                seen_e.add((mod, name))
                excl_open.append((mod, name))
        for name in sorted(info["fp_eager_g"] | info["fp_lazy_g"]):
            if name.split(".")[0] in EXCLUDED_GUI_PACKAGES and (mod, name) not in seen_e:
                seen_e.add((mod, name))
                excl_guarded.append((mod, name))
    if excl_open:
        print(f"[X] EXE EXCLUDE RISKI ({len(excl_open)}) -- headless bu paketleri ACIK import ediyor;")
        print("    spec.excludes'tan CIKARILMALI, yoksa EXE 'ModuleNotFoundError' verir:")
        for mod, name in excl_open:
            print(f"    - {mod}  ->  {name}")
        print()
    if excl_guarded:
        print(f"[i] GUI/legacy paketi GUARDED import ({len(excl_guarded)}) -- exclude GUVENLI:")
        for mod, name in excl_guarded:
            print(f"    - {mod}  --guarded-->  {name}")
        print()

    print("SONUC:", "KIRMIZI (hard break var)" if hard else "YESIL (startup Qt-free)")
    return 1 if hard else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
