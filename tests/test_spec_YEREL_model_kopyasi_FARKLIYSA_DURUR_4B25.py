# -*- coding: utf-8 -*-
"""4B-2.5 (4-B incelemesi A2) — D4.27: modül dizinindeki YEREL model kopyası izlenen `release_assets` kopyasından FARKLIYSA spec
SESSİZCE izlenen kopyayı gömüyor (ölçüldü: `_inceleme/kayit/k2_cift_kopya_sonda.txt` — uyarı 0 satır).

Geliştirici modeli modül dizininde yeniler (kaynaktan koşan backend onu yükler, testler onunla geçer) ama `release_assets`'i
unutursa EXE ESKİ ağırlığı sevk eder — geliştirme ile sevk FARKLI yazılım. Doğru: iki kopya farklıysa derleme DURUR ve hangisinin
doğru olduğunu sorar. Ölçüm: spec PyInstaller OLMADAN, D4.27 testinin KENDİ sürücüsüyle, GEÇİCİ AYNA proje kökünde (cwd) —
gerçek depo ağacına yazılmaz.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK / "tests"))

import test_her_model_agirligi_bir_PAKETE_duser_D427 as d427  # noqa: E402

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="spec yalnız Windows derlemesinde koşar")

_MODUL = "ai_hub/inference_ornek_4b25"


def _ayna(tmp: Path, yerel: bytes | None) -> Path:
    kok = tmp / "ayna"
    (kok / "build_tools").mkdir(parents=True)
    for ad in ("__init__.py", "make_model_zip.py", "PEMF_Backend_onedir.spec"):
        shutil.copy2(KOK / "build_tools" / ad, kok / "build_tools" / ad)
    ra = kok / "release_assets" / "ai_models" / _MODUL
    ra.mkdir(parents=True)
    (ra / "scaler.pkl").write_bytes(b"IZLENEN-release_assets-kopyasi")
    md = kok / _MODUL
    md.mkdir(parents=True)
    (md / "infer.py").write_text("# ornek\n", encoding="utf-8")
    if yerel is not None:
        (md / "scaler.pkl").write_bytes(yerel)
    return kok


def _kos(kok: Path, tmp: Path) -> tuple[subprocess.CompletedProcess, list]:
    (tmp / "surucu.py").write_text(d427._SURUCU, encoding="utf-8")
    cikti = tmp / "c.json"
    p = subprocess.run(
        [sys.executable, str(tmp / "surucu.py"), str(kok / "build_tools" / "PEMF_Backend_onedir.spec"), str(cikti)],
        cwd=str(kok),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
    )
    datas = json.loads(cikti.read_text(encoding="utf-8"))["datas"] if cikti.exists() else []
    return p, datas


def test_KRITIK_yerel_kopya_FARKLIYSA_spec_DURUR_ve_dosyayi_ADLANDIRIR(tmp_path):
    kok = _ayna(tmp_path, yerel=b"YENI-EGITILMIS-yerel-kopya")
    p, _ = _kos(kok, tmp_path)
    assert p.returncode != 0, (
        "modul dizinindeki yerel kopya release_assets'ten FARKLI ama spec SESSIZCE gecti (izlenen ESKI kopya sevk edilirdi)\n"
        + p.stdout[-1200:]
    )
    assert "scaler.pkl" in (p.stdout + p.stderr), (p.stdout + p.stderr)[-1200:]


@pytest.mark.parametrize("yerel", [None, b"IZLENEN-release_assets-kopyasi"], ids=["yerel_yok", "bayt_bayt_ayni"])
def test_KARSIT_yerel_kopya_YOK_ya_da_AYNI_ise_izlenen_kopya_GOMULUR(tmp_path, yerel):
    kok = _ayna(tmp_path, yerel=yerel)
    p, datas = _kos(kok, tmp_path)
    assert p.returncode == 0, p.stdout[-1200:] + p.stderr[-1200:]
    kaynaklar = [s.replace("\\", "/") for s, d in datas if s.replace("\\", "/").endswith(_MODUL + "/scaler.pkl")]
    assert kaynaklar and all("/release_assets/ai_models/" in s for s in kaynaklar), kaynaklar
