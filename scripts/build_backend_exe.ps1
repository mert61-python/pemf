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
    [switch]$SkipProtect,
    # AI hazırlık kapısını ATLA (üretilen EXE'de her AI modülünün gerçekten import
    # edilebildiğini doğrular — saha bulgusu 2026-08-27). Yalnız acil durumda kullanın:
    # kapı kapalıyken ölü-doğmuş bir modül yayına çıkabilir.
    [switch]$SkipAiGate
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

    # ── 5. KAPI: PYZ ARŞİVİNDE ai_hub VAR MI? (denetim 2026-08-28 #07) ──────────
    # ⚠️ Yukarıdaki dört kapının DÖRDÜ DE "DİSKTE düz .py kaldı mı" diye soruyordu ve
    # dördü de YEŞİL yanıyordu. Ölçüldü: sevk edilen EXE'nin PYZ arşivinde 87 ai_hub girişi
    # okunabilir bytecode olarak duruyordu; çalışan süreçte yüklü ai_hub .pyd sayısı 1/65 idi
    # (o tek modül de PYZ'de ikizi olmayan tek modül). Cython katmanının katkısı SIFIRDI.
    # PYZ'de ai_hub kalırsa import diskteki .pyd'yi ATLAR — koruma etkisizdir.
    Info "Koruma kapısı: EXE'nin PYZ arşivinde ai_hub var mı?"
    & $PY "$GuiRoot\scripts\pyz_koruma_kapisi.py" $exe --duz-py-de-kontrol "$dist\PEMF_Backend"
    if ($LASTEXITCODE -ne 0) {
        Die ("KOD KORUMASI KAPISI KIRMIZI: ai_hub PYZ arşivinde (ya da diskte düz .py olarak) " +
             "duruyor. Bu EXE'de Cython koruması ETKİSİZDİR — import .pyd'yi atlar. " +
             "spec'te `a.pure[:] = [... != 'ai_hub']` satırı PYZ(a.pure)'dan ÖNCE olmalı.")
    }

    # ── 6. KAPI: kaynak ai_hub'ın TAMAMI sevk ağacında mı? ───────────────────────
    # ⚠️ Bu kapı bir SESSİZ ÖLÜM kapısıdır, koruma kapısı değil. Ölçülen arıza: spec'teki
    # yol-çıpasız torch filtresi `ai_hub/xai_tabular/ig_torch.py`yi yiyordu (adında "torch"
    # geçiyor) → modül sevk ağacına HİÇ girmiyor, yalnız PYZ'de yaşıyordu. PYZ temizlenince
    # (5. kapının gerektirdiği düzeltme) RNA gen-katkısı açıklaması sessizce ölecekti.
    Info "Sevk ağacı kapısı: kaynak ai_hub modüllerinin hepsi pakette mi?"
    & $PY "$GuiRoot\scripts\sevk_agaci_ai_hub_kapisi.py" "$dist\PEMF_Backend"
    if ($LASTEXITCODE -ne 0) {
        Die ("SEVK AĞACI KAPISI KIRMIZI: kaynaktaki bir ai_hub modülü pakete GİRMEMİŞ. " +
             "Lazy import edilen bir modülse ilgili özellik sahada sessizce ölür ve başka " +
             "hiçbir kapı bunu görmez. Genellikle sebep spec'teki yol-çıpasız bir datas filtresidir.")
    }
}

