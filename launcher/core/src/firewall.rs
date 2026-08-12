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

/// Backend'in dinlediği API portu (LAN + mobil).
pub const API_PORT: u16 = 8000;
/// mDNS/UDP keşif portu — mobil uygulama cihazı bununla bulur.
pub const DISCOVERY_PORT: u16 = 5051;

/// Kural adları — ESKİ servis kurulumundakiyle AYNI. Aynı ada iki kural eklenmesin: klinikte
/// hem servis hem launcher kurulumu bulunabiliyor.
pub const KURAL_API: &str = "PEMF Backend API";
pub const KURAL_KESIF: &str = "PEMF UDP Discovery";

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
fn ps_kacis(s: &str) -> String {
    s.replace('\'', "''")
}

/// Kuralları ekleyen PowerShell betiği (YÜKSELTİLMİŞ çalıştırılmalı).
///
/// Var olan kuralı yeniden eklemez (idempotent) — klinikte eski servis kurulumu da olabilir.
pub fn ekleme_betigi(backend_exe: &Path) -> String {
    let p = ps_kacis(&backend_exe.to_string_lossy());
    format!(
        "$ErrorActionPreference='Stop'; \
         $p='{p}'; \
         if (-not (Get-NetFirewallRule -DisplayName '{api}' -ErrorAction SilentlyContinue)) {{ \
           New-NetFirewallRule -DisplayName '{api}' -Direction Inbound -Program $p \
             -Action Allow -Protocol TCP -LocalPort {tcp} -Profile Any | Out-Null }}; \
         if (-not (Get-NetFirewallRule -DisplayName '{kesif}' -ErrorAction SilentlyContinue)) {{ \
           New-NetFirewallRule -DisplayName '{kesif}' -Direction Inbound -Program $p \
             -Action Allow -Protocol UDP -LocalPort {udp} -Profile Any | Out-Null }}",
        p = p, api = KURAL_API, kesif = KURAL_KESIF, tcp = API_PORT, udp = DISCOVERY_PORT,
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
fn durum_betigi(backend_exe: Option<&Path>) -> String {
    let adli = format!(
        "$a = Get-NetFirewallRule -DisplayName '{api}' -ErrorAction SilentlyContinue; \
         $b = Get-NetFirewallRule -DisplayName '{kesif}' -ErrorAction SilentlyContinue; \
         $adli = [bool]($a -and $b); ",
        api = KURAL_API,
        kesif = KURAL_KESIF
    );
    match backend_exe {
        None => format!("{adli} if ($adli) {{ 'VAR' }} else {{ 'YOKSA' }}"),
        Some(p) => {
            let p = ps_kacis(&p.to_string_lossy());
            format!(
                "{adli} \
                 $exe='{p}'; $izin=$false; $engel=$false; \
                 try {{ \
                   $f = Get-NetFirewallApplicationFilter -ErrorAction SilentlyContinue | \
                        Where-Object {{ $_.Program -and ($_.Program -ieq $exe) }}; \
                   foreach ($x in $f) {{ \
                     $r = $x | Get-NetFirewallRule -ErrorAction SilentlyContinue; \
                     foreach ($rr in $r) {{ \
                       if ($rr.Direction -eq 'Inbound' -and $rr.Enabled -eq 'True') {{ \
                         if ($rr.Action -eq 'Block') {{ $engel = $true }} \
                         elseif ($rr.Action -eq 'Allow') {{ $izin = $true }} \
                       }} }} }} \
                 }} catch {{ }} \
                 if ($engel) {{ 'ENGEL' }} elseif ($adli -or $izin) {{ 'VAR' }} else {{ 'YOKSA' }}"
            )
        }
    }
}

/// Kurallar var mı? Okunamazsa `Acik` (fail-open — bkz. modül notu).
///
/// `backend_exe` verilirse Windows'un kendi otomatik izni de sayılır (bkz. `durum_betigi`).
#[cfg(windows)]
pub fn durum_icin(backend_exe: Option<&Path>) -> Durum {
    let betik = durum_betigi(backend_exe);
    // Konsol penceresi AÇMADAN (bkz. platform::gizli_komut): bu denetim launcher AÇILIŞINDA
    // koşar; çıplak `Command` kullanıcıya siyah pencere gösteriyordu.
    let cikti = crate::platform::gizli_komut("powershell")
        .args(["-NoProfile", "-NonInteractive", "-Command", &betik])
        .output();
    match cikti {
        Ok(o) if o.status.success() => {
            let s = String::from_utf8_lossy(&o.stdout);
            if s.contains("ENGEL") {
                Durum::Engelli
            } else if s.contains("YOKSA") {
                Durum::KuralYok
            } else {
                Durum::Acik
            }
        }
        // Okunamadı → ENGELLEME. Yanlış uyarı, uyarı körlüğü yaratır.
        _ => Durum::Acik,
    }
}

#[cfg(not(windows))]
pub fn durum_icin(_backend_exe: Option<&Path>) -> Durum {
    Durum::Gereksiz
}

/// Geriye uyum: exe yolu bilinmeden denetim (yalnız adlandırılmış kurallara bakar).
pub fn durum() -> Durum {
    durum_icin(None)
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
        let s = durum_betigi(Some(&PathBuf::from(r"C:\PEMF\PEMF_Backend.exe")));
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
        let s = durum_betigi(Some(&PathBuf::from(r"C:\PEMF\PEMF_Backend.exe")));
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
        let s = durum_betigi(Some(&PathBuf::from(r"C:\PEMF\PEMF_Backend.exe")));
        assert!(s.contains("'Block'"), "Block kurali tespit edilmiyor");
        assert!(
            s.contains("if ($engel) { 'ENGEL' }"),
            "Block, Allow'dan ONCE degerlendirilmiyor → engelli kurulum 'acik' gorunur"
        );
    }

    #[test]
    fn exe_YOKKEN_eski_davranis_korunur() {
        let s = durum_betigi(None);
        assert!(s.contains(KURAL_API) && s.contains(KURAL_KESIF));
        assert!(!s.contains("Get-NetFirewallApplicationFilter"));
    }

    #[test]
    fn durum_betigi_yol_KACISI_yapar() {
        // Kurulum dizini kullanıcı-etkili; tek tırnak kapatılıp komut enjekte edilmemeli.
        let s = durum_betigi(Some(&PathBuf::from(r"C:\a'b\PEMF_Backend.exe")));
        assert!(s.contains(r"C:\a''b\PEMF_Backend.exe"), "tek tirnak kacisi yapilmadi");
    }

    #[test]
    fn betik_iki_kurali_da_ekler() {
        let s = ekleme_betigi(&PathBuf::from(r"C:\PEMF\PEMF_Backend.exe"));
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
        let s = ekleme_betigi(&PathBuf::from("x"));
        assert!(s.contains("Get-NetFirewallRule"), "var-mi kontrolu yok — kural cogaltilir");
    }

    #[test]
    fn KRITIK_yol_enjeksiyonu_KACIRILIR() {
        // Betik YÜKSELTİLMİŞ çalışır. Kurulum dizini kullanıcı-etkilidir; tek tırnak
        // kapatılabilseydi keyfi komut yönetici olarak koşardı.
        let kotu = PathBuf::from(r"C:\a'; Remove-Item C:\Windows -Recurse; '");
        let s = ekleme_betigi(&kotu);
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

    #[test]
    fn durum_asla_PANIKLEMEZ() {
        // Fail-open sözleşmesi: powershell yoksa/yavaşsa bile çağrı bir değer döndürmeli.
        //
        // ⚠️ 2026-08-11: `Durum`a DÖRDÜNCÜ varyant (`KuralYok`) eklendi ve bu liste
        // güncellenmedi → CI'da (kuralları olmayan temiz runner) kırıldı. Yeni varyant
        // eklenirse burası da güncellenmeli; `matches!` sessizce eskimez, patlar.
        let d = durum();
        assert!(matches!(
            d,
            Durum::Acik | Durum::KuralYok | Durum::Engelli | Durum::Gereksiz
        ));
    }

    #[cfg(not(windows))]
    #[test]
    fn windows_disinda_GEREKSIZ() {
        assert_eq!(durum(), Durum::Gereksiz);
    }
}
