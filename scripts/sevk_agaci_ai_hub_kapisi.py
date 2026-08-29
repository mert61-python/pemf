# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""6. KORUMA KAPISI — kaynak ai_hub'daki HER modul sevk agacinda var mi? (denetim 2026-08-28 #07)

OLCULEN ARIZA. `PEMF_Backend_onedir.spec`teki torch kaynak-eleme filtresi YOL-CIPASIZDI:

    'torch' in x[0].lower() and x[0].endswith('.py')

`ai_hub/xai_tabular/ig_torch.py` ADINDA "torch" gectigi icin bu filtreye takiliyordu. Sonuc:
modul sevk agacina HIC girmiyordu (compile_pyd hedef listesi 65, ig_torch orada yok) ve urunde
YALNIZ PYZ bytecode'u olarak yasiyordu. `inference_human_kidney_rna.py:219` onu canli XAI
yolunda (`xai_top_genler`) LAZY import eder.

Bu, iki ayri sinifin kesisimi:
  (1) Kod korumasi: modul .pyd'ye hic derlenmedi -> korumasiz.
  (2) Sessiz olum: PYZ temizligi yapilinca (ki #07 duzeltmesi tam bunu yapar) modul TAMAMEN
      kaybolur ve RNA gen-katkisi aciklamasi sahada sessizce olur.

HICBIR MEVCUT KAPI BUNU GORMEZ:
  * dort koruma kapisi "diskte duz .py kaldi mi" diye sorar — olmayan dosya zaten .py degildir;
  * `/api/ai/hazirlik` yalniz _AI_MODUL_ENVANTERI'ndeki 15 UST modulu import eder;
  * `_xai_zinciri_durumu` kutuphaneleri (shap/captum/pytorch_grad_cam/ttach) yoklar;
  * `compile_pyd.py` yalniz KENDI listesini derler, listenin EKSIK olabilecegini sormaz.

Bu kapi kaynak agaci ile sevk agacini GORELI YOL uzerinden karsilastirir (dosya ADI ile DEGIL:
ai_hub'da yinelenen taban adlar var — pipeline.py x3, render.py x3, cabin_config.py x3 ...).

Kullanim:
    python scripts/sevk_agaci_ai_hub_kapisi.py PEMF_BUILD/dist/PEMF_Backend
Cikis: 0 tam, 1 eksik modul var.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# compile_pyd.py ile AYNI kurallar (sapma olmasin diye oradan okunur; okunamazsa kopya kullanilir).
_YEDEK_SKIP_NAMES = {"__init__.py", "setup.py", "conftest.py"}
_YEDEK_SKIP_DIRS = {"__pycache__", "PEMF_AI_Test_Girdileri", "results"}


def _skip_kurallari(kok: Path) -> tuple[set[str], set[str]]:
    """compile_pyd.py'deki SKIP kurallarini CALISTIRMADAN oku (tek kaynak)."""
    import ast

    dosya = kok / "build_tools" / "compile_pyd.py"
    if not dosya.is_file():
        return _YEDEK_SKIP_NAMES, _YEDEK_SKIP_DIRS
    adlar, dizinler = None, None
    for dugum in ast.parse(dosya.read_text(encoding="utf-8")).body:
        if not isinstance(dugum, ast.Assign):
            continue
        for hedef in dugum.targets:
            if not isinstance(hedef, ast.Name) or not isinstance(dugum.value, ast.Set):
                continue
            deger = {e.value for e in dugum.value.elts if isinstance(e, ast.Constant)}
            if hedef.id == "SKIP_NAMES":
                adlar = deger
            elif hedef.id == "SKIP_DIRS":
                dizinler = deger
    return (adlar or _YEDEK_SKIP_NAMES), (dizinler or _YEDEK_SKIP_DIRS)


def kaynak_modulleri(kok: Path, skip_names: set[str], skip_dirs: set[str]) -> set[str]:
    """Kaynak ai_hub'daki is-mantigi modulleri (goreli yol, uzantisiz)."""
    base = kok / "ai_hub"
    out = set()
    for p in base.rglob("*.py"):
        if p.name in skip_names or any(d in p.parts for d in skip_dirs):
            continue
        out.add(p.relative_to(base).with_suffix("").as_posix())
    return out


def sevk_modulleri(dist: Path) -> set[str]:
    """Sevk agacindaki ai_hub modulleri: .pyd / .pyenc / .py hepsi sayilir.

    Burada AMAC koruma olcmek DEGIL, KAYBI olcmek: modul hangi bicimde olursa olsun MEVCUT
    olmali. Koruma ayri kapilarin isi (pyz_koruma_kapisi.py + mevcut duz-.py kapilari)."""
    base = dist / "_internal" / "ai_hub"
    if not base.is_dir():
        base = dist / "ai_hub"
    out = set()
    if not base.is_dir():
        return out
    for p in base.rglob("*"):
        if not p.is_file():
            continue
        ad = p.name
        if ad.endswith(".pyd"):
            # cp310-win_amd64 gibi ABI ekini at: modul_a.cp310-win_amd64.pyd -> modul_a
            govde = ad.split(".")[0]
        elif ad.endswith(".pyenc"):
            govde = ad[: -len(".pyenc")]
        elif ad.endswith(".py"):
            govde = ad[: -len(".py")]
        elif ad.endswith(".so"):  # linux/mac
            govde = ad.split(".")[0]
        else:
            continue
        out.add((p.parent.relative_to(base) / govde).as_posix())
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("dist", type=Path, help="PEMF_BUILD/dist/PEMF_Backend")
    ap.add_argument("--kok", type=Path, default=None, help="proje koku (varsayilan: bu betigin ust dizini)")
    a = ap.parse_args()

    kok = a.kok or Path(__file__).resolve().parents[1]
    skip_names, skip_dirs = _skip_kurallari(kok)

    kaynak = kaynak_modulleri(kok, skip_names, skip_dirs)
    sevk = sevk_modulleri(a.dist)

    if not kaynak:
        print(f"[sevk-kapi] HATA: kaynak ai_hub bos okundu ({kok / 'ai_hub'}) — kapi hicbir sey olcmuyor.")
        return 1
    if not sevk:
        print(f"[sevk-kapi] HATA: sevk agacinda ai_hub yok ({a.dist}) — build eksik mi?")
        return 1

    eksik = sorted(kaynak - sevk)
    if eksik:
        print(f"[sevk-kapi] KIRMIZI: kaynakta olup sevk agacinda OLMAYAN {len(eksik)} ai_hub modulu:")
        for m in eksik[:15]:
            print(f"    - ai_hub/{m}.py")
        if len(eksik) > 15:
            print(f"    ... (+{len(eksik) - 15})")
        print(
            "[sevk-kapi] Bu moduller urunde YOK. Lazy import edilen biri varsa (or. ig_torch ->\n"
            "            inference_human_kidney_rna.py:219) ilgili ozellik SAHADA SESSIZCE OLUR;\n"
            "            hicbir mevcut kapi bunu gormez. Genellikle sebep spec'teki bir datas\n"
            "            filtresidir (yol-cipasiz 'torch'/'test' vb. desenler)."
        )
        return 1

    print(f"[sevk-kapi] Tam: kaynaktaki {len(kaynak)} ai_hub modulunun hepsi sevk agacinda var.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
