# =============================================================================
# PEMF — GitHub Release yayinlayici (oto-guncelleme icin).
# -----------------------------------------------------------------------------
# Yeni surum cikarinca TEK komut: release olusturur + asset (installer/APK) yukler
# + ilgili branch'in latest.json manifest'ini gunceller. Kurulu eski surumler bunu
# gorup guncellemeyi onerir (EXE: bildirim+tek-tik; mobil: indir).
#
# Token: git credential'dan otomatik alinir (pf/backend push'unda kullandigin).
#
# KULLANIM:
#   # EXE (device installer) yeni surum:
#   .\scripts\publish_release.ps1 -Branch exe -Version 1.5.0 `
#       -AssetPath 'C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\build_tools\Output\PEMFBackendSetup_device_v1.4.0.exe' `
#       -Notes 'Faz X duzeltmeleri'
#   # Mobil (APK) yeni surum:
#   .\scripts\publish_release.ps1 -Branch mobil -Version 1.0.4 -AssetPath 'C:\Users\merta\Desktop\PEMF-Vet.apk' -Notes '...'
# =============================================================================
param(
  [Parameter(Mandatory = $true)][ValidateSet('exe', 'mobil')][string]$Branch,
  [Parameter(Mandatory = $true)][string]$Version,       # or. 1.5.0
  [Parameter(Mandatory = $true)][string]$AssetPath,     # installer .exe / .apk yolu
  [string]$Notes = "",
  [switch]$Mandatory,
  [string]$Repo = "mert61-python/pemf-update"
)
$ErrorActionPreference = 'Stop'
if (-not (Test-Path $AssetPath)) { throw "Asset bulunamadi: $AssetPath" }

# --- GitHub token (git credential) ---
$out = ("protocol=https`nhost=github.com`n`n" | git credential fill 2>$null)
$token = (($out | Where-Object { $_ -like 'password=*' }) -replace '^password=', '')
if (-not $token) { throw "GitHub token bulunamadi (git credential fill bos). Once `git push` ile giris yap." }
$h = @{ Authorization = "Bearer $token"; "User-Agent" = "pemf-publish"; Accept = "application/vnd.github+json" }

$tag = "$Branch-v$Version"
$assetName = [IO.Path]::GetFileName($AssetPath)
$sha = (Get-FileHash $AssetPath -Algorithm SHA256).Hash.ToLower()
Write-Host "Asset: $assetName  ($([int]((Get-Item $AssetPath).Length/1MB)) MB)  SHA256=$($sha.Substring(0,16))..."

# --- 1) release (varsa yeniden kullan) ---
$rel = $null
try { $rel = Invoke-RestMethod "https://api.github.com/repos/$Repo/releases/tags/$tag" -Headers $h } catch {}
if ($rel) { Write-Host "Release zaten var ($tag) — asset guncellenecek." }
else {
  $body = @{ tag_name = $tag; target_commitish = $Branch; name = "$Branch $Version"; body = $Notes } | ConvertTo-Json
  $rel = Invoke-RestMethod "https://api.github.com/repos/$Repo/releases" -Headers $h -Method Post -Body $body -ContentType 'application/json'
  Write-Host "Release olusturuldu: $tag (id $($rel.id))"
}

# --- 2) ayni isimli eski asset varsa sil ---
foreach ($a in $rel.assets) {
  if ($a.name -eq $assetName) {
    Invoke-RestMethod "https://api.github.com/repos/$Repo/releases/assets/$($a.id)" -Headers $h -Method Delete | Out-Null
    Write-Host "Eski asset silindi: $assetName"
  }
}

# --- 3) asset yukle ---
$uploadUrl = ($rel.upload_url -replace '\{.*\}', '') + "?name=$assetName"
$uh = @{ Authorization = "Bearer $token"; "User-Agent" = "pemf-publish"; "Content-Type" = "application/octet-stream" }
Write-Host "Asset yukleniyor... (buyuk dosyada birkac dakika surebilir)"
$asset = Invoke-RestMethod $uploadUrl -Headers $uh -Method Post -InFile $AssetPath
$dl = $asset.browser_download_url
Write-Host "Yuklendi: $dl"

# --- 4) latest.json manifest guncelle ---
if ($Branch -eq 'exe') { $manifest = @{ version = $Version; notes = $Notes; installerUrl = $dl; sha256 = $sha; mandatory = [bool]$Mandatory } }
else { $manifest = @{ version = $Version; notes = $Notes; apkUrl = $dl; sha256 = $sha; mandatory = [bool]$Mandatory } }
$content = ($manifest | ConvertTo-Json -Compress)
$b64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($content))
$existing = $null; try { $existing = Invoke-RestMethod "https://api.github.com/repos/$Repo/contents/latest.json?ref=$Branch" -Headers $h } catch {}
$pb = @{ message = "release $tag"; content = $b64; branch = $Branch }
if ($existing) { $pb['sha'] = $existing.sha }
Invoke-RestMethod "https://api.github.com/repos/$Repo/contents/latest.json" -Headers $h -Method Put -Body ($pb | ConvertTo-Json) -ContentType 'application/json' | Out-Null

Write-Host ""
Write-Host "TAMAM: $Branch $Version yayinlandi. Kurulu eski surumler artik guncellemeyi gorecek." -ForegroundColor Green
