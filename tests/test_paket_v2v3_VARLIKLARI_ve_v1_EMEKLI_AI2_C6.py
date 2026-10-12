# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""AI-2 C6 — hocanın petri v2 / fantom v3 VARLIKLARI pakete girer, v1 `petri_cv` / `phantom_cv` EMEKLİ (2026-10-12).

NE DEĞİŞTİ: v1 paketleri silindi (S-AI2.4); ürün yükleyicileri (`ai_router._yukle_em_*_cv`, `ai_service.predictors`) v2 / v3'ü
kullanıyor. v2 / v3 üç yeni KOD DIŞI dosya getiriyor ve üçü de `load_cabin_config(None)` / `PhantomCvPipeline` tarafından
modül dizininden okunuyor:
    petri_cv_v2/cabin_config_v2.yaml · phantom_cv_v3/cabin_config_v3.yaml · phantom_cv_v3/phantom_layout_2026-10-02.json
Biri pakete girmezse dondurulmuş derlemede yükleyici `FileNotFoundError` verir (YAML) ya da hocanın sabit T1–T5 kimliği SESSİZCE
kaybolur (JSON yoksa `layout` None → kimlikler konum sıralı; uyarı da yok).

KAPI (gerçek derleme YOK — PyInstaller / ISCC / Cython koşmaz):
  · spec GERÇEK metniyle sahte PyInstaller altında koşar (D427 sürücüsü) → `datas` ölçülür: üç varlık doğru hedef dizinde,
    v1 dizinlerinden HİÇBİR şey yok;
  · KURU KURULUM: `datas`taki `ai_hub/**` girdilerinden geçici bir `_internal/ai_hub` ağacı kurulur (yalnız spec'in sevk ettiği
    dosyalar) ve AYRI bir süreçte oradan yüklenir — v2 YAML'ı (plaka kipi 24), v3 YAML'ı ve yerleşim referansı (T1–T5) okunur;
    `ai_hub` paketinin GERÇEKTEN o ağaçtan geldiği doğrulanır (depoya düşüş = sahte yeşil);
  · `compile_pyd.hedefler` aynı ağaçta v2 / v3 modüllerini görür, v1 görmez; YAML / JSON derlenmez (veri kalır).
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
VARLIKLAR = {
    "ai_hub/inference_petri_dish/petri_cv_v2": "cabin_config_v2.yaml",
    "ai_hub/inference_em_fantom/phantom_cv_v3": ("cabin_config_v3.yaml", "phantom_layout_2026-10-02.json"),
}
V1_DIZINLER = ("ai_hub/inference_petri_dish/petri_cv", "ai_hub/inference_em_fantom/phantom_cv")

pytestmark = pytest.mark.skipif(
    sys.platform != "win32", reason="spec yalnız Windows derlemesinde koşar (DLL/yol mantığı)"
)


def _beklenen() -> list[tuple[str, str]]:
    out = []
    for d, adlar in VARLIKLAR.items():
        for ad in (adlar,) if isinstance(adlar, str) else adlar:
            out.append((d, ad))
    return out


@pytest.fixture(scope="module")
def spec_datas(tmp_path_factory) -> list[tuple[str, str]]:
    from test_her_model_agirligi_bir_PAKETE_duser_D427 import _SURUCU, SPEC

    d = tmp_path_factory.mktemp("spec_ai2c6")
    surucu, cikti = d / "surucu.py", d / "cikti.json"
    surucu.write_text(_SURUCU, encoding="utf-8")
    p = subprocess.run(
        [sys.executable, str(surucu), str(SPEC), str(cikti)],
        cwd=str(KOK),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
    )
    assert p.returncode == 0 and cikti.exists(), f"spec koşmadı (rc={p.returncode}):\n{p.stderr[-1500:]}"
    return [(s, dd.replace("\\", "/")) for s, dd in json.loads(cikti.read_text(encoding="utf-8"))["datas"]]


def _ai_hub_girdileri(spec_datas) -> list[tuple[Path, str]]:
    return [(Path(s), dd) for s, dd in spec_datas if (dd == "ai_hub" or dd.startswith("ai_hub/")) and os.path.isfile(s)]


