# =============================================================================
# PEMF HEADLESS BACKEND — PyInstaller EXE build runner.  Faz 4.
# -----------------------------------------------------------------------------
# Mevcut, kanıtlanmış build ortamına (build_onedir_exe.ps1) uyumlu:
#   * Yorumlayıcı   : -Python > myenv > embeddable  (FRESH venv KURMAZ, indirme YOK)
#   * İzolasyon     : PYTHONNOUSERSITE=1 + PYTHONPATH=""  (Conda/Roaming sızıntısı yok)
#   * Çıktı yolu    : guii\PEMF_BUILD (VARSAYILAN, tek-yer + taşınabilir).
#                     En uzun yol ~238<260 + LongPathsEnabled=1. Derin hedefte
#                     MAX_PATH riski olursa: -BuildRoot C:\PEMF_BUILD (kısa) ile override.
#   * Guard         : önce check_headless_imports.py (KIRMIZI ise build YOK)
#
# Kullanım:
#   .\scripts\build_backend_exe.ps1                 # myenv/embeddable otomatik, çıktı guii\PEMF_BUILD
#   .\scripts\build_backend_exe.ps1 -Python "...\myenv\Scripts\python.exe"
#   .\scripts\build_backend_exe.ps1 -BuildRoot C:\PEMF_BUILD   # MAX_PATH kaçışı (derin/uzun hedef)
# Çıktı: <BuildRoot>\dist\PEMF_Backend\PEMF_Backend.exe  (varsayılan guii\PEMF_BUILD\...)
# =============================================================================
param(
    [string]$Python    = "",
    [string]$BuildRoot = "",
    [switch]$SkipGuard,
    [switch]$SkipWeb
)
$ErrorActionPreference = "Stop"
function Info($m) { Write-Host "[build] $m" -ForegroundColor Cyan }
function Die($m)  { Write-Host "[build] HATA: $m" -ForegroundColor Red; exit 1 }

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$GuiRoot   = Split-Path -Parent $ScriptDir
$EmbRoot   = Split-Path -Parent $GuiRoot     # embeddable python kökü (guii'nin üstü)

# --- Çıktı kökü: boşsa guii\PEMF_BUILD (tek-yer + taşınabilir). Derin hedefte -BuildRoot ile kısa yol verilebilir. ---
if (-not $BuildRoot) { $BuildRoot = Join-Path $GuiRoot "PEMF_BUILD" }
Info "Build kökü: $BuildRoot"

# --- 1. Yorumlayıcı seç: -Python > myenv (guii veya üst) > embeddable ---
$cands = @()
if ($Python) { $cands += $Python }
$cands += (Join-Path $GuiRoot "myenv\Scripts\python.exe")
$cands += (Join-Path $EmbRoot "myenv\Scripts\python.exe")
$cands += (Join-Path $EmbRoot "python.exe")          # embeddable
$PY = $cands | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
if (-not $PY) { Die "Build için Python bulunamadı (myenv/embeddable). -Python ile belirtin." }
Info "Yorumlayıcı: $PY"
& $PY --version

# --- 2. İzolasyon (build_onedir_exe.ps1 ile aynı) ---
$env:PYTHONNOUSERSITE = "1"
$env:PYTHONPATH       = ""

Set-Location $GuiRoot

# --- 3. Guard-check (Qt sızıntısı) ---
if (-not $SkipGuard) {
    Info "Headless guard-check çalıştırılıyor..."
    & $PY "scripts\check_headless_imports.py"
    if ($LASTEXITCODE -ne 0) { Die "Guard KIRMIZI — backend'e Qt sızmış. Build durduruldu." }
    Info "Guard YEŞİL — backend Qt-free."
}

# --- 4. PyInstaller var mı? ---
& $PY -c "import PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) {
    Info "PyInstaller yok, kuruluyor (küçük)..."
    & $PY -m pip install pyinstaller
    if ($LASTEXITCODE -ne 0) { Die "PyInstaller kurulamadı." }
}

