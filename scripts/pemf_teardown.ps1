# =============================================================================
# PEMF TEARDOWN — birleşik kaldırma motoru (Faz 2). pemf_footprint.ps1'i tüketir.
# -----------------------------------------------------------------------------
# TÜKETİCİLER (hepsi AYNI mantık + AYNI KVKK politikası):
#   • setup_services.ps1 -Uninstall      -> Invoke-PemfTeardown -Scope backend
#   • pemf_uninstall_all.ps1 (standalone)-> Invoke-PemfTeardown -Scope all
# NOT: eski GUI installer'ı (PEMF_Setup.iss) EMEKLİYE AYRILDI (kaynağı Faz-8'de silindi, build
# edilmiyordu). 'gui' scope + footprint KORUNUR: SAHADAKİ mevcut eski-GUI kurulumları standalone
# tam-kaldırıcı (Scope=all) ile KVKK-doğru temizlenir.
#
# KVKK: hasta verisi (Kvkk=$true) VARSAYILAN KORUNUR; yalnız -IncludePatientData ile silinir.
# -DryRun: hiçbir şey silmeden ne silineceğini logla (tam-kaldırıcı için güvenli önizleme).
#
# Bu dosya DOT-SOURCE edilmek içindir: . .\pemf_teardown.ps1  ->  Invoke-PemfTeardown ...
# =============================================================================

. (Join-Path $PSScriptRoot 'pemf_footprint.ps1')

# Log yeri: footprint-DIŞI olmalı — aksi halde teardown PEMF_System'i siler, sonra final log satırı
# onu YENİDEN yaratır (kalıntı bırakır). Varsayılan $env:TEMP; standalone Desktop'a override eder
# ($env:PEMF_TEARDOWN_LOG) ki KVKK "sildim" raporu kalıcı olsun.
$script:PemfLog = if ($env:PEMF_TEARDOWN_LOG) { $env:PEMF_TEARDOWN_LOG } else { Join-Path $env:TEMP 'pemf_teardown.log' }
function Write-PemfLog($msg, $color = 'Gray') {
    try {
        $dir = Split-Path $script:PemfLog -Parent
        if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
        ("$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $msg") | Add-Content -Path $script:PemfLog -Encoding UTF8
    } catch {}
    Write-Host "[pemf-teardown] $msg" -ForegroundColor $color
}

# ⚠️ DENETİM 2026-08-04 — SESSİZ SİLME BAŞARISIZLIĞI (KVKK YANLIŞ-GÜVENCE)
# Silme çağrılarının hepsi `-ErrorAction SilentlyContinue` ile yapılıyor (kaldırıcıda bu DOĞRU:
# bir adım patlayınca temizliğin geri kalanı sürmeli). AMA başarı KOŞULSUZ loglanıyordu:
# "silindi (HASTA-VERİSİ): <yol>" ve sonunda "HASTA VERİSİ DE SİLİNDİ (tam temizlik)".
# Dosya kilitliyse (çalışan backend/AV taraması) veya izin yoksa silme SESSİZCE başarısız olur,
# operatör ise kalıcı silme talebinin YERİNE GETİRİLDİĞİNİ sanır. Hasta verisi diskte kalırken
# kayıt "silindi" der — bir tıbbi cihazda kabul edilemez bir yanlış-güvence.
# Artık her silme DOĞRULANIR; başarısızlıklar sayılır ve sonuç raporu buna göre değişir.
$script:PemfFailed = @()
function Assert-PemfRemoved {
    param([string]$Path, [string]$Tag)
    if (Test-Path -LiteralPath $Path -ErrorAction SilentlyContinue) {
        $script:PemfFailed += $Path
        Write-PemfLog "SİLİNEMEDİ ($Tag): $Path — dosya kilitli veya izin yok" 'Red'
        return $false
    }
    Write-PemfLog "silindi ($Tag): $Path"
    return $true
}

# Bir öğe verilen kapsamda kaldırılmalı mı? 'shared' = backend+gui (ve all); client per-user kalır.
function Test-PemfScope([string]$Owner, [string]$Scope) {
    if ($Scope -eq 'all') { return $true }
    if ($Owner -eq $Scope) { return $true }
    if ($Owner -eq 'shared' -and ($Scope -eq 'backend' -or $Scope -eq 'gui')) { return $true }
    return $false
}

