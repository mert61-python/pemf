# =============================================================================
# PEMF - GitHub Release yayinlayici (oto-guncelleme icin).
# DIKKAT (4A-1.6): bu dosya BOM'suz -> YALNIZ ASCII kalmali. Windows PowerShell 5.1 BOM'suz betigi ANSI okur; UTF-8 tire
# (U+2014) baytlarinin sonuncusu sag cift tirnak olur ve cift tirnakli dizgeyi KAPATIR -> betik hic ayristirilmaz.
# -----------------------------------------------------------------------------
# Yeni surum cikarinca TEK komut: release olusturur + asset (installer/APK) yukler
# + ilgili branch'in latest.json manifest'ini gunceller. Kurulu eski surumler bunu
# gorup guncellemeyi onerir (EXE: bildirim+tek-tik; mobil: indir).
#
# Token: git credential'dan otomatik alinir (apps/ui/backend push'unda kullandigin).
#
# KULLANIM:
#   # EXE (device installer) yeni surum:
#   .\scripts\publish_release.ps1 -Branch exe -Version 1.5.0 `
#       -AssetPath 'C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii\build_tools\Output\PEMFBackendSetup_device_v1.4.0.exe' `
#       -Notes 'Faz X duzeltmeleri'
#   # Mobil (APK) yeni surum:
#   .\scripts\publish_release.ps1 -Branch mobil -Version 1.0.4 -AssetPath 'C:\Users\merta\Desktop\PEMF-Vet.apk' -Notes '...'
#   # Iki dilli not (YH D1): -Notes Turkce (eski istemciler bunu okur), -NotesEn Ingilizce. Metinler docs/surum_notlari.json'da.
#   # YLI-A2.2: PowerShell yerel komut ciktisini [Console]::OutputEncoding ile cozer (varsayilan OEM 857/437) -> ONCE UTF-8 yap:
#   #   [Console]::OutputEncoding = [Text.Encoding]::UTF8
#   #   -Notes (python scripts\surum_notlari.py goster mobile 2.3.35 tr) -NotesEn (python scripts\surum_notlari.py goster mobile 2.3.35 en)
#   # Bozuk kodlamali not (UTF-8'in OEM / ANSI ile okunmus izi) suit / kimlik / agdan ONCE reddedilir (Test-BozukKodlama).
# =============================================================================
param(
  [Parameter(Mandatory = $true)][ValidateSet('exe', 'mobil')][string]$Branch,
  [Parameter(Mandatory = $true)][string]$Version,       # or. 1.5.0
  [Parameter(Mandatory = $true)][string]$AssetPath,     # installer .exe / .apk yolu
  [string]$Notes = "",
  [string]$NotesEn = "",                                # YH D1: Ingilizce surum notu (manifest `notes_en`)
  [switch]$Mandatory,
  [string]$Repo = "mert61-python/pemf-update"
)
$ErrorActionPreference = 'Stop'

# --- YH D1: manifest ve release govdesi SAF fonksiyonlar (ag / dosya YOK). Birim testi bunlari AST'den cikarip sahte girdiyle
#     cagirir (tests/test_YH_D1_surum_notlari_iki_dil.py) - betigin kendisi testte KOSULMAZ. `notes` Turkce kalir (eski APK /
#     backend onu okur); `notes_en` YALNIZ doluysa eklenir (eski okuyucular icin bicim aynen korunur).
function New-YayinManifesti {
  param([string]$Branch, [string]$Version, [string]$Notes, [string]$NotesEn, [string]$Url, [string]$Sha, [bool]$Mandatory, $PrevStable)
  $m = [ordered]@{ version = $Version; notes = $Notes }
  if ($NotesEn) { $m['notes_en'] = $NotesEn }
  if ($Branch -eq 'exe') { $m['installerUrl'] = $Url } else { $m['apkUrl'] = $Url }
  $m['sha256'] = $Sha
  $m['mandatory'] = $Mandatory
  if ($PrevStable) { $m['previousStable'] = $PrevStable }
  return $m
}
function New-YayinGovdesi {
  param([string]$Notes, [string]$NotesEn)
  if ($NotesEn) { return "$Notes`n`n---`nEnglish:`n$NotesEn" }
  return $Notes
}
# YLI-A2.2: UTF-8 baytlarinin OEM (cp857 / cp437: lider bayt C3 / C4 / C5 / E2 -> kutu cizgisi U+2500-257F) ya da ANSI (cp1254 / cp1252:
# A-tilde / A-diaeresis / A-ring) kod sayfasiyla okunmus izi. Turkce ve Ingilizce notlarda bu karakterler MESRU olarak gecmez.
function Test-BozukKodlama {
  param([string]$Metin)
  return [bool]($Metin -match '[\u2500-\u257F\u00C3\u00C4\u00C5]')
}

