// Author: mertaygn, cglrgrkn
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
use std::path::{Path, PathBuf};
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

// ── Küçük METİN kaynakları (manifest) için AYRI ve KISA bütçe ────────────────────────────────
//
// ⚠️ DENETİM 2026-08-06 (P0 — OFFLINE BOOT KİLİDİ): manifest, GİGABAYTLIK paketlerle AYNI ajanı
// kullanıyordu (connect 15 sn / read 60 sn, KÜRESEL sınır YOK). Klinik senaryosunda (PEMF-Gateway
// hotspot'una bağlı ama upstream yok, ya da captive portal) bu, açılışı süresiz askıya alıyordu:
// `timeout_read` ureq'te HER OKUMAYA ayrı uygulanır, toplam isteğe DEĞİL → 59 saniyede bir bayt
// akıtan bir portal isteği hiç bitirmez. Manifest ~birkaç KB'lık bir metindir; 600 MB'lık base.zip
// için doğru olan bütçe onun için ÇOK uzundur. Ayrı, kısa ve KÜRESEL sınırlı bir ajan kullanıyoruz.
const TEXT_CONNECT_TIMEOUT_S: u64 = 5;
const TEXT_READ_TIMEOUT_S: u64 = 10;
/// ureq `AgentBuilder::timeout` = isteğin TAMAMI için küresel sınır (bugüne kadar HİÇ yoktu;
/// slowloris'i kesen tek şey budur).
const TEXT_TOTAL_TIMEOUT_S: u64 = 8;

/// Manifest çekiminin UI'yı bekletebileceği MUTLAK süre (duvar saati).
///
/// Neden ureq zaman aşımları YETMİYOR: ureq DNS çözümlemesine hiçbir deadline uygulayamıyor
/// (kütüphanenin kendi kaynağındaki `// TODO: Find a way to apply deadline to DNS lookup`,
/// ureq-2.12.1/src/stream.rs). Upstream'i olmayan bir hotspot'ta `getaddrinfo` onlarca saniye
/// asılabilir. Bu yüzden ikinci kemer: iş AYRI bir thread'e verilir ve bu süre dolunca çağıran
/// "çevrimdışı" sayıp DEVAM EDER (thread arkada kendi zaman aşımıyla ölür — sızıntı değil, gecikme).
/// Manifest çekiminin duvar-saati tavanı.
///
/// ⚠️ 2026-08-12'de 10 → 20 sn. Sebep: çekim artık geçici kopmada 3 kez deneniyor
/// (bkz. `MANIFEST_DENEME`) ve YAVAŞ ama ÇALIŞAN bir hatta (ölçüm: 2,6 sn/istek) üç deneme
/// 10 sn'ye sığmıyordu — bütçe, düzelmekte olan bağlantıyı keserdi.
/// Çevrimdışı makineyi GECİKTİRMEZ: rota/DNS yokken bağlantı <1 sn'de düşer, üç deneme
/// toplamı ~2 sn'dir. Tavanın koruduğu asıl durum ASILI kalan bağlantıdır; o hâlâ bağlı.
pub const TEXT_WALL_BUDGET_S: u64 = 20;

fn build_text_agent() -> ureq::Agent {
    ureq::AgentBuilder::new()
        .timeout_connect(Duration::from_secs(TEXT_CONNECT_TIMEOUT_S))
        .timeout_read(Duration::from_secs(TEXT_READ_TIMEOUT_S))
        .timeout(Duration::from_secs(TEXT_TOTAL_TIMEOUT_S))
        .https_only(true)
        .build()
}

