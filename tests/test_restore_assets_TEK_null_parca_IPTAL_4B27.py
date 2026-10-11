# -*- coding: utf-8 -*-
"""4B-2.7 (4-B incelemesi A2) — `restore_assets.ps1`: `model_parts.research = [null]` SESSİZCE "parça yok" sayılıyor.

PowerShell'de TEK öğeli dizi boolean bağlamda öğesinin doğruluğunu alır: `@($null)` → `$false`. Betik
`if ($manifest.model_parts -and $manifest.model_parts.$p)` ile parça listesini `@()`'e çeviriyor → D4.16'nın "url/sha256'sı eksik
parça girdisi → kurulum İPTAL" kuralı bu biçimde HİÇ koşmuyor: çıkış 0 + "Geri yuklendi", parça indirilmedi (ölçüldü pwsh 7 ve 5.1:
`_inceleme/kayit/k2_restore_sonda.txt` `girdi_null`). `[null, {...}]` (iki öğe) doğru biçimde İPTAL ediyor — tutarsız.
Ölçüm D4.16 testinin KENDİ gölge sarmalayıcısıyla (ağsız; gölge devrede değilse 99).
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK / "tests"))

import test_restore_assets_MODEL_PARCALARI_D416 as d416  # noqa: E402

_KABUKLAR = [k for k in ("pwsh", shutil.which("powershell.exe") if os.name == "nt" else None) if k and shutil.which(k)]


def _zip(yol: Path, girdiler: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(yol, "w") as z:
        for ad, veri in girdiler.items():
            z.writestr(ad, veri)
    return yol


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _kos(tmp: Path, parcalar: list, kabuk: str) -> subprocess.CompletedProcess:
    paket = tmp / "paket"
    paket.mkdir()
    research = _zip(paket / "research.zip", {"ai_models/ai_hub/em_petri/PetriNet_v3.onnx": b"ANA"})
    deps = _zip(
        paket / "base-deps.zip", {"PEMF_Backend/_internal/ai_models/ai_hub/inference_cat_organ/models/c.onnx": b"O"}
    )
    manifest = {
        "profiles": {"research": {"url": "https://paket.invalid/research.zip", "sha256": _sha(research), "size": 1}},
        "layers": {
            "win-x64": {"deps": {"url": "https://paket.invalid/base-deps.zip", "sha256": _sha(deps), "size": 1}}
        },
        "model_parts": {"research": parcalar},
    }
    (paket / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (tmp / "harita.json").write_text(
        json.dumps(
            {d416.MANIFEST_URL: str(paket / "manifest.json"), "https://paket.invalid/research.zip": str(research)}
        ),
        encoding="utf-8",
    )
    (tmp / "sarmal.ps1").write_text(d416._SARMAL, encoding="utf-8-sig")
    (tmp / "temp").mkdir()
    (tmp / "iwr.log").write_text("", encoding="utf-8")
    env = {**os.environ, "SAHTE_IWR_GUNLUK": str(tmp / "iwr.log"), "TEMP": str(tmp / "temp"), "TMP": str(tmp / "temp")}
    if kabuk != "pwsh":
        env = {k: v for k, v in env.items() if k.upper() != "PSMODULEPATH"}
    r = subprocess.run(
        [
            kabuk,
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(tmp / "sarmal.ps1"),
            str(d416.BETIK),
            str(tmp / "harita.json"),
            "-Profiller",
            "research",
            "-DepsZipYolu",
            str(deps),
            "-KokOverride",
            str(tmp / "kok"),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=180,
    )
    assert "GOLGE DEVREDE DEGIL" not in r.stdout, "golge devrede degil — betik kosturulmadi"
    return r


@pytest.mark.parametrize("kabuk", _KABUKLAR)
def test_KRITIK_tek_null_parca_girdisi_kurulumu_IPTAL_eder(tmp_path, kabuk):
    r = _kos(tmp_path, [None], kabuk)
    assert r.returncode != 0, f"[null] parca girdisi SESSIZCE 'parca yok' sayildi (rc=0)\n{r.stdout[-1200:]}"
    assert "girdisi eksik" in r.stdout and "Geri yuklendi" not in r.stdout, r.stdout[-1200:]


@pytest.mark.parametrize("kabuk", _KABUKLAR)
def test_KARSIT_bos_liste_parcasiz_GECER(tmp_path, kabuk):
    r = _kos(tmp_path, [], kabuk)
    assert r.returncode == 0 and "Geri yuklendi" in r.stdout, r.stdout[-1200:] + r.stderr[-600:]
