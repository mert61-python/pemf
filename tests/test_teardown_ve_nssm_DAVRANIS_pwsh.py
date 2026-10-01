# Author: mertaygn, cglrgrkn
"""D1.44 · B-10.24 · B-10.68 + D1.45 · B-10.25 · B-10.28 — kurulum/kaldırma betikleri pwsh'ta DAVRANIŞLA.

D1.44 (`scripts/setup_services.ps1` env + NSSM bloğu): kapılar metin aramasıydı — `PEMF_ALLOWED_HOSTS`
ayrıştırmadan düşse (servis `*` host ile açılır), ayrıştırıcı `Contains('==')` olsa (servis PEMF_DATA_DIR /
ENCRYPT_AT_REST olmadan açılır), ikinci bir `AppStopMethodConsole 1500` satırı eklense (NSSM graceful bobin
STOP'undan önce öldürür; mevcut kapı İLK eşleşmeye bakıyordu) YEŞİL kalıyordu. Bu kapı bloğu (yalnız o
ifadeler, AST'den) sahte `nssm` ile KOŞTURUR ve kaydedilen argümanları ölçer.

D1.45 (`scripts/pemf_teardown.ps1`): KVKK varsayılan koruma filtresi, servis durdurma sırası (broker EN SON)
ve orkestratörün kasa silmelerini yalnız `-IncludePatientData` ile yapması — hepsi yorum/metin kapısındaydı.

⛔ GÜVENLİK (görev kuralı): gerçek betik DOT-SOURCE EDİLMEZ. Yalnız izin listesindeki fonksiyonlar AST'den
tek tek tanımlanır; kimlik fonksiyonları (`Remove-PemfCredentials`, `Remove-PemfSystemCredentials` — ikincisi
`schtasks`'ı TAM YOLLA çağırdığı için gölgelenemez) HİÇ yüklenmez, kayıtçıyla değiştirilir. `sc.exe`, `cmdkey`,
`schtasks`, `nssm`, `icacls`, `Remove-Item`, `Stop-Service`, `Stop-Process`, `Get-Process`, `Get-Service`,
`Start-Sleep` FONKSİYONLA gölgelenir; çağrıdan ÖNCE kanarya her adın `Function` olarak çözüldüğünü doğrular,
tutmazsa hiçbir şey çağrılmadan çıkılır (çıkış 3). Yalnız geçici köklerde sahte footprint. Yönetici yetkisi
kullanılmaz. Gerçek servis, güvenlik duvarı, görev zamanlayıcı ve kimlik kasası DEĞİŞMEZ (oturum, her koşudan
önce/sonra `cmdkey` PEMF sayısını, servis ve kural sayılarını ölçer).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
TEARDOWN = KOK / "scripts" / "pemf_teardown.ps1"
SETUP = KOK / "scripts" / "setup_services.ps1"
DEVICE_ENV = KOK / "deploy" / "device.env"
_PWSH = shutil.which("pwsh")

pytestmark = [
    pytest.mark.skipif(sys.platform != "win32", reason="pwsh aparatı Windows betik anlamını ölçer"),
    pytest.mark.skipif(_PWSH is None, reason="pwsh (PowerShell 7) bulunamadı"),
]

_APARAT = r"""
param([string]$Teardown, [string]$Setup, [string]$Kok, [string]$Senaryo, [string]$Cikti)
$ErrorActionPreference = 'Stop'
$script:Kayit = [System.Collections.Generic.List[string]]::new()
function K([string]$s) { $script:Kayit.Add($s) }

