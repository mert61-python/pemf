# =============================================================================
# PEMF — LAUNCHER KATMANLI YAYIN HAZIRLIĞI (Y30 · 4-A devri #4)
# -----------------------------------------------------------------------------
# Sahip kararı Y30: yayın öncesi zorunlu tam süit YAYIN BETİĞİNE BAĞLI zorunlu adımdır. D4.10 bunu `publish_release.ps1`'e
# (exe / mobil kanalı) bağladı; launcher KATMANLI yayını (`make_manifest.py` + elle GitHub release) betikli değildi → o
# hatta süit hiç koşmadan manifest üretilip yüklenebiliyordu. Bu betik o kanalın betikli girişidir:
#   (0) `yayin_oncesi_suit.ps1` (ZORUNLU kip) → geçmezse manifest YAZILMAZ, DURUR. Atlama anahtarı YOK.
#   (1) `scripts/make_manifest.py <ManifestArgs>` → manifest. Düşerse DURUR.
# Yükleme (gh release …) bu betikte YOK — BUILD.md §6 sırasıyla ELLE (Ö.4-Y1: yayın durdurulmuştur; bugün koşturulmaz).
# Kapı: tests/test_katmanli_yayin_Y30_SUITI_once_kosar_4A_devir4.py
#
# KULLANIM (depo kökünden ya da herhangi bir yerden):
#   pwsh -File scripts\katmanli_yayin_hazirla.ps1 -ManifestArgs:"--dir,pemf-app-packages,--version,<sürüm>,--tag,client-app-v<sürüm>,--repo,mert61-python/pemf-update"
#   ⚠️ İki nokta (`-ManifestArgs:"…"`) ŞART: değer `--` ile başladığı için `pwsh -File` onu yeni bir parametre adı sanar.
# Denetim / sandbox kancaları (yayın makinesinde KULLANILMAZ): -PytestOnek, -Hedef (yayin_oncesi_suit.ps1'e aynen geçer).
# ⚠️ 4B-3.4: kancalar Y30'u daraltır ya da TÜMDEN atlar (ölçüldü: no-op -PytestOnek ile hiç test koşmadan manifest yazıldı) →
# YALNIZ açık denetim bayrağıyla (PEMF_Y30_DENETIM_KANCASI=1) kabul edilir ve çıktı "DAR SUIT" diye damgalanır.
# =============================================================================
param(
  [Parameter(Mandatory = $true)][string[]]$ManifestArgs,
  [string]$Python = "",
  [string[]]$PytestOnek = @(),
  [string]$Hedef = "tests"
)
$ErrorActionPreference = 'Stop'
$kok = Split-Path -Parent $PSScriptRoot
# `pwsh -File … -X "a,b"` dizi sözdizimini çözmez, TEK dize verir → virgülden böl.
if ($ManifestArgs.Count -eq 1 -and $ManifestArgs[0] -like '*,*') { $ManifestArgs = @($ManifestArgs[0] -split ',') }
if (-not $Python) {
  $gomulu = Join-Path (Split-Path -Parent $kok) 'python.exe'   # bu deponun gömülü yorumlayıcısı (kökün bir üstü)
  $Python = if (Test-Path -LiteralPath $gomulu) { $gomulu } else { 'python' }
}

# --- 0) Y30: YAYIN ÖNCESİ ZORUNLU TAM SÜİT ---
$kancaVar = ($PytestOnek.Count -gt 0) -or ($Hedef -ne 'tests')
if ($kancaVar -and $env:PEMF_Y30_DENETIM_KANCASI -ne '1') {
  throw "Y30 denetim kancasi (-PytestOnek / -Hedef) yayinda KULLANILMAZ - tam suit daraltilamaz, manifest YAZILMADI (yalniz denetim: PEMF_Y30_DENETIM_KANCASI=1)."
}
if ($kancaVar) { Write-Host "[KATMANLI-YAYIN] !!! DAR SUIT (denetim kancasi: Hedef=$Hedef) - bu manifest YAYINLANAMAZ !!!" }
# ⚠️ Adlandırılmış parametreler HASHTABLE ile geçirilir (dizi splat'ı "-Ad" dizesini KONUMSAL verir).
$y30 = @{ Hedef = $Hedef }
if ($PytestOnek.Count -gt 0) { $y30.PytestOnek = $PytestOnek }
& (Join-Path $PSScriptRoot 'yayin_oncesi_suit.ps1') @y30
if ($LASTEXITCODE -ne 0) {
  throw "Yayin oncesi tam suit GECMEDI (cikis=$LASTEXITCODE) - manifest YAZILMADI, katmanli yayin DURDU (Y30)."
}

# --- 1) MANIFEST ---
Write-Host "[KATMANLI-YAYIN] Y30 GECTI -> manifest uretiliyor: make_manifest.py $($ManifestArgs -join ' ')"
& $Python (Join-Path $kok 'scripts\make_manifest.py') @ManifestArgs
if ($LASTEXITCODE -ne 0) { throw "make_manifest.py DUSTU (cikis=$LASTEXITCODE) - manifest YAZILMADI." }
Write-Host "[KATMANLI-YAYIN] manifest yazildi. Yukleme (GitHub release) ELLE ve SIRAYLA: BUILD.md bolum 6."