/// Bloklayan bir ağ işini DUVAR SAATİ bütçesine bağla: bütçe dolarsa çağıran serbest kalır.
///
/// Saf karar mantığı (ağ gerektirmez → doğrudan birim-testlenebilir). İş thread'i `detach`
/// edilir: onu güvenle iptal etmenin taşınabilir bir yolu yok, ama kendi ureq zaman aşımlarıyla
/// en geç birkaç saniye sonra kendiliğinden biter. Kritik olan, ÇAĞIRANIN bütçe dolar dolmaz
/// yoluna devam edebilmesidir (client açılışı ağ yüzünden kilitlenmesin).
pub fn with_wall_budget<T, F>(budget: Duration, etiket: &str, f: F) -> Result<T, NetError>
where
    F: FnOnce() -> Result<T, NetError> + Send + 'static,
    T: Send + 'static,
{
    let (tx, rx) = std::sync::mpsc::channel();
    std::thread::spawn(move || {
        // Alıcı bütçeyi aşıp gittiyse `send` hata verir — sessizce yut (thread yalnız sonlanır).
        let _ = tx.send(f());
    });
    match rx.recv_timeout(budget) {
        Ok(r) => r,
        Err(std::sync::mpsc::RecvTimeoutError::Timeout) => Err(NetError::PolicyLimit(format!(
            "{etiket}: {} sn içinde yanıt gelmedi — çevrimdışı sayıldı",
            budget.as_secs()
        ))),
        // Gönderen thread panikledi → kanal koptu. Bunu "geçici aktarım hatası" say.
        Err(std::sync::mpsc::RecvTimeoutError::Disconnected) => {
            Err(NetError::Transport(format!("{etiket}: ağ görevi beklenmedik şekilde sonlandı")))
        }
    }
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

/// URL yolu, istemci-tarafı normalizasyonuyla BİZİM gördüğümüz metni ayrıştıracak bir yazım
/// içeriyor mu? (nokta-segmenti, yüzde-kodlu nokta/ayraç, ters-eğik, boş segment)
///
/// Bunlar meşru release-asset URL'lerinde ASLA bulunmaz; varlıkları tek başına şüphelidir.
/// Sorgu/parça (`?`/`#`) segment analizine dahil edilmez — pin yalnız YOL için anlamlıdır.
fn path_has_traversal(path_with_query: &str) -> bool {
    let path = path_with_query
        .split(['?', '#'])
        .next()
        .unwrap_or(path_with_query);
    let low = path.to_ascii_lowercase();
    // %2e = '.', %2f = '/', %5c = '\' → normalize eden istemci bunları çözüp yolu değiştirebilir.
    if low.contains("%2e") || low.contains("%2f") || low.contains("%5c") || path.contains('\\') {
        return true;
    }
    // Baştaki '/' yüzünden ilk parça daima boştur; onu atla.
    path.split('/')
        .skip(1)
        .any(|seg| seg == "." || seg == ".." || seg.is_empty())
}

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
        // ⚠️ DENETİM 2026-08-04 (P0 — BU DÜZELTMENİN KENDİ AÇIĞI): repo-yolu pini HAM METİN
        // üzerinde `starts_with` ile çalışıyordu, oysa ureq isteği göndermeden ÖNCE yolu
        // RFC 3986 "remove_dot_segments" kuralıyla NORMALİZE eder. Yani pinin gördüğü metin ile
        // sunucuya giden yol AYNI DEĞİL. Yerel bir sunucuya gerçek ureq isteğiyle ölçüldü:
        //   URL : /mert61-python/pemf-update/../../saldirgan/kotu/evil.exe
        //   GİDEN: GET /saldirgan/kotu/evil.exe
        // Zehirli bir manifest (pinin tam olarak savunduğu tehdit) böyle bir URL vererek pini
        // TAMAMEN atlatır; sha da aynı manifest'ten geldiği için doğrulama geçer ve
        // `apply_self_update` imzasız setup.exe'yi `/S` ile SESSİZCE kurar.
        // Çözüm: normalize edenle bizim aramızda AYRIŞMA üreten her yazımı REDDET.
        if path_has_traversal(path) {
            return Err(NetError::HostNotAllowed(format!(
                "github.com{} — yol nokta-segmenti/kodlanmış ayraç içeriyor (pin atlatma)",
                path.split("/releases").next().unwrap_or(path)
            )));
        }
        if !path.starts_with(UPDATE_REPO_PATH) {
            return Err(NetError::HostNotAllowed(format!(
                "github.com{} — beklenen repo {UPDATE_REPO_PATH}",
                path.split("/releases").next().unwrap_or(path)
            )));
        }
        return Ok(host);
    }
    // ⚠️ DENETİM 2026-08-04 (P2 — YANLIŞ GÜVENCE): burada `ALLOWED_HOSTS` kullanılıyordu ve o
    // liste `raw.githubusercontent.com` ile `codeload.github.com`'u da içeriyor. Bu ikisinde YOL
    // kontrolü yapılmadığı için `raw.githubusercontent.com/<saldirgan>/<repo>/main/base.zip`
    // KAYNAK olarak kabul ediliyordu — yani fonksiyonun kendi yorumunun "kapattım" dediği saldırı
    // açıktı. İkisi de ücretsiz bir GitHub hesabıyla tamamen saldırgan-kontrollü bayt sunar.
    // Yayındaki manifest yalnızca `github.com/mert61-python/pemf-update/releases/...` kullanıyor
    // (doğrulandı) → kaynak allowlist'i OPAK NESNE DEPOLARIYLA sınırlandırıldı. Bu ikisi
    // REDIRECT hedefi olarak hâlâ geçerli (`validate_url` değişmedi) — GitHub CDN'i oraya yönlendirir.
    if SOURCE_OBJECT_HOSTS.contains(&host.as_str()) {
        Ok(host)
    } else {
        Err(NetError::HostNotAllowed(host))
    }
}

