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
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Durum {
    /// Kural var (ya da okunamadı → fail-open).
    Acik,
    /// Kural YOK → mobil uygulama bağlanamaz.
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

/// Kurallar var mı? Okunamazsa `Acik` (fail-open — bkz. modül notu).
#[cfg(windows)]
pub fn durum() -> Durum {
    use std::process::Command;
    let betik = format!(
        "$a = Get-NetFirewallRule -DisplayName '{api}' -ErrorAction SilentlyContinue; \
         $b = Get-NetFirewallRule -DisplayName '{kesif}' -ErrorAction SilentlyContinue; \
         if ($a -and $b) {{ 'VAR' }} else {{ 'YOK' }}",
        api = KURAL_API, kesif = KURAL_KESIF);
    let cikti = Command::new("powershell")
        .args(["-NoProfile", "-NonInteractive", "-Command", &betik])
        .output();
    match cikti {
        Ok(o) if o.status.success() => {
            let s = String::from_utf8_lossy(&o.stdout);
            if s.contains("YOK") { Durum::Engelli } else { Durum::Acik }
        }
        // Okunamadı → ENGELLEME. Yanlış uyarı, uyarı körlüğü yaratır.
        _ => Durum::Acik,
    }
}

#[cfg(not(windows))]
pub fn durum() -> Durum {
    Durum::Gereksiz
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::PathBuf;

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
        let d = durum();
        assert!(matches!(d, Durum::Acik | Durum::Engelli | Durum::Gereksiz));
    }

    #[cfg(not(windows))]
    #[test]
    fn windows_disinda_GEREKSIZ() {
        assert_eq!(durum(), Durum::Gereksiz);
    }
}
