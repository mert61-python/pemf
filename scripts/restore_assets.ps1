# =============================================================================
# PEMF — VARLIK GERI YUKLEME (bos makinede depoyu calisir hale getirir)
# -----------------------------------------------------------------------------
# NEDEN VAR: `guii` klasoru tasinabilir bir PEMF projesidir, ama AI model agirliklarinin
# tamami git'e SIGMAZ. GitHub tek dosyada 100 MiB'i SERT olarak reddediyor ve Git LFS
# ucretli (public depo muafiyeti LFS'e GECMIYOR). Bu yuzden bolunme soyle:
#
#   git'te      : kaynak kod + yayinda kopyasi OLMAYAN 11 kucuk model dosyasi (6 MB)
#   Releases'te : buyuk agirliklar (2,1 GB) — home.zip / vet.zip / research.zip icinde
#
# Bu betik ikinci yarisini geri getirir. Yeni/bos bir makinede sira:
#     1) bu klasoru (ya da `git clone`) getir
#     2) .\bootstrap.ps1            # toolchain (Node/Rust/MSVC/JDK/Android/Inno)
#     3) .\scripts\restore_assets.ps1   # <-- BU: AI model agirliklari
#     4) .\scripts\build_backend_exe.ps1
#
# ⚠️ OLCULDU (2026-08-18): `release_assets/ai_models` altindaki dosyalarin cogu yayinlanmis
# paketlerde yedekli; hicbir yayinda kopyasi olmayan 11 kucuk dosyayi git tasiyor. Bu betik
# yayinlardaki yariyi indirir. `tests/test_yedek_kapsami.py` bu ayrimi kilitler.
#
# ⚠️ 2. TUR DENETIMI [3.5] (2026-08-20): CEKIRDEK MODEL (inference_cat_organ, ~200 MB — AI Pro
# organ lokalizasyonu) 2026-08-10'da home.zip'ten CIKARILIP yalniz base-deps.zip'e tasindi
# (make_base_zip CORE_MODELS istisnasi). Bu betik onu HIC getirmiyordu → temiz makinede ~1
# saatlik akis SON kapida ("cekirdek model (cat_organ) VAR" → exit 1) oluyordu. Artik profil
# zip'lerine EK olarak deps katmanindan `_internal/ai_models/` alti da (yalniz o!) acilir.
# Test kancalari (-DepsZipYolu/-YalnizCekirdek/-KokOverride): PEMF_PKG_OUT emsali — test gercek
# agi/dizini kullanmasin. Kilit: tests/test_restore_assets_cekirdek.py
# =============================================================================
[CmdletBinding()]
param(
  [string]$Repo = "mert61-python/pemf-update",
  [string]$Tag = "client-app-v1.8.0",   # profil zip'lerinin durdugu SABIT etiket
  [string[]]$Profiller = @("home", "vet", "research"),
  [switch]$Force,                         # var olan dosyalarin uzerine yaz
  [string]$DepsZipYolu = "",              # TEST/offline: yerel base-deps.zip (indirme + sha atlanir)
  [switch]$YalnizCekirdek,                # TEST/offline: profilleri atla, yalniz cekirdek modeli ac
  [string]$KokOverride = ""               # TEST: hedef kok (release_assets bunun altina yazilir)
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$Kok = if ($KokOverride) { $KokOverride } else { Split-Path -Parent $PSScriptRoot }

# --- Cekirdek modeli deps zip'inden ac (yalniz `_internal/ai_models/` alti) -------------------
function Restore-CekirdekModeller {
  param([string]$ZipYolu, [string]$HedefKok)
  Add-Type -AssemblyName System.IO.Compression.FileSystem | Out-Null
  $arsiv = [System.IO.Compression.ZipFile]::OpenRead($ZipYolu)
  try {
    $sayi = 0
    foreach ($girdi in $arsiv.Entries) {
      # Ayrac ureticiye gore degisebilir (bu deponun bilinen sinifi) → normalize et.
      $ad = $girdi.FullName.Replace('\', '/')
      if ($ad -notmatch '^(?i)PEMF_Backend/_internal/ai_models/.+') { continue }
      if ($ad.EndsWith('/')) { continue }  # dizin girdisi
      $gorece = $ad -replace '^(?i)PEMF_Backend/_internal/', ''
      $hedef = Join-Path $HedefKok ("release_assets/" + $gorece)
      New-Item -ItemType Directory -Force (Split-Path -Parent $hedef) | Out-Null
      [System.IO.Compression.ZipFileExtensions]::ExtractToFile($girdi, $hedef, $true)
      $sayi++
    }
    if ($sayi -eq 0) {
      # SESSIZ "0 dosya" basarisi YASAK: deps'te cekirdek yoksa paketleme sozlesmesi bozulmus
      # demektir — kullanici "geri yuklendi" sanip build'in son kapisinda yine duserdi.
      throw "deps zip'inde cekirdek model (_internal/ai_models) YOK — paketleme sozlesmesi bozulmus ($ZipYolu)"
    }
    Write-Host "[cekirdek] $sayi dosya acildi (inference_cat_organ dahil)" -ForegroundColor Green
    return $sayi
  } finally {
    $arsiv.Dispose()
  }
}

if ($YalnizCekirdek) {
  if (-not $DepsZipYolu) { throw "-YalnizCekirdek icin -DepsZipYolu gerekir (test/offline modu)" }
  Restore-CekirdekModeller -ZipYolu $DepsZipYolu -HedefKok $Kok | Out-Null
  return
}
$Hedef = Join-Path $Kok "release_assets\ai_models"
New-Item -ItemType Directory -Force $Hedef | Out-Null

Write-Host "PEMF varlik geri yukleme" -ForegroundColor Cyan
Write-Host "  hedef : $Hedef"
Write-Host "  kaynak: $Repo @ $Tag"
Write-Host ""

# home.zip artik AYRI bir etikette olabilir (make_manifest sha degismeyince URL'yi KORUYOR).
# Dogru adresi manifest'ten oku — elle tahmin etme.
$ManifestUrl = "https://github.com/$Repo/releases/download/client-app-v1.8.0/manifest.json"
try {
  $manifest = (Invoke-WebRequest -Uri $ManifestUrl -UseBasicParsing -TimeoutSec 120).Content | ConvertFrom-Json
} catch {
  throw "manifest okunamadi ($ManifestUrl): $_"
}

$gecici = Join-Path $env:TEMP "pemf-restore"
New-Item -ItemType Directory -Force $gecici | Out-Null
$toplam = 0

foreach ($p in $Profiller) {
  $girdi = $manifest.profiles.$p
  if (-not $girdi) { Write-Warning "manifest'te profil yok: $p — atlandi"; continue }

  $zip = Join-Path $gecici "$p.zip"
  $mb = [math]::Round($girdi.size / 1MB)
  Write-Host "[$p] indiriliyor ($mb MB)..." -NoNewline
  Invoke-WebRequest -Uri $girdi.url -OutFile $zip -TimeoutSec 3600
  Write-Host " tamam"

  # ⚠️ SHA DOGRULAMASI ZORUNLU: bozuk/yarim indirme sessizce yanlis model kurar ve bu bir
  # TIBBI CIHAZ — yanlis agirlikla calisan bir model yanlis klinik cikti uretir.
  $sha = (Get-FileHash $zip -Algorithm SHA256).Hash.ToLower()
  if ($sha -ne $girdi.sha256) {
    Remove-Item $zip -Force
    throw "[$p] SHA256 UYUSMUYOR (beklenen $($girdi.sha256), gelen $sha) — indirme bozuk, kurulum iptal."
  }
  Write-Host "[$p] sha256 dogrulandi"

  # Zip icindeki yollar `ai_models/...` ile basliyor; `release_assets/` altina acilir.
  Expand-Archive -Path $zip -DestinationPath (Join-Path $Kok "release_assets") -Force:$Force
  $toplam += $girdi.size
  Remove-Item $zip -Force
}

# --- CEKIRDEK MODEL (2. tur [3.5]): profil zip'lerinin HICBIRINDE yok — deps katmanindan gelir.
$catOrgan = Join-Path $Hedef "ai_hub\inference_cat_organ"
$catVar = (Test-Path $catOrgan) -and
  ((Get-ChildItem $catOrgan -Recurse -File -ErrorAction SilentlyContinue | Measure-Object).Count -gt 0)
if ($catVar -and -not $Force) {
  Write-Host "[cekirdek] inference_cat_organ zaten mevcut - atlandi (-Force ile yenile)"
} else {
  $deps = $manifest.layers.'win-x64'.deps
  if (-not $deps) { throw "manifest'te layers.win-x64.deps yok - cekirdek model getirilemez" }
  $dzip = $DepsZipYolu
  if (-not $dzip) {
    $dzip = Join-Path $gecici "base-deps.zip"
    $mb = [math]::Round($deps.size / 1MB)
    Write-Host "[cekirdek] base-deps.zip indiriliyor ($mb MB - cat_organ YALNIZ bu katmanda; bir kez)..." -NoNewline
    Invoke-WebRequest -Uri $deps.url -OutFile $dzip -TimeoutSec 3600
    Write-Host " tamam"
    # SHA dogrulamasi profil zip'leriyle AYNI gerekceyle zorunlu (tibbi cihaz, yanlis agirlik).
    $dsha = (Get-FileHash $dzip -Algorithm SHA256).Hash.ToLower()
    if ($dsha -ne $deps.sha256) {
      Remove-Item $dzip -Force
      throw "[cekirdek] SHA256 UYUSMUYOR (beklenen $($deps.sha256), gelen $dsha) - indirme bozuk, kurulum iptal."
    }
    Write-Host "[cekirdek] sha256 dogrulandi"
  }
  Restore-CekirdekModeller -ZipYolu $dzip -HedefKok $Kok | Out-Null
}

Remove-Item $gecici -Recurse -Force -ErrorAction SilentlyContinue

$n = (Get-ChildItem $Hedef -Recurse -File -ErrorAction SilentlyContinue | Measure-Object).Count
Write-Host ""
Write-Host "Geri yuklendi: $([math]::Round($toplam/1MB)) MB — $Hedef altinda $n dosya" -ForegroundColor Green
Write-Host "Sonraki adim: .\scripts\build_backend_exe.ps1" -ForegroundColor Cyan
