# =============================================================================
# PEMF Headless Backend — Windows Service kurulumu (NSSM).  Faz 5 (sağlamlaştırılmış)
# =============================================================================
# Öncelik: frozen EXE (dist\PEMF_Backend\PEMF_Backend.exe). Yoksa python + script.
# Mosquitto KENDİ servisidir (install_mosquitto_service.ps1) -> backend ona
# 'depends' ile bağlanır ve broker'ı kendi başlatmaz (--no-mosquitto-ensure).
# Çökme -> NSSM otomatik restart. Kapanış -> backend_service donanımı güvenli durdurur.
#
# Yönetici PowerShell:  .\install_backend_service.ps1                 (yalnız-LAN, güvenli)
#   Uzaktan erişim (internete açar):  .\install_backend_service.ps1 -EnableTunnel
# =============================================================================
param(
    # Cloudflare tüneli (uzaktan erişim) — VARSAYILAN KAPALI. Açarsanız cihaz internete
    # açılır; bu durumda kimlik doğrulama (PEMF_REQUIRE_AUTH) OTOMATİK zorunlu kılınır.
    [switch]$EnableTunnel,
    # API kimlik doğrulamasını zorla (LAN'da bile önerilir). Tünel açıksa zaten zorunlu.
    [switch]$RequireAuth
)
$ErrorActionPreference = "Stop"

function Write-Status($msg, $color = "White") {
    $ts = Get-Date -Format "HH:mm:ss"
    Write-Host "[$ts] $msg" -ForegroundColor $color
}

