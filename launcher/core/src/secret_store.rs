// Author: mertaygn, cglrgrkn
//! "Beni hatırla" deposu — oturumu İŞLETİM SİSTEMİ korumalı biçimde saklar.
//!
//! Windows: DPAPI (`CryptProtectData`, kullanıcı kapsamı + uygulamaya özel entropi). Anahtar
//! yönetimi yok, yeni bağımlılık yok (`windows-sys` zaten Tauri ağacında ve yerel cargo
//! önbelleğinde mevcut → çevrimdışı derlenir).
//!
//! ⚠️ KAPSAM SINIRI (bilinçli): DPAPI kullanıcı kapsamında şifreler; AYNI Windows kullanıcısı
//! olarak koşan kötücül bir süreçten KORUMAZ. Klinikte paylaşılan bir Windows hesabı varsa
//! oturum devralınabilir. Bu yüzden "Beni hatırla" kutucuğu VARSAYILAN KAPALI ve blob
//! `install_root` içinde tutulur → uygulama kaldırılınca oturum da gider.
//!
//! macOS/Linux: işletim sistemi korumalı bir depo entegre EDİLMEDİ. Bu platformlarda oturum
//! DİSKE YAZILMAZ (düz metin yazmak, korumanın tamamını anlamsız kılardı) — UI kutucuğu devre
//! dışı bırakır ve sebebini söyler.

use std::path::{Path, PathBuf};
use std::sync::Mutex;

use crate::auth::Session;

/// [F5] (denetim 2026-08-25): süreç-içi `save()` serileştirme. F6 pid-suffixli tek tmp yolu kullanır
/// ve atomikliği "intra-process tek-yazar" varsayımına dayandırır. F5 ikinci bir eşzamanlı yazar
/// ekledi (`son_oturumu_yakala` teardown'da, 60 sn rotasyon thread'i HÂLÂ canlıyken) → ikisi de AYNI
/// pid-tmp'ye yazınca atomik-rename kurtarmaz (iç içe yazım tmp'yi bozar). Bu kilit iki yazarı
/// serileştirir: her rename tam-geçerli bir blob koyar (son yazan kazanır; ikisi de aynı kullanıcının
/// geçerli oturumu). C3 guard rotasyon THREAD'lerini tekilleştirir ama son_oturumu_yakala'yı kapsamaz.
static SAVE_KILIDI: Mutex<()> = Mutex::new(());

/// Şifreli oturum blob'u. `install_root` içinde → kaldırmada birlikte silinir.
pub fn blob_path(install_root: &Path) -> PathBuf {
    install_root.join("auth_session.bin")
}

/// Atomik yazım için geçici blob yolu (F6, denetim 2026-08-24).
///
/// ⚠️ AYNI DİZİNDE (`install_root`) → aynı birim → `fs::rename` gerçekten atomiktir. `temp_dir()`
/// KULLANILMAZ: cross-volume rename ya çöker ya kopyalar (atomiklik kaybolur). pid-suffix
/// cross-process çakışmayı önler; intra-process eşzamanlı yazarları (F5 teardown-yakalama + rotasyon
/// thread'i) `save()` içindeki `SAVE_KILIDI` serileştirir (yol deterministik kalır — F6 testleri
/// bu yola dayanıyor).
fn gecici_blob_path(install_root: &Path) -> PathBuf {
    install_root.join(format!("auth_session.bin.{}.tmp", std::process::id()))
}

/// Bu platformda kalıcı ("beni hatırla") saklama var mı?
pub fn available() -> bool {
    cfg!(windows)
}

