# =============================================================================
# PEMF surum senkronizasyonu - versions.json TEK KAYNAK
# -----------------------------------------------------------------------------
# versions.json'daki degerleri hedef dosyalara yazar. build_installer.ps1 ve
# build_apk.ps1 basladiginda otomatik cagrilir; elle de calistirilabilir:
#
#   pwsh -File build_tools\sync_versions.ps1            # yaz
#   pwsh -File build_tools\sync_versions.ps1 -Check     # yazma, sadece farki bildir (CI icin)
#
# NOT: Bu dosya BILEREK yalnizca ASCII karakter icerir. Projedeki diger .ps1
# dosyalari UTF-8 (BOM'suz) + Turkce karakter iceriyor; Windows PowerShell 5.1
# onlari ANSI (cp1254) okuyup parse hatasi veriyor. Bu betik hem 5.1 hem 7'de
# calissin diye ASCII tutuldu. Digerleri icin pwsh (PowerShell 7) sart.
# =============================================================================
[CmdletBinding()]
param([switch]$Check)

$ErrorActionPreference = "Stop"
$ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
$VersionsFile = Join-Path $ProjectRoot "versions.json"

if (-not (Test-Path $VersionsFile)) { Write-Host "[surum] HATA: versions.json yok: $VersionsFile" -ForegroundColor Red; exit 1 }
$v = Get-Content $VersionsFile -Raw -Encoding UTF8 | ConvertFrom-Json

function Test-Semver($value, $label) {
    if ($value -notmatch '^\d+\.\d+\.\d+$') { Write-Host "[surum] HATA: $label 'x.y.z' olmali, su an: '$value'" -ForegroundColor Red; exit 1 }
}
Test-Semver $v.backend     "backend"
Test-Semver $v.launcher    "launcher"
Test-Semver $v.mobile.name "mobile.name"
Test-Semver $v.frontendOta "frontendOta"
# NOT: tip kontrolu YAPMA. ConvertFrom-Json tam sayiyi PS 5.1'de Int32,
# PS 7'de Int64 uretir; '-isnot [int]' PS 7'de yanlis tetikler. Degerin
# kendisine bak.
if ("$($v.mobile.androidVersionCode)" -notmatch '^\d+$' -or [int64]$v.mobile.androidVersionCode -lt 1) {
    Write-Host "[surum] HATA: mobile.androidVersionCode pozitif tam sayi olmali, su an: '$($v.mobile.androidVersionCode)'" -ForegroundColor Red; exit 1
}

$degisen = 0
$sorun   = 0

# Bir dosyada regex ile hedeflenen degeri gunceller. UTF-8 (BOM'suz) korunur,
# dosyanin geri kalan bicimi hic bozulmaz.
function Set-Value {
    param(
        [string]$Path,       # dosya
        [string]$Pattern,    # yakalama grubu 1 = korunacak on-ek, grup 2 = eski deger
        [string]$New,        # yeni deger
        [string]$Label,
        [switch]$FirstOnly
    )
    $full = Join-Path $ProjectRoot $Path
    if (-not (Test-Path $full)) { Write-Host "  [ATLA] $Label - dosya yok: $Path" -ForegroundColor DarkYellow; return }

    $raw = [System.IO.File]::ReadAllText($full)
    $m = [regex]::Match($raw, $Pattern)
    if (-not $m.Success) { Write-Host "  [!!] $Label - desen bulunamadi ($Path)" -ForegroundColor Yellow; $script:sorun++; return }

    $eski = $m.Groups[2].Value
    if ($eski -eq $New) { Write-Host ("  [ok]   {0,-34} {1}" -f $Label, $New) -ForegroundColor DarkGray; return }

    if ($Check) {
        Write-Host ("  [FARK] {0,-34} {1} -> {2}   ({3})" -f $Label, $eski, $New, $Path) -ForegroundColor Yellow
        $script:sorun++
        return
    }

    $rx = [regex]$Pattern
    $yeni = if ($FirstOnly) { $rx.Replace($raw, { param($x) $x.Groups[1].Value + $New + $x.Groups[3].Value }, 1) }
            else            { $rx.Replace($raw, { param($x) $x.Groups[1].Value + $New + $x.Groups[3].Value }) }
    # BOM'suz UTF-8 yaz (mevcut dosyalarla ayni kodlama)
    [System.IO.File]::WriteAllText($full, $yeni, (New-Object System.Text.UTF8Encoding $false))
    Write-Host ("  [YAZ]  {0,-34} {1} -> {2}" -f $Label, $eski, $New) -ForegroundColor Green
    $script:degisen++
}