# ── AI HAZIRLIK KAPISI (2026-08-27, saha bulgusu) ────────────────────────────────
# NEDEN: "Yara kapanma modeli bu kurulumda hazır değil" sahada, model paketi KURULUYKEN
# çıktı. Sebep bir bağımlılığın frozen EXE'de import EDİLEMEMESİYDİ — build yeşil, testler
# yeşil, paket yeşil; yalnız ÜRÜN ölüydü. Hiçbir kapı bunu görmüyordu çünkü tüm testler
# frozen OLMAYAN ortamda koşuyor (orada her bağımlılık pip'ten gelir ve hep vardır).
# ⚠️ SINIF: her yeni AI modülü aynı şekilde sessizce ölü doğabilir. Kapı, ÜRETİLEN EXE'yi
# ayağa kaldırıp `/api/ai/hazirlik?derin=1` ile GERÇEK import'u zorlar; bir modül ölüyse
# build KIRMIZI olur ve o EXE yayına çıkmaz. -SkipAiGate ile atlanabilir (acil durum).
if ((Test-Path $exe) -and -not $SkipAiGate) {
    Info "AI hazırlık kapısı: üretilen EXE'de tüm AI modülleri gerçekten import ediliyor mu?"
    $gatePort = 8177
    $gateLog = Join-Path $BuildRoot "ai_hazirlik_kapisi.log"
    $env:PEMF_SIMULATE = "1"
    $proc = Start-Process -FilePath $exe -ArgumentList "--port", "$gatePort" `
        -RedirectStandardOutput $gateLog -RedirectStandardError "$gateLog.err" -PassThru -WindowStyle Hidden
    try {
        $hazir = $false
        foreach ($i in 1..90) {
            Start-Sleep -Seconds 2
            try {
                $null = Invoke-RestMethod "http://127.0.0.1:$gatePort/api/health" -TimeoutSec 3
                $hazir = $true; break
            } catch { }
        }
        if (-not $hazir) { Warn "AI kapısı: EXE $gatePort portunda açılmadı → kapı ATLANDI (log: $gateLog)" }
        else {
            # derin=1: find_spec DEĞİL, GERÇEK import — ölü-doğmuş modülü yakalayan tek mod.
            $rapor = Invoke-RestMethod "http://127.0.0.1:$gatePort/api/ai/hazirlik?derin=1" -TimeoutSec 600
            Info "AI hazırlık: $($rapor.hazir)/$($rapor.toplam) modül hazır."
            if ($rapor.eksik.Count -gt 0) {
                foreach ($m in $rapor.moduller) {
                    if (-not $m.hazir) { Write-Host "   ✗ $($m.modul): kod=$($m.kod) model=$($m.model) — $($m.sebep)" -ForegroundColor Red }
                }
                Die ("AI HAZIRLIK KAPISI KIRMIZI: $($rapor.eksik -join ', ') modülü ÜRETİLEN EXE'de çalışmıyor. " +
                     "Bu EXE yayına çıkarsa kullanıcı 'model paketi gerekli' yanlış teşhisini görür " +
                     "(saha bulgusu 2026-08-27). Eksik bağımlılığı spec'e ekleyin ya da -SkipAiGate ile bilinçli geçin.")
            }

            # ⚠️ DENETİM 2026-08-28 #03/#10 — kapının KENDİSİ kördü: model sütunu dosyaya bakmadan
            # "gomulu" diyordu ve XAI zinciri (lazy import) hiç görünmüyordu. Uç artık ikisini de
            # raporluyor; build de ikisini KONTROL ETMELİ, yoksa kapı yine boş çalışır.
            if ($null -eq $rapor.xai) {
                Die "AI HAZIRLIK: yanıtta 'xai' bölümü yok — derin sorgu XAI zincirini ölçmüyor (denetim #03(b))."
            }
            if (-not $rapor.xai.hazir) {
                Write-Host "   ✗ XAI: grad_cam=$($rapor.xai.grad_cam) pytorch_grad_cam=$($rapor.xai.pytorch_grad_cam) shap=$($rapor.xai.shap) captum=$($rapor.xai.captum) ttach=$($rapor.xai.ttach)" -ForegroundColor Red
                if ($rapor.xai.em_ref_stats_eksik.Count -gt 0) {
                    Write-Host "   ✗ EM referans istatistikleri EKSİK: $($rapor.xai.em_ref_stats_eksik -join ', ')" -ForegroundColor Red
                }
                Die ("XAI ZİNCİRİ KIRMIZI: açıklanabilirlik kütüphaneleri ya da EM referans " +
                     "istatistikleri üretilen EXE'de eksik. Bu tam olarak 1.9.25'te yaşanan sessiz " +
                     "ölümdür (.npz spec'te yoktu, EM XAI üretimde ölüydü, hiçbir kapı görmedi).")
            }
            Info "XAI zinciri: grad_cam=$($rapor.xai.grad_cam), shap=$($rapor.xai.shap), captum=$($rapor.xai.captum), ttach=$($rapor.xai.ttach); EM ref-stats tam."

            if ($null -eq $rapor.pip_yasagi -or -not $rapor.pip_yasagi.etkin) {
                Die ("ÇALIŞMA-ANI PİP YASAĞI ETKİN DEĞİL: üretilen EXE çalışırken kendine paket " +
                     "kurmaya kalkabilir (denetim #10 — ürün kendi EXE'sini `-m pip install` ile " +
                     "alt-süreç olarak başlatıyordu). utils/runtime_guards.py giriş noktasında çağrılmalı.")
            }
            Info "Çalışma-anı pip yasağı: etkin."

            # ⚠️ DENETİM 2026-08-28 #07 — KORUMANIN ÇALIŞMA-ANI KANITI. Statik kapılar
            # (PYZ/disk) "korumasız dosya var mı" der; bu kontrol modüllerin GERÇEKTEN
            # nereden yüklendiğini ölçer. `.pyenc` MEŞRU sayılır: build_installer.ps1:574 ve
            # make_base_zip.py::_korumasiz_ai_hub() sahip ölçütü "düz .py YOK mu" — .pyd
            # zorunluluğu AYRI bir sahip kararıdır, buradan sessizce dayatılmaz.
            # `-SkipProtect` / MSVC-yok build'lerinde bu blok hiç çalışmaz (aşağıdaki koşul).
            if (-not $SkipProtect) {
                $korumasiz = @($rapor.moduller | Where-Object { $_.yukleme -notin @('pyd', 'pyenc') })
                if ($korumasiz.Count -gt 0) {
                    foreach ($m in $korumasiz) {
                        Write-Host "   ✗ $($m.modul): yukleme=$($m.yukleme)" -ForegroundColor Red
                    }
                    Die ("KOD KORUMASI ÇALIŞMA-ANINDA ETKİSİZ: $($korumasiz.Count)/$($rapor.toplam) modül " +
                         ".pyd/.pyenc DIŞINDAN yükleniyor ('pyz' = PYZ arşivinden, 'py' = diskteki düz " +
                         "kaynaktan). Sevk edilen 1.9.31'de bu oran 64/65'ti ve dört kapı da yeşildi.")
                }
                Info "Kod koruması (çalışma-anı): $($rapor.toplam)/$($rapor.toplam) modül .pyd/.pyenc'ten yükleniyor."
            }
        }
    } finally {
        try { Stop-Process -Id $proc.Id -Force -EA 0 } catch { }
        Remove-Item Env:PEMF_SIMULATE -EA 0
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
