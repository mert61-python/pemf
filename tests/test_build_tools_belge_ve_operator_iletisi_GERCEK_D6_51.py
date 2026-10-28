# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D6.51 (B-10.185 · B-10.186) — build_tools belgesi ve operatör iletileri F4 (apps/backend) ve korumalı derleme ağacı sonrasına uyar.

Kusur: `build_tools/README.md` çözücüyü `../utils/source_crypto.py`'de (YOK — gerçeği `apps/backend/utils/source_crypto.py`) ve
installer çıktısını sabit `v1.9.20` örneğiyle gösteriyordu; `build_installer.ps1` sonunda operatöre PyInstaller çıktısı olarak SABİT
`dist\\PEMF_Backend\\` yazıyordu (gerçek `$OutputDir` = `PEMF_BUILD\\dist\\PEMF_Backend`); `.iss` başlığı `..\\dist\\PEMF_Backend`
beklediğini ve `PEMFBackendSetup_v{VERSION}` ürettiğini söylüyordu (tanımlar: `BuildOutput` `..\\PEMF_BUILD\\…`, `OutputBaseFilename`
`PEMFBackendSetup_{#ModeName}_v…`); spec ve `source_crypto` parolanın `pemf_source_key` adıyla gömüldüğünü söylüyordu (spec onu
`_internal/_static_password.py` olarak koyar). README bağlantı kapısı ters tırnak içindeki yolları denetlemiyordu.

Gerçek derleme YOK (PyInstaller / Inno / build betiği koşturulmaz): metin + PowerShell ayrıştırıcısı.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import capraz
import pytest

KOK = Path(__file__).resolve().parent.parent
BT = KOK / "build_tools"
README = BT / "README.md"
PS1 = BT / "build_installer.ps1"
ISS = BT / "PEMF_Backend_Setup.iss"
SPEC = BT / "PEMF_Backend_onedir.spec"
CRYPTO = KOK / "apps" / "backend" / "utils" / "source_crypto.py"
PWSH = shutil.which("pwsh")
KAYNAK_UZANTI = (".py", ".ps1", ".spec", ".iss", ".sh", ".md", ".txt", ".bat")


