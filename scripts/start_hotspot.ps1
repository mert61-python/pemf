# =============================================================================
# PEMF — PEMF-Gateway Windows Mobile Hotspot başlatıcı (ESP bobinleri buna bağlanır).
# -----------------------------------------------------------------------------
# Windows Mobile Hotspot API KULLANICI OTURUMU ister (LocalSystem servisi/session-0
# başlatamaz). Bu yüzden setup_services.ps1 bunu (1) logon Scheduled Task'a kaydeder
# (her açılışta kullanıcı oturumunda çalışır) + (2) kurulumda bir kez çalıştırır.
# SSID/şifre ESP firmware'i (secrets_coil_*.h) ile EŞLEŞMELİ → varsayılan sabit.
# =============================================================================
param(
    [string]$Ssid = "PEMF-Gateway",
    [string]$Pass = "pemf1234"
)
$ErrorActionPreference = "Continue"

# Zaten aktif mi? (hotspot subnet 192.168.137.x IP var mı)
$active = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object { $_.IPAddress -like '192.168.137.*' }
if ($active) { Write-Host "Hotspot zaten aktif ($($active[0].IPAddress)) — atlandı."; exit 0 }

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
    if (-not $cp) { Write-Host "Ağ profili yok → netsh denenecek."; $useNetsh = $true }
    else {
        $mgr = [Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager]::CreateFromConnectionProfile($cp)
        try {
            $cfg = $mgr.GetCurrentAccessPointConfiguration()
            $cfg.Ssid = $Ssid
            $cfg.Passphrase = $Pass
            try { $cfg.Band = [Windows.Networking.NetworkOperators.TetheringWiFiBand]::TwoPointFourGigahertz } catch {}  # ESP32 = 2.4GHz
            AwaitAction ($mgr.ConfigureAccessPointAsync($cfg))
        } catch {}
        if ($mgr.TetheringOperationalState -ne 'On') {
            # LattePanda 3 = Intel AX201 → WinRT TEK yol (hosted-network YOK). Radyo init / internet-profili
            # gecikmesinde StartTetheringAsync ilk denemede non-Success dönebilir (özellikle offline klinikte
            # GetInternetConnectionProfile null) → birkaç kez dene ki AP yine de açılsın.
            $ok = $false
            for ($try = 1; $try -le 4 -and -not $ok; $try++) {
                $r = AwaitResult ($mgr.StartTetheringAsync()) ([Windows.Networking.NetworkOperators.NetworkOperatorTetheringOperationResult])
                if ($r.Status -eq 'Success') { Write-Host "Hotspot AKTİF: $Ssid (2.4GHz)"; $ok = $true }
                else { Write-Host "Deneme $try/4 — durum: $($r.Status) $($r.AdditionalErrorMessage)"; Start-Sleep 3 }
            }
            if (-not $ok) { Write-Host "WinRT 4 denemede başlatamadı → netsh fallback (AX201'de desteklenmez)"; $useNetsh = $true }
        }
        else { Write-Host "Hotspot zaten On: $Ssid" }
    }
}
catch { Write-Host "Mobile Hotspot API hatası: $_ → netsh denenecek."; $useNetsh = $true }

# Eski WiFi sürücüleri için HostedNetwork fallback (modern sürücülerde desteklenmeyebilir)
if ($useNetsh) {
    netsh wlan set hostednetwork mode=allow ssid="$Ssid" key="$Pass" | Out-Null
    $res = (netsh wlan start hostednetwork 2>&1) -join ' '
    Write-Host "netsh hostednetwork: $res"
}
