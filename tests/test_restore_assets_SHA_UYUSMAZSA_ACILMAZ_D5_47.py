# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D5.47 (B-10.76) — `scripts/restore_assets.ps1`'in İKİ SHA256 doğrulaması (profil zip'i, base-deps) DAVRANIŞLA kapılı.

ARIZA (kör kapı, ölçüldü): betikte üç SHA denetimi var — profil zip'i (`home/vet/research.zip`), model parçası
(`research-2.zip`, D4.16) ve çekirdek modelin geldiği `base-deps.zip`. Yalnız parça denetimi davranışla ölçülüyordu; profil ve
base-deps denetimleri `if ($false)` yapılınca mevcut 3 restore testi YEŞİL kalıyordu → bozuk / değiştirilmiş bir indirme
SESSİZCE `release_assets\ai_models` altına açılır ve derlenen EXE'ye girer (tıbbi cihaz: yanlış ağırlık = yanlış klinik çıktı).

ÖLÇÜM (ağsız): betik GERÇEKTEN pwsh'ta koşar; `Invoke-WebRequest` GÖLGE işlev (URL → yerel sahte dosya; haritada olmayan adres
REDDEDİLİR; sahte URL'ler `.invalid`) — gölgenin devrede olduğu (CommandType = Function) betikten ÖNCE denetlenir, değilse 99.
Hedef kök `-KokOverride` tmp. Beklenen: SHA uyuşmazlığında çıkış ≠ 0 VE hiçbir dosya açılmaz VE indirilen bozuk zip silinir.
KARŞIT: doğru SHA ile aynı akış açar (ölçüm kör değil).
MUTASYON: profil ya da base-deps SHA denetimini `if ($false)` yapmak → KIRMIZI.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
BETIK = KOK / "scripts" / "restore_assets.ps1"
MANIFEST_URL = "https://github.com/mert61-python/pemf-update/releases/download/client-app-v1.8.0/manifest.json"
PWSH = shutil.which("pwsh")

pytestmark = pytest.mark.skipif(PWSH is None, reason="pwsh yok")

_SARMAL = r"""
param([string]$Betik, [string]$Harita, [Parameter(ValueFromRemainingArguments = $true)][string[]]$Kalan)
$ErrorActionPreference = 'Stop'
$global:SAHTE_HARITA = @{}
(Get-Content -Raw -LiteralPath $Harita | ConvertFrom-Json).psobject.Properties | ForEach-Object { $global:SAHTE_HARITA[$_.Name] = $_.Value }
function global:Invoke-WebRequest {
  param([string]$Uri, [string]$OutFile, [switch]$UseBasicParsing, [int]$TimeoutSec)
  Add-Content -LiteralPath $env:SAHTE_IWR_GUNLUK -Value ("IWR " + $Uri + " -> " + $OutFile)
  if (-not $global:SAHTE_HARITA.ContainsKey($Uri)) { throw "SAHTE IWR: haritada olmayan adres (ag YOK): $Uri" }
  $yerel = $global:SAHTE_HARITA[$Uri]
  if ($OutFile) { Copy-Item -LiteralPath $yerel -Destination $OutFile -Force; return }
  return [pscustomobject]@{ Content = (Get-Content -Raw -LiteralPath $yerel) }
}
if ((Get-Command Invoke-WebRequest).CommandType -ne 'Function') { Write-Output 'GOLGE DEVREDE DEGIL'; exit 99 }
$ad = @{}
for ($i = 0; $i -lt $Kalan.Count; $i += 2) { $ad[$Kalan[$i].TrimStart('-')] = $Kalan[$i + 1] }
try { & $Betik @ad; exit 0 } catch { Write-Output ("BETIK HATASI: " + $_.Exception.Message); exit 1 }
"""


