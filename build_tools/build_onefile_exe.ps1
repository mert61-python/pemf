# ============================================================================
# PEMF GUI - ONE-FILE EXE BUILD SCRIPT (EMBEDDED PYTHON - ISOLATED)
# ============================================================================
# Bu script, PyInstaller'ın Conda kütüphanelerini yanlışlıkla projeye
# dahil etmesini (bloat & freeze sorununu) kökten çözer.
# ============================================================================

Write-Host "=" * 80 -ForegroundColor Cyan
Write-Host "PEMF GUI - ONE-FILE EXE BUILD SCRIPT (EMBEDDED PYTHON - ISOLATED)" -ForegroundColor Yellow
Write-Host "=" * 80 -ForegroundColor Cyan

# 1. Proje ana dizinine git
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

Write-Host "`n[1/6] Proje dizini doğrulandı:" -ForegroundColor Green
Write-Host $projectRoot -ForegroundColor Gray

# [IPTAL EDILDI: Conda PATH silme işlemi]
# Çünkü 'myenv' Conda tabanlı olduğu için Conda'nın DLL'lerine (Library\bin) ihtiyaç duyuyor!
# Silinirse Cryptography (libcrypto, libssl vb.) çöker ve PyInstaller paketi atlar.
# Zaten PYTHONNOUSERSITE ile izolasyonu sağladık.

# 2.5 ROAMING (USER SITE) KLASÖRÜNÜ İPTAL ET (KRİTİK!)
# Kullanıcının AppData\Roaming içindeki bozuk Python314 modüllerinin myenv'e sızmasını önler
$env:PYTHONNOUSERSITE = "1"
$env:PYTHONPATH = ""
Write-Host "[OK] PYTHONNOUSERSITE aktif edildi (Roaming sızıntısı engellendi)." -ForegroundColor Green

# 3. myenv varlık kontrolü
$myenvPath = Join-Path $projectRoot "myenv"
if (-not (Test-Path $myenvPath)) {
    # Embedded Python kurulumlarında myenv bir üst dizinde olabilir
    $myenvPath = Join-Path (Split-Path -Parent $projectRoot) "myenv"
    if (-not (Test-Path $myenvPath)) {
        Write-Host "`n[HATA] myenv sanal ortamı bulunamadı ne projede ne de bir üst dizinde!" -ForegroundColor Red
        Write-Host "Önce myenv oluşturmalısınız:" -ForegroundColor Yellow
        Write-Host "  python -m venv myenv" -ForegroundColor White
        exit 1
    }
}

# 4. myenv'i aktif et
Write-Host "`n[3/6] myenv sanal ortamı saf modda aktif ediliyor..." -ForegroundColor Green
$activateScript = Join-Path $myenvPath "Scripts\Activate.ps1"
& $activateScript

$currentPython = (Get-Command python).Source
Write-Host "[OK] Aktif Python Yolu: $currentPython" -ForegroundColor Green

if ($currentPython -notlike "*myenv*") {
    Write-Host "`n[HATA] myenv aktif edilemedi! PyInstaller Conda'yı görmeye devam edecektir. Çıkılıyor." -ForegroundColor Red
    exit 1
}

# 5. PyQt6-WebEngine ön kontrolü
Write-Host "`n[4/8] PyQt6-WebEngine modülü kontrol ediliyor..." -ForegroundColor Green
& python -c "import PyQt6.QtWebEngineWidgets, PyQt6.QtWebEngineCore" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "[HATA] PyQt6-WebEngine bu ortamda kurulu değil. EXE simülatörü çalışmaz." -ForegroundColor Red
    Write-Host "Çözüm: myenv aktifken şu komutu çalıştırın:" -ForegroundColor Yellow
    Write-Host "  pip install PyQt6-WebEngine" -ForegroundColor White
    exit 1
}
Write-Host "[OK] PyQt6-WebEngine modülü bulundu." -ForegroundColor Green

# 6. Simülatörü Otomatik Build Et
Write-Host "`n[5/8] Simülatör statik dosyaları hazırlanıyor (NPM Build)..." -ForegroundColor Green
$simDir = Join-Path $projectRoot "dema-terapi-simülatörü"
if (Test-Path $simDir) {
    Push-Location $simDir
    Write-Host "  -> npm install çalıştırılıyor..." -ForegroundColor DarkGray
    & npm install | Out-Null
    Write-Host "  -> npm run build çalıştırılıyor..." -ForegroundColor DarkGray
    & npm run build | Out-Null
    Pop-Location
    Write-Host "[OK] Simülatör başarıyla derlendi." -ForegroundColor Green
} else {
    Write-Host "[UYARI] Simülatör klasörü bulunamadı, atlanıyor." -ForegroundColor Yellow
}

# 7. Eski build/dist temizliği
Write-Host "`n[6/8] Eski build dosyaları temizleniyor..." -ForegroundColor Green
# Eğer uygulamanın kendisi çalışıyorsa, silmeyi engellememesi için kapat
Stop-Process -Name "PEMF_GUI" -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1

$buildDir = Join-Path $projectRoot "build"
$distDir = Join-Path $projectRoot "dist"

try {
    if (Test-Path $buildDir) { Remove-Item -Recurse -Force $buildDir -ErrorAction Stop | Out-Null }
    if (Test-Path $distDir) { Remove-Item -Recurse -Force $distDir -ErrorAction Stop | Out-Null }
    Write-Host "[OK] Temizlendi." -ForegroundColor Green
} catch {
    Write-Host "[HATA] Klasör temizlenemedi: $_" -ForegroundColor Yellow
    Write-Host "Arka planda açık bir program veya VSCode terminali olabilir. İşleme devam ediliyor..." -ForegroundColor DarkGray
}

# 8. PyInstaller çalıştır
Write-Host "`n[7/8] PyInstaller ile EXE oluşturuluyor..." -ForegroundColor Green
Write-Host "Bu işlem saf myenv kullanıldığı için daha hızlı sürecektir..." -ForegroundColor Yellow
Write-Host "=" * 80 -ForegroundColor Cyan

$specFile = Join-Path $projectRoot "build_tools\PEMF_GUI_onefile.spec"
$startTime = Get-Date

# Noconfirm ile spec dosyasından derle
& python -m PyInstaller --clean --noconfirm $specFile

$endTime = Get-Date
$duration = $endTime - $startTime

Write-Host "`n" + ("=" * 80) -ForegroundColor Cyan

if ($LASTEXITCODE -eq 0) {
    Write-Host "BUILD BAŞARILI! (SAF VE İZOLE)" -ForegroundColor Green
    Write-Host "Süre: $($duration.Minutes) dakika $($duration.Seconds) saniye" -ForegroundColor Cyan
    
    $exePath = Join-Path $distDir "PEMF_GUI_OneFile.exe"
    if (Test-Path $exePath) {
        $exeSize = (Get-Item $exePath).Length / 1MB
        Write-Host "EXE Boyutu: $([math]::Round($exeSize, 2)) MB (Eskisinden daha küçük olmalı!)" -ForegroundColor Cyan
        Write-Host "Konum: $exePath" -ForegroundColor Yellow
    }
} else {
    Write-Host "BUILD BAŞARISIZ!" -ForegroundColor Red
}

Write-Host "`n" + ("=" * 80) -ForegroundColor Cyan
Write-Host "[8/8] İşlem tamamlandı." -ForegroundColor Green
