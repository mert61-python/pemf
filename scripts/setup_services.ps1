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
    [switch]$PurgeData          # -Uninstall ile: hasta DB + şifreleme anahtarlarını da KALICI sil (KVKK; varsayılan KORU)
)
$ErrorActionPreference = "Continue"   # installer akışını tek bir hata kesmesin
function Log($m, $c = "White") { Write-Host "[setup-services] $m" -ForegroundColor $c }

if (-not $AppDir) { $AppDir = Split-Path -Parent $MyInvocation.MyCommand.Path }

$ServiceBackend = "PemfBackend"
$ServiceMosq    = "mosquitto"
$LogDir         = "C:\ProgramData\PEMF_System\logs"
# NSSM: ÖNCE bundled (offline, {app}\_internal\bin\nssm) → yoksa C:\nssm → en son indir (internet).
# Offline klinikte internet gerekmesin diye nssm.exe EXE'ye bundle edildi (spec bin/nssm).
$NssmBundled    = Join-Path $AppDir "_internal\bin\nssm\nssm.exe"
$NssmExe        = if (Test-Path $NssmBundled) { $NssmBundled } else { "C:\nssm\nssm.exe" }
$MosqInstallDir = "C:\Program Files\PEMF\mosquitto"
$MosqDataRoot   = "C:\ProgramData\PEMF_System\mosquitto"
$BackendExe     = Join-Path $AppDir "PEMF_Backend.exe"

# Bundled mosquitto kaynağı (PyInstaller onedir: {app}\_internal\bin\mosquitto)
$MosqSrc = Join-Path $AppDir "_internal\bin\mosquitto"
if (-not (Test-Path (Join-Path $MosqSrc "mosquitto.exe"))) {
    $alt = Join-Path $AppDir "bin\mosquitto"
    if (Test-Path (Join-Path $alt "mosquitto.exe")) { $MosqSrc = $alt }
}

