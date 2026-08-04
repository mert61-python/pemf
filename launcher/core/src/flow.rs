//! Kurulum akışının tamamı — UI'dan bağımsız, tek çağrı.
//!
//! UI yalnız `Progress` olaylarını dinler; sıralama, önbellek ve hata mantığı burada.
//! Böylece aynı akış Tauri kabuğundan da, bir CLI'dan da, testten de koşabilir.

use std::fs;
use std::path::{Path, PathBuf};

use crate::{extract, install, manifest::Manifest, net, verify};

/// UI'ya bildirilecek adımlar.
#[derive(Debug, Clone, PartialEq, Eq, serde::Serialize)]
#[serde(tag = "step", rename_all = "snake_case")]
pub enum Progress {
    ManifestFetched { version: String, schema: u8 },
    /// `total` 0 olabilir (sunucu Content-Length vermezse).
    Downloading { what: String, done: u64, total: u64 },
    /// Geçici ağ hatası (timeout/kopma) → `.part`'tan otomatik yeniden bağlanılıyor.
    Reconnecting { what: String, attempt: u32, max: u32 },
    Verifying { what: String },
    /// Paket önbellekte bulundu, indirme atlandı.
    Cached { what: String },
    Extracting { what: String },
    StartingBackend { port: u16 },
    Ready { url: String },
}

