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
    [switch]$SkipWeb,
    # Kod korumasını (.pyd derleme) ATLA — YALNIZ hata ayıklama için.
    # make_base_zip.py korumasız paketi zaten REDDEDER, bu yüzden yayına sızamaz.
    [switch]$SkipProtect
)
$ErrorActionPreference = "Stop"
function Info($m) { Write-Host "[build] $m" -ForegroundColor Cyan }
function Warn($m) { Write-Host "[build] UYARI: $m" -ForegroundColor Yellow }
function Die($m)  { Write-Host "[build] HATA: $m" -ForegroundColor Red; exit 1 }

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$GuiRoot   = Split-Path -Parent $ScriptDir
$EmbRoot   = Split-Path -Parent $GuiRoot     # embeddable python kökü (guii'nin üstü)

# --- Çıktı kökü: boşsa guii\PEMF_BUILD (tek-yer + taşınabilir). Derin hedefte -BuildRoot ile kısa yol verilebilir. ---
if (-not $BuildRoot) { $BuildRoot = Join-Path $GuiRoot "PEMF_BUILD" }
Info "Build kökü: $BuildRoot"

# --- 0) Sürüm senkronu (2. tur denetimi [5.4], 2026-08-20): versions.json → VERSION +
#     docs/version_info.txt. Bu çağrı OLMADAN spec'in EXE'ye gömdüğü dosya-özellikleri sürümü
#     DONUYORDU (üç yayın boyunca 1.9.14 kaldı — yalnız kapalı Inno kanalı yeniliyordu).
#     build_installer.ps1:104 / build_apk.ps1:33 ile aynı desen. ---
$SyncScript = Join-Path $GuiRoot "build_tools\sync_versions.ps1"
if (Test-Path $SyncScript) {
    & $SyncScript
    if ($LASTEXITCODE -ne 0) { Die "Surum senkronizasyonu basarisiz (versions.json)." }
} else {
    Warn "sync_versions.ps1 yok; VERSION/version_info.txt oldugu gibi kullanilacak."
}

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
# ⚠️ PAKET BELİRLENİMCİLİĞİ (2026-08-21, ölçülerek bulundu). PyInstaller `base_library.zip`
# içindeki stdlib .pyc'lerini bu süreçte derler. Marshal, `frozenset` sabitlerini KÜMENİN
# YİNELEME SIRASINA göre yazar; o sıra da string hash'lerine, yani `PYTHONHASHSEED`e bağlıdır.
# Sonuç: her build'de `_collections_abc.pyc` AYNI BOYUTTA ama FARKLI baytlarda çıkıyordu →
# `base-deps.zip` sha'sı değişiyor → yayında hiçbir bağımlılık değişmediği hâlde
# HER KLİNİK 1,4 GB'ı yeniden indiriyordu (katmanlı paketin varlık sebebini yok eder).
# Ölçüm: aynı kaynağı rastgele tohumla 5 kez derlemek 5 farklı marshal çıktısı verdi;
# PYTHONHASHSEED=0 ile 3/3 birebir aynı. Kilit: tests/test_paket_belirlenimciligi_tohum.py
$env:PYTHONHASHSEED   = "0"

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

    # ⚠️ DENETİM 2026-08-04 (P1): burada export KAYNAĞI `guii\frontend\` idi. O dizin `pf\`'in
    # 27 Temmuz'da DONMUŞ bir KOPYASIDIR (45 dosya fark) ve içinde
    # `src/components/ui/GlobalEmergencyStop.tsx` (AppShell'de HER ekrana basılan kayan ACİL DURDUR)
    # ile `hooks/useTeardownGuard.ts` HİÇ YOKTUR. Yani bu script'le üretilen base.zip, aynı sürüm
    # numarasıyla, ACİL DURDUR'u ekranların çoğunda OLMAYAN bir web UI sevk ediyordu —
    # build_installer.ps1 ile üretilen Inno kurulumunda ise buton VARDI (iki farklı UI, tek sürüm).
    # TEK KAYNAK = `pf\` (README: "Web/mobil UI'yi pf/'te düzenle — frontend/src bayat kopyadır").
    # build_tools/build_installer.ps1:237-269 ile AYNI desen: pf'te export al → frontend\dist'e kopyala.
    $PfDir = Join-Path $GuiRoot "pf"
    if (-not (Test-Path (Join-Path $PfDir "package.json"))) { Die "pf\ (web-UI kaynağı) bulunamadı: $PfDir" }

    # İKİNCİ-KAYNAK NÖBETİ: `frontend\` yalnızca ÜRETİLEN `dist\` aynası olmalı. İçinde bir Expo
    # projesi (package.json) duruyorsa bu bug bir daha oluşabilir → gürültülü uyar.
    if (Test-Path (Join-Path $FrontendDir "package.json")) {
        Warn "frontend\package.json VAR — bu bayat ikinci UI kaynağıdır ve karışıklığa yol açar. İçeriği (dist hariç) SİLİN; frontend\ yalnız dist aynası olmalı."
    }

    # npm / npx zorunlu (web build edilemezse GÜR-sesle fail)
    $npmCmd = Get-Command npm -ErrorAction SilentlyContinue
    if (-not $npmCmd) { Die "npm bulunamadı. React web export için Node.js/npm gerekli (web zorunlu)." }
    $npxCmd = Get-Command npx -ErrorAction SilentlyContinue
    if (-not $npxCmd) { Die "npx bulunamadı. Expo web export için npx gerekli (web zorunlu)." }

    Push-Location $PfDir
    try {
        # Idempotent: eski pf\dist'i temizle ki bayat dosya kalmasın
        $PfDist = Join-Path $PfDir "dist"
        if (Test-Path $PfDist) {
            Info "Eski pf\dist temizleniyor..."
            Remove-Item $PfDist -Recurse -Force
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

        # `npm run export:web` = expo export + postexport-web patcher. Ham `npx expo export`
        # patcher'ı ATLAR → build_installer.ps1 ile ÇIKTI FARKI oluşur. Aynı komutu kullan.
        Info "Expo web export alınıyor (npm run export:web)..."
        $env:EXPO_ROUTER_DISABLE_RN_NAVIGATION_CHECK = "1"
        & npm run export:web
        if ($LASTEXITCODE -ne 0) { Die "Expo web export (npm run export:web) başarısız!" }
    } finally {
        Pop-Location
    }

    # pf\dist -> frontend\dist (PyInstaller spec'inin bundle'ladığı kanonik konum)
    $FrontendDistDir = Join-Path $FrontendDir "dist"
    if (Test-Path $FrontendDistDir) { Remove-Item $FrontendDistDir -Recurse -Force }
    if (-not (Test-Path $FrontendDir)) { New-Item -ItemType Directory -Path $FrontendDir -Force | Out-Null }
    Copy-Item (Join-Path $PfDir "dist") $FrontendDistDir -Recurse -Force
    Info "pf web export -> frontend\dist kopyalandı."

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

# --- 4.5 E-stop bulut aynasi provizyonu (sahip karari 2026-08-19; git'e girmez, pakete gomulur)
# Yerel ESP Secrets.h'tan uretir; kaynak placeholder ise UYARIR ama build'i DURDURMAZ
# (CI/temiz-klon ortaminda paket sirsiz cikar, ayna sessizce devre disi kalir — guvenli).
& $PY "build_tools\make_cloud_provision.py"
if ($LASTEXITCODE -ne 0) { Warn "cloud_mqtt_provision uretilemedi -> paket BULUT-AYNASIZ cikacak (yerel E-stop etkilenmez)." }

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

# ── KOD KORUMASI (2026-08-08, sahip ilkesi: "onefile da olsa onedir de olsa client de olsa
# pyd olmalı") — build'in AYRILMAZ parçası. Eskiden ayrı elle çalıştırılıyordu; unutulunca
# ai_hub kaynağı DÜZ .py olarak dağıtılıyordu ve bu ancak sahada fark edilirdi.
# `-SkipProtect` yalnız hata ayıklama içindir; make_base_zip zaten korumasız paketi REDDEDER.
if (-not $SkipProtect -and (Test-Path $exe)) {
    Info "Kod koruması: ai_hub .py -> .pyd (Cython) derleniyor..."
    $vcv = Get-ChildItem "${env:ProgramFiles(x86)}\Microsoft Visual Studio\*\*\VC\Auxiliary\Build\vcvarsall.bat",
                         "$env:ProgramFiles\Microsoft Visual Studio\*\*\VC\Auxiliary\Build\vcvarsall.bat" -EA 0 |
           Select-Object -First 1
    if (-not $vcv) {
        Warn "MSVC (vcvarsall.bat) bulunamadı → .pyd derlenemedi. Paket KORUMASIZ kalır;"
        Warn "make_base_zip bunu reddedecektir. Çözüm: bootstrap.ps1 ile MSVC Build Tools kurun."
    } else {
        $protLog = Join-Path $BuildRoot "compile_pyd.log"
        $c = "call `"$($vcv.FullName)`" x64 >nul 2>&1 && set DISTUTILS_USE_SDK=1&& set MSSdk=1&& " +
             "set PYTHONIOENCODING=utf-8&& set PYTHONPATH=$GuiRoot&& " +
             "`"$PY`" `"$GuiRoot\build_tools\compile_pyd.py`" --dist `"$dist\PEMF_Backend`" > `"$protLog`" 2>&1"
        cmd /c $c
        $ozet = (Select-String -Path $protLog -Pattern "^Derlendi|^Başarısız" -EA 0 | ForEach-Object { $_.Line }) -join "  "
        if ($ozet) { Info "Kod koruması: $ozet" } else { Warn "Kod koruması çıktısı okunamadı → $protLog" }
        $kalan = @(Get-ChildItem "$dist\PEMF_Backend\_internal\ai_hub" -Recurse -Filter *.py -EA 0 |
                   Where-Object { $_.Name -ne "__init__.py" }).Count
        if ($kalan -gt 0) {
            Warn "$kalan modül derlenemedi → şifreleme uygulanıyor (yedek katman)..."
            & $PY "$GuiRoot\build_tools\encrypt_sources.py" --dist "$dist\PEMF_Backend" --verify
        }
    }
}

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
