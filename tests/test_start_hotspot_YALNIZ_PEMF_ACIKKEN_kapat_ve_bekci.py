# Author: mertaygn, cglrgrkn
"""start_hotspot.ps1 — hotspot YALNIZ PEMF açıkken (sahip 2026-11-04).

ARIZA (sahip makinesinde gözlendi): PEMF kapatılınca PEMF-Gateway hotspot'u KAPANMIYORDU. `PEMF-Hotspot` görevi (logon + her
3 dk) betiği PEMF'in çalışıp çalışmadığına BAKMADAN koşturuyordu → elle kapatılan hotspot bile 3 dk içinde geri geliyordu ve
kapatan hiçbir yol yoktu. Düzeltme: görev `-BekciKipi` ile çağırır (backend yoksa DOKUNMAZ), başlatıcı backend'i durdurduktan
sonra `-Kapat` çağırır (yalnız PEMF'in SSID'siyle açık hotspot, hiçbir PEMF backend'i kalmamışsa).

Betik pwsh altında KOŞTURULUR (metin aranmaz); `Get-Process`, `Get-NetIPAddress`, `Add-Type`, `netsh` GÖLGELENİR ve her çağrı
kayda yazılır → gerçek hotspot / ağ / WinRT'ye ASLA ulaşılmaz (bozuk bir kapı bile yalnız gölgeye çarpar). Günlük ve
`hotspot.json` tmp altında (`LOCALAPPDATA` / `ProgramData` yönlendirilir).
"""

from __future__ import annotations

import os
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
    (PWSH is None) and not capraz.ZORUNLU, reason="pwsh (PowerShell 7) yok — PS betiği koşturulamaz"
)


def _ps_lit(s: str | Path) -> str:
    return "'" + str(s).replace("'", "''") + "'"


