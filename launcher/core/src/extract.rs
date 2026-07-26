//! ZIP açma — zip-slip korumalı.
//!
//! Paketler uzaktan iner; arşiv girdisinin adı `../../` içerirse naif bir açıcı
//! kurulum kökünün DIŞINA yazar (zip-slip). Bu, uzaktan kod çalıştırmaya kadar
//! gidebilen klasik bir zafiyettir. Burada her girdinin hedefi kökün altında
//! kalmak ZORUNDA; değilse açma durur.

use std::fs;
use std::io::{self, Read};
use std::path::{Component, Path, PathBuf};

#[derive(Debug, thiserror::Error)]
pub enum ExtractError {
    #[error("dosya sistemi hatası: {0}")]
    Io(#[from] io::Error),
    #[error("zip okunamadı: {0}")]
    Zip(#[from] zip::result::ZipError),
    #[error("GÜVENLİK: arşiv girdisi kurulum dizininin dışına yazmaya çalıştı: {0:?}")]
    PathEscape(String),
}

/// `archive` içeriğini `dest` altına açar. Girdi yolları `dest` dışına çıkamaz.
/// Açılan dosya sayısını döndürür.
pub fn extract_zip(archive: &Path, dest: &Path) -> Result<usize, ExtractError> {
    let file = fs::File::open(archive)?;
    let mut zip = zip::ZipArchive::new(file)?;
    fs::create_dir_all(dest)?;

    let mut written = 0usize;
    for i in 0..zip.len() {
        let mut entry = zip.by_index(i)?;
        // `enclosed_name()` zip-slip'e karşı ilk savunma (mutlak yol / `..` reddeder),
        // ama kendi kontrolümüzü de yapıyoruz: tek savunma hattına güvenme.
        let raw_name = entry.name().to_string();
        let rel = match entry.enclosed_name() {
            Some(p) => p.to_path_buf(),
            None => return Err(ExtractError::PathEscape(raw_name)),
        };
        if !is_safe_relative(&rel) {
            return Err(ExtractError::PathEscape(raw_name));
        }

        let out = dest.join(&rel);
        if entry.is_dir() {
            fs::create_dir_all(&out)?;
            continue;
        }

        // SEMBOLİK LİNKLER: macOS base paketinde 96 adet var (ör. `_internal/Python` →
        // `Python.framework/Versions/3.10/Python`). Düz dosya olarak yazılırlarsa içerik
        // hedef yolun METNİ olur ve dlopen "slice is not valid mach-o file" ile ÇÖKER —
        // backend hiç açılmaz. (Bu hata gerçek pakette uçtan uca testle yakalandı.)
        if is_symlink(&entry) {
            let mut target = String::new();
            entry.read_to_string(&mut target)?;
            create_symlink(&target, &out, dest, &raw_name)?;
            written += 1;
            continue;
        }
        if let Some(parent) = out.parent() {
            fs::create_dir_all(parent)?;
        }
        let mut target = fs::File::create(&out)?;
        io::copy(&mut entry, &mut target)?;
        written += 1;

        // Çalıştırma bitini KORU: PEMF_Backend ve yanındaki ikili/kütüphaneler
        // Unix'te +x olmadan başlatılamaz (zip mode'u kaybolursa kurulum çalışmaz).
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            if let Some(mode) = entry.unix_mode() {
                fs::set_permissions(&out, fs::Permissions::from_mode(mode))?;
            }
        }
    }
    Ok(written)
}

/// Yol yalnız normal bileşenlerden oluşmalı: kök, önek (Windows `C:`), `..` YASAK.
fn is_safe_relative(p: &Path) -> bool {
    p.components().all(|c| matches!(c, Component::Normal(_)))
}

/// ZIP girdisi sembolik link mi? (unix mode'da S_IFLNK)
fn is_symlink(entry: &zip::read::ZipFile<'_>) -> bool {
    const S_IFMT: u32 = 0o170000;
    const S_IFLNK: u32 = 0o120000;
    entry.unix_mode().is_some_and(|m| m & S_IFMT == S_IFLNK)
}

/// Sembolik linki oluşturur — hedefi kurulum kökünün DIŞINA çıkamaz.
///
/// Symlink'ler zip-slip'in ikinci yüzüdür: `link -> ../../../etc/x` girdisi kendisi
/// kök altında dursa bile, sonradan o link ÜZERİNDEN dışarı yazılabilir. Bu yüzden
/// mutlak hedefler ve kökten çıkan göreli hedefler REDDEDİLİR.
fn create_symlink(
    target: &str,
    link_path: &Path,
    root: &Path,
    raw_name: &str,
) -> Result<(), ExtractError> {
    let target_path = Path::new(target);
    if target_path.is_absolute() {
        return Err(ExtractError::PathEscape(format!(
            "{raw_name} -> {target} (mutlak hedef)"
        )));
    }
    // Linkin bulunduğu dizine göre normalize et; `..` fazlaysa kökten çıkar.
    let base = link_path.parent().unwrap_or(root);
    if !stays_within(root, base, target_path) {
        return Err(ExtractError::PathEscape(format!(
            "{raw_name} -> {target} (kurulum dizini disina cikiyor)"
        )));
    }
    if let Some(parent) = link_path.parent() {
        fs::create_dir_all(parent)?;
    }
    // Yeniden kurulumda kalıntı olabilir.
    let _ = fs::remove_file(link_path);

    #[cfg(unix)]
    {
        std::os::unix::fs::symlink(target_path, link_path)?;
        Ok(())
    }
    // Windows'ta symlink ayrıcalık ister ve Windows base paketinde symlink YOKTUR;
    // sessizce düz dosya yazmaktansa açıkça reddet.
    #[cfg(not(unix))]
    {
        Err(ExtractError::PathEscape(format!(
            "{raw_name}: bu platformda sembolik link desteklenmiyor"
        )))
    }
}

/// `base/target` sadeleştirildiğinde hâlâ `root` altında mı? (dosya sistemine dokunmaz)
fn stays_within(root: &Path, base: &Path, target: &Path) -> bool {
    let mut stack: Vec<Component> = base.components().collect();
    for comp in target.components() {
        match comp {
            Component::ParentDir => {
                if stack.pop().is_none() {
                    return false;
                }
            }
            Component::CurDir => {}
            other => stack.push(other),
        }
    }
    let resolved: PathBuf = stack.iter().collect();
    resolved.starts_with(root)
}

/// Hedefin gerçekten kökün altında kaldığını sembolik link çözümünden SONRA doğrular.
/// (Kurulum sonrası savunma; `dest` yoksa `true` döner.)
pub fn is_within(root: &Path, candidate: &Path) -> bool {
    let (Ok(root), Ok(cand)) = (root.canonicalize(), candidate.canonicalize()) else {
        return true;
    };
    cand.starts_with(root)
}


#[cfg(test)]
mod tests {
    use std::io::Write;

