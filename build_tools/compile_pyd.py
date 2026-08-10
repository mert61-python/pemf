# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""`.py → .pyd` NATIVE DERLEME (Cython) — kaynağı gerçekten yok eden koruma (2026-08-06).

ŞİFRELEMEDEN FARKI (önemli): şifrelemede anahtar üründe gider, kararlı bir rakip kaynağı
geri alabilir. Burada kaynak DERLENİR — geriye makine kodu kalır, `.py` diye bir şey yoktur.
İkisi tamamlayıcıdır: derlenemeyen modüller şifreli kalır.

KULLANIM (build_backend_exe.ps1 SONRASI, encrypt_sources.py YERİNE ya da ONDAN ÖNCE):
    python build_tools/compile_pyd.py --list          # neyin derleneceğini göster
    python build_tools/compile_pyd.py --only inference_em_fantom
    python build_tools/compile_pyd.py                 # hepsini dene
    python build_tools/compile_pyd.py --keep-py       # .py'yi SİLME (karşılaştırma/hata ayıklama)

⚠️ HER MODÜL DERLENMEZ. Cython'ın zorlandığı desenler:
   * `__file__` ile yanındaki veri dosyasını bulan modüller (yol değişir)
   * çalışma anında kendi kaynağını okuyan/inspect eden kod
   * bazı dinamik `import` / `globals()` kullanımları
Bu yüzden betik modül BAŞINA çalışır, başarısızları RAPORLAR ve o modüller `.py` kalır —
"hepsi derlendi" gibi yanlış güvence vermez. Derlenmeyenler şifrelemeye bırakılmalıdır.

⚠️ Derlemeden sonra ilgili modülün GERÇEKTEN çalıştığı sınanmalı (import + bir çağrı).
Derlenmiş ama çalışmayan bir modül, sahada ilk analizde patlar.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

GUII = Path(__file__).resolve().parent.parent

# Derlenmeyecekler: paket keşfi bunlara İSİMDEN bakar; .pyd'ye çevrilirse paket bozulur.
SKIP_NAMES = {"__init__.py", "setup.py", "conftest.py"}
SKIP_DIRS = {"__pycache__", "PEMF_AI_Test_Girdileri", "results"}


def hedefler(dist: Path) -> list[Path]:
    base = dist / "_internal" / "ai_hub"
    if not base.exists():
        return []
    out = []
    for p in base.rglob("*.py"):
        if p.name in SKIP_NAMES or any(d in p.parts for d in SKIP_DIRS):
            continue
        out.append(p)
    return sorted(out)


def derle(py: Path, keep_py: bool) -> tuple[bool, str]:
    """Tek modülü .pyd'ye derle. Dönen: (başarılı mı, mesaj)."""
    tmp = Path(tempfile.mkdtemp(prefix="pemf_cy_"))
    try:
        kopya = tmp / py.name
        shutil.copy2(py, kopya)
        setup_py = tmp / "_setup.py"
        setup_py.write_text(
            "from setuptools import setup\n"
            "from Cython.Build import cythonize\n"
            f"setup(ext_modules=cythonize([r'{kopya}'], "
            "compiler_directives={'language_level': '3'}, quiet=True), script_args=['build_ext', '--inplace'])\n",
            encoding="utf-8",
        )
        r = subprocess.run([sys.executable, str(setup_py)], cwd=str(tmp), capture_output=True, text=True, timeout=600)
        if r.returncode != 0:
            son = (r.stderr or r.stdout or "").strip().splitlines()
            return False, (son[-1] if son else f"exit {r.returncode}")
        pyd = next(iter(tmp.glob(f"{py.stem}*.pyd")), None)
        if not pyd:
            return False, ".pyd üretilmedi"
        shutil.copy2(pyd, py.parent / pyd.name)
        if not keep_py:
            py.unlink()  # asıl amaç: kaynağı KALDIR
        return True, pyd.name
    except subprocess.TimeoutExpired:
        return False, "derleme zaman aşımı (600 sn)"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=".py → .pyd native derleme (Cython)")
    ap.add_argument("--dist", default=str(GUII / "PEMF_BUILD" / "dist" / "PEMF_Backend"))
    ap.add_argument("--only", default="", help="yalnız adı bunu içeren modülleri derle")
    ap.add_argument("--list", action="store_true", help="listele, derleme")
    ap.add_argument("--keep-py", action="store_true", help=".py dosyasını silme")
    a = ap.parse_args()

    dist = Path(a.dist).resolve()
    if "dist" not in [p.lower() for p in dist.parts]:
        print(f"HATA: hedef 'dist' içermiyor → kaynak ağacı olabilir, DURDUM: {dist}")
        return 2
    try:
        import Cython  # noqa: F401
    except Exception:
        print("HATA: Cython kurulu değil.  python -m pip install Cython")
        return 2

    liste = hedefler(dist)
    if a.only:
        liste = [p for p in liste if a.only.lower() in p.name.lower()]
    if not liste:
        print("Derlenecek modül yok (zaten derlenmiş/şifrelenmiş olabilir).")
        return 0

    print(f"Hedef : {dist}")
    print(f"Modül : {len(liste)}")
    if a.list:
        for p in liste:
            print(f"  {p.relative_to(dist)}")
        return 0

    ok, hata = [], []
    for i, p in enumerate(liste, 1):
        print(f"  [{i}/{len(liste)}] {p.name} … ", end="", flush=True)
        basarili, msg = derle(p, a.keep_py)
        if basarili:
            ok.append(p.name)
            print("OK")
        else:
            hata.append((p.name, msg))
            print(f"BASARISIZ ({msg[:90]})")

    print(f"\nDerlendi : {len(ok)}")
    print(f"Başarısız: {len(hata)}   ← bunlar .py KALDI, şifrelemeye bırakın")
    for n, m in hata:
        print(f"  - {n}: {m[:110]}")
    if hata:
        print("\n⚠️ Başarısızlar için `encrypt_sources.py` çalıştırın; aksi halde o modüller")
        print("   düz kaynak olarak dağıtılır.")
    print("\n⚠️ ZORUNLU SONRAKİ ADIM: EXE'yi çalıştırıp derlenen modüllerin GERÇEKTEN")
    print("   çalıştığını sınayın. Derlenmiş ama bozuk modül sahada ilk analizde patlar.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