def _pwsh(tmp_path: Path, ad: str, govde: str, env: dict | None = None) -> subprocess.CompletedProcess:
    p = tmp_path / ad
    p.write_text(govde, encoding="utf-8-sig", newline="\n")
    return subprocess.run(
        [PWSH, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(p)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=120,
    )


def _fonksiyon(tmp_path: Path, ad: str) -> str:
    """Fonksiyonu PowerShell'in KENDİ parser'ıyla betikten çıkarır (yeniden yazılmış kopya değil)."""
    out = tmp_path / f"{ad}.txt"
    govde = f"""
$tokens = $null; $errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile({_ps_lit(PS1)}, [ref]$tokens, [ref]$errors)
if ($errors.Count) {{ Write-Output ("PARSE-ERROR: " + (($errors | ForEach-Object {{ $_.Message }}) -join ' | ')); exit 3 }}
$f = $ast.Find({{ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq {_ps_lit(ad)} }}, $true)
if (-not $f) {{ Write-Output "NOT-FOUND"; exit 4 }}
[System.IO.File]::WriteAllText({_ps_lit(out)}, $f.Extent.Text, [System.Text.UTF8Encoding]::new($false))
Write-Output ("PARAMS=" + (($ast.ParamBlock.Parameters | ForEach-Object {{ $_.Name.VariablePath.UserPath }}) -join ','))
Write-Output "OK"
"""
    r = _pwsh(tmp_path, f"cikar_{ad}.ps1", govde)
    assert r.returncode == 0 and "OK" in r.stdout, (
        f"'{ad}' parser ile bulunamadı (rc={r.returncode})\n{r.stdout}\n{r.stderr}"
    )
    m = re.search(r"PARAMS=(.*)", r.stdout)
    parametreler = m.group(1).split(",") if m else []
    assert "BekciKipi" in parametreler and "Kapat" in parametreler, (
        f"-BekciKipi / -Kapat param bloğunda yok: {r.stdout}"
    )
    return out.read_text(encoding="utf-8")


def _betigi_kos(tmp_path: Path, anahtar: str, *, backend_var: bool, adresler: str = "") -> tuple[int, str, list[str]]:
    """Betiğin TAMAMINI `anahtar` ile koşturur; dönüş (çıkış kodu, günlük, gölgelenen çağrıların kaydı)."""
    yerel, pd = tmp_path / "LocalAppData", tmp_path / "ProgramData"
    yerel.mkdir(exist_ok=True)
    pd.mkdir(exist_ok=True)
    kayit = tmp_path / "cagrilar.txt"
    kayit.write_text("", encoding="utf-8")
    surec = "[pscustomobject]@{ Name = 'PEMF_Backend'; Id = 4242 }" if backend_var else ""
    govde = f"""
$ErrorActionPreference = 'Continue'
$K = {_ps_lit(kayit)}
function global:Get-Process {{ [CmdletBinding()] param([Parameter(ValueFromRemainingArguments=$true)]$Rest) Add-Content -LiteralPath $K -Value 'Get-Process'; @({surec}) }}
function global:Get-NetIPAddress {{ [CmdletBinding()] param([Parameter(ValueFromRemainingArguments=$true)]$Rest) Add-Content -LiteralPath $K -Value 'Get-NetIPAddress'; @({adresler}) }}
function global:Add-Type {{ [CmdletBinding()] param([Parameter(ValueFromRemainingArguments=$true)]$Rest) Add-Content -LiteralPath $K -Value 'Add-Type'; throw 'GOLGE: WinRT yuklenmez' }}
function global:netsh {{ Add-Content -LiteralPath $K -Value ('netsh ' + ($args -join ' ')); 'GOLGE netsh' }}
foreach ($ad in 'Get-Process', 'Get-NetIPAddress', 'Add-Type', 'netsh') {{
  if ((Get-Command $ad).CommandType -ne 'Function') {{ Write-Output "GOLGE DEVREDE DEGIL: $ad"; exit 99 }}
}}
& {_ps_lit(PS1)} {anahtar}
exit $LASTEXITCODE
"""
    env = {**os.environ, "LOCALAPPDATA": str(yerel), "ProgramData": str(pd)}
    env.pop("PEMF_HOTSPOT_SSID", None)
    env.pop("PEMF_HOTSPOT_PASS", None)
    r = _pwsh(tmp_path, "kos.ps1", govde, env)
    assert "GOLGE DEVREDE DEGIL" not in r.stdout, f"gölge devrede değil — betik KOŞTURULMADI: {r.stdout}"
    gunluk = yerel / "PEMF_System" / "hotspot.log"
    metin = gunluk.read_text(encoding="utf-8-sig") if gunluk.exists() else ""
    return r.returncode, metin, [s for s in kayit.read_text(encoding="utf-8").splitlines() if s.strip()]


def test_KRITIK_bekci_kipi_PEMF_KAPALIYKEN_hotspota_DOKUNMAZ(tmp_path):
    """Asıl arıza: PEMF kapalıyken görev hotspot'u yeniden açıyordu. Bekçi kipi ağa / WinRT'ye / netsh'e HİÇ ulaşmadan çıkar."""
    rc, gunluk, cagrilar = _betigi_kos(tmp_path, "-BekciKipi", backend_var=False)
    assert rc == 0, f"bekçi kipi sıfırdan farklı çıktı ({rc})"
    assert "Bekci: PEMF backend calismiyor" in gunluk, f"atlama günlüğe yazılmadı:\n{gunluk}"
    yasak = [c for c in cagrilar if c != "Get-Process"]
    assert not yasak, f"PEMF kapalıyken hotspot yoluna girildi: {yasak}"
    assert "Get-Process" in cagrilar, "backend varlığı hiç sorulmadı (kapı kör)"


def test_KARSIT_bekci_kipi_PEMF_ACIKKEN_eskisi_gibi_ACIK_TUTAR(tmp_path):
    """Backend çalışıyorsa bekçi kipi bugünkü yola devam eder (burada hotspot zaten bizde → 'atlandı', WinRT'ye inmez)."""
    sahip = "[pscustomobject]@{ IPAddress = '192.168.137.1'; PrefixOrigin = 'Manual'; InterfaceAlias = 'Local Area Connection* 12' }"
    rc, gunluk, cagrilar = _betigi_kos(tmp_path, "-BekciKipi", backend_var=True, adresler=sahip)
    assert rc == 0
    assert "Bekci: PEMF backend calismiyor" not in gunluk
    assert "Hotspot zaten aktif" in gunluk, f"backend açıkken bekçi kipi açık tutma yoluna girmedi:\n{gunluk}"
    assert "Get-NetIPAddress" in cagrilar and "Add-Type" not in cagrilar, cagrilar


def test_KARSIT_kipsiz_cagri_backend_KAPALIYKEN_de_ACAR(tmp_path):
    """Backend'in kendi açılış çağrısı (kipsiz) değişmedi: backend süreci adı ne olursa olsun açma yoluna girer."""
    rc, gunluk, cagrilar = _betigi_kos(tmp_path, "", backend_var=False)
    assert rc == 0
    assert "Bekci:" not in gunluk and "Kapat:" not in gunluk
    assert "Add-Type" in cagrilar, f"kipsiz çağrı açma yoluna (WinRT) girmedi: {cagrilar}"


def test_KRITIK_Kapat_baska_PEMF_backendi_CALISIRKEN_hotspotu_BIRAKIR(tmp_path):
    rc, gunluk, cagrilar = _betigi_kos(tmp_path, "-Kapat", backend_var=True)
    assert rc == 0
    assert "Kapat: PEMF backend hala calisiyor" in gunluk, gunluk
    assert "Add-Type" not in cagrilar and not any(c.startswith("netsh") for c in cagrilar), cagrilar


def test_Kapat_WinRT_yoksa_netsh_ile_KAPATIR_ACMAZ(tmp_path):
    """WinRT yüklenemezse (gölge atar) açılışın netsh yedeğiyle açılmış olabilecek ağ KAPATILIR — asla `start` / `set` değil."""
    rc, gunluk, cagrilar = _betigi_kos(tmp_path, "-Kapat", backend_var=False)
    assert rc == 0
    netsh = [c for c in cagrilar if c.startswith("netsh")]
    assert netsh == ["netsh wlan stop hostednetwork"], f"Kapat kipi netsh'te başka komut koşturdu: {netsh}"
    assert "Kapat: Mobile Hotspot API hatasi" in gunluk and "Kapat: netsh hostednetwork" in gunluk, gunluk
    assert "Get-NetIPAddress" not in cagrilar, "Kapat kipi açma yolunun durum tespitine girdi"


def _durdur(tmp_path: Path, durum: str, ssid: str, sonuc: str = "Success") -> tuple[str, int]:
    func = _fonksiyon(tmp_path, "Stop-PemfHotspot")
    govde = f"""
$ErrorActionPreference = 'Continue'
$script:durdurma = 0
$y = [pscustomobject]@{{ TetheringOperationalState = {_ps_lit(durum)} }}
$y | Add-Member -MemberType ScriptMethod -Name GetCurrentAccessPointConfiguration -Value {{ [pscustomobject]@{{ Ssid = {_ps_lit(ssid)} }} }}
$y | Add-Member -MemberType ScriptMethod -Name StopTetheringAsync -Value {{ $script:durdurma++; 'SAHTE-GOREV' }}
$bekle = {{ param($t) if ($t -ne 'SAHTE-GOREV') {{ throw "beklenen gorev degil: $t" }}; [pscustomobject]@{{ Status = {_ps_lit(sonuc)}; AdditionalErrorMessage = 'sahte' }} }}
{func}
$s = Stop-PemfHotspot $y 'PEMF-Gateway' $bekle
Write-Output ("SONUC=" + $s)
Write-Output ("DURDURMA=" + $script:durdurma)
"""
    r = _pwsh(tmp_path, "durdur.ps1", govde)
    assert r.returncode == 0, f"pwsh düştü (rc={r.returncode})\n{r.stdout}\n{r.stderr}"
    m, n = re.search(r"SONUC=(.*)", r.stdout), re.search(r"DURDURMA=(\d+)", r.stdout)
    assert m and n, f"çıktı yok:\n{r.stdout}\n{r.stderr}"
    return m.group(1).strip(), int(n.group(1))


def test_KRITIK_Stop_YALNIZ_PEMF_SSIDsiyle_ACIK_hotspotu_kapatir(tmp_path):
    s, n = _durdur(tmp_path, "On", "PEMF-Gateway")
    assert n == 1 and s.startswith("kapatildi"), (s, n)


def test_KARSIT_Stop_kullanicinin_BASKA_SSIDli_hotspotuna_DOKUNMAZ(tmp_path):
    s, n = _durdur(tmp_path, "On", "Mert-Telefon-Paylasim")
    assert n == 0 and "baska SSID" in s, (s, n)


def test_Stop_zaten_kapaliysa_cagirmaz_basarisizlik_DURUMUNU_soyler(tmp_path):
    s, n = _durdur(tmp_path, "Off", "PEMF-Gateway")
    assert n == 0 and s == "zaten kapali", (s, n)
    s, n = _durdur(tmp_path, "On", "PEMF-Gateway", sonuc="OperationInProgress")
    assert n == 1 and s.startswith("kapatilamadi: OperationInProgress"), (s, n)


def test_Test_PemfBackendCalisiyor_PEMF_Backend_surecini_sorar(tmp_path):
    func = _fonksiyon(tmp_path, "Test-PemfBackendCalisiyor")
    govde = f"""
$script:sorulan = @()
function Get-Process {{ param($Name, $ErrorAction) $script:sorulan += $Name; if ($script:var -and $Name -eq 'PEMF_Backend') {{ [pscustomobject]@{{ Name = $Name }} }} }}
{func}
$script:var = $false; Write-Output ("YOK=" + (Test-PemfBackendCalisiyor))
$script:var = $true;  Write-Output ("VAR=" + (Test-PemfBackendCalisiyor))
Write-Output ("AD=" + (($script:sorulan | Select-Object -Unique) -join ','))
"""
    r = _pwsh(tmp_path, "surec.ps1", govde)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "YOK=False" in r.stdout and "VAR=True" in r.stdout, (
        f"PEMF_Backend süreci varken 'çalışıyor' denmedi: {r.stdout}"
    )
    assert re.search(r"^AD=PEMF_Backend\s*$", r.stdout, re.M), f"backend süreç adı tam 'PEMF_Backend' değil: {r.stdout}"
