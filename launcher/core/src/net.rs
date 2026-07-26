//! İndirme katmanı — URL pinleme + SHA256 doğrulamalı indirme.
//!
//! Tehdit modeli: manifest ele geçerse (repo/hesap) saldırgan `url` alanını kendi
//! sunucusuna çevirip launcher'a keyfi kod indirtebilir. Bu yüzden şema HTTPS'e,
//! host da bilinen GitHub release sunucularına PİNLENİR.
//!
//! Liste `servers/update_manager.py::_ALLOWED_UPDATE_HOSTS` ile AYNI olmalı — backend
//! kendi OTA indirmesinde aynı korumayı uyguluyor; iki taraf ayrışırsa biri zayıf kalır.

use std::fs;
use std::io::{self, Read, Write};
use std::path::Path;

/// `update_manager.py::_ALLOWED_UPDATE_HOSTS` ile birebir.
pub const ALLOWED_HOSTS: &[&str] = &[
    "github.com",
    "codeload.github.com",
    "objects.githubusercontent.com",
    "release-assets.githubusercontent.com",
    "raw.githubusercontent.com",
];

/// Python tarafındaki `host.endswith(".githubusercontent.com")` gevşetmesi.
const ALLOWED_SUFFIX: &str = ".githubusercontent.com";

