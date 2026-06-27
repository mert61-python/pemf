# =============================================================================
# PEMF HEADLESS BACKEND — PyInstaller EXE build runner.  Faz 4.
# -----------------------------------------------------------------------------
# Mevcut, kanıtlanmış build ortamına (build_onedir_exe.ps1) uyumlu:
#   * Yorumlayıcı   : -Python > myenv > embeddable  (FRESH venv KURMAZ, indirme YOK)
#   * İzolasyon     : PYTHONNOUSERSITE=1 + PYTHONPATH=""  (Conda/Roaming sızıntısı yok)
#   * Çıktı yolu    : C:\PEMF_BUILD (KISA) — Windows 260-karakter sınırı için
#   * Guard         : önce check_headless_imports.py (KIRMIZI ise build YOK)
#
# Kullanım:
#   .\scripts\build_backend_exe.ps1                 # myenv/embeddable otomatik
#   .\scripts\build_backend_exe.ps1 -Python "...\myenv\Scripts\python.exe"
# Çıktı: C:\PEMF_BUILD\dist\PEMF_Backend\PEMF_Backend.exe
# =============================================================================
param(
    [string]$Python    = "",
    [string]$BuildRoot = "C:\PEMF_BUILD",
    [switch]$SkipGuard
)
$ErrorActionPreference = "Stop"
function Info($m) { Write-Host "[build] $m" -ForegroundColor Cyan }
function Die($m)  { Write-Host "[build] HATA: $m" -ForegroundColor Red; exit 1 }

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$GuiRoot   = Split-Path -Parent $ScriptDir
$EmbRoot   = Split-Path -Parent $GuiRoot     # embeddable python kökü (guii'nin üstü)

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