# ───────────────────────── UNINSTALL ─────────────────────────
if ($Uninstall) {
    Log "Servisler kaldırılıyor..." "Yellow"
    # KRİTİK: {app} altından çalışan TÜM süreçleri (backend + cloudflared-tünel + nssm) + mosquitto'yu ÖLDÜR →
    # dosya kilidi kalmasın ("bazı dosyalar kaldırılamadı / ille silin"i KÖKTEN önler). cloudflared tünel-watchdog
    # süreci {app}\bin\cloudflared'den çalışıp {app}'i kilitliyordu ve ESKİDEN öldürülmüyordu (asıl kalan-kilit nedeni).
    function Stop-AppProcs {
        Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $_.ExecutablePath -and $_.ExecutablePath -like "$AppDir\*" } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
        Get-Process cloudflared, nssm, mosquitto, PEMF_Backend -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    }
    Stop-AppProcs
    # Backend: nssm remove + sc delete (hiçbiri bloklamaz)
    if (Test-Path $NssmExe) {
        & $NssmExe stop $ServiceBackend *>$null
        & $NssmExe remove $ServiceBackend confirm *>$null
    }
    & sc.exe delete $ServiceBackend *>$null
    # Mosquitto: Stop-Service -Force YOK — StartPending'de ASILIR (install yolunda yasakladığımız
    # anti-pattern; uninstall yolu da aynı 5dk donmaya yol açıyordu). Süreç-kill + native uninstall + sc delete.
    if (Get-Service -Name $ServiceMosq -ErrorAction SilentlyContinue) {
        Get-Process mosquitto -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
        $mexe = Join-Path $MosqInstallDir "mosquitto.exe"
        if (Test-Path $mexe) { & $mexe uninstall *>$null }
        & sc.exe delete $ServiceMosq *>$null
    }
    # Servis kayıtlarının silinmesini poll et — max ~10sn
    foreach ($s in @($ServiceBackend, $ServiceMosq)) {
        for ($i = 0; $i -lt 10 -and (Get-Service -Name $s -ErrorAction SilentlyContinue); $i++) { Start-Sleep 1 }
    }
    # KRİTİK: TÜM ilgili süreçler GERÇEKTEN ölene kadar bekle (her turda yeniden öldür) → dosya kilidi serbest
    # kalsın ki Inno {app}'i silebilsin. Max ~15sn + handle-release payı.
    for ($i = 0; $i -lt 30; $i++) {
        $alive = @(Get-Process PEMF_Backend, mosquitto, cloudflared, nssm -ErrorAction SilentlyContinue)
        $alive += @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $_.ExecutablePath -and $_.ExecutablePath -like "$AppDir\*" })
        if ($alive.Count -eq 0) { break }
        Stop-AppProcs
        Start-Sleep -Milliseconds 500
    }
    Start-Sleep 1
    Remove-Item (Join-Path $AppDir ".install_verified") -Force -ErrorAction SilentlyContinue
    # Bundled mosquitto kurulum dizini Inno {app}'te DEĞİL (C:\Program Files\PEMF\mosquitto) → elle sil (artık kalmasın).
    Remove-Item $MosqInstallDir -Recurse -Force -ErrorAction SilentlyContinue
    schtasks /Delete /TN "PEMF-Hotspot" /F *>$null   # hotspot logon-task'ı kaldır
    # Hotspot keep-alive wscript'i System32\wscript.exe'den çalışır → $AppDir kill'i yakalamaz; cmdline'la eşleştir.
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $_.Name -eq 'wscript.exe' -and $_.CommandLine -match 'start_hotspot_hidden' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Remove-Item (Join-Path $AppDir "start_hotspot_hidden.vbs") -Force -ErrorAction SilentlyContinue

    # FIREWALL: eski sürüm yalnız 3 kuralı isimle silerdi; sahada pemf_gui / PEMF_Service_Port_* /
    # *_onefile.exe / cloudflared.exe / pemf_backend.exe gibi ~19 kural birikiyordu → WILDCARD ile hepsi.
    Get-NetFirewallRule -ErrorAction SilentlyContinue | Where-Object { $_.DisplayName -match 'pemf|mosquitto|cloudflared' } | Remove-NetFirewallRule -ErrorAction SilentlyContinue

    # ORTAM DEĞİŞKENLERİ: Makine-kapsamı PEMF_* (SetEnvironmentVariable($null) girdiyi BOŞ bırakır → Registry'den TAM sil).
    $mEnv = 'HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Environment'
    (Get-ItemProperty $mEnv -ErrorAction SilentlyContinue).PSObject.Properties | Where-Object { $_.Name -match '^PEMF_' } | ForEach-Object { Remove-ItemProperty -Path $mEnv -Name $_.Name -Force -ErrorAction SilentlyContinue }

    # REGISTRY: üretici anahtarı (HKLM). Client'ın HKCU anahtarları operatör bağlamında client-hook'la temizlenir.
    Remove-Item -LiteralPath 'HKLM:\SOFTWARE\PEMF Medical Technologies' -Recurse -Force -ErrorAction SilentlyContinue

    # ai_models = uygulama modelleri (HASTA VERİSİ DEĞİL) → her zaman kaldır.
    Remove-Item 'C:\ProgramData\PEMF_GUI\ai_models' -Recurse -Force -ErrorAction SilentlyContinue

    if ($PurgeData) {
        # KVKK-BİLİNÇLİ TAM SİLME: hasta DB + SQLCipher/Fernet anahtarları. Backend LocalSystem çalıştığından
        # hasta DB'si systemprofile altında; ayrıca ProgramData ve her operatör %APPDATA%'sında olabilir.
        Log "PurgeData: HASTA VERİSİ + şifreleme anahtarları KALICI siliniyor." "Red"
        foreach ($ck in 'fernet_key@PEMF_GUI','sqlcipher_key@PEMF_GUI','PEMF_GUI','api_token@PEMF_GUI') { cmdkey /delete:$ck *>$null }
        Remove-Item 'C:\Windows\System32\config\systemprofile\AppData\Roaming\PEMF_GUI' -Recurse -Force -ErrorAction SilentlyContinue
        Remove-Item 'C:\ProgramData\PEMF_GUI', 'C:\ProgramData\PEMF_System' -Recurse -Force -ErrorAction SilentlyContinue
        Get-ChildItem 'C:\Users' -Directory -ErrorAction SilentlyContinue | ForEach-Object {
            Remove-Item (Join-Path $_.FullName 'AppData\Roaming\PEMF_GUI') -Recurse -Force -ErrorAction SilentlyContinue
            Remove-Item (Join-Path $_.FullName 'AppData\Local\PEMF_GUI_OneFile') -Recurse -Force -ErrorAction SilentlyContinue
        }
        Log "Servisler + TÜM veri kaldırıldı (tam temizlik)." "Green"
    } else {
        Log "Servisler + firewall + görev + env + üretici-registry kaldırıldı. HASTA VERİSİ KORUNDU (KVKK) — tam silme: -PurgeData." "Green"
    }
    exit 0
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
"@
    # BOŞLUKSUZ yola yaz (C:\ProgramData\...): NSSM AppParameters '-c <yol>' boşlukta bölünür;
    # "C:\Program Files\..." mosquitto'ya "C:\Program" olarak geçip "Unable to open config" verirdi.
    Set-Content -Path "$MosqDataRoot\mosquitto.conf" -Value $conf -Encoding ASCII

    # Firewall (TCP 1883 — yalnız hotspot subnet, ESP bobin 6-8)
    if (-not (Get-NetFirewallRule -DisplayName "PEMF Mosquitto MQTT" -ErrorAction SilentlyContinue)) {
        # P0-3 (GÜVENLİK): Broker'a 1883 yalnız HOTSPOT subnet'inden (ESP bobin 6-8, 192.168.137.x)
        # erişilebilsin; klinik LAN'ından KAPALI. ESP firmware'i broker'a ANON bağlandığından
        # (BLE provisioner kimlik göndermiyor) auth açılamaz → savunma: hotspot WPA2 + bu subnet
        # kısıtı. Loopback (127.0.0.1) firewall'dan muaftır → backend localhost bağlantısı çalışır.
        New-NetFirewallRule -DisplayName "PEMF Mosquitto MQTT" -Direction Inbound -Protocol TCP -LocalPort 1883 -RemoteAddress 192.168.137.0/24 -Action Allow -Profile Any | Out-Null
    }

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
    Log "NSSM indiriliyor..." "Yellow"
    New-Item -ItemType Directory -Path (Split-Path $NssmExe) -Force | Out-Null
    try {
        $zip = "$env:TEMP\nssm.zip"
        Invoke-WebRequest "https://nssm.cc/release/nssm-2.24.zip" -OutFile $zip -UseBasicParsing -TimeoutSec 20
        Expand-Archive $zip "$env:TEMP\nssm_ext" -Force
        $bin = Get-ChildItem "$env:TEMP\nssm_ext" -Filter nssm.exe -Recurse | Where-Object { $_.FullName -like "*win64*" } | Select-Object -First 1
        if (-not $bin) { $bin = Get-ChildItem "$env:TEMP\nssm_ext" -Filter nssm.exe -Recurse | Select-Object -First 1 }
        Copy-Item $bin.FullName $NssmExe -Force
    } catch {
        Log "HATA: NSSM indirilemedi: $_" "Red"
    }
}

