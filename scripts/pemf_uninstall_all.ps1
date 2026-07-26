# =============================================================================
# PEMF TAM KALDIRICI (standalone) — makinedeki TÜM PEMF izini tek komutta kaldırır.
# -----------------------------------------------------------------------------
# ÜÇ installer'ın (Tauri client / Inno backend / eski GUI) footprint'ini + servis/görev/
# firewall/env/registry/veri kalıntılarını birleşik teardown modülüyle temizler. Destek/
# sıfırlama senaryosu + KVKK "tüm hasta verisini sildim" kanıtı (log raporu) için.
#
#   .\pemf_uninstall_all.ps1              # servis+veri kaldır, HASTA VERİSİ KORU (varsayılan; KVKK)
#   .\pemf_uninstall_all.ps1 -PurgeData   # hasta DB + şifreleme anahtarları dahil TAM sil
#   .\pemf_uninstall_all.ps1 -DryRun      # hiçbir şey silme, ne silineceğini göster (önizleme)
#   .\pemf_uninstall_all.ps1 -Yes         # onay sorma (otomasyon)
# =============================================================================
[CmdletBinding()]
param(
    [switch]$PurgeData,   # KVKK: hasta DB + anahtarları da KALICI sil
    [switch]$DryRun,      # yalnız önizleme
    [switch]$Yes          # interaktif onayı atla
)

$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) {
    Write-Host "Bu araç YÖNETİCİ gerektirir (servis/firewall/HKLM/systemprofile). Yönetici PowerShell'de çalıştırın." -ForegroundColor Red
    exit 1
}

# Modül {app} altında olabilir ve teardown {app}'i de siler -> kendini-silme kilidini önlemek için
# TEMP'e kopyala + oradan çalıştır. Log'u da PEMF_System'den BAĞIMSIZ tut (silinse de rapor kalsın).
$src = $PSScriptRoot
$tmp = Join-Path $env:TEMP ('pemf_teardown_' + [guid]::NewGuid().ToString('N').Substring(0, 8))
New-Item -ItemType Directory -Path $tmp -Force | Out-Null
foreach ($f in 'pemf_footprint.ps1', 'pemf_teardown.ps1') {
    $s = Join-Path $src $f
    if (-not (Test-Path $s)) { Write-Host "Birleşik teardown modülü eksik: $s" -ForegroundColor Red; exit 1 }
    Copy-Item $s $tmp -Force
}
$report = Join-Path ([Environment]::GetFolderPath('Desktop')) ("PEMF_Kaldirma_Raporu_$(Get-Date -Format yyyyMMdd_HHmmss).log")
$env:PEMF_TEARDOWN_LOG = $report

if (-not $DryRun -and -not $Yes) {
    $msg = if ($PurgeData) {
        "TÜM PEMF + HASTA VERİSİ (veritabanı + şifreleme anahtarları) GERİ DÖNÜLEMEZ şekilde silinecek.`nEmin misiniz?"
    } else {
        "TÜM PEMF (servis/ayar/uygulama-verisi) kaldırılacak; HASTA VERİSİ KORUNACAK.`nDevam edilsin mi?"
    }
    $ans = Read-Host "$msg [e/H]"
    if ($ans -notmatch '^(e|E|y|Y)') { Write-Host "İptal edildi." -ForegroundColor Yellow; exit 0 }
}

. (Join-Path $tmp 'pemf_teardown.ps1')
Invoke-PemfTeardown -Scope all -IncludePatientData:$PurgeData -DryRun:$DryRun
Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue

$sonuc = if ($DryRun) { "ÖNİZLEME tamamlandı (hiçbir şey silinmedi)" } else { "PEMF kaldırma tamamlandı" }
Write-Host "`n$sonuc. Rapor: $report" -ForegroundColor Green
