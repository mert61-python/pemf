# =============================================================================
# PEMF Headless — KURULU layout için servis kurulumu (installer'dan çağrılır).
# -----------------------------------------------------------------------------
# PEMF_Backend_Setup.iss bunu [Run]'da çağırır: {app} dizinine kurulu EXE +
# bundled mosquitto'dan iki Windows servisini kurar (non-interaktif).
#
#   setup_services.ps1 -AppDir "C:\Program Files\PEMF Backend"
#   setup_services.ps1 -AppDir "..." -Uninstall
# =============================================================================
param(
    [string]$AppDir = "",
    [ValidateSet("device","server","staging")]
    [string]$Mode = "device",   # device=klinik (donanım+mosquitto) / server=demo (simülasyon) / staging=üretim-benzeri doğrulama (simülasyon, audit B-9.4)
    [switch]$Uninstall,
    [switch]$PurgeData,         # -Uninstall ile: hasta DB + şifreleme anahtarlarını da KALICI sil (KVKK; varsayılan KORU)
    # ⚠️ BİLİNÇLİ SAHİP KARARI (2026-08-04): hotspot SSID/parolası SABİTTİR
    # (`PEMF-Gateway` / `pemf1234`) ve her kurulan makinede AYNI kalacaktır — ESP bobinleri
    # (6-8) bu değerleri KENDİ firmware'lerinde (`secrets_coil_*.h`, bu depoda DEĞİL) taşır.
    # Bu iki parametre VERİLMEZSE davranış eski hâliyle BİREBİR aynıdır; yalnızca ileride
    # cihaz-başına parola istenirse (ESP reflash'ıyla BİRLİKTE) kullanılmak üzere vardır.
    # Verilirse C:\ProgramData\PEMF_System\hotspot.json'a yazılır ve start_hotspot.ps1 oradan okur.
    [string]$HotspotSsid = "",
    [string]$HotspotPass = ""
)
$ErrorActionPreference = "Continue"   # installer akışını tek bir hata kesmesin
# DENETİM 2026-09-06: Inno bu script'i 'runhidden' ile çalıştırır → Write-Host çıktısı HİÇBİR YERE
# gitmiyordu (konsol yok); firewall/mosquitto uyarıları sahada iz bırakmadan kayboluyordu. Şimdi her
# satır ayrıca $LogDir\setup_services.log'a eklenir. Loglama ASLA kurulumu düşürmez (try/catch boş).
# $LogDir aşağıda (satır ~36) tanımlanır — PowerShell çağrı anında çözer; yine de boşsa sabit yola düş.
function Log($m, $c = "White") {
    Write-Host "[setup-services] $m" -ForegroundColor $c
    try {
        $ld = if ($LogDir) { $LogDir } else { "C:\ProgramData\PEMF_System\logs" }
        New-Item -ItemType Directory -Path $ld -Force -ErrorAction SilentlyContinue | Out-Null
        Add-Content -Path (Join-Path $ld "setup_services.log") -Value ("{0} [setup-services] {1}" -f (Get-Date -Format o), $m) -Encoding UTF8 -ErrorAction Stop
    } catch { }
}

if (-not $AppDir) { $AppDir = Split-Path -Parent $MyInvocation.MyCommand.Path }

# ⚠️ D2.74 (B-9.7): servis adı, NSSM log dizini ve güvenlik duvarı kuralı KİPE bağlıdır. Staging (simülasyon; ayrı veri kökü
# C:\ProgramData\PEMF_Staging, port 8010 — deploy\staging.env) eskiden klinik servisiyle AYNI adı ("PemfBackend") kullanıyordu →
# tek saha makinesinde `-Mode staging` klinik backend'ini DURDURUP SİLİYOR, yerine PEMF_SIMULATE=1 + başka veri kökü koyuyordu
# (hasta/seans geçmişi "kaybolmuş" görünür, bobin sürülmez); zorla-öldürme de ADINA göre TÜM PEMF_Backend süreçlerini (klinik
# dahil) ACİL DURDUR'suz öldürüyordu; kaldırma ise klinik kurulumunu (ACİL DURDUR 8000, birleşik teardown) hedefliyordu.
# Kapı: tests/test_setup_services_STAGING_klinige_DOKUNMAZ_D274.py
$StagingMi      = ($Mode -eq "staging")
$ServiceBackend = if ($StagingMi) { "PemfBackendStaging" } else { "PemfBackend" }
$ServiceMosq    = "mosquitto"
# staging.env PEMF_LOG_DIR ile AYNI (kapı ikisini eşler).
$LogDir         = if ($StagingMi) { "C:\ProgramData\PEMF_Staging\logs" } else { "C:\ProgramData\PEMF_System\logs" }

# D2.74: zorla-öldürme YALNIZ bu kurulumun ({app}) PEMF_Backend süreçlerine — başka kurulumun (klinik servisi / launcher çocuğu)
# backend'i öldürülmez (bobinler hastanın üzerinde olabilir; ACİL DURDUR onun işi değil).
function Stop-PemfKurulumBackendi([string]$Dizin) {
    Get-CimInstance Win32_Process -Filter "Name='PEMF_Backend.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.ExecutablePath -and $_.ExecutablePath -like "$Dizin\*" } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
}
# NSSM: ÖNCE bundled (offline, {app}\_internal\bin\nssm) → yoksa C:\nssm → en son indir (internet).
# Offline klinikte internet gerekmesin diye nssm.exe EXE'ye bundle edildi (spec bin/nssm).
$NssmBundled    = Join-Path $AppDir "_internal\bin\nssm\nssm.exe"

# ⚠️ DENETİM 2026-08-04 (P2 — YEREL AYRICALIK YÜKSELTME): NSSM bir servis-SARMALAYICISIDIR;
# servisin ImagePath'i nssm.exe'dir ve `ObjectName LocalSystem` ile çalışır. Eski kod onu
# `C:\nssm\nssm.exe`'ye koyuyordu. `C:\` kökünün VARSAYILAN ACL'i
# `NT AUTHORITY\Authenticated Users:(OI)(CI)(IO)(M)` içerir → C:\ altında OLUŞTURULAN her dizin
# ve dosya, makinedeki HERHANGİ bir kimliği doğrulanmış (yönetici OLMAYAN) kullanıcı tarafından
# DEĞİŞTİRİLEBİLİR. Yani standart bir kullanıcı nssm.exe'yi kendi ikilisiyle değiştirip bir
# sonraki servis başlangıcında LocalSystem olarak kod çalıştırabilirdi.
# ÇÖZÜM: indirme hedefi korumalı dizine taşındı + dizin ACL'i açıkça sertleştiriliyor.
$NssmFallbackDir = "C:\Program Files\PEMF\nssm"
$NssmLegacyDir   = "C:\nssm"   # eski kurulumlar — bulunursa YERİNDE sertleştirilir

