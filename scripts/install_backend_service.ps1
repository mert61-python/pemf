# =============================================================================
# PEMF Headless Backend — Windows Service kurulumu (NSSM).  Faz 5 (sağlamlaştırılmış)
# =============================================================================
# Öncelik: frozen EXE (dist\PEMF_Backend\PEMF_Backend.exe). Yoksa python + script.
# Mosquitto KENDİ servisidir (install_mosquitto_service.ps1); backend broker'ı kendi başlatmaz
# (--no-mosquitto-ensure) ve ona yeniden deneyerek bağlanır — SCM 'depend=' KULLANILMAZ (aşağıya bakın).
# Çökme -> NSSM otomatik restart. Kapanış -> backend_service donanımı güvenli durdurur.
#
# ⚠️ D2.73 (B-9.21 · A-11 sahip kararı): bu betik DESTEKLENEN İKİNCİ kurulum yoludur (sahadaki yol launcher'dır — Y36).
# Servis ortamı dağıtım profilinden (deploy\<Mode>.env; varsayılan device.env) setup_services.ps1 ile AYNI ayrıştırmayla
# kurulur: at-rest şifreleme (PEMF_ENCRYPT_AT_REST), veri kökü (PEMF_DATA_DIR — LocalSystem profili DEĞİL, operatörün görüp
# yedekleyebildiği ProgramData), STM portu (auto), DNS-rebinding koruması (PEMF_ALLOWED_HOSTS). Eskiden yalnız 3 değişken
# yazılıyordu: taze makinede hasta/seans DB'leri DÜZ METİN, veri kökü LocalSystem profilinde, ALLOWED_HOSTS='*'.
# Profil bulunamazsa kurulum, servise DOKUNMADAN durur. Kapı: tests/test_install_backend_service_PROFIL_ORTAMI_D273.py
#
# Yönetici PowerShell:  .\install_backend_service.ps1                 (yalnız-LAN, güvenli)
#   Uzaktan erişim (internete açar):  .\install_backend_service.ps1 -EnableTunnel
# =============================================================================
param(
    # Cloudflare tüneli (uzaktan erişim) — VARSAYILAN KAPALI. Açarsanız cihaz internete
    # açılır; bu durumda kimlik doğrulama (PEMF_REQUIRE_AUTH) OTOMATİK zorunlu kılınır.
    # Profil (device.env) tüneli açsa bile bu betikte tünel YALNIZ bu anahtarla açılır.
    [switch]$EnableTunnel,
    # API kimlik doğrulamasını zorla (LAN'da bile önerilir). Tünel açıksa zaten zorunlu.
    [switch]$RequireAuth,
    # Dağıtım profili: deploy\<Mode>.env (device = klinik, server = demo).
    [ValidateSet("device", "server")]
    [string]$Mode = "device"
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
# ⚠️ 2026-09-19: giris noktasi apps\backend altina tasindi (klasor duzeni F-E).
$BackendFile = "$GuiRoot\apps\backend\backend_service.py"
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

# ── D2.73 (A-11): dağıtım profili — setup_services.ps1 ile AYNI dosya araması ve AYNI ayrıştırma (kapı ikisinin çıktısını eşler) ──
function Get-PemfProfilEnvDosyasi([string]$AppDir, [string]$Mode, [string]$BetikDizini) {
    @(
        (Join-Path $AppDir "_internal\deploy\$Mode.env"),
        (Join-Path $AppDir "deploy\$Mode.env"),
        (Join-Path $BetikDizini "..\deploy\$Mode.env")
    ) | Where-Object { Test-Path $_ } | Select-Object -First 1
}

function Read-PemfProfilEnv([string]$Dosya) {
    $d = [ordered]@{}
    foreach ($ln in (Get-Content $Dosya)) {
        $t = $ln.Trim()
        if ($t -and -not $t.StartsWith("#") -and $t.Contains("=")) {
            $k, $v = $t.Split("=", 2); $d[$k.Trim()] = $v.Trim()
        }
    }
    $d
}

# Servis ortamı: temel değerler + profil (aynı anahtarda profil kazanır) + bu betiğin güvenlik anahtarları. Profil yoksa $null.
# GÜVENLİK: tünel (internete açma) bu betikte YALNIZ -EnableTunnel ile açılır — profil açsa bile yalnız-LAN varsayılanı korunur;
# tünel açıksa kimlik doğrulama zorunlu; profilin kimlik doğrulama zorunluluğu hiçbir durumda GEVŞETİLMEZ.
function Get-PemfServisOrtami([string]$ProfilDosyasi, [string]$LogDir, [bool]$UsingExe, [string]$GuiRoot, [bool]$Tunel, [bool]$Kimlik) {
    if (-not $ProfilDosyasi) { return $null }
    $EnvMap = [ordered]@{ "PYTHONUNBUFFERED" = "1"; "PEMF_HEADLESS" = "1"; "PEMF_LOG_DIR" = $LogDir }
    $Profil = Read-PemfProfilEnv $ProfilDosyasi
    foreach ($k in $Profil.Keys) { $EnvMap[$k] = $Profil[$k] }
    if (-not $UsingExe) { $EnvMap["PYTHONPATH"] = $GuiRoot }
    $EnvMap["PEMF_ENABLE_TUNNEL"] = $(if ($Tunel) { "1" } else { "0" })
    if ($Tunel -or $Kimlik) { $EnvMap["PEMF_REQUIRE_AUTH"] = "1" }
    @($EnvMap.Keys | ForEach-Object { "$_=$($EnvMap[$_])" })
}

# Y44 (setup_services.ps1 ile BİREBİR — eşlik kapıda ölçülür): `PEMF_API_PORT` backend'in `ortam_portu` kuralıyla (Python `int()` — baş/son
# boşluk, isteğe bağlı +/-, rakamlar arasında tek `_`, Unicode ondalık rakamlar — ve 1..65535). Bu betik `.Hata` metnini KULLANMAZ.
function Test-PemfApiPortDegeri([AllowNull()][string]$Ham) {
    $sonuc = [pscustomobject]@{ Port = $null; Hata = "" }
    $m = [regex]::Match([string]$Ham, '^\s*([+-]?)(\d+(?:_\d+)*)\s*$')
    $deger = $null
    if ($m.Success) {
        $deger = [long]0
        foreach ($ch in $m.Groups[2].Value.ToCharArray()) {
            if ($ch -eq '_') { continue }
            $deger = $deger * 10 + [long][char]::GetNumericValue($ch)
            if ($deger -gt 65535) { break }
        }
        if ($m.Groups[1].Value -eq '-') { $deger = -$deger }
    }
    if ($null -ne $deger -and $deger -ge 1 -and $deger -le 65535) {
        $sonuc.Port = [int]$deger
    } else {
        $sonuc.Hata = "PEMF_API_PORT geçersiz: '$Ham' — 1-65535 arası tamsayı olmalı (backend bu değerde uyarıyla " +
            "8000'e düşer, kurulumun sağlık sondası yanlış porta bakar). Profil dosyasında düzeltin ya da satırı silin (varsayılan 8000)."
    }
    $sonuc
}

# D5 H-1: servisin GERÇEKTEN dinleyeceği API portu — servise giden ortamdaki (profil) `PEMF_API_PORT`, backend'in kuralıyla; yoksa ya da
# bozuksa backend gibi 8000 (`ortam_portu` bozuk değerde uyarıyla 8000'e düşer — kural da o portu açar). Eskiden güvenlik duvarı SABİT 8000
# açıyordu: profil başka port verirse backend o portta dinler, LAN'dan (mobil / web istemci) erişim engelli kalırdı.
function Get-PemfServisApiPortu([string[]]$AppEnv) {
    $Ham = $null
    foreach ($Satir in @($AppEnv)) {
        $Anahtar, $Deger = "$Satir".Split("=", 2)
        if ($Anahtar -eq 'PEMF_API_PORT') { $Ham = "$Deger" }
    }
    if ($null -eq $Ham) { return 8000 }
    $Port = (Test-PemfApiPortDegeri $Ham).Port
    if ($Port) { return $Port }
    Write-Status "UYARI: profildeki PEMF_API_PORT geçersiz ('$Ham') — backend uyarıyla 8000'e düşer; güvenlik duvarı kuralı 8000'i açar. Profil dosyasında düzeltin ya da satırı silin (1-65535 arası tamsayı)." "Yellow"
    return 8000
}

# D5 H-1 (DEV-C4 / G-2 sınıfı): 'PEMF Backend API' / 'PEMF UDP Discovery' kuralları eskiden YALNIZ ADIYLA aranıyordu — aynı adlı devre dışı /
# Block / giden / yanlış protokol / başka port (eski PEMF_API_PORT) / dar profilli / başka programın (taşınmış kurulum) kuralı "var" sayılıyor,
# servis LAN'dan (mobil / web istemci — ACİL DURDUR dahil) erişilemezken betik sessiz bitiyordu. İÇERİK setup_services.ps1 API döngüsüyle AYNI
# (İG-9.5 + 4B-3.5): protokol · port · program · etkin · Allow · Inbound · tüm profiller. Uymayan aynı adlı kural silinir; uyan kural yoksa
# doğrusu kurulur (çift kural yok); silinemez / kurulamaz → eylemli UYARI + $false. Uzak adres KAPSAMINA dokunulmaz (A-01: LAN güvenilir —
# yeni kural uzak adres vermeden kurulur, mevcut kuralın uzak adresi değiştirilmez). Son doğrulama adla değil içerikle → [bool] özete girer.
# (setup_services.ps1 ile ortak yardımcıya taşınabilir.) Kapı: tests/test_install_backend_service_FW_kurali_ICERIKLE_D5H1.py
function Ensure-PemfBackendFirewallKurali([string]$Ad, [string]$Protokol, [int]$Port, [string]$Program) {
    $IcerikUygun = {
        param($Kural)
        $PortFiltresi = $Kural | Get-NetFirewallPortFilter -ErrorAction SilentlyContinue
        $ProgramFiltresi = $Kural | Get-NetFirewallApplicationFilter -ErrorAction SilentlyContinue
        [bool]($PortFiltresi -and "$($PortFiltresi.Protocol)" -eq $Protokol -and "$($PortFiltresi.LocalPort)" -eq "$Port" -and
            $ProgramFiltresi -and "$($ProgramFiltresi.Program)" -eq $Program -and "$($Kural.Enabled)" -eq 'True' -and
            "$($Kural.Action)" -eq 'Allow' -and "$($Kural.Direction)" -eq 'Inbound' -and "$($Kural.Profile)" -eq 'Any')
    }
    $ElleKur = "New-NetFirewallRule -DisplayName '$Ad' -Direction Inbound -Program '$($Program -replace "'", "''")' -Action Allow -Protocol $Protokol -LocalPort $Port -Profile Any"
    $Silinemedi = $false
    $Uyan = 0
    foreach ($Kural in @(Get-NetFirewallRule -DisplayName $Ad -ErrorAction SilentlyContinue | Where-Object { $_ })) {
        if (& $IcerikUygun $Kural) { $Uyan++; continue }
        $PortFiltresi = $Kural | Get-NetFirewallPortFilter -ErrorAction SilentlyContinue
        $ProgramFiltresi = $Kural | Get-NetFirewallApplicationFilter -ErrorAction SilentlyContinue
        $Icerik = "$($PortFiltresi.Protocol) $($PortFiltresi.LocalPort), Program=$($ProgramFiltresi.Program), Enabled=$($Kural.Enabled), Action=$($Kural.Action), Direction=$($Kural.Direction), Profile=$($Kural.Profile)"
        try {
            $Kural | Remove-NetFirewallRule -ErrorAction Stop
            Write-Status "Firewall: '$Ad' adlı kuralın içeriği uymuyordu ($Icerik) -> silindi; doğrusu ($Protokol $Port, $Program) kurulacak." "Yellow"
        } catch {
            Write-Status "UYARI: '$Ad' adlı kuralın içeriği uymuyor ($Icerik) ve silinemedi ($_) — LAN'dan (mobil / web istemci) erişim engelli kalabilir. Elle: Remove-NetFirewallRule -DisplayName '$Ad'; $ElleKur" "Yellow"
            $Silinemedi = $true
        }
    }
    if ($Uyan -eq 0 -and -not $Silinemedi) {
        try {
            New-NetFirewallRule -DisplayName $Ad -Direction Inbound -Program $Program -Action Allow -Protocol $Protokol -LocalPort $Port -Profile Any -ErrorAction Stop | Out-Null
            Write-Status "Firewall: $Protokol $Port inbound eklendi ('$Ad')." "Green"
        } catch {
            Write-Status "UYARI: Firewall kuralı oluşturulamadı ($Ad): $_" "Yellow"
        }
    }
    # HER YOLDA yeniden sorgula — adla değil İÇERİKLE (cmdlet sessizce geçse ya da ilke kuralı devre dışı bıraksa da).
    $UyanKural = @(Get-NetFirewallRule -DisplayName $Ad -ErrorAction SilentlyContinue | Where-Object { $_ -and (& $IcerikUygun $_) })
    $Ok = $UyanKural.Count -gt 0 -and -not $Silinemedi
    if (-not $Ok -and -not $Silinemedi) {
        Write-Status "UYARI: '$Ad' ($Protokol $Port inbound, $Program) kuralı YOK -> LAN'dan (mobil / web istemci) erişim engellenebilir. MpsSvc (Windows Defender Firewall) servisi çalışıyor mu? (Get-Service MpsSvc) Kural elle: $ElleKur" "Yellow"
    }
    return [bool]$Ok
}

# --- Servis ikilisi: önce frozen EXE, yoksa python + backend_service.py ---
# Ortak argüman: Mosquitto kendi servisi olduğu için broker'ı backend BAŞLATMAZ,
# sadece izler -> --no-mosquitto-ensure.
# ⚠️ E2-2.6: host/port CLI'da SABİTLENMEZ (setup_services.ps1 ile aynı) — backend PEMF_API_HOST / PEMF_API_PORT'u profilden okur.
# Eskiden `--host 0.0.0.0 --port 8000` server.env'in `PEMF_API_HOST=127.0.0.1`'ini (yalnız ters vekil arkası) EZİYORDU.
$CommonArgs = @("--no-mosquitto-ensure")
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
        Write-Status "HATA: apps/backend/backend_service.py bulunamadı: $BackendFile" "Red"
        pause; exit 1
    }
    $SvcBinary       = $foundPython.Source
    $SvcArgs         = @("$BackendFile") + $CommonArgs
    $AppDir          = $GuiRoot
    $FirewallProgram = $foundPython.Source
    $UsingExe        = $false
    Write-Status "Frozen EXE yok; python+script (dev) ile: $SvcBinary" "Yellow"
}