    use super::*;

    fn build_zip(entries: &[(&str, &[u8])]) -> (tempfile::TempDir, PathBuf) {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("a.zip");
        let f = fs::File::create(&path).unwrap();
        let mut w = zip::ZipWriter::new(f);
        let opts: zip::write::FileOptions<()> =
            zip::write::FileOptions::default().compression_method(zip::CompressionMethod::Deflated);
        for (name, data) in entries {
            w.start_file(*name, opts).unwrap();
            w.write_all(data).unwrap();
        }
        w.finish().unwrap();
        (dir, path)
    }

    #[test]
    fn normal_arsiv_acilir() {
        let (_d, zip_path) = build_zip(&[
            ("PEMF_Backend/PEMF_Backend", b"ELF" as &[u8]),
            ("PEMF_Backend/_internal/x.dat", b"data"),
        ]);
        let out = tempfile::tempdir().unwrap();
        let n = extract_zip(&zip_path, out.path()).unwrap();
        assert_eq!(n, 2);
        assert!(out.path().join("PEMF_Backend/PEMF_Backend").exists());
        assert!(out.path().join("PEMF_Backend/_internal/x.dat").exists());
    }

    /// ZIP-SLIP: `../` ile dışarı yazmaya çalışan arşiv REDDEDİLMELİ.
    #[test]
    fn zip_slip_reddedilir() {
        let (_d, zip_path) = build_zip(&[("../kotucul.txt", b"pwned" as &[u8])]);
        let out = tempfile::tempdir().unwrap();
        let err = extract_zip(&zip_path, out.path()).unwrap_err();
        assert!(matches!(err, ExtractError::PathEscape(_)));
        // Kurulum kökünün ÜSTÜNE hiçbir şey yazılmamış olmalı.
        assert!(!out.path().parent().unwrap().join("kotucul.txt").exists());
    }

    #[test]
    fn derin_zip_slip_de_reddedilir() {
        let (_d, zip_path) = build_zip(&[("a/b/../../../../etc/pemf_test", b"x" as &[u8])]);
        let out = tempfile::tempdir().unwrap();
        assert!(matches!(
            extract_zip(&zip_path, out.path()).unwrap_err(),
            ExtractError::PathEscape(_)
        ));
    }