# Dizini SYSTEM+Administrators'a tam, Users'a yalnız OKU/ÇALIŞTIR olacak şekilde kilitle.
# SID kullanılır: Türkçe Windows'ta grup adları "Yöneticiler"/"Kullanıcılar"dır, isimle
# eşleşme SESSİZCE başarısız olurdu.
function Protect-PemfDir([string]$Dir) {
    if (-not (Test-Path $Dir)) { return }
    try {
        & icacls $Dir /inheritance:r `
            /grant '*S-1-5-18:(OI)(CI)F' `
            /grant '*S-1-5-32-544:(OI)(CI)F' `
            /grant '*S-1-5-32-545:(OI)(CI)RX' *>$null
        if ($LASTEXITCODE -eq 0) { Log "ACL sertlestirildi: $Dir (Users = salt oku/calistir)" "Green" }
        else { Log "UYARI: ACL sertlestirilemedi ($Dir) — icacls kodu $LASTEXITCODE" "Yellow" }
    } catch { Log "UYARI: ACL sertlestirilemedi ($Dir): $_" "Yellow" }
}
# Çözümleme sırası: bundled ({app}\_internal — Program Files, zaten korumalı)
#   → eski C:\nssm (VARSA kullan ama YERİNDE sertleştir; kurulumu bozmamak için)
#   → korumalı fallback (indirme buraya yapılır).
$NssmExe = if (Test-Path $NssmBundled) {
    $NssmBundled
} elseif (Test-Path (Join-Path $NssmLegacyDir "nssm.exe")) {
    Protect-PemfDir $NssmLegacyDir   # eski kurulumdaki AÇIK dizini kapat
    Join-Path $NssmLegacyDir "nssm.exe"
} else {
    Join-Path $NssmFallbackDir "nssm.exe"
}
$MosqInstallDir = "C:\Program Files\PEMF\mosquitto"
$MosqDataRoot   = "C:\ProgramData\PEMF_System\mosquitto"
# Mosquitto firewall kuralı: 'PEMF Mosquitto MQTT' = TCP 1883 inbound, YALNIZ hotspot subnet'i.
# P0-3 (GÜVENLİK): Broker'a 1883 yalnız HOTSPOT subnet'inden (ESP bobin 6-8, 192.168.137.x)
# erişilebilsin; klinik LAN'ından KAPALI. ESP firmware'i broker'a ANON bağlandığından
# (BLE provisioner kimlik göndermiyor) auth açılamaz → savunma: hotspot WPA2 + bu subnet
# kısıtı. Loopback (127.0.0.1) firewall'dan muaftır → backend localhost bağlantısı çalışır.
#
# DENETİM 2026-09-06: eski kod New-NetFirewallRule'u try/catch'siz, -ErrorAction Stop'suz ve
# SON-KONTROLSÜZ çağırıyordu. MpsSvc durmuşsa / GPO firewall'u kilitlediyse cmdlet hata akışına
# düşüp geçiyordu; 1883 loopback probe'u yine geçer, "Mosquitto hazır" loglanır, .install_verified
# yazılır → ESP bobin 6-8 broker'a ULAŞAMAZ ama yerel her gösterge YEŞİL, sıfır kanıt. Şimdi:
# try/catch + her yolda kuralı YENİDEN SORGULA + eylem söyleyen UYARI + [bool] dönüş (özet+bayrağa).
# Fonksiyon olarak ayrıldı ki testler installer'ı çalıştırmadan dot-source edip mock'la ölçebilsin.
#
# D3.42 (B-9.22): aynı adlı kural VARSA yalnız ADI yetmez — eski (06-27 öncesi) kurulumdan kalan `-RemoteAddress Any` kuralı "var"
# sayılıp 1883 her kaynağa açık kalıyordu; `install_mosquitto.ps1`'in RFC1918 'Mosquitto MQTT' kuralı ve native 'mosquitto' servisi
# (anonim broker) hiç görülmüyordu. İÇERİK okunur (uzak adres). ESP KAPALI (HEAD varsayılanı): geniş kural hotspot alt ağına
# daraltılır, RFC1918 kuralı kaldırılır. ESP ETKİN: hotspot dışındaki ESP'nin (bobin 8) STOP yolu kesilmesin diye DOKUNULMAZ, uyarılır
# (Y3 / A-04 — ESP dönüşüyle). Uzak adres OKUNAMAZSA değiştirilmez (bilinmeyen kurala yazılmaz), uyarılır, sonuç $false.
function Ensure-PemfMosquittoFirewallRule([bool]$EspEtkin = $false) {
    $MosqFirewallOk = $false
    $Hotspot = "192.168.137.0/24"
    $Genis = $false
    $Mevcut = @(Get-NetFirewallRule -DisplayName "PEMF Mosquitto MQTT" -ErrorAction SilentlyContinue | Where-Object { $_ })
    if ($Mevcut.Count -eq 0) {
        try {
            New-NetFirewallRule -DisplayName "PEMF Mosquitto MQTT" -Direction Inbound -Protocol TCP -LocalPort 1883 -RemoteAddress 192.168.137.0/24 -Action Allow -Profile Any -ErrorAction Stop | Out-Null
        } catch {
            Log "UYARI: Firewall kuralı oluşturulamadı (PEMF Mosquitto MQTT): $_" "Yellow"
        }
    }
    foreach ($Kural in $Mevcut) {
        $Adres = @(($Kural | Get-NetFirewallAddressFilter -ErrorAction SilentlyContinue).RemoteAddress | Where-Object { $_ })
        if ($Adres.Count -eq 1 -and $Adres[0] -eq $Hotspot) { continue }
        if ($Adres.Count -eq 0) {
            Log "UYARI: 'PEMF Mosquitto MQTT' kuralının uzak adresi OKUNAMADI — değiştirilmedi; 1883 geniş kaynağa açık olabilir. Elle bakın: Get-NetFirewallRule -DisplayName 'PEMF Mosquitto MQTT' | Get-NetFirewallAddressFilter" "Yellow"
            $Genis = $true
        } elseif ($EspEtkin) {
            Log "UYARI: 'PEMF Mosquitto MQTT' kuralı GENİŞ (uzak adres: $($Adres -join ',')) — ESP ETKİN: hotspot dışındaki ESP'nin STOP yolu kesilmesin diye DARALTILMADI (Y3 / A-04). ESP'ler 192.168.137.x'teyse elle: Set-NetFirewallRule -DisplayName 'PEMF Mosquitto MQTT' -RemoteAddress $Hotspot" "Yellow"
        } else {
            try {
                $Kural | Set-NetFirewallRule -RemoteAddress $Hotspot -ErrorAction Stop
                Log "'PEMF Mosquitto MQTT' kuralı daraltıldı: uzak adres $($Adres -join ',') -> $Hotspot (ESP kapalı)." "Yellow"
            } catch {
                Log "UYARI: 'PEMF Mosquitto MQTT' kuralı daraltılamadı ($_) — 1883 $($Adres -join ',') kaynağına AÇIK kaldı. Elle: Set-NetFirewallRule -DisplayName 'PEMF Mosquitto MQTT' -RemoteAddress $Hotspot" "Yellow"
                $Genis = $true
            }
        }
    }
    $Eski = @(Get-NetFirewallRule -DisplayName "Mosquitto MQTT" -ErrorAction SilentlyContinue | Where-Object { $_ })
    if ($Eski.Count -gt 0) {
        if ($EspEtkin) {
            Log "UYARI: install_mosquitto.ps1'in 'Mosquitto MQTT' kuralı (1883 <- RFC1918, klinik LAN) VAR — ESP ETKİN: kaldırılmadı (Y3 / A-04). ESP'ler hotspot alt ağındaysa elle: Remove-NetFirewallRule -DisplayName 'Mosquitto MQTT'" "Yellow"
        } else {
            try {
                $Eski | Remove-NetFirewallRule -ErrorAction Stop
                Log "install_mosquitto.ps1'in 'Mosquitto MQTT' kuralı (1883 <- RFC1918) kaldırıldı (ESP kapalı; broker yalnız hotspot alt ağından)." "Yellow"
            } catch {
                Log "UYARI: 'Mosquitto MQTT' kuralı (1883 <- RFC1918) kaldırılamadı ($_) — anonim broker klinik LAN'ına AÇIK. Elle: Remove-NetFirewallRule -DisplayName 'Mosquitto MQTT'" "Yellow"
                $Genis = $true
            }
        }
    }
    if (Get-Service -Name "mosquitto" -ErrorAction SilentlyContinue) {
        Log "UYARI: native 'mosquitto' Windows servisi kurulu (install_mosquitto*.ps1) — PEMF broker'ı NSSM ile '$ServiceMosq'; native servis anonim ikinci bir broker olabilir. Gerekmiyorsa: Stop-Service mosquitto; sc.exe delete mosquitto" "Yellow"
    }
    # HER YOLDA yeniden sorgula: cmdlet sessizce geçse de kural GERÇEKTEN var mı?
    $MosqFirewallOk = [bool](Get-NetFirewallRule -DisplayName "PEMF Mosquitto MQTT" -ErrorAction SilentlyContinue) -and -not $Genis
    if (-not $MosqFirewallOk -and -not $Genis) {
        Log "UYARI: 'PEMF Mosquitto MQTT' (TCP 1883 <- 192.168.137.0/24) kuralı YOK -> ESP bobin 6-8 broker'a ULAŞAMAZ. MpsSvc (Windows Defender Firewall) servisi çalışıyor mu? (Get-Service MpsSvc) GPO firewall'u kilitliyor mu? Kural elle: New-NetFirewallRule -DisplayName 'PEMF Mosquitto MQTT' -Direction Inbound -Protocol TCP -LocalPort 1883 -RemoteAddress 192.168.137.0/24 -Action Allow -Profile Any" "Yellow"
    }
    return [bool]$MosqFirewallOk
}
# D3.42: ESP alt sistemi (MQTT + ESP bobinleri) bu kurulumda ETKİN mi — backend `live_state.esp_etkin()` ile AYNI anlam ("1" = açık,
# varsayılan KAPALI). Servis ortamı profilden (NSSM AppEnvironmentExtra) gelir; profilde yoksa makine ortamı.
function Test-PemfEspEtkin($Profil, [AllowNull()][string]$MakineDegeri) {
    $v = if ($Profil -and $Profil.Contains('PEMF_ESP_ENABLED')) { [string]$Profil['PEMF_ESP_ENABLED'] } else { $MakineDegeri }
    return ("$v".Trim() -eq '1')
}

# ⚠️ Y44 (sahip — 1-B açık madde 5, i1-B3): `PEMF_API_PORT` backend'le AYNI kuralla doğrulanır
# (`backend_service.ortam_portu`: Python `int()` — baş/son boşluk, isteğe bağlı +/-, rakamlar arasında tek `_`,
# Unicode ondalık rakamlar — ve 1..65535). Eskiden hiç doğrulanmıyordu: servis bozuk değerle kuruluyor (backend uyarıyla
# 8000'e düşer) ve sağlık sondası HAM değeri URL'ye koyup "CİHAZ ÇALIŞMIYOR" diyordu. Eşlik Python'a karşı ÖLÇÜLÜR
# (`tests/test_setup_services_API_PORT_Y44.py`). Çalışma anındaki uyarılı 8000'e düşüş AYNEN kalır (ACİL DURDUR ucu).
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

# Dağıtım profili dosyası (deploy\<Mode>.env) — ön doğrulama ve servis env'i AYNI dosyayı AYNI ayrıştırmayla okur (Y44).
function Get-PemfProfilEnvDosyasi([string]$AppDir, [string]$Mode, [string]$BetikDizini) {
    @(
        (Join-Path $AppDir "_internal\deploy\$Mode.env"),
        (Join-Path $AppDir "deploy\$Mode.env"),
        (Join-Path $BetikDizini "..\deploy\$Mode.env")
    ) | Where-Object { Test-Path $_ } | Select-Object -First 1
}

# D3.08 + D3.29 (B-3.46 · B-10.69): NSSM ortamı günlüğe yazılırken SIR adlı anahtarların (PASS / TOKEN / SECRET / KEY /
# CREDENTIAL / PRIVATE / _PAT) DEĞERİ maskelenir, ad görünür kalır. Eskiden `$AppEnv -join` ham yazılıyordu: device.env'e girilen
# tünel belirteci ya da MQTT parolası ProgramData\PEMF_System\logs\setup_services.log'a (Users okuyabilir) düz düşerdi.
# Boş değer "(boş)" — operatör tanımsızı görsün. Fonksiyon: testler parser'la çekip ölçer.
function Format-PemfEnvGunluk([System.Collections.IDictionary]$EnvMap) {
    @($EnvMap.Keys | ForEach-Object {
        $v = [string]$EnvMap[$_]
        if ($_ -match '(?i)(PASS|TOKEN|SECRET|KEY|CREDENTIAL|PRIVATE|_PAT$)') {
            if ($v) { "$_=***" } else { "$_=(boş)" }
        } else { "$_=$v" }
    }) -join '  '
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

$MosqFirewallOk = $false   # server/staging modunda ve mosquitto yoksa da tanımlı olsun (özet + .install_verified)
$BackendExe     = Join-Path $AppDir "PEMF_Backend.exe"

# Bundled mosquitto kaynağı (PyInstaller onedir: {app}\_internal\bin\mosquitto)
$MosqSrc = Join-Path $AppDir "_internal\bin\mosquitto"
if (-not (Test-Path (Join-Path $MosqSrc "mosquitto.exe"))) {
    $alt = Join-Path $AppDir "bin\mosquitto"
    if (Test-Path (Join-Path $alt "mosquitto.exe")) { $MosqSrc = $alt }
}

# ⚠️ D2.74: staging KLİNİK servisinin kurulum dizinini PAYLAŞAMAZ. -AppDir verilmezse betiğin KENDİ dizini kullanılır → klinik
# kurulumundaki kopyayla `-Mode staging` koşulursa {app} süreç temizliği (kurulumda da kaldırmada da) klinik backend'ini ACİL
# DURDUR'suz öldürürdü. Klinik servisinin uygulaması (NSSM Parameters\Application) bu dizindeyse HİÇBİR şey değiştirilmeden durur.
if ($StagingMi) {
    $KlinikUygulamasi = $null
    try { $KlinikUygulamasi = (Get-ItemProperty -LiteralPath 'HKLM:\SYSTEM\CurrentControlSet\Services\PemfBackend\Parameters' -ErrorAction Stop).Application } catch { }
    if ($KlinikUygulamasi -and ("$KlinikUygulamasi".Trim('"') -like "$AppDir\*")) {
        Log "HATA: $AppDir KLİNİK servisinin (PemfBackend) kurulum dizini — staging buradan kurulamaz/kaldırılamaz (klinik backend'i durdurulurdu). Staging paketini AYRI bir dizine açıp -AppDir ile verin. Hiçbir şey değiştirilmedi." "Red"
        exit 1
    }
}

# ───────────────────────── UNINSTALL ─────────────────────────
if ($Uninstall) {
    Log "Servisler kaldırılıyor..." "Yellow"
    # ⚠️ D2.74: STAGING kaldırması YALNIZ kendi servisini / {app} süreçlerini / güvenlik duvarı kuralını kaldırır. Adla öldürme
    # (klinik backend'i, mosquitto'su), ACİL DURDUR yardımcısı (önce 8000'i — KLİNİK backend'i — dener) ve birleşik teardown
    # (klinik servisleri / kökleri / kimlikleri) staging'de ATLANIR: staging simülasyondur (bobin yok), klinik seansını kesmek
    # kabul edilemez. Graceful durdur → bekle → zorla-öldür SIRASI iki kipte de AYNI. Staging veri kökü KORUNUR.
    # KRİTİK: {app} altından çalışan TÜM süreçleri (backend + cloudflared-tünel + nssm) + mosquitto'yu ÖLDÜR →
    # dosya kilidi kalmasın ("bazı dosyalar kaldırılamadı / ille silin"i KÖKTEN önler). cloudflared tünel-watchdog
    # süreci {app}\bin\cloudflared'den çalışıp {app}'i kilitliyordu ve ESKİDEN öldürülmüyordu (asıl kalan-kilit nedeni).
    function Stop-AppProcs {
        Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $_.ExecutablePath -and $_.ExecutablePath -like "$AppDir\*" } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
        if (-not $StagingMi) { Get-Process cloudflared, nssm, mosquitto, PEMF_Backend -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue }
    }
    # ⚠️ D1.92 (B-9.23): aşağıdaki force-kill döngüsü ADINA göre TÜM `PEMF_Backend` süreçlerini öldürür — launcher'ın
    # doğurduğu backend dahil (onun servisi yoktur, `nssm stop` onu durdurmaz). Bobin HER kill'den önce durur: birleşik
    # teardown'ın ACİL DURDUR yardımcısı (backend.port → 8000 → 8001..8049) EN BAŞTA. Hatası kaldırmayı DURDURMAZ.
    $teardownScript = Join-Path $AppDir 'pemf_teardown.ps1'
    if (-not $StagingMi -and (Test-Path $teardownScript)) {
        . $teardownScript
        try { [void](Send-PemfAcilDurdur) } catch { Log "UYARI: ACİL DURDUR gönderilemedi ($_) — kaldırma sürüyor." "Yellow" }
    }
    # TIBBİ GÜVENLİK: kaldırmadan ÖNCE servisi GRACEFUL durdur — nssm stop → NSSM Ctrl+C
    # (AppStopMethodConsole 15s) → backend signal-handler → bobin STOP + STM kuyruk-flush. Servis
    # STOPPED olana kadar BEKLE ki bobinler (hasta üzerindeyse) güvene alınsın. Force-kill'i ÖNCE
    # yaparsak (aşağıdaki wait-loop) bu graceful bobin-STOP ATLANIR → bobinler firmware-watchdog'una
    # kadar açık kalır. Bu yüzden önce graceful-dur+bekle, SONRA remove + force-kill fallback.
    if (Test-Path $NssmExe) { & $NssmExe stop $ServiceBackend *>$null }
    for ($i = 0; $i -lt 40 -and ((Get-Service -Name $ServiceBackend -ErrorAction SilentlyContinue).Status -in @('Running', 'StopPending')); $i++) { Start-Sleep -Milliseconds 500 }
    if (Test-Path $NssmExe) { & $NssmExe remove $ServiceBackend confirm *>$null }
    # {app}'e ÖZGÜ FALLBACK: graceful başarısız/asılıysa, {app} altındaki TÜM süreçler GERÇEKTEN ölene
    # kadar force-kill → dosya kilidi bırakılsın, Inno {app}'i silebilsin (cloudflared {app}\bin'den kilit).
    for ($i = 0; $i -lt 30; $i++) {
        $alive = @(if (-not $StagingMi) { Get-Process PEMF_Backend, mosquitto, cloudflared, nssm -ErrorAction SilentlyContinue })
        $alive += @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $_.ExecutablePath -and $_.ExecutablePath -like "$AppDir\*" })
        if ($alive.Count -eq 0) { break }
        Stop-AppProcs
        Start-Sleep -Milliseconds 500
    }
    if ($StagingMi) {
        Remove-NetFirewallRule -DisplayName "PEMF Backend API (staging)" -ErrorAction SilentlyContinue
        if ($PurgeData) { Log "NOT: staging veri kökü bu betikle SİLİNMEZ — gerekmiyorsa elle silin: C:\ProgramData\PEMF_Staging" "Yellow" }
        Log "Staging kaldırıldı ($ServiceBackend); klinik kurulumuna dokunulmadı; veri kökü korundu: C:\ProgramData\PEMF_Staging" "Green"
        exit 0
    }

    # Geri kalan HER ŞEY = BİRLEŞİK TEARDOWN modülü (Faz 2 tek-kaynak): servis-sil/görev/firewall/env/
    # registry/veri + KVKK politikası. Eski dağınık inline mantık buraya konsolide edildi (client/gui/
    # standalone ile AYNI kod). -PurgeData => hasta verisi de silinir (varsayılan KORU).
    Set-Location $env:SystemRoot   # {app}'ten çık: teardown {app}'i de silebilir, CWD kilidi olmasın
    $teardownScript = Join-Path $AppDir 'pemf_teardown.ps1'
    if (Test-Path $teardownScript) {
        . $teardownScript
        # Denetim 2026-08-04: dönüş değeri yok sayılıyordu → kilitli dosya yüzünden eksik kalan
        # temizlik "başarılı" görünüyordu. Uninstall'ı BLOKLAMIYORUZ (kullanıcı takılı kalmasın)
        # ama durumu AÇIKÇA bildiriyoruz; ayrıntı teardown log'unda.
        if (-not (Invoke-PemfTeardown -Scope backend -IncludePatientData:$PurgeData)) {
            Log "UYARI: teardown EKSİK tamamlandı — bazı öğeler silinemedi (bkz. teardown log'u)." "Red"
        }
    } else {
        # Paketleme hatası / çok-eski kurulum: modül yok → en azından servisleri sil (uninstall bloklamasın).
        Log "UYARI: pemf_teardown.ps1 yok ($teardownScript) — asgari servis-silmeye düşülüyor." "Yellow"
        & sc.exe delete $ServiceBackend *>$null
        & sc.exe delete $ServiceMosq *>$null
    }
    exit 0
}

# ───────────────────── 0. ÖN DOĞRULAMA (Y44) ─────────────────────
# Bozuk `PEMF_API_PORT` → kurulum servis/broker/NSSM/güvenlik duvarı adımlarına BAŞLAMADAN açık hatayla durur
# (eski servis kaldırılıp yarım kurulum bırakılmaz). Kaldırma (-Uninstall) bu kapıya takılmaz.
$OnEnvFile = Get-PemfProfilEnvDosyasi $AppDir $Mode (Split-Path -Parent $MyInvocation.MyCommand.Path)
if ($OnEnvFile) {
    $OnProfil = Read-PemfProfilEnv $OnEnvFile
    if ($OnProfil.Contains("PEMF_API_PORT")) {
        $OnPort = Test-PemfApiPortDegeri $OnProfil["PEMF_API_PORT"]
        if ($OnPort.Hata) { Log "HATA: $($OnPort.Hata) Dosya: $OnEnvFile — kurulum DURDU, hiçbir servis değiştirilmedi." "Red"; exit 1 }
    }
}
# ⚠️ E2-2.4 (S-E.4): portu bu kurulumun DIŞINDAN bir süreç (launcher'ın backend çocuğu / başka kurulum) tutuyorsa sağlık sondası
# ONUN /api/health'inden 200 alır → "Kurulum DOĞRULANDI" + .install_verified; yeni servis bind edemeyip döngüde çöker. O süreç
# öldürülmez (ACİL DURDUR bu betiğin işi değil) — kurulum HİÇBİR şey değiştirmeden durur.
$OnSondaPort = if ($OnPort -and $OnPort.Port) { $OnPort.Port } else { 8000 }
foreach ($PortSahibi in @(Get-NetTCPConnection -LocalPort $OnSondaPort -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique)) {
    $SahipYolu = (Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessId -eq $PortSahibi } | Select-Object -First 1).ExecutablePath
    if (-not ($SahipYolu -and $SahipYolu -like "$AppDir\*")) {
        Log "HATA: port $OnSondaPort dolu — bu kurulumun DIŞINDA bir süreç dinliyor (PID $PortSahibi, $SahipYolu). Launcher'ın backend'i ya da başka bir kurulum olabilir; sağlık sondası onun yanıtını bu servisin sanırdı. Önce onu kapatın (launcher'dan çıkın) ya da profilde PEMF_API_PORT'u değiştirin — kurulum DURDU, hiçbir servis değiştirilmedi." "Red"
        exit 1
    }
}

New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
# Önceki çalıştırmanın başarı-bayrağını temizle — bu kurulum GERÇEKTEN doğrulanmadıkça
# Inno ".install_verified" görmesin (sessiz-başarıyı installer seviyesinde de kapatır).
Remove-Item (Join-Path $AppDir ".install_verified") -Force -ErrorAction SilentlyContinue

# ───────────────────── 1. MOSQUITTO SERVİSİ (yalnız KLİNİK) ─────────────────────
# Sunucu (server) + staging (audit B-9.4) simülasyon → donanım yok, MQTT broker GEREKMEZ, kurulmaz.
if ($Mode -eq "server" -or $Mode -eq "staging") {
    Log "$Mode modu: Mosquitto/MQTT atlandı (donanım yok, simülasyon)." "Gray"
} elseif (Test-Path (Join-Path $MosqSrc "mosquitto.exe")) {
    Log "Mosquitto servisi kuruluyor (bundled → $MosqInstallDir)..." "Yellow"
    New-Item -ItemType Directory -Path $MosqInstallDir, "$MosqDataRoot\data", "$MosqDataRoot\log", "$MosqDataRoot\conf.d" -Force | Out-Null

    # Varolan mosquitto servisini SAĞLAM kaldır — wedged "StartPending" servise dayanıklı.
    # NOT: Stop-Service -Force böyle bir serviste ASILIR (kurulum 5dk+ donar) → süreç-kill +
    # native uninstall + sc delete kullan (hiçbiri bloklamaz). Eski/kilitli kayıt kalmaz.
    $svc = Get-Service -Name $ServiceMosq -ErrorAction SilentlyContinue
    $mexe = Join-Path $MosqInstallDir "mosquitto.exe"
    if ($svc) {
        Get-Process mosquitto -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
        if (Test-Path $mexe) { & $mexe uninstall *>$null }                          # eski NATIVE servis kaydı
        if (Test-Path $NssmExe) { & $NssmExe remove $ServiceMosq confirm *>$null }   # eski NSSM-managed kayıt
        & sc.exe delete $ServiceMosq *>$null
        # Servisin TAM silinmesini bekle (marked-for-delete yarışı) — yoksa reinstall ESKİ parametreyi alır.
        for ($k = 0; $k -lt 15 -and (Get-Service -Name $ServiceMosq -ErrorAction SilentlyContinue); $k++) { Start-Sleep 1 }
    }

    # Copy-Item öncesi çalışan mosquitto'yu durdur — libcrypto-3-x64.dll kilidi re-install'da
    # kopyalamayı bozardı. -EA SilentlyContinue: fresh'te tümü kopyalanır, kilitliyse mevcut dosya kullanılır.
    Get-Process mosquitto -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 800
    Copy-Item -Path (Join-Path $MosqSrc "*") -Destination $MosqInstallDir -Recurse -Force -ErrorAction SilentlyContinue

    $conf = @"
# PEMF — yerel MQTT broker (installer ile kuruldu, otomatik üretildi)
listener 1883 0.0.0.0
allow_anonymous true
# persistence KAPALI: bozuk persistence-DB ('Unrecognised file format') brokeri kilitliyordu — mosquitto
# her acilista cokup NSSM throttle -> servis 'Paused' -> port 1883 kapali -> UI 'Sistem Baglantisi = Uyari'.
# Bundled config de false. Retained/kuyruk mesajlari ESP reconnect'te yeniden yayinlanir (kritik degil).
persistence false
max_queued_messages 10000
max_connections 30
max_keepalive 120
retain_available true
log_dest file $($MosqDataRoot -replace '\\','/')/log/mosquitto.log
log_type error
log_type warning
log_type notice
log_timestamp true
# A-04 / D1.104: yerel broker KIMLIGI. 'PEMF_Backend.exe --mqtt-kimlik hazirla' (ESP donusunde) bu dizine
# pemf_kimlik.conf (allow_anonymous false + password_file + acl_file) yazar; SONDA oldugu icin yukaridaki
# anonim izni EZER. Dizin bossa davranis bugunku gibidir (anonim). Bu satir HER ZAMAN en sonda kalmali.
include_dir $($MosqDataRoot -replace '\\','/')/conf.d
"@
    # include_dir'in dizini YOKSA mosquitto acilmaz → once olustur. Yerinde guncellemede hazirlanmis kimlik parcasi
    # KORUNUR; kaldir-kur 'mosquitto' dizinini siler → 'hazirla' yeniden calistirilir (kimlik deposu korundugu icin
    # parolalar AYNI kalir, yakilmis ESP'ler yine baglanir).
    New-Item -ItemType Directory -Force -Path "$MosqDataRoot\conf.d" | Out-Null
    # ⚠️ BOS include_dir'de mosquitto (Windows) ACILMAZ ("Unable to open include_dir", 2.0.18'de OLCULDU) → hazirlanmamis
    # her kurulumda broker duser ve ESP STOP yolu kopardi. Yalniz yorumdan olusan yer tutucu parca dizini bos birakmaz.
    $TabanParca = Join-Path $MosqDataRoot "conf.d\00_pemf_taban.conf"
    if (-not (Test-Path $TabanParca)) {
        Set-Content -Path $TabanParca -Value "# PEMF: include_dir bos kalmasin (mosquitto Windows'ta bos dizinde ACILMAZ). Kimlik parcasi: pemf_kimlik.conf" -Encoding ASCII
    }
    # BOŞLUKSUZ yola yaz (C:\ProgramData\...): NSSM AppParameters '-c <yol>' boşlukta bölünür;
    # "C:\Program Files\..." mosquitto'ya "C:\Program" olarak geçip "Unable to open config" verirdi.
    Set-Content -Path "$MosqDataRoot\mosquitto.conf" -Value $conf -Encoding ASCII

    # Firewall (TCP 1883 — yalnız hotspot subnet, ESP bobin 6-8). D3.42: ESP ETKİN mi — backend'in göreceği değer (profil > makine ortamı).
    $EspEtkin = Test-PemfEspEtkin $OnProfil ([Environment]::GetEnvironmentVariable('PEMF_ESP_ENABLED', 'Machine'))
    $MosqFirewallOk = Ensure-PemfMosquittoFirewallRule -EspEtkin $EspEtkin

    # KRİTİK FIX: mosquitto NATIVE servis ('mosquitto install' = 'mosquitto.exe run') YERİNE NSSM ile
    # FOREGROUND yönetilir. Native mod Windows'ta SERVICE_RUNNING sinyali VERMEYİP StartPending'de
    # TAKILIR → Start-Service sonsuza bekler (kurulum donar) + backend 'depend= mosquitto' yüzünden
    # hiç başlamaz. Foreground 'mosquitto.exe -c conf' SORUNSUZ çalışır (1883 açılır); NSSM süreç-
    # canlılığıyla Running raporlar → güvenilir, donma yok. (Doğrulama: SCM durumu değil, 1883 portu.)
    if (-not (Test-Path $NssmExe)) {
        Log "HATA: Mosquitto için NSSM gerekli ama bulunamadı ($NssmExe). MQTT kurulamadı." "Red"
        $MosqFailed = $true
    } else {
        $mconf = "$MosqDataRoot\mosquitto.conf"   # BOŞLUKSUZ (C:\ProgramData\...) — boşluk NSSM param'ını bölerdi
        & $NssmExe install $ServiceMosq $mexe *>$null
        & $NssmExe set $ServiceMosq AppParameters "-c $mconf" *>$null
        & $NssmExe set $ServiceMosq AppDirectory  $MosqInstallDir *>$null
        & $NssmExe set $ServiceMosq DisplayName    "PEMF Mosquitto Broker" *>$null
        & $NssmExe set $ServiceMosq Description     "PEMF yerel MQTT broker (ESP bobin 6-8)." *>$null
        & $NssmExe set $ServiceMosq Start           SERVICE_AUTO_START *>$null
        & $NssmExe set $ServiceMosq AppStdout       "$MosqDataRoot\log\nssm_mosquitto.log" *>$null
        & $NssmExe set $ServiceMosq AppStderr       "$MosqDataRoot\log\nssm_mosquitto.log" *>$null
        & $NssmExe set $ServiceMosq AppExit         Default Restart *>$null
        & $NssmExe set $ServiceMosq AppRestartDelay 3000 *>$null
        & $NssmExe set $ServiceMosq AppThrottle     3000 *>$null
        & $NssmExe start $ServiceMosq *>$null
        # GERÇEK fonksiyonel doğrulama: 1883 dinleniyor mu (SCM Running'e güvenme).
        $mqttOk = $false
        for ($i = 0; $i -lt 12; $i++) {
            Start-Sleep 1
            if (Get-NetTCPConnection -LocalPort 1883 -State Listen -ErrorAction SilentlyContinue) { $mqttOk = $true; break }
        }
        if ($mqttOk) {
            Log "Mosquitto hazır (NSSM, 1883 dinliyor)." "Green"
        } else {
            $mst = (& $NssmExe status $ServiceMosq 2>&1) -join ''
            Log "HATA: Mosquitto 1883'ü açmadı (nssm durum=$mst). Log: $MosqDataRoot\log\nssm_mosquitto.log" "Red"
            $MosqFailed = $true
        }
    }
} else {
    Log "UYARI: Bundled mosquitto bulunamadı ($MosqSrc). MQTT servisi atlandı." "Yellow"
}

# ───────────────────── 2. NSSM (yoksa indir) ─────────────────────
if (-not (Test-Path $NssmExe)) {
    # ⚠️ Bu ikili LocalSystem servisinin ImagePath'i olacak. İndirmenin BÜTÜNLÜK DOĞRULAMASI
    # YOKTUR (nssm.cc yayınlanmış bir SHA256 sağlamıyor) → yalnızca SON ÇARE. Normal kurulumda
    # bundled nssm ({app}\_internal\bin\nssm) kullanılır ve buraya HİÇ gelinmez.
    Log "UYARI: bundled NSSM yok → internetten indiriliyor. Bu indirme DOGRULANMIYOR;" "Yellow"
    Log "       tercih edilen yol bundled NSSM'dir (offline + dogrulanmis)." "Yellow"
    $NssmDestDir = Split-Path $NssmExe
    New-Item -ItemType Directory -Path $NssmDestDir -Force | Out-Null
    # ÖNCE kilitle: dosya oraya YAZILMADAN dizin korumalı olsun (yarış penceresini kapat).
    Protect-PemfDir $NssmDestDir
    # Paylaşımlı TEMP'te SABİT ad kullanmak, önceden yerleştirilmiş bir nssm.exe'nin
    # `Get-ChildItem -Recurse | Select -First 1` ile seçilmesine yol açabilir → benzersiz dizin.
    $tmpRoot = Join-Path $env:TEMP ("pemf_nssm_" + [guid]::NewGuid().ToString("N"))
    try {
        New-Item -ItemType Directory -Path $tmpRoot -Force | Out-Null
        $zip = Join-Path $tmpRoot "nssm.zip"
        Invoke-WebRequest "https://nssm.cc/release/nssm-2.24.zip" -OutFile $zip -UseBasicParsing -TimeoutSec 20
        Expand-Archive $zip (Join-Path $tmpRoot "ext") -Force
        $bin = Get-ChildItem (Join-Path $tmpRoot "ext") -Filter nssm.exe -Recurse | Where-Object { $_.FullName -like "*win64*" } | Select-Object -First 1
        if (-not $bin) { $bin = Get-ChildItem (Join-Path $tmpRoot "ext") -Filter nssm.exe -Recurse | Select-Object -First 1 }
        Copy-Item $bin.FullName $NssmExe -Force
        Protect-PemfDir $NssmDestDir   # kopyalama sonrası da doğrula
    } catch {
        Log "HATA: NSSM indirilemedi: $_" "Red"
    } finally {
        Remove-Item $tmpRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}

# ───────────────────── 3. BACKEND SERVİSİ (NSSM) ─────────────────────
if (-not (Test-Path $BackendExe)) { Log "HATA: Backend EXE yok: $BackendExe" "Red"; exit 1 }
if (-not (Test-Path $NssmExe))    { Log "HATA: NSSM yok, backend servisi kurulamadı." "Red"; exit 1 }

Log "Backend servisi kuruluyor: $BackendExe" "Yellow"
if (Get-Service -Name $ServiceBackend -ErrorAction SilentlyContinue) {
    & $NssmExe stop $ServiceBackend *>$null
    # Süreç gerçekten ölsün (nssm stop timeout'unu aşabilir) → marked-for-delete (1072) yarışını önler.
    # D2.74: YALNIZ bu kurulumun ({app}) backend'i — eskiden adına göre TÜMÜ (staging klinik backend'ini öldürürdü).
    Stop-PemfKurulumBackendi $AppDir
    & $NssmExe remove $ServiceBackend confirm *>$null
    # SABİT sleep yerine GERÇEK silinmeyi poll et (max ~20sn) → 1072 "marked for delete" yarışını önler
    $deadline = (Get-Date).AddSeconds(20)
    while ((Get-Service -Name $ServiceBackend -ErrorAction SilentlyContinue) -and (Get-Date) -lt $deadline) { Start-Sleep -Milliseconds 500 }
}
# Mosquitto kendi servisi olduğu için backend onu başlatmaz, sadece izler.
# host/port deploy\<Mode>.env'den (PEMF_API_HOST/PEMF_API_PORT) okunur; CLI'da SABİTLENMEZ
# → server modunda 127.0.0.1 (yalnız reverse-proxy arkası), device modunda 0.0.0.0 (LAN).
$installed = $false
for ($i = 0; $i -lt 5 -and -not $installed; $i++) {
    & $NssmExe install $ServiceBackend $BackendExe "--no-mosquitto-ensure"
    if ($LASTEXITCODE -eq 0) { $installed = $true; break }
    Log "nssm install denemesi $($i+1)/5 başarısız (exit=$LASTEXITCODE) — eski servis kaydı silinmemiş olabilir, bekleniyor..." "Yellow"
    Start-Sleep 3
}
if (-not $installed) { Log "HATA: Backend servisi KURULAMADI (nssm install exit=$LASTEXITCODE). Önceki servis kaydı temizlenemedi (1072?)." "Red"; exit 1 }
& $NssmExe set $ServiceBackend AppDirectory        $AppDir
& $NssmExe set $ServiceBackend DisplayName         "PEMF Backend Service"
& $NssmExe set $ServiceBackend Description          "Headless PEMF backend: FastAPI, WebSocket, STM32, MQTT, React Web."
& $NssmExe set $ServiceBackend Start                SERVICE_AUTO_START
& $NssmExe set $ServiceBackend ObjectName           LocalSystem
& $NssmExe set $ServiceBackend AppStdout            "$LogDir\backend_service_stdout.log"
& $NssmExe set $ServiceBackend AppStderr            "$LogDir\backend_service_stderr.log"
& $NssmExe set $ServiceBackend AppRotateFiles       1
& $NssmExe set $ServiceBackend AppRotateBytes       10485760
& $NssmExe set $ServiceBackend AppExit              Default Restart
& $NssmExe set $ServiceBackend AppRestartDelay      5000
& $NssmExe set $ServiceBackend AppStopMethodConsole 15000
& $NssmExe set $ServiceBackend AppThrottle          5000
# Dağıtım profili env'leri: deploy\<Mode>.env (device=klinik / server=demo). Bulunamazsa
# yalnız temel env yazılır. Profil değerleri temel değerleri override eder (aynı KEY → profil).
$EnvMap = [ordered]@{ "PYTHONUNBUFFERED" = "1"; "PEMF_HEADLESS" = "1"; "PEMF_LOG_DIR" = $LogDir }
$EnvFile = Get-PemfProfilEnvDosyasi $AppDir $Mode (Split-Path -Parent $MyInvocation.MyCommand.Path)
if ($EnvFile) {
    Log "Profil yükleniyor ($Mode): $EnvFile" "Cyan"
    $Profil = Read-PemfProfilEnv $EnvFile
    foreach ($k in $Profil.Keys) { $EnvMap[$k] = $Profil[$k] }
} else {
    Log "UYARI: deploy\$Mode.env bulunamadı; yalnız temel env yazıldı." "Yellow"
}
$AppEnv = @($EnvMap.Keys | ForEach-Object { "$_=$($EnvMap[$_])" })
& $NssmExe set $ServiceBackend AppEnvironmentExtra @AppEnv
Log ("Env (" + $Mode + "): " + (Format-PemfEnvGunluk $EnvMap)) "Gray"

# NOT: SCM 'depend= mosquitto' KULLANILMAZ. NSSM-managed mosquitto'da SCM bağımlılık çözümü
# güvenilmez (mosquitto Running olsa BİLE "Bağımlılık başlayamadı"/1068 → backend HİÇ başlamaz).
# Backend MQTT broker'a zaten retry ile bağlanır (ESP bobinleri dinamik bağlanır/kopar). mosquitto
# bu scriptte backend'den ÖNCE başlatılır; boot'ta ikisi de Automatic → paralel başlar, backend
# broker gelene kadar dener. (Bağımlılık eklemek backend'i başlatmamaya yol açıyordu.)

# Y44: sonda DOĞRULANMIŞ portu kullanır (ön doğrulama geçti; `+8000`/`08000` gibi geçerli yazımlar URL'yi bozmasın).
# D2.74: güvenlik duvarı API kuralı da AYNI portu açar (eskiden SABİT 8000 — staging 8010'u açmıyordu).
$probePort = if ($EnvMap.Contains('PEMF_API_PORT')) { (Test-PemfApiPortDegeri $EnvMap['PEMF_API_PORT']).Port } else { 8000 }

# D2.74: kural adı kipe bağlı — staging kuralı klinik kuralını ezmez / onunla karışmaz; staging keşif (UDP 5051) kuralı açmaz.
$FwKurallar = @(@{n = $(if ($StagingMi) { "PEMF Backend API (staging)" } else { "PEMF Backend API" }); p = "TCP"; port = $probePort })
if (-not $StagingMi) { $FwKurallar += @{n = "PEMF UDP Discovery"; p = "UDP"; port = 5051 } }
# ⚠️ İG-9.5 artığı (4-A devri #3): kural eskiden yalnız ADINA göre denetleniyordu ("bu adda kural VAR → atla"). Aynı adlı ESKİ
# bir kural farklı port (eski PEMF_API_PORT), protokol ya da program yolu (taşınmış kurulum) taşıyorsa düzeltilmiyor, backend
# yeni portta dinlerken LAN erişimi engelli kalıyordu. Kural İÇERİĞİYLE (protokol + port + program) doğrulanır; uymayan aynı
# adlı kurallar silinip doğrusu kurulur. Kapı: tests/test_setup_services_FW_kurali_ADLA_degil_ICERIKLE_IG95.py
foreach ($r in $FwKurallar) {
    $mevcut = @(Get-NetFirewallRule -DisplayName $r.n -ErrorAction SilentlyContinue)
    if ($mevcut.Count -gt 0) {
        $uygun = $true
        foreach ($k in $mevcut) {
            # Değişken adları bilinçli UZUN: iki harfli kısaltmalar taşınmış-dizin kapısının aradığı eski dizin adlarıyla çakışıyordu.
            $portFiltre = $k | Get-NetFirewallPortFilter -ErrorAction SilentlyContinue
            $uygFiltre = $k | Get-NetFirewallApplicationFilter -ErrorAction SilentlyContinue
            # 4B-3.4/4B-3.5: LAN erişimini belirleyen kural alanları da içeriktir — aynı adlı ama Block / devre dışı / giden / dar profilli
            # kural "uygun" sayılırsa backend dinler, LAN'dan erişim ENGELLİ kalır (health yalnız localhost'u ölçer).
            if (-not $portFiltre -or "$($portFiltre.Protocol)" -ne $r.p -or "$($portFiltre.LocalPort)" -ne "$($r.port)" -or
                -not $uygFiltre -or "$($uygFiltre.Program)" -ne $BackendExe -or "$($k.Enabled)" -ne 'True' -or
                "$($k.Action)" -ne 'Allow' -or "$($k.Direction)" -ne 'Inbound' -or "$($k.Profile)" -ne 'Any') { $uygun = $false }
        }
        if ($uygun) { continue }
        Log "Firewall kuralı '$($r.n)' farklı port/protokol/program/durumla VAR -> yeniden kuruluyor ($($r.p) $($r.port))." "Yellow"
        try { Remove-NetFirewallRule -DisplayName $r.n -ErrorAction Stop }
        catch { Log "UYARI: eski firewall kuralı silinemedi ($($r.n)): $_" "Yellow" }
    }
    try { New-NetFirewallRule -DisplayName $r.n -Direction Inbound -Program $BackendExe -Action Allow -Protocol $r.p -LocalPort $r.port -Profile Any -ErrorAction Stop | Out-Null }
    catch { Log "UYARI: Firewall kuralı oluşturulamadı ($($r.n)): $_. LAN'dan (mobil/web) erişim engellenebilir." "Yellow" }
}

& $NssmExe start $ServiceBackend *>$null   # 'SERVICE_START_PENDING' zararsız uyarısını sustur; gerçek kanıt /api/health
# ── GERÇEK fonksiyonel doğrulama (sessiz-başarıyı kapat) ──────────────────────────
# nssm status TEK BAŞINA yetmez: AppThrottle/Restart ile crash-loop'ta bile RUNNING görünür.
# Bu yüzden /api/health 200 esas kanıt. (device=0.0.0.0, server=127.0.0.1 → localhost ikisinde de çalışır.)
$healthOk = $false
for ($i = 1; $i -le 8; $i++) {
    Start-Sleep 3
    try {
        $resp = Invoke-WebRequest -Uri "http://localhost:$probePort/api/health" -UseBasicParsing -TimeoutSec 4
        if ($resp.StatusCode -eq 200) { $healthOk = $true; break }
    } catch { }
    Log "Backend bekleniyor ($i/8)..." "Gray"
}
if (-not $healthOk) {
    $st = (& $NssmExe status $ServiceBackend 2>&1) -join ''
    $tail = ""
    if (Test-Path "$LogDir\backend_service_stderr.log") { $tail = (Get-Content "$LogDir\backend_service_stderr.log" -Tail 25 -ErrorAction SilentlyContinue) -join "`n" }
    Log "HATA: Backend /api/health 200 vermedi (nssm durum=$st). CİHAZ ÇALIŞMIYOR." "Red"
    Log "Olası neden: VC++ runtime eksik (VCRUNTIME140.dll), port $probePort dolu, eksik DLL/import, bozuk env." "Red"
    Log "Son stderr ($LogDir\backend_service_stderr.log):`n$tail" "Red"
    exit 1
}
# At-rest şifreleme istendiyse GERÇEKTEN aktif mi? (KVKK: sqlcipher eksikse düz-metne sessiz fallback)
if ($EnvMap['PEMF_ENCRYPT_AT_REST'] -eq '1') {
    $enc = $null
    for ($i = 0; $i -lt 6; $i++) {
        try { $h = Invoke-RestMethod -Uri "http://localhost:$probePort/api/health" -TimeoutSec 4; if ($null -ne $h.atRestEncrypted) { $enc = [bool]$h.atRestEncrypted; break } } catch { }
        Start-Sleep 2
    }
    if ($enc -eq $false) { Log "HATA: PEMF_ENCRYPT_AT_REST=1 ama at-rest şifreleme AKTİF DEĞİL (sqlcipher binding eksik) → hasta PII düz-metne yazılıyor (KVKK riski). Build'i düzeltin." "Red"; exit 1 }
    elseif ($null -eq $enc) { Log "UYARI: atRestEncrypted doğrulanamadı (health geç yanıt). Manuel kontrol: /api/health." "Yellow" }
    else { Log "At-rest şifreleme DOĞRULANDI (atRestEncrypted=true)." "Green" }
}
if ($MosqFailed) { Log "UYARI: Backend çalışıyor AMA Mosquitto broker başlamadı → ESP bobinleri (6-8) bağlanamaz. Yukarıdaki mosquitto hatasını giderin." "Yellow" }
# DENETİM 2026-09-06: firewall kuralı yoksa broker yerelde çalışsa bile ESP 6-8 (hotspot subnet) erişemez → özette görünsün.
if ($Mode -eq "device" -and -not $MosqFirewallOk) { Log "UYARI: Mosquitto firewall kuralı (PEMF Mosquitto MQTT) DOĞRULANAMADI → ESP bobinleri (6-8) broker'a ulaşamaz. Yukarıdaki firewall uyarısındaki komutu elle çalıştırın." "Yellow" }
Log "Kurulum DOĞRULANDI → http://localhost:$probePort (mosqFirewall=$MosqFirewallOk)" "Green"
# Başarı-bayrağı: Inno bunu [Code] ssPostInstall'da kontrol eder (PowerShell exit kodu Inno'da güvenilmez).
# Inno yalnız VARLIĞA bakar (FileExists), içeriği ayrıştırmaz → 1. satır zaman damgası, 2. satır firewall kanıtı.
Set-Content -Path (Join-Path $AppDir ".install_verified") -Value @((Get-Date -Format o), "mosqFirewall=$MosqFirewallOk") -Encoding ASCII -ErrorAction SilentlyContinue

# ───────────────────── HOTSPOT (PEMF-Gateway WiFi — yalnız KLİNİK/device) ─────────────────────
# ESP bobinleri (6-8) bu WiFi'ye bağlanıp yerel mosquitto'ya (1883) MQTT yapar. Windows Mobile Hotspot
# KULLANICI OTURUMU ister (LocalSystem servisi/session-0 başlatamaz) → (1) logon Scheduled Task ile her
# açılışta kullanıcı oturumunda başlat (eski GUI sistem davranışı) + (2) kurulumda bir kez hemen başlat.
if ($Mode -eq "device") {
    $hotspotPs = Join-Path $AppDir "start_hotspot.ps1"
    if (Test-Path $hotspotPs) {
        # Hotspot kimliğini TEK KAYNAĞA yaz (start_hotspot.ps1 buradan okur; script'te literal YOK).
        # Yalnız operatör değer verdiyse yazılır — verilmezse dosya oluşturulmaz ve script eski
        # varsayılana düşüp UYARI loglar (sahadaki mevcut ESP'ler bozulmaz).
        if ($HotspotSsid -or $HotspotPass) {
            try {
                $hcDir = "C:\ProgramData\PEMF_System"
                if (-not (Test-Path $hcDir)) { New-Item -ItemType Directory -Path $hcDir -Force | Out-Null }
                $hcPath = Join-Path $hcDir "hotspot.json"
                $hcObj  = @{
                    ssid = $(if ($HotspotSsid) { $HotspotSsid } else { "PEMF-Gateway" })
                    pass = $HotspotPass
                }
                ($hcObj | ConvertTo-Json -Compress) | Set-Content -LiteralPath $hcPath -Encoding UTF8
                Log "Hotspot kimliği yazıldı: $hcPath (SSID=$($hcObj.ssid))" "Green"
                Log "HATIRLATMA: parola değiştiyse ESP bobinleri 6-8 secrets_coil_*.h ile YENİDEN FLASH'LANMALI." "Yellow"
            } catch { Log "hotspot.json yazılamadı: $_" "Yellow" }
        } else {
            Log "Hotspot kimliği verilmedi → varsayılan SSID/parola kullanılacak (bilinçli karar; ESP 6-8 firmware'iyle eşleşir)." "Gray"
        }
        # LattePanda 3 = Intel AX201 → legacy hosted-network YOK (Intel SoftAP'yi AX2xx'te kaldırdı); tek yol WinRT
        # Mobile Hotspot, o da KULLANICI OTURUMU ister (LocalSystem servisi/session-0 AÇAMAZ). Bu yüzden logon-task +
        # keep-alive: ICS Mobile-Hotspot ~4dk boşta kapanır → idempotent script'i her 3dk tekrar çalıştır.
        # SESSİZ başlatıcı: task, kullanıcı oturumunda logon'da + her 3dk çalıştığı için powershell.exe
        # GÖRÜNÜR konsol penceresi (flash) açardı → user-friendly'yi bozar. wscript, VBS'i PENCERESİZ (0)
        # çalıştırır → hiçbir pencere görünmez. VBS kendi klasöründeki start_hotspot.ps1'i gizli başlatır.
        $hotspotVbs = Join-Path $AppDir "start_hotspot_hidden.vbs"
        $vbsBody = @'
Dim sh, fso, ps1
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
ps1 = fso.GetParentFolderName(WScript.ScriptFullName) & "\start_hotspot.ps1"
sh.Run "powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & ps1 & """", 0, False
'@
        Set-Content -Path $hotspotVbs -Value $vbsBody -Encoding ASCII
        try {
            $act = New-ScheduledTaskAction -Execute "wscript.exe" -Argument "`"$hotspotVbs`""
            $trg = New-ScheduledTaskTrigger -AtLogOn
            $trg.Repetition = (New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 3)).Repetition
            $prn = New-ScheduledTaskPrincipal -GroupId "S-1-5-32-545" -RunLevel Highest   # BUILTIN\Users = interaktif oturum
            $set = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
            $set.Hidden = $true
            Register-ScheduledTask -TaskName "PEMF-Hotspot" -Action $act -Trigger $trg -Principal $prn -Settings $set -Force -ErrorAction Stop | Out-Null
            Log "Hotspot logon-task + keep-alive kuruldu (PEMF-Hotspot: logon'da + her 3dk; SESSİZ/penceresiz)." "Green"
        } catch {
            schtasks /Create /TN "PEMF-Hotspot" /TR "wscript.exe `"$hotspotVbs`"" /SC ONLOGON /RL HIGHEST /F *>$null   # keep-alive'siz fallback
            Log "Hotspot logon-task kuruldu (keep-alive'siz fallback, sessiz): $_" "Yellow"
        }
        # ICS/Mobile Hotspot reboot-persistence + servisleri Otomatik (AP yeniden başlatmadan sonra geri gelsin)
        reg add "HKLM\Software\Microsoft\Windows\CurrentVersion\SharedAccess" /v EnableRebootPersistConnection /t REG_DWORD /d 1 /f *>$null
        Set-Service -Name SharedAccess -StartupType Automatic -ErrorAction SilentlyContinue
        Set-Service -Name icssvc -StartupType Automatic -ErrorAction SilentlyContinue
        # Kurulumda BİR KEZ hemen başlat (installer elevated-kullanıcı oturumu → WinRT çalışır)
        & powershell.exe -NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File $hotspotPs 2>&1 | ForEach-Object { Log "  [hotspot] $_" "Gray" }
        # AUTO-LOGON kontrolü: hotspot oturum ister; auto-logon yoksa açılışta kimse login olana kadar başlamaz.
        $alog = (Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon' -ErrorAction SilentlyContinue).AutoAdminLogon
        if ("$alog" -ne "1") { Log "UYARI: AUTO-LOGON KAPALI → açılışta hotspot OTOMATİK başlamaz. Klinikte auto-logon AÇILMALI (netplwiz)." "Red" }
    } else {
        Log "UYARI: start_hotspot.ps1 yok → PEMF-Gateway hotspot otomatik başlamayacak (ESP'ler bağlanamaz)." "Yellow"
    }
}
