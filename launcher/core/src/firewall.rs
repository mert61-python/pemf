// Author: mertaygn, cglrgrkn
//! WINDOWS GÜVENLİK DUVARI — mobil uygulama kliniğe bağlanabilsin (2026-08-09 denetimi, Tier 1).
//!
//! ARIZA
//! -----
//! Backend `0.0.0.0:8000`'i dinliyor ve keşif UDP 5051 kullanıyor, ama launcher yolunda gelen
//! kurulumda inbound güvenlik duvarı kuralı HİÇ OLUŞTURULMUYOR:
//!   * client kurulumu `installMode=currentUser` → NSIS YÜKSELTİLMİŞ DEĞİL, kural ekleyemez,
//!   * kuralları oluşturan tek yer `scripts/install_backend_service.ps1` — o ise ESKİ,
//!     servis-tabanlı (Inno) dağıtım yolu; launcher onu hiç çalıştırmaz.
//!
//! Sonuç: yayınlanan mobil APK klinik WiFi'sinde cihaza HİÇ bağlanamaz ve sebebi hiçbir yerde
//! yazmaz. Veteriner "uygulama bozuk" der; günlüklerde de bir hata yoktur, çünkü paket
//! backend'e HİÇ ULAŞMAZ. (Windows bazen ilk dinlemede bir izin penceresi gösterir; kullanıcı
//! yönetici değilse ya da pencereyi kapattıysa engel KALICIDIR.)
//!
//! ÇÖZÜM
//! -----
//! Kural ekleme YÖNETİCİ ister; launcher bilerek yükseltilmemiş çalışır (sessiz oto-güncelleme
//! UAC'siz olsun diye). Bu yüzden: DURUMU TESPİT ET, kullanıcıya SEBEBİ SÖYLE ve tek tıkla
//! yükseltilmiş düzeltmeyi çalıştır.
//!
//! ⚠️ FAIL-OPEN: durum okunamıyorsa "kural var" sayılır. Yanlış bir "bağlantı engelli" uyarısı,
//! çalışan bir kurulumda kullanıcıyı gereksiz UAC istemine iter ve uyarı körlüğü yaratır.

use std::path::Path;

/// Launcher çocuğunun GERÇEKTEN dinlediği API portu — güvenlik duvarı kuralının portu için TEK KAYNAK (D5 I-1).
///
/// ⚠️ Eskiden kural SABİT 8000'i (`API_PORT`) açıyordu; oysa çocuk `find_free_port(DEFAULT_PORT, 50)` ile 8000 doluysa
/// 8001+'ya kayar (`flow::start_backend`) ve keşif yanıtı mobil istemciye O portu bildirir → kural kapsamaz, LAN'dan
/// (mobil / web, ACİL DURDUR dahil) bağlantı SESSİZCE düşerdi. Port, launcher'ın çocuk hazır olunca yazdığı
/// `backend.port`'tan (`on_backend_ready`) okunur; yoksa / bozuksa `install::DEFAULT_PORT`.
pub fn api_portu(install_root: &Path) -> u16 {
    crate::backend::read_backend_port(install_root).unwrap_or(crate::install::DEFAULT_PORT)
}

/// mDNS/UDP keşif portu — mobil uygulama cihazı bununla bulur.
pub const DISCOVERY_PORT: u16 = 5051;

/// Kural adları — Y204 · S-D5.12 (sahip): launcher'ınki servis kurulumundan (`install_backend_service.ps1` / `setup_services.ps1`,
/// `ESKI_KURAL_*`) AYRI. Aynı adı paylaşınca iki yol birbirinin kuralını ADLA siliyordu (servis betikleri İG-9.5 "taşınmış kurulum"
/// kuralıyla launcher'ınkini; launcher kaldırması servisinkini — SON-A1.53). D5 I-1 sürer: kural İÇERİK + PROGRAMLA ölçülür, başka
/// programın kuralı sayılmaz / silinmez, aynı exe için ikinci kural eklenmez.
pub const KURAL_API: &str = "PEMF Backend API (Launcher)";
pub const KURAL_KESIF: &str = "PEMF UDP Discovery (Launcher)";
/// 1.9.51 öncesi launcher'ın (ve bugün servis kurulumunun) adları. Launcher yalnız PROGRAMI kendi exe'si olan eski adlı kuralı kendisininki
/// sayar: durumda geçerlidir (güncelleme sonrası gereksiz uyarı yok), "İzin ver"de yeni adlı kurallar KURULDUKTAN sonra taşınır (silinir),
/// kaldırmada silinir. Başka programın (servis kurulumu) eski adlı kuralına DOKUNULMAZ.
pub const ESKI_KURAL_API: &str = "PEMF Backend API";
pub const ESKI_KURAL_KESIF: &str = "PEMF UDP Discovery";

/// SAHİP 12 Kasım 2026 (A · #22): PEMF'in KENDİ broker'ı (`<backend dizini>\_internal\bin\mosquitto\mosquitto.exe`) için program
/// kapsamlı gelen izin (Windows'un kendi "İzin ver"inin aynısı) — standart hesapta Windows bunu onaylatamayıp Block yazıyordu.
pub const KURAL_BROKER: &str = "PEMF MQTT Broker (Launcher)";

/// SAHİP 12 Kasım 2026 (A · #22, Y209 · S-D5.13'ün yerine): `$p` (bu kurulumun backend'i) ve PEMF'in KENDİ broker'ı için Windows'un
/// ETKİN, GELEN Block kurallarını KALDIRIR (bizim adlı kurallarımız hariç; başka programa, devre dışı Block'a, Allow'a DOKUNMAZ); broker
/// diskteyse ve izni yoksa program kapsamlı izin kurar. ÇIKMAZ; kurulamayan broker izni `$kurulamadi`yı artırır. Kaldırılamayan Block
/// (grup ilkesi / yetki) çağıranın `$engel` denetiminde kalır → kod 4 ("kaldırın").
fn engel_kaldir_ve_broker_izni() -> String {
    format!(
        "$mq = [IO.Path]::Combine([IO.Path]::GetDirectoryName($p), '_internal\\bin\\mosquitto\\mosquitto.exe'); \
         foreach ($pp in @($p, $mq)) {{ \
           foreach ($x in @(Get-NetFirewallApplicationFilter -ErrorAction SilentlyContinue | Where-Object {{ $_.Program -and ($_.Program -ieq $pp) }})) {{ \
             foreach ($rr in @($x | Get-NetFirewallRule -ErrorAction SilentlyContinue)) {{ \
               if ($rr.Direction -eq 'Inbound' -and $rr.Enabled -eq 'True' -and $rr.Action -eq 'Block' -and \
                   @('{api}', '{kesif}', '{eski_api}', '{eski_kesif}', '{broker}') -notcontains $rr.DisplayName) {{ \
                 try {{ $rr | Remove-NetFirewallRule -ErrorAction Stop }} catch {{ }} }} }} }} }}; \
         if ([IO.File]::Exists($mq)) {{ \
           $mqIzin = 0; \
           foreach ($x in @(Get-NetFirewallApplicationFilter -ErrorAction SilentlyContinue | Where-Object {{ $_.Program -and ($_.Program -ieq $mq) }})) {{ \
             foreach ($rr in @($x | Get-NetFirewallRule -ErrorAction SilentlyContinue)) {{ \
               if ($rr.Direction -eq 'Inbound' -and $rr.Enabled -eq 'True' -and $rr.Action -eq 'Allow') {{ $mqIzin++ }} }} }}; \
           if ($mqIzin -eq 0) {{ try {{ New-NetFirewallRule -DisplayName '{broker}' -Direction Inbound -Program $mq -Action Allow \
             -Protocol TCP -Profile Any -ErrorAction Stop | Out-Null }} catch {{ $kurulamadi++ }} }} }}; ",
        api = KURAL_API,
        kesif = KURAL_KESIF,
        eski_api = ESKI_KURAL_API,
        eski_kesif = ESKI_KURAL_KESIF,
        broker = KURAL_BROKER,
    )
}

/// #22 (sahip 12 Kasım: "kullanıcı etkileşimini azalt"): paylaşım yönetici adımının (`paylasim::kurma_betigi`) güvenlik duvarı
/// ÖN-İZİN parçası — `$p` (hesabın backend'i) verilince adlı izinleri (API + keşif) kurar, Windows Block'unu kaldırır, broker iznini
/// kurar. ÇIKMAZ (paylaşımın sonucu bozulmaz); her adım en iyi çaba.
pub fn on_izin_parcasi(api_port: u16) -> String {
    format!(
        "{islevler}$kurulamadi = 0; \
         foreach ($k in @(@('{api}', 'TCP', {tcp}), @('{kesif}', 'UDP', {udp}))) {{ \
           $uyan = @(Get-NetFirewallRule -DisplayName $k[0] -ErrorAction SilentlyContinue | Where-Object {{ $_ -and (PemfKuralUyar $_ $k[1] $k[2]) }}).Count; \
           if ($uyan -eq 0) {{ try {{ New-NetFirewallRule -DisplayName $k[0] -Direction Inbound -Program $p -Action Allow \
             -Protocol $k[1] -LocalPort $k[2] -Profile Any -ErrorAction Stop | Out-Null }} catch {{ }} }} }}; \
         {engel}",
        islevler = ICERIK_ISLEVLERI,
        api = KURAL_API,
        kesif = KURAL_KESIF,
        tcp = api_port,
        udp = DISCOVERY_PORT,
        engel = engel_kaldir_ve_broker_izni(),
    )
}

/// Adlı kural İÇERİKLE doğrulanır (D5 I-1 · S-4BI.5; `setup_services.ps1` İG-9.5 / 4B-3.5 ölçütü): aynı adlı ama devre dışı /
/// Block / giden / yanlış protokol / yanlış port / dar profil / BAŞKA programın kuralı "var" SAYILMAZ. `$p` boşsa (exe
/// bilinmiyor) program denetlenmez. `PemfKuralBizim`: kural BU backend exe'sinin mi — başka programın aynı adlı kuralı (eski
/// servis kurulumu `install_backend_service.ps1` / `setup_services.ps1` AYNI adları kullanır) SİLİNMEZ, yalnız sayılmaz.
const ICERIK_ISLEVLERI: &str = r##"function PemfKuralUyar($r, $proto, $port) { $pf = $r | Get-NetFirewallPortFilter -ErrorAction SilentlyContinue; $af = $r | Get-NetFirewallApplicationFilter -ErrorAction SilentlyContinue; [bool]($pf -and $af -and "$($pf.Protocol)" -eq $proto -and "$($pf.LocalPort)" -eq "$port" -and (-not $p -or "$($af.Program)" -ieq $p) -and "$($r.Enabled)" -eq 'True' -and "$($r.Action)" -eq 'Allow' -and "$($r.Direction)" -eq 'Inbound' -and "$($r.Profile)" -eq 'Any') }; function PemfKuralBizim($r) { $af = $r | Get-NetFirewallApplicationFilter -ErrorAction SilentlyContinue; [bool]($p -and $af -and "$($af.Program)" -ieq $p) }; "##;

/// Windows'un KENDİ izni (program kapsamlı kural) API portunu kapsıyor mu: protokol TCP / Any ve yerel port Any, tam port ya da
/// onu içeren aralık (D5 I-1). Kendi 8000'lik kuralımız ya da yalnız UDP izni çocuğun 8001'ini AÇMAZ.
const PORT_KAPSAMI: &str = r##"function PemfPortuKapsar($r, $port) { $pf = $r | Get-NetFirewallPortFilter -ErrorAction SilentlyContinue; if (-not $pf -or @('TCP', 'Any') -notcontains "$($pf.Protocol)") { return $false }; foreach ($lp in @($pf.LocalPort)) { if ("$lp" -eq 'Any' -or "$lp" -eq "$port") { return $true }; if ("$lp" -match '^(\d+)-(\d+)$' -and [int]$Matches[1] -le $port -and $port -le [int]$Matches[2]) { return $true } }; return $false }; "##;

/// Güvenlik duvarı durumu.
///
/// ⚠️ ÜÇ DURUM, İKİ DEĞİL (2026-08-11). Eskiden "kural yok" ile "açıkça engellenmiş" AYNI
/// sayılıyordu ve uyarı her açılışta, backend daha bir kez bile dinlemeden gösteriliyordu.
/// Oysa Windows, program ilk kez dinlediğinde KENDİ izin penceresini gösterir ve kullanıcı
/// "İzin ver" derse iş biter. Yeni kurulumda "kural yok" NORMALDİR — hata değil.
/// İkisini ayırmak, kullanıcıyı işletim sisteminin zaten halledeceği bir şey için yönetici
/// istemine itmeyi bitirir.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Durum {
    /// İzin var (bizim kuralımız ya da Windows'un kendi izni) — ya da okunamadı (fail-open).
    Acik,
    /// Henüz kural YOK. Backend hiç dinlemediyse bu NORMALDİR; Windows kendi penceresini
    /// gösterecektir. Ancak backend çalıştıktan SONRA hâlâ yoksa mobil bağlantı kurulamaz.
    KuralYok,
    /// Açıkça ENGELLENMİŞ (etkin Block kuralı). Kullanıcı Windows penceresinde "İptal" demiş
    /// ya da politika engelliyor. Bu engel KALICIdır ve yalnız yükseltilmiş düzeltmeyle açılır.
    Engelli,
    /// Bu platformda kontrol anlamsız (Windows dışı).
    Gereksiz,
}

/// PowerShell dize sabiti için kaçış — `'` iki katına çıkarılır.
///
/// ⚠️ Yol KULLANICI-ETKİLİ olabilir (kurulum dizini). Kaçış yapılmazsa tek tırnak kapatılıp
/// komut enjekte edilebilirdi ve bu komut YÜKSELTİLMİŞ çalışıyor.
/// ⚠️ D3 T-g (ÖLÇÜLDÜ, 2026-10-25 — PowerShell 5.1 `PSParser::Tokenize`): PowerShell `‘ ’ ‚ ‛` (U+2018–U+201B) karakterlerini
/// de TEK TIRNAK sayar; yalnız ASCII `'` ikilenince `C:\Users\a’; Write-Output X; ’` ayrı bir KOMUT oluyordu. Kurulum kökü
/// `USERPROFILE`'dan (kullanıcı etkili) gelir → beşi de ikilenir (aynı karakterin ikilisi, dizede o karakterin kendisidir).
pub(crate) fn ps_kacis(s: &str) -> String {
    let mut o = String::with_capacity(s.len() + 2);
    for c in s.chars() {
        if matches!(c, '\'' | '\u{2018}' | '\u{2019}' | '\u{201A}' | '\u{201B}') {
            o.push(c);
        }
        o.push(c);
    }
    o
}

