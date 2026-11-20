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
#   -rfEs                         → kırmızılar (FAILED/ERROR) ve kalan her atlama NEDENİYLE kısa özette listelenir
#                                   (⚠️ 4A-4.1: `-r` varsayılan `fE`'nin YERİNE geçer — yalnız `-rs` kırmızıları özetten SİLERDİ)
#
# KULLANIM (depo kökünden ya da herhangi bir yerden):
#   pwsh -File scripts\yayin_oncesi_suit.ps1
# Denetim / sandbox kancaları (yayın makinesinde KULLANILMAZ):
#   -PytestOnek  pytest'i çağıran önek (varsayılan: <Python> -m pytest), ör. bekçili koşucu
#   -Hedef       test hedefi (varsayılan: tests)
# Çıkış: pytest'in çıkış kodu (0 = geçti; ≠0 = YAYIN DURUR).
#
# Y176 (S-YH.7 = S-4BI.9) YEŞİL-SÜİT DAMGASI — yalnız TAM kipte (kancasız: -PytestOnek YOK, -Hedef 'tests'):
#   koşu BAŞINDA eski damga silinir (kırmızı / yarıda kesilen koşu eski damgayı bırakmaz), süit GEÇİNCE
#   `<git-dizini>\pemf-y30-damga.json` yazılır (koşu başındaki HEAD · UTC zaman · kip TAM). `make_manifest.py` yayın
#   dizinine (`pemf-app-packages`) yazarken HEAD'i tutan, ≤ 24 sa, TAM damga ister; tek istisna paket / sha değiştirmeyen
#   ve rollout'u DÜŞÜREN "acil fren" çağrısıdır. Kancalı (denetim / sandbox) koşu damgaya DOKUNMAZ.
#   Kapı: tests/test_Y176_yesil_suit_damgasi.py
#
# Y312 (sahip 20-11: "tam testlerde süreler kısalsın" · "xdist kur") PARALEL SÜİT — pytest-xdist KURULUYSA TAM kip süiti
#   `-n <işçi> --dist loadgroup` ile koşar (seri ~1 sa 47 dk). İşçi = min(8, fiziksel çekirdek); bir dosyanın testleri AYNI işçide
#   kendi sırasıyla (tests/xdist_grup.py), `xdist_group("seri")` işaretliler tek işçide. İşçi sayısı süiti DARALTMAZ: TAM kip,
#   Y176 damgası ve "kanca yok" kuralı AYNEN. xdist YOKSA süit SERİ koşar + UYARI satırı (yayın DURMAZ).
#   -Isci 0  → elle SERİ (paralelde ortam sorunu çıkarsa geri dönüş; yine TAM kip) · -Isci <n> → n işçi.
#   Kancalı (denetim) kip SERİ kalır: denetim koşucusunun bekçisi kendi sürecinde kurulur, xdist işçisine GEÇMEZ.
#   Kapı: tests/test_yayin_oncesi_suit_PARALEL_Y312.py
# =============================================================================
param(
  [string]$Python = "",
  [string[]]$PytestOnek = @(),
  [string]$Hedef = "tests",
  [int]$Isci = -1
)
$ErrorActionPreference = 'Stop'
$kok = Split-Path -Parent $PSScriptRoot
# Y176: TAM kip = kanca yok. `katmanli_yayin_hazirla.ps1` -Hedef'i HER ZAMAN geçirir → Hedef değerine bakılır, bağlı olup olmadığına değil.
$tamKip = (-not $PSBoundParameters.ContainsKey('PytestOnek')) -and ($Hedef -eq 'tests')
function Get-Y30DamgaYolu([string]$Kok) {
  try { $gd = (& git -C $Kok rev-parse --absolute-git-dir 2>$null) } catch { return $null }
  if ($LASTEXITCODE -ne 0 -or -not $gd) { return $null }
  return (Join-Path ([string]$gd).Trim() 'pemf-y30-damga.json')
}
function Get-Y30Head([string]$Kok) {
  try { $h = (& git -C $Kok rev-parse HEAD 2>$null) } catch { return $null }
  if ($LASTEXITCODE -ne 0 -or -not $h) { return $null }
  return ([string]$h).Trim()
}
# `pwsh -File … -PytestOnek "a,-m,pytest"` dizi sözdizimini çözmez, TEK dize verir → virgülden böl.
if ($PytestOnek.Count -eq 1 -and $PytestOnek[0] -like '*,*') { $PytestOnek = @($PytestOnek[0] -split ',') }
if (-not $PytestOnek -or $PytestOnek.Count -eq 0) {
  if (-not $Python) {
    $gomulu = Join-Path (Split-Path -Parent $kok) 'python.exe'   # bu deponun gömülü yorumlayıcısı (kökün bir üstü)
    $Python = if (Test-Path -LiteralPath $gomulu) { $gomulu } else { 'python' }
  }
  $PytestOnek = @($Python, '-m', 'pytest')
}