def _git_dosyalari() -> set[str]:
    r = subprocess.run(
        ["git", "-C", str(KOK), "ls-files"], capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    return {Path(s).name for s in r.stdout.splitlines()}


def test_KRITIK_build_tools_README_ters_tirnakli_KAYNAK_yollari_diskte_VAR_D6_51():
    """Yol içeren (`/`) kaynak dosyası build_tools/'a göre diskte olmalı; çıplak ad depoda bir yerde izlenmeli. Çıktılar (zip / exe / apk /
    dizin) kaynak uzantısı taşımadığı için ölçülmez."""
    adlar = _git_dosyalari()
    kotu = []
    for tok in re.findall(r"`([^`\s]+)`", README.read_text(encoding="utf-8")):
        tok = tok.rstrip("\\")
        if not tok.lower().endswith(KAYNAK_UZANTI) or re.fullmatch(r"\.\w+", tok):  # `.py` = uzantı anılışı, yol değil
            continue
        if "/" in tok or "\\" in tok:
            if not (BT / tok.replace("\\", "/")).resolve().exists():
                kotu.append(f"{tok} (build_tools/'a göre YOK)")
        elif tok not in adlar and tok != "build-launcher.bat":  # README'nin "YOKtur" dediği tek ad
            kotu.append(f"{tok} (depoda izlenmiyor)")
    assert not kotu, "build_tools/README.md olmayan kaynak yolunu gösteriyor: " + "; ".join(kotu)


def test_KRITIK_README_installer_ornegi_iss_OutputBaseFilename_ile_UYUMLU_D6_51():
    iss = ISS.read_text(encoding="utf-8")
    m = re.search(r"^OutputBaseFilename=(\S+)", iss, re.M)
    assert m and "{#ModeName}" in m.group(1), f"iss OutputBaseFilename okunamadı: {m and m.group(1)}"
    satir = next((s for s in README.read_text(encoding="utf-8").splitlines() if s.startswith("| `Output/`")), "")
    assert satir and not re.search(r"PEMFBackendSetup_\w+_v\d+\.\d+\.\d+\.exe", satir), (
        f"README Output/ satırı sabit (bayatlayan) bir sürüm örneği taşıyor; desen kullanın: {satir}"
    )
    assert "PEMFBackendSetup_<mod>_v<sürüm>.exe" in satir, satir


def test_KRITIK_iss_baslik_yorumu_BuildOutput_ve_cikti_adi_TANIMLA_ayni_D6_51():
    iss = ISS.read_text(encoding="utf-8")
    tanim = re.search(r'#define BuildOutput\s+"([^"]+)"', iss)
    assert tanim, "iss BuildOutput tanımı bulunamadı"
    baslik = iss[: iss.find("[Setup]")] if "[Setup]" in iss else iss[:3000]
    baslik = baslik[: baslik.find("#ifndef BuildOutput")] if "#ifndef BuildOutput" in baslik else baslik
    assert '"..\\dist\\PEMF_Backend"' not in baslik, (
        "iss başlığı installer'ın eski korumasız ..\\dist\\PEMF_Backend ağacını beklediğini söylüyor"
    )
    assert f'"{tanim.group(1)}"' in baslik, f"iss başlığı varsayılan BuildOutput'u ({tanim.group(1)}) söylemiyor"
    cikti = re.search(r"^; CIKTI: (.+)$", iss, re.M)
    assert cikti and "{ModeName}" in cikti.group(1), (
        f"iss başlığı çıktı adını OutputBaseFilename'den farklı söylüyor: {cikti and cikti.group(1)}"
    )


@pytest.mark.skipif((PWSH is None) and not capraz.ZORUNLU, reason="pwsh (PowerShell 7) yok — ayrıştırıcı koşturulamaz")
def test_KRITIK_build_installer_ozeti_PyInstaller_ciktisini_OutputDir_ile_soyler_D6_51(tmp_path):
    betik = tmp_path / "ozet.ps1"
    lit = "'" + str(PS1).replace("'", "''") + "'"
    betik.write_text(
        "$t=$null;$e=$null\n"
        f"$ast=[System.Management.Automation.Language.Parser]::ParseFile({lit},[ref]$t,[ref]$e)\n"
        "if ($e.Count) { Write-Output ('PARSE-ERROR ' + $e.Count); exit 3 }\n"
        "$c=@($ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.CommandAst] -and $n.GetCommandName() -eq 'Write-Host' }, $true))\n"
        "foreach ($k in $c) { $a=$k.CommandElements[1]; if (\"$($a.Extent.Text)\" -match 'PyInstaller Ciktisi') {\n"
        "  $v=@($a.FindAll({ param($n) $n -is [System.Management.Automation.Language.VariableExpressionAst] }, $true) | ForEach-Object { $_.VariablePath.UserPath })\n"
        "  Write-Output ('OZET|' + $a.GetType().Name + '|' + ($v -join ',') + '|' + $a.Extent.Text) } }\n",
        encoding="utf-8-sig",
    )
    r = subprocess.run(
        [PWSH, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(betik)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    ozet = [s.split("|", 3) for s in r.stdout.splitlines() if s.startswith("OZET|")]
    assert r.returncode == 0 and len(ozet) == 1, (
        f"özet satırı (PyInstaller Ciktisi) tek ve ayrıştırılabilir değil:\n{r.stdout}\n{r.stderr}"
    )
    _, tur, degiskenler, metin = ozet[0]
    assert tur == "ExpandableStringExpressionAst" and "OutputDir" in degiskenler.split(","), (
        f"özet PyInstaller çıktısını gerçek $OutputDir yerine SABİT yolla söylüyor: {metin}"
    )
    assert "dist\\PEMF_Backend" not in metin, metin


def test_KRITIK_parola_gomme_adi_spec_ve_source_crypto_belgesinde_GERCEK_D6_51():
    spec = SPEC.read_text(encoding="utf-8")
    assert re.search(r"datas\.append\(\(_pw_src, '\.'\)\)", spec), (
        "spec parolayı kök seviyeye (_internal/) koymuyor — ölçüt değişti"
    )
    for kaynak, metin in (("spec", spec), ("source_crypto", CRYPTO.read_text(encoding="utf-8"))):
        assert not re.search(r"pemf_source_key`? adıyla", metin), (
            f"{kaynak}: parolanın `pemf_source_key` adıyla gömüldüğünü söylüyor (gerçekte _internal/_static_password.py)"
        )
    assert "(pemf_source_key)')" not in spec, "spec derleme günlüğü parolayı pemf_source_key adıyla gömdüğünü yazıyor"
    assert "_internal/_static_password.py" in spec and "_internal/_static_password.py" in CRYPTO.read_text(
        encoding="utf-8"
    )
    assert 'print("Çıktı: dist/PEMF_Backend/PEMF_Backend.exe")' not in spec, (
        "spec çıktı yolunu --distpath yerine sabit dist/ ile yazıyor"
    )
