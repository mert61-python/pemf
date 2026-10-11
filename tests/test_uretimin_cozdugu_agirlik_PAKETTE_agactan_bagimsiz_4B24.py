# -*- coding: utf-8 -*-
"""4B-2.4 (4-B incelemesi A2) — ÜRETİMİN çözdüğü her ağırlık bir launcher paketinde; kapı ağırlık ağacından BAĞIMSIZ.

Kör nokta (ölçüldü, `_inceleme/kayit/k2_mutasyon.txt`): profilden bir ağırlık düşürülünce (home `cat_disease/XGBoost.onnx`,
vet `cat_thermal/GhostNetV2.pt`, research `renal …kmc.onnx`) D4.27'nin 51 dosyalık kümesi YEŞİL kalır:
  · D4.27 envanter kolu yalnız diskte BULUNAN `release_assets` dosyalarını gezer — temiz klonda/CI'da yalnız 11 izlenen küçük
    dosya var (büyük ağırlıklar izlenmez) → profil ağırlıklarını hiç görmez;
  · `test_ai_hazirlik_envanteri::test_envanter_yollari_model_paketi_listeleriyle_TUTARLI` ağaç kurulu değilse ATLANIR.
Bu kapı beklenen kümeyi ÜRETİM KODUNDAN türetir (`_AI_MODUL_ENVANTERI` + `ai_router`'daki `download_model_sync("…")` çağrıları)
ve paket kümesini KODDAN (PROFILLER / PARCALAR / CORE_MODELS + D4.27'nin app-katmanı kuralı = depoda İZLENEN `release_assets`
dosyaları) okur — diskteki ağırlıklara bakmaz, atlanmaz.
"""

from __future__ import annotations

import ast
import importlib.util
import re
import subprocess
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]


def _mmz():
    s = importlib.util.spec_from_file_location("_mmz_4b24", KOK / "build_tools" / "make_model_zip.py")
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def _cekirdek() -> tuple[str, ...]:
    for d in ast.parse((KOK / "build_tools" / "make_base_zip.py").read_text(encoding="utf-8")).body:
        if isinstance(d, ast.Assign) and any(getattr(h, "id", "") == "CORE_MODELS" for h in d.targets):
            return tuple(v.replace("pemf_backend/_internal/ai_models/", "") for v in ast.literal_eval(d.value))
    raise AssertionError("CORE_MODELS bulunamadi")


def _izlenen_app_katmani() -> set[str]:
    ham = subprocess.run(
        ["git", "-c", "core.quotepath=off", "ls-files", "-z", "--", "release_assets/ai_models"],
        cwd=KOK,
        capture_output=True,
        timeout=120,
    ).stdout
    on = "release_assets/ai_models/"
    return {x.decode("utf-8")[len(on) :] for x in ham.split(b"\x00") if x}


def _uretimin_cozdugu() -> set[str]:
    src = (KOK / "apps" / "backend" / "servers" / "ai_router.py").read_text(encoding="utf-8")
    agac = ast.parse(src)
    envanter = set()
    for d in agac.body:
        if isinstance(d, ast.Assign) and any(getattr(h, "id", "") == "_AI_MODUL_ENVANTERI" for h in d.targets):
            envanter = {e.elts[2].value for e in d.value.elts}
    assert len(envanter) >= 15, f"vakum: _AI_MODUL_ENVANTERI {len(envanter)} girdi"
    cagri = set(re.findall(r'download_model_sync\(\s*"([^"]+)"', src))
    assert len(cagri) >= 8, f"vakum: download_model_sync cagrisi {len(cagri)}"
    # ürün kodundaki (ai_hub + apps/backend; testler hariç) model-köküne göreli HER ağırlık yolu: `download_model_sync`,
    # `pt_coz` (XAI PT ikizleri), `_yan` (yan dosya) ve sabitler aynı biçimi kullanır
    ham = subprocess.run(
        ["git", "-c", "core.quotepath=off", "ls-files", "-z", "--", "ai_hub", "apps/backend"],
        cwd=KOK,
        capture_output=True,
        timeout=120,
    ).stdout
    yol_deseni = re.compile(r'"(ai_hub/[A-Za-z0-9_./-]+\.(?:onnx|pt|pkl|npy|npz))"')
    literal = set()
    for ad in (x.decode("utf-8") for x in ham.split(b"\x00") if x):
        if ad.endswith(".py") and "/tests/" not in ad:
            literal |= set(yol_deseni.findall((KOK / ad).read_text(encoding="utf-8", errors="replace")))
    assert len(literal) >= 20, f"vakum: urun kodunda {len(literal)} agirlik yolu"
    return envanter | cagri | literal


def test_KRITIK_uretimin_cozdugu_HER_agirlik_bir_PAKETE_duser_agactan_BAGIMSIZ():
    mmz = _mmz()
    paketli = {r for t in (mmz.PROFILLER, mmz.PARCALAR) for liste in t.values() for r in liste}
    cekirdek = _cekirdek()
    app = _izlenen_app_katmani()
    assert len(app) >= 11, f"vakum: izlenen release_assets {len(app)}"
    disarda = sorted(
        m for m in _uretimin_cozdugu() if m not in paketli and not m.lower().startswith(cekirdek) and m not in app
    )
    assert not disarda, (
        "uretim kodunun cozdugu bu agirliklar HICBIR launcher paketine (profil / parca / cekirdek / izlenen app katmani) "
        f"girmiyor → sahada sessizce yok: {disarda}"
    )


def test_KARSIT_olcucu_kor_degil():
    """Ölçücü kendini kanıtlar: profil kümesinden bir girdi düşürülünce o ağırlık 'dışarıda' çıkar."""
    mmz = _mmz()
    paketli = {r for t in (mmz.PROFILLER, mmz.PARCALAR) for liste in t.values() for r in liste}
    hedef = "ai_hub/cat_disease/XGBoost.pkl"
    assert hedef in _uretimin_cozdugu() and hedef in paketli
    paketli.discard(hedef)
    assert hedef not in _izlenen_app_katmani() and not hedef.startswith(_cekirdek())