if ($NotesEn -and -not $Notes) { throw "-NotesEn tek basina verilemez: once Turkce not (-Notes) gerekli (eski istemciler yalniz notes'u okur)." }
foreach ($n in @($Notes, $NotesEn)) {
  if (Test-BozukKodlama $n) { throw "Surum notu bozuk kodlamali (UTF-8 metin OEM/ANSI kod sayfasiyla okunmus): once [Console]::OutputEncoding = [Text.Encoding]::UTF8 yapip notu yeniden alin. Yayin DURDU." }
}
if (-not (Test-Path $AssetPath)) { throw "Asset bulunamadi: $AssetPath" }

# --- 0) Y30 / D4.10: YAYIN ONCESI ZORUNLU TAM SUIT (sahip karari) ---
# Kimlik bilgisine ve aga dokunmadan ONCE: PEMF_CAPRAZ_KAYNAK_ZORUNLU=1 + PEMF_GOLDEN_REQUIRED=1 ile tam suit.
# Gecmezse hicbir sey yayinlanmaz. Atlama anahtari YOK (kapi: tests/test_yayin_oncesi_suit_Y30_D410.py).
& (Join-Path $PSScriptRoot 'yayin_oncesi_suit.ps1')
if ($LASTEXITCODE -ne 0) { throw "Yayin oncesi tam suit GECMEDI (cikis=$LASTEXITCODE) - yayin DURDU (Y30)." }

# --- 0b) CT2 a (Y326 katman 1): uc commit'in GitHub CI'i - GEREKLI islerin hepsi yesil degilse / kosmadiysa DUR ---
# Liste: scripts/ci_sozlesmesi.json (CT3 dal korumasi ayni listeyi kullanir). Gece kirmizisi UYARI. Kapi: tests/test_CT2a_yayin_CI_kapisi.py
& (Join-Path $PSScriptRoot 'yayin_ci_kapisi.ps1')
if ($LASTEXITCODE -ne 0) { throw "Uc commit'in GitHub CI'i yesil degil (cikis=$LASTEXITCODE; is + baglanti yukarida) - yayin DURDU (CT2 a)." }

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
if ($rel) { Write-Host "Release zaten var ($tag) - asset guncellenecek." }
else {
  $body = @{ tag_name = $tag; target_commitish = $Branch; name = "$Branch $Version"; body = (New-YayinGovdesi -Notes $Notes -NotesEn $NotesEn) } | ConvertTo-Json
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

# --- 4) latest.json manifest guncelle (audit B-9.2: rollback icin previousStable) ---
# ONCE mevcut latest.json'u cek: eski surumu, YENI manifest'e 'previousStable' (rollback hedefi)
# olarak tasiriz. Boylece kotu bir guncelleme sahada sorun cikarirsa operator son iyi surume doner.
$existing = $null; try { $existing = Invoke-RestMethod "https://api.github.com/repos/$Repo/contents/latest.json?ref=$Branch" -Headers $h } catch {}
$prevStable = $null
if ($existing -and $existing.content) {
  try {
    $oldJson = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String(($existing.content -replace '\s','')))
    $old = $oldJson | ConvertFrom-Json
    $oldUrl = if ($Branch -eq 'exe') { $old.installerUrl } else { $old.apkUrl }
    if ($old.version -and $old.version -ne $Version -and $oldUrl -and $old.sha256) {
      $prevStable = @{ version = "$($old.version)"; installerUrl = "$oldUrl"; sha256 = "$($old.sha256)" }
    }
  } catch { Write-Host "Onceki manifest okunamadi (previousStable atlandi): $_" }
}
$manifest = New-YayinManifesti -Branch $Branch -Version $Version -Notes $Notes -NotesEn $NotesEn -Url $dl -Sha $sha -Mandatory ([bool]$Mandatory) -PrevStable $prevStable
if ($prevStable) { Write-Host "Rollback hedefi (previousStable): $($old.version)" }
$content = ($manifest | ConvertTo-Json -Compress)
$b64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($content))
$pb = @{ message = "release $tag"; content = $b64; branch = $Branch }
if ($existing) { $pb['sha'] = $existing.sha }
Invoke-RestMethod "https://api.github.com/repos/$Repo/contents/latest.json" -Headers $h -Method Put -Body ($pb | ConvertTo-Json) -ContentType 'application/json' | Out-Null

Write-Host ""
Write-Host "TAMAM: $Branch $Version yayinlandi. Kurulu eski surumler artik guncellemeyi gorecek." -ForegroundColor Green
