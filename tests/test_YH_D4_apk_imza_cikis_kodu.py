# -*- coding: utf-8 -*-
"""YH D4 (D4B-İNC §9 #10) — `build_apk.ps1` imza denetimi `apksigner verify` HATASINI (çıkış kodu) görür.

ÖLÇÜLEN (YH, 2026-10-22; `build_apk.ps1:139` HEAD): çıktı yalnız "CN=Android Debug" için okunuyordu; doğrulama BAŞARISIZ olunca (imzasız /
bozuk / şema uyuşmaz APK, çıkış ≠ 0) akış "release" dalına düşüp boş DN üzerinde `.Trim()` çağırıyordu — ya anlamsız bir "null" hatası
ya da yanlış "Imza OK". Doğrulanamayan APK `release_assets\\` altında yayın adıyla (site + OTA'nın indirdiği adlar) kalıyordu.

Kapı (APK / gradle / gerçek apksigner YOK): karar fonksiyonu `Test-ApkImzasi` betikten AST ile çıkarılır, sahte apksigner (`.cmd`, istenen
çıktı + çıkış kodu) ile çağrılır. Ana akışın 'hata' dalı statik olarak: yayın adlarını yeniden adlandırır ve `Die` (çıkış 1) ile durur.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
BETIK = KOK / "build_tools" / "build_apk.ps1"
_PWSH = shutil.which("pwsh")

_CAGIR = r"""param([string]$Betik, [string]$Sahte)
$ErrorActionPreference = 'Stop'
$t = $null; $e = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($Betik, [ref]$t, [ref]$e)
if ($e.Count) { throw "ayristirma hatasi: $($e.Count)" }
$f = $ast.Find({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq 'Test-ApkImzasi' }, $true)
if (-not $f) { throw 'Test-ApkImzasi yok' }
Invoke-Expression $f.Extent.Text
$s = Test-ApkImzasi -Apksigner $Sahte -Apk 'C:\yok\PEMF_Vet_Mobil.apk'
[IO.File]::WriteAllText($env:YH_D4_CIKTI, (ConvertTo-Json -InputObject @{ durum = $s.durum; cikis = $s.cikis; dn = $s.dn } -Compress), (New-Object Text.UTF8Encoding $false))
"""


def _imza(tmp_path: Path, satirlar: list[str], cikis: int) -> dict:
    if not _PWSH:
        pytest.skip("pwsh (PowerShell 7) yok")
    if os.name != "nt":
        pytest.skip("sahte apksigner .cmd — yalnız Windows (build_apk.ps1 de yalnız Windows'ta koşar)")
    sahte = tmp_path / "apksigner.cmd"
    sahte.write_text(
        "@echo off\r\n" + "".join(f"echo {s}\r\n" for s in satirlar) + f"exit /b {cikis}\r\n", encoding="ascii"
    )
    (tmp_path / "cagir.ps1").write_bytes(b"\xef\xbb\xbf" + _CAGIR.encode("utf-8"))
    cikti = tmp_path / "sonuc.json"
    r = subprocess.run(
        [
            _PWSH,
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(tmp_path / "cagir.ps1"),
            "-Betik",
            str(BETIK),
            "-Sahte",
            str(sahte),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        env={**os.environ, "YH_D4_CIKTI": str(cikti)},
    )
    assert r.returncode == 0, r.stdout + r.stderr
    return json.loads(cikti.read_text(encoding="utf-8"))


def test_release_imza_DN_ile_OK(tmp_path):
    s = _imza(tmp_path, ["Verifies", "Signer #1 certificate DN: CN=PEMF Medical, O=PEMF"], 0)
    assert s["durum"] == "release" and s["dn"] == "Signer #1 certificate DN: CN=PEMF Medical, O=PEMF", s


def test_debug_anahtari_TANINIR(tmp_path):
    assert (
        _imza(tmp_path, ["Verifies", "Signer #1 certificate DN: C=US, O=Android, CN=Android Debug"], 0)["durum"]
        == "debug"
    )


def test_KRITIK_dogrulama_BASARISIZ_cikis_kodu_HATA_sayilir(tmp_path):
    s = _imza(tmp_path, ["DOES NOT VERIFY", "ERROR: Missing META-INF/MANIFEST.MF"], 1)
    assert s["durum"] == "hata" and s["cikis"] == 1, f"başarısız apksigner (çıkış 1) imza OK / debug sayıldı: {s}"


def test_KRITIK_cikis_kodu_ONCELIKLI_ciktida_DN_olsa_bile(tmp_path):
    """Çıktıda sertifika satırı (hatta debug DN) geçse de çıkış ≠ 0 → doğrulanmamış (ör. v2 şema imzası bozuk, v1 okunur)."""
    s = _imza(
        tmp_path,
        ["Signer #1 certificate DN: CN=PEMF Medical", "ERROR: APK Signature Scheme v2 signer #1: digest mismatch"],
        1,
    )
    assert s["durum"] == "hata", s


def test_KRITIK_basarili_ama_SERTIFIKASIZ_cikti_HATA_sayilir(tmp_path):
    assert _imza(tmp_path, ["Verifies"], 0)["durum"] == "hata"


def test_KRITIK_ana_akis_HATA_dalinda_KOPYADAN_ONCE_DURUR():
    """18K K5 · D3.25 (eski ad `…_HATA_dalinda_yayin_adlarini_kaldirir_ve_DURUR`): doğrulama artık gradle çıktısında, release_assets'e
    KOPYADAN ÖNCE — 'hata' dalı yayın adlarını yeniden adlandırmak yerine hiç oluşturmadan Die ile durur. Davranış kapısı:
    tests/test_18K_K5_apk_imzasi_KOPYADAN_ONCE.py (gerçek sıra, sahte apksigner + Copy-Item kaydı)."""
    metin = BETIK.read_text(encoding="utf-8-sig")
    m = re.search(r"if \(\$imza\.durum -eq 'hata'\) \{(.*?)\n\}", metin, re.S)
    assert m, "ana akışta 'hata' dalı yok — Test-ApkImzasi sonucu karar vermiyor"
    dal = m.group(1)
    assert re.search(r"^\s*Die ", dal, re.M), "hata dalı Die (çıkış 1) ile durmuyor"
    assert metin.index("-Apk $apk") < metin.index("Copy-Item $apk"), (
        "imza release_assets kopyasından SONRA doğrulanıyor"
    )
    assert "$certs" not in metin, "eski çıktı-yalnız karar (`$certs`) hâlâ betikte"