/// KAYNAK URL'lerinde kabul edilen OPAK nesne-depoları. GitHub bu adreslerde yolu kendisi
/// üretir (imzalı, geçici) → yol-pini uygulanamaz; koruma SHA256'dır. `raw.githubusercontent.com`
/// ve `codeload.github.com` BİLEREK YOK: oralarda yol `<sahip>/<repo>/...` biçimindedir ve
/// herkes kendi deposundan içerik sunabilir (bkz. validate_download_source notu).
const SOURCE_OBJECT_HOSTS: &[&str] = &[
    "objects.githubusercontent.com",
    "release-assets.githubusercontent.com",
];

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
    /// ⚠️ DENETİM 2026-08-04 (P2): boyut tavanı / küresel süre aşımı gibi DETERMİNİSTİK politika
    /// iptalleri eskiden `Transport` olarak dönüyordu; `flow::is_retriable` `Transport`'u koşulsuz
    /// GEÇİCİ saydığı için aynı hata 6 kez TAM YENİDEN İNDİRME tetikliyordu (klinik hattında
    /// gigabaytlarca boşuna trafik ve dakikalarca donma). Bunlar yeniden denemeyle DÜZELMEZ.
    #[error("indirme politika sınırı: {0}")]
    PolicyLimit(String),
    /// ⚠️ DENETİM 2026-08-23 (C8): YEREL dosya-sistemi hatası — `Io`dan AYRI tutulur.
    ///
    /// `download_to_file` içindeki yerel işlemler (`create_dir_all`, `File::create`, `write_all`,
    /// ve özellikle son adımdaki `fs::rename`) `io::Error` üretiyor ve hepsi `Io`ya düşüyordu;
    /// `flow::is_retriable` ise `Io`yu koşulsuz GEÇİCİ sayıyor. Sonuç: AV taraması ya da
    /// "sharing violation" (os error 32) yüzünden düşen tek bir `rename`, `ensure_package`'ı 6
    /// denemeye sokuyordu — ve her denemede TAMAMLANMIŞ `.part` silinip 1,19 GB'lık katman
    /// SIFIRDAN iniyordu (klinik hattında ~7 GB boşuna trafik, dakikalarca donma, sonunda yine
    /// aynı hata). Bunlar yeniden denemeyle DÜZELMEZ: disk dolu dolu kalır, kilit kilitli kalır.
    ///
    /// 2026-08-04'te `PolicyLimit` için kapatılan sınıfın aynısı, bir katman aşağıda.
    #[error("yerel dosya hatası: {0}")]
    LocalIo(String),
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

