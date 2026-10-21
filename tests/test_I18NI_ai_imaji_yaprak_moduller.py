# -*- coding: utf-8 -*-
"""I18NI-A3.2 — GPU AI mikroservis imajı (`docker/Dockerfile.ai`) `utils/panel_yayin.py`'yi kopyalar ama onun YENİ üst düzey içe aktarması
`from utils import ceviri`yi (ve `ceviri`nin katalog / `path_utils` bağımlılıklarını) KOPYALAMAZ → `ai_service/app.py` üst düzeyde
`utils.panel_yayin`'ı içe aktardığı için konteynerde `ImportError` → servis (uvicorn `ai_service.app:app`) AÇILMAZ.

Var olan kapı `test_ai_servis_8100_kapisi.py::test_DOCKERFILE_kapi_modullerini_KOPYALIYOR` yalnız `app.py`'nin DOĞRUDAN içe aktarmalarını
tarar (geçişli değil) → YEŞİL kalır. KURALLAR §4.8: "YAPRAK modüller (AI Docker imajına tek satırla girer) `utils.ceviri` İÇE AKTARMAZ".

Bu sonda (1) imaja kopyalanan her `utils` modülünün MODÜL DÜZEYİ depo-içi içe aktarmalarının (try içindekiler dahil) da imajda olduğunu
GEÇİŞLİ denetler (statik, AST); (2) imajın `utils/` dizinini geçici bir kökte AYNEN kurup her kopyalanan modülü ayrı bir alt süreçte (kafes `-I`yı reddeder; kök yalnız sys.path başına)
içe aktarır (dinamik — konteynerin içe aktarma davranışının eşi; cv2 / numpy yalnız `image_domain` için, site-packages'tan).
Taban `c1e098ef`: YEŞİL (panel_yayin yalnız stdlib). HEAD: KIRMIZI. Düzeltilince YEŞİL.
"""

from __future__ import annotations

import ast
import re
import shutil
import subprocess
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
DOCKERFILE = KOK / "docker" / "Dockerfile.ai"
UTILS = KOK / "apps" / "backend" / "utils"


def _imaj_utils_kumesi() -> set[str]:
    """Dockerfile.ai'nin `COPY … apps/backend/utils/<x>.py … ./utils/` satır(lar)ındaki modül adları (yorum satırları atlanır)."""
    kume: set[str] = set()
    for satir in DOCKERFILE.read_text(encoding="utf-8").splitlines():
        s = satir.strip()
        if not s.startswith("COPY") or "./utils/" not in s:
            continue
        kume.update(re.findall(r"apps/backend/utils/([A-Za-z0-9_]+)\.py", s))
    assert kume, "Dockerfile.ai'de utils COPY satırı bulunamadı"
    return kume


def _modul_duzeyi_utils_bagimliliklari(ad: str) -> set[str]:
    agac = ast.parse((UTILS / f"{ad}.py").read_text(encoding="utf-8"))
    dugumler: list[ast.AST] = []
    for d in agac.body:
        if isinstance(d, (ast.Try, ast.If)):
            dugumler.extend(ast.walk(d))
        else:
            dugumler.append(d)
    gerek: set[str] = set()
    for d in dugumler:
        if isinstance(d, ast.ImportFrom) and d.module:
            if d.module == "utils":
                gerek.update(a.name for a in d.names)
            elif d.module.startswith("utils."):
                gerek.add(d.module.split(".")[1])
        elif isinstance(d, ast.Import):
            for a in d.names:
                if a.name.startswith("utils."):
                    gerek.add(a.name.split(".")[1])
    return {g for g in gerek if (UTILS / f"{g}.py").exists() or (UTILS / g).is_dir()}


def test_imajdaki_utils_modullerinin_GECISLI_bagimliliklari_da_imajda():
    kume = _imaj_utils_kumesi()
    eksik = []
    for ad in sorted(kume - {"__init__"}):
        for g in sorted(_modul_duzeyi_utils_bagimliliklari(ad)):
            if g not in kume:
                eksik.append(f"utils/{ad}.py → utils/{g}.py (imajda YOK)")
    assert not eksik, "GPU AI imajında içe aktarma zinciri kırık — servis ImportError ile AÇILMAZ:\n  " + "\n  ".join(
        eksik
    )


def test_imajin_utils_dizini_yalitilmis_alt_surecte_ICE_AKTARILIR(tmp_path):
    kume = _imaj_utils_kumesi()
    hedef = tmp_path / "app" / "utils"
    hedef.mkdir(parents=True)
    for ad in kume:
        shutil.copy2(UTILS / f"{ad}.py", hedef / f"{ad}.py")
    sorunlu = []
    for ad in sorted(kume - {"__init__"}):
        kod = (
            "import sys; sys.path.insert(0, sys.argv[1]); "
            "import importlib; importlib.import_module('utils.' + sys.argv[2])"
        )
        r = subprocess.run(
            [sys.executable, "-c", kod, str(tmp_path / "app"), ad],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(tmp_path),
        )
        if r.returncode != 0:
            son = (r.stderr.strip().splitlines() or ["?"])[-1]
            sorunlu.append(f"utils.{ad}: {son}")
    assert not sorunlu, "GPU AI imajının utils/ kopyasında içe aktarılamayan modül:\n  " + "\n  ".join(sorunlu)


# ── (3) GPU profili: servis katalog taşımaz → backend panel adlarını İSTEK dilinde kurmalı ───────────────────────────────────────


def _gpu_yaniti():
    # Servis (düzeltme sonrası) çeviri yapamaz → `ad` = ham panel anahtarı; eski servis Türkçe göndermiş olabilir (ikisi de çevrilmeli).
    return {
        "status": "success",
        "image_base64": "",
        "paneller": [
            {"k": "01_input", "ad": "01_input", "image_base64": "", "image_w": 1, "image_h": 1},
            {"k": "07_combined", "ad": "Birleşik", "image_base64": "", "image_w": 1, "image_h": 1},
            {"k": "zz_bilinmeyen", "ad": "zz_bilinmeyen", "image_base64": "", "image_w": 1, "image_h": 1},
        ],
    }


import pytest  # noqa: E402


@pytest.mark.parametrize("uc,tablo", [("em_fantom", "PANEL_ADLARI"), ("em_petri", "PETRI_PANEL_ADLARI")])
@pytest.mark.parametrize("dil", ["tr", "en"])
def test_gpu_profili_panel_adlari_istek_dilinde(monkeypatch, uc, tablo, dil):
    import i18n_yardimci as iy
    from fastapi.testclient import TestClient
    from servers import ai_router, api_server
    from utils import panel_yayin

    async def _sahte_devret(name, label=None, **kw):
        return _gpu_yaniti()

    monkeypatch.setattr(ai_router, "ai_service_enabled", lambda: True)
    monkeypatch.setattr(ai_router, "_kapili_devret", _sahte_devret)
    c = TestClient(api_server.app, client=("127.0.0.1", 51241))
    r = c.post(f"/api/ai/vision/{uc}", files={"file": ("t.jpg", b"x", "image/jpeg")}, headers={"X-PEMF-Dil": dil})
    assert r.status_code == 200, r.text[:300]
    adlar = getattr(panel_yayin, tablo)
    kat = iy.katalog("sunucu", dil)
    got = {p["k"]: p["ad"] for p in r.json()["paneller"]}
    assert got["01_input"] == kat[adlar["01_input"]], got
    assert got["07_combined"] == kat[adlar["07_combined"]], got
    assert got["zz_bilinmeyen"] == "zz_bilinmeyen", got
