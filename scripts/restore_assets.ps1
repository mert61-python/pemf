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
# ⚠️ OLCULDU (2026-08-18): `release_assets/ai_models` altindaki 51 dosyanin 40'i yayinlanmis
# paketlerde yedekli, 11'i hicbir yerde yoktu -> o 11'i artik git tasiyor. Bu betik kalan 40'i
# indirir. `tests/test_yedek_kapsami.py` bu ayrimi kilitler.
# =============================================================================
[CmdletBinding()]
param(
  [string]$Repo = "mert61-python/pemf-update",
  [string]$Tag = "client-app-v1.8.0",   # profil zip'lerinin durdugu SABIT etiket
  [string[]]$Profiller = @("home", "vet", "research"),
  [switch]$Force                          # var olan dosyalarin uzerine yaz
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$Kok = Split-Path -Parent $PSScriptRoot
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

Remove-Item $gecici -Recurse -Force -ErrorAction SilentlyContinue

$n = (Get-ChildItem $Hedef -Recurse -File -ErrorAction SilentlyContinue | Measure-Object).Count
Write-Host ""
Write-Host "Geri yuklendi: $([math]::Round($toplam/1MB)) MB — $Hedef altinda $n dosya" -ForegroundColor Green
Write-Host "Sonraki adim: .\scripts\build_backend_exe.ps1" -ForegroundColor Cyan