# Y312: paralel argümanları (yalnız kancasız kip; xdist yoksa SERİ + uyarı — yayın DURMAZ).
$paralel = @()
if ($PSBoundParameters.ContainsKey('PytestOnek')) {
  Write-Host "[YAYIN-ONCESI] denetim kancasi: suit SERI (bekci xdist iscisine gecmez - Y312)."
} elseif ($Isci -eq 0) {
  Write-Host "[YAYIN-ONCESI] -Isci 0: suit SERI (elle secildi - Y312)."
} else {
  # stderr'siz yoklama: paket yoksa boş satır basar (5.1'de `2>$null` + Stop yerel komutu istisnaya çevirir). Çıktısız komutun sonucu
  # `[string]` dönüşümünde $null kalır → dize içine gömülür (her zaman dize).
  $xdistSurum = ''
  try {
    $xdistSurum = "$(& $PytestOnek[0] -c "import importlib.util as u; print(u.find_spec('xdist') and u.find_spec('execnet') and __import__('xdist').__version__ or '')")"
  } catch { $xdistSurum = '' }
  $xdistSurum = $xdistSurum.Trim()
  if (-not $xdistSurum) {
    Write-Host "[YAYIN-ONCESI] UYARI: pytest-xdist kurulu degil - suit SERI kosuyor (yavas; yayin DURMAZ). Kurulum: requirements-test.txt (Y312)."
  } else {
    $cekirdek = 0
    try { $cekirdek = [int]((Get-CimInstance Win32_Processor -ErrorAction Stop | Measure-Object -Property NumberOfCores -Sum).Sum) } catch { $cekirdek = 0 }
    if ($cekirdek -lt 1) { $cekirdek = [Math]::Max(1, [int][Math]::Floor([Environment]::ProcessorCount / 2)) }
    if ($Isci -lt 0) { $Isci = [Math]::Min(8, $cekirdek) }
    $paralel = @('-n', "$Isci", '--dist', 'loadgroup')
    Write-Host "[YAYIN-ONCESI] paralel: pytest-xdist $xdistSurum - $Isci isci (fiziksel cekirdek $cekirdek), --dist loadgroup (Y312)."
  }
}

$env:PEMF_CAPRAZ_KAYNAK_ZORUNLU = '1'
$env:PEMF_GOLDEN_REQUIRED = '1'

# Y176: TAM kipte eski damga koşu BAŞINDA silinir; silinemezse süit KOŞMAZ (bayat damga bir kırmızı koşudan sağ çıkmasın).
$damgaYolu = $null
$basHead = $null
if ($tamKip) {
  $damgaYolu = Get-Y30DamgaYolu $kok
  $basHead = Get-Y30Head $kok
  if ($damgaYolu -and (Test-Path -LiteralPath $damgaYolu)) {
    Remove-Item -LiteralPath $damgaYolu -Force
    if (Test-Path -LiteralPath $damgaYolu) {
      Write-Host "[YAYIN-ONCESI] eski Y30 damgasi SILINEMEDI: $damgaYolu - DURDU (Y176)."
      exit 1
    }
  }
}

$komut = $PytestOnek[0]
$argumanlar = @()
if ($PytestOnek.Count -gt 1) { $argumanlar += $PytestOnek[1..($PytestOnek.Count - 1)] }
$argumanlar += @($Hedef, '-q', '-rfEs', '-p', 'no:cacheprovider') + $paralel

