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
use std::time::Duration;

/// Bağlantı/okuma zaman aşımları: slowloris/asılı-uç indirmeyi süresiz askıya alamasın.
const CONNECT_TIMEOUT_S: u64 = 15;
const READ_TIMEOUT_S: u64 = 60;
/// Content-Length YOKSA mutlak indirme tavanı (disk-dolum DoS'a karşı). base.zip ~600MB +
/// ai_models ~2GB → 4 GB güvenli üst-sınır; meşru paket bunu aşmaz.
const MAX_DOWNLOAD_BYTES: u64 = 4 * 1024 * 1024 * 1024;

/// Zaman aşımlı + yalnız-HTTPS ajan. `https_only` HTTPS→HTTP downgrade redirect'ini reddeder;
/// redirect HEDEF host'u ayrıca download_to_file'da validate_url ile yeniden doğrulanır.
fn build_agent() -> ureq::Agent {
    ureq::AgentBuilder::new()
        .timeout_connect(Duration::from_secs(CONNECT_TIMEOUT_S))
        .timeout_read(Duration::from_secs(READ_TIMEOUT_S))
        .https_only(true)
        .build()
}

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
    /// Kullanıcı DURAKLATTI — `.part` KORUNUR, sonra Range ile kaldığı yerden sürer.
    #[error("indirme duraklatıldı")]
    Paused,
    /// Kullanıcı İPTAL etti — `.part` SİLİNİR.
    #[error("indirme iptal edildi")]
    Cancelled,
}

/// İndirme akış-kontrolü: her yığında kontrol edilir. `Continue` sürdürür, `Pause` `.part`'ı
/// koruyup durur (Range ile devam edilebilir), `Cancel` `.part`'ı silip durur.
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum Control {
    Continue,
    Pause,
    Cancel,
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

/// `url`'yi `dest`e indirir — RESUMABLE (kaldığı yerden). Host pinlemesi UYGULANIR.
///
/// Devam mantığı (Steam-benzeri): önce `.part`'a yazılır. `.part` varsa `Range: bytes=N-` ile
/// SUNUCUDAN kalan kısmı ister (206) ve APPEND eder → internet kesilse/laptop kapansa da
/// tekrar çağrıldığında baştan değil KALDIĞI YERDEN sürer. `.part` yarım kalırsa KORUNUR
/// (eski davranış: silinirdi). `control()` her yığında bakılır: Pause → `.part` kalır + `Paused`;
/// Cancel → `.part` silinir + `Cancelled`. Bütünlük ÇAĞIRANDA (`verify::verify_file`) SHA ile
/// denetlenir → yanlış-ofset/bozuk devam yakalanır ve `.zip` reddedilip taze inilir.
pub fn download_to_file(
    url: &str,
    dest: &Path,
    expected_size: u64,
    progress: ProgressFn<'_>,
    control: &dyn Fn() -> Control,
) -> Result<u64, NetError> {
    validate_url(url)?;
    if let Some(parent) = dest.parent() {
        fs::create_dir_all(parent)?;
    }
    let part = dest.with_extension("part");

    // Baştan Cancel istenmişse: yarım .part'ı temizle, hemen dön.
    if control() == Control::Cancel {
        let _ = fs::remove_file(&part);
        return Err(NetError::Cancelled);
    }

    // Devam noktası = mevcut .part boyutu. Beklenen boyuta eşit/aşkınsa şüpheli → sıfırla (416'dan kaçın).
    let mut done: u64 = fs::metadata(&part).map(|m| m.len()).unwrap_or(0);
    if expected_size > 0 && done >= expected_size {
        let _ = fs::remove_file(&part);
        done = 0;
    }

    let mut req = build_agent().get(url);
    if done > 0 {
        req = req.set("Range", &format!("bytes={done}-"));
    }
    let resp = req.call().map_err(|e| match e {
        ureq::Error::Status(status, _) => NetError::HttpStatus {
            status,
            url: url.to_string(),
        },
        other => NetError::Transport(other.to_string()),
    })?;

    // Redirect host-pin: SON URL'nin host'u allowlist içinde olmalı.
    validate_url(resp.get_url())?;

    // 206 = Partial (Range kabul, kaldığı yerden). 200 = sunucu Range'i yok saydı → BAŞTAN.
    let resuming = resp.status() == 206 && done > 0;
    if !resuming {
        done = 0;
    }
    let cl = resp
        .header("Content-Length")
        .and_then(|v| v.parse::<u64>().ok());
    // resuming ise Content-Length = KALAN; toplam = done + kalan. Değilse Content-Length = toplam.
    let total = if resuming {
        cl.map(|c| done + c).unwrap_or(expected_size)
    } else {
        cl.unwrap_or(expected_size)
    };
    let ceiling = if total > 0 {
        total.saturating_add(1 << 20)
    } else {
        MAX_DOWNLOAD_BYTES
    };

    // resuming → APPEND (mevcut baytları koru); değilse create (truncate = baştan).
    let mut out = if resuming {
        fs::OpenOptions::new().append(true).open(&part)?
    } else {
        fs::File::create(&part)?
    };
    let mut reader = resp.into_reader();
    let mut buf = vec![0u8; 256 * 1024];
    progress(done, total); // devam noktasını hemen bildir

    loop {
        match control() {
            Control::Pause => {
                let _ = out.flush(); // .part KORUNUR → sonra Range ile sürer
                return Err(NetError::Paused);
            }
            Control::Cancel => {
                drop(out);
                let _ = fs::remove_file(&part);
                return Err(NetError::Cancelled);
            }
            Control::Continue => {}
        }
        // Okuma hatası (internet kesildi) → `.part` KORUNUR (silinmez) → sonraki denemede devam.
        let n = reader.read(&mut buf)?;
        if n == 0 {
            break;
        }
        done += n as u64;
        if done > ceiling {
            return Err(NetError::Transport(format!(
                "indirme boyut sınırını aştı ({done} > {ceiling} bayt) — iptal edildi"
            )));
        }
        out.write_all(&buf[..n])?;
        progress(done, total);
    }
    out.flush()?;
    drop(out);
    fs::rename(&part, dest)?;
    Ok(done)
}

/// Küçük metin kaynağını (manifest) pinli + zaman-aşımlı indir. Host hem başlangıçta hem
/// redirect-sonrası doğrulanır; `into_string` ureq'te ~10MB'a kapalı (metin-DoS sınırı hazır).
pub fn fetch_string_pinned(url: &str) -> Result<String, NetError> {
    validate_url(url)?;
    let resp = build_agent()
        .get(url)
        .call()
        .map_err(|e| match e {
            ureq::Error::Status(status, _) => NetError::HttpStatus {
                status,
                url: url.to_string(),
            },
            other => NetError::Transport(other.to_string()),
        })?;
    validate_url(resp.get_url())?;
    resp.into_string().map_err(NetError::from)
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
