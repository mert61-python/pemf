# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D5.13 (B-9.10) — `build_tools/sync_versions.ps1 -Check` hedef dosyası OLMAYAN kanalı SORUN sayar (çıkış ≠ 0).

ARIZA (ölçüldü, HEAD 5bc99be1): `Set-Value` hedef dosya yoksa `[ATLA] … dosya yok` yazıp `return` ediyordu — `$sorun`
artmıyordu. `-Check` ("CI için") bu yüzden bir kanalın hedefi (ör. `launcher/app/tauri.conf.json`) kaybolsa / yeniden adlansa
da "Tum surumler versions.json ile uyumlu" + ÇIKIŞ 0 veriyordu: kanal sürümü artık hiçbir yerde senkronlanmıyor ve kapı yeşil.

ÖLÇÜM: betik + `versions.json` + yedi hedef dosya geçici bir ağaca kopyalanır (betik kökünü kendi konumundan bulur → GERÇEK depoya
yazılmaz; `-Check` zaten yazmaz). Her hedef SIRAYLA silinir → `-Check` çıkışı ≠ 0 ve eksik yol çıktıda. KARŞIT: tam ağaç → 0.
CI'a bağlama kolu ENGELLİ (A-43: itme yok) — yalnız yerel davranış kapısı.
MUTASYON: eksik dosya dalını `[ATLA] … return`e geri çevirmek → KIRMIZI.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import capraz
import pytest

KOK = Path(__file__).resolve().parents[1]
#: `sync_versions.ps1`'in yazdığı hedefler (betikteki `Set-Value -Path` listesi) — burada PİNLİ.
HEDEFLER = (
    "VERSION",
    "docs/version_info.txt",
    "launcher/Cargo.toml",
    "launcher/app/tauri.conf.json",
    "apps/ui/app.json",
    "apps/ui/android/app/build.gradle",
    "frontend_version.json",
)
PWSH = shutil.which("pwsh")

pytestmark = pytest.mark.skipif((PWSH is None) and not capraz.ZORUNLU, reason="pwsh (PowerShell 7) yok")


def _agac(tmp: Path) -> Path:
    kok = tmp / "agac"
    for rel in ("build_tools/sync_versions.ps1", "versions.json", *HEDEFLER):
        hedef = kok / rel
        hedef.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(KOK / rel, hedef)
    return kok


def _check(kok: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            PWSH,
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(kok / "build_tools" / "sync_versions.ps1"),
            "-Check",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        cwd=str(kok),
    )


def test_KARSIT_tam_agacta_check_SIFIR(tmp_path):
    r = _check(_agac(tmp_path))
    assert r.returncode == 0, (
        f"tam (senkron) kopya ağaçta -Check kırmızı — aparat ya da depo senkron değil:\n{r.stdout}\n{r.stderr}"
    )


@pytest.mark.parametrize("eksik", HEDEFLER)
def test_KRITIK_hedef_dosyasi_YOKSA_check_SIFIR_DEGIL(tmp_path, eksik):
    kok = _agac(tmp_path)
    (kok / eksik).unlink()
    r = _check(kok)
    assert r.returncode != 0, (
        f"`{eksik}` YOKKEN `sync_versions.ps1 -Check` çıkış 0 verdi — kanal sürümü hiçbir yerde senkronlanmıyor ama kapı yeşil "
        f"(D5.13 / B-9.10).\n{r.stdout[-1200:]}"
    )
    assert eksik in r.stdout.replace("\\", "/"), f"eksik hedef çıktıda adıyla bildirilmedi:\n{r.stdout[-1200:]}"
