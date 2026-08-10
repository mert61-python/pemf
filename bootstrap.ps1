# =============================================================================
# PEMF Vet — bootstrap.ps1
# SIFIR (bos) bir Windows makinesinde tum build+publish arac zincirini kurar.
# Amac: bu embeddable-python klasorunu herhangi bir laptoba koy + bu scripti
#       calistir -> tum build'ler (backend/base.zip/installer/launcher/APK)
#       ve yayinlar yapilabilir hale gelir.
#
# KURAR:  Node.js, Git, GitHub CLI, JDK 17, Inno Setup 6,
#         Rust (+ cargo-tauri), MSVC C++ Build Tools,
#         Android cmdline-tools + NDK 27.1.12297006 + CMake 3.22.1
# KURMAZ: Python -> myenv KLASORDE self-contained (Scripts\python310.dll +
#         python310.zip). Yine de dogrulanir; calismazsa uyarir.
# TASIMAZ: gh/Vercel oturumu makineye ozeldir -> her makinede `gh auth login`.
#
# KULLANIM (yonetici PowerShell onerilir; MSVC + winget icin):
#   .\bootstrap.ps1                 # her seyi kur (idempotent)
#   .\bootstrap.ps1 -SkipAndroid    # APK toolchain'i (NDK ~1GB) atla
#   .\bootstrap.ps1 -SkipMsvc       # MSVC zaten kuruluysa atla
#   .\bootstrap.ps1 -VerifyOnly     # hicbir sey kurma, sadece durum raporu ver
#
# NOT: winget kurulumlari makine/kullanici PATH'ini gunceller ama ACIK olan
#      terminal bunu gormez. Script PATH'i tazeler; yine de en sonda "yeni
#      terminal ac" denirse ilk seferde gereklidir.
# =============================================================================
[CmdletBinding()]
param(
    [switch]$SkipAndroid,
    [switch]$SkipMsvc,
    [switch]$VerifyOnly,
    [string]$NdkVersion   = "27.1.12297006",
    [string]$CmakeVersion = "3.22.1",
    [string]$NodePackage  = "OpenJS.NodeJS.LTS"   # RN/Expo icin LTS guvenli
)

$ErrorActionPreference = "Stop"
$ProgressPreference     = "SilentlyContinue"   # Invoke-WebRequest yavaslamasin

# --- konum: bu script guii\ icinde; embeddable kok = guii'nin ustu (myenv orada) ---
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$GuiRoot   = $ScriptDir
$EmbRoot   = Split-Path -Parent $GuiRoot

# --- yardimcilar ---
function Info($m){ Write-Host "[bootstrap] $m" -ForegroundColor Cyan }
function OK($m){   Write-Host "  [OK]   $m"    -ForegroundColor Green }
function Warn($m){ Write-Host "  [!!]   $m"    -ForegroundColor Yellow }
function Err($m){  Write-Host "  [HATA] $m"    -ForegroundColor Red }
function Have($exe){ [bool](Get-Command $exe -ErrorAction SilentlyContinue) }

function Refresh-Path {
    $m = [System.Environment]::GetEnvironmentVariable("Path","Machine")
    $u = [System.Environment]::GetEnvironmentVariable("Path","User")
    $env:PATH = (@($m, $u, "$env:USERPROFILE\.cargo\bin") | Where-Object { $_ }) -join ";"
}