/// Oturumu sakla. Best-effort: başarısızlıkta `false` (kullanıcı yine giriş yapmış sayılır,
/// yalnız sonraki açılışta parola sorulur).
pub fn save(install_root: &Path, session: &Session) -> bool {
    let Ok(json) = serde_json::to_vec(session) else {
        return false;
    };
    let Some(sifreli) = protect(&json) else {
        return false;
    };
    // ⚠️ protect() write'tan ÖNCE: serileştirme/DPAPI hatasında diske HİÇ dokunulmaz → eski blob
    // sağlam kalır (mevcut best-effort davranışı korunur).
    // [F5]: disk bölümünü serileştir — teardown son-yakalama ile 60 sn rotasyon thread'i aynı
    // pid-tmp'ye eşzamanlı yazıp bozmasın (zehirlenmede de guard'ı kurtar, best-effort sürsün).
    let _kilit = SAVE_KILIDI.lock().unwrap_or_else(|e| e.into_inner());
    let _ = std::fs::create_dir_all(install_root);
    // 🔴 F6 (denetim 2026-08-24): ATOMİK yazım (tmp aynı dizinde → rename). C3/4df79cc ile yazma
    // "yalnız girişte"den her jeton rotasyonuna (~saatte 1) çıktı; düz `fs::write` yarıda kesilirse
    // (elektrik/kill) SAĞLAM eski blob bozulur → açılışta `None` → parola yeniden. tmp'ye yaz, sonra
    // rename: yeni yazım düşerse eski blob DOKUNULMAZ. Windows `fs::rename` = MoveFileExW +
    // REPLACE_EXISTING (hedef varsa değiştirir) → manuel remove_file(blob)+rename EKLEME, atomik
    // boşluk açar. Emsal: flow.rs::atomik_takas, net.rs part_path.
    let g = gecici_blob_path(install_root);
    if std::fs::write(&g, &sifreli).is_err() {
        let _ = std::fs::remove_file(&g);
        return false;
    }
    if std::fs::rename(&g, blob_path(install_root)).is_err() {
        let _ = std::fs::remove_file(&g);
        return false;
    }
    true
}

/// Saklanan oturumu oku. Dosya yok / çözülemiyor / bozuk → `None` (sessiz).
pub fn load(install_root: &Path) -> Option<Session> {
    let raw = std::fs::read(blob_path(install_root)).ok()?;
    let acik = unprotect(&raw)?;
    serde_json::from_slice::<Session>(&acik).ok()
}

/// DÖNDÜRÜLEN jetonu diske işle. İşlendiyse `true`.
///
/// 🔴 SAHA ARIZASI (2026-08-24) — "Beni hatırla" bozuluyordu. Tek bir refresh-token ailesi İKİ
/// yerde yaşıyordu: burada (DPAPI blob'u) ve uygulama penceresindeki supabase-js istemcisinde.
/// Pencere `autoRefreshToken: true` ile arka planda yeniliyor ve Supabase yenilemede refresh
/// token'ı **DÖNDÜRÜYOR**; döndürülen jeton yalnız tarayıcı deposunda kalıyor, buradaki kopya
/// BAYATLIYORDU. Bir sonraki açılışta bayat jetonla yenileme deneniyor, GoTrue açıkça reddediyor,
/// bu `SessionRevoked`a eşleniyor ve blob SİLİNİYORDU → kullanıcıdan yeniden parola isteniyordu.
///
/// Pencere artık döndürdüğü oturumu backend'e geri yazıyor; bu fonksiyon onu diske işler.
///
/// ⚠️ ÜÇ KAPI (hepsi kasıtlı):
///   1. **Kayıtlı oturum YOKSA yazma.** Kullanıcı "Beni hatırla"yı seçmediyse blob yoktur;
///      devir oturumunu diske yazmak, açıkça istemediği kalıcılığı arkasından kurmak olurdu.
///   2. **Boş refresh jetonu yazma.** Backend `{}` ya da eksik alan dönebilir; boş jetonu
///      işlemek sağlam kaydı YOK EDERDİ.
///   3. **Başka e-posta yazma.** Farklı kullanıcı = rotasyon değil, BAŞKA bir giriş; sessizce
///      yazmak A'nın kaydını B ile değiştirirdi.
/// Ayrıca jeton AYNIYSA yazılmaz — periyodik senkron diski boşuna yormasın.
pub fn rotasyonu_isle(install_root: &Path, yeni: &Session) -> bool {
    if yeni.refresh_token.trim().is_empty() {
        return false;
    }
    let Some(mevcut) = load(install_root) else {
        return false; // "Beni hatırla" kapalı → kalıcılık kurma
    };
    if !mevcut.email.eq_ignore_ascii_case(&yeni.email) {
        return false; // başka kullanıcı
    }
    if mevcut.refresh_token == yeni.refresh_token {
        return false; // değişmemiş → boşuna yazma
    }
    save(install_root, yeni)
}

/// Saklanan oturumu sil ("Çıkış yap" ve iptal edilmiş jeton yolları).
pub fn clear(install_root: &Path) {
    let _ = std::fs::remove_file(blob_path(install_root));
}

// ── Platform katmanı ────────────────────────────────────────────────────────────────────────

/// Uygulamaya özel ek entropi: aynı kullanıcının BAŞKA bir uygulaması bu blob'u
/// `CryptUnprotectData` ile kendiliğinden çözemesin.
#[cfg(windows)]
const ENTROPY: &[u8] = b"PEMF-Vet-Client/auth-session/v1";

