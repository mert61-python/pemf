# -*- coding: utf-8 -*-
"""18K K5 · D3.25 — `build_apk.ps1` APK imzasını release_assets'e KOPYALAMADAN ÖNCE doğrular; debug imza / doğrulanamayan imza /
apksigner yokluğu → açık Die (çıkış 1), KOPYA YOK.

ÖLÇÜLEN (HEAD `9dccf7d9` öncesi): kopya (`release_assets\\PEMF_Vet_Mobil.apk` + sürümlü ad — site ve OTA bu adları indirir) imza
denetiminden ÖNCE yapılıyordu; debug imzada yalnız uyarı kutusu (çıkış 0), apksigner yokken yalnız uyarı (çıkış 0) → debug anahtarıyla
(depoda commit'li, parolası herkeste aynı) imzalı APK yayın adıyla kalıyordu.

Kapı (APK / gradle / gerçek apksigner YOK): betiğin GERÇEK bölümü (gradle sonrası `$apk` satırından scratch temizliğine dek) gerçek
sırasıyla pwsh'te koşar; `Copy-Item` gölgelenir (işlev > cmdlet önceliği) ve çağrıları kaydeder; sahte `apksigner.bat` sahte
`LOCALAPPDATA\\Android\\Sdk\\build-tools\\…` altında istenen çıktı + çıkış koduyla.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
BETIK = KOK / "build_tools" / "build_apk.ps1"
_PWSH = shutil.which("pwsh")

DEBUG = ["Signer #1 certificate DN: CN=Android Debug, O=Android, C=US"]
RELEASE = ["Verifies", "Signer #1 certificate DN: CN=PEMF Vet, OU=V-PEMF Technologies, O=V-PEMF, C=TR"]


def _bolum() -> str:
    metin = BETIK.read_text(encoding="utf-8-sig")
    bas = metin.index('$apk = Join-Path $android "app\\build\\outputs\\apk\\release\\app-release.apk"')
    son = metin.index("if ($RemoveScratch)", bas)
    return metin[bas:son]


def _kos(tmp_path: Path, apksigner: tuple[list[str], int] | None) -> tuple[int, list[str], str]:
    if not _PWSH or os.name != "nt":
        pytest.skip("pwsh + Windows gerekir (build_apk.ps1 yalnız Windows'ta koşar)")
    android = tmp_path / "android"
    apk = android / "app" / "build" / "outputs" / "apk" / "release" / "app-release.apk"
    apk.parent.mkdir(parents=True)
    apk.write_bytes(b"PK-sahte-apk")
    gui = tmp_path / "guii"
    gui.mkdir()
    (gui / "versions.json").write_text('{"mobile": {"name": "9.9.9"}}', encoding="utf-8")
    yerel = tmp_path / "yerel"
    if apksigner is not None:
        satirlar, cikis = apksigner
        bt = yerel / "Android" / "Sdk" / "build-tools" / "34.0.0"
        bt.mkdir(parents=True)
        (bt / "apksigner.bat").write_text(
            "@echo off\r\n" + "".join(f"echo {s}\r\n" for s in satirlar) + f"exit /b {cikis}\r\n", encoding="ascii"
        )
    else:
        yerel.mkdir()
    kayit = tmp_path / "kopyalar.txt"
    on = (
        "$ErrorActionPreference = 'Continue'\n"
        "function Info($m){ Write-Host \"[apk] $m\" }\n"
        "function Die($m){ Write-Host \"[apk] HATA: $m\"; exit 1 }\n"
        f"function Copy-Item {{ Add-Content -LiteralPath '{kayit}' -Value ($args -join ' ') }}\n"
        f"$env:LOCALAPPDATA = '{yerel}'\n$android = '{android}'\n$GuiRoot = '{gui}'\n"
    )
    betik = tmp_path / "bolum.ps1"
    betik.write_text(on + _bolum() + "\nexit 0\n", encoding="utf-8-sig")
    r = subprocess.run(
        [_PWSH, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(betik)],
        capture_output=True,
        timeout=180,
    )
    kopyalar = kayit.read_text(encoding="utf-8-sig").splitlines() if kayit.exists() else []
    return r.returncode, kopyalar, (r.stdout + r.stderr).decode("utf-8", errors="replace")


def test_KRITIK_18K_K5_DEBUG_imzali_APK_KOPYALANMAZ_ve_DURUR(tmp_path):
    rc, kopyalar, cikti = _kos(tmp_path, (DEBUG, 0))
    print("K5OLC|debug|", rc, kopyalar)
    assert rc == 1, f"debug imzalı APK'da betik durmadı (rc={rc}):\n{cikti[-1200:]}"
    assert kopyalar == [], f"debug imzalı APK release_assets'e kopyalandı: {kopyalar}"


def test_KRITIK_18K_K5_apksigner_YOKKEN_KOPYALANMAZ_ve_DURUR(tmp_path):
    rc, kopyalar, cikti = _kos(tmp_path, None)
    print("K5OLC|apksigner_yok|", rc, kopyalar)
    assert rc == 1 and kopyalar == [], f"rc={rc} kopyalar={kopyalar}\n{cikti[-1200:]}"


def test_KRITIK_18K_K5_dogrulanamayan_imza_KOPYALANMAZ(tmp_path):
    rc, kopyalar, cikti = _kos(tmp_path, (["ERROR: APK Signature Scheme v2 signer #1: digest mismatch"], 1))
    print("K5OLC|hata|", rc, kopyalar)
    assert rc == 1 and kopyalar == [], f"rc={rc} kopyalar={kopyalar}\n{cikti[-1200:]}"


def test_18K_K5_KARSIT_release_imzali_APK_iki_yayin_adina_kopyalanir(tmp_path):
    rc, kopyalar, cikti = _kos(tmp_path, (RELEASE, 0))
    print("K5OLC|release|", rc, kopyalar)
    assert rc == 0, f"release imzalı APK reddedildi (rc={rc}):\n{cikti[-1200:]}"
    assert len(kopyalar) == 2 and kopyalar[0].endswith("PEMF_Vet_Mobil.apk -Force"), kopyalar
    assert kopyalar[1].endswith("PEMF_Vet_Mobil-9.9.9.apk -Force"), kopyalar
