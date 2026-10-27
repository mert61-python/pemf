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

/// Kural adları — ESKİ servis kurulumundakiyle (`install_backend_service.ps1` / `setup_services.ps1`) AYNI: klinikte
/// hem servis hem launcher kurulumu bulunabiliyor. D5 I-1: aynı ad = aynı kural DEĞİL — kural PROGRAMIYLA ayrılır; başka
/// programın aynı adlı kuralı launcher çocuğunu kapsamaz (sayılmaz) ve SİLİNMEZ. Aynı exe için ikinci kural eklenmez.
pub const KURAL_API: &str = "PEMF Backend API";
pub const KURAL_KESIF: &str = "PEMF UDP Discovery";

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
pub fn ekleme_betigi(backend_exe: &Path, api_port: u16) -> String {
    let p = ps_kacis(&backend_exe.to_string_lossy());
    format!(
        "$ErrorActionPreference='Stop'; \
         $p='{p}'; {islevler}\
         foreach ($k in @(@('{api}', 'TCP', {tcp}), @('{kesif}', 'UDP', {udp}))) {{ \
           $uyan = 0; \
           foreach ($r in @(Get-NetFirewallRule -DisplayName $k[0] -ErrorAction SilentlyContinue | Where-Object {{ $_ }})) {{ \
             if (PemfKuralUyar $r $k[1] $k[2]) {{ $uyan++ }} \
             elseif (PemfKuralBizim $r) {{ $r | Remove-NetFirewallRule -ErrorAction SilentlyContinue }} }}; \
           if ($uyan -eq 0) {{ \
             New-NetFirewallRule -DisplayName $k[0] -Direction Inbound -Program $p \
               -Action Allow -Protocol $k[1] -LocalPort $k[2] -Profile Any | Out-Null }} }}",
        p = p, islevler = ICERIK_ISLEVLERI, api = KURAL_API, kesif = KURAL_KESIF, tcp = api_port, udp = DISCOVERY_PORT,
    )
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
pub fn silme_betigi() -> String {
    format!(
        "$ErrorActionPreference='SilentlyContinue'; \
         foreach ($ad in @('{api}','{kesif}')) {{ \
           Get-NetFirewallRule -DisplayName $ad -ErrorAction SilentlyContinue | \
             Remove-NetFirewallRule -ErrorAction SilentlyContinue }}",
        api = KURAL_API,
        kesif = KURAL_KESIF
    )
}

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
         $a = @(Get-NetFirewallRule -DisplayName '{api}' -ErrorAction SilentlyContinue | Where-Object {{ $_ -and (PemfKuralUyar $_ 'TCP' {tcp}) }}); \
         $b = @(Get-NetFirewallRule -DisplayName '{kesif}' -ErrorAction SilentlyContinue | Where-Object {{ $_ -and (PemfKuralUyar $_ 'UDP' {udp}) }}); \
         $adli = [bool]($a.Count -gt 0 -and $b.Count -gt 0); ",
        p = backend_exe.map(|e| ps_kacis(&e.to_string_lossy())).unwrap_or_default(),
        islevler = ICERIK_ISLEVLERI,
        api = KURAL_API,
        kesif = KURAL_KESIF,
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
                         elseif ($rr.Action -eq 'Allow' -and @('{api}', '{kesif}') -notcontains $rr.DisplayName -and (PemfPortuKapsar $rr {tcp})) {{ $izin = $true }} \
                       }} }} }} \
                 }} catch {{ }} \
                 if ($engel) {{ 'ENGEL' }} elseif ($adli -or $izin) {{ 'VAR' }} else {{ 'YOKSA' }}",
                kapsam = PORT_KAPSAMI,
                api = KURAL_API,
                kesif = KURAL_KESIF,
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

    /// D5 I-1 · çağrı yerleri (`launcher/app` — bu crate'in testi o crate'i derlemez): kural portu ÇOCUĞUN portundan, exe ile AYNI
    /// kurulum kökünden. `//` yorumları atılır (çağrı yalnız yorumda kalırsa KIRMIZI), boşluklar silinir (biçim kapıyı kırmasın).
    #[test]
    fn KRITIK_I1_main_rs_kural_portu_COCUGUN_portundan() {
        let kaynak = std::fs::read_to_string(concat!(env!("CARGO_MANIFEST_DIR"), "/../app/src/main.rs")).expect("main.rs okunamadı");
        let yalin: String = kaynak.lines().map(|l| l.split("//").next().unwrap_or("")).collect::<Vec<_>>().join("\n");
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
        }
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
            hata: String,
        }

        fn golge_kos(senaryolar: &[(&str, Vec<Kural>, String, u8)]) -> BTreeMap<String, Sonuc> {
            let mut ps = String::from(GOLGE_ONSOZ);
            for (ad, kurallar, betik, tur) in senaryolar {
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
                ps.push_str(&format!(
                    "$kurallar = @(\n{}\n)\n$betik = @'\n{betik}\n'@\nKos '{ad}' $kurallar $betik {tur}\n",
                    satirlar.join(",\n")
                ));
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
                "gölge aparatı tamamlanmadı (çıkış {:?}; 96 = gerçek NetSecurity erişilebilir, 99 = gölge eksik, 98 = NetSecurity yüklendi):\n{out}\n{}",
                o.status.code(),
                String::from_utf8_lossy(&o.stderr)
            );
            let mut r = BTreeMap::new();
            for l in out.lines() {
                if let Some(x) = l.strip_prefix("SENARYO\t") {
                    let p: Vec<&str> = x.splitn(5, '\t').collect();
                    assert_eq!(p.len(), 5, "bozuk aparat satırı: {l}");
                    let parca = |s: &str| s.split(';').filter(|t| !t.is_empty()).map(str::to_string).collect::<Vec<_>>();
                    r.insert(
                        p[0].to_string(),
                        Sonuc { cikti: p[1].to_string(), tablo: tablo(parca(p[2])), olay: parca(p[3]), hata: p[4].trim().to_string() },
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
function Kos([string]$Ad, $Kurallar, [string]$Betik, [int]$Tur) {
    $script:Tablo.Clear(); $script:Filtre.Clear(); $script:Olay.Clear(); $script:Silinemez = @(); $script:Sayac = 0
    foreach ($k in @($Kurallar)) {
        $script:Sayac++
        $n = "kural-$($script:Sayac)"
        [void]$script:Tablo.Add([pscustomobject]@{ Name = $n; DisplayName = $k.Ad; Enabled = $k.Etkin; Direction = $k.Yon; Action = $k.Eylem; Profile = $k.Profil })
        $script:Filtre[$n] = @{ Protocol = $k.Proto; LocalPort = $k.Port; Program = $k.Program }
        if ($k.Silinemez) { $script:Silinemez += $n }
    }
    $ErrorActionPreference = 'Continue'
    $cikti = @(); $hata = @()
    for ($i = 0; $i -lt $Tur; $i++) {
        $script:Olay.Clear()
        try {
            $cikti = @(& ([scriptblock]::Create($Betik)) 2>&1 | ForEach-Object {
                if ($_ -is [System.Management.Automation.ErrorRecord]) { $hata += "$_" } else { "$_" }
            })
        } catch { $hata += "$_" }
    }
    $tablo = @($script:Tablo | ForEach-Object { $f = $script:Filtre[$_.Name]; "$($_.DisplayName)/$($_.Enabled)/$($_.Direction)/$($_.Action)/$($_.Profile)/$($f.Protocol)/$($f.LocalPort)/$($f.Program)" })
    "SENARYO`t$Ad`t$($cikti -join ',')`t$($tablo -join ';')`t$($script:Olay -join ';')`t$($hata -join ' ~ ')"
}
"##;

        const GOLGE_SONSOZ: &str = r##"if (Get-Module NetSecurity) { 'NETSECURITY-YUKLENDI'; exit 98 }
'GOLGE-BITTI'
"##;
    }
}