/// Kuralları ekleyen PowerShell betiği (YÜKSELTİLMİŞ çalıştırılmalı).
///
/// İçeriği uyan kural varsa yeniden eklemez (idempotent) — klinikte eski servis kurulumu da olabilir.
/// D5 I-1: kural ADIYLA değil İÇERİKLE bulunur (`ICERIK_ISLEVLERI`) ve API portu çocuğun GERÇEK portudur (`api_portu`).
/// BU exe'nin uymayan aynı adlı kuralı silinip doğrusu kurulur (çift kural yok); silinemezse doğrusu yine kurulur.
/// Başka programın aynı adlı kuralına (servis kurulumu) DOKUNULMAZ. Uzak adres verilmez (A-01 kapsamı DEĞİŞMEDİ).
///
/// D5 J-3: sonuç ÇIKIŞ KODUYLA söylenir (`KOD_*`; okuyan `main.rs` `ps_yukselterek_kos_kodlu`). Eskiden `New-NetFirewallRule`
/// düşünce betik ilk hatada kesiliyor (ikinci kural hiç denenmiyordu), bozuk kuralın silinemeyişi `SilentlyContinue` ile
/// YUTULUYORDU; çağıran zaten kodu okumadığından arayüz her durumda "tamam" deyip uyarıyı kapatıyordu. Artık iki kural da denenir;
/// kurulamayan kural → `KOD_KURAL_KURULAMADI`, silinemeyen bozuk kural (doğrusu yine kurulur) → `KOD_BOZUK_KURAL_SILINEMEDI`.
pub fn ekleme_betigi(backend_exe: &Path, api_port: u16) -> String {
    let p = ps_kacis(&backend_exe.to_string_lossy());
    format!(
        "$ErrorActionPreference='Stop'; $kurulamadi = 0; $silinemedi = 0; \
         $p='{p}'; {islevler}\
         foreach ($k in @(@('{api}', 'TCP', {tcp}), @('{kesif}', 'UDP', {udp}))) {{ \
           $uyan = 0; \
           foreach ($r in @(Get-NetFirewallRule -DisplayName $k[0] -ErrorAction SilentlyContinue | Where-Object {{ $_ }})) {{ \
             if (PemfKuralUyar $r $k[1] $k[2]) {{ $uyan++ }} \
             elseif (PemfKuralBizim $r) {{ try {{ $r | Remove-NetFirewallRule -ErrorAction Stop }} catch {{ $silinemedi++ }} }} }}; \
           if ($uyan -eq 0) {{ \
             try {{ New-NetFirewallRule -DisplayName $k[0] -Direction Inbound -Program $p \
               -Action Allow -Protocol $k[1] -LocalPort $k[2] -Profile Any -ErrorAction Stop | Out-Null }} \
             catch {{ $kurulamadi++ }} }} }}; \
         if ($kurulamadi -eq 0) {{ foreach ($eski in @('{eski_api}', '{eski_kesif}')) {{ \
           foreach ($r in @(Get-NetFirewallRule -DisplayName $eski -ErrorAction SilentlyContinue | Where-Object {{ $_ }})) {{ \
             if (PemfKuralBizim $r) {{ try {{ $r | Remove-NetFirewallRule -ErrorAction Stop }} catch {{ $silinemedi++ }} }} }} }} }}; \
         {engel_kaldir}$engel = 0; \
         try {{ foreach ($x in @(Get-NetFirewallApplicationFilter -ErrorAction SilentlyContinue | \
                  Where-Object {{ $_.Program -and ($_.Program -ieq $p) }})) {{ \
                  foreach ($rr in @($x | Get-NetFirewallRule -ErrorAction SilentlyContinue)) {{ \
                    if ($rr.Direction -eq 'Inbound' -and $rr.Enabled -eq 'True' -and $rr.Action -eq 'Block' -and \
                        @('{api}', '{kesif}', '{eski_api}', '{eski_kesif}') -notcontains $rr.DisplayName) {{ $engel++ }} }} }} }} catch {{ }}; \
         if ($engel -gt 0) {{ exit {kod_engel} }}; \
         if ($kurulamadi -gt 0) {{ exit {kod_kur} }}; if ($silinemedi -gt 0) {{ exit {kod_sil} }}; exit {kod_tamam}",
        p = p, islevler = ICERIK_ISLEVLERI, api = KURAL_API, kesif = KURAL_KESIF, tcp = api_port, udp = DISCOVERY_PORT,
        eski_api = ESKI_KURAL_API, eski_kesif = ESKI_KURAL_KESIF,
        kod_kur = KOD_KURAL_KURULAMADI, kod_sil = KOD_BOZUK_KURAL_SILINEMEDI, kod_tamam = KOD_TAMAM, kod_engel = KOD_WINDOWS_ENGEL_KURALI,
        engel_kaldir = engel_kaldir_ve_broker_izni(),
    )
}

/// Ekleme betiğinin çıkış kodları (D5 J-3). PowerShell'in kendi "yakalanmamış hata" kodu (1) beklenmeyen arızadır — kurulamadı
/// sayılır. UAC reddi / yükseltilmiş süreç başlatılamadı: `crate::paylasim::KOD_UAC_REDDEDILDI` (1223; `main.rs` sarmalayıcısı).
pub const KOD_TAMAM: i32 = 0;
/// En az bir kural KURULAMADI (`New-NetFirewallRule` düştü) — LAN'dan (mobil / web, ACİL DURDUR dahil) erişim yok.
pub const KOD_KURAL_KURULAMADI: i32 = 2;
/// Doğru kurallar kuruldu ama bu programın BOZUK (ör. Block) eski kuralı SİLİNEMEDİ — engel sürebilir.
pub const KOD_BOZUK_KURAL_SILINEMEDI: i32 = 3;
/// Y209 · S-D5.13 (sahip): bu programı engelleyen Windows'un KENDİ (program kapsamlı, etkin, gelen) Block kuralı var — Block, Allow'dan
/// önce gelir, kurduğumuz kurallar engeli AÇMAZ. Kural SİLİNMEZ (kullanıcının / Windows'un kararı); kullanıcıya "kaldırın" denir.
/// Eskiden betik 0 dönüyor, uyarı kapanıyor, LAN'dan (mobil / web, ACİL DURDUR dahil) erişim kapalı kalıyordu (SON-A1.51).
pub const KOD_WINDOWS_ENGEL_KURALI: i32 = 4;

/// Yükseltilmiş ekleme betiğinin çıkış kodu → arayüze dönecek hata anahtarı (`None` = kurallar kuruldu). UAC reddi MEVCUT metni
/// korur ("Yönetici izni verilmedi …"); sıfır dışı başka her kod "tamam" SAYILMAZ (D5 J-3).
pub fn ekleme_hata_anahtari(kod: i32) -> Option<&'static str> {
    match kod {
        KOD_TAMAM => None,
        crate::paylasim::KOD_UAC_REDDEDILDI => Some("rust.hata.guvenlikDuvariIzinYok"),
        KOD_BOZUK_KURAL_SILINEMEDI => Some("rust.hata.guvenlikDuvariBozukKuralSilinemedi"),
        KOD_WINDOWS_ENGEL_KURALI => Some("rust.hata.guvenlikDuvariWindowsEngelKurali"),
        _ => Some("rust.hata.guvenlikDuvariKuralEklenemedi"),
    }
}

/// KALDIRMA temizliği: kendi adlandırdığımız kuralları sil.
///
/// ⚠️ SAHA BULGUSU 2026-08-29 (kaldırma denetimi): kural EKLENİYOR ama SİLEN KOD HİÇ YOKTU.
/// Kullanıcı client'ı kaldırdıktan sonra `PEMF Backend API` ve `PEMF UDP Discovery` kuralları
/// makinede kaldı ve artık var olmayan bir exe'yi (`...\PEMF Vet Client\runtime\...`) işaret
/// ediyordu. Kaldırma kancasının kendi notu bunu "ayrı ADMIN uninstaller'ının işi" sayıyordu;
/// ama backend'i CLIENT kuruyor, ayrı bir admin kurulumu bu makinede hiç olmadı → kurallar
/// hiçbir kaldırıcıya ait değildi.
///
/// ⚠️ YALNIZ KENDİ ADLANDIRDIĞIMIZ kurallar silinir. Windows'un kullanıcı onayıyla açtığı
/// program-kapsamlı kuralına DOKUNULMAZ: o kullanıcının kendi kararıdır ve başka bir yolla
/// (ör. yeniden kurulum) hâlâ geçerli olabilir.
///
/// ⚠️ Admin gerektirir (`Remove-NetFirewallRule`). Çağıran UAC ile yükseltir ve BAŞARISIZLIĞI
/// YUTAR: temizlik bir nezakettir, kaldırmayı düşürmesi kabul edilemez.
///
/// ⚠️ SON-A1.53 (22 · D5 I-1 değişmezinin ikiz çağrı yeri): adlar servis kurulumuyla (`install_backend_service.ps1` /
/// `setup_services.ps1`) AYNI — aynı ad = aynı kural DEĞİL. Adla bulunan kural YALNIZ bu launcher'ın exe'sine aitse
/// (`PemfKuralBizim`, `backend_exe` = `install::backend_path(kök)`) ya da programı artık VAR OLMAYAN yetim kuralsa
/// (`PemfKuralYetim`, saha bulgusu 2026-08-29) silinir. Eskiden ADLA hepsi siliniyordu: launcher kaldırılınca servis
/// backend'ine LAN'dan (mobil / web, ACİL DURDUR dahil) erişim SESSİZCE kapanıyordu (servis yolu kuralı yeniden denetlemez).
pub fn silme_betigi(backend_exe: &Path) -> String {
    format!(
        "$ErrorActionPreference='SilentlyContinue'; $p='{p}'; {islevler}{yetim}{broker_islevi}\
         foreach ($ad in @('{api}','{kesif}','{eski_api}','{eski_kesif}')) {{ \
           foreach ($r in @(Get-NetFirewallRule -DisplayName $ad -ErrorAction SilentlyContinue | Where-Object {{ $_ }})) {{ \
             if ((PemfKuralBizim $r) -or (PemfKuralYetim $r)) {{ $r | Remove-NetFirewallRule -ErrorAction SilentlyContinue }} }} }}; \
         foreach ($r in @(Get-NetFirewallRule -DisplayName '{broker}' -ErrorAction SilentlyContinue | Where-Object {{ $_ }})) {{ \
           if ((PemfBrokerBizim $r) -or (PemfKuralYetim $r)) {{ $r | Remove-NetFirewallRule -ErrorAction SilentlyContinue }} }}",
        broker = KURAL_BROKER,
        broker_islevi = BROKER_ISLEVI,
        p = ps_kacis(&backend_exe.to_string_lossy()),
        islevler = ICERIK_ISLEVLERI,
        yetim = YETIM_ISLEVI,
        api = KURAL_API,
        kesif = KURAL_KESIF,
        eski_api = ESKI_KURAL_API,
        eski_kesif = ESKI_KURAL_KESIF,
    )
}

/// SAHİP 12 Kasım 2026 (A · #22): adla bulunan broker kuralı BU kurulumun broker'ına mı ait (`$p` = backend → `<dizin>\_internal\bin\
/// mosquitto\mosquitto.exe`). Kaldırma YALNIZ kendi adlı kuralımızı siler; Windows'un kendi kurallarına dokunmaz.
const BROKER_ISLEVI: &str = r##"function PemfBrokerBizim($r) { $af = $r | Get-NetFirewallApplicationFilter -ErrorAction SilentlyContinue; $mq = [IO.Path]::Combine([IO.Path]::GetDirectoryName($p), '_internal\bin\mosquitto\mosquitto.exe'); [bool]($p -and $af -and "$($af.Program)" -ieq $mq) }; "##;

/// SON-A1.53: adlı kuralın programı (ortam değişkenleri açılarak) diskte YOKSA yetimdir — hiçbir kurulum onu kullanamaz.
/// Programsız (`Any`) ya da okunamayan kural yetim SAYILMAZ (kimin olduğu bilinmiyor → dokunulmaz).
const YETIM_ISLEVI: &str = r##"function PemfKuralYetim($r) { $af = $r | Get-NetFirewallApplicationFilter -ErrorAction SilentlyContinue; $prog = "$($af.Program)"; [bool]($prog -and $prog -ne 'Any' -and $prog -ne 'System' -and -not [System.IO.File]::Exists([Environment]::ExpandEnvironmentVariables($prog))) }; "##;