# ── 1) GÖLGELER: önce tanımlanır; komut çözümlemesi fonksiyonu uygulamadan ÖNCE bulur ──
function sc.exe { K ("sc " + ($args -join ' ')); if ($args[0] -eq 'stop') { $script:Servis[$args[1]] = 'Stopped' } elseif ($args[0] -eq 'delete') { $script:Servis.Remove($args[1]) }; $global:LASTEXITCODE = 0 }
function sc { sc.exe @args }
function cmdkey { K ("cmdkey " + ($args -join ' ')); $global:LASTEXITCODE = 0 }
function cmdkey.exe { cmdkey @args }
function schtasks { K ("schtasks " + ($args -join ' ')); $global:LASTEXITCODE = 0 }
function schtasks.exe { schtasks @args }
function nssm { K ("nssm " + ($args -join ' ')); $global:LASTEXITCODE = 0 }
function nssm.exe { nssm @args }
function icacls { K ("icacls " + ($args -join ' ')); $global:LASTEXITCODE = 0 }
function icacls.exe { icacls @args }
function Stop-Service { [CmdletBinding()] param([Parameter(ValueFromRemainingArguments = $true)]$R) K ("Stop-Service " + ($R -join ' ')) }
function Remove-Item { [CmdletBinding()] param([string]$LiteralPath, [string]$Path, [switch]$Recurse, [switch]$Force) K ("Remove-Item " + $LiteralPath + $Path) }
function Stop-Process { [CmdletBinding()] param([Parameter(ValueFromPipeline = $true)]$InputObject, $Id, [switch]$Force) K "Stop-Process" }
function Get-Process { [CmdletBinding()] param([Parameter(ValueFromRemainingArguments = $true)]$R) @() }
function Start-Sleep { [CmdletBinding()] param([Parameter(ValueFromRemainingArguments = $true)]$R) }
$script:Servis = @{}
function Get-Service { [CmdletBinding()] param([string]$Name) if ($script:Servis.ContainsKey($Name)) { [pscustomobject]@{ Name = $Name; Status = $script:Servis[$Name] } } }
$golgeler = 'sc.exe','sc','cmdkey','cmdkey.exe','schtasks','schtasks.exe','nssm','nssm.exe','icacls','icacls.exe','Stop-Service','Remove-Item','Stop-Process','Get-Process','Start-Sleep','Get-Service'
foreach ($ad in $golgeler) {
    $c = Get-Command $ad -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $c -or $c.CommandType -ne 'Function') { [Console]::Out.WriteLine("APARAT_HATASI golgelenemedi: $ad"); exit 3 }
}
& sc.exe query KANARYA; & cmdkey /list:KANARYA
if ($script:Kayit.Count -ne 2) { [Console]::Out.WriteLine("APARAT_HATASI kanarya kaydedilmedi"); exit 3 }
$script:Kayit.Clear()

# ── 2) GERÇEK fonksiyonlar YALNIZ izin listesinden, AST'den (dosya dot-source EDİLMEZ) ──
function Yukle([string]$Dosya, [string[]]$Adlar) {
    $t = $null; $e = $null
    $ast = [System.Management.Automation.Language.Parser]::ParseFile($Dosya, [ref]$t, [ref]$e)
    if ($e) { throw "parse hatasi: $Dosya" }
    foreach ($ad in $Adlar) {
        $f = $ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq $ad }, $true) | Select-Object -First 1
        if (-not $f) { throw "fonksiyon yok: $ad" }
        . ([ScriptBlock]::Create($f.Extent.Text))
    }
}
# 3) KAYITÇILAR (gerçekleri ASLA yüklenmez) + sahte footprint/profil kökü
function Write-PemfLog($msg, $color = 'Gray') { K ("LOG " + $msg) }
function Remove-PemfCredentials { param([string[]]$TargetNames, [switch]$DryRun) K ("KIMLIK_KULLANICI dry=" + [bool]$DryRun + " n=" + @($TargetNames).Count) }
function Remove-PemfSystemCredentials { param([string[]]$TargetNames, [switch]$DryRun) K ("KIMLIK_SYSTEM dry=" + [bool]$DryRun + " n=" + @($TargetNames).Count) }
function Remove-PemfTasks { param($Tasks, [switch]$DryRun) K "GOREV" }
function Remove-PemfFirewall { param($Rx, [switch]$DryRun) K "FIREWALL" }
function Remove-PemfEnv { param($Rx, [switch]$DryRun) K "ENV" }
function Remove-PemfRegistry { param($Registry, $Scope, [switch]$DryRun) K "REGISTRY" }
function Get-PemfProfileRoots { @(Join-Path $Kok 'profil') }

