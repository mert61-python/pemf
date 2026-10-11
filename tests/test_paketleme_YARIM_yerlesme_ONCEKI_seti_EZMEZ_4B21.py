# -*- coding: utf-8 -*-
"""4B-2.1 (4-B incelemesi A2; orkestratörün 4B-4.2 zincir ölçümüyle aynı açık) — `make_base_zip._yerlestir` YARIM yerleşmede önceki GEÇERLİ seti EZMEMELİ.

D4.31'in iddiası "doğrulamadan önce yayın dizini ezilmez / geçerli eski paket EZİLMEZ". `_yerlestir` deps → app → base.zip
sırasıyla AYRI AYRI `os.replace` yapar; biri yerine oturamazsa (Windows: yükleme aracı / antivirüs dosyayı paylaşımsız açık
tutuyor → PermissionError, WinError 32) öncekiler YERİNDE kalır: yayın dizini YENİ deps + ESKİ app (ya da tersi) olur ve
`make_manifest` bu karma seti çıkış 0 ile mühürler (ölçüldü: `_inceleme/4B-2.1/sonda.py`). Doğru: HEPSİ YA DA HİÇBİRİ.

Betik GERÇEK alt süreçte; kilit, `os.replace`'i YALNIZ hedef dosya için PermissionError fırlatan sarmalayıcıyla kurulur.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
MAKE_BASE_ZIP = KOK / "build_tools" / "make_base_zip.py"

_KILITLI_SARMAL = """import os
import runpy
import sys

betik, dist, kilitli = sys.argv[1], sys.argv[2], sys.argv[3]
_gercek = os.replace


def _replace(src, dst, *a, **k):
    if os.path.basename(str(dst)) == kilitli:
        raise PermissionError(32, "dosya baska bir surecte acik (test kilidi)", str(dst))
    return _gercek(src, dst, *a, **k)


os.replace = _replace
sys.argv = [betik, dist] + sys.argv[4:]
runpy.run_path(betik, run_name="__main__")
"""


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _zip(yol: Path, girdiler: dict[str, bytes]) -> None:
    with zipfile.ZipFile(yol, "w", zipfile.ZIP_STORED) as z:
        for ad, veri in girdiler.items():
            z.writestr(ad, veri)


def _sahte_dist(kok: Path) -> Path:
    d = kok / "dist" / "PEMF_Backend"
    for alt in ("ai_hub", "frontend/dist", "bin/mosquitto", "torch", "ai_models/ai_hub/inference_cat_organ/models"):
        (d / "_internal" / alt).mkdir(parents=True, exist_ok=True)
    (d / "PEMF_Backend.exe").write_bytes(b"EXE-YENI-build")
    (d / "_internal" / "ai_hub" / "model.pyd").write_bytes(b"PYD")
    (d / "_internal" / "frontend" / "dist" / "index.html").write_text("<html>", encoding="utf-8")
    (d / "_internal" / "bin" / "mosquitto" / "mosquitto.exe").write_bytes(b"MOSQ")
    (d / "_internal" / "torch" / "lib.dll").write_bytes(b"TORCH-YENI" * 50)
    (d / "_internal" / "ai_models" / "ai_hub" / "inference_cat_organ" / "models" / "r.onnx").write_bytes(b"ORGAN")
    return d


@pytest.fixture
def kum(tmp_path):
    cikti = tmp_path / "yayin"
    cikti.mkdir()
    _zip(cikti / "base-app.zip", {"PEMF_Backend/PEMF_Backend.exe": b"EXE-ESKI", "PEMF_Backend/_app_roots.json": b"{}"})
    _zip(cikti / "base-deps.zip", {"PEMF_Backend/_internal/torch/lib.dll": b"TORCH-ESKI"})
    once = {ad: _sha(cikti / ad) for ad in ("base-app.zip", "base-deps.zip")}
    return tmp_path, cikti, once


def _kos(tmp: Path, cikti: Path, kilitli: str, *ek: str) -> subprocess.CompletedProcess:
    sarmal = tmp / "kilitli_sarmal.py"
    sarmal.write_text(_KILITLI_SARMAL, encoding="utf-8")
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PEMF_PKG_OUT": str(cikti)}
    return subprocess.run(
        [sys.executable, str(sarmal), str(MAKE_BASE_ZIP), str(_sahte_dist(tmp)), kilitli, *ek],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=300,
    )


@pytest.mark.parametrize("kilitli", ["base-app.zip", "base-deps.zip"], ids=["app_kilitli", "deps_kilitli"])
def test_KRITIK_bir_katman_yerine_OTURMAZSA_onceki_GECERLI_set_AYNEN_kalir(kum, kilitli):
    tmp, cikti, once = kum
    r = _kos(tmp, cikti, kilitli)
    assert r.returncode == 1, f"kilitli {kilitli} ile betik BASARILI dondu (rc={r.returncode})\n{r.stdout[-1500:]}"
    assert "VALIDATION: FAIL" in r.stdout, r.stdout[-1500:]
    sonra = {ad: _sha(cikti / ad) for ad in once}
    degisen = sorted(ad for ad in once if sonra[ad] != once[ad])
    assert not degisen, (
        f"{kilitli} yerine oturamadi ama {degisen} YENI build'le EZILDI: yayin dizininde iki farkli build'in katmanlari "
        f"(karma set) — make_manifest bunu cikis 0 ile muhurler\n{r.stdout[-1500:]}"
    )
    artik = sorted(p.name for p in cikti.iterdir() if p.suffix in (".tmp", ".bak", ".onceki"))
    assert not artik, f"basarisiz yerlesme artik birakti: {artik}"
    assert "geri donduruldu" in r.stdout, "operator onceki setin geri konuldugunu GORMUYOR\n" + r.stdout[-1500:]


def test_KARSIT_kilit_YOKKEN_iki_katman_YERLESIR_artik_kalmaz(kum):
    tmp, cikti, once = kum
    r = _kos(tmp, cikti, "kilit-yok.zip")
    assert r.returncode == 0 and "VALIDATION: PASS" in r.stdout, r.stdout[-1500:] + r.stderr[-800:]
    for ad in once:
        assert _sha(cikti / ad) != once[ad], f"{ad} PASS'te yerine konmadi"
    assert not [p.name for p in cikti.iterdir() if p.suffix in (".tmp", ".bak", ".onceki")], "PASS'te artik kaldi"
