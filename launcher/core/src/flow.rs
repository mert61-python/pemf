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

/// Bir paketi hazır et: önbellekte geçerli kopya varsa indirme, yoksa indir + doğrula.
///
/// Doğrulama İKİ yolda da yapılır — önbellekteki dosya bozulmuş olabilir (disk hatası,
/// yarım kalmış eski indirme). "Önbellekte var" tek başına güven sebebi değildir.
pub fn ensure_package(
    pkg: &crate::Package,
    cache: &Path,
    label: &str,
    on: &mut dyn FnMut(Progress),
) -> Result<PathBuf, FlowError> {
    fs::create_dir_all(cache)?;
    let file_name = pkg
        .url
        .rsplit('/')
        .next()
        .filter(|s| !s.is_empty())
        .unwrap_or(label);
    let dest = cache.join(file_name);

    if dest.exists() && verify::verify_file(&dest, &pkg.sha256).is_ok() {
        on(Progress::Cached { what: label.to_string() });
        return Ok(dest);
    }

    let mut cb = |done, total| {
        on(Progress::Downloading { what: label.to_string(), done, total });
    };
    net::download_to_file(&pkg.url, &dest, pkg.size, &mut cb)?;

    on(Progress::Verifying { what: label.to_string() });
    if let Err(e) = verify::verify_file(&dest, &pkg.sha256) {
        // Bozuk dosyayı BIRAKMA: kalırsa sonraki kurulum onu "önbellek" sanıp
        // aynı hataya tekrar düşer.
        let _ = fs::remove_file(&dest);
        return Err(e.into());
    }
    Ok(dest)
}

/// manifest → base + profil → kurulum → backend başlat. Hazır olan URL'yi döndürür.
pub fn install_and_launch(
    manifest_raw: &str,
    profile: &str,
    install_root: &Path,
    on: &mut dyn FnMut(Progress),
) -> Result<(std::process::Child, String), FlowError> {
    let manifest = Manifest::parse(manifest_raw)?;
    on(Progress::ManifestFetched {
        version: manifest.version.clone(),
        schema: manifest.schema,
    });

    // Platform paketi YOKSA burada durur — asla başka platformun paketine düşmez.
    let runtime_pkg = manifest.runtime_for_current_platform()?;
    let model_pkg = manifest.model_package(profile)?;

    // Yükseltme: eski boşluksuz "PEMFVetClient" kurulumu varsa yeni isme taşı (2 GB yeniden inmesin).
    install::migrate_legacy_install_root(install_root);

    let cache = install::cache_dir(install_root);
    let runtime_zip = ensure_package(runtime_pkg, &cache, "base", on)?;
    let model_zip = ensure_package(model_pkg, &cache, profile, on)?;

    on(Progress::Extracting { what: "base".into() });
    extract::extract_zip(&runtime_zip, &install::runtime_dir(install_root))?;

    // Profil paketi `ai_models/...` önekiyle geldiği için kurulum KÖKÜNE açılır →
    // <kök>/ai_models/... oluşur ve PEMF_AI_MODELS_DIR tam oraya işaret eder.
    on(Progress::Extracting { what: profile.into() });
    extract::extract_zip(&model_zip, install_root)?;

    let port = crate::backend::find_free_port(install::DEFAULT_PORT, 50)?;
    on(Progress::StartingBackend { port });
    let child = crate::backend::start_and_wait(
        install_root,
        port,
        std::time::Duration::from_secs(180),
    )?;

    let url = crate::backend::app_url(port);
    on(Progress::Ready { url: url.clone() });
    Ok((child, url))
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
