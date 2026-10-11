# -*- coding: utf-8 -*-
"""D4.16 (B-9.24) — `scripts/restore_assets.ps1` manifestteki `model_parts` parçalarını (research-2.zip) sha DOĞRULAMALI indirip açar.

ARIZA: FAZ 4.5'ten (2026-08-26) beri araştırma profilinin iki büyük PT'si (renal XAI + in-process Yara-Kapanma, ~1,7 GB) 2 GiB
release sınırı yüzünden research.zip'e sığmaz ve AYRI parça zip'inde (`model_parts.research[0]` = research-2.zip) gider. Betik yalnız
`profiles`'ı geziyordu: BUILD.md sırasıyla yeniden kurulan derleme makinesi PT'siz EXE / installer üretir (renal XAI ve Yara-Kapanma
sahada ölür) ve betik yine "Geri yuklendi" der ([ÖLÇTÜM] HEAD'de `model_parts` / `research-2` geçişi 0).

Ölçüm: betik GERÇEKTEN pwsh'ta koşar; `Invoke-WebRequest` bir GÖLGE işlevle değiştirilir (URL → yerel sahte dosya; her çağrı
günlüğe). ⚠️ Gölge işlevin devrede olduğu (CommandType = Function) betik koşmadan ÖNCE denetlenir, değilse sarmalayıcı 99 ile çıkar
— ağa istek imkânsız; sahte manifestteki URL'ler ayrıca `.invalid`. Hedef kök `-KokOverride` tmp; çekirdek model `-DepsZipYolu` ile
yerel sahte zip'ten (ağsız).
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
BETIK = KOK / "scripts" / "restore_assets.ps1"
MANIFEST_URL = "https://github.com/mert61-python/pemf-update/releases/download/client-app-v1.8.0/manifest.json"

pytestmark = pytest.mark.skipif(shutil.which("pwsh") is None, reason="pwsh yok")

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
for ($i = 0; $i -lt $Kalan.Count; $i += 2) { $ad[$Kalan[$i].TrimStart('-')] = $Kalan[$i + 1] }  # dizi yayması adları konumsal geçirir
try { & $Betik @ad; exit 0 } catch { Write-Output ("BETIK HATASI: " + $_.Exception.Message); exit 1 }
"""