# Servisleri durdur + kaldır. TIBBİ GÜVENLİK: önce GRACEFUL sc-stop (→ NSSM Ctrl+C → backend
# bobin-STOP + STM kuyruk-flush) + servis STOPPED olana kadar BEKLE ki bobinler (hasta üzerindeyse)
# güvene alınsın; force-kill'i ÖNCE yaparsak bu graceful bobin-STOP ATLANIR. SONRA sc-delete +
# kalan için force-kill (fallback: graceful asılıysa dosya kilidi kalmasın). (mosquitto'da
# Stop-Service -Force StartPending'de ASILIR → sc + süreç-kill kullanılır.)
function Stop-PemfProcessesAndServices([string[]]$Services) {
    # ⚠️ TIBBİ GÜVENLİK — SIRA ÖNEMLİ (denetim 2026-08-04, P2).
    # ESKİ HÂLİ: ilk döngü TÜM servislere milisaniyeler içinde `sc.exe stop` gönderiyor, beklemeyi
    # AYRI bir döngüde SONRA yapıyordu. mosquitto <1 sn'de kapanır; backend ise `_safe_stop_outputs`
    # içinde ÖNCE 1.5 sn STM kuyruğunu boşaltır, ESP bobinleri (6-8) için MQTT STOP'u ANCAK ondan
    # sonra yayınlar → o an broker ÇOKTAN ÖLMÜŞTÜR. `_mqtt_publish` 127.0.0.1:1883'e bağlanamayınca
    # SESSİZCE False döner ve `_safe_stop_outputs` dönüş değerini kontrol etmez → ESP bobinleri
    # kapanış STOP'unu HİÇ ALMAZ. ESP'nin link-watchdog'u YOKTUR (STM'in 1500 ms ölü-adam devresinin
    # karşılığı yok) → bobin kendi süresi dolana kadar HASTANIN ÜZERİNDE sürmeye devam eder.
    # setup_services.ps1 bu sırayı DOĞRU kuruyor; teardown modülü kaybetmişti.
    # YENİ: her servisi SIRAYLA durdur ve STOPPED olmasını BEKLE; broker DAİMA EN SON kapanır.
    $ordered = @($Services | Where-Object { $_ -ne 'mosquitto' }) +
               @($Services | Where-Object { $_ -eq 'mosquitto' })
    foreach ($svc in $ordered) {
        if (-not (Get-Service -Name $svc -ErrorAction SilentlyContinue)) { continue }
        & sc.exe stop $svc *>$null
        # sc stop asenkron döner → STOPPED olana kadar bekle (NSSM AppStopMethodConsole 15s + pay ~20sn).
        for ($i = 0; $i -lt 40 -and ((Get-Service -Name $svc -ErrorAction SilentlyContinue).Status -in @('Running', 'StopPending')); $i++) { Start-Sleep -Milliseconds 500 }
        # DENETİM 2026-08-04 (P3): burada KOŞULSUZ "servis durduruldu" yazılıyordu. 20 sn'lik
        # bekleme zaman aşımına uğrayıp servis hâlâ Running/StopPending olsa bile log "durduruldu"
        # diyordu — aynı raporun KVKK silme kanıtı olarak kullanıldığı düşünülürse yanıltıcı.
        # Ayrıca durmayan bir backend, hemen ardından gelen dosya silmelerini de kilitler; bu
        # satır o başarısızlığın TEK görünür işareti olurdu.
        $son = (Get-Service -Name $svc -ErrorAction SilentlyContinue)
        if ($son -and $son.Status -in @('Running', 'StopPending')) {
            $script:PemfFailed += "servis: $svc ($($son.Status))"
            Write-PemfLog "SERVİS DURMADI: $svc — durum $($son.Status) (dosya kilitleri sürebilir)" 'Red'
        } else {
            Write-PemfLog "servis durduruldu: $svc"
        }
    }
    foreach ($svc in $Services) {
        if (Get-Service -Name $svc -ErrorAction SilentlyContinue) { & sc.exe delete $svc *>$null; Write-PemfLog "servis kaldırıldı: $svc" }
    }
    Get-Process cloudflared, nssm, mosquitto, PEMF_Backend -ErrorAction SilentlyContinue |
        Stop-Process -Force -ErrorAction SilentlyContinue
    # Kayıtlar gerçekten silinene + handle'lar bırakılana kadar kısa poll.
    foreach ($svc in $Services) {
        for ($i = 0; $i -lt 10 -and (Get-Service -Name $svc -ErrorAction SilentlyContinue); $i++) { Start-Sleep 1 }
    }
}

function Remove-PemfTasks([string[]]$Tasks, [switch]$DryRun) {
    foreach ($t in $Tasks) {
        schtasks /Query /TN $t *>$null
        if ($LASTEXITCODE -eq 0) {
            if ($DryRun) { Write-PemfLog "[DRY] görev: $t" 'Yellow' }
            else { schtasks /Delete /TN $t /F *>$null; Write-PemfLog "görev silindi: $t" }
        }
    }
    # Hotspot keep-alive wscript'i System32\wscript.exe'den çalışır -> cmdline ile yakala.
    if (-not $DryRun) {
        Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -eq 'wscript.exe' -and $_.CommandLine -match 'start_hotspot_hidden' } |
            ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    }
}

function Remove-PemfFirewall([string]$Rx, [switch]$DryRun) {
    Get-NetFirewallRule -ErrorAction SilentlyContinue | Where-Object { $_.DisplayName -match $Rx } | ForEach-Object {
        if ($DryRun) { Write-PemfLog "[DRY] firewall: $($_.DisplayName)" 'Yellow' }
        else { $_ | Remove-NetFirewallRule -ErrorAction SilentlyContinue; Write-PemfLog "firewall silindi: $($_.DisplayName)" }
    }
}

function Remove-PemfEnv([string]$Rx, [switch]$DryRun) {
    $key = 'HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Environment'
    (Get-ItemProperty $key -ErrorAction SilentlyContinue).PSObject.Properties |
        Where-Object { $_.Name -match $Rx } | ForEach-Object {
            if ($DryRun) { Write-PemfLog "[DRY] env (Makine): $($_.Name)" 'Yellow' }
            else { Remove-ItemProperty -Path $key -Name $_.Name -Force -ErrorAction SilentlyContinue; Write-PemfLog "env silindi: $($_.Name)" }
        }
}

function Remove-PemfRegistry($Registry, [string]$Scope, [switch]$DryRun) {
    foreach ($r in $Registry) {
        if (-not (Test-PemfScope $r.Owner $Scope)) { continue }
        if (Test-Path -LiteralPath $r.Path) {
            if ($DryRun) { Write-PemfLog "[DRY] registry: $($r.Path)" 'Yellow' }
            else {
                Remove-Item -LiteralPath $r.Path -Recurse -Force -ErrorAction SilentlyContinue
                [void](Assert-PemfRemoved -Path $r.Path -Tag 'registry')
            }
        }
    }
}

