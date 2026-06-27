# ============================================================================
# PEMF GUI - ONE-DIR EXE BUILD SCRIPT (EMBEDDED PYTHON - ISOLATED)
# ============================================================================

Write-Host "=" * 80 -ForegroundColor Cyan
Write-Host "PEMF GUI - ONE-DIR EXE BUILD SCRIPT (EMBEDDED PYTHON - ISOLATED)" -ForegroundColor Yellow
Write-Host "=" * 80 -ForegroundColor Cyan

# 1. Proje ana dizinine git
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

Write-Host "`n[1/6] Proje dizini dogrulanadi:" -ForegroundColor Green
Write-Host $projectRoot -ForegroundColor Gray

# 2.5 ROAMING (USER SITE) KLASÖRÜNÜ IPTAL ET (KRITIK!)
$env:PYTHONNOUSERSITE = "1"
$env:PYTHONPATH = ""
Write-Host "[OK] PYTHONNOUSERSITE aktif edildi (Roaming sizintisi engellendi)." -ForegroundColor Green

# 3. myenv varlik kontrolu
$myenvPath = Join-Path $projectRoot "myenv"
if (-not (Test-Path $myenvPath)) {
    # Embedded Python kurulumlarında myenv bir üst dizinde olabilir
    $myenvPath = Join-Path (Split-Path -Parent $projectRoot) "myenv"
    if (-not (Test-Path $myenvPath)) {
        Write-Host "`n[HATA] myenv sanal ortami bulunamadi ne projede ne de bir ust dizinde!" -ForegroundColor Red
        Write-Host "Once myenv olusturmalisiniz:" -ForegroundColor Yellow
        Write-Host "  python -m venv myenv" -ForegroundColor White
        exit 1
    }
}

# 4. myenv'i aktif et
Write-Host "`n[3/6] myenv sanal ortami saf modda aktif ediliyor..." -ForegroundColor Green
$activateScript = Join-Path $myenvPath "Scripts\Activate.ps1"
& $activateScript

$currentPython = (Get-Command python).Source
Write-Host "[OK] Aktif Python Yolu: $currentPython" -ForegroundColor Green

if ($currentPython -notlike "*myenv*") {
    Write-Host "`n[HATA] myenv aktif edilemedi! PyInstaller Conda'yi gormeye devam edecektir. Cikiliyor." -ForegroundColor Red
    exit 1
}

# 5. PyQt6-WebEngine on kontrolu
Write-Host "`n[4/8] PyQt6-WebEngine modulu kontrol ediliyor..." -ForegroundColor Green
& python -c "import PyQt6.QtWebEngineWidgets, PyQt6.QtWebEngineCore" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "[HATA] PyQt6-WebEngine bu ortamda kurulu degil." -ForegroundColor Red
    Write-Host "Cozum: myenv aktifken su komutu calistirin:" -ForegroundColor Yellow
    Write-Host "  pip install PyQt6-WebEngine" -ForegroundColor White
    exit 1
}
Write-Host "[OK] PyQt6-WebEngine modulu bulundu." -ForegroundColor Green

# 6. Simulatoru Otomatik Build Et
Write-Host "`n[5/8] Simulator statik dosyalari hazirlaniyor (NPM Build)..." -ForegroundColor Green
$simDirItem = Get-ChildItem -Path $projectRoot -Directory -Force -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -like "dema-terapi-sim*" } |
    Select-Object -First 1

if ($simDirItem) {
    $simDir = $simDirItem.FullName
    Push-Location $simDir
    Write-Host "  -> npm install calistiriliyor..." -ForegroundColor DarkGray
    & npm install | Out-Null
    Write-Host "  -> npm run build calistiriliyor..." -ForegroundColor DarkGray
    & npm run build | Out-Null
    Pop-Location
    Write-Host "[OK] Simulator basariyla derlendi: $($simDirItem.Name)" -ForegroundColor Green
} else {
    Write-Host "[UYARI] Simulator klasoru bulunamadi, atlaniyor." -ForegroundColor Yellow
}

# 7. Eski build/dist temizligi
# NOT: Dataset klasor isimleri cok uzun oldugu icin Windows 260 karakter sinirini asiyor.
# Bu nedenle dist ve build C:\PEMF_BUILD gibi kisa bir yolda tutulmali.
$guiRoot = Join-Path $projectRoot "guii"
$shortBuildRoot = "C:\PEMF_BUILD"
$shortDist = Join-Path $shortBuildRoot "dist"
$shortWork = Join-Path $shortBuildRoot "build"

if (-not (Test-Path $shortBuildRoot)) {
    New-Item -ItemType Directory -Path $shortBuildRoot | Out-Null
}

Write-Host "`n[6/8] Eski build dosyalari temizleniyor..." -ForegroundColor Green
Stop-Process -Name "PEMF_GUI" -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1

try {
    if (Test-Path $shortWork) { Remove-Item -Recurse -Force $shortWork -ErrorAction Stop | Out-Null }
    if (Test-Path $shortDist) { Remove-Item -Recurse -Force $shortDist -ErrorAction Stop | Out-Null }
    Write-Host "[OK] Temizlendi." -ForegroundColor Green
} catch {
    Write-Host "[HATA] Klasorler temizlenirken sorun olustu: $_" -ForegroundColor Yellow
    Write-Host "Arka planda acik bir dosya veya terminal olabilir, isleme devam ediliyor..." -ForegroundColor DarkGray
}

# 8. PyInstaller calistir
Write-Host "`n[7/8] PyInstaller ile EXE olusturuluyor..." -ForegroundColor Green
Write-Host "Cikti klasoru: $shortDist" -ForegroundColor Yellow
Write-Host "=" * 80 -ForegroundColor Cyan

$specFile = "build_tools\PEMF_GUI_onedir.spec"

$startTime = Get-Date

# We are already in projectRoot, so no need to change dir
& python -m PyInstaller --clean --noconfirm --distpath $shortDist --workpath $shortWork $specFile

$endTime = Get-Date
$duration = $endTime - $startTime

Write-Host "`n" + ("=" * 80) -ForegroundColor Cyan

if ($LASTEXITCODE -eq 0) {
    Write-Host "BUILD BASARILI!" -ForegroundColor Green
    Write-Host "Sure: $($duration.Minutes) dakika $($duration.Seconds) saniye" -ForegroundColor Cyan

    $exePath = Join-Path $shortDist "PEMF_GUI\PEMF_GUI.exe"
    if (Test-Path $exePath) {
        $exeSize = (Get-Item $exePath).Length / 1MB
        Write-Host "EXE Boyutu: $([math]::Round($exeSize, 2)) MB" -ForegroundColor Cyan
        Write-Host "Konum: $exePath" -ForegroundColor Yellow
    }
} else {
    Write-Host "BUILD BASARISIZ!" -ForegroundColor Red
}

Write-Host "`n" + ("=" * 80) -ForegroundColor Cyan
Write-Host "[8/8] Islem tamamlandi." -ForegroundColor Green
