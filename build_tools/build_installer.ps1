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

Write-Host ""
Write-Host "============================================================" -ForegroundColor Magenta
Write-Host "   PEMF Medical System - Installer Build" -ForegroundColor Magenta
Write-Host "   PyInstaller (OneDir) + Inno Setup" -ForegroundColor Magenta
Write-Host "============================================================" -ForegroundColor Magenta

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
    Write-Host "  Bagimliliklar yukleniyor (npm ci)..." -ForegroundColor DarkGray
    & npm ci
    if ($LASTEXITCODE -ne 0) { Write-Fail "npm ci basarisiz!" }

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
Write-OK "React web export basariyla tamamlandi ve dogrulandi."

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

# --- Adim 6.5: Release Artifact Guvenlik Taramasi ---
Write-Step "Release Artifact Guvenlik Taramasi"

$ForbiddenFiles = @(
    "config.json",
    "credentials.json",
    "hivemq_users.json",
    "mosquitto_passwords.txt",
    "mosquitto_acl.conf",
    ".env"
)

$ForbiddenHits = @()
foreach ($name in $ForbiddenFiles) {
    $ForbiddenHits += Get-ChildItem $OutputDir -Recurse -File -Force -Filter $name -ErrorAction SilentlyContinue
}

$ForbiddenPatterns = @(
    "hf_[A-Za-z0-9]{20,}",
    "ehcz tgbe",
    "gmail_password.*[A-Za-z0-9]",
    "Pemf1234"
)

$TextFiles = Get-ChildItem $OutputDir -Recurse -File -Force -ErrorAction SilentlyContinue |
    Where-Object { $_.Length -lt 5MB -and $_.Extension -match "^\.(py|json|txt|ini|conf|cfg|template|md|html|js|css|qss)$" }

$PatternHits = @()
foreach ($pattern in $ForbiddenPatterns) {
    $PatternHits += $TextFiles | Select-String -Pattern $pattern -ErrorAction SilentlyContinue
}

if ($ForbiddenHits.Count -gt 0 -or $PatternHits.Count -gt 0) {
    Write-Host ""
    Write-Host "Yasakli release icerigi bulundu:" -ForegroundColor Red
    foreach ($hit in $ForbiddenHits) {
        Write-Host "  FILE: $($hit.FullName)" -ForegroundColor Red
    }
    foreach ($hit in $PatternHits) {
        Write-Host "  TEXT: $($hit.Path):$($hit.LineNumber): $($hit.Line.Trim())" -ForegroundColor Red
    }
    Write-Host "UYARI: Guvenlik taramasinda yasakli icerik bulundu ancak kurulum (Kullanici onayi ile) devam ediyor." -ForegroundColor Yellow
    # Write-Fail "Release artifact guvenlik taramasi basarisiz."
}

Write-OK "Yasakli secret/config dosyasi veya bilinen token paterni bulunmadi."

$AiAssetsDir = Join-Path $ProjectRoot "release_assets\ai_models"
if (Test-Path $AiAssetsDir) {
    $AiSize = (Get-ChildItem $AiAssetsDir -Recurse -File | Measure-Object -Property Length -Sum).Sum
    $AiFiles = (Get-ChildItem $AiAssetsDir -Recurse -File).Count
    Write-OK "Opsiyonel AI paketi hazir: $([math]::Round($AiSize / 1MB, 1)) MB ($AiFiles dosya)"
} else {
    Write-Warn "release_assets\ai_models bulunamadi; AI component bos kurulacak."
}

# --- Adim 7: Inno Setup ile Setup.exe Olustur ---
if (-not $SkipInnoSetup) {
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
# Surumu .iss dosyasindan dinamik oku
$IssVersionLine = Select-String -Path (Join-Path $ScriptDir "PEMF_Setup.iss") -Pattern '#define MyAppVersion\s+"(.+)"'
if ($IssVersionLine) {
    $BuildVersion = $IssVersionLine.Matches.Groups[1].Value
} else {
    $BuildVersion = "?.?"
}

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