/// Durum denetimi betiği — `backend_exe` biliniyorsa Windows'un KENDİ izni de sayılır.
///
/// ⚠️ YANLIŞ ALARM DÜZELTMESİ (2026-08-11, sahip bildirimi: "eskiden buna gerek olmadan
/// buluyordu"). Denetim YALNIZ kendi adlandırılmış kurallarımıza bakıyordu. Oysa Windows,
/// bir program ilk kez dinlemeye başladığında "erişime izin ver" penceresi gösterir ve
/// kullanıcı onaylarsa **program kapsamlı bir Allow kuralı** oluşturur — bağlantı o kuralla
/// zaten çalışır. Bizim kurallarımız olmadığı için "engelli" deyip kullanıcıyı GEREKSİZ bir
/// UAC istemine itiyorduk (ve gereksiz uyarı, uyarı körlüğü yaratır).
///
/// Yeni kural: şu üçünden biri yeterlidir →
///   1. adlandırılmış kurallarımız (API + keşif),
///   2. backend exe'si için ETKİN, Inbound, **Allow** bir kural (Windows'un kendi izni).
/// ⚠️ Ama exe için ETKİN bir **Block** kuralı varsa durum ENGELLİdir — kullanıcı Windows
/// penceresinde "İptal" demiştir ve o engel KALICIDIR; asıl düzeltmeye ihtiyaç duyulan hâl budur.
///
/// D5 I-1: (1) adlı kurallar ADIYLA değil İÇERİKLE sayılır (`ICERIK_ISLEVLERI`, port = çocuğun GERÇEK portu `api_port`);
/// (2) Windows'un kendi izni API portunu kapsamalı (`PORT_KAPSAMI`) ve kendi adlı kurallarımız orada SAYILMAZ (onlar (1)'de
/// içerikle ölçülür — yoksa 8000'lik ya da dar profilli kendi kuralımız "Windows izni" diye geçerdi).
fn durum_betigi(backend_exe: Option<&Path>, api_port: u16) -> String {
    let adli = format!(
        "$p='{p}'; {islevler}\
         $a = @(@(Get-NetFirewallRule -DisplayName '{api}' -ErrorAction SilentlyContinue) + @(Get-NetFirewallRule -DisplayName '{eski_api}' -ErrorAction SilentlyContinue) | Where-Object {{ $_ -and (PemfKuralUyar $_ 'TCP' {tcp}) }}); \
         $b = @(@(Get-NetFirewallRule -DisplayName '{kesif}' -ErrorAction SilentlyContinue) + @(Get-NetFirewallRule -DisplayName '{eski_kesif}' -ErrorAction SilentlyContinue) | Where-Object {{ $_ -and (PemfKuralUyar $_ 'UDP' {udp}) }}); \
         $adli = [bool]($a.Count -gt 0 -and $b.Count -gt 0); ",
        p = backend_exe.map(|e| ps_kacis(&e.to_string_lossy())).unwrap_or_default(),
        islevler = ICERIK_ISLEVLERI,
        api = KURAL_API,
        kesif = KURAL_KESIF,
        eski_api = ESKI_KURAL_API,
        eski_kesif = ESKI_KURAL_KESIF,
        tcp = api_port,
        udp = DISCOVERY_PORT,
    );
    match backend_exe {
        None => format!("{adli} if ($adli) {{ 'VAR' }} else {{ 'YOKSA' }}"),
        Some(p) => {
            let p = ps_kacis(&p.to_string_lossy());
            format!(
                "{adli} \
                 $exe='{p}'; $izin=$false; $engel=$false; {kapsam}\
                 try {{ \
                   $f = Get-NetFirewallApplicationFilter -ErrorAction SilentlyContinue | \
                        Where-Object {{ $_.Program -and ($_.Program -ieq $exe) }}; \
                   foreach ($x in $f) {{ \
                     $r = $x | Get-NetFirewallRule -ErrorAction SilentlyContinue; \
                     foreach ($rr in $r) {{ \
                       if ($rr.Direction -eq 'Inbound' -and $rr.Enabled -eq 'True') {{ \
                         if ($rr.Action -eq 'Block') {{ $engel = $true }} \
                         elseif ($rr.Action -eq 'Allow' -and @('{api}', '{kesif}', '{eski_api}', '{eski_kesif}') -notcontains $rr.DisplayName -and (PemfPortuKapsar $rr {tcp})) {{ $izin = $true }} \
                       }} }} }} \
                 }} catch {{ }} \
                 if ($engel) {{ 'ENGEL' }} elseif ($adli -or $izin) {{ 'VAR' }} else {{ 'YOKSA' }}",
                kapsam = PORT_KAPSAMI,
                api = KURAL_API,
                kesif = KURAL_KESIF,
                eski_api = ESKI_KURAL_API,
                eski_kesif = ESKI_KURAL_KESIF,
                tcp = api_port,
            )
        }
    }
}

/// Kurallar var mı? Okunamazsa `Acik` (fail-open — bkz. modül notu).
///
/// `backend_exe` verilirse Windows'un kendi otomatik izni de sayılır (bkz. `durum_betigi`).
/// `api_port`: launcher çocuğunun GERÇEK portu (`api_portu`) — kural o portu kapsamalı (D5 I-1).
#[cfg(windows)]
pub fn durum_icin(backend_exe: Option<&Path>, api_port: u16) -> Durum {
    durum_kos("powershell", backend_exe, api_port)
}

/// `durum_icin`in gövdesi; PowerShell programı parametre — testler fail-open kolunu GERÇEK güvenlik duvarını okumadan,
/// başlatılamayan bir program adıyla ölçer (D5: eskiden `durum_asla_PANIKLEMEZ` her `cargo test`te gerçek
/// `Get-NetFirewallRule`ı okuyordu).
#[cfg(windows)]
fn durum_kos(program: &str, backend_exe: Option<&Path>, api_port: u16) -> Durum {
    let betik = durum_betigi(backend_exe, api_port);
    // Konsol penceresi AÇMADAN (bkz. platform::gizli_komut): bu denetim launcher AÇILIŞINDA
    // koşar; çıplak `Command` kullanıcıya siyah pencere gösteriyordu.
    let cikti = crate::platform::gizli_komut(program)
        .args(["-NoProfile", "-NonInteractive", "-Command", &betik])
        .output();
    match cikti {
        Ok(o) => durum_yorumla(o.status.success(), &o.stdout),
        // Okunamadı → ENGELLEME. Yanlış uyarı, uyarı körlüğü yaratır.
        Err(_) => Durum::Acik,
    }
}

/// Durum betiğinin çıktısı → `Durum`. Betik başarısız bittiyse `Acik` (fail-open — bkz. modül notu).
#[cfg_attr(not(windows), allow(dead_code))]
fn durum_yorumla(basarili: bool, stdout: &[u8]) -> Durum {
    if !basarili {
        return Durum::Acik;
    }
    let s = String::from_utf8_lossy(stdout);
    if s.contains("ENGEL") {
        Durum::Engelli
    } else if s.contains("YOKSA") {
        Durum::KuralYok
    } else {
        Durum::Acik
    }
}

#[cfg(not(windows))]
pub fn durum_icin(_backend_exe: Option<&Path>, _api_port: u16) -> Durum {
    Durum::Gereksiz
}