def test_KRITIK_v2_v3_varliklari_DOGRU_hedefe_SEVK_edilir(spec_datas):
    girdiler = {(dd, s.name) for s, dd in _ai_hub_girdileri(spec_datas)}
    eksik = [f"{d}/{ad}" for d, ad in _beklenen() if (d, ad) not in girdiler]
    assert not eksik, (
        f"spec bu varlıkları SEVK ETMİYOR (dondurulmuş derlemede yükleyici kırılır / T1–T5 kaybolur): {eksik}"
    )
    for d in VARLIKLAR:
        assert (d, "pipeline.py") in girdiler and (d, "cabin_config.py") in girdiler, f"{d}: modüller sevk edilmiyor"


def test_KRITIK_v1_dizinlerinden_HICBIR_sey_sevk_edilmez(spec_datas):
    v1 = sorted({f"{dd}/{s.name}" for s, dd in _ai_hub_girdileri(spec_datas) if dd in V1_DIZINLER})
    assert not v1, f"emekli v1 paketi hâlâ sevk ediliyor: {v1[:8]}"
    for d in V1_DIZINLER:
        assert not (KOK / d).exists(), f"{d} depoda duruyor — v1 emekliliği yarım"


_KURU = r'''
import sys
kok = sys.argv[1]
sys.path.insert(0, kok)
import ai_hub
assert ai_hub.__file__.replace("\\", "/").startswith(kok.replace("\\", "/")), "ai_hub paketten DEĞİL: " + ai_hub.__file__
from ai_hub.inference_petri_dish.petri_cv_v2.cabin_config import load_cabin_config as petri_yukle
from ai_hub.inference_em_fantom.phantom_cv_v3.cabin_config import load_cabin_config as fantom_yukle
from ai_hub.inference_em_fantom.phantom_cv_v3.layout import Layout
from pathlib import Path
p = petri_yukle(None)
f = fantom_yukle(None)
assert str(p.source_path).replace("\\", "/").startswith(kok.replace("\\", "/")), p.source_path
assert p.multiwell.plate_type == 24 and p.cabin_id == "petri_helmholtz_v1", (p.multiwell.plate_type, p.cabin_id)
assert f.cabin_id == "phantom_helmholtz_v1" and f.phantom_v2.ring_diameter_mm == 184.0
lay = Layout.load(Path(f.source_path).parent / f.phantom_v2.layout_file)
assert list(lay.ids) == ["T1", "T2", "T3", "T4", "T5"], lay.ids
print("KURU_KURULUM_TAMAM", p.multiwell.plate_type, list(lay.ids))
'''


def test_KRITIK_KURU_KURULUM_spec_agacindan_v2_v3_varsayilanlari_YUKLENIR(spec_datas, tmp_path):
    ic = tmp_path / "dist" / "PEMF_Backend" / "_internal"
    for kaynak, hedef in _ai_hub_girdileri(spec_datas):
        h = ic / hedef / kaynak.name
        h.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(kaynak, h)
    assert (ic / "ai_hub" / "__init__.py").exists(), "aparat: spec ai_hub/__init__.py sevk etmiyor"
    betik = tmp_path / "kuru.py"
    betik.write_text(_KURU, encoding="utf-8")
    p = subprocess.run(
        [sys.executable, str(betik), str(ic)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
    )
    assert p.returncode == 0 and "KURU_KURULUM_TAMAM 24" in p.stdout, (
        f"spec ağacından yükleme başarısız (rc={p.returncode}):\n{p.stdout[-800:]}\n{p.stderr[-1500:]}"
    )

    # compile_pyd aynı ağaçta: v2 / v3 modülleri hedef, v1 yok, veri dosyaları derlenmez
    s = importlib.util.spec_from_file_location("_cpyd_ai2c6", KOK / "build_tools" / "compile_pyd.py")
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    hedefler = {p_.relative_to(ic).as_posix() for p_ in m.hedefler(tmp_path / "dist" / "PEMF_Backend")}
    for d in VARLIKLAR:
        assert f"{d}/pipeline.py" in hedefler, f"compile_pyd {d}/pipeline.py'yi görmüyor"
    assert not [h for h in hedefler if any(h.startswith(v + "/") for v in V1_DIZINLER)], "compile_pyd v1 modülü görüyor"
    assert not [h for h in hedefler if h.endswith((".yaml", ".json"))], "veri dosyası derleme hedefi sayıldı"
