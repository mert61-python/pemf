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
            net::download_to_file(&pkg.url, &dest, pkg.size, &mut cb, control)
        };
        match result {
            Ok(_) => break,
            Err(e) => {
                let retriable = matches!(
                    e,
                    net::NetError::Io(_) | net::NetError::Transport(_) | net::NetError::HttpStatus { .. }
                );
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
    on(Progress::Extracting { what: "base".into() });
    extract::extract_zip(&runtime_zip, &install::runtime_dir(install_root))?;

    // Her profil paketi `ai_models/...` önekiyle geldiği için kurulum KÖKÜNE açılır →
    // <kök>/ai_models/... oluşur ve PEMF_AI_MODELS_DIR tam oraya işaret eder.
    for (name, pkg) in &model_pkgs {
        let model_zip = ensure_package(pkg, &cache, name, on, control)?;
        on(Progress::Extracting { what: (*name).clone() });
        extract::extract_zip(&model_zip, install_root)?;
    }

    // Kurulu profilleri kaydet (UI çip'leri + Onar bunu okur; mevcutlarla birleşir).
    install::add_installed_profiles(install_root, profiles);
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
    let installed = install::read_installed_profiles(install_root);
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

    #[test]
    fn progress_json_olarak_serilestirilebilir() {
        let p = Progress::Downloading { what: "base".into(), done: 5, total: 10 };
        let s = serde_json::to_string(&p).unwrap();
        assert!(s.contains("\"step\":\"downloading\""), "{s}");
    }
}
