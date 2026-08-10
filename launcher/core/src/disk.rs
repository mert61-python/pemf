// Author: mertaygn, cglrgrkn
//! DİSK ALANI — kurulum yarıda ölmesin (2026-08-09 denetimi, Tier 1).
//!
//! ARIZA
//! -----
//! Kurulum yolunda HİÇBİR yerde boş alan kontrolü yoktu ve önbellekteki TAMAMLANMIŞ paketler
//! hiç temizlenmiyordu (yalnız `.part` dosyaları, o da yalnız İPTAL'de). LattePanda'nın eMMC'sinde
//! ölçülen tablo: ~4,8 GB kalıcı önbellek birikiyor, kurulum 1,2 GB indirdikten SONRA
//! `os error 112` (yeterli disk alanı yok) ile ölüyor.
//!
//! Kullanıcı açısından en kötü kısmı şu: hata İNDİRME BİTTİKTEN SONRA, açma aşamasında geliyor.
//! Yani klinik 20 dakika bekliyor, sonra anlaşılmayan bir hata alıyor ve tekrar deniyor —
//! her denemede önbellek biraz daha şişiyor.
//!
//! ÇÖZÜM
//! -----
//!   1) `bos_alan` — platformun gerçek boş alanını sorar.
//!   2) `gereken_alan` — indirilecek + açılacak baytları hesaplar (paketler ZIP_STORED, yani
//!      açılmış boyut ≈ zip boyutu).
//!   3) `yeterli_alan_var_mi` — ÖNCEDEN karar verir; yetmezse indirmeye HİÇ başlanmaz.
//!   4) `olu_onbellek_temizle` — manifest'te ARTIK GEÇMEYEN paketleri siler (eski sürümlerin
//!      1,2 GB'lık kalıntıları). Yer açmanın en ucuz yolu budur.
//!
//! ⚠️ BOŞ ALAN OKUNAMAZSA ENGELLEME. Ölçemediğimiz bir platformda/dosya sisteminde kurulumu
//! reddetmek, gerçek bir sorunu olmayan kullanıcıyı kilitler. Bilinmiyorsa devam edilir; kontrol
//! bir KOLAYLIKtır, güvenlik kapısı değil.

use std::path::{Path, PathBuf};

/// Açma sırasında geçici olarak ihtiyaç duyulan pay (%). Paketler ZIP_STORED olduğundan açılmış
/// boyut ≈ zip boyutu; pay, dosya sistemi ek yükü ve eş zamanlı günlük/geçici dosyalar içindir.
const PAY_YUZDE: u64 = 10;

/// Verilen yolun bulunduğu birimdeki boş bayt. Ölçülemezse `None` (çağıran ENGELLEMEZ).
#[cfg(windows)]
pub fn bos_alan(yol: &Path) -> Option<u64> {
    use std::os::windows::ffi::OsStrExt;
    // Yol henüz yoksa en yakın VAR OLAN atasını sor — kurulum kökü ilk kurulumda yoktur.
    let hedef = mevcut_ata(yol)?;
    let mut geniş: Vec<u16> = hedef.as_os_str().encode_wide().collect();
    geniş.push(0);
    let mut serbest: u64 = 0;
    let ok = unsafe {
        windows_sys::Win32::Storage::FileSystem::GetDiskFreeSpaceExW(
            geniş.as_ptr(),
            &mut serbest,
            std::ptr::null_mut(),
            std::ptr::null_mut(),
        )
    };
    if ok == 0 { None } else { Some(serbest) }
}