function Remove-PemfPaths($Footprint, [string]$Scope, [switch]$IncludePatientData, [switch]$DryRun) {
    $profileRoots = Get-PemfProfileRoots
    # Non-KVKK ÖNCE: alt-dizin (ör. PEMF_GUI\ai_models) üst KVKK-dizininden önce temizlensin.
    $ordered = @($Footprint.Paths | Sort-Object { [int][bool]$_.Kvkk })
    foreach ($item in $ordered) {
        if (-not (Test-PemfScope $item.Owner $Scope)) { continue }
        if ($item.Kvkk -and -not $IncludePatientData) { continue }   # KVKK: koru
        $targets = if ($item.Kind -eq 'Abs') { @($item.Path) }
        else { $profileRoots | ForEach-Object { Join-Path $_ $item.Path } }
        foreach ($t in $targets) {
            if (Test-Path -LiteralPath $t -ErrorAction SilentlyContinue) {
                $tag = if ($item.Kvkk) { 'HASTA-VERİSİ' } else { 'veri' }
                if ($DryRun) { Write-PemfLog "[DRY] silinecek ($tag): $t" 'Yellow' }
                else {
                    Remove-Item -LiteralPath $t -Recurse -Force -ErrorAction SilentlyContinue
                    [void](Assert-PemfRemoved -Path $t -Tag $tag)
                }
            }
        }
    }
}

# NOT: $TargetNames = Windows Credential Manager HEDEF ADLARI (ör. 'PEMF_GUI') — PAROLA DEĞİL,
# yalnız cmdkey /delete için tanımlayıcı. (İsim 'Cred' içerince analyzer parola sanıyordu.)
#
# ⚠️ DENETİM 2026-09-06 — KİMLİK SİLME SONUCU DOĞRULANMIYORDU (KVKK YANLIŞ-GÜVENCE).
# Eski hâl: `cmdkey /delete:$c *>$null; Write-PemfLog "kimlik silindi"` KOŞULSUZ. cmdkey hedef
# yoksa exit 1 döner ("Eleman bulunamadı" — ölçüldü), $LASTEXITCODE hiç okunmuyor, $PemfFailed'e
# dokunulmuyordu. Footprint'teki ad da yanlıştı ('fernet_key' ≠ runtime'ın yazdığı
# 'patient_fernet_key') → HER koşu, hiçbir şey silmeden "kimlik silindi (KVKK)" raporluyordu.
# Artık: exit 0 → silindi; "bulunamadı" → yoktu (başarısızlık DEĞİL — eski-kurulum adları için
# normal); başka her şey (erişim engeli vb.) → $PemfFailed'e eklenir + kırmızı satır → rapor
# "tam temizlik" DEMEZ.
# KAPSAM SINIRI: cmdkey YALNIZ çağıran kullanıcının ($env:USERNAME) kasasını görür. Backend servisi
# LocalSystem olarak çalışır ve python-keyring KENDİ (SYSTEM) kasasına yazar — o kasa buradan
# ERİŞİLEMEZ. 2026-09-06'ya kadar depoda onu temizleyen başka adım da YOKTU; artık orkestratördeki
# bir SONRAKİ adım (Remove-PemfSystemCredentials: tek-seferlik /RU SYSTEM görevi) o kasayı temizler.
# Fonksiyon bu sınırı çağrı başına bir kez Sarı NOT olarak basar (rapor okuyan bilsin).
function Remove-PemfCredentials([string[]]$TargetNames, [switch]$DryRun) {
    Write-PemfLog "NOT: cmdkey yalnız '$env:USERNAME' kasasını görür; backend servisinin LocalSystem (SYSTEM) kasası bu adımın DIŞINDA — servis kasası bir SONRAKİ adımda (Remove-PemfSystemCredentials, SYSTEM görevi) temizlenir" 'Yellow'
    foreach ($c in $TargetNames) {
        if ($DryRun) { Write-PemfLog "[DRY] kimlik (KVKK): $c" 'Yellow'; continue }
        # cmdkey HİÇ BAŞLATILAMAZSA (PATH bozuk) `2>&1` hatayı $out'a alır ama $LASTEXITCODE önceki
        # değerinde kalır; önceki yerel komut 0 döndürmüşse sahte "silindi" olur. Önce 1'e çek.
        $global:LASTEXITCODE = 1
        $out = (& cmdkey /delete:$c 2>&1) -join ' '
        if ($LASTEXITCODE -eq 0) {
            Write-PemfLog "kimlik silindi (KVKK): $c"
        } elseif ($out -match 'bulunamad|not found|cannot find|does not exist') {
            Write-PemfLog "kimlik yoktu ($env:USERNAME kasası): $c"
        } else {
            $script:PemfFailed += "kimlik: $c"
            Write-PemfLog "KİMLİK SİLİNEMEDİ (KVKK): $c — $out — yönetici olarak 'cmdkey /delete:$c' ile elle silin" 'Red'
        }
    }
}