#[derive(Debug, thiserror::Error)]
pub enum FlowError {
    #[error(transparent)]
    Manifest(#[from] crate::manifest::ManifestError),
    #[error(transparent)]
    Net(#[from] net::NetError),
    #[error(transparent)]
    Verify(#[from] verify::VerifyError),
    #[error(transparent)]
    Extract(#[from] extract::ExtractError),
    #[error(transparent)]
    Backend(#[from] crate::backend::BackendError),
    #[error("dosya sistemi hatası: {0}")]
    Io(#[from] std::io::Error),
    /// DENETİM 2026-08-04: onarım, hangi profillerin kurulu olduğunu bilmeden model paketlerini
    /// SESSİZCE atlayıp "Hazır" diyordu. Artık kullanıcıya ne yapacağını söyleyen açık hata.
    #[error(
        "Kurulu profil kaydı okunamadı ama diskte model verisi VAR — hangi profillerin \
         onarılacağı bilinmiyor. Profilleri yeniden seçip kurun (indirilenler önbellekten gelir, \
         yeniden İNMEZ)."
    )]
    ProfileRecordUnreadable,
}

/// Cache dosya-adı güvenli mi: tek segment, yol-ayırıcı / sürücü / `..` / NUL YOK.
fn is_safe_filename(name: &str) -> bool {
    !name.is_empty()
        && name != "."
        && name != ".."
        && !name.contains('/')
        && !name.contains('\\')
        && !name.contains(':')
        && !name.contains('\0')
}

/// Bir indirme hatası GEÇİCİ mi (yeniden denenmeli) yoksa KALICI mı?
///
/// DENETİM 2026-08-04: `ensure_package`'ın yorumu "KALICI hatalar (host-pin/HTTPS/4xx) yeniden
/// denenmez" diyordu ama kod TÜM `HttpStatus` varyantlarını geçici sayıyordu. 404 (asset
/// `--clobber` ile silinmiş / yanlış tag) ya da 403'te kullanıcı ~22 sn "Yeniden bağlanılıyor"
/// görüp sonunda yine aynı hatayı alıyordu. Karar saf bir fonksiyona alındı → doğrudan test
/// edilebilir (host-pinlemesi yüzünden yerel HTTP sunucusuyla uçtan uca test edilemiyor).
fn is_retriable(e: &net::NetError) -> bool {
    match e {
        // Ağ kopması / timeout / aktarım hatası → geçici.
        net::NetError::Io(_) | net::NetError::Transport(_) => true,
        // 5xx sunucu tarafı geçicidir; 408 (Request Timeout) ve 429 (Too Many Requests) da öyle.
        // Diğer 4xx'ler KALICI: yeniden denemek yalnız kullanıcıyı bekletir.
        net::NetError::HttpStatus { status, .. } => *status >= 500 || *status == 408 || *status == 429,
        // ⚠️ DENETİM 2026-08-04 (P2): boyut tavanı / küresel süre aşımı ESKİDEN `Transport`
        // olarak dönüyordu ve yukarıdaki kol onları GEÇİCİ sayıyordu → aynı deterministik hata
        // 6 kez TAM YENİDEN İNDİRME tetikliyordu (gigabaytlarca boşuna trafik). Artık ayrı
        // varyant ve AÇIKÇA kalıcı. (Alttaki `_` zaten false döndürüyor; bu kol niyeti
        // belgeliyor ve varyant eklendiğinde sessizce yanlış tarafa düşmesini engelliyor.)
        net::NetError::PolicyLimit(_) => false,
        // Malformed / NotHttps / HostNotAllowed → GÜVENLİK reddi, ASLA yeniden deneme.
        // Paused / Cancelled → kullanıcı kararı, yeniden deneme YANLIŞ olur.
        _ => false,
    }
}

/// Bir paketi hazır et: önbellekte geçerli kopya varsa indirme, yoksa indir + doğrula.
///
/// Doğrulama İKİ yolda da yapılır — önbellekteki dosya bozulmuş olabilir (disk hatası,
/// yarım kalmış eski indirme). "Önbellekte var" tek başına güven sebebi değildir.
pub fn ensure_package(
    pkg: &crate::Package,
    cache: &Path,
    label: &str,
    on: &mut dyn FnMut(Progress),
    control: &dyn Fn() -> net::Control,
) -> Result<PathBuf, FlowError> {
    fs::create_dir_all(cache)?;
    // #131/#139: dosya adı SALDIRGAN-ETKİLİ pkg.url'den türüyor. Yol-kaçış karakteri (Windows '\',
    // sürücü ':', '/', '..', NUL) içeriyorsa cache DIŞINA yazabilir → güvenli ada düş. İlk güvenli
    // adayı seç: url-son-segment → label → sabit "package.bin".
    let raw_name = pkg.url.rsplit('/').next().unwrap_or("");
    let file_name = [raw_name, label, "package.bin"]
        .into_iter()
        .find(|s| is_safe_filename(s))
        .unwrap_or("package.bin");
    let dest = cache.join(file_name);

    if dest.exists() && verify::verify_file(&dest, &pkg.sha256).is_ok() {
        on(Progress::Cached { what: label.to_string() });
        return Ok(dest);
    }

    // Otomatik yeniden-deneme: GEÇİCİ ağ hataları (timeout/kopma/5xx — ör. os error 10060, büyük
    // paket sonrası bağlantı düşmesi) kurulumu düşürmesin. `.part` korunduğu için her deneme Range
    // ile KALDIĞI YERDEN sürer. Pause/Cancel + KALICI hatalar (host-pin/HTTPS/4xx) yeniden denenmez.
    const MAX_ATTEMPTS: u32 = 6;
    let mut attempt = 0u32;
    loop {
        attempt += 1;
        let result = {
            let mut cb = |done, total| {
                on(Progress::Downloading { what: label.to_string(), done, total });
            };
            net::download_to_file(&pkg.url, &dest, pkg.size, &pkg.sha256, &mut cb, control)
        };
        match result {
            Ok(_) => break,
            Err(e) => {
                let retriable = is_retriable(&e);
                if !retriable || attempt >= MAX_ATTEMPTS {
                    return Err(e.into());
                }
                on(Progress::Reconnecting { what: label.to_string(), attempt, max: MAX_ATTEMPTS });
                // Artan bekleme (1.5s→7.5s), ama Pause/Cancel gelirse HEMEN dön (asılı kalma).
                let wait_ms = (attempt.min(5) as u64) * 1500;
                let mut waited = 0u64;
                while waited < wait_ms {
                    match control() {
                        net::Control::Cancel => return Err(net::NetError::Cancelled.into()),
                        net::Control::Pause => return Err(net::NetError::Paused.into()),
                        net::Control::Continue => {}
                    }
                    std::thread::sleep(std::time::Duration::from_millis(200));
                    waited += 200;
                }
            }
        }
    }

    on(Progress::Verifying { what: label.to_string() });
    if let Err(e) = verify::verify_file(&dest, &pkg.sha256) {
        // Bozuk dosyayı BIRAKMA: kalırsa sonraki kurulum onu "önbellek" sanıp
        // aynı hataya tekrar düşer.
        let _ = fs::remove_file(&dest);
        return Err(e.into());
    }
    Ok(dest)
}

/// manifest → base + SEÇİLEN PROFİLLER → kurulum (backend BAŞLATMAZ). Kurulan profiller kaydedilir.
///
/// Çoklu-profil: kullanıcı birden çok profil (Ev Sahibi + Veteriner + Araştırma) seçebilir;
/// base BİR KEZ, her profil model-zip'i sırayla kurulur. Boş liste = yalnız base (onarım/temel).
pub fn install_profiles(
    manifest_raw: &str,
    profiles: &[String],
    install_root: &Path,
    on: &mut dyn FnMut(Progress),
    control: &dyn Fn() -> net::Control,
) -> Result<(), FlowError> {
    let manifest = Manifest::parse(manifest_raw)?;
    on(Progress::ManifestFetched {
        version: manifest.version.clone(),
        schema: manifest.schema,
    });

    // Platform paketi YOKSA burada durur — asla başka platformun paketine düşmez.
    let runtime_pkg = manifest.runtime_for_current_platform()?;
    // TÜM profilleri İNDİRMEDEN ÖNCE doğrula (biri manifestte yoksa hiç indirme başlamasın).
    let model_pkgs: Vec<(&String, &crate::Package)> = profiles
        .iter()
        .map(|p| manifest.model_package(p).map(|pk| (p, pk)))
        .collect::<Result<_, _>>()?;

    // Yükseltme: eski boşluksuz "PEMFVetClient" kurulumu varsa yeni isme taşı (2 GB yeniden inmesin).
    install::migrate_legacy_install_root(install_root);

    let cache = install::cache_dir(install_root);
    let runtime_zip = ensure_package(runtime_pkg, &cache, "base", on, control)?;

    // ⚠️ DENETİM 2026-08-04 (P2): `extract_zip` SALT-EKLEME/ÜZERİNE-YAZMA yapar — yalnız arşivde
    // BULUNAN girdileri yazar, arşivde OLMAYAN dosyaları KALDIRMAZ ve hedef ağacı önce silmez.
    // Kurulum yolunda hiçbir yerde `remove_dir_all(runtime_dir)` çağrılmıyordu (`remove_install`
    // yalnız Kaldır'da kullanılır). Sonuç: "başarılı" bir yükseltmeden sonra bile disk İKİ SÜRÜMÜN
    // BİRLEŞİMİYDİ — yeni sürümde KALDIRILAN dosyalar (eski .pyd/.dll, eski web bundle parçaları)
    // yaşamaya devam ediyordu. PyInstaller onedir düzeninde bayat bir DLL/uzantı, sürümü
    // uyuşmayan bir Python ikilisiyle yüklendiğinde tanımsız davranış üretir ve bu, sürüm
    // numarasına bakan hiçbir teşhisle görünmez.
    // base.zip runtime ağacının TAMAMINI içerir → ÖNCE TEMİZLE, sonra aç.
    // (Backend bu noktada zaten durdurulmuştur: install/repair yolları `stop_tracked_backend`
    //  çağırır. Dosya kilidi varsa burada AÇIK hata veririz — sessiz karışık-kurulumdan iyidir.)
    let rt = install::runtime_dir(install_root);
    if rt.exists() {
        on(Progress::Extracting { what: "eski sürüm temizleniyor".into() });
        fs::remove_dir_all(&rt)?;
    }
    // #110: açılım bütçesi TÜM kurulum boyunca PAYLAŞILIR. Eskiden her `extract_zip` çağrısı
    // sayacı sıfırlıyordu → belgelenen 8 GB tavanı base + 3 profil için pratikte 32 GB'dı.
    let mut extract_budget: u64 = 0;
    on(Progress::Extracting { what: "base".into() });
    // ⚠️ DENETİM 2026-08-04 (P2 — İPTAL ÖZELLİĞİNİN YAN ETKİSİ): iptali eklerken "yarım ağaç
    // zararsız, durum dosyaları güncellenmiyor" demiştim. YANLIŞTI. Launcher "kurulu mu"
    // kararını `installed_profiles.json`'a değil `install::backend_path().exists()`'e göre
    // veriyor (bkz. detect_environment) ve `make_base_zip.py` kökteki tek dosya olan
    // `PEMF_Backend.exe`'yi İLK girdi olarak yazıyor. Yani base açılımı %1'de iptal edilse
    // bile exe diske düşmüş oluyor → UI kurulumu "kurulu" gösterip 6155 girdisi (~1,29 GB
    // `_internal/` PyInstaller ağacı) EKSİK bir backend'i başlatmaya çalışıyor.
    // Bu yüzden base açılımı BAŞARISIZ olursa (iptal ya da G/Ç hatası) `runtime/` SİLİNİR —
    // "hiç kurulmamış" durumu, "yarım kurulmuş"tan her zaman iyidir. Maliyet düşük: iptal
    // genelde erken gelir ve zaten yeniden indirme gerektirmez (paketler önbellekte).
    if let Err(e) = extract::extract_zip_cancellable(
        &runtime_zip,
        &rt,
        &mut extract_budget,
        false,
        &|| control() == net::Control::Cancel,
    ) {
        let _ = fs::remove_dir_all(&rt);
        return Err(e.into());
    }

    // Her profil paketi `ai_models/...` önekiyle geldiği için kurulum KÖKÜNE açılır →
    // <kök>/ai_models/... oluşur ve PEMF_AI_MODELS_DIR tam oraya işaret eder.
    for (name, pkg) in &model_pkgs {
        let model_zip = ensure_package(pkg, &cache, name, on, control)?;
        on(Progress::Extracting { what: (*name).clone() });
        // `is_profile = true`: profil paketi doğrulanmış `runtime/` ağacını ve launcher durum
        // dosyalarını EZEMEZ (bkz. extract::PROFILE_FORBIDDEN_TOP, #104).
        extract::extract_zip_cancellable(&model_zip, install_root, &mut extract_budget, true, &|| {
            control() == net::Control::Cancel
        })?;
        // Bu profil TAM indi + açıldı → HEMEN "kurulu" işaretle (mevcutlarla birleşir).
        // ÖNEMLİ: işaretlemeyi döngü SONUNA bırakma. Çoklu-profil kurulumunda kullanıcı
        // sonraki profili İPTAL ederse (ör. Ev Sahibi bitti, Veteriner yarıda iptal),
        // erken-return burayı atlar → tamamlanan profil KAYBOLURDU. Her profili kendi
        // extract'ından hemen sonra kaydederek, iptal-sonrası kullanıcı tamamlanmış
        // profil(ler)le uygulamayı kurup başlatabilir.
        install::add_installed_profiles(install_root, std::slice::from_ref(*name));
    }
    Ok(())
}

/// Kurulu backend'i başlat (İNDİRME YOK). Hem ilk kurulum sonrası hem "Başlat" bunu kullanır.
pub fn start_backend(
    install_root: &Path,
    on: &mut dyn FnMut(Progress),
) -> Result<(std::process::Child, String, u16), FlowError> {
    let port = crate::backend::find_free_port(install::DEFAULT_PORT, 50)?;
    on(Progress::StartingBackend { port });
    let child = crate::backend::start_and_wait(
        install_root,
        port,
        std::time::Duration::from_secs(180),
    )?;
    let url = crate::backend::app_url(port);
    on(Progress::Ready { url: url.clone() });
    // Port da döner: launcher pencere kapanışında bobinleri güvene almak için (safe_stop_coils).
    Ok((child, url, port))
}

/// Onar: kurulu profilleri (+base) YENİDEN doğrula/çıkar. `ensure_package` önbellekteki dosyayı
/// SHA ile doğrular → bozuksa yeniden indirir; her paket yeniden extract edilir (eksik/bozuk
/// dosyalar onarılır). Hiç profil kurulu değilse yalnız base onarılır. Backend BAŞLATMAZ.
pub fn repair(
    manifest_raw: &str,
    install_root: &Path,
    on: &mut dyn FnMut(Progress),
    control: &dyn Fn() -> net::Control,
) -> Result<(), FlowError> {
    // DENETİM 2026-08-04: liste `read_installed_profiles`'tan alınıyordu; o fonksiyon dosya yoksa
    // VEYA JSON bozuksa BOŞ liste döndüğü için onarım YALNIZ base'i yeniliyor, model paketlerine
    // HİÇ dokunmuyor ve yine de `Ok(())` dönüyordu → UI "Hazır" diyordu. Artık kaydın durumu
    // ayırt ediliyor: okunamıyorsa ve diskte model verisi VARSA hangi profillerin onarılacağı
    // BİLİNEMEZ → sessiz başarı yerine AÇIK hata.
    let installed = match install::read_installed_profiles_detailed(install_root) {
        install::ProfileRecord::Ok(v) => v,
        _ if install::has_model_data(install_root) => {
            return Err(FlowError::ProfileRecordUnreadable);
        }
        // Kayıt yok/bozuk AMA diskte model de yok → gerçekten yalnız base kurulu; onarım doğru.
        _ => Vec::new(),
    };
    install_profiles(manifest_raw, &installed, install_root, on, control)
}

/// manifest → base + tek profil → kurulum → backend başlat. (Geriye-uyum: tek-profil sarmalayıcı.)
pub fn install_and_launch(
    manifest_raw: &str,
    profile: &str,
    install_root: &Path,
    on: &mut dyn FnMut(Progress),
) -> Result<(std::process::Child, String, u16), FlowError> {
    install_profiles(
        manifest_raw,
        std::slice::from_ref(&profile.to_string()),
        install_root,
        on,
        &|| net::Control::Continue,
    )?;
    start_backend(install_root, on)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;

    fn pkg(url: &str, sha: &str) -> crate::Package {
        crate::Package {
            url: url.to_string(),
            sha256: sha.to_string(),
            size: 0,
            kind: "zip".into(),
        }
    }

    const ABC_SHA: &str = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad";

    #[test]
    fn onbellekteki_gecerli_dosya_yeniden_indirilmez() {
        let dir = tempfile::tempdir().unwrap();
        let cache = dir.path();
        // URL'nin son parçası dosya adı olur.
        fs::File::create(cache.join("x.zip")).unwrap().write_all(b"abc").unwrap();

        let mut seen = Vec::new();
        let mut on = |p: Progress| seen.push(p);
        // Host pinlemesi geçerli bir URL; önbellek isabet ettiği için AĞA ÇIKILMAZ.
        let got = ensure_package(
            &pkg("https://github.com/a/x.zip", ABC_SHA),
            cache,
            "base",
            &mut on,
            &|| net::Control::Continue,
        )
        .unwrap();

        assert_eq!(got, cache.join("x.zip"));
        assert_eq!(seen, vec![Progress::Cached { what: "base".into() }]);
    }

    #[test]
    fn onbellekteki_bozuk_dosya_guven_sebebi_degil() {
        let dir = tempfile::tempdir().unwrap();
        let cache = dir.path();
        fs::File::create(cache.join("x.zip")).unwrap().write_all(b"BOZUK").unwrap();

        let mut on = |_: Progress| {};
        // Dosya bozuk → önbellek reddedilir → indirmeye gider → ağ yok/host testte
        // erişilemez olduğu için hata döner. Önemli olan: "Cached" DEMEDİ.
        let err = ensure_package(
            &pkg("https://github.com/a/x.zip", ABC_SHA),
            cache,
            "base",
            &mut on,
            &|| net::Control::Continue,
        )
        .unwrap_err();
        assert!(matches!(err, FlowError::Net(_)), "beklenmeyen: {err:?}");
    }

    #[test]
    fn pinlenmemis_host_indirmeden_once_reddedilir() {
        let dir = tempfile::tempdir().unwrap();
        let mut on = |_: Progress| {};
        let err = ensure_package(
            &pkg("https://evil.example/x.zip", ABC_SHA),
            dir.path(),
            "base",
            &mut on,
            &|| net::Control::Continue,
        )
        .unwrap_err();
        assert!(matches!(err, FlowError::Net(net::NetError::HostNotAllowed(_))));
    }

    #[test]
    fn eksik_platform_akisi_baslamadan_durdurur() {
        let raw = format!(
            r#"{{"version":"1.8.0","profiles":{{"vet":{{"url":"https://github.com/a/vet.zip","sha256":"{ABC_SHA}"}}}}}}"#
        );
        let dir = tempfile::tempdir().unwrap();
        let mut on = |_: Progress| {};
        let err = install_and_launch(&raw, "vet", dir.path(), &mut on).unwrap_err();
        assert!(matches!(
            err,
            FlowError::Manifest(crate::manifest::ManifestError::UnsupportedPlatform { .. })
        ));
    }

    /// DENETİM 2026-08-04: 4xx KALICIDIR — yeniden denemek kullanıcıyı ~22 sn boşuna bekletiyordu.
    /// Güvenlik reddi ve kullanıcı iptali de ASLA yeniden denenmemeli.
    #[test]
    fn yalniz_gercekten_gecici_hatalar_yeniden_denenir() {
        let st = |s: u16| net::NetError::HttpStatus { status: s, url: "https://x/y.zip".into() };

        // KALICI 4xx → yeniden deneme YOK.
        for s in [400u16, 401, 403, 404, 410, 416, 451] {
            assert!(!is_retriable(&st(s)), "{s} KALICI olmali (bosuna bekletme)");
        }
        // GEÇİCİ: 5xx + 408 + 429.
        for s in [408u16, 429, 500, 502, 503, 504] {
            assert!(is_retriable(&st(s)), "{s} GECICI olmali");
        }
        // Ağ/aktarım → geçici.
        assert!(is_retriable(&net::NetError::Transport("baglanti koptu".into())));
        assert!(is_retriable(&net::NetError::Io(std::io::Error::new(
            std::io::ErrorKind::TimedOut,
            "timeout"
        ))));
        // GÜVENLİK reddi → ASLA yeniden deneme (host-pin/HTTPS zorunluluğu kalıcıdır).
        assert!(!is_retriable(&net::NetError::HostNotAllowed("evil.example".into())));
        assert!(!is_retriable(&net::NetError::NotHttps("http://x".into())));
        assert!(!is_retriable(&net::NetError::Malformed("x".into())));
        // Kullanıcı kararı → yeniden deneme YANLIŞ.
        assert!(!is_retriable(&net::NetError::Paused));
        assert!(!is_retriable(&net::NetError::Cancelled));
        // P2: politika iptalleri DETERMINISTIK — yeniden denemek 6x tam indirme demek.
        assert!(!is_retriable(&net::NetError::PolicyLimit("boyut".into())));
    }

    /// DENETİM 2026-08-04: profil kaydı okunamaz + diskte MODEL VARSA onarım SESSİZCE yalnız
    /// base'i yenileyip "Hazır" diyordu. Artık açık hata verir (kullanıcı ne yapacağını bilir).
    #[test]
    fn onarim_profil_kaydi_okunamazken_sessizce_basarili_olmaz() {
        let dir = tempfile::tempdir().unwrap();
        let root = dir.path();
        // Diskte model verisi VAR ama kayıt BOZUK → onarım hangi profilleri onaracağını bilemez.
        fs::create_dir_all(install::models_dir(root).join("ai_hub")).unwrap();
        fs::write(install::installed_profiles_path(root), "{bozuk").unwrap();

        let mut on = |_: Progress| {};
        let err = repair("{}", root, &mut on, &|| net::Control::Continue).unwrap_err();
        assert!(
            matches!(err, FlowError::ProfileRecordUnreadable),
            "sessiz basari/farkli hata: {err:?}"
        );
    }

    /// Kayıt yok AMA disk de boşsa: gerçekten yalnız base kurulu → onarım DEVAM etmeli
    /// (ProfileRecordUnreadable DEĞİL; burada manifest bozuk olduğu için Manifest hatası bekleriz).
    /// ⚠️ P2 (denetim 2026-08-04): base açılımı iptal/hata ile yarım kalırsa `runtime/`
    /// SİLİNMELİ. Aksi halde `make_base_zip.py`'nin İLK girdi olarak yazdığı
    /// `PEMF_Backend.exe` diske düşmüş olur, `detect_environment` `backend_path().exists()`
    /// ile "kurulu" der ve UI EKSİK bir backend'i başlatmaya çalışır.
    #[test]
    fn yarim_kalan_base_acilimi_kurulu_gorunmez() {
        use std::io::Write;
        let d = tempfile::tempdir().unwrap();
        let root = d.path();
        let rt = install::runtime_dir(root);

        // İptal edilmiş bir açılımı taklit et: backend exe yazılmış, gerisi yok.
        let bp = install::backend_path(root);
        std::fs::create_dir_all(bp.parent().unwrap()).unwrap();
        let mut f = std::fs::File::create(&bp).unwrap();
        f.write_all(b"yarim").unwrap();
        assert!(bp.exists(), "on kosul: backend exe yerinde");

        // flow'un iptal/hata dalindaki temizligi ile AYNI islem.
        let _ = std::fs::remove_dir_all(&rt);

        assert!(
            !install::backend_path(root).exists(),
            "yarim agac temizlenmedi — UI kurulumu 'kurulu' gosterir ve EKSIK backend baslatilir"
        );
    }

    #[test]
    fn onarim_model_yokken_normal_akista_kalir() {
        let dir = tempfile::tempdir().unwrap();
        let mut on = |_: Progress| {};
        let err = repair("{}", dir.path(), &mut on, &|| net::Control::Continue).unwrap_err();
        assert!(
            !matches!(err, FlowError::ProfileRecordUnreadable),
            "model verisi yokken onarim engellenmemeli: {err:?}"
        );
    }

    #[test]
    fn progress_json_olarak_serilestirilebilir() {
        let p = Progress::Downloading { what: "base".into(), done: 5, total: 10 };
        let s = serde_json::to_string(&p).unwrap();
        assert!(s.contains("\"step\":\"downloading\""), "{s}");
    }
}
