# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D2.73 (B-9.21 · A-11 sahip kararı) — `install_backend_service.ps1` DESTEKLENEN ikinci kurulum yolu: servis ortamı dağıtım
profilinden (deploy\\device.env) `setup_services.ps1` ile AYNI ayrıştırmayla kurulur; SCM `depend= mosquitto` YOK.

Kusur: ortam yalnız `PYTHONUNBUFFERED`, `PEMF_HEADLESS`, `PEMF_LOG_DIR` idi → bu yolla kurulan klinikte (taze makine) hasta/seans DB'leri
DÜZ METİN, veri kökü LocalSystem profilinde (operatör göremez / yedekleyemez), `PEMF_ALLOWED_HOSTS` yok (DNS-rebinding koruması kapalı);
mosquitto servisi varsa `sc.exe config … depend= mosquitto` yazılıyordu (NSSM-managed mosquitto'da 1068 → backend HİÇ başlamaz).

⛔ Betik GERÇEKTEN koşmaz (görev kuralı: kurulum betikleri yalnız gölge koşum). Aparat betiğin ÜST DÜZEY ifadelerini sırayla dolaşır:
YALNIZ izin listesindeki komutlardan oluşan ifadeler koşar (`exit` / `pause` içerenler, `& $NssmExe`, `New-Item`, güvenlik duvarı,
`icacls`, indirme … ATLANIR); `sc.exe` ve `Get-Service` KAYITÇIDIR (mosquitto servisi "var"). `AppEnvironmentExtra`ya yayılan değişkenin
değeri okunur. Kök değişkenler (depo, `AppDir`) sahtedir; profil olarak depodaki GERÇEK `deploy\\device.env` okunur.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import capraz
import pytest

KOK = Path(__file__).resolve().parents[1]
BETIK = KOK / "scripts" / "install_backend_service.ps1"
SETUP = KOK / "scripts" / "setup_services.ps1"
DEVICE_ENV = KOK / "deploy" / "device.env"
_PWSH = shutil.which("pwsh")

pytestmark = [
    pytest.mark.skipif(sys.platform != "win32", reason="pwsh aparatı Windows betik anlamını ölçer"),
    pytest.mark.skipif((_PWSH is None) and not capraz.ZORUNLU, reason="pwsh (PowerShell 7) bulunamadı"),
]

_APARAT = r"""
param([string]$Betik, [string]$Setup, [string]$Depo, [string]$Kok, [string]$Senaryo, [string]$Girdi, [string]$Cikti)
$ErrorActionPreference = 'Stop'
$script:Sc = [System.Collections.Generic.List[string]]::new()
$script:Atlanan = 0
function Write-Host { }
function Out-Null { param([Parameter(ValueFromPipeline = $true)]$x) process { } }
function sc.exe { $script:Sc.Add("sc.exe " + ($args -join ' ')) }
function Get-Service { param([string]$Name, $ErrorAction) if ($Name -eq 'mosquitto') { [pscustomobject]@{ Name = 'mosquitto'; Status = 'Running' } } }
$izinli = [System.Collections.Generic.List[string]]@('Write-Status', 'Write-Host', 'Get-Date', 'Join-Path', 'Split-Path', 'Test-Path',
    'Where-Object', 'Select-Object', 'ForEach-Object', 'Get-Content', 'Get-PemfProfilEnvDosyasi', 'Read-PemfProfilEnv',
    'Get-PemfServisOrtami', 'Test-PemfProtectedPath', 'sc.exe', 'Get-Service', 'Out-Null')
function Agac([string]$Yol) {
    $t = $null; $e = $null
    $a = [System.Management.Automation.Language.Parser]::ParseFile($Yol, [ref]$t, [ref]$e)
    if ($e) { [Console]::Out.WriteLine("APARAT_HATASI parse " + $Yol); exit 3 }
    $a
}
function Saf($d) {
    if ($d.Find({ param($n) $n -is [System.Management.Automation.Language.ExitStatementAst] }, $true)) { return $false }
    foreach ($c in $d.FindAll({ param($n) $n -is [System.Management.Automation.Language.CommandAst] }, $true)) {
        $ad = $c.GetCommandName()
        if (-not $ad -or -not $izinli.Contains($ad)) { return $false }
    }
    $true
}
function IslevBul($ast, [string]$Ad) {
    # Betik bloğu DÖNER; çağıran betik kapsamında nokta-kaynaklar (işlev içinde tanımlanırsa dönüşte görünmez).
    $f = $ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq $Ad }, $false) | Select-Object -First 1
    if (-not $f) { return $null }
    if (-not (Saf $f)) { [Console]::Out.WriteLine("APARAT_HATASI saf olmayan islev " + $Ad); exit 3 }
    [ScriptBlock]::Create($f.Extent.Text)
}
$sonuc = [ordered]@{}
if ($Senaryo -eq 'parite') {
    foreach ($kaynak in @(@{ ad = 'install'; yol = $Betik }, @{ ad = 'setup'; yol = $Setup })) {
        $sb = IslevBul (Agac $kaynak.yol) 'Read-PemfProfilEnv'
        if (-not $sb) { $sonuc[$kaynak.ad] = $null; continue }
        . $sb
        $sonuc[$kaynak.ad] = Read-PemfProfilEnv $Girdi
    }
    ConvertTo-Json -InputObject $sonuc -Depth 4 | Set-Content -LiteralPath $Cikti -Encoding UTF8
    exit 0
}
$ast = Agac $Betik
# 1) İşlev tanımları: gövdesi saf olanlar yüklenir; olmayanlar izin listesinden düşer (çağıran ifade de koşmaz).
foreach ($f in $ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] }, $false)) {
    if (Saf $f) { . ([ScriptBlock]::Create($f.Extent.Text)) } else { [void]$izinli.Remove($f.Name) }
}
# 2) Sahte kökler (korunan değişkenlere betik içinde atama yapılmaz).
$GuiRoot = $Depo; $ScriptDir = Join-Path $Depo 'scripts'; $AppDir = Join-Path $Kok 'dist'
$ExePath = Join-Path $AppDir 'PEMF_Backend.exe'; $SvcBinary = $ExePath; $UsingExe = $true; $Mode = 'device'
$EnableTunnel = [switch]($Senaryo -eq 'tunel'); $RequireAuth = [switch]$false
$korunan = 'GuiRoot', 'ScriptDir', 'AppDir', 'ExePath', 'SvcBinary', 'UsingExe', 'Mode', 'EnableTunnel', 'RequireAuth', 'BackendFile', 'FirewallProgram'
# 3) Üst düzey ifadeler sırayla: yalnız saf olanlar koşar.
$ifadeler = @($ast.EndBlock.Statements)
foreach ($s in $ifadeler) {
    if ($s -is [System.Management.Automation.Language.FunctionDefinitionAst]) { continue }
    if ($s -is [System.Management.Automation.Language.AssignmentStatementAst]) {
        $hedef = $s.Left.Extent.Text.TrimStart('$')
        if ($korunan -contains $hedef) { continue }
    }
    if (-not (Saf $s)) { $script:Atlanan++; continue }
    . ([ScriptBlock]::Create($s.Extent.Text))
}
# 4) AppEnvironmentExtra'ya yayılan değişken + "profil yoksa servise dokunmadan dur" sırası (AST).
$cagri = $ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.CommandAst] -and $n.Extent.Text -match 'AppEnvironmentExtra' }, $true) | Select-Object -First 1
$yayilan = $cagri.CommandElements | Where-Object { $_ -is [System.Management.Automation.Language.VariableExpressionAst] -and $_.Splatted } | Select-Object -First 1
$ad = $yayilan.VariablePath.UserPath
$sonuc.degisken = $ad
$deger = Get-Variable -Name $ad -ValueOnly -ErrorAction SilentlyContinue
$sonuc.ortam = @($deger | Where-Object { $null -ne $_ } | ForEach-Object { [string]$_ })
$sonuc.sc = @($script:Sc)
$koruma = -1; $ilkNssm = -1
for ($i = 0; $i -lt $ifadeler.Count; $i++) {
    $x = $ifadeler[$i]
    if ($koruma -lt 0 -and $x -is [System.Management.Automation.Language.IfStatementAst] -and $x.Clauses[0].Item1.Extent.Text -match ('-not\s+\$' + $ad + '\b') -and $x.Find({ param($n) $n -is [System.Management.Automation.Language.ExitStatementAst] }, $true)) { $koruma = $i }
    if ($ilkNssm -lt 0 -and $x.Find({ param($n) $n -is [System.Management.Automation.Language.CommandAst] -and $n.Extent.Text -match '^&\s*\$NssmExe\s+(stop|remove|install)' }, $true)) { $ilkNssm = $i }
}
$sonuc.koruma = $koruma; $sonuc.ilk_nssm = $ilkNssm; $sonuc.atlanan = $script:Atlanan
ConvertTo-Json -InputObject $sonuc -Depth 4 | Set-Content -LiteralPath $Cikti -Encoding UTF8
exit 0
"""


def _kos(tmp_path: Path, senaryo: str, depo: Path = KOK, girdi: Path | None = None, betik: Path = BETIK) -> dict:
    aparat = tmp_path / "aparat.ps1"
    aparat.write_text(_APARAT, encoding="utf-8-sig")
    (tmp_path / "kok" / "dist").mkdir(parents=True, exist_ok=True)
    cikti = tmp_path / "cikti.json"
    p = subprocess.run(
        [_PWSH, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(aparat),
         "-Betik", str(betik), "-Setup", str(SETUP), "-Depo", str(depo), "-Kok", str(tmp_path / "kok"),
         "-Senaryo", senaryo, "-Girdi", str(girdi or DEVICE_ENV), "-Cikti", str(cikti)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180,
    )  # fmt: skip
    assert p.returncode == 0 and cikti.exists(), (
        f"aparat düştü (rc={p.returncode}):\n{p.stdout[-1500:]}\n{p.stderr[-1500:]}"
    )
    return json.loads(cikti.read_text(encoding="utf-8-sig"))


def test_ARAC_golge_aparati_yan_etkili_ifadeleri_KOSMAZ_kayitcilari_GORUR_D273(tmp_path):
    """Aparatın kendi kanıtı (betikler gerçek makinede koşmaz): sentetik betikte dosya oluşturma / SİLME, `& $NssmExe`, `exit`
    ATLANIR — nöbet dosyası yerinde kalır, süreç `exit` ile bitmez; `sc.exe` kayıtçıya düşer; saf ifade koşar."""
    nobet = tmp_path / "nobet.txt"
    nobet.write_text("dokunulmamali", encoding="utf-8")
    yasak = tmp_path / "YAPILMAMALI.txt"
    sentetik = tmp_path / "sentetik.ps1"
    sentetik.write_text(
        "$NssmExe = 'C:\\yok\\nssm.exe'\n"
        f"New-Item -ItemType File -Path '{yasak}' | Out-Null\n"
        f"Remove-Item -LiteralPath '{nobet}' -Force\n"
        "& $NssmExe stop Foo\n"
        "if ($true) { exit 7 }\n"
        "sc.exe config Foo depend= bar | Out-Null\n"
        "$Liste = @('A=1', 'B=2')\n"
        "& $NssmExe set Foo AppEnvironmentExtra @Liste\n",
        encoding="utf-8-sig",
    )
    s = _kos(tmp_path, "varsayilan", betik=sentetik)
    assert nobet.exists() and not yasak.exists(), "aparat yan etkili ifadeyi KOŞTU"
    assert s["atlanan"] >= 4, f"yan etkili ifadeler atlanmadı: {s}"
    assert s["sc"] == ["sc.exe config Foo depend= bar"], f"kayıtçı sc.exe çağrısını görmedi: {s['sc']}"
    assert s["ortam"] == ["A=1", "B=2"] and s["degisken"] == "Liste", s


def _profil() -> dict:
    d = {}
    for ln in DEVICE_ENV.read_text(encoding="utf-8").splitlines():
        t = ln.strip()
        if t and not t.startswith("#") and "=" in t:
            k, v = t.split("=", 1)
            d[k.strip()] = v.strip()
    return d


def _harita(ortam) -> dict:
    return dict(s.split("=", 1) for s in (ortam or []))


def test_KRITIK_servis_ortami_PROFILDEN_sifreleme_veri_koku_STM_izinli_adlar_ve_DEPEND_yok_D273(tmp_path):
    s = _kos(tmp_path, "varsayilan")
    o, p = _harita(s["ortam"]), _profil()
    eksik = {
        k: p[k]
        for k in ("PEMF_ENCRYPT_AT_REST", "PEMF_DATA_DIR", "PEMF_STM_PORT", "PEMF_ALLOWED_HOSTS")
        if o.get(k) != p[k]
    }
    assert not eksik, (
        f"servis ortamı profilin taşıyıcı anahtarlarını İÇERMİYOR (taze makinede düz-metin DB / LocalSystem veri kökü): {eksik} — ortam: {s['ortam']}"
    )
    assert o.get("PEMF_ENCRYPT_AT_REST") == "1" and o.get("PEMF_ALLOWED_HOSTS") != "*"
    assert not [c for c in s["sc"] if "depend=" in c], f"SCM bağımlılığı yazıldı (1068 → backend başlamaz): {s['sc']}"


def test_KRITIK_tunel_YALNIZ_anahtarla_acilir_profil_acsa_bile_varsayilan_KAPALI_D273(tmp_path):
    """device.env tüneli açıyor (`PEMF_ENABLE_TUNNEL=1`); bu betiğin belgelenmiş güvenli varsayılanı yalnız-LAN — profil onu ezemez."""
    assert _profil().get("PEMF_ENABLE_TUNNEL") == "1", "aparat: profil tüneli açmıyor, kol anlamsız"
    o = _harita(_kos(tmp_path, "varsayilan")["ortam"])
    assert o.get("PEMF_ENABLE_TUNNEL") == "0", (
        f"anahtar verilmeden tünel AÇIK (cihaz internete açılır): {o.get('PEMF_ENABLE_TUNNEL')!r}"
    )
    assert o.get("PEMF_REQUIRE_AUTH") == _profil().get("PEMF_REQUIRE_AUTH"), (
        "profilin kimlik doğrulama zorunluluğu gevşetildi"
    )


def test_KARSIT_EnableTunnel_ile_tunel_ACIK_ve_kimlik_ZORUNLU_D273(tmp_path):
    o = _harita(_kos(tmp_path, "tunel")["ortam"])
    assert o.get("PEMF_ENABLE_TUNNEL") == "1" and o.get("PEMF_REQUIRE_AUTH") == "1", o


def test_KRITIK_profil_YOKSA_servise_DOKUNMADAN_durur_D273(tmp_path):
    sahte_depo = tmp_path / "depo_yok"
    (sahte_depo / "scripts").mkdir(parents=True)
    s = _kos(tmp_path, "varsayilan", depo=sahte_depo)
    assert not s["ortam"], f"profil yokken ortam kuruldu (şifrelemesiz kurulum): {s['ortam']}"
    assert 0 <= s["koruma"] < s["ilk_nssm"], (
        f"profil yoksa duran koruma, mevcut servisi kaldıran/kuran ilk NSSM adımından ÖNCE değil: koruma={s['koruma']} "
        f"ilk_nssm={s['ilk_nssm']}"
    )


def test_KRITIK_profil_ayristirmasi_setup_services_ile_AYNI_D273(tmp_path):
    zor = tmp_path / "zor.env"
    zor.write_text(
        "# yorum\n\n  PEMF_A = 1 \nPEMF_B=x=y\nPEMF_DATA_DIR=C:\\ProgramData\\PEMF System\n#PEMF_C=2\nbozuk satir\nPEMF_A=2\n",
        encoding="utf-8",
    )
    for girdi in (DEVICE_ENV, zor):
        s = _kos(tmp_path, "parite", girdi=girdi)
        assert s["install"] is not None, "install_backend_service.ps1 profil ayrıştırıcısı (Read-PemfProfilEnv) YOK"
        assert s["install"] == s["setup"], f"iki kurulum yolu profili FARKLI ayrıştırıyor ({girdi.name}): {s}"
