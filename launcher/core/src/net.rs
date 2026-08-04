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
use std::time::{Duration, Instant};

/// Bağlantı/okuma zaman aşımları: slowloris/asılı-uç indirmeyi süresiz askıya alamasın.
const CONNECT_TIMEOUT_S: u64 = 15;
const READ_TIMEOUT_S: u64 = 60;
/// Content-Length YOKSA mutlak indirme tavanı (disk-dolum DoS'a karşı). base.zip ~600MB +
/// ai_models ~2GB → 4 GB güvenli üst-sınır; meşru paket bunu aşmaz.
const MAX_DOWNLOAD_BYTES: u64 = 4 * 1024 * 1024 * 1024;
/// TEK bir indirme denemesi için KÜRESEL süre tavanı.
///
/// DENETİM 2026-08-04: `timeout_read` ureq'te HER SOKET OKUMASINA ayrı uygulanır, toplam transfere
/// DEĞİL. Modül başlığı "slowloris/asılı-uç indirmeyi süresiz askıya alamasın" diyordu ama slowloris
/// tam olarak bu modelde çalışır: 59 saniyede bir 1 bayt gönderen sunucu HİÇBİR ZAMAN zaman aşımına
/// uğramaz, `reader.read` daima n>0 döner, döngü ilerler ve `progress` artan değer bildirir — hata
/// oluşmadığı için flow.rs'teki yeniden-deneme de devreye girmez. Kurulum SONSUZA KADAR asılı kalır.
/// 6 saat: 2 GB'lık research.zip bile ~1 Mbps'te ~4.5 saatte iner → meşru klinik hattını kesmez.
const MAX_DOWNLOAD_DURATION_S: u64 = 6 * 60 * 60;

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
///
/// ⚠️ Bu joker YALNIZCA **redirect hedefleri** için geçerlidir (GitHub kendi CDN'ine yönlendirir
/// ve alt alan adı zamanla değişebilir). Manifest'ten gelen **KAYNAK** URL'ler için değil —
/// bkz. `validate_download_source`.
const ALLOWED_SUFFIX: &str = ".githubusercontent.com";

/// Sürüm varlıklarının yayınlandığı repo. `github.com` yolu buna PİNLENİR.
/// (`launcher/app/src/main.rs::MANIFEST_URL` ile aynı repo — ayrışırsa pin anlamsızlaşır.)
const UPDATE_REPO_PATH: &str = "/mert61-python/pemf-update/";

/// KAYNAK (manifest'ten gelen) URL doğrulaması — `validate_url`'den DAHA KATI.
///
/// DENETİM 2026-08-04 (#97/#99): host-pin'i yalnızca "GitHub'da bir yer" anlamına geliyordu:
///   • `github.com` için YOL kontrolü yoktu → `github.com/<saldirgan>/<repo>/releases/download/...`
///     kabul ediliyordu (Python ikizi `update_manager.py` bu daraltmayı YAPIYOR — parite kırıktı).
///   • `.githubusercontent.com` JOKERİ `raw.githubusercontent.com/<herhangi-hesap>/<repo>/…`
///     adresini de kabul ediyordu; oraya ÜCRETSİZ bir GitHub hesabı keyfi bayt koyabilir.
/// Bu URL'ler yalnız indirme değil, `apply_self_update`'in de girdisidir: imzasız setup.exe
/// indirilip `/S` ile SESSİZCE kurulur ve SHA da AYNI manifest'ten gelir (orijinallik kanıtlamaz).
///
/// Artık kaynak URL: ya repo-yolu pinli `github.com`, ya da AÇIKÇA sayılmış nesne-depoları.
/// Joker sonek burada KABUL EDİLMEZ (redirect'lerde hâlâ geçerli — GitHub CDN'i oraya yönlendirir).
pub fn validate_download_source(url: &str) -> Result<String, NetError> {
    let host = validate_url(url)?;
    if host == "github.com" {
        // https://github.com<path…> — authority'den sonrası yol.
        let rest = url.strip_prefix("https://").unwrap_or(url);
        let path_start = rest.find(['/', '?', '#']).unwrap_or(rest.len());
        let path = &rest[path_start..];
        if !path.starts_with(UPDATE_REPO_PATH) {
            return Err(NetError::HostNotAllowed(format!(
                "github.com{} — beklenen repo {UPDATE_REPO_PATH}",
                path.split("/releases").next().unwrap_or(path)
            )));
        }
        return Ok(host);
    }
    // github.com değilse: AÇIKÇA listelenmiş olmalı; joker sonek kaynak URL için YETMEZ.
    if ALLOWED_HOSTS.contains(&host.as_str()) {
        Ok(host)
    } else {
        Err(NetError::HostNotAllowed(host))
    }
}

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

