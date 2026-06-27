# ============================================================================
# PEMF Medical System - Installer Build Script
# PyInstaller (OneDir) + Inno Setup
# ============================================================================
# KULLANIM: build_tools\ klasöründen calistirin:
#   cd build_tools
#   .\build_installer.ps1
# ============================================================================

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir

function Write-Step { param($msg) Write-Host "" ; Write-Host "=== $msg ===" -ForegroundColor Cyan }
function Write-OK   { param($msg) Write-Host "  [OK] $msg" -ForegroundColor Green }
function Write-Warn { param($msg) Write-Host "  [!!] $msg" -ForegroundColor Yellow }
function Write-Fail { param($msg) Write-Host "  [HATA] $msg" -ForegroundColor Red ; exit 1 }

function Invoke-NpmCleanInstall {
    param([string]$Label)
    if (Test-Path "package-lock.json") {
        Write-Host "  $Label bagimliliklari yukleniyor (npm ci --legacy-peer-deps)..." -ForegroundColor DarkGray
        & npm ci --legacy-peer-deps
    } else {
        Write-Warn "$Label package-lock.json bulunamadi; npm install --legacy-peer-deps kullaniliyor."
        & npm install --legacy-peer-deps
    }
    if ($LASTEXITCODE -ne 0) { Write-Fail "$Label npm bagimlilik kurulumu basarisiz!" }
}

