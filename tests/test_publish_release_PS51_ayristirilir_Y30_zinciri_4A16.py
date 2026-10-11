# -*- coding: utf-8 -*-
"""4A-1.6 (A1 incelemesi; 4-B ile) — Y30'un taşıyıcısı `publish_release.ps1` Windows PowerShell 5.1'de AYRIŞTIRILAMIYOR.

ÖLÇÜLEN (A1, 2026-10-11; `_inceleme/kayit/k3_ps51_ayristir.txt`, `k3_sonda.txt`): dosya BOM'suz UTF-8 ve `:49`daki çift tırnaklı
dizgede `—` (U+2014) var. 5.1 BOM'suz betiği ANSI (cp1254/1252) okur → E2 80 94 baytlarının sonuncusu `”` (U+201D) olur ve
PowerShell bunu TIRNAK sayar → "The string is missing the terminator" (2 ayrıştırma hatası). `KULLANIM` satırı betiği
`.\scripts\publish_release.ps1` diye çağırıyor (Windows'un varsayılan kabuğu 5.1). Gölgeli publish 5.1'de: süit rc 3 ve rc 0'da
kayıt BOŞ (süit hiç çağrılmaz), rc 9 — betik hiç başlamaz (fail-closed: yayın da olmaz). D4.10 kapısı yalnız pwsh'ta ölçüyor.
`yayin_oncesi_suit.ps1` (BOM'lu) 5.1'de ayrışır ve çıkış kodlarını pwsh ile AYNI taşır (0/1/5/3 ölçüldü).

Kapı: (1) 5.1 ayrıştırıcısı publish + süit betiğinde 0 hata; (2) gölgeli publish 5.1'de: süit rc 3 → kayıt YALNIZ `SUIT`, rc 9 "Y30";
süit rc 0 → `SUIT` → `GIT credential fill` (D4.10'un pwsh kapısının 5.1 ikizi).
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
BETIKLER = KOK / "scripts"
_PS51 = shutil.which("powershell.exe")

_TASLAK_SUIT = "Add-Content -LiteralPath $env:Y30_KAYIT -Value 'SUIT'\nexit [int]$env:Y30_SUIT_RC\n"
_SARMAL = r"""param([string]$Publish, [string]$Asset)
$ErrorActionPreference = 'Stop'
function global:git { Add-Content -LiteralPath $env:Y30_KAYIT -Value ('GIT ' + ($args -join ' ')) }
function global:gh { Add-Content -LiteralPath $env:Y30_KAYIT -Value 'GH'; throw 'golge gh' }
function global:Invoke-RestMethod { Add-Content -LiteralPath $env:Y30_KAYIT -Value 'IRM'; throw 'golge irm' }
function global:Invoke-WebRequest { Add-Content -LiteralPath $env:Y30_KAYIT -Value 'IWR'; throw 'golge iwr' }
try { & $Publish -Branch exe -Version 9.9.9 -AssetPath $Asset; Write-Host 'PUBLISH-BITTI'; exit 0 }
catch { Write-Host ('PUBLISH-HATA: ' + $_.Exception.Message); exit 9 }
"""

pytestmark = pytest.mark.skipif(os.name != "nt" or not _PS51, reason="Windows PowerShell 5.1 yalnız Windows'ta")


def _bom(yol: Path, metin: str) -> None:
    yol.write_bytes(b"\xef\xbb\xbf" + metin.encode("utf-8"))


def test_KRITIK_publish_ve_suit_betigi_PS51_ayristiricisinda_HATASIZ(tmp_path):
    betik = (
        "foreach ($d in $args) { $t = $null; $e = $null; "
        "[void][System.Management.Automation.Language.Parser]::ParseFile($d, [ref]$t, [ref]$e); "
        "Write-Host ('AYRISTIR ' + $e.Count + ' ' + (Split-Path -Leaf $d)) }"
    )
    _bom(tmp_path / "a.ps1", betik)
    r = subprocess.run(
        [
            _PS51,
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(tmp_path / "a.ps1"),
            str(BETIKLER / "publish_release.ps1"),
            str(BETIKLER / "yayin_oncesi_suit.ps1"),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
    )
    satirlar = [s for s in r.stdout.splitlines() if s.startswith("AYRISTIR")]
    assert len(satirlar) == 2, r.stdout + r.stderr
    hatali = [s for s in satirlar if not s.startswith("AYRISTIR 0 ")]
    assert not hatali, f"Windows PowerShell 5.1 betiği AYRIŞTIRAMIYOR (BOM'suz UTF-8 + ASCII dışı): {hatali}"


def _publish_51(tmp_path: Path, suit_rc: int):
    d = tmp_path / f"rc{suit_rc}"
    (d / "scripts").mkdir(parents=True)
    (d / "bos_path").mkdir()
    shutil.copy2(BETIKLER / "publish_release.ps1", d / "scripts" / "publish_release.ps1")
    _bom(d / "scripts" / "yayin_oncesi_suit.ps1", _TASLAK_SUIT)
    _bom(d / "sarmal.ps1", _SARMAL)
    (d / "asset.bin").write_bytes(b"x")
    kayit = d / "kayit.txt"
    kayit.write_text("", encoding="utf-8")
    env = {
        k: v for k, v in os.environ.items() if k.upper() not in ("PATH", "PEMF_CAPRAZ_KAYNAK_ZORUNLU", "PSMODULEPATH")
    }
    env.update({"PATH": str(d / "bos_path"), "Y30_KAYIT": str(kayit), "Y30_SUIT_RC": str(suit_rc)})
    env.update({"HTTPS_PROXY": "http://127.0.0.1:9", "HTTP_PROXY": "http://127.0.0.1:9", "GIT_TERMINAL_PROMPT": "0"})
    komut = [_PS51, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(d / "sarmal.ps1")]
    komut += ["-Publish", str(d / "scripts" / "publish_release.ps1"), "-Asset", str(d / "asset.bin")]
    r = subprocess.run(
        komut, cwd=d, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180
    )
    return (
        r.returncode,
        [s.strip() for s in kayit.read_text(encoding="utf-8-sig").splitlines() if s.strip()],
        r.stdout + r.stderr,
    )


def test_KRITIK_PS51_publish_SUIT_GECMEZSE_durur_GECERSE_ilerler(tmp_path):
    rc3, k3, c3 = _publish_51(tmp_path, 3)
    assert k3 == ["SUIT"] and rc3 == 9 and "Y30" in c3, (
        f"5.1: süit düşünce beklenen yalnız SUIT + Y30: rc={rc3} {k3}\n{c3[-600:]}"
    )
    rc0, k0, c0 = _publish_51(tmp_path, 0)
    assert k0[:1] == ["SUIT"] and any(s.startswith("GIT credential") for s in k0[1:]) and "IRM" not in k0, (
        f"5.1: süit geçince SUIT → GIT bekleniyordu: rc={rc0} {k0}\n{c0[-600:]}"
    )
