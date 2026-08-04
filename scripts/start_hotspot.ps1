# =============================================================================
# PEMF — PEMF-Gateway Windows Mobile Hotspot başlatıcı (ESP bobinleri buna bağlanır).
# -----------------------------------------------------------------------------
# Windows Mobile Hotspot API KULLANICI OTURUMU ister (LocalSystem servisi/session-0
# başlatamaz). Bu yüzden setup_services.ps1 bunu (1) logon Scheduled Task'a kaydeder
# (her açılışta kullanıcı oturumunda çalışır) + (2) kurulumda bir kez çalıştırır.
# SSID/şifre ESP firmware'i (secrets_coil_*.h) ile EŞLEŞMELİ → varsayılan sabit.
# =============================================================================
param(
    [string]$Ssid,
    [string]$Pass
)
$ErrorActionPreference = "Continue"

# ── SSID/PAROLA ÇÖZÜMLEMESİ — ⚠️ BİLİNÇLİ SAHİP KARARI (2026-08-04) ───────────
# VARSAYILAN SABİTTİR ve öyle KALACAKTIR: her kurulan makinede SSID `PEMF-Gateway`,
# parola `pemf1234`. Sahip bunu bilerek böyle istiyor — sahadaki tüm cihazlar eskisi
# gibi çalışmaya devam etmeli.
#
# NEDEN DEĞİŞTİRİLEMEZ: ESP bobinleri (6-8) SSID/parolayı KENDİ firmware'lerinde
# (`config/credentials/secrets_coil_*.h`) taşır ve o firmware bu depoda DEĞİLDİR.
# Parola değişirse o ESP'ler de YENİDEN FLASH'LANMAK zorundadır; aksi halde bobin 6-8
# hotspot'a bağlanamaz. Bu yüzden burada rastgele üretim YAPILMAZ.
#
# Aşağıdaki param/env/hotspot.json zinciri yalnızca İLERİDE cihaz-başına parola
# istenirse kullanılabilsin diye vardır (ESP reflash'ıyla BİRLİKTE). Hiçbiri
# verilmezse davranış eski hâliyle BİREBİR aynıdır. Bunu "eksik" sanıp değiştirme.
#
# Çözümleme sırası: parametre → ortam değişkeni → hotspot.json → (eski varsayılan + UYARI)
$LegacySsid = "PEMF-Gateway"
$LegacyPass = "pemf1234"
$HotspotConf = Join-Path $env:ProgramData 'PEMF_System\hotspot.json'

# Sessiz calisma (endustri-standardi): konsola HICBIR SEY yazma — bu script logon'da + her 3dk
# calistigi icin konsola yazmak gorunur/flash pencereye yol acardi. Tani icin dosyaya logla (rotasyonlu).
$LogDir  = Join-Path $env:LOCALAPPDATA 'PEMF_System'
$LogFile = Join-Path $LogDir 'hotspot.log'
function Log([string]$m) {
    try {
        if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }
        if ((Test-Path $LogFile) -and (Get-Item $LogFile).Length -gt 524288) { Clear-Content -LiteralPath $LogFile -ErrorAction SilentlyContinue }
        "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')  $m" | Add-Content -LiteralPath $LogFile -Encoding UTF8 -ErrorAction SilentlyContinue
    } catch {}
}

# ── SSID/parola çözümle (bkz. başlıktaki DENETİM notu) ──────────────────────
if (-not $Ssid -and $env:PEMF_HOTSPOT_SSID) { $Ssid = $env:PEMF_HOTSPOT_SSID }
if (-not $Pass -and $env:PEMF_HOTSPOT_PASS) { $Pass = $env:PEMF_HOTSPOT_PASS }
if ((-not $Ssid -or -not $Pass) -and (Test-Path -LiteralPath $HotspotConf)) {
    try {
        $hc = Get-Content -LiteralPath $HotspotConf -Raw -Encoding UTF8 | ConvertFrom-Json
        if (-not $Ssid -and $hc.ssid) { $Ssid = [string]$hc.ssid }
        if (-not $Pass -and $hc.pass) { $Pass = [string]$hc.pass }
    } catch { Log "hotspot.json okunamadi ($_) — varsayilana dusuluyor." }
}
if (-not $Ssid) { $Ssid = $LegacySsid }
if (-not $Pass) {
    # Varsayilan yol (BEKLENEN DURUM — bkz. basliktaki SAHIP KARARI notu).
    $Pass = $LegacyPass
    Log "Hotspot kimligi: varsayilan SSID/parola kullaniliyor (ESP 6-8 firmware'iyle eslesir)."
}
# WPA2 asgari uzunluk (8) — kisa parola ConfigureAccessPointAsync'i sessizce dusurur.
if ($Pass.Length -lt 8) { Log "UYARI: parola 8 karakterden kisa; WPA2 reddedebilir."; }