/// `Content-Range: bytes <start>-<end>/<total>` değerindeki BAŞLANGIÇ ofsetini çıkar.
/// Biçim tanınmazsa `None` — çağıran bunu "doğrulanamadı" sayıp devam ettirmez (fail-closed).
/// (Saf fonksiyon: `ureq::Response` kurmadan birim-test edilebilsin diye ayrıldı.)
fn parse_content_range_start(value: &str) -> Option<u64> {
    let v = value.trim().to_ascii_lowercase();
    let rest = v.strip_prefix("bytes")?.trim_start();
    rest.split(['-', '/']).next()?.trim().parse::<u64>().ok()
}

fn content_range_start(resp: &ureq::Response) -> Option<u64> {
    parse_content_range_start(resp.header("Content-Range")?)
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
    expected_sha: &str,
    progress: ProgressFn<'_>,
    control: &dyn Fn() -> Control,
) -> Result<u64, NetError> {
    // KAYNAK URL: repo-yolu pinli (bkz. validate_download_source). Redirect HEDEFİ aşağıda
    // daha gevşek `validate_url` ile doğrulanır — GitHub kendi CDN'ine yönlendirir.
    validate_download_source(url)?;
    if let Some(parent) = dest.parent() {
        fs::create_dir_all(parent)?;
    }
    // ⚠️ DENETİM 2026-08-04 (#95): `.part`'ın HANGİ İÇERİĞE ait olduğu hiçbir yerde kayıtlı
    // değildi ve adı yalnız URL'nin son parçasından türüyordu — bu projede SABİTTİR: manifest
    // hep `client-app-v1.8.0/base.zip` etiketine işaret eder ve yayın akışı asset'i AYNI URL
    // üzerine `--clobber` ile YENİDEN yükler. Sonuç: eski sürümün yarım `.part`'ı, YENİ sürümün
    // içeriği için geçerli bir devam noktası sanılıyor → `Range` ile üstüne eklenip MELEZ dosya
    // oluşuyor. SHA bunu yakalar ama gigabaytlarca trafik boşa gider ve kullanıcı sahte bir
    // "kurcalanma" hatası görür. Çözüm: `.part` adını beklenen SHA'ya bağla — farklı içerik
    // farklı `.part` demektir; TAMAMLANMIŞ önbellek (`dest`) ADI DEĞİŞMEDİĞİ için korunur.
    let part = if expected_sha.len() >= 12 {
        dest.with_extension(format!("{}.part", expected_sha[..12].to_ascii_lowercase()))
    } else {
        dest.with_extension("part")
    };

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

    // DENETİM 2026-08-04: 206 durum kodu TEK BAŞINA yeterli sayılıyordu; `Content-Range` başlığı
    // ne okunuyor ne de istenen ofsetle karşılaştırılıyordu. RFC'ye göre 206 dönen bir sunucu ya da
    // ara-vekil İSTENENDEN FARKLI bir aralık (hatta 0'dan itibaren tam gövde) dönebilir — CDN'ler,
    // şeffaf vekiller ve kurumsal proxy'ler bunu pratikte yapar. Kod ise dosyayı APPEND modunda açıp
    // gelen baytları körlemesine SONA ekliyordu → ilk `done` baytı ESKİ indirmeden, gerisi YENİ
    // aralıktan olan MELEZ dosya. (SHA sonunda yakalar ama gigabaytlarca trafik boşa gider ve
    // kullanıcı sahte bir "kurcalanma" hatası görür.) Artık ofset DOĞRULANIR.
    if resp.status() == 206 && done > 0 {
        let got = content_range_start(&resp);
        if got != Some(done) {
            let _ = fs::remove_file(&part); // bozuk devam noktası → bir sonraki deneme SIFIRDAN
            return Err(NetError::Transport(format!(
                "sunucu istenen aralığı vermedi (beklenen ofset {done}, gelen {got:?}) — .part sıfırlandı"
            )));
        }
    }

    // 206 = Partial (Range kabul edildi VE ofset doğrulandı). 200 = sunucu Range'i yok saydı → BAŞTAN.
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
    // DENETİM 2026-08-04 (#94): tavan ÖNCE sunucunun Content-Length'inden hesaplanıyordu ve
    // `MAX_DOWNLOAD_BYTES` (4 GB) YALNIZCA `total == 0` dalında devreye giriyordu → "disk-dolum
    // DoS'a karşı MUTLAK tavan" diye belgelenen sabit, sunucunun TEK BİR BAŞLIK göndermesiyle
    // tamamen devre dışı kalıyordu (Content-Length: 100 GB → 100 GB yazılırdı). Ayrıca manifest'in
    // kendi `size` alanıyla hiçbir çapraz kontrol yoktu.
    // Artık: sunucu tavanı ile manifest boyutunun KÜÇÜĞÜ alınır ve her hâlükârda
    // MAX_DOWNLOAD_BYTES'ı AŞAMAZ.
    let declared = if total > 0 { total } else { MAX_DOWNLOAD_BYTES };
    let manifest_cap = if expected_size > 0 {
        expected_size.saturating_add(1 << 20)
    } else {
        u64::MAX
    };
    let ceiling = declared
        .saturating_add(1 << 20)
        .min(manifest_cap)
        .min(MAX_DOWNLOAD_BYTES);

    // resuming → APPEND (mevcut baytları koru); değilse create (truncate = baştan).
    let mut out = if resuming {
        fs::OpenOptions::new().append(true).open(&part)?
    } else {
        fs::File::create(&part)?
    };
    let mut reader = resp.into_reader();
    let mut buf = vec![0u8; 256 * 1024];
    progress(done, total); // devam noktasını hemen bildir
    let started = Instant::now(); // küresel süre tavanı (bkz. MAX_DOWNLOAD_DURATION_S)

    loop {
        // Slowloris koruması: sunucu sürekli AZ ama SIFIR-OLMAYAN veri gönderirse hiçbir okuma
        // zaman aşımına uğramaz. Duraklat/İptal'de `.part` korunur, saat sonraki denemede sıfırlanır.
        if started.elapsed() > Duration::from_secs(MAX_DOWNLOAD_DURATION_S) {
            let _ = out.flush(); // `.part` KORUNUR → sonraki deneme Range ile sürer
            return Err(NetError::Transport(format!(
                "indirme küresel süre sınırını aştı ({MAX_DOWNLOAD_DURATION_S} sn) — iptal edildi"
            )));
        }
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
    validate_download_source(url)?;
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

    /// DENETİM 2026-08-04 (#97/#99): KAYNAK URL'ler repo-yolu pinli olmalı; joker
    /// `.githubusercontent.com` soneki kaynak için YETMEZ (redirect'te hâlâ geçerli).
    #[test]
    fn kaynak_url_repo_yoluna_pinli() {
        // ── GERÇEK yayın URL'leri GEÇMELİ (aksi halde tüm indirmeler kırılır) ──
        for u in [
            "https://github.com/mert61-python/pemf-update/releases/download/client-app-v1.8.0/base.zip",
            "https://github.com/mert61-python/pemf-update/releases/download/client-app-v1.8.0/vet.zip",
            "https://github.com/mert61-python/pemf-update/releases/download/launcher-v1.9.8/PEMFVetClient-Setup.exe",
            "https://github.com/mert61-python/pemf-update/releases/download/client-app-v1.8.0/manifest.json",
            // Nesne-depoları AÇIKÇA listeli → kaynak olarak da kabul.
            "https://objects.githubusercontent.com/x/y.zip",
            "https://release-assets.githubusercontent.com/a/b.zip",
        ] {
            assert!(validate_download_source(u).is_ok(), "GERCEK yayin URL'si reddedildi: {u}");
        }

        // ── BAŞKA repo → REDDET (eskiden geçiyordu; Python ikizi zaten reddediyordu) ──
        for u in [
            "https://github.com/saldirgan/pemf-update/releases/download/v1/evil.exe",
            "https://github.com/mert61-python/baska-repo/releases/download/v1/evil.exe",
            "https://github.com/evil.exe",
        ] {
            assert!(
                matches!(validate_download_source(u), Err(NetError::HostNotAllowed(_))),
                "BASKA repo KAYNAK olarak kabul edildi: {u}"
            );
        }

        // ── Joker sonek KAYNAK için yetmez: raw.* AÇIKÇA listeli olduğu için geçer, ama
        //    listelenmemiş bir *.githubusercontent.com alt alanı KAYNAK olarak REDDEDİLİR.
        assert!(validate_download_source("https://gist.githubusercontent.com/x/y/evil.exe").is_err());
        // Aynı URL redirect HEDEFİ olarak hâlâ kabul edilir (GitHub CDN'i değişebilir).
        assert!(validate_url("https://gist.githubusercontent.com/x/y/evil.exe").is_ok());
    }

    /// DENETİM 2026-08-04 (#95): `.part` adı yalnız URL'den türüyordu ve bu projede SABİT
    /// (`--clobber` ile aynı URL'e yeniden yayın). Eski sürümün yarım `.part`'ı YENİ içerik için
    /// "devam noktası" sanılıp `Range` ile üstüne ekleniyordu → MELEZ dosya + sahte kurcalanma
    /// alarmı + gigabaytlarca boşa trafik. Ad artık beklenen SHA'ya bağlı.
    #[test]
    fn part_dosyasi_beklenen_shaya_bagli() {
        // Saf ad hesabı — ağ gerekmez (download_to_file içindeki mantığın aynısı).
        fn part_of(dest: &Path, sha: &str) -> std::path::PathBuf {
            if sha.len() >= 12 {
                dest.with_extension(format!("{}.part", sha[..12].to_ascii_lowercase()))
            } else {
                dest.with_extension("part")
            }
        }
        let dest = Path::new("C:/cache/base.zip");
        let a = part_of(dest, "387aa4076bc3e52c03dbe7cff5502146984000c7c0ba9d7405e004e416cef448");
        let b = part_of(dest, "1b49fd93454c4ce558edde8cc345eb3e4aec673167033000e19dd42106aeaf53");
        assert_ne!(a, b, "FARKLI icerik AYNI .part adini paylasiyor (melez dosya riski)");
        assert!(a.to_string_lossy().contains("387aa4076bc3"));

        // `install::clear_partials` `extension() == "part"` ile temizler → ad değişse de bulunmalı.
        assert_eq!(a.extension().unwrap(), "part");

        // sha yoksa (eski/eksik manifest) eski davranışa düş — kırılma yok.
        assert_eq!(part_of(dest, "").extension().unwrap(), "part");
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

    /// DENETİM 2026-08-04: 206 yanıtında `Content-Range` HİÇ doğrulanmıyordu → sunucu/vekil farklı
    /// bir aralık dönerse baytlar körlemesine APPEND edilip MELEZ dosya oluşuyordu.
    #[test]
    fn content_range_baslangic_ofseti_dogru_ayristirilir() {
        assert_eq!(parse_content_range_start("bytes 1024-2047/4096"), Some(1024));
        assert_eq!(parse_content_range_start("bytes 0-99/100"), Some(0));
        // Büyük/küçük harf ve fazladan boşluk toleransı (RFC'ye uymayan sunucular).
        assert_eq!(parse_content_range_start("  BYTES   500-999/1000 "), Some(500));
        // Toplam bilinmiyor (`*`) ama başlangıç var → yine okunmalı.
        assert_eq!(parse_content_range_start("bytes 42-99/*"), Some(42));

        // FAIL-CLOSED: tanınmayan biçim → None (çağıran devam ETTİRMEZ).
        assert_eq!(parse_content_range_start("items 0-10/20"), None);
        assert_eq!(parse_content_range_start("bytes */4096"), None);
        assert_eq!(parse_content_range_start(""), None);
        assert_eq!(parse_content_range_start("bytes abc-def/1"), None);
    }
}
