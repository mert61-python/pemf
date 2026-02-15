# ============================================================================
# PEMF GUI - Build Script (myenv sanal ortamından)
# ============================================================================
# Bu script, proje dizinindeki myenv sanal ortamını kullanarak
# PyInstaller ile exe oluşturur.
# ============================================================================

Write-Host "=" * 80 -ForegroundColor Cyan
Write-Host "PEMF GUI - EXE BUILD SCRIPT" -ForegroundColor Yellow
Write-Host "=" * 80 -ForegroundColor Cyan

# Proje ana dizinine git
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

Write-Host "`n[1/5] Proje dizini kontrol ediliyor..." -ForegroundColor Green
Write-Host "Konum: $projectRoot" -ForegroundColor Gray

# myenv varlık kontrolü
$myenvPath = Join-Path $projectRoot "myenv"
if (-not (Test-Path $myenvPath)) {
    Write-Host "`n[HATA] myenv sanal ortamı bulunamadı!" -ForegroundColor Red
    Write-Host "Konum: $myenvPath" -ForegroundColor Gray
    Write-Host "`nÇözüm:" -ForegroundColor Yellow
    Write-Host "  python -m venv myenv" -ForegroundColor White
    Write-Host "  .\myenv\Scripts\Activate.ps1" -ForegroundColor White
    Write-Host "  pip install -r requirements.txt" -ForegroundColor White
    exit 1
}
Write-Host "[OK] myenv bulundu" -ForegroundColor Green

# myenv'i aktif et
Write-Host "`n[2/5] myenv sanal ortamı aktif ediliyor..." -ForegroundColor Green
$activateScript = Join-Path $myenvPath "Scripts\Activate.ps1"

if (-not (Test-Path $activateScript)) {
    Write-Host "[HATA] Activate.ps1 bulunamadı!" -ForegroundColor Red
    exit 1
}

# Aktif Python'u göster
Write-Host "Önceki Python:" (Get-Command python -ErrorAction SilentlyContinue).Source -ForegroundColor Gray

& $activateScript

$currentPython = (Get-Command python).Source
Write-Host "[OK] Aktif Python: $currentPython" -ForegroundColor Green

# Python ortamının myenv olduğunu doğrula
if ($currentPython -notlike "*myenv*") {
    Write-Host "`n[UYARI] Python myenv'den değil!" -ForegroundColor Yellow
    Write-Host "Devam etmek istiyor musunuz? (E/H)" -ForegroundColor Yellow
    $response = Read-Host
    if ($response -ne "E" -and $response -ne "e") {
        exit 1
    }
}

# PyInstaller kontrolü
Write-Host "`n[3/5] PyInstaller kontrol ediliyor..." -ForegroundColor Green
try {
    $pyinstallerVersion = & python -m PyInstaller --version 2>&1
    Write-Host "[OK] PyInstaller versiyon: $pyinstallerVersion" -ForegroundColor Green
} catch {
    Write-Host "[HATA] PyInstaller bulunamadı!" -ForegroundColor Red
    Write-Host "Kuruluyor..." -ForegroundColor Yellow
    & pip install pyinstaller
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[HATA] PyInstaller kurulamadı!" -ForegroundColor Red
        exit 1
    }
}

# Eski build dosyalarını temizle
Write-Host "`n[4/5] Eski build dosyaları temizleniyor..." -ForegroundColor Green
$buildDir = Join-Path $projectRoot "build"
$distDir = Join-Path $projectRoot "dist"

if (Test-Path $buildDir) {
    Remove-Item -Recurse -Force $buildDir
    Write-Host "[OK] build/ klasörü temizlendi" -ForegroundColor Gray
}

if (Test-Path $distDir) {
    Remove-Item -Recurse -Force $distDir
    Write-Host "[OK] dist/ klasörü temizlendi" -ForegroundColor Gray
}

# PyInstaller çalıştır
Write-Host "`n[5/5] PyInstaller ile exe oluşturuluyor..." -ForegroundColor Green
Write-Host "Bu işlem 5-10 dakika sürebilir..." -ForegroundColor Yellow
Write-Host "=" * 80 -ForegroundColor Cyan

$specFile = Join-Path $projectRoot "build_tools\PEMF_GUI.spec"
$startTime = Get-Date

& python -m PyInstaller --clean --noconfirm $specFile

$endTime = Get-Date
$duration = $endTime - $startTime

Write-Host "`n" + ("=" * 80) -ForegroundColor Cyan

if ($LASTEXITCODE -eq 0) {
    Write-Host "BUILD BAŞARILI!" -ForegroundColor Green
    Write-Host "`nSüre: $($duration.Minutes) dakika $($duration.Seconds) saniye" -ForegroundColor Cyan
    
    $exePath = Join-Path $distDir "PEMF_GUI.exe"
    if (Test-Path $exePath) {
        $exeSize = (Get-Item $exePath).Length / 1MB
        Write-Host "EXE Boyutu: $([math]::Round($exeSize, 2)) MB" -ForegroundColor Cyan
        Write-Host "`nKonum: $exePath" -ForegroundColor Yellow
        
        # Test çalıştırma önerisi
        Write-Host "`nTest etmek için:" -ForegroundColor White
        Write-Host "  cd dist" -ForegroundColor Gray
        Write-Host "  .\PEMF_GUI.exe" -ForegroundColor Gray
        
    } else {
        Write-Host "[UYARI] EXE dosyası bulunamadı: $exePath" -ForegroundColor Yellow
    }
} else {
    Write-Host "BUILD BAŞARISIZ!" -ForegroundColor Red
    Write-Host "`nHata kodu: $LASTEXITCODE" -ForegroundColor Red
    Write-Host "Log dosyasını kontrol edin: build/PEMF_GUI/" -ForegroundColor Yellow
    exit $LASTEXITCODE
}

Write-Host "`n" + ("=" * 80) -ForegroundColor Cyan
Write-Host "İşlem tamamlandı." -ForegroundColor Green
