# -*- coding: utf-8 -*-
"""D4.28 (B-10.92 · B-10.135) — build AI hazırlık kapısının yanıtı KENDİ başlattığı EXE'ye bağlıdır; kapı zincirinin
koşulları DAVRANIŞLA ölçülür.

ARIZA 1 (B-10.92): kapı yalnız "portta HTTP 200 + rapor" bakıyordu — `PEMF_HEALTH_NONCE` vermiyor, `$proc.HasExited`
okumuyordu. Üretilen EXE açılır açılmaz ölse bile aynı portta yanıt veren BAŞKA bir backend'in (yetim, elle açılmış,
başka BuildRoot) tam-yeşil raporu build'i yeşil bitiriyor, ölü EXE "hazır" diye paketleniyordu. Launcher aynı sorunu
nonce ile çözmüştü (`apps/backend/servers/system_router.py` `launcherNonce`, yalnız loopback).
ARIZA 2 (B-10.135): kapıları tutan testler metne çapalıydı; `-ne 0`→`-lt 0` (pyz / sevk), eksik eşiği `-gt 999`,
`PYTHONHASHSEED` atamasını yoruma almak süiti YEŞİL bırakıyordu.

Ölçüm (gerçek EXE / ağ / port YOK):
  * AI kapısı bloğu ve betiğin SON bloğu PowerShell AYRIŞTIRICISIYLA alınıp GERÇEK metinleriyle koşar; betiğin KENDİ
    `Info / Warn / Die`'ı kullanılır (Die = `exit 1` → süreç çıkış kodu). `Start-Process` gölge: EXE başlatılmaz, o
    anda çocuğa geçecek `PEMF_HEALTH_NONCE` kaydedilir. `Invoke-RestMethod` gölge: senaryoya göre "kendi EXE'miz"
    (nonce'u yansıtır) ya da "portu tutan başka backend" (yansıtmaz) gibi yanıt verir.
  * Kapı çağrısı (`& $PY …kapisi.py`) + hemen ardından gelen `if` deyimi AST'den alınır ve `$PY` yerine çıkış kodunu
    sabitleyen bir işlevle koşar: 1, 2 ve Windows çökme kodu (0xC0000005 → -1073741819) Die etmeli, 0 etmemeli.
  * `PYTHONHASHSEED`: üst düzey, koşulsuz, TEK atama; koşturulunca "0"; PyInstaller çağrısından ÖNCE.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
BETIK = KOK / "scripts" / "build_backend_exe.ps1"
PWSH = shutil.which("pwsh")

pytestmark = pytest.mark.skipif(PWSH is None, reason="pwsh yok — build betiği pwsh ile koşar")

_ORTAM = {**os.environ, "POWERSHELL_TELEMETRY_OPTOUT": "1", "POWERSHELL_UPDATECHECK": "Off"}

_AI_SURUCU = r"""
param([string]$Betik, [string]$Kok, [string]$Senaryo, [string]$Iz)
$ErrorActionPreference = 'Stop'
# Türkçe iletiler konsol kod sayfasında bozulursa "basılmaz" iddiaları SAHTE-YEŞİL olur → UTF-8 sabit.
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$tokens = $null; $errs = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($Betik, [ref]$tokens, [ref]$errs)
if ($errs) { throw "build betiği ayrıştırılamadı: $($errs | Out-String)" }
$ust = $ast.EndBlock.Statements
$ai = $ust | Where-Object { $_ -is [System.Management.Automation.Language.IfStatementAst] -and $_.Clauses[0].Item1.Extent.Text -match 'SkipAiGate' } | Select-Object -First 1
$son = $ust[$ust.Count - 1]
if (-not $ai -or -not ($son.Extent.Text -match 'EXE hazır')) { throw "çıpa: AI kapısı ya da son 'EXE hazır' bloğu bulunamadı" }
foreach ($fn in $ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] }, $true)) {
    Invoke-Expression $fn.Extent.Text   # Info / Warn / Die GERÇEK (Die = exit 1)
}
$global:SENARYO = $Senaryo
$global:IZ = $Iz
New-Item -ItemType Directory -Force -Path $Iz | Out-Null
Set-Content -LiteralPath (Join-Path $Iz 'saglik_sayisi.txt') -Value '0'
function Start-Sleep { }
function Stop-Process { }
function Wait-Process { }
function Get-Process { @() }
function Start-Process {
    param($FilePath, $ArgumentList, $RedirectStandardOutput, $RedirectStandardError, [switch]$PassThru, $WindowStyle)
    # Çocuk ortamı başlatma ANINDA kopyalanır: EXE'nin göreceği nonce budur.
    $n = [Environment]::GetEnvironmentVariable('PEMF_HEALTH_NONCE', 'Process')
    Set-Content -LiteralPath (Join-Path $global:IZ 'cocuk_nonce.txt') -Value ([string]$n) -NoNewline
    $global:COCUK_NONCE = $n
    [pscustomobject]@{ Id = 0; HasExited = ($global:SENARYO -eq 'yabanci_oldu'); ExitCode = 3 }
}
function Invoke-RestMethod {
    param($Uri, $TimeoutSec, $Headers)
    if ($Uri -match '/api/health') {
        $s = [int](Get-Content -LiteralPath (Join-Path $global:IZ 'saglik_sayisi.txt')) + 1
        Set-Content -LiteralPath (Join-Path $global:IZ 'saglik_sayisi.txt') -Value "$s"
        switch ($global:SENARYO) {
            'yabanci_oldu'  { return [pscustomobject]@{ status = 'ok'; launcherNonce = $null } }
            'yabanci_canli' { return [pscustomobject]@{ status = 'ok'; launcherNonce = $null } }
            'yabanci_nonce' { return [pscustomobject]@{ status = 'ok'; launcherNonce = 'baska-bir-backendin-nonce-u' } }
            default         { return [pscustomobject]@{ status = 'ok'; launcherNonce = $global:COCUK_NONCE } }
        }
    }
    $eksik = @()
    $mod = @([pscustomobject]@{ modul = 'yara_kapanma'; hazir = $true; yukleme = 'pyd' })
    if ($global:SENARYO -eq 'eksik') {
        $eksik = @('yara_kapanma')
        $mod = @([pscustomobject]@{ modul = 'yara_kapanma'; hazir = $false; kod = $true; model = $false; sebep = 'sahte' })
    }
    return [pscustomobject]@{ hazir = 1 - $eksik.Count; toplam = 1; eksik = $eksik; moduller = $mod;
        xai = [pscustomobject]@{ hazir = $true; grad_cam = $true; shap = $true; captum = $true; ttach = $true; em_ref_stats_eksik = @() };
        pip_yasagi = [pscustomobject]@{ etkin = $true } }
}
$BuildRoot = $Kok
$dist = Join-Path $Kok 'dist'
$exe = Join-Path $dist 'PEMF_Backend\PEMF_Backend.exe'
New-Item -ItemType File -Force -Path $exe | Out-Null
$SkipAiGate = $false
$SkipProtect = $true
$dt = [timespan]::Zero
& ([scriptblock]::Create($ai.Extent.Text))
& ([scriptblock]::Create($son.Extent.Text))
Write-Host 'SURUCU-SONU'
exit 0
"""


def _pwsh(surucu: Path, *argumanlar: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [PWSH, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(surucu), *argumanlar],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=_ORTAM,
        timeout=300,
    )


def _ai_kos(tmp_path: Path, senaryo: str) -> tuple[subprocess.CompletedProcess, dict]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    surucu = tmp_path / "ai_surucu.ps1"
    surucu.write_text(_AI_SURUCU, encoding="utf-8-sig")
    kok, iz = tmp_path / "build_kok", tmp_path / "iz"
    kok.mkdir()
    r = _pwsh(surucu, str(BETIK), str(kok), senaryo, str(iz))
    assert "çıpa" not in (r.stdout + r.stderr), r.stderr[-800:]
    assert "AI hazırlık kapısı" in r.stdout, (
        f"kodlama bozuk ya da AI bloğu koşmadı (iddialar sahte-yeşil olur):\n{r.stdout[-800:]}"
    )
    nonce_yolu = iz / "cocuk_nonce.txt"
    return r, {
        "nonce": nonce_yolu.read_text(encoding="utf-8-sig") if nonce_yolu.exists() else None,
        "saglik": int((iz / "saglik_sayisi.txt").read_text(encoding="utf-8-sig").strip() or 0),
    }


@pytest.mark.parametrize("senaryo", ["yabanci_oldu", "yabanci_canli", "yabanci_nonce"])
def test_KRITIK_portu_BASKA_backend_tutarken_kapi_YESIL_GECMEZ_B10_92(tmp_path, senaryo):
    """Portta tam-yeşil rapor veren başka bir backend var; bizim EXE ya hemen öldü ya da nonce'umuzu yansıtmıyor."""
    r, iz = _ai_kos(tmp_path, senaryo)
    assert r.returncode != 0, (
        f"[{senaryo}] yanıt BAŞKA bir süreçten geldiği hâlde build CIKIS 0 verdi — ölü/yabancı EXE 'hazır' paketlenir:\n"
        f"{r.stdout[-1500:]}"
    )
    assert "Headless backend EXE hazır" not in r.stdout, f"[{senaryo}] yabancı yanıtla 'EXE hazır' basıldı"
    assert "SURUCU-SONU" not in r.stdout, "Die betiği durdurmadı"
    assert "-SkipAiGate" in r.stdout, "hata iletisi bilinçli geçişin yolunu söylemiyor"