#[cfg(not(windows))]
pub fn bos_alan(yol: &Path) -> Option<u64> {
    use std::os::unix::ffi::OsStrExt;
    let hedef = mevcut_ata(yol)?;
    let mut c_yol: Vec<u8> = hedef.as_os_str().as_bytes().to_vec();
    c_yol.push(0);
    // SAFETY: `c_yol` NUL-sonlu; `st` çağrıdan önce sıfırlanır.
    unsafe {
        let mut st: libc::statvfs = std::mem::zeroed();
        if libc::statvfs(c_yol.as_ptr() as *const libc::c_char, &mut st) != 0 {
            return None;
        }
        // Ayrıcalıksız kullanıcıya AÇIK olan blok sayısı (`bavail`), toplam boş (`bfree`) değil.
        Some((st.f_bavail as u64).saturating_mul(st.f_frsize as u64))
    }
}

/// Yol yoksa yukarı doğru VAR OLAN ilk atayı bul (ilk kurulumda kök henüz yaratılmamıştır).
fn mevcut_ata(yol: &Path) -> Option<PathBuf> {
    let mut p = yol;
    loop {
        if p.exists() {
            return Some(p.to_path_buf());
        }
        p = p.parent()?;
    }
}

/// Bu paketleri indirip açmak için gereken bayt.
///
/// `indirilecek`: önbellekte OLMAYAN paketlerin boyutları (indirme + sonra açma → 2×).
/// `acilacak`: önbellekte ZATEN olan ama açılacak paketlerin boyutları (yalnız açma → 1×).
pub fn gereken_alan(indirilecek: &[u64], acilacak: &[u64]) -> u64 {
    let ham: u64 = indirilecek.iter().copied().map(|b| b.saturating_mul(2)).sum::<u64>()
        + acilacak.iter().copied().sum::<u64>();
    ham.saturating_add(ham / 100 * PAY_YUZDE)
}

/// Yeterli alan var mı? `Ok(())` ya da (gereken, mevcut). Ölçülemezse DAİMA `Ok(())`.
pub fn yeterli_alan_var_mi(hedef: &Path, gereken: u64) -> Result<(), (u64, u64)> {
    match bos_alan(hedef) {
        Some(bos) if bos < gereken => Err((gereken, bos)),
        _ => Ok(()),
    }
}

/// Bayt → insan-okur (hata mesajı kullanıcıya gösterilir).
pub fn insan_okur(bayt: u64) -> String {
    const GB: u64 = 1024 * 1024 * 1024;
    const MB: u64 = 1024 * 1024;
    if bayt >= GB {
        format!("{:.1} GB", bayt as f64 / GB as f64)
    } else {
        format!("{} MB", bayt / MB)
    }
}