# ⚠️ DENETİM 2026-09-06 — SYSTEM (LocalSystem) KİMLİK KASASI TEMİZLENMİYORDU (KVKK EKSİK TEMİZLİK).
# Backend servisi (PemfBackend, NSSM) LocalSystem olarak koşar; keyring.set_password ile YAZANLAR:
# database/sqlcipher_util.py ("PEMF_GUI","sqlcipher_key") + pemf_gui/config.py ("PEMF_GUI","patient_fernet_key")
# — python-keyring'in Windows arka ucu bunları SYSTEM HESABININ Credential Manager kasasına
# "<ad>@PEMF_GUI" hedefiyle koyar (okuyan: utils/secrets_manager.py; footprint listesi ikisini de kapsar).
# Remove-PemfCredentials yükseltilmiş YÖNETİCİ olarak cmdkey çalıştırır → yalnız yöneticinin kasasını
# görür; SYSTEM kasasındaki DB/fernet anahtarları "tam temizlik"ten SAĞ ÇIKIYORDU ve depoda bunu
# temizleyen başka adım yoktu (Sarı NOT ile operatöre bırakılıyordu).
# ÇÖZÜM (psexec'siz, kendine-yeten): tek-seferlik zamanlanmış görev (/RU SYSTEM) SYSTEM bağlamında
# küçük bir betik (kasa.ps1) koşturur; betik cmdkey /delete yapar, SONRA her hedefi cmdkey /list:<hedef>
# ile DOĞRULAR ve sonucu sonuc.txt'ye yazar; ana betik sonucu okur, loglar ve görev + çalışma dizinini
# HER DURUMDA (finally) siler. Çalışma dizini PEMF_System ALTINDA DEĞİLDİR (6. adım onu siler) ve
# %TEMP% DEĞİLDİR (SYSTEM'in TEMP'i farklıdır) → $env:ProgramData\PEMF_KimlikTemizlik_<guid>.
# ÖLÇÜM 2026-09-06 (bu makine, pwsh 7.6 + Windows PowerShell 5.1):
#   • schtasks /SC ONCE /ST 00:00 "geçmiş saat" UYARISI basar ama exit 0 döner; /Run exit 0; /Delete exit 0.
#   • /RL HIGHEST ve /RU SYSTEM yükseltilmiş oturum ister ("Erişim engellendi", exit 1). Çağıranlar
#     zaten yükseltilmiş: pemf_uninstall_all.ps1:20 IsInRole kapısı, setup_services.ps1 (Inno, admin).
#   • cmdkey /list:<hedef>: hedef VARSA "Target: <hedef>" satırı basılır (başlıkla birlikte ad 2 KEZ
#     geçer); YOKSA "* NONE *" (ad yalnız başlıkta, 1 kez). Sayım dil-bağımsızdır. TÜM kasa
#     grep'lenmez: geliştirici makinesinde başka PEMF kayıtları meşru olarak durabilir.
#   • PS 5.1 gömülü çift-tırnaklı argümanı bozuk aktarır → /TR içinde yol TIRNAKSIZ verilir (yol
#     boşluksuzdur; boşluklu kökte 8.3 kısa ad denenir; o da boşlukluysa /Create'e HİÇ gidilmez —
#     bilinen-bozuk komut sessizce gönderilmez, dürüst başarısızlık + elle komut).
#   • schtasks /Create'in "/ST geçmiş saat" UYARISI STDERR'e düşer; Windows PowerShell 5.1'de
#     $ErrorActionPreference='Stop' altında `2>&1` bunu FIRLATIR (mutlu yolda!) → fonksiyon EAP'yi
#     yerel olarak 'Continue' yapar (çağıranın tercihi ne olursa olsun; her rc ayrıca okunur).
#   • ProgramData'da yeni klasör 'BUILTIN\Users:(CI)(WD,AD)' ACE'sini MİRAS ALIR → standart bir yerel
#     kullanıcı sonuc.txt'yi SYSTEM görevinden ÖNCE sahte içerikle yaratabilirdi (sahte KVKK kanıtı).
#     Bu yüzden kasa.ps1 yazılmadan önce miras kesilir; yalnız SYSTEM + Administrators + çağıran
#     (zaten yönetici; SID'le, ad yerelleşir) kalır.
$script:PemfSystemKasaZamanAsimiSn = 60   # SYSTEM görevinin sonuc.txt'ye BITTI yazması için üst sınır (testler 2 yapar)
$script:PemfSchtasksYolu = Join-Path $env:SystemRoot 'System32\schtasks.exe'   # PATH hijyeni: tam yol (testler stub'a çevirir)
$script:PemfKimlikTemizlikKoku = $env:ProgramData   # çalışma dizini kökü (testler boşluklu/yazılamaz köke çevirir)

