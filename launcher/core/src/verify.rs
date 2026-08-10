// Author: mertaygn, cglrgrkn
//! SHA256 doğrulama — akış halinde (gigabaytlık paketler belleğe alınmaz).

use std::fs::File;
use std::io::{self, Read};
use std::path::Path;

use sha2::{Digest, Sha256};

#[derive(Debug, thiserror::Error)]
pub enum VerifyError {
    #[error("dosya okunamadı: {0}")]
    Io(#[from] io::Error),
    #[error(
        "SHA256 UYUŞMADI — dosya bozuk ya da değiştirilmiş. beklenen={expected} gerçek={actual}"
    )]
    Mismatch { expected: String, actual: String },
}

/// Dosyanın SHA256'sını hex olarak döndür.
pub fn sha256_file(path: &Path) -> Result<String, VerifyError> {
    let mut file = File::open(path)?;
    let mut hasher = Sha256::new();
    // 1 MiB tampon: 1.5 GB'lık research.zip için de sabit bellek.
    let mut buf = vec![0u8; 1024 * 1024];
    loop {
        let n = file.read(&mut buf)?;
        if n == 0 {
            break;
        }
        hasher.update(&buf[..n]);
    }
    Ok(hex(&hasher.finalize()))
}

/// Beklenen digest ile karşılaştır. Uyuşmazsa hata — çağıran dosyayı SİLMELİ.
pub fn verify_file(path: &Path, expected: &str) -> Result<(), VerifyError> {
    let actual = sha256_file(path)?;
    // Büyük/küçük harf farkı manifest yazımına göre değişebilir; kıyas normalize edilir.
    if actual.eq_ignore_ascii_case(expected) {
        Ok(())
    } else {
        Err(VerifyError::Mismatch {
            expected: expected.to_ascii_lowercase(),
            actual,
        })
    }
}

fn hex(bytes: &[u8]) -> String {
    use std::fmt::Write;
    bytes.iter().fold(String::with_capacity(64), |mut s, b| {
        let _ = write!(s, "{b:02x}");
        s
    })
}

#[cfg(test)]
mod tests {
    use std::io::Write;

    use super::*;

    fn tmp_with(content: &[u8]) -> (tempfile::TempDir, std::path::PathBuf) {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("f.bin");
        File::create(&path).unwrap().write_all(content).unwrap();
        (dir, path)
    }

    #[test]
    fn bos_dosya_bilinen_digest() {
        let (_d, p) = tmp_with(b"");
        assert_eq!(
            sha256_file(&p).unwrap(),
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        );
    }

    #[test]
    fn abc_bilinen_digest() {
        let (_d, p) = tmp_with(b"abc");
        assert_eq!(
            sha256_file(&p).unwrap(),
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
        );
    }

    #[test]
    fn buyuk_harfli_beklenen_deger_kabul_edilir() {
        let (_d, p) = tmp_with(b"abc");
        let upper = "BA7816BF8F01CFEA414140DE5DAE2223B00361A396177A9CB410FF61F20015AD";
        assert!(verify_file(&p, upper).is_ok());
    }

    #[test]
    fn yanlis_digest_hata_verir() {
        let (_d, p) = tmp_with(b"abc");
        let err = verify_file(&p, &"0".repeat(64)).unwrap_err();
        assert!(matches!(err, VerifyError::Mismatch { .. }));
    }

    /// 1 MiB tamponun sınırında (çok-bloklu okuma) doğru çalışmalı.
    #[test]
    fn cok_bloklu_dosya_dogru_hesaplanir() {
        let big = vec![7u8; 1024 * 1024 * 2 + 12345];
        let (_d, p) = tmp_with(&big);
        let mut h = Sha256::new();
        h.update(&big);
        assert_eq!(sha256_file(&p).unwrap(), hex(&h.finalize()));
    }
}