    #[test]
    fn is_safe_relative_dogru_ayirir() {
        assert!(is_safe_relative(Path::new("a/b/c.txt")));
        assert!(!is_safe_relative(Path::new("../a")));
        assert!(!is_safe_relative(Path::new("/mutlak/yol")));
    }

    #[cfg(unix)]
    fn build_zip_with_symlink(link: &str, target: &str) -> (tempfile::TempDir, PathBuf) {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("s.zip");
        let f = fs::File::create(&path).unwrap();
        let mut w = zip::ZipWriter::new(f);
        // add_symlink GERÇEK symlink girdisi yazar (S_IFLNK). `unix_permissions(0o120777)`
        // yetmez — o yalnız izin bitlerini taşır, dosya TİPİNİ değil.
        let opts: zip::write::SimpleFileOptions = zip::write::FileOptions::default();
        w.add_symlink(link, target, opts).unwrap();
        w.finish().unwrap();
        (dir, path)
    }

    /// GERÇEK PAKET DAVRANIŞI: `_internal/Python` bir symlink. Düz dosya olarak
    /// yazılırsa dlopen "slice is not valid mach-o file" der ve backend HİÇ açılmaz.
    #[cfg(unix)]
    #[test]
    fn sembolik_link_link_olarak_acilir() {
        let (_d, zip_path) =
            build_zip_with_symlink("PEMF_Backend/_internal/Python", "Python.framework/Versions/3.10/Python");
        let out = tempfile::tempdir().unwrap();
        extract_zip(&zip_path, out.path()).unwrap();

        let link = out.path().join("PEMF_Backend/_internal/Python");
        let meta = fs::symlink_metadata(&link).unwrap();
        assert!(meta.file_type().is_symlink(), "duz dosya olarak yazilmis — backend acilmaz");
        assert_eq!(
            fs::read_link(&link).unwrap(),
            Path::new("Python.framework/Versions/3.10/Python")
        );
    }

    /// Symlink zip-slip'in ikinci yüzü: link kök altında ama HEDEFİ dışarıda.
    #[cfg(unix)]
    #[test]
    fn disari_cikan_symlink_reddedilir() {
        let (_d, zip_path) = build_zip_with_symlink("a/b/link", "../../../../etc/passwd");
        let out = tempfile::tempdir().unwrap();
        assert!(matches!(
            extract_zip(&zip_path, out.path()).unwrap_err(),
            ExtractError::PathEscape(_)
        ));
    }

    #[cfg(unix)]
    #[test]
    fn mutlak_hedefli_symlink_reddedilir() {
        let (_d, zip_path) = build_zip_with_symlink("link", "/etc/passwd");
        let out = tempfile::tempdir().unwrap();
        assert!(matches!(
            extract_zip(&zip_path, out.path()).unwrap_err(),
            ExtractError::PathEscape(_)
        ));
    }

    /// Kök içinde kalan `..` kullanımı MEŞRUDUR (ör. framework içi göreli linkler).
    #[cfg(unix)]
    #[test]
    fn kok_icinde_kalan_gorelilik_kabul_edilir() {
        let (_d, zip_path) = build_zip_with_symlink("a/b/link", "../c/real.dylib");
        let out = tempfile::tempdir().unwrap();
        extract_zip(&zip_path, out.path()).unwrap();
        assert!(fs::symlink_metadata(out.path().join("a/b/link")).unwrap().file_type().is_symlink());
    }

    #[test]
    fn stays_within_dogru_hesaplar() {
        let root = Path::new("/opt/app");
        assert!(stays_within(root, Path::new("/opt/app/a/b"), Path::new("../c")));
        assert!(stays_within(root, Path::new("/opt/app"), Path::new("x/y")));
        assert!(!stays_within(root, Path::new("/opt/app/a"), Path::new("../../escape")));
    }

    #[cfg(unix)]
    #[test]
    fn calistirma_biti_korunur() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("x.zip");
        let f = fs::File::create(&path).unwrap();
        let mut w = zip::ZipWriter::new(f);
        let opts: zip::write::FileOptions<()> = zip::write::FileOptions::default()
            .compression_method(zip::CompressionMethod::Deflated)
            .unix_permissions(0o755);
        w.start_file("PEMF_Backend", opts).unwrap();
        w.write_all(b"#!/bin/sh\n").unwrap();
        w.finish().unwrap();

        let out = tempfile::tempdir().unwrap();
        extract_zip(&path, out.path()).unwrap();
        use std::os::unix::fs::PermissionsExt;
        let mode = fs::metadata(out.path().join("PEMF_Backend")).unwrap().permissions().mode();
        assert_eq!(mode & 0o111, 0o111, "calistirma biti kaybolmus — backend baslatilamaz");
    }
}