function Test-Admin {
    $id = [System.Security.Principal.WindowsIdentity]::GetCurrent()
    (New-Object System.Security.Principal.WindowsPrincipal($id)).IsInRole(
        [System.Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Test-Msvc {
    # cl.exe genelde PATH'te olmaz; vswhere ile VC++ x64 araclarini ara.
    $vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
    if (Test-Path $vswhere) {
        $p = & $vswhere -latest -products * `
            -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 `
            -property installationPath 2>$null
        if ($p) { return $true }
    }
    # yedek: herhangi bir cl.exe var mi
    foreach ($base in @("${env:ProgramFiles}\Microsoft Visual Studio","${env:ProgramFiles(x86)}\Microsoft Visual Studio")) {
        if (Test-Path $base) {
            if (Get-ChildItem $base -Recurse -Filter cl.exe -ErrorAction SilentlyContinue | Select-Object -First 1) { return $true }
        }
    }
    return $false
}

function Test-WinSdk {
    # kernel32.lib = Windows SDK (Rust linkleme icin SART). cl.exe olsa bile eksik olabilir.
    foreach ($base in @("${env:ProgramFiles(x86)}\Windows Kits\10\Lib","${env:ProgramFiles}\Windows Kits\10\Lib")) {
        if (Test-Path $base) {
            if (Get-ChildItem $base -Recurse -Filter kernel32.lib -ErrorAction SilentlyContinue | Where-Object { $_.FullName -match "\\um\\x64\\" } | Select-Object -First 1) { return $true }
        }
    }
    return $false
}

function Winget-Ensure {
    param([string]$Id, [string]$Probe, [string]$Label, [string]$Override)
    if ($Probe -and (Have $Probe)) { OK "$Label zaten var  ($((Get-Command $Probe).Source))"; return }
    if ($VerifyOnly)               { Warn "$Label YOK (VerifyOnly: kurulmadi)"; return }
    Info "$Label kuruluyor (winget: $Id)..."
    $wargs = @("install","--id",$Id,"-e","--accept-source-agreements","--accept-package-agreements","--silent")
    if ($Override) { $wargs += @("--override", $Override) }
    try { & winget @wargs } catch { Warn ("winget {0}: {1}" -f $Id, $_.Exception.Message) }
    Refresh-Path
    if     ($Probe -and (Have $Probe)) { OK "$Label kuruldu" }
    elseif ($Probe)                    { Warn "$Label kuruldu ama PATH'te gorunmuyor (yeni terminal gerekebilir)" }
    else                               { OK "$Label kurulum komutu calisti" }
}

# =============================================================================
Write-Host ""
Write-Host "============================================================" -ForegroundColor Magenta
Write-Host "   PEMF Vet — Build Toolchain Bootstrap" -ForegroundColor Magenta
Write-Host "   embeddable kok: $EmbRoot" -ForegroundColor DarkGray
Write-Host "============================================================" -ForegroundColor Magenta

# --- 0. On kontrol ---
Info "On kontrol"
if (Test-Admin) { OK "Yonetici olarak calisiyor" }
else            { Warn "Yonetici DEGIL — MSVC/winget bazi kurulumlari sorabilir. Sorun olursa yonetici PowerShell'de tekrar calistir." }

if (-not (Have "winget")) {
    Err "winget bulunamadi. App Installer'i Microsoft Store'dan kur (winget onun icinde gelir), sonra tekrar calistir."
    Err "Store: https://apps.microsoft.com/detail/9nblggh4nns1"
    exit 1
}
OK "winget mevcut"
Refresh-Path

# --- 1. winget araclari: Git, Node, gh, JDK17, Inno ---
Info "1) Temel araclar (Git / Node / GitHub CLI / JDK 17 / Inno Setup)"
Winget-Ensure -Id "Git.Git"              -Probe "git"  -Label "Git"
Winget-Ensure -Id $NodePackage           -Probe "node" -Label "Node.js (LTS)"
Winget-Ensure -Id "GitHub.cli"           -Probe "gh"   -Label "GitHub CLI"
Winget-Ensure -Id "Microsoft.OpenJDK.17" -Probe "java" -Label "JDK 17"
Winget-Ensure -Id "JRSoftware.InnoSetup" -Probe "iscc" -Label "Inno Setup 6"
if (-not (Have "iscc") -and (Test-Path "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe")) {
    OK "Inno Setup 6 kurulu (ISCC PATH'te degil ama build_installer.ps1 tam yoldan bulur)"
}

# --- 2. Rust + cargo-tauri ---
Info "2) Rust toolchain (launcher/Tauri icin)"
if (Have "cargo") {
    OK "Rust zaten var  ($(& cargo --version))"
} elseif ($VerifyOnly) {
    Warn "Rust YOK (VerifyOnly)"
} else {
    Info "rustup-init indiriliyor + kuruluyor (stable-msvc, minimal)..."
    $ri = Join-Path $env:TEMP "rustup-init.exe"
    curl.exe -L -s -o $ri "https://win.rustup.rs/x86_64"
    & $ri -y --default-toolchain stable --profile minimal --no-modify-path
    Refresh-Path
    if ((Have "cargo") -or (Test-Path "$env:USERPROFILE\.cargo\bin\cargo.exe")) { OK "Rust kuruldu" } else { Warn "Rust kurulumu dogrulanamadi" }
}
# cargo-tauri (launcher build komutu: cargo tauri build)
if (-not $VerifyOnly) {
    $cargoBin = "$env:USERPROFILE\.cargo\bin"
    if (Test-Path "$cargoBin\cargo-tauri.exe") {
        OK "cargo-tauri zaten var"
    } elseif (Test-Path "$cargoBin\cargo.exe") {
        Info "cargo-tauri kuruluyor (cargo install tauri-cli, kaynaktan derlenir ~5-10dk)..."
        & "$cargoBin\cargo.exe" install tauri-cli --version "^2" --locked
        if (Test-Path "$cargoBin\cargo-tauri.exe") { OK "cargo-tauri kuruldu" } else { Warn "cargo-tauri kurulamadi" }
    }
} elseif (Test-Path "$env:USERPROFILE\.cargo\bin\cargo-tauri.exe") { OK "cargo-tauri var" } else { Warn "cargo-tauri YOK (VerifyOnly)" }

# --- 3. MSVC C++ Build Tools (Rust linker: link.exe) ---
Info "3) MSVC C++ Build Tools (Rust linkleme icin sart)"
if (Test-Msvc) {
    OK "MSVC VC++ araclari mevcut (cl.exe/link.exe bulundu)"
} elseif ($SkipMsvc) {
    Warn "MSVC atlandi (-SkipMsvc). Launcher linklenmesi cl.exe/link.exe gerektirir."
} elseif ($VerifyOnly) {
    Warn "MSVC YOK (VerifyOnly)"
} else {
    Info "VS 2022 Build Tools + VCTools workload kuruluyor (buyuk ~3-6GB, sessiz)..."
    $ov = "--quiet --wait --norestart --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended"
    Winget-Ensure -Id "Microsoft.VisualStudio.2022.BuildTools" -Probe "" -Label "VS Build Tools + VCTools" -Override $ov
    if (Test-Msvc) { OK "MSVC kuruldu" } else { Warn "MSVC kurulumu dogrulanamadi (yeniden baslatma/yeni terminal gerekebilir)" }
}

# --- 3b. Windows SDK (kernel32.lib — Rust linkleme icin SART) ---
# ONEMLI: cl.exe olsa bile Windows SDK eksik olabilir (minimal BuildTools kurulumu).
# SDK yoksa 'cargo tauri build' -> LNK1181: kernel32.lib acilamiyor.
Info "3b) Windows SDK (Rust linkleme icin kernel32.lib)"
if (Test-WinSdk) {
    OK "Windows SDK mevcut (kernel32.lib bulundu)"
} elseif ($SkipMsvc) {
    Warn "Windows SDK atlandi (-SkipMsvc). Launcher linkleme kernel32.lib gerektirir."
} elseif ($VerifyOnly) {
    Warn "Windows SDK YOK (VerifyOnly)"
} else {
    Info "Windows SDK 10.0.26100 kuruluyor (winget, ~1-2GB)..."
    Winget-Ensure -Id "Microsoft.WindowsSDK.10.0.26100" -Probe "" -Label "Windows SDK 10.0.26100"
    if (-not (Test-WinSdk)) {
        Warn "26100 dogrulanamadi, 22621 deneniyor..."
        Winget-Ensure -Id "Microsoft.WindowsSDK.10.0.22621" -Probe "" -Label "Windows SDK 10.0.22621"
    }
    if (Test-WinSdk) { OK "Windows SDK kuruldu" } else { Warn "Windows SDK kurulamadi (winget ID/ag)" }
}

# --- 4. Android SDK bilesenleri (APK icin) ---
if ($SkipAndroid) {
    Info "4) Android toolchain ATLANDI (-SkipAndroid)"
} else {
    Info "4) Android cmdline-tools + NDK $NdkVersion + CMake $CmakeVersion (APK icin; NDK ~1GB — UZUN)"
    $sdk = Join-Path $env:LOCALAPPDATA "Android\Sdk"
    $env:ANDROID_HOME = $sdk; $env:ANDROID_SDK_ROOT = $sdk
    $sm = Join-Path $sdk "cmdline-tools\latest\bin\sdkmanager.bat"

    if (Test-Path $sm) {
        OK "sdkmanager mevcut"
    } elseif ($VerifyOnly) {
        Warn "sdkmanager YOK (VerifyOnly)"
    } else {
        Info "cmdline-tools indiriliyor (curl)..."
        $zip = Join-Path $env:TEMP "clt_bootstrap.zip"
        curl.exe -L -s -o $zip "https://dl.google.com/android/repository/commandlinetools-win-11076708_latest.zip"
        $ex = Join-Path $env:TEMP ("clt_bs_" + [System.Guid]::NewGuid().ToString("N").Substring(0,8))
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        [System.IO.Compression.ZipFile]::ExtractToDirectory($zip, $ex)
        $dst = Join-Path $sdk "cmdline-tools\latest"
        New-Item -ItemType Directory -Force $dst | Out-Null
        robocopy (Join-Path $ex "cmdline-tools") $dst /E /NFL /NDL /NJH /NP /R:1 /W:1 | Out-Null
        if (Test-Path $sm) { OK "sdkmanager kuruldu" } else { Warn "sdkmanager kurulamadi" }
    }

    if ((Test-Path $sm) -and -not $VerifyOnly) {
        if (-not (Have "java")) { Warn "java PATH'te yok — sdkmanager JDK ister (JDK 17 adimini kontrol et)" }
        $y = (1..80 | ForEach-Object { "y" }) -join "`r`n"
        Info "Lisanslar kabul ediliyor..."
        $y | & $sm --sdk_root="$sdk" --licenses  2>&1 | Select-Object -Last 1 | Out-Null
        Info "platform-tools + ndk;$NdkVersion + cmake;$CmakeVersion indiriliyor (UZUN, ag hizina bagli)..."
        $y | & $sm --sdk_root="$sdk" "platform-tools" "ndk;$NdkVersion" "cmake;$CmakeVersion" 2>&1 | Select-Object -Last 3
        if (Test-Path (Join-Path $sdk "ndk\$NdkVersion")) { OK "NDK $NdkVersion kuruldu" } else { Warn "NDK kurulmadi (ag/throttle olabilir; tekrar calistir)" }
        if (Test-Path (Join-Path $sdk "cmake\$CmakeVersion")) { OK "CMake $CmakeVersion kuruldu" } else { Warn "CMake kurulmadi" }
        Info "compileSdk platform + build-tools'u gradle ilk build'de otomatik ceker (lisanslar kabul edildi)."
    }
    if (Test-Path (Join-Path $sdk "ndk\$NdkVersion")) { OK "Android NDK hazir: $sdk\ndk\$NdkVersion" }
}

# --- 5. Python (KLASORDE gomulu embedded — self-contained, sistem Python/myenv GEREKMEZ) ---
Info "5) Python build ortami (embedded — klasorde, self-contained)"
$embPy = Join-Path $EmbRoot "python.exe"
if (Test-Path $embPy) {
    $pv = & $embPy --version 2>&1
    OK "Embedded Python: $pv (klasorde; sistem Python/myenv GEREKMEZ)"
    $hasPyi = & $embPy -c "import PyInstaller,numpy,torch; print(PyInstaller.__version__)" 2>&1
    if ($LASTEXITCODE -eq 0) { OK "Build deps mevcut (PyInstaller $hasPyi + numpy/torch pinli)" }
    else { Warn "Embedded deps eksik -> $embPy -m pip install --no-deps -r build_tools\myenv-requirements.txt --extra-index-url https://download.pytorch.org/whl/cpu" }
} else {
    Warn "Embedded python bulunamadi ($embPy). Script embeddable kokun icinden calismali."
}

# --- 5b. SIR TARAMASI KAPISI (pre-commit + gitleaks) ---
# ⚠️ DENETIM 2026-08-09 (Tier 3): `.pre-commit-config.yaml` gitleaks hook'unu TANIMLIYORDU ama
# `pre-commit install` HIC calistirilmamisti (`.git/hooks` bostu) — kapi bir kez bile acilmadi.
# Depo PUBLIC ve gecmisinde canli sir bulunmus bir depo. Kurulum adimini bootstrap'a bagliyoruz
# ki "yeni makinede unutuldu" diye acik kalmasin. CI'da ayrica gitleaks isi kosar (kapiyi kuran
# kisi kim olursa olsun korur) — ikisi birbirinin yerine GECMEZ.
Info "5b) Sir taramasi kapisi (pre-commit + gitleaks)"
if (Test-Path $embPy) {
    $pcOk = $false
    & $embPy -m pre_commit --version *> $null
    if ($LASTEXITCODE -eq 0) { $pcOk = $true }
    else {
        & $embPy -m pip install "pre-commit>=4.0,<5.0" *> $null
        & $embPy -m pre_commit --version *> $null
        if ($LASTEXITCODE -eq 0) { $pcOk = $true }
    }
    if (-not $pcOk) {
        Warn "pre-commit kurulamadi -> elle: $embPy -m pip install -r requirements-dev.txt"
    } elseif (-not (Test-Path (Join-Path $PSScriptRoot ".git"))) {
        Warn "Bu klasor bir git deposu degil -> pre-commit hook'u kurulamadi."
    } else {
        Push-Location $PSScriptRoot
        & $embPy -m pre_commit install *> $null
        $hook = Join-Path $PSScriptRoot ".git\hooks\pre-commit"
        if (Test-Path $hook) { OK "pre-commit hook kurulu (gitleaks + ruff + buyuk-dosya kapisi)" }
        else { Warn "pre-commit install basarisiz -> elle: $embPy -m pre_commit install" }
        Pop-Location
    }
}

# --- 6. DOGRULAMA TABLOSU ---
Refresh-Path
Write-Host ""
Write-Host "============================================================" -ForegroundColor Magenta
Write-Host "   DOGRULAMA" -ForegroundColor Magenta
Write-Host "============================================================" -ForegroundColor Magenta
$sdk = Join-Path $env:LOCALAPPDATA "Android\Sdk"
$rows = @(
    @{ Ad="node";        Var=(Have "node");                                     Icin="backend web export, APK, DEMA" }
    @{ Ad="npm";         Var=(Have "npm");                                      Icin="paket yonetimi" }
    @{ Ad="git";         Var=(Have "git");                                      Icin="genel" }
    @{ Ad="gh";          Var=(Have "gh");                                       Icin="yayin (GitHub Releases)" }
    @{ Ad="cargo";       Var=((Have "cargo") -or (Test-Path "$env:USERPROFILE\.cargo\bin\cargo.exe")); Icin="launcher (Rust)" }
    @{ Ad="cargo-tauri"; Var=(Test-Path "$env:USERPROFILE\.cargo\bin\cargo-tauri.exe"); Icin="launcher (Tauri build)" }
    @{ Ad="MSVC (cl)";   Var=(Test-Msvc);                                       Icin="launcher derleme" }
    @{ Ad="Windows SDK"; Var=(Test-WinSdk);                                     Icin="launcher linkleme (kernel32.lib)" }
    @{ Ad="java (JDK17)";Var=(Have "java");                                     Icin="APK (gradle)" }
    @{ Ad="Inno (ISCC)"; Var=((Have "iscc") -or (Test-Path "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe")); Icin="offline installer" }
    @{ Ad="Android NDK"; Var=(Test-Path (Join-Path $sdk "ndk\$NdkVersion"));    Icin="APK native" }
    @{ Ad="Android CMake";Var=(Test-Path (Join-Path $sdk "cmake\$CmakeVersion"));Icin="APK native" }
    @{ Ad="embedded Py"; Var=(Test-Path (Join-Path $EmbRoot "python.exe"));      Icin="backend/base.zip/installer (klasorde, self-contained)" }
)
$missing = 0
foreach ($r in $rows) {
    $mark = if ($r.Var) { "[OK] " } else { "[YOK]"; }
    $col  = if ($r.Var) { "Green" } else { "Red" }
    if (-not $r.Var) { $missing++ }
    Write-Host ("  {0}  {1,-14} — {2}" -f $mark, $r.Ad, $r.Icin) -ForegroundColor $col
}

Write-Host ""
if ($missing -eq 0) {
    Write-Host "  >> TUM ARAC ZINCIRI HAZIR." -ForegroundColor Green
} else {
    Write-Host "  >> $missing bilesen eksik. Yukaridaki uyarilara bak; genelde 'yeni terminal ac' + tekrar calistir cozer." -ForegroundColor Yellow
}

# --- 7. SONRAKI ADIMLAR ---
Write-Host ""
Write-Host "  SONRAKI ADIMLAR:" -ForegroundColor Cyan
Write-Host "   1) YENI bir PowerShell terminali ac (PATH guncellemesi icin)." -ForegroundColor White
Write-Host "   2) Yayin oturumu (makineye ozel, tasinmaz):" -ForegroundColor White
Write-Host "        gh auth login          # GitHub Releases icin" -ForegroundColor DarkGray
Write-Host "        npx vercel login       # (web deploy yapacaksan)" -ForegroundColor DarkGray
Write-Host "   3) Build'ler (guii kokunden — detay: BUILD.md):" -ForegroundColor White
Write-Host "        .\scripts\build_backend_exe.ps1          # backend frozen EXE" -ForegroundColor DarkGray
Write-Host "        python .\build_tools\make_base_zip.py    # base.zip" -ForegroundColor DarkGray
Write-Host "        .\build_tools\build_installer.ps1        # offline installer" -ForegroundColor DarkGray
Write-Host "        cd launcher\app; cargo tauri build       # launcher" -ForegroundColor DarkGray
Write-Host "        .\build_tools\build_apk.ps1              # Android APK" -ForegroundColor DarkGray
Write-Host ""
