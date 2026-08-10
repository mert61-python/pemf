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

use crate::auth::Session;

/// Şifreli oturum blob'u. `install_root` içinde → kaldırmada birlikte silinir.
pub fn blob_path(install_root: &Path) -> PathBuf {
    install_root.join("auth_session.bin")
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
    let _ = std::fs::create_dir_all(install_root);
    std::fs::write(blob_path(install_root), sifreli).is_ok()
}

/// Saklanan oturumu oku. Dosya yok / çözülemiyor / bozuk → `None` (sessiz).
pub fn load(install_root: &Path) -> Option<Session> {
    let raw = std::fs::read(blob_path(install_root)).ok()?;
    let acik = unprotect(&raw)?;
    serde_json::from_slice::<Session>(&acik).ok()
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