/// Manifest'te ARTIK GEÇMEYEN önbellek dosyalarını sil; silinen bayt sayısını döner.
///
/// ⚠️ `korunacak` HÂLÂ GEÇERLİ paketlerin dosya adlarıdır. Liste BOŞSA hiçbir şey silinmez:
/// boş liste "hiçbiri geçerli değil" değil, "bilmiyoruz" demektir — yanlış yorumlarsak
/// kullanıcının yeni indirdiği 1,2 GB'ı silip yeniden indirtiriz.
pub fn olu_onbellek_temizle(cache: &Path, korunacak: &[String]) -> u64 {
    if korunacak.is_empty() {
        return 0;
    }
    let mut silinen = 0u64;
    let Ok(girdiler) = std::fs::read_dir(cache) else { return 0 };
    for e in girdiler.flatten() {
        let yol = e.path();
        if !yol.is_file() {
            continue;
        }
        let Some(ad) = yol.file_name().and_then(|s| s.to_str()) else { continue };
        // `.part` dosyaları YARIM indirmelerdir; sürdürülebilir olduklarından burada silinmez
        // (İptal'de `clear_partials` siler). Onları burada silmek, kopan bir indirmenin
        // baştan başlamasına yol açardı.
        if ad.ends_with(".part") || korunacak.iter().any(|k| k == ad) {
            continue;
        }
        let boyut = e.metadata().map(|m| m.len()).unwrap_or(0);
        if std::fs::remove_file(&yol).is_ok() {
            silinen = silinen.saturating_add(boyut);
        }
    }
    silinen
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn bos_alan_gercek_bir_deger_doner() {
        let d = tempfile::tempdir().unwrap();
        let b = bos_alan(d.path()).expect("bu platformda bos alan okunabilmeli");
        assert!(b > 0, "bos alan 0 olamaz");
    }

    #[test]
    fn olmayan_yol_icin_ATASINA_bakar() {
        // İlk kurulumda kurulum kökü HENÜZ YOKTUR; kontrol o yüzden çökmemeli.
        let d = tempfile::tempdir().unwrap();
        let derin = d.path().join("a").join("b").join("c");
        assert!(bos_alan(&derin).is_some(), "olmayan yol icin ata aranmadi");
    }

    #[test]
    fn gereken_alan_indirmeyi_IKI_KEZ_sayar() {
        // İndirilecek paket önce diske yazılır, SONRA açılır → aynı baytlar iki kez yer kaplar.
        let g = gereken_alan(&[1000], &[]);
        assert!(g >= 2000, "indirme+acma iki kez sayilmadi: {g}");
        // Önbellekte olan yalnız açılır.
        assert!(gereken_alan(&[], &[1000]) < g);
    }

    #[test]
    fn pay_eklenir() {
        assert!(gereken_alan(&[], &[1000]) > 1000, "dosya sistemi payi eklenmedi");
    }

    #[test]
    fn olculemeyen_alan_ENGELLEMEZ() {
        // Fail-open sözleşmesi: ölçemediğimiz bir dosya sisteminde kurulumu reddetmeyiz.
        assert!(yeterli_alan_var_mi(Path::new("\0gecersiz"), u64::MAX).is_ok());
    }

    #[test]
    fn yetersiz_alan_YAKALANIR() {
        let d = tempfile::tempdir().unwrap();
        let r = yeterli_alan_var_mi(d.path(), u64::MAX / 2);
        assert!(r.is_err(), "imkansiz boyut icin bile 'yeterli' dendi");
        let (gereken, mevcut) = r.unwrap_err();
        assert!(gereken > mevcut);
    }

    #[test]
    fn olu_onbellek_SILINIR_gecerli_KORUNUR() {
        let d = tempfile::tempdir().unwrap();
        std::fs::write(d.path().join("base-app.zip"), vec![0u8; 100]).unwrap();
        std::fs::write(d.path().join("ESKI-base-app.zip"), vec![0u8; 500]).unwrap();

        let silinen = olu_onbellek_temizle(d.path(), &["base-app.zip".to_string()]);
        assert_eq!(silinen, 500);
        assert!(d.path().join("base-app.zip").exists(), "gecerli paket silindi");
        assert!(!d.path().join("ESKI-base-app.zip").exists(), "olu paket silinmedi");
    }

    #[test]
    fn part_dosyalari_KORUNUR() {
        // Yarım indirmeler Range ile sürdürülebilir; silmek kopan indirmeyi baştan başlatırdı.
        let d = tempfile::tempdir().unwrap();
        std::fs::write(d.path().join("yarim.part"), vec![0u8; 50]).unwrap();
        olu_onbellek_temizle(d.path(), &["baska.zip".to_string()]);
        assert!(d.path().join("yarim.part").exists(), "yarim indirme silindi");
    }

    #[test]
    fn KORUNACAK_BOSSA_hicbir_sey_silinmez() {
        // Boş liste "hiçbiri geçerli değil" DEĞİL, "bilmiyoruz" demektir. Yanlış yorumlanırsa
        // kullanıcının yeni indirdiği 1,2 GB silinir ve yeniden indirilir.
        let d = tempfile::tempdir().unwrap();
        std::fs::write(d.path().join("base.zip"), vec![0u8; 100]).unwrap();
        assert_eq!(olu_onbellek_temizle(d.path(), &[]), 0);
        assert!(d.path().join("base.zip").exists());
    }
}
