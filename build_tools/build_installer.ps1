# ============================================================================
# PEMF Medical System - Installer Build Script
# PyInstaller (OneDir) + Inno Setup
# ============================================================================
# KULLANIM: build_tools\ klasöründen calistirin:
#   .\build_tools\build_installer.ps1               # device installer (varsayilan)
#   .\build_tools\build_installer.ps1 -Mode server  # server installer
# ============================================================================

param([ValidateSet('device', 'server')][string]$Mode = 'device')

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
# PEMF Backend Version Information Resource
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
        [StringStruct(u'CompanyName', u'İBİA Teknoloji Ltd. Şti.'),
        StringStruct(u'FileDescription', u'PEMF Therapeutic Device Control Software'),
        StringStruct(u'FileVersion', u'$fileVersion'),
        StringStruct(u'InternalName', u'PEMF_Backend'),
        StringStruct(u'LegalCopyright', u'Copyright (C) 2026 İBİA Teknoloji Ltd. Şti. All rights reserved.'),
        StringStruct(u'OriginalFilename', u'PEMF_Backend.exe'),
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

# TEK KAYNAK: versions.json -> VERSION / Cargo.toml / tauri.conf.json / app.json /
# frontend_version.json. Asagidaki Sync-ReleaseVersion ise VERSION'dan .iss ve
# version_info.txt uretmeye devam eder.
$SyncScript = Join-Path $ScriptDir "sync_versions.ps1"
if (Test-Path $SyncScript) {
    & $SyncScript
    if ($LASTEXITCODE -ne 0) { Write-Fail "Surum senkronizasyonu basarisiz (versions.json)." }
} else {
    Write-Warn "sync_versions.ps1 yok; VERSION dosyasi oldugu gibi kullanilacak."
}

$VersionFile = Join-Path $ProjectRoot "VERSION"
if (-not (Test-Path $VersionFile)) {
    Write-Fail "VERSION dosyasi bulunamadi: $VersionFile"
}
$AppVersion = (Get-Content -Path $VersionFile -Raw).Trim()
$IssPath = Join-Path $ScriptDir "PEMF_Backend_Setup.iss"
$VersionInfoPath = Join-Path $ProjectRoot "docs\version_info.txt"
Sync-ReleaseVersion -Version $AppVersion -IssPath $IssPath -VersionInfoPath $VersionInfoPath
Write-OK "Surum senkronize edildi: $AppVersion"

# --- Adim 1: Python Kontrolu ---
Write-Step "Python Ortami Kontrolu"

# 2026-08-01 konsolidasyonu myenv'i ve sistem Python'unu KALDIRDI; build artik klasordeki
# EMBEDDED yorumlayiciyi kullanir (bkz. BUILD.md + scripts\build_backend_exe.ps1). Bu script
# guncellenmemisti: yalnizca silinmis myenv yollarina bakip son care olarak PATH'teki "python"u
# SECIYOR ve onu DOGRULAMADAN kabul ediyordu. Windows'ta PATH'teki "python" cogu kez Microsoft
# Store ALIAS STUB'idir; `--version` calistirilinca surum yerine "Python was not found..."
# yazar. Eski kod bunu surum satiri sanip yalnizca UYARI verip devam ediyordu ve build bir
# sonraki adimda "PyInstaller bulunamadi" ile anlamsiz bicimde patliyordu.
$PythonCandidates = @()
if ($env:PEMF_BUILD_PYTHON) {
    $PythonCandidates += $env:PEMF_BUILD_PYTHON
}
$PythonCandidates += @(
    (Join-Path (Split-Path -Parent $ProjectRoot) "python.exe"),   # embedded (klasor koku) — ASIL
    (Join-Path $ProjectRoot "myenv\Scripts\python.exe"),          # legacy (kaldirildi, geriye uyum)
    (Join-Path (Split-Path -Parent $ProjectRoot) "myenv\Scripts\python.exe"),
    "C:\build_envs\pemf_py310\Scripts\python.exe",
    "python"
)

$env:PYTHONNOUSERSITE = "1"
$env:PYTHONPATH = ""
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

# Adayi SECMEDEN ONCE gercekten calistigini dogrula: `--version` gecerli bir surum
# yazmali. Store stub'i / bozuk kurulum boylece elenir ve siradaki adaya gecilir.
$PythonExe = $null
$PyVersion = $null
foreach ($candidate in $PythonCandidates) {
    if ($candidate -ne "python" -and -not (Test-Path $candidate)) { continue }
    try {
        $out = (& $candidate --version 2>&1 | Out-String).Trim()
    } catch {
        continue
    }
    if ($out -match "Python (\d+\.\d+\.\d+)") {
        $PythonExe = $candidate
        $PyVersion = "Python $($Matches[1])"
        break
    }
    Write-Warn "Aday Python calismiyor, atlaniyor: $candidate  ($($out -replace '\s+',' '))"
}

if (-not $PythonExe) {
    Write-Fail ("Calisan Python yorumlayicisi bulunamadi. Beklenen: klasor kokundeki embedded " +
                "python.exe ($((Join-Path (Split-Path -Parent $ProjectRoot) 'python.exe'))). " +
                "Override: `$env:PEMF_BUILD_PYTHON = '<tam yol>'")
}
Write-OK "Python: $PyVersion  ($PythonExe)"

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

# ⚠️ TEK KAYNAK = `pf/` (2026-08-15). Eskiden burada "frontend" yaziyordu ve `guii/` altinda
# AYNI deponun (pemf-frontend.git) IKI ayri klonu duruyordu: `pf/` (gelistirilen) ve
# `frontend/` (build'in okudugu). Ikisi de .gitignore'da oldugu icin ayrisma GORUNMUYORDU.
# Olculdu: `frontend/` 15 commit GERIDE idi -> arayuz degisiklikleri masaustu paketine HIC
# ULASMIYORDU (dogrulanan ornek: web'de canli ses kaydi coken hata `pf/`de duzeltildi ama
# paket eski agactan uretiliyordu). Ikinci klon kaldirildi; tekrar olusmasi
# tests/test_frontend_tek_kaynak.py ile kilitlendi.
$FrontendDir = Join-Path $ProjectRoot "pf"

if ($env:PEMF_SKIP_FRONTEND -eq '1') {
    # Web UI (pf/) DEGISMEDIGINDE re-export'u ATLA: onceden saglanan frontend\dist KULLANILIR.
    # (Expo deps kurulumu gerekmez; frozen backend'e mevcut web UI baked kalir. Asagidaki
    # dogrulama HER IKI yolda da calisir -> gecersiz/eksik dist yine yakalanir.)
    Write-OK "Frontend export ATLANDI (PEMF_SKIP_FRONTEND=1) - mevcut frontend\dist kullaniliyor."
} else {
    # GERCEK web-UI kaynagi = pf\ (Expo app; export:web + typecheck scriptleri var). Eski BOS guii\frontend\
    # (git'te hic yoktu = leftover build-yolu) yerine pf\'den export edilir; cikti (pf\dist) kanonik
    # frontend\dist'e kopyalanir (PyInstaller spec frontend\dist'i bundle'lar).
    $PfDir = Join-Path $ProjectRoot "pf"
    if (-not (Test-Path (Join-Path $PfDir "package.json"))) { Write-Fail "pf\ (web-UI kaynagi) bulunamadi!" }
    Push-Location $PfDir
    try {
        $PfDist = Join-Path $PfDir "dist"
        if (Test-Path $PfDist) {
            Write-Host "  Eski pf\dist temizleniyor..." -ForegroundColor DarkGray
            Remove-Item $PfDist -Recurse -Force
        }

        Invoke-NpmCleanInstall -Label "Frontend (pf)"

        Write-Host "  Typecheck calistiriliyor (npm run typecheck)..." -ForegroundColor DarkGray
        & npm run typecheck
        if ($LASTEXITCODE -ne 0) { Write-Fail "npm run typecheck basarisiz! (pf TypeScript hatalarini duzeltin)" }

        Write-Host "  Expo Web Export aliniyor (export:web = expo export + postexport-web patcher)..." -ForegroundColor DarkGray
        $env:EXPO_ROUTER_DISABLE_RN_NAVIGATION_CHECK = "1"
        & npm run export:web
        if ($LASTEXITCODE -ne 0) { Write-Fail "Expo web export (npm run export:web) basarisiz!" }
    } finally {
        Pop-Location
    }

    # === PEMF-AYNALAMA-BASI === (test cipasi: tests/test_installer_frontend_aynalama.py)
    # pf\dist -> frontend\dist (PyInstaller'in bekledigi kanonik konum)
    #
    # DENETIM 2026-08-17: 2026-08-15 "tek kaynak" degisikliginden beri $FrontendDir ve $PfDir
    # AYNI dizini (pf) gosteriyor. Asagidaki Remove-Item TAZE export edilen pf\dist'i SILIYOR,
    # ardindan Copy-Item kaynagi bulamiyor ("Cannot find path ...\pf\dist") ve
    # $ErrorActionPreference='Stop' yuzunden Inno installer build'i VARSAYILAN yolda COKUYORDU
    # (yalniz PEMF_SKIP_FRONTEND=1 ile derlenebiliyordu). Ustelik pf\dist silinmis kaldigi icin
    # sonraki backend build'i de etkileniyordu.
    #
    # Aynalama bu haliyle GEREKSIZDIR: PEMF_Backend_onedir.spec web arayuzunu DOGRUDAN pf/dist'ten
    # paketliyor (yayinlanan base-app.zip ile dogrulandi: frontend\dist\version.json diskte VAR ama
    # zip'te YOK). Yine de kod KALDIRILMIYOR — $FrontendDir bir gun yeniden ayri bir dizine donerse
    # (baska bir paketleyici kanonik frontend\dist beklerse) yol calismaya devam etsin.
    #
    # Kilit: tests/test_installer_frontend_aynalama.py — blogu GERCEKTEN kosturur (grep DEGIL).
    $FrontendDistDir = Join-Path $FrontendDir "dist"
    $PfDistDir       = Join-Path $PfDir "dist"
    $AyniYer = ([IO.Path]::GetFullPath($PfDistDir).TrimEnd('\')) -ieq ([IO.Path]::GetFullPath($FrontendDistDir).TrimEnd('\'))
    if ($AyniYer) {
        Write-OK "Web export ZATEN kanonik konumda ($PfDistDir) - aynalama gerekmiyor."
    } else {
        if (Test-Path $FrontendDistDir) { Remove-Item $FrontendDistDir -Recurse -Force }
        if (-not (Test-Path $FrontendDir)) { New-Item -ItemType Directory -Path $FrontendDir -Force | Out-Null }
        Copy-Item $PfDistDir $FrontendDistDir -Recurse -Force
        Write-OK "pf web export -> $FrontendDistDir kopyalandi."
    }
    # === PEMF-AYNALAMA-SONU ===
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

$SpecFile = Join-Path $ScriptDir "PEMF_Backend_onedir.spec"
if (-not (Test-Path $SpecFile)) {
    Write-Fail "Spec dosyasi bulunamadi: $SpecFile"
}

$startTime = Get-Date

# KRITIK: spec project_path'i os.getcwd()'den turetir (basename 'build_tools' ise parent=guii, degilse cwd).
# build_installer artik herhangi bir dizinden calisabildigi icin CWD'yi $ProjectRoot (guii) yap ->
# spec her zaman project_path=guii cozer (yoksa backend_service.py 'not found' + Surum 0.0.0 olur).
Push-Location $ProjectRoot
try {
    & $PythonExe -m PyInstaller `
        --distpath (Join-Path $ProjectRoot "dist") `
        --workpath (Join-Path $ProjectRoot "build") `
        --noconfirm `
        $SpecFile
} finally {
    Pop-Location
}

if ($LASTEXITCODE -ne 0) {
    Write-Fail "PyInstaller build basarisiz! (Exit code: $LASTEXITCODE)"
}

$elapsed = (Get-Date) - $startTime
Write-OK "PyInstaller tamamlandi ($([int]$elapsed.TotalSeconds) saniye)"

# --- Adim 6: Build Ciktisini Dogrula ---
Write-Step "Build Ciktisi Dogrulanıyor"

$OutputDir = Join-Path $ProjectRoot "dist\PEMF_Backend"
$OutputExe = Join-Path $OutputDir "PEMF_Backend.exe"

if (-not (Test-Path $OutputDir)) {
    Write-Fail "dist\PEMF_Backend\ klasoru bulunamadi!"
}
if (-not (Test-Path $OutputExe)) {
    Write-Fail "PEMF_Backend.exe bulunamadi!"
}

$DirSize   = (Get-ChildItem $OutputDir -Recurse | Measure-Object -Property Length -Sum).Sum
$DirSizeMB = [math]::Round($DirSize / 1MB, 1)
$FileCount = (Get-ChildItem $OutputDir -Recurse -File).Count

Write-OK "PEMF_Backend.exe olusturuldu"
Write-OK "Klasor boyutu: $DirSizeMB MB ($FileCount dosya)"

# --- Adim 6.5: Release Artifact Config/Secret Kontrolu ---
Write-Step "Release Artifact Config/Secret Kontrolu"

# Bu installer plug-and-play dagitim icin config ve credential dosyalarini
# bilerek tasir. HF token gibi gelistirme/hesap tokenlari yine release icinde
# olmamali; onlar ayri taranir.
$BundledConfigFiles = @(
    "config.json",
    "credentials.json",
    "pemf_secrets.json",           # GUNCEL: TUM sirlar burada (SecretsManager) - release'e ASLA gomulmemeli
    "hivemq_users.json",           # legacy: credential_manager.export_hivemq_config hala uretebilir
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

# GUNCEL YAPI (spec:117 guvenlik): gercek config.json bundle EDILMEZ (Gmail App Password icerir);
# yalniz config.json.template gomulur. Gercek config runtime'da %USERPROFILE%\.pemf_gui'den okunur.
$ExpectedTemplate = Join-Path $OutputDir "_internal\config\config.json.template"
if (-not (Test-Path $ExpectedTemplate)) {
    Write-Warn "Bundle config template eksik: _internal\config\config.json.template (spec config bundling'i kontrol et)"
} else {
    Write-OK "Bundle config template dogrulandi: _internal\config\config.json.template"
}
$LeakedConfig = Join-Path $OutputDir "_internal\config\config.json"
if (Test-Path $LeakedConfig) {
    Write-Fail "SIZINTI: gercek config.json release'e gomulmus (_internal\config\config.json) - spec bunu skip etmeli!"
}
Write-OK "Yasakli HF token paterni bulunmadi."

$AiAssetsDir = Join-Path $ProjectRoot "release_assets\ai_models"
# GUNCEL YAPI: model aileleri release_assets\ai_models\ai_hub\<aile>\ altinda (inference_* dahil, ~17 aile).
# Sabit dosya-listesi STALE oluyordu (yeni inference_* modellerini kacirdi) -> DINAMIK dogrulama: her
# aile-dizininde en az bir agirlik (.onnx/.pkl) olmali; yoksa uyar. Yeni model eklenince otomatik kapsanir.
if (Test-Path $AiAssetsDir) {
    $AiHubDir = Join-Path $AiAssetsDir "ai_hub"
    $ModelFamilies = @()
    if (Test-Path $AiHubDir) {
        $ModelFamilies = @(Get-ChildItem $AiHubDir -Directory -ErrorAction SilentlyContinue)
    }
    if ($ModelFamilies.Count -eq 0) {
        Write-Warn "release_assets\ai_models\ai_hub altinda model-aile dizini bulunamadi!"
    }
    foreach ($fam in $ModelFamilies) {
        $weights = @(Get-ChildItem $fam.FullName -Recurse -File -ErrorAction SilentlyContinue |
            Where-Object { $_.Extension -in '.onnx', '.pkl' })
        if ($weights.Count -eq 0) {
            Write-Warn "Model ailesi BOS (agirlik yok): ai_hub\$($fam.Name)"
        }
    }

    $OnnxCount = @(Get-ChildItem $AiAssetsDir -Recurse -File -Filter *.onnx -ErrorAction SilentlyContinue).Count
    $AiSize = (Get-ChildItem $AiAssetsDir -Recurse -File | Measure-Object -Property Length -Sum).Sum
    $AiFiles = (Get-ChildItem $AiAssetsDir -Recurse -File).Count
    Write-OK "AI paketi: $($ModelFamilies.Count) model-aile, $OnnxCount ONNX, $([math]::Round($AiSize / 1MB, 1)) MB ($AiFiles dosya)"
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

    $IssFile = Join-Path $ScriptDir "PEMF_Backend_Setup.iss"
    if (-not (Test-Path $IssFile)) {
        Write-Fail "PEMF_Backend_Setup.iss bulunamadi: $IssFile"
    }

    $InnoOutputDir = Join-Path $ScriptDir "Output"
    if (-not (Test-Path $InnoOutputDir)) {
        New-Item -ItemType Directory -Path $InnoOutputDir | Out-Null
    }

    $startTime2 = Get-Date
    Write-Host "  ISCC modu: $Mode (ModeName=$Mode)" -ForegroundColor DarkGray
    & $IsccExe "/DModeName=$Mode" $IssFile

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
Write-Host "  PyInstaller Ciktisi : dist\PEMF_Backend\" -ForegroundColor White
if (-not $SkipInnoSetup) {
    Write-Host "  Kurulum Dosyasi    : build_tools\Output\PEMFBackendSetup_${Mode}_v$BuildVersion.exe" -ForegroundColor White
    Write-Host ""
    Write-Host "  -> Klinige dagitmak icin: PEMFBackendSetup_${Mode}_v$BuildVersion.exe dosyasini gonderin." -ForegroundColor Cyan
} else {
    Write-Host ""
    Write-Host "  -> Inno Setup kurulumu yapilip tekrar calistirin." -ForegroundColor Yellow
    Write-Host "     Indirme: https://jrsoftware.org/isinfo.php" -ForegroundColor Yellow
}
Write-Host ""