def _zip(yol: Path, girdiler: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(yol, "w") as z:
        for ad, veri in girdiler.items():
            z.writestr(ad, veri)
    return yol


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _kos(tmp_path: Path, *, profil_sha_bozuk: bool = False, deps_sha_bozuk: bool = False):
    """Profil `home` + base-deps İNDİRME yolu (-DepsZipYolu VERİLMEZ: deps SHA denetimi yalnız indirme yolunda koşar)."""
    paket = tmp_path / "paket"
    paket.mkdir()
    home = _zip(paket / "home.zip", {"ai_models/ai_hub/ev_modeli/agirlik.onnx": b"PROFIL-AGIRLIK"})
    deps = _zip(
        paket / "base-deps.zip",
        {"PEMF_Backend/_internal/ai_models/ai_hub/inference_cat_organ/models/c.onnx": b"CEKIRDEK-ORGAN"},
    )
    home_url, deps_url = "https://paket.invalid/home.zip", "https://paket.invalid/base-deps.zip"
    manifest = {
        "profiles": {"home": {"url": home_url, "sha256": ("0" * 64 if profil_sha_bozuk else _sha(home)), "size": 1}},
        "layers": {
            "win-x64": {"deps": {"url": deps_url, "sha256": ("f" * 64 if deps_sha_bozuk else _sha(deps)), "size": 1}}
        },
    }
    (paket / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    harita = tmp_path / "harita.json"
    harita.write_text(
        json.dumps({MANIFEST_URL: str(paket / "manifest.json"), home_url: str(home), deps_url: str(deps)}),
        encoding="utf-8",
    )
    sarmal = tmp_path / "sarmal.ps1"
    sarmal.write_text(_SARMAL, encoding="utf-8-sig")
    gunluk = tmp_path / "iwr.log"
    gunluk.write_text("", encoding="utf-8")
    temp = tmp_path / "temp"
    temp.mkdir()
    kok = tmp_path / "kok"
    env = {**os.environ, "SAHTE_IWR_GUNLUK": str(gunluk), "TEMP": str(temp), "TMP": str(temp)}
    r = subprocess.run(
        [
            PWSH,
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(sarmal),
            str(BETIK),
            str(harita),
            "-Profiller",
            "home",
            "-KokOverride",
            str(kok),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=180,
    )
    assert "GOLGE DEVREDE DEGIL" not in r.stdout, (
        "Invoke-WebRequest gölgesi devreye girmedi — betik KOŞTURULMADI (ağ koruması)"
    )
    hub = kok / "release_assets" / "ai_models" / "ai_hub"
    acilan = sorted(p.relative_to(hub).as_posix() for p in hub.rglob("*") if p.is_file()) if hub.is_dir() else []
    artik_zip = sorted(p.name for p in temp.rglob("*.zip"))
    return r, acilan, artik_zip, gunluk.read_text(encoding="utf-8")


def test_KARSIT_dogru_SHA_ile_profil_ve_cekirdek_ACILIR(tmp_path):
    r, acilan, _artik, iwr = _kos(tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert acilan == ["ev_modeli/agirlik.onnx", "inference_cat_organ/models/c.onnx"], acilan
    assert "home.zip" in iwr and "base-deps.zip" in iwr, f"aparat: indirme yolu koşmadı: {iwr}"


def test_KRITIK_profil_zip_SHA_UYUSMAZSA_cikis_SIFIR_DEGIL_ve_HICBIR_SEY_ACILMAZ(tmp_path):
    r, acilan, artik, _iwr = _kos(tmp_path, profil_sha_bozuk=True)
    assert r.returncode != 0, f"profil zip'i SHA256 uyuşmazken betik BAŞARIYLA bitti (D5.47):\n{r.stdout[-800:]}"
    # Neden SHA denetiminin KENDİSİ olmalı (sonraki bir adımın tesadüfi düşüşü değil): betiği durduran istisna bu ileti.
    assert re.search(r"BETIK HATASI: \[home\] SHA256 UYUSMUYOR", r.stdout), (
        f"betik SHA uyuşmazlığıyla DURMADI (başka nedenle düştü ya da yalnız uyardı):\n{r.stdout[-800:]}"
    )
    assert acilan == [], f"SHA256'sı tutmayan profil zip'i AÇILDI (yanlış ağırlık kurulur, D5.47): {acilan}"
    assert "home.zip" not in artik, f"bozuk indirme diskte bırakıldı: {artik}"


def test_KRITIK_base_deps_SHA_UYUSMAZSA_cikis_SIFIR_DEGIL_ve_cekirdek_ACILMAZ(tmp_path):
    r, acilan, artik, _iwr = _kos(tmp_path, deps_sha_bozuk=True)
    assert r.returncode != 0, f"base-deps SHA256 uyuşmazken betik BAŞARIYLA bitti (D5.47):\n{r.stdout[-800:]}"
    assert re.search(r"BETIK HATASI: \[cekirdek\] SHA256 UYUSMUYOR", r.stdout), (
        f"betik SHA uyuşmazlığıyla DURMADI (başka nedenle düştü ya da yalnız uyardı):\n{r.stdout[-800:]}"
    )
    assert not any(a.startswith("inference_cat_organ/") for a in acilan), (
        f"SHA256'sı tutmayan base-deps'ten çekirdek model AÇILDI (D5.47): {acilan}"
    )
    assert "base-deps.zip" not in artik, f"bozuk indirme diskte bırakıldı: {artik}"