# ───────────────────── 3. BACKEND SERVİSİ (NSSM) ─────────────────────
if (-not (Test-Path $BackendExe)) { Log "HATA: Backend EXE yok: $BackendExe" "Red"; exit 1 }
if (-not (Test-Path $NssmExe))    { Log "HATA: NSSM yok, backend servisi kurulamadı." "Red"; exit 1 }

Log "Backend servisi kuruluyor: $BackendExe" "Yellow"
if (Get-Service -Name $ServiceBackend -ErrorAction SilentlyContinue) {
    & $NssmExe stop $ServiceBackend *>$null
    # Süreç gerçekten ölsün (nssm stop timeout'unu aşabilir) → marked-for-delete (1072) yarışını önler
    Get-Process PEMF_Backend -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
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
$EnvFile = @(
    (Join-Path $AppDir "_internal\deploy\$Mode.env"),
    (Join-Path $AppDir "deploy\$Mode.env"),
    (Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "..\deploy\$Mode.env")
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if ($EnvFile) {
    Log "Profil yükleniyor ($Mode): $EnvFile" "Cyan"
    foreach ($ln in (Get-Content $EnvFile)) {
        $t = $ln.Trim()
        if ($t -and -not $t.StartsWith("#") -and $t.Contains("=")) {
            $k, $v = $t.Split("=", 2); $EnvMap[$k.Trim()] = $v.Trim()
        }
    }
} else {
    Log "UYARI: deploy\$Mode.env bulunamadı; yalnız temel env yazıldı." "Yellow"
}
$AppEnv = @($EnvMap.Keys | ForEach-Object { "$_=$($EnvMap[$_])" })
& $NssmExe set $ServiceBackend AppEnvironmentExtra @AppEnv
Log ("Env (" + $Mode + "): " + ($AppEnv -join '  ')) "Gray"

# NOT: SCM 'depend= mosquitto' KULLANILMAZ. NSSM-managed mosquitto'da SCM bağımlılık çözümü
# güvenilmez (mosquitto Running olsa BİLE "Bağımlılık başlayamadı"/1068 → backend HİÇ başlamaz).
# Backend MQTT broker'a zaten retry ile bağlanır (ESP bobinleri dinamik bağlanır/kopar). mosquitto
# bu scriptte backend'den ÖNCE başlatılır; boot'ta ikisi de Automatic → paralel başlar, backend
# broker gelene kadar dener. (Bağımlılık eklemek backend'i başlatmamaya yol açıyordu.)

foreach ($r in @(@{n = "PEMF Backend API"; p = "TCP"; port = 8000 }, @{n = "PEMF UDP Discovery"; p = "UDP"; port = 5051 })) {
    if (-not (Get-NetFirewallRule -DisplayName $r.n -ErrorAction SilentlyContinue)) {
        try { New-NetFirewallRule -DisplayName $r.n -Direction Inbound -Program $BackendExe -Action Allow -Protocol $r.p -LocalPort $r.port -Profile Any -ErrorAction Stop | Out-Null }
        catch { Log "UYARI: Firewall kuralı oluşturulamadı ($($r.n)): $_. LAN'dan (mobil/web) erişim engellenebilir." "Yellow" }
    }
}

& $NssmExe start $ServiceBackend *>$null   # 'SERVICE_START_PENDING' zararsız uyarısını sustur; gerçek kanıt /api/health
# ── GERÇEK fonksiyonel doğrulama (sessiz-başarıyı kapat) ──────────────────────────
# nssm status TEK BAŞINA yetmez: AppThrottle/Restart ile crash-loop'ta bile RUNNING görünür.
# Bu yüzden /api/health 200 esas kanıt. (device=0.0.0.0, server=127.0.0.1 → localhost ikisinde de çalışır.)
$probePort = if ($EnvMap['PEMF_API_PORT']) { $EnvMap['PEMF_API_PORT'] } else { 8000 }
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
Log "Kurulum DOĞRULANDI → http://localhost:$probePort" "Green"
# Başarı-bayrağı: Inno bunu [Code] ssPostInstall'da kontrol eder (PowerShell exit kodu Inno'da güvenilmez)
Set-Content -Path (Join-Path $AppDir ".install_verified") -Value (Get-Date -Format o) -Encoding ASCII -ErrorAction SilentlyContinue

# ───────────────────── HOTSPOT (PEMF-Gateway WiFi — yalnız KLİNİK/device) ─────────────────────
# ESP bobinleri (6-8) bu WiFi'ye bağlanıp yerel mosquitto'ya (1883) MQTT yapar. Windows Mobile Hotspot
# KULLANICI OTURUMU ister (LocalSystem servisi/session-0 başlatamaz) → (1) logon Scheduled Task ile her
# açılışta kullanıcı oturumunda başlat (eski GUI sistem davranışı) + (2) kurulumda bir kez hemen başlat.
if ($Mode -eq "device") {
    $hotspotPs = Join-Path $AppDir "start_hotspot.ps1"
    if (Test-Path $hotspotPs) {
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