def test_KRITIK_EXE_hemen_olurse_DONGU_BEKLEMEZ_ve_cikis_kodunu_soyler(tmp_path):
    """`$proc.HasExited` okunmalı: ölü EXE için 90×2 sn sağlık yoklaması yapılmaz, ileti EXE'nin çıkış kodunu verir."""
    r, iz = _ai_kos(tmp_path, "yabanci_oldu")
    assert iz["saglik"] <= 1, f"EXE ölü olduğu hâlde sağlık ucu {iz['saglik']} kez yoklandı (HasExited okunmuyor)"
    assert "çıkış kodu 3" in r.stdout, f"ileti EXE'nin KAPANDIĞINI / çıkış kodunu söylemiyor:\n{r.stdout[-1200:]}"


def test_KRITIK_yabanci_yanit_iletisi_PORTU_TUTAN_sureci_soyler(tmp_path):
    r, _ = _ai_kos(tmp_path, "yabanci_canli")
    assert "BAŞKA bir süreç" in r.stdout, f"ileti portu başka bir sürecin tuttuğunu söylemiyor:\n{r.stdout[-1200:]}"


def test_KRITIK_EXE_ye_TEK_SEFERLIK_nonce_verilir(tmp_path):
    _, iz1 = _ai_kos(tmp_path / "a", "kendi")
    _, iz2 = _ai_kos(tmp_path / "b", "kendi")
    n1, n2 = iz1["nonce"], iz2["nonce"]
    assert n1 and len(n1) >= 16, f"EXE'ye PEMF_HEALTH_NONCE verilmedi ya da kısa: {n1!r}"
    assert n1 != n2, "iki build AYNI nonce'u verdi (sabit nonce: önceki build'in yetimi bilebilir)"
    assert n1 not in BETIK.read_text(encoding="utf-8-sig"), "nonce betiğe GÖMÜLÜ"