# ── D2.73 (A-11): servis ortamı servise DOKUNMADAN ÖNCE kurulur — profil yoksa mevcut servis kaldırılmadan durulur ──
if ($EnableTunnel -and -not $RequireAuth) {
    Write-Status "Tünel açık -> PEMF_REQUIRE_AUTH otomatik ZORUNLU (public+kimliksiz engellendi)." "Yellow"
    $RequireAuth = $true
}
$ProfilDosyasi = Get-PemfProfilEnvDosyasi $AppDir $Mode $ScriptDir
$AppEnv = Get-PemfServisOrtami $ProfilDosyasi $LogDir $UsingExe $GuiRoot $EnableTunnel $RequireAuth
if (-not $AppEnv) {
    Write-Status "HATA: dağıtım profili deploy\$Mode.env bulunamadı ($AppDir / $ScriptDir\..) — at-rest şifreleme ve veri kökü KURULAMAZ; servis DEĞİŞTİRİLMEDİ." "Red"
    Write-Status "       Profili EXE'nin yanına (deploy\$Mode.env) koyun ya da depodaki betikten çalıştırın." "Red"
    pause; exit 1
}
Write-Status "Profil ($Mode): $ProfilDosyasi" "Cyan"

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

# Ortam değişkenleri — profil + güvenlik anahtarları (yukarıda, servise dokunmadan ÖNCE kuruldu: Get-PemfServisOrtami).
# GÜVENLİK: tünel (internete açma) VARSAYILAN KAPALI; açılırsa kimlik doğrulama OTOMATİK zorunlu.
# EXE'de PYTHONPATH'e gerek yok -> bundled modüller kullanılır.
& $NssmExe set $ServiceName AppEnvironmentExtra @AppEnv
if ($EnableTunnel) {
    Write-Status "Uzaktan erişim (Cloudflare tüneli) AÇIK + auth zorunlu. Token'ı istemcilere verin." "Cyan"
} else {
    Write-Status "Yalnız-LAN modu (tünel kapalı, güvenli). Uzaktan erişim için: -EnableTunnel" "Gray"
}

