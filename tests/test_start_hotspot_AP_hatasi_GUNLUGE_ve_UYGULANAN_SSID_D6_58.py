# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D6.58 (B-10.204) — `start_hotspot.ps1` AP yapılandırma hatası GÜNLÜĞE düşer; başarı günlüğü UYGULANAN SSID ve bandı yazar.

Kusur: `ConfigureAccessPointAsync` (ya da `GetCurrentAccessPointConfiguration`) hata verince `} catch {}` hatayı yutuyordu; hotspot
Windows'taki ESKİ SSID / bantla (ör. 5 GHz) açılıyor, `hotspot.log` yine "Hotspot AKTİF: PEMF-Gateway (2.4GHz)" — İSTENEN değeri —
yazıyordu. ESP bobini bağlanamıyor, tanı dosyası bunu GİZLİYORDU.

⛔ Betik GERÇEKTEN koşmaz (Y2: saha makinesinde koşturulmaz; gerçek `netsh` / Windows.Networking API YOK). Aparat betiğin KENDİ
parçalarını PowerShell parser'ıyla çeker — `Get-PemfUygulananAp` tanımı (varsa) ve AP yapılandırma `try`ından başlayıp aynı bloktaki
tethering başlatma deyimine dek GERÇEK deyimler — ve pwsh altında SAHTE tethering yöneticisiyle koşturur: modül otomatik yükleme
KAPALI, `netsh` / `Start-Sleep` gölge işlev (`Get-Command` kanıtı), WinRT türleri `Add-Type` ile süreç içi gölge.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import capraz
import pytest

REPO = Path(__file__).resolve().parent.parent
PS1 = REPO / "scripts" / "start_hotspot.ps1"
PWSH = shutil.which("pwsh")
pytestmark = pytest.mark.skipif(
    (PWSH is None) and not capraz.ZORUNLU, reason="pwsh (PowerShell 7) yok — PS parçaları koşturulamaz"
)

ISTENEN_SSID = "PEMF-Gateway"
ESKI_SSID = "EskiKlinikAgi"
HATA_IMZASI = "E_ACCESSDENIED (D6.58 aparat)"