# --- 4.5. React (Expo) WEB EXPORT — backend EXE'sinin sunacağı web UI'yi TAZE üret ---
# Spec (PEMF_Backend_onedir.spec:138-141) frontend\dist'i _internal\frontend\dist'e bundle'lar
# ve FastAPI '/' kökünden serve eder. build_installer.ps1 OLMADAN bu script ile build edilince
# web export TAZE üretilmezse EXE eski/eksik web içerir → STM takip web'de açılmaz (sessiz bug).
# Bu adım, build_installer.ps1'deki 'React Frontend Web Export' bölümünü (out: frontend\dist) REPLİKE eder.
$FrontendDir = Join-Path $GuiRoot "frontend"
if ($SkipWeb) {
    $FrontendIndex = Join-Path $FrontendDir "dist\index.html"
    if (-not (Test-Path $FrontendIndex)) {
        Die "-SkipWeb verildi ama mevcut web export yok ($FrontendIndex). Önce -SkipWeb'siz çalıştırın."
    }
    Info "Web export ATLANDI (-SkipWeb) — mevcut frontend\dist kullanılacak."
} else {
    Info "React (Expo) web export üretiliyor (backend bunu localhost:8000'de sunacak)..."
    if (-not (Test-Path $FrontendDir)) { Die "frontend\ klasörü bulunamadı: $FrontendDir" }

    # npm / npx zorunlu (web build edilemezse GÜR-sesle fail)
    $npmCmd = Get-Command npm -ErrorAction SilentlyContinue
    if (-not $npmCmd) { Die "npm bulunamadı. React web export için Node.js/npm gerekli (web zorunlu)." }
    $npxCmd = Get-Command npx -ErrorAction SilentlyContinue
    if (-not $npxCmd) { Die "npx bulunamadı. Expo web export için npx gerekli (web zorunlu)." }

    Push-Location $FrontendDir
    try {
        # Idempotent: eski dist'i temizle ki bayat dosya kalmasın
        $FrontendDistDir = Join-Path $FrontendDir "dist"
        if (Test-Path $FrontendDistDir) {
            Info "Eski frontend\dist temizleniyor..."
            Remove-Item $FrontendDistDir -Recurse -Force
        }

        # Bağımlılık kurulumu (build_installer.ps1 ile aynı: ci varsa ci, yoksa install)
        if (Test-Path "package-lock.json") {
            Info "Frontend bağımlılıkları yükleniyor (npm ci --legacy-peer-deps)..."
            & npm ci --legacy-peer-deps
        } else {
            Info "package-lock.json yok; npm install --legacy-peer-deps kullanılıyor."
            & npm install --legacy-peer-deps
        }
        if ($LASTEXITCODE -ne 0) { Die "Frontend npm bağımlılık kurulumu başarısız!" }

        Info "Typecheck çalıştırılıyor (npm run typecheck)..."
        & npm run typecheck
        if ($LASTEXITCODE -ne 0) { Die "npm run typecheck başarısız! (TypeScript hatalarını düzeltin)" }

        Info "Expo web export alınıyor (npx expo export --platform web)..."
        $env:EXPO_ROUTER_DISABLE_RN_NAVIGATION_CHECK = "1"
        & npx expo export --platform web
        if ($LASTEXITCODE -ne 0) { Die "Expo web export başarısız!" }
    } finally {
        Pop-Location
    }

    # DOĞRULAMA: spec'in topladığı tam yol (frontend\dist) üretilmiş mi?
    $FrontendIndex = Join-Path $FrontendDir "dist\index.html"
    if (-not (Test-Path $FrontendIndex)) {
        Die "frontend\dist\index.html üretilemedi! React web export hatalı."
    }
    $FrontendJsDir = Join-Path $FrontendDir "dist\_expo\static\js\web"
    $FrontendJsFiles = @()
    if (Test-Path $FrontendJsDir) {
        $FrontendJsFiles = Get-ChildItem $FrontendJsDir -Filter "*.js" -File -ErrorAction SilentlyContinue
    }
    if ($FrontendJsFiles.Count -eq 0) {
        Die "frontend\dist\_expo\static\js\web altında JS bundle yok! React export eksik."
    }

    # version.json (build_installer.ps1 ile parite) — VERSION dosyasından
    $VersionFile = Join-Path $GuiRoot "VERSION"
    $AppVersion = if (Test-Path $VersionFile) { (Get-Content -Path $VersionFile -Raw).Trim() } else { "0.0.0" }
    $FrontendVersionJson = @{
        version = $AppVersion
        builtAt = (Get-Date).ToString("o")
    } | ConvertTo-Json
    Set-Content -Path (Join-Path $FrontendDir "dist\version.json") -Value $FrontendVersionJson -Encoding UTF8

    Info "Web export tamamlandı ve doğrulandı → frontend\dist (sürüm $AppVersion)."
}

# --- 5. Build — KISA yola (260-karakter sınırı) ---
$dist = Join-Path $BuildRoot "dist"
$work = Join-Path $BuildRoot "build"
if (-not (Test-Path $BuildRoot)) { New-Item -ItemType Directory -Path $BuildRoot | Out-Null }
Info "PyInstaller build → $dist"
$t0 = Get-Date
& $PY -m PyInstaller "build_tools\PEMF_Backend_onedir.spec" --noconfirm --distpath $dist --workpath $work
if ($LASTEXITCODE -ne 0) { Die "PyInstaller build başarısız (log'a bakın)." }
$dt = (Get-Date) - $t0

$exe = Join-Path $dist "PEMF_Backend\PEMF_Backend.exe"
if (Test-Path $exe) {
    $mb = [math]::Round((Get-Item $exe).Length / 1MB, 1)
    Write-Host ""
    Write-Host "============================================" -ForegroundColor Green
    Write-Host "  ✓ Headless backend EXE hazır ($($dt.Minutes)dk $($dt.Seconds)sn)" -ForegroundColor Green
    Write-Host "============================================" -ForegroundColor Green
    Write-Host "  $exe  ($mb MB)" -ForegroundColor White
    Write-Host ""
    Write-Host "Test (Python'suz çalışmalı):  $exe --port 8000" -ForegroundColor Cyan
    Write-Host "Servis: install_backend_service.ps1 bu yolu otomatik bulur." -ForegroundColor Cyan
} else {
    Die "Build bitti ama EXE yok: $exe"
}
