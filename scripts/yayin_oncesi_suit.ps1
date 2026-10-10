# =============================================================================
# PEMF — YAYIN ÖNCESİ ZORUNLU TAM SÜİT (Y30 · D4.10 · B-10.3)
# -----------------------------------------------------------------------------
# Sahip kararı Y30 (2026-10-01): yayın öncesi zorunlu tam süit YAYIN BETİĞİNE BAĞLI zorunlu adımdır; süit geçmeden
# betik ilerlemez. `publish_release.ps1` bu betiği ağa / kimlik bilgisine dokunmadan ÖNCE çağırır ve çıkış kodu
# 0 değilse DURUR. (Ö.4-Y1: yayın durdurulmuştur — bu betik ve publish bugün koşturulmaz.)
#
# Neden ayrı ve ZORUNLU kipte: CI `pytest tests`i varsayılan kipte koşar; orada kardeş kaynak (release_assets
# ağırlıkları, izlenmeyen test girdileri, apps/ui) yoksa ≥193 test SESSİZCE atlanıyordu (88'i KRİTİK/KARŞIT).
# "Yayın makinesi bayrağı ayarlar" güvencesinin hiçbir betikte karşılığı yoktu. Burada:
#   PEMF_CAPRAZ_KAYNAK_ZORUNLU=1  → tests/capraz.py atlamayı BAŞARISIZLIĞA çevirir
#   PEMF_GOLDEN_REQUIRED=1        → AI altın değer / CKD asgari girdi testleri atlanamaz
#   -rs                           → kalan her atlama NEDENİYLE listelenir
#
# KULLANIM (depo kökünden ya da herhangi bir yerden):
#   pwsh -File scripts\yayin_oncesi_suit.ps1
# Denetim / sandbox kancaları (yayın makinesinde KULLANILMAZ):
#   -PytestOnek  pytest'i çağıran önek (varsayılan: <Python> -m pytest), ör. bekçili koşucu
#   -Hedef       test hedefi (varsayılan: tests)
# Çıkış: pytest'in çıkış kodu (0 = geçti; ≠0 = YAYIN DURUR).
# =============================================================================
param(
  [string]$Python = "",
  [string[]]$PytestOnek = @(),
  [string]$Hedef = "tests"
)
$ErrorActionPreference = 'Stop'
$kok = Split-Path -Parent $PSScriptRoot
# `pwsh -File … -PytestOnek "a,-m,pytest"` dizi sözdizimini çözmez, TEK dize verir → virgülden böl.
if ($PytestOnek.Count -eq 1 -and $PytestOnek[0] -like '*,*') { $PytestOnek = @($PytestOnek[0] -split ',') }
if (-not $PytestOnek -or $PytestOnek.Count -eq 0) {
  if (-not $Python) {
    $gomulu = Join-Path (Split-Path -Parent $kok) 'python.exe'   # bu deponun gömülü yorumlayıcısı (kökün bir üstü)
    $Python = if (Test-Path -LiteralPath $gomulu) { $gomulu } else { 'python' }
  }
  $PytestOnek = @($Python, '-m', 'pytest')
}

$env:PEMF_CAPRAZ_KAYNAK_ZORUNLU = '1'
$env:PEMF_GOLDEN_REQUIRED = '1'

$komut = $PytestOnek[0]
$argumanlar = @()
if ($PytestOnek.Count -gt 1) { $argumanlar += $PytestOnek[1..($PytestOnek.Count - 1)] }
$argumanlar += @($Hedef, '-q', '-rs', '-p', 'no:cacheprovider')

Write-Host "[YAYIN-ONCESI] tam suit (ZORUNLU=1, GOLDEN_REQUIRED=1): $komut $($argumanlar -join ' ')"
Push-Location -LiteralPath $kok
try {
  & $komut @argumanlar
  $rc = $LASTEXITCODE
} finally {
  Pop-Location
}
if ($null -eq $rc) { $rc = 1 }
if ($rc -ne 0) {
  Write-Host "[YAYIN-ONCESI] TAM SUIT GECMEDI (cikis=$rc) - YAYIN DURDU (Y30). Kirmizilari ve atlama nedenlerini (-rs) okuyun."
  exit $rc
}
Write-Host "[YAYIN-ONCESI] tam suit GECTI (ZORUNLU kip)."
exit 0