function Sync-ReleaseVersion {
    param(
        [string]$Version,
        [string]$IssPath,
        [string]$VersionInfoPath
    )

    if ($Version -notmatch '^\d+\.\d+\.\d+$') {
        Write-Fail "VERSION formati x.y.z olmali. Su an: $Version"
    }

    $parts = $Version.Split(".")
    $fileVersion = "$Version.0"
    $tuple = "($($parts[0]), $($parts[1]), $($parts[2]), 0)"

    $issText = Get-Content -Path $IssPath -Raw
    $issText = $issText -replace '#define MyAppVersion\s+".*"', "#define MyAppVersion   `"$Version`""
    Set-Content -Path $IssPath -Value $issText -Encoding UTF8

    $versionInfo = @"
# UTF-8
#
# PEMF GUI Version Information Resource
# Bu dosya build_tools\build_installer.ps1 tarafindan VERSION dosyasindan uretilir.
#

VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=$tuple,
    prodvers=$tuple,
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [
      StringTable(
        u'040904B0',
        [StringStruct(u'CompanyName', u'PEMF Medical Technologies'),
        StringStruct(u'FileDescription', u'PEMF Therapeutic Device Control Software'),
        StringStruct(u'FileVersion', u'$fileVersion'),
        StringStruct(u'InternalName', u'PEMF_GUI'),
        StringStruct(u'LegalCopyright', u'Copyright (C) 2026 PEMF Medical Technologies. All rights reserved.'),
        StringStruct(u'OriginalFilename', u'PEMF_GUI.exe'),
        StringStruct(u'ProductName', u'PEMF Control Suite'),
        StringStruct(u'ProductVersion', u'$fileVersion')])
      ]
    ),
    VarFileInfo([VarStruct(u'Translation', [1033, 1200])])
  ]
)
"@
    Set-Content -Path $VersionInfoPath -Value $versionInfo -Encoding UTF8
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Magenta
Write-Host "   PEMF Medical System - Installer Build" -ForegroundColor Magenta
Write-Host "   PyInstaller (OneDir) + Inno Setup" -ForegroundColor Magenta
Write-Host "============================================================" -ForegroundColor Magenta

# --- Adim 0: Release Surumu ---
Write-Step "Release Surumu Senkronizasyonu"

$VersionFile = Join-Path $ProjectRoot "VERSION"
if (-not (Test-Path $VersionFile)) {
    Write-Fail "VERSION dosyasi bulunamadi: $VersionFile"
}
$AppVersion = (Get-Content -Path $VersionFile -Raw).Trim()
$IssPath = Join-Path $ScriptDir "PEMF_Setup.iss"
$VersionInfoPath = Join-Path $ProjectRoot "docs\version_info.txt"
Sync-ReleaseVersion -Version $AppVersion -IssPath $IssPath -VersionInfoPath $VersionInfoPath
Write-OK "Surum senkronize edildi: $AppVersion"

# --- Adim 1: Python Kontrolu ---
Write-Step "Python Ortami Kontrolu"

$PythonCandidates = @()
if ($env:PEMF_BUILD_PYTHON) {
    $PythonCandidates += $env:PEMF_BUILD_PYTHON
}
$PythonCandidates += @(
    (Join-Path $ProjectRoot "myenv\Scripts\python.exe"),
    (Join-Path (Split-Path -Parent $ProjectRoot) "myenv\Scripts\python.exe"),
    "C:\build_envs\pemf_py310\Scripts\python.exe",
    "python"
)

$PythonExe = $null
foreach ($candidate in $PythonCandidates) {
    if ($candidate -eq "python") {
        $PythonExe = $candidate
        break
    }
    if (Test-Path $candidate) {
        $PythonExe = $candidate
        break
    }
}

$env:PYTHONNOUSERSITE = "1"
$env:PYTHONPATH = ""
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

try {
    $PyVersion = & $PythonExe --version 2>&1
    Write-OK "Python: $PyVersion"
} catch {
    Write-Fail "Python bulunamadi: $PythonExe"
}

if ($PyVersion -notmatch "Python 3\.10\.") {
    Write-Warn "Release build icin Python 3.10.x onerilir. Su an: $PyVersion"
}

# --- Node / npm Kontrolu ---
Write-Step "Node.js Ortami Kontrolu"
try {
    $NodeVersion = & node --version 2>&1
    $NpmVersion = & npm --version 2>&1
    Write-OK "Node: $NodeVersion"
    Write-OK "npm: $NpmVersion"
} catch {
    Write-Fail "Node.js veya npm bulunamadi. Frontend build icin gereklidir."
}

# --- Adim 2: PyInstaller Kontrolu ---
Write-Step "PyInstaller Kontrolu"

$PyInstallerCheck = & $PythonExe -m PyInstaller --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Fail "PyInstaller bulunamadi. Yuklemek icin: pip install pyinstaller"
}
Write-OK "PyInstaller: $PyInstallerCheck"

# --- Adim 3: Inno Setup Kontrolu ---
Write-Step "Inno Setup Kontrolu"

$InnoSetupPaths = @(
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    "C:\Program Files\Inno Setup 6\ISCC.exe",
    "C:\Program Files (x86)\Inno Setup 5\ISCC.exe"
)

$IsccExe = $null
foreach ($path in $InnoSetupPaths) {
    if (Test-Path $path) {
        $IsccExe = $path
        break
    }
}

if (-not $IsccExe) {
    Write-Warn "Inno Setup bulunamadi!"
    Write-Host "    Indirmek icin: https://jrsoftware.org/isinfo.php" -ForegroundColor Yellow
    Write-Host "    Sadece PyInstaller build yapilacak (Setup.exe olusturulmayacak)" -ForegroundColor Yellow
    $SkipInnoSetup = $true
} else {
    Write-OK "Inno Setup: $IsccExe"
    $SkipInnoSetup = $false
}

# --- Adim 4: Temizlik ---
Write-Step "Onceki Build Temizleniyor"

$DistDir  = Join-Path $ProjectRoot "dist"
$BuildDir = Join-Path $ProjectRoot "build"

if (Test-Path $DistDir) {
    Remove-Item $DistDir -Recurse -Force
    Write-OK "dist/ temizlendi"
}
if (Test-Path $BuildDir) {
    Remove-Item $BuildDir -Recurse -Force
    Write-OK "build/ temizlendi"
}

# --- Adim 4.5: React Web Export ---
Write-Step "React Frontend Web Export"

$FrontendDir = Join-Path $ProjectRoot "frontend"
if (-not (Test-Path $FrontendDir)) {
    Write-Fail "frontend\ klasoru bulunamadi!"
}

Push-Location $FrontendDir
try {
    $FrontendDistDir = Join-Path $FrontendDir "dist"
    if (Test-Path $FrontendDistDir) {
        Write-Host "  Eski frontend dist temizleniyor..." -ForegroundColor DarkGray
        Remove-Item $FrontendDistDir -Recurse -Force
    }

    Invoke-NpmCleanInstall -Label "Frontend"

    Write-Host "  Typecheck calistiriliyor (npm run typecheck)..." -ForegroundColor DarkGray
    & npm run typecheck
    if ($LASTEXITCODE -ne 0) { Write-Fail "npm run typecheck basarisiz! (TypeScript hatalarini duzeltin)" }

    Write-Host "  Expo Web Export aliniyor..." -ForegroundColor DarkGray
    $env:EXPO_ROUTER_DISABLE_RN_NAVIGATION_CHECK = "1"
    & npx expo export --platform web
    if ($LASTEXITCODE -ne 0) { Write-Fail "Expo web export basarisiz!" }
} finally {
    Pop-Location
}

$FrontendIndex = Join-Path $FrontendDir "dist\index.html"
if (-not (Test-Path $FrontendIndex)) {
    Write-Fail "frontend\dist\index.html uretilemedi! React build adimi hatali."
}
$FrontendJsDir = Join-Path $FrontendDir "dist\_expo\static\js\web"
$FrontendJsFiles = @()
if (Test-Path $FrontendJsDir) {
    $FrontendJsFiles = Get-ChildItem $FrontendJsDir -Filter "*.js" -File -ErrorAction SilentlyContinue
}
if ($FrontendJsFiles.Count -eq 0) {
    Write-Fail "frontend\dist\_expo\static\js\web altinda JS bundle bulunamadi! React export eksik."
}

$FrontendVersionJson = @{
    version = $AppVersion
    builtAt = (Get-Date).ToString("o")
} | ConvertTo-Json
Set-Content -Path (Join-Path $FrontendDir "dist\version.json") -Value $FrontendVersionJson -Encoding UTF8
Write-OK "React web export basariyla tamamlandi ve dogrulandi."

# --- Adim 4.6: DEMA Terapi Simulatoru Build ---
Write-Step "DEMA Terapi Simulatoru Build"

$DemaDirItem = Get-ChildItem -Path $ProjectRoot -Directory -Force -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -like "dema-terapi-sim*" } |
    Select-Object -First 1

if (-not $DemaDirItem) {
    Write-Fail "dema-terapi-sim* klasoru bulunamadi!"
}
$DemaDir = $DemaDirItem.FullName
Write-OK "DEMA klasoru bulundu: $($DemaDirItem.Name)"

Push-Location $DemaDir
try {
    Invoke-NpmCleanInstall -Label "DEMA"

    Write-Host "  Typecheck calistiriliyor (npm run lint)..." -ForegroundColor DarkGray
    & npm run lint
    if ($LASTEXITCODE -ne 0) { Write-Fail "DEMA npm run lint basarisiz! (TypeScript hatalarini duzeltin)" }

    Write-Host "  Vite build aliniyor..." -ForegroundColor DarkGray
    & npm run build
    if ($LASTEXITCODE -ne 0) { Write-Fail "DEMA npm run build basarisiz!" }
} finally {
    Pop-Location
}

$DemaIndex = Join-Path $DemaDir "dist\index.html"
if (-not (Test-Path $DemaIndex)) {
    Write-Fail "$($DemaDirItem.Name)\dist\index.html uretilemedi! DEMA build adimi hatali."
}
Write-OK "DEMA Terapi Simulatoru build edildi ve dogrulandi."

# --- Adim 5: PyInstaller OneDir Build ---
Write-Step "PyInstaller OneDir Build Baslatiliyor"
Write-Host "  Bu islem 5-15 dakika surebilir..." -ForegroundColor DarkGray

$SpecFile = Join-Path $ScriptDir "PEMF_GUI_onedir.spec"
if (-not (Test-Path $SpecFile)) {
    Write-Fail "Spec dosyasi bulunamadi: $SpecFile"
}

$startTime = Get-Date

& $PythonExe -m PyInstaller `
    --distpath (Join-Path $ProjectRoot "dist") `
    --workpath (Join-Path $ProjectRoot "build") `
    --noconfirm `
    $SpecFile

if ($LASTEXITCODE -ne 0) {
    Write-Fail "PyInstaller build basarisiz! (Exit code: $LASTEXITCODE)"
}

$elapsed = (Get-Date) - $startTime
Write-OK "PyInstaller tamamlandi ($([int]$elapsed.TotalSeconds) saniye)"

# --- Adim 6: Build Ciktisini Dogrula ---
Write-Step "Build Ciktisi Dogrulanıyor"

$OutputDir = Join-Path $ProjectRoot "dist\PEMF_GUI"
$OutputExe = Join-Path $OutputDir "PEMF_GUI.exe"

if (-not (Test-Path $OutputDir)) {
    Write-Fail "dist\PEMF_GUI\ klasoru bulunamadi!"
}
if (-not (Test-Path $OutputExe)) {
    Write-Fail "PEMF_GUI.exe bulunamadi!"
}

$DirSize   = (Get-ChildItem $OutputDir -Recurse | Measure-Object -Property Length -Sum).Sum
$DirSizeMB = [math]::Round($DirSize / 1MB, 1)
$FileCount = (Get-ChildItem $OutputDir -Recurse -File).Count

Write-OK "PEMF_GUI.exe olusturuldu"
Write-OK "Klasor boyutu: $DirSizeMB MB ($FileCount dosya)"

# --- Adim 6.5: Release Artifact Config/Secret Kontrolu ---
Write-Step "Release Artifact Config/Secret Kontrolu"

# Bu installer plug-and-play dagitim icin config ve credential dosyalarini
# bilerek tasir. HF token gibi gelistirme/hesap tokenlari yine release icinde
# olmamali; onlar ayri taranir.
$BundledConfigFiles = @(
    "config.json",
    "credentials.json",
    "hivemq_users.json",
    "mosquitto_passwords.txt",
    "mosquitto_acl.conf",
    "bridge_hivemq.conf",
    "mosquitto.conf"
)

$BundledConfigHits = @()
foreach ($name in $BundledConfigFiles) {
    $BundledConfigHits += Get-ChildItem $OutputDir -Recurse -File -Force -Filter $name -ErrorAction SilentlyContinue
}

$ForbiddenPatterns = @(
    "hf_[A-Za-z0-9]{20,}"
)

$TextFiles = Get-ChildItem $OutputDir -Recurse -File -Force -ErrorAction SilentlyContinue |
    Where-Object { $_.Length -lt 5MB -and $_.Extension -match "^\.(py|json|txt|ini|conf|cfg|template|md|html|js|css|qss)$" }

$PatternHits = @()
foreach ($pattern in $ForbiddenPatterns) {
    $PatternHits += $TextFiles | Select-String -Pattern $pattern -ErrorAction SilentlyContinue
}

if ($BundledConfigHits.Count -gt 0) {
    Write-Host ""
    Write-Host "Bundle edilen config/credential dosyalari:" -ForegroundColor Yellow
    foreach ($hit in $BundledConfigHits) {
        Write-Host "  FILE: $($hit.FullName)" -ForegroundColor Yellow
    }
    Write-Warn "Config ve sifre dosyalari kullanici onayi ile setup'a gomuluyor."
}

if ($PatternHits.Count -gt 0) {
    Write-Host ""
    Write-Host "Release icinde yasakli token paterni bulundu:" -ForegroundColor Red
    foreach ($hit in $PatternHits) {
        Write-Host "  TEXT: $($hit.Path):$($hit.LineNumber): $($hit.Line.Trim())" -ForegroundColor Red
    }
    Write-Fail "Release artifact icinde Hugging Face veya benzeri token paterni bulundu."
}

$ExpectedBundledConfig = Join-Path $OutputDir "_internal\config\config.json"
if (-not (Test-Path $ExpectedBundledConfig)) {
    Write-Fail "Bundle config eksik: $ExpectedBundledConfig"
}
Write-OK "Bundle config dogrulandi: _internal\config\config.json"
Write-OK "Yasakli HF token paterni bulunmadi."

$AiAssetsDir = Join-Path $ProjectRoot "release_assets\ai_models"
$RequiredAiAssets = @(
    "ai_hub\cat_disease\XGBoost.onnx",
    "ai_hub\cat_disease\XGBoost.pkl",
    "ai_hub\cat_disease\label_encoder.pkl",
    "ai_hub\cat_disease\scaler_X.pkl",
    "ai_hub\cat_landmark\thresholds_calibrated.json",
    "ai_hub\cat_landmark\yolo26m-pose.onnx",
    "ai_hub\cat_segmentation\yolov8m-seg.onnx",
    "ai_hub\cat_thermal\GhostNetV2.onnx",
    "ai_hub\em_kedi_legacy\ResNet_kedi_v2.onnx",
    "ai_hub\em_kedi_legacy\scaler_X_kedi_v2.pkl",
    "ai_hub\em_kedi_legacy\scaler_extra_kedi.pkl",
    "ai_hub\em_kedi_legacy\scaler_y_kedi_v2.pkl",
    "ai_hub\em_kedi\BiLSTM_XXL_Raw.onnx"
    "ai_hub\em_kedi\scaler_X.pkl",
    "ai_hub\em_kedi\scaler_extra.pkl",
    "ai_hub\em_kedi\scaler_y.pkl",
    "ai_hub\em_petri\PetriNet_v3.onnx",
    "ai_hub\em_petri\scaler_D_petri_v3.pkl",
    "ai_hub\em_petri\scaler_E_petri_v3.pkl",
    "ai_hub\em_petri\scaler_X_petri_v3.pkl",
    "ai_hub\em_petri\scaler_extra_petri_v3.pkl",
    "ai_hub\em_phantom\PhantomNet_v3.onnx",
    "ai_hub\em_phantom\scaler_D_phantom_v3.pkl",
    "ai_hub\em_phantom\scaler_E_phantom_v3.pkl",
    "ai_hub\em_phantom\scaler_X_phantom_v3.pkl",
    "ai_hub\em_phantom\scaler_extra_phantom_v3.pkl",
    "ai_hub\feline_reticulocytes\yolov8s.onnx",
    "ai_hub\petri_dish\yolo11m-seg.onnx"
)

if (Test-Path $AiAssetsDir) {
    foreach ($asset in $RequiredAiAssets) {
        $assetPath = Join-Path $AiAssetsDir $asset
        if (-not (Test-Path $assetPath)) {
            Write-Warn "Kritik AI model eksik: release_assets\ai_models\$asset"
        }
    }

    $AiSize = (Get-ChildItem $AiAssetsDir -Recurse -File | Measure-Object -Property Length -Sum).Sum
    $AiFiles = (Get-ChildItem $AiAssetsDir -Recurse -File).Count
    Write-OK "Opsiyonel AI paketi hazir: $([math]::Round($AiSize / 1MB, 1)) MB ($AiFiles dosya)"
} else {
    Write-Warn "release_assets\ai_models bulunamadi; AI component bos kurulacak."
}

# --- Adim 7: Inno Setup ile Setup.exe Olustur ---
if (-not $SkipInnoSetup) {
    Write-Step "VC++ Redistributable Hazirligi"

    $LatteSetupDir = Join-Path $ProjectRoot "lattekurulum"
    $VcRedistPath = Join-Path $LatteSetupDir "VC_redist.x64.exe"
    if (-not (Test-Path $LatteSetupDir)) {
        New-Item -ItemType Directory -Path $LatteSetupDir | Out-Null
    }

    if (-not (Test-Path $VcRedistPath)) {
        $VcRedistUrl = "https://aka.ms/vc14/vc_redist.x64.exe"
        Write-Warn "VC_redist.x64.exe bulunamadi; Microsoft resmi linkinden indiriliyor..."
        try {
            Invoke-WebRequest -Uri $VcRedistUrl -OutFile $VcRedistPath -UseBasicParsing
            if (Test-Path $VcRedistPath) {
                Write-OK "VC++ Redistributable indirildi: lattekurulum\VC_redist.x64.exe"
            }
        } catch {
            Write-Warn "VC++ Redistributable indirilemedi. Setup yine olusturulacak; hedef makinede VC runtime zaten kurulu degilse manuel kurulum gerekebilir. Hata: $($_.Exception.Message)"
        }
    } else {
        Write-OK "VC++ Redistributable hazir: lattekurulum\VC_redist.x64.exe"
    }

    Write-Step "Inno Setup ile Installer Olusturuluyor"

    $IssFile = Join-Path $ScriptDir "PEMF_Setup.iss"
    if (-not (Test-Path $IssFile)) {
        Write-Fail "PEMF_Setup.iss bulunamadi: $IssFile"
    }

    $InnoOutputDir = Join-Path $ScriptDir "Output"
    if (-not (Test-Path $InnoOutputDir)) {
        New-Item -ItemType Directory -Path $InnoOutputDir | Out-Null
    }

    $startTime2 = Get-Date
    & $IsccExe $IssFile

    if ($LASTEXITCODE -ne 0) {
        Write-Fail "Inno Setup basarisiz! (Exit code: $LASTEXITCODE)"
    }

    $elapsed2 = (Get-Date) - $startTime2
    Write-OK "Inno Setup tamamlandi ($([int]$elapsed2.TotalSeconds) saniye)"

    $SetupExe = Get-ChildItem $InnoOutputDir -Filter "*.exe" | Select-Object -First 1
    if ($SetupExe) {
        $SetupSizeMB = [math]::Round($SetupExe.Length / 1MB, 1)
        Write-OK "Kurulum dosyasi: $($SetupExe.Name) ($SetupSizeMB MB)"
    }
}

# --- Ozet ---
$BuildVersion = $AppVersion

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "                  BUILD TAMAMLANDI" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host ""
Write-Host "  PyInstaller Ciktisi : dist\PEMF_GUI\" -ForegroundColor White
if (-not $SkipInnoSetup) {
    Write-Host "  Kurulum Dosyasi    : build_tools\Output\PEMFSetup_v$BuildVersion.exe" -ForegroundColor White
    Write-Host ""
    Write-Host "  -> Veterinere dagitmak icin: PEMFSetup_v$BuildVersion.exe dosyasini gonderin." -ForegroundColor Cyan
} else {
    Write-Host ""
    Write-Host "  -> Inno Setup kurulumu yapilip tekrar calistirin." -ForegroundColor Yellow
    Write-Host "     Indirme: https://jrsoftware.org/isinfo.php" -ForegroundColor Yellow
}
Write-Host ""