#[cfg(windows)]
fn protect(plain: &[u8]) -> Option<Vec<u8>> {
    use windows_sys::Win32::Security::Cryptography::{
        CryptProtectData, CRYPTPROTECT_UI_FORBIDDEN, CRYPT_INTEGER_BLOB,
    };
    unsafe {
        let mut girdi = CRYPT_INTEGER_BLOB {
            cbData: plain.len() as u32,
            pbData: plain.as_ptr() as *mut u8,
        };
        let mut ent = CRYPT_INTEGER_BLOB {
            cbData: ENTROPY.len() as u32,
            pbData: ENTROPY.as_ptr() as *mut u8,
        };
        let mut cikti = CRYPT_INTEGER_BLOB { cbData: 0, pbData: std::ptr::null_mut() };
        // UI_FORBIDDEN: servis/otomasyon bağlamında Windows'un parola istemi AÇILMASIN
        // (aksi halde çağrı süresiz asılabilirdi).
        let ok = CryptProtectData(
            &mut girdi,
            std::ptr::null(),
            &mut ent,
            std::ptr::null(),
            std::ptr::null(),
            CRYPTPROTECT_UI_FORBIDDEN,
            &mut cikti,
        );
        if ok == 0 || cikti.pbData.is_null() {
            return None;
        }
        let v = std::slice::from_raw_parts(cikti.pbData, cikti.cbData as usize).to_vec();
        windows_sys::Win32::Foundation::LocalFree(cikti.pbData as _);
        Some(v)
    }
}

#[cfg(windows)]
fn unprotect(blob: &[u8]) -> Option<Vec<u8>> {
    use windows_sys::Win32::Security::Cryptography::{
        CryptUnprotectData, CRYPTPROTECT_UI_FORBIDDEN, CRYPT_INTEGER_BLOB,
    };
    if blob.is_empty() {
        return None;
    }
    unsafe {
        let mut girdi = CRYPT_INTEGER_BLOB {
            cbData: blob.len() as u32,
            pbData: blob.as_ptr() as *mut u8,
        };
        let mut ent = CRYPT_INTEGER_BLOB {
            cbData: ENTROPY.len() as u32,
            pbData: ENTROPY.as_ptr() as *mut u8,
        };
        let mut cikti = CRYPT_INTEGER_BLOB { cbData: 0, pbData: std::ptr::null_mut() };
        let ok = CryptUnprotectData(
            &mut girdi,
            std::ptr::null_mut(),
            &mut ent,
            std::ptr::null(),
            std::ptr::null(),
            CRYPTPROTECT_UI_FORBIDDEN,
            &mut cikti,
        );
        if ok == 0 || cikti.pbData.is_null() {
            return None;
        }
        let v = std::slice::from_raw_parts(cikti.pbData, cikti.cbData as usize).to_vec();
        windows_sys::Win32::Foundation::LocalFree(cikti.pbData as _);
        Some(v)
    }
}

/// Windows dışı: KALICI SAKLAMA YOK. Düz metin yazmak yerine hiç yazmıyoruz — oturum
/// süreç-ömürlü kalır (bkz. modül başlığı).
#[cfg(not(windows))]
fn protect(_plain: &[u8]) -> Option<Vec<u8>> {
    None
}

#[cfg(not(windows))]
fn unprotect(_blob: &[u8]) -> Option<Vec<u8>> {
    None
}

#[cfg(test)]
mod tests {
    use super::*;

    fn ornek() -> Session {
        Session {
            access_token: "eyJACCESS".into(),
            refresh_token: "REFRESH-XYZ".into(),
            email: "vet@klinik.com".into(),
            expires_at: 1_900_000_000,
        }
    }

    /// "Beni hatırla" yuvarlak-yolu: sakla → oku → AYNI oturum.
    #[cfg(windows)]
    #[test]
    fn oturum_yuvarlak_yolu_calisir() {
        let d = tempfile::tempdir().unwrap();
        assert!(load(d.path()).is_none(), "bos dizinde oturum bulundu");

        assert!(save(d.path(), &ornek()), "DPAPI ile saklanamadi");
        let s = load(d.path()).expect("saklanan oturum okunamadi");
        assert_eq!(s.access_token, "eyJACCESS");
        assert_eq!(s.refresh_token, "REFRESH-XYZ");
        assert_eq!(s.email, "vet@klinik.com");
        assert_eq!(s.expires_at, 1_900_000_000);

        clear(d.path());
        assert!(load(d.path()).is_none(), "'Cikis yap' sonrasi oturum diskte kaldi");
    }