# --- Mosquitto: SCM bağımlılığı KULLANILMAZ (D2.73 — setup_services.ps1 ile aynı gerekçe) ---
# NSSM-managed mosquitto'da SCM bağımlılık çözümü güvenilmez: mosquitto Running olsa BİLE "Bağımlılık başlayamadı" (1068) →
# backend HİÇ başlamaz (ACİL DURDUR ucu da yok). Backend broker'a yeniden deneyerek bağlanır; ikisi de Automatic başlar.
if (Get-Service -Name "mosquitto" -ErrorAction SilentlyContinue) {
    Write-Status "mosquitto servisi var — backend broker'a yeniden deneyerek bağlanır (SCM bağımlılığı YOK)." "Green"
} else {
    Write-Status "UYARI: 'mosquitto' servisi yok. Önce install_mosquitto_service.ps1 çalıştırın." "Yellow"
}

# --- Firewall (API TCP <servis portu> + keşif UDP 5051) — adla değil İÇERİKLE (D5 H-1; bkz. Ensure-PemfBackendFirewallKurali) ---
# API portu servise giden ortamdan ($AppEnv → PEMF_API_PORT, backend'in kuralıyla); keşif portu backend'de sabit (headless_core: 5051).
$ApiPort = Get-PemfServisApiPortu $AppEnv
$ApiFirewallOk = $false
$KesifFirewallOk = $false
try {
    $ApiFirewallOk = Ensure-PemfBackendFirewallKurali -Ad "PEMF Backend API" -Protokol "TCP" -Port $ApiPort -Program $FirewallProgram
    $KesifFirewallOk = Ensure-PemfBackendFirewallKurali -Ad "PEMF UDP Discovery" -Protokol "UDP" -Port 5051 -Program $FirewallProgram
} catch {
    Write-Status "UYARI: Firewall kuralı denetlenemedi / eklenemedi: $_" "Yellow"
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
Write-Host "  URL    : http://localhost:$ApiPort"
Write-Host "  Loglar : $LogDir\backend_service.log"
Write-Host "  Profil : $ProfilDosyasi (at-rest şifreleme / veri kökü / STM portu / izinli adlar profilden)"
Write-Host "  Broker : mosquitto servisi (SCM bağımlılığı yok; backend yeniden dener)"
if ($ApiFirewallOk -and $KesifFirewallOk) {
    Write-Host "  Firewall: 'PEMF Backend API' (TCP $ApiPort) + 'PEMF UDP Discovery' (UDP 5051) içerikle doğrulandı"
} else {
    Write-Host "  Firewall: kural DOĞRULANAMADI — yukarıdaki UYARI'ya bakın; mobil / web istemci LAN'dan bağlanamayabilir." -ForegroundColor Yellow
}
Write-Host ""
Write-Host "Yönetim: $NssmExe (status|stop|start|restart|remove) $ServiceName"
Write-Host ""
pause