/// Yarım indirmenin (`.part`) yolu — ad BEKLENEN SHA'ya bağlıdır (bkz. `download_to_file`).
///
/// ⚠️ TEK KAYNAK. Bu hesap `flow.rs`te de gerekiyor (sha uyuşmazlığından sonra temiz yeniden
/// indirme yaparken `.part` SİLİNMELİ; kalırsa "temiz" deneme yine Range ile aynı bozuk
/// baytların üzerine ekler ve kaçınılmaz olarak yine başarısız olur). İki yerde ayrı ayrı
/// hesaplanırsa sessizce ayrışır: kısa sha kolunda adlar farklı çıkar ve YANLIŞ dosya silinir.
pub fn part_path(dest: &Path, expected_sha: &str) -> PathBuf {
    if expected_sha.len() >= 12 {
        dest.with_extension(format!("{}.part", expected_sha[..12].to_ascii_lowercase()))
    } else {
        dest.with_extension("part")
    }
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
        fs::create_dir_all(parent)
            .map_err(|e| NetError::LocalIo(format!("{} oluşturulamadı: {e}", parent.display())))?;
    }
    // ⚠️ DENETİM 2026-08-04 (#95): `.part`'ın HANGİ İÇERİĞE ait olduğu hiçbir yerde kayıtlı
    // değildi ve adı yalnız URL'nin son parçasından türüyordu — bu projede SABİTTİR: manifest
    // hep `client-app-v1.8.0/base.zip` etiketine işaret eder ve yayın akışı asset'i AYNI URL
    // üzerine `--clobber` ile YENİDEN yükler. Sonuç: eski sürümün yarım `.part`'ı, YENİ sürümün
    // içeriği için geçerli bir devam noktası sanılıyor → `Range` ile üstüne eklenip MELEZ dosya
    // oluşuyor. SHA bunu yakalar ama gigabaytlarca trafik boşa gider ve kullanıcı sahte bir
    // "kurcalanma" hatası görür. Çözüm: `.part` adını beklenen SHA'ya bağla — farklı içerik
    // farklı `.part` demektir; TAMAMLANMIŞ önbellek (`dest`) ADI DEĞİŞMEDİĞİ için korunur.
    // ⚠️ DENETİM 2026-08-04 (P3): `.part` adını sha'ya bağlamak, sha DEĞİŞTİĞİNDE (yeni sürüm
    // yayını) eski yarım indirmeyi KALICI YETİM dosyaya çeviriyor — `install::clear_partials`
    // yalnız AÇIK iptalde koşar, normal akış onları hiç temizlemez. Klinik diskinde her sürümde
    // yüzlerce MB birikir. Yeni indirmeye başlarken AYNI hedefin farklı-sha artıklarını sil.
    if let (Some(dir), Some(stem)) = (dest.parent(), dest.file_stem().and_then(|s| s.to_str())) {
        let onek = format!("{stem}.");
        if let Ok(rd) = fs::read_dir(dir) {
            for e in rd.flatten() {
                let ad = e.file_name();
                let Some(ad) = ad.to_str() else { continue };
                if ad.starts_with(&onek) && ad.ends_with(".part") {
                    // Bizim kullanacağımız `.part` aşağıda hesaplanıyor; onu ELEMEK için
                    // beklenen sha ön-ekini taşıyanı atlıyoruz.
                    let bizim = expected_sha.len() >= 12
                        && ad.contains(&expected_sha[..12].to_ascii_lowercase());
                    if !bizim {
                        let _ = fs::remove_file(e.path());
                    }
                }
            }
        }
    }
    let part = part_path(dest, expected_sha);

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
    // ⚠️ YEREL hatalar `LocalIo` (denetim 2026-08-23, C8): dosyayı açamamak ağ sorunu DEĞİLDİR;
    // `Io` olarak dönerse `flow::is_retriable` onu geçici sayar ve GB'lar boşuna yeniden iner.
    let mut out = if resuming {
        fs::OpenOptions::new()
            .append(true)
            .open(&part)
            .map_err(|e| NetError::LocalIo(format!("{} açılamadı: {e}", part.display())))?
    } else {
        fs::File::create(&part)
            .map_err(|e| NetError::LocalIo(format!("{} oluşturulamadı: {e}", part.display())))?
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
            return Err(NetError::PolicyLimit(format!(
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
            return Err(NetError::PolicyLimit(format!(
                "indirme boyut sınırını aştı ({done} > {ceiling} bayt) — iptal edildi"
            )));
        }
        // ⚠️ Diske yazamamak (disk dolu / izin / AV) yeniden denemeyle DÜZELMEZ → LocalIo.
        out.write_all(&buf[..n])
            .map_err(|e| NetError::LocalIo(format!("diske yazılamadı: {e}")))?;
        progress(done, total);
    }
    out.flush()
        .map_err(|e| NetError::LocalIo(format!("diske yazılamadı (flush): {e}")))?;
    drop(out);
    // ⚠️ EN KRİTİK NOKTA: buraya gelindiğinde indirme TAMAMLANMIŞTIR. `rename` düşerse (AV
    // taraması, os error 32 sharing violation) eskiden `Io` dönüyordu → 6 yeniden deneme → her
    // denemede tamamlanmış `.part` SİLİNİP 1,19 GB sıfırdan iniyordu. Artık kalıcı hata:
    // tamamlanmış baytlar korunur ve kullanıcı gerçek sebebi görür.
    fs::rename(&part, dest)
        .map_err(|e| NetError::LocalIo(format!("{} taşınamadı: {e}", dest.display())))?;
    Ok(done)
}

/// Küçük metin kaynağını (manifest) pinli + zaman-aşımlı indir. Host hem başlangıçta hem
/// redirect-sonrası doğrulanır; `into_string` ureq'te ~10MB'a kapalı (metin-DoS sınırı hazır).
///
/// ⚠️ Bu çağrı YİNE bloklar (DNS'e deadline uygulanamıyor). Açılış yolundan çağırıyorsan
/// `fetch_string_pinned_budgeted` kullan — o, duvar-saati bütçesiyle sarmalar.
pub fn fetch_string_pinned(url: &str) -> Result<String, NetError> {
    validate_download_source(url)?;
    let resp = build_text_agent()
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

/// `fetch_string_pinned` + DUVAR SAATİ bütçesi — AÇILIŞ yolunun kullanması gereken sürüm.
///
/// DENETİM 2026-08-06 (P0): client açılışta manifest'i çekmeden hiçbir ekran göstermiyordu ve bu
/// çağrının üst sınırı YOKTU → internet olmayan klinikte uygulama "Ortam algılanıyor…" ekranında
/// SONSUZA KADAR kalıyordu. Artık en geç `TEXT_WALL_BUDGET_S` sonra bir hata döner; UI bunu
/// "çevrimdışı" sayıp KURULU uygulamayı başlatmaya devam eder (backend zaten yereldir).
/// Manifest çekiminde GEÇİCİ aktarım hatası için deneme sayısı (ilk deneme dahil).
///
/// ⚠️ SAHA BULGUSU 2026-08-12: kullanıcı "internet var" derken client "İnternet bağlantısı yok;
/// kurulum için bağlantı gerekli" gösteriyordu. Ölçüldü (aynı makine, aynı an, 6 deneme):
///     HTTP 200 · 200 · **000** · **000** · 200 · 200      → ~%33 anlık kopma
/// Kopmalar 0,46-0,57 sn'de oluyordu; yani zaman aşımı DEĞİL, TCP sıfırlaması — zayıf WiFi /
/// hotspot / ISP dalgalanmasında olağan, tam da klinik ortamı. Çekim TEK denemeydi: bir kopma
/// tüm açılışı "internetsiz" ilan ediyordu. Klinik, çalışan bir hatta kurulum yapamıyordu.
const MANIFEST_DENEME: u32 = 3;
/// Denemeler arası kısa bekleme (ms). Toplam ek yük ≤ 1 sn — duvar bütçesine rahat sığar.
const MANIFEST_BEKLEME_MS: [u64; 2] = [250, 750];

/// Hata YENİDEN DENEMEYE değer mi? Yalnız GEÇİCİ aktarım hataları.
///
/// ⚠️ Deterministik olanlar (HTTP 404, host pini reddi, HTTPS değil, politika sınırı) tekrarda
/// AYNI sonucu verir; denemek yalnız kullanıcıyı bekletir ve hatayı gizler. `PolicyLimit`
/// ayrımının neden var olduğu için bkz. `NetError::PolicyLimit` notu (2026-08-04 P2).
fn gecici_hata_mi(e: &NetError) -> bool {
    matches!(e, NetError::Transport(_) | NetError::Io(_))
}

/// Yeniden deneme DÖNGÜSÜ — çekim işi ENJEKTE edilir (ağsız birim-testlenebilir).
///
/// `bekle`: denemeler arası uyku; testte no-op verilir ki süit yavaşlamasın.
pub fn denemeli_cek<F, B>(mut cek: F, mut bekle: B) -> Result<String, NetError>
where
    F: FnMut() -> Result<String, NetError>,
    B: FnMut(u64),
{
    let mut son: Option<NetError> = None;
    for deneme in 0..MANIFEST_DENEME {
        match cek() {
            Ok(s) => return Ok(s),
            Err(e) if !gecici_hata_mi(&e) => return Err(e), // kalıcı → HEMEN dön
            Err(e) => {
                son = Some(e);
                // Son denemeden sonra bekleme yok (boşuna gecikme).
                if let Some(ms) = MANIFEST_BEKLEME_MS.get(deneme as usize) {
                    bekle(*ms);
                }
            }
        }
    }
    Err(son.unwrap_or_else(|| NetError::Transport("manifest alınamadı".into())))
}

pub fn fetch_string_pinned_budgeted(url: &str) -> Result<String, NetError> {
    // Host pinini bütçeden ÖNCE uygula: güvenlik reddi ağ beklemeden, deterministik olsun.
    validate_download_source(url)?;
    let u = url.to_string();
    with_wall_budget(Duration::from_secs(TEXT_WALL_BUDGET_S), "manifest", move || {
        denemeli_cek(
            || fetch_string_pinned(&u),
            |ms| std::thread::sleep(Duration::from_millis(ms)),
        )
    })
}

#[cfg(test)]
mod tests {
    // ── MANİFEST YENİDEN DENEME (saha bulgusu 2026-08-12) ────────────────────────────────
    // Kullanıcı "internet var" derken client "İnternet bağlantısı yok" diyordu. Aynı makinede
    // aynı anda ölçüldü: 6 istekten 2'si 0,5 sn'de KOPTU (TCP reset), 4'ü 200 döndü. Çekim tek
    // denemeydi → bir kopma tüm açılışı "internetsiz" ilan ediyor, klinik kurulum yapamıyordu.

    fn gecici() -> NetError {
        NetError::Transport("connection reset".into())
    }

    #[test]
    fn gecici_kopmada_YENIDEN_DENER_ve_basarir() {
        let mut kalan_hata = 2; // ilk iki deneme kopsun, üçüncüsü tutsun
        let mut uykular = vec![];
        let r = denemeli_cek(
            || {
                if kalan_hata > 0 {
                    kalan_hata -= 1;
                    Err(gecici())
                } else {
                    Ok("{\"schema\":2}".to_string())
                }
            },
            |ms| uykular.push(ms),
        );
        assert!(r.is_ok(), "geçici kopmada pes edildi → kullanıcıya yanlışlıkla 'internet yok' denir");
        assert_eq!(uykular, vec![250, 750], "denemeler arası bekleme beklenenden farklı");
    }

    #[test]
    fn KALICI_hata_TEKRARLANMAZ() {
        // HTTP 404 / pin reddi tekrarda AYNI sonucu verir; denemek kullanıcıyı bekletir.
        let mut sayac = 0;
        let r = denemeli_cek(
            || {
                sayac += 1;
                Err(NetError::HttpStatus { status: 404, url: "https://x/y".into() })
            },
            |_| panic!("kalıcı hatada BEKLENMEMELİ"),
        );
        assert!(r.is_err());
        assert_eq!(sayac, 1, "kalıcı hata {sayac} kez denendi — 1 olmalı");
    }

    #[test]
    fn politika_siniri_TEKRARLANMAZ() {
        // Deterministik politika iptali (bkz. NetError::PolicyLimit, 2026-08-04 P2).
        let mut sayac = 0;
        let r = denemeli_cek(
            || {
                sayac += 1;
                Err(NetError::PolicyLimit("boyut tavanı".into()))
            },
            |_| panic!("politika sınırında BEKLENMEMELİ"),
        );
        assert!(r.is_err());
        assert_eq!(sayac, 1);
    }

    #[test]
    fn hepsi_koparsa_SON_hata_doner() {
        let mut sayac = 0;
        let mut uykular = vec![];
        let r = denemeli_cek(
            || {
                sayac += 1;
                Err(gecici())
            },
            |ms| uykular.push(ms),
        );
        assert!(matches!(r, Err(NetError::Transport(_))), "gerçek kopmada yine de hata dönmeli");
        assert_eq!(sayac, MANIFEST_DENEME, "deneme sayısı sözleşmesi değişti");
        assert_eq!(uykular.len(), 2, "SON denemeden sonra boşuna beklenmiş");
    }

    #[test]
    fn ilk_deneme_tutarsa_HIC_beklemez() {
        let r = denemeli_cek(|| Ok("ok".to_string()), |_| panic!("başarıda beklenmemeli"));
        assert_eq!(r.unwrap(), "ok");
    }
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

    /// ⚠️ P0 (denetim 2026-08-04) — repo-yolu pini NOKTA-SEGMENTİYLE ATLATILIYORDU.
    ///
    /// Pin ham metinde `starts_with` yapıyordu; ureq ise isteği göndermeden önce yolu RFC 3986
    /// `remove_dot_segments` ile NORMALİZE ediyor. Yerel sunucuya GERÇEK ureq isteğiyle ölçüldü:
    ///   URL   : /mert61-python/pemf-update/../../saldirgan/kotu/evil.exe
    ///   GİDEN : GET /saldirgan/kotu/evil.exe
    /// Yani zehirli manifest pini tamamen atlatıp kendi deposundan imzasız setup.exe indirtebilirdi
    /// (sha da aynı manifest'ten geldiği için doğrulama geçer, `/S` ile sessizce kurulur).
    #[test]
    fn nokta_segmentli_url_pini_atlatamaz() {
        let kotu = [
            "https://github.com/mert61-python/pemf-update/../../saldirgan/kotu/releases/download/v1/evil.exe",
            "https://github.com/mert61-python/pemf-update/%2e%2e/%2e%2e/saldirgan/kotu/base.zip",
            "https://github.com/mert61-python/pemf-update/%2E%2E/saldirgan/x.zip",
            "https://github.com/mert61-python/pemf-update/./../saldirgan/x.zip",
            "https://github.com/mert61-python/pemf-update//../saldirgan/x.zip",
            "https://github.com/mert61-python/pemf-update/..%2fsaldirgan/x.zip",
        ];
        for u in kotu {
            assert!(
                validate_download_source(u).is_err(),
                "PIN ATLATILDI (istek saldirganin deposuna gider): {u}"
            );
        }

        // MEŞRU URL'ler etkilenmemeli.
        for u in [
            "https://github.com/mert61-python/pemf-update/releases/download/client-app-v1.8.0/base.zip",
            "https://github.com/mert61-python/pemf-update/releases/download/client-app-v1.8.0/manifest.json",
        ] {
            assert!(validate_download_source(u).is_ok(), "mesru URL reddedildi: {u}");
        }
    }

    /// Saf yardımcının kendisi: sorgu/parça segment analizine karışmamalı.
    #[test]
    fn path_has_traversal_dogru_ayirir() {
        assert!(path_has_traversal("/a/../b"));
        assert!(path_has_traversal("/a/%2e%2e/b"));
        assert!(path_has_traversal("/a//b"));
        assert!(path_has_traversal("/a/./b"));
        assert!(!path_has_traversal("/mert61-python/pemf-update/releases/download/v1/base.zip"));
        // sorgu icindeki '//' YOL degildir — yanlis-pozitif olmamali
        assert!(!path_has_traversal("/a/b?x=1//2#frag"));
    }

    /// ⚠️ P2 (denetim 2026-08-04): `validate_download_source`'un YORUMU
    /// `raw.githubusercontent.com/<herhangi-hesap>/...` saldirisinin kapatildigini soyluyordu
    /// ama KOD o host'u (ve codeload'u) yol kontrolu OLMADAN kabul ediyordu — yanlis guvence.
    /// Ikisi de ucretsiz bir GitHub hesabiyla tamamen saldirgan-kontrollu bayt sunar.
    #[test]
    fn raw_ve_codeload_kaynak_olarak_kabul_edilmez() {
        for u in [
            "https://raw.githubusercontent.com/saldirgan/kotu/main/base.zip",
            "https://raw.githubusercontent.com/mert61-python/pemf-update/main/base.zip",
            "https://codeload.github.com/saldirgan/kotu/zip/refs/heads/main",
        ] {
            assert!(
                validate_download_source(u).is_err(),
                "KAYNAK olarak kabul edildi (saldirgan kendi deposundan bayt sunar): {u}"
            );
            // Ama REDIRECT hedefi olarak hala gecerli — GitHub CDN'i oraya yonlendirir.
            assert!(validate_url(u).is_ok(), "redirect hedefi olarak reddedildi: {u}");
        }

        // Opak nesne depolari KAYNAK olarak gecerli (yol GitHub tarafindan uretilir, imzalidir).
        for u in [
            "https://objects.githubusercontent.com/github-production-release-asset/1/2?x=y",
            "https://release-assets.githubusercontent.com/a/b",
        ] {
            assert!(validate_download_source(u).is_ok(), "opak nesne deposu reddedildi: {u}");
        }
    }

    /// P3 (denetim 2026-08-04): sha degisince eski `.part` KALICI YETIM kaliyordu — hicbir
    /// normal akis temizlemiyordu (clear_partials yalniz acik iptalde kosar). Klinik diskinde
    /// her surumde yuzlerce MB birikirdi.
    #[test]
    fn eski_shali_part_artiklari_temizlenir() {
        let d = tempfile::tempdir().unwrap();
        let dest = d.path().join("base.zip");
        let eski = d.path().join("base.aaaaaaaaaaaa.part");
        let yeni_sha = "bbbbbbbbbbbbcccccccccccccccccccccccccccccccccccccccccccccccccccc";
        let yeni = d.path().join(format!("base.{}.part", &yeni_sha[..12]));
        let alakasiz = d.path().join("baska.dddddddddddd.part");
        std::fs::write(&eski, b"bayat").unwrap();
        std::fs::write(&yeni, b"devam").unwrap();
        std::fs::write(&alakasiz, b"baska-indirme").unwrap();

        // download_to_file'in temizlik adiminin AYNISI (ag gerekmez).
        let dir = dest.parent().unwrap();
        let stem = dest.file_stem().unwrap().to_str().unwrap();
        let onek = format!("{stem}.");
        for e in std::fs::read_dir(dir).unwrap().flatten() {
            let ad = e.file_name();
            let ad = ad.to_str().unwrap().to_string();
            if ad.starts_with(&onek) && ad.ends_with(".part") {
                let bizim = ad.contains(&yeni_sha[..12]);
                if !bizim {
                    let _ = std::fs::remove_file(e.path());
                }
            }
        }

        assert!(!eski.exists(), "eski sha'li .part temizlenmedi (yetim dosya birikir)");
        assert!(yeni.exists(), "DEVAM EDILECEK .part silindi — indirme bastan baslar");
        assert!(alakasiz.exists(), "BASKA bir indirmenin .part'i silindi");
    }

    /// ⚠️ P0 (denetim 2026-08-06) — OFFLINE BOOT KİLİDİ.
    ///
    /// Manifest çekimi ureq zaman aşımlarına güveniyordu; ureq ise DNS çözümlemesine deadline
    /// UYGULAYAMIYOR (kendi kaynağındaki TODO). Upstream'siz hotspot'ta `getaddrinfo` onlarca
    /// saniye asılır ve client "Ortam algılanıyor…"da kilitlenirdi. İkinci kemer: duvar saati.
    #[test]
    fn duvar_saati_butcesi_asili_isi_keser() {
        let t = Instant::now();
        // 60 sn "asılı kalan" bir ağ işi taklidi — bütçe 1 sn.
        let r: Result<String, NetError> = with_wall_budget(Duration::from_secs(1), "test", || {
            std::thread::sleep(Duration::from_secs(60));
            Ok("gec-gelen".to_string())
        });
        let sure = t.elapsed();
        assert!(
            matches!(r, Err(NetError::PolicyLimit(_))),
            "asili is butce dolunca kesilmedi — client acilisi kilitlenir: {r:?}"
        );
        assert!(sure < Duration::from_secs(5), "butce uygulanmadi, {sure:?} beklendi");
    }

    /// Bütçe içinde biten iş AYNEN geçmeli (yanlış-pozitif "çevrimdışı" olmasın).
    #[test]
    fn duvar_saati_butcesi_hizli_isi_engellemez() {
        let r = with_wall_budget(Duration::from_secs(5), "test", || Ok("tamam".to_string()));
        assert_eq!(r.unwrap(), "tamam");
        // İçerideki HATA da aynen geçmeli (bütçe hatayı maskelemez).
        let e: Result<(), NetError> =
            with_wall_budget(Duration::from_secs(5), "test", || Err(NetError::NotHttps("x".into())));
        assert!(matches!(e, Err(NetError::NotHttps(_))));
    }

    /// Bütçeli sürüm de host-pinlemesini uygular ve bunu AĞ BEKLEMEDEN yapar
    /// (güvenlik reddi deterministik kalmalı).
    #[test]
    fn butceli_manifest_cekimi_pini_uygular() {
        let t = Instant::now();
        let r = fetch_string_pinned_budgeted("https://evil.example.com/manifest.json");
        assert!(matches!(r, Err(NetError::HostNotAllowed(_))));
        assert!(t.elapsed() < Duration::from_secs(2), "pin reddi ag bekledi");
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