$principal = New-Object System.Security.Principal.WindowsPrincipal([System.Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([System.Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Status "HATA: Bu script Yönetici olarak çalıştırılmalıdır." "Red"
    pause; exit 1
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  PEMF Backend Service Kurulumu (NSSM)" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

$ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$GuiRoot     = Split-Path -Parent $ScriptDir
$BackendFile = "$GuiRoot\backend_service.py"
$ExePath     = @("$GuiRoot\PEMF_BUILD\dist\PEMF_Backend\PEMF_Backend.exe", "C:\PEMF_BUILD\dist\PEMF_Backend\PEMF_Backend.exe", "$GuiRoot\dist\PEMF_Backend\PEMF_Backend.exe") |
               Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $ExePath) { $ExePath = "$GuiRoot\dist\PEMF_Backend\PEMF_Backend.exe" }

# ⚠️ DENETİM 2026-08-04: servis LocalSystem olarak çalışır → ImagePath'teki ikili KORUMALI bir
# dizinde olmalı. Aday listesi `C:\PEMF_BUILD\...` ve kullanıcı profili altındaki build çıktılarını
# da içeriyor; oralar yönetici-olmayan kullanıcılarca YAZILABİLİR → ikili değiştirilirse bir
# sonraki servis başlangıcında LocalSystem'de keyfi kod çalışır. Bu script bir GELİŞTİRME/elle
# kurulum aracı olduğu için build dizininden çalıştırmayı ENGELLEMİYORUZ, ama SESSİZ bırakmıyoruz.
# Üretim yolu: Inno installer → setup_services.ps1 → C:\Program Files\PEMF Backend (korumalı).
function Test-PemfProtectedPath([string]$P) {
    $p = $P.ToLowerInvariant()
    return ($p.StartsWith("c:\program files\") -or $p.StartsWith("c:\program files (x86)\") -or $p.StartsWith("c:\windows\"))
}
if (-not (Test-PemfProtectedPath $ExePath)) {
    Write-Status "UYARI: servis ikilisi KORUMASIZ dizinde: $ExePath" "Red"
    Write-Status "       Yonetici olmayan bir kullanici bu dosyayi degistirip LocalSystem'de kod calistirabilir." "Red"
    Write-Status "       Uretim kurulumu icin Inno installer + setup_services.ps1 kullanin (Program Files)." "Yellow"
}
# ⚠️ DENETİM 2026-08-04 (P2 — YEREL AYRICALIK YÜKSELTME): NSSM servis-sarmalayıcısıdır; servisin
# ImagePath'i nssm.exe'dir ve LocalSystem olarak çalışır. `C:\nssm` kullanılıyordu; `C:\` kökünün
# varsayılan ACL'i `Authenticated Users:(OI)(CI)(IO)(M)` içerdiğinden orada oluşan dosyaları
# YÖNETİCİ OLMAYAN her kullanıcı DEĞİŞTİREBİLİR → nssm.exe değiştirilip LocalSystem'de kod
# çalıştırılabilirdi. Korumalı dizine taşındı; eski dizin varsa YERİNDE sertleştirilir.
# ⚠️ DENETİM 2026-08-04 (P3 — BU DÜZELTMENİN KENDİ AÇIĞI): yukarıdaki düzeltme korumalı dizine
# geçti AMA `C:\nssm\nssm.exe` VARSA hâlâ ONU TERCİH ediyordu. Oysa tam da anlatılan zafiyet
# nedeniyle o dosya, kurulumdan ÖNCE yönetici olmayan biri tarafından YERLEŞTİRİLMİŞ olabilir
# (`C:\` kökü Authenticated Users'a yazma verir). Dizinin ACL'ini sonradan sertleştirmek ZATEN
# YERLEŞTİRİLMİŞ ikiliyi geri almaz — servis yine saldırganın exe'sini LocalSystem olarak koşar.
# Artık HER ZAMAN korumalı dizin kullanılır; oradaki nssm.exe yoksa temiz kopya indirilir.
# `C:\nssm` yalnızca ARTIK OLARAK ele alınır (aşağıda sertleştirilir/temizlenir), kaynak olarak DEĞİL.
$NssmDir     = "C:\Program Files\PEMF\nssm"
$LegacyNssm  = "C:\nssm"
$NssmExe     = "$NssmDir\nssm.exe"

# Dizini SYSTEM+Administrators'a tam, Users'a yalnız OKU/ÇALIŞTIR yap. SID kullanılır:
# Türkçe Windows'ta grup adları "Yöneticiler"/"Kullanıcılar" olduğundan isimle eşleşme
# SESSİZCE başarısız olurdu.
function Protect-PemfDir([string]$Dir) {
    if (-not (Test-Path $Dir)) { return }
    try {
        & icacls $Dir /inheritance:r `
            /grant '*S-1-5-18:(OI)(CI)F' `
            /grant '*S-1-5-32-544:(OI)(CI)F' `
            /grant '*S-1-5-32-545:(OI)(CI)RX' *>$null
    } catch { }
}
$ServiceName = "PemfBackend"
$LogDir      = "C:\ProgramData\PEMF_System\logs"

# --- Servis ikilisi: önce frozen EXE, yoksa python + backend_service.py ---
# Ortak argüman: Mosquitto kendi servisi olduğu için broker'ı backend BAŞLATMAZ,
# sadece izler -> --no-mosquitto-ensure.
$CommonArgs = @("--host", "0.0.0.0", "--port", "8000", "--no-mosquitto-ensure")
if (Test-Path $ExePath) {
    $SvcBinary       = $ExePath
    $SvcArgs         = $CommonArgs
    $AppDir          = Split-Path -Parent $ExePath
    $FirewallProgram = $ExePath
    $UsingExe        = $true
    Write-Status "Servis ikilisi: frozen EXE -> $ExePath" "Green"
} else {
    $foundPython = Get-Command python -ErrorAction SilentlyContinue
    if (-not $foundPython) {
        Write-Status "HATA: Ne frozen EXE ne PATH'te python var. Önce build_backend_exe.ps1 çalıştırın." "Red"
        pause; exit 1
    }
    if (-not (Test-Path $BackendFile)) {
        Write-Status "HATA: backend_service.py bulunamadı: $BackendFile" "Red"
        pause; exit 1
    }
    $SvcBinary       = $foundPython.Source
    $SvcArgs         = @("$BackendFile") + $CommonArgs
    $AppDir          = $GuiRoot
    $FirewallProgram = $foundPython.Source
    $UsingExe        = $false
    Write-Status "Frozen EXE yok; python+script (dev) ile: $SvcBinary" "Yellow"
}

if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
    Write-Status "Log dizini oluşturuldu: $LogDir" "Green"
}

# --- NSSM hazır mı? (yoksa indir) ---
if (-not (Test-Path $NssmExe)) {
    Write-Status "NSSM bulunamadı, indiriliyor (bu indirme DOĞRULANMIYOR — bundled NSSM tercih edilir)..." "Yellow"
    if (-not (Test-Path $NssmDir)) { New-Item -ItemType Directory -Path $NssmDir -Force | Out-Null }
    Protect-PemfDir $NssmDir   # dosya yazılmadan ÖNCE kilitle (yarış penceresi)
    # Paylaşımlı TEMP'te SABİT ad + `-Recurse | Select -First 1`, önceden yerleştirilmiş bir
    # nssm.exe'nin seçilmesine yol açabilirdi → süreç-özel benzersiz dizin.
    $TmpRoot = Join-Path $env:TEMP ("pemf_nssm_" + [guid]::NewGuid().ToString("N"))
    try {
        New-Item -ItemType Directory -Path $TmpRoot -Force | Out-Null
        $NssmZip = Join-Path $TmpRoot "nssm.zip"
        Invoke-WebRequest -Uri "https://nssm.cc/release/nssm-2.24.zip" -OutFile $NssmZip -UseBasicParsing
        Expand-Archive -Path $NssmZip -DestinationPath (Join-Path $TmpRoot "ext") -Force
        $NssmBin = Get-ChildItem (Join-Path $TmpRoot "ext") -Filter "nssm.exe" -Recurse |
            Where-Object { $_.FullName -like "*win64*" } | Select-Object -First 1
        if (-not $NssmBin) { $NssmBin = Get-ChildItem (Join-Path $TmpRoot "ext") -Filter "nssm.exe" -Recurse | Select-Object -First 1 }
        Copy-Item $NssmBin.FullName $NssmExe -Force
        Protect-PemfDir $NssmDir
        Write-Status "NSSM kuruldu: $NssmExe" "Green"
    } finally {
        Remove-Item $TmpRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
} else {
    Protect-PemfDir $NssmDir   # mevcut korumalı dizin — yine de sertleştir (idempotent)
    Write-Status "NSSM bulundu: $NssmExe" "Green"
}

# Eski `C:\nssm` ARTIK: kaynak olarak KULLANILMAZ (bkz. $NssmDir notu) ama diskte duruyorsa
# yazılabilir bir dizinde LocalSystem'de koşabilecek bir ikili bırakmayalım — sertleştir ve
# operatörü uyar. Silmiyoruz: başka bir servis onu kullanıyor olabilir.
if (Test-Path $LegacyNssm) {
    Protect-PemfDir $LegacyNssm
    Write-Status "UYARI: eski '$LegacyNssm' dizini duruyor — KULLANILMADI, yalnız sertleştirildi." "Yellow"
    Write-Status "       Baska bir servis kullanmiyorsa elle silin (yazilabilir konumda ikili birakmayin)." "Yellow"
}

# --- Varolan servisi kaldır ---
if (Get-Service -Name $ServiceName -ErrorAction SilentlyContinue) {
    Write-Status "Mevcut servis kaldırılıyor..." "Yellow"
    & $NssmExe stop $ServiceName *>$null
    Start-Sleep -Seconds 2
    & $NssmExe remove $ServiceName confirm *>$null
    Start-Sleep -Seconds 2
}

# --- Kur ---
Write-Status "Servis kuruluyor: $ServiceName" "Yellow"
# GUARD: nssm install'a GEÇERLİ program yolu verilmezse NSSM, sessiz kurulum yerine interaktif
# config GUI'si açar (boş Path/Arguments penceresi → kafa karıştırır). Geçersiz binary'de net hata ver.
if (-not $SvcBinary -or -not (Test-Path $SvcBinary)) {
    Write-Status "HATA: Servis ikilisi geçersiz/bulunamadı ($SvcBinary). Önce build_backend_exe.ps1 ile EXE üretin VEYA installer kullanın. (nssm install ATLANDI — aksi halde elle-config GUI açılırdı.)" "Red"
    exit 1
}
& $NssmExe install $ServiceName $SvcBinary @SvcArgs

& $NssmExe set $ServiceName AppDirectory       $AppDir
& $NssmExe set $ServiceName DisplayName        "PEMF Backend Service"
& $NssmExe set $ServiceName Description         "Headless PEMF backend: FastAPI, WebSocket, STM32, MQTT, React Web."
& $NssmExe set $ServiceName Start               SERVICE_AUTO_START
& $NssmExe set $ServiceName ObjectName          LocalSystem

# Log (NSSM stdout/stderr yakalar + döndürür)
& $NssmExe set $ServiceName AppStdout           "$LogDir\backend_service_stdout.log"
& $NssmExe set $ServiceName AppStderr           "$LogDir\backend_service_stderr.log"
& $NssmExe set $ServiceName AppRotateFiles      1
& $NssmExe set $ServiceName AppRotateBytes      10485760

# Çökme kurtarma + güvenli durdurma süresi (backend_service finally bloğu donanımı durdurur)
& $NssmExe set $ServiceName AppExit             Default Restart
& $NssmExe set $ServiceName AppRestartDelay     5000
& $NssmExe set $ServiceName AppStopMethodConsole 15000
& $NssmExe set $ServiceName AppThrottle         5000

# Ortam değişkenleri. GÜVENLİK: tünel (internete açma) VARSAYILAN KAPALI. Açılırsa
# kimlik doğrulama OTOMATİK zorunlu kılınır (public + kimliksiz erişim engellenir).
# EXE'de PYTHONPATH'e gerek yok -> bundled modüller kullanılır.
if ($EnableTunnel -and -not $RequireAuth) {
    Write-Status "Tünel açık -> PEMF_REQUIRE_AUTH otomatik ZORUNLU (public+kimliksiz engellendi)." "Yellow"
    $RequireAuth = $true
}
$EnvList = @("PYTHONUNBUFFERED=1", "PEMF_HEADLESS=1", "PEMF_LOG_DIR=$LogDir")
if (-not $UsingExe) { $EnvList = @("PYTHONPATH=$GuiRoot") + $EnvList }
if ($EnableTunnel)  { $EnvList += "PEMF_ENABLE_TUNNEL=1" }
if ($RequireAuth)   { $EnvList += "PEMF_REQUIRE_AUTH=1" }
& $NssmExe set $ServiceName AppEnvironmentExtra @EnvList
if ($EnableTunnel) {
    Write-Status "Uzaktan erişim (Cloudflare tüneli) AÇIK + auth zorunlu. Token'ı istemcilere verin." "Cyan"
} else {
    Write-Status "Yalnız-LAN modu (tünel kapalı, güvenli). Uzaktan erişim için: -EnableTunnel" "Gray"
}

# --- Mosquitto bağımlılığı (kendi servisi varsa) ---
if (Get-Service -Name "mosquitto" -ErrorAction SilentlyContinue) {
    sc.exe config $ServiceName depend= mosquitto | Out-Null
    Write-Status "Bağımlılık eklendi: PemfBackend -> mosquitto" "Green"
} else {
    Write-Status "UYARI: 'mosquitto' servisi yok. Önce install_mosquitto_service.ps1 çalıştırın." "Yellow"
}

# --- Firewall (API 8000 TCP + keşif 5051 UDP) ---
try {
    if (-not (Get-NetFirewallRule -DisplayName "PEMF Backend API" -ErrorAction SilentlyContinue)) {
        New-NetFirewallRule -DisplayName "PEMF Backend API" -Direction Inbound `
            -Program $FirewallProgram -Action Allow -Protocol TCP -LocalPort 8000 -Profile Any | Out-Null
        Write-Status "Firewall: TCP 8000 inbound eklendi." "Green"
    }
    if (-not (Get-NetFirewallRule -DisplayName "PEMF UDP Discovery" -ErrorAction SilentlyContinue)) {
        New-NetFirewallRule -DisplayName "PEMF UDP Discovery" -Direction Inbound `
            -Program $FirewallProgram -Action Allow -Protocol UDP -LocalPort 5051 -Profile Any | Out-Null
        Write-Status "Firewall: UDP 5051 inbound eklendi." "Green"
    }
} catch {
    Write-Status "Firewall kuralı eklenemedi: $_" "Yellow"
}

# --- Başlat ---
Write-Status "Servis başlatılıyor..." "Yellow"
& $NssmExe start $ServiceName
Start-Sleep -Seconds 4
$status = & $NssmExe status $ServiceName 2>&1
Write-Status "Servis durumu: $status" "Cyan"

Write-Host ""
Write-Host "Backend servisi kuruldu." -ForegroundColor Green
Write-Host "  Servis : $ServiceName  (ikili: $(if($UsingExe){'frozen EXE'}else{'python+script'}))"
Write-Host "  URL    : http://localhost:8000"
Write-Host "  Loglar : $LogDir\backend_service.log"
Write-Host "  Bağımlılık: mosquitto (otomatik sıra: mosquitto -> PemfBackend)"
Write-Host ""
Write-Host "Yönetim: $NssmExe (status|stop|start|restart|remove) $ServiceName"
Write-Host ""
pause