def test_KARSIT_kendi_EXE_miz_nonce_u_yansitinca_kapi_GECER(tmp_path):
    r, iz = _ai_kos(tmp_path, "kendi")
    assert r.returncode == 0 and "Headless backend EXE hazır" in r.stdout, f"{r.stdout[-1500:]}\n{r.stderr[-800:]}"
    assert iz["saglik"] >= 1


def test_KRITIK_eksik_modul_raporu_derlemeyi_DURDURUR_B10_135(tmp_path):
    r, _ = _ai_kos(tmp_path, "eksik")
    assert r.returncode != 0 and "AI HAZIRLIK KAPISI KIRMIZI" in r.stdout, (
        f"üretilen EXE'de 1 modül ölü raporlandı ama build durmadı (eksik eşiği etkisiz):\n{r.stdout[-1500:]}"
    )
    assert "Headless backend EXE hazır" not in r.stdout


_KOSUL_SURUCU = r"""
param([string]$Betik, [string]$Cikti)
$ErrorActionPreference = 'Stop'
$tokens = $null; $errs = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($Betik, [ref]$tokens, [ref]$errs)
if ($errs) { throw "build betiği ayrıştırılamadı: $($errs | Out-String)" }
function Info { }
function Warn { }
function Die($m) { throw "DIE: $m" }
function SahtePy { $global:LASTEXITCODE = $global:KOD }
$PY = 'SahtePy'; $GuiRoot = 'C:\yok_kok'; $exe = 'C:\yok_kok\x.exe'; $dist = 'C:\yok_kok\dist'
$sonuc = [ordered]@{}
foreach ($k in 'check_headless_imports.py', 'pyz_koruma_kapisi.py', 'sevk_agaci_ai_hub_kapisi.py') {
    $cagri = @($ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.CommandAst] -and
        $n.InvocationOperator -eq 'Ampersand' -and $n.CommandElements[0].Extent.Text -eq '$PY' -and
        $n.Extent.Text -match [regex]::Escape($k) }, $true))
    $kayit = [ordered]@{ cagri = $cagri.Count; sonraki = $null; die = [ordered]@{} }
    if ($cagri.Count -eq 1) {
        $deyim = $cagri[0].Parent
        $liste = @($deyim.Parent.Statements)
        $i = [array]::IndexOf($liste, $deyim)
        $sonraki = if ($i -ge 0 -and ($i + 1) -lt $liste.Count) { $liste[$i + 1] } else { $null }
        if ($sonraki) { $kayit.sonraki = $sonraki.GetType().Name }
        if ($sonraki -is [System.Management.Automation.Language.IfStatementAst]) {
            $sb = [scriptblock]::Create($deyim.Extent.Text + "`n" + $sonraki.Extent.Text)
            foreach ($kod in 0, 1, 2, -1073741819) {
                $global:KOD = $kod; $global:LASTEXITCODE = 0
                try { & $sb; $kayit.die["$kod"] = 'gecti' }
                catch { $kayit.die["$kod"] = if ("$_" -like 'DIE:*') { 'die' } else { "hata: $_" } }
            }
        }
    }
    $sonuc[$k] = $kayit
}
$atama = @($ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.AssignmentStatementAst] -and
    $n.Left.Extent.Text -ieq '$env:PYTHONHASHSEED' }, $true))
$pyi = $ast.Find({ param($n) $n -is [System.Management.Automation.Language.CommandAst] -and
    $n.Extent.Text -cmatch '-m\s+PyInstaller\s' }, $true)
$tohum = [ordered]@{ atama = $atama.Count; ust_duzey = $false; deger = $null; once = $false; pyinstaller = [bool]$pyi }
if ($atama.Count -eq 1) {
    $tohum.ust_duzey = ($atama[0].Parent -eq $ast.EndBlock)
    Remove-Item Env:PYTHONHASHSEED -EA 0
    & ([scriptblock]::Create($atama[0].Extent.Text))
    $tohum.deger = $env:PYTHONHASHSEED
    if ($pyi) { $tohum.once = $atama[0].Extent.StartOffset -lt $pyi.Extent.StartOffset }
}
$sonuc['tohum'] = $tohum
$sonuc | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $Cikti -Encoding UTF8
"""


