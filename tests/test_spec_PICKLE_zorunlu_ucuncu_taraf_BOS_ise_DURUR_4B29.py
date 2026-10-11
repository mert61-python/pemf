# -*- coding: utf-8 -*-
"""4B-2.9 (4-B incelemesi A2; KARAR) — spec'in ÜÇÜNCÜ-TARAF gizli-içe-aktarma dalı: `sklearn` boş toplanırsa derleme DURMALI.

D4.17 birinci-taraf paketleri fail-closed yaptı; üçüncü-taraf dalında hoşgörü kaldı. Ölçüldü (`_inceleme/kayit/k3_ucuncu_taraf_sonda.txt`):
GERÇEK `collect_submodules` ortamda OLMAYAN paket için İSTİSNA DEĞİL **0 modül** döndürür → `except: pass` bile gerekmeden sessiz.
`sklearn` ürün kodunda HİÇBİR yerde statik içe aktarılmıyor [ÖLÇTÜM `git grep`]; böbrek-hastalık `preprocessor.pkl` (ColumnTransformer)
yalnız pickle'dan yüklenir → derleme ortamında sklearn yoksa EXE sklearn'süz çıkar, D4.28 AI kapısı (modül içe aktarımı + dosya varlığı)
GEÇER, sahada ilk böbrek-hastalık analizi `No module named 'sklearn…'` ile ölür. XAI paketleri (shap/timm/…) zarif düşüşlü → hoşgörü kalır.
Sürücü: D4.27 testinin KENDİ PyInstaller'sız sürücüsü; yalnız `collect_submodules` belirtilen paket için boş döner.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK / "tests"))

import test_her_model_agirligi_bir_PAKETE_duser_D427 as d427  # noqa: E402

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="spec yalnız Windows derlemesinde koşar")

_ESKI = "hooks.collect_submodules = lambda pkg, *a, **k: [pkg + '._sahte']"
_YENI = (
    "hooks.collect_submodules = lambda pkg, *a, **k: [] if pkg == os.environ.get('BOS_DONSUN') else [pkg + '._sahte']"
)


def _kos(tmp: Path, bos: str) -> subprocess.CompletedProcess:
    assert d427._SURUCU.count(_ESKI) == 1, "D4.27 surucusu degisti — bu kapi guncellensin"
    (tmp / "surucu.py").write_text(d427._SURUCU.replace(_ESKI, _YENI), encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(tmp / "surucu.py"), str(d427.SPEC), str(tmp / "c.json")],
        cwd=str(KOK),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "BOS_DONSUN": bos, "PEMF_EMBED_MODELS": "0"},
        timeout=300,
    )


def test_KRITIK_pickle_zorunlu_sklearn_BOS_toplanirsa_spec_DURUR(tmp_path):
    r = _kos(tmp_path, "sklearn")
    assert r.returncode != 0, "sklearn 0 modul toplandi ama spec BASARIYLA bitti (CKD sahada olur)\n" + r.stdout[-800:]
    assert "sklearn" in (r.stdout + r.stderr), (r.stdout + r.stderr)[-800:]


@pytest.mark.parametrize("paket", ["shap", "timm", "celldetection"])
def test_KARSIT_zarif_dususlu_XAI_paketi_BOSSA_HOSGORU_kalir(tmp_path, paket):
    r = _kos(tmp_path, paket)
    assert r.returncode == 0, r.stdout[-800:] + r.stderr[-800:]
