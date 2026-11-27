# =============================================================================
# PEMF - YAYIN CI KAPISI (istem 66 CT2 a / Y326 katman 1). DIKKAT: YALNIZ ASCII (publish_release.ps1 ile ayni kural - PS 5.1).
# -----------------------------------------------------------------------------
# Uc commit'in GitHub CI'inda GEREKLI islerin (scripts/ci_sozlesmesi.json -> gerekli_isler) HEPSI yesil degilse ya da biri
# kosmadiysa yayin DURUR (hata metni: hangi is + baglanti). Gece tam kosusu kirmiziysa UYARI. Durum okunamazsa (gh yok / oturum
# yok / ag) yine DURUR (fail-closed). Cagiranlar: publish_release.ps1 + katmanli_yayin_hazirla.ps1 (Y30 suitinden SONRA,
# kimlik / manifest adimindan ONCE). Yayindan once elle de kosulabilir: python scripts\ci_durum.py
# -ChecksJson / -GeceJson YALNIZ testler icindir (gh yaniti yerine dosya); yayin betikleri bunlari VERMEZ.
# Kapi: tests/test_CT2a_yayin_CI_kapisi.py
# =============================================================================
param(
  [string]$Python = "",
  [string]$Sha = "",
  [string]$ChecksJson = "",
  [string]$GeceJson = ""
)
$ErrorActionPreference = 'Stop'
$kok = Split-Path -Parent $PSScriptRoot
if (-not $Python) {
  $gomulu = Join-Path (Split-Path -Parent $kok) 'python.exe'   # bu deponun gomulu yorumlayicisi (kokun bir ustu)
  $Python = if (Test-Path -LiteralPath $gomulu) { $gomulu } else { 'python' }
}
$arg = @((Join-Path $PSScriptRoot 'ci_durum.py'))
if ($Sha) { $arg += @('--sha', $Sha) }
if ($ChecksJson) { $arg += @('--checks-json', $ChecksJson) }
if ($GeceJson) { $arg += @('--gece-json', $GeceJson) }
$env:PYTHONIOENCODING = 'utf-8'
& $Python @arg
exit $LASTEXITCODE