Write-Host "[YAYIN-ONCESI] tam suit (ZORUNLU=1, GOLDEN_REQUIRED=1): $komut $($argumanlar -join ' ')"
# ⚠️ PSModulePath (ölçüldü, 4-A ZORUNLU koşusu 2026-10-10): pwsh 7 kendi modül dizinlerini süreç PSModulePath'ine ekler;
# pytest'in açtığı powershell.exe (5.1) bunu MİRAS alır, Microsoft.PowerShell.Security'nin 7 sürümünü yükleyemez ve
# "Get-Acl ... module could not be loaded" ile düşer → 9 ACL testi YALANCI KIRMIZI, Y30 her yayını durdururdu. (pwsh
# powershell.exe'yi DOĞRUDAN açınca yolu kendisi ayıklar; araya python girince ayıklama yok.) Süit süresince değişken
# KALDIRILIR — her kabuk kendi varsayılanını kurar — ve sonra AYNEN geri yüklenir (betik `&` ile çağrılır; publish'in
# kalanı etkilenmesin).
# ⚠️ S-4B.3 (4-A inc. A1 S4, ölçüldü 4-B): değişken SİLİNMEZ, BOŞ DİZEYE çekilir. Silinen değişkeni pwsh bir sonraki modül
# (oto)yüklemesinde KENDİ yollarıyla yeniden kurar → python → powershell.exe 5.1 yine düşer (sonda: silme = dokunmama = KIRMIZI,
# boş dize = YEŞİL). Bugün silme ile çağrı arasında otoyükleme yok; araya giren her cmdlet Y30'u sessizce bozardı. Boş dizede
# her kabuk kendi varsayılanını kurar. Kapı: tests/test_yayin_oncesi_suit_PSMODULEPATH_otoyuklemeye_dayanikli_S4B3.py
$psModulYolu = $env:PSModulePath
$env:PSModulePath = ''
Push-Location -LiteralPath $kok
try {
  & $komut @argumanlar
  $rc = $LASTEXITCODE
} finally {
  # Önceden YOKSA yine YOK bırak ('' kalmasın — SetEnvironmentVariable($null) değişkeni silmez, "" bırakır).
  if ($null -ne $psModulYolu) { $env:PSModulePath = $psModulYolu }
  else { Remove-Item -LiteralPath 'Env:PSModulePath' -ErrorAction SilentlyContinue }
  Pop-Location
}
if ($null -eq $rc) { $rc = 1 }
if ($rc -ne 0) {
  Write-Host "[YAYIN-ONCESI] TAM SUIT GECMEDI (cikis=$rc) - YAYIN DURDU (Y30). Kirmizilari (FAILED/ERROR) ve atlama nedenlerini (SKIPPED) kisa ozette okuyun."
  exit $rc
}
# Y176: yalnız TAM kipte ve süit GEÇTİYSE damga yazılır — koşu başındaki HEAD için (süit sırasında HEAD değiştiyse YAZILMAZ).
if ($tamKip) {
  $sonHead = Get-Y30Head $kok
  if (-not $damgaYolu -or -not $basHead) {
    Write-Host "[YAYIN-ONCESI] UYARI: git dizini / HEAD okunamadi - Y30 damgasi YAZILMADI; make_manifest yayin dizinine YAZMAZ (Y176)."
  } elseif ($sonHead -ne $basHead) {
    Write-Host "[YAYIN-ONCESI] UYARI: suit sirasinda HEAD degisti ($basHead -> $sonHead) - Y30 damgasi YAZILMADI (Y176)."
  } else {
    $damga = [ordered]@{ head = $basHead; zaman = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds(); kip = 'TAM'; betik = 'scripts/yayin_oncesi_suit.ps1' }
    $gecici = "$damgaYolu.tmp"
    [IO.File]::WriteAllText($gecici, ($damga | ConvertTo-Json -Compress), [Text.UTF8Encoding]::new($false))
    Move-Item -LiteralPath $gecici -Destination $damgaYolu -Force
    Write-Host "[YAYIN-ONCESI] Y30 damgasi yazildi: HEAD=$basHead (24 sa gecerli; make_manifest yayin dizinine yazarken ister - Y176)."
  }
}
Write-Host "[YAYIN-ONCESI] tam suit GECTI (ZORUNLU kip)."
exit 0
