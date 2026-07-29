# =============================================================================
# PEMF Vet Mobil — Android APK release build (guii'den tek komut).
# -----------------------------------------------------------------------------
# NEDEN kısa-dizin: Android CMake/ninja, obje dosyası yoluna KAYNAK yolunun
# tamamını gömer (<.cxx>\...\C_\<abs-source-path>\file.cpp.o) → yol ~2 katına
# çıkar. ninja Stat() ANSI Win32 API → 260 sınırını LongPathsEnabled ile bile
# AŞAMAZ. guii derin (58 char) → derleme patlar. Çözüm: kaynağı kısa köke
# (C:\pb, 5 char) AYNALA, orada derle, APK'yı guii'ye geri kopyala.
# KAYNAK guii'de KALIR; C:\pb yalnızca geçici build-scratch'tir.
#
# Kullanım (guii kökünden ya da herhangi bir yerden):
#   .\build_tools\build_apk.ps1                 # C:\pb'ye aynala + assembleRelease + APK'yı geri getir
#   .\build_tools\build_apk.ps1 -Clean          # scratch'i sıfırdan (tam yeniden kopyala)
#   .\build_tools\build_apk.ps1 -ShortDir C:\x  # farklı kısa kök
#   .\build_tools\build_apk.ps1 -RemoveScratch  # build sonrası C:\pb'yi sil (C: temiz kalsın; sonraki build yavaş)
# =============================================================================
param(
    [string]$ShortDir = "C:\pb",
    [switch]$Clean,
    [switch]$RemoveScratch
)
$ErrorActionPreference = "Stop"
function Info($m){ Write-Host "[apk] $m" -ForegroundColor Cyan }
function Die($m){ Write-Host "[apk] HATA: $m" -ForegroundColor Red; exit 1 }

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$GuiRoot   = Split-Path -Parent $ScriptDir
$Pf        = Join-Path $GuiRoot "pf"
if (-not (Test-Path (Join-Path $Pf "android\gradlew.bat"))) { Die "pf\android\gradlew.bat yok: $Pf" }

# ShortDir yeterince kısa mı (aksi halde anlamsız)
if ($ShortDir.Length -gt 12) { Write-Host "[apk] UYARI: kısa-dizin uzun ($ShortDir); MAX_PATH riski sürebilir." -ForegroundColor Yellow }

if ($Clean -and (Test-Path $ShortDir)) { Info "Scratch sıfırlanıyor: $ShortDir"; cmd /c rmdir /s /q "$ShortDir" 2>$null }

# --- 1. Kaynağı kısa köke AYNALA (robocopy /MIR). Regenere-edilebilir + >260 üreten dizinler HARİÇ:
#        .cxx (CMake obje ağacı — kısa kökte TAZE üretilmeli), .gradle (cache), .transforms (355-char dex),
#        build\intermediates\cxx. node_modules'ün ÖN-DERLENMİŞ 'build' JS'i KORUNUR (sadece .cxx/.transforms/.gradle atılır). ---
Info "Kaynak aynalanıyor: $Pf  ->  $ShortDir  (.cxx/.gradle/.transforms hariç)"
$rc = Start-Process robocopy -ArgumentList @(
    "`"$Pf`"", "`"$ShortDir`"", "/MIR", "/MT:16", "/NFL", "/NDL", "/NJH", "/NJS", "/R:1", "/W:1",
    "/XD", ".cxx", ".gradle", ".transforms", ".idea"
) -NoNewWindow -Wait -PassThru
# robocopy exit: <8 = başarı (0=değişiklik yok, 1=kopyalandı, vb.)
if ($rc.ExitCode -ge 8) { Die "robocopy başarısız (exit $($rc.ExitCode))" }
Info "Aynalama tamam (robocopy exit $($rc.ExitCode))."

# --- 2. Kısa kökte assembleRelease ---
$android = Join-Path $ShortDir "android"
$gw = Join-Path $android "gradlew.bat"
Info "assembleRelease çalıştırılıyor: $android"
Push-Location $android
try {
    & $gw --stop 2>&1 | Out-Null
    & $gw assembleRelease --console=plain
    $code = $LASTEXITCODE
} finally { Pop-Location }
if ($code -ne 0) { Die "gradle assembleRelease başarısız (exit $code)" }

# --- 3. APK'yı guii\release_assets'e geri getir ---
$apk = Join-Path $android "app\build\outputs\apk\release\app-release.apk"
if (-not (Test-Path $apk)) { Die "APK üretilemedi: $apk" }
$destDir = Join-Path $GuiRoot "release_assets"
if (-not (Test-Path $destDir)) { New-Item -ItemType Directory -Path $destDir | Out-Null }
$dest = Join-Path $destDir "PEMF_Vet_Mobil.apk"
Copy-Item $apk $dest -Force
$mb = [math]::Round((Get-Item $dest).Length/1MB,1)
Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "  APK HAZIR ($mb MB)" -ForegroundColor Green
Write-Host "  $dest" -ForegroundColor White
Write-Host "============================================" -ForegroundColor Green

if ($RemoveScratch) { Info "Scratch siliniyor (C: temiz): $ShortDir"; cmd /c rmdir /s /q "$ShortDir" 2>$null }
else { Info "Scratch korundu ($ShortDir) — sonraki build hızlı (incremental). Silmek için -RemoveScratch." }