def _zip(yol: Path, girdiler: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(yol, "w") as z:
        for ad, veri in girdiler.items():
            z.writestr(ad, veri)
    return yol


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _kur(tmp_path: Path, *, parca_sha_bozuk: bool = False, parcasiz: bool = False, kabuk: str = "pwsh"):
    paket = tmp_path / "paket"
    paket.mkdir()
    research = _zip(paket / "research.zip", {"ai_models/ai_hub/em_petri/PetriNet_v3.onnx": b"ANA-ONNX"})
    parca = _zip(
        paket / "research-2.zip",
        {
            "ai_models/ai_hub/inference_paper_dilek_hoca/ginoro_parca.pt": b"PARCA-PT-1",
            "ai_models/ai_hub/inference_renal_histopath_kmc/v22_parca.pt": b"PARCA-PT-2",
        },
    )
    deps = _zip(
        paket / "base-deps.zip", {"PEMF_Backend/_internal/ai_models/ai_hub/inference_cat_organ/models/c.onnx": b"ORGAN"}
    )
    ana_url, parca_url = "https://paket.invalid/research.zip", "https://paket.invalid/research-2.zip"
    manifest = {
        "profiles": {"research": {"url": ana_url, "sha256": _sha(research), "size": research.stat().st_size}},
        "layers": {
            "win-x64": {"deps": {"url": "https://paket.invalid/base-deps.zip", "sha256": _sha(deps), "size": 1}}
        },
    }
    if not parcasiz:
        manifest["model_parts"] = {
            "research": [
                {
                    "url": parca_url,
                    "sha256": ("0" * 64 if parca_sha_bozuk else _sha(parca)),
                    "size": parca.stat().st_size,
                }
            ]
        }
    (paket / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    harita = tmp_path / "harita.json"
    harita.write_text(
        json.dumps({MANIFEST_URL: str(paket / "manifest.json"), ana_url: str(research), parca_url: str(parca)}),
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
    if kabuk != "pwsh":  # pwsh 7 -> python -> 5.1 zincirinde PSModulePath 5.1'in modül otomatik yüklemesini bozar
        env = {k: v for k, v in env.items() if k.upper() != "PSMODULEPATH"}
    r = subprocess.run(
        [
            kabuk,
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(sarmal),
            str(BETIK),
            str(harita),
            "-Profiller",
            "research",
            "-DepsZipYolu",
            str(deps),
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
        "Invoke-WebRequest golgesi devreye girmedi — betik KOSTURULMADI (ag korumasi)"
    )
    return r, kok / "release_assets" / "ai_models" / "ai_hub", gunluk.read_text(encoding="utf-8")


def test_KRITIK_model_parcasi_sha_DOGRULAMALI_indirilip_ACILIR(tmp_path):
    r, ai_hub, gunluk = _kur(tmp_path)
    assert r.returncode == 0, f"betik basarisiz (rc={r.returncode}):\n{r.stdout[-1500:]}\n{r.stderr[-800:]}"
    assert (ai_hub / "em_petri" / "PetriNet_v3.onnx").read_bytes() == b"ANA-ONNX", "on-kosul: ana research.zip acilmadi"
    assert "https://paket.invalid/research-2.zip" in gunluk, (
        f"model_parts parcasi (research-2.zip) HIC INDIRILMEDI — PT'siz derleme uretilir:\n{gunluk}"
    )
    assert (ai_hub / "inference_paper_dilek_hoca" / "ginoro_parca.pt").read_bytes() == b"PARCA-PT-1"
    assert (ai_hub / "inference_renal_histopath_kmc" / "v22_parca.pt").read_bytes() == b"PARCA-PT-2"
    assert "research-2" in r.stdout and "sha256 dogrulandi" in r.stdout, (
        f"parca sha dogrulamasi raporlanmadi:\n{r.stdout[-1500:]}"
    )


def test_KRITIK_parca_sha_UYUSMAZSA_kurulum_IPTAL_ve_cikis_SIFIR_DEGIL(tmp_path):
    """Bozuk / yarım parça sessizce açılmaz: tıbbi cihaz — yanlış ağırlık yanlış klinik çıktı. `exit 0` ile yutulan hata = KIRMIZI."""
    r, ai_hub, gunluk = _kur(tmp_path, parca_sha_bozuk=True)
    assert r.returncode != 0, f"sha uyusmayan parca ile betik BASARILI dondu:\n{r.stdout[-1500:]}"
    assert "SHA256 UYUSMUYOR" in r.stdout, r.stdout[-1500:]
    assert not (ai_hub / "inference_paper_dilek_hoca" / "ginoro_parca.pt").exists(), "sha'si tutmayan parca ACILDI"
    assert "Geri yuklendi" not in r.stdout, "hata varken 'Geri yuklendi' basildi"


def test_KARSIT_parcasiz_manifest_eski_davranisla_GECER(tmp_path):
    """Ölçücü kör değil ve geri-uyum: `model_parts`'sız manifestte parça indirilmez, betik başarılı."""
    r, ai_hub, gunluk = _kur(tmp_path, parcasiz=True)
    assert r.returncode == 0, f"{r.stdout[-1500:]}\n{r.stderr[-800:]}"
    assert "research-2" not in gunluk and (ai_hub / "em_petri" / "PetriNet_v3.onnx").is_file()
    assert MANIFEST_URL in gunluk, "golge gunlugu bos — olcucu calismadi"


# ── S-4B.1 (4-A incelemesi A1 S3; Y123 önerilen): Windows PowerShell 5.1 ─────────────────────────────────────────────
# BUILD.md taze makinede `.\scripts\restore_assets.ps1` diye çağırıyor (Windows'un varsayılan kabuğu 5.1; pwsh 7 henüz yok
# olabilir). Dosya BOM'suz UTF-8 ve Türkçe / em-dash taşıyordu → 5.1 onu ANSI okur: 18 ayrıştırma hatası, betik HİÇ başlamaz.
_PS51 = shutil.which("powershell.exe")


@pytest.mark.skipif(os.name != "nt" or not _PS51, reason="Windows PowerShell 5.1 yalnız Windows'ta")
def test_KRITIK_PS51_ayristiricisi_HATASIZ_S4B1(tmp_path):
    betik = (
        "$t = $null; $e = $null; "
        "[void][System.Management.Automation.Language.Parser]::ParseFile($args[0], [ref]$t, [ref]$e); "
        "Write-Output ('AYRISTIR ' + $e.Count)"
    )
    a = tmp_path / "ayristir.ps1"
    a.write_bytes(b"\xef\xbb\xbf" + betik.encode("utf-8"))
    env = {k: v for k, v in os.environ.items() if k.upper() != "PSMODULEPATH"}
    r = subprocess.run(
        [_PS51, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(a), str(BETIK)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=120,
    )
    assert "AYRISTIR 0" in r.stdout, (
        f"restore_assets.ps1 Windows PowerShell 5.1'de AYRISTIRILAMIYOR: {r.stdout[-600:]}{r.stderr[-600:]}"
    )


@pytest.mark.skipif(os.name != "nt" or not _PS51, reason="Windows PowerShell 5.1 yalnız Windows'ta")
def test_KRITIK_PS51_ile_model_parcasi_ACILIR_S4B1(tmp_path):
    """Ayrışması yetmez: 5.1'de de profil + parça + çekirdek akışı tamamlanır (D4.16'nın 5.1 ikizi)."""
    r, ai_hub, gunluk = _kur(tmp_path, kabuk=_PS51)
    assert r.returncode == 0, f"5.1'de betik basarisiz (rc={r.returncode}):\n{r.stdout[-1500:]}\n{r.stderr[-800:]}"
    assert (ai_hub / "inference_paper_dilek_hoca" / "ginoro_parca.pt").read_bytes() == b"PARCA-PT-1"
    assert "https://paket.invalid/research-2.zip" in gunluk