$sonuc = [ordered]@{ senaryo = $Senaryo }
switch -Wildcard ($Senaryo) {
    'yollar*' {
        . Yukle $Teardown @('Test-PemfScope', 'Assert-PemfRemoved', 'Remove-PemfPaths')
        $kvkk = Join-Path $Kok 'hasta_verisi'; $normal = Join-Path $Kok 'gecici_veri'
        New-Item -ItemType Directory -Force $kvkk, $normal | Out-Null
        $fp = [pscustomobject]@{ Paths = @(
            [pscustomobject]@{ Kind = 'Abs'; Path = $kvkk; Kvkk = $true; Owner = 'backend' },
            [pscustomobject]@{ Kind = 'Abs'; Path = $normal; Kvkk = $false; Owner = 'backend' }) }
        $script:PemfFailed = @()
        if ($Senaryo -eq 'yollar_hasta_dahil') { Remove-PemfPaths -Footprint $fp -Scope backend -IncludePatientData }
        else { Remove-PemfPaths -Footprint $fp -Scope backend }
        $sonuc.kvkk = $kvkk; $sonuc.normal = $normal
    }
    'servis_sirasi' {
        . Yukle $Teardown @('Stop-PemfProcessesAndServices')
        $script:Servis['mosquitto'] = 'Running'; $script:Servis['PemfBackend'] = 'Running'
        $script:PemfFailed = @()
        Stop-PemfProcessesAndServices -Services @('mosquitto', 'PemfBackend')
    }
    'orkestrator*' {
        . Yukle $Teardown @('Test-PemfScope', 'Assert-PemfRemoved', 'Remove-PemfPaths', 'Invoke-PemfTeardown')
        function Get-PemfFootprint { [pscustomobject]@{ Services = @(); Tasks = @(); FirewallRx = 'YOK'; EnvRx = 'YOK'; Registry = @(); Paths = @(); Credentials = @('PEMF_SAHTE@PEMF_GUI') } }
        if ($Senaryo -eq 'orkestrator_dry_hasta') { [void](Invoke-PemfTeardown -Scope backend -DryRun -IncludePatientData) }
        else { [void](Invoke-PemfTeardown -Scope backend -DryRun) }
    }
    'nssm_blogu' {
        $t = $null; $e = $null
        $ast = [System.Management.Automation.Language.Parser]::ParseFile($Setup, [ref]$t, [ref]$e)
        if ($e) { throw "parse hatasi: $Setup" }
        $ifadeler = @($ast.EndBlock.Statements)
        $bas = -1; $son = -1
        for ($i = 0; $i -lt $ifadeler.Count; $i++) {
            $x = $ifadeler[$i].Extent.Text
            if ($bas -lt 0 -and $x -match '^&\s*\$NssmExe\s+set\s+\$ServiceBackend\s+AppDirectory\b') { $bas = $i }
            if ($x -match '^&\s*\$NssmExe\s+set\s+\$ServiceBackend\s+AppEnvironmentExtra\b') { $son = $i }
        }
        if ($bas -lt 0 -or $son -lt $bas) { throw "nssm blogu bulunamadi ($bas, $son)" }
        $metin = ($ifadeler[$bas..$son] | ForEach-Object { $_.Extent.Text }) -join "`n"
        New-Item -ItemType Directory -Force (Join-Path $Kok 'scripts'), (Join-Path $Kok 'deploy'), (Join-Path $Kok 'app') | Out-Null
        Copy-Item (Join-Path (Split-Path -Parent (Split-Path -Parent $Setup)) 'deploy\device.env') (Join-Path $Kok 'deploy\device.env')
        $blok = Join-Path $Kok 'scripts\nssm_blogu.ps1'
        Set-Content -LiteralPath $blok -Value $metin -Encoding UTF8
        $NssmExe = 'nssm'; $ServiceBackend = 'PemfBackend'; $AppDir = Join-Path $Kok 'app'; $LogDir = Join-Path $Kok 'log'; $Mode = 'device'
        function Log { param($m, $c) }
        . $blok
    }
}
$sonuc.kayit = @($script:Kayit)
$sonuc | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $Cikti -Encoding UTF8
exit 0
"""


def _kos(tmp_path: Path, senaryo: str) -> dict:
    aparat = tmp_path / "aparat.ps1"
    aparat.write_text(_APARAT, encoding="utf-8-sig")
    cikti = tmp_path / "cikti.json"
    kok = tmp_path / "kok"
    kok.mkdir()
    r = subprocess.run(
        [
            _PWSH,
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(aparat),
            "-Teardown",
            str(TEARDOWN),
            "-Setup",
            str(SETUP),
            "-Kok",
            str(kok),
            "-Senaryo",
            senaryo,
            "-Cikti",
            str(cikti),
        ],
        capture_output=True,
        timeout=120,
        cwd=str(tmp_path),
    )
    out = r.stdout.decode("utf-8", "replace") + r.stderr.decode("utf-8", "replace")
    assert "APARAT_HATASI" not in out, f"aparat güvenli değil — hiçbir şey çağrılmadı: {out[-600:]}"
    assert r.returncode == 0 and cikti.exists(), f"aparat koşmadı (rc={r.returncode}): {out[-1200:]}"
    return json.loads(cikti.read_text(encoding="utf-8-sig"))


def _yasakli(kayit: list[str]) -> list[str]:
    """Gerçek dünyaya dokunacak her komut gölgede kalmalı; kayıtta yalnız GÖLGE kayıtları olur."""
    return [k for k in kayit if k.startswith(("cmdkey", "schtasks", "icacls"))]


# ── D1.45 ───────────────────────────────────────────────────────────────────


def test_KRITIK_D145_varsayilan_kaldirma_HASTA_VERISINI_silmez(tmp_path):
    s = _kos(tmp_path, "yollar_varsayilan")
    silinen = [k[len("Remove-Item ") :] for k in s["kayit"] if k.startswith("Remove-Item ")]
    assert s["kvkk"] not in silinen, "VARSAYILAN kaldırma Kvkk=$true yolu SİLİYOR — hasta verisi/anahtar gider (KVKK)"
    assert s["normal"] in silinen, (
        f"aparat: KVKK-dışı yol bile silinmek istenmedi (Remove-PemfPaths koşmadı?): {s['kayit']}"
    )
    assert _yasakli(s["kayit"]) == []


def test_KARSIT_D145_IncludePatientData_ile_hasta_verisi_SILINIR(tmp_path):
    s = _kos(tmp_path, "yollar_hasta_dahil")
    silinen = [k[len("Remove-Item ") :] for k in s["kayit"] if k.startswith("Remove-Item ")]
    assert s["kvkk"] in silinen and s["normal"] in silinen, f"-IncludePatientData tam temizlik yapmadı: {silinen}"


def test_KRITIK_D145_servisler_SIRAYLA_broker_EN_SON_ve_kill_STOPLARDAN_sonra(tmp_path):
    s = _kos(tmp_path, "servis_sirasi")
    stoplar = [k.split()[2] for k in s["kayit"] if k.startswith("sc stop ")]
    assert stoplar == ["PemfBackend", "mosquitto"], (
        f"durdurma sırası {stoplar} — broker backend'den ÖNCE kapanırsa backend'in ESP STOP yayını broker'sız kalır"
    )
    son_stop = max(i for i, k in enumerate(s["kayit"]) if k.startswith("sc stop "))
    kill = [i for i, k in enumerate(s["kayit"]) if k == "Stop-Process"]
    assert not kill or min(kill) > son_stop, "force-kill graceful durdurmalardan ÖNCE"
    assert _yasakli(s["kayit"]) == []


@pytest.mark.parametrize(
    ("senaryo", "beklenen"),
    [
        ("orkestrator_dry", []),
        ("orkestrator_dry_hasta", ["KIMLIK_KULLANICI dry=True n=1", "KIMLIK_SYSTEM dry=True n=1"]),
    ],
)
def test_KRITIK_D145_orkestrator_kasa_silmesini_YALNIZ_IncludePatientData_ile_ve_DryRun_gecirerek_yapar(
    tmp_path, senaryo, beklenen
):
    s = _kos(tmp_path, senaryo)
    kimlik = [k for k in s["kayit"] if k.startswith("KIMLIK_")]
    assert kimlik == beklenen, (
        f"{senaryo}: kasa çağrıları {kimlik} (beklenen {beklenen}) — varsayılan kaldırmada anahtar silinirse "
        "korunan şifreli DB OKUNAMAZ; önizleme (-DryRun) kasaya dokunmamalı"
    )
    assert _yasakli(s["kayit"]) == []


# ── D1.44 ───────────────────────────────────────────────────────────────────


def _env_anahtarlari() -> set[str]:
    anahtar = set()
    for ln in DEVICE_ENV.read_text(encoding="utf-8").splitlines():
        t = ln.strip()
        if t and not t.startswith("#") and "=" in t:
            anahtar.add(t.split("=", 1)[0].strip())
    return anahtar


def test_KRITIK_D144_nssm_env_device_env_ve_temel_uclu_ve_SON_stop_butcesi(tmp_path):
    import backend_service as bs

    s = _kos(tmp_path, "nssm_blogu")
    env = [k for k in s["kayit"] if k.startswith("nssm set PemfBackend AppEnvironmentExtra ")]
    assert len(env) == 1, f"AppEnvironmentExtra {len(env)} kez yazıldı"
    yazilan = {p.split("=", 1)[0] for p in env[0].split()[4:]}
    beklenen = _env_anahtarlari() | {"PYTHONUNBUFFERED", "PEMF_HEADLESS", "PEMF_LOG_DIR"}
    assert {"PEMF_ALLOWED_HOSTS", "PEMF_DATA_DIR", "PEMF_ENCRYPT_AT_REST"} <= beklenen, (
        "ön koşul: device.env bu anahtarları taşımıyor"
    )
    assert yazilan == beklenen, (
        f"servise giden env anahtarları eksik/fazla: eksik={sorted(beklenen - yazilan)} fazla={sorted(yazilan - beklenen)}"
    )
    stop = [k for k in s["kayit"] if k.startswith("nssm set PemfBackend AppStopMethodConsole ")]
    assert stop, "AppStopMethodConsole hiç yazılmadı"
    son_ms = int(stop[-1].split()[-1])
    butce_ms = (bs._GRACEFUL_SHUTDOWN_TIMEOUT_S + bs._SAFE_STOP_BUDGET_S) * 1000
    assert son_ms > butce_ms, (
        f"SON AppStopMethodConsole {son_ms} ms ≤ backend kapanış bütçesi {butce_ms:.0f} ms — NSSM graceful bobin "
        "STOP'u bitmeden süreci SERT öldürür"
    )
