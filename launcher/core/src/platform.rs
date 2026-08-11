// Author: mertaygn, cglrgrkn
//! Platform anahtarı — manifest'teki runtime kaydını seçen TEK kaynak.
//!
//! Sessiz fallback YOK. Eski launcher'da Linux istemcisi manifest'te `base_linux`
//! bulamayınca Windows `base.zip`'ini indiriyordu ve backend hiç çalışmıyordu
//! (bkz. pemf-app-packages/publish.ps1 içindeki uyarı). Burada eşleşme bulunamazsa
//! HATA döner; yanlış paketi kurmaktansa kurulum durur.

// ── SİYAH KONSOL PENCERESİ ───────────────────────────────────────────────────────────────────
//
// SAHA ŞİKÂYETİ (2026-08-11): "client güncellemesi için uygulamayı kapatıp geri açtığımda
// 2 kez siyah konsol penceresi çıktı."
//
// SEBEP: launcher pencereli (konsolsuz) bir uygulamadır. Konsol-altsistem bir program
// (powershell, icacls, taskkill, cmd…) böyle bir süreçten başlatılınca Windows ona **YENİ BİR
// KONSOL** açar ve kullanıcı ekranda siyah pencerenin yanıp söndüğünü görür. `CREATE_NO_WINDOW`
// bunu tamamen engeller.
//
// Backend spawn'ında bu bayrak zaten vardı ama YARDIMCI KOMUTLARDA unutulmuştu (güvenlik duvarı
// denetimi + kurulum dizinine ACL). İkisi de "kapat-aç" akışında çalışır → tam olarak 2 pencere.
//
// ⚠️ Windows'ta süreç başlatan HER yer bunu kullanmalı; `Command::new` doğrudan çağrılmamalı.
// `tests/konsol_penceresi.rs` kaynakta çıplak `Command::new` kalmadığını denetler.

/// Konsol penceresi AÇMADAN çalışan bir komut. Windows dışında düz `Command`.
pub fn gizli_komut<S: AsRef<std::ffi::OsStr>>(program: S) -> std::process::Command {
    let mut c = std::process::Command::new(program);
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        /// `CREATE_NO_WINDOW` — süreç konsol penceresi almaz.
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        c.creation_flags(CREATE_NO_WINDOW);
    }
    c
}

/// Manifest v2 `runtimes` anahtarları.
pub const WIN_X64: &str = "win-x64";
pub const LINUX_X64: &str = "linux-x64";
pub const MAC_ARM64: &str = "mac-arm64";
pub const MAC_X64: &str = "mac-x64";

/// Bu ikilinin derlendiği platformun manifest anahtarı.
pub const fn current() -> &'static str {
    #[cfg(all(target_os = "windows", target_arch = "x86_64"))]
    {
        WIN_X64
    }
    #[cfg(all(target_os = "linux", target_arch = "x86_64"))]
    {
        LINUX_X64
    }
    #[cfg(all(target_os = "macos", target_arch = "aarch64"))]
    {
        MAC_ARM64
    }
    #[cfg(all(target_os = "macos", target_arch = "x86_64"))]
    {
        MAC_X64
    }
    // Desteklenmeyen hedeflerde DERLEME hatası ver: çalışma anında yanlış paket
    // indirmektense build'in kırılması yeğdir.
    #[cfg(not(any(
        all(target_os = "windows", target_arch = "x86_64"),
        all(target_os = "linux", target_arch = "x86_64"),
        all(target_os = "macos", target_arch = "aarch64"),
        all(target_os = "macos", target_arch = "x86_64"),
    )))]
    {
        compile_error!(
            "Desteklenmeyen platform: launcher yalnız win-x64 / linux-x64 / mac-arm64 / mac-x64 hedefler."
        )
    }
}

/// Backend çalıştırılabilirinin paket içindeki adı.
pub const fn backend_exe_name() -> &'static str {
    if cfg!(target_os = "windows") {
        "PEMF_Backend.exe"
    } else {
        "PEMF_Backend"
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn current_platform_bilinen_anahtar_dondurur() {
        assert!(matches!(current(), WIN_X64 | LINUX_X64 | MAC_ARM64 | MAC_X64));
    }

    #[test]
    fn backend_adi_windowsta_exe_uzantili() {
        let name = backend_exe_name();
        if cfg!(target_os = "windows") {
            assert_eq!(name, "PEMF_Backend.exe");
        } else {
            assert_eq!(name, "PEMF_Backend");
        }
    }
}