def _pwsh_file(tmp_path: Path, name: str, body: str) -> subprocess.CompletedProcess:
    p = tmp_path / name
    p.write_text(body, encoding="utf-8-sig", newline="\n")
    return subprocess.run(
        [PWSH, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(p)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )


def _ps_lit(s: str | Path) -> str:
    return "'" + str(s).replace("'", "''") + "'"


def _betik_parcalari(tmp_path: Path) -> tuple[str, str]:
    """(Get-PemfUygulananAp tanımı ya da '', AP yapılandırma try'ından itibaren aynı bloktaki deyimler) — PARSER ile."""
    fonk = tmp_path / "fonk.txt"
    parca = tmp_path / "parca.txt"
    body = f"""
$tokens = $null; $errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile({_ps_lit(PS1)}, [ref]$tokens, [ref]$errors)
if ($errors.Count) {{ Write-Output ("PARSE-ERROR: " + (($errors | ForEach-Object {{ $_.Message }}) -join ' | ')); exit 3 }}
$f = @($ast.FindAll({{ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq 'Get-PemfUygulananAp' }}, $true))
[System.IO.File]::WriteAllText({_ps_lit(fonk)}, (($f | ForEach-Object {{ $_.Extent.Text }}) -join "`n"), [System.Text.UTF8Encoding]::new($false))
$d = @($ast.FindAll({{ param($n) $n -is [System.Management.Automation.Language.TryStatementAst] -and
    $n.Body.Extent.Text -match 'ConfigureAccessPointAsync' -and $n.Body.Extent.Text -notmatch 'CreateFromConnectionProfile' }}, $true))
if ($d.Count -ne 1) {{ Write-Output ("AP-TRY-SAYISI=" + $d.Count); exit 4 }}
$blok = @($d[0].Parent.Statements)
$i = [array]::IndexOf($blok, $d[0])
if ($i -lt 0) {{ Write-Output "AP-TRY-BLOKTA-YOK"; exit 5 }}
[System.IO.File]::WriteAllText({_ps_lit(parca)}, (($blok[$i..($blok.Count - 1)] | ForEach-Object {{ $_.Extent.Text }}) -join "`n"), [System.Text.UTF8Encoding]::new($false))
Write-Output "OK"
"""
    r = _pwsh_file(tmp_path, "parcala.ps1", body)
    assert r.returncode == 0 and "OK" in r.stdout, (
        f"start_hotspot.ps1'de AP yapılandırma try'ı (ConfigureAccessPointAsync) parser ile bulunamadı (rc={r.returncode})\n"
        f"{r.stdout}\n{r.stderr}"
    )
    metin = parca.read_text(encoding="utf-8")
    assert "StartTetheringAsync" in metin and "TetheringOperationalState" in metin, (
        f"AP yapılandırma try'ından sonra aynı blokta tethering başlatma deyimi yok — aparat başarı günlüğünü ölçemez:\n{metin}"
    )
    return fonk.read_text(encoding="utf-8"), metin


def _kos(tmp_path: Path, *, isletim: str, yapilandirma_hatasi: bool) -> list[str]:
    """Sahte yönetici: Windows'taki AP = (ESKI_SSID, 5 GHz). Yapılandırma ya HATA fırlatır ya uygular. → günlük satırları."""
    fonk, parca = _betik_parcalari(tmp_path)
    log = tmp_path / "hotspot.log"
    log.write_text("", encoding="utf-8")
    yapilandir = (
        f"throw {_ps_lit(HATA_IMZASI)}"
        if yapilandirma_hatasi
        else "$global:D658Ap = [pscustomobject]@{ Ssid = $c.Ssid; Passphrase = $c.Passphrase; Band = $c.Band }; 'gorev'"
    )
    body = f"""
Import-Module Microsoft.PowerShell.Management, Microsoft.PowerShell.Utility
$PSModuleAutoLoadingPreference = 'None'
$ErrorActionPreference = 'Continue'   # start_hotspot.ps1 ile AYNI
# WinRT türleri pwsh 7'de YOK → süreç içi GÖLGE (yalnız tür adı; hiçbir Windows API'si yok).
Add-Type -TypeDefinition @'
namespace Windows.Networking.NetworkOperators {{
    public enum TetheringWiFiBand {{ Auto = 0, TwoPointFourGigahertz = 1, FiveGigahertz = 2 }}
    public sealed class NetworkOperatorTetheringOperationResult {{ }}
}}
'@
function netsh {{ throw 'D6.58 aparat: netsh CAGRILMAMALI' }}
function Start-Sleep {{ param([Parameter(ValueFromRemainingArguments=$true)]$Rest) }}
Write-Output ("KOMUT netsh=" + (Get-Command netsh).CommandType + " Start-Sleep=" + (Get-Command Start-Sleep).CommandType)
$Ssid = {_ps_lit(ISTENEN_SSID)}; $Pass = 'pemf1234'
function Log([string]$m) {{ Add-Content -LiteralPath {_ps_lit(log)} -Value $m -Encoding UTF8 }}
function AwaitAction($t) {{ }}
function AwaitResult($t, $rt) {{ [pscustomobject]@{{ Status = 'Success'; AdditionalErrorMessage = '' }} }}
$global:D658Ap = [pscustomobject]@{{ Ssid = {_ps_lit(ESKI_SSID)}; Passphrase = 'eski-parola'; Band = [Windows.Networking.NetworkOperators.TetheringWiFiBand]::FiveGigahertz }}
$mgr = [pscustomobject]@{{ TetheringOperationalState = {_ps_lit(isletim)} }}
$mgr | Add-Member -MemberType ScriptMethod -Name GetCurrentAccessPointConfiguration -Value {{
    [pscustomobject]@{{ Ssid = $global:D658Ap.Ssid; Passphrase = $global:D658Ap.Passphrase; Band = $global:D658Ap.Band }} }}
$mgr | Add-Member -MemberType ScriptMethod -Name ConfigureAccessPointAsync -Value {{ param($c) {yapilandir} }}
$mgr | Add-Member -MemberType ScriptMethod -Name StartTetheringAsync -Value {{ 'gorev' }}
# ── betikten PARSER ile çekilen GERÇEK parçalar ──
{fonk}
{parca}
Write-Output "BITTI"
"""
    r = _pwsh_file(tmp_path, "kos.ps1", body)
    assert r.returncode == 0 and "BITTI" in r.stdout, f"aparat düştü (rc={r.returncode}):\n{r.stdout}\n{r.stderr}"
    assert "KOMUT netsh=Function Start-Sleep=Function" in r.stdout, f"gölge işlevler etkin değil:\n{r.stdout}"
    return [s for s in log.read_text(encoding="utf-8-sig").splitlines() if s.strip()]


def _satir(satirlar: list[str], onek: str) -> str:
    bulunan = [s for s in satirlar if s.startswith(onek)]
    assert len(bulunan) == 1, (
        f"'{onek}' ile başlayan TEK günlük satırı bekleniyordu, bulunan {len(bulunan)}:\n" + "\n".join(satirlar)
    )
    return bulunan[0]


def test_KRITIK_AP_yapilandirma_HATASI_gunluge_duser_ve_AKTIF_satiri_UYGULANAN_SSIDi_yazar_D6_58(tmp_path):
    satirlar = _kos(tmp_path, isletim="Off", yapilandirma_hatasi=True)
    hata = [s for s in satirlar if "UYARI" in s and HATA_IMZASI in s]
    assert hata, (
        "AP yapılandırma hatası (ConfigureAccessPointAsync fırlattı) hotspot.log'a DÜŞMEDİ — boş catch geri geldi; hotspot eski "
        "SSID / bantla açılır ve tanı dosyası bunu gizler. catch gövdesinde Log \"UYARI: … ($_) …\" olmalı.\n"
        + "\n".join(satirlar)
    )
    aktif = _satir(satirlar, "Hotspot AKTİF")
    assert ISTENEN_SSID not in aktif and "2.4GHz" not in aktif, (
        f"başarı günlüğü İSTENEN SSID / bandı uygulanmış gibi yazıyor (yapılandırma BAŞARISIZDI): {aktif!r}"
    )
    assert ESKI_SSID in aktif and "FiveGigahertz" in aktif, (
        f"başarı günlüğü Windows'un UYGULADIĞI SSID ({ESKI_SSID}) ve bandı (FiveGigahertz) söylemiyor: {aktif!r}"
    )


def test_KRITIK_zaten_ACIK_hotspotta_da_UYGULANAN_SSID_yazilir_D6_58(tmp_path):
    satirlar = _kos(tmp_path, isletim="On", yapilandirma_hatasi=True)
    assert any("UYARI" in s and HATA_IMZASI in s for s in satirlar), (
        "zaten açık dalda yapılandırma hatası günlüğe düşmedi:\n" + "\n".join(satirlar)
    )
    acik = _satir(satirlar, "Hotspot zaten On")
    assert ISTENEN_SSID not in acik and ESKI_SSID in acik and "FiveGigahertz" in acik, (
        f"'zaten On' günlüğü İSTENEN SSID'i yazıyor ya da uygulananı söylemiyor: {acik!r}"
    )


def test_KARSIT_yapilandirma_BASARILI_ise_UYARI_yok_ve_uygulanan_istenenle_AYNI_D6_58(tmp_path):
    satirlar = _kos(tmp_path, isletim="Off", yapilandirma_hatasi=False)
    assert not [s for s in satirlar if s.startswith("UYARI")], "yapılandırma başarılıyken sahte UYARI:\n" + "\n".join(
        satirlar
    )
    assert any(s.startswith("AP yapilandirmasi guncellendi") for s in satirlar), "\n".join(satirlar)
    aktif = _satir(satirlar, "Hotspot AKTİF")
    assert re.search(rf"SSID={re.escape(ISTENEN_SSID)}\b", aktif) and "TwoPointFourGigahertz" in aktif, (
        f"yapılandırma uygulandığı hâlde başarı günlüğü uygulanan SSID / bandı (PEMF-Gateway, 2.4 GHz) yazmıyor: {aktif!r}"
    )
