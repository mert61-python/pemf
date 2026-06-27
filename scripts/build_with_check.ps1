# Digital Twin Build Pre-Check Script
# Exe build yapmadan once buildPEMF klasorunu dogrula

Write-Host "======================================" -ForegroundColor Cyan
Write-Host "PEMF DIGITAL TWIN BUILD HAZIRLIK" -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""

$buildPemfPath = "buildPEMF"
$criticalFiles = @(
    "PEMF.exe",
    "UnityPlayer.dll",
    "PEMF_Data"
)

# 1. buildPEMF klasoru kontrolu
Write-Host "[1] buildPEMF klasoru kontrol ediliyor..." -ForegroundColor Yellow

if (Test-Path $buildPemfPath) {
    Write-Host "    [OK] buildPEMF klasoru mevcut" -ForegroundColor Green
    
    # Kritik dosyalari kontrol et
    $allFilesExist = $true
    foreach ($file in $criticalFiles) {
        $fullPath = Join-Path $buildPemfPath $file
        if (Test-Path $fullPath) {
            Write-Host "    [OK] $file mevcut" -ForegroundColor Green
            
            # Dosya boyutunu goster
            if (Test-Path $fullPath -PathType Leaf) {
                $size = (Get-Item $fullPath).Length
                $sizeMB = [math]::Round($size / 1MB, 2)
                Write-Host "         Boyut: $sizeMB MB" -ForegroundColor Gray
            }
        } else {
            Write-Host "    [HATA] $file BULUNAMADI!" -ForegroundColor Red
            $allFilesExist = $false
        }
    }
    
    if (-not $allFilesExist) {
        Write-Host ""
        Write-Host "UYARI: Kritik dosyalar eksik!" -ForegroundColor Red
        Write-Host "Unity'den yeniden build almaniz gerekebilir." -ForegroundColor Red
        Write-Host ""
        Write-Host "Yine de devam etmek istiyor musunuz? (E/H)" -ForegroundColor Yellow
        $response = Read-Host
        if ($response -ne "E" -and $response -ne "e") {
            Write-Host "Build islemi iptal edildi." -ForegroundColor Red
            exit 1
        }
    }
} else {
    Write-Host "    [HATA] buildPEMF klasoru BULUNAMADI!" -ForegroundColor Red
    Write-Host ""
    Write-Host "Digital Twin calismayacaktir!" -ForegroundColor Red
    Write-Host "Unity'den build alin ve 'buildPEMF' olarak adlandirin." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Yine de devam etmek istiyor musunuz? (E/H)" -ForegroundColor Yellow
    $response = Read-Host
    if ($response -ne "E" -and $response -ne "e") {
        Write-Host "Build islemi iptal edildi." -ForegroundColor Red
        exit 1
    }
}

Write-Host ""

# 2. myenv aktivasyon kontrolu
Write-Host "[2] Python ortami kontrol ediliyor..." -ForegroundColor Yellow

if ($env:VIRTUAL_ENV) {
    Write-Host "    [OK] Virtual environment aktif: $env:VIRTUAL_ENV" -ForegroundColor Green
} else {
    Write-Host "    [UYARI] Virtual environment aktif degil!" -ForegroundColor Yellow
    Write-Host "    myenv aktivasyonu icin: .\myenv\Scripts\Activate.ps1" -ForegroundColor Gray
    Write-Host ""
    Write-Host "myenv'i aktivasyon yapmak istiyor musunuz? (E/H)" -ForegroundColor Yellow
    $response = Read-Host
    if ($response -eq "E" -or $response -eq "e") {
        if (Test-Path "myenv\Scripts\Activate.ps1") {
            Write-Host "    myenv aktivasyonu yapiliyor..." -ForegroundColor Cyan
            & ".\myenv\Scripts\Activate.ps1"
        } else {
            Write-Host "    [HATA] myenv\Scripts\Activate.ps1 bulunamadi!" -ForegroundColor Red
            exit 1
        }
    }
}

Write-Host ""

# 3. PyInstaller kontrolu
Write-Host "[3] PyInstaller kontrol ediliyor..." -ForegroundColor Yellow

try {
    $pyinstallerVersion = & python -m PyInstaller --version 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "    [OK] PyInstaller yuklu: $pyinstallerVersion" -ForegroundColor Green
    } else {
        throw "PyInstaller bulunamadi"
    }
} catch {
    Write-Host "    [HATA] PyInstaller yuklu degil!" -ForegroundColor Red
    Write-Host "    Kurulum icin: pip install pyinstaller" -ForegroundColor Gray
    Write-Host ""
    Write-Host "PyInstaller'i kurmak istiyor musunuz? (E/H)" -ForegroundColor Yellow
    $response = Read-Host
    if ($response -eq "E" -or $response -eq "e") {
        Write-Host "    PyInstaller kuruluyor..." -ForegroundColor Cyan
        & pip install pyinstaller
    } else {
        exit 1
    }
}

Write-Host ""

# 4. Spec dosyasi kontrolu
Write-Host "[4] PEMF_GUI.spec kontrol ediliyor..." -ForegroundColor Yellow

if (Test-Path "PEMF_GUI.spec") {
    Write-Host "    [OK] PEMF_GUI.spec mevcut" -ForegroundColor Green
    
    # buildPEMF tanimli mi?
    $specContent = Get-Content "PEMF_GUI.spec" -Raw
    if ($specContent -match "buildPEMF") {
        Write-Host "    [OK] buildPEMF spec dosyasinda tanimli" -ForegroundColor Green
    } else {
        Write-Host "    [HATA] buildPEMF spec dosyasinda TANIMLI DEGIL!" -ForegroundColor Red
        Write-Host "    PEMF_GUI.spec dosyasini duzenleyin:" -ForegroundColor Yellow
        Write-Host "    datas.append(('buildPEMF', 'buildPEMF'))" -ForegroundColor Gray
        exit 1
    }
} else {
    Write-Host "    [HATA] PEMF_GUI.spec BULUNAMADI!" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "======================================" -ForegroundColor Cyan
Write-Host "TUM KONTROLLER BASARILI!" -ForegroundColor Green
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Build komutunu calistirmak icin:" -ForegroundColor Yellow
Write-Host "    pyinstaller PEMF_GUI.spec --clean" -ForegroundColor White
Write-Host ""
Write-Host "Build'i simdi baslatmak istiyor musunuz? (E/H)" -ForegroundColor Yellow
$response = Read-Host

if ($response -eq "E" -or $response -eq "e") {
    Write-Host ""
    Write-Host "Build baslatiliyor..." -ForegroundColor Cyan
    Write-Host "======================================" -ForegroundColor Cyan
    Write-Host ""
    
    & pyinstaller PEMF_GUI.spec --clean
    
    Write-Host ""
    Write-Host "======================================" -ForegroundColor Cyan
    Write-Host "BUILD TAMAMLANDI!" -ForegroundColor Green
    Write-Host "======================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Exe konumu: dist\PEMF_GUI.exe" -ForegroundColor Yellow
    Write-Host ""
} else {
    Write-Host "Build islemi iptal edildi." -ForegroundColor Yellow
}
