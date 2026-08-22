# Author: mertaygn, cglrgrkn
"""RESTORE_ASSETS ÇEKİRDEK MODELİ — 2. tur denetimi bulgu [3.5] (2026-08-20).

ÖLÇÜLEN DURUM: `scripts/restore_assets.ps1` yalnız home/vet/research profil zip'lerini
indiriyordu; oysa `inference_cat_organ` (3 ONNX, ~200 MB — AI Pro organ lokalizasyonunun
çekirdeği) 2026-08-10'da home.zip'ten ÇIKARILIP yalnız `base-deps.zip`e taşındı (make_base_zip
CORE_MODELS istisnası). Uzaktan ölçüldü: üç profil zip'inin 37 girdisinin HİÇBİRİNDE cat_organ
yok → temiz makinede ~1 saatlik "klon = çalışan sistem" akışı SON kapıda ("cekirdek model
(cat_organ) VAR" → exit 1) ölüyordu; kapı elle atlansa AI Pro organ-lokalizasyonsuz backend
dağıtılırdı.

SÖZLEŞME: betik çekirdek modelleri deps katmanından da getirir. Test edilebilirlik için üç
parametre (PEMF_PKG_OUT emsali — test gerçek ağı/dizini kullanmasın): `-DepsZipYolu` (yerel zip,
ağ yok), `-YalnizCekirdek` (profilleri atla), `-KokOverride` (hedef kök). Deps zip'inde çekirdek
model YOKSA sessiz "0 dosya" başarısı YASAK — açık hata (paketleme sözleşmesi bozulmuş demektir).
"""

from __future__ import annotations

import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
BETIK = KOK / "scripts" / "restore_assets.ps1"


def _powershell():
    for aday in ("pwsh", "powershell"):
        if shutil.which(aday):
            return aday
    return None


pytestmark = pytest.mark.skipif(_powershell() is None, reason="PowerShell bulunamadi")


def _kostur(*ek_args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [_powershell(), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(BETIK), *ek_args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )


def _deps_zip(yol: Path, girdiler: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(yol, "w") as z:
        for ad, veri in girdiler.items():
            z.writestr(ad, veri)
    return yol


def test_KRITIK_cekirdek_model_deps_zipinden_gelir(tmp_path):
    """Yerel sahte deps zip'i ile: YALNIZ `_internal/ai_models/` altı (çekirdek modeller)
    release_assets'e açılır; torch gibi dev deps kalabalığı AÇILMAZ."""
    zipp = _deps_zip(
        tmp_path / "base-deps.zip",
        {
            "PEMF_Backend/_internal/ai_models/ai_hub/inference_cat_organ/models/a.onnx": b"CAT-ORGAN-A",
            "PEMF_Backend/_internal/ai_models/ai_hub/inference_cat_organ/lib/b.bin": b"CAT-ORGAN-B",
            "PEMF_Backend/_internal/torch/dev.dll": b"TORCH-DEV",
            "PEMF_Backend/PEMF_Backend.exe": b"EXE",
        },
    )
    hedef_kok = tmp_path / "kok"

    r = _kostur("-YalnizCekirdek", "-DepsZipYolu", str(zipp), "-KokOverride", str(hedef_kok))
    assert r.returncode == 0, f"betik çekirdek-model modunu tanımıyor/başaramadı (bulgu [3.5]):\n{r.stdout}\n{r.stderr}"

    ra = hedef_kok / "release_assets"
    a = ra / "ai_models/ai_hub/inference_cat_organ/models/a.onnx"
    assert a.is_file() and a.read_bytes() == b"CAT-ORGAN-A", (
        f"çekirdek model deps'ten AÇILMADI — temiz makinede make_base_zip kapısı yine düşer: {r.stdout!r}"
    )
    assert (ra / "ai_models/ai_hub/inference_cat_organ/lib/b.bin").is_file()
    # deps kalabalığı release_assets'e SIZMAZ
    assert not list(hedef_kok.rglob("dev.dll")), "torch/deps kalabalığı da açılmış — filtre yok"
    assert not list(hedef_kok.rglob("PEMF_Backend.exe")), "exe açılmış — filtre yok"


def test_KRITIK_depste_cekirdek_yoksa_ACIK_hata(tmp_path):
    """Sessiz '0 dosya açıldı' başarısı YASAK: deps zip'inde çekirdek model yoksa paketleme
    sözleşmesi bozulmuş demektir — betik açık hatayla düşmeli (kullanıcı 'geri yüklendi' sanmasın)."""
    zipp = _deps_zip(tmp_path / "bos-deps.zip", {"PEMF_Backend/_internal/torch/dev.dll": b"X"})
    hedef_kok = tmp_path / "kok"

    r = _kostur("-YalnizCekirdek", "-DepsZipYolu", str(zipp), "-KokOverride", str(hedef_kok))
    assert r.returncode != 0, f"deps'te çekirdek model YOKKEN betik başarı bildirdi — sessiz eksik kurulum:\n{r.stdout}"
    assert "cekirdek" in (r.stdout + r.stderr).lower() or "ai_models" in (r.stdout + r.stderr), (
        f"hata sebebi söylenmiyor: {r.stdout!r} {r.stderr!r}"
    )


def test_ters_bolulu_zip_girdileri_de_calisir(tmp_path):
    """Zip girdi ayracı üretici tarafına göre değişebilir (bu deponun bilinen sınıfı) —
    ters-bölülü girdiler de doğru yere açılmalı."""
    zipp = _deps_zip(
        tmp_path / "bs-deps.zip",
        {"PEMF_Backend\\_internal\\ai_models\\ai_hub\\inference_cat_organ\\models\\c.onnx": b"CAT-C"},
    )
    hedef_kok = tmp_path / "kok"

    r = _kostur("-YalnizCekirdek", "-DepsZipYolu", str(zipp), "-KokOverride", str(hedef_kok))
    assert r.returncode == 0, f"{r.stdout}\n{r.stderr}"
    assert (hedef_kok / "release_assets/ai_models/ai_hub/inference_cat_organ/models/c.onnx").is_file()
