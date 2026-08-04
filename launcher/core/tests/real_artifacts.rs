//! Gerçek artefakt üzerinde uçtan uca doğrulama.
//!
//! Depoda `base-mac.zip` + `base-mac.sha256.txt` varsa (build_mac.sh çıktısı) çekirdeği
//! ONUN üzerinde koşar: manifest'ten gelen digest ile doğrulama, zip-slip korumalı açma
//! ve backend'in çalıştırma bitiyle çıkması. Artefakt yoksa test ATLANIR (CI'da opsiyonel).

use std::path::{Path, PathBuf};

use pemf_launcher_core::{backend, extract, install, platform, verify};

fn repo_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("../..").canonicalize().unwrap()
}

#[test]
fn gercek_base_paketi_dogrulanir_ve_acilir() {
    // ⚠️ DENETİM 2026-08-04 (#100): bu test bir macOS PAKETİNİ açar; `base-mac.zip` içinde
    // GERÇEK sembolik linkler var (`_internal/*.dylib`, `_internal/Python`). Windows'ta symlink
    // ayrıcalık ister ve `extract` bunu bilerek reddeder → test, artefakt çalışma ağacında
    // durduğu SÜRECE bu makinede DAİMA kırmızıydı ("acma basarisiz: bu platformda sembolik link
    // desteklenmiyor"). Kalıcı kırmızı test, gerçek regresyonların da yok sayılmasına yol açar.
    // Testin kendi son satırı zaten `assert_eq!(platform::current(), MAC_ARM64)` diyor — yani
    // TASARIMI gereği yalnız macOS testi. Kapıyı en başa alıyoruz: başka platformda ATLANIR.
    if platform::current() != platform::MAC_ARM64 {
        eprintln!(
            "ATLANDI: base-mac.zip yalniz macOS'ta acilabilir (symlink); host={}",
            platform::current()
        );
        return;
    }
    let root = repo_root();
    let zip_path = root.join("base-mac.zip");
    let sha_path = root.join("base-mac.sha256.txt");
    if !zip_path.exists() || !sha_path.exists() {
        eprintln!("ATLANDI: base-mac.zip yok (once ./build_mac.sh)");
        return;
    }

    // build_mac.sh çıktısı: "<digest>  base-mac.zip"
    let sha_line = std::fs::read_to_string(&sha_path).unwrap();
    let expected = sha_line.split_whitespace().next().unwrap();

    // 1) Manifest'ten gelmiş gibi doğrula.
    verify::verify_file(&zip_path, expected).expect("gercek paketin SHA256'si uyusmadi");

    // 2) Bozuk digest REDDEDİLMELİ (doğrulamanın gerçekten çalıştığının kanıtı).
    let bad = "0".repeat(64);
    assert!(verify::verify_file(&zip_path, &bad).is_err(), "bozuk digest kabul edildi!");

    // 3) Zip-slip korumalı açma.
    let tmp = tempfile::tempdir().unwrap();
    let install_root = tmp.path();
    let runtime = install::runtime_dir(install_root);
    let n = extract::extract_zip(&zip_path, &runtime).expect("acma basarisiz");
    assert!(n > 3000, "beklenenden az dosya acildi: {n}");

    // 4) Backend ikilisi doğru yerde ve ÇALIŞTIRILABİLİR olmalı.
    let backend = install::backend_path(install_root);
    assert!(backend.exists(), "backend bulunamadi: {}", backend.display());
    assert!(extract::is_within(install_root, &backend), "backend kurulum kokunun disinda!");

    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let mode = std::fs::metadata(&backend).unwrap().permissions().mode();
        assert_eq!(mode & 0o111, 0o111, "calistirma biti yok — backend baslatilamazdi");
    }

    // 5) Bu platformun paketi olduğu teyidi.
    assert_eq!(platform::current(), platform::MAC_ARM64);
}