Write-Host ""
Write-Host "=== Surum senkronizasyonu (versions.json) ===" -ForegroundColor Cyan
if ($Check) { Write-Host "  MOD: yalnizca kontrol, dosya yazilmayacak" -ForegroundColor DarkGray }

# --- backend: VERSION dosyasi ---
#     .iss (MyAppVersion) ve docs/version_info.txt'yi build_installer.ps1 icindeki
#     Sync-ReleaseVersion zaten VERSION'dan uretiyor; burada tekrarlamiyoruz.
Set-Value -Path "VERSION" -Label "backend (VERSION)" -New $v.backend `
          -Pattern '(\A\s*)(\d+\.\d+\.\d+)(\s*\z)'

# --- launcher: Cargo.toml [workspace.package] + tauri.conf.json ---
Set-Value -Path "launcher\Cargo.toml" -Label "launcher (Cargo.toml)" -New $v.launcher `
          -Pattern '(\[workspace\.package\][\s\S]*?version\s*=\s*")(\d+\.\d+\.\d+)(")' -FirstOnly
Set-Value -Path "launcher\app\tauri.conf.json" -Label "launcher (tauri.conf.json)" -New $v.launcher `
          -Pattern '("version"\s*:\s*")(\d+\.\d+\.\d+)(")' -FirstOnly

# --- mobile: pf/app.json ---
Set-Value -Path "pf\app.json" -Label "mobile adi (app.json)" -New $v.mobile.name `
          -Pattern '("version"\s*:\s*")(\d+\.\d+\.\d+)(")' -FirstOnly
Set-Value -Path "pf\app.json" -Label "mobile versionCode" -New ([string]$v.mobile.androidVersionCode) `
          -Pattern '("versionCode"\s*:\s*)(\d+)()'
Set-Value -Path "pf\app.json" -Label "mobile iOS buildNumber" -New $v.mobile.iosBuildNumber `
          -Pattern '("buildNumber"\s*:\s*")([^"]+)(")'

# --- mobile (Android GERCEK kaynagi): pf/android/app/build.gradle ---
# ONEMLI: pf/android/ COMMIT'LI tam native proje ve build_apk.ps1 gradle'i DOGRUDAN calistiriyor
# (expo prebuild YOK). Bu yuzden app.json'daki version/versionCode APK'ya UYGULANMIYOR; gradle
# defaultConfig KAZANIYOR. Denetimde build.gradle 2.3.2/vc9'da DONMUS bulundu (versions.json
# 2.3.3/vc10 derken) -> yayinlanan APK yanlis surumdeydi ve Play Store'a ayni versionCode ile
# ikinci kez yuklenemezdi. Tek-kaynak artik build.gradle'i da yaziyor.
Set-Value -Path "pf\android\app\build.gradle" -Label "mobile versionName (build.gradle)" -New $v.mobile.name `
          -Pattern '(versionName\s+")(\d+\.\d+\.\d+)(")' -FirstOnly
Set-Value -Path "pf\android\app\build.gradle" -Label "mobile versionCode (build.gradle)" -New ([string]$v.mobile.androidVersionCode) `
          -Pattern '(versionCode\s+)(\d+)()' -FirstOnly

# --- frontend OTA ---
Set-Value -Path "frontend_version.json" -Label "frontend OTA" -New $v.frontendOta `
          -Pattern '("version"\s*:\s*")(\d+\.\d+\.\d+)(")' -FirstOnly

Write-Host ""
if ($Check) {
    if ($sorun -gt 0) { Write-Host "[surum] $sorun uyusmazlik - versions.json ile hedefler ayni degil." -ForegroundColor Red; exit 1 }
    Write-Host "[surum] Tum surumler versions.json ile uyumlu." -ForegroundColor Green
} else {
    Write-Host "[surum] $degisen dosya guncellendi, $sorun sorun." -ForegroundColor $(if ($sorun) { "Yellow" } else { "Green" })
    if ($sorun -gt 0) { exit 1 }
}

# ACIK 'exit 0' SART: cagiran betikler $LASTEXITCODE'a bakiyor. Betik exit
# cagirmadan biterse $LASTEXITCODE onceki komuttan kalan degeri korur ve
# basarili senkronizasyon hatali gorunur.
exit 0