/// Geriye uyum: exe yolu bilinmeden denetim (yalnız adlandırılmış kurallara bakar — içerikle, program hariç; varsayılan port).
pub fn durum() -> Durum {
    durum_icin(None, crate::install::DEFAULT_PORT)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::PathBuf;

    #[test]
    fn KRITIK_windows_kendi_izni_de_SAYILIR() {
        // Sahip bildirimi 2026-08-11: "eskiden buna gerek olmadan buluyordu". Windows, program
        // ilk dinlemede kullanıcı onaylarsa KENDİ Allow kuralını oluşturur ve bağlantı çalışır.
        // Denetim yalnız bizim adlandırılmış kurallarımıza bakarsa YANLIŞ ALARM verir ve
        // kullanıcıyı gereksiz UAC istemine iter.
        let s = durum_betigi(Some(&PathBuf::from(r"C:\PEMF\PEMF_Backend.exe")), 8000);
        assert!(
            s.contains("Get-NetFirewallApplicationFilter"),
            "exe kapsamli kurallar (Windows'un kendi izni) HIC sorgulanmiyor"
        );
        assert!(s.contains("'Allow'"), "Allow kurali dikkate alinmiyor");
        assert!(s.contains("$adli -or $izin"), "adli VEYA windows-izni kabul edilmiyor");
    }

    #[test]
    fn KRITIK_kural_YOK_ile_ENGELLI_AYRI_raporlanir() {
        // ⚠️ EN ÖNEMLİ UX DEĞİŞMEZİ. İkisi aynı sayılırsa, YENİ KURULUMDA (henüz hiç kural
        // yokken, backend hiç dinlemeden) uyarı çıkar ve kullanıcı Windows'un zaten
        // halledeceği bir şey için yönetici istemine itilir.
        let s = durum_betigi(Some(&PathBuf::from(r"C:\PEMF\PEMF_Backend.exe")), 8000);
        assert!(s.contains("'ENGEL'"), "acikca engellenmis hal ayri raporlanmiyor");
        assert!(s.contains("'YOKSA'"), "'kural yok' hali ayri raporlanmiyor");
        assert!(
            !s.contains("{{ 'YOK' }}"),
            "eski TEK 'YOK' cikti hali duruyor → iki durum ayirt edilemez"
        );
    }

    #[test]
    fn KRITIK_ETKIN_BLOCK_kurali_ENGELLI_sayilir() {
        // Kullanıcı Windows penceresinde "İptal" derse Windows BLOCK kuralı yazar ve engel
        // KALICIdır. Asıl düzeltmeye ihtiyaç duyulan hâl budur; "Allow var" diye geçilemez.
        let s = durum_betigi(Some(&PathBuf::from(r"C:\PEMF\PEMF_Backend.exe")), 8000);
        assert!(s.contains("'Block'"), "Block kurali tespit edilmiyor");
        assert!(
            s.contains("if ($engel) { 'ENGEL' }"),
            "Block, Allow'dan ONCE degerlendirilmiyor → engelli kurulum 'acik' gorunur"
        );
    }

    #[test]
    fn exe_YOKKEN_eski_davranis_korunur() {
        let s = durum_betigi(None, 8000);
        assert!(s.contains(KURAL_API) && s.contains(KURAL_KESIF));
        // D5 I-1: adlı kurallar artık İÇERİKLE sayılır (kural başına süzgeç okuması) — "eski davranış"ın korunan kısmı:
        // exe bilinmeden Windows'un kendi izni (TÜM kuralların süzgeç taraması) YAPILMAZ.
        assert!(!s.contains("$f = Get-NetFirewallApplicationFilter") && !s.contains("$izin"));
    }

    #[test]
    fn durum_betigi_yol_KACISI_yapar() {
        // Kurulum dizini kullanıcı-etkili; tek tırnak kapatılıp komut enjekte edilmemeli.
        let s = durum_betigi(Some(&PathBuf::from(r"C:\a'b\PEMF_Backend.exe")), 8000);
        assert!(s.contains(r"C:\a''b\PEMF_Backend.exe"), "tek tirnak kacisi yapilmadi");
    }

    #[test]
    fn betik_iki_kurali_da_ekler() {
        let s = ekleme_betigi(&PathBuf::from(r"C:\PEMF\PEMF_Backend.exe"), 8000);
        assert!(s.contains(KURAL_API), "API kurali yok — mobil baglanamaz");
        assert!(s.contains(KURAL_KESIF), "kesif kurali yok — mobil cihazi BULAMAZ");
        assert!(s.contains("8000") && s.contains("5051"));
        assert!(s.contains("TCP") && s.contains("UDP"));
        assert!(s.contains("Inbound"), "yalnizca inbound gerekli");
    }

    #[test]
    fn betik_IDEMPOTENT() {
        // Klinikte eski servis kurulumu da olabilir; aynı ada ikinci kural eklemek karışıklık
        // yaratır ve kaldırma sırasında biri geride kalır.
        let s = ekleme_betigi(&PathBuf::from("x"), 8000);
        assert!(s.contains("Get-NetFirewallRule"), "var-mi kontrolu yok — kural cogaltilir");
    }

    #[test]
    fn KRITIK_yol_enjeksiyonu_KACIRILIR() {
        // Betik YÜKSELTİLMİŞ çalışır. Kurulum dizini kullanıcı-etkilidir; tek tırnak
        // kapatılabilseydi keyfi komut yönetici olarak koşardı.
        let kotu = PathBuf::from(r"C:\a'; Remove-Item C:\Windows -Recurse; '");
        let s = ekleme_betigi(&kotu, 8000);
        // Doğru kaçış: atama TAM olarak kaçırılmış hâli içermeli (her `'` iki katına çıkmış).
        let beklenen = format!("$p='{}'", kotu.to_string_lossy().replace('\'', "''"));
        assert!(s.contains(&beklenen), "yol dogru kacirilmamis — YUKSELTILMIS RCE");
        // Ham (kaçırılmamış) hâli ASLA geçmemeli.
        assert!(!s.contains(&format!("$p='{}'", kotu.to_string_lossy())),
            "ham yol betige girdi");
        // PowerShell tek-tırnaklı dizede `''` kaçırılmış tırnaktır. Dize iyi-biçimlidir ancak
        // ve ancak İÇERİKTEKİ her tırnak ikili gruplar hâlindeyse — yani `''`lerden ayırınca
        // hiçbir parçada TEK tırnak kalmamalı. Kalsaydı dize erken kapanır ve gerisi KOMUT olurdu.
        let kacirilmis = kotu.to_string_lossy().replace('\'', "''");
        assert!(kacirilmis.split("''").all(|parca| !parca.contains('\'')),
            "kacirilmis yolda tek tirnak kalmis — dize kapanabilir");
    }

    /// D3 T-g ÖNCE-KIRMIZI (ölçüldü: PowerShell 5.1 tokenizer'ı U+2018–U+201B'yi tek tırnak sayar): AKILLI tırnaklı yol da
    /// yükseltilmiş betikte dizeyi kapatamaz — her biri ikilenir.
    #[test]
    fn KRITIK_T_g_AKILLI_tirnakli_yol_enjeksiyonu_KACIRILIR() {
        for t in ['\u{2018}', '\u{2019}', '\u{201A}', '\u{201B}'] {
            let kotu = PathBuf::from(format!(r"C:\Users\a{t}; Remove-Item C:\Windows -Recurse; {t}"));
            let s = ekleme_betigi(&kotu, 8000);
            let ham = kotu.to_string_lossy().into_owned();
            assert!(s.contains(&format!("$p='{}'", ham.replace(t, &format!("{t}{t}")))), "U+{:04X} kaçırılmadı", t as u32);
            assert!(!s.contains(&format!("$p='{ham}'")), "ham yol betiğe girdi (U+{:04X})", t as u32);
        }
        assert_eq!(ps_kacis("a'b\u{2019}c"), "a''b\u{2019}\u{2019}c");
    }

    #[test]
    fn durum_asla_PANIKLEMEZ() {
        // Fail-open sözleşmesi: powershell yoksa/yavaşsa bile çağrı bir değer döndürmeli.
        //
        // ⚠️ 2026-08-11: `Durum`a DÖRDÜNCÜ varyant (`KuralYok`) eklendi ve bu liste
        // güncellenmedi → CI'da (kuralları olmayan temiz runner) kırıldı. Yeni varyant
        // eklenirse burası da güncellenmeli; `matches!` sessizce eskimez, patlar.
        //
        // ⚠️ D5: bu test eskiden GERÇEK `durum()`u çağırıyordu → her `cargo test` (CI dahil) gerçek PowerShell ile gerçek
        // `Get-NetFirewallRule`ı okuyordu ve makinenin kural tablosu sonucu belirliyordu. Artık yorumlayıcı ve başlatılamayan
        // program kolu ölçülür; betiğin kendisi yalnız `mod golge`de GÖLGE NetSecurity ile koşar
        // (kapı: tests/test_launcher_firewall_testleri_GERCEK_guvenlik_duvarini_OKUMAZ_D5.py).
        for (basarili, cikti, beklenen) in [
            (true, "ENGEL", Durum::Engelli),
            (true, "YOKSA", Durum::KuralYok),
            (true, "VAR", Durum::Acik),
            (true, "", Durum::Acik),
            (false, "YOKSA", Durum::Acik),
            (false, "ENGEL", Durum::Acik),
        ] {
            let d = durum_yorumla(basarili, cikti.as_bytes());
            assert!(matches!(
                d,
                Durum::Acik | Durum::KuralYok | Durum::Engelli | Durum::Gereksiz
            ));
            assert_eq!(d, beklenen, "betik çıktısı {cikti:?} (başarılı={basarili}) yanlış yorumlandı — fail-open sözleşmesi");
        }
        #[cfg(windows)]
        assert_eq!(
            durum_kos("pemf-k5-olmayan-powershell", None, crate::install::DEFAULT_PORT),
            Durum::Acik,
            "PowerShell başlatılamayınca durum fail-open (Acik) dönmedi — yanlış 'bağlantı engelli' uyarısı gereksiz UAC'ye iter"
        );
    }

    #[cfg(not(windows))]
    #[test]
    fn windows_disinda_GEREKSIZ() {
        assert_eq!(durum(), Durum::Gereksiz);
    }

    /// D5 I-1 · port TEK KAYNAK: launcher çocuğu 8000 doluysa 8001+'ya kayar ve portunu `backend.port`'a yazar.
    #[test]
    fn KRITIK_I1_api_portu_TEK_KAYNAK_backend_port_dosyasi() {
        let d = tempfile::tempdir().unwrap();
        assert_eq!(api_portu(d.path()), 8000, "port dosyası yokken launcher varsayılanı (8000) dönmedi");
        std::fs::write(d.path().join("backend.port"), "8001\r\n").unwrap();
        assert_eq!(
            api_portu(d.path()),
            8001,
            "launcher çocuğu 8001'e kaydı (backend.port) ama kural portu onu izlemiyor → LAN'dan (mobil / web, ACİL DURDUR dahil) erişim sessizce düşer"
        );
        for bozuk in ["abc", "0", "70000", ""] {
            std::fs::write(d.path().join("backend.port"), bozuk).unwrap();
            assert_eq!(api_portu(d.path()), 8000, "bozuk backend.port ({bozuk:?}) varsayılana (8000) düşmedi");
        }
    }

    /// D5 J-3 (tur 2 · çürütücü n10): Rust kaynağından `//` VE `/* … */` yorumlarını atar (dizge ve karakter sabitlerinin içi korunur;
    /// `'"'` gibi bir karakter sabiti dizge sanılmaz). Eskiden kapılar satırı `//`de kesiyordu — `/* … */` içine alınan çağrı "var"
    /// sayılıyordu (çağrı blok yorumuna alınıp yerine `Ok(Value::Null)` konunca 20 / 50 / 213 passed — YEŞİL).
    fn rust_yorumsuz(src: &str) -> String {
        let k: Vec<char> = src.chars().collect();
        let mut o = String::with_capacity(src.len());
        let mut i = 0;
        while i < k.len() {
            let c = k[i];
            let s = k.get(i + 1).copied();
            if c == '/' && s == Some('/') {
                while i < k.len() && k[i] != '\n' {
                    i += 1;
                }
            } else if c == '/' && s == Some('*') {
                let mut derinlik = 1;
                i += 2;
                while i < k.len() && derinlik > 0 {
                    if k[i] == '/' && k.get(i + 1) == Some(&'*') {
                        derinlik += 1;
                        i += 2;
                    } else if k[i] == '*' && k.get(i + 1) == Some(&'/') {
                        derinlik -= 1;
                        i += 2;
                    } else {
                        if k[i] == '\n' {
                            o.push('\n');
                        }
                        i += 1;
                    }
                }
            } else if c == '"' {
                o.push(c);
                i += 1;
                while i < k.len() && k[i] != '"' {
                    if k[i] == '\\' && i + 1 < k.len() {
                        o.push(k[i]);
                        i += 1;
                    }
                    o.push(k[i]);
                    i += 1;
                }
                if i < k.len() {
                    o.push('"');
                    i += 1;
                }
            } else if c == '\'' && (s == Some('\\') || k.get(i + 2) == Some(&'\'')) {
                // karakter sabiti ('x', '\n', '\u…'); yaşam süresi ('a) olduğu gibi geçer
                let bas = if s == Some('\\') { i + 3 } else { i + 2 };
                let son = (bas..k.len()).find(|&j| k[j] == '\'').unwrap_or(k.len() - 1);
                o.extend(&k[i..=son]);
                i = son + 1;
            } else {
                o.push(c);
                i += 1;
            }
        }
        o
    }

    #[test]
    fn rust_yorumsuz_satir_blok_dizge_ve_karakter() {
        let g = "a(); // x()\nb(/* y() */); /* c(\n) */ d(\"// z\", '\"', '/', '\\'', 'q); // w()\ne();";
        let y = rust_yorumsuz(g);
        assert!(y.contains("a();") && y.contains("b(") && y.contains("d(\"// z\", '\"', '/', '\\'', 'q);") && y.contains("e();"), "{y}");
        assert!(!y.contains("w()"), "karakter sabitinden sonraki yorum kaldı: {y}");
        assert!(!y.contains("x()") && !y.contains("y()") && !y.contains("c("), "yorum kaldı: {y}");
    }

    /// KP-8: Rust blok yorumları İÇ İÇE olabilir — iç `*/` dış yorumu kapatmaz; aradaki çağrı "var" sayılmaz (kapı kandırılmaz).
    #[test]
    fn rust_yorumsuz_ic_ice_blok_yorum() {
        let y = rust_yorumsuz("a(); /* dis /* ic() */ hala_yorum() */ b();");
        assert!(y.contains("a();") && y.contains("b();"), "{y}");
        assert!(!y.contains("ic()") && !y.contains("hala_yorum()"), "iç içe blok yorumun içi kod sayıldı: {y}");
    }

    /// D5 I-1 · çağrı yerleri (`launcher/app` — bu crate'in testi o crate'i derlemez): kural portu ÇOCUĞUN portundan, exe ile AYNI
    /// kurulum kökünden. Yorumlar (`//` ve — D5 J-3 tur 2 — `/* … */`) atılır (çağrı yalnız yorumda kalırsa KIRMIZI), boşluklar silinir.
    #[test]
    fn KRITIK_I1_main_rs_kural_portu_COCUGUN_portundan() {
        // KP-4 A1 (Y257 c): güvenlik duvarı komut kabukları (S) app/src/kabuk.rs'te (main.rs onu `include!` ile katar).
        let kaynak = std::fs::read_to_string(concat!(env!("CARGO_MANIFEST_DIR"), "/../app/src/kabuk.rs")).expect("kabuk.rs okunamadı");
        let yalin = rust_yorumsuz(&kaynak).replace("\r\n", "\n");
        for (islev, cagri) in [
            ("fn firewall_durumu_blocking()", "durum_icin(Some(&exe),api_portu(&root))"),
            ("fn firewall_kurali_ekle_blocking()", "ekleme_betigi(&exe,api_portu(&root))"),
        ] {
            let i = yalin.find(islev).unwrap_or_else(|| panic!("{islev} bulunamadı"));
            let j = yalin[i..].find("\n\u{7d}\n").map(|j| i + j).expect("işlev gövdesinin sonu bulunamadı");
            let govde: String = yalin[i..j].split_whitespace().collect();
            assert!(
                govde.contains(cagri),
                "{islev}: güvenlik duvarı kuralının portu launcher çocuğunun GERÇEK portundan (firewall::api_portu = backend.port) gelmiyor — beklenen `{cagri}`"
            );
            assert!(
                govde.contains("letroot=install::default_install_root(&home_dir());") && govde.contains("letexe=install::backend_path(&root);"),
                "{islev}: exe ve port AYNI kurulum kökünden okunmuyor"
            );
            // SON-A1.54 (22 · A1b, yaşayan c94_m2): çağrı metninin VARLIĞI yetmez — ikinci (sabit portlu) bir çağrı sonucu ezerse kapı
            // yeşil kalıyordu. Çağrı gövdede TEK olmalı.
            let ad = cagri.split('(').next().unwrap_or_default();
            assert_eq!(
                govde.matches(&format!("{ad}(")).count(),
                1,
                "{islev}: `{ad}(` gövdede birden çok kez — sonucu kullanılan çağrı çocuğun portundan gelmeyebilir"
            );
        }
        // SON-A1.54: arayüze dönen durum, ÇOCUĞUN portuyla ölçülen `d`den (sonuç atılıp başka değerle ezilmez).
        let i = yalin.find("fn firewall_durumu_blocking()").expect("durum işlevi");
        let j = yalin[i..].find("\n\u{7d}\n").map(|j| i + j).expect("gövde sonu");
        let govde: String = yalin[i..j].split_whitespace().collect();
        assert!(
            govde.contains("letd=durum_icin(Some(&exe),api_portu(&root));") && govde.contains("\"engelli\":d==Durum::Engelli"),
            "firewall_durumu_blocking: arayüze dönen durum çocuğun portuyla ölçülen sonuçtan gelmiyor"
        );
    }

    /// D5 J-3 · çıkış kodu → arayüz iletisi: başarı YALNIZ 0; UAC reddi (1223) MEVCUT metni korur; kurulamayan kural ve silinemeyen
    /// bozuk kural AYRI iletiyle söylenir (kod iletide). Anahtarlar TR + EN katalogda (`{{kod}}` yer tutucusuyla). Kodlar burada SABİT.
    #[test]
    fn KRITIK_J3_ekleme_cikis_kodu_ARAYUZ_iletisine_cevrilir_UAC_reddi_mevcut_metin() {
        use crate::dil::{katalog, Dil};
        assert_eq!(ekleme_hata_anahtari(0), None, "başarı (0) hata sayıldı");
        assert_eq!(ekleme_hata_anahtari(1223), Some("rust.hata.guvenlikDuvariIzinYok"), "UAC reddinin MEVCUT iletisi değişti");
        assert_eq!(ekleme_hata_anahtari(3), Some("rust.hata.guvenlikDuvariBozukKuralSilinemedi"), "silinemeyen bozuk kural ayrı söylenmiyor");
        // Y209 · S-D5.13: Windows'un kendi Block kuralı AYRI iletiyle ("kaldırın") söylenir — kural silinmez.
        assert_eq!(ekleme_hata_anahtari(4), Some("rust.hata.guvenlikDuvariWindowsEngelKurali"), "Windows engel kuralı ayrı söylenmiyor");
        for kod in [1, 2, 5, 96, 99, -1] {
            assert_eq!(
                ekleme_hata_anahtari(kod),
                Some("rust.hata.guvenlikDuvariKuralEklenemedi"),
                "sıfır dışı çıkış {kod} 'tamam' ya da yanlış ileti sayıldı → arayüz uyarıyı kapatır, erişim YOK"
            );
        }
        for anahtar in [
            "rust.hata.guvenlikDuvariKuralEklenemedi",
            "rust.hata.guvenlikDuvariBozukKuralSilinemedi",
            "rust.hata.guvenlikDuvariWindowsEngelKurali",
        ] {
            for d in [Dil::Tr, Dil::En] {
                let m = katalog(d).get(anahtar).unwrap_or_else(|| panic!("{anahtar} {d:?} katalogda yok"));
                assert!(m.contains("{{kod}}"), "{anahtar} {d:?}: çıkış kodu iletide yok (destek ekibi ayıramaz): {m}");
            }
        }
    }

    /// D5 J-3 · çağrı yeri (`launcher/app`; bu crate'in testi o crate'i derlemez): "İzin ver" yükseltilmiş betiği KODLU koşar
    /// (`ps_yukselterek_kos_kodlu`, `-PassThru` + `exit $p.ExitCode`) ve sonucu SAF `izin_ver_sonucu`na verir (davranışı app crate
    /// testinde: `KRITIK_J3_izin_ver_sonucu_KOD_davranisi_UAC_reddi_mevcut_metin`); kodsuz `ps_yukselterek_kos` (sonuç okunmaz) ve
    /// kod okunmadan "tamam" dönen dal bu gövdede YOK. Yorumlar — `//` ve (tur 2 · n10) `/* … */` — atılır, boşluklar silinir.
    #[test]
    fn KRITIK_J3_main_rs_izin_ver_KODLU_kosar_kodu_Err_e_cevirir() {
        // KP-4 A1 (Y257 c): güvenlik duvarı komut kabukları (S) app/src/kabuk.rs'te (main.rs onu `include!` ile katar).
        let kaynak = std::fs::read_to_string(concat!(env!("CARGO_MANIFEST_DIR"), "/../app/src/kabuk.rs")).expect("kabuk.rs okunamadı");
        let main_rs = std::fs::read_to_string(concat!(env!("CARGO_MANIFEST_DIR"), "/../app/src/main.rs")).expect("main.rs okunamadı");
        let main_yalin = rust_yorumsuz(&main_rs).replace("\r\n", "\n");
        let yalin = rust_yorumsuz(&kaynak).replace("\r\n", "\n");
        let govde_of = |islev: &str| -> String {
            let i = yalin.find(islev).unwrap_or_else(|| panic!("{islev} bulunamadı"));
            let j = yalin[i..].find("\n\u{7d}\n").map(|j| i + j).expect("işlev gövdesinin sonu bulunamadı");
            yalin[i..j].split_whitespace().collect()
        };
        let govde = govde_of("fn firewall_kurali_ekle_blocking()");
        assert!(
            govde.contains("izin_ver_sonucu(ps_yukselterek_kos_kodlu(&ekleme_betigi(&exe,api_portu(&root))))"),
            "'İzin ver' yükseltilmiş betiği ÇIKIŞ KODU okunmadan / sonucu eşlenmeden koşuyor → kural kurulamasa da arayüz 'tamam' der"
        );
        assert!(!govde.contains("ps_yukselterek_kos("), "kodsuz yükseltme (sonuç okunmaz) 'İzin ver' gövdesinde duruyor");
        assert!(!govde.contains("\"status\":\"ok\""), "kod okunmadan 'tamam' dönen bir dal var (başarı yalnız izin_ver_sonucu'nda)");
        // `izin_ver_sonucu` (K, saf) main.rs'te kaldı — kabukta ARANMAZ.
        let esle: String = {
            let i = main_yalin.find("fn izin_ver_sonucu(").expect("fn izin_ver_sonucu( bulunamadı");
            let j = main_yalin[i..].find("\n\u{7d}\n").map(|j| i + j).expect("işlev gövdesinin sonu bulunamadı");
            main_yalin[i..j].split_whitespace().collect()
        };
        assert!(
            esle.contains("pemf_launcher_core::firewall::ekleme_hata_anahtari(kod)"),
            "izin_ver_sonucu çıkış kodunu ekleme_hata_anahtari ile eşlemiyor"
        );
        assert_eq!(esle.matches("\"status\":\"ok\"").count(), 1, "izin_ver_sonucu'nda ikinci bir 'tamam' dalı var");
        // TUR 3 (çürütücü 2 j1): arayüzün ÇAĞIRDIĞI Tauri komutu (`async fn firewall_kurali_ekle`) ölçülmüyordu — `…map_err(…)?`
        // sonuna `.or_else(|_e| Ok(json!({"status":"ok"})))` eklenince saf işlev ve `_blocking` doğru kaldı, Rust `Err`i komut
        // katmanında "tamam"a döndü (app 53 / çekirdek 21 / pytest 1015 passed). Artık komut gövdesi (yorumsuz, boşluksuz) TAM OLARAK
        // `tauri::async_runtime::spawn_blocking(firewall_kurali_ekle_blocking).await.map_err(<görev çöktü iletisi>)?` — `?`ten SONRA
        // hiçbir dönüşüm (`or_else` / `unwrap_or` / `ok()` / `map(`) ve başka deyim YOK; `spawn_blocking`e işlevin KENDİSİ verilir.
        let komut = govde_of("async fn firewall_kurali_ekle()");
        let ac = komut.find('\u{7b}').expect("komut gövdesi yok");
        let ic = &komut[ac + 1..];
        let on = "tauri::async_runtime::spawn_blocking(firewall_kurali_ekle_blocking).await.map_err(";
        assert!(
            ic.starts_with(on),
            "'İzin ver' Tauri komutu `_blocking`in sonucunu doğrudan geçirmiyor (araya dönüşüm / başka çağrı girdi): {ic}"
        );
        // map_err( … ) ayracının kapanışı (dizge içi ayraç sayılmaz) → ardından YALNIZ `?`
        let (mut derinlik, mut dizge, mut kapanis) = (1i32, false, None);
        let mut onceki = ' ';
        for (i, c) in ic[on.len()..].char_indices() {
            if dizge {
                if c == '"' && onceki != '\\' {
                    dizge = false;
                }
            } else if c == '"' {
                dizge = true;
            } else if c == '(' {
                derinlik += 1;
            } else if c == ')' {
                derinlik -= 1;
                if derinlik == 0 {
                    kapanis = Some(on.len() + i + 1);
                    break;
                }
            }
            onceki = if onceki == '\\' { ' ' } else { c };
        }
        let kapanis = kapanis.expect("map_err ayracı kapanmıyor");
        let map_err = &ic[on.len()..kapanis];
        assert!(
            map_err.contains("rust.hata.guvenlikDuvariGorevCoktu"),
            "görev çökmesi MEVCUT iletiyle hataya çevrilmiyor: {map_err}"
        );
        assert_eq!(
            &ic[kapanis..],
            "?",
            "'İzin ver' Tauri komutu `?`ten SONRA sonucu dönüştürüyor (or_else / unwrap_or / ok() / map( …) — Rust Err'i arayüze 'tamam' gidebilir: {ic}"
        );
    }

    /// D5 I-1 — adlı kural İÇERİKLE, port ÇOCUKTAN: ÜRETİLEN betik GÖLGE NetSecurity ile KOŞULUR (yalnız Windows; CI windows-latest).
    /// Gerçek güvenlik duvarına YOL YOK: modül otomatik yükleme KAPALI (gerçek NetSecurity komutu çözülürse çıkış 96), beş
    /// NetSecurity komutu da modülsüz, işaretli gölge İŞLEV (değilse 99), koşu sonunda NetSecurity yüklü değil (değilse 98).
    /// Durum tutan sahte kural tablosu; kural nesnesinde protokol / port / program YOK (gerçeği gibi yalnız süzgeçlerde).
    #[cfg(windows)]
    mod golge {
        use super::*;
        use std::collections::BTreeMap;

        const EXE: &str = r"C:\Kurulum\runtime\PEMF_Backend\PEMF_Backend.exe";
        const SERVIS_EXE: &str = r"C:\PEMF\backend\PEMF_Backend.exe";
        /// Launcher çocuğu 8000 doluyken `find_free_port` ile 8001'e kaydı.
        const COCUK: u16 = 8001;

        fn ekle_betik(port: u16) -> String {
            ekleme_betigi(Path::new(EXE), port)
        }
        fn durum_betik(exe: Option<&str>, port: u16) -> String {
            durum_betigi(exe.map(Path::new), port)
        }
        /// SON-A1.53: kaldırma temizliği betiği (bu launcher'ın exe'si `EXE`).
        fn silme_betik() -> String {
            silme_betigi(Path::new(EXE))
        }

        #[derive(Clone)]
        struct Kural {
            ad: &'static str,
            etkin: &'static str,
            yon: &'static str,
            eylem: &'static str,
            profil: &'static str,
            proto: &'static str,
            port: String,
            program: String,
            silinemez: bool,
        }

        fn api(port: u16) -> Kural {
            Kural {
                ad: KURAL_API,
                etkin: "True",
                yon: "Inbound",
                eylem: "Allow",
                profil: "Any",
                proto: "TCP",
                port: port.to_string(),
                program: EXE.to_string(),
                silinemez: false,
            }
        }
        fn kesif() -> Kural {
            Kural { ad: KURAL_KESIF, proto: "UDP", port: DISCOVERY_PORT.to_string(), ..api(0) }
        }
        /// Windows'un KENDİ izni (ilk dinlemede kullanıcı onayı): ad = exe adı, program kapsamlı, tek profil.
        fn win(proto: &'static str, port: &str, eylem: &'static str) -> Kural {
            Kural { ad: "pemf_backend.exe", proto, port: port.to_string(), eylem, profil: "Public", ..api(0) }
        }
        fn satir(k: &Kural) -> String {
            format!("{}/{}/{}/{}/{}/{}/{}/{}", k.ad, k.etkin, k.yon, k.eylem, k.profil, k.proto, k.port, k.program)
        }
        fn tablo(mut v: Vec<String>) -> Vec<String> {
            v.sort();
            v
        }
        /// Doğru kuralın gölge `New-NetFirewallRule` kaydı — uzak adres BOŞ (A-01: LAN güvenilir; kapsam DEĞİŞMEDİ), profil Any.
        fn yeni(k: &Kural) -> String {
            format!("NEW|{}|Inbound|{}|Allow|{}|{}|Any|", k.ad, EXE, k.proto, k.port)
        }

        struct Sonuc {
            cikti: String,
            tablo: Vec<String>,
            olay: Vec<String>,
            /// D5 J-3: betiğin ÇIKIŞ KODU (`exit N`; betik bir dosyadan nokta-kaynak koşar → `$LASTEXITCODE`). `exit` yoksa 0.
            kod: i32,
            hata: String,
        }

        /// Kural tablosu → aparatın `$kurallar` dizisi (PowerShell sabiti).
        fn kurallar_ps(kurallar: &[Kural]) -> String {
            let satirlar: Vec<String> = kurallar
                .iter()
                .map(|k| {
                    format!(
                        "  @{{ Ad = '{}'; Etkin = '{}'; Yon = '{}'; Eylem = '{}'; Profil = '{}'; Proto = '{}'; Port = '{}'; Program = '{}'; Silinemez = ${} }}",
                        ps_kacis(k.ad),
                        k.etkin,
                        k.yon,
                        k.eylem,
                        k.profil,
                        k.proto,
                        ps_kacis(&k.port),
                        ps_kacis(&k.program),
                        k.silinemez
                    )
                })
                .collect();
            format!("$kurallar = @(\n{}\n)\n", satirlar.join(",\n"))
        }

        fn golge_kos(senaryolar: &[(&str, Vec<Kural>, String, u8)]) -> BTreeMap<String, Sonuc> {
            let s: Vec<_> = senaryolar.iter().map(|(ad, k, b, t)| (*ad, k.clone(), b.clone(), *t, "")).collect();
            golge_kos_ayarli(&s)
        }

        /// `ayar`: gölge arıza düğmesi — `yeni_hata` → gölge `New-NetFirewallRule` "Access is denied" ile DÜŞER (D5 J-3: kurulamayan
        /// kural; grup ilkesi / yetki). Boş = arızasız.
        fn golge_kos_ayarli(senaryolar: &[(&str, Vec<Kural>, String, u8, &str)]) -> BTreeMap<String, Sonuc> {
            let mut ps = String::from(GOLGE_ONSOZ);
            for (ad, kurallar, betik, tur, ayar) in senaryolar {
                ps.push_str(&kurallar_ps(kurallar));
                ps.push_str(&format!("$betik = @'\n{betik}\n'@\nKos '{ad}' $kurallar $betik {tur} '{ayar}'\n"));
            }
            ps.push_str(GOLGE_SONSOZ);
            let dizin = tempfile::tempdir().expect("geçici dizin");
            let yol = dizin.path().join("golge_netsecurity.ps1");
            std::fs::write(&yol, ps.as_bytes()).expect("aparat yazılamadı");
            let o = crate::platform::gizli_komut("powershell")
                .args(["-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File"])
                .arg(&yol)
                // pwsh 7'nin modül yolları 5.1'e sızmasın (aparat Utility'yi $PSHOME'dan tam yolla yükler).
                .env("PSModulePath", "")
                .output()
                .expect("powershell başlatılamadı");
            let out = String::from_utf8_lossy(&o.stdout).into_owned();
            assert!(
                o.status.success() && out.contains("GOLGE-BITTI"),
                "gölge aparatı tamamlanmadı (çıkış {:?}; 96 = gerçek NetSecurity erişilebilir, 97 = aparat dizini yok, 99 = gölge eksik, 98 = NetSecurity yüklendi):\n{out}\n{}",
                o.status.code(),
                String::from_utf8_lossy(&o.stderr)
            );
            let mut r = BTreeMap::new();
            for l in out.lines() {
                if let Some(x) = l.strip_prefix("SENARYO\t") {
                    let p: Vec<&str> = x.splitn(6, '\t').collect();
                    assert_eq!(p.len(), 6, "bozuk aparat satırı: {l}");
                    let parca = |s: &str| s.split(';').filter(|t| !t.is_empty()).map(str::to_string).collect::<Vec<_>>();
                    r.insert(
                        p[0].to_string(),
                        Sonuc {
                            cikti: p[1].to_string(),
                            tablo: tablo(parca(p[2])),
                            olay: parca(p[3]),
                            kod: p[4].trim().parse().unwrap_or_else(|_| panic!("bozuk çıkış kodu: {l}")),
                            hata: p[5].trim().to_string(),
                        },
                    );
                }
            }
            for (ad, ..) in senaryolar {
                assert!(r.contains_key(*ad), "senaryo koşmadı: {ad}\n{out}");
            }
            r
        }

        fn temiz(r: &BTreeMap<String, Sonuc>) {
            for (ad, x) in r {
                assert!(x.hata.is_empty(), "{ad}: üretilen betik HATA verdi (gölgelenmemiş komut / sözdizimi?): {}", x.hata);
            }
        }

        /// D5 J-3 · ÜRETİM BİÇİMİ: yükseltilmiş betik AYRI bir `powershell` SÜRECİ olarak koşar (`-EncodedCommand`) ve çağıran
        /// (`main.rs` `ps_yukselterek_kos_kodlu`) O SÜRECİN çıkış kodunu okur. Burada da betik kendi sürecinde, ÜST DÜZEYDE koşar
        /// (önsöz = gölge NetSecurity + kural tablosu) ve sürecin çıkış kodu döner — `exit N` ile yakalanmamış hata (PowerShell kodu 1)
        /// ayrımı üretimdeki gibidir (ölçüldü 2026-10-27: `-File` ve `-EncodedCommand` `exit 5`te ikisi de 5; `finally` `exit`te de
        /// koşar → olay günlüğü çıkıştan sonra basılır). Dönüş: (çıkış kodu, olaylar, son kural tablosu).
        fn golge_surec_kos(kurallar: &[Kural], betik: &str, ayar: &str) -> (i32, Vec<String>, Vec<String>) {
            let ps = format!(
                "{onsoz}{tablo_ps}Yukle $kurallar '{ayar}'\n'GOLGE-HAZIR'\ntry {{\n{betik}\n}} finally {{\n{sonsoz}\n}}\n",
                onsoz = GOLGE_ONSOZ,
                tablo_ps = kurallar_ps(kurallar),
                sonsoz = GOLGE_SUREC_SONSOZ,
            );
            let dizin = tempfile::tempdir().expect("geçici dizin");
            let yol = dizin.path().join("golge_surec.ps1");
            std::fs::write(&yol, ps.as_bytes()).expect("aparat yazılamadı");
            let o = crate::platform::gizli_komut("powershell")
                .args(["-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File"])
                .arg(&yol)
                .env("PSModulePath", "")
                .output()
                .expect("powershell başlatılamadı");
            let out = String::from_utf8_lossy(&o.stdout).into_owned();
            assert!(
                out.contains("GOLGE-HAZIR"),
                "gölge önsözü tamamlanmadı (çıkış {:?}; 96 = gerçek NetSecurity erişilebilir, 97 = aparat dizini yok, 99 = gölge eksik):\n{out}\n{}",
                o.status.code(),
                String::from_utf8_lossy(&o.stderr)
            );
            assert!(!out.contains("NETSECURITY-YUKLENDI"), "betik GERÇEK NetSecurity modülünü yükledi:\n{out}");
            let alan = |on: &str| -> Vec<String> {
                out.lines()
                    .find_map(|l| l.strip_prefix(on))
                    .unwrap_or_else(|| panic!("aparat {on} satırı yok:\n{out}"))
                    .split(';')
                    .filter(|t| !t.trim().is_empty())
                    .map(|t| t.trim().to_string())
                    .collect()
            };
            (o.status.code().expect("çıkış kodu yok"), alan("OLAY\t"), tablo(alan("TABLO\t")))
        }

        /// D5 J-3 ÖNCE-KIRMIZI (yardımcı I'nın kapsam dışı bulgusu, 2026-10-27): "İzin ver" düğmesinin yükseltilmiş betiği kural
        /// KURAMASA da arayüz "tamam" deyip uyarıyı kapatıyordu. Betik tarafı: kurulamayan kural ilk hatada betiği kesiyordu (ikinci
        /// kural HİÇ denenmiyordu); bozuk (ör. Block) kuralın silinemeyişi `SilentlyContinue` ile yutuluyordu → çıkış 0. Artık iki kural
        /// da denenir ve sonuç ÇIKIŞ KODUYLA söylenir: 2 = kural kurulamadı, 3 = bozuk kural silinemedi (doğrusu yine kurulur).
        /// Kodlar burada SABİT (ürün sabitinden okunmaz — tanım satırı mutasyonu da kırmızı olsun).
        #[test]
        fn KRITIK_J3_ekleme_KURULAMAYAN_ve_SILINEMEYEN_kuralda_SIFIR_DISI_cikis_kodu() {
            let block_silinemez = Kural { eylem: "Block", silinemez: true, ..api(COCUK) };
            let r = golge_kos_ayarli(&[
                ("j_kurulamaz", vec![], ekle_betik(COCUK), 1, "yeni_hata"),
                ("j_kurulamaz_yalniz_kesif", vec![api(COCUK)], ekle_betik(COCUK), 1, "yeni_hata"),
                ("j_block_silinemez", vec![block_silinemez.clone(), kesif()], ekle_betik(COCUK), 1, ""),
                ("j_ikisi_birden", vec![block_silinemez.clone(), kesif()], ekle_betik(COCUK), 1, "yeni_hata"),
                // KARŞIT — başarıda 0 (uyarı haklı olarak kapanır)
                ("j_yok", vec![], ekle_betik(COCUK), 1, ""),
                ("j_dogru", vec![api(COCUK), kesif()], ekle_betik(COCUK), 1, ""),
                ("j_dogru_ariza_dugmesi", vec![api(COCUK), kesif()], ekle_betik(COCUK), 1, "yeni_hata"),
                ("j_block_silinir", vec![Kural { eylem: "Block", ..api(COCUK) }, kesif()], ekle_betik(COCUK), 1, ""),
                ("j_iki_tur", vec![], ekle_betik(COCUK), 2, ""),
            ]);
            temiz(&r);
            let x = &r["j_kurulamaz"];
            assert_eq!(
                x.kod, 2,
                "kural KURULAMADI ama betik başarı ({}) ile bitti → arayüz 'tamam' deyip uyarıyı kapatır, LAN'dan (mobil / web, ACİL DURDUR dahil) erişim YOK",
                x.kod
            );
            assert_eq!(
                x.olay,
                vec![format!("NEWRED|{KURAL_API}"), format!("NEWRED|{KURAL_KESIF}")],
                "ilk kural kurulamayınca ikincisi DENENMEDİ (betik ilk hatada kesildi)"
            );
            assert!(x.tablo.is_empty(), "kurulamayan kural tabloya girdi: {:?}", x.tablo);
            let y = &r["j_kurulamaz_yalniz_kesif"];
            assert_eq!((y.kod, y.olay.clone()), (2, vec![format!("NEWRED|{KURAL_KESIF}")]), "yalnız keşif kuralı kurulamadı — kod 2 değil");
            let b = &r["j_block_silinemez"];
            assert_eq!(
                b.kod, 3,
                "bu programın BOZUK (Block) kuralı SİLİNEMEDİ — engel sürer — ama betik {} ile bitti (hata yutuldu)",
                b.kod
            );
            assert_eq!(
                b.tablo,
                tablo(vec![satir(&block_silinemez), satir(&api(COCUK)), satir(&kesif())]),
                "silinemeyen bozuk kural yüzünden doğrusu KURULMADI"
            );
            assert_eq!(r["j_ikisi_birden"].kod, 2, "kurulamayan kural (erişim YOK) silinemeyenden ÖNCE söylenmeli");
            for ad in ["j_yok", "j_dogru", "j_dogru_ariza_dugmesi", "j_block_silinir", "j_iki_tur"] {
                assert_eq!(r[ad].kod, 0, "{ad}: kurallar kurulduğu / zaten doğru olduğu hâlde betik {} ile bitti (yanlış alarm)", r[ad].kod);
            }
            assert!(r["j_dogru_ariza_dugmesi"].olay.is_empty(), "doğru kural varken yeniden kurulmaya çalışıldı");
        }

        /// Y209 · S-D5.13 → SAHİP 12 Kasım 2026 (istem 46 · #22, ikinci Windows hesabında ölçüldü): standart hesap Windows'un "erişime
        /// izin ver" penceresini yönetici olmadan onaylayamaz → Windows backend için KENDİ Block kurallarını yazar; Block, Allow'dan önce
        /// gelir ve "İzin ver"in kurduğu kurallar engeli açmıyordu (eskiden kod 4 + "kaldırın"; ileti de ekranda ezilip kayboluyordu).
        /// Sahip (A): "İzin ver (yönetici)" YALNIZ PEMF'in KENDİ backend'ine ait etkin, gelen Block kurallarını KALDIRIR ve izinleri kurar
        /// → kod 0. Kaldırılamayan Block (grup ilkesi / yetki) → kod 4 ("kaldırın" iletisi). Devre dışı Block ve Windows'un Allow kuralına
        /// DOKUNULMAZ; başka programın Block kuralına DOKUNULMAZ.
        #[test]
        fn KRITIK_Y209_SAHIP_12_11_windows_block_KALDIRILIR_izin_KURULUR_baska_programa_DOKUNULMAZ() {
            let wb_tcp = win("TCP", "Any", "Block");
            let wb_udp = win("UDP", "Any", "Block");
            let baska = Kural { ad: "baska.exe", program: r"C:\Baska\baska.exe".to_string(), ..win("TCP", "Any", "Block") };
            let r = golge_kos(&[
                ("w_block_iki", vec![wb_tcp.clone(), wb_udp.clone(), baska.clone()], ekle_betik(COCUK), 1),
                ("w_block_tcp", vec![wb_tcp.clone()], ekle_betik(COCUK), 1),
                ("w_block_adli_dogru", vec![wb_tcp.clone(), wb_udp.clone(), api(COCUK), kesif()], ekle_betik(COCUK), 1),
                ("w_block_silinemez", vec![Kural { silinemez: true, ..wb_tcp.clone() }], ekle_betik(COCUK), 1),
                // KARŞIT — engel değil
                ("w_block_devre_disi", vec![Kural { etkin: "False", ..wb_tcp.clone() }], ekle_betik(COCUK), 1),
                ("w_allow", vec![win("TCP", "Any", "Allow")], ekle_betik(COCUK), 1),
            ]);
            temiz(&r);
            for ad in ["w_block_iki", "w_block_tcp", "w_block_adli_dogru"] {
                let x = &r[ad];
                assert_eq!(x.kod, KOD_TAMAM, "{ad}: Windows'un Block kuralı kaldırılıp izin kurulmadı (kod {}); tablo: {:?}", x.kod, x.tablo);
                assert!(x.olay.iter().any(|o| o.starts_with("REMOVE|pemf_backend.exe|")), "{ad}: Windows'un Block kuralı KALDIRILMADI: {:?}", x.olay);
                assert!(!x.tablo.iter().any(|t| t.contains("/Block/") && t.ends_with(EXE)), "{ad}: backend Block kuralı kaldı: {:?}", x.tablo);
                assert!(x.tablo.contains(&satir(&api(COCUK))) && x.tablo.contains(&satir(&kesif())), "{ad}: izin kuralları yok: {:?}", x.tablo);
            }
            assert!(r["w_block_iki"].tablo.contains(&satir(&baska)), "başka programın Block kuralına DOKUNULDU");
            let s = &r["w_block_silinemez"];
            assert_eq!(s.kod, KOD_WINDOWS_ENGEL_KURALI, "kaldırılamayan Windows Block kuralında betik {} ile bitti (engel sürüyor)", s.kod);
            assert!(s.tablo.iter().any(|t| t.contains("/Block/")), "silinemez Block tablodan kalktı: {:?}", s.tablo);
            for ad in ["w_block_devre_disi", "w_allow"] {
                assert_eq!(r[ad].kod, KOD_TAMAM, "{ad}: engel olmayan Windows kuralında betik {} ile bitti (yanlış alarm)", r[ad].kod);
                assert!(!r[ad].olay.iter().any(|o| o.starts_with("REMOVE")), "{ad}: Windows'un kuralına dokunuldu: {:?}", r[ad].olay);
            }
        }

        /// SAHİP 12 Kasım 2026 (A, #22): PEMF'in KENDİ broker'ı (`<backend dizini>\_internal\bin\mosquitto\mosquitto.exe`) için Windows'un
        /// Block kuralı da kaldırılır ve program kapsamlı izin kurulur (Windows'un kendi "İzin ver"i gibi); başka mosquitto'ya dokunulmaz.
        #[test]
        fn KRITIK_IH22_PEMF_mosquitto_block_KALDIRILIR_broker_izni_KURULUR() {
            let d = tempfile::tempdir().unwrap();
            let exe = d.path().join("runtime").join("PEMF_Backend").join("PEMF_Backend.exe");
            let mq = exe.parent().unwrap().join("_internal").join("bin").join("mosquitto").join("mosquitto.exe");
            std::fs::create_dir_all(mq.parent().unwrap()).unwrap();
            std::fs::write(&exe, b"x").unwrap();
            std::fs::write(&mq, b"x").unwrap();
            let mqs = mq.to_string_lossy().into_owned();
            let mq_block = Kural { ad: "mosquitto.exe", program: mqs.clone(), ..win("TCP", "Any", "Block") };
            let baska_mq = Kural { ad: "mosquitto.exe", program: r"C:\Baska\mosquitto.exe".to_string(), ..win("TCP", "Any", "Block") };
            let r = golge_kos(&[("m", vec![mq_block, baska_mq.clone()], ekleme_betigi(&exe, COCUK), 1)]);
            temiz(&r);
            let x = &r["m"];
            assert_eq!(x.kod, KOD_TAMAM, "{:?}", x.olay);
            assert!(x.olay.iter().any(|o| o == &format!("REMOVE|mosquitto.exe|{mqs}")), "PEMF mosquitto Block kuralı kaldırılmadı: {:?}", x.olay);
            assert!(
                x.olay.iter().any(|o| o.starts_with(&format!("NEW|{KURAL_BROKER}|Inbound|{mqs}|Allow|TCP|"))),
                "broker izni kurulmadı: {:?}",
                x.olay
            );
            assert!(x.tablo.contains(&satir(&baska_mq)), "başka mosquitto'nun kuralına DOKUNULDU");
            // Kaldırma temizliği broker kuralını da siler (bu kurulumun broker'ı).
            let k = Kural { ad: KURAL_BROKER, program: mqs.clone(), proto: "TCP", port: "Any".to_string(), ..api(0) };
            let r2 = golge_kos(&[("s", vec![k, baska_mq.clone()], silme_betigi(&exe), 1)]);
            assert!(r2["s"].olay.iter().any(|o| o == &format!("REMOVE|{KURAL_BROKER}|{mqs}")), "kaldırmada broker kuralı kalmış: {:?}", r2["s"].olay);
            assert!(r2["s"].tablo.contains(&satir(&baska_mq)));
        }

        /// #22 (sahip 12 Kasım: "kullanıcı etkileşimini azalt"): paylaşım adımının ön-izin PARÇASI (ÇIKMAZ — paylaşım sonucunu bozmaz) —
        /// `$p` verilince Windows Block'u kaldırır, adlı izinleri (API + keşif) kurar.
        #[test]
        fn KRITIK_IH22_on_izin_parcasi_CIKMAZ_engeli_kaldirir_izinleri_kurar() {
            let betik = format!("$p = '{}'; {} 'ON-IZIN-BITTI'", ps_kacis(EXE), on_izin_parcasi(COCUK));
            let r = golge_kos(&[
                ("o", vec![win("TCP", "Any", "Block")], betik.clone(), 1),
                ("o_ariza", vec![], betik, 1),
            ]);
            let x = &r["o"];
            assert!(x.cikti.contains("ON-IZIN-BITTI"), "parça betiği SONLANDIRDI: {}", x.cikti);
            assert!(x.olay.iter().any(|o| o.starts_with("REMOVE|pemf_backend.exe|")), "{:?}", x.olay);
            assert!(x.tablo.contains(&satir(&api(COCUK))) && x.tablo.contains(&satir(&kesif())), "{:?}", x.tablo);
            assert!(!on_izin_parcasi(COCUK).contains("exit"), "ön-izin parçası çıkış yapıyor");
        }

        /// D5 J-3 · ÜRETİM BİÇİMİ: aynı kollar betik KENDİ `powershell` sürecinde koşarken — çağıranın okuduğu şey sürecin çıkış kodudur.
        #[test]
        fn KRITIK_J3_ekleme_betigi_KENDI_SURECINDE_basarisizlikta_SIFIR_DISI_cikar() {
            let (kod, olay, t) = golge_surec_kos(&[], &ekle_betik(COCUK), "yeni_hata");
            assert_eq!(kod, 2, "kural kurulamadı ama yükseltilmiş SÜREÇ {kod} ile çıktı — çağıran 'tamam' sayar");
            assert_eq!(olay, vec![format!("NEWRED|{KURAL_API}"), format!("NEWRED|{KURAL_KESIF}")], "ikinci kural denenmedi");
            assert!(t.is_empty());
            let block_silinemez = Kural { eylem: "Block", silinemez: true, ..api(COCUK) };
            let (kod, _, t) = golge_surec_kos(&[block_silinemez.clone(), kesif()], &ekle_betik(COCUK), "");
            assert_eq!(kod, 3, "bozuk Block kuralı silinemedi ama süreç {kod} ile çıktı");
            assert_eq!(t, tablo(vec![satir(&block_silinemez), satir(&api(COCUK)), satir(&kesif())]));
            let (kod, olay, t) = golge_surec_kos(&[], &ekle_betik(COCUK), "");
            assert_eq!(kod, 0, "KARŞIT: kurallar kuruldu ama süreç {kod} ile çıktı (yanlış alarm)");
            assert_eq!(olay, vec![yeni(&api(COCUK)), yeni(&kesif())]);
            assert_eq!(t, tablo(vec![satir(&api(COCUK)), satir(&kesif())]));
        }

        #[test]
        fn KRITIK_I1_ekleme_ayni_adli_BOZUK_kurali_ICERIKLE_duzeltir_portu_COCUKTAN_alir() {
            let bozuklar: Vec<(&str, Kural, Kural)> = vec![
                ("e_devre_disi", Kural { etkin: "False", ..api(COCUK) }, kesif()),
                ("e_block", Kural { eylem: "Block", ..api(COCUK) }, kesif()),
                ("e_giden", Kural { yon: "Outbound", ..api(COCUK) }, kesif()),
                ("e_udp", Kural { proto: "UDP", ..api(COCUK) }, kesif()),
                ("e_eski_port_8000", api(8000), kesif()),
                ("e_dar_profil", Kural { profil: "Private", ..api(COCUK) }, kesif()),
                ("e_kesif_tcp", api(COCUK), Kural { proto: "TCP", ..kesif() }),
                ("e_kesif_devre_disi", api(COCUK), Kural { etkin: "False", ..kesif() }),
            ];
            let s: Vec<_> = bozuklar.iter().map(|(ad, a, k)| (*ad, vec![a.clone(), k.clone()], ekle_betik(COCUK), 1u8)).collect();
            let r = golge_kos(&s);
            temiz(&r);
            for (ad, a, k) in &bozuklar {
                let x = &r[*ad];
                assert_eq!(
                    x.tablo,
                    tablo(vec![satir(&api(COCUK)), satir(&kesif())]),
                    "{ad}: aynı adlı BOZUK kural 'var' sayılıp bırakıldı ya da doğrusu (TCP {COCUK} = çocuğun GERÇEK portu) kurulmadı → LAN'dan (mobil / web, ACİL DURDUR dahil) erişim sessizce düşer"
                );
                let (bozuk, dogru) = if satir(a) != satir(&api(COCUK)) { (a, api(COCUK)) } else { (k, kesif()) };
                assert_eq!(
                    x.olay,
                    vec![format!("REMOVE|{}|{}", bozuk.ad, bozuk.program), yeni(&dogru)],
                    "{ad}: tek sil + tek kur beklenirdi"
                );
            }
        }

        #[test]
        fn KRITIK_I1_baska_programin_ayni_adli_kurali_SILINMEZ_SAYILMAZ_silinemeyen_bozukta_dogrusu_kurulur() {
            let servis_api = Kural { program: SERVIS_EXE.to_string(), ..api(COCUK) };
            let servis_kesif = Kural { program: SERVIS_EXE.to_string(), ..kesif() };
            let silinemez = Kural { etkin: "False", silinemez: true, ..api(COCUK) };
            let r = golge_kos(&[
                ("e_servis", vec![servis_api.clone(), servis_kesif.clone()], ekle_betik(COCUK), 1),
                ("e_silinemez", vec![silinemez.clone(), kesif()], ekle_betik(COCUK), 1),
            ]);
            temiz(&r);
            let x = &r["e_servis"];
            assert!(
                !x.olay.iter().any(|o| o.starts_with("REMOVE")),
                "başka programın (servis kurulumu — install_backend_service.ps1 / setup_services.ps1 AYNI adı kullanır) kuralı SİLİNDİ: {:?}",
                x.olay
            );
            assert_eq!(
                x.tablo,
                tablo(vec![satir(&servis_api), satir(&servis_kesif), satir(&api(COCUK)), satir(&kesif())]),
                "başka programın aynı adlı kuralı launcher çocuğunu KAPSAMAZ ama 'var' sayıldı → launcher'ın kuralı kurulmadı"
            );
            assert_eq!(
                r["e_silinemez"].tablo,
                tablo(vec![satir(&silinemez), satir(&api(COCUK)), satir(&kesif())]),
                "silinemeyen bozuk kural yüzünden doğrusu KURULMADI (betik düştü?)"
            );
            // D5 J-3: doğrusu kurulsa da silinemeyen bozuk kural SÖYLENİR (çıkış 3); başka programın kuralına dokunmamak hata değil (0).
            assert_eq!((x.kod, r["e_silinemez"].kod), (0, 3), "çıkış kodları (servis kuralı, silinemeyen bozuk kural)");
        }

        /// SON-A1.53 (22 · A1b) · D5 I-1 değişmezinin İKİZ ÇAĞRI YERİ: KALDIRMA temizliği (`silme_betigi`, `main.rs` `uninstall`) de
        /// başka programın (servis kurulumu — `install_backend_service.ps1` / `setup_services.ps1` AYNI adları kullanır) aynı adlı
        /// kuralını SİLMEMELİ: launcher kaldırılınca servis backend'ine LAN'dan (mobil / web, ACİL DURDUR dahil) erişim sessizce kapanır
        /// (servis yolu kuralı yeniden denetlemez). Silinen: bu launcher'ın exe'sinin adlı kuralları + programı artık VAR OLMAYAN (yetim,
        /// saha bulgusu 2026-08-29) adlı kural. Windows'un kendi (exe adlı) kuralına dokunulmaz (`test_kaldirma_tam_temizlik.py` kapsam sınırı).
        /// Servis programı GERÇEKTEN var olmalı (yetim sayılmasın) → geçici dizinde boş dosya; gerçek güvenlik duvarına YOL YOK (gölge).
        #[test]
        fn KRITIK_SON_A1_53_kaldirma_BASKA_programin_ayni_adli_kuralini_SILMEZ_yetimi_ve_kendisini_siler() {
            let d = tempfile::tempdir().expect("geçici dizin");
            let servis_exe = d.path().join("PEMF_Backend.exe");
            std::fs::write(&servis_exe, b"").expect("sahte servis exe yazılamadı");
            let servis = servis_exe.to_string_lossy().into_owned();
            let yetim = d.path().join("tasindi").join("PEMF_Backend.exe").to_string_lossy().into_owned();
            // Y204 · S-D5.12: servis kurulumu ESKİ adları kullanır; launcher'ın taşınmamış eski adlı kendi kuralı da silinir.
            let servis_api = Kural { ad: ESKI_KURAL_API, program: servis.clone(), ..api(8000) };
            let servis_kesif = Kural { ad: ESKI_KURAL_KESIF, program: servis.clone(), ..kesif() };
            let yetim_api = Kural { ad: ESKI_KURAL_API, program: yetim, ..api(8000) };
            let eski_kendi = Kural { ad: ESKI_KURAL_KESIF, ..kesif() };
            let windows_izni = win("TCP", "Any", "Allow");
            let kurallar =
                vec![api(COCUK), kesif(), eski_kendi, servis_api.clone(), servis_kesif.clone(), yetim_api, windows_izni.clone()];
            let (kod, olay, son) = golge_surec_kos(&kurallar, &silme_betik(), "");
            assert_eq!(
                son,
                tablo(vec![satir(&servis_api), satir(&servis_kesif), satir(&windows_izni)]),
                "kaldırma temizliği yanlış kuralları sildi — başka programın (servis kurulumu) aynı adlı kuralı SİLİNİRSE o backend'e LAN'dan \
                 (ACİL DURDUR dahil) erişim sessizce kapanır; bu launcher'ın / yetim kural KALIRSA yetim kural sızıntısı (2026-08-29). Olaylar: {olay:?}"
            );
            assert_eq!(kod, 0, "temizlik betiği sıfır dışı çıktı");
        }

        /// Y204 · S-D5.12 (sahip): launcher kuralları servis kurulumundan AYRI adla kurulur. Bu exe'nin ESKİ adlı kuralı yeni adlı kurallar
        /// KURULDUKTAN sonra taşınır (silinir); yeni kural kurulamazsa çalışan eski kural SİLİNMEZ (LAN erişimi — ACİL DURDUR dahil — kesilmez).
        /// Servis kurulumunun eski adlı kuralına (başka program) dokunulmaz. Güncelleme sonrası, taşınmamış eski adlı kendi kuralı durumda
        /// geçerlidir (gereksiz uyarı / UAC yok); yalnız servisin eski adlı kuralı launcher çocuğunu kapsamaz.
        #[test]
        fn KRITIK_Y204_S_D5_12_AYRI_ad_ESKI_adli_kendi_kurali_TASINIR_servisinki_DOKUNULMAZ() {
            assert_ne!(KURAL_API, ESKI_KURAL_API, "launcher kuralı servis kurulumuyla AYNI adı taşıyor");
            assert_ne!(KURAL_KESIF, ESKI_KURAL_KESIF, "launcher keşif kuralı servis kurulumuyla AYNI adı taşıyor");
            let eski_api = Kural { ad: ESKI_KURAL_API, ..api(COCUK) };
            let eski_kesif = Kural { ad: ESKI_KURAL_KESIF, ..kesif() };
            let servis = r"C:\Program Files\PEMF\PEMF_Backend.exe".to_string();
            let servis_api = Kural { ad: ESKI_KURAL_API, program: servis.clone(), ..api(8000) };
            let servis_kesif = Kural { ad: ESKI_KURAL_KESIF, program: servis, ..kesif() };
            let r = golge_kos_ayarli(&[
                ("t_tasima", vec![eski_api.clone(), eski_kesif.clone(), servis_api.clone()], ekle_betik(COCUK), 1, ""),
                ("t_kurulamaz", vec![eski_api.clone(), eski_kesif.clone()], ekle_betik(COCUK), 1, "yeni_hata"),
            ]);
            temiz(&r);
            let t = &r["t_tasima"];
            assert_eq!(t.kod, KOD_TAMAM, "taşıma 'tamam' demedi: {:?}", t.olay);
            assert_eq!(
                t.tablo,
                tablo(vec![satir(&servis_api), satir(&api(COCUK)), satir(&kesif())]),
                "taşıma sonrası tablo yanlış (yeni adlı kurallar + servisin DOKUNULMAMIŞ eski adlı kuralı beklenir): {:?}",
                t.olay
            );
            let k = &r["t_kurulamaz"];
            assert_eq!(k.kod, KOD_KURAL_KURULAMADI);
            assert!(
                k.tablo.contains(&satir(&eski_api)) && k.tablo.contains(&satir(&eski_kesif)),
                "yeni kural KURULAMADI ama çalışan ESKİ kural silindi → LAN erişimi kesilir: {:?}",
                k.tablo
            );
            let d = golge_kos(&[
                ("d_eski_kendi", vec![eski_api.clone(), eski_kesif.clone()], durum_betik(Some(EXE), COCUK), 1),
                ("d_yalniz_servis", vec![servis_api.clone(), servis_kesif.clone()], durum_betik(Some(EXE), COCUK), 1),
            ]);
            temiz(&d);
            assert_eq!(d["d_eski_kendi"].cikti, "VAR", "güncelleme sonrası taşınmamış eski adlı KENDİ kuralı yok sayıldı (gereksiz uyarı)");
            assert_eq!(d["d_yalniz_servis"].cikti, "YOKSA", "servisin eski adlı kuralı launcher çocuğunu kapsıyor sayıldı");
        }

        #[test]
        fn KRITIK_I1_karsit_dogru_kural_DOKUNULMAZ_IDEMPOTENT_kapsam_DEGISMEZ() {
            let harf = Kural { program: EXE.to_lowercase(), ..api(COCUK) };
            let harf_k = Kural { program: EXE.to_uppercase(), ..kesif() };
            let wk = win("TCP", "Any", "Allow");
            let r = golge_kos(&[
                ("k_dogru", vec![api(COCUK), kesif()], ekle_betik(COCUK), 1),
                ("k_harf", vec![harf.clone(), harf_k.clone()], ekle_betik(COCUK), 1),
                ("k_yok", vec![], ekle_betik(COCUK), 1),
                ("k_iki_tur", vec![], ekle_betik(COCUK), 2),
                ("k_windows_kendi", vec![wk.clone()], ekle_betik(COCUK), 1),
                ("k_ikiz", vec![api(COCUK), Kural { etkin: "False", ..api(COCUK) }, kesif()], ekle_betik(COCUK), 1),
                ("k_varsayilan_8000", vec![], ekle_betik(8000), 1),
            ]);
            temiz(&r);
            let iki = tablo(vec![satir(&api(COCUK)), satir(&kesif())]);
            assert!(r["k_dogru"].olay.is_empty() && r["k_dogru"].tablo == iki, "doğru kural varken yine silindi / eklendi: {:?}", r["k_dogru"].olay);
            assert!(
                r["k_harf"].olay.is_empty(),
                "program yolunun harf farkı (Windows yolu harf duyarsız) kuralı 'uymuyor' saydı: {:?}",
                r["k_harf"].olay
            );
            assert_eq!(
                r["k_yok"].olay,
                vec![yeni(&api(COCUK)), yeni(&kesif())],
                "kural yokken kurulan kuralların içeriği / kapsamı değişti (uzak adres boş = A-01)"
            );
            assert_eq!(r["k_yok"].tablo, iki);
            assert!(
                r["k_iki_tur"].olay.is_empty() && r["k_iki_tur"].tablo == iki,
                "betik IDEMPOTENT değil — ikinci koşu yine sildi / ekledi: {:?}",
                r["k_iki_tur"].olay
            );
            assert_eq!(
                r["k_windows_kendi"].tablo,
                tablo(vec![satir(&wk), satir(&api(COCUK)), satir(&kesif())]),
                "Windows'un kendi (kullanıcı onaylı) kuralına dokunuldu ya da adlı kurallar kurulmadı"
            );
            assert_eq!(
                r["k_ikiz"].olay,
                vec![format!("REMOVE|{KURAL_API}|{EXE}")],
                "uyan kural VARKEN yalnız bozuk ikiz silinmeli, yeni kural eklenmemeli"
            );
            assert_eq!(r["k_ikiz"].tablo, iki);
            assert_eq!(r["k_varsayilan_8000"].olay, vec![yeni(&api(8000)), yeni(&kesif())], "port parametresi kurala geçmiyor");
        }

        #[test]
        fn KRITIK_I1_durum_ayni_adli_BOZUK_kurali_VAR_saymaz_portu_COCUKTAN_olcer() {
            let e = Some(EXE);
            let servis = |k: Kural| Kural { program: SERVIS_EXE.to_string(), ..k };
            let vakalar: Vec<(&str, Vec<Kural>, Option<&str>, u16, &str)> = vec![
                ("d_devre_disi", vec![Kural { etkin: "False", ..api(COCUK) }, kesif()], e, COCUK, "YOKSA"),
                ("d_giden", vec![Kural { yon: "Outbound", ..api(COCUK) }, kesif()], e, COCUK, "YOKSA"),
                ("d_udp", vec![Kural { proto: "UDP", ..api(COCUK) }, kesif()], e, COCUK, "YOKSA"),
                ("d_eski_port_8000", vec![api(8000), kesif()], e, COCUK, "YOKSA"),
                ("d_dar_profil", vec![Kural { profil: "Private", ..api(COCUK) }, kesif()], e, COCUK, "YOKSA"),
                ("d_servis_programi", vec![servis(api(COCUK)), servis(kesif())], e, COCUK, "YOKSA"),
                ("d_kesif_tcp", vec![api(COCUK), Kural { proto: "TCP", ..kesif() }], e, COCUK, "YOKSA"),
                ("d_kesif_devre_disi", vec![api(COCUK), Kural { etkin: "False", ..kesif() }], e, COCUK, "YOKSA"),
                ("d_win_dar_port", vec![win("TCP", "8000", "Allow")], e, COCUK, "YOKSA"),
                ("d_win_udp", vec![win("UDP", "Any", "Allow")], e, COCUK, "YOKSA"),
                ("d_win_devre_disi", vec![Kural { etkin: "False", ..win("TCP", "Any", "Allow") }], e, COCUK, "YOKSA"),
                ("dn_devre_disi", vec![Kural { etkin: "False", ..api(COCUK) }, kesif()], None, COCUK, "YOKSA"),
                ("dn_eski_port", vec![api(8000), kesif()], None, COCUK, "YOKSA"),
                // KARŞIT — yanlış alarm YOK (fail-open notu; sahip bildirimi 2026-08-11)
                ("d_dogru", vec![api(COCUK), kesif()], e, COCUK, "VAR"),
                ("d_dogru_8000", vec![api(8000), kesif()], e, 8000, "VAR"),
                ("d_harf", vec![Kural { program: EXE.to_lowercase(), ..api(COCUK) }, Kural { program: EXE.to_uppercase(), ..kesif() }], e, COCUK, "VAR"),
                ("d_yok", vec![], e, COCUK, "YOKSA"),
                ("d_block", vec![Kural { eylem: "Block", ..api(COCUK) }, kesif()], e, COCUK, "ENGEL"),
                ("d_win_any", vec![win("TCP", "Any", "Allow")], e, COCUK, "VAR"),
                ("d_win_aralik", vec![win("TCP", "8000-8049", "Allow")], e, COCUK, "VAR"),
                // SON-A1.54 (yaşayan c94_m3 — aralık sınırı ±1): sınırlar DAHİL, bir dışı HARİÇ.
                ("d_win_aralik_ust_sinir", vec![win("TCP", "7990-8001", "Allow")], e, COCUK, "VAR"),
                ("d_win_aralik_alt_sinir", vec![win("TCP", "8001-8049", "Allow")], e, COCUK, "VAR"),
                ("d_win_aralik_ust_bir_eksik", vec![win("TCP", "7990-8000", "Allow")], e, COCUK, "YOKSA"),
                ("d_win_aralik_alt_bir_fazla", vec![win("TCP", "8002-8049", "Allow")], e, COCUK, "YOKSA"),
                ("d_win_block", vec![win("TCP", "Any", "Block"), api(COCUK), kesif()], e, COCUK, "ENGEL"),
                ("dn_dogru", vec![api(COCUK), kesif()], None, COCUK, "VAR"),
                ("dn_program_bilinmiyor", vec![servis(api(COCUK)), servis(kesif())], None, COCUK, "VAR"),
            ];
            let s: Vec<_> = vakalar.iter().map(|(ad, k, exe, port, _)| (*ad, k.clone(), durum_betik(*exe, *port), 1u8)).collect();
            let r = golge_kos(&s);
            temiz(&r);
            for (ad, _, _, _, beklenen) in &vakalar {
                assert_eq!(
                    r[*ad].cikti,
                    *beklenen,
                    "{ad}: durum yanlış — aynı adlı ama içeriği uymayan / başka programın / çocuğun portunu kapsamayan kural 'VAR' sayılırsa LAN'dan erişim engelliyken uyarı ÇIKMAZ"
                );
                assert!(r[*ad].olay.is_empty(), "{ad}: durum denetimi kural DEĞİŞTİRDİ: {:?}", r[*ad].olay);
            }
        }

        const GOLGE_ONSOZ: &str = r##"# PEMF-GOLGE (D5 I-1): gercek NetSecurity'ye YOL YOK
$ErrorActionPreference = 'Stop'
Import-Module "$PSHOME\Modules\Microsoft.PowerShell.Utility\Microsoft.PowerShell.Utility.psd1"
$PSModuleAutoLoadingPreference = 'None'
if (Get-Command Set-NetFirewallRule -ErrorAction SilentlyContinue) { 'GERCEK-NETSECURITY-ERISILEBILIR'; exit 96 }
# D5 J-3: betik dosyası aparatın KENDİ geçici dizinine yazılır (boşsa göreli yol cargo'nun çalışma dizinine — klona — düşerdi).
$script:AparatDizini = $PSScriptRoot
if (-not $script:AparatDizini) { 'APARAT-DIZINI-YOK'; exit 97 }
$script:Tablo = New-Object System.Collections.ArrayList
$script:Filtre = @{}
$script:Olay = New-Object System.Collections.ArrayList
$script:Silinemez = @()
$script:Sayac = 0
function Get-NetFirewallRule {
    [CmdletBinding()]
    param([string]$DisplayName, [Parameter(ValueFromPipeline = $true)]$InputObject)
    process {
        # PEMF-GOLGE
        if ($null -ne $InputObject) {
            foreach ($k in @($script:Tablo)) { if ($k.Name -eq $InputObject.KuralAdi) { $k } }
            return
        }
        if (-not $DisplayName) { return @($script:Tablo) }
        $bulunan = @($script:Tablo | Where-Object { $_.DisplayName -like $DisplayName })
        if ($bulunan.Count -eq 0) { Write-Error "No MSFT_NetFirewallRule objects found with property 'DisplayName' equal to '$DisplayName'."; return }
        $bulunan
    }
}
function Get-NetFirewallPortFilter {
    [CmdletBinding()]
    param([Parameter(ValueFromPipeline = $true)]$InputObject)
    process {
        # PEMF-GOLGE
        if ($null -eq $InputObject) { return }
        $f = $script:Filtre[$InputObject.Name]
        [pscustomobject]@{ KuralAdi = $InputObject.Name; Protocol = $f.Protocol; LocalPort = $f.LocalPort }
    }
}
function Get-NetFirewallApplicationFilter {
    [CmdletBinding()]
    param([Parameter(ValueFromPipeline = $true)]$InputObject)
    process {
        # PEMF-GOLGE
        if ($null -ne $InputObject) { [pscustomobject]@{ KuralAdi = $InputObject.Name; Program = $script:Filtre[$InputObject.Name].Program }; return }
        foreach ($k in @($script:Tablo)) { [pscustomobject]@{ KuralAdi = $k.Name; Program = $script:Filtre[$k.Name].Program } }
    }
}
function New-NetFirewallRule {
    [CmdletBinding()]
    param([string]$DisplayName, [string]$Direction = 'Inbound', [string]$Program = 'Any', [string]$Action = 'Allow',
          [string]$Protocol = 'Any', [string[]]$LocalPort = @('Any'), [Alias('Profile')][string]$Profil = 'Any',
          [string]$Enabled = 'True', [string[]]$RemoteAddress = @())
    # PEMF-GOLGE
    # D5 J-3 arıza düğmesi: kural KURULAMAZ (grup ilkesi / yetki) — olay "NEWRED" (denendi), tabloya girmez.
    if ($script:YeniHata) { [void]$script:Olay.Add("NEWRED|$DisplayName"); Write-Error "Access is denied (golge: New $DisplayName)"; return }
    $script:Sayac++
    $ad = "golge-$($script:Sayac)"
    [void]$script:Olay.Add("NEW|$DisplayName|$Direction|$Program|$Action|$Protocol|$($LocalPort -join ',')|$Profil|$($RemoteAddress -join ',')")
    $k = [pscustomobject]@{ Name = $ad; DisplayName = $DisplayName; Enabled = $Enabled; Direction = $Direction; Action = $Action; Profile = $Profil }
    [void]$script:Tablo.Add($k)
    $script:Filtre[$ad] = @{ Protocol = $Protocol; LocalPort = ($LocalPort -join ','); Program = $Program }
    $k
}
function Remove-NetFirewallRule {
    [CmdletBinding()]
    param([Parameter(ValueFromPipeline = $true)]$InputObject, [string]$DisplayName)
    process {
        # PEMF-GOLGE
        $hedef = @()
        if ($null -ne $InputObject) { $hedef = @($InputObject.Name) }
        elseif ($DisplayName) { $hedef = @($script:Tablo | Where-Object { $_.DisplayName -like $DisplayName } | ForEach-Object { $_.Name }) }
        foreach ($h in $hedef) {
            $k = @($script:Tablo | Where-Object { $_.Name -eq $h })
            if ($k.Count -eq 0) { continue }
            if ($script:Silinemez -contains $h) { Write-Error "Access is denied (golge: $h)"; continue }
            [void]$script:Olay.Add("REMOVE|$($k[0].DisplayName)|$($script:Filtre[$h].Program)")
            $script:Tablo.Remove($k[0])
            $script:Filtre.Remove($h)
        }
    }
}
foreach ($n in @('Get-NetFirewallRule', 'New-NetFirewallRule', 'Remove-NetFirewallRule', 'Get-NetFirewallPortFilter', 'Get-NetFirewallApplicationFilter')) {
    $c = Get-Command $n -ErrorAction SilentlyContinue
    if (-not $c -or "$($c.CommandType)" -ne 'Function' -or $c.ModuleName -or "$($c.ScriptBlock)" -notmatch 'PEMF-GOLGE') { "GOLGE-YOK`t$n"; exit 99 }
}
function Yukle($Kurallar, [string]$Ayar) {
    $script:Tablo.Clear(); $script:Filtre.Clear(); $script:Olay.Clear(); $script:Silinemez = @(); $script:Sayac = 0
    $script:YeniHata = ($Ayar -eq 'yeni_hata')
    foreach ($k in @($Kurallar)) {
        $script:Sayac++
        $n = "kural-$($script:Sayac)"
        [void]$script:Tablo.Add([pscustomobject]@{ Name = $n; DisplayName = $k.Ad; Enabled = $k.Etkin; Direction = $k.Yon; Action = $k.Eylem; Profile = $k.Profil })
        $script:Filtre[$n] = @{ Protocol = $k.Proto; LocalPort = $k.Port; Program = $k.Program }
        if ($k.Silinemez) { $script:Silinemez += $n }
    }
}
function TabloSatirlari {
    @($script:Tablo | ForEach-Object { $f = $script:Filtre[$_.Name]; "$($_.DisplayName)/$($_.Enabled)/$($_.Direction)/$($_.Action)/$($_.Profile)/$($f.Protocol)/$($f.LocalPort)/$($f.Program)" })
}
# D5 J-3: betik bir DOSYADAN, iç bir betik bloğunda NOKTA-KAYNAK olarak koşar (`& { . $args[0] } $yol`) — betikteki `exit N` yalnız
# o dosyayı bitirir ve `$LASTEXITCODE`e yazılır (eskiden `[scriptblock]::Create` ile koşuyordu: `exit` tüm aparatı bitirirdi).
# `& $yol` OLMAZ: dosya kendi betik kapsamını açar ve gölge işlevlerin `$script:` durumu (tablo / olay) o BOŞ kapsama düşer
# (ölçüldü 2026-10-27, PS 5.1: olay boş, "null-valued expression"); dış `& { }` betiğin değişkenlerini ve
# `$ErrorActionPreference`ını `Kos`a sızdırmaz.
function Kos([string]$Ad, $Kurallar, [string]$Betik, [int]$Tur, [string]$Ayar = '') {
    Yukle $Kurallar $Ayar
    $yol = [System.IO.Path]::Combine($script:AparatDizini, 'golge_betik.ps1')
    [System.IO.File]::WriteAllText($yol, $Betik, [System.Text.UTF8Encoding]::new($true))
    $ErrorActionPreference = 'Continue'
    $cikti = @(); $hata = @(); $kod = 0
    for ($i = 0; $i -lt $Tur; $i++) {
        $script:Olay.Clear()
        $global:LASTEXITCODE = 0
        try {
            $cikti = @(& { . $args[0] } $yol 2>&1 | ForEach-Object {
                if ($_ -is [System.Management.Automation.ErrorRecord]) { $hata += "$_" } else { "$_" }
            })
        } catch { $hata += "$_" }
        $kod = $global:LASTEXITCODE
    }
    $tablo = TabloSatirlari
    "SENARYO`t$Ad`t$($cikti -join ',')`t$($tablo -join ';')`t$($script:Olay -join ';')`t$kod`t$($hata -join ' ~ ')"
}
"##;

        /// D5 J-3 süreç kipi: betiğin `exit`inden SONRA da koşar (`finally`) — olay günlüğü, son tablo, NetSecurity sızıntı işareti.
        const GOLGE_SUREC_SONSOZ: &str = r##""OLAY`t$($script:Olay -join ';')"
"TABLO`t$((TabloSatirlari) -join ';')"
if (Get-Module NetSecurity) { 'NETSECURITY-YUKLENDI' }"##;

        const GOLGE_SONSOZ: &str = r##"if (Get-Module NetSecurity) { 'NETSECURITY-YUKLENDI'; exit 98 }
'GOLGE-BITTI'
"##;
    }
}
