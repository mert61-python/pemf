# Author: mertaygn, cglrgrkn
# PEMF-Hotspot KEEP-ALIVE GOREVI — kullanici kapsaminda kurar/kaldirir.
# =============================================================================
# NEDEN AYRI BIR BETIK (2026-09-10):
# Bu blok `setup_services.ps1` icindeydi ve YALNIZ Inno/servis kurulum yolunda
# calisiyordu. Launcher ile kurulan makineler gorevi HIC almiyordu → hotspot bir
# kez elle acilsa bile ag degisiminde/yeniden baslatmada dusuyor ve onu geri
# getirecek kimse olmuyordu. Sahada olculdu: ESP bobinleri (6-8) baglanamaz.
#
# ⚠️ NEDEN 3 DAKIKA: ICS Mobile-Hotspot ~4 dk bosta kendini kapatir. Idempotent
# `start_hotspot.ps1`i her 3 dk tekrar calistirmak tek guvenilir care (ayni
# gerekce setup_services.ps1'de de yaziyor).
#
# ⚠️⚠️ NEDEN `powershell.exe`, `pwsh` DEGIL (2026-09-10, ACIYLA OGRENILDI):
# Mobile Hotspot WinRT API'si PowerShell 7'de YOK. pwsh ile calistirilinca
#     "Operation is not supported on this platform. (0x80131539)"
# verir, netsh yedegine duser, o da yonetici ister ve sessizce basarisiz olur.
# Windows PowerShell 5.1 ile ayni betik YONETICI OLMADAN calisir (olculdu).
# Bu satiri `pwsh`e cevirmeyin.
#
# ⚠️ NEDEN VBS RUNTIME DISINDA: `start_hotspot.ps1` app katmanindadir ve her
# uygulama guncellemesinde silinip yeniden yazilir (`_app_roots.json` siniri).
# VBS'i oraya koyarsak guncellemede kaybolur → gorev kirilir. Bu yuzden VBS
# `%LOCALAPPDATA%\PEMF_System\` altinda (log ile ayni, kalici yer) durur ve
# runtime'daki ps1'e isaret eder.
#
# ⚠️ YONETICI GEREKMEZ: gorev kullanici kapsaminda kurulur (RunLevel Highest ve
# sistem principal'i YOK). setup_services.ps1'deki surum elevated kurulumda
# kosuyordu; burada gerek yok, cunku WinRT yolu yukseltilmeden calisiyor.
#
# Kullanim:
#   powershell.exe -NoProfile -ExecutionPolicy Bypass -File install_hotspot_task.ps1
#   ... -Ps1Yolu "C:\...\start_hotspot.ps1"   (varsayilan: bu betigin yani)
#   ... -Kaldir                                (gorevi ve VBS'i siler)
# Cikis: 0 = basarili (idempotent), 1 = kurulamadi.
# =============================================================================
param(
    [string]$Ps1Yolu = "",
    [switch]$Kaldir
)

$ErrorActionPreference = 'Stop'
$GOREV = 'PEMF-Hotspot'

$LogDir = Join-Path $env:LOCALAPPDATA 'PEMF_System'
$LogFile = Join-Path $LogDir 'hotspot.log'
function Log([string]$m) {
    try {
        if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }
        "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')  [gorev] $m" | Add-Content -LiteralPath $LogFile -Encoding UTF8 -ErrorAction SilentlyContinue
    } catch {}
}

$VbsYolu = Join-Path $LogDir 'start_hotspot_hidden.vbs'

# ── KALDIR ────────────────────────────────────────────────────────────────────
if ($Kaldir) {
    try { Unregister-ScheduledTask -TaskName $GOREV -Confirm:$false -ErrorAction Stop; Log "gorev kaldirildi" }
    catch { Log "gorev zaten yok ya da kaldirilamadi: $($_.Exception.Message)" }
    try { if (Test-Path $VbsYolu) { Remove-Item -LiteralPath $VbsYolu -Force; Log "VBS silindi" } } catch {}
    exit 0
}

# ── ps1 yolunu coz ────────────────────────────────────────────────────────────
if (-not $Ps1Yolu) { $Ps1Yolu = Join-Path $PSScriptRoot 'start_hotspot.ps1' }
if (-not (Test-Path -LiteralPath $Ps1Yolu)) {
    Log "HATA: start_hotspot.ps1 bulunamadi ($Ps1Yolu) → gorev kurulmadi"
    exit 1
}
$Ps1Yolu = (Resolve-Path -LiteralPath $Ps1Yolu).Path

# ── Sessiz baslatici (penceresiz) ─────────────────────────────────────────────
# Gorev logon'da + her 3 dk kostugu icin powershell.exe GORUNUR konsol penceresi
# acardi (her 3 dk flash). wscript VBS'i pencere stili 0 ile calistirir.
# NOT: 5.1 yolu tam yol ile verilir — PATH'te `powershell` baska bir seye
# isaret ederse (ornegin pwsh takma adi) WinRT yine kirilirdi.
$Ps51 = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
if (-not (Test-Path -LiteralPath $Ps51)) {
    Log "HATA: Windows PowerShell 5.1 bulunamadi ($Ps51) → gorev kurulmadi"
    exit 1
}

if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }
# ⚠️ TIRNAK KACISI YOK — BILEREK. Ilk yazimda VBS icindeki tirnaklar PowerShell
# backtick'iyle kacirilmisti; here-string bunlari LITERAL backtick olarak yaziyor
# ve VBScript'te tirnak `""` ile kacilir, backtick ile DEGIL → uretilen dosya
# calismazdi (yalitilmis testte yakalandi). `Chr(34)` ile tirnak hic gomulmuyor:
# yollar degiskene alinir, tirnak calisma aninda eklenir. Yollarda tirnak olamaz.
$vbs = @"
' PEMF-Hotspot sessiz baslatici — install_hotspot_task.ps1 uretir, ELLE DUZENLEMEYIN.
Option Explicit
Dim sh, q, ps51, ps1
Set sh = CreateObject("WScript.Shell")
q = Chr(34)
ps51 = "$Ps51"
ps1 = "$Ps1Yolu"
sh.Run q & ps51 & q & " -NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File " & q & ps1 & q, 0, False
"@
Set-Content -LiteralPath $VbsYolu -Value $vbs -Encoding ASCII

# ── Gorevi kur (idempotent) ───────────────────────────────────────────────────
try {
    $act = New-ScheduledTaskAction -Execute 'wscript.exe' -Argument "`"$VbsYolu`""
    $trg = New-ScheduledTaskTrigger -AtLogOn
    # Tekrar araligi ayri bir tetikleyiciden kopyalanir — New-ScheduledTaskTrigger
    # -AtLogOn dogrudan -RepetitionInterval kabul etmez.
    $trg.Repetition = (New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 3)).Repetition
    $set = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero)
    $set.Hidden = $true
    Register-ScheduledTask -TaskName $GOREV -Action $act -Trigger $trg -Settings $set -Force -ErrorAction Stop | Out-Null
    Log "gorev kuruldu/guncellendi → $Ps1Yolu (logon + her 3 dk, penceresiz, kullanici kapsami)"
    exit 0
} catch {
    Log "HATA: gorev kurulamadi: $($_.Exception.Message)"
    exit 1
}