# Yükseltilmiş (yönetici) oturum mu? Ayrı fonksiyon: testler gölgeler.
function Test-PemfYukseltilmis {
    return ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

# SYSTEM kasasındaki hedef adlarını (KVKK) tek-seferlik /RU SYSTEM görevi ile siler ve DOĞRULAR.
function Remove-PemfSystemCredentials([string[]]$TargetNames, [switch]$DryRun) {
    # Fonksiyon-yerel: 5.1'de schtasks'ın stderr UYARISI Stop altında `2>&1` ile fırlar (ölçüm 2026-09-06);
    # kasa.ps1'deki disiplinle aynı. Her yerel komutun rc'si zaten ayrıca okunur.
    $ErrorActionPreference = 'Continue'
    if (-not $TargetNames -or @($TargetNames).Count -eq 0) { Write-PemfLog "SYSTEM kasası: hedef yok, atlandı" 'Yellow'; return }
    if ($env:OS -ne 'Windows_NT') { Write-PemfLog "SYSTEM kasası: Windows değil, atlandı" 'Yellow'; return }
    # Hedef adı doğrulama = betik-enjeksiyonu savunması (Rust batch üreticileriyle aynı disiplin):
    # geçersiz ad kasa.ps1'e ASLA gömülmez, başarısızlık sayılır. -DryRun'dan ÖNCE koşar ki önizleme
    # gerçek koşuda reddedilecek adı da göstersin (önizleme ile gerçek koşu aynı sonucu versin).
    # ⚠️ -cmatch ŞART (ölçüm 2026-09-06): -match büyük/küçük-duyarsızdır ve Windows PowerShell 5.1
    # tr-TR kültüründe 'I' → 'ı' (noktasız) katlanır; '@PEMF_GUI' içindeki I [a-z]'ye düşmez → HER
    # geçerli ad reddediliyordu (pwsh 7'de görünmez, üretim Inno=5.1'de görünür).
    $gecerli = @()
    foreach ($t in $TargetNames) {
        if ($t -cmatch '^[A-Za-z0-9_@.\-]+$') { $gecerli += $t }
        else {
            $script:PemfFailed += "SYSTEM kimlik (geçersiz ad): $t"
            Write-PemfLog "SYSTEM kasası: GEÇERSİZ hedef adı atlandı (yalnız harf/rakam/_ @ . - kabul edilir): '$t' — pemf_footprint.ps1 Credentials listesini düzeltin" 'Red'
        }
    }
    if ($DryRun) {
        if ($gecerli.Count -gt 0) { Write-PemfLog "[DRY] SYSTEM kasası (KVKK): $($gecerli -join ', ')" 'Yellow' }
        return
    }
    if (-not (Test-PemfYukseltilmis)) {
        $script:PemfFailed += 'SYSTEM kimlik kasası (yükseltilmiş oturum gerekir)'
        Write-PemfLog "SYSTEM KASASI TEMİZLENEMEDİ (KVKK): bu oturum yükseltilmiş değil, /RU SYSTEM görevi oluşturulamaz — kaldırıcıyı yükseltilmiş (yönetici) PowerShell'de yeniden çalıştırın" 'Red'
        return
    }
    if ($gecerli.Count -eq 0) { Write-PemfLog "SYSTEM kasası: geçerli hedef kalmadı, görev oluşturulmadı" 'Red'; return }

    # Elle-komut metni: kalan adlarla yeniden üretilebilsin diye tek yerde.
    $elleMetin = { param($adlar) "yükseltilmiş PowerShell'de elle çalıştırın (her ad için): schtasks /Create /TN PEMF-KimlikTemizle /RU SYSTEM /SC ONCE /ST 00:00 /F /RL HIGHEST /TR `"cmd /c cmdkey /delete:<ad>`" ; schtasks /Run /TN PEMF-KimlikTemizle ; schtasks /Delete /TN PEMF-KimlikTemizle /F — adlar: $($adlar -join ', ')" }
    $elle = & $elleMetin $gecerli
    $kok = $script:PemfKimlikTemizlikKoku
    if (-not $kok) { $kok = $env:ProgramData }
    if (-not $kok) {
        # Yönetici oturumunda hep tanımlıdır; tanımsızsa Join-Path $null döner ve SYSTEM'e '-File ' (boş)
        # komutlu görev yaratılıp 60 sn beklenirdi — kök neden log'a düşmezdi.
        $script:PemfFailed += 'SYSTEM kimlik kasası (ProgramData tanımsız)'
        Write-PemfLog "SYSTEM KASASI TEMİZLENEMEDİ (KVKK): `$env:ProgramData tanımsız, çalışma dizini kurulamaz — $elle" 'Red'
        return
    }
    $kimlikNo = [guid]::NewGuid().ToString('N')
    $gorev = "PEMF-KimlikTemizle-$kimlikNo"
    $calisma = Join-Path $kok ("PEMF_KimlikTemizlik_" + $kimlikNo)
    $kasaPs1 = Join-Path $calisma 'kasa.ps1'
    $sonucYolu = Join-Path $calisma 'sonuc.txt'
    $schtasks = $script:PemfSchtasksYolu
    if (-not $schtasks) { $schtasks = Join-Path $env:SystemRoot 'System32\schtasks.exe' }
    $psExe = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'   # PATH hijyeni: SYSTEM görevi de tam yol
    $icacls = Join-Path $env:SystemRoot 'System32\icacls.exe'
    $zamanAsimi = $script:PemfSystemKasaZamanAsimiSn
    if (-not $zamanAsimi) { $zamanAsimi = 60 }
    $gorevOlustu = $false
    try {
        # HAZIRLIK — her adım doğrulanır: dizin yoksa / ACL kesilemezse / kasa.ps1 yazılamazsa /Create'e
        # HİÇ gidilmez (aksi hâlde SYSTEM'e var olmayan betiği işaret eden görev yaratılıp 60 sn beklenir
        # ve zaman aşımı 'Görev Zamanlayıcı kapalı' diye YANLIŞ teşhis edilirdi).
        try {
            New-Item -ItemType Directory -Path $calisma -Force -ErrorAction Stop | Out-Null
            if (-not (Test-Path -LiteralPath $calisma -PathType Container)) { throw "çalışma dizini oluşturulamadı: $calisma (kök '$kok' yazılabilir değil / disk)" }
            # ACL: mirası kes; SYSTEM (S-1-5-18) + Administrators (S-1-5-32-544) + çağıran hesap (zaten
            # yönetici) — BUILTIN\Users mirası kalırsa sonuc.txt SYSTEM'den ÖNCE sahte yaratılabilir.
            $sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
            $global:LASTEXITCODE = 1
            $aclOut = ((& $icacls $calisma /inheritance:r /grant:r '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' "*${sid}:(OI)(CI)F" 2>&1) -join ' ') -replace 'System\.Management\.Automation\.RemoteException', ''
            if ($LASTEXITCODE -ne 0) { throw "çalışma dizini kilitlenemedi (icacls rc=$LASTEXITCODE): $aclOut" }
            # SYSTEM tarafında koşacak betik — Windows PowerShell 5.1'de PARSE ETMELİ (sade sözdizimi).
            # Hedefler yukarıda doğrulandığından tek-tırnak içine güvenle gömülür. Her adım sonuc.txt'ye
            # yazar; try/catch HATA= yazar ki ana betik çökmüş bir betiği beklemesin. KALANLAR= satırı
            # hangi adların durduğunu söyler (operatör elle komutu yalnız onlar için koşturur).
            $hedefListe = @($gecerli | ForEach-Object { "'" + $_ + "'" }) -join ', '
            $sonucLit = "'" + ($sonucYolu -replace "'", "''") + "'"
            $satirlar = @(
                '$ErrorActionPreference = ''Continue''',
                ('$sonuc = ' + $sonucLit),
                ('$hedefler = @(' + $hedefListe + ')'),
                'try {',
                '    Set-Content -LiteralPath $sonuc -Value (''KIMLIK='' + [Security.Principal.WindowsIdentity]::GetCurrent().Name) -Encoding UTF8',
                '    foreach ($t in $hedefler) {',
                '        $global:LASTEXITCODE = 1',
                '        $o = (& cmdkey /delete:$t 2>&1) -join '' ''',
                '        Add-Content -LiteralPath $sonuc -Value ($t + ''='' + $LASTEXITCODE + ''|'' + $o) -Encoding UTF8',
                '    }',
                '    $kalan = 0',
                '    $kalanlar = @()',
                '    foreach ($t in $hedefler) {',
                '        $l = (& cmdkey /list:$t 2>&1) -join '' ''',
                '        if (([regex]::Matches($l, [regex]::Escape($t))).Count -ge 2) { $kalan = $kalan + 1; $kalanlar += $t }',
                '    }',
                '    Add-Content -LiteralPath $sonuc -Value (''KALANLAR='' + ($kalanlar -join '','')) -Encoding UTF8',
                '    Add-Content -LiteralPath $sonuc -Value (''KALAN='' + $kalan) -Encoding UTF8',
                '} catch {',
                '    Add-Content -LiteralPath $sonuc -Value (''HATA='' + $_.Exception.Message) -Encoding UTF8',
                '}',
                'Add-Content -LiteralPath $sonuc -Value ''BITTI'' -Encoding UTF8'
            )
            Set-Content -LiteralPath $kasaPs1 -Value ($satirlar -join "`r`n") -Encoding UTF8 -ErrorAction Stop
            if (-not (Test-Path -LiteralPath $kasaPs1)) { throw "kasa.ps1 yazılamadı: $kasaPs1 (ProgramData izni / disk)" }
        } catch {
            $script:PemfFailed += "SYSTEM kimlik kasası (hazırlık: $($_.Exception.Message))"
            Write-PemfLog "SYSTEM KASASI TEMİZLENEMEDİ (KVKK): çalışma dizini/betik hazırlanamadı, görev oluşturulmadı — $($_.Exception.Message) — $elle" 'Red'
            return
        }

        $tr = "$psExe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $kasaPs1"
        if ($kasaPs1 -match '\s') {
            $kisa = $null
            try { $kisa = (New-Object -ComObject Scripting.FileSystemObject).GetFile($kasaPs1).ShortPath } catch { $kisa = $null }
            if ($kisa -and $kisa -notmatch '\s') { $tr = "$psExe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $kisa" }
            else {
                # 8.3 adı yok (fsutil 8dot3name birimde kapalı): tırnaklı /TR 5.1'de bozuk aktarılır → görev
                # bozuk komutla oluşur, /Run 'başarılı', 60 sn sonra zaman aşımı. Bilinen-bozuk komutu GÖNDERME.
                $script:PemfFailed += 'SYSTEM kimlik kasası (çalışma dizini yolu boşluklu, 8.3 kısa ad yok)'
                Write-PemfLog "SYSTEM KASASI TEMİZLENEMEDİ (KVKK): çalışma dizini yolu boşluk içeriyor ve 8.3 kısa adı yok ('$kasaPs1') — /TR güvenle kurulamaz; boşluksuz bir ProgramData ile yeniden deneyin veya $elle" 'Red'
                return
            }
        }
        # schtasks HİÇ BAŞLATILAMAZSA $LASTEXITCODE eski değerinde kalır → önce 1'e çek (Remove-PemfCredentials'taki ders).
        $global:LASTEXITCODE = 1
        $out = ((& $schtasks /Create /TN $gorev /RU SYSTEM /SC ONCE /ST 00:00 /F /RL HIGHEST /TR $tr 2>&1) -join ' ') -replace 'System\.Management\.Automation\.RemoteException', ''
        if ($LASTEXITCODE -ne 0) {
            $script:PemfFailed += 'SYSTEM kimlik kasası (görev oluşturulamadı)'
            Write-PemfLog "SYSTEM KASASI TEMİZLENEMEDİ (KVKK): schtasks /Create başarısız (rc=$LASTEXITCODE): $out — $elle" 'Red'
            return
        }
        $gorevOlustu = $true
        $global:LASTEXITCODE = 1
        $out = ((& $schtasks /Run /TN $gorev 2>&1) -join ' ') -replace 'System\.Management\.Automation\.RemoteException', ''
        if ($LASTEXITCODE -ne 0) {
            $script:PemfFailed += 'SYSTEM kimlik kasası (görev başlatılamadı)'
            Write-PemfLog "SYSTEM KASASI TEMİZLENEMEDİ (KVKK): schtasks /Run başarısız (rc=$LASTEXITCODE): $out — $elle" 'Red'
            return
        }
        # sonuc.txt'de BITTI (veya HATA=) görünene kadar 500 ms adımlarla bekle.
        $icerik = $null
        $son = (Get-Date).AddSeconds($zamanAsimi)
        while ((Get-Date) -lt $son) {
            if (Test-Path -LiteralPath $sonucYolu) {
                $okunan = Get-Content -LiteralPath $sonucYolu -Raw -ErrorAction SilentlyContinue
                if ($okunan -and ($okunan -match 'BITTI|HATA=')) { $icerik = $okunan; break }
            }
            Start-Sleep -Milliseconds 500
        }
        if (-not $icerik) {
            $script:PemfFailed += "SYSTEM kimlik kasası (görev $zamanAsimi sn içinde bitmedi)"
            Write-PemfLog "SYSTEM KASASI TEMİZLENEMEDİ (KVKK): SYSTEM görevi '$gorev' $zamanAsimi sn içinde sonuç yazmadı (Görev Zamanlayıcı servisi kapalı/engelli olabilir) — $elle" 'Red'
            $kismi = $null
            if (Test-Path -LiteralPath $sonucYolu) { $kismi = Get-Content -LiteralPath $sonucYolu -Raw -ErrorAction SilentlyContinue }
            if ($kismi) { Write-PemfLog "SYSTEM kasası kısmi sonuç (dizin silinmeden önce kopyalandı): $($kismi -replace '\r?\n', ' | ')" 'Yellow' }
            return
        }
        # Sonucu ayrıştır — yalnız GÖNDERİLEN hedefler sayılır.
        $silindi = 0; $yoktu = 0; $hata = 0; $kalan = -1; $kimlik = '?'; $kalanAdlar = @()
        foreach ($ln in ($icerik -split "`r?`n")) {
            $ln = "$ln".Trim()
            if (-not $ln -or $ln -eq 'BITTI') { continue }
            if ($ln.StartsWith('KIMLIK=')) { $kimlik = $ln.Substring(7); continue }
            if ($ln.StartsWith('KALANLAR=')) {
                # yalnız GÖNDERİLEN adlar (sonuc.txt SYSTEM yazar ama yine de yabancı satır atılır)
                $kalanAdlar = @(($ln.Substring(9) -split ',') | ForEach-Object { $_.Trim() } | Where-Object { $_ -and ($gecerli -contains $_) })
                continue
            }
            if ($ln.StartsWith('KALAN=')) {
                $kalan = ($ln.Substring(6) -as [int])
                if ($null -eq $kalan) { $kalan = -1 }
                continue
            }
            if ($ln.StartsWith('HATA=')) {
                $hata++
                $script:PemfFailed += "SYSTEM kimlik kasası (SYSTEM betiği hatası: $($ln.Substring(5)))"
                Write-PemfLog "SYSTEM KASASI TEMİZLENEMEDİ (KVKK): SYSTEM betiği hata verdi: $($ln.Substring(5)) — $elle" 'Red'
                continue
            }
            $i = $ln.IndexOf('=')
            if ($i -lt 1) { continue }
            $t = $ln.Substring(0, $i); $geri = $ln.Substring($i + 1)
            if ($gecerli -notcontains $t) { continue }
            $j = $geri.IndexOf('|')
            if ($j -lt 0) { continue }
            $rc = $geri.Substring(0, $j); $o = $geri.Substring($j + 1)
            if ($rc -eq '0') { $silindi++; Write-PemfLog "SYSTEM kasası: kimlik silindi (KVKK): $t" }
            elseif ($o -match 'bulunamad|not found|cannot find|does not exist') { $yoktu++; Write-PemfLog "SYSTEM kasası: kimlik yoktu: $t" }
            else {
                $hata++
                $script:PemfFailed += "SYSTEM kimlik: $t"
                Write-PemfLog "SYSTEM KASASI: KİMLİK SİLİNEMEDİ (KVKK): $t — $o — $elle" 'Red'
            }
        }
        Write-PemfLog "SYSTEM kasası: görev kimliği $kimlik"
        if ($kimlik -notmatch 'SYSTEM$') { Write-PemfLog "SYSTEM kasası: görev beklenen 'NT AUTHORITY\SYSTEM' yerine '$kimlik' olarak koştu — doğrulama o hesabın kasasına aittir" 'Yellow' }
        if ($kalan -gt 0) {
            # Elle komut yalnız DURAN adlarla (6 adın hepsini değil); KALANLAR satırı gelmediyse tüm liste.
            $elleKalan = if ($kalanAdlar.Count -gt 0) { & $elleMetin $kalanAdlar } else { $elle }
            $adMetni = if ($kalanAdlar.Count -gt 0) { " (" + ($kalanAdlar -join ', ') + ")" } else { '' }
            $script:PemfFailed += "SYSTEM kasası: $kalan kimlik hâlâ duruyor$adMetni"
            Write-PemfLog "SYSTEM KASASI EKSİK (KVKK): silme sonrası $kalan kimlik hâlâ SYSTEM kasasında DURUYOR$adMetni — $elleKalan" 'Red'
        } elseif ($kalan -lt 0 -and $hata -eq 0) {
            $script:PemfFailed += 'SYSTEM kasası: doğrulama (KALAN) yazılmadı'
            Write-PemfLog "SYSTEM KASASI DOĞRULANAMADI (KVKK): SYSTEM betiği KALAN satırı yazmadı — $elle" 'Red'
        }
        $renk = if ($hata -eq 0 -and $kalan -eq 0) { 'Green' } else { 'Red' }
        Write-PemfLog "SYSTEM kasası: $silindi silindi / $yoktu yoktu / $hata hata (kimlik: $kimlik)" $renk
    } finally {
        # HER DURUMDA: görev kalıntısı bırakma + çalışma dizinini sil (kasa.ps1 hedef adlarını içerir).
        if ($gorevOlustu) {
            $global:LASTEXITCODE = 1
            $out = ((& $schtasks /Delete /TN $gorev /F 2>&1) -join ' ') -replace 'System\.Management\.Automation\.RemoteException', ''
            if ($LASTEXITCODE -ne 0) {
                $script:PemfFailed += "SYSTEM görev kalıntısı: $gorev"
                Write-PemfLog "SYSTEM kasası: görev SİLİNEMEDİ: $gorev — $out — yükseltilmiş PowerShell'de 'schtasks /Delete /TN $gorev /F' çalıştırın" 'Red'
            }
        }
        if (Test-Path -LiteralPath $calisma) {
            Remove-Item -LiteralPath $calisma -Recurse -Force -ErrorAction SilentlyContinue
            if (Test-Path -LiteralPath $calisma) {
                $script:PemfFailed += $calisma
                Write-PemfLog "SİLİNEMEDİ (SYSTEM kasası çalışma dizini): $calisma — elle silin" 'Red'
            }
        }
    }
}

# ───────────────────────────── ORKESTRATÖR ─────────────────────────────
function Invoke-PemfTeardown {
    [CmdletBinding()]
    param(
        [ValidateSet('client', 'backend', 'gui', 'all')] [string]$Scope = 'all',
        [switch]$IncludePatientData,   # KVKK: hasta DB + şifreleme anahtarlarını da KALICI sil
        [switch]$DryRun                # hiçbir şey silme, yalnız logla (önizleme)
    )
    # DENETIM 2026-08-04 (P2): sayaç MODÜL yüklenirken bir kez sıfırlanıyordu, çağrı başına
    # DEĞİL. Dosya başlığındaki resmi kullanım dot-source + tekrar çağrıdır; operatör servisi
    # durdurup AYNI oturumda tekrar çalıştırdığında ilk turun başarısızlıkları taşınıyor ve
    # ZATEN SİLİNMİŞ yollar "SİLİNEMEDİ" diye raporlanıp fonksiyon $false dönüyordu.
    $script:PemfFailed = @()
    $fp = Get-PemfFootprint
    Write-PemfLog "TEARDOWN başladı — Scope=$Scope IncludePatientData=$IncludePatientData DryRun=$DryRun" 'Cyan'

    # 1. Süreç+servis (yalnız backend/all — client/gui'de NSSM servisi yok)
    if ($Scope -eq 'backend' -or $Scope -eq 'all') {
        if ($DryRun) { foreach ($s in $fp.Services) { if (Get-Service -Name $s -ErrorAction SilentlyContinue) { Write-PemfLog "[DRY] servis: $s" 'Yellow' } } }
        else { Stop-PemfProcessesAndServices -Services $fp.Services }
    }
    # 2. Görevler + hotspot wscript
    Remove-PemfTasks -Tasks $fp.Tasks -DryRun:$DryRun
    # 3. Firewall (wildcard)
    Remove-PemfFirewall -Rx $fp.FirewallRx -DryRun:$DryRun
    # 4. Makine ortam değişkenleri PEMF_*
    Remove-PemfEnv -Rx $fp.EnvRx -DryRun:$DryRun
    # 5. Registry (owner-filtreli)
    Remove-PemfRegistry -Registry $fp.Registry -Scope $Scope -DryRun:$DryRun
    # 6. Yollar (non-KVKK her zaman; KVKK yalnız -IncludePatientData; owner-filtreli)
    Remove-PemfPaths -Footprint $fp -Scope $Scope -IncludePatientData:$IncludePatientData -DryRun:$DryRun
    # 7. Kimlikler (KVKK — yalnız -IncludePatientData)
    if ($IncludePatientData) { Remove-PemfCredentials -TargetNames $fp.Credentials -DryRun:$DryRun }
    # 8. SYSTEM (LocalSystem servis) kasası — KVKK; tek-seferlik /RU SYSTEM görevi (denetim 2026-09-06).
    #    7. adımdan SONRA ve yollardan (6) sonra: çalışma dizini ProgramData\PEMF_KimlikTemizlik_* olduğundan
    #    6. adımın PEMF_System silmesinden etkilenmez; görev+dizin fonksiyon içinde her durumda temizlenir.
    if ($IncludePatientData) { Remove-PemfSystemCredentials -TargetNames $fp.Credentials -DryRun:$DryRun }

    # ⚠️ Rapor GERÇEĞE dayanmalı: tek bir silme bile başarısızsa "tam temizlik" DENMEZ.
    if ($script:PemfFailed.Count -gt 0) {
        Write-PemfLog "TEARDOWN EKSİK — $($script:PemfFailed.Count) öğe SİLİNEMEDİ:" 'Red'
        foreach ($f in $script:PemfFailed) { Write-PemfLog "   kalan: $f" 'Red' }
        if ($IncludePatientData) {
            Write-PemfLog "HASTA VERİSİ TAM SİLİNMEDİ — yukarıdaki yollar diskte DURUYOR. Backend/servisleri durdurup yeniden çalıştırın." 'Red'
        }
        Write-PemfLog "TEARDOWN bitti — EKSİK (bkz. yukarıdaki liste)" 'Red'
        return $false
    }
    # DENETIM 2026-08-04 (P2): -DryRun'da da "HASTA VERİSİ DE SİLİNDİ (tam temizlik)" yazıyordu.
    # Bu log dosyası, dosya başlığında KVKK "tüm hasta verisini sildim" KANITI olarak tanımlı;
    # önizleme koşusunun raporu silme kanıtı gibi okunurdu.
    $policy = if ($DryRun) {
        'ÖNİZLEME — HİÇBİR ŞEY SİLİNMEDİ (DryRun)'
    } elseif ($IncludePatientData) {
        'HASTA VERİSİ DE SİLİNDİ (tam temizlik)'
    } else {
        'HASTA VERİSİ KORUNDU (KVKK; -IncludePatientData ile silinir)'
    }
    Write-PemfLog "TEARDOWN bitti — $policy" 'Green'
    return $true
}