@pytest.fixture(scope="module")
def kosullar(tmp_path_factory) -> dict:
    d = tmp_path_factory.mktemp("kosul_d428")
    surucu, cikti = d / "kosul_surucu.ps1", d / "kosul.json"
    surucu.write_text(_KOSUL_SURUCU, encoding="utf-8-sig")
    r = _pwsh(surucu, str(BETIK), str(cikti))
    assert r.returncode == 0 and cikti.exists(), f"koşul sürücüsü koşmadı:\n{r.stdout[-1200:]}\n{r.stderr[-1200:]}"
    return json.loads(cikti.read_text(encoding="utf-8-sig"))


@pytest.mark.parametrize("kapi", ["check_headless_imports.py", "pyz_koruma_kapisi.py", "sevk_agaci_ai_hub_kapisi.py"])
def test_KRITIK_kapi_betigi_SIFIR_DISI_her_cikista_derleme_DURUR_B10_135(kosullar, kapi):
    k = kosullar[kapi]
    assert k["cagri"] == 1, f"{kapi} build betiğinde tam 1 kez `& $PY` ile çağrılmalı (bulunan: {k['cagri']})"
    assert k["sonraki"] == "IfStatementAst", f"{kapi} çağrısından hemen sonra çıkış kodu denetimi yok: {k['sonraki']}"
    yanlis = {kod: s for kod, s in k["die"].items() if s != ("gecti" if kod == "0" else "die")}
    assert not yanlis, (
        f"{kapi}: çıkış kodu → beklenen (0 → geçer; 1 / 2 / çökme -1073741819 → Die) tutmadı: {yanlis} "
        "(ör. `-lt 0` normal kırmızıyı, `-gt 0` çökmeyi YUTAR)"
    )


def test_KRITIK_PYTHONHASHSEED_ust_duzey_KOSULSUZ_ve_PyInstallerdan_ONCE_B10_135(kosullar):
    t = kosullar["tohum"]
    assert t["pyinstaller"], "çıpa: PyInstaller çağrısı bulunamadı"
    assert t["atama"] == 1, f"$env:PYTHONHASHSEED ataması tam 1 olmalı (yorum satırı atama DEĞİLDİR): {t['atama']}"
    assert t["ust_duzey"], "PYTHONHASHSEED ataması koşullu/iç blokta — her build'de koşmayabilir"
    assert t["deger"] == "0", f"PYTHONHASHSEED koşturulunca '0' değil: {t['deger']!r}"
    assert t["once"], "PYTHONHASHSEED ataması PyInstaller çağrısından SONRA (paket belirlenimciliği düşer)"
