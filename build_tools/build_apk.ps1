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

# TEK KAYNAK: versions.json -> pf\app.json (version, versionCode, buildNumber).
# Aynalamadan ÖNCE çalışmalı, yoksa C:\pb'ye eski sürüm kopyalanır.
$SyncScript = Join-Path $ScriptDir "sync_versions.ps1"
if (Test-Path $SyncScript) {
    & $SyncScript
    if ($LASTEXITCODE -ne 0) { Die "Sürüm senkronizasyonu başarısız (versions.json)." }
} else {
    Write-Host "[apk] UYARI: sync_versions.ps1 yok; app.json olduğu gibi kullanılacak." -ForegroundColor Yellow
}

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

# --- 1b. AYNA BÜTÜNLÜK DENETİMİ ---------------------------------------------
# robocopy "basarili" der ama KAYNAK kopyalama sirasinda degisiyorsa sonuc EKSIK kalir ve bunu
# rapor ETMEZ. Somut vaka: build_installer.ps1 / build_backend_exe.ps1 de pf'te
# `npm ci --legacy-peer-deps` calistirir -> node_modules SILINIP yeniden kurulur. O sirada baslayan
# APK aynalamasi yarim bir agac kopyalar; gradle ise 10 satirlik anlamsiz bir hatayla duser:
#   "settings.gradle line 3: Process 'command 'node'' finished with non-zero exit value 1"
# (gercek sebep: node_modules\react-native\package.json yok). Sessiz bozulmayi burada yakala.
Info "Ayna bütünlüğü doğrulanıyor..."
$mustExist = @(
    "node_modules\react-native\package.json",
    "node_modules\@react-native\gradle-plugin\package.json",
    "node_modules\expo\package.json",
    "android\gradlew.bat"
)
foreach ($rel in $mustExist) {
    if (-not (Test-Path (Join-Path $ShortDir $rel))) {
        Die ("Ayna EKSİK: $rel yok.`n" +
             "       En olası sebep: aynalama sırasında pf\node_modules başka bir build tarafından`n" +
             "       değiştiriliyordu (build_installer.ps1 / build_backend_exe.ps1 `npm ci` çalıştırır).`n" +
             "       O build BİTTİKTEN SONRA bu scripti tekrar çalıştırın (paralel ÇALIŞTIRMAYIN).")
    }
}
# Kaynak ile hedefteki react-native dosya sayisi kabaca tutmali (yarim kopya erken yakalanir).
$srcRn = @(Get-ChildItem (Join-Path $Pf "node_modules\react-native") -Recurse -File -ErrorAction SilentlyContinue).Count
$dstRn = @(Get-ChildItem (Join-Path $ShortDir "node_modules\react-native") -Recurse -File -ErrorAction SilentlyContinue).Count
if ($srcRn -gt 0 -and $dstRn -lt ($srcRn * 0.9)) {
    Die "Ayna EKSİK: react-native $dstRn/$srcRn dosya. Paralel bir build kaynağı değiştiriyor olabilir."
}
Info "Ayna bütünlüğü OK (react-native $dstRn dosya)."

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

# --- 4. İMZA DENETİMİ (tedarik zinciri) -------------------------------------
# build.gradle, release keystore yapılandırılmamışsa DEBUG anahtara düşer ve uyarı basar; ancak
# o uyari 2+ MB'lik gradle ciktisinin icinde kayboluyor. Debug keystore repoda commit'li ve
# parolasi Android'in EVRENSEL varsayilani ('android'/'androiddebugkey') oldugundan, bu anahtarla
# imzalanan bir APK'nin UZERINE ayni anahtarla imzalanmis SAHTE bir APK in-place kurulabilir ve
# uygulama verisini (SecureStore'daki cihaz X-API-Key'i + Supabase oturumu) DEVRALIR.
# Bu yuzden imzayi build SONRASI dogrula ve sonucu en son, en gorunur yerde soyle.
$apksigner = Get-ChildItem "$env:LOCALAPPDATA\Android\Sdk\build-tools\*\apksigner.bat" -ErrorAction SilentlyContinue |
             Sort-Object FullName | Select-Object -Last 1
if ($apksigner) {
    $certs = & $apksigner.FullName verify --print-certs $dest 2>&1 | Out-String
    if ($certs -match "CN=Android Debug") {
        Write-Host ""
        Write-Host "############################################################" -ForegroundColor Red
        Write-Host "#  DIKKAT: APK **DEBUG KEYSTORE** ILE IMZALANDI            #" -ForegroundColor Red
        Write-Host "#  Bu anahtar repoda commit'li ve parolasi herkeste ayni.  #" -ForegroundColor Red
        Write-Host "#  YAYINA CIKARMAYIN / SIDELOAD DAGITMAYIN.                #" -ForegroundColor Red
        Write-Host "#                                                          #" -ForegroundColor Red
        Write-Host "#  Cozum: pf\android\keystore.properties olusturun:        #" -ForegroundColor Yellow
        Write-Host "#    storeFile=C:\\yol\\pemf-release.p12                     #" -ForegroundColor Yellow
        Write-Host "#    storePassword=...  keyAlias=pemf  keyPassword=...     #" -ForegroundColor Yellow
        Write-Host "############################################################" -ForegroundColor Red
    } else {
        $dn = ($certs -split "`n" | Where-Object { $_ -match "certificate DN" } | Select-Object -First 1).Trim()
        Write-Host "[apk] Imza OK (release keystore): $dn" -ForegroundColor Green
    }
} else {
    Write-Host "[apk] UYARI: apksigner bulunamadi; imza dogrulanamadi." -ForegroundColor Yellow
}

if ($RemoveScratch) { Info "Scratch siliniyor (C: temiz): $ShortDir"; cmd /c rmdir /s /q "$ShortDir" 2>$null }
else { Info "Scratch korundu ($ShortDir) — sonraki build hızlı (incremental). Silmek için -RemoveScratch." }