#[derive(Debug, thiserror::Error)]
pub enum NetError {
    #[error("URL çözümlenemedi: {0:?}")]
    Malformed(String),
    #[error("URL HTTPS değil — indirilmedi (güvenlik): {0}")]
    NotHttps(String),
    #[error("Host beklenen release sunucusu değil ({0}) — indirilmedi (güvenlik)")]
    HostNotAllowed(String),
    #[error("HTTP {status} — {url}")]
    HttpStatus { status: u16, url: String },
    #[error("ağ/dosya hatası: {0}")]
    Io(#[from] io::Error),
    #[error("indirme aktarımı başarısız: {0}")]
    Transport(String),
}

/// URL'yi şema + host bakımından doğrula. Kabul edilirse host'u döndürür.
pub fn validate_url(url: &str) -> Result<String, NetError> {
    let rest = url
        .strip_prefix("https://")
        .ok_or_else(|| {
            if url.starts_with("http://") {
                NetError::NotHttps(url.to_string())
            } else {
                NetError::Malformed(url.to_string())
            }
        })?;

    // authority = host[:port]  (yol/sorgu/parça öncesi)
    let authority = rest
        .split(['/', '?', '#'])
        .next()
        .filter(|a| !a.is_empty())
        .ok_or_else(|| NetError::Malformed(url.to_string()))?;

    // userinfo@host biçimi: "evil.com@github.com" gibi kafa karıştırıcı yazımlar
    // ayrıştırıcılar arasında farklı yorumlanabildiği için TAMAMEN reddedilir.
    if authority.contains('@') {
        return Err(NetError::Malformed(url.to_string()));
    }

    let host = authority.split(':').next().unwrap_or("").to_ascii_lowercase();
    if host.is_empty() {
        return Err(NetError::Malformed(url.to_string()));
    }

    let allowed =
        ALLOWED_HOSTS.contains(&host.as_str()) || host.ends_with(ALLOWED_SUFFIX);
    if !allowed {
        return Err(NetError::HostNotAllowed(host));
    }
    Ok(host)
}

/// İlerleme geri çağrımı: (inen_bayt, toplam_bayt_veya_0).
pub type ProgressFn<'a> = &'a mut dyn FnMut(u64, u64);

/// `url`'yi `dest`e indirir. Host pinlemesi UYGULANIR.
///
/// Doğrulama ÇAĞIRANIN sorumluluğu (`verify::verify_file`); burada ayrılmasının sebebi
/// önbellekten gelen dosyanın da aynı doğrulamadan geçmesi gerektiği.
pub fn download_to_file(
    url: &str,
    dest: &Path,
    expected_size: u64,
    progress: ProgressFn<'_>,
) -> Result<u64, NetError> {
    validate_url(url)?;

    let resp = ureq::get(url)
        .call()
        .map_err(|e| match e {
            ureq::Error::Status(status, _) => NetError::HttpStatus {
                status,
                url: url.to_string(),
            },
            other => NetError::Transport(other.to_string()),
        })?;

    let total = resp
        .header("Content-Length")
        .and_then(|v| v.parse::<u64>().ok())
        .unwrap_or(expected_size);

    if let Some(parent) = dest.parent() {
        fs::create_dir_all(parent)?;
    }
    // Yarım kalan indirmenin geçerli sanılmaması için ÖNCE .part'a yaz, bitince taşı.
    let part = dest.with_extension("part");
    let mut out = fs::File::create(&part)?;
    let mut reader = resp.into_reader();
    let mut buf = vec![0u8; 256 * 1024];
    let mut done: u64 = 0;

    loop {
        let n = reader.read(&mut buf)?;
        if n == 0 {
            break;
        }
        out.write_all(&buf[..n])?;
        done += n as u64;
        progress(done, total);
    }
    out.flush()?;
    drop(out);
    fs::rename(&part, dest)?;
    Ok(done)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn gercek_release_urlleri_kabul_edilir() {
        for u in [
            "https://github.com/mert61-python/pemf-update/releases/download/client-app-v1.8.0/base.zip",
            "https://objects.githubusercontent.com/x/y.zip",
            "https://raw.githubusercontent.com/mert61-python/pemf-update/exe/latest.json",
            "https://release-assets.githubusercontent.com/a/b.zip",
        ] {
            assert!(validate_url(u).is_ok(), "reddedildi: {u}");
        }
    }

    #[test]
    fn http_reddedilir() {
        let err = validate_url("http://github.com/x.zip").unwrap_err();
        assert!(matches!(err, NetError::NotHttps(_)));
    }

    #[test]
    fn yabanci_host_reddedilir() {
        let err = validate_url("https://evil.example.com/base.zip").unwrap_err();
        assert!(matches!(err, NetError::HostNotAllowed(_)));
    }

    /// Klasik atlatma: "github.com" ALT DİZİ olarak geçse de host o değildir.
    #[test]
    fn benzer_isimli_host_atlatamaz() {
        for u in [
            "https://github.com.evil.example/base.zip",
            "https://notgithub.com/base.zip",
            "https://evilgithubusercontent.com/base.zip",
        ] {
            assert!(
                matches!(validate_url(u), Err(NetError::HostNotAllowed(_))),
                "ATLATILDI: {u}"
            );
        }
    }

    /// userinfo hilesi: bazı ayrıştırıcılar host'u "github.com" sanır.
    #[test]
    fn userinfo_iceren_url_reddedilir() {
        assert!(validate_url("https://github.com@evil.example/x.zip").is_err());
        assert!(validate_url("https://evil.example@github.com/x.zip").is_err());
    }

    #[test]
    fn buyuk_harfli_host_normalize_edilir() {
        assert_eq!(validate_url("https://GitHub.COM/x.zip").unwrap(), "github.com");
    }

    #[test]
    fn port_iceren_url_hostu_dogru_ayirir() {
        assert_eq!(validate_url("https://github.com:443/x.zip").unwrap(), "github.com");
    }

    #[test]
    fn bozuk_url_reddedilir() {
        for u in ["", "github.com/x.zip", "https://", "ftp://github.com/x"] {
            assert!(validate_url(u).is_err(), "kabul edildi: {u:?}");
        }
    }

    /// manifest-local.json 127.0.0.1 kullanıyor (yerel yayın testi) — üretim
    /// akışında REDDEDİLMELİ; aksi halde pinleme anlamsızlaşır.
    #[test]
    fn yerel_test_urlsi_uretimde_reddedilir() {
        assert!(validate_url("http://127.0.0.1:8100/base.zip").is_err());
    }
}