/// `scripts/make_manifest.py` çıktısı launcher tarafından okunabiliyor mu?
///
/// Üreticiyle tüketici ayrı dillerde (Python / Rust) — şema sapması ancak gerçek
/// çıktı ayrıştırılarak yakalanır. `PEMF_MANIFEST_FILE` ile dosya verilir.
#[test]
fn uretilen_manifest_launcher_tarafindan_okunur() {
    let Ok(path) = std::env::var("PEMF_MANIFEST_FILE") else {
        eprintln!("ATLANDI: PEMF_MANIFEST_FILE verilmedi");
        return;
    };
    let raw = std::fs::read_to_string(&path).expect("manifest okunamadi");
    let m = pemf_launcher_core::Manifest::parse(&raw).expect("uretilen manifest AYRISTIRILAMADI");

    assert_eq!(m.schema, 2, "make_manifest.py sema v2 yazmali");
    // Üç platform da tanımlı olmalı — biri eksikse o istemci kurulum yapamaz.
    for key in [platform::WIN_X64, platform::LINUX_X64, platform::MAC_ARM64] {
        assert!(m.runtimes.contains_key(key), "{key} runtime eksik");
    }
    for p in ["home", "vet", "research"] {
        assert!(m.models.contains_key(p), "{p} profili eksik");
    }
    // Bu platformun paketi çözülebilmeli.
    let pkg = m.runtime_for_current_platform().expect("platform paketi cozulemedi");
    assert!(pkg.url.starts_with("https://"), "beklenmeyen url: {}", pkg.url);

    // #100: digest karşılaştırması, diskteki dosyayla AYNI platformun paketi üzerinden yapılmalı.
    // Önceden MEVCUT platformun paketi alınıp `base-mac.zip`e karşı doğrulanıyordu — mac dışında
    // her zaman uyumsuz çıkardı (test yalnız PEMF_MANIFEST_FILE verilmediği için sessiz kalıyordu).
    let local = repo_root().join("base-mac.zip");
    if local.exists() {
        let mac = m.runtimes.get(platform::MAC_ARM64).expect("mac runtime eksik");
        assert!(mac.url.ends_with("base-mac.zip"), "beklenmeyen mac url: {}", mac.url);
        verify::verify_file(&local, &mac.sha256)
            .expect("manifest digest'i gercek base-mac.zip ile UYUSMUYOR");
    }
}

/// UÇTAN UCA: çekirdek, kurduğu paketten GERÇEK backend'i başlatabiliyor mu?
///
/// `PEMF_LAUNCHER_E2E=1` ile açılır — varsayılan olarak koşmaz çünkü (a) ~2 dk sürer,
/// (b) backend açılışta cihaz kaydını BULUT'a yazar. Veri dizini BİLEREK varsayılanda
/// bırakılır: geçici bir dizin verilseydi her koşuda YENİ device_id üretilip üretim
/// Supabase'ine çöp cihaz kaydı düşerdi.
#[test]
fn gercek_backend_baslatilir_ve_health_doner() {
    if std::env::var("PEMF_LAUNCHER_E2E").as_deref() != Ok("1") {
        eprintln!("ATLANDI: PEMF_LAUNCHER_E2E=1 ile calistirin");
        return;
    }
    // #100: mac paketi + mac ikilisi — başka platformda açılamaz, çalıştırılamaz.
    if platform::current() != platform::MAC_ARM64 {
        eprintln!("ATLANDI: base-mac.zip E2E'si yalniz macOS'ta kosar");
        return;
    }
    let root = repo_root();
    let zip_path = root.join("base-mac.zip");
    if !zip_path.exists() {
        eprintln!("ATLANDI: base-mac.zip yok");
        return;
    }

    let tmp = tempfile::tempdir().unwrap();
    let install_root = tmp.path();
    extract::extract_zip(&zip_path, &install::runtime_dir(install_root)).unwrap();

    let port = backend::find_free_port(48100, 50).unwrap();
    let mut child = backend::start_and_wait(install_root, port, std::time::Duration::from_secs(120))
        .expect("backend hazir olmadi");

    // Hazırsa web arayüzü de servis edilmeli (frontend/dist paketlenmiş olmalı).
    let body = ureq::get(&backend::app_url(port)).call().unwrap();
    assert_eq!(body.status(), 200);

    let raw = ureq::get(&backend::health_url(port)).call().unwrap().into_string().unwrap();
    let health: serde_json::Value = serde_json::from_str(&raw).unwrap();
    assert_eq!(health["status"], "online");
    // Medikal veri kapısı: at-rest şifreleme AÇIK olmadan kurulum geçerli sayılmaz.
    assert_eq!(health["atRestEncrypted"], true, "at-rest sifreleme KAPALI");

    let _ = child.kill();
    let _ = child.wait();
}