    /// ⚠️ GÜVENLİK: blob DİSKTE DÜZ METİN OLMAMALI. (Bu, DPAPI çağrısı yanlışlıkla
    /// "sadece dosyaya yaz"a dönüştürülürse anında kırmızı verir.)
    #[cfg(windows)]
    #[test]
    fn diskteki_blob_duz_metin_degil() {
        let d = tempfile::tempdir().unwrap();
        assert!(save(d.path(), &ornek()));
        let ham = std::fs::read(blob_path(d.path())).unwrap();
        let metin = String::from_utf8_lossy(&ham);
        assert!(!metin.contains("REFRESH-XYZ"), "refresh_token DISKTE DUZ METIN");
        assert!(!metin.contains("eyJACCESS"), "access_token DISKTE DUZ METIN");
        assert!(!metin.contains("vet@klinik.com"), "e-posta (PII) DISKTE DUZ METIN");
    }

    /// 🔴 F6 (denetim 2026-08-24): yazım anında elektrik/kill blob'u BOZMAMALI. `save` düz
    /// `fs::write` yaparsa yarım yazım SAĞLAM eski oturumu ezer → açılışta bozuk `None` → parola
    /// yeniden. Atomik (tmp+rename): yeni yazım düşerse eski blob DOKUNULMAZ kalır. Geçici-dosya
    /// yolunu bir DİZİN yaparak yeni yazımı deterministik BLOKE eder (elektrik/kill taklidi).
    #[cfg(windows)]
    #[test]
    fn yarim_yazim_ESKI_oturumu_BOZMAZ() {
        let d = tempfile::tempdir().unwrap();
        assert!(save(d.path(), &ornek()), "onkosul: eski oturum saklanamadi");
        assert_eq!(load(d.path()).unwrap().refresh_token, "REFRESH-XYZ");
        // Geçici-dosya yolunu DİZİN yap → yeni yazım (tmp'ye) deterministik DÜŞER.
        std::fs::create_dir_all(gecici_blob_path(d.path())).unwrap();
        let mut yeni = ornek();
        yeni.refresh_token = "YENI-YARIDA".into();
        let ok = save(d.path(), &yeni);
        assert!(!ok, "yarim yazim 'basarili' dondu — atomik degil (duz fs::write bloke tmp'yi yok saydi)");
        assert_eq!(
            load(d.path()).unwrap().refresh_token,
            "REFRESH-XYZ",
            "yarim yazim SAGLAM eski oturumu EZDI (F6: atomik degil)"
        );
    }

    /// Geçici yol `install_root` İÇİNDE olmalı (aynı birim → rename atomik; temp_dir cross-volume çöker).
    #[cfg(windows)]
    #[test]
    fn gecici_yol_install_root_icinde() {
        let d = tempfile::tempdir().unwrap();
        assert_eq!(gecici_blob_path(d.path()).parent(), blob_path(d.path()).parent());
    }

    /// Başarılı save sonrası geçici dosya KALMAZ (yalnız auth_session.bin).
    #[cfg(windows)]
    #[test]
    fn basarili_save_sonrasi_tmp_kalmaz() {
        let d = tempfile::tempdir().unwrap();
        assert!(save(d.path(), &ornek()));
        assert!(!gecici_blob_path(d.path()).exists(), "basarili save sonrasi yetim .tmp kaldi");
        assert!(blob_path(d.path()).exists());
    }

    /// Bozuk/başkasına ait blob sessizce `None` olmalı — çökme YOK (açılış yolunda çalışır).
    #[cfg(windows)]
    #[test]
    fn bozuk_blob_cokmeden_yok_sayilir() {
        let d = tempfile::tempdir().unwrap();
        std::fs::write(blob_path(d.path()), b"bu-DPAPI-blobu-degil").unwrap();
        assert!(load(d.path()).is_none());
        std::fs::write(blob_path(d.path()), b"").unwrap();
        assert!(load(d.path()).is_none());
    }

    /// Windows dışında kalıcı depo YOK → düz metin YAZILMAMALI.
    #[cfg(not(windows))]
    #[test]
    fn desteklenmeyen_platformda_duz_metin_yazilmaz() {
        let d = tempfile::tempdir().unwrap();
        assert!(!available());
        assert!(!save(d.path(), &ornek()));
        assert!(!blob_path(d.path()).exists(), "korumasiz platformda oturum diske yazildi");
    }
}
