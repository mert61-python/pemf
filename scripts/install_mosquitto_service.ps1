# =============================================================================
# PEMF — Mosquitto'yu BAĞIMSIZ Windows Servisi olarak kurar (OFFLINE / mühürlü)
# =============================================================================
# Faz 3 hedefi: 24/7 sunucuda Mosquitto kendi otomatik-başlayan Windows servisi
# olsun; PemfBackend servisi ona `depends` ile bağlansın. Bu script bundle'daki
# bin\mosquitto\ ikilisini kullanır — internet GEREKMEZ (sahada offline kurulum).
#
# Kullanım (Yönetici PowerShell):
#   .\install_mosquitto_service.ps1
#   .\install_mosquitto_service.ps1 -Uninstall
# =============================================================================
param(
    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"

function Write-Status($msg, $color = "White") {
    $ts = Get-Date -Format "HH:mm:ss"
    Write-Host "[$ts] $msg" -ForegroundColor $color
}

# ESP alt sistemi (MQTT + ESP bobinleri) ETKİN mi — backend `live_state.esp_etkin()` ile AYNI anlam ("1" = açık, varsayılan KAPALI).
# setup_services.ps1'deki Test-PemfEspEtkin ile BİREBİR (eşlik kapıda ölçülür). Bu betik profil okumaz (bkz. adım 5).
function Test-PemfEspEtkin($Profil, [AllowNull()][string]$MakineDegeri) {
    $v = if ($Profil -and $Profil.Contains('PEMF_ESP_ENABLED')) { [string]$Profil['PEMF_ESP_ENABLED'] } else { $MakineDegeri }
    return ("$v".Trim() -eq '1')
}

# D5 G-2 (DEV-C4 sınıfı): 'PEMF Mosquitto MQTT' kuralı eskiden YALNIZ ADIYLA aranıyordu — aynı adlı devre dışı / Block / giden / UDP / başka
# port / dar profilli kural "var" sayılıyor, uzak adresi Any olan eski kural (P0-3) anonim broker'ı klinik LAN'ına açık bırakıyordu; hiçbiri
# söylenmeden "✓ çalışıyor" basılıyordu. setup_services.ps1 `Ensure-PemfMosquittoFirewallRule` (D3.42 + DEV-C4) ile AYNI sözleşme: İÇERİK
# doğrulanır (TCP · 1883 · Inbound · Allow · etkin · tüm profiller; uzak adres yalnız hotspot alt ağı). ESP KAPALI: uymayan kural silinip
# doğrusu kurulur, geniş adres daraltılır. ESP ETKİN: dokunulmaz (Y3 / A-04), eylemli UYARI. Uzak adres okunamazsa değiştirilmez. Son
# doğrulama adla değil içerikle; sonuç [bool] kurulum özetine girer. (setup_services.ps1 ile ortak yardımcıya taşınabilir.)
# Kapı: tests/test_install_mosquitto_service_FW_kurali_ICERIKLE_D5G2.py
function Ensure-PemfMosquittoServisFirewallRule([bool]$EspEtkin = $false) {
    $Ad = "PEMF Mosquitto MQTT"
    $Hotspot = "192.168.137.0/24"
    $Genis = $false
    $IcerikUymuyor = $false
    $SilinenKural = 0
    $IcerikUygun = {
        param($Kural)
        $PortFiltresi = $Kural | Get-NetFirewallPortFilter -ErrorAction SilentlyContinue
        [bool]($PortFiltresi -and "$($PortFiltresi.Protocol)" -eq 'TCP' -and "$($PortFiltresi.LocalPort)" -eq '1883' -and
            "$($Kural.Enabled)" -eq 'True' -and "$($Kural.Action)" -eq 'Allow' -and "$($Kural.Direction)" -eq 'Inbound' -and "$($Kural.Profile)" -eq 'Any')
    }
    $ElleKur = "New-NetFirewallRule -DisplayName '$Ad' -Direction Inbound -Protocol TCP -LocalPort 1883 -RemoteAddress $Hotspot -Action Allow -Profile Any"
    $Mevcut = @(Get-NetFirewallRule -DisplayName $Ad -ErrorAction SilentlyContinue | Where-Object { $_ })
    foreach ($Kural in $Mevcut) {
        if (-not (& $IcerikUygun $Kural)) {
            $PortFiltresi = $Kural | Get-NetFirewallPortFilter -ErrorAction SilentlyContinue
            $Icerik = "$($PortFiltresi.Protocol) $($PortFiltresi.LocalPort), Enabled=$($Kural.Enabled), Action=$($Kural.Action), Direction=$($Kural.Direction), Profile=$($Kural.Profile)"
            if ($EspEtkin) {
                Write-Status "UYARI: '$Ad' adlı kural VAR ama içeriği TCP 1883 Inbound Allow (etkin, tüm profiller) DEĞİL ($Icerik) — ESP ETKİN: DOKUNULMADI (Y3 / A-04); ESP bobinleri (6-8) broker'a ulaşamayabilir. Elle: Remove-NetFirewallRule -DisplayName '$Ad'; $ElleKur" "Yellow"
                $IcerikUymuyor = $true
            } else {
                try {
                    $Kural | Remove-NetFirewallRule -ErrorAction Stop
                    $SilinenKural++
                    Write-Status "'$Ad' adlı kuralın içeriği uymuyordu ($Icerik) -> silindi; doğrusu (TCP 1883 <- $Hotspot) kurulacak." "Yellow"
                } catch {
                    Write-Status "UYARI: '$Ad' adlı kuralın içeriği uymuyor ($Icerik) ve silinemedi ($_) — ESP bobinleri (6-8) broker'a ulaşamayabilir. Elle: Remove-NetFirewallRule -DisplayName '$Ad'; $ElleKur" "Yellow"
                    $IcerikUymuyor = $true
                }
            }
            continue
        }
        $Adres = @(($Kural | Get-NetFirewallAddressFilter -ErrorAction SilentlyContinue).RemoteAddress | Where-Object { $_ })
        if ($Adres.Count -eq 1 -and $Adres[0] -eq $Hotspot) { continue }
        if ($Adres.Count -eq 0) {
            Write-Status "UYARI: '$Ad' kuralının uzak adresi OKUNAMADI — değiştirilmedi; 1883 geniş kaynağa açık olabilir. Elle bakın: Get-NetFirewallRule -DisplayName '$Ad' | Get-NetFirewallAddressFilter" "Yellow"
            $Genis = $true
        } elseif ($EspEtkin) {
            Write-Status "UYARI: '$Ad' kuralı GENİŞ (uzak adres: $($Adres -join ',')) — ESP ETKİN: hotspot dışındaki ESP'nin STOP yolu kesilmesin diye DARALTILMADI (Y3 / A-04). ESP'ler 192.168.137.x'teyse elle: Set-NetFirewallRule -DisplayName '$Ad' -RemoteAddress $Hotspot" "Yellow"
        } else {
            try {
                $Kural | Set-NetFirewallRule -RemoteAddress $Hotspot -ErrorAction Stop
                Write-Status "'$Ad' kuralı daraltıldı: uzak adres $($Adres -join ',') -> $Hotspot (ESP kapalı)." "Yellow"
            } catch {
                Write-Status "UYARI: '$Ad' kuralı daraltılamadı ($_) — 1883 $($Adres -join ',') kaynağına AÇIK kaldı. Elle: Set-NetFirewallRule -DisplayName '$Ad' -RemoteAddress $Hotspot" "Yellow"
                $Genis = $true
            }
        }
    }
    # Hiç kural yoktu ya da hepsi içerik uymadığı için silindi → doğrusu kurulur (uyan kural kaldıysa çift kural kurulmaz).
    # P0-3 (GÜVENLİK): 1883 yalnız hotspot subnet'inden (ESP bobinleri) — klinik LAN'a KAPALI.
    # (ESP anon bağlandığından MQTT auth açılamaz; savunma hotspot WPA2 + subnet kısıtı.)
    if ($Mevcut.Count -eq $SilinenKural -and -not $IcerikUymuyor) {
        try {
            New-NetFirewallRule -DisplayName $Ad -Direction Inbound -Protocol TCP -LocalPort 1883 -RemoteAddress $Hotspot -Action Allow -Profile Any -ErrorAction Stop | Out-Null
            Write-Status "Firewall kuralı eklendi: TCP 1883 inbound (yalnız hotspot subnet $Hotspot)." "Green"
        } catch {
            Write-Status "UYARI: Firewall kuralı oluşturulamadı ($Ad): $_" "Yellow"
        }
    }
    # HER YOLDA yeniden sorgula — adla değil İÇERİKLE (cmdlet sessizce geçse ya da ilke kuralı devre dışı bıraksa da).
    $UyanKural = @(Get-NetFirewallRule -DisplayName $Ad -ErrorAction SilentlyContinue | Where-Object { $_ -and (& $IcerikUygun $_) })
    $Ok = $UyanKural.Count -gt 0 -and -not $Genis -and -not $IcerikUymuyor
    if (-not $Ok -and -not $Genis -and -not $IcerikUymuyor) {
        Write-Status "UYARI: '$Ad' (TCP 1883 <- $Hotspot) kuralı YOK -> ESP bobin 6-8 broker'a ULAŞAMAZ. MpsSvc (Windows Defender Firewall) servisi çalışıyor mu? (Get-Service MpsSvc) GPO firewall'u kilitliyor mu? Kural elle: $ElleKur" "Yellow"
    }
    return [bool]$Ok
}

# --- Admin kontrolü ---
$principal = New-Object System.Security.Principal.WindowsPrincipal([System.Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([System.Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Status "HATA: Bu script Yönetici (Administrator) olarak çalıştırılmalıdır." "Red"
    exit 1
}

# --- Yollar ---
$ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$GuiRoot     = Split-Path -Parent $ScriptDir
$BundledDir  = Join-Path $GuiRoot "bin\mosquitto"
$InstallDir  = "C:\Program Files\PEMF\mosquitto"
$DataRoot    = "C:\ProgramData\PEMF_System\mosquitto"
$DataDir     = "$DataRoot\data"
$LogDir      = "$DataRoot\log"
$ConfDir     = "$DataRoot\conf.d"
$ServiceName = "mosquitto"
$ExePath     = Join-Path $InstallDir "mosquitto.exe"
$ConfPath    = Join-Path $InstallDir "mosquitto.conf"

# --- Uninstall yolu ---
if ($Uninstall) {
    Write-Status "Mosquitto servisi kaldırılıyor..." "Yellow"
    $svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
    if ($svc) {
        if ($svc.Status -eq "Running") { Stop-Service -Name $ServiceName -Force; Start-Sleep 2 }
        if (Test-Path $ExePath) { & $ExePath uninstall 2>$null }
        Start-Sleep 1
    }
    Write-Status "Tamamlandı. (Veri/log korundu: $DataRoot)" "Green"
    exit 0
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  PEMF — Mosquitto Bağımsız Servis Kurulumu" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# --- 1. Bundle kontrolü ---
if (-not (Test-Path (Join-Path $BundledDir "mosquitto.exe"))) {
    Write-Status "HATA: Bundle'da mosquitto.exe yok: $BundledDir" "Red"
    exit 1
}
Write-Status "Bundle bulundu: $BundledDir" "Green"

# --- 2. Dizinleri oluştur ---
foreach ($d in @($InstallDir, $DataDir, $LogDir, $ConfDir)) {
    if (-not (Test-Path $d)) { New-Item -ItemType Directory -Path $d -Force | Out-Null }
}
# ⚠️ 1-G inceleme G-3.3: BOŞ include_dir'de mosquitto 2.0.18 (Windows) AÇILMAZ ("Unable to open include_dir", ölçüldü —
# bu betiğin yapılandırmasıyla da). conf.d yalnız oluşturulursa hazırlanmamış her kurulumda servis düşer (ESP STOP yolu
# backend'in yedek broker'ına kalır). Yalnız yorumdan oluşan yer tutucu dizini boş bırakmaz (setup_services.ps1 ile aynı);
# yerel broker kimliği (A-04 · D1.104 `--mqtt-kimlik hazirla`) bu dizine pemf_kimlik.conf yazar.
$TabanParca = Join-Path $ConfDir "00_pemf_taban.conf"
if (-not (Test-Path $TabanParca)) {
    Set-Content -Path $TabanParca -Value "# PEMF: include_dir bos kalmasin (mosquitto Windows'ta bos dizinde ACILMAZ). Kimlik parcasi: pemf_kimlik.conf" -Encoding ASCII
}
Write-Status "Dizinler hazır (Program Files + ProgramData)." "Green"

# --- 3. Bundled ikilileri Install dizinine kopyala (varolan servisi durdurarak) ---
$svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($svc -and $svc.Status -eq "Running") {
    Write-Status "Mevcut mosquitto servisi durduruluyor (dosya kilidi için)..." "Yellow"
    Stop-Service -Name $ServiceName -Force
    Start-Sleep 2
}
Copy-Item -Path (Join-Path $BundledDir "*") -Destination $InstallDir -Recurse -Force
Write-Status "Bundled ikililer kopyalandı: $InstallDir" "Green"

# --- 4. Sertleştirilmiş mosquitto.conf yaz ---
# ESP32 cihazları izole hotspot/LAN üzerinden bağlanır; broker yereldir.
$conf = @"
# PEMF — yerel MQTT broker (Faz 3, bağımsız servis). Otomatik üretildi.
listener 1883 0.0.0.0
allow_anonymous true

# persistence KAPALI: bozuk persistence-DB brokeri kilitliyordu (mosquitto cokup NSSM throttle ->
# servis 'Paused' -> port 1883 kapali). Bundled config de false; ESP durumu reconnect'te yeniden yayinlanir.
persistence false

# Mesaj kuyruğu (ESP'ler offline'dayken biriken mesajlar)
max_queued_messages 10000
max_queued_bytes 0
max_inflight_messages 40

# Bağlantı/keepalive limitleri (8 ESP + backend + yedek)
max_connections 30
max_keepalive 120
retain_available true

# Loglama
log_dest file $($LogDir -replace '\\','/')/mosquitto.log
log_type error
log_type warning
log_type notice
log_type information
log_timestamp true
log_timestamp_format %Y-%m-%dT%H:%M:%S

# Opsiyonel bridge (internet varsa) buraya .conf bırakılabilir
include_dir $($ConfDir -replace '\\','/')
"@
Set-Content -Path $ConfPath -Value $conf -Encoding ASCII
Write-Status "Sertleştirilmiş mosquitto.conf yazıldı: $ConfPath" "Green"

# --- 5. Firewall (TCP 1883) — adla değil İÇERİKLE (D5 G-2; bkz. Ensure-PemfMosquittoServisFirewallRule) ---
# ESP kipi backend'in göreceği değerden: bu betik profil okumaz — A-11 yolunda backend servisi (install_backend_service.ps1) makine ortamını
# devralır, deploy\<Mode>.env PEMF_ESP_ENABLED taşımaz (taşırsa setup_services.ps1 gibi profil de okunmalı).
$MosqFirewallOk = Ensure-PemfMosquittoServisFirewallRule -EspEtkin (Test-PemfEspEtkin $null ([Environment]::GetEnvironmentVariable('PEMF_ESP_ENABLED', 'Machine')))

# --- 6. Servisi (yeniden) kaydet ---
if ($svc) {
    Write-Status "Eski servis kaydı kaldırılıyor..." "Yellow"
    & $ExePath uninstall 2>$null
    Start-Sleep 1
}
Write-Status "Mosquitto servis olarak kaydediliyor (native install)..." "Yellow"
& $ExePath install
Start-Sleep 2

# mosquitto native servisi config'i exe yanından okur; otomatik başlatma + başlat
Set-Service -Name $ServiceName -StartupType Automatic
sc.exe failure $ServiceName reset= 86400 actions= restart/5000/restart/5000/restart/10000 | Out-Null
Start-Service -Name $ServiceName
Start-Sleep 3

# --- 7. Doğrulama ---
$svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($svc -and $svc.Status -eq "Running") {
    Write-Host ""
    Write-Host "============================================" -ForegroundColor Green
    Write-Host "  ✓ Mosquitto servisi çalışıyor (otomatik)" -ForegroundColor Green
    Write-Host "============================================" -ForegroundColor Green
    Write-Host "  Broker : localhost:1883" -ForegroundColor White
    Write-Host "  Exe    : $ExePath" -ForegroundColor White
    Write-Host "  Conf   : $ConfPath" -ForegroundColor White
    Write-Host "  Log    : $LogDir\mosquitto.log" -ForegroundColor White
    Write-Host "  Kurtarma: çökerse 5sn sonra otomatik restart" -ForegroundColor White
    if ($MosqFirewallOk) {
        Write-Host "  Firewall: 'PEMF Mosquitto MQTT' (TCP 1883 inbound) içerikle doğrulandı" -ForegroundColor White
    } else {
        Write-Host "  Firewall: 1883 kuralı DOĞRULANAMADI — yukarıdaki UYARI'ya bakın; ESP bobinleri (6-8) broker'a ulaşamayabilir." -ForegroundColor Yellow
    }
    Write-Host ""
    Write-Host "Sonraki adım: PemfBackend servisini kurun (install_backend_service.ps1)." -ForegroundColor Cyan
    Write-Host "Backend bu servise 'depends= mosquitto' ile bağlanacaktır." -ForegroundColor Cyan
} else {
    Write-Status "HATA: Mosquitto servisi başlatılamadı. services.msc → mosquitto kontrol edin." "Red"
    exit 1
}