# Zaten aktif mi? (hotspot subnet 192.168.137.x IP var mı)
$active = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object { $_.IPAddress -like '192.168.137.*' }
if ($active) { Log "Hotspot zaten aktif ($($active[0].IPAddress)) — atlandı."; exit 0 }

$useNetsh = $false
try {
    Add-Type -AssemblyName System.Runtime.WindowsRuntime
    $asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
        $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
    $asTaskAction = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
        $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncAction' })[0]
    function AwaitResult($t, $rt) { $at = $asTaskGeneric.MakeGenericMethod($rt); $nt = $at.Invoke($null, @($t)); $nt.Wait(-1) | Out-Null; $nt.Result }
    function AwaitAction($t) { $nt = $asTaskAction.Invoke($null, @($t)); $nt.Wait(-1) | Out-Null }

    [Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager, Windows.Networking.NetworkOperators, ContentType = WindowsRuntime] | Out-Null
    [Windows.Networking.Connectivity.NetworkInformation, Windows.Networking.Connectivity, ContentType = WindowsRuntime] | Out-Null

    $cp = [Windows.Networking.Connectivity.NetworkInformation]::GetInternetConnectionProfile()
    if (-not $cp) { $cp = ([Windows.Networking.Connectivity.NetworkInformation]::GetConnectionProfiles() | Select-Object -First 1) }
    if (-not $cp) { Log "Ağ profili yok → netsh denenecek."; $useNetsh = $true }
    else {
        $mgr = [Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager]::CreateFromConnectionProfile($cp)
        try {
            $cfg = $mgr.GetCurrentAccessPointConfiguration()
            # DENETİM 2026-08-04: AP yapılandırması KOŞULSUZ yeniden yazılıyordu → operatörün
            # Windows Ayarlar'dan koyduğu cihaza-özel parola, ilk boşta-kalma (ICS ~4 dk) döngüsünde
            # sessizce eski değere DÖNÜYORDU. Artık yalnız GERÇEKTEN farklıysa yaz.
            $needCfg = ($cfg.Ssid -ne $Ssid) -or ($cfg.Passphrase -ne $Pass)
            if ($needCfg) {
                $cfg.Ssid = $Ssid
                $cfg.Passphrase = $Pass
                try { $cfg.Band = [Windows.Networking.NetworkOperators.TetheringWiFiBand]::TwoPointFourGigahertz } catch {}  # ESP32 = 2.4GHz
                AwaitAction ($mgr.ConfigureAccessPointAsync($cfg))
                Log "AP yapilandirmasi guncellendi (SSID=$Ssid)."
            } else { Log "AP yapilandirmasi zaten dogru — dokunulmadi." }
        } catch {}
        if ($mgr.TetheringOperationalState -ne 'On') {
            # LattePanda 3 = Intel AX201 → WinRT TEK yol (hosted-network YOK). Radyo init / internet-profili
            # gecikmesinde StartTetheringAsync ilk denemede non-Success dönebilir (özellikle offline klinikte
            # GetInternetConnectionProfile null) → birkaç kez dene ki AP yine de açılsın.
            $ok = $false
            for ($try = 1; $try -le 4 -and -not $ok; $try++) {
                $r = AwaitResult ($mgr.StartTetheringAsync()) ([Windows.Networking.NetworkOperators.NetworkOperatorTetheringOperationResult])
                if ($r.Status -eq 'Success') { Log "Hotspot AKTİF: $Ssid (2.4GHz)"; $ok = $true }
                else { Log "Deneme $try/4 — durum: $($r.Status) $($r.AdditionalErrorMessage)"; Start-Sleep 3 }
            }
            if (-not $ok) { Log "WinRT 4 denemede başlatamadı → netsh fallback (AX201'de desteklenmez)"; $useNetsh = $true }
        }
        else { Log "Hotspot zaten On: $Ssid" }
    }
}
catch { Log "Mobile Hotspot API hatası: $_ → netsh denenecek."; $useNetsh = $true }

# Eski WiFi sürücüleri için HostedNetwork fallback (modern sürücülerde desteklenmeyebilir)
if ($useNetsh) {
    netsh wlan set hostednetwork mode=allow ssid="$Ssid" key="$Pass" | Out-Null
    $res = (netsh wlan start hostednetwork 2>&1) -join ' '
    Log "netsh hostednetwork: $res"
}
